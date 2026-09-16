# -*- coding: utf-8 -*-
"""Fetch complex-schema texts via Sefaria's merged-version download endpoint."""
import io, json, os, sys, time, urllib.parse, urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(BASE, 'raw')
os.makedirs(RAW, exist_ok=True)
UA = {'User-Agent': 'alma-research/1.0 (structural-analysis)'}


def download_merged(title, outname):
    dst = os.path.join(RAW, outname + '.json')
    if os.path.exists(dst):
        print('  cached', outname)
        return json.load(io.open(dst, encoding='utf-8'))
    u = 'https://www.sefaria.org/download/version/' + \
        urllib.parse.quote(title + ' - he - merged') + '.json'
    last = None
    for i in range(4):
        try:
            req = urllib.request.Request(u, headers=UA)
            with urllib.request.urlopen(req, timeout=180) as f:
                d = json.loads(f.read().decode('utf-8'))
            json.dump(d, io.open(dst, 'w', encoding='utf-8'), ensure_ascii=False)
            segs = []
            flatten(d.get('text'), segs)
            print('  got %-30s segs=%6d  license=%s  title=%s' %
                  (outname, len(segs), d.get('license'), str(d.get('versionTitle'))[:30]))
            return d
        except Exception as e:
            last = e
            time.sleep(2 * (i + 1))
    print('  FAIL', title, type(last).__name__, str(last)[:120])
    return None


def flatten(x, out):
    if isinstance(x, str):
        if x.strip():
            out.append(x)
    elif isinstance(x, list):
        for y in x:
            flatten(y, out)
    elif isinstance(x, dict):
        for k in x:
            flatten(x[k], out)


JOBS = [
    # (Sefaria title, our name, role)
    ('Likutei Moharan',            'target_Likutei_Moharan',    'target'),
    ('Sippurei Maasiyot',          'target_Sippurei_Maasiyot',  'target'),
    # --- controls ---
    ('Mishnah Berakhot',           'ctrl_mishnah_probe',        'control'),
    ('Mishneh Torah, Repentance',  'ctrl_rambam_probe',         'control'),
    ('Guide for the Perplexed',    'ctrl_moreh',                'control'),
    ('Kuzari',                     'ctrl_kuzari',               'control'),
]

if __name__ == '__main__':
    only = sys.argv[1] if len(sys.argv) > 1 else None
    for title, name, role in JOBS:
        if only and only not in role:
            continue
        download_merged(title, name)
