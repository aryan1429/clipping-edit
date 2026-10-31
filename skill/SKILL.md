---
name: clipping-edit
description: Use when the user gives a YouTube link (podcast, stream, interview, long video) and wants short-form clips cut from it - finding the best/viral moments, reframing to vertical with face tracking, animated captions, hooks, zooms and SFX - or shares clipping tutorial links to study. Covers download, transcription, highlight scoring, face-tracked reframe, caption styling, render and review.
---

# Clipping edit

Long video -> best moments -> finished short clips. Learnings repo: https://github.com/aryan1429/clipping-edit (private, local clone `C:/Users/aryan/clipping-edit`; copy this skill into `skill/` and push after every new learning).

## Status
2026-10-31: style spec = references/01_ishowspeed_clip_style.md (READ FIRST; it overrides the defaults below). User hard rules: final file <= 60 s (assert <= 59.5 s), face tracking always on, colour correction must make it sharper, brighter, more colourful (measured vs source). Python: run with `-P` (not `-I`), PYTHONIOENCODING=utf8, feed faster-whisper a numpy array.

## Tools on this machine
- Editing software: **EffectCraft** (CLI, by script; see ref 01 'Editing tool' for the Python-prep / EC-edit / ffmpeg-mux split)
- Python: `C:/Users/aryan/AppData/Local/Python/pythoncore-3.14-64/python.exe` (yt_dlp, faster_whisper, cv2, numpy, torch present; no mediapipe)
- ffmpeg: `imageio_ffmpeg.get_ffmpeg_exe()`
- GPU: RTX 3050 laptop, 4 GB (faster-whisper small/medium int8 fits)
- GitHub: no gh CLI; API calls use the git credential manager token; network needs sandbox disabled

## Pipeline (default)
One-line trigger ("clip this video: <url>"): run the whole job without asking questions. Ref 01 rules on style; ref 02 rules on workflow and picking.
0. **Preflight.**
   - Check the imports (yt_dlp, faster_whisper, cv2, numpy), ffmpeg and CUDA.
   - Note rights: is the source the user's own channel or third-party?
   - Create the job folder `output/<slug(title)[:35]>-<videoId>/`.
1. **Download.**
   - Fetch audio-only first so ASR can start, then the best mp4 (plus subtitles if present).
   - On a bot block, retry with `--cookies-from-browser chrome`.
2. **Transcribe.**
   - faster-whisper with word timestamps (CUDA int8), run in the background with an ETA given. Output: `transcript.json`.
   - Also write `transcript_lines.txt`: `mm:ss  SPEAKER: sentence`. Split at punctuation or at gaps over 0.6 s. Label speakers by diarization or by LLM inference.
3. **Pick moments (ref 02).** The LLM reads the whole `transcript_lines.txt`.
   - **Candidate JSON:** `{rank, score 1-10, start, end, hook_line, hook_type, hook_speaker, payoff_line, title, post_caption, reason}`, saved to `clips.json`.
   - **Hook type:** `hook_type` is one of contrarian / surprising_fact / novel_claim / story_opener. Reject a candidate without one.
   - **Start:** exactly on the hook line (first word minus 0.05 s). Warm-up, filler and ramble before it are cut. The hook may be the other speaker's question. The premise must be spoken by t ≤ 2.5 s.
   - **End:** on the payoff line (last word plus 0.15 s). The clip must be understandable to a total stranger with zero context.
   - **Length:** ≤ 59.5 s after dead-air removal, target 35-55 s. If the payoff falls past 60 s, use an earlier payoff, cut the middle tangent, or drop the candidate.
   - **Count and spread:**
     - 3-8 non-overlapping candidates, about 1 per 12-15 min of source.
     - Spread across the source, with no more than 50% from one third of it.
     - Ranked by score, descending.
   - **Copy for each candidate:**
     - title: Title Case, 4-7 words, curiosity or contrast phrasing
     - post caption: 1-2 sentences plus 3 hashtags
   - **Always show the user the table** `# | Title | Score | Hook type | Length | Opens with`.
   - **Default renders:** the top 3 with score ≥ 7, always at least #1. "best clip only" renders #1 only; "all" renders every candidate.
4. **Reframe to 3:4 1080x1440, 60 fps** (ref 01; 9:16 only on request).
   - Detect faces per frame and track the active speaker.
   - Detect camera cuts (ffmpeg `scene` > 0.3). At each cut, reset the smoother and snap to the new shot's active face. Never pan across a cut.
   - Within a shot, smooth per ref 01: EMA, 8% W dead-zone, ≤ 3% W/s, no jitter.
   - On a same-camera jump cut, vary the crop scale by 4-10% (face height stays at 20-30% H).
   - Two people: use a wider crop that holds both. Never use a split screen (ref 01).
   - Gate: the face bbox plus a 5% margin is always inside the frame, including after any push-in or zoom.
5. Captions (ref 01): built as text layers in EffectCraft (user's editing software, ref 01 'Editing tool'); Montserrat Black ALL CAPS, 2-4 word chunks building word by word, white + 1-3 coloured keywords, centred ~50% height, moved if over the face.
6. Polish (ref 01): hook = strongest line from frame 0 (no banner), music full from frame 0, accents (flash/whip + unique SFX) every ~6-8 s; ending = normal clean hard cut after the payoff by default, meme freeze + 💀 only when the moment fits (not every clip); grade = eq/vibrance/unsharp + light glow, verify luma/sat/sharpness gains.
7. **Render** 1080x1440 h264 + AAC.
   - Output: `raw/NN-slug.mp4` (reframed only) and `edited/NN-slug.mp4`.
   - Log one line per clip: `ok NN-slug.mp4 dur:XX.Xs accents:N captions:N`.
   - Review the frames (face in frame, captions synced, no cut mid-word) and fix before delivery.
   - Deliver the paths, the candidate table and `captions.md` (title and post caption per clip).
8. **Re-edits** (for example "under 30 s, no SFX, blue keywords, 9:16"): reuse the cached audio, transcript, `clips.json` and face tracks. Re-run steps 4-7 only, never the download or ASR.
- **Benchmark:** a 1h43 source gives a ranked list plus 3 clips in ≤ 40 min end to end.

## References
Tutorial studies go in `references/NN_<topic>.md` (one per tutorial video): what the editor does, timings, caption style, tools, and the rule it implies for this pipeline. Raw studies go in `C:/Users/aryan/clipping-edit/analysis/`.
- `references/01_ishowspeed_clip_style.md`: the user's target look (canvas, captions, accents, grade, QC). It wins on all style questions.
- `references/02_eddie_claude_clipping_tutorial.md`: Eddie | AI's Claude clipper (https://youtu.be/IY08-3TS2o8), covering hook-first/payoff picking, hook types, the /10 ranking, 3-8 candidates, per-clip title and post caption, shot-cut reframe reset, the output layout and cached re-edits. It wins on workflow and picking. Its NOT ADOPTED list shows where it conflicts with ref 01.
