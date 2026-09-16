#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ALMA WRAP — THE WRAPPER that turns the Enhancer from storage into an enhancer.

100% ALMAWARE. Pure Python stdlib only (argparse, json, os, subprocess, sys,
time, urllib). No pip. Model backends are external CLIs / the OpenAI HTTP API.

Every AI model call goes THROUGH this shim and comes out augmented with:
  (a) that AI's adapter profile   [LoRA-like prompt-side layer]
  (b) the top-K shared-context cards [larger shared context window]
and every answer is written BACK to the shared pool so all AIs benefit
[shared memory].

It imports alma_enhancer as a module and calls its section-access functions
directly (read_section / append_bytes / parse_jsonl / score_card / rule_key)
— it does NOT reimplement the RAM protocol.

CLI:
  alma_wrap --ai NAME --model claude|grok|gpt-api|grok-web|gpt-web|gemini-web
            [-k K] [--no-writeback] [--dry-run] [--council] "PROMPT"

Flow:
  1. ENHANCE-IN  : fold the AI's adapter rules + recall top-K context cards,
                   compose one compact augmented prompt.
  2. --dry-run   : print the augmented prompt and exit (zero model cost).
  3. CALL MODEL  : route to the chosen backend; capture the answer.
  4. ENHANCE-OUT : writeback a prompt->answer digest as a shared card (unless
                   --no-writeback). "REMEMBER: ..." prompts also learn a fact.
  5. TRACE       : print the answer + a one-line [wrap ...] trace.
  --council      : also post a one-line summary to the council chat as <AI>:.
"""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error

# --- import the Enhancer core as a module (same dir) ----------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
import alma_enhancer as E  # noqa: E402

# --- backend locations (proven on this machine) ---------------------------
CLAUDE_EXE = r'C:/Users/<user>/.local/bin/claude.exe'
GROK_EXE = r'C:/Users/<user>/.grok/bin/grok.exe'
WEBBRAIN_PY = r'D:/CLAUDE/alma-webbrain/alma_webbrain.py'
OPENAI_KEY_FILE = r'C:/Users/<user>/.secrets/openai_api_key.txt'
OPENAI_MODEL_FILE = r'C:/Users/<user>/.secrets/openai_model.txt'
OPENAI_URL = 'https://api.openai.com/v1/chat/completions'

WEB_SITE = {'grok-web': 'grok', 'gpt-web': 'gpt', 'gemini-web': 'gemini'}

CTX_BLOCK_CAP = 2000   # chars for the [SHARED CONTEXT] block
DIGEST_CAP = 800       # chars for the writeback card text
TOPIC_CAP = 40         # chars for the writeback card topic


# =========================================================================
# ENHANCE-IN  (uses the Enhancer's own scoring / folding — no reimplement)
# =========================================================================

def fold_adapter(ai):
    """Return (profile_text, rule_count) for AI from ALMA_ADAPT.

    Folds near-duplicate rules last-wins exactly like adapt profile, ordered
    style > correction > skill > fact, using E.rule_key + E.parse_jsonl.
    """
    ai = ai.upper()
    _, _, _, data = E.read_section('adapt')
    records, _ = E.parse_jsonl(data)
    folded = {}  # rule_key -> event (last wins)
    for ev in records:
        if str(ev.get('ai', '')).upper() != ai:
            continue
        folded[E.rule_key(ev.get('rule', ''))] = ev
    events = sorted(folded.values(), key=lambda e: float(e.get('ts', 0)))
    if not events:
        return '(none yet)', 0
    order = ['style', 'correction', 'skill', 'fact']
    kinds = order + sorted(set(e.get('kind', '?') for e in events) - set(order))
    lines = []
    for kind in kinds:
        for ev in events:
            if ev.get('kind') == kind:
                lines.append('- [%s] %s' % (kind, ev.get('rule', '')))
    return '\n'.join(lines), len(events)


def recall_context(query, k):
    """Return (ctx_block_text, n_cards_used) — top-K weighted cards.

    Uses E.score_card (token-overlap x recency x weight). Highest weight
    first, capped to CTX_BLOCK_CAP chars.
    """
    _, _, _, data = E.read_section('ctx')
    records, _ = E.parse_jsonl(data)
    now = time.time()
    qtok = E.tokenize(query)
    scored = [(E.score_card(c, qtok, now), c) for c in records]
    scored = [(s, c) for s, c in scored if s > 0.0]
    scored.sort(key=lambda sc: sc[0], reverse=True)
    top = scored[:k]
    if not top:
        return '(no relevant cards)', 0
    lines, used, n = [], 0, 0
    for s, c in top:
        line = '(%.3f) %s/%s: %s' % (s, c.get('author', '?'),
                                     c.get('topic', '?'), c.get('text', ''))
        if used + len(line) + 1 > CTX_BLOCK_CAP and n > 0:
            break
        lines.append(line)
        used += len(line) + 1
        n += 1
    return '\n'.join(lines), n


def compose(ai, prompt, k):
    """Build the augmented prompt. Returns (augmented, n_ctx, n_rules)."""
    profile, n_rules = fold_adapter(ai)
    ctx_block, n_ctx = recall_context(prompt, k)
    augmented = (
        '[ADAPTER PROFILE for %s]\n%s\n\n'
        '[SHARED CONTEXT — top %d, weighted]\n%s\n\n'
        '[USER PROMPT]\n%s'
        % (ai.upper(), profile, k, ctx_block, prompt)
    )
    return augmented, n_ctx, n_rules


# =========================================================================
# MODEL BACKENDS
# =========================================================================

def _run(cmd, timeout, stdin_text=None):
    """Run a subprocess, return stdout text. Raise RuntimeError on failure."""
    try:
        proc = subprocess.run(
            cmd, capture_output=True, timeout=timeout,
            input=(stdin_text.encode('utf-8') if stdin_text is not None else None),
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError('backend timed out after %ss' % timeout)
    except OSError as ex:
        raise RuntimeError('backend not runnable: %s' % ex)
    out = (proc.stdout or b'').decode('utf-8', 'replace').strip()
    err = (proc.stderr or b'').decode('utf-8', 'replace').strip()
    if proc.returncode != 0:
        raise RuntimeError('backend rc=%d: %s' % (proc.returncode, err or out or '(no output)'))
    if not out:
        raise RuntimeError('backend returned empty stdout (stderr: %s)' % (err or '(none)'))
    return out


def call_claude(prompt):
    return _run([CLAUDE_EXE, '-p', prompt, '--model', 'haiku'], timeout=180)


def call_grok(prompt):
    return _run([GROK_EXE, '-p', prompt], timeout=180)


def call_web(site, prompt):
    return _run([sys.executable, WEBBRAIN_PY, '--site', site, 'ask', prompt], timeout=240)


def call_gpt_api(prompt):
    """OpenAI /v1/chat/completions via urllib. Never prints the key.

    Model from openai_model.txt if present, else 'gpt-4o', falling back to
    'gpt-4o-mini' on a 404 (unknown model).
    """
    with open(OPENAI_KEY_FILE, 'r', encoding='utf-8') as f:
        key = f.read().strip()
    if not key:
        raise RuntimeError('OpenAI key file is empty')
    models = []
    if os.path.isfile(OPENAI_MODEL_FILE):
        with open(OPENAI_MODEL_FILE, 'r', encoding='utf-8') as f:
            m = f.read().strip()
        if m:
            models.append(m)
    for fallback in ('gpt-4o', 'gpt-4o-mini'):
        if fallback not in models:
            models.append(fallback)

    last_err = None
    for model in models:
        body = json.dumps({
            'model': model,
            'messages': [{'role': 'user', 'content': prompt}],
        }).encode('utf-8')
        req = urllib.request.Request(
            OPENAI_URL, data=body, method='POST',
            headers={'Authorization': 'Bearer %s' % key,
                     'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                doc = json.loads(resp.read().decode('utf-8', 'replace'))
            text = doc['choices'][0]['message']['content'].strip()
            if not text:
                raise RuntimeError('OpenAI returned empty content (model=%s)' % model)
            return text
        except urllib.error.HTTPError as ex:
            detail = ex.read().decode('utf-8', 'replace')[:300] if ex.fp else ''
            last_err = 'HTTP %d for model=%s: %s' % (ex.code, model, detail)
            if ex.code == 404:
                continue  # try next model in the fallback chain
            raise RuntimeError('OpenAI %s' % last_err)
        except (urllib.error.URLError, KeyError, IndexError, ValueError) as ex:
            last_err = '%s (model=%s)' % (ex, model)
            continue
    raise RuntimeError('OpenAI call failed: %s' % last_err)


def dispatch(model, prompt):
    if model == 'claude':
        return call_claude(prompt)
    if model == 'grok':
        return call_grok(prompt)
    if model == 'gpt-api':
        return call_gpt_api(prompt)
    if model in WEB_SITE:
        return call_web(WEB_SITE[model], prompt)
    raise RuntimeError('unknown model backend: %s' % model)


# =========================================================================
# ENHANCE-OUT  (writeback -> shared memory)
# =========================================================================

def writeback(ai, prompt, answer):
    """Deposit a prompt->answer digest card via the Enhancer append protocol."""
    topic = prompt.strip().replace('\n', ' ')[:TOPIC_CAP] or 'exchange'
    ans = answer.strip().replace('\n', ' ')
    text = 'Q: %s | A: %s' % (prompt.strip().replace('\n', ' '), ans)
    if len(text) > DIGEST_CAP:
        text = text[:DIGEST_CAP - 1] + '…'
    card = {
        'id': E.uuid.uuid4().hex[:12],
        'author': ai.upper(),
        'topic': topic,
        'text': text,
        'ts': time.time(),
        'weight': 1.0,
    }
    payload = (json.dumps(card, ensure_ascii=False) + '\n').encode('utf-8')
    E.append_bytes('ctx', payload)
    return card['id']


def learn_fact(ai, rule):
    """Record a REMEMBER: rule as an adapter fact via the Enhancer protocol."""
    event = {'ai': ai.upper(), 'kind': 'fact', 'rule': rule, 'ts': time.time()}
    payload = (json.dumps(event, ensure_ascii=False) + '\n').encode('utf-8')
    E.append_bytes('adapt', payload)


def council_post(ai, prompt, answer):
    """Post a one-line summary to the council chat as <AI>: ..."""
    one = answer.strip().replace('\n', ' ')
    if len(one) > 200:
        one = one[:199] + '…'
    line = '[%s] %s: %s\n' % (time.strftime('%H:%M:%S'), ai.upper(), one)
    E.append_bytes('chat', line.encode('utf-8'))


# =========================================================================
# CLI
# =========================================================================

def build_parser():
    p = argparse.ArgumentParser(
        prog='alma_wrap.py',
        description='ALMA WRAP — augment every AI call with adapter profile + '
                    'shared context, and write the answer back to the pool.')
    p.add_argument('--ai', required=True, help='AI identity (CLOD/GPT/GROK/GEMINI/...)')
    p.add_argument('--model', required=True,
                   choices=['claude', 'grok', 'gpt-api', 'grok-web', 'gpt-web', 'gemini-web'])
    p.add_argument('-k', type=int, default=5, help='top-K context cards (default 5)')
    p.add_argument('--no-writeback', action='store_true',
                   help='do not deposit the exchange back into the shared pool')
    p.add_argument('--dry-run', action='store_true',
                   help='print the augmented prompt and exit (zero model cost)')
    p.add_argument('--council', action='store_true',
                   help='also post a one-line summary to the council chat as <AI>:')
    p.add_argument('prompt')
    return p


def main(argv=None):
    E.force_utf8()
    if os.name != 'nt':
        print('ERROR: alma_wrap depends on alma_enhancer (Windows-only RAM sections).')
        return 3
    args = build_parser().parse_args(argv)
    ai = args.ai.upper()

    # 1. ENHANCE-IN
    try:
        augmented, n_ctx, n_rules = compose(ai, args.prompt, args.k)
    except E.SectionDown as ex:
        print('ERROR: %s' % ex)
        return 2

    # 2. DRY-RUN
    if args.dry_run:
        print(augmented)
        print('\n[wrap ai=%s model=%s k=%d ctx adapter=%d rules writeback=dry-run]'
              % (ai, args.model, n_ctx, n_rules))
        return 0

    # 3. CALL MODEL
    error_note = None
    try:
        answer = dispatch(args.model, augmented)
    except RuntimeError as ex:
        error_note = str(ex)
        answer = '[ERROR calling %s: %s]' % (args.model, error_note)

    # 4. ENHANCE-OUT
    wb = 'no'
    if not args.no_writeback:
        try:
            writeback(ai, args.prompt, answer)
            wb = 'yes'
        except E.EnhancerError as ex:
            wb = 'failed:%s' % ex
    # REMEMBER: path -> learn a fact (independent of writeback flag)
    remembered = ''
    if args.prompt.strip().startswith('REMEMBER:'):
        fact = args.prompt.strip()[len('REMEMBER:'):].strip()
        if fact:
            try:
                learn_fact(ai, fact)
                remembered = ' remembered=fact'
            except E.EnhancerError as ex:
                remembered = ' remember-failed=%s' % ex

    # --council convenience
    if args.council and error_note is None:
        try:
            council_post(ai, args.prompt, answer)
            remembered += ' council=posted'
        except E.EnhancerError as ex:
            remembered += ' council-failed=%s' % ex

    # 5. PRINT answer + trace
    print(answer)
    print('[wrap ai=%s model=%s k=%d ctx adapter=%d rules writeback=%s%s]'
          % (ai, args.model, n_ctx, n_rules, wb, remembered))
    return 0 if error_note is None else 6


if __name__ == '__main__':
    sys.exit(main())
