"""Client for the Maestro Bridge device script running inside FL Studio.

The device script announces its transport in ~/FLMaestro/.bridge/status.json:
"udp" (localhost datagrams) or "file" (request/response files in that folder,
for FL builds whose embedded Python blocks sockets).
"""

from __future__ import annotations

import itertools
import json
import os
import socket
import time
import uuid
from pathlib import Path
from typing import Any

DEFAULT_PORT = 47391

SETUP_HINT = (
    "FL Studio is not answering on the Maestro Bridge. Check that: (1) FL Studio is open; "
    "(2) `fl-maestro setup` has been run, so the 'Maestro Bridge' script is installed; "
    "(3) in FL Studio, Options > MIDI settings, a MIDI input (for example the loopMIDI port "
    "'Maestro') is enabled with controller type 'Maestro Bridge'. Offline tools (create_project, "
    "write_pattern, review_project, arrange, export_project) work without FL Studio."
)


class BridgeError(RuntimeError):
    pass


def ipc_candidates() -> list[Path]:
    """Same order as IPC_CANDIDATES in the device script."""
    override = os.environ.get("FL_MAESTRO_IPC_DIR")
    if override:
        return [Path(override)]
    from . import paths
    temp = os.environ.get("TEMP") or os.environ.get("TMPDIR")
    out = [Path.home() / "FLMaestro" / ".bridge", paths.hardware_dir() / "Maestro Bridge" / "ipc"]
    if temp:
        out.append(Path(temp) / "fl-maestro-bridge")
    return out


def _find_status() -> tuple[Path, dict[str, Any]] | None:
    found = []
    for folder in ipc_candidates():
        try:
            status = json.loads((folder / "status.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        found.append((status.get("started", 0), folder, status))
    if not found:
        return None
    _, folder, status = max(found, key=lambda f: f[0])
    return folder, status


def ipc_dir() -> Path:
    hit = _find_status()
    return hit[0] if hit else ipc_candidates()[0]


def bridge_status() -> dict[str, Any] | None:
    hit = _find_status()
    return hit[1] if hit else None


class Bridge:
    def __init__(self, host: str = "127.0.0.1", port: int | None = None, timeout: float | None = None):
        self.host = host
        self.port = port or int(os.environ.get("FL_MAESTRO_PORT", DEFAULT_PORT))
        self.timeout = timeout or float(os.environ.get("FL_MAESTRO_TIMEOUT", 3.0))
        self._ids = itertools.count(1)

    def call(self, cmd: str, timeout: float | None = None, **args: Any) -> Any:
        status = bridge_status()
        if status and status.get("transport") == "file":
            reply = self._call_file(cmd, args, timeout or self.timeout)
        else:
            reply = self._call_udp(cmd, args, timeout or self.timeout)
        if not reply.get("ok"):
            raise BridgeError(f"FL Studio rejected '{cmd}': {reply.get('error')}")
        return reply.get("result")

    def _call_file(self, cmd: str, args: dict[str, Any], timeout: float) -> dict[str, Any]:
        folder = ipc_dir()
        req_id = f"{time.time_ns()}-{uuid.uuid4().hex[:8]}"
        req, resp = folder / f"req-{req_id}.json", folder / f"resp-{req_id}.json"
        tmp = folder / f"req-{req_id}.tmp"
        tmp.write_text(json.dumps({"id": req_id, "cmd": cmd, "args": args}, ensure_ascii=True), encoding="utf-8")
        os.replace(tmp, req)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if resp.exists():
                try:
                    reply = json.loads(resp.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    time.sleep(0.005)
                    continue
                resp.unlink(missing_ok=True)
                return reply
            time.sleep(0.005)
        req.unlink(missing_ok=True)
        raise BridgeError(SETUP_HINT)

    def _call_udp(self, cmd: str, args: dict[str, Any], timeout: float) -> dict[str, Any]:
        req_id = next(self._ids)
        payload = json.dumps({"id": req_id, "cmd": cmd, "args": args}, ensure_ascii=True).encode("ascii")
        deadline = time.monotonic() + timeout
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.bind((self.host, 0))
            sock.sendto(payload, (self.host, self.port))
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise BridgeError(SETUP_HINT)
                sock.settimeout(remaining)
                try:
                    data, _ = sock.recvfrom(65535)
                except socket.timeout:
                    raise BridgeError(SETUP_HINT) from None
                except ConnectionResetError:  # Windows: nothing listening on the port
                    raise BridgeError(SETUP_HINT) from None
                reply = json.loads(data.decode("utf-8"))
                if reply.get("id") != req_id:
                    continue  # a late reply to an earlier request
                return reply
