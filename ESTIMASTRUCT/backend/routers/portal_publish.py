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
from backend.models import Presupuesto, Capitulo, ConfigPresupuesto, CronogramaOverride, CronogramaOrden, InsumoPartida
from backend import cronograma as crono_engine
from backend.routers.cronograma import _calcular as _crono_calcular, _orden_manual as _crono_orden

router = APIRouter(prefix="/presupuestos", tags=["portal"])

SUPABASE_URL = os.environ.get(
    "SUPABASE_URL", "https://gcicapuvgzzafeepbhfs.supabase.co"
).rstrip("/")
SUPABASE_SECRET = os.environ.get("SUPABASE_SECRET_KEY", "")
if not SUPABASE_SECRET:
    # [2026-10-04] Fuente unica de la key: D:\Secrets\Supabase Finance.txt (la misma que
    # lee START_UNICA.ps1). Asi el backend la tiene aunque lo arranque un agente
    # (estimastruct_backend_ensure) y rotar la key = editar 1 archivo + reiniciar.
    try:
        import re as _re
        _f = os.environ.get("SUPABASE_SECRET_FILE", r"D:\Secrets\Supabase Finance.txt")
        _m = _re.search(r"sb_secret_[A-Za-z0-9_\-]+", open(_f, encoding="utf-8").read())
        SUPABASE_SECRET = _m.group(0) if _m else ""
    except OSError:
        SUPABASE_SECRET = ""

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

    # Cronograma: MISMA ruta de calculo que el Gantt del front (routers/cronograma._calcular):
    # orden manual vigente, overrides n_esp/n_ay y fecha_fin. Catalogo activo (v1.3 por defecto).
    try:
        crono_rows = _crono_calcular(p, overrides, _crono_orden(db, pid))
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

    # [2026-10-02] Materiales por partida (para "Materiales semanales" del portal):
    # insumos MATERIAL con costo_unit YA reajustado (reajuste_materiales de la obra),
    # asi el portal y EstimaStruct dan los mismos montos. Tolerante: si la tabla
    # obra_material aun no existe en Supabase (005 sin aplicar) no aborta el publish.
    from backend.services.pricing import factor_materiales
    f_ma = factor_materiales(cfg)
    mat_rows, mat_err = [], None
    for cap in caps:
        for pa in cap.partidas:
            if pa.id not in id_por_epid:
                continue
            for ins in pa.insumos:
                if ins.tipo != "MATERIAL" or float(ins.cantidad or 0) <= 0:
                    continue
                mat_rows.append({
                    "obra_id": obra_id, "estimastruct_partida_id": pa.id,
                    "clave": ins.clave or f"SIN-{ins.id[:8]}", "descripcion": ins.descripcion or "",
                    "unidad": ins.unidad or "", "cantidad_unit": round(float(ins.cantidad or 0), 6),
                    "costo_unit": round(float(ins.costo_unit or 0) * f_ma, 4),
                })
    # dedupe (obra, partida, clave) — unique en obra_material
    _seen = {}
    for m in mat_rows:
        k = (m["estimastruct_partida_id"], m["clave"])
        if k in _seen:
            _seen[k]["cantidad_unit"] = round(_seen[k]["cantidad_unit"] + m["cantidad_unit"], 6)
        else:
            _seen[k] = m
    mat_rows = list(_seen.values())
    try:
        _sb("DELETE", f"obra_material?obra_id=eq.{obra_id}", None)
        for i in range(0, len(mat_rows), 500):
            _sb("POST", "obra_material", mat_rows[i:i + 500], prefer="return=minimal")
    except HTTPException as e:
        mat_err = str(e.detail)[:200]
        mat_rows = []

    # [2026-10-04] Espejo Gantt: dejar el snapshot de sync = lo recien publicado
    from backend.services import gantt_sync
    gsync = gantt_sync.safe_sync(db, pid, origin="estimastruct")

    return {
        "ok": True,
        "obra_id": obra_id,
        "nombre": p.nombre,
        "partidas": len(rows),
        "cronograma": crono_pub,
        "gantt_sync": gsync.get("accion"),
        "materiales": len(mat_rows),
        "materiales_error": mat_err,
        "fecha_inicio": fecha_inicio_obra,
        "cronograma_error": crono_err,
        "total": round(total, 2),
    }


@router.post("/{pid}/sync-media-supabase")
def sync_media_supabase(pid: str, db: Session = Depends(get_db)):
    """Dispara la sincronización de media (fotos/videos/planos/renders) de
    esta obra hacia su bucket Cloudflare R2 dedicado.

    Decisión David 2026-09-17: los binarios NUNCA los sube EstimaStruct ni
    toca credenciales de Cloudflare — projectmanager_bot es el único que
    sube al bucket. Este endpoint solo:
      1. Confirma que la obra está publicada en el portal (obra_id existe).
      2. Asegura el nombre convencional del bucket por-obra:
         `obra-{estimastruct_id}` con subcarpetas fotos/ videos/ planos/ renders/.
      3. Manda un mensaje async por el bus (agent_send) a projectmanager_bot
         pidiéndole que sincronice ese bucket ahora — pmbot notifica cuando
         termina, este endpoint no espera el resultado real de la subida.
    """
    if not SUPABASE_SECRET:
        raise HTTPException(400, "Falta SUPABASE_SECRET_KEY en el entorno del backend.")
    p = db.query(Presupuesto).get(pid)
    if not p:
        raise HTTPException(404, "Presupuesto no encontrado")

    obras = _sb("GET", f"obra?estimastruct_id=eq.{p.id}&select=id")
    if not obras:
        raise HTTPException(404, "La obra no está publicada en el portal — usá Publicar primero.")
    obra_id = obras[0]["id"]

    bucket_name = f"obra-{p.id}"

    # NOTA HONESTA: agent_send (bus MCP hacia projectmanager_bot) es una tool
    # de Hermes, no una librería que este proceso FastAPI pueda invocar por
    # su cuenta — el bus vive en Postgres brain-agentic, fuera de este
    # runtime. Este endpoint deja la solicitud lista (bucket esperado,
    # obra_id, subcarpetas) para que el agente que orquesta el click (o un
    # webhook futuro) dispare el agent_send real. No inventa una columna
    # Supabase que no existe — no escribe nada más en `obra` por ahora.

    return {
        "ok": True,
        "obra_id": obra_id,
        "nombre": p.nombre,
        "bucket": bucket_name,
        "subcarpetas": ["fotos", "videos", "planos", "renders"],
        "mensaje": "Solicitud registrada. projectmanager_bot sincroniza el bucket y notifica al terminar.",
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
