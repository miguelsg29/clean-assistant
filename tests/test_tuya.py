import base64, json, os, sys, tempfile, time
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fake_tuya as F
from conga_core import commands as cmd
from conga_core.config import RobotConfig
from conga_core.tuya import proto as P
from conga_core.tuya.robot import TuyaRobot, faults, parse_frame, robot_state


def wait(cond, t=5.0):
    end = time.time() + t
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


# ---------- piezas sueltas ----------
assert P.decrypt(b"k" * 16, P.encrypt(b"k" * 16, b"hola")) == b"hola"
fr = P.pack(5, 7, b"abc"); (seq, c, rc, data), rest = P.unpack(fr + b"xx")
assert (seq, c, data, rest) == (5, 7, b"abc", b"xx")
assert P.unpack(fr[:10]) == (None, fr[:10])
fr = P.pack(6, 8, b"\0\0\0\0zz", hmac_key=b"s" * 16); (_, _, rc, data), _ = P.unpack(fr, b"s" * 16)
assert rc == 0 and data == b"zz"
try:
    P.unpack(fr, b"t" * 16); raise SystemExit("HMAC malo aceptado")
except P.TuyaError:
    pass
# tramas byte a byte iguales a las de tinytuya 1.17.4 (la cola es 0000AA55; con AA99 el robot real las ignoraba)
import types
_t = P.time; P.time = types.SimpleNamespace(time=lambda: 1793538124.0)
class _S:
    def sendall(self, b): self.b = b
d = P.TuyaDevice("bf0123456789abcdefgh", "x", "0123456789abcdef", "3.3"); d._sock = _S(); d._seq = 0
d.query()
assert d._sock.b.hex() == ("000055aa000000010000000a00000078a582c52e5a14f42dc57e6b4371d0f7898f84c1b859b79478a8eff0e8"
    "7abb16691d6e826df5b2d248589c9b1fe24d857c4d81a1c5a9ed3374f5bbddd8805697471289985ddcc6ad4334e0f2be9c78211b3257c3855eea"
    "3abd3a03de1f21fbaf5489cddb48e1fc74f4c2461691b531a2e5b0d6d98d0000aa55"), d._sock.b.hex()
d.set_dps({"1": True})
assert d._sock.b.hex().startswith("000055aa000000020000000700000077332e33") and d._sock.b.hex().endswith("0000aa55")
P.time = _t
assert faults(32768) == ["dustbox_out"] and faults(16777216) == ["land_check"] and faults(0) == []
# tramas del registro real: inicio con succión strong (03), agua close (00); limpieza de habitación
assert parse_frame("qgEAAAAJWQAAAQEDAAEAXw==") == (0x59, bytes.fromhex("00 00 01 01 03 00 01 00"))
assert parse_frame(base64.b64encode(bytes.fromhex("aa 01 00 00 00 0a 59 01 01 04 01 01 02 00 01 00 64")).decode())[1][:3] == bytes([1, 1, 4])
assert parse_frame("qgEAAAAJWQAAAQEDAAEAXg==") is None            # suma incorrecta
assert robot_state({"5": "smart"}) == "cleaning" and robot_state({"5": "goto_charge"}) == "returning"
assert robot_state({"5": "charge_done"}) == "docked" and robot_state({"5": "paused", "28": 1 << 20}) == "error"
assert robot_state({"5": "smart", "28": 1}) == "cleaning"              # batería baja: aviso, no error


def run(version):
    dev = F.FakeTuya(version)
    tmp = tempfile.mkdtemp()
    fac = lambda i, h, k, v, port=None, **kw: P.TuyaDevice(i, h, k, v, port=dev.port, **kw)
    logs = []
    r = TuyaRobot(RobotConfig(), logger=logs.append, host="127.0.0.1", dev_id=F.DEV_ID, local_key=F.KEY,
                  version=version, data_dir=tmp, device_factory=fac)
    ups = []; r.on_update = lambda: ups.append(1)
    r.start()
    assert wait(lambda: r.state.online and r.state.battery == 100), (version, logs)
    s = r.state
    assert s.state == "docked" and s.charging and s.fault == 0 and s.area == 39.0 and s.clean_time == 45, s
    assert r.stats == {"time_h": 577.6, "area_m2": 29845, "runs": 790}, r.stats
    # consumibles caducados (minutos negativos) -> más horas de uso que su vida (0 %)
    assert s.consumables["main_brush"] > 300 and s.consumables["dishcloth"] < 160, s.consumables
    assert s.voice == {"voiceMode": 1, "volume": 8} and s.quiet == {"is_open": 0}
    assert json.load(open(os.path.join(tmp, "tuya_link.json")))["ip"] == "127.0.0.1"

    # preferencias y modo -> limpieza completa con todo en una orden
    r.command(cmd.fan("Turbo")); r.command(cmd.water("Bajo")); r.command(cmd.select_mode("Bordes"))
    r.command(cmd.start())
    assert wait(lambda: s.state == "cleaning"), s.state
    assert wait(lambda: dev.received[-1] == {"9": "strong", "10": "low", "105": "acrubbing", "1": True}), dev.received[-1]
    assert dev.received[0] == {"9": "strong"} and dev.received[1] == {"10": "low"}
    r.command(cmd.pause()); assert wait(lambda: s.state == "paused")
    assert wait(lambda: dev.received[-1] == {"2": True})
    r.command(cmd.resume()); assert wait(lambda: s.state == "cleaning") and dev.received[-1] == {"2": False}
    r.command(cmd.home()); assert wait(lambda: s.state == "returning") and dev.received[-1] == {"3": True}
    r.command(cmd.resume()); assert wait(lambda: dev.received[-1] == {"1": True})   # volviendo -> sigue
    # «Fregado»: solo fregar
    r.command(cmd.select_mode("Fregado")); r.command(cmd.start())
    assert wait(lambda: dev.received[-1].get("41") == "only_mop"), dev.received[-1]
    assert wait(lambda: r.dps.get("41") == "only_mop")          # el robot lo confirma
    r.command(cmd.select_mode("Auto")); r.command(cmd.start())
    assert wait(lambda: dev.received[-1].get("41") == "only_sweep" and dev.received[-1]["105"] == "auto")
    # localizar, consumible, voz, no molestar, turbo alfombras, vaciado
    n = len(dev.received)
    r.command(cmd.locate()); r.command(cmd.reset_consumable("filter")); r.command(cmd.set_voice(False, 3))
    r.command(cmd.set_quiet(True, 1320, 420)); r.command(cmd.carpet_turbo(False)); r.command(cmd.dust_action())
    assert wait(lambda: len(dev.received) >= n + 6)
    assert dev.received[n:n + 6] == [{"11": True}, {"22": True}, {"108": False, "26": 30}, {"25": True},
                                     {"45": False}, {"38": True}], dev.received[n:]
    assert wait(lambda: r.state.consumables["filter"] == 0.0), r.state.consumables
    # mando manual: entra en manual, mueve, para solo y sale tras unos segundos sin pulsos
    import conga_core.tuya.robot as TR
    TR.DIRECT_IDLE_S = 1.2
    n = len(dev.received)
    r.command(cmd.direct(1)); r.command(cmd.direct(3))
    assert wait(lambda: dev.received[n:n + 3] == [{"4": "manual"}, {"12": "forward"}, {"12": "turn_right"}]), dev.received[n:]
    assert wait(lambda: {"12": "stop"} in dev.received[n:], 3) and wait(lambda: {"12": "exit"} in dev.received[n:], 4)
    assert wait(lambda: s.state == "idle"), s.state
    # avisos / errores del robot (empujados por él)
    dev.push(dev._react({"5": "paused", "28": 1 << 20}))
    assert wait(lambda: s.state == "error" and s.fault == 501), (s.state, s.fault)
    dev.push(dev._react({"28": 1 << 16, "5": "smart"}))
    assert wait(lambda: s.state == "cleaning" and s.fault == 527 and "lleno" in s.warning), (s.state, s.fault)
    dev.push(dev._react({"28": 0}))
    assert wait(lambda: s.fault == 0 and s.warning is None)
    # sin mapa: limpieza por habitaciones rechazada, no rompe
    assert r.command(cmd.clean_rooms([2]))["ok"] is False and r.map is None and r.map_empty
    # se cae el robot -> reconecta solo
    TR.RETRY_S = 0.3
    for c in dev.conns: c.close()
    assert wait(lambda: len(dev.conns) >= 2, 4), "no reconectó"
    assert wait(lambda: s.online)
    r.stop(); dev.close()
    print(f"OK tuya {version}: {len(dev.received)} órdenes")


run("3.3")
run("3.4")

# local key equivocada (3.4): no conecta y lo dice
dev = F.FakeTuya("3.4")
d = P.TuyaDevice(F.DEV_ID, "127.0.0.1", "ffffffffffffffff", "3.4", port=dev.port)
try:
    d.connect(); raise SystemExit("conectó con una key mala")
except (P.TuyaError, OSError) as e:
    assert "key" in str(e).lower() or "HMAC" in str(e), e
dev.close()
# 3.5 aún no
try:
    P.TuyaDevice("x", "127.0.0.1", F.KEY, "3.5").connect(); raise SystemExit("3.5 aceptado")
except P.TuyaError:
    pass
print("OK tuya")
