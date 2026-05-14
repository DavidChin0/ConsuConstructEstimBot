#!/usr/bin/env python3
"""
Importar Opus Export Full.xlsx a ESTIMASTRUCT DB
Convierte 277 matrices + 5000+ recursos a SQLite
"""

import json
import sqlite3
from datetime import datetime

# Rutas
OPUS_JSON = r"D:\OneDrive\Desktop\My Brain\ConsuConstruct\03 automation projects\ESTIMASTRUCT\OPUS_RECURSOS_EXTRAIDO.json"
DB_PATH = r"D:\OneDrive\Bots\ESTIMASTRUCT\estimastruct.db"

# Mapear códigos recurso a tipo (deducir de prefijo)
def get_tipo_recurso(codigo):
    if codigo.startswith('MA-'):
        return 'MA'
    elif codigo.startswith('MO-'):
        return 'MO'
    elif codigo.startswith('EQ-'):
        return 'EQ'
    elif codigo.startswith('SC-'):
        return 'SC'
    elif codigo.startswith('HER-'):
        return 'HER'
    elif codigo.startswith('DIS-'):
        return 'DIS'
    elif codigo.startswith('FL-'):
        return 'FL'
    else:
        return 'OTR'

def import_opus():
    """Importar matrices y recursos a ESTIMASTRUCT"""

    # Cargar JSON
    print("Leyendo OPUS_RECURSOS_EXTRAIDO.json...")
    with open(OPUS_JSON, 'r', encoding='utf-8') as f:
        matrices = json.load(f)

    # Conectar DB
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    total_matrices = 0
    total_recursos = 0
    errores = []

    print(f"Importando {len(matrices)} matrices...")

    for clave, data in matrices.items():
        try:
            # 1. Insertar actividad (matriz)
            unidad = data.get('unidad', '')[:10] if data.get('unidad') else ''

            cursor.execute("""
                INSERT INTO actividades
                (codigo_matriz, descripcion, unidad_matriz, mo_unitario, ma_unitario, total_unitario)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                clave,
                data.get('descripcion', '')[:100],
                unidad if unidad else 'unidad',
                data.get('mo_unitario', 0),
                data.get('ma_unitario', 0),
                0  # Se calcula después
            ))

            actividad_id = cursor.lastrowid
            total_matrices += 1

            # 2. Insertar recursos
            for recurso in data.get('recursos', []):
                try:
                    tipo = get_tipo_recurso(recurso.get('codigo', ''))
                    unidad_rec = recurso.get('unidad', '')[:10] if recurso.get('unidad') else 'unidad'

                    cursor.execute("""
                        INSERT INTO recursos
                        (actividad_id, tipo_recurso, codigo, descripcion, rendimiento, unidad_recurso, precio_unitario, precio_total)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        actividad_id,
                        tipo,
                        recurso.get('codigo', '')[:20],
                        recurso.get('descripcion', '')[:200],
                        recurso.get('cantidad', 0),
                        unidad_rec,
                        recurso.get('precio_unitario', 0),
                        recurso.get('cantidad', 0) * recurso.get('precio_unitario', 0)
                    ))

                    total_recursos += 1
                except Exception as e:
                    errores.append(f"Recurso {clave}: {str(e)}")

            # Barra de progreso
            if total_matrices % 50 == 0:
                print(f"  {total_matrices}/{len(matrices)} matrices importadas...")

        except Exception as e:
            errores.append(f"Matriz {clave}: {str(e)}")

    # 3. Recalcular totales unitarios
    print("Recalculando Mo/Ma unitarios...")
    cursor.execute("""
        UPDATE actividades
        SET mo_unitario = (
            SELECT COALESCE(SUM(precio_total), 0)
            FROM recursos
            WHERE actividad_id = actividades.id
            AND tipo_recurso = 'MO'
        ),
        ma_unitario = (
            SELECT COALESCE(SUM(precio_total), 0)
            FROM recursos
            WHERE actividad_id = actividades.id
            AND tipo_recurso IN ('MA', 'EQ', 'SC', 'HER', 'DIS', 'FL', 'OTR')
        )
    """)

    cursor.execute("""
        UPDATE actividades
        SET total_unitario = mo_unitario + ma_unitario
    """)

    conn.commit()

    # 4. Log
    cursor.execute("""
        INSERT INTO importacion_log
        (total_matrices, total_recursos, archivo_origen, status, notas)
        VALUES (?, ?, ?, ?, ?)
    """, (
        total_matrices,
        total_recursos,
        'Opus Export Full.xlsx',
        'OK' if not errores else 'PARCIAL',
        f"Errores: {len(errores)}" if errores else "Sin errores"
    ))

    conn.commit()
    conn.close()

    # Resultados
    print("\n" + "="*60)
    print("IMPORTACION COMPLETADA")
    print("="*60)
    print(f"Matrices importadas: {total_matrices}")
    print(f"Recursos importados: {total_recursos}")
    print(f"Errores: {len(errores)}")
    print(f"DB: {DB_PATH}")

    if errores:
        print("\nErrores:")
        for e in errores[:10]:
            print(f"  - {e}")

    return total_matrices, total_recursos

if __name__ == '__main__':
    import_opus()
