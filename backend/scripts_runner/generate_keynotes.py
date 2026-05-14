"""Genera RevitKeynotes_<Obra>_<Fecha>.txt desde la obra activa (DB).

Formato (igual a PY_S1_xlsx_a_keynotes.py existente):
  Encoding   : latin-1
  Separador  : TAB
  Fin de linea: CRLF
  Sección 1  : XX 00 00 \\t <nombre_capitulo> \\t (vacío)
  Sección 2  : <CSI> \\t <descripción> \\t XX 00 00

Uso (CLI):
  python generate_keynotes.py <obra_id>
"""
import os, re, sys, datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import SessionLocal
from models import Presupuesto, Capitulo, Partida

OUT_DIR = r"D:\OneDrive\Bots\Estimbot\EXPORTS\S1_keynotes"


def _clean(text: str) -> str:
    if text is None:
        return ""
    t = str(text).strip()
    t = re.sub(r"_x000D_\s*", "", t)
    t = re.sub(r"[\r\n]+", " ", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def _csi_natural_key(s: str):
    parts = []
    for tok in re.findall(r"\d+|\D+", s or ""):
        parts.append((0, int(tok)) if tok.isdigit() else (1, tok.lower()))
    return parts


def generate(obra_id: str) -> dict:
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

        os.makedirs(OUT_DIR, exist_ok=True)
        nombre_safe = re.sub(r"[^\w\-]+", "_", (obra.nombre or "obra")).strip("_") or "obra"
        date_tag = datetime.datetime.now().strftime("%Y-%m-%d")
        filename = f"RevitKeynotes_{nombre_safe}_{date_tag}.txt"
        out_path = os.path.join(OUT_DIR, filename)

        content = "\r\n".join(lines) + "\r\n"
        encoded = content.encode("latin-1", errors="replace")
        with open(out_path, "wb") as f:
            f.write(encoded)

        return {
            "ok": True,
            "path": out_path,
            "filename": filename,
            "lines": len(lines),
            "divisiones": len(capitulos),
            "partidas": len(lines) - len(capitulos),
            "size_bytes": len(encoded),
            "message": f"(keynote creado) {filename} — {len(capitulos)} divisiones, {len(lines) - len(capitulos)} partidas",
        }
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python generate_keynotes.py <obra_id>")
        sys.exit(1)
    res = generate(sys.argv[1])
    print(res.get("message") or res.get("error"))
    sys.exit(0 if res.get("ok") else 1)
