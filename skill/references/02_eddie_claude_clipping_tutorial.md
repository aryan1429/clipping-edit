# 02 - Eddie | AI "Claude Code Can Now Clip ANY Video (Free Skill)": workflow and moment-picking

Studied 2026-10-31 from https://youtu.be/IY08-3TS2o8 (Eddie | AI, about 8:20). Raw chapter studies: `C:/Users/aryan/clipping-edit/analysis/tutorials/02_eddie_tutorial.md`. Frames and stills: `C:/Users/aryan/clipping_jobs/tut1/`.

**Precedence.** Ref 01 (the IShowSpeed look) is the user's target style and wins on every style question: canvas, captions, accents, SFX, grade and pacing. This ref wins on workflow and moment-picking, where ref 01 says nothing. The user's hard rules override both: final file ≤ 60 s, face tracking always on, CC must be sharper, brighter and more colourful, and 3:4 is the default canvas.

## Source
- The demo skill is "Long-Form Clipper" / `Claude-Video-Clipper-main.zip`. It is free behind the Skool "AI Builders Club". Its author says it runs his Instagram at 20 reels a day.
- The demo source was MrBeast on The Diary Of A CEO (1:43:14). The run produced 7 clips with no human touch after the prompt. A second run used his own 8-minute video.

## What the demoed skill does end-to-end
- **Trigger.** One line in Claude Code opened on the project folder: "Run the clipper skill for this video <url>" or "clip this video: <url>". It asks no questions.
- **Four stages:**
  1. **Watch:** "downloads + transcribes"
  2. **Pick:** "finds the best moments"
  3. **Cut:** "cuts them vertical"
  4. **Edit:** "captions, zooms, sounds"
- **Before downloading,** Claude checks rights ("from your own channel, so rights are fine"). It downloads audio only for ASR, runs transcription as a background task, and gives an ETA ("2-4 minutes").
- **Lesson 1, verbatim, "What you get back":**
  - "3 to 8 vertical clips (9:16, 1080x1920)"
  - "Every clip starts on a hook and ends on a payoff, so it works for someone with zero context"
  - "The frame re-centres on whoever is speaking, every time the camera cuts"
  - "Zooms, word-by-word captions and a couple of subtle whooshes on every clip"
  - "A title and a ready-to-post caption for every clip"
- **Final reply.** `Done. 7 clips are in output/<slug(title)[:~35]>-<videoId>/edited/`, then a table with the columns `# | Clip | Length | Opens with`.
- **Re-edit by prompt, with no re-download.** For example: "extract only the best clip and keep it under 30 seconds with no sound effects. Also, use a blue color for the captions." The result was clip 7 trimmed to 0:28, with blue captions and no SFX.

## Pipeline and tools
- **Repo layout:** `.claude/`, `CLAUDE.md`, `assets/` (`sfx/click.wav`, `whoosh-cinematic.mp3`, `whoosh-heavy.mp3`), `clipper/` (Python package), `remotion/` (optional, slower render engine), `output/`, `install.py`, `run.py`, `requirements.txt`.
- **Edit scripts:** `cut.py`, `reframe.py`, `edit.py`, `sfx.py`.
- **Prerequisites:** Claude Code (free download) plus a paid Claude plan ("the pro plan works fine"). Extract the zip, open Claude Code on that folder, approve any permission prompts. Setup is one-time, a few minutes.
- **Setup prompt:** "Hey Claude can you set up this full repository for me." (on screen; spoken as "this folder repository").
  - It checks Python, ffmpeg, Node and GPU.
  - `install.py` creates a `.venv` with yt-dlp, faster-whisper and OpenCV, plus optional Remotion.
  - It then smoke-tests the CLI and imports.
- **Setup notes:**
  - The first run downloads a "~500 MB speech model" (faster-whisper small).
  - `--device cuda` is optional; the default is CPU.
  - On a YouTube "not a bot" error: `--cookies-from-browser chrome`.
- **The LLM's only job** is picking moments plus writing the titles and captions. Everything else is deterministic local Python, and the default "python engine" renders 1080x1920.
- **Log line per clip:** `ok 01-want-to-be-liked-dont-help-people.mp4  zooms:19  captions:105`.
- **Captions** are built from Whisper `word_timestamps`. The accent colour is chosen in this order: brand colour, then a colour sampled from the video, then the default `#FFD60A`.
- **Zooms:**
  - Position chosen from the transcript ("right when Mr. Beast finishes a point" = sentence end), then centred on the face found by face detection in that shot.
  - 13-19 per clip, about one every 3-4 s.
  - Scales vary: 1.16x, 1.04x, 1.22x.
  - Framing changes on every camera cut "so the jump doesn't feel too harsh".
- **Reframe:**
  - Detects camera cuts.
  - Re-centres on the active speaker once per shot, held static ("FACE CENTRED", no jitter while he gestures).
  - In a two-shot, it boxes the speaker.

## Moment-picking criteria (verbatim where possible)
1. "It reads the whole transcript of the video start to finish". This is a timestamped, line-by-line transcript (`mm:ss` per line) with speaker labels ("Steven: Are you a billionaire?").
2. "moments that work on their own, something a total stranger could watch with zero context and fully understand" (the "0 context" badge).
3. "Right before it, Mr. Beast is kind of rambling. So Claude skips all of that and starts the clip exactly on this hook."
   - Lines 22:19-22:23 are tagged WARM-UP and removed. Line 22:25, "To go viral, you have to do something that's never been done before.", is tagged HOOK.
   - The hook may be the interviewer's question.
4. "it ends on the payoff, so the clip actually feels finished instead of just cutting it through." The payoff line is tagged PAYOFF: "...there's usually a reason because it's very f***ing hard."
5. "It also knows the types of hooks that work on shorts like a surprising fact or a bold claim or the start of a story. And every clip has to open with one of them."
   - On-screen categories: **contrarian, surprising fact, novel claim, story opener**.
6. "it gives every clip a score out of 10 and ranks them so the best one is always first". On screen: 10, 9, 9, 8, 8, 7, ... sorted descending.
7. **Spread across the whole source.** The clip markers span 0 to 1:43:14. The 7 clips run 29-76 s (3 of 7 are over 60 s).
8. **Per clip:**
   - A title in Title Case, 4-7 words, with curiosity or contrast phrasing ("Billionaire On Paper, Broke In The Bank").
   - A post caption of 1-2 sentences plus 3 hashtags ("MrBeast is a billionaire with less than $1M in the bank. Here's why. #mrbeast #money #business").

## Edit style of its outputs (for contrast only; ref 01 rules)
- **Framing:** 9:16 full-bleed with a single speaker. No b-roll, banner, progress bar, music bed or colour grade (source colour).
- **Captions:**
  - Montserrat ExtraBold/Black-like, ALL CAPS, cap height about 4.5-6% H. Narration and overlay say "2-3 words at a time"; the demo frames often show a single word.
  - Placed at 58-66% H (chest level), with a thin dark stroke and a soft shadow.
  - Karaoke: the active word is yellow (#F2C200-#FFD60A) and the rest white.
  - Each new word scale-pops in.
  - Money and status keywords (BILLIONAIRE, MILLION) appear alone in a dark rounded box with a neon border.
- **Zooms:** subtle 1.04-1.22x punch-ins at sentence ends.
- **SFX:** from the 3 bundled files, "a couple of whooshes on every zoom"; can be switched off by prompt.
- **Render:** 1080p.

## Cost and speed notes
- **Cost.** The skill costs $0 beyond Claude Pro ($20/mo, or $17/mo billed annually). There are no API keys or credits. Download, Whisper, cutting and editing all run locally, and only the Pick step uses the Claude plan ("about 5 podcasts like this a week").
- **OpusClip, for comparison:**
  - Starter is $15/mo for 150 min. One 1:43 podcast uses about 2/3 of a month.
  - Pro is $29/mo for 300 min, which covers about 3 such podcasts.
- **Speed claims:**
  - 1:43 source to 7 clips in about 30 min (the course page says under 40 min) end to end.
  - The edit pass took about 7 min for 7 clips, so about 1 min per clip.
  - An 8-minute source takes 2-4 min (first run longer: Whisper model download).

## ADOPTED INTO OUR PIPELINE (measurable)

### Picking (SKILL step 3)
1. **Full-transcript read.** Build `transcript_lines.txt` as `mm:ss  SPEAKER: sentence` from the whisper words, split at sentence punctuation or at gaps over 0.6 s. Label speakers by diarization, or by LLM inference from the dialogue when there is no diarizer. The LLM reads the whole file. Do not use heuristic window scoring alone.
2. **Candidate fields.** Every candidate is JSON: `{rank, score(1-10), start, end, hook_line, hook_type, hook_speaker, payoff_line, title, post_caption, reason}`. `hook_type` is one of `contrarian | surprising_fact | novel_claim | story_opener`. A candidate without a valid `hook_type` is rejected.
3. **Start on the hook.**
   - `start` = the first word of the hook line minus 0.05 s.
   - Delete warm-up, filler and ramble before it ("I just…", "I don't know…").
   - The hook may be the other speaker's question.
   - Ref 01's rule still applies: the premise must be spoken by t ≤ 2.5 s.
4. **End on the payoff.** `end` = the last word of the payoff line + 0.15 s, cut at a word boundary. The clip must be understandable to a "total stranger with zero context". The LLM self-checks this and states it in `reason`.
5. **Length.**
   - The hook-to-payoff span must be ≤ 59.5 s after dead-air removal; target 35-55 s.
   - If the natural payoff falls past 60 s, either pick an earlier payoff or tighten inside the clip (remove the middle tangent).
   - If neither works, drop the candidate. Never ship it over 60 s.
6. **Spread and count.**
   - Return 3-8 candidates, at least 3 when the source is 10 minutes or longer. Scale with length: about 1 per 12-15 min, max 8.
   - Candidates must not overlap.
   - Spread them across the source: no more than 50% from any one third of the video, unless the content forces it.
   - Rank by score, descending.
7. **Per-clip copy.**
   - Title: Title Case, 4-7 words, curiosity or contrast phrasing.
   - Post caption: 1-2 sentences plus 3 lowercase hashtags.

### Workflow and output
8. **Multi-clip deliverable.**
   - Always show the ranked candidate table: `# | Title | Score | Hook type | Length | Opens with`.
   - By default, render the top 3 candidates with score ≥ 7, always at least #1.
   - "only the best clip" renders #1 only. "all" renders every candidate.
9. **Output layout.**
   - Job folder: `output/<slug(title)[:35]>-<videoId>/`.
   - Contents: `raw/NN-<title-slug>.mp4` (reframed, no captions or grade) and `edited/NN-<title-slug>.mp4`, plus `clips.json`, `captions.md` (title and post caption per clip) and the transcript files.
   - Log one line per clip: `ok NN-slug.mp4  dur:XX.Xs  accents:N  captions:N`.
10. **Cached re-edits.**
    - Cache the audio, `transcript.json`, `transcript_lines.txt`, `clips.json` and face tracks.
    - Prompt-level changes (max length, clip count, SFX off, accent colour override, 9:16) re-run only cut, reframe and render, never download or ASR.
11. **Preflight and run hygiene.**
    - Check Python imports (yt_dlp, faster_whisper, cv2, numpy), ffmpeg and CUDA.
    - Download audio-only first for ASR, and run ASR in the background (CUDA int8 on the RTX 3050) while the video downloads.
    - On a yt-dlp bot block, retry with `--cookies-from-browser chrome`.
    - Note rights: whether the source is the user's own channel or third-party.
12. **Benchmark.** A 1h43 source should give a ranked list plus 3 rendered clips in ≤ 40 min end to end, with about 1-2 min of render per clip.

### Reframe (SKILL step 4, compatible with ref 01 section 4)
13. **Shot-aware tracking.**
    - Detect camera cuts with ffmpeg `select='gt(scene,0.3)'` or a histogram difference over 0.35.
    - Reset the smoother at every cut: snap to the new shot's active face on the cut frame and never pan across a cut.
    - Within a shot, keep ref 01's EMA, 8% W dead-zone and ≤ 3% W/s, so gestures do not drag the crop.
14. **Face-in-frame gate.** After any crop or scale (including the ref 01 push-in on long holds and the ending zoom-blur), the face bbox plus a 5% margin must stay fully inside the frame. This is checked in QC on 1 fps samples. Nobody may be "half cut off".
15. **Cut-to-cut scale variation.** When consecutive shots come from the same camera (jump cut), vary the crop scale by 4-10% between them, so the jump does not feel harsh. This changes framing only at a cut, which ref 01 allows ("reframe with cuts"). Stay within ref 01's face-height range of 20-30% H.

## NOT ADOPTED (and why)
- **9:16 1080x1920 default.** Ref 01 and the user rule set 3:4 1080x1440. 9:16 is available only on request.
- **Clips of 60-76 s.** The user's hard rule is ≤ 60 s.
- **Karaoke active-word recolour, per-word scale-pop, 1-word pages, captions at 58-66% H, neon keyword boxes.** Ref 01 specifies a word-by-word additive build with a 3-frame fade/blur-in, "no bounce and no karaoke recolour/box", semantic keyword colours, 2-4 words per chunk and y = 50% H.
- **Accent colour from brand, then video, then #FFD60A.** Ref 01 uses a fixed semantic palette (green, yellow, red, magenta, cyan). We keep only their prompt-level colour override, as a user option.
- **Zoom punch-ins every 3-4 s at sentence ends (13-19 per clip).** Ref 01 says "no constant zoom punch-ins", "no zoom changes inside a shot" and "never per-word zoom punches". Only ref 01's mild push-in on long holds remains.
- **Whooshes on every zoom, from the same 3 files.** Ref 01 puts SFX only on flash or whip accents (1 per 6-8 s), and the user's unique-variant rule forbids reusing one sample. A "no SFX" switch is still honoured.
- **Static crop per shot with no tracking.** The user rule says face tracking is always on. We take only their per-cut reset (rule 13).
- **No grade or music bed.** Ref 01 and the user rule require a sharper, brighter and more colourful grade plus a continuous music bed.
- **Remotion engine and a repo-style installer.** Our ffmpeg + libass + Pillow path already covers this (ref 01). We use the preflight checks without the repo packaging.
