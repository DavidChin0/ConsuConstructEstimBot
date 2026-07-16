# -*- coding: utf-8 -*-
"""
Motor de calculo — Conexiones de Acero (AISC 360-16 §J, LRFD)
=============================================================
Conexiones de acero (viga-columna, viga-viga, soldadas) por metodo LRFD,
estilo Mathcad. METRICO: kgf, cm, t.  Ru ≤ φRn  (§B3.1, §J1.1).

Funciones PURAS (sin ORM). Fuente unica de verdad:
  calcular_conexion(elem, caso) -> dict   (φRn por estado, gobernante, DC, cumple)
  memoria_conexion(elem, caso)  -> {meta, pasos[], constantes[]}   (narrada)

Implementa:
  §J3 pernos   — area Ab, cortante J3-1, traccion J3-1, combinado J3-3a,
                 aplastamiento J3-6a, desgarre/tearout J3-6c, por-perno=min, grupo=Σ
  §J2 soldadura— te=0.707w, Fnw J2-5, φRn soldadura J2-3/4, METAL BASE J2-2 (min),
                 limites Tabla J2.4 / §J2.2b / L≥4w  (cierra GAP1-4)
  §J4 elementos— fluencia traccion J4-1, rotura J4-2, fluencia corte J4-3,
                 rotura corte J4-4, block shear J4-5

NO toca BD. Persistencia + partidas Div 05 + placa base §J8 + import fuerzas-nudo
ETABS = fase siguiente (requiere confirmar 3 tablas nuevas).

Reutiliza helpers de formato/LaTeX de calculo_estructural (DRY) y las tablas de
perfiles_acero.py + el resolver de acero_ficha.py.
"""

import math
import re

from backend.calculo_estructural import _fmt, _ascii_to_latex
from backend.perfiles_acero import (
    PERFILES_ACERO, PERNOS, ACEROS, FEXX_E70,
)
from backend.acero_ficha import conexion_ficha, _norm_tipo_conexion


# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTES — factores φ (LRFD) con referencia AISC 360-16
# ─────────────────────────────────────────────────────────────────────────────
PHI_SOLD      = 0.75   # §J2.4  soldadura de filete
PHI_PERNO     = 0.75   # §J3.6  pernos (corte/traccion/aplastamiento/tearout)
PHI_FLUENCIA  = 0.90   # §J4.1  fluencia por traccion
PHI_ROTURA    = 0.75   # §J4.2  rotura por traccion
PHI_CORTE_FLU = 1.00   # §J4.3  fluencia por cortante
PHI_CORTE_ROT = 0.75   # §J4.4  rotura por cortante
PHI_BLOCK     = 0.75   # §J4.5  block shear

COEF_GARG = 0.707      # garganta efectiva del filete = 0.707·w (§J2.2a)
COEF_FNW  = 0.60       # Fnw = 0.60·FEXX (§J2.4, Tabla J2.5)
UBS       = 1.0        # factor de tension uniforme en block shear (§J4.3)
HOLE_GAP  = 0.16       # cm — sobre-dimension de agujero estandar (d_b + 1.6 mm)

# Tamaño minimo de filete (Tabla J2.4) — (espesor_max_cm_parte_delgada, w_min_cm)
WMIN_TABLA = [
    (0.60, 0.30),   # ≤ 6 mm   -> 3 mm
    (1.30, 0.50),   # 6–13 mm  -> 5 mm
    (1.90, 0.60),   # 13–19 mm -> 6 mm
    (1e9,  0.80),   # > 19 mm  -> 8 mm
]


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def _norm(perfil: str) -> str:
    """Normaliza designacion de perfil (mayusc, sin espacios, ×->X, sin (imperial))."""
    if not perfil:
        return ""
    s = str(perfil).strip().upper()
    s = re.sub(r"\([^)]*\)", "", s)
    s = s.replace('"', "").replace("”", "").replace("''", "").replace("×", "X")
    return re.sub(r"\s+", "", s)


def _perfil(perfil: str) -> dict:
    """Propiedades de seccion (cm/cm²) o ceros si no esta en la tabla."""
    return PERFILES_ACERO.get(_norm(perfil), {"d": 0.0, "bf": 0.0, "tf": 0.0,
                                              "tw": 0.0, "Ag": 0.0})


def _fnv(grado: str, roscas_en_corte: bool) -> float:
    """Fnv del perno segun grado y si las roscas estan en el plano de corte
    (N=incluidas, conservador) o excluidas (X)."""
    p = PERNOS.get((grado or "A325").upper(), PERNOS["A325"])
    return p["Fnv_N"] if roscas_en_corte else p["Fnv_X"]


def _fnt(grado: str) -> float:
    p = PERNOS.get((grado or "A325").upper(), PERNOS["A325"])
    return p["Fnt"]


def _mat(acero: str) -> dict:
    return ACEROS.get((acero or "A992").upper(), ACEROS["A992"])


def _wmin_filete(t_min_cm: float) -> float:
    """Tamaño minimo de filete (Tabla J2.4) por espesor de la parte mas delgada."""
    for techo, wmin in WMIN_TABLA:
        if t_min_cm <= techo:
            return wmin
    return WMIN_TABLA[-1][1]


def _area_perno(d_b: float) -> float:
    """Ab = π/4·d_b²  (area nominal del perno)."""
    return math.pi / 4.0 * d_b ** 2 if d_b > 0 else 0.0


# ─────────────────────────────────────────────────────────────────────────────
# §J3 — PERNOS
# ─────────────────────────────────────────────────────────────────────────────
def rn_corte_pernos(Fnv, Ab, n):
    """φRn cortante del grupo (J3-1):  φ·Fnv·Ab·n   [kgf]."""
    return PHI_PERNO * Fnv * Ab * n


def rn_traccion_pernos(Fnt, Ab, n):
    """φRn traccion del grupo (J3-1):  φ·Fnt·Ab·n   [kgf]."""
    return PHI_PERNO * Fnt * Ab * n


def fnt_combinado(Fnt, Fnv, frv):
    """F'nt combinado tension-cortante (J3-3a):
       F'nt = 1.3·Fnt − Fnt/(φ·Fnv)·frv ≤ Fnt   [kgf/cm²]."""
    if Fnv <= 0:
        return Fnt
    val = 1.3 * Fnt - (Fnt / (PHI_PERNO * Fnv)) * frv
    return max(0.0, min(val, Fnt))


def rn_aplastamiento(d_b, t, Fu, n):
    """φRn aplastamiento del grupo (J3-6a, deformacion considerada):
       φ·(2.4·d_b·t·Fu)·n   [kgf]."""
    return PHI_PERNO * (2.4 * d_b * t * Fu) * n


def rn_tearout(lc, t, Fu, n):
    """φRn desgarre/tearout del grupo (J3-6c):  φ·(1.2·lc·t·Fu)·n   [kgf]."""
    return PHI_PERNO * (1.2 * lc * t * Fu) * n


# ─────────────────────────────────────────────────────────────────────────────
# §J2 — SOLDADURA
# ─────────────────────────────────────────────────────────────────────────────
def garganta_filete(w):
    """te = 0.707·w  (§J2.2a)."""
    return COEF_GARG * w


def fnw_soldadura(FEXX, theta_deg=0.0):
    """Fnw = 0.60·FEXX·(1+0.5·sin^1.5 θ)  (J2-5). θ=0 conservador (longitudinal)."""
    th = math.radians(theta_deg)
    return COEF_FNW * FEXX * (1.0 + 0.5 * (math.sin(th) ** 1.5))


def rn_soldadura(Fnw, te, L):
    """φRn del metal de soldadura (J2-3/4):  φ·Fnw·(te·L)   [kgf]."""
    return PHI_SOLD * Fnw * (te * L)


def rn_metal_base_corte(Fu, t_base, L):
    """φRn del metal BASE por rotura en cortante (J2-2 con FnBM=0.6·Fu, §J4):
       φ·0.6·Fu·(t_base·L)   [kgf].  φ=0.75 (rotura)."""
    return PHI_CORTE_ROT * 0.60 * Fu * (t_base * L)


# ─────────────────────────────────────────────────────────────────────────────
# §J4 — ELEMENTOS AFECTADOS (placa de conexion)
# ─────────────────────────────────────────────────────────────────────────────
def rn_fluencia_traccion(Fy, Ag):
    """φRn fluencia por traccion (J4-1):  φ·Fy·Ag   [kgf].  φ=0.90."""
    return PHI_FLUENCIA * Fy * Ag


def rn_rotura_traccion(Fu, Ae):
    """φRn rotura por traccion (J4-2):  φ·Fu·Ae   [kgf].  φ=0.75."""
    return PHI_ROTURA * Fu * Ae


def rn_fluencia_corte(Fy, Agv):
    """φRn fluencia por cortante (J4-3):  φ·0.60·Fy·Agv   [kgf].  φ=1.00."""
    return PHI_CORTE_FLU * 0.60 * Fy * Agv


def rn_rotura_corte(Fu, Anv):
    """φRn rotura por cortante (J4-4):  φ·0.60·Fu·Anv   [kgf].  φ=0.75."""
    return PHI_CORTE_ROT * 0.60 * Fu * Anv


def rn_block_shear(Fy, Fu, Agv, Anv, Ant):
    """φRn block shear (J4-5):
       φ·[0.6·Fu·Anv + Ubs·Fu·Ant] ≤ φ·[0.6·Fy·Agv + Ubs·Fu·Ant]   [kgf].  φ=0.75."""
    rotura  = 0.60 * Fu * Anv + UBS * Fu * Ant
    fluenc  = 0.60 * Fy * Agv + UBS * Fu * Ant
    return PHI_BLOCK * min(rotura, fluenc)


# ─────────────────────────────────────────────────────────────────────────────
# §J8 — PLACA BASE (aplastamiento del concreto + espesor de placa, DG-1)
# ─────────────────────────────────────────────────────────────────────────────
PHI_APLAST = 0.65   # §J8  aplastamiento del concreto


def rn_aplastamiento_concreto(fc, A1, A2):
    """φPp aplastamiento del concreto bajo la placa base (J8-1/J8-2):
       Pp = 0.85·f'c·A1·√(A2/A1) ≤ 1.7·f'c·A1.  φc = 0.65.  [kgf].
       A1 = area de la placa, A2 = area del pedestal/zapata (≥ A1)."""
    if A1 <= 0 or fc <= 0:
        return 0.0
    ratio = math.sqrt(A2 / A1) if A2 >= A1 > 0 else 1.0
    ratio = min(ratio, 2.0)
    Pp = min(0.85 * fc * A1 * ratio, 1.7 * fc * A1)
    return PHI_APLAST * Pp


def espesor_placa_base(Pu, Fy, B, N, d, bf):
    """Espesor requerido de placa base (AISC Design Guide 1, lineas de fluencia).
    Devuelve (tp_req, m, n, n_prima, l_max, fp)  [cm · kgf/cm²].
    m=(N−0.95d)/2, n=(B−0.80bf)/2, n'=√(d·bf)/4, l=max ; tp=l·√(2·fp/(0.90·Fy))."""
    if B <= 0 or N <= 0 or Fy <= 0:
        return 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
    m = (N - 0.95 * d) / 2.0
    nn = (B - 0.80 * bf) / 2.0
    n_prima = math.sqrt(d * bf) / 4.0 if (d > 0 and bf > 0) else 0.0
    l = max(m, nn, n_prima, 0.0)
    fp = Pu / (B * N) if (B * N) > 0 else 0.0
    tp_req = l * math.sqrt(2.0 * fp / (0.90 * Fy)) if fp > 0 else 0.0
    return tp_req, m, nn, n_prima, l, fp


# ─────────────────────────────────────────────────────────────────────────────
# GEOMETRIA DERIVADA  (defaults razonables cuando el usuario no detalla todo)
# ─────────────────────────────────────────────────────────────────────────────
def _geometria(elem: dict) -> dict:
    """Deriva geometria de placa/pernos a partir de los inputs minimos.
    Convenciones (placa simple a cortante, 1 columna de pernos):
      paso s = 3·d_b · borde Le = 1.5·d_b · lc (libre) = Le − d_hole/2
      h_placa = (n−1)·s + 2·Le · Ag = t·h_placa · Agv = t·h_placa (corte)
    Todo en cm."""
    d_b = float(elem.get("perno_d_cm", 1.9) or 0)
    n   = int(elem.get("n_pernos", 0) or 0)
    t   = float(elem.get("t_placa_cm", 0) or 0)
    d_hole = d_b + HOLE_GAP if d_b > 0 else 0.0
    s   = 3.0 * d_b
    Le  = 1.5 * d_b
    lc  = max(Le - d_hole / 2.0, 0.0)
    h_placa = (max(n - 1, 0) * s + 2 * Le) if n > 0 else 0.0
    Agv = t * h_placa                                   # area bruta a cortante
    Anv = t * (h_placa - (n * d_hole)) if n > 0 else 0.0   # area neta a cortante
    Anv = max(Anv, 0.0)
    Ag  = t * h_placa                                   # area bruta a traccion (placa)
    Ae  = Ag                                            # placa soldada: Ae≈Ag (U=1)
    # Block shear (un bloque, tension horizontal + corte vertical):
    Agt = t * lc if lc > 0 else 0.0                     # area bruta a tension (al borde)
    Ant = max(t * (lc - 0.5 * d_hole), 0.0)             # area neta a tension
    return {
        "d_b": d_b, "n": n, "t": t, "d_hole": d_hole, "s": s, "Le": Le, "lc": lc,
        "h_placa": h_placa, "Agv": Agv, "Anv": Anv, "Ag": Ag, "Ae": Ae,
        "Agt": Agt, "Ant": Ant,
    }


# ─────────────────────────────────────────────────────────────────────────────
# FUNCION MAESTRA — calcular_conexion  (UNICA fuente de verdad)
# ─────────────────────────────────────────────────────────────────────────────
def calcular_conexion(elem: dict, caso: dict) -> dict:
    """
    elem keys: tipo_conexion, perfil_viga, perfil_columna, acero,
               t_placa_cm, perno_grado, perno_d_cm, n_pernos, roscas_en_corte,
               w_filete_cm, L_soldadura_cm
    caso keys: vu_t, nu_t, mu_tm

    Devuelve dict con φRn por estado limite [t], estado gobernante, dc_ratio,
    cumple. Guards anti-NaN (todo finito o None). NO toca BD.
    """
    tn   = _norm_tipo_conexion(elem.get("tipo_conexion", "VC_CORTANTE"))
    mat  = _mat(elem.get("acero", "A992"))
    Fy, Fu = mat["Fy"], mat["Fu"]
    geo  = _geometria(elem)

    grado = (elem.get("perno_grado", "A325") or "A325").upper()
    roscas = bool(elem.get("roscas_en_corte", True))
    d_b = geo["d_b"]; n = geo["n"]; t = geo["t"]
    Ab  = _area_perno(d_b)
    Fnv = _fnv(grado, roscas)
    Fnt = _fnt(grado)

    w   = float(elem.get("w_filete_cm", 0) or 0)
    L   = float(elem.get("L_soldadura_cm", 0) or 0)
    te  = garganta_filete(w)
    Fnw = fnw_soldadura(FEXX_E70, 0.0)

    Vu = float(caso.get("vu_t", 0) or 0)
    Nu = float(caso.get("nu_t", 0) or 0)
    Mu = float(caso.get("mu_tm", 0) or 0)
    Pu = float(caso.get("pu_t", 0) or 0)   # axial de columna (placa base, de ETABS)

    aplica = _estados_por_tipo(tn)
    estados = {}   # nombre -> φRn en t (None si no aplica)

    KG_A_T = 1.0 / 1000.0

    # ── PERNOS ────────────────────────────────────────────────────────────────
    if aplica["pernos_corte"] and n > 0 and Ab > 0:
        estados["perno_cortante"]   = rn_corte_pernos(Fnv, Ab, n) * KG_A_T
        if t > 0:
            estados["perno_aplastamiento"] = rn_aplastamiento(d_b, t, Fu, n) * KG_A_T
            estados["perno_tearout"]       = rn_tearout(geo["lc"], t, Fu, n) * KG_A_T
    if aplica["pernos_traccion"] and n > 0 and Ab > 0:
        # combinado J3-3a: reduce Fnt por el cortante actuante frv
        frv = (Vu * 1000.0) / (Ab * n) if (Ab * n) > 0 else 0.0
        Fnt_eff = fnt_combinado(Fnt, Fnv, frv) if Vu > 0 else Fnt
        estados["perno_traccion"] = rn_traccion_pernos(Fnt_eff, Ab, n) * KG_A_T

    # ── SOLDADURA ───────────────────────────────────────────────────────────--
    if aplica["soldadura"] and w > 0 and L > 0:
        estados["soldadura"] = rn_soldadura(Fnw, te, L) * KG_A_T
        if t > 0:
            estados["metal_base"] = rn_metal_base_corte(Fu, t, L) * KG_A_T

    # ── ELEMENTOS §J4 (placa) ─────────────────────────────────────────────────
    if aplica["j4"] and t > 0 and geo["h_placa"] > 0:
        estados["fluencia_traccion"] = rn_fluencia_traccion(Fy, geo["Ag"]) * KG_A_T
        estados["rotura_traccion"]   = rn_rotura_traccion(Fu, geo["Ae"]) * KG_A_T
        estados["fluencia_corte"]    = rn_fluencia_corte(Fy, geo["Agv"]) * KG_A_T
        estados["rotura_corte"]      = rn_rotura_corte(Fu, geo["Anv"]) * KG_A_T
        if geo["Ant"] > 0:
            estados["block_shear"] = rn_block_shear(Fy, Fu, geo["Agv"], geo["Anv"], geo["Ant"]) * KG_A_T

    # ── PLACA BASE §J8 (aplastamiento del concreto + espesor de placa) ─────────
    j8 = None
    if aplica.get("placa_base"):
        fc = float(elem.get("fc_kg_cm2", 210) or 210)
        pc = _perfil(elem.get("perfil_columna"))
        d_col = pc.get("d", 0.0); bf_col = pc.get("bf", 0.0)
        # Placa B×N: input editable o derivada (perfil columna + 2·5 cm de borde)
        B = float(elem.get("B_placa_cm", 0) or 0) or ((bf_col + 10.0) if bf_col > 0 else 0.0)
        N = float(elem.get("N_placa_cm", 0) or 0) or ((d_col + 10.0) if d_col > 0 else 0.0)
        Pu_ax = abs(Pu) or abs(Nu)                       # axial de columna (ETABS)
        A1 = B * N
        A2 = float(elem.get("A2_cm2", 0) or 0) or A1     # pedestal ≥ placa (default = A1)
        if A1 > 0 and fc > 0:
            phiPp = rn_aplastamiento_concreto(fc, A1, A2) * KG_A_T
            estados["aplastamiento_concreto"] = phiPp
            tp_req, m_pl, n_pl, n_prima, l_pl, fp = espesor_placa_base(
                Pu_ax * 1000.0, Fy, B, N, d_col, bf_col)
            ok_esp = (t >= tp_req) if (t > 0 and tp_req > 0) else None
            j8 = {
                "fc": round(fc, 1), "B": round(B, 2), "N": round(N, 2),
                "A1": round(A1, 1), "A2": round(A2, 1), "Pu_axial_t": round(Pu_ax, 3),
                "phiPp_t": round(phiPp, 3), "fp": round(fp, 2),
                "m": round(m_pl, 2), "n": round(n_pl, 2), "n_prima": round(n_prima, 2),
                "l": round(l_pl, 2), "tp_req": round(tp_req, 3), "tp": round(t, 3),
                "ok_espesor": ok_esp,
                "dc_aplast": round(Pu_ax / phiPp, 4) if phiPp > 0 else None,
            }

    # Saneo anti-NaN/inf
    estados = {k: (round(v, 4) if isinstance(v, (int, float)) and math.isfinite(v) else None)
               for k, v in estados.items()}
    validos = {k: v for k, v in estados.items() if v is not None and v > 0}

    gobernante = min(validos, key=validos.get) if validos else None
    phi_rn_gob = validos[gobernante] if gobernante else None

    # Demanda gobernante segun tipo: corte para VC/VV/soldada; traccion si Nu domina
    demanda = max(abs(Vu), abs(Nu))
    if tn == "VC_MOMENTO" and Mu > 0:
        # par de fuerzas de ala: Fuf = Mu/(d−tf)
        pv = _perfil(elem.get("perfil_viga"))
        brazo = max(pv["d"] - pv["tf"], 1e-6) / 100.0   # cm -> m
        demanda = max(demanda, Mu / brazo)
    if tn == "PLACA_BASE" and j8:
        demanda = max(demanda, j8["Pu_axial_t"])   # axial gobierna la placa base

    dc = (demanda / phi_rn_gob) if (phi_rn_gob and phi_rn_gob > 0) else None
    cumple = (dc is not None and dc <= 1.0)

    # Limites geometricos de soldadura (§J2.2b / Tabla J2.4) — informativo
    chk_sold = None
    if aplica["soldadura"] and w > 0:
        t_thin = min([x for x in (t, _perfil(elem.get("perfil_viga"))["tf"],
                                  _perfil(elem.get("perfil_columna"))["tf"]) if x > 0]
                     or [t]) if t > 0 else 0
        wmin = _wmin_filete(t_thin) if t_thin > 0 else 0
        wmax = (t_thin - 0.16) if t_thin >= 0.6 else t_thin
        chk_sold = {
            "w": round(w, 4), "w_min": round(wmin, 4), "w_max": round(wmax, 4),
            "L": round(L, 3), "L_min": round(4 * w, 3),
            "ok_wmin": (w >= wmin) if wmin else True,
            "ok_wmax": (w <= wmax) if wmax > 0 else True,
            "ok_lmin": (L >= 4 * w) if L > 0 else True,
        }

    return {
        "tipo_conexion": tn,
        "estados": estados,
        "phi_rn_gobernante": phi_rn_gob,
        "estado_gobernante": gobernante,
        "demanda_t": round(demanda, 4),
        "dc_ratio": round(dc, 4) if dc is not None else None,
        "cumple": bool(cumple),
        "chk_soldadura": chk_sold,
        "geo": {k: (round(v, 4) if isinstance(v, (int, float)) else v) for k, v in geo.items()},
        "Ab_cm2": round(Ab, 4),
        "Fnv": Fnv, "Fnt": Fnt, "Fy": Fy, "Fu": Fu,
        "j8": j8,
    }


def _estados_por_tipo(tn: str) -> dict:
    """Tabla §6 del plan: que estados aplica cada tipo de conexion."""
    base = {"pernos_corte": False, "pernos_traccion": False,
            "soldadura": False, "j4": False, "placa_base": False}
    if tn == "VC_CORTANTE":
        base.update(pernos_corte=True, soldadura=True, j4=True)
    elif tn == "VC_MOMENTO":
        base.update(pernos_corte=True, pernos_traccion=True, soldadura=True, j4=True)
    elif tn == "VV":
        base.update(pernos_corte=True, j4=True)
    elif tn == "SOLDADA":
        base.update(soldadura=True)
    elif tn == "PLACA_BASE":
        base.update(soldadura=True, placa_base=True)   # §J8 aplastamiento + espesor
    return base


# ─────────────────────────────────────────────────────────────────────────────
# MEMORIA DE CALCULO narrada (estilo Mathcad) — calca el plan §4
# ─────────────────────────────────────────────────────────────────────────────
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


# ── LATEX_BY_FORMULA (del §5 del plan) ───────────────────────────────────────
LATEX_BY_FORMULA = {
    "Ab = pi/4·db^2":                       r"A_b = \tfrac{\pi}{4}\,d_b^2",
    "phiRn = 0.75·Fnv·Ab·n":                r"\phi R_{n,v} = 0.75\,F_{nv}\,A_b\,n",
    "phiRn = 0.75·Fnt·Ab·n":                r"\phi R_{n,t} = 0.75\,F_{nt}\,A_b\,n",
    "Fnt' = 1.3Fnt − (Fnt/(phi·Fnv))·frv":  r"F'_{nt}=1.3F_{nt}-\dfrac{F_{nt}}{\phi F_{nv}}\,f_{rv}\le F_{nt}",
    "phiRn = 0.75·2.4·db·tp·Fu·n":          r"\phi R_n=0.75\,(2.4\,d_b\,t_p\,F_u)\,n",
    "phiRn = 0.75·1.2·lc·tp·Fu·n":          r"\phi R_n=0.75\,(1.2\,l_c\,t_p\,F_u)\,n",
    "te = 0.707·w":                         r"t_e = 0.707\,w",
    "Fnw = 0.6·FEXX·(1+0.5·sin^1.5 θ)":     r"F_{nw}=0.60\,F_{EXX}\,(1+0.5\sin^{1.5}\theta)",
    "phiRn = 0.75·Fnw·te·L":                r"\phi R_{n,sold}=0.75\,F_{nw}\,t_e\,L",
    "phiRn_BM = 0.75·0.6·Fu·tbase·L":       r"\phi R_{n,BM}=0.75\cdot0.6\,F_u\,t_{base}\,L",
    "phiRn = 0.90·Fy·Ag":                   r"\phi R_n=0.90\,F_y\,A_g",
    "phiRn = 0.75·Fu·Ae":                   r"\phi R_n=0.75\,F_u\,A_e",
    "phiRn = 1.00·0.60·Fy·Agv":             r"\phi R_n=1.00\cdot0.60\,F_y\,A_{gv}",
    "phiRn = 0.75·0.60·Fu·Anv":             r"\phi R_n=0.75\cdot0.60\,F_u\,A_{nv}",
    "blockshear J4-5":                      r"\phi R_n=0.75\,[\,0.6F_uA_{nv}+U_{bs}F_uA_{nt}\,]\le 0.75\,[\,0.6F_yA_{gv}+U_{bs}F_uA_{nt}\,]",
    "phiRn,gob = min(estados)":             r"\phi R_{n,gob}=\min(\text{todos los estados})",
    "DC = demanda/phiRn":                   r"DC=\dfrac{D}{\phi R_{n,gob}}\le 1.0",
    "Fuf = Mu/(d−tf)":                      r"F_{uf}=\dfrac{M_u}{d-t_f}",
    "s = 3·d_b · L_e = 1.5·d_b · l_c = L_e − d_hole/2":
        r"s = 3\,d_b \quad L_e = 1.5\,d_b \quad l_c = L_e - \tfrac{d_{hole}}{2}",
    "h_p = (n−1)·s + 2·L_e · Ag = t·h_p":
        r"h_p = (n-1)\,s + 2\,L_e \quad A_g = t\,h_p",
}


# Etiquetas legibles de estados (para la verificacion)
_EST_LBL = {
    "perno_cortante": "Pernos a cortante", "perno_traccion": "Pernos a traccion",
    "perno_aplastamiento": "Aplastamiento", "perno_tearout": "Desgarre (tearout)",
    "soldadura": "Soldadura (metal de aporte)", "metal_base": "Metal base",
    "fluencia_traccion": "Fluencia por traccion", "rotura_traccion": "Rotura por traccion",
    "fluencia_corte": "Fluencia por cortante", "rotura_corte": "Rotura por cortante",
    "block_shear": "Block shear",
}


def memoria_conexion(elem: dict, caso: dict) -> dict:
    """Memoria narrada de una conexion. {meta, pasos[], constantes[]}.
    Calca el plan §4 (cada paso con fórmula + sustitucion numerica + ref AISC)."""
    res  = calcular_conexion(elem, caso)
    tn   = res["tipo_conexion"]
    aplica = _estados_por_tipo(tn)
    mat  = _mat(elem.get("acero", "A992"))
    Fy, Fu = mat["Fy"], mat["Fu"]
    geo  = res["geo"]
    est  = res["estados"]

    grado = (elem.get("perno_grado", "A325") or "A325").upper()
    roscas = bool(elem.get("roscas_en_corte", True))
    pinfo = PERNOS.get(grado, PERNOS["A325"])
    d_b = geo["d_b"]; n = geo["n"]; t = geo["t"]
    Ab  = res["Ab_cm2"]; Fnv = res["Fnv"]; Fnt = res["Fnt"]
    w   = float(elem.get("w_filete_cm", 0) or 0)
    L   = float(elem.get("L_soldadura_cm", 0) or 0)
    te  = garganta_filete(w)
    Fnw = fnw_soldadura(FEXX_E70, 0.0)

    Vu = float(caso.get("vu_t", 0) or 0)
    Nu = float(caso.get("nu_t", 0) or 0)
    Mu = float(caso.get("mu_tm", 0) or 0)

    pv = _perfil(elem.get("perfil_viga"))
    pc = _perfil(elem.get("perfil_columna"))
    ficha = conexion_ficha(elem.get("perfil_viga", ""), elem.get("perfil_columna", ""), tn)

    P = []

    # ── 0. MATERIALES Y CONSTANTES ────────────────────────────────────────────
    P.append(_paso("Materiales", "F_y · F_u", f"Acero {mat['desc']}",
        f"{_fmt(Fy)} / {_fmt(Fu)}", "kgf/cm²",
        "propiedades del material", f"F_y = {_fmt(Fy)} · F_u = {_fmt(Fu)}",
        "AISC Tabla 2-4", "Fluencia y rotura del acero de la placa/miembro.", "input"))
    P.append(_paso("Materiales", "F_EXX", "Resistencia del electrodo", FEXX_E70, "kgf/cm²",
        "electrodo E70XX", f"F_EXX = {_fmt(FEXX_E70)}", "AISC Tabla J2.5",
        "Resistencia minima del metal de aporte (E70XX = 70 ksi).", "input"))
    if aplica["pernos_corte"] or aplica["pernos_traccion"]:
        rosca_txt = "N (roscas incluidas)" if roscas else "X (roscas excluidas)"
        P.append(_paso("Materiales", "F_nt · F_nv", f"Perno {grado} — {rosca_txt}",
            f"{_fmt(Fnt)} / {_fmt(Fnv)}", "kgf/cm²",
            "Tabla J3.2", f"{grado}: F_nt = {_fmt(Fnt)} · F_nv = {_fmt(Fnv)}",
            "AISC Tabla J3.2", "Esfuerzos nominales de traccion y cortante del perno.", "input"))

    # ── 1. GEOMETRIA ──────────────────────────────────────────────────────────
    if elem.get("perfil_viga"):
        P.append(_paso("Geometria", "Viga", f"Perfil de viga {elem.get('perfil_viga')}",
            f"d={_fmt(pv['d'])} · t_f={_fmt(pv['tf'])} · A_g={_fmt(pv['Ag'])}", "cm",
            "tabla de perfiles", f"d = {_fmt(pv['d'])} cm · b_f = {_fmt(pv['bf'])} cm",
            "AISC Shapes v15", "Propiedades del perfil de la viga conectada.", "input"))
    if elem.get("perfil_columna"):
        P.append(_paso("Geometria", "Columna", f"Perfil de columna {elem.get('perfil_columna')}",
            f"d={_fmt(pc['d'])} · t_f={_fmt(pc['tf'])} · A_g={_fmt(pc['Ag'])}", "cm",
            "tabla de perfiles", f"d = {_fmt(pc['d'])} cm · b_f = {_fmt(pc['bf'])} cm",
            "AISC Shapes v15", "Propiedades del perfil de la columna soporte.", "input"))
    if t > 0:
        P.append(_paso("Geometria", "t_p", "Espesor de la placa", t, "cm",
            "dato de diseño", f"t_p = {_fmt(t)}", "—",
            "Espesor de la placa de conexion (shear tab / gusset).", "input"))
    if n > 0:
        P.append(_paso("Geometria", "n · d_b", f"Pernos ({grado})",
            f"{n} × Ø{_fmt(d_b)}", "cm", "dato de diseño",
            f"n = {n} pernos · d_b = {_fmt(d_b)} cm", "—",
            "Cantidad y diametro de los pernos del grupo.", "input"))
        P.append(_paso("Geometria", "s · L_e · l_c", "Espaciamiento / borde / libre",
            f"{_fmt(geo['s'])} / {_fmt(geo['Le'])} / {_fmt(geo['lc'])}", "cm",
            "s = 3·d_b · L_e = 1.5·d_b · l_c = L_e − d_hole/2",
            f"s = 3·{_fmt(d_b)} = {_fmt(geo['s'])} · l_c = {_fmt(geo['lc'])}",
            "AISC §J3.3/§J3.4", "Paso, distancia al borde y distancia libre (gobiernan tearout).", "intermedio"))

    # ── 2. DEMANDA ────────────────────────────────────────────────────────────
    P.append(_paso("Demanda", "V_u", "Cortante ultimo", Vu, "t",
        "demanda del analisis (ETABS, combo LRFD)", f"V_u = {_fmt(Vu)}", "AISC §J1.1",
        "Cortante ultimo de la conexion por la combinacion gobernante.", "input"))
    if aplica["pernos_traccion"] or Nu != 0:
        P.append(_paso("Demanda", "N_u", "Traccion ultima", Nu, "t",
            "demanda del analisis (ETABS, combo LRFD)", f"N_u = {_fmt(Nu)}", "AISC §J1.1",
            "Fuerza axial ultima de traccion en la conexion.", "input"))
    if tn == "VC_MOMENTO":
        P.append(_paso("Demanda", "M_u", "Momento ultimo", Mu, "t·m",
            "demanda del analisis (ETABS, combo LRFD)", f"M_u = {_fmt(Mu)}", "AISC §J1.1",
            "Momento ultimo; genera par de fuerzas en las alas.", "input"))
        brazo = max(pv["d"] - pv["tf"], 1e-6)
        Fuf = Mu / (brazo / 100.0) if brazo > 0 else 0.0
        P.append(_paso("Demanda", "F_uf", "Fuerza de ala", round(Fuf, 3), "t",
            "Fuf = Mu/(d−tf)",
            f"{_fmt(Mu)}/({_fmt(pv['d'])}−{_fmt(pv['tf'])})·100⁻¹ = {_fmt(Fuf)}",
            "AISC §J10", "Par de fuerzas de las alas por el momento (tension/compresion).", "resultado",
            latex=LATEX_BY_FORMULA["Fuf = Mu/(d−tf)"]))

    # ── 3. PERNOS §J3 ─────────────────────────────────────────────────────────
    if (aplica["pernos_corte"] or aplica["pernos_traccion"]) and n > 0 and Ab > 0:
        P.append(_paso("Pernos §J3", "A_b", "Area nominal del perno", round(Ab, 4), "cm²",
            "Ab = pi/4·db^2", f"π/4·{_fmt(d_b)}² = {_fmt(Ab,4)}", "AISC §J3.6",
            "Area de la seccion transversal nominal del perno.", "intermedio",
            latex=LATEX_BY_FORMULA["Ab = pi/4·db^2"]))
        if aplica["pernos_corte"] and "perno_cortante" in est:
            P.append(_paso("Pernos §J3", "φR_{n,v}", "Cortante del grupo (J3-1)",
                est["perno_cortante"], "t",
                "phiRn = 0.75·Fnv·Ab·n",
                f"0.75·{_fmt(Fnv)}·{_fmt(Ab,4)}·{n} = {_fmt(est['perno_cortante']*1000)} kgf = {_fmt(est['perno_cortante'])} t",
                "AISC §J3.6 ec.J3-1", "Resistencia de diseño a cortante de los n pernos.", "resultado",
                latex=LATEX_BY_FORMULA["phiRn = 0.75·Fnv·Ab·n"]))
            if "perno_aplastamiento" in est:
                P.append(_paso("Pernos §J3", "φR_{n,ap}", "Aplastamiento (J3-6a)",
                    est["perno_aplastamiento"], "t",
                    "phiRn = 0.75·2.4·db·tp·Fu·n",
                    f"0.75·2.4·{_fmt(d_b)}·{_fmt(t)}·{_fmt(Fu)}·{n} = {_fmt(est['perno_aplastamiento'])} t",
                    "AISC §J3.10 ec.J3-6a", "Aplastamiento del perno sobre la placa.", "resultado",
                    latex=LATEX_BY_FORMULA["phiRn = 0.75·2.4·db·tp·Fu·n"]))
            if "perno_tearout" in est:
                P.append(_paso("Pernos §J3", "φR_{n,to}", "Desgarre / tearout (J3-6c)",
                    est["perno_tearout"], "t",
                    "phiRn = 0.75·1.2·lc·tp·Fu·n",
                    f"0.75·1.2·{_fmt(geo['lc'])}·{_fmt(t)}·{_fmt(Fu)}·{n} = {_fmt(est['perno_tearout'])} t",
                    "AISC §J3.10 ec.J3-6c", "Desgarre del material entre el perno y el borde.", "resultado",
                    latex=LATEX_BY_FORMULA["phiRn = 0.75·1.2·lc·tp·Fu·n"]))
        if aplica["pernos_traccion"] and "perno_traccion" in est:
            frv = (Vu * 1000.0) / (Ab * n) if (Ab * n) > 0 else 0.0
            Fnt_eff = fnt_combinado(Fnt, Fnv, frv) if Vu > 0 else Fnt
            if Vu > 0:
                P.append(_paso("Pernos §J3", "F'_{nt}", "Traccion reducida por cortante (J3-3a)",
                    round(Fnt_eff, 1), "kgf/cm²",
                    "Fnt' = 1.3Fnt − (Fnt/(phi·Fnv))·frv",
                    f"1.3·{_fmt(Fnt)} − ({_fmt(Fnt)}/(0.75·{_fmt(Fnv)}))·{_fmt(frv,1)} = {_fmt(Fnt_eff,1)}",
                    "AISC §J3.7 ec.J3-3a", "Esfuerzo de traccion del perno reducido por el cortante actuante.", "intermedio",
                    latex=LATEX_BY_FORMULA["Fnt' = 1.3Fnt − (Fnt/(phi·Fnv))·frv"]))
            P.append(_paso("Pernos §J3", "φR_{n,t}", "Traccion del grupo (J3-1)",
                est["perno_traccion"], "t",
                "phiRn = 0.75·Fnt·Ab·n",
                f"0.75·{_fmt(Fnt_eff,1)}·{_fmt(Ab,4)}·{n} = {_fmt(est['perno_traccion'])} t",
                "AISC §J3.6 ec.J3-1", "Resistencia de diseño a traccion de los n pernos.", "resultado",
                latex=LATEX_BY_FORMULA["phiRn = 0.75·Fnt·Ab·n"]))

    # ── 4. SOLDADURA §J2 ──────────────────────────────────────────────────────
    if aplica["soldadura"] and w > 0 and L > 0:
        P.append(_paso("Soldadura §J2", "t_e", "Garganta efectiva", round(te, 4), "cm",
            "te = 0.707·w", f"0.707·{_fmt(w)} = {_fmt(te,4)}", "AISC §J2.2a",
            "Espesor efectivo del filete (gobierna la resistencia del cordon).", "intermedio",
            latex=LATEX_BY_FORMULA["te = 0.707·w"]))
        P.append(_paso("Soldadura §J2", "F_nw", "Esfuerzo nominal del cordon", round(Fnw, 1), "kgf/cm²",
            "Fnw = 0.6·FEXX·(1+0.5·sin^1.5 θ)",
            f"0.6·{_fmt(FEXX_E70)}·(1+0) = {_fmt(Fnw,1)}  (θ=0, conservador)",
            "AISC §J2.4 ec.J2-5", "Esfuerzo nominal del metal de soldadura (θ=0, cordon longitudinal).", "intermedio",
            latex=LATEX_BY_FORMULA["Fnw = 0.6·FEXX·(1+0.5·sin^1.5 θ)"]))
        P.append(_paso("Soldadura §J2", "φR_{n,sold}", "Resistencia del metal de aporte",
            est.get("soldadura"), "t",
            "phiRn = 0.75·Fnw·te·L",
            f"0.75·{_fmt(Fnw,1)}·{_fmt(te,4)}·{_fmt(L)} = {_fmt((est.get('soldadura') or 0))} t",
            "AISC §J2.4 ec.J2-3", "Resistencia de diseño del cordon de soldadura.", "resultado",
            latex=LATEX_BY_FORMULA["phiRn = 0.75·Fnw·te·L"]))
        if "metal_base" in est:
            P.append(_paso("Soldadura §J2", "φR_{n,BM}", "Metal base (J2-2 → min)",
                est["metal_base"], "t",
                "phiRn_BM = 0.75·0.6·Fu·tbase·L",
                f"0.75·0.6·{_fmt(Fu)}·{_fmt(t)}·{_fmt(L)} = {_fmt(est['metal_base'])} t",
                "AISC §J2.4(a) ec.J2-2", "Rotura por cortante del metal base; la junta = min(soldadura, base).", "resultado",
                latex=LATEX_BY_FORMULA["phiRn_BM = 0.75·0.6·Fu·tbase·L"]))
        chk = res.get("chk_soldadura")
        if chk:
            ok = chk["ok_wmin"] and chk["ok_wmax"] and chk["ok_lmin"]
            P.append(_paso("Soldadura §J2", "✓ límites", "w_min / w_max / L≥4w", ok, "",
                "Tabla J2.4 · §J2.2b · §J2.2b(c)",
                f"w={_fmt(chk['w'])} (min {_fmt(chk['w_min'])}, max {_fmt(chk['w_max'])}) · "
                f"L={_fmt(chk['L'])} ≥ 4w={_fmt(chk['L_min'])} → {'OK' if ok else 'REVISAR'}",
                "AISC Tabla J2.4 / §J2.2b", "Limites geometricos del filete (cierra GAP 1-4 del motor viejo).", "check"))

    # ── 5. ELEMENTOS AFECTADOS §J4 (placa) ────────────────────────────────────
    if aplica["j4"] and t > 0 and geo["h_placa"] > 0:
        P.append(_paso("Elementos §J4", "h_p · A_g", "Placa: altura y area bruta",
            f"{_fmt(geo['h_placa'])} · {_fmt(geo['Ag'])}", "cm / cm²",
            "h_p = (n−1)·s + 2·L_e · Ag = t·h_p",
            f"h_p = {_fmt(geo['h_placa'])} cm · A_g = {_fmt(t)}·{_fmt(geo['h_placa'])} = {_fmt(geo['Ag'])} cm²",
            "geometria de la placa", "Dimensiones de la placa para los estados §J4.", "intermedio"))
        if "fluencia_traccion" in est:
            P.append(_paso("Elementos §J4", "φR_{n,fy}", "Fluencia por traccion (J4-1)",
                est["fluencia_traccion"], "t",
                "phiRn = 0.90·Fy·Ag",
                f"0.90·{_fmt(Fy)}·{_fmt(geo['Ag'])} = {_fmt(est['fluencia_traccion'])} t",
                "AISC §J4.1 ec.J4-1", "Fluencia de la placa en el area bruta a traccion.", "resultado",
                latex=LATEX_BY_FORMULA["phiRn = 0.90·Fy·Ag"]))
        if "rotura_traccion" in est:
            P.append(_paso("Elementos §J4", "φR_{n,ru}", "Rotura por traccion (J4-2)",
                est["rotura_traccion"], "t",
                "phiRn = 0.75·Fu·Ae",
                f"0.75·{_fmt(Fu)}·{_fmt(geo['Ae'])} = {_fmt(est['rotura_traccion'])} t",
                "AISC §J4.1 ec.J4-2", "Rotura de la placa en el area neta efectiva.", "resultado",
                latex=LATEX_BY_FORMULA["phiRn = 0.75·Fu·Ae"]))
        if "fluencia_corte" in est:
            P.append(_paso("Elementos §J4", "φR_{n,vy}", "Fluencia por cortante (J4-3)",
                est["fluencia_corte"], "t",
                "phiRn = 1.00·0.60·Fy·Agv",
                f"1.00·0.60·{_fmt(Fy)}·{_fmt(geo['Agv'])} = {_fmt(est['fluencia_corte'])} t",
                "AISC §J4.2 ec.J4-3", "Fluencia de la placa en el area bruta a cortante.", "resultado",
                latex=LATEX_BY_FORMULA["phiRn = 1.00·0.60·Fy·Agv"]))
        if "rotura_corte" in est:
            P.append(_paso("Elementos §J4", "φR_{n,vu}", "Rotura por cortante (J4-4)",
                est["rotura_corte"], "t",
                "phiRn = 0.75·0.60·Fu·Anv",
                f"0.75·0.60·{_fmt(Fu)}·{_fmt(geo['Anv'])} = {_fmt(est['rotura_corte'])} t",
                "AISC §J4.2 ec.J4-4", "Rotura de la placa en el area neta a cortante.", "resultado",
                latex=LATEX_BY_FORMULA["phiRn = 0.75·0.60·Fu·Anv"]))
        if "block_shear" in est:
            P.append(_paso("Elementos §J4", "φR_{n,bs}", "Block shear (J4-5)",
                est["block_shear"], "t",
                "blockshear J4-5",
                f"0.75·[0.6·{_fmt(Fu)}·{_fmt(geo['Anv'])} + {_fmt(Fu)}·{_fmt(geo['Ant'])}] = {_fmt(est['block_shear'])} t",
                "AISC §J4.3 ec.J4-5", "Desgarre en bloque (corte + tension) del grupo de pernos.", "resultado",
                latex=LATEX_BY_FORMULA["blockshear J4-5"]))

    # ── 5b. PLACA BASE §J8 (aplastamiento del concreto + espesor) ─────────────
    j8 = res.get("j8")
    if aplica.get("placa_base") and j8:
        P.append(_paso("Placa base §J8", "B × N", "Geometria de la placa",
            f"{_fmt(j8['B'])} × {_fmt(j8['N'])}", "cm",
            "A_1 = B·N ; A_2 = pedestal",
            f"A_1 = {_fmt(j8['B'])}·{_fmt(j8['N'])} = {_fmt(j8['A1'])} cm² · A_2 = {_fmt(j8['A2'])} cm²",
            "geometria de la placa (input o derivada del perfil columna +2·5 cm)",
            "Area de contacto placa-concreto. B,N vienen de ETABS pero quedan editables.", "intermedio",
            latex=r"A_1=B\,N\qquad A_2=A_{pedestal}"))
        P.append(_paso("Placa base §J8", "φP_p", "Aplastamiento del concreto",
            j8["phiPp_t"], "t",
            "phiPp = 0.65·0.85·f'c·A1·√(A2/A1) ≤ 0.65·1.7·f'c·A1",
            f"0.65·0.85·{_fmt(j8['fc'])}·{_fmt(j8['A1'])}·√({_fmt(j8['A2'])}/{_fmt(j8['A1'])}) = {_fmt(j8['phiPp_t'])} t",
            "AISC §J8 ec.J8-1/J8-2 · ACI 318 §14", "Resistencia al aplastamiento del concreto bajo la placa; √(A2/A1)≤2.", "resultado",
            latex=r"\phi P_p=0.65\cdot0.85\,f'_c\,A_1\sqrt{A_2/A_1}\le0.65\cdot1.7\,f'_c\,A_1"))
        P.append(_paso("Placa base §J8", "f_p", "Presion de contacto",
            j8["fp"], "kgf/cm²",
            "fp = Pu/(B·N)",
            f"{_fmt(j8['Pu_axial_t'])}t / {_fmt(j8['A1'])}cm² = {_fmt(j8['fp'])} kgf/cm²",
            "presion uniforme bajo la placa", "Carga axial de la columna repartida en el area de la placa.", "intermedio",
            latex=r"f_p=\dfrac{P_u}{B\,N}"))
        P.append(_paso("Placa base §J8", "l", "Voladizo critico (cantilever)",
            j8["l"], "cm",
            "l = max(m, n, n') ; m=(N−0.95d)/2 · n=(B−0.80b_f)/2 · n'=√(d·b_f)/4",
            f"max(m={_fmt(j8['m'])}, n={_fmt(j8['n'])}, n'={_fmt(j8['n_prima'])}) = {_fmt(j8['l'])} cm",
            "Design Guide 1 (voladizos de la placa)", "El mayor voladizo flexiona mas la placa; gobierna el espesor.", "intermedio",
            latex=r"l=\max(m,\,n,\,n')"))
        ok_esp = j8.get("ok_espesor")
        P.append(_paso("Placa base §J8", "t_{p,req}", "Espesor minimo de placa",
            j8["tp_req"], "cm",
            "tp = l·√(2·fp/(0.90·Fy))",
            f"{_fmt(j8['l'])}·√(2·{_fmt(j8['fp'])}/(0.90·{_fmt(Fy)})) = {_fmt(j8['tp_req'])} cm "
            f"vs t_prov = {_fmt(j8['tp'])} cm → {'OK' if ok_esp else ('REVISAR' if ok_esp is False else '—')}",
            "AISC Design Guide 1 ec.3.3.14a", "Espesor por flexion del voladizo; t_provisto debe ≥ t_req.",
            "check" if ok_esp is not None else "resultado",
            latex=r"t_{p,req}=l\sqrt{\dfrac{2\,f_p}{0.90\,F_y}}"))

    # ── 6. VERIFICACION ───────────────────────────────────────────────────────
    gob = res["estado_gobernante"]
    phi_gob = res["phi_rn_gobernante"]
    P.append(_paso("Verificacion", "φR_{n,gob}", "Resistencia gobernante",
        phi_gob, "t",
        "phiRn,gob = min(estados)",
        (f"min(estados) = {_EST_LBL.get(gob, gob)} = {_fmt(phi_gob)} t" if gob
         else "sin estados calculados (faltan datos de geometria)"),
        "AISC §J", "El estado limite mas debil gobierna la conexion.", "resultado",
        latex=LATEX_BY_FORMULA["phiRn,gob = min(estados)"]))
    P.append(_paso("Verificacion", "DC", "Relacion demanda/capacidad",
        res["dc_ratio"], "",
        "DC = demanda/phiRn",
        (f"{_fmt(res['demanda_t'])}/{_fmt(phi_gob)} = {_fmt(res['dc_ratio'])}" if phi_gob
         else "—"),
        "AISC §B3.1", "Cociente de demanda sobre capacidad gobernante.", "intermedio",
        latex=LATEX_BY_FORMULA["DC = demanda/phiRn"]))
    P.append(_paso("Verificacion", "✓ LRFD", "Demanda ≤ φRn_gob",
        bool(res["cumple"]), "",
        "demanda ≤ resistencia de diseño",
        (f"{_fmt(res['demanda_t'])} t {'≤' if res['cumple'] else '>'} {_fmt(phi_gob)} t → "
         + ("OK" if res["cumple"] else "NO CUMPLE") if phi_gob else "sin verificar (faltan datos)"),
        "AISC §J1.1", "La conexion resiste la demanda ultima.", "check",
        latex=r"D \le \phi R_{n,gob}"))

    # ── post-proceso latex (pasos sin latex explicito caen al mapa por formula) ─
    for p in P:
        if p["tipo"] != "input" and p["latex"] is None:
            p["latex"] = LATEX_BY_FORMULA.get(p["formula"])

    constantes = [
        {"simbolo": "φ_sold", "latex": r"\phi_{sold} = 0.75", "valor": PHI_SOLD,      "unidad": "", "desc": "Factor LRFD a soldadura de filete (§J2.4)."},
        {"simbolo": "φ_perno","latex": r"\phi_{perno} = 0.75","valor": PHI_PERNO,     "unidad": "", "desc": "Factor LRFD a pernos (corte/traccion/aplast.) (§J3.6)."},
        {"simbolo": "φ_fy",   "latex": r"\phi_{fy} = 0.90",   "valor": PHI_FLUENCIA,  "unidad": "", "desc": "Factor LRFD fluencia por traccion (§J4.1)."},
        {"simbolo": "φ_ru",   "latex": r"\phi_{ru} = 0.75",   "valor": PHI_ROTURA,    "unidad": "", "desc": "Factor LRFD rotura por traccion (§J4.2)."},
        {"simbolo": "φ_vy",   "latex": r"\phi_{vy} = 1.00",   "valor": PHI_CORTE_FLU, "unidad": "", "desc": "Factor LRFD fluencia por cortante (§J4.3)."},
        {"simbolo": "φ_bs",   "latex": r"\phi_{bs} = 0.75",   "valor": PHI_BLOCK,     "unidad": "", "desc": "Factor LRFD block shear (§J4.5)."},
        {"simbolo": "F_EXX",  "latex": r"F_{EXX} = 4920",     "valor": FEXX_E70,      "unidad": "kgf/cm²", "desc": "Electrodo E70XX (70 ksi)."},
        {"simbolo": "0.707",  "latex": r"t_e = 0.707\,w",     "valor": COEF_GARG,     "unidad": "", "desc": "Factor de garganta del filete (§J2.2a)."},
        {"simbolo": "U_bs",   "latex": r"U_{bs} = 1.0",       "valor": UBS,           "unidad": "", "desc": "Factor de tension uniforme en block shear (§J4.3)."},
    ]
    meta = {
        "tipo_conexion": tn,
        "ficha":     ficha["ficha"],
        "rotulo":    ficha["rotulo"],
        "aproximado": ficha["aproximado"],
        "descripcion": ficha["descripcion"],
        "perfil_viga": elem.get("perfil_viga", ""),
        "perfil_columna": elem.get("perfil_columna", ""),
        "material":  f"{mat['desc']} · F_y {_fmt(Fy)} / F_u {_fmt(Fu)} kgf/cm²",
        "estado_gobernante": _EST_LBL.get(gob, gob) if gob else None,
        "phi_rn_gobernante_t": phi_gob,
        "demanda_t": res["demanda_t"],
        "dc_ratio":  res["dc_ratio"],
        "cumple":    bool(res["cumple"]),
        "seccion":   ficha["rotulo"],
        "resumen":   (f"{ficha['ficha']} · {_EST_LBL.get(gob, gob) if gob else '—'} gobierna · "
                      f"φRn={_fmt(phi_gob)} t · D={_fmt(res['demanda_t'])} t · DC={_fmt(res['dc_ratio'])}"
                      if phi_gob else f"{ficha['ficha']} · faltan datos de geometria"),
    }
    return {"meta": meta, "pasos": P, "resultado": res, "constantes": constantes}
