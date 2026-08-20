#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sqlite3

con = sqlite3.connect(r'D:\EstimaStruct\data\estimacion.db')
cur = con.cursor()

cur.execute('SELECT COUNT(*) FROM rendimiento_audit')
print('Total audit records:', cur.fetchone()[0])

cur.execute('SELECT fuente, COUNT(DISTINCT partida_id) as act, COUNT(*) as rend FROM rendimiento_audit GROUP BY fuente')
for r in cur.fetchall():
    print(f'  {r[0]}: {r[1]} act, {r[2]} rend')

cur.execute('SELECT tipo_match, COUNT(*) FROM rendimiento_audit GROUP BY tipo_match')
for r in cur.fetchall():
    print(f'  {r[0]}: {r[1]}')

cur.execute('''
    SELECT 
        CASE WHEN tipo_match IN ("exacto","semantico") THEN "AUDITADO" ELSE "REVISION_MANUAL" END as estado, 
        COUNT(*) 
    FROM rendimiento_audit 
    GROUP BY estado
''')
for r in cur.fetchall():
    print(f'  estado {r[0]}: {r[1]}')

# Verify unique constraint
cur.execute('''
    SELECT partida_id, fuente, recurso_tipo, fuente_codigo, fecha_consulta, COUNT(*) as cnt
    FROM rendimiento_audit
    GROUP BY partida_id, fuente, recurso_tipo, fuente_codigo, fecha_consulta
    HAVING cnt > 1
''')
dups = cur.fetchall()
print(f'Duplicates (should be 0): {len(dups)}')

con.close()