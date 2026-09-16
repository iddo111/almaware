#ifndef ALMA_HTTP_H
#define ALMA_HTTP_H
#include <stddef.h>

typedef struct {
    int status;        /* HTTP status code */
    char *body;        /* malloc'd, NUL-terminated; free with http_response_free */
    size_t body_len;
} http_response;

/* Parse "http://host[:port][/...]" -> host + port (default 80). 0 ok, -1 bad. */
int parse_http_url(const char *url, char *host, size_t hostsz, int *port);

/* One-shot HTTP/1.1 POST with Content-Type: application/octet-stream and the
 * ALMA-STT X-ALMA-Sample-Rate: 16000 header. Returns 0 on transport success
 * (resp->status valid), -1 on transport failure (err filled). */
int http_post_octet(const char *host, int port, const char *path,
                    const void *body, size_t body_len,
                    int connect_timeout_ms, int io_timeout_ms,
                    http_response *resp, char *err, size_t errsz);

void http_response_free(http_response *r);

#endif
