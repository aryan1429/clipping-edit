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
| Caption layout, safe areas (never off-screen), face-clear placement, caption pixel gate | ref 07 |
| Cut detection, reframe resets, accent timing | ref 04 §2 |
| Face tracking, crop path, camera stabiliser (smooth / steady / lock), two-person framing, framing and jitter gates | ref 08 |
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
| Face tracking | Always on for speaking shots (no blind centre crop); only deliberate wide action shots holding all subjects are exempt; camera `smooth` (`steady` for handheld), `scripts/face_track.py`, ref 08 |
| Grade | Must measurably beat the source on the same frames: mean luma +10%, median saturation +25%, Laplacian sharpness x1.4 |
| Canvas | 3:4 1080x1440, 60 fps (30 if the source is under 50 fps); 9:16 1080x1920 on request |
| Ending | Clean hard cut right after the payoff. Meme freeze + skull emoji only when the moment is a comedic fail / "no way" reaction that fits |
| Clip count | Show all 3-8 candidates; render the top 3 scoring >= 7/10, always at least #1 |
| Captions | Every word inside the canvas's safe area on every frame: `scripts/captions.py` lays out, `scripts/caption_gate.py` checks the pixels (ref 07) |
| Editing tool | EffectCraft when installed; otherwise ffmpeg + ASS/libass + Pillow |
| SFX | One per accent, each a different variant (never reuse one sample) |
| Music bed | Instrumental, mood-matched, licence-safe (CC0 / PD / CC BY / royalty-free; never NC, ND or SA) from `scripts/find_music.py`; credit line in `captions.md` when the licence needs one |

## Setup / preflight
Run `<python> <skill dir>/scripts/preflight.py` (the skill dir is the folder holding this SKILL.md, e.g. `~/.claude/skills/clipping-edit`; in a repo checkout it is `skill/`). It prints a status table and a `PREFLIGHT_JSON {...}` line with resolved paths; exit 1 means a required piece is missing.
- **Required:** Python 3.9+ with `yt_dlp`, `faster_whisper`, `cv2` (opencv-python), `numpy`, `PIL` (pillow); ffmpeg. Install: `<python> -m pip install yt-dlp faster-whisper opencv-python numpy pillow imageio-ffmpeg` (same list as the repo's `requirements.txt`).
- **Optional:** CUDA GPU, EffectCraft CLI, ffprobe, Montserrat Black font, YuNet face model (OpenCV Zoo `face_detection_yunet_2023mar.onnx`, needed by `face_track.py`), `scipy` and `matplotlib` (`face_track.py` degrades without them) (`torch` only as a second CUDA probe; faster-whisper does not need it). For music: a local music folder with a `licences.json` manifest, and optionally `JAMENDO_CLIENT_ID` (free key) so `find_music.py` can also search Jamendo (ref 06).

### Tool discovery (never hard-code paths)
- **Python:** the first of `python3`, `python`, `py -3` on PATH.
- **ffmpeg:** `ffmpeg` on PATH, else `imageio_ffmpeg.get_ffmpeg_exe()`. ffprobe may be absent with the imageio build; then read durations with `ffmpeg -i` or cv2.
- **GPU:** faster-whisper on CUDA (`int8_float16`) if available, else CPU `int8`. `small` fits ~4 GB VRAM; `medium` for better accuracy on bigger GPUs; CPU is fine for sources under ~30 min.
- **EffectCraft CLI:** env var `EFFECTCRAFT_CLI`, else `effectcraft-cli` on PATH. Not found -> fallback editing path.
- **Font:** Montserrat Black from the OS font dirs (Windows `Fonts`, macOS `~/Library/Fonts` + `/Library/Fonts`, Linux `~/.fonts`, `~/.local/share/fonts`, `/usr/share/fonts`, or `fc-match`) or env `CLIP_FONT` (path to the .ttf); fallback Montserrat ExtraBold, then Arial Black. `captions.py` exits 1 when the font it lays out with is not the one libass will draw (a fallback font is wider and pushes words off-screen).
- **Face model:** `--model`, env `CLIP_YUNET_MODEL` (a missing file is an error), `./models`, `./models/yunet`, the cwd, `<skill>/models`, `~/models/yunet`, `~/models`, `~/.cache/opencv_zoo` (preflight reports it as `yunet_model` and test-loads it).

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
   - Face track + stabilised camera (ref 08): `scripts/face_track.py run clips/NN/cut.mov --workdir clips/NN/face --size <canvas> --audio clips/NN/dialogue.wav --cut-frames <splice frames> [--jump-cuts F,..] [--subject auto|group|speaker] [--mode smooth|steady|lock] --render` -> `clips/NN/face/path.json` (per-frame crop + EffectCraft Position/Scale keys), `qc/face_track_path.png`, `preview.mp4`. Needs the YuNet .onnx (preflight `yunet_model`).
   - Cuts: `run` runs `scripts/cuts.py` on `cut.mov` itself (hard/soft cuts reset; flashes and fast moves do not; ref 04 §2) and merges it with `--cuts` / `--cut-frames` (the cut list's splice frames, already in edit frames). Never pass `cuts.py --start/--end` source-window frames unremapped. Same-camera joins go to `--jump-cuts` (scale 4-10 %, face kept in place). The camera resets and snaps at each, and at a hand-off to another face; it never pans across a cut.
   - Camera: `smooth` by default (holds still inside an 8 % W dead zone; eased pans planned offline, so no lag and no jitter); `steady` for handheld/IRL footage (camera shake cancelled); `lock` pins the face in place. If lock/steady fail their jitter gates (fast action, face at the source edge), use smooth. One crop size per shot (face 24 % H, upscale <= 2).
   - Two people: a two-shot that fits the canvas is framed as a group automatically; when it does not (usual for 9:16 of a 16:9 two-shot), `--subject speaker --audio clips/NN/dialogue.wav` cuts between speakers. Never a split screen or two half faces.
   - Gate: `face_track.py qc` exits 0 (face bbox + 5 % margin inside the crop on every frame, wide shots included; no tracked face lost; 0 pans across cuts; camera oscillation per 0.5 s window; for lock/steady the face jitter vs flow and in the rendered preview; jump-cut anchor; framing medians per ref 05 §1). Push-ins go on a parent and are re-checked on the composed transform (ref 04 §2 rule 6).
5. **Captions (ref 01 section 3; ref 07).** Montserrat Black ALL CAPS, 2-4 word chunks building word by word, white + 1-3 semantic keyword colours, centred at ~50% height, moved off the face (9:16 low: block bottom on the UI band, y 1330 of 1920; else high or any clear height).
   - Never hand-place caption text. Write the token file (ref 04 §1 rule 1 + output-second times, `c`, `brk`, `type` for typed stage directions, `shadow` for a chunk's shadow opacity), then `scripts/captions.py --tokens clips/NN/tokens.json --canvas WxH --fps F --frames N --faces clips/NN/face/path.json --ass clips/NN/captions.ass --layout clips/NN/captions_layout.json`.
   - It measures every word with the real font, including stroke, shadow, glow and the entrance scale, re-chunks so every line fits the safe area for the canvas's aspect ratio (9:16 band y 168-1330 + side margins and the right action rail; 3:4, 1:1 and 16:9 margins), and keeps every chunk off the faces (face tracks on another fps are remapped). Only a lone over-wide word scales down, with a warning; no ink ever leaves the safe area.
   - Exit 1 = a font or glyph problem, or a chunk that cannot avoid a face: fix it, never bypass it.
   - Path B burns with the layout's `burn` block (ffmpeg cwd = `burn.cwd`, `-vf <burn.filter>`, ref 03 §4 rule 8). Path A builds one text layer per word from the layout JSON (`em_px`, `baseline_center`, `appear_f`/`full_f`/`end_f`).
6. **Polish (ref 01).** **Music bed (ref 06):** `scripts/find_music.py --mood <hype|tense|funny|emotional|chill|epic|inspiring, from the transcript> --clip-s <len> --dialogue clips/NN/dialogue.wav --library <music folder> --choose --out-dir clips/NN` writes `bed.<ext>` + `music.json`. Its `bed` block goes into `audio_plan.json` and its `attribution` into `captions.md`. On exit 1, follow its `hints`. Never put trending or chart songs in the exported MP4. Hook = strongest line from frame 0 (no banner); music full from frame 0; accents (flash/whip + unique SFX) every ~6-8 s; ending per the Defaults table; grade the footage only, under accents and captions (ref 04 §3), then verify the gains with `scripts/grade_gate.py`. Accents start at full peak on their cause frame; each SFX peak lands on accent frame + 1 (ref 04 §2, ref 03 §3). Audio: `scripts/mix_audio.py` (static gain to -14 LUFS, bed at its strongest section, word-timed duck -10 dB with 20 ms / 300 ms ramps, limiter last; ref 03 §3).
7. **Edit and render** (see Editing paths below), h264 + AAC.
   - Output: `raw/NN-slug.mp4` (reframed only) and `edited/NN-slug.mp4`.
   - Log one line per clip: `ok NN-slug.mp4 dur:XX.Xs accents:N captions:N`.
   - Finish with `scripts/finalize_mux.py`: the mix is fitted to the decoded frame count, AAC is encoded once, true peak is <= -1.0 dBTP after the AAC, then copy-mux with BT.709 tags and faststart, the delivery gate, and an atomic promote. Never `-shortest`.
   - Gates before delivery: ref 01's QC checklist plus ref 05 §1 (decoded frames, `cuts.py --plan` events vs plan, A/V offset, black/freeze/frame 0, framing medians), ref 04's caption and grade gates and ref 03 §3's audio gates. Caption gate (ref 07 §4): `scripts/caption_gate.py --ass clips/NN/captions.ass --layout clips/NN/captions_layout.json --qc qc/NN` (path B), or `--video <caption-only render> --layout ...` (path A, every frame), then `--video edited/NN-slug.mp4 --clean qc/NN/grade.mp4 --layout ... --exclude <accent spans>`; any P0 (`outside_safe`, `edge_clipped`, `missing_word`, `off_frame`, `face_cover`, `font_fallback`, ...) blocks delivery; read `qc/NN/caption_gate_sheet.png`. Face gate: `face_track.py qc --video` on the final crop path and preview (ref 08). Open the review sheets in `qc/NN/`; fix every P0 before delivery.
   - Deliver the paths, the candidate table and `captions.md` (title and post caption per clip).
8. **Re-edits** (for example "under 30 s, no SFX, blue keywords, 9:16"): reuse the cached audio, transcript, `clips.json` and face tracks. Write the change into the clip's plan as absolute values. Re-run only the stages after the changed field (SFX or music: new mix + `-c:v copy` mux), never the download or ASR. Version every render; "undo" re-delivers the previous version (ref 05 §2).
- **Lessons:** log each correction, QC fail and fallback; a detail seen in 2+ jobs becomes a rule or QC check (ref 05 §2).
- **Benchmark:** a 1h43 source gives a ranked list plus 3 clips in <= 40 min end to end on a mid-range GPU (CPU-only takes longer for ASR).

## Editing paths
**A. EffectCraft (default when `EFFECTCRAFT_CLI` / `effectcraft-cli` is found).** Open-source After Effects-style editor driven by script/CLI.
- **Python/ffmpeg prep:** download, transcribe, pick, `splice.py` cuts frame-exact video-only segments from the source through `norm_vf` (seek early + trim, seekable CFR `.mov`; ref 03 §2, §4) plus one pre-rolled PCM dialogue stem, `face_track.py` crop path (stabilised, reset at cuts; ref 08), `captions.py` caption layout with keyword colours (ref 07), accent/SFX timeline, audio mix (dialogue -14 LUFS + ducked music + SFX).
- **EffectCraft edit:** canvas-size comp; source layer with the Position/Scale keyframes from `path.json`'s EffectCraft block (that is the face tracking); per-word text layers placed from `captions_layout.json` (`baseline_center` + `em_px`, frames `appear_f`..`end_f`, entrance scale about `anchor`; no paragraph boxes or auto-size; stroke + shadow + keyword glow), checked with `caption_gate.py --video` on a caption-only render; flashes/whips, sticker PNGs; grade on an adjustment layer (Brightness/Contrast, Hue/Sat or Vibrance, Sharpen, glow from a blurred Screen copy). Adjustment-layer blend modes may be ignored; composite the glow with a precomp or CC Composite.
- **Render:** high bitrate (>= 30 Mbps), in parts if memory runs out (frames == sum of parts); then `finalize_mux.py` (one AAC encode, copy-mux, colour tags per ref 03 §4; check EffectCraft's output colour once per version).
- Anything EffectCraft cannot draw (e.g. colour emoji) -> Pillow PNG imported as a footage layer.

**B. Fallback: ffmpeg + ASS/libass + Pillow (no EffectCraft).**
- Crop path -> `face_track.py render` (per-frame crop + scale piped to ffmpeg), or ffmpeg `crop`/`scale` driven from `path.json`.
- Captions -> `captions.py` writes the ASS (per-word `\an5\pos` events, WrapStyle 2, PlayRes = canvas, ScaledBorderAndShadow) and copies the font to `<ass folder>/fonts`; burn with the layout JSON's `burn.filter`, ffmpeg cwd = `burn.cwd`.
- Flashes, washes, stickers, skull -> Pillow PNGs / `color` sources overlaid with `overlay` + `enable`/fade; grade with ref 01's reference ffmpeg chain.
- Tag BT.709 before `ass`/`overlay`/`color` (untagged frames use BT.601). One encode: libx264 `-preset medium -crf 16 -bf 0`, `yuv420p`, BT.709 flags; then `finalize_mux.py` (ref 03 §4).

## References and studying new material
- `references/01_ishowspeed_clip_style.md`: target look (canvas, captions, accents, grade, QC). Wins on all style questions.
- `references/02_eddie_claude_clipping_tutorial.md`: Eddie | AI's Claude clipper (https://youtu.be/IY08-3TS2o8): hook-first/payoff picking, hook types, /10 ranking, 3-8 candidates, title + post caption, shot-cut reframe reset, output layout, cached re-edits. Wins on workflow and picking; its NOT ADOPTED list shows conflicts with ref 01.
- `references/03_hyperframes_media_pipeline.md`, `04_hyperframes_captions_framing_grade.md`, `05_hyperframes_qc_workflow.md`: mechanics and gates from a study of HeyGen HyperFrames (Apache-2.0). See "What to read when".
- **Scripts** (`scripts/`, each prints one JSON object; exit 0 ok, 1 gate failed, 2 bad input; ffprobe optional): `probe_source.py`, `cutlist.py`, `splice.py`, `cuts.py`, `mix_audio.py`, `finalize_mux.py`, `grade_gate.py`, `find_music.py`, `captions.py`, `caption_gate.py`, `face_track.py` (self-tests: `captions.py --self-test`, `caption_gate.py --self-test`, `face_track.py selftest`), with shared helpers in `cliplib.py`. Run with `<python> -P`. Tests live in the repo's `tests/`.
- `references/06_background_music.md`: choosing a bed (mood → BPM and energy, no vocals under speech, a strong entry from frame 0, phone-speaker low end), sources ranked by safety with verified terms, the licence policy (CC 4.0: syncing music to video makes Adapted Material, so no ND or SA; no NC), Content ID and in-app-sound caveats, and the credit-line format.
- `references/07_caption_safe_area.md`: why captions left the screen (16 reproduced causes: unmeasured widths, halo not counted, lone long words, two-line low blocks, no horizontal clamp, 9:16 numbers on other canvases, libass font fallback, PlayRes mismatch, ...), safe areas per aspect ratio, the measured fit, face-clear placement, the keyword guard per chunk, typed stage directions, the ASS timing fix, the Windows-safe burn filter, and the pixel gate (every word drawn, safe area, faces, length). Implemented by `scripts/captions.py` and `scripts/caption_gate.py`.
- `references/08_face_track_stabilizer.md`: face detection (YuNet + LK flow), tracking, subject choice (auto/group with a fit test, speaker, hand-offs), detector + flow fusion, the L1-optimal smooth camera and steady/lock face stabilisation, resets at cuts, EffectCraft keys, the preview render and the gates (face/margin, face_lost, oscillation, flow- and output-measured face jitter, jump cuts), with tested numbers. Implemented by `scripts/face_track.py`.
- **New reference shorts** (needs a clone of the repo; `analysis/` is not part of the installed skill folder): download them, run `<python> analysis/tools/extract_ref.py <video.mp4> <outdir>` (metadata, cut times, 1 fps frame grid, luma/sat/sharpness stats, transcript), write the study to `analysis/refs/`, then distil the rules into `references/NN_<topic>.md` (what the editor does, timings, caption style, tools, and the rule it implies for this pipeline).
- **New tutorials:** one `references/NN_<topic>.md` per video, raw notes in `analysis/tutorials/`.
