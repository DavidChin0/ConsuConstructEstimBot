from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import get_db
from models import Presupuesto, Capitulo, Partida, ConfigPresupuesto, InsumoPartida

router = APIRouter(tags=["calculos"])


def _recalcular_todo(p: Presupuesto, db: Session):
    cfg = p.config
    sobrecosto = float(cfg.sobrecosto) if cfg and cfg.sobrecosto is not None else 20.0

    costo_directo = 0.0
    for cap in p.capitulos:
        for partida in cap.partidas:
            mo_total = 0.0
            ma_total = 0.0
            for ins in partida.insumos:
                cant = float(ins.cantidad or 0)
                cu = float(ins.costo_unit or 0)
                ins.total = cant * cu
                if ins.tipo == 'MANO_OBRA':
                    mo_total += ins.total
                else:
                    ma_total += ins.total
            if partida.insumos:
                partida.costo_mo = mo_total
                partida.costo_ma = ma_total

            base = float(partida.costo_mo or 0) + float(partida.costo_ma or 0) + float(partida.unitario_matriz or 0)
            pu = base * (1 + sobrecosto / 100)
            partida.costo_base = base
            partida.precio_unitario = pu
            partida.total = float(partida.cantidad or 0) * pu
            costo_directo += partida.total

    return costo_directo


def _factor_indirectos(cfg: ConfigPresupuesto) -> float:
    if not cfg:
        return 1.0
    return 1 + (
        float(cfg.administracion or 0) +
        float(cfg.utilidad or 0) +
        float(cfg.imprevistos or 0) +
        float(cfg.iva or 0) +
        float(cfg.otros_factor or 0)
    ) / 100


@router.post("/presupuestos/{pid}/calcular")
def recalcular(pid: str, db: Session = Depends(get_db)):
    p = db.query(Presupuesto).options(
        joinedload(Presupuesto.config),
        joinedload(Presupuesto.capitulos).joinedload(Capitulo.partidas).joinedload(Partida.insumos)
    ).filter(Presupuesto.id == pid).first()
    if not p:
        raise HTTPException(404, "Presupuesto no encontrado")

    costo_directo = _recalcular_todo(p, db)
    factor = _factor_indirectos(p.config)
    db.commit()

    return {
        "costo_directo": costo_directo,
        "total_con_indirectos": costo_directo * factor,
    }


@router.get("/presupuestos/{pid}/reporte")
def reporte(pid: str, db: Session = Depends(get_db)):
    p = db.query(Presupuesto).options(
        joinedload(Presupuesto.config),
        joinedload(Presupuesto.capitulos).joinedload(Capitulo.partidas)
    ).filter(Presupuesto.id == pid).first()
    if not p:
        raise HTTPException(404, "Presupuesto no encontrado")

    cfg = p.config
    sobrecosto = float(cfg.sobrecosto) if cfg and cfg.sobrecosto is not None else 20.0

    costo_directo = 0.0
    capitulos_out = []
    for cap in p.capitulos:
        cap_total = sum(float(pa.total or 0) for pa in cap.partidas)
        costo_directo += cap_total
        capitulos_out.append({"clave": cap.clave, "nombre": cap.nombre, "total": cap_total})

    indirectos_detalle = {}
    factor = 1.0
    if cfg:
        for campo in ("administracion", "utilidad", "imprevistos", "iva", "otros_factor"):
            pct = float(getattr(cfg, campo) or 0)
            indirectos_detalle[campo] = {"pct": pct, "monto": costo_directo * pct / 100}
            factor += pct / 100

    return {
        "nombre": p.nombre,
        "moneda": p.moneda,
        "sobrecosto": sobrecosto,
        "costo_directo": costo_directo,
        "total_con_indirectos": costo_directo * factor,
        "indirectos": indirectos_detalle,
        "capitulos": capitulos_out,
    }
