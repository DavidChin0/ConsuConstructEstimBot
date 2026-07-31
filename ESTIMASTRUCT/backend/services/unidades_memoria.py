# -*- coding: utf-8 -*-
"""
Conversión de unidades ETABS → motor — memoria narrada (2026-07-31).

Módulo ciego C-10 de `docs/auditoria_formulas_mapa_estructura.md` — riesgo MEDIO
por probabilidad, ALTO por consecuencia: `seccion_ficha.factores_unidad()` aplica
un factor a **cada número de fuerza y momento** que entra desde ETABS. Un error
aquí no produce un resultado raro en una partida: escala TODO el diseño
estructural por ~9.8× de forma uniforme, lo cual es exactamente el tipo de error
que se ve "consistente" y por eso no se detecta.

LO QUE ESTABA CIEGO
-------------------
1. **El fallback silencioso.** `factores_unidad` normaliza el texto quitando todo
   lo que no sea letra y busca en `UNIDAD_FACTORES`. Si la unidad NO está en el
   diccionario (`kip`, `lb`, `N`, `MN`, un typo, un string vacío…) devuelve
   **kgf** sin decir nada. Quien exporta de ETABS en kN y elige/escribe una
   unidad no reconocida obtiene fuerzas 9.80665× menores de lo real, y el diseño
   entero sale del lado inseguro.
2. **El factor mismo.** Ni el import ni ninguna memoria muestran por qué el Pu
   que se está diseñando es 0.001× o 0.102× el número del reporte de ETABS.
3. **Fuerza y momento comparten factor.** Es correcto (el brazo va en metros en
   ambos flujos) pero no está escrito en ningún lado, así que nadie puede
   verificarlo.

ADR-003: no hay motor nuevo. Se llama `seccion_ficha.factores_unidad()` — la
misma función que usan los imports de ETABS en producción — y se narra su salida.

Contrato de salida:  {meta, pasos[], constantes[], resultado{}}
"""
import re

from backend.calculo_estructural import _fmt, _ascii_to_latex
from backend.seccion_ficha import factores_unidad, UNIDAD_FACTORES, KN_POR_T

UNIDAD_DEFAULT = "kgf"

UNIDAD_DESC = {
    "kgf": "Kilogramo-fuerza. Flujo estándar del despacho (ETABS configurado 'kgf, m, C').",
    "kg":  "Alias de kgf. ETABS a veces rotula 'kg' aunque sea fuerza.",
    "ton": "Tonelada-fuerza métrica. Ya es la unidad interna del motor.",
    "t":   "Alias de ton.",
    "kn":  "Kilonewton. Unidad SI; requiere dividir por g = 9.80665 para llegar a t-fuerza.",
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


LATEX_BY_FORMULA_UNID = {
    "P[t] = P_entrada × ff":
        r"P_{[t]} = P_{ETABS}\cdot f_f",
    "M[t·m] = M_entrada × fm":
        r"M_{[t\cdot m]} = M_{ETABS}\cdot f_m",
    "ff(kN) = 1 / 9.80665":
        r"f_f^{kN} = \dfrac{1}{9.80665}",
    "ff(kgf) = 1 / 1000":
        r"f_f^{kgf} = \dfrac{1}{1000}",
    "error_relativo = ff_elegido / ff_correcto":
        r"e = \dfrac{f_f^{elegido}}{f_f^{correcto}}",
}


def _norm_unidad(u: str) -> str:
    return re.sub(r"[^a-z]", "", (u or UNIDAD_DEFAULT).lower())


# ─────────────────────────────────────────────────────────────────────────────
# MEMORIA NARRADA — el motor es seccion_ficha.factores_unidad, aquí sólo se lee
# ─────────────────────────────────────────────────────────────────────────────
def memoria_factores_unidad(unidad_entrada: str = "kgf",
                            p_entrada: float = 0.0, m_entrada: float = 0.0,
                            meta_extra: dict | None = None) -> dict:
    """Narra la conversión de unidades de un import ETABS. `p_entrada`/`m_entrada`
    son un valor de ejemplo (fuerza y momento) para ver el efecto real."""
    crudo = unidad_entrada if unidad_entrada is not None else ""
    norm = _norm_unidad(crudo)
    reconocida = norm in UNIDAD_FACTORES
    ff, fm = factores_unidad(crudo)

    p_t = float(p_entrada or 0) * ff
    m_tm = float(m_entrada or 0) * fm

    # Qué pasaría si la unidad correcta fuera la otra gran candidata (kN vs kgf):
    ff_kn = UNIDAD_FACTORES["kn"][0]
    ff_kgf = UNIDAD_FACTORES["kgf"][0]
    razon_kn_kgf = ff_kn / ff_kgf     # = 1000/9.80665 ≈ 101.97

    advertencias = []
    if not reconocida:
        advertencias.append(
            f"Unidad {crudo!r} (normalizada '{norm}') NO está en UNIDAD_FACTORES "
            f"({', '.join(sorted(UNIDAD_FACTORES))}). `factores_unidad` cayó en el default "
            f"'{UNIDAD_DEFAULT}' SIN avisar. Si los datos de ETABS venían en kN, cada fuerza "
            f"quedó {razon_kn_kgf:.2f}× fuera de escala y TODO el diseño está mal de forma "
            "uniforme — el tipo de error que se ve consistente y no se detecta revisando "
            "un resultado suelto.")
    if norm in ("ton", "t"):
        advertencias.append(
            "Unidad 't/ton': factor = 1.0, no hay conversión. Verificar que el reporte de "
            "ETABS efectivamente esté en tonelada-FUERZA y no en tonelada métrica de masa.")

    P = []
    P.append(_paso("Entrada", "u", "Unidad declarada del reporte ETABS", crudo or "—", "",
        "dato del import", f"unidad = {crudo!r}",
        "POST /diseno/{pid}/import-etabs-*",
        "La unidad que el usuario declara al pegar la tabla de ETABS. Es la única señal que "
        "tiene el sistema: nada en el texto pegado dice en qué unidad están los números.",
        "input"))
    P.append(_paso("Entrada", "u_norm", "Unidad normalizada", norm or "—", "",
        "quitar todo lo que no sea letra + minúsculas",
        f"normalizar({crudo!r}) = '{norm}'",
        "seccion_ficha.factores_unidad:173",
        "Tolerante a mayúsculas, espacios, guiones y símbolos: 'KN-m', 'kN ' y 'kn' llegan "
        "todos a 'kn'. Lo que NO tolera es una unidad que no esté en el diccionario.",
        "intermedio"))
    P.append(_paso("Entrada", "reconocida", "Unidad reconocida por el diccionario",
        reconocida, "", "u_norm ∈ UNIDAD_FACTORES",
        f"'{norm}' {'∈' if reconocida else '∉'} {{{', '.join(sorted(UNIDAD_FACTORES))}}}",
        "seccion_ficha.UNIDAD_FACTORES",
        "⚠ EL check que faltaba. Si es falso, el sistema NO falla ni avisa: asume kgf y sigue. "
        "Éste es el mecanismo exacto por el que un diseño puede salir escalado ~9.8× sin que "
        "nadie lo note.", "check"))

    P.append(_paso("Factores", "f_f", "Factor de fuerza → tonelada-fuerza", ff, "",
        ("ff(kN) = 1 / 9.80665" if norm == "kn" else
         "ff(kgf) = 1 / 1000" if norm in ("kgf", "kg") else "factor tabulado"),
        (f"1 / {KN_POR_T} = {ff:.8f}" if norm == "kn" else
         f"1 / 1000 = {ff:.8f}" if norm in ("kgf", "kg") else f"f_f = {ff:.8f}"),
        "seccion_ficha.UNIDAD_FACTORES",
        UNIDAD_DESC.get(norm, f"Unidad no reconocida — se aplicó el factor de {UNIDAD_DEFAULT}."),
        "resultado"))
    P.append(_paso("Factores", "f_m", "Factor de momento → tonelada-fuerza·metro", fm, "",
        "mismo factor que la fuerza (el brazo ya está en metros)",
        f"f_m = {fm:.8f}",
        "seccion_ficha.UNIDAD_FACTORES",
        "Fuerza y momento comparten factor porque en ambos flujos ETABS reporta el brazo en "
        "metros: sólo cambia la unidad de fuerza. Es correcto, pero no estaba escrito en "
        "ninguna parte y por eso nadie podía verificarlo.", "intermedio"))

    if p_entrada:
        P.append(_paso("Aplicación", "P", "Fuerza convertida", round(p_t, 6), "t",
            "P[t] = P_entrada × ff",
            f"{_fmt(p_entrada, 4)} {norm or UNIDAD_DEFAULT} × {ff:.8f} = {_fmt(p_t, 6)} t",
            "unidad interna del motor",
            "El motor de diseño trabaja SIEMPRE en t y t·m. Este es el número que realmente "
            "entra a §J8, §H1 y a las memorias de acero.", "resultado"))
    if m_entrada:
        P.append(_paso("Aplicación", "M", "Momento convertido", round(m_tm, 6), "t·m",
            "M[t·m] = M_entrada × fm",
            f"{_fmt(m_entrada, 4)} {norm or UNIDAD_DEFAULT}·m × {fm:.8f} = {_fmt(m_tm, 6)} t·m",
            "unidad interna del motor", "Ídem para momentos.", "resultado"))

    P.append(_paso("Sensibilidad", "e", "Error si la unidad real fuera kN y se leyó kgf",
        round(razon_kn_kgf, 4), "×",
        "error_relativo = ff_elegido / ff_correcto",
        f"{ff_kgf:.8f} / {ff_kn:.8f} = 1/{razon_kn_kgf:.2f}  →  factor de error {razon_kn_kgf:.2f}×",
        "derivado",
        f"Elegir kgf cuando los datos venían en kN divide todas las fuerzas por "
        f"{razon_kn_kgf:.2f}: un pedestal con Pu real de 50 t se diseña para 0.49 t. Al revés "
        "(kN cuando eran kgf) sobredimensiona por el mismo factor. Ninguno de los dos casos "
        "produce un número que 'se vea mal'.", "intermedio"))
    P.append(_paso("Sensibilidad", "g", "Constante de conversión kN ↔ t-fuerza", KN_POR_T, "kN/t",
        "1 t-fuerza = 9.80665 kN",
        f"KN_POR_T = {KN_POR_T}",
        "SI (gravedad estándar)",
        "Aceleración de la gravedad estándar. Es todo el origen del factor 9.8 que puede "
        "escalar el diseño.", "input"))

    for p in P:
        if p["tipo"] != "input" and p["latex"] is None:
            p["latex"] = LATEX_BY_FORMULA_UNID.get(p["formula"])

    constantes = [
        {"simbolo": "g", "latex": r"g = 9.80665\ \mathrm{kN/t}", "valor": KN_POR_T, "unidad": "kN/t",
         "desc": "1 tonelada-fuerza = 9.80665 kN. Fuente del riesgo de escala ×9.8."},
        {"simbolo": "u_def", "latex": r"u_{def} = \mathrm{kgf}", "valor": UNIDAD_DEFAULT, "unidad": "",
         "desc": "Unidad a la que cae `factores_unidad` cuando no reconoce la entrada. Fallback SILENCIOSO."},
    ]

    meta = {
        "dominio": "unidades_etabs",
        "norma": "SI — conversión de unidades",
        "riesgo": "MEDIO en probabilidad, ALTO en consecuencia (escala todo el diseño ×9.8)",
        "unidad_entrada": crudo,
        "unidad_normalizada": norm,
        "reconocida": reconocida,
        "cumple_normativa": reconocida,
        "advertencias": advertencias,
        "unidades_validas": sorted(UNIDAD_FACTORES),
        "nota_norma": ("No hay margen de interpretación: la conversión es aritmética exacta. "
                       "El único riesgo es de PROCESO — declarar mal la unidad de origen — y "
                       "el código lo agrava al no fallar cuando no reconoce lo que le dan."),
    }
    if meta_extra:
        meta.update(meta_extra)
    return {"meta": meta, "pasos": P, "constantes": constantes,
            "resultado": {"unidad": crudo, "unidad_norm": norm, "reconocida": reconocida,
                          "factor_fuerza": ff, "factor_momento": fm,
                          "p_t": round(p_t, 6), "m_tm": round(m_tm, 6),
                          "razon_kn_kgf": round(razon_kn_kgf, 6),
                          "advertencias": advertencias}}
