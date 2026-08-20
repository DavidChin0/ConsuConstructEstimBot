#!/usr/bin/env python
# -*- coding: utf-8 -*-
import re

with open(r'D:\GitHub\EstimBot\ConsuConstructEstimBot\ESTIMASTRUCT\development\rendimientos_audit\pipeline\data\downloads\cype_superficiales.html', encoding='utf-8') as f:
    html = f.read()

# Search for table or list patterns
print("Searching for unit of work data...")

# Look for table structure
tables = re.findall(r'<table[^>]*>.*?</table>', html, re.DOTALL)
print(f"Tables found: {len(tables)}")
for t in tables[:3]:
    print(f"  Table: {t[:500]}")

# Look for div with class patterns
divs = re.findall(r'<div[^>]*class="[^"]*"[^>]*>.*?</div>', html, re.DOTALL)
for d in divs:
    if any(kw in d.lower() for kw in ['precio', 'unidad', 'coeficiente', 'mano', 'maquinaria', 'rendimiento']):
        print(f"  Div: {d[:500]}")

# Search for JSON data in scripts
scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
for i, s in enumerate(scripts):
    if any(kw in s.lower() for kw in ['precio', 'coeficiente', 'unidad', 'mano', 'maquinaria', 'data', 'json', 'items']):
        print(f"\nScript {i} (relevant): {s[:2000]}")

# Also search for specific text patterns
patterns = ['unidad de obra', 'precio unitario', 'coeficiente', 'h/m', 'hombre', 'maquina', 'equipo']
for p in patterns:
    matches = re.findall(rf'[^<>]*{p}[^<>]*', html, re.IGNORECASE)
    if matches:
        print(f"\nPattern '{p}':")
        for m in matches[:5]:
            print(f"  {m[:200]}")