"""
Bases de Datos — editor de rendimientos y precios unitarios de fichas.
GET  /bases              → versiones disponibles
GET  /bases/{version}    → fichas completas con insumos
POST /bases/{version}/sync → guarda JSON y propaga a todos los presupuestos de esa versión
"""
import json, os, shutil
from collections import Counter, defaultdict
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Any, List
from backend.db import get_db
from backend.models import ConfigPresupuesto, Capitulo, Partida, InsumoPartida
from backend.config import CONFIG
from backend.services.pricing import calc_base, precio_unitario

router = APIRouter(prefix="/bases", tags=["bases"])

BASE_PATH = CONFIG.FICHAS_DIR


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
    # Prefiere el archivo MÁS NUEVO por fecha de modificación. Auto-cura divergencias
    # cuando un script escribe solo uno de los dos (.json vs .live.json) y evita que
    # un .live.json viejo "tape" fichas nuevas del .json canónico (bug de shadowing).
    candidates = [p for p in (_live_path(version), _ficha_path(version)) if os.path.exists(p)]
    if not candidates:
        raise HTTPException(404, f"Versión '{version}' no encontrada")
    path = max(candidates, key=os.path.getmtime)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _count_fichas(version: str) -> int:
    return len(_load_fichas(version))


def _recompute_precio_unitario(ficha: dict) -> dict:
    """Fuerza el invariante precio_unitario == Σ(cantidad × precioUnitario) de
    los insumos. Se llama en TODO punto de escritura del catálogo para que
    ningún caller (UI, dedup, script) pueda dejar el total desincronizado de
    sus propios insumos — bug encontrado 2026-07-07 (199/343 fichas stale)."""
    if not isinstance(ficha, dict):
        return ficha
    insumos = ficha.get("insumos") or []
    if not insumos:
        return ficha
    total = 0.0
    for ins in insumos:
        if not isinstance(ins, dict):
            continue
        cant = _precio_key(ins.get("cantidad"))
        precio = _precio_key(ins.get("precioUnitario"))
        t = round(cant * precio, 4)
        ins["total"] = t
        total += t
    ficha["precio_unitario"] = round(total, 2)
    return ficha


def _write_fichas(version: str, fichas: list):
    for ficha in fichas:
        _recompute_precio_unitario(ficha)
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


def _precio_key(v) -> float:
    try:
        return round(float(v or 0), 4)
    except Exception:
        return 0.0


def _desc_key(v) -> str:
    return (str(v or "").replace("_x000D_", "").strip())


def _canon_desc_map(fichas: list) -> dict[str, str]:
    """
    Descripción canónica por código:
    - usa la descripción no vacía más repetida
    - si hay empate, conserva la primera descripción vista con esa frecuencia
    """
    desc_counts: dict[str, Counter] = defaultdict(Counter)
    desc_order: dict[str, list[str]] = defaultdict(list)

    for ficha in fichas:
        if not isinstance(ficha, dict):
            continue
        for ins in ficha.get("insumos") or []:
            if not isinstance(ins, dict):
                continue
            codigo = (ins.get("codigo") or "").strip().upper()
            if not codigo:
                continue
            descripcion = _desc_key(ins.get("descripcion"))
            if not descripcion:
                continue
            desc_counts[codigo][descripcion] += 1
            if descripcion not in desc_order[codigo]:
                desc_order[codigo].append(descripcion)

    canon: dict[str, str] = {}
    for codigo, counter in desc_counts.items():
        if not counter:
            continue
        max_count = max(counter.values())
        candidates = [descripcion for descripcion, count in counter.items() if count == max_count]
        if len(candidates) == 1:
            canon[codigo] = candidates[0]
            continue
        ordered = desc_order.get(codigo, [])
        chosen = next((descripcion for descripcion in ordered if descripcion in candidates), candidates[0])
        canon[codigo] = chosen

    return canon


def _canon_price_map(fichas: list) -> dict[str, float]:
    """
    Precio canónico por código:
    - usa el precio no-cero más repetido
    - si hay empate, conserva el primer precio visto con esa frecuencia
    """
    price_counts: dict[str, Counter] = defaultdict(Counter)
    price_order: dict[str, list[float]] = defaultdict(list)

    for ficha in fichas:
        if not isinstance(ficha, dict):
            continue
        for ins in ficha.get("insumos") or []:
            if not isinstance(ins, dict):
                continue
            codigo = (ins.get("codigo") or "").strip().upper()
            if not codigo:
                continue
            if codigo == "HER-00":
                # HER-00 es variable por matriz: porcentaje sobre la MO de la ficha.
                continue
            precio = _precio_key(ins.get("precioUnitario"))
            if precio <= 0:
                continue
            price_counts[codigo][precio] += 1
            if precio not in price_order[codigo]:
                price_order[codigo].append(precio)

    canon: dict[str, float] = {}
    for codigo, counter in price_counts.items():
        if not counter:
            continue
        max_count = max(counter.values())
        candidates = [precio for precio, count in counter.items() if count == max_count]
        if len(candidates) == 1:
            canon[codigo] = candidates[0]
            continue
        ordered = price_order.get(codigo, [])
        chosen = next((precio for precio in ordered if precio in candidates), candidates[0])
        canon[codigo] = chosen

    return canon


def _normalizar_descripciones_por_codigo(fichas: list) -> tuple[list, list]:
    """
    Propaga la descripción canónica a todas las apariciones del mismo código.
    No altera el código de la matriz ni el del insumo.
    """
    canon = _canon_desc_map(fichas)
    cambios = []

    for ficha in fichas:
        if not isinstance(ficha, dict):
            continue
        for ins in ficha.get("insumos") or []:
            if not isinstance(ins, dict):
                continue
            codigo = (ins.get("codigo") or "").strip().upper()
            if not codigo:
                continue
            descripcion_canonica = canon.get(codigo)
            if descripcion_canonica is None:
                continue
            descripcion_actual = _desc_key(ins.get("descripcion"))
            if descripcion_actual != descripcion_canonica:
                ins["descripcion"] = descripcion_canonica
                cambios.append({
                    "codigo": codigo,
                    "descripcion_anterior": descripcion_actual,
                    "descripcion_nueva": descripcion_canonica,
                })

    return fichas, cambios


def _normalizar_precios_por_codigo(fichas: list) -> tuple[list, list]:
    """
    Propaga el precio canónico a todas las apariciones del mismo código.
    No altera el código de la matriz ni el del insumo.
    """
    canon = _canon_price_map(fichas)
    cambios = []

    for ficha in fichas:
        if not isinstance(ficha, dict):
            continue
        for ins in ficha.get("insumos") or []:
            if not isinstance(ins, dict):
                continue
            codigo = (ins.get("codigo") or "").strip().upper()
            if not codigo:
                continue
            if codigo == "HER-00":
                # HER-00 se calcula como porcentaje sobre la mano de obra total de la ficha.
                continue
            precio_canonico = canon.get(codigo)
            if precio_canonico is None:
                continue
            precio_actual = _precio_key(ins.get("precioUnitario"))
            if precio_actual != precio_canonico:
                ins["precioUnitario"] = precio_canonico
                cant = _precio_key(ins.get("cantidad"))
                ins["total"] = round(cant * precio_canonico, 4)
                cambios.append({
                    "codigo": codigo,
                    "precio_anterior": precio_actual,
                    "precio_nuevo": precio_canonico,
                })

    # La propagación de precio canónico arriba solo toca insumos individuales;
    # sin esto el precio_unitario de la ficha queda desincronizado de sus
    # propios insumos (bug encontrado 2026-07-07, 199/343 fichas en V1.1).
    for ficha in fichas:
        _recompute_precio_unitario(ficha)

    return fichas, cambios


def _reasignar_duplicados(fichas: list) -> tuple[list, list]:
    """
    Para fichas con Type Mark o CSI repetido, genera sufijo -2, -3, etc. en lugar de eliminar.
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
    deduped, _ = _normalizar_descripciones_por_codigo(deduped)
    deduped, _ = _normalizar_precios_por_codigo(deduped)
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
    reasignadas, cambios_desc = _normalizar_descripciones_por_codigo(reasignadas)
    cambios += [{"campo": "descripcion", **c} for c in cambios_desc]
    reasignadas, cambios_precios = _normalizar_precios_por_codigo(reasignadas)
    cambios += [{"campo": "precioUnitario", **c} for c in cambios_precios]
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
    clean_payload, cambios_desc = _normalizar_descripciones_por_codigo(clean_payload)
    clean_payload, cambios_precios = _normalizar_precios_por_codigo(clean_payload)
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
                    new_desc = (ins.get("descripcion", ip.descripcion) or ip.descripcion or "").strip()
                    new_unit = (ins.get("unidad", ip.unidad) or ip.unidad or "").strip()
                    new_q  = float(ins.get("cantidad", ip.cantidad))
                    new_pu = float(ins.get("precioUnitario", ip.costo_unit))
                    if (ip.descripcion or "").strip() != new_desc:
                        ip.descripcion = new_desc
                        changed = True
                        updated_insumos += 1
                    if (ip.unidad or "").strip() != new_unit:
                        ip.unidad = new_unit
                        changed = True
                        updated_insumos += 1
                    if round(float(ip.cantidad), 6) != round(new_q, 6) or \
                       round(float(ip.costo_unit), 4) != round(new_pu, 4):
                        ip.cantidad   = new_q
                        ip.costo_unit = new_pu
                        ip.total      = round(new_q * new_pu, 4)
                        updated_insumos += 1
                        changed = True

                # Bucketing 3-vias (fuente unica: backend.services.pricing), corre siempre
                # (antes: ramas if/else identicas, 2-vias, sin tocar unitario_matriz -> stale
                # -> doble conteo en /calcular, mismo bug historico documentado en pricing.py).
                mo     = sum(float(i.total) for i in partida.insumos if i.tipo == "MANO_OBRA")
                ma     = sum(float(i.total) for i in partida.insumos if i.tipo == "MATERIAL")
                matriz = sum(float(i.total) for i in partida.insumos if i.tipo not in ("MANO_OBRA", "MATERIAL"))
                base   = calc_base(mo, ma, matriz)
                pu     = precio_unitario(base, sc)
                tot    = round(float(partida.cantidad or 0) * pu, 4)

                partida.costo_mo        = round(mo, 4)
                partida.costo_ma        = round(ma, 4)
                partida.unitario_matriz = round(matriz, 4)
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
        "descripciones_normalizadas": len(cambios_desc),
        "precios_normalizados": len(cambios_precios),
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
