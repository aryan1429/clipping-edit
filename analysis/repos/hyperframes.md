# HyperFrames repo study: raw notes

- **Source:** https://github.com/heygen-com/hyperframes (Apache-2.0, (c) 2026 HeyGen, Inc.). Studied at commit `8c22ddb` (2026-11-01, CLI v0.8.226).
- **What it is:** an open-source framework that renders HTML/CSS/GSAP compositions to MP4 by seeking each frame in headless Chrome and encoding with ffmpeg. It ships agent skills (`/hyperframes`, `/media-use`, `reverse-any-video`, ...), a CLI (`measure`, `lint`, `check`, `snapshot`, `render`, `normalize-audio`, `transcribe`) and about 450 registry blocks.
- **Why it matters here:** HyperFrames is not our renderer. Its media tooling solves problems every clipping pipeline hits: frame-exact transcript cuts, click-free splices, ducking from word timings, loudness and true-peak gates, BT.709 tagging, HDR/VFR intake, cut detection, caption timing contracts, review sheets and agent-skill structure.
- **Method:** 9 parallel readers (captions, transcript-cutting, audio, grade-look, measure-reverse, motion-editing, render-qc, skill-design, plus a keyword sweep for uncovered material) read 50-90 files each and returned evidence-backed learnings (file + lines + verbatim quote). 9 synthesizers deduped them into the skill references. Independent verifiers then re-checked every cited claim and tested every ffmpeg command on synthetic media.
- **Distilled rules:** `hyperframes_draft_sections.md` in this folder (9 sections, each marked verified or pending). After reconciliation they become `skill/references/03_hyperframes_media_pipeline.md`, `04_hyperframes_captions_framing_grade.md` and `05_hyperframes_qc_workflow.md`. This file is the raw reader output and the index into the HyperFrames source; items here are unverified unless a reference cites them.

## Where HyperFrames keeps what (most-cited places)

| Path | Citations | Topics |
|---|---|---|
| `skills/media-use` | 117 | accents-motion, audio, captions, download, grade, pick, preflight, qc-review, re-edit-cache, render-encode, skill-structure, transcribe |
| `packages/cli/src/measure` | 102 | accents-motion, analysis-tooling, captions, download, grade, qc-review, re-edit-cache, reframe, render-encode, skill-structure, transcribe |
| `skills/hyperframes` | 100 | accents-motion, audio, captions, other, pick, qc-review, re-edit-cache, reframe, render-encode, skill-structure, transcribe |
| `packages/engine/src/services` | 62 | audio, download, grade, re-edit-cache, render-encode |
| `packages/cli/src/media-use` | 59 | analysis-tooling, audio, captions, grade, pick, qc-review, re-edit-cache, render-encode, skill-structure, transcribe |
| `docs/guides` | 38 | accents-motion, audio, captions, download, grade, other, pick, qc-review, re-edit-cache, render-encode, transcribe |
| `packages/cli/src/commands` | 36 | accents-motion, analysis-tooling, audio, captions, download, qc-review, render-encode |
| `packages/cli/src/whisper` | 32 | re-edit-cache, render-encode, transcribe |
| `registry/components` | 32 | accents-motion, captions, reframe, transcribe |
| `.agents/skills` | 27 | accents-motion, captions, other, pick, qc-review, re-edit-cache, reframe, render-encode, skill-structure, transcribe |
| `skills/reverse-any-video` | 26 | analysis-tooling, captions, pick, qc-review, reframe, render-encode, skill-structure, transcribe |
| `packages/producer/src/services` | 26 | audio, qc-review, render-encode |
| `docs/prompting` | 23 | analysis-tooling, captions, grade, qc-review, re-edit-cache, render-encode, skill-structure |
| `packages/cli/src/utils` | 22 | audio, captions, pick, qc-review, render-encode, skill-structure |
| `packages/engine/src/utils` | 22 | download, grade, qc-review, render-encode, skill-structure |
| `packages/cli/src/audio` | 18 | accents-motion, analysis-tooling, audio, pick, qc-review |
| `skills/hyperframes-cli` | 16 | captions, other, preflight, qc-review, re-edit-cache, render-encode, skill-structure |
| `packages/studio-server/src/helpers` | 14 | audio, download, grade, qc-review, reframe, render-encode |
| `registry/blocks` | 12 | accents-motion |
| `packages/core/src/audioCarve.ts` | 11 | audio, qc-review |
| `docs/packages` | 11 | accents-motion, analysis-tooling, audio, pick, qc-review |
| `packages/core/src/audioAnalysis.ts` | 11 | accents-motion, audio, qc-review |
| `packages/core/src/runtime` | 9 | analysis-tooling, grade, re-edit-cache |
| `scripts` | 9 | skill-structure |
| `packages/core/src/colorGradingBake.ts` | 6 | analysis-tooling, grade |
| `docs/reference` | 5 | audio, grade |
| `packages/core/src/audioLeveller.ts` | 5 | audio |
| `packages/core/src/audioFxPresets.ts` | 4 | audio |
| `packages/studio/src/components` | 4 | qc-review |
| `packages/core/src/hdrToneMap.ts` | 3 | download |

## Reader summaries

### captions

HyperFrames keeps its caption knowledge in three layers. The first is agent references: captions.md, the media-use authoring/motion/transcript-handling files, the captions-overlay doctrine and vertical.md. They give numeric rules for word grouping, placement, platform safe bands, legibility and transcript cleanup. The second is about 17 registry caption components. Their JS does deterministic grouping (3-4 words; break at a 0.1 s pause or punctuation; two balanced lines measured with the real font x 1.14). It also sets entrance leads that end on the spoken word, hold/exit timing and seeded keyword colouring. The third is CLI code. It covers ASR word normalisation (token joining, zero-duration interpolation) and repair of speech the ASR silently skipped (energy-gap re-decode). It adds a display/spoken token aligner with MISMATCH gating, and a transcript-cut compiler that keeps cuts frame-exact and gap-free through splices (PCM intermediates, 6-decimal seeks, 0.15 s silence pads). It also has measurable audits: WCAG contrast sampled inside the text box (stroke counts), reading-time and type-size floors, caption-zone collisions and a caption hard-kill lint. HyperFrames' caption STYLE defaults conflict with the measured IShowSpeed style and are rejected: karaoke baseline, audio-reactive pulses, bounce, style cycling, quick exit fades and enlarged accent words. What the clipping skill lacks is the correctness machinery. That means timing contracts through LLM cleanup and cuts, transcript QC, sync/presence/legibility gates, the 9:16 UI band, and face-avoidance measured over each chunk's window.

*Gaps:* This was a read-only study. Nothing in the checkout was executed, so no HyperFrames component was rendered or timed; all numbers are as written in its code and docs.

Read only by grep or partially:
- layout-audit.browser.js (3096 lines) and checkBrowser.ts (the contrast collection wrapper).
- The studio caption parser, store and hooks.
- contrastMotion.ts beyond line 80.
- Release notes, which were grepped rather than read.

Not studied:
- HeyGen paid transcription and diarisation (--speakers), and the TTS paths.
- extract-audio-data.py (audio-reactive captions, a rejected style).

Release notes mention a data-driven 'caption-data runtime' and an 'emphasis heuristic' for caption-highlight and caption-editorial-emphasis. This checkout's component files do not contain them (they still use hand-authored RAW_GROUPS/BLOCKS), so those heuristics could not be read.

HyperFrames gives no width for the 9:16 right-hand action rail and no measured caption sync tolerance. The 0.87 W / 74% W rail estimate, the ±frame sync gates, the 1.5 s missing-caption threshold and the speech-rate bands are my proposals.

From general knowledge, not checked in this session:
- libass/ffmpeg behaviour cited in hints: collision shifting of overlapping events without \pos, centisecond ASS times, Start <= t < End, frame-time truncation in the ass filter.
- That EffectCraft centres text strokes like AE.
- How YouTube/TikTok letterbox 3:4 uploads.

The faster-whisper parameters cited (hotwords, initial_prompt, hallucination_silence_threshold, clip_timestamps, language_detection_segments, vad_filter default False) were confirmed only by reading the installed faster_whisper 1.2.1 source, not by running it. Whisper hallucination heuristics (compression_ratio > 2.4, avg_logprob < -1.0 with no_speech_prob > 0.6) are standard whisper practice, not HyperFrames evidence.

### transcript-cutting

HyperFrames' transcript-cutting stack has three layers. (1) Local ASR: Parakeet-TDT 0.6B v3 (parakeet-mlx on Apple Silicon, an int8 ONNX export through sherpa-onnx elsewhere, Windows x64 included) with a whisper.cpp fallback. Output is normalised to [{id, text, start, end}] words. A dropped-speech repair loop works on 60 s windows split at the quietest point and re-decodes energy-checked token gaps with 0.5 s pads. Written whisper hallucination and quality rules sit on top. (2) media-use's transcript-cut 'compiler' takes time ranges, inclusive word-index ranges, bare-token fillers and padded silence centres, then merges, inverts and filters them (0.2 s minimum) into kept segments. Those segments are cut with 6-decimal seeks into PCM .mov intermediates (CFR, a keyframe every second) with 30 ms splice ramps and a single AAC encode. Its tests pin the failure modes: frames off the grid, sparse keyframes, ~25 ms AAC-priming gaps per splice, and clicks. (3) Supporting pieces: ducking from word spans plus a spectral/level 'carve'; a pitch-preserving atempo speed-ramp baker; final-mux rules that keep the AAC priming edit list (otherwise the start shifts ~21 ms and the first frame shows black); and measure tools (a MAD jump-cut detector and a mouth-motion A/V-sync lag) that work as QC. Its guides insist on cutting before captioning. It has no J/L-cut, zero-crossing or freeze-frame implementation.

*Gaps:* This was a read-only study. No tests, CLIs or ffmpeg commands from the checkout were run. Figures such as ~25-35 ms of AAC priming per splice, the ffmpeg 7/8 behaviours, Parakeet's WER and speed claims, and the 0.26 s re-hear measurement are HyperFrames' own claims, not verified here.

The clone is shallow (50 commits), so the commits behind changelog fixes could not be diffed: #4179 (clicks/gaps), #5426 (frame precision), #5463 (repeated frames) and #3505 (AAC priming edit list).

packages/core/src/editing/ holds Studio edit-panel affordances (DOM capability flags) and has no cutting logic. packages/cli/src/media-use/lib/freeze.mjs 'freezes' downloaded assets into the media ledger; it is not a freeze-frame. The files studied contain no J/L-cut (split edit), zero-crossing snapping or freeze-frame implementation: splices are hard A/V cuts with 30 ms audio ramps, and 'J-cut' appears only as SFX-decay advice in the SFX manifest.

Only parts of the large files were read: packages/engine/src/services/audioMixer.ts lines 1-560, chunkEncoder.ts lines 880-915 and 1040-1075, videoFrameExtractor.ts lines 1165-1240, and the VFR probe in ffprobe.ts.

Several rules are my own adaptations, not HyperFrames code: frame-grid snapping of the cut list, the 0.08 s pads for 0.30-0.60 s gaps, the 0.2 s minimum removal, the remap plus re-ASR caption check, the differential A/V-sync gate and its mouth-ROI choice, pre-rolled duck ramps, the >50% sub-150 Hz bed flag, and the mid-file hallucination extension. faster-whisper option names (vad_filter, hallucination_silence_threshold, initial_prompt, hotwords) and the sherpa-onnx Python API come from general knowledge and should be checked against the installed versions.

### audio

HyperFrames treats audio as measure-then-write. Every level change is computed from the actual PCM and then baked into plain gain envelopes or filter chains: integrated LUFS and true peak via ffmpeg ebur128, windowed RMS for levelling and voice-vs-bed ducking, FFT band power to carve the bed where the voice sits, an Ellis-style DP beat tracker with Foote novelty sections for music structure, and 1 ms RMS 'moments' for where an SFX hits. Its render path is hardened against the ffmpeg failure modes our clipping mixer will hit: amix normalize/dropout scaling, s16 clipping of sums over unity, the -3 dB mono upmix, volume-expression overflow, AAC priming gaps and cold-start overshoot, and ±1 ms A/V length drift. It also enforces a true-peak ceiling of -1 dBTP measured after the AAC encode, with up to 3 correction passes. The authoring rules are short and numeric: in narrated pieces the voice is the clock; every SFX has a cause on screen and lands its peak one frame after the picture; hits sit 3-6 dB over the bed; repeated sounds rotate takes; social mixes land at -16 to -14 LUFS with true peak at or under -1 dBTP; and the delivery note says the sound was measured, not heard. For the clipping skill, the biggest wins are the mix and encode correctness rules, transcript-driven ducking checked by a measured voice-over-bed margin, SFX placed from their measured peaks out of a manifest-driven variant library, and an audio QC battery (post-encode LUFS/TP, clipping, silence, lip-sync lag). HF style preferences that differ from ref 01 are recorded as note_only or adopt_optional: the 2.4 s bed release, the ~15.6 dB voice-over-bed default, the 0.4 s bed fade-in, and SFX at volume 0.35 under everything.

*Gaps:* This was a read-only study and nothing was executed. Every constant and claimed measurement comes from source code, comments and docs, not from anything I reproduced. That includes the -3 dB mono rematrix, the ~25-35 ms AAC priming, the 4.5 dB AAC cold-start overshoot, the 0.6 / 1.2-1.7 dB true-peak limiter overshoot, the -33.8 vs -61.8 LUFS window gotcha, and the 2.4 s vs 1.6 s release preference.

Not read, or only skimmed:
- packages/core/src/audioFx.ts (effect registry, parameter ranges), audioAutomation.ts, audioGroups.ts, audioPitch.ts (the voicedShare used by the voice/music classifier).
- The offline FX renderer (engine audioFxRender.ts: the compressor, limiter and gate DSP).
- Most of audioMixer.ts (about 300 of 1974 lines read).
- packages/cli/src/audio/read/music.ts and stems.ts (bed and ambience reading, which depend on HeyGen's paid stems API).
- The `beats` CLI command itself.
- Studio UI audio code.
- Most test files (only duck.test.mjs read; audioRhythm.test.ts grepped).

Unavailable: the commit behind the 'clip-before-duck fix (55f852a72)' is only referenced in plans/audio-fx-presets.md.

Skipped as paid or out of stack: HeyGen music retrieval, TTS, Lyria/MusicGen generation.

Unverified ffmpeg facts in the implementation hints (my knowledge, to check on the installed build): av_strtod parsing a 'dB' suffix, the default of alimiter's 'level' auto-level, loudnorm's normalization_type and 192 kHz output.

Thresholds marked 'ours' were added to make HF's methods measurable and are not HF values: the 75th-percentile bed-entry rule, the 6 dB leveller trigger, the 0.10 s dead-air pad, the 20 ms duck pre-roll, and the mouth ROI = lower 40% of the face box.

### grade-look

HyperFrames grades footage with a display-referred Rec.709/SDR WebGL shader in a fixed order: exposure gain, masked shadows and highlights, black/white point, temperature/tint, contrast, skin-weighted vibrance, saturation, tonal wheels, PCHIP curves, hue curves, HSL secondaries, LUT, then an intensity mix. It runs the same pointwise math on the CPU to bake .cube LUTs for ffmpeg lut3d. Spatial finishing (grain, an aspect-aware vignette, a thresholded half-res bloom) runs after the colour stages, and the LUT bake refuses those stages. To diagnose footage it runs a side-effect-free ffmpeg signalstats sampler over 5 mid-interval frames. The sampler has explicit thresholds for underexposure, flatness, colour cast and clip risk at the 10th/90th percentiles, returns small bounded 'starting suggestions', and adds HDR/LOG warnings. HDR is recognised by transfer only (PQ/HLG) and tone-mapped with zscale+hable to explicitly converted, tagged BT.709 tv-range. Every encode and RGB/YUV conversion names its matrix, range and tags, and x264 runs with aq-mode=3 against banding. The skill layer corrects first and keeps changes minimal: grade groups per camera, bounded recipe seeds (Natural Portrait, Product Polish, UI Fidelity = no grade), before/after contact sheets read once, never reading .cube bodies, and explicit rejection checks (implausible or flattened dark skin, clipped highlights, bloom that fools clipping metrics). Its looks are much gentler than our IShowSpeed targets, so what transfers is measurement, colour-pipeline correctness and QC, not the looks themselves.

*Gaps:* This was a read-only study. Nothing in the checkout was executed (no ffmpeg, zscale, tonemap or lut3d runs), so every filter string is quoted from HF source and tests and has not been tested against this machine's ffmpeg. Whether the Windows or imageio-ffmpeg build ships zscale/libzimg is also unknown.

Coverage:
- Of the 4,340-line runtime shader, only these parts were read: primary grade, LUT sampling, grain, bloom (threshold and blur passes), vignette, dither and scanlines.
- Wheels, curves, hue curves and secondaries were taken from the CPU bake, which claims and tests parity with the shader; their GLSL was not read line by line.
- Stylized recipes (VHS, 8mm, CRT, halftone, ASCII, engraving, crosshatch) were skimmed or skipped as out of scope.

These points come from my own knowledge, not from HF evidence:
- yt-dlp prefers HDR by default, and the exact syntax of a dynamic_range=SDR filter.
- The option names of ffmpeg's h264_metadata bitstream filter.
- Whether ffmpeg's curves filter offers interp=pchip, and whether lut3d accepts gbrp16le.
- Which ffmpeg filters are RGB-only (vibrance, colorbalance, curves, lut3d) and which are YUV-only (eq, unsharp).
- The magenta cast from a screen blend in yuv420p. I computed it from the blend formula (+~10 code values on U and V at opacity 0.15) and did not test it.

EffectCraft unknowns: whether it can load .cube LUTs, whether it tags colour, what output range it writes, and whether adjustment layers can be scoped to the footage precomp.

HF's analyzer suggests blacks = +0.08 when shadows clip, which under its own black-point semantics darkens them further. That looks inverted, so it is not adopted.

These thresholds are my proposals and need calibrating on real clips:
- haze: p2 +6
- clipping: +1 pp in the face box, +3 pp globally
- skin hue drift: <= 5 deg
- vectorscope tolerance: +-12 deg
- dark skin: median V 110
- camera-group clustering: dU/dV 4, dY 15, face centre 0.15 W
- caption colour tolerance: +-8 per channel
- no-op stage: 0.5/255

Also noticed: in the clipping-edit repo, analysis/tools/extract_ref.py measures 'luma' as mean HSV V, 'sat' as mean S and 'sharp' as Laplacian variance at native resolution. Ref 01 states median HSV saturation and Laplacian at 720p, so the numeric targets may not be comparable until the metrics are unified.

### measure-reverse

HyperFrames' measure layer (packages/cli/src/measure + commands/measure, ported from HeyGen Studio's viral-clone tools) measures a reference video using only ffmpeg raw decodes and plain loops. Its cut detector compares each frame difference with a moving median of its neighbours, on 64x36 grey signatures. It finds same-angle punch-ins and jump cuts, and labels light flashes and whips/fast moves as not-cuts. Around it sit a grid event map (appear/disappear steps, local flashes, holds, sound onsets grouped into look-windows with frame strips that keep the frames around each onset), Haar face size bands and per-shot median framing gates, and a mouth-motion-vs-voice lag estimator with confidence levels and a -125/+45 ms gate. It also has look stats (luma, contrast, saturation, warmth, B/W share) with floors and tolerances, an ease fitter, and ink-based text metrics. `diff` scores a render against the original: SSIM per frame for the whole frame and a 4x4 grid of cells, missing content, cuts matched within ±1 frame, duration within ±1.5 frames, and sound offset found by onset cross-correlation (±1 frame). The robustness rules may matter most for us:
- probe and normalize VFR/HDR sources to a CFR SDR copy
- pick frames by index, seeking half a frame early
- decode audio on its own timestamps (aresample first_pts=0, because of an HE-AAC edit-list bug)
- write times as frame/fps rounded down

For clipping-edit the biggest gains are:
- Replace our ffmpeg scene>0.3 and HSV-histogram cut detection with the ported detector. The histogram version found 172 'cuts' on ref1 and missed jump cuts on ref3.
- Turn the QC lines that are now prose-only into measured gates: EDL-vs-output cuts, A/V sync, caption sync from pixels, per-shot framing medians, contrast and warmth in the grade gate.
- Review event strips instead of 1 fps samples, which miss 2-3-frame accents.

*Gaps:* This was a read-only study and nothing was executed, so no constant was re-validated on our material: the 60 fps 3:4 reference Shorts or podcast/stream sources. HyperFrames tuned these on its 24-30 fps rebuild benches. Several of their own thresholds are labelled provisional or 'to be calibrated': DEFAULT_MIN_MEAN, DEFAULT_MIN_CELL, sameLook. The Studio originals they were ported from (videoShots.mjs, viral-clone events.mjs/media.mjs, hf-media face_size/av_sync, look-stats.mjs, motion-energy.mjs) are not in the OSS repo.

Not studied in depth:
- the audio provider ladder (beat-this, API, Apple) behind events --map beats/bpm;
- the check command's craft audit and keepsMoving classifier (only the docs row for dead_stretch);
- snapshot and contact-sheet code;
- the paid HeyGen draft-timeline and generate paths;
- the second half of diff-people.test.ts (read only up to line 147 plus test names).

Proposed rules marked 'extension' are my inferences, not HyperFrames code: fps scaling of the frame-count constants, the whip-transition rule, the tint colour/opacity solve, FFT cross-correlation for hour-long sources, the band-passed speech envelope, the active-speaker picker, the static-face filter, the frozen-frame MAD < 0.1 cut-off, and the eye-line placement in the target face box. The quoted line ranges were checked against the files; the extract_ref.py failure counts come from our own analysis/refs notes.

### motion-editing

HyperFrames' motion layer is a set of measured defaults (motion.md, film.md, vertical.md, overlays.md) plus internal motion-doctrine / cut-the-curve / seam-craft skills that treat every cut as one continuous move (same axis, direction and speed, cut at peak velocity, a carrier handed across, no ping-pong), enforced by a numeric seam verifier that samples motion at cut ±1 frame and ±0.1 s. The registry ships parameterised primitives with real constants: a 0.55 s strip whip with a 16 px capped horizontal blur peaking at the switch frame and its SFX cue at peak velocity, an 11% / 1.2 s talking-head punch-in, a beat freeze-cut, freeze-frame dressing, and closed-form shader formulas for whip, radial zoom-blur and dip-to-white. Its CLI measure/check/snapshot tools are deterministic frame analysers: a soft-cut-aware shot detector that catches same-angle punch-ins ffmpeg's scene score misses, an ROI event detector (caption switches, flashes), an ease fitter, an A/V sync estimator, seam strips at ±0.2 s with a 360 px phone sheet, and craft thresholds. media-use's transcript-cut is a frame-exact cut compiler: 0.15 s word-edge pads, 0.2 s minimum segment, 30 ms splice fades, PCM audio in .mov intermediates, 6-decimal seeks and a keyframe every second. The style doctrine targets launch films, so its preferences on hard-cut share, punch-ins, whip length and music fade-ins conflict with the ref 01 viral-short measurements. Its timing math, seam mechanics, cut safety and QC tooling transfer directly to the Python/ffmpeg/EffectCraft clipping pipeline.

*Gaps:* I did not read: packages/core/src/audioRhythm.ts (the beat tracker itself); effects.ts beyond line 140 (SFX classification); the camera-shake profile tables; the transitions-* CSS blocks; the editorial-flash-overlay, sdf-iris and cinematic-zoom block HTML (I used only the shared shader formulas in packages/shader-transitions); the motion-blur.html runtime beyond its header; snapshotReview.ts after line 200; or measure/diff.ts, person.ts and look.ts. The repo's lessons on timing and camera are hosted externally and are not in the checkout. Nothing was executed (read-only rule), so none of HF's thresholds were validated on podcast or stream footage: cut levels 12/10 grey, soft-cut ratios, sync r >= 0.5, 30 ms fades, the 0.15 s pads. Several pieces are my derivations, not HyperFrames statements: the seam-gate is DOM-based and its crop-path adaptation is mine; the 3:4-in-9:16 safe-band mapping assumes a fit-width letterbox in the Shorts/TikTok player; the ASS centisecond floor rule, the A/V pass threshold (<= 2 frames), the mouth-ROI geometry and the last-frame luma > 16 check are mine. HyperFrames' own rail width for the right action rail is not given. I did not open the clipping-edit repo's analysis/tools/extract_ref.py (it is not in the installed skill folder), so the claim that reference measurements use a 1 fps grid comes from SKILL.md line 102. HyperFrames films default to 30 fps, so I converted its frame counts (for example the 3-frame dip cut) to 60 fps assuming 30 fps sources.

### render-qc

This part of HyperFrames turns frame captures into a delivered file, then proves the file is right. Encoding is ffmpeg with explicit arguments throughout: frame rates as exact rationals, BT.709 matrix conversion plus full colour tags, aq-mode 3, -xerror, even-dimension padding, and locked GOPs only when chunks are stream-copied. Audio is mixed once as 48 kHz float and AAC-encoded once. That AAC is then padded or trimmed to exactly video_frames/fps, true-peak checked after the codec (re-encoded at most 3 times to stay under -1 dBTP), and stream-copied into the MP4 with +faststart. -avoid_negative_ts and -shortest are never used at that step. Every artifact passes fail-loud gates before it is promoted: per-clip frame coverage >= 0.95, duration within one frame, frame shortfall <= 1, exact size, then an atomic rename that retries on Windows file locks. Caches are content-addressed, and ffmpeg is killed on inactivity, not wall-clock time. The review layer adds frame-index-exact sampling and contact sheets (beats, seam strips at -0.2..+0.2 s around every cut, 360 px phone sheet, render-vs-reference pairs). It also adds measurement tools: a cut/flash/whip classifier, a mouth-vs-voice A/V lag, look stats, SSIM/PSNR and black-dropout diffs, and audio null tests. Reviews follow a P0/P1/P2 note format and end in an honest note that separates what was measured from what was only looked at.

*Gaps:* This was a read-only study: nothing in the checkout was executed, so every constant is as written in code or comments, not re-measured. Files read only in part: videoFrameExtractor.ts (about 600 of 3214 lines), ffprobe.ts, audioMixer.ts, artifactTransaction.ts (first 280 lines), regression-harness.ts (PSNR section), loudness.ts (lines 400-570), snapshot.ts, craftAudit.ts (first 200 lines). Not read: frameCapture.ts, streamingEncoder.ts internals, distributed assemble/plan/chunk code (beyond the mp4Stitch header), motion-blur services, hlsConfig, the HTML/GSAP-specific lint rules, the measure/events.ts and measure/diff.ts algorithms beyond their constants, the audio-analysis onset providers, docs/guides/hdr.mdx and performance.mdx. EffectCraft's own encoder colour matrix, tags, GOP/B-frame structure and audio-track behaviour are unknown; a test card must measure them before the tagging and parts-concat rules are final. These come from general ffmpeg/yt-dlp knowledge, not the HF repo: the yt-dlp HDR-preference default, the alimiter (level=0), h264_metadata, -fps_mode and CREATE_NO_WINDOW syntax, the 32,767-character Windows command-line limit, and the 90000-timescale arithmetic. The 9:16 platform-UI band (168/1330 px) is HF skill text with no stated source, and the 3:4-in-9:16 placement assumes a letterboxed player. The mouth-ROI size factors (1.6x/0.9x of the mouth-corner distance), the 34 ms sync gate, the 3-frame persistence rule and the 5-10 ms splice fades are our own proposals, not HF constants.

### skill-design

Each HyperFrames domain gets one small entry skill: SKILL.md stays at or under 7,168 B and the description at or under 320 B, because descriptions are listed to the agent on every turn. The entry skill holds a numbered contract (enforced by a CLI check that prints a Fix: line), a work loop with stop points, and a request-to-reference routing table. Topic references of about 6 KB each are read only when a row applies, and pipeline skills such as changelog-video build every job from the skill's own shipped scaffold or a JSON ledger, so the output passes its gates by construction. User memory has two tiers. Preferences are recorded only when the user confirms them and move to the personal tier once confirmed in 2 different projects. An approved run is frozen as a versioned recipe bundle, and a new freeze archives the old one as name@vN. Assets go into an append-only JSONL ledger with an index.md the agent can read, plus a global cache keyed by a 16-hex SHA-256 that counts a hit only when its completion sentinel exists. A local misses log feeds hit-rate and top-5 statistics used for tuning. Review works as 'measure, then look': numbers first, then contact sheets with strips across every cut, one-line notes ranked P0 to P2, fix rounds bounded at one extra pass, hard gates for data that can vanish silently (word timings, caption presence), and a REVIEW.md that the next turn reads first. Skill upkeep is automated: a bundle hash with CRLF normalised to LF catches drift and triggers a once-a-day stale notice, a linter checks the frontmatter schema, inline code that can stop Claude Code loading the skill, links and size budgets, parity tests catch docs that contradict the code, retired skills leave pointers, and eval corpora gate releases with thresholds 0.02 below measured p05 and a 2-of-3 regression ratchet. For clipping-edit, the biggest gaps are per-job hand-written render code (ship versioned scripts plus a style data file instead), re-edits that rebuild more than the change needs, cache reuse with no validity check, no gate on transcript or caption presence, no check of the render against the planned duration, and no lessons log or eval harness to turn each correction into a rule with a regression check.

*Gaps:* I did not read docs/prompting/captions-catalog.mdx, color-grading.mdx, design-systems.mdx, motion.mdx, data-and-maps.mdx or remotion-migration.mdx. The hyperframes references format, look, motion, film, overlays, runtimes and plugin-installation were not read either, and storyboard-format.md was only grepped. From media-use I skipped grading, mixing, media-treatments, media-treatment-recipes, heygen, local and audio.md. Several source files went unread: the history command (packages/cli/src/commands/history.ts), diff.ts beyond its constants, events.ts after about line 230, seam-gate.mjs beyond its constants, telemetry.mjs, and the Studio viral-clone sources that events.ts was ported from. DESIGN.md was only skimmed; it is docs-site branding. packages/cli/AGENTS.md and docs/AGENTS.md loaded automatically as context and were quoted as data.

Nothing in the checkout was executed. All constants come from reading the source, not from running it. I did not verify HF's claim that '!' or '>word' inside inline backticks stops Claude Code from loading a skill; clipping-edit has zero such spans today in any case. The caption-presence gate's pairing with raw/ and the burned-in-subtitle edge heuristic are my own adaptations; HF supplies only the gate idea and thr=5. I have not measured the platform UI band for 3:4 Shorts.

Facts about the user's repo came from read-only commands:
- SKILL.md is 11,175 B and its description 389 B; ref 01 is 21,229 B and ref 02 14,100 B.
- There are 0 risky inline-code spans.
- 2 backticked paths resolve only in the repo.
- The installed copy matches the repo copy (diff -rq).
- ref1.md documents 172 detected cuts against about 27 real ones, and lists only 1 fps frames and 10 fps sheets as its sources for caption timing.

### sweep

Sweep of HyperFrames material outside the eight topic readers. The most valuable uncovered code is the `hyperframes audio` analysis stack: BS.1770 loudness and true peak, sound 'moments' (onset, steepest rise, peak, tail), silence spans, onsets, a voice/music/sfx classifier, an SFX event detector that labels and groups sounds, and a per-sentence prosody reader (`--read`) that turns a recording into grep-able lines for an agent. Around it sit the engine's ffmpeg mixer and an amix level-measurement spike, plus the background-removal decode, process and encode pipe, which has the same shape as our cv2 fallback. Also swept: the studio proxy transcoder, the HDR and BT.709 tagging helpers, the producer's frame-coverage gate, the CLI's QC audits (craft, contrast, audio), whisper transcript repair and Windows UTF-8 guards for skill Python. In the registry: the flash, whip, zoom-blur and light-leak shader transitions, motion-blur sampling rules, the camera-shake overscan solver and a critically damped follow camera. Most of what transfers is correctness: unity-sum mixing, SFX hit-point alignment, splice micro-fades, explicit BT.709 conversion, HDR and VFR source gates, frame-coverage and frame-0 checks, and QC that only fails on defects held across samples. Style items (flash kernels, carving the music bed, spring follow) are offered as options that keep ref 01's numbers.

*Gaps:* Read-only sweep: nothing in the checkout was run, so several repo claims are quoted, not re-measured. These are parity with ffmpeg ebur128 within 0.1 LU, the +2.499 dB nested-amix error, Chrome's guess for untagged colour matrices, and the FFmpeg 8 VFR behaviour.

Not read in full:
- checkPipeline.ts (2383 lines): only the caption-zone, frame-breach and contrast-persistence parts.
- camera-shake's profile table beyond the overscan solver.
- audio read/music.ts: it needs HeyGen stem separation.
- bandFramesOf in audioRhythm.ts (owned by the audio reader). The 1/5-octave band layout in the effects port is inferred from effects.ts constants.

Deliberately left to other readers: audioCarve.ts band selection (one line peeked), videoFrameExtractor's VFR code and the encoder argument builders (only lines 955-985 read), sound.md (one line quoted), and measure/* (cuts, faces, sync).

Not verified:
- yt-dlp's [dynamic_range=SDR] format-filter syntax.
- How ffmpeg/libass convert ASS colours to YUV (matrix handling). That is why a palette test card is proposed instead of a claim.
- That ~8 KB is a safe threshold for moving filter graphs to a file on Windows next to EffectCraft's own command lines.
- The suggested face-follow numbers (omega 2.5 rad/s, 0.25 s look-ahead) and the 12/8 dB margin thresholds are my translations, not HyperFrames values.

HyperFrames has nothing usable on diarization or active-speaker choice, auto-reframe or saliency cropping, platform UI safe zones (only the Premiere-style 90%/80% action/title-safe guides in studio/previewSafeMargins.ts), or hook and virality scoring. Those gaps remain open for the clipping skill.

## Learning index (reader proposals, before dedupe)

Adoption and value (1-5) are the reader's proposal. The references hold the final decision. Evidence paths are repo-relative to HyperFrames.

### captions (25)

| id | step | proposal | value | evidence |
|---|---|---|---|---|
| caption-sync-through-cuts | render-encode | adopt_default | 5 | `skills/media-use/scripts/transcript-cut.mjs:96-100`; `skills/media-use/scripts/transcript-cut.mjs:278-281` |
| llm-cleanup-timing-contract | captions | adopt_default | 5 | `.agents/skills/changelog-video/scripts/align-captions.mjs:11-15`; `.agents/skills/changelog-video/scripts/align-captions.mjs:54-58` |
| final-mp4-sync-check | qc-review | adopt_default | 4 | `.agents/skills/changelog-video/SKILL.md:100-102`; `.agents/skills/changelog-video/SKILL.md:104-109` |
| transcript-quality-gate | transcribe | adopt_default | 4 | `skills/hyperframes/references/captions.md:8`; `skills/hyperframes/references/captions.md:10` |
| dropped-speech-repair | transcribe | adopt_default | 4 | `packages/cli/src/whisper/parakeet.ts:153-171`; `packages/cli/src/whisper/parakeet.ts:163` |
| measured-fit-balanced-lines | captions | adopt_default | 4 | `registry/components/caption-neon-accent/caption-neon-accent.html:139`; `registry/components/caption-neon-accent/caption-neon-accent.html:311-342` |
| face-avoid-over-chunk-window | captions | adopt_default | 4 | `skills/hyperframes/references/captions.md:45`; `docs/guides/captions-and-recuts.mdx:125-127` |
| vertical-platform-ui-band | captions | adopt_default | 4 | `skills/hyperframes/references/types/vertical.md:7`; `skills/hyperframes/references/types/vertical.md:7` |
| caption-layer-determinism | captions | adopt_default | 4 | `skills/hyperframes/references/captions.md:21`; `packages/lint/src/rules/captions.ts:26-36` |
| word-timestamp-normalization | transcribe | adopt_default | 3 | `packages/cli/src/whisper/normalize.ts:96-99`; `packages/cli/src/whisper/normalize.ts:118` |
| asr-language-model-lexicon | transcribe | adopt_default | 3 | `skills/media-use/audio/references/transcribe.md:16`; `skills/media-use/audio/references/transcribe.md:37` |
| parakeet-asr-option | transcribe | adopt_optional | 3 | `skills/media-use/references/operations.md:107-112`; `skills/media-use/references/operations.md:112` |
| frame-snapped-caption-times | captions | adopt_default | 3 | `skills/media-use/scripts/transcript-cut.mjs:278-285`; `packages/cli/src/media-use/lib/cutlist.mjs:176-178` |
| caption-contrast-gate | qc-review | adopt_default | 3 | `packages/cli/src/commands/contrast-sample.ts:3-8`; `packages/cli/src/commands/contrast-sample.ts:56-60` |
| caption-presence-coverage-gate | qc-review | adopt_default | 3 | `.agents/skills/changelog-video/SKILL.md:162-167`; `releases/v0.8.221.md:23` |
| burned-in-text-scan | captions | adopt_default | 3 | `skills/hyperframes/references/captions.md:39`; `docs/guides/captions-and-recuts.mdx:49-50` |
| non-speech-text-floors | captions | adopt_default | 3 | `packages/cli/src/utils/craftAudit.ts:5-7`; `packages/cli/src/utils/craftAudit.ts:6` |
| keyword-guard-deterministic | captions | adopt_default | 3 | `registry/components/caption-emoji-pop/caption-emoji-pop.html:262-277`; `registry/components/caption-emoji-pop/caption-emoji-pop.html:270-271` |
| ec-stroke-paint-order | captions | adopt_default | 3 | `registry/components/caption-emoji-pop/caption-emoji-pop.html:106`; `registry/components/caption-emoji-pop/caption-emoji-pop.html:107` |
| word-id-caption-overrides | re-edit-cache | adopt_default | 3 | `packages/core/src/runtime/captionOverrides.ts:8-10`; `packages/core/src/runtime/captionOverrides.ts:4-6` |
| entrance-lead-before-word | captions | adopt_optional | 2 | `registry/components/caption-neon-accent/caption-neon-accent.html:466-471`; `registry/components/caption-pill-karaoke/caption-pill-karaoke.html:151` |
| multi-radius-glow | captions | adopt_optional | 2 | `registry/components/caption-neon-accent/caption-neon-accent.html:414-426`; `registry/components/caption-neon-accent/caption-neon-accent.html:427` |
| speech-rate-chunk-size | captions | adopt_optional | 2 | `skills/hyperframes/references/captions.md:19`; `registry/components/caption-glitch-rgb/caption-glitch-rgb.html:178-179` |
| hf-motion-defaults-rejected | captions | reject | 1 | `skills/media-use/audio/references/captions/motion.md:15`; `skills/media-use/audio/references/captions/motion.md:23` |
| hf-timing-conventions-noted | captions | note_only | 1 | `skills/hyperframes/references/captions.md:20`; `docs/guides/captions-and-recuts.mdx:135` |

### transcript-cutting (25)

| id | step | proposal | value | evidence |
|---|---|---|---|---|
| splice-fade-30ms | audio | adopt_default | 5 | `packages/cli/src/media-use/lib/transcriptCutFade.mjs:5-13`; `skills/media-use/scripts/transcript-cut.mjs:106-114` |
| pcm-intermediates-one-aac-encode | render-encode | adopt_default | 5 | `skills/media-use/scripts/transcript-cut.mjs:96-100`; `skills/media-use/scripts/transcript-cut.mjs:128-132` |
| dropped-speech-repair | transcribe | adopt_default | 5 | `packages/cli/src/whisper/parakeet.ts:153-171`; `packages/cli/src/whisper/parakeet.ts:163` |
| cut-then-caption-remap | captions | adopt_default | 5 | `docs/guides/captions-and-recuts.mdx:116-119`; `docs/guides/captions-and-recuts.mdx:38-39` |
| frame-exact-cut-times | render-encode | adopt_default | 4 | `skills/media-use/scripts/transcript-cut.mjs:278-285`; `packages/cli/src/media-use/lib/cutlist.mjs:176-178` |
| intermediate-container-flags | render-encode | adopt_default | 4 | `skills/media-use/scripts/transcript-cut.mjs:101-104`; `skills/media-use/scripts/transcript-cut.mjs:203-205` |
| cut-list-compiler | pick | adopt_default | 4 | `packages/cli/src/media-use/lib/cutlist.mjs:3`; `packages/cli/src/media-use/lib/cutlist.mjs:21-28` |
| llm-cuts-by-word-id | pick | adopt_default | 4 | `packages/cli/src/media-use/lib/cutlist.mjs:92-95`; `skills/media-use/audio/references/transcribe.md:43` |
| dead-air-guard-pads | pick | adopt_default | 4 | `packages/cli/src/media-use/lib/cutlist.mjs:4`; `packages/cli/src/media-use/lib/cutlist.mjs:131-135` |
| whisper-hallucination-gate | transcribe | adopt_default | 4 | `skills/hyperframes/references/captions.md:8`; `skills/media-use/audio/references/captions/transcript-handling.md:35` |
| word-timing-repair-and-id-edits | transcribe | adopt_default | 4 | `packages/cli/src/whisper/normalize.ts:96-103`; `packages/cli/src/whisper/normalize.ts:118` |
| splices-reset-reframe | reframe | adopt_default | 4 | `skills/reverse-any-video/SKILL.md:19`; `packages/cli/src/measure/cuts.ts:1-2` |
| final-mux-priming | render-encode | adopt_default | 4 | `packages/engine/src/services/audioMixer.ts:79-81`; `packages/engine/src/services/chunkEncoder.ts:892-896` |
| splice-qc-suite | qc-review | adopt_default | 4 | `skills/media-use/scripts/transcript-cut.test.mjs:136-146`; `skills/media-use/scripts/transcript-cut.test.mjs:178-181` |
| asr-language-and-vocab | transcribe | adopt_default | 3 | `skills/media-use/audio/references/transcribe.md:14-22`; `packages/cli/src/whisper/modelForLanguage.ts:1-8` |
| parakeet-engine-option | transcribe | adopt_optional | 3 | `packages/cli/src/whisper/parakeet.ts:4-7`; `skills/media-use/references/operations.md:111-112` |
| filler-token-safe-list | pick | adopt_default | 3 | `packages/cli/src/media-use/lib/cutlist.mjs:108-109`; `skills/media-use/references/operations.md:147` |
| ffmpeg-volume-expression-limit | audio | adopt_default | 3 | `packages/engine/src/services/audioMixer.ts:199-209`; `packages/engine/src/services/audioMixer.ts:215` |
| av-sync-measure | qc-review | adopt_default | 3 | `packages/cli/src/measure/sync.ts:1-3`; `packages/cli/src/measure/sync.ts:45` |
| duck-from-word-spans | audio | adopt_optional | 3 | `packages/cli/src/media-use/lib/duck.mjs:4`; `packages/cli/src/media-use/lib/duck.mjs:36-39` |
| sfx-peak-one-frame-late | accents-motion | adopt_default | 3 | `skills/hyperframes/references/sound.md:36`; `skills/hyperframes/references/sound.md:37` |
| loudnorm-two-pass-tp | audio | adopt_default | 3 | `skills/media-use/references/operations.md:193-195`; `skills/media-use/references/operations.md:198-200` |
| vfr-source-to-cfr | render-encode | adopt_default | 3 | `packages/engine/src/utils/ffprobe.ts:974-975`; `packages/engine/src/services/videoFrameExtractor.ts:1174-1184` |
| atomic-cache-writes | re-edit-cache | adopt_default | 3 | `skills/media-use/scripts/transcribe.mjs:92-98`; `skills/media-use/scripts/transcript-cut.mjs:123-125` |
| speed-change-atempo | audio | adopt_optional | 2 | `packages/engine/src/services/audioMixer.ts:111-126`; `packages/engine/src/services/audioMixer.ts:128-130` |

### audio (25)

| id | step | proposal | value | evidence |
|---|---|---|---|---|
| ffmpeg-mix-graph-gain-law | audio | adopt_default | 5 | `packages/engine/src/services/audioMixer.ts:954-956`; `packages/engine/src/services/audioMixer.ts:955` |
| splice-pcm-intermediates-30ms-fades | render-encode | adopt_default | 5 | `skills/media-use/scripts/transcript-cut.mjs:95-100`; `packages/cli/src/media-use/lib/transcriptCutFade.mjs:5-13` |
| transcript-driven-duck-envelope | audio | adopt_default | 5 | `skills/media-use/scripts/audio-duck.mjs:13-16`; `packages/cli/src/media-use/lib/duck.mjs:89-103` |
| aac-true-peak-post-encode-gate | render-encode | adopt_default | 4 | `packages/producer/src/services/render/audioPadTrim.ts:49-52`; `packages/producer/src/services/render/audioPadTrim.ts:442-451` |
| limiter-last-with-margin | audio | adopt_default | 4 | `docs/reference/audio-effects.mdx:281-283`; `docs/reference/audio-effects.mdx:293-299` |
| static-gain-loudness-normalisation | audio | adopt_default | 4 | `packages/studio-server/src/helpers/loudness.ts:503-506`; `packages/studio-server/src/helpers/loudness.ts:523-528` |
| dialogue-cleanup-chain | audio | adopt_default | 4 | `packages/core/src/audioFxPresets.ts:93-109`; `packages/core/src/audioFxPresets.ts:99` |
| voice-over-bed-margin-qc | qc-review | adopt_default | 4 | `packages/core/src/audioCarve.ts:672-681`; `packages/core/src/audioCarve.ts:721` |
| sfx-peak-alignment | accents-motion | adopt_default | 4 | `skills/hyperframes/references/sound.md:36`; `docs/packages/cli.mdx:764-766` |
| sfx-variant-library-manifest | audio | adopt_default | 4 | `skills/media-use/audio/references/sfx.md:5-6`; `skills/media-use/audio/references/sfx.md:12` |
| bed-entry-strongest-section-and-loop | audio | adopt_default | 4 | `skills/hyperframes/references/sound.md:20`; `skills/media-use/audio/references/bgm.md:36` |
| exact-length-audio-before-mux | render-encode | adopt_default | 4 | `packages/producer/src/services/render/audioPadTrim.ts:11-14`; `packages/producer/src/services/render/audioPadTrim.ts:178-185` |
| lip-sync-lag-qc | qc-review | adopt_default | 4 | `packages/cli/src/measure/sync.ts:1-3`; `packages/cli/src/measure/sync.ts:45` |
| audio-qc-battery | qc-review | adopt_default | 4 | `packages/core/src/audioAnalysis.ts:474-512`; `packages/core/src/audioAnalysis.ts:514-533` |
| reference-short-audio-measurement | analysis-tooling | adopt_default | 4 | `docs/packages/cli.mdx:812-816`; `docs/packages/cli.mdx:822-833` |
| measure-only-the-played-window | qc-review | adopt_default | 3 | `packages/studio-server/src/helpers/loudness.ts:448-457`; `packages/studio-server/src/helpers/loudness.ts:453-456` |
| sfx-reuse-fingerprint-qc | qc-review | adopt_default | 3 | `packages/cli/src/audio/read/effects.ts:14`; `packages/cli/src/audio/read/effects.ts:205-212` |
| bed-sub-150hz-share-check | audio | adopt_default | 3 | `skills/hyperframes/references/sound.md:37`; `packages/cli/src/audio/read/effects.ts:186-188` |
| beat-grid-only-where-music-leads | accents-motion | adopt_optional | 3 | `packages/core/src/audioRhythm.ts:454-462`; `packages/core/src/beats/beatDetection.ts:44-45` |
| source-already-has-music | audio | adopt_optional | 3 | `packages/core/src/audioAnalysis.ts:112-120`; `packages/core/src/audioAnalysis.ts:600-617` |
| even-out-dialogue-leveller | audio | adopt_optional | 3 | `packages/core/src/audioLeveller.ts:41-53`; `packages/core/src/audioLeveller.ts:117-129` |
| bed-spectral-carve | audio | adopt_optional | 3 | `packages/core/src/audioCarve.ts:25`; `packages/core/src/audioCarve.ts:443-447` |
| dead-air-cut-padding | pick | adopt_optional | 3 | `packages/cli/src/media-use/lib/cutlist.mjs:3-4`; `packages/cli/src/media-use/lib/cutlist.mjs:121-138` |
| bed-recovery-release-time | audio | adopt_optional | 2 | `packages/core/src/audioCarve.ts:504-510`; `packages/core/src/audioCarve.ts:513-527` |
| sfx-level-relative-to-bed | audio | note_only | 2 | `skills/hyperframes/references/sound.md:37`; `skills/media-use/audio/references/sfx.md:44` |

### grade-look (22)

| id | step | proposal | value | evidence |
|---|---|---|---|---|
| gate-on-footage-pixels-only | qc-review | adopt_default | 5 | `docs/prompting/color-grading.mdx:10-11`; `skills/media-use/references/media-treatment-recipes.md:791-792` |
| one-metric-module-with-parity-test | analysis-tooling | adopt_default | 4 | `packages/cli/src/media-use/lib/grade-analyzer.mjs:1-2`; `packages/cli/src/media-use/lib/grade-analyzer.mjs:2` |
| hdr-pq-hlg-tonemap-at-ingest | download | adopt_default | 4 | `packages/engine/src/utils/hdr.ts:18-21`; `packages/core/src/hdrToneMap.ts:29` |
| name-matrix-and-range-on-every-rgb-hop | grade | adopt_default | 4 | `packages/engine/src/services/videoFrameExtractor.ts:971`; `packages/engine/src/services/videoFrameExtractor.ts:977` |
| tag-bt709-tv-in-vui-and-container | render-encode | adopt_default | 4 | `packages/engine/src/services/chunkEncoder.ts:477`; `packages/engine/src/services/chunkEncoder.ts:423` |
| signalstats-source-classes | grade | adopt_default | 4 | `packages/cli/src/media-use/lib/grade-analyzer.mjs:116-117`; `packages/cli/src/media-use/lib/grade-analyzer.mjs:122` |
| correct-per-camera-then-one-look | grade | adopt_default | 4 | `docs/guides/media-effects.mdx:53`; `packages/core/src/colorGroups.ts:2-6` |
| skin-weighted-vibrance | grade | adopt_optional | 4 | `packages/core/src/runtime/colorGrading.ts:1239`; `packages/core/src/runtime/colorGrading.ts:1240` |
| thresholded-glow-in-rgb | grade | adopt_default | 4 | `packages/core/src/runtime/colorGrading.ts:1484-1485`; `packages/core/src/runtime/colorGrading.ts:2358` |
| haze-guard-black-level-contrast | qc-review | adopt_default | 4 | `docs/prompting/color-grading.mdx:104`; `docs/prompting/color-grading.mdx:104` |
| headroom-aware-luma-gate | qc-review | adopt_default | 4 | `packages/cli/src/media-use/lib/grade-analyzer.mjs:117`; `packages/cli/src/media-use/lib/grade-analyzer.mjs:122` |
| grade-footage-layer-not-captions | grade | adopt_default | 4 | `docs/prompting/color-grading.mdx:10-11`; `docs/prompting/color-grading.mdx:198` |
| anti-banding-aq-and-opacity-floor | render-encode | adopt_default | 3 | `packages/engine/src/services/chunkEncoder.ts:406-407`; `packages/engine/src/services/chunkEncoder.ts:432` |
| neutral-pixel-cast-before-warmth | grade | adopt_default | 3 | `packages/core/src/colorGradingBake.ts:107-109`; `packages/cli/src/media-use/lib/grade-analyzer.mjs:132-133` |
| bake-pointwise-grade-to-cube | grade | adopt_optional | 3 | `packages/core/src/colorGradingBake.ts:20-21`; `packages/core/src/colorGradingBake.ts:26` |
| skin-qc-circular-hue-vectorscope-dark-skin | qc-review | adopt_default | 3 | `packages/studio/src/components/editor/colorGradingFrameAnalysis.ts:174-176`; `packages/studio/src/components/editor/colorGradingFrameAnalysis.ts:187-191` |
| ui-screen-gameplay-fidelity | grade | adopt_optional | 3 | `skills/media-use/references/media-treatment-recipes.md:153-155`; `skills/media-use/references/media-treatment-recipes.md:161-162` |
| before-after-sheet-and-honest-report | qc-review | adopt_default | 3 | `skills/media-use/references/media-treatments.md:141-142`; `skills/media-use/references/media-treatments.md:145-147` |
| exposure-push-flash | accents-motion | adopt_optional | 3 | `skills/media-use/references/media-treatment-recipes.md:923-924`; `skills/media-use/references/media-treatment-recipes.md:925-926` |
| lut-hygiene-never-read-cube | skill-structure | adopt_default | 2 | `skills/media-use/references/grading.md:20`; `packages/cli/src/media-use/lib/cube-validate.mjs:158` |
| hf-content-recipes-reference | grade | note_only | 2 | `skills/media-use/references/media-treatment-recipes.md:40-52`; `packages/core/src/colorGrading.ts:485-499` |
| pchip-s-curve | grade | adopt_optional | 2 | `packages/core/src/colorGradingCurves.ts:152`; `packages/core/src/colorGradingCurves.ts:59-61` |

### measure-reverse (23)

| id | step | proposal | value | evidence |
|---|---|---|---|---|
| adaptive-cut-detector | reframe | adopt_default | 5 | `packages/cli/src/measure/cuts.ts:2`; `packages/cli/src/measure/cuts.ts:7-19` |
| edl-cut-match-qc | qc-review | adopt_default | 5 | `packages/cli/src/measure/diff.ts:67`; `packages/cli/src/measure/diff.ts:469-472` |
| probe-normalize-cfr-sdr | download | adopt_default | 5 | `packages/cli/src/measure/media.ts:133`; `packages/cli/src/measure/media.ts:134` |
| audio-clock-alignment | transcribe | adopt_default | 5 | `packages/cli/src/measure/diff.ts:1062`; `packages/cli/src/measure/sync.ts:21` |
| flash-whip-not-cuts | qc-review | adopt_default | 4 | `packages/cli/src/measure/cuts.ts:17-19`; `packages/cli/src/measure/cuts.ts:84` |
| frame-exact-segment-cuts | render-encode | adopt_default | 4 | `packages/cli/src/commands/measure/extract.ts:100`; `packages/cli/src/commands/measure/extract.ts:106` |
| frame-time-rounding | captions | adopt_default | 4 | `packages/cli/src/measure/media.ts:340-341`; `skills/reverse-any-video/SKILL.md:19` |
| av-sync-gate | qc-review | adopt_default | 4 | `packages/cli/src/measure/sync.ts:3`; `packages/cli/src/measure/sync.ts:120` |
| active-speaker-by-av-correlation | reframe | adopt_optional | 4 | `packages/cli/src/measure/sync.ts:73`; `packages/cli/src/measure/person.ts:449` |
| per-shot-framing-medians | qc-review | adopt_default | 4 | `packages/cli/src/measure/person.ts:16-17`; `packages/cli/src/measure/person.ts:16` |
| grade-qc-contrast-warmth-floors | grade | adopt_default | 4 | `packages/cli/src/measure/look.ts:7`; `packages/cli/src/measure/look.ts:40` |
| event-strips-not-grids | analysis-tooling | adopt_default | 4 | `packages/cli/src/commands/measure/frames.ts:140`; `packages/cli/src/commands/measure/frames.ts:151` |
| caption-switches-from-pixels | captions | adopt_default | 4 | `skills/reverse-any-video/references/match.md:8`; `packages/cli/src/measure/events.ts:198` |
| locate-clip-in-source-by-audio | analysis-tooling | adopt_optional | 4 | `packages/cli/src/measure/person.ts:35`; `packages/cli/src/measure/person.ts:139-140` |
| face-detector-robustness | reframe | adopt_optional | 3 | `packages/cli/src/measure/face.ts:14`; `packages/cli/src/measure/face.ts:123` |
| ink-text-metrics | captions | adopt_default | 3 | `packages/cli/src/measure/drawn.ts:12`; `packages/cli/src/measure/drawn.ts:46` |
| holds-frozen-frames | qc-review | adopt_default | 3 | `packages/cli/src/measure/events.ts:11`; `packages/cli/src/measure/events.ts:103` |
| onset-detector-for-sfx-accents | audio | adopt_optional | 3 | `packages/core/src/audioAnalysis.ts:313`; `packages/core/src/audioAnalysis.ts:293` |
| regression-diff-for-re-edits | re-edit-cache | adopt_optional | 3 | `packages/cli/src/measure/diff.ts:304`; `packages/cli/src/measure/diff.ts:60` |
| agent-friendly-measure-output | skill-structure | adopt_default | 3 | `packages/cli/src/measure/command.ts:1`; `packages/cli/src/measure/media.ts:343` |
| ease-and-envelope-fitting | accents-motion | adopt_optional | 3 | `packages/cli/src/measure/curve.ts:197`; `packages/cli/src/measure/curve.ts:206` |
| motion-energy-profile | analysis-tooling | adopt_optional | 2 | `packages/cli/src/measure/energy.ts:2`; `packages/cli/src/measure/energy.ts:9` |
| stop-after-one-rediff | qc-review | note_only | 2 | `skills/reverse-any-video/SKILL.md:36`; `skills/reverse-any-video/SKILL.md:38` |

### motion-editing (25)

| id | step | proposal | value | evidence |
|---|---|---|---|---|
| frame-exact-segment-cuts | render-encode | adopt_default | 5 | `skills/media-use/scripts/transcript-cut.mjs:278-285`; `skills/media-use/scripts/transcript-cut.mjs:101-103` |
| source-cut-detection-soft-cuts | reframe | adopt_default | 5 | `packages/cli/src/measure/cuts.ts:1-2`; `packages/cli/src/measure/cuts.ts:7-19` |
| click-free-splices | audio | adopt_default | 4 | `skills/media-use/scripts/lib/transcriptCutFade.mjs:5-21`; `skills/media-use/scripts/transcript-cut.mjs:96-100` |
| dead-air-edge-padding | pick | adopt_default | 4 | `packages/cli/src/media-use/lib/cutlist.mjs:3-4`; `packages/cli/src/media-use/lib/cutlist.mjs:131-134` |
| unplanned-event-qc | qc-review | adopt_default | 4 | `packages/cli/src/measure/cuts.ts:28`; `packages/cli/src/measure/events.ts:128-129` |
| seam-strip-and-phone-sheet | qc-review | adopt_default | 4 | `packages/cli/src/commands/snapshotReview.ts:13-16`; `skills/hyperframes/references/review.md:8` |
| accent-sync-frames | accents-motion | adopt_default | 4 | `skills/hyperframes/references/film.md:34`; `skills/hyperframes/references/sound.md:36` |
| jump-cut-eye-trace | reframe | adopt_default | 4 | `.agents/skills/motion-doctrine/SKILL.md:77-78`; `.agents/skills/motion-doctrine/scripts/seam-gate.mjs:43-44` |
| platform-ui-safe-band | captions | adopt_default | 4 | `skills/hyperframes/references/types/vertical.md:7`; `skills/hyperframes/SKILL.md:41` |
| frame-quantized-times | captions | adopt_default | 4 | `skills/reverse-any-video/SKILL.md:19`; `docs/prompting/motion.mdx:110` |
| caption-switch-from-pixels | qc-review | adopt_default | 4 | `skills/reverse-any-video/references/match.md:8`; `packages/cli/src/measure/events.ts:1-3` |
| av-sync-qc | qc-review | adopt_default | 4 | `packages/cli/src/measure/sync.ts:1-3`; `packages/cli/src/measure/sync.ts:119-124` |
| edge-sliver-snap | pick | adopt_default | 4 | `packages/cli/src/media-use/lib/cutlist.mjs:3`; `packages/core/src/audioSnap.ts:32` |
| reference-study-full-fps | analysis-tooling | adopt_default | 4 | `skills/reverse-any-video/SKILL.md:21`; `packages/cli/src/measure/events.ts:15-19` |
| payoff-pause | pick | adopt_optional | 3 | `skills/hyperframes/references/motion.md:24`; `.agents/skills/motion-doctrine/SKILL.md:140-143` |
| whip-vector-law | accents-motion | adopt_default | 3 | `.agents/skills/cut-the-curve/SKILL.md:106-107`; `.agents/skills/cut-the-curve/SKILL.md:50` |
| opaque-ground-no-dips | render-encode | adopt_default | 3 | `.agents/skills/seam-craft/SKILL.md:23-31`; `docs/prompting/motion.mdx:137` |
| clamp-ends-and-1s-gop | render-encode | adopt_default | 3 | `skills/hyperframes/references/overlays.md:30`; `skills/hyperframes/references/overlays.md:37` |
| hook-first-second | pick | adopt_optional | 3 | `skills/hyperframes/references/types/vertical.md:11-12`; `packages/cli/src/utils/craftAudit.ts:133` |
| music-beat-grid | audio | adopt_optional | 3 | `skills/hyperframes/references/motion.md:13`; `skills/hyperframes/references/film.md:32-33` |
| flash-freeze-envelopes | accents-motion | adopt_optional | 3 | `registry/blocks/beat-freeze-cut/beat-freeze-cut.html:742-748`; `registry/blocks/beat-freeze-cut/beat-freeze-cut.html:724` |
| synthetic-blur-and-transition-formulas | accents-motion | adopt_optional | 3 | `registry/components/motion-blur/motion-blur.html:42-47`; `registry/components/motion-blur/motion-blur.html:56` |
| camera-move-layering | reframe | adopt_default | 3 | `skills/hyperframes/references/motion.md:57`; `registry/components/yt-camera-move/yt-camera-move.html:113-126` |
| review-notes-format | qc-review | adopt_default | 3 | `skills/hyperframes/references/review.md:32`; `skills/hyperframes/references/review.md:38` |
| hf-style-defaults-not-adopted | other | note_only | 1 | `skills/hyperframes/references/motion.md:30`; `.agents/skills/motion-doctrine/SKILL.md:155` |

### render-qc (25)

| id | step | proposal | value | evidence |
|---|---|---|---|---|
| audio-exact-length-no-shortest | render-encode | adopt_default | 5 | `packages/producer/src/services/render/audioPadTrim.ts:11-14`; `packages/producer/src/services/render/audioPadTrim.ts:47` |
| mux-copy-aac-no-black-first-frame | render-encode | adopt_default | 5 | `packages/engine/src/services/chunkEncoder.ts:892-896`; `packages/engine/src/services/chunkEncoder.ts:898` |
| bt709-explicit-matrix-and-tags | render-encode | adopt_default | 5 | `packages/engine/src/utils/sdrCaptureColor.ts:1-5`; `packages/engine/src/services/chunkEncoder.ts:474-479` |
| fps-rationals-vfr-cfr-mezzanine | download | adopt_default | 5 | `packages/core/src/fps.ts:63-71`; `packages/engine/src/utils/ffprobe.ts:974-975` |
| render-artifact-gate | qc-review | adopt_default | 5 | `packages/producer/src/services/render/artifactTransaction.ts:27-30`; `packages/producer/src/services/render/artifactTransaction.ts:187-191` |
| review-contact-sheets | qc-review | adopt_default | 5 | `packages/cli/src/commands/snapshotReview.ts:10-16`; `packages/cli/src/commands/snapshotReview.ts:148-151` |
| true-peak-post-aac-and-window-loudness | audio | adopt_default | 4 | `packages/producer/src/services/render/audioPadTrim.ts:50-52`; `packages/producer/src/services/render/audioPadTrim.ts:442-451` |
| source-colour-hdr-sar-rotation-normalise | download | adopt_default | 4 | `packages/engine/src/utils/hdr.ts:18-21`; `packages/engine/src/utils/hdr.ts:145` |
| segment-frame-coverage | render-encode | adopt_default | 4 | `packages/producer/src/services/render/videoFrameCoverage.ts:40-44`; `packages/producer/src/services/render/videoFrameCoverage.ts:62-63` |
| parts-concat-closed-gop | render-encode | adopt_default | 4 | `packages/engine/src/services/chunkEncoder.ts:222-233`; `packages/engine/src/services/chunkEncoder.ts:235-243` |
| qc-sampling-index-exact-persistent | qc-review | adopt_default | 4 | `packages/cli/src/measure/media.ts:212`; `packages/producer/src/regression-harness.ts:607-612` |
| review-notes-p0-p1-p2 | qc-review | adopt_default | 4 | `skills/hyperframes/references/review.md:12`; `skills/hyperframes/references/review.md:32` |
| av-sync-lag-gate | qc-review | adopt_default | 4 | `packages/cli/src/measure/sync.ts:1-3`; `packages/cli/src/measure/sync.ts:76` |
| classified-cut-detector | qc-review | adopt_default | 4 | `packages/cli/src/measure/cuts.ts:1-2`; `packages/cli/src/measure/cuts.ts:5-19` |
| decoded-durations-not-container | qc-review | adopt_default | 4 | `packages/engine/src/utils/ffprobe.ts:1264-1265`; `packages/engine/src/utils/ffprobe.ts:1330-1341` |
| sample-accurate-audio-assembly | audio | adopt_default | 4 | `packages/engine/src/services/audioMixer.ts:686-687`; `packages/engine/src/services/audioMixer.ts:954-957` |
| windows-ffmpeg-robustness | render-encode | adopt_default | 4 | `packages/producer/src/regression-harness.ts:669-670`; `packages/engine/src/services/audioMixer.ts:964-974` |
| stall-timeouts-atomic-stages-early-report | skill-structure | adopt_default | 4 | `packages/engine/src/utils/runFfmpeg.ts:81-83`; `packages/engine/src/config.ts:321-323` |
| content-addressed-cache-deterministic | re-edit-cache | adopt_default | 4 | `packages/engine/src/services/extractionCache.ts:13-18`; `packages/engine/src/services/extractionCache.ts:61-65` |
| caption-box-vs-face-whole-window | captions | adopt_default | 4 | `skills/hyperframes/references/captions.md:45`; `skills/hyperframes/references/types/vertical.md:7` |
| edl-single-clock | captions | adopt_default | 4 | `docs/guides/captions-and-recuts.mdx:116-117`; `packages/core/src/clipFacts.ts:33-35` |
| x264-delivery-settings | render-encode | adopt_default | 3 | `packages/engine/src/services/chunkEncoder.ts:55-59`; `packages/cli/src/commands/render/plan.ts:42-48` |
| sfx-peak-one-frame-after | audio | adopt_default | 3 | `skills/hyperframes/references/sound.md:36`; `packages/cli/src/commands/audio.ts:238-241` |
| blank-frame-and-render-regression | qc-review | adopt_default | 3 | `packages/cli/src/utils/craftAudit.ts:128-135`; `skills/hyperframes-cli/references/lint-validate-inspect.md:26` |
| hf-style-defaults-not-adopted | other | note_only | 1 | `docs/guides/rendering.mdx:312`; `skills/hyperframes/references/sound.md:43` |

### skill-design (24)

| id | step | proposal | value | evidence |
|---|---|---|---|---|
| ship-scripts-fill-plan | skill-structure | adopt_default | 5 | `.agents/skills/changelog-video/SKILL.md:32-48`; `.agents/skills/changelog-video/SKILL.md:46` |
| hard-gates-silent-loss | qc-review | adopt_default | 5 | `.agents/skills/changelog-video/SKILL.md:104-107`; `.agents/skills/changelog-video/SKILL.md:162-167` |
| re-edit-minimal-stage-set | re-edit-cache | adopt_default | 4 | `docs/prompting/editing-existing-videos.mdx:8`; `skills/hyperframes/references/storyboard.md:15` |
| stage-cache-sentinel | re-edit-cache | adopt_default | 4 | `packages/cli/src/media-use/lib/cache.mjs:16-18`; `packages/cli/src/media-use/lib/cache.mjs:68-77` |
| lessons-log-and-banned-list | skill-structure | adopt_default | 4 | `packages/cli/src/media-use/lib/misses.mjs:11-27`; `packages/cli/src/media-use/lib/stats.mjs:6` |
| review-measure-then-look | qc-review | adopt_default | 4 | `skills/hyperframes/references/review.md:3`; `skills/hyperframes/references/review.md:8` |
| render-verify-duration-frames | render-encode | adopt_default | 4 | `skills/hyperframes-cli/SKILL.md:35`; `skills/reverse-any-video/SKILL.md:18-19` |
| eval-corpus-ratchet | qc-review | adopt_optional | 4 | `skills/remotion-to-hyperframes/references/eval.md:68-75`; `skills/remotion-to-hyperframes/assets/test-corpus/tier-1-title-card/expected.json:25` |
| persistent-name-lexicon | transcribe | adopt_default | 4 | `.agents/skills/changelog-video/SKILL.md:73-74`; `.agents/skills/changelog-video/SKILL.md:118-120` |
| reference-study-frame-accurate | analysis-tooling | adopt_default | 4 | `skills/reverse-any-video/SKILL.md:21`; `skills/reverse-any-video/SKILL.md:19` |
| vertical-ui-safe-band | captions | adopt_default | 4 | `skills/hyperframes/references/types/vertical.md:7` |
| job-ledger-index | re-edit-cache | adopt_default | 3 | `skills/media-use/references/memory.md:33-34`; `packages/cli/src/media-use/lib/manifest.mjs:172-173` |
| user-edits-and-versioned-undo | re-edit-cache | adopt_default | 3 | `skills/hyperframes/SKILL.md:45`; `skills/hyperframes-cli/SKILL.md:52` |
| prefs-two-tier-promotion | re-edit-cache | adopt_default | 3 | `skills/media-use/references/memory.md:5`; `skills/media-use/references/memory.md:13` |
| frozen-looks | re-edit-cache | adopt_optional | 3 | `skills/media-use/references/memory.md:21`; `skills/media-use/references/memory.md:29` |
| qc-findings-fix-waiver | qc-review | adopt_default | 3 | `skills/hyperframes/SKILL.md:18`; `skills/hyperframes/references/review.md:7` |
| skill-router-budgets | skill-structure | adopt_default | 3 | `scripts/check-core-skills.mjs:12-23`; `skills/hyperframes/SKILL.md:58-74` |
| skill-lint-parity-tests | skill-structure | adopt_default | 3 | `scripts/lint-skills.ts:2-6`; `scripts/lint-skills.ts:72-75` |
| installed-copy-drift-hash | skill-structure | adopt_default | 3 | `packages/cli/src/utils/skillsManifest.ts:27-29`; `packages/cli/src/utils/skillsManifest.ts:233-247` |
| delivery-note-fallbacks | qc-review | adopt_default | 3 | `skills/media-use/SKILL.md:46`; `skills/media-use/SKILL.md:38` |
| copy-facts-trace-to-transcript | pick | adopt_default | 3 | `skills/hyperframes/references/story.md:12`; `skills/hyperframes/references/story.md:13` |
| sfx-library-manifest-health | audio | adopt_default | 3 | `packages/cli/src/media-use/lib/bundled-sfx-provider.mjs:47-77`; `skills/media-use/audio/assets/sfx/manifest.json:22-25` |
| lifecycle-retire-not-renumber | skill-structure | adopt_default | 2 | `packages/cli/src/utils/skillsManifest.ts:155-189`; `skills/hyperframes/references/skill-lifecycle.md:49` |
| script-io-conventions | preflight | adopt_default | 2 | `packages/cli/AGENTS.md:12-13`; `packages/cli/AGENTS.md:20-24` |

### sweep (25)

| id | step | proposal | value | evidence |
|---|---|---|---|---|
| amix-unity-sum | audio | adopt_default | 4 | `plans/spikes/amix-nesting-spike.sh:33`; `packages/engine/src/services/audioMixer.ts:955` |
| voice-over-music-margin | qc-review | adopt_default | 4 | `docs/packages/cli.mdx:811-816`; `packages/cli/src/audio/read/read.ts:161-180` |
| sfx-hit-alignment | audio | adopt_default | 4 | `docs/packages/cli.mdx:763-766`; `packages/core/src/audioAnalysis.ts:332-363` |
| cfr-seekable-intermediate | reframe | adopt_default | 4 | `releases/v0.8.156.md:15`; `releases/v0.7.29.md:29` |
| splice-microfades | audio | adopt_default | 3 | `packages/cli/src/media-use/lib/transcriptCutFade.mjs:5-8`; `packages/cli/src/media-use/lib/transcriptCutFade.mjs:13` |
| bt709-explicit-matrix | render-encode | adopt_default | 3 | `packages/engine/src/utils/sdrCaptureColor.ts:1-5`; `packages/studio-server/src/helpers/proxyTranscoder.ts:679` |
| hdr-source-gate | download | adopt_default | 3 | `packages/engine/src/utils/hdr.ts:16-21`; `docs/guides/hdr.mdx:71` |
| frame-coverage-gate | qc-review | adopt_default | 3 | `packages/producer/src/services/render/videoFrameCoverage.ts:7-13`; `packages/producer/src/services/render/videoFrameCoverage.ts:40-44` |
| frame0-thumbnail | captions | adopt_default | 3 | `packages/cli/src/utils/craftAudit.ts:116-138` |
| edge-coverage-overscan | accents-motion | adopt_default | 3 | `registry/components/camera-shake/camera-shake.html:690-691`; `registry/components/camera-shake/camera-shake.html:730` |
| critically-damped-follow | reframe | adopt_optional | 3 | `registry/components/cursor-zoom-follow/cursor-zoom-follow.html:551-567`; `registry/components/cursor-zoom-follow/cursor-zoom-follow.html:537-548` |
| accent-transition-kernels | accents-motion | adopt_optional | 3 | `registry/blocks/flash-through-white/flash-through-white.html:311`; `registry/blocks/whip-pan/whip-pan.html:311` |
| shutter-sampled-whip | accents-motion | adopt_default | 3 | `docs/guides/motion-blur.mdx:30-31`; `docs/guides/motion-blur.mdx:37` |
| whisper-word-repair | transcribe | adopt_default | 3 | `packages/cli/src/whisper/normalize.ts:96-99`; `packages/cli/src/whisper/normalize.ts:118` |
| windows-utf8-python | preflight | adopt_default | 3 | `skills/python-encoding.test.mjs:1-12`; `skills/media-use/audio/scripts/extract-audio-data.py:29-31` |
| ffmpeg-process-robustness | render-encode | adopt_default | 3 | `packages/studio-server/src/helpers/proxyTranscoder.ts:62-70`; `packages/studio-server/src/helpers/proxyTranscoder.ts:69` |
| prosody-annotated-transcript | pick | adopt_optional | 3 | `docs/packages/cli.mdx:804-819`; `docs/packages/cli.mdx:810-812` |
| sfx-variant-distinctness | qc-review | adopt_default | 3 | `packages/cli/src/audio/read/effects.ts:14`; `packages/cli/src/audio/read/effects.ts:178-184` |
| qc-sampling-design | qc-review | adopt_default | 3 | `packages/cli/src/utils/checkPipeline.ts:1890-1896`; `packages/cli/src/utils/craftAudit.ts:18` |
| reedit-absolute-targets | re-edit-cache | adopt_default | 3 | `docs/prompting/editing-existing-videos.mdx:8`; `docs/prompting/editing-existing-videos.mdx:10` |
| spectral-carve-bed | audio | adopt_optional | 2 | `docs/studio/audio-effects.mdx:171-172`; `docs/studio/audio-effects.mdx:210` |
| caption-legibility-qc | captions | adopt_optional | 2 | `packages/cli/src/commands/contrast-sample.ts:6-8`; `packages/cli/src/commands/contrast-bg.ts:42-44` |
| skill-doc-contract-tests | skill-structure | adopt_default | 2 | `scripts/creator-editing-capabilities.test.mjs:43-56`; `scripts/creator-editing-capabilities.test.mjs:129` |
| asr-prep-robustness | transcribe | adopt_optional | 2 | `packages/cli/src/whisper/transcribe.ts:186-198`; `packages/cli/src/whisper/transcribe.ts:33` |
| source-bed-clash | audio | adopt_optional | 2 | `packages/core/src/audioAnalysis.ts:600-617`; `packages/core/src/audioAnalysis.ts:554-555` |

## Port candidates (algorithms worth re-implementing)

| name | value | source files | found by |
|---|---|---|---|
| caption_chunker_layout | 4 | `registry/components/caption-neon-accent/caption-neon-accent.html`, `registry/components/caption-pill-karaoke/caption-pill-karaoke.html`, `registry/components/caption-emoji-pop/caption-emoji-pop.html` | captions |
| align_display_tokens | 4 | `.agents/skills/changelog-video/scripts/align-captions.mjs`, `.agents/skills/changelog-video/references/script-voice.md` | captions |
| dropped_speech_gap_repair | 4 | `packages/cli/src/whisper/parakeet.ts`, `packages/cli/src/whisper/sherpaWorker.ts` | captions |
| cutlist_and_caption_remap | 4 | `packages/cli/src/media-use/lib/cutlist.mjs`, `skills/media-use/scripts/transcript-cut.mjs`, `packages/cli/src/media-use/lib/transcriptCutFade.mjs` | captions |
| normalize_asr_words | 3 | `packages/cli/src/whisper/normalize.ts`, `packages/cli/src/media-use/lib/parakeet-words.mjs`, `skills/media-use/audio/references/captions/transcript-handling.md` | captions |
| caption_contrast_ratio | 3 | `packages/cli/src/commands/contrast-sample.ts`, `packages/cli/src/commands/contrast-audit.browser.js`, `packages/cli/src/utils/contrastMotion.ts` | captions |
| zone_and_face_overlap_checks | 3 | `packages/cli/src/utils/checkPipeline.ts`, `skills/hyperframes/references/types/vertical.md`, `packages/studio/src/utils/previewSafeMargins.ts` | captions |
| reading_and_type_floor | 2 | `packages/cli/src/utils/craftAudit.ts` | captions |
| compile_cut_list (transcript-cut compiler, clip-window variant) | 5 | `packages/cli/src/media-use/lib/cutlist.mjs`, `packages/cli/src/media-use/lib/words.mjs`, `packages/cli/src/media-use/lib/cutlist.test.mjs` | transcript-cutting |
| splice_render (fade ramps + PCM .mov intermediates + one-encode concat) | 5 | `packages/cli/src/media-use/lib/transcriptCutFade.mjs`, `skills/media-use/scripts/transcript-cut.mjs` | transcript-cutting |
| dropped_speech_repair (quiet-point windows + energy-checked gap re-decode) | 5 | `packages/cli/src/whisper/parakeet.ts`, `packages/cli/src/whisper/sherpaWorker.ts` | transcript-cutting |
| remap_through_cutlist (+ re-ASR caption timing check) | 5 | `packages/cli/src/media-use/lib/cutlist.mjs`, `docs/guides/captions-and-recuts.mdx` | transcript-cutting |
| normalize_and_vet_words (fragment merge, zero-duration repair, failure gate, hallucinated tail) | 4 | `packages/cli/src/whisper/normalize.ts`, `skills/media-use/audio/references/captions/transcript-handling.md`, `skills/hyperframes/references/captions.md` | transcript-cutting |
| speech_activity_floor (energy VAD used to verify dead air) | 4 | `packages/cli/src/audio/read/voice.ts`, `packages/cli/src/audio/read/signal.ts` | transcript-cutting |
| hard_cut_detector (64x36 grey MAD with soft/flash/fast classes) | 4 | `packages/cli/src/measure/cuts.ts`, `packages/cli/src/measure/media.ts`, `packages/cli/src/commands/measure/cuts.ts` | transcript-cutting |
| splice_qc_suite | 4 | `skills/media-use/scripts/transcript-cut.test.mjs` | transcript-cutting |
| av_sync_lag (mouth motion vs loudness change) | 3 | `packages/cli/src/measure/sync.ts` | transcript-cutting |
| word_span_duck + level_match_duck (+ optional static voice carve) | 3 | `packages/cli/src/media-use/lib/duck.mjs`, `packages/core/src/audioCarve.ts`, `skills/media-use/audio/scripts/carve.mjs` | transcript-cutting |
| volume_keyframe_simplify (RDP + 32-segment cap + nested-if expression) | 3 | `packages/engine/src/services/audioMixer.ts` | transcript-cutting |
| atempo_chain_and_rate_integral | 2 | `packages/engine/src/services/audioMixer.ts`, `packages/core/src/speedRamp.ts`, `packages/core/src/audioAutomation.ts` | transcript-cutting |
| sentence_ending_intonation (YIN pitch, rising/falling end) | 2 | `packages/core/src/audioPitch.ts`, `packages/cli/src/audio/read/voice.ts` | transcript-cutting |
| transcript_duck_envelope (with speech-activity union) | 5 | `packages/cli/src/media-use/lib/duck.mjs`, `skills/media-use/scripts/audio-duck.mjs`, `packages/cli/src/audio/read/voice.ts` | audio |
| sfx_moments (hit-point locator) | 4 | `packages/core/src/audioAnalysis.ts`, `docs/packages/cli.mdx` | audio |
| aac_true_peak_gate_and_exact_length | 4 | `packages/producer/src/services/render/audioPadTrim.ts`, `packages/producer/src/services/render/audioTruePeak.ts`, `packages/engine/src/services/aacEncode.ts` | audio |
| cutlist_with_splice_fades | 4 | `packages/cli/src/media-use/lib/cutlist.mjs`, `packages/cli/src/media-use/lib/transcriptCutFade.mjs`, `skills/media-use/scripts/transcript-cut.mjs` | audio |
| av_sync_lag (mouth motion vs audio energy) | 4 | `packages/cli/src/measure/sync.ts` | audio |
| voice_carve (spectral bands + relative-headroom level duck) | 3 | `packages/core/src/audioCarve.ts`, `skills/media-use/audio/scripts/carve.mjs` | audio |
| onsets_spectral_flux | 3 | `packages/core/src/audioAnalysis.ts` | audio |
| beat_tracker_ellis (beats, confidence, tempo, downbeats) | 3 | `packages/core/src/audioRhythm.ts`, `packages/core/src/beats/beatDetection.ts`, `packages/cli/src/audio/analysis/analyze.ts` | audio |
| even_out_leveller | 3 | `packages/core/src/audioLeveller.ts` | audio |
| bs1770_meter (integrated/short-term LUFS, 4x true peak, clipping, silence) | 3 | `packages/core/src/audioAnalysis.ts` | audio |
| sfx_event_detector_and_print (for reference analysis and the reuse QC) | 3 | `packages/cli/src/audio/read/effects.ts`, `packages/cli/src/audio/read/signal.ts` | audio |
| openverse_sfx_pick | 3 | `skills/media-use/audio/scripts/lib/openverse.mjs`, `skills/media-use/audio/references/sfx.md` | audio |
| foote_sections_with_beat_snap | 2 | `packages/core/src/audioSections.ts`, `packages/core/src/audioSnap.ts` | audio |
| signalstats_source_diagnosis | 4 | `packages/core/src/mediaGradeAnalyzer.ts`, `packages/cli/src/media-use/lib/grade-analyzer.mjs`, `packages/cli/src/media-use/lib/grade-analyzer.test.mjs` | grade-look |
| hdr_to_sdr_tonemap_chain | 4 | `packages/core/src/hdrToneMap.ts`, `packages/core/src/hdrToneMap.test.ts`, `packages/engine/src/utils/hdr.ts` | grade-look |
| primary_grade_lut_bake | 4 | `packages/core/src/colorGradingBake.ts`, `packages/core/src/colorGradingBake.test.ts`, `packages/core/src/runtime/colorGrading.ts` | grade-look |
| untagged_matrix_guess_and_explicit_rgb_hops | 3 | `packages/engine/src/services/videoFrameExtractor.ts`, `packages/engine/src/utils/sdrCaptureColor.ts`, `packages/engine/src/services/chunkEncoder.ts` | grade-look |
| thresholded_half_res_bloom | 3 | `packages/core/src/runtime/colorGrading.ts`, `packages/core/src/colorGrading.ts` | grade-look |
| hsl_secondary_qualifier_and_skin_key | 3 | `packages/core/src/colorGrading.ts`, `packages/core/src/colorGradingBake.ts`, `packages/studio/src/components/editor/colorGradingFrameAnalysis.ts` | grade-look |
| monotone_pchip_curve_compiler | 2 | `packages/core/src/colorGradingCurves.ts` | grade-look |
| cube_validator_and_atomic_freeze | 2 | `packages/cli/src/media-use/lib/cube-validate.mjs`, `packages/core/src/colorLuts.ts`, `packages/cli/src/media-use/lib/lut-preset-provider.mjs` | grade-look |
| aspect_aware_squircle_vignette | 2 | `packages/core/src/runtime/colorGrading.ts`, `packages/core/src/colorGrading.ts` | grade-look |
| luma_masked_deterministic_grain | 2 | `packages/core/src/runtime/colorGrading.ts`, `packages/core/src/colorGrading.ts` | grade-look |
| labelled_compare_grid_layout | 2 | `packages/cli/src/commands/grade-compare.ts`, `packages/cli/src/commands/snapshotSampling.ts` | grade-look |
| Adaptive shot-cut detector with flash/fast classification | 5 | `packages/cli/src/measure/cuts.ts`, `packages/cli/src/measure/media.ts`, `packages/cli/src/commands/measure/cuts.ts` | measure-reverse |
| Planned-EDL vs detected cut matcher with soft-cut confirmation | 5 | `packages/cli/src/measure/diff.ts`, `packages/cli/src/measure/cuts.ts` | measure-reverse |
| Probe and CFR/SDR normalize | 5 | `packages/cli/src/measure/media.ts`, `packages/cli/src/commands/measure/probe.ts` | measure-reverse |
| Audio offset check and clip-in-source locator | 5 | `packages/cli/src/measure/diff.ts`, `packages/cli/src/measure/person.ts`, `packages/cli/src/measure/diff-people.test.ts` | measure-reverse |
| Mouth-motion vs voice lag estimator (A/V sync) and gate | 4 | `packages/cli/src/measure/sync.ts`, `packages/cli/src/measure/person.ts`, `packages/cli/src/measure/sync.test.ts` | measure-reverse |
| Look metrics and comparison | 4 | `packages/cli/src/measure/look.ts`, `packages/cli/src/measure/media.ts`, `packages/cli/src/measure/compare.test.ts` | measure-reverse |
| Screen-event detector (cut, flash, appear/disappear, change, hold), look windows and onset-keeping strips | 4 | `packages/cli/src/measure/events.ts`, `packages/cli/src/commands/measure/frames.ts`, `packages/cli/src/commands/measure/events.ts` | measure-reverse |
| Per-shot framing medians and face-fit transform | 4 | `packages/cli/src/measure/person.ts`, `packages/cli/src/measure/face.ts`, `packages/cli/src/measure/diff.test.ts` | measure-reverse |
| Local-contrast ink detector, text line bands and drawn-element F1 | 3 | `packages/cli/src/measure/drawn.ts`, `packages/cli/src/measure/ink.ts`, `packages/cli/src/measure/drawn.test.ts` | measure-reverse |
| Ease and pulse fitter for one element's move | 3 | `packages/cli/src/measure/curve.ts`, `packages/cli/src/measure/curve.test.ts` | measure-reverse |
| Whole-frame + 4x4-cell SSIM diff with missing-content check | 3 | `packages/cli/src/measure/diff.ts`, `skills/remotion-to-hyperframes/references/eval.md` | measure-reverse |
| Spectral-flux onset detector | 3 | `packages/core/src/audioAnalysis.ts`, `packages/cli/src/commands/measure/events.ts` | measure-reverse |
| Motion-energy curve and comparison | 2 | `packages/cli/src/measure/energy.ts`, `packages/cli/src/measure/compare.test.ts` | measure-reverse |
| shot-change-classifier (measure cuts) | 5 | `packages/cli/src/measure/cuts.ts`, `packages/cli/src/measure/media.ts` | motion-editing |
| transcript-cut-compiler (cut list + splice fades + segment encoder) | 5 | `packages/cli/src/media-use/lib/cutlist.mjs`, `packages/cli/src/media-use/lib/transcriptCutFade.mjs`, `skills/media-use/scripts/transcript-cut.mjs` | motion-editing |
| roi-event-detector (measure events) | 4 | `packages/cli/src/measure/events.ts`, `packages/cli/src/measure/cuts.ts` | motion-editing |
| av-sync-estimator (measure sync) | 4 | `packages/cli/src/measure/sync.ts` | motion-editing |
| seam-audit (seam-gate adapted to crop/transform tracks) | 3 | `.agents/skills/motion-doctrine/scripts/seam-gate.mjs`, `.agents/skills/motion-doctrine/references/seam-gate.md` | motion-editing |
| ease-library-and-move-fitter (measure curve) | 3 | `packages/cli/src/measure/curve.ts` | motion-editing |
| shutter-supersampled-motion-blur | 3 | `registry/components/motion-blur/motion-blur.html`, `docs/guides/motion-blur.mdx`, `skills/hyperframes/references/motion.md` | motion-editing |
| transition-frame-generators (whip, radial zoom, white dip, strip whip) | 3 | `packages/shader-transitions/src/shaders/registry.ts`, `packages/shader-transitions/src/hyper-shader.ts`, `registry/components/whip-pan-cut/whip-pan-cut.html` | motion-editing |
| sfx-hit-detector (onset and peak of a sound file) | 3 | `packages/cli/src/audio/read/effects.ts`, `packages/cli/src/audio/read/signal.ts` | motion-editing |
| seam-strip-and-phone-sheet-planner (snapshot --review) | 3 | `packages/cli/src/commands/snapshotReview.ts`, `skills/hyperframes/references/review.md` | motion-editing |
| beat-grid-and-snapper | 2 | `skills/hyperframes/references/motion.md`, `packages/core/src/audioSnap.ts`, `packages/core/src/beats/beatDetection.ts` | motion-editing |
| pad_or_trim_audio_and_enforce_true_peak | 5 | `packages/producer/src/services/render/audioPadTrim.ts`, `packages/producer/src/services/render/audioTruePeak.ts`, `packages/engine/src/services/aacEncode.ts` | render-qc |
| fps_and_frame_grid_math | 4 | `packages/core/src/fps.ts`, `packages/engine/src/services/videoFrameExtractor.ts`, `packages/cli/src/commands/measure/probe.ts` | render-qc |
| classified_cuts | 4 | `packages/cli/src/measure/cuts.ts`, `packages/cli/src/commands/measure/cuts.ts`, `packages/cli/src/measure/media.ts` | render-qc |
| av_sync_lag | 4 | `packages/cli/src/measure/sync.ts`, `packages/cli/src/commands/measure/sync.ts`, `packages/cli/src/measure/media.ts` | render-qc |
| render_artifact_gate | 4 | `packages/producer/src/services/render/artifactTransaction.ts`, `packages/core/src/renameWithRetry.ts` | render-qc |
| review_sheet_plan | 4 | `packages/cli/src/commands/snapshotReview.ts`, `packages/cli/src/commands/measure/frames.ts`, `packages/cli/src/commands/snapshot.ts` | render-qc |
| source_colour_normalisation_filters | 4 | `packages/engine/src/utils/hdr.ts`, `packages/core/src/hdrToneMap.ts`, `packages/engine/src/services/videoFrameExtractor.ts` | render-qc |
| decoded_media_durations | 3 | `packages/engine/src/utils/ffprobe.ts`, `packages/cli/src/measure/media.ts` | render-qc |
| audio_mux_integrity | 3 | `packages/producer/src/utils/audioRegression.ts`, `packages/producer/tests/audio-mux-parity/meta.json` | render-qc |
| segment_coverage_gate | 3 | `packages/producer/src/services/render/videoFrameCoverage.ts`, `packages/engine/src/services/videoFrameExtractor.ts` | render-qc |
| black_dropout_diff | 3 | `packages/engine/src/utils/gpuParityDiff.ts`, `packages/cli/src/measure/diff.ts`, `packages/engine/src/utils/psnr.ts` | render-qc |
| stage_cache_commit | 3 | `packages/engine/src/services/extractionCache.ts`, `packages/engine/src/services/videoFrameExtractor.ts`, `packages/producer/src/services/render/stages/freezePlan.ts` | render-qc |
| cut_classifier (hard and soft cuts, flashes, whips) | 5 | `packages/cli/src/measure/cuts.ts`, `packages/cli/src/measure/media.ts` | skill-design |
| caption_presence_gate | 5 | `.agents/skills/changelog-video/SKILL.md`, `packages/cli/src/measure/events.ts`, `skills/hyperframes/references/captions.md` | skill-design |
| stage_cache (schema-prefixed, sentinel-validated) | 4 | `packages/cli/src/media-use/lib/cache.mjs`, `packages/cli/src/media-use/lib/manifest.mjs`, `packages/cli/src/media-use/lib/candidates.mjs` | skill-design |
| lessons_log + stats | 4 | `packages/cli/src/media-use/lib/misses.mjs`, `packages/cli/src/media-use/lib/stats.mjs` | skill-design |
| prefs_store (two-tier remembered defaults) | 3 | `packages/cli/src/media-use/lib/prefs-store.mjs`, `packages/cli/src/media-use/lib/config-lock.mjs`, `skills/media-use/scripts/prefs.mjs` | skill-design |
| skill_bundle_hash (drift detection) | 3 | `packages/cli/src/utils/skillsManifest.ts`, `packages/cli/scripts/gen-skills-manifest.ts`, `packages/cli/src/utils/skillsUpdateCheck.ts` | skill-design |
| skill_lint | 3 | `scripts/lint-skills.ts`, `scripts/check-core-skills.mjs`, `scripts/check-skill-import-boundaries.test.mjs` | skill-design |
| job_ledger (append-only JSONL, id allocation, INDEX.md) | 3 | `packages/cli/src/media-use/lib/manifest.mjs`, `packages/cli/src/media-use/lib/index-gen.mjs` | skill-design |
| golden_render_diff | 3 | `packages/cli/src/measure/diff.ts`, `skills/remotion-to-hyperframes/references/eval.md`, `skills/remotion-to-hyperframes/assets/test-corpus/tier-1-title-card/expected.json` | skill-design |
| ratchet_gate (2-of-3 regression gate for the eval corpus) | 3 | `packages/studio/tests/e2e/edit-accuracy/ratchet.mjs`, `scripts/ci/edit-accuracy-shard.sh` | skill-design |
| look_store (frozen versioned recipes) | 3 | `packages/cli/src/media-use/lib/recipe-store.mjs`, `skills/media-use/scripts/recipe.mjs` | skill-design |
| Sound moments, silence spans and silent-window check | 4 | `packages/core/src/audioAnalysis.ts`, `packages/cli/src/utils/checkAudio.ts` | sweep |
| BS.1770 integrated/short-term loudness + 4x true peak (numpy) | 3 | `packages/core/src/audioAnalysis.ts` | sweep |
| Sound-effect event detector, kind classifier and same-sound grouping | 3 | `packages/cli/src/audio/read/effects.ts`, `packages/cli/src/audio/read/signal.ts` | sweep |
| Prosody reader: sentences, rate, YIN pitch, rising/falling ends, pauses | 3 | `packages/cli/src/audio/read/voice.ts`, `packages/core/src/audioPitch.ts`, `packages/cli/src/audio/read/format.ts` | sweep |
| Whisper word repair | 3 | `packages/cli/src/whisper/normalize.ts` | sweep |
| Critically damped follow camera with look-ahead and edge clamp | 3 | `registry/components/cursor-zoom-follow/cursor-zoom-follow.html` | sweep |
| Accent transition kernels (flash-through-white, whip, radial zoom, light leak, camera flash) | 3 | `registry/blocks/flash-through-white/flash-through-white.html`, `registry/blocks/whip-pan/whip-pan.html`, `registry/blocks/cinematic-zoom/cinematic-zoom.html` | sweep |
| amix-safe mix graph and null test | 3 | `packages/engine/src/services/audioMixer.ts`, `plans/spikes/amix-nesting-spike.sh` | sweep |
| Voice/music/sfx kind guess (source-bed check) | 2 | `packages/core/src/audioAnalysis.ts` | sweep |
| Overscan solver for plate transforms | 2 | `registry/components/camera-shake/camera-shake.html` | sweep |
| Craft audit (frame 0, line holds, dead stretches, type floor) | 2 | `packages/cli/src/utils/craftAudit.ts`, `packages/cli/src/utils/checkPipeline.ts` | sweep |
| Caption contrast audit with fill hidden | 2 | `packages/cli/src/commands/contrast-bg.ts`, `packages/cli/src/commands/contrast-sample.ts` | sweep |
| Speech-onset intro detector | 2 | `packages/cli/src/whisper/transcribe.ts` | sweep |
| Frame coverage gate | 2 | `packages/producer/src/services/render/videoFrameCoverage.ts` | sweep |
