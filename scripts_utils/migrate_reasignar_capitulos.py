"""
Migración: reasigna partidas al capítulo CSI correcto en TODOS los presupuestos.
Ejecutar con el backend corriendo en localhost:8000.
"""
import requests

BASE = "http://localhost:8000"

presupuestos = requests.get(f"{BASE}/presupuestos").json()
print(f"Presupuestos encontrados: {len(presupuestos)}\n")

for p in presupuestos:
    pid  = p["id"]
    nombre = p.get("nombre", pid)
    r = requests.post(f"{BASE}/presupuestos/{pid}/reasignar-capitulos")
    if r.ok:
        data = r.json()
        print(f"OK  {nombre[:50]:<50} | movidas={data['partidas_movidas']} | caps_eliminados={data['capitulos_eliminados']}")
    else:
        print(f"ERR {nombre[:50]:<50} | {r.status_code} {r.text[:80]}")

print("\nMigración completa.")
