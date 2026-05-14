from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import get_db
from models import Capitulo, Partida, ConfigPresupuesto, DIVISIONES_CSI, InsumoPartida
from csi_utils import infer_csi, is_valid_csi

router = APIRouter(tags=["partidas"])


class PartidaIn(BaseModel):
    clave_csi: str
    descripcion: str
    unidad: str
    cantidad: float = 0
    costo_mo: float = 0
    costo_ma: float = 0
    unitario_matriz: float = 0
    orden: int = 0


class CantidadIn(BaseModel):
    cantidad: float


class RevitQIn(BaseModel):
    revit_q: float


class FactoresIn(BaseModel):
    factor_e: Optional[float] = None
    factor_f: Optional[float] = None
    color_tipo: Optional[str] = None


class NuevaActividadIn(BaseModel):
    presupuesto_id: str
    clave_csi: Optional[str] = ""
    descripcion: str
    unidad: str


class UnidadIn(BaseModel):
    unidad: str


class DescripcionIn(BaseModel):
    descripcion: str


class TypeMarkIn(BaseModel):
    type_mark: Optional[str] = None


class ColorIn(BaseModel):
    color_tipo: str

_VALID_COLORS = {"amarillo", "verde", "azul", "rosa", "blanco"}


class ClaveCsiIn(BaseModel):
    clave_csi: str


def _safe_factor(v, default=1.0):
    f = float(v or default)
    return f if f else default


def _calcular_partida(partida: Partida, sobrecosto: float):
    base = float(partida.costo_mo or 0) + float(partida.costo_ma or 0) + float(partida.unitario_matriz or 0)
    partida.costo_base = base
    partida.precio_unitario = base * (1 + sobrecosto / 100)
    partida.total = float(partida.cantidad or 0) * float(partida.precio_unitario)


def _get_sobrecosto(capitulo_id: str, db: Session) -> float:
    cap = db.query(Capitulo).get(capitulo_id)
    if not cap:
        return 20.0
    cfg = db.query(ConfigPresupuesto).filter(
        ConfigPresupuesto.presupuesto_id == cap.presupuesto_id
    ).first()
    return float(cfg.sobrecosto) if cfg and cfg.sobrecosto is not None else 20.0


@router.get("/capitulos/{cid}/partidas")
def listar(cid: str, db: Session = Depends(get_db)):
    parts = db.query(Partida).filter(Partida.capitulo_id == cid).order_by(Partida.orden).all()
    return [_partida_dict(p) for p in parts]


@router.post("/capitulos/{cid}/partidas", status_code=201)
def crear(cid: str, data: PartidaIn, db: Session = Depends(get_db)):
    if not db.query(Capitulo).get(cid):
        raise HTTPException(404, "Capitulo no encontrado")
    sobrecosto = _get_sobrecosto(cid, db)
    base = data.costo_mo + data.costo_ma + data.unitario_matriz
    pu = base * (1 + sobrecosto / 100)
    p = Partida(
        capitulo_id=cid,
        clave_csi=data.clave_csi,
        descripcion=data.descripcion,
        unidad=data.unidad,
        cantidad=data.cantidad,
        costo_mo=data.costo_mo,
        costo_ma=data.costo_ma,
        unitario_matriz=data.unitario_matriz,
        costo_base=base,
        precio_unitario=pu,
        total=data.cantidad * pu,
        orden=data.orden,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return {"id": p.id}


@router.put("/partidas/{pid}")
def actualizar(pid: str, data: PartidaIn, db: Session = Depends(get_db)):
    p = db.query(Partida).get(pid)
    if not p:
        raise HTTPException(404, "Partida no encontrada")
    sobrecosto = _get_sobrecosto(p.capitulo_id, db)
    p.clave_csi = data.clave_csi
    p.descripcion = data.descripcion
    p.unidad = data.unidad
    p.cantidad = data.cantidad
    p.costo_mo = data.costo_mo
    p.costo_ma = data.costo_ma
    p.unitario_matriz = data.unitario_matriz
    _calcular_partida(p, sobrecosto)
    db.commit()
    return {"ok": True}


@router.patch("/partidas/{pid}/cantidad")
def actualizar_cantidad(pid: str, data: CantidadIn, db: Session = Depends(get_db)):
    p = db.query(Partida).get(pid)
    if not p:
        raise HTTPException(404, "Partida no encontrada")
    p.cantidad = data.cantidad
    p.revit_q = data.cantidad  # sync
    sobrecosto = _get_sobrecosto(p.capitulo_id, db)
    _calcular_partida(p, sobrecosto)
    db.commit()
    return {"id": p.id, "cantidad": float(p.cantidad), "total": float(p.total)}


@router.patch("/partidas/{pid}/revit-q")
def actualizar_revit_q(pid: str, data: RevitQIn, db: Session = Depends(get_db)):
    p = db.query(Partida).get(pid)
    if not p:
        raise HTTPException(404, "Partida no encontrada")
    p.revit_q = data.revit_q
    fe = _safe_factor(p.factor_e)
    ff = _safe_factor(p.factor_f)
    p.cantidad = data.revit_q * fe * ff
    sobrecosto = _get_sobrecosto(p.capitulo_id, db)
    _calcular_partida(p, sobrecosto)
    db.commit()
    return {
        "id": p.id,
        "revit_q": float(p.revit_q),
        "cantidad": float(p.cantidad),
        "total": float(p.total),
    }


@router.patch("/partidas/{pid}/factores")
def actualizar_factores(pid: str, data: FactoresIn, db: Session = Depends(get_db)):
    p = db.query(Partida).get(pid)
    if not p:
        raise HTTPException(404, "Partida no encontrada")
    if data.factor_e is not None:
        p.factor_e = data.factor_e
    if data.factor_f is not None:
        p.factor_f = data.factor_f
    if data.color_tipo is not None:
        p.color_tipo = data.color_tipo
    # recalcular cantidad con nuevos factores
    fe = _safe_factor(p.factor_e)
    ff = _safe_factor(p.factor_f)
    rq = float(p.revit_q or 0)
    p.cantidad = rq * fe * ff
    sobrecosto = _get_sobrecosto(p.capitulo_id, db)
    _calcular_partida(p, sobrecosto)
    db.commit()
    return {
        "id": p.id,
        "factor_e": float(p.factor_e),
        "factor_f": float(p.factor_f),
        "color_tipo": p.color_tipo,
        "cantidad": float(p.cantidad),
        "total": float(p.total),
    }


@router.post("/partidas/nueva-actividad", status_code=201)
def nueva_actividad(data: NuevaActividadIn, db: Session = Depends(get_db)):
    from models import Presupuesto
    if not db.query(Presupuesto).get(data.presupuesto_id):
        raise HTTPException(404, "Presupuesto no encontrado")

    clave = (data.clave_csi or "").strip()

    # Si no es un código CSI válido (ej. es un type mark o viene vacío), inferir
    if not is_valid_csi(clave):
        clave = infer_csi(clave, data.descripcion) or "00 00 00"

    # Detectar división CSI
    div = clave[:2]
    if not div.isdigit():
        div = "00"

    # Buscar capítulo existente o crear uno nuevo
    cap = db.query(Capitulo).filter(
        Capitulo.presupuesto_id == data.presupuesto_id,
        Capitulo.clave == div
    ).first()

    if not cap:
        nombre_div = DIVISIONES_CSI.get(div, f"División {div}")
        max_ord = db.query(Capitulo).filter(
            Capitulo.presupuesto_id == data.presupuesto_id
        ).count()
        cap = Capitulo(
            presupuesto_id=data.presupuesto_id,
            clave=div,
            nombre=nombre_div,
            orden=max_ord,
        )
        db.add(cap)
        db.flush()

    max_ord = db.query(Partida).filter(Partida.capitulo_id == cap.id).count()
    sobrecosto = _get_sobrecosto(cap.id, db)

    p = Partida(
        capitulo_id=cap.id,
        clave_csi=clave,
        descripcion=data.descripcion,
        unidad=data.unidad,
        cantidad=0,
        revit_q=0,
        factor_e=1.0,
        factor_f=1.0,
        color_tipo='blanco',
        es_formula=False,
        costo_mo=0, costo_ma=0, unitario_matriz=0,
        costo_base=0, precio_unitario=0, total=0,
        orden=max_ord,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return {
        "id": p.id,
        "capitulo_id": cap.id,
        "capitulo_clave": cap.clave,
        "capitulo_nombre": cap.nombre,
        "clave_csi_asignada": clave,
        "es_nuevo_capitulo": False,
    }


@router.patch("/partidas/{pid}/unidad")
def actualizar_unidad(pid: str, data: UnidadIn, db: Session = Depends(get_db)):
    p = db.query(Partida).get(pid)
    if not p:
        raise HTTPException(404, "Partida no encontrada")
    p.unidad = data.unidad
    db.commit()
    return {"id": p.id, "unidad": p.unidad}


@router.patch("/partidas/{pid}/descripcion")
def actualizar_descripcion(pid: str, data: DescripcionIn, db: Session = Depends(get_db)):
    p = db.query(Partida).get(pid)
    if not p:
        raise HTTPException(404, "Partida no encontrada")
    p.descripcion = data.descripcion.replace('_x000D_', '').replace('\r', '').strip()
    db.commit()
    return {"id": p.id, "descripcion": p.descripcion}


@router.patch("/partidas/{pid}/clave-csi")
def actualizar_clave_csi(pid: str, data: ClaveCsiIn, db: Session = Depends(get_db)):
    p = db.query(Partida).get(pid)
    if not p:
        raise HTTPException(404, "Partida no encontrada")
    nuevo = (data.clave_csi or "").strip()
    if not nuevo:
        raise HTTPException(400, "CSI vacío")
    p.clave_csi = nuevo
    db.commit()
    return {"id": p.id, "clave_csi": p.clave_csi}


@router.patch("/partidas/{pid}/type-mark")
def actualizar_type_mark(pid: str, data: TypeMarkIn, db: Session = Depends(get_db)):
    p = db.query(Partida).get(pid)
    if not p:
        raise HTTPException(404, "Partida no encontrada")
    p.type_mark = (data.type_mark or '').strip() or None
    db.commit()
    return {"id": p.id, "type_mark": p.type_mark}


@router.patch("/partidas/{pid}/color")
def actualizar_color(pid: str, data: ColorIn, db: Session = Depends(get_db)):
    if data.color_tipo not in _VALID_COLORS:
        raise HTTPException(400, f"color_tipo inválido: {data.color_tipo}")
    p = db.query(Partida).get(pid)
    if not p:
        raise HTTPException(404, "Partida no encontrada")
    p.color_tipo = data.color_tipo
    db.commit()
    return {"id": p.id, "color_tipo": p.color_tipo}


@router.get("/unidades")
def listar_unidades(db: Session = Depends(get_db)):
    """Devuelve todas las unidades distintas usadas en partidas e insumos."""
    p_unidades = {u[0] for u in db.query(Partida.unidad).distinct().all() if u[0]}
    i_unidades = {u[0] for u in db.query(InsumoPartida.unidad).distinct().all() if u[0]}
    todas = sorted(p_unidades | i_unidades, key=lambda s: s.lower())
    return {"unidades": todas}


@router.delete("/partidas/{pid}", status_code=204)
def eliminar(pid: str, db: Session = Depends(get_db)):
    p = db.query(Partida).get(pid)
    if not p:
        raise HTTPException(404, "Partida no encontrada")
    db.delete(p)
    db.commit()


def _partida_dict(p: Partida):
    return {
        "id": p.id,
        "clave_csi": p.clave_csi,
        "type_mark": p.type_mark or "",
        "descripcion": p.descripcion,
        "unidad": p.unidad,
        "revit_q": float(p.revit_q or 0),
        "factor_e": float(p.factor_e or 1),
        "factor_f": float(p.factor_f or 1),
        "color_tipo": p.color_tipo or 'blanco',
        "cantidad": float(p.cantidad or 0),
        "costo_mo": float(p.costo_mo or 0),
        "costo_ma": float(p.costo_ma or 0),
        "unitario_matriz": float(p.unitario_matriz or 0),
        "costo_base": float(p.costo_base or 0),
        "precio_unitario": float(p.precio_unitario or 0),
        "total": float(p.total or 0),
        "es_formula": bool(p.es_formula),
        "formula_ref": p.formula_ref,
        "type_mark": p.type_mark,
        "orden": p.orden,
    }
