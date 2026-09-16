

```python
# app/sttclient.py
import json
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import Optional
import journal  # assumed to be provided elsewhere


@dataclass
class DecodeResult:
    ok: bool
    text: str = ''
    lang: Optional[str] = None
    avg_logprob: Optional[float] = None
    ms: int = 0
    reason: str = ''  # ''|timeout|http|late_reply|server


class SttClient:
    def __init__(self, base_url: str, token_file: str, timeout_s: float = 8.0):
        self.base_url = base_url.rstrip('/')
        self.token_file = token_file
        self.timeout_s = timeout_s

    def _read_token(self) -> str:
        with open(self.token_file, 'r') as f:
            return f.read().strip()

    def decode(self, rec_id: str, wav_bytes: bytes, lang_hint: str = 'auto') -> DecodeResult:
        token = self._read_token()
        url = f"{self.base_url}/v1/transcribe"
        req = urllib.request.Request(
            url,
            data=wav_bytes,
            method='POST',
            headers={
                'Authorization': f'Bearer {token}',
                'X-Request-Id': rec_id,
                'X-Lang-Hint': lang_hint,
                'Content-Type': 'application/octet-stream',
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                payload = resp.read().decode('utf-8')
                try:
                    data = json.loads(payload)
                except json.JSONDecodeError:
                    reason = 'server'
                    journal.event(reason=reason, rec_id=rec_id)
                    return DecodeResult(ok=False, reason=reason)
                # verify request_id
                if data.get('request_id') != rec_id:
                    reason = 'late_reply'
                    journal.event(reason=reason, rec_id=rec_id)
                    return DecodeResult(ok=False, reason=reason)
                # success fields
                text = str(data.get('text', ''))
                lang = data.get('language')
                if lang is not None:
                    lang = str(lang)
                avg_logprob = data.get('avg_logprob')
                if avg_logprob is not None:
                    try:
                        avg_logprob = float(avg_logprob)
                    except (ValueError, TypeError):
                        avg_logprob = None
                ms = int(data.get('processing_ms', 0))
                return DecodeResult(
                    ok=True,
                    text=text,
                    lang=lang,
                    avg_logprob=avg_logprob,
                    ms=ms,
                    reason='',
                )
        except urllib.error.URLError as e:
            if 'timed out' in str(e).lower():
                reason = 'timeout'
            else:
                reason = 'http'
            journal.event(reason=reason, rec_id=rec_id)
            return DecodeResult(ok=False, reason=reason)

    def health(self) -> bool:
        token = self._read_token()
        url = f"{self.base_url}/health"
        req = urllib.request.Request(
            url,
            method='GET',
            headers={'Authorization': f'Bearer {token}'},
        )
        try:
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                return resp.status == 200
        except urllib.error.URLError:
            return False
```

```python
# tests/test_sttclient.py
import unittest
import tempfile
import os
import threading
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.request import Request, urlopen
from urllib.error import URLError
from unittest.mock import patch
import sys

# Import the module under test
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.sttclient import SttClient, DecodeResult


class TestSttClient(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.token_file = os.path.join(self.temp_dir.name, 'token.txt')
        self.base_url = 'http://127.0.0.1:0'  # placeholder, actual port set per test

    def tearDown(self):
        self.temp_dir.cleanup()

    def _start_server(self, handler_class):
        server = HTTPServer(('127.0.0.1', 0), handler_class)
        port = server.server_address[1]
        self.base_url = f'http://127.0.0.1:{port}'
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        # give server a moment to start
        import time
        time.sleep(0.05)
        return server, thread

    def test_good_decode(self):
        token = 'testtoken'
        with open(self.token_file, 'w') as f:
            f.write(token)
        rec_id = 'abc123'
        expected_text = 'hello world'
        expected_lang = 'en'
        expected_logprob = -0.15
        expected_ms = 95

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                if self.path != '/v1/transcribe':
                    self.send_response(404)
                    self.end_headers()
                    return
                auth = self.headers.get('Authorization')
                if auth != f'Bearer {token}':
                    self.send_response(401)
                    self.end_headers()
                    return
                length = int(self.headers.get('Content-Length', 0))
                self.rfile.read(length)  # discard body
                resp = {
                    'request_id': rec_id,
                    'text': expected_text,
                    'language': expected_lang,
                    'avg_logprob': expected_logprob,
                    'processing_ms': expected_ms,
                }
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(resp).encode())

            def log_message(self, format, *args):
                pass

        server, thread = self._start_server(Handler)
        try:
            client = SttClient(self.base_url, self.token_file, timeout_s=2.0)
            wav = b'dummy'
            with patch('app.sttclient.journal.event') as mock_journal:
                result = client.decode(rec_id, wav, lang_hint='en')
                mock_journal.assert_not_called()
            self.assertTrue(result.ok)
            self.assertEqual(result.text, expected_text)
            self.assertEqual(result.lang, expected_lang)
            self.assertAlmostEqual(result.avg_logprob, expected_logprob)
            self.assertEqual(result.ms, expected_ms)
            self.assertEqual(result.reason, '')
        finally:
            server.shutdown()
            thread.join()

    def test_late_reply(self):
        token = 'testtoken'
        with open(self.token_file, 'w') as f:
            f.write(token)
        rec_id = 'rec-1'
        wrong_id = 'rec-2'

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                if self.path != '/v1/transcribe':
                    self.send_response(404)
                    self.end_headers()
                    return
                auth = self.headers.get('Authorization')
                if auth != f'Bearer {token}':
                    self.send_response(401)
                    self.end_headers()
                    return
                length = int(self.headers.get('Content-Length', 0))
                self.rfile.read(length)
                resp = {
                    'request_id': wrong_id,  # deliberately mismatched
                    'text': 'ignore',
                }
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(resp).encode())

            def log_message(self, format, *args):
                pass

        server, thread = self._start_server(Handler)
        try:
            client = SttClient(self.base_url, self.token_file, timeout_s=2.0)
            wav = b'dummy'
            with patch('app.sttclient.journal.event') as mock_journal:
                result = client.decode(rec_id, wav)
                mock_journal.assert_called_once()
                args, kwargs = mock_journal.call_args
                self.assertEqual(kwargs.get('reason'), 'late_reply')
                self.assertEqual(kwargs.get('rec_id'), rec_id)
            self.assertFalse(result.ok)
            self.assertEqual(result.reason, 'late_reply')
            self.assertEqual(result.text, '')
            self.assertIsNone(result.lang)
            self.assertIsNone(result.avg_logprob)
            self.assertEqual(result.ms, 0)
        finally:
            server.shutdown()
            thread.join()

    def test_dead_port_http(self):
        # Use a port that is guaranteed not to be listening
        dead_port = 9  # reserved
        base_url = f'http://127.0.0.1:{dead_port}'
        with open(self.token_file, 'w') as f:
            f.write('token')
        client = SttClient(base_url, self.token_file, timeout_s=0.5)
        with patch('app.sttclient.journal.event') as mock_journal:
            result = client.decode('rec-id', b'')
            mock_journal.assert_called_once()
            args, kwargs = mock_journal.call_args
            self.assertIn(kwargs.get('reason'), ('http', 'timeout'))
        self.assertFalse(result.ok)
        self.assertIn(result.reason, ('http', 'timeout'))

    def test_health_true(self):
        token = 'health-ok'
        with open(self.token_file, 'w') as f:
            f.write(token)

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path != '/health':
                    self.send_response(404)
                    self.end_headers()
                    return
                auth = self.headers.get('Authorization')
                if auth != f'Bearer {token}':
                    self.send_response(401)
                    self.end_headers()
                    return
                self.send_response(200)
                self.end_headers()

            def log_message(self, format, *args):
                pass

        server, thread = self._start_server(Handler)
        try:
            client = SttClient(self.base_url, self.token_file, timeout_s=2.0)
            self.assertTrue(client.health())
        finally:
            server.shutdown()
            thread.join()

    def test_health_false(self):
        token = 'health-fail'
        with open(self.token_file, 'w') as f:
            f.write(token)

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path != '/health':
                    self.send_response(404)
                    self.end_headers()
                    return
                auth = self.headers.get('Authorization')
                if auth != f'Bearer {token}':
                    self.send_response(401)
                    self.end_headers()
                    return
                self.send_response(500)  # simulate failure
                self.end_headers()

            def log_message(self, format, *args):
                pass

        server, thread = self._start_server(Handler)
        try:
            client = SttClient(self.base_url, self.token_file, timeout_s=2.0)
            self.assertFalse(client.health())
        finally:
            server.shutdown()
            thread.join()


if __name__ == '__main__':
    unittest.main()
```