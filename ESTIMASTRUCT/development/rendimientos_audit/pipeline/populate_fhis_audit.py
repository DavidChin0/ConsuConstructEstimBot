#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sqlite3
import csv
import hashlib

# Cargar candidatos
candidates = []
with open(r'D:\GitHub\EstimBot\ConsuConstructEstimBot\ESTIMASTRUCT\development\rendimientos_audit\pipeline\data\candidatos_fhis_catalogo.csv', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    candidates = list(reader)

# Agrupar por partida_id
from collections import defaultdict
cand_by_partida = defaultdict(list)
for c in candidates:
    cand_by_partida[c['partida_id']].append(c)

# Cargar datos FHIS parseados
con_fhis = sqlite3.connect(r'D:\GitHub\EstimBot\ConsuConstructEstimBot\ESTIMASTRUCT\development\rendimientos_audit\pipeline\data\rendimientos_audit.db')
cur_fhis = con_fhis.cursor()

# Cargar BD canonica
con_canon = sqlite3.connect(r'D:\EstimaStruct\data\estimacion.db')
cur_canon = con_canon.cursor()

# Hash del PDF
pdf_path = r'D:\GitHub\EstimBot\ConsuConstructEstimBot\ESTIMASTRUCT\development\rendimientos_audit\pipeline\data\downloads\fichas-de-costos-unitarios.pdf'
pdf_hash = hashlib.sha256(open(pdf_path, "rb").read()).hexdigest()

# Mapear tipo FHIS -> recurso_tipo
tipo_map = {"MANO_OBRA": "MANO_OBRA", "EQUIPO": "EQUIPO"}

inserted = 0
errors = 0

for partida_id, cands in cand_by_partida.items():
    # Tomar el mejor candidato (mayor score)
    best = max(cands, key=lambda x: float(x['score']))
    ficha_code = best['ficha']
    score = float(best['score'])
    
    # Determinar tipo_match
    if score >= 0.8:
        tipo_match = "exacto"
    elif score >= 0.5:
        tipo_match = "semantico"
    else:
        tipo_match = "manual"
    
    # Obtener datos de la partida
    cur_canon.execute("""
        SELECT p.clave_csi, p.descripcion, p.unidad
        FROM partida p WHERE p.id = ?
    """, (partida_id,))
    pdata = cur_canon.fetchone()
    if not pdata:
        print(f"Partida no encontrada: {partida_id}")
        errors += 1
        continue
    clave_csi, p_desc, p_unidad = pdata
    
    # Obtener rendimientos FHIS para esta ficha (solo MANO_OBRA y EQUIPO)
    cur_fhis.execute("""
        SELECT seccion, tipo, recurso_codigo, recurso_desc, valor, unidad_recurso, pagina_pdf
        FROM ficha_fhis
        WHERE ficha_codigo = ? AND tipo IN ('MANO_OBRA', 'EQUIPO')
    """, (ficha_code,))
    fhis_rows = cur_fhis.fetchall()
    
    for seccion, tipo, rec_codigo, rec_desc, valor, unidad_rec, pagina in fhis_rows:
        if valor is None:
            continue
        
        recurso_tipo = tipo_map.get(tipo, tipo)
        
        # Normalizar: FHIS ya expresa coeficientes por unidad de actividad
        # La unidad de la ficha es la unidad de actividad
        cur_fhis.execute("SELECT unidad_actividad FROM ficha_fhis WHERE ficha_codigo = ? LIMIT 1", (ficha_code,))
        ua_row = cur_fhis.fetchone()
        unidad_actividad_fhis = ua_row[0] if ua_row else ""
        
        # Formula de conversion
        if unidad_rec and unidad_actividad_fhis:
            formula = f"{valor} {unidad_rec} por {unidad_actividad_fhis} de actividad"
        else:
            formula = "Directo desde fuente"
        
        # Coeficiente normalizado = valor (FHIS ya está por unidad de actividad)
        coef_normalizado = float(valor)
        
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
                partida_id,
                clave_csi,
                p_desc,
                p_unidad,
                "FHIS",
                "Manual de Rendimientos 2003-11 (Cred. BM 3443-HO)",
                ficha_code,
                "https://icunah.wordpress.com/wp-content/uploads/2008/10/fichas-de-costos-unitarios.pdf",
                str(pagina),
                "2026-08-20",
                recurso_tipo,
                rec_desc,
                float(valor),
                unidad_rec or "",
                coef_normalizado,
                formula,
                tipo_match,
                round(score, 3),
                f"Ficha FHIS {ficha_code}, pagina {pagina}, seccion {seccion}",
                f"Actividad FHIS: {best['ficha_desc']}, unidad: {unidad_actividad_fhis}",
                pdf_hash,
                f"Match score: {score:.3f}" if score < 1.0 else ""
            ))
            if cur_canon.rowcount > 0:
                inserted += 1
        except Exception as e:
            print(f"Error insertando {partida_id} {rec_codigo}: {e}")
            errors += 1

con_canon.commit()
con_canon.close()
con_fhis.close()

print(f"Insertados: {inserted}")
print(f"Errores: {errors}")

# Verificar
con = sqlite3.connect(r'D:\EstimaStruct\data\estimacion.db')
cur = con.cursor()
cur.execute("SELECT COUNT(*) FROM rendimiento_audit")
print(f"Total en rendimiento_audit: {cur.fetchone()[0]}")
cur.execute("SELECT fuente, recurso_tipo, COUNT(*) FROM rendimiento_audit GROUP BY fuente, recurso_tipo")
for r in cur.fetchall():
    print(f"  {r[0]} {r[1]}: {r[2]}")
con.close()