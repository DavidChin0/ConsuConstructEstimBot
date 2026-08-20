#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backfill_estima_rag.py — carga one-shot del corpus de producto EstimaStruct
(motor de calculo, fichas de costeo, arquitectura) a estima_rag.documents/chunks
en Postgres, desde el CSV ya depurado de PII/credenciales (goal-20144,
17/195 chunks descartados: 2 credenciales, 15 comercial-sensible).

Reemplaza a build_rag_sqlite.py (goal-20833: rag.sqlite muere, todo Postgres,
decision David 2026-08-17). Mismo CSV de entrada, mismo re-embed via Ollama
(el CSV no trae embeddings), pero destino Postgres (estima_rag.*) en vez de
un archivo rag.sqlite nuevo.

Migration-only tool: correr una vez por version de corpus, no en operacion
normal (mismo criterio que el build_rag_sqlite.py que reemplaza).

Input CSV: columnas chunk_id, source_path, project_id, semantic_route,
domain, doc_kind, chunk_type, descriptor_300, content.

Uso:
    D:\\LLM\\python\\python.exe backend\\scripts\\backfill_estima_rag.py <csv_depurado>
"""
from __future__ import annotations

import csv
import json
import sys
import time
import urllib.request
from pathlib import Path

import psycopg2

DB_HOST = "127.0.0.1"
DB_PORT = 5432
DB_NAME = "estimastruct"
DB_USER = "postgres"
PG_CREDS_FILE = Path(r"D:\Secrets\postgres_credentials.txt")

OLLAMA_URL = "http://127.0.0.1:11434"
EMBED_MODEL = "nomic-embed-text"
EMBED_DIM = 768
EMBED_TIMEOUT = 120
MAX_CONTENT_CHARS = 2000  # mismo tope defensivo que build_rag_sqlite.py


def _read_pg_password() -> str:
    for line in PG_CREDS_FILE.read_text().splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError(f"No se encontro password= en {PG_CREDS_FILE}")


def _connect():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER,
        password=_read_pg_password(),
    )


def embed(text: str) -> list[float]:
    payload = {"model": EMBED_MODEL, "input": text[:MAX_CONTENT_CHARS], "keep_alive": "5m"}
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/embed",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=EMBED_TIMEOUT) as resp:
        out = json.loads(resp.read().decode("utf-8"))
    vecs = out.get("embeddings") or []
    vec = vecs[0] if vecs else []
    if len(vec) != EMBED_DIM:
        raise ValueError(f"embedding dim={len(vec)}, esperado {EMBED_DIM}")
    return vec


def vec_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.7f}" for x in vec) + "]"


def backfill(csv_path: Path, wipe: bool) -> None:
    with open(csv_path, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    conn = _connect()
    conn.autocommit = False
    cur = conn.cursor()

    if wipe:
        cur.execute("DELETE FROM estima_rag.chunks")
        cur.execute("DELETE FROM estima_rag.documents")
        conn.commit()
        print("wipe: estima_rag.documents/chunks vaciadas")

    doc_ids: dict[str, int] = {}
    t0 = time.perf_counter()

    for i, row in enumerate(rows, 1):
        source_path = row["source_path"]
        if source_path not in doc_ids:
            cur.execute(
                """
                INSERT INTO estima_rag.documents (source_path, project_id, doc_kind)
                VALUES (%s,%s,%s)
                ON CONFLICT (source_path) DO UPDATE SET updated_at = NOW()
                RETURNING document_id
                """,
                (source_path, row["project_id"], row.get("doc_kind")),
            )
            doc_ids[source_path] = cur.fetchone()[0]
        document_id = doc_ids[source_path]

        content = row["content"]
        vec = embed(content)

        cur.execute(
            """
            INSERT INTO estima_rag.chunks
              (document_id, chunk_index, content, descriptor_300, semantic_route,
               domain, source_path, embedding)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s::vector)
            """,
            (document_id, i, content, row.get("descriptor_300"), row.get("semantic_route"),
             row.get("domain"), source_path, vec_literal(vec)),
        )

        if i % 25 == 0 or i == len(rows):
            elapsed = time.perf_counter() - t0
            print(f"  {i}/{len(rows)} chunks embebidos ({elapsed:.1f}s)")

    conn.commit()

    cur.execute("SELECT count(*) FROM estima_rag.documents")
    n_docs = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM estima_rag.chunks")
    n_chunks = cur.fetchone()[0]
    conn.close()

    print(f"\nestima_rag.documents={n_docs} estima_rag.chunks={n_chunks}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: backfill_estima_rag.py <csv_depurado> [--wipe]")
        sys.exit(1)
    backfill(Path(sys.argv[1]), wipe="--wipe" in sys.argv)
