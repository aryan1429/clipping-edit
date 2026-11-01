---
name: clipping-edit
description: Use when the user gives a YouTube link (podcast, stream, interview, long video) and wants short-form clips cut from it - finding the best/viral moments, reframing to vertical with face tracking, animated captions, hooks, zooms and SFX - or shares clipping tutorial links to study. Covers download, transcription, highlight scoring, face-tracked reframe, caption styling, render and review.
---

# Clipping edit

Long video -> best moments -> finished short clips. Style spec = `references/01_ishowspeed_clip_style.md` (READ FIRST; it wins on every style question). Workflow and moment-picking = `references/02_eddie_claude_clipping_tutorial.md`. Technical correctness (timing, cutting, audio, encode, QC, job hygiene) = refs 03-05.

## What to read when
| Task | Read |
|---|---|
| Any clip job | ref 01 (style), ref 02 (picking, job layout) |
| Download, probe, HDR/VFR, ASR words | ref 03 §1 |
| Cut list, dead air, fillers, splicing, one clock | ref 03 §2 |
| Mix, ducking, loudness, SFX timing | ref 03 §3 |
| Encode, mux, colour tags, Windows ffmpeg | ref 03 §4 |
| Captions mechanics and caption gates | ref 04 §1 |
| Cut detection, reframe resets, accent timing | ref 04 §2 |
| Grade pipeline and grade gates | ref 04 §3 |
| QC gates, review sheets, reference studies | ref 05 §1 |
| Caching, re-edits, versions, lessons loop | ref 05 §2 |
| Picking non-copyright background music | ref 06 |

Refs 03-05 come from a study of HeyGen HyperFrames (Apache-2.0). They win on technical correctness where 01/02 are silent and never on style.

## Defaults (override per request)
Any of these can be changed by the request ("9:16", "under 30 s", "all clips", "no SFX", "blue keywords", "skull ending"). Without an override, apply them as hard gates.

| Setting | Default |
|---|---|
| Max clip length | 60 s; render asserts `duration <= 59.5 s` and re-cuts on failure. Target 35-55 s |
| Face tracking | Always on for speaking shots (no blind centre crop); only deliberate wide action shots holding all subjects are exempt |
| Grade | Must measurably beat the source on the same frames: mean luma +10%, median saturation +25%, Laplacian sharpness x1.4 |
| Canvas | 3:4 1080x1440, 60 fps (30 if the source is under 50 fps); 9:16 1080x1920 on request |
| Ending | Clean hard cut right after the payoff. Meme freeze + skull emoji only when the moment is a comedic fail / "no way" reaction that fits |
| Clip count | Show all 3-8 candidates; render the top 3 scoring >= 7/10, always at least #1 |
| Editing tool | EffectCraft when installed; otherwise ffmpeg + ASS/libass + Pillow |
| SFX | One per accent, each a different variant (never reuse one sample) |
| Music bed | Instrumental, mood-matched, licence-safe (CC0 / PD / CC BY / royalty-free; never NC, ND or SA) from `scripts/find_music.py`; credit line in `captions.md` when the licence needs one |

## Setup / preflight
Run `<python> <skill dir>/scripts/preflight.py` (the skill dir is the folder holding this SKILL.md, e.g. `~/.claude/skills/clipping-edit`; in a repo checkout it is `skill/`). It prints a status table and a `PREFLIGHT_JSON {...}` line with resolved paths; exit 1 means a required piece is missing.
- **Required:** Python 3.9+ with `yt_dlp`, `faster_whisper`, `cv2` (opencv-python), `numpy`, `PIL` (pillow); ffmpeg. Install: `<python> -m pip install yt-dlp faster-whisper opencv-python numpy pillow imageio-ffmpeg` (same list as the repo's `requirements.txt`).
- **Optional:** CUDA GPU, EffectCraft CLI, ffprobe, Montserrat Black font (`torch` only as a second CUDA probe; faster-whisper does not need it). For music: a local music folder with a `licences.json` manifest, and optionally `JAMENDO_CLIENT_ID` (free key) so `find_music.py` can also search Jamendo (ref 06).

### Tool discovery (never hard-code paths)
- **Python:** the first of `python3`, `python`, `py -3` on PATH.
- **ffmpeg:** `ffmpeg` on PATH, else `imageio_ffmpeg.get_ffmpeg_exe()`. ffprobe may be absent with the imageio build; then read durations with `ffmpeg -i` or cv2.
- **GPU:** faster-whisper on CUDA (`int8_float16`) if available, else CPU `int8`. `small` fits ~4 GB VRAM; `medium` for better accuracy on bigger GPUs; CPU is fine for sources under ~30 min.
- **EffectCraft CLI:** env var `EFFECTCRAFT_CLI`, else `effectcraft-cli` on PATH. Not found -> fallback editing path.
- **Font:** Montserrat Black from the OS font dirs (Windows `Fonts`, macOS `~/Library/Fonts` + `/Library/Fonts`, Linux `~/.fonts`, `~/.local/share/fonts`, `/usr/share/fonts`, or `fc-match`) or env `CLIP_FONT` (path to the .ttf); fallback Montserrat ExtraBold, then Arial Black.

### Generic gotchas
- On some installs faster-whisper's PyAV decoder breaks: decode with ffmpeg to 16 kHz mono float32 and pass the numpy array to `transcribe()`.
- If cv2/faster_whisper live in user site-packages, do not run Python with `-I` (it hides them); use `-P` to keep the cwd off `sys.path`.
- Set `PYTHONIOENCODING=utf8` on Windows consoles (titles, emoji and non-ASCII transcripts).
- yt-dlp "not a bot" block: retry with `--cookies-from-browser <browser>`.

## Pipeline
One-line trigger ("clip this video: <url>"): run the whole job without asking questions. Ref 01 rules on style; ref 02 rules on workflow and picking.
0. **Preflight.**
   - Run `scripts/preflight.py`; take `whisper_device`, `whisper_compute_type`, `ffmpeg`, `font` and `edit_path` from its JSON.
   - Note rights: is the source the user's own channel or third-party?
   - Create the job folder `output/<slug(title)[:35]>-<videoId>/` (under the current working directory unless the user names another).
1. **Download.**
   - Fetch audio-only first so ASR can start, then the best SDR video: `-f "bv[dynamic_range=SDR][ext=mp4]+ba[ext=m4a]/bv[dynamic_range=SDR]+ba/bv*+ba/b"` (plus subtitles if present). Probe once into `source_facts.json` (`scripts/probe_source.py`, ref 03 §1).
   - On a bot block, retry with `--cookies-from-browser <browser>`.
2. **Transcribe.**
   - faster-whisper with word timestamps, run in the background with an ETA given. Output: `transcript.json` with word ids `w0..`.
   - Gate (ref 03 §1): ASR audio decoded with ffmpeg on the video's clock (`aresample=async=1:first_pts=0`); words normalised; > 20% junk in a 60 s window re-runs with the next model; final-silence words dropped.
   - Also write `transcript_lines.txt`: `mm:ss  SPEAKER: sentence`. Split at punctuation or at gaps over 0.6 s. Label speakers by diarization or by LLM inference.
3. **Pick moments (ref 02).** The LLM reads the whole `transcript_lines.txt`.
   - **Candidate JSON:** `{rank, score 1-10, start_word, end_word, remove_words, hook_line, hook_type, hook_speaker, payoff_line, title, post_caption, reason}`, saved to `clips.json`. The LLM names word ids, never seconds; `scripts/cutlist.py` derives frame-snapped times (ref 03 §2).
   - **Copy fidelity:** every number and name in the title and post caption occurs in the clip's words, the video title or the channel (ref 05 §2).
   - **Hook type:** `hook_type` is one of contrarian / surprising_fact / novel_claim / story_opener. Reject a candidate without one.
   - **Start:** exactly on the hook line (first word minus 0.05 s). Warm-up, filler and ramble before it are cut. The hook may be the other speaker's question. The premise must be spoken by t <= 2.5 s.
   - **End:** on the payoff line (last word plus 0.15 s). The clip must be understandable to a total stranger with zero context.
   - **Length:** within the max length after dead-air removal (default <= 59.5 s, target 35-55 s). If the payoff falls past it, use an earlier payoff, cut the middle tangent, or drop the candidate.
   - **Count and spread:**
     - 3-8 non-overlapping candidates, about 1 per 12-15 min of source.
     - Spread across the source, with no more than 50% from one third of it.
     - Ranked by score, descending.
   - **Copy for each candidate:**
     - title: Title Case, 4-7 words, curiosity or contrast phrasing
     - post caption: 1-2 sentences plus 3 lowercase hashtags
   - **Always show the user the table** `# | Title | Score | Hook type | Length | Opens with`.
   - **Renders:** default count from the Defaults table. "best clip only" renders #1 only; "all" renders every candidate.
4. **Cut, then reframe to the canvas** (default 3:4 1080x1440 60 fps; ref 01 section 4).
   - Cut first: `cutlist.py` (fail if kept length > 59.5 s), then `splice.py` (frame-exact video-only `cut.mov` + one ramped PCM dialogue stem). Every later timing (captions, crop path, accents, ducking) uses the cut list's remap (ref 03 §2).
   - Detect faces per frame (YuNet via cv2 needs no extra install; MediaPipe / InsightFace also work) and track the active speaker.
   - Detect camera cuts with `scripts/cuts.py` (classified detector: hard/soft cuts reset; flashes and fast moves do not; ref 04 §2). At each cut, reset the smoother and snap to the new shot's active face. Never pan across a cut.
   - Within a shot, smooth per ref 01: EMA, 8% W dead-zone, <= 3% W/s, no jitter.
   - On a same-camera jump cut, vary the crop scale by 4-10% (face height stays at 20-30% H).
   - Two people: use a wider crop that holds both. Never use a split screen.
   - Gate: the face bbox plus a 5% margin is always inside the frame, including after any push-in or zoom.
5. **Captions (ref 01 section 3).** Montserrat Black ALL CAPS, 2-4 word chunks building word by word, white + 1-3 semantic keyword colours, centred at ~50% height, moved to ~72% if over the face.
6. **Polish (ref 01).** **Music bed (ref 06):** `scripts/find_music.py --mood <hype|tense|funny|emotional|chill|epic|inspiring, from the transcript> --clip-s <len> --dialogue clips/NN/dialogue.wav --library <music folder> --choose --out-dir clips/NN` writes `bed.<ext>` + `music.json`. Its `bed` block goes into `audio_plan.json` and its `attribution` into `captions.md`. On exit 1, follow its `hints`. Never put trending or chart songs in the exported MP4. Hook = strongest line from frame 0 (no banner); music full from frame 0; accents (flash/whip + unique SFX) every ~6-8 s; ending per the Defaults table; grade the footage only, under accents and captions (ref 04 §3), then verify the gains with `scripts/grade_gate.py`. Accents start at full peak on their cause frame; each SFX peak lands on accent frame + 1 (ref 04 §2, ref 03 §3). Audio: `scripts/mix_audio.py` (static gain to -14 LUFS, bed at its strongest section, word-timed duck -10 dB with 20 ms / 300 ms ramps, limiter last; ref 03 §3).
7. **Edit and render** (see Editing paths below), h264 + AAC.
   - Output: `raw/NN-slug.mp4` (reframed only) and `edited/NN-slug.mp4`.
   - Log one line per clip: `ok NN-slug.mp4 dur:XX.Xs accents:N captions:N`.
   - Finish with `scripts/finalize_mux.py`: the mix is fitted to the decoded frame count, AAC is encoded once, true peak is <= -1.0 dBTP after the AAC, then copy-mux with BT.709 tags and faststart, the delivery gate, and an atomic promote. Never `-shortest`.
   - Gates before delivery: ref 01's QC checklist plus ref 05 §1 (decoded frames, `cuts.py --plan` events vs plan, A/V offset, black/freeze/frame 0, framing medians), ref 04's caption and grade gates and ref 03 §3's audio gates. Open the review sheets in `qc/NN/`; fix every P0 before delivery.
   - Deliver the paths, the candidate table and `captions.md` (title and post caption per clip).
8. **Re-edits** (for example "under 30 s, no SFX, blue keywords, 9:16"): reuse the cached audio, transcript, `clips.json` and face tracks. Write the change into the clip's plan as absolute values. Re-run only the stages after the changed field (SFX or music: new mix + `-c:v copy` mux), never the download or ASR. Version every render; "undo" re-delivers the previous version (ref 05 §2).
- **Lessons:** log each correction, QC fail and fallback; a detail seen in 2+ jobs becomes a rule or QC check (ref 05 §2).
- **Benchmark:** a 1h43 source gives a ranked list plus 3 clips in <= 40 min end to end on a mid-range GPU (CPU-only takes longer for ASR).

## Editing paths
**A. EffectCraft (default when `EFFECTCRAFT_CLI` / `effectcraft-cli` is found).** Open-source After Effects-style editor driven by script/CLI.
- **Python/ffmpeg prep:** download, transcribe, pick, `splice.py` cuts frame-exact video-only segments from the source through `norm_vf` (seek early + trim, seekable CFR `.mov`; ref 03 §2, §4) plus one pre-rolled PCM dialogue stem, smoothed per-frame crop path (reset at cuts), caption chunk list with keyword colours, accent/SFX timeline, audio mix (dialogue -14 LUFS + ducked music + SFX).
- **EffectCraft edit:** canvas-size comp; source layer with Position/Scale keyframes from the crop path (that is the face tracking); per-chunk text layers (per-word layers or text animators for the build; stroke + shadow + keyword glow); flashes/whips, sticker PNGs; grade on an adjustment layer (Brightness/Contrast, Hue/Sat or Vibrance, Sharpen, glow from a blurred Screen copy). Adjustment-layer blend modes may be ignored; composite the glow with a precomp or CC Composite.
- **Render:** high bitrate (>= 30 Mbps), in parts if memory runs out (frames == sum of parts); then `finalize_mux.py` (one AAC encode, copy-mux, colour tags per ref 03 §4; check EffectCraft's output colour once per version).
- Anything EffectCraft cannot draw (e.g. colour emoji) -> Pillow PNG imported as a footage layer.

**B. Fallback: ffmpeg + ASS/libass + Pillow (no EffectCraft).**
- Crop path -> ffmpeg `crop`/`scale` (per-frame via `sendcmd` or by rendering cropped frames with cv2 and piping to ffmpeg).
- Captions -> an ASS file (`\fad`/`\t` for the 3-frame fade + scale + blur-in, `\bord`/`\shad`/`\blur` for stroke, shadow and glow, per-word `\c` colours), burned with the `subtitles`/`ass` filter and `fontsdir` pointing at the font.
- Flashes, washes, stickers, skull -> Pillow PNGs / `color` sources overlaid with `overlay` + `enable`/fade; grade with ref 01's reference ffmpeg chain.
- Tag BT.709 before `ass`/`overlay`/`color` (untagged frames use BT.601). One encode: libx264 `-preset medium -crf 16 -bf 0`, `yuv420p`, BT.709 flags; then `finalize_mux.py` (ref 03 §4).

## References and studying new material
- `references/01_ishowspeed_clip_style.md`: target look (canvas, captions, accents, grade, QC). Wins on all style questions.
- `references/02_eddie_claude_clipping_tutorial.md`: Eddie | AI's Claude clipper (https://youtu.be/IY08-3TS2o8): hook-first/payoff picking, hook types, /10 ranking, 3-8 candidates, title + post caption, shot-cut reframe reset, output layout, cached re-edits. Wins on workflow and picking; its NOT ADOPTED list shows conflicts with ref 01.
- `references/03_hyperframes_media_pipeline.md`, `04_hyperframes_captions_framing_grade.md`, `05_hyperframes_qc_workflow.md`: mechanics and gates from a study of HeyGen HyperFrames (Apache-2.0). See "What to read when".
- **Scripts** (`scripts/`, each prints one JSON object; exit 0 ok, 1 gate failed, 2 bad input; ffprobe optional): `probe_source.py`, `cutlist.py`, `splice.py`, `cuts.py`, `mix_audio.py`, `finalize_mux.py`, `grade_gate.py`, `find_music.py`, with shared helpers in `cliplib.py`. Run with `<python> -P`. Tests live in the repo's `tests/`.
- `references/06_background_music.md`: choosing a bed (mood → BPM and energy, no vocals under speech, a strong entry from frame 0, phone-speaker low end), sources ranked by safety with verified terms, the licence policy (CC 4.0: syncing music to video makes Adapted Material, so no ND or SA; no NC), Content ID and in-app-sound caveats, and the credit-line format.
- **New reference shorts** (needs a clone of the repo; `analysis/` is not part of the installed skill folder): download them, run `<python> analysis/tools/extract_ref.py <video.mp4> <outdir>` (metadata, cut times, 1 fps frame grid, luma/sat/sharpness stats, transcript), write the study to `analysis/refs/`, then distil the rules into `references/NN_<topic>.md` (what the editor does, timings, caption style, tools, and the rule it implies for this pipeline).
- **New tutorials:** one `references/NN_<topic>.md` per video, raw notes in `analysis/tutorials/`.
