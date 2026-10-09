"""
Router: Obra Media — evidencia de obra (fotos/videos/planos/renders)
=====================================================================
Ver backend/models.py::ObraMediaItem para el contexto completo de la
decisión de arquitectura (David 2026-09-17).

REGLA DE ORO: este router NUNCA sube binarios ni toca credenciales de
Cloudflare. Los archivos viven en un bucket R2 que sube/administra
projectmanager_bot. Este endpoint solo registra la REFERENCIA (bucket +
object_key + metadata) DESPUÉS de que pmbot confirma la subida.

Contrato con projectmanager_bot (Opción B, decidida 2026-09-17):
  1. pmbot sube el binario a R2.
  2. pmbot llama POST /obra-media/{pid}/items con bucket+object_key+tipo.
  3. Este endpoint valida que pid exista y NUNCA toca Partida/precios.

Endpoints:
  GET    /obra-media/{pid}/items            (lista, filtro opcional ?tipo=)
  POST   /obra-media/{pid}/items            (pmbot registra tras subir a R2)
  DELETE /obra-media/items/{item_id}        (soft delete real — activo=False)
  GET    /obra-media/tipos                  (catálogo de categorías válidas)
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, field_validator
from typing import Optional, List
from datetime import datetime, date

from backend.db import get_db
from backend.models import Presupuesto, ObraMediaItem, TIPOS_OBRA_MEDIA

router = APIRouter(prefix="/obra-media", tags=["obra-media"])


# ─────────────────────────────────────────────────────────────────────────────
# SCHEMAS
# ─────────────────────────────────────────────────────────────────────────────

class ItemCreate(BaseModel):
    tipo:          str = "FOTO"
    nombre:        str
    descripcion:   str = ""
    bucket:        str
    object_key:    str
    url_publica:   Optional[str] = None
    tamano_bytes:  Optional[int] = None
    mime_type:     Optional[str] = None
    subido_por:    str = "projectmanager_bot"
    fecha_obra:    Optional[date] = None
    etiqueta_zona: str = ""

    @field_validator("tipo")
    @classmethod
    def _validar_tipo(cls, v):
        if v not in TIPOS_OBRA_MEDIA:
            raise ValueError(f"tipo inválido: {v}. Debe ser uno de {TIPOS_OBRA_MEDIA}")
        return v


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _item_to_dict(it: ObraMediaItem) -> dict:
    return {
        "id":             it.id,
        "presupuesto_id": it.presupuesto_id,
        "tipo":           it.tipo,
        "nombre":         it.nombre,
        "descripcion":    it.descripcion or "",
        "bucket":         it.bucket,
        "object_key":     it.object_key,
        "url_publica":    it.url_publica,
        "tamano_bytes":   it.tamano_bytes,
        "mime_type":      it.mime_type,
        "subido_por":     it.subido_por,
        "fecha_obra":     it.fecha_obra.isoformat() if it.fecha_obra else None,
        "etiqueta_zona":  it.etiqueta_zona or "",
        "activo":         bool(it.activo),
        "created_at":     it.created_at.isoformat() if it.created_at else None,
    }


def _get_presupuesto_or_404(pid: str, db: Session) -> Presupuesto:
    """Scoping obligatorio: cada endpoint valida que el presupuesto exista
    ANTES de tocar obra_media_item — nunca se listan/crean items huérfanos
    ni se filtra por otra cosa que no sea presupuesto_id exacto."""
    p = db.query(Presupuesto).filter(Presupuesto.id == pid).first()
    if not p:
        raise HTTPException(404, f"Presupuesto {pid} no existe")
    return p


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/tipos")
def catalogo_tipos():
    """Catálogo de categorías válidas — usado por el frontend para pintar
    el menú de botones (Fotos / Videos / Planos / Renders / Otro)."""
    return {"tipos": list(TIPOS_OBRA_MEDIA)}


@router.get("/{pid}/items")
def listar_items(pid: str, tipo: Optional[str] = None, db: Session = Depends(get_db)):
    _get_presupuesto_or_404(pid, db)

    q = db.query(ObraMediaItem).filter(
        ObraMediaItem.presupuesto_id == pid,
        ObraMediaItem.activo == True,  # noqa: E712
    )
    if tipo:
        if tipo not in TIPOS_OBRA_MEDIA:
            raise HTTPException(400, f"tipo inválido: {tipo}. Debe ser uno de {TIPOS_OBRA_MEDIA}")
        q = q.filter(ObraMediaItem.tipo == tipo)

    items = q.order_by(ObraMediaItem.created_at.desc()).all()
    return {
        "presupuesto_id": pid,
        "total": len(items),
        "items": [_item_to_dict(it) for it in items],
    }


@router.post("/{pid}/items")
def crear_item(pid: str, body: ItemCreate, db: Session = Depends(get_db)):
    """Registra la REFERENCIA de un archivo ya subido a R2 por
    projectmanager_bot. No sube nada, no valida contra el bucket real
    (pmbot es responsable de esa parte) — solo persiste la metadata."""
    _get_presupuesto_or_404(pid, db)

    item = ObraMediaItem(
        presupuesto_id=pid,
        tipo=body.tipo,
        nombre=body.nombre,
        descripcion=body.descripcion,
        bucket=body.bucket,
        object_key=body.object_key,
        url_publica=body.url_publica,
        tamano_bytes=body.tamano_bytes,
        mime_type=body.mime_type,
        subido_por=body.subido_por,
        fecha_obra=body.fecha_obra,
        etiqueta_zona=body.etiqueta_zona,
        activo=True,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _item_to_dict(item)


@router.delete("/items/{item_id}")
def borrar_item(item_id: str, db: Session = Depends(get_db)):
    """Soft delete real — nunca DELETE duro (mismo criterio de auditoría
    que financiero_item: la referencia queda, solo se desactiva)."""
    item = db.query(ObraMediaItem).filter(ObraMediaItem.id == item_id).first()
    if not item:
        raise HTTPException(404, f"Item {item_id} no existe")
    item.activo = False
    item.updated_at = datetime.utcnow()
    db.commit()
    return {"status": "ok", "id": item_id, "activo": False}
