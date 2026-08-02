#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_rag_sqlite.py — construye rag.sqlite (RAG semántico portable de EstimaStruct)
desde un CSV depurado de chunks exportado de rag.chunks (Postgres, ConsuConstruct).

Fase intermedia hacia el SaaS: el target final del RAG es Postgres (mismo motor
que consuconstruct), pero mientras se arma esa infraestructura, este SQLite deja
el semantic search funcionando YA, embebido en el mismo repo que ya usa SQLite
para estimacion.db (backend/db.py). No es el diseño permanente — es la base
mínima para no bloquear el producto en lo que Postgres del SaaS está listo.

Migration-only tool: correr una vez por versión de corpus, no en operación
normal (mismo criterio que routers/updater.py para materiales/MO).

Input: CSV con columnas chunk_id, source_path, project_id, semantic_route,
domain, doc_kind, chunk_type, descriptor_300, content — ya depurado de
credenciales/PII/datos comerciales sensibles (ver goal-20144, 17/195 chunks
descartados antes de este export).

Output: rag.sqlite con:
  - rag_documents / rag_chunks: datos planos
  - rag_chunks_fts: FTS5 (BM25 keyword, stdlib, sin dependencias)
  - rag_chunks_vec: sqlite-vec vec0 (coseno, embeddings nomic-embed-text 768d)

Uso:
    D:\\LLM\\python\\python.exe backend\\scripts\\build_rag_sqlite.py <csv_depurado>
"""
from __future__ import annotations

import csv
import json
import sqlite3
import sys
import time
import urllib.request
from pathlib import Path

import sqlite_vec

RAG_DB_PATH = Path(r"C:\EstimaStruct\data\rag.sqlite")

OLLAMA_URL = "http://127.0.0.1:11434"
EMBED_MODEL = "nomic-embed-text"
EMBED_DIM = 768
EMBED_TIMEOUT = 120
MAX_CONTENT_CHARS = 2000  # mismo tope defensivo que fast_search.py::MAX_QUERY_CHARS


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


SCHEMA = """
CREATE TABLE rag_documents (
  document_id   INTEGER PRIMARY KEY AUTOINCREMENT,
  source_path   TEXT NOT NULL UNIQUE,
  project_id    TEXT NOT NULL,
  doc_kind      TEXT,
  updated_at    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE rag_chunks (
  chunk_id        INTEGER PRIMARY KEY,
  document_id     INTEGER NOT NULL REFERENCES rag_documents(document_id),
  chunk_index     INTEGER NOT NULL DEFAULT 0,
  content         TEXT NOT NULL,
  descriptor_300  TEXT,
  semantic_route  TEXT,
  domain          TEXT,
  source_path     TEXT NOT NULL
);
CREATE INDEX idx_rag_chunks_document ON rag_chunks(document_id);
CREATE INDEX idx_rag_chunks_route ON rag_chunks(semantic_route);

CREATE VIRTUAL TABLE rag_chunks_fts USING fts5(
  content, descriptor_300, content='rag_chunks', content_rowid='chunk_id'
);
"""


def build(csv_path: Path) -> None:
    RAG_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if RAG_DB_PATH.exists():
        RAG_DB_PATH.unlink()

    conn = sqlite3.connect(str(RAG_DB_PATH))
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.execute("PRAGMA journal_mode=WAL")

    conn.executescript(SCHEMA)
    conn.execute(
        f"CREATE VIRTUAL TABLE rag_chunks_vec USING vec0("
        f"chunk_id INTEGER PRIMARY KEY, embedding float[{EMBED_DIM}] distance_metric=cosine)"
    )

    with open(csv_path, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    doc_ids: dict[str, int] = {}
    cur = conn.cursor()
    t0 = time.perf_counter()

    for i, row in enumerate(rows, 1):
        source_path = row["source_path"]
        if source_path not in doc_ids:
            cur.execute(
                "INSERT INTO rag_documents (source_path, project_id, doc_kind) VALUES (?,?,?)",
                (source_path, row["project_id"], row.get("doc_kind")),
            )
            doc_ids[source_path] = cur.lastrowid
        document_id = doc_ids[source_path]

        chunk_id = int(row["chunk_id"]) if row.get("chunk_id") else i
        content = row["content"]

        cur.execute(
            """
            INSERT INTO rag_chunks
              (chunk_id, document_id, chunk_index, content, descriptor_300,
               semantic_route, domain, source_path)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            (chunk_id, document_id, i, content, row.get("descriptor_300"),
             row.get("semantic_route"), row.get("domain"), source_path),
        )
        cur.execute(
            "INSERT INTO rag_chunks_fts (rowid, content, descriptor_300) VALUES (?,?,?)",
            (chunk_id, content, row.get("descriptor_300") or ""),
        )

        vec = embed(content)
        cur.execute(
            "INSERT INTO rag_chunks_vec (chunk_id, embedding) VALUES (?,?)",
            (chunk_id, vec_literal(vec)),
        )

        if i % 25 == 0 or i == len(rows):
            elapsed = time.perf_counter() - t0
            print(f"  {i}/{len(rows)} chunks embebidos ({elapsed:.1f}s)")

    conn.commit()

    n_docs = conn.execute("SELECT count(*) FROM rag_documents").fetchone()[0]
    n_chunks = conn.execute("SELECT count(*) FROM rag_chunks").fetchone()[0]
    n_vec = conn.execute("SELECT count(*) FROM rag_chunks_vec").fetchone()[0]
    conn.close()

    print(f"\n{RAG_DB_PATH}")
    print(f"documents={n_docs} chunks={n_chunks} vectors={n_vec}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: build_rag_sqlite.py <csv_depurado>")
        sys.exit(1)
    build(Path(sys.argv[1]))
