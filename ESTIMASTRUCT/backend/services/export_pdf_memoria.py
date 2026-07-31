# -*- coding: utf-8 -*-
"""
Prorrateo bancario — motor PURO + memoria narrada (2026-07-31).

Módulo ciego C-03 de `docs/auditoria_formulas_mapa_estructura.md` — **riesgo
ALTO**: es el único cálculo del sistema cuyo resultado sale del taller y llega a
un tercero (el banco) como documento formal, y hoy el factor que multiplica cada
precio unitario no aparece en ninguna parte del PDF.

QUÉ HACÍA (y sigue haciendo — este módulo NO cambia el número, lo expone)
------------------------------------------------------------------------
`routers/export_pdf.py::_export_pdf_banco` (líneas ~305-353):

    total_real  = Σ partida.total                       (con sobrecosto aplicado)
    factor      = valor_banco / total_real
    pu_banco    = partida.precio_unitario × factor
    total_banco = partida.total × factor
    fila TOTAL  = valor_banco EXACTO (forzado, no Σ de las filas redondeadas)
    Gantt       + BUFFER_CONTRATIEMPOS_DIAS = 26 días activos al final

Tres cosas que el PDF no dice y esta memoria sí:

1. **El factor.** El banco ve precios unitarios que no son los del presupuesto
   real. Si factor ≠ 1 el documento está escalado y nadie puede reproducirlo.
2. **El residuo de redondeo.** La fila TOTAL se fuerza a `valor_banco`, pero la
   suma de las filas ya redondeadas a 2 decimales casi nunca da exactamente eso.
   La diferencia (residuo) existe siempre; aquí se cuantifica en Lempiras. Es una
   decisión deliberada y defendible (el banco pidió un total exacto), pero tiene
   que estar escrita.
3. **El margen implícito sobre el costo directo.** Si `valor_banco` queda por
   DEBAJO del costo directo de la obra (Σ cantidad·costo_base, sin sobrecosto),
   el documento que va al banco muestra un precio con el que la obra pierde
   plata. Eso hoy no lo avisa nadie. Aquí se calcula y se levanta advertencia.

ADR-003: este módulo NO recalcula la obra. Recibe `total_real` y `costo_directo`
tal como los produce `_costos_obra(p)` (que a su vez usa `services.pricing.calc_base`,
fuente única de costeo) y sólo narra la aritmética del prorrateo. `_export_pdf_banco`
importa `prorrateo_banco()` de aquí, así que el factor del PDF y el factor narrado
son literalmente el mismo cálculo — no dos copias que puedan divergir.

Contrato de salida idéntico a los otros motores narrados:
    {meta, pasos[], constantes[], resultado{}}
"""
from backend.calculo_estructural import _fmt, _ascii_to_latex

# Tolerancia (en unidades monetarias) bajo la cual el residuo de redondeo se
# considera ruido de coma flotante y no un descuadre real.
RESIDUO_TOL = 0.005

# Umbral de |factor − 1| a partir del cual el prorrateo deja de ser un ajuste
# cosmético y pasa a ser una reescritura del presupuesto. 5 % es el criterio
# operativo del Director, no una norma — está aquí para que se pueda discutir en
# UN solo lugar en vez de vivir como un juicio implícito de quien mira el PDF.
FACTOR_ALERTA_PCT = 5.0


def _fmt_money(v) -> str:
    try:
        if v is None:
            return "—"
        return f"{float(v):,.4f}"
    except (TypeError, ValueError):
        return str(v)


def _paso(seccion, simbolo, etiqueta, valor, unidad, formula, sustitucion,
          referencia, descripcion, tipo="intermedio", latex=None) -> dict:
    return {
        "seccion": seccion, "simbolo": simbolo, "etiqueta": etiqueta,
        "valor": valor, "unidad": unidad, "formula": formula,
        "sustitucion": sustitucion, "referencia": referencia,
        "descripcion": descripcion, "tipo": tipo,
        "latex": latex,
        "latex_sub": (_ascii_to_latex(sustitucion) if tipo != "input" else None),
    }


LATEX_BY_FORMULA_BANCO = {
    "factor = valor_banco / total_real":
        r"f = \dfrac{V_{banco}}{T_{real}}",
    "Δ% = (factor − 1) · 100":
        r"\Delta\% = (f-1)\cdot 100",
    "pu_banco = precio_unitario × factor":
        r"PU_{banco} = PU_{real}\cdot f",
    "total_banco = total × factor":
        r"T_{banco,i} = T_{real,i}\cdot f",
    "Σ filas = Σ round(total_i × factor, 2)":
        r"\sum_i \mathrm{round}(T_{real,i}\cdot f,\,2)",
    "residuo = valor_banco − Σ filas":
        r"\varepsilon = V_{banco} - \sum_i T_{banco,i}",
    "margen_implicito = valor_banco / costo_directo − 1":
        r"m = \dfrac{V_{banco}}{C_{directo}} - 1",
    "sobrecosto_real = total_real / costo_directo − 1":
        r"s_{real} = \dfrac{T_{real}}{C_{directo}} - 1",
    "dias_totales = fin_cronograma + buffer":
        r"D_{total} = D_{fin} + D_{buffer}",
}


# ─────────────────────────────────────────────────────────────────────────────
# MOTOR PURO — fuente única. `_export_pdf_banco` lo llama; la memoria lo narra.
# ─────────────────────────────────────────────────────────────────────────────
def prorrateo_banco(total_real: float, valor_banco: float,
                    costo_directo: float = 0.0,
                    totales_partida: list | None = None) -> dict:
    """Factor de prorrateo bancario y sus consecuencias. Aritmética pura, sin BD.

    total_real       Σ partida.total (con sobrecosto) — lo que vale la obra hoy.
    valor_banco      total EXACTO que el banco exige ver en el documento.
    costo_directo    Σ cantidad × costo_base (sin sobrecosto). 0 = no evaluado.
    totales_partida  lista de partida.total (>0) para cuantificar el residuo de
                     redondeo real. None ⇒ no se evalúa el residuo.

    NUNCA lanza por un prorrateo agresivo o con pérdida: devuelve `advertencias`
    para que el Director decida. Sí lanza si los divisores son 0 (mismo criterio
    que el endpoint, que devuelve 400).
    """
    tr = float(total_real or 0)
    vb = float(valor_banco or 0)
    cd = float(costo_directo or 0)
    if tr <= 0:
        raise ValueError("total_real debe ser > 0 (la obra no tiene costos).")
    if vb <= 0:
        raise ValueError("valor_banco debe ser > 0.")

    factor = vb / tr
    delta_pct = (factor - 1.0) * 100.0

    # Residuo de redondeo: las filas del PDF van a 2 decimales; la fila TOTAL se
    # fuerza a valor_banco. La diferencia es real y sale de esta resta.
    suma_filas = None
    residuo = None
    n_filas = None
    if totales_partida is not None:
        n_filas = len(totales_partida)
        suma_filas = round(sum(round(float(t or 0) * factor, 2) for t in totales_partida), 2)
        residuo = round(vb - suma_filas, 4)

    margen_implicito = (vb / cd - 1.0) if cd > 0 else None
    sobrecosto_real = (tr / cd - 1.0) if cd > 0 else None

    advertencias = []
    if abs(delta_pct) > FACTOR_ALERTA_PCT:
        advertencias.append(
            f"El factor de prorrateo mueve cada precio unitario {delta_pct:+.2f}% "
            f"(tope de alerta ±{FACTOR_ALERTA_PCT}%). El PDF que ve el banco NO muestra "
            f"los precios del presupuesto real y no incluye el factor en ninguna parte.")
    if cd > 0 and vb < cd:
        advertencias.append(
            f"valor_banco ({_fmt_money(vb)}) queda POR DEBAJO del costo directo de la obra "
            f"({_fmt_money(cd)}). El documento formal al banco muestra un precio con el que "
            f"la obra pierde {_fmt_money(cd - vb)} antes de cualquier indirecto.")
    elif margen_implicito is not None and margen_implicito < 0.10:
        advertencias.append(
            f"Margen implícito sobre costo directo = {margen_implicito*100:.2f}% "
            "(< 10%). Cubre el costo directo pero deja muy poco para indirectos, "
            "imprevistos e IVA.")
    if residuo is not None and abs(residuo) > RESIDUO_TOL:
        advertencias.append(
            f"La fila TOTAL del PDF se fuerza a {_fmt_money(vb)} pero la suma de las "
            f"{n_filas} filas redondeadas da {_fmt_money(suma_filas)}: residuo de "
            f"{_fmt_money(residuo)}. Es una decisión deliberada (el banco pide un total "
            "exacto), pero el PDF no la declara, así que el documento no cuadra si el "
            "revisor suma las filas a mano.")

    return {
        "total_real": round(tr, 4),
        "valor_banco": round(vb, 4),
        "costo_directo": round(cd, 4) if cd else 0.0,
        "factor": factor,
        "delta_pct": round(delta_pct, 6),
        "n_filas": n_filas,
        "suma_filas": suma_filas,
        "residuo": residuo,
        "margen_implicito": round(margen_implicito, 6) if margen_implicito is not None else None,
        "sobrecosto_real": round(sobrecosto_real, 6) if sobrecosto_real is not None else None,
        "advertencias": advertencias,
        "ok_factor": abs(delta_pct) <= FACTOR_ALERTA_PCT,
        "ok_margen": (margen_implicito is None) or (margen_implicito >= 0.0),
        "ok_residuo": (residuo is None) or (abs(residuo) <= RESIDUO_TOL),
    }


# ─────────────────────────────────────────────────────────────────────────────
# MEMORIA NARRADA — lee el motor puro de arriba, nunca recalcula por su cuenta
# ─────────────────────────────────────────────────────────────────────────────
def memoria_prorrateo_banco(total_real: float, valor_banco: float,
                            costo_directo: float = 0.0,
                            totales_partida: list | None = None,
                            buffer_dias: int = 0, fin_cronograma_dias: int = 0,
                            moneda: str = "L", meta_extra: dict | None = None) -> dict:
    """Narra el prorrateo bancario paso a paso. Devuelve {meta, pasos, constantes,
    resultado}. NO escribe nada, NO persiste `valor_banco` (a diferencia del
    endpoint real de export, que sí lo guarda en el JSON de la obra)."""
    r = prorrateo_banco(total_real, valor_banco, costo_directo, totales_partida)
    P = []
    m = moneda or "L"

    # ── ENTRADAS ─────────────────────────────────────────────────────────────
    P.append(_paso("Base de la obra", "T_real", "Total real del presupuesto", r["total_real"], m,
        "total_real = Σ partida.total",
        f"Σ partida.total = {_fmt_money(r['total_real'])}",
        "routers/export_pdf.py::_costos_obra",
        "Lo que vale la obra HOY según el presupuesto vivo: suma de partida.total, que ya "
        "lleva el sobrecosto aplicado (total = cantidad × PU). Es el denominador del factor.", "input"))
    P.append(_paso("Base de la obra", "C_directo", "Costo directo (sin sobrecosto)", r["costo_directo"], m,
        "costo_directo = Σ cantidad × costo_base",
        f"Σ cantidad · calc_base(mo, ma, matriz) = {_fmt_money(r['costo_directo'])}",
        "services/pricing.calc_base (ADR-003)",
        "MO + materiales + sub-matrices, sin ningún markup. Es el piso: por debajo de esto "
        "la obra pierde plata aunque el papel diga otra cosa.", "input"))
    P.append(_paso("Base de la obra", "V_banco", "Valor exigido por el banco", r["valor_banco"], m,
        "dato de proyecto",
        f"V_banco = {_fmt_money(r['valor_banco'])}",
        "query param valor_banco",
        "Total EXACTO que el banco quiere ver como cierre del documento. Es la entrada que "
        "el usuario teclea en el popup del PDF y que queda persistida por obra en el JSON "
        "de valores_banco.", "input"))

    # ── FACTOR ───────────────────────────────────────────────────────────────
    P.append(_paso("Factor de prorrateo", "f", "Factor de prorrateo", round(r["factor"], 6), "",
        "factor = valor_banco / total_real",
        f"{_fmt_money(r['valor_banco'])} / {_fmt_money(r['total_real'])} = {r['factor']:.6f}",
        "routers/export_pdf.py:322",
        "El número que multiplica TODOS los precios unitarios y todos los totales del PDF "
        "bancario. Hasta 2026-07-31 no aparecía en ninguna parte del documento ni de la UI: "
        "el banco recibía precios escalados sin poder reproducirlos.", "resultado"))
    P.append(_paso("Factor de prorrateo", "Δ%", "Desplazamiento de cada precio", r["delta_pct"], "%",
        "Δ% = (factor − 1) · 100",
        f"({r['factor']:.6f} − 1) · 100 = {r['delta_pct']:+.4f}",
        "derivado",
        "Cuánto se mueve cada precio unitario respecto del presupuesto real. Positivo = el "
        "banco ve precios MÁS altos; negativo = más bajos.", "intermedio"))
    P.append(_paso("Factor de prorrateo", "PU_banco", "Precio unitario prorrateado", None, m,
        "pu_banco = precio_unitario × factor",
        f"PU_banco,i = PU_real,i · {r['factor']:.6f}",
        "routers/export_pdf.py:207",
        "Se aplica fila por fila. La columna 'Precio unitario' del PDF bancario NO es la del "
        "presupuesto: es ésta.", "intermedio"))
    P.append(_paso("Factor de prorrateo", "T_banco,i", "Total de fila prorrateado", None, m,
        "total_banco = total × factor",
        f"T_banco,i = T_real,i · {r['factor']:.6f}",
        "routers/export_pdf.py:208",
        "Ídem para la columna 'Total' de cada partida.", "intermedio"))

    # ── CUADRE / RESIDUO ─────────────────────────────────────────────────────
    if r["residuo"] is not None:
        P.append(_paso("Cuadre del documento", "Σ filas", "Suma de las filas ya redondeadas",
            r["suma_filas"], m,
            "Σ filas = Σ round(total_i × factor, 2)",
            f"Σ de {r['n_filas']} filas a 2 decimales = {_fmt_money(r['suma_filas'])}",
            "derivado del PDF real",
            "Lo que da si el revisor del banco suma a mano la columna Total del PDF.", "intermedio"))
        P.append(_paso("Cuadre del documento", "ε", "Residuo de redondeo", r["residuo"], m,
            "residuo = valor_banco − Σ filas",
            f"{_fmt_money(r['valor_banco'])} − {_fmt_money(r['suma_filas'])} = {_fmt_money(r['residuo'])}",
            "routers/export_pdf.py:330",
            "La fila TOTAL del PDF se FUERZA a valor_banco, no a la suma de las filas. Esta "
            "es la diferencia exacta. Decisión deliberada (el banco pide un total redondo), "
            "pero el documento no la declara.", "intermedio"))
        P.append(_paso("Cuadre del documento", "ok_ε", "Residuo dentro de tolerancia",
            r["ok_residuo"], "",
            "|residuo| ≤ 0.005",
            f"|{_fmt_money(r['residuo'])}| vs {RESIDUO_TOL}",
            "criterio interno",
            "Si falla, la columna Total del PDF no suma el TOTAL impreso. No es un error de "
            "cálculo — es el precio de forzar un total exacto — pero debe verse.", "check"))

    # ── MARGEN ───────────────────────────────────────────────────────────────
    if r["margen_implicito"] is not None:
        P.append(_paso("Margen del documento", "s_real", "Sobrecosto real del presupuesto",
            round(r["sobrecosto_real"] * 100, 4), "%",
            "sobrecosto_real = total_real / costo_directo − 1",
            f"{_fmt_money(r['total_real'])} / {_fmt_money(r['costo_directo'])} − 1 = {r['sobrecosto_real']*100:.4f}",
            "derivado",
            "Markup efectivo que hoy lleva el presupuesto vivo sobre su costo directo.", "intermedio"))
        P.append(_paso("Margen del documento", "m", "Margen implícito del valor bancario",
            round(r["margen_implicito"] * 100, 4), "%",
            "margen_implicito = valor_banco / costo_directo − 1",
            f"{_fmt_money(r['valor_banco'])} / {_fmt_money(r['costo_directo'])} − 1 = {r['margen_implicito']*100:.4f}",
            "derivado",
            "Markup que queda DESPUÉS del prorrateo. Éste es el número que realmente importa: "
            "si es negativo, el papel que va al banco documenta una obra a pérdida.", "resultado"))
        P.append(_paso("Margen del documento", "ok_m", "Margen no negativo", r["ok_margen"], "",
            "valor_banco ≥ costo_directo",
            f"{_fmt_money(r['valor_banco'])} vs {_fmt_money(r['costo_directo'])}",
            "criterio financiero",
            "Piso absoluto: el valor declarado al banco no puede quedar bajo el costo directo.", "check"))

    P.append(_paso("Margen del documento", "ok_f", f"Factor dentro de ±{FACTOR_ALERTA_PCT}%",
        r["ok_factor"], "",
        "|Δ%| ≤ 5",
        f"|{r['delta_pct']:+.4f}| vs {FACTOR_ALERTA_PCT}",
        "criterio operativo (Director)",
        "Arriba de este umbral el prorrateo deja de ser un ajuste de cierre y pasa a ser una "
        "reescritura del presupuesto. No es una norma: es un criterio, y vive en un solo "
        "lugar para poder discutirlo.", "check"))

    # ── CRONOGRAMA BANCARIO ──────────────────────────────────────────────────
    if buffer_dias:
        total_dias = int(fin_cronograma_dias or 0) + int(buffer_dias)
        P.append(_paso("Gantt bancario", "D_buffer", "Buffer de contratiempos", int(buffer_dias),
            "días activos", "constante del módulo",
            f"BUFFER_CONTRATIEMPOS_DIAS = {int(buffer_dias)}",
            "routers/export_pdf.py:29",
            "1 mes laboral (6 días/semana) que se agrega al FINAL del Gantt bancario como "
            "barra de valor L 0. No es costo: es holgura de plazo. El banco la ve como una "
            "actividad más sin saber que es una constante fija, no un cálculo.", "input"))
        P.append(_paso("Gantt bancario", "D_total", "Plazo total declarado al banco",
            total_dias, "días activos",
            "dias_totales = fin_cronograma + buffer",
            f"{int(fin_cronograma_dias or 0)} + {int(buffer_dias)} = {total_dias}",
            "derivado",
            "Días ACTIVOS (calendario de 6 días/semana, domingo no laboral — ver "
            "cronograma.DIAS_SEMANA), no días calendario.", "resultado"))

    for p in P:
        if p["tipo"] != "input" and p["latex"] is None:
            p["latex"] = LATEX_BY_FORMULA_BANCO.get(p["formula"])

    constantes = [
        {"simbolo": "tol_ε", "latex": r"\varepsilon_{tol} = 0.005", "valor": RESIDUO_TOL, "unidad": moneda,
         "desc": "Tolerancia del residuo de redondeo: por debajo es ruido de coma flotante, por encima es descuadre real del documento."},
        {"simbolo": "Δ%_max", "latex": r"\Delta\%_{max} = 5", "valor": FACTOR_ALERTA_PCT, "unidad": "%",
         "desc": "Umbral de alerta del factor de prorrateo. Criterio operativo del Director, no norma."},
    ]

    meta = {
        "dominio": "export_pdf_banco",
        "norma": "—  (decisión comercial, no normativa)",
        "riesgo": "ALTO — documento formal que sale al banco",
        "cumple_normativa": bool(r["ok_factor"] and r["ok_margen"] and r["ok_residuo"]),
        "advertencias": r["advertencias"],
        "nota_norma": ("El prorrateo bancario no responde a ninguna norma técnica: es una "
                       "decisión comercial. Precisamente por eso tiene que estar narrado — no "
                       "hay un código al cual apelar si alguien pregunta de dónde salió el número."),
        "pendiente_aprobacion_director": True,
    }
    if meta_extra:
        meta.update(meta_extra)
    return {"meta": meta, "pasos": P, "constantes": constantes, "resultado": r}
