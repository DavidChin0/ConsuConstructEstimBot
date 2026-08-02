"""
Motor de cálculo financiero — cédula de indirectos auditable
===============================================================
Contexto (por qué existe): auditoría del catálogo de rendimientos v1.3
(1145 partidas) contra RICS ICMS 3rd edition encontró que EstimaStruct tiene
campos `config_presupuesto.imprevistos` (contingencia) y
`config_presupuesto.administracion` (gastos generales) — pero en 0.00 en las
6 obras reales. Todo el margen vive en un solo campo `sobrecosto` (15-25%,
no desglosado). Cero partidas de seguros/fianzas en las 1145. Esto rompe
auditabilidad: nadie puede probar cuánto del precio es riesgo real vs.
utilidad vs. gasto general vs. seguro.

Este motor NO toca config_presupuesto ni sobrecosto — es la cédula financiera
ADITIVA que un auditor fiscal exigiría: cada indirecto es una línea trazable
con orden de aplicación EXPLÍCITO (interés compuesto, no aditivo plano),
con evidencia cuando aplica, y el snapshot resultante (financiero_calculo)
es INMUTABLE una vez generado — igual que un auditor fiscal no acepta que la
cédula de un ejercicio cerrado cambie sola si después cambian los %.

Todas las funciones son PURAS (sin ORM). Moneda: Lempiras (HNL).
"""

import math
from datetime import datetime


# ─────────────────────────────────────────────────────────────────────────────
# CATÁLOGO ICMS DE REFERENCIA (RICS International Cost Management Standard,
# 3rd edition — Table B-1 / Table 2). Solo los ~8 códigos relevantes para
# indirectos de obra en Honduras. Sirve de tooltip/ayuda en el frontend al
# crear un financiero_item — el `categoria_icms` es la ancla de auditoría
# que conecta cada línea de esta cédula con el estándar internacional.
# ─────────────────────────────────────────────────────────────────────────────
CATALOGO_ICMS_REFERENCIA = {
    "08.010": "Gestión y administración de obra (Preliminares — Constructors' site overheads)",
    "08.110": "Seguros, fianzas, garantías y bonos (Preliminaries — Insurances, bonds, guarantees and warranties)",
    "08.120": "Tasas y permisos estatutarios del constructor",
    "09.010": "Asignación por desarrollo de diseño (Risk Allowance — Design development allowance)",
    "09.020": "Contingencia de construcción (Risk Allowance — Construction contingencies)",
    "09.030": "Ajuste por nivel de precios / escalamiento",
    "10.010": "Impuestos pagados por el constructor (IVA/ISV)",
    "10.020": "Impuestos pagados por el cliente relacionados al contrato",
}

BASES_CALCULO = ("COSTO_DIRECTO", "SUBTOTAL_ACUMULADO", "MONTO_FIJO")
TIPOS_ITEM = ("IMPREVISTO", "SEGURO", "FIANZA", "ADMINISTRACION",
              "UTILIDAD", "IMPUESTO", "ESCALAMIENTO", "OTRO")

TOLERANCIA_REDONDEO = 0.01   # Lempiras — tolerancia de checksum por redondeo


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS DE FORMATO (texto de sustitución tipo auditor: "L. 850,000.00")
# ─────────────────────────────────────────────────────────────────────────────

def _fmt_l(monto: float) -> str:
    """Lempiras con separador de miles, 2 decimales: 'L. 850,000.00'."""
    return f"L. {monto:,.2f}"


def _fmt_pct(pct: float) -> str:
    """Porcentaje con 2 decimales: '8.00%'."""
    return f"{pct:.2f}%"


def _paso(orden, nombre, categoria_icms, tipo, base_calculo, base_valor,
          formula, sustitucion, monto, subtotal_acumulado, evidencia,
          obligatorio) -> dict:
    return {
        "orden":               orden,
        "nombre":              nombre,
        "categoria_icms":      categoria_icms,
        "tipo":                tipo,
        "base_calculo":        base_calculo,
        "base_valor":          round(base_valor, 4),
        "formula":             formula,
        "sustitucion":         sustitucion,
        "monto":               round(monto, 4),
        "subtotal_acumulado":  round(subtotal_acumulado, 4),
        "evidencia":           evidencia or "",
        "obligatorio":         bool(obligatorio),
    }


# ─────────────────────────────────────────────────────────────────────────────
# MOTOR NÚCLEO
# ─────────────────────────────────────────────────────────────────────────────

def calcular_indirectos(costo_directo: float, iva_pct: float, items: list) -> dict:
    """
    Aplica la cédula de indirectos sobre `costo_directo`, en el `orden`
    declarado por cada item, con compounding real (SUBTOTAL_ACUMULADO se
    calcula sobre costo_directo + indirectos de menor orden ya aplicados).
    IVA siempre es el último paso, sobre el subtotal final. Función PURA.

    items: lista de dicts, cada uno con
      {id, nombre, tipo, categoria_icms, base_calculo, porcentaje,
       monto_fijo, orden, obligatorio, evidencia}
    Los ordena por 'orden' ascendente antes de aplicar — el motor ordena,
    no confía en el caller.

    Devuelve dict:
      memoria (lista de pasos), costo_directo, subtotal_antes_iva, iva_monto,
      total_general, items_aplicados (listo para persistir en items_json),
      advertencias (lista de strings), cuadra (bool, checksum).
    """
    if costo_directo < 0:
        raise ValueError(f"costo_directo no puede ser negativo: {costo_directo}")

    advertencias = []
    memoria = []
    items_aplicados = []

    items_ordenados = sorted(items or [], key=lambda it: it.get("orden") or 0)

    subtotal = float(costo_directo)

    for it in items_ordenados:
        nombre         = it.get("nombre") or "(sin nombre)"
        tipo           = it.get("tipo") or "OTRO"
        categoria_icms = it.get("categoria_icms") or ""
        base_calculo   = it.get("base_calculo") or "COSTO_DIRECTO"
        orden          = it.get("orden") or 0
        obligatorio    = bool(it.get("obligatorio"))
        evidencia      = it.get("evidencia") or ""

        porcentaje = it.get("porcentaje")
        monto_fijo = it.get("monto_fijo")

        if base_calculo == "MONTO_FIJO":
            if monto_fijo is None:
                monto_fijo = 0.0
                advertencias.append(
                    f"obligatorio=True pero monto_fijo vacío (tratado como 0): {nombre}"
                    if obligatorio else
                    f"monto_fijo vacío (tratado como 0): {nombre}"
                )
            monto_fijo = float(monto_fijo)
            base_valor = 0.0   # no aplica base % en monto fijo
            monto = monto_fijo
            formula = "Monto fijo"
            sustitucion = _fmt_l(monto)
        else:
            porcentaje_faltaba = porcentaje is None
            if porcentaje_faltaba:
                porcentaje = 0.0
            porcentaje = float(porcentaje)
            if obligatorio and porcentaje == 0.0:
                advertencias.append(f"obligatorio=True pero inactivo/0%: {nombre}")
            elif porcentaje_faltaba:
                advertencias.append(f"porcentaje vacío (tratado como 0%): {nombre}")

            if base_calculo == "COSTO_DIRECTO":
                base_valor = float(costo_directo)
                formula = "Costo_directo × %"
            else:   # SUBTOTAL_ACUMULADO
                base_valor = subtotal
                formula = "Subtotal_acumulado × %"

            monto = base_valor * porcentaje / 100.0
            sustitucion = f"{_fmt_l(base_valor)} × {_fmt_pct(porcentaje)} = {_fmt_l(monto)}"

        subtotal += monto

        memoria.append(_paso(
            orden=orden, nombre=nombre, categoria_icms=categoria_icms, tipo=tipo,
            base_calculo=base_calculo, base_valor=base_valor,
            formula=formula, sustitucion=sustitucion, monto=monto,
            subtotal_acumulado=subtotal, evidencia=evidencia, obligatorio=obligatorio,
        ))

        items_aplicados.append({
            "id":                  it.get("id"),
            "nombre":              nombre,
            "tipo":                tipo,
            "categoria_icms":      categoria_icms,
            "base_calculo":        base_calculo,
            "porcentaje":          porcentaje if base_calculo != "MONTO_FIJO" else None,
            "monto_fijo":          monto_fijo if base_calculo == "MONTO_FIJO" else None,
            "orden":               orden,
            "obligatorio":         obligatorio,
            "evidencia":           evidencia,
            "monto_calculado":     round(monto, 4),
            "base_usada_valor":    round(base_valor, 4),
        })

    subtotal_antes_iva = subtotal

    # IVA — SIEMPRE el último paso, parámetro directo (no viene de items).
    iva_pct = float(iva_pct or 0)
    iva_monto = subtotal_antes_iva * iva_pct / 100.0
    total_general = subtotal_antes_iva + iva_monto

    memoria.append(_paso(
        orden=(max([it.get("orden") or 0 for it in items_ordenados], default=0) + 1),
        nombre="IVA", categoria_icms="10.010", tipo="IMPUESTO",
        base_calculo="SUBTOTAL_ACUMULADO", base_valor=subtotal_antes_iva,
        formula="Subtotal_antes_IVA × IVA%",
        sustitucion=f"{_fmt_l(subtotal_antes_iva)} × {_fmt_pct(iva_pct)} = {_fmt_l(iva_monto)}",
        monto=iva_monto, subtotal_acumulado=total_general,
        evidencia="", obligatorio=True,
    ))

    # Checksum interno — auditor fiscal: la cédula debe cuadrar exacto.
    suma_items = sum(x["monto_calculado"] for x in items_aplicados)
    check1 = abs((costo_directo + suma_items) - subtotal_antes_iva) <= TOLERANCIA_REDONDEO
    check2 = abs((subtotal_antes_iva + iva_monto) - total_general) <= TOLERANCIA_REDONDEO
    cuadra = check1 and check2
    if not cuadra:
        advertencias.append(
            f"CHECKSUM NO CUADRA: costo_directo+items={costo_directo + suma_items:.4f} "
            f"vs subtotal_antes_iva={subtotal_antes_iva:.4f} (check1={check1}); "
            f"subtotal+iva={subtotal_antes_iva + iva_monto:.4f} vs "
            f"total_general={total_general:.4f} (check2={check2})"
        )

    return {
        "memoria":              memoria,
        "costo_directo":        round(costo_directo, 4),
        "subtotal_antes_iva":   round(subtotal_antes_iva, 4),
        "iva_monto":            round(iva_monto, 4),
        "total_general":        round(total_general, 4),
        "items_aplicados":      items_aplicados,
        "advertencias":         advertencias,
        "cuadra":               cuadra,
    }
