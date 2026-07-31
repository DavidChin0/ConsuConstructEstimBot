-- rag_schema.sql — schema dedicado para el RAG de histórico de obras (F3.1/F3.2
-- de docs/roadmap_case_saas_001_scope_v2.md). Ejecutado a mano (mismo patrón que
-- arch_chunks/csi_embeddings, que tampoco pasaron por Alembic — este repo no
-- tiene convención sql/ previa; se crea acá siguiendo la de brain-agentic).
--
-- POR QUÉ SCHEMA APARTE, NO public
-- ─────────────────────────────────
-- rules.md #19 ("un solo catálogo por kind, no crear paralelos") y la decisión
-- ya escrita en el roadmap: "esquema rag dentro de estimastruct, con tenant_id
-- en cada chunk". Separa el dominio del Estima-Agent (dueño de este schema) del
-- dominio de producción (public, solo lo escribe el backend FastAPI).
--
-- tenant_id nullable desde ya: hoy cliente único, pero F1 (multi-tenancy) no
-- debería requerir re-schema, solo poblar la columna que ya existe.
--
-- Idempotente: seguro correr más de una vez.

CREATE SCHEMA IF NOT EXISTS rag;

CREATE TABLE IF NOT EXISTS rag.chunks (
    id             BIGSERIAL PRIMARY KEY,
    presupuesto_id VARCHAR(36) NOT NULL REFERENCES public.presupuesto(id) ON DELETE CASCADE,
    tenant_id      TEXT,                       -- NULL hoy (cliente único). F1 lo puebla, no re-schema.
    capitulo_ref   TEXT NOT NULL,               -- capitulo.clave (ej. "03")
    capitulo_title TEXT NOT NULL,
    content        TEXT NOT NULL,
    token_count    INTEGER NOT NULL,
    embedding      vector(768),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (presupuesto_id, capitulo_ref)
);

CREATE INDEX IF NOT EXISTS idx_rag_chunks_embedding
    ON rag.chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = '10');
    -- lists=10, mismo valor que arch_chunks (volumen bajo hoy: 6 obras, 90 chunks)

CREATE INDEX IF NOT EXISTS idx_rag_chunks_presupuesto
    ON rag.chunks (presupuesto_id);

CREATE INDEX IF NOT EXISTS idx_rag_chunks_tenant
    ON rag.chunks (tenant_id);

COMMENT ON TABLE rag.chunks IS
  'Histórico de presupuestos por capítulo, para RAG (F3.1/F3.2 roadmap_case_saas_001_scope_v2.md). '
  'Escritor único: backend/scripts_runner/rag_sync.py --write. Nunca escribir a mano.';
