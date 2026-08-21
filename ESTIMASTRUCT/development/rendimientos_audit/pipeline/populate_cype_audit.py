#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Inserta rendimientos CYPE Honduras en rendimiento_audit (estimacion.db).
Fuente: cype_rendimientos_browser.json (extraccion browser goal-21170).
Idempotente via INSERT OR IGNORE. No toca tablas de precios.
"""
import sqlite3, json, hashlib, re
from datetime import date

BROWSER_JSON = r'D:\GitHub\EstimBot\ConsuConstructEstimBot\ESTIMASTRUCT\development\rendimientos_audit\pipeline\data\cype_rendimientos_browser.json'
CANON_DB     = r'D:\EstimaStruct\data\estimacion.db'
HOY          = date.today().isoformat()

# Hash del JSON de origen para trazabilidad
src_hash = hashlib.sha256(open(BROWSER_JSON, 'rb').read()).hexdigest()

# Mapa semantico: patron de descripcion EstimaStruct -> lista de cype_codes candidatos
# Solo match explicito basado en tipo de trabajo; confianza ajustada manualmente
CROSSWALK = [
    # (patron_regex_en_descripcion_partida, [cype_codes], confianza, tipo_match)
    (r'zapata.*concreto.*(reforzado|armado)|concreto.*(reforzado|armado).*zapata',
     ['CSZ010'], 0.7, 'semantico'),
    (r'zapata.*concreto simple|zapata.*masa',
     ['CSZ015'], 0.7, 'semantico'),
    (r'encofrado.*zapata|zapata.*encofrado',
     ['CSZ020'], 0.75, 'semantico'),
    (r'placa de cimiento|losa de cimentac|placa.*ciment',
     ['CSL010'], 0.75, 'semantico'),
    (r'encofrado.*placa.*ciment|encofrado.*losa.*ciment',
     ['CSL020'], 0.75, 'semantico'),
    (r'losa maciza|losa.*(concreto|hormigon).*(reforzado|armado)',
     ['EHL010'], 0.7, 'semantico'),
    (r'columna.*(concreto|hormigon).*(reforzado|armado)|columna.*(rectangular|cuadrada)',
     ['EHS010'], 0.7, 'semantico'),
    (r'encofrado.*columna|columna.*encofrado',
     ['EHS012'], 0.7, 'semantico'),
    (r'viga.*(concreto|hormigon).*(reforzado|armado)|viga.*(rectangular)',
     ['EHV010'], 0.7, 'semantico'),
    (r'encofrado.*viga|viga.*encofrado',
     ['EHV011'], 0.7, 'semantico'),
    # encofrado perimetral losa -> EHV011 como aproximacion
    (r'encofrado.*losa|encofrado.*perimetral',
     ['EHV011'], 0.5, 'semantico'),
    # armado refuerzos / acero en columna -> EHS010 (incluye acero)
    (r'armado.*encofrado.*fundido.*columna|columna.*armado.*encofrado',
     ['EHS010'], 0.6, 'semantico'),
    # armado encofrado fundido zapata -> CSZ010
    (r'armado.*encofrado.*fundido.*zapata|zapata.*armado.*encofrado',
     ['CSZ010'], 0.65, 'semantico'),
]

with open(BROWSER_JSON, encoding='utf-8') as f:
    cype_units = {u['cype_code']: u for u in json.load(f)}

con = sqlite3.connect(CANON_DB)
cur = con.cursor()

# Cargar partidas con insumos de mano_obra / equipo
cur.execute("""
SELECT DISTINCT p.id, p.clave_csi, p.descripcion, p.unidad
FROM partida p
""")
partidas = cur.fetchall()

inserted = 0
skipped_already = 0
skipped_no_match = 0

for p_id, clave_csi, p_desc, p_unidad in partidas:
    desc_lower = p_desc.lower() if p_desc else ''
    matched_codes = []
    for patron, codes, confianza, tipo_match in CROSSWALK:
        if re.search(patron, desc_lower, re.IGNORECASE):
            for code in codes:
                matched_codes.append((code, confianza, tipo_match))
            break  # primer patron que matchea

    if not matched_codes:
        skipped_no_match += 1
        continue

    for cype_code, confianza, tipo_match in matched_codes:
        unit = cype_units.get(cype_code)
        if not unit:
            continue
        for rend in unit['rendimientos']:
            # Unidad nativa del coeficiente: "h/m³" -> normalizada = coeficiente (h por unidad obra)
            coef = float(rend['coeficiente'])
            unidad_nat = rend.get('unidad', '')
            formula = f"{coef} {unidad_nat} (CYPE HN, proyecto referencia)"
            evidencia = (f"CYPE {cype_code}: {unit['titulo'][:60]}, "
                         f"recurso: {rend['descripcion'][:40]}")
            notas = (f"CYPE contextual: rendimiento para proyecto de referencia HN. "
                     f"Match con '{p_desc[:50]}' por patron semantico.")

            try:
                cur.execute("""
                    INSERT OR IGNORE INTO rendimiento_audit
                    (partida_id, partida_clave_csi, partida_descripcion, partida_unidad,
                     fuente, fuente_edicion, fuente_codigo, fuente_url, fuente_pagina,
                     fecha_consulta, recurso_tipo, recurso_descripcion,
                     coeficiente_nativo, unidad_nativa, coeficiente_normalizado,
                     formula_conversion, tipo_match, confianza, evidencia,
                     condiciones_alcance, hash_insumo, notas_discrepancia)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    p_id, clave_csi, p_desc, p_unidad,
                    'CYPE_HN',
                    'Generador de Precios Honduras 2026 (proyecto referencia)',
                    cype_code,
                    unit['url'],
                    'online',
                    HOY,
                    rend['tipo'].upper(),
                    rend['descripcion'],
                    coef,
                    unidad_nat,
                    coef,
                    formula,
                    tipo_match,
                    round(confianza, 3),
                    evidencia,
                    'Proyecto de referencia CYPE HN; rendimientos contextuales, no universales.',
                    src_hash,
                    notas,
                ))
                if cur.rowcount > 0:
                    inserted += 1
                else:
                    skipped_already += 1
            except Exception as e:
                print(f"ERROR {p_id} {cype_code}: {e}")

con.commit()
con.close()

print(f"Insertados CYPE:    {inserted}")
print(f"Ya existian:        {skipped_already}")
print(f"Sin match patron:   {skipped_no_match}")

# Verificar totales
con = sqlite3.connect(CANON_DB)
cur = con.cursor()
cur.execute("SELECT fuente, recurso_tipo, COUNT(*) FROM rendimiento_audit GROUP BY fuente, recurso_tipo ORDER BY fuente, recurso_tipo")
print("\nEstado rendimiento_audit por fuente:")
for r in cur.fetchall():
    print(f"  {r[0]:15} {r[1]:12} {r[2]:4}")
cur.execute("SELECT COUNT(*) FROM rendimiento_audit")
print(f"TOTAL: {cur.fetchone()[0]}")
con.close()
