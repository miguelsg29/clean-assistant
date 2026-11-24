"""Synthetic native I/O tests. Never connects to a robot."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.native_map_io import NativeMapIO, NativeMapError


class NativeMapTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="conga-native-")
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        config = self.directory / "ssh_config"
        config.write_text("Host conga-map\n HostName example.invalid\n")
        self.io = NativeMapIO(config)
        self.names = ("customer_map_list_path.plan", "scheme_data.info42")
        self.files = {self.names[0]: b"native-plan", self.names[1]: b"native-scheme\x00\xff"}

    def test_ssh_fails_closed_and_fixed_alias(self):
        with patch("backend.native_map_io.subprocess.run") as run:
            run.return_value = subprocess.CompletedProcess([], 0, b"ok", b"")
            self.assertEqual(self.io._run("fixed"), b"ok")
            args = run.call_args.args[0]
            self.assertEqual(args[-2:], ["conga-map", "fixed"])
            for option in ("StrictHostKeyChecking=yes", "BatchMode=yes", "PasswordAuthentication=no",
                           "KbdInteractiveAuthentication=no", "ControlPath=none"):
                self.assertIn(option, args)
            self.assertEqual(run.call_args.kwargs["timeout"], self.io.TIMEOUT)
            run.side_effect = subprocess.TimeoutExpired("ssh", 1)
            with self.assertRaises(NativeMapError):
                self.io._run("fixed")

    def test_reject_bad_ids_paths_and_empty_required_source_before_ssh(self):
        self.io._run = Mock(side_effect=AssertionError("must not connect"))
        for mid in (True, "42", 0, -1, 2**31):
            with self.assertRaises(ValueError):
                self.io.read_pair(mid)
        for bad in (dict(self.files, **{"../../etc/passwd": b"x"}),
                    {self.names[0]: b"", self.names[1]: b"x"}, {}):
            with self.assertRaises(ValueError):
                self.io.restore_pair(42, bad)
        with self.assertRaises(NativeMapError):
            self.io.read_pair(42)
        self.io._run.assert_not_called()

    def identity(self, mac="aa:bb:cc:dd:ee:ff", version="S3.3.8"):
        return (mac + "\n192.168.1.4 50000 192.168.1.9 22\n"
                "[SysVersion]\nsysProduct=CECOTECCRL300\nsysVersion=" + version + "\n").encode()

    def test_identity_mac_peer_and_firmware_pinning(self):
        self.io._run = Mock(return_value=self.identity())
        result = self.io.verify_identity(expected_ip="192.168.1.9")
        self.assertEqual(result["mac"], "aa:bb:cc:dd:ee:ff")
        self.assertEqual(result["sysProduct"], "CECOTECCRL300")
        with self.assertRaises(NativeMapError):
            self.io.verify_identity(expected_ip="192.168.1.10")
        with self.assertRaises(NativeMapError):
            self.io.verify_identity(expected_mac="aa:bb:cc:dd:ee:00")
        self.io._run.return_value = self.identity(version="changed")
        with self.assertRaises(NativeMapError):
            self.io._identity()

    def test_stable_twice_and_inventory_change(self):
        self.io._identity = Mock()
        self.io._inventory = Mock(return_value=self.names)
        self.io._read_once = Mock(return_value=self.files)
        self.assertEqual(self.io.read_pair(42), self.files)
        self.assertEqual(self.io._read_once.call_count, 2)
        self.io._inventory.side_effect = [self.names, self.names + ("scheme_data.info43",)]
        with self.assertRaises(NativeMapError):
            self.io.read_pair(42)
        self.io._inventory.side_effect = None
        self.io._read_once.side_effect = [self.files, dict(self.files, **{self.names[0]: b"changed"})]
        with self.assertRaises(NativeMapError):
            self.io.read_pair(42)

    def test_inventory_and_bounds(self):
        self.io._run = Mock(return_value=b"scheme_data.info42\ncustomer_map_list_path.plan\nresume_data.info\n")
        self.assertIn("resume_data.info", self.io._inventory(42))
        for listing in (b"scheme_data.info42\n../secret\n", b"customer_map_list_path.plan\n",
                        b"scheme_data.info42\ncustomer_map_list_path.plan\nscheme_data.info42\n"):
            self.io._run.return_value = listing
            with self.assertRaises(NativeMapError):
                self.io._inventory(42)
        self.io._run.return_value = b""
        self.assertEqual(self.io._read_once(("resume_data.info",)), {"resume_data.info": b""})
        self.io.MAX_FILE_BYTES = 3
        self.io._run.return_value = b"1234"
        with self.assertRaises(NativeMapError):
            self.io._read_once(self.names)

    def test_restore_refuses_changed_set_and_pairing_marker(self):
        self.io._identity = Mock()
        self.io._stable = Mock(return_value=dict(self.files, **{"scheme_data.info43": b"other"}))
        self.io._run = Mock(side_effect=AssertionError("must not mutate"))
        with self.assertRaisesRegex(NativeMapError, "filename set"):
            self.io.restore_pair(42, self.files)
        flag = "first_hardware_unbunding_flag.ini"
        self.io._stable.return_value = dict(self.files, **{flag: b"original"})
        with self.assertRaisesRegex(NativeMapError, "unbinding"):
            self.io.restore_pair(42, dict(self.files, **{flag: b"changed"}))
        self.io._run.assert_not_called()

    def test_missing_inventory_is_only_accepted_for_recovery_safety(self):
        self.io._run = Mock(return_value=b"")
        with self.assertRaises(NativeMapError):
            self.io._inventory(42)
        self.assertEqual(self.io._inventory(42, allow_missing=True), ())

    def test_marker_is_compared_but_never_replaced(self):
        flag = "first_hardware_unbunding_flag.ini"
        files = dict(self.files, **{flag: b"marker"})
        self.io._identity = Mock()
        self.io._stable = Mock(return_value=files)
        self.io._run = Mock(return_value=b"restored\n")
        receipt = self.io.restore_pair(42, files)
        self.assertNotIn(flag, receipt["files"])
        script = self.io._run.call_args.args[1].decode()
        self.assertNotIn(" " + self.io.ROOT + "/" + flag + "\n", "\n".join(
            line for line in script.splitlines() if line.startswith("mv ")))
        self.io._stable.return_value = self.files
        with self.assertRaisesRegex(NativeMapError, "unbinding"):
            self.io.restore_pair(42, files)

    def test_before_write_callback_runs_after_read_and_can_refuse(self):
        events = []
        self.io._identity = lambda: events.append("identity")
        self.io._stable = lambda *a, **kw: events.append("read") or self.files
        self.io._run = Mock(side_effect=AssertionError("must not mutate"))
        def refuse():
            events.append("preflight")
            raise NativeMapError("Robot left dock")
        with self.assertRaisesRegex(NativeMapError, "left dock"):
            self.io.restore_pair(42, self.files, before_write=refuse)
        self.assertEqual(events, ["identity", "read", "preflight"])
        self.io._run.assert_not_called()

    def test_safe_preflight_errors_are_actionable(self):
        self.io._identity = Mock()
        self.io._stable = Mock(return_value=self.files)
        for result, message in ((b"blocked-existing\n", "acknowledged completed"),
                                (b"blocked-space\n", "16 MiB headroom"),
                                (b"blocked-sha256\n", "lacks sha256sum")):
            self.io._run = Mock(return_value=result)
            with self.assertRaisesRegex(NativeMapError, message):
                self.io.restore_pair(42, self.files)

    def shell_restore(self, fail=False, source_change=False, missing=(), prefix="", prior=None):
        shell = shutil.which("bash") or shutil.which("sh")
        git_shell = Path("C:/Program Files/Git/bin/bash.exe")
        if git_shell.is_file():
            shell = str(git_shell)
        if not shell:
            self.skipTest("POSIX shell unavailable")
        self.io.ROOT = self.directory.as_posix()
        self.io._guard = lambda: f"test -d {self.io.ROOT}"
        old = {n: b"previous-" + v for n, v in self.files.items() if n not in missing}
        for n, data in old.items():
            (self.directory / n).write_bytes(data)
        txn = self.io.ROOT + "/.conga-map-fixture"
        script = self.io._restore_script(self.names, self.files, old, txn)
        if prior:
            previous = self.directory / ".conga-map-prior"
            previous.mkdir()
            (previous / "original0").write_bytes(b"retained-backup")
            if prior == "complete":
                (previous / "complete").touch()
        if fail:
            script = ('mv() { if [ "$2" = "' + txn + '/new1" ]; then return 1; '
                      'else command mv "$@"; fi; }\n') + script
        if source_change:
            (self.directory / self.names[0]).write_bytes(b"concurrent-change")
        script = prefix + script
        result = subprocess.run([shell, "-s"], input=script.encode(), capture_output=True, timeout=15)
        return result, old, Path(txn)

    def test_actual_shell_staging_and_retained_originals(self):
        result, old, txn = self.shell_restore()
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual(result.stdout, b"restored\n")
        for i, n in enumerate(self.names):
            self.assertEqual((self.directory / n).read_bytes(), self.files[n])
            self.assertEqual((txn / f"original{i}").read_bytes(), old[n])
        self.assertTrue((txn / "complete").is_file())
        self.assertEqual({p.name for p in txn.iterdir()},
                         {"original0", "original1", "files", "absent", "complete"})
        self.assertFalse((self.directory / ".conga-map-lock").exists())

    def test_actual_shell_rollback_after_second_rename_failure(self):
        result, old, txn = self.shell_restore(fail=True)
        self.assertNotEqual(result.returncode, 0)
        for i, n in enumerate(self.names):
            self.assertEqual((self.directory / n).read_bytes(), old[n])
            self.assertEqual((txn / f"original{i}").read_bytes(), old[n])
        self.assertFalse((txn / "complete").exists())
        self.assertFalse((self.directory / ".conga-map-lock").exists())

    def test_actual_shell_refuses_concurrent_original_change(self):
        result, old, txn = self.shell_restore(source_change=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.directory / self.names[0]).read_bytes(), b"concurrent-change")
        self.assertEqual((self.directory / self.names[1]).read_bytes(), old[self.names[1]])

    def test_actual_shell_recovers_partial_and_complete_loss(self):
        for missing in ((self.names[1],), self.names):
            with self.subTest(missing=missing):
                result, old, txn = self.shell_restore(missing=missing)
                self.assertEqual(result.returncode, 0, result.stderr.decode())
                for name, content in self.files.items():
                    self.assertEqual((self.directory / name).read_bytes(), content)
                self.assertEqual(set((txn / "absent").read_text().splitlines()), set(missing))
                # Reuse this fixture only after deleting generated local test files.
                shutil.rmtree(txn)
                for name in self.files:
                    (self.directory / name).unlink()

    def test_actual_shell_rolls_back_missing_state_after_loss(self):
        for missing in ((self.names[1],), self.names):
            with self.subTest(missing=missing):
                result, old, txn = self.shell_restore(fail=True, missing=missing)
                self.assertNotEqual(result.returncode, 0)
                for name in self.names:
                    path = self.directory / name
                    if name in missing:
                        self.assertFalse(path.exists())
                    else:
                        self.assertEqual(path.read_bytes(), old[name])
                self.assertEqual(set((txn / "absent").read_text().splitlines()), set(missing))
                shutil.rmtree(txn)
                for name in old:
                    (self.directory / name).unlink()

    def test_actual_shell_missing_sha256_refuses_before_staging(self):
        prefix = ('command() { if [ "$1" = "-v" ] && [ "$2" = "sha256sum" ]; '
                  'then return 1; else builtin command "$@"; fi; }\n')
        result, old, txn = self.shell_restore(prefix=prefix)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual(result.stdout, b"blocked-sha256\n")
        self.assertFalse(txn.exists())
        self.assertFalse((self.directory / ".conga-map-lock").exists())
        for name, content in old.items():
            self.assertEqual((self.directory / name).read_bytes(), content)

    def test_actual_shell_low_space_refuses_before_staging(self):
        prefix = ("df() { printf 'Filesystem 1024-blocks Used Available Capacity Mounted\\n"
                  "fixture 100 100 0 100%% root\\n'; }\n")
        result, old, txn = self.shell_restore(prefix=prefix)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual(result.stdout, b"blocked-space\n")
        self.assertFalse(txn.exists())
        for name, content in old.items():
            self.assertEqual((self.directory / name).read_bytes(), content)

    def test_actual_shell_retains_completed_and_failed_prior_transactions(self):
        for status in ("complete", "failed"):
            with self.subTest(status=status):
                result, old, txn = self.shell_restore(prior=status)
                self.assertEqual(result.returncode, 0, result.stderr.decode())
                self.assertEqual(result.stdout, b"blocked-existing\n")
                self.assertFalse(txn.exists())
                previous = self.directory / ".conga-map-prior"
                self.assertEqual((previous / "original0").read_bytes(), b"retained-backup")
                for name, content in old.items():
                    self.assertEqual((self.directory / name).read_bytes(), content)
                shutil.rmtree(previous)


if __name__ == "__main__":
    unittest.main()
