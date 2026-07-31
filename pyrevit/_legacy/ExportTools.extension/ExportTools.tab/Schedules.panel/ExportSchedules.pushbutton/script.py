# -*- coding: utf-8 -*-
"""
ExportSchedules - Exporta schedules nativos de Revit a CSV para EstimAStruct.
Delega toda la logica a PYR_S5_exportar_schedules.py.
"""
import sys

SCRIPTS_DIR = r"D:\OneDrive\Bots\Estimbot\scripts"
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import PYR_S5_exportar_schedules as s5
s5.main()
