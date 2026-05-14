from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import get_db
from models import InsumoPartida, Partida, Recurso, Capitulo, ConfigPresupuesto

router = APIRouter(tags=["insumos"])

TIPO_LABEL = {
    "MATERIAL": "MA", "MANO_OBRA": "MO", "EQUIPO": "EQ",
    "SUBCONTRATO": "SC", "HERRAMIENTA": "HER", "DISEÑO": "DIS", "FLETE": "FL",
}


class InsumoIn(BaseModel):
    recurso_id: str
    cantidad: float = 1.0


class InsumoUpdate(BaseModel):
    cantidad: Optional[float] = None
    descripcion: Optional[str] = None
    unidad: Optional[str] = None
    costo_unit: Optional[float] = None


def _get_sobrecosto(partida: Partida, db: Session) -> float:
    cfg = db.query(ConfigPresupuesto).filter(
        ConfigPresupuesto.presupuesto_id ==
        db.query(Capitulo).get(partida.capitulo_id).presupuesto_id
    ).first()
    return float(cfg.sobrecosto) if cfg and cfg.sobrecosto is not None else 20.0


def _recalcular_partida(partida: Partida, db: Session):
    """Recalcula costo_mo, costo_ma, unitario_matriz, costo_base, PU, total desde insumos."""
    insumos = db.query(InsumoPartida).filter(InsumoPartida.partida_id == partida.id).all()
    mo = sum(float(i.total) for i in insumos if i.tipo == "MANO_OBRA")
    ma = sum(float(i.total) for i in insumos if i.tipo == "MATERIAL")
    otros = sum(float(i.total) for i in insumos if i.tipo not in ("MANO_OBRA", "MATERIAL"))
    partida.costo_mo = mo
    partida.costo_ma = ma
    partida.unitario_matriz = otros
    partida.costo_base = mo + ma + otros
    sc = _get_sobrecosto(partida, db)
    partida.precio_unitario = float(partida.costo_base) * (1 + sc / 100)
    partida.total = float(partida.cantidad or 0) * float(partida.precio_unitario)


def _insumo_dict(i: InsumoPartida):
    return {
        "id": i.id,
        "recurso_id": i.recurso_id,
        "clave": i.clave,
        "descripcion": i.descripcion,
        "unidad": i.unidad,
        "tipo": i.tipo,
        "tipo_label": TIPO_LABEL.get(i.tipo, i.tipo),
        "cantidad": float(i.cantidad),
        "costo_unit": float(i.costo_unit),
        "total": float(i.total),
        "orden": i.orden,
    }


@router.get("/partidas/{pid}/insumos")
def listar(pid: str, db: Session = Depends(get_db)):
    p = db.query(Partida).get(pid)
    if not p:
        raise HTTPException(404, "Partida no encontrada")
    insumos = db.query(InsumoPartida).filter(
        InsumoPartida.partida_id == pid
    ).order_by(InsumoPartida.orden).all()
    items = [_insumo_dict(i) for i in insumos]

    # Totales por tipo
    totales = {}
    for i in insumos:
        totales[i.tipo] = totales.get(i.tipo, 0) + float(i.total)
    total_todos = sum(totales.values())

    return {
        "insumos": items,
        "totales": totales,
        "total_todos": total_todos,
        "partida": {
            "costo_mo": float(p.costo_mo or 0),
            "costo_ma": float(p.costo_ma or 0),
            "unitario_matriz": float(p.unitario_matriz or 0),
            "costo_base": float(p.costo_base or 0),
            "precio_unitario": float(p.precio_unitario or 0),
            "total": float(p.total or 0),
        }
    }


@router.post("/partidas/{pid}/insumos", status_code=201)
def agregar(pid: str, data: InsumoIn, db: Session = Depends(get_db)):
    p = db.query(Partida).get(pid)
    if not p:
        raise HTTPException(404, "Partida no encontrada")
    r = db.query(Recurso).get(data.recurso_id)
    if not r:
        raise HTTPException(404, "Recurso no encontrado")

    orden = db.query(InsumoPartida).filter(InsumoPartida.partida_id == pid).count()
    total = float(data.cantidad) * float(r.precio_unitario)

    ins = InsumoPartida(
        partida_id=pid,
        recurso_id=r.id,
        clave=r.clave,
        descripcion=r.descripcion,
        unidad=r.unidad,
        tipo=r.tipo,
        cantidad=data.cantidad,
        costo_unit=float(r.precio_unitario),
        total=total,
        orden=orden,
    )
    db.add(ins)
    db.flush()
    _recalcular_partida(p, db)
    db.commit()
    return {**_insumo_dict(ins), "partida_actualizada": {
        "costo_mo": float(p.costo_mo), "costo_ma": float(p.costo_ma),
        "costo_base": float(p.costo_base), "precio_unitario": float(p.precio_unitario),
        "total": float(p.total),
    }}


@router.patch("/insumos/{iid}")
def actualizar(iid: str, data: InsumoUpdate, db: Session = Depends(get_db)):
    ins = db.query(InsumoPartida).get(iid)
    if not ins:
        raise HTTPException(404, "Insumo no encontrado")
    if data.cantidad is not None:
        ins.cantidad = data.cantidad
    if data.costo_unit is not None:
        ins.costo_unit = data.costo_unit
    if data.descripcion is not None:
        ins.descripcion = data.descripcion
    if data.unidad is not None:
        ins.unidad = data.unidad
    ins.total = float(ins.cantidad or 0) * float(ins.costo_unit or 0)
    p = db.query(Partida).get(ins.partida_id)
    _recalcular_partida(p, db)
    db.commit()
    return {**_insumo_dict(ins), "partida_actualizada": {
        "costo_mo": float(p.costo_mo), "costo_ma": float(p.costo_ma),
        "costo_base": float(p.costo_base), "precio_unitario": float(p.precio_unitario),
        "total": float(p.total),
    }}


@router.delete("/insumos/{iid}", status_code=204)
def eliminar(iid: str, db: Session = Depends(get_db)):
    ins = db.query(InsumoPartida).get(iid)
    if not ins:
        raise HTTPException(404, "Insumo no encontrado")
    pid = ins.partida_id
    db.delete(ins)
    db.flush()
    p = db.query(Partida).get(pid)
    _recalcular_partida(p, db)
    db.commit()
