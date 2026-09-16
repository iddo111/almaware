import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

import server


class FakeProvider:
    model = "test-ant:tiny"

    def status(self):
        return {
            "reachable": True,
            "model": self.model,
            "model_loaded": True,
            "available_models": [self.model],
            "endpoint": "test://local",
        }

    def chat(self, ant, history, text):
        return f"אני {ant['name']}. שמעתי: {text}. זיק (בואו לכאן)."


class AntFarmTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        db = Path(self.temp.name) / "test.db"
        self.httpd = server.create_server(
            "127.0.0.1", 0, db_path=db, provider=FakeProvider()
        )
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def get_json(self, path):
        with urllib.request.urlopen(self.base + path, timeout=3) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def post_json(self, path, payload):
        request = urllib.request.Request(
            self.base + path,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=3) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def test_health_reports_real_provider_identity(self):
        status, payload = self.get_json("/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(payload["model"]["model"], "test-ant:tiny")
        self.assertTrue(payload["model"]["model_loaded"])

    def test_colony_has_nine_ants_and_three_judges(self):
        status, payload = self.get_json("/api/colony")
        self.assertEqual(status, 200)
        self.assertEqual(len(payload["ants"]), 9)
        self.assertEqual(len(payload["judges"]), 3)
        self.assertEqual(len(payload["norms"]), 4)

    def test_chat_persists_both_sides_and_returns_judges(self):
        status, payload = self.post_json(
            "/api/chat", {"ant_id": "tami", "message": "מה מצאת בשביל?"}
        )
        self.assertEqual(status, 200)
        self.assertIn("תמי", payload["reply"])
        self.assertEqual(len(payload["judges"]), 3)
        _, history = self.get_json("/api/history?ant_id=tami")
        self.assertEqual([item["speaker"] for item in history["messages"]], ["human", "ant"])

    def test_unknown_ant_is_rejected(self):
        request = urllib.request.Request(
            self.base + "/api/chat",
            data=json.dumps({"ant_id": "missing", "message": "שלום"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=3)
        self.assertEqual(caught.exception.code, 400)

    def test_system_prompt_marks_simulation_and_norms(self):
        prompt = server.build_system_prompt(server.get_ant("oren"))
        self.assertIn("בסימולציית מחשב", prompt)
        self.assertIn("כשאינך יודע", prompt)
        self.assertNotIn("/no_think", prompt)


if __name__ == "__main__":
    unittest.main()
