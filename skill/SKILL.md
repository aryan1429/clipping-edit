---
name: clipping-edit
description: Use when the user gives a YouTube link (podcast, stream, interview, long video) and wants short-form clips cut from it - finding the best/viral moments, reframing to vertical with face tracking, animated captions, hooks, zooms and SFX - or shares clipping tutorial links to study. Covers download, transcription, highlight scoring, face-tracked reframe, caption styling, render and review.
---

# Clipping edit

Long video -> best moments -> finished short clips. Learnings repo: https://github.com/aryan1429/clipping-edit (private, local clone `C:/Users/aryan/clipping-edit`; copy this skill into `skill/` and push after every new learning).

## Status
2026-10-31: style spec = references/01_ishowspeed_clip_style.md (READ FIRST; it overrides the defaults below). User hard rules: final file <= 60 s (assert <= 59.5 s), face tracking always on, colour correction must make it sharper, brighter, more colourful (measured vs source). Python: run with `-P` (not `-I`), PYTHONIOENCODING=utf8, feed faster-whisper a numpy array.

## Tools on this machine
- Python: `C:/Users/aryan/AppData/Local/Python/pythoncore-3.14-64/python.exe` (yt_dlp, faster_whisper, cv2, numpy, torch present; no mediapipe)
- ffmpeg: `imageio_ffmpeg.get_ffmpeg_exe()`
- GPU: RTX 3050 laptop, 4 GB (faster-whisper small/medium int8 fits)
- GitHub: no gh CLI; API calls use the git credential manager token; network needs sandbox disabled

## Pipeline (default)
1. Download: yt-dlp best mp4 + subtitles if present, into its own folder per job.
2. Transcribe: faster-whisper with word timestamps -> transcript.json.
3. Pick moments: score transcript windows; total 35-55 s, never > 60 s for a strong hook in the first 3 s, a self-contained payoff, emotion/controversy/humor; cut on sentence boundaries; list candidates with timestamps + reason, best first.
4. Reframe to 3:4 1080x1440 60 fps (ref 01; 9:16 only on request): detect faces per frame, track the active speaker, smooth the crop path (no jitter), hard switch on speaker change; split-screen when two people talk fast.
5. Captions (ref 01): ASS via libass burned in the same ffmpeg pass as crop+grade; Montserrat Black ALL CAPS, 2-4 word chunks building word by word, white + 1-3 coloured keywords, centred ~50% height, moved if over the face.
6. Polish (ref 01): hook = strongest line from frame 0 (no banner), music full from frame 0, accents (flash/whip + unique SFX) every ~6-8 s, freeze-frame reaction ending; grade = eq/vibrance/unsharp + light glow, verify luma/sat/sharpness gains.
7. Render 1080x1440 h264 + AAC, then review frames (face in frame, captions synced, no cut mid-word) and fix before delivery.

## References
Tutorial studies go in `references/NN_<topic>.md` (one per tutorial video): what the editor does, timings, caption style, tools, and the rule it implies for this pipeline.
