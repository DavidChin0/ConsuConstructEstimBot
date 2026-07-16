# -*- coding: utf-8 -*-
"""
Acción sísmica CHOC-08 — motor de cálculo (estilo Mathcad)
==========================================================
Módulo ADITIVO. NO toca calculo_estructural.py (diseño ACI de elemento).
Sólo produce la memoria sísmica: parámetros, periodo, coeficiente sísmico,
cortante basal, espectro de respuesta y deriva límite, conforme CHOC-08.

Notación de salida idéntica a calculo_estructural.memoria_calculo:
  {meta, pasos[], espectro[[T, a_g], ...], constantes[]}
Cada paso = {seccion, simbolo, etiqueta, valor, unidad, formula,
             sustitucion, referencia, descripcion, tipo, latex, latex_sub}
El frontend (KaTeX, función kx()) consume latex + latex_sub.

Unidades: kgf, m, s · g = 9.81 m/s².
Normas: CHOC-08 (acción sísmica) · ACI 318 (diseño concreto, en otro módulo).
"""

import math

G = 9.81  # m/s²

# ── Tabla de suelos CHOC-08 (Tabla 1.3.4-2) ──────────────────────────────────
# clave -> {S, Ta, Tb, c}
SUELOS = {
    "S1": {"S": 1.0, "Ta": 0.155, "Tb": 0.364, "c": 2.0, "desc": "Roca / suelo medio-denso a duro"},
    "S2": {"S": 1.2, "Ta": 0.186, "Tb": 0.524, "c": 2.0, "desc": "Suelo firme, profundidad media"},
    "S3": {"S": 1.5, "Ta": 0.233, "Tb": 0.818, "c": 2.0, "desc": "Suelo blando o estratos profundos"},
    "S4": {"S": 2.0, "Ta": 0.310, "Tb": 1.455, "c": 2.0, "desc": "Arcilla blanda de gran espesor"},
}

# ── Tabla de zonas sísmicas (Fig. 1.3.4-1) ───────────────────────────────────
# clave de zona -> Z (fracción de g)
ZONAS = {
    "1":  0.10, "2":  0.15, "3a": 0.20, "3b": 0.25, "4a": 0.30,
    "4b": 0.35, "5a": 0.40, "5b": 0.45, "6":  0.50,
}

CT_CONCRETO = 0.0731  # marco de concreto reforzado (Periodo Método A)
C_MAX       = 2.75    # tope del coeficiente sísmico C
C_RW_MIN    = 0.075   # piso del cociente C/Rw


# ── Helpers de formato ───────────────────────────────────────────────────────
def _fmt(x, dec=3):
    """Número limpio: sin ceros de cola, coma de miles, '—' si None."""
    if x is None:
        return "—"
    if isinstance(x, bool):
        return "OK" if x else "FALLA"
    try:
        xf = float(x)
    except (TypeError, ValueError):
        return str(x)
    if xf == int(xf) and abs(xf) < 1e9:
        return f"{int(xf):,}"
    return f"{round(xf, dec):,}".rstrip("0").rstrip(".")


def _paso(seccion, simbolo, etiqueta, valor, unidad, formula, sustitucion,
          referencia, descripcion, tipo="intermedio", latex=None, latex_sub=None):
    return {
        "seccion":     seccion,
        "simbolo":     simbolo,
        "etiqueta":    etiqueta,
        "valor":       valor,
        "unidad":      unidad,
        "formula":     formula,
        "sustitucion": sustitucion,
        "referencia":  referencia,
        "descripcion": descripcion,
        "tipo":        tipo,        # input | intermedio | resultado | check
        "latex":       latex,       # fórmula simbólica LaTeX
        "latex_sub":   latex_sub,   # sustitución numérica LaTeX
    }


# ── Funciones puras del espectro CHOC-08 ─────────────────────────────────────
def periodo_metodo_a(hn_m, ct=CT_CONCRETO):
    """T_A = Ct·hn^(3/4)  (CHOC-08 1.3.6.5.3, marco de concreto)."""
    return ct * (hn_m ** 0.75)


def coef_sismico(S, T, c_max=C_MAX):
    """C = 1.25·S / T^(2/3),  acotado a c_max  (CHOC-08 1.3.6.4)."""
    if T <= 0:
        return c_max
    return min(1.25 * S / (T ** (2.0 / 3.0)), c_max)


def cortante_basal(Z, I, C, Rw, W):
    """V = (Z·I·C / Rw)·W  (cortante basal estático, CHOC-08 1.3.6.2)."""
    return (Z * I * C / Rw) * W


def cortante_estatico(Z, I, C, Rw, W):
    """V_est = Z·I·C/Rw·W  (alias semántico de cortante_basal para el escalado
    1.3.6.5.3; mismo cálculo, nombre explícito para comparar con el dinámico)."""
    return cortante_basal(Z, I, C, Rw, W)


def escalado_cortante(V_din, V_est, regular=True):
    """Escalado del cortante dinámico (CHOC-08 1.3.6.5.3).

    El cortante dinámico (modal espectral) no puede quedar por debajo de un
    porcentaje del estático: 90% si la estructura es regular, 100% si irregular.
    Si queda por debajo, se aplica en ETABS un factor de escala al caso SH.

    Devuelve {V_est, V_din, objetivo_pct, V_objetivo, factor_escala, cumple}:
      objetivo_pct  : 90 (regular) o 100 (irregular)
      V_objetivo    : objetivo_pct/100 · V_est
      factor_escala : max(1.0, V_objetivo/V_din) si V_din>0, si no None
      cumple        : V_din >= V_objetivo
    """
    pct = 0.90 if regular else 1.00
    V_obj = pct * V_est
    if V_din is not None and V_din > 0:
        factor = max(1.0, V_obj / V_din)
    else:
        factor = None
    cumple = (V_din is not None) and (V_din >= V_obj)
    return {
        "V_est":         round(V_est, 1) if V_est is not None else None,
        "V_din":         round(V_din, 1) if V_din is not None else None,
        "objetivo_pct":  int(round(pct * 100)),
        "V_objetivo":    round(V_obj, 1),
        "factor_escala": round(factor, 4) if factor is not None else None,
        "cumple":        bool(cumple),
    }


def verificar_derivas(derivas_por_piso, deriva_limite):
    """Verifica la deriva de cada piso contra el límite CHOC-08 1.3.5.8.2.

    derivas_por_piso : lista de {story, direction, drift} (del parser ETABS).
    deriva_limite    : tope admisible (de la hoja sísmica / ContextoSismico).

    Devuelve {pisos[], resumen{max, story_max, dir_max, cumple_global, limite}}.
    Cada piso: {story, dir, drift, limite, cumple}.
    """
    lim = float(deriva_limite) if deriva_limite is not None else None
    pisos = []
    dr_max = None
    story_max = None
    dir_max = None
    cumple_global = True
    for d in (derivas_por_piso or []):
        drift = d.get("drift")
        if drift is None:
            continue
        cumple = (lim is None) or (drift <= lim)
        if not cumple:
            cumple_global = False
        if dr_max is None or drift > dr_max:
            dr_max = drift
            story_max = d.get("story")
            dir_max = d.get("direction")
        pisos.append({
            "story":  d.get("story"),
            "dir":    d.get("direction"),
            "drift":  round(drift, 6),
            "limite": round(lim, 6) if lim is not None else None,
            "cumple": bool(cumple),
        })
    return {
        "pisos": pisos,
        "resumen": {
            "max":           round(dr_max, 6) if dr_max is not None else None,
            "story_max":     story_max,
            "dir_max":       dir_max,
            "limite":        round(lim, 6) if lim is not None else None,
            "cumple_global": bool(cumple_global) if pisos else None,
        },
    }


def acel_espectral(T, Z, Ta, Tb, c):
    """a/g(T) por ramas (CHOC-08 1.3.6-10/11/12). Adimensional (fracción de g)."""
    if T < Ta:
        return 2.5 * Z * (0.4 + 0.7 * T / Ta)
    elif T <= Tb:
        return 2.75 * Z
    else:
        return 2.75 * Z * (Tb / T) ** c


def deriva_limite(T, Rw):
    """Deriva de entrepiso límite (CHOC-08 1.3.5.8.2)."""
    if T < 0.7:
        return min(0.04 / Rw, 0.005)
    return min(0.03 / Rw, 0.004)


def construir_espectro(Z, Ta, Tb, c, t_max=2.0, paso=0.05):
    """Genera la tabla de pares [T, a/g] de 0 a t_max para graficar/exportar.
    Inserta puntos clave (Ta, Tb) para capturar los quiebres del espectro."""
    pts = set()
    n = int(round(t_max / paso))
    for i in range(n + 1):
        pts.add(round(i * paso, 4))
    for k in (Ta, Tb):
        pts.add(round(k, 4))
        pts.add(round(k - 1e-4, 4))  # justo antes del quiebre
    tabla = []
    for T in sorted(p for p in pts if 0 <= p <= t_max):
        tabla.append([round(T, 4), round(acel_espectral(T, Z, Ta, Tb, c), 4)])
    return tabla


# ── Memoria sísmica completa (forma idéntica a memoria_calculo) ──────────────
def memoria_sismica(entrada: dict) -> dict:
    """
    entrada (todas con default CC-135):
      zona  : clave de ZONAS  (default "3b")
      suelo : clave de SUELOS (default "S1")
      I     : factor de importancia (default 1.0)
      Rw    : factor de reducción (default 8)
      hn_m  : altura total del edificio en m (default 3)
      W_t   : peso sísmico en kgf (default 1206)
    Devuelve {meta, pasos, espectro, constantes}.
    """
    zona  = str(entrada.get("zona", "3b"))
    suelo = str(entrada.get("suelo", "S1")).upper()
    I     = float(entrada.get("I", 1.0))
    Rw    = float(entrada.get("Rw", 8))
    hn    = float(entrada.get("hn_m", 3))
    W     = float(entrada.get("W_t", 1206))

    if zona not in ZONAS:
        zona = "3b"
    if suelo not in SUELOS:
        suelo = "S1"

    Z  = ZONAS[zona]
    sp = SUELOS[suelo]
    S, Ta, Tb, c = sp["S"], sp["Ta"], sp["Tb"], sp["c"]

    # Cálculos
    T   = periodo_metodo_a(hn)
    C   = coef_sismico(S, T)
    C_sin_tope = 1.25 * S / (T ** (2.0 / 3.0)) if T > 0 else C
    c_rw = C / Rw
    V   = cortante_basal(Z, I, C, Rw, W)
    a_meseta = 2.75 * Z
    a_T = acel_espectral(T, Z, Ta, Tb, c)
    d_lim = deriva_limite(T, Rw)
    espectro = construir_espectro(Z, Ta, Tb, c)

    P = []

    # ── PARÁMETROS ───────────────────────────────────────────────────────────
    P.append(_paso("Parámetros", "Zona", "Zona sísmica", zona, "",
        "mapa Fig. 1.3.4-1", f"Zona {zona}", "CHOC-08 Fig. 1.3.4-1",
        "Zona sísmica del municipio; fija el factor de zona Z.", "input"))
    P.append(_paso("Parámetros", "Z", "Factor de zona sísmica", Z, "g (fracción)",
        "Z = APS de la zona (Tabla)", f"Zona {zona} → Z = {_fmt(Z)}",
        "CHOC-08 Tabla 1.3.4-1",
        "Aceleración pico del suelo como fracción de g.", "input",
        latex=r"Z = \text{APS de la zona}",
        latex_sub=rf"Z = {_fmt(Z)}"))
    P.append(_paso("Parámetros", "Suelo", "Perfil de suelo", f"{suelo} — {sp['desc']}", "",
        "Tabla 1.3.4-2", f"{suelo}: {sp['desc']}", "CHOC-08 Tabla 1.3.4-2",
        "Perfil de suelo; define S, Ta, Tb y c del espectro.", "input"))
    P.append(_paso("Parámetros", "S", "Coeficiente de suelo", S, "",
        "según perfil (Tabla 1.3.4-2)", f"{suelo} → S = {_fmt(S)}",
        "CHOC-08 Tabla 1.3.4-2",
        "Amplificación del sitio; entra en el coeficiente sísmico C.", "input",
        latex=r"S \;\text{(perfil de suelo)}", latex_sub=rf"S = {_fmt(S)}"))
    P.append(_paso("Parámetros", "Ta", "Periodo inicial de meseta", Ta, "s",
        "según perfil (Tabla 1.3.4-2)", f"{suelo} → Ta = {_fmt(Ta)}",
        "CHOC-08 Tabla 1.3.4-2",
        "Inicio de la meseta del espectro de aceleraciones.", "input",
        latex=r"T_a", latex_sub=rf"T_a = {_fmt(Ta)}\;s"))
    P.append(_paso("Parámetros", "Tb", "Periodo final de meseta", Tb, "s",
        "según perfil (Tabla 1.3.4-2)", f"{suelo} → Tb = {_fmt(Tb)}",
        "CHOC-08 Tabla 1.3.4-2",
        "Fin de la meseta; a partir de aquí el espectro decae.", "input",
        latex=r"T_b", latex_sub=rf"T_b = {_fmt(Tb)}\;s"))
    P.append(_paso("Parámetros", "c", "Exponente de decaimiento", c, "",
        "según perfil (Tabla 1.3.4-2)", f"{suelo} → c = {_fmt(c)}",
        "CHOC-08 Tabla 1.3.4-2",
        "Exponente de la rama descendente del espectro (T > Tb).", "input",
        latex=r"c", latex_sub=rf"c = {_fmt(c)}"))
    P.append(_paso("Parámetros", "I", "Factor de importancia", I, "",
        "Tabla 1.3.4-3 (uso/ocupación)", f"I = {_fmt(I)}",
        "CHOC-08 Tabla 1.3.4-3",
        "Mayora la demanda según la importancia de la edificación.", "input",
        latex=r"I", latex_sub=rf"I = {_fmt(I)}"))
    P.append(_paso("Parámetros", "Rw", "Factor de reducción", Rw, "",
        "Tabla 1.3.4-6 (sistema estructural)", f"Rw = {_fmt(Rw)}",
        "CHOC-08 Tabla 1.3.4-6",
        "Reduce la demanda elástica por ductilidad del sistema (marco/muro/dual).", "input",
        latex=r"R_w", latex_sub=rf"R_w = {_fmt(Rw)}"))
    P.append(_paso("Parámetros", "hn", "Altura total del edificio", hn, "m",
        "dato del proyecto", f"hn = {_fmt(hn)} m", "—",
        "Altura desde la base hasta el nivel superior; entra en el periodo Método A.", "input",
        latex=r"h_n", latex_sub=rf"h_n = {_fmt(hn)}\;m"))
    P.append(_paso("Parámetros", "W", "Peso sísmico", W, "kgf",
        "carga muerta + porción de viva (1.3.5.1)", f"W = {_fmt(W)} kgf", "CHOC-08 1.3.5.1",
        "Peso que se moviliza en el sismo (CM total + porción de CV según uso).", "input",
        latex=r"W", latex_sub=rf"W = {_fmt(W)}\;kgf"))

    # ── PERIODO ──────────────────────────────────────────────────────────────
    P.append(_paso("Periodo", "T_A", "Periodo fundamental (Método A)", round(T, 4), "s",
        "T_A = 0.0731·hn^(3/4)   (marco concreto)",
        f"0.0731·{_fmt(hn)}^(3/4) = {_fmt(T, 4)} s",
        "CHOC-08 1.3.6.5.3",
        "Periodo aproximado del edificio (Ct=0.0731 para marco de concreto reforzado).",
        "resultado",
        latex=r"T_A = 0.0731\,h_n^{3/4}",
        latex_sub=rf"T_A = 0.0731\cdot {_fmt(hn)}^{{3/4}} = {_fmt(T, 4)}\;s"))

    # ── CORTANTE BASAL ───────────────────────────────────────────────────────
    P.append(_paso("Cortante basal", "C", "Coeficiente sísmico", round(C, 4), "",
        "C = 1.25·S / T^(2/3),   C ≤ 2.75",
        f"1.25·{_fmt(S)} / {_fmt(T, 4)}^(2/3) = {_fmt(C_sin_tope, 4)} → C = {_fmt(C, 4)}"
            + ("  (limitado a 2.75)" if C_sin_tope > C_MAX else ""),
        "CHOC-08 1.3.6.4",
        "Coeficiente del espectro de diseño en el periodo del edificio, con tope 2.75.",
        "resultado",
        latex=r"C = \dfrac{1.25\,S}{T^{2/3}} \le 2.75",
        latex_sub=rf"C = \dfrac{{1.25\cdot {_fmt(S)}}}{{{_fmt(T, 4)}^{{2/3}}}} = {_fmt(C, 4)}"))
    P.append(_paso("Cortante basal", "C/Rw", "Chequeo de piso del coeficiente",
        bool(c_rw >= C_RW_MIN), "",
        "C/Rw ≥ 0.075",
        f"{_fmt(C, 4)}/{_fmt(Rw)} = {_fmt(c_rw, 4)} {'≥' if c_rw >= C_RW_MIN else '<'} 0.075",
        "CHOC-08 1.3.6.4",
        "El coeficiente reducido no puede bajar de 0.075 (piso de diseño).",
        "check",
        latex=r"\dfrac{C}{R_w} \ge 0.075",
        latex_sub=rf"\dfrac{{{_fmt(C, 4)}}}{{{_fmt(Rw)}}} = {_fmt(c_rw, 4)}"))
    P.append(_paso("Cortante basal", "V", "Cortante basal estático", round(V, 1), "kgf",
        "V = (Z·I·C / Rw)·W",
        f"({_fmt(Z)}·{_fmt(I)}·{_fmt(C, 4)} / {_fmt(Rw)})·{_fmt(W)} = {_fmt(V, 1)} kgf",
        "CHOC-08 1.3.6.2",
        "Fuerza cortante en la base que el sismo induce en el edificio (estático).",
        "resultado",
        latex=r"V = \dfrac{Z\,I\,C}{R_w}\,W",
        latex_sub=rf"V = \dfrac{{{_fmt(Z)}\cdot{_fmt(I)}\cdot{_fmt(C, 4)}}}{{{_fmt(Rw)}}}\cdot{_fmt(W)} = {_fmt(V, 1)}\;kgf"))

    # ── ESPECTRO ─────────────────────────────────────────────────────────────
    P.append(_paso("Espectro", "a/g | T<Ta", "Rama ascendente", "—", "g",
        "a/g = 2.5·Z·(0.4 + 0.7·T/Ta)",
        f"para T < {_fmt(Ta)} s", "CHOC-08 1.3.6-10",
        "Rama inicial creciente del espectro de aceleraciones.", "intermedio",
        latex=r"\dfrac{a}{g} = 2.5\,Z\left(0.4 + 0.7\dfrac{T}{T_a}\right)",
        latex_sub=rf"T < T_a = {_fmt(Ta)}\;s"))
    P.append(_paso("Espectro", "a/g | meseta", "Rama de meseta", round(a_meseta, 4), "g",
        "a/g = 2.75·Z          (Ta ≤ T ≤ Tb)",
        f"2.75·{_fmt(Z)} = {_fmt(a_meseta, 4)} g", "CHOC-08 1.3.6-11",
        "Meseta de máxima aceleración espectral.", "resultado",
        latex=r"\dfrac{a}{g} = 2.75\,Z \quad (T_a \le T \le T_b)",
        latex_sub=rf"\dfrac{{a}}{{g}} = 2.75\cdot{_fmt(Z)} = {_fmt(a_meseta, 4)}\;g"))
    P.append(_paso("Espectro", "a/g | T>Tb", "Rama descendente", "—", "g",
        "a/g = 2.75·Z·(Tb/T)^c",
        f"para T > {_fmt(Tb)} s, c = {_fmt(c)}", "CHOC-08 1.3.6-12",
        "Rama descendente del espectro (periodos largos).", "intermedio",
        latex=r"\dfrac{a}{g} = 2.75\,Z\left(\dfrac{T_b}{T}\right)^{c}",
        latex_sub=rf"T > T_b = {_fmt(Tb)}\;s"))
    P.append(_paso("Espectro", "a_max/g", "Aceleración espectral máxima (meseta)",
        round(a_meseta, 4), "g",
        "a_max/g = 2.75·Z", f"2.75·{_fmt(Z)} = {_fmt(a_meseta, 4)} g",
        "CHOC-08 1.3.6-11",
        "Ordenada máxima del espectro = meseta.", "resultado",
        latex=r"\dfrac{a_{max}}{g} = 2.75\,Z",
        latex_sub=rf"\dfrac{{a_{{max}}}}{{g}} = 2.75\cdot{_fmt(Z)} = {_fmt(a_meseta, 4)}\;g"))
    P.append(_paso("Espectro", "a/g(T_A)", "Ordenada en el periodo del edificio",
        round(a_T, 4), "g",
        "a/g evaluado en T_A", f"T_A = {_fmt(T, 4)} s → a/g = {_fmt(a_T, 4)} g",
        "CHOC-08 1.3.6",
        "Aceleración espectral que le corresponde al periodo fundamental del edificio.",
        "resultado",
        latex=r"\dfrac{a}{g}(T_A)",
        latex_sub=rf"\dfrac{{a}}{{g}}({_fmt(T, 4)}) = {_fmt(a_T, 4)}\;g"))

    # ── DERIVA ───────────────────────────────────────────────────────────────
    rama_d = "T < 0.7 s → min(0.04/Rw, 0.005)" if T < 0.7 else "T ≥ 0.7 s → min(0.03/Rw, 0.004)"
    num1, num2 = (0.04, 0.005) if T < 0.7 else (0.03, 0.004)
    P.append(_paso("Deriva", "Δ_lim", "Deriva de entrepiso límite", round(d_lim, 5), "",
        rama_d,
        f"min({_fmt(num1)}/{_fmt(Rw)}, {_fmt(num2)}) = {_fmt(d_lim, 5)} (≈ 1/{int(round(1 / d_lim))})",
        "CHOC-08 1.3.5.8.2",
        "Tope de deriva de entrepiso; la deriva real de ETABS debe quedar por debajo.",
        "resultado",
        latex=(r"\Delta_{lim} = \min\!\left(\dfrac{0.04}{R_w},\,0.005\right)" if T < 0.7
               else r"\Delta_{lim} = \min\!\left(\dfrac{0.03}{R_w},\,0.004\right)"),
        latex_sub=rf"\Delta_{{lim}} = \min\!\left(\dfrac{{{_fmt(num1)}}}{{{_fmt(Rw)}}},\,{_fmt(num2)}\right) = {_fmt(d_lim, 5)}"))

    meta = {
        "modulo":   "ETABS · Acción sísmica CHOC-08",
        "norma":    "CHOC-08 (sismo) · ACI 318 (concreto)",
        "zona":     zona,
        "suelo":    suelo,
        "Z":        Z, "S": S, "Ta": Ta, "Tb": Tb, "c": c,
        "I":        I, "Rw": Rw, "hn_m": hn, "W_t": W,
        "T_A":      round(T, 4),
        "C":        round(C, 4),
        "V_kgf":    round(V, 1),
        "a_max_g":  round(a_meseta, 4),
        "deriva_limite": round(d_lim, 5),
        "ok_c_rw":  bool(c_rw >= C_RW_MIN),
        "resumen":  f"Zona {zona} (Z={_fmt(Z)}) · {suelo} · I={_fmt(I)} · Rw={_fmt(Rw)} · "
                    f"T={_fmt(T, 3)}s · C={_fmt(C, 3)} · V={_fmt(V, 0)} kgf",
    }

    constantes = [
        {"simbolo": "g",   "latex": r"g = 9.81\;m/s^2",     "valor": G,        "unidad": "m/s²", "desc": "Aceleración de la gravedad."},
        {"simbolo": "Ct",  "latex": r"C_t = 0.0731",        "valor": CT_CONCRETO, "unidad": "", "desc": "Coeficiente del periodo Método A (marco de concreto reforzado)."},
        {"simbolo": "C_max", "latex": r"C_{max} = 2.75",    "valor": C_MAX,    "unidad": "", "desc": "Tope del coeficiente sísmico C."},
        {"simbolo": "C/Rw_min", "latex": r"(C/R_w)_{min} = 0.075", "valor": C_RW_MIN, "unidad": "", "desc": "Piso del coeficiente reducido C/Rw."},
        {"simbolo": "ξ",   "latex": r"\xi = 5\%",           "valor": 0.05,     "unidad": "", "desc": "Amortiguamiento del espectro de respuesta."},
        {"simbolo": "f_dir", "latex": r"100/30",            "valor": 0.30,     "unidad": "", "desc": "Combinación direccional (regla 100/30)."},
        {"simbolo": "e_acc", "latex": r"e = 5\%",           "valor": 0.05,     "unidad": "", "desc": "Excentricidad accidental (torsión, 1.3.5.5)."},
    ]

    return {"meta": meta, "pasos": P, "espectro": espectro, "constantes": constantes}


def espectro_csv(espectro) -> str:
    """Serializa el espectro a CSV (T,a_g) listo para pegar en ETABS."""
    lineas = ["T,a_g"]
    for T, a_g in espectro:
        lineas.append(f"{T},{a_g}")
    return "\n".join(lineas)
