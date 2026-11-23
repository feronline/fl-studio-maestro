"""Listening and watching: analyze a reference audio file or a video before composing for it.

Audio: tempo (onset autocorrelation), key (Krumhansl-Schmuckler on a chromagram), loudness,
brightness and an energy curve. Video: duration, scene cuts, speech segments, keyframes for
Claude to look at, and tempos whose bar lines land on the cuts.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

from . import theory

AR = 22050  # analysis sample rate

_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


class AnalysisError(RuntimeError):
    pass


def _ffmpeg() -> str:
    from .render import ffmpeg_exe
    ff = ffmpeg_exe()
    if not ff:
        raise AnalysisError("ffmpeg is needed to read audio/video (pip install imageio-ffmpeg)")
    return ff


def load_audio(path: str | Path, sr: int = AR, mono: bool = True) -> np.ndarray:
    """Decode any audio/video file to float32 with ffmpeg."""
    path = Path(path)
    if not path.exists():
        raise AnalysisError(f"file not found: {path}")
    cmd = [_ffmpeg(), "-v", "error", "-i", str(path), "-vn", "-f", "f32le", "-acodec", "pcm_f32le",
           "-ac", "1" if mono else "2", "-ar", str(sr), "-"]
    res = subprocess.run(cmd, capture_output=True, timeout=600)
    if res.returncode != 0:
        raise AnalysisError(f"could not decode {path.name}: {res.stderr.decode(errors='ignore')[:300]}")
    data = np.frombuffer(res.stdout, dtype="<f4")
    return data if mono else data.reshape(-1, 2).T


def _stft_mag(x: np.ndarray, n_fft: int = 2048, hop: int = 512) -> np.ndarray:
    if x.size < n_fft:
        x = np.pad(x, (0, n_fft - x.size))
    frames = 1 + (x.size - n_fft) // hop
    idx = np.arange(n_fft)[None, :] + hop * np.arange(frames)[:, None]
    win = np.hanning(n_fft)
    return np.abs(np.fft.rfft(x[idx] * win, axis=1))


def estimate_tempo(x: np.ndarray, sr: int = AR) -> tuple[float, float]:
    """Returns (bpm, confidence 0-1)."""
    hop = 512
    mag = _stft_mag(x, 2048, hop)
    flux = np.maximum(np.diff(np.log1p(mag), axis=0), 0).sum(axis=1)
    if flux.size < 16:
        return 0.0, 0.0
    flux -= flux.mean()
    ac = np.correlate(flux, flux, "full")[flux.size - 1:]
    fps = sr / hop
    bpms = np.arange(60, 200.5, 0.5)
    lags = fps * 60 / bpms
    vals = np.interp(lags, np.arange(ac.size), ac)
    # perceptual prior around 115 BPM, and support from the double lag
    prior = np.exp(-0.5 * (np.log2(bpms / 115) / 0.9) ** 2)
    support = np.interp(lags * 2, np.arange(ac.size), ac)
    score = (vals + 0.5 * support) * prior
    best = bpms[int(np.argmax(score))]
    conf = float(np.clip(score.max() / (np.abs(score).mean() * 4 + 1e-9), 0, 1))
    return float(best), conf


def estimate_key(x: np.ndarray, sr: int = AR) -> tuple[str, str, float]:
    """Returns (tonic, 'major'|'minor', confidence)."""
    mag = _stft_mag(x, 4096, 2048)
    freqs = np.fft.rfftfreq(4096, 1 / sr)
    valid = (freqs > 55) & (freqs < 5000)
    pcs = (np.round(12 * np.log2(freqs[valid] / 440)) + 9) % 12
    chroma = np.zeros(12)
    energy = (mag[:, valid] ** 2).sum(axis=0)
    for pc in range(12):
        chroma[pc] = energy[pcs == pc].sum()
    if chroma.sum() == 0:
        return "C", "major", 0.0
    chroma /= chroma.max()
    best = (-2.0, 0, "major")
    scores = []
    for tonic in range(12):
        for mode, prof in (("major", _MAJOR), ("minor", _MINOR)):
            r = np.corrcoef(chroma, np.roll(prof, tonic))[0, 1]
            scores.append(r)
            if r > best[0]:
                best = (r, tonic, mode)
    scores.sort(reverse=True)
    conf = float(np.clip((scores[0] - scores[1]) * 5, 0, 1))
    return theory.NOTE_NAMES[best[1]], best[2], conf


def analyze_audio(path: str | Path) -> dict[str, Any]:
    x = load_audio(path)
    if x.size < AR:
        raise AnalysisError("audio is shorter than one second")
    stereo = load_audio(path, 44100, mono=False)
    from .render import k_weighted_loudness
    bpm, tconf = estimate_tempo(x)
    tonic, mode, kconf = estimate_key(x)
    bpm = round(bpm)
    mag = _stft_mag(x)
    freqs = np.fft.rfftfreq(2048, 1 / AR)
    centroid = float((mag * freqs).sum() / (mag.sum() + 1e-9))
    seconds = x.size / AR
    seg = np.array_split(x, 10)
    energy = [round(float(20 * np.log10(np.sqrt(np.mean(s ** 2)) + 1e-9)), 1) for s in seg]
    low = float((mag[:, freqs < 150] ** 2).sum() / ((mag ** 2).sum() + 1e-9))
    return {
        "file": str(path), "duration_s": round(seconds, 2),
        "tempo_bpm": bpm, "tempo_confidence": round(tconf, 2),
        "half_or_double_time": [round(bpm / 2, 1), round(bpm * 2, 1)],
        "key": f"{tonic} {mode}", "key_confidence": round(kconf, 2),
        "relative_key": _relative(tonic, mode),
        "key_note": "major keys and their relative minors share the same notes; pick by the mood (dark = minor)",
        "suggested_scale": "major" if mode == "major" else "natural_minor",
        "loudness_lufs": round(k_weighted_loudness(stereo.astype(np.float32)), 1),
        "brightness_hz": round(centroid), "brightness": "dark" if centroid < 1500 else "bright" if centroid > 3000 else "balanced",
        "bass_weight": round(low, 2),
        "energy_curve_db": energy,
        "note": "Use these as a style brief (tempo, key, energy shape, brightness); do not copy the melody.",
    }


def _relative(tonic: str, mode: str) -> str:
    pc = theory.pitch_class(tonic)
    return (f"{theory.NOTE_NAMES[(pc + 9) % 12]} minor" if mode == "major"
            else f"{theory.NOTE_NAMES[(pc + 3) % 12]} major")


def _probe(path: Path) -> dict[str, Any]:
    from shutil import which
    ffprobe = which("ffprobe")
    if ffprobe:
        res = subprocess.run([ffprobe, "-v", "error", "-show_entries",
                              "format=duration:stream=codec_type,width,height,avg_frame_rate", "-of", "json", str(path)],
                             capture_output=True, text=True, timeout=60)
        if res.returncode == 0:
            data = json.loads(res.stdout)
            video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
            has_audio = any(s.get("codec_type") == "audio" for s in data.get("streams", []))
            num, _, den = (video.get("avg_frame_rate") or "0/1").partition("/")
            fps = float(num) / float(den or 1) if float(den or 1) else 0
            return {"duration_s": float(data["format"]["duration"]), "width": video.get("width"),
                    "height": video.get("height"), "fps": round(fps, 2), "has_audio": has_audio}
    # fallback: parse ffmpeg's banner
    res = subprocess.run([_ffmpeg(), "-i", str(path)], capture_output=True, text=True, timeout=60)
    text = res.stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", text)
    if not m:
        raise AnalysisError(f"could not read {path.name}")
    dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    size = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", text)
    fps = re.search(r"([\d.]+) fps", text)
    return {"duration_s": dur, "width": int(size.group(1)) if size else None, "height": int(size.group(2)) if size else None,
            "fps": float(fps.group(1)) if fps else None, "has_audio": "Audio:" in text}


def scene_cuts(path: Path, threshold: float = 0.32) -> list[float]:
    res = subprocess.run([_ffmpeg(), "-hide_banner", "-i", str(path), "-an", "-filter:v",
                          f"select='gt(scene,{threshold})',showinfo", "-f", "null", "-"],
                         capture_output=True, text=True, timeout=900)
    times = [float(t) for t in re.findall(r"pts_time:([\d.]+)", res.stderr)]
    out: list[float] = []
    for t in times:
        if not out or t - out[-1] > 0.4:
            out.append(round(t, 2))
    return out


def speech_segments(x: np.ndarray, sr: int = AR) -> list[tuple[float, float]]:
    """Voice-activity detection: energy in the 300-3400 Hz band, low spectral flatness, hangover."""
    hop, n_fft = 441, 1024  # 20 ms frames at 22.05 kHz
    mag = _stft_mag(x, n_fft, hop)
    freqs = np.fft.rfftfreq(n_fft, 1 / sr)
    band = (freqs > 300) & (freqs < 3400)
    e_band = (mag[:, band] ** 2).sum(axis=1)
    e_all = (mag ** 2).sum(axis=1) + 1e-12
    ratio = e_band / e_all
    db = 10 * np.log10(e_band + 1e-12)
    floor = np.percentile(db, 15)
    geo = np.exp(np.mean(np.log(mag[:, band] + 1e-9), axis=1))
    flat = geo / (np.mean(mag[:, band], axis=1) + 1e-9)
    # syllabic modulation: speech energy fluctuates at 3-8 Hz
    active = (db > floor + 12) & (ratio > 0.45) & (flat < 0.45)
    hang = 12  # 240 ms
    smooth = np.convolve(active.astype(float), np.ones(hang), "same") > 0
    segs, start = [], None
    t = lambda i: i * hop / sr
    for i, a in enumerate(smooth):
        if a and start is None:
            start = i
        if not a and start is not None:
            if t(i) - t(start) >= 0.35:
                segs.append((round(t(start), 2), round(t(i), 2)))
            start = None
    if start is not None and t(len(smooth)) - t(start) >= 0.35:
        segs.append((round(t(start), 2), round(t(len(smooth)), 2)))
    merged: list[tuple[float, float]] = []
    for a, b in segs:  # join pauses between words so the music does not pump
        if merged and a - merged[-1][1] < 0.6:
            merged[-1] = (merged[-1][0], b)
        else:
            merged.append((a, b))
    return merged


def tempo_suggestions(cuts: list[float], duration: float, beats_per_bar: int = 4) -> list[dict[str, Any]]:
    """Tempos whose bar lines (or half bars) fall closest to the scene cuts."""
    if not cuts:
        return []
    out = []
    for bpm in np.arange(70, 176, 1.0):
        bar = 60 / bpm * beats_per_bar
        grid = bar / 2
        err = np.array([min(c % grid, grid - c % grid) for c in cuts])
        on_bar = sum(1 for c in cuts if min(c % bar, bar - c % bar) < 0.06)
        score = float(np.mean(err < 0.06)) + 0.5 * on_bar / len(cuts)
        out.append({"bpm": int(bpm), "cuts_on_grid": int(np.sum(err < 0.06)), "cuts_on_bar_lines": on_bar,
                    "bars": round(float(duration / bar), 2), "score": round(float(score), 3)})
    out.sort(key=lambda r: -r["score"])
    return out[:5]


def analyze_video(path: str | Path, frames_dir: Path, keyframes: int = 8) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        raise AnalysisError(f"file not found: {path}")
    info = _probe(path)
    dur = info["duration_s"]
    cuts = scene_cuts(path)
    frames_dir.mkdir(parents=True, exist_ok=True)
    stamps = sorted(set([round(dur * (i + 0.5) / keyframes, 2) for i in range(keyframes)] + cuts[:8]))
    frames = []
    for i, ts in enumerate(stamps[:16]):
        img = frames_dir / f"frame_{i:02d}_{ts:06.2f}s.jpg"
        subprocess.run([_ffmpeg(), "-v", "error", "-y", "-ss", str(ts), "-i", str(path), "-frames:v", "1",
                        "-vf", "scale=480:-2", "-q:v", "4", str(img)], timeout=60)
        if img.exists():
            frames.append({"time_s": ts, "image": str(img)})
    speech, audio_lufs = [], None
    if info["has_audio"]:
        x = load_audio(path)
        speech = speech_segments(x)
        from .render import k_weighted_loudness
        st = load_audio(path, 44100, mono=False).astype(np.float32)
        audio_lufs = round(k_weighted_loudness(st), 1) if st.shape[1] > 44100 else None
    speech_total = round(sum(b - a for a, b in speech), 2)
    return {
        "file": str(path), **info, "scene_cuts_s": cuts,
        "speech_segments_s": [list(s) for s in speech], "speech_seconds": speech_total,
        "has_speech": speech_total > 1.0, "original_audio_lufs": audio_lufs,
        "keyframes": frames,
        "tempo_suggestions": tempo_suggestions(cuts, dur),
        "next": "Look at the keyframes (Read the images) to judge mood and pacing, pick a tempo from "
                "tempo_suggestions so section changes land on cuts, compose music of duration_s, "
                "render_audio, then score_video.",
    }
