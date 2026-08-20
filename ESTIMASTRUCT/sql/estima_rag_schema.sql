-- estima_rag_schema.sql — schema dedicado para el RAG propio de EstimaStruct
-- (conocimiento del producto: motor de calculo, fichas de costeo, arquitectura,
-- + logs de automation CC002-estimastruct). Reemplaza rag.sqlite (goal-20833,
-- decision David 2026-08-17: todo en Postgres, no mas artefacto portable).
--
-- POR QUE SCHEMA APARTE, NO rag NI public
-- ────────────────────────────────────────
-- `rag.chunks` en esta misma DB ya es otra cosa (historico de presupuestos por
-- capitulo, F3.1/F3.2 roadmap_case_saas_001_scope_v2.md, ver sql/rag_schema.sql).
-- `arch_chunks` tambien es otra cosa (docs/architecture.md, vector-only). Este
-- schema es el conocimiento "como funciona EstimaStruct" que sirve la tool
-- estima_rag_search — separacion intencional, documentada en persona_md de
-- brain.agent_identities role_key='estimastruct' (rules.md regla 32).
--
-- Hibrido FTS + vector, mismo criterio que el rag_search general de Brain:
-- tsvector/GIN (keyword, reemplaza FTS5/BM25) + pgvector ivfflat (semantico,
-- reemplaza sqlite-vec vec0). Config 'simple' en to_tsvector (no stemming) para
-- no cambiar el comportamiento de matching que tenia FTS5 con tokens literales.
--
-- Escritores (2):
--   1. brain-agentic/scripts/rag/ingest_estimastruct_pg.py — incremental,
--      vault/logs/automation/CC002-estimastruct/*.md (source_hash, idempotente).
--   2. backend/scripts/backfill_estima_rag.py — one-shot, corpus de producto
--      desde el CSV depurado de PII (goal-20144).
-- Lector: backend/routers/rag.py -> GET /rag/search -> tool estima_rag_search.
--
-- Idempotente: seguro correr mas de una vez.

CREATE SCHEMA IF NOT EXISTS estima_rag;

CREATE TABLE IF NOT EXISTS estima_rag.documents (
    document_id   BIGSERIAL PRIMARY KEY,
    source_path   TEXT NOT NULL UNIQUE,
    project_id    TEXT NOT NULL,
    doc_kind      TEXT,
    source_hash   TEXT,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS estima_rag.chunks (
    chunk_id        BIGSERIAL PRIMARY KEY,
    document_id     BIGINT NOT NULL REFERENCES estima_rag.documents(document_id) ON DELETE CASCADE,
    chunk_index     INTEGER NOT NULL DEFAULT 0,
    content         TEXT NOT NULL,
    descriptor_300  TEXT,
    semantic_route  TEXT,
    domain          TEXT,
    source_path     TEXT NOT NULL,
    embedding       vector(768),
    content_tsv     tsvector GENERATED ALWAYS AS (
                        to_tsvector('simple', coalesce(content, '') || ' ' || coalesce(descriptor_300, ''))
                    ) STORED,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_estima_rag_chunks_embedding
    ON estima_rag.chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = '10');
    -- lists=10, mismo criterio que rag.chunks/arch_chunks (volumen bajo hoy)

CREATE INDEX IF NOT EXISTS idx_estima_rag_chunks_tsv
    ON estima_rag.chunks USING GIN (content_tsv);

CREATE INDEX IF NOT EXISTS idx_estima_rag_chunks_document
    ON estima_rag.chunks (document_id);

CREATE INDEX IF NOT EXISTS idx_estima_rag_chunks_route
    ON estima_rag.chunks (semantic_route);

COMMENT ON TABLE estima_rag.documents IS
  'RAG propio EstimaStruct (goal-20833). Reemplaza rag.sqlite. No confundir con rag.chunks (historico presupuestos) ni arch_chunks (architecture.md).';

COMMENT ON TABLE estima_rag.chunks IS
  'Chunks hibridos FTS(tsvector/GIN)+vector(ivfflat) del RAG propio EstimaStruct. Escritores: ingest_estimastruct_pg.py (brain-agentic, incremental) y backfill_estima_rag.py (one-shot, corpus producto). Lector: backend/routers/rag.py.';
