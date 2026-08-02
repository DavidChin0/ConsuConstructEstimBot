"""
Endpoint de busqueda semantica sobre rag.sqlite (conocimiento propio de
EstimaStruct: motor de calculo, fichas de costeo, arquitectura).

rag.sqlite es un artefacto de build separado de estimacion.db (transaccional):
se reconstruye con backend/scripts/build_rag_sqlite.py cuando cambia el corpus,
no vive dentro del ORM de SQLAlchemy porque no es dato de negocio del tenant.

Fase intermedia hacia el SaaS -- el target final del RAG es Postgres (mismo
motor que consuconstruct), esto deja el semantic search funcionando ya.
"""
import json
import os
import re
import sqlite3
import urllib.request
from pathlib import Path

import sqlite_vec
from fastapi import APIRouter

router = APIRouter(prefix="/rag", tags=["rag"])

RAG_DB_PATH = Path(os.environ.get("ESTIMASTRUCT_RAG_DB", r"C:\EstimaStruct\data\rag.sqlite"))
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
EMBED_MODEL = "nomic-embed-text"
EMBED_TIMEOUT = 30


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(RAG_DB_PATH))
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn


def _embed(text: str) -> list[float] | None:
    """Best-effort: si Ollama no responde, la busqueda cae a solo FTS5 (keyword)."""
    payload = {"model": EMBED_MODEL, "input": text[:2000], "keep_alive": "5m"}
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/embed",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=EMBED_TIMEOUT) as resp:
            out = json.loads(resp.read().decode("utf-8"))
        vec = (out.get("embeddings") or [None])[0]
        return vec if vec and len(vec) == 768 else None
    except Exception:
        return None


def _fts5_safe_query(q: str) -> str:
    """Escapa la query de usuario para FTS5 MATCH.

    FTS5 interpreta '-', '"', '*', '(', ')', ':' y las keywords AND/OR/NOT/NEAR
    como sintaxis de operadores, no como texto literal -- un guion en la query
    ("dibujar-desde-DB") ya tiraba 'fts5: syntax error near "-"' (500 real,
    encontrado 2026-08-02 probando estima_rag_search). Se envuelve cada token
    en comillas dobles (escapando comillas internas) para forzar match literal
    de frase, sin interpretacion de operadores.
    """
    tokens = re.findall(r"\w+", q, re.UNICODE)
    if not tokens:
        return '""'
    return " ".join(f'"{t}"' for t in tokens)


@router.get("/search")
def rag_search(q: str, top_k: int = 5):
    """Busqueda hibrida: FTS5 (BM25 keyword) + vec0 (coseno), score compuesto.

    Sin dependencia dura de Ollama: si el embedding falla, degrada a solo
    keyword en vez de tirar 500 -- mismo criterio best-effort que
    fast_search.py del lado ConsuConstruct. Igual si FTS5 revienta por sintaxis
    (ver _fts5_safe_query): degrada a solo vector en vez de 500.
    """
    if not RAG_DB_PATH.exists():
        return {"error": f"rag.sqlite no existe en {RAG_DB_PATH}. "
                          f"Correr backend/scripts/build_rag_sqlite.py primero."}

    top_k = max(1, min(int(top_k), 20))
    conn = _get_conn()
    try:
        # FTS5: candidatos por keyword, normalizamos bm25 (mas negativo = mejor)
        # a un score positivo 0..1 para poder combinarlo con similarity.
        try:
            fts_rows = conn.execute(
                """
                SELECT rowid, bm25(rag_chunks_fts) AS score
                FROM rag_chunks_fts
                WHERE rag_chunks_fts MATCH ?
                ORDER BY score
                LIMIT 20
                """,
                (_fts5_safe_query(q),),
            ).fetchall()
        except sqlite3.OperationalError:
            fts_rows = []
        fts_scores: dict[int, float] = {}
        if fts_rows:
            worst = min(r[1] for r in fts_rows)  # bm25 mas negativo del set
            for chunk_id, score in fts_rows:
                fts_scores[chunk_id] = score / worst if worst else 0.0  # 0..1

        # vec0: candidatos por coseno, solo si el embedding de la query salio bien.
        vec_scores: dict[int, float] = {}
        vec = _embed(q)
        if vec is not None:
            vec_lit = "[" + ",".join(f"{x:.7f}" for x in vec) + "]"
            vec_rows = conn.execute(
                """
                SELECT chunk_id, distance FROM rag_chunks_vec
                WHERE embedding MATCH ? AND k = 20
                ORDER BY distance
                """,
                (vec_lit,),
            ).fetchall()
            for chunk_id, distance in vec_rows:
                vec_scores[chunk_id] = 1 - distance  # cosine similarity

        candidates = set(fts_scores) | set(vec_scores)
        if not candidates:
            return {"query": q, "results": [], "count": 0}

        ranked = sorted(
            candidates,
            key=lambda cid: fts_scores.get(cid, 0.0) * 0.4 + vec_scores.get(cid, 0.0) * 0.6,
            reverse=True,
        )[:top_k]

        results = []
        for chunk_id in ranked:
            row = conn.execute(
                "SELECT content, source_path, semantic_route, descriptor_300 "
                "FROM rag_chunks WHERE chunk_id = ?",
                (chunk_id,),
            ).fetchone()
            if row is None:
                continue
            content, source_path, semantic_route, descriptor_300 = row
            results.append({
                "chunk_id": chunk_id,
                "content": content,
                "source_path": source_path,
                "semantic_route": semantic_route,
                "descriptor_300": descriptor_300,
                "score_fts": round(fts_scores.get(chunk_id, 0.0), 4),
                "score_vec": round(vec_scores.get(chunk_id, 0.0), 4),
            })

        return {"query": q, "results": results, "count": len(results),
                "embedding_available": vec is not None}
    finally:
        conn.close()
