#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Per-syllable AUC + per-syllable permutation p for the leading candidates."""
import json, os, collections
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
D = json.load(open(os.path.join(HERE, 'feats.json'), encoding='utf-8'))
from split import pack, score, auc_p  # noqa

STRATA = [('station', 'ma'), ('station', 'ba'), ('station', 'ah'),
          ('sitting-20260901', 'ba'), ('station', 'ih')]
SHOW = ['f1_traj_hz', 'f2_traj_hz', 'spec_flux', 'burst_rise_hf_db', 'burst_rise_db',
        'vot_ms', 'voice_onset_s', 'tilt_db_oct', 'hf_lf_db', 'centroid_hz',
        'f0_med', 'f0_range_st', 'f0_slope_st_s', 'f0_jitter',
        'periodicity', 'hnr_db', 'voiced_frac', 'dur_active', 'mod_ratio',
        'noisefloor_rel_db', 'snr_db', 'crest_db', 'rms_db',
        'wdist', 'p_judge']
K = lambda d: (d['source'], d['unit'])


def main():
    print('PER-SYLLABLE AUC vs IDDO  (AUC>0.5 = the measure agrees with him)')
    print('permutation p per cell, 10000 shuffles of his labels inside that syllable\n')
    hdr = '%-19s' % 'measure'
    for s, u in STRATA:
        hdr += '%16s' % ('%s/%s n=%d' % (s[:3], u, sum(1 for d in D if (d['source'], d['unit']) == (s, u))))
    print(hdr)
    for f in SHOW:
        line = '%-19s' % f
        for k in STRATA:
            rows = [d for d in D if (d['source'], d['unit']) == k]
            pk = pack(rows, K, f)
            if not pk:
                line += '%16s' % '-'
                continue
            a, p, n, sd = auc_p(pk, nperm=10000)
            if not np.isfinite(a):
                line += '%16s' % '-'
            else:
                star = '***' if p < .001 else '**' if p < .01 else '*' if p < .05 else ''
                line += '%16s' % ('%.2f p%.3f%s' % (a, p, star))
        print(line)
    print('\n(ih n=5 has only 4 orderable pairs - it is decoration, not evidence)')
    print('wdist is shown in RANKING convention (higher wdist).  The search keeps LOW')
    print('wdist, so its agreement with Iddo is 1-AUC in every cell above.')


if __name__ == '__main__':
    main()
