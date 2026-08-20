#!/usr/bin/env python
# -*- coding: utf-8 -*-
import json
import sqlite3
import hashlib

# Load Suárez Salazar data
with open(r'D:\GitHub\EstimBot\ConsuConstructEstimBot\ESTIMASTRUCT\development\rendimientos_audit\pipeline\data\suarez_miguelgarcia_rows.json', encoding='utf-8') as f:
    suarez_rows = json.load(f)

# Clean data
clean_rows = []
for row in suarez_rows:
    if len(row) >= 4:
        desc = row[0].strip()
        unidad = row[1].strip()
        rendimiento = row[2].strip()  # e.g., "50.000 m2 / Jor"
        inverso = row[3].strip()      # e.g., "0.020 Jor / m2"
        
        # Parse rendimiento value
        import re
        m = re.search(r'([\d.,]+)\s*(\w+)\s*/\s*(\w+)', rendimiento)
        if m:
            val = float(m.group(1).replace(',', '.'))
            unit_out = m.group(2)
            unit_in = m.group(3)
        else:
            val = None
            unit_out = unidad
            unit_in = 'Jor'
        
        # Parse inverso for normalization
        m2 = re.search(r'([\d.,]+)\s*(\w+)\s*/\s*(\w+)', inverso)
        if m2:
            val_inv = float(m2.group(1).replace(',', '.'))
        else:
            val_inv = None
        
        clean_rows.append({
            'descripcion': desc,
            'unidad': unidad,
            'rendimiento_str': rendimiento,
            'inverso_str': inverso,
            'valor': val,           # e.g., 50.0 (m2/Jor)
            'unidad_out': unit_out, # e.g., m2
            'unidad_in': unit_in,   # e.g., Jor
            'valor_inv': val_inv,   # e.g., 0.02 (Jor/m2)
        })

print(f'Clean rows: {len(clean_rows)}')

# Load canonical catalog
con_canon = sqlite3.connect(r'D:\EstimaStruct\data\estimacion.db')
cur_canon = con_canon.cursor()

# Get all partidas with CSI codes and descriptions
cur_canon.execute("""
    SELECT p.id, p.clave_csi, p.descripcion, p.unidad, c.clave, c.nombre
    FROM partida p JOIN capitulo c ON c.id=p.capitulo_id
    WHERE c.presupuesto_id = '00140181-128a-4c6a-96bb-296928cc371f'
    ORDER BY c.orden, p.orden
""")
catalogo = cur_canon.fetchall()
print(f'Catalogo partidas: {len(catalogo)}')

# Simple token matching
import re
STOP = set("de del la el los las en con para por y o a al un una que se su".split())

def tokens(s):
    s = s.lower()
    s = re.sub(r"[^a-z0-9\u00e0-\u00ff]+", " ", s)
    return set(t for t in s.split() if t not in STOP and len(t) > 1)

def similarity(a, b):
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    inter = ta & tb
    den = min(len(ta), len(tb))
    return len(inter) / den if den else 0.0

# Match each Suárez row to catalog
matches = []
for sr in clean_rows:
    best = None
    best_score = 0
    for p in catalogo:
        score = similarity(sr['descripcion'], p[2])  # p[2] = partida descripcion
        if score > best_score:
            best_score = score
            best = p
    if best and best_score >= 0.3:
        matches.append({
            'suarez': sr,
            'partida_id': best[0],
            'clave_csi': best[1],
            'partida_desc': best[2],
            'partida_unidad': best[3],
            'score': best_score
        })

print(f'Matches (score>=0.3): {len(matches)}')
for m in matches[:10]:
    print(f"  {m['score']:.3f} | {m['partida_desc'][:50]} <- {m['suarez']['descripcion'][:50]}")

# Hash of source
url = "http://miguelgarcia.xyz/rendimientos/"
source_html = r'D:\GitHub\EstimBot\ConsuConstructEstimBot\ESTIMASTRUCT\development\rendimientos_audit\pipeline\data\downloads\suarez_miguelgarcia.html'
html_hash = hashlib.sha256(open(source_html, "rb").read()).hexdigest()

# Insert into audit table
inserted = 0
for m in matches:
    sr = m['suarez']
    if sr['valor_inv'] is None:
        continue
    
    # Use inverse as normalized coefficient (Jor per unit of activity)
    # The unidad of the activity is sr['unidad'] (e.g., m2, m3, ton)
    coef_normalizado = sr['valor_inv']
    unidad_nativa = f"Jor/{sr['unidad']}"
    formula = f"Inverso del rendimiento: {sr['inverso_str']} (fuente: {sr['rendimiento_str']})"
    
    if m['score'] >= 0.7:
        tipo_match = "exacto"
    elif m['score'] >= 0.5:
        tipo_match = "semantico"
    else:
        tipo_match = "manual"
    
    try:
        cur_canon.execute("""
            INSERT OR IGNORE INTO rendimiento_audit
            (partida_id, partida_clave_csi, partida_descripcion, partida_unidad,
             fuente, fuente_edicion, fuente_codigo, fuente_url, fuente_pagina,
             fecha_consulta, recurso_tipo, recurso_descripcion,
             coeficiente_nativo, unidad_nativa, coeficiente_normalizado,
             formula_conversion, tipo_match, confianza, evidencia,
             condiciones_alcance, hash_insumo, notas_discrepancia)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            m['partida_id'],
            m['clave_csi'],
            m['partida_desc'],
            m['partida_unidad'],
            "SUAREZ_SALAZAR",
            "Costo y tiempo en edificación (3a ed., Limusa) - datos extraídos de http://miguelgarcia.xyz/rendimientos/",
            "Tabla de rendimientos promedio de obra",
            url,
            "Tabla web (índice por capítulos)",
            "2026-08-20",
            "MANO_OBRA",
            sr['descripcion'],
            sr['valor_inv'],
            unidad_nativa,
            coef_normalizado,
            formula,
            tipo_match,
            round(m['score'], 3),
            f"Rendimiento: {sr['rendimiento_str']}, Inverso: {sr['inverso_str']}",
            f"Actividad: {sr['descripcion']}, unidad: {sr['unidad']}",
            html_hash,
            f"Match score: {m['score']:.3f}; Fuente secundaria (web) basada en libro Suárez Salazar 3a ed." if m['score'] < 1.0 else ""
        ))
        if cur_canon.rowcount > 0:
            inserted += 1
    except Exception as e:
        print(f"Error: {e}")

con_canon.commit()
con_canon.close()

print(f'Inserted: {inserted}')

# Verify
con = sqlite3.connect(r'D:\EstimaStruct\data\estimacion.db')
cur = con.cursor()
cur.execute("SELECT COUNT(*) FROM rendimiento_audit WHERE fuente = 'SUAREZ_SALAZAR'")
print(f"SUAREZ_SALAZAR records: {cur.fetchone()[0]}")
cur.execute("SELECT COUNT(*) FROM rendimiento_audit")
print(f"Total audit records: {cur.fetchone()[0]}")
con.close()