#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests del parser de filas Suarez Salazar (goal-21170).

Verifica el patron de las filas extraidas de la fuente (e.g.
'50.000 m2 / Jor' -> rendimiento 50.0 en m2/Jor y su inverso) tal como lo
usa insert_suarez_audit.py, con fixtures pequenos. Nota: estas filas NO se
insertan en la BD canonica (fuente NO_VERIFICADO); el test valida solo la
logica de parsing. Ejecutar: D:\\LLM\\python\\python.exe -m pytest tests -q
"""
import re

PATRON = re.compile(r"([\d.,]+)\s*(\w+)\s*/\s*(\w+)")


def parse_rendimiento_str(s):
    """Devuelve (valor, unidad_salida, unidad_entrada) o (None,)*3."""
    m = PATRON.search(s)
    if not m:
        return None, None, None
    return float(m.group(1).replace(",", ".")), m.group(2), m.group(3)


def test_parse_rendimiento_50_m2_por_jor():
    val, out, inp = parse_rendimiento_str("50.000 m2 / Jor")
    assert val == 50.0
    assert out == "m2"
    assert inp == "Jor"


def test_parse_rendimiento_ton_por_jor():
    val, out, inp = parse_rendimiento_str("0.170 ton / Jor")
    assert val == 0.17
    assert out == "ton"
    assert inp == "Jor"


def test_parse_inverso():
    val, _, _ = parse_rendimiento_str("0.020 Jor / m2")
    assert val == 0.02


def test_parse_formato_coma():
    val, _, _ = parse_rendimiento_str("1,050 m2 / Jor")
    assert val == 1.05


def test_parse_sin_formato_devuelve_none():
    assert parse_rendimiento_str("sin datos") == (None, None, None)