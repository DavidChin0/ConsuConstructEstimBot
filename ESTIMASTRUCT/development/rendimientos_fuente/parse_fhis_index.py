#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
parse_fhis_index.py  —  goal-21068 (rol estimastruct)

Etapa 1-2 del plan aprobado (goal-21065 §4): ADQUISICIÓN + PARSEO de la fuente
primaria de RENDIMIENTOS a una TABLA INTERMEDIA (staging), sin tocar producción.

Fuente:  FHIS — "Manual de Rendimientos, Crédito No. 3443-HO del Banco Mundial,
         noviembre 2003" (Honduras). Índice de actividades digitalizado por
         Quercusoft: https://quercusoft.com/honduras-fhis-200311/
Insumo:  artifacts/fhis/quercusoft_listado.html (HTML descargado 2026-08-15)

Qué produce (todo STAGING, prefijo data/):
  - fhis_actividad.csv / .json  : índice normalizado de 2204 actividades
                                  (fhis_code, descripcion, unidad, capitulo,
                                   subcapitulo, inhabilitada, fuente, anio)
  - rendimientos_fuente.db (SQLite, tabla fhis_actividad + rendimiento_fuente)

Qué NO produce (gated a 2º OK de David — "poblar valores = producción"):
  - Los valores numéricos de rendimiento por recurso (cuadrilla, m·h/unidad,
    cantidad de material) NO están en el índice Quercusoft: viven en las fichas
    escaneadas del PDF FHIS. La tabla `rendimiento_fuente` queda CREADA pero
    VACÍA — se puebla en el paso siguiente (extracción del PDF), que requiere OK.

Correr:  D:\LLM\python\python.exe parse_fhis_index.py
"""
import os
import re
import csv
import json
import html
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
HTML_SRC = r"C:\Users\consu\.openclaw\workspace\artifacts\fhis\quercusoft_listado.html"
FUENTE = "FHIS Manual de Rendimientos 2003-11 (Cred. BM 3443-HO)"
ANIO = 2003

# FHIS agrupa por capítulo F0XX. El capítulo mayor (F01..F30, F50) es lo que
# mapea a división CSI. Nombres de capítulo derivados del propio índice.
CAPITULOS = {
    "F01": "Limpieza, demolicion, trazado y movimiento de tierra menor",
    "F02": "Cimentacion (mamposteria, zapatas, pedestales, dados)",
    "F03": "Estructura de concreto (solera, castillo, columna, viga)",
    "F04": "Paredes (ladrillo, bloque, adobe, concreto)",
    "F05": "Concreto y acero de refuerzo",
    "F06": "Acabados (afinado, azulejo, curado, jardin)",
    "F07": "Pisos",
    "F08": "Techos, cielo falso y canaletas",
    "F09": "Losas",
    "F10": "Tuberia de agua potable (PVC/concreto)",
    "F11": "Saneamiento (cajas, tanque septico, letrina, pozo)",
    "F12": "Ventaneria, contramarcos, divisiones y balcones",
    "F13": "Apoyos estructurales (neopreno)",
    "F14": "Cercos, malla ciclon y postes",
    "F15": "Pavimentos, adoquin, bordillo y sellos",
    "F16": "Alcantarillado sanitario (pozos, PVC, pruebas)",
    "F17": "Pinturas",
    "F18": "Direccion tecnica de obra",
    "F19": "Cunetas y rejillas",
    "F20": "Aparatos sanitarios",
    "F21": "Instalacion electrica e iluminacion",
    "F22": "Drenaje pluvial (tragantes, bajantes)",
    "F23": "Valvulas, impermeabilizacion y obra de concreto hidraulica",
    "F24": "Disipadores de mamposteria",
    "F25": "Horas maquina (tractor, equipo pesado)",
    "F26": "Remocion y carga con maquinaria",
    "F27": "Bajantes PVC",
    "F28": "Gradas, pasamanos y asta de bandera",
    "F30": "Puentes colgantes peatonales",
    "F50": "Mobiliario escolar",
    "F51": "Material didactico y alimentacion (programa social)",
    "F52": "Ensayos de suelos (Proctor, densidad)",
    "F53": "Alquiler de maquinaria (excavadora)",
    "F54": "Juegos infantiles y mobiliario de sitio",
    "F55": "Mobiliario urbano (bancas, faroles)",
}


def cap_mayor(code):
    """F034xxx -> F03 ; F211xxx -> F21 ; F503xxx -> F50."""
    return code[:3]


def clean(txt):
    txt = html.unescape(txt)
    # normaliza comillas/pulgadas y espacios
    txt = txt.replace("\u2033", '"').replace("\u2032", "'")
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt


def parse():
    raw = open(HTML_SRC, encoding="utf-8").read()
    rows = re.findall(
        r'<td[^>]*>\s*(F\d{6})\s*</td>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>',
        raw, re.S,
    )
    out = []
    seen = set()
    for code, desc, unit in rows:
        if code in seen:      # el índice tiene 1 duplicado; se conserva 1
            continue
        seen.add(code)
        desc_c = clean(desc)
        unit_c = clean(unit)
        cap = cap_mayor(code)
        out.append({
            "fhis_code": code,
            "descripcion": desc_c,
            "unidad": unit_c,
            "capitulo": cap,
            "capitulo_nombre": CAPITULOS.get(cap, "(sin clasificar)"),
            "subcapitulo": code[:4],
            "inhabilitada": 1 if "INHABILITADA" in desc_c.upper() else 0,
            "fuente": FUENTE,
            "anio": ANIO,
        })
    return out


def write_flat(rows):
    os.makedirs(DATA, exist_ok=True)
    cols = ["fhis_code", "descripcion", "unidad", "capitulo", "capitulo_nombre",
            "subcapitulo", "inhabilitada", "fuente", "anio"]
    with open(os.path.join(DATA, "fhis_actividad.csv"), "w", newline="",
              encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    with open(os.path.join(DATA, "fhis_actividad.json"), "w",
              encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)


def write_db(rows):
    db = os.path.join(DATA, "rendimientos_fuente.db")
    con = sqlite3.connect(db)
    cur = con.cursor()
    cur.executescript("""
    DROP TABLE IF EXISTS fhis_actividad;
    CREATE TABLE fhis_actividad (
        fhis_code      TEXT PRIMARY KEY,
        descripcion    TEXT NOT NULL,
        unidad         TEXT,
        capitulo       TEXT,
        capitulo_nombre TEXT,
        subcapitulo    TEXT,
        inhabilitada   INTEGER DEFAULT 0,
        fuente         TEXT,
        anio           INTEGER
    );
    -- Tabla intermedia de rendimientos por recurso (§4 del plan).
    -- Se crea ahora; se POBLA en el paso siguiente (extraccion del PDF FHIS),
    -- que es produccion y requiere 2o OK de David.
    DROP TABLE IF EXISTS rendimiento_fuente;
    CREATE TABLE rendimiento_fuente (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        fhis_code    TEXT NOT NULL REFERENCES fhis_actividad(fhis_code),
        recurso_clave TEXT,
        recurso_desc TEXT,
        tipo         TEXT,      -- MANO_OBRA | MATERIAL | EQUIPO
        cantidad     REAL,      -- rendimiento: cantidad de recurso por unidad de actividad
        unidad       TEXT,
        desperdicio  REAL,      -- % de desperdicio (solo materiales)
        fuente       TEXT,
        anio         INTEGER
    );
    """)
    cur.executemany(
        "INSERT INTO fhis_actividad VALUES (?,?,?,?,?,?,?,?,?)",
        [(r["fhis_code"], r["descripcion"], r["unidad"], r["capitulo"],
          r["capitulo_nombre"], r["subcapitulo"], r["inhabilitada"],
          r["fuente"], r["anio"]) for r in rows],
    )
    con.commit()
    con.close()
    return db


def main():
    rows = parse()
    write_flat(rows)
    db = write_db(rows)
    act = len(rows)
    inhab = sum(r["inhabilitada"] for r in rows)
    caps = len({r["capitulo"] for r in rows})
    print(f"[FHIS] actividades parseadas : {act}")
    print(f"[FHIS] capitulos mayores      : {caps}")
    print(f"[FHIS] inhabilitadas (flag)   : {inhab}  (activas: {act - inhab})")
    print(f"[FHIS] staging DB             : {db}")
    print(f"[FHIS] rendimiento_fuente     : 0 filas (gated a 2o OK: extraccion PDF)")


if __name__ == "__main__":
    main()
