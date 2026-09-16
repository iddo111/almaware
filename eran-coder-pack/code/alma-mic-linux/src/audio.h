#ifndef ALMA_AUDIO_H
#define ALMA_AUDIO_H
#include <stdint.h>
#include <stddef.h>

#define AM_RATE          16000
#define AM_FRAME_MS      30
#define AM_FRAME_SAMPLES (AM_RATE * AM_FRAME_MS / 1000)   /* 480 */

typedef struct audio_src audio_src;

/* device: Pulse/PipeWire source name, NULL = default source */
audio_src *audio_open_pulse(const char *device, char *err, size_t errsz);
/* WAV file fed through the identical pipeline (must be PCM16 mono 16 kHz) */
audio_src *audio_open_wav(const char *path, char *err, size_t errsz);

/* Read exactly n samples. Returns 1 ok, 0 EOF (wav only), -1 error. */
int  audio_read(audio_src *s, int16_t *out, int n);
void audio_close(audio_src *s);
const char *audio_desc(audio_src *s);

/* Print capture sources + default source to stdout. 0 ok. */
int audio_list_devices(void);

#endif
