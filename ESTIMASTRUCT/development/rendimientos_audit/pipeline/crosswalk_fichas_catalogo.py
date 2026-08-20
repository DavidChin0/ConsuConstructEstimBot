#!/usr/bin/env python
# -*- coding: utf-8 -*-
# crosswalk_fichas_catalogo.py - goal-21170 (rol estimastruct)
# Cruza las fichas FHIS parseadas contra las partidas del catalogo EstimaStruct
# (Template 2026, BD canonica). NO escribe en la BD canonica: produce candidatos
# para revision manual.
import os
import re
import json
import csv
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
CANON = r"D:\EstimaStruct\data\estimacion.db"
TEMPLATE_ID = "00140181-128a-4c6a-96bb-296928cc371f"

# crosswalk capitulo FHIS -> divisiones CSI (mismo criterio que goal-21068)
FHIS_CSI = {
    "F01": ["02", "31"], "F02": ["03", "31"], "F03": ["03"], "F04": ["04", "03"],
    "F05": ["03"], "F06": ["09"], "F07": ["09"], "F08": ["07", "09"], "F09": ["03"],
    "F10": ["22", "33"], "F11": ["22", "33"], "F12": ["08", "10"], "F13": ["05", "03"],
    "F14": ["32"], "F15": ["32", "33"], "F16": ["33"], "F17": ["09"], "F18": ["01"],
    "F19": ["32", "33"], "F20": ["22"], "F21": ["26"], "F22": ["22", "33"],
    "F23": ["22", "07", "33"], "F24": ["22", "33"], "F25": ["31"], "F26": ["31"],
    "F27": ["22"], "F28": ["05", "03"], "F30": ["32", "05"], "F50": ["12"],
    "F51": ["01", "12"], "F52": ["02", "31"], "F53": ["31"], "F54": ["32", "12"],
    "F55": ["32", "12"],
}
STOP = set("de del la el los las en con para por y o a al un una que se su ala e".split())


def csi_div(code):
    if not code:
        return None
    d = "".join(ch for ch in str(code) if ch.isdigit())
    return d[:2] if len(d) >= 2 else None


def tokens(s):
    s = s.lower()
    s = re.sub(r"[^a-z0-9\u00e0-\u00ff]+", " ", s)
    return set(t for t in s.split() if t not in STOP and len(t) > 1)


def norm_units(u):
    u = (u or "").strip().upper()
    u = re.sub(r"\s+", " ", u)
    return u


def load_catalogo():
    con = sqlite3.connect(CANON)
    cur = con.cursor()
    rows = cur.execute("""
        SELECT p.id, p.clave_csi, p.descripcion, p.unidad, c.clave, c.nombre
        FROM partida p JOIN capitulo c ON c.id=p.capitulo_id
        WHERE c.presupuesto_id=?
        ORDER BY c.orden, p.orden""", (TEMPLATE_ID,)).fetchall()
    # insumos MO/Equipo por partida
    ins = {}
    for r in cur.execute("""
        SELECT i.partida_id, count(*)
        FROM insumo_partida i
        WHERE i.tipo IN ('MANO DE OBRA','EQUIPO','MANO_OBRA','MAQUINARIA','EQUIPOS')
        GROUP BY i.partida_id"""):
        ins[r[0]] = r[1]
    con.close()
    return [{"id": r[0], "clave_csi": r[1], "descripcion": r[2], "unidad": r[3],
             "cap_clave": r[4], "cap_nombre": r[5], "n_insumos_mo_eq": ins.get(r[0], 0)}
            for r in rows]


def load_fichas():
    con = sqlite3.connect(os.path.join(DATA, "rendimientos_audit.db"))
    cur = con.cursor()
    fichas = {}
    for r in cur.execute("""
        SELECT ficha_codigo, descripcion, unidad_actividad, pagina_pdf, pagina_fin
        FROM ficha_fhis GROUP BY ficha_codigo"""):
        fichas[r[0]] = {"codigo": r[0], "descripcion": r[1], "unidad": r[2],
                        "pagina": r[3], "pagina_fin": r[4]}
    con.close()
    return fichas


def similarity(a, b):
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    inter = ta & tb
    den = min(len(ta), len(tb))
    return len(inter) / den if den else 0.0


def main():
    catalogo = load_catalogo()
    fichas = load_fichas()
    # fichas agrupadas por division CSI (a traves de su capitulo Fxx)
    fichas_by_div = {}
    for c, f in fichas.items():
        cap = c[:3]
        for d in FHIS_CSI.get(cap, []):
            fichas_by_div.setdefault(d, []).append(f)

    cand = []
    for p in catalogo:
        div = csi_div(p["clave_csi"])
        if not div:
            continue
        cands_f = fichas_by_div.get(div, [])
        if not cands_f:
            continue
        best = []
        for f in cands_f:
            s = similarity(p["descripcion"], f["descripcion"])
            if s >= 0.34:
                best.append((s, f))
        best.sort(key=lambda x: x[0], reverse=True)
        for s, f in best[:5]:
            cand.append({
                "partida_id": p["id"],
                "clave_csi": p["clave_csi"],
                "capitulo": p["cap_clave"],
                "cap_nombre": p["cap_nombre"],
                "partida_desc": p["descripcion"],
                "partida_unidad": norm_units(p["unidad"]),
                "n_insumos_mo_eq": p["n_insumos_mo_eq"],
                "ficha": f["codigo"],
                "ficha_desc": f["descripcion"],
                "ficha_unidad": norm_units(f["unidad"]),
                "ficha_pagina": f["pagina"],
                "score": round(s, 3),
            })

    out = os.path.join(DATA, "candidatos_fhis_catalogo.csv")
    with open(out, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(cand[0].keys()))
        w.writeheader()
        w.writerows(cand)
    print(f"[XWALK] partidas catalogo    : {len(catalogo)}")
    print(f"[XWALK] fichas FHIS          : {len(fichas)}")
    print(f"[XWALK] candidatos (score>=.34): {len(cand)}")
    print(f"[XWALK] partidas con candidato: {len({c['partida_id'] for c in cand})}")
    print(f"[XWALK] salida               : {out}")
    # top por capitulo
    bycap = {}
    for c in cand:
        bycap.setdefault(c["capitulo"], 0)
        bycap[c["capitulo"]] += 1
    print(f"[XWALK] candidatos por capitulo: {dict(sorted(bycap.items()))}")


if __name__ == "__main__":
    main()