import os
import unittest

from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///./data/test-regression.db"
os.environ["DEFAULT_PASSWORD"] = "secret-pass"
os.environ["AUTONOMY_SELF_EDIT_ENABLED"] = "true"

from app.main import app  # noqa: E402
from app.storage import ensure_default_user, init_db  # noqa: E402


class AutonomyRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        init_db()
        ensure_default_user("admin", "secret-pass")
        self.client = TestClient(app)
        resp = self.client.post("/login", data={"username": "admin", "password": "secret-pass"})
        self.assertIn(resp.status_code, (200, 303))

    def test_queue_and_worker_endpoints(self) -> None:
        q = self.client.post(
            "/api/admin/agent/queue",
            json={"goal": "проверить версию python", "provider": "gigachat", "priority": 2, "iterations": 2},
        )
        self.assertEqual(q.status_code, 200)
        queue = self.client.get("/api/admin/agent/queue")
        self.assertEqual(queue.status_code, 200)
        self.assertIn("items", queue.json())

        w = self.client.post("/api/admin/agent/worker", json={"enabled": False})
        self.assertEqual(w.status_code, 200)

    def test_approvals_and_kpi(self) -> None:
        kpi = self.client.get("/api/admin/agent/kpi")
        self.assertEqual(kpi.status_code, 200)

        approvals = self.client.get("/api/admin/approvals")
        self.assertEqual(approvals.status_code, 200)

        decision = self.client.post(
            "/api/admin/approvals/decide",
            json={"approval_id": 1, "approve": False, "note": "regression check"},
        )
        self.assertEqual(decision.status_code, 200)

    def test_self_edit_safe_pipeline(self) -> None:
        planned = self.client.post("/api/admin/agent/self-edit/plan", json={"goal": "улучшить диагностику"})
        self.assertEqual(planned.status_code, 200)
        checked = self.client.post("/api/admin/agent/self-edit/check", json={"goal": "улучшить диагностику"})
        self.assertEqual(checked.status_code, 200)
        runs = self.client.get("/api/admin/agent/self-edit/runs")
        self.assertEqual(runs.status_code, 200)


if __name__ == "__main__":
    unittest.main()
