#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests del parser FHIS (goal-21170) con fixtures pequenos.

Fixture: una ficha tipo del Manual de Rendimientos FHIS 2003-11 (formato de
pagina verificada en el PDF fuente, pag. 62: ficha F013001 "TRAZADO CON
TEODOLITO"). Ejecutar: D:\\LLM\\python\\python.exe -m pytest tests -q
"""
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PIPELINE = os.path.join(HERE, "..")
if PIPELINE not in sys.path:
    sys.path.insert(0, PIPELINE)

from parse_fhis_fichas import parse_ficha, parse_value  # noqa: E402

FICHA_TRAZADO = """Fondo Hondureño de Inversion Social
Unidad de Control de Costos
Direccion de Proyectos
Fichas x Actividad
TRAZADO CON TEODOLITO
F013001
Actividad
M.L.
Unidad
Materiales
Rendimiento
Desperdicio
Unidad
MN-F2301001
CLAVOS
0.007
LB
MN-F2901001
MADERA RUSTICA DE PINO
0.191
PIE T
Mano de Obra
Rendimiento
Unidad
OC-F01014
TOPOGRAFO
0.005
JRD
ON-F01002
CADENERO
0.005
JDR
ON-F01003
PEON
0.005
JDR
Herramienta y Equipo
Rendimiento
Unidad
HE-F04003
TEODOLITO
0.005
DIA
Pag:
61"""


def test_parse_value_coma_y_punto():
    assert parse_value("0,005") == 0.005
    assert parse_value("5.000") == 5.0
    assert parse_value("50.000") == 50.0
    assert parse_value("abc") is None


def test_parse_ficha_extrae_codigo():
    f = parse_ficha(FICHA_TRAZADO.split("\n"))
    assert f is not None
    assert f["ficha_codigo"] == "F013001"
    assert f["descripcion"] == "TRAZADO CON TEODOLITO"
    assert f["unidad_actividad"] == "M.L."


def test_parse_ficha_secciones_y_valores():
    f = parse_ficha(FICHA_TRAZADO.split("\n"))
    # el parser conserva la capitalizacion del PDF (Materiales / Mano de Obra /
    # Herramienta y Equipo); el tipo normalizado se deriva al aplanar.
    secciones = {s["seccion"].upper(): s["rows"] for s in f["secciones"]}
    assert "MATERIALES" in secciones
    assert "MANO DE OBRA" in secciones
    assert "HERRAMIENTA Y EQUIPO" in secciones

    mano = secciones["MANO DE OBRA"]
    assert len(mano) == 3
    topografo = next(r for r in mano if r["recurso_codigo"] == "OC-F01014")
    assert topografo["recurso_desc"] == "TOPOGRAFO"
    assert topografo["valor"] == 0.005
    assert topografo["unidad"] == "JRD"

    equipo = secciones["HERRAMIENTA Y EQUIPO"]
    teodolito = next(r for r in equipo if r["recurso_codigo"] == "HE-F04003")
    assert teodolito["valor"] == 0.005
    assert teodolito["unidad"] == "DIA"


def test_parse_ficha_ignora_pagina_y_encabezados():
    f = parse_ficha(FICHA_TRAZADO.split("\n"))
    # "Pag:" y "61" no deben quedar como filas de recurso
    total_rows = sum(len(s["rows"]) for s in f["secciones"])
    assert total_rows == 6  # 2 materiales + 3 mano de obra + 1 equipo (fixture)
    descs = [r["recurso_desc"] for s in f["secciones"] for r in s["rows"]]
    assert "PAG:" not in [d.upper() for d in descs]
    assert "61" not in descs


def test_parse_ficha_sin_ficha_devuelve_none():
    assert parse_ficha(["texto", "sin", "codigo", "F de ficha"]) is None