# -*- coding: utf-8 -*-
"""
perfiles_acero.py — Tabla de propiedades de perfiles de acero (W / HSS)
=======================================================================
Modulo ADITIVO y PURO (sin ORM). Fuente unica de propiedades de seccion
para el motor de conexiones (calculo_conexion_acero.py), el motor de
miembros LRFD (calculo_miembro_acero.py) y, a futuro, para absorber
PERFILES_W de calculo_soldadura.py (hoy solo tiene d, bf).

Propiedades por perfil, en METRICO (cm / cm²):
  d   : peralte total                  [cm]
  bf  : ancho de ala (HSS: lado)       [cm]
  tf  : espesor de ala (HSS: pared)    [cm]
  tw  : espesor de alma (HSS: pared)   [cm]
  Ag  : area bruta de la seccion       [cm²]

Valores tomados de la AISC Shapes Database v15 (unidades SI: d/bf/tf/tw en mm,
A en mm²) convertidos a cm. HSS cuadrado: bf = lado, tf = tw = espesor de diseño
(0.93·t_nominal), Ag de la designacion.

Constantes metricas de material/soldadura (ksi -> kgf/cm²  ×70.307):
  FEXX_E70  electrodo E70XX
  Tabla J3.2 (pernos)  A325 / A490 / A307   Fnt, Fnv (N=roscas en corte, X=excluidas)
  Aceros A992 / A36    Fy, Fu
"""

# ─────────────────────────────────────────────────────────────────────────────
# CONVERSION
# ─────────────────────────────────────────────────────────────────────────────
KSI_A_KGCM2 = 70.307   # 1 ksi = 70.307 kgf/cm²


# ─────────────────────────────────────────────────────────────────────────────
# TABLA DE PERFILES W (metrico AISC v15, convertido a cm / cm²)
#   Clave = designacion W metrica normalizada (ver calculo_conexion_acero._norm)
# ─────────────────────────────────────────────────────────────────────────────
PERFILES_ACERO = {
    # ── Vigas VA-x (perfiles W ligeros/medianos) ──────────────────────────────
    "W150X18":  {"d": 15.30, "bf": 10.20, "tf": 0.710, "tw": 0.580, "Ag": 23.40},
    "W180X22":  {"d": 17.70, "bf": 10.20, "tf": 0.760, "tw": 0.590, "Ag": 28.50},
    "W200X27":  {"d": 20.70, "bf": 13.30, "tf": 0.840, "tw": 0.580, "Ag": 34.80},
    "W250X33":  {"d": 25.80, "bf": 14.60, "tf": 0.940, "tw": 0.610, "Ag": 42.70},
    # ── Sincronizados con TABLA_W (CISC/AISC, mm÷10) — 2026-05-31 ──────────────
    "W150X24":  {"d": 16.00, "bf": 10.20, "tf": 1.030, "tw": 0.660, "Ag": 30.60},
    "W200X36":  {"d": 20.10, "bf": 16.50, "tf": 1.020, "tw": 0.620, "Ag": 45.70},
    "W200X71":  {"d": 21.00, "bf": 20.60, "tf": 1.740, "tw": 1.020, "Ag": 91.00},
    "W250X49":  {"d": 24.70, "bf": 20.20, "tf": 1.070, "tw": 0.740, "Ag": 62.60},
    "W310X73":  {"d": 31.00, "bf": 25.40, "tf": 1.460, "tw": 0.890, "Ag": 92.90},
    # ── Columnas W ────────────────────────────────────────────────────────────
    "W200X46":  {"d": 20.30, "bf": 20.30, "tf": 1.100, "tw": 0.720, "Ag": 58.90},
    "W250X73":  {"d": 25.30, "bf": 25.40, "tf": 1.420, "tw": 0.860, "Ag": 93.10},
    # ── Perfiles imperiales (clases de peso para resolver fichas CV/VV) ────────
    #    d/bf/tf/tw/Ag sincronizados con TABLA_W (los presentes en ella).
    "W6X16":    {"d": 15.95, "bf": 10.24, "tf": 1.030, "tw": 0.660, "Ag": 30.58},  # AISC v15: tf=0.405in=1.03cm (antes 0.660=tw, error ~36%); usado por placa base/conexion P5
    "W8X24":    {"d": 20.10, "bf": 16.50, "tf": 1.020, "tw": 0.620, "Ag": 45.50},  # bf=16.50 (AISC); TABLA_W W8X24 bf=133mm parece erroneo (ver nota)
    "W8X48":    {"d": 21.60, "bf": 20.60, "tf": 1.740, "tw": 1.020, "Ag": 90.97},
    "W10X33":   {"d": 24.70, "bf": 20.20, "tf": 1.100, "tw": 0.740, "Ag": 62.65},
    "W12X53":   {"d": 30.70, "bf": 25.40, "tf": 1.460, "tw": 0.880, "Ag": 100.65},
    # ── HSS cuadrado (columnas C-1..C-3). bf=lado, tf=tw=espesor de diseño ─────
    #   AUDIT 2026-06-02 (v2): tf/tw = espesor de DISEÑO A500 (0.93·t_nom). Ag
    #   reconciliado a area de DISEÑO A500 (AISC v15 Tabla 1-12) para que sea
    #   consistente con tf/tw y con r=sqrt(I/Ag): A[in²]×6.4516 = A[cm²].
    #     HSS6x6x3/16 A=3.98in²=25.68 · HSS8x8x1/4 A=6.76in²=43.61 · HSS10x10x1/2 A=16.4in²=105.81
    #   (Antes Ag venia en area NOMINAL/A1085 = 7.10/17.2in² -> ~5% alto.)
    "HSS6X6X3/16":  {"d": 15.24, "bf": 15.24, "tf": 0.444, "tw": 0.444, "Ag": 25.68},
    "HSS8X8X1/4":   {"d": 20.32, "bf": 20.32, "tf": 0.591, "tw": 0.591, "Ag": 43.61},
    "HSS10X10X1/2": {"d": 25.40, "bf": 25.40, "tf": 1.176, "tw": 1.176, "Ag": 105.81},
}
# ─────────────────────────────────────────────────────────────────────────────
# AUDIT tf/tw vs AISC v15 / CISC (2026-06-02) — cierra 🔴 bus 2026-05-31 (l.95)
#   Tras el sync 2026-05-31, las geometrias W coinciden con TABLA_W (AISC/CISC
#   exacto). Verificado perfil por perfil:
#     · W6X16: tf estaba en 0.660 (= tw, error ~36%) -> CORREGIDO a 1.03 (0.405in).
#     · W150X24/W200X36/W200X71/W250X49/W310X73/W200X46/W250X73: OK (= TABLA_W).
#     · W8X24/W8X48/W10X33/W12X53: OK (= TABLA_W, AISC 16a -> SI).
#     · VA-x (W150X18/W180X22/W200X27/W250X33, NO en TABLA_W): d/bf/tw OK; tf de
#       W180X22 (0.76 vs 0.80) y W250X33 (0.94 vs 0.91) ~3-5% off (CISC), no §J
#       critico — se dejan hasta confirmar contra CISC Handbook con doc fuente.
#   El motor de MIEMBROS usa TABLA_W (no esta tabla); el de CONEXIONES §J usa
#   tf/tw de aqui -> el unico defecto §J real (W6X16) queda corregido.
# ─────────────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTES METRICAS — SOLDADURA / PERNOS / ACERO  (kgf/cm²)
# ─────────────────────────────────────────────────────────────────────────────
FEXX_E70 = 4920          # E70XX  (70 ksi ×70.307 ≈ 4921, el vault usa 4920)

# Tabla J3.2 AISC 360-16 — esfuerzos nominales de pernos (kgf/cm²)
#   Fnt = traccion · Fnv_N = corte con roscas INCLUIDAS en plano de corte
#   Fnv_X = corte con roscas EXCLUIDAS · A307: un solo Fnv
PERNOS = {
    "A325": {"Fnt": 6328, "Fnv_N": 3797, "Fnv_X": 4781, "desc": "A325 (alta resistencia)"},
    "A490": {"Fnt": 7945, "Fnv_N": 4781, "Fnv_X": 5906, "desc": "A490 (alta resistencia)"},
    "A307": {"Fnt": 3164, "Fnv_N": 1898, "Fnv_X": 1898, "desc": "A307 (comun)"},
}

# Aceros estructurales (kgf/cm²)  — Fy fluencia · Fu rotura
ACEROS = {
    "A992": {"Fy": 3515, "Fu": 4570, "desc": "A992 (perfiles W)"},
    "A36":  {"Fy": 2531, "Fu": 4078, "desc": "A36 (placas/angulos)"},
    "A500": {"Fy": 3235, "Fu": 4360, "desc": "A500 Gr.C (HSS)"},
}

# Modulo de elasticidad y de corte del acero (AISC 360-16 §E)
import math
import re as _re
E_ACERO = 2038900   # kgf/cm²  (29 000 ksi × 70.307) — modulo de elasticidad
G_ACERO = 784600    # kgf/cm²  (11 200 ksi)          — modulo de corte


def _es_hss(perfil: str) -> bool:
    return str(perfil).upper().startswith("HSS")


def _norm_w(perfil: str) -> str:
    """Normaliza designacion W (mayusc, sin espacios, ×->X, sin (imperial))."""
    if not perfil:
        return ""
    s = str(perfil).strip().upper()
    s = _re.sub(r"\([^)]*\)", "", s)
    s = s.replace('"', "").replace("”", "").replace("''", "").replace("×", "X")
    return _re.sub(r"\s+", "", s)


# ─────────────────────────────────────────────────────────────────────────────
# TABLA_W — propiedades de seccion para diseño LRFD AISC 360-16 (SI: mm/mm²/mm³)
#   Fuente: CISC Handbook (W150/W200/W250/W310) + AISC 16a -> SI (W8/W10/W12).
#   Doc: 03 Automation Projects\estimbot\reference\plan_revision_aci_lrfd_2026_05_31.md
#   props_seccion() convierte a cm para el motor. NO derivar de geometria: la
#   geometria de PERFILES_ACERO arriba es aproximada (tf/tw imprecisos) y daria
#   Zx/ry ~25-34 % bajos. Estos valores son AISC/CISC exactos.
# ─────────────────────────────────────────────────────────────────────────────
TABLA_W = {
    # ── VIGAS (d/bf > 1.2) ────────────────────────────────────────────────────
    "W150X24": {"Ag": 3060,  "d": 160, "bf": 102, "tf": 10.3, "tw": 6.6,  "h_tw": 21.1,
                "Ix": 13.4e6, "Sx": 167e3,  "Zx": 191e3,  "Iy": 1.83e6, "Sy": 35.9e3, "Zy": 55.8e3,
                "ry": 24.5, "rts": 28.6, "J": 55.7e3, "Cw": 10.3e9, "ho": 149.7, "uso": "VIGA"},
    "W200X36": {"Ag": 4570,  "d": 201, "bf": 165, "tf": 10.2, "tw": 6.2,  "h_tw": 29.1,
                "Ix": 34.4e6, "Sx": 343e3,  "Zx": 380e3,  "Iy": 7.64e6, "Sy": 92.6e3, "Zy": 141e3,
                "ry": 40.9, "rts": 46.1, "J": 118e3,  "Cw": 69.5e9, "ho": 190.8, "uso": "VIGA"},
    "W250X49": {"Ag": 6260,  "d": 247, "bf": 202, "tf": 10.7, "tw": 7.4,  "h_tw": 30.1,
                "Ix": 70.8e6, "Sx": 573e3,  "Zx": 637e3,  "Iy": 15.2e6, "Sy": 150e3,  "Zy": 229e3,
                "ry": 49.3, "rts": 55.7, "J": 256e3,  "Cw": 212e9,  "ho": 236.3, "uso": "VIGA"},
    # ── COLUMNAS (d/bf ≤ 1.1) ─────────────────────────────────────────────────
    "W150X37": {"Ag": 4740,  "d": 162, "bf": 154, "tf": 11.6, "tw": 8.1,  "h_tw": 17.2,
                "Ix": 22.2e6, "Sx": 274e3,  "Zx": 308e3,  "Iy": 7.07e6, "Sy": 91.8e3, "Zy": 140e3,
                "ry": 38.6, "rts": 44.0, "J": 131e3,  "Cw": 40e9, "ho": 150.4, "uso": "COLUMNA"},
    "W200X46": {"Ag": 5890,  "d": 203, "bf": 203, "tf": 11.0, "tw": 7.2,  "h_tw": 25.4,
                "Ix": 45.8e6, "Sx": 451e3,  "Zx": 508e3,  "Iy": 15.3e6, "Sy": 151e3,  "Zy": 229e3,
                "ry": 51.1, "rts": 57.4, "J": 220e3,  "Cw": 141e9, "ho": 192.0, "uso": "COLUMNA"},
    "W200X71": {"Ag": 9100,  "d": 210, "bf": 206, "tf": 17.4, "tw": 10.2, "h_tw": 17.0,
                "Ix": 76.6e6, "Sx": 730e3,  "Zx": 828e3,  "Iy": 25.4e6, "Sy": 247e3,  "Zy": 378e3,
                "ry": 52.8, "rts": 57.9, "J": 818e3,  "Cw": 236e9,  "ho": 192.6, "uso": "COLUMNA"},
    "W250X73": {"Ag": 9310,  "d": 253, "bf": 254, "tf": 14.2, "tw": 8.6,  "h_tw": 24.9,
                "Ix": 113e6,  "Sx": 895e3,  "Zx": 1010e3, "Iy": 38.8e6, "Sy": 306e3,  "Zy": 466e3,
                "ry": 64.5, "rts": 72.1, "J": 567e3,  "Cw": 553e9,  "ho": 238.8, "uso": "COLUMNA"},
    "W310X73": {"Ag": 9290,  "d": 310, "bf": 254, "tf": 14.6, "tw": 8.9,  "h_tw": 30.3,
                "Ix": 165e6,  "Sx": 1060e3, "Zx": 1200e3, "Iy": 38.8e6, "Sy": 306e3,  "Zy": 466e3,
                "ry": 64.6, "rts": 73.5, "J": 571e3,  "Cw": 846e9,  "ho": 295.4, "uso": "COLUMNA"},
    # ── PERFILES US (AISC 16a -> SI) ──────────────────────────────────────────
    "W8X24":   {"Ag": 4550,  "d": 201, "bf": 165, "tf": 10.2, "tw": 6.2,  "h_tw": 28.7,
                "Ix": 34.4e6, "Sx": 342e3,  "Zx": 380e3,  "Iy": 7.64e6, "Sy": 92.6e3, "Zy": 141e3,
                "ry": 40.9, "rts": 46.1, "J": 144e3,  "Cw": 69.5e9, "ho": 190.8, "uso": "VIGA"},
    "W8X48":   {"Ag": 9097,  "d": 216, "bf": 206, "tf": 17.4, "tw": 10.2, "h_tw": 17.2,
                "Ix": 76.6e6, "Sx": 709e3,  "Zx": 803e3,  "Iy": 25.4e6, "Sy": 246e3,  "Zy": 375e3,
                "ry": 52.8, "rts": 59.6, "J": 816e3,  "Cw": 250e9,  "ho": 198.6, "uso": "COLUMNA"},
    "W10X33":  {"Ag": 6265,  "d": 247, "bf": 202, "tf": 11.0, "tw": 7.4,  "h_tw": 27.1,
                "Ix": 71.2e6, "Sx": 574e3,  "Zx": 636e3,  "Iy": 15.2e6, "Sy": 150e3,  "Zy": 229e3,
                "ry": 49.3, "rts": 55.9, "J": 243e3,  "Cw": 212e9,  "ho": 236.0, "uso": "VIGA"},
    "W12X53":  {"Ag": 10065, "d": 307, "bf": 254, "tf": 14.6, "tw": 8.8,  "h_tw": 28.1,
                "Ix": 177e6,  "Sx": 1157e3, "Zx": 1277e3, "Iy": 39.9e6, "Sy": 314e3,  "Zy": 477e3,
                "ry": 63.0, "rts": 70.9, "J": 658e3,  "Cw": 853e9,  "ho": 292.4, "uso": "COLUMNA"},
}


def props_seccion(perfil_dict: dict, perfil_nombre: str = "") -> dict:
    """Propiedades de seccion para el motor LRFD, en cm/cm²/cm³/cm⁴/cm⁶.

    PRIMERO busca en TABLA_W (valores AISC/CISC exactos) y convierte SI->cm.
    Si el perfil no esta en TABLA_W y NO es HSS, deriva de la geometria
    (3 rectangulos, ~3 % conservador, marca fuente="derivada").
    HSS: las formulas de perfil I no aplican -> {"hss": True} sin props.
    Devuelve tambien d/bf/tf/tw/Ag (fuente unica para el motor)."""
    nom = _norm_w(perfil_nombre)
    w = TABLA_W.get(nom)
    if w:
        d = w["d"] / 10; bf = w["bf"] / 10; tf = w["tf"] / 10; tw = w["tw"] / 10
        Ag = w["Ag"] / 100
        Ix = w["Ix"] / 1e4; Iy = w["Iy"] / 1e4
        Sx = w["Sx"] / 1e3; Sy = w["Sy"] / 1e3
        Zx = w["Zx"] / 1e3; Zy = w["Zy"] / 1e3
        ry = w["ry"] / 10; rts = w["rts"] / 10
        J = w["J"] / 1e4; Cw = w["Cw"] / 1e6; ho = w["ho"] / 10
        rx = math.sqrt(Ix / Ag) if Ag > 0 else 0.0
        return {
            "hss": False, "fuente": "tabla", "uso": w.get("uso", ""),
            "d": d, "bf": bf, "tf": tf, "tw": tw, "Ag": Ag, "hw": w["h_tw"] * tw,
            "Ix": Ix, "Iy": Iy, "Sx": Sx, "Sy": Sy, "Zx": Zx, "Zy": Zy,
            "rx": rx, "ry": ry, "J": J, "ho": ho, "Cw": Cw, "rts": rts,
            "lam_ala": bf / (2 * tf), "lam_alma": w["h_tw"],
        }

    # ── Fallback: derivar de la geometria (perfil sin tabla, no HSS) ──────────
    d  = perfil_dict.get("d", 0.0);  bf = perfil_dict.get("bf", 0.0)
    tf = perfil_dict.get("tf", 0.0); tw = perfil_dict.get("tw", 0.0)
    Ag = perfil_dict.get("Ag", 0.0)
    if _es_hss(perfil_nombre):
        # HSS cuadrado cerrado: lado b = bf, pared de diseño t = tf (cm). Props exactas
        # (doblemente simétrico, Ix=Iy, sin LTB). lam = ancho plano/t (AISC ≈ b−3t).
        b = bf; t = tf
        if b > 0 and t > 0 and Ag > 0:
            bi = max(b - 2 * t, 0.0)
            I = (b ** 4 - bi ** 4) / 12.0
            S = 2 * I / b
            Z = (b ** 3 - bi ** 3) / 4.0
            r = math.sqrt(I / Ag)
            flat = max(b - 3 * t, 0.0)
            lam = flat / t if t > 0 else 0.0
            Am = (b - t) ** 2                       # área media encerrada (torsión cerrada)
            J = (4 * Am ** 2 * t / (4 * (b - t))) if (b - t) > 0 else 0.0
            return {
                "hss": True, "fuente": "hss", "uso": perfil_dict.get("uso", "COLUMNA"),
                "d": b, "bf": b, "tf": t, "tw": t, "Ag": Ag, "hw": flat,
                "Ix": I, "Iy": I, "Sx": S, "Sy": S, "Zx": Z, "Zy": Z,
                "rx": r, "ry": r, "J": J, "ho": b - t, "Cw": 0.0, "rts": r,
                "lam_ala": lam, "lam_alma": lam, "b_hss": b, "t_hss": t,
            }
        return {"hss": True}
    if min(d, bf, tf, tw) <= 0:
        return {"hss": False}
    hw = d - 2 * tf
    Ix = bf * d**3 / 12 - (bf - tw) * hw**3 / 12
    Iy = 2 * (tf * bf**3 / 12) + hw * tw**3 / 12
    Sx = 2 * Ix / d;  Sy = 2 * Iy / bf
    Zx = bf * tf * (d - tf) + tw * hw**2 / 4
    Zy = tf * bf**2 / 2 + hw * tw**2 / 4
    rx = math.sqrt(Ix / Ag) if Ag > 0 else 0.0
    ry = math.sqrt(Iy / Ag) if Ag > 0 else 0.0
    J  = (2 * bf * tf**3 + hw * tw**3) / 3
    ho = d - tf;  Cw = Iy * ho**2 / 4
    rts = math.sqrt(math.sqrt(Iy * Cw) / Sx) if Sx > 0 else 0.0
    return {
        "hss": False, "fuente": "derivada",
        "d": d, "bf": bf, "tf": tf, "tw": tw, "Ag": Ag, "hw": hw,
        "Ix": Ix, "Iy": Iy, "Sx": Sx, "Sy": Sy, "Zx": Zx, "Zy": Zy,
        "rx": rx, "ry": ry, "J": J, "ho": ho, "Cw": Cw, "rts": rts,
        "lam_ala": (bf / 2) / tf, "lam_alma": hw / tw,
    }
