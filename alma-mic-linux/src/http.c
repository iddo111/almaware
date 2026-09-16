#define _GNU_SOURCE
#include "http.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <netdb.h>

int parse_http_url(const char *url, char *host, size_t hostsz, int *port)
{
    const char *p = url;
    if (strncmp(p, "http://", 7) != 0) return -1;
    p += 7;
    const char *colon = strchr(p, ':');
    const char *slash = strchr(p, '/');
    size_t hlen;
    *port = 80;
    if (colon && (!slash || colon < slash)) {
        hlen = (size_t)(colon - p);
        *port = atoi(colon + 1);
    } else {
        hlen = slash ? (size_t)(slash - p) : strlen(p);
    }
    if (hlen == 0 || hlen >= hostsz || *port <= 0 || *port > 65535) return -1;
    memcpy(host, p, hlen);
    host[hlen] = 0;
    return 0;
}

static int send_all(int fd, const void *buf, size_t len)
{
    const char *b = buf;
    while (len > 0) {
        ssize_t w = send(fd, b, len, MSG_NOSIGNAL);
        if (w < 0) {
            if (errno == EINTR) continue;
            return -1;
        }
        b += w;
        len -= (size_t)w;
    }
    return 0;
}

int http_post_octet(const char *host, int port, const char *path,
                    const void *body, size_t body_len,
                    int connect_timeout_ms, int io_timeout_ms,
                    http_response *resp, char *err, size_t errsz)
{
    resp->status = 0;
    resp->body = NULL;
    resp->body_len = 0;

    char portstr[16];
    snprintf(portstr, sizeof portstr, "%d", port);
    struct addrinfo hints, *ai = NULL;
    memset(&hints, 0, sizeof hints);
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;
    int rc = getaddrinfo(host, portstr, &hints, &ai);
    if (rc != 0) {
        snprintf(err, errsz, "resolve %s: %s", host, gai_strerror(rc));
        return -1;
    }

    int fd = -1;
    for (struct addrinfo *a = ai; a; a = a->ai_next) {
        fd = socket(a->ai_family, a->ai_socktype | SOCK_NONBLOCK, a->ai_protocol);
        if (fd < 0) continue;
        rc = connect(fd, a->ai_addr, a->ai_addrlen);
        if (rc == 0) break;
        if (errno == EINPROGRESS) {
            struct pollfd pf;
            pf.fd = fd;
            pf.events = POLLOUT;
            rc = poll(&pf, 1, connect_timeout_ms);
            if (rc == 1) {
                int soerr = 0;
                socklen_t sl = sizeof soerr;
                getsockopt(fd, SOL_SOCKET, SO_ERROR, &soerr, &sl);
                if (soerr == 0) break;
                errno = soerr;
            } else if (rc == 0) {
                errno = ETIMEDOUT;
            }
        }
        close(fd);
        fd = -1;
    }
    freeaddrinfo(ai);
    if (fd < 0) {
        snprintf(err, errsz, "connect %s:%d: %s", host, port, strerror(errno));
        return -1;
    }

    /* back to blocking, with I/O timeouts */
    int fl = fcntl(fd, F_GETFL, 0);
    fcntl(fd, F_SETFL, fl & ~O_NONBLOCK);
    struct timeval tv;
    tv.tv_sec = io_timeout_ms / 1000;
    tv.tv_usec = (io_timeout_ms % 1000) * 1000;
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof tv);
    setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof tv);

    char head[1024];
    int hl = snprintf(head, sizeof head,
        "POST %s HTTP/1.1\r\n"
        "Host: %s:%d\r\n"
        "User-Agent: alma-micd/1.0\r\n"
        "Content-Type: application/octet-stream\r\n"
        "X-ALMA-Sample-Rate: 16000\r\n"
        "Content-Length: %zu\r\n"
        "Connection: close\r\n\r\n",
        path, host, port, body_len);
    if (hl <= 0 || hl >= (int)sizeof head) {
        close(fd);
        snprintf(err, errsz, "request header too long");
        return -1;
    }
    if (send_all(fd, head, (size_t)hl) < 0 ||
        send_all(fd, body, body_len) < 0) {
        snprintf(err, errsz, "send: %s", strerror(errno));
        close(fd);
        return -1;
    }

    size_t cap = 16384, len = 0;
    char *buf = malloc(cap);
    if (!buf) {
        close(fd);
        snprintf(err, errsz, "out of memory");
        return -1;
    }
    for (;;) {
        if (len + 4096 > cap) {
            if (cap >= 4u * 1024 * 1024) break;   /* 4 MB response cap */
            cap *= 2;
            char *nb = realloc(buf, cap);
            if (!nb) break;
            buf = nb;
        }
        ssize_t r = recv(fd, buf + len, cap - len - 1, 0);
        if (r < 0) {
            if (errno == EINTR) continue;
            break;
        }
        if (r == 0) break;   /* server closed (Connection: close) */
        len += (size_t)r;
    }
    close(fd);
    buf[len] = 0;
    if (len == 0) {
        free(buf);
        snprintf(err, errsz, "empty response");
        return -1;
    }

    int status = 0;
    if (sscanf(buf, "HTTP/%*s %d", &status) != 1 || status < 100) {
        free(buf);
        snprintf(err, errsz, "malformed status line");
        return -1;
    }
    char *sep = strstr(buf, "\r\n\r\n");
    if (sep) {
        sep += 4;
        resp->body_len = len - (size_t)(sep - buf);
        resp->body = malloc(resp->body_len + 1);
        if (resp->body) {
            memcpy(resp->body, sep, resp->body_len);
            resp->body[resp->body_len] = 0;
        } else {
            resp->body_len = 0;
        }
    }
    resp->status = status;
    free(buf);
    return 0;
}

void http_response_free(http_response *r)
{
    free(r->body);
    r->body = NULL;
    r->body_len = 0;
}
