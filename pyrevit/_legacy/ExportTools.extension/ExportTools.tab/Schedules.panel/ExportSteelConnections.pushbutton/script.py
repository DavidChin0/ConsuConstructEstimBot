# -*- coding: utf-8 -*-
"""
ExportSteelConnections - Cuenta nodos viga-columna y exporta CSV para EstimAStruct.
Delega toda la logica a count_connections.py.
"""
import sys

SCRIPTS_DIR = r"D:\OneDrive\Bots\Estimbot\scripts"
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import count_connections
count_connections.main()
