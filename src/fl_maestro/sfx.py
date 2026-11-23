"""Procedural game sound effects: every sound is synthesized from scratch, so each seed is unique.

Recipes combine oscillators (with pitch sweeps), FM, modal synthesis (inharmonic metal/bell partials),
filtered noise, granular crunch and bubble physics. A style colours every recipe (retro, cartoon,
realistic, magical, scifi), and an optional space adds a room, hall or cave.
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any, Callable

import numpy as np

SR = 44100

STYLES = ("realistic", "retro", "cartoon", "magical", "scifi")
SPACES = ("dry", "room", "hall", "cave")
MATERIALS = ("grass", "dirt", "gravel", "wood", "stone", "metal", "snow", "sand", "puddle")


# ============================================================================ primitives
def t_axis(seconds: float) -> np.ndarray:
    return np.arange(int(seconds * SR)) / SR


def exp_env(n: int, decay_s: float, attack_s: float = 0.002) -> np.ndarray:
    t = np.arange(n) / SR
    att = np.clip(t / max(attack_s, 1e-4), 0, 1)
    return att * np.exp(-t / max(decay_s, 1e-4))


def adsr(n: int, a: float, d: float, s: float, r: float) -> np.ndarray:
    a_n, d_n, r_n = int(a * SR), int(d * SR), int(r * SR)
    s_n = max(0, n - a_n - d_n - r_n)
    env = np.concatenate([np.linspace(0, 1, a_n, endpoint=False), np.linspace(1, s, d_n, endpoint=False),
                          np.full(s_n, s), np.linspace(s, 0, r_n)])
    return np.pad(env, (0, max(0, n - env.size)))[:n]


def osc(freq: np.ndarray | float, n: int, shape: str = "sine", phase: float = 0.0) -> np.ndarray:
    f = np.broadcast_to(np.asarray(freq, dtype=np.float64), (n,))
    ph = 2 * np.pi * np.cumsum(f) / SR + phase
    if shape == "sine":
        return np.sin(ph)
    if shape == "square":
        return np.sign(np.sin(ph))
    if shape == "pulse25":
        return np.where((ph / (2 * np.pi)) % 1 < 0.25, 1.0, -1.0)
    if shape == "saw":
        return 2 * ((ph / (2 * np.pi)) % 1) - 1
    if shape == "triangle":
        return 2 * np.abs(2 * ((ph / (2 * np.pi)) % 1) - 1) - 1
    raise ValueError(shape)


def noise(n: int, rng: np.random.Generator, color: str = "white") -> np.ndarray:
    w = rng.standard_normal(n)
    if color == "white":
        return w
    spec = np.fft.rfft(w)
    f = np.fft.rfftfreq(n, 1 / SR)
    f[0] = f[1] if n > 1 else 1
    spec /= np.sqrt(f) if color == "pink" else f  # brown
    out = np.fft.irfft(spec, n)
    return out / (np.abs(out).max() + 1e-9)


def svf(x: np.ndarray, cutoff: np.ndarray | float, q: float = 0.7, mode: str = "lp") -> np.ndarray:
    """Chamberlin state-variable filter with a per-sample cutoff (for sweeps)."""
    n = x.size
    fc = np.broadcast_to(np.asarray(cutoff, dtype=np.float64), (n,))
    f = 2 * np.sin(np.pi * np.clip(fc, 20, SR / 6) / SR)
    damp = 1 / max(q, 0.5)
    low = band = 0.0
    out = np.empty(n)
    xs = x.tolist()
    fs = f.tolist()
    pick = {"lp": 0, "bp": 1, "hp": 2}[mode]
    for i in range(n):
        fi = fs[i]
        low += fi * band
        high = xs[i] - low - damp * band
        band += fi * high
        out[i] = (low, band, high)[pick]
    return out


def fft_filter(x: np.ndarray, gain: Callable[[np.ndarray], np.ndarray]) -> np.ndarray:
    n = x.size
    spec = np.fft.rfft(x)
    spec *= gain(np.fft.rfftfreq(n, 1 / SR))
    return np.fft.irfft(spec, n)


def lowpass(x: np.ndarray, hz: float) -> np.ndarray:
    return fft_filter(x, lambda f: 1 / np.sqrt(1 + (f / hz) ** 4))


def highpass(x: np.ndarray, hz: float) -> np.ndarray:
    return fft_filter(x, lambda f: 1 / np.sqrt(1 + (hz / np.maximum(f, 1e-3)) ** 4))


def bandpass(x: np.ndarray, hz: float, octaves: float = 1.0) -> np.ndarray:
    return fft_filter(x, lambda f: np.exp(-(np.log2(np.maximum(f, 1) / hz) / octaves) ** 2))


def modal(freqs: list[float], decays: list[float], amps: list[float], seconds: float,
          rng: np.random.Generator) -> np.ndarray:
    n = int(seconds * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)
    for f, d, a in zip(freqs, decays, amps):
        out += a * np.sin(2 * np.pi * f * t + rng.uniform(0, 2 * np.pi)) * np.exp(-t / d)
    return out * np.clip(t / 0.0008, 0, 1)


def bubble(radius_mm: float, seconds: float, rng: np.random.Generator, rise: float = 1.0) -> np.ndarray:
    """Minnaert resonance with the upward chirp of a bubble near the surface."""
    f0 = 3260 / max(radius_mm, 0.3)  # Hz, Minnaert approximation for water
    t = t_axis(seconds)
    freq = f0 * (1 + rise * 1.6 * t / seconds) ** 1.2
    decay = 0.012 + 0.03 * radius_mm / 3
    return np.sin(2 * np.pi * np.cumsum(freq) / SR) * np.exp(-t / decay) * np.clip(t / 0.0005, 0, 1)


def place(buf: np.ndarray, sound: np.ndarray, at_s: float, gain: float = 1.0) -> None:
    i = int(at_s * SR)
    if i >= buf.size:
        return
    end = min(buf.size, i + sound.size)
    buf[i:end] += sound[:end - i] * gain


def crunch(seconds: float, density: float, center: float, rng: np.random.Generator, spread: float = 0.8) -> np.ndarray:
    """Granular crunch: many tiny filtered clicks (gravel, snow, leaves)."""
    out = np.zeros(int(seconds * SR))
    count = max(1, int(density * seconds))
    for _ in range(count):
        g_len = rng.uniform(0.002, 0.012)
        g = noise(int(g_len * SR) + 8, rng) * exp_env(int(g_len * SR) + 8, g_len / 3)
        g = bandpass(g, center * 2 ** rng.uniform(-spread, spread), 0.8)
        place(out, g, rng.beta(1.4, 3) * seconds, rng.uniform(0.3, 1))
    return out


def bitcrush(x: np.ndarray, bits: int = 6, hold: int = 4) -> np.ndarray:
    held = np.repeat(x[::hold], hold)[:x.size]
    q = 2 ** (bits - 1)
    return np.round(held * q) / q


def note_hz(semitones_from_a4: float) -> float:
    return 440 * 2 ** (semitones_from_a4 / 12)


# ============================================================================ recipes
# Every recipe: (rng, p) -> mono float array. p holds pitch (semitones), length (multiplier),
# brightness (0-1), intensity (0-1), style, material.

def r_coin(rng, p):
    st, k = p["style"], 2 ** (p["pitch"] / 12)
    if st == "retro":
        a, b = note_hz(26 + p["pitch"]), note_hz(31 + p["pitch"] + rng.choice([0, 0, 2]))
        n1, n2 = int(0.06 * SR * p["length"]), int(0.34 * SR * p["length"])
        s1 = osc(a, n1, "pulse25") * 0.5
        s2 = osc(b, n2, "pulse25") * 0.5 * exp_env(n2, 0.12 * p["length"])
        return np.concatenate([s1, s2])
    # metallic coin: two clinks with inharmonic partials
    base = rng.uniform(1900, 2600) * k
    ratios = [1, 2.09 + rng.uniform(-.05, .05), 3.43, 5.11 + rng.uniform(-.1, .1), 7.2]
    seconds = 0.55 * p["length"]
    hit = lambda f, g: modal([f * r for r in ratios], [0.35, 0.22, 0.14, 0.09, 0.05], [1, .55, .4 * (.5 + p["brightness"]), .25, .15], seconds, rng) * g
    out = np.zeros(int((seconds + 0.12) * SR))
    place(out, hit(base, 1.0), 0)
    if st in ("cartoon", "magical"):
        place(out, hit(base * 1.335, 0.9), 0.075 * p["length"])  # rising fourth: "ka-ching"
    else:
        place(out, hit(base * rng.uniform(1.02, 1.08), 0.45), rng.uniform(0.05, 0.09))
    click = highpass(noise(400, rng), 5000) * exp_env(400, 0.002)
    place(out, click, 0, 0.3)
    if st == "magical":
        out += r_sparkle(rng, {**p, "length": p["length"] * 0.6})[:out.size] * 0.35 if out.size else 0
    return out


def r_ding(rng, p):
    st = p["style"]
    f = note_hz(15 + p["pitch"]) * rng.uniform(0.99, 1.01)
    seconds = 1.4 * p["length"]
    if st == "retro":
        n = int(seconds * 0.5 * SR)
        return osc(f, n, "square") * exp_env(n, 0.18 * p["length"]) * 0.5
    ratios = [0.5, 1, 1.19, 1.56, 2.0, 2.51, 3.01]  # bell partials
    amps = [0.5, 1, 0.45, 0.35, 0.3 * (0.4 + p["brightness"]), 0.2 * p["brightness"], 0.12 * p["brightness"]]
    decays = [1.2, 0.9, 0.5, 0.4, 0.3, 0.2, 0.15]
    s = modal([f * r * rng.uniform(0.997, 1.003) for r in ratios], [d * p["length"] for d in decays], amps, seconds, rng)
    if st == "scifi":
        s *= 1 + 0.5 * np.sin(2 * np.pi * 7 * t_axis(seconds))
    return s


def r_click(rng, p):
    st = p["style"]
    n = int(0.05 * SR * p["length"])
    if st == "retro":
        return osc(note_hz(24 + p["pitch"]), int(0.025 * SR), "square") * exp_env(int(0.025 * SR), 0.008) * 0.6
    tr = highpass(noise(n, rng), 2500 + 4000 * p["brightness"]) * exp_env(n, 0.0025)
    body = osc(rng.uniform(1200, 1800) * 2 ** (p["pitch"] / 12), n) * exp_env(n, 0.006)
    return tr * 0.7 + body * 0.5 * (0.5 + p["intensity"])


def r_whoosh(rng, p):
    seconds = 0.55 * p["length"]
    n = int(seconds * SR)
    t = np.linspace(0, 1, n)
    peak = rng.uniform(0.4, 0.6)
    shape = np.exp(-((t - peak) / 0.22) ** 2)
    center = (300 + 2500 * p["brightness"]) * 2 ** (p["pitch"] / 12) * (0.4 + 1.2 * shape)
    if p["style"] == "scifi":
        center *= 1 + 0.3 * np.sin(2 * np.pi * 18 * t)
    s = svf(noise(n, rng, "pink"), center, q=1.8 + 2 * p["intensity"], mode="bp")
    s *= shape
    if p["style"] == "cartoon":
        s += osc(center * 0.5, n, "sine") * shape * 0.25
    return s


def r_footstep(rng, p):
    mat = p["material"]
    seconds = 0.32 * p["length"]
    n = int(seconds * SR)
    out = np.zeros(n)
    k = 2 ** (p["pitch"] / 12)
    weight = 0.5 + p["intensity"]
    # heel thump
    thump_n = int(0.09 * SR)
    thump = osc(rng.uniform(55, 95) * k * np.linspace(1.3, 0.8, thump_n), thump_n) * exp_env(thump_n, 0.025)
    soft = {"grass": .5, "dirt": .8, "gravel": .7, "wood": 1, "stone": 1, "metal": .8, "snow": .4, "sand": .45, "puddle": .6}[mat]
    place(out, thump, 0, 0.7 * weight * soft)
    toe_at = rng.uniform(0.045, 0.08)
    if mat in ("wood",):
        modes = [rng.uniform(180, 260) * k, rng.uniform(420, 560) * k, rng.uniform(800, 1100) * k]
        for at, g in ((0, 1), (toe_at, 0.5)):
            place(out, modal(modes, [.05, .03, .02], [1, .6, .3], 0.15, rng), at, 0.6 * g * weight)
            place(out, bandpass(noise(800, rng), 1800 * k, 1.2) * exp_env(800, 0.004), at, 0.4 * g)
    elif mat == "stone":
        for at, g in ((0, 1), (toe_at, 0.55)):
            place(out, bandpass(noise(1500, rng), rng.uniform(1500, 2600) * k, 1.0) * exp_env(1500, 0.006), at, g)
        place(out, crunch(0.08, 120, 3500 * k, rng), 0.01, 0.15)
    elif mat == "metal":
        modes = [f * k for f in (rng.uniform(380, 520), rng.uniform(1100, 1400), rng.uniform(2300, 2800), rng.uniform(3900, 4500))]
        for at, g in ((0, 1), (toe_at, 0.5)):
            place(out, modal(modes, [.18, .12, .08, .05], [1, .6, .4, .25], 0.3, rng), at, 0.5 * g * weight)
    elif mat == "gravel":
        place(out, crunch(0.22 * p["length"], 900 + 600 * p["intensity"], 2600 * k, rng, 1.1), 0, 0.9)
    elif mat == "snow":
        c = lowpass(crunch(0.26 * p["length"], 1400, 1800 * k, rng, 0.9), 3500)
        place(out, c, 0.005, 1.2)
    elif mat == "sand":
        place(out, lowpass(crunch(0.2 * p["length"], 700, 1500 * k, rng, 1.2), 2600), 0, 0.8)
        place(out, lowpass(noise(int(0.12 * SR), rng, "pink"), 1500) * exp_env(int(0.12 * SR), 0.03), 0, 0.3)
    elif mat == "grass":
        sw = highpass(noise(int(0.18 * SR), rng, "pink"), 1800) * adsr(int(0.18 * SR), 0.015, 0.05, 0.3, 0.08)
        place(out, sw, 0, 0.5)
        place(out, crunch(0.15, 260, 4200 * k, rng), 0.01, 0.25)
    elif mat == "dirt":
        place(out, lowpass(noise(int(0.08 * SR), rng, "brown"), 900) * exp_env(int(0.08 * SR), 0.02), 0, 0.9)
        place(out, crunch(0.12, 220, 1600 * k, rng), toe_at * 0.6, 0.35)
    elif mat == "puddle":
        place(out, lowpass(noise(int(0.1 * SR), rng), 2500) * exp_env(int(0.1 * SR), 0.03), 0, 0.5)
        for _ in range(rng.integers(5, 10)):
            place(out, bubble(rng.uniform(0.8, 2.5), 0.06, rng), rng.uniform(0.01, 0.2), rng.uniform(0.15, 0.4))
    return out


def r_water(rng, p):
    """material picks the variant: drop (default), splash, bubbles, pour."""
    variant = p.get("variant") or "drop"
    k = 2 ** (p["pitch"] / 12)
    if variant == "drop":
        s = bubble(rng.uniform(1.4, 2.6) / k, 0.18 * p["length"], rng, rise=1 + p["brightness"])
        tick = highpass(noise(300, rng), 3000) * exp_env(300, 0.0015)
        s[:300] += tick * 0.25
        return s
    seconds = {"splash": 0.9, "bubbles": 1.2, "pour": 2.5}.get(variant, 1.0) * p["length"]
    out = np.zeros(int(seconds * SR))
    if variant == "splash":
        n = int(0.5 * SR)
        place(out, bandpass(noise(n, rng), 1200 * k, 2.0) * exp_env(n, 0.09 * (0.5 + p["intensity"])), 0, 0.8)
        count = int(30 + 40 * p["intensity"])
        for _ in range(count):
            place(out, bubble(rng.uniform(0.6, 3.0) / k, 0.08, rng), rng.exponential(0.12), rng.uniform(0.05, 0.3))
    else:
        rate = 14 if variant == "bubbles" else 70
        for _ in range(int(rate * seconds)):
            r = rng.uniform(0.8, 3.5) / k if variant == "bubbles" else rng.uniform(0.5, 2.0) / k
            place(out, bubble(r, 0.07, rng), rng.uniform(0, seconds - 0.05), rng.uniform(0.1, 0.35))
        if variant == "pour":
            out += lowpass(noise(out.size, rng, "pink"), 2200) * 0.12 * adsr(out.size, 0.1, 0.2, 0.9, 0.4)
    return out


def r_jump(rng, p):
    seconds = 0.28 * p["length"]
    n = int(seconds * SR)
    t = np.linspace(0, 1, n)
    base = note_hz(-5 + p["pitch"]) * rng.uniform(0.95, 1.05)
    if p["style"] == "retro":
        f = base * (1 + 2.2 * t ** 0.7)
        return osc(f, n, "square") * (1 - t) ** 0.6 * 0.5
    if p["style"] == "cartoon":  # boing: spring wobble
        f = base * 1.4 * (1 + 0.35 * np.sin(2 * np.pi * 18 * t) * np.exp(-3 * t)) * (1 + 0.6 * t)
        return osc(f, n) * exp_env(n, seconds * 0.5)
    f = base * 2 * (1 + 1.4 * t)
    out = osc(f, n, "triangle") * exp_env(n, seconds * 0.35) * 0.7
    place(out, r_whoosh(rng, {**p, "length": p["length"] * 0.4}), 0, 0.4)
    return out


def r_laser(rng, p):
    seconds = 0.35 * p["length"]
    n = int(seconds * SR)
    t = np.linspace(0, 1, n)
    f = note_hz(30 + p["pitch"]) * (1 - 0.85 * t ** 0.5) * rng.uniform(0.9, 1.1)
    mod = osc(f * 1.5, n) * 600 * (0.5 + p["brightness"])
    s = osc(f + mod, n, "saw" if p["style"] != "retro" else "square") * exp_env(n, seconds * 0.45)
    return lowpass(s, 4000 + 6000 * p["brightness"]) * 0.6


def r_explosion(rng, p):
    seconds = 2.2 * p["length"]
    n = int(seconds * SR)
    t = np.arange(n) / SR
    body = noise(n, rng, "brown") * exp_env(n, 0.45 * p["length"] * (0.6 + p["intensity"]), 0.004)
    cut = 9000 * np.exp(-t / (0.25 * p["length"])) + 150
    body = svf(body, cut, 0.6, "lp")
    sub_f = 70 * 2 ** (p["pitch"] / 12) * np.exp(-t / 0.4) + 28
    sub = osc(sub_f, n) * exp_env(n, 0.35 * p["length"])
    crack = highpass(noise(int(0.04 * SR), rng), 2000) * exp_env(int(0.04 * SR), 0.01)
    out = body * 1.0 + sub * 0.8
    out[:crack.size] += crack * 0.7
    debris = crunch(seconds * 0.8, 120 * p["intensity"], 2500, rng, 1.2)
    place(out, debris, 0.15, 0.25)
    out = np.tanh(out / (np.abs(out).max() + 1e-9) * (2.5 + 2 * p["intensity"]))  # saturate: weight, not just peaks
    if p["style"] == "retro":
        out = bitcrush(out, 5, 6)
    return out


def r_hit(rng, p):
    seconds = 0.4 * p["length"]
    n = int(seconds * SR)
    k = 2 ** (p["pitch"] / 12)
    thump = osc(rng.uniform(60, 90) * k * np.linspace(1.8, 0.7, n), n) * exp_env(n, 0.05 * p["length"])
    snap = bandpass(noise(n, rng), rng.uniform(900, 1600) * k, 1.3) * exp_env(n, 0.015)
    out = thump * (0.6 + 0.6 * p["intensity"]) + snap * (0.5 + 0.5 * p["brightness"])
    if p["style"] == "cartoon":
        out += osc(note_hz(10 + p["pitch"]) * np.linspace(1.5, 0.6, n), n) * exp_env(n, 0.06) * 0.3
    if p["style"] == "retro":
        out = bitcrush(out / (np.abs(out).max() + 1e-9), 5, 8)
    return out


def r_powerup(rng, p):
    st = p["style"]
    scale = [0, 4, 7, 12, 16, 19, 24] if rng.random() < 0.6 else [0, 3, 7, 10, 12, 15, 19, 24]
    step = 0.055 * p["length"]
    root = 3 + p["pitch"] + rng.choice([0, 2, 5])
    shape = "square" if st == "retro" else "triangle" if st == "cartoon" else "sine"
    out = np.zeros(int((step * len(scale) + 0.5) * SR))
    for i, iv in enumerate(scale):
        nn = int(0.22 * SR)
        tone = osc(note_hz(root + iv), nn, shape) * exp_env(nn, 0.12) * (0.6 + 0.4 * i / len(scale))
        place(out, tone, i * step, 0.5)
    if st in ("magical", "scifi"):
        place(out, r_sparkle(rng, p), step * 2, 0.4)
    return out


def r_hurt(rng, p):
    seconds = 0.4 * p["length"]
    n = int(seconds * SR)
    t = np.linspace(0, 1, n)
    f = note_hz(5 + p["pitch"]) * (1 - 0.5 * t) * (1 + 0.05 * np.sin(2 * np.pi * 30 * t))
    tone = osc(f, n, "square" if p["style"] == "retro" else "saw") * exp_env(n, seconds * 0.4)
    grit = bandpass(noise(n, rng), 1200, 1.5) * exp_env(n, 0.05)
    out = lowpass(tone, 2500 + 3000 * p["brightness"]) * 0.6 + grit * 0.35 * p["intensity"]
    return np.tanh(out * (1 + 2 * p["intensity"]))


def r_pickup(rng, p):
    n = int(0.16 * SR * p["length"])
    t = np.linspace(0, 1, n)
    f = note_hz(24 + p["pitch"]) * (1 + 0.5 * t) * rng.uniform(0.97, 1.03)
    shape = "square" if p["style"] == "retro" else "sine"
    return osc(f, n, shape) * exp_env(n, 0.06 * p["length"]) * 0.7 + osc(f * 2, n) * exp_env(n, 0.03) * 0.2 * p["brightness"]


def r_sparkle(rng, p):
    seconds = 1.2 * p["length"]
    out = np.zeros(int(seconds * SR))
    for _ in range(int(18 + 20 * p["intensity"])):
        f = note_hz(rng.choice([24, 28, 31, 36, 40, 43]) + p["pitch"]) * rng.uniform(0.995, 1.005)
        nn = int(0.25 * SR)
        place(out, osc(f, nn) * exp_env(nn, rng.uniform(0.04, 0.12)), rng.beta(1.2, 2.5) * seconds, rng.uniform(0.1, 0.35))
    return out


def r_error(rng, p):
    st = p["style"]
    out = np.zeros(int(0.45 * SR * p["length"]))
    shape = "square" if st in ("retro", "scifi") else "triangle"
    for i, semi in enumerate((-2, -6)):
        nn = int(0.16 * SR * p["length"])
        place(out, lowpass(osc(note_hz(semi + p["pitch"]), nn, shape), 2500) * adsr(nn, 0.005, 0.05, 0.6, 0.05), i * 0.17 * p["length"], 0.5)
    return out


def r_success(rng, p):
    st = p["style"]
    chord = [0, 4, 7, 12]
    step = 0.09 * p["length"]
    out = np.zeros(int((step * 4 + 1.2) * SR))
    shape = "square" if st == "retro" else "triangle" if st == "cartoon" else "sine"
    root = p["pitch"] + rng.choice([0, 2, 3, 5])
    for i, iv in enumerate(chord):
        last = i == len(chord) - 1
        nn = int((1.0 if last else 0.2) * SR)
        tone = osc(note_hz(root + iv), nn, shape) + 0.3 * osc(note_hz(root + iv + 12), nn)
        place(out, tone * exp_env(nn, 0.5 if last else 0.12), i * step, 0.4)
    if st == "magical":
        place(out, r_sparkle(rng, p), step * 3, 0.35)
    return out


RECIPES: dict[str, Callable] = {
    "coin": r_coin, "ding": r_ding, "ui_click": r_click, "whoosh": r_whoosh, "footstep": r_footstep,
    "water": r_water, "jump": r_jump, "laser": r_laser, "explosion": r_explosion, "hit": r_hit,
    "powerup": r_powerup, "hurt": r_hurt, "pickup": r_pickup, "magic": r_sparkle, "error": r_error,
    "success": r_success,
}
KINDS = tuple(RECIPES)
WATER_VARIANTS = ("drop", "splash", "bubbles", "pour")


# ============================================================================ finishing
def finish(x: np.ndarray, rng: np.random.Generator, space: str, style: str, width: float = 0.25) -> np.ndarray:
    x = x - np.mean(x)
    x = highpass(x, 25)
    if style == "retro":
        x = bitcrush(x / (np.abs(x).max() + 1e-9), 8, 2)
    peak = np.abs(x).max() + 1e-9
    x = x / peak
    # stereo: decorrelated copies for width
    side = fft_filter(x, lambda f: np.exp(1j * rng.uniform(-np.pi, np.pi, f.size)) * (f > 200)).real
    stereo = np.stack([x + side * width, x - side * width])
    if space != "dry":
        from .render import convolve, reverb_ir
        rt = {"room": 0.45, "hall": 1.8, "cave": 3.2}[space]
        wet_amt = {"room": 0.18, "hall": 0.28, "cave": 0.4}[space]
        ir = reverb_ir(rt, 0.008 if space == "room" else 0.025, seed=int(rng.integers(1, 10_000)))
        wet = convolve(stereo.astype(np.float32), ir)
        dry = np.pad(stereo, ((0, 0), (0, wet.shape[1] - stereo.shape[1])))
        stereo = dry + wet * wet_amt
    # trim trailing silence, fade the very end
    level = np.abs(stereo).max(axis=0)
    above = np.nonzero(level > 10 ** (-60 / 20) * level.max())[0]
    end = min(stereo.shape[1], (above[-1] if above.size else stereo.shape[1]) + int(0.01 * SR))
    stereo = stereo[:, :end]
    fade = min(int(0.01 * SR), stereo.shape[1])
    stereo[:, -fade:] *= np.linspace(1, 0, fade)
    peak = np.abs(stereo).max() + 1e-9
    return (stereo / peak * 10 ** (-1 / 20)).astype(np.float32)


def make(kind: str, name: str, out_dir: Path, variations: int = 3, seed: int | None = None,
         style: str = "realistic", pitch: float = 0.0, length: float = 1.0, brightness: float = 0.5,
         intensity: float = 0.5, space: str = "dry", material: str = "stone", variant: str | None = None,
         formats: tuple[str, ...] = ("wav",)) -> dict[str, Any]:
    if kind not in RECIPES:
        raise ValueError(f"unknown kind {kind!r}; choose one of: {', '.join(KINDS)}")
    if style not in STYLES:
        raise ValueError(f"unknown style {style!r}; choose one of: {', '.join(STYLES)}")
    if space not in SPACES:
        raise ValueError(f"unknown space {space!r}; choose one of: {', '.join(SPACES)}")
    if material not in MATERIALS:
        raise ValueError(f"unknown material {material!r}; choose one of: {', '.join(MATERIALS)}")
    if variant is not None and variant not in WATER_VARIANTS:
        raise ValueError(f"unknown water variant {variant!r}; choose one of: {', '.join(WATER_VARIANTS)}")
    if not 1 <= variations <= 24:
        raise ValueError("variations must be 1-24")
    from .render import write_wav, ffmpeg_exe
    import subprocess
    seed = random.SystemRandom().randrange(1, 2**31) if seed is None else int(seed)
    out_dir.mkdir(parents=True, exist_ok=True)
    files = []
    for i in range(variations):
        rng = np.random.default_rng([seed, i])
        p = {"style": style, "material": material, "variant": variant,
             "pitch": pitch + (rng.uniform(-0.6, 0.6) if variations > 1 else 0),
             "length": length * (rng.uniform(0.92, 1.08) if variations > 1 else 1),
             "brightness": float(np.clip(brightness + (rng.uniform(-0.08, 0.08) if variations > 1 else 0), 0, 1)),
             "intensity": float(np.clip(intensity, 0, 1))}
        audio = finish(RECIPES[kind](rng, p), rng, space, style)
        stem = out_dir / (f"{name}_{i + 1:02d}" if variations > 1 else name)
        wav = stem.with_suffix(".wav")
        write_wav(wav, audio)
        entry = {"wav": str(wav), "seconds": round(audio.shape[1] / SR, 3)}
        for fmt in formats:
            if fmt == "wav":
                continue
            ff = ffmpeg_exe()
            if not ff:
                entry[fmt] = None
                continue
            codec = {"ogg": ["-c:a", "libvorbis", "-q:a", "6"], "mp3": ["-c:a", "libmp3lame", "-b:a", "256k"]}[fmt]
            target = stem.with_suffix("." + fmt)
            subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(wav), *codec, str(target)], check=True, timeout=120)
            entry[fmt] = str(target)
        if "wav" not in formats:
            wav.unlink()
            entry.pop("wav")
        files.append(entry)
    return {"kind": kind, "name": name, "seed": seed, "style": style, "space": space,
            "material": material if kind == "footstep" else None,
            "variant": (variant or "drop") if kind == "water" else None,
            "folder": str(out_dir), "files": files,
            "regenerate": f"same seed {seed} reproduces these files; any other seed gives new sounds"}
