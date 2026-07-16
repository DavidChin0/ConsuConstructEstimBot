from backend.db import get_db
from backend.models import Presupuesto, Capitulo, Partida, InsumoPartida, DisenoElemento, CasoDiseno, ResultadoDiseno
from backend.calculo_miembro_acero import memoria_miembro
from backend.perfiles_acero import TABLA_W, PERFILES_ACERO, _norm_w
from sqlalchemy.orm import Session
from typing import Optional
import uuid, json, datetime

def _get_o_crear_capitulo(presupuesto_id: str, clave: str, db: Session) -> Capitulo:
    """Obtiene o crea capítulo CSI."""
    from backend.models import DIVISIONES_CSI
    cap = db.query(Capitulo).filter(
        Capitulo.presupuesto_id == presupuesto_id,
        Capitulo.clave == clave
    ).first()
    if not cap:
        nombre = DIVISIONES_CSI.get(clave, f"División {clave}")
        max_orden = db.query(Capitulo).filter(
            Capitulo.presupuesto_id == presupuesto_id
        ).count()
        cap = Capitulo(
            id=str(uuid.uuid4()),
            presupuesto_id=presupuesto_id,
            clave=clave,
            nombre=nombre,
            orden=max_orden + 1,
        )
        db.add(cap)
        db.flush()
    return cap

def _crear_o_actualizar_partida(cap: Capitulo, clave_csi: str, descripcion: str,
                                 unidad: str, cantidad: float, type_mark: str,
                                 db: Session) -> Partida:
    """Crea o actualiza partida en el capítulo dado."""
    partida = db.query(Partida).filter(
        Partida.capitulo_id == cap.id,
        Partida.clave_csi == clave_csi,
        Partida.type_mark == type_mark,
    ).first()

    if not partida:
        max_orden = max((p.orden for p in cap.partidas), default=0)
        partida = Partida(
            id=str(uuid.uuid4()),
            capitulo_id=cap.id,
            clave_csi=clave_csi,
            descripcion=descripcion,
            unidad=unidad,
            cantidad=round(cantidad, 4),
            type_mark=type_mark,
            orden=max_orden + 1,
        )
        db.add(partida)
    else:
        partida.cantidad = round(cantidad, 4)
        partida.descripcion = descripcion

    db.flush()
    return partida

def _acero_caso_dicts(caso: CasoDiseno):
    """Mapea (DisenoElemento ACERO + CasoDiseno) -> dicts del motor de miembros.
    UNICA fuente del mapeo (la usan _correr_caso_acero y la memoria):
      COLUMNA: pu_t -> compresion (-|P|) · mu_xx_tm -> Mux · mu_yy_tm -> Muy · vu_t -> Vu
      VIGA   : nu_t -> Pu axial (+tracc/-compr) · mu_tm -> Mux · vu_t -> Vu
    """
    elem = caso.elemento
    elem_m = {
        "perfil": elem.perfil_acero or "",
        "acero":  elem.acero_grado or "A992",
        "L_cm":   float(elem.longitud_m or 0) * 100.0,
        "K":      float(caso.k_x or 1.0),
        "Lb_cm":  float(caso.lu_cm or 0),
        "Cb":     1.0,
    }
    if elem.tipo == "COLUMNA":
        caso_m = {"pu_t": -abs(float(caso.pu_t or 0)),   # columna: compresion
                  "mux_tm": float(caso.mu_xx_tm or 0),
                  "muy_tm": float(caso.mu_yy_tm or 0),
                  "vu_t":   float(caso.vu_t or 0)}
    else:
        caso_m = {"pu_t": float(caso.nu_t or 0),          # viga: +tracc / -compr
                  "mux_tm": float(caso.mu_tm or 0),
                  "muy_tm": 0.0,
                  "vu_t":   float(caso.vu_t or 0)}
    return elem_m, caso_m

def _correr_caso_acero(caso: CasoDiseno, db: Session):
    """Ejecuta el motor LRFD AISC §D-H para un elemento de ACERO y persiste
    φRn/DC en ResultadoDiseno (campos acero_*). Sin commit."""
    elem_m, caso_m = _acero_caso_dicts(caso)
    res = memoria_miembro(elem_m, caso_m)["resultado"]
    gob = res.get("estado_gobernante")
    estados = res.get("estados", {})
    phi_gob = (estados.get(gob, {}).get("phi_rn") if gob else 0.0) or 0.0

    resultado = caso.resultado
    if not resultado:
        resultado = ResultadoDiseno(id=str(uuid.uuid4()), caso_id=caso.id)
        caso.resultado = resultado
        db.add(resultado)
    resultado.acero_estado_gob   = gob or ""
    resultado.acero_phi_rn_gob   = round(float(phi_gob), 4)
    resultado.acero_dc           = round(float(res.get("dc_gobernante") or 0.0), 4)
    resultado.acero_cumple       = bool(res.get("cumple"))
    resultado.acero_estados_json = json.dumps(estados, ensure_ascii=False)
    resultado.calculado_at = datetime.utcnow()
    return resultado

def _marcar_gobierna_acero(elemento: DisenoElemento):
    """Marca el caso de ACERO con mayor DC como gobierna."""
    mejor, mid = -1.0, None
    for c in elemento.casos:
        if c.resultado and c.resultado.acero_dc is not None:
            dc = float(c.resultado.acero_dc or 0)
            if dc > mejor:
                mejor, mid = dc, c.id
    for c in elemento.casos:
        c.gobierna = (c.id == mid)

def _perfil_acero_valido(section: str):
    """Normaliza el nombre de seccion ETABS a una clave de perfil de acero.
    Devuelve (perfil_norm, uso) o (None, None) si no esta en las tablas."""
    n = _norm_w(section or "")
    if n in TABLA_W:
        return n, TABLA_W[n].get("uso", "")
    if n in PERFILES_ACERO:
        es_col = abs(PERFILES_ACERO[n]["d"] - PERFILES_ACERO[n]["bf"]) <= 2.0
        return n, ("COLUMNA" if es_col else "VIGA")
    return None, None

