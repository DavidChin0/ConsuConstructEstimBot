from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from pydantic import BaseModel
from typing import Optional
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db import get_db
from models import Presupuesto, ConfigPresupuesto, Capitulo, Partida, InsumoPartida, new_uuid, DIVISIONES_CSI

router = APIRouter(prefix="/presupuestos", tags=["presupuestos"])


import re
_NUM_RX = re.compile(r"\d+|\D+")
def _csi_sort_key(pa):
    """Orden natural por CSI: '01 31 13' < '01 31 13.1' < '01 31 13.2' < '01 32 00'."""
    s = pa.clave_csi or ""
    parts = []
    for tok in _NUM_RX.findall(s):
        parts.append((0, int(tok)) if tok.isdigit() else (1, tok.lower()))
    return parts


class ConfigIn(BaseModel):
    sobrecosto: float = 20
    administracion: float = 0
    utilidad: float = 0
    imprevistos: float = 0
    iva: float = 15
    otros_factor: float = 0


class PresupuestoIn(BaseModel):
    nombre: str
    cliente: Optional[str] = None
    moneda: str = "HNL"
    config: Optional[ConfigIn] = None


class FromTemplateIn(BaseModel):
    nombre: str
    cliente: Optional[str] = None
    moneda: str = "HNL"
    config: Optional[ConfigIn] = None
    template_version: str = "v1.1"  # v1.0 o v1.1 para Template 2 - Updated


def _load_fichas_from_json(template_version: str) -> list:
    """Carga fichas desde Template 2 - Updated (v1.0 o v1.1)."""
    base_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "development", "Template2_Updated")
    )
    live_path = os.path.join(base_path, template_version, "fichas", f"fichas_{template_version}.live.json")
    json_path = os.path.join(base_path, template_version, "fichas", f"fichas_{template_version}.json")

    if os.path.exists(live_path):
        path = live_path
    elif os.path.exists(json_path):
        path = json_path
    else:
        raise HTTPException(400, f"Archivo de template {template_version} no encontrado: {json_path}")

    try:
        with open(path, 'r', encoding='utf-8') as f:
            fichas = json.load(f)
        if not isinstance(fichas, list):
            fichas = [fichas]
        return fichas
    except Exception as e:
        raise HTTPException(500, f"Error al cargar template {template_version}: {str(e)}")


def _tipo_from_clave(clave: str) -> str:
    c = clave.upper()
    if c.startswith("MO-") or c.startswith("MO."):
        return "MANO_OBRA"
    if c.startswith("HE-") or c.startswith("EQ-"):
        return "EQUIPO"
    if c.startswith("SC-") or c.startswith("SUB-"):
        return "SUBCONTRATO"
    if c.startswith("DIS-"):
        return "DISEÑO"
    return "MATERIAL"


def _create_from_template2_updated(nuevo: Presupuesto, template_version: str, sobrecosto: float, db: Session):
    """Crea capítulos y partidas a partir de Template 2 - Updated (v1.0/v1.1)."""
    try:
        fichas = _load_fichas_from_json(template_version)
    except HTTPException:
        raise

    # Ordenar fichas por división CSI (00→33) antes de procesar
    def _csi_div(f):
        csi = f.get('csi', '99')
        try:
            return int(csi[:2])
        except ValueError:
            return 99

    fichas = sorted(fichas, key=_csi_div)

    capitulos_map = {}
    orden_cap = 0
    orden_partida = {}
    for ficha in fichas:
        clave_csi = ficha.get('csi', '00')
        type_mark = ficha.get('codigo', '')
        if not type_mark:
            continue

        div = clave_csi[:2] if len(clave_csi) >= 2 else "00"
        if div not in DIVISIONES_CSI:
            div = "00"

        if div not in capitulos_map:
            cap = Capitulo(
                presupuesto_id=nuevo.id,
                clave=div,
                nombre=DIVISIONES_CSI[div],
                orden=orden_cap,
            )
            db.add(cap)
            db.flush()
            capitulos_map[div] = cap
            orden_partida[cap.id] = 0
            orden_cap += 1

        cap = capitulos_map[div]

        descripcion = (ficha.get('descripcion') or "").replace("_x000D_", "").strip()
        if not descripcion:
            descripcion = type_mark

        unidad = ficha.get('unidad', 'm2')
        costo_total = float(ficha.get('costoTotal', ficha.get('precio_unitario', 0)))

        costo_mo = 0.0
        costo_ma = 0.0
        for insumo in ficha.get('insumos', []):
            cantidad = float(insumo.get('cantidad', 0))
            precio = float(insumo.get('precioUnitario', 0))
            total_ins = cantidad * precio
            if insumo.get('codigo', '').startswith('MO-'):
                costo_mo += total_ins
            else:
                costo_ma += total_ins

        if costo_mo == 0 and costo_ma == 0:
            costo_ma = costo_total

        base = costo_mo + costo_ma
        pu = base * (1 + sobrecosto / 100) if base > 0 else 0

        partida = Partida(
            capitulo_id=cap.id,
            clave_csi=clave_csi,
            descripcion=descripcion,
            unidad=unidad,
            cantidad=0,
            revit_q=0,
            factor_e=1,
            factor_f=1,
            color_tipo=ficha.get('color_tipo', 'rosa'),
            costo_mo=costo_mo,
            costo_ma=costo_ma,
            unitario_matriz=0,
            costo_base=base,
            precio_unitario=pu,
            total=0,
            es_formula=False,
            formula_ref=None,
            type_mark=type_mark,
            omniclass_num=None,
            assembly_num=None,
            orden=orden_partida[cap.id],
        )
        db.add(partida)
        db.flush()

        for idx, insumo in enumerate(ficha.get('insumos', [])):
            clave_ins = insumo.get('codigo', '')
            cant_ins  = float(insumo.get('cantidad', 0))
            pu_ins    = float(insumo.get('precioUnitario', 0))
            db.add(InsumoPartida(
                partida_id  = partida.id,
                recurso_id  = None,
                clave       = clave_ins,
                descripcion = insumo.get('descripcion', clave_ins),
                unidad      = insumo.get('unidad', 'global'),
                tipo        = _tipo_from_clave(clave_ins),
                cantidad    = cant_ins,
                costo_unit  = pu_ins,
                total       = round(cant_ins * pu_ins, 4),
                orden       = idx,
            ))

        orden_partida[cap.id] += 1

    db.flush()


def _totales(p: Presupuesto):
    cfg = p.config
    sobrecosto = float(cfg.sobrecosto) if cfg and cfg.sobrecosto is not None else 20.0
    costo_directo = 0.0
    for cap in p.capitulos:
        for pa in cap.partidas:
            base = float(pa.costo_mo or 0) + float(pa.costo_ma or 0) + float(pa.unitario_matriz or 0)
            pu = base * (1 + sobrecosto / 100)
            costo_directo += float(pa.cantidad or 0) * pu
    factor = 1.0
    if cfg:
        factor = 1 + (
            float(cfg.administracion or 0) +
            float(cfg.utilidad or 0) +
            float(cfg.imprevistos or 0) +
            float(cfg.iva or 0) +
            float(cfg.otros_factor or 0)
        ) / 100
    return costo_directo, costo_directo * factor


@router.get("")
def listar(db: Session = Depends(get_db)):
    presupuestos = db.query(Presupuesto).options(
        joinedload(Presupuesto.config),
        joinedload(Presupuesto.capitulos).joinedload(Capitulo.partidas)
    ).order_by(Presupuesto.created_at.desc()).all()

    return [
        {
            "id": p.id,
            "nombre": p.nombre,
            "cliente": p.cliente,
            "moneda": p.moneda,
            "es_template": p.es_template,
            "fecha": str(p.fecha) if p.fecha else None,
            "costo_directo": _totales(p)[0],
            "total_con_indirectos": _totales(p)[1],
        }
        for p in presupuestos
    ]


@router.post("", status_code=201)
def crear(data: PresupuestoIn, db: Session = Depends(get_db)):
    p = Presupuesto(nombre=data.nombre, cliente=data.cliente, moneda=data.moneda)
    db.add(p)
    db.flush()
    cfg_data = data.config or ConfigIn()
    cfg = ConfigPresupuesto(presupuesto_id=p.id, **cfg_data.model_dump())
    db.add(cfg)
    db.commit()
    db.refresh(p)
    return {"id": p.id, "nombre": p.nombre}


@router.post("/from-template", status_code=201)
def crear_desde_template(data: FromTemplateIn, db: Session = Depends(get_db)):
    nuevo = Presupuesto(nombre=data.nombre, cliente=data.cliente, moneda=data.moneda)
    db.add(nuevo)
    db.flush()

    cfg_data = data.config or ConfigIn()
    template_version = data.template_version.lower().strip()

    cfg = ConfigPresupuesto(presupuesto_id=nuevo.id, template_version=template_version, **cfg_data.model_dump())
    db.add(cfg)
    db.flush()

    sobrecosto = cfg_data.sobrecosto

    # Determinar qué template usar

    # Si es v1.0 o v1.1, cargar desde Template 2 - Updated JSON
    if template_version in ["v1.0", "v1.1"]:
        _create_from_template2_updated(nuevo, template_version, sobrecosto, db)
        db.commit()
        db.refresh(nuevo)
        capitulos_count = len(nuevo.capitulos)
        return {
            "id": nuevo.id,
            "nombre": nuevo.nombre,
            "capitulos": capitulos_count,
            "template_source": f"Template 2 - Updated {template_version}"
        }

    # Fallback: usar template de BD (Template CC 2026)
    template = db.query(Presupuesto).options(
        joinedload(Presupuesto.capitulos).joinedload(Capitulo.partidas)
    ).filter(Presupuesto.es_template == True).first()

    if not template:
        raise HTTPException(404, "No existe un Template CC 2026. Corre seed_bd.py primero.")

    for cap_src in template.capitulos:
        cap_new = Capitulo(
            presupuesto_id=nuevo.id,
            clave=cap_src.clave,
            nombre=cap_src.nombre,
            orden=cap_src.orden,
        )
        db.add(cap_new)
        db.flush()

        for pa_src in cap_src.partidas:
            base = float(pa_src.costo_mo or 0) + float(pa_src.costo_ma or 0) + float(pa_src.unitario_matriz or 0)
            pu = base * (1 + sobrecosto / 100)
            pa_new = Partida(
                capitulo_id=cap_new.id,
                clave_csi=pa_src.clave_csi,
                descripcion=pa_src.descripcion,
                unidad=pa_src.unidad,
                cantidad=0,
                revit_q=0,
                factor_e=pa_src.factor_e,
                factor_f=pa_src.factor_f,
                color_tipo=pa_src.color_tipo,
                costo_mo=pa_src.costo_mo,
                costo_ma=pa_src.costo_ma,
                unitario_matriz=pa_src.unitario_matriz,
                costo_base=base,
                precio_unitario=pu,
                total=0,
                es_formula=pa_src.es_formula,
                formula_ref=pa_src.formula_ref,
                type_mark=pa_src.type_mark,
                omniclass_num=pa_src.omniclass_num,
                assembly_num=pa_src.assembly_num,
                orden=pa_src.orden,
            )
            db.add(pa_new)

    db.commit()
    db.refresh(nuevo)
    return {"id": nuevo.id, "nombre": nuevo.nombre, "capitulos": len(template.capitulos)}


@router.get("/{pid}")
def detalle(pid: str, db: Session = Depends(get_db)):
    p = db.query(Presupuesto).options(
        joinedload(Presupuesto.config),
        joinedload(Presupuesto.capitulos).joinedload(Capitulo.partidas)
    ).filter(Presupuesto.id == pid).first()
    if not p:
        raise HTTPException(404, "Presupuesto no encontrado")

    cfg = p.config
    sobrecosto = float(cfg.sobrecosto) if cfg and cfg.sobrecosto is not None else 20.0
    cd, total = _totales(p)

    return {
        "id": p.id,
        "nombre": p.nombre,
        "cliente": p.cliente,
        "moneda": p.moneda,
        "es_template": p.es_template,
        "fecha": str(p.fecha) if p.fecha else None,
        "costo_directo": cd,
        "total_con_indirectos": total,
        "config": {
            "sobrecosto": sobrecosto,
            "administracion": float(cfg.administracion) if cfg else 0,
            "utilidad": float(cfg.utilidad) if cfg else 0,
            "imprevistos": float(cfg.imprevistos) if cfg else 0,
            "iva": float(cfg.iva) if cfg else 15,
            "otros_factor": float(cfg.otros_factor) if cfg else 0,
            "template_version": cfg.template_version if cfg else "v1.0",
        },
        "capitulos": [
            {
                "id": cap.id,
                "clave": cap.clave,
                "nombre": cap.nombre,
                "orden": cap.orden,
                "total": sum(float(pa.total or 0) for pa in cap.partidas),
                "partidas": [
                    {
                        "id": pa.id,
                        "clave_csi": pa.clave_csi,
                        "type_mark": pa.type_mark or "",
                        "descripcion": pa.descripcion,
                        "unidad": pa.unidad,
                        "revit_q": float(pa.revit_q or 0),
                        "factor_e": float(pa.factor_e or 1),
                        "factor_f": float(pa.factor_f or 1),
                        "color_tipo": pa.color_tipo or 'blanco',
                        "cantidad": float(pa.cantidad or 0),
                        "costo_mo": float(pa.costo_mo or 0),
                        "costo_ma": float(pa.costo_ma or 0),
                        "unitario_matriz": float(pa.unitario_matriz or 0),
                        "costo_base": float(pa.costo_base or 0),
                        "precio_unitario": float(pa.precio_unitario or 0),
                        "total": float(pa.total or 0),
                        "es_formula": bool(pa.es_formula),
                        "formula_ref": pa.formula_ref,
                        "orden": pa.orden,
                    }
                    for pa in sorted(cap.partidas, key=_csi_sort_key)
                ]
            }
            for cap in sorted(p.capitulos, key=lambda c: int(c.clave) if (c.clave or "").isdigit() else 999)
        ]
    }


class NombreIn(BaseModel):
    nombre: str

class SobrecostoIn(BaseModel):
    sobrecosto: float


@router.patch("/{pid}/nombre")
def renombrar(pid: str, data: NombreIn, db: Session = Depends(get_db)):
    p = db.query(Presupuesto).get(pid)
    if not p:
        raise HTTPException(404, "Presupuesto no encontrado")
    p.nombre = data.nombre
    db.commit()
    return {"id": p.id, "nombre": p.nombre}


@router.patch("/{pid}/sobrecosto")
def actualizar_sobrecosto(pid: str, data: SobrecostoIn, db: Session = Depends(get_db)):
    p = db.query(Presupuesto).options(
        joinedload(Presupuesto.config),
        joinedload(Presupuesto.capitulos).joinedload(Capitulo.partidas)
    ).filter(Presupuesto.id == pid).first()
    if not p:
        raise HTTPException(404, "Presupuesto no encontrado")
    sc = max(0, float(data.sobrecosto))
    if p.config:
        p.config.sobrecosto = sc
    for cap in p.capitulos:
        for pa in cap.partidas:
            base = float(pa.costo_mo or 0) + float(pa.costo_ma or 0) + float(pa.unitario_matriz or 0)
            pa.costo_base = base
            pa.precio_unitario = base * (1 + sc / 100)
            pa.total = float(pa.cantidad or 0) * float(pa.precio_unitario)
    db.commit()
    return {"sobrecosto": sc}


@router.put("/{pid}")
def actualizar(pid: str, data: PresupuestoIn, db: Session = Depends(get_db)):
    p = db.query(Presupuesto).get(pid)
    if not p:
        raise HTTPException(404, "Presupuesto no encontrado")
    p.nombre = data.nombre
    p.cliente = data.cliente
    p.moneda = data.moneda
    if data.config and p.config:
        for k, v in data.config.model_dump().items():
            setattr(p.config, k, v)
    db.commit()
    return {"ok": True}


@router.post("/{pid}/reasignar-capitulos")
def reasignar_capitulos(pid: str, db: Session = Depends(get_db)):
    """
    Recorre todas las partidas de un presupuesto y mueve cada una al capítulo
    correcto según los primeros 2 dígitos de su clave_csi.
    Crea capítulos nuevos si no existen. Elimina capítulos que quedaron vacíos.
    """
    p = db.query(Presupuesto).options(
        joinedload(Presupuesto.capitulos).joinedload(Capitulo.partidas)
    ).filter(Presupuesto.id == pid).first()
    if not p:
        raise HTTPException(404, "Presupuesto no encontrado")

    capitulos_map = {cap.clave: cap for cap in p.capitulos}
    max_orden = max((cap.orden or 0 for cap in p.capitulos), default=-1) + 1
    movidas = 0

    all_partidas = [pa for cap in p.capitulos for pa in cap.partidas]

    for pa in all_partidas:
        csi = (pa.clave_csi or "").strip()
        div = csi[:2] if len(csi) >= 2 and csi[:2].isdigit() else "00"

        # Already in correct chapter
        cap_actual = db.query(Capitulo).get(pa.capitulo_id)
        if cap_actual and cap_actual.clave == div:
            continue

        # Get or create target chapter
        if div not in capitulos_map:
            nombre_div = DIVISIONES_CSI.get(div, f"División {div}")
            new_cap = Capitulo(
                presupuesto_id=pid,
                clave=div,
                nombre=nombre_div,
                orden=max_orden,
            )
            db.add(new_cap)
            db.flush()
            capitulos_map[div] = new_cap
            max_orden += 1

        target_cap = capitulos_map[div]
        new_orden = db.query(Partida).filter(Partida.capitulo_id == target_cap.id).count()
        pa.capitulo_id = target_cap.id
        pa.orden = new_orden
        movidas += 1

    db.flush()

    # Remove empty chapters (except keep chapter "00" always)
    eliminados = []
    for cap in list(p.capitulos):
        count = db.query(Partida).filter(Partida.capitulo_id == cap.id).count()
        if count == 0 and cap.clave != "00":
            eliminados.append(cap.clave)
            db.delete(cap)

    db.commit()
    return {
        "ok": True,
        "partidas_movidas": movidas,
        "capitulos_eliminados": eliminados,
    }


PROTECTED_OBRAS = {"OBRA #1 TEST"}


@router.delete("/{pid}", status_code=204)
def eliminar(pid: str, db: Session = Depends(get_db)):
    p = db.query(Presupuesto).get(pid)
    if not p:
        raise HTTPException(404, "Presupuesto no encontrado")
    if p.es_template or (p.nombre and p.nombre.strip().upper() in {n.upper() for n in PROTECTED_OBRAS}):
        raise HTTPException(403, f"La obra '{p.nombre}' está protegida y no se puede borrar")
    db.delete(p)
    db.commit()


# --- Capitulos ---

class CapituloIn(BaseModel):
    clave: str
    nombre: str
    orden: int = 0


@router.get("/{pid}/capitulos")
def listar_capitulos(pid: str, db: Session = Depends(get_db)):
    caps = db.query(Capitulo).filter(Capitulo.presupuesto_id == pid).order_by(Capitulo.orden).all()
    return [{"id": c.id, "clave": c.clave, "nombre": c.nombre, "orden": c.orden} for c in caps]


@router.post("/{pid}/capitulos", status_code=201)
def crear_capitulo(pid: str, data: CapituloIn, db: Session = Depends(get_db)):
    if not db.query(Presupuesto).get(pid):
        raise HTTPException(404, "Presupuesto no encontrado")
    c = Capitulo(presupuesto_id=pid, **data.model_dump())
    db.add(c)
    db.commit()
    db.refresh(c)
    return {"id": c.id, "clave": c.clave, "nombre": c.nombre}
