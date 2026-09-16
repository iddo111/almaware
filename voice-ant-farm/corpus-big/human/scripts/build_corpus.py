# -*- coding: utf-8 -*-
"""build_corpus.py -- gather + QC + convert Iddo's own Hebrew audio.

Output: D:\\CLAUDE\\voice-ant-farm\\corpus-big\\human\\{train,heldout,eval}\\*.wav
        (16 kHz mono PCM16) plus manifest.json / rejected.json.

Nothing in recordings\\ or state\\ is touched.
"""
import os, sys, json, glob, hashlib, wave, struct, subprocess, argparse, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from audioqc import analyze, verdict, segment_speech, SR

OUT_ROOT = r'D:\CLAUDE\voice-ant-farm\corpus-big\human'
FFMPEG = 'ffmpeg'

# ---------------------------------------------------------------- sources
KAFE = r'D:\קפה-קלוד'
VINPUT = r'D:\CLAUDE\voice-input\profiles\iddo1\samples'
ALMAMIC = r'D:\CLAUDE\alma-mic\voice_corpus'
CHEDER = r'D:\CLAUDE\eran-audio\heard\cheder'


def sources():
    """[(group, path, longform)]"""
    S = []
    for p in sorted(glob.glob(os.path.join(KAFE, '*.WAV'))):
        S.append(('kafe', p, True))
    for p in sorted(glob.glob(os.path.join(VINPUT, '*.wav'))):
        S.append(('vinput', p, False))
    for p in sorted(glob.glob(os.path.join(ALMAMIC, '*.wav'))):
        S.append(('almamic', p, False))
    for p in sorted(glob.glob(os.path.join(CHEDER, '*.wav'))):
        S.append(('cheder', p, True))
    return S


def session_date(group, path):
    b = os.path.basename(path)
    digits = ''.join(ch for ch in b if ch.isdigit())
    if group == 'cheder':
        return '20260618'          # captured with the eran-audio heard set
    if len(digits) >= 8 and digits[:4] in ('2025', '2026'):
        return digits[:8]
    return 'unknown'


# ---------------------------------------------------------------- io
def sha256_file(path, buf=1 << 20):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while True:
            b = f.read(buf)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def read_wav_16k_mono(path):
    """Fast path: PCM16 wav already at 16 kHz mono. Returns None if not applicable."""
    try:
        with wave.open(path, 'rb') as w:
            if w.getframerate() != SR or w.getnchannels() != 1 or w.getsampwidth() != 2:
                return None
            raw = w.readframes(w.getnframes())
        return np.frombuffer(raw, dtype='<i2').astype(np.float32) / 32768.0
    except Exception:
        return None


def decode_ffmpeg(path):
    p = subprocess.run([FFMPEG, '-v', 'error', '-nostdin', '-i', path,
                        '-ac', '1', '-ar', str(SR), '-f', 's16le', '-acodec', 'pcm_s16le', '-'],
                       capture_output=True)
    if p.returncode != 0 or not p.stdout:
        return None
    return np.frombuffer(p.stdout, dtype='<i2').astype(np.float32) / 32768.0


def load(path):
    x = read_wav_16k_mono(path)
    if x is not None:
        return x, 'direct'
    return decode_ffmpeg(path), 'ffmpeg'


def write_wav(path, x):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    y = np.clip(x, -1.0, 1.0)
    pcm = (y * 32767.0).astype('<i2')
    with wave.open(path, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def content_hash(x):
    return hashlib.sha256(np.clip(x, -1, 1).astype(np.float32).tobytes()).hexdigest()


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--stage', default='analyze')     # analyze | write
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--groups', default='')
    ap.add_argument('--out', default=os.path.join(HERE, 'qc'))
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    S = sources()
    if args.groups:
        want = set(args.groups.split(','))
        S = [s for s in S if s[0] in want]
    if args.limit:
        S = S[:args.limit]

    recs = []
    t0 = time.time()
    for i, (group, path, longform) in enumerate(S):
        if i % 250 == 0:
            print('  [%s] %d/%d  %.0fs' % (group, i, len(S), time.time() - t0), flush=True)
        try:
            st = os.stat(path)
        except OSError:
            continue
        base = dict(group=group, src=path, src_bytes=st.st_size,
                    session=session_date(group, path))
        x, how = load(path)
        if x is None or len(x) == 0:
            base.update(status='reject', reason='decode_failed')
            recs.append(base); continue
        base['decode'] = how
        base['src_duration'] = len(x) / float(SR)
        # duration decides, not just the group: alma-mic has 898 s outliers that
        # must be segmented too, and framing those whole would blow memory.
        if base['src_duration'] > 45.0:
            longform = True

        if longform:
            spans = segment_speech(x)
            base['n_spans'] = len(spans)
            kept = []
            for si, (a, b) in enumerate(spans):
                seg = x[int(a * SR):int(b * SR)]
                m = analyze(seg)
                ok, why = verdict(m)
                kept.append(dict(idx=si, t0=round(a, 3), t1=round(b, 3),
                                 ok=ok, reason=why, m={k: round(float(v), 5) for k, v in m.items()}))
            base['segments'] = kept
            base['status'] = 'segmented'
            base['kept_seconds'] = sum(s['t1'] - s['t0'] for s in kept if s['ok'])
        else:
            m = analyze(x)
            ok, why = verdict(m)
            base['m'] = {k: round(float(v), 5) for k, v in m.items()}
            base['status'] = 'accept' if ok else 'reject'
            base['reason'] = why
            base['kept_seconds'] = base['src_duration'] if ok else 0.0
        recs.append(base)

    tag = args.groups.replace(',', '_') or 'all'
    fp = os.path.join(args.out, 'qc_%s.json' % tag)
    json.dump(recs, open(fp, 'w', encoding='utf-8'), ensure_ascii=False)
    tot_src = sum(r.get('src_duration', 0) for r in recs)
    tot_keep = sum(r.get('kept_seconds', 0) for r in recs)
    print('WROTE %s  n=%d  src_h=%.3f  keep_h=%.3f  (%.0fs)' %
          (fp, len(recs), tot_src / 3600, tot_keep / 3600, time.time() - t0))


if __name__ == '__main__':
    main()
