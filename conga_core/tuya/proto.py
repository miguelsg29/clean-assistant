"""Protocolo local de Tuya (puerto TCP 6668), versiones 3.3 y 3.4, sin tinytuya.

Trama 55AA:  prefijo 000055AA | seq | cmd | longitud | [retcode] payload | CRC32 o HMAC | 0000AA99
  - 3.3: payload cifrado AES-128-ECB con la local key; CRC32 de cabecera+payload.
  - 3.4: primero se negocia una clave de sesión (cmd 3/4/5) y luego todo va cifrado con ella;
    HMAC-SHA256 en lugar de CRC32. Las órdenes son CONTROL_NEW (13) y las consultas DP_QUERY_NEW (16).
El robot manda sus cambios por su cuenta (cmd 8, STATUS) en cuanto ocurren: no hace falta sondear.
Basado en la documentación pública de tinytuya (github.com/jasonacox/tinytuya).
"""
from __future__ import annotations
import binascii
import hashlib
import hmac
import json
import os
import socket
import struct
import threading
import time

PORT = 6668
PREFIX, SUFFIX = 0x000055AA, 0x0000AA99
SESS_KEY_NEG_START, SESS_KEY_NEG_RESP, SESS_KEY_NEG_FINISH = 3, 4, 5
CONTROL, STATUS, HEART_BEAT, DP_QUERY = 7, 8, 9, 10
CONTROL_NEW, DP_QUERY_NEW, UPDATEDPS = 13, 16, 18
# órdenes que no llevan la cabecera de versión («3.3» + 12 bytes) delante del contenido
NO_HEADER = {DP_QUERY, DP_QUERY_NEW, UPDATEDPS, HEART_BEAT,
             SESS_KEY_NEG_START, SESS_KEY_NEG_RESP, SESS_KEY_NEG_FINISH}
HEARTBEAT_S = 10.0
TIMEOUT_S = 6.0


class TuyaError(Exception):
    pass


# ---------------- AES-128-ECB (cryptography) ----------------
def _aes(key: bytes):
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    return Cipher(algorithms.AES(key), modes.ECB())


def encrypt(key: bytes, raw: bytes, pad: bool = True) -> bytes:
    if pad:
        n = 16 - len(raw) % 16
        raw = raw + bytes([n]) * n
    e = _aes(key).encryptor()
    return e.update(raw) + e.finalize()


def decrypt(key: bytes, data: bytes, unpad: bool = True) -> bytes:
    d = _aes(key).decryptor()
    raw = d.update(data) + d.finalize()
    if unpad and raw and 1 <= raw[-1] <= 16 and raw.endswith(bytes([raw[-1]]) * raw[-1]):
        raw = raw[:-raw[-1]]
    return raw


# ---------------- tramas ----------------
def pack(seq: int, cmd: int, payload: bytes, hmac_key: bytes | None = None) -> bytes:
    """Trama 55AA. Con `hmac_key` (3.4) firma con HMAC-SHA256; si no, CRC32 (3.3)."""
    tail = 32 if hmac_key else 4
    head = struct.pack(">4I", PREFIX, seq, cmd, len(payload) + tail + 4)
    if hmac_key:
        sig = hmac.new(hmac_key, head + payload, hashlib.sha256).digest()
    else:
        sig = struct.pack(">I", binascii.crc32(head + payload) & 0xFFFFFFFF)
    return head + payload + sig + struct.pack(">I", SUFFIX)


def unpack(buf: bytes, hmac_key: bytes | None = None):
    """Primera trama completa de `buf` -> ((seq, cmd, retcode, payload), resto), o (None, buf) si
    aún no ha llegado entera. Descarta basura hasta el prefijo."""
    start = buf.find(struct.pack(">I", PREFIX))
    if start < 0:
        return None, b""
    buf = buf[start:]
    if len(buf) < 16:
        return None, buf
    _, seq, cmd, length = struct.unpack(">4I", buf[:16])
    if len(buf) < 16 + length:
        return None, buf
    body, rest = buf[16:16 + length], buf[16 + length:]
    tail = 32 if hmac_key else 4
    data = body[:-(tail + 4)]
    if hmac_key:
        sig = hmac.new(hmac_key, buf[:16] + data, hashlib.sha256).digest()
        if sig != body[-(tail + 4):-4]:
            raise TuyaError("HMAC incorrecto (¿local key equivocada?)")
    retcode = None
    if len(data) >= 4 and struct.unpack(">I", data[:4])[0] & 0xFFFFFF00 == 0:
        retcode, data = struct.unpack(">I", data[:4])[0], data[4:]
    return (seq, cmd, retcode, data), rest


class TuyaDevice:
    """Conexión persistente con un dispositivo Tuya. `on_dps(dict)` recibe cada cambio de DPs
    (también la respuesta a la consulta inicial); `on_link(bool)` cuando conecta o se cae."""

    def __init__(self, dev_id: str, host: str, local_key: str, version: str = "3.3",
                 port: int = PORT, on_dps=None, on_link=None, log=print):
        self.dev_id, self.host, self.port = dev_id, host, port
        self.key = local_key.encode("latin-1")
        self.version = str(version or "3.3")
        self.on_dps, self.on_link, self.log = on_dps, on_link, log
        self.connected = False
        self._sock = None
        self._seq = 1
        self._lock = threading.Lock()
        self._session = None           # clave de sesión (3.4)
        self._buf = b""

    @property
    def v34(self) -> bool:
        return self.version >= "3.4"

    # ---------------- conexión ----------------
    def connect(self):
        if self.version >= "3.5":
            raise TuyaError(f"protocolo Tuya {self.version} aún no soportado (solo 3.3 y 3.4)")
        s = socket.create_connection((self.host, self.port), timeout=TIMEOUT_S)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        self._sock, self._buf, self._session = s, b"", None
        if self.v34:
            self._negotiate()
        self.connected = True
        self._fire(self.on_link, True)
        self.query()

    def close(self):
        was = self.connected
        self.connected = False
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
        self._sock = None
        if was:
            self._fire(self.on_link, False)

    def _negotiate(self):
        """3.4: clave de sesión = AES(local_key, nonce_local XOR nonce_remoto)."""
        local_nonce = os.urandom(16)
        self._send_raw(SESS_KEY_NEG_START, encrypt(self.key, local_nonce), hmac_key=self.key)
        frame = self._read_frame(hmac_key=self.key)
        if not frame or frame[1] != SESS_KEY_NEG_RESP:
            raise TuyaError("el robot no respondió a la negociación de sesión 3.4 (¿local key o versión equivocadas?)")
        resp = decrypt(self.key, frame[3])
        remote_nonce, proof = resp[:16], resp[16:48]
        if proof != hmac.new(self.key, local_nonce, hashlib.sha256).digest():
            raise TuyaError("local key incorrecta (la negociación 3.4 no cuadra)")
        self._send_raw(SESS_KEY_NEG_FINISH,
                       encrypt(self.key, hmac.new(self.key, remote_nonce, hashlib.sha256).digest()),
                       hmac_key=self.key)
        xored = bytes(a ^ b for a, b in zip(local_nonce, remote_nonce))
        self._session = encrypt(self.key, xored, pad=False)[:16]

    # ---------------- envío ----------------
    def _cipher_key(self) -> bytes:
        return self._session or self.key

    def _send_raw(self, cmd: int, payload: bytes, hmac_key: bytes | None = None):
        with self._lock:
            if not self._sock:
                raise TuyaError("sin conexión")
            self._seq += 1
            self._sock.sendall(pack(self._seq, cmd, payload, hmac_key))

    def _send(self, cmd: int, obj: dict):
        raw = json.dumps(obj, separators=(",", ":")).encode()
        header = self.version.encode() + b"\0" * 12
        if self.v34:
            if cmd not in NO_HEADER:
                raw = header + raw
            self._send_raw(cmd, encrypt(self._session, raw), hmac_key=self._session)
        else:
            payload = encrypt(self.key, raw)
            if cmd not in NO_HEADER:
                payload = header + payload
            self._send_raw(cmd, payload)

    def query(self):
        if self.v34:
            self._send(DP_QUERY_NEW, {})
        else:
            t = str(int(time.time()))
            self._send(DP_QUERY, {"gwId": self.dev_id, "devId": self.dev_id, "uid": self.dev_id, "t": t})

    def set_dps(self, dps: dict):
        """Cambia uno o varios DPs ({"1": True, "9": "normal"})."""
        dps = {str(k): v for k, v in dps.items()}
        if self.v34:
            self._send(CONTROL_NEW, {"protocol": 5, "t": int(time.time()), "data": {"dps": dps}})
        else:
            self._send(CONTROL, {"devId": self.dev_id, "uid": self.dev_id,
                                 "t": str(int(time.time())), "dps": dps})

    def heartbeat(self):
        self._send(HEART_BEAT, {} if self.v34 else {"gwId": self.dev_id, "devId": self.dev_id})

    # ---------------- recepción ----------------
    def _read_frame(self, hmac_key: bytes | None = None, timeout: float = TIMEOUT_S):
        """Una trama (seq, cmd, retcode, payload) o None si vence el plazo."""
        end = time.time() + timeout
        while True:
            frame, self._buf = unpack(self._buf, hmac_key)
            if frame:
                return frame
            left = end - time.time()
            if left <= 0:
                return None
            self._sock.settimeout(left)
            try:
                chunk = self._sock.recv(4096)
            except socket.timeout:
                return None
            if not chunk:
                raise TuyaError("el robot cerró la conexión")
            self._buf += chunk

    def decode(self, payload: bytes):
        """Contenido de una trama -> dict (JSON) o None (acuse vacío)."""
        if not payload:
            return None
        if not self.v34 and payload[:3] == self.version.encode():
            payload = payload[15:]                   # cabecera de versión (3.3, fuera del cifrado)
        raw = decrypt(self._cipher_key(), payload)
        if raw[:3] in (b"3.3", b"3.4", b"3.5"):
            raw = raw[15:]                           # cabecera de versión (3.4, dentro del cifrado)
        try:
            obj = json.loads(raw.decode("utf-8", "replace"))
        except ValueError:
            text = raw.decode("utf-8", "replace").strip()
            if text:
                self.log(f"  [tuya] respuesta no JSON del robot: {text[:80]}")
            return None
        return obj

    def poll(self, timeout: float = 1.0):
        """Lee lo que haya llegado (hasta `timeout` s) y entrega los DPs a `on_dps`."""
        frame = self._read_frame(self._session if self.v34 else None, timeout)
        if not frame:
            return
        _, cmd, _, payload = frame
        if cmd == HEART_BEAT:
            return
        obj = self.decode(payload)
        if not isinstance(obj, dict):
            return
        dps = obj.get("dps")
        if dps is None and isinstance(obj.get("data"), dict):
            dps = obj["data"].get("dps")
        if dps:
            self._fire(self.on_dps, {str(k): v for k, v in dps.items()})

    @staticmethod
    def _fire(cb, *a):
        if cb:
            try:
                cb(*a)
            except Exception:
                pass
