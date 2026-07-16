"""
Router: Diseño Estructural — EstimaStruct
==========================================
CSI Div 03 (Concreto) + Div 04 (Mampostería)

Endpoints:
  GET/POST  /diseno/{pid}/elementos
  GET/PUT/DELETE /diseno/elementos/{eid}
  POST      /diseno/elementos/{eid}/casos
  PUT/DELETE /diseno/casos/{cid}
  POST      /diseno/casos/{cid}/calcular
  GET       /diseno/casos/{cid}/resultado
  POST      /diseno/casos/{cid}/generar-partidas
  GET       /diseno/{pid}/resumen
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from backend.db import get_db
from backend.models import (
    Presupuesto, Capitulo, Partida, InsumoPartida,
    DisenoElemento, CasoDiseno, ResultadoDiseno, ContextoSismico
)
from backend.calculo_estructural import calcular_caso, memoria_calculo, predimensionar
from backend.calculo_miembro_acero import memoria_miembro
from backend.perfiles_acero import TABLA_W, PERFILES_ACERO, _norm_w
from backend.acero_ficha import (
    mapear_perfil_a_ficha, agregar_por_ficha,
    parse_acero_texto, parse_acero_bytes, conexion_ficha,
)
from backend.calculo_sismico_choc08 import (
    memoria_sismica, espectro_csv, ZONAS, SUELOS,
    coef_sismico, periodo_metodo_a, cortante_estatico,
    escalado_cortante, verificar_derivas, deriva_limite as _calc_deriva_limite,
    C_RW_MIN,
)
from backend.etabs_procedimiento import (
    ORIGEN_INPUTS, PROCEDIMIENTO, EXPORT_ETABS_DOC,
    parse_export_etabs, parse_export_etabs_bytes,
)
from backend.seccion_ficha import (
    mapear_seccion_a_ficha, factores_unidad,
    parse_concreto_texto, parse_concreto_bytes,
)
from backend.calculo_estructural import RECUB_DEFAULT
import uuid, os, re, json

router = APIRouter(prefix="/diseno", tags=["diseno-estructural"])


# ─────────────────────────────────────────────────────────────────────────────
# SCHEMAS
# ─────────────────────────────────────────────────────────────────────────────

class ElementoCreate(BaseModel):
    csi:         str        = ""               # llave maestra; si vacío, se auto-asigna
    type_mark:   str        = ""               # etiqueta secundaria opcional
    tipo:        str        = "VIGA_SIMPLE"   # VIGA_SIMPLE|VIGA_DOBLE|VIGA_T|COLUMNA
    b_cm:        float      = 30.0
    d_cm:        float      = 50.0
    d_prima_cm:  float      = 5.0
    bp_cm:       float      = 0.0
    t_cm:        float      = 0.0
    lx_cm:       float      = 0.0
    ly_cm:       float      = 0.0
    fc_kg_cm2:   float      = 210.0
    fy_kg_cm2:   float      = 4200.0
    longitud_m:  float      = 0.0
    notas:       str        = ""


class ElementoUpdate(BaseModel):
    csi:         Optional[str]   = None
    type_mark:   Optional[str]   = None
    tipo:        Optional[str]   = None
    b_cm:        Optional[float] = None
    d_cm:        Optional[float] = None
    d_prima_cm:  Optional[float] = None
    bp_cm:       Optional[float] = None
    t_cm:        Optional[float] = None
    lx_cm:       Optional[float] = None
    ly_cm:       Optional[float] = None
    fc_kg_cm2:   Optional[float] = None
    fy_kg_cm2:   Optional[float] = None
    longitud_m:  Optional[float] = None
    notas:       Optional[str]   = None


class CasoCreate(BaseModel):
    nombre:    str   = "D+L"
    mu_tm:     float = 0.0
    vu_t:      float = 0.0
    tu_tm:     float = 0.0
    nu_t:      float = 0.0
    pu_t:      float = 0.0
    mu_xx_tm:  float = 0.0
    mu_yy_tm:  float = 0.0
    lu_cm:     float = 0.0
    k_x:       float = 1.0
    k_y:       float = 1.0
    bd_x:      float = 0.15
    bd_y:      float = 0.15
    cm_x:      float = 1.0
    cm_y:      float = 1.0


class CasoUpdate(BaseModel):
    nombre:    Optional[str]   = None
    mu_tm:     Optional[float] = None
    vu_t:      Optional[float] = None
    tu_tm:     Optional[float] = None
    nu_t:      Optional[float] = None
    pu_t:      Optional[float] = None
    mu_xx_tm:  Optional[float] = None
    mu_yy_tm:  Optional[float] = None
    lu_cm:     Optional[float] = None
    k_x:       Optional[float] = None
    k_y:       Optional[float] = None
    bd_x:      Optional[float] = None
    bd_y:      Optional[float] = None
    cm_x:      Optional[float] = None
    cm_y:      Optional[float] = None


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────


from backend.services.etabs_parse import _decode_bytes, _es_xlsx
from backend.services.partidas_bridge import _get_o_crear_capitulo, _crear_o_actualizar_partida, _perfil_acero_valido, _correr_caso_acero, _marcar_gobierna_acero
def _elem_to_dict(e: DisenoElemento) -> dict:
    return {
        "id":          e.id,
        "presupuesto_id": e.presupuesto_id,
        "csi":         e.csi or "",
        "type_mark":   e.type_mark or "",
        "tipo":        e.tipo,
        "b_cm":        float(e.b_cm or 0),
        "d_cm":        float(e.d_cm or 0),
        "d_prima_cm":  float(e.d_prima_cm or 0),
        "bp_cm":       float(e.bp_cm or 0),
        "t_cm":        float(e.t_cm or 0),
        "lx_cm":       float(e.lx_cm or 0),
        "ly_cm":       float(e.ly_cm or 0),
        "fc_kg_cm2":   float(e.fc_kg_cm2 or 210),
        "fy_kg_cm2":   float(e.fy_kg_cm2 or 4200),
        "longitud_m":  float(e.longitud_m or 0),
        "material_tipo": getattr(e, "material_tipo", None) or "CONCRETO",
        "perfil_acero":  getattr(e, "perfil_acero", None) or "",
        "acero_grado":   getattr(e, "acero_grado", None) or "A992",
        "notas":       e.notas or "",
        "created_at":  e.created_at.isoformat() if e.created_at else None,
        "num_casos":   len(e.casos),
    }

def _caso_to_dict(c: CasoDiseno) -> dict:
    return {
        "id":                  c.id,
        "diseno_elemento_id":  c.diseno_elemento_id,
        "nombre":              c.nombre,
        "gobierna":            c.gobierna,
        "origen":              getattr(c, "origen", None) or "MANUAL",
        "combo_etabs":         getattr(c, "combo_etabs", None) or "",
        "mu_tm":               float(c.mu_tm or 0),
        "vu_t":                float(c.vu_t or 0),
        "tu_tm":               float(c.tu_tm or 0),
        "nu_t":                float(c.nu_t or 0),
        "pu_t":                float(c.pu_t or 0),
        "mu_xx_tm":            float(c.mu_xx_tm or 0),
        "mu_yy_tm":            float(c.mu_yy_tm or 0),
        "lu_cm":               float(c.lu_cm or 0),
        "k_x":                 float(c.k_x or 1),
        "k_y":                 float(c.k_y or 1),
        "bd_x":                float(c.bd_x or 0.15),
        "bd_y":                float(c.bd_y or 0.15),
        "cm_x":                float(c.cm_x or 1),
        "cm_y":                float(c.cm_y or 1),
        "tiene_resultado":     c.resultado is not None,
        "resultado":           _resultado_to_dict(c.resultado) if c.resultado else None,
        "created_at":          c.created_at.isoformat() if c.created_at else None,
    }

def _resultado_to_dict(r: ResultadoDiseno) -> dict:
    return {
        "id":                  r.id,
        "caso_id":             r.caso_id,
        "pb":                  float(r.pb or 0),
        "pmax":                float(r.pmax or 0),
        "as_cm2":              float(r.as_cm2 or 0),
        "a_prima_cm2":         float(r.a_prima_cm2 or 0),
        "as_min_cm2":          float(r.as_min_cm2 or 0),
        "as_max_cm2":          float(r.as_max_cm2 or 0),
        "vc_kg_cm2":           float(r.vc_kg_cm2 or 0),
        "vtu_kg_cm2":          float(r.vtu_kg_cm2 or 0),
        "av_cm2":              float(r.av_cm2 or 0),
        "at_cm2":              float(r.at_cm2 or 0),
        "al_cm2":              float(r.al_cm2 or 0),
        "s_max_cm":            float(r.s_max_cm or 20),
        "delta_x":             float(r.delta_x or 1),
        "delta_y":             float(r.delta_y or 1),
        "as_col_cm2":          float(r.as_col_cm2 or 0),
        "pg_pct":              float(r.pg_pct or 0),
        "concreto_m3":         float(r.concreto_m3 or 0),
        "encofrado_m2":        float(r.encofrado_m2 or 0),
        "acero_kg":            float(r.acero_kg or 0),
        "estribos_kg":         float(r.estribos_kg or 0),
        "ok_sismico":          r.ok_sismico,
        "ok_pg":               r.ok_pg,
        "advertencias":        r.advertencias or "",
        "acero_estado_gob":    getattr(r, "acero_estado_gob", None) or "",
        "acero_phi_rn_gob":    float(getattr(r, "acero_phi_rn_gob", 0) or 0),
        "acero_dc":            float(getattr(r, "acero_dc", 0) or 0),
        "acero_cumple":        bool(getattr(r, "acero_cumple", True)),
        "acero_estados":       json.loads(getattr(r, "acero_estados_json", None) or "{}"),
        "partida_concreto_id": r.partida_concreto_id,
        "partida_acero_id":    r.partida_acero_id,
        "partida_encofrado_id": r.partida_encofrado_id,
        "calculado_at":        r.calculado_at.isoformat() if r.calculado_at else None,
    }

def _marcar_gobierna(elemento: DisenoElemento):
    """Marca el caso con mayor As como gobierna."""
    mejor_as = -1
    mejor_id = None
    for caso in elemento.casos:
        if caso.resultado:
            as_v = float(caso.resultado.as_cm2 or 0)
            if as_v > mejor_as:
                mejor_as = as_v
                mejor_id = caso.id
    for caso in elemento.casos:
        caso.gobierna = (caso.id == mejor_id)

@router.get("/{pid}/elementos")
def listar_elementos(pid: str, db: Session = Depends(get_db)):
    """Lista todos los elementos de diseño de un presupuesto."""
    elementos = db.query(DisenoElemento).filter(
        DisenoElemento.presupuesto_id == pid
    ).order_by(DisenoElemento.created_at).all()

    out = []
    for e in elementos:
        d = _elem_to_dict(e)
        d["casos"] = [_caso_to_dict(c) for c in e.casos]
        out.append(d)

    return {
        "presupuesto_id": pid,
        "total": len(elementos),
        "elementos": out,
    }

def _next_csi_diseno(pid: str, db: Session) -> str:
    """Siguiente CSI libre en serie 03 31 00.NN para los elementos de diseño del presupuesto."""
    existentes = db.query(DisenoElemento.csi).filter(
        DisenoElemento.presupuesto_id == pid).all()
    maxn = 0
    for (c,) in existentes:
        m = re.match(r'03 31 00\.(\d+)', c or '')
        if m:
            maxn = max(maxn, int(m.group(1)))
    return f"03 31 00.{maxn + 1:02d}"

@router.post("/{pid}/elementos")
def crear_elemento(pid: str, data: ElementoCreate = ElementoCreate(),
                   db: Session = Depends(get_db)):
    """Crea nuevo elemento de diseño. CSI es la llave: si no se envía, se auto-asigna."""
    pres = db.query(Presupuesto).filter(Presupuesto.id == pid).first()
    if not pres:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")

    payload = data.dict()
    if not (payload.get("csi") or "").strip():
        payload["csi"] = _next_csi_diseno(pid, db)

    elem = DisenoElemento(
        id=str(uuid.uuid4()),
        presupuesto_id=pid,
        **payload,
    )
    db.add(elem)
    db.commit()
    db.refresh(elem)

    return _elem_to_dict(elem)

def _fichas_path(version: str) -> str:
    base = os.path.join(_FICHAS_BASE, version, "fichas")
    live = os.path.join(base, f"fichas_{version}.live.json")
    return live if os.path.exists(live) else os.path.join(base, f"fichas_{version}.json")

def _to_cm(v) -> float:
    v = float(v)
    return v * 100 if v < 5 else v   # valores < 5 se asumen en metros

def _clasificar_ficha(desc: str, mark: str):
    """VIGA_SIMPLE | COLUMNA | None según descripción/mark de la ficha Div 03."""
    d = desc.lower()
    if any(w in d for w in ('columna', 'pedestal', 'castillo')):
        return 'COLUMNA'
    if any(w in d for w in ('viga', 'solera', 'dintel', 'nervio')):
        return 'VIGA_SIMPLE'
    if any(w in d for w in _EXCLUDE):
        return None
    p = (mark or '').lstrip('-')[:1].upper()
    if p == 'V':
        return 'VIGA_SIMPLE'
    if p in ('C', 'R', 'P'):
        return 'COLUMNA'
    return None

def _parse_fichas_div03(version: str) -> list:
    """Extrae candidatos estructurales (vigas/columnas con sección rectangular) de Div 03."""
    path = _fichas_path(version)
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as f:
        fichas = json.load(f)

    out = []
    for x in fichas:
        csi = x.get('csi', '')
        if not csi.startswith('03'):
            continue
        if (x.get('unidad', '') or '').lower() not in ('ml', 'm'):
            continue
        desc = x.get('descripcion', '')
        mk = _MARK_RE.search(desc)
        mark = mk.group(1) if mk else (x.get('codigo', '') or csi)
        tipo = _clasificar_ficha(desc, mark)
        if not tipo:
            continue
        m = _DIM_RE.search(desc)
        if not m:
            continue
        a, b = _to_cm(m.group(1)), _to_cm(m.group(2))
        if a < 10 or b < 10 or a > 200 or b > 200:
            continue
        out.append({"csi": csi, "mark": mark, "tipo": tipo,
                    "a": round(a, 1), "b": round(b, 1), "desc": desc})
    return out

class ImportarBasesBody(BaseModel):
    version: str = "v1.2"

@router.post("/{pid}/importar-bases")
def importar_bases(pid: str, body: ImportarBasesBody = ImportarBasesBody(),
                   db: Session = Depends(get_db)):
    """Auto-crea elementos de diseño desde fichas Div 03 de la base de datos.
    Detecta vigas/columnas con sección rectangular parseable y los lista en el panel."""
    pres = db.query(Presupuesto).filter(Presupuesto.id == pid).first()
    if not pres:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")

    cands = _parse_fichas_div03(body.version)
    if not cands:
        return {"status": "sin_candidatos", "version": body.version,
                "creados": 0, "actualizados": 0, "total": 0}

    # Dedupe por CSI (llave maestra), no por type_mark
    existentes = {e.csi: e for e in db.query(DisenoElemento).filter(
        DisenoElemento.presupuesto_id == pid).all() if e.csi}

    creados = actualizados = 0
    for c in cands:
        csi, mark, a, b = c["csi"], c["mark"], c["a"], c["b"]
        notas = f"Auto {body.version} · {csi} · {c['desc'][:70]}"
        elem = existentes.get(csi)

        if elem is None:
            if c["tipo"] == "COLUMNA":
                elem = DisenoElemento(
                    id=str(uuid.uuid4()), presupuesto_id=pid, csi=csi, type_mark=mark,
                    tipo="COLUMNA", lx_cm=a, ly_cm=b, b_cm=0, d_cm=0,
                    fc_kg_cm2=210, fy_kg_cm2=4200, longitud_m=0, notas=notas)
            else:
                elem = DisenoElemento(
                    id=str(uuid.uuid4()), presupuesto_id=pid, csi=csi, type_mark=mark,
                    tipo="VIGA_SIMPLE", b_cm=a, d_cm=round(b - 6, 1),
                    fc_kg_cm2=210, fy_kg_cm2=4200, longitud_m=0,
                    notas=f"{notas} · h={b:.0f}cm (d=h-6)")
            db.add(elem)
            creados += 1
        else:
            elem.type_mark = mark
            if c["tipo"] == "COLUMNA":
                elem.tipo, elem.lx_cm, elem.ly_cm = "COLUMNA", a, b
            else:
                elem.tipo, elem.b_cm, elem.d_cm = "VIGA_SIMPLE", a, round(b - 6, 1)
            elem.notas = notas
            actualizados += 1

    db.commit()

    elementos = db.query(DisenoElemento).filter(
        DisenoElemento.presupuesto_id == pid).order_by(DisenoElemento.created_at).all()
    out = []
    for e in elementos:
        d = _elem_to_dict(e)
        d["casos"] = [_caso_to_dict(c) for c in e.casos]
        out.append(d)

    return {
        "status": "ok", "version": body.version,
        "creados": creados, "actualizados": actualizados, "total": len(cands),
        "elementos": out,
    }

@router.get("/elementos/{eid}")
def get_elemento(eid: str, db: Session = Depends(get_db)):
    """Obtiene elemento con sus casos."""
    elem = db.query(DisenoElemento).filter(DisenoElemento.id == eid).first()
    if not elem:
        raise HTTPException(status_code=404, detail="Elemento no encontrado")

    d = _elem_to_dict(elem)
    d["casos"] = [_caso_to_dict(c) for c in elem.casos]
    return d

@router.patch("/elementos/{eid}")
def actualizar_elemento(eid: str, data: ElementoUpdate, db: Session = Depends(get_db)):
    """Actualiza geometría/material del elemento."""
    elem = db.query(DisenoElemento).filter(DisenoElemento.id == eid).first()
    if not elem:
        raise HTTPException(status_code=404, detail="Elemento no encontrado")

    for field, value in data.dict(exclude_none=True).items():
        setattr(elem, field, value)

    db.commit()
    db.refresh(elem)
    return _elem_to_dict(elem)

@router.delete("/elementos/{eid}")
def eliminar_elemento(eid: str, db: Session = Depends(get_db)):
    """Elimina elemento y todos sus casos + resultados en cascada."""
    elem = db.query(DisenoElemento).filter(DisenoElemento.id == eid).first()
    if not elem:
        raise HTTPException(status_code=404, detail="Elemento no encontrado")

    db.delete(elem)
    db.commit()
    return {"status": "deleted", "id": eid}

@router.post("/elementos/{eid}/casos")
def crear_caso(eid: str, data: CasoCreate, db: Session = Depends(get_db)):
    """Agrega caso de carga al elemento."""
    elem = db.query(DisenoElemento).filter(DisenoElemento.id == eid).first()
    if not elem:
        raise HTTPException(status_code=404, detail="Elemento no encontrado")

    caso = CasoDiseno(
        id=str(uuid.uuid4()),
        diseno_elemento_id=eid,
        **data.dict(),
    )
    db.add(caso)
    db.commit()
    db.refresh(caso)

    return _caso_to_dict(caso)

@router.patch("/casos/{cid}")
def actualizar_caso(cid: str, data: CasoUpdate, db: Session = Depends(get_db)):
    """Actualiza cargas de un caso."""
    caso = db.query(CasoDiseno).filter(CasoDiseno.id == cid).first()
    if not caso:
        raise HTTPException(status_code=404, detail="Caso no encontrado")

    for field, value in data.dict(exclude_none=True).items():
        setattr(caso, field, value)

    db.commit()
    db.refresh(caso)
    return _caso_to_dict(caso)

@router.delete("/casos/{cid}")
def eliminar_caso(cid: str, db: Session = Depends(get_db)):
    """Elimina caso y su resultado."""
    caso = db.query(CasoDiseno).filter(CasoDiseno.id == cid).first()
    if not caso:
        raise HTTPException(status_code=404, detail="Caso no encontrado")

    db.delete(caso)
    db.commit()
    return {"status": "deleted", "id": cid}

@router.post("/casos/{cid}/calcular")
def calcular_caso_endpoint(cid: str, db: Session = Depends(get_db)):
    """Ejecuta motor de cálculo ACI 318-19 y guarda ResultadoDiseno."""
    caso = db.query(CasoDiseno).filter(CasoDiseno.id == cid).first()
    if not caso:
        raise HTTPException(status_code=404, detail="Caso no encontrado")

    elem = caso.elemento

    # ACERO: motor LRFD §D-H (no ACI). Persiste acero_* y devuelve resumen.
    if (elem.material_tipo or "CONCRETO") == "ACERO":
        _correr_caso_acero(caso, db)
        db.flush()
        _marcar_gobierna_acero(elem)
        db.commit()
        r = caso.resultado
        return {
            "material": "ACERO", "perfil": elem.perfil_acero, "tipo": elem.tipo,
            "estado_gobernante": r.acero_estado_gob,
            "phi_rn_gob": float(r.acero_phi_rn_gob or 0),
            "dc": float(r.acero_dc or 0),
            "cumple": bool(r.acero_cumple),
            "estados": json.loads(r.acero_estados_json or "{}"),
        }

    # Preparar dicts
    elem_d = {
        "tipo":        elem.tipo,
        "b_cm":        float(elem.b_cm or 30),
        "d_cm":        float(elem.d_cm or 50),
        "d_prima_cm":  float(elem.d_prima_cm or 5),
        "bp_cm":       float(elem.bp_cm or 0),
        "t_cm":        float(elem.t_cm or 0),
        "lx_cm":       float(elem.lx_cm or 0),
        "ly_cm":       float(elem.ly_cm or 0),
        "fc_kg_cm2":   float(elem.fc_kg_cm2 or 210),
        "fy_kg_cm2":   float(elem.fy_kg_cm2 or 4200),
        "longitud_m":  float(elem.longitud_m or 0),
    }
    caso_d = {
        "mu_tm":    float(caso.mu_tm or 0),
        "vu_t":     float(caso.vu_t or 0),
        "tu_tm":    float(caso.tu_tm or 0),
        "nu_t":     float(caso.nu_t or 0),
        "pu_t":     float(caso.pu_t or 0),
        "mu_xx_tm": float(caso.mu_xx_tm or 0),
        "mu_yy_tm": float(caso.mu_yy_tm or 0),
        "lu_cm":    float(caso.lu_cm or 0),
        "k_x":      float(caso.k_x or 1),
        "k_y":      float(caso.k_y or 1),
        "bd_x":     float(caso.bd_x or 0.15),
        "bd_y":     float(caso.bd_y or 0.15),
        "cm_x":     float(caso.cm_x or 1),
        "cm_y":     float(caso.cm_y or 1),
    }

    # Calcular
    res_d = calcular_caso(elem_d, caso_d)

    # Guardar o actualizar resultado
    resultado = caso.resultado
    if not resultado:
        resultado = ResultadoDiseno(
            id=str(uuid.uuid4()),
            caso_id=cid,
        )
        db.add(resultado)

    for field, value in res_d.items():
        if hasattr(resultado, field):
            setattr(resultado, field, value)

    resultado.calculado_at = datetime.utcnow()

    # Marcar cuál caso gobierna en el elemento
    db.flush()
    _marcar_gobierna(elem)

    db.commit()
    db.refresh(resultado)

    return _resultado_to_dict(resultado)

@router.get("/casos/{cid}/resultado")
def get_resultado(cid: str, db: Session = Depends(get_db)):
    """Obtiene el resultado calculado de un caso."""
    caso = db.query(CasoDiseno).filter(CasoDiseno.id == cid).first()
    if not caso:
        raise HTTPException(status_code=404, detail="Caso no encontrado")

    if not caso.resultado:
        raise HTTPException(status_code=404, detail="Aún no calculado. POST /calcular primero.")

    return _resultado_to_dict(caso.resultado)

@router.get("/casos/{cid}/memoria")
def get_memoria_calculo(cid: str, db: Session = Depends(get_db)):
    """
    Memoria de cálculo narrada (estilo Excel/Mathcad): cada valor con su
    símbolo, fórmula, sustitución numérica, referencia ACI/CHOC y descripción.
    No persiste nada — recalcula on-the-fly desde geometría + cargas actuales.
    """
    caso = db.query(CasoDiseno).filter(CasoDiseno.id == cid).first()
    if not caso:
        raise HTTPException(status_code=404, detail="Caso no encontrado")

    elem = caso.elemento

    # ACERO: hoja LRFD §D-H (estilo Mathcad) en vez de la memoria ACI.
    if (elem.material_tipo or "CONCRETO") == "ACERO":
        elem_m, caso_m = _acero_caso_dicts(caso)
        memoria = memoria_miembro(elem_m, caso_m)
        memoria["meta"]["caso_id"] = cid
        memoria["meta"]["caso_nombre"] = caso.nombre or ""
        memoria["meta"]["csi"] = elem.csi or ""
        return memoria

    elem_d = {
        "tipo":        elem.tipo,
        "b_cm":        float(elem.b_cm or 30),
        "d_cm":        float(elem.d_cm or 50),
        "d_prima_cm":  float(elem.d_prima_cm or 5),
        "bp_cm":       float(elem.bp_cm or 0),
        "t_cm":        float(elem.t_cm or 0),
        "lx_cm":       float(elem.lx_cm or 0),
        "ly_cm":       float(elem.ly_cm or 0),
        "fc_kg_cm2":   float(elem.fc_kg_cm2 or 210),
        "fy_kg_cm2":   float(elem.fy_kg_cm2 or 4200),
        "longitud_m":  float(elem.longitud_m or 0),
    }
    caso_d = {
        "mu_tm":    float(caso.mu_tm or 0),
        "vu_t":     float(caso.vu_t or 0),
        "tu_tm":    float(caso.tu_tm or 0),
        "nu_t":     float(caso.nu_t or 0),
        "pu_t":     float(caso.pu_t or 0),
        "mu_xx_tm": float(caso.mu_xx_tm or 0),
        "mu_yy_tm": float(caso.mu_yy_tm or 0),
        "lu_cm":    float(caso.lu_cm or 0),
        "k_x":      float(caso.k_x or 1),
        "k_y":      float(caso.k_y or 1),
        "bd_x":     float(caso.bd_x or 0.15),
        "bd_y":     float(caso.bd_y or 0.15),
        "cm_x":     float(caso.cm_x or 1),
        "cm_y":     float(caso.cm_y or 1),
    }

    memoria = memoria_calculo(elem_d, caso_d)
    memoria["meta"]["caso_id"]   = cid
    memoria["meta"]["caso_nombre"] = caso.nombre or ""
    memoria["meta"]["type_mark"] = elem.type_mark or ""
    memoria["meta"]["csi"]       = elem.csi or ""
    return memoria

class CalcRapida(BaseModel):
    """Geometría + cargas en un solo cuerpo. Calculadora en vivo, sin persistir."""
    tipo:       str = "VIGA_SIMPLE"
    b_cm:       float = 30
    d_cm:       float = 50
    d_prima_cm: float = 5
    bp_cm:      float = 0
    t_cm:       float = 0
    lx_cm:      float = 0
    ly_cm:      float = 0
    fc_kg_cm2:  float = 210
    fy_kg_cm2:  float = 4200
    longitud_m: float = 0
    mu_tm:      float = 0
    vu_t:       float = 0
    tu_tm:      float = 0
    nu_t:       float = 0
    pu_t:       float = 0
    mu_xx_tm:   float = 0
    mu_yy_tm:   float = 0
    lu_cm:      float = 0
    k_x:        float = 1
    k_y:        float = 1
    bd_x:       float = 0.15
    bd_y:       float = 0.15
    cm_x:       float = 1
    cm_y:       float = 1

@router.post("/memoria-rapida")
def memoria_rapida(body: CalcRapida):
    """Calculadora en vivo: recibe geometría + cargas y devuelve la memoria
    de cálculo (fórmulas, sustituciones, resultado). NO toca la base de datos."""
    elem_d = {
        "tipo": body.tipo,
        "b_cm": body.b_cm, "d_cm": body.d_cm, "d_prima_cm": body.d_prima_cm,
        "bp_cm": body.bp_cm, "t_cm": body.t_cm, "lx_cm": body.lx_cm, "ly_cm": body.ly_cm,
        "fc_kg_cm2": body.fc_kg_cm2, "fy_kg_cm2": body.fy_kg_cm2, "longitud_m": body.longitud_m,
    }
    caso_d = {
        "mu_tm": body.mu_tm, "vu_t": body.vu_t, "tu_tm": body.tu_tm, "nu_t": body.nu_t,
        "pu_t": body.pu_t, "mu_xx_tm": body.mu_xx_tm, "mu_yy_tm": body.mu_yy_tm,
        "lu_cm": body.lu_cm, "k_x": body.k_x, "k_y": body.k_y,
        "bd_x": body.bd_x, "bd_y": body.bd_y, "cm_x": body.cm_x, "cm_y": body.cm_y,
    }
    memoria = memoria_calculo(elem_d, caso_d)
    memoria["meta"]["caso_nombre"] = "Calculadora en vivo"
    return memoria

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

def _elem_d_from_orm(elem: DisenoElemento) -> dict:
    return {
        "tipo": elem.tipo,
        "b_cm": float(elem.b_cm or 30), "d_cm": float(elem.d_cm or 50),
        "d_prima_cm": float(elem.d_prima_cm or 5),
        "bp_cm": float(elem.bp_cm or 0), "t_cm": float(elem.t_cm or 0),
        "lx_cm": float(elem.lx_cm or 0), "ly_cm": float(elem.ly_cm or 0),
        "fc_kg_cm2": float(elem.fc_kg_cm2 or 210), "fy_kg_cm2": float(elem.fy_kg_cm2 or 4200),
        "longitud_m": float(elem.longitud_m or 0),
    }

def _caso_d_from_orm(caso: CasoDiseno) -> dict:
    return {
        "mu_tm": float(caso.mu_tm or 0), "vu_t": float(caso.vu_t or 0),
        "tu_tm": float(caso.tu_tm or 0), "nu_t": float(caso.nu_t or 0),
        "pu_t": float(caso.pu_t or 0), "mu_xx_tm": float(caso.mu_xx_tm or 0),
        "mu_yy_tm": float(caso.mu_yy_tm or 0), "lu_cm": float(caso.lu_cm or 0),
        "k_x": float(caso.k_x or 1), "k_y": float(caso.k_y or 1),
        "bd_x": float(caso.bd_x or 0.15), "bd_y": float(caso.bd_y or 0.15),
        "cm_x": float(caso.cm_x or 1), "cm_y": float(caso.cm_y or 1),
    }

def _correr_caso(caso: CasoDiseno, db: Session):
    """Ejecuta el motor ACI y persiste/actualiza ResultadoDiseno. Sin commit."""
    res_d = calcular_caso(_elem_d_from_orm(caso.elemento), _caso_d_from_orm(caso))
    resultado = caso.resultado
    if not resultado:
        resultado = ResultadoDiseno(id=str(uuid.uuid4()), caso_id=caso.id)
        caso.resultado = resultado   # poblar la relacion inversa en memoria
        db.add(resultado)
    for field, value in res_d.items():
        if hasattr(resultado, field):
            setattr(resultado, field, value)
    resultado.calculado_at = datetime.utcnow()
    return resultado

@router.post("/{pid}/import-etabs-concreto")
async def import_etabs_concreto(pid: str, request: Request,
                                db: Session = Depends(get_db)):
    """
    Puente ETABS -> presupuesto de CONCRETO (Div 03).

    Acepta:
      - multipart/form-data: campo 'archivo' (.csv/.xlsx) + opcionales
        'unidad' (kgf|kn|t, default kgf), 'recubrimiento_cm' (default 4).
      - application/json: {"texto": "<csv pegado>"} o
        {"secciones": [{member,section,b,h,fc}], "fuerzas": [{member,combo,P,V2,V3,T,M2,M3}]}
        + opcionales "unidad", "recubrimiento_cm".

    Proceso:
      1. Por miembro unico -> mapear seccion->ficha -> crear/actualizar DisenoElemento.
         tipo VIGA_SIMPLE o COLUMNA segun la seccion. d_cm = h - recubrimiento.
      2. Por (miembro, combo) -> CasoDiseno (origen=ETABS, combo_etabs=combo).
         Conversion de unidades ETABS -> motor (t / t-m).
      3. Correr motor ACI por caso. Marcar gobierna por elemento.
      4. NO genera partidas (usar luego POST /diseno/casos/{cid}/generar-partidas).

    Mapeo fuerzas ETABS -> CasoDiseno:
      VIGA   : M3 -> mu_tm ; V2 -> vu_t ; T -> tu_tm ; P -> nu_t
      COLUMNA: P -> pu_t  ; M3 -> mu_xx_tm ; M2 -> mu_yy_tm ; V2 -> vu_t
    """
    pres = db.query(Presupuesto).filter(Presupuesto.id == pid).first()
    if not pres:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")

    ctype = (request.headers.get("content-type") or "").lower()
    unidad = "kgf"
    recub = RECUB_DEFAULT
    parsed = {"secciones": {}, "fuerzas": [], "avisos": []}

    # ── Ingesta ──────────────────────────────────────────────────────────────
    if "multipart/form-data" in ctype:
        form = await request.form()
        unidad = (form.get("unidad") or "kgf")
        try:
            recub = float(form.get("recubrimiento_cm") or RECUB_DEFAULT)
        except (TypeError, ValueError):
            recub = RECUB_DEFAULT
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
        unidad = data.get("unidad") or "kgf"
        try:
            recub = float(data.get("recubrimiento_cm") or RECUB_DEFAULT)
        except (TypeError, ValueError):
            recub = RECUB_DEFAULT
        if data.get("secciones") is not None or data.get("fuerzas") is not None:
            # Secciones explicitas: normalizar a {member:{section,b,h,fc}}
            secs = {}
            for s in (data.get("secciones") or []):
                m = str(s.get("member") or s.get("frame") or "").strip()
                if not m:
                    continue
                secs[m] = {
                    "section": s.get("section") or s.get("seccion") or "",
                    "b": s.get("b"), "h": s.get("h"), "fc": s.get("fc"),
                    "L_m": s.get("L_m") or s.get("longitud") or s.get("length"),
                }
            parsed = {"secciones": secs, "fuerzas": list(data.get("fuerzas") or []),
                      "avisos": []}
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

    if not secciones and not fuerzas:
        return {"status": "sin_datos", "avisos": avisos or
                ["No se reconocieron tablas de secciones ni fuerzas."],
                "elementos_creados": 0, "casos_creados": 0,
                "gobernantes": [], "mapeos_aproximados": []}

    f_fuerza, f_mom = factores_unidad(unidad)

    # Miembros: union de los que tienen seccion y/o fuerzas
    miembros = set(secciones.keys()) | {f.get("member") for f in fuerzas if f.get("member")}
    miembros.discard("")
    miembros.discard(None)

    # ── 1) Crear/actualizar elementos ────────────────────────────────────────
    existentes = {e.csi: e for e in db.query(DisenoElemento).filter(
        DisenoElemento.presupuesto_id == pid).all() if e.csi}
    elem_por_miembro = {}      # member -> DisenoElemento
    elementos_creados = 0
    mapeos_aproximados = []

    for member in sorted(miembros):
        sec = secciones.get(member)
        if not sec or (sec.get("b") is None and sec.get("h") is None):
            avisos.append(f"Miembro '{member}': sin seccion legible; se omite.")
            continue
        b_cm = sec.get("b") or sec.get("h")
        h_cm = sec.get("h") or sec.get("b")
        # Inferir tipo: el nombre de seccion suele traer R-/V-/S-; si no, cuadrada=>columna
        sname = (sec.get("section") or "").upper()
        if "S-" in sname or "SOLERA" in sname:
            tipo_hint = "SOLERA"
        elif "V-" in sname or "VIGA" in sname:
            tipo_hint = "VIGA"
        elif "R-" in sname or "C-" in sname or "P-" in sname or "COLUM" in sname:
            tipo_hint = "COLUMNA"
        else:
            tipo_hint = "COLUMNA" if abs(b_cm - h_cm) <= 1 else "VIGA"

        mapa = mapear_seccion_a_ficha(b_cm, h_cm, tipo_hint)
        type_mark = mapa["type_mark"] or member
        es_columna = (mapa["tipo_estructura"] == "COLUMNA")
        tipo_elem = "COLUMNA" if es_columna else "VIGA_SIMPLE"
        fc = float(sec.get("fc") or 210)
        if fc < 50:   # fc venia en MPa o mal escalado -> default
            fc = 210.0

        csi = f"ETABS:{member}"
        elem = existentes.get(csi)
        d_eff = round(max(h_cm - recub, 1), 1)
        # Longitud del frame (Frame length de ETABS) -> takeoff de concreto/encofrado.
        # Sin esto el motor ACI devuelve volumen 0. None si el export no la trae.
        L_m = sec.get("L_m")
        try:
            L_m = float(L_m) if L_m is not None else None
        except (TypeError, ValueError):
            L_m = None
        notas = (f"ETABS member={member} · seccion={sec.get('section') or '-'} · "
                 f"{b_cm:.0f}x{h_cm:.0f}cm -> {type_mark}"
                 + (f" · L={L_m:.2f}m" if L_m else "")
                 + (" (APROX)" if mapa["aproximado"] else ""))

        if elem is None:
            if es_columna:
                elem = DisenoElemento(
                    id=str(uuid.uuid4()), presupuesto_id=pid, csi=csi,
                    type_mark=type_mark, tipo="COLUMNA",
                    lx_cm=b_cm, ly_cm=h_cm, b_cm=b_cm, d_cm=d_eff,
                    fc_kg_cm2=fc, fy_kg_cm2=4200, longitud_m=(L_m or 0), notas=notas)
            else:
                elem = DisenoElemento(
                    id=str(uuid.uuid4()), presupuesto_id=pid, csi=csi,
                    type_mark=type_mark, tipo="VIGA_SIMPLE",
                    b_cm=b_cm, d_cm=d_eff, fc_kg_cm2=fc, fy_kg_cm2=4200,
                    longitud_m=(L_m or 0), notas=notas)
            db.add(elem)
            existentes[csi] = elem
            elementos_creados += 1
        else:
            elem.type_mark = type_mark
            elem.tipo = "COLUMNA" if es_columna else "VIGA_SIMPLE"
            if es_columna:
                elem.lx_cm, elem.ly_cm = b_cm, h_cm
            elem.b_cm, elem.d_cm, elem.fc_kg_cm2, elem.notas = b_cm, d_eff, fc, notas
            if L_m:                       # solo sobrescribe si el export trae longitud
                elem.longitud_m = L_m

        elem_por_miembro[member] = elem
        if mapa["aproximado"]:
            mapeos_aproximados.append({
                "member": member, "dim": {"b": b_cm, "h": h_cm},
                "type_mark": type_mark, "dim_ficha": mapa.get("dim_ficha"),
                "tipo": mapa["tipo_estructura"], "dist_cm": mapa.get("dist"),
            })

    if elem_por_miembro and not any((e.longitud_m or 0) > 0
                                    for e in elem_por_miembro.values()):
        avisos.append("Ningun miembro trae 'Length' (Frame length): el takeoff de "
                      "concreto/encofrado saldra 0. Exporta tambien la columna "
                      "Length (Frame Assignments - Summary) o edita la longitud por "
                      "elemento.")

    db.flush()

    # ── 2) Crear casos por combinacion ───────────────────────────────────────
    casos_creados = 0
    nuevos_casos = []
    for fz in fuerzas:
        member = (fz.get("member") or "").strip()
        elem = elem_por_miembro.get(member)
        if elem is None:
            # Fuerza sin seccion correspondiente: crear elemento minimo si hay otro
            if not member:
                continue
            avisos.append(f"Fuerza combo '{fz.get('combo')}' del miembro '{member}': "
                          "sin seccion; caso omitido.")
            continue
        combo = (fz.get("combo") or "ETABS").strip()
        P  = (fz.get("P")  or 0) * f_fuerza
        V2 = (fz.get("V2") or 0) * f_fuerza
        T  = (fz.get("T")  or 0) * f_mom
        M2 = (fz.get("M2") or 0) * f_mom
        M3 = (fz.get("M3") or 0) * f_mom

        caso = CasoDiseno(
            id=str(uuid.uuid4()), diseno_elemento_id=elem.id,
            nombre=combo, origen="ETABS", combo_etabs=combo)
        if elem.tipo == "COLUMNA":
            caso.pu_t = abs(P)
            caso.mu_xx_tm = abs(M3)
            caso.mu_yy_tm = abs(M2)
            caso.vu_t = abs(V2)
        else:
            caso.mu_tm = abs(M3)
            caso.vu_t = abs(V2)
            caso.tu_tm = abs(T)
            caso.nu_t = P   # +comp/-tension
        db.add(caso)
        nuevos_casos.append(caso)
        casos_creados += 1

    db.flush()

    # ── 3) Correr motor por caso ─────────────────────────────────────────────
    for caso in nuevos_casos:
        _correr_caso(caso, db)
    db.flush()

    # ── 4) Marcar gobierna por elemento ──────────────────────────────────────
    gobernantes = []
    for elem in {c.diseno_elemento_id: c.elemento for c in nuevos_casos}.values():
        _marcar_gobierna(elem)
        for caso in elem.casos:
            if caso.gobierna:
                r = caso.resultado
                gobernantes.append({
                    "elemento_id": elem.id, "csi": elem.csi,
                    "type_mark": elem.type_mark, "tipo": elem.tipo,
                    "caso_id": caso.id, "combo": caso.combo_etabs or caso.nombre,
                    "as_cm2": float(r.as_cm2 or 0) if r else None,
                    "as_col_cm2": float(r.as_col_cm2 or 0) if r else None,
                    "ok_sismico": (r.ok_sismico if r else None),
                })

    db.commit()

    return {
        "status": "ok",
        "unidad_entrada": unidad,
        "factor_fuerza_a_t": round(f_fuerza, 8),
        "factor_momento_a_tm": round(f_mom, 8),
        "recubrimiento_cm": recub,
        "elementos_creados": elementos_creados,
        "casos_creados": casos_creados,
        "gobernantes": gobernantes,
        "mapeos_aproximados": mapeos_aproximados,
        "avisos": avisos,
    }

class PredimBody(BaseModel):
    """Body de /diseno/predimensionar (no toca BD)."""
    tipo:            str   = "VIGA"      # COLUMNA | VIGA
    niveles:         int   = 1
    luz_libre_cm:    float = 0.0
    b_apoyo_cm:      float = 0.0
    recubrimiento_cm: Optional[float] = None

@router.post("/predimensionar")
def predimensionar_endpoint(body: PredimBody):
    """Predimensionamiento estructural (G2). Funcion PURA — NO toca la BD.

    COLUMNA: lado_min = niveles · 10 · 0.8 ; b=h = ↑múltiplo de 5 ≥ lado_min.
    VIGA   : h = (luz_libre − 2·b_apoyo)/10 ; ↑múltiplo de 5 ; b ≈ h/2 (mín 20).
    d = h − recubrimiento.

    Devuelve {tipo, b_cm, h_cm, d_cm, lado_min_cm|h_prop_cm, regla_usada, notas}."""
    rec = body.recubrimiento_cm if body.recubrimiento_cm is not None else RECUB_DEFAULT
    return predimensionar(
        tipo=body.tipo, niveles=body.niveles,
        luz_libre_cm=body.luz_libre_cm, b_apoyo_cm=body.b_apoyo_cm,
        recubrimiento_cm=rec,
    )

@router.post("/casos/{cid}/generar-partidas")
def generar_partidas(cid: str, db: Session = Depends(get_db)):
    """
    Crea/actualiza las 3 partidas CSI 03 desde el resultado del caso.
    Requiere que el caso haya sido calculado primero.
    """
    caso = db.query(CasoDiseno).filter(CasoDiseno.id == cid).first()
    if not caso:
        raise HTTPException(status_code=404, detail="Caso no encontrado")

    if not caso.resultado:
        raise HTTPException(status_code=400, detail="Calcule el caso antes de generar partidas.")

    elem      = caso.elemento
    resultado = caso.resultado
    pid       = elem.presupuesto_id
    # CSI es la llave de identidad de las partidas; type_mark solo etiqueta
    ident     = elem.csi or elem.type_mark or elem.id[:8]
    lbl       = elem.type_mark or ident

    # Obtener o crear capítulo 03
    cap03 = _get_o_crear_capitulo(pid, "03", db)

    # Partida encofrado — 03 10 00
    p_enc = _crear_o_actualizar_partida(
        cap03, "03 10 00",
        f"Encofrado {elem.tipo} {lbl} [{ident}]",
        "m2",
        float(resultado.encofrado_m2 or 0),
        ident, db,
    )

    # Partida acero — 03 20 00
    acero_total = float(resultado.acero_kg or 0) + float(resultado.estribos_kg or 0)
    p_ace = _crear_o_actualizar_partida(
        cap03, "03 20 00",
        f"Acero de refuerzo {elem.tipo} {lbl} [{ident}]",
        "kg",
        acero_total,
        ident, db,
    )

    # Partida concreto — 03 30 00
    p_con = _crear_o_actualizar_partida(
        cap03, "03 30 00",
        f"Concreto colado {elem.tipo} {lbl} [{ident}] f'c={int(elem.fc_kg_cm2 or 210)} kg/cm²",
        "m3",
        float(resultado.concreto_m3 or 0),
        ident, db,
    )

    # Guardar links en resultado
    resultado.partida_encofrado_id = p_enc.id
    resultado.partida_acero_id     = p_ace.id
    resultado.partida_concreto_id  = p_con.id

    db.commit()

    return {
        "status": "ok",
        "csi":    ident,
        "mark":   lbl,
        "partidas": {
            "encofrado": {"id": p_enc.id, "clave": "03 10 00", "cantidad": float(p_enc.cantidad), "unidad": "m2"},
            "acero":     {"id": p_ace.id, "clave": "03 20 00", "cantidad": float(p_ace.cantidad), "unidad": "kg"},
            "concreto":  {"id": p_con.id, "clave": "03 30 00", "cantidad": float(p_con.cantidad), "unidad": "m3"},
        }
    }

@router.get("/{pid}/resumen")
def resumen_csi(pid: str, db: Session = Depends(get_db)):
    """Resumen de cantidades totales de diseño estructural del presupuesto."""
    elementos = db.query(DisenoElemento).filter(
        DisenoElemento.presupuesto_id == pid
    ).all()

    totales = {
        "elementos": len(elementos),
        "casos_calculados": 0,
        "concreto_m3":  0.0,
        "encofrado_m2": 0.0,
        "acero_kg":     0.0,
        "estribos_kg":  0.0,
    }

    por_tipo = {}

    for elem in elementos:
        tipo = elem.tipo
        if tipo not in por_tipo:
            por_tipo[tipo] = {"cantidad": 0, "concreto_m3": 0, "acero_kg": 0}
        por_tipo[tipo]["cantidad"] += 1

        for caso in elem.casos:
            if caso.resultado and caso.gobierna:
                r = caso.resultado
                totales["casos_calculados"] += 1
                totales["concreto_m3"]  += float(r.concreto_m3 or 0)
                totales["encofrado_m2"] += float(r.encofrado_m2 or 0)
                totales["acero_kg"]     += float(r.acero_kg or 0)
                totales["estribos_kg"]  += float(r.estribos_kg or 0)
                por_tipo[tipo]["concreto_m3"] += float(r.concreto_m3 or 0)
                por_tipo[tipo]["acero_kg"]    += float(r.acero_kg or 0)

    return {
        "presupuesto_id": pid,
        "totales": totales,
        "por_tipo": por_tipo,
    }

class MampoCreate(BaseModel):
    type_mark:     str   = "MR-01"
    longitud_m:    float = 0.0
    altura_m:      float = 0.0
    espesor_cm:    float = 20.0    # espesor del bloque (15, 20, 25 cm)
    con_refuerzo:  bool  = False
    con_relleno:   bool  = False
    notas:         str   = ""

@router.post("/{pid}/mamposteria")
def crear_mamposteria(pid: str, data: MampoCreate, db: Session = Depends(get_db)):
    """
    Takeoff simple de muro de mampostería. Genera partidas CSI 04 y 03.
    Sin diseño estructural complejo.
    """
    pres = db.query(Presupuesto).filter(Presupuesto.id == pid).first()
    if not pres:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")

    mark   = data.type_mark
    area_m2 = round(data.longitud_m * data.altura_m, 4)

    # Acero vertical (si con_refuerzo): 1 varilla Ø1/2" c/0.60m
    ACERO_KG_M2 = 3.5 if data.con_refuerzo else 0.0   # kg/m² approx
    acero_kg = round(area_m2 * ACERO_KG_M2, 2)

    # Concreto de relleno (si con_relleno): celdas cada 0.20m, secc ≈ 15×15cm
    CONCRETO_M3_M2 = 0.023 if data.con_relleno else 0.0  # m³/m² approx
    concreto_m3 = round(area_m2 * CONCRETO_M3_M2, 4)

    partidas_gen = []

    # CSI 04 — Mampostería
    cap04 = _get_o_crear_capitulo(pid, "04", db)
    p_mamp = _crear_o_actualizar_partida(
        cap04, "04 20 00",
        f"Mampostería bloque {int(data.espesor_cm)}cm {mark}",
        "m2", area_m2, mark, db,
    )
    partidas_gen.append({"clave": "04 20 00", "cantidad": area_m2, "unidad": "m2"})

    cap03 = None
    if data.con_refuerzo or data.con_relleno:
        cap03 = _get_o_crear_capitulo(pid, "03", db)

    if data.con_refuerzo and acero_kg > 0:
        p_ace = _crear_o_actualizar_partida(
            cap03, "03 20 00",
            f"Acero vertical mampostería {mark}",
            "kg", acero_kg, mark, db,
        )
        partidas_gen.append({"clave": "03 20 00", "cantidad": acero_kg, "unidad": "kg"})

    if data.con_relleno and concreto_m3 > 0:
        p_con = _crear_o_actualizar_partida(
            cap03, "03 30 00",
            f"Concreto de relleno mampostería {mark}",
            "m3", concreto_m3, mark, db,
        )
        partidas_gen.append({"clave": "03 30 00", "cantidad": concreto_m3, "unidad": "m3"})

    db.commit()

    return {
        "status":    "ok",
        "mark":      mark,
        "area_m2":   area_m2,
        "acero_kg":  acero_kg,
        "concreto_m3": concreto_m3,
        "partidas":  partidas_gen,
    }

