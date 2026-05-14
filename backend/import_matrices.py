# MIGRATION TOOL — Solo para import inicial desde Excel/OPUS.
# No usar en operación normal. Fuente activa: estimacion.db
import openpyxl
from sqlalchemy.orm import Session
from db import get_db, engine, Base
from models import Presupuesto, Capitulo, Partida, InsumoPartida, Recurso
from decimal import Decimal

TIPO_MAP = {
    'DIS': 'DISEÑO',
    'SC': 'SUBCONTRATO',
    'MO': 'MANO_OBRA',
    'MA': 'MATERIAL',
    'EQ': 'EQUIPO',
    'HER': 'HERRAMIENTA',
    'FL': 'FLETE',
}

def get_tipo_from_clave(clave):
    """Obtener tipo de recurso de la clave"""
    if not clave:
        return 'MATERIAL'
    prefix = clave.split('-')[0].upper()
    return TIPO_MAP.get(prefix, 'MATERIAL')

def parse_excel(file_path):
    """Parsear el archivo Excel y extraer matrices y recursos"""
    wb = openpyxl.load_workbook(file_path)
    ws = wb.active

    matrices = []
    current_matrix = None

    for i, row in enumerate(ws.iter_rows(values_only=True), 1):
        if i == 1:  # Encabezado
            continue

        # Verificar si es una matriz (columna 1 es un CSI)
        if row[0] and isinstance(row[0], str) and ' ' in row[0] and row[0][0].isdigit():
            # Es una matriz
            if current_matrix:
                matrices.append(current_matrix)

            current_matrix = {
                'csi': row[0],
                'clave': row[1],
                'descripcion': row[2],
                'unidad': row[3],
                'cantidad': row[4] or 0,
                'mo_unit': row[8] or 0,
                'ma_unit': row[9] or 0,
                'recursos': []
            }

        # Encabezado de recursos
        elif row[0] == 'C':
            continue

        # Recurso
        elif row[0] == 'Simple' and current_matrix:
            recurso = {
                'clave': row[1],
                'descripcion': row[2],
                'unidad': row[3],
                'rendimiento': row[4] or 0,
                'costo_unit': row[5] or 0,
                'total': row[6] or 0,
            }
            current_matrix['recursos'].append(recurso)

    if current_matrix:
        matrices.append(current_matrix)

    return matrices

def import_matrices(presupuesto_id, file_path):
    """Importar matrices a la BD"""
    db = next(get_db())
    try:
        # Obtener presupuesto
        presupuesto = db.query(Presupuesto).filter(Presupuesto.id == presupuesto_id).first()
        if not presupuesto:
            print(f"Presupuesto {presupuesto_id} no encontrado")
            return False

        # Parsear Excel
        matrices = parse_excel(file_path)
        print(f"Se encontraron {len(matrices)} matrices")

        imported = 0
        for matrix in matrices:
            # Buscar partida por CSI
            csi = matrix['csi']
            partida = db.query(Partida).filter(Partida.clave_csi == csi).first()

            if not partida:
                print(f"Partida {csi} no encontrada, creando...")
                # Obtener o crear capítulo
                cap_code = csi.split()[0]
                capitulo = db.query(Capitulo).filter(
                    Capitulo.presupuesto_id == presupuesto_id,
                    Capitulo.clave == cap_code
                ).first()

                if not capitulo:
                    from models import DIVISIONES_CSI
                    cap_name = DIVISIONES_CSI.get(cap_code, f"Capítulo {cap_code}")
                    capitulo = Capitulo(
                        presupuesto_id=presupuesto_id,
                        clave=cap_code,
                        nombre=cap_name,
                        orden=0
                    )
                    db.add(capitulo)
                    db.flush()

                partida = Partida(
                    capitulo_id=capitulo.id,
                    clave_csi=csi,
                    descripcion=matrix['descripcion'],
                    unidad=matrix['unidad'],
                    cantidad=Decimal(str(matrix['cantidad'])),
                    costo_mo=Decimal('0'),
                    costo_ma=Decimal('0'),
                    unitario_matriz=Decimal('0'),
                    costo_base=Decimal('0'),
                    precio_unitario=Decimal('0'),
                    total=Decimal('0'),
                    orden=0
                )
                db.add(partida)
                db.flush()

            # Limpiar insumos anteriores
            db.query(InsumoPartida).filter(InsumoPartida.partida_id == partida.id).delete()

            # Agregar recursos como insumos
            mo_total = Decimal('0')
            ma_total = Decimal('0')

            for i, recurso in enumerate(matrix['recursos'], 1):
                clave = recurso['clave']
                tipo = get_tipo_from_clave(clave)

                # Buscar recurso en BD
                res_obj = db.query(Recurso).filter(Recurso.clave == clave).first()
                recurso_id = res_obj.id if res_obj else None

                insumo = InsumoPartida(
                    partida_id=partida.id,
                    recurso_id=recurso_id,
                    clave=clave,
                    descripcion=recurso['descripcion'],
                    unidad=recurso['unidad'],
                    tipo=tipo,
                    cantidad=Decimal(str(recurso['rendimiento'])),
                    costo_unit=Decimal(str(recurso['costo_unit'])),
                    total=Decimal(str(recurso['total'])),
                    orden=i
                )
                db.add(insumo)

                # Sumar MO y MA
                if tipo == 'MANO_OBRA':
                    mo_total += Decimal(str(recurso['total']))
                else:
                    ma_total += Decimal(str(recurso['total']))

            # Actualizar totales de partida
            partida.costo_mo = mo_total
            partida.costo_ma = ma_total
            partida.unitario_matriz = Decimal('0')
            partida.costo_base = mo_total + ma_total
            partida.precio_unitario = partida.costo_base

            if partida.cantidad > 0:
                partida.total = partida.costo_base * partida.cantidad

            db.commit()
            imported += 1
            print(f"✓ {csi} - {matrix['descripcion'][:50]}")

        print(f"\nImportación completada: {imported} partidas actualizadas")
        return True

    except Exception as e:
        print(f"Error en importación: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Uso: python import_matrices.py <presupuesto_id> [archivo_excel]")
        sys.exit(1)

    presupuesto_id = sys.argv[1]
    file_path = sys.argv[2] if len(sys.argv) > 2 else r"D:\OneDrive\Bots\Estimbot\MasterFiles\INPUTS\FULL_breakdown\MatricesImport.xlsx"

    success = import_matrices(presupuesto_id, file_path)
    sys.exit(0 if success else 1)
