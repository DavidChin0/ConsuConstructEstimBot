# -*- coding: utf-8 -*-
"""
Predimensionamiento de secciones — memoria narrada (2026-07-31).

Módulo ciego C-09b de `docs/auditoria_formulas_mapa_estructura.md` — riesgo BAJO
y el más barato de narrar: `calculo_estructural.predimensionar()` ya es una
función PURA, ya tiene las fórmulas escritas en su docstring y ya devuelve
`regla_usada` + `notas`. Lo único que le faltaba era el formato `_paso` para
entrar a la Hoja de Auditoría como cualquier otro cálculo.

LO QUE SÍ VALE LA PENA DECIR
----------------------------
Las dos reglas son heurísticas del despacho, NO normativas:

  COLUMNA:  lado_min = niveles · 10 · 0.8   →  ↑ múltiplo de 5 cm
  VIGA:     h = (luz_libre − 2·b_apoyo)/10  →  ↑ múltiplo de 5 cm ; b ≈ h/2 (mín 20)

La de viga es una lectura del criterio clásico L/10 aplicado a la luz LIBRE (de
cara a cara de apoyo, no entre ejes) — más conservador que el L/12 a L/16 que se
suele citar para vigas continuas. La de columna (8 cm de lado por nivel) es una
regla de pulgar de edificación baja en Honduras, sin respaldo en ACI 318-19: la
norma no predimensiona, verifica. Escribir esto es el aporte real de la
narración — el resultado numérico nunca estuvo en duda, su PROCEDENCIA sí.

ADR-003: no hay motor nuevo. Se llama `predimensionar()` y se narra su salida.

Contrato de salida:  {meta, pasos[], constantes[], resultado{}}
"""
from backend.calculo_estructural import (
    predimensionar, RECUB_DEFAULT, _fmt, _ascii_to_latex,
)

FACTOR_COLUMNA = 0.8     # niveles · 10 · 0.8  → 8 cm de lado por nivel
MULTIPLO_CM = 5          # redondeo constructivo (formaleta)
B_MIN_VIGA_CM = 20       # ancho mínimo de viga
DIVISOR_VIGA = 10        # h = luz_libre / 10


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


LATEX_BY_FORMULA_PREDIM = {
    "lado_min = niveles · 10 · 0.8":
        r"a_{min} = n\cdot 10\cdot 0.8",
    "lado = ceil5(lado_min)":
        r"a = 5\left\lceil \dfrac{a_{min}}{5} \right\rceil",
    "h_prop = (luz_libre − 2·b_apoyo)/10":
        r"h_{prop} = \dfrac{L_{libre} - 2 b_{apoyo}}{10}",
    "h = ceil5(h_prop)":
        r"h = 5\left\lceil \dfrac{h_{prop}}{5} \right\rceil",
    "b = max(ceil5(h/2), 20)":
        r"b = \max\left(5\left\lceil \dfrac{h}{10} \right\rceil,\ 20\right)",
    "d = h − recubrimiento":
        r"d = h - rec",
    "L/h = luz_libre / h":
        r"\dfrac{L}{h}",
}


# ─────────────────────────────────────────────────────────────────────────────
# MEMORIA NARRADA — el motor es calculo_estructural.predimensionar
# ─────────────────────────────────────────────────────────────────────────────
def memoria_predimensionar(tipo: str = "VIGA", niveles: int = 1,
                           luz_libre_cm: float = 0.0, b_apoyo_cm: float = 0.0,
                           recubrimiento_cm: float = RECUB_DEFAULT,
                           meta_extra: dict | None = None) -> dict:
    """Narra el predimensionamiento. Devuelve {meta, pasos, constantes, resultado}."""
    r = predimensionar(tipo, niveles, luz_libre_cm, b_apoyo_cm, recubrimiento_cm)
    es_col = r["tipo"] == "COLUMNA"
    rec = float(recubrimiento_cm or RECUB_DEFAULT)
    P = []
    advertencias = []

    P.append(_paso("Entrada", "tipo", "Elemento a predimensionar", r["tipo"], "",
        "dato de proyecto", f"tipo = {r['tipo']}", "—",
        "COLUMNA y VIGA usan reglas distintas y sin relación entre sí.", "input"))

    if es_col:
        n = max(int(niveles or 1), 1)
        lado_min = r["lado_min_cm"]
        P.append(_paso("Entrada", "n", "Niveles que soporta la columna", n, "niveles",
            "dato de proyecto", f"n = {n}", "—",
            "Número de pisos que carga la columna, contando desde arriba.", "input"))
        P.append(_paso("Columna", "a_min", "Lado mínimo antes de redondear", lado_min, "cm",
            "lado_min = niveles · 10 · 0.8",
            f"{n} · 10 · {FACTOR_COLUMNA} = {_fmt(lado_min)}",
            "regla de pulgard del despacho (NO ACI)",
            "8 cm de lado por nivel. Es una regla de edificación baja para Honduras, "
            "confirmada por el Director — ACI 318-19 no predimensiona, verifica. Sirve para "
            "arrancar el modelo, NO sustituye la verificación de §22.4 (Pn máx) ni la de "
            "esbeltez §6.2.5.", "intermedio"))
        P.append(_paso("Columna", "a", "Lado adoptado", r["b_cm"], "cm",
            "lado = ceil5(lado_min)",
            f"↑múltiplo de 5 ≥ {_fmt(lado_min)} = {int(r['b_cm'])}",
            "constructibilidad (formaleta)",
            "Redondeo hacia arriba a múltiplo de 5 cm: la formaleta viene en esos pasos. "
            "Sección cuadrada b = h.", "resultado"))
        if r["b_cm"] < 25:
            advertencias.append(
                f"Lado adoptado {int(r['b_cm'])} cm. ACI 318-19 §18.7.2.1 exige, para columnas "
                "de pórticos especiales resistentes a momento (zona sísmica alta — que es el "
                "caso de Honduras), dimensión mínima de 30 cm. Esta regla de predimensionamiento "
                "NO lo contempla: verificar antes de modelar.")
    else:
        luz = float(luz_libre_cm or 0)
        ba = float(b_apoyo_cm or 0)
        P.append(_paso("Entrada", "L_libre", "Luz libre entre apoyos", luz, "cm",
            "dato de proyecto", f"L_libre = {_fmt(luz)}", "—",
            "Luz LIBRE (cara a cara de apoyo), no entre ejes. La distinción importa: usar la "
            "luz entre ejes engorda la viga.", "input"))
        P.append(_paso("Entrada", "b_apoyo", "Ancho de apoyo", ba, "cm",
            "dato de proyecto", f"b_apoyo = {_fmt(ba)}", "—",
            "Ancho de la columna o muro donde se apoya la viga, en cada extremo.", "input"))
        P.append(_paso("Viga", "h_prop", "Peralte propuesto", r["h_prop_cm"], "cm",
            "h_prop = (luz_libre − 2·b_apoyo)/10",
            f"({_fmt(luz)} − 2·{_fmt(ba)}) / {DIVISOR_VIGA} = {_fmt(r['h_prop_cm'])}",
            "criterio L/10 sobre luz libre (heurística del despacho)",
            "Lectura del criterio clásico L/10. Más conservador que el L/12–L/16 habitual "
            "para vigas continuas; ACI 318-19 Tabla 9.3.1.1 da L/16 para viga simplemente "
            "apoyada como peralte mínimo SIN verificar deflexión — esta regla queda del lado "
            "seguro respecto de eso.", "intermedio"))
        P.append(_paso("Viga", "h", "Peralte adoptado", r["h_cm"], "cm",
            "h = ceil5(h_prop)",
            f"↑múltiplo de 5 ≥ {_fmt(r['h_prop_cm'])} = {int(r['h_cm'])}",
            "constructibilidad (formaleta)",
            "Redondeo hacia arriba a múltiplo de 5 cm.", "resultado"))
        P.append(_paso("Viga", "b", "Base adoptada", r["b_cm"], "cm",
            "b = max(ceil5(h/2), 20)",
            f"max(↑5({_fmt(r['h_cm'])}/2), {B_MIN_VIGA_CM}) = {int(r['b_cm'])}",
            "proporción b ≈ h/2 + mínimo constructivo",
            "Relación de esbeltez de sección b ≈ h/2, con piso de 20 cm: por debajo no cabe el "
            "armado ni el vibrador. ACI 318-19 §9.2.1 no fija un mínimo absoluto de base para "
            "viga no sísmica; §18.6.2.1 sí pide 25 cm en pórticos especiales.", "resultado"))
        if r["h_cm"] and luz > 0:
            rel = luz / r["h_cm"]
            P.append(_paso("Viga", "L/h", "Relación luz/peralte", round(rel, 2), "",
                "L/h = luz_libre / h",
                f"{_fmt(luz)} / {int(r['h_cm'])} = {_fmt(rel, 2)}",
                "ACI 318-19 Tabla 9.3.1.1 (referencia)",
                "Indicador de control. Por encima de ~16 conviene verificar deflexión "
                "explícitamente; por debajo de ~10 la viga es peraltada y podría requerir "
                "tratamiento de viga-pared (§9.9).", "check"))
            if rel > 16:
                advertencias.append(
                    f"L/h = {rel:.1f} > 16. El peralte queda por debajo del mínimo de "
                    "ACI 318-19 Tabla 9.3.1.1 para no verificar deflexión: hay que calcular "
                    "deflexión explícitamente.")
        if r["b_cm"] and r["b_cm"] < 25:
            advertencias.append(
                f"Base {int(r['b_cm'])} cm. Para pórtico especial resistente a momento "
                "(ACI 318-19 §18.6.2.1) el mínimo es 25 cm. Esta regla no lo contempla.")

    P.append(_paso("Peralte efectivo", "rec", "Recubrimiento libre", rec, "cm",
        "dato de proyecto", f"rec = {_fmt(rec)}",
        "ACI 318-19 §20.5.1.3",
        "Recubrimiento libre al refuerzo. Default 4 cm (concreto no expuesto, colado en obra).",
        "input"))
    P.append(_paso("Peralte efectivo", "d", "Peralte efectivo", r["d_cm"], "cm",
        "d = h − recubrimiento",
        f"{int(r['h_cm'])} − {_fmt(rec)} = {_fmt(r['d_cm'])}",
        "ACI 318-19 §2 (definición de d)",
        "Aproximación: el d riguroso descuenta también el estribo y medio diámetro de la "
        "barra longitudinal. Para predimensionar es suficiente; para diseñar, el motor de "
        "cálculo usa el d real.", "resultado"))

    P.append(_paso("Verificación", "ok_regla", "Predimensionamiento sin banderas",
        not advertencias, "",
        "sin advertencias sísmicas ni de deflexión",
        f"{len(advertencias)} advertencia(s)",
        "auditoría de fórmulas",
        "Estas reglas son heurísticas de arranque, no verificación. El check falla cuando el "
        "resultado choca con un mínimo de ACI 318-19 que la regla no conoce.", "check"))

    for p in P:
        if p["tipo"] != "input" and p["latex"] is None:
            p["latex"] = LATEX_BY_FORMULA_PREDIM.get(p["formula"])

    constantes = [
        {"simbolo": "k_col", "latex": r"k_{col} = 0.8", "valor": FACTOR_COLUMNA, "unidad": "",
         "desc": "Factor de la regla de columna: niveles · 10 · 0.8 = 8 cm de lado por nivel. Heurística del despacho, no ACI."},
        {"simbolo": "múltiplo", "latex": r"\Delta = 5\ \text{cm}", "valor": MULTIPLO_CM, "unidad": "cm",
         "desc": "Paso de redondeo constructivo (formaleta). Siempre hacia arriba."},
        {"simbolo": "b_min", "latex": r"b_{min} = 20\ \text{cm}", "valor": B_MIN_VIGA_CM, "unidad": "cm",
         "desc": "Base mínima de viga para que quepa el armado y el vibrador."},
        {"simbolo": "rec", "latex": r"rec = 4\ \text{cm}", "valor": RECUB_DEFAULT, "unidad": "cm",
         "desc": "Recubrimiento libre por defecto (ACI 318-19 §20.5.1.3, concreto no expuesto)."},
    ]

    meta = {
        "dominio": "predimensionamiento",
        "norma": "— heurística del despacho; ACI 318-19 citada sólo como referencia de control",
        "riesgo": "BAJO — es un punto de partida, el diseño real lo verifica después",
        "regla_usada": r["regla_usada"],
        "notas_motor": r["notas"],
        "cumple_normativa": not advertencias,
        "advertencias": advertencias,
        "nota_norma": ("ACI 318-19 no predimensiona: verifica. Estas dos reglas son criterio "
                       "del despacho, confirmadas por el Director, para arrancar un modelo. "
                       "Su valor no está en discusión — lo que faltaba era que estuviera "
                       "ESCRITO que no son norma, para que nadie las defienda como si lo fueran."),
    }
    if meta_extra:
        meta.update(meta_extra)
    return {"meta": meta, "pasos": P, "constantes": constantes, "resultado": r}
