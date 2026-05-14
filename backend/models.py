import uuid
from datetime import date, datetime
from sqlalchemy import (
    Column, String, Text, Numeric, SmallInteger, Boolean, Date,
    DateTime, ForeignKey, CheckConstraint
)
from sqlalchemy.orm import relationship
from db import Base


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
    template_version = Column(String(10), default="v1.0")  # Template DB version: v1.0 (original), v1.1 (updated), etc

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
    presupuesto_id   = Column(String(36), ForeignKey("presupuesto.id", ondelete="CASCADE"))
    clave            = Column(Text, nullable=False)   # "03"
    nombre           = Column(Text, nullable=False)   # "Concreto"
    orden            = Column(SmallInteger, default=0)

    presupuesto = relationship("Presupuesto", back_populates="capitulos")
    partidas    = relationship("Partida", back_populates="capitulo", cascade="all, delete-orphan", order_by="Partida.orden")


class Partida(Base):
    __tablename__ = "partida"

    id               = Column(String(36), primary_key=True, default=new_uuid)
    capitulo_id      = Column(String(36), ForeignKey("capitulo.id", ondelete="CASCADE"))
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
    color_tipo       = Column(Text, default='blanco')       # amarillo|verde|azul|rosa|blanco

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
    partida_id  = Column(String(36), ForeignKey("partida.id", ondelete="CASCADE"))
    recurso_id  = Column(String(36), ForeignKey("recurso.id", ondelete="SET NULL"), nullable=True)
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


class MatrizSoldaduraConexion(Base):
    __tablename__ = "soldadura_conexion"

    id               = Column(String(36), primary_key=True, default=new_uuid)
    presupuesto_id   = Column(String(36), ForeignKey("presupuesto.id", ondelete="CASCADE"))

    # Identificación CSI nueva
    clave_csi_nuevo  = Column(Text, nullable=False, default="05 12 00.01")
    type_mark        = Column(Text, nullable=False)

    # Dependencia: CSI de partida estructural de origen
    clave_csi_origen = Column(Text)
    partida_id       = Column(String(36), ForeignKey("partida.id", ondelete="SET NULL"), nullable=True)

    # Clasificación (Cap2)
    perfil_w         = Column(Text, default="W8x48")
    tipo_elemento    = Column(Text, default="VIGA")
    tipo_conexion    = Column(Text, default="VIGA-COLUMNA")
    tipo_soldadura   = Column(Text, default="FILETE")
    tamano_filete    = Column(Text, default="5/16")

    # Cantidades calculadas (Cap4)
    longitud_perfil_m    = Column(Numeric(14, 4), default=0)
    longitud_soldadura_m = Column(Numeric(14, 4), default=0)
    volumen_cm3          = Column(Numeric(14, 4), default=0)
    peso_electrodo_kg    = Column(Numeric(14, 4), default=0)
    horas_hombre         = Column(Numeric(14, 4), default=0)

    # Precios editables
    precio_electrodo = Column(Numeric(14, 4), default=45)
    precio_soldador  = Column(Numeric(14, 4), default=80)

    # Costos calculados
    costo_material   = Column(Numeric(14, 4), default=0)
    costo_mano_obra  = Column(Numeric(14, 4), default=0)
    costo_total      = Column(Numeric(14, 4), default=0)

    # LRFD (Cap3)
    phi_rn       = Column(Numeric(14, 4), default=0)
    vu_aplicado  = Column(Numeric(14, 4), default=0)
    cumple_lrfd  = Column(Boolean, default=False)

    notas      = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    presupuesto = relationship("Presupuesto")
