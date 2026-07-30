"""
Memoria narrada de `routers/calculos.py` — indirectos y totales de presupuesto.

Auditoría de Fórmulas (2026-07-27). Este módulo es READ-ONLY: nunca llama
`_recalcular_todo` (que escribe `ins.total`/`partida.costo_*` in-place y hace
`db.commit()`), nunca invoca `recalcular_partida`. Recalcula EN MEMORIA LOCAL,
con las mismas funciones puras de `services/pricing.py`, exactamente lo que
`POST /presupuestos/{pid}/calcular` calcularía — sin tocar ningún objeto ORM ni
la base de datos.

[RESUELTO 2026-07-30, goal-19654] Hallazgo documentado en
docs/auditoria_formulas_mapa_estructura.md §C-02 (verificado contra el código
2026-07-27): `/calcular` y `/reporte` llamaban "costo_directo" a dos cosas
DISTINTAS — /reporte sumaba `partida.total` (YA CON sobrecosto, porque
total = cantidad·PU) y luego multiplicaba OTRA VEZ por `factor`, aplicando el
sobrecosto dos veces. Confirmado por Opus 2026-07-30 (diagnóstico financiero,
protocolo bugs con riesgo real) y corregido en routers/calculos.py:78-92:
`reporte()` ahora calcula `costo_directo` con `calc_base` (misma definición
que /calcular) y expone `total_con_indirectos` = Σ partida.total directo
(que ya es el total real persistido), sin re-aplicar `factor`. Este módulo ya
NO corrige nada (sigue siendo read-only) — solo narra ambas vistas, que ahora
coinciden.
"""
from decimal import Decimal

from backend.calculo_estructural import _fmt, _ascii_to_latex
from backend.services.pricing import calc_base, rebucket_insumos, quantize_money
from backend.routers.calculos import _factor_indirectos


def _fmt_money(v) -> str:
    try:
        if v is None:
            return "—"
        return f"{float(v):,.4f}"
    except (TypeError, ValueError):
        return str(v)


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


LATEX_BY_FORMULA_CALCULOS = {
    "costo_directo(calcular) = Σ (cantidad · costo_base)":
        r"\text{costo\_directo}_{\text{calcular}} = \sum(\text{cantidad}\cdot\text{costo\_base})",
    "costo_directo(reporte) = Σ (cantidad · costo_base)":
        r"\text{costo\_directo}_{\text{reporte}} = \sum(\text{cantidad}\cdot\text{costo\_base})",
    "factor = 1 + sobrecosto/100":
        r"\text{factor} = 1+\dfrac{\text{sobrecosto}\,\%}{100}",
    "total_con_indirectos = costo_directo × factor":
        r"\text{total\_con\_indirectos} = \text{costo\_directo}\times\text{factor}",
    "total_con_indirectos = Σ partida.total":
        r"\text{total\_con\_indirectos} = \sum \text{partida.total}",
    "monto_indirecto = costo_directo × pct/100":
        r"\text{monto\_indirecto} = \text{costo\_directo}\times\dfrac{\text{pct}}{100}",
}


def memoria_calculos_presupuesto(p) -> dict:
    """Narra AMBOS flujos de indirectos sobre un `Presupuesto` ORM real (con
    `capitulos.partidas.insumos` ya cargados vía joinedload por el caller).

    No muta ningún objeto ORM, no hace commit. Devuelve {meta, pasos, constantes}.
    """
    cfg = p.config
    sobrecosto = float(cfg.sobrecosto) if cfg and cfg.sobrecosto is not None else 20.0
    factor = _factor_indirectos(cfg)   # función real de routers/calculos.py, pura

    P = []

    # ── VISTA A — semántica de POST /presupuestos/{pid}/calcular ────────────
    # Recalcula costo_base EN MEMORIA (rebucket + calc_base, puros) desde los
    # insumos actuales — igual que _recalcular_todo, sin escribir la partida.
    partidas_v1 = []
    costo_directo_v1 = 0.0
    n_partidas = 0
    for cap in p.capitulos:
        for partida in cap.partidas:
            n_partidas += 1
            if partida.insumos:
                mo, ma, otros = rebucket_insumos(partida.insumos)
            else:
                mo, ma, otros = float(partida.costo_mo or 0), float(partida.costo_ma or 0), float(partida.unitario_matriz or 0)
            base = calc_base(mo, ma, otros)
            cant = float(partida.cantidad or 0)
            aporte = cant * base
            costo_directo_v1 += aporte
            partidas_v1.append((partida, base, aporte))

    top_v1 = sorted(partidas_v1, key=lambda t: t[2], reverse=True)[:3]
    ejemplo_v1 = " + ".join(f"{_fmt(t[0].cantidad)}×{_fmt_money(t[1])}" for t in top_v1)
    P.append(_paso("Vista A — /calcular", "costo_directo₁", "Costo directo (semántica de /calcular)",
        costo_directo_v1, "HNL", "costo_directo(calcular) = Σ (cantidad · costo_base)",
        f"costo_directo₁ = {ejemplo_v1} + … ({n_partidas} partidas) = {_fmt_money(costo_directo_v1)}",
        "routers/calculos.py:12-34 _recalcular_todo() [recalculado aquí sin escribir BD]",
        "Recorre TODAS las partidas del presupuesto y suma cantidad × costo_base — costo_base recién recalculado desde los insumos actuales de cada partida (bucketing 3-vías real), SIN aplicar sobrecosto todavía.",
        "resultado"))

    total_v1 = costo_directo_v1 * factor
    P.append(_paso("Vista A — /calcular", "total₁", "Total con indirectos (semántica de /calcular)",
        total_v1, "HNL", "total_con_indirectos = costo_directo × factor",
        f"total₁ = {_fmt_money(costo_directo_v1)} × {_fmt(factor)} = {_fmt_money(total_v1)}",
        "routers/calculos.py:44-60 recalcular()",
        f"factor = 1 + sobrecosto/100 = 1 + {_fmt(sobrecosto)}/100 = {_fmt(factor)}. Este es el número que devuelve hoy `POST /presupuestos/{{pid}}/calcular`.",
        "resultado"))

    # ── VISTA B — semántica de GET /presupuestos/{pid}/reporte ──────────────
    # [RESUELTO 2026-07-30] costo_directo₂ ahora usa calc_base (misma definición
    # que Vista A), y total₂ = Σ partida.total real, sin re-multiplicar por
    # factor. Ver routers/calculos.py:75-92.
    caps_v2 = []
    costo_directo_v2 = 0.0
    total_v2_acc = 0.0
    for cap in p.capitulos:
        cap_directo = sum(float(pa.cantidad or 0) * calc_base(pa.costo_mo, pa.costo_ma, pa.unitario_matriz) for pa in cap.partidas)
        cap_total = sum(float(pa.total or 0) for pa in cap.partidas)
        costo_directo_v2 += cap_directo
        total_v2_acc += cap_total
        caps_v2.append((cap, cap_directo, cap_total))

    top_v2 = sorted(caps_v2, key=lambda t: t[2], reverse=True)[:3]
    ejemplo_v2 = " + ".join(f"{_fmt_money(t[1])}({t[0].clave})" for t in top_v2)
    paso_costo_directo_v2 = _paso("Vista B — /reporte", "costo_directo₂", "Costo directo (semántica de /reporte, corregida)",
        costo_directo_v2, "HNL", "costo_directo(reporte) = Σ (cantidad · costo_base)",
        f"costo_directo₂ = {ejemplo_v2} + … ({len(caps_v2)} capítulos) = {_fmt_money(costo_directo_v2)}",
        "routers/calculos.py:63-92 reporte(), línea 78 (fix 2026-07-30, goal-19654)",
        "Antes sumaba partida.total (ya con markup); ahora usa calc_base igual que /calcular — misma definición en ambas vistas.",
        "resultado")
    P.append(paso_costo_directo_v2)

    monto_indirecto_v2 = costo_directo_v2 * sobrecosto / 100
    P.append(_paso("Vista B — /reporte", "monto_indirecto₂", "Monto de indirectos mostrado en /reporte",
        monto_indirecto_v2, "HNL", "monto_indirecto = costo_directo × pct/100",
        f"monto_indirecto₂ = {_fmt_money(costo_directo_v2)} × {_fmt(sobrecosto)}/100 = {_fmt_money(monto_indirecto_v2)}",
        "routers/calculos.py:86 (indirectos_detalle['sobrecosto'])",
        "Ahora se calcula sobre costo_directo₂ limpio (sin markup) — mismo resultado que el sobrecosto real aplicado en /calcular.",
        "resultado"))

    total_v2 = total_v2_acc
    paso_total_v2 = _paso("Vista B — /reporte", "total₂", "Total con indirectos (semántica de /reporte, corregida)",
        total_v2, "HNL", "total_con_indirectos = Σ partida.total",
        f"total₂ = Σ partida.total ({len(caps_v2)} capítulos) = {_fmt_money(total_v2)}",
        "routers/calculos.py:94 (fix 2026-07-30, goal-19654)",
        "Ya no se re-multiplica por factor. partida.total (services/pricing.py) ya incluye el sobrecosto una sola vez — este es ahora el total real.",
        "resultado")
    P.append(paso_total_v2)

    for _pref in (paso_costo_directo_v2, paso_total_v2):
        if _pref["latex"] is None:
            _pref["latex"] = LATEX_BY_FORMULA_CALCULOS.get(_pref["formula"])

    diff = total_v2 - total_v1
    P.append(_paso("✅ Resuelto", "✅", "Doble aplicación de sobrecosto — RESUELTO 2026-07-30 (goal-19654)",
        round(diff, 4), "HNL", "—",
        f"/calcular → total₁ = {_fmt_money(total_v1)}  ·  /reporte → total₂ = {_fmt_money(total_v2)}  ·  Δ = {_fmt_money(diff)} (≈0, redondeo)",
        "docs/auditoria_formulas_mapa_estructura.md §C-02 · routers/calculos.py (fix 2026-07-30)",
        ("Hallazgo confirmado por Opus (protocolo de diagnóstico para bugs con riesgo financiero real) y corregido: "
         "/reporte ya no suma partida.total (con markup) y vuelve a aplicar factor — ahora usa calc_base como /calcular "
         "y expone el total real sin duplicar el sobrecosto. Ambas vistas coinciden (Δ≈0)."),
        "resultado"))

    for p_ in P:
        if p_["tipo"] != "input" and p_["latex"] is None:
            p_["latex"] = LATEX_BY_FORMULA_CALCULOS.get(p_["formula"])

    constantes = [
        {"simbolo": "sobrecosto", "latex": r"\text{sobrecosto}\,\% = " + _fmt(sobrecosto), "valor": sobrecosto, "unidad": "%",
         "desc": "config_presupuesto.sobrecosto — default 20.0 si no hay config (hardcode en calculos.py:14,73)."},
        {"simbolo": "factor", "latex": r"\text{factor} = " + _fmt(factor), "valor": factor, "unidad": "",
         "desc": "1 + sobrecosto/100. El comentario en el código dice: \"El sobrecosto ya incluye IVA y cualquier margen adicional del negocio\" — los campos administracion/utilidad/imprevistos/iva de config_presupuesto NO se leen en ningún cálculo."},
    ]
    meta = {
        "dominio": "calculos",
        "presupuesto_id": p.id,
        "nombre": p.nombre,
        "moneda": p.moneda,
        "n_partidas": n_partidas,
        "n_capitulos": len(caps_v2),
        "bug_doble_sobrecosto": False,
        "bug_doble_sobrecosto_resuelto_fecha": "2026-07-30",
        "total_v1_calcular": round(total_v1, 4),
        "total_v2_reporte": round(total_v2, 4),
        "diff_total": round(diff, 4),
    }
    return {"meta": meta, "pasos": P, "constantes": constantes}
