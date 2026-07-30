from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
import sys, os
from backend.db import get_db
from backend.models import Presupuesto, Capitulo, Partida, ConfigPresupuesto, InsumoPartida
from decimal import Decimal
from backend.services.pricing import recalcular_partida, rebucket_insumos, quantize_money, calc_base

router = APIRouter(tags=["calculos"])


def _recalcular_todo(p: Presupuesto, db: Session):
    cfg = p.config
    sobrecosto = float(cfg.sobrecosto) if cfg and cfg.sobrecosto is not None else 20.0

    base_total = 0.0
    for cap in p.capitulos:
        for partida in cap.partidas:
            for ins in partida.insumos:
                cant = float(ins.cantidad or 0)
                cu = float(ins.costo_unit or 0)
                nuevo = quantize_money(Decimal(str(cant)) * Decimal(str(cu)))
                if float(ins.total or 0) != nuevo:   # skip-unchanged: evita UPDATE inutil (6759 insumos)
                    ins.total = nuevo
            if partida.insumos:
                mo_total, ma_total, otros_total = rebucket_insumos(partida.insumos)
                partida.costo_mo = mo_total
                partida.costo_ma = ma_total
                partida.unitario_matriz = otros_total

            recalcular_partida(partida, sobrecosto)
            base_total += float(partida.cantidad or 0) * float(partida.costo_base)

    return base_total


def _factor_indirectos(cfg: ConfigPresupuesto) -> float:
    if not cfg:
        return 1.0
    # El sobrecosto ya incluye IVA y cualquier margen adicional del negocio.
    return 1 + float(cfg.sobrecosto or 0) / 100


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
    total_real = 0.0
    capitulos_out = []
    for cap in p.capitulos:
        cap_directo = sum(float(pa.cantidad or 0) * calc_base(pa.costo_mo, pa.costo_ma, pa.unitario_matriz) for pa in cap.partidas)
        cap_total = sum(float(pa.total or 0) for pa in cap.partidas)  # partida.total YA incluye sobrecosto (pricing.recalcular_partida)
        costo_directo += cap_directo
        total_real += cap_total
        capitulos_out.append({"clave": cap.clave, "nombre": cap.nombre, "costo_directo": cap_directo, "total": cap_total})

    indirectos_detalle = {}
    if cfg:
        pct = float(cfg.sobrecosto or 0)
        indirectos_detalle["sobrecosto"] = {"pct": pct, "monto": costo_directo * pct / 100}

    return {
        "nombre": p.nombre,
        "moneda": p.moneda,
        "sobrecosto": sobrecosto,
        "costo_directo": costo_directo,
        "total_con_indirectos": total_real,
        "indirectos": indirectos_detalle,
        "capitulos": capitulos_out,
    }
