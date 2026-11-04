"""Round-trip de la capa base del backend legacy (sin robot)."""
import sys
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from conga_core.legacy import protobuf as pb
from conga_core.legacy.packet import Packet, respond, send
from conga_core.legacy.opcodes import OPCODES, name_of, code_of

ok = 0
def check(name, cond):
    global ok
    assert cond, f"FALLO: {name}"
    ok += 1
    print(f"  ok  {name}")

print("== protobuf: vectores conocidos ==")
check("varint 0",      pb.encode({1: 0}) == b"\x08\x00")
check("varint 300",    pb.encode({1: 300}) == b"\x08\xac\x02")
check("string 'hi'",   pb.encode({2: "hi"}) == b"\x12\x02hi")
check("bool True",     pb.encode({3: True}) == b"\x18\x01")
check("nested {4:{1:7}}", pb.encode({4: {1: 7}}) == b"\x22\x02\x08\x07")
check("repeated 5=[1,2]", pb.encode({5: [1, 2]}) == b"\x28\x01\x28\x02")

print("== protobuf: round-trip ==")
msg = {1: 0, 2: {1: 1234567}, 3: "Conga 4090", 7: [10, 20, 30]}
dec = pb.decode(pb.encode(msg))
check("result campo1",   pb.first(dec, 1) == 0)
check("device.id anidado", pb.first(pb.decode(pb.first(dec, 2)), 1) == 1234567)
check("string campo3",   pb.as_str(pb.first(dec, 3)) == "Conga 4090")
check("repeated campo7",  dec[7] == [10, 20, 30])

print("== packet: round-trip de la trama de 24 bytes ==")
payload = pb.encode({1: 0, 2: {1: 42}})
p = Packet("DEVICE_REGISTER_RSP", payload, ctype=2, flow=1,
           device_id=0xAABBCCDD, user_id=0x11223344, sequence=0x1122334455667788)
raw = p.to_bytes()
check("tamano = 24 + payload", len(raw) == 24 + len(payload))
check("prefijo size LE", int.from_bytes(raw[:4], "little") == len(raw))
q = Packet.from_bytes(raw)
check("opcode preservado",  q.opcode == OPCODES["DEVICE_REGISTER_RSP"])
check("opname",             q.opname == "DEVICE_REGISTER_RSP")
check("ctype",              q.ctype == 2)
check("flow",               q.flow == 1)
check("device_id",          q.device_id == 0xAABBCCDD)
check("user_id",            q.user_id == 0x11223344)
check("sequence u64",       q.sequence == 0x1122334455667788)
check("payload",            q.payload == payload)
check("payload decodifica", pb.first(pb.decode(q.payload), 1) == 0)

print("== respond(): eco + flow+1 + ids intercambiados ==")
req = Packet("DEVICE_REGISTER_REQ", b"", ctype=5, flow=0,
             device_id=0, user_id=777, sequence=999)
rsp = respond(req, "DEVICE_REGISTER_RSP", pb.encode({1: 0}))
check("respond ctype eco",  rsp.ctype == 5)
check("respond flow+1",     rsp.flow == 1)
check("respond seq eco",    rsp.sequence == 999)
check("respond swap: user=req.device", rsp.user_id == req.device_id)
check("respond swap: device=req.user", rsp.device_id == req.user_id)

print("== opcodes clave (vs @agnoc/core) ==")
check("DEVICE_REGISTER_REQ 0x0fa1", OPCODES["DEVICE_REGISTER_REQ"] == 0x0fa1)
check("CLIENT_ONLINE_REQ 0x07d1",   OPCODES["CLIENT_ONLINE_REQ"] == 0x07d1)
check("CLIENT_HEARTBEAT_REQ 0x07d5", OPCODES["CLIENT_HEARTBEAT_REQ"] == 0x07d5)
check("DEVICE_TIME_SYNC_RSP 0x0fa4", OPCODES["DEVICE_TIME_SYNC_RSP"] == 0x0fa4)
check("name_of desconocido", name_of(0x9999) == "UNK_9999")

print(f"\nTODO OK: {ok} comprobaciones pasaron ✓")
