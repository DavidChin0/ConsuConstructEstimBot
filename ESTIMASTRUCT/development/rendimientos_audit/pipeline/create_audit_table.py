#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Crear tabla de auditoría de rendimientos en la BD canónica (goal-21170).
Migración idempotente para poblar datos comparativos de rendimiento.
"""
import sqlite3
import os

DB = r"D:\EstimaStruct\data\estimacion.db"

MIGRATION_SQL = """
-- Tabla comparativa/auditable de rendimientos (no sobrescribe tablas de precios)
CREATE TABLE IF NOT EXISTS rendimiento_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    -- Clave de idempotencia: actividad+fuente+recurso+referencia
    partida_id TEXT NOT NULL,           -- FK a partida.id (actividad EstimaStruct)
    partida_clave_csi TEXT NOT NULL,    -- código CSI de la partida
    partida_descripcion TEXT NOT NULL,  -- descripción de la actividad
    partida_unidad TEXT NOT NULL,       -- unidad de la actividad
    fuente TEXT NOT NULL,               -- FHIS | SUAREZ_SALAZAR | CYPE_HN
    fuente_edicion TEXT,                -- edición/año/ISBN cuando aplique
    fuente_codigo TEXT,                 -- código exacto (ficha FHIS, página libro, URL CYPE)
    fuente_url TEXT NOT NULL,           -- URL online verificada
    fuente_pagina TEXT,                 -- página/ficha/tabla
    fecha_consulta TEXT NOT NULL,       -- fecha de consulta ISO
    recurso_tipo TEXT NOT NULL,         -- MANO_OBRA | EQUIPO (maquinaria)
    recurso_descripcion TEXT NOT NULL,  -- descripción del recurso
    coeficiente_nativo REAL NOT NULL,   -- coeficiente en unidad nativa de la fuente
    unidad_nativa TEXT NOT NULL,        -- unidad nativa de la fuente
    coeficiente_normalizado REAL NOT NULL, -- coeficiente normalizado a unidad de partida
    formula_conversion TEXT,            -- fórmula de conversión explícita
    tipo_match TEXT NOT NULL,           -- exacto | semantico | manual
    confianza REAL NOT NULL,            -- 0.0-1.0
    evidencia TEXT,                     -- evidencia textual/JSON
    condiciones_alcance TEXT,           -- condiciones/alcance de la actividad
    hash_insumo TEXT,                   -- hash del archivo fuente (PDF, HTML, etc)
    notas_discrepancia TEXT,            -- notas de discrepancia
    UNIQUE(partida_id, fuente, recurso_tipo, fuente_codigo, fecha_consulta)
);

-- Índices para consultas frecuentes
CREATE INDEX IF NOT EXISTS idx_rendimiento_audit_partida ON rendimiento_audit(partida_id);
CREATE INDEX IF NOT EXISTS idx_rendimiento_audit_fuente ON rendimiento_audit(fuente);
CREATE INDEX IF NOT EXISTS idx_rendimiento_audit_recurso ON rendimiento_audit(recurso_tipo);
CREATE INDEX IF NOT EXISTS idx_rendimiento_audit_csi ON rendimiento_audit(partida_clave_csi);
"""

def main():
    con = sqlite3.connect(DB)
    cur = con.cursor()
    
    # Ejecutar migración
    cur.executescript(MIGRATION_SQL)
    con.commit()
    
    # Verificar
    cur.execute("PRAGMA table_info(rendimiento_audit)")
    print("Tabla rendimiento_audit creada/verificada:")
    for r in cur.fetchall():
        print(f"  {r[1]} {r[2]} {'NOT NULL' if r[3] else ''} {'PK' if r[5] else ''}")
    
    cur.execute("SELECT COUNT(*) FROM rendimiento_audit")
    print(f"Filas actuales: {cur.fetchone()[0]}")
    
    con.close()
    print("Migración completada.")

if __name__ == "__main__":
    main()