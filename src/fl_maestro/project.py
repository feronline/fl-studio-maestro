"""The Maestro session: plan, agents, patterns and arrangement, persisted as JSON."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from . import paths, theory

ROLES = (
    "drums", "percussion", "bass", "chords", "pad", "lead", "vocal", "choir",
    "counter_melody", "arp", "strings", "brass", "woodwinds", "fx", "atmosphere", "other",
)
# Roles that are allowed to sit in the low end / centre and are exempt from scale checks.
UNPITCHED_ROLES = {"drums", "percussion", "fx"}

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    slug = _SLUG_RE.sub("-", text.lower()).strip("-")
    if not slug:
        raise ValueError("name must contain at least one letter or digit")
    return slug[:64]


class Project:
    def __init__(self, data: dict[str, Any]):
        self.data = data

    # ----- construction / persistence -------------------------------------------------
    @classmethod
    def new(cls, name: str, bpm: float, key: str, scale: str, time_signature: str = "4/4",
            chords: list[str] | None = None, chord_bars: int = 1,
            sections: list[dict[str, Any]] | None = None, loop: bool = False,
            genre: str = "", mood: str = "") -> "Project":
        if not 20 <= bpm <= 999:
            raise ValueError("bpm must be between 20 and 999")
        theory.scale_pitch_classes(key, scale)  # validates both
        num, den = _parse_ts(time_signature)
        for c in chords or []:
            theory.parse_chord(c)
        if chord_bars < 1:
            raise ValueError("chord_bars must be at least 1")
        data = {
            "name": name, "slug": slugify(name), "genre": genre, "mood": mood,
            "bpm": float(bpm), "ts_num": num, "ts_den": den, "key": key, "scale": scale,
            "chords": list(chords or []), "chord_bars": chord_bars, "loop": loop,
            "sections": [], "agents": {}, "patterns": {}, "arrangement": [],
        }
        proj = cls(data)
        if sections:
            proj.set_sections(sections)
        return proj

    @property
    def dir(self) -> Path:
        return paths.projects_root() / self.data["slug"]

    @property
    def file(self) -> Path:
        return self.dir / "session.json"

    def save(self) -> Path:
        self.dir.mkdir(parents=True, exist_ok=True)
        self.file.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
        (paths.projects_root() / ".active").write_text(self.data["slug"], encoding="utf-8")
        return self.file

    @classmethod
    def load(cls, name: str | None = None) -> "Project":
        root = paths.projects_root()
        if name is None:
            marker = root / ".active"
            if not marker.exists():
                raise LookupError("no active project: call create_project first")
            slug = marker.read_text(encoding="utf-8").strip()
        else:
            slug = slugify(name)
        file = root / slug / "session.json"
        if not file.exists():
            raise LookupError(f"project {slug!r} not found in {root}")
        proj = cls(json.loads(file.read_text(encoding="utf-8")))
        (root / ".active").write_text(slug, encoding="utf-8")
        return proj

    @staticmethod
    def list_all() -> list[str]:
        root = paths.projects_root()
        if not root.exists():
            return []
        return sorted(p.parent.name for p in root.glob("*/session.json"))

    # ----- timing ----------------------------------------------------------------------
    @property
    def beats_per_bar(self) -> float:
        return self.data["ts_num"] * 4 / self.data["ts_den"]

    def song_bars(self) -> int:
        end = 0.0
        for s in self.data["sections"]:
            end = max(end, s["start_bar"] - 1 + s["bars"])
        for pl in self.data["arrangement"]:
            pat = self.data["patterns"].get(pl["pattern"])
            if pat:
                end = max(end, pl["start_bar"] - 1 + pat["length_beats"] * pl["repeat"] / self.beats_per_bar)
        return int(-(-end // 1))

    # ----- edits -----------------------------------------------------------------------
    def set_sections(self, sections: list[dict[str, Any]]) -> None:
        clean = []
        for s in sections:
            name = str(s.get("name", "")).strip()
            start, bars = int(s.get("start_bar", 0)), int(s.get("bars", 0))
            if not name or start < 1 or bars < 1:
                raise ValueError(f"section needs name, start_bar >= 1 and bars >= 1: {s}")
            clean.append({"name": name, "start_bar": start, "bars": bars})
        clean.sort(key=lambda s: s["start_bar"])
        self.data["sections"] = clean

    def upsert_agent(self, agent_id: str, name: str, role: str, instrument: str,
                     channel: int, mixer_track: int, low_note: int | str, high_note: int | str,
                     pan: float = 0.0, volume_db: float = 0.0, brief: str = "") -> dict[str, Any]:
        if role not in ROLES:
            raise ValueError(f"unknown role {role!r}; choose one of: {', '.join(ROLES)}")
        low, high = theory.parse_pitch(low_note), theory.parse_pitch(high_note)
        if low > high:
            raise ValueError("low_note must not be above high_note")
        if channel < 0 or mixer_track < 0:
            raise ValueError("channel and mixer_track must be >= 0")
        if not -1 <= pan <= 1:
            raise ValueError("pan must be between -1 (left) and 1 (right)")
        aid = slugify(agent_id)
        for other_id, other in self.data["agents"].items():
            if other_id == aid:
                continue
            if other["channel"] == channel:
                raise ValueError(f"channel {channel} already belongs to agent {other_id!r} (channel isolation)")
            if mixer_track and other["mixer_track"] == mixer_track:
                raise ValueError(f"mixer track {mixer_track} already belongs to agent {other_id!r} (channel isolation)")
        agent = {"id": aid, "name": name, "role": role, "instrument": instrument,
                 "channel": channel, "mixer_track": mixer_track, "low": low, "high": high,
                 "pan": pan, "volume_db": volume_db, "brief": brief}
        self.data["agents"][aid] = agent
        return agent

    def upsert_pattern(self, pattern_id: str, agent_id: str, name: str, length_beats: float,
                       notes: list[dict[str, Any]], humanize: float = 0.0) -> dict[str, Any]:
        aid = slugify(agent_id)
        if aid not in self.data["agents"]:
            raise LookupError(f"unknown agent {agent_id!r}: register it first")
        if length_beats <= 0:
            raise ValueError("length_beats must be positive")
        if not 0 <= humanize <= 1:
            raise ValueError("humanize must be between 0 and 1")
        pid = slugify(pattern_id)
        existing = self.data["patterns"].get(pid)
        if existing and existing["agent"] != aid:
            raise ValueError(f"pattern {pid!r} belongs to agent {existing['agent']!r} (channel isolation)")
        clean = []
        for i, n in enumerate(notes):
            try:
                pitch = theory.parse_pitch(n["pitch"])
                start, length = float(n["start"]), float(n["length"])
                vel = int(n.get("velocity", 100))
            except KeyError as exc:
                raise ValueError(f"note {i} is missing {exc.args[0]!r} (needs pitch, start, length)") from None
            if start < 0 or length <= 0:
                raise ValueError(f"note {i}: start must be >= 0 and length > 0")
            if start >= length_beats:
                raise ValueError(f"note {i} starts at beat {start}, past the pattern end ({length_beats})")
            if not 1 <= vel <= 127:
                raise ValueError(f"note {i}: velocity must be 1-127")
            clean.append({"pitch": pitch, "start": start, "length": length, "velocity": vel})
        clean.sort(key=lambda n: (n["start"], n["pitch"]))
        if humanize:
            clean = humanize_notes(clean, humanize, self.beats_per_bar, seed=pid)
        fl_pattern = existing["fl_pattern"] if existing else self._next_fl_pattern()
        pattern = {"id": pid, "name": name, "agent": aid, "fl_pattern": fl_pattern,
                   "length_beats": float(length_beats), "notes": clean}
        self.data["patterns"][pid] = pattern
        return pattern

    def _next_fl_pattern(self) -> int:
        used = {p["fl_pattern"] for p in self.data["patterns"].values()}
        n = 1
        while n in used:
            n += 1
        return n

    def set_arrangement(self, placements: list[dict[str, Any]]) -> None:
        clean = []
        for pl in placements:
            pid = slugify(str(pl.get("pattern", "")))
            if pid not in self.data["patterns"]:
                raise LookupError(f"unknown pattern {pl.get('pattern')!r} in arrangement")
            start, repeat = int(pl.get("start_bar", 0)), int(pl.get("repeat", 1))
            if start < 1 or repeat < 1:
                raise ValueError(f"placement needs start_bar >= 1 and repeat >= 1: {pl}")
            clean.append({"pattern": pid, "start_bar": start, "repeat": repeat})
        clean.sort(key=lambda p: (p["start_bar"], p["pattern"]))
        self.data["arrangement"] = clean

    # ----- views -----------------------------------------------------------------------
    def summary(self) -> dict[str, Any]:
        d = self.data
        return {
            "name": d["name"], "genre": d["genre"], "mood": d["mood"], "bpm": d["bpm"],
            "time_signature": f"{d['ts_num']}/{d['ts_den']}", "key": d["key"], "scale": d["scale"],
            "chords": d["chords"], "chord_bars": d["chord_bars"], "loop": d["loop"],
            "sections": d["sections"], "song_bars": self.song_bars(),
            "agents": [
                {k: a[k] for k in ("id", "name", "role", "instrument", "channel", "mixer_track", "pan", "volume_db")}
                | {"range": f"{theory.note_name(a['low'])}-{theory.note_name(a['high'])}"}
                for a in d["agents"].values()
            ],
            "patterns": [
                {"id": p["id"], "name": p["name"], "agent": p["agent"], "fl_pattern": p["fl_pattern"],
                 "length_beats": p["length_beats"], "notes": len(p["notes"])}
                for p in sorted(d["patterns"].values(), key=lambda p: p["fl_pattern"])
            ],
            "arrangement": d["arrangement"],
            "session_file": str(self.file),
        }


def humanize_notes(notes: list[dict[str, Any]], amount: float, beats_per_bar: float,
                   seed: str) -> list[dict[str, Any]]:
    """Deterministic humanization: metric accents (only if velocities are flat) plus small jitter."""
    flat = len({n["velocity"] for n in notes}) <= 1
    out = []
    for i, n in enumerate(notes):
        h = hashlib.sha256(f"{seed}:{i}".encode()).digest()
        r_vel = h[0] / 255 * 2 - 1
        r_time = h[1] / 255 * 2 - 1
        vel = n["velocity"]
        if flat:
            pos = n["start"] % beats_per_bar
            if abs(pos) < 1e-6:
                vel += 10
            elif abs(n["start"] - round(n["start"])) < 1e-6:
                vel += 2
            elif abs(n["start"] * 2 - round(n["start"] * 2)) < 1e-6:
                vel -= 8
            else:
                vel -= 16
        vel = round(vel + r_vel * 10 * amount)
        start = n["start"]
        if start > 0:
            start = max(0.0, start + r_time * 0.02 * amount)
        out.append({**n, "start": round(start, 4), "velocity": max(1, min(127, vel))})
    return out


def _parse_ts(ts: str) -> tuple[int, int]:
    m = re.match(r"^\s*(\d{1,2})\s*/\s*(\d{1,2})\s*$", ts)
    if not m:
        raise ValueError("time_signature must look like '4/4', '6/8' or '7/8'")
    num, den = int(m.group(1)), int(m.group(2))
    if num < 1 or den not in (1, 2, 4, 8, 16, 32):
        raise ValueError("invalid time signature")
    return num, den
