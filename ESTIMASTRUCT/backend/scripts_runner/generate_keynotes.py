"""Genera RevitKeynotes_<Obra>_<Fecha>.txt desde la obra activa (DB).

Formato (igual a PY_S1_xlsx_a_keynotes.py existente):
  Encoding   : **UTF-8 SIN BOM** (ver GOTCHA abajo — NO Latin-1/Windows-1252,
               a pesar de que ese era el fix "de libro" para Keynote tables)
  Separador  : TAB
  Fin de linea: CRLF
  Sección 1  : XX 00 00 \\t <nombre_capitulo> \\t (vacío)
  Sección 2  : <CSI> \\t <descripción> \\t XX 00 00

GOTCHA de encoding (2026-07-08, costó 2 iteraciones, no repetir):
  La corrupción de acentos en el KeynoteTable de Revit ("Mamposter•a" en vez
  de "Mampostería") NO es porque el archivo tenga BOM, y NO se arregla
  escribiendo Latin-1/Windows-1252 (el fix "estándar" que asume que Revit lee
  keynote.txt como ANSI clásico). La causa real: Windows 11 puede tener
  activo "Use Unicode UTF-8 for worldwide language support" (Beta), que
  redefine el codepage ANSI del sistema (`chcp`) a 65001 (UTF-8) en vez del
  1252 tradicional. Revit usa el codepage ANSI del sistema para leer el
  keynote.txt — en una máquina con ese beta activo, un archivo Latin-1
  (1 byte por acento, ej. í=0xED) se decodifica como si fuera UTF-8, produce
  bytes huérfanos sin secuencia válida, y Revit muestra el glifo de
  reemplazo ("•"/mojibake) para CADA acento. Verificar `chcp` / `[System.
  Text.Encoding]::Default.CodePage` en PowerShell antes de asumir cuál
  encoding usar — en esta máquina dio 65001, por eso el fix es UTF-8 sin BOM.
  El BOM SÍ sigue rompiendo la jerarquía de keys (confirmado con el archivo
  viejo `RevitKeynotes_xx_2026-05-29.txt`, que tenía BOM+UTF-8) — por eso
  UTF-8 SIN BOM, no "cualquier UTF-8".

Auto-verificación: después de escribir, `generate()` relee el archivo en modo
binario y valida (a) que NO tenga BOM y (b) que decodifique 100% limpio como
UTF-8 (round-trip) — si falla, devuelve `ok: False` con el motivo, en vez de
dejar un .txt corrupto silencioso como pasaba antes.

Uso (CLI):
  python generate_keynotes.py <obra_id>
"""
import os, re, sys, datetime

from backend.db import SessionLocal
from backend.models import Presupuesto, Capitulo, Partida
from backend.config import CONFIG

OUT_DIR = CONFIG.KEYNOTES_DIR

# Caracteres tipográficos que Word/Excel insertan por auto-corrección (comillas
# curvas, guiones en/em-dash, elipsis, espacio duro). Con UTF-8 ya no rompen el
# encoding, pero se normalizan igual — Revit/fuentes de diálogo pueden no tener
# glifo para varios de estos y mostrar su propio placeholder, mejor ASCII plano.
_SMART_CHAR_MAP = {
    "‐": "-",   # hyphen
    "‑": "-",   # non-breaking hyphen
    "‒": "-",   # figure dash
    "–": "-",   # en dash
    "—": "-",   # em dash
    "‘": "'",   # left single quote
    "’": "'",   # right single quote / apostrophe
    "“": '"',   # left double quote
    "”": '"',   # right double quote
    "…": "...",  # ellipsis
    " ": " ",   # non-breaking space
    "•": "-",   # bullet
    "≤": "<=",  # menor o igual
    "≥": ">=",  # mayor o igual
    "×": "x",   # multiplicacion (dimensiones)
    "÷": "/",   # division
    "≈": "~",   # aproximado
}


def _normalize_smart_chars(text: str) -> str:
    for bad, good in _SMART_CHAR_MAP.items():
        text = text.replace(bad, good)
    return text


def _clean(text: str) -> str:
    if text is None:
        return ""
    t = str(text).strip()
    t = re.sub(r"_x000D_\s*", "", t)
    t = re.sub(r"[\r\n]+", " ", t)
    t = re.sub(r"\s+", " ", t)
    t = _normalize_smart_chars(t)
    return t.strip()


def _csi_natural_key(s: str):
    parts = []
    for tok in re.findall(r"\d+|\D+", s or ""):
        parts.append((0, int(tok)) if tok.isdigit() else (1, tok.lower()))
    return parts


def generate(obra_id: str, output_dir: str = None) -> dict:
    db = SessionLocal()
    try:
        obra = db.query(Presupuesto).filter(Presupuesto.id == obra_id).first()
        if not obra:
            return {"ok": False, "error": f"Obra {obra_id} no encontrada"}

        capitulos = sorted(obra.capitulos, key=lambda c: (c.orden if c.orden is not None else 999, c.clave or ""))
        if not capitulos:
            return {"ok": False, "error": "La obra no tiene capítulos"}

        lines = []
        # Sección 1: cabecera de capítulos (clave + ' 00 00')
        for cap in capitulos:
            cap_code = (cap.clave or "").strip()
            div_code = f"{cap_code} 00 00"
            lines.append(f"{div_code}\t{_clean(cap.nombre)}\t")

        # Sección 2: partidas de cada capítulo
        for cap in capitulos:
            partidas = sorted(cap.partidas, key=lambda p: _csi_natural_key(p.clave_csi))
            cap_code = (cap.clave or "").strip()
            parent = f"{cap_code} 00 00"
            for pa in partidas:
                csi = _clean(pa.clave_csi)
                desc = _clean(pa.descripcion)
                if not csi or not desc:
                    continue
                lines.append(f"{csi}\t{desc}\t{parent}")

        target_dir = output_dir or OUT_DIR
        os.makedirs(target_dir, exist_ok=True)
        nombre_safe = re.sub(r"[^\w\-]+", "_", (obra.nombre or "obra")).strip("_") or "obra"
        date_tag = datetime.datetime.now().strftime("%Y-%m-%d")

        # Versioning: si el archivo ya existe hoy, incrementar contador
        base_filename = f"RevitKeynotes_{nombre_safe}_{date_tag}"
        filename = f"{base_filename}.txt"
        out_path = os.path.join(target_dir, filename)
        v = 2
        while os.path.isfile(out_path):
            filename = f"{base_filename}_v{v}.txt"
            out_path = os.path.join(target_dir, filename)
            v += 1

        content = "\r\n".join(lines) + "\r\n"

        # UTF-8 sin BOM (ver GOTCHA en el docstring del módulo — NO latin-1).
        # UTF-8 puede representar cualquier caracter Unicode, así que un encode
        # estricto casi nunca falla; el chequeo queda igual por si algún día
        # aparece un surrogate/caracter inválido en la descripción de una ficha.
        bad_chars = []
        for line in lines:
            try:
                line.encode("utf-8")
            except UnicodeEncodeError as ex:
                bad_chars.append({
                    "line": line[:80],
                    "char": repr(content[ex.start:ex.end]),
                    "position": ex.start,
                })

        encoded = content.encode("utf-8", errors="replace")
        with open(out_path, "wb") as f:
            f.write(encoded)

        # Auto-verificación: releer en binario y confirmar (a) sin BOM UTF-8
        # (rompe la jerarquía de keys en Revit) y (b) round-trip limpio. Esto
        # atrapa tanto el caso viejo (BOM+UTF-8, 2026-05-29) como el caso nuevo
        # (Latin-1 en una máquina con codepage ANSI = UTF-8, 2026-07-08).
        with open(out_path, "rb") as f:
            raw = f.read()
        has_bom = raw[:3] == b"\xef\xbb\xbf"
        roundtrip_ok = raw == encoded
        verification_ok = (not has_bom) and roundtrip_ok and not bad_chars

        result = {
            "ok": verification_ok,
            "path": out_path,
            "filename": filename,
            "lines": len(lines),
            "divisiones": len(capitulos),
            "partidas": len(lines) - len(capitulos),
            "size_bytes": len(encoded),
            "verification": {
                "has_bom": has_bom,
                "roundtrip_ok": roundtrip_ok,
                "bad_chars": bad_chars[:20],
                "bad_chars_count": len(bad_chars),
            },
        }
        if verification_ok:
            result["message"] = (
                f"(keynote creado) {filename} — {len(capitulos)} divisiones, "
                f"{len(lines) - len(capitulos)} partidas — verificado sin BOM, "
                f"sin caracteres corruptos."
            )
        else:
            reasons = []
            if has_bom:
                reasons.append("archivo tiene BOM UTF-8 (Revit lo malinterpreta)")
            if not roundtrip_ok:
                reasons.append("round-trip de encoding falló")
            if bad_chars:
                reasons.append(f"{len(bad_chars)} línea(s) con caracteres inválidos (ver 'bad_chars')")
            result["error"] = "Verificación falló: " + "; ".join(reasons)
            result["message"] = result["error"]
        return result
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python generate_keynotes.py <obra_id>")
        sys.exit(1)
    res = generate(sys.argv[1])
    print(res.get("message") or res.get("error"))
    sys.exit(0 if res.get("ok") else 1)
