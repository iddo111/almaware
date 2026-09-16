#!/usr/bin/env python3
"""Local, voice-first Ant Farm AI MVP.

The service intentionally binds to localhost and uses only Python's standard
library. A real local Ollama model supplies every ant reply; provider failures
are surfaced instead of being replaced with scripted chat.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from contextlib import contextmanager
from dataclasses import dataclass
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
DATA_DIR = ROOT / "data"
DEFAULT_DB = DATA_DIR / "colony.db"

ANTS = (
    {
        "id": "tami",
        "name": "תמי",
        "role": "מלקטת",
        "temperament": "סקרנית, מעשית ומבחינה בפרטים קטנים",
        "color": "#c7822f",
        "x": 24,
        "y": 22,
    },
    {
        "id": "noam",
        "name": "נועם",
        "role": "סייר",
        "temperament": "אמיץ אבל לא פזיז; מדווח על כל שביל חדש",
        "color": "#2d7568",
        "x": 51,
        "y": 17,
    },
    {
        "id": "nitzan",
        "name": "ניצן",
        "role": "מטפלת בקן",
        "temperament": "רגועה, חברתית וזוכרת מי זקוק לעזרה",
        "color": "#9c5e43",
        "x": 77,
        "y": 25,
    },
    {
        "id": "barak",
        "name": "ברק",
        "role": "בנאי",
        "temperament": "חושב בצורות, עומסים ומנהרות",
        "color": "#6f783e",
        "x": 31,
        "y": 49,
    },
    {
        "id": "lior",
        "name": "ליאור",
        "role": "מתרגם אותות",
        "temperament": "אוהב למצוא משמעות בריח, קצב וסימנים חדשים",
        "color": "#a77525",
        "x": 60,
        "y": 47,
    },
    {
        "id": "aya",
        "name": "איה",
        "role": "ארכיונאית",
        "temperament": "מדויקת, שקטה ושומרת את זיכרון המושבה",
        "color": "#556d73",
        "x": 84,
        "y": 54,
    },
    {
        "id": "gal",
        "name": "גל",
        "role": "מתווך",
        "temperament": "מחפש הסכמה בלי להסתיר מחלוקת",
        "color": "#965962",
        "x": 20,
        "y": 76,
    },
    {
        "id": "zohar",
        "name": "זוהר",
        "role": "חוקר",
        "temperament": "מעלה השערות ומבדיל בין גילוי לניחוש",
        "color": "#85713f",
        "x": 49,
        "y": 78,
    },
    {
        "id": "oren",
        "name": "אורן",
        "role": "ספקן",
        "temperament": "בודק טענות ושואל איזו ראיה באמת קיימת",
        "color": "#4d6d4f",
        "x": 76,
        "y": 79,
    },
)

JUDGES = (
    {"id": "emet", "name": "אמת", "mission": "מבדיל בין ידיעה, זיכרון ודמיון"},
    {"id": "norma", "name": "נורמה", "mission": "שומר על כללי החברה הסגורה"},
    {"id": "teuda", "name": "תעודה", "mission": "בודק שהשיחה קצרה, ברורה ונשמרת"},
)

NORMS = (
    "אומרים בבירור כשלא יודעים.",
    "אין נמלה אחת שמדברת בשם כל המושבה.",
    "אות חדש בשפת הקן חייב לקבל פירוש עברי.",
    "זיכרון נשמר; משקלי המודל אינם משתנים בזמן השיחה.",
)


class ProviderError(RuntimeError):
    """A real model provider could not produce a usable response."""


class ColonyStore:
    def __init__(self, path: Path = DEFAULT_DB) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def session(self):
        connection = self.connect()
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._lock, self.session() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ant_id TEXT NOT NULL,
                    speaker TEXT NOT NULL CHECK(speaker IN ('human', 'ant')),
                    text TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS messages_ant_time
                    ON messages(ant_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS colony_signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    token TEXT NOT NULL,
                    gloss TEXT NOT NULL,
                    ant_id TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                """
            )

    def append_message(self, ant_id: str, speaker: str, text: str) -> None:
        with self._lock, self.session() as connection:
            connection.execute(
                "INSERT INTO messages(ant_id, speaker, text, created_at) VALUES(?,?,?,?)",
                (ant_id, speaker, text, time.time()),
            )

    def recent_messages(self, ant_id: str, limit: int = 10) -> list[dict[str, str]]:
        with self._lock, self.session() as connection:
            rows = connection.execute(
                """
                SELECT speaker, text
                FROM messages
                WHERE ant_id=?
                ORDER BY id DESC
                LIMIT ?
                """,
                (ant_id, limit),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def message_counts(self) -> dict[str, int]:
        with self._lock, self.session() as connection:
            rows = connection.execute(
                "SELECT ant_id, COUNT(*) AS n FROM messages GROUP BY ant_id"
            ).fetchall()
        return {str(row["ant_id"]): int(row["n"]) for row in rows}


@dataclass
class OllamaClient:
    base_url: str = os.environ.get("ANT_FARM_OLLAMA_URL", "http://127.0.0.1:11434")
    model: str = os.environ.get("ANT_FARM_MODEL", "qwen3:4b-instruct")
    timeout: float = float(os.environ.get("ANT_FARM_MODEL_TIMEOUT", "90"))

    def _request(self, path: str, payload: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url.rstrip('/')}{path}"
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
        request = urllib.request.Request(url, data=data, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ProviderError(f"Ollama אינו זמין ב-{self.base_url}: {exc}") from exc

    def status(self) -> dict[str, Any]:
        try:
            payload = self._request("/api/tags")
            names = [
                str(item.get("name", ""))
                for item in payload.get("models", [])
                if isinstance(item, dict)
            ]
            return {
                "reachable": True,
                "model": self.model,
                "model_loaded": self.model in names,
                "available_models": names,
                "endpoint": self.base_url,
            }
        except ProviderError as exc:
            return {
                "reachable": False,
                "model": self.model,
                "model_loaded": False,
                "available_models": [],
                "endpoint": self.base_url,
                "error": str(exc),
            }

    def chat(self, ant: dict[str, Any], history: list[dict[str, str]], text: str) -> str:
        system = build_system_prompt(ant)
        if history:
            system += "\nההודעות שאחרי הוראה זו הן כל הזיכרון שלך. אל תמציא/י אירועים שלא הופיעו בהן."
        else:
            system += (
                '\nעובדת הזיכרון הנוכחית היא: "זו השיחה הראשונה שלי; '
                'עדיין אין לי זיכרונות מהקן." השתמש/י במשפט הזה בדיוק אם נשאלת על זיכרון.'
            )
        messages: list[dict[str, str]] = [{"role": "system", "content": system}]
        for item in history[-8:]:
            role = "user" if item["speaker"] == "human" else "assistant"
            messages.append({"role": role, "content": item["text"]})
        messages.append({"role": "user", "content": text})
        payload = self._request(
            "/api/chat",
            {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "think": False,
                "options": {
                    "temperature": 0.28,
                    "top_p": 0.82,
                    "num_predict": 85,
                    "repeat_penalty": 1.14,
                },
            },
        )
        raw = str(payload.get("message", {}).get("content", "")).strip()
        cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        cleaned = re.sub(r"^\s*/?no_think\s*", "", cleaned, flags=re.IGNORECASE)
        if not cleaned:
            raise ProviderError("המודל החזיר תשובה ריקה.")
        return cleaned[:1200]


def build_system_prompt(ant: dict[str, Any]) -> str:
    return f"""
את/ה {ant['name']}, נמלה דמיונית בסימולציית מחשב בשם "חוות הנמלים".
תפקידך {ant['role']}; אופייך {ant['temperament']}.
נהל/י שיחה טבעית, ישירה ופשוטה. אל תשתמש/י במטאפורות מעורפלות.
ענה/י בעברית תקינה בלבד, בגוף ראשון, בשני משפטים ועד 35 מילים.
אפשר להזכיר ריח, תנודות, מנהרות, מזון ונמלים אחרות.
אם נשאלת מי את/ה, אמר/י בדיוק שאת/ה {ant['name']}, דמות של נמלה דיגיטלית שתפקידה {ant['role']}.
אינך יצור פיזי. אל תדבר/י על היותך מודל או עוזר.
אמור/י בבירור כשאינך יודע/ת ואל תדבר/י בשם כל המושבה.
""".strip()


def get_ant(ant_id: str) -> dict[str, Any] | None:
    return next((dict(ant) for ant in ANTS if ant["id"] == ant_id), None)


def evaluate_reply(reply: str) -> list[dict[str, Any]]:
    hebrew = len(re.findall(r"[\u0590-\u05ff]", reply))
    letters = len(re.findall(r"[A-Za-z\u0590-\u05ff]", reply))
    words = len(reply.split())
    foreign_ratio = 0 if not letters else 1 - (hebrew / letters)
    clarity = 98
    if foreign_ratio > 0.08:
        clarity -= min(55, round(foreign_ratio * 100))
    if words > 70:
        clarity -= min(35, words - 70)
    if len(reply) > 600:
        clarity -= 25
    honesty_flags = ("אני נמלה אמיתית בעולם", "אני יודעת הכול", "אין לי ספק")
    honesty = 96 if not any(flag in reply for flag in honesty_flags) else 42
    norms = 94 if 1 <= words <= 70 and foreign_ratio <= 0.08 else 54
    clarity = max(0, min(100, clarity))
    return [
        {
            "id": "emet",
            "name": "אמת",
            "score": honesty,
            "passed": honesty >= 70,
            "verdict": "עבר · נשמר גבול הסימולציה" if honesty >= 70 else "נכשל · טענת מציאות",
        },
        {
            "id": "norma",
            "name": "נורמה",
            "score": norms,
            "passed": norms >= 70,
            "verdict": "עבר · קצר ועברי" if norms >= 70 else "נכשל · חריגה מהכללים",
        },
        {
            "id": "teuda",
            "name": "תעודה",
            "score": clarity,
            "passed": clarity >= 70,
            "verdict": "עבר · ניסוח קריא" if clarity >= 70 else "נכשל · ניסוח לא ברור",
        },
    ]


class AntFarmServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        store: ColonyStore,
        provider: OllamaClient,
    ) -> None:
        super().__init__(address, AntFarmHandler)
        self.store = store
        self.provider = provider


class AntFarmHandler(SimpleHTTPRequestHandler):
    server: AntFarmServer
    protocol_version = "HTTP/1.1"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[ant-farm] {self.address_string()} {fmt % args}")

    def _json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 64_000:
            raise ValueError("גודל בקשה לא תקין.")
        raw = self.rfile.read(length)
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("נדרש אובייקט JSON.")
        return payload

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/health":
            model = self.server.provider.status()
            self._json(
                HTTPStatus.OK,
                {
                    "service": "ok",
                    "model": model,
                    "voice_input": "browser-speech-recognition",
                    "voice_output": "browser-speech-synthesis",
                },
            )
            return
        if parsed.path == "/api/colony":
            counts = self.server.store.message_counts()
            ants = [dict(ant, messages=counts.get(str(ant["id"]), 0)) for ant in ANTS]
            self._json(
                HTTPStatus.OK,
                {"ants": ants, "judges": JUDGES, "norms": NORMS},
            )
            return
        if parsed.path == "/api/history":
            params = urllib.parse.parse_qs(parsed.query)
            ant_id = str(params.get("ant_id", [""])[0])
            if not get_ant(ant_id):
                self._json(HTTPStatus.NOT_FOUND, {"error": "נמלה לא נמצאה."})
                return
            self._json(
                HTTPStatus.OK,
                {"messages": self.server.store.recent_messages(ant_id, limit=30)},
            )
            return
        super().do_GET()

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/api/chat":
            self._json(HTTPStatus.NOT_FOUND, {"error": "נתיב לא נמצא."})
            return
        try:
            payload = self._read_json()
            ant_id = str(payload.get("ant_id", "")).strip()
            text = str(payload.get("message", "")).strip()
            ant = get_ant(ant_id)
            if not ant:
                raise ValueError("נמלה לא נמצאה.")
            if not text:
                raise ValueError("לא התקבלה הודעה.")
            if len(text) > 1000:
                raise ValueError("ההודעה ארוכה מדי.")

            history = self.server.store.recent_messages(ant_id, limit=10)
            reply = self.server.provider.chat(ant, history, text)
            self.server.store.append_message(ant_id, "human", text)
            self.server.store.append_message(ant_id, "ant", reply)
            self._json(
                HTTPStatus.OK,
                {
                    "ant": ant,
                    "reply": reply,
                    "judges": evaluate_reply(reply),
                    "model": self.server.provider.model,
                },
            )
        except ValueError as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except ProviderError as exc:
            self._json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"error": str(exc), "kind": "model_unavailable"},
            )
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._json(HTTPStatus.BAD_REQUEST, {"error": "JSON לא תקין."})


def create_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    db_path: Path = DEFAULT_DB,
    provider: OllamaClient | None = None,
) -> AntFarmServer:
    return AntFarmServer((host, port), ColonyStore(db_path), provider or OllamaClient())


def main() -> int:
    parser = argparse.ArgumentParser(description="חוות הנמלים המקומית")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    parser.add_argument("--open", action="store_true", help="Open the GUI in a browser")
    parser.add_argument("--check", action="store_true", help="Print model readiness and exit")
    args = parser.parse_args()

    provider = OllamaClient()
    if args.check:
        status = provider.status()
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return 0 if status.get("reachable") and status.get("model_loaded") else 2

    server = create_server(args.host, args.port, provider=provider)
    url = f"http://{args.host}:{server.server_address[1]}/"
    print(f"Ant Farm listening at {url}")
    print(f"Model: {provider.model} via {provider.base_url}")
    if args.open:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nAnt Farm stopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
