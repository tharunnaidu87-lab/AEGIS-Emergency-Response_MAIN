"""Database backend selection and PostgreSQL compatibility.

SQLite remains the local-development default. Render must be configured with a
PostgreSQL ``DATABASE_URL`` so production never silently writes to an ephemeral
filesystem.
"""
from contextlib import contextmanager
import os
import re
import threading


_POOL = None
_POOL_KEY = None
_POOL_LOCK = threading.Lock()
_WRITE_LOCK_ID = 6_933_476_847_120_263_921


def database_url():
    return os.getenv("DATABASE_URL", "").strip()


def database_backend():
    url = database_url()
    if url:
        if not url.startswith(("postgres://", "postgresql://")):
            raise RuntimeError("DATABASE_URL must be a PostgreSQL connection URL.")
        return "postgresql"
    if os.getenv("RENDER", "").lower() == "true":
        raise RuntimeError(
            "DATABASE_URL is required on Render. Refusing ephemeral SQLite storage."
        )
    return "sqlite"


def _pool_size():
    try:
        return max(1, min(int(os.getenv("AEGIS_DB_POOL_SIZE", "5")), 10))
    except ValueError:
        return 5


def database_schema():
    schema = os.getenv("AEGIS_DB_SCHEMA", "public").strip() or "public"
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,62}", schema):
        raise RuntimeError("AEGIS_DB_SCHEMA is not a valid PostgreSQL identifier.")
    return schema


def _get_pool(url):
    global _POOL, _POOL_KEY
    schema = database_schema()
    key = (url, schema)
    with _POOL_LOCK:
        if _POOL is not None and _POOL_KEY != key:
            _POOL.close()
            _POOL = None
        if _POOL is None:
            try:
                from psycopg.rows import dict_row
                from psycopg_pool import ConnectionPool
            except ImportError as error:
                raise RuntimeError(
                    "PostgreSQL support is not installed. Install backend requirements."
                ) from error
            _POOL = ConnectionPool(
                conninfo=url,
                min_size=0,
                max_size=_pool_size(),
                timeout=10,
                kwargs={
                    "row_factory": dict_row,
                    "connect_timeout": 10,
                    "application_name": "aegis-backend",
                    "options": f"-c search_path={schema}",
                },
                open=True,
            )
            _POOL_KEY = key
        return _POOL


def _postgres_sql(statement):
    text = statement.strip()
    if text.rstrip(";").upper() == "BEGIN IMMEDIATE":
        return None
    translated = statement.replace("?", "%s")
    if text.upper().startswith("CREATE TABLE"):
        translated = re.sub(r"\bBLOB\b", "BYTEA", translated, flags=re.I)
        translated = re.sub(r"\bREAL\b", "DOUBLE PRECISION", translated, flags=re.I)
    return translated


class PostgresConnection:
    dialect = "postgresql"

    def __init__(self, connection):
        self._connection = connection

    def execute(self, statement, parameters=None):
        translated = _postgres_sql(statement)
        if translated is None:
            self._connection.execute("BEGIN")
            return self._connection.execute(
                "SELECT pg_advisory_xact_lock(%s)", (_WRITE_LOCK_ID,)
            )
        if parameters is None:
            return self._connection.execute(translated)
        return self._connection.execute(translated, parameters)


@contextmanager
def postgres_connection():
    pool = _get_pool(database_url())
    with pool.connection() as connection:
        yield PostgresConnection(connection)


def close_pool():
    global _POOL, _POOL_KEY
    with _POOL_LOCK:
        if _POOL is not None:
            _POOL.close()
            _POOL = None
            _POOL_KEY = None
