"""The Theory & QA Critic: deterministic checks over patterns and the arrangement."""

from __future__ import annotations

from collections import defaultdict
from statistics import median
from typing import Any

from . import theory
from .project import UNPITCHED_ROLES, Project

MELODIC_ROLES = {"lead", "vocal", "choir", "counter_melody", "arp", "strings", "brass", "woodwinds"}
KICK_PITCHES = {35, 36}


def _where(proj: Project, beat: float) -> str:
    bpb = proj.beats_per_bar
    bar = int(beat // bpb) + 1
    return f"bar {bar} beat {beat - (bar - 1) * bpb + 1:g}"


def _timeline(proj: Project) -> list[dict[str, Any]]:
    """Every note of the arrangement at its absolute beat."""
    d, bpb = proj.data, proj.beats_per_bar
    events = []
    for pl in d["arrangement"]:
        pat = d["patterns"][pl["pattern"]]
        for rep in range(pl["repeat"]):
            offset = (pl["start_bar"] - 1) * bpb + rep * pat["length_beats"]
            for n in pat["notes"]:
                events.append({**n, "abs": offset + n["start"], "agent": pat["agent"], "pattern": pat["id"]})
    return events


def review(proj: Project, pattern_ids: list[str] | None = None) -> dict[str, Any]:
    d = proj.data
    agents, patterns = d["agents"], d["patterns"]
    selected = [patterns[p] for p in (pattern_ids or patterns) if p in patterns]
    missing = [p for p in (pattern_ids or []) if p not in patterns]
    issues: list[dict[str, Any]] = []

    def add(severity, check, message, fix, agent=None, pattern=None, where=None):
        issues.append({k: v for k, v in {
            "severity": severity, "check": check, "agent": agent, "pattern": pattern,
            "where": where, "message": message, "fix": fix}.items() if v is not None})

    for p in missing:
        add("error", "unknown_pattern", f"pattern {p!r} does not exist", "check get_project for pattern ids")

    scale_pcs = theory.scale_pitch_classes(d["key"], d["scale"])
    chords = [theory.parse_chord(c) for c in d["chords"]]

    # ---- per-pattern checks ---------------------------------------------------------
    for pat in selected:
        agent = agents[pat["agent"]]
        pitched = agent["role"] not in UNPITCHED_ROLES
        notes = pat["notes"]
        if not notes:
            add("warning", "empty_pattern", "pattern has no notes", "write notes or remove it", agent["id"], pat["id"])
            continue
        if pitched:
            bad = [n for n in notes if n["pitch"] % 12 not in scale_pcs]
            for n in bad[:8]:
                add("warning", "out_of_scale",
                    f"{theory.note_name(n['pitch'])} is outside {d['key']} {d['scale']}",
                    "move it to a scale tone, or keep it only if it is a deliberate chromatic passing/tension note",
                    agent["id"], pat["id"], _where(proj, n["start"]))
            if len(bad) > 8:
                add("warning", "out_of_scale", f"{len(bad) - 8} more out-of-scale notes", "see above", agent["id"], pat["id"])
            out = [n for n in notes if not agent["low"] <= n["pitch"] <= agent["high"]]
            if out:
                add("warning", "out_of_range",
                    f"{len(out)} note(s) outside the agent's band "
                    f"{theory.note_name(agent['low'])}-{theory.note_name(agent['high'])}, e.g. {theory.note_name(out[0]['pitch'])}",
                    "transpose by an octave or widen the band if no other agent lives there",
                    agent["id"], pat["id"], _where(proj, out[0]["start"]))
        if len(notes) >= 4 and len({n["velocity"] for n in notes}) == 1:
            add("warning", "mechanical_velocity",
                f"all {len(notes)} notes have velocity {notes[0]['velocity']}",
                "accent downbeats, soften passing and ghost notes (or rewrite with humanize 0.3-0.6)",
                agent["id"], pat["id"])
        if pitched and len(notes) >= 8 and len({n["pitch"] for n in notes}) == 1 and agent["role"] not in ("bass",):
            add("info", "monotony", "the pattern repeats a single pitch", "add movement or a variation", agent["id"], pat["id"])

    # ---- identical variations ---------------------------------------------------------
    sigs = defaultdict(list)
    for pat in selected:
        sig = (pat["agent"], tuple((n["pitch"], round(n["start"], 2), round(n["length"], 2)) for n in pat["notes"]))
        sigs[sig].append(pat["id"])
    for ids in sigs.values():
        if len(ids) > 1:
            add("info", "duplicate_variation", f"patterns {', '.join(ids)} have identical notes",
                "make the variations differ (fills, octave, rhythm) or reuse one pattern")

    # ---- arrangement-level checks -----------------------------------------------------
    events = _timeline(proj)
    if d["arrangement"]:
        in_scope = {p["id"] for p in selected}
        by_agent = defaultdict(list)
        for e in events:
            by_agent[e["agent"]].append(e)

        # Chord conformance for bass on chord changes.
        if chords:
            bpb = proj.beats_per_bar
            span = d["chord_bars"] * bpb
            for e in events:
                agent = agents[e["agent"]]
                if agent["role"] != "bass" or e["pattern"] not in in_scope:
                    continue
                pos = e["abs"] % span
                if pos < 1e-3:
                    root, pcs, bass_pc = chords[int(e["abs"] // span) % len(chords)]
                    if e["pitch"] % 12 not in pcs:
                        add("warning", "chord_clash",
                            f"bass plays {theory.note_name(e['pitch'])} on a chord change to "
                            f"{d['chords'][int(e['abs'] // span) % len(chords)]}",
                            "land on the chord root (or the slash bass) at chord changes",
                            agent["id"], e["pattern"], _where(proj, e["abs"]))

        # Kick / bass flams: onsets close together but not together.
        kicks = sorted(e["abs"] for e in events
                       if agents[e["agent"]]["role"] == "drums"
                       and (e["pitch"] in KICK_PITCHES or "kick" in agents[e["agent"]]["name"].lower()))
        if kicks:
            reported = 0
            for e in events:
                if agents[e["agent"]]["role"] != "bass" or e["pattern"] not in in_scope:
                    continue
                near = min(kicks, key=lambda k: abs(k - e["abs"]))
                if 0.02 < abs(near - e["abs"]) < 0.125:
                    reported += 1
                    if reported <= 5:
                        add("warning", "kick_bass_flam",
                            f"bass onset is {abs(near - e['abs']):.3f} beats off the kick",
                            "align the bass note with the kick or move it clearly off it (sidechain helps)",
                            agents[e["agent"]]["id"], e["pattern"], _where(proj, e["abs"]))

        # Register masking between melodic agents that play at the same time.
        melodic = [a for a in agents.values() if a["role"] in MELODIC_ROLES and by_agent.get(a["id"])]
        for i, a in enumerate(melodic):
            for b in melodic[i + 1:]:
                ea, eb = by_agent[a["id"]], by_agent[b["id"]]
                bars_a = {int(e["abs"] // proj.beats_per_bar) for e in ea}
                bars_b = {int(e["abs"] // proj.beats_per_bar) for e in eb}
                shared = bars_a & bars_b
                if len(shared) < 2:
                    continue
                ma = median(e["pitch"] for e in ea if int(e["abs"] // proj.beats_per_bar) in shared)
                mb = median(e["pitch"] for e in eb if int(e["abs"] // proj.beats_per_bar) in shared)
                if abs(ma - mb) <= 4:
                    add("warning", "register_masking",
                        f"{a['id']} and {b['id']} play in the same register "
                        f"(around {theory.note_name(int(ma))}) in {len(shared)} shared bars",
                        "move one of them an octave, or thin one out where they overlap")

        # Monotony: one pattern carries an agent through most of a multi-section song.
        song = proj.song_bars()
        if len(d["sections"]) >= 3 and song:
            used = defaultdict(set)
            bars = defaultdict(float)
            for pl in d["arrangement"]:
                pat = d["patterns"][pl["pattern"]]
                used[pat["agent"]].add(pat["id"])
                bars[pat["agent"]] += pat["length_beats"] * pl["repeat"] / proj.beats_per_bar
            for aid, pats in used.items():
                if len(pats) == 1 and bars[aid] > song * 0.5:
                    add("info", "monotony", f"{aid} uses one pattern for {bars[aid]:g} of {song} bars",
                        "write 2-3 variations (verse/chorus/fill) and alternate them", aid)

        # Silent bars inside the song.
        if song:
            sounding = {int(e["abs"] // proj.beats_per_bar) for e in events}
            silent = [b + 1 for b in range(song) if b not in sounding]
            if silent:
                add("info", "silent_bars", f"{len(silent)} silent bar(s), first at bar {silent[0]}",
                    "fine for a deliberate break; otherwise place a pattern there")

        # Loop seam.
        if d["loop"] and song:
            ends = [pl["start_bar"] - 1 + d["patterns"][pl["pattern"]]["length_beats"] * pl["repeat"] / proj.beats_per_bar
                    for pl in d["arrangement"]]
            if abs(max(ends) - round(max(ends))) > 1e-6:
                add("warning", "loop_seam", f"the arrangement ends mid-bar ({max(ends):g} bars)",
                    "end every layer on a bar line so the loop wraps seamlessly")
            tails = [e for e in events if e["abs"] + e["length"] > song * proj.beats_per_bar + 1e-6]
            if tails:
                add("info", "loop_seam", f"{len(tails)} note(s) ring past the loop point",
                    "shorten them or accept the overlap into bar 1")
    elif selected:
        add("info", "no_arrangement", "no arrangement yet, so cross-agent checks were skipped",
            "call arrange to place patterns, then review again")

    # ---- mix sanity -------------------------------------------------------------------
    for a in agents.values():
        if a["volume_db"] > 0:
            add("warning", "gain_staging", f"{a['id']} is set to +{a['volume_db']} dB",
                "keep channels at or below 0 dB and leave headroom on the master", a["id"])

    counts = defaultdict(int)
    for i in issues:
        counts[i["severity"]] += 1
    return {
        "passed": counts["error"] == 0 and counts["warning"] == 0,
        "counts": {"error": counts["error"], "warning": counts["warning"], "info": counts["info"]},
        "patterns_reviewed": [p["id"] for p in selected],
        "issues": issues,
    }
