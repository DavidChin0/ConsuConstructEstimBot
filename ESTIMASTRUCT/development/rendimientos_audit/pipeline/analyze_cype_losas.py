#!/usr/bin/env python
# -*- coding: utf-8 -*-
import re

with open(r'D:\GitHub\EstimBot\ConsuConstructEstimBot\ESTIMASTRUCT\development\rendimientos_audit\pipeline\data\downloads\cype_losas.html', encoding='utf-8') as f:
    html = f.read()

# Search for actual unit of work data - look for patterns like "unidad de obra", prices, coefficients
patterns = ['unidad de obra', 'precio unitario', 'coeficiente', 'mano de obra', 'maquinaria', 'rendimiento', 'h/m', 'hombre', 'máquina', 'equipo', 'ud.', 'ud ', 'm2', 'm3', 'ml', 'kg']
for p in patterns:
    matches = re.findall(rf'[^<>]*{re.escape(p)}[^<>]*', html, re.IGNORECASE)
    if matches:
        print(f"\nPattern '{p}' ({len(matches)} matches):")
        for m in matches[:10]:
            print(f"  {m[:300]}")

# Also look for list items that might be units of work
list_items = re.findall(r'<li[^>]*>.*?</li>', html, re.DOTALL)
print(f"\n\nList items: {len(list_items)}")
for li in list_items[:20]:
    if any(kw in li.lower() for kw in ['precio', 'coef', 'mano', 'maqui', 'rendim']):
        print(f"  {li[:300]}")

# Look for divs with specific classes that might contain data
data_divs = re.findall(r'<div[^>]*class="[^"]*(?:item|unit|price|coef|data)[^"]*"[^>]*>.*?</div>', html, re.DOTALL | re.IGNORECASE)
print(f"\n\nData divs: {len(data_divs)}")
for d in data_divs[:10]:
    print(f"  {d[:300]}")