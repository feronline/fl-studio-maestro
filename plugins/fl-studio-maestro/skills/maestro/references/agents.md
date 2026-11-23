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

## Rendered sounds (`gm_program`, General MIDI, 0-based)
The MP3 is rendered with the GeneralUser GS SoundFont. If you leave `gm_program` out, the server
picks a sound from the role and the instrument text. Set it explicitly when you want something
specific.

| Family | Programs |
|---|---|
| Piano and keys | 0 grand, 4 electric piano (Rhodes), 6 harpsichord, 8 celesta, 11 vibraphone, 12 marimba, 14 tubular bells, 19 church organ |
| Guitar | 24 nylon, 25 steel, 27 clean electric, 29 overdrive, 30 distortion |
| Bass | 32 upright, 33 finger, 34 pick, 36 slap, 38 synth bass 1, 39 synth bass 2 |
| Strings | 40 violin, 41 viola, 42 cello, 43 contrabass, 45 pizzicato, 46 harp, 47 timpani, 48 string ensemble, 49 slow strings, 50 synth strings |
| Choir and voice | 52 choir aahs, 53 voice oohs, 54 synth voice, 91 choir pad |
| Brass | 56 trumpet, 57 trombone, 58 tuba, 60 French horn, 61 brass section, 62 synth brass |
| Woodwinds | 65 alto sax, 68 oboe, 70 bassoon, 71 clarinet, 72 piccolo, 73 flute, 75 pan flute, 77 shakuhachi |
| Synth leads | 80 square, 81 saw, 84 charang (pluck-like), 87 bass+lead |
| Synth pads | 88 new age, 89 warm, 90 polysynth, 92 bowed, 94 halo, 95 sweep |
| FX | 96 rain, 98 crystal, 99 atmosphere, 100 brightness, 101 goblins, 102 echoes, 103 sci-fi, 122 seashore (noise) |
| World | 104 sitar, 105 banjo (oud stand-in), 106 shamisen (saz stand-in), 107 koto (kanun stand-in), 108 kalimba, 109 bagpipe, 110 fiddle, 111 shanai (zurna stand-in), 116 taiko |
| Drum kits (drums/percussion roles) | 0 standard, 8 room, 16 power, 24 electronic, 25 TR-808, 32 jazz, 40 brush, 48 orchestral |
