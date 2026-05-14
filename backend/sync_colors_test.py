"""Copia color_tipo desde el Template a las partidas del proyecto 'test',
emparejando por clave_csi."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from db import SessionLocal
from models import Presupuesto, Capitulo, Partida

db = SessionLocal()
try:
    obra = db.query(Presupuesto).filter(Presupuesto.nombre == 'test').first()
    template = db.query(Presupuesto).filter(Presupuesto.es_template == True).first()
    if not obra or not template:
        print("Falta obra 'test' o template")
        sys.exit(1)

    tpl_partidas = db.query(Partida).join(Capitulo).filter(
        Capitulo.presupuesto_id == template.id
    ).all()
    tpl_map = {p.clave_csi: p.color_tipo or 'blanco' for p in tpl_partidas}
    print(f"Template: {len(tpl_map)} partidas")

    obra_partidas = db.query(Partida).join(Capitulo).filter(
        Capitulo.presupuesto_id == obra.id
    ).all()
    print(f"Test: {len(obra_partidas)} partidas")

    counts = {'blanco':0,'rosa':0,'amarillo':0,'verde':0,'azul':0}
    matched = 0
    no_match = []
    for p in obra_partidas:
        color = tpl_map.get(p.clave_csi)
        if color is None:
            no_match.append(p.clave_csi)
            color = 'rosa'  # sin contraparte en template -> sin asignar
        p.color_tipo = color
        counts[color] = counts.get(color, 0) + 1
        matched += 1 if p.clave_csi in tpl_map else 0

    db.commit()
    print(f"\nActualizadas: {len(obra_partidas)} | Match con template: {matched}")
    print("Distribucion final:", counts)
    if no_match:
        print(f"Sin match en template ({len(no_match)}): {no_match[:15]}")
finally:
    db.close()
