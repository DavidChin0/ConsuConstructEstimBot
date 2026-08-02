"""Sincroniza CSI keynote + marca (Type Mark / instance Mark) desde un proyecto
Revit de REFERENCIA (real, con datos correctos) hacia un template/proyecto
NUEVO que cargó las mismas familias pero perdió los valores CSI/marca — típico
después de `LoadFamily` en un template vacío (las familias vienen con el
keynote de fábrica del vendor, no el CSI de EstimaStruct).

Run vía execute_revit_code (o revit_mcp.pipe.helpers.execute_code) — IronPython
2.7 dentro de Revit/pyRevit, con AMBOS documentos (referencia + destino)
abiertos en la misma sesión de Revit.

ESTRATEGIA (3 pasadas, en este orden — descubierto en vivo 2026-08-02,
goal-20147/20173/20149):

1. **Match exacto (familia, nombre de tipo)**: la forma más precisa. Falla
   cuando el tipo del destino quedó con el nombre genérico de fábrica (no el
   nombre que tenía en el proyecto de referencia) — típico en familias
   multi-tamaño (perfiles de acero AISC/CISC, sanitarios con variantes).

2. **Match por familia sola, SOLO si el destino tiene exactamente 1 tipo bajo
   esa familia** Y el proyecto de referencia tiene un único par (keynote,marca)
   real para esa familia (sin ambigüedad). Cubre el caso más común: familias
   de un solo tamaño (puertas/ventanas/luminarias vendor) donde el tipo nunca
   se duplicó ni renombró.

3. **`fase1_sync_marks`** (el mismo que corre el botón pyRevit "Sync Marks",
   ver `EstimBot.extension/EstimBot.tab/EstimaStruct.panel/Sync Marks.pushbutton`):
   una vez que los Types tienen el keynote real, sincroniza materiales,
   muros/pisos (vía csi_to_codigo.json), y — el paso que se pierde fácil —
   la INSTANCIA de puertas/ventanas (`ALL_MODEL_MARK`), que es lo que el tag
   en planta realmente lee, no el TypeMark del tipo.

GOTCHA real (2026-08-02): un tag en un View de Revit NO se refresca solo
cuando la API cambia un parámetro por afuera de una transacción de UI. Después
de escribir, llamar la tool `refresh_view` (o el usuario cambia de vista y
vuelve) para ver el cambio reflejado — si no, parece que "no pegó" cuando en
realidad el dato ya está bien (confirmar siempre leyendo el parámetro de
vuelta antes de asumir que falló).

4. **`pass4_struct_design_match`**: perfiles estructurales (columnas/vigas de
   acero, catálogo AISC/CISC). GOTCHA real descubierto 2026-08-02: el primer
   intento de cargar estos perfiles cargó la variante MÉTRICA (prefijo `M_`,
   ej `M_HSS Square-Column`, `M_W Shapes-Column`) mientras el proyecto de
   referencia usa la variante IMPERIAL (sin prefijo, ej `HSS Square-Column`,
   `W Shapes-Column`) — nombre de FAMILIA distinto de raíz, pass1/pass2 nunca
   iban a matchear aunque los tipos no se hubieran renombrado. Fix: cargar
   `C:/ProgramData/Autodesk/RVT 2027/Libraries/English-Imperial/US/...`
   (no `English/...`) para las familias de acero/madera/concreto-viga.
   Además, incluso con la familia correcta, el proyecto de referencia
   prefija la marca antes de la designación real
   (ej. tipo `"C1 HSS6X6X3/16"` en vez de `"HSS6X6X3/16"`) — pass4 extrae
   la designación AISC/HSS con regex y matchea por substring normalizado
   dentro de la misma familia.

Familias/tipos que TODAVÍA no matchean con ninguna pasada: columnas de
concreto rectangulares (familia paramétrica `Columna Rectangular de Concreto
Reforzado` en la referencia / `M_Concrete-Rectangular-Column` en el destino
— no es un catálogo de tipos con nombre AISC, hay que crear/duplicar tipos
con Width/Depth reales, ej R1 15x15cm .. P4 70x70cm, 16 tipos) y perfiles
descritos con nomenclatura no estándar en el nombre (ej `"WF 12"x10"x53
Lbs (W310x73)"`, `"Viga IPR 7"x5"x6mm (W180x22)"` — no matchean el regex de
pass4, requieren mapeo manual).

Uso: pegar CODE en execute_revit_code con REFERENCE_TITLE/TARGET_TITLE
reemplazados, o llamar build_code(reference_title, target_title,
csi_to_codigo_path).
"""
CODE_TEMPLATE = r'''
import io, json, os
from collections import defaultdict
import Autodesk.Revit.DB as DB
import unicodedata

def A(s):
    if s is None:
        return None
    try:
        return unicodedata.normalize("NFKD", unicode(s)).encode("ascii", "ignore")
    except Exception:
        return str(s)

app = __revit__.Application
reference = None
target = None
for d in app.Documents:
    if d.Title == "REFERENCE_TITLE_PLACEHOLDER":
        reference = d
    if d.Title == "TARGET_TITLE_PLACEHOLDER":
        target = d

KEY_PARAM = DB.BuiltInParameter.KEYNOTE_PARAM
TYPE_MARK = DB.BuiltInParameter.ALL_MODEL_TYPE_MARK
INST_MARK = DB.BuiltInParameter.ALL_MODEL_MARK
COMPOUND = (DB.WallType, DB.FloorType, DB.RoofType, DB.CeilingType)

def elem_name(e):
    try:
        return DB.Element.Name.__get__(e)
    except Exception:
        try:
            return e.Name
        except Exception:
            return None

def get_kn(t):
    p = t.get_Parameter(KEY_PARAM)
    v = p.AsString() if p else None
    return v.strip() if v else None

def get_tm(t):
    p = t.get_Parameter(TYPE_MARK)
    v = p.AsString() if p else None
    return v.strip() if v else None

def sp(elem, bip, val):
    if elem is None or not val:
        return False
    p = elem.get_Parameter(bip)
    if not p or p.IsReadOnly:
        return False
    if p.AsString() == val:
        return False
    try:
        p.Set(val)
        return True
    except Exception:
        return False

stats = {"pass1_pair_match": 0, "pass2_family_only": 0, "pass3_inst_sync": 0, "pass4_struct_design_match": 0}

# --- PASADA 1: match exacto (familia, tipo) ---
pair_map = {}
for t in DB.FilteredElementCollector(reference).WhereElementIsElementType().ToElements():
    if isinstance(t, COMPOUND):
        continue
    fam = getattr(t, "FamilyName", None)
    name = elem_name(t)
    kn = get_kn(t)
    if not fam or not name or not kn:
        continue
    pair_map[(fam, name)] = (kn, get_tm(t) or "")

target_types_by_fam = defaultdict(list)
for t in DB.FilteredElementCollector(target).WhereElementIsElementType().ToElements():
    if isinstance(t, COMPOUND):
        continue
    fam = getattr(t, "FamilyName", None)
    name = elem_name(t)
    if not fam or not name:
        continue
    target_types_by_fam[fam].append(t)
    key = (fam, name)
    if key in pair_map:
        kn, tm = pair_map[key]
        c1 = sp(t, KEY_PARAM, kn)
        c2 = sp(t, TYPE_MARK, tm)
        if c1 or c2:
            stats["pass1_pair_match"] += 1

# --- PASADA 2: familia sola, solo si target tiene 1 unico tipo Y referencia
#     tiene un unico (keynote,marca) real (sin ambiguedad) ---
fam_pairs = defaultdict(set)
for t in DB.FilteredElementCollector(reference).WhereElementIsElementType().ToElements():
    if isinstance(t, COMPOUND):
        continue
    fam = getattr(t, "FamilyName", None)
    kn = get_kn(t)
    if not fam or not kn:
        continue
    fam_pairs[fam].add((kn, get_tm(t) or ""))
unambiguous = {f: list(p)[0] for f, p in fam_pairs.items() if len(p) == 1}

for fam, types in target_types_by_fam.items():
    if len(types) != 1 or fam not in unambiguous:
        continue
    kn, tm = unambiguous[fam]
    t = types[0]
    c1 = sp(t, KEY_PARAM, kn)
    c2 = sp(t, TYPE_MARK, tm)
    if c1 or c2:
        stats["pass2_family_only"] += 1

# --- PASADA 3: sync instancia (ALL_MODEL_MARK) = TypeMark del tipo, para
#     puertas/ventanas placed -- lo que el tag en planta realmente lee ---
for cat in (DB.BuiltInCategory.OST_Doors, DB.BuiltInCategory.OST_Windows):
    for inst in DB.FilteredElementCollector(target).OfCategory(cat)\
            .WhereElementIsNotElementType().ToElements():
        etype = target.GetElement(inst.GetTypeId())
        if not etype:
            continue
        tm_val = get_tm(etype)
        if not tm_val:
            continue
        if sp(inst, INST_MARK, tm_val):
            stats["pass3_inst_sync"] += 1

# --- PASADA 4: perfiles estructurales (columnas/vigas) donde la referencia
#     prefijo la marca antes de la designacion AISC/HSS real, ej.
#     "C1 HSS6X6X3/16" en vez de "HSS6X6X3/16". Extrae la designacion via
#     regex y matchea por substring normalizado dentro de la MISMA familia
#     (family names ya deben coincidir exacto -- si no, cargar la variante
#     imperial correcta de la libreria, ver gotcha de unidades) ---
import re
DESIGN_RE = re.compile(
    r'(HSS\s?[\d.]+\s?[Xx]\s?[\d.]+\s?[Xx]\s?[\d/./]+'
    r'|W\s?\d+\s?[Xx]\s?[\d.]+'
    r'|C\s?\d+\s?[Xx]\s?[\d.]+'
    r'|MC\s?\d+\s?[Xx]\s?[\d.]+)'
)
# WF DxWx##Lbs -> el depth y el peso YA son la designacion imperial real,
# solo hay que reformatear (descubierto 2026-08-02, marcas C8/C9/C10):
# "WF 12\"x10\"x53 Lbs (W310x73)" -> "W12X53" (la parte metrica en
# parentesis NO es directamente convertible, se ignora)
WF_RE = re.compile(r'WF\s*(\d+)"?\s*[Xx]\s*\d+"?\s*[Xx]\s*(\d+)\s*Lbs', re.IGNORECASE)
# "W 6\"x12lbx6m" (VA-1 style, sin "Lbs" separado, sin segundo ancho) ->
# depth=6 peso=12 -> "W6X12"
W_LB_RE = re.compile(r'\bW\s*(\d+)"?\s*[Xx]\s*(\d+)\s*lb', re.IGNORECASE)
# HSS sin prefijo dentro de familia HSS-* (ej "STR-15 2x2x1/4" en familia
# "HSS-Hollow Structural Section-Column") -> reconstruye con prefijo HSS
BARE_HSS_RE = re.compile(r'\b(\d+(?:\.\d+)?)\s?[Xx]\s?(\d+(?:\.\d+)?)\s?[Xx]\s?([\d/]+)\b')

def norm_design(s):
    return re.sub(r'\s+', '', s).upper() if s else None

def extract_design(name, fam=None):
    wf = WF_RE.search(name)
    if wf:
        return "W%sX%s" % (wf.group(1), wf.group(2))
    wl = W_LB_RE.search(name)
    if wl:
        return "W%sX%s" % (wl.group(1), wl.group(2))
    m = DESIGN_RE.search(name)
    if m:
        return m.group(1)
    if fam and fam.upper().startswith("HSS"):
        bh = BARE_HSS_RE.search(name)
        if bh:
            return "HSS%sX%sX%s" % (bh.group(1), bh.group(2), bh.group(3))
    return None

STRUCT_CATS = (DB.BuiltInCategory.OST_StructuralColumns, DB.BuiltInCategory.OST_StructuralFraming)

ref_struct = []
for cat in STRUCT_CATS:
    for t in DB.FilteredElementCollector(reference).OfCategory(cat).WhereElementIsElementType().ToElements():
        fam = getattr(t, "FamilyName", None)
        name = elem_name(t)
        kn = get_kn(t)
        tm = get_tm(t)
        if not fam or not name or not kn:
            continue
        design = extract_design(name, fam)
        if not design:
            continue
        ref_struct.append((fam, norm_design(design), kn, tm or ""))

target_struct_by_fam = defaultdict(dict)
for cat in STRUCT_CATS:
    for t in DB.FilteredElementCollector(target).OfCategory(cat).WhereElementIsElementType().ToElements():
        fam = getattr(t, "FamilyName", None)
        name = elem_name(t)
        if not fam or not name:
            continue
        target_struct_by_fam[fam][norm_design(name)] = t

for fam, design, kn, tm in ref_struct:
    t = target_struct_by_fam.get(fam, {}).get(design)
    if not t:
        continue
    c1 = sp(t, KEY_PARAM, kn)
    c2 = sp(t, TYPE_MARK, tm)
    if c1 or c2:
        stats["pass4_struct_design_match"] += 1

print(json.dumps(stats))
'''


def build_code(reference_title, target_title):
    return (CODE_TEMPLATE
            .replace("REFERENCE_TITLE_PLACEHOLDER", reference_title)
            .replace("TARGET_TITLE_PLACEHOLDER", target_title))
