"""Endpoints para invocar los scripts del flujo (Paso 2 keynotes, Paso 4 schedules)
y duplicar obras."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional
import os, sys, copy
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import get_db, SessionLocal
from models import Presupuesto, ConfigPresupuesto, Capitulo, Partida, InsumoPartida
from scripts_runner.generate_keynotes import generate as generate_keynotes
from scripts_runner.import_quantities import import_quantities, _parse_schedules_csv

router = APIRouter(tags=["scripts"])

S5_SCHEDULES_DIR = r"D:\OneDrive\Bots\Estimbot\EXPORTS\S5_schedules"
SCHEDULES_PREFIX = "schedules_"


def _is_schedules_export(name: str) -> bool:
    lower = name.lower()
    return lower.startswith(SCHEDULES_PREFIX) and lower.endswith(".csv")


@router.post("/presupuestos/{pid}/scripts/keynotes")
def run_keynotes(pid: str, db: Session = Depends(get_db)):
    obra = db.query(Presupuesto).filter(Presupuesto.id == pid).first()
    if not obra:
        raise HTTPException(404, "Obra no encontrada")
    res = generate_keynotes(pid)
    if not res.get("ok"):
        raise HTTPException(500, res.get("error", "Error generando keynotes"))
    return res


@router.get("/scripts/schedules-csvs")
def listar_schedules_csvs():
    """Lista solo exports de schedules de PyRevit en S5_schedules."""
    if not os.path.isdir(S5_SCHEDULES_DIR):
        return {"dir": S5_SCHEDULES_DIR, "files": []}
    files = []
    for name in sorted(os.listdir(S5_SCHEDULES_DIR), reverse=True):
        full = os.path.join(S5_SCHEDULES_DIR, name)
        if os.path.isfile(full) and _is_schedules_export(name):
            st = os.stat(full)
            files.append({
                "name": name,
                "size": st.st_size,
                "mtime": int(st.st_mtime),
            })
    files.sort(key=lambda item: (item["mtime"], item["name"]), reverse=True)
    return {"dir": S5_SCHEDULES_DIR, "files": files}


class ImportQtyIn(BaseModel):
    filename: str  # nombre del archivo dentro de S5_SCHEDULES_DIR


@router.post("/presupuestos/{pid}/scripts/import-quantities")
def run_import_quantities(pid: str, data: ImportQtyIn, db: Session = Depends(get_db)):
    obra = db.query(Presupuesto).filter(Presupuesto.id == pid).first()
    if not obra:
        raise HTTPException(404, "Obra no encontrada")
    # Sanitizar: el archivo debe estar dentro de S5_SCHEDULES_DIR
    safe_name = os.path.basename(data.filename)
    if not _is_schedules_export(safe_name):
        raise HTTPException(400, "Solo se admiten exports de schedules: schedules_*.csv")
    full_path = os.path.join(S5_SCHEDULES_DIR, safe_name)
    if not os.path.isfile(full_path):
        raise HTTPException(404, f"CSV no encontrado: {safe_name}")
    res = import_quantities(pid, full_path)
    if not res.get("ok"):
        raise HTTPException(500, res.get("error", "Error importando cantidades"))
    return res


# ── DUPLICAR OBRA ──────────────────────────────────────────────────────────

class DuplicarIn(BaseModel):
    nuevo_nombre: Optional[str] = None


@router.post("/presupuestos/{pid}/duplicar", status_code=201)
def duplicar(pid: str, data: DuplicarIn, db: Session = Depends(get_db)):
    src = db.query(Presupuesto).filter(Presupuesto.id == pid).first()
    if not src:
        raise HTTPException(404, "Obra origen no encontrada")
    nombre = (data.nuevo_nombre or f"{src.nombre} (copia)").strip()

    nueva = Presupuesto(
        nombre=nombre,
        cliente=src.cliente,
        moneda=src.moneda,
        es_template=False,
    )
    db.add(nueva)
    db.flush()

    if src.config:
        cfg = ConfigPresupuesto(
            presupuesto_id=nueva.id,
            sobrecosto=src.config.sobrecosto,
            administracion=src.config.administracion,
            utilidad=src.config.utilidad,
            imprevistos=src.config.imprevistos,
            iva=src.config.iva,
            otros_factor=src.config.otros_factor,
        )
        db.add(cfg)

    for cap_src in src.capitulos:
        cap = Capitulo(
            presupuesto_id=nueva.id,
            clave=cap_src.clave,
            nombre=cap_src.nombre,
            orden=cap_src.orden,
        )
        db.add(cap)
        db.flush()
        for pa_src in cap_src.partidas:
            pa = Partida(
                capitulo_id=cap.id,
                clave_csi=pa_src.clave_csi,
                descripcion=pa_src.descripcion,
                unidad=pa_src.unidad,
                cantidad=pa_src.cantidad,
                costo_mo=pa_src.costo_mo,
                costo_ma=pa_src.costo_ma,
                unitario_matriz=pa_src.unitario_matriz,
                costo_base=pa_src.costo_base,
                precio_unitario=pa_src.precio_unitario,
                total=pa_src.total,
                revit_q=pa_src.revit_q,
                factor_e=pa_src.factor_e,
                factor_f=pa_src.factor_f,
                color_tipo=pa_src.color_tipo,
                es_formula=pa_src.es_formula,
                formula_ref=pa_src.formula_ref,
                type_mark=pa_src.type_mark,
                omniclass_num=pa_src.omniclass_num,
                assembly_num=pa_src.assembly_num,
                orden=pa_src.orden,
            )
            db.add(pa)
            db.flush()
            for ins_src in pa_src.insumos:
                ins = InsumoPartida(
                    partida_id=pa.id,
                    recurso_id=ins_src.recurso_id,
                    clave=ins_src.clave,
                    descripcion=ins_src.descripcion,
                    unidad=ins_src.unidad,
                    tipo=ins_src.tipo,
                    cantidad=ins_src.cantidad,
                    costo_unit=ins_src.costo_unit,
                    total=ins_src.total,
                    orden=ins_src.orden,
                )
                db.add(ins)

    db.commit()
    return {"ok": True, "id": nueva.id, "nombre": nueva.nombre}
