#!/usr/bin/env python
# -*- coding: utf-8 -*-
import re

with open(r'D:\GitHub\EstimBot\ConsuConstructEstimBot\ESTIMASTRUCT\development\rendimientos_audit\pipeline\data\downloads\cype_info.html', encoding='utf-8') as f:
    html = f.read()

# Search for coefficients, labor, machinery patterns
patterns = ['coeficiente', 'mano de obra', 'maquinaria', 'rendimiento', 'h/m', 'hombre', 'precio unitario']
for p in patterns:
    matches = re.findall(rf'[^<>]*{p}[^<>]*', html, re.IGNORECASE)
    if matches:
        print(f'\nPattern "{p}" ({len(matches)} matches):')
        for m in matches[:5]:
            print(f'  {m[:300]}')