"""
Publicar una obra de EstimaStruct al Portal (Supabase).
POST /presupuestos/{pid}/publish-supabase
Requiere SUPABASE_SECRET_KEY en el entorno del backend (no commitear).
"""
import os
import json
import urllib.request
import urllib.error
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.db import get_db
from backend.models import Presupuesto, Capitulo, ConfigPresupuesto, CronogramaOverride
from backend import cronograma as crono_engine

router = APIRouter(prefix="/presupuestos", tags=["portal"])

SUPABASE_URL = os.environ.get(
    "SUPABASE_URL", "https://humdvodaanyduqxojoxp.supabase.co"
).rstrip("/")
SUPABASE_SECRET = os.environ.get("SUPABASE_SECRET_KEY", "")


def _sb(method: str, path: str, body=None, prefer: str | None = None):
    url = f"{SUPABASE_URL}/rest/v1/{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("apikey", SUPABASE_SECRET)
    req.add_header("Authorization", f"Bearer {SUPABASE_SECRET}")
    req.add_header("Content-Type", "application/json")
    if prefer:
        req.add_header("Prefer", prefer)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            txt = r.read().decode("utf-8")
            return json.loads(txt) if txt else []
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8")[:400]
        raise HTTPException(502, f"Supabase {method} {path}: {e.code} {detail}")
    except urllib.error.URLError as e:
        raise HTTPException(502, f"Sin conexión a Supabase: {e.reason}")


@router.post("/{pid}/publish-supabase")
def publish_supabase(pid: str, db: Session = Depends(get_db)):
    if not SUPABASE_SECRET:
        raise HTTPException(
            400,
            "Falta SUPABASE_SECRET_KEY en el entorno del backend. "
            "Setealo (p.ej. en START_UNICA.ps1) y reinicia EstimaStruct.",
        )
    p = db.query(Presupuesto).get(pid)
    if not p:
        raise HTTPException(404, "Presupuesto no encontrado")

    cfg = db.query(ConfigPresupuesto).filter(
        ConfigPresupuesto.presupuesto_id == pid
    ).first()
    sc = float(cfg.sobrecosto) if cfg else 20.0

    caps = db.query(Capitulo).filter(Capitulo.presupuesto_id == pid).all()
    overrides = {r.partida_id: (max(1, int(r.n_esp or crono_engine.DEF_ESP)),
                                 max(1, int(r.n_ay or crono_engine.DEF_AY)))
                 for r in db.query(CronogramaOverride).filter(
                     CronogramaOverride.presupuesto_id == pid).all()}
    partidas = []          # filas para partida_valor (Supabase)
    crono_input = []       # filas para el motor de cronograma
    total = 0.0
    for cap in caps:
        for pa in cap.partidas:
            if float(pa.total or 0) <= 0:
                continue
            csi = (pa.clave_csi or "00").strip()
            partidas.append({
                "estimastruct_partida_id": pa.id,
                "csi": csi,
                "descripcion": pa.descripcion or "",
                "unidad": pa.unidad or "",
                "cantidad": float(pa.cantidad or 0),
                "total": round(float(pa.total or 0), 2),
                "costo_mo": round(float(pa.costo_mo or 0), 2),
                "costo_ma": round(float(pa.costo_ma or 0), 2),
                "division": csi[:2],
            })
            _ne, _na = overrides.get(pa.id, (crono_engine.DEF_ESP, crono_engine.DEF_AY))
            crono_input.append({
                "clave_csi": csi,
                "descripcion": pa.descripcion or "",
                "unidad": pa.unidad or "",
                "cantidad": float(pa.cantidad or 0),
                "capitulo_clave": (cap.clave or csi[:2]).strip(),
                "partida_id": pa.id,
                "n_esp": _ne,
                "n_ay": _na,
            })
            total += float(pa.total or 0)

    if not partidas:
        raise HTTPException(400, "La obra no tiene partidas con valor (total > 0)")

    # Cronograma: duraciones por tiempo unitario del catalogo V1.2 x cantidad
    try:
        crono_rows = crono_engine.construir_cronograma(crono_input)
    except Exception as e:  # catalogo ausente / corrupto -> no abortar la publicacion
        crono_rows = []
        crono_err = str(e)
    else:
        crono_err = None
    fecha_inicio_obra = min((c["fecha_inicio"] for c in crono_rows), default=None)

    # Upsert obra por estimastruct_id (preserva id, movimientos y primer_desembolso).
    # fecha_inicio NO va en el upsert: el admin la fija en el portal (ancla la
    # curva S) — solo se setea desde el cronograma si aún está vacía.
    obra_row = [{
        "estimastruct_id": p.id,
        "nombre": p.nombre,
        "cliente": p.cliente or "",
        "moneda": p.moneda or "HNL",
        "sobrecosto": sc,
        "total": round(total, 2),
    }]
    res = _sb(
        "POST", "obra?on_conflict=estimastruct_id", obra_row,
        prefer="resolution=merge-duplicates,return=representation",
    )
    if not res or "id" not in res[0]:
        raise HTTPException(502, "Supabase no devolvió el id de la obra")
    obra_id = res[0]["id"]
    if fecha_inicio_obra and not res[0].get("fecha_inicio"):
        _sb("PATCH", f"obra?id=eq.{obra_id}",
            {"fecha_inicio": fecha_inicio_obra}, prefer="return=minimal")

    # Refrescar partidas (borrar + insertar). Capturamos los id que asigna Supabase
    # para enlazar el cronograma por estimastruct_partida_id.
    _sb("DELETE", f"cronograma?obra_id=eq.{obra_id}", None)
    _sb("DELETE", f"partida_valor?obra_id=eq.{obra_id}", None)
    rows = [dict(obra_id=obra_id, **pp) for pp in partidas]
    id_por_epid = {}
    for i in range(0, len(rows), 200):
        ins = _sb("POST", "partida_valor", rows[i:i + 200],
                  prefer="return=representation")
        for r in (ins or []):
            id_por_epid[r["estimastruct_partida_id"]] = r["id"]

    # Insertar cronograma (1:1 con partida_valor via estimastruct_partida_id)
    crono_pub = 0
    if crono_rows:
        crows = []
        for c in crono_rows:
            pv_id = id_por_epid.get(c["partida_id"])
            if not pv_id:
                continue
            crows.append({
                "obra_id": obra_id,
                "partida_id": pv_id,
                "fecha_inicio": c["fecha_inicio"],
                "duracion_dias": int(c["duracion_dias"]),
                "orden": int(c["orden"]),
                "avance_pct": 0,
                "activa": False,
                "fase": c["fase"],
                "fuente": c.get("fuente", ""),
                "n_esp": int(c.get("n_esp", crono_engine.DEF_ESP)),
                "n_ay": int(c.get("n_ay", crono_engine.DEF_AY)),
                "jh_esp": round(float(c.get("jh_esp", 0)), 3),
                "jh_ay": round(float(c.get("jh_ay", 0)), 3),
            })
        for i in range(0, len(crows), 200):
            _sb("POST", "cronograma", crows[i:i + 200], prefer="return=minimal")
        crono_pub = len(crows)

    return {
        "ok": True,
        "obra_id": obra_id,
        "nombre": p.nombre,
        "partidas": len(rows),
        "cronograma": crono_pub,
        "fecha_inicio": fecha_inicio_obra,
        "cronograma_error": crono_err,
        "total": round(total, 2),
    }


@router.post("/{pid}/sync-precios-supabase")
def sync_precios_supabase(pid: str, db: Session = Depends(get_db)):
    """Sincroniza SOLO precios al portal: costo_ma/costo_mo/total/cantidad por
    partida + sobrecosto y total de la obra. NO toca cronograma, avance,
    fecha_inicio ni movimientos (a diferencia de publish, que resetea todo).
    Partidas nuevas se insertan; las eliminadas en EstimaStruct se reportan."""
    if not SUPABASE_SECRET:
        raise HTTPException(400, "Falta SUPABASE_SECRET_KEY en el entorno del backend.")
    p = db.query(Presupuesto).get(pid)
    if not p:
        raise HTTPException(404, "Presupuesto no encontrado")

    cfg = db.query(ConfigPresupuesto).filter(
        ConfigPresupuesto.presupuesto_id == pid
    ).first()
    sc = float(cfg.sobrecosto) if cfg else 20.0

    obras = _sb("GET", f"obra?estimastruct_id=eq.{p.id}&select=id")
    if not obras:
        raise HTTPException(404, "La obra no está publicada en el portal — usá Publicar primero.")
    obra_id = obras[0]["id"]

    partidas = []
    total = 0.0
    for cap in db.query(Capitulo).filter(Capitulo.presupuesto_id == pid).all():
        for pa in cap.partidas:
            if float(pa.total or 0) <= 0:
                continue
            csi = (pa.clave_csi or "00").strip()
            partidas.append({
                "estimastruct_partida_id": pa.id,
                "csi": csi,
                "descripcion": pa.descripcion or "",
                "unidad": pa.unidad or "",
                "cantidad": float(pa.cantidad or 0),
                "total": round(float(pa.total or 0), 2),
                "costo_mo": round(float(pa.costo_mo or 0), 2),
                "costo_ma": round(float(pa.costo_ma or 0), 2),
                "division": csi[:2],
            })
            total += float(pa.total or 0)
    if not partidas:
        raise HTTPException(400, "La obra no tiene partidas con valor (total > 0)")

    # Obra: solo sobrecosto + total (nombre/fechas/carpetas quedan como están)
    _sb("PATCH", f"obra?id=eq.{obra_id}",
        {"sobrecosto": sc, "total": round(total, 2)}, prefer="return=minimal")

    existentes = _sb(
        "GET",
        f"partida_valor?obra_id=eq.{obra_id}&select=estimastruct_partida_id",
    )
    est_portal = {r["estimastruct_partida_id"] for r in existentes
                  if r.get("estimastruct_partida_id")}
    est_local = {pp["estimastruct_partida_id"] for pp in partidas}

    actualizadas = 0
    nuevas = []
    for pp in partidas:
        if pp["estimastruct_partida_id"] in est_portal:
            _sb(
                "PATCH",
                f"partida_valor?obra_id=eq.{obra_id}"
                f"&estimastruct_partida_id=eq.{pp['estimastruct_partida_id']}",
                {k: pp[k] for k in
                 ("cantidad", "total", "costo_mo", "costo_ma", "descripcion", "unidad")},
                prefer="return=minimal",
            )
            actualizadas += 1
        else:
            nuevas.append(dict(obra_id=obra_id, **pp))
    for i in range(0, len(nuevas), 200):
        _sb("POST", "partida_valor", nuevas[i:i + 200], prefer="return=minimal")

    return {
        "ok": True,
        "obra_id": obra_id,
        "nombre": p.nombre,
        "sobrecosto": sc,
        "total": round(total, 2),
        "actualizadas": actualizadas,
        "nuevas": len(nuevas),
        "huerfanas_en_portal": len(est_portal - est_local),
    }
