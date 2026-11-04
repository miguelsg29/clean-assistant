"""Carrera 4010/4030: aunque el canal del MAPA se registre primero, las órdenes salen por 4010."""
import socket
import sys
import time
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from conga_core import commands as cmd
from conga_core.config import RobotConfig
from conga_core.legacy import protobuf as pb
from conga_core.legacy.packet import Packet
from conga_core.legacy.robot import LegacyRobot

PORTS = {"cmd": 16010, "map": 16030, "rtc": 16050}
r = LegacyRobot(RobotConfig(), logger=lambda m: None, host="127.0.0.1", ports=PORTS)
r.start()

def drain(s, t=1.0):
    s.settimeout(t); out = []; buf = b""
    try:
        while True:
            d = s.recv(65536)
            if not d: break
            buf += d
    except socket.timeout:
        pass
    while len(buf) >= 4 and len(buf) >= int.from_bytes(buf[:4], "little"):
        n = int.from_bytes(buf[:4], "little"); out.append(Packet.from_bytes(buf[:n]).opname); buf = buf[n:]
    return out

ok = 0
def check(name, cond, extra=""):
    global ok
    assert cond, f"FALLO: {name} {extra}"
    ok += 1; print(f"  ok  {name}")

# peor orden posible: el 4030 llega y manda su latido ANTES que el ONLINE del 4010
m = socket.create_connection(("127.0.0.1", PORTS["map"]))
m.sendall(Packet("CLIENT_HEARTBEAT_REQ", b"", ctype=1, device_id=8058).to_bytes())
time.sleep(0.5)
c = socket.create_connection(("127.0.0.1", PORTS["cmd"]))
c.sendall(Packet("CLIENT_ONLINE_REQ", pb.encode({1: "XXXXXXXXXXXX", 2: 1, 3: 1001}), ctype=1, device_id=8058).to_bytes())
time.sleep(0.8)
oc, om = drain(c), drain(m)
print("    4010 recibe:", oc); print("    4030 recibe:", om)
check("handshake por 4010 aunque el 4030 llegara antes", "DEVICE_CONTROL_LOCK_REQ" in oc and "DEVICE_MAPID_GET_GLOBAL_INFO_REQ" in oc)
check("por 4030 solo la respuesta a su latido", om == ["CLIENT_HEARTBEAT_RSP"], om)
r.command(cmd.home())
check("las órdenes de la interfaz también van por 4010", drain(c) == ["DEVICE_CHARGE_REQ"] and drain(m, 0.3) == [])
c.close(); time.sleep(0.5)
r.command(cmd.home())
check("si cae el 4010, se usa el que quede (4030)", drain(m) == ["DEVICE_CHARGE_REQ"])
m.close(); r.stop()
print(f"\nTODO OK: {ok} comprobaciones")
