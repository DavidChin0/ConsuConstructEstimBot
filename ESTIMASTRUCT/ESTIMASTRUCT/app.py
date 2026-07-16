#!/usr/bin/env python3
"""
ESTIMASTRUCT Web App - Flask
Interfaz para gestionar matrices y recursos
http://localhost:5000
"""

from flask import Flask, render_template, render_template_string, request, jsonify, send_from_directory
import sqlite3
import os
import json
import glob

# Rutas relativas al repo (portable; sobrevive moves del arbol)
ESTIMASTRUCT_PATH = os.path.dirname(os.path.abspath(__file__))
FRONTEND_PATH = os.path.join(os.path.dirname(ESTIMASTRUCT_PATH), "frontend")

app = Flask(__name__,
            template_folder=ESTIMASTRUCT_PATH + "/templates",
            static_folder=FRONTEND_PATH)
DB_PATH = os.environ.get("ESTIMASTRUCT_UI_DB", r"C:\EstimaStruct\data\estimastruct.db")  # BD UI fuera de OneDrive (FASE 0 patrón; original quedó como copia stale en ESTIMASTRUCT/)
API_BASE = os.environ.get("ESTIMASTRUCT_API_BASE", "http://localhost:8002")
INDEX_TEMPLATE_PATH = os.path.join(ESTIMASTRUCT_PATH, "templates", "index.html")


def _current_asset_version() -> str:
    """Cache-bust por-request: usa el mtime ACTUAL de TODO el JS/CSS del frontend.
    Antes era una constante calculada al boot → editar el frontend no cambiaba el ?v=
    y el navegador servía JS/CSS viejos en cargas normales (solo Ctrl+F5 traía el fix).
    Glob de *.js/*.css para cubrir la modularizacion (core.js + futuros modulos)."""
    paths = (
        glob.glob(os.path.join(FRONTEND_PATH, "js", "*.js")) +
        glob.glob(os.path.join(FRONTEND_PATH, "css", "*.css"))
    )
    latest = 0.0
    for p in paths:
        try:
            latest = max(latest, os.path.getmtime(p))
        except OSError:
            pass
    return str(int(latest))


@app.route('/css/<path:filename>')
def serve_css(filename):
    """Servir archivos CSS desde frontend/css/"""
    return send_from_directory(os.path.join(FRONTEND_PATH, 'css'), filename)


@app.route('/js/<path:filename>')
def serve_js(filename):
    """Servir archivos JS desde frontend/js/"""
    return send_from_directory(os.path.join(FRONTEND_PATH, 'js'), filename)


@app.route('/vendor/<path:filename>')
def serve_vendor(filename):
    """Servir librerías vendorizadas (KaTeX) desde frontend/vendor/"""
    return send_from_directory(os.path.join(FRONTEND_PATH, 'vendor'), filename)

def get_db():
    """Conectar a DB"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _render_front():
    """Renderiza el dashboard de produccion (templates/index.html) con el contexto de la BD."""
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

    with open(INDEX_TEMPLATE_PATH, "r", encoding="utf-8") as f:
        template = f.read()

    return render_template_string(
        template,
        total_matrices=total_matrices,
        total_recursos=total_recursos,
        tipos=tipos,
        top_matrices=top_matrices,
        api_base=API_BASE,
        asset_version=_current_asset_version(),
    )


@app.route('/')
def index():
    """Home - Dashboard (PRODUCCION)"""
    return _render_front()


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
