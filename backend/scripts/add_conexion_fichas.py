"""
add_conexion_fichas.py
Agrega 6 fichas de costo de conexiones de soldadura estructural a V1.1.
Crea recursos nuevos si no existen. No repite CSI ni Type Mark.
"""
import json, os, shutil, sqlite3, uuid
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "backend" / "estimacion.db"
JSON_PATH = REPO_ROOT / "development" / "Template2_Updated" / "v1.1" / "fichas" / "fichas_v1.1.json"
JSON_PATH_STR = str(JSON_PATH)
LIVE_PATH = JSON_PATH_STR.replace(".json", ".live.json")

# ---------------------------------------------------------------------------
# 1. Recursos a garantizar en BD
# ---------------------------------------------------------------------------
RECURSOS_NUEVOS = [
    # (clave, descripcion, unidad, tipo, precio_unitario)
    ("MA-368", "Disco de corte 4-1/2\" x 1/8\"",          "pza",   "MATERIAL",    55.00),
    ("MA-372", "Disco de desbaste 4-1/2\" x 1/4\"",        "pza",   "MATERIAL",    65.00),
    ("EQ-010", "Equipo de soldadura inverter 200A",         "hora",  "EQUIPO",      25.00),
    ("FL-001", "Flete al sitio",                            "viaje", "FLETE",     1500.00),
]

def ensure_recursos(con):
    cur = con.cursor()
    now = datetime.utcnow().isoformat()
    for clave, desc, unidad, tipo, precio in RECURSOS_NUEVOS:
        cur.execute("SELECT 1 FROM recurso WHERE clave=?", (clave,))
        if not cur.fetchone():
            cur.execute(
                "INSERT INTO recurso (id, clave, descripcion, unidad, tipo, precio_unitario, ultima_actualizacion)"
                " VALUES (?,?,?,?,?,?,?)",
                (str(uuid.uuid4()), clave, desc, unidad, tipo, precio, now)
            )
            print(f"  CREADO recurso {clave} - {desc}")
        else:
            print(f"  OK (existe) {clave}")
    con.commit()

# ---------------------------------------------------------------------------
# 2. Definición de las 6 fichas
# ---------------------------------------------------------------------------
# Unidad: "conexion" (precio por conexión completa)
# Insumos: cantidad por conexion, precio unitario real

FICHAS_NUEVAS = [
    {
        "csi": "05 20 00.15",
        "codigo": "CX-15",
        "descripcion": "Conexion soldada W200x36 - Filete AISC (por conexion)",
        "unidad": "conexion",
        "color_tipo": "azul",
        "insumos": [
            {"codigo": "MA-182", "descripcion": "Electrodo E6013 1/8\"",          "unidad": "lb",     "tipo": "MATERIAL",    "cantidad": 6.00,  "precioUnitario": 150.00},
            {"codigo": "MA-372", "descripcion": "Disco desbaste 4-1/2\"",          "unidad": "pza",    "tipo": "MATERIAL",    "cantidad": 2.50,  "precioUnitario":  65.00},
            {"codigo": "MA-368", "descripcion": "Disco corte 4-1/2\"",             "unidad": "pza",    "tipo": "MATERIAL",    "cantidad": 0.85,  "precioUnitario":  55.00},
            {"codigo": "MO-013", "descripcion": "Soldador calificado",             "unidad": "jor",    "tipo": "MANO_OBRA",   "cantidad": 3.60,  "precioUnitario": 700.00},
            {"codigo": "MO-006", "descripcion": "Ayudante",                        "unidad": "jor",    "tipo": "MANO_OBRA",   "cantidad": 1.61,  "precioUnitario": 500.00},
            {"codigo": "EQ-010", "descripcion": "Equipo soldadura inverter",       "unidad": "hora",   "tipo": "EQUIPO",      "cantidad": 22.00, "precioUnitario":  25.00},
            {"codigo": "HER-00", "descripcion": "Herramienta manual",              "unidad": "(%)mo",  "tipo": "HERRAMIENTA", "cantidad": 0.05,  "precioUnitario": 3325.00},
            {"codigo": "FL-001", "descripcion": "Flete al sitio",                  "unidad": "viaje",  "tipo": "FLETE",       "cantidad": 0.19,  "precioUnitario": 1500.00},
        ]
    },
    {
        "csi": "05 20 00.16",
        "codigo": "CX-16",
        "descripcion": "Conexion soldada W200x71 - Filete AISC (por conexion)",
        "unidad": "conexion",
        "color_tipo": "azul",
        "insumos": [
            {"codigo": "MA-182", "descripcion": "Electrodo E6013 1/8\"",          "unidad": "lb",     "tipo": "MATERIAL",    "cantidad": 7.00,  "precioUnitario": 150.00},
            {"codigo": "MA-372", "descripcion": "Disco desbaste 4-1/2\"",          "unidad": "pza",    "tipo": "MATERIAL",    "cantidad": 2.00,  "precioUnitario":  65.00},
            {"codigo": "MA-368", "descripcion": "Disco corte 4-1/2\"",             "unidad": "pza",    "tipo": "MATERIAL",    "cantidad": 0.21,  "precioUnitario":  55.00},
            {"codigo": "MO-013", "descripcion": "Soldador calificado",             "unidad": "jor",    "tipo": "MANO_OBRA",   "cantidad": 4.00,  "precioUnitario": 700.00},
            {"codigo": "MO-006", "descripcion": "Ayudante",                        "unidad": "jor",    "tipo": "MANO_OBRA",   "cantidad": 1.55,  "precioUnitario": 500.00},
            {"codigo": "EQ-010", "descripcion": "Equipo soldadura inverter",       "unidad": "hora",   "tipo": "EQUIPO",      "cantidad": 23.00, "precioUnitario":  25.00},
            {"codigo": "HER-00", "descripcion": "Herramienta manual",              "unidad": "(%)mo",  "tipo": "HERRAMIENTA", "cantidad": 0.05,  "precioUnitario": 3575.00},
            {"codigo": "FL-001", "descripcion": "Flete al sitio",                  "unidad": "viaje",  "tipo": "FLETE",       "cantidad": 0.20,  "precioUnitario": 1500.00},
        ]
    },
    {
        "csi": "05 20 00.17",
        "codigo": "CX-17",
        "descripcion": "Conexion soldada W250x49 - Filete AISC (por conexion)",
        "unidad": "conexion",
        "color_tipo": "azul",
        "insumos": [
            {"codigo": "MA-182", "descripcion": "Electrodo E6013 1/8\"",          "unidad": "lb",     "tipo": "MATERIAL",    "cantidad": 6.90,  "precioUnitario": 150.00},
            {"codigo": "MA-372", "descripcion": "Disco desbaste 4-1/2\"",          "unidad": "pza",    "tipo": "MATERIAL",    "cantidad": 2.00,  "precioUnitario":  65.00},
            {"codigo": "MA-368", "descripcion": "Disco corte 4-1/2\"",             "unidad": "pza",    "tipo": "MATERIAL",    "cantidad": 0.10,  "precioUnitario":  55.00},
            {"codigo": "MO-013", "descripcion": "Soldador calificado",             "unidad": "jor",    "tipo": "MANO_OBRA",   "cantidad": 4.00,  "precioUnitario": 700.00},
            {"codigo": "MO-006", "descripcion": "Ayudante",                        "unidad": "jor",    "tipo": "MANO_OBRA",   "cantidad": 1.40,  "precioUnitario": 500.00},
            {"codigo": "EQ-010", "descripcion": "Equipo soldadura inverter",       "unidad": "hora",   "tipo": "EQUIPO",      "cantidad": 22.00, "precioUnitario":  25.00},
            {"codigo": "HER-00", "descripcion": "Herramienta manual",              "unidad": "(%)mo",  "tipo": "HERRAMIENTA", "cantidad": 0.05,  "precioUnitario": 3500.00},
            {"codigo": "FL-001", "descripcion": "Flete al sitio",                  "unidad": "viaje",  "tipo": "FLETE",       "cantidad": 0.19,  "precioUnitario": 1500.00},
        ]
    },
    {
        "csi": "05 20 00.18",
        "codigo": "CX-18",
        "descripcion": "Conexion soldada W310x73 - Filete AISC (por conexion)",
        "unidad": "conexion",
        "color_tipo": "azul",
        "insumos": [
            {"codigo": "MA-182", "descripcion": "Electrodo E6013 1/8\"",          "unidad": "lb",     "tipo": "MATERIAL",    "cantidad": 7.50,  "precioUnitario": 150.00},
            {"codigo": "MA-372", "descripcion": "Disco desbaste 4-1/2\"",          "unidad": "pza",    "tipo": "MATERIAL",    "cantidad": 2.00,  "precioUnitario":  65.00},
            {"codigo": "MA-368", "descripcion": "Disco corte 4-1/2\"",             "unidad": "pza",    "tipo": "MATERIAL",    "cantidad": 0.82,  "precioUnitario":  55.00},
            {"codigo": "MO-013", "descripcion": "Soldador calificado",             "unidad": "jor",    "tipo": "MANO_OBRA",   "cantidad": 4.30,  "precioUnitario": 700.00},
            {"codigo": "MO-006", "descripcion": "Ayudante",                        "unidad": "jor",    "tipo": "MANO_OBRA",   "cantidad": 1.78,  "precioUnitario": 500.00},
            {"codigo": "EQ-010", "descripcion": "Equipo soldadura inverter",       "unidad": "hora",   "tipo": "EQUIPO",      "cantidad": 24.00, "precioUnitario":  25.00},
            {"codigo": "HER-00", "descripcion": "Herramienta manual",              "unidad": "(%)mo",  "tipo": "HERRAMIENTA", "cantidad": 0.05,  "precioUnitario": 3900.00},
            {"codigo": "FL-001", "descripcion": "Flete al sitio",                  "unidad": "viaje",  "tipo": "FLETE",       "cantidad": 0.22,  "precioUnitario": 1500.00},
        ]
    },
    {
        "csi": "05 20 00.19",
        "codigo": "CX-19",
        "descripcion": "Conexion soldada W200x71 (col) x W200x36 (vig) - Mixta AISC (por conexion)",
        "unidad": "conexion",
        "color_tipo": "azul",
        "insumos": [
            {"codigo": "MA-182", "descripcion": "Electrodo E6013 1/8\"",          "unidad": "lb",     "tipo": "MATERIAL",    "cantidad": 7.20,  "precioUnitario": 150.00},
            {"codigo": "MA-372", "descripcion": "Disco desbaste 4-1/2\"",          "unidad": "pza",    "tipo": "MATERIAL",    "cantidad": 2.00,  "precioUnitario":  65.00},
            {"codigo": "MA-368", "descripcion": "Disco corte 4-1/2\"",             "unidad": "pza",    "tipo": "MATERIAL",    "cantidad": 0.42,  "precioUnitario":  55.00},
            {"codigo": "MO-013", "descripcion": "Soldador calificado",             "unidad": "jor",    "tipo": "MANO_OBRA",   "cantidad": 4.10,  "precioUnitario": 700.00},
            {"codigo": "MO-006", "descripcion": "Ayudante",                        "unidad": "jor",    "tipo": "MANO_OBRA",   "cantidad": 1.66,  "precioUnitario": 500.00},
            {"codigo": "EQ-010", "descripcion": "Equipo soldadura inverter",       "unidad": "hora",   "tipo": "EQUIPO",      "cantidad": 23.00, "precioUnitario":  25.00},
            {"codigo": "HER-00", "descripcion": "Herramienta manual",              "unidad": "(%)mo",  "tipo": "HERRAMIENTA", "cantidad": 0.05,  "precioUnitario": 3700.00},
            {"codigo": "FL-001", "descripcion": "Flete al sitio",                  "unidad": "viaje",  "tipo": "FLETE",       "cantidad": 0.21,  "precioUnitario": 1500.00},
        ]
    },
    {
        "csi": "05 20 00.20",
        "codigo": "CX-20",
        "descripcion": "Conexion soldada W250x49 (col) x W200x71 (vig) - Mixta AISC (por conexion)",
        "unidad": "conexion",
        "color_tipo": "azul",
        "insumos": [
            {"codigo": "MA-182", "descripcion": "Electrodo E6013 1/8\"",          "unidad": "lb",     "tipo": "MATERIAL",    "cantidad": 7.80,  "precioUnitario": 150.00},
            {"codigo": "MA-372", "descripcion": "Disco desbaste 4-1/2\"",          "unidad": "pza",    "tipo": "MATERIAL",    "cantidad": 1.00,  "precioUnitario":  65.00},
            {"codigo": "MA-368", "descripcion": "Disco corte 4-1/2\"",             "unidad": "pza",    "tipo": "MATERIAL",    "cantidad": 0.27,  "precioUnitario":  55.00},
            {"codigo": "MO-013", "descripcion": "Soldador calificado",             "unidad": "jor",    "tipo": "MANO_OBRA",   "cantidad": 4.20,  "precioUnitario": 700.00},
            {"codigo": "MO-006", "descripcion": "Ayudante",                        "unidad": "jor",    "tipo": "MANO_OBRA",   "cantidad": 1.62,  "precioUnitario": 500.00},
            {"codigo": "EQ-010", "descripcion": "Equipo soldadura inverter",       "unidad": "hora",   "tipo": "EQUIPO",      "cantidad": 24.00, "precioUnitario":  25.00},
            {"codigo": "HER-00", "descripcion": "Herramienta manual",              "unidad": "(%)mo",  "tipo": "HERRAMIENTA", "cantidad": 0.05,  "precioUnitario": 3750.00},
            {"codigo": "FL-001", "descripcion": "Flete al sitio",                  "unidad": "viaje",  "tipo": "FLETE",       "cantidad": 0.21,  "precioUnitario": 1500.00},
        ]
    },
]

# ---------------------------------------------------------------------------
# 3. Main
# ---------------------------------------------------------------------------
def main():
    # -- Recursos en BD --
    print("\n=== RECURSOS ===")
    con = sqlite3.connect(str(DB_PATH))
    ensure_recursos(con)
    con.close()

    # -- JSON V1.1 --
    print("\n=== JSON V1.1 ===")
    with open(JSON_PATH_STR, encoding="utf-8") as f:
        fichas = json.load(f)

    csi_existentes   = {(fi.get("csi") or "").strip() for fi in fichas}
    codigo_existentes = {(fi.get("codigo") or "").strip().upper() for fi in fichas}

    agregadas = []
    omitidas  = []

    for nueva in FICHAS_NUEVAS:
        csi    = nueva["csi"].strip()
        codigo = nueva["codigo"].strip()

        if csi in csi_existentes:
            omitidas.append(f"CSI repetido: {csi} ({codigo})")
            continue
        if codigo.upper() in codigo_existentes:
            omitidas.append(f"Type Mark repetido: {codigo} ({csi})")
            continue

        fichas.append(nueva)
        csi_existentes.add(csi)
        codigo_existentes.add(codigo.upper())
        agregadas.append(f"{csi} - {codigo}")

    if not agregadas:
        print("  Sin fichas nuevas que agregar.")
        return

    # Backup
    bak = JSON_PATH_STR.replace(".json", ".bak_conexion.json")
    shutil.copy2(JSON_PATH_STR, bak)
    print(f"  Backup: {os.path.basename(bak)}")

    # Guardar
    for target in (JSON_PATH_STR, LIVE_PATH):
        with open(target, "w", encoding="utf-8") as f:
            json.dump(fichas, f, ensure_ascii=False, indent=2)

    print(f"\n  Fichas totales: {len(fichas)}")
    print(f"  Agregadas ({len(agregadas)}):")
    for a in agregadas: print(f"    + {a}")
    if omitidas:
        print(f"  Omitidas ({len(omitidas)}):")
        for o in omitidas: print(f"    - {o}")


if __name__ == "__main__":
    main()
