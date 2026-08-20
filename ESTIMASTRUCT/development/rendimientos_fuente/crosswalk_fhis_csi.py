#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
crosswalk_fhis_csi.py  —  goal-21068 (rol estimastruct)

Etapa 3 del plan aprobado (goal-21065 §4): CROSSWALK actividad FHIS -> division
CSI del catalogo EstimaStruct, a tabla intermedia (staging). No toca produccion.

Requiere: data/rendimientos_fuente.db (correr antes parse_fhis_index.py).

Produce:
  - tabla `crosswalk_fhis_csi` en rendimientos_fuente.db
  - data/crosswalk_fhis_csi.csv
  - data/cobertura_report.md  (cobertura FHIS vs las 375 fichas del catalogo vivo)

Metodo del mapeo:
  El capitulo mayor FHIS (F01..F55) es la llave del crosswalk contra las 23
  divisiones CSI/MasterFormat que EstimaStruct usa como llave por partida
  (backend/csi_utils.py). Es el MISMO nivel al que goal-21061 mapeo CSI<->ICMS,
  pero ahora contra una fuente que SI tiene rendimientos. Un capitulo FHIS puede
  repartirse en >1 division CSI (p.ej. concreto: cimentacion vs superestructura);
  se marca la division primaria + notas de reparto.

Confianza:
  alta  = capitulo FHIS cae limpio en 1 division CSI
  media = se reparte por descripcion de partida (concreto, plomeria, etc.)
"""
import os
import csv
import sqlite3
import json

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
DB = os.path.join(DATA, "rendimientos_fuente.db")
# catalogo vivo de fichas (para medir cobertura). Solo LECTURA.
FICHAS = os.path.join(
    HERE, "..", "Template2_Updated", "v1.3", "fichas", "fichas_v1.3.json"
)

# Divisiones CSI/MasterFormat como las nombra EstimaStruct (csi_utils).
CSI_DIV = {
    "01": "General Requirements",
    "02": "Existing Conditions / Demolicion",
    "03": "Concrete",
    "04": "Masonry",
    "05": "Metals",
    "07": "Thermal & Moisture Protection",
    "08": "Openings",
    "09": "Finishes",
    "11": "Equipment",
    "12": "Furnishings",
    "22": "Plumbing",
    "26": "Electrical",
    "31": "Earthwork",
    "32": "Exterior Improvements",
    "33": "Utilities",
}

# Crosswalk capitulo FHIS -> (division CSI primaria, [divisiones secundarias],
#                             confianza, nota de reparto)
CROSSWALK = {
    "F01": ("02", ["31"], "media", "Limpieza/demolicion (02) + corte/conformacion/acarreo (31 Earthwork)"),
    "F02": ("03", ["31"], "media", "Cimentacion de concreto (03 substructure); excavacion asociada -> 31"),
    "F03": ("03", [],     "alta",  "Solera/castillo/columna/viga/losa = estructura de concreto"),
    "F04": ("04", ["03"], "media", "Paredes de bloque/ladrillo/adobe (04); pared de concreto reforzado -> 03"),
    "F05": ("03", [],     "alta",  "Concreto y acero de refuerzo genericos"),
    "F06": ("09", [],     "alta",  "Afinado/azulejo/curado = acabados"),
    "F07": ("09", [],     "alta",  "Pisos = acabados"),
    "F08": ("07", ["09"], "media", "Techos/canaletas (07 Moisture); cielo falso -> 09 Finishes"),
    "F09": ("03", [],     "alta",  "Losas de concreto = estructura"),
    "F10": ("22", ["33"], "media", "Tuberia agua potable interior (22); redes de sitio -> 33 Utilities"),
    "F11": ("22", ["33"], "media", "Cajas/tanque septico/letrina/pozo = saneamiento (22/33)"),
    "F12": ("08", ["10"], "media", "Contramarcos/ventaneria/balcones (08 Openings); divisiones -> 10 Specialties"),
    "F13": ("05", ["03"], "media", "Apoyos de neopreno = accesorio estructural (05/03)"),
    "F14": ("32", [],     "alta",  "Cercos/malla ciclon/postes = obra exterior"),
    "F15": ("32", ["33"], "media", "Pavimentos/adoquin/bordillo (32); base vial -> 33"),
    "F16": ("33", [],     "alta",  "Alcantarillado sanitario = utilities"),
    "F17": ("09", [],     "alta",  "Pinturas = acabados"),
    "F18": ("01", [],     "alta",  "Direccion de obra = requisitos generales/indirectos"),
    "F19": ("32", ["33"], "media", "Cunetas (32 exterior) y rejillas de drenaje (33)"),
    "F20": ("22", [],     "alta",  "Aparatos sanitarios = plomeria"),
    "F21": ("26", [],     "alta",  "Instalacion electrica e iluminacion"),
    "F22": ("22", ["33"], "media", "Drenaje pluvial: bajantes (22) y tragantes de sitio (33)"),
    "F23": ("22", ["07", "33"], "media", "Valvulas/obra hidraulica (22/33); impermeabilizacion -> 07"),
    "F24": ("22", ["33"], "media", "Disipadores de mamposteria en obra hidraulica"),
    "F25": ("31", [],     "alta",  "Horas maquina pesada = movimiento de tierra"),
    "F26": ("31", [],     "alta",  "Remocion/carga con maquinaria = earthwork"),
    "F27": ("22", [],     "alta",  "Bajantes PVC = plomeria pluvial"),
    "F28": ("05", ["03"], "media", "Pasamanos/asta HG (05 Metals); gradas de concreto -> 03"),
    "F30": ("32", ["05"], "media", "Puentes colgantes peatonales = obra especial exterior/metalica"),
    "F50": ("12", [],     "alta",  "Mobiliario escolar = furnishings"),
    "F51": ("01", ["12"], "media", "Material didactico/alimentacion = suministro social (fuera de obra fisica)"),
    "F52": ("02", ["31"], "media", "Ensayos de suelos = existing conditions/testing"),
    "F53": ("31", [],     "alta",  "Alquiler de maquinaria = earthwork"),
    "F54": ("32", ["12"], "media", "Juegos infantiles/mobiliario de sitio = exterior/furnishings"),
    "F55": ("32", ["12"], "media", "Mobiliario urbano (bancas/faroles) = exterior/furnishings"),
}


def csi_division(csi_code):
    """'03 30 00' / '033000' / '03' -> '03'. Toma los 2 primeros digitos."""
    if not csi_code:
        return None
    digits = "".join(ch for ch in str(csi_code) if ch.isdigit())
    return digits[:2] if len(digits) >= 2 else None


def build_crosswalk(con):
    cur = con.cursor()
    cur.executescript("""
    DROP TABLE IF EXISTS crosswalk_fhis_csi;
    CREATE TABLE crosswalk_fhis_csi (
        capitulo_fhis   TEXT PRIMARY KEY,
        capitulo_nombre TEXT,
        n_actividades   INTEGER,
        n_activas       INTEGER,
        csi_div_primaria TEXT,
        csi_div_nombre  TEXT,
        csi_div_secundarias TEXT,
        confianza       TEXT,
        nota            TEXT
    );
    """)
    # conteos por capitulo
    counts = {}
    for cap, n, act in cur.execute("""
        select capitulo, count(*), sum(case when inhabilitada=0 then 1 else 0 end)
        from fhis_actividad group by capitulo
    """):
        counts[cap] = (n, act)

    rows = []
    for cap in sorted(counts):
        n, act = counts[cap]
        name = con.execute(
            "select capitulo_nombre from fhis_actividad where capitulo=? limit 1",
            (cap,)).fetchone()[0]
        prim, secs, conf, nota = CROSSWALK.get(cap, (None, [], "sin_mapeo", ""))
        rows.append((
            cap, name, n, act, prim,
            CSI_DIV.get(prim, "?") if prim else None,
            ",".join(secs), conf, nota,
        ))
    cur.executemany(
        "INSERT INTO crosswalk_fhis_csi VALUES (?,?,?,?,?,?,?,?,?)", rows)
    con.commit()
    return rows


def coverage_report(con, rows):
    """Cobertura: cada division CSI usada en el catalogo vivo -> tiene fuente FHIS?"""
    fichas = json.load(open(os.path.abspath(FICHAS), encoding="utf-8"))
    cat_div = {}
    for f in fichas:
        d = csi_division(f.get("csi", ""))
        if d:
            cat_div[d] = cat_div.get(d, 0) + 1

    # divisiones cubiertas por el crosswalk FHIS (primaria + secundarias)
    fhis_divs = set()
    for r in rows:
        if r[4]:
            fhis_divs.add(r[4])
        for s in (r[6].split(",") if r[6] else []):
            if s:
                fhis_divs.add(s)

    lines = []
    lines.append("# goal-21068 — Cobertura FHIS -> catalogo EstimaStruct (STAGING)\n")
    lines.append("**Rol:** estimastruct · **Fuente:** FHIS Manual de Rendimientos "
                 "2003-11 (Cred. BM 3443-HO) · via Quercusoft index\n")
    lines.append("**Estado:** tabla intermedia construida, cero escritura a "
                 "produccion. Poblar valores numericos = gated a 2o OK.\n")
    lines.append("\n## 1. Volumen adquirido\n")
    tot = con.execute("select count(*) from fhis_actividad").fetchone()[0]
    act = con.execute(
        "select count(*) from fhis_actividad where inhabilitada=0").fetchone()[0]
    lines.append(f"- Actividades FHIS parseadas: **{tot}** "
                 f"(activas {act} / inhabilitadas {tot-act})")
    lines.append(f"- Capitulos FHIS mapeados a CSI: **{len(rows)}** de {len(rows)}")
    lines.append(f"- Filas de rendimiento por recurso: **0** "
                 f"(pendiente extraccion PDF, gated)\n")

    lines.append("\n## 2. Cobertura por division CSI del catalogo vivo (375 fichas v1.3)\n")
    lines.append("| CSI div | Nombre | # fichas catalogo | FHIS cubre? |")
    lines.append("|---|---|---:|---|")
    covered = gap = 0
    for d in sorted(cat_div):
        ok = d in fhis_divs
        covered += ok
        gap += (not ok)
        lines.append(f"| {d} | {CSI_DIV.get(d,'(no en mapa CSI base)')} "
                     f"| {cat_div[d]} | {'SI' if ok else 'NO — hueco'} |")
    lines.append(f"\n**Cobertura:** {covered}/{len(cat_div)} divisiones CSI del "
                 f"catalogo tienen fuente FHIS. Huecos: {gap}.")
    lines.append("Los huecos son el segmento de edificacion vertical fina que "
                 "goal-21065 §3 ya preveia rellenar con **Suarez Salazar**.\n")

    lines.append("\n## 3. Crosswalk capitulo FHIS -> division CSI\n")
    lines.append("| Cap FHIS | Nombre | #act (act) | CSI prim | Secundarias | Conf | Nota |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in rows:
        lines.append(f"| {r[0]} | {r[1]} | {r[2]} ({r[3]}) | "
                     f"{r[4]} {r[5] or ''} | {r[6] or '-'} | {r[7]} | {r[8]} |")

    lines.append("\n## 4. Frontera (lo que NO se hizo — gate de produccion)\n")
    lines.append("- **No se poblo ni un valor de rendimiento** en el catalogo. "
                 "`rendimiento_fuente` esta vacia por diseno.")
    lines.append("- Poblar exige: (a) extraer los valores numericos de las fichas "
                 "escaneadas del PDF FHIS, (b) 2o OK explicito de David, "
                 "(c) confirmar a que BD escribe el backend activo "
                 "(SQLite versionada del repo, no Postgres — memoria split-brain).")
    lines.append("- Precios NO se tocan: se montan al final desde CHICO 2025/2026.\n")

    out = os.path.join(DATA, "cobertura_report.md")
    open(out, "w", encoding="utf-8").write("\n".join(lines))
    return out, covered, len(cat_div), gap


def write_csv(rows):
    out = os.path.join(DATA, "crosswalk_fhis_csi.csv")
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["capitulo_fhis", "capitulo_nombre", "n_actividades",
                    "n_activas", "csi_div_primaria", "csi_div_nombre",
                    "csi_div_secundarias", "confianza", "nota"])
        w.writerows(rows)
    return out


def main():
    con = sqlite3.connect(DB)
    rows = build_crosswalk(con)
    csv_out = write_csv(rows)
    rep, cov, total, gap = coverage_report(con, rows)
    con.close()
    print(f"[XWALK] capitulos mapeados : {len(rows)}")
    print(f"[XWALK] cobertura CSI       : {cov}/{total} divisiones (huecos: {gap})")
    print(f"[XWALK] crosswalk CSV       : {csv_out}")
    print(f"[XWALK] reporte cobertura   : {rep}")


if __name__ == "__main__":
    main()
