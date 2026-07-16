"""
Motor de cronograma (Gantt) para EstimaStruct  —  modelo CATALOGO V1.2.

La duracion de cada actividad NO se calcula desde la mano de obra de la partida
de la obra, sino desde un TIEMPO DE EJECUCION POR UNIDAD definido una sola vez
por CSI en el catalogo V1.2 (development/Template2_Updated/v1.2/fichas):

    duracion_dias(actividad) = ceil( dias_unidad[CSI] * cantidad_obra )   (min 1)

dias_unidad se deriva de los coeficientes 'jor' (jornadas-hombre por unidad) de
la ficha V1.2, tomando el rol que gobierna con una cuadrilla chica (1 persona por
oficio trabajando en paralelo  ->  dias_unidad = max(coef por rol)).

Actividades que faltan en V1.2 (excavacion, demolicion globales, repello, columnas,
etc.) se completan con TIEMPOS_MANUALES (dias/unidad). Actividades con unidad
incompatible (p.ej. limpieza V1.2 va por 'mes') se fijan en TIEMPOS_FIJOS (dias
fijos por actividad, independientes de la cantidad).

Modulo PURO: no toca BD ni red. Lee el JSON del catalogo V1.2 de disco.
"""
from __future__ import annotations
import os
import json
import math
from datetime import date, timedelta

# ── Parametros ───────────────────────────────────────────────────────────────
DIAS_SEMANA   = 6            # lunes a sabado; domingo no se trabaja
CREW_LUMP     = 3            # cuadrilla para repartir fichas 'global/glb' lump
FECHA_DEFAULT = date(2026, 6, 15)   # lunes

# unidades que SON por-unidad (la duracion escala con la cantidad)
UNID_POR_UNIDAD = {"m2", "m3", "m", "ml", "kg", "ton", "pza", "und", "unidad",
                   "par", "juego", "pie2", "pie3", "lance", "nivel"}
# unidades 'bulto' (el coef es total de la actividad, no por unidad de obra)
UNID_LUMP = {"global", "glb", "gbl", "mes", "conexion"}

# Path al catalogo V1.2
_THIS = os.path.dirname(os.path.abspath(__file__))
CATALOGO_V12_PATH = os.path.normpath(os.path.join(
    _THIS, "..", "development", "Template2_Updated", "v1.2", "fichas", "fichas_v1.2.json"))


# ── Modelo de personal (despiece esp + ay) ───────────────────────────────────
# Cuadrilla chica = 3 especialistas + 3 ayudantes. Default por actividad = 3+3,
# editable. duracion = max(ceil(jh_esp/N_esp), ceil(jh_ay/N_ay), 1).
DEF_ESP = 3
DEF_AY  = 3
HELPER_KW = ("ayudante", "peon", "peón")


def _es_ayudante(desc: str) -> bool:
    d = (desc or "").lower()
    return any(k in d for k in HELPER_KW)


# ── Tiempos manuales (faltan en V1.2): jornadas-hombre por unidad (esp, ay) ────
# esp = especialista (albañil/armador/carpintero/soldador/fontanero/electricista/
# pintor/tablayesero); ay = ayudante/peón. 0 = ese tipo no participa.
MANUAL_SPLIT = {
    "01 54 23":      (0.0200, 0.0200),  # andamios montaje (m2)
    "01 74 41":      (0.0,    0.0400),  # transporte desperdicio (m3) — peones
    "02 21 13.14":   (0.0227, 0.0227),  # niveletas de madera (m2)
    "02 21 13.13":   (0.0250, 0.0250),  # trazado y marcado (m)
    "03 21 11.1":    (0.1330, 0.1330),  # castillo R1 15x15 (m2)
    "03 21 11.2":    (0.2500, 0.2500),  # columna R2 (mL)
    "03 21 11.6":    (0.0400, 0.0),     # refuerzo sillares (armador)
    "03 21 11.7":    (0.0625, 0.0),     # refuerzo 45 ventanas (armador)
    "03 21 11.8":    (0.0833, 0.0),     # refuerzo dintel puertas (armador)
    "03 21 11.9":    (0.0625, 0.0),     # refuerzo 45 puertas (armador)
    "03 21 11.10":   (0.4000, 0.4000),  # zapata Z1 80x80 (m2)
    "03 11 13.1":    (0.1000, 0.1000),  # encofrado perimetral losa (m)
    "03 22 00.1":    (0.0222, 0.0222),  # electromalla losa (m2)
    "03 31 13.2":    (0.1667, 0.1667),  # concreto premezclado (m3)
    "03 31 13.4":    (0.0500, 0.0500),  # fundido losa e=8 (m2)
    "04 05 13":      (0.1000, 0.1000),  # repello 1:4 (m2)
    "04 05 12":      (0.0714, 0.0714),  # pulido supercapa (m2)
    "04 05 14":      (0.1430, 0.1430),  # repello+pulido mochetas (mL)
    "04 26 00.6":    (0.3330, 0.3330),  # bordillo ducha (mL)
    "04 26 00.9":    (0.1667, 0.1667),  # solera S2 (mL)
    "04 26 00.10":   (0.2000, 0.2000),  # viga V-1 (mL)
    "08 51 13.2":    (0.5000, 0.5000),  # ventana corrediza (pza)
    "08 51 13.1":    (0.5000, 0.5000),  # ventana proyectable (pza)
    "08 51 13.6":    (0.2500, 0.2500),  # ventanas proyectables (c/u)
    "08 14 23.20":   (0.5000, 0.5000),  # reinstalacion de puerta
    "08 14 23.19.1": (0.6670, 0.6670),  # puerta termoformada (pza)
    "09 22 13.13.1": (0.0556, 0.0556),  # furring cielo (m2)
    "22 12 19.3":    (7.0000, 7.0000),  # cisterna 4m3 (obra completa)
    "22 41 23.3":    (2.0000, 2.0000),  # tina (pza)
    "26 27 19.3":    (0.1250, 0.0),     # tomacorriente TV (electricista)
    "31 23 16.16.2": (0.0,    0.0400),  # excavacion (maquina + peon)
}

# Tiempo FIJO por actividad (independiente de cantidad). Se modela como carga de
# ayudante calibrada al default (DEF_AY) para que a 3 ayudantes de el valor fijo.
TIEMPOS_FIJOS = {
    "01 74 23": 2,   # limpieza final (V1.2 va por 'mes' con 24 jor -> fijar 2 dias)
}


# ── Construccion del catalogo V1.2 ───────────────────────────────────────────
def cargar_catalogo(path: str | None = None) -> dict:
    """
    Devuelve {csi: {dias_u, unidad, fija, fuente}}.
      dias_u : dias por unidad (per-unidad) o dias fijos (si fija=True)
      fija   : True si el tiempo no escala con la cantidad de la obra
      fuente : 'V12' | 'V12_LUMP'
    Se mezcla luego con TIEMPOS_MANUALES / TIEMPOS_FIJOS en duracion_actividad().
    """
    path = path or CATALOGO_V12_PATH
    with open(path, encoding="utf-8") as fh:
        fichas = json.load(fh)

    cat: dict[str, dict] = {}
    for f in fichas:
        csi = (f.get("csi") or "").strip()
        if not csi:
            continue
        unidad = (f.get("unidad") or "").strip().lower()
        esp_u = ay_u = 0.0          # jornadas-hombre por unidad (especialista / ayudante)
        tiene_mo = False
        for m in f.get("insumos", []):
            cod = str(m.get("codigo") or "")
            if cod.startswith("MO") and m.get("unidad") == "jor":
                tiene_mo = True
                coef = float(m.get("cantidad") or 0)
                if _es_ayudante(m.get("descripcion") or cod):
                    ay_u += coef
                else:
                    esp_u += coef
        if not tiene_mo:
            continue  # ficha sin mano de obra (supply only) -> 1 dia por default
        lump = unidad in UNID_LUMP
        cat[csi] = dict(esp_u=round(esp_u, 6), ay_u=round(ay_u, 6),
                        unidad=unidad, lump=lump,
                        fuente="V12_LUMP" if lump else "V12")
    return cat


# ── Duracion de una actividad de la obra (despiece esp + ay) ─────────────────
def _jornadas(csi: str, cantidad: float, catalogo: dict):
    """Devuelve (jh_esp, jh_ay, fuente): jornadas-hombre de especialista y ayudante.
    Prioridad: TIEMPOS_FIJOS > MANUAL_SPLIT > catalogo V1.2."""
    csi = (csi or "").strip()
    q = float(cantidad or 0)

    if csi in TIEMPOS_FIJOS:   # fijo -> carga de ayudante calibrada a DEF_AY
        return 0.0, float(TIEMPOS_FIJOS[csi]) * DEF_AY, "FIJO"

    if csi in MANUAL_SPLIT:
        esp_u, ay_u = MANUAL_SPLIT[csi]
        return esp_u * q, ay_u * q, "MANUAL"

    e = catalogo.get(csi)
    if e:
        return e["esp_u"] * q, e["ay_u"] * q, e["fuente"]

    return 0.0, 0.0, "SIN_TIEMPO"   # sin mano de obra -> 1 dia


def duracion_actividad(csi: str, cantidad: float, catalogo: dict,
                       n_esp: int = DEF_ESP, n_ay: int = DEF_AY) -> dict:
    """
    duracion = max(ceil(jh_esp / N_esp), ceil(jh_ay / N_ay), 1).
    N_esp especialistas + N_ay ayudantes se reparten la carga de cada tipo.
    Devuelve dict(dias, jh_esp, jh_ay, n_esp, n_ay, fuente).
    """
    ne = max(1, int(n_esp or 1))
    na = max(1, int(n_ay or 1))
    jh_esp, jh_ay, fuente = _jornadas(csi, cantidad, catalogo)
    d_esp = math.ceil(jh_esp / ne) if jh_esp > 0 else 0
    d_ay = math.ceil(jh_ay / na) if jh_ay > 0 else 0
    dias = max(1, d_esp, d_ay)
    return dict(dias=dias, jh_esp=round(jh_esp, 3), jh_ay=round(jh_ay, 3),
                n_esp=ne, n_ay=na, fuente=fuente)


# ── Fase constructiva por division CSI (titulo, offset dia-laboral) ───────────
CAP_FASE = {
    "31": ("1. Sitio y movimiento de tierra",  0),
    "02": ("2. Trazo y demolición",            3),
    "01": ("3. Preliminares",                  3),
    "03": ("4. Cimentación y estructura",      8),
    "22": ("5. Plomería (rough-in)",          22),
    "26": ("5. Eléctrico (rough-in)",         29),
    "04": ("6. Mampostería, repello y pulido", 29),
    "05": ("7. Cubierta",                     50),
    "07": ("7. Cubierta",                     50),
    "08": ("8. Puertas y ventanas",           80),
    "09": ("9. Acabados",                     80),
}
CSI_FASE = {
    "01 54 23": ("3. Preliminares",            8),
    "01 74 23": ("10. Limpieza final",       120),
    "01 74 19": ("2. Trazo y demolición",      3),
    "01 74 41": ("2. Trazo y demolición",      3),
}


def _fase_de(csi: str, cap: str):
    if csi in CSI_FASE:
        return CSI_FASE[csi]
    return CAP_FASE.get(cap, ("9. Acabados", 80))


# ── Fechas (salta domingos) ──────────────────────────────────────────────────
def _suma_dias_laborales(inicio: date, dias_lab: int) -> date:
    d = inicio
    restantes = max(0, int(dias_lab))
    while restantes > 0:
        d += timedelta(days=1)
        if d.weekday() != 6:
            restantes -= 1
    return d


# ── Secuenciacion ────────────────────────────────────────────────────────────
def construir_cronograma(partidas: list[dict], catalogo: dict | None = None,
                         fecha_arranque: date | None = None) -> list[dict]:
    """
    partidas: dict(clave_csi, descripcion, unidad, cantidad, capitulo_clave, partida_id).
    Devuelve filas con duracion, fase, fecha_inicio, orden, fuente.
    """
    if catalogo is None:
        catalogo = cargar_catalogo()
    if fecha_arranque is None:
        fecha_arranque = FECHA_DEFAULT

    filas = []
    for p in partidas:
        csi = (p.get("clave_csi") or "").strip()
        cap = (p.get("capitulo_clave") or csi[:2]).strip()
        cant = p.get("cantidad", 0)
        ne = max(1, int(p.get("n_esp") or DEF_ESP))
        na = max(1, int(p.get("n_ay") or DEF_AY))
        dur = duracion_actividad(csi, cant, catalogo, ne, na)
        fase, offset = _fase_de(csi, cap)
        filas.append({**p, **dur, "fase": fase, "_offset": offset})

    filas.sort(key=lambda f: (f["_offset"], f.get("capitulo_clave", ""), f["clave_csi"]))

    cursor_lab: dict[str, int] = {}
    for i, f in enumerate(filas):
        fase = f["fase"]
        inicio_lab = cursor_lab.get(fase, f["_offset"])
        dur = max(1, int(f["dias"]))
        f["orden"] = i
        f["inicio_lab"] = inicio_lab          # offset en DÍAS ACTIVOS (0-based) desde el arranque
        f["fecha_inicio"] = _suma_dias_laborales(fecha_arranque, inicio_lab).isoformat()
        f["duracion_dias"] = dur
        f["avance_pct"] = 0
        cursor_lab[fase] = inicio_lab + dur
        f.pop("_offset", None)
    return filas


# ── Runner offline contra el SQLite local ────────────────────────────────────
if __name__ == "__main__":
    import sqlite3, sys
    from config import CONFIG   # FASE 0: BD movida fuera de OneDrive
    pid = sys.argv[1] if len(sys.argv) > 1 else "92de239d-e672-4f21-8aba-c38ed894cb9c"
    cat = cargar_catalogo()
    print(f"catalogo V1.2: {len(cat)} CSIs  (+{len(MANUAL_SPLIT)} manuales, "
          f"{len(TIEMPOS_FIJOS)} fijos)  default {DEF_ESP}esp+{DEF_AY}ay")
    c = sqlite3.connect(CONFIG.DB_PATH); c.row_factory = sqlite3.Row
    rows = c.execute("""SELECT cap.clave cap, p.id pid, p.clave_csi, p.descripcion,
        p.unidad, p.cantidad FROM partida p JOIN capitulo cap ON p.capitulo_id = cap.id
        WHERE cap.presupuesto_id = ? ORDER BY cap.orden, p.orden""", (pid,)).fetchall()
    partidas = [dict(clave_csi=r["clave_csi"], descripcion=r["descripcion"], unidad=r["unidad"],
                     cantidad=r["cantidad"], capitulo_clave=r["cap"], partida_id=r["pid"])
                for r in rows]
    crono = construir_cronograma(partidas, cat)
    sin = [f for f in crono if f["fuente"] == "SIN_TIEMPO"]
    fin = max(f["fecha_inicio"] for f in crono)
    print(f"partidas={len(crono)}  fin={fin}  sin_tiempo={len(sin)}  "
          f"suma_dias={sum(f['duracion_dias'] for f in crono)}")
    for f in crono:
        print(f"{f['orden']:>2} {f['fecha_inicio']} {f['duracion_dias']:>2}d "
              f"{f['n_esp']}e+{f['n_ay']}a jh[{f['jh_esp']:>5}/{f['jh_ay']:>5}] "
              f"{f['fuente']:<9} {f['clave_csi']:<14} {(f['descripcion'] or '')[:34]}")
    json.dump(crono, open(os.path.join(_THIS, "_camilo_cronograma.json"), "w",
              encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
