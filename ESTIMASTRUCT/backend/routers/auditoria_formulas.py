"""
Auditoría de Fórmulas — router.

Consolida el acceso a TODAS las memorias de cálculo del sistema en un solo
prefijo `/auditoria`, y agrega narración nueva para los dos módulos ciegos de
mayor riesgo financiero (`services/pricing.py` y `routers/calculos.py`), según
`docs/auditoria_formulas_mapa_estructura.md`.

Regla de diseño (ADR-003, no negociable): este router LEE y NARRA. Nunca
recalcula con aritmética propia, nunca llama `recalcular_partida` ni
`_recalcular_todo` (ambas escriben). Solo usa las funciones puras de
`services/pricing.py` y `routers/calculos.py::_factor_indirectos`.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from backend.db import get_db
from backend.models import Presupuesto, Capitulo, Partida
from backend.services.pricing_memoria import memoria_pricing
from backend.services.calculos_memoria import memoria_calculos_presupuesto
from backend.services.mamposteria_memoria import memoria_mamposteria
from backend.services.export_pdf_memoria import memoria_prorrateo_banco
from backend.services.partidas_memoria import memoria_cantidad
from backend.services.cronograma_memoria import memoria_cronograma
from backend.services.perfiles_memoria import memoria_props_seccion, catalogo_perfiles
from backend.services.unidades_memoria import memoria_factores_unidad
from backend.services.predimensionar_memoria import memoria_predimensionar
from backend.services.acero_ficha_memoria import memoria_agregacion_ficha

router = APIRouter(prefix="/auditoria", tags=["auditoria-formulas"])


# ─────────────────────────────────────────────────────────────────────────────
# Índice — qué está narrado hoy y qué sigue ciego (para la Hoja de Auditoría)
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/resumen")
def resumen():
    """Mapa estático de cobertura de narración, sincronizado a mano con
    docs/auditoria_formulas_mapa_estructura.md (generado 2026-07-27). No lee la
    BD — es metadata de arquitectura, no un cálculo."""
    return {
        "narrados": [
            {"id": "estructural", "nombre": "Concreto ACI 318-19", "archivo": "backend/calculo_estructural.py",
             "endpoint": "POST /diseno/memoria-rapida · GET /diseno/casos/{cid}/memoria", "pasos": 69,
             "modulo": "diseno"},
            {"id": "sismico", "nombre": "Sísmico CHOC-08", "archivo": "backend/calculo_sismico_choc08.py",
             "endpoint": "POST /diseno/sismo/memoria", "pasos": 22, "modulo": "etabs"},
            {"id": "acero", "nombre": "Acero LRFD §D-H", "archivo": "backend/calculo_miembro_acero.py",
             "endpoint": "POST /miembro-acero/memoria-rapida", "pasos": 31, "modulo": "acero"},
            {"id": "conexion", "nombre": "Conexiones AISC §J (incl. soldadura §J2)", "archivo": "backend/calculo_conexion_acero.py",
             "endpoint": "POST /conexion-acero/memoria-rapida", "pasos": 38, "modulo": "conexion"},
            {"id": "pricing", "nombre": "Pricing / costeo de partida", "archivo": "backend/services/pricing.py",
             "endpoint": "POST /auditoria/pricing/memoria-rapida · GET /auditoria/pricing/partida/{id}/memoria",
             "pasos": 6, "modulo": "auditoria", "nuevo_2026_07_27": True},
            {"id": "calculos", "nombre": "Indirectos de presupuesto (/calcular vs /reporte)", "archivo": "backend/routers/calculos.py",
             "endpoint": "GET /auditoria/calculos/{pid}/memoria", "pasos": 6, "modulo": "auditoria",
             "nuevo_2026_07_27": True, "flag": "⚠ doble aplicación de sobrecosto — ver pasos"},
            {"id": "mamposteria", "nombre": "Mampostería reforzada TMS 402-16",
             "archivo": "backend/services/mamposteria_memoria.py",
             "endpoint": "POST /auditoria/mamposteria/memoria-rapida", "pasos": 24, "modulo": "auditoria",
             "nuevo_2026_07_27": True,
             "flag": "✔ constantes mágicas 3.5 kg/m² (+111% vs su propio comentario) y 0.023 m³/m² (−38.7%, error dimensional) ELIMINADAS — ahora fórmula parametrizada"},

            # ── Tanda 2026-07-31 — los 7 módulos ciegos restantes ─────────────
            {"id": "banco", "nombre": "Prorrateo bancario (PDF al banco)",
             "archivo": "backend/services/export_pdf_memoria.py",
             "endpoint": "POST /auditoria/banco/memoria-rapida · GET /auditoria/banco/{pid}/memoria",
             "pasos": 13, "modulo": "auditoria", "nuevo_2026_07_31": True,
             "flag": "⚠ PENDIENTE APROBACIÓN DEL DIRECTOR — riesgo ALTO, documento formal al banco. Expone el factor de prorrateo, el residuo de redondeo de la fila TOTAL forzada y el margen implícito sobre costo directo."},
            {"id": "cantidad", "nombre": "Factores de cantidad (takeoff Revit)",
             "archivo": "backend/services/partidas_memoria.py",
             "endpoint": "POST /auditoria/cantidad/memoria-rapida · GET /auditoria/cantidad/partida/{id}/memoria",
             "pasos": 9, "modulo": "auditoria", "nuevo_2026_07_31": True,
             "flag": "✔ _safe_factor (0→1 silencioso, negativo aceptado, ceil oculto) ahora devuelve advertencias[] en PATCH /revit-q y /factores"},
            {"id": "cronograma", "nombre": "Cronograma — duración y fase",
             "archivo": "backend/services/cronograma_memoria.py",
             "endpoint": "POST /auditoria/cronograma/memoria-rapida · GET /auditoria/cronograma/partida/{id}/memoria",
             "pasos": 17, "modulo": "auditoria", "nuevo_2026_07_31": True,
             "flag": "✔ cascada de 4 fuentes (FIJO>MANUAL>V1.2>SIN_TIEMPO) y offsets mágicos de fase ahora narrados; SIN_TIEMPO ⇒ 1 día levanta advertencia"},
            {"id": "perfil", "nombre": "Propiedades de sección de acero",
             "archivo": "backend/services/perfiles_memoria.py",
             "endpoint": "POST /auditoria/perfil/memoria-rapida · GET /auditoria/perfil/catalogo",
             "pasos": 16, "modulo": "auditoria", "nuevo_2026_07_31": True,
             "flag": "✔ expone `fuente` (tabla AISC exacta · derivada ~3% conservadora · HSS) — el dato que invalidaba en silencio las memorias de acero"},
            {"id": "unidades", "nombre": "Conversión de unidades ETABS",
             "archivo": "backend/services/unidades_memoria.py",
             "endpoint": "POST /auditoria/unidades/memoria-rapida",
             "pasos": 9, "modulo": "auditoria", "nuevo_2026_07_31": True,
             "flag": "✔ fallback silencioso a kgf ahora es un CHECK visible: unidad no reconocida escala todo el diseño 101.97×"},
            {"id": "predim", "nombre": "Predimensionamiento de secciones",
             "archivo": "backend/services/predimensionar_memoria.py",
             "endpoint": "POST /auditoria/predimensionar/memoria-rapida",
             "pasos": 10, "modulo": "auditoria", "nuevo_2026_07_31": True,
             "flag": "✔ queda escrito que las reglas son heurística del despacho, NO ACI 318-19; checks de mínimos sísmicos §18.6/18.7 y L/h"},
            {"id": "aceroficha", "nombre": "Agregación de acero por ficha Div 05",
             "archivo": "backend/services/acero_ficha_memoria.py",
             "endpoint": "POST /auditoria/acero-ficha/memoria-rapida",
             "pasos": 12, "modulo": "auditoria", "nuevo_2026_07_31": True,
             "flag": "✔ la regla silenciosa 'perfil dual sin rol ⇒ COLUMNA', la envolvente D/C que descarta N−1 miembros y el acero no mapeado que no se presupuesta ahora se ven"},
        ],
        "ciegos_pendientes": [
            {"archivo": "backend/routers/acero_diseno.py", "dominio": "Placas base masivas (envolvente D/C por pedestal) — reusar memoria_conexion existente", "riesgo": "bajo"},
            {"archivo": "backend/routers/export.py:399-400", "dominio": "Split 2-vías para display Excel (contradice el modelo 3-vías real, no escribe a BD)", "riesgo": "bajo"},
            {"archivo": "backend/routers/conexion_acero.py", "dominio": "Falta GET /conexiones/{cid}/memoria — la conexión PERSISTIDA no es auditable, sólo la calculadora en vivo", "riesgo": "bajo"},
        ],
        "fuente": "docs/auditoria_formulas_mapa_estructura.md (2026-07-27) · tanda 2 cerrada 2026-07-31",
    }


# ─────────────────────────────────────────────────────────────────────────────
# PRICING — services/pricing.py
# ─────────────────────────────────────────────────────────────────────────────
class PricingRapida(BaseModel):
    """Calculadora en vivo — sin BD. Buckets ya sumados + sobrecosto + cantidad."""
    costo_mo: float = 0
    costo_ma: float = 0
    unitario_matriz: float = 0
    sobrecosto_pct: float = 20
    cantidad: float = 1


class MamposteriaRapida(BaseModel):
    """Calculadora en vivo de mampostería reforzada — sin BD.
    Defaults = TMS 402-16 §7.3.2.6 (ver services/mamposteria_memoria.py)."""
    longitud_m:  float = 5.0
    altura_m:    float = 3.0
    espesor_cm:  float = 20.0
    con_refuerzo: bool = True
    con_relleno:  bool = True
    barra_vertical:          str   = "#4"
    s_vertical_m:            float = 0.60
    barra_horizontal:        str   = "#4"
    s_horizontal_m:          float = 0.60
    con_refuerzo_horizontal: bool  = True
    celda_ancho_cm: float | None = None
    celda_largo_cm: float = 15.0
    s_celda_m:      float | None = None


@router.post("/mamposteria/memoria-rapida")
def mamposteria_memoria_rapida(body: MamposteriaRapida):
    """Narra el takeoff de mampostería paso a paso. NO toca la BD.

    Reemplaza el módulo ciego `routers/diseno_estructural.py::crear_mamposteria`,
    que hasta 2026-07-27 usaba dos constantes mágicas sin fórmula ni norma
    (3.5 kg/m² y 0.023 m³/m²). Ahora ambas se derivan de geometría real y se
    verifican contra TMS 402-16 §7.3.2.6.
    """
    try:
        return memoria_mamposteria(body.model_dump())
    except ValueError as ex:
        raise HTTPException(status_code=422, detail=str(ex))


@router.post("/pricing/memoria-rapida")
def pricing_memoria_rapida(body: PricingRapida):
    """Narra el pipeline de costeo con valores tecleados a mano. NO toca la BD."""
    memoria = memoria_pricing(body.costo_mo, body.costo_ma, body.unitario_matriz,
                               body.sobrecosto_pct, body.cantidad)
    memoria["meta"]["origen"] = "calculadora libre"
    return memoria


@router.get("/pricing/partida/{partida_id}/memoria")
def pricing_memoria_partida(partida_id: str, db: Session = Depends(get_db)):
    """Narra el pipeline de costeo de una partida REAL: bucketing desde sus
    insumos actuales, costo_base, PU, total — y lo compara contra lo persistido
    en BD (expone drift/datos stale sin corregirlos)."""
    partida = (
        db.query(Partida)
        .options(joinedload(Partida.insumos), joinedload(Partida.capitulo).joinedload(Capitulo.presupuesto).joinedload(Presupuesto.config))
        .filter(Partida.id == partida_id)
        .first()
    )
    if not partida:
        raise HTTPException(404, "Partida no encontrada")

    cap = partida.capitulo
    pres = cap.presupuesto if cap else None
    cfg = pres.config if pres else None
    sobrecosto = float(cfg.sobrecosto) if cfg and cfg.sobrecosto is not None else 20.0

    stored = {
        "costo_mo": float(partida.costo_mo or 0), "costo_ma": float(partida.costo_ma or 0),
        "unitario_matriz": float(partida.unitario_matriz or 0), "costo_base": float(partida.costo_base or 0),
        "precio_unitario": float(partida.precio_unitario or 0), "total": float(partida.total or 0),
    }
    memoria = memoria_pricing(
        partida.costo_mo, partida.costo_ma, partida.unitario_matriz, sobrecosto, partida.cantidad,
        insumos=partida.insumos, stored=stored,
        meta_extra={
            "partida_id": partida.id, "clave_csi": partida.clave_csi, "descripcion": partida.descripcion,
            "unidad": partida.unidad, "cantidad": float(partida.cantidad or 0),
            "presupuesto_id": pres.id if pres else None, "presupuesto_nombre": pres.nombre if pres else None,
            "origen": "partida real (BD)",
        },
    )
    return memoria


# ─────────────────────────────────────────────────────────────────────────────
# CALCULOS — routers/calculos.py (indirectos de presupuesto)
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/calculos/{pid}/memoria")
def calculos_memoria(pid: str, db: Session = Depends(get_db)):
    """Narra AMBOS flujos de indirectos (/calcular y /reporte) sobre un
    presupuesto real, incluyendo el hallazgo de doble aplicación de sobrecosto.
    Read-only: no llama /calcular, no persiste nada."""
    p = (
        db.query(Presupuesto)
        .options(
            joinedload(Presupuesto.config),
            joinedload(Presupuesto.capitulos).joinedload(Capitulo.partidas).joinedload(Partida.insumos),
        )
        .filter(Presupuesto.id == pid)
        .first()
    )
    if not p:
        raise HTTPException(404, "Presupuesto no encontrado")
    return memoria_calculos_presupuesto(p)


# ═════════════════════════════════════════════════════════════════════════════
# TANDA 2026-07-31 — los 7 módulos ciegos restantes.
# Todos read-only. Los que leen BD usan joinedload y NUNCA hacen commit.
# ═════════════════════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────────────────────────────────────
# 1) BANCO — routers/export_pdf.py (prorrateo bancario). RIESGO ALTO.
#    ⚠ PENDIENTE APROBACIÓN DEL DIRECTOR antes de dar por cerrado.
# ─────────────────────────────────────────────────────────────────────────────
class BancoRapida(BaseModel):
    """Calculadora en vivo del prorrateo bancario — sin BD."""
    total_real: float = 1_000_000.0
    valor_banco: float = 1_000_000.0
    costo_directo: float = 0.0
    buffer_dias: int = 0
    fin_cronograma_dias: int = 0
    moneda: str = "L"


@router.post("/banco/memoria-rapida")
def banco_memoria_rapida(body: BancoRapida):
    """Narra el prorrateo bancario con valores tecleados a mano. NO toca la BD y,
    a diferencia de GET /presupuestos/{pid}/export-pdf?report=banco, NO persiste
    `valor_banco` en el JSON de la obra."""
    try:
        return memoria_prorrateo_banco(
            body.total_real, body.valor_banco, body.costo_directo,
            totales_partida=None, buffer_dias=body.buffer_dias,
            fin_cronograma_dias=body.fin_cronograma_dias, moneda=body.moneda,
            meta_extra={"origen": "calculadora libre"})
    except ValueError as ex:
        raise HTTPException(status_code=422, detail=str(ex))


@router.get("/banco/{pid}/memoria")
def banco_memoria_presupuesto(pid: str, valor_banco: float,
                              db: Session = Depends(get_db)):
    """Narra el prorrateo bancario de un presupuesto REAL, con el residuo de
    redondeo calculado sobre sus filas reales. Read-only: reproduce la aritmética
    de `_export_pdf_banco` sin generar el PDF y sin persistir `valor_banco`."""
    from backend.routers.export_pdf import (
        _costos_obra, _sym, BUFFER_CONTRATIEMPOS_DIAS, _gantt_banco_data,
    )
    p = (
        db.query(Presupuesto)
        .options(joinedload(Presupuesto.capitulos).joinedload(Capitulo.partidas))
        .filter(Presupuesto.id == pid)
        .first()
    )
    if not p:
        raise HTTPException(404, "Presupuesto no encontrado")

    total_real, costo_directo = _costos_obra(p)
    totales = [float(pa.total or 0) for cap in p.capitulos for pa in cap.partidas
               if float(pa.total or 0) > 0]

    # Fin del cronograma en días activos — se lee del mismo motor que arma el
    # Gantt del PDF (factor 1.0: no interesa el dinero aquí, sólo el plazo).
    fin_dias = 0
    try:
        acts, _ = _gantt_banco_data(p, 1.0)
        fin_dias = max((a["dia_fin"] for a in acts if not a.get("buffer")), default=0)
    except (OSError, ValueError, KeyError):
        fin_dias = 0

    try:
        return memoria_prorrateo_banco(
            total_real, valor_banco, costo_directo, totales_partida=totales,
            buffer_dias=BUFFER_CONTRATIEMPOS_DIAS, fin_cronograma_dias=fin_dias,
            moneda=_sym(p),
            meta_extra={"presupuesto_id": p.id, "presupuesto_nombre": p.nombre,
                        "n_partidas": len(totales), "origen": "presupuesto real (BD)"})
    except ValueError as ex:
        raise HTTPException(status_code=422, detail=str(ex))


# ─────────────────────────────────────────────────────────────────────────────
# 2) CANTIDAD — routers/partidas.py (_safe_factor + ceil). RIESGO ALTO.
# ─────────────────────────────────────────────────────────────────────────────
class CantidadRapida(BaseModel):
    revit_q: float = 12.4
    factor_e: Optional[float] = 1.0
    factor_f: Optional[float] = 1.0
    precio_unitario: float = 0.0
    unidad: str = "m2"


@router.post("/cantidad/memoria-rapida")
def cantidad_memoria_rapida(body: CantidadRapida):
    """Narra `cantidad = ceil(revit_q) × fe × ff` con la semántica REAL de
    _safe_factor (0→1 silencioso, negativo aceptado). NO toca la BD."""
    return memoria_cantidad(body.revit_q, body.factor_e, body.factor_f,
                            body.precio_unitario, body.unidad,
                            meta_extra={"origen": "calculadora libre"})


@router.get("/cantidad/partida/{partida_id}/memoria")
def cantidad_memoria_partida(partida_id: str, db: Session = Depends(get_db)):
    """Narra el takeoff de cantidad de una partida REAL con sus factores actuales."""
    p = db.query(Partida).filter(Partida.id == partida_id).first()
    if not p:
        raise HTTPException(404, "Partida no encontrada")
    return memoria_cantidad(
        p.revit_q, p.factor_e, p.factor_f, p.precio_unitario, p.unidad or "",
        meta_extra={"partida_id": p.id, "clave_csi": p.clave_csi,
                    "descripcion": p.descripcion, "cantidad_persistida": float(p.cantidad or 0),
                    "origen": "partida real (BD)"})


# ─────────────────────────────────────────────────────────────────────────────
# 3) CRONOGRAMA — backend/cronograma.py. RIESGO MEDIO.
# ─────────────────────────────────────────────────────────────────────────────
class CronogramaRapida(BaseModel):
    clave_csi: str = "03 31 13.2"
    cantidad: float = 20.0
    unidad: str = "m3"
    n_esp: int = 3
    n_ay: int = 3
    capitulo_clave: str = ""
    descripcion: str = ""


@router.post("/cronograma/memoria-rapida")
def cronograma_memoria_rapida(body: CronogramaRapida):
    """Narra la duración y la fase de UNA actividad. Lee el catálogo V1.2 de
    disco (el mismo que usa el Gantt real). NO toca la BD."""
    return memoria_cronograma(body.clave_csi, body.cantidad, body.unidad,
                              body.n_esp, body.n_ay, body.capitulo_clave,
                              body.descripcion,
                              meta_extra={"origen": "calculadora libre"})


@router.get("/cronograma/partida/{partida_id}/memoria")
def cronograma_memoria_partida(partida_id: str, n_esp: int = 3, n_ay: int = 3,
                               db: Session = Depends(get_db)):
    """Narra la duración de una partida REAL con su cantidad y capítulo actuales."""
    p = (
        db.query(Partida)
        .options(joinedload(Partida.capitulo))
        .filter(Partida.id == partida_id)
        .first()
    )
    if not p:
        raise HTTPException(404, "Partida no encontrada")
    cap = p.capitulo
    return memoria_cronograma(
        p.clave_csi or "", float(p.cantidad or 0), p.unidad or "",
        n_esp, n_ay, (cap.clave if cap else ""), p.descripcion or "",
        meta_extra={"partida_id": p.id, "origen": "partida real (BD)"})


# ─────────────────────────────────────────────────────────────────────────────
# 4) PERFIL DE ACERO — backend/perfiles_acero.py. RIESGO MEDIO.
# ─────────────────────────────────────────────────────────────────────────────
class PerfilRapida(BaseModel):
    perfil: str = "W200X36"
    fy_kgcm2: float = 3515.0


@router.get("/perfil/catalogo")
def perfil_catalogo():
    """Perfiles disponibles y por qué ruta se resuelve cada uno (tabla / derivada
    / hss). Metadata pura, no lee BD."""
    return catalogo_perfiles()


@router.post("/perfil/memoria-rapida")
def perfil_memoria_rapida(body: PerfilRapida):
    """Narra de dónde salen las propiedades de sección de un perfil y qué
    confianza tiene el Zx que alimenta Mp = Fy·Zx. NO toca la BD."""
    try:
        return memoria_props_seccion(body.perfil, None, body.fy_kgcm2,
                                     meta_extra={"origen": "calculadora libre"})
    except ValueError as ex:
        raise HTTPException(status_code=422, detail=str(ex))


# ─────────────────────────────────────────────────────────────────────────────
# 5) UNIDADES ETABS — backend/seccion_ficha.py. RIESGO MEDIO.
# ─────────────────────────────────────────────────────────────────────────────
class UnidadesRapida(BaseModel):
    unidad: str = "kgf"
    p_entrada: float = 50000.0
    m_entrada: float = 12000.0


@router.post("/unidades/memoria-rapida")
def unidades_memoria_rapida(body: UnidadesRapida):
    """Narra la conversión de unidades de un import ETABS y expone el fallback
    silencioso a kgf. NO toca la BD."""
    return memoria_factores_unidad(body.unidad, body.p_entrada, body.m_entrada,
                                   meta_extra={"origen": "calculadora libre"})


# ─────────────────────────────────────────────────────────────────────────────
# 6) PREDIMENSIONAMIENTO — calculo_estructural.predimensionar. RIESGO BAJO.
# ─────────────────────────────────────────────────────────────────────────────
class PredimRapida(BaseModel):
    tipo: str = "VIGA"
    niveles: int = 1
    luz_libre_cm: float = 500.0
    b_apoyo_cm: float = 30.0
    recubrimiento_cm: float = 4.0


@router.post("/predimensionar/memoria-rapida")
def predim_memoria_rapida(body: PredimRapida):
    """Narra el predimensionamiento y deja escrito que las reglas son heurística
    del despacho, NO ACI 318-19. NO toca la BD."""
    return memoria_predimensionar(body.tipo, body.niveles, body.luz_libre_cm,
                                  body.b_apoyo_cm, body.recubrimiento_cm,
                                  meta_extra={"origen": "calculadora libre"})


# ─────────────────────────────────────────────────────────────────────────────
# 7) ACERO POR FICHA — backend/acero_ficha.py. RIESGO BAJO, ALTA COMPLEJIDAD.
# ─────────────────────────────────────────────────────────────────────────────
class MiembroAcero(BaseModel):
    frame: str = ""
    perfil: str = ""
    rol: str = ""
    longitud_mL: float = 0.0
    dc: Optional[float] = None
    combo: str = ""


class AceroFichaRapida(BaseModel):
    miembros: list[MiembroAcero] = []


@router.post("/acero-ficha/memoria-rapida")
def acero_ficha_memoria_rapida(body: AceroFichaRapida):
    """Narra la agregación de miembros de acero por ficha Div 05: mapeo,
    agrupación por (ficha, perfil, rol), envolvente D/C y los tres puntos donde
    la cadena descarta información en silencio. NO toca la BD."""
    try:
        return memoria_agregacion_ficha([m.model_dump() for m in body.miembros],
                                        meta_extra={"origen": "calculadora libre"})
    except ValueError as ex:
        raise HTTPException(status_code=422, detail=str(ex))
