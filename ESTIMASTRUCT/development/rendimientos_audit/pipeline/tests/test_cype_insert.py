#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests de insercion CYPE en rendimiento_audit.

Verifica sobre BD temporal:
  1. La insercion de rendimientos CYPE es idempotente (INSERT OR IGNORE).
  2. Se insertan solo coeficientes (no precios).
  3. UNIQUE constraint impide duplicados fuente+codigo+recurso.
"""
import os, sys, sqlite3, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PIPELINE = os.path.join(HERE, "..")
if PIPELINE not in sys.path:
    sys.path.insert(0, PIPELINE)

from create_audit_table import MIGRATION_SQL


def _tmp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    con = sqlite3.connect(path)
    con.executescript(MIGRATION_SQL)
    return con, path


SAMPLE_ROW = dict(
    partida_id="p-cype-test-001",
    partida_clave_csi="03 21 11",
    partida_descripcion="Encofrado y fundido columna de concreto",
    partida_unidad="m²",
    fuente="CYPE_HN",
    fuente_edicion="Generador de Precios Honduras 2026",
    fuente_codigo="EHS010",
    fuente_url="https://honduras.generadordeprecios.info/obra_nueva/Estructuras/Concreto_reforzado/Columnas/EHS010_Columna_rectangular_o_cuadrada_de_c.html",
    fuente_pagina="online",
    fecha_consulta="2026-08-20",
    recurso_tipo="MANO_OBRA",
    recurso_descripcion="Armador de encofrados",
    coeficiente_nativo=5.347,
    unidad_nativa="h/m³",
    coeficiente_normalizado=5.347,
    formula_conversion="5.347 h/m³ (CYPE HN, proyecto referencia)",
    tipo_match="semantico",
    confianza=0.7,
    evidencia="CYPE EHS010: Columna rectangular o cuadrada de concreto reforzado",
    condiciones_alcance="Proyecto de referencia CYPE HN; rendimientos contextuales, no universales.",
    hash_insumo="abc123",
    notas_discrepancia="Match semantico.",
)


def _insert(con, row):
    cols = list(row.keys())
    placeholders = ",".join("?" for _ in cols)
    sql = f"INSERT OR IGNORE INTO rendimiento_audit ({','.join(cols)}) VALUES ({placeholders})"
    cur = con.execute(sql, [row[c] for c in cols])
    return cur.rowcount


def test_cype_insert_basico():
    con, path = _tmp_db()
    rows = _insert(con, SAMPLE_ROW)
    assert rows == 1, "Primera insercion debe insertar 1 fila"
    con.close()
    os.unlink(path)


def test_cype_insert_idempotente():
    con, path = _tmp_db()
    _insert(con, SAMPLE_ROW)
    rows2 = _insert(con, SAMPLE_ROW)
    assert rows2 == 0, "Segunda insercion identica debe ser ignorada (idempotente)"
    cur = con.execute("SELECT COUNT(*) FROM rendimiento_audit WHERE fuente='CYPE_HN'")
    assert cur.fetchone()[0] == 1
    con.close()
    os.unlink(path)


def test_cype_sin_precio():
    """Verifica que las columnas de precio no existen en la tabla."""
    con, path = _tmp_db()
    cur = con.execute("PRAGMA table_info(rendimiento_audit)")
    cols = {r[1] for r in cur.fetchall()}
    precio_cols = {"precio_unitario", "costo", "subtotal", "total", "moneda"}
    assert not precio_cols.intersection(cols), f"Columnas de precio NO deben existir: {precio_cols.intersection(cols)}"
    con.close()
    os.unlink(path)


def test_cype_distinto_recurso_no_duplica():
    """Dos recursos distintos de la misma unidad CYPE son filas separadas."""
    con, path = _tmp_db()
    _insert(con, SAMPLE_ROW)
    row2 = dict(SAMPLE_ROW, recurso_tipo="MAQUINARIA", recurso_descripcion="Vibrador de hormigón", coeficiente_nativo=0.25)
    rows = _insert(con, row2)
    assert rows == 1
    cur = con.execute("SELECT COUNT(*) FROM rendimiento_audit WHERE fuente='CYPE_HN'")
    assert cur.fetchone()[0] == 2
    con.close()
    os.unlink(path)
