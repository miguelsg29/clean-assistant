"""Only map and status reports received on the current legacy connection are eligible."""
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from conga_core.config import RobotConfig
from conga_core.legacy import protobuf as pb
from conga_core.legacy.packet import Packet
from conga_core.legacy.robot import LegacyRobot


class SessionTest(unittest.TestCase):
    @patch("conga_core.legacy.robot.threading.Timer")
    def test_reconnect_requires_new_identity_status_and_complete_map(self, timer):
        robot = LegacyRobot(RobotConfig(), logger=lambda message: None)
        cmd, maps = Mock(), Mock()
        for sock in (cmd, maps):
            sock.getpeername.return_value = ("192.0.2.9", 41000)
        with patch.object(robot, "_start_handshake"):
            robot._handle(cmd, Packet("DEVICE_REGISTER_REQ", pb.encode({1: "test-fw", 3: "test-sn"})))
            first = robot.native_session_id
            robot._attach(maps)
            self.assertEqual(first, robot.native_session_id)
            self.assertEqual(robot.native_live_sn, "test-sn")
            self.assertEqual(robot.native_live_software, "test-fw")
            robot._apply_status({3: [0], 5: [1]})
            self.assertEqual(robot.native_state_session_id, first)
            self.assertEqual(robot.native_peer_ip, "192.0.2.9")
            maps.getpeername.return_value = ("192.0.2.19", 43000)
            self.assertIsNone(robot.native_peer_ip)

            head = {"map_head_id": 19, "size_x": 2, "size_y": 2, "min_x": 0,
                    "min_y": 0, "resolution": 1}
            with patch("conga_core.legacy.robot.mapdecode.decode_map",
                       side_effect=[{"head": head, "grid": bytes([13] * 4)}, {"head": head}]):
                robot._on_map(b"first-session")
                self.assertEqual(robot.native_map_session_id, first)
                robot._drop(maps)
                self.assertEqual(robot.native_session_id, first)
                robot._drop(cmd)
                robot._handle(cmd, Packet("CLIENT_ONLINE_REQ", pb.encode({1: "test-sn"}), device_id=1))
                self.assertNotEqual(robot.native_session_id, first)
                self.assertEqual(robot.native_live_sn, "test-sn")
                self.assertIsNone(robot.native_live_software)
                self.assertIsNone(robot.native_state_session_id)
                robot._on_map(b"partial-second-session")
                self.assertIsNone(robot.native_map_session_id)
                robot._handle(cmd, Packet("DEVICE_VERSION_INFO_UPDATE_REQ", pb.encode({1: "new-fw"}), device_id=1))
                self.assertEqual(robot.native_live_software, "new-fw")


if __name__ == "__main__":
    unittest.main()
