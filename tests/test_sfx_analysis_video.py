import subprocess
from pathlib import Path

import numpy as np
import pytest

from fl_maestro import analysis, paths, render, sfx, video


@pytest.mark.parametrize("kind", sfx.KINDS)
def test_every_sfx_kind_renders_unique_takes(kind, tmp_path):
    out = sfx.make(kind, kind, tmp_path, variations=2, seed=11, engine="synth")
    a = render.read_wav(Path(out["files"][0]["wav"]))
    b = render.read_wav(Path(out["files"][1]["wav"]))
    assert 0.02 < out["files"][0]["seconds"] < 6
    assert abs(20 * np.log10(np.abs(a).max()) + 1) < 0.2  # normalized to -1 dBFS
    n = min(a.shape[1], b.shape[1])
    assert np.abs(a[:, :n] - b[:, :n]).mean() > 1e-3  # variations differ


def test_sfx_seed_is_reproducible_and_materials_differ(tmp_path):
    one = sfx.make("footstep", "a", tmp_path / "1", variations=1, seed=5, material="gravel", engine="synth")
    two = sfx.make("footstep", "a", tmp_path / "2", variations=1, seed=5, material="gravel", engine="synth")
    wood = sfx.make("footstep", "a", tmp_path / "3", variations=1, seed=5, material="wood", engine="synth")
    read = lambda r: render.read_wav(Path(r["files"][0]["wav"]))
    assert np.array_equal(read(one), read(two))
    x, y = read(one), read(wood)
    n = min(x.shape[1], y.shape[1])
    assert np.abs(x[:, :n] - y[:, :n]).mean() > 1e-3


def test_sfx_rejects_bad_options(tmp_path):
    with pytest.raises(ValueError, match="unknown kind"):
        sfx.make("kazoo", "x", tmp_path)
    with pytest.raises(ValueError, match="material"):
        sfx.make("footstep", "x", tmp_path, material="lava")


def _click_track(bpm, seconds=12, sr=analysis.AR):
    x = np.zeros(int(seconds * sr))
    beat = 60 / bpm
    t = np.arange(int(0.03 * sr)) / sr
    click = np.sin(2 * np.pi * 1000 * t) * np.exp(-t / 0.005)
    for k in range(int(seconds / beat)):
        i = int(k * beat * sr)
        x[i:i + click.size] += click
    return x


def test_tempo_estimate():
    for bpm in (92, 120, 140):
        est, _ = analysis.estimate_tempo(_click_track(bpm))
        assert abs(est - bpm) <= 1.5 or abs(est - 2 * bpm) <= 2 or abs(est - bpm / 2) <= 1


def test_key_estimate_a_minor():
    sr = analysis.AR
    t = np.arange(sr * 6) / sr
    x = sum(np.sin(2 * np.pi * f * t) * w for f, w in ((220, 1.0), (261.63, 0.7), (329.63, 0.8), (110, 0.6), (196, 0.3)))
    tonic, mode, _ = analysis.estimate_key(x)
    assert (tonic, mode) in (("A", "minor"), ("C", "major"))


def test_tempo_suggestions_put_cuts_on_bars():
    top = analysis.tempo_suggestions([4.0, 8.0], 12.0)[0]
    assert top["cuts_on_bar_lines"] == 2 and (60 / top["bpm"] * 4) in (1.0, 2.0, 4.0) or top["cuts_on_bar_lines"] == 2


def test_ducking_envelope():
    env = video._envelope([(1.0, 2.0)], render.SR * 3, -12)
    assert env[int(0.2 * render.SR)] > 0.98
    assert env[int(1.5 * render.SR)] < 0.3
    assert env[int(2.9 * render.SR)] > 0.8


def test_output_dir_resolution(tmp_path, monkeypatch):
    monkeypatch.delenv("FL_MAESTRO_OUTPUT_DIR", raising=False)
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    assert paths.output_dir(str(tmp_path / "x")) == tmp_path / "x"
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path / "proj"))
    assert paths.output_dir() == tmp_path / "proj"
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CLAUDE_PROJECT_DIR")
    assert paths.output_dir() == Path.cwd()


@pytest.mark.skipif(render.ffmpeg_exe() is None, reason="ffmpeg not available")
def test_score_video_end_to_end(tmp_path):
    ff = render.ffmpeg_exe()
    vid = tmp_path / "clip.mp4"
    subprocess.run([ff, "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x240:r=25:d=2",
                    "-f", "lavfi", "-i", "color=c=red:s=320x240:r=25:d=2",
                    "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0,format=yuv420p[v]", "-map", "[v]",
                    "-c:v", "libx264", "-t", "4", str(vid)], check=True, timeout=120)
    t = np.arange(render.SR * 4) / render.SR
    music = (0.2 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    mwav = tmp_path / "music.wav"
    render.write_wav(mwav, np.stack([music, music]))
    hit = sfx.make("whoosh", "w", tmp_path, variations=1, seed=1, engine="synth")
    rep = video.score_video(vid, mwav, tmp_path / "clip_scored.mp4", [{"file": hit["files"][0]["wav"], "time_s": 1.8}])
    assert Path(rep["output_video"]).exists() and rep["sfx_placed"]
    info = analysis._probe(Path(rep["output_video"]))
    assert info["has_audio"] and abs(info["duration_s"] - 4) < 0.2
