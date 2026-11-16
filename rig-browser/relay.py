# Local-egress CONNECT relay (VM harness only — never production).
# This VM's egress is a TLS-intercepting proxy requiring PREEMPTIVE
# Basic auth, which Chromium refuses (ERR_TUNNEL_CONNECTION_FAILED).
# This relay on loopback adds the auth in-process. The credential is
# read from the ambient proxy env var in-process and never printed
# or stored. Extracted from ladder_before.py so both ladders share it.
import base64, os, socket, threading
from urllib.parse import urlparse


def start_relay(port=18080):
    pu = urlparse(os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY") or "")
    if not pu.hostname:
        return None
    cred = base64.b64encode(f"{pu.username}:{pu.password}".encode()).decode()
    up_addr = (pu.hostname, pu.port)

    def pipe(a, b):
        try:
            while True:
                d = a.recv(65536)
                if not d:
                    break
                b.sendall(d)
        except Exception:
            pass
        try:
            b.shutdown(socket.SHUT_WR)
        except Exception:
            pass

    def handle(c):
        try:
            buf = b""
            while b"\r\n\r\n" not in buf:
                d = c.recv(4096)
                if not d:
                    c.close(); return
                buf += d
            head, rest = buf.split(b"\r\n\r\n", 1)
            parts = head.split(b"\r\n")[0].decode("latin1").split(" ")
            if parts[0].upper() != "CONNECT":
                c.sendall(b"HTTP/1.1 405 Method Not Allowed\r\n\r\n"); c.close(); return
            target = parts[1]
            up = socket.create_connection(up_addr, timeout=15)
            up.sendall((f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n"
                        f"Proxy-Authorization: Basic {cred}\r\n\r\n").encode())
            rbuf = b""
            while b"\r\n\r\n" not in rbuf:
                d = up.recv(4096)
                if not d:
                    c.close(); up.close(); return
                rbuf += d
            if b" 200 " not in rbuf.split(b"\r\n")[0]:
                c.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n"); c.close(); up.close(); return
            c.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            if rest:
                up.sendall(rest)
            threading.Thread(target=pipe, args=(c, up), daemon=True).start()
            pipe(up, c)
            c.close(); up.close()
        except Exception:
            try:
                c.close()
            except Exception:
                pass

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", port)); srv.listen(50)

    def serve():
        while True:
            c, _ = srv.accept()
            threading.Thread(target=handle, args=(c,), daemon=True).start()

    threading.Thread(target=serve, daemon=True).start()
    return f"http://127.0.0.1:{port}"
