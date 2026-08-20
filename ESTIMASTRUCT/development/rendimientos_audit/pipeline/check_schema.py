#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sqlite3

db = r"D:\EstimaStruct\data\estimacion.db"
con = sqlite3.connect(db)
cur = con.cursor()

for table in ['recurso', 'insumo_partida', 'partida', 'capitulo']:
    cur.execute(f'PRAGMA table_info({table})')
    print(f"\n=== {table} ===")
    for r in cur.fetchall():
        print(f"  {r[1]} {r[2]} {'NOT NULL' if r[3] else ''} {'PK' if r[5] else ''}")

con.close()