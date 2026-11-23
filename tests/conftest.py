import importlib.util
import socket
import sys
import threading
import time
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DEVICE_SCRIPT = ROOT / "src" / "fl_maestro" / "fl_scripts" / "device_MaestroBridge.py"


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path, monkeypatch):
    monkeypatch.setenv("FL_MAESTRO_HOME", str(tmp_path / "projects"))
    monkeypatch.setenv("FL_MAESTRO_IPC_DIR", str(tmp_path / "no-bridge"))
    monkeypatch.setenv("FL_MAESTRO_FL_USER_DIR", str(tmp_path / "FL Studio"))
    return tmp_path


class FakeFL:
    """A tiny in-memory FL Studio exposing the MIDI scripting modules the bridge uses."""

    def __init__(self):
        self.tempo = 140.0
        self.playing = False
        self.channels = [{"name": f"Channel {i}", "vol": 0.78, "pan": 0.0, "fx": 0, "color": 0} for i in range(4)]
        self.mixer = [{"name": "Master" if i == 0 else f"Insert {i}", "vol": 0.8, "pan": 0.0, "sep": 0.0,
                       "muted": False, "color": 0, "routes": {0} if i else set()} for i in range(10)]
        self.patterns = {i: f"Pattern {i}" for i in range(1, 11)}
        self.current_pattern = 1
        self.selected_channel = None
        self.window = None
        self.saved = False
        self.params = {(0, -1): [0.5, 0.25]}

    def modules(self):
        fl = self
        m = {}
        m["midi"] = types.SimpleNamespace(REC_Tempo=0x4005, REC_Control=1, REC_UpdateControl=16,
                                          FPT_Save=92, widPianoRoll=3)

        def process(rec, value, flags):
            if rec == 0x4005:
                fl.tempo = value / 1000
        m["general"] = types.SimpleNamespace(getVersion=lambda: 40, processRECEvent=process)
        m["transport"] = types.SimpleNamespace(
            isPlaying=lambda: fl.playing, start=lambda: setattr(fl, "playing", True),
            stop=lambda: setattr(fl, "playing", False), record=lambda: None, setSongPos=lambda p: None,
            setLoopMode=lambda: None, getLoopMode=lambda: 0,
            globalTransport=lambda cmd, val: setattr(fl, "saved", cmd == 92))
        ch = fl.channels

        def ch_db(i, mode=0):
            return 20 * (ch[i]["vol"] - 0.78) if mode else ch[i]["vol"]
        m["channels"] = types.SimpleNamespace(
            channelCount=lambda: len(ch), getChannelName=lambda i: ch[i]["name"],
            setChannelName=lambda i, n: ch[i].__setitem__("name", n),
            setChannelColor=lambda i, c: ch[i].__setitem__("color", c), getChannelColor=lambda i: ch[i]["color"],
            setChannelPan=lambda i, p: ch[i].__setitem__("pan", p), getChannelPan=lambda i: ch[i]["pan"],
            setChannelVolume=lambda i, v: ch[i].__setitem__("vol", v), getChannelVolume=ch_db,
            setTargetFxTrack=lambda i, t: ch[i].__setitem__("fx", t), getTargetFxTrack=lambda i: ch[i]["fx"],
            selectOneChannel=lambda i: setattr(fl, "selected_channel", i))
        mx = fl.mixer

        def mx_vol(i, mode=0):
            return 40 * (mx[i]["vol"] - 0.8) if mode else mx[i]["vol"]

        def route(src, dst, on):
            (mx[src]["routes"].add if on else mx[src]["routes"].discard)(dst)
        m["mixer"] = types.SimpleNamespace(
            trackCount=lambda: len(mx), getTrackName=lambda i: mx[i]["name"],
            setTrackName=lambda i, n: mx[i].__setitem__("name", n),
            setTrackColor=lambda i, c: mx[i].__setitem__("color", c),
            setTrackPan=lambda i, p: mx[i].__setitem__("pan", p), getTrackPan=lambda i: mx[i]["pan"],
            setTrackStereoSep=lambda i, s: mx[i].__setitem__("sep", s),
            setTrackVolume=lambda i, v: mx[i].__setitem__("vol", v), getTrackVolume=mx_vol,
            isTrackMuted=lambda i: mx[i]["muted"], muteTrack=lambda i: mx[i].__setitem__("muted", not mx[i]["muted"]),
            getRouteSendActive=lambda s, d: d in mx[s]["routes"], setRouteTo=route,
            afterRoutingChanged=lambda: None, getCurrentTempo=lambda: int(fl.tempo * 1000))
        m["patterns"] = types.SimpleNamespace(
            patternCount=lambda: len(fl.patterns), getPatternName=lambda i: fl.patterns[i],
            setPatternName=lambda i, n: fl.patterns.__setitem__(i, n), setPatternColor=lambda i, c: None,
            getPatternLength=lambda i: 16, patternNumber=lambda: fl.current_pattern,
            jumpToPattern=lambda i: setattr(fl, "current_pattern", i))
        m["playlist"] = types.SimpleNamespace(trackCount=lambda: 3, getTrackName=lambda i: f"Track {i}",
                                              setTrackName=lambda i, n: None, setTrackColor=lambda i, c: None)

        def valid(index, slot=-1):
            return (index, slot) in fl.params

        def setp(value, p, index, slot):
            fl.params[(index, slot)][p] = value
        m["plugins"] = types.SimpleNamespace(
            isValid=valid, getPluginName=lambda i, s=-1: "FLEX", getParamCount=lambda i, s: len(fl.params[(i, s)]),
            getParamName=lambda p, i, s: ["Cutoff", "Resonance"][p], getParamValue=lambda p, i, s: fl.params[(i, s)][p],
            getParamValueString=lambda p, i, s: f"{fl.params[(i, s)][p] * 100:.0f}%", setParamValue=setp)
        m["ui"] = types.SimpleNamespace(showWindow=lambda w: setattr(fl, "window", w))
        return m


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(params=["udp", "file"])
def fake_fl(request, monkeypatch, tmp_path):
    """Load the real device script against FakeFL and pump OnIdle in a thread, like FL does.

    Runs every bridge test twice: over UDP, and over the file transport used when FL blocks sockets.
    """
    fl = FakeFL()
    ipc = tmp_path / "bridge"
    monkeypatch.setenv("FL_MAESTRO_IPC_DIR", str(ipc))
    for name, mod in fl.modules().items():
        monkeypatch.setitem(sys.modules, name, mod)
    spec = importlib.util.spec_from_file_location("device_MaestroBridge", DEVICE_SCRIPT)
    device = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(device)
    device.PORT = _free_port()
    device.IPC_CANDIDATES = [str(ipc)]
    device.FORCE_FILE_TRANSPORT = request.param == "file"
    device.OnInit()
    assert device._transport == request.param
    stop = threading.Event()

    def pump():
        while not stop.is_set():
            device.OnIdle()
            time.sleep(0.002)
    thread = threading.Thread(target=pump, daemon=True)
    thread.start()
    monkeypatch.setenv("FL_MAESTRO_PORT", str(device.PORT))
    fl.port = device.PORT
    yield fl
    stop.set()
    thread.join(1)
    device.OnDeInit()
