"""
Espejo bidireccional del Gantt  EstimaStruct (Postgres)  <->  Portal (Supabase `cronograma`).

Canon (David 2026-10-04, P0): el Gantt del portal es un REFLEJO del de EstimaStruct.
Si se mueve una actividad (orden) o se cambia su personal (n_esp/n_ay) en cualquiera
de los dos lados, el otro lado queda igual.

Estado del Gantt que se sincroniza = lo que EstimaStruct sabe representar:
    * orden relativo de las actividades   (cronograma_orden en Postgres)
    * n_esp / n_ay por actividad          (cronograma_override en Postgres)
Fechas y duraciones NO se sincronizan como dato: siempre las recalcula el motor
(backend/cronograma.py) y se EMPUJAN al portal. Así ambos lados dan las mismas fechas.

Quién ganó el último cambio — sin DDL en Supabase:
    snapshot = último estado empujado al portal (D:/EstimaStruct/data/gantt_sync_state.json)
    portal != snapshot  -> el cambio vino del portal  -> PULL a Postgres + PUSH canónico
    postgres != snapshot -> el cambio vino de EstimaStruct -> PUSH
avance_pct y activa son del portal (ejecución de obra): el push NUNCA los toca.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from sqlalchemy.orm import joinedload

from backend import cronograma as engine

_STATE_FILE = Path(os.getenv(
    "ESTIMASTRUCT_GANTT_SYNC_STATE",
    os.path.join(os.path.dirname(os.getenv("ESTIMA_DB_PATH", r"D:\EstimaStruct\data\estimacion.db")),
                 "gantt_sync_state.json")))
_LOCK = threading.RLock()
POLL_SECONDS = int(os.getenv("ESTIMASTRUCT_GANTT_POLL_S", "15"))


# ── snapshot ────────────────────────────────────────────────────────────────
def _load_state() -> dict:
    try:
        return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_snapshot(pid: str, snap: dict) -> None:
    st = _load_state()
    st[pid] = snap
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = _STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, _STATE_FILE)


def _snap_of(order: list, pers: dict) -> dict:
    return {"order": list(order), "pers": {k: list(v) for k, v in pers.items()}}


def _same(a: dict | None, b: dict | None) -> bool:
    if not a or not b:
        return False
    if a["order"] != b["order"]:
        return False
    keys = set(a["order"])
    return all(list(a["pers"].get(k, [3, 3])) == list(b["pers"].get(k, [3, 3])) for k in keys)


# ── lados ───────────────────────────────────────────────────────────────────
def _sb():
    from backend.routers import portal_publish as pp
    return pp


def _portal(pid: str):
    """(obra_id, {epid: pv_id}, snap_portal) o None si la obra no está publicada."""
    pp = _sb()
    obras = pp._sb("GET", f"obra?estimastruct_id=eq.{pid}&select=id")
    if not obras:
        return None
    obra_id = obras[0]["id"]
    pvs = pp._sb("GET", f"partida_valor?obra_id=eq.{obra_id}&select=id,estimastruct_partida_id")
    pv_by_epid = {r["estimastruct_partida_id"]: r["id"] for r in pvs if r.get("estimastruct_partida_id")}
    epid_by_pv = {v: k for k, v in pv_by_epid.items()}
    cron = pp._sb("GET", f"cronograma?obra_id=eq.{obra_id}&select=partida_id,orden,n_esp,n_ay")
    rows = [c for c in cron if c["partida_id"] in epid_by_pv]
    rows.sort(key=lambda c: (c.get("orden") if c.get("orden") is not None else 10**6))
    order = [epid_by_pv[c["partida_id"]] for c in rows]
    pers = {epid_by_pv[c["partida_id"]]: [int(c.get("n_esp") or engine.DEF_ESP), int(c.get("n_ay") or engine.DEF_AY)]
            for c in rows}
    return obra_id, pv_by_epid, _snap_of(order, pers)


def _filas(db, pid: str, manual: bool = True):
    from backend.models import Presupuesto, Capitulo
    from backend.routers.cronograma import _calcular, _overrides, _orden_manual
    p = db.query(Presupuesto).options(
        joinedload(Presupuesto.capitulos).joinedload(Capitulo.partidas)
    ).filter(Presupuesto.id == pid).first()
    if not p:
        return None
    return _calcular(p, _overrides(db, pid), _orden_manual(db, pid) if manual else {})


def _pg_snap(filas, published: set) -> dict:
    order = [f["partida_id"] for f in filas if f["partida_id"] in published]
    pers = {f["partida_id"]: [int(f.get("n_esp", engine.DEF_ESP)), int(f.get("n_ay", engine.DEF_AY))]
            for f in filas if f["partida_id"] in published}
    return _snap_of(order, pers)


def _push(pid: str, obra_id: str, pv_by_epid: dict, filas) -> int:
    pp = _sb()
    rows = []
    for f in filas:
        pv = pv_by_epid.get(f["partida_id"])
        if not pv:
            continue
        rows.append({
            "obra_id": obra_id, "partida_id": pv,
            "orden": int(f["orden"]), "fecha_inicio": f["fecha_inicio"],
            "duracion_dias": int(f["duracion_dias"]), "fase": f["fase"],
            "fuente": f.get("fuente", ""),
            "n_esp": int(f.get("n_esp", engine.DEF_ESP)), "n_ay": int(f.get("n_ay", engine.DEF_AY)),
            "jh_esp": round(float(f.get("jh_esp", 0)), 3), "jh_ay": round(float(f.get("jh_ay", 0)), 3),
        })
    # orden relativo: renumerar 0..n-1 solo entre publicadas (igual que el portal)
    for i, r in enumerate(rows):
        r["orden"] = i
    # Supabase `cronograma` NO tiene UNIQUE(partida_id) -> no hay upsert. PATCH fila por
    # fila (solo campos del plan; avance_pct/activa del portal NUNCA se tocan) y POST de
    # las que falten. Sin DDL en Supabase.
    fields = ("orden", "fecha_inicio", "duracion_dias", "fase", "fuente", "n_esp", "n_ay", "jh_esp", "jh_ay")
    cur = {c["partida_id"]: c for c in pp._sb(
        "GET", f"cronograma?obra_id=eq.{obra_id}&select=partida_id,{','.join(fields)}")}

    def _eq(a, b):
        if isinstance(b, (int, float)) and not isinstance(b, bool):
            try:
                return abs(float(a or 0) - float(b)) < 1e-3
            except (TypeError, ValueError):
                return False
        return str(a if a is not None else "") == str(b if b is not None else "")

    patches, nuevas = [], []
    for r in rows:
        c = cur.get(r["partida_id"])
        if c is None:
            nuevas.append(r)
            continue
        body = {k: r[k] for k in fields if not _eq(c.get(k), r[k])}
        if body:
            patches.append((r["partida_id"], body))

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(lambda pb: pp._sb("PATCH", f"cronograma?obra_id=eq.{obra_id}&partida_id=eq.{pb[0]}",
                                      pb[1], prefer="return=minimal"), patches))
    if nuevas:
        pp._sb("POST", "cronograma", nuevas, prefer="return=minimal")
    return len(patches) + len(nuevas)


def _pull(db, pid: str, filas, portal_snap: dict) -> None:
    """Aplica orden + personal del portal a Postgres (cronograma_orden / cronograma_override).
    Si el orden del portal == orden AUTOMATICO (fase/CSI), no se escribe orden manual:
    en el motor, orden manual = cadena secuencial, y eso alargaria la obra sin motivo."""
    from backend.models import CronogramaOrden, CronogramaOverride
    ids = list(portal_snap["order"]) + [f["partida_id"] for f in filas if f["partida_id"] not in set(portal_snap["order"])]
    db.query(CronogramaOrden).filter(CronogramaOrden.presupuesto_id == pid).delete()
    auto = _filas(db, pid, manual=False)   # ya sin orden manual
    auto_ids = [f["partida_id"] for f in auto if f["partida_id"] in set(portal_snap["order"])]
    if auto_ids != list(portal_snap["order"]):
        for i, epid in enumerate(ids):
            db.add(CronogramaOrden(presupuesto_id=pid, partida_id=epid, orden=i))
    for epid, (ne, na) in portal_snap["pers"].items():
        ne, na = max(1, min(12, int(ne))), max(1, min(12, int(na)))
        ov = db.query(CronogramaOverride).filter(CronogramaOverride.partida_id == epid).first()
        if ne == engine.DEF_ESP and na == engine.DEF_AY:
            if ov:
                db.delete(ov)
        elif ov:
            ov.n_esp, ov.n_ay = ne, na
        else:
            db.add(CronogramaOverride(presupuesto_id=pid, partida_id=epid, n_esp=ne, n_ay=na))
    db.commit()


# ── API pública ─────────────────────────────────────────────────────────────
def enabled() -> bool:
    return bool(_sb().SUPABASE_SECRET)


def sync(db, pid: str, origin: str = "auto") -> dict:
    """Reconciliar un presupuesto. origin='estimastruct' fuerza PUSH (cambio local recién hecho)."""
    if not enabled():
        return {"ok": False, "accion": "deshabilitado", "error": "sin SUPABASE_SECRET_KEY"}
    with _LOCK:
        portal = _portal(pid)
        if portal is None:
            return {"ok": True, "accion": "no_publicada"}
        obra_id, pv_by_epid, sb_snap = portal
        filas = _filas(db, pid)
        if not filas:
            return {"ok": True, "accion": "sin_actividades"}
        published = set(pv_by_epid)
        pg_snap = _pg_snap(filas, published)
        snap = _load_state().get(pid)

        accion = "igual"
        if origin == "estimastruct":
            accion = "push"
        elif snap is None:
            accion = "igual" if _same(sb_snap, pg_snap) else "push"
        elif not _same(sb_snap, snap):
            accion = "pull"
        elif not _same(pg_snap, snap):
            accion = "push"
        elif not _same(sb_snap, pg_snap):
            accion = "push"

        n = 0
        if accion == "pull":
            _pull(db, pid, filas, sb_snap)
            filas = _filas(db, pid)
            pg_snap = _pg_snap(filas, published)
        if accion in ("pull", "push"):
            n = _push(pid, obra_id, pv_by_epid, filas)
        _save_snapshot(pid, pg_snap)
        return {"ok": True, "accion": accion, "obra_id": obra_id, "filas_portal": n}


def safe_sync(db, pid: str, origin: str = "auto") -> dict:
    try:
        return sync(db, pid, origin)
    except Exception as e:  # el Gantt local nunca se cae por el portal
        try:
            db.rollback()
        except Exception:
            pass
        return {"ok": False, "accion": "error", "error": str(getattr(e, "detail", e))[:300]}


_poller_started = False


def start_poller() -> None:
    """Hilo daemon: cada POLL_SECONDS trae cambios del portal a Postgres (obras publicadas)."""
    global _poller_started
    if _poller_started or not enabled() or POLL_SECONDS <= 0:
        return
    _poller_started = True

    def _loop():
        from backend.db import SessionLocal
        from backend.models import Presupuesto
        while True:
            time.sleep(POLL_SECONDS)
            try:
                obras = _sb()._sb("GET", "obra?select=estimastruct_id&estimastruct_id=not.is.null")
                db = SessionLocal()
                try:
                    for o in obras:
                        pid = o.get("estimastruct_id")
                        if pid and db.get(Presupuesto, pid) is not None:
                            r = safe_sync(db, pid)
                            if r.get("accion") == "pull":
                                print(f"[gantt_sync] pull portal->postgres {pid}: {r}", flush=True)
                finally:
                    db.close()
            except Exception as e:
                print(f"[gantt_sync] poll error: {e}", flush=True)

    threading.Thread(target=_loop, name="gantt_sync_poller", daemon=True).start()
