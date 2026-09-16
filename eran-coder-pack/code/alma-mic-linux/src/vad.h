#ifndef ALMA_VAD_H
#define ALMA_VAD_H
#include <stdint.h>

/* Energy + zero-crossing VAD with hysteresis: opens fast (2 frames above the
 * open threshold), closes slow (hangover of silence below the close
 * threshold). Same approach as the Android side so behaviour is consistent. */
typedef struct {
    /* config */
    float open_mult;      /* open threshold  = max(noise_floor * open_mult,  abs_open)  */
    float close_mult;     /* close threshold = max(noise_floor * close_mult, abs_close) */
    float abs_open;
    float abs_close;
    float zcr_min, zcr_max;   /* zero-crossing sanity band for onset only */
    int   open_frames;        /* consecutive speechy frames required to open */
    int   hangover_frames;    /* silent frames required to close */
    int   warmup_frames;      /* frames used only to seed the noise floor */
    /* state */
    float noise_floor;
    int   consec_open;
    int   silence_run;
    int   in_speech;
    int   warmup_left;
    /* diagnostics: last frame */
    float last_rms;
    float last_zcr;
} vad_t;

void vad_init(vad_t *v, int frame_ms, int hangover_ms);
/* Process one PCM16 frame. Returns current open state (0/1);
 * *just_opened / *just_closed are set on the transition frame. */
int vad_process(vad_t *v, const int16_t *x, int n, int *just_opened, int *just_closed);

#endif
