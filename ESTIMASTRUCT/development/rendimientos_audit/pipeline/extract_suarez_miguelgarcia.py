#!/usr/bin/env python
# -*- coding: utf-8 -*-
import re
import json

with open(r'D:\GitHub\EstimBot\ConsuConstructEstimBot\ESTIMASTRUCT\development\rendimientos_audit\pipeline\data\downloads\suarez_miguelgarcia.html', encoding='utf-8') as f:
    html = f.read()

# Extract tables
tables = re.findall(r'<table[^>]*>.*?</table>', html, re.DOTALL)
print(f'Tables found: {len(tables)}')

all_rows = []
for i, table in enumerate(tables):
    # Parse rows
    rows = re.findall(r'<tr[^>]*>.*?</tr>', table, re.DOTALL)
    print(f'\nTable {i}: {len(rows)} rows')
    for row in rows[:5]:
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
        cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
        if cells:
            print(f'  {cells}')
            if len(cells) >= 4:
                all_rows.append(cells)

print(f'\nTotal data rows: {len(all_rows)}')
# Save as JSON for further processing
with open(r'D:\GitHub\EstimBot\ConsuConstructEstimBot\ESTIMASTRUCT\development\rendimientos_audit\pipeline\data\suarez_miguelgarcia_rows.json', 'w', encoding='utf-8') as f:
    json.dump(all_rows, f, ensure_ascii=False, indent=2)