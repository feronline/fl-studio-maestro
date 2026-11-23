---
name: score-video
description: Score an existing video (Instagram reel, TikTok, YouTube short, trailer, game clip) with original music and sound effects that match its length, mood and cuts, ducked under any speech so the voice stays clear, then deliver the finished MP4. Use when the user gives a video file and wants music, a soundtrack, background music or sound effects for it.
when_to_use: "Use for 'add music to this video', 'make background music for my reel', 'score this clip', 'bu videoya müzik yap', 'videoma uygun ses efekti ekle'."
argument-hint: "[path to the video, plus any mood wishes]"
---

# Video scoring

The result is the user's video with an original soundtrack. The music fits its length, mood and
pacing, hits land on its cuts, and the music drops under the voice whenever someone speaks.

## 1. Watch the video
Call `analyze_video` with the video's path. Then **Read the keyframe images** it returns and
judge what the video is about, its energy, colours and setting, and who the audience is. The
analysis also gives:
- `duration_s`: the music must last exactly this long.
- `scene_cuts_s`: the moments to mark with a section change, hit, riser or whoosh.
- `speech_segments_s` and `has_speech`: where the voice is. The mix will duck around it.
- `tempo_suggestions`: tempos whose bar lines land on the cuts. Prefer the top one if it fits
  the mood; otherwise pick a fitting tempo and note which cuts it catches.

## 2. Brief (one question round at most)
Ask once with `AskUserQuestion` in the user's language, with "you decide" first:
- **Mood:** You decide (Recommended, based on what you saw) / Energetic / Emotional / Funny /
  Dark-cinematic.
- **Sound effects:** You decide / Yes, whooshes and hits on the cuts / Music only.
- **Original audio:** Keep it (voice and ambience, Recommended when there is speech) / Replace
  it with music.

Skip questions the user already answered. If there is speech, plan a sparser, lower arrangement
under the voice: fewer leads, pads and bass instead of a busy melody.

## 3. Compose for picture
Use the `maestro` workflow (create_project, register_agent, write_pattern, review_project,
arrange), with these constraints:
- `bars = round(duration_s × bpm / 60 / 4)`, so that `render_audio(fit_seconds=duration_s)`
  only trims the tail.
- Put a section boundary (`sections`) at the bar nearest each important cut. Use a fill or riser
  in the bar before it and a crash on the cut.
- While someone speaks, keep the melody out of the 1-4 kHz range or leave it out entirely. Save
  the big moments for gaps in the speech.
- Short-form social video needs energy in the first 2 seconds. Do not start with a long, slow
  intro.

Then call `render_audio` with `fit_seconds=duration_s`, `target_lufs=-14` and `output_dir` set to
the user's folder.

## 4. Sound effects (if wanted)
Use `make_sfx` (see the `game-sfx` skill) for whooshes on cuts, hits on reveals, risers into
drops, and dings on text pops. Start a whoosh about 0.3-0.5 s before the cut, so its peak lands on
it. Keep effects at -12 to -6 dB.

## 5. Mix onto the video
Call `score_video` with:
- `video_path`;
- `music_path` set to the MP3 from `render_audio`;
- `sfx_cues` (file, time_s, gain_db);
- `keep_original_audio` set from the brief;
- `duck_db` -12, or -15 when the voice is quiet;
- `output_dir` set to the user's folder.

It writes `<video>_scored.mp4` and `<video>_scored-audio.mp3`.

## 6. Deliver
Give the MP4 path first, then the music MP3 and MIDI. Add a one-line summary: tempo and key,
which cuts are hit, how many speech parts are ducked, and loudness. Offer to open the video
(`start "" "<path>"`). Offer 2-3 concrete revisions ("more energy at the start", "music louder
between sentences", "no whoosh at 0:04").
