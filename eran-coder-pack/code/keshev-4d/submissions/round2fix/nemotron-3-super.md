

```python
# app/sttclient.py
import json
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import Optional

@dataclass
class DecodeResult:
    text: str = ''
    lang: Optional[str] = None
    avg_logprob: Optional[float] = None
    ms: int = 0
    reason: str = ''

class SttClient:
    def __init__(self, base_url: str, token_file: str, timeout_s: float = 8.0):
        self.base_url = base_url.rstrip('/')
        self.token_file = token_file
        self.timeout_s = timeout_s

    def _read_token(self) -> str:
        with open(self.token_file, 'r', encoding='utf-8') as f:
            return f.read().strip()

    def decode(self, rec_id: str, body_bytes: bytes, lang_hint: str = 'auto') -> DecodeResult:
        token = self._read_token()
        url = f"{self.base_url}/v1/transcribe"
        req = urllib.request.Request(url, data=body_bytes, method='POST')
        req.add_header('Authorization', f'Bearer {token}')
        req.add_header('X-Request-Id', rec_id)
        req.add_header('X-Lang-Hint', lang_hint)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                raw = resp.read()
                try:
                    data = json.loads(raw.decode('utf-8'))
                except json.JSONDecodeError:
                    return DecodeResult(reason='server')
                resp_id = data.get('request_id')
                if resp_id is not None and resp_id != rec_id:
                    return DecodeResult(reason='late_reply')
                text = data.get('text', '')
                lang = data.get('language')
                avg_logprob = data.get('avg_logprob')
                ms = data.get('ms', 0)
                if lang is not None:
                    lang = str(lang)
                if avg_logprob is not None:
                    try:
                        avg_logprob = float(avg_logprob)
                    except (ValueError, TypeError):
                        avg_logprob = None
                if not isinstance(ms, int):
                    try:
                        ms = int(ms)
                    except (ValueError, TypeError):
                        ms = 0
                return DecodeResult(text=text, lang=lang, avg_logprob=avg_logprob, ms=ms, reason='')
        except urllib.error.URLError as e:
            err_str = str(e)
            if 'timed out' in err_str.lower():
                reason = 'timeout'
            else:
                reason = 'http'
            return DecodeResult(reason=reason)
        except Exception:
            return DecodeResult(reason='server')

    def health(self) -> bool:
        url = f"{self.base_url}/health"
        req = urllib.request.Request(url, method='GET')
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                return resp.status == 200
        except Exception:
            return False
```

```python
# tests/test_sttclient.py
import unittest
import threading
import time
import os
import tempfile
import shutil
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from app.sttclient import SttClient, DecodeResult

class TestHandler(BaseHTTPRequestHandler):
    response_json = {}
    response_status = 200
    last_rec_id = None
    last_lang_hint = None
    last_body = None

    def do_POST(self):
        if self.path == '/v1/transcribe':
            content_len = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_len) if content_len > 0 else b''
            self.last_body = body
            self.last_rec_id = self.headers.get('X-Request-Id')
            self.last_lang_hint = self.headers.get('X-Lang-Hint')
            data = dict(self.response_json)
            if 'request_id' not in data:
                data['request_id'] = self.last_rec_id
            resp_body = json.dumps(data).encode('utf-8')
            self.send_response(self.response_status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(resp_body)))
            self.end_headers()
            self.wfile.write(resp_body)
        else:
            self.send_error(404)

    def do_GET(self):
        if self.path == '/health':
            self.send_response(self.response_status)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'OK')
        else:
            self.send_error(404)

    def log_message(self, format, *args):
        pass

class TestSttClient(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(('127.0.0.1', 0), TestHandler)
        cls.port = cls.server.server_port
        cls.base_url = f'http://127.0.0.1:{cls.port}'
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server_thread.join()

    def setUp(self):
        TestHandler.response_json = {}
        TestHandler.response_status = 200
        TestHandler.last_rec_id = None
        TestHandler.last_lang_hint = None
        TestHandler.last_body = None
        self.token_dir = tempfile.mkdtemp()
        self.token_file = os.path.join(self.token_dir, 'token.txt')
        with open(self.token_file, 'w') as f:
            f.write('fake-token')
        self.client = SttClient(self.base_url, self.token_file, timeout_s=2.0)

    def tearDown(self):
        shutil.rmtree(self.token_dir, ignore_errors=True)

    def test_good_decode(self):
        TestHandler.response_json = {
            'text': 'hello world',
            'language': 'en',
            'avg_logprob': -0.5,
            'ms': 1200,
            'request_id': 'rec123'
        }
        rec_id = 'rec123'
        body = b'{"audio": "dummy"}'
        result = self.client.decode(rec_id, body, lang_hint='en')
        self.assertEqual(result.reason, '')
        self.assertEqual(result.text, 'hello world')
        self.assertEqual(result.lang, 'en')
        self.assertAlmostEqual(result.avg_logprob, -0.5)
        self.assertEqual(result.ms, 1200)
        self.assertEqual(TestHandler.last_rec_id, rec_id)
        self.assertEqual(TestHandler.last_lang_hint, 'en')
        self.assertEqual(TestHandler.last_body, body)

    def test_late_reply(self):
        TestHandler.response_json = {
            'text': 'hi',
            'request_id': 'different-id'
        }
        rec_id = 'myid'
        body = b''
        result = self.client.decode(rec_id, body)
        self.assertEqual(result.reason, 'late_reply')
        self.assertEqual(result.text, '')
        self.assertIsNone(result.lang)
        self.assertIsNone(result.avg_logprob)
        self.assertEqual(result.ms, 0)

    def test_dead_port_http(self):
        dead_client = SttClient('http://127.0.0.1:99999', self.token_file, timeout_s=2.0)
        result = dead_client.decode('rec', b'')
        self.assertEqual(result.reason, 'http')
        self.assertFalse(dead_client.health())

    def test_timeout(self):
        class DelayHandler(BaseHTTPRequestHandler):
            def do_POST(self):
                time.sleep(2.5)
                self.send_error(500)
            def log_message(self, format, *args):
                pass
        server = HTTPServer(('127.0.0.1', 0), DelayHandler)
        port = server.server_port
        base_url = f'http://127.0.0.1:{port}'
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            client = SttClient(base_url, self.token_file, timeout_s=0.5)
            result = client.decode('rec', b'')
            self.assertEqual(result.reason, 'timeout')
        finally:
            server.shutdown()
            thread.join()

    def test_health_true(self):
        TestHandler.response_status = 200
        self.assertTrue(self.client.health())

    def test_health_false(self):
        TestHandler.response_status = 500
        self.assertFalse(self.client.health())
```