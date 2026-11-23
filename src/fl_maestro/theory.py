"""Music theory helpers: note names, scales, chords.

Pitch numbers are MIDI numbers in scientific pitch notation (C4 = 60).
FL Studio's piano roll labels MIDI 60 as "C5"; see ``fl_note_name``.
"""

from __future__ import annotations

import re

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

# Interval sets (semitones above the tonic).
SCALES: dict[str, tuple[int, ...]] = {
    "major": (0, 2, 4, 5, 7, 9, 11),
    "natural_minor": (0, 2, 3, 5, 7, 8, 10),
    "harmonic_minor": (0, 2, 3, 5, 7, 8, 11),
    "melodic_minor": (0, 2, 3, 5, 7, 9, 11),
    "dorian": (0, 2, 3, 5, 7, 9, 10),
    "phrygian": (0, 1, 3, 5, 7, 8, 10),
    "lydian": (0, 2, 4, 6, 7, 9, 11),
    "mixolydian": (0, 2, 4, 5, 7, 9, 10),
    "locrian": (0, 1, 3, 5, 6, 8, 10),
    "phrygian_dominant": (0, 1, 4, 5, 7, 8, 10),  # Hijaz flavour
    "double_harmonic": (0, 1, 4, 5, 7, 8, 11),
    "hungarian_minor": (0, 2, 3, 6, 7, 8, 11),
    "major_pentatonic": (0, 2, 4, 7, 9),
    "minor_pentatonic": (0, 3, 5, 7, 10),
    "blues": (0, 3, 5, 6, 7, 10),
    "hirajoshi": (0, 2, 3, 7, 8),
    "in_sen": (0, 1, 5, 7, 10),
    "whole_tone": (0, 2, 4, 6, 8, 10),
    "chromatic": tuple(range(12)),
}

CHORD_QUALITIES: dict[str, tuple[int, ...]] = {
    "": (0, 4, 7),
    "maj": (0, 4, 7),
    "m": (0, 3, 7),
    "min": (0, 3, 7),
    "5": (0, 7),
    "dim": (0, 3, 6),
    "aug": (0, 4, 8),
    "sus2": (0, 2, 7),
    "sus4": (0, 5, 7),
    "6": (0, 4, 7, 9),
    "m6": (0, 3, 7, 9),
    "7": (0, 4, 7, 10),
    "maj7": (0, 4, 7, 11),
    "m7": (0, 3, 7, 10),
    "mmaj7": (0, 3, 7, 11),
    "m7b5": (0, 3, 6, 10),
    "dim7": (0, 3, 6, 9),
    "add9": (0, 4, 7, 2),
    "madd9": (0, 3, 7, 2),
    "9": (0, 4, 7, 10, 2),
    "m9": (0, 3, 7, 10, 2),
    "maj9": (0, 4, 7, 11, 2),
}

_NOTE_RE = re.compile(r"^\s*([A-Ga-g])([#b]*)(-?\d+)\s*$")
_CHORD_RE = re.compile(r"^\s*([A-Ga-g])([#b]?)([^/\s]*)(?:/([A-Ga-g][#b]?))?\s*$")


def pitch_class(name: str) -> int:
    """'C#' -> 1, 'Bb' -> 10."""
    name = name.strip()
    pc = _PC[name[0].upper()]
    for ch in name[1:]:
        pc += 1 if ch == "#" else -1 if ch == "b" else 0
    return pc % 12


def parse_pitch(value: int | str) -> int:
    """Accept a MIDI number or a note name like 'D#3' / 'Bb4' (C4 = 60)."""
    if isinstance(value, bool):
        raise ValueError(f"invalid pitch: {value!r}")
    if isinstance(value, int):
        number = value
    elif isinstance(value, float) and value.is_integer():
        number = int(value)
    elif isinstance(value, str) and value.strip().lstrip("-").isdigit():
        number = int(value)
    else:
        m = _NOTE_RE.match(str(value))
        if not m:
            raise ValueError(f"invalid pitch {value!r}: use a MIDI number or a name like 'C4' or 'F#2'")
        letter, acc, octave = m.groups()
        semis = _PC[letter.upper()] + acc.count("#") - acc.count("b")
        number = (int(octave) + 1) * 12 + semis
    if not 0 <= number <= 127:
        raise ValueError(f"pitch {value!r} is outside MIDI range 0-127")
    return number


def note_name(number: int) -> str:
    """60 -> 'C4' (scientific pitch notation)."""
    return f"{NOTE_NAMES[number % 12]}{number // 12 - 1}"


def fl_note_name(number: int) -> str:
    """60 -> 'C5' (how FL Studio's piano roll labels it)."""
    return f"{NOTE_NAMES[number % 12]}{number // 12}"


def scale_pitch_classes(key: str, scale: str) -> set[int]:
    if scale not in SCALES:
        raise ValueError(f"unknown scale {scale!r}; choose one of: {', '.join(SCALES)}")
    root = pitch_class(key)
    return {(root + i) % 12 for i in SCALES[scale]}


def parse_chord(symbol: str) -> tuple[int, set[int], int]:
    """'Dm7' -> (root_pc, chord pitch classes, bass_pc). Slash chords supported: 'C/E'."""
    m = _CHORD_RE.match(symbol)
    if not m:
        raise ValueError(f"invalid chord symbol {symbol!r}")
    letter, acc, quality, bass = m.groups()
    root = pitch_class(letter + acc)
    q = quality.replace("M7", "maj7").replace("-", "m")
    if q not in CHORD_QUALITIES:
        raise ValueError(f"unknown chord quality {quality!r} in {symbol!r}; known: {', '.join(k or 'major' for k in CHORD_QUALITIES)}")
    pcs = {(root + i) % 12 for i in CHORD_QUALITIES[q]}
    bass_pc = pitch_class(bass) if bass else root
    pcs.add(bass_pc)
    return root, pcs, bass_pc
