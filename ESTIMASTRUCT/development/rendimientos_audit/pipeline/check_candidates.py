#!/usr/bin/env python
# -*- coding: utf-8 -*-
import csv

with open(r'D:\GitHub\EstimBot\ConsuConstructEstimBot\ESTIMASTRUCT\development\rendimientos_audit\pipeline\data\candidatos_fhis_catalogo.csv', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    rows = list(reader)
    print(f'Total candidatos: {len(rows)}')
    unique_partidas = set(r['partida_id'] for r in rows)
    print(f'Partidas unicas: {len(unique_partidas)}')
    for r in rows[:10]:
        print(f'  {r["partida_id"]} | {r["clave_csi"]} | {r["partida_desc"][:60]} | ficha:{r["ficha"]} score:{r["score"]}')