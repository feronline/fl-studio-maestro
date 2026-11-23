"""Audio rendering: every agent becomes a stem through FluidSynth + a General MIDI SoundFont,
then a mix engineer and a mastering engineer (pure numpy) turn the stems into a finished track.

Mix: frequency-domain high-pass and mud cut, kick sidechain, reverb send (convolution),
tempo-synced ping-pong delay, gain, pan and stereo width.
Master: loudness normalization (BS.1770-style K-weighting) and a look-ahead peak limiter.
Loops: reverb and delay tails wrap into bar 1 so the file loops seamlessly.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import urllib.request
import wave
import zipfile
from pathlib import Path
from typing import Any, Callable

import numpy as np

from . import export, paths
from .project import Project

SR = 44100

FLUIDSYNTH_WIN_URL = ("https://github.com/FluidSynth/fluidsynth/releases/download/v2.6.3/"
                      "fluidsynth-v2.6.3-win10-x64-cpp11.zip")
SOUNDFONT_URL = "https://github.com/mrbumpy409/GeneralUser-GS/raw/main/GeneralUser-GS.sf2"
SOUNDFONT_NAME = "GeneralUser-GS.sf2"

ELECTRONIC_WORDS = ("synth", "edm", "house", "techno", "trance", "dubstep", "trap", "drill", "pop", "phonk",
                    "wave", "dance", "electro", "dnb", "drum & bass", "drum and bass", "future", "cyber", "chiptune")

# Mix engineer defaults per role: high-pass Hz, mud cut dB at 300 Hz, reverb send, delay send, sidechain depth
ROLE_MIX: dict[str, dict[str, float]] = {
    "drums":          {"hp": 30,  "mud": 0,  "verb": 0.06, "delay": 0.0,  "duck": 0.0},
    "percussion":     {"hp": 60,  "mud": 0,  "verb": 0.12, "delay": 0.0,  "duck": 0.0},
    "bass":           {"hp": 30,  "mud": 0,  "verb": 0.0,  "delay": 0.0,  "duck": 0.55},
    "chords":         {"hp": 120, "mud": -2, "verb": 0.18, "delay": 0.0,  "duck": 0.3},
    "pad":            {"hp": 150, "mud": -3, "verb": 0.30, "delay": 0.0,  "duck": 0.35},
    "strings":        {"hp": 100, "mud": -2, "verb": 0.35, "delay": 0.0,  "duck": 0.0},
    "brass":          {"hp": 100, "mud": -2, "verb": 0.25, "delay": 0.0,  "duck": 0.0},
    "woodwinds":      {"hp": 150, "mud": -1, "verb": 0.25, "delay": 0.0,  "duck": 0.0},
    "lead":           {"hp": 150, "mud": -1, "verb": 0.22, "delay": 0.14, "duck": 0.0},
    "vocal":          {"hp": 120, "mud": -1, "verb": 0.25, "delay": 0.10, "duck": 0.0},
    "choir":          {"hp": 100, "mud": -2, "verb": 0.40, "delay": 0.0,  "duck": 0.0},
    "counter_melody": {"hp": 150, "mud": -1, "verb": 0.22, "delay": 0.08, "duck": 0.0},
    "arp":            {"hp": 200, "mud": -1, "verb": 0.18, "delay": 0.20, "duck": 0.2},
    "fx":             {"hp": 80,  "mud": 0,  "verb": 0.30, "delay": 0.0,  "duck": 0.0},
    "atmosphere":     {"hp": 120, "mud": -2, "verb": 0.45, "delay": 0.0,  "duck": 0.0},
    "other":          {"hp": 100, "mud": -1, "verb": 0.20, "delay": 0.0,  "duck": 0.0},
}


class RenderError(RuntimeError):
    pass


# ------------------------------------------------------------------------------ tools
def tools_dir() -> Path:
    d = paths.projects_root() / "tools"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _download(url: str, dest: Path) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "fl-studio-maestro"})
    with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f, 1 << 20)
    tmp.replace(dest)


def fluidsynth_exe() -> str:
    env = os.environ.get("FL_MAESTRO_FLUIDSYNTH")
    if env:
        return env
    found = shutil.which("fluidsynth")
    if found:
        return found
    if sys.platform == "win32":
        local = list(tools_dir().glob("fluidsynth/*/bin/fluidsynth.exe"))
        if local:
            return str(local[0])
        zpath = tools_dir() / "fluidsynth.zip"
        _download(FLUIDSYNTH_WIN_URL, zpath)
        with zipfile.ZipFile(zpath) as z:
            z.extractall(tools_dir() / "fluidsynth")
        zpath.unlink(missing_ok=True)
        local = list(tools_dir().glob("fluidsynth/*/bin/fluidsynth.exe"))
        if local:
            return str(local[0])
    hint = "brew install fluid-synth" if sys.platform == "darwin" else "sudo apt install fluidsynth"
    raise RenderError(f"FluidSynth is needed to render audio. Install it ({hint}) or set FL_MAESTRO_FLUIDSYNTH.")


def soundfont() -> str:
    env = os.environ.get("FL_MAESTRO_SOUNDFONT")
    if env:
        return env
    sf = tools_dir() / SOUNDFONT_NAME
    if not sf.exists() or sf.stat().st_size < 1_000_000:
        _download(SOUNDFONT_URL, sf)
    return str(sf)


def ffmpeg_exe() -> str | None:
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg  # type: ignore
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def fluidsynth_render(midi: Path, wav: Path) -> None:
    cmd = [fluidsynth_exe(), "-ni", "-q", "-R", "0", "-C", "0", "-g", "0.6", "-r", str(SR),
           "-T", "wav", "-O", "s16", "-F", str(wav), soundfont(), str(midi)]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if res.returncode != 0 or not wav.exists():
        raise RenderError(f"FluidSynth failed: {(res.stderr or res.stdout).strip()[:500]}")


# ------------------------------------------------------------------------------ audio io
def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        ch, width, n = w.getnchannels(), w.getsampwidth(), w.getnframes()
        raw = w.readframes(n)
    if width != 2:
        raise RenderError(f"unexpected sample width {width} in {path.name}")
    data = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    data = data.reshape(-1, ch)
    if ch == 1:
        data = np.repeat(data, 2, axis=1)
    return data[:, :2].T.copy()  # (2, n)


def write_wav(path: Path, audio: np.ndarray) -> None:
    pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2").T.copy()
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


# ------------------------------------------------------------------------------ dsp
def _fft_filter(x: np.ndarray, gain_fn: Callable[[np.ndarray], np.ndarray]) -> np.ndarray:
    n = x.shape[-1]
    size = 1 << (n - 1).bit_length()
    spec = np.fft.rfft(x, size, axis=-1)
    freqs = np.fft.rfftfreq(size, 1 / SR)
    spec *= gain_fn(freqs)
    return np.fft.irfft(spec, size, axis=-1)[..., :n].astype(np.float32)


def eq(x: np.ndarray, hp_hz: float = 0, mud_db: float = 0, air_db: float = 0) -> np.ndarray:
    if not hp_hz and not mud_db and not air_db:
        return x

    def g(f):
        out = np.ones_like(f)
        if hp_hz:
            with np.errstate(divide="ignore"):
                out *= 1 / np.sqrt(1 + (hp_hz / np.maximum(f, 1e-3)) ** 4)  # 2nd-order Butterworth
        if mud_db:
            octaves = np.log2(np.maximum(f, 1) / 300)
            out *= 10 ** (mud_db * np.exp(-(octaves / 0.6) ** 2) / 20)
        if air_db:
            out *= 10 ** (air_db / (1 + (10000 / np.maximum(f, 1)) ** 2) / 20)
        return out
    return _fft_filter(x, g)


def convolve(x: np.ndarray, ir: np.ndarray) -> np.ndarray:
    n = x.shape[-1] + ir.shape[-1] - 1
    size = 1 << (n - 1).bit_length()
    y = np.fft.irfft(np.fft.rfft(x, size, axis=-1) * np.fft.rfft(ir, size, axis=-1), size, axis=-1)
    return y[..., :n].astype(np.float32)


def reverb_ir(seconds: float = 2.4, predelay: float = 0.02, seed: int = 7) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(seconds * SR)
    t = np.arange(n) / SR
    env = np.exp(-6.9 * t / seconds)
    ir = rng.standard_normal((2, n)).astype(np.float32) * env
    ir = eq(ir, hp_hz=180)
    # darker tail: low-pass grows with time (simple two-band blend)
    dark = _fft_filter(ir, lambda f: 1 / np.sqrt(1 + (f / 4500) ** 4))
    blend = np.clip(t / seconds * 1.5, 0, 1)
    ir = ir * (1 - blend) + dark * blend
    ir = np.concatenate([np.zeros((2, int(predelay * SR)), np.float32), ir], axis=1)
    return ir / np.sqrt(np.sum(ir ** 2) / 2)


def pingpong_delay(x: np.ndarray, delay_s: float, feedback: float = 0.38, taps: int = 6) -> np.ndarray:
    d = int(delay_s * SR)
    n = x.shape[-1]
    out = np.zeros((2, n + d * taps), np.float32)
    mono = x.mean(axis=0)
    mono = eq(mono[None, :], hp_hz=300)[0]
    for k in range(1, taps + 1):
        side = (k - 1) % 2
        out[side, k * d:k * d + n] += mono * feedback ** (k - 1)
    return out


def pan_width(x: np.ndarray, pan: float, width: float) -> np.ndarray:
    mid, side = (x[0] + x[1]) / 2, (x[0] - x[1]) / 2
    side *= max(0.0, 1 + width)  # width -1 = mono, 0 = as is, 1 = twice as wide
    l, r = mid + side, mid - side
    angle = (pan + 1) * np.pi / 4  # constant-power pan
    return np.stack([l * np.cos(angle) * np.sqrt(2), r * np.sin(angle) * np.sqrt(2)]).astype(np.float32)


def sidechain_env(kick_times_s: list[float], n: int, depth: float, release_s: float) -> np.ndarray:
    if not kick_times_s or depth <= 0:
        return np.ones(n, np.float32)
    t = np.arange(n) / SR
    kicks = np.array(sorted(kick_times_s))
    idx = np.searchsorted(kicks, t, side="right") - 1
    since = np.where(idx >= 0, t - kicks[np.clip(idx, 0, None)], 1e9)
    attack = np.clip(since / 0.004, 0, 1)
    duck = depth * attack * np.exp(-since / (release_s / 3)) + depth * (1 - attack) * (idx >= 0) * 0
    return (1 - duck).astype(np.float32)


def k_weighted_loudness(x: np.ndarray) -> float:
    """Approximate integrated loudness (LUFS) with K-weighting and a -70 LUFS gate."""
    def kw(f):
        shelf = 10 ** (4 / (1 + (1500 / np.maximum(f, 1)) ** 2) / 20)
        hp = 1 / np.sqrt(1 + (38 / np.maximum(f, 1e-3)) ** 4)
        return shelf * hp
    y = _fft_filter(x, kw)
    block = int(0.4 * SR)
    hop = block // 4
    powers = []
    for s in range(0, max(1, y.shape[-1] - block), hop):
        powers.append(np.mean(y[:, s:s + block] ** 2, axis=1).sum())
    p = np.array(powers) if powers else np.array([np.mean(y ** 2, axis=1).sum()])
    lufs = -0.691 + 10 * np.log10(np.maximum(p, 1e-12))
    gated = p[lufs > -70]
    if not gated.size:
        return -70.0
    rel = -0.691 + 10 * np.log10(gated.mean()) - 10
    gated = p[(lufs > -70) & (lufs > rel)]
    return float(-0.691 + 10 * np.log10(max(gated.mean(), 1e-12)))


def limiter(x: np.ndarray, ceiling_db: float = -1.0, lookahead_s: float = 0.005, release_s: float = 0.08) -> np.ndarray:
    ceiling = 10 ** (ceiling_db / 20)
    block = 64
    n = x.shape[-1]
    nb = -(-n // block)
    padded = np.zeros((2, nb * block), np.float32)
    padded[:, :n] = x
    peaks = np.abs(padded).max(axis=0).reshape(nb, block).max(axis=1)
    la = max(1, int(lookahead_s * SR / block))
    ahead = np.array([peaks[i:i + la + 1].max() for i in range(nb)])
    target = np.minimum(1.0, ceiling / np.maximum(ahead, 1e-9))
    rel = np.exp(-block / (release_s * SR))
    gain = np.empty(nb)
    g = 1.0
    for i in range(nb):
        g = target[i] if target[i] < g else target[i] + (g - target[i]) * rel
        gain[i] = g
    per_sample = np.interp(np.arange(nb * block), np.arange(nb) * block + block / 2, gain)[:n]
    return np.clip(x * per_sample, -ceiling, ceiling).astype(np.float32)


# ------------------------------------------------------------------------------ render
def _kick_times(proj: Project) -> list[float]:
    d, bpb = proj.data, proj.beats_per_bar
    spb = 60 / d["bpm"]
    times = []
    for pl in d["arrangement"]:
        pat = d["patterns"][pl["pattern"]]
        agent = d["agents"][pat["agent"]]
        if agent["role"] != "drums":
            continue
        for rep in range(pl["repeat"]):
            base = (pl["start_bar"] - 1) * bpb + rep * pat["length_beats"]
            times += [(base + n["start"]) * spb for n in pat["notes"] if n["pitch"] in (35, 36)]
    return times


def render(proj: Project, fmt: str = "mp3", stems: bool = False, sidechain: bool | None = None,
           target_lufs: float = -14.0, synth: Callable[[Path, Path], None] | None = None) -> dict[str, Any]:
    d = proj.data
    if not d["arrangement"]:
        raise RenderError("the arrangement is empty: call arrange first")
    synth = synth or fluidsynth_render
    out_dir = proj.dir / "render"
    work = out_dir / "work"
    work.mkdir(parents=True, exist_ok=True)

    spb = 60 / d["bpm"]
    song_s = proj.song_bars() * proj.beats_per_bar * spb
    song_n = int(round(song_s * SR))
    tail_n = int(3.5 * SR)
    total_n = song_n + tail_n
    if sidechain is None:
        genre = f"{d.get('genre', '')} {d.get('mood', '')}".lower()
        sidechain = any(w in genre for w in ELECTRONIC_WORDS)
    kicks = _kick_times(proj) if sidechain else []

    dry = np.zeros((2, total_n), np.float32)
    verb_bus = np.zeros((2, total_n), np.float32)
    stem_files = []
    rendered = []
    for agent in sorted(d["agents"].values(), key=lambda a: a["channel"]):
        mid = work / f"{agent['channel']:02d}-{agent['id']}.mid"
        if not export.export_midi(proj, mid, only_agent=agent["id"])["tracks"][0]["notes"]:
            continue
        wav = work / f"{agent['channel']:02d}-{agent['id']}.wav"
        synth(mid, wav)
        x = read_wav(wav)
        x = x[:, :total_n] if x.shape[1] >= total_n else np.pad(x, ((0, 0), (0, total_n - x.shape[1])))
        mix = ROLE_MIX.get(agent["role"], ROLE_MIX["other"])
        x = eq(x, hp_hz=mix["hp"], mud_db=mix["mud"])
        if kicks and mix["duck"]:
            x *= sidechain_env(kicks, total_n, mix["duck"], release_s=spb * 0.9)
        x *= 10 ** (agent["volume_db"] / 20)
        width = -1.0 if agent["role"] in ("bass",) else 0.3 if agent["role"] in ("pad", "choir", "strings", "atmosphere") else 0.0
        x = pan_width(x, agent["pan"], width)
        if mix["delay"]:
            dl = pingpong_delay(x, delay_s=spb * 0.75)[:, :total_n] * mix["delay"]
            x = x + np.pad(dl, ((0, 0), (0, total_n - dl.shape[1])))
        dry += x
        verb_bus += x * mix["verb"]
        rendered.append(agent["id"])
        if stems:
            sp = out_dir / f"stem-{agent['channel']:02d}-{agent['id']}.wav"
            write_wav(sp, x / max(1.0, float(np.abs(x).max())))
            stem_files.append(str(sp))
    if not rendered:
        raise RenderError("no agent has notes in the arrangement")

    rt = 3.2 if any(w in d.get("genre", "").lower() for w in ("orchestr", "film", "cinematic", "ambient", "choir", "opera")) else 2.2
    wet = convolve(verb_bus, reverb_ir(rt))[:, :total_n] * 0.5
    mixbus = dry + wet

    if d["loop"]:
        tail = mixbus[:, song_n:]
        mixbus = mixbus[:, :song_n].copy()
        mixbus[:, :tail.shape[1]] += tail[:, :song_n]
    else:
        fade = np.linspace(1, 0, tail_n) ** 2
        mixbus[:, song_n:] *= fade

    mixbus = eq(mixbus, air_db=1.0)
    lufs_in = k_weighted_loudness(mixbus)
    mixbus *= 10 ** ((target_lufs - lufs_in) / 20)
    master = limiter(mixbus, ceiling_db=-1.0)
    lufs_out = k_weighted_loudness(master)

    base = d["slug"]
    wav_path = out_dir / f"{base}.wav"
    write_wav(wav_path, master)
    midi_path = out_dir / f"{base}.mid"
    export.export_midi(proj, midi_path)
    result: dict[str, Any] = {
        "wav": str(wav_path), "midi": str(midi_path), "stems": stem_files,
        "duration_s": round(master.shape[1] / SR, 2), "bars": proj.song_bars(), "loop": d["loop"],
        "loudness_lufs": round(lufs_out, 1), "peak_db": round(20 * np.log10(max(float(np.abs(master).max()), 1e-9)), 2),
        "sidechain": bool(kicks), "agents_rendered": rendered,
    }
    if fmt == "mp3":
        ff = ffmpeg_exe()
        if not ff:
            result["mp3"] = None
            result["note"] = "ffmpeg not found: delivered WAV only (pip install imageio-ffmpeg to enable MP3)"
        else:
            mp3 = out_dir / f"{base}.mp3"
            res = subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(wav_path), "-codec:a", "libmp3lame",
                                  "-b:a", "320k", str(mp3)], capture_output=True, text=True, timeout=300)
            if res.returncode != 0:
                raise RenderError(f"MP3 encoding failed: {res.stderr.strip()[:300]}")
            result["mp3"] = str(mp3)
    shutil.rmtree(work, ignore_errors=True)
    return result
