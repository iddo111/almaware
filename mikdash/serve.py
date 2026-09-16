# -*- coding: utf-8 -*-
"""
Serve the MIKDASH walkthrough.

    http://127.0.0.1:8875/          desktop check (localhost is already a secure
                                    context, so WebXR works here too)
    https://<tailnet-ip>:8876/     for the Quest, over Tailscale

WebXR REFUSES to start outside a secure context, and plain http:// to an IP is not
one. That is why the second socket exists. The certificate is self-signed and made
here on this machine; the Quest browser will show one warning that must be accepted
once per device. Nothing is sent anywhere to obtain it.

Runs BELOW_NORMAL: nothing on this PC may compete with Iddo's live microphone.
"""
from __future__ import annotations
import http.server, os, ssl, socket, sys, threading, datetime, ipaddress

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(HERE, "web")
CERT = os.path.join(HERE, "cert.pem")
KEY = os.path.join(HERE, "key.pem")
HTTP_PORT, HTTPS_PORT = 8875, 8876
TS_IP = "<tailnet-ip>"


def make_cert():
    if os.path.exists(CERT) and os.path.exists(KEY):
        return
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "mikdash.local")])
    san = x509.SubjectAlternativeName([
        x509.DNSName("localhost"),
        x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
        x509.IPAddress(ipaddress.ip_address(TS_IP)),
    ])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder()
            .subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=825))
            .add_extension(san, critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .sign(key, hashes.SHA256()))
    with open(KEY, "wb") as f:
        f.write(key.private_bytes(serialization.Encoding.PEM,
                                  serialization.PrivateFormat.TraditionalOpenSSL,
                                  serialization.NoEncryption()))
    with open(CERT, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    print(f"made a self-signed certificate for localhost / 127.0.0.1 / {TS_IP}")


class H(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                      ".js": "application/javascript", ".json": "application/json",
                      ".html": "text/html; charset=utf-8"}

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=WEB, **kw)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):
        pass          # the console stays quiet; this runs beside a live mic


class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def run(port, tls):
    srv = Server(("0.0.0.0", port), H)
    if tls:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(CERT, KEY)
        srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    srv.serve_forever()


def main():
    try:
        import psutil
        psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        print("priority: BELOW_NORMAL")
    except Exception as e:
        print(f"priority: could not lower ({e})")

    make_cert()
    threading.Thread(target=run, args=(HTTPS_PORT, True), daemon=True).start()
    print(f"  desktop   http://127.0.0.1:{HTTP_PORT}/")
    print(f"  Quest    https://{TS_IP}:{HTTPS_PORT}/   (accept the certificate warning once)")
    run(HTTP_PORT, False)


if __name__ == "__main__":
    main()
