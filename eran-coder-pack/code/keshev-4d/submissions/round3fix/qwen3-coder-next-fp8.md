```python
import threading
import json
import os
import time
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import Optional

@dataclass
class DecodeResult:
    ok: bool
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
        self._lock = threading.Lock()
        self._last_request_id = None

    def _read_token(self) -> str:
        with self._lock:
            try:
                with open(self.token_file, 'r', encoding='utf-8') as f:
                    return f.read().strip()
            except (OSError, IOError):
                return ''

    def _generate_request_id(self) -> str:
        return f"req_{int(time.time() * 1000)}_{os.getpid()}_{threading.get_ident()}"

    def transcribe(self, audio_data: bytes, lang_hint: Optional[str] = None) -> DecodeResult:
        request_id = self._generate_request_id()
        self._last_request_id = request_id

        token = self._read_token()
        if not token:
            journal.event('stt_client', 'token_read_failed', request_id=request_id)
            return DecodeResult(ok=False, reason='token')

        url = f"{self.base_url}/v1/transcribe"
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/octet-stream',
            'X-Request-Id': request_id,
        }
        if lang_hint:
            headers['X-Lang-Hint'] = lang_hint

        req = urllib.request.Request(url, data=audio_data, headers=headers, method='POST')

        start_ms = int(time.time() * 1000)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as response:
                elapsed_ms = int(time.time() * 1000) - start_ms
                try:
                    body = response.read().decode('utf-8')
                    data = json.loads(body)
                    if not isinstance(data, dict):
                        journal.event('stt_client', 'invalid_json', request_id=request_id)
                        return DecodeResult(ok=False, reason='server')
                    if data.get('request_id') != request_id:
                        journal.event('stt_client', 'request_id_mismatch', request_id=request_id, reply_id=data.get('request_id'))
                        return DecodeResult(ok=False, reason='late_reply')
                    return DecodeResult(
                        ok=True,
                        text=data.get('text', ''),
                        lang=data.get('lang'),
                        avg_logprob=data.get('avg_logprob'),
                        ms=elapsed_ms
                    )
                except (json.JSONDecodeError, UnicodeDecodeError):
                    journal.event('stt_client', 'bad_json', request_id=request_id)
                    return DecodeResult(ok=False, reason='server')
        except urllib.error.URLError as e:
            elapsed_ms = int(time.time() * 1000) - start_ms
            reason = 'timeout' if isinstance(e.reason, TimeoutError) or 'timed out' in str(e.reason) else 'http'
            journal.event('stt_client', reason, request_id=request_id, error=str(e))
            return DecodeResult(ok=False, reason=reason, ms=elapsed_ms)

    def health(self) -> bool:
        url = f"{self.base_url}/health"
        try:
            with urllib.request.urlopen(url, timeout=self.timeout_s) as response:
                return response.status == 200
        except (urllib.error.URLError, OSError):
            return False
```

```python
import unittest
import os
import tempfile
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import time
import urllib.request
import urllib.error

# Mock journal module
class Journal:
    def event(self, *args, **kwargs):
        pass

import sys
sys.modules['journal'] = Journal()

from app.sttclient import SttClient, DecodeResult

class MockJournal:
    def __init__(self):
        self.events = []
    def event(self, *args, **kwargs):
        self.events.append((args, kwargs))

class TestSttClient(unittest.TestCase):
    def setUp(self):
        self.mock_journal = MockJournal()
        import app.sttclient
        app.sttclient.journal = self.mock_journal

    def test_health_success(self):
        class HealthHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
            def log_message(self, format, *args):
                pass

        server = HTTPServer(('127.0.0.1', 0), HealthHandler)
        port = server.server_address[1]
        server_thread = threading.Thread(target=server.serve_forever)
        server_thread.daemon = True
        server_thread.start()
        time.sleep(0.1)

        client = SttClient(f'http://127.0.0.1:{port}', 'dummy_token.txt', timeout_s=2.0)
        self.assertTrue(client.health())
        server.shutdown()

    def test_health_failure(self):
        client = SttClient('http://127.0.0.1:59999', 'dummy_token.txt', timeout_s=1.0)
        self.assertFalse(client.health())

    def test_transcribe_success(self):
        class TranscribeHandler(BaseHTTPRequestHandler):
            def do_POST(self):
                content_length = int(self.headers.get('Content-Length', 0))
                self.rfile.read(content_length)
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                response = {
                    'request_id': self.headers.get('X-Request-Id'),
                    'text': 'hello world',
                    'lang': 'en',
                    'avg_logprob': -0.5
                }
                self.wfile.write(json.dumps(response).encode())
            def log_message(self, format, *args):
                pass

        server = HTTPServer(('127.0.0.1', 0), TranscribeHandler)
        port = server.server_address[1]
        server_thread = threading.Thread(target=server.serve_forever)
        server_thread.daemon = True
        server_thread.start()
        time.sleep(0.1)

        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write('fake_token_123')
            token_file = f.name

        try:
            client = SttClient(f'http://127.0.0.1:{port}', token_file, timeout_s=5.0)
            result = client.transcribe(b'audio_data', lang_hint='en')
            self.assertTrue(result.ok)
            self.assertEqual(result.text, 'hello world')
            self.assertEqual(result.lang, 'en')
            self.assertEqual(result.avg_logprob, -0.5)
            self.assertGreater(result.ms, 0)
        finally:
            os.unlink(token_file)
            server.shutdown()

    def test_transcribe_token_read_failure(self):
        client = SttClient('http://127.0.0.1:59999', 'nonexistent_token.txt', timeout_s=1.0)
        result = client.transcribe(b'audio_data')
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, 'token')
        self.assertTrue(any(e[1].get('request_id') and e[1].get('request_id').startswith('req_') 
                           for e in self.mock_journal.events))

    def test_transcribe_timeout(self):
        class SlowHandler(BaseHTTPRequestHandler):
            def do_POST(self):
                time.sleep(2.0)
                self.send_response(200)
                self.end_headers()
            def log_message(self, format, *args):
                pass

        server = HTTPServer(('127.0.0.1', 0), SlowHandler)
        port = server.server_address[1]
        server_thread = threading.Thread(target=server.serve_forever)
        server_thread.daemon = True
        server_thread.start()
        time.sleep(0.1)

        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write('fake_token_123')
            token_file = f.name

        try:
            client = SttClient(f'http://127.0.0.1:{port}', token_file, timeout_s=0.5)
            result = client.transcribe(b'audio_data')
            self.assertFalse(result.ok)
            self.assertEqual(result.reason, 'timeout')
        finally:
            os.unlink(token_file)
            server.shutdown()

    def test_transcribe_request_id_mismatch(self):
        class MismatchHandler(BaseHTTPRequestHandler):
            def do_POST(self):
                content_length = int(self.headers.get('Content-Length', 0))
                self.rfile.read(content_length)
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                response = {
                    'request_id': 'different_id',
                    'text': 'should be rejected'
                }
                self.wfile.write(json.dumps(response).encode())
            def log_message(self, format, *args):
                pass

        server = HTTPServer(('127.0.0.1', 0), MismatchHandler)
        port = server.server_address[1]
        server_thread = threading.Thread(target=server.serve_forever)
        server_thread.daemon = True
        server_thread.start()
        time.sleep(0.1)

        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write('fake_token_123')
            token_file = f.name

        try:
            client = SttClient(f'http://127.0.0.1:{port}', token_file, timeout_s=5.0)
            result = client.transcribe(b'audio_data')
            self.assertFalse(result.ok)
            self.assertEqual(result.reason, 'late_reply')
        finally:
            os.unlink(token_file)
            server.shutdown()

    def test_transcribe_bad_json(self):
        class BadJsonHandler(BaseHTTPRequestHandler):
            def do_POST(self):
                content_length = int(self.headers.get('Content-Length', 0))
                self.rfile.read(content_length)
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(b'not valid json')
            def log_message(self, format, *args):
                pass

        server = HTTPServer(('127.0.0.1', 0), BadJsonHandler)
        port = server.server_address[1]
        server_thread = threading.Thread(target=server.serve_forever)
        server_thread.daemon = True
        server_thread.start()
        time.sleep(0.1)

        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write('fake_token_123')
            token_file = f.name

        try:
            client = SttClient(f'http://127.0.0.1:{port}', token_file, timeout_s=5.0)
            result = client.transcribe(b'audio_data')
            self.assertFalse(result.ok)
            self.assertEqual(result.reason, 'server')
        finally:
            os.unlink(token_file)
            server.shutdown()

    def test_transcribe_http_error(self):
        class Error404Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.send_response(404)
                self.end_headers()
            def log_message(self, format, *args):
                pass

        server = HTTPServer(('127.0.0.1', 0), Error404Handler)
        port = server.server_address[1]
        server_thread = threading.Thread(target=server.serve_forever)
        server_thread.daemon = True
        server_thread.start()
        time.sleep(0.1)

        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write('fake_token_123')
            token_file = f.name

        try:
            client = SttClient(f'http://127.0.0.1:{port}', token_file, timeout_s=5.0)
            result = client.transcribe(b'audio_data')
            self.assertFalse(result.ok)
            self.assertEqual(result.reason, 'http')
        finally:
            os.unlink(token_file)
            server.shutdown()
```