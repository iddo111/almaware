#ifndef ALMA_UTIL_H
#define ALMA_UTIL_H
#include <stddef.h>
#include <stdint.h>

void log_init(int verbose);
void log_line(int pri, const char *fmt, ...) __attribute__((format(printf, 2, 3)));
#define LOG_ERR(...)  log_line(3, __VA_ARGS__)
#define LOG_WARN(...) log_line(4, __VA_ARGS__)
#define LOG_INFO(...) log_line(6, __VA_ARGS__)
#define LOG_DBG(...)  log_line(7, __VA_ARGS__)

/* Minimal JSON field readers (enough for the flat ALMA-STT response).
 * json_get_string unescapes \n \t \" \\ and \uXXXX (incl. surrogate pairs)
 * into UTF-8, because Python json.dumps ensure_ascii escapes Hebrew. */
int  json_get_string(const char *json, const char *key, char *out, size_t outsz);
int  json_get_double(const char *json, const char *key, double *out);
int  json_get_bool(const char *json, const char *key, int *out);
void json_escape(const char *in, char *out, size_t outsz);

uint64_t now_ms(void);
void iso_utc(char *out, size_t outsz);
int  mkdirs(const char *path);

#endif
