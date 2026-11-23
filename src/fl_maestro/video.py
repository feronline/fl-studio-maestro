"""Scoring a video: lay music (and sound effects) under it without burying the voice, then mux an MP4.

Ducking: wherever speech is detected the music drops by `duck_db` and gets a 1-4 kHz dip, so
words stay clear. The final mix is loudness-normalized for social platforms and limited at -1 dB.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import numpy as np

from . import analysis
from .render import SR, k_weighted_loudness, limiter, write_wav, ffmpeg_exe


def _fit(x: np.ndarray, n: int, loop: bool, fade_s: float = 1.5) -> np.ndarray:
    if x.shape[1] >= n:
        y = x[:, :n].copy()
        f = min(int(fade_s * SR), n)
        if f > 0:
            y[:, -f:] *= np.linspace(1, 0, f) ** 1.5
        return y
    if loop:
        reps = -(-n // x.shape[1])
        return _fit(np.tile(x, (1, reps)), n, False, fade_s)
    return np.pad(x, ((0, 0), (0, n - x.shape[1])))


def _envelope(segments: list[tuple[float, float]], n: int, depth_db: float,
              attack_s: float = 0.12, release_s: float = 0.35) -> np.ndarray:
    """1.0 where there is no speech, 10^(depth/20) under speech, with smooth ramps."""
    target = np.ones(n, np.float32)
    low = 10 ** (depth_db / 20)
    for a, b in segments:
        i0, i1 = max(0, int((a - attack_s) * SR)), min(n, int((b + 0.05) * SR))
        target[i0:i1] = low
    # one-pole smoothing at block rate (fast, and ramps both ways)
    block = 256
    nb = -(-n // block)
    t = np.pad(target, (0, nb * block - n), constant_values=1).reshape(nb, block).min(axis=1)
    ka, kr = np.exp(-block / (attack_s * SR)), np.exp(-block / (release_s * SR))
    g, out = 1.0, np.empty(nb)
    for i in range(nb):
        k = ka if t[i] < g else kr
        g = t[i] + (g - t[i]) * k
        out[i] = g
    return np.interp(np.arange(n), np.arange(nb) * block + block / 2, out).astype(np.float32)


def score_video(video: str | Path, music: str | Path | None, out_path: Path,
                sfx: list[dict[str, Any]] | None = None, music_db: float = -3.0, duck_db: float = -12.0,
                keep_original_audio: bool = True, loop_music: bool = False,
                target_lufs: float = -14.0) -> dict[str, Any]:
    video = Path(video)
    info = analysis._probe(video)
    n = int(info["duration_s"] * SR)
    mix = np.zeros((2, n), np.float32)
    report: dict[str, Any] = {"video": str(video), "duration_s": round(info["duration_s"], 2)}

    speech: list[tuple[float, float]] = []
    if info["has_audio"] and keep_original_audio:
        orig = analysis.load_audio(video, SR, mono=False).astype(np.float32)
        orig = _fit(orig, n, False, 0.0)
        speech = analysis.speech_segments(analysis.load_audio(video))
        mix += orig
        report["original_audio"] = "kept"
    report["speech_segments_s"] = [list(s) for s in speech]

    if music:
        m = analysis.load_audio(music, SR, mono=False).astype(np.float32)
        m = _fit(m, n, loop_music) * 10 ** (music_db / 20)
        if speech:
            env = _envelope(speech, n, duck_db)
            # vocal pocket: -4 dB around 1-4 kHz on the ducked copy
            dipped = _vocal_pocket(m)
            blend = (1 - env) / (1 - 10 ** (duck_db / 20))  # 0 = no speech, 1 = full duck
            m = (m * (1 - blend) + dipped * blend) * env
            report["ducking"] = f"{duck_db} dB under {len(speech)} speech segment(s), with a 1-4 kHz pocket"
        mix += m
        report["music"] = str(music)

    placed = []
    for item in sfx or []:
        s = analysis.load_audio(item["file"], SR, mono=False).astype(np.float32)
        at = int(float(item["time_s"]) * SR)
        if at >= n:
            continue
        gain = 10 ** (float(item.get("gain_db", -6)) / 20)
        end = min(n, at + s.shape[1])
        mix[:, at:end] += s[:, :end - at] * gain
        placed.append({"file": item["file"], "time_s": item["time_s"]})
    report["sfx_placed"] = placed

    lufs = k_weighted_loudness(mix)
    if lufs > -60:
        mix *= 10 ** ((target_lufs - lufs) / 20)
    mix = limiter(mix, -1.0)
    report["loudness_lufs"] = round(k_weighted_loudness(mix), 1)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wav = out_path.with_suffix(".mix.wav")
    write_wav(wav, mix)
    ff = ffmpeg_exe()
    if not ff:
        raise analysis.AnalysisError("ffmpeg is needed to write the video (pip install imageio-ffmpeg)")
    res = subprocess.run([ff, "-y", "-v", "error", "-i", str(video), "-i", str(wav), "-map", "0:v:0", "-map", "1:a:0",
                          "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart",
                          str(out_path)], capture_output=True, text=True, timeout=900)
    if res.returncode != 0:
        raise analysis.AnalysisError(f"muxing failed: {res.stderr.strip()[:400]}")
    audio_only = out_path.with_name(out_path.stem + "-audio.mp3")
    subprocess.run([ff, "-y", "-v", "error", "-i", str(wav), "-c:a", "libmp3lame", "-b:a", "256k", str(audio_only)],
                   capture_output=True, timeout=300)
    wav.unlink(missing_ok=True)
    report["output_video"] = str(out_path)
    report["output_audio"] = str(audio_only) if audio_only.exists() else None
    return report


def _vocal_pocket(x: np.ndarray) -> np.ndarray:
    from .render import _fft_filter

    def g(f):
        octaves = np.log2(np.maximum(f, 1) / 2000)
        return 10 ** (-5 * np.exp(-(octaves / 1.0) ** 2) / 20)
    return _fft_filter(x, g)
