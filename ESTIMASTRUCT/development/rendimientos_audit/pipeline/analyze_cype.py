#!/usr/bin/env python
# -*- coding: utf-8 -*-
import re

with open(r'D:\GitHub\EstimBot\ConsuConstructEstimBot\ESTIMASTRUCT\development\rendimientos_audit\pipeline\data\downloads\cype_obra_nueva.html', encoding='utf-8') as f:
    html = f.read()

# Find all links
links = re.findall(r'href="([^"]*)"', html)
print("All links:")
for l in links:
    print(f"  {l}")

print("\n\nSearching for chapter/unit patterns...")
# Search for chapter patterns
chapters = re.findall(r'(cap[ií]tulo|chapter|partida|unidad de obra)[^<>]*', html, re.IGNORECASE)
for c in chapters[:20]:
    print(f"  {c[:200]}")

# Search for data attributes or JS data
data_attrs = re.findall(r'data-[^=]+="[^"]*"', html)
print("\nData attributes:")
for d in data_attrs[:30]:
    print(f"  {d}")

# Look for script data
scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
for i, s in enumerate(scripts[:10]):
    if 'capitulo' in s.lower() or 'partida' in s.lower() or 'precio' in s.lower():
        print(f"\nScript {i} (relevant): {s[:500]}")