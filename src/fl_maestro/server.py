"""fl-studio-maestro MCP server: plan, compose, critique, arrange and drive FL Studio."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from . import __version__, critic, export, theory
from .bridge import Bridge
from .project import ROLES, Project

INSTRUCTIONS = """\
FL Studio Maestro: a multi-agent music production studio for FL Studio.
Workflow: fl_status -> create_project (the master plan) -> register_agent for every musician
-> write_pattern (2-3 variations per agent, humanized) -> review_project and fix every warning
-> arrange -> export_project (MIDI for File > Import, plus piano roll scripts) -> fl_apply_session
-> mix with fl_configure_mixer_track / fl_set_plugin_param -> fl_save_project.
Pitches use scientific notation (C4 = MIDI 60); FL Studio labels MIDI 60 as C5.
Times are in quarter-note beats from the start of the pattern.
"""

mcp = MCPServer("fl-studio-maestro", instructions=INSTRUCTIONS, version=__version__)
_bridge = Bridge()

READ = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
REPLACE = ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=False)
LIVE = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False)

Scale = Literal[tuple(theory.SCALES)]  # type: ignore[valid-type]
Role = Literal[ROLES]  # type: ignore[valid-type]


class Section(BaseModel):
    name: Annotated[str, Field(description="Section name, e.g. 'Intro', 'Verse A', 'Drop'.")]
    start_bar: Annotated[int, Field(ge=1, description="First bar of the section (1-based).")]
    bars: Annotated[int, Field(ge=1, description="Length of the section in bars.")]


class NoteIn(BaseModel):
    pitch: Annotated[int | str, Field(description="MIDI number (0-127) or note name like 'D3', 'F#4', 'Bb2' (C4 = 60). Drums: GM numbers, kick 36, snare 38, closed hat 42.")]
    start: Annotated[float, Field(ge=0, description="Start in quarter-note beats from the pattern start (0 = first beat, 0.5 = the 'and').")]
    length: Annotated[float, Field(gt=0, description="Duration in quarter-note beats (0.25 = a 16th note).")]
    velocity: Annotated[int, Field(ge=1, le=127, description="1-127. Accent downbeats (100-120), soften passing notes (70-90) and ghost notes (30-55).")] = 100


class Placement(BaseModel):
    pattern: Annotated[str, Field(description="Pattern id from write_pattern.")]
    start_bar: Annotated[int, Field(ge=1, description="Bar where the clip starts (1-based).")]
    repeat: Annotated[int, Field(ge=1, description="How many times the pattern plays back to back.")] = 1


def _project() -> Project:
    return Project.load()


# =============================================================== planning & composition
@mcp.tool(annotations=REPLACE)
def create_project(
    name: Annotated[str, Field(description="Project title, e.g. 'Neon Boss Fight'. Also used as the session folder name.")],
    bpm: Annotated[float, Field(ge=20, le=999, description="Tempo in beats per minute.")],
    key: Annotated[str, Field(description="Tonic, e.g. 'D', 'F#', 'Bb'.")],
    scale: Annotated[Scale, Field(description="Scale or mode of the piece.")],
    time_signature: Annotated[str, Field(description="Meter such as '4/4', '3/4', '6/8' or '7/8'.")] = "4/4",
    chords: Annotated[list[str] | None, Field(description="Chord progression symbols in order, e.g. ['Dm', 'Bb', 'F', 'C'] or ['Am7', 'D9', 'Gmaj7']. Cycles through the song.")] = None,
    chord_bars: Annotated[int, Field(ge=1, description="Bars each chord lasts.")] = 1,
    sections: Annotated[list[Section] | None, Field(description="Bar map of the song form, e.g. Intro 1-8, Verse 9-24.")] = None,
    genre: Annotated[str, Field(description="Genre or blend, e.g. 'synthwave boss fight'.")] = "",
    mood: Annotated[str, Field(description="Target emotion and use, e.g. 'relentless, loopable'.")] = "",
    loop: Annotated[bool, Field(description="True for game loops: the critic then checks that the end wraps seamlessly into bar 1.")] = False,
    overwrite: Annotated[bool, Field(description="Replace an existing project with the same name. Its agents and patterns are lost.")] = False,
) -> dict[str, Any]:
    """Create the master production plan (tempo, key, meter, chords, song form) and make it the active project.

    Every other composition tool works on the active project. Returns the plan summary.
    """
    proj = Project.new(name, bpm, key, scale, time_signature, chords, chord_bars,
                       [s.model_dump() for s in sections or []], loop, genre, mood)
    if proj.file.exists() and not overwrite:
        raise ValueError(f"project {proj.data['slug']!r} already exists: pass overwrite=true, or use get_project to open it")
    proj.save()
    return proj.summary()


@mcp.tool(annotations=READ)
def get_project(
    name: Annotated[str | None, Field(description="Project to open and make active. Omit for the active project.")] = None,
) -> dict[str, Any]:
    """Show the active (or named) project: plan, agent roster with FL channel/mixer map, patterns and arrangement.

    Also lists every saved project. Use it to resume work after a restart.
    """
    try:
        proj = Project.load(name)
    except LookupError as exc:
        return {"active": None, "message": str(exc), "projects": Project.list_all()}
    return proj.summary() | {"projects": Project.list_all()}


@mcp.tool(annotations=WRITE)
def register_agent(
    agent_id: Annotated[str, Field(description="Short id, e.g. 'bass', 'soprano-choir', 'lead-synth'.")],
    name: Annotated[str, Field(description="Display name, used for the FL channel and mixer track, e.g. '808 Bass'.")],
    role: Annotated[Role, Field(description="Musical role; drums, percussion and fx are exempt from scale checks.")],
    instrument: Annotated[str, Field(description="Instrument or plugin, preferably FL stock: FLEX, Sytrus, Harmor, 3xOsc, FL Keys, FPC, Sakura, DirectWave.")],
    channel: Annotated[int, Field(ge=0, description="Channel Rack index (0-based) this agent owns exclusively.")],
    mixer_track: Annotated[int, Field(ge=0, description="Mixer insert track this agent owns exclusively (1-125; 0 = master).")],
    low_note: Annotated[int | str, Field(description="Lowest note of the agent's frequency band, e.g. 'C2' or 36.")],
    high_note: Annotated[int | str, Field(description="Highest note of the band, e.g. 'C3' or 48.")],
    pan: Annotated[float, Field(ge=-1, le=1, description="Stereo position: -1 left, 0 centre, 1 right.")] = 0.0,
    volume_db: Annotated[float, Field(le=6, description="Target mixer level in dB (keep at or below 0).")] = 0.0,
    brief: Annotated[str, Field(description="Musical brief: what the agent plays (ostinato, pad, arpeggio, counter-melody...).")] = "",
) -> dict[str, Any]:
    """Create or update a musician agent's ID card: role, instrument, owned FL channel and mixer track, and note band.

    Channels and mixer tracks are exclusive: registering two agents on the same one fails.
    """
    proj = _project()
    agent = proj.upsert_agent(agent_id, name, role, instrument, channel, mixer_track,
                              low_note, high_note, pan, volume_db, brief)
    proj.save()
    return agent | {"range": f"{theory.note_name(agent['low'])}-{theory.note_name(agent['high'])}",
                    "fl_range": f"{theory.fl_note_name(agent['low'])}-{theory.fl_note_name(agent['high'])}"}


@mcp.tool(annotations=WRITE)
def write_pattern(
    pattern_id: Annotated[str, Field(description="Id such as 'bass-verse' or 'drums-chorus-fill'. Rewriting an id replaces its notes.")],
    agent_id: Annotated[str, Field(description="The agent that owns the pattern.")],
    name: Annotated[str, Field(description="Pattern name shown in FL Studio, e.g. 'Bass - Verse'.")],
    length_beats: Annotated[float, Field(gt=0, description="Pattern length in quarter-note beats (4 bars of 4/4 = 16).")],
    notes: Annotated[list[NoteIn], Field(description="The notes of the pattern.")],
    humanize: Annotated[float, Field(ge=0, le=1, description="0 keeps notes exact. 0.2-0.6 adds deterministic velocity/timing feel; flat velocities also get metric accents.")] = 0.0,
) -> dict[str, Any]:
    """Write (or rewrite) one agent's MIDI pattern in the active project and assign it an FL pattern number.

    Returns the stored pattern with its FL pattern number and a note summary.
    """
    proj = _project()
    pat = proj.upsert_pattern(pattern_id, agent_id, name, length_beats,
                              [n.model_dump() for n in notes], humanize)
    proj.save()
    pitches = [n["pitch"] for n in pat["notes"]]
    vels = [n["velocity"] for n in pat["notes"]]
    return {"id": pat["id"], "agent": pat["agent"], "fl_pattern": pat["fl_pattern"],
            "length_beats": pat["length_beats"], "notes": len(pitches),
            "range": f"{theory.note_name(min(pitches))}-{theory.note_name(max(pitches))}" if pitches else None,
            "velocity_range": [min(vels), max(vels)] if vels else None}


@mcp.tool(annotations=READ)
def review_project(
    pattern_ids: Annotated[list[str] | None, Field(description="Patterns to review. Omit to review all of them.")] = None,
) -> dict[str, Any]:
    """Run the Theory & QA Critic: out-of-scale and out-of-band notes, chord clashes, kick/bass flams,
    register masking, flat velocities, duplicate variations, monotony, silent bars, loop seams and gain staging.

    Every issue names the agent and pattern to revise, where it happens, and a fix.
    """
    return critic.review(_project(), pattern_ids)


@mcp.tool(annotations=REPLACE)
def arrange(
    placements: Annotated[list[Placement], Field(description="Every clip of the song. Replaces the previous arrangement.")],
) -> dict[str, Any]:
    """Lay out the song: place patterns on bars of the playlist following the section map.

    Returns the song length in bars and how many clips each section holds.
    """
    proj = _project()
    proj.set_arrangement([p.model_dump() for p in placements])
    proj.save()
    per_section = []
    for s in proj.data["sections"]:
        lo, hi = s["start_bar"], s["start_bar"] + s["bars"]
        per_section.append({"section": s["name"], "clips": sum(1 for p in proj.data["arrangement"] if lo <= p["start_bar"] < hi)})
    return {"song_bars": proj.song_bars(), "clips": len(proj.data["arrangement"]), "sections": per_section}


@mcp.tool(annotations=WRITE)
def export_project(
    format: Annotated[Literal["midi", "pianoroll_scripts", "both"], Field(description="midi: one multi-track .mid of the arrangement (tempo, meter, section markers). pianoroll_scripts: one FL piano roll script per pattern. both: the two.")] = "both",
) -> dict[str, Any]:
    """Export the active project for FL Studio.

    The .mid goes into the project folder: drag it into FL Studio (or File > Import > MIDI file) to create one channel and pattern per agent.
    Piano roll scripts go into FL's 'Piano roll scripts' folder: in a pattern's piano roll, run Scripts > 'Maestro - ...'.
    """
    proj = _project()
    out: dict[str, Any] = {}
    if format in ("midi", "both"):
        out["midi"] = export.export_midi(proj)
    if format in ("pianoroll_scripts", "both"):
        out["pianoroll_scripts"] = export.export_pianoroll_scripts(proj)
    return out


# =============================================================== live FL Studio control
@mcp.tool(annotations=READ)
def fl_status() -> dict[str, Any]:
    """Check the live connection to FL Studio and report its version, tempo, transport and channel/pattern/mixer counts."""
    return _bridge.call("ping")


@mcp.tool(annotations=READ)
def fl_inspect(
    scope: Annotated[Literal["channels", "mixer", "patterns", "playlist"], Field(description="What to list.")],
    limit: Annotated[int, Field(ge=1, le=500, description="Maximum rows.")] = 32,
) -> dict[str, Any]:
    """List the live FL Studio state: channels (plugin, mixer target, volume, pan), mixer tracks (levels, effects per slot), patterns or playlist tracks."""
    return _bridge.call("inspect", scope=scope, limit=limit)


@mcp.tool(annotations=LIVE)
def fl_set_tempo(bpm: Annotated[float, Field(ge=10, le=522, description="Project tempo in BPM.")]) -> dict[str, Any]:
    """Set FL Studio's project tempo."""
    return _bridge.call("set_tempo", bpm=bpm)


@mcp.tool(annotations=LIVE)
def fl_transport(
    action: Annotated[Literal["play", "stop", "record", "rewind", "toggle_song_mode"], Field(description="Transport action. toggle_song_mode switches between pattern and song playback.")],
) -> dict[str, Any]:
    """Control FL Studio's transport: play, stop, record, rewind to the start, or switch pattern/song mode."""
    return _bridge.call("transport", action=action)


@mcp.tool(annotations=LIVE)
def fl_configure_channel(
    index: Annotated[int, Field(ge=0, description="Channel Rack index (0-based).")],
    name: Annotated[str | None, Field(description="New channel name.")] = None,
    color: Annotated[str | None, Field(description="Colour as '#RRGGBB'.")] = None,
    volume_db: Annotated[float | None, Field(le=6, description="Channel volume in dB.")] = None,
    pan: Annotated[float | None, Field(ge=-1, le=1, description="-1 left, 0 centre, 1 right.")] = None,
    mixer_track: Annotated[int | None, Field(ge=0, description="Mixer insert to route the channel to.")] = None,
) -> dict[str, Any]:
    """Rename, colour, level, pan or route one Channel Rack channel. Only the given fields change."""
    return _bridge.call("channel", index=index, name=name, color=color, volume_db=volume_db, pan=pan, mixer_track=mixer_track)


@mcp.tool(annotations=LIVE)
def fl_configure_mixer_track(
    index: Annotated[int, Field(ge=0, description="Mixer track (0 = master).")],
    name: Annotated[str | None, Field(description="New track name.")] = None,
    color: Annotated[str | None, Field(description="Colour as '#RRGGBB'.")] = None,
    volume_db: Annotated[float | None, Field(le=6, description="Fader level in dB (stay at or below 0; leave about -6 dB headroom on the master bus).")] = None,
    pan: Annotated[float | None, Field(ge=-1, le=1, description="-1 left, 0 centre, 1 right.")] = None,
    stereo_separation: Annotated[float | None, Field(ge=-1, le=1, description="-1 merged (mono) to 1 separated (wide).")] = None,
    mute: Annotated[bool | None, Field(description="Mute or unmute the track.")] = None,
    route_to: Annotated[list[int] | None, Field(description="Tracks to send this one to, e.g. [20] for a bus or [0] for the master.")] = None,
    exclusive: Annotated[bool, Field(description="With route_to: remove every other send so the track goes only to route_to.")] = True,
) -> dict[str, Any]:
    """Set a mixer track's name, colour, fader (dB), pan, stereo width, mute and routing. Only the given fields change."""
    return _bridge.call("mixer_track", index=index, name=name, color=color, volume_db=volume_db, pan=pan,
                        stereo_separation=stereo_separation, mute=mute, route_to=route_to, exclusive=exclusive)


@mcp.tool(annotations=LIVE)
def fl_apply_session(
    set_tempo: Annotated[bool, Field(description="Also set FL's tempo to the project BPM.")] = True,
    name_patterns: Annotated[bool, Field(description="Rename FL patterns by their Maestro pattern number. Turn off after a MIDI import whose pattern layout differs (check fl_inspect patterns).")] = True,
) -> dict[str, Any]:
    """Apply the active project to the open FL Studio project in one go: tempo, then for every agent its
    channel name and colour, mixer routing, mixer track name, pan and level; then the name of every pattern.

    Run it after the instruments are on their channels (e.g. after importing the exported MIDI). Missing channels are reported, not created.
    """
    proj = _project()
    report: dict[str, Any] = {"channels": [], "patterns": [], "problems": []}
    if set_tempo:
        report["tempo"] = _bridge.call("set_tempo", bpm=proj.data["bpm"])
    palette = ["#e8524a", "#f0a030", "#e8d84a", "#6cc04a", "#3ab0a0", "#4a8ae8", "#8a5ae8", "#d05ab0"]
    for n, agent in enumerate(proj.data["agents"].values()):
        color = palette[n % len(palette)]
        try:
            _bridge.call("channel", index=agent["channel"], name=agent["name"], color=color,
                         mixer_track=agent["mixer_track"] or None)
            if agent["mixer_track"]:
                _bridge.call("mixer_track", index=agent["mixer_track"], name=agent["name"], color=color,
                             pan=agent["pan"], volume_db=agent["volume_db"])
            report["channels"].append({"agent": agent["id"], "channel": agent["channel"], "mixer_track": agent["mixer_track"]})
        except Exception as exc:
            report["problems"].append({"agent": agent["id"], "error": str(exc)})
    for pat in proj.data["patterns"].values() if name_patterns else []:
        try:
            _bridge.call("pattern", index=pat["fl_pattern"], name=pat["name"])
            report["patterns"].append({"pattern": pat["id"], "fl_pattern": pat["fl_pattern"]})
        except Exception as exc:
            report["problems"].append({"pattern": pat["id"], "error": str(exc)})
    return report


@mcp.tool(annotations=LIVE)
def fl_stage_pattern(
    pattern_id: Annotated[str, Field(description="Pattern id from write_pattern.")],
) -> dict[str, Any]:
    """Write a pattern into FL Studio: refresh its piano roll script, select its FL pattern and the agent's channel, and open the piano roll.

    The user then runs Tools/Scripts > 'Maestro - ...' in the piano roll (FL only lets scripts write notes there) and confirms.
    """
    proj = _project()
    pat = proj.data["patterns"].get(pattern_id)
    if not pat:
        raise LookupError(f"unknown pattern {pattern_id!r}")
    agent = proj.data["agents"][pat["agent"]]
    scripts = export.export_pianoroll_scripts(proj, [pattern_id])
    live = _bridge.call("stage_pattern", pattern=pat["fl_pattern"], channel=agent["channel"], pattern_name=pat["name"])
    return live | {"script": scripts["scripts"][0]["script"],
                   "next_step": f"In the open piano roll run the script '{scripts['scripts'][0]['script'][:-9]}' and press Accept."}


@mcp.tool(annotations=READ)
def fl_plugin_params(
    location: Annotated[Literal["channel", "mixer"], Field(description="channel: the instrument on a channel. mixer: an effect in a mixer slot.")],
    index: Annotated[int, Field(ge=0, description="Channel index, or mixer track index.")],
    slot: Annotated[int, Field(ge=0, le=9, description="Mixer effect slot (0-9); ignored for channels.")] = 0,
    search: Annotated[str | None, Field(description="Only parameters whose name contains this text, e.g. 'cutoff' or 'band 1'.")] = None,
    limit: Annotated[int, Field(ge=1, le=4096, description="Maximum parameters returned.")] = 64,
) -> dict[str, Any]:
    """List a plugin's automatable parameters with their current normalized value (0-1) and display text."""
    return _bridge.call("plugin_params", location=location, index=index, slot=slot, search=search, limit=limit)


@mcp.tool(annotations=LIVE)
def fl_set_plugin_param(
    location: Annotated[Literal["channel", "mixer"], Field(description="channel: the instrument on a channel. mixer: an effect in a mixer slot.")],
    index: Annotated[int, Field(ge=0, description="Channel index, or mixer track index.")],
    param: Annotated[int, Field(ge=0, description="Parameter number from fl_plugin_params.")],
    value: Annotated[float, Field(ge=0, le=1, description="Normalized value 0-1. Check the returned display text and adjust.")],
    slot: Annotated[int, Field(ge=0, le=9, description="Mixer effect slot (0-9); ignored for channels.")] = 0,
) -> dict[str, Any]:
    """Set one plugin parameter (EQ band, reverb mix, limiter ceiling, synth cutoff...) and return its new display value."""
    return _bridge.call("set_plugin_param", location=location, index=index, slot=slot, param=param, value=value)


@mcp.tool(annotations=LIVE)
def fl_save_project() -> dict[str, Any]:
    """Save the open FL Studio project (File > Save). An untitled project opens FL's save dialog."""
    return _bridge.call("save")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
