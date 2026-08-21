"""Runtime smoke for the v1.4 backend and browser-facing Flask shell."""
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from backend.config import CONFIG
from backend.main import app as api
from ESTIMASTRUCT.app import app as ui


def main() -> None:
    assert CONFIG.RELEASE_VERSION == "v1.4"
    assert Path(CONFIG.DB_PATH).resolve() == CONFIG.VERSIONED_DB_PATH.resolve()
    with TestClient(api) as client:
        health = client.get("/health")
        assert health.status_code == 200, health.text
        payload = health.json()
        assert payload["release"] == "v1.4", payload
        assert payload["database"]["user_version"] == 14, payload
        budgets = client.get("/presupuestos")
        assert budgets.status_code == 200, budgets.text
    with ui.test_client() as client:
        page = client.get("/")
        assert page.status_code == 200
        assert b'value="v1.4"' in page.data
        app_js = client.get("/js/app.js")
        assert app_js.status_code == 200
        assert b'option[value="v1.4"]' in app_js.data
    with sqlite3.connect(f"file:{CONFIG.DB_PATH}?mode=ro", uri=True) as conn:
        assert conn.execute("SELECT COUNT(*) FROM rendimiento_audit").fetchone()[0] == 257
    print("v1.4 runtime smoke: backend health/API + frontend shell/assets + versioned SQLite OK")


if __name__ == "__main__":
    main()
