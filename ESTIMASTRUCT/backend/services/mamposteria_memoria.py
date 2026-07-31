# -*- coding: utf-8 -*-
"""
Mampostería reforzada — motor de takeoff PURO + memoria narrada (2026-07-27).

Reemplaza las dos constantes mágicas que vivían inline en
`routers/diseno_estructural.py::crear_mamposteria` (módulo #3 de la lista de
"10 módulos ciegos" de `docs/auditoria_formulas_mapa_estructura.md`):

    ACERO_KG_M2    = 3.5    # kg/m² approx   ← sin fórmula, sin norma
    CONCRETO_M3_M2 = 0.023  # m³/m² approx   ← sin fórmula, sin norma

AUDITORÍA ARITMÉTICA DE LOS VALORES VIEJOS (verificada, no asumida)
-------------------------------------------------------------------
1) ACERO — el comentario decía "1 varilla Ø1/2\" c/0.60m" (vertical solo):
       peso #4 = π/4·(1.27 cm)² · 10⁻⁴ · 7850 = 0.9944 kg/m
       kg/m²   = 0.9944 / 0.60 = 1.6574 kg/m²
   El valor 3.5 es 2.11× eso → +111.2% de sobreestimación RESPECTO A SU PROPIO
   COMENTARIO. El 3.5 sí se aproxima al refuerzo en AMBAS direcciones
   (vertical + horizontal, #4 @ 0.60 c/u = 3.3147 kg/m², desviación +5.6%),
   que es lo que un muro reforzado en zona sísmica realmente lleva. Es decir:
   el número era defendible pero la etiqueta de la partida ("Acero vertical
   mampostería") y el comentario eran falsos. Aquí se calculan las dos
   direcciones EXPLÍCITAMENTE y la partida se renombra.

2) CONCRETO DE RELLENO — el comentario decía "celdas cada 0.20m, secc ≈15×15cm":
       área de celda = 0.15 × 0.15 = 0.0225 m²
       celdas por metro de longitud @0.20 m = 1/0.20 = 5
       m³/m² real (por m² de muro, largo × alto) = 0.0225 · 5 = 0.1125 m³/m²
   El valor 0.023 ≈ 0.0225 = el área de UNA celda, SIN dividir por el
   espaciamiento. Es un error dimensional: se usó m² (área de sección) como si
   fuera m³/m². Contra su propio comentario el error es −79.6%.
   Contra el default nuevo, defendible (relleno PARCIAL: sólo las celdas que
   llevan varilla, s = 0.60 m → 0.0375 m³/m²) el error viejo es −38.7%.

NORMA APLICABLE — nota de nomenclatura (importante)
----------------------------------------------------
ACI 318 **no cubre mampostería**; tiene un código hermano. La referencia
correcta es **TMS 402 "Building Code Requirements for Masonry Structures"**.
Histórico del nombre: hasta la edición 2013 se publicaba como el estándar
conjunto **TMS 402/ACI 530/ASCE 5** (comité MSJC). A finales de 2013 ACI y ASCE
cedieron sus derechos a The Masonry Society; desde la edición 2016 el documento
se designa sólo **TMS 402-16 / TMS 402-22**. Por eso: citar "ACI 530" es válido
sólo para ediciones ≤2013, y citar "ACI 318" para mampostería es un error.

Requisitos que fijan los defaults de este módulo — muro de cortante de
mampostería ESPECIAL reforzada, TMS 402-16 §7.3.2.6 (mismos números que adopta
el IBC/IRC §R606.12.3.2):
    · Σ(ρ_vertical + ρ_horizontal) ≥ 0.0020 · Ag
    · ρ en CADA dirección          ≥ 0.0007 · Ag
    · espaciamiento máximo del refuerzo ≤ 48 in = 1.219 m
    · TMS 402 §6.1.4.4: todo refuerzo debe quedar embebido en grout → las
      celdas rellenas son, como mínimo, las celdas reforzadas (por eso el
      default de `s_celda_m` es el propio espaciamiento vertical del refuerzo).

CHOC-08 (Código Hondureño de Construcción, 2008) — HONESTIDAD SOBRE LA FUENTE:
el CHOC-08 tiene un capítulo de Estructuras de Mampostería, y Honduras es zona
sísmica activa (este repo ya implementa el Cap. 1 sísmico en
`calculo_sismico_choc08.py`, de estructura Z/S/I/Rw/C derivada de UBC — ver
tabla de suelos y zonas ahí). NO se pudo verificar el número de artículo ni el
valor numérico exacto de la cuantía mínima de mampostería del CHOC-08 contra el
documento oficial en esta sesión. Por lo tanto los VALORES numéricos de este
módulo se anclan en TMS 402-16 §7.3.2.6 (verificado) y NO se le atribuye a
CHOC-08 una cifra que no se comprobó. Pendiente para el Director: confirmar el
Cap. de mampostería del CHOC-08 y, si difiere, ajustar RHO_MIN_* aquí (un solo
lugar, ya no hay constantes regadas).

Contrato de salida idéntico a los otros 6 motores narrados:
    {meta, pasos[], constantes[], resultado{}}
    paso = {seccion, simbolo, etiqueta, valor, unidad, formula, sustitucion,
            referencia, descripcion, tipo, latex, latex_sub}
"""
import math

from backend.calculo_estructural import DENSIDAD_ACERO, _fmt, _ascii_to_latex

# ── Diámetros nominales ASTM A615 (designación imperial → mm) ────────────────
# NO es una tabla de pesos nueva: sólo diámetros. El peso se DERIVA con
# DENSIDAD_ACERO (7850 kg/m³) importada de calculo_estructural.py, que es la
# misma constante y el mismo método (As·10⁻⁴·L·γs) que usan takeoff_viga y
# takeoff_columna. Derivar así reproduce el peso nominal ASTM A615 con <0.1%
# de error (#3 0.5594 vs 0.560 · #4 0.9944 vs 0.994 · #5 1.5538 vs 1.552 ·
# #6 2.2374 vs 2.235), así que no hay dos fuentes de verdad en el repo.
BARRAS_DB_MM = {
    "#2": 6.350, "#3": 9.525, "#4": 12.700, "#5": 15.875,
    "#6": 19.050, "#7": 22.225, "#8": 25.400,
}

# TMS 402-16 §7.3.2.6 — muro de cortante de mampostería especial reforzada
RHO_MIN_TOTAL = 0.0020   # Σ(ρv + ρh) mínimo sobre área bruta
RHO_MIN_DIR   = 0.0007   # mínimo por dirección
S_MAX_M       = 1.219    # 48 in — espaciamiento máximo del refuerzo

# Geometría del bloque hueco. La celda no puede ser más profunda que el bloque
# menos sus dos paredes de cara (face shells). 2.5 cm es el mínimo de pared de
# cara de bloque de concreto hueco de uso corriente (ASTM C90 pide 25 mm para
# unidades de 20 cm), así que celda_ancho = espesor − 2·2.5 es el techo físico,
# no un número inventado.
FACE_SHELL_CM       = 2.5
CELDA_LARGO_CM_DEF  = 15.0   # longitud de celda a lo largo del muro (bloque 40 cm, 2 celdas)


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


LATEX_BY_FORMULA_MAMPO = {
    "Ab = π/4 · db²":
        r"A_b = \dfrac{\pi}{4}\,d_b^{\,2}",
    "w = Ab · 10⁻⁴ · γs":
        r"w = A_b\cdot 10^{-4}\cdot \gamma_s",
    "área = longitud × altura":
        r"A_{muro} = L\cdot h",
    "acero_v_kg_m2 = w_v / s_v":
        r"q_{s,v} = \dfrac{w_v}{s_v}",
    "acero_h_kg_m2 = w_h / s_h":
        r"q_{s,h} = \dfrac{w_h}{s_h}",
    "acero_kg_m2 = acero_v_kg_m2 + acero_h_kg_m2":
        r"q_s = q_{s,v} + q_{s,h}",
    "acero_kg = área × acero_kg_m2":
        r"W_s = A_{muro}\cdot q_s",
    "b_celda = t − 2·pared_cara":
        r"b_{celda} = t - 2\,t_{fs}",
    "a_celda = ancho_celda × largo_celda":
        r"a_{celda} = b_{celda}\cdot l_{celda}",
    "concreto_m3_m2 = a_celda / s_celda":
        r"q_g = \dfrac{a_{celda}}{s_{celda}}",
    "concreto_m3 = área × concreto_m3_m2":
        r"V_g = A_{muro}\cdot q_g",
    "ρ = Ab / (s · t)":
        r"\rho = \dfrac{A_b}{s\,t}",
    "ρv + ρh ≥ 0.0020":
        r"\rho_v + \rho_h \ge 0.0020",
    "ρ ≥ 0.0007 (cada dirección)":
        r"\rho \ge 0.0007\quad\text{(cada dirección)}",
    "s ≤ 1.219 m (48 in)":
        r"s \le 1.219\ \text{m}\;(48\ \text{in})",
}


# ─────────────────────────────────────────────────────────────────────────────
# MOTOR PURO — fuente única. `crear_mamposteria` lo llama; la memoria lo narra.
# ─────────────────────────────────────────────────────────────────────────────
def peso_lineal_barra(designacion: str) -> tuple:
    """(db_mm, Ab_cm2, w_kg_m) de una designación ASTM A615. Peso DERIVADO de
    DENSIDAD_ACERO, no tabulado — misma vía que takeoff_viga/takeoff_columna."""
    key = str(designacion or "#4").strip()
    if not key.startswith("#"):
        key = "#" + key.lstrip("#")
    db = BARRAS_DB_MM.get(key)
    if db is None:
        raise ValueError(
            f"Designación de varilla desconocida: {designacion!r}. "
            f"Válidas: {', '.join(sorted(BARRAS_DB_MM))}"
        )
    ab_cm2 = math.pi / 4.0 * (db / 10.0) ** 2
    w_kg_m = ab_cm2 * 1e-4 * DENSIDAD_ACERO
    return db, ab_cm2, w_kg_m


def takeoff_mamposteria(longitud_m: float, altura_m: float, espesor_cm: float,
                        con_refuerzo: bool = False, con_relleno: bool = False,
                        barra_vertical: str = "#4", s_vertical_m: float = 0.60,
                        barra_horizontal: str = "#4", s_horizontal_m: float = 0.60,
                        con_refuerzo_horizontal: bool = True,
                        celda_ancho_cm=None, celda_largo_cm: float = CELDA_LARGO_CM_DEF,
                        s_celda_m=None) -> dict:
    """Takeoff de muro de mampostería reforzada. Aritmética pura, sin BD.

    Defaults (TMS 402-16 §7.3.2.6, ver docstring del módulo):
        #4 @ 0.60 m vertical Y horizontal → ρv = ρh = 0.001056 en muro de 20 cm,
        Σρ = 0.00211 ≥ 0.0020 ✓ y cada dirección ≥ 0.0007 ✓, s ≤ 1.219 m ✓.
        Relleno sólo de celdas reforzadas (s_celda = s_vertical), porque
        TMS 402 §6.1.4.4 exige que el refuerzo quede embebido en grout.

    Returns dict con cantidades + los checks normativos (nunca lanza por no
    cumplir cuantía: reporta `ok_*` y `advertencias` para que el Director vea).
    """
    L = float(longitud_m or 0)
    h = float(altura_m or 0)
    t_cm = float(espesor_cm or 20)
    area_m2 = round(L * h, 4)

    s_v = float(s_vertical_m or 0.60)
    s_h = float(s_horizontal_m or 0.60)
    if s_v <= 0 or s_h <= 0:
        raise ValueError("El espaciamiento del refuerzo debe ser > 0 m.")

    # ── ACERO ────────────────────────────────────────────────────────────────
    db_v, ab_v, w_v = peso_lineal_barra(barra_vertical)
    db_h, ab_h, w_h = peso_lineal_barra(barra_horizontal)

    acero_v_kg_m2 = 0.0
    acero_h_kg_m2 = 0.0
    if con_refuerzo:
        # Por m² de muro (1 m de largo × 1 m de alto):
        #   barras verticales   = 1/s_v barras/m de largo, cada una 1 m de alto
        #   barras horizontales = 1/s_h barras/m de alto,  cada una 1 m de largo
        # → en ambos casos la longitud de barra por m² es 1/s [m/m²].
        acero_v_kg_m2 = w_v / s_v
        acero_h_kg_m2 = (w_h / s_h) if con_refuerzo_horizontal else 0.0
    acero_kg_m2 = acero_v_kg_m2 + acero_h_kg_m2
    acero_kg = round(area_m2 * acero_kg_m2, 2)

    # ── CONCRETO DE RELLENO (grout) ──────────────────────────────────────────
    # Celda: ancho limitado por el espesor menos las dos paredes de cara.
    if celda_ancho_cm is None:
        celda_ancho_cm = max(t_cm - 2.0 * FACE_SHELL_CM, 5.0)
    celda_ancho_cm = float(celda_ancho_cm)
    celda_largo_cm = float(celda_largo_cm or CELDA_LARGO_CM_DEF)
    a_celda_m2 = (celda_ancho_cm / 100.0) * (celda_largo_cm / 100.0)

    # Default: sólo se rellenan las celdas que llevan varilla (TMS 402 §6.1.4.4).
    s_celda = float(s_celda_m) if s_celda_m else s_v
    if s_celda <= 0:
        raise ValueError("El espaciamiento de celdas rellenas debe ser > 0 m.")

    concreto_m3_m2 = (a_celda_m2 / s_celda) if con_relleno else 0.0
    concreto_m3 = round(area_m2 * concreto_m3_m2, 4)

    # ── CHECKS NORMATIVOS — TMS 402-16 §7.3.2.6 ─────────────────────────────
    ag_cm2_por_m = 100.0 * t_cm            # área bruta por metro de muro
    rho_v = (ab_v / s_v) / ag_cm2_por_m if con_refuerzo else 0.0
    rho_h = (ab_h / s_h) / ag_cm2_por_m if (con_refuerzo and con_refuerzo_horizontal) else 0.0
    rho_tot = rho_v + rho_h

    advertencias = []
    ok_rho_total = (not con_refuerzo) or (rho_tot >= RHO_MIN_TOTAL)
    ok_rho_v     = (not con_refuerzo) or (rho_v   >= RHO_MIN_DIR)
    ok_rho_h     = (not con_refuerzo) or (not con_refuerzo_horizontal) or (rho_h >= RHO_MIN_DIR)
    ok_s         = (not con_refuerzo) or (max(s_v, s_h if con_refuerzo_horizontal else 0) <= S_MAX_M)

    if con_refuerzo and not con_refuerzo_horizontal:
        advertencias.append(
            "Sólo refuerzo VERTICAL. TMS 402-16 §7.3.2.6 exige refuerzo en ambas "
            "direcciones para muro de cortante especial reforzada — este takeoff no "
            "cumple el mínimo sísmico si el muro es estructural.")
    if not ok_rho_total:
        advertencias.append(
            f"Σ(ρv+ρh) = {rho_tot:.5f} < {RHO_MIN_TOTAL} (TMS 402-16 §7.3.2.6). "
            f"Con espesor {int(t_cm)} cm hay que cerrar el espaciamiento o subir el diámetro.")
    if not ok_rho_v:
        advertencias.append(f"ρv = {rho_v:.5f} < {RHO_MIN_DIR} por dirección (TMS 402-16 §7.3.2.6).")
    if not ok_rho_h:
        advertencias.append(f"ρh = {rho_h:.5f} < {RHO_MIN_DIR} por dirección (TMS 402-16 §7.3.2.6).")
    if not ok_s:
        advertencias.append(f"Espaciamiento > {S_MAX_M} m (48 in), tope de TMS 402-16 §7.3.2.6.")
    if con_relleno and con_refuerzo and s_celda > s_v + 1e-9:
        advertencias.append(
            f"Celdas rellenas c/{s_celda} m pero varilla vertical c/{s_v} m: habría varilla "
            "sin grout. TMS 402-16 §6.1.4.4 exige el refuerzo embebido en grout.")

    return {
        "area_m2":        area_m2,
        "acero_kg":       acero_kg,
        "acero_kg_m2":    round(acero_kg_m2, 5),
        "acero_v_kg_m2":  round(acero_v_kg_m2, 5),
        "acero_h_kg_m2":  round(acero_h_kg_m2, 5),
        "concreto_m3":    concreto_m3,
        "concreto_m3_m2": round(concreto_m3_m2, 5),
        "params": {
            "espesor_cm": t_cm,
            "barra_vertical": barra_vertical, "db_v_mm": round(db_v, 3),
            "ab_v_cm2": round(ab_v, 4), "w_v_kg_m": round(w_v, 4), "s_vertical_m": s_v,
            "barra_horizontal": barra_horizontal, "db_h_mm": round(db_h, 3),
            "ab_h_cm2": round(ab_h, 4), "w_h_kg_m": round(w_h, 4), "s_horizontal_m": s_h,
            "con_refuerzo_horizontal": bool(con_refuerzo_horizontal),
            "celda_ancho_cm": celda_ancho_cm, "celda_largo_cm": celda_largo_cm,
            "a_celda_m2": round(a_celda_m2, 5), "s_celda_m": s_celda,
        },
        "normativa": {
            "rho_v": round(rho_v, 6), "rho_h": round(rho_h, 6), "rho_total": round(rho_tot, 6),
            "rho_min_total": RHO_MIN_TOTAL, "rho_min_dir": RHO_MIN_DIR, "s_max_m": S_MAX_M,
            "ok_rho_total": ok_rho_total, "ok_rho_v": ok_rho_v, "ok_rho_h": ok_rho_h,
            "ok_s": ok_s, "cumple": bool(ok_rho_total and ok_rho_v and ok_rho_h and ok_s),
            "referencia": "TMS 402-16 §7.3.2.6 (ex TMS 402/ACI 530/ASCE 5 hasta ed. 2013)",
        },
        "advertencias": advertencias,
    }


# ─────────────────────────────────────────────────────────────────────────────
# MEMORIA NARRADA — lee el motor puro de arriba, nunca recalcula por su cuenta
# ─────────────────────────────────────────────────────────────────────────────
def memoria_mamposteria(entrada: dict) -> dict:
    """Narra el takeoff de mampostería. `entrada` = mismos kwargs de
    `takeoff_mamposteria`. Devuelve {meta, pasos, constantes, resultado}."""
    e = dict(entrada or {})
    L   = float(e.get("longitud_m", 0) or 0)
    h   = float(e.get("altura_m", 0) or 0)
    t   = float(e.get("espesor_cm", 20) or 20)
    ref = bool(e.get("con_refuerzo", True))
    rel = bool(e.get("con_relleno", True))

    r  = takeoff_mamposteria(**{**e, "longitud_m": L, "altura_m": h, "espesor_cm": t,
                                "con_refuerzo": ref, "con_relleno": rel})
    pr = r["params"]
    nm = r["normativa"]
    P  = []

    # ── GEOMETRÍA ────────────────────────────────────────────────────────────
    P.append(_paso("Geometría", "L", "Longitud del muro", L, "m", "dato de proyecto",
        f"L = {_fmt(L)}", "takeoff", "Longitud en planta del paño de mampostería.", "input"))
    P.append(_paso("Geometría", "h", "Altura del muro", h, "m", "dato de proyecto",
        f"h = {_fmt(h)}", "takeoff", "Altura del paño (piso a viga corona).", "input"))
    P.append(_paso("Geometría", "t", "Espesor del bloque", t, "cm", "dato de proyecto",
        f"t = {_fmt(t)}", "takeoff",
        "Espesor nominal del bloque hueco. Define el área bruta Ag = 100·t por metro de muro y el ancho máximo de celda.", "input"))
    P.append(_paso("Geometría", "A_muro", "Área de mampostería", r["area_m2"], "m²",
        "área = longitud × altura", f"{_fmt(L)} × {_fmt(h)} = {_fmt(r['area_m2'])}",
        "CSI 04 20 00", "Cantidad que va a la partida de mampostería (m² de muro).", "takeoff"))

    # ── ACERO ────────────────────────────────────────────────────────────────
    P.append(_paso("Acero de refuerzo", "db,v", f"Diámetro varilla vertical ({pr['barra_vertical']})",
        pr["db_v_mm"], "mm", "dato de proyecto", f"db = {_fmt(pr['db_v_mm'])} mm ({pr['barra_vertical']})",
        "ASTM A615", "Diámetro nominal ASTM A615. Default #4 (Ø1/2\"), el mínimo práctico para muro estructural en zona sísmica.", "input"))
    P.append(_paso("Acero de refuerzo", "s_v", "Espaciamiento vertical", pr["s_vertical_m"], "m",
        "dato de proyecto", f"s_v = {_fmt(pr['s_vertical_m'])}", "TMS 402-16 §7.3.2.6",
        "Separación entre varillas verticales. Default 0.60 m: cumple ρ mínima en muro de 15–20 cm y queda muy por debajo del tope de 1.219 m (48 in).", "input"))
    P.append(_paso("Acero de refuerzo", "Ab,v", "Área de la varilla vertical", round(pr["ab_v_cm2"], 4), "cm²",
        "Ab = π/4 · db²", f"π/4 · ({_fmt(pr['db_v_mm']/10)} cm)² = {_fmt(pr['ab_v_cm2'],4)}",
        "ASTM A615", "Área nominal de la sección transversal de la varilla.", "intermedio"))
    P.append(_paso("Acero de refuerzo", "w_v", "Peso lineal de la varilla vertical", round(pr["w_v_kg_m"], 4), "kg/m",
        "w = Ab · 10⁻⁴ · γs", f"{_fmt(pr['ab_v_cm2'],4)} · 10⁻⁴ · {DENSIDAD_ACERO} = {_fmt(pr['w_v_kg_m'],4)}",
        "γs = 7850 kg/m³ (calculo_estructural.DENSIDAD_ACERO)",
        "Peso DERIVADO con la misma densidad y el mismo método (As·10⁻⁴·L·γs) que takeoff_viga/takeoff_columna — no hay una tabla de pesos paralela en el repo. Reproduce el nominal ASTM A615 con <0.1% de error.", "intermedio"))
    P.append(_paso("Acero de refuerzo", "q_s,v", "Acero vertical por m² de muro", r["acero_v_kg_m2"], "kg/m²",
        "acero_v_kg_m2 = w_v / s_v",
        f"{_fmt(pr['w_v_kg_m'],4)} / {_fmt(pr['s_vertical_m'])} = {_fmt(r['acero_v_kg_m2'],4)}",
        "takeoff geométrico",
        "Por cada m² de muro (1 m largo × 1 m alto) hay 1/s_v varillas verticales, cada una de 1 m de desarrollo → longitud de barra = 1/s_v m/m². ANTES: constante fija 3.5 kg/m², que era 2.11× este valor (+111%) pese a que su comentario decía justamente 'vertical #4 @0.60'.", "intermedio"))
    if pr["con_refuerzo_horizontal"]:
        P.append(_paso("Acero de refuerzo", "s_h", "Espaciamiento horizontal", pr["s_horizontal_m"], "m",
            "dato de proyecto", f"s_h = {_fmt(pr['s_horizontal_m'])}", "TMS 402-16 §7.3.2.6",
            "Separación del refuerzo horizontal (viga de amarre / escalerilla). Un muro de cortante especial reforzada NO puede llevar sólo acero vertical.", "input"))
        P.append(_paso("Acero de refuerzo", "q_s,h", "Acero horizontal por m² de muro", r["acero_h_kg_m2"], "kg/m²",
            "acero_h_kg_m2 = w_h / s_h",
            f"{_fmt(pr['w_h_kg_m'],4)} / {_fmt(pr['s_horizontal_m'])} = {_fmt(r['acero_h_kg_m2'],4)}",
            "takeoff geométrico",
            "Simétrico al vertical: 1/s_h varillas por m de altura, cada una de 1 m de largo.", "intermedio"))
    P.append(_paso("Acero de refuerzo", "q_s", "Acero total por m² de muro", r["acero_kg_m2"], "kg/m²",
        "acero_kg_m2 = acero_v_kg_m2 + acero_h_kg_m2",
        f"{_fmt(r['acero_v_kg_m2'],4)} + {_fmt(r['acero_h_kg_m2'],4)} = {_fmt(r['acero_kg_m2'],4)}",
        "TMS 402-16 §7.3.2.6",
        "Suma de ambas direcciones. Con el default (#4 @0.60 c/u) da 3.3147 kg/m²; la constante vieja 3.5 estaba 5.6% arriba de esto — cerca del total, pero la partida se etiquetaba 'Acero vertical', lo cual era falso.", "resultado"))
    P.append(_paso("Acero de refuerzo", "W_s", "Peso total de acero del paño", r["acero_kg"], "kg",
        "acero_kg = área × acero_kg_m2",
        f"{_fmt(r['area_m2'])} × {_fmt(r['acero_kg_m2'],4)} = {_fmt(r['acero_kg'])}",
        "CSI 03 20 00", "Cantidad que va a la partida de acero de refuerzo.", "takeoff"))

    # ── CONCRETO DE RELLENO ──────────────────────────────────────────────────
    P.append(_paso("Concreto de relleno", "b_celda", "Ancho útil de celda", pr["celda_ancho_cm"], "cm",
        "b_celda = t − 2·pared_cara", f"{_fmt(t)} − 2·{FACE_SHELL_CM} = {_fmt(pr['celda_ancho_cm'])}",
        "ASTM C90 (pared de cara ≥25 mm)",
        "La celda no puede ser más profunda que el bloque menos sus dos paredes de cara. Derivado del espesor, no fijo.", "intermedio"))
    P.append(_paso("Concreto de relleno", "l_celda", "Largo de celda", pr["celda_largo_cm"], "cm",
        "dato de proyecto", f"l_celda = {_fmt(pr['celda_largo_cm'])}", "geometría del bloque",
        "Longitud de la celda a lo largo del muro (bloque de 40 cm con 2 celdas).", "input"))
    P.append(_paso("Concreto de relleno", "a_celda", "Área de la celda", pr["a_celda_m2"], "m²",
        "a_celda = ancho_celda × largo_celda",
        f"{_fmt(pr['celda_ancho_cm']/100,3)} × {_fmt(pr['celda_largo_cm']/100,3)} = {_fmt(pr['a_celda_m2'],5)}",
        "geometría del bloque",
        "Sección transversal del grout en UNA celda. ⚠ La constante vieja 0.023 m³/m² era exactamente este número (0.0225 m²): se usó un ÁREA como si fuera un volumen por m², sin dividir por el espaciamiento. Error dimensional.", "intermedio"))
    P.append(_paso("Concreto de relleno", "s_celda", "Espaciamiento de celdas rellenas", pr["s_celda_m"], "m",
        "dato de proyecto", f"s_celda = {_fmt(pr['s_celda_m'])}", "TMS 402-16 §6.1.4.4",
        "Default = espaciamiento del refuerzo vertical: relleno PARCIAL, sólo las celdas con varilla, porque el código exige el refuerzo embebido en grout. Si se rellena todo el muro, poner el paso de celda del bloque (típico 0.20 m).", "input"))
    P.append(_paso("Concreto de relleno", "q_g", "Concreto de relleno por m² de muro", r["concreto_m3_m2"], "m³/m²",
        "concreto_m3_m2 = a_celda / s_celda",
        f"{_fmt(pr['a_celda_m2'],5)} / {_fmt(pr['s_celda_m'])} = {_fmt(r['concreto_m3_m2'],5)}",
        "takeoff geométrico",
        "Por m² de muro hay 1/s_celda celdas por metro de longitud, cada una de 1 m de alto. Con el default (0.60 m) = 0.0375 m³/m²: la constante vieja 0.023 subestimaba en 38.7%. Contra su propio comentario ('celdas c/0.20') la subestimación era 79.6%.", "resultado"))
    P.append(_paso("Concreto de relleno", "V_g", "Volumen total de relleno del paño", r["concreto_m3"], "m³",
        "concreto_m3 = área × concreto_m3_m2",
        f"{_fmt(r['area_m2'])} × {_fmt(r['concreto_m3_m2'],5)} = {_fmt(r['concreto_m3'],4)}",
        "CSI 03 30 00", "Cantidad que va a la partida de concreto de relleno.", "takeoff"))

    # ── VERIFICACIÓN NORMATIVA ───────────────────────────────────────────────
    P.append(_paso("Verificación TMS 402", "ρv", "Cuantía vertical sobre área bruta", nm["rho_v"], "",
        "ρ = Ab / (s · t)",
        f"{_fmt(pr['ab_v_cm2'],4)} / ({_fmt(pr['s_vertical_m'])}·100 · {_fmt(t)}) = {_fmt(nm['rho_v'],6)}",
        "TMS 402-16 §7.3.2.6",
        "Área de acero vertical entre área bruta del muro, por metro de longitud (Ag = 100·t cm²/m).", "intermedio"))
    P.append(_paso("Verificación TMS 402", "ρh", "Cuantía horizontal sobre área bruta", nm["rho_h"], "",
        "ρ = Ab / (s · t)",
        f"{_fmt(pr['ab_h_cm2'],4)} / ({_fmt(pr['s_horizontal_m'])}·100 · {_fmt(t)}) = {_fmt(nm['rho_h'],6)}",
        "TMS 402-16 §7.3.2.6", "Ídem para el refuerzo horizontal.", "intermedio"))
    P.append(_paso("Verificación TMS 402", "Σρ", "Cuantía total ≥ 0.0020", nm["ok_rho_total"], "",
        "ρv + ρh ≥ 0.0020",
        f"{_fmt(nm['rho_v'],6)} + {_fmt(nm['rho_h'],6)} = {_fmt(nm['rho_total'],6)} vs {RHO_MIN_TOTAL}",
        "TMS 402-16 §7.3.2.6",
        "Mínimo sísmico de muro de cortante de mampostería ESPECIAL reforzada. Ojo: con espesor 25 cm el default #4@0.60 en ambas direcciones YA NO alcanza (Σρ=0.00169) — hay que cerrar a 0.50 m o subir a #5.", "check"))
    P.append(_paso("Verificación TMS 402", "ρ_dir", "Cuantía mínima por dirección ≥ 0.0007",
        bool(nm["ok_rho_v"] and nm["ok_rho_h"]), "",
        "ρ ≥ 0.0007 (cada dirección)",
        f"ρv = {_fmt(nm['rho_v'],6)} · ρh = {_fmt(nm['rho_h'],6)} vs {RHO_MIN_DIR}",
        "TMS 402-16 §7.3.2.6",
        "Ninguna dirección puede quedar por debajo de 0.0007 aunque la suma cumpla.", "check"))
    P.append(_paso("Verificación TMS 402", "s_max", "Espaciamiento ≤ 1.219 m (48 in)", nm["ok_s"], "",
        "s ≤ 1.219 m (48 in)",
        f"max(s_v, s_h) = {_fmt(max(pr['s_vertical_m'], pr['s_horizontal_m'] if pr['con_refuerzo_horizontal'] else 0))} vs {S_MAX_M}",
        "TMS 402-16 §7.3.2.6", "Tope absoluto de separación del refuerzo.", "check"))

    for p in P:
        if p["tipo"] != "input" and p["latex"] is None:
            p["latex"] = LATEX_BY_FORMULA_MAMPO.get(p["formula"])

    constantes = [
        {"simbolo": "γs", "latex": r"\gamma_s = 7850", "valor": DENSIDAD_ACERO, "unidad": "kg/m³",
         "desc": "Densidad del acero. Importada de calculo_estructural.DENSIDAD_ACERO — fuente única, la misma que usan los takeoffs de viga y columna."},
        {"simbolo": "ρ_min,tot", "latex": r"\rho_{min,tot} = 0.0020", "valor": RHO_MIN_TOTAL, "unidad": "",
         "desc": "Σ(ρv+ρh) mínima sobre área bruta — TMS 402-16 §7.3.2.6, muro de cortante de mampostería especial reforzada."},
        {"simbolo": "ρ_min,dir", "latex": r"\rho_{min,dir} = 0.0007", "valor": RHO_MIN_DIR, "unidad": "",
         "desc": "Cuantía mínima en CADA dirección — TMS 402-16 §7.3.2.6."},
        {"simbolo": "s_max", "latex": r"s_{max} = 1.219\ \text{m}", "valor": S_MAX_M, "unidad": "m",
         "desc": "Espaciamiento máximo del refuerzo, 48 in — TMS 402-16 §7.3.2.6."},
        {"simbolo": "pared_cara", "latex": r"t_{fs} = 2.5\ \text{cm}", "valor": FACE_SHELL_CM, "unidad": "cm",
         "desc": "Pared de cara del bloque hueco (ASTM C90 ≥25 mm). Fija el ancho útil de celda: b_celda = t − 2·t_fs."},
    ]

    meta = {
        "dominio": "mamposteria",
        "norma": "TMS 402-16 §7.3.2.6 · §6.1.4.4 (ex TMS 402/ACI 530/ASCE 5 hasta ed. 2013)",
        "nota_norma": ("ACI 318 NO cubre mampostería. El código de mampostería es TMS 402 "
                       "(hasta 2013 publicado como el conjunto TMS 402/ACI 530/ASCE 5; desde 2016, "
                       "TMS 402 a secas). CHOC-08 tiene capítulo de mampostería pero su artículo y "
                       "valor numérico no se verificaron contra el documento oficial — los números "
                       "de este módulo se anclan en TMS 402-16."),
        "cumple_normativa": nm["cumple"],
        "advertencias": r["advertencias"],
        "reemplaza": "constantes mágicas 3.5 kg/m² y 0.023 m³/m² (routers/diseno_estructural.py, hasta 2026-07-27)",
    }
    return {"meta": meta, "pasos": P, "constantes": constantes, "resultado": r}
