# name=Maestro Bridge
# url=https://github.com/feronline/fl-studio-maestro
"""FL Studio side of fl-studio-maestro.

Receives JSON commands from the fl-maestro MCP server as MIDI SysEx and runs
them with FL Studio's MIDI scripting API. (FL's embedded Python blocks sockets
and file writes inside controller scripts, so MIDI is the only channel.)

Setup in Options > MIDI settings:
  INPUT  "Maestro"        enabled, controller type "Maestro Bridge", port number N
  OUTPUT "Maestro Reply"  port number N (the same), so replies can be sent back
"""

import json
import math

import channels
import device
import general
import midi
import mixer
import patterns
import playlist
import plugins
import transport
import ui

BRIDGE_VERSION = "0.3.0"

# SysEx framing (keep in sync with fl_maestro/sysex.py)
HEADER = bytes([0xF0, 0x7D, 0x4D, 0x53])
REQUEST, REPLY = 0x01, 0x02
CHUNK = 240

_parts = {}


# ----------------------------------------------------------------- helpers
def _color(value):
    if isinstance(value, str):
        value = int(value.lstrip("#"), 16)
    return int(value) & 0xFFFFFF


def _hex(color):
    return "#%06x" % (int(color) & 0xFFFFFF)


def _try(fn, *args, default=None):
    try:
        return fn(*args)
    except Exception:
        return default


def _search_volume(set_fn, get_db_fn, target_db):
    """Binary-search the normalized fader value whose dB reading matches target_db."""
    lo, hi = 0.0, 1.0
    for _ in range(24):
        mid = (lo + hi) / 2
        set_fn(mid)
        db = get_db_fn()
        if db is None or (isinstance(db, float) and math.isnan(db)):
            raise RuntimeError("this FL Studio version cannot report dB; pass a normalized volume instead")
        if db < target_db:
            lo = mid
        else:
            hi = mid
    set_fn((lo + hi) / 2)
    return get_db_fn()


def _track_db(index):
    return float(mixer.getTrackVolume(index, 1))


def _channel_db(index):
    return float(channels.getChannelVolume(index, 1))


def _tempo():
    t = _try(mixer.getCurrentTempo)
    if t is None:
        return None
    return t / 1000 if t > 1000 else t


# ----------------------------------------------------------------- commands
def cmd_ping(a):
    return {
        "bridge": BRIDGE_VERSION,
        "fl_version": _try(general.getVersion),
        "tempo": _tempo(),
        "playing": bool(_try(transport.isPlaying, default=False)),
        "channels": _try(channels.channelCount, default=0),
        "patterns": _try(patterns.patternCount, default=0),
        "current_pattern": _try(patterns.patternNumber),
        "mixer_tracks": _try(mixer.trackCount, default=0),
        "playlist_tracks": _try(playlist.trackCount, default=0),
    }


def _plugin_name(index, slot=-1):
    if _try(plugins.isValid, index, slot, default=False):
        return _try(plugins.getPluginName, index, slot)
    return None


def cmd_inspect(a):
    scope = a.get("scope", "channels")
    limit = int(a.get("limit", 32))
    rows = []
    if scope == "channels":
        for i in range(min(channels.channelCount(), limit)):
            rows.append({
                "index": i, "name": channels.getChannelName(i), "plugin": _plugin_name(i),
                "mixer_track": _try(channels.getTargetFxTrack, i),
                "volume": round(_try(channels.getChannelVolume, i, default=0), 4),
                "volume_db": _try(_channel_db, i),
                "pan": round(_try(channels.getChannelPan, i, default=0), 4),
                "color": _try(lambda: _hex(channels.getChannelColor(i))),
            })
    elif scope == "mixer":
        for i in range(min(mixer.trackCount(), limit)):
            slots = []
            for s in range(10):
                name = _plugin_name(i, s)
                if name:
                    slots.append({"slot": s, "plugin": name})
            rows.append({
                "index": i, "name": mixer.getTrackName(i),
                "volume": round(_try(mixer.getTrackVolume, i, default=0), 4),
                "volume_db": _try(_track_db, i), "pan": round(_try(mixer.getTrackPan, i, default=0), 4),
                "muted": bool(_try(mixer.isTrackMuted, i, default=False)), "effects": slots,
            })
    elif scope == "patterns":
        for i in range(1, min(patterns.patternCount(), limit) + 1):
            rows.append({"index": i, "name": patterns.getPatternName(i),
                         "length_beats": _try(patterns.getPatternLength, i)})
    elif scope == "playlist":
        for i in range(1, min(playlist.trackCount(), limit) + 1):
            rows.append({"index": i, "name": playlist.getTrackName(i)})
    else:
        raise ValueError("scope must be channels, mixer, patterns or playlist")
    return {"scope": scope, "rows": rows}


def cmd_set_tempo(a):
    bpm = float(a["bpm"])
    general.processRECEvent(midi.REC_Tempo, int(round(bpm * 1000)), midi.REC_Control | midi.REC_UpdateControl)
    return {"tempo": _tempo()}


def cmd_transport(a):
    action = a["action"]
    if action == "play":
        if not transport.isPlaying():
            transport.start()
    elif action == "stop":
        transport.stop()
    elif action == "record":
        transport.record()
    elif action == "rewind":
        transport.setSongPos(0)
    elif action == "toggle_song_mode":
        transport.setLoopMode()
    else:
        raise ValueError("unknown transport action")
    return {"playing": bool(transport.isPlaying()), "song_mode": _try(transport.getLoopMode)}


def cmd_channel(a):
    i = int(a["index"])
    if not 0 <= i < channels.channelCount():
        raise ValueError("channel %d does not exist (there are %d)" % (i, channels.channelCount()))
    if a.get("name") is not None:
        channels.setChannelName(i, a["name"])
    if a.get("color") is not None:
        channels.setChannelColor(i, _color(a["color"]))
    if a.get("pan") is not None:
        channels.setChannelPan(i, float(a["pan"]))
    if a.get("volume") is not None:
        channels.setChannelVolume(i, float(a["volume"]))
    if a.get("volume_db") is not None:
        _search_volume(lambda v: channels.setChannelVolume(i, v), lambda: _channel_db(i), float(a["volume_db"]))
    if a.get("mixer_track") is not None:
        channels.setTargetFxTrack(i, int(a["mixer_track"]))
    return cmd_inspect({"scope": "channels", "limit": 999})["rows"][i]


def cmd_mixer_track(a):
    i = int(a["index"])
    if not 0 <= i < mixer.trackCount():
        raise ValueError("mixer track %d does not exist" % i)
    if a.get("name") is not None:
        mixer.setTrackName(i, a["name"])
    if a.get("color") is not None:
        mixer.setTrackColor(i, _color(a["color"]))
    if a.get("pan") is not None:
        mixer.setTrackPan(i, float(a["pan"]))
    if a.get("stereo_separation") is not None:
        mixer.setTrackStereoSep(i, float(a["stereo_separation"]))
    if a.get("volume") is not None:
        mixer.setTrackVolume(i, float(a["volume"]))
    if a.get("volume_db") is not None:
        _search_volume(lambda v: mixer.setTrackVolume(i, v), lambda: _track_db(i), float(a["volume_db"]))
    if a.get("mute") is not None:
        if bool(mixer.isTrackMuted(i)) != bool(a["mute"]):
            mixer.muteTrack(i)
    if a.get("route_to") is not None:
        targets = [int(t) for t in a["route_to"]]
        if a.get("exclusive", True):
            for t in range(mixer.trackCount()):
                if t != i and t not in targets and _try(mixer.getRouteSendActive, i, t, default=False):
                    mixer.setRouteTo(i, t, False)
        for t in targets:
            mixer.setRouteTo(i, t, True)
        mixer.afterRoutingChanged()
    rows = cmd_inspect({"scope": "mixer", "limit": i + 1})["rows"]
    return rows[i]


def cmd_pattern(a):
    i = int(a["index"])
    if a.get("name") is not None:
        patterns.setPatternName(i, a["name"])
    if a.get("color") is not None:
        patterns.setPatternColor(i, _color(a["color"]))
    return {"index": i, "name": patterns.getPatternName(i)}


def cmd_playlist_track(a):
    i = int(a["index"])
    if a.get("name") is not None:
        playlist.setTrackName(i, a["name"])
    if a.get("color") is not None:
        playlist.setTrackColor(i, _color(a["color"]))
    return {"index": i, "name": playlist.getTrackName(i)}


def cmd_stage_pattern(a):
    pat, ch = int(a["pattern"]), int(a["channel"])
    if not 0 <= ch < channels.channelCount():
        raise ValueError("channel %d does not exist (there are %d): add the instrument first" % (ch, channels.channelCount()))
    patterns.jumpToPattern(pat)
    if a.get("pattern_name"):
        patterns.setPatternName(pat, a["pattern_name"])
    channels.selectOneChannel(ch)
    ui.showWindow(midi.widPianoRoll)
    return {"pattern": patterns.patternNumber(), "channel": ch, "channel_name": channels.getChannelName(ch)}


def _target(a):
    loc = a.get("location", "channel")
    index = int(a["index"])
    slot = -1 if loc == "channel" else int(a.get("slot", 0))
    if not plugins.isValid(index, slot):
        raise ValueError("no plugin at %s %d%s" % (loc, index, "" if slot < 0 else " slot %d" % slot))
    return index, slot


def cmd_plugin_params(a):
    index, slot = _target(a)
    count = plugins.getParamCount(index, slot)
    search = (a.get("search") or "").lower()
    limit = int(a.get("limit", 64))
    rows = []
    for p in range(count):
        name = plugins.getParamName(p, index, slot)
        if not name or (search and search not in name.lower()):
            continue
        rows.append({"param": p, "name": name, "value": round(plugins.getParamValue(p, index, slot), 4),
                     "display": _try(plugins.getParamValueString, p, index, slot)})
        if len(rows) >= limit:
            break
    return {"plugin": plugins.getPluginName(index, slot), "param_count": count, "params": rows}


def cmd_set_plugin_param(a):
    index, slot = _target(a)
    p = int(a["param"])
    plugins.setParamValue(float(a["value"]), p, index, slot)
    return {"param": p, "name": plugins.getParamName(p, index, slot),
            "value": round(plugins.getParamValue(p, index, slot), 4),
            "display": _try(plugins.getParamValueString, p, index, slot)}


def cmd_save(a):
    transport.globalTransport(midi.FPT_Save, 1)
    return {"saved": True}


COMMANDS = {
    "ping": cmd_ping, "inspect": cmd_inspect, "set_tempo": cmd_set_tempo, "transport": cmd_transport,
    "channel": cmd_channel, "mixer_track": cmd_mixer_track, "pattern": cmd_pattern,
    "playlist_track": cmd_playlist_track, "stage_pattern": cmd_stage_pattern,
    "plugin_params": cmd_plugin_params, "set_plugin_param": cmd_set_plugin_param, "save": cmd_save,
}


def handle(packet):
    req_id = None
    try:
        req = json.loads(packet.decode("utf-8"))
        req_id = req.get("id")
        fn = COMMANDS.get(req.get("cmd"))
        if fn is None:
            raise ValueError("unknown command %r" % req.get("cmd"))
        return {"id": req_id, "ok": True, "result": fn(req.get("args") or {})}
    except Exception as exc:  # report every failure back to the server
        return {"id": req_id, "ok": False, "error": "%s: %s" % (type(exc).__name__, exc)}


# ----------------------------------------------------------------- SysEx transport
def _b7(value, n):
    return bytes((value >> (7 * i)) & 0x7F for i in range(n))


def _u7(data):
    return sum(b << (7 * i) for i, b in enumerate(data))


def encode(direction, msg_id, payload):
    chunks = [payload[i:i + CHUNK] for i in range(0, len(payload), CHUNK)] or [b""]
    total = len(chunks)
    return [HEADER + bytes([direction]) + _b7(msg_id, 3) + _b7(i, 2) + _b7(total, 2) + c + bytes([0xF7])
            for i, c in enumerate(chunks)]


def receive(message):
    """Feed one SysEx message; returns (msg_id, payload) once a request is complete."""
    if len(message) < 13 or message[:4] != HEADER or message[-1] != 0xF7 or message[4] != REQUEST:
        return None
    msg_id, idx, total = _u7(message[5:8]), _u7(message[8:10]), _u7(message[10:12])
    got = _parts.setdefault(msg_id, {})
    got[idx] = bytes(message[12:-1])
    if len(got) < total:
        return None
    del _parts[msg_id]
    if len(_parts) > 64:  # drop abandoned partial messages
        _parts.clear()
    return msg_id, b"".join(got[i] for i in range(total))


def _send_reply(msg_id, reply):
    payload = json.dumps(reply, ensure_ascii=True).encode("ascii")
    for frame in encode(REPLY, msg_id, payload):
        device.midiOutSysex(frame)


# ----------------------------------------------------------------- FL callbacks
def OnInit():
    linked = _try(device.isAssigned, default=None)
    print("Maestro Bridge %s ready (SysEx). Reply output linked: %s" % (
        BRIDGE_VERSION, {True: "yes", False: "NO - set the 'Maestro Reply' output to this input's port number",
                         None: "unknown"}[linked if linked in (True, False) else None]))


def OnDeInit():
    _parts.clear()


def OnSysEx(event):
    done = receive(bytes(event.sysex))
    if done is None:
        return
    event.handled = True
    msg_id, packet = done
    _send_reply(msg_id, handle(packet))


def OnMidiMsg(event):
    event.handled = False
