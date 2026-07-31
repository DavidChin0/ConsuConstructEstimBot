"""
Export PDF con membrete ConsuConstruct (reportlab) — replica template Fittacori.
  GET /presupuestos/{pid}/export-pdf?report=presupuesto&cliente=..&proyecto=..&...

report: presupuesto | cronograma | insumos | db | audit
Campos del membrete vienen por query (editables en el dialogo); defaults desde la obra.
"""
import io
import os
import sys
import re
import json
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload

from backend.db import get_db
from backend.models import Presupuesto, Capitulo, Partida
from backend.config import CONFIG
from backend import membrete as MB
from backend import cronograma as crono_engine
from backend.routers.export import safe_fname
from backend.services.pricing import calc_base
from backend.services.export_pdf_memoria import prorrateo_banco

router = APIRouter(tags=["export-pdf"])

# Buffer de contratiempos que se agrega al FINAL del cronograma del banco.
BUFFER_CONTRATIEMPOS_DIAS = 26         # 1 mes laboral (6 días/sem)


# ── Persistencia "para Banco" por obra (JSON local; migra a Supabase luego) ──
# Bundle por obra: {valor_banco, rtn_cliente, ubicacion}. Al generar el PDF
# banco queda persistido y el popup lo pre-llena la próxima vez.
def _valores_banco_load() -> dict:
    try:
        with open(CONFIG.VALORES_BANCO_JSON, encoding="utf-8") as fh:
            return json.load(fh) or {}
    except (FileNotFoundError, ValueError, OSError):
        return {}


# Campos de texto del membrete que se persisten y autopopulan por obra.
BANCO_TEXT_KEYS = ("rtn_cliente", "ubicacion", "cliente", "proyecto", "codigo_interno")


def _obra_banco_get(pid: str) -> dict:
    """Bundle persistido de la obra: valor_banco + campos de texto del membrete
    (rtn_cliente, ubicacion, cliente, proyecto, codigo_interno).
    Compatibilidad: formato viejo era un escalar (solo valor_banco)."""
    raw = _valores_banco_load().get(pid)
    out = {"valor_banco": None}
    out.update({k: "" for k in BANCO_TEXT_KEYS})
    if raw is None:
        return out
    if isinstance(raw, (int, float)):                 # formato viejo (escalar)
        out["valor_banco"] = float(raw)
        return out
    if isinstance(raw, dict):
        for k in BANCO_TEXT_KEYS:
            out[k] = raw.get(k) or ""
        try:
            if raw.get("valor_banco") is not None:
                out["valor_banco"] = float(raw["valor_banco"])
        except (TypeError, ValueError):
            out["valor_banco"] = None
    return out


def _obra_banco_save(pid: str, valor: float, campos: dict) -> None:
    """Persiste el bundle {pid: {valor_banco, ...campos texto}} en el JSON local.
    Escritura atómica (tmp+replace)."""
    data = _valores_banco_load()
    bundle = {"valor_banco": float(valor)}
    for k in BANCO_TEXT_KEYS:
        bundle[k] = (campos.get(k) or "").strip()
    data[pid] = bundle
    path = CONFIG.VALORES_BANCO_JSON
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    except OSError:
        pass                              # no romper el export si falla el guardado

SUBTITULO = {
    "presupuesto": "ESTIMACIÓN DE OBRA POR ACTIVIDAD",
    "cronograma":  "CRONOGRAMA DE EJECUCIÓN",
    "insumos":     "INSUMOS NECESARIOS POR ACTIVIDAD",
    "db":          "BASE DE DATOS DE ACTIVIDADES",
    "audit":       "REPORTE DE AUDITORÍA",
    "banco":       "ESTIMACIÓN PARA FINANCIAMIENTO",
}

DISCLAIMER_PRESUPUESTO = [
    "ESTE PRESUPUESTO INCLUYE LA COMPRA, ENTREGA E INSTALACIÓN DE LOS MATERIALES "
    "REQUERIDOS PARA CADA ACTIVIDAD DESCRITA, QUE SON PARTE DEL CONTRATO.",
    "TODAS LAS ACTIVIDADES A REALIZAR EN ESTE PROYECTO ESTÁN SUJETAS AL CONTRATO DE "
    "CONSTRUCCIÓN. LAS ACTIVIDADES AQUÍ DESCRITAS CON SU CANTIDAD DE OBRA SON PARTE DEL "
    "CONTRATO; CASO CONTRARIO SE APLICARÁN LAS CLÁUSULAS NECESARIAS PARA LLEVAR A CABO "
    "OBRAS NO CONTEMPLADAS POR MEDIO DE ÓRDENES DE CAMBIO, PAGADAS SEGÚN EL PROGRAMA DE DESEMBOLSOS.",
    "TODAS LAS ACTIVIDADES DESCRITAS EN EL CONTRATO EN EL APARTADO TERCERO.",
]


def _fmt(n):
    try:
        return f"{float(n):,.2f}"
    except Exception:
        return "0.00"


def _sym(p) -> str:
    """Símbolo de la moneda de la obra. HNL/LPS -> 'L' (Lempira)."""
    m = (getattr(p, "moneda", None) or "HNL").strip().upper()
    return "L" if m in ("HNL", "L", "LPS") else m


def _money(n, sym) -> str:
    return f"{sym} {_fmt(n)}"


def _ctx(p: Presupuesto, report: str, q) -> dict:
    """Contexto del membrete: query params > defaults de la obra."""
    nombre = p.nombre or ""
    # codigo CC del nombre (ej. 'CC132 — ...' -> 'CC-2026-132')
    m = re.search(r"CC\s*-?\s*(\d+)", nombre, re.I)
    cod_def = f"CC-{date.today().year}-{m.group(1)}" if m else ""
    fecha_def = date.today().strftime("%d/%m/%Y")
    g = lambda k, d="": (q.get(k) or d)
    return {
        "titulo": g("proyecto", nombre),
        "titulo_proyecto": g("proyecto", nombre),
        "codigo_nombre": g("codigo_nombre", nombre),
        "subtitulo": g("subtitulo", SUBTITULO.get(report, "")),
        "cliente": g("cliente", p.cliente or ""),
        "rtn_cliente": g("rtn_cliente", ""),
        "ubicacion": g("ubicacion", ""),
        "fecha": g("fecha", fecha_def),
        "codigo_interno": g("codigo_interno", cod_def),
    }


def _rows_presupuesto(p: Presupuesto):
    sym = _sym(p)
    headers = ["Clave", "Descripción", "Unidad", "Cantidad", "Precio unitario", "Total"]
    widths = [58, 330, 42, 58, 86, 86]
    rows = []
    for cap in sorted(p.capitulos, key=lambda c: (c.orden or 0)):
        for pa in sorted(cap.partidas, key=lambda x: x.orden or 0):
            if float(pa.total or 0) <= 0:
                continue
            rows.append([pa.clave_csi or "", pa.descripcion or "", pa.unidad or "",
                         _fmt(pa.cantidad), _money(pa.precio_unitario, sym), _money(pa.total, sym)])
    total = sum(float(pa.total or 0) for cap in p.capitulos for pa in cap.partidas)
    rows.append(["", "TOTAL", "", "", "", _money(total, sym)])
    return headers, rows, widths, (3, 4, 5), DISCLAIMER_PRESUPUESTO


def _rows_cronograma(p: Presupuesto):
    crono_input = []
    for cap in sorted(p.capitulos, key=lambda c: (c.orden or 0)):
        for pa in sorted(cap.partidas, key=lambda x: x.orden or 0):
            if float(pa.cantidad or 0) <= 0:
                continue
            crono_input.append(dict(clave_csi=(pa.clave_csi or "").strip(),
                                    descripcion=pa.descripcion or "", unidad=pa.unidad or "",
                                    cantidad=float(pa.cantidad or 0),
                                    capitulo_clave=(cap.clave or "").strip(), partida_id=pa.id))
    filas = crono_engine.construir_cronograma(crono_input)
    headers = ["#", "CSI", "Descripción", "Fase", "Inicio", "Días", "Esp", "Ay"]
    widths = [26, 70, 300, 150, 60, 38, 30, 30]
    rows = [[f["orden"] + 1, f["clave_csi"], f["descripcion"], f["fase"],
             f["fecha_inicio"], f["duracion_dias"], f.get("n_esp", 3), f.get("n_ay", 3)]
            for f in filas]
    return headers, rows, widths, (5, 6, 7), None


def _costos_obra(p: Presupuesto):
    """total_real = Σ partida.total (con sobrecosto actual).
    costo_directo = Σ cantidad × costo_base (MO + MA + matriz), misma definición
    que /presupuestos y /calcular (services.pricing.calc_base), sin sobrecosto."""
    total_real = 0.0
    costo_directo = 0.0
    for cap in p.capitulos:
        for pa in cap.partidas:
            total_real += float(pa.total or 0)
            costo_directo += float(pa.cantidad or 0) * calc_base(pa.costo_mo, pa.costo_ma, pa.unitario_matriz)
    return total_real, costo_directo


def _rows_presupuesto_banco(p: Presupuesto, factor: float):
    """Igual que _rows_presupuesto pero precio unitario y total prorrateados
    por `factor` (= valor_banco / total_real). La fila TOTAL queda == valor_banco
    exacto (se fuerza al valor_banco pasado por el caller, no a la suma redondeada)."""
    sym = _sym(p)
    headers = ["Clave", "Descripción", "Unidad", "Cantidad", "Precio unitario", "Total"]
    widths = [58, 330, 42, 58, 86, 86]
    rows = []
    suma = 0.0
    for cap in sorted(p.capitulos, key=lambda c: (c.orden or 0)):
        for pa in sorted(cap.partidas, key=lambda x: x.orden or 0):
            if float(pa.total or 0) <= 0:
                continue
            pu_banco = float(pa.precio_unitario or 0) * factor
            total_banco = float(pa.total or 0) * factor
            suma += total_banco
            rows.append([pa.clave_csi or "", pa.descripcion or "", pa.unidad or "",
                         _fmt(pa.cantidad), _money(pu_banco, sym), _money(total_banco, sym)])
    return headers, rows, widths, (3, 4, 5), suma


def _gantt_banco_data(p: Presupuesto, factor: float):
    """Datos para el diagrama de Gantt del banco. Eje en DÍAS ACTIVOS (no fechas):
    cada actividad lleva dia_ini/dia_fin (offsets 0-based en días laborales) y su
    valor prorrateado. El PDF las dibuja como BARRAS (MB.build_gantt_table).
    Al FINAL se agrega un buffer de contratiempos de 1 mes (BUFFER_CONTRATIEMPOS_DIAS).
    Filtro total>0 (coherente con el presupuesto-banco; sin barras en L 0.00)."""
    sym = _sym(p)
    crono_input = []
    total_por_partida = {}
    for cap in sorted(p.capitulos, key=lambda c: (c.orden or 0)):
        for pa in sorted(cap.partidas, key=lambda x: x.orden or 0):
            if float(pa.total or 0) <= 0:
                continue
            crono_input.append(dict(clave_csi=(pa.clave_csi or "").strip(),
                                    descripcion=pa.descripcion or "", unidad=pa.unidad or "",
                                    cantidad=float(pa.cantidad or 0),
                                    capitulo_clave=(cap.clave or "").strip(), partida_id=pa.id))
            total_por_partida[pa.id] = float(pa.total or 0)
    filas = crono_engine.construir_cronograma(crono_input)
    activities = []
    suma = 0.0
    fin_max = 0
    for f in filas:
        dia_ini = int(f["inicio_lab"])                 # offset 0-based en días activos
        dia_fin = dia_ini + int(f["duracion_dias"])    # fin exclusivo (nº de días activos)
        fin_max = max(fin_max, dia_fin)
        valor = total_por_partida.get(f["partida_id"], 0.0) * factor
        suma += valor
        activities.append(dict(desc=f["descripcion"], dia_ini=dia_ini, dia_fin=dia_fin,
                               valor=_money(valor, sym), buffer=False))
    # Buffer de contratiempos: 1 mes laboral al final, valor L 0 (no es costo).
    if activities:
        activities.append(dict(
            desc=f"IMPREVISTOS / CONTRATIEMPOS (buffer {BUFFER_CONTRATIEMPOS_DIAS} días activos)",
            dia_ini=fin_max, dia_fin=fin_max + BUFFER_CONTRATIEMPOS_DIAS,
            valor=_money(0, sym), buffer=True))
    return activities, suma


def _rows_simple(p: Presupuesto, con_costos=True):
    sym = _sym(p)
    headers = ["Clave", "Descripción", "Unidad", "Cantidad", "M. Obra", "Materiales", "Total"]
    widths = [58, 300, 42, 56, 78, 80, 84]
    rows = []
    for cap in sorted(p.capitulos, key=lambda c: (c.orden or 0)):
        for pa in sorted(cap.partidas, key=lambda x: x.orden or 0):
            if float(pa.cantidad or 0) <= 0:
                continue
            rows.append([pa.clave_csi or "", pa.descripcion or "", pa.unidad or "",
                         _fmt(pa.cantidad), _money(pa.costo_mo, sym), _money(pa.costo_ma, sym), _money(pa.total, sym)])
    return headers, rows, widths, (3, 4, 5, 6), None


@router.get("/presupuestos/{pid}/export-pdf")
def export_pdf(pid: str, request: Request, report: str = "presupuesto",
               db: Session = Depends(get_db)):
    p = db.query(Presupuesto).options(
        joinedload(Presupuesto.capitulos).joinedload(Capitulo.partidas)
    ).filter(Presupuesto.id == pid).first()
    if not p:
        raise HTTPException(404, "Presupuesto no encontrado")

    q = request.query_params
    ctx = _ctx(p, report, q)

    if report == "banco":
        return _export_pdf_banco(p, ctx, q)

    if report == "presupuesto":
        headers, rows, widths, ar, disc = _rows_presupuesto(p)
    elif report == "cronograma":
        headers, rows, widths, ar, disc = _rows_cronograma(p)
    elif report in ("insumos", "db", "audit"):
        headers, rows, widths, ar, disc = _rows_simple(p)
    else:
        raise HTTPException(400, f"Reporte desconocido: {report}")

    if not rows:
        raise HTTPException(400, "La obra no tiene datos para exportar")

    buf = io.BytesIO()
    MB.build_report_pdf(buf, ctx, headers, rows, widths, disclaimer=disc, align_right_cols=ar)
    buf.seek(0)
    nombre = safe_fname(p.nombre)
    return StreamingResponse(
        buf, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="ConsuConstruct_{report}_{nombre}.pdf"'},
    )


def _export_pdf_banco(p: Presupuesto, ctx: dict, q) -> StreamingResponse:
    """report=banco: presupuesto-banco + Gantt prorrateados a `valor_banco`,
    en un solo PDF (2 secciones con PageBreak). Ver fórmulas en
    PLAN_PDF_BANCO_SONNET.md — riesgo financiero, cuadrar Σ == valor_banco."""
    try:
        valor_banco = float(q.get("valor_banco") or 0)
    except (TypeError, ValueError):
        valor_banco = 0.0
    if valor_banco <= 0:
        raise HTTPException(400, "valor_banco debe ser mayor que 0")

    total_real, costo_directo = _costos_obra(p)
    if total_real <= 0:
        raise HTTPException(400, "La obra no tiene costos (total_real == 0)")
    if costo_directo <= 0:
        raise HTTPException(400, "La obra no tiene costo directo (costo_directo == 0)")

    # Fuente ÚNICA del factor: services/export_pdf_memoria.prorrateo_banco.
    # Misma aritmética que antes (factor = valor_banco / total_real); lo que
    # cambia es que ahora el número que sale en el PDF y el que narra
    # GET /auditoria/export-pdf/{pid}/memoria son literalmente el mismo cálculo,
    # no dos copias que puedan divergir (ADR-003).
    factor = prorrateo_banco(total_real, valor_banco, costo_directo)["factor"]

    # persiste el bundle elegido para esta obra (valor + campos de membrete)
    _obra_banco_save(p.id, valor_banco, {k: q.get(k) for k in BANCO_TEXT_KEYS})

    h1, r1, w1, ar1, suma1 = _rows_presupuesto_banco(p, factor)
    if not r1:
        raise HTTPException(400, "La obra no tiene datos para exportar")
    r1.append(["", "TOTAL", "", "", "", _money(valor_banco, _sym(p))])

    activities, _suma2 = _gantt_banco_data(p, factor)
    gantt_tbl = MB.build_gantt_table(activities)   # None si no hay actividades

    # Header del PDF banco queda idéntico al del presupuesto normal (sin nota
    # de VALOR PARA BANCO / SOBRECOSTO APLICADO).
    ctx1 = dict(ctx, subtitulo=q.get("subtitulo") or "ESTIMACIÓN PARA FINANCIAMIENTO")
    ctx2 = dict(ctx1, subtitulo="DIAGRAMA DE EJECUCIÓN (GANTT)")

    sections = [
        dict(ctx=ctx1, headers=h1, rows=r1, col_widths=w1, align_right_cols=ar1,
             disclaimer=list(DISCLAIMER_PRESUPUESTO)),
    ]
    if gantt_tbl is not None:
        sections.append(dict(ctx=ctx2, flowable=gantt_tbl, disclaimer=None))
    buf = io.BytesIO()
    MB.build_report_pdf_multi(buf, sections)
    buf.seek(0)
    nombre = safe_fname(p.nombre)
    return StreamingResponse(
        buf, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="ConsuConstruct_banco_{nombre}.pdf"'},
    )


@router.get("/presupuestos/{pid}/valor-banco")
def get_valor_banco(pid: str):
    """Bundle persistido de la obra (valor_banco + campos de texto del membrete),
    o vacíos. Lo usa el popup para autopopular con lo último ingresado."""
    return _obra_banco_get(pid)
