---
name: game-sfx
description: Design unique, procedurally synthesized sound effects for games and apps (coins, dings, UI clicks, whooshes, footsteps on any surface, water, jumps, lasers, explosions, hits, power-ups, hurt, pickups, magic, error and success sounds), with several variations each, delivered as WAV/OGG files in the user's project. Use when the user wants game sounds, SFX, UI sounds, or says their current sound effects sound generic.
when_to_use: "Use for 'make a coin sound', 'I need footstep sounds on grass and wood', 'give me 8-bit jump and hit sounds', 'water splash sfx', 'UI click sounds for my app', 'oyunum için ses efekti yap'."
argument-hint: "[sounds you need, e.g. 'coin, jump, footsteps on grass, retro style']"
---

# Game SFX designer

Every sound is synthesized from scratch with the `make_sfx` tool: oscillators, FM, modal
(metal and bell) synthesis, filtered noise, granular crunch and bubble physics. No sample
libraries are used, so the sounds are unique to this user. A **seed** reproduces a set exactly,
and a new seed gives brand-new sounds.

## 1. Brief (one question round at most)
If the request leaves things open, ask once with `AskUserQuestion`, in the user's language, with
"you decide" first in each question:
- **Style:** You decide / Realistic / Retro 8-bit / Cartoon / Magical-fantasy / Sci-fi.
- **Format:** WAV (Recommended) / OGG (smaller, for web and mobile games) / Both.
- **Which sounds:** only ask if the user did not list them. Offer a starter pack: coin, jump,
  hit, hurt, UI click, power-up.

If the user describes their game ("a cozy farming game", "a cyberpunk shooter"), infer the style
and skip that question.

## 2. Design each sound
Map the description to `make_sfx` parameters:

| Need | kind | Useful settings |
|---|---|---|
| Coin, gem, currency | `coin` | retro = classic chip arpeggio; cartoon/magical = rising "ka-ching"; realistic = metal clinks |
| Notification, bell, ding | `ding` | `pitch` up for small bells; `space="room"` |
| Buttons, menus | `ui_click` | `brightness` 0.3 soft / 0.8 crisp; `length` 0.6 |
| Swings, dashes, transitions | `whoosh` | `length` 0.5 fast / 2 slow; `intensity` for air pressure |
| Footsteps | `footstep` | `material`: grass, dirt, gravel, wood, stone, metal, snow, sand or puddle; `intensity` = weight; **6-8 variations** |
| Water | `water` | `variant`: drop, splash, bubbles or pour; `space="cave"` for a dripping cave |
| Jump | `jump` | retro = chip sweep, cartoon = boing, realistic = airy hop |
| Shots, beams | `laser` | `style="scifi"` or retro; `pitch` down for heavy guns |
| Explosions | `explosion` | `intensity` = size; `space="hall"` for big spaces; retro = crunchy |
| Punch, impact, block | `hit` | `pitch` down + `intensity` up for heavy hits |
| Power-up, level-up | `powerup` | magical adds sparkle |
| Damage | `hurt` | `intensity` = pain |
| Item pickup | `pickup` | short, bright |
| Spell, sparkle, heal | `magic` | `space="hall"` |
| Wrong action | `error` | |
| Win, quest done | `success` | cartoon or magical for jingles |

Rules:
- **Variations:** 4-8 for sounds that repeat often (footsteps, hits, pickups, gunshots), 2-3 for
  rare ones. Every take differs slightly in pitch, length and texture, so the game never repeats
  one file.
- **Name the files** by game event (`coin_pickup`, `step_grass`, `ui_confirm`), not by kind.
- **Keep one style** across the whole pack. A game's sounds should feel like one family.
- Leave `seed` empty for new sounds. Reuse the returned seed when the user says "keep these,
  make them a bit lower".
- Pass `output_dir` = the user's working folder. Files land in its `sfx/` subfolder.

## 3. Deliver
List the files grouped by sound, with their absolute paths, and the seed of each set. Offer to
open the folder (`start "" "<folder>"` on Windows). Suggest tweaks in plain words, then apply
them with the same seed and new parameters: "heavier footsteps?" means lower `pitch` and higher
`intensity`; "softer UI?" means lower `brightness`.

Optionally, offer to write a tiny code snippet for the user's engine (Unity, Godot, Phaser,
pygame) that picks a random variation each time the sound plays.
