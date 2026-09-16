# -*- coding: utf-8 -*-
"""Download Hebrew translations of foreign works from Project Ben-Yehuda.

These are THE critical control: McKay, Bar-Natan, Bar-Hillel & Kalai (1999)
refuted Witztum-Rips-Rosenberg by finding equivalent 'codes' in a Hebrew
translation of War and Peace. We obtain that exact text, plus two more.

All texts are public domain. Project Ben-Yehuda explicitly licenses reuse.
robots.txt asks Crawl-delay: 10 -- honoured below.
"""
import io, os, time, urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(BASE, 'raw')
os.makedirs(RAW, exist_ok=True)
UA = {'User-Agent': 'alma-research/1.0 (academic text analysis; iddo111@gmail.com)'}

WORKS = [
    # (ben-yehuda id, our filename, description)
    (3210,  'ctrl_trans_WarPeace_v1', "War and Peace vol 1 (Tolstoy, tr. Y.E. Trivush, from Russian)"),
    (66738, 'ctrl_trans_WarPeace_v2', "War and Peace vol 2"),
    (66739, 'ctrl_trans_WarPeace_v3', "War and Peace vol 3"),
    (66740, 'ctrl_trans_WarPeace_v4', "War and Peace vol 4"),
    (3185,  'ctrl_trans_WarPeace_ep', "War and Peace epilogues (tr. A. Levinson)"),
    (5466,  'ctrl_trans_AnnaKarenina', "Anna Karenina (Tolstoy, tr. Y.E. Trivush)"),
    (380,   'ctrl_trans_CrimePunish', "Crime and Punishment (Dostoevsky, tr. Y.H. Brenner)"),
]


def get(wid, name, desc):
    dst = os.path.join(RAW, name + '.txt')
    if os.path.exists(dst) and os.path.getsize(dst) > 1000:
        print('  cached %-26s %9d bytes' % (name, os.path.getsize(dst)))
        return
    u = 'https://benyehuda.org/download/%d.txt' % wid
    for i in range(4):
        try:
            req = urllib.request.Request(u, headers=UA)
            with urllib.request.urlopen(req, timeout=180) as f:
                b = f.read()
            io.open(dst, 'wb').write(b)
            print('  got    %-26s %9d bytes  %s' % (name, len(b), desc))
            return
        except Exception as e:
            print('   retry', type(e).__name__, str(e)[:60])
            time.sleep(5 * (i + 1))
    print('  FAIL', name)


if __name__ == '__main__':
    for wid, name, desc in WORKS:
        get(wid, name, desc)
        time.sleep(10)   # robots.txt Crawl-delay
