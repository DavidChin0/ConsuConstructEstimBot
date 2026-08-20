#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
cleanup_suarez_no_verificado.py  -  goal-21170 (rol estimastruct)

Correccion de control de calidad sobre la tabla canónica rendimiento_audit.

Las 10 filas SUAREZ_SALAZAR insertadas en la sesion anterior provienen de
http://miguelgarcia.xyz/rendimientos/ (web personal que republica tablas del
libro de Suarez Salazar). Eso NO cumple el contrato del goal:

  - "Si no se puede verificar [el acceso legitimo al texto], usarlo solo como
     pista bibliografica y buscar otra fuente autorizada."
  - "No usar Scribd/idoc ni copias piratas."
  - "Cada numero debe tener URL online y pagina/ficha/tabla, o quedar como
     NO_VERIFICADO sin insertarse."

Las filas suarez carecen de pagina/tabla del libro (fuente_pagina = 'Tabla web
(indice por capitulos)') y la fuente es una republicacion no autorizada. Por
eso se RETIRAN de la tabla canonica comparativa y la fuente queda documentada
como NO_VERIFICADO en la bitacora. El material fuente (JSON de 59 filas, HTML
descargado, PDF de 43 MB) se conserva en pipeline/data como evidencia.

Este script es IDEMPOTENTE: solo borra filas con la clave exacta
fuente='SUAREZ_SALAZAR' AND fuente_url='http://miguelgarcia.xyz/rendimientos/'.
Antes de borrar vuelca las filas a data/suarez_rows_retiradas.json (rollback).

Correr: D:\\LLM\\python\\python.exe cleanup_suarez_no_verificado.py
"""
import os
import json
import sqlite3

DB = r"D:\EstimaStruct\data\estimacion.db"
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
BACKUP = os.path.join(DATA, "suarez_rows_retiradas.json")

SRC_URL = "http://miguelgarcia.xyz/rendimientos/"


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    cur.execute("""
        SELECT * FROM rendimiento_audit
        WHERE fuente = 'SUAREZ_SALAZAR' AND fuente_url = ?
    """, (SRC_URL,))
    rows = [dict(r) for r in cur.fetchall()]
    print(f"[CLEANUP] filas SUAREZ_SALAZAR a retirar: {len(rows)}")

    if rows:
        with open(BACKUP, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=1)
        print(f"[CLEANUP] backup rollback -> {BACKUP}")

        cur.execute("""
            DELETE FROM rendimiento_audit
            WHERE fuente = 'SUAREZ_SALAZAR' AND fuente_url = ?
        """, (SRC_URL,))
        con.commit()
        print(f"[CLEANUP] filas borradas: {cur.rowcount}")

    cur.execute("SELECT fuente, COUNT(*) FROM rendimiento_audit GROUP BY fuente ORDER BY fuente")
    print("[CLEANUP] estado final rendimiento_audit:")
    for r in cur.fetchall():
        print(f"    {r[0]}: {r[1]}")

    cur.execute("SELECT COUNT(*) FROM rendimiento_audit")
    print(f"[CLEANUP] total: {cur.fetchone()[0]}")
    con.close()


if __name__ == "__main__":
    main()