#!/usr/bin/env python3
"""
Test de rutas — Validar que ESTIMASTRUCT funciona sin lanzar servidor
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from app import app

CHECKLIST = {
    "✓ Ruta /": False,
    "✓ Ruta /matrices": False,
    "✓ Ruta /api/matrices": False,
    "✓ Ruta /api/unidades": False,
    "✓ Ruta /health": False,
    "✓ DB_PATH válido": False,
    "✓ Templates existen": False,
}

def test_routes():
    """Prueba todas las rutas sin lanzar servidor."""
    client = app.test_client()

    print("=" * 60)
    print("CHECKLIST: Validación de Rutas ESTIMASTRUCT")
    print("=" * 60)

    # Test 1: Ruta /
    try:
        resp = client.get('/')
        if resp.status_code == 200 and b'<!DOCTYPE html>' in resp.data:
            CHECKLIST["✓ Ruta /"] = True
            print("✓ GET / → 200 OK (HTML devuelto)")
        else:
            print(f"✗ GET / → {resp.status_code} (esperado 200)")
    except Exception as e:
        print(f"✗ GET / → Error: {e}")

    # Test 2: Ruta /matrices
    try:
        resp = client.get('/matrices')
        if resp.status_code == 200:
            CHECKLIST["✓ Ruta /matrices"] = True
            print("✓ GET /matrices → 200 OK")
        else:
            print(f"✗ GET /matrices → {resp.status_code}")
    except Exception as e:
        print(f"✗ GET /matrices → Error: {e}")

    # Test 3: API /api/matrices
    try:
        resp = client.get('/api/matrices')
        if resp.status_code == 200 and resp.content_type == 'application/json':
            CHECKLIST["✓ Ruta /api/matrices"] = True
            print("✓ GET /api/matrices → 200 OK (JSON devuelto)")
        else:
            print(f"✗ GET /api/matrices → {resp.status_code} ({resp.content_type})")
    except Exception as e:
        print(f"✗ GET /api/matrices → Error: {e}")

    # Test 4: API /api/unidades
    try:
        resp = client.get('/api/unidades')
        if resp.status_code == 200 and resp.content_type == 'application/json':
            CHECKLIST["✓ Ruta /api/unidades"] = True
            print("✓ GET /api/unidades → 200 OK (JSON devuelto)")
        else:
            print(f"✗ GET /api/unidades → {resp.status_code}")
    except Exception as e:
        print(f"✗ GET /api/unidades → Error: {e}")

    # Test 5: Health check
    try:
        resp = client.get('/health')
        if resp.status_code == 200 and resp.content_type == 'application/json':
            CHECKLIST["✓ Ruta /health"] = True
            print("✓ GET /health → 200 OK (JSON devuelto)")
        else:
            print(f"✗ GET /health → {resp.status_code}")
    except Exception as e:
        print(f"✗ GET /health → Error: {e}")

    # Test 6: DB_PATH válido
    from app import DB_PATH
    if os.path.exists(DB_PATH):
        CHECKLIST["✓ DB_PATH válido"] = True
        print(f"✓ DB_PATH existe: {DB_PATH}")
    else:
        print(f"✗ DB_PATH no existe: {DB_PATH}")

    # Test 7: Templates existen
    templates_dir = os.path.join(os.path.dirname(__file__), "templates")
    required_templates = ["index.html", "matrices.html"]
    all_exist = all(os.path.exists(os.path.join(templates_dir, t)) for t in required_templates)
    if all_exist:
        CHECKLIST["✓ Templates existen"] = True
        print(f"✓ Templates encontradas: {', '.join(required_templates)}")
    else:
        print(f"✗ Templates faltantes en {templates_dir}")

    print("\n" + "=" * 60)
    print("RESUMEN")
    print("=" * 60)

    passed = sum(1 for v in CHECKLIST.values() if v)
    total = len(CHECKLIST)

    for check, result in CHECKLIST.items():
        status = "PASS" if result else "FAIL"
        print(f"[{status}] {check}")

    print(f"\nTotal: {passed}/{total} pasaron")

    if passed == total:
        print("\n🟢 Frontend ESTIMASTRUCT restaurado correctamente")
        print("   Acceder a: http://localhost:5000/")
        return 0
    else:
        print(f"\n🔴 Fallos detectados ({total - passed})")
        return 1


if __name__ == '__main__':
    sys.exit(test_routes())
