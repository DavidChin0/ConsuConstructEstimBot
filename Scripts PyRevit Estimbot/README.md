# Scripts PyRevit Estimbot

Paquete de scripts de automatización para Revit / pyRevit usado por Estimbot.

## Contenido

- `step1_keywords/xlsx_to_revit_keynotes.py`
- `step6_quantities/107_ExportSchedules.py`
- `step6_quantities/update_quantities.py`

## Uso

Estos scripts están pensados para ejecutarse dentro de pyRevit o desde el entorno de automatización de Revit.

### Exportar schedules

El script `107_ExportSchedules.py` exporta schedules a CSV.

Variables opcionales:

- `ESTIMBOT_PYREVIT_ROOT`
- `ESTIMBOT_PYREVIT_SCHEDULES_DIR`

### Actualizar cantidades

El script `update_quantities.py` toma el CSV más reciente de `step6_quantities` y actualiza la base Excel.

Variables opcionales:

- `ESTIMBOT_PYREVIT_ROOT`
- `ESTIMBOT_PYREVIT_SCHEDULES_DIR`
- `ESTIMBOT_PYREVIT_BD_PATH`
- `ESTIMBOT_PYREVIT_OUTPUT_DIR`

### Convertir keynotes

El script `xlsx_to_revit_keynotes.py` convierte una tabla de keynotes en un archivo `.txt` compatible con Revit.

## Estructura esperada

```text
Scripts PyRevit Estimbot/
  README.md
  step1_keywords/
    xlsx_to_revit_keynotes.py
  step6_quantities/
    107_ExportSchedules.py
    update_quantities.py
```

## Notas

- Los scripts ya no dependen de rutas fijas de una máquina concreta.
- Si no se definen variables de entorno, usan rutas locales relativas al paquete.
- Las carpetas de salida deben existir o serán creadas al ejecutar los scripts.

