#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ALMAWARE CODER — a real desktop application for Qwen3-Coder-480B.

Iddo, 2026-09-09: "אני רוצה אפליקציית דסקטופ מלאה... עם שמירה, עם הכול, עם זיכרון
מלא, עם פרויקטים, עם workspaces, עם שיחות" — and the bar he named out loud was the
Claude Desktop app. Also: "why do you call it 'taste'? I want a WORK page, not a
demo." So this is not the tasting page with a window bolted on; it is the work tool.

WHAT IT IS
    PyQt6 (house convention — the precedent Iddo signed off on is
    D:\\CLAUDE\\emdr\\source-emdr-central\\emdr_widget.py v0.4).

    * a sidebar of named, switchable, persistent conversations (new / rename /
      pin / move / duplicate / delete-to-trash / search)
    * WORKSPACES ("projects"): each one carries standing instructions the model
      sees on every turn, plus a root directory that widens the per-turn grep
    * live token streaming from the door (SSE), with Stop, and an automatic
      fall back to the blocking call if streaming breaks
    * markdown rendering, code blocks with a language label and a Copy button,
      generic syntax highlighting, RTL Hebrew handled per message
    * the same RAG-grounding transparency the web page had: a collapsible
      "context used (N)" panel under every reply, listing what ALMA-RECALL, the
      ALMAWARE STANDARD and the project grep actually returned
    * full persistence — conversations, workspaces, settings, window geometry,
      which thread was open — all survive a restart

WHAT IT REUSES RATHER THAN REBUILDS
    coder_engine.py imports taste.py and calls its retrieval, its prompt
    assembly and its standing CONTEXT.md. The grounding logic built on
    2026-09-08/09 is not forked; the web page on :8875 and this app share it,
    and they even share conversations/default.jsonl, so the thread Iddo already
    started on the web page opens here with its history intact.

RUN
    pythonw coder_desktop.py            (Python 3.13 — the one with PyQt6)
    python  coder_desktop.py --selftest (headless-ish proof: real turn + PNG)
    python  coder_desktop.py --profile=swarmqa --shot=out.png   (boot, grab a PNG, quit)

2026-09-15 HARNESS SWARM (Iddo 02:47: "all the models - built-in QUORUM and chat online")
    * brains come from coder_brains.py, the ONE table; every assistant message is
      tagged with the model that wrote it (parity with taste.py's append_history)
    * 💬 ROOM: a dock inside this window over RAMCHAT (coder_room.py) -- a live feed,
      a composer, one chip per brain + Claude 💰 (paid, ticked per line) + Muse
    * ⚖️ QUORUM: a picker (topic, seats QUORUM reports up, rounds 1-3); every turn
      streams into the open conversation as its own message, the מסקנה last
"""
from __future__ import annotations

import html as _html
import json
import urllib.request
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

if sys.stdout is None or sys.stderr is None:                     # pythonw has no console
    _logf = open(os.path.join(APP_DIR, "coder_desktop.log"), "a",
                 encoding="utf-8", errors="replace", buffering=1)
    sys.stdout = _logf
    sys.stderr = _logf
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from string import Template

from PyQt6.QtCore import (QEvent, QPoint, QRect, QSettings, QSize, Qt, QThread,
                          QTimer, pyqtSignal)
from PyQt6.QtGui import (QAction, QColor, QFont, QFontMetrics, QGuiApplication,
                         QIcon, QKeySequence, QPainter, QPainterPath, QPixmap,
                         QShortcut, QSyntaxHighlighter, QTextCharFormat,
                         QTextDocument, QTextOption)
from PyQt6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox,
                             QComboBox, QDialog, QDialogButtonBox, QDockWidget,
                             QDoubleSpinBox,
                             QFileDialog, QFrame, QGridLayout, QHBoxLayout,
                             QInputDialog, QLabel, QLineEdit, QListWidget,
                             QListWidgetItem, QMainWindow, QMenu, QMessageBox,
                             QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy,
                             QSpinBox, QSplitter, QStyle, QStyledItemDelegate,
                             QTabWidget, QTextBrowser, QTextEdit, QToolButton,
                             QVBoxLayout, QWidget)

import coder_engine as engine
import coder_store as store
import coder_brains          # 2026-09-15 harnessswarm: the ONE brain table
import coder_quorum          # QUORUM :8099 client, no Qt
import coder_room            # RAMCHAT room + addressed replies, no Qt

APP_NAME = "ALMAWARE Coder"
APP_TAGLINE = "Qwen3-Coder-Next · eran4"   # fallback only; the live label is model_label()

# The window names the brain it really talks to (settings["model"]), not a hard-coded one.
# 2026-09-15 harnessswarm: the MODEL_LABELS table that lived here was a second copy of
# the brain list and had already drifted once (appqa 01:18: nemotron/glm had no label).
# Labels now come from coder_brains.model_label() -- one source of truth.
ACTIVE_MODEL_SHORT = "model"


def model_label(settings) -> str:
    m = (settings or {}).get("model") or ""
    return coder_brains.model_label(m) if m else "model"


def short_label_for(model: str) -> str:
    """Short card-header name for the brain that wrote a message ('' if no model)."""
    if not model:
        return ""
    return coder_brains.model_label(model).split(" · ")[0]


def model_short(settings) -> str:
    return model_label(settings).split(" · ")[0]


# THE HOLY HARNESS law (Iddo 2026-09-11): a model enters this app as an OPTION in
# the Brain menu, never as a new Desktop icon.
#
# 2026-09-12 00:40 -- Iddo: "תוריד פופאפים של חלונות" / "זוועה". Until tonight each
# brain was a separate PROFILE: its own window, its own desktop_settings.<profile>.json
# and its own conversations-<profile>\ store. That is two harnesses, not one: he asked
# the Maverick window about the psytrance project he had just imported, and that window
# could not see it -- the workspace lived in the main store. The Brain menu now switches
# the door and the model INSIDE this window; one window, one conversation store.
# ("profile" is kept only for `--profile=<name>` launches and their saved geometry.)
# 2026-09-15 harnessswarm: BRAINS is no longer written out here. coder_brains.py is the
# ONE table (door, model, label, max_tokens, Hebrew identity, cost, on_demand); the Brain
# menu, the top-bar combo, the ROOM chips and the QUORUM picker all read it. The notes
# that sat on these rows still hold where they moved: the NVIDIA key lives server-side on
# the eran1 router (never in this repo), and kimi-k3 / nemotron / glm spend part of
# max_tokens on hidden reasoning. Maverick is gone (2026-09-15, Iddo: "לא צריך אותו").
BRAINS = coder_brains.all_brains()


def brain_display_label(b: dict) -> str:
    """Menu/combo text for a brain: its label plus an honest on-demand / paid mark."""
    lab = b.get("label") or b.get("model") or "?"
    if b.get("on_demand"):
        lab += "  ·  ⏳ לפי דרישה · on-demand"
    if b.get("cost") == "paid":
        lab += "  💰"
    return lab


def brain_tooltip(b: dict) -> str:
    tip = "%s — %s" % (b.get("human_name") or b.get("label") or "?", b.get("where_he") or "")
    if b.get("on_demand"):
        tip += ("\nרץ על המחשב של עידו ועולה רק לפי דרישה — ייתכן שהוא לא טעון עכשיו · "
                "runs on Iddo's PC, loaded only on demand; it may not be loaded right now")
    return tip
BRAIN_OFFSET_PX = 40
ICON_PATH = os.path.join(APP_DIR, "almaware-coder.ico")

UI_FONT = "Segoe UI"
MONO_FONT = "Cascadia Mono"

# ---------------------------------------------------------------------------
# Palette — warm, deliberately continuous with the web page (#c8792f accent,
# #fff8ec paper, #241a12 ink) so this reads as the same product, grown up.
# ---------------------------------------------------------------------------

THEMES = {
    "dark": {
        "bg": "#17150f", "sidebar": "#110f0a", "surface": "#201c14",
        "surface_alt": "#262117", "raised": "#2c2619",
        "border": "#332c1f", "border_soft": "#282318",
        "text": "#ece5d6", "dim": "#a2977f", "faint": "#6f6653",
        "accent": "#d98b3a", "accent_hi": "#eda253", "accent_ink": "#1b1409",
        "accent_soft": "#3a2a15",
        "user": "#2a2317", "user_border": "#3d3320",
        "code_bg": "#100e09", "code_border": "#2b2417",
        "ok": "#6fbf73", "warn": "#e0a030", "err": "#e0655f",
        "sel": "#2e2717", "scroll": "#3a3325",
    },
    "light": {
        "bg": "#fdf8ee", "sidebar": "#f4ecdc", "surface": "#fffdf8",
        "surface_alt": "#f9f2e4", "raised": "#ffffff",
        "border": "#e3d7bf", "border_soft": "#ece2cd",
        "text": "#241a12", "dim": "#7a6a55", "faint": "#9c8d78",
        "accent": "#c8792f", "accent_hi": "#b56a24", "accent_ink": "#ffffff",
        "accent_soft": "#f6e7ce",
        "user": "#f2e6cf", "user_border": "#e3d3b3",
        "code_bg": "#f6f0e2", "code_border": "#e3d7bf",
        "ok": "#3f8f52", "warn": "#a8730d", "err": "#b4342e",
        "sel": "#f0e3c9", "scroll": "#d8caae",
    },
    # Bright tan (Iddo 2026-09-11 16:49: "בצבעים בהיר טאן").
    "tan": {
        "bg": "#f3e9d8", "sidebar": "#e9dcc3", "surface": "#faf4e8",
        "surface_alt": "#efe3cd", "raised": "#fffaf1",
        "border": "#d8c6a4", "border_soft": "#e2d3b6",
        "text": "#2e2216", "dim": "#6f5c43", "faint": "#998669",
        "accent": "#9c6a36", "accent_hi": "#845a2d", "accent_ink": "#ffffff",
        "accent_soft": "#ead8b9",
        "user": "#e6d6b8", "user_border": "#d4bf98",
        "code_bg": "#efe5d2", "code_border": "#d8c6a4",
        "ok": "#3f7f4a", "warn": "#9a6a10", "err": "#a8352e",
        "sel": "#e4d2b0", "scroll": "#cdb893",
    },
}

QSS = Template("""
QWidget { color: $text; font-family: "$uifont"; font-size: ${fs}px; }
QMainWindow, #Root { background: $bg; }
QMenuBar { background: $sidebar; color: $dim; border-bottom: 1px solid $border_soft; padding: 2px 4px; }
QMenuBar::item { padding: 5px 10px; border-radius: 6px; background: transparent; }
QMenuBar::item:selected { background: $sel; color: $text; }
QMenu { background: $raised; border: 1px solid $border; border-radius: 10px; padding: 6px; }
QMenu::item { padding: 6px 22px 6px 12px; border-radius: 6px; }
QMenu::item:selected { background: $accent_soft; color: $text; }
QMenu::separator { height: 1px; background: $border_soft; margin: 5px 8px; }

#Sidebar { background: $sidebar; border-right: 1px solid $border_soft; }
#Brand { font-size: ${fs_brand}px; font-weight: 600; color: $text; }
#BrandSub { color: $faint; font-size: ${fs_small}px; }
#SectionLabel { color: $faint; font-size: ${fs_tiny}px; font-weight: 600;
                letter-spacing: 0.9px; padding: 2px 4px; }

QPushButton { background: $surface_alt; color: $text; border: 1px solid $border;
              border-radius: 8px; padding: 7px 13px; }
QPushButton:hover { background: $raised; border-color: $accent; }
QPushButton:pressed { background: $sel; }
QPushButton:disabled { color: $faint; border-color: $border_soft; background: transparent; }
QPushButton#Primary { background: $accent; color: $accent_ink; border: none; font-weight: 600; }
QPushButton#Primary:hover { background: $accent_hi; }
QPushButton#Primary:disabled { background: $border; color: $faint; }
QPushButton#Ghost { background: transparent; border: 1px solid transparent; color: $dim; padding: 5px 8px; }
QPushButton#Ghost:hover { background: $sel; color: $text; }
QPushButton#Chip { background: $surface; border: 1px solid $border; color: $dim;
                   border-radius: 14px; padding: 7px 14px; text-align: left; }
QPushButton#Chip:hover { border-color: $accent; color: $text; background: $surface_alt; }

QToolButton { background: transparent; border: none; color: $dim; padding: 3px 6px; border-radius: 6px; }
QToolButton:hover { background: $sel; color: $text; }

QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background: $surface; border: 1px solid $border; border-radius: 8px;
    padding: 6px 9px; selection-background-color: $accent; selection-color: $accent_ink; }
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus { border-color: $accent; }
QComboBox::drop-down { border: none; width: 18px; }
QComboBox QAbstractItemView { background: $raised; border: 1px solid $border;
                              selection-background-color: $accent_soft; selection-color: $text;
                              outline: none; padding: 4px; }

QListWidget { background: transparent; border: none; outline: none; }
QListWidget::item { border: none; }

QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: $scroll; border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: $accent; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: $scroll; border-radius: 5px; min-width: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

#TopBar { background: $bg; border-bottom: 1px solid $border_soft; }
#ConvTitle { font-size: ${fs_title}px; font-weight: 600; color: $text; }
#ConvSub { color: $faint; font-size: ${fs_small}px; }
#StatusBar { background: $sidebar; border-top: 1px solid $border_soft; color: $faint;
             font-size: ${fs_tiny}px; }

#ChatScroll { background: $bg; border: none; }
#ChatCanvas { background: $bg; }
#UserCard { background: $user; border: 1px solid $user_border; border-radius: 14px; }
#BotCard  { background: $surface; border: 1px solid $border_soft; border-radius: 14px; }
#SysCard  { background: transparent; border: 1px dashed $border; border-radius: 12px; }
#Who { font-weight: 600; color: $text; font-size: ${fs_small}px; }
#When { color: $faint; font-size: ${fs_tiny}px; }
#Body { background: transparent; border: none; }
#CtxBox { background: $surface_alt; border: 1px solid $border_soft; border-radius: 10px; }
#CtxHead { color: $dim; font-size: ${fs_tiny}px; font-weight: 600; }
#CtxItem { background: $bg; border: 1px solid $border_soft; border-radius: 7px;
           color: $dim; font-size: ${fs_tiny}px; }
#CtxGroup { color: $accent; font-size: ${fs_tiny}px; font-weight: 600; letter-spacing: .6px; }

#CodeHead { background: $surface_alt; border: 1px solid $code_border;
            border-top-left-radius: 9px; border-top-right-radius: 9px; border-bottom: none; }
#CodeLang { color: $faint; font-size: ${fs_tiny}px; font-family: "$monofont"; letter-spacing: .5px; }
#CodeBody { background: $code_bg; border: 1px solid $code_border;
            border-bottom-left-radius: 9px; border-bottom-right-radius: 9px; border-top: none;
            font-family: "$monofont"; font-size: ${fs_code}px; padding: 9px 11px; }

#Composer { background: $surface; border: 1px solid $border; border-radius: 14px; }
#Composer[focused="true"] { border-color: $accent; }
#Input { background: transparent; border: none; font-size: ${fs}px; padding: 4px 2px; }
#Hint { color: $faint; font-size: ${fs_tiny}px; }
#Empty { color: $faint; }
#EmptyTitle { color: $text; font-size: 21px; font-weight: 600; }

QTabWidget::pane { border: 1px solid $border; border-radius: 10px; top: -1px; }
QTabBar::tab { background: transparent; color: $dim; padding: 7px 15px; border-radius: 8px; margin: 2px; }
QTabBar::tab:selected { background: $accent_soft; color: $text; }
QCheckBox::indicator { width: 15px; height: 15px; border: 1px solid $border;
                       border-radius: 4px; background: $surface; }
QCheckBox::indicator:checked { background: $accent; border-color: $accent; }
QSplitter::handle { background: $border_soft; width: 1px; }
QLabel[role="dim"] { color: $dim; }
QLabel[role="faint"] { color: $faint; }

QDockWidget { color: $dim; }
QDockWidget::title { background: $sidebar; padding: 6px 10px; border-bottom: 1px solid $border_soft; }
#RoomPanel { background: $sidebar; }
#RoomFeed { background: $surface; border: 1px solid $border_soft; border-radius: 10px; padding: 6px; }
QPushButton#RoomChip { background: $surface; border: 1px solid $border; color: $dim;
                       border-radius: 12px; padding: 4px 10px; }
QPushButton#RoomChip:hover { border-color: $accent; color: $text; }
QPushButton#RoomChip:checked { background: $accent_soft; border-color: $accent; color: $text;
                               font-weight: 600; }
""")


def build_qss(theme: dict, fs: int) -> str:
    d = dict(theme)
    d.update({"uifont": UI_FONT, "monofont": MONO_FONT, "fs": fs,
              "fs_small": max(11, fs - 2), "fs_tiny": max(10, fs - 3),
              "fs_code": max(11, fs - 1), "fs_title": fs + 3, "fs_brand": fs + 1})
    return QSS.substitute(d)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

HEB_RE = re.compile(r"[\u0590-\u05FF]")
LAT_RE = re.compile(r"[A-Za-z]")
FENCE_RE = re.compile(r"```([\w+#.\-]*)[ \t]*\r?\n(.*?)(?:```|\Z)", re.S)


def is_rtl(text: str) -> bool:
    sample = (text or "")[:1200]
    return len(HEB_RE.findall(sample)) > len(LAT_RE.findall(sample))


def split_segments(text: str):
    """-> [('text', s) | ('code', lang, s)]. Tolerates an unterminated fence."""
    out, last = [], 0
    for m in FENCE_RE.finditer(text or ""):
        if m.start() > last:
            out.append(("text", text[last:m.start()]))
        out.append(("code", (m.group(1) or "").strip(), m.group(2)))
        last = m.end()
    if last < len(text or ""):
        out.append(("text", text[last:]))
    return [s for s in out if (s[0] == "code" or s[1].strip())] or [("text", text or "")]


def rel_time(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return ""
    secs = (datetime.now(timezone.utc) - dt).total_seconds()
    if secs < 60:
        return "just now"
    if secs < 3600:
        return "%dm ago" % (secs // 60)
    if secs < 86400:
        return "%dh ago" % (secs // 3600)
    if secs < 86400 * 7:
        return "%dd ago" % (secs // 86400)
    return dt.astimezone().strftime("%d %b")


def clock(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone().strftime("%H:%M")
    except ValueError:
        return ""


def make_icon() -> QIcon:
    """Brand mark: warm rounded square, an accent prompt caret. Written to .ico
    (PNG-in-ICO container) so the Desktop/Start-Menu shortcut has a real icon."""
    pm = QPixmap(256, 256)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(8, 8, 240, 240, 54, 54)
    p.fillPath(path, QColor("#1b1710"))
    p.setPen(QColor("#d98b3a"))
    pen = p.pen()
    pen.setWidth(9)
    p.setPen(pen)
    p.drawPath(path)
    f = QFont(MONO_FONT, 96)
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor("#d98b3a"))
    p.drawText(QRect(0, 0, 256, 250), int(Qt.AlignmentFlag.AlignCenter), "›_")
    p.end()
    if not os.path.exists(ICON_PATH):
        try:
            png = os.path.join(APP_DIR, "_icon256.png")
            pm.save(png, "PNG")
            with open(png, "rb") as f2:
                data = f2.read()
            hdr = (b"\x00\x00\x01\x00\x01\x00"
                   b"\x00\x00\x00\x00\x01\x00\x20\x00"
                   + len(data).to_bytes(4, "little") + (22).to_bytes(4, "little"))
            with open(ICON_PATH, "wb") as f2:
                f2.write(hdr + data)
            os.remove(png)
        except OSError as e:
            print("[coder] icon write failed: %s" % e, file=sys.stderr)
    return QIcon(pm)


def _status_dot(color_hex: str, size: int = 10) -> QIcon:
    """A small filled circle for the Brain combo box -- green/red/grey liveness,
    drawn rather than an emoji so it renders identically on every Windows font."""
    pm = QPixmap(size, size)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(color_hex))
    p.drawEllipse(0, 0, size, size)
    p.end()
    return QIcon(pm)


# ---------------------------------------------------------------------------
# Code block: language label + Copy + a generic syntax highlighter
# ---------------------------------------------------------------------------

KEYWORDS = set("""def class return if elif else for while in not and or is None True False
import from as with try except finally raise lambda yield pass break continue global
async await self assert del function const let var new this typeof instanceof export
default extends implements interface public private protected static void int float
double string bool struct enum type fn let mut pub use match impl where echo local
export set param foreach do then fi esac case done elif shift""".split())


class MiniHighlighter(QSyntaxHighlighter):
    """Deliberately language-agnostic: strings, comments, numbers, keywords.
    A real per-language grammar is not worth the weight here; this is enough to
    stop a code block from being a wall of one colour."""

    def __init__(self, doc: QTextDocument, theme: dict):
        super().__init__(doc)
        def fmt(color, bold=False, italic=False):
            f = QTextCharFormat()
            f.setForeground(QColor(color))
            f.setFontWeight(QFont.Weight.Bold if bold else QFont.Weight.Normal)
            f.setFontItalic(italic)
            return f
        warm = theme is THEMES["dark"]
        self.f_kw = fmt(theme["accent"], bold=True)
        self.f_str = fmt("#8fbf7f" if warm else "#3f7f43")
        self.f_num = fmt("#c9a2e0" if warm else "#7a4fa0")
        self.f_com = fmt(theme["faint"], italic=True)
        self.rules = [
            (re.compile(r'(\"\"\"|\'\'\')(.*?)\1', re.S), self.f_str),
            (re.compile(r'"(?:\\.|[^"\\])*"'), self.f_str),
            (re.compile(r"'(?:\\.|[^'\\])*'"), self.f_str),
            (re.compile(r"`(?:\\.|[^`\\])*`"), self.f_str),
            (re.compile(r"\b\d[\d_]*(?:\.\d+)?(?:[eE][-+]?\d+)?\b"), self.f_num),
            (re.compile(r"(#|//|--).*$"), self.f_com),
            (re.compile(r"/\*.*?\*/", re.S), self.f_com),
        ]
        self.word = re.compile(r"\b[A-Za-z_][A-Za-z_0-9]*\b")

    def highlightBlock(self, text: str) -> None:
        for m in self.word.finditer(text):
            if m.group(0) in KEYWORDS:
                self.setFormat(m.start(), m.end() - m.start(), self.f_kw)
        for rx, f in self.rules:
            for m in rx.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), f)


class CodeView(QPlainTextEdit):
    """A code view that gives the wheel back to the chat scroller once its own
    content fits — otherwise the page stops scrolling under the cursor."""

    def wheelEvent(self, e):
        if self.verticalScrollBar().maximum() == 0:
            e.ignore()
        else:
            super().wheelEvent(e)


class CodeBlock(QFrame):
    MAX_H = 520

    def __init__(self, lang: str, code: str, theme: dict, parent=None):
        super().__init__(parent)
        self.code = code.rstrip("\n")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        head = QWidget(objectName="CodeHead")
        hl = QHBoxLayout(head)
        hl.setContentsMargins(11, 5, 6, 5)
        hl.setSpacing(6)
        hl.addWidget(QLabel((lang or "code").lower(), objectName="CodeLang"))
        hl.addStretch(1)
        self.copy_btn = QToolButton()
        self.copy_btn.setText("Copy")
        self.copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_btn.clicked.connect(self._copy)
        hl.addWidget(self.copy_btn)
        lay.addWidget(head)

        self.view = CodeView(objectName="CodeBody")
        self.view.setPlainText(self.code)
        self.view.setReadOnly(True)
        self.view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.view.setFont(QFont(MONO_FONT, max(9, theme.get("_code_pt", 10))))
        self.view.setFrameShape(QFrame.Shape.NoFrame)
        self.hl = MiniHighlighter(self.view.document(), theme)
        lay.addWidget(self.view)
        QTimer.singleShot(0, self._fit)

    def _fit(self):
        # Measure the laid-out document, NOT QFontMetrics of the font we asked for:
        # the QSS #CodeBody font-size wins over setFont(), so a metrics-based guess
        # came out short and chopped the last line off every code block (seen in the
        # first Hebrew screenshot, 2026-09-09).
        if getattr(self, "_fitting", False):
            return                        # re-entrancy guard; see Composer._grow
        self._fitting = True
        try:
            # Two traps here, both hit for real on 2026-09-09:
            #  1. QPlainTextEdit uses QPlainTextDocumentLayout, whose documentSize()
            #     returns the height in BLOCKS, not pixels -- using it collapsed every
            #     code block to a single line.
            #  2. self.view.fontMetrics() (resolved, post-polish, so it reflects the
            #     QSS font-size) -- not QFontMetrics(QFont(...)) of the font we asked
            #     for, which is a different size and chopped the last line off.
            # The horizontal scrollbar is real estate too: NoWrap means long lines
            # produce one, and forgetting it ate exactly one line.
            fm = self.view.fontMetrics()
            h = fm.lineSpacing() * self.view.document().blockCount() + 30
            if self.view.horizontalScrollBar().maximum() > 0:
                h += self.view.horizontalScrollBar().sizeHint().height()
            self.view.setFixedHeight(min(self.MAX_H, max(38, h)))
        finally:
            self._fitting = False

    def showEvent(self, e):
        super().showEvent(e)
        self._fit()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit()

    def _copy(self):
        QGuiApplication.clipboard().setText(self.code)
        self.copy_btn.setText("Copied ✓")
        QTimer.singleShot(1400, lambda: self.copy_btn.setText("Copy"))


class FlowText(QTextBrowser):
    """Markdown paragraph that grows to fit its content — no inner scrollbar."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Body")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setOpenExternalLinks(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.document().setDocumentMargin(0)
        self.document().contentsChanged.connect(self._fit)
        self.viewport().setAutoFillBackground(False)

    def wheelEvent(self, e):
        e.ignore()          # a message never scrolls; the chat area does

    def set_text(self, text: str, markdown: bool = True):
        rtl = is_rtl(text)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft if rtl
                                else Qt.LayoutDirection.LeftToRight)
        opt = QTextOption()
        opt.setAlignment(Qt.AlignmentFlag.AlignRight if rtl else Qt.AlignmentFlag.AlignLeft)
        opt.setTextDirection(Qt.LayoutDirection.RightToLeft if rtl
                             else Qt.LayoutDirection.LeftToRight)
        opt.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.document().setDefaultTextOption(opt)
        if markdown:
            self.document().setMarkdown(
                text, QTextDocument.MarkdownFeature.MarkdownDialectGitHub)
        else:
            self.setPlainText(text)
        self._fit()

    def _fit(self):
        w = max(80, self.viewport().width())
        self.document().setTextWidth(w)
        self.setFixedHeight(int(self.document().size().height()) + 8)
        # setMarkdown/setPlainText park the cursor at the end and scroll there, which
        # clipped the top half of the first line of every message (seen in the first
        # real screenshot, 2026-09-09). Pin the view back to the top -- the widget is
        # exactly as tall as its content, so there is nothing below to look at.
        self.verticalScrollBar().setValue(0)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit()


# ---------------------------------------------------------------------------
# The "context used" panel — the web page's transparency, kept
# ---------------------------------------------------------------------------

class ContextPanel(QFrame):
    def __init__(self, ctx: dict, theme: dict, parent=None):
        super().__init__(parent)
        self.setObjectName("CtxBox")
        self.ctx = ctx or {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 7, 10, 7)
        lay.setSpacing(6)

        n = engine.context_count(self.ctx)
        self.toggle = QPushButton("▸  context used (%d)" % n, objectName="Ghost")
        self.toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle.setStyleSheet("text-align:left; padding-left:0;")
        self.toggle.clicked.connect(self._toggle)
        lay.addWidget(self.toggle)

        self.body = QWidget()
        bl = QVBoxLayout(self.body)
        bl.setContentsMargins(0, 2, 0, 0)
        bl.setSpacing(7)
        groups = [
            ("BRAIN2 — the second brain: the maintained wiki (127.0.0.1:8897)",
             self.ctx.get("brain2") or [],
             lambda p: "%s · %s · %s\n%s" % (p.get("id"), p.get("confidence"),
                                             p.get("updated"), p.get("snip"))),
            ("ALMA-RECALL — memory + every AI chat", self.ctx.get("recall") or [],
             lambda h: "[%s %s] %s\n%s" % (h.get("source"), h.get("ts"),
                                           h.get("title"), h.get("snip"))),
            ("ALMAWARE STANDARD — requirements", self.ctx.get("standard_reqs") or [],
             lambda r: "%s  (%s)\n%s" % (r.get("id"), r.get("section"), r.get("text"))),
            ("ALMAWARE STANDARD — section", self.ctx.get("standard_secs") or [],
             lambda s: "%s\n%s" % (s.get("header"), (s.get("body") or "")[:320])),
            ("Project files under D:\\CLAUDE (grep)", self.ctx.get("project") or [],
             lambda p: "%s:%s\n%s" % (p.get("path"), p.get("line"), p.get("text"))),
            ("RAMCHAT — team coordination council", self.ctx.get("ramchat") or [],
             lambda m: "[%s %s]\n%s" % (m.get("at"), m.get("who"), m.get("text"))),
            ("QUORUM — past debate rooms (127.0.0.1:8099)", self.ctx.get("quorum") or [],
             lambda q: 'room "%s" — %s\n%s' % (q.get("room"), q.get("who"), q.get("snip"))),
        ]
        any_group = False
        for title, items, render in groups:
            if not items:
                continue
            any_group = True
            bl.addWidget(QLabel(title.upper(), objectName="CtxGroup"))
            for it in items:
                lbl = QLabel(render(it), objectName="CtxItem")
                lbl.setWordWrap(True)
                lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                lbl.setContentsMargins(8, 6, 8, 6)
                bl.addWidget(lbl)
        if not any_group:
            lbl = QLabel("nothing matched this turn — the reply rests on the standing "
                         "CONTEXT.md and the conversation only.", objectName="CtxItem")
            lbl.setWordWrap(True)
            lbl.setContentsMargins(8, 6, 8, 6)
            bl.addWidget(lbl)
        self.body.setVisible(False)
        lay.addWidget(self.body)

    def _toggle(self):
        vis = not self.body.isVisible()
        self.body.setVisible(vis)
        self.toggle.setText(self.toggle.text().replace("▸", "▾") if vis
                            else self.toggle.text().replace("▾", "▸"))


# ---------------------------------------------------------------------------
# A message
# ---------------------------------------------------------------------------

class MessageCard(QFrame):
    regenerate = pyqtSignal()
    delete_turn = pyqtSignal()

    def __init__(self, role: str, theme: dict, ts: str | None = None, parent=None,
                 who: str | None = None, who_tip: str = ""):
        super().__init__(parent)
        self.role = role
        self.theme = theme
        self.raw = ""
        self.setObjectName("UserCard" if role == "user" else "BotCard")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 12, 16, 12)
        outer.setSpacing(8)

        head = QHBoxLayout()
        head.setSpacing(8)
        dot = QLabel("●")
        dot.setStyleSheet("color: %s; font-size: 11px;"
                          % (theme["dim"] if role == "user" else theme["accent"]))
        head.addWidget(dot)
        # 2026-09-15 harnessswarm: an assistant card names the brain that WROTE it (the
        # message's own "speaker"/"model" tag), not whichever brain is selected now.
        self.who_lbl = QLabel("Iddo" if role == "user" else (who or ACTIVE_MODEL_SHORT),
                              objectName="Who")
        if who_tip:
            self.who_lbl.setToolTip(who_tip)
        head.addWidget(self.who_lbl)
        self.when = QLabel(clock(ts), objectName="When")
        head.addWidget(self.when)
        head.addStretch(1)
        self.stat = QLabel("", objectName="When")
        head.addWidget(self.stat)
        self.copy_btn = QToolButton()
        self.copy_btn.setText("⧉")
        self.copy_btn.setToolTip("Copy this message")
        self.copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_btn.clicked.connect(self._copy)
        head.addWidget(self.copy_btn)
        if role == "assistant":
            self.regen_btn = QToolButton()
            self.regen_btn.setText("↻")
            self.regen_btn.setToolTip("Regenerate this reply")
            self.regen_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.regen_btn.clicked.connect(self.regenerate.emit)
            self.regen_btn.setVisible(False)
            head.addWidget(self.regen_btn)
        outer.addLayout(head)

        self.body_box = QVBoxLayout()
        self.body_box.setSpacing(9)
        self.body_box.setContentsMargins(0, 0, 0, 0)
        outer.addLayout(self.body_box)

        self.ctx_panel = None
        self.outer = outer
        self._stream_view = None

    # -- streaming -------------------------------------------------------
    def begin_stream(self):
        self._clear_body()
        self._stream_view = FlowText()
        self._stream_view.set_text("", markdown=False)
        self.body_box.addWidget(self._stream_view)

    def stream_text(self, text: str):
        self.raw = text
        if self._stream_view is not None and _alive(self._stream_view):
            self._stream_view.set_text(text, markdown=False)

    # -- final render ----------------------------------------------------
    def set_content(self, text: str):
        self.raw = text or ""
        if not _alive(self.body_box):
            return                                   # the card is gone; nothing to draw into
        self._clear_body()
        self._stream_view = None
        for seg in split_segments(self.raw):
            if seg[0] == "code":
                self.body_box.addWidget(CodeBlock(seg[1], seg[2], self.theme))
            else:
                w = FlowText()
                w.set_text(seg[1].strip("\n"))
                self.body_box.addWidget(w)

    def set_stats(self, text: str):
        self.stat.setText(text)

    def set_context(self, ctx: dict):
        if self.ctx_panel is not None:
            self.ctx_panel.setParent(None)
            self.ctx_panel.deleteLater()
        self.ctx_panel = ContextPanel(ctx, self.theme)
        self.outer.addWidget(self.ctx_panel)

    def show_regen(self, show: bool):
        if self.role == "assistant":
            self.regen_btn.setVisible(show)

    def _clear_body(self):
        while self.body_box.count():
            it = self.body_box.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

    def _copy(self):
        QGuiApplication.clipboard().setText(self.raw)
        self.copy_btn.setText("✓")
        QTimer.singleShot(1200, lambda: self.copy_btn.setText("⧉"))

    def contextMenuEvent(self, e):
        m = QMenu(self)
        m.addAction("Copy message", self._copy)
        if self.role == "assistant":
            m.addAction("Regenerate", self.regenerate.emit)
        m.addSeparator()
        m.addAction("Delete this turn", self.delete_turn.emit)
        m.exec(e.globalPos())


# ---------------------------------------------------------------------------
# Worker: retrieval + door, off the UI thread
# ---------------------------------------------------------------------------

class TurnWorker(QThread):
    stage = pyqtSignal(str)
    ctx_ready = pyqtSignal(dict)
    chunk = pyqtSignal(str)
    done = pyqtSignal(str, dict, float, bool)   # text, usage, seconds, streamed
    failed = pyqtSignal(str, dict)              # message, ctx

    def __init__(self, history, user_msg, settings, workspace, conv_id, parent=None):
        super().__init__(parent)
        self.history, self.user_msg = history, user_msg
        self.settings, self.workspace = dict(settings), workspace
        self.conv_id = conv_id
        self._stop = False
        self._abort_holder = []   # holds the live urllib response once opened

    def stop(self):
        self._stop = True
        # 2026-09-12, Iddo hit this live: during a slow door's prompt-eval no
        # bytes arrive, so the read loop that checks _stop never runs and Stop
        # just sits at "stopping..." until the full request timeout (900s).
        # Closing the live socket here raises inside whatever blocking call is
        # in progress and unblocks it immediately.
        for resp in self._abort_holder:
            try:
                resp.close()
            except Exception:
                pass

    def run(self):
        ctx = dict(engine.EMPTY_CTX)
        try:
            self.stage.emit("searching memory, the standard and the project…")
            ctx = engine.build_context(self.user_msg, self.settings, self.workspace)
            self.ctx_ready.emit(ctx)
            # conv_id gives this thread its own rolling summary file (older
            # turns get compressed into <conv_id>.summary.txt instead of just
            # dropped once history nears MAX_PROMPT_CHARS -- taste.build_messages,
            # 2026-09-09); on_stage surfaces that moment in the status text
            # below rather than it happening silently.
            messages = engine.build_messages(self.history, self.user_msg, ctx, self.workspace,
                                             conv_id=self.conv_id, on_stage=self.stage.emit,
                                             settings=self.settings,
                                             abort_holder=self._abort_holder,
                                             should_stop=lambda: self._stop)
            self.stage.emit("waiting for %s…" % ACTIVE_MODEL_SHORT)
            t0 = time.time()
            if self.settings.get("stream", True):
                try:
                    text, usage, stopped = engine.stream_completion(
                        messages, self.settings, self.chunk.emit, lambda: self._stop,
                        abort_holder=self._abort_holder)
                    if stopped:
                        # A stop is never "the model returned nothing" (2026-09-12):
                        # a 12k-token prompt spends ~35 s in prompt processing before
                        # the first token, so Stop/Escape almost always lands while
                        # nothing has arrived yet -- and the model keeps generating.
                        text = (text + "\n\n_(נעצר על ידך · stopped by you)_") if text.strip() else (
                            "**נעצר על ידך — עוד שום דבר לא חזר מהמודל.**\n\n"
                            "Stopped before the first token. A long prompt can spend ~35 s "
                            "in prompt processing before anything appears, so the model was "
                            "still working. Use *Regenerate* to ask it again.")
                    self.done.emit(text, usage, time.time() - t0, True)
                    return
                except engine.DoorError as e:
                    # Do not hide it: say the streaming path broke, then try the
                    # blocking one rather than showing nothing.
                    self.stage.emit("stream failed (%s) — retrying without streaming…" % e)
            text, usage = engine.blocking_completion(messages, self.settings)
            self.done.emit(text, usage, time.time() - t0, False)
        except Exception as e:
            self.failed.emit("%s: %s" % (type(e).__name__, e), ctx)


class DoorProbe(QThread):
    result = pyqtSignal(bool, str)

    def __init__(self, door, parent=None):
        super().__init__(parent)
        self.door = door

    def run(self):
        ok, info = engine.door_status(self.door)
        self.result.emit(ok, info)


class MuseProbe(QThread):
    """Super-project Phase 4: Muse status via the existing Muse Door (:8900),
    the same scoped door built 2026-09-13 -- no new probe surface.

    2026-09-15 harnessswarm: probe '/' itself. The Muse Door is not an OpenAI door
    and has no /v1/models; engine.door_status() asked for exactly that path, got a
    404 and painted "muse: down" in red while the door was up (measured 03:3x:
    GET / -> 200, GET /v1/models -> 404)."""
    MUSE_DOOR = "http://127.0.0.1:8900/"
    result = pyqtSignal(bool)

    def run(self):
        try:
            with urllib.request.urlopen(self.MUSE_DOOR, timeout=5) as r:
                code = int(getattr(r, "status", 0) or 0)
            self.result.emit(200 <= code < 400)
        except Exception:
            self.result.emit(False)


class NowProbe(QThread):
    """Super-project Phase 4: the Now strip's background check. Reuses
    RAMCHAT's own get_queue() directly (ramlink.py), not a reimplementation."""
    result = pyqtSignal(object)  # int (open count) or None on failure

    def run(self):
        try:
            sys.path.insert(0, r"D:\CLAUDE\RAMCHAT")
            import ramlink
            items, _src = ramlink.get_queue()
            open_n = sum(1 for t in items if not t.get("claimed_by")
                        and t.get("status") not in ramlink.TERMINAL_STATUS
                        and t.get("status") not in ramlink.BUSY_STATUS)
            self.result.emit(open_n)
        except Exception:
            self.result.emit(None)


class FleetProbe(QThread):
    """Super-project Phase 4 (2026-09-14): the Fleet strip's background check.
    Reuses fleet_inventory.check() directly -- the same probe fleet_inventory.py
    --check already runs -- instead of a second door-checking implementation.
    Off the UI thread for the same reason DoorProbe/BrainProbe are: a dead box
    is a real multi-second timeout and must never freeze the window."""
    result = pyqtSignal(object)  # list of (name, ok, code, elapsed_s, url) or None on failure

    def run(self):
        try:
            sys.path.insert(0, r"D:\CLAUDE")
            import fleet_inventory
            rows = fleet_inventory.check(timeout=4.0)
            self.result.emit(rows)
        except Exception as e:
            self.result.emit(None)


class BrainProbe(QThread):
    """Checks every BRAINS door's /v1/models, off the UI thread, for the top-bar
    combo box. One thread, doors de-duplicated (kimi-k3, nemotron and glm share
    the eran1 router door, so that door is only hit once) -- never touches Qt widgets
    itself, only emits a plain dict back to the main thread."""
    result = pyqtSignal(dict)   # {door: (ok, info)}

    def __init__(self, doors, parent=None):
        super().__init__(parent)
        self.doors = list(doors)

    def run(self):
        out = {}
        for d in self.doors:
            try:
                out[d] = engine.door_status(d)
            except Exception as e:
                out[d] = (False, "%s: %s" % (type(e).__name__, e))
        self.result.emit(out)


class ModeWorker(QThread):
    """BRAIN SWITCH (Iddo 2026-09-15 10:07-10:08: "only one model runs at a time and
    I choose - easily"). Runs coder_brains.ensure_brain_mode() -- the ONE shared
    client of eran4's /mode API, the same one the tailnet twin calls -- off the UI
    thread: waking the coder can take a minute or more (240 s contract limit).
    Never touches a widget; emits plain text and a plain dict only."""
    status = pyqtSignal(str)
    result = pyqtSignal(dict)

    def __init__(self, brain, parent=None):
        super().__init__(parent)
        self.brain = dict(brain or {})
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            res = coder_brains.ensure_brain_mode(self.brain, on_status=self.status.emit, wait=True,
                                                 should_stop=lambda: self._stop)
        except Exception as e:                      # ensure_brain_mode never raises; belt and braces
            res = {"ok": False, "state": "error", "mode": None, "target": "coder",
                   "detail": str(e), "text": "%s: %s" % (type(e).__name__, e),
                   "model": self.brain.get("model")}
        try:
            self.result.emit(res)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 💬 ROOM + ⚖️ QUORUM threads (2026-09-15 harnessswarm). Nothing below touches a
# Qt widget: each thread only emits plain Python data back to the UI thread.
# ---------------------------------------------------------------------------

class RoomPoll(QThread):
    """Tail of the RAMCHAT room through coder_room.RamchatStore (ramlink.py's own
    get_transcript) -- off the UI thread, RAMCHAT's durable file is not small."""
    result = pyqtSignal(object)   # list of {ts, who, text}, or None on failure

    def __init__(self, n=60, parent=None):
        super().__init__(parent)
        self.n = n

    def run(self):
        try:
            self.result.emit(coder_room.RamchatStore().read(self.n))
        except Exception as e:
            _brain_log("room poll failed: %s: %s" % (type(e).__name__, e))
            self.result.emit(None)


class RoomSendWorker(QThread):
    """One addressed room line: coder_room.address() posts Iddo's words to RAMCHAT,
    then each target he ticked answers once, in order. Brains are free; 'claude'
    is in `targets` only when he ticked Claude 💰 for THIS line; 'muse' queues a
    task for muse-code. address() never raises for a target -- only failing to post
    Iddo's own line can, and that comes back as an error string (his text is then
    offered again, because nothing reached the room)."""
    reply = pyqtSignal(str, str)      # who, reply
    completed = pyqtSignal(object)    # list[(who, reply)] or an error string

    def __init__(self, text, targets, parent=None):
        super().__init__(parent)
        self.text = text
        self.targets = list(targets)

    def run(self):
        try:
            room = coder_room.RamchatStore()
            out = coder_room.address(room, self.text, self.targets,
                                     on_reply=lambda who, rep: self.reply.emit(who, rep))
            self.completed.emit(out)
        except Exception as e:
            _brain_log("room send failed: %s: %s" % (type(e).__name__, e))
            self.completed.emit("%s: %s" % (type(e).__name__, e))


class QuorumSeatProbe(QThread):
    """GET /api/models on QUORUM (coder_quorum.seatable) -- a real network wait,
    never on the UI thread. {} means QUORUM did not answer."""
    result = pyqtSignal(object)

    def run(self):
        try:
            self.result.emit(coder_quorum.seatable(timeout=coder_quorum.SEATABLE_TIMEOUT_S,
                                                   url=coder_quorum.QUORUM_URL))
        except Exception as e:
            _brain_log("quorum seat probe failed: %s: %s" % (type(e).__name__, e))
            self.result.emit({})


class QuorumWorker(QThread):
    """One live QUORUM debate (POST /debate, SSE) on its own thread. Every SSE event
    is forwarded as sse(name, data); `completed` carries QuorumRun.run()'s return
    (the done payload, or {'error': ...}). stop() is thread-safe: cancel() closes
    the stream. (The signal is `sse`, not `event`: a signal named `event` would
    shadow QObject.event() and break Qt's own event delivery to this object.)"""
    sse = pyqtSignal(str, object)
    completed = pyqtSignal(object)

    def __init__(self, topic, seats, rounds, parent=None):
        super().__init__(parent)
        self.run_obj = coder_quorum.QuorumRun(topic, seats, rounds=rounds,
                                              url=coder_quorum.QUORUM_URL)

    def stop(self):
        try:
            self.run_obj.cancel()
        except Exception:
            pass

    def run(self):
        try:
            done = self.run_obj.run(lambda name, data: self.sse.emit(name, data))
        except Exception as e:
            done = {"error": "%s: %s" % (type(e).__name__, e)}
        self.completed.emit(done if isinstance(done, dict) else {"error": repr(done)})


# ---------------------------------------------------------------------------
# Sidebar list rendering
# ---------------------------------------------------------------------------

class ConvDelegate(QStyledItemDelegate):
    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self.theme = theme

    def sizeHint(self, option, index):
        return QSize(200, 52)

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = option.rect.adjusted(6, 2, -6, -2)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if selected:
            painter.setPen(QColor(self.theme["accent"]))
            painter.setBrush(QColor(self.theme["accent_soft"]))
            painter.drawRoundedRect(r, 9, 9)
        elif hovered:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(self.theme["sel"]))
            painter.drawRoundedRect(r, 9, 9)

        data = index.data(Qt.ItemDataRole.UserRole) or {}
        title = data.get("title") or "(untitled)"
        if data.get("pinned"):
            title = "📌 " + title
        sub = "%d msg%s · %s" % (data.get("n", 0), "" if data.get("n") == 1 else "s",
                                 rel_time(data.get("updated")))
        if data.get("ws_name"):
            sub = data["ws_name"] + " · " + sub

        f = QFont(UI_FONT, 10)
        f.setBold(selected)
        painter.setFont(f)
        painter.setPen(QColor(self.theme["text"] if selected or hovered else self.theme["text"]))
        fm = QFontMetrics(f)
        tr = QRect(r.left() + 11, r.top() + 7, r.width() - 22, fm.height())
        painter.drawText(tr, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                         fm.elidedText(title, Qt.TextElideMode.ElideRight, tr.width()))

        f2 = QFont(UI_FONT, 8)
        painter.setFont(f2)
        painter.setPen(QColor(self.theme["faint"]))
        fm2 = QFontMetrics(f2)
        sr = QRect(r.left() + 11, r.top() + 9 + fm.height(), r.width() - 22, fm2.height())
        painter.drawText(sr, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                         fm2.elidedText(sub, Qt.TextElideMode.ElideRight, sr.width()))
        painter.restore()


# ---------------------------------------------------------------------------
# Composer
# ---------------------------------------------------------------------------

class Composer(QFrame):
    submitted = pyqtSignal(str)
    stopped = pyqtSignal()
    remember_requested = pyqtSignal(str)
    quorum_requested = pyqtSignal(str)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setObjectName("Composer")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.settings = settings
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 12, 10)
        lay.setSpacing(6)

        self._busy = False
        self.input = QTextEdit(objectName="Input")
        self.input.setPlaceholderText("שאל את הקודר · ask the coder…    (Enter to send, Shift+Enter for a new line)")
        self.input.setAcceptRichText(False)
        self.input.setFrameShape(QFrame.Shape.NoFrame)
        self.input.installEventFilter(self)
        self.input.textChanged.connect(self._grow)
        self.input.setFixedHeight(46)
        lay.addWidget(self.input)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.hint = QLabel("", objectName="Hint")
        row.addWidget(self.hint)
        row.addStretch(1)
        # Memory box (super-project Phase 4): sends the current input text to
        # brain2's /remember (a real proposal, not a private note) instead of
        # only ever being conversation. Reuses the existing propose pipeline.
        self.remember_btn = QPushButton("🧠 Remember", objectName="Ghost")
        self.remember_btn.setToolTip("Propose this text as a brain2 fact (queued for the maintainer)")
        self.remember_btn.clicked.connect(
            lambda: self.remember_requested.emit(self.input.toPlainText().strip()))
        row.addWidget(self.remember_btn)
        # ⚖️ QUORUM (2026-09-15 harnessswarm): a live debate on the text typed here.
        self.quorum_btn = QPushButton("⚖️ קוורום", objectName="Ghost")
        self.quorum_btn.setToolTip(
            "פתח דיון קוורום על מה שכתוב כאן · start a QUORUM debate on this text "
            "(Ctrl+Shift+Q)")
        self.quorum_btn.clicked.connect(
            lambda _c=False: self.quorum_requested.emit(self.input.toPlainText().strip()))
        row.addWidget(self.quorum_btn)
        # Iddo 2026-09-15 00:57: a small, always-visible Hebrew+English count of
        # queued messages -- MainWindow owns the actual queue, this is just the label.
        self.queue_lbl = QLabel("", objectName="Hint")
        self.queue_lbl.setVisible(False)
        self.queue_lbl.setToolTip(
            "כל הודעה ממתינה נשלחת למוח שנבחר ברגע שהיא בפועל יוצאת, לא למוח שהיה "
            "נבחר כשהקלדת אותה · each queued message is sent using whichever brain "
            "is selected at the moment it actually goes out, not the one selected "
            "when you typed it.")
        row.addWidget(self.queue_lbl)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setVisible(False)
        self.stop_btn.clicked.connect(self.stopped.emit)
        row.addWidget(self.stop_btn)
        self.send_btn = QPushButton("Send  ⏎", objectName="Primary")
        self.send_btn.setToolTip(
            "בזמן שסבב רץ ההודעה תתווסף לתור ותישלח אוטומטית כשהוא ייגמר · "
            "while a turn is running this queues instead of blocking")
        self.send_btn.clicked.connect(self._submit)
        row.addWidget(self.send_btn)
        lay.addLayout(row)

    def eventFilter(self, obj, ev):
        if obj is self.input and ev.type() == QEvent.Type.KeyPress:
            enter = ev.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            shift = bool(ev.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            ctrl = bool(ev.modifiers() & Qt.KeyboardModifier.ControlModifier)
            if enter and (ctrl or (self.settings.get("send_on_enter", True) and not shift)):
                self._submit()
                return True
        if obj is self.input and ev.type() in (QEvent.Type.FocusIn, QEvent.Type.FocusOut):
            self.setProperty("focused", "true" if ev.type() == QEvent.Type.FocusIn else "false")
            self.style().unpolish(self)
            self.style().polish(self)
        return super().eventFilter(obj, ev)

    def _grow(self):
        # Re-entrancy guard: QTextEdit.setAlignment() edits the block format, which
        # emits textChanged, which lands back here. Without this it is an infinite
        # recursion that takes the whole process down with a stack overflow --
        # measured, not theoretical (2026-09-09, first GUI selftest run).
        if getattr(self, "_growing", False):
            return
        self._growing = True
        try:
            doc = self.input.document()
            doc.setTextWidth(self.input.viewport().width())
            h = int(doc.size().height()) + 14
            self.input.setFixedHeight(max(46, min(240, h)))
            rtl = is_rtl(self.input.toPlainText())
            if rtl != getattr(self, "_rtl", None):
                self._rtl = rtl
                d = Qt.LayoutDirection.RightToLeft if rtl else Qt.LayoutDirection.LeftToRight
                opt = doc.defaultTextOption()
                opt.setAlignment(Qt.AlignmentFlag.AlignRight if rtl
                                 else Qt.AlignmentFlag.AlignLeft)
                opt.setTextDirection(d)
                doc.setDefaultTextOption(opt)
                self.input.setLayoutDirection(d)
        finally:
            self._growing = False

    def _submit(self):
        # Iddo 2026-09-15 00:57: typing and Send/Enter are NEVER blocked by a
        # running turn. This always emits -- MainWindow.send_message decides
        # whether to start it now or queue it (self.worker is not None there).
        # Always clearing here (not just on the non-busy path) is what lets him
        # fire off several messages in a row while one is still streaming.
        text = self.input.toPlainText().strip()
        if not text:
            return
        self.input.clear()
        self.submitted.emit(text)

    def clear(self):
        self.input.clear()

    def set_busy(self, busy: bool, note: str = ""):
        # 2026-09-12, Iddo: let him keep typing his next message while a reply
        # streams in -- the input box is never disabled.
        # 2026-09-15, Iddo 00:57: Send now ALSO stays visible+enabled while busy
        # (it queues instead of sending immediately) -- Stop appears alongside it
        # to still cut the CURRENT turn short. Queueing itself lives in MainWindow
        # (send_message / _enqueue_message), not here.
        self._busy = busy
        self.stop_btn.setVisible(busy)
        self.hint.setText(note)

    def set_queue_count(self, n: int):
        """Small Hebrew+English 'N waiting' indicator. MainWindow calls this
        whenever its queue changes (enqueue / cancel / dispatch)."""
        if n <= 0:
            self.queue_lbl.setVisible(False)
            self.queue_lbl.setText("")
            return
        word = "הודעה אחת ממתינה" if n == 1 else "%d הודעות ממתינות" % n
        self.queue_lbl.setText("⏳ %s בתור · %d queued" % (word, n))
        self.queue_lbl.setVisible(True)


# ---------------------------------------------------------------------------
# Dialogs
# ---------------------------------------------------------------------------

class SettingsDialog(QDialog):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings · " + APP_NAME)
        self.setMinimumWidth(520)
        self.s = dict(settings)
        tabs = QTabWidget()

        # --- model
        mw = QWidget()
        g = QGridLayout(mw)
        g.setColumnStretch(1, 1)
        self.door = QLineEdit(self.s["door"])
        self.model = QLineEdit(self.s["model"])
        self.temp = QDoubleSpinBox()
        self.temp.setRange(0.0, 2.0)
        self.temp.setSingleStep(0.05)
        self.temp.setValue(float(self.s["temperature"]))
        self.maxtok = QSpinBox()
        self.maxtok.setRange(256, 32000)
        self.maxtok.setSingleStep(500)
        self.maxtok.setValue(int(self.s["max_tokens"]))
        self.stream = QCheckBox("Stream tokens as they are generated")
        self.stream.setChecked(bool(self.s["stream"]))
        for i, (lbl, w) in enumerate([("Door (OpenAI-compatible URL)", self.door),
                                      ("Model id", self.model),
                                      ("Temperature", self.temp),
                                      ("Max reply tokens", self.maxtok)]):
            g.addWidget(QLabel(lbl), i, 0)
            g.addWidget(w, i, 1)
        g.addWidget(self.stream, 4, 0, 1, 2)
        note = QLabel("Model context is 32,768 tokens. This build's tool-calling is broken "
                      "(xgrammar scar) — the app never sends tools/tool_choice.")
        note.setWordWrap(True)
        note.setProperty("role", "faint")
        g.addWidget(note, 5, 0, 1, 2)
        g.setRowStretch(6, 1)
        tabs.addTab(mw, "Model")

        # --- retrieval
        rw = QWidget()
        rg = QVBoxLayout(rw)
        self.c_recall = QCheckBox("ALMA-RECALL — search memory files + every AI chat (127.0.0.1:8794)")
        self.c_std = QCheckBox("ALMAWARE STANDARD — the 184 ALMA-<AREA>-<nnn> requirements")
        self.c_proj = QCheckBox("Project grep — D:\\CLAUDE subtree named in the message, plus the workspace root")
        self.c_ramchat = QCheckBox("RAMCHAT — recent posts from other AI agents/sessions (team council)")
        self.c_quorum = QCheckBox("QUORUM — past debate rooms from the multi-AI arena (127.0.0.1:8099)")
        self.c_brain2 = QCheckBox("BRAIN2 — the second brain: the maintained wiki where projects live (127.0.0.1:8897)")
        for c, k in ((self.c_recall, "rag_recall"), (self.c_std, "rag_standard"),
                     (self.c_proj, "rag_project"), (self.c_ramchat, "rag_ramchat"),
                     (self.c_quorum, "rag_quorum"), (self.c_brain2, "rag_brain2")):
            c.setChecked(bool(self.s.get(k, True)))    # .get: a settings file written before
                                                       # this source existed has no such key
            rg.addWidget(c)
        row = QHBoxLayout()
        row.addWidget(QLabel("ALMA-RECALL hits per turn"))
        self.rlimit = QSpinBox()
        self.rlimit.setRange(1, 12)
        self.rlimit.setValue(int(self.s["recall_limit"]))
        row.addWidget(self.rlimit)
        row.addStretch(1)
        rg.addLayout(row)
        n = QLabel("The standing CONTEXT.md block is always loaded and is not a toggle — "
                   "it is the model's baseline knowledge of the fleet and the projects.")
        n.setWordWrap(True)
        n.setProperty("role", "faint")
        rg.addWidget(n)
        rg.addStretch(1)
        tabs.addTab(rw, "Retrieval")

        # --- appearance
        aw = QWidget()
        ag = QGridLayout(aw)
        self.theme = QComboBox()
        self.theme.addItems(["tan", "light", "dark"])
        self.theme.setCurrentText(self.s["theme"])
        self.fs = QSpinBox()
        self.fs.setRange(11, 20)
        self.fs.setValue(int(self.s["font_size"]))
        self.enter = QCheckBox("Enter sends the message (Shift+Enter makes a new line)")
        self.enter.setChecked(bool(self.s["send_on_enter"]))
        ag.addWidget(QLabel("Theme"), 0, 0)
        ag.addWidget(self.theme, 0, 1)
        ag.addWidget(QLabel("Base font size"), 1, 0)
        ag.addWidget(self.fs, 1, 1)
        ag.addWidget(self.enter, 2, 0, 1, 2)
        ag.setRowStretch(3, 1)
        ag.setColumnStretch(1, 1)
        tabs.addTab(aw, "Appearance")

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                              QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(tabs)
        lay.addWidget(bb)

    def values(self) -> dict:
        self.s.update({
            "door": self.door.text().strip(), "model": self.model.text().strip(),
            "temperature": self.temp.value(), "max_tokens": self.maxtok.value(),
            "stream": self.stream.isChecked(), "rag_recall": self.c_recall.isChecked(),
            "rag_standard": self.c_std.isChecked(), "rag_project": self.c_proj.isChecked(),
            "rag_ramchat": self.c_ramchat.isChecked(), "rag_quorum": self.c_quorum.isChecked(),
            "rag_brain2": self.c_brain2.isChecked(),
            "recall_limit": self.rlimit.value(), "theme": self.theme.currentText(),
            "font_size": self.fs.value(), "send_on_enter": self.enter.isChecked(),
        })
        return self.s


class WorkspaceDialog(QDialog):
    """The 'projects' Iddo asked for: a named space with standing instructions the
    model sees every turn, and a root directory that widens the per-turn grep."""

    def __init__(self, workspaces: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Workspaces · " + APP_NAME)
        self.resize(760, 470)
        self.ws = [dict(w) for w in workspaces]
        self._cur = None

        lay = QHBoxLayout(self)
        left = QVBoxLayout()
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._select)
        left.addWidget(self.list, 1)
        brow = QHBoxLayout()
        add = QPushButton("+ New")
        add.clicked.connect(self._add)
        rem = QPushButton("Delete")
        rem.clicked.connect(self._remove)
        brow.addWidget(add)
        brow.addWidget(rem)
        left.addLayout(brow)
        lw = QWidget()
        lw.setLayout(left)
        lw.setFixedWidth(220)
        lay.addWidget(lw)

        right = QGridLayout()
        self.name = QLineEdit()
        self.name.textChanged.connect(self._name_changed)
        self.root = QLineEdit()
        self.root.setPlaceholderText("optional — e.g. D:\\CLAUDE\\eran-brain")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        self.instr = QPlainTextEdit()
        self.instr.setPlaceholderText(
            "Standing instructions for this workspace. Appended to the system prompt on "
            "EVERY turn in this workspace — project facts, conventions, what to never do.")
        right.addWidget(QLabel("Name"), 0, 0)
        right.addWidget(self.name, 0, 1, 1, 2)
        right.addWidget(QLabel("Root folder"), 1, 0)
        right.addWidget(self.root, 1, 1)
        right.addWidget(browse, 1, 2)
        right.addWidget(QLabel("Standing instructions"), 2, 0, Qt.AlignmentFlag.AlignTop)
        right.addWidget(self.instr, 2, 1, 1, 2)
        right.setColumnStretch(1, 1)
        right.setRowStretch(2, 1)
        rw = QWidget()
        rw.setLayout(right)
        lay.addWidget(rw, 1)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save |
                              QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._save_and_accept)
        bb.rejected.connect(self.reject)
        right.addWidget(bb, 3, 0, 1, 3)

        self._reload()
        if self.ws:
            self.list.setCurrentRow(0)

    def _reload(self):
        self.list.blockSignals(True)
        self.list.clear()
        for w in self.ws:
            self.list.addItem(w["name"])
        self.list.blockSignals(False)

    def _flush(self):
        if self._cur is not None and 0 <= self._cur < len(self.ws):
            self.ws[self._cur]["name"] = self.name.text().strip() or self.ws[self._cur]["name"]
            self.ws[self._cur]["root"] = self.root.text().strip()
            self.ws[self._cur]["instructions"] = self.instr.toPlainText()

    def _select(self, row):
        self._flush()
        self._cur = row
        if 0 <= row < len(self.ws):
            w = self.ws[row]
            self.name.setText(w["name"])
            self.root.setText(w.get("root", ""))
            self.instr.setPlainText(w.get("instructions", ""))

    def _name_changed(self, text):
        if self._cur is not None and 0 <= self._cur < self.list.count():
            self.list.item(self._cur).setText(text or "(unnamed)")

    def _add(self):
        base = "Project %d" % (len(self.ws) + 1)
        wid = store.slug(base, "ws").lower() + "-" + os.urandom(2).hex()
        self.ws.append({"id": wid, "name": base, "instructions": "", "root": "",
                        "color": "#c8792f"})
        self._reload()
        self.list.setCurrentRow(len(self.ws) - 1)

    def _remove(self):
        row = self.list.currentRow()
        if row < 0 or len(self.ws) <= 1:
            QMessageBox.information(self, APP_NAME, "At least one workspace must exist.")
            return
        if self.ws[row]["id"] == "general":
            QMessageBox.information(self, APP_NAME, "The General workspace cannot be deleted.")
            return
        self.ws.pop(row)
        self._cur = None
        self._reload()
        self.list.setCurrentRow(0)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Workspace root folder",
                                             self.root.text() or "D:\\CLAUDE")
        if d:
            self.root.setText(os.path.normpath(d))

    def _save_and_accept(self):
        self._flush()
        self.accept()

    def values(self):
        return self.ws


# ---------------------------------------------------------------------------
# 💬 ROOM panel + ⚖️ QUORUM picker (2026-09-15 harnessswarm)
# ---------------------------------------------------------------------------

ROOM_PAID_TIP = ("Claude עולה כסף. הוא עונה רק לשורה שסימנת אותו בשבילה, והסימון יורד "
                 "אחרי השליחה · Claude is paid: he answers only the one line you tick him "
                 "for, and the tick clears after sending.")
ROOM_MUSE_TIP = ("Muse מקבל משימה בתור של RAMCHAT (muse-code) ועונה בחדר מאוחר יותר · "
                 "Muse gets a task on the RAMCHAT queue (muse-code) and answers in the "
                 "room later.")


class RoomPanel(QWidget):
    """The ROOM, docked inside the main window (ONE HARNESS: never a window of its
    own). A live RAMCHAT feed, a composer, and one checkable chip per participant:
    every brain in coder_brains, Claude 💰 and Muse."""
    send_requested = pyqtSignal()

    def __init__(self, theme_fn, current_model="", parent=None):
        super().__init__(parent)
        self.setObjectName("RoomPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumWidth(280)
        self._theme_fn = theme_fn
        self._rows = []
        self._sig = None
        self._loaded = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 10)
        lay.setSpacing(7)

        self.state_lbl = QLabel("RAMCHAT · טוען… · loading", objectName="Hint")
        self.state_lbl.setWordWrap(True)
        lay.addWidget(self.state_lbl)

        self.feed = QTextBrowser(objectName="RoomFeed")
        self.feed.setOpenLinks(False)
        self.feed.setOpenExternalLinks(False)
        lay.addWidget(self.feed, 1)

        lay.addWidget(QLabel("מי עונה · WHO ANSWERS", objectName="SectionLabel"))
        grid = QGridLayout()
        grid.setSpacing(5)
        self.chips = []                      # [(target id, QPushButton)] in answer order
        entries = []
        for b in coder_brains.all_brains():
            name = b.get("human_name") or b.get("label") or b.get("id")
            if b.get("on_demand"):
                name += " ⏳"
            entries.append((b["id"], name, brain_tooltip(b),
                            bool(current_model) and b.get("model") == current_model))
        entries.append(("claude", "Claude 💰", ROOM_PAID_TIP, False))
        entries.append(("muse", "Muse", ROOM_MUSE_TIP, False))
        for i, (tid, text, tip, checked) in enumerate(entries):
            chip = QPushButton(text, objectName="RoomChip")
            chip.setCheckable(True)
            chip.setChecked(checked)
            chip.setToolTip(tip)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            grid.addWidget(chip, i // 2, i % 2)
            self.chips.append((tid, chip))
        lay.addLayout(grid)

        self.input = QPlainTextEdit()
        self.input.setPlaceholderText("כתוב לחדר · write to the room    (Ctrl+Enter)")
        self.input.setFixedHeight(74)
        self.input.installEventFilter(self)
        lay.addWidget(self.input)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.hint = QLabel("", objectName="Hint")
        self.hint.setWordWrap(True)
        row.addWidget(self.hint, 1)
        self.send_btn = QPushButton("שלח לחדר · Send", objectName="Primary")
        self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_btn.clicked.connect(lambda _c=False: self.send_requested.emit())
        row.addWidget(self.send_btn)
        lay.addLayout(row)

    def eventFilter(self, obj, ev):
        try:
            if obj is self.input and ev.type() == QEvent.Type.KeyPress:
                enter = ev.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                ctrl = bool(ev.modifiers() & Qt.KeyboardModifier.ControlModifier)
                if enter and ctrl:
                    self.send_requested.emit()
                    return True
        except Exception as e:
            _brain_log("room input key failed: %s: %s" % (type(e).__name__, e))
        return super().eventFilter(obj, ev)

    def targets(self) -> list:
        return [tid for tid, chip in self.chips if chip.isChecked()]

    def clear_paid(self):
        """MONEY LAW: Claude is chosen per line, so his tick never survives a send."""
        for tid, chip in self.chips:
            if tid == "claude":
                chip.setChecked(False)

    def set_rows(self, rows):
        if rows is None:
            self.state_lbl.setText("RAMCHAT לא עונה · RAMCHAT unreachable — ננסה שוב בעוד 5 שניות")
            return
        self._rows = list(rows)
        first = not self._loaded
        self._loaded = True
        self.state_lbl.setText("RAMCHAT חי · live — %d שורות אחרונות · %s"
                               % (len(self._rows), time.strftime("%H:%M:%S")))
        sig = (len(self._rows), tuple((r.get("ts"), r.get("who"), str(r.get("text") or "")[:80])
                                      for r in self._rows[-3:]))
        if sig == self._sig and not first:
            return
        self._sig = sig
        self.render(force_bottom=first)

    def render(self, force_bottom=False):
        th = (self._theme_fn() if self._theme_fn else None) or {}
        faint = th.get("faint", "#999999")
        if not self._loaded:
            self.feed.setHtml('<p style="color:%s">טוען את החדר… · loading the room…</p>' % faint)
            return
        bar = self.feed.verticalScrollBar()
        at_bottom = force_bottom or bar.value() >= bar.maximum() - 40
        parts = []
        for r in self._rows:
            who = str(r.get("who") or "?")
            text = str(r.get("text") or "")
            if len(text) > 1800:
                text = text[:1800] + " …"
            rtl = is_rtl(text)
            paid = who.startswith("claude@")
            colour = (th.get("accent", "#c8792f") if who == coder_room.IDDO
                      else th.get("warn", "#a8730d") if paid else th.get("text", "#222222"))
            parts.append(
                '<p dir="%s" align="%s" style="margin:0 0 8px 0;">'
                '<span style="color:%s;">%s</span> <b style="color:%s;">%s%s</b><br>%s</p>'
                % ("rtl" if rtl else "ltr", "right" if rtl else "left",
                   faint, _html.escape(str(r.get("ts") or "")),
                   colour, "💰 " if paid else "", _html.escape(who),
                   _html.escape(text).replace("\n", "<br>")))
        self.feed.setHtml("".join(parts) or
                          '<p style="color:%s">(החדר ריק · the room is empty)</p>' % faint)
        if at_bottom:
            QTimer.singleShot(0, lambda: bar.setValue(bar.maximum()) if _alive(bar) else None)


class QuorumDialog(QDialog):
    """The QUORUM picker: the question (prefilled from the composer), the seats that
    QUORUM itself reports UP right now (coder_quorum.seatable), rounds 1-3. A brain
    QUORUM cannot seat is listed greyed with the reason, never silently dropped.
    On-demand brains (the PC's small model) start unticked."""

    def __init__(self, topic, seats, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚖️ קוורום · QUORUM")
        self.setMinimumWidth(540)
        self.seats = dict(seats or {})
        self._boxes = []                     # [(seat id, speaker name, QCheckBox)]
        v = QVBoxLayout(self)
        v.setSpacing(8)

        v.addWidget(QLabel("השאלה לשקלא וטריא · THE QUESTION", objectName="SectionLabel"))
        self.topic = QPlainTextEdit()
        self.topic.setPlainText(topic or "")
        self.topic.setFixedHeight(90)
        v.addWidget(self.topic)

        v.addWidget(QLabel("מושבים · SEATS — רק מה שהקוורום מדווח שהוא למעלה · only seats "
                           "QUORUM reports up", objectName="SectionLabel"))
        if not self.seats:
            warn = QLabel("הקוורום לא ענה על %s/api/models — אי אפשר לפתוח דיון עכשיו.\n"
                          "QUORUM did not answer, so no debate can start right now."
                          % coder_quorum.QUORUM_URL)
            warn.setWordWrap(True)
            warn.setProperty("role", "dim")
            v.addWidget(warn)
        used = set()
        for b in coder_brains.all_brains():
            seat = coder_quorum.map_brain_to_quorum(b.get("model"), self.seats)
            if seat and seat not in used:
                used.add(seat)
                cb = QCheckBox("%s  →  %s" % (brain_display_label(b), seat))
                cb.setChecked(not b.get("on_demand"))
                cb.setToolTip(brain_tooltip(b))
                self._boxes.append((seat, b.get("human_name") or b.get("label") or seat, cb))
                cb.toggled.connect(self._validate)
            else:
                cb = QCheckBox("%s — לא יושב בקוורום עכשיו · not seated now" % b.get("label"))
                cb.setEnabled(False)
            v.addWidget(cb)
        # PC ollama seats follow coder_brains.PC_LOCAL_ALLOWED (True since Iddo
        # amended the PC-models law, 2026-09-15 02:54: on demand, never choking it).
        others = [s for s, up in sorted(self.seats.items())
                  if up and s not in used and "maverick" not in s.lower()
                  and (coder_brains.PC_LOCAL_ALLOWED or not coder_quorum.is_pc_local_seat(s))]
        if others:
            v.addWidget(QLabel("מושבים נוספים שהקוורום מושיב · OTHER LIVE QUORUM SEATS",
                               objectName="SectionLabel"))
            for s in others:
                cb = QCheckBox(s)
                cb.toggled.connect(self._validate)
                self._boxes.append((s, s, cb))
                v.addWidget(cb)

        r = QHBoxLayout()
        r.addWidget(QLabel("סבבים · rounds"))
        self.rounds = QSpinBox()
        self.rounds.setRange(1, 3)
        self.rounds.setValue(2)
        r.addWidget(self.rounds)
        r.addStretch(1)
        v.addLayout(r)

        self.why = QLabel("", objectName="Hint")
        self.why.setWordWrap(True)
        v.addWidget(self.why)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                              | QDialogButtonBox.StandardButton.Cancel)
        self.ok_btn = bb.button(QDialogButtonBox.StandardButton.Ok)
        self.ok_btn.setText("התחל דיון · Start")
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText("ביטול · Cancel")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self.topic.textChanged.connect(self._validate)
        self._validate()

    def selected(self):
        return [(s, n) for s, n, cb in self._boxes if cb.isChecked()]

    def _validate(self, *_):
        try:
            n = len(self.selected())
            topic_ok = bool(self.topic.toPlainText().strip())
            self.ok_btn.setEnabled(topic_ok and n >= 2)
            if not topic_ok:
                self.why.setText("כתוב שאלה · write a question")
            elif n < 2:
                self.why.setText("דיון צריך לפחות שני מושבים (נבחרו %d) · a debate needs at "
                                 "least 2 seats (%d chosen)" % (n, n))
            else:
                self.why.setText("%d מושבים · %d seats" % (n, n))
        except Exception as e:
            _brain_log("quorum dialog validate failed: %s: %s" % (type(e).__name__, e))

    def values(self):
        sel = self.selected()
        return (self.topic.toPlainText().strip(), [s for s, _n in sel],
                int(self.rounds.value()), {s: n for s, n in sel})


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class BrainComboBox(QComboBox):
    """A QComboBox that announces when its popup is about to open, so the window
    can kick off a fresh liveness check right then (Iddo 2026-09-12: the model
    picker must live in the window itself, next to the title -- not the Brain
    menu -- and it must show, honestly, which brains are actually up)."""
    aboutToOpen = pyqtSignal()

    def showPopup(self):
        self.aboutToOpen.emit()
        super().showPopup()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = store.load_settings()
        global ACTIVE_MODEL_SHORT
        ACTIVE_MODEL_SHORT = model_short(self.settings)
        self.workspaces = store.load_workspaces()
        self.index = store.load_index()
        self.theme = THEMES.get(self.settings.get("theme", "tan"), THEMES["light"])
        self.theme["_code_pt"] = max(9, int(self.settings["font_size"]) - 4)
        self.conv_id = None
        self.worker = None
        self.stream_buf = ""
        self.active_card = None
        self.cards = []
        self.ws_filter = "*"
        # Iddo 2026-09-15 00:57 (typeahead law): messages sent while a turn is
        # running queue here instead of being blocked or dropped. Each item is
        # {"id", "text", "widget"} -- widget is the "waiting" bar in the canvas,
        # torn down the moment the item is cancelled or dispatched. Main-thread
        # only: appended from Composer.submitted and popped from _finish_turn,
        # both plain Qt-signal slots, never from a worker thread.
        self._queue = []
        # 2026-09-15 harnessswarm: at most one live QUORUM debate (self._q holds its
        # streaming state) and the ROOM's own send thread. Main-thread-owned refs to
        # parented QThreads only.
        self.quorum_worker = None
        self._q = None
        self.room_worker = None
        # BRAIN SWITCH (Iddo 2026-09-15 10:08): eran4 holds ONE model at a time. The gate
        # (coder_brains.BrainModeGate, no Qt) decides whether a message to the coder may go
        # out yet; ModeWorker wakes the coder off the UI thread. Main-thread-owned only.
        self._mode_gate = coder_brains.BrainModeGate()
        self.mode_worker = None
        self._mode_busy = False
        self._parked_mode_workers = []

        self.setWindowTitle(APP_NAME + " · " + model_label(self.settings))
        self.setWindowIcon(make_icon())
        self.resize(1240, 840)
        self.setMinimumSize(880, 560)

        self._build_menu()      # before _build_ui: it populates self.move_menu
        self._build_ui()
        self._apply_theme()
        self._restore_geometry()
        self._reload_sidebar()

        last = self.index.get("last")
        rows = store.sorted_conversations(self.index)
        self.open_conversation(last if last and store.find_conversation(self.index, last)
                               else (rows[0]["id"] if rows else None))
        self._probe_door()
        self._refresh_brain_liveness()
        self.probe_timer = QTimer(self)
        self.probe_timer.timeout.connect(self._probe_door)
        self.probe_timer.start(120000)
        # Fleet strip: first check shortly after startup (not blocking window
        # paint), then every 3 min -- fleet_inventory.check() walks ~30 doors
        # and is slower than a single door probe.
        QTimer.singleShot(1500, self._refresh_fleet_liveness)
        self.fleet_timer = QTimer(self)
        self.fleet_timer.timeout.connect(self._refresh_fleet_liveness)
        self.fleet_timer.start(180000)
        QTimer.singleShot(800, self._refresh_now_liveness)
        self.now_timer = QTimer(self)
        self.now_timer.timeout.connect(self._refresh_now_liveness)
        self.now_timer.start(60000)
        QTimer.singleShot(1100, self._refresh_muse_liveness)
        self.muse_timer = QTimer(self)
        self.muse_timer.timeout.connect(self._refresh_muse_liveness)
        self.muse_timer.start(120000)
        # 💬 ROOM feed: the RAMCHAT tail every 5 s, polled only while the dock is on screen.
        QTimer.singleShot(900, self._refresh_room)
        self.room_timer = QTimer(self)
        self.room_timer.timeout.connect(self._refresh_room)
        self.room_timer.start(5000)
        try:
            # --shot / app.quit() never reach closeEvent: stop our threads there too.
            QApplication.instance().aboutToQuit.connect(self._stop_threads)
        except Exception as e:
            _brain_log("aboutToQuit hook failed: %s: %s" % (type(e).__name__, e))

    # -- construction ----------------------------------------------------
    def _build_ui(self):
        root = QWidget(objectName="Root")
        self.setCentralWidget(root)
        rl = QHBoxLayout(root)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        rl.addWidget(self.splitter)

        # ---- sidebar
        side = QWidget(objectName="Sidebar")
        sl = QVBoxLayout(side)
        sl.setContentsMargins(12, 12, 8, 10)
        sl.setSpacing(9)

        brand = QHBoxLayout()
        brand.setSpacing(9)
        mark = QLabel()
        mark.setPixmap(make_icon().pixmap(26, 26))
        brand.addWidget(mark)
        bt = QVBoxLayout()
        bt.setSpacing(0)
        bt.addWidget(QLabel(APP_NAME, objectName="Brand"))
        self.brand_sub = QLabel(model_label(self.settings), objectName="BrandSub")
        bt.addWidget(self.brand_sub)
        brand.addLayout(bt)
        brand.addStretch(1)
        sl.addLayout(brand)

        self.new_btn = QPushButton("＋   New conversation", objectName="Primary")
        self.new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.new_btn.clicked.connect(self.new_conversation)
        sl.addWidget(self.new_btn)

        wsrow = QHBoxLayout()
        wsrow.setSpacing(6)
        self.ws_combo = QComboBox()
        self.ws_combo.currentIndexChanged.connect(self._ws_filter_changed)
        wsrow.addWidget(self.ws_combo, 1)
        gear = QToolButton()
        gear.setText("⚙")
        gear.setToolTip("Manage workspaces")
        gear.clicked.connect(self.manage_workspaces)
        wsrow.addWidget(gear)
        sl.addLayout(wsrow)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search conversations…")
        self.search.textChanged.connect(self._reload_sidebar)
        self.search.setClearButtonEnabled(True)
        sl.addWidget(self.search)

        sl.addWidget(QLabel("CONVERSATIONS", objectName="SectionLabel"))
        self.conv_list = QListWidget()
        self.conv_list.setMouseTracking(True)
        self.conv_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.conv_list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.conv_list.itemClicked.connect(
            lambda it: self.open_conversation(it.data(Qt.ItemDataRole.UserRole)["id"]))
        self.conv_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.conv_list.customContextMenuRequested.connect(self._conv_menu)
        self.conv_list.itemDoubleClicked.connect(lambda it: self.rename_conversation())
        sl.addWidget(self.conv_list, 1)

        self.door_lbl = QLabel("checking door…")
        self.door_lbl.setProperty("role", "faint")
        self.door_lbl.setWordWrap(True)
        sl.addWidget(self.door_lbl)
        self.splitter.addWidget(side)

        # ---- main column
        main = QWidget()
        ml = QVBoxLayout(main)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(0)

        top = QWidget(objectName="TopBar")
        tl = QHBoxLayout(top)
        tl.setContentsMargins(22, 12, 16, 12)
        tl.setSpacing(10)
        tt = QVBoxLayout()
        tt.setSpacing(1)
        self.title_lbl = QLabel("—", objectName="ConvTitle")
        self.sub_lbl = QLabel("", objectName="ConvSub")
        tt.addWidget(self.title_lbl)
        tt.addWidget(self.sub_lbl)
        tl.addLayout(tt)

        # Model picker (Iddo 2026-09-12 02:48, "תשנה מיד את ההרנס שאני יכול לבחור
        # מודל כמו פה" -- pick the brain right here, the way a model is picked in
        # this window, not through a menu). One table (BRAINS) drives both this
        # combo box and the Brain menu below; choosing an entry here calls the
        # very same switch_brain() the menu already used, so there is exactly one
        # code path for "change this window's brain in place".
        self.brain_combo = BrainComboBox(objectName="BrainCombo")
        self.brain_combo.setToolTip("בחר מוח לחלון הזה / pick this window's brain")
        self.brain_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToContentsOnFirstShow)
        self.brain_combo.setMinimumWidth(230)
        self._populate_brain_combo()
        self.brain_combo.currentIndexChanged.connect(self._on_brain_combo_changed)
        self.brain_combo.aboutToOpen.connect(self._refresh_brain_liveness)
        tl.addWidget(self.brain_combo)

        # Fleet strip (super-project Phase 4, 2026-09-14): live box/door health
        # from the ONE address source (fleet_inventory.py), never a cached
        # copy. Text only, no state of its own -- must fail visibly (shows
        # "fleet: ?" ) rather than freeze or show stale numbers if the probe
        # itself breaks.
        self.fleet_label = QLabel("fleet: …", objectName="Ghost")
        self.fleet_label.setToolTip("Fleet door health (fleet_inventory.check()) — click to refresh")
        self.fleet_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.fleet_label.mousePressEvent = lambda e: self._refresh_fleet_liveness()
        tl.addWidget(self.fleet_label)

        # Now strip (super-project Phase 4): RAMCHAT's own open-queue count,
        # reusing ramlink.get_queue() -- the "now" tense, separate from the
        # Fleet strip's door health and brain2's durable facts.
        self.now_label = QLabel("now: …", objectName="Ghost")
        self.now_label.setToolTip("RAMCHAT open queue — click to refresh")
        self.now_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.now_label.mousePressEvent = lambda e: self._refresh_now_liveness()
        tl.addWidget(self.now_label)

        self.muse_label = QLabel("muse: …", objectName="Ghost")
        self.muse_label.setToolTip("Muse Door (:8900) — click to refresh")
        self.muse_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.muse_label.mousePressEvent = lambda e: self._refresh_muse_liveness()
        tl.addWidget(self.muse_label)

        self.room_btn = QPushButton("💬 חדר", objectName="Ghost")
        self.room_btn.setToolTip("הצג/הסתר את החדר · show/hide the Room — RAMCHAT live, every "
                                 "brain, Claude 💰, Muse (Ctrl+Shift+R)")
        self.room_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.room_btn.clicked.connect(lambda _c=False: self._toggle_room())
        tl.addWidget(self.room_btn)

        tl.addStretch(1)
        for text, tip, slot in (("Rename", "Rename this conversation", self.rename_conversation),
                                ("Export", "Export to Markdown", self.export_conversation),
                                ("Theme", "Switch light / dark", self.toggle_theme)):
            b = QPushButton(text, objectName="Ghost")
            b.setToolTip(tip)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(slot)
            tl.addWidget(b)
        ml.addWidget(top)

        self.scroll = QScrollArea(objectName="ChatScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.canvas = QWidget(objectName="ChatCanvas")
        self.canvas_l = QVBoxLayout(self.canvas)
        self.canvas_l.setContentsMargins(26, 20, 26, 20)
        self.canvas_l.setSpacing(14)
        self.canvas_l.addStretch(1)
        self.scroll.setWidget(self.canvas)
        ml.addWidget(self.scroll, 1)

        cwrap = QWidget()
        cw = QVBoxLayout(cwrap)
        cw.setContentsMargins(26, 6, 26, 14)
        self.composer = Composer(self.settings)
        self.composer.submitted.connect(self.send_message)
        self.composer.stopped.connect(self.stop_generation)
        self.composer.remember_requested.connect(self.remember_this)
        self.composer.quorum_requested.connect(self.open_quorum)
        cw.addWidget(self.composer)
        ml.addWidget(cwrap)

        self.status = QLabel("", objectName="StatusBar")
        self.status.setContentsMargins(24, 5, 24, 5)
        ml.addWidget(self.status)

        self.splitter.addWidget(main)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([int(self.settings.get("sidebar_width", 288)), 900])
        self._refresh_ws_combo()
        self._build_room_dock()

    def _build_menu(self):
        mb = self.menuBar()
        m = mb.addMenu("&File")
        act = QAction("New conversation", self)
        act.setShortcut(QKeySequence("Ctrl+N"))
        act.triggered.connect(self.new_conversation)
        m.addAction(act)
        a = QAction("Rename conversation…", self)
        a.setShortcut(QKeySequence("F2"))
        a.triggered.connect(self.rename_conversation)
        m.addAction(a)
        a = QAction("Export to Markdown…", self)
        a.setShortcut(QKeySequence("Ctrl+E"))
        a.triggered.connect(self.export_conversation)
        m.addAction(a)
        m.addSeparator()
        a = QAction("Open conversations folder", self)
        a.triggered.connect(lambda: os.startfile(store.CONV_DIR))
        m.addAction(a)
        m.addSeparator()
        a = QAction("Delete conversation (to trash)", self)
        a.triggered.connect(self.delete_conversation)
        m.addAction(a)
        m.addSeparator()
        a = QAction("Quit", self)
        a.setShortcut(QKeySequence("Ctrl+Q"))
        a.triggered.connect(self.close)
        m.addAction(a)

        m = mb.addMenu("&Workspace")
        a = QAction("Manage workspaces…", self)
        a.triggered.connect(self.manage_workspaces)
        m.addAction(a)
        self.move_menu = m.addMenu("Move this conversation to")
        m.addSeparator()
        a = QAction("Pin / unpin", self)
        a.triggered.connect(self.toggle_pin)
        m.addAction(a)

        m = mb.addMenu("&View")
        self.view_menu = m            # the Room dock adds its toggle here (_build_room_dock)
        a = QAction("Toggle light / dark", self)
        a.setShortcut(QKeySequence("Ctrl+D"))
        a.triggered.connect(self.toggle_theme)
        m.addAction(a)
        a = QAction("Bigger text", self)
        a.setShortcut(QKeySequence("Ctrl+="))
        a.triggered.connect(lambda: self._zoom(1))
        m.addAction(a)
        a = QAction("Smaller text", self)
        a.setShortcut(QKeySequence("Ctrl+-"))
        a.triggered.connect(lambda: self._zoom(-1))
        m.addAction(a)
        m.addSeparator()
        a = QAction("Focus the message box", self)
        a.setShortcut(QKeySequence("Ctrl+L"))
        a.triggered.connect(lambda: self.composer.input.setFocus())
        m.addAction(a)
        a = QAction("Search conversations", self)
        a.setShortcut(QKeySequence("Ctrl+F"))
        a.triggered.connect(lambda: self.search.setFocus())
        m.addAction(a)

        # Brain -- one entry per brain; choosing one swaps the door and the model of
        # THIS window (2026-09-12). No second window, no second conversation store.
        m = mb.addMenu("&Brain")
        m.setToolTipsVisible(True)
        self._brain_actions = []
        for b in BRAINS:
            a = QAction(brain_display_label(b), self)
            a.setToolTip(brain_tooltip(b))
            a.setCheckable(True)
            a.setChecked(b["model"] == self.settings.get("model"))
            a.triggered.connect(lambda _checked=False, mdl=b["model"]: self.switch_brain(mdl))
            m.addAction(a)
            self._brain_actions.append((b["model"], a))

        m = mb.addMenu("&Tools")
        a = QAction("Settings…", self)
        a.setShortcut(QKeySequence("Ctrl+,"))
        a.triggered.connect(self.open_settings)
        m.addAction(a)
        a = QAction("Re-check the door now", self)
        a.triggered.connect(self._probe_door)
        m.addAction(a)
        a = QAction("Open the web page (:8875)", self)
        a.triggered.connect(lambda: os.startfile("http://127.0.0.1:8875/"))
        m.addAction(a)
        # Muse Code (Meta) -- Iddo 2026-09-12: "סדר לי מיוז קודר". It is a terminal
        # agent, not a door we can chat through: it asks its own front door for
        # GET /muse-code/models, so it cannot be pointed at the fleet doors and is
        # NOT a Brain. It enters the harness as a TOOL, opened in this conversation's
        # workspace Root folder. One harness -- no window of ours, just the terminal.
        a = QAction("Muse Code (Meta) — open in this project…", self)
        a.triggered.connect(self.open_muse_code)
        m.addAction(a)
        m.addSeparator()
        # ⚖️ QUORUM built in (2026-09-15 harnessswarm) -- same path as the composer button.
        a = QAction("⚖️ קוורום · QUORUM debate…", self)
        a.setShortcut(QKeySequence("Ctrl+Shift+Q"))
        a.triggered.connect(lambda _c=False: self.open_quorum(None))
        m.addAction(a)

        m = mb.addMenu("&Help")
        a = QAction("About " + APP_NAME, self)
        a.triggered.connect(self.about)
        m.addAction(a)

        QShortcut(QKeySequence("Escape"), self, activated=self.stop_generation)

    # -- muse code (Meta's terminal agent, a tool -- not a brain) ---------
    def open_muse_code(self):
        """Open Meta's Muse Code CLI in this conversation's workspace Root folder.

        Muse Code lives in WSL (Ubuntu): Meta's installer has no native Windows
        build. Installed 2026-09-12 to ~/.local/bin/muse, user scope, no admin,
        verified `Muse Code 1.1.1`. The first run needs `muse login` once, in a
        browser, with a Meta account -- that is his to do, not ours. Measured
        2026-09-12: --base-url onto the fleet doors is refused ("Meta bearer
        withheld"), and even pinned it asks for GET /muse-code/models, which is
        Meta's own catalog route and not OpenAI-compatible. So: a tool, here.
        """
        ws = self.current_workspace()
        root = (ws.get("root") or "").strip()
        if not root or not os.path.isdir(root):
            QMessageBox.information(
                self, "Muse Code",
                "This project has no Root folder yet, so there is nowhere to open "
                "Muse Code.\n\nWorkspace → Manage workspaces… → Root folder, "
                "then try again.")
            return
        drive, rest = os.path.splitdrive(os.path.abspath(root))
        linux = ("/mnt/" + drive[0].lower() + rest.replace("\\", "/")) if drive else root
        args = ["wsl.exe", "-d", "Ubuntu", "--cd", linux,
                "--", "bash", "-lc", "$HOME/.local/bin/muse"]
        try:
            subprocess.Popen(["wt.exe"] + args, close_fds=True)
        except (FileNotFoundError, OSError):
            # No Windows Terminal on this box -- plain console instead.
            subprocess.Popen(args, close_fds=True,
                             creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))

    # -- theme -----------------------------------------------------------
    def _apply_theme(self):
        self.theme = THEMES.get(self.settings.get("theme", "tan"), THEMES["light"])
        self.theme["_code_pt"] = max(9, int(self.settings["font_size"]) - 4)
        QApplication.instance().setStyleSheet(
            build_qss(self.theme, int(self.settings["font_size"])))
        self.conv_list.setItemDelegate(ConvDelegate(self.theme, self.conv_list))
        self.conv_list.viewport().update()
        rp = getattr(self, "room_panel", None)
        if rp is not None:
            try:
                rp.render()
            except Exception as e:
                _brain_log("room re-render failed: %s: %s" % (type(e).__name__, e))

    def toggle_theme(self):
        order = ["tan", "light", "dark"]
        cur = self.settings.get("theme", "tan")
        self.settings["theme"] = order[(order.index(cur) + 1) % 3] if cur in order else "tan"
        store.save_settings(self.settings)
        self._apply_theme()
        self.open_conversation(self.conv_id, force=True)

    def _zoom(self, delta):
        self.settings["font_size"] = max(11, min(20, int(self.settings["font_size"]) + delta))
        store.save_settings(self.settings)
        self._apply_theme()
        self.open_conversation(self.conv_id, force=True)

    # -- sidebar ---------------------------------------------------------
    def _refresh_ws_combo(self):
        self.ws_combo.blockSignals(True)
        self.ws_combo.clear()
        self.ws_combo.addItem("All workspaces", "*")
        for w in self.workspaces:
            self.ws_combo.addItem(w["name"], w["id"])
        i = self.ws_combo.findData(self.ws_filter)
        self.ws_combo.setCurrentIndex(max(0, i))
        self.ws_combo.blockSignals(False)
        self.move_menu.clear()
        for w in self.workspaces:
            act = QAction(w["name"], self)
            act.triggered.connect(lambda _c=False, wid=w["id"]: self.move_conversation(wid))
            self.move_menu.addAction(act)

    def _ws_filter_changed(self):
        self.ws_filter = self.ws_combo.currentData() or "*"
        self._reload_sidebar()

    def _reload_sidebar(self):
        names = {w["id"]: w["name"] for w in self.workspaces}
        ws = None if self.ws_filter == "*" else self.ws_filter
        rows = store.sorted_conversations(self.index, ws, self.search.text())
        self.conv_list.blockSignals(True)
        self.conv_list.clear()
        for c in rows:
            it = QListWidgetItem()
            d = dict(c)
            d["ws_name"] = names.get(c.get("workspace", "general"), "")
            it.setData(Qt.ItemDataRole.UserRole, d)
            it.setSizeHint(QSize(200, 52))
            self.conv_list.addItem(it)
            if c["id"] == self.conv_id:
                self.conv_list.setCurrentItem(it)
        self.conv_list.blockSignals(False)

    def _conv_menu(self, pos: QPoint):
        it = self.conv_list.itemAt(pos)
        if not it:
            return
        cid = it.data(Qt.ItemDataRole.UserRole)["id"]
        self.open_conversation(cid)
        m = QMenu(self)
        m.addAction("Rename…", self.rename_conversation)
        m.addAction("Pin / unpin", self.toggle_pin)
        m.addAction("Export to Markdown…", self.export_conversation)
        sub = m.addMenu("Move to workspace")
        for w in self.workspaces:
            sub.addAction(w["name"], lambda wid=w["id"]: self.move_conversation(wid))
        m.addSeparator()
        m.addAction("Delete (to trash)", self.delete_conversation)
        m.exec(self.conv_list.viewport().mapToGlobal(pos))

    # -- conversations ---------------------------------------------------
    def current_workspace(self) -> dict:
        row = store.find_conversation(self.index, self.conv_id) or {}
        return store.workspace_by_id(self.workspaces, row.get("workspace", "general"))

    def new_conversation(self):
        ws = self.ws_filter if self.ws_filter != "*" else "general"
        row = store.new_conversation(self.index, ws)
        self._reload_sidebar()
        self.open_conversation(row["id"])
        self.composer.input.setFocus()

    def rename_conversation(self):
        if not self.conv_id:
            return
        row = store.find_conversation(self.index, self.conv_id)
        text, ok = QInputDialog.getText(self, "Rename conversation", "Name:",
                                        text=row.get("title", ""))
        if ok and text.strip():
            store.rename_conversation(self.index, self.conv_id, text)
            self._reload_sidebar()
            self._refresh_header()

    def toggle_pin(self):
        if self.conv_id:
            store.toggle_pin(self.index, self.conv_id)
            self._reload_sidebar()

    def move_conversation(self, ws_id):
        if self.conv_id:
            store.set_workspace(self.index, self.conv_id, ws_id)
            self._reload_sidebar()
            self._refresh_header()

    def delete_conversation(self):
        if not self.conv_id:
            return
        row = store.find_conversation(self.index, self.conv_id) or {}
        r = QMessageBox.question(
            self, "Delete conversation",
            "Move \"%s\" to conversations\\_trash\\ ?\n\nNothing is erased — the file is "
            "moved, not deleted." % row.get("title", self.conv_id))
        if r != QMessageBox.StandardButton.Yes:
            return
        store.delete_conversation(self.index, self.conv_id)
        self._reload_sidebar()
        rows = store.sorted_conversations(self.index)
        self.open_conversation(rows[0]["id"] if rows else None)

    def export_conversation(self):
        if not self.conv_id:
            return
        row = store.find_conversation(self.index, self.conv_id) or {}
        msgs = store.load_messages(self.conv_id)
        default = os.path.join(os.path.expanduser("~"), "Desktop",
                               store.slug(row.get("title", self.conv_id)) + ".md")
        path, _ = QFileDialog.getSaveFileName(self, "Export conversation", default,
                                              "Markdown (*.md)")
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write(store.export_markdown(self.conv_id, row.get("title", self.conv_id), msgs))
        self.status.setText("Exported to %s" % path)

    def open_conversation(self, conv_id, force=False):
        if conv_id is None:
            self.conv_id = None
            self._clear_canvas()
            self._show_empty()
            self._refresh_header()
            return
        if conv_id == self.conv_id and not force:
            return
        self.conv_id = conv_id
        self.index["last"] = conv_id
        store.save_index(self.index)
        self._clear_canvas()
        msgs = store.load_messages(conv_id)
        if not msgs:
            self._show_empty()
        else:
            last_assistant = None
            last_assistant_msg = None
            for m in msgs:
                who, who_tip = self._who_for(m)
                card = self._add_card(m.get("role", "assistant"), m.get("content", ""),
                                      m.get("ts"), m.get("context"),
                                      m.get("dt"), m.get("tokens"), who=who, who_tip=who_tip)
                if m.get("role") == "assistant":
                    last_assistant = card
                    last_assistant_msg = m
            # A QUORUM transcript is not "one reply": Regenerate would pop every turn of
            # the debate and resend the topic as a plain turn. No ↻ on a debate.
            if last_assistant and not (last_assistant_msg or {}).get("quorum"):
                last_assistant.show_regen(True)
            if msgs[-1].get("role") == "user" and not msgs[-1].get("quorum"):
                # A turn that was written but never answered -- the app was closed or
                # the door died mid-turn. The message is safe on disk (that is the
                # whole point of writing it before calling the model); offer to
                # finish it instead of leaving a dead end. Hit for real 2026-09-09.
                self._add_unanswered_bar(msgs[-1].get("content") or "")
        self._refresh_header()
        self._reload_sidebar()
        QTimer.singleShot(30, self._scroll_bottom)

    def _refresh_header(self):
        row = store.find_conversation(self.index, self.conv_id) or {}
        ws = self.current_workspace()
        self.title_lbl.setText(row.get("title", "No conversation"))
        bits = []
        if row:
            bits.append("%d messages" % row.get("n", 0))
            bits.append("workspace: " + ws.get("name", "General"))
            if ws.get("root"):
                bits.append("root " + ws["root"])
            bits.append("updated " + rel_time(row.get("updated")))
        self.sub_lbl.setText("  ·  ".join(bits) or APP_TAGLINE)

    # -- canvas ----------------------------------------------------------
    def _clear_canvas(self):
        self.cards = []
        self.empty_box = None
        self.unanswered_bar = None
        if getattr(self, "_queue", None):
            # Conversation switched away from under a queue -- its "waiting" bars
            # are about to be torn down by the loop below along with everything
            # else in the canvas, so drop our references to them too rather than
            # risk touching a deleted C++ object later (cancel/dispatch would).
            self._queue = []
            self._update_queue_indicator()
        while self.canvas_l.count() > 1:
            it = self.canvas_l.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

    def _show_empty(self):
        box = QWidget()
        v = QVBoxLayout(box)
        v.setSpacing(10)
        v.addSpacing(50)
        t = QLabel(APP_NAME, objectName="EmptyTitle")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(t)
        s = QLabel(model_short(self.settings) + ", on Iddo's own hardware — grounded every turn in "
                   "ALMA-RECALL, the ALMAWARE standard and the project tree.",
                   objectName="Empty")
        s.setAlignment(Qt.AlignmentFlag.AlignCenter)
        s.setWordWrap(True)
        v.addWidget(s)
        v.addSpacing(14)
        for q in ("מה זה חוק החלונות השבורים, ואיפה הוא כתוב?",
                  "Summarise the Sacred Audio requirements in the ALMAWARE standard",
                  "What is eran4 used for, and what depends on it?",
                  "Write a PowerShell one-liner that lists every listening port with its process"):
            b = QPushButton(q, objectName="Chip")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _c=False, text=q: self._prefill(text))
            v.addWidget(b)
        v.addStretch(1)
        self.canvas_l.insertWidget(self.canvas_l.count() - 1, box)
        self.empty_box = box

    def _add_unanswered_bar(self, user_text):
        box = QFrame(objectName="SysCard")
        h = QHBoxLayout(box)
        h.setContentsMargins(16, 11, 12, 11)
        h.setSpacing(12)
        lbl = QLabel("This message was never answered — the app closed, or the door "
                     "dropped, before the reply came back.")
        lbl.setProperty("role", "dim")
        lbl.setWordWrap(True)
        h.addWidget(lbl, 1)
        b = QPushButton("Answer it now", objectName="Primary")
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(lambda: self.send_message(user_text, _resend=True))
        h.addWidget(b)
        self.canvas_l.insertWidget(self.canvas_l.count() - 1, box)
        self.unanswered_bar = box

    def _drop_unanswered_bar(self):
        box = getattr(self, "unanswered_bar", None)
        if box is not None:
            box.setParent(None)
            box.deleteLater()
            self.unanswered_bar = None

    # -- queued messages (Iddo 2026-09-15 00:57 typeahead law) ------------
    #
    # He wants to type and hit Send while a turn is streaming, without losing
    # focus or waiting. Composer._submit() now ALWAYS emits `submitted`; this
    # is the other half -- send_message() enqueues instead of starting a turn
    # whenever self.worker is not None, and _finish_turn() drains one entry
    # every time a turn ends (success, error, OR Stop -- Stop only cancels the
    # turn in flight, never this list). Everything here runs on the main
    # thread only (Composer's own signal, or a slot on worker.done/failed),
    # so it is safe to touch canvas widgets directly -- no cross-thread calls,
    # per reference_pyqt6_slot_exception_abort every public entry point below
    # still wraps its body in try/except and logs rather than letting a stray
    # exception reach Qt and qFatal the whole app.

    def _enqueue_message(self, text):
        try:
            text = (text or "").strip()
            if not text:
                return
            item = {"id": "q%d-%d" % (int(time.time() * 1000), len(self._queue)),
                    "text": text, "widget": None}
            self._queue.append(item)
            self._add_queue_bar(item)
            self._update_queue_indicator()
        except Exception as e:
            _brain_log("_enqueue_message failed: %s: %s" % (type(e).__name__, e))

    def _add_queue_bar(self, item):
        box = QFrame(objectName="SysCard")
        h = QHBoxLayout(box)
        h.setContentsMargins(16, 11, 12, 11)
        h.setSpacing(10)
        badge = QLabel("⏳ ממתין/ה · יישלח למוח שייבחר באותו רגע — queued, sent to "
                       "whichever brain is picked when it actually goes",
                       objectName="Who")
        badge.setWordWrap(True)
        badge.setStyleSheet("color: %s;" % self.theme["accent"])
        h.addWidget(badge, 1)
        cancel_btn = QToolButton()
        cancel_btn.setText("✕")
        cancel_btn.setToolTip("בטל הודעה ממתינה זו · cancel this queued message")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.clicked.connect(lambda _c=False, mid=item["id"]: self._cancel_queued(mid))
        h.addWidget(cancel_btn)
        outer = QVBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)
        outer.addWidget(box)
        txt = QLabel(item["text"] if len(item["text"]) <= 220 else item["text"][:220] + " …")
        txt.setWordWrap(True)
        txt.setProperty("role", "dim")
        txt.setContentsMargins(4, 0, 4, 0)
        outer.addWidget(txt)
        holder = QWidget()
        holder.setLayout(outer)
        wrap = QHBoxLayout()
        wrap.setContentsMargins(0, 0, 0, 0)
        wrap.addStretch(2)
        wrap.addWidget(holder, 7)
        outer_holder = QWidget()
        outer_holder.setLayout(wrap)
        self.canvas_l.insertWidget(self.canvas_l.count() - 1, outer_holder)
        item["widget"] = outer_holder
        QTimer.singleShot(20, self._scroll_bottom)

    def _cancel_queued(self, item_id):
        try:
            for i, it in enumerate(self._queue):
                if it["id"] == item_id:
                    w = it.get("widget")
                    if w is not None and _alive(w):
                        w.setParent(None)
                        w.deleteLater()
                    del self._queue[i]
                    break
            self._update_queue_indicator()
        except Exception as e:
            _brain_log("_cancel_queued failed: %s: %s" % (type(e).__name__, e))

    def _update_queue_indicator(self):
        try:
            self.composer.set_queue_count(len(self._queue))
        except Exception as e:
            _brain_log("_update_queue_indicator failed: %s: %s" % (type(e).__name__, e))

    def _dispatch_next_queued(self):
        """Called only from _finish_turn, i.e. only once self.worker is None
        again -- so the send_message() call below runs the normal immediate-send
        path, not another enqueue. One queued message per finished turn; if more
        are waiting the next _finish_turn drains the next one, in order."""
        try:
            if not self._queue:
                return
            if self._mode_gate.on_send(self.settings.get("door"), self.settings.get("model")) != "send":
                # BRAIN SWITCH: the coder is not confirmed up -- keep the queue in order, wake it
                self._start_mode_worker(self._current_brain_record())
                return
            item = self._queue.pop(0)
            w = item.get("widget")
            if w is not None and _alive(w):
                w.setParent(None)
                w.deleteLater()
            self._update_queue_indicator()
            self.send_message(item["text"])
        except Exception as e:
            _brain_log("_dispatch_next_queued failed: %s: %s" % (type(e).__name__, e))

    def _prefill(self, text):
        self.composer.input.setPlainText(text)
        self.composer.input.setFocus()

    def _who_for(self, m):
        """(header name, tooltip) for a stored message: the brain that WROTE it."""
        m = m or {}
        if m.get("role") == "user":
            return None, ""
        model = m.get("model") or ""
        if m.get("speaker"):
            return m["speaker"], model
        if model:
            return short_label_for(model), model
        return ("coder", "הודעה ישנה — לא נרשם איזה מוח כתב אותה · an older message: "
                         "the brain that wrote it was not recorded")

    def _add_card(self, role, content, ts=None, ctx=None, dt=None, tokens=None,
                  who=None, who_tip=""):
        if getattr(self, "empty_box", None) is not None:
            self.empty_box.setParent(None)
            self.empty_box.deleteLater()
            self.empty_box = None
        card = MessageCard(role, self.theme, ts, who=who, who_tip=who_tip)
        card.set_content(content or "")
        if role == "assistant":
            if dt is not None:
                card.set_stats("%s tok · %ss" % (tokens if tokens is not None else "?",
                                                 round(float(dt), 1)))
            if ctx is not None:
                card.set_context(ctx)
            card.regenerate.connect(self.regenerate)
        card.delete_turn.connect(lambda c=card: self.delete_turn(c))
        wrap = QHBoxLayout()
        wrap.setContentsMargins(0, 0, 0, 0)
        if role == "user":
            wrap.addStretch(2)
            wrap.addWidget(card, 7)
        else:
            wrap.addWidget(card, 1)
        holder = QWidget()
        holder.setLayout(wrap)
        self.canvas_l.insertWidget(self.canvas_l.count() - 1, holder)
        self.cards.append(card)
        return card

    def _scroll_bottom(self):
        bar = self.scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    # -- sending ---------------------------------------------------------
    def send_message(self, text, _resend=False):
        # A live QUORUM debate is writing into this store too: queue behind it, the
        # same way a message typed during a normal turn queues (typeahead law).
        if self.worker is not None or self._quorum_busy():
            # Iddo 2026-09-15 00:57: never silently drop this (that was the old
            # bug) -- queue it. It goes out the instant _finish_turn sees the
            # queue non-empty, through this same send_message, so it reads
            # self.settings (the brain combo) fresh AT THAT MOMENT.
            self._enqueue_message(text)
            return
        # BRAIN SWITCH: never send to the eran4 coder before eran4 says it is up. The
        # message waits in the same visible queue and goes out the moment it is ready.
        try:
            verdict = self._mode_gate.on_send(self.settings.get("door"), self.settings.get("model"),
                                              resend=_resend)
        except Exception as e:
            _brain_log("brain switch gate failed, sending as before: %s: %s" % (type(e).__name__, e))
            verdict = "send"
        if verdict == "hold-resend":
            self._start_mode_worker(self._current_brain_record())
            self.status.setText(coder_brains.TEXT_LOADING
                                + " — לחץ Regenerate כשהוא מוכן · press Regenerate once it is ready")
            return
        if verdict == "hold":
            self._enqueue_message(text)
            self._start_mode_worker(self._current_brain_record())
            return
        if not self.conv_id:
            self.new_conversation()
        for c in self.cards:
            c.show_regen(False)
        self._drop_unanswered_bar()
        if not _resend:
            store.append_message(self.index, self.conv_id, "user", text)
            self._add_card("user", text, store.now_iso())
        self.composer.clear()
        self._reload_sidebar()
        self._refresh_header()

        self.active_card = self._add_card("assistant", "", store.now_iso(),
                                          who=model_short(self.settings))
        self.active_card.begin_stream()
        self.active_card.set_stats("…")
        self.stream_buf = ""
        self._last_flush = -1
        QTimer.singleShot(20, self._scroll_bottom)

        history = store.load_messages(self.conv_id)[:-1]   # the turn we just wrote is the prompt
        old = getattr(self, "worker", None)
        if old is not None and _qt_alive_and_running(old):
            # a running QThread must outlive its last Python reference (Qt fatal
            # otherwise). Ask it to stop; if it will not, park it until it finishes.
            old.stop()
            if not old.wait(1500):
                self._parked_workers = getattr(self, "_parked_workers", [])
                self._parked_workers.append(old)
                old.finished.connect(lambda w=old: self._parked_workers.remove(w) if w in self._parked_workers else None)
        self.worker = TurnWorker(history, text, self.settings, self.current_workspace(),
                                 self.conv_id, self)
        self.worker.stage.connect(lambda s: self.composer.set_busy(True, s))
        self.worker.ctx_ready.connect(self._on_ctx)
        self.worker.chunk.connect(self._on_chunk)
        self.worker.done.connect(lambda t, u, d, s: self._on_done(text, t, u, d, s))
        self.worker.failed.connect(lambda m, c: self._on_failed(text, m, c))
        self.composer.set_busy(True, "starting…")
        self._pending_ctx = dict(engine.EMPTY_CTX)
        self.worker.start()

        self.stream_timer = QTimer(self)
        self.stream_timer.timeout.connect(self._flush_stream)
        self.stream_timer.start(70)

    def _on_ctx(self, ctx):
        self._pending_ctx = ctx
        self.status.setText(
            "context: %d ALMA-RECALL · %d standard requirements · %d standard sections · "
            "%d project files" % (len(ctx["recall"]), len(ctx["standard_reqs"]),
                                  len(ctx["standard_secs"]), len(ctx["project"])))

    def _on_chunk(self, piece):
        self.stream_buf += piece

    def _flush_stream(self):
        if self.active_card is None or not self.stream_buf:
            return
        if not _alive(self.active_card):
            return                                   # card torn down mid-stream; _on_done re-adds one
        if len(self.stream_buf) == getattr(self, "_last_flush", -1):
            return                                   # nothing new since last tick
        self._last_flush = len(self.stream_buf)
        at_bottom = (self.scroll.verticalScrollBar().value()
                     >= self.scroll.verticalScrollBar().maximum() - 60)
        self.active_card.stream_text(self.stream_buf)
        if at_bottom:
            self._scroll_bottom()

    def _stop_timer(self):
        t = getattr(self, "stream_timer", None)
        if t is not None:
            t.stop()

    def _on_done(self, user_msg, text, usage, dt, streamed):
        self._stop_timer()
        text = text or "(the model returned nothing)"
        card = self.active_card
        ctx = getattr(self, "_pending_ctx", dict(engine.EMPTY_CTX))
        used_model = self._worker_model()
        try:                                     # BRAIN SWITCH: a real answer proves the coder is up
            w_settings = getattr(self.worker, "settings", None) or self.settings
            self._mode_gate.on_turn_done(w_settings.get("door"), used_model)
        except Exception as e:
            _brain_log("brain switch on_turn_done failed: %s: %s" % (type(e).__name__, e))
        if card is not None and not _alive(card):
            # The card died while the model was still talking (see _alive). The
            # answer is still saved below; show it again rather than lose it.
            card = self._add_card("assistant", "", store.now_iso(),
                                  who=short_label_for(used_model) or None)
            self.active_card = card
        if card is not None:
            card.set_content(text)
            card.set_stats("%s tok · %.1fs%s" % (usage.get("completion_tokens", "?"), dt,
                                                 "" if streamed else " · no stream"))
            card.set_context(ctx)
            card.show_regen(True)
        # 2026-09-15 harnessswarm: tag the brain that WROTE this reply -- the worker's
        # own frozen settings copy, not self.settings (the combo may have moved since).
        # Parity with taste.py's append_history(..., extra={"model": brain["model"]}).
        store.append_message(self.index, self.conv_id, "assistant", text,
                             {"context": ctx, "dt": round(dt, 1),
                              "tokens": usage.get("completion_tokens"),
                              "model": used_model})
        store.append_context_receipt(self.conv_id, user_msg, ctx, round(dt, 1))
        self.status.setText(
            "%s · %s prompt tokens, %s completion tokens, %.1fs%s"
            % (used_model or self.settings.get("model", "?"), usage.get("prompt_tokens", "?"),
               usage.get("completion_tokens", "?"), dt,
               "" if streamed else "  (streaming unavailable — used the blocking call)"))
        self._finish_turn()

    def _on_failed(self, user_msg, message, ctx):
        self._stop_timer()
        card = self.active_card
        wake = False
        try:
            # BRAIN SWITCH: eran4's fast 503 "coder asleep" means someone put the coder to
            # sleep under us -- forget "ready" and wake it again below.
            w_settings = getattr(self.worker, "settings", None) or self.settings
            wake = self._mode_gate.on_turn_failed(w_settings.get("door"), self._worker_model(), message)
        except Exception as e:
            _brain_log("brain switch on_turn_failed failed: %s: %s" % (type(e).__name__, e))
        body = ("**The door did not answer.**\n\n```\n%s\n```\n\n"
                "The message above is saved — nothing was lost. Tools → *Re-check the door now*, "
                "or check that vLLM is still up on eran2/3/4." % message)
        if card is not None:
            card.set_content(body)
            card.set_stats("failed")
            card.set_context(ctx)
            card.show_regen(True)
        store.append_message(self.index, self.conv_id, "assistant", body,
                             {"context": ctx, "dt": 0, "tokens": 0, "error": True,
                              "model": self._worker_model()})
        self.status.setText("ERROR: " + message)
        self._finish_turn()
        if wake:
            try:
                if self._mode_gate.needs_switch(self.settings.get("door")):
                    self._start_mode_worker(self._current_brain_record())
                    self.status.setText("הקודר ישן — מעיר אותו; לחץ Regenerate כשהוא מוכן · "
                                        "the coder was asleep — waking it; press Regenerate once it is ready")
            except Exception as e:
                _brain_log("brain switch re-wake failed: %s: %s" % (type(e).__name__, e))

    def _worker_model(self) -> str:
        """The model the running TurnWorker actually uses (its frozen settings copy)."""
        w = getattr(self, "worker", None)
        s = getattr(w, "settings", None) if w is not None else None
        return str((s or self.settings or {}).get("model") or "")

    def _finish_turn(self):
        self.worker = None
        self.active_card = None
        self.stream_buf = ""
        self.composer.set_busy(False, "")
        self._reload_sidebar()
        self._refresh_header()
        QTimer.singleShot(40, self._scroll_bottom)
        self.composer.input.setFocus()
        # Iddo 2026-09-15 00:57: Stop lands here too (worker.stop() still ends in
        # a done/failed signal -> _finish_turn), so stopping the current answer
        # does NOT discard the queue -- the next queued message still goes.
        self._dispatch_next_queued()

    def remember_this(self, text):
        """Memory box (super-project Phase 4): post the composer's current text
        to brain2's /remember as a real proposal -- queued for the maintainer,
        never a private note. Runs the tiny HTTP POST inline (a few hundred ms
        to loopback) rather than spinning up a whole QThread for it."""
        text = (text or "").strip()
        if not text:
            return
        try:
            token = open(r"D:\CLAUDE\alma-brain2\state\token.txt", encoding="utf-8").read().strip()
            body = json.dumps({
                "page": "projects/almaware_coder_remembered",
                "author": "iddo-via-coder",
                "change": text,
                "rationale": "sent via the Memory box in ALMAWARE Coder",
            }).encode("utf-8")
            req = urllib.request.Request(
                "http://127.0.0.1:8897/remember", data=body,
                headers={"Content-Type": "application/json", "X-Brain2-Token": token})
            with urllib.request.urlopen(req, timeout=6) as resp:
                ok = resp.status in (200, 202)
        except Exception as e:
            ok = False
            _brain_log("remember_this failed: %s: %s" % (type(e).__name__, e))
        self.composer.hint.setText("נשלח לזיכרון ✓" if ok else "נכשל לשלוח לזיכרון ✗")
        self.composer.clear()

    def stop_generation(self):
        if self.worker is not None:
            self.worker.stop()
            self.composer.set_busy(True, "stopping…")
        elif self._quorum_busy():
            self.stop_quorum()

    def regenerate(self):
        if self.worker is not None or self._quorum_busy() or not self.conv_id:
            return
        msgs = store.load_messages(self.conv_id)
        while msgs and msgs[-1].get("role") == "assistant":
            msgs.pop()
        if not msgs or msgs[-1].get("role") != "user":
            return
        last_user = msgs[-1].get("content", "")
        store.rewrite_messages(self.conv_id, msgs)
        row = store.find_conversation(self.index, self.conv_id)
        if row:
            row["n"] = len(msgs)
            store.save_index(self.index)
        self.open_conversation(self.conv_id, force=True)
        self.send_message(last_user, _resend=True)

    def delete_turn(self, card):
        if self.worker is not None or self._quorum_busy() or card not in self.cards:
            return
        i = self.cards.index(card)
        msgs = store.load_messages(self.conv_id)
        if i >= len(msgs):
            return
        # a "turn" = this message and, if it is the user's, the reply that followed
        drop = 2 if (msgs[i].get("role") == "user" and i + 1 < len(msgs)
                     and msgs[i + 1].get("role") == "assistant") else 1
        del msgs[i:i + drop]
        store.rewrite_messages(self.conv_id, msgs)
        row = store.find_conversation(self.index, self.conv_id)
        if row:
            row["n"] = len(msgs)
            store.save_index(self.index)
        self.open_conversation(self.conv_id, force=True)

    # -- misc ------------------------------------------------------------
    def _probe_door(self):
        # 2026-09-09 14:09 crash (Event 1000, Qt6Core 0xc0000409): the 120 s timer
        # re-assigned self.probe while the previous DoorProbe was still inside a
        # hung tailnet DNS lookup (urlopen's timeout does not cover getaddrinfo).
        # Dropping the last reference to a running QThread is a Qt fatal. Never
        # replace a running probe; let Qt own the object's death via deleteLater.
        prev = getattr(self, "probe", None)
        if prev is not None and _qt_alive_and_running(prev):
            return
        self.probe = DoorProbe(self.settings["door"], self)
        self.probe.result.connect(self._door_result)
        self.probe.start()

    def _door_result(self, ok, info):
        colour = self.theme["ok"] if ok else self.theme["err"]
        self.door_lbl.setText(("● door up · %s" if ok else "● door DOWN · %s") % info)
        self.door_lbl.setStyleSheet("color: %s; font-size: 11px;" % colour)

    def open_settings(self):
        dlg = SettingsDialog(self.settings, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.settings.update(dlg.values())
            self.composer.settings = self.settings
            store.save_settings(self.settings)
            self._apply_theme()
            self.open_conversation(self.conv_id, force=True)
            self._probe_door()

    def manage_workspaces(self):
        dlg = WorkspaceDialog(self.workspaces, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.workspaces = dlg.values()
            store.save_workspaces(self.workspaces)
            self._refresh_ws_combo()
            self._reload_sidebar()
            self._refresh_header()

    def switch_brain(self, model_id):
        """Swap this window's brain in place: door + model + that brain's token budget.

        The conversation store does not move -- the same conversations, the same
        workspaces, the same history, a different mind reading them. Saving settings
        also moves the tailnet twin on :8875, which reads this file per request, so
        "the same brain and the same conversation store" stays literally true.

        2026-09-12: a turn in flight is no longer a reason to refuse the switch.
        TurnWorker takes its own dict(settings) COPY the moment it is constructed
        (send_message -> TurnWorker(..., self.settings, ...) -> self.settings =
        dict(settings) inside __init__), so the running turn already carries its
        own frozen door/model and cannot be affected by what we write here. Only
        the NEXT send_message() reads self.settings fresh. So: switch immediately,
        save immediately, just say so in Hebrew when a turn is running."""
        try:
            b = next((x for x in BRAINS if x["model"] == model_id), None)
            if b is None:
                return "unknown"
            busy = self.worker is not None
            self.settings["door"] = b["door"]
            self.settings["model"] = b["model"]
            self.settings["max_tokens"] = b["max_tokens"]
            store.save_settings(self.settings)
            global ACTIVE_MODEL_SHORT
            ACTIVE_MODEL_SHORT = model_short(self.settings)
            self.setWindowTitle(APP_NAME + " · " + model_label(self.settings))
            self.brand_sub.setText(model_label(self.settings))
            self._sync_brain_menu()
            self._sync_brain_combo()
            if busy:
                self.status.setText(
                    "המעבר יחול על ההודעה הבאה — הסבב הנוכחי ממשיך עם המוח הקודם")
            else:
                self.status.setText("brain: " + model_label(self.settings))
            self._probe_door()
            self._refresh_brain_liveness()
            self._on_brain_selected(b)
            _brain_log("switched in place to %r (%s)%s" % (
                b["model"], b["door"], " -- turn in flight, applies next turn" if busy else ""))
            return "switched-pending" if busy else "switched"
        except Exception as e:
            _brain_log("switch_brain failed: %s: %s" % (type(e).__name__, e))
            return "error"

    # -- BRAIN SWITCH (Iddo 2026-09-15 10:07-10:08) ---------------------------
    # eran4 holds ONE model: gpt-oss-120b (chat) or the coder. Picking the coder wakes it
    # (ModeWorker, off the UI thread); picking any other brain asks eran4 back to chat on
    # a daemon thread (coder_brains.ensure_brain_mode backgrounds that itself). The
    # decisions live in coder_brains.BrainModeGate (no Qt, tested headless). Every slot
    # here catches: a slot exception is a Qt fatal (reference_pyqt6_slot_exception_abort).

    def _current_brain_record(self) -> dict:
        m = self.settings.get("model")
        b = next((x for x in BRAINS if x["model"] == m), None)
        return dict(b) if b else {"door": self.settings.get("door"), "model": m}

    def _on_brain_selected(self, b):
        try:
            if self._mode_gate.on_select(b) == "wake":
                self._start_mode_worker(b)
                return
            r = coder_brains.ensure_brain_mode(b)       # returns at once; release runs on its own thread
            _brain_log("brain switch: %s for %r" % (r.get("state"), b.get("model")))
            if self._queue and self.worker is None and not self._quorum_busy():
                self._dispatch_next_queued()            # queued lines go to the brain picked now
        except Exception as e:
            _brain_log("brain switch on select failed: %s: %s" % (type(e).__name__, e))

    def _start_mode_worker(self, b):
        """At most one ModeWorker at a time. A worker whose result already arrived but
        whose OS thread is still exiting is parked, never dropped while running (the
        2026-09-09 14:09 Qt-fatal lesson)."""
        try:
            if not b or not self._mode_gate.needs_switch(b.get("door")):
                return
            if self._mode_busy:
                return                                  # the running check reports against the brain picked then
            prev = self.mode_worker
            if prev is not None and _qt_alive_and_running(prev):
                self._parked_mode_workers.append(prev)
                prev.finished.connect(lambda w=prev: self._parked_mode_workers.remove(w)
                                      if w in self._parked_mode_workers else None)
            self._mode_busy = True
            w = ModeWorker(b, self)
            w.status.connect(self._on_mode_status)
            w.result.connect(self._on_mode_result)
            self.mode_worker = w
            self.status.setText("בודק את הקודר על eran4… · checking the coder on eran4…")
            _brain_log("brain switch: waking %r via %s" % (b.get("model"), b.get("door")))
            w.start()
        except Exception as e:
            self._mode_busy = False
            _brain_log("brain switch worker failed to start: %s: %s" % (type(e).__name__, e))

    def _on_mode_status(self, text):
        try:
            if self._mode_gate.needs_switch(self.settings.get("door")):
                self.status.setText(text)
        except Exception as e:
            _brain_log("brain switch status slot failed: %s: %s" % (type(e).__name__, e))

    def _on_mode_result(self, res):
        try:
            self._mode_busy = False
            res = res if isinstance(res, dict) else {}
            door, model = self.settings.get("door"), self.settings.get("model")
            action = self._mode_gate.on_result(door, model, res)
            _brain_log("brain switch result for %r: state=%s ok=%s -> %s (%s)" % (
                res.get("model"), res.get("state"), res.get("ok"), action, res.get("detail") or "-"))
            if action == "dispatch":
                if res.get("model") == model and res.get("text"):
                    self.status.setText(res["text"])
                if res.get("ok") and res.get("model") == model:
                    self._probe_door()
                    self._refresh_brain_liveness()
                if self._queue and self.worker is None and not self._quorum_busy():
                    self._dispatch_next_queued()
            elif action == "retry":
                self._start_mode_worker(self._current_brain_record())
            else:
                note = res.get("text") or "?"
                if self._queue:
                    note += ("  ·  ההודעות בתור מחכות — בחר שוב את הקודר כדי לנסות שוב, או מוח אחר · "
                             "queued messages are waiting — pick the coder again to retry, or pick another brain")
                self.status.setText(note)
        except Exception as e:
            _brain_log("brain switch result slot failed: %s: %s" % (type(e).__name__, e))

    def _sync_brain_menu(self):
        for model_id, a in getattr(self, "_brain_actions", []):
            a.setChecked(model_id == self.settings.get("model"))

    # -- model-picker combo box (top bar) ---------------------------------
    def _populate_brain_combo(self):
        self.brain_combo.blockSignals(True)
        self.brain_combo.clear()
        for b in BRAINS:
            self.brain_combo.addItem(brain_display_label(b), b["model"])
            self.brain_combo.setItemData(self.brain_combo.count() - 1, brain_tooltip(b),
                                         Qt.ItemDataRole.ToolTipRole)
        self.brain_combo.blockSignals(False)
        self._sync_brain_combo()

    def _sync_brain_combo(self):
        if not hasattr(self, "brain_combo"):
            return
        idx = self.brain_combo.findData(self.settings.get("model"))
        if idx < 0:
            return
        if self.brain_combo.currentIndex() != idx:
            self.brain_combo.blockSignals(True)
            self.brain_combo.setCurrentIndex(idx)
            self.brain_combo.blockSignals(False)

    def _on_brain_combo_changed(self, idx):
        """The combo's own slot -- one exception here must never take the window
        down with it (reference_pyqt6_slot_exception_abort)."""
        try:
            if idx < 0:
                return
            model_id = self.brain_combo.itemData(idx)
            if not model_id or model_id == self.settings.get("model"):
                return
            self.switch_brain(model_id)
        except Exception as e:
            _brain_log("brain combo change failed: %s: %s" % (type(e).__name__, e))

    def _refresh_brain_liveness(self):
        """Check every brain's door in a worker thread -- never on the UI thread,
        and a dead door (a 6 s timeout each, engine.door_status) must not freeze
        the window while it is checked. Never replace a still-running probe:
        the same 2026-09-09 14:09 Qt-fatal lesson as _probe_door below."""
        try:
            prev = getattr(self, "brain_probe", None)
            if prev is not None and _qt_alive_and_running(prev):
                return
            doors = sorted({b["door"] for b in BRAINS})
            self.brain_probe = BrainProbe(doors, self)
            self.brain_probe.result.connect(self._on_brain_liveness)
            self.brain_probe.start()
        except Exception as e:
            _brain_log("brain liveness probe failed to start: %s: %s" % (type(e).__name__, e))

    def _on_brain_liveness(self, results):
        try:
            if not hasattr(self, "brain_combo"):
                return
            for i in range(self.brain_combo.count()):
                model_id = self.brain_combo.itemData(i)
                b = next((x for x in BRAINS if x["model"] == model_id), None)
                if b is None:
                    continue
                ok, info = results.get(b["door"], (None, ""))
                if ok is None:
                    continue
                # An on-demand brain (the PC's small model) that is not loaded is not
                # "broken": amber with the reason, never a false red.
                if ok:
                    colour, note = self.theme["ok"], info
                elif b.get("on_demand"):
                    colour = self.theme["warn"]
                    note = "לא טעון עכשיו (לפי דרישה) · not loaded right now (on-demand) — %s" % info
                elif getattr(self, "_mode_gate", None) is not None and self._mode_gate.needs_switch(b["door"]):
                    # BRAIN SWITCH: eran4 holds one model; a sleeping coder is amber, not a false red
                    colour = self.theme["warn"]
                    note = ("ישן או לא זמין — נטען כשבוחרים בו (~דקה) · "
                            "asleep or unavailable — loads when you pick it (~1 min) — %s" % info)
                else:
                    colour, note = self.theme["err"], info
                self.brain_combo.setItemIcon(i, _status_dot(colour))
                self.brain_combo.setItemData(
                    i, "%s\n%s" % (brain_tooltip(b), note), Qt.ItemDataRole.ToolTipRole)
        except Exception as e:
            _brain_log("brain liveness UI update failed: %s: %s" % (type(e).__name__, e))

    def _refresh_fleet_liveness(self):
        """Same never-replace-a-running-probe rule as _refresh_brain_liveness."""
        try:
            prev = getattr(self, "fleet_probe", None)
            if prev is not None and _qt_alive_and_running(prev):
                return
            self.fleet_label.setText("fleet: checking…")
            self.fleet_probe = FleetProbe(self)
            self.fleet_probe.result.connect(self._on_fleet_liveness)
            self.fleet_probe.start()
        except Exception as e:
            _brain_log("fleet liveness probe failed to start: %s: %s" % (type(e).__name__, e))
            self.fleet_label.setText("fleet: ?")

    def _on_fleet_liveness(self, rows):
        try:
            if not rows:
                # Fail visibly (Phase 4 acceptance): never show stale numbers
                # silently if the probe itself broke.
                self.fleet_label.setText("fleet: ? (probe failed)")
                self.fleet_label.setStyleSheet("color:%s" % self.theme["err"])
                return
            live = [r for r in rows if r[1] == "VERIFIED"]
            broken = [r for r in rows if r[1] == "BROKEN"]
            self.fleet_label.setText("fleet: %d/%d up" % (len(live), len(live) + len(broken)))
            colour = self.theme["ok"] if not broken else self.theme["err"]
            self.fleet_label.setStyleSheet("color:%s" % colour)
            if broken:
                names = ", ".join(r[0] for r in broken[:6])
                self.fleet_label.setToolTip("BROKEN: %s" % names)
            else:
                self.fleet_label.setToolTip("all live doors verified")
        except Exception as e:
            _brain_log("fleet liveness UI update failed: %s: %s" % (type(e).__name__, e))

    def _refresh_now_liveness(self):
        try:
            prev = getattr(self, "now_probe", None)
            if prev is not None and _qt_alive_and_running(prev):
                return
            self.now_label.setText("now: checking…")
            self.now_probe = NowProbe(self)
            self.now_probe.result.connect(self._on_now_liveness)
            self.now_probe.start()
        except Exception as e:
            _brain_log("now liveness probe failed to start: %s: %s" % (type(e).__name__, e))
            self.now_label.setText("now: ?")

    def _on_now_liveness(self, open_n):
        try:
            if open_n is None:
                self.now_label.setText("now: ? (RAMCHAT unreachable)")
                self.now_label.setStyleSheet("color:%s" % self.theme["err"])
                return
            self.now_label.setText("now: %d open" % open_n)
            self.now_label.setStyleSheet("")
            self.now_label.setToolTip("RAMCHAT open queue: %d task(s) — click to refresh" % open_n)
        except Exception as e:
            _brain_log("now liveness UI update failed: %s: %s" % (type(e).__name__, e))

    def _refresh_muse_liveness(self):
        try:
            prev = getattr(self, "muse_probe", None)
            if prev is not None and _qt_alive_and_running(prev):
                return
            self.muse_label.setText("muse: checking…")
            self.muse_probe = MuseProbe(self)
            self.muse_probe.result.connect(self._on_muse_liveness)
            self.muse_probe.start()
        except Exception as e:
            _brain_log("muse liveness probe failed to start: %s: %s" % (type(e).__name__, e))
            self.muse_label.setText("muse: ?")

    def _on_muse_liveness(self, ok):
        try:
            self.muse_label.setText("muse: up" if ok else "muse: down")
            self.muse_label.setStyleSheet(
                "color:%s" % (self.theme["ok"] if ok else self.theme["err"]))
        except Exception as e:
            _brain_log("muse liveness UI update failed: %s: %s" % (type(e).__name__, e))

    # -- 💬 ROOM (2026-09-15 harnessswarm) -------------------------------
    def _build_room_dock(self):
        self.room_panel = RoomPanel(lambda: self.theme, self.settings.get("model", ""))
        self.room_panel.send_requested.connect(self._room_send)
        dock = QDockWidget("💬 חדר · Room", self)
        dock.setObjectName("RoomDock")
        # ONE HARNESS: movable left/right and closable, never floatable -- a floating
        # dock is a second top-level window, which the law forbids.
        dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable
                         | QDockWidget.DockWidgetFeature.DockWidgetMovable)
        dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea
                             | Qt.DockWidgetArea.RightDockWidgetArea)
        dock.setWidget(self.room_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        self.room_dock = dock
        try:
            self.resizeDocks([dock], [int(self.settings.get("room_width", 360))],
                             Qt.Orientation.Horizontal)
        except Exception as e:
            _brain_log("room dock resize failed: %s: %s" % (type(e).__name__, e))
        dock.setVisible(bool(self.settings.get("room_visible", True)))
        dock.visibilityChanged.connect(self._on_room_visibility)
        act = dock.toggleViewAction()
        act.setText("💬 חדר · Room panel")
        act.setShortcut(QKeySequence("Ctrl+Shift+R"))
        if getattr(self, "view_menu", None) is not None:
            self.view_menu.addSeparator()
            self.view_menu.addAction(act)

    def _toggle_room(self):
        try:
            self.room_dock.setVisible(self.room_dock.isHidden())
        except Exception as e:
            _brain_log("room toggle failed: %s: %s" % (type(e).__name__, e))

    def _on_room_visibility(self, visible):
        try:
            if visible:
                self._refresh_room()
        except Exception as e:
            _brain_log("room visibility slot failed: %s: %s" % (type(e).__name__, e))

    def _refresh_room(self):
        """Same never-replace-a-running-probe rule as the other strips."""
        try:
            dock = getattr(self, "room_dock", None)
            if dock is None or not dock.isVisible():
                return
            prev = getattr(self, "room_poll", None)
            if prev is not None and _qt_alive_and_running(prev):
                return
            p = RoomPoll(60, self)
            p.result.connect(self._on_room_rows)
            p.finished.connect(p.deleteLater)
            self.room_poll = p
            p.start()
        except Exception as e:
            _brain_log("room poll failed to start: %s: %s" % (type(e).__name__, e))

    def _on_room_rows(self, rows):
        try:
            self.room_panel.set_rows(rows)
        except Exception as e:
            _brain_log("room feed update failed: %s: %s" % (type(e).__name__, e))

    def _room_send(self):
        try:
            panel = self.room_panel
            text = panel.input.toPlainText().strip()
            if not text:
                panel.hint.setText("כתוב משהו קודם · write something first")
                return
            prev = getattr(self, "room_worker", None)
            if prev is not None and _qt_alive_and_running(prev):
                panel.hint.setText("עוד עונים על השורה הקודמת · still answering the previous line")
                return
            targets = panel.targets()
            paid = "claude" in targets
            panel.input.clear()
            panel.clear_paid()          # MONEY LAW: Claude is ticked per line, never sticky
            self._room_pending_text = text
            panel.hint.setText("שולח… · sending%s%s" % (
                (" → " + ", ".join(targets)) if targets else " (בלי מענה · no one addressed)",
                "  💰" if paid else ""))
            w = RoomSendWorker(text, targets, self)
            w.reply.connect(self._on_room_reply)
            w.completed.connect(self._on_room_sent)
            w.finished.connect(w.deleteLater)
            self.room_worker = w
            w.start()
            QTimer.singleShot(500, self._refresh_room)
            if paid:
                _brain_log("room: Claude (paid) explicitly selected by Iddo for one line")
        except Exception as e:
            _brain_log("room send failed to start: %s: %s" % (type(e).__name__, e))

    def _on_room_reply(self, who, reply):
        try:
            bad = str(reply).startswith("[room error]")
            self.room_panel.hint.setText("%s %s %s" % ("✗" if bad else "✓", who,
                                                       "נכשל · failed" if bad else "ענה · answered"))
            self._refresh_room()
        except Exception as e:
            _brain_log("room reply slot failed: %s: %s" % (type(e).__name__, e))

    def _on_room_sent(self, result):
        try:
            panel = self.room_panel
            if isinstance(result, str):
                panel.hint.setText("✗ החדר לא קיבל את השורה · the room refused the line: %s"
                                   % result[:160])
                if not panel.input.toPlainText().strip():
                    panel.input.setPlainText(getattr(self, "_room_pending_text", ""))
            else:
                rows = list(result or [])
                errs = sum(1 for _w, r in rows if str(r).startswith("[room error]"))
                panel.hint.setText("✓ נשלח · sent — %d תשובות · replies%s" % (
                    len(rows), ("  ·  %d שגיאות · errors" % errs) if errs else ""))
            self._refresh_room()
        except Exception as e:
            _brain_log("room sent slot failed: %s: %s" % (type(e).__name__, e))

    # -- ⚖️ QUORUM (2026-09-15 harnessswarm) -----------------------------
    def _quorum_busy(self) -> bool:
        return getattr(self, "quorum_worker", None) is not None

    def open_quorum(self, topic=None):
        """Menu / composer button: check the live seats off the UI thread, then show
        the picker. Nothing reaches QUORUM's /debate until Iddo presses Start."""
        try:
            if self._quorum_busy():
                self.status.setText("⚖️ דיון קוורום כבר רץ — Stop/Esc עוצר · a QUORUM debate "
                                    "is already running")
                return
            prev = getattr(self, "quorum_seat_probe", None)
            if prev is not None and _qt_alive_and_running(prev):
                return
            self._quorum_prefill = (topic if isinstance(topic, str) and topic.strip()
                                    else self.composer.input.toPlainText().strip())
            self.status.setText("⚖️ בודק מי יושב בקוורום… · checking QUORUM seats")
            p = QuorumSeatProbe(self)
            p.result.connect(self._on_quorum_seats)
            p.finished.connect(p.deleteLater)
            self.quorum_seat_probe = p
            p.start()
        except Exception as e:
            _brain_log("open_quorum failed: %s: %s" % (type(e).__name__, e))

    def _on_quorum_seats(self, seats):
        try:
            self._quorum_seats = dict(seats or {})
            up = [s for s, ok in self._quorum_seats.items() if ok]
            self.status.setText(("⚖️ QUORUM: %d מושבים למעלה · %d seats up" % (len(up), len(up)))
                                if self._quorum_seats else
                                "⚖️ הקוורום לא עונה על :8099 · QUORUM is not answering")
            # Let this slot return before a modal dialog spins its own event loop.
            QTimer.singleShot(0, self._show_quorum_dialog)
        except Exception as e:
            _brain_log("quorum seats slot failed: %s: %s" % (type(e).__name__, e))

    def _show_quorum_dialog(self):
        try:
            dlg = QuorumDialog(getattr(self, "_quorum_prefill", ""),
                               getattr(self, "_quorum_seats", {}), self)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            topic, seat_ids, rounds, labels = dlg.values()
            self.start_quorum(topic, seat_ids, rounds, labels)
        except Exception as e:
            _brain_log("quorum dialog failed: %s: %s" % (type(e).__name__, e))

    def start_quorum(self, topic, seat_ids, rounds=2, labels=None):
        """Start a live debate. Every turn streams into THIS conversation as its own
        assistant message tagged {model, speaker, round, quorum}; the closing מסקנה
        is written last. Returns 'started' | 'busy' | 'invalid' | 'error'."""
        try:
            topic = (topic or "").strip()
            seat_ids = [s for s in (seat_ids or []) if s]
            rounds = max(1, min(3, int(rounds or 2)))
            if not topic or len(seat_ids) < 2:
                self.status.setText("⚖️ צריך שאלה ולפחות שני מושבים · need a question and 2+ seats")
                return "invalid"
            if self._quorum_busy():
                return "busy"
            if self.worker is not None:
                self.status.setText("⚖️ סבב רגיל עוד רץ — התחל קוורום כשייגמר · a normal turn "
                                    "is still running; start QUORUM when it ends")
                return "busy"
            if not self.conv_id:
                self.new_conversation()
            conv = self.conv_id
            for c in self.cards:
                c.show_regen(False)
            self._drop_unanswered_bar()
            labels = dict(labels or {})
            head = "⚖️ **קוורום · QUORUM** — %d מושבים · %d סבבים\n%s\n\n%s" % (
                len(seat_ids), rounds, "  ·  ".join(labels.get(s, s) for s in seat_ids), topic)
            store.append_message(self.index, conv, "user", head,
                                 {"quorum": "start", "seats": seat_ids, "rounds": rounds,
                                  "topic": topic})
            self._add_card("user", head, store.now_iso())
            if self.composer.input.toPlainText().strip() == topic:
                self.composer.clear()
            self._q = {"conv": conv, "labels": labels, "cards": {}, "bufs": {}, "meta": {},
                       "saved": set(), "dirty": set(), "errors": [], "notes": {},
                       "debate_id": "", "t0": time.time()}
            w = QuorumWorker(topic, seat_ids, rounds, self)
            w.sse.connect(self._on_quorum_event)
            w.completed.connect(self._on_quorum_done)
            w.finished.connect(w.deleteLater)
            self.quorum_worker = w
            self.composer.set_busy(True, "⚖️ קוורום רץ · QUORUM running — Stop/Esc עוצר")
            self.q_timer = QTimer(self)
            self.q_timer.timeout.connect(self._flush_quorum)
            self.q_timer.start(120)
            w.start()
            self._reload_sidebar()
            self._refresh_header()
            QTimer.singleShot(30, self._scroll_bottom)
            _brain_log("quorum started: seats=%s rounds=%d conv=%s" % (seat_ids, rounds, conv))
            return "started"
        except Exception as e:
            _brain_log("start_quorum failed: %s: %s" % (type(e).__name__, e))
            try:
                self.status.setText("⚖️ הקוורום לא התחיל · QUORUM did not start: %s" % e)
            except Exception:
                pass
            return "error"

    def stop_quorum(self):
        try:
            w = getattr(self, "quorum_worker", None)
            if w is not None and _qt_alive_and_running(w):
                w.stop()
                self.composer.set_busy(True, "⚖️ עוצר את הקוורום… · stopping QUORUM")
        except Exception as e:
            _brain_log("stop_quorum failed: %s: %s" % (type(e).__name__, e))

    def _q_name(self, model):
        q = self._q or {}
        return (q.get("labels") or {}).get(model) or model or "?"

    def _q_meta(self, agent, data):
        """Speaker/model/round for one debate voice; shakla names a turn 'R:model'
        and the closing voice 'synth'."""
        q = self._q
        meta = q["meta"].get(agent)
        if meta is None:
            data = data or {}
            model = data.get("model") or ""
            if agent == "synth":
                rnd = None
                speaker = "⚖️ מסקנה · %s" % self._q_name(model)
            else:
                rnd = data.get("round")
                if rnd is None and ":" in agent and agent.split(":", 1)[0].isdigit():
                    rnd = int(agent.split(":", 1)[0])
                if not model and ":" in agent:
                    model = agent.split(":", 1)[1]
                speaker = "⚖️ %s · %s" % (self._q_name(model),
                                          "עמדות" if rnd == 0 else "סבב %s" % rnd)
            meta = {"model": model, "round": rnd, "speaker": speaker}
            q["meta"][agent] = meta
        elif not meta["model"] and (data or {}).get("model"):
            meta["model"] = data["model"]
        return meta

    def _q_card(self, agent):
        """The live card for one voice -- only while its conversation is on screen."""
        q = self._q
        if q is None or q["conv"] != self.conv_id or agent in q["saved"]:
            return None
        card = q["cards"].get(agent)
        if card is not None and _alive(card):
            return card
        meta = self._q_meta(agent, {})
        card = self._add_card("assistant", "", store.now_iso(),
                              who=meta["speaker"], who_tip=meta["model"])
        card.begin_stream()
        card.set_stats("…")
        if q["bufs"].get(agent):
            card.stream_text(q["bufs"][agent])
        q["cards"][agent] = card
        QTimer.singleShot(20, self._scroll_bottom)
        return card

    def _on_quorum_event(self, name, data):
        try:
            q = self._q
            if q is None:
                return
            data = data if isinstance(data, dict) else {}
            if data.get("debate_id"):
                q["debate_id"] = data["debate_id"]
            agent = str(data.get("agent") or "")
            if name == "plan":
                self.status.setText("⚖️ %d מושבים · %s סבבים · seats / rounds"
                                    % (len(data.get("agents") or []), data.get("rounds", "?")))
            elif name == "status":
                state = data.get("state")
                if agent == "shakla":
                    if state == "round-start":
                        self.status.setText("⚖️ סבב %s · %s" % (data.get("round"),
                                                                data.get("label") or ""))
                elif agent and state == "writing":
                    meta = self._q_meta(agent, data)
                    self._q_card(agent)
                    self.composer.set_busy(True, "⚖️ %s כותב… · writing" % meta["speaker"])
                elif agent and state == "note":
                    note = str(data.get("note") or "")
                    q["notes"].setdefault(agent, []).append(note)
                    card = q["cards"].get(agent)
                    if card is not None and _alive(card):
                        card.set_stats(note[:80])
                elif agent and agent != "synth" and state == "done":
                    self._q_meta(agent, data)
                    self._q_finalize(agent)
            elif name == "delta":
                if not agent:
                    return
                self._q_meta(agent, data)
                q["bufs"][agent] = q["bufs"].get(agent, "") + str(data.get("text") or "")
                q["dirty"].add(agent)
                card = q["cards"].get(agent)
                if card is None or not _alive(card):
                    self._q_card(agent)
            elif name == "error":
                note = str(data.get("note") or data.get("error") or "error")
                # Only a real voice ('R:model' or 'synth') gets a speaker; QUORUM's own
                # errors (agent 'server', 'shakla', none) are debate-level and must never
                # become an empty assistant turn saved into Iddo's conversation.
                is_voice = agent == "synth" or (":" in agent and agent.split(":", 1)[0].isdigit())
                who = (self._q_meta(agent, data)["speaker"] if is_voice
                       else ("QUORUM" if agent in ("", "shakla", "server") else "QUORUM · %s" % agent))
                q["errors"].append("%s: %s" % (who, note))
                self.status.setText("⚖️ %s: %s" % (who, note[:200]))
            elif name == "done":
                q["done"] = data
        except Exception as e:
            _brain_log("quorum event %r failed: %s: %s" % (name, type(e).__name__, e))

    def _flush_quorum(self):
        try:
            q = self._q
            if q is None or not q["dirty"]:
                return
            bar = self.scroll.verticalScrollBar()
            at_bottom = bar.value() >= bar.maximum() - 60
            for agent in list(q["dirty"]):
                card = q["cards"].get(agent)
                if card is not None and _alive(card) and agent not in q["saved"]:
                    card.stream_text(q["bufs"].get(agent, ""))
            q["dirty"].clear()
            if at_bottom:
                self._scroll_bottom()
        except Exception as e:
            _brain_log("quorum flush failed: %s: %s" % (type(e).__name__, e))

    def _q_finalize(self, agent, suffix=""):
        """Write one finished voice to the conversation store, tagged, and render it."""
        q = self._q
        if q is None or agent in q["saved"]:
            return
        q["saved"].add(agent)
        q["dirty"].discard(agent)
        meta = self._q_meta(agent, {})
        text = (q["bufs"].get(agent) or "").strip()
        notes = [n for n in q["notes"].get(agent, []) if n]
        if text:
            body = text + suffix
        else:
            body = "_(לא ענה · no reply%s)_" % ((" — " + "; ".join(notes)[:300]) if notes else "")
        extra = {"model": meta["model"], "speaker": meta["speaker"],
                 "quorum": q.get("debate_id") or "live"}
        if meta.get("round") is not None:
            extra["round"] = meta["round"]
        if not text:
            extra["error"] = True
        store.append_message(self.index, q["conv"], "assistant", body, extra)
        card = q["cards"].get(agent)
        if (card is None or not _alive(card)) and q["conv"] == self.conv_id:
            card = self._add_card("assistant", "", store.now_iso(),
                                  who=meta["speaker"], who_tip=meta["model"])
            q["cards"][agent] = card
        if card is not None and _alive(card):
            card.set_content(body)
            card.set_stats(meta["model"])

    def _on_quorum_done(self, result):
        q = self._q
        try:
            t = getattr(self, "q_timer", None)
            if t is not None:
                t.stop()
            result = result if isinstance(result, dict) else {"error": str(result)}
            if q is not None:
                merged = dict(q.get("done") or {})
                merged.update(result)
                cancelled = (merged.get("error") == "cancelled"
                             or merged.get("note") == "cancelled")
                for agent in list(q["meta"]):
                    if agent != "synth" and agent not in q["saved"]:
                        self._q_finalize(agent, suffix="\n\n_(נעצר באמצע · stopped mid-turn)_")
                synthesis = str(merged.get("synthesis") or "").strip()
                synth_model = (merged.get("synth_model")
                               or (q["meta"].get("synth") or {}).get("model") or "")
                name = self._q_name(synth_model) if synth_model else "QUORUM"
                speaker = "⚖️ מסקנה · %s" % name
                if synthesis:
                    body = "**מסקנה · Conclusion** — %s\n\n%s" % (name, synthesis)
                else:
                    partial = (q["bufs"].get("synth") or "").strip()
                    why = []
                    if cancelled:
                        why.append("נעצר על ידך · stopped by you")
                    for w in ([str(merged["error"])] if merged.get("error") and not cancelled else []) \
                            + ([str(merged["note"])] if merged.get("note") and not cancelled else []) \
                            + q["errors"][-6:]:
                        if w and w not in why:
                            why.append(w)
                    body = "**⚖️ אין מסקנה · no conclusion**\n\n%s%s" % (
                        (partial + "\n\n_(נעצר באמצע · stopped mid-synthesis)_\n\n") if partial else "",
                        "\n".join("- " + w for w in why)
                        or "- הקוורום סגר את הזרם בלי מסקנה · QUORUM closed the stream without one")
                elapsed = merged.get("elapsed")
                if elapsed is None:
                    elapsed = round(time.time() - q["t0"], 1)
                extra = {"model": synth_model or "quorum", "speaker": speaker,
                         "quorum": q.get("debate_id") or "live", "quorum_final": True,
                         "live": bool(merged.get("live")), "elapsed": elapsed}
                if not synthesis:
                    extra["error"] = True
                store.append_message(self.index, q["conv"], "assistant", body, extra)
                q["saved"].add("synth")
                card = q["cards"].get("synth")
                if (card is None or not _alive(card)) and q["conv"] == self.conv_id:
                    card = self._add_card("assistant", "", store.now_iso(),
                                          who=speaker, who_tip=synth_model)
                if card is not None and _alive(card):
                    card.set_content(body)
                    card.set_stats("%s · %ss" % (synth_model or "quorum", elapsed))
                self.status.setText(("⚖️ הקוורום הסתיים · QUORUM finished in %ss" % elapsed)
                                    if synthesis else
                                    ("⚖️ הקוורום נעצר · QUORUM stopped" if cancelled else
                                     "⚖️ הקוורום נגמר בלי מסקנה · QUORUM ended without a conclusion"))
                _brain_log("quorum finished: synthesis=%s cancelled=%s elapsed=%s"
                           % (bool(synthesis), cancelled, elapsed))
        except Exception as e:
            _brain_log("quorum done slot failed: %s: %s" % (type(e).__name__, e))
        finally:
            self._q = None
            self.quorum_worker = None
            try:
                self.composer.set_busy(False, "")
                self._reload_sidebar()
                self._refresh_header()
                QTimer.singleShot(40, self._scroll_bottom)
                self._dispatch_next_queued()
            except Exception as e:
                _brain_log("quorum teardown failed: %s: %s" % (type(e).__name__, e))

    def _register_window(self):
        """Leave this window's hwnd+pid where the Brain menu of a sibling window can
        find it, so choosing an already-open brain focuses it instead of spawning."""
        try:
            qs = QSettings("ALMAWARE", _profile_key(store.PROFILE))
            qs.setValue("hwnd", int(self.winId()))
            qs.setValue("pid", os.getpid())
            qs.sync()
        except Exception as e:
            _brain_log("register failed: %s: %s" % (type(e).__name__, e))

    def about(self):
        QMessageBox.about(
            self, "About " + APP_NAME,
            "<b>%s</b><br>%s<br><br>"
            "A desktop client for Iddo's own models on his fleet.<br><br>"
            "Every turn is grounded in ALMA-RECALL, the ALMAWARE standard and a grep of the "
            "project tree — the retrieval code is shared with the web page on :8875, and so "
            "is <code>conversations\\default.jsonl</code>.<br><br>"
            "Conversations: <code>%s</code><br>"
            "Door: <code>%s</code>" % (APP_NAME, model_label(self.settings), store.CONV_DIR,
                                       self.settings["door"]))

    def _restore_geometry(self):
        qs = QSettings("ALMAWARE", "CoderDesktop" + (("-" + store.PROFILE) if store.PROFILE else ""))
        g = qs.value("geometry")
        idx = _brain_index(store.PROFILE)
        if g is not None:
            self.restoreGeometry(g)
            if idx > 0:
                # a profile window whose saved spot is byte-identical to the main
                # window's would sit exactly on top of it: nudge it once.
                # Compare the saved FRAME rect only (the full 66-byte blobs differ in
                # other fields even on identical pixels), and against EVERY brain listed
                # before this one, not only the main window: measured 2026-09-11,
                # maverick and chat both framed (660,246)-(1899,1115) while main differed.
                fg = _geom_frame(g)
                same = fg is not None and any(
                    _geom_frame(QSettings("ALMAWARE", _profile_key(b["profile"])).value("geometry")) == fg
                    for b in BRAINS[:idx])
                if same:
                    d = BRAIN_OFFSET_PX * idx
                    self.move(self.pos() + QPoint(d, d))
        elif idx > 0:
            # no saved geometry yet: open offset 40 px per profile, not on top
            scr = QGuiApplication.primaryScreen().availableGeometry()
            d = BRAIN_OFFSET_PX * idx
            self.move(scr.x() + max(0, (scr.width() - self.width()) // 2) + d,
                      scr.y() + max(0, (scr.height() - self.height()) // 2) + d)
        s = qs.value("splitter")
        if s is not None:
            self.splitter.restoreState(s)

    def closeEvent(self, e):
        qs = QSettings("ALMAWARE", "CoderDesktop" + (("-" + store.PROFILE) if store.PROFILE else ""))
        qs.setValue("geometry", self.saveGeometry())
        qs.setValue("splitter", self.splitter.saveState())
        sizes = self.splitter.sizes()
        if sizes and sizes[0] > 60:
            self.settings["sidebar_width"] = sizes[0]
        try:
            self.settings["room_visible"] = not self.room_dock.isHidden()
            if self.room_panel.width() > 120:
                self.settings["room_width"] = self.room_panel.width()
        except Exception as ex:
            _brain_log("room state save failed: %s: %s" % (type(ex).__name__, ex))
        store.save_settings(self.settings)
        # Settings are saved above; from here nothing is worth preserving, so a
        # thread that will not stop (a 480B stream can run minutes, a tailnet DNS
        # lookup can hang) is terminated rather than destroyed while running --
        # the latter is the Qt fatal behind the 2026-09-09 14:09 crash.
        self._stop_threads()
        super().closeEvent(e)

    def _stop_threads(self):
        """Stop, wait, and only then terminate every thread this window may own. Used
        by closeEvent and by aboutToQuit (--shot quits without a closeEvent). A thread
        destroyed while running is the Qt fatal of 2026-09-09 14:09."""
        for name, wait_ms in (("worker", 4000), ("probe", 4000), ("quorum_worker", 4000),
                              ("room_worker", 4000), ("room_poll", 2000),
                              ("quorum_seat_probe", 1500), ("brain_probe", 1500),
                              ("fleet_probe", 1500), ("now_probe", 1500), ("muse_probe", 1500),
                              ("mode_worker", 2000)):
            th = getattr(self, name, None)
            try:
                if th is None or not _qt_alive_and_running(th):
                    continue
                if hasattr(th, "stop"):
                    th.stop()
                if not th.wait(wait_ms):
                    th.terminate()
                    th.wait(1000)
            except Exception as ex:
                _brain_log("stopping %s failed: %s: %s" % (name, type(ex).__name__, ex))


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------

def _qt_alive_and_running(th):
    """True only if the QThread's C++ side still exists AND it is running.
    A Python wrapper can outlive its C++ object (after deleteLater / parent
    destruction); touching it then raises RuntimeError -- and an exception that
    escapes a Qt slot makes PyQt6 abort the whole process (the 0xc0000409
    'window closed by itself' of 2026-09-09 14:09 and 14:25)."""
    try:
        return bool(th.isRunning())
    except RuntimeError:
        return False


def _alive(obj) -> bool:
    """True if `obj` is a Qt object whose C++ side still exists.

    2026-09-09 22:44: a reply from the 480B landed in _on_done AFTER its card had
    been torn down (conversation switched / canvas cleared mid-stream). Touching
    the dead card raised 'wrapped C/C++ object of type QVBoxLayout has been
    deleted' -- caught by the excepthook, so the app lived, but the answer was
    never shown and Iddo read it as 'the coder crashed'. Ask sip before touching
    any card that a worker may outlive."""
    if obj is None:
        return False
    try:
        from PyQt6 import sip as _sip
        return not _sip.isdeleted(obj)
    except Exception:
        return True


_INSTANCE_MUTEX = None


def _profile_key(profile: str) -> str:
    return "CoderDesktop" + (("-" + profile) if profile else "")


def _mutex_name(profile: str) -> str:
    return "Local\\ALMAWARE-Coder-Desktop" + (("-" + profile) if profile else "")


def _geom_frame(qba):
    """(x1, y1, x2, y2) of the frame rect inside a QWidget.saveGeometry() blob, or None."""
    if qba is None:
        return None
    try:
        import struct
        b = qba.data() if hasattr(qba, "data") else bytes(qba)
        if len(b) < 24 or struct.unpack(">I", b[:4])[0] != 0x01D9D0CB:
            return None
        return struct.unpack(">iiii", b[8:24])
    except Exception:
        return None


def _brain_index(profile: str) -> int:
    for i, b in enumerate(BRAINS):
        if b["profile"] == profile:
            return i
    return len(BRAINS)


def _brain_log(msg: str) -> None:
    try:
        with open(os.path.join(APP_DIR, "coder_desktop.log"), "a", encoding="utf-8") as f:
            f.write("[%s] brain-menu: %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
    except Exception:
        pass


# REMOVED 2026-09-12: _profile_is_open / _focus_profile_window / _spawn_profile_window
# / open_brain_window. They existed to give every brain its own window -- which gave
# every brain its own conversation store, and cost Iddo the psytrance workspace on the
# night he asked for it ("תוריד פופאפים של חלונות", 00:40). MainWindow.switch_brain
# now swaps the door and the model inside the one window. `--profile=<name>` still
# starts a separate window with its own store if it is ever wanted deliberately.


def _single_instance() -> bool:
    """Windows named mutex: True if this is the only ALMAWARE Coder running.

    2026-09-09 22:59: two real instances were alive at once (a 14:36 console
    diagnostic one and Iddo's), both over one conversation store. (A process
    listing that night also showed "four instances" -- those were the shells of
    the listing command itself, whose command lines contained 'coder_desktop'.
    Measure the parent before believing a count.) One window, or none."""
    global _INSTANCE_MUTEX
    if os.name != "nt":
        return True
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        _INSTANCE_MUTEX = k32.CreateMutexW(None, False, "Local\\ALMAWARE-Coder-Desktop" + (("-" + store.PROFILE) if store.PROFILE else ""))
        return k32.GetLastError() != 183          # ERROR_ALREADY_EXISTS
    except Exception:
        return True


def _install_excepthook():
    """PyQt6 calls qFatal() on any exception that escapes a slot -- the window
    simply vanishes, with only an Event 1000 in Windows to show for it. Log the
    traceback to coder_desktop.log and keep the app alive instead."""
    import traceback as _tb
    log_path = os.path.join(APP_DIR, "coder_desktop.log")

    def hook(exc_type, exc, tb):
        text = "".join(_tb.format_exception(exc_type, exc, tb))
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write("[%s] UNHANDLED in Qt slot -- app kept alive:\n%s\n"
                        % (time.strftime("%Y-%m-%d %H:%M:%S"), text))
        except Exception:
            pass
        try:
            sys.__stderr__.write(text)
        except Exception:
            pass
    sys.excepthook = hook


def main():
    _install_excepthook()
    if not any(a == "--selftest" or a.startswith("--shot=") for a in sys.argv):
        if not _single_instance():
            try:
                with open(os.path.join(APP_DIR, "coder_desktop.log"), "a", encoding="utf-8") as f:
                    f.write("[%s] second instance refused -- one is already running\n"
                            % time.strftime("%Y-%m-%d %H:%M:%S"))
            except Exception:
                pass
            return
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("ALMAWARE")
    app.setFont(QFont(UI_FONT, 10))
    win = MainWindow()
    win.show()
    if not any(a == "--selftest" or a.startswith("--shot=") for a in sys.argv):
        win._register_window()

    if "--selftest" in sys.argv:
        _run_selftest(app, win)
    for a in sys.argv:                      # --shot=PATH: prove what restored, then quit
        if a.startswith("--shot="):
            path = a.split("=", 1)[1]

            def snap():
                win.grab().save(path, "PNG")
                print("[shot] %s · conversation=%s · messages=%d"
                      % (path, win.conv_id, len(win.cards)), flush=True)
                app.quit()
            QTimer.singleShot(2600, snap)
    sys.exit(app.exec())


def _run_selftest(app, win):
    """Real proof, not a claim: open a fresh conversation, send a real message to
    the live door, wait for the real reply, save a PNG of the window, print the
    receipt. `--keep` leaves the app open afterwards."""
    out_png = os.path.join(APP_DIR, "selftest.png")
    prompt = "In two sentences: what is eran1 used for, and what must never run on it? Cite where you got it."
    for a in sys.argv:
        if a.startswith("--png="):
            out_png = a.split("=", 1)[1]
        if a.startswith("--ask="):
            prompt = a.split("=", 1)[1]

    state = {"t0": time.time()}

    def start():
        row = store.new_conversation(win.index, "general", "Selftest %s" % time.strftime("%H:%M:%S"))
        win._reload_sidebar()
        win.open_conversation(row["id"])
        print("[selftest] conversation:", row["id"], flush=True)
        win.send_message(prompt)

    def poll():
        if win.worker is None and state.get("started"):
            msgs = store.load_messages(win.conv_id)
            print("[selftest] messages now: %d" % len(msgs), flush=True)
            for m in msgs:
                print("   %-9s %4d chars  %s" % (m["role"], len(m.get("content") or ""),
                                                 (m.get("content") or "")[:110].replace("\n", " ")),
                      flush=True)
            QTimer.singleShot(900, shot)
            timer.stop()
        elif time.time() - state["t0"] > 420:
            print("[selftest] TIMEOUT", flush=True)
            timer.stop()
            app.quit()

    def shot():
        win.grab().save(out_png, "PNG")
        print("[selftest] screenshot -> %s (%d bytes)"
              % (out_png, os.path.getsize(out_png) if os.path.exists(out_png) else -1), flush=True)
        print("[selftest] conversation file -> %s" % store.conv_path(win.conv_id), flush=True)
        if "--keep" not in sys.argv:
            QTimer.singleShot(300, app.quit)

    timer = QTimer(win)          # parented, so it is not garbage-collected
    win._selftest_timer = timer
    timer.timeout.connect(poll)

    def go():
        start()
        state["started"] = True
        timer.start(700)

    QTimer.singleShot(1200, go)


if __name__ == "__main__":
    main()
