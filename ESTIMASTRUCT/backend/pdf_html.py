"""
Pipeline HTML -> PDF para EstimaStruct (membrete ConsuConstruct).

Doble propósito:
  - render_document_html(...)  -> HTML imprimible (vista previa en navegador,
    Ctrl+P o ajuste de márgenes en vivo). Replica el membrete de membrete.py.
  - html_to_pdf(html)          -> bytes PDF vía Playwright (Chromium headless).

Ventaja sobre reportlab: la maqueta es HTML/CSS, los márgenes se editan con
`@page { margin: ... }` y el preview ES el navegador (WYSIWYG).

Márgenes parametrizables (cm) desde la query del endpoint.
"""
import os
import base64
import html as _html
from backend import membrete as MB

# ── Logo en base64 (data URI) — no depende de rutas estáticas ────────────────
def _logo_data_uri() -> str:
    try:
        with open(MB.LOGO_PATH, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        return f"data:image/png;base64,{b64}"
    except Exception:
        return ""


def _esc(v) -> str:
    return _html.escape("" if v is None else str(v))


# ── Bloque de empresa (4 columnas) ───────────────────────────────────────────
def _company_block_html(ctx: dict) -> str:
    e = MB.EMPRESA
    cuentas = "".join(
        f'<div class="bank">{_esc(n)}: <b>{_esc(v)}</b></div>' for n, v in e["cuentas"]
    )
    contacto = "".join(
        f'<tr><td class="ck">{_esc(k)}</td><td class="cv">{_esc(v)}</td></tr>'
        for k, v in e["contacto"]
    )
    rtn_cli = (
        f'<div class="cli-rtn">RTN: {_esc(ctx.get("rtn_cliente"))}</div>'
        if ctx.get("rtn_cliente") else ""
    )
    logo = _logo_data_uri()
    logo_html = f'<img class="logo" src="{logo}" alt="ConsuConstruct"/>' if logo else ""
    return f"""
    <table class="company">
      <tr>
        <td class="c-left">
          <div class="left-grid">
            {logo_html}
            <div class="obra-info">
              <div class="razon">{_esc(e["razon_social"])}</div>
              <div class="codnom">{_esc(ctx.get("codigo_nombre"))}</div>
              <div class="subt">{_esc(ctx.get("subtitulo"))}</div>
              <div class="cli-row">
                <span class="cli-lbl">CLIENTE:</span>
                <span class="cli-box">{_esc(ctx.get("cliente"))}</span>
              </div>
              {rtn_cli}
              <div class="ubic">{_esc(ctx.get("ubicacion"))}</div>
              <div class="resp">{_esc(e["responsable"])}</div>
              <div class="fecha-cod">
                <span>{_esc(ctx.get("fecha"))}</span>
                <span class="cod">{_esc(ctx.get("codigo_interno"))}</span>
              </div>
            </div>
          </div>
        </td>
        <td class="c-cuentas">
          <div class="cuentas-h">CUENTAS</div>
          <div class="cuentas-rtn">RTN: {_esc(e["rtn"])}</div>
        </td>
        <td class="c-bancos">
          {cuentas}
          <div class="titular">{_esc(e["titular_cuentas"])}</div>
        </td>
        <td class="c-contacto">
          <table class="contacto">{contacto}</table>
        </td>
      </tr>
    </table>
    """


def _disclaimer_html(cols) -> str:
    c = (list(cols) + ["", "", ""])[:3]
    return (
        '<table class="disclaimer"><tr>'
        + "".join(f'<td>{_esc(x)}</td>' for x in c)
        + "</tr></table>"
    )


def _data_table_html(headers, rows, align_right_cols) -> str:
    ths = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    body = []
    for r in rows:
        tds = []
        for ci, v in enumerate(r):
            cls = "num" if ci in align_right_cols else ""
            tds.append(f'<td class="{cls}">{_esc(v)}</td>')
        body.append("<tr>" + "".join(tds) + "</tr>")
    colgroup = ""  # anchos los maneja el CSS auto; descripción flexible
    return f"""
    <table class="data">
      <thead><tr>{ths}</tr></thead>
      <tbody>{''.join(body)}</tbody>
    </table>
    """


# ── Documento completo ───────────────────────────────────────────────────────
def render_document_html(ctx, headers, rows, align_right_cols=(), disclaimer=None,
                         margins_cm=None, with_toolbar=False, report="presupuesto",
                         pid="") -> str:
    """HTML imprimible. margins_cm = dict(top,right,bottom,left) en cm."""
    m = {"top": 1.2, "right": 1.2, "bottom": 1.4, "left": 1.2}
    if margins_cm:
        m.update({k: float(v) for k, v in margins_cm.items() if v is not None})

    titulo = ctx.get("titulo") or ctx.get("titulo_proyecto", "")
    disc_html = _disclaimer_html(disclaimer) if disclaimer else ""
    company = _company_block_html(ctx)
    table = _data_table_html(headers, rows, align_right_cols)

    # Barra de controles (solo pantalla): editar márgenes + descargar
    toolbar = ""
    if with_toolbar:
        toolbar = f"""
        <div class="toolbar no-print">
          <span class="tb-title">Vista previa PDF — ajustá márgenes y descargá</span>
          <label>Sup <input id="m-top" type="number" step="0.1" value="{m['top']}"></label>
          <label>Der <input id="m-right" type="number" step="0.1" value="{m['right']}"></label>
          <label>Inf <input id="m-bottom" type="number" step="0.1" value="{m['bottom']}"></label>
          <label>Izq <input id="m-left" type="number" step="0.1" value="{m['left']}"></label>
          <span class="tb-unit">cm</span>
          <button onclick="aplicar()">Aplicar</button>
          <button class="primary" onclick="descargar()">⬇ Descargar PDF</button>
          <span class="tb-hint">o usá Ctrl+P → Guardar como PDF</span>
        </div>
        <script>
          function qs(){{
            return new URLSearchParams(location.search);
          }}
          function aplicar(){{
            const q = qs();
            q.set('mt', document.getElementById('m-top').value);
            q.set('mr', document.getElementById('m-right').value);
            q.set('mb', document.getElementById('m-bottom').value);
            q.set('ml', document.getElementById('m-left').value);
            location.search = q.toString();
          }}
          function descargar(){{
            const q = qs();
            q.set('mt', document.getElementById('m-top').value);
            q.set('mr', document.getElementById('m-right').value);
            q.set('mb', document.getElementById('m-bottom').value);
            q.set('ml', document.getElementById('m-left').value);
            window.open('/presupuestos/{pid}/export-pdf-html?' + q.toString(), '_blank');
          }}
        </script>
        """

    return f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8"/>
<title>{_esc(titulo)} — Vista previa</title>
<style>
  @page {{
    size: Letter landscape;
    margin: {m['top']}cm {m['right']}cm {m['bottom']}cm {m['left']}cm;
  }}
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; padding: 0; font-family: Helvetica, Arial, sans-serif;
                color: #1a1a1a; font-size: 8pt; }}
  body {{ background: #525659; }}

  /* Barra de título + pie repetidos en cada página */
  .titlebar {{
    position: fixed; top: 0; left: 0; right: 0; height: 22px;
    border: 0.7pt solid #1a1a1a; display: flex; align-items: center;
    justify-content: center; font-weight: bold; font-size: 11pt; background: #fff;
  }}
  .pie {{
    position: fixed; bottom: 0; left: 0; right: 0; height: 16px;
    display: flex; align-items: center; justify-content: center;
  }}
  .pie .marca {{ background: #5e5e5e; color: #fff; font-weight: bold; font-size: 8.5pt;
                 padding: 1px 26px; }}
  .pie .pageno {{ position: absolute; right: 0; background: #ffd600; color: #1a1a1a;
                  font-weight: bold; font-size: 9pt; padding: 1px 8px; }}
  .pie .pageno::after {{ content: counter(page) " / " counter(pages); }}

  .content {{ padding-top: 30px; padding-bottom: 24px; }}

  /* Bloque empresa */
  table.company {{ width: 100%; border-collapse: collapse; margin-bottom: 4px; }}
  table.company > tr > td {{ vertical-align: top; padding: 2px; }}
  .c-left {{ width: 46%; }}
  .c-cuentas {{ width: 15%; text-align: center; }}
  .c-bancos {{ width: 18%; }}
  .c-contacto {{ width: 21%; }}
  .left-grid {{ display: flex; gap: 6px; }}
  .logo {{ width: 64px; height: 64px; flex: 0 0 64px; object-fit: contain; }}
  .obra-info {{ flex: 1; }}
  .razon {{ font-size: 9pt; }}
  .codnom {{ font-size: 8pt; }}
  .subt {{ font-size: 9pt; font-weight: bold; text-align: center; margin: 2px 0; }}
  .cli-row {{ display: flex; align-items: center; gap: 4px; margin-top: 2px; }}
  .cli-lbl {{ font-size: 7.5pt; }}
  .cli-box {{ border: 0.5pt solid #1a1a1a; padding: 1px 6px; font-weight: bold; font-size: 8pt; flex: 1; }}
  .cli-rtn, .ubic, .resp {{ font-size: 7pt; }}
  .fecha-cod {{ display: flex; gap: 24px; margin-top: 3px; font-weight: bold; font-size: 8pt; }}
  .cuentas-h {{ font-weight: bold; font-size: 8pt; }}
  .cuentas-rtn {{ font-weight: bold; font-size: 8pt; margin-top: 2px; }}
  .bank {{ font-size: 8pt; font-weight: bold; margin-bottom: 2px; }}
  .titular {{ font-size: 7pt; margin-top: 2px; }}
  table.contacto {{ border-collapse: collapse; width: 100%; }}
  table.contacto td {{ border: 0.5pt solid #222; padding: 1px 4px; font-size: 7.5pt; font-weight: bold; }}
  table.contacto .ck {{ width: 38%; }}
  table.contacto .cv {{ color: #1f6fb7; text-align: center; }}

  /* Disclaimer */
  table.disclaimer {{ width: 100%; border-collapse: collapse; margin-bottom: 4px;
                      border: 0.5pt solid #1a1a1a; }}
  table.disclaimer td {{ border-right: 0.5pt solid #1a1a1a; padding: 3px 4px;
                         font-size: 6pt; vertical-align: top; width: 33.33%; }}
  table.disclaimer td:last-child {{ border-right: none; }}

  /* Tabla de datos */
  table.data {{ width: 100%; border-collapse: collapse; }}
  table.data th {{ background: #ffd600; color: #1a1a1a; font-weight: bold;
                   font-size: 8pt; text-align: center; border: 0.4pt solid #ccc; padding: 2px 3px; }}
  table.data td {{ border: 0.4pt solid #ccc; font-size: 7.5pt; padding: 2px 3px;
                   vertical-align: middle; }}
  table.data td.num {{ text-align: center; }}
  table.data tbody tr:nth-child(even) {{ background: #f7f7f7; }}
  table.data thead {{ display: table-header-group; }}  /* repite encabezado por página */
  table.data tr {{ page-break-inside: avoid; }}

  /* Toolbar (pantalla) y simulación de hoja */
  .toolbar {{ position: sticky; top: 0; z-index: 10; background: #1f1f1f; color: #eee;
              display: flex; align-items: center; gap: 10px; padding: 8px 14px;
              font-size: 12px; flex-wrap: wrap; }}
  .toolbar .tb-title {{ font-weight: 700; }}
  .toolbar label {{ display: flex; align-items: center; gap: 3px; }}
  .toolbar input {{ width: 52px; padding: 2px 4px; }}
  .toolbar button {{ padding: 3px 10px; cursor: pointer; }}
  .toolbar button.primary {{ background: #ffd600; border: none; font-weight: 700; }}
  .toolbar .tb-hint {{ color: #aaa; }}
  @media screen {{
    .page {{ background: #fff; width: 27.94cm; min-height: 21.59cm;
             margin: 16px auto; padding: {m['top']}cm {m['right']}cm {m['bottom']}cm {m['left']}cm;
             box-shadow: 0 0 8px rgba(0,0,0,.5); position: relative; }}
    .titlebar, .pie {{ position: static; }}
    .pie .pageno::after {{ content: "1 / 1"; }}
  }}
  @media print {{
    .no-print {{ display: none !important; }}
    body {{ background: #fff; }}
    .page {{ width: auto; min-height: auto; margin: 0; padding: 0; box-shadow: none; }}
  }}
</style></head>
<body>
  {toolbar}
  <div class="page">
    <div class="titlebar">{_esc(titulo)}</div>
    <div class="pie"><span class="marca">CONSUCONSTRUCT.COM</span><span class="pageno"></span></div>
    <div class="content">
      {company}
      {disc_html}
      {table}
    </div>
  </div>
</body></html>"""


# ── HTML -> PDF (Playwright Chromium) ─────────────────────────────────────────
def html_to_pdf(html: str) -> bytes:
    """Renderiza el HTML a PDF respetando @page (margins/size del CSS)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page()
        page.set_content(html, wait_until="networkidle")
        pdf = page.pdf(print_background=True, prefer_css_page_size=True)
        browser.close()
    return pdf
