#define _GNU_SOURCE
#include "util.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <time.h>
#include <unistd.h>
#include <sys/stat.h>
#include <errno.h>

static int g_verbose = 0;
static int g_tty = 0;

void log_init(int verbose)
{
    g_verbose = verbose;
    g_tty = isatty(2);
}

void log_line(int pri, const char *fmt, ...)
{
    if (pri >= 7 && !g_verbose) return;
    char msg[2048];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(msg, sizeof msg, fmt, ap);
    va_end(ap);
    if (g_tty) {
        char ts[32];
        struct timespec t;
        clock_gettime(CLOCK_REALTIME, &t);
        struct tm tm;
        localtime_r(&t.tv_sec, &tm);
        strftime(ts, sizeof ts, "%H:%M:%S", &tm);
        static const char *tag[8] = {"", "", "", "ERR ", "WARN", "", "info", "dbg "};
        fprintf(stderr, "%s.%03ld %s %s\n", ts, t.tv_nsec / 1000000, tag[pri & 7], msg);
    } else {
        /* sd-daemon style priority prefix -> journald severity */
        fprintf(stderr, "<%d>%s\n", pri, msg);
    }
    fflush(stderr);
}

uint64_t now_ms(void)
{
    struct timespec t;
    clock_gettime(CLOCK_REALTIME, &t);
    return (uint64_t)t.tv_sec * 1000u + (uint64_t)(t.tv_nsec / 1000000);
}

void iso_utc(char *out, size_t outsz)
{
    time_t t = time(NULL);
    struct tm tm;
    gmtime_r(&t, &tm);
    strftime(out, outsz, "%Y-%m-%dT%H:%M:%SZ", &tm);
}

int mkdirs(const char *path)
{
    char tmp[1024];
    snprintf(tmp, sizeof tmp, "%s", path);
    size_t len = strlen(tmp);
    if (len == 0) return -1;
    for (char *p = tmp + 1; *p; p++) {
        if (*p == '/') {
            *p = 0;
            mkdir(tmp, 0755);
            *p = '/';
        }
    }
    if (mkdir(tmp, 0755) < 0 && errno != EEXIST) return -1;
    return 0;
}

/* ---- JSON helpers ---- */

static const char *find_key(const char *json, const char *key)
{
    char pat[128];
    snprintf(pat, sizeof pat, "\"%s\"", key);
    const char *p = strstr(json, pat);
    if (!p) return NULL;
    p += strlen(pat);
    while (*p == ' ' || *p == '\t' || *p == '\r' || *p == '\n') p++;
    if (*p != ':') return NULL;
    p++;
    while (*p == ' ' || *p == '\t' || *p == '\r' || *p == '\n') p++;
    return p;
}

static size_t utf8_put(char *out, size_t outsz, size_t pos, unsigned cp)
{
    unsigned char b[4];
    int n;
    if (cp < 0x80)        { b[0] = (unsigned char)cp; n = 1; }
    else if (cp < 0x800)  { b[0] = 0xC0 | (cp >> 6); b[1] = 0x80 | (cp & 0x3F); n = 2; }
    else if (cp < 0x10000){ b[0] = 0xE0 | (cp >> 12); b[1] = 0x80 | ((cp >> 6) & 0x3F);
                            b[2] = 0x80 | (cp & 0x3F); n = 3; }
    else                  { b[0] = 0xF0 | (cp >> 18); b[1] = 0x80 | ((cp >> 12) & 0x3F);
                            b[2] = 0x80 | ((cp >> 6) & 0x3F); b[3] = 0x80 | (cp & 0x3F); n = 4; }
    for (int i = 0; i < n; i++)
        if (pos + 1 < outsz) out[pos++] = (char)b[i];
    return pos;
}

static int hex4(const char *p, unsigned *v)
{
    *v = 0;
    for (int i = 0; i < 4; i++) {
        char c = p[i];
        *v <<= 4;
        if (c >= '0' && c <= '9') *v |= (unsigned)(c - '0');
        else if (c >= 'a' && c <= 'f') *v |= (unsigned)(c - 'a' + 10);
        else if (c >= 'A' && c <= 'F') *v |= (unsigned)(c - 'A' + 10);
        else return -1;
    }
    return 0;
}

int json_get_string(const char *json, const char *key, char *out, size_t outsz)
{
    const char *p = find_key(json, key);
    if (!p || *p != '"' || outsz == 0) return -1;
    p++;
    size_t pos = 0;
    while (*p && *p != '"') {
        if (*p == '\\') {
            p++;
            char e = *p;
            if (!e) break;
            p++;
            switch (e) {
            case 'n': if (pos + 1 < outsz) out[pos++] = '\n'; break;
            case 't': if (pos + 1 < outsz) out[pos++] = '\t'; break;
            case 'r': if (pos + 1 < outsz) out[pos++] = '\r'; break;
            case 'b': case 'f': break;
            case 'u': {
                unsigned cp;
                if (hex4(p, &cp) != 0) { out[pos] = 0; return -1; }
                p += 4;
                if (cp >= 0xD800 && cp <= 0xDBFF && p[0] == '\\' && p[1] == 'u') {
                    unsigned lo;
                    if (hex4(p + 2, &lo) == 0 && lo >= 0xDC00 && lo <= 0xDFFF) {
                        cp = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00);
                        p += 6;
                    }
                }
                pos = utf8_put(out, outsz, pos, cp);
                break;
            }
            default:
                if (pos + 1 < outsz) out[pos++] = e;
                break;
            }
        } else {
            if (pos + 1 < outsz) out[pos++] = *p;
            p++;
        }
    }
    out[pos] = 0;
    return 0;
}

int json_get_double(const char *json, const char *key, double *out)
{
    const char *p = find_key(json, key);
    if (!p) return -1;
    char *end;
    double v = strtod(p, &end);
    if (end == p) return -1;
    *out = v;
    return 0;
}

int json_get_bool(const char *json, const char *key, int *out)
{
    const char *p = find_key(json, key);
    if (!p) return -1;
    if (strncmp(p, "true", 4) == 0)  { *out = 1; return 0; }
    if (strncmp(p, "false", 5) == 0) { *out = 0; return 0; }
    return -1;
}

void json_escape(const char *in, char *out, size_t outsz)
{
    size_t pos = 0;
    if (outsz == 0) return;
    for (const unsigned char *p = (const unsigned char *)in; *p; p++) {
        char tmp[8];
        const char *rep = NULL;
        size_t rl = 0;
        if (*p == '"')       { rep = "\\\""; rl = 2; }
        else if (*p == '\\') { rep = "\\\\"; rl = 2; }
        else if (*p == '\n') { rep = "\\n"; rl = 2; }
        else if (*p == '\r') { rep = "\\r"; rl = 2; }
        else if (*p == '\t') { rep = "\\t"; rl = 2; }
        else if (*p < 0x20)  { snprintf(tmp, sizeof tmp, "\\u%04x", *p); rep = tmp; rl = 6; }
        if (rep) {
            if (pos + rl + 1 >= outsz) break;
            memcpy(out + pos, rep, rl);
            pos += rl;
        } else {
            if (pos + 2 >= outsz) break;
            out[pos++] = (char)*p;
        }
    }
    out[pos] = 0;
}
