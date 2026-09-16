# -*- coding: utf-8 -*-
"""Normalise Sefaria JSON -> plain consonantal Hebrew.

Strips: HTML tags, Sefaria footnotes, nikkud (U+0591-U+05C7), maqaf, sof pasuq,
punctuation, Latin, digits. Keeps: the 22 Hebrew letters. Final forms are folded
to their base letter (ך->כ etc.) because a Torah scroll makes no such distinction
and the expansion hypothesis is about letters, not graphemes.
"""
import io, json, os, re, sys, unicodedata

BASE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(BASE, 'raw')
CLEAN = os.path.join(BASE, 'clean')
os.makedirs(CLEAN, exist_ok=True)

FINALS = {'ך': 'כ', 'ם': 'מ', 'ן': 'נ',
          'ף': 'פ', 'ץ': 'צ'}
LETTERS = set('אבגדהוזחטי'
              'כלמנסעפצקר'
              'שת') | set(FINALS)

TAG = re.compile(r'<[^>]*>')
FOOTNOTE = re.compile(r'<i class="footnote".*?</i>', re.S)
# MAM embeds scribal section markers {פ} {ס} {ר} {ש} and poetic-layout marks.
# These are page furniture, NOT text: they must go or they inflate letter counts.
BRACED = re.compile(r'\{[^}]{0,12}\}')
SQBRACK = re.compile(r'\[[^\]]{0,40}\]')   # editorial insertions in Chasidut texts
# nikkud, te'amim, and the Hebrew punctuation block
DIACRITIC = re.compile('[֑-ׇֽֿׁׂׅׄ]')
HEBPUNCT = re.compile('[־׀׃׆׳״]')


def strip_markup(s, drop_brackets=True):
    s = FOOTNOTE.sub(' ', s)
    s = TAG.sub(' ', s)
    s = s.replace('&nbsp;', ' ').replace('&amp;', '&')
    s = s.replace('&thinsp;', ' ').replace('&quot;', '"')
    s = BRACED.sub(' ', s)
    if drop_brackets:
        s = SQBRACK.sub(' ', s)
    return s


def to_consonantal(s, fold_finals=True):
    """Return the letter-only string (no spaces)."""
    s = strip_markup(s)
    s = unicodedata.normalize('NFD', s)
    s = DIACRITIC.sub('', s)
    s = HEBPUNCT.sub(' ', s)
    out = []
    for ch in s:
        if ch in LETTERS:
            out.append(FINALS.get(ch, ch) if fold_finals else ch)
    return ''.join(out)


def to_words(s, fold_finals=True):
    """Return list of consonantal words, preserving word boundaries."""
    s = strip_markup(s)
    s = unicodedata.normalize('NFD', s)
    s = DIACRITIC.sub('', s)
    s = HEBPUNCT.sub(' ', s)
    words = []
    cur = []
    for ch in s:
        if ch in LETTERS:
            cur.append(FINALS.get(ch, ch) if fold_finals else ch)
        else:
            if cur:
                words.append(''.join(cur))
                cur = []
    if cur:
        words.append(''.join(cur))
    return words


def flatten(x, out):
    if isinstance(x, str):
        if x.strip():
            out.append(x)
    elif isinstance(x, list):
        for y in x:
            flatten(y, out)
    elif isinstance(x, dict):
        for k in sorted(x.keys()):
            flatten(x[k], out)


def process(path):
    d = json.load(io.open(path, encoding='utf-8'))
    segs = []
    flatten(d.get('text'), segs)
    letters = ''.join(to_consonantal(s) for s in segs)
    words = []
    for s in segs:
        words.extend(to_words(s))
    return d, segs, letters, words


if __name__ == '__main__':
    rows = []
    for fn in sorted(os.listdir(RAW)):
        if not fn.endswith('.json'):
            continue
        name = fn[:-5]
        if name.startswith('mam_'):
            continue  # vocalised cross-check, handled separately
        d, segs, letters, words = process(os.path.join(RAW, fn))
        io.open(os.path.join(CLEAN, name + '.letters.txt'), 'w',
                encoding='utf-8').write(letters)
        io.open(os.path.join(CLEAN, name + '.words.txt'), 'w',
                encoding='utf-8').write(' '.join(words))
        io.open(os.path.join(CLEAN, name + '.segments.txt'), 'w',
                encoding='utf-8').write(
                    '\n'.join(' '.join(to_words(s)) for s in segs))
        rows.append((name, len(segs), len(words), len(letters)))
        print('%-34s segs=%6d words=%8d letters=%9d' %
              (name, len(segs), len(words), len(letters)))
    io.open(os.path.join(BASE, 'sizes.tsv'), 'w', encoding='utf-8').write(
        'name\tsegments\twords\tletters\n' +
        '\n'.join('%s\t%d\t%d\t%d' % r for r in rows) + '\n')
