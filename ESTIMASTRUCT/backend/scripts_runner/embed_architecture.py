"""
Chunk architecture.md by §N sections → embed with nomic → insert into arch_chunks (pgvector).

Usage:
    python embed_architecture.py [--arch PATH] [--project NAME] [--wipe]
"""

import argparse
import os
import re
import sys
import json
import urllib.request
from pathlib import Path
from datetime import datetime

# -- config -------------------------------------------------------------------
ARCH_DEFAULT = Path(__file__).parents[2] / "docs" / "architecture.md"
OLLAMA_EMBED_URL = "http://127.0.0.1:11434/api/embeddings"
EMBED_MODEL = "nomic-embed-text"
DB_HOST = "127.0.0.1"
DB_PORT = 5432
DB_NAME = "estimastruct"
DB_USER = "postgres"
PG_CREDS_FILE = r"D:\Secrets\postgres_credentials.txt"

# -- helpers ------------------------------------------------------------------

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
    return data["embedding"]


MAX_WORDS = 600  # nomic-embed-text safe limit


def _sub_chunk(ref: str, title: str, header: str, body: str) -> list[dict]:
    """Split body by ### headers when section is too large."""
    sub_parts = re.split(r"(?m)^(### .+)$", body)
    results = []

    # leading text before first ###
    lead = sub_parts[0].strip()
    if lead:
        content = f"{header}\n\n{lead}"
        results.append({"section_ref": ref, "section_title": title, "content": content})

    i = 1
    while i < len(sub_parts) - 1:
        sh = sub_parts[i].strip()
        sb = sub_parts[i + 1].strip()
        i += 2
        sub_title = re.sub(r"^###\s*", "", sh).strip()
        m = re.search(r"(§[\d.]+)", sh)
        sub_ref = m.group(1) if m else ref

        content = f"{header} > {sh}\n\n{sb}"
        # if still too big, truncate
        words = content.split()
        if len(words) > MAX_WORDS:
            content = " ".join(words[:MAX_WORDS]) + "\n\n[truncated — see full docs/architecture.md]"

        results.append({"section_ref": sub_ref, "section_title": f"{title} > {sub_title}", "content": content})

    return results if results else [{"section_ref": ref, "section_title": title, "content": f"{header}\n\n{body}"}]


def chunk_architecture(path: Path) -> list[dict]:
    """Split by ## headers; sub-chunk by ### if section > MAX_WORDS."""
    text = path.read_text(encoding="utf-8")
    chunks = []
    parts = re.split(r"(?m)^(## .+)$", text)

    preamble = parts[0].strip()
    if preamble:
        chunks.append({"section_ref": "§0", "section_title": "Preamble", "content": preamble})

    i = 1
    while i < len(parts) - 1:
        header = parts[i].strip()
        body   = parts[i + 1].strip()
        i += 2

        m = re.search(r"(§[\d.]+)", header)
        ref   = m.group(1) if m else header[:20]
        title = re.sub(r"^##\s*", "", header).strip()

        content = f"{header}\n\n{body}"
        if token_approx(content) > MAX_WORDS:
            chunks.extend(_sub_chunk(ref, title, header, body))
        else:
            chunks.append({"section_ref": ref, "section_title": title, "content": content})

    return chunks


def token_approx(text: str) -> int:
    return len(text.split())


# -- main ---------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--arch", default=str(ARCH_DEFAULT))
    parser.add_argument("--project", default="estimastruct")
    parser.add_argument("--wipe", action="store_true", help="Delete existing chunks for project before insert")
    args = parser.parse_args()

    arch_path = Path(args.arch)
    if not arch_path.exists():
        print(f"ERROR: architecture.md not found at {arch_path}", file=sys.stderr)
        sys.exit(1)

    pw = read_pg_password()
    conn = get_conn(pw)
    cur = conn.cursor()

    if args.wipe:
        cur.execute("DELETE FROM arch_chunks WHERE project = %s", (args.project,))
        print(f"Wiped existing chunks for project={args.project}")

    chunks = chunk_architecture(arch_path)
    print(f"Chunked {len(chunks)} sections from {arch_path.name}")

    inserted = 0
    for i, chunk in enumerate(chunks, 1):
        ref   = chunk["section_ref"]
        title = chunk["section_title"]
        content = chunk["content"]
        tokens = token_approx(content)

        print(f"  [{i:02d}/{len(chunks)}] {ref} — {title[:50]} ({tokens} words) ... ", end="", flush=True)

        try:
            vec = embed(content)
        except Exception as e:
            print(f"EMBED ERROR: {e}")
            continue

        cur.execute(
            """
            INSERT INTO arch_chunks (project, doc_path, section_ref, section_title, content, token_count, embedding, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s::vector, NOW())
            ON CONFLICT DO NOTHING
            """,
            (args.project, str(arch_path), ref, title, content, tokens, str(vec)),
        )
        inserted += 1
        print("✓")

    conn.commit()
    conn.close()

    print(f"\nDone. {inserted}/{len(chunks)} chunks embedded and stored in arch_chunks.")
    print(f"Query example:")
    print(f"  SELECT section_ref, section_title, content")
    print(f"  FROM arch_chunks")
    print(f"  ORDER BY embedding <=> '<query_vector>'::vector")
    print(f"  LIMIT 3;")


if __name__ == "__main__":
    main()
