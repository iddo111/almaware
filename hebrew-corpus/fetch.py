# -*- coding: utf-8 -*-
"""Fetch machine-readable Hebrew texts from Sefaria (public API).
CPU only. No GPU. Writes raw JSON to raw/ and never overwrites silently."""
import io, json, os, sys, time, urllib.parse, urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
RAW  = os.path.join(BASE, 'raw')
os.makedirs(RAW, exist_ok=True)

UA = {'User-Agent': 'alma-research/1.0 (structural-analysis; contact iddo111@gmail.com)'}

def api(path, tries=4):
    url = 'https://www.sefaria.org/api/' + path
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.loads(r.read().decode('utf-8'))
        except Exception as e:
            last = e
            time.sleep(1.5 * (i + 1))
    raise last

def index(title):
    return api('v2/index/' + urllib.parse.quote(title))

def text(ref, version=None):
    p = 'v3/texts/' + urllib.parse.quote(ref)
    if version:
        p += '?version=' + urllib.parse.quote('hebrew|' + version)
    else:
        p += '?version=hebrew'
    return api(p)

def flatten(x, out):
    """Sefaria returns arbitrarily nested lists of strings."""
    if isinstance(x, str):
        if x.strip():
            out.append(x)
    elif isinstance(x, list):
        for y in x:
            flatten(y, out)

def fetch_book(ref, version, outname):
    """Fetch a whole book in one v3 call; fall back to per-section if too big."""
    dst = os.path.join(RAW, outname + '.json')
    if os.path.exists(dst):
        print('  cached', outname)
        return json.load(io.open(dst, encoding='utf-8'))
    d = text(ref, version)
    vs = d.get('versions') or []
    if not vs:
        raise RuntimeError('no hebrew version for ' + ref)
    v = vs[0]
    rec = {
        'ref': ref,
        'versionTitle': v.get('versionTitle'),
        'license': v.get('license'),
        'versionSource': v.get('versionSource'),
        'heTitle': d.get('heTitle'),
        'text': v.get('text'),
    }
    json.dump(rec, io.open(dst, 'w', encoding='utf-8'), ensure_ascii=False)
    segs = []
    flatten(rec['text'], segs)
    print('  got %-28s %-34s segs=%6d  license=%s' %
          (outname, (rec['versionTitle'] or '')[:34], len(segs), rec['license']))
    return rec


TORAH = ['Genesis', 'Exodus', 'Leviticus', 'Numbers', 'Deuteronomy']
TARGETS_TANAKH = TORAH + ['Psalms', 'Song of Songs']

# --- controls: other biblical books, NOT under test ---
CTRL_TANAKH = ['Isaiah', 'Jeremiah', 'Ezekiel', 'Job', 'Proverbs',
               'Ecclesiastes', 'I Samuel', 'II Samuel', 'I Kings', 'II Kings',
               'I Chronicles', 'II Chronicles', 'Joshua', 'Judges',
               'Lamentations', 'Ruth', 'Esther', 'Daniel', 'Nehemiah', 'Ezra']

if __name__ == '__main__':
    which = sys.argv[1] if len(sys.argv) > 1 else 'all'
    if which in ('all', 'tanakh'):
        print('== TARGET: Tanakh consonantal (Tanach with Text Only, Public Domain)')
        for b in TARGETS_TANAKH:
            fetch_book(b, 'Tanach with Text Only', 'target_' + b.replace(' ', '_'))
        print('== TARGET: Tanakh vocalised cross-check (Miqra according to the Masorah)')
        for b in TARGETS_TANAKH:
            fetch_book(b, 'Miqra according to the Masorah', 'mam_' + b.replace(' ', '_'))
    if which in ('all', 'breslov'):
        print('== TARGET: Breslov')
        for t in ['Likutei Moharan', 'Likutei Moharan Part II', 'Sippurei Maasiyot']:
            try:
                fetch_book(t, None, 'target_' + t.replace(' ', '_'))
            except Exception as e:
                print('  FAIL', t, type(e).__name__, str(e)[:120])
    if which in ('all', 'ctrl'):
        print('== CONTROL: other Tanakh books (consonantal, same register+era)')
        for b in CTRL_TANAKH:
            try:
                fetch_book(b, 'Tanach with Text Only', 'ctrl_bib_' + b.replace(' ', '_'))
            except Exception as e:
                print('  FAIL', b, type(e).__name__, str(e)[:120])
