"""Genera RevitKeynotes_CATALOG_v1.3_<Fecha>.txt desde fichas_v1.3.json (catálogo completo).

A diferencia de generate_keynotes.py (que lee partidas de UNA obra), este script
genera el TXT desde los 375 CSI del catálogo v1.3. Sirve para cargar en Revit
todos los keynotes disponibles, incluyendo JSON-only (no promovidos a partidas).

Formato Revit (idéntico a generate_keynotes.py):
  Sección 1: XX 00 00 TAB <División> TAB (vacío)
  Sección 2: <CSI> TAB <descripción> TAB <XX 00 00 padre>

Encoding: UTF-8 SIN BOM, CRLF.

Uso:
  python -m backend.scripts_runner.generate_keynotes_catalog
  python -m backend.scripts_runner.generate_keynotes_catalog --version v1.2
"""
import json, os, re, sys, datetime

from backend.db import SessionLocal
from backend.models import Capitulo
from backend.config import CONFIG

_THIS    = os.path.dirname(os.path.abspath(__file__))
_REPO    = os.path.abspath(os.path.join(_THIS, "..", ".."))
_FICHAS_BASE = os.path.join(_REPO, "development", "Template2_Updated")
OUT_DIR  = CONFIG.KEYNOTES_DIR

_SMART_CHAR_MAP = {
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-",
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "…": "...", " ": " ", "•": "-",
    "≤": "<=", "≥": ">=", "×": "x", "÷": "/", "≈": "~",
}


def _clean(text: str) -> str:
    if not text:
        return ""
    t = str(text).strip()
    t = re.sub(r"_x000D_\s*", "", t)
    t = re.sub(r"[\r\n]+", " ", t)
    t = re.sub(r"\s+", " ", t)
    for bad, good in _SMART_CHAR_MAP.items():
        t = t.replace(bad, good)
    return t.strip()


def _csi_division(csi: str) -> str:
    """Extrae código de división (primeros 2 dígitos) → 'XX 00 00'."""
    m = re.match(r"(\d{2})", (csi or "").strip())
    if m:
        return f"{m.group(1)} 00 00"
    return "00 00 00"


def _load_fichas(version="v1.3"):
    fichas_dir = os.path.join(_FICHAS_BASE, version, "fichas")
    for name in (f"fichas_{version}.live.json", f"fichas_{version}.json"):
        path = os.path.join(fichas_dir, name)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
    raise FileNotFoundError(f"No fichas JSON found for {version} in {fichas_dir}")


def _load_division_names() -> dict:
    """Carga nombres de divisiones desde DB (todos los capitulos de todas las obras)."""
    div_names = {}
    db = SessionLocal()
    try:
        caps = db.query(Capitulo).all()
        for c in caps:
            clave = (c.clave or "").strip()
            nombre = (c.nombre or "").strip()
            if clave and nombre:
                div_key = f"{clave} 00 00" if not clave.endswith("00 00") else clave
                if div_key not in div_names:
                    div_names[div_key] = nombre
    finally:
        db.close()
    return div_names


_DEFAULT_DIV_NAMES = {
    "00 00 00": "Preliminares y Contratos",
    "01 00 00": "Requerimientos Generales",
    "02 00 00": "Condiciones Existentes",
    "03 00 00": "Concreto",
    "04 00 00": "Mampostería",
    "05 00 00": "Metales",
    "06 00 00": "Madera y Carpintería",
    "07 00 00": "Protección Térmica e Impermeabilización",
    "08 00 00": "Puertas y Ventanas",
    "09 00 00": "Acabados",
    "10 00 00": "Especialidades",
    "11 00 00": "Equipos",
    "22 00 00": "Plomería",
    "23 00 00": "HVAC",
    "26 00 00": "Electricidad",
    "31 00 00": "Movimiento de Tierra",
    "32 00 00": "Mejoras Exteriores",
    "33 00 00": "Servicios Públicos",
}


def generate(version="v1.3") -> dict:
    fichas = _load_fichas(version)

    div_names = {**_DEFAULT_DIV_NAMES, **_load_division_names()}

    # Ordenar fichas por CSI natural
    def _sort_key(f):
        parts = []
        for tok in re.findall(r"\d+|\D+", f.get("csi", "") or ""):
            parts.append((0, int(tok)) if tok.isdigit() else (1, tok.lower()))
        return parts or [(1, "zz")]

    fichas_sorted = sorted(fichas, key=_sort_key)

    # Recopilar divisiones en orden de aparición
    seen_divs = []
    seen_div_set = set()
    for fi in fichas_sorted:
        div = _csi_division(fi.get("csi", ""))
        if div not in seen_div_set:
            seen_div_set.add(div)
            seen_divs.append(div)

    lines = []
    # Sección 1: cabeceras de división
    for div in seen_divs:
        name = div_names.get(div, div)
        lines.append(f"{div}\t{_clean(name)}\t")

    # Sección 2: partidas del catálogo
    for fi in fichas_sorted:
        csi = _clean(fi.get("csi", ""))
        desc = _clean(fi.get("descripcion", ""))
        if not csi or not desc:
            continue
        parent = _csi_division(csi)
        lines.append(f"{csi}\t{desc}\t{parent}")

    os.makedirs(OUT_DIR, exist_ok=True)
    date_tag = datetime.datetime.now().strftime("%Y-%m-%d")
    filename = f"RevitKeynotes_CATALOG_{version}_{date_tag}.txt"
    out_path = os.path.join(OUT_DIR, filename)

    content = "\r\n".join(lines) + "\r\n"

    bad_chars = []
    for i, line in enumerate(lines, 1):
        try:
            line.encode("utf-8")
        except Exception as e:
            bad_chars.append(f"line {i}: {e}")

    with open(out_path, "w", encoding="utf-8", newline="") as f:
        f.write(content)

    # Verificar sin BOM
    raw = open(out_path, "rb").read(3)
    has_bom = raw[:3] == b"\xef\xbb\xbf"

    return {
        "ok": not has_bom and not bad_chars,
        "path": out_path,
        "fichas": len(fichas_sorted),
        "divisiones": len(seen_divs),
        "has_bom": has_bom,
        "bad_chars": bad_chars,
    }


if __name__ == "__main__":
    version = "v1.3"
    for arg in sys.argv[1:]:
        if arg.startswith("--version"):
            version = arg.split("=")[-1].strip() if "=" in arg else sys.argv[sys.argv.index(arg) + 1]

    r = generate(version)
    if r["ok"]:
        print(f"(keynote catalog creado) {os.path.basename(r['path'])} — {r['divisiones']} divisiones, {r['fichas']} fichas — sin BOM, sin chars corruptos")
    else:
        print(f"ERROR: has_bom={r['has_bom']}, bad_chars={r['bad_chars']}")
    print(f"  → {r['path']}")
