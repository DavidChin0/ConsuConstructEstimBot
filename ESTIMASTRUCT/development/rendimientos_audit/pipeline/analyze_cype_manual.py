#!/usr/bin/env python
# -*- coding: utf-8 -*-
import re

with open(r'D:\GitHub\EstimBot\ConsuConstructEstimBot\ESTIMASTRUCT\development\rendimientos_audit\pipeline\data\downloads\cype_manual.html', encoding='utf-8') as f:
    html = f.read()

# Search for coefficient patterns
patterns = ['coeficiente', 'mano de obra', 'maquinaria', 'rendimiento', 'precio']
for p in patterns:
    matches = re.findall(rf'[^<>]*{p}[^<>]*', html, re.IGNORECASE)
    if matches:
        print(f'Pattern "{p}" ({len(matches)} matches):')
        for m in matches[:3]:
            print(f'  {m[:200]}')
print()

# Look for tables
tables = re.findall(r'<table[^>]*>.*?</table>', html, re.DOTALL)
print(f'Tables: {len(tables)}')
for t in tables[:2]:
    print(t[:1000])