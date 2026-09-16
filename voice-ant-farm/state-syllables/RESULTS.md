# Do the ants know the syllables?

Held-out audio only: 132 syllable tokens from vocoder renderings that appear in no training split, encoded into unit strings by codebooks that were fitted on 396 other tokens. Chance is 4.5% over 22 classes. Quantisation error is not reported.

## Verdict

**Partly - and the part that works is not the part that was trained.**

They discriminate: `512/ant-b` reaches 44.7% top-1 (80.3% top-5) on 22 held-out classes against 4.5% chance, and the k=256 colony averages 41.9% across four independent ants. That is a real effect: it survives a label-permutation null, it is not duration, and the syllable curriculum is what produced it - the same learner on the original human-only corpus gets 23.7% (+18.2 points, p < 0.001, all four ants).

They do not know them the way the word 'know' implies. A codebook built from random real frames of the same corpus, with the k-means iterations never run, scores 40.3% - statistically indistinguishable from the trained ants' 41.9% (paired McNemar p = 0.54, and the trained ant loses on the edit metric). The ants also fail every minimal pair that is genuinely hard (ba/pa, da/ta) while scoring high on pairs modern Hebrew treats as the same sound, and the compositional word test sits at its floor. What the training bought is in-domain reference points and enough of them, not a learned representation.

## Test 0 - the things that would invalidate everything

| control                           | syllable top-1 | reading                                                    |
|-----------------------------------|----------------|------------------------------------------------------------|
| label permutation (200 draws)     | 4.5%           | empirical floor; matches analytic chance                   |
| duration of the sound alone       | 5.3%           | the probes are not measuring how long a syllable is        |
| raw 14-dim features, no codebook  | 53.8%          | ceiling on the speech span                                 |
| raw features, loudest 60% pooling | 68.9%          | ceiling under the earlier report's pooling, for continuity |

Leak check on the held-out set: {"shared_base_renderings_train_heldout": [], "shared_file_names": [], "identical_speech_spans": 0} - no shared vocoder rendering, no shared file, no identical frame matrix.

## Test 1 + 2 - consistency, distinctness, identification

`sep` is within-syllable minus between-syllable similarity over held-out pairs, counting only pairs from *different* vocoder renderings. `AUC` is the probability that a same-syllable pair scores above a different-syllable pair (0.5 = no information). `twin` is the same-rendering augmentation pairs, shown only to prove they were excluded from `sep`.

| group                  | ant   | k   | cos@1 | cos@5 | edit@1 | edit@5 | sep cos | AUC cos | sep edit | AUC edit | twin edit |
|------------------------|-------|-----|-------|-------|--------|--------|---------|---------|----------|----------|-----------|
| 64                     | ant-a | 64  | 34.1  | 70.5  | 26.5   | 60.6   | +0.155  | 0.653   | +0.076   | 0.650    | 0.252     |
| 64                     | ant-b | 64  | 34.8  | 69.7  | 29.5   | 69.7   | +0.180  | 0.684   | +0.088   | 0.676    | 0.235     |
| 64                     | ant-c | 64  | 33.3  | 67.4  | 26.5   | 63.6   | +0.166  | 0.672   | +0.088   | 0.654    | 0.232     |
| 64                     | ant-d | 64  | 31.8  | 72.0  | 27.3   | 73.5   | +0.180  | 0.677   | +0.080   | 0.668    | 0.246     |
| 128                    | ant-a | 128 | 34.1  | 68.9  | 37.1   | 67.4   | +0.163  | 0.700   | +0.078   | 0.690    | 0.182     |
| 128                    | ant-b | 128 | 37.1  | 72.0  | 35.6   | 75.0   | +0.163  | 0.690   | +0.075   | 0.681    | 0.192     |
| 128                    | ant-c | 128 | 31.8  | 73.5  | 34.1   | 77.3   | +0.172  | 0.698   | +0.087   | 0.691    | 0.187     |
| 128                    | ant-d | 128 | 38.6  | 68.2  | 28.0   | 64.4   | +0.166  | 0.699   | +0.076   | 0.688    | 0.177     |
| 256                    | ant-a | 256 | 42.4  | 73.5  | 32.6   | 76.5   | +0.147  | 0.695   | +0.062   | 0.670    | 0.138     |
| 256                    | ant-b | 256 | 40.2  | 72.0  | 37.1   | 78.0   | +0.160  | 0.706   | +0.072   | 0.678    | 0.139     |
| 256                    | ant-c | 256 | 40.9  | 75.8  | 37.9   | 75.0   | +0.149  | 0.704   | +0.065   | 0.676    | 0.143     |
| 256                    | ant-d | 256 | 43.9  | 79.5  | 41.7   | 81.8   | +0.146  | 0.696   | +0.060   | 0.682    | 0.133     |
| 512                    | ant-a | 512 | 41.7  | 81.8  | 44.7   | 84.1   | +0.126  | 0.710   | +0.053   | 0.690    | 0.101     |
| 512                    | ant-b | 512 | 44.7  | 80.3  | 39.4   | 77.3   | +0.123  | 0.692   | +0.055   | 0.684    | 0.107     |
| 512                    | ant-c | 512 | 41.7  | 78.0  | 39.4   | 84.8   | +0.126  | 0.702   | +0.051   | 0.685    | 0.108     |
| 512                    | ant-d | 512 | 40.2  | 77.3  | 47.0   | 81.1   | +0.125  | 0.708   | +0.053   | 0.700    | 0.102     |
| baseline-human-only    | ant-a | 64  | 27.3  | 50.8  | 16.7   | 46.2   | +0.082  | 0.607   | +0.067   | 0.612    | 0.367     |
| baseline-human-only    | ant-b | 64  | 26.5  | 56.8  | 15.9   | 50.8   | +0.053  | 0.571   | +0.044   | 0.582    | 0.339     |
| baseline-human-only    | ant-c | 64  | 18.9  | 53.0  | 15.2   | 53.0   | +0.048  | 0.567   | +0.044   | 0.591    | 0.338     |
| baseline-human-only    | ant-d | 64  | 22.0  | 48.5  | 15.9   | 46.2   | +0.059  | 0.583   | +0.068   | 0.608    | 0.379     |
| random-real-frames-64  | ant-a | 64  | 27.3  | 72.7  | 16.7   | 57.6   | +0.162  | 0.673   | +0.076   | 0.641    | 0.296     |
| random-real-frames-64  | ant-b | 64  | 38.6  | 69.7  | 28.0   | 69.7   | +0.199  | 0.706   | +0.083   | 0.666    | 0.234     |
| random-real-frames-64  | ant-c | 64  | 29.5  | 68.9  | 22.0   | 67.4   | +0.149  | 0.668   | +0.077   | 0.649    | 0.273     |
| random-real-frames-64  | ant-d | 64  | 34.8  | 75.0  | 28.0   | 68.9   | +0.212  | 0.751   | +0.085   | 0.692    | 0.254     |
| random-real-frames-128 | ant-a | 128 | 31.8  | 75.8  | 31.1   | 73.5   | +0.158  | 0.673   | +0.076   | 0.690    | 0.198     |
| random-real-frames-128 | ant-b | 128 | 34.8  | 68.9  | 34.1   | 67.4   | +0.157  | 0.687   | +0.069   | 0.676    | 0.183     |
| random-real-frames-128 | ant-c | 128 | 35.6  | 77.3  | 32.6   | 71.2   | +0.171  | 0.693   | +0.082   | 0.673    | 0.199     |
| random-real-frames-128 | ant-d | 128 | 36.4  | 76.5  | 34.1   | 79.5   | +0.207  | 0.728   | +0.078   | 0.678    | 0.211     |
| random-real-frames-256 | ant-a | 256 | 41.7  | 80.3  | 35.6   | 72.7   | +0.170  | 0.713   | +0.065   | 0.682    | 0.157     |
| random-real-frames-256 | ant-b | 256 | 33.3  | 67.4  | 42.4   | 75.0   | +0.132  | 0.672   | +0.063   | 0.678    | 0.138     |
| random-real-frames-256 | ant-c | 256 | 46.2  | 79.5  | 37.9   | 74.2   | +0.157  | 0.703   | +0.071   | 0.682    | 0.151     |
| random-real-frames-256 | ant-d | 256 | 40.2  | 77.3  | 37.9   | 73.5   | +0.154  | 0.694   | +0.055   | 0.672    | 0.142     |
| random-real-frames-512 | ant-a | 512 | 46.2  | 79.5  | 49.2   | 76.5   | +0.160  | 0.728   | +0.054   | 0.707    | 0.114     |
| random-real-frames-512 | ant-b | 512 | 43.2  | 83.3  | 42.4   | 79.5   | +0.126  | 0.710   | +0.053   | 0.682    | 0.107     |
| random-real-frames-512 | ant-c | 512 | 35.6  | 76.5  | 37.9   | 75.0   | +0.122  | 0.697   | +0.046   | 0.681    | 0.113     |
| random-real-frames-512 | ant-d | 512 | 39.4  | 79.5  | 40.2   | 74.2   | +0.145  | 0.705   | +0.049   | 0.689    | 0.098     |
| random-centres-64      | ant-a | 64  | 21.2  | 59.1  | 19.7   | 51.5   | +0.071  | 0.592   | +0.073   | 0.640    | 0.300     |
| random-centres-64      | ant-b | 64  | 22.0  | 59.1  | 31.8   | 64.4   | +0.087  | 0.601   | +0.079   | 0.650    | 0.321     |
| random-centres-64      | ant-c | 64  | 24.2  | 52.3  | 22.0   | 54.5   | +0.067  | 0.570   | +0.059   | 0.616    | 0.233     |
| random-centres-64      | ant-d | 64  | 22.0  | 64.4  | 25.0   | 57.6   | +0.132  | 0.659   | +0.069   | 0.644    | 0.312     |
| random-centres-128     | ant-a | 128 | 28.8  | 63.6  | 16.7   | 58.3   | +0.101  | 0.621   | +0.068   | 0.651    | 0.299     |
| random-centres-128     | ant-b | 128 | 25.0  | 62.9  | 23.5   | 51.5   | +0.104  | 0.618   | +0.059   | 0.630    | 0.333     |
| random-centres-128     | ant-c | 128 | 24.2  | 62.9  | 28.0   | 62.9   | +0.132  | 0.660   | +0.053   | 0.622    | 0.264     |
| random-centres-128     | ant-d | 128 | 13.6  | 45.5  | 24.2   | 57.6   | +0.064  | 0.611   | +0.082   | 0.674    | 0.296     |
| random-centres-256     | ant-a | 256 | 25.0  | 57.6  | 26.5   | 61.4   | +0.068  | 0.574   | +0.061   | 0.635    | 0.243     |
| random-centres-256     | ant-b | 256 | 26.5  | 65.2  | 25.8   | 63.6   | +0.104  | 0.606   | +0.058   | 0.665    | 0.248     |
| random-centres-256     | ant-c | 256 | 32.6  | 67.4  | 25.8   | 57.6   | +0.168  | 0.688   | +0.057   | 0.621    | 0.252     |
| random-centres-256     | ant-d | 256 | 18.9  | 55.3  | 21.2   | 59.8   | +0.104  | 0.631   | +0.074   | 0.658    | 0.297     |
| random-centres-512     | ant-a | 512 | 23.5  | 67.4  | 25.8   | 62.1   | +0.140  | 0.658   | +0.082   | 0.700    | 0.239     |
| random-centres-512     | ant-b | 512 | 27.3  | 57.6  | 21.2   | 61.4   | +0.109  | 0.613   | +0.058   | 0.655    | 0.226     |
| random-centres-512     | ant-c | 512 | 34.8  | 72.7  | 30.3   | 69.7   | +0.166  | 0.673   | +0.077   | 0.674    | 0.234     |
| random-centres-512     | ant-d | 512 | 17.4  | 53.0  | 25.8   | 58.3   | +0.113  | 0.645   | +0.069   | 0.651    | 0.277     |

Colony means over the four independent ants (± sd):

| group                  | k   | cos@1    | cos@5    | cos mean-link@1 | edit@1   | AUC cos | AUC edit | vs human-only | vs chance |
|------------------------|-----|----------|----------|-----------------|----------|---------|----------|---------------|-----------|
| 64                     | 64  | 33.5±1.1 | 69.9±1.6 | 27.1±2.8        | 27.5±1.2 | 0.672   | 0.662    | +9.8          | 7.4x      |
| 128                    | 128 | 35.4±2.6 | 70.6±2.2 | 34.7±1.1        | 33.7±3.5 | 0.697   | 0.688    | +11.7         | 7.8x      |
| 256                    | 256 | 41.9±1.5 | 75.2±2.9 | 41.3±0.8        | 37.3±3.2 | 0.700   | 0.677    | +18.2         | 9.2x      |
| 512                    | 512 | 42.0±1.7 | 79.4±1.8 | 44.5±5.5        | 42.6±3.3 | 0.703   | 0.690    | +18.4         | 9.2x      |
| baseline-human-only    | 64  | 23.7±3.4 | 52.3±3.1 | 13.4±4.4        | 15.9±0.5 | 0.582   | 0.598    | +0.0          | 5.2x      |
| random-real-frames-64  | 64  | 32.6±4.4 | 71.6±2.4 | 27.3±6.6        | 23.7±4.7 | 0.700   | 0.662    | +8.9          | 7.2x      |
| random-real-frames-128 | 128 | 34.7±1.7 | 74.6±3.3 | 33.9±1.5        | 33.0±1.3 | 0.695   | 0.679    | +11.0         | 7.6x      |
| random-real-frames-256 | 256 | 40.3±4.6 | 76.1±5.2 | 36.6±3.6        | 38.4±2.5 | 0.695   | 0.678    | +16.7         | 8.9x      |
| random-real-frames-512 | 512 | 41.1±4.0 | 79.7±2.4 | 40.9±2.2        | 42.4±4.3 | 0.710   | 0.690    | +17.4         | 9.0x      |
| random-centres-64      | 64  | 22.3±1.1 | 58.7±4.3 | 13.6±3.9        | 24.6±4.6 | 0.606   | 0.637    | -1.3          | 4.9x      |
| random-centres-128     | 128 | 22.9±5.6 | 58.7±7.7 | 16.1±6.0        | 23.1±4.1 | 0.627   | 0.644    | -0.8          | 5.0x      |
| random-centres-256     | 256 | 25.8±4.9 | 61.4±5.1 | 16.7±3.9        | 24.8±2.1 | 0.625   | 0.645    | +2.1          | 5.7x      |
| random-centres-512     | 512 | 25.8±6.3 | 62.7±7.8 | 18.6±3.1        | 25.8±3.2 | 0.647   | 0.670    | +2.1          | 5.7x      |

## Which syllables they confuse

Pooled over the four ants of the k=512 colony (528 decisions):

| confused pair | errors | phonetics, and how close the two really are                                                                      |
|---------------|--------|------------------------------------------------------------------------------------------------------------------|
| ba/tha        | 17     | stop/bilabial/voiced vs stop/alveolar/voiceless - shares stop                                                    |
| la/qa         | 13     | approximant/alveolar/voiced vs stop/velar/voiceless - #3 acoustically closest pair                               |
| da/ga         | 12     | stop/alveolar/voiced vs stop/velar/voiced - shares stop, voiced                                                  |
| ah/ma         | 11     | vowel-onset/glottal/voiced vs nasal/bilabial/voiced - shares voiced                                              |
| ha/na         | 11     | fricative/glottal/voiceless vs nasal/alveolar/voiced - #2 acoustically closest pair                              |
| aa/ra         | 10     | vowel-onset/pharyngeal/voiced vs approximant/uvular/voiced - #1 acoustically closest pair; shares voiced         |
| aa/ka         | 8      | vowel-onset/pharyngeal/voiced vs stop/velar/voiceless                                                            |
| ka/sa         | 8      | stop/velar/voiceless vs fricative/alveolar/voiceless - #5 acoustically closest pair; shares voiceless            |
| da/pa         | 6      | stop/alveolar/voiced vs stop/bilabial/voiceless - #6 acoustically closest pair; shares stop                      |
| da/tha        | 6      | stop/alveolar/voiced vs stop/alveolar/voiceless - shares stop, alveolar                                          |
| ta/tha        | 6      | stop/alveolar/voiceless vs stop/alveolar/voiceless - SAME phoneme in modern Hebrew; #8 acoustically closest pair |
| aa/ma         | 5      | vowel-onset/pharyngeal/voiced vs nasal/bilabial/voiced - shares voiced                                           |
| aa/sa         | 4      | vowel-onset/pharyngeal/voiced vs fricative/alveolar/voiceless                                                    |
| ah/ra         | 3      | vowel-onset/glottal/voiced vs approximant/uvular/voiced - shares voiced                                          |
| ba/pa         | 3      | stop/bilabial/voiced vs stop/bilabial/voiceless - shares stop, bilabial                                          |

Confusion structure, pooled per colony. `rho acoustic` is Spearman correlation between how often a pair is confused and how far apart the two syllables sit in the ants' own 14-dim feature space (negative = confuses things that sound alike, which is what a real representation should do). `rho phonetic` is the same against shared manner/place/voicing. `closest-10` is the share of all errors landing on the ten acoustically closest pairs, which are 4.3% of the 231 possible pairs.

| group                  | errors | rho acoustic | rho phonetic | closest-10 share |
|------------------------|--------|--------------|--------------|------------------|
| 64                     | 351    | -0.514       | +0.046       | 23.4%            |
| 128                    | 341    | -0.562       | +0.043       | 22.3%            |
| 256                    | 307    | -0.497       | +0.087       | 26.1%            |
| 512                    | 306    | -0.461       | +0.027       | 24.2%            |
| baseline-human-only    | 403    | -0.382       | +0.106       | 10.2%            |
| random-real-frames-64  | 356    | -0.507       | +0.082       | 19.4%            |
| random-real-frames-128 | 345    | -0.520       | +0.099       | 22.3%            |
| random-real-frames-256 | 315    | -0.529       | +0.101       | 24.4%            |
| random-real-frames-512 | 311    | -0.560       | +0.056       | 22.5%            |
| random-centres-64      | 410    | -0.426       | +0.004       | 11.7%            |
| random-centres-128     | 407    | -0.401       | +0.081       | 13.5%            |
| random-centres-256     | 392    | -0.402       | +0.156       | 15.1%            |
| random-centres-512     | 392    | -0.471       | +0.060       | 16.1%            |

Per-class held-out accuracy, same colony, mean over the four ants:

| syllable | accuracy |
|----------|----------|
| sha      | 100%     |
| tsa      | 100%     |
| za       | 88%      |
| ya       | 88%      |
| sa       | 62%      |
| kha      | 62%      |
| ra       | 58%      |
| va       | 58%      |
| ha       | 50%      |
| na       | 50%      |
| tha      | 42%      |
| la       | 33%      |
| ah       | 29%      |
| ka       | 29%      |
| ta       | 21%      |
| qa       | 17%      |
| aa       | 12%      |
| ga       | 12%      |
| da       | 4%       |
| ma       | 4%       |
| pa       | 4%       |
| ba       | 0%       |

## Test 3 - minimal pairs (forced two-way choice, chance 50%, 48 decisions each)

`1-NN` and `mean-link` are the same decision made two ways; with six held-out tokens per syllable a single odd training token can swing 1-NN, so a pair only counts as separated if both agree. `raw` is the same test on the ants' features with no codebook - it says whether the contrast survives in the audio at all. `dist` is the distance between the two syllables' centroids in that feature space; a large distance means the pair is not actually a hard case in this corpus, whatever the phonology says.

| pair   | 1-NN | mean-link | 1-NN correct | human-only | raw  | dist | verdict                               |
|--------|------|-----------|--------------|------------|------|------|---------------------------------------|
| ba/pa  | 35%  | 50%       | 17/48        | 44%        | 100% | 2.61 | NOT separated                         |
| ga/ka  | 100% | 100%      | 48/48        | 69%        | 100% | 6.35 | separated                             |
| da/ta  | 54%  | 56%       | 26/48        | 50%        | 75%  | 1.86 | NOT separated                         |
| sa/sha | 100% | 100%      | 48/48        | 96%        | 100% | 7.34 | separated                             |
| ka/qa  | 100% | 100%      | 48/48        | 42%        | 100% | 4.43 | separated (same phoneme - see below)  |
| ta/tha | 69%  | 69%       | 33/48        | 58%        | 83%  | 2.18 | borderline (same phoneme - see below) |
| za/sa  | 100% | 100%      | 48/48        | 73%        | 100% | 5.54 | separated                             |
| ah/aa  | 69%  | 67%       | 33/48        | 40%        | 100% | 2.56 | borderline (same phoneme - see below) |

**Read `aa/ah`, `ka/qa`, `ta/tha` in the opposite direction.** Modern Israeli Hebrew merges these: kaf/qof are both /k/, tet/tav are both /t/, alef/ayin are both a bare vowel onset. A high score there is not phonetic skill, it is the ant picking up a fingerprint of how mms-tts-heb rendered two different letters. The prior corpus audit already established that the tokenizer strips niqqud, so the realised sound is whatever the model inferred from a bare consonant, not the vowel that was written down. `ka/qa` sits 4.4 apart in feature space - further than most genuinely different consonants - which is not what a merged pair should look like.

## Test 4 - words (the honest one)

| group                  | k   | word id edit@1 | word id cos@1 | constituent AUC | constituent rank pct | in-top-n % |
|------------------------|-----|----------------|---------------|-----------------|----------------------|------------|
| 64                     | 64  | 54.4±2.6       | 47.4±8.9      | 0.551           | 0.440                | 17.6       |
| 128                    | 128 | 61.2±2.7       | 52.1±4.2      | 0.562           | 0.422                | 20.5       |
| 256                    | 256 | 66.7±4.1       | 57.8±0.9      | 0.569           | 0.422                | 22.1       |
| 512                    | 512 | 65.4±4.2       | 62.8±4.4      | 0.582           | 0.417                | 21.5       |
| baseline-human-only    | 64  | 33.1±6.2       | 33.3±3.0      | 0.553           | 0.443                | 19.5       |
| random-real-frames-64  | 64  | 52.3±10.1      | 43.0±7.4      | 0.564           | 0.426                | 21.0       |
| random-real-frames-128 | 128 | 53.6±6.3       | 51.0±2.9      | 0.576           | 0.423                | 21.4       |
| random-real-frames-256 | 256 | 64.3±6.7       | 55.2±1.3      | 0.545           | 0.446                | 18.9       |
| random-real-frames-512 | 512 | 66.4±2.7       | 59.6±2.4      | 0.573           | 0.423                | 21.6       |
| random-centres-64      | 64  | 41.1±4.9       | 34.1±3.8      | 0.580           | 0.413                | 19.5       |
| random-centres-128     | 128 | 44.0±7.7       | 43.2±5.4      | 0.564           | 0.426                | 19.2       |
| random-centres-256     | 256 | 50.5±1.7       | 40.9±4.3      | 0.576           | 0.420                | 17.4       |
| random-centres-512     | 512 | 52.6±4.9       | 44.0±8.2      | 0.590           | 0.395                | 21.3       |

Word identification is 12-way, chance 8.3%, leave-one-vocoder-rendering-out, on 96 files no colony ever trained on. That part works, and it scales with the syllable curriculum the same way the syllable test does.

**The constituent test does not work, and that is the honest headline of this section.** It asks whether a word's unit string actually contains its syllables' unit strings: each of the 22 syllables is aligned as a substring of the word (free start, free end) and the 22 are ranked. If the representation were compositional the syllables a word is spelled with would rank at the top. AUC 0.5 and rank percentile 0.5 are no information. The trained colonies sit at AUC 0.582 - and random Gaussian centres, which know nothing, sit at 0.590. The trained ants are not better than the untrained control here, so the small excess over 0.5 is a property of the alignment statistic, not evidence of learned sub-word structure. Word identification therefore works the way any whole-utterance fingerprint works, not by recognising the syllables inside. That is the predicted outcome - the ants were taught isolated syllables, and a syllable inside a word is shorter and coarticulated - but it is worth saying plainly rather than reporting the 65% word score alone. Chance for the in-top-n column is 12.9%.

## Capacity

| k   | syllable cos@1 | syllable edit@1 | AUC cos | word edit@1 | mean unit-string length | units used on held-out |
|-----|----------------|-----------------|---------|-------------|-------------------------|------------------------|
| 64  | 33.5±1.1       | 27.5±1.2        | 0.672   | 54.4±2.6    | 19.0                    | 46                     |
| 128 | 35.4±2.6       | 33.7±3.5        | 0.697   | 61.2±2.7    | 22.6                    | 90                     |
| 256 | 41.9±1.5       | 37.3±3.2        | 0.700   | 66.7±4.1    | 25.5                    | 172                    |
| 512 | 42.0±1.7       | 42.6±3.3        | 0.703   | 65.4±4.2    | 28.7                    | 321                    |

## Paired tests on the same 132 items (exact McNemar)

Every codebook is scored on the same held-out tokens, so the honest comparison is item-by-item and matched by seed, not colony mean against colony mean.

| comparison                                               | metric | left % | right % | delta pts | p      | ants won |
|----------------------------------------------------------|--------|--------|---------|-----------|--------|----------|
| A curriculum: combined-64 vs human-only-64               | cosine | 33.5   | 23.7    | +9.8      | 0.0000 | 4/4      |
| B optimiser: combined-256 vs random-real-frames-256      | cosine | 41.9   | 40.3    | +1.5      | 0.5394 | 3/4      |
| B' optimiser: combined-64 vs random-real-frames-64       | cosine | 33.5   | 32.6    | +0.9      | 0.7345 | 2/4      |
| C partition: combined-256 vs random-gaussian-centres-256 | cosine | 41.9   | 25.8    | +16.1     | 0.0000 | 4/4      |
| D capacity: combined-256 vs combined-64                  | cosine | 41.9   | 33.5    | +8.3      | 0.0003 | 4/4      |
| A curriculum: combined-64 vs human-only-64               | edit   | 27.5   | 15.9    | +11.6     | 0.0000 | 4/4      |
| B optimiser: combined-256 vs random-real-frames-256      | edit   | 37.3   | 38.4    | -1.1      | 0.6832 | 1/4      |
| B' optimiser: combined-64 vs random-real-frames-64       | edit   | 27.5   | 23.7    | +3.8      | 0.1205 | 3/4      |
| C partition: combined-256 vs random-gaussian-centres-256 | edit   | 37.3   | 24.8    | +12.5     | 0.0000 | 4/4      |
| D capacity: combined-256 vs combined-64                  | edit   | 37.3   | 27.5    | +9.8      | 0.0000 | 4/4      |

## What this does not prove

- One synthetic voice. Every syllable and word came from a single cached mms-tts-heb speaker. Nothing here shows the ants would recognise these syllables from a human mouth, and the 24 human recordings are one speaker too.
- One vocoder, one recording chain. Held-out tokens are different renderings with different prosody seeds, but the same synthesiser and the same augmentation pipeline. Cross-speaker and cross-channel generalisation is completely untested.
- Recognition, not production. A codebook that separates syllables cannot utter them; the exemplar reconstruction path is a different claim and is not measured here.
- No phonetics. A unit is a 25 ms spectral cluster. Nothing establishes that a unit corresponds to a phoneme, a segment boundary, or any linguistic object.
- The Lloyd iterations are not what is working. Random real frames from the same corpus score the same, so 'the ant learned' means 'the ant is holding in-domain reference points', not 'the ant optimised a representation'.
- Isolated syllables are the easy case. The word tests show the representation does not carry over to syllables inside connected speech.
- The held-out split fed the Queen's selection criterion (quantisation error), so it is held out from fitting but not from every decision in the pipeline.
- 132 held-out tokens, 22 classes, six tokens per class. Per-class and per-minimal-pair numbers are noisy; only the pooled figures carry weight.

{
  "report": "reports/syllable-knowledge.json",
  "paired_tests": "reports/paired-tests.json",
  "confusion_analysis": "reports/confusion-analysis.json",
  "probe_library": "sequence_probes.py",
  "driver": "run_knowledge_tests.py",
  "summariser": "summarise_knowledge.py",
  "tests": "tests/test_sequence_probes.py"
}
