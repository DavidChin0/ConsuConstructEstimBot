import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Backend en sys.path (mismo patron que routers/*.py: sys.path.insert al
# directorio backend/ para poder importar config/db/models como top-level).

from backend.config import CONFIG  # noqa: E402
from backend.db import Base  # noqa: E402
from backend import models  # noqa: E402  (registra todas las tablas en Base.metadata)

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# URL de la BD viva — misma logica que db.py.
config.set_main_option("sqlalchemy.url", CONFIG.DATABASE_URL)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata


def include_object(object_, name, type_, reflected, compare_to):
    """Red de seguridad contra el footgun de `alembic revision --autogenerate`
    (goal-21080): la BD Postgres de EstimaStruct tiene tablas y un schema que
    NO están en models.py (arch_chunks, assistant_sessions, assistant_messages,
    csi_codes, csi_embeddings y el schema `rag`). Sin este filtro, autogenerate
    los ve como "sobrantes" y emite DROP TABLE / DROP SCHEMA por ellos.

    Regla: una tabla REFLEJADA de la BD que el ORM no declara (compare_to is
    None) nunca se toca — se excluye del diff. El ORM sólo administra lo que
    modela; todo lo demás es intocable para las migraciones autogeneradas.
    """
    if type_ == "table" and reflected and compare_to is None:
        return False
    return True

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
        include_schemas=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            include_schemas=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
