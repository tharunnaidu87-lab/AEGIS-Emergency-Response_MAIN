"""Database selection, SQL compatibility, and optional real PostgreSQL restart tests."""
import base64
import io
import os
import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

import database_runtime
import db
import distress
import intake_delivery
import operations


class FakeRawConnection:
    def __init__(self):
        self.calls = []

    def execute(self, statement, parameters=None):
        self.calls.append((statement, parameters))
        return self


class DatabaseRuntimeTests(unittest.TestCase):
    def tearDown(self):
        database_runtime.close_pool()

    def test_local_sqlite_and_render_fail_closed(self):
        with patch.dict(os.environ, {"DATABASE_URL": "", "RENDER": ""}):
            self.assertEqual(database_runtime.database_backend(), "sqlite")
        with patch.dict(os.environ, {"DATABASE_URL": "", "RENDER": "true"}):
            with self.assertRaisesRegex(RuntimeError, "DATABASE_URL is required"):
                database_runtime.database_backend()
        with patch.dict(os.environ, {"DATABASE_URL": "sqlite:///ephemeral.db", "RENDER": "true"}):
            with self.assertRaisesRegex(RuntimeError, "PostgreSQL"):
                database_runtime.database_backend()

    def test_postgres_translation_and_serialized_write_lock(self):
        self.assertEqual(
            database_runtime._postgres_sql("SELECT * FROM reports WHERE id=?"),
            "SELECT * FROM reports WHERE id=%s",
        )
        schema = database_runtime._postgres_sql(
            "CREATE TABLE sample (value REAL, content BLOB)"
        )
        self.assertIn("DOUBLE PRECISION", schema)
        self.assertIn("BYTEA", schema)
        raw = FakeRawConnection()
        connection = database_runtime.PostgresConnection(raw)
        connection.execute("BEGIN IMMEDIATE")
        self.assertEqual(raw.calls[0], ("BEGIN", None))
        self.assertEqual(raw.calls[1][0], "SELECT pg_advisory_xact_lock(%s)")


@unittest.skipUnless(
    os.getenv("AEGIS_TEST_DATABASE_URL"),
    "Set AEGIS_TEST_DATABASE_URL to run the real PostgreSQL restart test.",
)
class PostgresRestartIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        from psycopg import sql

        cls.url = os.environ["AEGIS_TEST_DATABASE_URL"]
        cls.schema = "aegis_test_" + uuid.uuid4().hex[:12]
        with psycopg.connect(cls.url, autocommit=True) as connection:
            connection.execute(
                sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(cls.schema))
            )
        cls.environment = patch.dict(
            os.environ,
            {
                "DATABASE_URL": cls.url,
                "AEGIS_DB_SCHEMA": cls.schema,
                "RENDER": "true",
            },
        )
        cls.environment.start()
        db.init_db()
        intake_delivery.init_schema()

    @classmethod
    def tearDownClass(cls):
        import psycopg
        from psycopg import sql

        db.close_pool()
        cls.environment.stop()
        with psycopg.connect(cls.url, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(cls.schema))
            )

    def test_reports_tokens_assignments_audit_distress_and_media_survive_restart(self):
        image = io.BytesIO()
        Image.new("RGB", (4, 4), "green").save(image, "PNG")
        payload = {
            "client_request_id": "postgres-restart-" + uuid.uuid4().hex[:16],
            "incident_type": "Fire",
            "location": "PostgreSQL restart verification",
            "latitude": 13.13,
            "longitude": 80.22,
            "people_affected": 2,
            "hazard_intensity": 0.4,
            "description": "Automated isolated-schema persistence test.",
            "photos": [base64.b64encode(image.getvalue()).decode()],
        }
        report = operations.submit(payload)
        receipt = intake_delivery.receipt(report)
        assignments = operations.dispatch(report["id"])["assignments"]
        signal_id = "postgres-sos-" + uuid.uuid4().hex[:16]
        distress.create_distress(
            distress.DistressRequest(
                client_request_id=signal_id,
                captured_at="2026-09-20T15:08:25Z",
            )
        )
        events = db.list_audit_events(report_id=report["id"])

        db.close_pool()  # Equivalent to a backend process shutting down.
        db.init_db()
        intake_delivery.init_schema()

        restored = db.get_report(report["id"])
        self.assertEqual(restored["fusion_id"], report["fusion_id"])
        self.assertEqual(db.list_assignments(report_id=report["id"]), assignments)
        self.assertEqual(db.list_audit_events(report_id=report["id"]), events)
        self.assertEqual(intake_delivery.media_ids(report["id"]), receipt["report"]["photo_ids"])
        self.assertEqual(
            intake_delivery.receipt(intake_delivery.existing_report(payload))["tracking_token"],
            receipt["tracking_token"],
        )
        self.assertEqual(distress.get_row(signal_id)["status"], "LOCATION_NEEDED")

