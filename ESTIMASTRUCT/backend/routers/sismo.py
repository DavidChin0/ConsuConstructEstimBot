from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from backend.db import get_db
from backend.models import Presupuesto, ContextoSismico
from backend.calculo_sismico_choc08 import (
    memoria_sismica, espectro_csv, ZONAS, SUELOS,
    coef_sismico, periodo_metodo_a, cortante_estatico,
    escalado_cortante, verificar_derivas, deriva_limite as _calc_deriva_limite,
    C_RW_MIN,
)
from backend.services.etabs_parse import _decode_bytes, _es_xlsx
from backend.etabs_procedimiento import (
    ORIGEN_INPUTS, PROCEDIMIENTO, EXPORT_ETABS_DOC,
    parse_export_etabs, parse_export_etabs_bytes,
)
from backend.calculo_estructural import RECUB_DEFAULT
import uuid, os, re, json

# Defaults CC-135 (Comayagua) usados cuando no hay ContextoSismico persistido
_SISMO_DEFAULTS = {
    "zona": "3b", "suelo": "S1", "importancia_i": 1.0,
    "rw": 8.0, "hn_m": 3.0, "w_t": 1206.0,
}

# Municipios Honduras → zona sísmica CHOC-08 (nombre normalizado sin tildes/espacios)
_MUNICIPIOS_ZONA = {
    # Zona 1
    "puerto cortes": "1", "cortes": "1", "omoa": "1", "choloma": "1",
    "la ceiba": "1", "ceiba": "1", "tela": "1", "trujillo": "1",
    "tocoa": "1", "sonaguera": "1", "olanchito": "1",
    # Zona 2
    "san pedro sula": "2", "villanueva": "2", "la lima": "2",
    "el progreso": "2", "yoro": "2", "juticalpa": "2", "catacamas": "2",
    # Zona 3a
    "tegucigalpa": "3a", "distrito central": "3a", "talanga": "3a",
    "danli": "3a", "choluteca": "3a", "nacaome": "3a", "langue": "3a",
    "santa rosa de copan": "3a", "copan": "3a",
    # Zona 3b
    "comayagua": "3b", "siguatepeque": "3b", "la paz": "3b",
    "marcala": "3b", "intibuca": "3b", "la esperanza": "3b",
    "gracias": "3b", "nueva ocotepeque": "3b", "ocotepeque": "3b",
    # Zona 4a
    "san marcos de colon": "4a", "langue": "4a", "nacaome": "4a",
    # Zona 4b
    "amatillo": "4b",
}

router = APIRouter(prefix="/diseno", tags=["diseno-sismo"])

class SismoChoc08(BaseModel):
    """Parámetros sísmicos CHOC-08. Defaults = proyecto piloto CC-135 (Comayagua)."""
    zona:  str   = "3b"      # clave de ZONAS
    suelo: str   = "S1"      # clave de SUELOS
    I:     float = 1.0       # factor de importancia
    Rw:    float = 8         # factor de reducción
    hn_m:  float = 3         # altura total del edificio (m)
    W_t:   float = 1206      # peso sísmico (kgf)

class ContextoSismicoUpsert(BaseModel):
    """Body para crear/actualizar el contexto sísmico del presupuesto.
    deriva_limite y espectro se recalculan en el servidor (no se confían del cliente)."""
    municipio:   Optional[str]   = None
    zona:        str             = "3b"
    suelo:       str             = "S1"
    importancia_i: float         = 1.0
    rw:          float           = 8
    hn_m:        float           = 3
    w_t:         float           = 1206
    v_din_t:     Optional[float] = None
    deriva_real: Optional[float] = None
    notas:       Optional[str]   = None

def _ctx_to_dict(ctx: ContextoSismico, existe: bool = True) -> dict:
    """Serializa el contexto sísmico (o defaults CC-135 si ctx es None)."""
    if ctx is None:
        d = dict(_SISMO_DEFAULTS)
        # Completar Z/S/Ta/Tb/c/deriva desde el motor para los defaults
        mem = memoria_sismica({
            "zona": d["zona"], "suelo": d["suelo"], "I": d["importancia_i"],
            "Rw": d["rw"], "hn_m": d["hn_m"], "W_t": d["w_t"],
        })
        meta = mem["meta"]
        d.update({
            "norma": "CHOC-08", "z_factor": meta["Z"], "s_coef": meta["S"],
            "ta_s": meta["Ta"], "tb_s": meta["Tb"], "c_exp": meta["c"],
            "deriva_limite": meta["deriva_limite"], "espectro": mem["espectro"],
            "existe": False, "updated_at": None,
        })
        return d
    espectro = []
    if ctx.espectro_json:
        try:
            espectro = json.loads(ctx.espectro_json)
        except (ValueError, TypeError):
            espectro = []
    return {
        "existe":        existe,
        "id":            ctx.id,
        "presupuesto_id": ctx.presupuesto_id,
        "norma":         ctx.norma or "CHOC-08",
        "municipio":     ctx.municipio or "",
        "zona":          ctx.zona or "3b",
        "z_factor":      float(ctx.z_factor) if ctx.z_factor is not None else None,
        "suelo":         ctx.suelo or "S1",
        "s_coef":        float(ctx.s_coef) if ctx.s_coef is not None else None,
        "ta_s":          float(ctx.ta_s) if ctx.ta_s is not None else None,
        "tb_s":          float(ctx.tb_s) if ctx.tb_s is not None else None,
        "c_exp":         float(ctx.c_exp) if ctx.c_exp is not None else None,
        "importancia_i": float(ctx.importancia_i) if ctx.importancia_i is not None else None,
        "rw":            float(ctx.rw) if ctx.rw is not None else None,
        "deriva_limite": float(ctx.deriva_limite) if ctx.deriva_limite is not None else None,
        "hn_m":          float(ctx.hn_m) if ctx.hn_m is not None else None,
        "w_t":           float(ctx.w_t) if ctx.w_t is not None else None,
        "v_din_t":       float(ctx.v_din_t) if ctx.v_din_t is not None else None,
        "deriva_real":   float(ctx.deriva_real) if ctx.deriva_real is not None else None,
        "espectro":      espectro,
        "notas":         ctx.notas or "",
        "updated_at":    ctx.updated_at.isoformat() if ctx.updated_at else None,
    }

@router.get("/{pid}/sismo")
def get_contexto_sismico(pid: str, db: Session = Depends(get_db)):
    """Devuelve el contexto sísmico del presupuesto. Si no existe, devuelve
    los defaults CC-135 con flag existe=false (sin persistir)."""
    pres = db.query(Presupuesto).filter(Presupuesto.id == pid).first()
    if not pres:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")
    ctx = db.query(ContextoSismico).filter(
        ContextoSismico.presupuesto_id == pid).first()
    return _ctx_to_dict(ctx, existe=ctx is not None)

@router.put("/{pid}/sismo")
def upsert_contexto_sismico(pid: str, body: ContextoSismicoUpsert,
                            db: Session = Depends(get_db)):
    """Crea o actualiza (upsert 1:1) el contexto sísmico del presupuesto.
    Recalcula deriva_limite y espectro con CHOC-08 y guarda espectro_json."""
    pres = db.query(Presupuesto).filter(Presupuesto.id == pid).first()
    if not pres:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")

    # Recalcular parámetros derivados con el motor (fuente de verdad)
    mem = memoria_sismica({
        "zona": body.zona, "suelo": body.suelo, "I": body.importancia_i,
        "Rw": body.rw, "hn_m": body.hn_m, "W_t": body.w_t,
    })
    meta = mem["meta"]

    ctx = db.query(ContextoSismico).filter(
        ContextoSismico.presupuesto_id == pid).first()
    if not ctx:
        ctx = ContextoSismico(id=str(uuid.uuid4()), presupuesto_id=pid)
        db.add(ctx)

    ctx.norma          = "CHOC-08"
    if body.municipio is not None:
        ctx.municipio  = body.municipio
    ctx.zona           = meta["zona"]
    ctx.z_factor       = meta["Z"]
    ctx.suelo          = meta["suelo"]
    ctx.s_coef         = meta["S"]
    ctx.ta_s           = meta["Ta"]
    ctx.tb_s           = meta["Tb"]
    ctx.c_exp          = meta["c"]
    ctx.importancia_i  = body.importancia_i
    ctx.rw             = body.rw
    ctx.deriva_limite  = meta["deriva_limite"]
    ctx.hn_m           = body.hn_m
    ctx.w_t            = body.w_t
    ctx.v_din_t        = body.v_din_t
    ctx.deriva_real    = body.deriva_real
    ctx.espectro_json  = json.dumps(mem["espectro"])
    if body.notas is not None:
        ctx.notas      = body.notas
    ctx.updated_at     = datetime.utcnow()

    db.commit()
    db.refresh(ctx)
    return _ctx_to_dict(ctx, existe=True)

@router.get("/sismo/tablas")
def sismo_tablas():
    """Catálogos para los dropdowns del frontend: zonas (Z) y suelos (S/Ta/Tb/c)."""
    return {
        "zonas":  [{"zona": k, "Z": v} for k, v in ZONAS.items()],
        "suelos": [{"suelo": k, **v} for k, v in SUELOS.items()],
    }

@router.post("/sismo/memoria")
def sismo_memoria(body: SismoChoc08):
    """Memoria sísmica CHOC-08 (estilo Mathcad): parámetros, periodo, coeficiente,
    cortante basal, espectro y deriva límite. NO toca la base de datos.
    Devuelve {meta, pasos[], espectro[[T,a_g]], constantes[]}."""
    return memoria_sismica(body.dict())

@router.post("/sismo/espectro-csv")
def sismo_espectro_csv(body: SismoChoc08):
    """Espectro CHOC-08 en CSV (pares T,a/g) listo para pegar en ETABS."""
    from fastapi.responses import PlainTextResponse
    mem = memoria_sismica(body.dict())
    return PlainTextResponse(espectro_csv(mem["espectro"]),
                             media_type="text/csv")

@router.get("/sismo/procedimiento")
def sismo_procedimiento():
    """Material explicativo del modulo ETABS (no toca BD):
      - origen_inputs : de donde viene cada dato de entrada (norma/tabla/documento)
      - procedimiento : pasos reproducidos de los MD fuente (navegacion ETABS,
                        datos+origen, verificacion, errores comunes)
      - export_doc    : que es el archivo de export de ETABS y como producirlo/cargarlo
    """
    return {
        "origen_inputs": ORIGEN_INPUTS,
        "procedimiento": PROCEDIMIENTO,
        "export_doc":    EXPORT_ETABS_DOC,
    }

def _norm_mun(m: str) -> str:
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", m.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))

def _clasificar_suelo_choc08(capas: list) -> str:
    """S1-S4 CHOC-08 Tabla 1.3.4-1 desde capas SPT. Conservador."""
    if not capas:
        return "S3"
    total_esp = 0.0
    sum_n_esp = 0.0
    soft_coh = False
    n_values = []
    for c in capas:
        esp = float(c.get("prof_m_fin", 0)) - float(c.get("prof_m_inicio", 0))
        n60 = float(c.get("n60") or 0)
        sucs = str(c.get("sucs") or "").upper().strip()
        if esp <= 0 or n60 <= 0:
            continue
        total_esp += esp
        sum_n_esp += n60 * esp
        n_values.append(n60)
        if sucs in ("CH", "MH", "OH", "OL") and n60 < 8:
            soft_coh = True
    if not n_values:
        return "S3"
    n_avg = sum_n_esp / total_esp if total_esp > 0 else sum(n_values) / len(n_values)
    n_min = min(n_values)
    if soft_coh or n_min < 5:
        return "S4"
    if n_min < 15 or n_avg < 15:
        return "S3"
    if n_avg <= 50:
        return "S2"
    return "S1"

def _qadm_en_desplante(capas: list, prof_desplante_m: float) -> dict:
    """qadm (kg/cm²) a la profundidad de desplante dada."""
    if not capas:
        return {"qadm_kg_cm2": None, "prof_m": None, "nota": "Sin datos"}
    sorted_c = sorted(capas, key=lambda c: float(c.get("prof_m_inicio", 0)))
    for c in sorted_c:
        p0 = float(c.get("prof_m_inicio", 0))
        p1 = float(c.get("prof_m_fin", 0))
        qb = c.get("qb_kg_cm2")
        if qb and p0 <= prof_desplante_m < p1:
            return {"qadm_kg_cm2": float(qb), "prof_m": round((p0 + p1) / 2, 3),
                    "nota": f"Capa {p0:.2f}-{p1:.2f}m SUCS={c.get('sucs','')}"}
    last = sorted_c[-1]
    qb = last.get("qb_kg_cm2")
    p0 = float(last.get("prof_m_inicio", 0))
    p1 = float(last.get("prof_m_fin", 0))
    return {"qadm_kg_cm2": float(qb) if qb else None, "prof_m": round((p0 + p1) / 2, 3),
            "nota": f"Última capa {p0:.2f}-{p1:.2f}m (desplante más profundo)"}

def _advertencias_suelo(capas, suelo, nf):
    warns = []
    n_values = [float(c.get("n60") or 0) for c in capas if c.get("n60")]
    if n_values and min(n_values) < 10:
        warns.append(f"Capas con N60 < 10 (mín={min(n_values):.0f}) — verificar profundidad de desplante")
    if suelo in ("S3", "S4") and nf is None:
        warns.append("NF no determinado — riesgo de licuefacción no evaluado")
    if nf is not None and nf < 2.0:
        warns.append(f"NF superficial a {nf:.2f}m — evaluar presión de poros")
    if suelo == "S4":
        warns.append("S4: S=2.0 — espectro amplificado, revisar período largo")
    return warns

class EstudioCapaIn(BaseModel):
    prof_m_inicio:  float
    prof_m_fin:     float
    sucs:           str              = ""
    n60:            Optional[float]  = None
    qb_kg_cm2:      Optional[float]  = None
    descripcion:    str              = ""

class EstudioSueloIn(BaseModel):
    municipio:          str              = ""
    departamento:       str              = ""
    descripcion_sitio:  str              = ""
    capas:              list             = []
    prof_desplante_m:   float            = 1.5
    nivel_freatico_m:   Optional[float]  = None
    zona_override:      Optional[str]    = None
    suelo_override:     Optional[str]    = None
    municipio_completo: str              = ""
    notas_adicionales:  str              = ""

@router.post("/sismo/inferir-suelo")
def inferir_suelo_choc08(body: EstudioSueloIn):
    """Deriva S1-S4 CHOC-08 y zona sísmica desde datos SPT. No persiste."""
    mun_key = _norm_mun(body.municipio)
    zona = body.zona_override or _MUNICIPIOS_ZONA.get(mun_key)
    if zona is None:
        for k, z in _MUNICIPIOS_ZONA.items():
            if k in mun_key or mun_key in k:
                zona = z
                break
    zona = zona or "3a"

    suelo = body.suelo_override or _clasificar_suelo_choc08(body.capas)
    qadm_info = _qadm_en_desplante(body.capas, body.prof_desplante_m)
    suelo_params = SUELOS.get(suelo, SUELOS["S3"])
    nf_nota = ("NF no detectado" if body.nivel_freatico_m is None
               else f"NF a {body.nivel_freatico_m:.2f}m")

    spt_tabla = [
        {"prof": f"{c.get('prof_m_inicio',0):.2f}-{c.get('prof_m_fin',0):.2f}m",
         "sucs": c.get("sucs", ""), "n60": c.get("n60"),
         "qb_kg_cm2": c.get("qb_kg_cm2"), "desc": c.get("descripcion", "")}
        for c in body.capas
    ]
    return {
        "zona_derivada": zona,
        "z_factor": ZONAS.get(zona, 0.20),
        "suelo_derivado": suelo,
        "suelo_params": suelo_params,
        "qadm": qadm_info,
        "nivel_freatico": nf_nota,
        "spt_tabla": spt_tabla,
        "contexto_sismico_sugerido": {"zona": zona, "suelo": suelo,
                                      "importancia_i": 1.0, "rw": 8},
        "advertencias": _advertencias_suelo(body.capas, suelo, body.nivel_freatico_m),
    }

@router.post("/{pid}/sismo/from-estudio-suelo")
def sismo_from_estudio_suelo(pid: str, body: EstudioSueloIn,
                              db: Session = Depends(get_db)):
    """Deriva y persiste ContextoSismico desde estudio geotécnico.
    Guarda tabla SPT en notas del contexto sísmico como referencia."""
    pres = db.query(Presupuesto).filter(Presupuesto.id == pid).first()
    if not pres:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")

    derived = inferir_suelo_choc08(body)
    zona  = derived["zona_derivada"]
    suelo = derived["suelo_derivado"]

    spt_lines = [f"  {r['prof']} | {r['sucs']} | N60={r['n60']} | qb={r['qb_kg_cm2']} kg/cm²"
                 for r in derived["spt_tabla"]]
    nota_geo = (
        f"[Estudio Geotécnico]\n"
        f"Ubicación: {body.municipio_completo or body.municipio}"
        + (f", {body.departamento}" if body.departamento else "") + "\n"
        + (f"Sitio: {body.descripcion_sitio}\n" if body.descripcion_sitio else "")
        + f"SPT Sondeo:\n" + "\n".join(spt_lines) + "\n"
        + f"Nivel freático: {derived['nivel_freatico']}\n"
        + f"qadm ({body.prof_desplante_m}m desplante): "
        + f"{derived['qadm'].get('qadm_kg_cm2')} kg/cm²\n"
        + f"Clasificación CHOC-08: {suelo} (zona {zona}, Z={derived['z_factor']}g)\n"
        + (f"Notas: {body.notas_adicionales}\n" if body.notas_adicionales else "")
    )

    mem = memoria_sismica({"zona": zona, "suelo": suelo, "I": 1.0,
                           "Rw": 8, "hn_m": 3.0, "W_t": 1206})
    meta = mem["meta"]
    ctx = db.query(ContextoSismico).filter(
        ContextoSismico.presupuesto_id == pid).first()
    if not ctx:
        ctx = ContextoSismico(id=str(uuid.uuid4()), presupuesto_id=pid)
        db.add(ctx)
    ctx.norma         = "CHOC-08"
    ctx.municipio     = body.municipio_completo or body.municipio
    ctx.zona          = meta["zona"]
    ctx.z_factor      = meta["Z"]
    ctx.suelo         = meta["suelo"]
    ctx.s_coef        = meta["S"]
    ctx.ta_s          = meta["Ta"]
    ctx.tb_s          = meta["Tb"]
    ctx.c_exp         = meta["c"]
    ctx.importancia_i = 1.0
    ctx.rw            = 8
    ctx.deriva_limite = meta["deriva_limite"]
    ctx.hn_m          = 3.0
    ctx.w_t           = 1206
    ctx.espectro_json = json.dumps(mem["espectro"])
    ctx.notas         = nota_geo
    ctx.updated_at    = datetime.utcnow()
    db.commit()
    db.refresh(ctx)
    return {
        "contexto_sismico": _ctx_to_dict(ctx, existe=True),
        "derivacion": derived,
    }

def _ctx_sismo_params(pid, db, overrides):
    """Resuelve los parámetros sísmicos (Z,I,Rw,W,S,T,deriva_limite) para el
    escalado/verificación. Prioridad: overrides del request > ContextoSismico
    persistido (si hay pid) > defaults CC-135. Devuelve dict o None si no hay base."""
    base = None
    if pid:
        ctx = db.query(ContextoSismico).filter(
            ContextoSismico.presupuesto_id == pid).first()
        if ctx is not None:
            base = _ctx_to_dict(ctx, existe=True)
    if base is None:
        # Sin contexto persistido: usar defaults + lo que venga en overrides
        base = _ctx_to_dict(None)

    def pick(*keys, default=None):
        for k in keys:
            v = overrides.get(k)
            if v is not None:
                return v
        for k in keys:
            v = base.get(k)
            if v is not None:
                return v
        return default

    zona = str(pick("zona", default="3b"))
    suelo = str(pick("suelo", default="S1")).upper()
    I = float(pick("I", "importancia_i", default=1.0))
    Rw = float(pick("Rw", "rw", default=8))
    hn = float(pick("hn_m", default=3))
    W = float(pick("W", "W_t", "w_t", default=1206))

    Z = base.get("z_factor")
    S = base.get("s_coef")
    if Z is None and zona in ZONAS:
        Z = ZONAS[zona]
    if S is None and suelo in SUELOS:
        S = SUELOS[suelo]["S"]
    d_lim = base.get("deriva_limite")
    return {
        "zona": zona, "suelo": suelo, "I": I, "Rw": Rw, "hn_m": hn,
        "W": W, "Z": Z, "S": S, "deriva_limite": d_lim,
    }

def _enriquecer_sismo(res, pid, db, overrides):
    """Agrega al resultado del parser (in place) los bloques 'escalado' y
    'verificacion_derivas' usando V_din + derivas_por_piso del export y el
    contexto sísmico (Z,I,Rw,W,S,T,deriva_limite). Aditivo, tolerante."""
    if not isinstance(res, dict):
        return res
    overrides = overrides or {}

    # Permitir 'regular' (estructura regular/irregular) por el request
    reg = overrides.get("regular")
    regular = True if reg is None else str(reg).lower() not in ("0", "false", "no", "irregular")

    try:
        P = _ctx_sismo_params(pid, db, overrides)
    except Exception:  # noqa: BLE001
        return res

    # ── ESCALADO DEL CORTANTE (1.3.6.5.3) ────────────────────────────────────
    V_din = res.get("V_din")
    Z, S, I, Rw, W = P["Z"], P["S"], P["I"], P["Rw"], P["W"]
    # Peso: si el export trae W, úsalo (más fiel al modelo); si no, el del contexto
    W_use = res.get("W") if res.get("W") is not None else W
    # Periodo para C: modal real del export si existe, si no Método A
    T_use = res.get("T")
    metodo_T = "modal (export ETABS)"
    if T_use is None or T_use <= 0:
        T_use = periodo_metodo_a(P["hn_m"])
        metodo_T = "Método A (0.0731·hn^¾)"
    if None not in (Z, S, I, Rw, W_use) and V_din is not None:
        C = coef_sismico(S, T_use)
        c_rw = C / Rw if Rw else None
        # Respetar piso C/Rw ≥ 0.075 (CHOC 1.3.6.4)
        c_rw_aplicado = max(c_rw, C_RW_MIN) if c_rw is not None else None
        V_est = (Z * I * c_rw_aplicado) * W_use if c_rw_aplicado is not None else None
        esc = escalado_cortante(V_din, V_est, regular=regular)
        esc.update({
            "Z": Z, "I": I, "Rw": Rw, "S": S, "W": round(W_use, 1),
            "T_usado": round(T_use, 4), "metodo_T": metodo_T,
            "C": round(C, 4), "C_Rw": round(c_rw, 4) if c_rw is not None else None,
            "C_Rw_aplicado": round(c_rw_aplicado, 4) if c_rw_aplicado is not None else None,
            "regular": regular,
            "piso_c_rw": bool(c_rw is not None and c_rw < C_RW_MIN),
        })
        res["escalado"] = esc
    else:
        res["escalado"] = None

    # ── VERIFICACIÓN DE DERIVAS POR PISO (1.3.5.8.2) ─────────────────────────
    d_lim = P["deriva_limite"]
    if d_lim is None:
        try:
            d_lim = _calc_deriva_limite(T_use, Rw)
        except Exception:  # noqa: BLE001
            d_lim = None
    por_piso = res.get("derivas_por_piso") or []
    if por_piso and d_lim is not None:
        res["verificacion_derivas"] = verificar_derivas(por_piso, d_lim)
    else:
        res["verificacion_derivas"] = None
    return res

@router.post("/sismo/import-etabs")
async def sismo_import_etabs(request: Request, pid: Optional[str] = None,
                             db: Session = Depends(get_db)):
    """Parsea un export de ETABS (.xlsx multi-hoja, CSV/TSV o texto pegado) y
    devuelve {W, T, V_din, deriva, derivas_por_piso, escalado,
    verificacion_derivas, leido[], avisos[], formato}. Tolerante con nombres de
    columna/hoja. Acepta el archivo como multipart (campo 'archivo') o JSON
    {"texto": "..."}. Detecta .xlsx por extension/content-type/magic.

    Escalado (1.3.6.5.3) y verificación de derivas (1.3.5.8.2) se calculan con
    el contexto sísmico del presupuesto (?pid=...) o con los params que vengan en
    el form/JSON (zona, suelo, I, Rw, hn_m, W, regular). Aditivo: si falta el
    contexto, esos bloques salen None y el resto funciona igual."""
    ctype = (request.headers.get("content-type") or "").lower()

    if "multipart/form-data" in ctype:
        form = await request.form()
        overrides = {k: form.get(k) for k in
                     ("zona", "suelo", "I", "Rw", "hn_m", "W", "regular")}
        pid_eff = pid or form.get("pid")
        up = form.get("archivo")
        if up is not None and hasattr(up, "read"):
            raw = await up.read()
            nombre = getattr(up, "filename", "") or ""
            up_ct = getattr(up, "content_type", "") or ""
            if _es_xlsx(nombre, up_ct, raw):
                res = parse_export_etabs_bytes(raw)
            else:
                res = parse_export_etabs(_decode_bytes(raw))
                res.setdefault("formato", "csv")
            return _enriquecer_sismo(res, pid_eff, db, overrides)
        if form.get("texto"):
            res = parse_export_etabs(str(form.get("texto")))
            res.setdefault("formato", "texto")
            return _enriquecer_sismo(res, pid_eff, db, overrides)
        return parse_export_etabs("")

    if "application/json" in ctype:
        try:
            data = await request.json()
            contenido = str((data or {}).get("texto", "") or "")
        except Exception:
            data, contenido = {}, ""
        res = parse_export_etabs(contenido)
        res.setdefault("formato", "texto")
        pid_eff = pid or (data or {}).get("pid")
        overrides = {k: (data or {}).get(k) for k in
                     ("zona", "suelo", "I", "Rw", "hn_m", "W", "regular")}
        return _enriquecer_sismo(res, pid_eff, db, overrides)

    # cuerpo crudo (puede ser xlsx binario o texto)
    raw = await request.body()
    if _es_xlsx("", ctype, raw):
        res = parse_export_etabs_bytes(raw)
    else:
        res = parse_export_etabs(_decode_bytes(raw))
        res.setdefault("formato", "csv")
    return _enriquecer_sismo(res, pid, db, {})

