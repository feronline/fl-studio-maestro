# Genre playbook

These are starting points, not laws. Blend them freely, for example orchestral trap or Balkan drum & bass.
"Scale" values are the `scale` names that `create_project` accepts.

## Game music
| Style | BPM | Meter | Scale | Progression / device | Core cast |
|---|---|---|---|---|---|
| Boss fight | 140-180 | 4/4, 7/8 | harmonic_minor, phrygian | i-VI-VII-i, pedal bass, ostinato | Taiko/drums, staccato strings, brass stabs, choir, distorted bass |
| Main menu | 80-110 | 4/4 | major, lydian | I-V-vi-IV, slow motif | Pad, piano/harp, strings, soft lead |
| Exploration | 90-120 | 4/4, 6/8 | dorian, mixolydian | i-IV (dorian), modal vamps | Plucks, arp, flute/woodwinds, light percussion |
| Psychological horror | 50-80 or free | 4/4 | chromatic, locrian | Clusters, tritones, no resolution | Drones, prepared piano, reversed FX, sub pulses |
| 8-bit / chiptune | 120-160 | 4/4 | major, minor_pentatonic | I-vi-IV-V, fast arps | 3xOsc square/pulse lead, triangle bass, noise drums |
| RPG / fantasy | 70-120 | 3/4, 4/4 | natural_minor, dorian | i-VII-VI-VII, leitmotifs | Strings, horns, harp, celesta, choir |
| Cyberpunk / sci-fi | 100-130 | 4/4 | phrygian, harmonic_minor | i-bII, i-VI | Harmor bass, gated pads, glitch percussion |
| Cozy / lo-fi | 70-90 | 4/4 swing | major, dorian | ii7-V7-Imaj7 | FL Keys, vinyl FX, soft drums, upright bass |

Loops: set `loop=true`, end every layer on a bar line, and avoid long tails across the seam.

## Film and TV
- **Epic orchestral:** 60-100 BPM, natural minor or dorian, i-VI-III-VII. Ostinato strings, horns, choir, taiko. Build with an octave doubling every 8 bars.
- **Drama:** 60-80 BPM, major with borrowed iv. Solo piano or cello and a sustained string bed.
- **Thriller / action:** 120-170 BPM, phrygian or chromatic pulses. Low string spiccato and synth pulse.
- **Minimalist:** 60-100 BPM, additive repeating cells (Glass/Reich style). Change one layer every 4-8 bars.
- **Leitmotif:** a 2-4 bar motif per character, varied by mode, tempo, register and orchestration.

## Stage
- **Opera:** an aria over a cantabile line on sustained strings; recitative with free rhythm over sparse chords; choir in SATB (S C4-A5, A G3-D5, T C3-G4, B E2-C4).
- **Musical theatre:** tempo and key changes between sections, often a half-step lift into the last chorus. Piano-led, with brass hits.
- **Ballet:** 3/4 or 2/4, clear phrases of 8 or 16 bars, strong downbeats for the dancers.

## Pop and modern
- **Pop:** 95-128 BPM, I-V-vi-IV or vi-IV-I-V. Verse 8, pre-chorus 4-8, chorus 8-16.
- **Synth-pop:** 110-125 BPM, 3xOsc/Sytrus arps, gated snare.
- **R&B / soul:** 60-90 BPM, extended chords (maj9, m9, 11), ghost-note drums.
- **Funk / disco:** 100-125 BPM, dorian or mixolydian vamps, sixteenth-note guitar, octave bass, four-on-the-floor in disco.
- **Indie:** 90-140 BPM, guitars, and open voicings with sus2/add9 chords.

## Hip-hop and urban
| Style | BPM | Notes |
|---|---|---|
| Trap | 130-160 (half-time feel) | 808 with glides, hat rolls in 1/32 and triplets, sparse minor melodies |
| Drill | 140-145 | Sliding 808s, syncopated snare on beat 4 and the "and" of 3, dark harmonic_minor |
| Boom bap | 85-95 | Swung drums, chopped samples, jazzy minor 7ths |
| Old school | 90-105 | Drum-machine grooves, simple bass riffs |
| Phonk | 130-160 | Cowbell melody, distorted 808, Memphis vocal chops |
| Melodic rap | 120-150 | Guitar or piano loop, emotional minor progressions |
| Afrotrap | 100-115 | Afro percussion patterns, bouncy 808 |

## Rock and metal
- **Classic / hard rock:** 100-140 BPM, mixolydian or minor pentatonic riffs, I-bVII-IV.
- **Punk:** 160-200 BPM, power chords (`5` chords), straight eighths.
- **Grunge:** 90-120 BPM, drop-tuned riffs, quiet-verse and loud-chorus dynamics.
- **Heavy / thrash:** 160-220 BPM, phrygian and locrian riffs, double kick.
- **Symphonic metal:** add choir, strings and brass on top of thrash parts.
- **Nu metal:** 90-110 BPM, syncopated low riffs, scratch FX.
- **Post-rock / shoegaze:** 70-130 BPM, long crescendos, delayed and reverbed walls of sound.

## Electronic and dance
| Style | BPM | Form / device |
|---|---|---|
| House | 120-126 | Four-on-the-floor, offbeat hats, 16-32 bar sections |
| Deep house | 118-124 | m7/m9 chords, warm bass, shuffled hats |
| Techno | 125-140 | Minimal motifs, filter automation, rumble kick |
| Trance | 132-140 | Supersaw lead, 8-bar arps, long breakdown and build |
| Dubstep | 140 (half-time) | Wobble bass in Harmor/Sytrus, drop on bar 33 |
| Drum & bass | 170-176 | Breakbeats, Reese bass, 32-bar intro for DJs |
| Synthwave / retrowave | 80-118 | Gated reverb snare, analog arps, i-VI-III-VII |
| Ambient | free (60-90) | Drones, slow pads, sparse motifs |
| IDM | any | Irregular meters, glitch edits, Euclidean rhythms |

Energy curve for EDM: intro (DJ-friendly), build (riser, snare roll, low-pass sweep), drop
(everything plays, with sidechain), break, second build, drop 2 (with a variation), outro.

## Classical, jazz and world
- **Baroque:** counterpoint, sequences, a figured-bass feel. Harpsichord (FL Keys) and strings.
- **Romantic:** wide dynamics, chromatic modulations, lush strings.
- **Contemporary classical:** extended harmony, minimalist or aleatoric textures.
- **Swing / bebop:** 120-300 BPM swing, ii-V-I chains, walking bass, ride on 2 and 4.
- **Smooth jazz:** 80-100 BPM, maj9 and m11 chords, soft lead.
- **Blues:** 12-bar I7-IV7-V7, blues scale, shuffle.
- **Turkish art and folk (makam flavour):** Hijaz is `phrygian_dominant`; Nikriz and Kurdi lean on `phrygian`. Usul meters include 9/8 (2+2+2+3) and 7/8 (2+2+3). Instruments: saz, kanun and ney via FLEX or Sytrus plucks. Microtones (koma) are approximate in 12-TET; mention it in the report.
- **Balkan:** 7/8, 9/8, 11/8, `double_harmonic` or `harmonic_minor`, brass and clarinet leads.
- **Middle Eastern:** `double_harmonic`, `phrygian_dominant`, darbuka patterns, drones.
- **Japanese:** `hirajoshi`, `in_sen`, koto and shakuhachi colours, sparse taiko.
- **Celtic:** `dorian`, `mixolydian`, 6/8 jigs, fiddle and tin-whistle leads, bodhrán.
