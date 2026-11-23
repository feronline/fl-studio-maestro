"""Minimal SysEx-capable MIDI port access.

Windows: winmm via ctypes (no dependencies; works on every Python version).
Elsewhere: python-rtmidi if installed (`pip install python-rtmidi`).
"""

from __future__ import annotations

import queue
import sys
import time


class PortError(RuntimeError):
    pass


def _match(names: list[str], wanted: str) -> int:
    for i, n in enumerate(names):
        if n == wanted:
            return i
    for i, n in enumerate(names):  # some drivers append " 1", " [1]"...
        if n.startswith(wanted) and not n[len(wanted):].strip().lower().startswith("reply"):
            return i
    raise PortError(f"MIDI port {wanted!r} not found. Available: {', '.join(names) or 'none'}")


# ============================================================================ Windows
if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _winmm = ctypes.WinDLL("winmm")
    _kernel32 = ctypes.WinDLL("kernel32")
    HANDLE = ctypes.c_void_p
    CALLBACK_EVENT = 0x50000
    MHDR_DONE = 0x1

    class MIDIOUTCAPSW(ctypes.Structure):
        _fields_ = [("wMid", wintypes.WORD), ("wPid", wintypes.WORD), ("vDriverVersion", wintypes.UINT),
                    ("szPname", wintypes.WCHAR * 32), ("wTechnology", wintypes.WORD), ("wVoices", wintypes.WORD),
                    ("wNotes", wintypes.WORD), ("wChannelMask", wintypes.WORD), ("dwSupport", wintypes.DWORD)]

    class MIDIINCAPSW(ctypes.Structure):
        _fields_ = [("wMid", wintypes.WORD), ("wPid", wintypes.WORD), ("vDriverVersion", wintypes.UINT),
                    ("szPname", wintypes.WCHAR * 32), ("dwSupport", wintypes.DWORD)]

    class MIDIHDR(ctypes.Structure):
        pass

    MIDIHDR._fields_ = [("lpData", ctypes.c_void_p), ("dwBufferLength", wintypes.DWORD),
                        ("dwBytesRecorded", wintypes.DWORD), ("dwUser", ctypes.c_size_t),
                        ("dwFlags", wintypes.DWORD), ("lpNext", ctypes.POINTER(MIDIHDR)),
                        ("reserved", ctypes.c_size_t), ("dwOffset", wintypes.DWORD),
                        ("dwReserved", ctypes.c_size_t * 8)]

    def _sig(fn, *args):
        f = getattr(_winmm, fn)
        f.argtypes, f.restype = list(args), wintypes.UINT
        return f

    midiOutGetNumDevs = _sig("midiOutGetNumDevs")
    midiOutGetDevCapsW = _sig("midiOutGetDevCapsW", ctypes.c_size_t, ctypes.POINTER(MIDIOUTCAPSW), wintypes.UINT)
    midiOutOpen = _sig("midiOutOpen", ctypes.POINTER(HANDLE), wintypes.UINT, ctypes.c_size_t, ctypes.c_size_t, wintypes.DWORD)
    midiOutPrepareHeader = _sig("midiOutPrepareHeader", HANDLE, ctypes.POINTER(MIDIHDR), wintypes.UINT)
    midiOutUnprepareHeader = _sig("midiOutUnprepareHeader", HANDLE, ctypes.POINTER(MIDIHDR), wintypes.UINT)
    midiOutLongMsg = _sig("midiOutLongMsg", HANDLE, ctypes.POINTER(MIDIHDR), wintypes.UINT)
    midiOutClose = _sig("midiOutClose", HANDLE)
    midiInGetNumDevs = _sig("midiInGetNumDevs")
    midiInGetDevCapsW = _sig("midiInGetDevCapsW", ctypes.c_size_t, ctypes.POINTER(MIDIINCAPSW), wintypes.UINT)
    midiInOpen = _sig("midiInOpen", ctypes.POINTER(HANDLE), wintypes.UINT, ctypes.c_size_t, ctypes.c_size_t, wintypes.DWORD)
    midiInPrepareHeader = _sig("midiInPrepareHeader", HANDLE, ctypes.POINTER(MIDIHDR), wintypes.UINT)
    midiInUnprepareHeader = _sig("midiInUnprepareHeader", HANDLE, ctypes.POINTER(MIDIHDR), wintypes.UINT)
    midiInAddBuffer = _sig("midiInAddBuffer", HANDLE, ctypes.POINTER(MIDIHDR), wintypes.UINT)
    midiInStart = _sig("midiInStart", HANDLE)
    midiInReset = _sig("midiInReset", HANDLE)
    midiInClose = _sig("midiInClose", HANDLE)
    _kernel32.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, ctypes.c_wchar_p]
    _kernel32.CreateEventW.restype = HANDLE
    _kernel32.WaitForSingleObject.argtypes = [HANDLE, wintypes.DWORD]
    _kernel32.CloseHandle.argtypes = [HANDLE]

    def _check(code: int, what: str) -> None:
        if code:
            raise PortError(f"{what} failed (MMRESULT {code}); is another program holding the port?")

    def output_names() -> list[str]:
        out = []
        for i in range(midiOutGetNumDevs()):
            caps = MIDIOUTCAPSW()
            midiOutGetDevCapsW(i, ctypes.byref(caps), ctypes.sizeof(caps))
            out.append(caps.szPname)
        return out

    def input_names() -> list[str]:
        out = []
        for i in range(midiInGetNumDevs()):
            caps = MIDIINCAPSW()
            midiInGetDevCapsW(i, ctypes.byref(caps), ctypes.sizeof(caps))
            out.append(caps.szPname)
        return out

    class Output:
        def __init__(self, name: str):
            self.h = HANDLE()
            _check(midiOutOpen(ctypes.byref(self.h), _match(output_names(), name), 0, 0, 0), f"opening output {name!r}")

        def send(self, data: bytes) -> None:
            buf = ctypes.create_string_buffer(data, len(data))
            hdr = MIDIHDR(lpData=ctypes.cast(buf, ctypes.c_void_p), dwBufferLength=len(data))
            size = ctypes.sizeof(MIDIHDR)
            _check(midiOutPrepareHeader(self.h, ctypes.byref(hdr), size), "midiOutPrepareHeader")
            try:
                _check(midiOutLongMsg(self.h, ctypes.byref(hdr), size), "midiOutLongMsg")
                deadline = time.monotonic() + 2
                while not hdr.dwFlags & MHDR_DONE and time.monotonic() < deadline:
                    time.sleep(0.001)
            finally:
                while midiOutUnprepareHeader(self.h, ctypes.byref(hdr), size) == 65:  # MIDIERR_STILLPLAYING
                    time.sleep(0.001)

        def close(self) -> None:
            if self.h:
                midiOutClose(self.h)
                self.h = HANDLE()

    class Input:
        BUFFERS, SIZE = 16, 4096

        def __init__(self, name: str):
            self.event = _kernel32.CreateEventW(None, False, False, None)
            self.h = HANDLE()
            _check(midiInOpen(ctypes.byref(self.h), _match(input_names(), name), self.event, 0, CALLBACK_EVENT),
                   f"opening input {name!r}")
            self.bufs, self.hdrs = [], []
            for _ in range(self.BUFFERS):
                buf = ctypes.create_string_buffer(self.SIZE)
                hdr = MIDIHDR(lpData=ctypes.cast(buf, ctypes.c_void_p), dwBufferLength=self.SIZE)
                _check(midiInPrepareHeader(self.h, ctypes.byref(hdr), ctypes.sizeof(MIDIHDR)), "midiInPrepareHeader")
                _check(midiInAddBuffer(self.h, ctypes.byref(hdr), ctypes.sizeof(MIDIHDR)), "midiInAddBuffer")
                self.bufs.append(buf)
                self.hdrs.append(hdr)
            self.pending: list[bytes] = []
            _check(midiInStart(self.h), "midiInStart")

        def _collect(self) -> None:
            for buf, hdr in zip(self.bufs, self.hdrs):
                if hdr.dwFlags & MHDR_DONE:
                    if hdr.dwBytesRecorded:
                        self.pending.append(buf.raw[:hdr.dwBytesRecorded])
                    hdr.dwBytesRecorded = 0
                    midiInAddBuffer(self.h, ctypes.byref(hdr), ctypes.sizeof(MIDIHDR))

        def receive(self, timeout: float) -> bytes | None:
            deadline = time.monotonic() + timeout
            while True:
                self._collect()
                if self.pending:
                    return self.pending.pop(0)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                _kernel32.WaitForSingleObject(self.event, max(1, min(50, int(remaining * 1000))))

        def close(self) -> None:
            if self.h:
                midiInReset(self.h)
                for hdr in self.hdrs:
                    midiInUnprepareHeader(self.h, ctypes.byref(hdr), ctypes.sizeof(MIDIHDR))
                midiInClose(self.h)
                self.h = HANDLE()
            if self.event:
                _kernel32.CloseHandle(self.event)
                self.event = None

# ============================================================================ rtmidi (macOS / Linux)
else:
    def _rtmidi():
        try:
            import rtmidi  # type: ignore
        except ImportError:
            raise PortError("MIDI on this platform needs python-rtmidi: pip install python-rtmidi") from None
        return rtmidi

    def output_names() -> list[str]:
        return _rtmidi().MidiOut().get_ports()

    def input_names() -> list[str]:
        return _rtmidi().MidiIn().get_ports()

    class Output:
        def __init__(self, name: str):
            self.port = _rtmidi().MidiOut()
            self.port.open_port(_match(self.port.get_ports(), name))

        def send(self, data: bytes) -> None:
            self.port.send_message(list(data))

        def close(self) -> None:
            self.port.close_port()

    class Input:
        def __init__(self, name: str):
            self.port = _rtmidi().MidiIn()
            self.port.ignore_types(sysex=False, timing=True, active_sense=True)
            self.q: queue.Queue[bytes] = queue.Queue()
            self.port.set_callback(lambda msg, _: self.q.put(bytes(msg[0])))
            self.port.open_port(_match(self.port.get_ports(), name))

        def receive(self, timeout: float) -> bytes | None:
            try:
                return self.q.get(timeout=timeout)
            except queue.Empty:
                return None

        def close(self) -> None:
            self.port.close_port()
