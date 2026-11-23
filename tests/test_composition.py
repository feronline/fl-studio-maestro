import struct

import pytest

from fl_maestro import critic, export, theory
from fl_maestro.project import Project


def test_pitch_parsing_and_names():
    assert theory.parse_pitch("C4") == 60
    assert theory.parse_pitch("F#2") == 42
    assert theory.parse_pitch("Bb3") == 58
    assert theory.parse_pitch(36) == 36
    assert theory.note_name(60) == "C4"
    assert theory.fl_note_name(60) == "C5"
    with pytest.raises(ValueError):
        theory.parse_pitch("H2")
    with pytest.raises(ValueError):
        theory.parse_pitch(200)


def test_scales_and_chords():
    assert theory.scale_pitch_classes("D", "harmonic_minor") == {2, 4, 5, 7, 9, 10, 1}
    root, pcs, bass = theory.parse_chord("Bb")
    assert (root, pcs, bass) == (10, {10, 2, 5}, 10)
    assert theory.parse_chord("C/E")[2] == 4
    assert theory.parse_chord("Am7")[1] == {9, 0, 4, 7}
    with pytest.raises(ValueError):
        theory.parse_chord("Cwhat")


def make_project(**kw):
    proj = Project.new("Neon Boss", 140, "D", "natural_minor", "4/4",
                       chords=["Dm", "Bb", "F", "C"], sections=[
                           {"name": "Intro", "start_bar": 1, "bars": 4},
                           {"name": "Verse", "start_bar": 5, "bars": 4},
                           {"name": "Chorus", "start_bar": 9, "bars": 4}], **kw)
    proj.upsert_agent("drums", "Drums", "drums", "FPC", 0, 1, 35, 60)
    proj.upsert_agent("bass", "808 Bass", "bass", "3xOsc", 1, 2, "C1", "C3")
    proj.upsert_agent("lead", "Lead", "lead", "Sytrus", 2, 3, "C4", "C6")
    proj.upsert_agent("arp", "Arp", "arp", "FLEX", 3, 4, "C4", "C6")
    return proj


def test_channel_isolation():
    proj = make_project()
    with pytest.raises(ValueError, match="channel 1 already belongs"):
        proj.upsert_agent("bass2", "Bass 2", "bass", "3xOsc", 1, 9, "C1", "C2")
    with pytest.raises(ValueError, match="mixer track 2"):
        proj.upsert_agent("bass2", "Bass 2", "bass", "3xOsc", 9, 2, "C1", "C2")
    proj.upsert_pattern("bass-a", "bass", "Bass A", 4, [{"pitch": "D2", "start": 0, "length": 1}])
    with pytest.raises(ValueError, match="belongs to agent"):
        proj.upsert_pattern("bass-a", "lead", "x", 4, [{"pitch": "D4", "start": 0, "length": 1}])


def test_fl_pattern_numbers_are_stable():
    proj = make_project()
    a = proj.upsert_pattern("a", "lead", "A", 4, [{"pitch": "D4", "start": 0, "length": 1}])
    b = proj.upsert_pattern("b", "lead", "B", 4, [{"pitch": "F4", "start": 0, "length": 1}])
    a2 = proj.upsert_pattern("a", "lead", "A", 4, [{"pitch": "E4", "start": 0, "length": 1}])
    assert (a["fl_pattern"], b["fl_pattern"], a2["fl_pattern"]) == (1, 2, 1)


def test_humanize_is_deterministic_and_accents_flat_velocities():
    proj = make_project()
    notes = [{"pitch": "D4", "start": i * 0.5, "length": 0.5, "velocity": 100} for i in range(8)]
    p1 = proj.upsert_pattern("h", "lead", "H", 4, notes, humanize=0.5)
    p2 = proj.upsert_pattern("h", "lead", "H", 4, notes, humanize=0.5)
    assert p1["notes"] == p2["notes"]
    vels = [n["velocity"] for n in p1["notes"]]
    assert len(set(vels)) > 2
    assert vels[0] > vels[1]  # downbeat louder than the offbeat
    assert p1["notes"][0]["start"] == 0


def test_save_and_load_roundtrip():
    proj = make_project()
    proj.save()
    again = Project.load()
    assert again.data == proj.data
    assert Project.list_all() == ["neon-boss"]


def checks(result):
    return {i["check"] for i in result["issues"]}


def test_critic_flags_problems():
    proj = make_project()
    proj.upsert_pattern("lead-a", "lead", "Lead", 4, [
        {"pitch": "D#4", "start": 0, "length": 1, "velocity": 100},   # out of scale
        {"pitch": "F4", "start": 1, "length": 1, "velocity": 100},
        {"pitch": "G4", "start": 2, "length": 1, "velocity": 100},
        {"pitch": "A2", "start": 3, "length": 1, "velocity": 100},    # out of band, flat velocity
    ])
    proj.upsert_pattern("arp-a", "arp", "Arp", 4, [
        {"pitch": p, "start": i, "length": 1, "velocity": 90 + i} for i, p in enumerate(["D4", "F4", "G4", "F4"])])
    proj.upsert_pattern("kick", "drums", "Kick", 4, [{"pitch": 36, "start": b, "length": 0.25, "velocity": 110} for b in range(4)])
    proj.upsert_pattern("bass-a", "bass", "Bass", 4, [
        {"pitch": "E2", "start": 0, "length": 1, "velocity": 100},     # not in Dm at the chord change
        {"pitch": "D2", "start": 1.06, "length": 1, "velocity": 90},  # flams with the kick
    ])
    proj.set_arrangement([{"pattern": p, "start_bar": 1, "repeat": 8} for p in ("lead-a", "arp-a", "kick", "bass-a")])
    result = critic.review(proj)
    found = checks(result)
    assert {"out_of_scale", "out_of_range", "mechanical_velocity", "chord_clash",
            "kick_bass_flam", "register_masking", "monotony", "silent_bars"} <= found
    assert not result["passed"]


def test_critic_passes_clean_material():
    proj = make_project()
    proj.upsert_pattern("bass-a", "bass", "Bass", 16, [
        {"pitch": p, "start": i * 4, "length": 3.5, "velocity": 100 - i}
        for i, p in enumerate(["D2", "A#1", "F2", "C2"])])
    proj.set_arrangement([{"pattern": "bass-a", "start_bar": 1, "repeat": 3}])
    result = critic.review(proj)
    assert result["counts"]["warning"] == 0, result["issues"]


def test_loop_seam():
    proj = make_project(loop=True)
    proj.upsert_pattern("a", "lead", "A", 6, [{"pitch": "D4", "start": 0, "length": 1, "velocity": 90}])
    proj.set_arrangement([{"pattern": "a", "start_bar": 1, "repeat": 1}])
    assert "loop_seam" in checks(critic.review(proj))


def _read_midi(data):
    assert data[:4] == b"MThd"
    fmt, ntrks, ppq = struct.unpack(">HHH", data[8:14])
    pos, tracks = 14, []
    for _ in range(ntrks):
        assert data[pos:pos + 4] == b"MTrk"
        size = struct.unpack(">I", data[pos + 4:pos + 8])[0]
        tracks.append(data[pos + 8:pos + 8 + size])
        pos += 8 + size
    return fmt, ppq, tracks


def test_midi_export(isolated_dirs):
    proj = make_project()
    proj.upsert_pattern("bass-a", "bass", "Bass", 4, [{"pitch": "D2", "start": 0, "length": 1, "velocity": 100}])
    proj.upsert_pattern("kick", "drums", "Kick", 4, [{"pitch": 36, "start": 0, "length": 0.25, "velocity": 110}])
    proj.set_arrangement([{"pattern": "bass-a", "start_bar": 1, "repeat": 2}, {"pattern": "kick", "start_bar": 1}])
    info = export.export_midi(proj)
    fmt, ppq, tracks = _read_midi(open(info["file"], "rb").read())
    assert (fmt, ppq, len(tracks)) == (1, 480, 5)  # conductor + every agent, even silent ones
    assert b"\xff\x51\x03" in tracks[0] and b"Verse" in tracks[0]
    assert tracks[2].count(bytes([0x90, 38])) == 2  # bass: two note-ons on channel 1
    assert bytes([0x99, 36, 110]) in tracks[1]      # drums on MIDI channel 10
    assert info["tracks"][0] == {"agent": "drums", "fl_channel": 0, "midi_channel": 10, "notes": 1}


def test_pianoroll_script_is_valid_python(isolated_dirs):
    proj = make_project()
    proj.upsert_pattern("lead-a", "lead", 'Lead "Hook"', 4, [{"pitch": "D4", "start": 0.5, "length": 0.25, "velocity": 64}])
    info = export.export_pianoroll_scripts(proj)
    path = isolated_dirs / "FL Studio" / "Settings" / "Piano roll scripts" / info["scripts"][0]["script"]
    source = path.read_text(encoding="utf-8")
    compile(source, str(path), "exec")
    assert "(62, 0.5, 0.25, 0.5039)" in source
