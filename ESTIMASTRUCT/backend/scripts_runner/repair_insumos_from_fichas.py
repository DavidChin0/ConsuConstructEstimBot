"""Repara insumos mezclados (MO+MA en un solo insumo) de un presupuesto creado
desde template, re-expandiendo la descomposicion desde las fichas canonicas
(regeneradas desde Postgres) y resolviendo precio/tipo contra `recurso`.

Sintoma que repara (bug 2026-10-02): insumos con clave='' tipo MATERIAL
costo_unit=0 y partida.costo_ma = PU de ficha (con markup), costo_mo = 0.

Solo toca partidas afectadas. Conserva cantidad, color, type_mark, orden.
Recalcula todo el presupuesto con la misma ruta de /calcular.

Uso (desde ESTIMASTRUCT/, con ESTIMASTRUCT_DATABASE_URL apuntando a Postgres):
  python -m backend.scripts_runner.repair_insumos_from_fichas <presupuesto_id> [v1.3] [--apply]
Sin --apply = dry-run (rollback).
"""
import sys, re
from sqlalchemy.orm import joinedload
from backend.db import SessionLocal
from backend.models import Presupuesto, Capitulo, Partida, InsumoPartida, Recurso
from backend.routers.presupuestos import _load_fichas_from_json, _normalizar_insumo
from backend.routers.calculos import _recalcular_todo


def _norm(s):
    return " ".join((s or "").replace("_x000D_", "").split()).lower()


def main(pid, version="v1.3", apply=False):
    db = SessionLocal()
    try:
        fichas = _load_fichas_from_json(version)
        by_tm, by_desc, by_csi = {}, {}, {}
        for f in fichas:
            if f.get("codigo"):
                by_tm.setdefault((f["csi"], f["codigo"]), f)
            by_desc.setdefault((f["csi"], _norm(f.get("descripcion"))), f)
            by_csi.setdefault(f["csi"], f)
        recursos = {r.clave: r for r in db.query(Recurso).all()}

        p = db.query(Presupuesto).options(
            joinedload(Presupuesto.config),
            joinedload(Presupuesto.capitulos).joinedload(Capitulo.partidas).joinedload(Partida.insumos),
        ).filter(Presupuesto.id == pid).first()
        if not p:
            raise SystemExit(f"Presupuesto {pid} no existe")

        antes = sum(float(pa.total or 0) for c in p.capitulos for pa in c.partidas)
        rep, sin_ficha = 0, []
        for cap in p.capitulos:
            for pa in cap.partidas:
                if not any((i.clave or "") == "" and float(i.costo_unit or 0) == 0 for i in pa.insumos):
                    continue
                f = (by_tm.get((pa.clave_csi, pa.type_mark)) or
                     by_desc.get((pa.clave_csi, _norm(pa.descripcion))) or
                     by_csi.get(pa.clave_csi))
                if not f or not f.get("insumos"):
                    sin_ficha.append((pa.clave_csi, pa.descripcion[:50]))
                    continue
                for ins in list(pa.insumos):
                    db.delete(ins)
                db.flush()
                for idx, raw in enumerate(f["insumos"]):
                    n = _normalizar_insumo(raw, recursos)
                    db.add(InsumoPartida(partida_id=pa.id, recurso_id=n.recurso_id, clave=n.clave,
                                         descripcion=n.descripcion, unidad=n.unidad, tipo=n.tipo,
                                         cantidad=n.cantidad, costo_unit=n.costo_unit, total=n.total,
                                         orden=idx))
                rep += 1
        db.flush()
        db.expire_all()
        p = db.query(Presupuesto).options(
            joinedload(Presupuesto.config),
            joinedload(Presupuesto.capitulos).joinedload(Capitulo.partidas)
                .joinedload(Partida.insumos).joinedload(InsumoPartida.recurso),
        ).filter(Presupuesto.id == pid).first()
        cd = _recalcular_todo(p, db)
        despues = sum(float(pa.total or 0) for c in p.capitulos for pa in c.partidas)
        quedan = sum(1 for c in p.capitulos for pa in c.partidas for i in pa.insumos
                     if (i.clave or "") == "" and float(i.costo_unit or 0) == 0)
        print(f"{p.nombre}\n  partidas reparadas: {rep}\n  sin ficha: {len(sin_ficha)} {sin_ficha[:10]}")
        print(f"  insumos rotos restantes: {quedan}")
        print(f"  total partidas antes: {antes:,.2f}  despues: {despues:,.2f}  costo_directo: {cd:,.2f}")
        if apply:
            db.commit(); print("  APLICADO (commit)")
        else:
            db.rollback(); print("  DRY-RUN (rollback) — usar --apply")
    finally:
        db.close()


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__); sys.exit(1)
    main(args[0], args[1] if len(args) > 1 else "v1.3", "--apply" in sys.argv)
