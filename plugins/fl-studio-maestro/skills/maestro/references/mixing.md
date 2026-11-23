# Mix and mastering with FL stock plugins

Plugin parameters are normalized from 0 to 1. Always read the result's `display` text and
adjust in small steps. To find a control's number, call `fl_plugin_params` with `search`
(for example "freq", "gain", "mix" or "ceiling").

## Gain staging
- Set each track's peak to about -12 to -6 dB with `fl_configure_mixer_track` `volume_db`.
- Never go above 0 dB on a track. Leave about -6 dB of headroom on the master before mastering.
- Balance in this order: kick and bass first, then lead/vocal, then harmony, then everything else.

## Panning map (`pan` -1 to 1)
| Element | Pan |
|---|---|
| Kick, snare, sub/808, main bass, lead/vocal | 0 (centre) |
| Hi-hats, shakers | ±0.2-0.35 |
| Percussion, toms | spread ±0.2-0.5 |
| Rhythm guitars, doubled synths | ±0.5-0.65 (hard pairs L/R) |
| Choir sections, string sections | Soprano/violins about -0.3, alto/violas about +0.3, and so on |
| Pads | centre, widened with `stereo_separation` 0.3-0.6 |
| Sub/808 width | `stereo_separation` -1 (mono) |

## Fruity Parametric EQ 2 parameter map (verified in FL Studio 2026)
| Param | Meaning | Value formula |
|---|---|---|
| 0-6 | Band 1-7 level | `0.5 + dB/36` (±18 dB; 0.5 = 0 dB) |
| 7-13 | Band 1-7 frequency | `(log10(Hz) - 1.298) / 3.008` (20 Hz-20 kHz, log; 150 Hz = 0.292, 300 Hz = 0.392) |
| 14-20 | Band 1-7 width | 0-1 (0.388 = default peaking width) |
| 21-27 | Band 1-7 type | `index/7`: 0 off, 1 low pass, 2 band pass, **3 high pass**, 4 notch, 5 low shelf, **6 peaking**, 7 high shelf |
| 28-34 | Band 1-7 order (slope) | 0.5 = 2nd order |
| 35 | Main level | `0.5 + dB/36` |

Default bands: 1 low shelf at 63 Hz, 2-6 peaking at 136/294/632/1363/2936 Hz, 7 high shelf at 6.3 kHz.
Example: high-pass at 150 Hz means param 21 = 3/7 and param 7 = 0.292; a -3 dB mud cut at 300 Hz means param 9 = 0.392 and param 2 = 0.417.

## Fader levels
`volume_db` is converted with FL's own fader curve, so you can trust the requested value: on a mixer track 0 dB is
the default position and the maximum is +5.6 dB; on a channel the maximum is 0 dB (default -5.2 dB).

## EQ (Fruity Parametric EQ 2)
- High-pass at 80-150 Hz on everything except kick, sub and bass.
- If 200-400 Hz builds up into mud, cut it gently (-2 to -4 dB) on pads, guitars and keys.
- Make space for the lead with a slight 2-4 kHz dip on competing pads.
- For air, add a gentle high shelf (+1 to +2 dB) above 10 kHz on the lead, choir and master.

## Dynamics
- Fruity Limiter in compressor mode, or Fruity Compressor: drums with a 2-6 dB gain reduction,
  bass with even 3-4 dB.
- Sidechain (EDM, trap, modern pop): route the kick's track to the bass track's sidechain input
  (the user picks "Sidechain to this track" on the kick's routing), then set the bass's
  Fruity Limiter to COMP mode, with the sidechain input selected and a fast release.

## Space
- Fruity Reeverb 2 on a send/return bus (track 20+): a short room for drums, a hall for
  strings and choir, a plate for the lead.
- Fruity Delay 3: 1/8 or dotted 1/8 on leads and plucks, filtered, with low feedback.
- Keep heavy reverb off the kick, sub and bass. Use more reverb in film, ambient and orchestral
  work, and less in trap and drill.

## Genre notes
- Trap/drill: a loud, centred 808 with saturation (Fruity Fast Dist or Soft Clipper), crisp
  hats, a dry lead with a short delay.
- Orchestral: little compression, long halls, depth set by level and reverb send.
- Lo-fi: low-pass the master around 8-12 kHz, add vinyl noise and a slight wow (Fruity Chorus).

## Mastering (master track 0)
1. A gentle tonal EQ (Fruity Parametric EQ 2): a slight low-mid cut and +1 dB of air if needed.
2. Optionally glue with Fruity Limiter in compressor mode at a 2:1 ratio, with 1-2 dB of reduction.
3. Maximus or Fruity Limiter as the last slot, with the ceiling at -0.3 to -1.0 dB and no clipping.
4. Loudness targets: streaming about -14 LUFS integrated, game loops about -16 LUFS,
   club tracks louder only if the user asks.
