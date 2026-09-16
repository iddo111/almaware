#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ALMA ENHANCER GUI — the native face of the ALMA Enhancer (tkinter, no browser).

100% ALMAWARE. Pure Python stdlib only (tkinter, mmap via alma_enhancer, ctypes,
subprocess for local process control, json, argparse). No pip, no network, no HTML.

Imports alma_enhancer (same dir) and talks to the shared-RAM sections DIRECTLY
through its section-access functions — no shelling out for reads or writes.

Tabs:
  COUNCIL       live chat log (polls shared RAM every 500 ms) + send bar
  CONTEXT POOL  recall (scored), add card, newest cards
  ADAPTERS      per-AI folded rule profile + learn form

Status bar: per-section alive dots + used bytes + holder pid, refreshed every 2 s.
If the sections are dead (no holder): big START ENGINE button spawns the holder
hidden (CREATE_NO_WINDOW) and re-checks.

--selftest: builds all widgets WITHOUT mainloop, drives the real handlers
programmatically, asserts results, prints SELFTEST PASS/FAIL.
"""

import argparse
import ctypes
import json
import os
import re
import struct
import subprocess
import sys
import threading
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import alma_enhancer as core  # noqa: E402  (same-dir module, by design)

import tkinter as tk          # noqa: E402
from tkinter import ttk       # noqa: E402

# ---------------------------------------------------------------- constants

CORE_DIR = os.path.dirname(os.path.abspath(__file__))
CORE_PATH = os.path.join(CORE_DIR, 'alma_enhancer.py')
PIDFILE = os.path.join(CORE_DIR, 'holder.pid')

CREATE_NO_WINDOW = 0x08000000
STILL_ACTIVE = 259

PARTIES = ['USER', 'CLOD', 'GEMINI', 'GPT', 'GROK']
ADAPT_KINDS = ['style', 'correction', 'skill', 'fact']

# ------- bright ALMA palette (Iddo's law: bright, alive) -------
BG = '#FAF7F0'          # warm white
PANEL = '#FFFFFF'
INK = '#2A2118'         # warm near-black
MUTED = '#9A8F7F'
ACCENT = '#E86A33'      # ALMA coral
ACCENT_DARK = '#C64F1E'
TEAL = '#0E7C7B'
GOLD = '#F2B705'
OK_GREEN = '#2E9E44'
BAD_RED = '#D63B2F'
STRIPE = '#FDF6EA'
BANNER_BG = '#FFF3E0'

PARTY_COLORS = {
    'USER': '#1B6CA8',
    'CLOD': '#E86A33',
    'GEMINI': '#7B2D8B',
    'GPT': '#10A37F',
    'GROK': '#5D4037',
}

FONT = ('Segoe UI', 11)
FONT_BOLD = ('Segoe UI', 11, 'bold')
FONT_BIG = ('Segoe UI', 16, 'bold')
FONT_SMALL = ('Segoe UI', 9)
FONT_CHAT = ('Segoe UI', 11)


# ---------------------------------------------------------------- helpers

def human_bytes(n):
    if n < 1024:
        return '%dB' % n
    if n < 1024 * 1024:
        return '%.1fKiB' % (n / 1024.0)
    return '%.2fMiB' % (n / (1024.0 * 1024.0))


def peek_section(key):
    """Lock-free liveness peek: (alive, head). Writers set data before HEAD,
    so reading up to HEAD without the mutex is always consistent."""
    spec = core.SECTIONS[key]
    try:
        m = core.open_section(key)
    except (ValueError, OSError):
        return False, core.DATA_OFF
    try:
        if not core.is_initialized(m):
            return False, core.DATA_OFF
        head = struct.unpack('<Q', m[core.HEAD_OFF:core.HEAD_OFF + 8])[0]
        if head < core.DATA_OFF or head > spec['size']:
            return False, core.DATA_OFF
        return True, head
    finally:
        m.close()


def all_sections_alive():
    return all(peek_section(k)[0] for k in ('ctx', 'adapt', 'chat'))


def pid_alive(pid):
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    k = ctypes.windll.kernel32
    h = k.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    try:
        code = ctypes.c_ulong()
        if not k.GetExitCodeProcess(h, ctypes.byref(code)):
            return False
        return code.value == STILL_ACTIVE
    finally:
        k.CloseHandle(h)


def read_pidfile():
    try:
        with open(PIDFILE, 'r', encoding='ascii') as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


def find_holder_pid_slow():
    """Best-effort holder discovery via a hidden local CIM query (no network)."""
    ps = ("Get-CimInstance Win32_Process -Filter \"Name LIKE 'python%'\" | "
          "Where-Object { $_.CommandLine -match 'alma_enhancer' -and "
          "$_.CommandLine -match 'hold' } | "
          "Select-Object -First 1 -ExpandProperty ProcessId")
    try:
        out = subprocess.check_output(
            ['powershell', '-NoProfile', '-NonInteractive', '-Command', ps],
            creationflags=CREATE_NO_WINDOW, stdin=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=20)
        return int(out.decode('ascii', 'replace').strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def start_holder():
    """Spawn the life-support holder hidden. Survives GUI exit (no job object)."""
    proc = subprocess.Popen(
        [sys.executable, CORE_PATH, 'hold'],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW, cwd=CORE_DIR)
    try:
        with open(PIDFILE, 'w', encoding='ascii') as f:
            f.write(str(proc.pid))
    except OSError:
        pass
    return proc


def fold_profile(records, ai):
    """Replicates core profile fold: last-wins per normalized rule key."""
    ai = str(ai).upper()
    folded, total = {}, 0
    for ev in records:
        if str(ev.get('ai', '')).upper() != ai:
            continue
        total += 1
        folded[core.rule_key(ev.get('rule', ''))] = ev
    events = sorted(folded.values(), key=lambda e: float(e.get('ts', 0)))
    return events, total


# ---------------------------------------------------------------- the GUI

class EnhancerGUI:

    def __init__(self, root):
        self.root = root
        self._destroyed = False
        self._chat_head = core.DATA_OFF
        self._status_tick = 0
        self.holder_pid = None
        self._pid_query_running = False

        root.title('ALMA ENHANCER')
        root.geometry('1000x680')
        root.minsize(880, 560)
        root.configure(bg=BG)
        root.bind('<Destroy>', self._on_destroy)

        self._build_styles()
        self._build_header()
        self._build_banner()
        self._build_notebook()
        self._build_statusbar()

        self.refresh_status()
        self.poll_chat()
        self.refresh_newest()
        self._find_holder_async()

    # ---------------------------------------------------------- style / shell

    def _build_styles(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use('clam')
        except tk.TclError:
            pass
        style.configure('.', background=BG, foreground=INK, font=FONT)
        style.configure('TNotebook', background=BG, borderwidth=0, tabmargins=(8, 6, 8, 0))
        style.configure('TNotebook.Tab', font=('Segoe UI', 12, 'bold'),
                        padding=(20, 9), background='#F0E7D8', foreground='#6B5A45')
        style.map('TNotebook.Tab',
                  background=[('selected', ACCENT)],
                  foreground=[('selected', '#FFFFFF')])
        style.configure('TFrame', background=BG)
        style.configure('Panel.TFrame', background=PANEL)
        style.configure('Treeview', font=('Segoe UI', 10), rowheight=26,
                        background=PANEL, fieldbackground=PANEL, foreground=INK)
        style.configure('Treeview.Heading', font=('Segoe UI', 10, 'bold'),
                        background=TEAL, foreground='#FFFFFF', relief='flat')
        style.map('Treeview.Heading', background=[('active', '#0A6362')])
        style.configure('TCombobox', fieldbackground=PANEL, background=PANEL)

    def _mk_button(self, parent, text, command, big=False, color=ACCENT, active=ACCENT_DARK):
        return tk.Button(parent, text=text, command=command,
                         font=('Segoe UI', 14 if big else 11, 'bold'),
                         bg=color, fg='#FFFFFF', activebackground=active,
                         activeforeground='#FFFFFF', relief='flat',
                         cursor='hand2', padx=18 if big else 12, pady=8 if big else 3)

    def _mk_entry(self, parent, textvariable=None, width=None):
        e = tk.Entry(parent, textvariable=textvariable, font=FONT, bg=PANEL, fg=INK,
                     relief='solid', bd=1, insertbackground=INK,
                     highlightthickness=1, highlightcolor=ACCENT,
                     highlightbackground='#E3D9C6')
        if width:
            e.configure(width=width)
        return e

    def _build_header(self):
        hdr = tk.Frame(self.root, bg=BG)
        hdr.pack(fill='x', padx=16, pady=(12, 4))
        tk.Label(hdr, text='ALMA ENHANCER', font=('Segoe UI', 20, 'bold'),
                 bg=BG, fg=TEAL).pack(side='left')
        tk.Label(hdr, text='  shared-RAM organ · context pool · adapters · council',
                 font=('Segoe UI', 11), bg=BG, fg=MUTED).pack(side='left', pady=(8, 0))
        tk.Label(hdr, text='100% ALMAWARE', font=('Segoe UI', 10, 'bold'),
                 bg=GOLD, fg=INK, padx=10, pady=3).pack(side='right')

    def _build_banner(self):
        self.banner = tk.Frame(self.root, bg=BANNER_BG, bd=1, relief='solid',
                               highlightbackground=ACCENT)
        inner = tk.Frame(self.banner, bg=BANNER_BG)
        inner.pack(pady=14)
        tk.Label(inner, text='ENGINE OFFLINE — shared-RAM sections are down (RAM-only, need the holder).',
                 font=('Segoe UI', 12, 'bold'), bg=BANNER_BG, fg=BAD_RED).pack()
        self.engine_btn = self._mk_button(inner, 'START ENGINE', self.start_engine, big=True)
        self.engine_btn.pack(pady=(10, 2))
        self._banner_visible = False  # packed on demand by refresh_status

    def _show_banner(self, show):
        if show and not self._banner_visible:
            self.banner.pack(fill='x', padx=16, pady=6, before=self.notebook)
            self._banner_visible = True
        elif not show and self._banner_visible:
            self.banner.pack_forget()
            self._banner_visible = False

    def _build_notebook(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True, padx=16, pady=(6, 4))
        self._build_tab_council()
        self._build_tab_context()
        self._build_tab_adapters()

    # ---------------------------------------------------------- tab: COUNCIL

    def _build_tab_council(self):
        tab = tk.Frame(self.notebook, bg=BG)
        self.notebook.add(tab, text='  COUNCIL  ')

        wrap = tk.Frame(tab, bg=BG)
        wrap.pack(fill='both', expand=True, padx=10, pady=(10, 4))
        self.chat_text = tk.Text(wrap, font=FONT_CHAT, bg=PANEL, fg=INK,
                                 relief='solid', bd=1, wrap='word', state='disabled',
                                 padx=10, pady=8, insertbackground=INK)
        sb = ttk.Scrollbar(wrap, command=self.chat_text.yview)
        self.chat_text.configure(yscrollcommand=sb.set)
        sb.pack(side='right', fill='y')
        self.chat_text.pack(side='left', fill='both', expand=True)

        self.chat_text.tag_configure('ts', foreground=MUTED, font=('Segoe UI', 9))
        for party, color in PARTY_COLORS.items():
            self.chat_text.tag_configure('party_%s' % party, foreground=color,
                                         font=('Segoe UI', 11, 'bold'))
        self.chat_text.tag_configure('party_other', foreground='#555555',
                                     font=('Segoe UI', 11, 'bold'))
        self.chat_text.tag_configure('msg', foreground=INK)

        bar = tk.Frame(tab, bg=BG)
        bar.pack(fill='x', padx=10, pady=(4, 10))
        self.party_var = tk.StringVar(value='USER')
        cb = ttk.Combobox(bar, textvariable=self.party_var, values=PARTIES,
                          state='readonly', width=9, font=FONT)
        cb.pack(side='left')
        self.chat_entry = self._mk_entry(bar)
        self.chat_entry.pack(side='left', fill='x', expand=True, padx=8, ipady=5)
        self.chat_entry.bind('<Return>', lambda e: (self.send_chat(), 'break')[1])
        self._mk_button(bar, 'Send  ➤', self.send_chat).pack(side='left')

    def _clear_chat_widget(self):
        self.chat_text.configure(state='normal')
        self.chat_text.delete('1.0', 'end')
        self.chat_text.configure(state='disabled')

    def _append_chat_line(self, line):
        self.chat_text.configure(state='normal')
        m = re.match(r'^\[(\d{2}:\d{2}:\d{2})\]\s+([^:\s]+):\s?(.*)$', line)
        if m:
            ts, party, msg = m.groups()
            tag = 'party_%s' % party if party in PARTY_COLORS else 'party_other'
            self.chat_text.insert('end', '[%s] ' % ts, ('ts',))
            self.chat_text.insert('end', '%s: ' % party, (tag,))
            self.chat_text.insert('end', msg + '\n', ('msg',))
        else:
            self.chat_text.insert('end', line + '\n', ('msg',))
        self.chat_text.configure(state='disabled')
        self.chat_text.see('end')

    def _poll_chat_step(self):
        """One poll: pull any new bytes from the chat section into the widget."""
        alive, head = peek_section('chat')
        if not alive:
            return False
        if head < self._chat_head:            # section was reset/restored
            self._chat_head = core.DATA_OFF
            self._clear_chat_widget()
        if head > self._chat_head:
            spec = core.SECTIONS['chat']
            m = core.open_section('chat')
            try:
                data = bytes(m[self._chat_head:min(head, spec['size'])])
            finally:
                m.close()
            self._chat_head = head
            for ln in data.decode('utf-8', 'replace').splitlines():
                if ln.strip():
                    self._append_chat_line(ln)
        return True

    def poll_chat(self):
        if self._destroyed:
            return
        try:
            self._poll_chat_step()
        except Exception as e:
            self._flash('chat poll error: %s' % e, bad=True)
        self.root.after(500, self.poll_chat)

    def send_chat(self):
        msg = self.chat_entry.get().strip().replace('\n', ' ')
        if not msg:
            return
        party = (self.party_var.get() or 'USER').strip().upper()
        line = '[%s] %s: %s\n' % (time.strftime('%H:%M:%S'), party, msg)
        try:
            core.append_bytes('chat', line.encode('utf-8'))
        except core.SectionDown:
            self._flash('COUNCIL section is DOWN — press START ENGINE', bad=True)
            self._show_banner(True)
            return
        except core.EnhancerError as e:
            self._flash('send failed: %s' % e, bad=True)
            return
        self.chat_entry.delete(0, 'end')
        self._poll_chat_step()

    # ------------------------------------------------------ tab: CONTEXT POOL

    def _build_tab_context(self):
        tab = tk.Frame(self.notebook, bg=BG)
        self.notebook.add(tab, text='  CONTEXT POOL  ')

        # recall row
        top = tk.Frame(tab, bg=BG)
        top.pack(fill='x', padx=10, pady=(12, 4))
        tk.Label(top, text='Recall', font=FONT_BOLD, bg=BG, fg=TEAL).pack(side='left')
        self.search_var = tk.StringVar()
        se = self._mk_entry(top, textvariable=self.search_var)
        se.pack(side='left', fill='x', expand=True, padx=8, ipady=4)
        se.bind('<Return>', lambda e: (self.do_recall(), 'break')[1])
        self._mk_button(top, 'Recall 🔎', self.do_recall, color=TEAL,
                        active='#0A6362').pack(side='left')

        cols = ('score', 'author', 'topic', 'when', 'text')
        self.results_tree = ttk.Treeview(tab, columns=cols, show='headings', height=7)
        for c, w, anchor in (('score', 70, 'center'), ('author', 90, 'center'),
                             ('topic', 150, 'w'), ('when', 150, 'center'), ('text', 440, 'w')):
            self.results_tree.heading(c, text=c.upper())
            self.results_tree.column(c, width=w, anchor=anchor, stretch=(c == 'text'))
        self.results_tree.tag_configure('odd', background=STRIPE)
        self.results_tree.pack(fill='x', padx=10, pady=4)

        # add-card form
        form = tk.Frame(tab, bg=BG)
        form.pack(fill='x', padx=10, pady=(10, 4))
        tk.Label(form, text='Add Card', font=FONT_BOLD, bg=BG, fg=ACCENT).pack(side='left')
        self.ctx_author_var = tk.StringVar(value='USER')
        ttk.Combobox(form, textvariable=self.ctx_author_var, values=PARTIES,
                     state='readonly', width=9, font=FONT).pack(side='left', padx=(8, 4))
        tk.Label(form, text='topic', font=FONT_SMALL, bg=BG, fg=MUTED).pack(side='left')
        self.ctx_topic_var = tk.StringVar()
        self._mk_entry(form, textvariable=self.ctx_topic_var, width=18).pack(side='left', padx=4, ipady=4)
        tk.Label(form, text='text', font=FONT_SMALL, bg=BG, fg=MUTED).pack(side='left')
        te = self._mk_entry(form, textvariable=None)
        self.ctx_text_entry = te
        te.pack(side='left', fill='x', expand=True, padx=4, ipady=4)
        te.bind('<Return>', lambda e: (self.add_card(), 'break')[1])
        self._mk_button(form, 'Add ➕', self.add_card).pack(side='left', padx=(4, 0))

        # newest cards
        nf = tk.Frame(tab, bg=BG)
        nf.pack(fill='x', padx=10, pady=(8, 0))
        tk.Label(nf, text='Newest cards', font=FONT_BOLD, bg=BG, fg=TEAL).pack(side='left')
        self._mk_button(nf, 'Refresh ⟳', self.refresh_newest, color='#8A7B63',
                        active='#6B5A45').pack(side='right')
        ncols = ('weight', 'author', 'topic', 'when', 'text')
        self.newest_tree = ttk.Treeview(tab, columns=ncols, show='headings', height=6)
        for c, w, anchor in (('weight', 70, 'center'), ('author', 90, 'center'),
                             ('topic', 150, 'w'), ('when', 150, 'center'), ('text', 440, 'w')):
            self.newest_tree.heading(c, text=c.upper())
            self.newest_tree.column(c, width=w, anchor=anchor, stretch=(c == 'text'))
        self.newest_tree.tag_configure('odd', background=STRIPE)
        self.newest_tree.pack(fill='both', expand=True, padx=10, pady=(4, 10))

    @staticmethod
    def _fill_tree(tree, rows):
        tree.delete(*tree.get_children())
        for i, row in enumerate(rows):
            tree.insert('', 'end', values=row, tags=('odd',) if i % 2 else ())

    def do_recall(self):
        query = self.search_var.get().strip()
        if not query:
            self._flash('type a recall query first')
            return
        try:
            _, _, _, data = core.read_section('ctx')
        except core.SectionDown:
            self._flash('CTX section is DOWN — press START ENGINE', bad=True)
            self._show_banner(True)
            return
        records, _ = core.parse_jsonl(data)
        now = time.time()
        qtok = core.tokenize(query)
        scored = [(core.score_card(c, qtok, now), c) for c in records]
        scored = [(s, c) for s, c in scored if s > 0.0]
        scored.sort(key=lambda sc: sc[0], reverse=True)
        rows = [('%.3f' % s, c.get('author', '?'), c.get('topic', '?'),
                 core.iso_of(c.get('ts', 0)), c.get('text', ''))
                for s, c in scored[:12]]
        self._fill_tree(self.results_tree, rows)
        self._flash('%d matching card(s) for "%s"' % (len(rows), query),
                    bad=(not rows))

    def add_card(self):
        text = self.ctx_text_entry.get().strip()
        if not text:
            self._flash('card text is empty')
            return
        card = {
            'id': uuid.uuid4().hex[:12],
            'author': (self.ctx_author_var.get() or 'USER').upper(),
            'topic': self.ctx_topic_var.get().strip() or 'general',
            'text': text,
            'ts': time.time(),
            'weight': 1.0,
        }
        payload = (json.dumps(card, ensure_ascii=False) + '\n').encode('utf-8')
        try:
            core.append_bytes('ctx', payload)
        except core.SectionDown:
            self._flash('CTX section is DOWN — press START ENGINE', bad=True)
            self._show_banner(True)
            return
        except core.EnhancerError as e:
            self._flash('add card failed: %s' % e, bad=True)
            return
        self.ctx_text_entry.delete(0, 'end')
        self.ctx_topic_var.set('')
        self._flash('card %s deposited (author=%s)' % (card['id'], card['author']))
        self.refresh_newest()

    def refresh_newest(self):
        try:
            _, _, _, data = core.read_section('ctx')
        except core.SectionDown:
            return
        except core.EnhancerError:
            return
        records, _ = core.parse_jsonl(data)
        rows = [('%.2f' % float(c.get('weight', 1.0)), c.get('author', '?'),
                 c.get('topic', '?'), core.iso_of(c.get('ts', 0)), c.get('text', ''))
                for c in records[-12:][::-1]]
        self._fill_tree(self.newest_tree, rows)

    # -------------------------------------------------------- tab: ADAPTERS

    def _build_tab_adapters(self):
        tab = tk.Frame(self.notebook, bg=BG)
        self.notebook.add(tab, text='  ADAPTERS  ')

        top = tk.Frame(tab, bg=BG)
        top.pack(fill='x', padx=10, pady=(12, 4))
        tk.Label(top, text='AI profile', font=FONT_BOLD, bg=BG, fg=TEAL).pack(side='left')
        self.adapt_ai_var = tk.StringVar(value='CLOD')
        cb = ttk.Combobox(top, textvariable=self.adapt_ai_var, values=PARTIES,
                          state='readonly', width=9, font=FONT)
        cb.pack(side='left', padx=8)
        cb.bind('<<ComboboxSelected>>', lambda e: self.load_profile())
        self._mk_button(top, 'Load Profile', self.load_profile, color=TEAL,
                        active='#0A6362').pack(side='left')
        tk.Label(top, text='prompt-side adaptation (LoRA-like role — no model weights touched)',
                 font=FONT_SMALL, bg=BG, fg=MUTED).pack(side='left', padx=10)

        wrap = tk.Frame(tab, bg=BG)
        wrap.pack(fill='both', expand=True, padx=10, pady=4)
        self.profile_text = tk.Text(wrap, font=('Consolas', 11), bg=PANEL, fg=INK,
                                    relief='solid', bd=1, wrap='word', state='disabled',
                                    padx=10, pady=8)
        psb = ttk.Scrollbar(wrap, command=self.profile_text.yview)
        self.profile_text.configure(yscrollcommand=psb.set)
        psb.pack(side='right', fill='y')
        self.profile_text.pack(side='left', fill='both', expand=True)
        self.profile_text.tag_configure('hdr', foreground=TEAL, font=('Consolas', 11, 'bold'))
        self.profile_text.tag_configure('kind', foreground=ACCENT, font=('Consolas', 11, 'bold'))

        form = tk.Frame(tab, bg=BG)
        form.pack(fill='x', padx=10, pady=(6, 12))
        tk.Label(form, text='Learn rule', font=FONT_BOLD, bg=BG, fg=ACCENT).pack(side='left')
        self.adapt_kind_var = tk.StringVar(value='style')
        ttk.Combobox(form, textvariable=self.adapt_kind_var, values=ADAPT_KINDS,
                     state='readonly', width=11, font=FONT).pack(side='left', padx=8)
        self.adapt_rule_entry = self._mk_entry(form)
        self.adapt_rule_entry.pack(side='left', fill='x', expand=True, padx=4, ipady=4)
        self.adapt_rule_entry.bind('<Return>', lambda e: (self.learn_rule(), 'break')[1])
        self._mk_button(form, 'Learn 🧠', self.learn_rule).pack(side='left', padx=(4, 0))

    def load_profile(self):
        ai = (self.adapt_ai_var.get() or 'CLOD').upper()
        try:
            _, _, _, data = core.read_section('adapt')
        except core.SectionDown:
            self._flash('ADAPT section is DOWN — press START ENGINE', bad=True)
            self._show_banner(True)
            return
        records, _ = core.parse_jsonl(data)
        events, total = fold_profile(records, ai)
        self.profile_text.configure(state='normal')
        self.profile_text.delete('1.0', 'end')
        self.profile_text.insert('end', '### ALMA ADAPT PROFILE :: %s :: %d rules (folded from %d events)\n'
                                 % (ai, len(events), total), ('hdr',))
        self.profile_text.insert('end', '### inject this block at session start — honest mechanism: '
                                 'prompt rules, no weight updates\n\n', ('hdr',))
        if not events:
            self.profile_text.insert('end', '(no rules learned yet for %s)\n' % ai)
        else:
            for kind in ADAPT_KINDS + sorted(set(e.get('kind', '?') for e in events) - set(ADAPT_KINDS)):
                for ev in events:
                    if ev.get('kind') == kind:
                        self.profile_text.insert('end', '- [%s] ' % kind, ('kind',))
                        self.profile_text.insert('end', '%s  (%s)\n'
                                                 % (ev.get('rule', ''), core.iso_of(ev.get('ts', 0))))
        self.profile_text.configure(state='disabled')

    def learn_rule(self):
        rule = self.adapt_rule_entry.get().strip()
        if not rule:
            self._flash('rule text is empty')
            return
        event = {'ai': (self.adapt_ai_var.get() or 'CLOD').upper(),
                 'kind': self.adapt_kind_var.get() or 'style',
                 'rule': rule, 'ts': time.time()}
        payload = (json.dumps(event, ensure_ascii=False) + '\n').encode('utf-8')
        try:
            core.append_bytes('adapt', payload)
        except core.SectionDown:
            self._flash('ADAPT section is DOWN — press START ENGINE', bad=True)
            self._show_banner(True)
            return
        except core.EnhancerError as e:
            self._flash('learn failed: %s' % e, bad=True)
            return
        self.adapt_rule_entry.delete(0, 'end')
        self._flash('rule learned for %s [%s]' % (event['ai'], event['kind']))
        self.load_profile()

    # ---------------------------------------------------------- status bar

    def _build_statusbar(self):
        bar = tk.Frame(self.root, bg='#F1EADC')
        bar.pack(fill='x', side='bottom')
        self._section_widgets = []
        for key, label in (('ctx', 'CTX'), ('adapt', 'ADAPT'), ('chat', 'COUNCIL')):
            dot = tk.Label(bar, text='●', font=('Segoe UI', 12, 'bold'),
                           bg='#F1EADC', fg=MUTED)
            dot.pack(side='left', padx=(12, 1), pady=3)
            txt = tk.Label(bar, text='%s —' % label, font=FONT_SMALL,
                           bg='#F1EADC', fg=INK)
            txt.pack(side='left')
            self._section_widgets.append((key, label, dot, txt))
        self.pid_label = tk.Label(bar, text='holder: ?', font=FONT_SMALL,
                                  bg='#F1EADC', fg=MUTED)
        self.pid_label.pack(side='right', padx=12)
        self.flash_label = tk.Label(bar, text='', font=FONT_SMALL,
                                    bg='#F1EADC', fg=TEAL, anchor='e')
        self.flash_label.pack(side='right', padx=12)

    def _flash(self, msg, bad=False):
        self.flash_label.configure(text=msg, fg=(BAD_RED if bad else TEAL))

    def _find_holder_async(self):
        if self._pid_query_running:
            return
        pid = read_pidfile()
        if pid and pid_alive(pid):
            self.holder_pid = pid
            return
        self._pid_query_running = True

        def work():
            try:
                pid2 = find_holder_pid_slow()
                if pid2 and pid_alive(pid2):
                    self.holder_pid = pid2
                    try:
                        with open(PIDFILE, 'w', encoding='ascii') as f:
                            f.write(str(pid2))
                    except OSError:
                        pass
            finally:
                self._pid_query_running = False
        threading.Thread(target=work, daemon=True).start()

    def refresh_status(self):
        if self._destroyed:
            return
        self._status_tick += 1
        any_down = False
        for key, label, dot, txt in self._section_widgets:
            try:
                alive, head = peek_section(key)
            except Exception:
                alive, head = False, core.DATA_OFF
            if alive:
                dot.configure(fg=OK_GREEN)
                txt.configure(text='%s %s' % (label, human_bytes(head - core.DATA_OFF)))
            else:
                dot.configure(fg=BAD_RED)
                txt.configure(text='%s DOWN' % label)
                any_down = True
        self._show_banner(any_down)
        if self.holder_pid and pid_alive(self.holder_pid):
            self.pid_label.configure(text='holder pid %d' % self.holder_pid, fg=OK_GREEN)
        else:
            self.holder_pid = None
            self.pid_label.configure(text='holder: not found', fg=MUTED)
            # re-discover occasionally while sections are alive (external holder)
            if not any_down and self._status_tick % 15 == 1:
                self._find_holder_async()
        self.root.after(2000, self.refresh_status)

    def start_engine(self):
        self.engine_btn.configure(state='disabled', text='STARTING…')
        try:
            proc = start_holder()
            self.holder_pid = proc.pid
        except OSError as e:
            self._flash('holder spawn failed: %s' % e, bad=True)
            self.engine_btn.configure(state='normal', text='START ENGINE')
            return
        self._flash('engine starting (holder pid %d)…' % self.holder_pid)
        self.root.after(900, self._after_engine_start)

    def _after_engine_start(self):
        if all_sections_alive():
            self._flash('engine ALIVE — holder pid %s' % self.holder_pid)
            self._show_banner(False)
            self.refresh_newest()
        else:
            self._flash('engine not up yet — re-checking…', bad=True)
            self.root.after(900, self._after_engine_start)
        self.engine_btn.configure(state='normal', text='START ENGINE')

    def _on_destroy(self, event):
        if event.widget is self.root:
            self._destroyed = True


# ---------------------------------------------------------------- selftest

def run_selftest():
    print('[selftest] ALMA ENHANCER GUI — programmatic widget test (no mainloop)')

    # 1) engine: confirm holder / start one hidden if sections are down
    spawned = None
    if all_sections_alive():
        print('[selftest] sections already ALIVE (external holder)')
    else:
        print('[selftest] sections DOWN — spawning holder hidden…')
        spawned = start_holder()
        deadline = time.time() + 8
        while time.time() < deadline and not all_sections_alive():
            time.sleep(0.25)
        if not all_sections_alive():
            print('SELFTEST FAIL: holder did not bring sections up within 8s '
                  '(spawned pid=%s)' % (spawned.pid if spawned else '?'))
            return 1
        print('[selftest] holder pid %d brought sections ALIVE' % spawned.pid)

    root = None
    try:
        root = tk.Tk()
        root.withdraw()  # build everything, show nothing
        app = EnhancerGUI(root)
        root.update()
        print('[selftest] widgets built: 3 tabs + status bar, no mainloop')

        marker = 'selftest-%s' % uuid.uuid4().hex[:8]

        # 2) council: send via the real handler, poll once, assert in widget
        msg = 'GUI %s שלום מהסלפטסט' % marker          # Hebrew round-trip too
        app.party_var.set('CLOD')
        app.chat_entry.delete(0, 'end')
        app.chat_entry.insert(0, msg)
        app.send_chat()
        app._poll_chat_step()
        chat_content = app.chat_text.get('1.0', 'end')
        if marker not in chat_content:
            print('SELFTEST FAIL: marker %s not found in chat widget' % marker)
            return 1
        if 'שלום' not in chat_content:
            print('SELFTEST FAIL: Hebrew text lost in chat widget round-trip')
            return 1
        print('[selftest] COUNCIL: sent + polled + found marker %s (Hebrew intact)' % marker)

        # 3) context pool: add via form handler, recall via handler, assert row
        app.ctx_author_var.set('CLOD')
        app.ctx_topic_var.set('selftest')
        app.ctx_text_entry.delete(0, 'end')
        app.ctx_text_entry.insert(0, 'alma enhancer gui selftest card %s' % marker)
        app.add_card()
        app.search_var.set(marker)
        app.do_recall()
        rows = app.results_tree.get_children()
        found = any(marker in str(app.results_tree.item(r)['values']) for r in rows)
        if not found:
            print('SELFTEST FAIL: recalled rows (%d) do not contain marker %s'
                  % (len(rows), marker))
            return 1
        top = app.results_tree.item(rows[0])['values']
        print('[selftest] CONTEXT: card added + recalled, top score=%s author=%s'
              % (top[0], top[1]))

        # 4) adapters: learn a rule, profile shows it (bonus coverage)
        app.adapt_ai_var.set('CLOD')
        app.adapt_kind_var.set('fact')
        app.adapt_rule_entry.delete(0, 'end')
        app.adapt_rule_entry.insert(0, 'selftest rule %s' % marker)
        app.learn_rule()
        prof = app.profile_text.get('1.0', 'end')
        if marker not in prof:
            print('SELFTEST FAIL: learned rule %s missing from profile view' % marker)
            return 1
        print('[selftest] ADAPTERS: rule learned + visible in folded profile')

        # 5) status bar refresh ran at least once (dots green)
        greens = sum(1 for _, _, dot, _ in app._section_widgets
                     if dot.cget('fg') == OK_GREEN)
        if greens != 3:
            print('SELFTEST FAIL: expected 3 green section dots, got %d' % greens)
            return 1
        print('[selftest] STATUS BAR: 3/3 sections green')

        print('SELFTEST PASS')
        return 0
    except Exception as e:
        import traceback
        traceback.print_exc()
        print('SELFTEST FAIL: %s' % e)
        return 1
    finally:
        if root is not None:
            try:
                root.destroy()
            except tk.TclError:
                pass


# ---------------------------------------------------------------- main

def main(argv=None):
    core.force_utf8()  # Hebrew-safe stdout on Windows consoles
    if os.name != 'nt':
        print('ERROR: alma_enhancer_gui v1 is Windows-only (named shared-memory sections).')
        return 3
    ap = argparse.ArgumentParser(
        prog='alma_enhancer_gui.py',
        description='ALMA ENHANCER GUI — native tkinter face for the shared-RAM enhancer.')
    ap.add_argument('--selftest', action='store_true',
                    help='build all widgets without mainloop, drive handlers, assert, exit')
    args = ap.parse_args(argv)
    if args.selftest:
        return run_selftest()
    root = tk.Tk()
    EnhancerGUI(root)
    root.mainloop()
    return 0


if __name__ == '__main__':
    sys.exit(main())
