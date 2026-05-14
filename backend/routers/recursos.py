from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import get_db
from models import Recurso

router = APIRouter(prefix="/recursos", tags=["recursos"])


class RecursoIn(BaseModel):
    clave: str
    descripcion: str
    unidad: str
    tipo: str
    precio_unitario: float = 0


class RecursoOut(BaseModel):
    id: str
    clave: str
    descripcion: str
    unidad: str
    tipo: str
    precio_unitario: float

    class Config:
        from_attributes = True


@router.get("", response_model=list[RecursoOut])
def listar(
    tipo: Optional[str] = None,
    q: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Recurso)
    if tipo:
        query = query.filter(Recurso.tipo == tipo.upper())
    if q:
        query = query.filter(
            or_(Recurso.clave.ilike(f"%{q}%"), Recurso.descripcion.ilike(f"%{q}%"))
        )
    return query.order_by(Recurso.clave).all()


@router.post("", response_model=RecursoOut, status_code=201)
def crear(data: RecursoIn, db: Session = Depends(get_db)):
    if db.query(Recurso).filter(Recurso.clave == data.clave).first():
        raise HTTPException(400, f"Clave '{data.clave}' ya existe")
    r = Recurso(**data.model_dump())
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


@router.put("/{rid}", response_model=RecursoOut)
def actualizar(rid: str, data: RecursoIn, db: Session = Depends(get_db)):
    r = db.query(Recurso).get(rid)
    if not r:
        raise HTTPException(404, "Recurso no encontrado")
    for k, v in data.model_dump().items():
        setattr(r, k, v)
    r.ultima_actualizacion = datetime.utcnow()
    db.commit()
    db.refresh(r)
    return r


@router.patch("/{rid}/unidad")
def actualizar_unidad(rid: str, data: dict, db: Session = Depends(get_db)):
    r = db.query(Recurso).get(rid)
    if not r:
        raise HTTPException(404, "Recurso no encontrado")
    r.unidad = str(data.get("unidad", r.unidad))
    r.ultima_actualizacion = datetime.utcnow()
    db.commit()
    return {"id": r.id, "clave": r.clave, "unidad": r.unidad}


@router.patch("/{rid}/precio")
def actualizar_precio(rid: str, data: dict, db: Session = Depends(get_db)):
    r = db.query(Recurso).get(rid)
    if not r:
        raise HTTPException(404, "Recurso no encontrado")
    precio = float(data.get("precio_unitario", 0))
    r.precio_unitario = precio
    r.ultima_actualizacion = datetime.utcnow()
    db.commit()
    return {"id": r.id, "clave": r.clave, "precio_unitario": float(r.precio_unitario)}


@router.delete("/{rid}", status_code=204)
def eliminar(rid: str, db: Session = Depends(get_db)):
    r = db.query(Recurso).get(rid)
    if not r:
        raise HTTPException(404, "Recurso no encontrado")
    db.delete(r)
    db.commit()
