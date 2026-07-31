from pyrevit import revit
import io
path = r"D:\OneDrive\Bots\Estimbot\logs\pyrevit_smoke_test.txt"
handle = io.open(path, 'w', encoding='utf-8')
try:
    doc = revit.doc
    title = doc.Title if doc else 'NO_DOC'
    handle.write(title)
finally:
    handle.close()
