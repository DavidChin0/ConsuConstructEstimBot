"""Generate csi_to_codigo.json from fichas_v1.2.live.json.

Output: D:\\OneDrive\\Bots\\Estimbot\\EXPORTS\\csi_to_codigo.json
Format: {"09 29 00.6": "WS-04", ...}

Run before revit_set_marks_snippet.py.
"""
import json, os, sys

FICHAS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..",
    "development", "Template2_Updated", "v1.2", "fichas", "fichas_v1.2.live.json"
)
OUT_PATH = r"D:\OneDrive\Bots\Estimbot\EXPORTS\csi_to_codigo.json"


def generate() -> dict:
    with open(FICHAS_PATH, encoding="utf-8") as f:
        fichas = json.load(f)
    mapping = {}
    for ficha in fichas:
        csi = ficha.get("csi") or ficha.get("clave_csi")
        codigo = ficha.get("codigo")
        if csi and codigo:
            mapping[csi] = codigo
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)
    print("Written: {} entries -> {}".format(len(mapping), OUT_PATH))
    return mapping


if __name__ == "__main__":
    generate()
