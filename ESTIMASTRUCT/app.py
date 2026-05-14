#!/usr/bin/env python3
"""
ESTIMASTRUCT Web App - Flask
Interfaz para gestionar matrices y recursos
http://localhost:5000
"""

from flask import Flask, render_template, request, jsonify, send_from_directory
import sqlite3
import os
import json
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_PATH = REPO_ROOT / "frontend"
ESTIMASTRUCT_PATH = REPO_ROOT / "ESTIMASTRUCT"

app = Flask(__name__,
            template_folder=str(ESTIMASTRUCT_PATH / "templates"),
            static_folder=str(FRONTEND_PATH))
DB_PATH = ESTIMASTRUCT_PATH / "estimastruct.db"
API_BASE = os.environ.get("ESTIMASTRUCT_API_BASE", "http://localhost:8002")
ASSET_VERSION = str(int(os.path.getmtime(FRONTEND_PATH / "js" / "app.js")))


def init_db():
    """Crear un esquema mínimo si la base local todavía no existe."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS actividades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo_matriz TEXT,
            descripcion TEXT,
            unidad_matriz TEXT,
            mo_unitario REAL DEFAULT 0,
            ma_unitario REAL DEFAULT 0,
            total_unitario REAL DEFAULT 0
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS recursos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actividad_id INTEGER,
            tipo_recurso TEXT,
            codigo TEXT,
            descripcion TEXT,
            rendimiento REAL DEFAULT 0,
            unidad_recurso TEXT,
            precio_unitario REAL DEFAULT 0,
            precio_total REAL DEFAULT 0
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS unidades (
            codigo TEXT PRIMARY KEY,
            nombre TEXT NOT NULL,
            tipo TEXT NOT NULL,
            activa INTEGER DEFAULT 1
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS importacion_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            total_matrices INTEGER,
            total_recursos INTEGER,
            archivo_origen TEXT,
            status TEXT,
            notas TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    unidades_base = [
        ("global", "Global", "general", 1),
        ("unidad", "Unidad", "general", 1),
        ("pza", "Pieza", "general", 1),
        ("m", "Metro", "longitud", 1),
        ("m2", "Metro cuadrado", "superficie", 1),
        ("m3", "Metro cúbico", "volumen", 1),
        ("kg", "Kilogramo", "peso", 1),
        ("hr", "Hora", "tiempo", 1),
        ("jor", "Jornada", "tiempo", 1),
        ("mes", "Mes", "tiempo", 1),
        ("viaje", "Viaje", "general", 1),
    ]
    cur.executemany(
        "INSERT OR IGNORE INTO unidades (codigo, nombre, tipo, activa) VALUES (?, ?, ?, ?)",
        unidades_base,
    )
    conn.commit()
    conn.close()


init_db()


@app.route('/css/<path:filename>')
def serve_css(filename):
    """Servir archivos CSS desde frontend/css/"""
    return send_from_directory(str(FRONTEND_PATH / 'css'), filename)


@app.route('/js/<path:filename>')
def serve_js(filename):
    """Servir archivos JS desde frontend/js/"""
    return send_from_directory(str(FRONTEND_PATH / 'js'), filename)

def get_db():
    """Conectar a DB"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    """Home - Dashboard"""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM actividades")
    total_matrices = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM recursos")
    total_recursos = cursor.fetchone()[0]

    cursor.execute("""
        SELECT tipo_recurso, COUNT(*) as qty
        FROM recursos
        GROUP BY tipo_recurso
        ORDER BY qty DESC
    """)
    tipos = cursor.fetchall()

    cursor.execute("""
        SELECT codigo_matriz, descripcion, unidad_matriz, total_unitario
        FROM actividades
        ORDER BY total_unitario DESC
        LIMIT 10
    """)
    top_matrices = cursor.fetchall()

    conn.close()

    return render_template('index.html',
                         total_matrices=total_matrices,
                         total_recursos=total_recursos,
                         tipos=tipos,
                         top_matrices=top_matrices,
                         api_base=API_BASE,
                         asset_version=ASSET_VERSION)

@app.route('/api/matrices')
def api_matrices():
    """API - Listar matrices con filtro"""
    conn = get_db()
    cursor = conn.cursor()

    search = request.args.get('search', '')
    limit = request.args.get('limit', 50)

    if search:
        cursor.execute("""
            SELECT id, codigo_matriz, descripcion, unidad_matriz, mo_unitario, ma_unitario, total_unitario
            FROM actividades
            WHERE codigo_matriz LIKE ? OR descripcion LIKE ?
            LIMIT ?
        """, (f'%{search}%', f'%{search}%', limit))
    else:
        cursor.execute("""
            SELECT id, codigo_matriz, descripcion, unidad_matriz, mo_unitario, ma_unitario, total_unitario
            FROM actividades
            LIMIT ?
        """, (limit,))

    matrices = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return jsonify(matrices)

@app.route('/api/matriz/<int:matriz_id>')
def api_matriz_detail(matriz_id):
    """API - Detalles de una matriz"""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, codigo_matriz, descripcion, unidad_matriz, mo_unitario, ma_unitario, total_unitario
        FROM actividades
        WHERE id = ?
    """, (matriz_id,))

    matriz = dict(cursor.fetchone() or {})

    if matriz:
        cursor.execute("""
            SELECT id, tipo_recurso, codigo, descripcion, rendimiento, unidad_recurso, precio_unitario, precio_total
            FROM recursos
            WHERE actividad_id = ?
            ORDER BY tipo_recurso, codigo
        """, (matriz_id,))

        matriz['recursos'] = [dict(row) for row in cursor.fetchall()]

    conn.close()

    return jsonify(matriz)

@app.route('/api/recursos', methods=['GET', 'POST'])
def api_recursos():
    """API - Listar o crear recursos"""
    conn = get_db()
    cursor = conn.cursor()

    if request.method == 'GET':
        matriz_id = request.args.get('matriz_id')
        tipo = request.args.get('tipo')

        query = "SELECT * FROM recursos WHERE 1=1"
        params = []

        if matriz_id:
            query += " AND actividad_id = ?"
            params.append(matriz_id)

        if tipo:
            query += " AND tipo_recurso = ?"
            params.append(tipo)

        query += " LIMIT 100"
        cursor.execute(query, params)

        recursos = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return jsonify(recursos)

    elif request.method == 'POST':
        data = request.get_json()

        cursor.execute("""
            INSERT INTO recursos
            (actividad_id, tipo_recurso, codigo, descripcion, rendimiento, unidad_recurso, precio_unitario, precio_total)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get('actividad_id'),
            data.get('tipo_recurso'),
            data.get('codigo'),
            data.get('descripcion'),
            data.get('rendimiento'),
            data.get('unidad_recurso'),
            data.get('precio_unitario'),
            data.get('precio_total')
        ))

        conn.commit()
        conn.close()

        return jsonify({'status': 'OK', 'id': cursor.lastrowid})

@app.route('/api/unidades')
def api_unidades():
    """API - Unidades dropdown"""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT codigo, nombre, tipo
        FROM unidades
        WHERE activa = TRUE
        ORDER BY tipo, nombre
    """)

    unidades = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return jsonify(unidades)

@app.route('/matrices')
def matrices_page():
    """Página - Listar matrices"""
    return render_template('matrices.html')

@app.route('/matriz/<int:matriz_id>')
def matriz_page(matriz_id):
    """Página - Detalle matriz"""
    return render_template('matriz_detail.html', matriz_id=matriz_id)

@app.route('/health')
def health():
    """Health check"""
    return jsonify({'status': 'OK', 'db': os.path.exists(DB_PATH)})

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)
