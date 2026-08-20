"""
Endpoint de busqueda semantica sobre estima_rag.* (conocimiento propio de
EstimaStruct: motor de calculo, fichas de costeo, arquitectura, logs de
automation CC002-estimastruct).

Postgres (DB "estimastruct", schema estima_rag) -- goal-20833, migracion de
rag.sqlite completada 2026-08-17 (decision David: todo el RAG propio en
Postgres, worker de Brain escribe ahi directo). No es rag.chunks (historico
de presupuestos) ni arch_chunks (architecture.md) -- schema separado a
proposito, ver sql/estima_rag_schema.sql.
"""
import json
import os
import urllib.request
from pathlib import Path

import psycopg
from fastapi import APIRouter

router = APIRouter(prefix="/rag", tags=["rag"])

DB_HOST = os.environ.get("ESTIMASTRUCT_RAG_DB_HOST", "127.0.0.1")
DB_PORT = int(os.environ.get("ESTIMASTRUCT_RAG_DB_PORT", "5432"))
DB_NAME = os.environ.get("ESTIMASTRUCT_RAG_DB_NAME", "estimastruct")
DB_USER = os.environ.get("ESTIMASTRUCT_RAG_DB_USER", "postgres")
PG_CREDS_FILE = Path(r"D:\Secrets\postgres_credentials.txt")

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
EMBED_MODEL = "nomic-embed-text"
EMBED_TIMEOUT = 30


def _read_pg_password() -> str:
    pw = os.environ.get("ESTIMASTRUCT_RAG_DB_PASSWORD")
    if pw:
        return pw
    for line in PG_CREDS_FILE.read_text().splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError(f"No se encontro password= en {PG_CREDS_FILE}")


def _get_conn():
    return psycopg.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER,
        password=_read_pg_password(),
    )


def _embed(text: str) -> list[float] | None:
    """Best-effort: si Ollama no responde, la busqueda cae a solo keyword (FTS)."""
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


def _vec_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.7f}" for x in vec) + "]"


@router.get("/search")
def rag_search(q: str, top_k: int = 5):
    """Busqueda hibrida: tsvector/GIN (keyword) + pgvector ivfflat (coseno),
    score compuesto 0.4/0.6 -- mismo criterio que tenia FTS5+vec0 en rag.sqlite.

    Sin dependencia dura de Ollama: si el embedding falla, degrada a solo
    keyword en vez de tirar 500. Si Postgres no responde, error explicito
    (a diferencia de rag.sqlite ya no hay fallback de archivo local).
    """
    top_k = max(1, min(int(top_k), 20))

    try:
        conn = _get_conn()
    except Exception as exc:
        return {"error": f"No se pudo conectar a estima_rag (Postgres): {exc}"}

    try:
        cur = conn.cursor()

        # Keyword: candidatos por ts_rank sobre content_tsv (config 'simple',
        # mismo criterio no-stemming que tenia FTS5 con tokens literales).
        cur.execute(
            """
            SELECT chunk_id, ts_rank(content_tsv, plainto_tsquery('simple', %s)) AS score
            FROM estima_rag.chunks
            WHERE content_tsv @@ plainto_tsquery('simple', %s)
            ORDER BY score DESC
            LIMIT 20
            """,
            (q, q),
        )
        fts_rows = cur.fetchall()
        fts_scores: dict[int, float] = {}
        if fts_rows:
            best = max(r[1] for r in fts_rows) or 1.0
            for chunk_id, score in fts_rows:
                fts_scores[chunk_id] = (score / best) if best else 0.0  # 0..1

        # Vector: candidatos por coseno, solo si el embedding de la query salio bien.
        vec_scores: dict[int, float] = {}
        vec = _embed(q)
        if vec is not None:
            cur.execute(
                """
                SELECT chunk_id, 1 - (embedding <=> %s::vector) AS similarity
                FROM estima_rag.chunks
                ORDER BY embedding <=> %s::vector
                LIMIT 20
                """,
                (_vec_literal(vec), _vec_literal(vec)),
            )
            for chunk_id, similarity in cur.fetchall():
                vec_scores[chunk_id] = float(similarity)

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
            cur.execute(
                "SELECT content, source_path, semantic_route, descriptor_300 "
                "FROM estima_rag.chunks WHERE chunk_id = %s",
                (chunk_id,),
            )
            row = cur.fetchone()
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
