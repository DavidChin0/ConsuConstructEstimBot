"""Acceptance gates for EstimaStruct v1.4 (goal-21174).

Read-only with respect to the versioned SQLite. It does not crawl or scrape.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone


ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "v1.4" / "estimacion.db"
OUT = ROOT / "release" / "ESTIMASTRUCT_GATES_v1.4.json"
AUDIT_CSV = ROOT / "development" / "rendimientos_audit" / "pipeline" / "data" / "rendimientos_auditados.csv"
SOURCE_LOG = ROOT / "development" / "rendimientos_audit" / "pipeline" / "data" / "bitacora_fuentes_no_encontradas.md"
PRICE_TABLES = ["partida", "insumo_partida", "recurso", "capitulo", "presupuesto"]
EXPECTED_PRICE_HASH = "635a3e8f7c666be2a9f33ea16048c72a42537d5752fb9dccb7b32736d0d8fe20"


def table_hash(conn: sqlite3.Connection, table: str) -> tuple[str, int]:
    cur = conn.execute(f'SELECT * FROM [{table}]')
    columns = [item[0] for item in cur.description]
    rows = cur.fetchall()
    digest = hashlib.sha256()
    digest.update("|".join(columns).encode("utf-8", "replace"))
    for row in rows:
        digest.update("|".join("" if value is None else str(value) for value in row).encode("utf-8", "replace"))
        digest.update(b"\n")
    return digest.hexdigest(), len(rows)


def inspect_db() -> dict:
    with sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True) as conn:
        quick_check = conn.execute("PRAGMA quick_check").fetchone()[0]
        user_version = conn.execute("PRAGMA user_version").fetchone()[0]
        counts = dict(conn.execute("SELECT fuente, COUNT(*) FROM rendimiento_audit GROUP BY fuente"))
        total = conn.execute("SELECT COUNT(*) FROM rendimiento_audit").fetchone()[0]
        missing_source = conn.execute(
            "SELECT COUNT(*) FROM rendimiento_audit "
            "WHERE COALESCE(TRIM(fuente_url), '') = '' OR "
            "COALESCE(TRIM(fuente_codigo), '') = ''"
        ).fetchone()[0]
        hashes = {table: table_hash(conn, table) for table in PRICE_TABLES}
    price_hash = hashlib.sha256("|".join(hashes[t][0] for t in PRICE_TABLES).encode()).hexdigest()
    return {
        "path": str(DB.relative_to(ROOT)),
        "sha256": hashlib.sha256(DB.read_bytes()).hexdigest(),
        "quick_check": quick_check,
        "user_version": user_version,
        "audit": {"total": total, "by_source": counts, "missing_source": missing_source},
        "price_tables": {t: {"sha256": hashes[t][0], "rows": hashes[t][1]} for t in PRICE_TABLES},
        "price_hash": price_hash,
    }


def run(name: str, command: list[str], cwd: Path, env: dict | None = None) -> dict:
    started = datetime.now(timezone.utc)
    result = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True)
    return {
        "name": name,
        "command": subprocess.list2cmdline(command),
        "started_at": started.isoformat(),
        "exit_code": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def check_export() -> dict:
    with AUDIT_CSV.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    sources: dict[str, int] = {}
    for row in rows:
        sources[row["fuente"]] = sources.get(row["fuente"], 0) + 1
    missing = sum(not row["referencia_online"].strip() or not row["pagina_ficha"].strip() for row in rows)
    forbidden = sum(row["fuente"] not in {"FHIS", "CYPE_HN"} for row in rows)
    return {"path": str(AUDIT_CSV.relative_to(ROOT)), "rows": len(rows), "by_source": sources,
            "missing_traceability": missing, "forbidden_sources": forbidden}


def check_suarez_policy() -> dict:
    log_text = SOURCE_LOG.read_text(encoding="utf-8")
    required = [
        "https://books.google.com/books?id=f8G8UFFjd9sC",
        "9681800672",
        "NO_DISPONIBLE_EN_VISTA_LEGITIMA",
        "NO_VERIFICADO",
    ]
    missing_log_fields = [value for value in required if value not in log_text]
    with sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True) as conn:
        sqlite_rows = conn.execute(
            "SELECT COUNT(*) FROM rendimiento_audit WHERE fuente = 'SUAREZ_SALAZAR'"
        ).fetchone()[0]
    return {
        "log_path": str(SOURCE_LOG.relative_to(ROOT)),
        "legitimate_catalog_url": "https://books.google.com/books?id=f8G8UFFjd9sC",
        "edition": "3a ed., Editorial Limusa, 1977, 451 paginas",
        "isbn_10": "9681800672",
        "isbn_13": "9789681800673",
        "page_or_table": "NO_DISPONIBLE_EN_VISTA_LEGITIMA",
        "status": "NO_VERIFICADO",
        "sqlite_rows": sqlite_rows,
        "missing_log_fields": missing_log_fields,
    }


def main() -> int:
    before = inspect_db()
    env = os.environ.copy()
    env.update({
        "ESTIMA_DB_PATH": str(DB),
        "ESTIMASTRUCT_AUTO_CREATE_SCHEMA": "false",
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    gates = [
        run("build", ["node", "--check", "frontend/js/app.js"], ROOT),
        run("build_core", ["node", "--check", "frontend/js/core.js"], ROOT),
        run("tests", [sys.executable, "-m", "pytest", "pipeline/tests", "-q"],
            ROOT / "development" / "rendimientos_audit"),
        run("smoke", [sys.executable, "release/smoke_v14.py"], ROOT, env),
    ]
    after = inspect_db()
    export = check_export()
    suarez = check_suarez_policy()
    expected_counts = {"FHIS": 181, "CYPE_HN": 76}
    ok = (
        all(gate["exit_code"] == 0 for gate in gates)
        and before == after
        and before["quick_check"] == "ok"
        and before["user_version"] == 14
        and before["audit"]["total"] == 257
        and before["audit"]["by_source"] == expected_counts
        and before["audit"]["missing_source"] == 0
        and before["price_hash"] == EXPECTED_PRICE_HASH
        and export["rows"] == 257
        and export["by_source"] == expected_counts
        and export["missing_traceability"] == 0
        and export["forbidden_sources"] == 0
        and suarez["sqlite_rows"] == 0
        and not suarez["missing_log_fields"]
    )
    commit = subprocess.run(["git", "-c", f"safe.directory={ROOT.parent.as_posix()}", "rev-parse", "HEAD"],
                            cwd=ROOT, text=True, capture_output=True).stdout.strip()
    artifact = {
        "schema": "ESTIMASTRUCT_GATES_JSON/1",
        "goal": 21174,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "commit": commit,
        "db_version": "v1.4",
        "success": ok,
        "database_before": before,
        "database_after": after,
        "price_hash_before": before["price_hash"],
        "price_hash_after": after["price_hash"],
        "audited_rendimientos_export": export,
        "suarez_salazar_policy": suarez,
        "gates": {gate["name"]: gate for gate in gates},
    }
    OUT.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"success": ok, "artifact": str(OUT), "gates": {g["name"]: g["exit_code"] for g in gates},
                      "price_hash": before["price_hash"], "audit": before["audit"]}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
