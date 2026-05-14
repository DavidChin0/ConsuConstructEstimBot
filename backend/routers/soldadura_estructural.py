from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime
from db import get_db
from models import MatrizSoldaduraConexion, Presupuesto, Capitulo, Partida
import uuid, re

router = APIRouter(prefix="/soldadura-estructural", tags=["soldadura-estructural"])


# Tipos CSI predefinidos
TIPOS_CSI = [
    {"clave_csi": "05 12 00.01", "type_mark_base": "SC-VW", "tipo_elemento": "VIGA",     "tipo_conexion": "VIGA-COLUMNA",  "tipo_soldadura": "FILETE", "filete": "5/16"},
    {"clave_csi": "05 12 00.02", "type_mark_base": "SC-CM", "tipo_elemento": "COLUMNA",  "tipo_conexion": "MOMENTO",       "tipo_soldadura": "FILETE", "filete": "3/8"},
    {"clave_csi": "05 12 00.03", "type_mark_base": "SC-DC", "tipo_elemento": "DIAGONAL", "tipo_conexion": "CORTANTE",      "tipo_soldadura": "FILETE", "filete": "1/4"},
    {"clave_csi": "05 12 00.04", "type_mark_base": "SC-RI", "tipo_elemento": "VIGA",     "tipo_conexion": "RIGIDIZADOR",   "tipo_soldadura": "FILETE", "filete": "5/16"},
    {"clave_csi": "05 12 00.05", "type_mark_base": "SC-PB", "tipo_elemento": "COLUMNA",  "tipo_conexion": "PLACA BASE",    "tipo_soldadura": "FILETE", "filete": "1/4"},
    {"clave_csi": "05 12 00.06", "type_mark_base": "SC-EM", "tipo_elemento": "COLUMNA",  "tipo_conexion": "EMPALME",       "tipo_soldadura": "CJP",    "filete": "3/8"},
    {"clave_csi": "05 12 00.07", "type_mark_base": "SC-IN", "tipo_elemento": "VIGA",     "tipo_conexion": "INTERMITENTE",  "tipo_soldadura": "FILETE", "filete": "5/16"},
]

# Datos de perfiles W (altura, ancho de ala en mm)
PERFILES_W = {
    "W8x24":   {"d": 203, "bf": 133},
    "W8x48":   {"d": 203, "bf": 203},
    "W10x33":  {"d": 254, "bf": 203},
    "W12x53":  {"d": 310, "bf": 310},
    "W150x24": {"d": 152, "bf": 102},
    "W150x37": {"d": 152, "bf": 153},
    "W200x36": {"d": 203, "bf": 133},
    "W200x46": {"d": 210, "bf": 205},
    "W200x71": {"d": 210, "bf": 205},
    "W250x49": {"d": 254, "bf": 203},
    "W250x73": {"d": 260, "bf": 260},
    "W310x73": {"d": 310, "bf": 310},
}

# Rendimiento por tamaño filete (kg/hora)
RENDIMIENTO = {
    "1/4":   1.2,
    "5/16":  1.5,
    "3/8":   1.8,
    "7/16":  2.0,
    "1/2":   2.2,
}

# Filetes en pulgadas
FILETES = {
    "1/4":   0.25,
    "5/16":  0.3125,
    "3/8":   0.375,
    "7/16":  0.4375,
    "1/2":   0.5,
}


class SoldaduraCreate(BaseModel):
    clave_csi_nuevo: str = "05 12 00.01"
    type_mark: str
    clave_csi_origen: str = None
    partida_id: str = None
    perfil_w: str = "W8x48"
    tipo_elemento: str = "VIGA"
    tipo_conexion: str = "VIGA-COLUMNA"
    tipo_soldadura: str = "FILETE"
    tamano_filete: str = "5/16"
    longitud_perfil_m: float = 0
    precio_electrodo: float = 45
    precio_soldador: float = 80
    vu_aplicado: float = 0
    notas: str = ""


class SoldaduraUpdate(BaseModel):
    clave_csi_origen: str = None
    perfil_w: str = None
    tipo_elemento: str = None
    tipo_conexion: str = None
    tipo_soldadura: str = None
    tamano_filete: str = None
    longitud_perfil_m: float = None
    precio_electrodo: float = None
    precio_soldador: float = None
    vu_aplicado: float = None
    notas: str = None


def calcular_lrfd(conn: MatrizSoldaduraConexion):
    """Calcula LRFD + cantidades (Cap3 + Cap4)"""

    # Obtener datos del perfil
    perfil = PERFILES_W.get(conn.perfil_w)
    if not perfil:
        return

    d, bf = perfil["d"], perfil["bf"]

    # Tamaño filete → pulgadas
    s = FILETES.get(str(conn.tamano_filete), 0.3125)

    # Cap3: Garganta efectiva
    t = 0.707 * s

    # Cap4: Longitud por metro lineal (mm)
    L_por_metro = 2 * d + 2 * bf
    L_total_mm = L_por_metro * float(conn.longitud_perfil_m)
    L_total_m = L_total_mm / 1000

    # Volumen + peso electrodo
    t_mm = t * 25.4  # pulgadas → mm
    V_mm3 = t_mm * L_total_mm
    V_cm3 = V_mm3 / 1000
    peso_kg = V_cm3 * 7.85 / 1000

    # Horas-hombre
    r = RENDIMIENTO.get(str(conn.tamano_filete), 1.5)
    HH = peso_kg / r if r > 0 else 0

    # Costos
    costo_mat = peso_kg * float(conn.precio_electrodo)
    costo_mo = HH * float(conn.precio_soldador)

    # LRFD (E70XX = 70 ksi)
    FEXX = 70
    Rn = 0.6 * FEXX * t * (L_total_mm * 0.03937)  # L en pulgadas
    phi_Rn = 0.75 * Rn

    # Actualizar modelo
    conn.longitud_soldadura_m = round(L_total_m, 4)
    conn.volumen_cm3 = round(V_cm3, 4)
    conn.peso_electrodo_kg = round(peso_kg, 4)
    conn.horas_hombre = round(HH, 4)
    conn.costo_material = round(costo_mat, 4)
    conn.costo_mano_obra = round(costo_mo, 4)
    conn.costo_total = round(costo_mat + costo_mo, 4)
    conn.phi_rn = round(phi_Rn, 4)
    conn.cumple_lrfd = float(conn.vu_aplicado) <= phi_Rn


@router.get("/tipos")
def get_tipos_csi():
    """Devuelve tipos CSI predefinidos"""
    return {"tipos": TIPOS_CSI}


@router.get("/presupuesto/{pid}")
def get_soldaduras(pid: str, db: Session = Depends(get_db)):
    """Obtiene todas las conexiones de un presupuesto"""
    conexiones = db.query(MatrizSoldaduraConexion).filter(
        MatrizSoldaduraConexion.presupuesto_id == pid
    ).order_by(MatrizSoldaduraConexion.created_at).all()

    return {
        "presupuesto_id": pid,
        "total": len(conexiones),
        "conexiones": [
            {
                "id": c.id,
                "clave_csi_nuevo": c.clave_csi_nuevo,
                "type_mark": c.type_mark,
                "clave_csi_origen": c.clave_csi_origen,
                "perfil_w": c.perfil_w,
                "tipo_elemento": c.tipo_elemento,
                "tipo_conexion": c.tipo_conexion,
                "tipo_soldadura": c.tipo_soldadura,
                "tamano_filete": c.tamano_filete,
                "longitud_perfil_m": float(c.longitud_perfil_m),
                "longitud_soldadura_m": float(c.longitud_soldadura_m),
                "peso_electrodo_kg": float(c.peso_electrodo_kg),
                "horas_hombre": float(c.horas_hombre),
                "precio_electrodo": float(c.precio_electrodo),
                "precio_soldador": float(c.precio_soldador),
                "costo_material": float(c.costo_material),
                "costo_mano_obra": float(c.costo_mano_obra),
                "costo_total": float(c.costo_total),
                "phi_rn": float(c.phi_rn),
                "vu_aplicado": float(c.vu_aplicado),
                "cumple_lrfd": c.cumple_lrfd,
                "notas": c.notas,
                "created_at": c.created_at.isoformat(),
            }
            for c in conexiones
        ]
    }


@router.post("/presupuesto/{pid}")
def create_soldadura(pid: str, data: SoldaduraCreate, db: Session = Depends(get_db)):
    """Crea nueva conexión de soldadura"""

    # Verificar presupuesto existe
    presupuesto = db.query(Presupuesto).filter(Presupuesto.id == pid).first()
    if not presupuesto:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")

    conn = MatrizSoldaduraConexion(
        id=str(uuid.uuid4()),
        presupuesto_id=pid,
        clave_csi_nuevo=data.clave_csi_nuevo,
        type_mark=data.type_mark,
        clave_csi_origen=data.clave_csi_origen,
        partida_id=data.partida_id,
        perfil_w=data.perfil_w,
        tipo_elemento=data.tipo_elemento,
        tipo_conexion=data.tipo_conexion,
        tipo_soldadura=data.tipo_soldadura,
        tamano_filete=data.tamano_filete,
        longitud_perfil_m=data.longitud_perfil_m,
        precio_electrodo=data.precio_electrodo,
        precio_soldador=data.precio_soldador,
        vu_aplicado=data.vu_aplicado,
        notas=data.notas,
    )

    # Calcular LRFD
    calcular_lrfd(conn)

    db.add(conn)
    db.commit()
    db.refresh(conn)

    return {
        "id": conn.id,
        "type_mark": conn.type_mark,
        "costo_total": float(conn.costo_total),
        "cumple_lrfd": conn.cumple_lrfd,
    }


@router.patch("/{sid}")
def update_soldadura(sid: str, data: SoldaduraUpdate, db: Session = Depends(get_db)):
    """Actualiza campo de conexión"""

    conn = db.query(MatrizSoldaduraConexion).filter(
        MatrizSoldaduraConexion.id == sid
    ).first()

    if not conn:
        raise HTTPException(status_code=404, detail="Conexión no encontrada")

    # Actualizar campos proporcionados
    if data.clave_csi_origen is not None:
        conn.clave_csi_origen = data.clave_csi_origen
    if data.perfil_w is not None:
        conn.perfil_w = data.perfil_w
    if data.tipo_elemento is not None:
        conn.tipo_elemento = data.tipo_elemento
    if data.tipo_conexion is not None:
        conn.tipo_conexion = data.tipo_conexion
    if data.tipo_soldadura is not None:
        conn.tipo_soldadura = data.tipo_soldadura
    if data.tamano_filete is not None:
        conn.tamano_filete = data.tamano_filete
    if data.longitud_perfil_m is not None:
        conn.longitud_perfil_m = data.longitud_perfil_m
    if data.precio_electrodo is not None:
        conn.precio_electrodo = data.precio_electrodo
    if data.precio_soldador is not None:
        conn.precio_soldador = data.precio_soldador
    if data.vu_aplicado is not None:
        conn.vu_aplicado = data.vu_aplicado
    if data.notas is not None:
        conn.notas = data.notas

    # Recalcular LRFD si cambió algo relevante
    calcular_lrfd(conn)

    db.commit()
    db.refresh(conn)

    return {"id": conn.id, "costo_total": float(conn.costo_total), "cumple_lrfd": conn.cumple_lrfd}


@router.post("/{sid}/calcular")
def calcular_soldadura_endpoint(sid: str, db: Session = Depends(get_db)):
    """Recalcula LRFD + cantidades"""

    conn = db.query(MatrizSoldaduraConexion).filter(
        MatrizSoldaduraConexion.id == sid
    ).first()

    if not conn:
        raise HTTPException(status_code=404, detail="Conexión no encontrada")

    calcular_lrfd(conn)
    db.commit()
    db.refresh(conn)

    return {
        "id": conn.id,
        "longitud_soldadura_m": float(conn.longitud_soldadura_m),
        "peso_electrodo_kg": float(conn.peso_electrodo_kg),
        "horas_hombre": float(conn.horas_hombre),
        "costo_total": float(conn.costo_total),
        "phi_rn": float(conn.phi_rn),
        "cumple_lrfd": conn.cumple_lrfd,
    }


@router.delete("/{sid}")
def delete_soldadura(sid: str, db: Session = Depends(get_db)):
    """Elimina conexión"""

    conn = db.query(MatrizSoldaduraConexion).filter(
        MatrizSoldaduraConexion.id == sid
    ).first()

    if not conn:
        raise HTTPException(status_code=404, detail="Conexión no encontrada")

    db.delete(conn)
    db.commit()

    return {"status": "deleted", "id": sid}


def detectar_perfil(descripcion: str, type_mark: str) -> str:
    texto = f"{descripcion or ''} {type_mark or ''}".upper()
    match = re.search(r'W(\d+)[Xx](\d+)', texto)
    if match:
        clave = f"W{match.group(1)}x{match.group(2)}"
        if clave in PERFILES_W:
            return clave
    if "COLUMNA" in texto:
        return "W250x73"
    return "W200x46"


def _get_sobrecosto(pid: str, db: Session) -> float:
    """Obtiene el sobrecosto del presupuesto para calcular el PU de la partida unificada."""
    presupuesto = db.query(Presupuesto).filter(Presupuesto.id == pid).first()
    if not presupuesto or not presupuesto.config or presupuesto.config.sobrecosto is None:
        return 20.0
    return float(presupuesto.config.sobrecosto)


@router.post("/sync/{pid}")
def sync_soldaduras(pid: str, db: Session = Depends(get_db)):
    """Sincroniza conexiones soldadura desde partidas de acero CSI 05 del presupuesto"""

    presupuesto = db.query(Presupuesto).filter(Presupuesto.id == pid).first()
    if not presupuesto:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")

    # Leer todos los capítulos y partidas del presupuesto
    capitulos = db.query(Capitulo).filter(Capitulo.presupuesto_id == pid).all()

    partidas_acero = []
    cap_05 = None
    for cap in capitulos:
        if cap.clave.startswith("05"):
            cap_05 = cap
            for p in cap.partidas:
                if p.clave_csi == "05 12 00.00":
                    continue  # skip la partida unificada
                desc = (p.descripcion or "").lower()
                tipo_elem = None
                if "viga" in desc:
                    tipo_elem = "VIGA"
                elif "columna" in desc:
                    tipo_elem = "COLUMNA"
                else:
                    continue
                if float(p.cantidad or 0) <= 0:
                    continue
                partidas_acero.append({"partida": p, "tipo_elemento": tipo_elem})

    if not partidas_acero:
        return {"status": "sin_acero", "msg": "No se encontraron vigas/columnas con cantidad > 0 en CSI 05"}

    creadas = 0
    actualizadas = 0

    for item in partidas_acero:
        p = item["partida"]
        tipo_elem = item["tipo_elemento"]
        perfil = detectar_perfil(p.descripcion, p.type_mark or "")
        tipo_conexion = "VIGA-COLUMNA" if tipo_elem == "VIGA" else "MOMENTO"
        clave_nueva = "05 12 00.01" if tipo_elem == "VIGA" else "05 12 00.02"
        filete = "5/16" if tipo_elem == "VIGA" else "3/8"

        conn = db.query(MatrizSoldaduraConexion).filter(
            MatrizSoldaduraConexion.partida_id == p.id
        ).first()

        if not conn:
            conn = MatrizSoldaduraConexion(
                id=str(uuid.uuid4()),
                presupuesto_id=pid,
                clave_csi_nuevo=clave_nueva,
                type_mark=p.type_mark or p.clave_csi,
                clave_csi_origen=p.clave_csi,
                partida_id=p.id,
                perfil_w=perfil,
                tipo_elemento=tipo_elem,
                tipo_conexion=tipo_conexion,
                tipo_soldadura="FILETE",
                tamano_filete=filete,
                longitud_perfil_m=float(p.cantidad or 0),
                precio_electrodo=45,
                precio_soldador=80,
                vu_aplicado=0,
                notas=f"Auto: {p.clave_csi}",
            )
            calcular_lrfd(conn)
            db.add(conn)
            creadas += 1
        else:
            conn.longitud_perfil_m = float(p.cantidad or 0)
            conn.perfil_w = perfil
            calcular_lrfd(conn)
            actualizadas += 1

    db.flush()

    # Totales
    todas = db.query(MatrizSoldaduraConexion).filter(
        MatrizSoldaduraConexion.presupuesto_id == pid
    ).all()
    costo_total = sum(float(c.costo_total) for c in todas)
    long_total = sum(float(c.longitud_soldadura_m) for c in todas)
    costo_unitario = round(costo_total / long_total, 4) if long_total > 0 else 0
    sobrecosto = _get_sobrecosto(pid, db)
    precio_unitario = round(costo_unitario * (1 + sobrecosto / 100), 4) if costo_unitario > 0 else 0

    # Crear/actualizar partida unificada en capítulo 05
    if cap_05:
        partida_sol = db.query(Partida).filter(
            Partida.capitulo_id == cap_05.id,
            Partida.clave_csi == "05 12 00.00"
        ).first()
        total_partida = round(long_total * precio_unitario, 4)
        if not partida_sol:
            max_orden = max((p.orden for p in cap_05.partidas), default=0)
            partida_sol = Partida(
                id=str(uuid.uuid4()),
                capitulo_id=cap_05.id,
                clave_csi="05 12 00.00",
                descripcion="Soldaduras Estructurales - Conexiones de Acero",
                unidad="m",
                cantidad=round(long_total, 4),
                costo_mo=0,
                costo_ma=costo_unitario,
                unitario_matriz=0,
                costo_base=costo_unitario,
                precio_unitario=precio_unitario,
                total=total_partida,
                type_mark="SC-SOL",
                orden=max_orden + 1,
            )
            db.add(partida_sol)
        else:
            partida_sol.cantidad = round(long_total, 4)
            partida_sol.costo_mo = 0
            partida_sol.costo_ma = costo_unitario
            partida_sol.unitario_matriz = 0
            partida_sol.costo_base = costo_unitario
            partida_sol.precio_unitario = precio_unitario
            partida_sol.total = total_partida

    db.commit()

    return {
        "status": "ok",
        "conexiones_creadas": creadas,
        "conexiones_actualizadas": actualizadas,
        "total_conexiones": len(todas),
        "longitud_total_m": round(long_total, 4),
        "costo_total": round(costo_total, 4),
        "partida_csi": "05 12 00.00",
    }


@router.get("/reporte/{pid}")
def reporte_soldaduras(pid: str, db: Session = Depends(get_db)):
    """Reporte agrupado por tipo"""

    conexiones = db.query(MatrizSoldaduraConexion).filter(
        MatrizSoldaduraConexion.presupuesto_id == pid
    ).all()

    totales = {
        "total_conexiones": len(conexiones),
        "costo_total": sum(float(c.costo_total) for c in conexiones),
        "peso_electrodo_total_kg": sum(float(c.peso_electrodo_kg) for c in conexiones),
        "horas_hombre_total": sum(float(c.horas_hombre) for c in conexiones),
        "cumplimiento_lrfd": sum(1 for c in conexiones if c.cumple_lrfd),
    }

    por_tipo = {}
    for c in conexiones:
        tipo = c.tipo_conexion
        if tipo not in por_tipo:
            por_tipo[tipo] = {
                "cantidad": 0,
                "costo_total": 0,
                "peso_kg": 0,
                "conexiones": []
            }
        por_tipo[tipo]["cantidad"] += 1
        por_tipo[tipo]["costo_total"] += float(c.costo_total)
        por_tipo[tipo]["peso_kg"] += float(c.peso_electrodo_kg)
        por_tipo[tipo]["conexiones"].append({
            "type_mark": c.type_mark,
            "perfil": c.perfil_w,
            "costo": float(c.costo_total),
        })

    return {
        "presupuesto_id": pid,
        "totales": totales,
        "por_tipo": por_tipo,
    }
