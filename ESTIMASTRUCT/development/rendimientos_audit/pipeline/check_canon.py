#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sqlite3

db = r"D:\EstimaStruct\data\estimacion.db"
con = sqlite3.connect(db)
cur = con.cursor()
cur.execute('SELECT name FROM sqlite_master WHERE type="table" AND name NOT LIKE "sqlite_%" ORDER BY name')
for r in cur.fetchall():
    print(r[0])
con.close()