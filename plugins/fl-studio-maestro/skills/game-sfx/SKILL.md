---
name: game-sfx
description: Make game and app sound effects from 4,500+ real CC0 recordings (coins, dings, UI clicks, whooshes, footsteps on any surface, water, jumps, lasers, explosions, hits, power-ups, hurt, pickups, magic, error and success sounds, doors, swords, monsters and anything else in the catalogue), with several re-processed variations each, delivered as WAV/OGG files in the user's project. Free, no account and no setup. Use when the user wants game sounds, SFX, UI sounds, or says their current sound effects sound generic.
when_to_use: "Use for 'make a coin sound', 'I need footstep sounds on grass and wood', 'give me 8-bit jump and hit sounds', 'water splash sfx', 'UI click sounds for my app', 'door and sword sounds', 'oyunum için ses efekti yap'."
argument-hint: "[sounds you need, e.g. 'coin, jump, footsteps on grass, retro style']"
---

# Game SFX designer

`make_sfx` builds sounds from a bundled catalogue of **4,500+ real CC0 recordings**: Kenney's
audio packs and dozens of OpenGameArt packs (footsteps on snow, gravel, mud, wood and stone;
water splashes; coins; UI; swords; doors; monsters; retro 8-bit packs). It downloads only the
recordings it needs, caches them, and writes a `CREDITS.txt`. CC0 allows commercial use with no
attribution required.

Every take starts from a different recording and is re-processed: varispeed pitch, tone tilt,
weight and saturation, layering of two recordings for coins, hits and explosions, and an
optional room, hall or cave. So a set of 8 footsteps never repeats, and a **seed** reproduces it
exactly. `engine="synth"` (procedural) is the offline fallback, and the server falls back to it
on its own when there is no internet.

## 1. Brief (one question round at most)
Ask once with `AskUserQuestion` in the user's language, with "you decide" first, only for what is
missing:
- **Style:** You decide / Realistic / Retro 8-bit / Cartoon / Magical-fantasy / Sci-fi.
- **Format:** WAV (Recommended) / OGG (smaller, for web and mobile games) / Both.
- **Which sounds:** only ask if the user did not list them. Offer a starter pack: coin, jump,
  hit, hurt, UI click, power-up.

If the user describes their game ("cozy farming game", "cyberpunk shooter"), infer the style and
skip that question.

## 2. Design each sound
Use `kind` for the common sounds, and `query` (English words) for anything else or to refine a
kind (`kind="footstep", query="boots"`). When unsure what exists, call `find_sfx` first.

| Need | Call |
|---|---|
| Coin, gem, money | `kind="coin"`: retro gives chip coins, realistic gives coin clinks and shakes |
| Notification, bell | `kind="ding"` |
| Buttons, menus | `kind="ui_click"`; `kind="error"` for denied; `kind="success"` for confirm jingles |
| Swings, dashes | `kind="whoosh"`, or `query="sword swing"` |
| Footsteps | `kind="footstep"`, `material` = grass, dirt, gravel, wood, stone, metal, snow, sand or puddle; **6-8 variations** |
| Water | `kind="water"`, `variant` = drop, splash, bubbles or pour |
| Jump, land | `kind="jump"` (retro for platformers) |
| Shots, beams | `kind="laser"`, style scifi or retro |
| Explosions, impacts | `kind="explosion"`, `kind="hit"`; `intensity` high for heavy |
| Rewards | `kind="powerup"`, `kind="pickup"`, `kind="magic"` |
| Damage | `kind="hurt"` |
| Anything else | `query="door creak"`, `"glass break"`, `"zombie"`, `"dice roll"`, `"typing"`, `"book page"`, `"engine loop"`... |

Rules:
- **Variations:** 4-8 for sounds that repeat often (footsteps, hits, pickups, shots), 2-3 for
  rare ones.
- **Name files by game event** (`coin_pickup`, `step_grass`, `ui_confirm`), not by kind.
- **Keep one style** across a pack: same `style`, similar `brightness`, same `space`.
- **Tweaks:** "heavier" means `pitch` -3 to -6 and `intensity` 0.7. "Softer" means
  `brightness` 0.3. "Snappier" means `length` 0.6. "Bigger room" means `space="hall"`. Keep the
  seed when the user likes the set and only wants it adjusted.
- Pass `output_dir` = the user's working folder. Files land in `sfx/`, next to `CREDITS.txt`.

## 3. Deliver
List the files grouped by sound, with absolute paths and the recordings they came from, and the
seed of each set. Mention that `sfx/CREDITS.txt` lists the CC0 sources. Offer to open the folder
(`start "" "<folder>"` on Windows) and to adjust anything in plain words.

Optionally, offer a tiny snippet for the user's engine (Unity, Godot, Phaser, pygame) that plays
a random variation each time.
