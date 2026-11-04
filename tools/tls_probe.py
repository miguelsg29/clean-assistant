"""TLS probe: does a robot accept a fake cloud server?

Pretends to be the manufacturer's cloud with a certificate from a FAKE certificate authority and
records, for every connection the robot opens, whether it ACCEPTS the fake certificate (local
control by impersonating the cloud is possible) or REJECTS it (the robot verifies/pins the
certificate).

Usage:
    pip install cryptography
    python tls_probe.py                    # ports 443 8883 8007 5223 + 80
    python tls_probe.py --ports 443 8883   # only some ports

Then point the cloud domains to this computer in your DNS and restart the robot (see issue #24
in github.com/miguelsg29/clean-assistant). Ports below 1024 need admin rights on Linux/macOS
(sudo).

Nothing is sent anywhere: it only listens on your network. The log (tls_probe_log.txt) contains
host names and results; tokens and device ids are masked, but have a look before sharing it.
"""
from __future__ import annotations

import argparse
import datetime
import os
import socket
import ssl
import sys
import tempfile
import threading
import time
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)   # TLS 1.0 a propósito

try:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
except ImportError:
    sys.exit("Missing dependency: run  pip install cryptography  and try again.")

DEFAULT_PORTS = [443, 8883, 8007, 5223]
PLAIN_PORTS = [80]
LOG_FILE = "tls_probe_log.txt"
TMP = tempfile.mkdtemp(prefix="tls_probe_")
_lock = threading.Lock()
_summary: dict[tuple[str, int], dict[str, int]] = {}


def log(msg: str):
    line = f"{datetime.datetime.now():%H:%M:%S} {msg}"
    with _lock:
        print(line, flush=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def count(name: str, port: int, result: str):
    with _lock:
        _summary.setdefault((name, port), {}).setdefault(result, 0)
        _summary[(name, port)][result] += 1


def mask(s: str) -> str:
    return s if len(s) <= 4 else s[:2] + "*" * (len(s) - 4) + s[-2:]


# ---------------- fake certificate authority ----------------
def _key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _name(cn):
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])


NOW = datetime.datetime.now(datetime.timezone.utc)
CA_KEY = _key()
CA_CERT = (x509.CertificateBuilder()
           .subject_name(_name("Clean Assistant TLS probe CA")).issuer_name(_name("Clean Assistant TLS probe CA"))
           .public_key(CA_KEY.public_key()).serial_number(x509.random_serial_number())
           .not_valid_before(NOW - datetime.timedelta(days=1)).not_valid_after(NOW + datetime.timedelta(days=3650))
           .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
           .sign(CA_KEY, hashes.SHA256()))
_contexts: dict[str, ssl.SSLContext] = {}


def context_for(host: str) -> ssl.SSLContext:
    """Certificate for exactly the name the robot asked for (SNI), signed by the fake CA: if the
    robot rejects it, it's because of who signed it, not because of the name."""
    host = host or "localhost"
    with _lock:
        if host in _contexts:
            return _contexts[host]
    key = _key()
    cert = (x509.CertificateBuilder()
            .subject_name(_name(host)).issuer_name(CA_CERT.subject)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(NOW - datetime.timedelta(days=1)).not_valid_after(NOW + datetime.timedelta(days=825))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(host)]), critical=False)
            .sign(CA_KEY, hashes.SHA256()))
    path = os.path.join(TMP, f"{abs(hash(host))}.pem")
    with open(path, "wb") as f:
        f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
                                  serialization.NoEncryption()))
        f.write(cert.public_bytes(serialization.Encoding.PEM))
        f.write(CA_CERT.public_bytes(serialization.Encoding.PEM))
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1           # old robots may still use TLS 1.0/1.1
    try:
        ctx.set_ciphers("ALL:@SECLEVEL=0")
    except ssl.SSLError:
        pass
    ctx.load_cert_chain(path)
    with _lock:
        _contexts[host] = ctx
    return ctx


# ---------------- what the robot sends after the handshake (masked) ----------------
def describe(data: bytes) -> str:
    if not data:
        return "no data"
    if data[0] >> 4 == 1 and len(data) > 10 and data[4:8] in (b"MQTT", b"MQIs"):   # MQTT CONNECT
        try:
            i = 1
            while data[i] & 0x80:
                i += 1
            i += 1
            plen = int.from_bytes(data[i:i + 2], "big")
            i += 2 + plen + 1 + 1 + 2
            clen = int.from_bytes(data[i:i + 2], "big")
            client_id = data[i + 2:i + 2 + clen].decode("utf-8", "replace")
            return f"MQTT CONNECT (client id {mask(client_id)})"
        except Exception:
            return "MQTT CONNECT"
    text = data[:200].decode("latin-1")
    first = text.split("\r\n", 1)[0]
    if first.split(" ")[0] in ("GET", "POST", "PUT", "HEAD", "DELETE", "PATCH"):
        method, _, rest = first.partition(" ")
        path = rest.split(" ")[0].split("?")[0]
        return f"HTTP {method} {path}"
    if text.startswith("<"):
        return "XMPP/XML"
    return f"{len(data)} bytes of an unknown protocol"


# ---------------- servers ----------------
def _on_sni(sslobj, server_name, _ctx):
    sslobj.probe_sni = server_name or ""             # se guarda en la propia conexión
    sslobj.context = context_for(server_name or "localhost")


def handle_tls(conn: socket.socket, addr, port: int):
    base = context_for("localhost")
    base.sni_callback = _on_sni
    conn.settimeout(15)
    try:
        tls = base.wrap_socket(conn, server_side=True, do_handshake_on_connect=False)
        tls.probe_sni = ""
        try:
            tls.do_handshake()
        except ssl.SSLError as e:
            reason = (getattr(e, "reason", None) or str(e)).lower()
            name = tls.probe_sni or "(no name)"
            if any(k in reason for k in ("unknown_ca", "unknown ca", "bad_certificate", "bad certificate",
                                         "certificate_unknown", "certificate unknown", "decrypt_error")):
                log(f"REJECTED  {addr[0]} -> {name}:{port}  the robot does NOT accept the fake certificate ({reason})")
                count(name, port, "rejected")
            else:
                log(f"FAILED    {addr[0]} -> {name}:{port}  handshake error: {reason}")
                count(name, port, "failed")
            return
        except (ConnectionResetError, ConnectionAbortedError, socket.timeout, OSError) as e:
            name = tls.probe_sni or "(no name)"
            log(f"CLOSED    {addr[0]} -> {name}:{port}  the robot hung up during the handshake "
                f"(usually means it rejected the certificate): {type(e).__name__}")
            count(name, port, "closed")
            return
        name = tls.probe_sni or "(no name)"
        log(f"ACCEPTED  {addr[0]} -> {name}:{port}  the robot accepted the FAKE certificate "
            f"({tls.version()})")
        count(name, port, "ACCEPTED")
        try:
            data = tls.recv(4096)
        except (OSError, ssl.SSLError):
            data = b""
        log(f"          first message: {describe(data)}")
        tls.close()
    finally:
        try:
            conn.close()
        except OSError:
            pass


def handle_plain(conn: socket.socket, addr, port: int):
    conn.settimeout(10)
    try:
        data = conn.recv(4096)
    except OSError:
        data = b""
    host = ""
    for line in data.decode("latin-1").split("\r\n"):
        if line.lower().startswith("host:"):
            host = line.split(":", 1)[1].strip()
    log(f"PLAIN     {addr[0]} -> {host or '(no host)'}:{port}  {describe(data)}")
    count(host or "(no host)", port, "plain")
    try:
        conn.sendall(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
    except OSError:
        pass
    conn.close()


def serve(port: int, handler):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("0.0.0.0", port))
    except OSError as e:
        log(f"!! cannot listen on port {port}: {e}  (in use, or needs admin/sudo)")
        return
    s.listen(16)
    log(f"listening on port {port}")
    while True:
        conn, addr = s.accept()
        threading.Thread(target=handler, args=(conn, addr, port), daemon=True).start()


def print_summary():
    print("\n===== SUMMARY =====")
    if not _summary:
        print("No connections. Is the robot using your DNS, and does it point the cloud domains to "
              "this computer? Check the DNS query log for the robot's IP.")
    for (name, port), res in sorted(_summary.items()):
        print(f"  {name}:{port}  " + ", ".join(f"{k}={v}" for k, v in sorted(res.items())))
    if any("ACCEPTED" in r for r in _summary.values()):
        print("=> The robot ACCEPTS a fake cloud: local control is possible.")
    elif any(k in r for r in _summary.values() for k in ("rejected", "closed")):
        print("=> The robot REJECTS the fake cloud on every connection seen.")
    print(f"Full log: {os.path.abspath(LOG_FILE)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--ports", type=int, nargs="+", default=DEFAULT_PORTS, help="TLS ports to listen on")
    ap.add_argument("--plain", type=int, nargs="*", default=PLAIN_PORTS, help="plain-text ports to log")
    args = ap.parse_args()
    ip = "?"
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as u:
            u.connect(("192.0.2.1", 9))            # no traffic is sent; just picks the LAN interface
            ip = u.getsockname()[0]
    except OSError:
        pass
    log(f"TLS probe started. This computer's IP: {ip}  (point the cloud domains here)")
    for p in args.ports:
        threading.Thread(target=serve, args=(p, handle_tls), daemon=True).start()
    for p in args.plain:
        threading.Thread(target=serve, args=(p, handle_plain), daemon=True).start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print_summary()


if __name__ == "__main__":
    main()
