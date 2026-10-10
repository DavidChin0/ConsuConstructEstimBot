"""
Cronograma / Gantt de una obra.
  GET /presupuestos/{pid}/cronograma          -> JSON para el front (Gantt)
  GET /presupuestos/{pid}/export-cronograma   -> XLSX (tabla + grilla de semanas)
  GET /presupuestos/{pid}/export-materiales-semanales -> XLSX materiales por semana
      (orden VIGENTE del Gantt: manual si lo hay, si no automatico)

Duraciones por tiempo unitario del catalogo de fichas activo, v1.3 por defecto (cronograma.py).
"""
import io
import os
import sys
from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from backend.db import get_db
from backend.models import Presupuesto, Capitulo, Partida, CronogramaOverride, CronogramaOrden
from backend import cronograma as engine
from backend.routers.export import safe_fname
from backend.services.pricing import factor_materiales
from backend.services import gantt_sync

router = APIRouter(tags=["cronograma"])

CUADRILLAS_MAX = 12   # tope de cuadrillas en paralelo por actividad

# Paleta ConsuConstruct (espejo de export.py)
HDR_FILL = "FFF5C518"
HDR_TEXT = "FF1A1A1A"
DIV_FILL = "FF3A3A3A"
DIV_TEXT = "FFF5C518"
TOT_TEXT = "FFE94560"

# Color por fase (para el grid del Gantt en Excel y referencia del front)
FASE_FILL = {
    "1.": "FF9AA0A6", "2.": "FF9AA0A6", "3.": "FFB0B0B0",
    "4.": "FF378ADD", "5.": "FF1D9E75", "6.": "FFEF6C5A",
    "7.": "FF9C6ADE", "8.": "FF5DCAA5", "9.": "FF5DA8E8", "10": "FFB0B0B0",
}


def _fase_color(fase: str) -> str:
    return FASE_FILL.get((fase or "")[:2], "FF378ADD")


def _overrides(db: Session, pid: str) -> dict:
    """{partida_id: (n_esp, n_ay)} para las partidas que el usuario ajusto."""
    rows = db.query(CronogramaOverride).filter(
        CronogramaOverride.presupuesto_id == pid).all()
    return {r.partida_id: (max(1, int(r.n_esp or engine.DEF_ESP)),
                           max(1, int(r.n_ay or engine.DEF_AY))) for r in rows}


def _partidas_obra(p: Presupuesto, overrides: dict):
    """crono_input para el motor: partidas con cantidad > 0 (+ n_esp/n_ay)."""
    crono_input = []
    for cap in sorted(p.capitulos, key=lambda c: (c.orden if c.orden is not None else 999)):
        for pa in sorted(cap.partidas, key=lambda x: x.orden or 0):
            if float(pa.cantidad or 0) <= 0:
                continue
            csi = (pa.clave_csi or "00").strip()
            ne, na = overrides.get(pa.id, (engine.DEF_ESP, engine.DEF_AY))
            crono_input.append({
                "clave_csi": csi,
                "descripcion": pa.descripcion or "",
                "unidad": pa.unidad or "",
                "cantidad": float(pa.cantidad or 0),
                "capitulo_clave": (cap.clave or csi[:2]).strip(),
                "partida_id": pa.id,
                "n_esp": ne,
                "n_ay": na,
            })
    return crono_input


def _orden_manual(db: Session, pid: str) -> dict:
    """{partida_id: orden} si el usuario reordeno el Gantt; {} = orden automatico."""
    rows = db.query(CronogramaOrden).filter(CronogramaOrden.presupuesto_id == pid).all()
    return {r.partida_id: int(r.orden) for r in rows}


def _cfg_cronograma(p: Presupuesto):
    """(fecha_arranque, serie) por obra desde config_presupuesto. None/False = comportamiento actual."""
    c = getattr(p, "config", None)
    fa = getattr(c, "cronograma_fecha_arranque", None) if c else None
    modo = (getattr(c, "cronograma_modo", None) or "paralelo") if c else "paralelo"
    return fa, modo == "serie"


def _calcular(p: Presupuesto, overrides: dict, orden_manual: dict | None = None):
    crono_input = _partidas_obra(p, overrides)
    if not crono_input:
        raise HTTPException(400, "La obra no tiene partidas con cantidad > 0")
    fa, serie = _cfg_cronograma(p)
    filas = engine.construir_cronograma(crono_input, orden_manual=orden_manual,
                                        fecha_arranque=fa, serie=serie)
    # fin (dia laboral) por actividad
    for f in filas:
        ini = date.fromisoformat(f["fecha_inicio"])
        f["fecha_fin"] = engine._suma_dias_laborales(ini, max(0, f["duracion_dias"] - 1)).isoformat()
    return filas


@router.get("/presupuestos/{pid}/cronograma")
def get_cronograma(pid: str, db: Session = Depends(get_db), sync: bool = True):
    # [2026-10-04] Espejo portal: al abrir/refrescar el Gantt, traer primero los cambios
    # que se hayan hecho en el Gantt del portal (Supabase). Tolerante: si el portal no
    # responde, el Gantt local se sirve igual y se reporta en "portal_sync".
    psync = gantt_sync.safe_sync(db, pid) if sync else {"accion": "omitido"}
    p = db.query(Presupuesto).options(
        joinedload(Presupuesto.capitulos).joinedload(Capitulo.partidas)
    ).filter(Presupuesto.id == pid).first()
    if not p:
        raise HTTPException(404, "Presupuesto no encontrado")

    filas = _calcular(p, _overrides(db, pid), _orden_manual(db, pid))
    inicio = min(f["fecha_inicio"] for f in filas)
    fin = max(f["fecha_fin"] for f in filas)
    d0 = date.fromisoformat(inicio)
    dfin = date.fromisoformat(fin)
    dias_cal = (dfin - d0).days + 1

    # Días laborables: lunes-viernes completos, sábado medio día, domingo libre.
    dias_lab = 0.0
    d = d0
    while d <= dfin:
        wd = d.weekday()
        if wd <= 4:
            dias_lab += 1.0
        elif wd == 5:
            dias_lab += 0.5
        d += timedelta(days=1)

    fases_orden = []
    for f in filas:
        if f["fase"] not in fases_orden:
            fases_orden.append(f["fase"])

    acts = []
    for f in filas:
        ini = date.fromisoformat(f["fecha_inicio"])
        fn = date.fromisoformat(f["fecha_fin"])
        acts.append({
            "orden": f["orden"],
            "csi": f["clave_csi"],
            "descripcion": f["descripcion"],
            "unidad": f["unidad"],
            "cantidad": f["cantidad"],
            "fase": f["fase"],
            "fase_color": "#" + _fase_color(f["fase"])[2:],
            "fecha_inicio": f["fecha_inicio"],
            "fecha_fin": f["fecha_fin"],
            "duracion_dias": f["duracion_dias"],
            "offset_dias": (ini - d0).days,           # para posicionar la barra (calendario)
            "span_dias": (fn - ini).days + 1,         # ancho de la barra (calendario)
            "fuente": f["fuente"],
            "jh_esp": f.get("jh_esp", 0),
            "jh_ay": f.get("jh_ay", 0),
            "n_esp": f.get("n_esp", engine.DEF_ESP),
            "n_ay": f.get("n_ay", engine.DEF_AY),
            "partida_id": f.get("partida_id"),
        })

    return {
        "obra_id": p.id,
        "nombre": p.nombre,
        "fecha_inicio": inicio,
        "fecha_fin": fin,
        "dias_calendario": dias_cal,
        "dias_laborables": dias_lab,   # L-V completos + sábado ½
        "semanas": (dias_cal + 6) // 7,
        "meses": round(dias_cal / 30.44, 1),
        "fases": fases_orden,
        "actividades": acts,
        "orden_manual": bool(_orden_manual(db, pid)),
        "portal_sync": {k: psync.get(k) for k in ("accion", "error") if psync.get(k)},
    }


def _dias_actividad(f: dict) -> list:
    """Dias laborales (L-S) que ocupa la actividad: inicio + duracion_dias-1 saltando domingos."""
    ini = date.fromisoformat(f["fecha_inicio"])
    dias = [ini]
    for k in range(1, max(1, int(f["duracion_dias"]))):
        dias.append(engine._suma_dias_laborales(ini, k))
    return dias


def _materiales_semana(p: Presupuesto, filas: list) -> dict:
    """Cantidad de MATERIALES por semana, repartida uniforme en los dias de cada actividad.

    Cantidad total de un insumo = rendimiento (insumo_partida.cantidad) x cantidad de la
    partida — misma formula que /export-insumos ("Cantidad requerida"). Semana 0-based
    desde el inicio de obra, igual que la grilla S1..Sn del XLSX de cronograma."""
    d0 = date.fromisoformat(min(f["fecha_inicio"] for f in filas))
    dfin = max(date.fromisoformat(f["fecha_fin"]) for f in filas)
    n_sem = ((dfin - d0).days // 7) + 1
    partidas = {pa.id: pa for cap in p.capitulos for pa in cap.partidas}
    items: dict = {}
    for f in filas:
        pa = partidas.get(f.get("partida_id"))
        if not pa:
            continue
        dias = _dias_actividad(f)
        por_sem: dict = {}
        for d in dias:
            w = (d - d0).days // 7
            por_sem[w] = por_sem.get(w, 0) + 1
        for ins in pa.insumos:
            if ins.tipo != "MATERIAL":
                continue
            total = float(ins.cantidad or 0) * float(pa.cantidad or 0)
            if total <= 0:
                continue
            key = (ins.clave or "", ins.descripcion or "", ins.unidad or "")
            it = items.setdefault(key, {"clave": key[0], "descripcion": key[1], "unidad": key[2],
                                        "total": 0.0, "semanas": [0.0] * n_sem, "actividades": [[] for _ in range(n_sem)]})
            it["total"] += total
            for w, nd in por_sem.items():
                it["semanas"][w] += total * nd / len(dias)
                if f["clave_csi"] not in it["actividades"][w]:
                    it["actividades"][w].append(f["clave_csi"])
    lista = sorted(items.values(), key=lambda x: (x["clave"].lower(), x["descripcion"].lower()))
    for it in lista:
        it["total"] = round(it["total"], 4)
        it["semanas"] = [round(v, 4) for v in it["semanas"]]
    return {"fecha_inicio": d0.isoformat(), "semanas": n_sem, "materiales": lista}


@router.get("/presupuestos/{pid}/cronograma/materiales")
def get_materiales_semana(pid: str, db: Session = Depends(get_db)):
    p = db.query(Presupuesto).options(
        joinedload(Presupuesto.capitulos).joinedload(Capitulo.partidas).joinedload(Partida.insumos)
    ).filter(Presupuesto.id == pid).first()
    if not p:
        raise HTTPException(404, "Presupuesto no encontrado")
    filas = _calcular(p, _overrides(db, pid), _orden_manual(db, pid))
    return _materiales_semana(p, filas)


class MoverIn(BaseModel):
    partida_id: str
    nueva_posicion: int   # 0-based en la lista actual del Gantt


@router.post("/presupuestos/{pid}/cronograma/mover")
def mover_actividad(pid: str, body: MoverIn, db: Session = Depends(get_db)):
    """Mueve una actividad a nueva_posicion; persiste el orden completo y
    devuelve el cronograma recalculado (fechas en cadena segun el nuevo orden)."""
    p = db.query(Presupuesto).options(
        joinedload(Presupuesto.capitulos).joinedload(Capitulo.partidas)
    ).filter(Presupuesto.id == pid).first()
    if not p:
        raise HTTPException(404, "Presupuesto no encontrado")
    filas = _calcular(p, _overrides(db, pid), _orden_manual(db, pid))
    ids = [f["partida_id"] for f in filas]
    if body.partida_id not in ids:
        raise HTTPException(404, "Partida no esta en el cronograma (cantidad > 0)")
    ids.remove(body.partida_id)
    pos = max(0, min(len(ids), int(body.nueva_posicion)))
    ids.insert(pos, body.partida_id)
    db.query(CronogramaOrden).filter(CronogramaOrden.presupuesto_id == pid).delete()
    for i, part_id in enumerate(ids):
        db.add(CronogramaOrden(presupuesto_id=pid, partida_id=part_id, orden=i))
    db.commit()
    gantt_sync.safe_sync(db, pid, origin="estimastruct")   # espejo -> portal
    return get_cronograma(pid, db, sync=False)


@router.post("/presupuestos/{pid}/cronograma/reset-orden")
def reset_orden(pid: str, db: Session = Depends(get_db)):
    """Vuelve al orden automatico por fase/CSI."""
    n = db.query(CronogramaOrden).filter(CronogramaOrden.presupuesto_id == pid).delete()
    db.commit()
    ps = gantt_sync.safe_sync(db, pid, origin="estimastruct")   # espejo -> portal
    return {"ok": True, "filas_borradas": n, "portal_sync": ps.get("accion")}


class PersonalIn(BaseModel):
    partida_id: str
    n_esp: int
    n_ay: int


@router.post("/presupuestos/{pid}/cronograma/personal")
def set_personal(pid: str, body: PersonalIn, db: Session = Depends(get_db)):
    """Ajusta especialistas + ayudantes de una actividad. Default (3,3) elimina el override."""
    p = db.query(Presupuesto).filter(Presupuesto.id == pid).first()
    if not p:
        raise HTTPException(404, "Presupuesto no encontrado")
    ne = max(1, min(CUADRILLAS_MAX, int(body.n_esp or engine.DEF_ESP)))
    na = max(1, min(CUADRILLAS_MAX, int(body.n_ay or engine.DEF_AY)))
    ov = db.query(CronogramaOverride).filter(
        CronogramaOverride.partida_id == body.partida_id).first()
    if ne == engine.DEF_ESP and na == engine.DEF_AY:
        if ov:
            db.delete(ov)
    elif ov:
        ov.n_esp = ne
        ov.n_ay = na
    else:
        db.add(CronogramaOverride(presupuesto_id=pid, partida_id=body.partida_id,
                                  n_esp=ne, n_ay=na))
    db.commit()
    ps = gantt_sync.safe_sync(db, pid, origin="estimastruct")   # espejo -> portal
    return {"ok": True, "partida_id": body.partida_id, "n_esp": ne, "n_ay": na,
            "portal_sync": ps.get("accion")}


@router.get("/presupuestos/{pid}/export-cronograma")
def export_cronograma(pid: str, db: Session = Depends(get_db)):
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
    except ImportError:
        raise HTTPException(500, "openpyxl no disponible")

    p = db.query(Presupuesto).options(
        joinedload(Presupuesto.capitulos).joinedload(Capitulo.partidas).joinedload(Partida.insumos)
    ).filter(Presupuesto.id == pid).first()
    if not p:
        raise HTTPException(404, "Presupuesto no encontrado")

    filas = _calcular(p, _overrides(db, pid), _orden_manual(db, pid))
    inicio = min(f["fecha_inicio"] for f in filas)
    fin = max(f["fecha_fin"] for f in filas)
    d0 = date.fromisoformat(inicio)
    dfin = date.fromisoformat(fin)
    n_sem = ((dfin - d0).days // 7) + 1

    wb = Workbook()
    ws = wb.active
    ws.title = "cronograma"

    thin = Side(style="thin", color="CCCCCC")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    TBL = ["#", "CSI", "Descripción", "Unidad", "Cantidad", "Fase",
           "Inicio", "Días", "Esp", "Ay", "Fin", "Fuente"]
    ncol_tbl = len(TBL)

    # Título
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncol_tbl + n_sem)
    t = ws.cell(row=1, column=1, value=f"{p.nombre} — Cronograma (Gantt)")
    t.font = Font(bold=True, size=13, color=HDR_TEXT)
    t.fill = PatternFill("solid", fgColor=HDR_FILL)
    t.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 22

    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=ncol_tbl + n_sem)
    sub = ws.cell(row=2, column=1, value=(
        f"Inicio {inicio}  |  Fin {fin}  |  {n_sem} semanas  |  "
        f"{len(filas)} actividades  |  Duraciones por tiempo unitario catálogo {engine.CATALOGO_VERSION}"))
    sub.font = Font(size=10, italic=True, color="666666")
    sub.alignment = Alignment(horizontal="center")

    # Headers tabla + semanas
    hr = 4
    for ci, txt in enumerate(TBL, 1):
        c = ws.cell(row=hr, column=ci, value=txt)
        c.font = Font(bold=True, color=HDR_TEXT, size=10)
        c.fill = PatternFill("solid", fgColor=HDR_FILL)
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = border
    for w in range(n_sem):
        c = ws.cell(row=hr, column=ncol_tbl + 1 + w, value=f"S{w + 1}")
        c.font = Font(bold=True, color=HDR_TEXT, size=9)
        c.fill = PatternFill("solid", fgColor=HDR_FILL)
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = border
    ws.row_dimensions[hr].height = 24

    row = hr + 1
    fase_actual = None
    for f in filas:
        if f["fase"] != fase_actual:
            fase_actual = f["fase"]
            ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=ncol_tbl + n_sem)
            hc = ws.cell(row=row, column=1, value=fase_actual)
            hc.font = Font(bold=True, color=DIV_TEXT, size=11)
            hc.fill = PatternFill("solid", fgColor=DIV_FILL)
            hc.alignment = Alignment(horizontal="left", indent=1)
            row += 1

        ini = date.fromisoformat(f["fecha_inicio"])
        fn = date.fromisoformat(f["fecha_fin"])
        vals = [f["orden"] + 1, f["clave_csi"], f["descripcion"], f["unidad"],
                f["cantidad"], f["fase"], f["fecha_inicio"], f["duracion_dias"],
                f.get("n_esp", engine.DEF_ESP), f.get("n_ay", engine.DEF_AY),
                f["fecha_fin"], f["fuente"]]
        for ci, v in enumerate(vals, 1):
            c = ws.cell(row=row, column=ci, value=v)
            c.border = border
            c.font = Font(size=9)
            if ci in (5, 8, 9, 10):
                c.alignment = Alignment(horizontal="right")
                c.number_format = '#,##0.00' if ci == 5 else '0'
        # barra de la fase en la grilla de semanas
        wfill = PatternFill("solid", fgColor=_fase_color(f["fase"]))
        sem_ini = (ini - d0).days // 7
        sem_fin = (fn - d0).days // 7
        for w in range(n_sem):
            cell = ws.cell(row=row, column=ncol_tbl + 1 + w)
            cell.border = border
            if sem_ini <= w <= sem_fin:
                cell.fill = wfill
        row += 1

    widths = [5, 14, 46, 8, 10, 30, 11, 6, 5, 5, 11, 9]
    for ci, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(ci)].width = w
    for w in range(n_sem):
        ws.column_dimensions[get_column_letter(ncol_tbl + 1 + w)].width = 3.2
    ws.freeze_panes = f"{get_column_letter(ncol_tbl + 1)}{hr + 1}"

    # Hoja 2: materiales por semana (misma formula que /export-insumos)
    mat = _materiales_semana(p, filas)
    wm = wb.create_sheet("materiales_semana")
    MH = ["Clave", "Descripción", "Unidad", "Total obra"]
    for ci, txt in enumerate(MH + [f"S{w + 1}" for w in range(mat["semanas"])], 1):
        c = wm.cell(row=1, column=ci, value=txt)
        c.font = Font(bold=True, color=HDR_TEXT, size=10)
        c.fill = PatternFill("solid", fgColor=HDR_FILL)
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = border
    for ri, it in enumerate(mat["materiales"], 2):
        for ci, v in enumerate([it["clave"], it["descripcion"], it["unidad"], it["total"]] + it["semanas"], 1):
            c = wm.cell(row=ri, column=ci, value=v)
            c.border = border
            c.font = Font(size=9)
            if ci >= 4:
                c.alignment = Alignment(horizontal="right")
                c.number_format = '#,##0.00;;'
    for ci, w in enumerate([16, 46, 9, 12], 1):
        wm.column_dimensions[get_column_letter(ci)].width = w
    for w in range(mat["semanas"]):
        wm.column_dimensions[get_column_letter(len(MH) + 1 + w)].width = 8
    wm.freeze_panes = "E2"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    nombre = safe_fname(p.nombre)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="Estimastruct_Cronograma_{nombre}.xlsx"'},
    )



# ─────────────────────────────────────────────────────────────────────────────
# MATERIALES POR SEMANA — segun el orden VIGENTE del Gantt
# ─────────────────────────────────────────────────────────────────────────────
def _dias_laborales_actividad(fecha_inicio: str, duracion: int) -> list:
    """Los N dias laborables (lun-sab) de la actividad, igual que el motor."""
    d = date.fromisoformat(fecha_inicio)
    out = []
    while len(out) < max(1, int(duracion)):
        if d.weekday() != 6:
            out.append(d)
        d += timedelta(days=1)
    return out


def materiales_semanales(p: Presupuesto, filas: list, tipos=("MATERIAL",)) -> list:
    """Una fila por (semana, actividad, insumo). Reparto proporcional a los
    dias laborables de la actividad que caen en cada semana (lunes-domingo).
    cantidad = insumo.cantidad x partida.cantidad x dias_semana / duracion.
    costo    = cantidad x costo_unit (mercado) x reajuste_materiales (solo MATERIAL).
    tipos: ("MATERIAL",) por default; ("MANO_OBRA",) para gasto de mano de obra."""
    f_ma = factor_materiales(p.config)
    partidas = {pa.id: pa for cap in p.capitulos for pa in cap.partidas}
    out = []
    for f in filas:   # filas ya vienen en el orden vigente del Gantt
        pa = partidas.get(f.get("partida_id"))
        if not pa:
            continue
        mats = [i for i in (pa.insumos or []) if i.tipo in tipos and float(i.cantidad or 0) > 0]
        if not mats:
            continue
        dur = max(1, int(f["duracion_dias"]))
        semanas = {}
        for d in _dias_laborales_actividad(f["fecha_inicio"], dur):
            lunes = d - timedelta(days=d.weekday())
            semanas[lunes] = semanas.get(lunes, 0) + 1
        cant_pa = float(pa.cantidad or 0)
        for lunes in sorted(semanas):
            frac = semanas[lunes] / dur
            for i in sorted(mats, key=lambda x: x.orden or 0):
                q = float(i.cantidad or 0) * cant_pa * frac
                cu = float(i.costo_unit or 0) * (f_ma if i.tipo == "MATERIAL" else 1.0)
                out.append({
                    "semana_inicio": lunes, "semana_fin": lunes + timedelta(days=6),
                    "orden": f["orden"], "csi": f["clave_csi"], "actividad": f["descripcion"],
                    "fase": f["fase"], "act_inicio": f["fecha_inicio"], "act_fin": f["fecha_fin"],
                    "dias_semana": semanas[lunes], "duracion": dur, "tipo": i.tipo,
                    "clave": i.clave or "", "material": i.descripcion or "", "unidad": i.unidad or "",
                    "cantidad": round(q, 4), "costo_unit": round(cu, 4), "costo": round(q * cu, 2),
                })
    out.sort(key=lambda r: (r["semana_inicio"], r["orden"]))
    return out


def _cargar_con_insumos(pid: str, db: Session) -> Presupuesto:
    p = db.query(Presupuesto).options(
        joinedload(Presupuesto.config),
        joinedload(Presupuesto.capitulos).joinedload(Capitulo.partidas).selectinload(Partida.insumos)
    ).filter(Presupuesto.id == pid).first()
    if not p:
        raise HTTPException(404, "Presupuesto no encontrado")
    return p


@router.get("/presupuestos/{pid}/materiales-semanales")
def get_materiales_semanales(pid: str, db: Session = Depends(get_db)):
    p = _cargar_con_insumos(pid, db)
    filas = _calcular(p, _overrides(db, pid), _orden_manual(db, pid))
    rows = materiales_semanales(p, filas)
    for r in rows:
        r["semana_inicio"] = r["semana_inicio"].isoformat(); r["semana_fin"] = r["semana_fin"].isoformat()
    return {"obra_id": p.id, "orden_manual": bool(_orden_manual(db, pid)),
            "reajuste_materiales": float(p.config.reajuste_materiales or 0) if p.config else 0.0,
            "filas": rows, "costo_total": round(sum(r["costo"] for r in rows), 2)}


@router.get("/presupuestos/{pid}/gasto-semanal")
def get_gasto_semanal(pid: str, db: Session = Depends(get_db)):
    """[2026-10-04] Panel del Gantt: por semana, gasto de MATERIALES + MANO DE OBRA y la
    lista consolidada de materiales, en el orden VIGENTE del Gantt. Se re-pide en cada
    movimiento del slider, asi la lista y los montos siguen al Gantt en vivo.
    Costos = costo directo (sin sobrecosto); materiales con reajuste de la obra.
    Mismo reparto que el portal (v_materiales_semanales 006): dias laborables lun-sab."""
    p = _cargar_con_insumos(pid, db)
    filas = _calcular(p, _overrides(db, pid), _orden_manual(db, pid))
    rows = materiales_semanales(p, filas, tipos=("MATERIAL", "MANO_OBRA"))
    # jornadas por semana (de la cuadrilla del Gantt): n_esp/n_ay x dias en la semana
    jorn = {}
    for f in filas:
        dur = max(1, int(f["duracion_dias"]))
        for d in _dias_laborales_actividad(f["fecha_inicio"], dur):
            lunes = d - timedelta(days=d.weekday())
            j = jorn.setdefault(lunes, [0, 0])
            j[0] += int(f.get("n_esp", engine.DEF_ESP)); j[1] += int(f.get("n_ay", engine.DEF_AY))
    semanas = sorted(set(jorn) | {r["semana_inicio"] for r in rows})
    d0 = semanas[0] if semanas else None
    out = []
    for lunes in semanas:
        sr = [r for r in rows if r["semana_inicio"] == lunes]
        mats, acts = {}, []
        for r in sr:
            tag = f"#{r['orden'] + 1} {r['csi']}"
            if tag not in acts:
                acts.append(tag)
            if r["tipo"] != "MATERIAL":
                continue
            k = (r["clave"], r["unidad"])
            m = mats.setdefault(k, {"clave": r["clave"], "material": r["material"], "unidad": r["unidad"],
                                    "cantidad": 0.0, "costo": 0.0})
            m["cantidad"] += r["cantidad"]; m["costo"] += r["costo"]
        ma = sum(r["costo"] for r in sr if r["tipo"] == "MATERIAL")
        mo = sum(r["costo"] for r in sr if r["tipo"] == "MANO_OBRA")
        out.append({
            "semana": (lunes - d0).days // 7 + 1,
            "semana_inicio": lunes.isoformat(), "semana_fin": (lunes + timedelta(days=6)).isoformat(),
            "materiales_costo": round(ma, 2), "mano_obra_costo": round(mo, 2), "total": round(ma + mo, 2),
            "jornadas_esp": jorn.get(lunes, [0, 0])[0], "jornadas_ay": jorn.get(lunes, [0, 0])[1],
            "actividades": acts,
            "materiales": sorted(({**m, "cantidad": round(m["cantidad"], 4), "costo": round(m["costo"], 2)}
                                  for m in mats.values()), key=lambda m: -m["costo"]),
        })
    return {
        "obra_id": p.id, "moneda": p.moneda or "HNL", "orden_manual": bool(_orden_manual(db, pid)),
        "reajuste_materiales": float(p.config.reajuste_materiales or 0) if p.config else 0.0,
        "semanas": out,
        "total_materiales": round(sum(s["materiales_costo"] for s in out), 2),
        "total_mano_obra": round(sum(s["mano_obra_costo"] for s in out), 2),
    }


@router.get("/presupuestos/{pid}/export-materiales-semanales")
def export_materiales_semanales(pid: str, db: Session = Depends(get_db)):
    """XLSX: hoja 'Por semana' (materiales consolidados por semana, para comprar),
    hoja 'Por actividad' (detalle semana > actividad en orden del Gantt > material)."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
    except ImportError:
        raise HTTPException(500, "openpyxl no disponible")

    p = _cargar_con_insumos(pid, db)
    om = _orden_manual(db, pid)
    filas = _calcular(p, _overrides(db, pid), om)
    rows = materiales_semanales(p, filas)
    if not rows:
        raise HTTPException(400, "La obra no tiene insumos MATERIAL en partidas con cantidad")
    moneda = p.moneda or "HNL"
    reaj = float(p.config.reajuste_materiales or 0) if p.config else 0.0

    thin = Side(style="thin", color="CCCCCC")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    hdr_font = Font(bold=True, color=HDR_TEXT, size=10)
    hdr_fill = PatternFill("solid", fgColor=HDR_FILL)
    sem_fill = PatternFill("solid", fgColor=DIV_FILL)

    semanas = []
    for r in rows:
        if not semanas or semanas[-1] != r["semana_inicio"]:
            if r["semana_inicio"] not in semanas:
                semanas.append(r["semana_inicio"])
    d0 = semanas[0]

    def titulo(ws, txt, ncol):
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncol)
        c = ws.cell(row=1, column=1, value=txt)
        c.font = Font(bold=True, size=13, color=HDR_TEXT); c.fill = hdr_fill
        c.alignment = Alignment(horizontal="center")
        ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=ncol)
        s = ws.cell(row=2, column=1, value=(
            f"Orden del Gantt: {'MANUAL' if om else 'automático (fase/CSI)'}  |  {len(semanas)} semanas  |  "
            f"Reparto proporcional a días laborables (lun-sáb)  |  Reajuste materiales {reaj:+.2f}%  |  "
            f"Costo total {moneda} {sum(r['costo'] for r in rows):,.2f}"))
        s.font = Font(size=9, italic=True, color="666666"); s.alignment = Alignment(horizontal="center")

    def header(ws, row, cols):
        for ci, t in enumerate(cols, 1):
            c = ws.cell(row=row, column=ci, value=t)
            c.font = hdr_font; c.fill = hdr_fill; c.border = border
            c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    def semana_bar(ws, row, ncol, lunes, extra):
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=ncol)
        n = (lunes - d0).days // 7 + 1
        c = ws.cell(row=row, column=1, value=(
            f"Semana {n}:  {lunes.strftime('%d/%m/%Y')} – {(lunes + timedelta(days=6)).strftime('%d/%m/%Y')}   {extra}"))
        c.font = Font(bold=True, color=DIV_TEXT, size=11); c.fill = sem_fill
        c.alignment = Alignment(horizontal="left", indent=1)

    wb = Workbook()
    # Hoja 1: Por semana (consolidado para compras)
    ws = wb.active; ws.title = "Por semana"
    cols = ["Clave", "Material", "Unidad", "Cantidad", f"Costo unit. ({moneda})", f"Costo ({moneda})", "Actividades (orden Gantt)"]
    titulo(ws, f"{p.nombre} — Materiales por semana", len(cols))
    header(ws, 4, cols)
    r_ = 5
    for lunes in semanas:
        sem_rows = [x for x in rows if x["semana_inicio"] == lunes]
        cons = {}
        for x in sem_rows:   # conserva el orden de primera aparicion (orden del Gantt)
            k = (x["clave"], x["unidad"])
            c = cons.setdefault(k, {"material": x["material"], "cant": 0.0, "costo": 0.0, "cu": x["costo_unit"], "acts": []})
            c["cant"] += x["cantidad"]; c["costo"] += x["costo"]
            tag = f"#{x['orden'] + 1} {x['csi']}"
            if tag not in c["acts"]:
                c["acts"].append(tag)
        semana_bar(ws, r_, len(cols), lunes,
                   f"{len(cons)} materiales  ·  {moneda} {sum(c['costo'] for c in cons.values()):,.2f}")
        r_ += 1
        for (clave, uni), c in cons.items():
            vals = [clave, c["material"], uni, round(c["cant"], 4), c["cu"], round(c["costo"], 2), ", ".join(c["acts"])]
            for ci, v in enumerate(vals, 1):
                cell = ws.cell(row=r_, column=ci, value=v); cell.border = border; cell.font = Font(size=9)
                if ci in (4, 5, 6):
                    cell.number_format = '#,##0.00'; cell.alignment = Alignment(horizontal="right")
            r_ += 1
    for ci, w in enumerate([11, 46, 8, 12, 13, 14, 40], 1):
        ws.column_dimensions[get_column_letter(ci)].width = w
    ws.freeze_panes = "A5"

    # Hoja 2: Por actividad (detalle)
    ws2 = wb.create_sheet("Por actividad")
    cols2 = ["#", "CSI", "Actividad", "Inicio", "Fin", "Días en sem.", "Clave", "Material", "Unidad", "Cantidad", f"Costo ({moneda})"]
    titulo(ws2, f"{p.nombre} — Materiales por semana y actividad (orden del Gantt)", len(cols2))
    header(ws2, 4, cols2)
    r_ = 5
    for lunes in semanas:
        sem_rows = [x for x in rows if x["semana_inicio"] == lunes]
        semana_bar(ws2, r_, len(cols2), lunes, f"{moneda} {sum(x['costo'] for x in sem_rows):,.2f}")
        r_ += 1
        for x in sem_rows:
            vals = [x["orden"] + 1, x["csi"], x["actividad"], x["act_inicio"], x["act_fin"],
                    f"{x['dias_semana']}/{x['duracion']}", x["clave"], x["material"], x["unidad"], x["cantidad"], x["costo"]]
            for ci, v in enumerate(vals, 1):
                cell = ws2.cell(row=r_, column=ci, value=v); cell.border = border; cell.font = Font(size=9)
                if ci in (10, 11):
                    cell.number_format = '#,##0.00'; cell.alignment = Alignment(horizontal="right")
            r_ += 1
    for ci, w in enumerate([5, 12, 40, 11, 11, 9, 10, 40, 8, 12, 13], 1):
        ws2.column_dimensions[get_column_letter(ci)].width = w
    ws2.freeze_panes = "A5"

    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="Estimastruct_Materiales_Semanales_{safe_fname(p.nombre)}.xlsx"'},
    )
