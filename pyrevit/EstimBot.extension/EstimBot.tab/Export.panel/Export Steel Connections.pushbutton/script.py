# -*- coding: utf-8 -*-
"""
EstimBot - Export Steel Connections by Node (C10)

Boton delgado: delega TODA la logica a count_connections.py (fuente unica).
Edita la logica en:  D:\\GitHub\\EstimBot\\ConsuConstructEstimBot\\pyrevit\\scripts\\count_connections.py
"""
import sys

SCRIPTS_DIR = r"D:\GitHub\EstimBot\ConsuConstructEstimBot\pyrevit\scripts"
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import count_connections
reload(count_connections)  # IronPython 2.7: recarga si pyRevit cachea el modulo
count_connections.main()
