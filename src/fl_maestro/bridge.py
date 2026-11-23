"""Client for the Maestro Bridge device script running inside FL Studio.

FL Studio's embedded Python blocks sockets and file writes in controller scripts,
so the bridge talks MIDI SysEx over two virtual ports (loopMIDI on Windows, IAC on macOS):
  "Maestro"        server -> FL   (FL input, controller type "Maestro Bridge")
  "Maestro Reply"  FL -> server   (FL output, same port number as the input)
"""

from __future__ import annotations

import json
import os
import random
import threading
import time
from typing import Any, Callable

from . import sysex

SETUP_HINT = (
    "FL Studio is not answering on the Maestro Bridge. Check that: (1) FL Studio is open; "
    "(2) loopMIDI has two ports, 'Maestro' and 'Maestro Reply'; (3) in FL Studio, Options > MIDI settings, "
    "the INPUT 'Maestro' is enabled with controller type 'Maestro Bridge' and a port number (e.g. 10), and the "
    "OUTPUT 'Maestro Reply' has the SAME port number; (4) View > Script output says 'Maestro Bridge ... ready'. "
    "Offline tools (create_project, write_pattern, review_project, arrange, export_project) work without FL Studio."
)


class BridgeError(RuntimeError):
    pass


def to_fl_port() -> str:
    return os.environ.get("FL_MAESTRO_TO_FL_PORT", "Maestro")


def from_fl_port() -> str:
    return os.environ.get("FL_MAESTRO_FROM_FL_PORT", "Maestro Reply")


def _default_ports() -> tuple[Any, Any]:
    from . import midiports
    try:
        inp = midiports.Input(from_fl_port())
    except midiports.PortError as exc:
        raise BridgeError(f"{exc}\n\n{SETUP_HINT}") from None
    try:
        out = midiports.Output(to_fl_port())
    except midiports.PortError as exc:
        inp.close()
        raise BridgeError(f"{exc}\n\n{SETUP_HINT}") from None
    return out, inp


class Bridge:
    """Each call opens the ports, sends one request and waits for the matching reply.

    `ports` is a factory returning (output, input) objects; tests pass an in-memory pair.
    """

    _lock = threading.Lock()

    def __init__(self, timeout: float | None = None, ports: Callable[[], tuple[Any, Any]] | None = None):
        self.timeout = timeout or float(os.environ.get("FL_MAESTRO_TIMEOUT", 4.0))
        self.ports = ports

    def call(self, cmd: str, timeout: float | None = None, **args: Any) -> Any:
        msg_id = random.randrange(1, 1 << 21)
        payload = json.dumps({"id": msg_id, "cmd": cmd, "args": args}, ensure_ascii=True).encode("ascii")
        with self._lock:
            out, inp = (self.ports or _default_ports)()
            try:
                for frame in sysex.encode(sysex.REQUEST, msg_id, payload):
                    out.send(frame)
                reply = self._wait(inp, msg_id, timeout or self.timeout)
            finally:
                out.close()
                inp.close()
        if not reply.get("ok"):
            raise BridgeError(f"FL Studio rejected '{cmd}': {reply.get('error')}")
        return reply.get("result")

    @staticmethod
    def _wait(inp: Any, msg_id: int, timeout: float) -> dict[str, Any]:
        assembler = sysex.Assembler()
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise BridgeError(SETUP_HINT)
            message = inp.receive(remaining)
            if message is None:
                continue
            done = assembler.add(message, sysex.REPLY)
            if done and done[0] == msg_id:
                return json.loads(done[1].decode("ascii"))
