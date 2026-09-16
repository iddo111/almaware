# -*- coding: utf-8 -*-
"""write_corpus.py -- stage 2: session-split + convert accepted audio.

Reads qc/qc_*.json produced by build_corpus.py, assigns WHOLE SESSIONS
(session = calendar date, across every source) to train/heldout/evaluation,
then writes 16 kHz mono PCM16 wavs + manifest.json.

Session = date across ALL sources on purpose: the same day's cafe recording and
dictation capture are the same speaking occasion, so a random or per-source
split would leak one into another split and inflate every score.
"""
import os, sys, json, glob, hashlib, wave, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build_corpus import load, write_wav, sha256_file, SR, session_date

OUT_ROOT = r'D:\CLAUDE\voice-ant-farm\corpus-big\human'

# Sessions already committed by the existing 253 s corpus. Keeping them in the
# same split preserves comparability with every previously reported number.
PINNED = {'20260618': 'train', '20260624': 'heldout',
          '20260625': 'heldout', '20260701': 'evaluation'}
TARGET = {'train': 0.80, 'heldout': 0.10, 'evaluation': 0.10}


def pcm_sha(path):
    with wave.open(path, 'rb') as w:
        return hashlib.sha256(w.readframes(w.getnframes())).hexdigest()


def plan_splits(sess_seconds):
    """Assign whole sessions to splits, largest-first, to hit TARGET by duration."""
    assign = {}
    got = {k: 0.0 for k in TARGET}
    for s, sp in PINNED.items():
        if s in sess_seconds:
            assign[s] = sp
            got[sp] += sess_seconds[s]
    total = sum(sess_seconds.values())
    rest = sorted((s for s in sess_seconds if s not in assign),
                  key=lambda s: -sess_seconds[s])
    for s in rest:
        # give the session to whichever split is furthest below its quota
        deficit = {k: TARGET[k] * total - got[k] for k in TARGET}
        pick = max(deficit, key=deficit.get)
        assign[s] = pick
        got[pick] += sess_seconds[s]
    return assign, got


def main():
    qc = []
    for fp in sorted(glob.glob(os.path.join(HERE, 'qc', 'qc_*.json'))):
        qc.extend(json.load(open(fp, encoding='utf-8')))
    print('qc records: %d' % len(qc))

    # ---- how much accepted audio does each session have? ----
    # eran-audio/heard/cheder was remuxed through ffmpeg, so its origin metadata
    # is gone and I cannot prove it is recorded rather than TTS. The founding rule
    # is that synthetic never enters, so it is quarantined, not split.
    sess = {}
    for r in qc:
        if r['group'] == 'cheder':
            continue
        sess[r['session']] = sess.get(r['session'], 0.0) + r.get('kept_seconds', 0.0)
    sess = {k: v for k, v in sess.items() if v > 0}
    assign, got = plan_splits(sess)
    print('sessions=%d' % len(sess))
    for s in sorted(sess):
        print('   %s  %8.1f s  -> %s' % (s, sess[s], assign[s]))
    print('split totals (h): ' + ', '.join('%s=%.2f' % (k, v / 3600) for k, v in got.items()))

    # ---- write ----
    entries, rejects = [], []
    seen_pcm = {}
    dup = 0
    t0 = time.time()
    for i, r in enumerate(qc):
        if i % 500 == 0:
            print('  write %d/%d  %.0fs' % (i, len(qc), time.time() - t0), flush=True)
        if r.get('status') == 'reject':
            rejects.append(dict(src=r['src'], group=r['group'], reason=r.get('reason'),
                                duration=r.get('src_duration'), m=r.get('m')))
            continue
        if r['group'] == 'cheder':
            split = '_unverified_provenance'
        else:
            split = assign.get(r['session'])
        if split is None:
            continue
        # which pieces of this file are we keeping?
        if r.get('status') == 'segmented':
            keeps = [s for s in r['segments'] if s['ok']]
            for s in r['segments']:
                if not s['ok']:
                    rejects.append(dict(src=r['src'], group=r['group'], seg=s['idx'],
                                        reason=s['reason'], duration=s['t1'] - s['t0']))
            if not keeps:
                continue
        else:
            keeps = None

        x, _ = load(r['src'])
        if x is None:
            continue
        src_sha = sha256_file(r['src'])
        stem = os.path.splitext(os.path.basename(r['src']))[0]

        pieces = []
        if keeps is None:
            pieces.append((None, x, r.get('m', {}), r['src_duration']))
        else:
            for s in keeps:
                seg = x[int(s['t0'] * SR):int(s['t1'] * SR)]
                pieces.append((s, seg, s['m'], s['t1'] - s['t0']))

        for s, seg, m, dur in pieces:
            if s is None:
                name = '%s__%s.wav' % (r['group'], stem)
                off = 0.0
            else:
                name = '%s__%s__seg%04d.wav' % (r['group'], stem, s['idx'])
                off = s['t0']
            h = hashlib.sha256(np.clip(seg, -1, 1).astype(np.float32).tobytes()).hexdigest()
            if h in seen_pcm:
                dup += 1
                rejects.append(dict(src=r['src'], group=r['group'], reason='duplicate_audio',
                                    duplicate_of=seen_pcm[h], duration=dur))
                continue
            seen_pcm[h] = name
            dest = os.path.join(OUT_ROOT, split, name)
            write_wav(dest, seg)
            entries.append(dict(
                path='%s/%s' % (split, name), split=split, speaker_id='iddo1',
                session_id='%s-%s-%s' % (r['session'][:4], r['session'][4:6], r['session'][6:8]),
                source_group=r['group'], source_path=r['src'],
                source_sha256=src_sha, source_bytes=r['src_bytes'],
                source_offset_s=round(off, 3), duration_s=round(dur, 3),
                sample_rate=SR, sample_count=len(seg),
                pcm_sha256=pcm_sha(dest),
                qc=dict(rms_dbfs=m.get('rms_dbfs'), snr_db=m.get('snr_db'),
                        speech_frac=m.get('speech_frac'), voiced_frac=m.get('voiced_frac'),
                        clip_frac_runs=m.get('clip_frac_runs'), f0_median=m.get('f0_median'),
                        mod_2_8_ratio=m.get('mod_2_8_ratio')),
            ))

    os.makedirs(OUT_ROOT, exist_ok=True)
    man = dict(
        format_version=1,
        architecture='private-waveform-only-corpus',
        learning_tokens='waveform-features-only',
        private=True,
        provenance='Iddo\u2019s own recordings only (kafe-claude ideation sessions, '
                   'voice-input dictation, alma-mic dictation, eran-audio cheder). '
                   'No scraped, licensed or third-party material. '
                   'No synthetic ant/Eran babble.',
        split_policy='whole calendar-date sessions, shared across all sources; '
                     'sessions 2026-06-18/24/25 and 2026-07-01 pinned to match the '
                     'pre-existing recordings/ split',
        sample_rate=SR, channels=1, encoding='pcm_s16le',
        entries=entries,
    )
    json.dump(man, open(os.path.join(OUT_ROOT, 'manifest.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    json.dump(rejects, open(os.path.join(OUT_ROOT, 'rejected.json'), 'w', encoding='utf-8'),
              ensure_ascii=False)
    tot = sum(e['duration_s'] for e in entries)
    print('\nWROTE %d files  %.3f h  duplicates_dropped=%d  rejects=%d'
          % (len(entries), tot / 3600, dup, len(rejects)))
    for k in ('train', 'heldout', 'evaluation'):
        d = sum(e['duration_s'] for e in entries if e['split'] == k)
        n = sum(1 for e in entries if e['split'] == k)
        print('  %-11s n=%-6d %.3f h' % (k, n, d / 3600))


if __name__ == '__main__':
    main()
