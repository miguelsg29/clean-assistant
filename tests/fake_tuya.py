"""Robot Tuya simulado (lado dispositivo, protocolos 3.3 y 3.4) con los DPs reales del Conga 8290
de @ftorrealbaa (#8). Reacciona a las órdenes como en su registro: 1=True -> smart, 2 -> pausa, ..."""
import hashlib, hmac, json, os, socket, struct, sys, threading, time
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from conga_core.tuya import proto as P

DEV_ID, KEY = "bf0123456789abcdefgh", "0123456789abcdef"
BASE = {"1": False, "2": False, "3": True, "4": "smart", "5": "charge_done", "6": 45, "7": 39, "8": 100,
        "9": "normal", "10": "close", "17": -15771, "19": -16659, "21": -15771, "23": 6395, "25": False,
        "26": 80, "27": True, "28": 0, "29": 29845, "30": 790, "31": 34659, "37": 1, "38": False,
        "39": False, "40": "none", "41": "both_work", "44": "adaptive", "45": True, "47": False,
        "53": "normal", "101": False, "104": False, "105": "auto", "108": True, "120": "allow_play",
        "128": "20", "146": False}


class FakeTuya:
    def __init__(self, version="3.3", key=KEY):
        self.version, self.key = version, key.encode()
        self.dps = dict(BASE)
        self.received = []            # DPs recibidos en cada orden
        self.srv = socket.socket(); self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind(("127.0.0.1", 0)); self.srv.listen(4)
        self.port = self.srv.getsockname()[1]
        self.conns = []
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        while True:
            try:
                c, _ = self.srv.accept()
            except OSError:
                return
            self.conns.append(c)
            threading.Thread(target=self._serve, args=(c,), daemon=True).start()

    def drop(self):
        """Corta las conexiones abiertas. shutdown() avisa al cliente también en Linux, donde un
        close() con otro hilo bloqueado en recv() no manda el FIN."""
        for c in self.conns:
            try: c.shutdown(socket.SHUT_RDWR)
            except OSError: pass
            try: c.close()
            except OSError: pass

    def close(self):
        try: self.srv.shutdown(socket.SHUT_RDWR)
        except OSError: pass
        self.srv.close()
        self.drop()

    def _serve(self, c):
        buf, sess, seq = b"", None, 100
        v34 = self.version >= "3.4"
        def send(cmd, payload, hk=None):
            nonlocal seq; seq += 1
            c.sendall(P.pack(seq, cmd, struct.pack(">I", 0) + payload, hk))
        def push(dps):
            if v34:
                raw = b"3.4" + b"\0" * 12 + json.dumps({"protocol": 4, "t": int(time.time()), "data": {"dps": dps}}).encode()
                send(P.STATUS, P.encrypt(sess, raw), sess)
            else:
                send(P.STATUS, b"3.3" + b"\0" * 12 + P.encrypt(self.key, json.dumps({"devId": DEV_ID, "dps": dps, "t": int(time.time())}).encode()))
        self.push = push
        try:
            while True:
                hk = (sess or self.key) if v34 else None
                frame, buf = P.unpack(buf, hk)
                if not frame:
                    d = c.recv(4096)
                    if not d: return
                    buf += d; continue
                _, cmd, _, payload = frame
                if cmd == P.SESS_KEY_NEG_START:
                    ln = P.decrypt(self.key, payload)
                    self._rn = os.urandom(16)
                    send(P.SESS_KEY_NEG_RESP, P.encrypt(self.key, self._rn + hmac.new(self.key, ln, hashlib.sha256).digest()), self.key)
                    self._ln = ln
                elif cmd == P.SESS_KEY_NEG_FINISH:
                    sess = P.encrypt(self.key, bytes(a ^ b for a, b in zip(self._ln, self._rn)), pad=False)[:16]
                elif cmd in (P.DP_QUERY, P.DP_QUERY_NEW):
                    if v34:
                        send(cmd, P.encrypt(sess, json.dumps({"dps": self.dps}).encode()), sess)
                    else:
                        json.loads(P.decrypt(self.key, payload))      # comprueba que es JSON válido
                        send(cmd, P.encrypt(self.key, json.dumps({"devId": DEV_ID, "dps": self.dps}).encode()))
                elif cmd == P.HEART_BEAT:
                    send(P.HEART_BEAT, b"", sess if v34 else None)
                elif cmd in (P.CONTROL, P.CONTROL_NEW):
                    if v34:
                        raw = P.decrypt(sess, payload); assert raw[:3] == b"3.4"
                        dps = json.loads(raw[15:])["data"]["dps"]
                    else:
                        assert payload[:3] == b"3.3"
                        dps = json.loads(P.decrypt(self.key, payload[15:]))["dps"]
                    self.received.append(dps)
                    send(cmd, b"", sess if v34 else None)            # acuse
                    push(self._react(dps))
        except OSError:
            return

    def _react(self, dps):
        ch = dict(dps)
        if dps.get("1") is True:
            ch.update({"5": "smart", "3": False, "6": 0, "7": 0})
        if "15" in dps:                     # trama 0x59 «empezar» (bordes/espiral), como el 8290 real
            import base64
            b = base64.b64decode(dps["15"])
            if b[6] == 0x59:
                way = {1: "auto", 3: "acrubbing", 5: "espiral"}.get(b[9], "auto")
                ch.update({"4": "smart", "105": way, "5": "smart", "1": True, "3": False, "6": 0, "7": 0})
        if dps.get("2") is True:
            ch["5"] = "paused"
        if dps.get("2") is False and self.dps.get("5") == "paused":
            ch["5"] = "smart"
        if dps.get("3") is True:
            ch.update({"5": "goto_charge", "1": False, "4": "zone"})
        if dps.get("4") == "manual":
            ch["5"] = "manual"
        if dps.get("12") == "exit":
            ch.update({"5": "standby", "4": "smart"})
        for r, life in (("18", "17"), ("20", "19"), ("22", "21"), ("24", "23")):
            if dps.get(r) is True:
                ch[life] = {"17": 9000, "19": 18000, "21": 9000, "23": 9000}[life]
        self.dps.update(ch)
        return ch
