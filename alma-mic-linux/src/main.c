/* alma-micd — ALMA always-on microphone daemon (native Linux, C11).
 *
 * Captures 16 kHz mono PCM16 from the default PipeWire/PulseAudio source,
 * segments speech with an energy + zero-crossing VAD (hysteresis: open fast,
 * close slow — same approach as the Android client), converts each utterance
 * to raw float32 LE and POSTs it to the ALMA-STT fleet endpoint:
 *
 *   POST /v1/transcribe?language=he&task=transcribe
 *   Content-Type: application/octet-stream
 *   X-ALMA-Sample-Rate: 16000
 *   body: float32 LE mono 16 kHz, <= 30 s
 *
 * Every finished segment is first written to a disk queue; a sender thread
 * drains the queue oldest-first and deletes on HTTP 200. If the endpoint is
 * unreachable (or refuses: the fleet allowlist currently only admits the PC),
 * audio is kept on disk and retried with exponential backoff (5 s .. 5 min).
 * Logs go to stderr with sd-daemon priority prefixes -> journald.
 */
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <errno.h>
#include <signal.h>
#include <dirent.h>
#include <pthread.h>
#include <time.h>
#include <sys/stat.h>

#include "audio.h"
#include "vad.h"
#include "http.h"
#include "util.h"

#define MAX_BODY_BYTES 1920000       /* server hard limit: 30 s of float32 */
#define QUEUE_MAX_FILES 500
#define QUEUE_MAX_BYTES (256u * 1024 * 1024)
#define PREROLL_FRAMES 10            /* 300 ms kept before VAD onset */

typedef struct {
    char server[512];
    char host[256];
    int  port;
    char language[16];
    char device[256];
    char queue_dir[512];
    char bad_dir[560];
    char transcripts[512];
    int  hangover_ms;
    int  min_speech_ms;
    int  max_segment_ms;
    double open_rms;
    double rms_gate;
    int  verbose;
} cfg_t;

static volatile sig_atomic_t g_run = 1;
static pthread_mutex_t g_qmx = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t  g_qcv = PTHREAD_COND_INITIALIZER;
static int g_echo = 0;   /* --once/--wav/--flush: also print outcomes to stdout */

static void on_signal(int sig)
{
    (void)sig;
    g_run = 0;
}

static void sleep_checked(int tenths)
{
    for (int i = 0; i < tenths && g_run; i++) {
        struct timespec ts = {0, 100000000L};
        nanosleep(&ts, NULL);
    }
}

/* ---------------- disk queue ---------------- */

static int q_filter(const struct dirent *d)
{
    size_t n = strlen(d->d_name);
    return strncmp(d->d_name, "utt_", 4) == 0 &&
           n > 4 && strcmp(d->d_name + n - 4, ".f32") == 0;
}

static void enforce_queue_cap(const cfg_t *cfg)
{
    struct dirent **list = NULL;
    int n = scandir(cfg->queue_dir, &list, q_filter, alphasort);
    if (n <= 0) { free(list); return; }
    long long total = 0;
    for (int i = 0; i < n; i++) {
        char p[1200];
        snprintf(p, sizeof p, "%s/%s", cfg->queue_dir, list[i]->d_name);
        struct stat st;
        if (stat(p, &st) == 0) total += st.st_size;
    }
    int drop = 0;
    while (drop < n && (n - drop > QUEUE_MAX_FILES || total > (long long)QUEUE_MAX_BYTES)) {
        char p[1200];
        snprintf(p, sizeof p, "%s/%s", cfg->queue_dir, list[drop]->d_name);
        struct stat st;
        long long sz = (stat(p, &st) == 0) ? st.st_size : 0;
        if (unlink(p) == 0) {
            LOG_WARN("queue cap reached, dropped oldest: %s", list[drop]->d_name);
            total -= sz;
        }
        drop++;
    }
    for (int i = 0; i < n; i++) free(list[i]);
    free(list);
}

static int enqueue_segment(const cfg_t *cfg, const int16_t *s, size_t n, float rms)
{
    float *f = malloc(n * sizeof(float));
    if (!f) return -1;
    for (size_t i = 0; i < n; i++)
        f[i] = (float)s[i] / 32768.0f;      /* aarch64/x86 are LE: raw = float32 LE */

    static unsigned seq = 0;
    char fin[1200], tmp[1220];
    snprintf(fin, sizeof fin, "%s/utt_%013llu_%04u.f32",
             cfg->queue_dir, (unsigned long long)now_ms(), seq++);
    snprintf(tmp, sizeof tmp, "%s.tmp", fin);
    FILE *fp = fopen(tmp, "wb");
    if (!fp) { free(f); LOG_ERR("queue write failed: %s: %s", tmp, strerror(errno)); return -1; }
    size_t w = fwrite(f, sizeof(float), n, fp);
    fclose(fp);
    free(f);
    if (w != n) { unlink(tmp); LOG_ERR("queue short write: %s", tmp); return -1; }
    rename(tmp, fin);
    LOG_INFO("segment queued: %s (%.2f s, rms %.4f)", fin, (double)n / AM_RATE, rms);
    if (g_echo) printf("QUEUED  %s (%.2f s)\n", fin, (double)n / AM_RATE);
    enforce_queue_cap(cfg);
    pthread_mutex_lock(&g_qmx);
    pthread_cond_signal(&g_qcv);
    pthread_mutex_unlock(&g_qmx);
    return 0;
}

/* ---------------- sender ---------------- */

typedef enum { SEND_OK, SEND_RETRY, SEND_BAD } send_result;

static void append_transcript(const cfg_t *cfg, const char *utt,
                              const char *text, const char *lang, double lat)
{
    FILE *fp = fopen(cfg->transcripts, "a");
    if (!fp) { LOG_WARN("cannot append %s", cfg->transcripts); return; }
    char ts[40], esc[16384];
    iso_utc(ts, sizeof ts);
    json_escape(text, esc, sizeof esc);
    fprintf(fp, "{\"ts\":\"%s\",\"utt\":\"%s\",\"text\":\"%s\",\"language\":\"%s\",\"latency_s\":%.3f}\n",
            ts, utt, esc, lang, lat);
    fclose(fp);
}

static send_result process_file(const cfg_t *cfg, const char *name)
{
    char path[1200];
    snprintf(path, sizeof path, "%s/%s", cfg->queue_dir, name);

    FILE *fp = fopen(path, "rb");
    if (!fp) return SEND_BAD;
    fseek(fp, 0, SEEK_END);
    long sz = ftell(fp);
    fseek(fp, 0, SEEK_SET);
    if (sz <= 0 || (sz % 4) != 0 || sz > MAX_BODY_BYTES) {
        fclose(fp);
        char bad[1800];
        snprintf(bad, sizeof bad, "%s/%s", cfg->bad_dir, name);
        rename(path, bad);
        LOG_WARN("invalid segment size %ld, moved to bad/: %s", sz, name);
        return SEND_BAD;
    }
    char *body = malloc((size_t)sz);
    if (!body) { fclose(fp); return SEND_RETRY; }
    size_t got = fread(body, 1, (size_t)sz, fp);
    fclose(fp);
    if (got != (size_t)sz) { free(body); return SEND_RETRY; }

    char qpath[256];
    snprintf(qpath, sizeof qpath, "/v1/transcribe?language=%s&task=transcribe", cfg->language);
    http_response resp;
    char err[256];
    int rc = http_post_octet(cfg->host, cfg->port, qpath, body, (size_t)sz,
                             8000, 120000, &resp, err, sizeof err);
    free(body);
    if (rc != 0) {
        LOG_WARN("send %s: %s", name, err);
        if (g_echo) printf("RETRY   %s (transport: %s)\n", name, err);
        return SEND_RETRY;
    }

    send_result result;
    if (resp.status == 200 && resp.body) {
        char text[8192] = {0}, lang[32] = {0};
        double lat = 0;
        int suppressed = 0;
        json_get_string(resp.body, "text", text, sizeof text);
        json_get_string(resp.body, "language", lang, sizeof lang);
        json_get_double(resp.body, "latency_s", &lat);
        json_get_bool(resp.body, "suppressed_as_no_speech", &suppressed);
        if (suppressed || text[0] == 0) {
            LOG_INFO("no speech in %s (server no-speech suppression)", name);
            if (g_echo) printf("NOSPEECH %s\n", name);
        } else {
            LOG_INFO("transcript [%s, stt %.2fs] %s", lang[0] ? lang : "?", lat, text);
            if (g_echo) printf("TRANSCRIPT [%s, stt %.2fs] %s\n", lang[0] ? lang : "?", lat, text);
            append_transcript(cfg, name, text, lang[0] ? lang : "?", lat);
        }
        unlink(path);
        result = SEND_OK;
    } else if (resp.status == 400 || resp.status == 413 ||
               resp.status == 415 || resp.status == 422) {
        char bad[1800];
        snprintf(bad, sizeof bad, "%s/%s", cfg->bad_dir, name);
        rename(path, bad);
        LOG_WARN("server rejected %s as invalid (HTTP %d: %.160s), moved to bad/",
                 name, resp.status, resp.body ? resp.body : "");
        if (g_echo) printf("BAD     %s (HTTP %d)\n", name, resp.status);
        result = SEND_BAD;
    } else {
        LOG_WARN("server HTTP %d for %s (%.160s) - will retry",
                 resp.status, name, resp.body ? resp.body : "");
        if (g_echo) printf("RETRY   %s (HTTP %d %.120s)\n", name, resp.status,
                           resp.body ? resp.body : "");
        result = SEND_RETRY;
    }
    http_response_free(&resp);
    return result;
}

/* One pass over the queue. Returns number of files still needing retry. */
static int drain_once(const cfg_t *cfg)
{
    struct dirent **list = NULL;
    int n = scandir(cfg->queue_dir, &list, q_filter, alphasort);
    if (n <= 0) {
        free(list);
        if (g_echo) printf("queue empty\n");
        return 0;
    }
    int pending = 0, transport_fails = 0;
    for (int i = 0; i < n && g_run; i++) {
        send_result r = process_file(cfg, list[i]->d_name);
        if (r == SEND_RETRY) {
            pending++;
            if (++transport_fails >= 3) {   /* endpoint clearly down: stop the pass */
                pending += n - i - 1;
                break;
            }
        } else {
            transport_fails = 0;
        }
    }
    for (int i = 0; i < n; i++) free(list[i]);
    free(list);
    return pending;
}

static void *sender_main(void *arg)
{
    const cfg_t *cfg = arg;
    int backoff = 0;
    while (g_run) {
        struct dirent **list = NULL;
        int n = scandir(cfg->queue_dir, &list, q_filter, alphasort);
        if (n <= 0) {
            free(list);
            pthread_mutex_lock(&g_qmx);
            struct timespec ts;
            clock_gettime(CLOCK_REALTIME, &ts);
            ts.tv_sec += 10;
            pthread_cond_timedwait(&g_qcv, &g_qmx, &ts);
            pthread_mutex_unlock(&g_qmx);
            continue;
        }
        int retry = 0;
        for (int i = 0; i < n && g_run; i++) {
            send_result r = process_file(cfg, list[i]->d_name);
            if (r == SEND_OK) backoff = 0;
            else if (r == SEND_RETRY) { retry = 1; break; }
        }
        for (int i = 0; i < n; i++) free(list[i]);
        free(list);
        if (retry && g_run) {
            backoff = backoff < 7 ? backoff + 1 : 7;
            int wait_s = 5 << (backoff - 1);           /* 5,10,20,40,80,160,300 */
            if (wait_s > 300) wait_s = 300;
            LOG_WARN("STT endpoint unavailable; audio kept in queue, retry in %d s", wait_s);
            sleep_checked(wait_s * 10);
        }
    }
    return NULL;
}

/* ---------------- capture + VAD + segmentation ---------------- */

static int finalize_segment(const cfg_t *cfg, const int16_t *seg, size_t len,
                            double sumsq, int *count)
{
    if (len == 0) return 0;
    double dur_ms = (double)len * 1000.0 / AM_RATE;
    /* segment includes ~300 ms preroll + ~hangover of tail silence */
    if (dur_ms < (double)cfg->min_speech_ms + 600.0) {
        LOG_DBG("segment too short (%.0f ms), dropped", dur_ms);
        return 0;
    }
    double rms = 0.0;
    if (len > 0) {
        double m = sumsq / (double)len;
        rms = m > 0 ? __builtin_sqrt(m) : 0;
    }
    if (rms < cfg->rms_gate) {
        LOG_INFO("segment below energy gate (rms %.4f < %.4f), dropped", rms, cfg->rms_gate);
        return 0;
    }
    if (enqueue_segment(cfg, seg, len, (float)rms) == 0) {
        (*count)++;
        return 1;
    }
    return 0;
}

static int run_capture(const cfg_t *cfg, int once_seconds, const char *wav_path)
{
    vad_t vad;
    int16_t frame[AM_FRAME_SAMPLES];
    int16_t pre[PREROLL_FRAMES][AM_FRAME_SAMPLES];
    int pre_n = 0, pre_head = 0;

    size_t max_samples = (size_t)cfg->max_segment_ms * AM_RATE / 1000;
    int16_t *seg = malloc(max_samples * sizeof(int16_t));
    if (!seg) { LOG_ERR("oom"); return 1; }
    size_t seg_len = 0;
    double seg_sumsq = 0;
    int in_seg = 0;
    int segments = 0;
    uint64_t frames_total = 0;
    uint64_t frames_limit = once_seconds > 0
        ? (uint64_t)once_seconds * 1000 / AM_FRAME_MS : 0;

    audio_src *src = NULL;
    while (g_run) {
        if (!src) {
            char err[512];
            src = wav_path
                ? audio_open_wav(wav_path, err, sizeof err)
                : audio_open_pulse(cfg->device[0] ? cfg->device : NULL, err, sizeof err);
            if (!src) {
                if (wav_path) { LOG_ERR("%s", err); free(seg); return 1; }
                LOG_WARN("capture open failed (%s); retrying in 15 s", err);
                sleep_checked(150);
                continue;
            }
            LOG_INFO("capture open: %s @ %d Hz mono, frame %d ms", audio_desc(src),
                     AM_RATE, AM_FRAME_MS);
            vad_init(&vad, AM_FRAME_MS, cfg->hangover_ms);
            vad.abs_open = (float)cfg->open_rms;
            pre_n = 0; pre_head = 0;
        }

        int r = audio_read(src, frame, AM_FRAME_SAMPLES);
        if (r < 0) {
            LOG_WARN("capture read error; reopening source");
            if (in_seg) {
                finalize_segment(cfg, seg, seg_len, seg_sumsq, &segments);
                in_seg = 0; seg_len = 0; seg_sumsq = 0;
            }
            audio_close(src);
            src = NULL;
            sleep_checked(20);
            continue;
        }
        if (r == 0) break;   /* wav EOF */
        frames_total++;

        int jo = 0, jc = 0;
        vad_process(&vad, frame, AM_FRAME_SAMPLES, &jo, &jc);

        if (!in_seg) {
            memcpy(pre[pre_head], frame, sizeof frame);
            pre_head = (pre_head + 1) % PREROLL_FRAMES;
            if (pre_n < PREROLL_FRAMES) pre_n++;
            if (jo) {
                in_seg = 1;
                seg_len = 0;
                seg_sumsq = 0;
                for (int i = 0; i < pre_n; i++) {   /* oldest-first, includes this frame */
                    int idx = (pre_head - pre_n + i + 2 * PREROLL_FRAMES) % PREROLL_FRAMES;
                    memcpy(seg + seg_len, pre[idx], sizeof frame);
                    for (int k = 0; k < AM_FRAME_SAMPLES; k++) {
                        double s = pre[idx][k] / 32768.0;
                        seg_sumsq += s * s;
                    }
                    seg_len += AM_FRAME_SAMPLES;
                }
                LOG_DBG("VAD open (rms %.4f zcr %.3f floor %.4f)",
                        vad.last_rms, vad.last_zcr, vad.noise_floor);
            }
        } else {
            if (seg_len + AM_FRAME_SAMPLES <= max_samples) {
                memcpy(seg + seg_len, frame, sizeof frame);
                for (int k = 0; k < AM_FRAME_SAMPLES; k++) {
                    double s = frame[k] / 32768.0;
                    seg_sumsq += s * s;
                }
                seg_len += AM_FRAME_SAMPLES;
            }
            int force_split = seg_len + AM_FRAME_SAMPLES > max_samples;
            if (jc || force_split) {
                finalize_segment(cfg, seg, seg_len, seg_sumsq, &segments);
                seg_len = 0;
                seg_sumsq = 0;
                pre_n = 0;
                pre_head = 0;
                if (force_split && !jc) {
                    LOG_DBG("max segment length reached, splitting");
                    /* still talking: stay open, next frames start a new segment */
                } else {
                    in_seg = 0;
                    LOG_DBG("VAD close");
                }
            }
        }

        if (frames_limit && frames_total >= frames_limit) break;
    }

    if (in_seg && seg_len > 0)   /* flush trailing open segment (EOF / shutdown) */
        finalize_segment(cfg, seg, seg_len, seg_sumsq, &segments);
    if (src) audio_close(src);
    free(seg);
    LOG_INFO("capture done: %llu frames (%.1f s), %d segment(s) queued",
             (unsigned long long)frames_total,
             (double)frames_total * AM_FRAME_MS / 1000.0, segments);
    return 0;
}

/* ---------------- config / main ---------------- */

static void usage(void)
{
    printf(
"alma-micd - ALMA always-on mic -> fleet STT daemon\n"
"\n"
"usage: alma-micd [options]\n"
"  (no mode)          run as daemon: capture forever, queue + send utterances\n"
"  --list-devices     list PipeWire/Pulse capture sources and exit\n"
"  --once N           capture N seconds, send queued segments once, exit\n"
"  --wav FILE         feed a 16 kHz mono PCM16 WAV through the identical\n"
"                     VAD->segment->send path instead of the mic, then exit\n"
"  --flush            one pass over the disk queue, then exit\n"
"\n"
"  --server URL       STT base URL (default http://<tailnet-ip>:8844,\n"
"                     env ALMA_MIC_SERVER)\n"
"  --language L       he | en | auto (default he, env ALMA_MIC_LANGUAGE)\n"
"  --device NAME      Pulse source name (default: default source,\n"
"                     env ALMA_MIC_DEVICE)\n"
"  --queue-dir DIR    default ~/.local/share/alma-micd/queue\n"
"  --transcripts F    default ~/.local/share/alma-micd/transcripts.jsonl\n"
"  --hangover-ms N    silence to close an utterance (default 800)\n"
"  --min-speech-ms N  minimum speech to keep a segment (default 350)\n"
"  --max-segment-ms N split cap, server max is 30000 (default 28000)\n"
"  --open-rms F       absolute VAD open threshold (default 0.006)\n"
"  --rms-gate F       drop finished segments quieter than this (default 0.010)\n"
"  --verbose          debug logging\n");
}

int main(int argc, char **argv)
{
    cfg_t cfg;
    memset(&cfg, 0, sizeof cfg);
    const char *home = getenv("HOME");
    if (!home) home = "/tmp";
    const char *ev;
    snprintf(cfg.server, sizeof cfg.server, "%s",
             (ev = getenv("ALMA_MIC_SERVER")) && *ev ? ev : "http://<tailnet-ip>:8844");
    snprintf(cfg.language, sizeof cfg.language, "%s",
             (ev = getenv("ALMA_MIC_LANGUAGE")) && *ev ? ev : "he");
    snprintf(cfg.device, sizeof cfg.device, "%s",
             (ev = getenv("ALMA_MIC_DEVICE")) ? ev : "");
    snprintf(cfg.queue_dir, sizeof cfg.queue_dir, "%s/.local/share/alma-micd/queue", home);
    snprintf(cfg.transcripts, sizeof cfg.transcripts,
             "%s/.local/share/alma-micd/transcripts.jsonl", home);
    cfg.hangover_ms = 800;
    cfg.min_speech_ms = 350;
    cfg.max_segment_ms = 28000;
    cfg.open_rms = 0.006;
    cfg.rms_gate = 0.010;

    int mode_list = 0, mode_flush = 0, once_seconds = 0;
    const char *wav_path = NULL;

    for (int i = 1; i < argc; i++) {
        const char *a = argv[i];
        if (!strcmp(a, "--list-devices")) mode_list = 1;
        else if (!strcmp(a, "--flush")) mode_flush = 1;
        else if (!strcmp(a, "--once") && i + 1 < argc) once_seconds = atoi(argv[++i]);
        else if (!strcmp(a, "--wav") && i + 1 < argc) wav_path = argv[++i];
        else if (!strcmp(a, "--server") && i + 1 < argc)
            snprintf(cfg.server, sizeof cfg.server, "%s", argv[++i]);
        else if (!strcmp(a, "--language") && i + 1 < argc)
            snprintf(cfg.language, sizeof cfg.language, "%s", argv[++i]);
        else if (!strcmp(a, "--device") && i + 1 < argc)
            snprintf(cfg.device, sizeof cfg.device, "%s", argv[++i]);
        else if (!strcmp(a, "--queue-dir") && i + 1 < argc)
            snprintf(cfg.queue_dir, sizeof cfg.queue_dir, "%s", argv[++i]);
        else if (!strcmp(a, "--transcripts") && i + 1 < argc)
            snprintf(cfg.transcripts, sizeof cfg.transcripts, "%s", argv[++i]);
        else if (!strcmp(a, "--hangover-ms") && i + 1 < argc) cfg.hangover_ms = atoi(argv[++i]);
        else if (!strcmp(a, "--min-speech-ms") && i + 1 < argc) cfg.min_speech_ms = atoi(argv[++i]);
        else if (!strcmp(a, "--max-segment-ms") && i + 1 < argc) cfg.max_segment_ms = atoi(argv[++i]);
        else if (!strcmp(a, "--open-rms") && i + 1 < argc) cfg.open_rms = atof(argv[++i]);
        else if (!strcmp(a, "--rms-gate") && i + 1 < argc) cfg.rms_gate = atof(argv[++i]);
        else if (!strcmp(a, "--verbose") || !strcmp(a, "-v")) cfg.verbose = 1;
        else if (!strcmp(a, "--help") || !strcmp(a, "-h")) { usage(); return 0; }
        else { fprintf(stderr, "unknown option: %s (see --help)\n", a); return 2; }
    }
    if (cfg.max_segment_ms > 29000) cfg.max_segment_ms = 29000;   /* server caps at 30 s */
    snprintf(cfg.bad_dir, sizeof cfg.bad_dir, "%s/bad", cfg.queue_dir);

    log_init(cfg.verbose);

    if (mode_list) return audio_list_devices();

    if (parse_http_url(cfg.server, cfg.host, sizeof cfg.host, &cfg.port) != 0) {
        LOG_ERR("bad --server URL (want http://host:port): %s", cfg.server);
        return 2;
    }
    if (mkdirs(cfg.queue_dir) != 0 || mkdirs(cfg.bad_dir) != 0) {
        LOG_ERR("cannot create queue dir %s", cfg.queue_dir);
        return 1;
    }

    struct sigaction sa;
    memset(&sa, 0, sizeof sa);
    sa.sa_handler = on_signal;
    sigaction(SIGTERM, &sa, NULL);
    sigaction(SIGINT, &sa, NULL);
    signal(SIGPIPE, SIG_IGN);

    if (mode_flush) {
        g_echo = 1;
        int pending = drain_once(&cfg);
        if (pending) printf("%d segment(s) still queued\n", pending);
        return pending ? 1 : 0;
    }

    LOG_INFO("alma-micd starting: server %s (lang %s), device %s, queue %s",
             cfg.server, cfg.language, cfg.device[0] ? cfg.device : "(default)",
             cfg.queue_dir);

    if (once_seconds > 0 || wav_path) {
        g_echo = 1;
        int rc = run_capture(&cfg, once_seconds, wav_path);
        if (rc == 0) {
            int pending = drain_once(&cfg);
            if (pending) printf("%d segment(s) left in queue for retry\n", pending);
        }
        return rc;
    }

    /* daemon mode */
    pthread_t sender;
    if (pthread_create(&sender, NULL, sender_main, &cfg) != 0) {
        LOG_ERR("cannot start sender thread");
        return 1;
    }
    run_capture(&cfg, 0, NULL);
    g_run = 0;
    pthread_mutex_lock(&g_qmx);
    pthread_cond_broadcast(&g_qcv);
    pthread_mutex_unlock(&g_qmx);
    pthread_join(sender, NULL);
    LOG_INFO("alma-micd stopped");
    return 0;
}
