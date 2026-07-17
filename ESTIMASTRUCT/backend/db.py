"""
Conexion a BD — SQLite local (fuera de OneDrive) con FK + WAL.

FASE 0 de estabilizacion:
  - Ruta absoluta via config.CONFIG.DB_PATH (antes: sqlite:///./estimacion.db,
    relativo al cwd => fragil; ademas OneDrive corrompia el .db por sync).
  - PRAGMA foreign_keys=ON  => aplica los ondelete CASCADE/SET NULL del modelo
    (antes OFF => cascadas inertes, huerfanos silenciosos).
  - PRAGMA journal_mode=WAL => menos bloqueo de escritura.
  - get_db() hace rollback ante excepcion (antes solo cerraba).
"""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from backend.config import CONFIG

# URL sqlite requiere forward slashes
_DB_URL = "sqlite:///" + CONFIG.DB_PATH.replace("\\", "/")

engine = create_engine(_DB_URL, connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_conn, _record):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.execute("PRAGMA mmap_size=268435456")   # 256MB I/O mapeado — lecturas mas rapidas
    cur.execute("PRAGMA cache_size=-16000")      # 16MB cache de paginas
    cur.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def dispose_engine():
    """Descarta el pool de conexiones del engine — fuerza reconexion fresca
    al archivo canonico (CONFIG.DB_PATH) en el siguiente checkout.

    Uso: tras reemplazar estimacion.db por un import ZIP (backend/routers/
    db_backup.py), tanto SQLAlchemy como el driver sqlite3 subyacente pueden
    tener conexiones abiertas contra el archivo VIEJO. dispose() cierra esas
    conexiones pooleadas sin recrear el objeto `engine` — mantiene su
    identidad de objeto, asi que los modulos que ya hicieron
    `from backend.db import engine` (main.py) o que usan `SessionLocal`
    (la mayoria de los routers, via get_db(), y scripts_runner) NO necesitan
    reimportar nada: el siguiente `SessionLocal()` abre una conexion nueva
    que ve el archivo reemplazado. El hook `_set_sqlite_pragmas` (evento
    "connect") se re-aplica automaticamente en esa conexion nueva.
    """
    engine.dispose()
