"""
Vista previa HTML + export PDF vía navegador (Playwright/Chromium).
Alternativa WYSIWYG al PDF de reportlab: márgenes editables con @page.

  GET /presupuestos/{pid}/preview-pdf?report=...&mt=&mr=&mb=&ml=
      -> HTML imprimible con toolbar (ajustar márgenes, descargar, Ctrl+P).
  GET /presupuestos/{pid}/export-pdf-html?report=...&mt=&mr=&mb=&ml=
      -> PDF (Chromium) con los mismos márgenes.

Reutiliza los builders de filas de routers.export_pdf (misma fuente de datos).
"""
import io
import os
import sys
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy.orm import Session, joinedload

from backend.db import get_db
from backend.models import Presupuesto, Capitulo
from backend.routers.export_pdf import (
    _ctx, _rows_presupuesto, _rows_cronograma, _rows_simple,
)
from backend.routers.export import safe_fname
from backend import pdf_html as PH

router = APIRouter(tags=["preview-pdf"])


def _load(pid: str, db: Session) -> Presupuesto:
    p = db.query(Presupuesto).options(
        joinedload(Presupuesto.capitulos).joinedload(Capitulo.partidas)
    ).filter(Presupuesto.id == pid).first()
    if not p:
        raise HTTPException(404, "Presupuesto no encontrado")
    return p


def _build(p: Presupuesto, report: str, q):
    ctx = _ctx(p, report, q)
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
    return ctx, headers, rows, ar, disc


def _margins(q) -> dict:
    def g(k, d):
        try:
            return float(q.get(k))
        except (TypeError, ValueError):
            return d
    return {"top": g("mt", 1.2), "right": g("mr", 1.2),
            "bottom": g("mb", 1.4), "left": g("ml", 1.2)}


@router.get("/presupuestos/{pid}/preview-pdf", response_class=HTMLResponse)
def preview_pdf(pid: str, request: Request, report: str = "presupuesto",
                db: Session = Depends(get_db)):
    p = _load(pid, db)
    q = request.query_params
    ctx, headers, rows, ar, disc = _build(p, report, q)
    html = PH.render_document_html(
        ctx, headers, rows, align_right_cols=ar, disclaimer=disc,
        margins_cm=_margins(q), with_toolbar=True, report=report, pid=pid)
    return HTMLResponse(html)


@router.get("/presupuestos/{pid}/export-pdf-html")
def export_pdf_html(pid: str, request: Request, report: str = "presupuesto",
                    db: Session = Depends(get_db)):
    p = _load(pid, db)
    q = request.query_params
    ctx, headers, rows, ar, disc = _build(p, report, q)
    html = PH.render_document_html(
        ctx, headers, rows, align_right_cols=ar, disclaimer=disc,
        margins_cm=_margins(q), with_toolbar=False, report=report, pid=pid)
    try:
        pdf = PH.html_to_pdf(html)
    except Exception as e:
        raise HTTPException(
            500,
            "No se pudo generar el PDF con Chromium. "
            "Instalá el navegador: `python -m playwright install chromium`. "
            f"Detalle: {e}",
        )
    nombre = safe_fname(p.nombre)
    return StreamingResponse(
        io.BytesIO(pdf), media_type="application/pdf",
        headers={"Content-Disposition":
                 f'attachment; filename="ConsuConstruct_{report}_{nombre}.pdf"'},
    )
