"""Render pipeline tests with a stand-in synth (FluidSynth is not available in CI)."""

import numpy as np

from fl_maestro import render
from fl_maestro.project import Project, gm_program


def fake_synth(midi, wav):
    """Writes a 1 s-per-beat tone burst so the mix/master stages have real signal to process."""
    seconds = 12
    t = np.arange(seconds * render.SR) / render.SR
    tone = 0.3 * np.sin(2 * np.pi * 220 * t) * (np.sin(2 * np.pi * 2 * t) > 0)
    render.write_wav(wav, np.stack([tone, tone * 0.8]).astype(np.float32))


def make(loop):
    p = Project.new("Render Test", 120, "A", "natural_minor", chords=["Am", "F"], loop=loop,
                    sections=[{"name": "A", "start_bar": 1, "bars": 4}], genre="synthwave")
    p.upsert_agent("drums", "Drums", "drums", "FPC electronic kit", 0, 1, 35, 60)
    p.upsert_agent("bass", "Bass", "bass", "3xOsc saw", 1, 2, "A1", "A3", volume_db=-3)
    p.upsert_pattern("k", "drums", "Kick", 4, [{"pitch": 36, "start": b, "length": 0.25, "velocity": 110 - b} for b in range(4)])
    p.upsert_pattern("b", "bass", "Bass", 4, [{"pitch": "A2", "start": b, "length": 0.5, "velocity": 100 - b} for b in range(4)])
    p.set_arrangement([{"pattern": "k", "start_bar": 1, "repeat": 4}, {"pattern": "b", "start_bar": 1, "repeat": 4}])
    return p


def test_render_master_loudness_peak_and_files(isolated_dirs):
    out = render.render(make(loop=True), fmt="wav", stems=True, synth=fake_synth)
    assert out["duration_s"] == 8.0  # 4 bars at 120 BPM, loop: no tail
    assert out["peak_db"] <= -0.99
    assert abs(out["loudness_lufs"] + 14) < 1.5
    assert out["sidechain"] is True and len(out["stems"]) == 2
    audio = render.read_wav(__import__("pathlib").Path(out["wav"]))
    assert audio.shape == (2, 8 * render.SR)


def test_non_loop_gets_a_faded_tail(isolated_dirs):
    out = render.render(make(loop=False), fmt="wav", synth=fake_synth)
    assert out["duration_s"] == 11.5
    audio = render.read_wav(__import__("pathlib").Path(out["wav"]))
    assert np.abs(audio[:, -100:]).max() < 1e-3


def test_limiter_and_sidechain_shapes():
    x = np.ones((2, render.SR), np.float32) * 2.0
    y = render.limiter(x, ceiling_db=-1)
    assert np.abs(y).max() <= 10 ** (-1 / 20) + 1e-6
    env = render.sidechain_env([0.0, 0.5], render.SR, depth=0.5, release_s=0.4)
    assert env[int(0.01 * render.SR)] < 0.6 and env[int(0.45 * render.SR)] > 0.9


def test_gm_program_is_role_aware():
    agent = {"role": "bass", "instrument": "3xOsc detuned saw", "name": "Bass"}
    assert gm_program(agent) == 38
    assert gm_program({"role": "pad", "instrument": "Sytrus analog brass pad", "name": "Pad"}) == 89
    assert gm_program({"role": "strings", "instrument": "FLEX cello", "name": "Cello"}) == 42
    assert gm_program({"role": "drums", "instrument": "FPC TR-808", "name": "Drums"}) == 25
    assert gm_program({"role": "lead", "instrument": "x", "name": "y", "gm_program": 73}) == 73
