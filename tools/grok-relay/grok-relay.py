"""grok-relay: watch Grok activity, relay to clod-bridge state + memory.

Watches:
  - D:\\grok\\OUTBOX\\
  - D:\\grok\\INBOX\\
  - C:\\Users\\iddo1\\.grok\\logs\\unified.jsonl

Writes:
  - D:\\CLAUDE\\tools\\clod-bridge\\state\\grok-recent.jsonl
  - C:\\Users\\iddo1\\.claude\\projects\\D--CLAUDE\\memory\\grok-recent.md
"""
import os
import sys
import time
import json
import threading
from pathlib import Path
from datetime import datetime, timezone

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

WATCH_PATHS = [
    Path(r'D:\grok\OUTBOX'),
    Path(r'D:\grok\INBOX'),
]
LOG_TAIL = Path(r'C:\Users\<user>\.grok\logs\unified.jsonl')

STATE_DIR = Path(r'D:\CLAUDE\tools\clod-bridge\state')
STATE_DIR.mkdir(parents=True, exist_ok=True)
JSONL_PATH = STATE_DIR / 'grok-recent.jsonl'
MEMORY_MD = Path(r'C:\Users\<user>\.claude\projects\D--CLAUDE\memory\grok-recent.md')

EVENTS = []
LOCK = threading.Lock()

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def record(kind, source, summary):
    ev = {'ts': now_iso(), 'kind': kind, 'source': source, 'summary': summary[:500]}
    with LOCK:
        EVENTS.append(ev)
        EVENTS[:] = EVENTS[-200:]
        with JSONL_PATH.open('a', encoding='utf-8') as f:
            f.write(json.dumps(ev, ensure_ascii=False) + '\n')
        write_memory()
    print('[{}] {} {}: {}'.format(ev['ts'], kind, source, summary[:100]), flush=True)

def write_memory():
    last = EVENTS[-20:]
    lines = [
        '---',
        'name: grok-recent',
        'description: "Last 20 Grok-side events auto-updated by grok-relay watcher. Routine refresh cron reads this so remote link shows current Grok state."',
        'metadata:',
        '  type: reference',
        '---',
        '',
        'Auto-updated by D:\\\\CLAUDE\\\\tools\\\\grok-relay\\\\grok-relay.py - last write: ' + now_iso(),
        '',
        '## Last 20 events (most recent first)',
        '',
    ]
    for ev in reversed(last):
        lines.append('- **{}** `{}` `{}` - {}'.format(ev['ts'], ev['kind'], ev['source'], ev['summary'][:200]))
    MEMORY_MD.write_text('\n'.join(lines), encoding='utf-8')

class HandoffWatcher(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return
        p = Path(event.src_path)
        if p.name.startswith('.'):
            return
        kind = 'INBOX' if 'INBOX' in str(p) else 'OUTBOX'
        try:
            txt = p.read_text(encoding='utf-8', errors='replace')[:500]
        except Exception:
            txt = '[binary/unreadable]'
        record(kind, p.name, txt)

    def on_modified(self, event):
        if event.is_directory:
            return
        p = Path(event.src_path)
        if p.name.startswith('.'):
            return
        kind = 'INBOX-mod' if 'INBOX' in str(p) else 'OUTBOX-mod'
        try:
            txt = p.read_text(encoding='utf-8', errors='replace')[:300]
        except Exception:
            return
        record(kind, p.name, txt)

def tail_unified_log():
    if not LOG_TAIL.exists():
        return
    last_size = LOG_TAIL.stat().st_size
    while True:
        try:
            cur = LOG_TAIL.stat().st_size
            if cur > last_size:
                with LOG_TAIL.open('r', encoding='utf-8', errors='replace') as f:
                    f.seek(last_size)
                    chunk = f.read(cur - last_size)
                for line in chunk.splitlines():
                    try:
                        j = json.loads(line)
                        msg = j.get('msg', '')
                        lvl = j.get('lvl', '')
                        src = j.get('src', '')
                        if lvl in ('info', 'warn', 'error') and src in ('grok-pager', 'shell'):
                            if 'prompt.enqueue' in msg or 'auth' in msg or 'error' in msg.lower():
                                record('cli-' + lvl, src, msg)
                    except json.JSONDecodeError:
                        pass
                last_size = cur
            elif cur < last_size:
                last_size = cur
        except Exception as e:
            print('tail err: ' + str(e), flush=True)
        time.sleep(2)

def main():
    for p in WATCH_PATHS:
        p.mkdir(parents=True, exist_ok=True)

    observers = []
    handler = HandoffWatcher()
    for p in WATCH_PATHS:
        obs = Observer()
        obs.schedule(handler, str(p), recursive=False)
        obs.start()
        observers.append(obs)
        print('watching ' + str(p), flush=True)

    t = threading.Thread(target=tail_unified_log, daemon=True)
    t.start()
    print('tailing ' + str(LOG_TAIL), flush=True)
    print('state -> ' + str(JSONL_PATH), flush=True)
    print('memory -> ' + str(MEMORY_MD), flush=True)

    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        for obs in observers:
            obs.stop()
        for obs in observers:
            obs.join()

if __name__ == '__main__':
    main()
