"""Carga un keynotes.txt (generado por generate_keynotes.py) en la KeynoteTable
del documento Revit activo — vía Revit API, sin pasar por el diálogo de UI
(Manage → Keynoting Settings → Browse).

Run vía execute_revit_code (o revit_mcp.pipe.helpers.execute_code) — IronPython
2.7 dentro de Revit/pyRevit. NOT run standalone con Python normal.

PROBLEMA QUE RESUELVE (descubierto 2026-08-02, goal-20171):
El pipeline dibujar-desde-DB (build_generic_element_schema.py + creación de
assemblies) setea KEYNOTE_PARAM directo en cada Type — pero eso NO llena la
KeynoteTable del documento (la tabla que mapea código→texto descriptivo,
Manage → Keynoting Settings). Sin la tabla cargada, audit_keynotes.py no tiene
con qué comparar el TEXTO del keynote y todo sale RED aunque el código CSI
esté perfecto. Verificado en vivo: 0 GREEN / 600 RED antes de cargar la tabla,
103 GREEN / 497 RED después (mismo modelo, mismo catálogo).

API real (no documentada en el SDK como flujo típico — encontrada por
reflexión sobre DB.KeynoteTable/DB.ExternalResourceReference, Revit 2024+):
  1. DB.ExternalResourceTypes.BuiltInExternalResourceTypes.KeynoteTable
     -> el "tipo de recurso" que Revit espera para un archivo de keynotes.
  2. DB.ModelPathUtils.ConvertUserVisiblePathToModelPath(path)
     -> convierte un path de Windows normal a ModelPath (formato interno).
  3. DB.ExternalResourceReference.CreateLocalResource(doc, resourceType,
     modelPath, DB.PathType.Absolute)
     -> arma la referencia al archivo externo.
  4. DB.KeynoteTable.GetKeynoteTable(doc).LoadFrom(ref, None)
     -> carga de verdad. Devuelve ExternalResourceLoadStatus ("Success" si OK).

GOTCHA: LoadFrom espera un ExternalResourceReference, NO un string de path
plano — pasar el path directo tira TypeError. El segundo argumento
(loadResults) puede ser None si no interesa capturar warnings/errores
detallados de la carga.

Uso: reemplazar TXT_PATH abajo antes de mandar el CODE, o adaptar para
recibir el path como parámetro si se llama desde un wrapper Python.
"""
CODE = r'''
import json
import Autodesk.Revit.DB as DB

doc = __revit__.ActiveUIDocument.Document
txt_path = r"TXT_PATH_PLACEHOLDER"

resource_type = DB.ExternalResourceTypes.BuiltInExternalResourceTypes.KeynoteTable
model_path = DB.ModelPathUtils.ConvertUserVisiblePathToModelPath(txt_path)
path_type = DB.PathType.Absolute

ref = DB.ExternalResourceReference.CreateLocalResource(doc, resource_type, model_path, path_type)

kt = DB.KeynoteTable.GetKeynoteTable(doc)
status = kt.LoadFrom(ref, None)

print(json.dumps({"load_status": str(status)}))
'''


def build_code(txt_path: str) -> str:
    """Devuelve el CODE con el path real embebido, listo para execute_code()."""
    escaped = txt_path.replace("\\", "\\\\")
    return CODE.replace("TXT_PATH_PLACEHOLDER", escaped)
