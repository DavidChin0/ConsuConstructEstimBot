"""
rag_sync.py — extracción controlada de presupuesto/partida/insumo_partida hacia
rag.chunks (histórico de obras, RAG pgvector — F3.1 de docs/roadmap_case_saas_001_scope_v2.md).

Mismo patrón que embed_architecture.py (ya existe en este directorio): psycopg3,
credenciales desde D:\\Secrets\\postgres_credentials.txt, embeddings nomic-embed-text
vía Ollama local. NO usa el patrón de cola de brain-agentic/scripts/rag/vault_sync.py
(doc_manifest + FOR UPDATE SKIP LOCKED) porque acá no hay archivos que escanear —
la fuente es Postgres mismo, y el volumen (6 presupuestos hoy) no lo justifica.

SEGURIDAD (rule #18 del vault — nunca modificar BD sin confirmación explícita):
  - Default es --dry-run. Sin --write, el script SOLO lee `public.*` y muestra
    qué chunks generaría — cero conexión a Ollama, cero escritura.
  - --write exige que el schema `rag` ya exista (creado aparte, gate del Director).
    Si no existe, el script se detiene con un mensaje claro, no lo crea él mismo.
  - Nunca toca `public.*` (producción). Solo lee de ahí; solo escribe a `rag.*`.

USO
───
  python rag_sync.py --dry-run                  # default, no toca nada
  python rag_sync.py --dry-run --presupuesto ID  # preview de una sola obra
  python rag_sync.py --write                     # requiere schema rag ya creado

Contrato de BD: pendiente — se crea junto con el schema `rag` (fuera de este script).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

DB_HOST = "127.0.0.1"
DB_PORT = 5432
DB_NAME = "estimastruct"
DB_USER = "postgres"
PG_CREDS_FILE = r"D:\Secrets\postgres_credentials.txt"

OLLAMA_EMBED_URL = "http://127.0.0.1:11434/api/embeddings"
EMBED_MODEL = "nomic-embed-text"
EMBED_DIM = 768
MAX_WORDS = 600  # mismo límite que embed_architecture.py


def log(msg: str) -> None:
    print(f"[rag_sync] {msg}", flush=True)


# ─────────────────────────────────────────────────────────────────────────────
# Conexión — mismo patrón que embed_architecture.py
# ─────────────────────────────────────────────────────────────────────────────

def read_pg_password() -> str:
    try:
        text = Path(PG_CREDS_FILE).read_text()
        for line in text.splitlines():
            if line.startswith("password="):
                return line.split("=", 1)[1].strip()
    except FileNotFoundError:
        pass
    return os.environ.get("PGPASSWORD", "")


def get_conn(pw: str):
    import psycopg
    return psycopg.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=pw
    )


def embed(text: str) -> list[float]:
    payload = json.dumps({"model": EMBED_MODEL, "prompt": text}).encode()
    req = urllib.request.Request(
        OLLAMA_EMBED_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())
    vec = data["embedding"]
    if len(vec) != EMBED_DIM:
        raise ValueError(f"embedding dim={len(vec)}, esperado {EMBED_DIM}")
    return vec


def token_approx(text: str) -> int:
    return len(text.split())


def rag_schema_exists(cur) -> bool:
    cur.execute("SELECT 1 FROM information_schema.schemata WHERE schema_name = 'rag'")
    return cur.fetchone() is not None


# ─────────────────────────────────────────────────────────────────────────────
# Extracción — public.presupuesto/capitulo/partida/insumo_partida
# ─────────────────────────────────────────────────────────────────────────────

def fetch_presupuestos(cur, presupuesto_id: str | None) -> list[dict]:
    if presupuesto_id:
        cur.execute(
            "SELECT id, nombre, cliente, fecha, moneda FROM presupuesto WHERE id = %s",
            (presupuesto_id,),
        )
    else:
        cur.execute("SELECT id, nombre, cliente, fecha, moneda FROM presupuesto ORDER BY fecha DESC")
    cols = ["id", "nombre", "cliente", "fecha", "moneda"]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def fetch_capitulos(cur, presupuesto_id: str) -> list[dict]:
    cur.execute(
        """SELECT id, clave, nombre, orden FROM capitulo
           WHERE presupuesto_id = %s ORDER BY orden""",
        (presupuesto_id,),
    )
    cols = ["id", "clave_csi", "nombre", "orden"]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def fetch_partidas(cur, capitulo_id: str) -> list[dict]:
    cur.execute(
        """SELECT clave_csi, descripcion, unidad, cantidad, precio_unitario, total
           FROM partida WHERE capitulo_id = %s ORDER BY orden""",
        (capitulo_id,),
    )
    cols = ["clave_csi", "descripcion", "unidad", "cantidad", "precio_unitario", "total"]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def build_capitulo_chunk(presu: dict, cap: dict, partidas: list[dict]) -> dict:
    """Un chunk por capítulo: encabezado de la obra + tabla de sus partidas.
    Mismo patrón de sub-chunking por sección que embed_architecture.py — acá
    la 'sección' natural es el capítulo CSI en vez de un ## header de Markdown."""
    header = (
        f"OBRA: {presu['nombre']} (cliente: {presu['cliente'] or 's/d'}, "
        f"fecha: {presu['fecha']}, moneda: {presu['moneda']})\n"
        f"CAPÍTULO {cap['clave_csi']}: {cap['nombre']}"
    )
    lines = [
        f"  - {p['clave_csi']} {p['descripcion']} | {p['cantidad']} {p['unidad']} "
        f"× {p['precio_unitario']} = {p['total']}"
        for p in partidas
    ]
    content = header + "\n\n" + "\n".join(lines) if lines else header + "\n\n(sin partidas)"
    words = content.split()
    if len(words) > MAX_WORDS:
        content = " ".join(words[:MAX_WORDS]) + "\n\n[truncado — ver presupuesto completo en la app]"
    return {
        "presupuesto_id": presu["id"],
        "capitulo_ref": cap["clave_csi"],
        "capitulo_title": cap["nombre"],
        "content": content,
        "token_count": token_approx(content),
        "n_partidas": len(partidas),
    }


def build_chunks(cur, presupuestos: list[dict]) -> list[dict]:
    chunks: list[dict] = []
    for presu in presupuestos:
        capitulos = fetch_capitulos(cur, presu["id"])
        for cap in capitulos:
            partidas = fetch_partidas(cur, cap["id"])
            chunks.append(build_capitulo_chunk(presu, cap, partidas))
    return chunks


# ─────────────────────────────────────────────────────────────────────────────
# Escritura — solo en modo --write, solo a rag.chunks
# ─────────────────────────────────────────────────────────────────────────────

def write_chunk(cur, chunk: dict, vec: list[float]) -> None:
    cur.execute(
        """
        INSERT INTO rag.chunks
            (presupuesto_id, capitulo_ref, capitulo_title, content, token_count, embedding, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s::vector, NOW())
        ON CONFLICT (presupuesto_id, capitulo_ref) DO UPDATE SET
            capitulo_title = EXCLUDED.capitulo_title,
            content        = EXCLUDED.content,
            token_count    = EXCLUDED.token_count,
            embedding      = EXCLUDED.embedding,
            updated_at     = NOW()
        """,
        (chunk["presupuesto_id"], chunk["capitulo_ref"], chunk["capitulo_title"],
         chunk["content"], chunk["token_count"], str(vec)),
    )


# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="rag_sync — presupuesto/partida -> rag.chunks (EstimaStruct)")
    ap.add_argument("--dry-run", action="store_true", default=True,
                     help="default: solo muestra qué se generaría, no toca Ollama ni escribe")
    ap.add_argument("--write", action="store_true",
                     help="escribe de verdad a rag.chunks — requiere schema rag ya creado")
    ap.add_argument("--presupuesto", metavar="ID", help="limitar a una sola obra")
    args = ap.parse_args()

    write_mode = args.write
    dry_run = not write_mode

    pw = read_pg_password()
    conn = get_conn(pw)
    cur = conn.cursor()

    try:
        if write_mode and not rag_schema_exists(cur):
            log("ABORTADO: schema 'rag' no existe todavía.")
            log("Ese DDL es un paso aparte, gateado por el Director (rule #18 del vault).")
            log("Corré con --dry-run mientras tanto — no requiere el schema.")
            return 1

        presupuestos = fetch_presupuestos(cur, args.presupuesto)
        if not presupuestos:
            log("sin presupuestos que coincidan — nada que hacer")
            return 0

        chunks = build_chunks(cur, presupuestos)
        log(f"{len(presupuestos)} presupuesto(s) -> {len(chunks)} chunk(s) de capítulo")

        if dry_run:
            for c in chunks:
                log(f"  [preview] {c['presupuesto_id']} · {c['capitulo_ref']} "
                    f"{c['capitulo_title'][:40]:<40} {c['n_partidas']:>3} partidas, "
                    f"{c['token_count']} words")
            log("dry-run: nada escrito, Ollama no fue llamado")
            return 0

        written = 0
        for c in chunks:
            try:
                vec = embed(c["content"])
            except (urllib.error.URLError, ValueError) as exc:
                log(f"  EMBED ERROR {c['presupuesto_id']}/{c['capitulo_ref']}: {exc}")
                continue
            write_chunk(cur, c, vec)
            written += 1
            log(f"  OK {c['presupuesto_id']} · {c['capitulo_ref']} ({c['n_partidas']} partidas)")

        conn.commit()
        log(f"write: {written}/{len(chunks)} chunks escritos a rag.chunks")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
