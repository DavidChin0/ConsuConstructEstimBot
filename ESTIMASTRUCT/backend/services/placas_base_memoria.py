# -*- coding: utf-8 -*-
"""
Auditoría de Fórmulas — Placas Base §J8 (envolvente ETABS por pedestal)
========================================================================
Último módulo ciego del mapa (docs/auditoria_formulas_mapa_estructura.md, C-08),
catalogado riesgo BAJO precisamente porque el motor de conexión YA tiene
`memoria_conexion` (backend/calculo_conexion_acero.py) y el tipo PLACA_BASE
YA está narrado ahí (sección "Placa base §J8": B×N, φPp aplastamiento del
concreto, presión de contacto, voladizo crítico, espesor requerido).

Este archivo NO reimplementa esa narración. La única pieza propia es la
sección "Envolvente ETABS", que expone lo que hoy `placas_base_etabs` hace en
silencio: corre §J8 con CADA combinación de carga del joint y retiene la de
mayor DC, sin mostrar cuántos combos se descartaron ni cuál ganó. Eso es
exactamente `_paso` #7 del mapa: "el usuario ve un solo número y no sabe qué
combo lo produjo ni cuántos se descartaron".

ADR-003 (no negociable): no se reimplementa aritmética paralela. Se llama
`calcular_conexion` por cada combo con LA MISMA lógica de selección (mayor
DC) que `backend/routers/acero_diseno.py::placas_base_etabs`, y se narra el
combo gobernante con `memoria_conexion` — el motor real, no una copia.
"""
import math

from backend.calculo_estructural import _fmt
from backend.calculo_conexion_acero import calcular_conexion, memoria_conexion
from backend.seccion_ficha import factores_unidad


def _combo_r(r: dict) -> str:
    return str(r.get("combo") or r.get("outputcase") or "").strip()


def memoria_placa_base_envolvente(pedestal_spec: dict, reacciones: list,
                                  unidad: str = "kgf", meta_extra: dict | None = None) -> dict:
    """Narra §J8 para UN pedestal a partir de la envolvente de sus reacciones.

    pedestal_spec: {pedestal, joint, perfil_columna, acero, fc_kg_cm2, lado_cm,
                    A2_cm2, t_placa_cm, B_placa_cm, N_placa_cm} — mismo shape
                   que `PlacaBaseSpec` de `routers/acero_diseno.py`.
    reacciones: lista YA FILTRADA al joint del pedestal, mismo formato que
                produce `seccion_ficha.parse_reacciones_texto`:
                [{joint, combo, FX, FY, FZ, ...}, ...]

    Devuelve {meta, pasos, constantes, resultado} = memoria_conexion() del
    combo gobernante, con la sección "Envolvente ETABS" insertada al frente
    y `meta.envolvente` con el detalle de TODOS los combos corridos.
    Read-only / stateless (ADR-003): no toca BD, no persiste nada.
    """
    if not pedestal_spec.get("perfil_columna"):
        raise ValueError(
            f"Pedestal {pedestal_spec.get('pedestal', '?')} sin perfil de columna: "
            "§J8 (memoria_conexion) requiere perfil_columna para derivar B×N y d/bf.")
    if not reacciones:
        raise ValueError(
            f"Sin reacciones para el joint '{pedestal_spec.get('joint', '')}' del "
            f"pedestal {pedestal_spec.get('pedestal', '?')}.")

    ff, _fm = factores_unidad(unidad)

    lado = float(pedestal_spec.get("lado_cm", 0) or 0)
    A2 = float(pedestal_spec.get("A2_cm2", 0) or 0) or (lado * lado if lado > 0 else 0.0)
    elem = {
        "tipo_conexion":   "PLACA_BASE",
        "perfil_viga":     "",
        "perfil_columna":  pedestal_spec["perfil_columna"],
        "acero":           pedestal_spec.get("acero", "A992"),
        "t_placa_cm":      float(pedestal_spec.get("t_placa_cm", 1.9) or 1.9),
        "fc_kg_cm2":       float(pedestal_spec.get("fc_kg_cm2", 210.0) or 210.0),
        "B_placa_cm":      float(pedestal_spec.get("B_placa_cm", 0) or 0),
        "N_placa_cm":      float(pedestal_spec.get("N_placa_cm", 0) or 0),
        "A2_cm2":          A2,
    }

    # ── Igual que producción: corre §J8 por CADA combo, retiene el de mayor DC ──
    corridos = []
    mejor = None
    mejor_caso = None
    for r in reacciones:
        pu = abs(float(r.get("FZ") or 0)) * ff
        vu = math.hypot(float(r.get("FX") or 0), float(r.get("FY") or 0)) * ff
        caso = {"pu_t": pu, "vu_t": vu, "nu_t": 0.0, "mu_tm": 0.0}
        res = calcular_conexion(elem, caso)
        dc = res.get("dc_ratio")
        corridos.append({
            "combo": _combo_r(r), "pu_t": round(pu, 3), "vu_t": round(vu, 3),
            "dc": dc, "cumple": bool(res.get("cumple")),
        })
        if dc is not None and (mejor is None or dc > mejor["dc"]):
            mejor = corridos[-1]
            mejor_caso = caso

    if mejor is None:
        raise ValueError(
            "Ningun combo produjo un DC calculable (faltan datos de geometria de la placa/pedestal).")

    # ── El motor real narra el combo gobernante — no se reimplementa nada ──────
    memoria = memoria_conexion(elem, mejor_caso)

    n_desc = len(corridos) - 1
    detalle = "; ".join(
        f"{c['combo'] or '?'}→DC={_fmt(c['dc']) if c['dc'] is not None else '—'}"
        for c in corridos)
    envolvente_paso = {
        "seccion": "Envolvente ETABS",
        "simbolo": "combo_{gob}",
        "etiqueta": f"Combo gobernante de {len(corridos)} corrido(s)",
        "valor": mejor["combo"] or "(sin nombre)",
        "unidad": "",
        "formula": "gobernante = argmax(DC) sobre TODOS los combos del joint",
        "sustitucion": (f"{detalle}  ⇒ gana {mejor['combo'] or '?'} "
                         f"(DC={_fmt(mejor['dc'])}), {n_desc} combo(s) descartado(s)"),
        "referencia": "AISC §J8 — envolvente por pedestal "
                       "(routers/acero_diseno.py::placas_base_etabs)",
        "descripcion": ("Se corre §J8 con Pu=|FZ|, Vu=hypot(FX,FY) para CADA combinacion de "
                         "carga del joint y se retiene la de mayor DC. En produccion los combos "
                         "descartados no aparecen en el resultado; aqui se listan para poder "
                         "auditar cual goberno y cuantos se descartaron."),
        "tipo": "check",
        "latex": None,
        "latex_sub": None,
    }
    memoria["pasos"].insert(0, envolvente_paso)
    memoria["meta"]["envolvente"] = {
        "n_combos": len(corridos), "n_descartados": n_desc,
        "combo_gobernante": mejor["combo"], "combos": corridos,
        "pedestal": pedestal_spec.get("pedestal", ""),
        "joint": pedestal_spec.get("joint", ""),
    }
    # Alias para el banner generico del frontend (mismo contrato que
    # mamposteria/banco/cantidad/cronograma): "sin banderas" = pasa §J8.
    memoria["meta"]["cumple_normativa"] = memoria["meta"].get("cumple", True)
    if n_desc > 0:
        memoria["meta"].setdefault("advertencias", []).append(
            f"{n_desc} combo(s) corrido(s) y descartado(s) por la envolvente "
            f"(gobierna {mejor['combo'] or '?'}) — ver seccion 'Envolvente ETABS'.")
    if meta_extra:
        memoria["meta"].update(meta_extra)
    return memoria
