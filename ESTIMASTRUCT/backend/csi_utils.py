"""
Shared CSI chapter inference — used by updater (Excel import) and partidas (nueva actividad).
"""
import re

_CHAPTER_BY_PREFIX = {
    "GRL":  "01",
    "DON":  "02", "PRM0": "02",
    "ARM":  "03", "ENC":  "03", "CM":   "03", "CON":  "03", "CONC": "03",
    "GR":   "03", "P":    "03", "R":    "03", "S":    "03", "V":    "03",
    "C":    "05", "CG":   "05", "CV":   "05", "SF":   "05",
    "VA":   "05", "VV":   "05", "RAI":  "05",
    "MD":   "06", "COA8": "06",
    "AT":   "07", "COA1": "07", "COA9": "07", "FB":   "07",
    "CW":   "08", "PM":   "08", "PP":   "08", "PT":   "08",
    "PV":   "08", "VP":   "08",
    "CEI":  "09", "CER":  "09", "FL":   "09", "PN":   "09", "WS":   "09",
    "SIG":  "10",
    "COC":  "11", "LVA":  "11",
    "CLO":  "12", "ESP":  "12", "FUR0": "12", "MOB":  "12",
    "INC":  "21",
    "BOM":  "22", "PB":   "22", "PB01": "22", "PB02": "22", "SN":   "22",
    "EXB":  "23", "GAS":  "23", "HV":   "23",
    "DMT":  "25", "ILU1": "25",
    "CEM":  "26", "EL":   "26", "ILU0": "26", "TOM0": "26", "UPS":  "26",
    "COM0": "27", "TEL":  "27",
    "SEG":  "28",
    "EXT":  "31",
}

_CHAPTER_BY_KEYWORD = [
    (r"bomba|pump",                                        "22"),
    (r"plomer|sanitari|tuberi|drenaje sanitari",           "22"),
    (r"hvac|climatiz|aire acondicion|ventilac",            "23"),
    (r"el[eé]ctric|iluminac|luminari",                    "26"),
    (r"incendio|rociador|fire",                            "21"),
    (r"comunicac|datos|telecom|red inform",                "27"),
    (r"seguridad|c[aá]mara|acceso|alarma",                "28"),
    (r"concreto|losa|columna|viga|cimentac",               "03"),
    (r"mamposte|bloque|ladrillo|repello|alba[nñ]il",      "04"),
    (r"acero estructural|perfil|joist|deck met",           "05"),
    (r"madera|carpinter",                                  "06"),
    (r"impermeabiliz|cubierta|techo lamin",                "07"),
    (r"puerta|ventana|vidrio|aluminio",                    "08"),
    (r"pintura|acabado|piso|baldosa|cer[aá]mica|cielo raso","09"),
    (r"excavac|relleno|compactac|movimiento de tierra",    "31"),
    (r"pavimento|acera|jardiner|cerca|muro sitio",         "32"),
    (r"agua potable|alcantarill|drenaje pluvial",          "33"),
]

_CSI_DIV_RE = re.compile(r"^\d{2}")


def infer_csi(codigo: str, descripcion: str) -> str:
    """
    Returns a CSI code like '09 00 00' inferred from type mark prefix or description keywords.
    Returns '' if no match found.
    """
    prefix = (codigo or "").split("-")[0].upper()
    if prefix in _CHAPTER_BY_PREFIX:
        return f"{_CHAPTER_BY_PREFIX[prefix]} 00 00"
    desc_lower = (descripcion or "").lower()
    for pattern, div in _CHAPTER_BY_KEYWORD:
        if re.search(pattern, desc_lower):
            return f"{div} 00 00"
    return ""


def is_valid_csi(clave: str) -> bool:
    """True if clave starts with two digits (valid CSI division prefix)."""
    return bool(_CSI_DIV_RE.match((clave or "").strip()))
