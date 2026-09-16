#define _GNU_SOURCE
#include "audio.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <pulse/simple.h>
#include <pulse/error.h>
#include <pulse/pulseaudio.h>

struct audio_src {
    int kind;            /* 0 = pulse, 1 = wav */
    pa_simple *pa;
    FILE *f;
    long data_left;      /* bytes remaining in wav data chunk */
    char desc[300];
};

audio_src *audio_open_pulse(const char *device, char *err, size_t errsz)
{
    pa_sample_spec ss;
    ss.format = PA_SAMPLE_S16LE;
    ss.rate = AM_RATE;
    ss.channels = 1;
    pa_buffer_attr ba;
    ba.maxlength = (uint32_t)-1;
    ba.tlength   = (uint32_t)-1;
    ba.prebuf    = (uint32_t)-1;
    ba.minreq    = (uint32_t)-1;
    ba.fragsize  = AM_FRAME_SAMPLES * 2;   /* ~30 ms fragments */
    int e = 0;
    pa_simple *pa = pa_simple_new(NULL, "alma-micd", PA_STREAM_RECORD,
                                  device, "capture", &ss, NULL, &ba, &e);
    if (!pa) {
        snprintf(err, errsz, "pa_simple_new(%s): %s",
                 device ? device : "default", pa_strerror(e));
        return NULL;
    }
    audio_src *s = calloc(1, sizeof *s);
    if (!s) { pa_simple_free(pa); snprintf(err, errsz, "oom"); return NULL; }
    s->kind = 0;
    s->pa = pa;
    snprintf(s->desc, sizeof s->desc, "pulse:%s", device ? device : "default");
    return s;
}

static int rd_u32(FILE *f, uint32_t *v)
{
    unsigned char b[4];
    if (fread(b, 1, 4, f) != 4) return -1;
    *v = (uint32_t)b[0] | ((uint32_t)b[1] << 8) | ((uint32_t)b[2] << 16) | ((uint32_t)b[3] << 24);
    return 0;
}

static int rd_u16(FILE *f, uint16_t *v)
{
    unsigned char b[2];
    if (fread(b, 1, 2, f) != 2) return -1;
    *v = (uint16_t)(b[0] | (b[1] << 8));
    return 0;
}

audio_src *audio_open_wav(const char *path, char *err, size_t errsz)
{
    FILE *f = fopen(path, "rb");
    if (!f) { snprintf(err, errsz, "open %s failed", path); return NULL; }
    char id[4];
    uint32_t sz;
    if (fread(id, 1, 4, f) != 4 || memcmp(id, "RIFF", 4) != 0 || rd_u32(f, &sz) != 0 ||
        fread(id, 1, 4, f) != 4 || memcmp(id, "WAVE", 4) != 0) {
        snprintf(err, errsz, "%s: not a RIFF/WAVE file", path);
        fclose(f);
        return NULL;
    }
    uint16_t fmt = 0, ch = 0, bits = 0;
    uint32_t rate = 0, data_sz = 0;
    long data_off = -1;
    for (;;) {
        if (fread(id, 1, 4, f) != 4 || rd_u32(f, &sz) != 0) break;
        if (memcmp(id, "fmt ", 4) == 0) {
            long next = ftell(f) + (long)sz + (long)(sz & 1);
            uint32_t br;
            uint16_t ba;
            if (rd_u16(f, &fmt) || rd_u16(f, &ch) || rd_u32(f, &rate) ||
                rd_u32(f, &br) || rd_u16(f, &ba) || rd_u16(f, &bits)) break;
            fseek(f, next, SEEK_SET);
        } else if (memcmp(id, "data", 4) == 0) {
            data_off = ftell(f);
            data_sz = sz;
            break;
        } else {
            fseek(f, (long)sz + (long)(sz & 1), SEEK_CUR);
        }
    }
    if (fmt != 1 || ch != 1 || bits != 16 || rate != AM_RATE || data_off < 0) {
        snprintf(err, errsz,
                 "%s: need PCM16 mono %d Hz (got fmt=%u ch=%u bits=%u rate=%u)",
                 path, AM_RATE, fmt, ch, bits, rate);
        fclose(f);
        return NULL;
    }
    fseek(f, data_off, SEEK_SET);
    audio_src *s = calloc(1, sizeof *s);
    if (!s) { fclose(f); snprintf(err, errsz, "oom"); return NULL; }
    s->kind = 1;
    s->f = f;
    s->data_left = (long)data_sz;
    snprintf(s->desc, sizeof s->desc, "wav:%s", path);
    return s;
}

int audio_read(audio_src *s, int16_t *out, int n)
{
    if (s->kind == 0) {
        int e = 0;
        if (pa_simple_read(s->pa, out, (size_t)n * 2, &e) < 0) return -1;
        return 1;
    }
    if (s->data_left <= 0) return 0;
    long want = (long)n * 2;
    long take = s->data_left < want ? s->data_left : want;
    size_t got = fread(out, 1, (size_t)take, s->f);
    s->data_left -= (long)got;
    if (got == 0) { s->data_left = 0; return 0; }
    if ((long)got < want)
        memset((char *)out + got, 0, (size_t)(want - (long)got));
    return 1;
}

void audio_close(audio_src *s)
{
    if (!s) return;
    if (s->kind == 0 && s->pa) pa_simple_free(s->pa);
    if (s->kind == 1 && s->f) fclose(s->f);
    free(s);
}

const char *audio_desc(audio_src *s)
{
    return s->desc;
}

/* ---- device listing via the Pulse introspection API ---- */

typedef struct {
    int done;        /* 1 = finished ok, -1 = failed */
    int count;
    char defsrc[512];
} list_ctx;

static void src_cb(pa_context *c, const pa_source_info *i, int eol, void *ud)
{
    (void)c;
    list_ctx *lc = ud;
    if (eol) { lc->done = 1; return; }
    if (!i) return;
    const char *mark = (lc->defsrc[0] && strcmp(i->name, lc->defsrc) == 0) ? "  [default]" : "";
    const char *kind = (i->monitor_of_sink != PA_INVALID_INDEX) ? "monitor" : "input";
    const char *st = i->state == PA_SOURCE_RUNNING ? "running" :
                     i->state == PA_SOURCE_IDLE ? "idle" : "suspended";
    printf("  #%-3u %-7s %-9s %uch @ %5u Hz  %s%s\n"
           "        desc: %s\n",
           i->index, kind, st, i->sample_spec.channels, i->sample_spec.rate,
           i->name, mark, i->description ? i->description : "");
    lc->count++;
}

static void server_cb(pa_context *c, const pa_server_info *i, void *ud)
{
    list_ctx *lc = ud;
    if (i && i->default_source_name)
        snprintf(lc->defsrc, sizeof lc->defsrc, "%s", i->default_source_name);
    pa_operation *o = pa_context_get_source_info_list(c, src_cb, lc);
    if (o) pa_operation_unref(o);
    else lc->done = -1;
}

static void state_cb(pa_context *c, void *ud)
{
    list_ctx *lc = ud;
    pa_context_state_t st = pa_context_get_state(c);
    if (st == PA_CONTEXT_READY) {
        pa_operation *o = pa_context_get_server_info(c, server_cb, lc);
        if (o) pa_operation_unref(o);
        else lc->done = -1;
    } else if (st == PA_CONTEXT_FAILED || st == PA_CONTEXT_TERMINATED) {
        lc->done = -1;
    }
}

int audio_list_devices(void)
{
    list_ctx lc;
    memset(&lc, 0, sizeof lc);
    pa_mainloop *ml = pa_mainloop_new();
    if (!ml) return 1;
    pa_context *c = pa_context_new(pa_mainloop_get_api(ml), "alma-micd");
    if (!c) { pa_mainloop_free(ml); return 1; }
    pa_context_set_state_callback(c, state_cb, &lc);
    if (pa_context_connect(c, NULL, PA_CONTEXT_NOFLAGS, NULL) < 0) {
        fprintf(stderr, "cannot connect to PulseAudio/PipeWire: %s\n",
                pa_strerror(pa_context_errno(c)));
        pa_context_unref(c);
        pa_mainloop_free(ml);
        return 1;
    }
    printf("capture sources (PipeWire/Pulse):\n");
    int iters = 0;
    while (lc.done == 0 && iters++ < 20000) {
        if (pa_mainloop_iterate(ml, 1, NULL) < 0) break;
    }
    int ok = (lc.done == 1);   /* read before disconnect: the TERMINATED state
                                  callback fires during disconnect and would
                                  overwrite lc.done */
    if (ok && lc.count == 0)
        printf("  (none - no capture source present on this node)\n");
    if (lc.defsrc[0])
        printf("default source: %s\n", lc.defsrc);
    if (!ok)
        fprintf(stderr, "pulse connection failed or timed out\n");
    pa_context_disconnect(c);
    pa_context_unref(c);
    pa_mainloop_free(ml);
    return ok ? 0 : 1;
}
