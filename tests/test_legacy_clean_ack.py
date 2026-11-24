"""Pre-clean safety: settings never replace zones; failed preparation never starts."""
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.update(CONGA_MODE="mock", MQTT_HOST="", DATA_DIR=tempfile.mkdtemp())
from backend import app as A
from conga_core import commands as cmd
from conga_core.config import RobotConfig
from conga_core.legacy.robot import LegacyRobot
from conga_core.legacy import protobuf as pb
from conga_core.legacy import mapdecode
from backend.mqtt_bridge import MqttBridge
from backend.schedules import ScheduleStore


sent = []

def legacy():
    r = LegacyRobot(RobotConfig(), logger=lambda *args: None)
    r._lmap = {"head": {"map_head_id": 77}, "walls": {"areas": []},
               "rooms": [{"id": 1, "name": "Kitchen"}]}
    r._send = lambda op, f, **kw: (sent.append((op, f)), {"result": 0})[1]
    return r


for operation in (lambda r: r.command(cmd.clean_rooms([1])), lambda r: r.command(cmd.start())):
    for fail_at in (1, 2):
        sent.clear()
        r = legacy()
        counter = [0]
        def response(*args):
            counter[0] += 1
            return counter[0] != fail_at
        r._send_recv = response
        result = operation(r)
        assert result["ok"] is False
        assert not any(op == "DEVICE_AUTO_CLEAN_REQ" for op, _ in sent)

# A positive wall acknowledgement updates the walls included in the next room plan.
sent.clear()
r = legacy()
r._send_recv = lambda *args: True
assert r.command(cmd.set_virwall([{"points": [(0, 0), (1, 0)], "type": 200}], 77))["result"] == 0
assert r._plan_rooms_req(77, lambda _: True)[6][3] == 1
r._send_recv = lambda *args: False
assert r.command(cmd.set_virwall([{"points": [(0, 0), (1, 0)], "type": 301}], 77))["ok"] is False

# Wire responses: explicit zero succeeds; errors, empty responses and timeout fail.
for fields, expected in (({1: [0]}, True), ({1: [5]}, False), ({}, False)):
    r = legacy()
    r._send = lambda op, f, **kw: (r._wake("TEST_RSP", fields, kw["sequence"]), {"result": 0})[1]
    assert r._send_recv("TEST_REQ", {}, "TEST_RSP", timeout=0.01) is expected
    assert not r._waiters
r = legacy()
assert r._send_recv("TEST_REQ", {}, "TEST_RSP", timeout=0.001) is False
assert not r._waiters

# Partial pushes from another map cannot retain the previous map's walls/rooms.
r = legacy()
decode = mapdecode.decode_map
mapdecode.decode_map = lambda _: {"head": {"map_head_id": 88}}
try:
    r._on_map(b"test")
    assert "walls" not in r._lmap and "rooms" not in r._lmap
finally:
    mapdecode.decode_map = decode
r._send = lambda *args, **kw: {"ok": False}
assert r._send_recv("TEST_REQ", {}, "TEST_RSP", timeout=0.001) is False
assert not r._waiters


# Wrong-map restrictions never reach the transport; unsupported restrictions fail.
sent.clear()
r = legacy()
r._send_recv = lambda *a: True
assert r.command(cmd.set_virwall([{"points": [(0, 0), (1, 0)]}], 88))["ok"] is False
assert not sent
r._lmap.pop("walls")
assert r.command(cmd.start())["ok"] is False
assert not any(op == "DEVICE_AUTO_CLEAN_REQ" for op, _ in sent)
r._lmap = {}
assert r.command(cmd.start())["ok"] is False

# Concurrent requests with the same opcode and stale replies have separate waiters.
import concurrent.futures
import threading
r = legacy()
requests = []
ready = threading.Event()
def capture(op, fields, **kw):
    requests.append(kw["sequence"])
    if len(requests) == 2:
        ready.set()
    return {"result": 0}
r._send = capture
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    first = pool.submit(r._send_recv, "TEST_REQ", {}, "TEST_RSP", 1)
    second = pool.submit(r._send_recv, "TEST_REQ", {}, "TEST_RSP", 1)
    assert ready.wait(1)
    r._wake("TEST_RSP", {1: [0]}, -1)
    assert not first.done() and not second.done()
    r._wake("TEST_RSP", {1: [0]}, requests[0])
    r._wake("TEST_RSP", {1: [5]}, requests[1])
    assert sorted([first.result(), second.result()]) == [False, True]
assert not r._waiters
try:
    r._send_recv("DEVICE_MAPID_GET_GLOBAL_INFO_REQ", {}, "DEVICE_MAPID_GET_GLOBAL_INFO_RSP")
    raise AssertionError("Binary map must not count as a result ACK")
except ValueError:
    pass

# API waits in a worker and returns rejection before recording a successful trigger.
A.LEGACY = True
A.robot = r = legacy()
A._ui_prefs["resend_before_clean"] = False
A._ui_prefs["resend_restrictions_before_clean"] = False
entered = threading.Event()
release = threading.Event()
def reject_plan(*args):
    entered.set()
    assert release.wait(1)
    return False
r._send_recv = reject_plan
async def api_rejection():
    before = dict(A._clean_trigger)
    task = asyncio.create_task(A.post_command({"action": "start"}))
    while not entered.is_set():
        await asyncio.sleep(0.001)
    # Running this coroutine while the robot is waiting proves the loop is free.
    assert not task.done()
    release.set()
    result = await task
    assert result["ok"] is False and result["code"] == "command_failed"
    assert A._clean_trigger == before
asyncio.run(api_rejection())
print("OK legacy ACK: positive/rejected/missing responses, sequence correlation and async API")
