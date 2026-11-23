"""Sound effects from real recordings: a bundled catalogue of 4,500+ CC0 sounds (Kenney, OpenGameArt and
others, mirrored by github.com/novincode/atomcut-library and pinned to one commit), fetched on demand and
re-processed per take (varispeed pitch, tone tilt, saturation, layering, space) so every file is new.
"""

from __future__ import annotations

import json
import re
import urllib.request
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

import numpy as np

from . import paths

SR = 44100

# Words that describe each kind, plus the tags that should win. Order matters: the first word is the core.
KIND_WORDS: dict[str, list[str]] = {
    "coin": ["coin", "coins", "money", "cash", "gold", "jackpot"],
    "ding": ["ding", "bell", "chime", "notification", "confirmation", "bong", "glass"],
    "ui_click": ["click", "button", "switch", "select", "tap", "toggle", "tick"],
    "whoosh": ["whoosh", "swish", "swoosh", "swing", "woosh", "swipe", "wind"],
    "footstep": ["footstep", "footsteps", "step", "steps", "walk", "walking", "running"],
    "water": ["water", "splash", "drop", "drip", "bubble", "bubbles", "liquid", "pour", "slime", "wet"],
    "jump": ["jump", "hop", "boing", "bounce", "spring"],
    "laser": ["laser", "phaser", "zap", "blaster", "shot", "beam", "shoot"],
    "explosion": ["explosion", "explode", "bang", "blast", "boom", "firework"],
    "hit": ["hit", "punch", "impact", "thud", "smack", "kick", "slap", "hurt"],
    "powerup": ["powerup", "power", "levelup", "level", "upgrade", "up"],
    "hurt": ["hurt", "pain", "damage", "ouch", "grunt", "death"],
    "pickup": ["pickup", "pick", "collect", "item", "get", "grab", "gem"],
    "magic": ["magic", "spell", "sparkle", "heal", "fantasy", "mana", "enchant"],
    "error": ["error", "wrong", "deny", "negative", "fail", "back", "cancel"],
    "success": ["success", "win", "victory", "complete", "positive", "jingle", "fanfare", "correct"],
}
MATERIAL_WORDS: dict[str, list[str]] = {
    "grass": ["grass", "leaves", "leaf", "bush"],
    "dirt": ["dirt", "mud", "earth", "soil"],
    "gravel": ["gravel", "rock", "pebble"],
    "wood": ["wood", "wooden", "plank", "floor"],
    "stone": ["stone", "concrete", "tile", "rock"],
    "metal": ["metal", "steel", "iron", "grate"],
    "snow": ["snow", "ice"],
    "sand": ["sand", "beach"],
    "puddle": ["puddle", "water", "wet", "splash", "mud"],
}
WATER_VARIANT_WORDS = {"drop": ["drop", "drip", "droplet"], "splash": ["splash", "slime", "wet"],
                       "bubbles": ["bubble", "bubbles", "bloop"], "pour": ["pour", "liquid", "stream", "flow"]}
STYLE_WORDS: dict[str, list[str]] = {
    "retro": ["retro", "8", "bit", "8bit", "nes", "chiptune", "digital", "arcade", "16"],
    "realistic": ["foley", "nature", "impact", "real"],
    "cartoon": ["cartoon", "funny", "casino", "jingle", "toon"],
    "magical": ["magic", "fantasy", "spell", "rpg"],
    "scifi": ["sci", "scifi", "space", "laser", "digital", "synth", "robot"],
}
_WORD = re.compile(r"[a-z0-9]+")


class LibraryError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def catalog() -> dict[str, Any]:
    data = json.loads((resources.files("fl_maestro") / "data" / "sfx_catalog.json").read_text(encoding="utf-8"))
    index = []
    for pack, file, name, tags in data["sounds"]:
        title = data["packs"][pack]["title"]
        name_words = set(_WORD.findall(f"{name} {Path(file).stem}".lower()))
        tag_words = set(_WORD.findall(" ".join(tags).lower()))
        pack_words = set(_WORD.findall(title.lower()))
        index.append({"pack": pack, "file": file, "name": name, "tags": tags, "name_words": name_words,
                      "tag_words": tag_words, "words": name_words | tag_words, "pack_words": pack_words})
    data["index"] = index
    return data


def _score(entry: dict[str, Any], core: list[str], extra: list[str], style_words: list[str], avoid: list[str]) -> float:
    """Names outweigh tags (tags are often pack-wide), tags outweigh the pack title."""
    nw, tw, pw = entry["name_words"], entry["tag_words"], entry["pack_words"]
    s = 0.0
    for i, word in enumerate(core):
        primary = i < 2
        if word in nw:
            s += 3.0 if primary else 2.0
        elif word in tw:
            s += 1.2 if primary else 0.8
        elif word in pw:
            s += 0.6 if primary else 0.3
    for word in extra:
        if word in nw:
            s += 3.0
        elif word in tw:
            s += 1.2
        elif word in pw:
            s += 0.8
    for word in style_words:
        if word in nw or word in tw or word in pw:
            s += 0.8
    for word in avoid:
        if word in nw:
            s -= 4
        elif word in tw:
            s -= 1
    return s


def search(query: str = "", kind: str | None = None, style: str | None = None, material: str | None = None,
           variant: str | None = None, limit: int = 12) -> list[dict[str, Any]]:
    """Rank catalogue sounds for a kind and/or free-text query."""
    core = list(KIND_WORDS.get(kind or "", []))
    if kind == "water" and variant:
        core = WATER_VARIANT_WORDS.get(variant, [variant]) + ["water", "wet"]
    extra = _WORD.findall(query.lower())
    if kind == "footstep" and material:
        extra += MATERIAL_WORDS.get(material, [material])
    style_words = STYLE_WORDS.get(style or "", [])
    avoid: list[str] = []
    if style == "realistic":
        avoid = ["8", "bit", "nes", "retro", "chiptune", "synth"]
    if kind == "footstep":
        avoid += ["jump", "door", "sword"]
        if material:
            own = set(MATERIAL_WORDS.get(material, []))
            avoid += [m for mat, words in MATERIAL_WORDS.items() if mat != material for m in words[:1] if m not in own]
    if kind == "ding":
        avoid += ["breaking", "break", "shatter", "smash"]
    if kind == "coin":
        avoid += ["slot", "machine"]
    if kind == "hit":
        avoid += ["voice", "grunt", "scream"]
    pool = catalog()["index"]
    if kind == "footstep" and material:  # the surface must be named, if the catalogue has it
        words = set(MATERIAL_WORDS.get(material, [material]))
        strict = [e for e in pool if words & e["words"] and {"step", "steps", "footstep", "footsteps", "walking", "walk"} & (e["words"] | e["pack_words"])]
        if len(strict) >= 2:
            pool = strict
            materials = {w for ws in MATERIAL_WORDS.values() for w in ws}
            avoid = [a for a in avoid if a not in materials]
    ranked = []
    for e in pool:
        sc = _score(e, core, extra, style_words, avoid)
        need = 2.5 if (core or extra) else 0
        if sc >= need:
            ranked.append((sc, e))
    ranked.sort(key=lambda r: (-r[0], r[1]["name"]))
    return [{"pack": e["pack"], "file": e["file"], "name": e["name"], "tags": e["tags"], "score": round(sc, 1)}
            for sc, e in ranked[:limit]]


def fetch(entry: dict[str, Any]) -> Path:
    cat = catalog()
    cache = paths.projects_root() / "tools" / "sfx-cache" / cat["commit"][:12] / entry["pack"]
    dest = cache / Path(entry["file"]).name
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    cache.mkdir(parents=True, exist_ok=True)
    url = f"https://raw.githubusercontent.com/novincode/atomcut-library/{cat['commit']}/packs/{entry['pack']}/{entry['file']}"
    req = urllib.request.Request(url, headers={"User-Agent": "fl-studio-maestro"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
    except Exception as exc:  # offline, rate limit...
        raise LibraryError(f"could not download {entry['name']} ({exc}); use engine='synth' to work offline") from None
    tmp = dest.with_suffix(dest.suffix + ".part")
    tmp.write_bytes(data)
    tmp.replace(dest)
    return dest


def load(path: Path) -> np.ndarray:
    from .analysis import load_audio
    x = load_audio(path, SR, mono=False).astype(np.float32)
    return x


# ------------------------------------------------------------------------------ processing
def _trim(x: np.ndarray, threshold_db: float = -50) -> np.ndarray:
    level = np.abs(x).max(axis=0)
    peak = level.max() + 1e-9
    idx = np.nonzero(level > peak * 10 ** (threshold_db / 20))[0]
    if not idx.size:
        return x
    start = max(0, idx[0] - int(0.002 * SR))
    end = min(x.shape[1], idx[-1] + int(0.02 * SR))
    return x[:, start:end]


def _varispeed(x: np.ndarray, semitones: float) -> np.ndarray:
    """Tape-style pitch shift (pitch and length together), the classic way to vary game SFX."""
    if abs(semitones) < 1e-3:
        return x
    ratio = 2 ** (semitones / 12)
    n = x.shape[1]
    new_n = max(16, int(n / ratio))
    src = np.linspace(0, n - 1, new_n)
    return np.stack([np.interp(src, np.arange(n), ch) for ch in x]).astype(np.float32)


def _tilt(x: np.ndarray, db: float, pivot: float = 1500) -> np.ndarray:
    if abs(db) < 0.05:
        return x
    from .sfx import fft_filter
    g = lambda f: 10 ** (db * np.tanh(np.log2(np.maximum(f, 20) / pivot) / 2) / 20)
    return np.stack([fft_filter(ch, g) for ch in x]).astype(np.float32)


def _shape_length(x: np.ndarray, length: float) -> np.ndarray:
    """length < 1 shortens with a fade; length > 1 lets the tail ring (handled by space)."""
    if length >= 0.999:
        return x
    n = max(int(x.shape[1] * length), int(0.03 * SR))
    y = x[:, :n].copy()
    f = min(int(0.04 * SR), n // 2)
    y[:, -f:] *= np.linspace(1, 0, f) ** 2
    return y


def process(sources: list[np.ndarray], rng: np.random.Generator, p: dict[str, Any], space: str) -> np.ndarray:
    base = _trim(sources[0])
    base = _varispeed(base, p["pitch"] + rng.uniform(-1.2, 1.2))
    if len(sources) > 1 and p.get("layer"):
        layer = _varispeed(_trim(sources[1]), p["pitch"] + rng.uniform(-2, 2) + rng.choice([0, 0, 12, -12]))
        n = max(base.shape[1], layer.shape[1])
        base = np.pad(base, ((0, 0), (0, n - base.shape[1])))
        offset = int(rng.uniform(0, 0.012) * SR)
        layer = np.pad(layer, ((0, 0), (offset, max(0, n - layer.shape[1] - offset))))[:, :n]
        base = base + layer * rng.uniform(0.25, 0.5)
    base = _tilt(base, (p["brightness"] - 0.5) * 10 + rng.uniform(-1.5, 1.5))
    if p["intensity"] > 0.55:  # weight: saturate and lift the lows
        drive = 1 + (p["intensity"] - 0.55) * 6
        base = np.tanh(base / (np.abs(base).max() + 1e-9) * drive)
        base = _tilt(base, -2.0 * (p["intensity"] - 0.55) * 2, pivot=400)
    base = _shape_length(base, p["length"])
    return base


def credits_line(entry: dict[str, Any]) -> str:
    pack = catalog()["packs"][entry["pack"]]
    return f"{entry['name']} — {pack['attribution'] or pack['title']} — {pack['homepage']}".strip(" —")
