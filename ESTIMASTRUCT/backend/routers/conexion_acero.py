# -*- coding: utf-8 -*-
"""
Router — Conexiones de Acero (AISC 360-16 §J, LRFD)
===================================================
prefix /conexion-acero.  STATELESS: no toca BD, no crea tablas, no genera
partidas todavia (eso es fase posterior con confirmacion del Director).

Endpoints:
  GET  /conexion-acero/catalogo        -> pobla menus (vigas/columnas/conexiones)
  POST /conexion-acero/memoria-rapida  -> Hoja en vivo (memoria_conexion + ficha)
"""

import uuid, json
from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from backend.db import get_db
from backend.models import Presupuesto, ConexionAcero, ConexionCaso, ConexionResultado
from backend.calculo_conexion_acero import memoria_conexion, calcular_conexion
from backend.acero_ficha import catalogo_acero, conexion_ficha
from backend.seccion_ficha import factores_unidad, parse_concreto_texto

router = APIRouter(prefix="/conexion-acero", tags=["conexion-acero"])


@router.get("/catalogo")
def get_catalogo():
    """Catalogo de perfiles y fichas de conexion para poblar los menus.
    El frontend NO hardcodea perfiles; los pide aqui (fuente unica)."""
    return catalogo_acero()


class ConexionRapida(BaseModel):
    tipo_conexion:    str   = "VC_CORTANTE"   # VC_CORTANTE|VC_MOMENTO|VV|SOLDADA|PLACA_BASE
    perfil_viga:      str   = ""
    perfil_columna:   str   = ""
    acero:            str   = "A992"
    t_placa_cm:       float = 0.95
    perno_grado:      str   = "A325"
    perno_d_cm:       float = 1.9
    n_pernos:         int   = 3
    roscas_en_corte:  bool  = True
    w_filete_cm:      float = 0.0
    L_soldadura_cm:   float = 0.0
    vu_t:             float = 0.0
    nu_t:             float = 0.0
    mu_tm:            float = 0.0
    # Placa base §J8 (vienen de ETABS pero quedan editables como variables)
    pu_t:             float = 0.0     # axial de columna (compresión)
    fc_kg_cm2:        float = 210.0   # f'c del concreto del pedestal/zapata
    B_placa_cm:       float = 0.0     # ancho placa (0 → derivar de columna)
    N_placa_cm:       float = 0.0     # largo placa (0 → derivar de columna)
    A2_cm2:           float = 0.0     # área pedestal (0 → = A1, conservador)


@router.post("/memoria-rapida")
def memoria_rapida_conexion(body: ConexionRapida):
    """Calculadora en vivo de conexiones: geometria+demanda -> memoria narrada.
    Devuelve memoria_conexion (meta/pasos/constantes) con la ficha resuelta. NO toca BD."""
    elem = {
        "tipo_conexion":   body.tipo_conexion,
        "perfil_viga":     body.perfil_viga,
        "perfil_columna":  body.perfil_columna,
        "acero":           body.acero,
        "t_placa_cm":      body.t_placa_cm,
        "perno_grado":     body.perno_grado,
        "perno_d_cm":      body.perno_d_cm,
        "n_pernos":        body.n_pernos,
        "roscas_en_corte": body.roscas_en_corte,
        "w_filete_cm":     body.w_filete_cm,
        "L_soldadura_cm":  body.L_soldadura_cm,
        "fc_kg_cm2":       body.fc_kg_cm2,
        "B_placa_cm":      body.B_placa_cm,
        "N_placa_cm":      body.N_placa_cm,
        "A2_cm2":          body.A2_cm2,
    }
    caso = {"vu_t": body.vu_t, "nu_t": body.nu_t, "mu_tm": body.mu_tm, "pu_t": body.pu_t}
    mem = memoria_conexion(elem, caso)
    mem["ficha"] = conexion_ficha(body.perfil_viga, body.perfil_columna, body.tipo_conexion)
    return mem


# ─────────────────────────────────────────────────────────────────────────────
# R4 — IMPORT MASIVO DE FUERZAS-NUDO ETABS -> CONEXIONES (batch §J, STATELESS)
# Parsea la tabla de fuerzas de ETABS (member, P, V2, M2, M3, combo), agrupa por
# nudo y, por cada conexion especificada, toma la ENVOLVENTE de DC sobre todas
# las combinaciones del miembro. Sin specs -> devuelve la envolvente de fuerzas
# por nudo (para que el usuario arme las specs). NO toca BD.
# ─────────────────────────────────────────────────────────────────────────────

class ConexionSpecLote(BaseModel):
    """Una conexion a verificar: a que miembro (nudo) pertenece + su config §J.
    Las fuerzas salen de la tabla ETABS por 'member'; el resto son variables."""
    member:           str   = ""             # debe coincidir con 'member' de la tabla
    tipo_conexion:    str   = "VC_CORTANTE"   # VC_CORTANTE|VC_MOMENTO|VV|SOLDADA|PLACA_BASE
    perfil_viga:      str   = ""
    perfil_columna:   str   = ""
    acero:            str   = "A992"
    t_placa_cm:       float = 0.95
    perno_grado:      str   = "A325"
    perno_d_cm:       float = 1.9
    n_pernos:         int   = 3
    roscas_en_corte:  bool  = True
    w_filete_cm:      float = 0.0
    L_soldadura_cm:   float = 0.0
    fc_kg_cm2:        float = 210.0
    B_placa_cm:       float = 0.0
    N_placa_cm:       float = 0.0
    A2_cm2:           float = 0.0


class ConexionLoteETABS(BaseModel):
    """Body de /conexion-acero/import-etabs-fuerzas."""
    unidad:      str   = "kgf"   # kgf|kn|t -> se lleva a t / t·m (factores_unidad)
    texto:       str   = ""      # tabla ETABS pegada (member,P,V2,M2,M3,combo)
    fuerzas:     list  = []      # alternativa estructurada [{member,P,V2,M2,M3,combo}]
    conexiones:  List[ConexionSpecLote] = []   # specs por nudo
    # ── Persistencia masiva (opcional). Si persistir y pid: guarda cada conexion
    #    del lote (combo gobernante) en conexion_acero/_caso/_resultado. ──────────
    pid:             str  = ""     # presupuesto destino (requerido para persistir)
    persistir:       bool = False  # guarda las conexiones spec'd con su envolvente
    generar_partidas: bool = False # ademas crea/actualiza partidas Div 05 por ficha


def _elem_from_spec(sp: ConexionSpecLote) -> dict:
    """ConexionSpecLote -> dict de elem que consume calcular_conexion."""
    return {
        "tipo_conexion":   sp.tipo_conexion,
        "perfil_viga":     sp.perfil_viga,
        "perfil_columna":  sp.perfil_columna,
        "acero":           sp.acero,
        "t_placa_cm":      sp.t_placa_cm,
        "perno_grado":     sp.perno_grado,
        "perno_d_cm":      sp.perno_d_cm,
        "n_pernos":        sp.n_pernos,
        "roscas_en_corte": sp.roscas_en_corte,
        "w_filete_cm":     sp.w_filete_cm,
        "L_soldadura_cm":  sp.L_soldadura_cm,
        "fc_kg_cm2":       sp.fc_kg_cm2,
        "B_placa_cm":      sp.B_placa_cm,
        "N_placa_cm":      sp.N_placa_cm,
        "A2_cm2":          sp.A2_cm2,
    }


def _demanda_lote(tipo: str, fz: dict, ff: float, fm: float) -> dict:
    """Fuerzas-nudo ETABS (en su unidad) -> demanda de conexion (t / t·m).
      cortante/VV/soldada: Vu=|V2|, Nu=P axial, sin Mu
      VC_MOMENTO        : Vu=|V2|, Mu=|M3|, Nu=P
      PLACA_BASE        : Pu=|P| (axial de columna/reaccion), Vu=|V2|"""
    P  = float(fz.get("P")  or 0) * ff
    V2 = float(fz.get("V2") or 0) * ff
    M3 = float(fz.get("M3") or 0) * fm
    vu, mu, axial = abs(V2), abs(M3), P
    if tipo == "PLACA_BASE":
        return {"vu_t": vu, "nu_t": 0.0, "mu_tm": 0.0, "pu_t": abs(axial)}
    if tipo == "VC_MOMENTO":
        return {"vu_t": vu, "nu_t": axial, "mu_tm": mu, "pu_t": 0.0}
    return {"vu_t": vu, "nu_t": axial, "mu_tm": 0.0, "pu_t": 0.0}


def _combo_de(fz: dict) -> str:
    return str(fz.get("combo") or fz.get("outputcase") or "").strip()


@router.post("/import-etabs-fuerzas")
def import_etabs_fuerzas(body: ConexionLoteETABS, db: Session = Depends(get_db)):
    """Import masivo: fuerzas-nudo ETABS -> verificacion §J por conexion.

    Acepta {unidad, texto|fuerzas[], conexiones[]}. Por cada spec de conexion
    corre calcular_conexion con la demanda de CADA combinacion del miembro y se
    queda con la ENVOLVENTE (mayor DC). Sin conexiones[] devuelve la envolvente
    de fuerzas por nudo. STATELESS (no persiste; las partidas se generan aparte)."""
    if body.fuerzas:
        fuerzas = list(body.fuerzas); formato = "json"
    elif (body.texto or "").strip():
        fuerzas = parse_concreto_texto(body.texto).get("fuerzas") or []; formato = "texto"
    else:
        fuerzas = []; formato = "vacio"

    if not fuerzas:
        return {"status": "sin_datos", "formato": formato,
                "avisos": ["No se reconocio la tabla de FUERZAS de ETABS."],
                "conexiones": [], "demanda_por_nudo": []}

    ff, fm = factores_unidad(body.unidad)
    by_member: dict = {}
    for fz in fuerzas:
        m = str(fz.get("member") or fz.get("frame") or "").strip()
        if m:
            by_member.setdefault(m, []).append(fz)

    # ── Sin specs: envolvente de fuerzas por nudo (para armar specs) ──────────
    if not body.conexiones:
        nudos = []
        for m, fl in sorted(by_member.items()):
            def _env(key, fac):
                best = max(fl, key=lambda f: abs(float(f.get(key) or 0)))
                return abs(float(best.get(key) or 0)) * fac, _combo_de(best)
            v, vc = _env("V2", ff); mm, mc = _env("M3", fm); p, pc = _env("P", ff)
            nudos.append({"member": m, "n_combos": len(fl),
                          "vu_max_t": round(v, 3),  "combo_v": vc,
                          "mu_max_tm": round(mm, 3), "combo_m": mc,
                          "p_max_t": round(p, 3),    "combo_p": pc})
        return {"status": "solo_fuerzas", "formato": formato, "unidad": body.unidad,
                "n_nudos": len(nudos), "demanda_por_nudo": nudos, "conexiones": [],
                "avisos": ["Sin specs de conexion: envolvente de fuerzas por nudo. "
                           "Define tipo+perfiles por miembro para calcular §J."]}

    # ── Con specs: envolvente de DC sobre las combinaciones del miembro ──────
    resultados, sobre, sin_fuerza = [], [], []
    for sp in body.conexiones:
        combos = by_member.get((sp.member or "").strip(), [])
        fr = conexion_ficha(sp.perfil_viga, sp.perfil_columna, sp.tipo_conexion)
        if not combos:
            sin_fuerza.append(sp.member)
            continue
        elem = _elem_from_spec(sp)
        mejor = None
        for fz in combos:
            caso = _demanda_lote(sp.tipo_conexion, fz, ff, fm)
            res = calcular_conexion(elem, caso)
            dc = res.get("dc_ratio")
            if dc is None:
                continue
            if mejor is None or dc > mejor["dc"]:
                mejor = {"combo": _combo_de(fz), "dc": dc,
                         "estado_gob": res.get("estado_gobernante"),
                         "phi_rn": res.get("phi_rn_gobernante"),
                         "demanda_t": res.get("demanda_t"),
                         "cumple": bool(res.get("cumple")),
                         "demanda": caso}
        row = {"member": sp.member, "tipo_conexion": sp.tipo_conexion,
               "perfil_viga": sp.perfil_viga, "perfil_columna": sp.perfil_columna,
               "ficha": fr.get("ficha"), "rotulo": fr.get("rotulo"),
               "aproximado": bool(fr.get("aproximado")),
               **(mejor or {"combo": "", "dc": None, "estado_gob": None,
                            "phi_rn": None, "demanda_t": None, "cumple": False,
                            "demanda": {}})}
        resultados.append(row)
        if mejor and mejor["dc"] is not None and mejor["dc"] > 1.0:
            sobre.append(sp.member)

    resultados.sort(key=lambda r: (r["dc"] is None, -(r["dc"] or 0.0)))
    avisos = []
    if sin_fuerza:
        avisos.append(f"{len(sin_fuerza)} conexion(es) sin fuerzas en la tabla "
                      f"(member no coincide): {', '.join(str(x) for x in sin_fuerza)}.")

    # ── Persistencia masiva (opcional) ───────────────────────────────────────
    persistidas, partidas_generadas = [], []
    if body.persistir:
        if not body.pid:
            avisos.append("persistir=true pero falta 'pid': no se guardo nada.")
        elif not db.query(Presupuesto).filter(Presupuesto.id == body.pid).first():
            avisos.append(f"Presupuesto '{body.pid}' no existe: no se persistio el lote.")
        else:
            existentes = {c.csi: c for c in db.query(ConexionAcero).filter(
                ConexionAcero.presupuesto_id == body.pid).all() if c.csi}
            por_ficha = {}   # (tipo, pv, pc) -> n
            for sp in body.conexiones:
                row = next((r for r in resultados if r["member"] == sp.member
                            and r["dc"] is not None), None)
                if row is None:
                    continue   # sin fuerzas / sin DC -> no se persiste
                csi = f"ETABS:{sp.member}"
                c = existentes.get(csi)
                if c is None:
                    c = ConexionAcero(id=str(uuid.uuid4()), presupuesto_id=body.pid, csi=csi)
                    db.add(c); existentes[csi] = c
                # Campos de geometria desde el spec
                c.type_mark      = row.get("ficha") or ""
                c.tipo_conexion  = sp.tipo_conexion
                c.perfil_viga    = sp.perfil_viga
                c.perfil_columna = sp.perfil_columna
                c.acero          = sp.acero
                c.t_placa_cm     = sp.t_placa_cm
                c.perno_grado    = sp.perno_grado
                c.perno_d_cm     = sp.perno_d_cm
                c.n_pernos       = sp.n_pernos
                c.roscas_en_corte = sp.roscas_en_corte
                c.w_filete_cm    = sp.w_filete_cm
                c.L_soldadura_cm = sp.L_soldadura_cm
                c.fc_kg_cm2      = sp.fc_kg_cm2
                c.B_placa_cm     = sp.B_placa_cm
                c.N_placa_cm     = sp.N_placa_cm
                c.A2_cm2         = sp.A2_cm2
                c.notas          = f"ETABS lote · combo gob {row.get('combo') or '-'}"
                db.flush()
                # Reemplaza casos previos por el caso de la envolvente (combo gobernante)
                for k in list(c.casos):
                    db.delete(k)
                db.flush()
                dem = row.get("demanda") or {}
                caso = ConexionCaso(
                    id=str(uuid.uuid4()), conexion_id=c.id,
                    nombre=row.get("combo") or "ETABS", origen="ETABS",
                    combo_etabs=row.get("combo") or "",
                    vu_t=float(dem.get("vu_t") or 0), nu_t=float(dem.get("nu_t") or 0),
                    mu_tm=float(dem.get("mu_tm") or 0), pu_t=float(dem.get("pu_t") or 0))
                db.add(caso); db.flush()
                _correr_conexion_caso(caso, db); db.flush()
                _marcar_gobierna_conexion(c)
                persistidas.append({"id": c.id, "csi": csi, "ficha": c.type_mark,
                                    "dc": row.get("dc"), "cumple": row.get("cumple")})
                key = (sp.tipo_conexion, sp.perfil_viga, sp.perfil_columna)
                por_ficha[key] = por_ficha.get(key, 0) + 1
            db.commit()

            if body.generar_partidas and por_ficha:
                # Lazy import para evitar ciclo de modulos entre routers.
                from backend.routers.acero_diseno import (conexion_generar_partida,
                                                   ConexionPartidaBody)
                for (tipo, pv, pc), n in por_ficha.items():
                    pres = conexion_generar_partida(
                        body.pid,
                        ConexionPartidaBody(perfil_viga=pv, perfil_columna=pc,
                                            tipo_conexion=tipo, n_conexiones=n),
                        db)
                    partidas_generadas.append(pres)

    return {"status": "ok", "formato": formato, "unidad": body.unidad,
            "n_conexiones": len(resultados), "n_sobre_esforzadas": len(sobre),
            "sobre_esforzadas": sobre, "sin_fuerzas": sin_fuerza,
            "conexiones": resultados, "avisos": avisos,
            "persistidas": persistidas, "n_persistidas": len(persistidas),
            "partidas_generadas": partidas_generadas}


# ─────────────────────────────────────────────────────────────────────────────
# R5 — PERSISTENCIA DE CONEXIONES (§J).  CRUD + cálculo persistido.
# Tablas conexion_acero / conexion_caso / conexion_resultado (espeja Diseño).
# ─────────────────────────────────────────────────────────────────────────────

_CAMPOS_CONEXION = (
    "csi", "type_mark", "tipo_conexion", "perfil_viga", "perfil_columna", "acero", "notas",
    "t_placa_cm", "perno_grado", "perno_d_cm", "n_pernos", "roscas_en_corte",
    "w_filete_cm", "L_soldadura_cm", "fc_kg_cm2", "B_placa_cm", "N_placa_cm", "A2_cm2",
)


class CasoIn(BaseModel):
    nombre:      str   = "D+L"
    origen:      str   = "MANUAL"   # MANUAL | ETABS
    combo_etabs: str   = ""
    vu_t:        float = 0.0
    nu_t:        float = 0.0
    mu_tm:       float = 0.0
    pu_t:        float = 0.0


class ConexionIn(BaseModel):
    csi:             str   = ""
    type_mark:       str   = ""
    tipo_conexion:   str   = "VC_CORTANTE"
    perfil_viga:     str   = ""
    perfil_columna:  str   = ""
    acero:           str   = "A992"
    notas:           str   = ""
    t_placa_cm:      float = 0.95
    perno_grado:     str   = "A325"
    perno_d_cm:      float = 1.9
    n_pernos:        int   = 3
    roscas_en_corte: bool  = True
    w_filete_cm:     float = 0.0
    L_soldadura_cm:  float = 0.0
    fc_kg_cm2:       float = 210.0
    B_placa_cm:      float = 0.0
    N_placa_cm:      float = 0.0
    A2_cm2:          float = 0.0
    casos:           List[CasoIn] = []


def _aplica_campos(c: ConexionAcero, b: ConexionIn):
    for f in _CAMPOS_CONEXION:
        setattr(c, f, getattr(b, f))


def _conexion_elem_dict(c: ConexionAcero) -> dict:
    return {
        "tipo_conexion": c.tipo_conexion, "perfil_viga": c.perfil_viga or "",
        "perfil_columna": c.perfil_columna or "", "acero": c.acero or "A992",
        "t_placa_cm": float(c.t_placa_cm or 0), "perno_grado": c.perno_grado or "A325",
        "perno_d_cm": float(c.perno_d_cm or 0), "n_pernos": int(c.n_pernos or 0),
        "roscas_en_corte": bool(c.roscas_en_corte), "w_filete_cm": float(c.w_filete_cm or 0),
        "L_soldadura_cm": float(c.L_soldadura_cm or 0), "fc_kg_cm2": float(c.fc_kg_cm2 or 210),
        "B_placa_cm": float(c.B_placa_cm or 0), "N_placa_cm": float(c.N_placa_cm or 0),
        "A2_cm2": float(c.A2_cm2 or 0),
    }


def _correr_conexion_caso(caso: ConexionCaso, db: Session):
    """Corre §J (calcular_conexion) y persiste/actualiza ConexionResultado. Sin commit."""
    elem = _conexion_elem_dict(caso.conexion)
    res = calcular_conexion(elem, {"vu_t": float(caso.vu_t or 0), "nu_t": float(caso.nu_t or 0),
                                   "mu_tm": float(caso.mu_tm or 0), "pu_t": float(caso.pu_t or 0)})
    r = caso.resultado
    if not r:
        r = ConexionResultado(id=str(uuid.uuid4()), caso_id=caso.id)
        caso.resultado = r; db.add(r)
    r.estado_gob   = res.get("estado_gobernante") or ""
    r.phi_rn_gob   = round(float(res.get("phi_rn_gobernante") or 0), 4)
    r.demanda_t    = round(float(res.get("demanda_t") or 0), 4)
    r.dc           = round(float(res.get("dc_ratio") or 0), 4)
    r.cumple       = bool(res.get("cumple"))
    r.estados_json = json.dumps(res.get("estados") or {}, ensure_ascii=False)
    r.j8_json      = json.dumps(res.get("j8") or {}, ensure_ascii=False)
    r.calculado_at = datetime.utcnow()
    return r


def _marcar_gobierna_conexion(c: ConexionAcero):
    mejor, mid = -1.0, None
    for caso in c.casos:
        if caso.resultado and caso.resultado.dc is not None:
            dc = float(caso.resultado.dc or 0)
            if dc > mejor:
                mejor, mid = dc, caso.id
    for caso in c.casos:
        caso.gobierna = (caso.id == mid)


def _res_dict(r: ConexionResultado):
    if not r:
        return None
    return {"estado_gob": r.estado_gob, "phi_rn": float(r.phi_rn_gob or 0),
            "demanda_t": float(r.demanda_t or 0), "dc": float(r.dc or 0),
            "cumple": bool(r.cumple)}


def _conexion_to_dict(c: ConexionAcero, full: bool = False) -> dict:
    gob = next((k for k in c.casos if k.gobierna), None) or (c.casos[0] if c.casos else None)
    d = {"id": c.id, "presupuesto_id": c.presupuesto_id, "csi": c.csi, "type_mark": c.type_mark,
         "tipo_conexion": c.tipo_conexion, "perfil_viga": c.perfil_viga,
         "perfil_columna": c.perfil_columna, "acero": c.acero, "notas": c.notas,
         "n_casos": len(c.casos), "partida_id": c.partida_id,
         "t_placa_cm": float(c.t_placa_cm or 0), "perno_grado": c.perno_grado,
         "perno_d_cm": float(c.perno_d_cm or 0), "n_pernos": int(c.n_pernos or 0),
         "roscas_en_corte": bool(c.roscas_en_corte), "w_filete_cm": float(c.w_filete_cm or 0),
         "L_soldadura_cm": float(c.L_soldadura_cm or 0), "fc_kg_cm2": float(c.fc_kg_cm2 or 210),
         "B_placa_cm": float(c.B_placa_cm or 0), "N_placa_cm": float(c.N_placa_cm or 0),
         "A2_cm2": float(c.A2_cm2 or 0),
         "gobernante": (None if not (gob and gob.resultado) else
                        {"caso": gob.nombre, "combo": gob.combo_etabs, **_res_dict(gob.resultado)})}
    if full:
        d["casos"] = [{"id": k.id, "nombre": k.nombre, "origen": k.origen,
                       "combo_etabs": k.combo_etabs, "gobierna": bool(k.gobierna),
                       "vu_t": float(k.vu_t or 0), "nu_t": float(k.nu_t or 0),
                       "mu_tm": float(k.mu_tm or 0), "pu_t": float(k.pu_t or 0),
                       "resultado": _res_dict(k.resultado)} for k in c.casos]
    return d


def _get_conexion(cid: str, db: Session) -> ConexionAcero:
    c = db.query(ConexionAcero).filter(ConexionAcero.id == cid).first()
    if not c:
        raise HTTPException(status_code=404, detail="Conexión no encontrada")
    return c


@router.post("/{pid}/conexiones")
def crear_conexion(pid: str, body: ConexionIn, db: Session = Depends(get_db)):
    """Crea una conexión persistente con sus casos (demandas), corre §J y guarda
    el resultado. Si no se pasan casos, crea uno por defecto (demanda 0)."""
    if not db.query(Presupuesto).filter(Presupuesto.id == pid).first():
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")
    c = ConexionAcero(id=str(uuid.uuid4()), presupuesto_id=pid)
    _aplica_campos(c, body)
    db.add(c); db.flush()
    casos = body.casos or [CasoIn()]
    for ci in casos:
        db.add(ConexionCaso(id=str(uuid.uuid4()), conexion_id=c.id, nombre=ci.nombre,
                            origen=ci.origen, combo_etabs=ci.combo_etabs,
                            vu_t=ci.vu_t, nu_t=ci.nu_t, mu_tm=ci.mu_tm, pu_t=ci.pu_t))
    db.flush()
    for caso in c.casos:
        _correr_conexion_caso(caso, db)
    db.flush(); _marcar_gobierna_conexion(c); db.commit()
    return _conexion_to_dict(c, full=True)


@router.get("/{pid}/conexiones")
def listar_conexiones(pid: str, db: Session = Depends(get_db)):
    """Lista las conexiones guardadas del presupuesto con su gobernante."""
    if not db.query(Presupuesto).filter(Presupuesto.id == pid).first():
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")
    cs = db.query(ConexionAcero).filter(
        ConexionAcero.presupuesto_id == pid).order_by(ConexionAcero.created_at).all()
    return {"n": len(cs), "conexiones": [_conexion_to_dict(c) for c in cs]}


@router.get("/conexiones/{cid}")
def get_conexion(cid: str, db: Session = Depends(get_db)):
    """Detalle de una conexión (incluye casos + resultados)."""
    return _conexion_to_dict(_get_conexion(cid, db), full=True)


@router.put("/conexiones/{cid}")
def actualizar_conexion(cid: str, body: ConexionIn, db: Session = Depends(get_db)):
    """Actualiza geometría/identificación. Si se pasan casos, REEMPLAZA los casos.
    Recalcula §J y persiste."""
    c = _get_conexion(cid, db)
    _aplica_campos(c, body)
    if body.casos:
        for k in list(c.casos):
            db.delete(k)
        db.flush()
        for ci in body.casos:
            db.add(ConexionCaso(id=str(uuid.uuid4()), conexion_id=c.id, nombre=ci.nombre,
                                origen=ci.origen, combo_etabs=ci.combo_etabs,
                                vu_t=ci.vu_t, nu_t=ci.nu_t, mu_tm=ci.mu_tm, pu_t=ci.pu_t))
        db.flush()
    for caso in c.casos:
        _correr_conexion_caso(caso, db)
    db.flush(); _marcar_gobierna_conexion(c); db.commit()
    return _conexion_to_dict(c, full=True)


@router.post("/conexiones/{cid}/recalcular")
def recalcular_conexion(cid: str, db: Session = Depends(get_db)):
    """Re-corre §J de todos los casos y re-marca el gobernante. Persiste."""
    c = _get_conexion(cid, db)
    for caso in c.casos:
        _correr_conexion_caso(caso, db)
    db.flush(); _marcar_gobierna_conexion(c); db.commit()
    return _conexion_to_dict(c, full=True)


@router.delete("/conexiones/{cid}")
def eliminar_conexion(cid: str, db: Session = Depends(get_db)):
    """Borra una conexión y sus casos/resultados (cascade)."""
    c = _get_conexion(cid, db)
    db.delete(c); db.commit()
    return {"status": "ok", "deleted": cid}
