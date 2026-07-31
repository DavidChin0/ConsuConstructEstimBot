"""
Memoria de cálculo narrada de `services/pricing.py` — Auditoría de Fórmulas (2026-07-27).

Este módulo NO calcula nada por su cuenta. Narra, paso a paso (símbolo +
fórmula + sustitución numérica + valor + referencia), exactamente lo que
`services/pricing.py` (ADR-003, fuente ÚNICA de costeo) ya calcula. Sigue el
mismo contrato `_paso()` que `calculo_estructural.memoria_calculo`,
`calculo_conexion_acero.memoria_conexion` y `calculo_miembro_acero.memoria_miembro`.

Funciones de pricing.py usadas (todas PURAS, sin efecto — nunca `recalcular_partida`,
que escribe in-place sobre el ORM; ver docstring de pricing.py y architecture.md §7):
    rebucket_insumos(insumos) -> (mo, ma, otros)
    calc_base(mo, ma, matriz) -> costo_base
    precio_unitario(base, sobrecosto_pct) -> PU
    quantize_money(x) -> Decimal(str(x)).quantize(0.0001, ROUND_HALF_UP)

`total = cantidad × PU` no tiene función pura propia en pricing.py (solo existe
dentro de `recalcular_partida`, que escribe). Aquí se narra con la MISMA fórmula
documentada en pricing.py y architecture.md §4 Paso 4, usando `quantize_money`
importado (no una cuantización paralela) — sin tocar ningún objeto ORM.
"""
from decimal import Decimal

from backend.calculo_estructural import _fmt, _ascii_to_latex
from backend.services.pricing import calc_base, rebucket_insumos, precio_unitario, quantize_money


def _fmt_money(v) -> str:
    """Formatea dinero a 4dp con separador de miles — igual a Numeric(14,4) / ADR-004."""
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


LATEX_BY_FORMULA_PRICING = {
    "costo_mo = Σ insumo.total (tipo = MANO_OBRA)":
        r"\text{costo\_mo} = \sum_{i\,:\,\text{MANO\_OBRA}} i.\text{total}",
    "costo_ma = Σ insumo.total (tipo = MATERIAL)":
        r"\text{costo\_ma} = \sum_{i\,:\,\text{MATERIAL}} i.\text{total}",
    "unitario_matriz = Σ insumo.total (tipo ∉ {MANO_OBRA, MATERIAL})":
        r"\text{unitario\_matriz} = \sum_{i\,\notin\,\{MO,MA\}} i.\text{total}",
    "costo_base = costo_mo + costo_ma + unitario_matriz":
        r"\text{costo\_base} = \text{costo\_mo} + \text{costo\_ma} + \text{unitario\_matriz}",
    "PU = costo_base × (1 + sobrecosto/100)":
        r"PU = \text{costo\_base}\left(1+\dfrac{\text{sobrecosto}\,\%}{100}\right)",
    "total = cantidad × PU":
        r"\text{total} = \text{cantidad}\times PU",
    "x_q = Decimal(str(x)).quantize(0.0001, ROUND_HALF_UP)":
        r"x_q = \text{Decimal}(x)\big._{\text{quantize}}(0.0001,\ \text{ROUND\_HALF\_UP})",
}


def memoria_pricing(costo_mo, costo_ma, unitario_matriz, sobrecosto_pct, cantidad,
                     insumos=None, stored=None, meta_extra=None) -> dict:
    """Narra el pipeline de costeo de UNA partida (`services/pricing.py`, ADR-003).

    Args:
        costo_mo, costo_ma, unitario_matriz: buckets de entrada. Si `insumos` se
            provee, estos tres valores se IGNORAN y se recalculan en vivo desde los
            insumos reales vía `rebucket_insumos` (fuente única) — así el paso de
            bucketing queda narrado con números reales, no solo el resultado final.
        sobrecosto_pct: % de sobrecosto (mismo campo que `config_presupuesto.sobrecosto`).
        cantidad: cantidad de la partida (para el paso `total`).
        insumos: lista opcional de InsumoPartida ORM (o cualquier objeto con
            .tipo/.total) — activa la narración de bucketing 3-vías.
        stored: dict opcional con los valores YA PERSISTIDOS en la partida real
            (costo_mo, costo_ma, unitario_matriz, costo_base, precio_unitario, total)
            — si se provee, se agrega un paso de verificación que compara el
            recálculo en vivo (desde insumos actuales) contra lo guardado en BD,
            para exponer datos posiblemente STALE (ver nota "footgun de datos" en
            pricing.py). Esto es lectura/comparación, nunca escribe nada.
        meta_extra: dict opcional para enriquecer `meta` (partida_id, clave_csi, etc.)

    Returns:
        {meta, pasos, constantes} — mismo contrato que los otros 4 motores narrados.
    """
    P = []
    meta = {"dominio": "pricing", "insumos_reales": insumos is not None}

    mo, ma, otros = float(costo_mo or 0), float(costo_ma or 0), float(unitario_matriz or 0)

    # ── BUCKETING 3-VÍAS (solo si se pasan insumos reales) ──────────────────────
    if insumos is not None:
        n_mo = [i for i in insumos if i.tipo == "MANO_OBRA"]
        n_ma = [i for i in insumos if i.tipo == "MATERIAL"]
        n_ot = [i for i in insumos if i.tipo not in ("MANO_OBRA", "MATERIAL")]
        mo, ma, otros = rebucket_insumos(insumos)   # ÚNICA fuente — pricing.rebucket_insumos

        def _sum_terms(lst, cap=5):
            terms = [_fmt_money(float(i.total or 0)) for i in lst[:cap]]
            suf = f" + … ({len(lst) - cap} más)" if len(lst) > cap else ""
            return (" + ".join(terms) if terms else "0") + suf

        P.append(_paso("Bucketing 3-vías", "costo_mo", "Mano de obra (Σ insumos MANO_OBRA)",
            mo, "HNL/unidad", "costo_mo = Σ insumo.total (tipo = MANO_OBRA)",
            f"costo_mo = {_sum_terms(n_mo)} = {_fmt_money(mo)}  ({len(n_mo)} insumo(s))",
            "services/pricing.py:56-65 rebucket_insumos()",
            "Suma de todos los insumos tipo MANO_OBRA de la partida. Fuente única desde 2026-07-03 (antes duplicada 2-vías en calculos.py — ver ADR-003).",
            "intermedio"))
        P.append(_paso("Bucketing 3-vías", "costo_ma", "Material (Σ insumos MATERIAL)",
            ma, "HNL/unidad", "costo_ma = Σ insumo.total (tipo = MATERIAL)",
            f"costo_ma = {_sum_terms(n_ma)} = {_fmt_money(ma)}  ({len(n_ma)} insumo(s))",
            "services/pricing.py:56-65 rebucket_insumos()",
            "Suma de todos los insumos tipo MATERIAL de la partida.",
            "intermedio"))
        P.append(_paso("Bucketing 3-vías", "unitario_matriz", "Sub-matrices OPUS (Σ resto)",
            otros, "HNL/unidad", "unitario_matriz = Σ insumo.total (tipo ∉ {MANO_OBRA, MATERIAL})",
            f"unitario_matriz = {_sum_terms(n_ot)} = {_fmt_money(otros)}  ({len(n_ot)} insumo(s): HERRAMIENTA/EQUIPO/FLETE/SUBCONTRATO/DISEÑO)",
            "services/pricing.py:56-65 rebucket_insumos()",
            "Todo insumo que NO es MANO_OBRA ni MATERIAL va aquí — SUBCONTRATO/FLETE/EQUIPO/HERRAMIENTA/DISEÑO. Bug histórico 2026-07-03: calculos.py ignoraba este bucket → doble conteo si un insumo caía aquí.",
            "intermedio"))

    # ── COSTO BASE ────────────────────────────────────────────────────────────
    base = calc_base(mo, ma, otros)   # pricing.calc_base — ÚNICA fuente
    P.append(_paso("Costo base", "costo_base", "Costo base de la partida", base, "HNL/unidad",
        "costo_base = costo_mo + costo_ma + unitario_matriz",
        f"costo_base = {_fmt_money(mo)} + {_fmt_money(ma)} + {_fmt_money(otros)} = {_fmt_money(base)}",
        "services/pricing.py:50-53 calc_base()",
        "costo_base = MO + MA + sub-matrices OPUS. Fuente única del sistema — ningún router debe recalcular esto en paralelo (ADR-003).",
        "intermedio"))

    # ── PRECIO UNITARIO ───────────────────────────────────────────────────────
    sc = float(sobrecosto_pct or 0)
    pu = precio_unitario(base, sc)   # pricing.precio_unitario — ÚNICA fuente
    P.append(_paso("Precio unitario", "PU", "Precio unitario de venta", pu, "HNL/unidad",
        "PU = costo_base × (1 + sobrecosto/100)",
        f"PU = {_fmt_money(base)} × (1 + {_fmt(sc)}/100) = {_fmt_money(pu)}",
        "services/pricing.py:68-71 precio_unitario()",
        "Sobrecosto = markup del negocio. Nota de arquitectura: config_presupuesto también tiene administracion/utilidad/imprevistos/iva, pero NINGÚN cálculo los lee hoy — son campos muertos (ver docs/auditoria_formulas_mapa_estructura.md §0).",
        "resultado"))

    # ── TOTAL ─────────────────────────────────────────────────────────────────
    cant = float(cantidad or 0)
    total = quantize_money(Decimal(str(cant)) * Decimal(str(pu)))   # misma fórmula documentada en pricing.py; quantize_money real, sin escribir ORM
    P.append(_paso("Total", "total", "Total de la partida", total, "HNL",
        "total = cantidad × PU",
        f"total = {_fmt(cant)} × {_fmt_money(pu)} = {_fmt_money(total)}",
        "services/pricing.py:74-81 recalcular_partida() [solo la fórmula — este endpoint NO escribe la partida]",
        "cantidad × precio unitario = monto que va a la fila del presupuesto. Este endpoint lee y narra; nunca invoca recalcular_partida (que persiste).",
        "resultado"))

    # ── CUANTIZACIÓN (ADR-004) ───────────────────────────────────────────────
    P.append(_paso("Cuantización", "x_q", "Cuantización monetaria en cada boundary de escritura",
        True, "", "x_q = Decimal(str(x)).quantize(0.0001, ROUND_HALF_UP)",
        "aplicada a costo_base, PU y total arriba (Decimal, nunca float directo)",
        "services/pricing.py:45-47 quantize_money() · ADR-004",
        "Toda cifra monetaria pasa por Decimal(str(x)) — nunca Decimal(float) — cuantizada ROUND_HALF_UP a 4 decimales, igual a las columnas Numeric(14,4). Fix 2026-07-12: antes era float puro y acumulaba drift en recálculos sucesivos.",
        "check"))

    # ── VERIFICACIÓN vs BD (solo si se pasa `stored`) ────────────────────────
    if stored:
        def _diff(a, b):
            try:
                return abs(float(a or 0) - float(b or 0))
            except (TypeError, ValueError):
                return None
        checks = [
            ("costo_base", base, stored.get("costo_base")),
            ("precio_unitario", pu, stored.get("precio_unitario")),
            ("total", total, stored.get("total")),
        ]
        drift = [(k, live, st, _diff(live, st)) for k, live, st in checks]
        peor = max((d[3] or 0) for d in drift)
        ok = peor <= 0.0001
        detalle = " · ".join(f"{k}: BD={_fmt_money(st)} vs recálculo={_fmt_money(live)}" for k, live, st, d in drift)
        P.append(_paso("Verificación vs BD", "✓" if ok else "⚠", "Recálculo en vivo (insumos actuales) vs valores persistidos",
            ok, "", "—", detalle, "—",
            ("Los valores guardados en la partida coinciden con recalcular desde los insumos actuales."
             if ok else
             "⚠ DISCREPANCIA: la partida tiene valores persistidos distintos a lo que sus insumos actuales producirían. No es necesariamente un error — puede ser sobrecosto editado manualmente después del último /calcular (ver 'footgun de datos' en pricing.py:37-40) — pero el Director debe verlo, no asumirlo."),
            "check"))

    for p in P:
        if p["tipo"] != "input" and p["latex"] is None:
            p["latex"] = LATEX_BY_FORMULA_PRICING.get(p["formula"])

    constantes = [
        {"simbolo": "sobrecosto", "latex": r"\text{sobrecosto}\,\% = " + _fmt(sc), "valor": sc, "unidad": "%",
         "desc": "Markup del negocio sobre costo_base. Config por presupuesto (config_presupuesto.sobrecosto), default 20% si no hay config."},
        {"simbolo": "dp", "latex": r"4\ \text{decimales, ROUND\_HALF\_UP}", "valor": 4, "unidad": "dp",
         "desc": "Precisión de cuantización monetaria — igual a columnas Numeric(14,4). ADR-004, fix 2026-07-12."},
    ]
    if meta_extra:
        meta.update(meta_extra)
    return {"meta": meta, "pasos": P, "resultado": {"costo_base": base, "precio_unitario": pu, "total": total,
            "costo_mo": mo, "costo_ma": ma, "unitario_matriz": otros}, "constantes": constantes}
