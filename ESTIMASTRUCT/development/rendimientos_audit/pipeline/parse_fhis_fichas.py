#!/usr/bin/env python
# -*- coding: utf-8 -*-
# parse_fhis_fichas.py - goal-21170 (rol estimastruct)
# Extrae rendimientos del Manual de Rendimientos FHIS 2003-11 (PDF con capa de
# texto) alojado en el blog IC-UNAH (Ingenieria Civil UNAH, Honduras):
#   blog: https://icunah.wordpress.com/2008/10/10/fichas-de-costos-unitarios/
#   pdf : https://icunah.wordpress.com/wp-content/uploads/2008/10/fichas-de-costos-unitarios.pdf
# 1 ficha por pagina. Estructura por pagina:
#   <descripcion> / <codigo FXXXXXX> / Actividad / <unidad> / Unidad
#   luego secciones [Materiales|Mano de Obra|Herramienta y Equipo], cada una con
#   filas: <codigo_recurso> <desc> <valor> [<desperdicio>] <unidad_recurso>
#   y cierre "Pag:" <n>. Se extrae SOLO rendimiento con trazabilidad (nada de
#   precios). Correr con D:\LLM\python\python.exe
import os
import re
import json
import csv
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
PDF = os.path.join(DATA, "downloads", "fichas-de-costos-unitarios.pdf")
FUENTE = "FHIS Manual de Rendimientos 2003-11 (Cred. BM 3443-HO)"
URL = "https://icunah.wordpress.com/wp-content/uploads/2008/10/fichas-de-costos-unitarios.pdf"
SECCIONES = ["MATERIALES", "MANO DE OBRA", "HERRAMIENTA Y EQUIPO"]
COD_RE = re.compile(r"^[A-Z]{2}-[A-Z0-9]{4,8}$")
VAL_RE = re.compile(r"^[-+]?\d+([.,]\d+)?$")


def norm_txt(s):
    s = s.replace("\u201d", '"').replace("\u201c", '"')
    s = s.replace("\u2032", "'").replace("\u2033", '"')
    return re.sub(r"\s+", " ", s).strip()


def parse_value(v):
    v = v.replace(",", ".")
    try:
        return float(v)
    except Exception:
        return None


def parse_ficha(lines):
    ls = [norm_txt(x) for x in lines if norm_txt(x)]
    if not ls:
        return None
    code = None
    desc = ""
    for i, l in enumerate(ls):
        mm = re.search(r"\b(F\d{6})\b", l)
        if mm:
            code = mm.group(1)
            desc = norm_txt(ls[i - 1]) if i > 0 else ""
            break
    if not code:
        return None
    unidad = ""
    for i, l in enumerate(ls):
        if l.upper() == "ACTIVIDAD" and i + 1 < len(ls):
            unidad = ls[i + 1]
            break
    secciones = []
    cur = None
    i, n = 0, len(ls)
    while i < n:
        l = ls[i]
        u = l.upper()
        if u in SECCIONES:
            cur = {"seccion": l, "rows": []}
            secciones.append(cur)
            i += 1
            continue
        if u in ("RENDIMIENTO", "UNIDAD", "DESPERDICIO", "PAG:", "PAG"):
            i += 1
            continue
        if cur is not None and COD_RE.match(l):
            rdesc = norm_txt(ls[i + 1]) if i + 1 < n else ""
            j = i + 2
            rest = []
            while j < n and not COD_RE.match(ls[j]) and ls[j].upper() not in SECCIONES:
                if ls[j].upper() in ("RENDIMIENTO", "UNIDAD", "DESPERDICIO", "PAG:", "PAG"):
                    break
                rest.append(ls[j])
                j += 1
            valor = None
            desperdicio = None
            unidad_r = None
            if rest:
                if VAL_RE.match(rest[0]):
                    valor = parse_value(rest[0])
                    rest = rest[1:]
                if rest:
                    unidad_r = rest[0]
                    rest = rest[1:]
                # en MATERIALES el desperdicio va DESPUES de la unidad
                if cur["seccion"].upper() == "MATERIALES" and rest and VAL_RE.match(rest[0]):
                    desperdicio = parse_value(rest[0])
            cur["rows"].append({"recurso_codigo": l, "recurso_desc": rdesc,
                                "valor": valor, "desperdicio": desperdicio,
                                "unidad": unidad_r})
            i = j
            continue
        i += 1
    return {"ficha_codigo": code, "descripcion": desc,
            "unidad_actividad": unidad, "secciones": secciones}


def main():
    import fitz
    doc = fitz.open(PDF)
    fichas = []
    for pno in range(doc.page_count):
        f = parse_ficha(doc[pno].get_text().split("\n"))
        if f:
            f["pagina_pdf"] = pno + 1
            fichas.append(f)
    doc.close()

    merged = {}
    order = []
    for f in fichas:
        c = f["ficha_codigo"]
        if c in merged:
            prev = merged[c]
            for sec in f["secciones"]:
                target = next((s for s in prev["secciones"] if s["seccion"].upper() == sec["seccion"].upper()), None)
                if target:
                    target["rows"].extend(sec["rows"])
                else:
                    prev["secciones"].append(sec)
            prev["pagina_fin"] = f["pagina_pdf"]
        else:
            merged[c] = f
            merged[c]["pagina_fin"] = f["pagina_pdf"]
            order.append(c)

    flat = []
    n_parseados = len(order)
    n_paginas = len(fichas)
    for c in order:
        f = merged[c]
        for sec in f["secciones"]:
            tipo = {"MATERIALES": "MATERIAL", "MANO DE OBRA": "MANO_OBRA",
                    "HERRAMIENTA Y EQUIPO": "EQUIPO"}.get(sec["seccion"].upper(), sec["seccion"])
            for r in sec["rows"]:
                flat.append({
                    "ficha_codigo": c,
                    "descripcion": f["descripcion"],
                    "unidad_actividad": f["unidad_actividad"],
                    "pagina_pdf": f["pagina_pdf"],
                    "pagina_fin": f.get("pagina_fin", f["pagina_pdf"]),
                    "seccion": sec["seccion"],
                    "tipo": tipo,
                    "recurso_codigo": r["recurso_codigo"],
                    "recurso_desc": r["recurso_desc"],
                    "valor": r["valor"],
                    "desperdicio": r["desperdicio"],
                    "unidad_recurso": r["unidad"],
                    "fuente": FUENTE,
                    "url": URL,
                    "fecha_consulta": "2026-08-20",
                    "sha256_pdf": _sha(PDF),
                })
    _write_json(flat)
    _write_csv(flat)
    _write_db(flat)
    print(f"[FHIS-FICHAS] paginas procesadas : {n_paginas}")
    print(f"[FHIS-FICHAS] fichas parseadas   : {n_parseados}")
    print(f"[FHIS-FICHAS] filas por recurso  : {len(flat)}")
    print(f"[FHIS-FICHAS] mano_obra          : {sum(1 for r in flat if r['tipo']=='MANO_OBRA')}")
    print(f"[FHIS-FICHAS] equipo             : {sum(1 for r in flat if r['tipo']=='EQUIPO')}")
    print(f"[FHIS-FICHAS] material           : {sum(1 for r in flat if r['tipo']=='MATERIAL')}")


def _sha(p):
    import hashlib
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def _write_json(flat):
    out = os.path.join(DATA, "fichas_fhis_parseadas.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(flat, f, ensure_ascii=False, indent=1)
    print(f"[FHIS-FICHAS] json              : {out}")


def _write_csv(flat):
    out = os.path.join(DATA, "fichas_fhis_parseadas.csv")
    cols = ["ficha_codigo", "descripcion", "unidad_actividad", "pagina_pdf",
            "pagina_fin", "seccion", "tipo", "recurso_codigo", "recurso_desc",
            "valor", "desperdicio", "unidad_recurso", "fuente", "url",
            "fecha_consulta", "sha256_pdf"]
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(flat)
    print(f"[FHIS-FICHAS] csv               : {out}")


def _write_db(flat):
    db = os.path.join(DATA, "rendimientos_audit.db")
    con = sqlite3.connect(db)
    cur = con.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS ficha_fhis (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ficha_codigo TEXT NOT NULL,
        descripcion TEXT,
        unidad_actividad TEXT,
        pagina_pdf INTEGER,
        pagina_fin INTEGER,
        seccion TEXT,
        tipo TEXT,
        recurso_codigo TEXT,
        recurso_desc TEXT,
        valor REAL,
        desperdicio REAL,
        unidad_recurso TEXT,
        fuente TEXT,
        url TEXT,
        fecha_consulta TEXT,
        sha256_pdf TEXT,
        UNIQUE(ficha_codigo, recurso_codigo, seccion)
    );
    """)
    for r in flat:
        cur.execute("""
        INSERT OR REPLACE INTO ficha_fhis
        (ficha_codigo, descripcion, unidad_actividad, pagina_pdf, pagina_fin,
         seccion, tipo, recurso_codigo, recurso_desc, valor, desperdicio,
         unidad_recurso, fuente, url, fecha_consulta, sha256_pdf)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (r["ficha_codigo"], r["descripcion"], r["unidad_actividad"],
              r["pagina_pdf"], r["pagina_fin"], r["seccion"], r["tipo"],
              r["recurso_codigo"], r["recurso_desc"], r["valor"],
              r["desperdicio"], r["unidad_recurso"], r["fuente"], r["url"],
              r["fecha_consulta"], r["sha256_pdf"]))
    con.commit()
    con.close()
    print(f"[FHIS-FICHAS] sqlite staging   : {db}")


if __name__ == "__main__":
    main()