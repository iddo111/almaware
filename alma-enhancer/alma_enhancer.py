#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ALMA ENHANCER CORE — the shared-RAM organ for the AI council (CLOD/GEMINI/GPT/GROK + GUI).

100% ALMAWARE. Pure Python stdlib only (mmap, ctypes, struct, json, argparse, re).
No pip, no network, no external models.

Three named shared-memory sections (Windows, RAM-backed via mmap tagname —
alive while at least one process holds a handle; 'hold' is the life-support):

  ALMA_CTX_POOL  64 MiB  Local\\ALMA_CTX_POOL_64MB       JSONL context cards
  ALMA_ADAPT      8 MiB  Local\\ALMA_ADAPT_8MB           JSONL adapter events
  COUNCIL        10 MiB  Local\\ASCII_CHAT_COUNCIL_10MB  plain-text chat lines

Layout per section (glock-bus protocol):
  @0    text header (<= 512 bytes, magic + purpose)
  @512  HEAD, u64 little-endian = absolute offset of next free byte
  @520  magic b'ALMA'
  @1024 append-only data (UTF-8 JSONL, or plain chat lines for COUNCIL)

Writes serialize on named mutex 'Local\\<TAG>_MUTEX' (ctypes kernel32).

HONEST NAMING: 'adapt' is a prompt-side adaptation layer. It plays the ROLE of
LoRA (per-AI persistent adaptation) but the MECHANISM is folded rules injected
into the session prompt — no model weights are updated anywhere.
"""

import argparse
import ctypes
import ctypes.wintypes as wintypes
import json
import mmap
import os
import re
import struct
import sys
import time
import uuid

# ---------------------------------------------------------------- constants

MiB = 1024 * 1024
HDR_TEXT_MAX = 512
HEAD_OFF = 512
MAGIC_OFF = 520
MAGIC = b'ALMA'
DATA_OFF = 1024

HALF_LIFE_DAYS = 7.0
DECAY_FLOOR = 0.3
MUTEX_TIMEOUT_MS = 5000

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SNAP_DIR = os.path.join(SCRIPT_DIR, 'snapshots')

SECTIONS = {
    'ctx': {
        'name': 'ALMA_CTX_POOL',
        'tag': 'Local\\ALMA_CTX_POOL_64MB',
        'size': 64 * MiB,
        'kind': 'jsonl',
        'purpose': 'context cards {"id","author","topic","text","ts","weight"}',
        'snap_file': 'alma_ctx_pool.json',
    },
    'adapt': {
        'name': 'ALMA_ADAPT',
        'tag': 'Local\\ALMA_ADAPT_8MB',
        'size': 8 * MiB,
        'kind': 'jsonl',
        'purpose': 'adapter events {"ai","kind","rule","ts"} kind=style|correction|skill|fact',
        'snap_file': 'alma_adapt.json',
    },
    'chat': {
        'name': 'COUNCIL',
        'tag': 'Local\\ASCII_CHAT_COUNCIL_10MB',
        'size': 10 * MiB,
        'kind': 'text',
        'purpose': 'council chat, plain [HH:MM:SS] PARTY: msg lines (ram-council compatible)',
        'snap_file': 'council_chat.json',
    },
}


class EnhancerError(Exception):
    """Generic enhancer failure."""


class SectionDown(EnhancerError):
    """Section has no magic — no holder alive / never initialized."""


class CapacityError(EnhancerError):
    """Append would overflow the section."""


# ---------------------------------------------------------------- win32 mutex

_k32 = None


def _kernel32():
    global _k32
    if _k32 is None:
        k = ctypes.WinDLL('kernel32', use_last_error=True)
        k.CreateMutexW.restype = wintypes.HANDLE
        k.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        k.WaitForSingleObject.restype = wintypes.DWORD
        k.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        k.ReleaseMutex.restype = wintypes.BOOL
        k.ReleaseMutex.argtypes = [wintypes.HANDLE]
        k.CloseHandle.restype = wintypes.BOOL
        k.CloseHandle.argtypes = [wintypes.HANDLE]
        _k32 = k
    return _k32


WAIT_OBJECT_0 = 0x00
WAIT_ABANDONED = 0x80
WAIT_TIMEOUT = 0x102


class SectionMutex:
    """Named Win32 mutex guarding one section: 'Local\\<TAG>_MUTEX'."""

    def __init__(self, tag, timeout_ms=MUTEX_TIMEOUT_MS):
        self.name = tag + '_MUTEX'
        self.timeout_ms = timeout_ms
        self.handle = None

    def __enter__(self):
        k = _kernel32()
        h = k.CreateMutexW(None, False, self.name)
        if not h:
            raise EnhancerError('CreateMutexW failed for %s (winerr=%d)'
                                % (self.name, ctypes.get_last_error()))
        rc = k.WaitForSingleObject(h, self.timeout_ms)
        if rc not in (WAIT_OBJECT_0, WAIT_ABANDONED):
            k.CloseHandle(h)
            raise EnhancerError('mutex %s not acquired (rc=0x%X)' % (self.name, rc))
        self.handle = h
        return self

    def __exit__(self, exc_type, exc, tb):
        k = _kernel32()
        try:
            k.ReleaseMutex(self.handle)
        finally:
            k.CloseHandle(self.handle)
            self.handle = None
        return False


# ---------------------------------------------------------------- section I/O

def open_section(key):
    """Attach to (or create zeroed) the named shared-memory section."""
    spec = SECTIONS[key]
    return mmap.mmap(-1, spec['size'], tagname=spec['tag'])


def is_initialized(m):
    return m[MAGIC_OFF:MAGIC_OFF + 4] == MAGIC


def get_head(m, spec):
    head = struct.unpack('<Q', m[HEAD_OFF:HEAD_OFF + 8])[0]
    if head < DATA_OFF or head > spec['size']:
        raise EnhancerError('%s: corrupt HEAD=%d' % (spec['name'], head))
    return head


def set_head(m, head):
    m[HEAD_OFF:HEAD_OFF + 8] = struct.pack('<Q', head)


def init_section(m, spec):
    """Write text header + HEAD + magic. Caller must hold the mutex."""
    txt = ('ALMA-ENHANCER v1 :: %s :: %s :: init %s\n'
           % (spec['name'], spec['purpose'], iso_now()))
    raw = txt.encode('utf-8')[:HDR_TEXT_MAX]
    m[0:HDR_TEXT_MAX] = raw + b'\x00' * (HDR_TEXT_MAX - len(raw))
    set_head(m, DATA_OFF)
    m[MAGIC_OFF:MAGIC_OFF + 4] = MAGIC


def require_alive(m, spec):
    if not is_initialized(m):
        raise SectionDown(
            "%s (%s) is DOWN — no magic. Start the life-support first:\n"
            "  python %s hold   (detached, e.g. Start-Process -WindowStyle Hidden)"
            % (spec['name'], spec['tag'], os.path.abspath(__file__)))


def append_bytes(key, payload):
    """Mutex-guarded append at HEAD. Returns (old_head, new_head)."""
    spec = SECTIONS[key]
    with SectionMutex(spec['tag']):
        m = open_section(key)
        try:
            require_alive(m, spec)
            head = get_head(m, spec)
            new_head = head + len(payload)
            if new_head > spec['size']:
                raise CapacityError('%s full: head=%d + %dB > %dB'
                                    % (spec['name'], head, len(payload), spec['size']))
            m[head:new_head] = payload
            set_head(m, new_head)
            return head, new_head
        finally:
            m.close()


def read_section(key):
    """Mutex-guarded snapshot read. Returns (spec, header_text, head, data_bytes)."""
    spec = SECTIONS[key]
    with SectionMutex(spec['tag']):
        m = open_section(key)
        try:
            require_alive(m, spec)
            head = get_head(m, spec)
            hdr = bytes(m[0:HDR_TEXT_MAX]).split(b'\x00', 1)[0].decode('utf-8', 'replace')
            data = bytes(m[DATA_OFF:head])
            return spec, hdr, head, data
        finally:
            m.close()


def parse_jsonl(data):
    """Returns (records, bad_line_count)."""
    records, bad = [], 0
    for line in data.decode('utf-8', 'replace').splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except ValueError:
            bad += 1
    return records, bad


# ---------------------------------------------------------------- helpers

def iso_now():
    return time.strftime('%Y-%m-%dT%H:%M:%S')


def iso_of(ts):
    try:
        return time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(float(ts)))
    except (ValueError, OverflowError, OSError):
        return '?'


def tokenize(text):
    return set(re.findall(r'\w+', str(text).lower(), re.UNICODE))


def recency_decay(ts, now):
    age_days = max(0.0, (now - float(ts)) / 86400.0)
    return max(DECAY_FLOOR, 0.5 ** (age_days / HALF_LIFE_DAYS))


def score_card(card, query_tokens, now):
    """One number (gist principle): token-overlap x recency decay x stored weight."""
    if not query_tokens:
        return 0.0
    card_tokens = tokenize('%s %s %s' % (card.get('topic', ''),
                                         card.get('text', ''),
                                         card.get('author', '')))
    overlap = len(query_tokens & card_tokens) / float(len(query_tokens))
    if overlap == 0.0:
        return 0.0
    return overlap * recency_decay(card.get('ts', now), now) * float(card.get('weight', 1.0))


def rule_key(rule):
    """Normalized key for near-duplicate folding (last-wins)."""
    return ' '.join(re.findall(r'\w+', str(rule).lower(), re.UNICODE))


def print_card(card, weight=None):
    w = card.get('weight', 1.0) if weight is None else weight
    print('%.3f  [%s] %s/%s %s :: %s'
          % (float(w), card.get('id', '?'), card.get('author', '?'),
             card.get('topic', '?'), iso_of(card.get('ts', 0)), card.get('text', '')))


# ---------------------------------------------------------------- commands

def cmd_hold(args):
    handles = []
    for key in ('ctx', 'adapt', 'chat'):
        spec = SECTIONS[key]
        m = open_section(key)
        with SectionMutex(spec['tag']):
            if is_initialized(m):
                head = get_head(m, spec)
                print('[hold] %-14s attached (magic present, head=%d, used=%dB)'
                      % (spec['name'], head, head - DATA_OFF))
            else:
                init_section(m, spec)
                print('[hold] %-14s initialized fresh (head=%d)' % (spec['name'], DATA_OFF))
        handles.append(m)
    print('[hold] pid=%d holding %d sections. RAM-only: sections die with the last handle.'
          % (os.getpid(), len(handles)))
    sys.stdout.flush()
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print('[hold] released by KeyboardInterrupt')
    return 0


def cmd_status(args):
    rc = 0
    for key in ('ctx', 'adapt', 'chat'):
        spec = SECTIONS[key]
        try:
            _, _, head, data = read_section(key)
        except SectionDown:
            print('%-14s %-32s DOWN   (no magic — start "hold")' % (spec['name'], spec['tag']))
            rc = 2
            continue
        used = head - DATA_OFF
        if spec['kind'] == 'jsonl':
            records, bad = parse_jsonl(data)
            n = '%d records%s' % (len(records), (' (%d bad lines)' % bad) if bad else '')
        else:
            n = '%d lines' % len([ln for ln in data.decode('utf-8', 'replace').splitlines() if ln])
        print('%-14s %-32s ALIVE  used=%dB/%dMiB (%.4f%%)  %s'
              % (spec['name'], spec['tag'], used, spec['size'] // MiB,
                 100.0 * used / spec['size'], n))
    return rc


def _chat_lines():
    _, _, _, data = read_section('chat')
    return [ln for ln in data.decode('utf-8', 'replace').splitlines() if ln]


def cmd_chat_write(args):
    text = args.text.rstrip('\n')
    line = '[%s] %s\n' % (time.strftime('%H:%M:%S'), text)
    old, new = append_bytes('chat', line.encode('utf-8'))
    print('OK chat write %dB @%d->%d :: %s' % (new - old, old, new, line.rstrip('\n')))
    return 0


def cmd_chat_read(args):
    lines = _chat_lines()
    if args.n is not None:
        lines = lines[-args.n:]
    for ln in lines:
        print(ln)
    return 0


def cmd_chat_tail(args):
    for ln in _chat_lines()[-10:]:
        print(ln)
    return 0


def cmd_ctx_put(args):
    card = {
        'id': uuid.uuid4().hex[:12],
        'author': args.author,
        'topic': args.topic,
        'text': args.text,
        'ts': time.time(),
        'weight': 1.0,
    }
    payload = (json.dumps(card, ensure_ascii=False) + '\n').encode('utf-8')
    old, new = append_bytes('ctx', payload)
    print('OK ctx put id=%s %dB @%d->%d author=%s topic=%s'
          % (card['id'], new - old, old, new, card['author'], card['topic']))
    return 0


def cmd_ctx_get(args):
    _, _, _, data = read_section('ctx')
    records, _ = parse_jsonl(data)
    now = time.time()
    qtok = tokenize(args.query)
    scored = [(score_card(c, qtok, now), c) for c in records]
    scored = [(s, c) for s, c in scored if s > 0.0]
    scored.sort(key=lambda sc: sc[0], reverse=True)
    top = scored[:args.n]
    if not top:
        print('(no matching cards for query: %s)' % args.query)
        return 1
    for s, c in top:
        print_card(c, weight=s)
    return 0


def cmd_ctx_list(args):
    _, _, _, data = read_section('ctx')
    records, bad = parse_jsonl(data)
    for c in records[-args.n:][::-1]:
        print_card(c)
    if bad:
        print('(warning: %d unparseable lines)' % bad)
    return 0


def cmd_adapt_learn(args):
    event = {'ai': args.ai.upper(), 'kind': args.kind, 'rule': args.rule, 'ts': time.time()}
    payload = (json.dumps(event, ensure_ascii=False) + '\n').encode('utf-8')
    old, new = append_bytes('adapt', payload)
    print('OK adapt learn ai=%s kind=%s %dB @%d->%d :: %s'
          % (event['ai'], event['kind'], new - old, old, new, event['rule']))
    return 0


def cmd_adapt_profile(args):
    _, _, _, data = read_section('adapt')
    records, _ = parse_jsonl(data)
    ai = args.ai.upper()
    folded = {}  # rule_key -> event (last wins)
    total = 0
    for ev in records:
        if str(ev.get('ai', '')).upper() != ai:
            continue
        total += 1
        folded[rule_key(ev.get('rule', ''))] = ev
    events = sorted(folded.values(), key=lambda e: float(e.get('ts', 0)))
    print('### ALMA ADAPT PROFILE :: %s :: %d rules (folded from %d events)' % (ai, len(events), total))
    print('### prompt-side adaptation layer — inject this block at session start.')
    print('### (LoRA-like in role, honest in mechanism: no model weights are updated)')
    if not events:
        print('(no rules learned yet for %s)' % ai)
        return 1
    order = ['style', 'correction', 'skill', 'fact']
    for kind in order + sorted(set(e.get('kind', '?') for e in events) - set(order)):
        for ev in events:
            if ev.get('kind') == kind:
                print('- [%s] %s  (%s)' % (kind, ev.get('rule', ''), iso_of(ev.get('ts', 0))))
    return 0


def cmd_snapshot(args):
    outdir = args.dir or DEFAULT_SNAP_DIR
    os.makedirs(outdir, exist_ok=True)
    for key in ('ctx', 'adapt', 'chat'):
        spec, hdr, head, data = read_section(key)
        if spec['kind'] == 'jsonl':
            records, bad = parse_jsonl(data)
            body = {'records': records, 'bad_lines': bad}
        else:
            body = {'lines': [ln for ln in data.decode('utf-8', 'replace').splitlines() if ln]}
        doc = {'section': spec['name'], 'tag': spec['tag'], 'size': spec['size'],
               'kind': spec['kind'], 'header_text': hdr, 'head': head,
               'used_bytes': head - DATA_OFF, 'saved_at': iso_now()}
        doc.update(body)
        path = os.path.join(outdir, spec['snap_file'])
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(doc, f, ensure_ascii=False, indent=1)
        print('OK snapshot %-14s -> %s (%dB used)' % (spec['name'], path, head - DATA_OFF))
    return 0


def _record_key(rec):
    """Dedup identity for a jsonl record: prefer its id, else its canonical JSON."""
    rid = rec.get('id')
    if rid:
        return ('id', rid)
    return ('json', json.dumps(rec, ensure_ascii=False, sort_keys=True))


def _union(live_items, snap_items, key_fn):
    """Union preserving live first (never drop newer live data), snapshot fills gaps."""
    seen, out = set(), []
    for item in live_items + snap_items:
        k = key_fn(item)
        if k not in seen:
            seen.add(k)
            out.append(item)
    return out


def cmd_restore(args):
    """Load sections from snapshot files. SAFE BY DEFAULT: a plain restore refuses to
    destroy live items the snapshot lacks. Use --merge to union live+snapshot, or
    --force to overwrite live state with the snapshot verbatim."""
    indir = args.dir or DEFAULT_SNAP_DIR
    merge = getattr(args, 'merge', False)
    force = getattr(args, 'force', False)
    rc = 0
    for key in ('ctx', 'adapt', 'chat'):
        spec = SECTIONS[key]
        path = os.path.join(indir, spec['snap_file'])
        if not os.path.isfile(path):
            print('SKIP restore %-14s (no file %s)' % (spec['name'], path))
            continue
        with open(path, 'r', encoding='utf-8') as f:
            doc = json.load(f)
        with SectionMutex(spec['tag']):
            m = open_section(key)
            try:
                require_alive(m, spec)   # RAM-only: restoring into a dead section is lost work
                live_head = get_head(m, spec)
                live_used = live_head - DATA_OFF
                live_data = bytes(m[DATA_OFF:live_head])

                if spec['kind'] == 'jsonl':
                    live_items, _ = parse_jsonl(live_data)
                    snap_items = doc.get('records', [])
                    key_fn = _record_key
                    dump = lambda r: json.dumps(r, ensure_ascii=False) + '\n'
                else:
                    live_items = [ln for ln in live_data.decode('utf-8', 'replace').splitlines() if ln]
                    snap_items = doc.get('lines', [])
                    key_fn = lambda ln: ln
                    dump = lambda ln: ln + '\n'

                if merge:
                    out_items = _union(live_items, snap_items, key_fn)
                else:
                    out_items = snap_items
                    # SAFETY GUARD: in replace mode, never silently drop live items the snapshot lacks.
                    snap_keys = set(key_fn(i) for i in snap_items)
                    lost = [i for i in live_items if key_fn(i) not in snap_keys]
                    if live_used > 0 and lost and not force:
                        print('REFUSE restore %-14s: replace would DESTROY %d live item(s) '
                              'absent from the snapshot (live=%d, snapshot=%d). '
                              'Use --merge to union, or --force to overwrite anyway.'
                              % (spec['name'], len(lost), len(live_items), len(snap_items)))
                        rc = 5
                        continue

                payload = ''.join(dump(i) for i in out_items)
                raw = payload.encode('utf-8')
                if DATA_OFF + len(raw) > spec['size']:
                    print('FAIL restore %s: %dB exceeds section' % (spec['name'], len(raw)))
                    rc = 4
                    continue
                m[DATA_OFF:DATA_OFF + len(raw)] = raw
                set_head(m, DATA_OFF + len(raw))
                if len(raw) < live_used:   # zero the freed tail so stale bytes never reparse
                    m[DATA_OFF + len(raw):live_head] = b'\x00' * (live_used - len(raw))
            finally:
                m.close()
        mode = 'merge' if merge else ('force-replace' if force else 'replace')
        print('OK restore %-14s <- %s (%s: live=%d snap=%d -> %d, %dB)'
              % (spec['name'], path, mode, len(live_items), len(snap_items),
                 len(out_items), len(raw)))
    return rc


# ---------------------------------------------------------------- CLI

def build_parser():
    p = argparse.ArgumentParser(
        prog='alma_enhancer.py',
        description='ALMA Enhancer CORE — shared-RAM context pool, adapter layer, and council chat.',
        epilog='Life-support: run "hold" detached first; sections are RAM-only and die with it.')
    sub = p.add_subparsers(dest='cmd', required=True)

    sp = sub.add_parser('hold', help='open/create all sections, init if needed, sleep forever')
    sp.set_defaults(func=cmd_hold)

    sp = sub.add_parser('status', help='per-section: alive? bytes used? record/line count')
    sp.set_defaults(func=cmd_status)

    chat = sub.add_parser('chat', help='council chat (plain text lines, ram-council compatible)')
    chat_sub = chat.add_subparsers(dest='chat_cmd', required=True)
    sp = chat_sub.add_parser('write', help='append \'PARTY: msg\' with timestamp')
    sp.add_argument('text')
    sp.set_defaults(func=cmd_chat_write)
    sp = chat_sub.add_parser('read', help='print all lines (or last N)')
    sp.add_argument('n', nargs='?', type=int, default=None)
    sp.set_defaults(func=cmd_chat_read)
    sp = chat_sub.add_parser('tail', help='print last 10 lines')
    sp.set_defaults(func=cmd_chat_tail)

    ctx = sub.add_parser('ctx', help='shared context pool (JSONL cards)')
    ctx_sub = ctx.add_subparsers(dest='ctx_cmd', required=True)
    sp = ctx_sub.add_parser('put', help='deposit a context card (weight starts 1.0)')
    sp.add_argument('--author', required=True)
    sp.add_argument('--topic', required=True)
    sp.add_argument('text')
    sp.set_defaults(func=cmd_ctx_put)
    sp = ctx_sub.add_parser('get', help='recall top-K: token-overlap x recency decay '
                                        '(half-life 7d, floor 0.3) — one weight number')
    sp.add_argument('query')
    sp.add_argument('-n', type=int, default=5)
    sp.set_defaults(func=cmd_ctx_get)
    sp = ctx_sub.add_parser('list', help='newest N cards')
    sp.add_argument('-n', type=int, default=10)
    sp.set_defaults(func=cmd_ctx_list)

    adapt = sub.add_parser('adapt', help='per-AI adaptation rules (prompt-side LoRA-like layer; '
                                         'no weights updated)')
    adapt_sub = adapt.add_subparsers(dest='adapt_cmd', required=True)
    sp = adapt_sub.add_parser('learn', help='record a rule event')
    sp.add_argument('--ai', required=True)
    sp.add_argument('--kind', required=True, choices=['style', 'correction', 'skill', 'fact'])
    sp.add_argument('rule')
    sp.set_defaults(func=cmd_adapt_learn)
    sp = adapt_sub.add_parser('profile', help='folded profile (last-wins per near-duplicate rule) '
                                              '— printable block to inject into any AI session')
    sp.add_argument('--ai', required=True)
    sp.set_defaults(func=cmd_adapt_profile)

    sp = sub.add_parser('snapshot', help='dump all sections to JSON files (manual; RAM-only otherwise)')
    sp.add_argument('--dir', default=None)
    sp.set_defaults(func=cmd_snapshot)

    sp = sub.add_parser('restore', help='load sections from JSON files (SAFE: refuses to drop live items; --merge to union, --force to overwrite)')
    sp.add_argument('--dir', default=None)
    sp.add_argument('--merge', action='store_true',
                    help='union live + snapshot (dedup by id/line) instead of replacing')
    sp.add_argument('--force', action='store_true',
                    help='overwrite live state with the snapshot even if live items would be lost')
    sp.set_defaults(func=cmd_restore)
    return p


def force_utf8():
    """Hebrew-safe stdout/stderr on Windows consoles."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError, OSError):
            pass


def main(argv=None):
    force_utf8()
    if os.name != 'nt':
        print('ERROR: alma_enhancer v1 is Windows-only (mmap tagname + Win32 named mutex).')
        return 3
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except SectionDown as e:
        print('ERROR: %s' % e)
        return 2
    except CapacityError as e:
        print('ERROR: %s' % e)
        return 4
    except EnhancerError as e:
        print('ERROR: %s' % e)
        return 5


if __name__ == '__main__':
    sys.exit(main())
