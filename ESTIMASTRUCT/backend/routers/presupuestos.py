from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy import func
from pydantic import BaseModel
from typing import Optional
import sys, os, json
from decimal import Decimal
from types import SimpleNamespace
from backend.db import get_db
from backend.models import Presupuesto, ConfigPresupuesto, Capitulo, Partida, InsumoPartida, Recurso, new_uuid, DIVISIONES_CSI
from backend.services.pricing import recalcular_partida, calc_base, precio_unitario, rebucket_insumos, quantize_money
from backend.config import CONFIG

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
    template_version: str = "v1.3"  # v1.3 CANON (Postgres); v1.2/v1.1/v1.0 legacy


def _load_fichas_from_json(template_version: str) -> list:
    """Carga fichas desde Template 2 - Updated (v1.0/v1.1 legacy, v1.2 vigente)."""
    base_path = CONFIG.FICHAS_DIR
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


def _normalizar_insumo(insumo: dict, recursos: dict):
    """Insumo de ficha (v1.2 codigo/precioUnitario o v1.3+ clave/costo_unit/tipo)
    -> objeto con recurso_id/clave/tipo/costo_unit/total. Postgres `recurso` es canon:
    si la clave existe ahi, manda su precio y tipo; si no, el valor de la ficha."""
    clave = (insumo.get('clave') or insumo.get('codigo') or '').strip()
    desc = (insumo.get('descripcion') or clave).replace('_x000D_', '').strip()
    if not clave:
        # fichas viejas guardan la clave dentro de la descripcion: "MO-006 Ayudante"
        m = re.match(r'^([A-Z]{2,3}-\d+(?:\.\d+)?)\s', desc)
        if m:
            clave = m.group(1)
    cant = float(insumo.get('cantidad') or 0)
    rec = recursos.get(clave)
    if rec is not None:
        cu = float(rec.precio_unitario or 0)
        tipo = rec.tipo
        rid = rec.id
        unidad = insumo.get('unidad') or rec.unidad
    else:
        cu = float(insumo.get('costo_unit', insumo.get('precioUnitario', 0)) or 0)
        tipo = insumo.get('tipo') if clave == '' or insumo.get('tipo') not in (None, '', 'MATERIAL') else _tipo_from_clave(clave)
        tipo = tipo or _tipo_from_clave(clave)
        rid = None
        unidad = insumo.get('unidad', 'global')
    return SimpleNamespace(recurso_id=rid, clave=clave, descripcion=desc, unidad=unidad,
                           tipo=tipo, cantidad=cant, costo_unit=cu,
                           total=quantize_money(Decimal(str(cant)) * Decimal(str(cu))))


def _create_from_template2_updated(nuevo: Presupuesto, template_version: str, sobrecosto: float, db: Session):
    """Crea capítulos y partidas a partir de Template 2 - Updated (v1.0/v1.1 legacy, v1.2 vigente)."""
    try:
        fichas = _load_fichas_from_json(template_version)
    except HTTPException:
        raise
    recursos = {r.clave: r for r in db.query(Recurso).all()}

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

        # [FIX 2026-10-02] Canon Postgres: los insumos se resuelven contra la
        # tabla `recurso` (precio/tipo vigentes). Acepta formato v1.2
        # (codigo/precioUnitario) y v1.3+ (clave/costo_unit/tipo). Antes solo
        # leia 'codigo' -> en v1.3 todos los insumos quedaban clave='' tipo
        # MATERIAL costo 0, y costo_ma = precio_unitario (MO+MA mezclados).
        insumos_norm = [_normalizar_insumo(ins, recursos) for ins in ficha.get('insumos', [])]
        costo_mo, costo_ma, otros = rebucket_insumos(insumos_norm)

        if not insumos_norm:
            # Ficha sin descomposicion: respetar el desglose declarado, nunca el PU con markup
            costo_mo = float(ficha.get('costo_mo') or 0)
            costo_ma = float(ficha.get('costo_ma') or 0)
            otros = float(ficha.get('unitario_matriz') or 0)

        base = calc_base(costo_mo, costo_ma, otros)
        pu = precio_unitario(base, sobrecosto)

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
            unitario_matriz=otros,
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

        for idx, ins in enumerate(insumos_norm):
            db.add(InsumoPartida(
                partida_id  = partida.id,
                recurso_id  = ins.recurso_id,
                clave       = ins.clave,
                descripcion = ins.descripcion,
                unidad      = ins.unidad,
                tipo        = ins.tipo,
                cantidad    = ins.cantidad,
                costo_unit  = ins.costo_unit,
                total       = ins.total,
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
            base = calc_base(pa.costo_mo, pa.costo_ma, pa.unitario_matriz)
            costo_directo += float(pa.cantidad or 0) * base
    total_con_indirectos = costo_directo * (1 + sobrecosto / 100)
    return costo_directo, total_con_indirectos


@router.get("")
def listar(db: Session = Depends(get_db)):
    # Solo config (NO cargar las ~1035 partidas como objetos ORM solo para sumar)
    presupuestos = db.query(Presupuesto).options(
        joinedload(Presupuesto.config)
    ).order_by(Presupuesto.created_at.desc()).all()

    # costo_directo por presupuesto en UN agregado SQL (COALESCE = semantica float(x or 0))
    cd_rows = (
        db.query(
            Capitulo.presupuesto_id,
            func.coalesce(func.sum(
                func.coalesce(Partida.cantidad, 0) * (
                    func.coalesce(Partida.costo_mo, 0) +
                    func.coalesce(Partida.costo_ma, 0) +
                    func.coalesce(Partida.unitario_matriz, 0)
                )
            ), 0),
        )
        .join(Partida, Partida.capitulo_id == Capitulo.id)
        .group_by(Capitulo.presupuesto_id)
        .all()
    )
    cd_map = {pid: float(s or 0) for pid, s in cd_rows}

    result = []
    for p in presupuestos:
        sobrecosto = float(p.config.sobrecosto) if p.config and p.config.sobrecosto is not None else 20.0
        cd = cd_map.get(p.id, 0.0)
        result.append({
            "id": p.id,
            "nombre": p.nombre,
            "cliente": p.cliente,
            "moneda": p.moneda,
            "es_template": p.es_template,
            "fecha": str(p.fecha) if p.fecha else None,
            "costo_directo": cd,
            "total_con_indirectos": cd * (1 + sobrecosto / 100),
        })
    return result


@router.post("", status_code=201)
def crear(data: PresupuestoIn, db: Session = Depends(get_db)):
    p = Presupuesto(nombre=data.nombre, cliente=data.cliente, moneda=data.moneda)
    db.add(p)
    db.flush()
    cfg_data = data.config or ConfigIn()
    cfg = ConfigPresupuesto(presupuesto_id=p.id, **cfg_data.model_dump())
    db.add(cfg)
    # Cédula financiera: siembra Administración/Utilidad/Imprevistos default
    # (porcentaje=0, activo=True). Seguros/Fianzas quedan sin sembrar — no
    # toda obra lleva póliza. Ver backend/routers/financiero.py.
    from backend.routers.financiero import sembrar_items_default
    sembrar_items_default(p.id, db)
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
    from backend.routers.financiero import sembrar_items_default
    sembrar_items_default(nuevo.id, db)
    db.flush()

    sobrecosto = cfg_data.sobrecosto

    # Determinar qué template usar

    # Si es v1.0/v1.1/v1.2/v1.3, cargar desde Template 2 - Updated JSON
    if template_version in ["v1.0", "v1.1", "v1.2", "v1.3"]:
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
            base = calc_base(pa_src.costo_mo, pa_src.costo_ma, pa_src.unitario_matriz)
            pu = precio_unitario(base, sobrecosto)
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
            .selectinload(Partida.insumos)   # 1 query extra: resumen de reajuste de materiales
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
            "reajuste_materiales": float(cfg.reajuste_materiales or 0) if cfg else 0.0,
            "valor_objetivo": float(cfg.valor_objetivo) if cfg and cfg.valor_objetivo is not None else None,
        },
        "reajuste": _resumen_reajuste(p),
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


class ReajusteIn(BaseModel):
    reajuste_materiales: Optional[float] = None   # % sobre insumos MATERIAL (ej. -25.7)
    valor_objetivo: Optional[float] = None        # monto contrato con sobrecosto (para recalcular)


def _resumen_reajuste(p: Presupuesto) -> dict:
    """Σ MO / Σ materiales a precio de MERCADO / Σ materiales reajustados / Σ otros.
    Sale de los insumos (precio mercado) — el reajuste solo vive en config."""
    cfg = p.config
    pct = float(cfg.reajuste_materiales or 0) if cfg else 0.0
    mo = ma_mkt = ot = 0.0
    for cap in p.capitulos:
        for pa in cap.partidas:
            q = float(pa.cantidad or 0)
            if not q:
                continue
            if pa.insumos:
                for i in pa.insumos:
                    t = q * float(i.total or 0)
                    if i.tipo == "MANO_OBRA": mo += t
                    elif i.tipo == "MATERIAL": ma_mkt += t
                    else: ot += t
            else:   # partida sin insumos: costo_ma ya guardado (no reajustable)
                mo += q * float(pa.costo_mo or 0); ot += q * float(pa.costo_ma or 0) + q * float(pa.unitario_matriz or 0)
    return {"pct": pct, "mo": round(mo, 2), "materiales_mercado": round(ma_mkt, 2),
            "materiales_reajustados": round(ma_mkt * (1 + pct / 100), 2),
            "absorbido": round(ma_mkt * (-pct / 100), 2), "otros": round(ot, 2)}


def _cargar_full(pid: str, db: Session) -> Presupuesto:
    p = db.query(Presupuesto).options(
        joinedload(Presupuesto.config),
        joinedload(Presupuesto.capitulos).joinedload(Capitulo.partidas)
            .joinedload(Partida.insumos).joinedload(InsumoPartida.recurso)
    ).filter(Presupuesto.id == pid).first()
    if not p:
        raise HTTPException(404, "Presupuesto no encontrado")
    if not p.config:
        raise HTTPException(400, "Presupuesto sin config")
    return p


@router.patch("/{pid}/reajuste-materiales")
def actualizar_reajuste(pid: str, data: ReajusteIn, db: Session = Depends(get_db)):
    """Fija el % de reajuste de materiales (y/o el valor objetivo) y recalcula la obra."""
    from backend.routers.calculos import _recalcular_todo
    p = _cargar_full(pid, db)
    if data.reajuste_materiales is not None:
        pct = float(data.reajuste_materiales)
        if pct <= -100 or pct > 500:
            raise HTTPException(400, "Reajuste fuera de rango (-100, 500]")
        p.config.reajuste_materiales = round(pct, 4)
    if data.valor_objetivo is not None:
        p.config.valor_objetivo = data.valor_objetivo if data.valor_objetivo > 0 else None
    _recalcular_todo(p, db)
    db.commit()
    cd, total = _totales(p)
    return {"reajuste_materiales": float(p.config.reajuste_materiales or 0),
            "valor_objetivo": float(p.config.valor_objetivo) if p.config.valor_objetivo is not None else None,
            "costo_directo": cd, "total_con_indirectos": total, "reajuste": _resumen_reajuste(p)}


@router.post("/{pid}/reajuste-materiales/recalcular")
def recalcular_reajuste(pid: str, data: ReajusteIn = None, db: Session = Depends(get_db)):
    """Calcula el % exacto para que el total (con sobrecosto) = valor_objetivo,
    moviendo SOLO materiales. MO y otros quedan intactos.
      total = (MO + MA_mercado·f + otros)·(1+sc)  →  f = (obj/(1+sc) − MO − otros) / MA_mercado"""
    from backend.routers.calculos import _recalcular_todo
    p = _cargar_full(pid, db)
    cfg = p.config
    if data and data.valor_objetivo:
        cfg.valor_objetivo = data.valor_objetivo
    if cfg.valor_objetivo is None:
        raise HTTPException(400, "Falta valor_objetivo (monto contrato)")
    obj = float(cfg.valor_objetivo)
    sc = float(cfg.sobrecosto if cfg.sobrecosto is not None else 20)
    # Precios de insumos al día (mismo paso que /calcular) antes de resolver el factor
    cfg.reajuste_materiales = 0
    _recalcular_todo(p, db)
    r = _resumen_reajuste(p)
    if r["materiales_mercado"] <= 0:
        raise HTTPException(400, "La obra no tiene materiales que reajustar")
    f = (obj / (1 + sc / 100) - r["mo"] - r["otros"]) / r["materiales_mercado"]
    if f <= 0:
        raise HTTPException(400, f"Imposible: MO+otros ya exceden el objetivo (factor {f:.4f})")
    cfg.reajuste_materiales = round((f - 1) * 100, 4)
    _recalcular_todo(p, db)
    db.commit()
    cd, total = _totales(p)
    return {"reajuste_materiales": float(cfg.reajuste_materiales), "factor": round(f, 6),
            "valor_objetivo": obj, "costo_directo": cd, "total_con_indirectos": total,
            "diferencia": round(total - obj, 2), "reajuste": _resumen_reajuste(p)}


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
            recalcular_partida(pa, sc)
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
    cap_by_id = {cap.id: cap for cap in p.capitulos}
    max_orden = max((cap.orden or 0 for cap in p.capitulos), default=-1) + 1
    movidas = 0

    all_partidas = [pa for cap in p.capitulos for pa in cap.partidas]

    for pa in all_partidas:
        csi = (pa.clave_csi or "").strip()
        div = csi[:2] if len(csi) >= 2 and csi[:2].isdigit() else "00"

        # Already in correct chapter
        cap_actual = cap_by_id.get(pa.capitulo_id)
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
            cap_by_id[new_cap.id] = new_cap
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


@router.post("/{pid}/duplicar", status_code=201)
def duplicar(pid: str, db: Session = Depends(get_db)):
    p = db.query(Presupuesto).options(
        joinedload(Presupuesto.config),
        joinedload(Presupuesto.capitulos).joinedload(Capitulo.partidas).joinedload(Partida.insumos)
    ).filter(Presupuesto.id == pid).first()
    if not p:
        raise HTTPException(404, "Presupuesto no encontrado")

    nuevo = Presupuesto(
        nombre=f"{p.nombre} (copia)",
        cliente=p.cliente,
        moneda=p.moneda,
    )
    db.add(nuevo)
    db.flush()

    if p.config:
        db.add(ConfigPresupuesto(
            presupuesto_id=nuevo.id,
            sobrecosto=p.config.sobrecosto,
            administracion=p.config.administracion,
            utilidad=p.config.utilidad,
            imprevistos=p.config.imprevistos,
            iva=p.config.iva,
            otros_factor=p.config.otros_factor,
            template_version=p.config.template_version,
            reajuste_materiales=p.config.reajuste_materiales,
            valor_objetivo=p.config.valor_objetivo,
        ))
        db.flush()

    for cap in sorted(p.capitulos, key=lambda c: c.orden or 0):
        new_cap = Capitulo(
            presupuesto_id=nuevo.id,
            clave=cap.clave,
            nombre=cap.nombre,
            orden=cap.orden,
        )
        db.add(new_cap)
        db.flush()

        for pa in sorted(cap.partidas, key=lambda x: x.orden or 0):
            new_pa = Partida(
                capitulo_id=new_cap.id,
                clave_csi=pa.clave_csi,
                descripcion=pa.descripcion,
                unidad=pa.unidad,
                cantidad=pa.cantidad,
                revit_q=pa.revit_q,
                factor_e=pa.factor_e,
                factor_f=pa.factor_f,
                color_tipo=pa.color_tipo,
                costo_mo=pa.costo_mo,
                costo_ma=pa.costo_ma,
                unitario_matriz=pa.unitario_matriz,
                costo_base=pa.costo_base,
                precio_unitario=pa.precio_unitario,
                total=pa.total,
                es_formula=pa.es_formula,
                formula_ref=pa.formula_ref,
                type_mark=pa.type_mark,
                omniclass_num=pa.omniclass_num,
                assembly_num=pa.assembly_num,
                orden=pa.orden,
            )
            db.add(new_pa)
            db.flush()

            for ins in sorted(pa.insumos, key=lambda x: x.orden or 0):
                db.add(InsumoPartida(
                    partida_id=new_pa.id,
                    recurso_id=ins.recurso_id,
                    clave=ins.clave,
                    descripcion=ins.descripcion,
                    unidad=ins.unidad,
                    tipo=ins.tipo,
                    cantidad=ins.cantidad,
                    costo_unit=ins.costo_unit,
                    total=ins.total,
                    orden=ins.orden,
                ))

    db.commit()
    db.refresh(nuevo)
    return {"id": nuevo.id, "nombre": nuevo.nombre}


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
