"""
Bases de Datos — editor de rendimientos y precios unitarios de fichas.
GET  /bases              → versiones disponibles
GET  /bases/{version}    → fichas completas con insumos
POST /bases/{version}/sync → guarda JSON y propaga a todos los presupuestos de esa versión
"""
import json, os, shutil
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Any, List
from db import get_db
from models import ConfigPresupuesto, Capitulo, Partida, InsumoPartida

router = APIRouter(prefix="/bases", tags=["bases"])

BASE_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "development", "Template2_Updated")
)


_MAX_BAKS = 4


def _ficha_path(version: str) -> str:
    return os.path.join(BASE_PATH, version, "fichas", f"fichas_{version}.json")


def _live_path(version: str) -> str:
    return os.path.join(BASE_PATH, version, "fichas", f"fichas_{version}.live.json")


def _bak_path(version: str, n: int) -> str:
    return os.path.join(BASE_PATH, version, "fichas", f"fichas_{version}.bak{n}.json")


def _backup(version: str):
    """Rotate backups before overwriting: bak4←bak3←bak2←bak1←current."""
    path = _ficha_path(version)
    if not os.path.exists(path):
        return
    for i in range(_MAX_BAKS, 1, -1):
        src = _bak_path(version, i - 1)
        dst = _bak_path(version, i)
        if os.path.exists(src):
            shutil.copy2(src, dst)
    shutil.copy2(path, _bak_path(version, 1))


def _undo_levels(version: str) -> int:
    return sum(1 for i in range(1, _MAX_BAKS + 1) if os.path.exists(_bak_path(version, i)))


def _load_fichas(version: str) -> list:
    for path in (_live_path(version), _ficha_path(version)):
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
    raise HTTPException(404, f"Versión '{version}' no encontrada")


def _count_fichas(version: str) -> int:
    return len(_load_fichas(version))


def _write_fichas(version: str, fichas: list):
    path = _ficha_path(version)
    live_path = _live_path(version)
    for target in (path, live_path):
        with open(target, "w", encoding="utf-8") as f:
            json.dump(fichas, f, ensure_ascii=False, indent=2)


@router.get("")
def list_versions():
    versions = []
    if not os.path.exists(BASE_PATH):
        return versions
    for d in sorted(os.listdir(BASE_PATH)):
        if os.path.exists(_ficha_path(d)):
            try:
                total = _count_fichas(d)
            except Exception:
                total = 0
            versions.append({
                "version": d,
                "fichas_total": total,
            })
    return versions


def _csi_sort_key(ficha: dict):
    import re
    s = ficha.get("csi", "") or ""
    _NUM_RX = re.compile(r"\d+|\D+")
    parts = []
    for tok in _NUM_RX.findall(s):
        parts.append((0, int(tok)) if tok.isdigit() else (1, tok.lower()))
    return parts or [(1, "zz")]


def _reasignar_duplicados(fichas: list) -> tuple[list, list]:
    """
    Para fichas con Type Mark o CSI repetido, genera sufijo -2, -3, etc. en lugar de eliminar.
    También deduplica insumos internos por codigo (fusiona primer encontrado).
    Retorna (fichas_limpias, lista_de_reasignaciones).
    """
    seen_codigo: dict[str, int] = {}
    seen_csi: dict[str, int] = {}
    result = []
    reasignaciones = []

    for ficha in fichas:
        if not isinstance(ficha, dict):
            continue
        ficha = dict(ficha)
        codigo_orig = (ficha.get("codigo") or "").strip()
        csi_orig = (ficha.get("csi") or "").strip()

        codigo_key = codigo_orig.upper()
        csi_key = csi_orig

        # Reasignar Type Mark si duplicado
        if codigo_key and codigo_key in seen_codigo:
            seen_codigo[codigo_key] += 1
            nuevo_codigo = f"{codigo_orig}-{seen_codigo[codigo_key]}"
            reasignaciones.append({"campo": "type_mark", "original": codigo_orig, "nuevo": nuevo_codigo})
            ficha["codigo"] = nuevo_codigo
            codigo_key = nuevo_codigo.upper()
        elif codigo_key:
            seen_codigo[codigo_key] = 1

        # Reasignar CSI si duplicado
        if csi_key and csi_key in seen_csi:
            seen_csi[csi_key] += 1
            sufijo = chr(ord('a') + seen_csi[csi_key] - 2)  # .b, .c, .d ...
            nuevo_csi = f"{csi_orig}.{sufijo}"
            reasignaciones.append({"campo": "csi", "original": csi_orig, "nuevo": nuevo_csi})
            ficha["csi"] = nuevo_csi
        elif csi_key:
            seen_csi[csi_key] = 1

        # Dedup insumos internos por codigo (primer hallazgo gana)
        insumos = ficha.get("insumos") or []
        seen_ins: dict[str, bool] = {}
        clean_ins = []
        for ins in insumos:
            k = (ins.get("codigo") or "").strip().upper()
            if k and k in seen_ins:
                continue
            if k:
                seen_ins[k] = True
            clean_ins.append(ins)
        ficha["insumos"] = clean_ins
        result.append(ficha)

    return result, reasignaciones


@router.get("/{version}")
def get_fichas(version: str):
    fichas = _load_fichas(version)
    clean = []
    for ficha in fichas:
        if not isinstance(ficha, dict):
            continue
        item = dict(ficha)
        clean.append(item)
    deduped, _ = _reasignar_duplicados(clean)
    return sorted(deduped, key=_csi_sort_key)


@router.post("/{version}/dedup")
def dedup_version(version: str):
    """Reasigna CSI/Type Mark duplicados con sufijo único (-2, .b, etc). No elimina fichas."""
    fichas = _load_fichas(version)
    clean = []
    for ficha in fichas:
        if not isinstance(ficha, dict):
            continue
        item = dict(ficha)
        clean.append(item)
    reasignadas, cambios = _reasignar_duplicados(clean)
    if cambios:
        _backup(version)
        _write_fichas(version, reasignadas)
    return {
        "ok": True,
        "version": version,
        "fichas_total": len(reasignadas),
        "reasignaciones": len(cambios),
        "detalle": cambios,
    }


@router.post("/{version}/sync")
def sync_version(version: str, payload: List[Any], db: Session = Depends(get_db)):
    path = _ficha_path(version)
    if not os.path.exists(path):
        raise HTTPException(404, f"Versión '{version}' no encontrada")

    # 1. Backup before overwrite (enables undo)
    _backup(version)

    # 2. Persist updated JSON
    clean_payload = []
    for fi in payload:
        if not isinstance(fi, dict):
            continue
        item = dict(fi)
        item["descripcion"] = (item.get("descripcion") or "").replace("_x000D_", "").strip()
        clean_payload.append(item)

    clean_payload, _ = _reasignar_duplicados(clean_payload)
    _write_fichas(version, clean_payload)

    ficha_map = {fi["codigo"]: fi for fi in clean_payload if "codigo" in fi}

    # 2. Find all presupuestos on this version
    configs = db.query(ConfigPresupuesto).filter(
        ConfigPresupuesto.template_version == version
    ).all()

    sobrecosto_map = {c.presupuesto_id: float(c.sobrecosto or 20) for c in configs}
    pres_ids = list(sobrecosto_map.keys())

    updated_partidas = 0
    updated_insumos  = 0

    for pres_id in pres_ids:
        sc   = sobrecosto_map[pres_id]
        caps = db.query(Capitulo).filter(Capitulo.presupuesto_id == pres_id).all()

        for cap in caps:
            for partida in cap.partidas:
                tm = (partida.type_mark or "").strip()
                ficha = None
                if tm and tm in ficha_map:
                    ficha = ficha_map[tm]
                if not ficha:
                    continue

                desired_tm = (ficha.get("codigo") or tm).strip()
                desired_desc = (ficha.get("descripcion") or partida.descripcion or "").strip()
                desired_unit = (ficha.get("unidad") or partida.unidad or "global").strip()
                desired_color = (ficha.get("color_tipo") or partida.color_tipo or "rosa").strip()
                ins_map = {ins["codigo"]: ins for ins in ficha.get("insumos", [])}

                partida.type_mark = desired_tm
                partida.descripcion = desired_desc
                partida.unidad = desired_unit
                partida.color_tipo = desired_color

                changed = False
                for ip in partida.insumos:
                    if ip.clave not in ins_map:
                        continue
                    ins    = ins_map[ip.clave]
                    new_q  = float(ins.get("cantidad", ip.cantidad))
                    new_pu = float(ins.get("precioUnitario", ip.costo_unit))
                    if round(float(ip.cantidad), 6) != round(new_q, 6) or \
                       round(float(ip.costo_unit), 4) != round(new_pu, 4):
                        ip.cantidad   = new_q
                        ip.costo_unit = new_pu
                        ip.total      = round(new_q * new_pu, 4)
                        updated_insumos += 1
                        changed = True

                if changed:
                    mo   = sum(float(i.total) for i in partida.insumos if i.tipo == "MANO_OBRA")
                    ma   = sum(float(i.total) for i in partida.insumos if i.tipo != "MANO_OBRA")
                    base = round(mo + ma, 4)
                    pu   = round(base * (1 + sc / 100), 4)
                    tot  = round(float(partida.cantidad or 0) * pu, 4)

                    partida.costo_mo        = mo
                    partida.costo_ma        = ma
                    partida.costo_base      = base
                    partida.precio_unitario = pu
                    partida.total           = tot
                    updated_partidas += 1
                else:
                    mo   = sum(float(i.total) for i in partida.insumos if i.tipo == "MANO_OBRA")
                    ma   = sum(float(i.total) for i in partida.insumos if i.tipo != "MANO_OBRA")
                    base = round(mo + ma, 4)
                    pu   = round(base * (1 + sc / 100), 4)
                    tot  = round(float(partida.cantidad or 0) * pu, 4)
                    partida.costo_mo        = mo
                    partida.costo_ma        = ma
                    partida.costo_base      = base
                    partida.precio_unitario = pu
                    partida.total           = tot
                    updated_partidas += 1

    db.commit()

    return {
        "ok": True,
        "version": version,
        "fichas_en_json": len(clean_payload),
        "presupuestos_afectados": len(pres_ids),
        "partidas_actualizadas": updated_partidas,
        "insumos_actualizados": updated_insumos,
        "undo_levels": _undo_levels(version),
    }


@router.get("/{version}/undo-status")
def undo_status(version: str):
    return {"version": version, "undo_levels": _undo_levels(version)}


@router.post("/{version}/undo")
def undo_version(version: str):
    path = _ficha_path(version)
    bak1 = _bak_path(version, 1)
    if not os.path.exists(bak1):
        raise HTTPException(400, "No hay más pasos para deshacer")

    # Restore bak1 → current, shift remaining baks down
    shutil.copy2(bak1, path)
    for i in range(1, _MAX_BAKS):
        nxt = _bak_path(version, i + 1)
        if os.path.exists(nxt):
            shutil.copy2(nxt, _bak_path(version, i))
            os.remove(nxt)
        else:
            os.remove(_bak_path(version, i))
            break

    with open(path, encoding="utf-8") as f:
        fichas = json.load(f)
    _write_fichas(version, fichas)

    return {
        "ok": True,
        "version": version,
        "fichas_restauradas": len(fichas),
        "undo_levels": _undo_levels(version),
    }
