import uuid
from datetime import date, datetime
from sqlalchemy import (
    Column, String, Text, Numeric, SmallInteger, Boolean, Date,
    DateTime, ForeignKey, CheckConstraint
)
from sqlalchemy.orm import relationship
from backend.db import Base


def new_uuid():
    return str(uuid.uuid4())


class Presupuesto(Base):
    __tablename__ = "presupuesto"

    id         = Column(String(36), primary_key=True, default=new_uuid)
    nombre     = Column(Text, nullable=False)
    cliente    = Column(Text)
    fecha      = Column(Date, default=date.today)
    moneda     = Column(String(10), default="HNL")
    es_template = Column(Boolean, default=False)   # True = Template CC 2026
    created_at = Column(DateTime, default=datetime.utcnow)

    config    = relationship("ConfigPresupuesto", back_populates="presupuesto", uselist=False, cascade="all, delete-orphan")
    capitulos = relationship("Capitulo", back_populates="presupuesto", cascade="all, delete-orphan", order_by="Capitulo.orden")
    financiero_items     = relationship("FinancieroItem", back_populates="presupuesto",
                                        cascade="all, delete-orphan", order_by="FinancieroItem.orden")
    financiero_calculos   = relationship("FinancieroCalculo", back_populates="presupuesto",
                                        cascade="all, delete-orphan", order_by="FinancieroCalculo.generado_at.desc()")


class ConfigPresupuesto(Base):
    __tablename__ = "config_presupuesto"

    id               = Column(String(36), primary_key=True, default=new_uuid)
    presupuesto_id   = Column(String(36), ForeignKey("presupuesto.id", ondelete="CASCADE"))
    sobrecosto       = Column(Numeric(5, 2), default=20)   # % overhead sobre costo base → PU = base × (1 + sobrecosto/100)
    administracion   = Column(Numeric(5, 2), default=0)    # % indirecto al total proyecto
    utilidad         = Column(Numeric(5, 2), default=0)
    imprevistos      = Column(Numeric(5, 2), default=0)
    iva              = Column(Numeric(5, 2), default=15)
    otros_factor     = Column(Numeric(5, 2), default=0)
    template_version = Column(String(10), default="v1.2")  # Template DB version: v1.2 vigente, v1.1 legacy, v1.0 original

    presupuesto = relationship("Presupuesto", back_populates="config")


DIVISIONES_CSI = {
    "00": "Preliminares y Contratos",
    "01": "Requerimientos Generales",
    "02": "Condiciones Existentes",
    "03": "Concreto",
    "04": "Mampostería",
    "05": "Metales",
    "06": "Madera y Carpintería",
    "07": "Protección Térmica e Impermeabilización",
    "08": "Puertas y Ventanas",
    "09": "Acabados",
    "10": "Especialidades",
    "11": "Equipamiento",
    "12": "Mobiliario",
    "21": "Protección contra Incendios",
    "22": "Plomería",
    "23": "HVAC",
    "25": "Iluminación",
    "26": "Eléctrico",
    "27": "Comunicaciones",
    "28": "Seguridad Electrónica",
    "31": "Movimiento de Tierra",
    "32": "Obras Exteriores",
    "33": "Utilidades del Sitio",
}


class Capitulo(Base):
    __tablename__ = "capitulo"

    id               = Column(String(36), primary_key=True, default=new_uuid)
    presupuesto_id   = Column(String(36), ForeignKey("presupuesto.id", ondelete="CASCADE"), index=True)
    clave            = Column(Text, nullable=False)   # "03"
    nombre           = Column(Text, nullable=False)   # "Concreto"
    orden            = Column(SmallInteger, default=0)

    presupuesto = relationship("Presupuesto", back_populates="capitulos")
    partidas    = relationship("Partida", back_populates="capitulo", cascade="all, delete-orphan", order_by="Partida.orden")


class Partida(Base):
    __tablename__ = "partida"

    id               = Column(String(36), primary_key=True, default=new_uuid)
    capitulo_id      = Column(String(36), ForeignKey("capitulo.id", ondelete="CASCADE"), index=True)
    clave_csi        = Column(Text, nullable=False)     # "03 31 00.1"
    descripcion      = Column(Text, nullable=False)
    unidad           = Column(Text, nullable=False)
    cantidad         = Column(Numeric(14, 4), default=0)

    # Precios históricos — fuente: EstimaStruct DB (no se recalculan en runtime)
    costo_mo         = Column(Numeric(14, 4), default=0)   # Mano de obra unitaria
    costo_ma         = Column(Numeric(14, 4), default=0)   # Material unitario
    unitario_matriz  = Column(Numeric(14, 4), default=0)   # Sub-matrices OPUS
    costo_base       = Column(Numeric(14, 4), default=0)   # = MO + MA + Matriz
    precio_unitario  = Column(Numeric(14, 4), default=0)   # = costo_base × (1 + sobrecosto/100)
    total            = Column(Numeric(14, 4), default=0)   # = cantidad × precio_unitario

    # Inputs de Revit y factores de fórmula
    revit_q          = Column(Numeric(14, 4), default=0)    # Casilla editable (valor bruto de Revit)
    factor_e         = Column(Numeric(14, 6), default=1)    # Factor col E del Excel
    factor_f         = Column(Numeric(14, 6), default=1)    # Factor col F del Excel
    color_tipo       = Column(Text, default='rosa')          # verde=asignado Revit OK | rojo=conflicto Revit | rosa=no asignado en Revit (default) | amarillo=manual/labor | azul=manual/otro (semantica 2026-08-01, ver sync_audit_colors.py)

    # Metadata de la BD origen
    es_formula       = Column(Boolean, default=False)   # Celda amarilla en BaseDatosOpus
    formula_ref      = Column(Text)                     # Fórmula original de referencia
    type_mark        = Column(Text)                     # Col M del Excel
    omniclass_num    = Column(Text)                     # Col O
    assembly_num     = Column(Text)                     # Col Q

    orden            = Column(SmallInteger, default=0)

    capitulo = relationship("Capitulo", back_populates="partidas")
    insumos  = relationship("InsumoPartida", back_populates="partida",
                            cascade="all, delete-orphan", order_by="InsumoPartida.orden")


TIPOS_RECURSO = ("MATERIAL", "MANO_OBRA", "HERRAMIENTA", "EQUIPO", "FLETE", "SUBCONTRATO", "DISEÑO")

UNIDADES = [
    "m2","m3","m","mL","ml","kg","ton","global","glb","pza","unidad",
    "mes","hr","jor","viaje","und","lt","gal","lb","pie2","pie3",
    "caja","rollo","saco","bolsa","par","juego","set","km","cm","mm",
]


class InsumoPartida(Base):
    __tablename__ = "insumo_partida"

    id          = Column(String(36), primary_key=True, default=new_uuid)
    partida_id  = Column(String(36), ForeignKey("partida.id", ondelete="CASCADE"), index=True)
    recurso_id  = Column(String(36), ForeignKey("recurso.id", ondelete="SET NULL"), nullable=True, index=True)
    clave       = Column(Text, nullable=False)
    descripcion = Column(Text, nullable=False)
    unidad      = Column(Text, nullable=False)
    tipo        = Column(Text, nullable=False)   # MATERIAL | MANO_OBRA | EQUIPO | etc.
    cantidad    = Column(Numeric(14, 6), default=0)
    costo_unit  = Column(Numeric(14, 4), default=0)
    total       = Column(Numeric(14, 4), default=0)
    orden       = Column(SmallInteger, default=0)

    partida = relationship("Partida", back_populates="insumos")
    recurso = relationship("Recurso")


class Recurso(Base):
    __tablename__ = "recurso"

    id                   = Column(String(36), primary_key=True, default=new_uuid)
    clave                = Column(Text, unique=True, nullable=False)
    descripcion          = Column(Text, nullable=False)
    unidad               = Column(Text, nullable=False)
    tipo                 = Column(Text, nullable=False)
    precio_unitario      = Column(Numeric(14, 4), default=0)
    ultima_actualizacion = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        CheckConstraint(f"tipo IN {TIPOS_RECURSO}", name="ck_recurso_tipo"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# MÓDULO DISEÑO ESTRUCTURAL — Div 03 / 04 CSI
# (Soldadura §J2 eliminada en R7 — subsumida por Conexión §J. Backup de BD hecho.)
# ─────────────────────────────────────────────────────────────────────────────

class DisenoElemento(Base):
    __tablename__ = "diseno_elemento"

    id             = Column(String(36), primary_key=True, default=new_uuid)
    presupuesto_id = Column(String(36), ForeignKey("presupuesto.id", ondelete="CASCADE"), nullable=False)

    # Identificación — CSI es la llave maestra
    csi            = Column(Text, default="", index=True)  # "03 31 00.11" — IDENTIFICADOR PRINCIPAL
    type_mark      = Column(Text, default="")   # etiqueta secundaria opcional ("VA-01")
    tipo           = Column(Text, default="VIGA_SIMPLE")  # VIGA_SIMPLE|VIGA_DOBLE|VIGA_T|COLUMNA
    notas          = Column(Text, default="")

    # Geometría viga
    b_cm           = Column(Numeric(10, 3), default=30)    # ancho o bw
    d_cm           = Column(Numeric(10, 3), default=50)    # peralte efectivo
    d_prima_cm     = Column(Numeric(10, 3), default=5)     # recubrimiento compresión (doble armado)
    bp_cm          = Column(Numeric(10, 3), default=0)     # patín viga T
    t_cm           = Column(Numeric(10, 3), default=0)     # espesor patín viga T

    # Geometría columna
    lx_cm          = Column(Numeric(10, 3), default=0)
    ly_cm          = Column(Numeric(10, 3), default=0)

    # Material
    fc_kg_cm2      = Column(Numeric(10, 2), default=210)
    fy_kg_cm2      = Column(Numeric(10, 2), default=4200)

    # Longitud para takeoff
    longitud_m     = Column(Numeric(10, 3), default=0)

    # Acero estructural LRFD (material_tipo=ACERO) — aditivo. Reusa tipo
    # (VIGA_SIMPLE|COLUMNA) para el rol y longitud_m para L. K/Lb van en el caso.
    material_tipo  = Column(Text, default="CONCRETO")   # CONCRETO | ACERO
    perfil_acero   = Column(Text, default="")           # designacion W/HSS (TABLA_W)
    acero_grado    = Column(Text, default="A992")        # A992 | A36 | A500

    created_at     = Column(DateTime, default=datetime.utcnow)

    presupuesto    = relationship("Presupuesto")
    casos          = relationship("CasoDiseno", back_populates="elemento",
                                  cascade="all, delete-orphan", order_by="CasoDiseno.created_at")


class CasoDiseno(Base):
    __tablename__ = "caso_diseno"

    id                 = Column(String(36), primary_key=True, default=new_uuid)
    diseno_elemento_id = Column(String(36), ForeignKey("diseno_elemento.id", ondelete="CASCADE"), nullable=False)

    nombre             = Column(Text, default="D+L")   # "D+L", "D+L+E", "Sismo X"
    gobierna           = Column(Boolean, default=False)

    # Trazabilidad del import ETABS (puente concreto). Aditivo — ALTER idempotente.
    origen             = Column(Text, default="MANUAL")   # MANUAL | ETABS
    combo_etabs        = Column(Text, default="")         # "1.2D+1.0L+E" (OutputCase ETABS)

    # Cargas viga
    mu_tm              = Column(Numeric(14, 4), default=0)   # Momento último [t·m]
    vu_t               = Column(Numeric(14, 4), default=0)   # Cortante último [t]
    tu_tm              = Column(Numeric(14, 4), default=0)   # Torsión última [t·m]
    nu_t               = Column(Numeric(14, 4), default=0)   # Axial viga [t] (+comp, -tensión)

    # Cargas columna
    pu_t               = Column(Numeric(14, 4), default=0)   # Axial última [t]
    mu_xx_tm           = Column(Numeric(14, 4), default=0)   # Momento eje fuerte [t·m]
    mu_yy_tm           = Column(Numeric(14, 4), default=0)   # Momento eje débil [t·m]

    # Esbeltez columna
    lu_cm              = Column(Numeric(10, 3), default=0)
    k_x                = Column(Numeric(8, 4), default=1.0)
    k_y                = Column(Numeric(8, 4), default=1.0)
    bd_x               = Column(Numeric(8, 4), default=0.15)
    bd_y               = Column(Numeric(8, 4), default=0.15)
    cm_x               = Column(Numeric(8, 4), default=1.0)
    cm_y               = Column(Numeric(8, 4), default=1.0)

    created_at         = Column(DateTime, default=datetime.utcnow)

    elemento   = relationship("DisenoElemento", back_populates="casos")
    resultado  = relationship("ResultadoDiseno", uselist=False, back_populates="caso",
                              cascade="all, delete-orphan")


class ResultadoDiseno(Base):
    __tablename__ = "resultado_diseno"

    id       = Column(String(36), primary_key=True, default=new_uuid)
    caso_id  = Column(String(36), ForeignKey("caso_diseno.id", ondelete="CASCADE"), nullable=False)

    # Flexión
    pb           = Column(Numeric(14, 6), default=0)
    pmax         = Column(Numeric(14, 6), default=0)
    as_cm2       = Column(Numeric(14, 4), default=0)
    a_prima_cm2  = Column(Numeric(14, 4), default=0)
    as_min_cm2   = Column(Numeric(14, 4), default=0)
    as_max_cm2   = Column(Numeric(14, 4), default=0)

    # Cortante / torsión
    vc_kg_cm2    = Column(Numeric(14, 4), default=0)
    vtu_kg_cm2   = Column(Numeric(14, 4), default=0)
    av_cm2       = Column(Numeric(14, 4), default=0)
    at_cm2       = Column(Numeric(14, 4), default=0)
    al_cm2       = Column(Numeric(14, 4), default=0)
    s_max_cm     = Column(Numeric(14, 4), default=20)

    # Columna
    delta_x      = Column(Numeric(10, 4), default=1.0)
    delta_y      = Column(Numeric(10, 4), default=1.0)
    as_col_cm2   = Column(Numeric(14, 4), default=0)
    pg_pct       = Column(Numeric(10, 4), default=0)

    # Takeoff CSI 03
    concreto_m3  = Column(Numeric(14, 4), default=0)
    encofrado_m2 = Column(Numeric(14, 4), default=0)
    acero_kg     = Column(Numeric(14, 4), default=0)
    estribos_kg  = Column(Numeric(14, 4), default=0)

    # Verificaciones
    ok_sismico   = Column(Boolean, default=True)
    ok_pg        = Column(Boolean, default=True)
    advertencias = Column(Text, default="")

    # Acero LRFD (material_tipo=ACERO) — aditivo. φRn/DC por el motor §D-H.
    acero_estado_gob   = Column(Text, default="")             # estado limite gobernante
    acero_phi_rn_gob   = Column(Numeric(14, 4), default=0)     # φRn gobernante [t o t·m]
    acero_dc           = Column(Numeric(10, 4), default=0)     # DC gobernante
    acero_cumple       = Column(Boolean, default=True)         # demanda ≤ φRn
    acero_estados_json = Column(Text, default="")             # estados completos (JSON)

    # Links a partidas generadas
    partida_concreto_id  = Column(String(36), ForeignKey("partida.id", ondelete="SET NULL"), nullable=True)
    partida_acero_id     = Column(String(36), ForeignKey("partida.id", ondelete="SET NULL"), nullable=True)
    partida_encofrado_id = Column(String(36), ForeignKey("partida.id", ondelete="SET NULL"), nullable=True)

    calculado_at = Column(DateTime, default=datetime.utcnow)

    caso = relationship("CasoDiseno", back_populates="resultado")


# ─────────────────────────────────────────────────────────────────────────────
# CONTEXTO SÍSMICO POR PRESUPUESTO — CHOC-08 (1:1 con presupuesto)
# Tabla NUEVA → create_all la crea sola (no requiere ALTER). ADITIVA.
# ─────────────────────────────────────────────────────────────────────────────

class ContextoSismico(Base):
    __tablename__ = "contexto_sismico"

    id             = Column(String(36), primary_key=True, default=new_uuid)
    # 1:1 con el presupuesto → unique. CASCADE al borrar el presupuesto.
    presupuesto_id = Column(String(36), ForeignKey("presupuesto.id", ondelete="CASCADE"),
                            nullable=False, unique=True, index=True)

    norma          = Column(Text, default="CHOC-08")

    # Ubicación / zonificación
    municipio      = Column(Text, default="")
    zona           = Column(Text, default="3b")     # clave de ZONAS
    z_factor       = Column(Numeric(6, 4), default=0.25)

    # Perfil de suelo (Tabla 1.3.4-2)
    suelo          = Column(Text, default="S1")      # clave de SUELOS
    s_coef         = Column(Numeric(6, 4), default=1.0)
    ta_s           = Column(Numeric(8, 4), default=0.155)
    tb_s           = Column(Numeric(8, 4), default=0.364)
    c_exp          = Column(Numeric(6, 4), default=2.0)

    # Factores y geometría
    importancia_i  = Column(Numeric(6, 4), default=1.0)
    rw             = Column(Numeric(6, 4), default=8)
    deriva_limite  = Column(Numeric(8, 5), default=0.005)
    hn_m           = Column(Numeric(10, 3), default=3)
    w_t            = Column(Numeric(14, 2), default=1206)

    # Datos leídos de ETABS (verificación)
    v_din_t        = Column(Numeric(14, 2), nullable=True)
    deriva_real    = Column(Numeric(10, 6), nullable=True)

    # Espectro serializado (lista de pares [T, a/g])
    espectro_json  = Column(Text, default="")
    notas          = Column(Text, default="")

    updated_at     = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    presupuesto    = relationship("Presupuesto")


# ─────────────────────────────────────────────────────────────────────────────
# CONEXIONES DE ACERO — persistencia §J (R5). 3 tablas NUEVAS; create_all las
# crea solas (ADITIVO, no toca data existente). Espeja el patrón
# DisenoElemento / CasoDiseno / ResultadoDiseno.
# ─────────────────────────────────────────────────────────────────────────────

class ConexionAcero(Base):
    __tablename__ = "conexion_acero"

    id             = Column(String(36), primary_key=True, default=new_uuid)
    presupuesto_id = Column(String(36), ForeignKey("presupuesto.id", ondelete="CASCADE"), nullable=False)

    # Identificación
    csi            = Column(Text, default="", index=True)   # ficha CV/VV/CX (llave maestra)
    type_mark      = Column(Text, default="")               # etiqueta (junta J1, pedestal Pn…)
    tipo_conexion  = Column(Text, default="VC_CORTANTE")     # VC_CORTANTE|VC_MOMENTO|VV|SOLDADA|PLACA_BASE
    perfil_viga    = Column(Text, default="")
    perfil_columna = Column(Text, default="")
    acero          = Column(Text, default="A992")
    notas          = Column(Text, default="")

    # Geometría placa / pernos / soldadura
    t_placa_cm     = Column(Numeric(10, 3), default=0.95)
    perno_grado    = Column(Text, default="A325")
    perno_d_cm     = Column(Numeric(10, 3), default=1.9)
    n_pernos       = Column(SmallInteger, default=3)
    roscas_en_corte = Column(Boolean, default=True)
    w_filete_cm    = Column(Numeric(10, 3), default=0)
    L_soldadura_cm = Column(Numeric(10, 3), default=0)

    # Placa base §J8
    fc_kg_cm2      = Column(Numeric(10, 2), default=210)
    B_placa_cm     = Column(Numeric(10, 3), default=0)
    N_placa_cm     = Column(Numeric(10, 3), default=0)
    A2_cm2         = Column(Numeric(12, 2), default=0)

    # Link a partida Div 05 generada
    partida_id     = Column(String(36), ForeignKey("partida.id", ondelete="SET NULL"), nullable=True)

    created_at     = Column(DateTime, default=datetime.utcnow)

    presupuesto    = relationship("Presupuesto")
    casos          = relationship("ConexionCaso", back_populates="conexion",
                                  cascade="all, delete-orphan", order_by="ConexionCaso.created_at")


class ConexionCaso(Base):
    __tablename__ = "conexion_caso"

    id           = Column(String(36), primary_key=True, default=new_uuid)
    conexion_id  = Column(String(36), ForeignKey("conexion_acero.id", ondelete="CASCADE"), nullable=False)

    nombre       = Column(Text, default="D+L")
    gobierna     = Column(Boolean, default=False)
    origen       = Column(Text, default="MANUAL")    # MANUAL | ETABS
    combo_etabs  = Column(Text, default="")

    # Demanda §J
    vu_t         = Column(Numeric(14, 4), default=0)   # cortante [t]
    nu_t         = Column(Numeric(14, 4), default=0)   # axial conexión [t]
    mu_tm        = Column(Numeric(14, 4), default=0)   # momento [t·m]
    pu_t         = Column(Numeric(14, 4), default=0)   # axial columna (placa base) [t]

    created_at   = Column(DateTime, default=datetime.utcnow)

    conexion     = relationship("ConexionAcero", back_populates="casos")
    resultado    = relationship("ConexionResultado", uselist=False, back_populates="caso",
                                cascade="all, delete-orphan")


class ConexionResultado(Base):
    __tablename__ = "conexion_resultado"

    id           = Column(String(36), primary_key=True, default=new_uuid)
    caso_id      = Column(String(36), ForeignKey("conexion_caso.id", ondelete="CASCADE"), nullable=False)

    estado_gob   = Column(Text, default="")            # estado límite gobernante §J
    phi_rn_gob   = Column(Numeric(14, 4), default=0)    # φRn gobernante [t]
    demanda_t    = Column(Numeric(14, 4), default=0)    # demanda gobernante [t]
    dc           = Column(Numeric(10, 4), default=0)    # DC gobernante
    cumple       = Column(Boolean, default=True)
    estados_json = Column(Text, default="")            # estados completos (JSON)
    j8_json      = Column(Text, default="")            # detalle §J8 placa base (JSON)

    calculado_at = Column(DateTime, default=datetime.utcnow)

    caso = relationship("ConexionCaso", back_populates="resultado")


# ─────────────────────────────────────────────────────────────────────────────
# CRONOGRAMA — override de cuadrillas por actividad (Gantt). Tabla NUEVA,
# create_all la crea sola (ADITIVA, no toca partida). 1 fila por partida que
# el usuario haya ajustado; ausencia = 1 cuadrilla (default).
# ─────────────────────────────────────────────────────────────────────────────

class CronogramaOverride(Base):
    __tablename__ = "cronograma_override"

    id             = Column(String(36), primary_key=True, default=new_uuid)
    presupuesto_id = Column(String(36), ForeignKey("presupuesto.id", ondelete="CASCADE"),
                            nullable=False, index=True)
    partida_id     = Column(String(36), ForeignKey("partida.id", ondelete="CASCADE"),
                            nullable=False, unique=True, index=True)
    cuadrillas     = Column(SmallInteger, default=1)   # DEPRECADO (legacy)
    n_esp          = Column(SmallInteger, default=3)   # especialistas en paralelo (>=1)
    n_ay           = Column(SmallInteger, default=3)   # ayudantes en paralelo (>=1)

    updated_at     = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ─────────────────────────────────────────────────────────────────────────────
# FINANCIERO — cédula de indirectos auditable (imprevistos, seguros, fianzas,
# administración, utilidad, escalamiento, IVA). ADITIVO — 2 tablas NUEVAS,
# create_all las crea solas (no ALTER de config_presupuesto/partida/presupuesto).
#
# Por qué existe: auditoría del catálogo v1.3 (1145 partidas vs RICS ICMS 3rd
# ed.) encontró config_presupuesto.imprevistos/administracion en 0.00 en las
# 6 obras reales, con todo el margen metido en un solo campo `sobrecosto`
# (15-25% sin desglosar) y CERO partidas de seguros/fianzas. Este módulo NO
# reemplaza sobrecosto/config_presupuesto (otros routers los leen, se dejan
# intactos) — es la cédula financiera trazable que un auditor fiscal exigiría
# encima: cada indirecto con su base de cálculo, su orden de aplicación
# (interés compuesto, no aditivo plano), su evidencia (póliza/afianzadora) y
# snapshots INMUTABLES por cálculo (financiero_calculo nunca se actualiza,
# solo se crea uno nuevo — como una cédula de ejercicio fiscal cerrado).
# ─────────────────────────────────────────────────────────────────────────────

TIPOS_FINANCIERO_ITEM = (
    "IMPREVISTO", "SEGURO", "FIANZA", "ADMINISTRACION",
    "UTILIDAD", "IMPUESTO", "ESCALAMIENTO", "OTRO",
)
BASES_CALCULO_FINANCIERO = ("COSTO_DIRECTO", "SUBTOTAL_ACUMULADO", "MONTO_FIJO")


class FinancieroItem(Base):
    """Catálogo de indirectos por presupuesto — editable, nunca se borra
    duro (auditoría: un % ya usado en un cálculo histórico no puede
    desaparecer sin dejar rastro; se desactiva con `activo=False`)."""
    __tablename__ = "financiero_item"

    id             = Column(String(36), primary_key=True, default=new_uuid)
    presupuesto_id = Column(String(36), ForeignKey("presupuesto.id", ondelete="CASCADE"),
                            nullable=False, index=True)

    # Ancla de auditoría: código ICMS Group.SubGroup (RICS ICMS 3rd ed.)
    categoria_icms = Column(Text, default="")   # "09.020", "08.110", ...
    tipo           = Column(Text, nullable=False, default="OTRO")
    nombre         = Column(Text, nullable=False)

    base_calculo   = Column(Text, nullable=False, default="COSTO_DIRECTO")
    porcentaje     = Column(Numeric(7, 4), nullable=True)    # solo si base_calculo != MONTO_FIJO
    monto_fijo     = Column(Numeric(14, 4), nullable=True)   # solo si base_calculo == MONTO_FIJO

    orden          = Column(SmallInteger, nullable=False, default=0)
    obligatorio    = Column(Boolean, default=False)   # ICMS lo trata como reporte obligatorio
    evidencia      = Column(Text, default="")         # póliza/afianzadora/aseguradora/vigencia
    activo         = Column(Boolean, default=True)

    created_at     = Column(DateTime, default=datetime.utcnow)
    updated_at     = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        CheckConstraint(f"tipo IN {TIPOS_FINANCIERO_ITEM}", name="ck_financiero_item_tipo"),
        CheckConstraint(f"base_calculo IN {BASES_CALCULO_FINANCIERO}", name="ck_financiero_item_base"),
    )

    presupuesto    = relationship("Presupuesto", back_populates="financiero_items")


class FinancieroCalculo(Base):
    """Snapshot INMUTABLE de una cédula financiera calculada. Nunca se
    actualiza — cada POST /calcular crea una fila nueva. `items_json`
    congela cada financiero_item aplicado CON su monto_calculado y la base
    sobre la que se aplicó, para que el snapshot siga siendo auditable
    aunque el financiero_item se edite o desactive después."""
    __tablename__ = "financiero_calculo"

    id                  = Column(String(36), primary_key=True, default=new_uuid)
    presupuesto_id      = Column(String(36), ForeignKey("presupuesto.id", ondelete="CASCADE"),
                                 nullable=False, index=True)

    costo_directo       = Column(Numeric(14, 4), default=0)
    iva_pct             = Column(Numeric(7, 4), default=15)
    items_json          = Column(Text, default="[]")
    subtotal_antes_iva  = Column(Numeric(14, 4), default=0)
    iva_monto           = Column(Numeric(14, 4), default=0)
    total_general       = Column(Numeric(14, 4), default=0)

    generado_at         = Column(DateTime, default=datetime.utcnow)
    nota                = Column(Text, default="")

    presupuesto         = relationship("Presupuesto", back_populates="financiero_calculos")
