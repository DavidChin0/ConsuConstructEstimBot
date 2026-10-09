"""
Worker Report — reporte en vivo del hooke_worker (EstimaStruct) desde Postgres.

El worker (scripts/agents/hooke_worker) ya escribe en Postgres `consuconstruct`
schema `brain` (record.py): brain.sessions, brain.estimastruct_attempt_memory,
brain.goals.context. Este router SOLO LEE esas tablas y las expone al frontend
para que el dashboard muestre qué hizo el agente, con qué modelo, qué tools usó
y cómo van los goals. Read-only: nunca escribe a Postgres.

Credenciales: D:\\Secrets\\postgres_credentials.txt (k=v, keys 'role'/'password').
Si Postgres está caído, devuelve JSON de error controlado (no 500).
"""
from fastapi import APIRouter
from pathlib import Path
import os

router = APIRouter(prefix="/worker", tags=["worker"])

_CREDS_PATH = os.getenv("BRAIN_PG_CREDS", r"D:\Secrets\postgres_credentials.txt")
_PG_HOST = os.getenv("BRAIN_PG_HOST", "127.0.0.1")
_PG_PORT = int(os.getenv("BRAIN_PG_PORT", "5432"))
_PG_DB = os.getenv("BRAIN_PG_DB", "consuconstruct")
_PROJECT = "estimastruct"


def _creds() -> dict:
    d = {}
    try:
        for line in open(_CREDS_PATH, encoding="utf-8"):
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                d[k.strip().lower()] = v.strip()
    except OSError:
        pass
    return d


def _connect():
    import psycopg2
    d = _creds()
    return psycopg2.connect(
        host=_PG_HOST, port=_PG_PORT, dbname=_PG_DB,
        user=d.get("role", "postgres"), password=d.get("password", ""),
        connect_timeout=5,
    )


def _q(sql, params=()):
    """Ejecuta SELECT read-only, devuelve lista de dicts. Lanza excepción si falla."""
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()


def _err(e):
    return {"ok": False, "error": str(e)[:300], "postgres": "unreachable"}


@router.get("/health")
def worker_health():
    """¿Postgres brain alcanzable?"""
    try:
        rows = _q("SELECT 1 AS ok")
        return {"ok": True, "postgres": "up", "db": _PG_DB}
    except Exception as e:
        return _err(e)


@router.get("/report")
def worker_report(limit: int = 15):
    """Resumen consolidado: goals abiertos + últimas sesiones + últimos intentos."""
    try:
        goals = _q("""
            SELECT id, status, priority, attempt_no,
                   LEFT(goal, 160) AS goal,
                   claimed_by, lease_until, updated_at
            FROM brain.goals
            WHERE project_id = %s
              AND status IN ('pending','in_progress','queued','running','blocked','escalated')
            ORDER BY priority DESC, updated_at DESC
            LIMIT %s
        """, (_PROJECT, limit))

        sessions = _q("""
            SELECT session_id, goal_id, outcome, effective_model,
                   tools_used, tokens_in, tokens_out, cost_estimate_usd,
                   latency_s, ended_at, LEFT(summary_md, 300) AS summary
            FROM brain.sessions
            WHERE project_id = %s AND runtime = 'worker'
            ORDER BY ended_at DESC NULLS LAST
            LIMIT %s
        """, (_PROJECT, limit))

        attempts = _q("""
            SELECT goal_id, attempt_no, actor, outcome, failure_class,
                   completed_at
            FROM brain.estimastruct_attempt_memory
            ORDER BY completed_at DESC NULLS LAST, id DESC
            LIMIT %s
        """, (limit,))

        return {
            "ok": True,
            "project": _PROJECT,
            "open_goals": goals,
            "recent_sessions": sessions,
            "recent_attempts": attempts,
            "counts": {
                "open_goals": len(goals),
                "sessions": len(sessions),
                "attempts": len(attempts),
            },
        }
    except Exception as e:
        return _err(e)


@router.get("/goals")
def worker_goals(limit: int = 30):
    """Goals estimastruct abiertos con contexto del worker (context->'estimastruct_worker')."""
    try:
        rows = _q("""
            SELECT id, status, priority, attempt_no, kind, source,
                   LEFT(goal, 240) AS goal,
                   context->'estimastruct_worker' AS last_run,
                   claimed_by, lease_until, updated_at
            FROM brain.goals
            WHERE project_id = %s
            ORDER BY updated_at DESC
            LIMIT %s
        """, (_PROJECT, limit))
        return {"ok": True, "goals": rows, "count": len(rows)}
    except Exception as e:
        return _err(e)


@router.get("/sessions")
def worker_sessions(limit: int = 25):
    """Últimas sesiones del worker (una por goal trabajado)."""
    try:
        rows = _q("""
            SELECT session_id, goal_id, outcome, effective_model,
                   tools_used, providers_tried, tokens_in, tokens_out,
                   cost_estimate_usd, latency_s, started_at, ended_at, status,
                   LEFT(objective, 200) AS objective,
                   LEFT(summary_md, 500) AS summary
            FROM brain.sessions
            WHERE project_id = %s AND runtime = 'worker'
            ORDER BY ended_at DESC NULLS LAST, started_at DESC
            LIMIT %s
        """, (_PROJECT, limit))
        return {"ok": True, "sessions": rows, "count": len(rows)}
    except Exception as e:
        return _err(e)


@router.get("/attempts")
def worker_attempts(limit: int = 25):
    """Memoria de intentos (outcome + failure_class) para ver la tasa de fallo."""
    try:
        rows = _q("""
            SELECT goal_id, attempt_no, actor, outcome, failure_class,
                   started_at, completed_at
            FROM brain.estimastruct_attempt_memory
            ORDER BY completed_at DESC NULLS LAST, id DESC
            LIMIT %s
        """, (limit,))
        # tasa de fallo simple
        total = len(rows)
        failed = sum(1 for r in rows if r.get("outcome") not in ("succeeded", "completed"))
        return {
            "ok": True, "attempts": rows, "count": total,
            "fail_rate": round(failed / total, 3) if total else None,
        }
    except Exception as e:
        return _err(e)
