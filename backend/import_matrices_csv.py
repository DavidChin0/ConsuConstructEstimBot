import csv
import sys
import os
from decimal import Decimal

# Agregar directorio actual al path
sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy.orm import Session
from db import SessionLocal, engine
from models import (
    Base, Presupuesto, ConfigPresupuesto, Capitulo, Partida,
    InsumoPartida, Recurso, DIVISIONES_CSI
)

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
    """Obtener tipo de recurso de la clave (prefijo)"""
    if not clave:
        return 'MATERIAL'
    prefix = clave.split('-')[0].upper()
    return TIPO_MAP.get(prefix, 'MATERIAL')

def parse_csv(file_path):
    """Parsear CSV y extraer matrices y recursos"""
    matrices = []
    current_matrix = None

    with open(file_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f, delimiter=';')
        next(reader)  # Saltar encabezado

        for row in reader:
            if not row or all(cell.strip() == '' for cell in row):
                continue

            # Fila de matriz (tiene CSI en columna 0)
            if row[0] and not row[0].startswith('C') and not row[0].startswith('Simple'):
                try:
                    # Validar que sea un CSI válido
                    if ' ' in row[0] and row[0][0].isdigit():
                        if current_matrix:
                            matrices.append(current_matrix)

                        current_matrix = {
                            'csi': row[0].strip(),
                            'clave': row[1].strip() if len(row) > 1 else '',
                            'descripcion': row[2].strip() if len(row) > 2 else '',
                            'unidad': row[3].strip() if len(row) > 3 else 'global',
                            'cantidad': float(row[4]) if len(row) > 4 and row[4].strip() else 0,
                            'recursos': []
                        }
                except (ValueError, IndexError):
                    pass

            # Fila separadora "C | Clave | ..."
            elif row[0] == 'C':
                continue

            # Fila de recurso "Simple | Clave | ..."
            elif row[0] == 'Simple' and current_matrix:
                try:
                    recurso = {
                        'clave': row[1].strip() if len(row) > 1 else '',
                        'descripcion': row[2].strip() if len(row) > 2 else '',
                        'unidad': row[3].strip() if len(row) > 3 else 'global',
                        'rendimiento': float(row[4]) if len(row) > 4 and row[4].strip() else 0,
                        'costo_unit': float(row[5]) if len(row) > 5 and row[5].strip() else 0,
                        'total': float(row[6]) if len(row) > 6 and row[6].strip() else 0,
                    }
                    current_matrix['recursos'].append(recurso)
                except (ValueError, IndexError):
                    pass

    if current_matrix:
        matrices.append(current_matrix)

    return matrices

def get_or_create_obra_test(db: Session) -> Presupuesto:
    """Buscar o crear la obra 'test'"""
    obra = db.query(Presupuesto).filter(Presupuesto.nombre == 'test').first()

    if obra:
        print(f"✓ Obra 'test' encontrada: {obra.id}")
        return obra

    print("Creando obra 'test' (clonado del template)...")

    # Obtener template
    template = db.query(Presupuesto).filter(Presupuesto.es_template == True).first()
    if not template:
        raise Exception("No hay template disponible. Ejecuta seed_bd.py primero.")

    # Crear nueva obra
    obra = Presupuesto(
        nombre='test',
        cliente='Test Client',
        moneda='HNL',
        es_template=False
    )
    db.add(obra)
    db.flush()

    # Copiar configuración del template
    if template.config:
        cfg = ConfigPresupuesto(
            presupuesto_id=obra.id,
            sobrecosto=template.config.sobrecosto,
            administracion=template.config.administracion,
            utilidad=template.config.utilidad,
            imprevistos=template.config.imprevistos,
            iva=template.config.iva,
            otros_factor=template.config.otros_factor
        )
        db.add(cfg)
        db.flush()

    print(f"✓ Obra 'test' creada: {obra.id}")
    return obra

def import_matrices(csv_file_path):
    """Importar matrices desde CSV a la obra 'test'"""
    db = SessionLocal()
    try:
        # Parsear CSV
        matrices = parse_csv(csv_file_path)
        print(f"\n✓ Se encontraron {len(matrices)} matrices en el CSV")

        # Obtener o crear obra
        obra = get_or_create_obra_test(db)

        imported = 0
        failed = 0
        partida_counter = {}  # capitulo_id -> contador de orden

        for matrix in matrices:
            try:
                csi = matrix['csi']

                # Buscar o crear capítulo
                cap_code = csi.split()[0]
                # Orden estable: usar el número del código CSI (00, 01, ... 33)
                try:
                    cap_orden = int(cap_code)
                except ValueError:
                    cap_orden = 999

                capitulo = db.query(Capitulo).filter(
                    Capitulo.presupuesto_id == obra.id,
                    Capitulo.clave == cap_code
                ).first()

                if not capitulo:
                    cap_name = DIVISIONES_CSI.get(cap_code, f"Capítulo {cap_code}")
                    capitulo = Capitulo(
                        presupuesto_id=obra.id,
                        clave=cap_code,
                        nombre=cap_name,
                        orden=cap_orden
                    )
                    db.add(capitulo)
                    db.flush()
                else:
                    # Actualizar orden si estaba en 0
                    if capitulo.orden != cap_orden:
                        capitulo.orden = cap_orden

                # Orden de partida: incremental por aparición dentro del capítulo
                partida_counter.setdefault(capitulo.id, 0)
                partida_counter[capitulo.id] += 1
                part_orden = partida_counter[capitulo.id]

                # Buscar o crear partida
                partida = db.query(Partida).filter(
                    Partida.capitulo_id == capitulo.id,
                    Partida.clave_csi == csi
                ).first()

                if not partida:
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
                        orden=part_orden
                    )
                    db.add(partida)
                    db.flush()
                else:
                    partida.orden = part_orden

                # Limpiar insumos anteriores
                db.query(InsumoPartida).filter(
                    InsumoPartida.partida_id == partida.id
                ).delete()

                # Agregar recursos como insumos
                mo_total = Decimal('0')
                ma_total = Decimal('0')

                for i, recurso in enumerate(matrix['recursos'], 1):
                    clave = recurso['clave']
                    tipo = get_tipo_from_clave(clave)

                    # Buscar recurso en catálogo
                    res_obj = db.query(Recurso).filter(
                        Recurso.clave == clave
                    ).first()
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

                imported += 1
                desc_short = matrix['descripcion'][:40]
                print(f"  ✓ {csi:12} | {desc_short}")

            except Exception as e:
                failed += 1
                print(f"  ✗ Error en {matrix['csi']}: {str(e)}")

        db.commit()

        print(f"\n{'='*60}")
        print(f"Importación completada:")
        print(f"  Partidas procesadas: {imported}")
        print(f"  Errores: {failed}")
        print(f"  Obra destino: 'test' ({obra.id})")
        print(f"{'='*60}")

        return True

    except Exception as e:
        print(f"\n❌ Error en importación: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)

    csv_file = r"D:\OneDrive\Bots\Estimbot\MasterFiles\INPUTS\FULL_breakdown\MatricesImport.csv"

    if len(sys.argv) > 1:
        csv_file = sys.argv[1]

    if not os.path.exists(csv_file):
        print(f"❌ Archivo no encontrado: {csv_file}")
        sys.exit(1)

    print(f"Importando desde: {csv_file}\n")
    success = import_matrices(csv_file)
    sys.exit(0 if success else 1)
