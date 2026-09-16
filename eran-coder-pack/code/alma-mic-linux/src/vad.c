#include "vad.h"
#include <math.h>

void vad_init(vad_t *v, int frame_ms, int hangover_ms)
{
    v->open_mult   = 3.0f;   /* mirrors alma-mic desktop VAD (onset floor*3.0) */
    v->close_mult  = 1.8f;   /* offset below floor*1.8 */
    v->abs_open    = 0.006f;
    v->abs_close   = 0.003f;
    v->zcr_min     = 0.015f; /* rejects pure low-frequency hum */
    v->zcr_max     = 0.50f;  /* rejects broadband electrical hash */
    v->open_frames = 2;                            /* open fast: 60 ms */
    v->hangover_frames = hangover_ms / frame_ms;   /* close slow */
    if (v->hangover_frames < 1) v->hangover_frames = 1;
    v->warmup_frames = 150 / frame_ms;             /* 150 ms floor seeding */
    v->noise_floor = 0.0015f;
    v->consec_open = 0;
    v->silence_run = 0;
    v->in_speech   = 0;
    v->warmup_left = v->warmup_frames;
    v->last_rms = 0.0f;
    v->last_zcr = 0.0f;
}

int vad_process(vad_t *v, const int16_t *x, int n, int *just_opened, int *just_closed)
{
    *just_opened = 0;
    *just_closed = 0;
    if (n <= 0) return v->in_speech;

    double sq = 0.0;
    int zc = 0, prev_sign = 0;
    const int dead = 60;   /* ~0.002 FS deadband: idle hiss does not count as crossings */
    for (int i = 0; i < n; i++) {
        float s = (float)x[i] / 32768.0f;
        sq += (double)s * s;
        int sgn = (x[i] > dead) ? 1 : (x[i] < -dead ? -1 : 0);
        if (sgn != 0) {
            if (prev_sign != 0 && sgn != prev_sign) zc++;
            prev_sign = sgn;
        }
    }
    float rms = (float)sqrt(sq / (double)n);
    float zcr = (float)zc / (float)n;
    v->last_rms = rms;
    v->last_zcr = zcr;

    if (v->warmup_left > 0) {
        v->warmup_left--;
        v->noise_floor = 0.8f * v->noise_floor + 0.2f * rms;
        if (v->noise_floor < 0.0004f) v->noise_floor = 0.0004f;
        if (v->noise_floor > 0.02f)   v->noise_floor = 0.02f;
        return 0;
    }

    float open_thr = v->noise_floor * v->open_mult;
    if (open_thr < v->abs_open) open_thr = v->abs_open;
    float close_thr = v->noise_floor * v->close_mult;
    if (close_thr < v->abs_close) close_thr = v->abs_close;

    if (!v->in_speech) {
        int speechy = (rms > open_thr) && (zcr >= v->zcr_min) && (zcr <= v->zcr_max);
        if (speechy) {
            v->consec_open++;
            if (v->consec_open >= v->open_frames) {
                v->in_speech = 1;
                v->consec_open = 0;
                v->silence_run = 0;
                *just_opened = 1;
            }
        } else {
            v->consec_open = 0;
            /* adapt the noise floor only on clearly non-speech frames */
            if (rms < open_thr) {
                v->noise_floor = 0.95f * v->noise_floor + 0.05f * rms;
                if (v->noise_floor < 0.0004f) v->noise_floor = 0.0004f;
                if (v->noise_floor > 0.02f)   v->noise_floor = 0.02f;
            }
        }
    } else {
        if (rms < close_thr) {
            v->silence_run++;
            if (v->silence_run >= v->hangover_frames) {
                v->in_speech = 0;
                v->silence_run = 0;
                *just_closed = 1;
            }
        } else {
            v->silence_run = 0;
        }
    }
    return v->in_speech;
}
