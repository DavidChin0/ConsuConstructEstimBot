"""
Motor de cálculo estructural — ACI 318-19
==========================================
Fórmulas verificadas en:
  D:/OneDrive/Desktop/My Brain/ConsuConstruct/03 Automation Projects/
  EstimaStruct/diseno_estructural/formulas_test_model.py (22/22 tests OK)

Fuente original: Viga-Colum.xls (rosado&rosado, ACI 318-71)
Adaptación φ: ACI 318-19 (cortante 0.75, columnas 0.65, flexión 0.90)
Torsión: fórmulas ACI 318-71 §11.6 (Σx²y). ACI 318-19 §22.7 usa modelo de tubo de pared delgada (pendiente implementar).

Todas las funciones son PURAS (sin ORM). Entrada/salida en unidades:
  longitudes: cm | fuerzas: t o kg | momentos: t·m | áreas: cm²
"""

import math

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTES
# ─────────────────────────────────────────────────────────────────────────────
FMAX_SISMICO  = 0.5         # Factor máx cuantía zona sísmica ACI 318-19 §21
PHI_FLEXION   = 0.90        # ACI 318-19 §21.2.1
PHI_CORTANTE  = 0.75        # ACI 318-19 §21.2.1
PHI_COLUMNA   = 0.65        # ACI 318-19 §21.2.1 (espiral: 0.75)
DENSIDAD_ACERO = 7850       # kg/m³
RECUB_DEFAULT  = 4.0        # cm — recubrimiento libre default
S_DEFAULT      = 20.0       # cm — separación de estribos default para Av


# ─────────────────────────────────────────────────────────────────────────────
# A — MATERIALES
# ─────────────────────────────────────────────────────────────────────────────

def beta1(fc: float) -> float:
    """β₁ del bloque rectangular equivalente. ACI 318-19 §22.2.2.3."""
    if fc <= 280:
        return 0.85
    return max(1.05 - fc / 1400, 0.65)


def pb(fc: float, fy: float) -> float:
    """Cuantía balanceada. ACI 318-19 §22.2.2."""
    b1 = beta1(fc)
    return 0.85 * fc * b1 * 6000 / (fy * (6000 + fy))


def pmax_valor(fc: float, fy: float, fmax: float = FMAX_SISMICO) -> float:
    """Cuantía máxima sísmica = fmax · pb."""
    return fmax * pb(fc, fy)


# ─────────────────────────────────────────────────────────────────────────────
# B — VIGA SIMPLE
# ─────────────────────────────────────────────────────────────────────────────

def k_flexion(Mu_tm: float, b: float, d: float, fc: float,
              phi: float = PHI_FLEXION) -> float:
    """K = Mu / (φ·f'c·b·d²). Mu en t·m → kg·cm. 0 si geometría/material inválidos."""
    denom = phi * fc * b * d**2
    if denom <= 0:
        return 0.0
    return Mu_tm * 100_000 / denom


def cuantia_requerida(K: float, fc: float, fy: float) -> float:
    """p = f'c/fy · [1 − √(1−2.36K)] / 1.18. Retorna nan si K > 0.424."""
    disc = 1 - 2.36 * K
    if disc < 0:
        return float('nan')
    return (fc / fy) * (1 - math.sqrt(disc)) / 1.18


def as_min(b: float, d: float, fy: float, bw: float = None) -> float:
    """As,min = 14·b·d / fy (bw para vigas T). ACI 318-19 §9.6.1.2."""
    ancho = bw if bw is not None else b
    return 14 * ancho * d / fy


def mmax(b: float, d: float, fc: float, fy: float,
         fmax: float = FMAX_SISMICO, phi: float = PHI_FLEXION) -> float:
    """Momento máximo con pmax. Retorna t·m."""
    pm = pmax_valor(fc, fy, fmax)
    qm = pm * fy / fc
    return phi * fc * b * d**2 * qm * (1 - 0.59 * qm) / 100_000


def calcular_viga_simple(b: float, d: float, fc: float, fy: float,
                          Mu_tm: float, phi: float = PHI_FLEXION) -> dict:
    """Diseño viga rectangular simple. Retorna dict completo."""
    K     = k_flexion(Mu_tm, b, d, fc, phi)
    p     = cuantia_requerida(K, fc, fy)
    As    = p * b * d if not math.isnan(p) else float('nan')
    Asmin = as_min(b, d, fy)
    pm    = pmax_valor(fc, fy)
    Asmax = pm * b * d
    Mm    = mmax(b, d, fc, fy)
    pb_v  = pb(fc, fy)

    As_final = max(As, Asmin) if not math.isnan(As) else float('nan')

    advs = []
    if math.isnan(As):
        advs.append("Sección imposible (K>0.424). Aumentar b o d.")
    elif As > Asmax:
        advs.append("As > As_max: sección insuficiente. Aumentar dimensiones o usar doble armado.")
    if Mu_tm > Mm:
        advs.append("Mu > Mmax: se requiere doble armado.")

    return {
        "tipo_resultado": "VIGA_SIMPLE",
        "K":              round(K, 6),
        "pb":             round(pb_v, 6),
        "pmax":           round(pm, 6),
        "As_cm2":         round(As_final, 4) if not math.isnan(As_final) else None,
        "A_prima_cm2":    0.0,
        "As_min_cm2":     round(Asmin, 4),
        "As_max_cm2":     round(Asmax, 4),
        "Mmax_tm":        round(Mm, 4),
        "ok_sismico":     (not math.isnan(As)) and (As <= Asmax),
        "necesita_doble": Mu_tm > Mm,
        "advertencias":   "; ".join(advs),
    }


# ─────────────────────────────────────────────────────────────────────────────
# C — VIGA DOBLEMENTE ARMADA
# ─────────────────────────────────────────────────────────────────────────────

def fs_compresion(d: float, d_prima: float, fy: float) -> float:
    """f's acero compresión por compatibilidad. ACI 318-19."""
    fs = 6000 * (1 - (d_prima / d) * (1 + fy / 6000))
    return min(fs, fy)


def calcular_viga_doble(b: float, d: float, d_prima: float,
                         fc: float, fy: float, Mu_tm: float,
                         pmax_factor: float = FMAX_SISMICO,
                         phi: float = PHI_FLEXION) -> dict:
    """Diseño viga doblemente armada."""
    pm    = pmax_factor * pb(fc, fy)
    qm    = pm * fy / fc
    Mmax_kgcm   = phi * fc * b * d**2 * qm * (1 - 0.59 * qm)
    Mmax_tm     = Mmax_kgcm / 100_000

    DM_kgcm = (Mu_tm - Mmax_tm) * 100_000
    fs_p    = fs_compresion(d, d_prima, fy)

    A_prima  = DM_kgcm / (phi * fs_p * (d - d_prima))
    As2      = A_prima * fs_p / fy
    As1      = pm * b * d
    As       = As1 + As2

    p_prima  = A_prima / (b * d)
    pb_corr  = pb(fc, fy) + p_prima * fs_p / fy
    Asmax    = FMAX_SISMICO * pb_corr * b * d
    Asmin    = as_min(b, d, fy)

    advs = []
    if As > Asmax:
        advs.append("As > As_max (doble armado). Aumentar sección.")

    return {
        "tipo_resultado": "VIGA_DOBLE",
        "pb":             round(pb(fc, fy), 6),
        "pmax":           round(pm, 6),
        "Mmax_tm":        round(Mmax_tm, 4),
        "A_prima_cm2":    round(A_prima, 4),
        "As_cm2":         round(As, 4),
        "As_min_cm2":     round(Asmin, 4),
        "As_max_cm2":     round(Asmax, 4),
        "fs_prima_kg":    round(fs_p, 2),
        "ok_sismico":     As <= Asmax,
        "advertencias":   "; ".join(advs),
    }


# ─────────────────────────────────────────────────────────────────────────────
# D — VIGA T
# ─────────────────────────────────────────────────────────────────────────────

def calcular_viga_t(bw: float, bp: float, t: float, d: float,
                     fc: float, fy: float, Mu_tm: float,
                     phi: float = PHI_FLEXION) -> dict:
    """Diseño viga T. Verifica si actúa como rectangular."""
    Cf_total     = 0.85 * fc * bp * t
    Mp_patin_tm  = phi * Cf_total * (d - t / 2) / 100_000

    if Mu_tm <= Mp_patin_tm:
        res = calcular_viga_simple(bp, d, fc, fy, Mu_tm, phi)
        res["tipo_resultado"] = "VIGA_T_RECTANGULAR"
        res["Mp_patin_tm"]    = round(Mp_patin_tm, 4)
        return res

    # Viga T real
    Cf    = 0.85 * fc * (bp - bw) * t
    Asf   = Cf / fy
    Mf_tm = phi * Cf * (d - t / 2) / 100_000

    DM_kgcm = (Mu_tm - Mf_tm) * 100_000
    K    = DM_kgcm / (phi * fc * bw * d**2)
    disc = 1 - 2.36 * K
    pw   = (fc / fy) * (1 - math.sqrt(disc)) / 1.18 if disc >= 0 else float('nan')
    Asw  = pw * bw * d if not math.isnan(pw) else float('nan')
    As   = Asw + Asf if not math.isnan(Asw) else float('nan')

    pb_rect = pb(fc, fy)
    pb_T    = (bw / bp) * (pb_rect + Asf / (bw * d))
    Asmax   = FMAX_SISMICO * pb_T * bp * d
    Asmin   = as_min(bw, d, fy)

    advs = []
    if math.isnan(As):
        advs.append("Sección imposible (alma). Aumentar bw o d.")
    elif As > Asmax:
        advs.append("As > As_max viga T. Aumentar sección.")

    As_final = max(As, Asmin) if not math.isnan(As) else None

    return {
        "tipo_resultado": "VIGA_T",
        "pb":             round(pb_rect, 6),
        "pmax":           round(FMAX_SISMICO * pb_T, 6),
        "Mp_patin_tm":    round(Mp_patin_tm, 4),
        "Asf_cm2":        round(Asf, 4),
        "Mf_tm":          round(Mf_tm, 4),
        "A_prima_cm2":    0.0,
        "As_cm2":         round(As_final, 4) if As_final is not None else None,
        "As_min_cm2":     round(Asmin, 4),
        "As_max_cm2":     round(Asmax, 4),
        "ok_sismico":     (not math.isnan(As)) and (As <= Asmax) if not math.isnan(As) else False,
        "advertencias":   "; ".join(advs),
    }


# ─────────────────────────────────────────────────────────────────────────────
# E — CORTANTE
# ─────────────────────────────────────────────────────────────────────────────

def vc_concreto(fc: float, Nu_kg: float = 0, Ag: float = 1) -> float:
    """Resistencia al cortante del concreto vc [kg/cm²]. ACI 318-19 §22.5.6."""
    vc_base = 0.53 * math.sqrt(fc)
    if Nu_kg == 0:
        return vc_base
    elif Nu_kg > 0:
        return vc_base * math.sqrt(1 + 0.0285 * Nu_kg / Ag)
    else:
        return max(vc_base * (1 + 0.0285 * Nu_kg / Ag), 0.0)


def vu_esfuerzo(Vu_t: float, bw: float, d: float,
                phi: float = PHI_CORTANTE) -> float:
    """vu = Vu / (φ·bw·d) [kg/cm²]. Vu en toneladas. 0 si geometría inválida."""
    denom = phi * bw * d
    if denom <= 0:
        return 0.0
    return Vu_t * 1000 / denom


def av_requerido(vu: float, vc: float, bw: float, S: float, fy: float) -> float:
    """Av (2 ramas) = (vu−vc)·bw·S/fy [cm²]. ACI 318-19 §22.5.8."""
    if vu <= vc:
        return 0.0
    return (vu - vc) * bw * S / fy


def av_minimo(bw: float, S: float, fy: float) -> float:
    """Av,min = 3.52·bw·S/fy. ACI 318-19 §9.6.3.3."""
    return 3.52 * bw * S / fy


def smax_cortante(d: float) -> float:
    """Separación máxima estribos por cortante = min(d/2, 60 cm)."""
    return min(d / 2, 60.0)


# ─────────────────────────────────────────────────────────────────────────────
# F — TORSIÓN
# ─────────────────────────────────────────────────────────────────────────────

def sum_x2y_rectangular(b: float, d: float) -> float:
    """Σx²y para sección rectangular simple = b²·d (x=b<d)."""
    x, y = (b, d) if b <= d else (d, b)
    return x**2 * y


def dim_estribo(b: float, d: float, recub: float = RECUB_DEFAULT):
    """x1, y1 dimensiones del estribo de eje a eje."""
    x1 = b - 2 * recub
    y1 = d - recub
    return x1, y1


def vtu_esfuerzo(Tu_tm: float, sum_x2y: float,
                 phi: float = PHI_CORTANTE) -> float:
    """vtu = 3·Tu / (φ·Σx²y) [kg/cm²]. Tu en t·m. ACI 318-71 §11.6."""
    return 3 * Tu_tm * 100_000 / (phi * sum_x2y)


def vtc_basico(fc: float) -> float:
    """vtc = 0.63·√f'c [kg/cm²]."""
    return 0.63 * math.sqrt(fc)


def vtcmax_combinado(fc: float, vu: float, vtu: float) -> float:
    """vtc,max con interacción cortante-torsión. ACI 318-71 §11.6.6.2."""
    if vtu == 0:
        return vtc_basico(fc)
    return 0.636 * math.sqrt(fc) / math.sqrt(1 + (1.2 * vu / vtu)**2)


def alpha_t(x1: float, y1: float) -> float:
    """αt = min(0.66 + 0.33·x1/y1, 1.50). ACI 318-71 §11.6.8."""
    return min(0.66 + 0.33 * x1 / y1, 1.50)


def at_requerido(vtu: float, vtc: float, S: float, sum_x2y: float,
                 x1: float, y1: float, fy: float) -> float:
    """At (1 rama) por torsión [cm²]. ACI 318-71 §11.6.8."""
    if vtu <= vtc:
        return 0.0
    at = alpha_t(x1, y1)
    return (vtu - vtc) * S * sum_x2y / (3 * at * x1 * y1 * fy)


def smax_torsion(x1: float, y1: float) -> float:
    """Smax por torsión = min((x1+y1)/4, 30 cm)."""
    return min((x1 + y1) / 4, 30.0)


def al_torsion(At: float, S: float, x1: float, y1: float,
               bw: float, vu: float, vtu: float, fy: float) -> float:
    """Al longitudinal por torsión [cm²]. ACI 318-71 §11.6.9."""
    opt1 = 2 * At * (x1 + y1) / S
    term_28   = 28 * bw * S / fy * (vtu / (vtu + vu)) if (vtu + vu) > 0 else 0
    opt2_base = (term_28 - 2 * At) * (x1 + y1) / S
    opt2_min  = (term_28 - 3.5 * bw * S / fy) * (x1 + y1) / S
    opt2 = max(opt2_base, opt2_min)
    return max(opt1, opt2)


# ─────────────────────────────────────────────────────────────────────────────
# G — COLUMNA: ESBELTEZ
# ─────────────────────────────────────────────────────────────────────────────

def radio_giro(t: float) -> float:
    """r = 0.3·t para sección rectangular. ACI aprox."""
    return 0.3 * t


def esbeltez(k: float, lu: float, r: float) -> float:
    """λ = k·lu / r."""
    return k * lu / r


def pc_euler(fc: float, Ig: float, k: float, lu: float, bd: float) -> float:
    """Carga crítica Euler Pc [t]. EI=Ec·Ig/(2.5·(1+βd))."""
    Ec = 15100 * math.sqrt(fc)
    EI = Ec * Ig / (2.5 * (1 + bd))
    Pc_kg = (math.pi**2 * EI) / (k * lu)**2
    return Pc_kg / 1000  # → t


def factor_amplificacion(Cm: float, Pu_t: float, Pc_t: float,
                          phi: float = PHI_COLUMNA) -> float:
    """δ = Cm/(1 − Pu/(φ·Pc)) ≥ 1.0. ACI 318-19 §6.6.4.4."""
    denom = 1 - Pu_t / (phi * Pc_t)
    if denom <= 0:
        return float('inf')
    return max(Cm / denom, 1.0)


# ─────────────────────────────────────────────────────────────────────────────
# H — TAKEOFF CSI 03
# ─────────────────────────────────────────────────────────────────────────────

def takeoff_viga(b: float, d: float, longitud_m: float,
                 As_cm2: float, A_prima_cm2: float = 0,
                 Av_cm2: float = 0, S_cm: float = S_DEFAULT,
                 Al_cm2: float = 0,
                 recubrimiento_cm: float = RECUB_DEFAULT,
                 factor_empalme: float = 1.15) -> dict:
    """
    Cantidades CSI 03 para viga rectangular.
    Returns: {concreto_m3, encofrado_m2, acero_kg, estribos_kg}
    """
    h_total = (d + recubrimiento_cm) / 100  # m
    b_m     = b / 100
    L       = longitud_m

    concreto_m3  = b_m * h_total * L
    encofrado_m2 = (2 * h_total + b_m) * L   # 2 laterales + fondo

    As_long_tot = As_cm2 + A_prima_cm2 + Al_cm2
    acero_kg    = As_long_tot * 1e-4 * L * DENSIDAD_ACERO * factor_empalme

    r_m          = recubrimiento_cm / 100
    bw_libre     = b_m - 2 * r_m
    d_libre      = h_total - 2 * r_m
    perim_est_m  = 2 * bw_libre + 2 * d_libre + 0.24  # +ganchos aprox
    n_estribos   = L / (S_cm / 100)
    estribos_kg  = Av_cm2 * 1e-4 * n_estribos * perim_est_m * DENSIDAD_ACERO

    return {
        "concreto_m3":  round(concreto_m3, 4),
        "encofrado_m2": round(encofrado_m2, 4),
        "acero_kg":     round(acero_kg, 2),
        "estribos_kg":  round(estribos_kg, 2),
    }


def takeoff_columna(lx: float, ly: float, longitud_m: float,
                    As_col_cm2: float, Av_cm2: float = 0,
                    S_cm: float = S_DEFAULT,
                    recubrimiento_cm: float = RECUB_DEFAULT,
                    factor_empalme: float = 1.15) -> dict:
    """
    Cantidades CSI 03 para columna rectangular.
    Returns: {concreto_m3, encofrado_m2, acero_kg, estribos_kg}
    """
    lx_m = lx / 100
    ly_m = ly / 100
    L    = longitud_m

    concreto_m3  = lx_m * ly_m * L
    encofrado_m2 = 2 * (lx_m + ly_m) * L  # 4 caras

    acero_kg     = As_col_cm2 * 1e-4 * L * DENSIDAD_ACERO * factor_empalme

    r_m         = recubrimiento_cm / 100
    bw_libre    = lx_m - 2 * r_m
    d_libre     = ly_m - 2 * r_m
    perim_est_m = 2 * bw_libre + 2 * d_libre + 0.24
    n_estribos  = L / (S_cm / 100)
    estribos_kg = Av_cm2 * 1e-4 * n_estribos * perim_est_m * DENSIDAD_ACERO

    return {
        "concreto_m3":  round(concreto_m3, 4),
        "encofrado_m2": round(encofrado_m2, 4),
        "acero_kg":     round(acero_kg, 2),
        "estribos_kg":  round(estribos_kg, 2),
    }


# ─────────────────────────────────────────────────────────────────────────────
# I — FUNCIÓN MAESTRA: calcular_caso
# ─────────────────────────────────────────────────────────────────────────────

def calcular_caso(elem: dict, caso: dict) -> dict:
    """
    Función maestra. Recibe dicts con campos de DisenoElemento y CasoDiseno.
    Retorna dict con todos los resultados para guardar en ResultadoDiseno.

    elem keys: tipo, b_cm, d_cm, d_prima_cm, bp_cm, t_cm, lx_cm, ly_cm,
               fc_kg_cm2, fy_kg_cm2, longitud_m
    caso keys: mu_tm, vu_t, tu_tm, nu_t, pu_t, mu_xx_tm, mu_yy_tm,
               lu_cm, k_x, k_y, bd_x, bd_y, cm_x, cm_y
    """
    tipo = elem.get("tipo", "VIGA_SIMPLE")
    fc   = float(elem["fc_kg_cm2"])
    fy   = float(elem["fy_kg_cm2"])
    b    = float(elem["b_cm"])
    d    = float(elem["d_cm"])
    d_p  = float(elem.get("d_prima_cm", 5))
    bp   = float(elem.get("bp_cm", 0))
    t_f  = float(elem.get("t_cm", 0))
    lx   = float(elem.get("lx_cm", 0))
    ly   = float(elem.get("ly_cm", 0))
    long = float(elem.get("longitud_m", 0))

    Mu   = float(caso.get("mu_tm", 0))
    Vu   = float(caso.get("vu_t", 0))
    Tu   = float(caso.get("tu_tm", 0))
    Nu   = float(caso.get("nu_t", 0))
    Pu   = float(caso.get("pu_t", 0))
    Mxx  = float(caso.get("mu_xx_tm", 0))
    Myy  = float(caso.get("mu_yy_tm", 0))
    lu   = float(caso.get("lu_cm", 0))
    kx   = float(caso.get("k_x", 1.0))
    ky   = float(caso.get("k_y", 1.0))
    bdx  = float(caso.get("bd_x", 0.15))
    bdy  = float(caso.get("bd_y", 0.15))
    cmx  = float(caso.get("cm_x", 1.0))
    cmy  = float(caso.get("cm_y", 1.0))

    # Validación de geometría. k_flexion/vu_esfuerzo retornan 0 si es inválida
    # (no crashean); aquí avisamos al usuario para que As=0 tenga explicación.
    _es_col_geom = (tipo == "COLUMNA")
    _bchk = lx if _es_col_geom else b
    _dchk = (ly - RECUB_DEFAULT) if _es_col_geom else d
    geom_aviso = ""
    if _bchk <= 0 or _dchk <= 0:
        geom_aviso = ("Geometría incompleta: define " +
                      ("lx y ly (columna)" if _es_col_geom else "b y d (viga)") +
                      " mayores que 0.")

    resultado = {}

    # ── FLEXIÓN ──────────────────────────────────────────────────────────────
    if tipo == "VIGA_SIMPLE":
        r = calcular_viga_simple(b, d, fc, fy, Mu)
    elif tipo == "VIGA_DOBLE":
        r = calcular_viga_doble(b, d, d_p, fc, fy, Mu)
    elif tipo == "VIGA_T":
        r = calcular_viga_t(b, bp, t_f, d, fc, fy, Mu)
    elif tipo == "COLUMNA":
        # Para columna: diseñar como viga simple en eje fuerte (Bresler simplificado)
        r = calcular_viga_simple(lx, ly - RECUB_DEFAULT, fc, fy, Mxx) if Mxx > 0 else {}
        r.setdefault("As_cm2", 0)
        r.setdefault("A_prima_cm2", 0)
        r.setdefault("ok_sismico", True)
        r.setdefault("advertencias", "")
        r.setdefault("pb", pb(fc, fy))
        r.setdefault("pmax", pmax_valor(fc, fy))
        r.setdefault("As_min_cm2", as_min(lx, ly, fy))
        r.setdefault("As_max_cm2", pmax_valor(fc, fy) * lx * ly)
    else:
        r = calcular_viga_simple(b, d, fc, fy, Mu)

    resultado["pb"]          = r.get("pb", pb(fc, fy))
    resultado["pmax"]        = r.get("pmax", pmax_valor(fc, fy))
    resultado["as_cm2"]      = r.get("As_cm2", 0) or 0
    resultado["a_prima_cm2"] = r.get("A_prima_cm2", 0) or 0
    resultado["as_min_cm2"]  = r.get("As_min_cm2", 0) or 0
    resultado["as_max_cm2"]  = r.get("As_max_cm2", 0) or 0
    resultado["ok_sismico"]  = r.get("ok_sismico", True)
    advertencias = r.get("advertencias", "")
    if geom_aviso:
        advertencias = f"{geom_aviso}; {advertencias}" if advertencias else geom_aviso

    # ── CORTANTE ─────────────────────────────────────────────────────────────
    bw = b if tipo != "COLUMNA" else lx
    d_eff = d if tipo != "COLUMNA" else (ly - RECUB_DEFAULT)
    Ag = b * d if tipo != "COLUMNA" else lx * ly

    vc = vc_concreto(fc, Nu_kg=Nu * 1000, Ag=Ag)
    vu = vu_esfuerzo(Vu, bw, d_eff) if Vu > 0 else 0.0
    s_estribo = S_DEFAULT
    Av = av_requerido(vu, vc, bw, s_estribo, fy)
    Av = max(Av, av_minimo(bw, s_estribo, fy)) if Vu > 0 else 0.0
    Smax_c = smax_cortante(d_eff)

    resultado["vc_kg_cm2"] = round(vc, 4)
    resultado["av_cm2"]    = round(Av, 4)

    # ── TORSIÓN ──────────────────────────────────────────────────────────────
    vtu = 0.0
    At  = 0.0
    Al  = 0.0
    vtu_val = 0.0
    Smax_t = Smax_c

    if Tu > 0:
        sx2y = sum_x2y_rectangular(bw, d_eff)
        x1, y1 = dim_estribo(bw, d_eff)
        vtu_val = vtu_esfuerzo(Tu, sx2y)
        vtc = vtcmax_combinado(fc, vu, vtu_val) if vu > 0 else vtc_basico(fc)
        At  = at_requerido(vtu_val, vtc, s_estribo, sx2y, x1, y1, fy)
        Smax_t = smax_torsion(x1, y1)
        if At > 0 and vu > 0:
            Al = al_torsion(At, s_estribo, x1, y1, bw, vu, vtu_val, fy)

    resultado["vtu_kg_cm2"] = round(vtu_val, 4)
    resultado["at_cm2"]     = round(At, 4)
    resultado["al_cm2"]     = round(Al, 4)
    resultado["s_max_cm"]   = round(min(Smax_c, Smax_t), 4)

    # ── ESBELTEZ COLUMNA ─────────────────────────────────────────────────────
    delta_x = 1.0
    delta_y = 1.0
    as_col  = resultado["as_cm2"]
    pg_pct  = 0.0

    if tipo == "COLUMNA" and lx > 0 and ly > 0:
        # Esbeltez (2º orden) — solo si se dio longitud libre lu
        if lu > 0:
            rx   = radio_giro(lx)
            ry   = radio_giro(ly)
            lam_x = esbeltez(kx, lu, rx)
            lam_y = esbeltez(ky, lu, ry)

            if lam_x > 22:
                Ig_x  = lx**3 * ly / 12
                Pc_x  = pc_euler(fc, Ig_x, kx, lu, bdx)
                if Pu > 0:
                    delta_x = factor_amplificacion(cmx, Pu, Pc_x)
                    if math.isinf(delta_x):
                        advertencias += "; Columna inestable eje X (δ→∞)"
                        delta_x = 99.0

            if lam_y > 22:
                Ig_y  = ly**3 * lx / 12
                Pc_y  = pc_euler(fc, Ig_y, ky, lu, bdy)
                if Pu > 0:
                    delta_y = factor_amplificacion(cmy, Pu, Pc_y)
                    if math.isinf(delta_y):
                        advertencias += "; Columna inestable eje Y (δ→∞)"
                        delta_y = 99.0

        # Cuantía geométrica ρg — siempre para una columna (no depende de esbeltez)
        Ag_col = lx * ly
        if as_col > 0:
            pg_pct = as_col / Ag_col * 100
            if pg_pct < 1.0:
                advertencias += f"; ρg={pg_pct:.2f}% < 1% ACI mínimo"
            if pg_pct > 8.0:
                advertencias += f"; ρg={pg_pct:.2f}% > 8% ACI máximo"

    resultado["delta_x"]   = round(delta_x, 4)
    resultado["delta_y"]   = round(delta_y, 4)
    resultado["as_col_cm2"] = round(as_col, 4)
    resultado["pg_pct"]    = round(pg_pct, 4)
    resultado["ok_pg"]     = (1.0 <= pg_pct <= 8.0) if pg_pct > 0 else True

    # ── TAKEOFF ──────────────────────────────────────────────────────────────
    tq = {}
    if long > 0:
        As_f  = resultado["as_cm2"]
        Ap_f  = resultado["a_prima_cm2"]
        Al_f  = resultado["al_cm2"]
        Av_f  = resultado["av_cm2"]
        At_f  = resultado["at_cm2"]
        Av_total = Av_f + 2 * At_f  # estribo combina cortante + torsión

        if tipo == "COLUMNA":
            tq = takeoff_columna(lx, ly, long, As_f, Av_total, S_DEFAULT)
        else:
            tq = takeoff_viga(b, d, long, As_f, Ap_f, Av_total, S_DEFAULT, Al_f)

    resultado["concreto_m3"]  = tq.get("concreto_m3", 0)
    resultado["encofrado_m2"] = tq.get("encofrado_m2", 0)
    resultado["acero_kg"]     = tq.get("acero_kg", 0)
    resultado["estribos_kg"]  = tq.get("estribos_kg", 0)

    resultado["advertencias"] = advertencias.lstrip("; ")

    return resultado


# ─────────────────────────────────────────────────────────────────────────────
# J — MEMORIA DE CÁLCULO (narrador descriptivo, estilo Excel / Mathcad)
# ─────────────────────────────────────────────────────────────────────────────
# Convierte el resultado del motor en una lista ORDENADA de pasos, cada uno con
# fórmula + sustitución + referencia ACI/CHOC + qué significa. Los valores son
# los mismos que calcular_caso() (única fuente de verdad). NO recalcula diseño.

def _fmt(v, dec: int = 3) -> str:
    """Formatea número para mostrar en sustitución. '—' si None/nan."""
    try:
        if v is None:
            return "—"
        f = float(v)
        if math.isnan(f):
            return "—"
        if abs(f) >= 1000:
            return f"{f:,.0f}"
        s = f"{f:.{dec}f}".rstrip("0").rstrip(".")
        return s if s not in ("", "-0") else "0"
    except (TypeError, ValueError):
        return str(v)


def _paso(seccion, simbolo, etiqueta, valor, unidad, formula, sustitucion,
          referencia, descripcion, tipo="intermedio") -> dict:
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
        "tipo":        tipo,   # input | intermedio | resultado | check | takeoff
        "latex":       None,   # fórmula simbólica en LaTeX (se rellena post-proceso)
        "latex_sub":   None,   # sustitución numérica en LaTeX
    }


# ── LaTeX: render idéntico al MD ─────────────────────────────────────────────
# Mapa fórmula-ASCII → LaTeX simbólico (verbatim del MD). El render del frontend
# (KaTeX) pinta esto como ecuación real. Si una clave no coincide, el frontend
# cae a la fórmula monospace (degradación elegante, sin romper).

_SUP = {"²":"2","³":"3","⁴":"4","⁵":"5","⁶":"6","⁷":"7","⁸":"8","⁹":"9",
        "⁰":"0","¹":"1","⁻":"-"}
_SUB_U = {"₀":"0","₁":"1","₂":"2","₃":"3","₄":"4"}


def _convert_sqrt(t: str) -> str:
    """Convierte √(...) y √token a \\sqrt{...} (paréntesis balanceado)."""
    out = []
    i = 0
    while i < len(t):
        if t[i] == "√":
            j = i + 1
            if j < len(t) and t[j] == "(":
                depth = 0; k = j
                while k < len(t):
                    if t[k] == "(":
                        depth += 1
                    elif t[k] == ")":
                        depth -= 1
                        if depth == 0:
                            break
                    k += 1
                inner = t[j + 1:k]
                out.append(r"\sqrt{" + _convert_sqrt(inner) + "}")
                i = k + 1
            else:
                k = j
                while k < len(t) and (t[k].isalnum() or t[k] in ".'"):
                    k += 1
                out.append(r"\sqrt{" + t[j:k] + "}")
                i = k
        else:
            out.append(t[i]); i += 1
    return "".join(out)


def _ascii_to_latex(s: str):
    """Convierte una sustitución numérica ASCII a LaTeX (best-effort).
    Si el texto es prosa (acentos castellanos o '%'), devuelve None →
    el frontend lo muestra en monospace en vez de forzarlo a notación math."""
    if not s or s == "—":
        return None
    if any(c in s for c in "áéíóúñÁÉÍÓÚÑ%"):
        return None
    import re as _re
    t = s
    t = _re.sub(r"[²³⁴⁵⁶⁷⁸⁹⁰¹⁻]+",
                lambda m: "^{" + "".join(_SUP[c] for c in m.group(0)) + "}", t)
    t = _re.sub(r"[₀₁₂₃₄]+",
                lambda m: "_{" + "".join(_SUB_U[c] for c in m.group(0)) + "}", t)
    t = _convert_sqrt(t)
    t = (t.replace("·", r" \cdot ").replace("×", r" \times ")
           .replace("−", "-").replace("≤", r" \le ").replace("≥", r" \ge ")
           .replace("≈", r" \approx ").replace("→", r" \rightarrow ")
           .replace("Σ", r"\Sigma ").replace("Δ", r"\Delta ")
           .replace("φ", r"\phi ").replace("α", r"\alpha ").replace("β", r"\beta ")
           .replace("ρ", r"\rho ").replace("λ", r"\lambda ").replace("δ", r"\delta ")
           .replace("π", r"\pi ").replace("’", "'"))
    return t


LATEX_BY_FORMULA = {
    # Materiales
    "Ec = 15100·√f'c": r"E_c = 15100\sqrt{f'_c}",
    "ρb = 0.85·f'c·β₁·6000 / (f'y·(6000+f'y))":
        r"\rho_b = \dfrac{0.85\,f'_c\,\beta_1 \cdot 6000}{f_y\,(6000+f_y)}",
    "ρmax = 0.5·ρb": r"\rho_{max} = 0.5\,\rho_b",
    "β₁ = 0.85 si f'c ≤ 280; si no max(1.05 − f'c/1400, 0.65)":
        r"\beta_1 = \begin{cases}0.85 & f'_c \le 280\\[2pt] 1.05 - \dfrac{f'_c}{1400} & f'_c > 280\end{cases}",
    # Flexión — común
    "Mmax = φ·f'c·b·d²·qmax·(1−0.59·qmax),  qmax = pmax·fy/f'c":
        r"M_{max} = \phi\,f'_c\,b\,d^2\,q_{max}(1-0.59\,q_{max}),\quad q_{max}=\dfrac{\rho_{max}\,f_y}{f'_c}",
    "K = Mu / (φ·f'c·b·d²),  φ = 0.90": r"K = \dfrac{M_u}{\phi\,f'_c\,b\,d^2}",
    "As,min = 14·b·d / fy": r"A_{s,min} = \dfrac{14\,b\,d}{f_y}",
    "As,max = pmax·b·d": r"A_{s,max} = \rho_{max}\,b\,d",
    "As = max(As_req, As,min)": r"A_s = \max(A_{s,req},\;A_{s,min})",
    # Flexión — viga simple
    "p = (f'c/fy)·(1 − √(1 − 2.36K)) / 1.18":
        r"\rho = \dfrac{f'_c}{f_y}\cdot\dfrac{1-\sqrt{1-2.36K}}{1.18}",
    "As = p·b·d": r"A_s = \rho\,b\,d",
    # Flexión — viga doble
    "ΔM = Mu − Mmax": r"\Delta M = M_u - M_{max}",
    "f's = 6000·[1 − (d'/d)·(1 + fy/6000)] ≤ fy":
        r"f'_s = 6000\left[1-\dfrac{d'}{d}\left(1+\dfrac{f_y}{6000}\right)\right]\le f_y",
    "A's = ΔM / (φ·f's·(d − d'))": r"A'_s = \dfrac{\Delta M}{\phi\,f'_s\,(d-d')}",
    "As1 = pmax·b·d": r"A_{s1} = \rho_{max}\,b\,d",
    "As2 = A's·f's/fy": r"A_{s2} = \dfrac{A'_s\,f'_s}{f_y}",
    "As = As1 + As2": r"A_s = A_{s1} + A_{s2}",
    # Flexión — viga T
    "Mp = φ·0.85·f'c·bp·t·(d − t/2)":
        r"M_p = \phi\cdot 0.85\,f'_c\,b_p\,t\left(d-\tfrac{t}{2}\right)",
    "p = (f'c/fy)·(1−√(1−2.36K))/1.18":
        r"\rho = \dfrac{f'_c}{f_y}\cdot\dfrac{1-\sqrt{1-2.36K}}{1.18}",
    "As = p·bp·d": r"A_s = \rho\,b_p\,d",
    "Asf = 0.85·f'c·(bp − bw)·t / fy":
        r"A_{sf} = \dfrac{0.85\,f'_c\,(b_p-b_w)\,t}{f_y}",
    "Mf = φ·Cf·(d − t/2)": r"M_f = \phi\,C_f\left(d-\tfrac{t}{2}\right)",
    "ΔM = Mu − Mf": r"\Delta M = M_u - M_f",
    "pw = (f'c/fy)·(1−√(1−2.36K))/1.18,  K = ΔM/(φ·f'c·bw·d²)":
        r"\rho_w = \dfrac{f'_c}{f_y}\cdot\dfrac{1-\sqrt{1-2.36K}}{1.18},\quad K=\dfrac{\Delta M}{\phi\,f'_c\,b_w\,d^2}",
    "Asw = pw·bw·d": r"A_{sw} = \rho_w\,b_w\,d",
    "As = Asw + Asf": r"A_s = A_{sw} + A_{sf}",
    # Cortante
    "vc = 0.53·√f'c": r"v_c = 0.53\sqrt{f'_c}",
    "vc = 0.53·√f'c·√(1 + 0.0285·Nu/Ag)   (compresión)":
        r"v_c = 0.53\sqrt{f'_c}\,\sqrt{1+0.0285\dfrac{N_u}{A_g}}",
    "vc = 0.53·√f'c·(1 + 0.0285·Nu/Ag)   (tensión, Nu<0)":
        r"v_c = 0.53\sqrt{f'_c}\left(1+0.0285\dfrac{N_u}{A_g}\right)",
    "vu = Vu / (φ·bw·d),  φ = 0.75": r"v_u = \dfrac{V_u}{\phi\,b_w\,d}",
    "Av,min = 3.52·bw·S / fy": r"A_{v,min} = \dfrac{3.52\,b_w\,S}{f_y}",
    "Av = max[ (vu − vc)·bw·S / fy ,  Av,min ]":
        r"A_v = \max\!\left[\dfrac{(v_u-v_c)\,b_w\,S}{f_y},\;A_{v,min}\right]",
    # Torsión
    "Σx²y = b²·h   (b = lado menor, h = lado mayor)":
        r"\Sigma x^2 y = b^2 h \quad(b=\text{lado menor})",
    "x₁ = bw − 2·rec ;  y₁ = d − rec   (rec = 4 cm)":
        r"x_1 = b_w - 2\,\text{rec};\quad y_1 = d - \text{rec}",
    "vtu = 3·Tu / (φ·Σx²y),  φ = 0.75":
        r"v_{tu} = \dfrac{3\,T_u}{\phi\,\Sigma x^2 y}",
    "vtc,max = 0.636·√f'c / √(1 + (1.2·vu/vtu)²)":
        r"v_{tc,max} = \dfrac{0.636\sqrt{f'_c}}{\sqrt{1+\left(\dfrac{1.2\,v_u}{v_{tu}}\right)^2}}",
    "vtc = 0.63·√f'c": r"v_{tc} = 0.63\sqrt{f'_c}",
    "αt = 0.66 + 0.33·(x₁/y₁) ≤ 1.50":
        r"\alpha_t = 0.66 + 0.33\,\dfrac{x_1}{y_1} \le 1.50",
    "At = (vtu − vtc)·S·Σx²y / (3·αt·x₁·y₁·fy)":
        r"A_t = \dfrac{(v_{tu}-v_{tc})\,S\,\Sigma x^2 y}{3\,\alpha_t\,x_1\,y_1\,f_y}",
    "Al = max[ 2·At·(x₁+y₁)/S ,  opción con mínimo ]":
        r"A_l = \max\!\left[\dfrac{2\,A_t\,(x_1+y_1)}{S},\;A_{l,min}\right]",
    "S,max = min[ cortante: d/2 ≤ 60 ;  torsión: (x₁+y₁)/4 ≤ 30 ]":
        r"S_{max} = \min\!\left[\tfrac{d}{2},\;\dfrac{x_1+y_1}{4}\right]",
    # Columna — esbeltez
    "r = 0.3·t   (X: 0.3·Lx,  Y: 0.3·Ly)":
        r"r = 0.3\,t \quad(r_x=0.3L_x,\; r_y=0.3L_y)",
    "λ = k·lu / r   (esbelta si λ > 22)":
        r"\lambda = \dfrac{k\,l_u}{r}\quad(\text{esbelta si }\lambda>22)",
    "Pc = π²·EI / (k·lu)²,  EI = Ec·Ig / (2.5·(1+βd))":
        r"P_c = \dfrac{\pi^2 EI}{(k\,l_u)^2},\quad EI=\dfrac{E_c I_g}{2.5(1+\beta_d)}",
    "δ = Cm / (1 − Pu/(φ·Pc)) ≥ 1.0,  φ = 0.65":
        r"\delta = \dfrac{C_m}{1-\dfrac{P_u}{\phi P_c}} \ge 1.0",
    "ρg = As_col / Ag · 100": r"\rho_g = \dfrac{A_{s,col}}{A_g}\cdot 100",
    # Takeoff
    "Vol = b · h · L,   h = (d + rec)/100":
        r"V = b\cdot h\cdot L,\quad h=\dfrac{d+\text{rec}}{100}",
    "Vol = Lx · Ly · L": r"V = L_x\cdot L_y\cdot L",
    "Enc = (2·h + b) · L   (2 laterales + fondo)":
        r"\text{Enc} = (2h+b)\cdot L",
    "Enc = 2·(Lx + Ly) · L   (4 caras)":
        r"\text{Enc} = 2(L_x+L_y)\cdot L",
    "Acl = (As + A's + Al) · 10⁻⁴ · L · 7850 · 1.15   (+15% empalmes)":
        r"\text{Acl} = (A_s+A'_s+A_l)\cdot 10^{-4}\cdot L\cdot 7850\cdot 1.15",
    "Acl = As_col · 10⁻⁴ · L · 7850 · 1.15   (+15% empalmes)":
        r"\text{Acl} = A_{s,col}\cdot 10^{-4}\cdot L\cdot 7850\cdot 1.15",
    "Aes = (Av + 2·At) · 10⁻⁴ · n · perím · 7850,   n = L / (S/100)":
        r"\text{Aes} = (A_v+2A_t)\cdot 10^{-4}\cdot n\cdot p_{est}\cdot 7850",
    # Cortante — criterio de estribos
    "comparar vu con vc/2 y vc":
        r"v_u \;\text{vs}\; \tfrac{v_c}{2}\,,\; v_c",
    # Columna — esbeltez no evaluada (fallback columna corta)
    "λ = k·lu/r no evaluada (falta lu)":
        r"\lambda = \dfrac{k\,l_u}{r}\;\Rightarrow\;\delta = 1.0\ \text{(columna corta)}",
    # Verificación
    "As_req ≤ ρmax·b·d": r"A_{s,req} \le \rho_{max}\,b\,d",
    "0.01 ≤ As/Ag ≤ 0.08": r"0.01 \le \dfrac{A_s}{A_g} \le 0.08",
}


def memoria_calculo(elem: dict, caso: dict) -> dict:
    """
    Devuelve la memoria de cálculo narrada de un caso.
    Retorna {meta:{...}, pasos:[...]} listo para pintar como hoja de cálculo.
    """
    res = calcular_caso(elem, caso)

    tipo   = elem.get("tipo", "VIGA_SIMPLE")
    es_col = (tipo == "COLUMNA")
    fc = float(elem["fc_kg_cm2"]); fy = float(elem["fy_kg_cm2"])
    b  = float(elem["b_cm"]);      d  = float(elem["d_cm"])
    d_p = float(elem.get("d_prima_cm", 5))
    bp  = float(elem.get("bp_cm", 0)); t_f = float(elem.get("t_cm", 0))
    lx = float(elem.get("lx_cm", 0)); ly = float(elem.get("ly_cm", 0))
    L  = float(elem.get("longitud_m", 0))

    Mu  = float(caso.get("mu_tm", 0));  Vu  = float(caso.get("vu_t", 0))
    Tu  = float(caso.get("tu_tm", 0));  Nu  = float(caso.get("nu_t", 0))
    Pu  = float(caso.get("pu_t", 0))
    Mxx = float(caso.get("mu_xx_tm", 0)); Myy = float(caso.get("mu_yy_tm", 0))

    b1  = beta1(fc); pbv = pb(fc, fy); pmv = pmax_valor(fc, fy)
    Ec  = 15100 * math.sqrt(fc)

    P = []  # pasos

    # ── MATERIALES ───────────────────────────────────────────────────────────
    P.append(_paso("Materiales", "f'c", "Resistencia del concreto", fc, "kg/cm²",
        "dato de proyecto", f"f'c = {_fmt(fc)}", "ACI 318-19 §19.2.1",
        "Resistencia a compresión especificada del concreto a 28 días.", "input"))
    P.append(_paso("Materiales", "f'y", "Fluencia del acero", fy, "kg/cm²",
        "dato de proyecto", f"f'y = {_fmt(fy)}", "ASTM A615 Gr60",
        "Esfuerzo de fluencia del acero de refuerzo longitudinal.", "input"))
    P.append(_paso("Materiales", "β₁", "Factor del bloque equivalente", round(b1, 4), "",
        "β₁ = 0.85 si f'c ≤ 280; si no max(1.05 − f'c/1400, 0.65)",
        f"f'c = {_fmt(fc)} → β₁ = {_fmt(b1)}", "ACI 318-19 §22.2.2.3",
        "Relaciona la altura del bloque rectangular de compresión con la del eje neutro.", "intermedio"))
    P.append(_paso("Materiales", "Ec", "Módulo de elasticidad", round(Ec, 0), "kg/cm²",
        "Ec = 15100·√f'c", f"15100·√{_fmt(fc)} = {_fmt(Ec)}", "ACI 318-19 §19.2.2.1",
        "Rigidez del concreto; gobierna deflexiones y la esbeltez de columna (Pc Euler).", "intermedio"))
    P.append(_paso("Materiales", "ρb", "Cuantía balanceada", round(pbv, 5), "",
        "ρb = 0.85·f'c·β₁·6000 / (f'y·(6000+f'y))",
        f"0.85·{_fmt(fc)}·{_fmt(b1)}·6000 / ({_fmt(fy)}·(6000+{_fmt(fy)})) = {_fmt(pbv,5)}",
        "ACI 318-19 §22.2.2",
        "Cuantía donde concreto y acero alcanzan su límite a la vez. Referencia teórica.", "intermedio"))
    P.append(_paso("Materiales", "ρmax", "Cuantía máxima (sísmica)", round(pmv, 5), "",
        "ρmax = 0.5·ρb", f"0.5·{_fmt(pbv,5)} = {_fmt(pmv,5)}", "ACI 318-19 §21 (falla dúctil)",
        "Tope de acero a tensión para garantizar falla dúctil en zona sísmica.", "intermedio"))

    # ── GEOMETRÍA ────────────────────────────────────────────────────────────
    if es_col:
        P.append(_paso("Geometría", "Lx·Ly", "Sección de columna",
            f"{_fmt(lx)}×{_fmt(ly)}", "cm", "dato / predimensionamiento",
            f"Ag = {_fmt(lx)}·{_fmt(ly)} = {_fmt(lx*ly)} cm²", "—",
            "Dimensiones de la columna. Ag = área bruta de la sección.", "input"))
    else:
        P.append(_paso("Geometría", "b", "Ancho (bw)", b, "cm", "dato / predimensionamiento",
            f"b = {_fmt(b)}", "—", "Ancho de la viga; en torsión y cortante actúa como bw.", "input"))
        P.append(_paso("Geometría", "d", "Peralte efectivo", d, "cm", "d = h − recubrimiento",
            f"d = {_fmt(d)}", "ACI 318-19 §20.5.1",
            "Distancia de la fibra en compresión al centroide del acero de tensión. NO es la altura total h.", "input"))
        if tipo == "VIGA_T":
            P.append(_paso("Geometría", "bp·t", "Patín de viga T", f"{_fmt(bp)}×{_fmt(t_f)}", "cm",
                "ancho colaborante · espesor de losa", f"bp = {_fmt(bp)}, t = {_fmt(t_f)}",
                "ACI 318-19 §6.3.2", "Define si el bloque de compresión cae en el patín o entra al alma.", "input"))
        if tipo == "VIGA_DOBLE":
            P.append(_paso("Geometría", "d'", "Recubrimiento a compresión", d_p, "cm",
                "dato", f"d' = {_fmt(d_p)}", "ACI 318-19 §20.5.1",
                "Posición del acero de compresión; controla si éste fluye (f's).", "input"))
    if L > 0:
        P.append(_paso("Geometría", "L", "Longitud del elemento", L, "m", "dato",
            f"L = {_fmt(L)}", "—", "Longitud usada para el takeoff de concreto, encofrado y acero.", "input"))

    # ── FLEXIÓN ──────────────────────────────────────────────────────────────
    as_v   = res.get("as_cm2", 0) or 0
    asmin  = res.get("as_min_cm2", 0) or 0
    asmax  = res.get("as_max_cm2", 0) or 0
    aprima = res.get("a_prima_cm2", 0) or 0

    if not es_col:
        K  = k_flexion(Mu, b, d, fc)
        qm = pmv * fy / fc
        Mm = mmax(b, d, fc, fy)
        P.append(_paso("Flexión", "Mu", "Momento último de diseño", Mu, "t·m",
            "demanda del análisis estructural", f"Mu = {_fmt(Mu)}", "MD §2.4",
            "Momento flector último; viene del análisis (combinación gobernante).", "input"))
        P.append(_paso("Flexión", "Mmax", "Momento máximo con pmax", round(Mm, 3), "t·m",
            "Mmax = φ·f'c·b·d²·qmax·(1−0.59·qmax),  qmax = pmax·fy/f'c",
            f"0.90·{_fmt(fc)}·{_fmt(b)}·{_fmt(d)}²·{_fmt(qm,4)}·(1−0.59·{_fmt(qm,4)}) = {_fmt(Mm)}",
            "MD §3.3 · ACI 318-71",
            "Momento resistente con cuantía máxima. Si Mu > Mmax la viga necesita doble armado.", "intermedio"))
        P.append(_paso("Flexión", "K", "Índice de resistencia", round(K, 5), "",
            "K = Mu / (φ·f'c·b·d²),  φ = 0.90",
            f"{_fmt(Mu)}·10⁵ / (0.90·{_fmt(fc)}·{_fmt(b)}·{_fmt(d)}²) = {_fmt(K,5)}",
            "MD §3.4 · ACI 318-71",
            "Demanda adimensional de flexión (de aquí sale la cuantía).", "intermedio"))

        if tipo == "VIGA_DOBLE":
            fsp = fs_compresion(d, d_p, fy)
            dM  = Mu - Mm
            As1 = pmv * b * d
            As2 = aprima * fsp / fy
            P.append(_paso("Flexión", "ΔM", "Momento incremental", round(dM, 3), "t·m",
                "ΔM = Mu − Mmax", f"{_fmt(Mu)} − {_fmt(Mm)} = {_fmt(dM)}", "MD §4.1",
                "Exceso de momento sobre Mmax que toma el doble armado.", "intermedio"))
            P.append(_paso("Flexión", "f's", "Esfuerzo del acero a compresión", round(fsp, 1), "kg/cm²",
                "f's = 6000·[1 − (d'/d)·(1 + fy/6000)] ≤ fy",
                f"6000·[1 − ({_fmt(d_p)}/{_fmt(d)})·(1+{_fmt(fy)}/6000)] = {_fmt(fsp,1)}",
                "MD §4.2 · ACI 318-71",
                "Tensión del acero de compresión por compatibilidad; si < fy no fluye.", "intermedio"))
            P.append(_paso("Flexión", "A's", "Acero a compresión", round(aprima, 3), "cm²",
                "A's = ΔM / (φ·f's·(d − d'))",
                f"{_fmt(dM)}·10⁵ / (0.90·{_fmt(fsp,1)}·({_fmt(d)}−{_fmt(d_p)})) = {_fmt(aprima)}",
                "MD §4.3 · ACI 318-71", "Acero de compresión requerido.", "resultado"))
            P.append(_paso("Flexión", "As1", "Acero a tensión por Mmax", round(As1, 3), "cm²",
                "As1 = pmax·b·d", f"{_fmt(pmv,5)}·{_fmt(b)}·{_fmt(d)} = {_fmt(As1)}",
                "MD §4.5", "Componente de tensión asociada al momento máximo.", "intermedio"))
            P.append(_paso("Flexión", "As2", "Acero a tensión por ΔM", round(As2, 3), "cm²",
                "As2 = A's·f's/fy", f"{_fmt(aprima)}·{_fmt(fsp,1)}/{_fmt(fy)} = {_fmt(As2)}",
                "MD §4.4", "Componente de tensión que equilibra al acero de compresión.", "intermedio"))
            P.append(_paso("Flexión", "As", "Acero a tensión total", round(as_v, 3), "cm²",
                "As = As1 + As2", f"{_fmt(As1)} + {_fmt(As2)} = {_fmt(as_v)}",
                "MD §4.6 · ACI 318-71", "Acero de tensión total de la viga doblemente armada.", "resultado"))

        elif tipo == "VIGA_T":
            Cf_tot = 0.85 * fc * bp * t_f
            Mp = PHI_FLEXION * Cf_tot * (d - t_f / 2) / 100_000
            P.append(_paso("Flexión", "Mp", "Momento del patín", round(Mp, 3), "t·m",
                "Mp = φ·0.85·f'c·bp·t·(d − t/2)",
                f"0.90·0.85·{_fmt(fc)}·{_fmt(bp)}·{_fmt(t_f)}·({_fmt(d)}−{_fmt(t_f)}/2) = {_fmt(Mp)}",
                "MD §5.1 · ACI 318-71",
                "Momento que resiste el patín. Si Mu ≤ Mp se diseña rectangular de ancho bp.", "intermedio"))
            if Mu <= Mp:
                K2 = k_flexion(Mu, bp, d, fc)
                p2 = cuantia_requerida(K2, fc, fy)
                P.append(_paso("Flexión", "p", "Cuantía requerida (rectangular bp)",
                    round(p2, 5) if not math.isnan(p2) else None, "",
                    "p = (f'c/fy)·(1−√(1−2.36K))/1.18",
                    f"({_fmt(fc)}/{_fmt(fy)})·(1−√(1−2.36·{_fmt(K2,5)}))/1.18 = {_fmt(p2,5)}",
                    "MD §3.5 · ACI 318-71", "El bloque cae en el patín: actúa como viga rectangular de ancho bp.", "intermedio"))
                P.append(_paso("Flexión", "As", "Acero a tensión", round(as_v, 3), "cm²",
                    "As = p·bp·d", f"{_fmt(p2,5)}·{_fmt(bp)}·{_fmt(d)} = {_fmt(as_v)}",
                    "MD §3.6 · ACI 318-71", "Acero de tensión (sección actúa rectangular).", "resultado"))
            else:
                Cf  = 0.85 * fc * (bp - b) * t_f
                Asf = Cf / fy
                Mf  = PHI_FLEXION * Cf * (d - t_f / 2) / 100_000
                dM  = Mu - Mf
                Kw  = k_flexion(dM, b, d, fc)
                pw  = cuantia_requerida(Kw, fc, fy)
                Asw = pw * b * d if not math.isnan(pw) else float('nan')
                P.append(_paso("Flexión", "Asf", "Acero equivalente del patín", round(Asf, 3), "cm²",
                    "Asf = 0.85·f'c·(bp − bw)·t / fy",
                    f"0.85·{_fmt(fc)}·({_fmt(bp)}−{_fmt(b)})·{_fmt(t_f)}/{_fmt(fy)} = {_fmt(Asf)}",
                    "MD §5.3 · ACI 318-71", "Acero que equilibra la compresión de las alas.", "intermedio"))
                P.append(_paso("Flexión", "Mf", "Momento de las alas", round(Mf, 3), "t·m",
                    "Mf = φ·Cf·(d − t/2)",
                    f"0.90·{_fmt(Cf)}·({_fmt(d)}−{_fmt(t_f)}/2)·10⁻⁵ = {_fmt(Mf)}",
                    "MD §5.4", "Momento resistido por las alas.", "intermedio"))
                P.append(_paso("Flexión", "ΔM", "Momento al alma", round(dM, 3), "t·m",
                    "ΔM = Mu − Mf", f"{_fmt(Mu)} − {_fmt(Mf)} = {_fmt(dM)}", "MD §5.5",
                    "Momento que toma el alma.", "intermedio"))
                P.append(_paso("Flexión", "pw", "Cuantía del alma",
                    round(pw, 5) if not math.isnan(pw) else None, "",
                    "pw = (f'c/fy)·(1−√(1−2.36K))/1.18,  K = ΔM/(φ·f'c·bw·d²)",
                    f"K = {_fmt(Kw,5)} → pw = {_fmt(pw,5)}", "MD §5.6–5.7", "Cuantía del alma por ΔM.", "intermedio"))
                P.append(_paso("Flexión", "Asw", "Acero del alma",
                    round(Asw, 3) if not math.isnan(Asw) else None, "cm²",
                    "Asw = pw·bw·d", f"{_fmt(pw,5)}·{_fmt(b)}·{_fmt(d)} = {_fmt(Asw)}",
                    "MD §5.8", "Acero de tensión del alma.", "intermedio"))
                P.append(_paso("Flexión", "As", "Acero a tensión total", round(as_v, 3), "cm²",
                    "As = Asw + Asf", f"{_fmt(Asw)} + {_fmt(Asf)} = {_fmt(as_v)}",
                    "MD §5.9 · ACI 318-71", "Acero total de tensión de la viga T.", "resultado"))

        else:  # VIGA_SIMPLE
            p_req   = cuantia_requerida(K, fc, fy)
            As_calc = p_req * b * d if not math.isnan(p_req) else float('nan')
            P.append(_paso("Flexión", "p", "Cuantía requerida",
                round(p_req, 5) if not math.isnan(p_req) else None, "",
                "p = (f'c/fy)·(1 − √(1 − 2.36K)) / 1.18",
                f"({_fmt(fc)}/{_fmt(fy)})·(1−√(1−2.36·{_fmt(K,5)}))/1.18 = {_fmt(p_req,5)}",
                "MD §3.5 · ACI 318-71",
                "Cuantía de acero a tensión que pide el momento. '—' si K>0.424 (sección imposible).", "intermedio"))
            P.append(_paso("Flexión", "As(req)", "Acero a tensión requerido",
                round(As_calc, 3) if not math.isnan(As_calc) else None, "cm²",
                "As = p·b·d", f"{_fmt(p_req,5)}·{_fmt(b)}·{_fmt(d)} = {_fmt(As_calc)}",
                "MD §3.6 · ACI 318-71", "Acero por resistencia, antes de aplicar mínimos.", "intermedio"))

        # ── comunes a toda viga ──
        P.append(_paso("Flexión", "As,min", "Acero mínimo", round(asmin, 3), "cm²",
            "As,min = 14·b·d / fy", f"14·{_fmt(b)}·{_fmt(d)}/{_fmt(fy)} = {_fmt(asmin)}",
            "MD §3.7 · ACI 318-71", "Piso por control de fisuración. As final = max(As_req, As,min).", "check"))
        P.append(_paso("Flexión", "As,max", "Acero máximo sísmico", round(asmax, 3), "cm²",
            "As,max = pmax·b·d", f"{_fmt(pmv,5)}·{_fmt(b)}·{_fmt(d)} = {_fmt(asmax)}",
            "MD §13 · ACI 318-71", "Techo por ductilidad. Si As_req > As,max la sección no pasa.", "check"))
        if tipo not in ("VIGA_DOBLE", "VIGA_T"):
            P.append(_paso("Flexión", "As", "Acero adoptado", round(as_v, 3), "cm²",
                "As = max(As_req, As,min)", f"max(As_req, {_fmt(asmin)}) = {_fmt(as_v)}",
                "MD §3.6", "Acero de tensión final que va al armado y al takeoff.", "resultado"))
    else:
        P.append(_paso("Flexión", "Mxx", "Momento eje fuerte", Mxx, "t·m",
            "demanda del análisis estructural", f"Mxx = {_fmt(Mxx)}", "MD §9.1 (Mu_xx)",
            "Momento en el eje fuerte. Cálculo simplificado: As por flexión uniaxial (As exacto P-M-M se importará).", "input"))
        P.append(_paso("Flexión", "Myy", "Momento eje débil", Myy, "t·m",
            "demanda del análisis estructural", f"Myy = {_fmt(Myy)}", "MD §9.1 (Mu_yy)",
            "Momento en el eje débil. La interacción biaxial de Bresler (MD §11) se evalúa con el acero importado.", "input"))

    # ── CORTANTE ─────────────────────────────────────────────────────────────
    bw    = b if not es_col else lx
    d_eff = d if not es_col else (ly - RECUB_DEFAULT)
    Ag    = b * d if not es_col else lx * ly
    vc    = res.get("vc_kg_cm2", 0) or 0
    av    = res.get("av_cm2", 0) or 0
    vu_e  = vu_esfuerzo(Vu, bw, d_eff) if Vu > 0 else 0.0

    P.append(_paso("Cortante", "Vu", "Cortante último", Vu, "t",
        "demanda del análisis estructural", f"Vu = {_fmt(Vu)}", "MD §2.4",
        "Fuerza cortante última (a distancia d de la cara del apoyo).", "input"))
    if Nu > 0:
        vc_for = "vc = 0.53·√f'c·√(1 + 0.0285·Nu/Ag)   (compresión)"
        vc_sub = f"0.53·√{_fmt(fc)}·√(1+0.0285·{_fmt(Nu*1000)}/{_fmt(Ag)}) = {_fmt(vc)}"
    elif Nu < 0:
        vc_for = "vc = 0.53·√f'c·(1 + 0.0285·Nu/Ag)   (tensión, Nu<0)"
        vc_sub = f"0.53·√{_fmt(fc)}·(1+0.0285·{_fmt(Nu*1000)}/{_fmt(Ag)}) = {_fmt(vc)}"
    else:
        vc_for = "vc = 0.53·√f'c"
        vc_sub = f"0.53·√{_fmt(fc)} = {_fmt(vc)}"
    P.append(_paso("Cortante", "vc", "Resistencia del concreto", round(vc, 3), "kg/cm²",
        vc_for, vc_sub, "MD §6.2 · ACI 318-71",
        "Cortante que resiste el concreto solo (ajustado por axial si Nu≠0).", "intermedio"))
    P.append(_paso("Cortante", "vu", "Esfuerzo cortante último", round(vu_e, 3), "kg/cm²",
        "vu = Vu / (φ·bw·d),  φ = 0.75",
        f"{_fmt(Vu)}·1000 / (0.75·{_fmt(bw)}·{_fmt(d_eff)}) = {_fmt(vu_e)}",
        "MD §6.1 · ACI 318-71", "Demanda de cortante; se compara contra vc.", "intermedio"))
    if vu_e <= vc / 2:
        crit = "vu ≤ vc/2 → no requiere estribos por resistencia"
    elif vu_e <= vc:
        crit = "vc/2 < vu ≤ vc → estribos mínimos"
    else:
        crit = "vu > vc → estribos por resistencia"
    P.append(_paso("Cortante", "criterio", "¿Requiere estribos?", crit, "",
        "comparar vu con vc/2 y vc",
        f"vu={_fmt(vu_e)} · vc/2={_fmt(vc/2)} · vc={_fmt(vc)}",
        "MD §6.3 · ACI 318-71", "Define si la viga necesita estribos por resistencia.", "check"))
    avmin = av_minimo(bw, S_DEFAULT, fy) if Vu > 0 else 0.0
    P.append(_paso("Cortante", "Av,min", "Estribo mínimo", round(avmin, 4), "cm²",
        "Av,min = 3.52·bw·S / fy",
        f"3.52·{_fmt(bw)}·{S_DEFAULT:.0f}/{_fmt(fy)} = {_fmt(avmin,4)}",
        "MD §6.4 · ACI 318-71", f"Área mínima de estribo (2 ramas) por S = {S_DEFAULT:.0f} cm.", "check"))
    P.append(_paso("Cortante", "Av/S", "Área de estribo adoptada", round(av, 4), "cm²",
        "Av = max[ (vu − vc)·bw·S / fy ,  Av,min ]",
        f"max[({_fmt(vu_e)}−{_fmt(vc)})·{_fmt(bw)}·{S_DEFAULT:.0f}/{_fmt(fy)}, {_fmt(avmin,4)}] = {_fmt(av,4)}",
        "MD §6.5 · ACI 318-71", f"Área de estribo (2 ramas) por separación S = {S_DEFAULT:.0f} cm.", "resultado"))

    # ── TORSIÓN (solo si Tu > 0) — MD §7 ─────────────────────────────────────
    if Tu > 0:
        vtu  = res.get("vtu_kg_cm2", 0) or 0
        at   = res.get("at_cm2", 0) or 0
        al   = res.get("al_cm2", 0) or 0
        smax = res.get("s_max_cm", 0) or 0
        sx2y   = sum_x2y_rectangular(bw, d_eff)
        x1, y1 = dim_estribo(bw, d_eff)
        vtc  = vtcmax_combinado(fc, vu_e, vtu) if vu_e > 0 else vtc_basico(fc)
        at_v = alpha_t(x1, y1)
        xmin, xmax = (min(bw, d_eff), max(bw, d_eff))
        P.append(_paso("Torsión", "Tu", "Torsión última", Tu, "t·m",
            "demanda del análisis estructural", f"Tu = {_fmt(Tu)}", "MD §2.4",
            "Momento torsor último de la combinación. Activa estribo cerrado + acero longitudinal adicional.", "input"))
        P.append(_paso("Torsión", "Σx²y", "Rigidez torsional de la sección", round(sx2y, 1), "cm³",
            "Σx²y = b²·h   (b = lado menor, h = lado mayor)",
            f"{_fmt(xmin)}²·{_fmt(xmax)} = {_fmt(sx2y,1)}", "MD §7.1 · ACI 318-71 §11.6 (fórmulas clásicas en uso)",
            "Suma de (lado menor)²·(lado mayor) de los rectángulos. Sección rectangular: b²·h.", "intermedio"))
        P.append(_paso("Torsión", "x₁·y₁", "Lados del estribo cerrado", f"{_fmt(x1)}×{_fmt(y1)}", "cm",
            "x₁ = bw − 2·rec ;  y₁ = d − rec   (rec = 4 cm)",
            f"x₁ = {_fmt(bw)}−2·4 = {_fmt(x1)} ;  y₁ = {_fmt(d_eff)}−4 = {_fmt(y1)}",
            "MD §7 · ACI 318-71 §11.6 (fórmulas clásicas en uso)", "Dimensiones del estribo cerrado medidas de eje a eje.", "intermedio"))
        P.append(_paso("Torsión", "vtu", "Esfuerzo de torsión último", round(vtu, 3), "kg/cm²",
            "vtu = 3·Tu / (φ·Σx²y),  φ = 0.75",
            f"3·{_fmt(Tu)}·10⁵ / (0.75·{_fmt(sx2y,1)}) = {_fmt(vtu)}", "MD §7.1 · ACI 318-71 §11.6 (fórmulas clásicas en uso)",
            "Esfuerzo torsional último. Si vtu ≤ 0.4·√f'c la torsión se desprecia (MD §7.2).", "intermedio"))
        if vu_e > 0:
            vtc_for = "vtc,max = 0.636·√f'c / √(1 + (1.2·vu/vtu)²)"
            vtc_sub = f"0.636·√{_fmt(fc)} / √(1+(1.2·{_fmt(vu_e)}/{_fmt(vtu)})²) = {_fmt(vtc)}"
            vtc_ref = "MD §7.4 · ACI 318-71 §11.6 (fórmulas clásicas en uso)"
        else:
            vtc_for = "vtc = 0.63·√f'c"
            vtc_sub = f"0.63·√{_fmt(fc)} = {_fmt(vtc)}"
            vtc_ref = "MD §7.3 · ACI 318-71 §11.6 (fórmulas clásicas en uso)"
        P.append(_paso("Torsión", "vtc", "Resistencia del concreto a torsión", round(vtc, 3), "kg/cm²",
            vtc_for, vtc_sub, vtc_ref,
            "Torsión que toma el concreto solo; con cortante se reduce por la interacción vu–vtu.", "intermedio"))
        P.append(_paso("Torsión", "αt", "Factor de estribo por torsión", round(at_v, 4), "",
            "αt = 0.66 + 0.33·(x₁/y₁) ≤ 1.50",
            f"0.66 + 0.33·({_fmt(x1)}/{_fmt(y1)}) = {_fmt(at_v)}", "MD §7.6 · ACI 318-71 §11.6 (fórmulas clásicas en uso)",
            "Factor geométrico del estribo cerrado por torsión.", "intermedio"))
        P.append(_paso("Torsión", "At/S", "Estribo por torsión (1 rama)", round(at, 4), "cm²",
            "At = (vtu − vtc)·S·Σx²y / (3·αt·x₁·y₁·fy)",
            f"({_fmt(vtu)}−{_fmt(vtc)})·{S_DEFAULT:.0f}·{_fmt(sx2y,1)} / "
            f"(3·{_fmt(at_v)}·{_fmt(x1)}·{_fmt(y1)}·{_fmt(fy)}) = {_fmt(at,4)}",
            "MD §7.7 · ACI 318-71 §11.6 (fórmulas clásicas en uso)",
            "Área de UNA rama del estribo cerrado por torsión. Se SUMA al cortante: Av + 2·At.", "resultado"))
        P.append(_paso("Torsión", "Al", "Acero longitudinal por torsión", round(al, 3), "cm²",
            "Al = max[ 2·At·(x₁+y₁)/S ,  opción con mínimo ]",
            f"2·{_fmt(at,4)}·({_fmt(x1)}+{_fmt(y1)})/{S_DEFAULT:.0f} = {_fmt(al)}",
            "MD §7.9 · ACI 318-71 §11.6 (fórmulas clásicas en uso)",
            "Acero longitudinal extra distribuido en el perímetro de la sección.", "resultado"))
        P.append(_paso("Torsión", "S,max", "Separación máxima de estribos", round(smax, 2), "cm",
            "S,max = min[ cortante: d/2 ≤ 60 ;  torsión: (x₁+y₁)/4 ≤ 30 ]",
            f"min[ {_fmt(d_eff/2)} , ({_fmt(x1)}+{_fmt(y1)})/4 = {_fmt((x1+y1)/4)} ] = {_fmt(smax,2)}",
            "MD §7.8 · ACI 318-71 §11.6 (fórmulas clásicas en uso)", "Separación máxima de estribos; gobierna el menor de cortante y torsión.", "check"))

    # ── COLUMNA: ESBELTEZ + CUANTÍA — MD §10 ─────────────────────────────────
    if es_col:
        dx = res.get("delta_x", 1.0) or 1.0
        dy = res.get("delta_y", 1.0) or 1.0
        ascol = res.get("as_col_cm2", 0) or 0
        pg = res.get("pg_pct", 0) or 0
        lu  = float(caso.get("lu_cm", 0) or 0)
        kx  = float(caso.get("k_x", 1) or 1);  ky  = float(caso.get("k_y", 1) or 1)
        bdx = float(caso.get("bd_x", 0.15) or 0.15); bdy = float(caso.get("bd_y", 0.15) or 0.15)
        cmx = float(caso.get("cm_x", 1) or 1); cmy = float(caso.get("cm_y", 1) or 1)
        P.append(_paso("Columna", "Pu", "Carga axial última", Pu, "t",
            "demanda del análisis estructural", f"Pu = {_fmt(Pu)}", "MD §9.1",
            "Carga axial última de compresión sobre la columna.", "input"))
        if lu > 0 and lx > 0 and ly > 0:
            rx = radio_giro(lx); ry = radio_giro(ly)
            lam_x = esbeltez(kx, lu, rx); lam_y = esbeltez(ky, lu, ry)
            P.append(_paso("Columna", "r", "Radio de giro", f"{_fmt(rx)} / {_fmt(ry)}", "cm",
                "r = 0.3·t   (X: 0.3·Lx,  Y: 0.3·Ly)",
                f"rx = 0.3·{_fmt(lx)} = {_fmt(rx)} ;  ry = 0.3·{_fmt(ly)} = {_fmt(ry)}",
                "MD §10.4 · ACI 318-71", "Radio de giro de la sección rectangular por dirección.", "intermedio"))
            P.append(_paso("Columna", "λ", "Relación de esbeltez (X / Y)",
                f"{_fmt(lam_x,2)} / {_fmt(lam_y,2)}", "",
                "λ = k·lu / r   (esbelta si λ > 22)",
                f"λx = {_fmt(kx)}·{_fmt(lu)}/{_fmt(rx)} = {_fmt(lam_x,2)} ;  "
                f"λy = {_fmt(ky)}·{_fmt(lu)}/{_fmt(ry)} = {_fmt(lam_y,2)}",
                "MD §10.4–10.5 · ACI 318-71",
                "Esbeltez por dirección. Si λ ≤ 22 se ignora el 2º orden (δ = 1).", "intermedio"))
            if lam_x > 22:
                Ig_x = lx**3 * ly / 12
                Pc_x = pc_euler(fc, Ig_x, kx, lu, bdx)
                P.append(_paso("Columna", "Pc-X", "Carga crítica de Euler (eje X)", round(Pc_x, 2), "t",
                    "Pc = π²·EI / (k·lu)²,  EI = Ec·Ig / (2.5·(1+βd))",
                    f"Ig = {_fmt(lx)}³·{_fmt(ly)}/12 = {_fmt(Ig_x,0)} cm⁴ → Pc = {_fmt(Pc_x)}",
                    "MD §10.7 · ACI 318-71", "Carga de pandeo de Euler en el eje fuerte.", "intermedio"))
            if lam_y > 22:
                Ig_y = ly**3 * lx / 12
                Pc_y = pc_euler(fc, Ig_y, ky, lu, bdy)
                P.append(_paso("Columna", "Pc-Y", "Carga crítica de Euler (eje Y)", round(Pc_y, 2), "t",
                    "Pc = π²·EI / (k·lu)²,  EI = Ec·Ig / (2.5·(1+βd))",
                    f"Ig = {_fmt(ly)}³·{_fmt(lx)}/12 = {_fmt(Ig_y,0)} cm⁴ → Pc = {_fmt(Pc_y)}",
                    "MD §10.7 · ACI 318-71", "Carga de pandeo de Euler en el eje débil.", "intermedio"))
            P.append(_paso("Columna", "δx", "Amplificador de momento X", round(dx, 3), "",
                "δ = Cm / (1 − Pu/(φ·Pc)) ≥ 1.0,  φ = 0.65",
                (f"{_fmt(cmx)} / (1 − {_fmt(Pu)}/(0.65·Pc-X)) = {_fmt(dx)}" if lam_x > 22
                 else f"λx = {_fmt(lam_x,2)} ≤ 22 → δx = 1.0"),
                "MD §10.8 · ACI 318-71",
                "Amplifica Mxx por esbeltez (2º orden). δ>1 ⇒ columna esbelta.", "intermedio"))
            P.append(_paso("Columna", "δy", "Amplificador de momento Y", round(dy, 3), "",
                "δ = Cm / (1 − Pu/(φ·Pc)) ≥ 1.0,  φ = 0.65",
                (f"{_fmt(cmy)} / (1 − {_fmt(Pu)}/(0.65·Pc-Y)) = {_fmt(dy)}" if lam_y > 22
                 else f"λy = {_fmt(lam_y,2)} ≤ 22 → δy = 1.0"),
                "MD §10.8 · ACI 318-71", "Amplificador de esbeltez en el eje débil.", "intermedio"))
        else:
            P.append(_paso("Columna", "δ", "Amplificador de momento", "1.00 / 1.00", "",
                "λ = k·lu/r no evaluada (falta lu)", "δx = δy = 1.0  (columna corta)", "MD §10.5",
                "No se ingresó longitud libre lu: se asume columna corta sin amplificación (δ = 1).", "intermedio"))
        P.append(_paso("Columna", "ρg", "Cuantía geométrica", round(pg, 3), "%",
            "ρg = As_col / Ag · 100", f"{_fmt(ascol)}/{_fmt(lx*ly)}·100 = {_fmt(pg)}",
            "MD §9.8 · ACI 318-71", "Acero longitudinal total / área bruta. ACI: 1% ≤ ρg ≤ 8%.", "check"))

    # ── TAKEOFF CSI 03 — cantidades reales (sección · longitud) ──────────────
    if L > 0:
        vol = res.get("concreto_m3", 0) or 0
        enc = res.get("encofrado_m2", 0) or 0
        acl = res.get("acero_kg", 0) or 0
        aes = res.get("estribos_kg", 0) or 0
        if es_col:
            lxm = lx / 100; lym = ly / 100
            ascol_t = res.get("as_col_cm2", 0) or 0
            vol_for = "Vol = Lx · Ly · L"
            vol_sub = f"{_fmt(lxm)}·{_fmt(lym)}·{_fmt(L)} = {_fmt(vol,4)}"
            enc_for = "Enc = 2·(Lx + Ly) · L   (4 caras)"
            enc_sub = f"2·({_fmt(lxm)}+{_fmt(lym)})·{_fmt(L)} = {_fmt(enc,4)}"
            acl_for = "Acl = As_col · 10⁻⁴ · L · 7850 · 1.15   (+15% empalmes)"
            acl_sub = f"{_fmt(ascol_t)}·10⁻⁴·{_fmt(L)}·7850·1.15 = {_fmt(acl,2)}"
        else:
            h_tot = (d + RECUB_DEFAULT) / 100; b_m = b / 100
            al_t = res.get("al_cm2", 0) or 0
            vol_for = "Vol = b · h · L,   h = (d + rec)/100"
            vol_sub = f"{_fmt(b_m)}·{_fmt(h_tot)}·{_fmt(L)} = {_fmt(vol,4)}"
            enc_for = "Enc = (2·h + b) · L   (2 laterales + fondo)"
            enc_sub = f"(2·{_fmt(h_tot)}+{_fmt(b_m)})·{_fmt(L)} = {_fmt(enc,4)}"
            acl_for = "Acl = (As + A's + Al) · 10⁻⁴ · L · 7850 · 1.15   (+15% empalmes)"
            acl_sub = (f"({_fmt(as_v)}+{_fmt(aprima)}+{_fmt(al_t)})·10⁻⁴·"
                       f"{_fmt(L)}·7850·1.15 = {_fmt(acl,2)}")
        P.append(_paso("Takeoff CSI 03", "Vol", "Concreto", round(vol, 4), "m³",
            vol_for, vol_sub, "CSI 03 30 00",
            "Volumen de concreto. Genera la partida 03 30 00 (concreto colado).", "takeoff"))
        P.append(_paso("Takeoff CSI 03", "Enc", "Encofrado", round(enc, 4), "m²",
            enc_for, enc_sub, "CSI 03 10 00",
            "Área de cimbra/encofrado. Genera la partida 03 10 00.", "takeoff"))
        P.append(_paso("Takeoff CSI 03", "Acl", "Acero longitudinal", round(acl, 2), "kg",
            acl_for, acl_sub, "CSI 03 20 00",
            "Peso del acero longitudinal, con 15% de empalmes. Genera la partida 03 20 00.", "takeoff"))
        P.append(_paso("Takeoff CSI 03", "Aes", "Estribos", round(aes, 2), "kg",
            "Aes = (Av + 2·At) · 10⁻⁴ · n · perím · 7850,   n = L / (S/100)",
            f"estribo combinado cortante+torsión, S = {S_DEFAULT:.0f} cm → {_fmt(aes,2)}",
            "CSI 03 20 00", "Peso de estribos (cortante + torsión). Se suma a la partida 03 20 00.", "takeoff"))

    # ── VERIFICACIONES ───────────────────────────────────────────────────────
    P.append(_paso("Verificación", "✓ Sísmico", "As ≤ As,max (ductilidad)",
        bool(res.get("ok_sismico", True)), "", "As_req ≤ ρmax·b·d",
        "OK" if res.get("ok_sismico", True) else "FALLA", "MD §13 · ACI 318-71",
        "Verifica que la sección falle de forma dúctil (controlada por tensión).", "check"))
    if es_col:
        P.append(_paso("Verificación", "✓ ρg", "1% ≤ ρg ≤ 8%",
            bool(res.get("ok_pg", True)), "", "0.01 ≤ As/Ag ≤ 0.08",
            "OK" if res.get("ok_pg", True) else "FUERA DE RANGO", "MD §9.8 · ACI 318-71",
            "Cuantía longitudinal de columna dentro del rango de código.", "check"))
    adv = (res.get("advertencias") or "").strip()
    if adv:
        P.append(_paso("Verificación", "⚠", "Advertencias", adv, "", "—", adv, "—",
            "Avisos del motor de cálculo sobre la sección o el armado.", "check"))

    # ── LaTeX por paso: fórmula simbólica (mapa) + sustitución (conversor) ────
    for p in P:
        if p["tipo"] != "input":
            p["latex"] = LATEX_BY_FORMULA.get(p["formula"])
            p["latex_sub"] = _ascii_to_latex(p["sustitucion"])

    meta = {
        "tipo":      tipo,
        "seccion":   (f"{_fmt(lx)}×{_fmt(ly)} cm" if es_col else f"{_fmt(b)}×{_fmt(d)} cm (d)"),
        "material":  f"f'c {_fmt(fc)} · f'y {_fmt(fy)} kg/cm²",
        "ok_sismico": bool(res.get("ok_sismico", True)),
        "ok_pg":      bool(res.get("ok_pg", True)),
    }
    constantes = [
        {"simbolo": "φ_f",   "latex": r"\phi_{flex} = 0.90",  "valor": PHI_FLEXION,  "unidad": "", "desc": "Factor de reducción a flexión (ACI 318-19 §21.2.1)."},
        {"simbolo": "φ_v",   "latex": r"\phi_{corte} = 0.75", "valor": PHI_CORTANTE, "unidad": "", "desc": "Factor de reducción a cortante y torsión."},
        {"simbolo": "φ_c",   "latex": r"\phi_{col} = 0.65",   "valor": PHI_COLUMNA,  "unidad": "", "desc": "Factor de reducción a compresión (columna con estribo)."},
        {"simbolo": "Fmax",  "latex": r"F_{max} = 0.50",      "valor": FMAX_SISMICO, "unidad": "", "desc": "Tope de cuantía en zona sísmica: ρmax = 0.5·ρb."},
        {"simbolo": "Es",    "latex": r"E_s = 2{,}000{,}000", "valor": 2_000_000,    "unidad": "kg/cm²", "desc": "Módulo de elasticidad del acero."},
        {"simbolo": "εcu",   "latex": r"\varepsilon_{cu} = 0.003", "valor": 0.003,   "unidad": "", "desc": "Deformación unitaria última del concreto."},
        {"simbolo": "Es·εcu","latex": r"E_s\,\varepsilon_{cu} = 6000", "valor": 6000, "unidad": "kg/cm²", "desc": "Constante del eje neutro balanceado (en ρb y f's)."},
        {"simbolo": "β₁",    "latex": r"\beta_1 = 0.85\ (f'_c\le 280)", "valor": 0.85, "unidad": "", "desc": "Factor del bloque de compresión (base; baja si f'c>280)."},
        {"simbolo": "γs",    "latex": r"\gamma_s = 7850",     "valor": DENSIDAD_ACERO, "unidad": "kg/m³", "desc": "Densidad del acero (takeoff de peso)."},
        {"simbolo": "rec",   "latex": r"rec = 4",             "valor": RECUB_DEFAULT, "unidad": "cm", "desc": "Recubrimiento libre por defecto."},
        {"simbolo": "S",     "latex": r"S = 20",              "valor": S_DEFAULT,    "unidad": "cm", "desc": "Separación de estribos por defecto."},
    ]
    return {"meta": meta, "pasos": P, "resultado": res, "constantes": constantes}


# ─────────────────────────────────────────────────────────────────────────────
# PREDIMENSIONAMIENTO (G2) — reglas confirmadas por el Director
#   COLUMNA: lado_min = niveles · 10 · 0.8   (ej. 3 niveles -> 24 cm)
#   VIGA   : h = (luz_libre − 2·b_apoyo) / 10   (de la hoja de viga)
#   Ambas dimensiones se redondean hacia arriba a multiplo de 5 cm.
# ─────────────────────────────────────────────────────────────────────────────

def _ceil_mult5(x: float) -> int:
    """Redondea x hacia arriba al multiplo de 5 cm mas cercano (>= x)."""
    return int(math.ceil(float(x) / 5.0) * 5)


def predimensionar(tipo: str, niveles: int = 1, luz_libre_cm: float = 0.0,
                   b_apoyo_cm: float = 0.0,
                   recubrimiento_cm: float = RECUB_DEFAULT) -> dict:
    """
    Predimensionamiento estructural (funcion PURA, sin ORM).

    tipo: "COLUMNA" | "VIGA" (tolerante a VIGA_SIMPLE/etc.).

    COLUMNA: lado_min_cm = niveles · 10 · 0.8 ; b=h = ceil a multiplo de 5 >= lado_min.
    VIGA   : h = (luz_libre_cm − 2·b_apoyo_cm) / 10 ; h_cm = ceil a multiplo de 5;
             b_cm ≈ h/2 (minimo 20, redondeado a multiplo de 5).
    d_cm = h − recubrimiento (peralte efectivo).

    Devuelve {tipo, b_cm, h_cm, d_cm, lado_min_cm|h_prop_cm, regla_usada, notas}.
    """
    t = (tipo or "").strip().upper()
    rec = float(recubrimiento_cm or RECUB_DEFAULT)

    if "COLUM" in t or "PEDESTAL" in t or t.startswith("C"):
        n = max(int(niveles or 1), 1)
        lado_min = n * 10.0 * 0.8
        lado = _ceil_mult5(lado_min)
        h_cm = b_cm = lado
        d_cm = round(h_cm - rec, 1)
        return {
            "tipo": "COLUMNA",
            "b_cm": float(b_cm),
            "h_cm": float(h_cm),
            "d_cm": d_cm,
            "lado_min_cm": round(lado_min, 2),
            "regla_usada": "lado_min = niveles · 10 · 0.8 ; redondeo ↑ a múltiplo de 5",
            "notas": (f"{n} nivel(es) → lado_min={lado_min:.1f} cm → "
                      f"{lado}×{lado} cm. d = h − rec({rec:.0f}) = {d_cm:.0f} cm."),
        }

    # VIGA (default)
    luz = float(luz_libre_cm or 0.0)
    ba = float(b_apoyo_cm or 0.0)
    h_prop = (luz - 2.0 * ba) / 10.0
    h_cm = _ceil_mult5(h_prop) if h_prop > 0 else 0
    b_cm = max(_ceil_mult5(h_cm / 2.0), 20) if h_cm > 0 else 0
    d_cm = round(h_cm - rec, 1) if h_cm > 0 else 0.0
    return {
        "tipo": "VIGA",
        "b_cm": float(b_cm),
        "h_cm": float(h_cm),
        "d_cm": d_cm,
        "h_prop_cm": round(h_prop, 2),
        "regla_usada": "h = (luz_libre − 2·b_apoyo)/10 ; b ≈ h/2 (mín 20); redondeo ↑ a múltiplo de 5",
        "notas": (f"h_prop=({luz:.0f}−2·{ba:.0f})/10={h_prop:.1f} cm → h={h_cm} cm, "
                  f"b={b_cm} cm. d = h − rec({rec:.0f}) = {d_cm:.0f} cm."),
    }
