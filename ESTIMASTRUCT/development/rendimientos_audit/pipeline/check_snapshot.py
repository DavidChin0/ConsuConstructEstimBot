#!/usr/bin/env python
# -*- coding: utf-8 -*-
import json

with open(r'D:\GitHub\EstimBot\ConsuConstructEstimBot\ESTIMASTRUCT\development\rendimientos_audit\pipeline\data\precios_snapshot_latest.json', encoding='utf-8') as f:
    snap = json.load(f)

print('Price invariant hash:', snap['price_invariant']['hash_concat'])
print('Price rows:', snap['price_invariant']['rows_sum'])
print('Tables:', list(snap['price_tables'].keys()))
for t, info in snap['price_tables'].items():
    print(f'  {t}: {info["rows"]} rows, hash={info["sha256"][:16]}...')