"""Limpia _x000D_ y \\r de descripciones en partidas e insumos (one-shot)."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from db import SessionLocal
from models import Partida, InsumoPartida, Capitulo

def clean(s):
    if s is None:
        return s
    return s.replace('_x000D_', '').replace('\r', '').strip()

db = SessionLocal()
try:
    n_p = n_i = n_c = 0
    for p in db.query(Partida).all():
        for f in ('descripcion','formula_ref','type_mark','omniclass_num','assembly_num'):
            v = getattr(p, f, None)
            if v and ('_x000D_' in v or '\r' in v):
                setattr(p, f, clean(v)); n_p += 1
    for i in db.query(InsumoPartida).all():
        for f in ('descripcion','clave','unidad'):
            v = getattr(i, f, None)
            if v and ('_x000D_' in v or '\r' in v):
                setattr(i, f, clean(v)); n_i += 1
    for c in db.query(Capitulo).all():
        v = c.nombre
        if v and ('_x000D_' in v or '\r' in v):
            c.nombre = clean(v); n_c += 1
    db.commit()
    print(f"Partidas limpiadas: {n_p} | Insumos: {n_i} | Capitulos: {n_c}")
finally:
    db.close()
