import sqlite3
import os

dbs = [
    r"D:\OneDrive\Bots\Estimbot\Estimacion\backend\estimacion.db",
    r"D:\OneDrive\Bots\Estimbot\Estimacion\backend\estimastruct.db",
    r"D:\OneDrive\Bots\Estimbot\Estimacion\backend\estimacion-Consu.db",
    r"D:\OneDrive\Bots\Estimbot\Estimacion\backend\estimacion-ConstruLaptop.db",
]

for db_path in dbs:
    if not os.path.exists(db_path):
        print("[SKIP] Not found: " + db_path)
        continue

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        print("\n[OK] Connected: " + os.path.basename(db_path))

        # Verificar tablas
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [t[0] for t in cursor.fetchall()]

        if "config_presupuesto" not in tables:
            print("  [SKIP] Table config_presupuesto not found")
            conn.close()
            continue

        # Verificar columnas
        cursor.execute("PRAGMA table_info(config_presupuesto)")
        columns = {col[1]: col[2] for col in cursor.fetchall()}

        if "template_version" in columns:
            print("  [OK] template_version already exists")
        else:
            print("  [ADD] Adding template_version column...")
            cursor.execute("""
                ALTER TABLE config_presupuesto
                ADD COLUMN template_version VARCHAR(10) DEFAULT 'v1.0'
            """)
            conn.commit()
            print("  [OK] Column added successfully")

        conn.close()

    except Exception as e:
        print("  [ERROR] " + str(e))

print("\n=== Migration Complete ===")
