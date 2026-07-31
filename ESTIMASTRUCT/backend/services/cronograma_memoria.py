# -*- coding: utf-8 -*-
"""
Cronograma / duración de actividad — memoria narrada (2026-07-31).

Módulo ciego C-04 de `docs/auditoria_formulas_mapa_estructura.md` — riesgo MEDIO:
no mueve plata directamente, pero define el Gantt que se entrega al cliente y al
banco, y el plazo contractual sale de ahí.

ADR-003 estricto: aquí NO hay motor nuevo. `backend/cronograma.py` ya corre en
producción y es la fuente única — este módulo importa `duracion_actividad`,
`_jornadas`, `_fase_de` y `cargar_catalogo` y sólo NARRA lo que devuelven. Ni una
línea de aritmética propia.

LO QUE ESTABA CIEGO
-------------------
1. **Cascada de prioridad de fuente, 4 niveles, invisible.**
       TIEMPOS_FIJOS  >  MANUAL_SPLIT  >  catálogo V1.2  >  SIN_TIEMPO (⇒ 1 día)
   El campo `fuente` ya viajaba en la respuesta del endpoint, pero nadie explica
   qué significa "MANUAL" ni por qué esa actividad no salió del catálogo. Una
   partida con fuente SIN_TIEMPO recibe **1 día** por defecto — puede ser una
   actividad de tres semanas y el Gantt la dibuja como un día.
2. **Offsets de fase mágicos.** `CAP_FASE` / `CSI_FASE` asignan a cada división
   CSI un offset en días laborales (0, 3, 8, 22, 29, 50, 80, 120) sin ninguna
   justificación escrita. Ese número es lo que decide en qué punto del Gantt
   arranca un capítulo entero.
3. **Calendario de 6 días.** `DIAS_SEMANA = 6`: los "días" del cronograma son
   días ACTIVOS, no calendario. Un plazo de 120 días activos son ~140 días
   calendario. El PDF no lo aclara.
4. **Cuadrilla default 3+3.** `DEF_ESP`/`DEF_AY` fijan la duración por división
   entera de jornadas-hombre; cambiar el personal cambia el plazo y hoy nadie ve
   cuánta holgura hay en ese redondeo (`ceil`).

Contrato de salida idéntico a los otros motores narrados:
    {meta, pasos[], constantes[], resultado{}}
"""
import math

from backend.calculo_estructural import _fmt, _ascii_to_latex
from backend.cronograma import (
    duracion_actividad, _jornadas, _fase_de, cargar_catalogo,
    DIAS_SEMANA, DEF_ESP, DEF_AY, CREW_LUMP,
    TIEMPOS_FIJOS, MANUAL_SPLIT, CAP_FASE, CSI_FASE,
)

# Explicación de cada nivel de la cascada de prioridad. Es documentación, no
# cálculo: el motor decide, esto sólo traduce el código `fuente` a español.
FUENTE_DESC = {
    "FIJO": ("TIEMPOS_FIJOS — prioridad 1 (máxima)",
             "Actividad con duración FIJA por decisión explícita, independiente de la cantidad "
             "de obra. Se usa cuando la ficha V1.2 tiene una unidad incompatible (p.ej. limpieza "
             "final viene por 'mes' con 24 jornadas). Se modela como carga de ayudante calibrada "
             "a la cuadrilla default para que a 3 ayudantes dé exactamente el valor fijo."),
    "MANUAL": ("MANUAL_SPLIT — prioridad 2",
               "La actividad NO existe en el catálogo V1.2 (excavación, demolición, repello, "
               "columnas, ventanas…). El rendimiento (jornadas-hombre por unidad, separado en "
               "especialista y ayudante) está tecleado a mano en cronograma.MANUAL_SPLIT. Es un "
               "juicio de obra, no un dato del catálogo."),
    "V12": ("Catálogo V1.2 — prioridad 3",
            "Rendimiento derivado de los insumos 'MO…jor' de la ficha V1.2 del catálogo. Es la "
            "vía normal y la única trazable a la base de datos de fichas."),
    "V12_LUMP": ("Catálogo V1.2 (unidad global) — prioridad 3",
                 "Ficha del catálogo cuya unidad es global/glb/mes/conexión: el coeficiente es el "
                 "TOTAL de la actividad, no un rendimiento por unidad de obra. La duración NO "
                 "escala con la cantidad."),
    "SIN_TIEMPO": ("SIN_TIEMPO — prioridad 4 (fallback)",
                   "⚠ La actividad no está en NINGUNA de las tres fuentes anteriores. El motor le "
                   "asigna el mínimo de 1 día. Si la actividad realmente lleva semanas, el Gantt "
                   "la subestima por completo y el plazo entregado es falso."),
}


def _paso(seccion, simbolo, etiqueta, valor, unidad, formula, sustitucion,
          referencia, descripcion, tipo="intermedio", latex=None) -> dict:
    return {
        "seccion": seccion, "simbolo": simbolo, "etiqueta": etiqueta,
        "valor": valor, "unidad": unidad, "formula": formula,
        "sustitucion": sustitucion, "referencia": referencia,
        "descripcion": descripcion, "tipo": tipo,
        "latex": latex,
        "latex_sub": (_ascii_to_latex(sustitucion) if tipo != "input" else None),
    }


LATEX_BY_FORMULA_CRONO = {
    "jh_esp = esp_u × cantidad":
        r"JH_{esp} = r_{esp}\cdot Q",
    "jh_ay = ay_u × cantidad":
        r"JH_{ay} = r_{ay}\cdot Q",
    "d_esp = ceil(jh_esp / N_esp)":
        r"d_{esp} = \left\lceil \dfrac{JH_{esp}}{N_{esp}} \right\rceil",
    "d_ay = ceil(jh_ay / N_ay)":
        r"d_{ay} = \left\lceil \dfrac{JH_{ay}}{N_{ay}} \right\rceil",
    "duracion = max(d_esp, d_ay, 1)":
        r"D = \max(d_{esp},\, d_{ay},\, 1)",
    "inicio_lab = offset de fase (o fin de la actividad previa de la misma fase)":
        r"t_0 = \mathrm{offset}(\text{fase})",
    "dias_calendario ≈ dias_activos × 7 / 6":
        r"D_{cal} \approx D\cdot \dfrac{7}{6}",
    "holgura = N × duracion − jh":
        r"H = N\cdot D - JH",
}

_CATALOGO_CACHE = None


def _catalogo():
    """Catálogo V1.2 cargado una vez por proceso (lectura de disco, sin BD)."""
    global _CATALOGO_CACHE
    if _CATALOGO_CACHE is None:
        try:
            _CATALOGO_CACHE = cargar_catalogo()
        except (OSError, ValueError):
            _CATALOGO_CACHE = {}
    return _CATALOGO_CACHE


# ─────────────────────────────────────────────────────────────────────────────
# MEMORIA NARRADA — el motor es backend/cronograma.py, aquí sólo se lee
# ─────────────────────────────────────────────────────────────────────────────
def memoria_cronograma(csi: str, cantidad: float, unidad: str = "",
                       n_esp: int = DEF_ESP, n_ay: int = DEF_AY,
                       capitulo_clave: str = "", descripcion: str = "",
                       meta_extra: dict | None = None) -> dict:
    """Narra la duración y la fase de UNA actividad. `csi` es la clave CSI de la
    partida. Devuelve {meta, pasos, constantes, resultado}."""
    cat = _catalogo()
    csi = (csi or "").strip()
    cap = (capitulo_clave or csi[:2]).strip()
    q = float(cantidad or 0)

    # Motor real — no se recalcula nada aquí.
    dur = duracion_actividad(csi, q, cat, n_esp, n_ay)
    jh_esp, jh_ay, fuente = _jornadas(csi, q, cat)
    fase, offset = _fase_de(csi, cap)
    entrada_cat = cat.get(csi)

    fuente_titulo, fuente_desc = FUENTE_DESC.get(
        fuente, (fuente, "Fuente no reconocida por la auditoría."))

    ne, na = dur["n_esp"], dur["n_ay"]
    d_esp = math.ceil(jh_esp / ne) if jh_esp > 0 else 0
    d_ay = math.ceil(jh_ay / na) if jh_ay > 0 else 0
    dias = dur["dias"]

    # Rendimientos unitarios efectivos (lo que el motor usó, leído de la fuente
    # que ganó la cascada — no recalculado).
    if fuente == "MANUAL":
        esp_u, ay_u = MANUAL_SPLIT[csi]
    elif fuente in ("V12", "V12_LUMP") and entrada_cat:
        esp_u, ay_u = entrada_cat["esp_u"], entrada_cat["ay_u"]
    else:
        esp_u = ay_u = None

    holgura_esp = ne * dias - jh_esp
    holgura_ay = na * dias - jh_ay
    dias_cal = math.ceil(dias * 7.0 / DIAS_SEMANA)

    advertencias = []
    if fuente == "SIN_TIEMPO":
        advertencias.append(
            f"CSI '{csi}' no está en TIEMPOS_FIJOS, ni en MANUAL_SPLIT, ni en el catálogo V1.2. "
            "El motor le asignó el MÍNIMO de 1 día. Si esta actividad realmente lleva más, el "
            "plazo del Gantt está subestimado y nadie lo ve: la fila se dibuja igual que "
            "cualquier otra.")
    if fuente == "V12_LUMP":
        advertencias.append(
            "Ficha de unidad global/lump: el rendimiento es el TOTAL de la actividad, así que "
            "la duración NO escala con la cantidad de obra. Duplicar la cantidad no alarga el "
            "Gantt.")
    if csi not in CSI_FASE and cap not in CAP_FASE:
        advertencias.append(
            f"La división CSI '{cap}' no está en CAP_FASE: la actividad cayó en el default "
            "'9. Acabados' con offset 80 días. Ese destino es un fallback, no una decisión de "
            "planificación.")
    if q <= 0 and fuente not in ("FIJO",):
        advertencias.append(
            "Cantidad = 0: las jornadas-hombre dan 0 y la duración cae al mínimo de 1 día.")

    P = []

    # ── ENTRADAS ─────────────────────────────────────────────────────────────
    P.append(_paso("Actividad", "CSI", "Clave CSI de la partida", csi or "—", "",
        "dato de proyecto", f"CSI = {csi or '—'}", "MasterFormat CSI",
        (descripcion or "Actividad del presupuesto. La clave CSI es la que gobierna TODO: "
         "el rendimiento, la fase y el offset de arranque."), "input"))
    P.append(_paso("Actividad", "Q", "Cantidad de obra", q, unidad or "und",
        "dato de proyecto", f"Q = {_fmt(q)}", "partida.cantidad",
        "Cantidad final de la partida (ya con ceil y factores aplicados — ver la memoria de "
        "Factores de cantidad).", "input"))

    # ── CASCADA DE FUENTE ────────────────────────────────────────────────────
    P.append(_paso("Fuente del rendimiento", "fuente", "Nivel que ganó la cascada",
        fuente, "", "TIEMPOS_FIJOS > MANUAL_SPLIT > catálogo V1.2 > SIN_TIEMPO",
        f"fuente('{csi}') = {fuente}  →  {fuente_titulo}",
        "cronograma.py::_jornadas",
        fuente_desc, "check" if fuente == "SIN_TIEMPO" else "resultado"))
    if esp_u is not None:
        P.append(_paso("Fuente del rendimiento", "r_esp", "Rendimiento de especialista",
            round(esp_u, 6), f"jornada-hombre / {unidad or 'und'}",
            "dato del catálogo / MANUAL_SPLIT",
            f"r_esp = {_fmt(esp_u, 6)}",
            "fichas_v1.2.json (insumos MO·jor)" if fuente.startswith("V12") else "cronograma.MANUAL_SPLIT",
            "Jornadas-hombre de albañil/armador/carpintero/soldador por unidad de obra.", "input"))
        P.append(_paso("Fuente del rendimiento", "r_ay", "Rendimiento de ayudante",
            round(ay_u, 6), f"jornada-hombre / {unidad or 'und'}",
            "dato del catálogo / MANUAL_SPLIT",
            f"r_ay = {_fmt(ay_u, 6)}",
            "fichas_v1.2.json (insumos MO·jor)" if fuente.startswith("V12") else "cronograma.MANUAL_SPLIT",
            "Ídem para ayudante/peón. 0 = ese oficio no participa.", "input"))
    elif fuente == "FIJO":
        P.append(_paso("Fuente del rendimiento", "D_fijo", "Duración fija declarada",
            TIEMPOS_FIJOS[csi], "días", "dato explícito",
            f"TIEMPOS_FIJOS['{csi}'] = {TIEMPOS_FIJOS[csi]}",
            "cronograma.TIEMPOS_FIJOS",
            "Días fijos por decisión, independientes de la cantidad. Internamente se convierten "
            f"a carga de ayudante multiplicando por la cuadrilla default ({DEF_AY}) para que el "
            "motor de duración devuelva exactamente este número.", "input"))

    # ── JORNADAS-HOMBRE ──────────────────────────────────────────────────────
    P.append(_paso("Jornadas-hombre", "JH_esp", "Carga total de especialista", round(jh_esp, 3),
        "jornada-hombre", "jh_esp = esp_u × cantidad",
        (f"{_fmt(esp_u, 6)} × {_fmt(q)} = {_fmt(jh_esp, 3)}" if esp_u is not None
         else f"JH_esp = {_fmt(jh_esp, 3)}"),
        "cronograma.py::_jornadas",
        "Trabajo total de especialista que exige la actividad, antes de repartirlo entre "
        "personas.", "intermedio"))
    P.append(_paso("Jornadas-hombre", "JH_ay", "Carga total de ayudante", round(jh_ay, 3),
        "jornada-hombre", "jh_ay = ay_u × cantidad",
        (f"{_fmt(ay_u, 6)} × {_fmt(q)} = {_fmt(jh_ay, 3)}" if ay_u is not None
         else f"JH_ay = {_fmt(jh_ay, 3)}"),
        "cronograma.py::_jornadas",
        "Ídem para ayudantes/peones.", "intermedio"))

    # ── DURACIÓN ─────────────────────────────────────────────────────────────
    P.append(_paso("Duración", "N_esp", "Especialistas asignados", ne, "personas",
        "dato de proyecto", f"N_esp = {ne}", f"default {DEF_ESP} (cronograma.DEF_ESP)",
        "Cuadrilla chica. Editable por actividad desde POST /cronograma/personal.", "input"))
    P.append(_paso("Duración", "N_ay", "Ayudantes asignados", na, "personas",
        "dato de proyecto", f"N_ay = {na}", f"default {DEF_AY} (cronograma.DEF_AY)",
        "Ídem ayudantes.", "input"))
    P.append(_paso("Duración", "d_esp", "Días que impone el especialista", d_esp, "días activos",
        "d_esp = ceil(jh_esp / N_esp)",
        f"ceil({_fmt(jh_esp, 3)} / {ne}) = {d_esp}",
        "cronograma.py:171",
        "Redondeo hacia ARRIBA: media jornada sobrante cuesta un día entero de calendario.",
        "intermedio"))
    P.append(_paso("Duración", "d_ay", "Días que impone el ayudante", d_ay, "días activos",
        "d_ay = ceil(jh_ay / N_ay)",
        f"ceil({_fmt(jh_ay, 3)} / {na}) = {d_ay}",
        "cronograma.py:172", "Ídem para la cuadrilla de ayudantes.", "intermedio"))
    P.append(_paso("Duración", "D", "Duración de la actividad", dias, "días activos",
        "duracion = max(d_esp, d_ay, 1)",
        f"max({d_esp}, {d_ay}, 1) = {dias}",
        "cronograma.py:173",
        "Gobierna el oficio más cargado. El piso de 1 día es lo que convierte una actividad "
        "sin rendimiento conocido (SIN_TIEMPO) en una barra de un día.", "resultado"))
    P.append(_paso("Duración", "H_esp", "Holgura de especialista", round(holgura_esp, 3),
        "jornada-hombre", "holgura = N × duracion − jh",
        f"{ne} × {dias} − {_fmt(jh_esp, 3)} = {_fmt(holgura_esp, 3)}",
        "derivado",
        "Capacidad sobrante que deja el redondeo. Holgura alta = la duración está dominada por "
        "el otro oficio o por el mínimo de 1 día, no por este.", "intermedio"))
    P.append(_paso("Duración", "H_ay", "Holgura de ayudante", round(holgura_ay, 3),
        "jornada-hombre", "holgura = N × duracion − jh",
        f"{na} × {dias} − {_fmt(jh_ay, 3)} = {_fmt(holgura_ay, 3)}",
        "derivado", "Ídem para ayudantes.", "intermedio"))

    # ── SECUENCIACIÓN ────────────────────────────────────────────────────────
    P.append(_paso("Secuenciación", "fase", "Fase constructiva asignada", fase, "",
        "CSI_FASE[csi] si existe, si no CAP_FASE[división], si no default",
        f"fase('{csi}', cap='{cap}') = {fase}",
        "cronograma.CAP_FASE / CSI_FASE",
        "La fase agrupa actividades que corren en cadena. Dentro de una misma fase, cada "
        "actividad arranca donde terminó la anterior (cursor por fase); fases distintas corren "
        "en paralelo.", "resultado"))
    P.append(_paso("Secuenciación", "t₀", "Offset de arranque de la fase", offset, "días activos",
        "inicio_lab = offset de fase (o fin de la actividad previa de la misma fase)",
        f"offset('{fase}') = {offset}",
        "cronograma.CAP_FASE / CSI_FASE",
        "⚠ Número MÁGICO: los offsets (0, 3, 8, 22, 29, 50, 80, 120) están codificados a mano "
        "por división CSI sin justificación escrita en el repo. Definen en qué día del proyecto "
        "puede arrancar un capítulo entero — es decir, el plazo total del Gantt sale en buena "
        "medida de estas constantes, no del cálculo de jornadas.", "check"))
    P.append(_paso("Secuenciación", "D_cal", "Equivalente en días calendario", dias_cal, "días",
        "dias_calendario ≈ dias_activos × 7 / 6",
        f"ceil({dias} × 7 / {DIAS_SEMANA}) = {dias_cal}",
        f"cronograma.DIAS_SEMANA = {DIAS_SEMANA}",
        "Todo el cronograma cuenta días ACTIVOS (lunes a sábado; domingo no se trabaja). Un "
        "plazo contractual en días calendario es ~17% mayor. El PDF del banco no aclara cuál "
        "de los dos está mostrando.", "intermedio"))

    P.append(_paso("Verificación", "ok_fuente", "Rendimiento con fuente trazable",
        fuente != "SIN_TIEMPO", "",
        "fuente ≠ SIN_TIEMPO",
        f"fuente = {fuente}",
        "auditoría de fórmulas",
        "Falla cuando la duración es el fallback de 1 día y no un cálculo. Es el hallazgo más "
        "importante del cronograma: una obra con muchas partidas SIN_TIEMPO tiene un Gantt "
        "ficticio.", "check"))

    for p in P:
        if p["tipo"] != "input" and p["latex"] is None:
            p["latex"] = LATEX_BY_FORMULA_CRONO.get(p["formula"])

    constantes = [
        {"simbolo": "días/sem", "latex": r"\text{días/sem} = 6", "valor": DIAS_SEMANA, "unidad": "días",
         "desc": "Calendario laboral: lunes a sábado, domingo no se trabaja. Todos los 'días' del cronograma son días activos."},
        {"simbolo": "N_esp,def", "latex": r"N_{esp,def} = 3", "valor": DEF_ESP, "unidad": "personas",
         "desc": "Cuadrilla chica de especialistas por default."},
        {"simbolo": "N_ay,def", "latex": r"N_{ay,def} = 3", "valor": DEF_AY, "unidad": "personas",
         "desc": "Cuadrilla chica de ayudantes por default."},
        {"simbolo": "crew_lump", "latex": r"crew_{lump} = 3", "valor": CREW_LUMP, "unidad": "personas",
         "desc": "Cuadrilla usada para repartir fichas de unidad global/lump."},
        {"simbolo": "D_min", "latex": r"D_{min} = 1", "valor": 1, "unidad": "día activo",
         "desc": "Piso de duración. Es lo que reciben todas las actividades sin rendimiento conocido."},
    ]

    meta = {
        "dominio": "cronograma",
        "norma": "— (modelo de productividad interno, no normativo)",
        "riesgo": "MEDIO — define el Gantt y el plazo entregados al cliente y al banco",
        "cumple_normativa": fuente != "SIN_TIEMPO" and not advertencias,
        "advertencias": advertencias,
        "fuente_rendimiento": fuente,
        "fuente_titulo": fuente_titulo,
        "catalogo_csis": len(cat),
        "n_manual_split": len(MANUAL_SPLIT),
        "n_tiempos_fijos": len(TIEMPOS_FIJOS),
        "nota_norma": ("El cronograma no responde a norma: es un modelo de productividad "
                       "(jornadas-hombre por unidad) calibrado con el catálogo V1.2 y "
                       "completado a mano. Su punto débil no es la fórmula — es de dónde "
                       "sale el rendimiento y qué pasa cuando no sale de ningún lado."),
    }
    if meta_extra:
        meta.update(meta_extra)
    return {"meta": meta, "pasos": P, "constantes": constantes,
            "resultado": {**dur, "fase": fase, "offset": offset, "dias_calendario": dias_cal,
                          "holgura_esp": round(holgura_esp, 3), "holgura_ay": round(holgura_ay, 3),
                          "advertencias": advertencias}}
