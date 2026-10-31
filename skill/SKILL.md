---
name: clipping-edit
description: Use when the user gives a YouTube link (podcast, stream, interview, long video) and wants short-form clips cut from it - finding the best/viral moments, reframing to vertical with face tracking, animated captions, hooks, zooms and SFX - or shares clipping tutorial links to study. Covers download, transcription, highlight scoring, face-tracked reframe, caption styling, render and review.
---

# Clipping edit

Long video -> best moments -> finished short clips. Style spec = `references/01_ishowspeed_clip_style.md` (READ FIRST; it wins on every style question). Workflow and moment-picking = `references/02_eddie_claude_clipping_tutorial.md`.

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

## Setup / preflight
Run `<python> <skill dir>/scripts/preflight.py` (the skill dir is the folder holding this SKILL.md, e.g. `~/.claude/skills/clipping-edit`; in a repo checkout it is `skill/`). It prints a status table and a `PREFLIGHT_JSON {...}` line with resolved paths; exit 1 means a required piece is missing.
- **Required:** Python 3.9+ with `yt_dlp`, `faster_whisper`, `cv2` (opencv-python), `numpy`, `PIL` (pillow); ffmpeg. Install: `<python> -m pip install yt-dlp faster-whisper opencv-python numpy pillow imageio-ffmpeg` (same list as the repo's `requirements.txt`).
- **Optional:** CUDA GPU, EffectCraft CLI, ffprobe, Montserrat Black font (`torch` only as a second CUDA probe; faster-whisper does not need it).

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
   - Fetch audio-only first so ASR can start, then the best mp4 (plus subtitles if present).
   - On a bot block, retry with `--cookies-from-browser <browser>`.
2. **Transcribe.**
   - faster-whisper with word timestamps, run in the background with an ETA given. Output: `transcript.json`.
   - Also write `transcript_lines.txt`: `mm:ss  SPEAKER: sentence`. Split at punctuation or at gaps over 0.6 s. Label speakers by diarization or by LLM inference.
3. **Pick moments (ref 02).** The LLM reads the whole `transcript_lines.txt`.
   - **Candidate JSON:** `{rank, score 1-10, start, end, hook_line, hook_type, hook_speaker, payoff_line, title, post_caption, reason}`, saved to `clips.json`.
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
4. **Reframe to the canvas** (default 3:4 1080x1440 60 fps; ref 01 section 4).
   - Detect faces per frame (YuNet via cv2 needs no extra install; MediaPipe / InsightFace also work) and track the active speaker.
   - Detect camera cuts (ffmpeg `scene` > 0.3). At each cut, reset the smoother and snap to the new shot's active face. Never pan across a cut.
   - Within a shot, smooth per ref 01: EMA, 8% W dead-zone, <= 3% W/s, no jitter.
   - On a same-camera jump cut, vary the crop scale by 4-10% (face height stays at 20-30% H).
   - Two people: use a wider crop that holds both. Never use a split screen.
   - Gate: the face bbox plus a 5% margin is always inside the frame, including after any push-in or zoom.
5. **Captions (ref 01 section 3).** Montserrat Black ALL CAPS, 2-4 word chunks building word by word, white + 1-3 semantic keyword colours, centred at ~50% height, moved to ~72% if over the face.
6. **Polish (ref 01).** Hook = strongest line from frame 0 (no banner); music full from frame 0; accents (flash/whip + unique SFX) every ~6-8 s; ending per the Defaults table; grade = eq/vibrance/unsharp + light glow, then verify the luma/sat/sharpness gains.
7. **Edit and render** (see Editing paths below), h264 + AAC.
   - Output: `raw/NN-slug.mp4` (reframed only) and `edited/NN-slug.mp4`.
   - Log one line per clip: `ok NN-slug.mp4 dur:XX.Xs accents:N captions:N`.
   - Review frames against ref 01's QC checklist (face in frame, captions synced, no cut mid-word, grade ratios, duration) and fix before delivery.
   - Deliver the paths, the candidate table and `captions.md` (title and post caption per clip).
8. **Re-edits** (for example "under 30 s, no SFX, blue keywords, 9:16"): reuse the cached audio, transcript, `clips.json` and face tracks. Re-run steps 4-7 only, never the download or ASR.
- **Benchmark:** a 1h43 source gives a ranked list plus 3 clips in <= 40 min end to end on a mid-range GPU (CPU-only takes longer for ASR).

## Editing paths
**A. EffectCraft (default when `EFFECTCRAFT_CLI` / `effectcraft-cli` is found).** Open-source After Effects-style editor driven by script/CLI.
- **Python/ffmpeg prep:** download, transcribe, pick, cut + concat source segments to a near-lossless intermediate (keep 60 fps), smoothed per-frame crop path (reset at cuts), caption chunk list with keyword colours, accent/SFX timeline, audio mix (dialogue -14 LUFS + ducked music + SFX).
- **EffectCraft edit:** canvas-size comp; source layer with Position/Scale keyframes from the crop path (that is the face tracking); per-chunk text layers (per-word layers or text animators for the build; stroke + shadow + keyword glow); flashes/whips, sticker PNGs; grade on an adjustment layer (Brightness/Contrast, Hue/Sat or Vibrance, Sharpen, glow from a blurred Screen copy). Adjustment-layer blend modes may be ignored; composite the glow with a precomp or CC Composite.
- **Render:** high bitrate (>= 30 Mbps), in parts if memory runs out; then ffmpeg-mux the mixed audio with `-c:v copy` (no second video encode) and verify duration.
- Anything EffectCraft cannot draw (e.g. colour emoji) -> Pillow PNG imported as a footage layer.

**B. Fallback: ffmpeg + ASS/libass + Pillow (no EffectCraft).**
- Crop path -> ffmpeg `crop`/`scale` (per-frame via `sendcmd` or by rendering cropped frames with cv2 and piping to ffmpeg).
- Captions -> an ASS file (`\fad`/`\t` for the 3-frame fade + scale + blur-in, `\bord`/`\shad`/`\blur` for stroke, shadow and glow, per-word `\c` colours), burned with the `subtitles`/`ass` filter and `fontsdir` pointing at the font.
- Flashes, washes, stickers, skull -> Pillow PNGs / `color` sources overlaid with `overlay` + `enable`/fade; grade with ref 01's reference ffmpeg chain.
- One encode: h264 CRF <= 18, `yuv420p`, AAC 192k 48 kHz.

## References and studying new material
- `references/01_ishowspeed_clip_style.md`: target look (canvas, captions, accents, grade, QC). Wins on all style questions.
- `references/02_eddie_claude_clipping_tutorial.md`: Eddie | AI's Claude clipper (https://youtu.be/IY08-3TS2o8): hook-first/payoff picking, hook types, /10 ranking, 3-8 candidates, title + post caption, shot-cut reframe reset, output layout, cached re-edits. Wins on workflow and picking; its NOT ADOPTED list shows conflicts with ref 01.
- **New reference shorts** (needs a clone of the repo; `analysis/` is not part of the installed skill folder): download them, run `<python> analysis/tools/extract_ref.py <video.mp4> <outdir>` (metadata, cut times, 1 fps frame grid, luma/sat/sharpness stats, transcript), write the study to `analysis/refs/`, then distil the rules into `references/NN_<topic>.md` (what the editor does, timings, caption style, tools, and the rule it implies for this pipeline).
- **New tutorials:** one `references/NN_<topic>.md` per video, raw notes in `analysis/tutorials/`.
