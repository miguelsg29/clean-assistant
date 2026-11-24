"""Restricted administrator SSH access to the Conga 4090 native map collection.

The administrator supplies an OpenSSH config with alias ``conga-map`` and a
verified known-host entry. No credentials, hostnames or shell commands come from
HTTP. This module does not reboot the robot or stop firmware processes.

Renames are atomic individually, not as a collection. Firmware writers and power
loss can still interrupt consistency; restores retain a private remote transaction
directory containing originals for administrator recovery. There is no fsync or
power-loss durability guarantee. SSH interruption can leave a transaction running
or a stale lock; an administrator must inspect retained data before retry.
"""
from __future__ import annotations

import base64
import hashlib
import ipaddress
import re
from pathlib import Path
import subprocess
import threading
import uuid


class NativeMapError(RuntimeError):
    """Native transport failed; no success should be reported to the user."""


class NativeMapIO:
    MAX_FILE_BYTES = 8 * 1024 * 1024
    TIMEOUT = 60
    MAX_FILES = 64
    MAX_TOTAL_BYTES = 32 * 1024 * 1024
    COMPANIONS = ("carto_slam.data", "resume_data.info", "unfinished_carto_slam.data",
                  "unfinished_data.info", "first_hardware_unbunding_flag.ini")
    ROOT = "/mnt/UDISK/log"

    def __init__(self, config_path):
        self.config_path = Path(config_path).resolve(strict=True)
        if not self.config_path.is_file():
            raise ValueError("SSH configuration must be a regular file")
        self._lock = threading.Lock()
        self._expected_mac = None
        self._firmware_identity = None

    @staticmethod
    def _names(map_id):
        if type(map_id) is not int or not 1 <= map_id <= 2**31 - 1:
            raise ValueError("map_id must be a positive 32-bit integer")
        return (f"scheme_data.info{map_id}", "customer_map_list_path.plan")

    def _run(self, command, payload=None):
        # Command strings are internal templates using only validated integers and
        # generated UUIDs. -o options precede config processing and fail closed.
        args = ["ssh", "-F", str(self.config_path),
                "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
                "-o", "PasswordAuthentication=no", "-o", "KbdInteractiveAuthentication=no",
                "-o", "PreferredAuthentications=publickey", "-o", "UpdateHostKeys=no",
                "-o", "ForwardAgent=no", "-o", "ClearAllForwardings=yes",
                "-o", "PermitLocalCommand=no",
                "-o", "ControlMaster=no", "-o", "ControlPath=none",
                "-o", "ConnectTimeout=10", "-o", "ConnectionAttempts=1",
                "-o", "ServerAliveInterval=5", "-o", "ServerAliveCountMax=2",
                "-T", "conga-map", command]
        try:
            result = subprocess.run(args, input=payload, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, timeout=self.TIMEOUT,
                                    check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise NativeMapError("Native SSH failed or timed out") from exc
        if result.returncode:
            raise NativeMapError("Native SSH operation failed")
        return result.stdout

    @classmethod
    def _guard(cls):
        return "\n".join(f"test -d {p} && test ! -L {p} || exit 1"
                         for p in ("/mnt", "/mnt/UDISK", cls.ROOT))

    @classmethod
    def _allowed(cls, name):
        return (name == "customer_map_list_path.plan" or name in cls.COMPANIONS or
                re.fullmatch(r"scheme_data\.info[0-9]{1,10}", name) is not None)

    def verify_identity(self, expected_mac=None, expected_ip=None):
        """Bind SSH to the physical bridge MAC and read firmware identity."""
        if expected_mac is not None and (not isinstance(expected_mac, str) or not re.fullmatch(
                r"[0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5}", expected_mac)):
            raise ValueError("Invalid physical robot MAC address")
        if expected_mac is None and expected_ip is None:
            raise ValueError("A physical robot MAC or current command peer IP is required")
        if expected_ip is not None:
            expected_ip = ipaddress.ip_address(expected_ip)
        raw = self._run("cat /sys/class/net/wlan0/address; "
                        "printf '%s\\n' \"$SSH_CONNECTION\"; "
                        "head -c 4097 /etc/sysconf/sysVersion.ini")
        try:
            mac, connection, ini = raw.decode("ascii").split("\n", 2)
            mac = mac.strip().lower()
            parts = connection.split()
            endpoint = ipaddress.ip_address(parts[2]) if len(parts) == 4 else None
        except (UnicodeError, ValueError) as exc:
            raise NativeMapError("Invalid SSH robot identity") from exc
        if (not re.fullmatch(r"[0-9a-f]{2}(?::[0-9a-f]{2}){5}", mac) or
                mac in ("00:00:00:00:00:00", "ff:ff:ff:ff:ff:ff") or len(ini) > 4096 or
                (expected_mac is not None and mac != expected_mac.lower()) or
                (expected_ip is not None and endpoint != expected_ip)):
            raise NativeMapError("SSH target does not match the physical robot identity")
        fields = {}
        for line in ini.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                if key.strip() in ("sysProduct", "sysVersion"):
                    if key.strip() in fields:
                        raise NativeMapError("Ambiguous firmware identity")
                    fields[key.strip()] = value.strip()
        if set(fields) != {"sysProduct", "sysVersion"}:
            raise NativeMapError("Missing native firmware identity")
        if self._firmware_identity is not None and fields != self._firmware_identity:
            raise NativeMapError("Native firmware identity changed")
        self._firmware_identity = fields
        self._expected_mac = mac
        return dict(fields, mac=self._expected_mac)

    def _identity(self):
        if self._expected_mac is None:
            raise NativeMapError("Verify the physical robot MAC before native access")
        self.verify_identity(self._expected_mac)

    def read_registration_identity(self):
        """Read the registration fields from the verified robot's configuration."""
        path = "/mnt/UDISK/config/device_config.ini"
        with self._lock:
            self._identity()
            script = (
                "set -eu\n"
                "for p in /mnt /mnt/UDISK /mnt/UDISK/config; do\n"
                'test -d "$p" && test ! -L "$p" || exit 1\n'
                "done\n"
                f"test -f {path} && test ! -L {path} || exit 1\n"
                f"size=$(wc -c < {path})\n"
                'test "$size" -le 16384 || exit 1\n'
                f"awk -F= '$1 ~ /^[[:space:]]*(device_sn|software_version)[[:space:]]*$/ {{print}}' {path}"
            )
            raw = self._run(script)
        if len(raw) > 16384:
            raise NativeMapError("Invalid robot registration identity")
        try:
            lines = raw.decode("ascii").splitlines()
        except UnicodeError as exc:
            raise NativeMapError("Invalid robot registration identity") from exc
        fields = {}
        names = {"device_sn": "sn", "software_version": "software"}
        for line in lines:
            key, separator, value = line.partition("=")
            key, value = key.strip(), value.strip()
            if (not separator or key not in names or names[key] in fields or
                    not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", value)):
                raise NativeMapError("Invalid robot registration identity")
            fields[names[key]] = value
        if set(fields) != {"sn", "software"}:
            raise NativeMapError("Missing robot registration identity")
        return fields

    def _inventory(self, map_id, allow_missing=False):
        patterns = " ".join(f"{self.ROOT}/{n}" for n in
                            ("scheme_data.info[0-9]*", "customer_map_list_path.plan") + self.COMPANIONS)
        script = (f"{self._guard()}\ncount=0\nfor p in {patterns}; do\n"
                  'if [ -e "$p" ] || [ -L "$p" ]; then\n'
                  'test -f "$p" && test ! -L "$p" || exit 1\n'
                  f'count=$((count + 1)); test "$count" -le {self.MAX_FILES} || exit 1\n'
                  'printf \'%s\\n\' "${p##*/}"\nfi\ndone')
        try:
            names = self._run(script).decode("ascii").splitlines()
        except UnicodeError as exc:
            raise NativeMapError("Invalid native inventory") from exc
        if (len(names) > self.MAX_FILES or len(names) != len(set(names)) or
                any(not self._allowed(n) for n in names) or
                (not allow_missing and not set(self._names(map_id)).issubset(names))):
            raise NativeMapError("Missing, excessive or unsupported native files")
        return tuple(sorted(names))

    def _read_once(self, names, allow_empty=False):
        files = {}
        for name in names:
            path = f"{self.ROOT}/{name}"
            script = (f"{self._guard()}\ntest -f {path} && test ! -L {path} || exit 1\n"
                      f"head -c {self.MAX_FILE_BYTES + 1} {path}")
            data = self._run(script)
            if len(data) > self.MAX_FILE_BYTES or (not data and not allow_empty and name not in self.COMPANIONS):
                raise NativeMapError("Native file is empty or exceeds the size limit")
            files[name] = data
            if sum(map(len, files.values())) > self.MAX_TOTAL_BYTES:
                raise NativeMapError("Native collection exceeds the total size limit")
        return files

    def _stable(self, map_id, allow_missing=False):
        names = self._inventory(map_id, allow_missing=allow_missing)
        first = self._read_once(names, allow_empty=allow_missing)
        if names != self._inventory(map_id, allow_missing=allow_missing) or first != self._read_once(names, allow_empty=allow_missing):
            raise NativeMapError("Native files changed during capture")
        if names != self._inventory(map_id, allow_missing=allow_missing):
            raise NativeMapError("Native inventory changed during capture")
        return first

    def read_pair(self, map_id, *, allow_missing=False):
        """Capture native bytes twice; allow_missing is for pre-restore safety only."""
        self._names(map_id)
        with self._lock:
            self._identity()
            return self._stable(map_id, allow_missing=allow_missing)

    def restore_pair(self, map_id, files, *, before_write=None):
        """Restore exact captured bytes; return the retained remote backup path.

        Input must contain the active scheme, shared index, every saved scheme, and
        present allowlisted companions. Missing live map files can be recovered;
        live-only filenames are refused. The unbinding marker is never written.
        Empty optional markers are accepted. This
        validates transport shape/size, not firmware binary semantics. Errors retain
        transaction originals even if automatic rollback fails.

        Only one retained transaction is permitted. Before another restore, an
        administrator must inspect it, acknowledge a completed transaction and
        manually remove that exact directory. Failed transactions require recovery
        first. No original data is deleted automatically to recover free space.
        """
        required = self._names(map_id)
        if before_write is not None and not callable(before_write):
            raise ValueError("before_write must be a synchronous callable")
        if (not isinstance(files, dict) or not set(required).issubset(files) or
                len(files) > self.MAX_FILES or
                any(not isinstance(n, str) or not self._allowed(n) or
                    type(v) is not bytes or len(v) > self.MAX_FILE_BYTES or
                    (not v and n not in self.COMPANIONS) for n, v in files.items()) or
                sum(map(len, files.values())) > self.MAX_TOTAL_BYTES):
            raise ValueError("A complete bounded native collection is required")
        # Freeze the mapping before any network operation.
        files = dict(files)
        names = tuple(sorted(files))
        txn = f"{self.ROOT}/.conga-map-{uuid.uuid4().hex}"
        with self._lock:
            self._identity()
            originals = self._stable(map_id, allow_missing=True)
            if set(originals) - set(files):
                raise NativeMapError("Live native filename set has extra files; preserve them before restore")
            flag = "first_hardware_unbunding_flag.ini"
            if originals.get(flag) != files.get(flag):
                raise NativeMapError("Hardware unbinding marker differs; restore refused")
            names = tuple(n for n in names if n != flag)
            script = self._restore_script(names, files, originals, txn)
            if before_write is not None:
                before_write()
            try:
                result = self._run("sh -s", script.encode("ascii"))
            except NativeMapError as exc:
                raise NativeMapError(f"Native restore failed; inspect retained backup {txn}") from exc
            if result == b"blocked-existing\n":
                raise NativeMapError(
                    f"A retained native transaction exists in {self.ROOT}/.conga-map-*. "
                    "An administrator must recover failed transactions or inspect and manually "
                    "remove an acknowledged completed transaction before another restore")
            if result == b"blocked-sha256\n":
                raise NativeMapError("Robot lacks sha256sum; native restore is blocked before staging or replacing files")
            if result == b"blocked-space\n":
                raise NativeMapError("Insufficient free log-partition space for originals, staging, "
                                     "rollback and 16 MiB headroom; restore refused before staging")
            if result != b"restored\n":
                raise NativeMapError(f"Native restore incomplete; inspect retained backup {txn}")
        return {"backup_path": txn, "files": list(names), "rebooted": False}

    def _restore_script(self, names, files, originals, txn):
        # BusyBox ash/base64/sha256sum/df -Pk suffice; no SFTP subsystem.
        # All destinations are generated here; the input keys never become paths.
        def verify(path, content):
            digest = hashlib.sha256(content).hexdigest()
            return [f"digest=$(sha256sum {path})", f'test "${{digest%% *}}" = {digest}']

        # Include allocation rounding per file, retained originals, stage data,
        # the largest rollback copy, and reserve 16 MiB for firmware activity.
        rounded = lambda n: ((n + 4095) // 4096) * 4096
        old_sizes = [rounded(len(originals[n])) for n in names if n in originals]
        needed = (sum(old_sizes) + sum(rounded(len(files[n])) for n in names) +
                  max(old_sizes, default=0) + 16 * 1024 * 1024 + 64 * 1024)
        needed_kb = (needed + 1023) // 1024
        lines = ["set -eu", "umask 077", self._guard(),
                 f"mkdir {self.ROOT}/.conga-map-lock || exit 1",
                 "changed=0", "success=0",
                 "finish() {", "rc=$?", "trap - 0 1 2 15", "set +e",
                 'if [ "$changed" = 1 ] && [ "$success" != 1 ]; then']
        for i, name in enumerate(names):
            if name in originals:
                lines.append(f"cp -p {txn}/original{i} {txn}/rollback{i} && "
                             f"mv -f {txn}/rollback{i} {self.ROOT}/{name}")
            else:
                lines.append(f"rm -f {self.ROOT}/{name}")
        lines += ["fi", f"rmdir {self.ROOT}/.conga-map-lock", 'exit "$rc"', "}",
                  "trap finish 0", "trap 'exit 1' 1 2 15",
                  f"for prior in {self.ROOT}/.conga-map-*; do",
                  f'test "$prior" = {self.ROOT}/.conga-map-lock && continue',
                  'if [ -e "$prior" ] || [ -L "$prior" ]; then',
                  "printf 'blocked-existing\\n'; exit 0", "fi", "done",
                  "if ! command -v sha256sum >/dev/null; then",
                  "printf 'blocked-sha256\\n'; exit 0", "fi",
                  f"set -- $(df -Pk {self.ROOT} | tail -n 1)",
                  'test "$#" -ge 6', 'available_kb=$4',
                  'case "$available_kb" in ""|*[!0-9]*) exit 1 ;; esac',
                  f'if [ "$available_kb" -lt {needed_kb} ]; then',
                  "printf 'blocked-space\\n'; exit 0", "fi",
                  f"mkdir {txn}",
                  f"printf '%s\\n' {' '.join(names)} > {txn}/files",
                  f": > {txn}/absent"]
        for i, name in enumerate(names):
            path = f"{self.ROOT}/{name}"
            if name in originals:
                lines += [f"test -f {path} && test ! -L {path} || exit 1",
                          f"cp -p {path} {txn}/original{i}"]
            else:
                lines += [f"test ! -e {path} && test ! -L {path} || exit 1",
                          f"printf '%s\\n' {name} >> {txn}/absent"]
            if name in originals:
                lines += verify(f"{txn}/original{i}", originals[name])
                lines += [f"cp -p {txn}/original{i} {txn}/new{i}"]
            encoded = base64.b64encode(files[name]).decode("ascii")
            lines += [f"base64 -d > {txn}/new{i} <<'CONGA_DATA'", encoded, "CONGA_DATA"]
            lines += verify(f"{txn}/new{i}", files[name])
            if name in originals:
                lines += [f"touch -r {txn}/original{i} {txn}/new{i}"]
        # Refuse a newly appearing map/companion before committing any rename.
        patterns = " ".join(f"{self.ROOT}/{n}" for n in
                            ("scheme_data.info[0-9]*", "customer_map_list_path.plan") + self.COMPANIONS)
        accepted = "|".join(originals) or "__no_native_files__"
        lines += ["count=0", f"for p in {patterns}; do",
                  'if [ -e "$p" ] || [ -L "$p" ]; then',
                  'test -f "$p" && test ! -L "$p" || exit 1',
                  f'case "${{p##*/}}" in {accepted}) ;; *) exit 1 ;; esac',
                  'count=$((count + 1))', "fi", "done",
                  f'test "$count" -eq {len(originals)}']
        # Check original bytes and absent destinations immediately before commit.
        for i, name in enumerate(names):
            if name in originals:
                lines += [f"test -f {self.ROOT}/{name} && test ! -L {self.ROOT}/{name} || exit 1",
                          f"cmp -s {self.ROOT}/{name} {txn}/original{i}"]
            else:
                lines += [f"test ! -e {self.ROOT}/{name} && test ! -L {self.ROOT}/{name} || exit 1"]
        flag = "first_hardware_unbunding_flag.ini"
        if flag in originals:
            lines += verify(f"{self.ROOT}/{flag}", originals[flag])
        lines += ["changed=1"]
        for i, name in enumerate(names):
            lines += [f"mv -f {txn}/new{i} {self.ROOT}/{name}"]
        for i, name in enumerate(names):
            lines += verify(f"{self.ROOT}/{name}", files[name])
        lines += [f"touch {txn}/complete", "success=1", "printf 'restored\\n'"]
        return "\n".join(lines) + "\n"
