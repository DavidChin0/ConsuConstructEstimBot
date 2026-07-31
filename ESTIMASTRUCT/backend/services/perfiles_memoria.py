# -*- coding: utf-8 -*-
"""
Propiedades de sección de acero — memoria narrada (2026-07-31).

Módulo ciego C-06 de `docs/auditoria_formulas_mapa_estructura.md` — riesgo MEDIO,
pero es **el gap más traicionero del sistema**: no produce un número visiblemente
malo, sino que invalida en silencio memorias de acero que SÍ se ven perfectamente
narradas.

EL PROBLEMA
-----------
`calculo_miembro_acero` muestra φMn = φ·Fy·Zx paso a paso, con LaTeX, sustitución
numérica y referencia AISC. Impecable. Pero el `Zx` que entra a esa fórmula sale
de `perfiles_acero.props_seccion()`, que tiene **tres rutas de resolución
distintas** y la memoria no dice cuál se usó:

  1. `fuente = "tabla"`     → valores AISC/CISC EXACTOS de TABLA_W, convertidos
                              SI→cm (÷10 longitudes, ÷100 áreas, ÷1e3 módulos,
                              ÷1e4 inercias, ÷1e6 Cw).
  2. `fuente = "derivada"`  → el perfil NO está en TABLA_W: se deriva de tres
                              rectángulos. El propio docstring del módulo admite
                              **~3 % conservador**, y la geometría base de
                              PERFILES_ACERO tiene tf/tw imprecisos (el comentario
                              de TABLA_W advierte que derivar da Zx/ry 25-34 %
                              bajos si se usa esa geometría). Un φMn calculado
                              sobre un Zx derivado NO es el mismo dato que uno
                              sobre tabla, y hasta hoy se veían idénticos.
  3. `fuente = "hss"`       → sección cerrada, fórmulas de perfil I no aplican;
                              props exactas de tubo cuadrado (Ix=Iy, sin LTB).

Esta memoria expone `fuente` y, cuando es "derivada", narra las cinco fórmulas
de derivación con sus números reales para que se vea de dónde salió cada
propiedad.

ADR-003: no hay motor nuevo. Se llama `perfiles_acero.props_seccion()` — el mismo
que usan los dos motores LRFD en producción — y se narra su salida.

Contrato de salida:  {meta, pasos[], constantes[], resultado{}}
"""
from backend.calculo_estructural import _fmt, _ascii_to_latex
from backend.perfiles_acero import (
    props_seccion, PERFILES_ACERO, TABLA_W, _norm_w, _es_hss,
)

# Penalización típica de la vía derivada, según el docstring de props_seccion.
DERIVADA_CONSERVADURISMO_PCT = 3.0

FUENTE_DESC = {
    "tabla": ("TABLA_W — valores AISC/CISC exactos",
              "El perfil está tabulado. Ix, Zx, ry, J, Cw, rts vienen del CISC Handbook / "
              "AISC 16a en SI y sólo se convierten de unidad. Es la vía confiable: el φMn que "
              "se narra aguas abajo está apoyado en datos de norma, no en una aproximación."),
    "derivada": ("DERIVADA de 3 rectángulos — aproximación",
                 "⚠ El perfil NO está en TABLA_W. Las propiedades se derivan tratando la sección "
                 "como dos alas + un alma. El propio módulo admite ~3 % conservador, y advierte "
                 "que la geometría de PERFILES_ACERO tiene tf/tw imprecisos. Toda memoria de "
                 "acero construida sobre estas props hereda esa incertidumbre SIN DECLARARLA."),
    "hss": ("HSS — sección cerrada exacta",
            "Tubo cuadrado: Ix = Iy, sin pandeo lateral-torsional, J de torsión cerrada "
            "(fórmula de Bredt). Las fórmulas de perfil I no aplican y por eso hay una rama "
            "propia. Los valores son exactos para la geometría dada."),
}


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


LATEX_BY_FORMULA_PERFIL = {
    "Ix = bf·d³/12 − (bf−tw)·hw³/12":
        r"I_x = \dfrac{b_f d^3}{12} - \dfrac{(b_f-t_w)h_w^3}{12}",
    "Iy = 2·(tf·bf³/12) + hw·tw³/12":
        r"I_y = 2\dfrac{t_f b_f^3}{12} + \dfrac{h_w t_w^3}{12}",
    "Zx = bf·tf·(d−tf) + tw·hw²/4":
        r"Z_x = b_f t_f (d-t_f) + \dfrac{t_w h_w^2}{4}",
    "Sx = 2·Ix/d":
        r"S_x = \dfrac{2 I_x}{d}",
    "ry = √(Iy/Ag)":
        r"r_y = \sqrt{\dfrac{I_y}{A_g}}",
    "J = (2·bf·tf³ + hw·tw³)/3":
        r"J = \dfrac{2 b_f t_f^3 + h_w t_w^3}{3}",
    "Cw = Iy·ho²/4":
        r"C_w = \dfrac{I_y h_o^2}{4}",
    "rts = √(√(Iy·Cw)/Sx)":
        r"r_{ts} = \sqrt{\dfrac{\sqrt{I_y C_w}}{S_x}}",
    "hw = d − 2·tf":
        r"h_w = d - 2 t_f",
    "I = (b⁴ − bi⁴)/12":
        r"I = \dfrac{b^4 - b_i^4}{12}",
    "Z = (b³ − bi³)/4":
        r"Z = \dfrac{b^3 - b_i^3}{4}",
    "J = 4·Am²·t/(4·(b−t))":
        r"J = \dfrac{4 A_m^2 t}{4(b-t)}",
    "λ = (b − 3t)/t":
        r"\lambda = \dfrac{b-3t}{t}",
    "λ_ala = bf/(2·tf)":
        r"\lambda_{ala} = \dfrac{b_f}{2 t_f}",
    "Mp = Fy · Zx":
        r"M_p = F_y Z_x",
}


def catalogo_perfiles() -> dict:
    """Perfiles disponibles y por qué ruta se resuelve cada uno. Metadata pura."""
    out = []
    for nombre in sorted(PERFILES_ACERO):
        nom = _norm_w(nombre)
        if nom in TABLA_W:
            f = "tabla"
        elif _es_hss(nombre):
            f = "hss"
        else:
            f = "derivada"
        out.append({"perfil": nombre, "fuente": f})
    return {
        "perfiles": out,
        "n_tabla": sum(1 for x in out if x["fuente"] == "tabla"),
        "n_derivada": sum(1 for x in out if x["fuente"] == "derivada"),
        "n_hss": sum(1 for x in out if x["fuente"] == "hss"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# MEMORIA NARRADA — el motor es perfiles_acero.props_seccion, aquí sólo se lee
# ─────────────────────────────────────────────────────────────────────────────
def memoria_props_seccion(perfil_nombre: str, perfil_dict: dict | None = None,
                          fy_kgcm2: float = 3515.0,
                          meta_extra: dict | None = None) -> dict:
    """Narra de dónde salen las propiedades de sección de `perfil_nombre`.

    `perfil_dict` opcional; si no se da, se toma de PERFILES_ACERO (misma vía que
    usan los motores LRFD). `fy_kgcm2` sólo se usa para ilustrar el impacto en Mp
    (A992 Fy=50 ksi = 3515 kgf/cm² por default).
    """
    nombre = (perfil_nombre or "").strip()
    pd = perfil_dict if perfil_dict is not None else PERFILES_ACERO.get(_norm_w(nombre), {})
    r = props_seccion(pd, nombre)

    if not r or (r.get("hss") and "Ag" not in r):
        raise ValueError(
            f"Perfil {nombre!r} sin geometría utilizable. Perfiles conocidos: "
            f"{', '.join(sorted(PERFILES_ACERO)[:12])}…")

    fuente = r.get("fuente", "")
    f_titulo, f_desc = FUENTE_DESC.get(fuente, (fuente, "Ruta de resolución no reconocida."))
    en_tabla = _norm_w(nombre) in TABLA_W
    P = []

    advertencias = []
    if fuente == "derivada":
        advertencias.append(
            f"'{nombre}' NO está en TABLA_W: todas sus propiedades son DERIVADAS de 3 "
            f"rectángulos (~{DERIVADA_CONSERVADURISMO_PCT}% conservador por admisión del propio "
            "módulo). Cualquier memoria de acero que use este perfil muestra φPn/φMn/φVn con "
            "aspecto exacto pero apoyados en una aproximación — y no lo declara. Si el perfil "
            "es de uso frecuente, agregarlo a TABLA_W con valores AISC/CISC.")
        advertencias.append(
            "La geometría base de PERFILES_ACERO tiene tf/tw imprecisos (advertencia explícita "
            "en el comentario de TABLA_W: derivar de ella da Zx/ry 25-34% BAJOS). El error real "
            "puede ser mucho mayor que el 3% nominal.")
    if fuente == "hss":
        advertencias.append(
            "Sección cerrada: no aplica pandeo lateral-torsional (§F2 no gobierna) y Cw = 0. "
            "Si aguas abajo alguna memoria narra LTB para este perfil, está narrando un estado "
            "límite que no existe aquí.")

    # ── IDENTIFICACIÓN Y RUTA ────────────────────────────────────────────────
    P.append(_paso("Identificación", "perfil", "Designación del perfil", nombre or "—", "",
        "dato de proyecto", f"perfil = {nombre}", "AISC / CISC",
        "Nombre tal como llega del modelo (ETABS/Revit). Se normaliza (mayúsculas, sin "
        "espacios, sin equivalencia imperial entre paréntesis) antes de buscar en tabla.",
        "input"))
    P.append(_paso("Identificación", "fuente", "Ruta de resolución de propiedades",
        fuente, "", "TABLA_W → derivada de geometría → HSS",
        f"fuente('{nombre}') = {fuente}  →  {f_titulo}",
        "perfiles_acero.props_seccion:177",
        f_desc, "resultado" if fuente in ("tabla", "hss") else "check"))
    P.append(_paso("Identificación", "en_tabla", "El perfil está tabulado en AISC/CISC",
        en_tabla, "", "perfil ∈ TABLA_W",
        f"'{_norm_w(nombre)}' {'∈' if en_tabla else '∉'} TABLA_W ({len(TABLA_W)} perfiles)",
        "perfiles_acero.TABLA_W",
        "Éste es el check que hasta 2026-07-31 no existía en ninguna memoria de acero. Si "
        "falla, el diseño está apoyado en una derivación, no en la norma.", "check"))

    # ── GEOMETRÍA ────────────────────────────────────────────────────────────
    for sim, key, uni, desc in (
        ("d",  "d",  "cm",  "Peralte total de la sección."),
        ("b_f", "bf", "cm", "Ancho de ala (lado, en HSS)."),
        ("t_f", "tf", "cm", "Espesor de ala (pared de diseño, en HSS)."),
        ("t_w", "tw", "cm", "Espesor de alma (pared de diseño, en HSS)."),
        ("A_g", "Ag", "cm²", "Área bruta de la sección — entra directo a φPn de tracción §D2."),
    ):
        if r.get(key) is not None:
            P.append(_paso("Geometría", sim, desc.split(".")[0], round(float(r[key]), 4), uni,
                ("TABLA_W ÷10 (÷100 para Ag)" if fuente == "tabla" else "dato de PERFILES_ACERO"),
                f"{sim} = {_fmt(r[key], 4)}",
                "CISC Handbook / AISC 16a" if fuente == "tabla" else "perfiles_acero.PERFILES_ACERO",
                desc, "input"))
    if r.get("hw") is not None and fuente != "tabla":
        P.append(_paso("Geometría", "h_w", "Altura del alma", round(float(r["hw"]), 4), "cm",
            "hw = d − 2·tf",
            f"{_fmt(r['d'], 3)} − 2·{_fmt(r['tf'], 3)} = {_fmt(r['hw'], 4)}",
            "geometría", "Porción de alma entre alas, base de la derivación.", "intermedio"))

    # ── PROPIEDADES ──────────────────────────────────────────────────────────
    if fuente == "derivada":
        P.append(_paso("Propiedades derivadas", "I_x", "Momento de inercia fuerte",
            round(r["Ix"], 3), "cm⁴", "Ix = bf·d³/12 − (bf−tw)·hw³/12",
            f"{_fmt(r['bf'],3)}·{_fmt(r['d'],3)}³/12 − ({_fmt(r['bf'],3)}−{_fmt(r['tw'],3)})·{_fmt(r['hw'],3)}³/12 = {_fmt(r['Ix'],3)}",
            "derivación de 3 rectángulos",
            "Rectángulo lleno menos los dos huecos laterales. Exacto para la geometría dada — "
            "el problema es que la geometría dada es aproximada.", "intermedio"))
        P.append(_paso("Propiedades derivadas", "I_y", "Momento de inercia débil",
            round(r["Iy"], 3), "cm⁴", "Iy = 2·(tf·bf³/12) + hw·tw³/12",
            f"2·({_fmt(r['tf'],3)}·{_fmt(r['bf'],3)}³/12) + {_fmt(r['hw'],3)}·{_fmt(r['tw'],3)}³/12 = {_fmt(r['Iy'],3)}",
            "derivación de 3 rectángulos",
            "Gobierna el pandeo por flexión débil (§E3) y, vía ry, toda la compresión.",
            "intermedio"))
        P.append(_paso("Propiedades derivadas", "Z_x", "Módulo plástico fuerte",
            round(r["Zx"], 3), "cm³", "Zx = bf·tf·(d−tf) + tw·hw²/4",
            f"{_fmt(r['bf'],3)}·{_fmt(r['tf'],3)}·({_fmt(r['d'],3)}−{_fmt(r['tf'],3)}) + {_fmt(r['tw'],3)}·{_fmt(r['hw'],3)}²/4 = {_fmt(r['Zx'],3)}",
            "derivación de 3 rectángulos",
            "⚠ EL número crítico: Mp = Fy·Zx. Todo el φMn que se narra aguas abajo cuelga de "
            "aquí. Si este Zx viene derivado y no de tabla, φMn hereda el error sin avisar.",
            "resultado"))
        P.append(_paso("Propiedades derivadas", "S_x", "Módulo elástico fuerte",
            round(r["Sx"], 3), "cm³", "Sx = 2·Ix/d",
            f"2·{_fmt(r['Ix'],3)}/{_fmt(r['d'],3)} = {_fmt(r['Sx'],3)}",
            "derivación", "Gobierna cuando la sección no es compacta (§F3/F4).", "intermedio"))
        P.append(_paso("Propiedades derivadas", "r_y", "Radio de giro débil",
            round(r["ry"], 4), "cm", "ry = √(Iy/Ag)",
            f"√({_fmt(r['Iy'],3)} / {_fmt(r['Ag'],3)}) = {_fmt(r['ry'],4)}",
            "derivación",
            "Entra a KL/r en compresión §E3 — un ry bajo penaliza φPn de forma cuadrática.",
            "intermedio"))
        P.append(_paso("Propiedades derivadas", "J", "Constante torsional",
            round(r["J"], 4), "cm⁴", "J = (2·bf·tf³ + hw·tw³)/3",
            f"(2·{_fmt(r['bf'],3)}·{_fmt(r['tf'],3)}³ + {_fmt(r['hw'],3)}·{_fmt(r['tw'],3)}³)/3 = {_fmt(r['J'],4)}",
            "torsión de St. Venant (perfil abierto)",
            "Rige junto con Cw el pandeo lateral-torsional (§F2). Muy sensible a tf, que es "
            "justo el dato impreciso.", "intermedio"))
        P.append(_paso("Propiedades derivadas", "C_w", "Constante de alabeo",
            round(r["Cw"], 3), "cm⁶", "Cw = Iy·ho²/4",
            f"{_fmt(r['Iy'],3)}·{_fmt(r['ho'],3)}²/4 = {_fmt(r['Cw'],3)}",
            "AISC §F2 (perfil doblemente simétrico)",
            "Aproximación clásica para perfil I doblemente simétrico.", "intermedio"))
        P.append(_paso("Propiedades derivadas", "r_ts", "Radio efectivo para LTB",
            round(r["rts"], 4), "cm", "rts = √(√(Iy·Cw)/Sx)",
            f"√(√({_fmt(r['Iy'],3)}·{_fmt(r['Cw'],3)}) / {_fmt(r['Sx'],3)}) = {_fmt(r['rts'],4)}",
            "AISC §F2 ec. F2-7",
            "Define Lp/Lr, los límites de longitud no arriostrada.", "intermedio"))
    elif fuente == "hss":
        P.append(_paso("Propiedades HSS", "I", "Momento de inercia (Ix = Iy)",
            round(r["Ix"], 3), "cm⁴", "I = (b⁴ − bi⁴)/12",
            f"({_fmt(r['bf'],3)}⁴ − ({_fmt(r['bf'],3)}−2·{_fmt(r['tf'],3)})⁴)/12 = {_fmt(r['Ix'],3)}",
            "sección cerrada cuadrada",
            "Tubo lleno menos hueco interior. Doblemente simétrico: Ix = Iy exactamente.",
            "intermedio"))
        P.append(_paso("Propiedades HSS", "Z", "Módulo plástico (Zx = Zy)",
            round(r["Zx"], 3), "cm³", "Z = (b³ − bi³)/4",
            f"({_fmt(r['bf'],3)}³ − ({_fmt(r['bf'],3)}−2·{_fmt(r['tf'],3)})³)/4 = {_fmt(r['Zx'],3)}",
            "sección cerrada cuadrada", "Mp = Fy·Z cuelga de aquí.", "resultado"))
        P.append(_paso("Propiedades HSS", "J", "Constante torsional cerrada",
            round(r["J"], 3), "cm⁴", "J = 4·Am²·t/(4·(b−t))",
            f"Am = ({_fmt(r['bf'],3)}−{_fmt(r['tf'],3)})² → J = {_fmt(r['J'],3)}",
            "fórmula de Bredt (torsión cerrada)",
            "Torsión de sección cerrada: órdenes de magnitud mayor que la de un perfil abierto. "
            "Por eso el HSS no sufre LTB.", "intermedio"))
        P.append(_paso("Propiedades HSS", "λ", "Esbeltez de pared",
            round(r["lam_ala"], 3), "", "λ = (b − 3t)/t",
            f"({_fmt(r['bf'],3)} − 3·{_fmt(r['tf'],3)})/{_fmt(r['tf'],3)} = {_fmt(r['lam_ala'],3)}",
            "AISC Tabla B4.1 (ancho plano ≈ b−3t)",
            "Clasifica la pared como compacta/no compacta/esbelta.", "intermedio"))
        P.append(_paso("Propiedades HSS", "C_w", "Constante de alabeo", r["Cw"], "cm⁶",
            "Cw = 0 (sección cerrada)", "Cw = 0",
            "AISC §F7", "El alabeo no gobierna en secciones cerradas.", "intermedio"))
    else:  # tabla
        for sim, key, uni, desc in (
            ("I_x", "Ix", "cm⁴", "Momento de inercia fuerte — valor tabulado, dividido por 1e4 desde mm⁴."),
            ("I_y", "Iy", "cm⁴", "Momento de inercia débil — ÷1e4 desde mm⁴."),
            ("S_x", "Sx", "cm³", "Módulo elástico fuerte — ÷1e3 desde mm³."),
            ("Z_x", "Zx", "cm³", "Módulo plástico fuerte — ÷1e3 desde mm³. Alimenta Mp = Fy·Zx."),
            ("r_y", "ry", "cm",  "Radio de giro débil — ÷10 desde mm. Entra a KL/r en compresión §E3."),
            ("J",   "J",  "cm⁴", "Constante torsional — ÷1e4 desde mm⁴."),
            ("C_w", "Cw", "cm⁶", "Constante de alabeo — ÷1e6 desde mm⁶."),
            ("r_ts", "rts", "cm", "Radio efectivo para LTB (§F2 ec. F2-7) — ÷10 desde mm."),
        ):
            if r.get(key) is not None:
                P.append(_paso("Propiedades (tabla AISC/CISC)", sim, desc.split("—")[0].strip(),
                    round(float(r[key]), 4), uni,
                    "valor tabulado + conversión de unidad SI→cm",
                    f"{sim} = {_fmt(r[key], 4)} (TABLA_W['{_norm_w(nombre)}'])",
                    "CISC Handbook / AISC 16a",
                    desc, "input"))

    # ── ESBELTECES E IMPACTO ─────────────────────────────────────────────────
    if fuente != "hss" and r.get("lam_ala") is not None:
        P.append(_paso("Esbelteces", "λ_ala", "Esbeltez del ala", round(r["lam_ala"], 3), "",
            "λ_ala = bf/(2·tf)",
            f"{_fmt(r['bf'],3)}/(2·{_fmt(r['tf'],3)}) = {_fmt(r['lam_ala'],3)}",
            "AISC Tabla B4.1b",
            "Clasifica el ala en compacta / no compacta / esbelta. Decide si §F2 (Mp completo) "
            "o §F3 (pandeo local del ala) gobierna la flexión.", "intermedio"))
        P.append(_paso("Esbelteces", "λ_alma", "Esbeltez del alma", round(r["lam_alma"], 3), "",
            "h/tw",
            f"λ_alma = {_fmt(r['lam_alma'],3)}",
            "AISC Tabla B4.1b",
            "Ídem para el alma. También decide Cv en cortante §G2.", "intermedio"))

    if r.get("Zx"):
        mp = float(fy_kgcm2) * float(r["Zx"]) / 100000.0   # kgf·cm → t·m
        P.append(_paso("Impacto aguas abajo", "M_p", "Momento plástico resultante",
            round(mp, 4), "t·m", "Mp = Fy · Zx",
            f"{_fmt(fy_kgcm2)} kgf/cm² × {_fmt(r['Zx'],3)} cm³ = {_fmt(mp,4)} t·m",
            "AISC §F2.1 ec. F2-1",
            "Aquí se cierra el círculo: éste es el número que la memoria de miembro de acero "
            "muestra narrado y perfecto. Su calidad es exactamente la calidad del Zx de arriba, "
            f"y su procedencia es '{fuente}'.", "resultado"))

    for p in P:
        if p["tipo"] != "input" and p["latex"] is None:
            p["latex"] = LATEX_BY_FORMULA_PERFIL.get(p["formula"])

    constantes = [
        {"simbolo": "n_tabla", "latex": r"n_{TABLA\_W}", "valor": len(TABLA_W), "unidad": "perfiles",
         "desc": "Perfiles con propiedades AISC/CISC exactas. Fuera de esta lista, todo se deriva."},
        {"simbolo": "n_catálogo", "latex": r"n_{PERFILES}", "valor": len(PERFILES_ACERO), "unidad": "perfiles",
         "desc": "Perfiles con geometría en el catálogo (d, bf, tf, tw, Ag)."},
        {"simbolo": "err_deriv", "latex": r"\approx 3\%", "valor": DERIVADA_CONSERVADURISMO_PCT, "unidad": "%",
         "desc": "Conservadurismo nominal de la vía derivada, por admisión del docstring de props_seccion. Con geometría imprecisa el error real puede llegar a 25-34%."},
    ]

    meta = {
        "dominio": "perfiles_acero",
        "norma": "AISC 360-16 · CISC Handbook (propiedades de sección)",
        "riesgo": "MEDIO — invalida silenciosamente memorias de acero que sí se ven",
        "perfil": nombre,
        "fuente": fuente,
        "fuente_titulo": f_titulo,
        "en_tabla": en_tabla,
        "cumple_normativa": fuente in ("tabla", "hss"),
        "advertencias": advertencias,
        "nota_norma": ("La norma no está en discusión: AISC 360-16 es correcta. Lo que estaba "
                       "ciego es de dónde salen los DATOS que entran a la norma. Una memoria "
                       "impecable sobre un Zx derivado es una memoria impecablemente incierta."),
    }
    if meta_extra:
        meta.update(meta_extra)
    return {"meta": meta, "pasos": P, "constantes": constantes, "resultado": r}
