#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Generar salida final obligatoria: CSV y Markdown 'rendimientos_auditados'
con columnas: actividad | unidad_actividad | recurso | rendimiento | unidad_rendimiento | fuente | referencia_online | pagina_ficha | confianza | estado
"""
import sqlite3
import csv
import os

DB = r"D:\EstimaStruct\data\estimacion.db"
OUT_DIR = r"D:\GitHub\EstimBot\ConsuConstructEstimBot\ESTIMASTRUCT\development\rendimientos_audit\pipeline\data"
OUT_CSV = os.path.join(OUT_DIR, "rendimientos_auditados.csv")
OUT_MD = os.path.join(OUT_DIR, "rendimientos_auditados.md")

con = sqlite3.connect(DB)
cur = con.cursor()

# Get all audit records with partida info
cur.execute("""
    SELECT 
        ra.partida_id,
        ra.partida_clave_csi,
        ra.partida_descripcion,
        ra.partida_unidad,
        ra.fuente,
        ra.fuente_codigo,
        ra.fuente_url,
        ra.fuente_pagina,
        ra.recurso_tipo,
        ra.recurso_descripcion,
        ra.coeficiente_normalizado,
        ra.unidad_nativa,
        ra.confianza,
        ra.tipo_match,
        ra.evidencia
    FROM rendimiento_audit ra
    ORDER BY ra.fuente, ra.partida_clave_csi, ra.recurso_tipo
""")
rows = cur.fetchall()

# Write CSV
csv_rows = []
for r in rows:
    partida_id, clave_csi, desc, unidad, fuente, fuente_codigo, fuente_url, fuente_pagina, recurso_tipo, recurso_desc, coef_norm, unidad_nativa, confianza, tipo_match, evidencia = r
    
    # Actividad: use CSI code + description
    actividad = f"{clave_csi} - {desc}"
    
    # Recurso: combine tipo and description
    recurso = f"{recurso_tipo}: {recurso_desc}"
    
    # Rendimiento: the normalized coefficient
    rendimiento = coef_norm
    
    # Unidad rendimiento
    unidad_rendimiento = unidad_nativa
    
    # Referencia online
    referencia_online = fuente_url
    
    # Pagina/ficha
    pagina_ficha = f"{fuente_codigo or ''} - {fuente_pagina or ''}".strip(" -")
    
    # Confianza
    conf = confianza
    
    # Estado
    estado = "AUDITADO" if tipo_match in ("exacto", "semantico") else "REVISION_MANUAL"
    
    csv_rows.append({
        'actividad': actividad,
        'unidad_actividad': unidad,
        'recurso': recurso,
        'rendimiento': rendimiento,
        'unidad_rendimiento': unidad_rendimiento,
        'fuente': fuente,
        'referencia_online': referencia_online,
        'pagina_ficha': pagina_ficha,
        'confianza': conf,
        'estado': estado
    })

# Write CSV
cols = ['actividad', 'unidad_actividad', 'recurso', 'rendimiento', 'unidad_rendimiento', 
        'fuente', 'referencia_online', 'pagina_ficha', 'confianza', 'estado']
with open(OUT_CSV, 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.DictWriter(f, fieldnames=cols)
    w.writeheader()
    w.writerows(csv_rows)

print(f"CSV escrito: {OUT_CSV} ({len(csv_rows)} filas)")

# Write Markdown
with open(OUT_MD, 'w', encoding='utf-8') as f:
    f.write("# Rendimientos Auditados - Goal 21170\n\n")
    f.write(f"Generado: 2026-08-20\n")
    f.write(f"Total registros: {len(csv_rows)}\n\n")
    
    # Summary by source
    f.write("## Resumen por Fuente\n\n")
    from collections import Counter
    src_counts = Counter(r['fuente'] for r in csv_rows)
    for src, cnt in src_counts.items():
        f.write(f"- **{src}**: {cnt} registros\n")
    
    f.write("\n## Resumen por Recurso\n\n")
    rec_counts = Counter(r['recurso'].split(':')[0] for r in csv_rows)
    for rec, cnt in rec_counts.items():
        f.write(f"- **{rec}**: {cnt} registros\n")
    
    f.write("\n## Resumen por Capítulo CSI (división mayor)\n\n")
    cap_counts = Counter(r['actividad'].split()[0][:2] for r in csv_rows)
    for cap, cnt in sorted(cap_counts.items()):
        f.write(f"- **{cap}**: {cnt} registros\n")
    
    f.write("\n## Tabla Completa\n\n")
    # Write header
    f.write("| " + " | ".join(cols) + " |\n")
    f.write("| " + " | ".join(["---"] * len(cols)) + " |\n")
    for r in csv_rows:
        vals = [str(r[c]).replace("|", "\\|")[:100] for c in cols]
        f.write("| " + " | ".join(vals) + " |\n")

print(f"Markdown escrito: {OUT_MD}")

# Also create coverage summary and not-found log
print("\n=== COBERTURA ===")
cur.execute("""
    SELECT fuente, COUNT(DISTINCT partida_id) as actividades, COUNT(*) as rendimientos
    FROM rendimiento_audit
    GROUP BY fuente
""")
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1]} actividades, {r[2]} rendimientos")

cur.execute("""
    SELECT partida_clave_csi, COUNT(DISTINCT partida_id) as act, COUNT(*) as rend
    FROM rendimiento_audit
    GROUP BY partida_clave_csi
    ORDER BY act DESC
""")
print("\n=== POR CAPITULO CSI ===")
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1]} act, {r[2]} rend")

con.close()