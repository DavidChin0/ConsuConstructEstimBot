"""
Fuente UNICA de cálculo de precios de partida — EstimaStruct (FASE 1).

Antes esta lógica estaba duplicada (idéntica) en routers/partidas.py,
routers/calculos.py, routers/insumos.py y routers/presupuestos.py. Auditado
2026-06-16 sobre datos vivos: las 3 rutas runtime dan resultado idéntico
(Casa StoneRaise sc=20% y CC132 sc=25% → 0 diferencias). Esta función las
reemplaza SIN cambiar números.

[FIX 2026-07-03] La auditoría de 2026-06-16 quedó stale por cambio de datos,
no de código: calculos.py tenía bucketing de 2 vías (MO vs todo-lo-demás) y
nunca tocaba unitario_matriz, mientras insumos.py ya usaba bucketing de 3 vías
(MO/MATERIAL/otros->unitario_matriz). Mientras ninguna partida tuviera
unitario_matriz != 0 las dos rutas coincidían; en cuanto insumos.py pobló ese
campo (partidas con insumos SUBCONTRATO/FLETE/EQUIPO reales), calcular() en
calculos.py empezó a duplicar ese monto (costo_ma recalculado + unitario_matriz
stale, ambos sumados en calc_base). Fix: rebucket_insumos() abajo es ahora la
ÚNICA fuente de bucketing; calculos.py e insumos.py la llaman en vez de
reimplementarla.

Módulo PURO: no toca BD ni resuelve el sobrecosto (eso es responsabilidad del
router, que lo lee de config_presupuesto según el contexto).

[FIX 2026-07-12 — P5, decisión Director] Antes este módulo NO redondeaba
(float puro de punta a punta), lo que dejaba resultados no determinísticos
frente a orden de operaciones y acumulaba drift en re-cálculos sucesivos.
Ahora se computa internamente con `decimal.Decimal` (conversión SIEMPRE vía
`Decimal(str(x))`, nunca `Decimal(float)`, para no heredar el error binario
del float) y se cuantiza con ROUND_HALF_UP a 4 decimales — igual a las
columnas monetarias Numeric(14,4) — en los BOUNDARIES de escritura (valores
que se asignan a columnas de partida/insumo). Las funciones siguen
ACEPTANDO y DEVOLVIENDO float: los callers (routers, calculos.py) siguen
haciendo su aritmética en float; esto no rompe sus interfaces. Deltas vs los
valores almacenados pre-fix son ≤0.0001 por valor y solo se materializan
cuando el presupuesto se recalcula.

OJO (footgun de datos, no de fórmula): si un presupuesto tiene sobrecosto=0 en
config pero sus PU almacenados llevan markup viejo (caso 'Apartamento Valle de
Angeles'), recalcular con sc=0 BORRA el margen. Eso es decisión de negocio, no
de este módulo.
"""
from decimal import Decimal, ROUND_HALF_UP


def quantize_money(x) -> float:
    """Cuantiza a 4 decimales ROUND_HALF_UP (boundary de escritura, columnas Numeric(14,4))."""
    return float(Decimal(str(x or 0)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))


def calc_base(costo_mo, costo_ma, unitario_matriz) -> float:
    """costo_base = MO + MA + sub-matrices OPUS."""
    total = Decimal(str(costo_mo or 0)) + Decimal(str(costo_ma or 0)) + Decimal(str(unitario_matriz or 0))
    return quantize_money(total)


def rebucket_insumos(insumos) -> tuple:
    """Bucketing canonico 3-vias desde insumos -> (mo, ma, otros).
    otros = SUBCONTRATO/FLETE/EQUIPO/etc (todo lo que no es MO ni MATERIAL) -> unitario_matriz.
    Fuente unica: cualquier ruta que recalcule costo_mo/costo_ma/unitario_matriz desde
    insumos debe usar esta funcion, no reimplementar el bucketing (bug historico: calculos.py
    tenia bucketing de 2 vias y dejaba unitario_matriz stale -> doble conteo en calc_base)."""
    mo = sum((Decimal(str(i.total or 0)) for i in insumos if i.tipo == "MANO_OBRA"), Decimal("0"))
    ma = sum((Decimal(str(i.total or 0)) for i in insumos if i.tipo == "MATERIAL"), Decimal("0"))
    otros = sum((Decimal(str(i.total or 0)) for i in insumos if i.tipo not in ("MANO_OBRA", "MATERIAL")), Decimal("0"))
    return quantize_money(mo), quantize_money(ma), quantize_money(otros)


def precio_unitario(base, sobrecosto_pct) -> float:
    """PU = base × (1 + sobrecosto/100)."""
    pu = Decimal(str(base or 0)) * (Decimal("1") + Decimal(str(sobrecosto_pct or 0)) / Decimal("100"))
    return quantize_money(pu)


def recalcular_partida(partida, sobrecosto_pct) -> None:
    """Escribe costo_base, precio_unitario y total en la partida (in place)."""
    base = calc_base(partida.costo_mo, partida.costo_ma, partida.unitario_matriz)
    pu = precio_unitario(base, sobrecosto_pct)
    total = Decimal(str(partida.cantidad or 0)) * Decimal(str(pu))
    partida.costo_base = base
    partida.precio_unitario = pu
    partida.total = quantize_money(total)
