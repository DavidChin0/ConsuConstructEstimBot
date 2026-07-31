# -*- coding: utf-8 -*-
"""
Takeoff de cantidad de partida — motor PURO + memoria narrada (2026-07-31).

Módulo ciego C-05 de `docs/auditoria_formulas_mapa_estructura.md` — **riesgo
ALTO**: es la fórmula que convierte la cantidad bruta de Revit en la cantidad
que se factura, y tiene un comportamiento silencioso que cambia el número sin
avisar.

    cantidad = ceil(revit_q) × factor_e × factor_f

EL PROBLEMA REAL — `_safe_factor` (routers/partidas.py:70-72)
--------------------------------------------------------------
    def _safe_factor(v, default=1.0):
        f = float(v or default)
        return f if f else default

Tres comportamientos que el usuario no ve:

1. **factor = 0 ⇒ se convierte en 1.0.** Quien teclea 0 esperando anular la
   partida obtiene la cantidad COMPLETA. `float(0 or 1.0)` = 1.0 por el `or`, y
   aunque no fuera así el `return f if f else default` lo atraparía igual. Es el
   caso peligroso: la intención del usuario ("no quiero esto") se invierte en
   silencio a "quiero todo".
2. **factor negativo PASA.** `-1` es truthy, así que sobrevive las dos guardas y
   produce una cantidad negativa → total negativo → resta del presupuesto.
3. **ceil() sobre revit_q.** La cantidad de Revit se redondea SIEMPRE hacia
   arriba antes de aplicar factores; 12.1 m³ se factura como 13. Es deliberado
   (no se compra medio saco) pero el usuario no ve el salto.

Este módulo NO cambia ninguno de los tres comportamientos — cambiarlos sin
autorización rompería presupuestos vivos. Los EXPONE como `advertencias[]`,
exactamente como se hizo con mampostería, y `routers/partidas.py` ahora devuelve
esas advertencias en la respuesta de `/revit-q` y `/factores` (campo aditivo, no
rompe clientes existentes).

ADR-003: `takeoff_cantidad()` es el motor; `routers/partidas.py` lo llama en vez
de repetir la aritmética inline, y `memoria_cantidad()` sólo lee su salida.

Contrato de salida idéntico a los otros motores narrados:
    {meta, pasos[], constantes[], resultado{}}
"""
import math

from backend.calculo_estructural import _fmt, _ascii_to_latex

FACTOR_DEFAULT = 1.0


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


LATEX_BY_FORMULA_PARTIDAS = {
    "revit_q_ceil = ceil(revit_q)":
        r"Q_{ceil} = \left\lceil Q_{revit} \right\rceil",
    "cantidad = ceil(revit_q) × factor_e × factor_f":
        r"Q = Q_{ceil}\cdot f_e\cdot f_f",
    "f_efectivo = f si f ≠ 0, si no 1.0":
        r"f_{ef} = \begin{cases} f & f \ne 0 \\ 1.0 & f = 0\end{cases}",
    "total = cantidad × precio_unitario":
        r"T = Q\cdot PU",
    "Δcantidad = cantidad − revit_q":
        r"\Delta Q = Q - Q_{revit}",
}


# ─────────────────────────────────────────────────────────────────────────────
# MOTOR PURO — fuente única. routers/partidas.py lo llama; la memoria lo narra.
# ─────────────────────────────────────────────────────────────────────────────
def factor_efectivo(v, default: float = FACTOR_DEFAULT) -> tuple:
    """Réplica EXACTA de `routers/partidas._safe_factor`, pero devolviendo también
    qué pasó: (valor_efectivo, aviso|None). No cambia el comportamiento."""
    f = float(v or default)         # aritmética idéntica a _safe_factor
    f = f if f else default
    # Diagnóstico (no cambia el resultado): distinguir "el usuario puso 0" de
    # "no había valor". `v is None` = campo vacío → el default es legítimo.
    # `v == 0` = el usuario tecleó cero y el sistema lo reinterpretó como 1.
    if v is not None:
        try:
            if float(v) == 0.0:
                return f, "cero_a_uno"
        except (TypeError, ValueError):
            pass
    if f < 0:
        return f, "negativo"
    return f, None


def takeoff_cantidad(revit_q, factor_e=None, factor_f=None,
                     precio_unitario: float = 0.0) -> dict:
    """cantidad = ceil(revit_q) × fe × ff, con la semántica REAL de _safe_factor.

    Devuelve dict con la cantidad, los factores efectivos, los factores crudos
    tal como llegaron, y `advertencias[]` cuando el resultado no es el que un
    usuario razonable esperaría. Nunca lanza: el takeoff siempre produce número.
    """
    rq_crudo = float(revit_q or 0)
    rq = math.ceil(rq_crudo)
    fe, aviso_e = factor_efectivo(factor_e)
    ff, aviso_f = factor_efectivo(factor_f)
    cantidad = rq * fe * ff
    total = cantidad * float(precio_unitario or 0)

    advertencias = []
    if aviso_e == "cero_a_uno":
        advertencias.append(
            "factor_e = 0 se convirtió en 1.0 (routers/partidas._safe_factor). Si la "
            "intención era anular la partida, NO se anuló: quedó la cantidad completa. "
            "Para dejar la partida en cero hay que poner cantidad = 0, no el factor.")
    if aviso_f == "cero_a_uno":
        advertencias.append(
            "factor_f = 0 se convirtió en 1.0 (routers/partidas._safe_factor). Mismo caso "
            "que factor_e: el 0 no anula, deja la cantidad completa.")
    if aviso_e == "negativo" or aviso_f == "negativo":
        advertencias.append(
            f"Factor negativo aceptado (fe={fe}, ff={ff}): la cantidad resultante es "
            f"{cantidad:g} y su total RESTA del presupuesto. _safe_factor sólo atrapa el 0, "
            "no el signo.")
    if rq != rq_crudo:
        advertencias.append(
            f"revit_q se redondeó HACIA ARRIBA de {rq_crudo:g} a {rq} antes de aplicar "
            f"factores (ceil). Se facturan {rq - rq_crudo:g} unidades por encima de lo "
            "medido en el modelo. Es deliberado, pero el salto no se muestra en la tabla.")

    return {
        "revit_q_crudo": round(rq_crudo, 6),
        "revit_q": rq,
        "factor_e_crudo": factor_e,
        "factor_f_crudo": factor_f,
        "factor_e": fe,
        "factor_f": ff,
        "cantidad": cantidad,
        "precio_unitario": round(float(precio_unitario or 0), 4),
        "total": round(total, 4),
        "delta_ceil": round(rq - rq_crudo, 6),
        "aviso_e": aviso_e,
        "aviso_f": aviso_f,
        "advertencias": advertencias,
        "ok_factores": not advertencias,
    }


# ─────────────────────────────────────────────────────────────────────────────
# MEMORIA NARRADA — lee el motor puro de arriba, nunca recalcula por su cuenta
# ─────────────────────────────────────────────────────────────────────────────
def memoria_cantidad(revit_q, factor_e=None, factor_f=None,
                     precio_unitario: float = 0.0, unidad: str = "",
                     meta_extra: dict | None = None) -> dict:
    """Narra el takeoff de cantidad de una partida. Devuelve {meta, pasos,
    constantes, resultado}. NO toca la BD."""
    r = takeoff_cantidad(revit_q, factor_e, factor_f, precio_unitario)
    u = unidad or "und"
    P = []

    P.append(_paso("Cantidad de Revit", "Q_revit", "Cantidad bruta del modelo",
        r["revit_q_crudo"], u, "dato del modelo Revit",
        f"Q_revit = {_fmt(r['revit_q_crudo'])}", "import Revit / schedule",
        "Cantidad medida directamente en el modelo (schedule exportado). Es el único dato "
        "que viene de fuera; todo lo demás se deriva de aquí.", "input"))
    P.append(_paso("Cantidad de Revit", "Q_ceil", "Cantidad redondeada hacia arriba",
        r["revit_q"], u, "revit_q_ceil = ceil(revit_q)",
        f"ceil({_fmt(r['revit_q_crudo'])}) = {r['revit_q']}",
        "routers/partidas.py:158,187",
        "Siempre hacia ARRIBA, nunca al más cercano: no se compra medio saco ni media "
        "varilla. El salto respecto de la medición real es Δ = "
        f"{_fmt(r['delta_ceil'])} {u}.", "intermedio"))

    P.append(_paso("Factores de ajuste", "f_e (crudo)", "Factor E tal como está guardado",
        r["factor_e_crudo"] if r["factor_e_crudo"] is not None else "—", "",
        "dato de proyecto", f"factor_e = {r['factor_e_crudo']}", "columna partida.factor_e",
        "Factor de esponjamiento / desperdicio. Lo teclea el usuario en la tabla.", "input"))
    P.append(_paso("Factores de ajuste", "f_e", "Factor E EFECTIVO", r["factor_e"], "",
        "f_efectivo = f si f ≠ 0, si no 1.0",
        f"_safe_factor({r['factor_e_crudo']}) = {_fmt(r['factor_e'])}",
        "routers/partidas.py:70-72",
        "⚠ Un 0 NO anula: se convierte en 1.0 y la partida queda completa. Un valor "
        "negativo SÍ pasa y produce cantidad negativa. Éste es el paso que hasta "
        "2026-07-31 corría totalmente ciego.",
        "resultado" if r["aviso_e"] is None else "check"))
    P.append(_paso("Factores de ajuste", "f_f (crudo)", "Factor F tal como está guardado",
        r["factor_f_crudo"] if r["factor_f_crudo"] is not None else "—", "",
        "dato de proyecto", f"factor_f = {r['factor_f_crudo']}", "columna partida.factor_f",
        "Segundo factor de ajuste (merma, traslape, forma). Mismo tratamiento que f_e.", "input"))
    P.append(_paso("Factores de ajuste", "f_f", "Factor F EFECTIVO", r["factor_f"], "",
        "f_efectivo = f si f ≠ 0, si no 1.0",
        f"_safe_factor({r['factor_f_crudo']}) = {_fmt(r['factor_f'])}",
        "routers/partidas.py:70-72",
        "Mismo comportamiento silencioso que f_e.",
        "resultado" if r["aviso_f"] is None else "check"))

    P.append(_paso("Cantidad facturable", "Q", "Cantidad final de la partida",
        r["cantidad"], u,
        "cantidad = ceil(revit_q) × factor_e × factor_f",
        f"{r['revit_q']} × {_fmt(r['factor_e'])} × {_fmt(r['factor_f'])} = {_fmt(r['cantidad'])}",
        "routers/partidas.py:161,189",
        "La cantidad que se factura y que multiplica el precio unitario. Es lo que ve el "
        "cliente en la fila del presupuesto.", "takeoff"))
    P.append(_paso("Cantidad facturable", "ΔQ", "Diferencia contra el modelo",
        round(r["cantidad"] - r["revit_q_crudo"], 6), u,
        "Δcantidad = cantidad − revit_q",
        f"{_fmt(r['cantidad'])} − {_fmt(r['revit_q_crudo'])} = {_fmt(r['cantidad'] - r['revit_q_crudo'])}",
        "derivado",
        "Cuánto se separa lo facturado de lo modelado, sumando el ceil y los dos factores.",
        "intermedio"))
    if r["precio_unitario"]:
        P.append(_paso("Cantidad facturable", "T", "Total de la partida", r["total"], "L",
            "total = cantidad × precio_unitario",
            f"{_fmt(r['cantidad'])} × {_fmt(r['precio_unitario'])} = {_fmt(r['total'])}",
            "services/pricing.recalcular_partida",
            "El precio unitario NO se toca aquí — viene del motor de pricing (ADR-003). "
            "Este paso sólo cierra el impacto en dinero del takeoff.", "resultado"))

    P.append(_paso("Verificación", "ok_f", "Factores sin comportamiento silencioso",
        r["ok_factores"], "",
        "f_e ≠ 0 y f_f ≠ 0 y ambos > 0 y revit_q entero",
        f"fe={r['factor_e_crudo']} · ff={r['factor_f_crudo']} · ceil Δ={_fmt(r['delta_ceil'])}",
        "auditoría de fórmulas",
        "Falla cuando algún factor fue reinterpretado (0→1), es negativo, o el ceil movió "
        "la cantidad. Ninguno de los tres casos es un error del código — los tres son "
        "invisibles, que es el problema.", "check"))

    for p in P:
        if p["tipo"] != "input" and p["latex"] is None:
            p["latex"] = LATEX_BY_FORMULA_PARTIDAS.get(p["formula"])

    constantes = [
        {"simbolo": "f_default", "latex": r"f_{default} = 1.0", "valor": FACTOR_DEFAULT, "unidad": "",
         "desc": "Valor al que _safe_factor colapsa cualquier factor nulo o 0. Fuente del comportamiento silencioso."},
    ]

    meta = {
        "dominio": "partidas_cantidad",
        "norma": "— (regla de negocio, no normativa)",
        "riesgo": "ALTO — define la cantidad que se factura",
        "cumple_normativa": r["ok_factores"],
        "advertencias": r["advertencias"],
        "nota_norma": ("No hay norma que gobierne estos factores: son criterio de obra. "
                       "Por eso el requisito es que sean VISIBLES, no que cumplan un límite."),
    }
    if meta_extra:
        meta.update(meta_extra)
    return {"meta": meta, "pasos": P, "constantes": constantes, "resultado": r}
