# -*- coding: utf-8 -*-
"""
Agregación de miembros de acero por ficha Div 05 — memoria narrada (2026-07-31).

Módulo ciego C-07 de `docs/auditoria_formulas_mapa_estructura.md`. Riesgo BAJO en
plata pero el de mayor COMPLEJIDAD LÓGICA de los siete: no es una fórmula, es una
cadena de decisiones (mapeo, agrupación, envolvente) donde cada paso descarta
información y ninguno de los descartes se ve.

LAS CUATRO COSAS QUE ESTABAN CIEGAS
-----------------------------------
1. **La regla "perfil dual sin rol ⇒ COLUMNA".** Cinco perfiles del catálogo
   (W150X24, W200X36, W200X71, W250X49, W310X73, más el alias W6X16) sirven como
   viga o como columna y mapean a fichas DISTINTAS. Si ETABS no trae el rol, el
   código asume COLUMNA. `agregar_por_ficha` sí emite el aviso en `avisos[]`…
   pero **ese array no se renderiza en ningún lado**. La cantidad se va a la
   ficha C-x en vez de la VA-x, con otros insumos y otro costo, y el usuario
   nunca ve el aviso.
2. **La envolvente D/C.** Cada ficha reporta UN `dc_max` y UN `combo_gobernante`:
   el del miembro peor. Los otros N−1 miembros y sus combos desaparecen. El
   usuario ve "D/C = 0.87 · combo ENV-3" sin saber sobre cuántos miembros se
   tomó ese máximo ni cuán lejos quedó el segundo.
3. **La agrupación por triple clave.** Se agrupa por (ficha, perfil_norm, rol).
   Dos miembros que mapean a la misma ficha pero con perfil normalizado distinto
   generan DOS filas — correcto, pero invisible como criterio.
4. **Los perfiles no mapeados se pierden.** Un perfil fuera de FICHAS_ACERO cae
   en `perfiles_no_mapeados` y su longitud NO entra a ninguna partida: acero real
   del modelo que sencillamente no se presupuesta.

ADR-003 — CUIDADO ESPECIAL AQUÍ: esta memoria NO reagrupa, NO recalcula
longitudes y NO recalcula la envolvente. Llama `agregar_por_ficha(miembros)`, que
es el motor que corre en producción, y luego recorre la lista de miembros SÓLO
para describir estadísticamente lo que el motor ya decidió (cuántos miembros
entraron a cada grupo, cuál fue el segundo D/C). Ninguna cifra de la memoria
sustituye a una del motor: si el motor dice dc_max = 0.87, la memoria muestra
0.87, no un máximo propio.

Contrato de salida:  {meta, pasos[], constantes[], resultado{}}
"""
from backend.calculo_estructural import _fmt, _ascii_to_latex
from backend.acero_ficha import (
    agregar_por_ficha, mapear_perfil_a_ficha, FICHAS_ACERO, DC_LIMITE,
)

# Perfiles duales: los que mapean a dos fichas distintas según el rol.
PERFILES_DUALES = sorted(k for k, v in FICHAS_ACERO.items() if isinstance(v, dict))


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


LATEX_BY_FORMULA_ACERO_FICHA = {
    "L_ficha = Σ longitud de los miembros del grupo":
        r"L_{ficha} = \sum_{i \in grupo} L_i",
    "dc_max = max(dc) del grupo":
        r"DC_{max} = \max_{i \in grupo} DC_i",
    "sobre_esforzado ⇔ dc > 1.0":
        r"DC_i > 1.0",
    "clave_grupo = (ficha, perfil_norm, rol)":
        r"g = (\text{ficha},\ \text{perfil},\ \text{rol})",
    "L_no_mapeada = Σ longitud de perfiles fuera del catálogo":
        r"L_{perdida} = \sum_{p \notin FICHAS} L_p",
    "margen = 1.0 − dc_max":
        r"m = 1.0 - DC_{max}",
}


# ─────────────────────────────────────────────────────────────────────────────
# MEMORIA NARRADA — el motor es acero_ficha.agregar_por_ficha
# ─────────────────────────────────────────────────────────────────────────────
def memoria_agregacion_ficha(miembros: list, meta_extra: dict | None = None) -> dict:
    """Narra la agregación por ficha de una lista de miembros de acero.

    `miembros` = salida del parser de ETABS: dicts con
    {frame, perfil, rol, longitud_mL, dc, combo}. Devuelve {meta, pasos,
    constantes, resultado}. NO toca la BD.
    """
    ms = list(miembros or [])
    if not ms:
        raise ValueError("Se requiere al menos un miembro para narrar la agregación.")

    # ── MOTOR REAL — única fuente de los números agregados ───────────────────
    r = agregar_por_ficha(ms)
    por_ficha = r["por_ficha"]
    sobre = r["sobre_esforzados"]
    no_map = r["perfiles_no_mapeados"]

    # ── Descripción del proceso (NO recálculo): sólo se re-recorre la entrada
    #    para explicar qué decidió el motor sobre cada miembro. Ninguna de estas
    #    cifras reemplaza una del motor.
    duales_sin_rol = []
    dc_por_grupo = {}
    for m in ms:
        perfil = m.get("perfil") or ""
        mapa = mapear_perfil_a_ficha(perfil, m.get("rol") or "")
        if mapa["mapeado"] and mapa["rol_asumido"]:
            duales_sin_rol.append({
                "frame": m.get("frame") or "-", "perfil": perfil,
                "ficha_asignada": mapa["type_mark"],
                "ficha_alternativa": FICHAS_ACERO[mapa["perfil_norm"]]["viga"],
            })
        if mapa["mapeado"] and m.get("dc") is not None:
            clave = (mapa["type_mark"], mapa["perfil_norm"], mapa["rol"])
            dc_por_grupo.setdefault(clave, []).append(
                (float(m["dc"]), m.get("combo") or "", m.get("frame") or "-"))

    long_perdida = sum(float(m.get("longitud_mL") or 0)
                       for m in ms
                       if not mapear_perfil_a_ficha(m.get("perfil") or "",
                                                    m.get("rol") or "")["mapeado"])
    long_total_mapeada = sum(f["longitud_total_mL"] for f in por_ficha)

    advertencias = []
    if duales_sin_rol:
        detalle = ", ".join(f"{d['frame']}·{d['perfil']}→{d['ficha_asignada']}"
                            for d in duales_sin_rol[:6])
        advertencias.append(
            f"{len(duales_sin_rol)} miembro(s) de perfil DUAL llegaron sin rol explícito y se "
            f"asumieron COLUMNA ({detalle}{'…' if len(duales_sin_rol) > 6 else ''}). Cada uno "
            "pudo haber ido a la ficha de VIGA, que tiene otros insumos y otro costo. El motor "
            "sí genera este aviso en `avisos[]` desde siempre — lo que nunca existió es un "
            "lugar donde se muestre.")
    if no_map:
        advertencias.append(
            f"{len(no_map)} miembro(s) con perfil fuera de FICHAS_ACERO "
            f"({', '.join(sorted({x['perfil'] for x in no_map}))[:120]}): "
            f"{long_perdida:.2f} mL de acero del modelo NO entran a ninguna partida. No es un "
            "error de cálculo — es material real que no se presupuesta.")
    if sobre:
        advertencias.append(
            f"{len(sobre)} miembro(s) con D/C > {DC_LIMITE} (AISC 360-16 §H1.1): el modelo "
            "está sobre-esforzado. Presupuestar sobre un diseño que no pasa es documentar "
            "una obra que hay que rediseñar.")

    P = []

    # ── ENTRADA ──────────────────────────────────────────────────────────────
    P.append(_paso("Entrada", "n_miembros", "Miembros recibidos de ETABS", len(ms), "miembros",
        "dato del import", f"n = {len(ms)}",
        "parse_acero_texto / parse_acero_bytes",
        "Filas de la tabla de Steel Frame Design. Cada una trae frame, perfil, rol, longitud, "
        "D/C y combo gobernante.", "input"))
    P.append(_paso("Entrada", "n_duales", "Perfiles duales en el catálogo", len(PERFILES_DUALES),
        "perfiles", "perfiles con dos fichas posibles",
        f"{', '.join(PERFILES_DUALES)}",
        "acero_ficha.FICHAS_ACERO",
        "Estos perfiles sirven como viga O como columna y mapean a fichas Div 05 DISTINTAS. "
        "Todo depende del rol que ETABS haya reportado.", "input"))

    # ── MAPEO PERFIL → FICHA ─────────────────────────────────────────────────
    P.append(_paso("Mapeo perfil → ficha", "n_mapeados", "Miembros con ficha asignada",
        len(ms) - len(no_map), "miembros",
        "perfil normalizado ∈ FICHAS_ACERO",
        f"{len(ms)} − {len(no_map)} = {len(ms) - len(no_map)}",
        "acero_ficha.mapear_perfil_a_ficha",
        "El perfil se normaliza (mayúsculas, sin espacios, sin la equivalencia imperial entre "
        "paréntesis) y se busca en el diccionario de fichas Div 05.", "intermedio"))
    P.append(_paso("Mapeo perfil → ficha", "n_dual_asumido",
        "Miembros duales resueltos por ASUNCIÓN", len(duales_sin_rol), "miembros",
        "perfil dual y rol vacío ⇒ COLUMNA",
        f"{len(duales_sin_rol)} miembro(s) sin rol → ficha de columna",
        "acero_ficha.py:123 (default columna)",
        "⚠ LA REGLA SILENCIOSA. Cuando ETABS no reporta DesignType, el código elige columna. "
        "No es un error — hay que elegir algo — pero es una decisión de diseño tomada por el "
        "software y hasta 2026-07-31 el usuario no tenía forma de enterarse.",
        "check" if duales_sin_rol else "resultado"))
    P.append(_paso("Mapeo perfil → ficha", "L_perdida", "Longitud que NO se presupuesta",
        round(long_perdida, 3), "mL",
        "L_no_mapeada = Σ longitud de perfiles fuera del catálogo",
        f"Σ longitud de {len(no_map)} miembro(s) no mapeado(s) = {_fmt(long_perdida, 3)}",
        "acero_ficha.agregar_por_ficha (perfiles_no_mapeados)",
        "Acero que existe en el modelo y no llega a ninguna partida. Silencioso: el resumen de "
        "importación no lo suma en ninguna parte.",
        "check" if long_perdida > 0 else "intermedio"))

    # ── AGRUPACIÓN ───────────────────────────────────────────────────────────
    P.append(_paso("Agrupación", "g", "Criterio de agrupación", len(por_ficha), "grupos",
        "clave_grupo = (ficha, perfil_norm, rol)",
        f"{len(ms) - len(no_map)} miembros → {len(por_ficha)} grupo(s)",
        "acero_ficha.py:491",
        "Triple clave, no sólo la ficha: dos perfiles distintos que mapean a la misma ficha "
        "producen filas separadas, para no mezclar longitudes de secciones diferentes.",
        "intermedio"))
    P.append(_paso("Agrupación", "L_total", "Longitud total mapeada",
        round(long_total_mapeada, 3), "mL",
        "L_ficha = Σ longitud de los miembros del grupo",
        f"Σ longitud_total_mL de {len(por_ficha)} grupo(s) = {_fmt(long_total_mapeada, 3)}",
        "acero_ficha.agregar_por_ficha",
        "Cantidad que efectivamente se convierte en partidas Div 05.", "takeoff"))

    # ── UN PASO POR FICHA (envolvente) ───────────────────────────────────────
    for f in por_ficha:
        clave = (f["ficha"], f["perfil"], f["rol"])
        lista = sorted(dc_por_grupo.get(clave, []), reverse=True)
        segundo = lista[1] if len(lista) > 1 else None
        frame_gob = lista[0][2] if lista else "-"
        sust = (f"max de {len(lista)} D/C → {_fmt(f['dc_max'], 3)} (frame {frame_gob}, "
                f"combo {f['combo_gobernante'] or '—'})" if lista
                else "sin D/C reportado en el grupo")
        desc = (
            f"Ficha {f['ficha']} · perfil {f['perfil']} · rol {f['rol']} · "
            f"{f['n_miembros']} miembro(s) · {_fmt(f['longitud_total_mL'], 3)} mL. "
            "El D/C que se reporta es el del PEOR miembro del grupo; los otros "
            f"{max(f['n_miembros'] - 1, 0)} y sus combos no se muestran en ningún lado.")
        if segundo:
            desc += (f" Segundo D/C más alto: {segundo[0]:.3f} (frame {segundo[2]}, combo "
                     f"{segundo[1] or '—'}) — la distancia al gobernante indica si la "
                     "envolvente la define un caso aislado o todo el grupo.")
        P.append(_paso("Envolvente D/C por ficha", f"DC[{f['ficha']}]",
            f"{f['ficha']} — {f['perfil']} ({f['rol']})",
            f["dc_max"] if f["dc_max"] is not None else "—", "",
            "dc_max = max(dc) del grupo", sust,
            "AISC 360-16 §H1.1", desc,
            "check" if (f["dc_max"] is not None and f["dc_max"] > DC_LIMITE) else "resultado"))

    # ── VERIFICACIÓN ─────────────────────────────────────────────────────────
    dc_global = max([f["dc_max"] for f in por_ficha if f["dc_max"] is not None] or [0.0])
    P.append(_paso("Verificación", "DC_global", "D/C máximo de todo el import",
        round(dc_global, 3), "",
        "dc_max = max(dc) del grupo",
        f"max sobre {len(por_ficha)} ficha(s) = {_fmt(dc_global, 3)} vs límite {DC_LIMITE}",
        "AISC 360-16 §H1.1",
        "Peor relación demanda/capacidad del modelo importado.", "intermedio"))
    P.append(_paso("Verificación", "m", "Margen contra el límite",
        round(DC_LIMITE - dc_global, 3), "",
        "margen = 1.0 − dc_max",
        f"{DC_LIMITE} − {_fmt(dc_global, 3)} = {_fmt(DC_LIMITE - dc_global, 3)}",
        "AISC 360-16 §H1.1",
        "Negativo = el modelo no pasa.", "intermedio"))
    P.append(_paso("Verificación", "ok_dc", f"Todos los miembros con D/C ≤ {DC_LIMITE}",
        len(sobre) == 0, "",
        "sobre_esforzado ⇔ dc > 1.0",
        f"{len(sobre)} miembro(s) sobre-esforzado(s) de {len(ms)}",
        "AISC 360-16 §H1.1", "Check normativo duro.", "check"))
    P.append(_paso("Verificación", "ok_rol", "Ningún rol asumido por default",
        len(duales_sin_rol) == 0, "",
        "sin perfiles duales sin rol explícito",
        f"{len(duales_sin_rol)} rol(es) asumido(s) como COLUMNA",
        "auditoría de fórmulas",
        "Falla cuando el software eligió por el usuario a qué ficha —y por tanto a qué "
        "costo— se va una cantidad de acero.", "check"))
    P.append(_paso("Verificación", "ok_map", "Todo el acero del modelo llegó a una partida",
        len(no_map) == 0, "",
        "perfiles_no_mapeados = ∅",
        f"{len(no_map)} perfil(es) sin ficha · {_fmt(long_perdida, 3)} mL fuera del presupuesto",
        "auditoría de fórmulas",
        "Falla cuando hay acero modelado que no se presupuesta.", "check"))

    for p in P:
        if p["tipo"] != "input" and p["latex"] is None:
            p["latex"] = LATEX_BY_FORMULA_ACERO_FICHA.get(p["formula"])

    constantes = [
        {"simbolo": "DC_lim", "latex": r"DC_{lim} = 1.0", "valor": DC_LIMITE, "unidad": "",
         "desc": "Relación demanda/capacidad admisible — AISC 360-16 §H1.1."},
        {"simbolo": "n_fichas", "latex": r"n_{FICHAS}", "valor": len(FICHAS_ACERO), "unidad": "perfiles",
         "desc": "Perfiles con ficha Div 05 asignada. Fuera de esta lista, la longitud no se presupuesta."},
        {"simbolo": "n_duales", "latex": r"n_{duales}", "valor": len(PERFILES_DUALES), "unidad": "perfiles",
         "desc": "Perfiles que mapean a dos fichas distintas según el rol. Sin rol ⇒ COLUMNA."},
    ]

    meta = {
        "dominio": "acero_ficha",
        "norma": "AISC 360-16 §H1.1 (límite D/C); fichas Div 05 = catálogo interno",
        "riesgo": "BAJO en plata · ALTO en trazabilidad (decisiones invisibles en cadena)",
        "cumple_normativa": (len(sobre) == 0 and len(duales_sin_rol) == 0 and len(no_map) == 0),
        "advertencias": advertencias,
        "avisos_motor": r["avisos"],
        "n_fichas_generadas": len(por_ficha),
        "nota_norma": ("Aquí no se diseña nada: ETABS ya diseñó y este módulo sólo mapea al "
                       "presupuesto. Por eso el riesgo no es que la fórmula esté mal, sino "
                       "que la cadena de decisiones descarta información en tres puntos "
                       "distintos sin dejar rastro visible."),
    }
    if meta_extra:
        meta.update(meta_extra)
    return {"meta": meta, "pasos": P, "constantes": constantes,
            "resultado": {**r, "longitud_total_mapeada_mL": round(long_total_mapeada, 3),
                          "longitud_no_mapeada_mL": round(long_perdida, 3),
                          "duales_sin_rol": duales_sin_rol,
                          "dc_global": round(dc_global, 3),
                          "advertencias": advertencias}}
