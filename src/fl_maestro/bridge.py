"""Client for the Maestro Bridge device script running inside FL Studio (UDP on localhost)."""

from __future__ import annotations

import itertools
import json
import os
import socket
import time
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


class Bridge:
    def __init__(self, host: str = "127.0.0.1", port: int | None = None, timeout: float | None = None):
        self.host = host
        self.port = port or int(os.environ.get("FL_MAESTRO_PORT", DEFAULT_PORT))
        self.timeout = timeout or float(os.environ.get("FL_MAESTRO_TIMEOUT", 3.0))
        self._ids = itertools.count(1)

    def call(self, cmd: str, timeout: float | None = None, **args: Any) -> Any:
        req_id = next(self._ids)
        payload = json.dumps({"id": req_id, "cmd": cmd, "args": args}, ensure_ascii=True).encode("ascii")
        deadline = time.monotonic() + (timeout or self.timeout)
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
                if not reply.get("ok"):
                    raise BridgeError(f"FL Studio rejected '{cmd}': {reply.get('error')}")
                return reply.get("result")
