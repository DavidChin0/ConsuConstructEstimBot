#!/usr/bin/env python
# -*- coding: utf-8 -*-
import re

with open(r'D:\GitHub\EstimBot\ConsuConstructEstimBot\ESTIMASTRUCT\development\rendimientos_audit\pipeline\data\downloads\cype_cimentaciones.html', encoding='utf-8') as f:
    html = f.read()

# Find all links
links = re.findall(r'href="([^"]*)"', html)
print("Links in chapter page:")
for l in links:
    if 'unidad' in l.lower() or 'precio' in l.lower() or '.html' in l:
        print(f"  {l}")

# Search for table or data patterns
print("\nSearching for unit of work patterns...")
# Look for table rows
rows = re.findall(r'<tr[^>]*>.*?</tr>', html, re.DOTALL)
print(f"Table rows found: {len(rows)}")
for r in rows[:10]:
    print(f"  {r[:300]}")

# Look for precio/coeficiente patterns
precios = re.findall(r'(precio|coeficiente|mano de obra|maquinaria|rendimiento)[^<>]*', html, re.IGNORECASE)
for p in precios[:20]:
    print(f"  {p[:200]}")

# Search for data in script tags
scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
for i, s in enumerate(scripts):
    if any(kw in s.lower() for kw in ['precio', 'coeficiente', 'unidad', 'mano de obra', 'maquinaria', 'data', 'json']):
        print(f"\nScript {i} (relevant): {s[:1000]}")