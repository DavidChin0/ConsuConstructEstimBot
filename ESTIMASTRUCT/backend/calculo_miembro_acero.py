# -*- coding: utf-8 -*-
"""
Motor de calculo — Miembros de Acero LRFD (AISC 360-16 §D/E/F/G/H)
===================================================================
Verificacion INDEPENDIENTE de miembros de acero por metodo LRFD, estilo
Mathcad. METRICO: kgf, cm, t.  Demanda ≤ φRn  (§B3.1).

Calcula φRn PROPIO por estado limite (no lee el D/C de ETABS): sirve de
chequeo cruzado del Steel Frame Design de ETABS.

Estados implementados:
  §D  Traccion        — fluencia (D2-1) + rotura (D2-2)
  §E  Compresion      — pandeo por flexion (E3): Fe (E3-4), Fcr (E3-2/3), Pn (E3-1)
  §F  Flexion         — fluencia Mp (F2-1) + pandeo lateral-torsional (F2-2/3)
  §G  Cortante        — fluencia del alma (G2-1)
  §H  Flexo-compresion— interaccion (H1-1a / H1-1b)

Propiedades de seccion (Ix, Sx, Zx, rx, ry, J, Cw, ho, rts) DERIVADAS de la
geometria d/bf/tf/tw via perfiles_acero.props_seccion() — se muestran como
pasos en la memoria (notacion exacta). HSS: §E/§F omitidos (formula I-shape
no aplica) — fase siguiente.

Funciones PURAS (sin ORM). Reutiliza helpers de formato/LaTeX de
calculo_estructural (DRY) y las tablas de perfiles_acero.py.
"""

import math
import re

from backend.calculo_estructural import _fmt, _ascii_to_latex
from backend.perfiles_acero import (
    PERFILES_ACERO, ACEROS, E_ACERO, G_ACERO, props_seccion, _es_hss,
)


# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTES — factores φ (LRFD) con referencia AISC 360-16
# ─────────────────────────────────────────────────────────────────────────────
PHI_T_FLU   = 0.90   # §D2(a)  fluencia por traccion
PHI_T_ROT   = 0.75   # §D2(b)  rotura por traccion
PHI_C       = 0.90   # §E1     compresion
PHI_B       = 0.90   # §F1     flexion
PHI_V       = 1.00   # §G1     cortante (almas laminadas compactas, h/tw≤2.24√(E/Fy))
PHI_V_ESB   = 0.90   # §G1     cortante (resto)

KV_ALMA     = 5.34   # coeficiente de pandeo por cortante del alma sin atiesadores
COEF_LP     = 1.76   # F2-5
COEF_LR     = 1.95   # F2-6
KG_A_T      = 1.0 / 1000.0       # kgf -> t
KGCM_A_TM   = 1.0 / 100000.0     # kgf·cm -> t·m


def _norm(perfil: str) -> str:
    """Normaliza designacion (mayusc, sin espacios, ×->X, sin (imperial))."""
    if not perfil:
        return ""
    s = str(perfil).strip().upper()
    s = re.sub(r"\([^)]*\)", "", s)
    s = s.replace('"', "").replace("”", "").replace("''", "").replace("×", "X")
    return re.sub(r"\s+", "", s)


def _perfil(perfil: str) -> dict:
    return PERFILES_ACERO.get(_norm(perfil),
                              {"d": 0.0, "bf": 0.0, "tf": 0.0, "tw": 0.0, "Ag": 0.0})


def _mat(acero: str) -> dict:
    return ACEROS.get((acero or "A992").upper(), ACEROS["A992"])


# ─────────────────────────────────────────────────────────────────────────────
# §D — TRACCION
# ─────────────────────────────────────────────────────────────────────────────
def pn_fluencia_traccion(Fy, Ag):
    """φPn fluencia en el area bruta (D2-1): φ·Fy·Ag  [kgf].  φ=0.90."""
    return PHI_T_FLU * Fy * Ag


def pn_rotura_traccion(Fu, Ae):
    """φPn rotura en el area neta efectiva (D2-2): φ·Fu·Ae  [kgf].  φ=0.75."""
    return PHI_T_ROT * Fu * Ae


# ─────────────────────────────────────────────────────────────────────────────
# §E — COMPRESION (pandeo por flexion, E3)
# ─────────────────────────────────────────────────────────────────────────────
def esbeltez_columna(K, L, r):
    """Relacion de esbeltez KL/r (adimensional)."""
    return K * L / r if r > 0 else 0.0


def fe_euler(KLr):
    """Esfuerzo critico de pandeo elastico de Euler (E3-4): Fe = π²E/(KL/r)²."""
    return math.pi ** 2 * E_ACERO / KLr ** 2 if KLr > 0 else float("inf")


def fcr_columna(Fy, Fe, KLr):
    """Esfuerzo critico Fcr (E3-2 inelastico / E3-3 elastico).
    Frontera: KL/r ≤ 4.71·√(E/Fy)  (equivale a Fy/Fe ≤ 2.25)."""
    lim = 4.71 * math.sqrt(E_ACERO / Fy)
    if KLr <= lim:
        return (0.658 ** (Fy / Fe)) * Fy          # E3-2
    return 0.877 * Fe                              # E3-3


def pn_compresion(Fcr, Ag):
    """φPn compresion (E3-1): φ·Fcr·Ag  [kgf].  φ=0.90."""
    return PHI_C * Fcr * Ag


# ─────────────────────────────────────────────────────────────────────────────
# §F — FLEXION (fluencia + pandeo lateral-torsional, F2)
# ─────────────────────────────────────────────────────────────────────────────
def mp_plastico(Fy, Zx):
    """Momento plastico (F2-1): Mp = Fy·Zx  [kgf·cm]."""
    return Fy * Zx


def lp_limite(ry, Fy):
    """Lp limite de fluencia (F2-5): Lp = 1.76·ry·√(E/Fy)  [cm]."""
    return COEF_LP * ry * math.sqrt(E_ACERO / Fy)


def lr_limite(rts, Sx, J, ho, Fy):
    """Lr limite de LTB inelastico (F2-6)  [cm]."""
    a = COEF_LR * rts * (E_ACERO / (0.7 * Fy))
    rad = J / (Sx * ho) if (Sx * ho) > 0 else 0.0
    interno = 1.0 + math.sqrt(1.0 + 6.76 * ((0.7 * Fy / E_ACERO) * (Sx * ho / J)) ** 2) if J > 0 else 1.0
    return a * math.sqrt(rad) * math.sqrt(interno)


def mn_flexion(Fy, Zx, Sx, ry, rts, J, ho, Lb, Cb):
    """Mn por F2: fluencia / LTB inelastico / LTB elastico  [kgf·cm].
    Devuelve (Mn, Mp, Lp, Lr, zona)."""
    Mp = mp_plastico(Fy, Zx)
    Lp = lp_limite(ry, Fy)
    Lr = lr_limite(rts, Sx, J, ho, Fy)
    if Lb <= Lp:
        return Mp, Mp, Lp, Lr, "plastico"                      # F2-1
    if Lb <= Lr:                                               # F2-2 (LTB inelastico)
        Mn = Cb * (Mp - (Mp - 0.7 * Fy * Sx) * (Lb - Lp) / (Lr - Lp))
        return min(Mn, Mp), Mp, Lp, Lr, "LTB inelastico"
    # F2-3/F2-4 (LTB elastico)
    Lb_rts = Lb / rts if rts > 0 else 0.0
    Fcr = (Cb * math.pi ** 2 * E_ACERO / Lb_rts ** 2) * \
          math.sqrt(1.0 + 0.078 * (J / (Sx * ho)) * Lb_rts ** 2) if Lb_rts > 0 else 0.0
    return min(Fcr * Sx, Mp), Mp, Lp, Lr, "LTB elastico"


def mny_eje_debil(Fy, Zy, Sy):
    """Mn eje debil (F6-1): Mn = min(Fy·Zy, 1.6·Fy·Sy)  [kgf·cm]. Sin LTB."""
    return min(Fy * Zy, 1.6 * Fy * Sy)


# ─────────────────────────────────────────────────────────────────────────────
# §G — CORTANTE (G2)
# ─────────────────────────────────────────────────────────────────────────────
def vn_cortante(Fy, d, tw, hw):
    """φVn fluencia del alma (G2-1): φ·0.6·Fy·Aw·Cv1  [kgf].
    Devuelve (φVn, Aw, Cv1, phi_v, compacta_bool)."""
    Aw = d * tw
    h_tw = hw / tw if tw > 0 else 1e9
    lim = 2.24 * math.sqrt(E_ACERO / Fy)
    if h_tw <= lim:
        Cv1, phi_v, compacta = 1.0, PHI_V, True                # §G2.1(a)
    else:
        lim2 = 1.10 * math.sqrt(KV_ALMA * E_ACERO / Fy)
        Cv1 = (lim2 / h_tw) if h_tw > lim2 else 1.0            # G2-4 (aprox)
        phi_v, compacta = PHI_V_ESB, False
    Vn = 0.6 * Fy * Aw * Cv1
    return phi_v * Vn, Aw, Cv1, phi_v, compacta


def mn_flexion_hss(Fy, Zx, Sx, lam):
    """Mn de HSS cuadrado/rectangular (§F7): fluencia Mp + pandeo local de ala (FLB).
    SIN pandeo lateral-torsional (sección cerrada doblemente simétrica). lam = ancho
    plano/t. Devuelve (Mn, zona)  [kgf·cm]."""
    Mp = Fy * Zx
    lam_p = 1.12 * math.sqrt(E_ACERO / Fy)       # F7: ala compacta
    lam_r = 1.40 * math.sqrt(E_ACERO / Fy)       # F7: ala no-compacta
    if lam <= lam_p:
        return Mp, "plastico (compacta)"
    if lam <= lam_r:                             # F7-2 ala no-compacta
        Mn = Mp - (Mp - Fy * Sx) * (3.57 * lam * math.sqrt(Fy / E_ACERO) - 4.0)
        return min(max(Mn, Fy * Sx), Mp), "FLB no-compacta"
    return Fy * Sx, "FLB esbelta (Se≈Sx aprox)"   # F7-3 (ancho efectivo no codificado)


def vn_cortante_hss(Fy, t, flat):
    """φVn de HSS (§G4): φ·0.6·Fy·Aw·Cv2, Aw = 2·h·t (las 2 almas), h = ancho plano.
    kv=5, φ=0.90. Devuelve (φVn, Aw, Cv2, compacta_bool)."""
    Aw = 2.0 * flat * t
    h_t = flat / t if t > 0 else 1e9
    kv = 5.0
    lim1 = 1.10 * math.sqrt(kv * E_ACERO / Fy)
    lim2 = 1.37 * math.sqrt(kv * E_ACERO / Fy)
    if h_t <= lim1:
        Cv2, compacta = 1.0, True
    elif h_t <= lim2:
        Cv2, compacta = lim1 / h_t, False
    else:
        Cv2, compacta = 1.51 * kv * E_ACERO / (h_t ** 2 * Fy), False
    Vn = 0.6 * Fy * Aw * Cv2
    return PHI_V_ESB * Vn, Aw, Cv2, compacta


# ─────────────────────────────────────────────────────────────────────────────
# §H — FLEXO-COMPRESION / INTERACCION (H1)
# ─────────────────────────────────────────────────────────────────────────────
def interaccion_h1(Pr, Pc, Mrx, Mcx, Mry, Mcy):
    """Razon de interaccion (H1-1a / H1-1b). Devuelve (valor, ecuacion)."""
    if Pc <= 0:
        return None, "—"
    p = Pr / Pc
    mom = (Mrx / Mcx if Mcx > 0 else 0.0) + (Mry / Mcy if Mcy > 0 else 0.0)
    if p >= 0.2:
        return p + (8.0 / 9.0) * mom, "H1-1a"
    return p / 2.0 + mom, "H1-1b"


# ─────────────────────────────────────────────────────────────────────────────
# FUNCION MAESTRA — calcular_miembro  (UNICA fuente de verdad)
# ─────────────────────────────────────────────────────────────────────────────
def calcular_miembro(elem: dict, caso: dict) -> dict:
    """
    elem keys: perfil, acero, L_cm, K, Lb_cm, Cb
    caso keys: pu_t (+tracc / -compr), mux_tm, muy_tm, vu_t

    Devuelve φRn por estado [t / t·m], DC por estado, gobernante (max DC),
    cumple. Guards anti-NaN. NO toca BD.
    """
    pn   = elem.get("perfil", "")
    pdict = _perfil(pn)
    pr   = props_seccion(pdict, pn)
    mat  = _mat(elem.get("acero", "A992"))
    Fy, Fu = mat["Fy"], mat["Fu"]
    Ag = pr.get("Ag", pdict.get("Ag", 0.0))   # de TABLA_W (real) o geometria
    es_hss = bool(pr.get("hss"))

    L  = float(elem.get("L_cm", 0) or 0)
    K  = float(elem.get("K", 1.0) or 1.0)
    Lb = float(elem.get("Lb_cm", 0) or 0) or L
    Cb = float(elem.get("Cb", 1.0) or 1.0)

    Pu  = float(caso.get("pu_t", 0) or 0)
    Mux = abs(float(caso.get("mux_tm", 0) or 0))
    Muy = abs(float(caso.get("muy_tm", 0) or 0))
    Vu  = abs(float(caso.get("vu_t", 0) or 0))

    estados = {}   # nombre -> {phi_rn, demanda, dc, unidad}
    avisos = []

    # Demanda aplicada (distingue "sin carga" de "no cumple")
    hay_demanda = (Pu != 0) or (Mux > 0) or (Muy > 0) or (Vu > 0)

    # Las CAPACIDADES (φRn) se calculan SIEMPRE para el perfil dado (hoja de
    # capacidades estilo Mathcad). La DEMANDA puede ser 0 -> DC=0. Sin demanda el
    # miembro cumple trivialmente: no hay nada que resistir (no es "no cumple").

    # ── §D TRACCION (capacidad siempre; demanda solo si Pu>0) ─────────────────
    if Ag > 0:
        Ae = Ag   # miembro sin agujeros: U=1; con conexion pernada Ae<Ag (ver §J)
        phiPn_t = min(pn_fluencia_traccion(Fy, Ag), pn_rotura_traccion(Fu, Ae)) * KG_A_T
        dem_t = Pu if Pu > 0 else 0.0
        estados["traccion"] = {"phi_rn": round(phiPn_t, 3), "demanda": round(dem_t, 3),
                               "dc": round(dem_t / phiPn_t, 4) if phiPn_t > 0 else None, "u": "t"}
        if Pu > 0:
            avisos.append("Traccion: Ae=Ag (U=1, miembro sin agujeros). Con conexion pernada revisar §D3.")

    # ── §E COMPRESION (§E3 pandeo por flexion; vale para I-shape y HSS cuadrado) ─
    phiPn_c = None
    if Ag > 0 and L > 0 and pr.get("rx", 0) > 0:
        r_min = min(pr["rx"], pr["ry"])
        KLr = esbeltez_columna(K, L, r_min)
        Fe  = fe_euler(KLr)
        Fcr = fcr_columna(Fy, Fe, KLr)
        phiPn_c = pn_compresion(Fcr, Ag) * KG_A_T
        dem_c = -Pu if Pu < 0 else 0.0
        estados["compresion"] = {"phi_rn": round(phiPn_c, 3), "demanda": round(dem_c, 3),
                                 "dc": round(dem_c / phiPn_c, 4) if phiPn_c > 0 else None, "u": "t"}
        if Pu < 0 and KLr > 200:
            avisos.append(f"KL/r={KLr:.0f} > 200: esbeltez excesiva (§E2 recomienda ≤200).")
        if es_hss and Pu < 0:
            lam = pr.get("lam_ala", 0.0)
            lam_r = 1.40 * math.sqrt(E_ACERO / Fy)
            if lam > lam_r:
                avisos.append(f"HSS pared esbelta (b/t={lam:.0f} > {lam_r:.0f}): §E7 reduce φPn (no codificado, optimista).")

    # ── §F FLEXION (I-shape §F2 con LTB · HSS cuadrado §F7 sin LTB) ────────────
    phiMnx = None
    phiMny = None
    if not es_hss and pr.get("Zx", 0) > 0:
        Mn, Mp, Lp, Lr, zona = mn_flexion(Fy, pr["Zx"], pr["Sx"], pr["ry"], pr["rts"],
                                          pr["J"], pr["ho"], Lb, Cb)
        phiMnx = PHI_B * Mn * KGCM_A_TM
        estados["flexion_x"] = {"phi_rn": round(phiMnx, 3), "demanda": round(Mux, 3),
                                "dc": round(Mux / phiMnx, 4) if phiMnx > 0 else None, "u": "t·m"}
        Mny = mny_eje_debil(Fy, pr["Zy"], pr["Sy"])
        phiMny = PHI_B * Mny * KGCM_A_TM
        estados["flexion_y"] = {"phi_rn": round(phiMny, 3), "demanda": round(Muy, 3),
                                "dc": round(Muy / phiMny, 4) if phiMny > 0 else None, "u": "t·m"}
    elif es_hss and pr.get("Zx", 0) > 0:
        Mn_h, _zona_h = mn_flexion_hss(Fy, pr["Zx"], pr["Sx"], pr.get("lam_ala", 0.0))
        phiMnx = PHI_B * Mn_h * KGCM_A_TM
        estados["flexion_x"] = {"phi_rn": round(phiMnx, 3), "demanda": round(Mux, 3),
                                "dc": round(Mux / phiMnx, 4) if phiMnx > 0 else None, "u": "t·m"}
        phiMny = phiMnx   # HSS cuadrado: eje débil = eje fuerte (Iy = Ix)
        estados["flexion_y"] = {"phi_rn": round(phiMny, 3), "demanda": round(Muy, 3),
                                "dc": round(Muy / phiMny, 4) if phiMny > 0 else None, "u": "t·m"}

    # ── §G CORTANTE (I-shape §G2 · HSS §G4) ───────────────────────────────────
    if not es_hss and pr.get("d", 0) > 0 and pr.get("tw", 0) > 0:
        phiVn, Aw, Cv1, phi_v, compacta = vn_cortante(Fy, pr["d"], pr["tw"], pr["hw"])
        phiVn_t = phiVn * KG_A_T
        estados["cortante"] = {"phi_rn": round(phiVn_t, 3), "demanda": round(Vu, 3),
                               "dc": round(Vu / phiVn_t, 4) if phiVn_t > 0 else None, "u": "t"}
    elif es_hss and pr.get("hw", 0) > 0 and pr.get("tw", 0) > 0:
        phiVn, Aw, Cv2, compacta = vn_cortante_hss(Fy, pr["tw"], pr["hw"])
        phiVn_t = phiVn * KG_A_T
        estados["cortante"] = {"phi_rn": round(phiVn_t, 3), "demanda": round(Vu, 3),
                               "dc": round(Vu / phiVn_t, 4) if phiVn_t > 0 else None, "u": "t"}

    # ── §H INTERACCION (solo con demanda combinada axial+flexion real) ─────────
    if (Pu < 0 and (Mux > 0 or Muy > 0)) and phiPn_c and (phiMnx or phiMny):
        Pc  = phiPn_c
        Mcx = phiMnx or 1e9
        Mcy = phiMny or 1e9
        val, ec = interaccion_h1(abs(Pu), Pc, Mux, Mcx, Muy, Mcy)
        if val is not None:
            estados["interaccion"] = {"phi_rn": 1.0, "demanda": round(val, 4),
                                      "dc": round(val, 4), "u": "", "ec": ec}

    # ── GOBERNANTE / CUMPLE ───────────────────────────────────────────────────
    # Sin demanda -> cumple trivialmente (capacidades quedan con DC=0). Con
    # demanda -> gobierna el mayor DC entre estados con demanda > 0.
    if not hay_demanda:
        gobernante = None
        dc_gob = None
        cumple = True
    else:
        con_dc = {k: v for k, v in estados.items()
                  if v.get("dc") is not None and v.get("demanda", 0) > 0}
        gobernante = max(con_dc, key=lambda k: con_dc[k]["dc"]) if con_dc else None
        dc_gob = con_dc[gobernante]["dc"] if gobernante else None
        cumple = (dc_gob is not None and dc_gob <= 1.0)

    return {
        "perfil": _norm(pn),
        "es_hss": es_hss,
        "props": {k: (round(v, 4) if isinstance(v, (int, float)) else v) for k, v in pr.items()},
        "Fy": Fy, "Fu": Fu, "Ag": Ag,
        "estados": estados,
        "estado_gobernante": gobernante,
        "dc_gobernante": dc_gob,
        "cumple": bool(cumple),
        "avisos": avisos,
    }


# ─────────────────────────────────────────────────────────────────────────────
# MEMORIA DE CALCULO narrada (estilo Mathcad)
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


LATEX_BY_FORMULA = {
    # Seccion (propiedades derivadas)
    "Zx = bf·tf·(d−tf) + tw·hw²/4":   r"Z_x = b_f t_f (d-t_f) + \dfrac{t_w h_w^2}{4}",
    "Sx = 2·Ix/d":                    r"S_x = \dfrac{2 I_x}{d}",
    "rx = √(Ix/Ag) ; ry = √(Iy/Ag)":  r"r_x=\sqrt{\dfrac{I_x}{A_g}},\;\; r_y=\sqrt{\dfrac{I_y}{A_g}}",
    "rts = √(√(Iy·Cw)/Sx)":           r"r_{ts}=\sqrt{\dfrac{\sqrt{I_y C_w}}{S_x}}",
    # §D
    "φPn = min(0.90·Fy·Ag, 0.75·Fu·Ae)": r"\phi P_n=\min(0.90\,F_y A_g,\;0.75\,F_u A_e)",
    # §E
    "KL/r = K·L/r_min":               r"\dfrac{KL}{r}=\dfrac{K\,L}{r_{min}}",
    "Fe = π²E/(KL/r)²":               r"F_e=\dfrac{\pi^2 E}{(KL/r)^2}",
    "Fcr = 0.658^(Fy/Fe)·Fy   si KL/r ≤ 4.71√(E/Fy)": r"F_{cr}=\left(0.658^{F_y/F_e}\right)F_y",
    "Fcr = 0.877·Fe   si KL/r > 4.71√(E/Fy)": r"F_{cr}=0.877\,F_e",
    "φPn = 0.90·Fcr·Ag":              r"\phi P_n=0.90\,F_{cr} A_g",
    # §F
    "Mp = Fy·Zx":                     r"M_p=F_y Z_x",
    "Lp = 1.76·ry·√(E/Fy)":           r"L_p=1.76\,r_y\sqrt{\dfrac{E}{F_y}}",
    "Lr = 1.95·rts·(E/0.7Fy)·√(J/(Sx·ho))·√(1+√(1+6.76(0.7Fy·Sx·ho/(E·J))²))":
        r"L_r=1.95\,r_{ts}\dfrac{E}{0.7F_y}\sqrt{\dfrac{J}{S_x h_o}}\sqrt{1+\sqrt{1+6.76\left(\dfrac{0.7F_y}{E}\dfrac{S_x h_o}{J}\right)^2}}",
    "Mn = Mp   (Lb ≤ Lp)":            r"M_n=M_p \quad (L_b\le L_p)",
    "Mn = Cb·[Mp − (Mp−0.7Fy·Sx)(Lb−Lp)/(Lr−Lp)] ≤ Mp":
        r"M_n=C_b\left[M_p-(M_p-0.7F_y S_x)\dfrac{L_b-L_p}{L_r-L_p}\right]\le M_p",
    "Mn = Fcr·Sx ≤ Mp   (Lb > Lr)":   r"M_n=F_{cr}S_x\le M_p\quad(L_b>L_r)",
    "φMn = 0.90·Mn":                  r"\phi M_n=0.90\,M_n",
    "Mny = min(Fy·Zy, 1.6·Fy·Sy)":    r"M_{ny}=\min(F_y Z_y,\;1.6F_y S_y)",
    # §G
    "φVn = φ·0.6·Fy·Aw·Cv1":          r"\phi V_n=\phi\,0.6\,F_y A_w C_{v1}",
    # §H
    "Pr/Pc + (8/9)(Mrx/Mcx + Mry/Mcy) ≤ 1.0   (Pr/Pc ≥ 0.2)":
        r"\dfrac{P_r}{P_c}+\dfrac{8}{9}\!\left(\dfrac{M_{rx}}{M_{cx}}+\dfrac{M_{ry}}{M_{cy}}\right)\le 1.0",
    "Pr/(2Pc) + (Mrx/Mcx + Mry/Mcy) ≤ 1.0   (Pr/Pc < 0.2)":
        r"\dfrac{P_r}{2P_c}+\left(\dfrac{M_{rx}}{M_{cx}}+\dfrac{M_{ry}}{M_{cy}}\right)\le 1.0",
    "DC = demanda / φRn":             r"DC=\dfrac{\text{demanda}}{\phi R_n}\le 1.0",
}


_EST_LBL = {
    "traccion": "Traccion §D", "compresion": "Compresion §E",
    "flexion_x": "Flexion eje fuerte §F", "flexion_y": "Flexion eje debil §F6",
    "cortante": "Cortante §G", "interaccion": "Flexo-compresion §H1",
}


def memoria_miembro(elem: dict, caso: dict) -> dict:
    """Memoria narrada de un miembro de acero. {meta, pasos[], constantes[]}."""
    res = calcular_miembro(elem, caso)
    pn  = res["perfil"]
    pdict = _perfil(pn)
    pr  = res["props"]
    mat = _mat(elem.get("acero", "A992"))
    Fy, Fu = mat["Fy"], mat["Fu"]
    Ag = res["Ag"]
    est = res["estados"]
    es_hss = res["es_hss"]

    L  = float(elem.get("L_cm", 0) or 0)
    K  = float(elem.get("K", 1.0) or 1.0)
    Lb = float(elem.get("Lb_cm", 0) or 0) or L
    Cb = float(elem.get("Cb", 1.0) or 1.0)
    Pu  = float(caso.get("pu_t", 0) or 0)
    Mux = abs(float(caso.get("mux_tm", 0) or 0))
    Muy = abs(float(caso.get("muy_tm", 0) or 0))
    Vu  = abs(float(caso.get("vu_t", 0) or 0))

    P = []

    # ── MATERIAL ──────────────────────────────────────────────────────────────
    P.append(_paso("Material", "F_y · F_u", f"Acero {mat['desc']}",
        f"{_fmt(Fy)} / {_fmt(Fu)}", "kgf/cm²",
        "propiedades del material", f"F_y = {_fmt(Fy)} · F_u = {_fmt(Fu)}",
        "AISC Tabla 2-4", "Fluencia y rotura del acero del perfil.", "input"))
    P.append(_paso("Material", "E", "Modulo de elasticidad", E_ACERO, "kgf/cm²",
        "constante del acero (29 000 ksi)", f"E = {_fmt(E_ACERO)}", "AISC 360-16 §E",
        "Rigidez del acero; gobierna pandeo (Fe) y LTB.", "input"))

    # ── SECCION (propiedades de tabla AISC/CISC) ──────────────────────────────
    fuente_lbl = "CISC/AISC 16a (TABLA_W)" if pr.get("fuente") == "tabla" else "derivada de la geometria (aprox)"
    P.append(_paso("Seccion", pn, f"Perfil {pn}",
        f"d={_fmt(pr.get('d',0))} · b_f={_fmt(pr.get('bf',0))} · t_f={_fmt(pr.get('tf',0))} · t_w={_fmt(pr.get('tw',0))}", "cm",
        f"propiedades — {fuente_lbl}",
        f"A_g = {_fmt(Ag)} cm²", "AISC 360-16 / CISC Handbook",
        "Geometria y propiedades del perfil (tabla AISC/CISC). Alimentan §D-§H.", "input"))
    if not es_hss:
        P.append(_paso("Seccion", "Z_x · S_x", "Modulos plastico / elastico (eje fuerte)",
            f"{_fmt(pr['Zx'],1)} / {_fmt(pr['Sx'],1)}", "cm³",
            "tabla AISC/CISC", f"Z_x = {_fmt(pr['Zx'],1)} · S_x = {_fmt(pr['Sx'],1)}",
            "AISC Shapes / CISC", "Z_x define Mp = F_y·Z_x; S_x gobierna el LTB elastico.", "input"))
        P.append(_paso("Seccion", "r_x · r_y", "Radios de giro", f"{_fmt(pr['rx'],2)} / {_fmt(pr['ry'],2)}", "cm",
            "tabla AISC/CISC (r_y) · r_x = √(I_x/A_g)", f"r_x = {_fmt(pr['rx'],2)} · r_y = {_fmt(pr['ry'],2)}",
            "AISC Shapes / CISC", "El radio MENOR gobierna el pandeo por flexion (KL/r).", "input"))
        P.append(_paso("Seccion", "r_ts · J · C_w", "Constantes de LTB",
            f"{_fmt(pr['rts'],2)} · {_fmt(pr['J'],1)} · {_fmt(pr['Cw'],0)}", "cm·cm⁴·cm⁶",
            "tabla AISC/CISC", f"r_ts = {_fmt(pr['rts'],2)} · J = {_fmt(pr['J'],1)} · C_w = {_fmt(pr['Cw'],0)}",
            "AISC 360-16 §F2", "Entran en L_r y en el M_n del pandeo lateral-torsional elastico.", "input"))
    else:
        P.append(_paso("Seccion", "Z · S · r", "Modulos y radio (HSS cuadrado)",
            f"Z={_fmt(pr['Zx'],1)} · S={_fmt(pr['Sx'],1)} · r={_fmt(pr['rx'],2)}", "cm³·cm³·cm",
            "seccion cerrada doblemente simetrica (I_x=I_y)",
            f"Z = {_fmt(pr['Zx'],1)} cm³ · S = {_fmt(pr['Sx'],1)} cm³ · r = {_fmt(pr['rx'],2)} cm · b/t = {_fmt(pr.get('lam_ala',0),1)}",
            "AISC 360-16 §F7/§E3", "HSS cuadrado: Z_x=Z_y, SIN pandeo lateral-torsional; b/t define el pandeo local de pared.", "input"))

    # ── DEMANDA ───────────────────────────────────────────────────────────────
    if Pu != 0:
        tipo_ax = "traccion (+)" if Pu > 0 else "compresion (−)"
        P.append(_paso("Demanda", "P_u", f"Carga axial ultima — {tipo_ax}", Pu, "t",
            "demanda del analisis (ETABS, combo LRFD)", f"P_u = {_fmt(Pu)}", "AISC §B3.1",
            "Fuerza axial ultima. Signo: + traccion (§D), − compresion (§E).", "input"))
    if Mux > 0:
        P.append(_paso("Demanda", "M_ux", "Momento ultimo (eje fuerte)", Mux, "t·m",
            "demanda del analisis", f"M_ux = {_fmt(Mux)}", "AISC §B3.1",
            "Momento flector ultimo respecto al eje fuerte.", "input"))
    if Muy > 0:
        P.append(_paso("Demanda", "M_uy", "Momento ultimo (eje debil)", Muy, "t·m",
            "demanda del analisis", f"M_uy = {_fmt(Muy)}", "AISC §B3.1",
            "Momento flector ultimo respecto al eje debil.", "input"))
    if Vu > 0:
        P.append(_paso("Demanda", "V_u", "Cortante ultimo", Vu, "t",
            "demanda del analisis", f"V_u = {_fmt(Vu)}", "AISC §B3.1",
            "Fuerza cortante ultima.", "input"))
    if L > 0:
        P.append(_paso("Demanda", "L · K · Lb · Cb", "Longitud y factores",
            f"L={_fmt(L)} · K={_fmt(K)} · Lb={_fmt(Lb)} · Cb={_fmt(Cb)}", "cm",
            "datos del modelo / arriostramiento", f"L = {_fmt(L)} cm", "AISC §C/§F",
            "Longitud, factor de longitud efectiva K, longitud sin soporte lateral Lb y factor Cb.", "input"))

    # ── §D TRACCION ───────────────────────────────────────────────────────────
    if "traccion" in est:
        e = est["traccion"]
        P.append(_paso("§D Traccion", "φP_n", "Resistencia a traccion (D2)", e["phi_rn"], "t",
            "φPn = min(0.90·Fy·Ag, 0.75·Fu·Ae)",
            f"min(0.90·{_fmt(Fy)}·{_fmt(Ag)}, 0.75·{_fmt(Fu)}·{_fmt(Ag)}) = {_fmt(e['phi_rn'])} t",
            "AISC 360-16 §D2", "Menor entre fluencia del area bruta y rotura del area neta.", "resultado",
            latex=LATEX_BY_FORMULA["φPn = min(0.90·Fy·Ag, 0.75·Fu·Ae)"]))

    # ── §E COMPRESION ─────────────────────────────────────────────────────────
    if "compresion" in est:
        r_min = min(pr["rx"], pr["ry"])
        KLr = K * L / r_min if r_min > 0 else 0.0
        Fe  = math.pi ** 2 * E_ACERO / KLr ** 2 if KLr > 0 else 0.0
        lim = 4.71 * math.sqrt(E_ACERO / Fy)
        Fcr = fcr_columna(Fy, Fe, KLr)
        e = est["compresion"]
        P.append(_paso("§E Compresion", "KL/r", "Esbeltez", round(KLr, 1), "",
            "KL/r = K·L/r_min", f"{_fmt(K)}·{_fmt(L)}/{_fmt(r_min,2)} = {_fmt(KLr,1)}",
            "AISC 360-16 §E2", "Relacion de esbeltez; r_min gobierna (eje debil).", "intermedio",
            latex=LATEX_BY_FORMULA["KL/r = K·L/r_min"]))
        P.append(_paso("§E Compresion", "F_e", "Esfuerzo de Euler", round(Fe, 1), "kgf/cm²",
            "Fe = π²E/(KL/r)²", f"π²·{_fmt(E_ACERO)}/{_fmt(KLr,1)}² = {_fmt(Fe,1)}",
            "AISC 360-16 ec.E3-4", "Esfuerzo de pandeo elastico (Euler).", "intermedio",
            latex=LATEX_BY_FORMULA["Fe = π²E/(KL/r)²"]))
        inelastico = KLr <= lim
        fkey = "Fcr = 0.658^(Fy/Fe)·Fy   si KL/r ≤ 4.71√(E/Fy)" if inelastico else "Fcr = 0.877·Fe   si KL/r > 4.71√(E/Fy)"
        P.append(_paso("§E Compresion", "F_cr", "Esfuerzo critico", round(Fcr, 1), "kgf/cm²",
            fkey,
            (f"0.658^({_fmt(Fy)}/{_fmt(Fe,1)})·{_fmt(Fy)} = {_fmt(Fcr,1)}" if inelastico
             else f"0.877·{_fmt(Fe,1)} = {_fmt(Fcr,1)}")
            + f"  ({'inelastico' if inelastico else 'elastico'}, limite KL/r={_fmt(lim,1)})",
            "AISC 360-16 ec.E3-2/E3-3", "Esfuerzo critico de pandeo (inelastico si KL/r ≤ 4.71√(E/Fy)).", "intermedio",
            latex=LATEX_BY_FORMULA[fkey]))
        P.append(_paso("§E Compresion", "φP_n", "Resistencia a compresion (E3-1)", e["phi_rn"], "t",
            "φPn = 0.90·Fcr·Ag", f"0.90·{_fmt(Fcr,1)}·{_fmt(Ag)} = {_fmt(e['phi_rn'])} t",
            "AISC 360-16 §E3", "Resistencia de diseño a compresion por pandeo por flexion.", "resultado",
            latex=LATEX_BY_FORMULA["φPn = 0.90·Fcr·Ag"]))

    # ── §F FLEXION (I-shape §F2 con LTB · HSS §F7 sin LTB) ────────────────────
    if "flexion_x" in est:
        e = est["flexion_x"]
        if not es_hss:
            Mn, Mp, Lp, Lr, zona = mn_flexion(Fy, pr["Zx"], pr["Sx"], pr["ry"], pr["rts"],
                                              pr["J"], pr["ho"], Lb, Cb)
            P.append(_paso("§F Flexion", "M_p", "Momento plastico (F2-1)", round(Mp * KGCM_A_TM, 3), "t·m",
                "Mp = Fy·Zx", f"{_fmt(Fy)}·{_fmt(pr['Zx'],1)} = {_fmt(Mp,0)} kgf·cm = {_fmt(Mp*KGCM_A_TM,3)} t·m",
                "AISC 360-16 ec.F2-1", "Momento de plastificacion total de la seccion.", "intermedio",
                latex=LATEX_BY_FORMULA["Mp = Fy·Zx"]))
            P.append(_paso("§F Flexion", "L_p · L_r", "Limites de arriostramiento",
                f"{_fmt(Lp,1)} / {_fmt(Lr,1)}", "cm",
                "Lp = 1.76·ry·√(E/Fy)", f"Lp = 1.76·{_fmt(pr['ry'],2)}·√({_fmt(E_ACERO)}/{_fmt(Fy)}) = {_fmt(Lp,1)} · Lr = {_fmt(Lr,1)}",
                "AISC 360-16 ec.F2-5/F2-6", "Lb ≤ Lp: plastico · Lp<Lb≤Lr: LTB inelastico · Lb>Lr: LTB elastico.", "intermedio",
                latex=LATEX_BY_FORMULA["Lp = 1.76·ry·√(E/Fy)"]))
            zkey = ("Mn = Mp   (Lb ≤ Lp)" if zona == "plastico"
                    else "Mn = Cb·[Mp − (Mp−0.7Fy·Sx)(Lb−Lp)/(Lr−Lp)] ≤ Mp" if zona == "LTB inelastico"
                    else "Mn = Fcr·Sx ≤ Mp   (Lb > Lr)")
            P.append(_paso("§F Flexion", "M_n", f"Momento nominal — {zona}", round(Mn * KGCM_A_TM, 3), "t·m",
                zkey,
                f"Lb={_fmt(Lb,1)} vs Lp={_fmt(Lp,1)}, Lr={_fmt(Lr,1)} → zona {zona} → Mn = {_fmt(Mn*KGCM_A_TM,3)} t·m",
                "AISC 360-16 §F2", f"Momento nominal en la zona de pandeo lateral-torsional ({zona}).", "intermedio",
                latex=LATEX_BY_FORMULA[zkey]))
            P.append(_paso("§F Flexion", "φM_nx", "Resistencia a flexion (eje fuerte)", e["phi_rn"], "t·m",
                "φMn = 0.90·Mn", f"0.90·{_fmt(Mn*KGCM_A_TM,3)} = {_fmt(e['phi_rn'])} t·m",
                "AISC 360-16 §F1", "Resistencia de diseño a flexion respecto al eje fuerte.", "resultado",
                latex=LATEX_BY_FORMULA["φMn = 0.90·Mn"]))
        else:
            Mn_h, zona_h = mn_flexion_hss(Fy, pr["Zx"], pr["Sx"], pr.get("lam_ala", 0.0))
            Mp_h = Fy * pr["Zx"]
            P.append(_paso("§F Flexion", "M_p", "Momento plastico (F7-1)", round(Mp_h * KGCM_A_TM, 3), "t·m",
                "Mp = Fy·Zx", f"{_fmt(Fy)}·{_fmt(pr['Zx'],1)} = {_fmt(Mp_h*KGCM_A_TM,3)} t·m",
                "AISC 360-16 ec.F7-1", "HSS compacto: Mn = Mp (sin pandeo lateral-torsional).", "intermedio",
                latex=LATEX_BY_FORMULA["Mp = Fy·Zx"]))
            P.append(_paso("§F Flexion", "λ_pared", f"Pandeo local de pared — {zona_h}", round(pr.get('lam_ala', 0), 1), "",
                "b/t  vs  λp = 1.12√(E/Fy)",
                f"b/t = {_fmt(pr.get('lam_ala',0),1)} · λp = {_fmt(1.12*math.sqrt(E_ACERO/Fy),1)} → {zona_h}",
                "AISC 360-16 §F7.2", "Pared compacta → Mp; no-compacta → reduce (F7-2); esbelta → Se (F7-3).", "intermedio"))
            P.append(_paso("§F Flexion", "φM_nx", "Resistencia a flexion (HSS)", e["phi_rn"], "t·m",
                "φMn = 0.90·Mn", f"0.90·{_fmt(Mn_h*KGCM_A_TM,3)} = {_fmt(e['phi_rn'])} t·m",
                "AISC 360-16 §F7", "HSS cuadrado: sin pandeo lateral-torsional (eje fuerte = eje débil, Z_x=Z_y).", "resultado",
                latex=LATEX_BY_FORMULA["φMn = 0.90·Mn"]))
    if "flexion_y" in est and not es_hss:
        Mny = mny_eje_debil(Fy, pr["Zy"], pr["Sy"])
        e = est["flexion_y"]
        P.append(_paso("§F Flexion", "φM_ny", "Resistencia a flexion (eje debil)", e["phi_rn"], "t·m",
            "Mny = min(Fy·Zy, 1.6·Fy·Sy)",
            f"0.90·min({_fmt(Fy)}·{_fmt(pr['Zy'],1)}, 1.6·{_fmt(Fy)}·{_fmt(pr['Sy'],1)}) = {_fmt(e['phi_rn'])} t·m",
            "AISC 360-16 §F6", "Resistencia a flexion eje debil (sin pandeo lateral-torsional).", "resultado",
            latex=LATEX_BY_FORMULA["Mny = min(Fy·Zy, 1.6·Fy·Sy)"]))

    # ── §G CORTANTE (I-shape §G2 · HSS §G4) ───────────────────────────────────
    if "cortante" in est:
        e = est["cortante"]
        if not es_hss:
            phiVn, Aw, Cv1, phi_v, compacta = vn_cortante(Fy, pr["d"], pr["tw"], pr["hw"])
            P.append(_paso("§G Cortante", "φV_n", "Resistencia a cortante (G2-1)", e["phi_rn"], "t",
                "φVn = φ·0.6·Fy·Aw·Cv1",
                f"{_fmt(phi_v)}·0.6·{_fmt(Fy)}·{_fmt(Aw,2)}·{_fmt(Cv1)} = {_fmt(e['phi_rn'])} t  (Aw=d·tw, {'φ=1.0 alma compacta' if compacta else 'φ=0.90'})",
                "AISC 360-16 §G2", "Resistencia de diseño a cortante por fluencia del alma.", "resultado",
                latex=LATEX_BY_FORMULA["φVn = φ·0.6·Fy·Aw·Cv1"]))
        else:
            phiVn, Aw, Cv2, compacta = vn_cortante_hss(Fy, pr["tw"], pr["hw"])
            P.append(_paso("§G Cortante", "φV_n", "Resistencia a cortante (G4)", e["phi_rn"], "t",
                "φVn = φ·0.6·Fy·Aw·Cv1",
                f"0.90·0.6·{_fmt(Fy)}·{_fmt(Aw,2)}·{_fmt(Cv2)} = {_fmt(e['phi_rn'])} t  (Aw=2·h·t, las 2 almas)",
                "AISC 360-16 §G4", "HSS: cortante por las 2 almas; Cv2 segun esbeltez de pared.", "resultado",
                latex=LATEX_BY_FORMULA["φVn = φ·0.6·Fy·Aw·Cv1"]))

    # ── §H INTERACCION ────────────────────────────────────────────────────────
    if "interaccion" in est:
        e = est["interaccion"]
        ec = e.get("ec", "H1-1a")
        Pc = est["compresion"]["phi_rn"]
        Mcx = est.get("flexion_x", {}).get("phi_rn", 0)
        fkey = ("Pr/Pc + (8/9)(Mrx/Mcx + Mry/Mcy) ≤ 1.0   (Pr/Pc ≥ 0.2)" if ec == "H1-1a"
                else "Pr/(2Pc) + (Mrx/Mcx + Mry/Mcy) ≤ 1.0   (Pr/Pc < 0.2)")
        P.append(_paso("§H Interaccion", "IR", f"Razon de interaccion ({ec})", e["dc"], "",
            fkey,
            f"P_r/P_c = {_fmt(abs(Pu))}/{_fmt(Pc)} ; M_rx/M_cx = {_fmt(Mux)}/{_fmt(Mcx)} → IR = {_fmt(e['dc'])}",
            f"AISC 360-16 ec.{ec}", "Interaccion flexo-axial; ≤ 1.0 para que cumpla.", "resultado",
            latex=LATEX_BY_FORMULA[fkey]))

    # ── VERIFICACION ──────────────────────────────────────────────────────────
    gob = res["estado_gobernante"]
    dcg = res["dc_gobernante"]
    P.append(_paso("Verificacion", "DC", "Relacion demanda/capacidad gobernante", dcg, "",
        "DC = demanda / φRn",
        (f"{_EST_LBL.get(gob, gob)}: DC = {_fmt(dcg)}" if gob else "sin demanda aplicada"),
        "AISC §B3.1", "El estado limite con mayor DC gobierna el miembro.", "intermedio",
        latex=LATEX_BY_FORMULA["DC = demanda / φRn"]))
    P.append(_paso("Verificacion", "✓ LRFD", "Demanda ≤ φRn", bool(res["cumple"]), "",
        "demanda ≤ resistencia de diseño",
        (f"DC_gob = {_fmt(dcg)} {'≤' if res['cumple'] else '>'} 1.0 → " + ("OK" if res["cumple"] else "NO CUMPLE")
         if dcg is not None else "sin demanda aplicada → DC=0 (capacidades del perfil calculadas)"),
        "AISC §B3.1", "El miembro resiste la demanda ultima por todos los estados limite.", "check",
        latex=r"DC \le 1.0"))

    # Post-proceso latex
    for p in P:
        if p["tipo"] != "input" and p["latex"] is None:
            p["latex"] = LATEX_BY_FORMULA.get(p["formula"])

    constantes = [
        {"simbolo": "E",     "latex": r"E = 2.04\times10^6\ \text{kgf/cm}^2", "valor": E_ACERO, "unidad": "kgf/cm²", "desc": "Modulo de elasticidad del acero (29 000 ksi)."},
        {"simbolo": "φ_t",   "latex": r"\phi_t = 0.90/0.75", "valor": PHI_T_FLU, "unidad": "", "desc": "Factor LRFD traccion: 0.90 fluencia / 0.75 rotura (§D2)."},
        {"simbolo": "φ_c",   "latex": r"\phi_c = 0.90", "valor": PHI_C, "unidad": "", "desc": "Factor LRFD compresion (§E1)."},
        {"simbolo": "φ_b",   "latex": r"\phi_b = 0.90", "valor": PHI_B, "unidad": "", "desc": "Factor LRFD flexion (§F1)."},
        {"simbolo": "φ_v",   "latex": r"\phi_v = 1.00", "valor": PHI_V, "unidad": "", "desc": "Factor LRFD cortante, alma laminada compacta (§G1)."},
    ]
    avisos = res.get("avisos", [])
    meta = {
        "perfil": pn,
        "material": f"{mat['desc']} · F_y {_fmt(Fy)} / F_u {_fmt(Fu)} kgf/cm²",
        "seccion": pn,
        "es_hss": es_hss,
        "estado_gobernante": _EST_LBL.get(gob, gob) if gob else None,
        "dc_gobernante": dcg,
        "cumple": bool(res["cumple"]),
        "avisos": avisos,
        "resumen": (f"{pn} · {_EST_LBL.get(gob, gob) if gob else '—'} gobierna · DC={_fmt(dcg)}"
                    if dcg is not None else f"{pn} · sin demanda aplicada"),
    }
    return {"meta": meta, "pasos": P, "resultado": res, "constantes": constantes}
