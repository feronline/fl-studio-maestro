import asyncio
import json

import pytest

from fl_maestro.bridge import Bridge, BridgeError


def test_ping(fake_fl):
    info = Bridge(port=fake_fl.port).call("ping")
    assert info["tempo"] == 140 and info["channels"] == 4 and info["bridge"]


def test_tempo_transport_save(fake_fl):
    b = Bridge(port=fake_fl.port)
    assert b.call("set_tempo", bpm=128.5)["tempo"] == 128.5
    assert b.call("transport", action="play")["playing"] is True
    b.call("save")
    assert fake_fl.saved


def test_channel_and_mixer(fake_fl):
    b = Bridge(port=fake_fl.port)
    row = b.call("channel", index=1, name="808 Bass", color="#ff0000", pan=0.0, mixer_track=2, volume_db=-3)
    assert row["name"] == "808 Bass" and row["mixer_track"] == 2 and row["color"] == "#ff0000"
    assert abs(row["volume_db"] + 3) < 0.01
    row = b.call("mixer_track", index=2, name="808 Bass", pan=-0.3, volume_db=-6, route_to=[5])
    assert row["name"] == "808 Bass" and abs(row["volume_db"] + 6) < 0.01
    assert fake_fl.mixer[2]["routes"] == {5}


def test_stage_pattern_and_plugins(fake_fl):
    b = Bridge(port=fake_fl.port)
    out = b.call("stage_pattern", pattern=3, channel=0, pattern_name="Drums A")
    assert out["pattern"] == 3 and fake_fl.selected_channel == 0 and fake_fl.window == 3
    params = b.call("plugin_params", location="channel", index=0, search="cut")
    assert params["params"] == [{"param": 0, "name": "Cutoff", "value": 0.5, "display": "50%"}]
    assert b.call("set_plugin_param", location="channel", index=0, param=1, value=0.75)["display"] == "75%"


def test_errors_come_back_readable(fake_fl):
    b = Bridge(port=fake_fl.port)
    with pytest.raises(BridgeError, match="channel 99 does not exist"):
        b.call("channel", index=99, name="x")
    with pytest.raises(BridgeError, match="unknown command"):
        b.call("explode")


def test_no_fl_gives_setup_hint():
    with pytest.raises(BridgeError, match="Maestro Bridge"):
        Bridge(port=1, timeout=0.3).call("ping")


def _call(tool, **args):
    from fl_maestro.server import mcp
    result = asyncio.run(mcp.call_tool(tool, args))
    assert not result.is_error, result.content
    return result


def _payload(result):
    if result.structured_content:
        return result.structured_content.get("result", result.structured_content)
    return json.loads(result.content[0].text)


def test_end_to_end_through_mcp(fake_fl, isolated_dirs):
    _call("create_project", name="Test Song", bpm=96, key="A", scale="natural_minor",
          chords=["Am", "F", "C", "G"], sections=[{"name": "Intro", "start_bar": 1, "bars": 2}])
    _call("register_agent", agent_id="keys", name="FL Keys", role="chords", instrument="FL Keys",
          channel=2, mixer_track=3, low_note="C3", high_note="C5", pan=0.2, volume_db=-4)
    pat = _payload(_call("write_pattern", pattern_id="keys-a", agent_id="keys", name="Keys A", length_beats=8,
                         notes=[{"pitch": "A3", "start": 0, "length": 4, "velocity": 90},
                                {"pitch": "F3", "start": 4, "length": 4, "velocity": 80}]))
    assert pat["fl_pattern"] == 1
    _call("arrange", placements=[{"pattern": "keys-a", "start_bar": 1}])
    review = _payload(_call("review_project"))
    assert review["counts"]["error"] == 0
    exported = _payload(_call("export_project", format="both"))
    assert exported["midi"]["tracks"][0]["notes"] == 2
    applied = _payload(_call("fl_apply_session"))
    assert not applied["problems"]
    assert fake_fl.tempo == 96 and fake_fl.channels[2]["name"] == "FL Keys" and fake_fl.channels[2]["fx"] == 3
    assert fake_fl.mixer[3]["name"] == "FL Keys" and fake_fl.patterns[1] == "Keys A"
    staged = _payload(_call("fl_stage_pattern", pattern_id="keys-a"))
    assert staged["script"].startswith("Maestro - test-song - P01")
