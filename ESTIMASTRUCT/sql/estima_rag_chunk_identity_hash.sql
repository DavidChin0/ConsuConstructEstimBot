-- estima_rag_chunk_identity_hash.sql — migración aditiva para hash de identidad por chunk
-- Añadido 2026-08-24 (goal brain-agentic m2_workers).
--
-- POR QUÉ ESTA COLUMNA EXISTE
-- ────────────────────────────
-- La consolidación de memoria del agente estimastruct (chunks generados por worker
-- M2.7 + respuesta de Hooke) necesita poder deduplicar chunks idénticos antes de
-- escribir a estima_rag.chunks. Sin una columna de identidad no hay forma de saber
-- si un chunk ya existe — solo con el contenido no basta (dos fuentes distintas
-- pueden producir el mismo texto por casualidad).
--
-- La solución es un hash SHA256 hex (64 chars) calculado sobre el contenido del
-- chunk en el momento de su creación. Este hash se almacena en chunk_identity_hash.
--
-- POR QUÉ ES ADITIVO E IDEMPOTENTE
-- ─────────────────────────────────
--   · IF NOT EXISTS en el ALTER y en el CREATE INDEX — seguro correr más de una vez.
--   · No modifica ni elimina filas existentes (222 filas de producto preexistentes
--     quedan con NULL en chunk_identity_hash — el índice parcial las excluye).
--   · No toca el schema, las columnas existentes, ni los índices actuales.
--
-- QUÉ NO HACE ESTA MIGRACIÓN
-- ──────────────────────────
--   · No calcula hash para las filas existentes (las deja NULL — el pipeline de
--     ingest que recalcula ingestará chunks nuevos con hash).
--   · No borra ni reescribe datos.
--   · No hay DROP de nada.

ALTER TABLE estima_rag.chunks
    ADD COLUMN IF NOT EXISTS chunk_identity_hash TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_estima_rag_chunks_identity_hash
    ON estima_rag.chunks (chunk_identity_hash)
    WHERE chunk_identity_hash IS NOT NULL;

COMMENT ON COLUMN estima_rag.chunks.chunk_identity_hash IS
    'Hash de identidad del chunk (sha256 hex, 64 chars). Añadido para dedupe en la
     consolidación de memoria del agente estimastruct (worker M2.7 + Hooke).
     NULL en las 222 filas de producto preexistentes — el índice parcial
     (WHERE NOT NULL) las deja fuera de la restricción de unicidad.';
