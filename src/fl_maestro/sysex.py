"""SysEx framing shared with the device script (which keeps its own copy, since FL loads it standalone).

Message: F0 7D 4D 53 <dir> <id0 id1 id2> <idx0 idx1> <tot0 tot1> <payload ASCII JSON> F7
  7D       = non-commercial manufacturer id
  4D 53    = "MS" (Maestro)
  dir      = 01 request (server -> FL), 02 reply (FL -> server)
  id       = 21-bit message id, 7 bits per byte
  idx/tot  = 14-bit chunk index and chunk count
"""

from __future__ import annotations

HEADER = bytes([0xF0, 0x7D, 0x4D, 0x53])
REQUEST, REPLY = 0x01, 0x02
CHUNK = 240  # payload bytes per SysEx message


def _b7(value: int, n: int) -> bytes:
    return bytes((value >> (7 * i)) & 0x7F for i in range(n))


def _u7(data: bytes) -> int:
    return sum(b << (7 * i) for i, b in enumerate(data))


def encode(direction: int, msg_id: int, payload: bytes) -> list[bytes]:
    if any(b > 0x7F for b in payload):
        raise ValueError("SysEx payload must be 7-bit (ASCII JSON)")
    chunks = [payload[i:i + CHUNK] for i in range(0, len(payload), CHUNK)] or [b""]
    total = len(chunks)
    return [HEADER + bytes([direction]) + _b7(msg_id, 3) + _b7(i, 2) + _b7(total, 2) + c + b"\xF7"
            for i, c in enumerate(chunks)]


def decode(message: bytes) -> tuple[int, int, int, int, bytes] | None:
    """-> (direction, msg_id, index, total, payload), or None if not a Maestro message."""
    if len(message) < 13 or message[:4] != HEADER or message[-1] != 0xF7:
        return None
    return message[4], _u7(message[5:8]), _u7(message[8:10]), _u7(message[10:12]), bytes(message[12:-1])


class Assembler:
    """Collects chunks until a whole message has arrived."""

    def __init__(self) -> None:
        self.parts: dict[int, dict[int, bytes]] = {}

    def add(self, message: bytes, direction: int) -> tuple[int, bytes] | None:
        frame = decode(message)
        if frame is None or frame[0] != direction:
            return None
        _, msg_id, idx, total, payload = frame
        got = self.parts.setdefault(msg_id, {})
        got[idx] = payload
        if len(got) < total:
            return None
        del self.parts[msg_id]
        return msg_id, b"".join(got[i] for i in range(total))
