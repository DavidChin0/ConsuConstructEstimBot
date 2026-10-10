"""Reproduce plan.tsv de 1fca7285 (57 filas, 159 dias, 2026-10-05 a 2027-04-07) sin tocar BD.
Entradas: crono_in.json (57 partidas) y plan.tsv, ambas fijadas por sha256 en el paquete."""
import json, os
from datetime import date
from backend import cronograma as e

HERE = os.path.dirname(__file__)
FIX = os.environ.get("CRONO_FIX_DIR", HERE)


def _plan():
    rows = [l.rstrip("\n").split("\t") for l in open(os.path.join(FIX, "plan.tsv"), encoding="utf-8")][1:]
    return rows


def _run(**kw):
    inp = json.load(open(os.path.join(FIX, "crono_in.json"), encoding="utf-8"))
    cat = e.cargar_catalogo(e._catalogo_path("v1.3"))
    return e.construir_cronograma(inp, catalogo=cat, **kw)


def test_serie_reproduce_plan():
    f = _run(fecha_arranque=date(2026, 10, 5), serie=True)
    plan = _plan()
    assert len(f) == len(plan) == 57
    assert sum(x["duracion_dias"] for x in f) == 159
    for x, r in zip(f, plan):
        fin = e._suma_dias_laborales(date.fromisoformat(x["fecha_inicio"]), max(0, x["duracion_dias"] - 1)).isoformat()
        assert (x["orden"] + 1, x["partida_id"], x["fecha_inicio"], fin, x["duracion_dias"], x["fuente"]) == \
               (int(r[0]), r[1], r[5], r[6], int(r[7]), r[12])
    assert f[0]["fecha_inicio"] == "2026-10-05"


def test_serie_cadena_sin_domingos():
    f = _run(fecha_arranque=date(2026, 10, 5), serie=True)
    prev = None
    for x in f:
        ini = date.fromisoformat(x["fecha_inicio"]); assert ini.weekday() != 6
        if prev:
            assert ini == e._suma_dias_laborales(prev, 1)
        prev = e._suma_dias_laborales(ini, max(0, x["duracion_dias"] - 1))


def test_defaults_sin_cambio():
    a = _run(); b = _run(fecha_arranque=None, serie=False)
    assert [x["fecha_inicio"] for x in a] == [x["fecha_inicio"] for x in b]
    assert a[0]["fecha_inicio"] == "2026-06-15"      # FECHA_DEFAULT intacta
    assert sum(x["duracion_dias"] for x in a) == 159
