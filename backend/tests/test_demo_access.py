"""Public evaluator access is opt-in, revocable and uses no admin password."""
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from test_aegis import AegisTests, PAYLOAD
from main import app


class DemoAccessTests(unittest.TestCase):
    setUp = AegisTests.setUp
    tearDown = AegisTests.tearDown

    def test_demo_disabled_keeps_staff_routes_locked(self):
        with patch.dict(os.environ, {"AEGIS_PUBLIC_DEMO": "false"}):
            client = TestClient(app)
            self.assertEqual(client.get("/auth/demo").json(), {"enabled": False})
            self.assertEqual(client.post("/auth/command/demo").status_code, 404)
            self.assertEqual(client.get("/reports").status_code, 401)
            self.assertNotEqual(client.post("/auth/responder/login", json={
                "username": "POL-02", "password": "AEGIS-demo-only",
            }).status_code, 200)

    def test_demo_command_and_prefilled_responder_work_end_to_end(self):
        with patch.dict(os.environ, {
            "AEGIS_PUBLIC_DEMO": "true", "AEGIS_ENABLE_RESET": "false",
            "AEGIS_RESPONDER_ACCOUNTS": '{"POL-02":"private-unit-password"}',
        }):
            command = TestClient(app)
            config = command.get("/auth/demo")
            self.assertEqual(config.headers["cache-control"], "no-store")
            self.assertNotIn("test-password", config.text)
            self.assertNotIn("private-unit-password", config.text)
            self.assertNotIn("test-secret-only", config.text)
            login = command.post("/auth/command/demo")
            self.assertEqual(login.status_code, 200, login.text)
            command_token = login.json()["token"]
            command.headers["Authorization"] = "Bearer " + command_token
            self.assertEqual(command.get("/auth/command/session").status_code, 200)
            for path in ["/reports", "/resources", "/relocation-centres", "/assignments"]:
                self.assertEqual(command.get(path).status_code, 200, path)
            self.assertEqual(command.post("/demo/reset").status_code, 403)
            report = TestClient(app).post("/reports", json=PAYLOAD).json()["report"]
            dispatch = command.post(f'/reports/{report["id"]}/dispatch')
            self.assertEqual(dispatch.status_code, 200, dispatch.text)
            self.assertEqual(command.get(f'/reports/{report["id"]}').status_code, 200)
            responder = TestClient(app)
            response = responder.post("/auth/responder/login", json=config.json()["responder"])
            self.assertEqual(response.status_code, 200, response.text)
            responder_token = response.json()["token"]
            responder.headers["Authorization"] = "Bearer " + responder_token
            self.assertEqual(responder.get("/auth/responder/session").status_code, 200)
            self.assertEqual(responder.get("/assignments?resource_id=POL-02").status_code, 200)
            self.assertEqual(responder.get("/assignments?resource_id=AMB-02").status_code, 403)
            self.assertEqual(responder.get("/auth/command/session").status_code, 401)
            self.assertEqual(responder.get("/resources").status_code, 401)
            self.assertEqual(responder.post("/auth/responder/login", json={
                "username": "POL-02", "password": "wrong",
            }).status_code, 401)

        with patch.dict(os.environ, {"AEGIS_PUBLIC_DEMO": "false"}):
            self.assertEqual(command.get("/reports").status_code, 401)
            self.assertEqual(responder.get("/auth/responder/session").status_code, 401)


if __name__ == "__main__":
    unittest.main()
