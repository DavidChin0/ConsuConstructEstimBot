# -*- coding: utf-8 -*-
"""
Router — Acero estructural sobre presupuesto (Div 05, STATEFUL)
==============================================================
prefix /diseno (compartido con diseno_estructural).  R3: separa del archivo
gigante `diseno_estructural.py` los endpoints de ACERO que tocan BD:
  - puentes ETABS -> acero (ratios D/C y fuerzas LRFD §D-H),
  - generación de partidas Div 05 (suministro mL + conexiones pza con insumos).

Los paths NO cambian (siguen bajo /diseno/{pid}/...), así que el frontend
no se toca. Los helpers de mapeo/persistencia de acero y de presupuesto VIVEN
en diseno_estructural.py (los comparten /casos/{cid}/calcular y /memoria) y se
importan aquí: import UNIDIRECCIONAL (diseno_estructural NO importa este módulo),
sin ciclo.

Endpoints (idénticos a antes de R3):
  POST /diseno/{pid}/import-etabs-acero          -> ratios D/C + partidas Div 05
  POST /diseno/{pid}/import-etabs-acero-fuerzas  -> corre LRFD §D-H (chequeo cruzado)
  POST /diseno/{pid}/acero-generar-partidas      -> Div 05 mL desde elementos BD
  POST /diseno/{pid}/conexion-generar-partida    -> Div 05 pza con insumos de ficha
"""

import uuid, re, math
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel

from backend.db import get_db
from backend.models import (
    Presupuesto, Partida, InsumoPartida, DisenoElemento, CasoDiseno,
)
from backend.acero_ficha import (
    agregar_por_ficha, parse_acero_texto, parse_acero_bytes, conexion_ficha,
)
from backend.seccion_ficha import (
    factores_unidad, parse_concreto_texto, parse_concreto_bytes, parse_reacciones_texto,
)
from backend.calculo_conexion_acero import calcular_conexion
# Helpers compartidos (viven en diseno_estructural; import unidireccional sin ciclo).
from backend.services.etabs_parse import _decode_bytes, _es_xlsx
from backend.services.partidas_bridge import _get_o_crear_capitulo, _crear_o_actualizar_partida, _perfil_acero_valido, _correr_caso_acero, _marcar_gobierna_acero
from backend.services.pricing import calc_base, precio_unitario

router = APIRouter(prefix="/diseno", tags=["acero-diseno"])


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT — PUENTE ETABS -> ACERO (ratios D/C + cantidades -> Div 05)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/{pid}/import-etabs-acero")
async def import_etabs_acero(pid: str, request: Request,
                             generar: bool = False,
                             db: Session = Depends(get_db)):
    """
    Puente ETABS -> presupuesto de ACERO (Div 05). MVP: importa ratios D/C y
    cantidades; NO disena (el diseno LRFD AISC 360-16 lo hace ETABS).

    Acepta:
      - multipart/form-data: campo 'archivo' (.csv/.xlsx). Opcional 'generar'.
      - application/json: {"texto": "<csv pegado>"} o
        {"miembros": [{frame,perfil/section,rol/tipo,longitud_mL/length,dc,combo}]}

    Query / form:
      - generar=true  -> crea/actualiza partidas Div 05 por ficha (unidad mL,
                         cantidad = longitud_total_mL, precio_unitario=0; el
                         precio se inyecta luego por fichas, igual que Div 03).

    Proceso:
      1. Parsear miembros (Frame, Section, Length, DesignType, Ratio, Combo).
      2. Mapear perfil->ficha (§6.2), desambiguando duales por rol COLUMNA/VIGA.
      3. Agregar longitud por ficha, D/C max y combo gobernante; listar
         sobre-esforzados (D/C>1.0) y perfiles no mapeados.

    Salida: {status, por_ficha[], sobre_esforzados[], perfiles_no_mapeados[],
             avisos[], formato, partidas_generadas[] (si generar=true)}.

    FUERA DE ALCANCE: conexiones CV/VV/CX (otra sesion, soldadura §J) y el
    diseno LRFD de miembros (lo entrega ETABS). Aqui solo ratios + cantidades.
    """
    pres = db.query(Presupuesto).filter(Presupuesto.id == pid).first()
    if not pres:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")

    ctype = (request.headers.get("content-type") or "").lower()
    gen = bool(generar)
    parsed = {"miembros": [], "avisos": [], "formato": "texto"}

    # ── Ingesta ──────────────────────────────────────────────────────────────
    if "multipart/form-data" in ctype:
        form = await request.form()
        gen = gen or str(form.get("generar") or "").lower() in ("1", "true", "yes", "si")
        up = form.get("archivo")
        if up is not None and hasattr(up, "read"):
            raw = await up.read()
            nombre = getattr(up, "filename", "") or ""
            up_ct = getattr(up, "content_type", "") or ""
            if _es_xlsx(nombre, up_ct, raw):
                parsed = parse_acero_bytes(raw)
            else:
                parsed = parse_acero_texto(_decode_bytes(raw))
        elif form.get("texto"):
            parsed = parse_acero_texto(str(form.get("texto")))
    elif "application/json" in ctype:
        try:
            data = await request.json()
        except Exception:
            data = {}
        data = data or {}
        gen = gen or str(data.get("generar") or "").lower() in ("1", "true", "yes", "si")
        if data.get("miembros") is not None:
            miembros = []
            for m in (data.get("miembros") or []):
                miembros.append({
                    "frame": str(m.get("frame") or m.get("member") or "").strip(),
                    "perfil": str(m.get("perfil") or m.get("section") or "").strip(),
                    "rol": str(m.get("rol") or m.get("tipo") or m.get("designtype") or "").strip(),
                    "longitud_mL": m.get("longitud_mL") if m.get("longitud_mL") is not None
                                   else m.get("length") if m.get("length") is not None
                                   else m.get("longitud"),
                    "dc": m.get("dc") if m.get("dc") is not None else m.get("ratio"),
                    "combo": str(m.get("combo") or m.get("outputcase") or "").strip(),
                })
            parsed = {"miembros": miembros, "avisos": [], "formato": "json"}
        else:
            parsed = parse_acero_texto(str(data.get("texto", "") or ""))
    else:
        raw = await request.body()
        if _es_xlsx("", ctype, raw):
            parsed = parse_acero_bytes(raw)
        else:
            parsed = parse_acero_texto(_decode_bytes(raw))

    miembros = parsed.get("miembros") or []
    avisos = list(parsed.get("avisos") or [])

    if not miembros:
        return {"status": "sin_datos",
                "avisos": avisos or ["No se reconocio la tabla de miembros de acero."],
                "por_ficha": [], "sobre_esforzados": [],
                "perfiles_no_mapeados": [], "formato": parsed.get("formato"),
                "partidas_generadas": []}

    agg = agregar_por_ficha(miembros)
    avisos.extend(agg.get("avisos") or [])

    # ── Generar partidas Div 05 (opcional) ───────────────────────────────────
    partidas_generadas = []
    if gen and agg["por_ficha"]:
        cap05 = _get_o_crear_capitulo(pid, "05", db)
        for f in agg["por_ficha"]:
            ficha = f["ficha"]
            # Clave CSI por rol: vigas 05 10 00, columnas 05 20 00 (Div 05)
            clave_csi = "05 10 00" if (f["rol"] == "VIGA") else "05 20 00"
            desc = (f"Acero estructural {f['rol'].title()} {ficha} "
                    f"perfil {f['perfil']} (D/C max {f['dc_max'] if f['dc_max'] is not None else '-'})")
            p = _crear_o_actualizar_partida(
                cap05, clave_csi, desc, "mL",
                float(f["longitud_total_mL"] or 0), ficha, db,
            )
            partidas_generadas.append({
                "id": p.id, "clave": clave_csi, "ficha": ficha,
                "cantidad": float(p.cantidad), "unidad": "mL",
            })
        db.commit()

    return {
        "status": "ok",
        "formato": parsed.get("formato"),
        "n_miembros": len(miembros),
        "por_ficha": agg["por_ficha"],
        "sobre_esforzados": agg["sobre_esforzados"],
        "perfiles_no_mapeados": agg["perfiles_no_mapeados"],
        "generado": gen,
        "partidas_generadas": partidas_generadas,
        "avisos": avisos,
        "nota": ("MVP: solo se importan ratios D/C y cantidades. El diseno LRFD "
                 "lo hace ETABS; conexiones CV/VV/CX van en otra sesion. "
                 "Las partidas (?generar=true) salen con precio_unitario=0; el "
                 "precio se inyecta luego por fichas (igual que Div 03)."),
    }


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT — PUENTE ETABS -> ACERO LRFD (verificacion §D-H propia de miembros)
# A diferencia de import-etabs-acero (D/C+presupuesto), aqui SI se corre el
# motor de miembros (calculo_miembro_acero) como chequeo cruzado de ETABS.
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/{pid}/import-etabs-acero-fuerzas")
async def import_etabs_acero_fuerzas(pid: str, request: Request,
                                     db: Session = Depends(get_db)):
    """
    Puente ETABS -> diseno LRFD de MIEMBROS de acero. Corre §D-H propios.

    Acepta (igual que import-etabs-concreto):
      - multipart/form-data: 'archivo' (.csv/.xlsx) + opcional 'unidad','acero'.
      - application/json: {"texto":"<csv>"} o {"secciones":[...],"fuerzas":[...]}
        + opcional "unidad" (kgf|kn|t, default kgf), "acero" (A992).

    Mapeo ETABS -> motor:
      COLUMNA: P->Pu(compresion) · M3->Mux · M2->Muy · V2->Vu
      VIGA   : M3->Mux · V2->Vu · P->Pu axial
    Seccion ETABS -> perfil: debe existir en TABLA_W/PERFILES_ACERO. Rol
    VIGA/COLUMNA del 'uso' de la tabla (o 'rol'/DesignType si se provee).
    """
    pres = db.query(Presupuesto).filter(Presupuesto.id == pid).first()
    if not pres:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")

    ctype = (request.headers.get("content-type") or "").lower()
    unidad = "kgf"
    acero_grado = "A992"
    parsed = {"secciones": {}, "fuerzas": [], "avisos": []}

    if "multipart/form-data" in ctype:
        form = await request.form()
        unidad = str(form.get("unidad") or "kgf").lower()
        acero_grado = str(form.get("acero") or "A992").upper()
        up = form.get("archivo")
        if up is not None and hasattr(up, "read"):
            raw = await up.read()
            nombre = getattr(up, "filename", "") or ""
            up_ct = getattr(up, "content_type", "") or ""
            if _es_xlsx(nombre, up_ct, raw):
                parsed = parse_concreto_bytes(raw)
            else:
                parsed = parse_concreto_texto(_decode_bytes(raw))
        elif form.get("texto"):
            parsed = parse_concreto_texto(str(form.get("texto")))
    elif "application/json" in ctype:
        try:
            data = await request.json()
        except Exception:
            data = {}
        data = data or {}
        unidad = str(data.get("unidad") or "kgf").lower()
        acero_grado = str(data.get("acero") or "A992").upper()
        if data.get("secciones") is not None or data.get("fuerzas") is not None:
            secs = {}
            for s in (data.get("secciones") or []):
                m = str(s.get("member") or s.get("frame") or "").strip()
                if m:
                    secs[m] = {"section": str(s.get("section") or s.get("perfil") or ""),
                               "rol": str(s.get("rol") or s.get("designtype") or ""),
                               "longitud_m": s.get("longitud_m") or s.get("length")}
            parsed = {"secciones": secs, "fuerzas": (data.get("fuerzas") or []), "avisos": []}
        else:
            parsed = parse_concreto_texto(str(data.get("texto", "") or ""))
    else:
        raw = await request.body()
        if _es_xlsx("", ctype, raw):
            parsed = parse_concreto_bytes(raw)
        else:
            parsed = parse_concreto_texto(_decode_bytes(raw))

    secciones = parsed.get("secciones") or {}
    fuerzas = parsed.get("fuerzas") or []
    avisos = list(parsed.get("avisos") or [])
    f_fuerza, f_mom = factores_unidad(unidad)

    if not fuerzas:
        return {"status": "sin_datos",
                "avisos": avisos or ["No se reconocio la tabla de FUERZAS."],
                "elementos_creados": 0, "casos_creados": 0,
                "gobernantes": [], "perfiles_no_mapeados": []}

    # ── 1) Elementos de acero por miembro ────────────────────────────────────
    existentes = {e.csi: e for e in db.query(DisenoElemento).filter(
        DisenoElemento.presupuesto_id == pid).all()}
    elem_por_miembro = {}
    no_map = []
    creados = 0
    miembros = set(secciones.keys()) | {(f.get("member") or "").strip() for f in fuerzas}
    for member in sorted(m for m in miembros if m):
        sec = secciones.get(member, {})
        section = sec.get("section") or member
        perfil, uso = _perfil_acero_valido(section)
        if not perfil:
            no_map.append({"member": member, "section": section})
            continue
        rol = (sec.get("rol") or uso or "").upper()
        es_col = ("COL" in rol) or (rol == "" and uso == "COLUMNA")
        tipo_elem = "COLUMNA" if es_col else "VIGA_SIMPLE"
        L_m = sec.get("longitud_m")
        L_m = float(L_m) if L_m not in (None, "") else 0.0
        csi = f"ETABS-ACERO:{member}"
        notas = f"ETABS acero member={member} · {section} -> {perfil} ({tipo_elem})"
        elem = existentes.get(csi)
        if elem is None:
            elem = DisenoElemento(
                id=str(uuid.uuid4()), presupuesto_id=pid, csi=csi,
                type_mark=member, tipo=tipo_elem,
                material_tipo="ACERO", perfil_acero=perfil, acero_grado=acero_grado,
                longitud_m=L_m, notas=notas)
            db.add(elem); existentes[csi] = elem; creados += 1
        else:
            elem.tipo = tipo_elem
            elem.material_tipo = "ACERO"
            elem.perfil_acero = perfil
            elem.acero_grado = acero_grado
            if L_m > 0:
                elem.longitud_m = L_m
            elem.notas = notas
        elem_por_miembro[member] = elem
    db.flush()

    # ── 2) Casos por combinacion ─────────────────────────────────────────────
    nuevos = []
    casos_creados = 0
    for fz in fuerzas:
        member = (fz.get("member") or "").strip()
        elem = elem_por_miembro.get(member)
        if elem is None:
            continue
        combo = (fz.get("combo") or fz.get("outputcase") or "ETABS").strip()
        P  = (fz.get("P")  or 0) * f_fuerza
        V2 = (fz.get("V2") or 0) * f_fuerza
        M2 = (fz.get("M2") or 0) * f_mom
        M3 = (fz.get("M3") or 0) * f_mom
        caso = CasoDiseno(id=str(uuid.uuid4()), diseno_elemento_id=elem.id,
                          nombre=combo, origen="ETABS", combo_etabs=combo)
        if elem.tipo == "COLUMNA":
            caso.pu_t = abs(P); caso.mu_xx_tm = abs(M3)
            caso.mu_yy_tm = abs(M2); caso.vu_t = abs(V2)
        else:
            caso.mu_tm = abs(M3); caso.vu_t = abs(V2); caso.nu_t = P
        caso.lu_cm = float(elem.longitud_m or 0) * 100.0   # Lb = L por defecto
        db.add(caso); nuevos.append(caso); casos_creados += 1
    db.flush()

    # ── 3) Correr motor LRFD + 4) gobernante por elemento ────────────────────
    for caso in nuevos:
        _correr_caso_acero(caso, db)
    db.flush()
    gobernantes = []
    for elem in {c.diseno_elemento_id: c.elemento for c in nuevos}.values():
        _marcar_gobierna_acero(elem)
        for caso in elem.casos:
            if caso.gobierna and caso.resultado:
                r = caso.resultado
                gobernantes.append({
                    "elemento_id": elem.id, "csi": elem.csi,
                    "perfil": elem.perfil_acero, "tipo": elem.tipo,
                    "combo": caso.combo_etabs or caso.nombre,
                    "estado_gob": r.acero_estado_gob,
                    "phi_rn": float(r.acero_phi_rn_gob or 0),
                    "dc": float(r.acero_dc or 0),
                    "cumple": bool(r.acero_cumple),
                })
    db.commit()
    return {
        "status": "ok",
        "unidad_entrada": unidad,
        "acero_grado": acero_grado,
        "elementos_creados": creados,
        "casos_creados": casos_creados,
        "gobernantes": gobernantes,
        "perfiles_no_mapeados": no_map,
        "avisos": avisos,
        "nota": ("Verificacion LRFD §D-H propia como chequeo cruzado del Steel "
                 "Frame Design de ETABS. Columna asume compresion (|P|); para "
                 "uplift/tension usar caso manual. Lb=L por defecto (revisar "
                 "arriostramiento real)."),
    }


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT — ACERO: generar partidas Div 05 (suministro mL) desde elementos BD
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/{pid}/acero-generar-partidas")
def acero_generar_partidas(pid: str, db: Session = Depends(get_db)):
    """Genera partidas Div 05 (suministro, mL) desde los elementos de ACERO ya
    persistidos en la obra: perfil -> ficha VA-x/C-x -> agrega longitud por ficha.
    Claves: 05 10 00 vigas / 05 20 00 columnas. precio_unitario=0 (el precio se
    inyecta luego por fichas, igual que Div 03). Conexiones se costean aparte."""
    pres = db.query(Presupuesto).filter(Presupuesto.id == pid).first()
    if not pres:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")

    elems = db.query(DisenoElemento).filter(
        DisenoElemento.presupuesto_id == pid,
        DisenoElemento.material_tipo == "ACERO",
    ).all()
    if not elems:
        return {"status": "sin_elementos", "partidas_generadas": [], "por_ficha": [],
                "avisos": ["No hay elementos de acero en la obra. Importa de ETABS primero."]}

    miembros = []
    for el in elems:
        gob = next((c for c in el.casos if c.gobierna), None) or (el.casos[0] if el.casos else None)
        dc = None
        combo = ""
        if gob is not None:
            combo = gob.combo_etabs or gob.nombre or ""
            if gob.resultado is not None:
                dc = float(getattr(gob.resultado, "acero_dc", 0) or 0) or None
        miembros.append({
            "frame": el.type_mark or el.csi or "",
            "perfil": el.perfil_acero or "",
            "rol": "COLUMNA" if el.tipo == "COLUMNA" else "VIGA",
            "longitud_mL": float(el.longitud_m or 0),
            "dc": dc,
            "combo": combo,
        })

    agg = agregar_por_ficha(miembros)
    avisos = list(agg.get("avisos") or [])

    partidas_generadas = []
    if agg["por_ficha"]:
        cap05 = _get_o_crear_capitulo(pid, "05", db)
        for f in agg["por_ficha"]:
            ficha = f["ficha"]
            clave_csi = "05 10 00" if (f["rol"] == "VIGA") else "05 20 00"
            dcm = f["dc_max"] if f["dc_max"] is not None else "-"
            desc = (f"Acero estructural {f['rol'].title()} {ficha} "
                    f"perfil {f['perfil']} (D/C max {dcm})")
            p = _crear_o_actualizar_partida(
                cap05, clave_csi, desc, "mL",
                float(f["longitud_total_mL"] or 0), ficha, db,
            )
            partidas_generadas.append({
                "id": p.id, "clave": clave_csi, "ficha": ficha,
                "perfil": f["perfil"], "rol": f["rol"],
                "cantidad": float(p.cantidad), "unidad": "mL",
            })
        db.commit()

    return {
        "status": "ok",
        "n_elementos": len(elems),
        "partidas_generadas": partidas_generadas,
        "por_ficha": agg["por_ficha"],
        "perfiles_no_mapeados": agg.get("perfiles_no_mapeados", []),
        "avisos": avisos,
        "nota": ("Partidas Div 05 de suministro (mL) por ficha de perfil. "
                 "precio_unitario=0; el precio se inyecta por fichas. Las conexiones "
                 "se costean aparte (modulo Conexion)."),
    }


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT — CONEXION: generar partida Div 05 (pza) con insumos de la ficha
# ─────────────────────────────────────────────────────────────────────────────

class ConexionPartidaBody(BaseModel):
    """Body de /diseno/{pid}/conexion-generar-partida."""
    perfil_viga:    str   = ""
    perfil_columna: str   = ""
    tipo_conexion:  str   = "VC_CORTANTE"
    n_conexiones:   float = 1


@router.post("/{pid}/conexion-generar-partida")
def conexion_generar_partida(pid: str, body: ConexionPartidaBody,
                             db: Session = Depends(get_db)):
    """Crea/actualiza una partida Div 05 de CONEXION desde la ficha resuelta
    (CV/VV/CX) con sus insumos (BOM de la base curada). cantidad = n_conexiones (pza).
    Idempotente por (capitulo 05, csi de la ficha, type_mark)."""
    pres = db.query(Presupuesto).filter(Presupuesto.id == pid).first()
    if not pres:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")

    fr = conexion_ficha(body.perfil_viga, body.perfil_columna, body.tipo_conexion)
    if not fr.get("csi") or not fr.get("insumos_ok"):
        return {"status": "sin_ficha", "ficha": fr.get("ficha"),
                "avisos": [f"La ficha {fr.get('ficha')} no tiene insumos en la base curada."]}

    sobrecosto = float(pres.config.sobrecosto) if (pres.config and pres.config.sobrecosto is not None) else 20.0
    insumos = fr["insumos"]
    # Bucketing 3-vias (fuente unica: backend.services.pricing) para no dejar
    # unitario_matriz stale en el UPDATE -> doble conteo en /calcular (bug historico).
    costo_mo = round(sum(i["total"] for i in insumos if i["tipo"] == "MANO_OBRA"), 4)
    costo_ma = round(sum(i["total"] for i in insumos if i["tipo"] == "MATERIAL"), 4)
    matriz = round(sum(i["total"] for i in insumos if i["tipo"] not in ("MANO_OBRA", "MATERIAL")), 4)
    base = calc_base(costo_mo, costo_ma, matriz)
    pu = precio_unitario(base, sobrecosto) if base > 0 else 0.0
    n = max(float(body.n_conexiones or 1), 0.0)
    clave_csi = fr["csi"]
    tm = fr["ficha"]

    cap05 = _get_o_crear_capitulo(pid, "05", db)
    partida = db.query(Partida).filter(
        Partida.capitulo_id == cap05.id,
        Partida.clave_csi == clave_csi,
        Partida.type_mark == tm,
    ).first()
    if partida is None:
        partida = Partida(
            capitulo_id=cap05.id, clave_csi=clave_csi,
            descripcion=fr.get("descripcion") or f"Conexion {tm}",
            unidad=fr.get("unidad", "pza"), cantidad=n, revit_q=0, factor_e=1, factor_f=1,
            color_tipo="azul", costo_mo=costo_mo, costo_ma=costo_ma, unitario_matriz=matriz,
            costo_base=base, precio_unitario=pu, total=round(n * pu, 4),
            type_mark=tm, orden=len(cap05.partidas),
        )
        db.add(partida)
        db.flush()
    else:
        partida.descripcion = fr.get("descripcion") or partida.descripcion
        partida.unidad = fr.get("unidad", "pza")
        partida.cantidad = n
        partida.costo_mo = costo_mo
        partida.costo_ma = costo_ma
        partida.unitario_matriz = matriz
        partida.costo_base = base
        partida.precio_unitario = pu
        partida.total = round(n * pu, 4)
        for ip in list(partida.insumos):
            db.delete(ip)
        db.flush()

    for idx, i in enumerate(insumos):
        db.add(InsumoPartida(
            partida_id=partida.id, recurso_id=None,
            clave=i["codigo"], descripcion=i["descripcion"], unidad=i["unidad"],
            tipo=i["tipo"], cantidad=i["cantidad"], costo_unit=i["precio_unit"],
            total=i["total"], orden=idx,
        ))
    db.commit()
    return {
        "status": "ok", "ficha": tm, "csi": clave_csi,
        "descripcion": partida.descripcion, "unidad": partida.unidad,
        "cantidad": n, "n_insumos": len(insumos),
        "costo_directo": round(base, 2), "precio_unitario": round(pu, 2),
        "total": round(n * pu, 4), "partida_id": partida.id,
        "aproximado": bool(fr.get("aproximado")),
    }


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT — CONEXION: importar CSV de pyRevit (conteo de nodos) -> partidas+insumos
#   pyRevit (boton "Export Steel Connections") exporta:
#     tipo_conexion, csi_viga, perfil_viga, csi_columna, perfil_columna, cantidad
#   Aqui se DECIDE soldada vs apernada (vc_modo) y se generan las fichas Div 05
#   con insumos (materiales + mano de obra) x cantidad. La placa base NO entra
#   (ya esta en los insumos del pedestal). Solo VV y VC.
# ─────────────────────────────────────────────────────────────────────────────

_W_PERFIL_RE = re.compile(r"W\s*(\d+)\s*[Xx]\s*(\d+)", re.IGNORECASE)


def _norm_w(s: str) -> str:
    m = _W_PERFIL_RE.search(s or "")
    return "W{0}X{1}".format(m.group(1), m.group(2)) if m else ""


def _perfil_de_csi(csi: str, db: Session, fallback: str = "") -> str:
    """Perfil canonico (metrico 'W150X24') desde el keynote CSI via la BD.
    El CSV de Revit puede traer designacion US (W6x16); la ficha se resuelve por
    el perfil canonico, asi que preferimos el de la BD (descripcion de la partida)."""
    csi = (csi or "").strip()
    if csi:
        p = db.query(Partida).filter(Partida.clave_csi == csi).first()
        if p and p.descripcion:
            cand = _norm_w(p.descripcion)
            if cand:
                return cand
    return _norm_w(fallback) or (fallback or "").strip()


def _parse_pyrevit_csv(text: str) -> List[dict]:
    """Parsea el CSV crudo de pyRevit. Tolera BOM (utf-8-sig por linea), comillas y header."""
    out = []
    for raw in (text or "").splitlines():
        line = raw.replace("﻿", "").strip()
        if not line or line.startswith("#"):
            continue
        parts = [c.replace("﻿", "").strip().strip('"') for c in line.split(",")]
        if not parts or parts[0].lower() in ("tipo_conexion", "tipo"):
            continue
        if len(parts) < 6:
            continue
        try:
            n = float(parts[5])
        except (ValueError, TypeError):
            continue
        if n <= 0:
            continue
        out.append({"tipo": parts[0].upper(), "csi_v": parts[1], "perfil_v": parts[2],
                    "csi_c": parts[3], "perfil_c": parts[4], "cant": n})
    return out


class ConexionImportCSVBody(BaseModel):
    """Body de /diseno/{pid}/conexion-import-pyrevit-csv."""
    csv_text: str = ""
    vc_modo:  str = "apernada"   # decision del modulo: "apernada" (CV) | "soldada" (CX)


@router.post("/{pid}/conexion-import-pyrevit-csv")
def conexion_import_pyrevit_csv(pid: str, body: ConexionImportCSVBody,
                                db: Session = Depends(get_db)):
    """Importa el CSV de pyRevit (conteo de conexiones por nodo) y genera las
    partidas Div 05 con insumos. La decision soldada/apernada se toma AQUI
    (vc_modo): VV -> ficha VV · VC -> CV (apernada) o CX (soldada). Agrega por ficha."""
    pres = db.query(Presupuesto).filter(Presupuesto.id == pid).first()
    if not pres:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")

    rows = _parse_pyrevit_csv(body.csv_text)
    if not rows:
        return {"status": "vacio", "avisos": ["CSV sin filas validas (revisa el formato pyRevit)."]}

    modo = (body.vc_modo or "apernada").strip().lower()

    # Agregar por (tipo_estima, perfil_viga, perfil_columna) — suma cantidades.
    agg = {}
    descartados = 0
    for r in rows:
        if r["tipo"] == "VV":
            tipo_e = "VV"
        elif r["tipo"] == "VC":
            tipo_e = "SOLDADA" if modo == "soldada" else "VC_CORTANTE"
        else:
            descartados += 1
            continue
        pv = _perfil_de_csi(r["csi_v"], db, r["perfil_v"])
        pc = _perfil_de_csi(r["csi_c"], db, r["perfil_c"])
        key = (tipo_e, pv, pc)
        agg[key] = agg.get(key, 0.0) + r["cant"]

    detalle, sin_ficha = [], []
    n_part, total = 0, 0.0
    for (tipo_e, pv, pc), n in sorted(agg.items()):
        entry = {"tipo": tipo_e, "perfil_viga": pv, "perfil_columna": pc, "cantidad": n}
        res = conexion_generar_partida(
            pid,
            ConexionPartidaBody(perfil_viga=pv, perfil_columna=pc,
                                tipo_conexion=tipo_e, n_conexiones=n),
            db,
        )
        res["entrada"] = entry
        detalle.append(res)
        if res.get("status") == "ok":
            n_part += 1
            total += float(res.get("total") or 0)
        else:
            sin_ficha.append({**entry, "ficha": res.get("ficha")})

    return {
        "status": "ok",
        "modo_vc": modo,
        "filas_csv": len(rows),
        "grupos": len(agg),
        "partidas_generadas": n_part,
        "sin_ficha": sin_ficha,
        "descartados": descartados,
        "total": round(total, 2),
        "detalle": detalle,
    }


# ─────────────────────────────────────────────────────────────────────────────
# MÓDULO PLACAS BASE §J8 — pedestales P1..Pn (placa de acero sobre concreto)
# La placa base apoya la columna de acero sobre el pedestal de concreto. El
# pedestal da A2 (área de aplastamiento); la reacción ETABS (FZ) da Pu axial.
# Flujo: preseed de pedestales desde la BD -> mañana se pega Joint Reactions ->
# se corre §J8 por pedestal (envolvente de DC sobre combos). STATELESS al correr.
# ─────────────────────────────────────────────────────────────────────────────

_HYPHENS = dict.fromkeys(map(ord, "‐‑‒–—−"), "-")


def _pedestal_de_elem(e: DisenoElemento) -> dict:
    """Extrae una spec de placa base desde un DisenoElemento 'Pedestal Pn'.
    Lee de las notas/ficha: lado (->A2), perfil de columna de acero (si está),
    columnas servidas. f'c sale del elemento (concreto del pedestal)."""
    notas = (e.notas or "").translate(_HYPHENS)
    lado = 0.0
    m = re.search(r"(\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)", notas)
    if m:
        lado = float(m.group(1))
    perfil = ""
    mp = re.search(r"\bW\s*\d+\s*[xX]\s*\d+", notas)
    if mp:
        perfil = re.sub(r"\s+", "", mp.group(0)).upper().replace("X", "X")
    cols = re.findall(r"\bC\s*-?\s*(\d+)\b", notas)
    columnas = ", ".join(f"C{n}" for n in dict.fromkeys(cols))   # únicas, en orden
    return {
        "pedestal":       e.type_mark or "",
        "lado_cm":        lado,
        "A2_cm2":         round(lado * lado, 1) if lado > 0 else 0.0,
        "perfil_columna": perfil,
        "columnas":       columnas,
        "acero":          "A992",
        "fc_kg_cm2":      float(e.fc_kg_cm2 or 210),
        "joint":          "",         # lo mapea el usuario contra la tabla ETABS
        "t_placa_cm":     1.9,
        "B_placa_cm":     0.0,
        "N_placa_cm":     0.0,
        "notas":          (e.notas or "")[:140],
    }


@router.get("/{pid}/pedestales-base")
def pedestales_base(pid: str, db: Session = Depends(get_db)):
    """Preseed del módulo Placas Base: lee los pedestales (Pn) de la obra y
    devuelve una spec por pedestal (lado->A2, perfil de columna si está en las
    notas, f'c). El usuario completa el perfil faltante y el 'joint' de ETABS."""
    pres = db.query(Presupuesto).filter(Presupuesto.id == pid).first()
    if not pres:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")
    elems = db.query(DisenoElemento).filter(
        DisenoElemento.presupuesto_id == pid).all()
    peds = []
    for e in elems:
        tm = (e.type_mark or "").strip()
        es_ped = bool(re.match(r"^P-?\d+$", tm)) or ("pedestal" in (e.notas or "").lower())
        if es_ped and (e.material_tipo or "CONCRETO").upper() == "CONCRETO":
            peds.append(_pedestal_de_elem(e))
    # ordenar P1, P2, ... por número
    def _num(p):
        m = re.search(r"\d+", p.get("pedestal") or "")
        return int(m.group(0)) if m else 999
    peds.sort(key=_num)
    return {"status": "ok", "n_pedestales": len(peds), "pedestales": peds,
            "avisos": ([] if peds else
                       ["No se encontraron pedestales (Pn) en la obra."])}


class PlacaBaseSpec(BaseModel):
    """Una placa base a verificar: pedestal + columna de acero + joint ETABS."""
    pedestal:       str   = ""
    joint:          str   = ""     # joint/label de ETABS (lo mapea el usuario)
    perfil_columna: str   = ""
    acero:          str   = "A992"
    fc_kg_cm2:      float = 210.0
    lado_cm:        float = 0.0    # lado del pedestal -> A2 (si A2_cm2=0)
    A2_cm2:         float = 0.0    # 0 -> lado_cm^2
    t_placa_cm:     float = 1.9
    B_placa_cm:     float = 0.0    # 0 -> deriva del perfil columna
    N_placa_cm:     float = 0.0


class PlacasBaseETABS(BaseModel):
    """Body de /diseno/{pid}/placas-base-etabs."""
    unidad:     str   = "kgf"   # kgf|kn|t -> a t / t·m
    texto:      str   = ""      # Joint Reactions pegado (Joint,OutputCase,FX,FY,FZ,...)
    reacciones: list  = []      # alternativa estructurada
    pedestales: List[PlacaBaseSpec] = []


def _combo_r(r: dict) -> str:
    return str(r.get("combo") or r.get("outputcase") or "").strip()


@router.post("/{pid}/placas-base-etabs")
def placas_base_etabs(pid: str, body: PlacasBaseETABS,
                      db: Session = Depends(get_db)):
    """Diseño masivo de placas base §J8 desde Joint Reactions de ETABS. Por cada
    pedestal toma la ENVOLVENTE de DC sobre sus combinaciones (Pu=|FZ|, Vu=hypot
    (FX,FY), A2=lado²). Sin specs -> envolvente de reacciones por nudo. Stateless."""
    pres = db.query(Presupuesto).filter(Presupuesto.id == pid).first()
    if not pres:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")

    if body.reacciones:
        reacc = list(body.reacciones); formato = "json"
    elif (body.texto or "").strip():
        reacc = parse_reacciones_texto(body.texto).get("reacciones") or []; formato = "texto"
    else:
        reacc = []; formato = "vacio"

    if not reacc:
        return {"status": "sin_datos", "formato": formato,
                "avisos": ["No se reconocio la tabla de JOINT REACTIONS de ETABS."],
                "placas": [], "reacciones_por_nudo": []}

    ff, fm = factores_unidad(body.unidad)
    by_joint: dict = {}
    for r in reacc:
        j = str(r.get("joint") or "").strip()
        if j:
            by_joint.setdefault(j, []).append(r)

    # ── Sin specs: envolvente de reacciones por nudo (para mapear joints) ────
    if not body.pedestales:
        nudos = []
        for j, rl in sorted(by_joint.items()):
            best = max(rl, key=lambda r: abs(float(r.get("FZ") or 0)))
            pu = abs(float(best.get("FZ") or 0)) * ff
            vu = math.hypot(float(best.get("FX") or 0), float(best.get("FY") or 0)) * ff
            nudos.append({"joint": j, "n_combos": len(rl),
                          "pu_max_t": round(pu, 3), "vu_t": round(vu, 3),
                          "combo": _combo_r(best)})
        nudos.sort(key=lambda n: -n["pu_max_t"])
        return {"status": "solo_reacciones", "formato": formato, "unidad": body.unidad,
                "n_nudos": len(nudos), "reacciones_por_nudo": nudos, "placas": [],
                "avisos": ["Sin specs: envolvente de reacciones por nudo. Mapea cada "
                           "joint a su pedestal + perfil de columna para correr §J8."]}

    # ── Con specs: §J8 envolvente de DC sobre las combinaciones del joint ────
    placas, sobre, sin_reacc, sin_perfil = [], [], [], []
    for sp in body.pedestales:
        A2 = sp.A2_cm2 or (sp.lado_cm * sp.lado_cm if sp.lado_cm > 0 else 0.0)
        base = {"pedestal": sp.pedestal, "joint": sp.joint,
                "perfil_columna": sp.perfil_columna, "lado_cm": sp.lado_cm,
                "A2_cm2": round(A2, 1), "fc_kg_cm2": sp.fc_kg_cm2}
        if not sp.perfil_columna:
            sin_perfil.append(sp.pedestal)
            placas.append({**base, "dc": None, "cumple": False, "error": "sin perfil de columna"})
            continue
        rl = by_joint.get((sp.joint or "").strip(), [])
        if not rl:
            sin_reacc.append(sp.pedestal)
            placas.append({**base, "dc": None, "cumple": False, "error": "sin reacciones (joint no coincide)"})
            continue
        elem = {"tipo_conexion": "PLACA_BASE", "perfil_viga": "",
                "perfil_columna": sp.perfil_columna, "acero": sp.acero,
                "t_placa_cm": sp.t_placa_cm, "fc_kg_cm2": sp.fc_kg_cm2,
                "B_placa_cm": sp.B_placa_cm, "N_placa_cm": sp.N_placa_cm, "A2_cm2": A2}
        mejor = None
        for r in rl:
            pu = abs(float(r.get("FZ") or 0)) * ff
            vu = math.hypot(float(r.get("FX") or 0), float(r.get("FY") or 0)) * ff
            res = calcular_conexion(elem, {"pu_t": pu, "vu_t": vu, "nu_t": 0.0, "mu_tm": 0.0})
            dc = res.get("dc_ratio")
            if dc is None:
                continue
            if mejor is None or dc > mejor["dc"]:
                j8 = res.get("j8") or {}
                mejor = {"combo": _combo_r(r), "pu_t": round(pu, 3), "vu_t": round(vu, 3),
                         "dc": dc, "estado_gob": res.get("estado_gobernante"),
                         "cumple": bool(res.get("cumple")),
                         "phiPp_t": j8.get("phiPp_t"), "B": j8.get("B"), "N": j8.get("N"),
                         "A1": j8.get("A1"), "A2": j8.get("A2"),
                         "tp_req": j8.get("tp_req"), "tp": j8.get("tp"),
                         "ok_espesor": j8.get("ok_espesor")}
        placas.append({**base, **(mejor or {"dc": None, "cumple": False, "error": "sin DC calculado"})})
        if mejor and mejor["dc"] is not None and mejor["dc"] > 1.0:
            sobre.append(sp.pedestal)

    placas.sort(key=lambda p: (p.get("dc") is None, -(p.get("dc") or 0.0)))
    avisos = []
    if sin_perfil:
        avisos.append(f"{len(sin_perfil)} pedestal(es) sin perfil de columna: {', '.join(sin_perfil)}.")
    if sin_reacc:
        avisos.append(f"{len(sin_reacc)} pedestal(es) sin reacciones (joint no coincide): {', '.join(sin_reacc)}.")
    return {"status": "ok", "formato": formato, "unidad": body.unidad,
            "n_placas": len(placas), "n_sobre_esforzadas": len(sobre),
            "sobre_esforzadas": sobre, "sin_reacciones": sin_reacc,
            "sin_perfil": sin_perfil, "placas": placas, "avisos": avisos}
