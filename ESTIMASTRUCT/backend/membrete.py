"""
Membrete ConsuConstruct para exports PDF (reportlab).
Replica el encabezado/pie del template Fittacori (CC135):

  - Barra de título (caja con nombre de proyecto)  -> en TODAS las paginas
  - Pie: barra gris CONSUCONSTRUCT.COM + caja amarilla N/total  -> TODAS
  - Bloque de empresa (logo + razon social + cliente + cuentas + contacto) -> pag 1
  - Banda de disclaimer (3 columnas) -> pag 1, opcional (solo Presupuesto)

build_report_pdf(buf, ctx, headers, rows, col_widths, disclaimer=None) arma el
reporte completo: bloque empresa (pag1) + tabla de datos (repite encabezados).
"""
import os
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Table, TableStyle,
    Image, Spacer, PageBreak,
)
from reportlab.pdfgen import canvas as _canvas
from reportlab.graphics.shapes import Drawing, Rect, Line, String

_THIS = os.path.dirname(os.path.abspath(__file__))
# Icono oficial ConsuConstruct (PNG 512x512 aplanado sobre blanco). El antiguo
# logo_consu.png no era PNG real y reportlab lo renderizaba oscuro.
LOGO_PATH = os.path.join(_THIS, "assets", "logo_consuconstruct.png")

PAGE = landscape(letter)            # 792 x 612 pt
W, H = PAGE
MARGEN = 34                          # margen izq/der (subido: respeta margen)
TITULO_H = 20                        # alto barra de titulo
TITULO_TOP = H - 38                  # tope de la barra de titulo (más aire arriba)
PIE_Y = 22                           # baseline del pie (más aire abajo)

AMARILLO = colors.HexColor("#FFD600")
GRIS = colors.HexColor("#5E5E5E")
NEGRO = colors.HexColor("#1A1A1A")
AZUL = colors.HexColor("#1F6FB7")

# ── Datos fijos de empresa (template Fittacori) ──────────────────────────────
EMPRESA = {
    "razon_social": "Consultorías de Construcción S. de R.L.",
    "rtn": "08019025220890",
    "responsable": "Ing. David Chinchilla",
    "titular_cuentas": "Consultorias de Construcción S. de R.L.",
    "cuentas": [
        ("BAC Dólares", "759381371"),
        ("Davivienda", "1201574976"),
        ("Ficohsa", "200021854475"),
    ],
    "contacto": [
        ("Web Page", "CONSUCONSTRUCT.COM"),
        ("Instagram", "consuconstruct"),
        ("Facebook", "consuconstruct.hn"),
        ("e-mail", "consuconstruct@gmail.com"),
        ("Whatsapp", "504 9662-8408"),
        ("Linked-in", "consuconstruct"),
    ],
}

# ── Estilos de parrafo ───────────────────────────────────────────────────────
def _st(name, size, bold=False, color=NEGRO, align=TA_LEFT, leading=None):
    return ParagraphStyle(
        name, fontName="Helvetica-Bold" if bold else "Helvetica",
        fontSize=size, leading=leading or size + 2, textColor=color, alignment=align)

S_RAZON = _st("razon", 9, color=NEGRO)
S_CODNOM = _st("codnom", 8, color=NEGRO)
S_SUBT = _st("subt", 9, bold=True, color=NEGRO, align=TA_CENTER)
S_LBL = _st("lbl", 7.5, color=NEGRO)
S_VAL = _st("val", 8, bold=True, color=NEGRO)
S_SM = _st("sm", 7, color=NEGRO)
S_CTA_H = _st("ctah", 8, bold=True, align=TA_CENTER)
S_CTA = _st("cta", 7.5, bold=True)
S_LINK = _st("link", 7.5, bold=True, color=AZUL, align=TA_CENTER)
S_DISC = _st("disc", 6, color=NEGRO, leading=7)
S_TH = _st("th", 8, bold=True, color=colors.white, align=TA_CENTER)
S_TD = _st("td", 7.5, color=NEGRO)
S_TDR = _st("tdr", 7.5, color=NEGRO, align=TA_CENTER)
S_NOTA = _st("nota", 10.5, bold=True, color=NEGRO, align=TA_CENTER)


def nota_block(text):
    """Franja destacada (fondo amarillo) para una nota visible en el header,
    p.ej. 'VALOR PARA BANCO … · SOBRECOSTO APLICADO X%'."""
    t = Table([[Paragraph(text, S_NOTA)]], colWidths=[W - 2 * MARGEN])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), AMARILLO),
        ("BOX", (0, 0), (-1, -1), 0.6, NEGRO),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


# ── Canvas con numero de pagina (N/total) ────────────────────────────────────
class _NumberedCanvas(_canvas.Canvas):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._saved = []

    def showPage(self):
        self._saved.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved)
        for st in self._saved:
            self.__dict__.update(st)
            self._pageno(total)
            super().showPage()
        super().save()

    def _pageno(self, total):
        bw, bh = 50, 15
        x = W - MARGEN - bw
        self.setFillColor(AMARILLO)
        self.rect(x, PIE_Y - 3, bw, bh, fill=1, stroke=0)
        self.setFillColor(NEGRO)
        self.setFont("Helvetica-Bold", 9)
        self.drawCentredString(x + bw / 2, PIE_Y + 1, f"{self._pageNumber}/{total}")


# ── Barra de titulo + pie (cada pagina) ──────────────────────────────────────
def _furniture(canvas, doc):
    titulo = getattr(doc, "_titulo", "")
    canvas.saveState()
    # barra de titulo
    canvas.setStrokeColor(NEGRO)
    canvas.setLineWidth(0.7)
    canvas.rect(MARGEN, TITULO_TOP, W - 2 * MARGEN, TITULO_H, fill=0, stroke=1)
    canvas.setFillColor(NEGRO)
    canvas.setFont("Helvetica-Bold", 11)
    canvas.drawCentredString(W / 2, TITULO_TOP + 6, titulo)
    # pie: barra gris centrada
    bw = 175
    canvas.setFillColor(GRIS)
    canvas.rect(W / 2 - bw / 2, PIE_Y - 3, bw, 15, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 8.5)
    canvas.drawCentredString(W / 2, PIE_Y + 1, "CONSUCONSTRUCT.COM")
    canvas.restoreState()


# ── Bloque de empresa (pagina 1) ─────────────────────────────────────────────
def _tabla_contacto():
    rows = [[Paragraph(k, S_CTA), Paragraph(v, S_LINK)] for k, v in EMPRESA["contacto"]]
    t = Table(rows, colWidths=[55, 110])
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#222222")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return t


def _col_izq(ctx):
    cli = [
        [Paragraph("CLIENTE:", S_LBL), Paragraph(ctx.get("cliente", ""), S_VAL)],
    ]
    if ctx.get("rtn_cliente"):
        cli.append([Paragraph("RTN:", S_LBL), Paragraph(ctx["rtn_cliente"], S_SM)])
    cli_t = Table(cli, colWidths=[42, 150])
    cli_t.setStyle(TableStyle([
        ("BOX", (1, 0), (1, 0), 0.5, NEGRO), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))
    fecha_cod = Table([[Paragraph(ctx.get("fecha", ""), S_VAL),
                        Paragraph(ctx.get("codigo_interno", ""), S_VAL)]],
                      colWidths=[95, 110])
    fecha_cod.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    inner = [
        [Paragraph(EMPRESA["razon_social"], S_RAZON)],
        [Paragraph(ctx.get("codigo_nombre", ""), S_CODNOM)],
        [Spacer(1, 2)],
        [Paragraph(ctx.get("subtitulo", ""), S_SUBT)],
        [Spacer(1, 2)],
        [cli_t],
        [Paragraph(ctx.get("ubicacion", ""), S_SM)],
        [Paragraph(EMPRESA["responsable"], S_SM)],
        [Spacer(1, 2)],
        [fecha_cod],
    ]
    return Table([[i] for i in inner], colWidths=[300],
                 style=TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0),
                                   ("TOPPADDING", (0, 0), (-1, -1), 0),
                                   ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))


def _col_cuentas():
    rows = [[Paragraph("CUENTAS", S_CTA_H)],
            [Paragraph(f"RTN: {EMPRESA['rtn']}", S_VAL)]]
    return Table(rows, colWidths=[120], style=TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("TOPPADDING", (0, 0), (-1, -1), 2)]))


def _col_bancos():
    rows = [[Paragraph(f"{n}: {v}", S_VAL)] for n, v in EMPRESA["cuentas"]]
    rows.append([Paragraph(EMPRESA["titular_cuentas"], S_SM)])
    return Table(rows, colWidths=[150], style=TableStyle([
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))


def company_block(ctx):
    """Tabla de 4 columnas: logo+datos obra | cuentas | bancos | contacto."""
    try:
        logo = Image(LOGO_PATH, width=68, height=68)   # PNG cuadrado 512x512
    except Exception:
        logo = Spacer(1, 1)
    left = Table([[logo, _col_izq(ctx)]], colWidths=[78, 305],
                 style=TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                   ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    grid = Table([[left, _col_cuentas(), _col_bancos(), _tabla_contacto()]],
                 colWidths=[388, 120, 152, 170])
    grid.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
    ]))
    return grid


def disclaimer_block(cols):
    """cols = lista de 3 textos (izq, centro, der)."""
    row = [Paragraph(c or "", S_DISC) for c in (cols + ["", "", ""])[:3]]
    t = Table([row], colWidths=[300, 380, 160])
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, NEGRO),
        ("LINEAFTER", (0, 0), (1, 0), 0.5, NEGRO),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


# ── Builder de reporte completo ──────────────────────────────────────────────
def build_report_pdf(buf, ctx, headers, rows, col_widths, disclaimer=None,
                     align_right_cols=()):
    """
    ctx: dict con titulo (barra), titulo_proyecto, codigo_nombre, subtitulo,
         cliente, rtn_cliente, ubicacion, fecha, codigo_interno.
    headers: lista de encabezados de columna.
    rows: lista de filas (cada fila lista de valores str/num).
    col_widths: anchos de columna (pt). disclaimer: [izq,centro,der] o None.
    """
    doc = BaseDocTemplate(
        buf, pagesize=PAGE,
        leftMargin=MARGEN, rightMargin=MARGEN,
        topMargin=H - TITULO_TOP + 6, bottomMargin=36)
    doc._titulo = ctx.get("titulo") or ctx.get("titulo_proyecto", "")
    frame = Frame(MARGEN, 34, W - 2 * MARGEN, TITULO_TOP - 34 - 4, id="body",
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=_furniture)])

    story = [company_block(ctx), Spacer(1, 4)]
    if disclaimer:
        story += [disclaimer_block(disclaimer), Spacer(1, 4)]
    story.append(_tabla_datos(headers, rows, col_widths, align_right_cols))
    doc.build(story, canvasmaker=_NumberedCanvas)
    return buf


def _tabla_datos(headers, rows, col_widths, align_right_cols=()):
    """Tabla de datos con encabezados que repiten por pagina (fila amarilla +
    zebra). Factorizado de build_report_pdf para reusar en build_report_pdf_multi."""
    data = [[Paragraph(str(h), S_TH) for h in headers]]
    for r in rows:
        cells = []
        for ci, v in enumerate(r):
            cells.append(Paragraph(str(v), S_TDR if ci in align_right_cols else S_TD))
        data.append(cells)
    tbl = Table(data, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), AMARILLO),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CCCCCC")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F7F7")]),
    ]))
    return tbl


# ── Diagrama de Gantt (barras de ejecución, eje en DÍAS ACTIVOS) ─────────────
GANTT_BAR = AZUL                       # barra de actividad normal
GANTT_BUFFER = GRIS                    # barra del buffer de contratiempos
DIAS_MES_ACTIVO = 26                   # paso del eje (1 mes laboral a 6 días/sem)


def _gantt_axis_dias(total_dias: int, width: float, height: float = 16,
                     paso: int = DIAS_MES_ACTIVO):
    """Encabezado del eje en DÍAS ACTIVOS: fondo amarillo + marcas cada `paso`
    días con etiqueta numérica (p.ej. 26d, 52d)."""
    dr = Drawing(width, height)
    total = max(1, total_dias)
    dr.add(Rect(0, 0, width, height, fillColor=AMARILLO, strokeColor=None))
    d = paso
    while d < total:
        x = d / total * width
        dr.add(Line(x, 0, x, height, strokeColor=colors.white, strokeWidth=0.6))
        dr.add(String(x + 2, 5, f"{d}d", fontName="Helvetica-Bold",
                      fontSize=6, fillColor=NEGRO))
        d += paso
    dr.add(String(2, 5, "días activos →", fontName="Helvetica-Bold",
                  fontSize=6, fillColor=NEGRO))
    return dr


def _gantt_bar_dias(dia_ini: int, dia_fin: int, total_dias: int, width: float,
                    height: float = 13, color=GANTT_BAR, paso: int = DIAS_MES_ACTIVO):
    """Barra por offset de DÍA ACTIVO. Etiqueta día inicio (izq) y día fin (der)."""
    dr = Drawing(width, height)
    total = max(1, total_dias)
    x0 = dia_ini / total * width
    x1 = dia_fin / total * width
    bw = max(2.5, x1 - x0)
    # guías tenues cada `paso` días
    d = paso
    while d < total:
        gx = d / total * width
        dr.add(Line(gx, 0, gx, height, strokeColor=colors.HexColor("#EEEEEE"),
                    strokeWidth=0.4))
        d += paso
    dr.add(Rect(x0, 3, bw, height - 6, fillColor=color, strokeColor=None))
    dr.add(String(max(0, x0 - 2), 4, str(dia_ini + 1), fontName="Helvetica",
                  fontSize=5, fillColor=NEGRO, textAnchor="end"))
    dr.add(String(min(width, x1 + 2), 4, str(dia_fin), fontName="Helvetica",
                  fontSize=5, fillColor=NEGRO, textAnchor="start"))
    return dr


def build_gantt_table(activities, col_act=200, col_time=460, col_val=64):
    """Tabla-Gantt en DÍAS ACTIVOS: [Actividad | barra (timeline) | Valor].
    activities: lista dict(desc, dia_ini:int, dia_fin:int (offsets 0-based en
    días activos), valor:str, buffer:bool). Repite el eje como encabezado en
    cada página (repeatRows=1)."""
    if not activities:
        return None
    total_dias = max(a["dia_fin"] for a in activities)
    header = [Paragraph("Actividad", S_TH), _gantt_axis_dias(total_dias, col_time),
              Paragraph("Valor actividad", S_TH)]
    data = [header]
    for a in activities:
        color = GANTT_BUFFER if a.get("buffer") else GANTT_BAR
        data.append([Paragraph(a["desc"] or "", S_TD),
                     _gantt_bar_dias(a["dia_ini"], a["dia_fin"], total_dias,
                                     col_time, color=color),
                     Paragraph(a["valor"] or "", S_TDR)])
    t = Table(data, colWidths=[col_act, col_time, col_val], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), AMARILLO),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CCCCCC")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F7F7")]),
    ]))
    return t


def build_report_pdf_multi(buf, sections):
    """
    Un solo PDF con varias secciones (cada una: subtítulo propio + su tabla),
    separadas por PageBreak. El company_block (logo/cliente/cuentas/contacto)
    va SOLO en la primera sección (pág 1); las siguientes arrancan directo con
    su subtítulo + tabla. repeatRows=1 y _NumberedCanvas (N/total global) se
    mantienen igual que build_report_pdf.

    sections: lista de dict(ctx, headers, rows, col_widths, align_right_cols,
                            disclaimer=None).
              ctx de la 1a sección define el título de la barra superior
              (se usa en TODAS las páginas, como en build_report_pdf).
    """
    if not sections:
        raise ValueError("build_report_pdf_multi: sections vacío")
    ctx0 = sections[0]["ctx"]
    doc = BaseDocTemplate(
        buf, pagesize=PAGE,
        leftMargin=MARGEN, rightMargin=MARGEN,
        topMargin=H - TITULO_TOP + 6, bottomMargin=36)
    doc._titulo = ctx0.get("titulo") or ctx0.get("titulo_proyecto", "")
    frame = Frame(MARGEN, 34, W - 2 * MARGEN, TITULO_TOP - 34 - 4, id="body",
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=_furniture)])

    story = []
    for i, sec in enumerate(sections):
        ctx = sec["ctx"]
        if i == 0:
            story += [company_block(ctx), Spacer(1, 4)]
        else:
            story += [PageBreak(),
                      Paragraph(ctx.get("subtitulo", ""), S_SUBT), Spacer(1, 6)]
        if sec.get("nota"):
            story += [nota_block(sec["nota"]), Spacer(1, 4)]
        disc = sec.get("disclaimer")
        if disc:
            story += [disclaimer_block(disc), Spacer(1, 4)]
        flow = sec.get("flowable")
        if flow is not None:
            story.append(flow)                     # p.ej. tabla-Gantt ya armada
        else:
            story.append(_tabla_datos(sec["headers"], sec["rows"], sec["col_widths"],
                                      sec.get("align_right_cols", ())))
    doc.build(story, canvasmaker=_NumberedCanvas)
    return buf
