# Agent ID cards

Every musician agent is one `register_agent` call. Log the card when you cast the agent:

```
[MAESTRO] -> Cast: SOPRANO CHOIR
  Instrument : FLEX - Choir preset (fallback: Sytrus "Vox" pad)
  Band       : C4-A5
  FL         : channel 5 | patterns choir-verse, choir-chorus | mixer 6
  Brief      : sustained "ah" pads on chord tones, octave lift in the final chorus
```

## Frequency and octave bands (scientific pitch, C4 = MIDI 60)
| Layer | Band | Typical agents |
|---|---|---|
| Sub / bass | C1-C3 | 808, sub, synth bass, double bass, tuba, bass guitar |
| Low-mid harmony | C2-C4 | Cello, left-hand piano, low pads, rhythm guitar, trombone |
| Mid harmony | C3-C5 | Pads, chords, viola, horns, choir alto and tenor |
| Lead / melody | C4-C6 | Lead synth, vocal line, violin, flute, trumpet, soprano |
| Air / sparkle | C6-C8 | Bells, glockenspiel, high arps, piccolo |
| Unpitched | GM drum map | Drums, percussion, FX (exempt from scale checks) |

Melodic agents that play together should sit at least 5 semitones apart in their median
register. Otherwise the critic reports `register_masking`.

## Channel and mixer plan
- Register agents in Channel Rack order: channel 0, 1, 2 and so on. The exported MIDI writes its
  tracks in that order, so importing it into an empty FL project lines the channels up with the agents.
- Mixer tracks: one insert per agent, starting at 1. Put buses at 20 and above (drum bus,
  music bus, FX returns) and route agents to them with `fl_configure_mixer_track`'s `route_to`.

## Starting rosters
**Trap / drill:** Drums (FPC), 808 (FLEX/3xOsc), Melody (FL Keys or a FLEX bell), Counter (pluck), FX/Atmos.

**Epic orchestral boss:** Taiko/percussion (FPC/DirectWave), Low strings ostinato (FLEX Strings),
High strings (FLEX Strings), Brass (FLEX Brass), Choir (FLEX Choir), Sub hits (3xOsc), FX risers (Harmor).

**Synthwave:** Drums (FPC, gated snare), Bass (3xOsc saw octave), Pads (Sytrus), Arp (3xOsc),
Lead (Harmor/Sytrus), FX (noise risers).

**Lo-fi / cozy:** Drums (FPC swung), Keys (FL Keys), Upright bass (FLEX), Melody (FLEX flute or
guitar), Vinyl/atmos (DirectWave).

**Jazz combo:** Drums (ride/brush), Walking bass, Piano comping, Horn lead, Counter line.

**Opera / choir:** Soprano, Alto, Tenor, Bass choir agents, String bed, Harp/piano,
Timpani. Four separate agents keep the voices isolated and easy to balance.

## Revision orders
When the critic finds an issue, address it to the agent that owns the pattern and have that
agent rewrite only that pattern:
```
[CRITIC] -> bass-chorus bar 2: flams with the kick by 0.06 beats -> revision to 808 BASS.
[808 BASS] -> bass-chorus rewritten: onsets locked to the kick, glide moved to beat 4.5.
```
