import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from foxalien_control.server import make_server


class HttpIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config_file = tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False, encoding="utf-8"
        )
        json.dump(
            {
                "transport": {"mode": "simulation"},
                "server": {"host": "127.0.0.1", "port": 0},
            },
            config_file,
        )
        config_file.close()
        cls.config_path = Path(config_file.name)
        cls.server, cls.service = make_server(cls.config_path)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        cls.config_path.unlink(missing_ok=True)

    def request(self, path, method="GET", body=None, origin=None):
        headers = {}
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if origin is not None:
            headers["Origin"] = origin
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        return urllib.request.urlopen(request, timeout=3)

    def test_static_console_is_served(self):
        with self.request("/") as response:
            body = response.read().decode("utf-8")
        self.assertIn("XE-PRO", body)
        self.assertIn("SPINDLE LOCKED", body)

    def test_connect_and_validate(self):
        with self.request("/api/connect", "POST", {}) as response:
            connected = json.load(response)
        self.assertTrue(connected["connected"])
        with self.request(
            "/api/job/validate",
            "POST",
            {"source": "G21\nG90\nG1 X10 F100\nM5"},
        ) as response:
            validation = json.load(response)
        self.assertTrue(validation["validation"]["valid"])

    def test_examples_are_served_and_validate(self):
        with self.request("/api/examples") as response:
            payload = json.load(response)
        self.assertGreaterEqual(len(payload["examples"]), 4)
        for example in payload["examples"]:
            with self.request(
                "/api/job/validate",
                "POST",
                {"source": example["source"]},
            ) as response:
                validation = json.load(response)
            self.assertTrue(
                validation["validation"]["valid"],
                f"Built-in example failed validation: {example['id']}",
            )

    def test_health_endpoint(self):
        with self.request("/health") as response:
            payload = json.load(response)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["mode"], "simulation")

    def test_cross_origin_control_is_blocked(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request(
                "/api/connect",
                "POST",
                {},
                origin="https://untrusted.example",
            )
        self.assertEqual(caught.exception.code, 409)


if __name__ == "__main__":
    unittest.main()
