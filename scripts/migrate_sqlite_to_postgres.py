"""Copy an AEGIS SQLite database into the configured PostgreSQL database.

The source is never modified. Existing PostgreSQL rows are skipped only when
all copied values match; a conflicting primary key aborts the transaction.
"""
import argparse
import os
from pathlib import Path
import sqlite3
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import provider_config  # noqa: F401 - loads backend/.env without overriding shell values
import db
import intake_delivery


TABLES = (
    "reports",
    "assignments",
    "audit_events",
    "intake_previews",
    "report_media",
    "distress",
)


def normalized(value):
    return bytes(value) if isinstance(value, memoryview) else value


def sqlite_columns(connection, table):
    return [row[1] for row in connection.execute(f"PRAGMA table_info({table})")]


def migrate(source_path):
    source_path = source_path.resolve()
    if not source_path.is_relative_to(ROOT):
        raise ValueError("The SQLite source must stay inside AEGIS-MAIN.")
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    if db.database_backend() != "postgresql":
        raise RuntimeError("Set DATABASE_URL to the target PostgreSQL database first.")

    db.init_db()
    intake_delivery.init_schema()
    counts = {}
    source = sqlite3.connect(source_path)
    source.row_factory = sqlite3.Row
    try:
        with db.WRITE_LOCK, db.get_connection() as target:
            target.execute("BEGIN IMMEDIATE")
            for table in TABLES:
                columns = sqlite_columns(source, table)
                if not columns:
                    counts[table] = 0
                    continue
                target_columns = db._table_columns(target, table)
                copied_columns = [name for name in columns if name in target_columns]
                placeholders = ",".join("?" for _ in copied_columns)
                column_list = ",".join(copied_columns)
                inserted = 0
                for source_row in source.execute(f"SELECT * FROM {table}"):
                    values = tuple(source_row[name] for name in copied_columns)
                    existing = target.execute(
                        f"SELECT * FROM {table} WHERE id=?", (source_row["id"],)
                    ).fetchone()
                    if existing:
                        expected = {name: normalized(source_row[name]) for name in copied_columns}
                        actual = {name: normalized(existing[name]) for name in copied_columns}
                        if expected != actual:
                            raise RuntimeError(
                                f"Conflicting {table} row {source_row['id']}; migration stopped."
                            )
                        continue
                    target.execute(
                        f"INSERT INTO {table} ({column_list}) VALUES ({placeholders})",
                        values,
                    )
                    inserted += 1
                counts[table] = inserted
    finally:
        source.close()
        db.close_pool()
    return counts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--sqlite",
        default=os.getenv("AEGIS_DB_PATH", "data/aegis.db"),
        help="SQLite file inside AEGIS-MAIN (default: data/aegis.db)",
    )
    args = parser.parse_args()
    source = (ROOT / args.sqlite).resolve()
    counts = migrate(source)
    print("SQLite source preserved. PostgreSQL rows inserted:")
    for table, count in counts.items():
        print(f"  {table}: {count}")


if __name__ == "__main__":
    main()

