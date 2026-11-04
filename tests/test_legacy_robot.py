"""Prueba de punta a punta de LegacyRobot con un Conga 4090 SIMULADO (sin hardware)."""
import socket
import sys
import time
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from conga_core.config import RobotConfig
from conga_core.legacy import protobuf as pb
from conga_core.legacy.packet import Packet
from conga_core.legacy.robot import LegacyRobot

PORTS = {"cmd": 14010, "map": 14030, "rtc": 14050}
logs = []
robot = LegacyRobot(RobotConfig(), logger=lambda m: logs.append(m), host="127.0.0.1", ports=PORTS)
updates = []
robot.on_update = lambda: updates.append(robot.state.state)
robot.start()

ok = 0
def check(name, cond):
    global ok
    assert cond, f"FALLO: {name}\n" + "\n".join(logs[-15:])
    ok += 1
    print(f"  ok  {name}")

def recv_pkt(s):
    head = s.recv(4, socket.MSG_WAITALL)
    size = int.from_bytes(head, "little")
    body = b""
    while len(body) < size - 4:
        body += s.recv(size - 4 - len(body))
    return Packet.from_bytes(head + body)

def tx(s, opname, fields, dev=0, usr=0, seq=1, flow=0):
    s.sendall(Packet(opname, pb.encode(fields), ctype=2, flow=flow,
                     device_id=dev, user_id=usr, sequence=seq).to_bytes())

print("== rtc (4050): hora al conectar ==")
r = socket.create_connection(("127.0.0.1", PORTS["rtc"]))
p = recv_pkt(r)
t = pb.first(pb.decode(pb.first(pb.decode(p.payload), 3)), 1)
check("DEVICE_TIME_SYNC_RSP", p.opname == "DEVICE_TIME_SYNC_RSP")
check("hora ~ ahora", abs(t - time.time()) < 5)
r.close()

print("== online sin deviceId -> 12002 (debe registrarse) ==")
c = socket.create_connection(("127.0.0.1", PORTS["cmd"]))
tx(c, "CLIENT_ONLINE_REQ", {1: "SN-FAKE", 2: True, 3: 0}, dev=0, seq=7)
p = recv_pkt(c)
check("CLIENT_ONLINE_RSP", p.opname == "CLIENT_ONLINE_RSP")
check("result 12002", pb.first(pb.decode(p.payload), 1) == 12002)

print("== registro (cmd 4010) ==")
tx(c, "DEVICE_REGISTER_REQ", {1: "SW-1.0", 2: "HW-2", 3: "SN-FAKE", 4: "AA:BB:CC:DD:EE:FF",
                              5: 20, 6: 1003, 7: "V4.0"}, seq=42)
p = recv_pkt(c)
rsp = pb.decode(p.payload)
dev_id = pb.first(pb.decode(pb.first(rsp, 3)), 1)
check("DEVICE_REGISTER_RSP", p.opname == "DEVICE_REGISTER_RSP")
check("result 0", pb.first(rsp, 1) == 0)
check("device id asignado", isinstance(dev_id, int) and dev_id > 0)
check("seq eco", p.sequence == 42)
check("flow+1", p.flow == 1)
check("identidad capturada", robot.captured.get("sn") == "SN-FAKE" and robot.captured["ctrl_version"] == "V4.0")

print("== online (map 4030) con el id asignado -> handshake ==")
m = socket.create_connection(("127.0.0.1", PORTS["map"]))
tx(m, "CLIENT_ONLINE_REQ", {1: "SN-FAKE", 2: True, 3: 0}, dev=dev_id, seq=43)
p = recv_pkt(m)
check("online OK", p.opname == "CLIENT_ONLINE_RSP" and pb.first(pb.decode(p.payload), 1) == 0)
# 2 conexiones -> handshake por la PRIMERA (cmd)
hs = [recv_pkt(c).opname for _ in range(10)]
check("handshake: lock", hs[0] == "DEVICE_CONTROL_LOCK_REQ")
check("handshake: actualizaciones OFF + lectura", hs[1:3] == ["DEVICE_UPGRADE_SET_AUTO_INSTALL_REQ", "DEVICE_UPGRADE_GET_AUTO_INSTALL_REQ"])
check("handshake: status", hs[3] == "DEVICE_STATUS_GETTING_REQ")
check("handshake: mapas", hs[4] == "DEVICE_GET_ALL_GLOBAL_MAP_INFO_REQ")
check("handshake: hora", hs[5] == "DEVICE_GETTIME_REQ")
check("handshake: pide mapa", hs[6] == "DEVICE_MAPID_GET_GLOBAL_INFO_REQ")
check("handshake: consumibles", hs[7] == "DEVICE_MAPID_GET_CONSUMABLES_PARAM_REQ")
check("handshake: WiFi", hs[8] == "DEVICE_WLAN_INFO_GETTING_REQ")
check("handshake: horarios del robot", hs[9] == "DEVICE_ORDERLIST_GETTING_REQ")

print("== estado: en la base cargando ==")
tx(c, "DEVICE_MAPID_WORK_STATUS_PUSH_REQ",
   {1: 77, 2: False, 3: 0, 4: 160, 5: True, 6: 0, 7: 0, 8: 2, 9: False, 10: 0, 11: 0}, dev=dev_id)
time.sleep(0.3)
s = robot.state
check("online", s.online)
check("docked", s.state == "docked")
check("bateria 160 -> 80% (×2, app oficial)", s.battery == 80)
check("map_head_id", s.map_head_id == 77)
check("on_update llamado", "docked" in updates)

print("== estado: limpiando con aviso 525 (depósito de agua) ==")
tx(c, "DEVICE_MAPID_WORK_STATUS_PUSH_REQ",
   {1: 77, 2: False, 3: 1, 4: 190, 5: False, 6: 0, 7: 525, 8: 2, 9: False, 10: 12, 11: 1506}, dev=dev_id)
time.sleep(0.3)
check("cleaning", s.state == "cleaning")
check("aviso 5xx NO es error", s.state != "error")
check("texto del aviso", s.warning == "Depósito de agua bajo")
check("bateria 190 -> 95%", s.battery == 95)
check("area 15.06", s.area == 15.06)

print("== estado: pausa (workMode 4) / volviendo (10) / type!=0 -> error ==")
tx(c, "DEVICE_MAPID_WORK_STATUS_PUSH_REQ", {3: 4, 4: 190, 5: False, 6: 0, 7: 0}, dev=dev_id); time.sleep(0.2)
check("paused", s.state == "paused")
tx(c, "DEVICE_MAPID_WORK_STATUS_PUSH_REQ", {3: 10, 4: 190, 5: False, 6: 0, 7: 0}, dev=dev_id); time.sleep(0.2)
check("returning", s.state == "returning")
tx(c, "DEVICE_MAPID_WORK_STATUS_PUSH_REQ", {3: 1, 4: 190, 5: False, 6: 1, 7: 0}, dev=dev_id); time.sleep(0.2)
check("error por type", s.state == "error")

print("== batería por push, latido y versión ==")
tx(c, "PUSH_DEVICE_BATTERY_INFO_REQ", {1: {1: 200}}, dev=dev_id, seq=50)
p = recv_pkt(c)
check("BATTERY_RSP", p.opname == "PUSH_DEVICE_BATTERY_INFO_RSP")
time.sleep(0.2)
check("bateria 100%", s.battery == 100)
tx(c, "CLIENT_HEARTBEAT_REQ", {}, dev=dev_id, seq=51)
check("HEARTBEAT_RSP", recv_pkt(c).opname == "CLIENT_HEARTBEAT_RSP")
tx(c, "DEVICE_SETTIME_REQ", {}, dev=dev_id, seq=52)
p = recv_pkt(c)
check("SETTIME_RSP con hora", p.opname == "DEVICE_SETTIME_RSP" and abs(pb.first(pb.decode(p.payload), 1) - time.time()) < 5)

print("== comandos de la interfaz -> opcodes legacy ==")
from conga_core import commands as cmd
def sent_after(control):
    robot.command(control)
    return recv_pkt(c)
p = sent_after(cmd.start()); f = pb.decode(p.payload)
check("start -> AUTO_CLEAN ctrl=1 type=2", p.opname == "DEVICE_AUTO_CLEAN_REQ" and f[1] == [1] and f[2] == [2])
check("ids intercambiados (wire userId = device)", p.user_id == dev_id)
p = sent_after(cmd.pause()); check("pause -> ctrl=2", pb.first(pb.decode(p.payload), 1) == 2)
p = sent_after(cmd.resume()); check("resume -> ctrl=1", pb.first(pb.decode(p.payload), 1) == 1)
p = sent_after(cmd.home()); check("home -> CHARGE_REQ enable=1", p.opname == "DEVICE_CHARGE_REQ" and pb.first(pb.decode(p.payload), 1) == 1)
p = sent_after(cmd.cancel_home()); check("cancel_home -> AUTO_CLEAN stop", p.opname == "DEVICE_AUTO_CLEAN_REQ" and pb.first(pb.decode(p.payload), 1, 0) == 0)
p = sent_after(cmd.locate()); check("locate -> SEEK_LOCATION", p.opname == "DEVICE_SEEK_LOCATION_REQ")
p = sent_after(cmd.fan("Turbo")); check("fan Turbo -> PREFERENCE 2 (prueba de oído #12)", p.opname == "DEVICE_SET_CLEAN_PREFERENCE_REQ" and pb.first(pb.decode(p.payload), 1) == 2)
p = sent_after(cmd.fan("Off")); check("fan Off(=Máx legacy) -> 3", pb.first(pb.decode(p.payload), 1) == 3)
p = sent_after(cmd.water("Alto")); check("agua Alto -> 13", pb.first(pb.decode(p.payload), 1) == 13)
p = sent_after(cmd.water("Off")); check("agua Off -> 10", pb.first(pb.decode(p.payload), 1) == 10)
robot.command(cmd.direct(1))
a, b = recv_pkt(c), recv_pkt(c)
check("manual: init(10) + adelante(1)", pb.first(pb.decode(a.payload), 1) == 10 and pb.first(pb.decode(b.payload), 1) == 1)
p = sent_after(cmd.direct(0)); check("manual: parar -> 5", pb.first(pb.decode(p.payload), 1) == 5)
r = robot.command(cmd.base_type("Base de carga"))
check("no soportado -> ok False sin romper", r.get("ok") is False)

print("== desconexión -> offline ==")
c.close(); m.close(); time.sleep(0.5)
check("offline al cerrar", robot.state.online is False)

robot.stop()
print(f"\nTODO OK: {ok} comprobaciones")
