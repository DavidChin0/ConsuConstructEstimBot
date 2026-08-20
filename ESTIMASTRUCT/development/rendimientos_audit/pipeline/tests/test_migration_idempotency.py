#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests de migracion e idempotencia de rendimiento_audit (goal-21170).

Verifica sobre una BD SQLite temporal (nunca toca D:\\EstimaStruct\\data\\estimacion.db):
  1. La migracion (MIGRATION_SQL de create_audit_table.py) es idempotente:
     ejecutarla 2 veces no rompe ni duplica.
  2. La UNIQUE(partida_id, fuente, recurso_tipo, fuente_codigo, fecha_consulta)
     impide duplicar la misma actividad+fuente+recurso+referencia.
  3. INSERT OR IGNORE respeta la clave de idempotencia.

Ejecutar: D:\\LLM\\python\\python.exe -m pytest tests -q
"""
import os
import sys
import sqlite3
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PIPELINE = os.path.join(HERE, "..")
if PIPELINE not in sys.path:
    sys.path.insert(0, PIPELINE)

from create_audit_table import MIGRATION_SQL  # noqa: E402


def _tmp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    con = sqlite3.connect(path)
    return con, path


def _row(partida_id="p1", fuente="FHIS", tipo="MANO_OBRA", codigo="F013001", fecha="2026-08-20"):
    return (partida_id, "02 21 13", "TRAZADO", "m2", fuente, "ed",
            codigo, "https://x", "62", fecha, tipo, "TOPOGRAFO", 0.005,
            "JRD", 0.005, "directo", "semantico", 0.5, "ev", "alcance", "h", "n")


def test_migracion_idempotente():
    con, path = _tmp_db()
    try:
        cur = con.cursor()
        cur.executescript(MIGRATION_SQL)
        con.commit()
        cur.executescript(MIGRATION_SQL)  # segunda pasada
        con.commit()
        cur.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='rendimiento_audit'")
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT COUNT(*) FROM rendimiento_audit")
        assert cur.fetchone()[0] == 0
    finally:
        con.close()
        os.remove(path)


def test_unique_impide_duplicado():
    con, path = _tmp_db()
    try:
        cur = con.cursor()
        cur.executescript(MIGRATION_SQL)
        cur.execute("INSERT INTO rendimiento_audit (partida_id, partida_clave_csi, partida_descripcion, "
                    "partida_unidad, fuente, fuente_edicion, fuente_codigo, fuente_url, fuente_pagina, "
                    "fecha_consulta, recurso_tipo, recurso_descripcion, coeficiente_nativo, unidad_nativa, "
                    "coeficiente_normalizado, formula_conversion, tipo_match, confianza, evidencia, "
                    "condiciones_alcance, hash_insumo, notas_discrepancia) VALUES "
                    "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", _row())
        try:
            cur.execute("INSERT INTO rendimiento_audit (partida_id, partida_clave_csi, partida_descripcion, "
                        "partida_unidad, fuente, fuente_edicion, fuente_codigo, fuente_url, fuente_pagina, "
                        "fecha_consulta, recurso_tipo, recurso_descripcion, coeficiente_nativo, unidad_nativa, "
                        "coeficiente_normalizado, formula_conversion, tipo_match, confianza, evidencia, "
                        "condiciones_alcance, hash_insumo, notas_discrepancia) VALUES "
                        "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", _row())
            raised = False
        except sqlite3.IntegrityError:
            raised = True
        assert raised, "el UNIQUE deberia rechazar el duplicado"
        cur.execute("SELECT COUNT(*) FROM rendimiento_audit")
        assert cur.fetchone()[0] == 1
    finally:
        con.close()
        os.remove(path)


def test_insert_or_ignore_idempotente():
    con, path = _tmp_db()
    try:
        cur = con.cursor()
        cur.executescript(MIGRATION_SQL)
        cols = ("partida_id, partida_clave_csi, partida_descripcion, partida_unidad, fuente, "
                "fuente_edicion, fuente_codigo, fuente_url, fuente_pagina, fecha_consulta, recurso_tipo, "
                "recurso_descripcion, coeficiente_nativo, unidad_nativa, coeficiente_normalizado, "
                "formula_conversion, tipo_match, confianza, evidencia, condiciones_alcance, hash_insumo, "
                "notas_discrepancia")
        sql = f"INSERT OR IGNORE INTO rendimiento_audit ({cols}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
        cur.execute(sql, _row())
        cur.execute(sql, _row())
        con.commit()
        cur.execute("SELECT COUNT(*) FROM rendimiento_audit")
        assert cur.fetchone()[0] == 1
    finally:
        con.close()
        os.remove(path)


def test_distinta_fuente_no_duplica_ignorado():
    """Misma partida+recurso+referencia pero distinta fuente se conserva por separado."""
    con, path = _tmp_db()
    try:
        cur = con.cursor()
        cur.executescript(MIGRATION_SQL)
        cols = ("partida_id, partida_clave_csi, partida_descripcion, partida_unidad, fuente, "
                "fuente_edicion, fuente_codigo, fuente_url, fuente_pagina, fecha_consulta, recurso_tipo, "
                "recurso_descripcion, coeficiente_nativo, unidad_nativa, coeficiente_normalizado, "
                "formula_conversion, tipo_match, confianza, evidencia, condiciones_alcance, hash_insumo, "
                "notas_discrepancia")
        sql = f"INSERT OR IGNORE INTO rendimiento_audit ({cols}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
        cur.execute(sql, _row(fuente="FHIS"))
        cur.execute(sql, _row(fuente="SUAREZ_SALAZAR"))
        con.commit()
        cur.execute("SELECT COUNT(*) FROM rendimiento_audit")
        assert cur.fetchone()[0] == 2
    finally:
        con.close()
        os.remove(path)