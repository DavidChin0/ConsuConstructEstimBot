"""
Router: Financiero — cédula de indirectos auditable
=====================================================
Ver backend/calculo_financiero.py para el contexto de negocio completo.

Endpoints:
  GET    /financiero/{pid}/items
  POST   /financiero/{pid}/items
  PUT    /financiero/items/{item_id}
  DELETE /financiero/items/{item_id}   (soft delete real — ver nota abajo)
  POST   /financiero/{pid}/calcular
  POST   /financiero/{pid}/memoria-rapida
  GET    /financiero/{pid}/historial
  GET    /financiero/catalogo-icms
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel, model_validator
from typing import Optional, List
from datetime import datetime
import json
import uuid

from backend.db import get_db
from backend.models import (
    Presupuesto, Capitulo, Partida, ConfigPresupuesto,
    FinancieroItem, FinancieroCalculo,
    TIPOS_FINANCIERO_ITEM, BASES_CALCULO_FINANCIERO,
)
from backend.calculo_financiero import calcular_indirectos, CATALOGO_ICMS_REFERENCIA

router = APIRouter(prefix="/financiero", tags=["financiero"])


# ─────────────────────────────────────────────────────────────────────────────
# SCHEMAS
# ─────────────────────────────────────────────────────────────────────────────

class ItemCreate(BaseModel):
    categoria_icms: str = ""
    tipo:           str = "OTRO"
    nombre:         str
    base_calculo:   str = "COSTO_DIRECTO"
    porcentaje:     Optional[float] = None
    monto_fijo:     Optional[float] = None
    orden:          int = 0
    obligatorio:    bool = False
    evidencia:      str = ""
    activo:         bool = True

    @model_validator(mode="after")
    def _validar(self):
        if self.tipo not in TIPOS_FINANCIERO_ITEM:
            raise ValueError(f"tipo inválido: {self.tipo}. Debe ser uno de {TIPOS_FINANCIERO_ITEM}")
        if self.base_calculo not in BASES_CALCULO_FINANCIERO:
            raise ValueError(f"base_calculo inválido: {self.base_calculo}. Debe ser uno de {BASES_CALCULO_FINANCIERO}")
        if self.base_calculo == "MONTO_FIJO":
            if self.porcentaje is not None:
                raise ValueError("porcentaje debe ser None cuando base_calculo=MONTO_FIJO")
        else:
            if self.monto_fijo is not None:
                raise ValueError("monto_fijo debe ser None salvo que base_calculo=MONTO_FIJO")
        return self


class ItemUpdate(BaseModel):
    categoria_icms: Optional[str]   = None
    tipo:           Optional[str]   = None
    nombre:         Optional[str]   = None
    base_calculo:   Optional[str]   = None
    porcentaje:     Optional[float] = None
    monto_fijo:     Optional[float] = None
    orden:          Optional[int]   = None
    obligatorio:    Optional[bool]  = None
    evidencia:      Optional[str]   = None
    activo:         Optional[bool]  = None


class ItemOverride(BaseModel):
    """Item completo para simulación en /memoria-rapida (sin persistir)."""
    id:             Optional[str] = None
    categoria_icms: str = ""
    tipo:           str = "OTRO"
    nombre:         str = ""
    base_calculo:   str = "COSTO_DIRECTO"
    porcentaje:     Optional[float] = None
    monto_fijo:     Optional[float] = None
    orden:          int = 0
    obligatorio:    bool = False
    evidencia:      str = ""


class MemoriaRapidaBody(BaseModel):
    costo_directo: Optional[float] = None
    iva_pct:       Optional[float] = None
    items:         Optional[List[ItemOverride]] = None


class CalcularBody(BaseModel):
    nota: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _item_to_dict(it: FinancieroItem) -> dict:
    return {
        "id":             it.id,
        "presupuesto_id": it.presupuesto_id,
        "categoria_icms": it.categoria_icms or "",
        "tipo":           it.tipo,
        "nombre":         it.nombre,
        "base_calculo":   it.base_calculo,
        "porcentaje":     float(it.porcentaje) if it.porcentaje is not None else None,
        "monto_fijo":     float(it.monto_fijo) if it.monto_fijo is not None else None,
        "orden":          it.orden,
        "obligatorio":    bool(it.obligatorio),
        "evidencia":      it.evidencia or "",
        "activo":         bool(it.activo),
        "created_at":     it.created_at.isoformat() if it.created_at else None,
        "updated_at":     it.updated_at.isoformat() if it.updated_at else None,
    }


def _item_to_motor_dict(it) -> dict:
    """Acepta FinancieroItem ORM o ItemOverride Pydantic."""
    if isinstance(it, FinancieroItem):
        return _item_to_dict(it)
    d = it.model_dump()
    d.setdefault("id", None)
    return d


def _costo_directo_real(pid: str, db: Session) -> float:
    """Misma query que presupuestos.py::listar (agregado SQL, no ORM loop)."""
    row = (
        db.query(
            func.coalesce(func.sum(
                func.coalesce(Partida.cantidad, 0) * (
                    func.coalesce(Partida.costo_mo, 0) +
                    func.coalesce(Partida.costo_ma, 0) +
                    func.coalesce(Partida.unitario_matriz, 0)
                )
            ), 0),
        )
        .select_from(Partida)
        .join(Capitulo, Capitulo.id == Partida.capitulo_id)
        .filter(Capitulo.presupuesto_id == pid)
        .scalar()
    )
    return float(row or 0)


def _iva_pct_default(pid: str, db: Session) -> float:
    cfg = db.query(ConfigPresupuesto).filter(ConfigPresupuesto.presupuesto_id == pid).first()
    if cfg and cfg.iva is not None:
        return float(cfg.iva)
    return 15.0


def sembrar_items_default(presupuesto_id: str, db: Session):
    """Siembra los 3 financiero_item default al crear un presupuesto nuevo:
    Administración, Utilidad, Imprevistos (obligatorio, activo, porcentaje=0).
    Seguros/Fianzas (08.110) NO se siembran — no toda obra lleva póliza; el
    usuario los agrega manualmente desde el catálogo ICMS si aplica.
    Sin commit — el caller decide cuándo confirmar la transacción."""
    defaults = [
        dict(categoria_icms="08.010", tipo="ADMINISTRACION", nombre="Administración",
             base_calculo="COSTO_DIRECTO", porcentaje=0, orden=1, obligatorio=False),
        dict(categoria_icms="", tipo="UTILIDAD", nombre="Utilidad",
             base_calculo="SUBTOTAL_ACUMULADO", porcentaje=0, orden=2, obligatorio=False),
        dict(categoria_icms="09.020", tipo="IMPREVISTO", nombre="Imprevistos de obra",
             base_calculo="SUBTOTAL_ACUMULADO", porcentaje=0, orden=3, obligatorio=True),
    ]
    for d in defaults:
        db.add(FinancieroItem(id=str(uuid.uuid4()), presupuesto_id=presupuesto_id, activo=True, **d))


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/catalogo-icms")
def catalogo_icms():
    """Catálogo ICMS de referencia (RICS ICMS 3rd ed.) para tooltip/select del frontend."""
    return {"catalogo": CATALOGO_ICMS_REFERENCIA}


@router.get("/{pid}/items")
def listar_items(pid: str, db: Session = Depends(get_db)):
    pres = db.query(Presupuesto).filter(Presupuesto.id == pid).first()
    if not pres:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")
    items = db.query(FinancieroItem).filter(
        FinancieroItem.presupuesto_id == pid
    ).order_by(FinancieroItem.orden).all()
    return {"presupuesto_id": pid, "total": len(items), "items": [_item_to_dict(i) for i in items]}


@router.post("/{pid}/items", status_code=201)
def crear_item(pid: str, data: ItemCreate, db: Session = Depends(get_db)):
    pres = db.query(Presupuesto).filter(Presupuesto.id == pid).first()
    if not pres:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")
    item = FinancieroItem(id=str(uuid.uuid4()), presupuesto_id=pid, **data.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return _item_to_dict(item)


@router.put("/items/{item_id}")
def actualizar_item(item_id: str, data: ItemUpdate, db: Session = Depends(get_db)):
    item = db.query(FinancieroItem).filter(FinancieroItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item no encontrado")

    payload = data.model_dump(exclude_none=True)
    tipo = payload.get("tipo", item.tipo)
    base_calculo = payload.get("base_calculo", item.base_calculo)
    if tipo not in TIPOS_FINANCIERO_ITEM:
        raise HTTPException(status_code=422, detail=f"tipo inválido: {tipo}")
    if base_calculo not in BASES_CALCULO_FINANCIERO:
        raise HTTPException(status_code=422, detail=f"base_calculo inválido: {base_calculo}")

    for field, value in payload.items():
        setattr(item, field, value)

    # Si cambia a MONTO_FIJO, limpiar porcentaje (y viceversa) — consistencia.
    if item.base_calculo == "MONTO_FIJO":
        item.porcentaje = None
    else:
        item.monto_fijo = None

    item.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(item)
    return _item_to_dict(item)


@router.delete("/items/{item_id}")
def eliminar_item(item_id: str, db: Session = Depends(get_db)):
    """Soft delete SIEMPRE: no hay FK directa entre financiero_calculo.items_json
    (serializado) y financiero_item, así que no hay forma de saber por FK si un
    item ya fue usado en un cálculo histórico. Un auditor fiscal esperaría que
    un indirecto que alguna vez formó parte de una cédula nunca desaparezca del
    catálogo — se desactiva (`activo=False`), nunca DELETE físico."""
    item = db.query(FinancieroItem).filter(FinancieroItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item no encontrado")
    item.activo = False
    item.updated_at = datetime.utcnow()
    db.commit()
    return {"status": "desactivado", "id": item_id, "activo": False}


@router.post("/{pid}/calcular")
def calcular_y_guardar(pid: str, body: CalcularBody = CalcularBody(), db: Session = Depends(get_db)):
    """Calcula la cédula con los items ACTIVOS reales y PERSISTE un nuevo
    financiero_calculo (snapshot inmutable — nunca hace UPDATE de uno viejo)."""
    pres = db.query(Presupuesto).filter(Presupuesto.id == pid).first()
    if not pres:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")

    items = db.query(FinancieroItem).filter(
        FinancieroItem.presupuesto_id == pid, FinancieroItem.activo == True   # noqa: E712
    ).order_by(FinancieroItem.orden).all()

    costo_directo = _costo_directo_real(pid, db)
    iva_pct = _iva_pct_default(pid, db)

    res = calcular_indirectos(costo_directo, iva_pct, [_item_to_dict(i) for i in items])

    calc = FinancieroCalculo(
        id=str(uuid.uuid4()), presupuesto_id=pid,
        costo_directo=res["costo_directo"], iva_pct=iva_pct,
        items_json=json.dumps(res["items_aplicados"], ensure_ascii=False),
        subtotal_antes_iva=res["subtotal_antes_iva"],
        iva_monto=res["iva_monto"], total_general=res["total_general"],
        nota=body.nota or "",
    )
    db.add(calc)
    db.commit()
    db.refresh(calc)

    return {
        "id":                  calc.id,
        "presupuesto_id":      pid,
        "costo_directo":       res["costo_directo"],
        "iva_pct":             iva_pct,
        "subtotal_antes_iva":  res["subtotal_antes_iva"],
        "iva_monto":           res["iva_monto"],
        "total_general":       res["total_general"],
        "memoria":             res["memoria"],
        "advertencias":        res["advertencias"],
        "cuadra":              res["cuadra"],
        "generado_at":         calc.generado_at.isoformat() if calc.generado_at else None,
        "nota":                calc.nota,
    }


@router.post("/{pid}/memoria-rapida")
def memoria_rapida(pid: str, body: MemoriaRapidaBody = MemoriaRapidaBody(), db: Session = Depends(get_db)):
    """Stateless: para la Hoja en vivo. NO persiste nada. Si `items` no viene,
    usa los financiero_item activos reales del presupuesto (permite simular
    "qué pasa si subo imprevistos a 10%" sin guardar, mandando `items` con el
    override completo)."""
    pres = db.query(Presupuesto).filter(Presupuesto.id == pid).first()
    if not pres:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")

    if body.items is not None:
        items = [_item_to_motor_dict(i) for i in body.items]
    else:
        orm_items = db.query(FinancieroItem).filter(
            FinancieroItem.presupuesto_id == pid, FinancieroItem.activo == True   # noqa: E712
        ).order_by(FinancieroItem.orden).all()
        items = [_item_to_dict(i) for i in orm_items]

    costo_directo = body.costo_directo if body.costo_directo is not None else _costo_directo_real(pid, db)
    iva_pct = body.iva_pct if body.iva_pct is not None else _iva_pct_default(pid, db)

    try:
        res = calcular_indirectos(costo_directo, iva_pct, items)
    except ValueError as ex:
        raise HTTPException(status_code=422, detail=str(ex))

    res["presupuesto_id"] = pid
    res["iva_pct"] = iva_pct
    return res


@router.get("/{pid}/historial")
def historial(pid: str, db: Session = Depends(get_db)):
    """Cédulas históricas, más reciente primero. NUNCA se borran — libro de auditoría."""
    pres = db.query(Presupuesto).filter(Presupuesto.id == pid).first()
    if not pres:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")

    calcs = db.query(FinancieroCalculo).filter(
        FinancieroCalculo.presupuesto_id == pid
    ).order_by(FinancieroCalculo.generado_at.desc()).all()

    out = []
    for c in calcs:
        out.append({
            "id":                 c.id,
            "costo_directo":      float(c.costo_directo or 0),
            "iva_pct":            float(c.iva_pct or 0),
            "subtotal_antes_iva": float(c.subtotal_antes_iva or 0),
            "iva_monto":          float(c.iva_monto or 0),
            "total_general":      float(c.total_general or 0),
            "items":              json.loads(c.items_json or "[]"),
            "generado_at":        c.generado_at.isoformat() if c.generado_at else None,
            "nota":               c.nota or "",
        })
    return {"presupuesto_id": pid, "total": len(out), "historial": out}
