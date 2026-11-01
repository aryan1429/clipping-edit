# 03 - HyperFrames study: media pipeline (intake, cutting, audio, encode)

Studied from HeyGen HyperFrames (https://github.com/heygen-com/hyperframes, Apache-2.0, (c) 2026 HeyGen, Inc.) at commit 8c22ddb (2026-11-01). The method, raw notes and full learning index are in `analysis/repos/hyperframes.md` (repo-relative; not part of the installed skill).

**Precedence.** Ref 01 wins on style: canvas, caption look, accents, grade targets, pacing and ending. Ref 02 wins on moment-picking and job layout. The SKILL.md Defaults table is fixed. Refs 03-05 win on technical correctness where 01/02 are silent or vague: timing and sync, cutting and splicing, audio levels and mixing, encode/mux and colour metadata, QC gates and job hygiene. A rule that changes an older one says "Refines ... (old: ...)".

**Reading the rules.** "HF: path:lines" cites the HyperFrames repo at that commit. "Tested" or "here" means measured with ffmpeg 7.1 on synthetic lavfi media while this reference was written. Pointers like "→ ref 03 §2 **Frame grid**" name the section and the rule's bold title.

## 1. Source intake: probe, normalise, ASR words
Scope: download → `source_facts.json`, one normalised intermediate per clip, `transcript.json`.

### Adopted (default)
1. **Probe once.** Write `source_facts.json`:
   - displayed W × H = the picture `norm_vf` outputs (swap if rotation % 180 = 90, then the SAR squared to an even width: 320×240 at SAR 4:3 → 426×240), SAR `N:D`, clockwise rotation, duration; `fps_r` and `fps_avg` as `num/den`, `vfr` = |avg − r|/r > 1%;
   - matrix, primaries, transfer, range; an untagged matrix is bt709 if H ≥ 720 and the codec is not VP9/AV1, else smpte170m.
   - audio: codec, rate, channels, layout, `start_vs_video_s` (first decoded audio frame − first video frame; warn when > 1 ms). It is precise to one audio frame only (→ **ASR on the video's clock** for the true offset).
   - No ffprobe: parse `ffmpeg -hide_banner -i SRC` stderr (`N fps` = avg, `N tbr` = r; W × H = the comma part matching `^\d+x\d+`). Snap a printed rate p to round(p) if within 0.005, else to n × 1000/1001 (n = round(1.001p)) if within 0.005.
   - On exit 1 (HDR/BT.2020 without `zscale`, no video, ASR offset) the facts are still written with `ok: false` and the error; `norm_vf` is null when it cannot be built, so no stale `norm_vf` survives a failed rerun.
   - Implemented by `scripts/probe_source.py` (`norm_vf`, `canvas_fps` and `asr_offset_s` included; untested: the ffprobe path, every test ran on the ffmpeg-only fallback).
   Why: every later step reads these facts instead of probing again.
   HF: packages/cli/src/measure/media.ts:109-134; packages/engine/src/services/videoFrameExtractor.ts:220-227,971-979
2. **SDR at download.** Refines SKILL step 1 (old: "the best mp4"):
   `-f "bv[dynamic_range=SDR][ext=mp4]+ba[ext=m4a]/bv[dynamic_range=SDR]+ba/bv*+ba/b"`
   - HDR = transfer `smpte2084` or `arib-std-b67`; BT.2020 primaries alone are SDR (converted in **Normalise in every clip intermediate**).
   - An HDR-only format list falls back to HDR video (→ **HDR fallback**).
   Why: yt-dlp sorts HDR first ("best mp4" took AV1 HDR10 in a test); `bv` (video-only) skips the 360p combined SDR file that `bv*` picked over 4K HDR-only video. Tested on mock format lists (yt-dlp 2026.08.19): SDR mp4 + m4a when offered; a missing `dynamic_range` counts as SDR. AV1 SDR (often first) decodes in software here (libaom: 120/120 frames).
   HF: packages/engine/src/utils/hdr.ts:16-21
3. **Normalise in every clip intermediate.** Per clip, write one video-only intermediate of the source window [W0, W1] through `norm_vf`. Face tracks and cut detection read only it; the splice reads SRC through the same `norm_vf` (→ ref 03 §2 **Video splice**), so all three share canvas frame k. cv2 never opens the raw download.
   - W0 = max(0, ⌊A⌋ − 1), W1 = min(duration, ⌈B⌉ + 1) for the clip window [A, B] in source seconds. Whole seconds keep local frame j = source frame k − W0·fps exact at the 60/30 canvas, and leave ≥ 0.5 s for the cut detector (→ ref 04 §2 **Classified cut detector**).
   - `ffmpeg -ss W0 -i SRC -t <W1 − W0> -vf "<norm_vf>" <flags> clip.mov`; flags → ref 03 §4 **Seekable mezzanine**.
   - `norm_vf`, in this order:
     - `fps=<canvas>` first;
     - `scale=trunc(iw*sar/2)*2:ih,setsar=1` if SAR ≠ 1;
     - colour, one of: HDR → **HDR fallback**; SDR BT.2020 (primaries or matrix bt2020*, non-HDR transfer) → that chain's tail from `zscale=p=bt709`; a non-709 matrix (smpte170m/bt470bg → bt601, smpte240m, fcc, or the untagged guess) or pc range → `scale=in_color_matrix=<m>:in_range=<tv|pc>:out_color_matrix=bt709:out_range=tv:flags=accurate_rnd+full_chroma_int` (pc for `yuvj*` or a pc tag); an RGB source (PNG, ProRes 4444; ours) → `scale=out_color_matrix=bt709:out_range=tv:flags=accurate_rnd+full_chroma_int`;
     - last `setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv`.
   - `norm_vf` is built by `scripts/probe_source.py`; no script writes the intermediate yet.
   - Tested: 7.1 negotiates the range, not the matrix. A relabel-only read (`fps` + the final `setparams`) of a pc-range BT.709 source, and of an RGB source, decoded right; relabelled BT.601 still read (255,23,0). The explicit `in_range` and RGB steps stay for builds without that negotiation.
   - Canvas: refines ref 01 §1 (old: "60 fps if the source is 50/60, otherwise 30"): source fps = `fps_avg`, so 60 when `fps_avg` ≥ 50. The Defaults Canvas row stands.
   - Re-time only with `fps=`; never relabel the rate (input `-r`, `setpts=PTS*k`): 0.1% = 60 ms/min drift.
   Why: cv2 indexed VFR at 48.16 fps, up to 0.488 s off. Scale-then-fps lost a frame (89 of 90); a 30+60 fps VFR join put a cut at 1.983 s without `fps=` first, 2.000 s with it. Relabelled BT.601 red decoded (255,23,0), converted (251,0,0); BT.2020 (200,60,40) relabelled read (171,87,52), converted (199,58,39). A full-range BT.601 VP9 card read 17 off without `in_range`, 5 with it, 2 with the flags.
   HF: packages/cli/src/commands/measure/probe.ts:46-66; packages/engine/src/services/videoFrameExtractor.ts:1171-1173
4. **HDR fallback.**
   - `zscale=t=linear:npl=100,tonemap=hable:desat=0,zscale=p=bt709:t=bt709:m=bt709:r=tv,scale=out_color_matrix=bt709:out_range=tv`;
   - tags missing on frame 0 (`-frames:v 1 -vf showinfo`): prefix `setparams=` from the probe, else bt2020nc/bt2020; an SDR BT.2020 frame with no transfer tag also gets `color_trc=bt2020-10` (ours); untagged, zscale fails ("no path between colorspaces");
   - no `zscale`/`tonemap` in `ffmpeg -hide_banner -filters`: exit 1 (`hdr_no_zscale`, or `bt2020_no_zscale`: SDR BT.2020 needs `zscale` too), `norm_vf` null, with a fix hint (re-download SDR or an ffmpeg build with zimg).
   - Refines ref 01 §0.3 (old: "Measure source against output"): HDR source frames = this SDR copy.
   - Implemented by `scripts/probe_source.py`.
   - Tested: 7.1's H.264 decoder copies container `colr` tags onto frames when the VUI has none (a VUI-less PQ stream in `.mov` with `colr` gave frame 0 bt2020nc/bt2020/smpte2084), so the fill acts on partly tagged bitstreams (VUI fields unspecified), not on `colr`-only files. Without the `bt2020-10` fill, an untagged SDR BT.2020 transfer failed in zscale.
   Why: PQ read as SDR: SATAVG 23 vs 64 tone-mapped; unnamed matrix: pure red/green Y 73/181, not 63/173.
   HF: packages/core/src/hdrToneMap.ts:15-43; packages/studio-server/src/helpers/proxyTranscoder.ts:679-686
5. **ASR on the video's clock.** Refines SKILL Generic gotchas (old: "decode with ffmpeg to 16 kHz mono float32"): always decode ASR audio with ffmpeg and pass the array to `transcribe()`:
   `-vn -af "aresample=async=1:first_pts=0,pan=mono|c0=0.5*c0+0.5*c1" -ar 16000 -f f32le -` (mono source: `pan=mono|c0=c0`)
   - `async=1:first_pts=0` goes on every decode that maps word times to samples: this one and ref 03 §2 **Dialogue stem**.
   - Offset of the video file's audio vs the ASR audio: 20 s windows at start, middle and end (same filter, `-ar 8000`); rises of 10 ms RMS; Pearson over ±500 ms (≥ 50 values); r ≤ 0.3 is not judged; take the median (HF: first 20 s only).
   - Sign: pair the SRC curve at i + lag with the ASR curve at i, so + lag = the video's audio is late (HF's spec never says which curve is a; with a = SRC its formula reads late audio as negative).
   - |offset| > 1 canvas frame: add it to every word time. `probe_source.py --asr-audio` writes it as `asr_offset_s` and exits 1 (`asr_offset`).
   - Never take the offset from timestamps: a late AAC stream's first decoded frame carries the encoder priming.
   Why: audio muxed 0.25 s late decoded 0.23 s early without the filter (~14 frames at 60 fps; PyAV too). Tested with the pairing above: SRC delayed 40 ms read +40 ms, `-itsoffset 0.25` read +250 ms, while that file's first decoded AAC frame said 0.228 s.
   HF: packages/cli/src/measure/diff.ts:1059-1100
6. **Language and names.** Pass `language=` (yt-dlp `language`, else `detect_language` on 30 s of speech); `.en` models only for `en`; speech over music or crowd starts at `medium`.
   - Refines SKILL Tool discovery (old: "`medium` for better accuracy on bigger GPUs").
   - Metadata names go to the caption cleanup (→ ref 04 §1 **Token timing contract**), never to `hotwords`/`initial_prompt`.
   Why: `.en` models translate (HF); on noise `detect_language` said `nn` (p 0.45-0.53); seeded names landed in noise.
   HF: skills/media-use/audio/references/transcribe.md:14-22,37; .agents/skills/changelog-video/SKILL.md:118-120
7. **Normalise words.** Keep `raw_words.json`; `transcript.json` =
   - drop non-words (the junk of **Failure gate + hallucinations**): empty, `[_`/`[BLANK`, only ♪/�; fillers stay (→ ref 03 §2 **Fillers: safe list**);
   - join punctuation-only, `'t 'm 's 've 're 'll 'd` and no-leading-space tokens to the previous word; merge a lone capital (not I/A/O) + a lowercase word, and a lowercase end + `in'`;
   - spread start ≥ end runs evenly from the previous end to the next start (0.3 s/word at the end); round to ms;
   - ≥ 1 canvas frame between starts, shifting ≤ 2 frames (threshold ours);
   - clamp start ≥ 0, end = min(dur, max(start, end)); flag spans < 0.05 s; ids `w0..wN`; text fixes key on ids, never re-match by string (→ ref 04 §1 **Token timing contract**); assert starts are non-decreasing.
   Why: zero-length runs pop together (seeded `tiny`: 184-186 words, 178-183 zero-length); text matching gives a repeated word the wrong time.
   HF: packages/cli/src/whisper/normalize.ts:70-149,162-164,529-543; skills/media-use/audio/references/captions/transcript-handling.md:31; skills/hyperframes/references/captions.md:9
8. **Failure gate + hallucinations.** New SKILL step 2 gate:
   - 0 words in the file, or a word without start/end: failed (HF: word timings are a hard gate).
   - Per 60 s window, junk > 20% of raw entries: re-run with the next model (small → medium → large-v3). LLM-flagged nonsense while picking: same, then re-pick.
   - `silencedetect=noise=-35dB:d=0.6`: drop words starting in the final silence (`silence_end` absent or ≥ duration − 0.05; 7.1 prints it at EOF).
   - In other silences, drop stock phrases (you, thank you, thanks for watching, subscribe, subtitles by) and metadata names starting in [start, end − 0.3 s] (not in HF).
   Why: Whisper invents "Thank you." over silence (HF); the seeded loop sat in the final silence (0% junk).
   HF: skills/hyperframes/references/captions.md:8-10; .agents/skills/changelog-video/SKILL.md:104-109
9. **Dropped-speech repair.**
   - Cut ~60 s windows at the quietest 100 ms within ±5 s.
   - A gap ≥ 1.0 s (edges count) with mean(x²) > 0.3 × the window's is skipped speech; a window with 0 words is one gap, tested against the file's mean (threshold ours).
   - Re-decode [g0 − 0.5, g1 + 0.5] after 0.5 s of zeros (`vad_filter=False, condition_on_previous_text=False`); t → max(0, t − 0.5) + lo.
   - Add words starting in the gap, minus neighbours re-heard within 0.3 s of an edge (letters-only match); **Normalise words** and **Failure gate + hallucinations** apply. None added: re-decode the padded window; keep it if it has more words.
   - Leftovers → `suspect_gaps`: no captions, never dead air (→ ref 03 §2 **Dead air**).
   Why: skipped speech = missing captions + cuts through it.
   HF: packages/cli/src/whisper/parakeet.ts:153-274; packages/cli/src/whisper/sherpaWorker.ts:30-81
10. **Script hygiene.** Refines SKILL Generic gotchas (old: "Set `PYTHONIOENCODING=utf8`"):
    - `for s in (sys.stdout, sys.stderr): s.reconfigure(encoding="utf-8", errors=s.errors)`; `encoding="utf-8"` on text IO; subprocess `errors="replace"`;
    - one JSON object on stdout, logs on stderr; exit 0 ok, 1 a step or gate failed, 2 usage error or unreadable input;
    - background job logs end `DONE ok|fail`; wait on that line, never `pgrep -f`.
    - Implemented by `scripts/cliplib.py` (UTF-8 stdio, `run_main`, `ClipError` with exit 1/2) for every shipped script; each prints `{ok, version, ...}`.
    Why: on Windows a non-cp1252 glyph printed to a pipe exited 1; `open()` defaulted to cp1252.
    HF: skills/media-use/audio/scripts/extract-audio-data.py:25-31,60-65; packages/cli/AGENTS.md:12-26; skills/hyperframes-cli/SKILL.md:66

### Optional
- **Parakeet engine.** With `sherpa_onnx` + the int8 `parakeet-tdt-0.6b-v3` export (25 languages): `nemo_transducer`, greedy search, 16 kHz, 80-dim features, 4 threads; then **Normalise words** onward. HF's WER/speed claims are unverified: A/B on 2-3 sources first.
  HF: packages/cli/src/whisper/sherpa.ts:338-354; packages/cli/src/whisper/parakeet.ts:4-8,33-35

## 2. Cut list and splicing: frame-exact, click-free, one clock
Scope: word ids → `cutlist.json` → video-only `cut.mov` + one dialogue stem; one clock for every later time.

### Adopted (default)
1. **Cut points by word id.** `transcript_lines.txt` lines start `[w812-w840] mm:ss  SPEAKER:`. The LLM writes `start_word`, `end_word`, `remove_words: [[i, j]]` (inclusive) and `keep_gaps: [i]` (keep the pause after word i: a visual payoff); never seconds.
   - `scripts/cutlist.py` fills `start`/`end` (ref 02: −0.05/+0.15 s); it rejects ids out of range, reversed or overlapping, and picks whose first/last 3 bare tokens miss `hook_line`/`payoff_line` (safe-list fillers ignored on both sides: "So, um, the thing" matches words "so um the thing").
   - Refines ref 02 rules 1-2 and SKILL steps 2-3 (old: "`mm:ss  SPEAKER: sentence`"; "`{rank, score(1-10), start, end, ...}`").
   Why: lines carry 1 s timestamps; typed seconds miss word edges.
   HF: packages/cli/src/media-use/lib/cutlist.mjs:77-96
2. **One compiler per clip.** `scripts/cutlist.py` writes `cutlist.json` (implements this rule and **Dead air**, **Fillers: safe list**, the boundary half of **Frame grid** and **No slivers at splices**); never write it by hand:
   - removals clamped to the window, sorted, merged when `start ≤ prev.end`, inverted, snapped (**Frame grid**);
   - kept pieces < 0.20 s: dropped if no word starts in them, else grown to 0.20 s (warn);
   - `kept_s` (+ any freeze hold, `freeze_s` in `clips.json`) is the table's Length; over 59.5 s exits 1 (`too_long`, nothing written) before any render, then ref 02 rule 5;
   - a new max length or "keep the pauses" recompiles it, then re-runs only the stages after it (→ ref 05 §2 **Re-edits touch the smallest stage set**); "keep the pauses" skips the gap pass.
   Why: one source of truth; an over-length clip fails in seconds.
   HF: packages/cli/src/media-use/lib/cutlist.mjs:6-29,149-183
3. **Dead air.** Gap ≥ 0.30 s between kept words, not in `keep_gaps`: remove `[prev.end + 0.10, next.start − 0.10]` (0.20 s stays).
   - Quiet = 10 ms block power ≤ median word-block power − 15 dB (threshold ours); only quiet audio is removed.
   - An edge whose 30 ms ramp zone is not quiet moves 0.05 s away from its word (pad ≤ 0.20 s).
   - A non-quiet run ≥ 0.10 s in a gap (laugh, skipped word) and every `suspect_gaps` span (ref 03 §1 **Dropped-speech repair**) count as words; skip removals < 0.10 s.
   - The quiet test needs the source audio (`cutlist.py --source`); without it the word gaps are trusted and the warning `quiet_test_skipped` is logged.
   - Refines ref 01 §8 (old: "gaps ≥ 0.3 s between phrases are cut unless they are a visual payoff").
   Why: ASR word edges drift; raw-edge cuts clip tails; unrecognised sound is not dead air.
   HF: packages/cli/src/media-use/lib/cutlist.mjs:121-138; packages/cli/src/whisper/parakeet.ts:153-170
4. **Fillers: safe list.** Auto-remove only bare tokens (`re.sub(r'^[\W_]+|[\W_]+$', '', w.lower())`) in {um, umm, uh, uhh, uhm, er, erm}; like, so, oh, ah and you know go only by LLM ids.
   - Removed words leave the word list before the gap pass (pause + "um" + pause = one splice); each removal covers the word's `[start, end]`.
   Why: HF's documented `"um,uh,like"` deletes every verb "like"; "OH!" is often the reaction.
   HF: packages/cli/src/media-use/lib/cutlist.mjs:99-119; skills/media-use/references/operations.md:147
5. **Frame grid** (whole pipeline). `fps` = the exact rate of the frames being indexed (the canvas rate for clips), as a `Fraction`; frame k shows time k/fps.
   - Boundaries (segment in/out): the nearest frame edge, `k = round(t*fps)`, because cut points sit between frames. Touching segments merge. The cut list computes them once; every later step reads the integers.
   - Events and samples (word reveal, accent cause, sampled frame): the frame showing t, `k(t) = floor((t + 0.0005)*fps + 1e-6)`. The 0.5 ms absorbs ms-rounded times: 38/24 s printed as 1.583 → frame 38 (a plain floor gives 37).
   - Times handed to ffmpeg: `T(k)` = k/fps floored to the microsecond in integer math, written with 6 decimals (`"%d.%06d"`), never 3. Never a rounded k/fps for a frame seek: at 30000/1001, 1/fps rounded to `0.033367` lies after frame 1's pts (0.0333667), so an input seek skips that frame.
   - Implemented by `scripts/cliplib.py` `boundary_frame`, `event_frame` and `t6_frame` (`t6` alone rounds; it is for non-frame times), and by exact-`Fraction` copies in the scripts.
   - Tested: `-ss 12.867` at 30 fps starts on frame 387, not 386; 3-decimal `-ss/-t` miscounted 16-40 of 48 random cuts per rate, 6 decimals 0 of 144 (60/30/29.97).
   Why: a boundary is an edge, so the nearest stays within ½ frame, inside the pads; an event must show on the frame on screen at t, never a frame late.
   HF: skills/media-use/scripts/transcript-cut.mjs:278-285; skills/reverse-any-video/SKILL.md:19; packages/cli/src/measure/media.ts:339-341
6. **Video splice.** Read SRC through `norm_vf` (→ ref 03 §1 **Normalise in every clip intermediate**), so the splice shares canvas frame k with face tracks and cut detection.
   - Per segment, n = ko − ki; seek at least 1 s early to a whole canvas frame k_a = max(0, ki − ⌈fps⌉), then trim on the canvas grid:
     `ffmpeg -nostdin -y -ss T(k_a) -i SRC -map 0:V:0 -vf "<norm_vf>,settb=1/<fps>,trim=start_pts=<ki − k_a>,setpts=PTS-STARTPTS" -frames:v n -r <fps> -map_metadata -1 <flags> seg_0000.mov` (no `-ss` when k_a = 0); flags → ref 03 §4 **Seekable mezzanine**.
   - `-frames:v n` caps every segment, so the frame count is always right and cannot catch a one-frame miscut: the `frame_identity` gate in **Splice gates** does.
   - Join: `ffmpeg -f concat -i concat-<pid>-<n>.txt -c copy cut.mov` (list → ref 03 §4 **Windows-safe ffmpeg**).
   - Implemented by `scripts/splice.py` (writes `cut.mov` and the **Dialogue stem**, then runs the **Splice gates**).
   Why: CFR, exact frames, 1 s keyframes for seeking. Tested: a plain `-ss T(ki) -i SRC -vf <norm_vf>` drops the source frame still on screen at T(ki) whenever `norm_vf`'s `fps=` re-times the source (25 or VFR → 30: 2 of 150 frames wrong), because the accurate seek discards it before `fps=` sees it; the early seek + trim put every frame on the planned one. Without `-r`, the encoder fell back to 25 fps after `setpts`. A plain seek is exact only on a file already CFR at the canvas rate (W0 = 1-2 s intermediates at 60, 59.94→60, 30, 29.97→30 and 25→30 fps: every frame the planned one).
   HF: skills/media-use/scripts/transcript-cut.mjs:101-103,203-209
7. **Dialogue stem.** One pre-rolled decode of the source audio:
   `ffmpeg -ss P -i SRC -map 0:a:0 -af "aresample=48000:async=1:first_pts=0,pan=mono|c0=0.5*c0+0.5*c1,atrim=start_sample=S0:end_sample=S1" -f f32le -`
   - t0 = K0/fps and t1 = K1/fps (K0 = the first ki, K1 = the last ko, on the source grid); P = max(0, ⌊t0⌋ − 1); S0 = round(t0·48000) − 48000·P; S1 = round(t1·48000) − 48000·P.
   - Mono source: `pan=mono|c0=c0`; a layout with a centre channel (3.0 up to 7.1): `pan=mono|c0=0.5*c0+0.5*c1+0.7071*c2`. Never `-ac 1` where level matters: it is 3.0 dB hotter as f32le than as s16le.
   - `async=1:first_pts=0` as in ref 03 §1 **ASR on the video's clock**: without it, audio 0.25 s late made the stem 229 ms early at P = 0; with it, the stem matched the ASR-clock decode sample for sample.
   - Float PCM until the single AAC (→ ref 03 §4 **One AAC encode, copied at the mux**); never AAC per segment (+29-31 ms and zero runs up to 19 ms each).
   - Implemented by `scripts/cutlist.py` `decode_mono` (shared with `splice.py`, which writes `dialogue.wav`, `pcm_f32le`); source audio ending early is zero-padded with an `audio_short` warning.
   Why: an AAC decode needs warm-up; per-segment encodes add priming gaps.
   HF: packages/producer/src/services/render/audioTruePeak.ts:105-107; skills/media-use/scripts/transcript-cut.mjs:96-100
8. **Ramps on every edge.** Slice the decode `x` in numpy, per segment `x[a:a+m]`:
   - `a = round(ki·SR/fps) − round(K0·SR/fps)`, `m = round((o+n)·SR/fps) − round(o·SR/fps)` (o = output frame offset, SR = 48000), so Σm = round(Σn·SR/fps).
   - 30 ms linear ramps at both ends: `np.linspace(0, 1, min(1440, m // 4))`.
   - The clip's first and last edges ramp too, inside ref 02's 0.05/0.15 s pads: a de-click, still ref 01's hard cut, no fade-in (§2, §5).
   - Tested click ratio (**Splice gates**): 0.14-0.16 ramped, up to 32 unramped.
   - Implemented by `scripts/splice.py` (half-up rounding of every sample position).
   Why: an unramped join clicks.
   HF: packages/cli/src/media-use/lib/transcriptCutFade.mjs:5-21; skills/media-use/scripts/transcript-cut.mjs:106-114
9. **One clock.** Cut first, then caption: `remap(t) = (o + t·fps − ki)/fps` for the segment holding source time t; words starting in a removal drop; words crossing `ko` clamp.
   - Captions, the crop path (output frame f ← source frame `ki + f − o`; face tracks stay cached in source frames), accent cause frames (`k(remap(word.start))`), SFX cues and duck spans all use it, then **Frame grid**.
   - Implemented as `scripts/cutlist.py` library functions (`remap`, `remap_span`, `out_to_src_frame`, `src_to_out_frame`); `cutlist.json` carries the words already remapped to output seconds.
   Why: per-splice offsets add up.
   HF: docs/guides/captions-and-recuts.mdx:116-119
10. **No slivers at splices.** Splices feed the reframe (resets → ref 04 §2 **Classified cut detector**; same-camera scale change → ref 04 §2 **Face carried across jump cuts**).
    - A hard or soft source cut in a segment's first/last 0.20 s moves that edge onto it when no word overlaps the sliver; else warn `sliver_kept`. Implemented by `cutlist.py --shot-cuts cuts.json` (events from `scripts/cuts.py` on the source window).
    Why: no < 0.20 s flash of another shot at frame 0 or at a join.
    HF: packages/cli/src/measure/cuts.ts:1-2
11. **Splice gates** (every clip, before any render).
    - Decoded frames (last `frame=` of `ffmpeg -v error -i cut.mov -map 0:v:0 -f null - -progress pipe:1`) == packets (rows of `-c copy -f framemd5 -`) == Σn (a last frame outside the edit list gave 178 packets but 177 frames).
    - Every packet pts·tb == i/fps (sorted, `Fraction`); keyframe gap ≤ 1.05 s, also from the last keyframe to the end (`ffmpeg -skip_frame nokey -i cut.mov -map 0:v:0 -vf showinfo -f null -`); stem samples == round(Σn·SR/fps).
    - Frame identity: each segment's first and last frame matches canvas frame ki / ko − 1 of SRC read through `norm_vf` (found by pts after `settb=1/fps`, from a seek ≥ 1 s early) better than its neighbours: grey 128×72 thumbnails, mean |d| ≤ 4 and no neighbour closer by more than 0.25 (ours; a CRF 12 copy of the right frame read ≤ 0.31).
    - Per splice: max |Δ| within ±5 ms ≤ 2 × the 99.9th percentile of |Δ| over ±250 ms outside it; exact-zero runs < 20 samples within ±50 ms unless the source has that run.
    - Implemented by `scripts/splice.py`: any failed gate exits 1 and the outputs keep their temp names.
    Why: these defects are invisible on 1 fps review; with `-frames:v n` only the identity check sees a one-frame miscut (3-decimal seeks fail `frame_identity`, not the frame count).
    HF: skills/media-use/scripts/transcript-cut.test.mjs:127-197,243-264

### Optional
- **ffmpeg self-test** (new machine or build): `splice.py --selftest` cuts testsrc2 + a 440 Hz sine at 30, 30000/1001 and 60 fps with HF's keeps 0.137-1.913, 2.845-4.111 and 4.9-5.47 plus 6.067-7.5 (ours: its frame time rounds up at 3 decimals at every rate); the **Splice gates** pass, and each negative control fails its gate: per-segment AAC → stem samples, 3-decimal times → frame identity, no ramps → click.
  HF: skills/media-use/scripts/transcript-cut.test.mjs:50-52
- Untested: the ffprobe paths of `cutlist.py`/`splice.py` (packet cross-check, probe); every test ran on the ffmpeg-only fallback. No stall watchdog on segment encodes (they are short).

## 3. Audio: mix, ducking, loudness, SFX and gates
Scope: the dialogue stem (ref 03 §2) to the float master; the single AAC encode and the mux are ref 03 §4.

### Adopted (default)
1. **Float unity mix.**
   - Decode each stem once to f32 48 kHz stereo; upmix mono with `pan=stereo|FL=FL+FC|FR=FR+FC`, never `-ac 2`.
   - Sum in numpy at sample round(t·48000) into a buffer of round(N·48000/fps) samples (→ ref 03 §4 **Picture is the clock**). Intermediates stay `pcm_f32le` until the AAC.
   - ffmpeg path: per branch `adelay=delays=<n>S:all=1,apad,atrim=end_sample=<total>`, then `amix=inputs=K:duration=longest:dropout_transition=0:normalize=0`.
   - Implemented by `scripts/mix_audio.py` (numpy path; rules 1-7, 9 and 11 of this section and the reuse check of rule 8). It writes `mix.wav` (float32 stereo, exactly round(N·48000/fps) samples), `mix_report.json` and the float stems `mix_dialogue.wav`, `mix_bed.wav`, `mix_sfx.wav` (the duck-margin gate measures them). A dialogue stem more than one frame of samples off that length exits 2 (`length_mismatch`); within one frame it is padded or trimmed with a warning.
   Why: here `-ac 2` cost 3.01 dB; default amix cost 6.02 dB, then swelled 6 dB over 2 s after a branch ended; one-value `adelay` delayed only the first channel; an s16 intermediate clipped a +1.58 dBFS sum flat (36000 samples). The sample-exact branch gave exactly 2271069 samples (1418 frames at 30000/1001).
   HF: packages/engine/src/services/audioMixer.ts:226-229,954-957,1170-1176
2. **Envelopes as samples.** Multiply duck lanes and de-click ramps into the numpy buffer (`np.interp` per sample). Any `volume=...:eval=frame` expression stays ≤ 32 segments (RDP, epsilon 0.005 linear).
   Why: nested `if(lt(t,...))` failed graph init at 99 levels here (98 ran), dropping the audio.
   HF: packages/engine/src/services/audioVolumeEnvelope.ts:1-11; packages/engine/src/services/audioMixer.ts:199-224
3. **Dialogue chain, static gains.** Refines ref 01 §6 (old: "normalised to about -14 LUFS integrated").
   - Static pre-gain to -18 LUFS (threshold ours), then Clean Voice: `highpass=f=80:poles=2,equalizer=f=250:t=q:w=1.2:g=-3,acompressor=threshold=0.1:ratio=3:attack=12:release=180:makeup=1.413,equalizer=f=3000:t=q:w=1:g=2.5`. Its -1 dB limiter moves to **Limiter last**.
   - Then one gain g = -14 − I, skipped within 0.5 LU. Warn if the total gain exceeds +12 dB (noise rises too). Never claim denoising.
   - No dynamic loudnorm: two-pass `linear=true` (I -14, TP -1.5, LRA 11) stays linear only if TP − I ≤ 12.5 dB and 0 < LRA ≤ 11; otherwise it goes dynamic (192 kHz out) silently, so check `normalization_type`.
   Why: on a -40.6 LUFS stem the -20 dB threshold barely acted (PLR 26.1 vs 26.5 with EQ alone; pre-gained: 22.4); loudnorm went dynamic at TP − I 12.7, LRA 12.0 and LRA 0 (linear at 12.2 and 10.4).
   HF: packages/core/src/audioFxPresets.ts:93-109,147-150; skills/media-use/references/operations.md:193-200
4. **Measure the played window.** `ffmpeg -ss S -t D -i src -map 0:a:0 -vn -af ebur128=peak=true -f null -`, seeking before `-i` (times → ref 03 §2 **Frame grid**); parse the last summary `I:` and `Peak:` lines.
   - Widen windows < 0.4 s (0.3 s read -70.0; 0.4 s read -37.3). Never gain-match a window ≤ -70 LUFS.
   - Implemented by `scripts/cliplib.py` `ebur128()`.
   Why: output-side `-t 4` read -20.0 LUFS for a window that is -60.0.
   HF: packages/studio-server/src/helpers/loudness.ts:448-457,505-506
5. **Transcript duck lane.** Refines ref 01 §6 (old: "sidechain ducking (attack 20 ms, release 300 ms)"): same numbers, pre-rolled.
   - Spans = post-cut words (→ ref 03 §2 **One clock**) ∪ speech activity on the dialogue stem: 50 ms hop, 100 ms window, threshold max(-45, p90 − 30) dB; a span ends where ≥ 0.4 s below it starts; keep spans ≥ 0.3 s.
   - Merge spans when the gap is < 0.6 s (short pauses stay ducked).
   - Bed gain 0.316 (-10 dB): a 20 ms down-ramp ending at each span start, a 300 ms up-ramp from its end; overlaps take the minimum; a bed entering mid-span starts ducked. Key = dialogue only.
   - A planned ref 01 §6 tension mute goes in the plan as `bed.mutes: [[s, e]]`: the bed gain is 0 there. Depth, ramps and the merge gap are plan keys (`duck.depth_db`, `attack_s`, `release_s`, `merge_gap_s`).
   Why: a sidechain reacts after the first syllable; known times duck before it.
   HF: packages/cli/src/media-use/lib/duck.mjs:4,36-103; packages/cli/src/audio/read/voice.ts:15,126-157
6. **Bed entry, level, length.** Refines ref 01 §6 (old: "about -20 dBFS short-term in speechless stretches").
   - Offset = the earliest point whose next 5 s reach the 75th percentile of all 5 s windows' mean short-term loudness (threshold ours); S from ebur128's per-frame lines (`ebur128=framelog=info`: at the default log level they are not printed). Compare the window means at S's own resolution (rounded to 1e-4; S is logged to 0.1 LU).
   - Unducked bed at -20 LUFS over the used window.
   - Cover the clip: drop trailing samples under -60 dBFS from the loop seed, then loop with a 0.3 s equal-power cos/sin crossfade.
   - No fades (ref 01 §2); 5 ms de-click ramps on the first and last samples.
   Why: a quiet intro drains the hook (an 8.3 s intro gave offset 8.2 s here; unrounded cumsum means let float drift pick 14.1 s); a short file leaves a silent tail, and a silent tail in the seed leaves a hole at every seam.
   HF: skills/media-use/audio/references/bgm.md:36; skills/hyperframes/references/sound.md:20; skills/media-use/audio/scripts/lib/bgm.mjs:205-226
7. **SFX on the hit.** Refines ref 01 §5 (old: "one SFX per flash or whip", no timing).
   - Per file, RMS of sqrt(mean of channel squares) every 1 ms over a centred 4 ms window; peak = argmax; onset = first ≥ 0.2 × peak; tail = last ≥ peak − 40 dB.
   - Start = (F + 1)/fps − peak_s for accent frame F (any class); a start < 0 trims the head; decays run over the next cut.
   - Scale to -11 dBFS sample peak (ref 01 §6). QC per sound: each SFX's own placed signal (4 ms RMS every 1 ms on the clip grid) peaks on a frame (`k(t)`, ref 03 §2 **Frame grid**) in [F, F + 2]; never the argmax of the summed SFX bus. An accent on the last frame cannot land (`peak_cut`) and fails.
   - Tested: a whoosh peaking at 123 ms, placed for F = 90 at 60 fps, peaked at 1517.0 ms (target 1516.7); trimmed for F = 0, at 17.0 ms (target 16.7). A riser at F = 180 into a hit at F = 186: the bus window for the hit read frame 180 (the riser's crest) and failed a correctly placed hit; its own signal read 187.
   Why: the hit is not the file start (riser crest ≈ 2.5 s, whoosh 0.393 s here); a sound early reads wrong sooner than one late; overlapping sounds own each other's bus peaks.
   HF: skills/hyperframes/references/sound.md:36; packages/core/src/audioAnalysis.ts:135-149,332-361
8. **Distinct-variant library.**
   - A JSON manifest beside the SFX files: per file class (whoosh|hit|riser|boom), duration, onset/peak/tail, sample peak, md5, print, licence, source URL.
   - Same sound = equal md5, or print cosine ≥ 0.95 with a length ratio of 0.5-2. Print = sqrt of each octave's energy share (1/5-octave bands, 30 Hz-9 kHz) over 0.4 s from onset.
   - Before the first render: the manifest parses, every file decodes, and distinct counts reach whoosh 4, hit 7, riser 2, boom 1 (threshold ours, from ref 01 §5 maxima); short = warning `sfx_library_incomplete`.
   - Per clip: round-robin, no sound reused. An accent with no unused sound gets a new file (Openverse, CC0/CC BY only; credit CC BY on its own line of `captions.md`); none found = a Defaults breach.
   - `scripts/mix_audio.py` gates reuse among the plan's SFX (`sfx_reuse`: same resolved path, same md5, or the print test above). The manifest, the library counts, round-robin picking and the Openverse top-up are not scripted yet.
   Why: HF's own whoosh/whoosh-short and click/click-soft are byte-identical; a -9 dB copy scored cosine 1.000 here.
   HF: packages/cli/src/audio/read/effects.ts:14,128-138,205-263,330; skills/media-use/audio/references/sfx.md:12
9. **Limiter last.** Master chain: float sum → static trim to -14 LUFS if |I + 14| > 0.5 → `aresample=192000,alimiter=limit=0.708:attack=5:release=50:level=0:latency=1,aresample=48000` (-3 dBFS: 2 dB under -1 dBTP) → written as the float master (`pcm_f32le`). Nothing raises the level after it; the AAC encode is ref 03 §4.
   - The trim must make the limited master read -14 LUFS: if it misses by more than 0.5 LU, add the miss to the pre-limiter trim and run the limiter once more (one corrective pass; the report lists both).
   - Gate `master_lag`: the cross-correlation lag between the pre-limiter and the limited master over their loudest 2.7 s is 0 samples.
   Why: 7.1 defaults `level=1` re-normalised to 0 dBFS (+6.02 dB) and `latency=0` put audio 5.0 ms late (240 samples); at 48 kHz a -2 dBFS limit left +3.5 dBTP on hot white noise; a mix with +5.5 dBTP plosives gave -2.9 dBTP (AAC -2.9 to -2.4), I -0.2 LU. Tested: the trim on the float sum ignores the limiter's own loss (0.3-0.8 LU on dense synthetic speech peaks): a sum inside the 0.5 LU skip came out at -15.0 LUFS, the gate edge; the corrective pass gave -14.2 (and -14.7 → -14.2 on hot plosives). The 192 → 48 kHz downsampler leaves the sample peak at -2.45 to -2.86 dBFS and the true peak at -2.5 to -2.9 dBTP, not -3.
   HF: docs/reference/audio-effects.mdx:281-299; packages/core/src/audioLeveller.ts:201-210
10. **True peak after AAC.** Refines ref 01 §6 (old: "true peak ≤ -1 dBTP", no stage named). Runs at the mux, after the single encode (→ ref 03 §4 **One AAC encode, copied at the mux**).
    - Measure the .m4a with the **Measure the played window** command (last `Peak:`); require ≤ -1.0 dBTP.
    - Else re-encode from the PCM with `volume=<att>dB`, att += −1 − 0.5·2^p − max(tp_aac, tp_pcm + att), p = the pass just measured (0 = the first encode); at most 3 corrections (true peak measured up to 4 times), then fail listing every pass.
    - Implemented by `scripts/finalize_mux.py`.
    Why: AAC added 0.0-0.5 dB on mixes, 2.8 dB on limited white noise; one pass fixed that (+1.3 → -2.2 dBTP); a +5.5 dBTP PCM took two. Re-tested: hot noise took 1 correction (+7.2 → -2.0 dBTP), clipped-hot noise 2 (+9.3, +0.9, -3.1).
    HF: packages/producer/src/services/render/audioPadTrim.ts:49-52,376-379,442-451
11. **Audio gates.** Refines ref 01 QC checklist (old: "audio present"). Log `audio NN lufs:-14.1 tp:-2.4 lowered:0.0 clip:0 sil:0 vom:16`.
    - On the float master: I -14 ±1 LU; samples with |x| ≥ 0.999: 0. On the .m4a: TP per **True peak after AAC**; tracks → ref 03 §4 **Delivery gate**.
    - `silencedetect=n=-50dB:d=0.1` reports nothing outside a planned ref 01 §6 mute (d=0.2 missed a 0.166 s tail here).
    - Per duck span (widened to ≥ 0.4 s): LUFS(dialogue) − LUFS(ducked bed) target ≥ 12 dB (9-12 dB warns); < 9 dB fails (threshold ours). Fix: deepen the duck by the shortfall to 12 dB (or lower the bed) and re-mix; tested: the hinted depth brought a 2.2 dB margin back to 12.0 dB.
    - Bed energy below 150 Hz ≥ 50%: warn and pick another bed (phone speakers).
    - Every input decodes, has audio, and is not silent in its used window (dialogue or bed ≤ -70 LUFS, SFX 4 ms RMS peak < -50 dBFS). A missing file, no audio stream or a failed decode exits 2; ffmpeg error lines in an otherwise good decode, or silence, fail this gate (a damaged MP3 bed needs re-encoding). Silent inputs are never gain-matched.
    - `scripts/mix_audio.py` runs these on the float master: each gate is `{ok, measured, limit, level}`, failures exit 1 with the files written and a fix hint per gate; `bed_low_share` is warn-only. TP after AAC and the tracks run in `finalize_mux.py`.
    - Delivery note → ref 05 §1 **Measure, then look**.
    Why: ref 01 levels gave 16.1-16.4 dB span margins; HF dropped a 9 dB carve aim as "still fighting the voice"; 100 ms windows fail on syllable troughs (p05 2.4-6.9 dB).
    HF: packages/cli/src/audio/read/read.ts:161-180; skills/media-use/audio/scripts/carve.mjs:38-39; packages/core/src/audioCarve.ts:259-262; packages/cli/src/utils/checkAudio.ts:175-214

### Optional
- **Even out speakers.** When the speaking-window p80 − p20 > 6 dB (threshold ours), run HF's leveller before the static gain: 4096-sample windows, skip < peak − 42 dB, target p80, correct 0.55 × the gap, clamp ±12 dB, attack 0.35 s, release 0.9 s, snap < 0.4 dB.
  HF: packages/core/src/audioLeveller.ts:41-53,73-76,117-145
- **Spectral carve.** If the bed must stay hot: peaking cuts (Q 1.4) on the bed at the voice's top 3 of 9 third-octave centres (160-6000 Hz), ranked with HF's 2 kHz weighting; -6 dB on the top band, -3 to -6 dB on the others; faded in by the duck lane.
  HF: packages/core/src/audioCarve.ts:25,245-264,443-495
- **Calm release.** On request ("less pumping"): up-ramp 2.4 s (`duck.release_s: 2.4` in the audio plan). Refines ref 01 §6 (old: "release 300 ms").
  Why: 1.6 s still read as the bed "coming back" at each sentence break.
  HF: packages/core/src/audioCarve.ts:512-527
- **Source already has music.** Onset regularity ≥ 0.35 on speechless stretches (peak autocorrelation of a 10 ms spectral-flux curve, 0.3-1.5 s lags): bed 6 dB lower (threshold ours), logged; no bed only on request. Refines ref 01 §6 (old: "It rises to about -20 dBFS short-term").
  HF: packages/core/src/audioAnalysis.ts:536-552,587,600-617
- Not scripted: Even out speakers, Spectral carve, Source already has music. Untested: `mix_audio.py` on real voice (its tests use synthetic noise-burst speech; the limiter's loss on real speech is expected to be smaller) and its ffprobe path.

## 4. Encode and mux: exact lengths, BT.709 tags, delivery settings
Scope: intermediates, the final encode, audio length, the mux and its gate, ffmpeg on Windows.

### Adopted (default)
1. **Picture is the clock.** The render's N frames set every length (frame times → ref 03 §2 **Frame grid**).
   - Audio = round(N·SR/fps) samples (SR 48000; 60 fps: 800 per frame): zero-pad or trim the float mix in numpy before the AAC.
   - Event ends clamp to frame N. Never `-shortest`.
   - Implemented by `scripts/finalize_mux.py` (N = the video's decoded frame count, which must equal `--frames`; the report's `audio.fit` says copy, pad or trim). Exact halves of N·48000/fps never occur at 24/25/30/50/60 fps or their /1001 rates, so the scripts' rounding (half-up vs `mix_audio.py`'s half-even) cannot differ there.
   Why: a mix 12.6 ms short made `-shortest` cut 150 frames to 149 (`-bf 0`) or 148 (B-frames); a 22.9 ms long one gave 2.496 s of audio.
   HF: packages/producer/src/services/render/audioPadTrim.ts:11-14,47,299; skills/reverse-any-video/SKILL.md:18
2. **One AAC encode, copied at the mux.** Fit → AAC → true peak (→ ref 03 §3 **True peak after AAC**) → mux. The final mux step owns all four, because it knows the render's decoded N; the mix step delivers the float master.
   - `ffmpeg -i mix_T.wav -c:a aac -b:a 192k -ar 48000 audio.m4a`
   - `ffmpeg -i video.mp4 -i audio.m4a -map 0:v:0 -map 1:a:0 -c copy -r <fps> -map_metadata -1 -map_chapters -1 <re-tag> -movflags +faststart out.mp4`; `<re-tag>` = the **EffectCraft colour** bsf + flags, on every mux by default (BT.709 tv; → **BT.709 from the head of the graph** for why an encode's own tags are not enough).
   - Never a raw `.aac`, an AAC re-encode at the mux, or `-avoid_negative_ts make_zero`.
   - Implemented by `scripts/finalize_mux.py` (`--tag 709tv|601tv|none`, default 709tv): it refuses a VFR (more than one `stts` entry), non-H.264-yuv420p, fps- or frame-mismatched video before any encode, muxes to a staged name, runs the **Delivery gate**, and promotes only on a pass.
   - Refines SKILL path A Render (old: "ffmpeg-mux the mixed audio with `-c:v copy` (no second video encode) and verify duration").
   Why: copied `.m4a`: in sync, audio edit 2.500 s. Raw `.aac`: 21.33 ms late, audio edit 2539 ms, media_time 0 (no priming skip). `make_zero`: an empty 21 ms video edit (HF: black first frame), and it also sets the audio edit's media_time to 0 and stretches it to 2522 ms for a 2500 ms clip. Re-encoded `audio.m4a`: 2.517 s. Cuts inherit the source title and URL; chapters in the video become an extra text track unless `-map_chapters -1`.
   HF: packages/engine/src/services/audioMixer.ts:79-81; packages/engine/src/services/chunkEncoder.ts:892-924
3. **BT.709 from the head of the graph.** ffmpeg path:
   - `setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv` on the footage before `ass` and `overlay`: they convert RGB by that tag (untagged = BT.601). Overlays stay RGBA.
   - Encoder: `-x264-params colorprim=bt709:transfer=bt709:colormatrix=bt709 -colorspace bt709 -color_primaries bt709 -color_trc bt709 -color_range tv`. libx264 needs the `-x264-params` part whenever the graph ends in a `scale=out_color_matrix=...` exit (ref 04 §3): that exit tags only matrix and range.
   - The `colr` box comes from the mux re-tag (→ ref 03 §4 **One AAC encode, copied at the mux**), so it is right whatever the encode wrote.
   - Matrix naming at RGB stages, piped frames and colour sources → ref 04 §3 **Name the matrix at every RGB hop**; BT.601/BT.2020 sources are converted in ref 03 §1 **Normalise in every clip intermediate**.
   Why: untagged: #2BFF2B 33 off, #FF2BD6 30, #FF1A1A 22; tagged ≤ 1. With a filter graph on 7.1, `setparams` writes the VUI + `colr`, `-x264-params` the VUI only, and the `-color_*` flags only the VUI matrix (primaries/transfer unknown, no `colr`). Tested: `scale=out_color_matrix=bt709:out_range=tv` passes its tags to libx264, which then writes a partial VUI (matrix 1, range 0, primaries 2, transfer 2) and no `colr`: it decodes within 1 code value in ffmpeg, but primaries, transfer and `colr` are missing.
   HF: packages/engine/src/utils/sdrCaptureColor.ts:1-5; packages/engine/src/services/chunkEncoder.ts:419-423,474-511
4. **EffectCraft colour.** Once per EffectCraft version, decode an EffectCraft render of a ref 01 palette card as 709/601 × tv/pc: the decode within 4 code values is what it wrote (right ≤ 1, wrong ≥ 17). The card check picks the tag; the mux cannot tell what matrix the pixels were encoded with.
   - A reference card made with ffmpeg must be truly untagged: end its graph with `setparams=colorspace=unknown:range=unknown` after the conversion.
   - Re-tag at the copy-mux: `-bsf:v h264_metadata=colour_primaries=1:transfer_characteristics=1:matrix_coefficients=1:video_full_range_flag=0` (VUI) plus the `-color_*` flags (`colr`). BT.601: `matrix_coefficients=6`, `-colorspace smpte170m` (primaries and transfer stay BT.709); full range: `video_full_range_flag=1`, `-color_range pc`.
   - Implemented by `finalize_mux.py --tag 709tv|601tv|none` (default 709tv; none keeps the video's tags and the gate only reports them). Full-range tags (709pc/601pc) are not offered yet: add them only if the card check finds a full-range render.
   - Untested: the card check on a real EffectCraft render; `finalize_mux.py` refuses a render whose last sample has its own duration (two `stts` entries) as VFR.
   Why: ffmpeg decodes untagged as BT.601 (palette card 34 off), while Chrome reads ≥ 720-line H.264 as BT.709. On a copy the bsf alone writes no `colr` and the flags no VUI; both: 1/1/1/0, PSNR inf. Tested: a card that only names its exit matrix is not untagged (→ **BT.709 from the head of the graph**): its "wrong decode" baseline read 1 instead of 34 (#FF2BD6).
   HF: packages/engine/src/services/videoFrameExtractor.ts:971-979
5. **Delivery encode.** ffmpeg path: `-c:v libx264 -preset medium -crf 16 -bf 0 -pix_fmt yuv420p -r <fps> -an` plus **BT.709 from the head of the graph**; audio joins at the mux. Image-sequence or pipe input: `-xerror`.
   - Refines ref 01 §1 and SKILL path B (old: "h264 CRF 18 or lower" / "h264 CRF <= 18").
   Why: medium CRF 16 is HF's default `looks` tier ("visually lossless at 1080p"). `-bf 0`: video edit media_time 0, not 512 (2 frames). Without `-xerror` a corrupt PNG exited 0 with 59 of 60 frames.
   HF: packages/engine/src/services/chunkEncoder.ts:57,311-312,389-404; packages/cli/src/commands/render/plan.ts:46; docs/guides/rendering.mdx:262
6. **Seekable mezzanine.** Every intermediate (clip intermediates, cut segments, plates, EffectCraft footage) is a `.mov` encoded with:
   `-an -c:v libx264 -preset veryfast -crf 12 -pix_fmt yuv420p -fps_mode cfr -force_key_frames "expr:gte(t,n_forced)"`
   - Video only: dialogue → ref 03 §2 **Dialogue stem**; an intermediate that must carry audio uses `pcm_f32le` (ref 03 §3 **Float unity mix**).
   - Cuts → ref 03 §2 **Video splice**, then assert n decoded frames. VFR and colour → ref 03 §1 **Normalise in every clip intermediate**.
   - Never `.mkv`/`.webm` or `-c copy` cuts.
   - `scripts/splice.py` encodes every segment with these flags.
   - Refines SKILL path A (old: "near-lossless intermediate (keep 60 fps)").
   Why: x264 default: keyframes 4.17 s apart; forced: 1.000 s. `.mkv` (1/1000 timebase) put 91/137 frames of one cut off the 60 fps grid, and 232/250 (30), 466/502 (60) and 246/250 (29.97) of joined segments; `.mov` 0. Without `-pix_fmt` a 4:2:2 10-bit source stayed yuv422p10le.
   HF: skills/media-use/scripts/transcript-cut.mjs:101-103,201-209
7. **Delivery gate.** On the muxed file before delivery, by a standard-library MP4 box walk (no ffprobe needed). Frames, ≤ 59.5 s, decode errors and black → ref 05 §1 **Stage, validate, promote** and **Black, frozen, frame 0**; audio levels → ref 03 §3 **Audio gates**.
   - `moov` before `mdat` (no `moof`); exactly 1 H.264 yuv420p video + 1 AAC 48 kHz stereo track, no other stream (subtitle, chapter text, second audio); global tags only major_brand, minor_version, compatible_brands, encoder (+ title).
   - Video: one `stts` entry (60 fps: 256 at 1/15360) at the expected rate; no empty edit (`elst` media_time −1); first decoded pts 0.
   - Audio: `elst` media_time > 0 (1024 = priming); |Σ edit durations − N/fps| ≤ max(1 ms, one movie-timescale tick). Never the decoded count (end padding: 120832 for 120000); only without an audio edit list, decoded − N/fps must lie in [−1 frame, +1 frame + 1024 samples].
   - `colr` nclx and VUI (`-bsf:v trace_headers`): 1/1/1, range 0, or the card's values.
   - Also on the delivered file: decoded frames == N, no decode error lines, no black frame in the last 0.1 s, N/fps ≤ `--max-dur` (59.5 s), true peak ≤ -1.0 dBTP.
   - Implemented by `scripts/finalize_mux.py` (14 named checks; `--check FILE` runs the gate alone).
   Why: each tested defect (`-shortest`, raw `.aac`, `make_zero`, mux re-encode, untagged, inherited tags, an extra stream, moov at the end) fails its check; a clean mux passed all (re-tested: 150 × 256 at 1/15360, edits 0 and 1024, audio edit 2.500 s). Tested: ffmpeg writes the `elst` in movie ticks (1/1000 by default) rounded up, so a correct mux reads up to 0.999 ms off (151 frames at 60 fps: 2517 vs 2516.667 ms), and a 600 timescale ticks 1.67 ms. For ffmpeg's own AAC the exact count is mdhd duration − media_time (121024 − 1024 = 120000).
   HF: skills/hyperframes-cli/SKILL.md:35; packages/producer/tests/audio-mux-parity/meta.json:3; packages/producer/src/services/render/audioPadTrim.ts:47
8. **Windows-safe ffmpeg.**
   - `cwd=<job dir>` and bare relative names in filters (`ass=captions/01.ass:fontsdir=fonts`); an unescaped `C:/…` path failed to parse.
   - Per-frame values in a `sendcmd=f=<file>`; graphs over 8 KB (threshold ours) via `-filter_complex_script <file>` (else `-/filter_complex`). Command lines cap at 32,767 chars (32,110 ran; 36,510 raised WinError 206).
   - Concat: a new `concat-<pid>-<n>.txt` beside the parts, with bare `file 'part_01.mp4'` lines; absolute paths need `-safe 0` and `'` → `'\''`. Joined frames == the sum of the parts.
   - `-progress pipe:1 -nostats`: kill only after 180 s without `out_time_us` growth (implemented in `finalize_mux.py`; the short segment encodes of `splice.py` have no watchdog). Temp names → ref 05 §2 **Crash-safe writes**.
   - Exit 3221225781, 3221225595 or 3221225794 = a broken build: reinstall.
   Why: a reused list silently gives a wrong video, and a stall means a hung encode (both from HF).
   HF: packages/engine/src/services/audioMixer.ts:964-974; packages/engine/src/services/chunkEncoder.ts:679-692; packages/engine/src/utils/runFfmpeg.ts:85-106; packages/studio-server/src/helpers/proxyTranscoder.ts:62-68

### Optional
- **Drafts.** `-preset ultrafast -crf 28` while iterating; never delivered.
  HF: packages/engine/src/services/chunkEncoder.ts:56
- Untested: `finalize_mux.py` with ffprobe installed (the box walk and ffmpeg checks are the same either way) and on a real EffectCraft render.

## Not adopted (and why)
- §1: HF `probe --normalize`: one whole-source CFR copy at the standard rate nearest the average (24000/1001, 24, 25, 30000/1001, 30, 50, 60000/1001, 60), AAC 192k (HF: packages/cli/src/commands/measure/probe.ts:29-66). Why not: the Defaults fix the canvas at 60 fps (30 under 50 fps), so each clip window is normalised straight to the canvas rate; a CRF-12 transcode of a 1-2 h source would break ref 02 rule 12's ≤ 40 min benchmark.
- §1: Keeping 60000/1001 for 59.94 sources (proposed during the study). Why not: the Defaults canvas is 60 fps; `fps=60` duplicates 4 frames per 60 s (tested: 3597 in, 3601 out) with no A/V drift. Only relabelling the rate is banned.
- §1: HF engine VFR threshold, 10% of max(r, avg) (HF: packages/engine/src/utils/ffprobe.ts:974-975). Why not: we keep the measure tools' 1% (HF: packages/cli/src/measure/media.ts:133); `norm_vf` resamples every source anyway, so `vfr` only adds a warning, and 1% also flags stream VODs with dropped frames.
- §1: Seeding names into ASR via `hotwords`/`initial_prompt`. Why not: tested offline with faster-whisper 1.2.1 on noise and silence: seeded names were written into non-speech, and a name prompt at temperature 0 made `tiny` loop 184-186 words. HF keeps whisper for timestamps only and fixes display spelling afterwards (HF: .agents/skills/changelog-video/SKILL.md:118-120).
- §1: An external transcription API or user-supplied text as the failure fallback (HF: skills/media-use/audio/references/captions/transcript-handling.md:41-43,62-91). Why not: dependencies stay within requirements.txt + ffmpeg; the local ladder small → medium → large-v3, then re-pick, covers it. A request can still ask for an API.
- §1: HF default whisper models `small.en`/`medium.en` (HF: skills/media-use/audio/references/transcribe.md:3,18; skills/hyperframes/references/captions.md:6). Why not: the SKILL keeps multilingual `small`/`medium`; a `.en` model is used only for English, because `.en` models translate (HF).
- §1: Parakeet-TDT as the default local engine (HF: skills/media-use/references/operations.md:107-112; packages/cli/src/whisper/parakeet.ts:4-8). Why not: it needs sherpa-onnx, outside requirements.txt, and HF's WER/speed claims are unverified here; it stays Optional, behind an A/B.
- §1: probe.ts tone-map order, primaries converted in linear light before hable (HF: packages/cli/src/commands/measure/probe.ts:57). Why not: we keep one chain, HF's shared helper (HF: packages/core/src/hdrToneMap.ts:29, used at packages/engine/src/services/videoFrameExtractor.ts:1194, packages/studio-server/src/helpers/proxyTranscoder.ts:682 and snapshot.ts:608) plus the named-matrix step (proxyTranscoder.ts:683). Without that step, tone-mapped pure red read Y 73, not 63.
- §1, §2: HF caption cleaner's huh/uh/um/ah/oh shorter than 0.1 s, as a transcript drop or as an auto-cut list (HF: skills/media-use/audio/references/captions/transcript-handling.md:55). Why not: fillers stay in `transcript.json` with ids; ref 03 §2 **Fillers: safe list** auto-cuts only hesitations; ref 04 §1 **Token timing contract** drops them from captions; "OH!"/"AH!" are often the reaction itself (ref 01 §3 keeps hype lines).
- §1: Rejecting decimal frame rates such as 29.97 (HF: packages/core/src/fps.ts:63-71). Why not: canvas rates are integers (60/30) and `fps_r` is stored as `num/den`; 29.97 vs 30000/1001 differs by 1e-6 (relative), 0.06 ms/min.
- §2: HF `--cut-silence` example threshold of 0.8 s (HF: docs/guides/captions-and-recuts.mdx:42; skills/media-use/references/operations.md:148). Why not: ref 01 §8 wins on pacing: gaps ≥ 0.3 s between phrases are cut, so the trigger stays 0.30 s.
- §2: HF 0.15 s silence pads on each side (HF: packages/cli/src/media-use/lib/cutlist.mjs:4,133-134). Why not: every cut pause would end at 0.30 s, ref 01 §8's own cut threshold. We pad 0.10 s (0.20 s stays) and widen an edge toward 0.20 s only where its ramp zone is not quiet.
- §2: HF filler example list `"um,uh,like"` (HF: skills/media-use/references/operations.md:147). Why not: bare-token matching removes every "like", verbs included; HF's own test drops "LIKE" (HF: packages/cli/src/media-use/lib/cutlist.test.mjs:54-68). Only hesitation tokens are auto-removed; context words go only when the LLM names their word ids (picking stays with the LLM, ref 02).
- §2: Ramps only on interior splices, none at the export's own start/end (HF: skills/media-use/scripts/transcript-cut.mjs:106-108; packages/cli/src/media-use/lib/transcriptCutFade.mjs:7-8). Why not: a clip's first and last edges are also cuts into running audio; the 30 ms ramp ends inside ref 02's 0.05/0.15 s pads, so it still reads as ref 01 §5's hard cut.
- §2: A+V segments with PCM audio cut straight from the AAC source by input seek (HF: skills/media-use/scripts/transcript-cut.mjs:184-216). Why not: tested on ffmpeg 7.1: plain `-ss` into an audio-only .m4a decoded the first 1-17 ms wrong (error up to 65% of the peak); seeks into an A+V .mp4 were exact only because the demuxer seeks to a video keyframe. A whole-second pre-roll matched a full decode within 7e-6 on both, and HF pre-rolls the same way (HF: packages/producer/src/services/render/audioTruePeak.ts:105-107). One stem decode works on either file and gives exact sample counts per segment.
- §2: HF skipped-speech constant as the quiet threshold, mean power > 0.3 × the window mean (HF: packages/cli/src/whisper/parakeet.ts:163). Why not: it was built for token-free stretches of at least 1 s and floats with talk time (about -8.4 dB re speech at 48% talk time, -8.0 dB in the test fixture). Ours is fixed against speech, median word-block power − 15 dB; in a lavfi fixture it kept a -1.5 dB laugh and removed a -25.4 dB breath.
- §2: A re-ASR caption-sync gate, median |Δ start| ≤ 1 frame against a second faster-whisper pass (proposed during the study, not HF code). Why not: a second ASR pass carries its own word-time error, likely above a 1-2 frame tolerance (not measured); the deterministic remap and the stem-sample gate check the same chain without that noise. Caption timing from pixels belongs to ref 04 §1.
- §2: Two-tier pads (0.15 s for gaps ≥ 0.6 s, 0.08 s for 0.3-0.6 s) and a 0.20 s minimum removal (proposed during the study). Why not: the tiers are non-monotonic (a 0.59 s gap ends at 0.16 s, a 0.61 s gap at 0.30 s), and a 0.20 s minimum removal would leave gaps uncut against ref 01 §8: 0.30-0.40 s gaps with 0.10 s pads, 0.30-0.50 s with 0.15 s pads.
- §2: A single-pass `trim=start_frame`/`atrim` + concat filter graph (idea from HF: packages/cli/src/commands/measure/extract.ts:100-106). Why not: per-segment early seeks with floored 6-decimal times plus a canvas-grid `trim` (ref 03 §2 **Video splice**) tested exact at 30/29.97/60 fps and on 25 fps and VFR sources re-timed to 30, and allow a per-segment frame check; one long graph needs a filter script on Windows. It can be added later as an alternative.
- §2: Hold 0.3-0.75 s before the payoff, the "dramatic comma" (HF: skills/hyperframes/references/motion.md:24; .agents/skills/motion-doctrine/SKILL.md:140-143). Why not: ref 01 §8 wins: "gaps ≥ 0.3 s between phrases are cut unless they are a visual payoff"; a kept pause before a spoken payoff was not measured in the reference Shorts.
- §3: HF duck defaults 0.25 (-12 dB), 0.15 s attack, 0.4 s release (HF: packages/cli/src/media-use/lib/duck.mjs:36-39; skills/media-use/scripts/audio-duck.mjs:13-16). Why not: ref 01 §6 wins on style: about 10 dB down, attack 20 ms, release 300 ms; HF's own "about 0.3-0.4" (HF: skills/media-use/references/mixing.md:68) brackets our 0.316. Ref 03 §3 **Transcript duck lane** takes only HF's mechanism.
- §3: Level-match duck as the default: headroom 6 + 12s dB, max duck 24s dB; the default s = 0.8 gives 15.6 dB and 19.2 dB (HF: packages/core/src/audioCarve.ts:245-264,672-727). Why not: ref 01 §6 fixes a duck of about 10 dB; the per-span margin in ref 03 §3 **Audio gates** catches a bed that still fights the voice.
- §3: A 2.4 s bed release as the default (HF: packages/core/src/audioCarve.ts:512-527). Why not: ref 01 §6 "release 300 ms" wins; it is kept as the Optional ref 03 §3 **Calm release**, on request.
- §3: Bed fade-in 0.4 s and fade-out 1.5 s (HF: skills/hyperframes/references/film.md:32); "end on a bar line with a short fade under the end card" (HF: skills/hyperframes/references/sound.md:20); fades after trimming (HF: skills/media-use/audio/references/bgm.md:36). Why not: ref 01 §2 "The music bed is at full level from frame 0" and the Defaults Ending row (clean hard cut) win; only 5 ms de-click ramps are kept.
- §3: SFX at volume ~0.35 under voice and bed (HF: skills/media-use/audio/references/sfx.md:44); hits 3-6 dB over the bed (HF: skills/hyperframes/references/sound.md:37). Why not: ref 01 §6 "SFX peaks reach about -11 dBFS" wins.
- §3: "Rotate two or three takes of a repeated sound" (HF: skills/hyperframes/references/sound.md:38). Why not: ref 01 §5 and the Defaults SFX row are stricter: never reuse a sample within a clip.
- §3: Skip a missing SFX, never block the render (HF: skills/media-use/audio/references/sfx.md:32,45). Why not: the Defaults SFX row requires one distinct SFX per accent; ref 03 §3 **Distinct-variant library** fetches a new file or reports the breach.
- §3: The Broadcast voice preset for "shouty streams" (HF: packages/core/src/audioFxPresets.ts:110-128). Why not: HF describes it as "denser and more forward: a radio-presenter sound", not a fix for shouting, and the trigger was never measured. Clean Voice is the one default chain; the ffmpeg translation of Broadcast parses on 7.1 if a request asks for it.
- §3: A -16 LUFS default target (HF: packages/studio-server/src/helpers/loudness.ts:503); "mix around -16 to -14 LUFS for social" (HF: skills/hyperframes/references/sound.md:43). Why not: ref 01 §6 sets -14 LUFS, gated at -14 ±1 LU.
- §3: A bed under a voice at ~0.14 volume (HF: skills/hyperframes/references/sound.md:43), BGM_BED_VOLUME 0.12 ≈ -18 dB (HF: skills/media-use/audio/references/bgm.md:34), about -31 LUFS under TTS (HF: skills/media-use/audio/references/tts.md:21). Why not: ref 01 §6 wins: bed at -20 in gaps, ducked about 10 dB, so about 16 dB under -14 LUFS dialogue (16.1-16.4 dB measured), inside HF's own range.
- §3: Baked `sidechaincompress=threshold=0.03:ratio=8:attack=200:release=400` (HF: skills/media-use/references/operations.md:177-181). Why not: its 200 ms attack contradicts ref 01 §6 "attack 20 ms", and a reactive key lets the first syllable through; ref 03 §3 **Transcript duck lane** replaces it.
- §3: A duck ramp starting at the span start (HF: packages/cli/src/media-use/lib/duck.mjs:43-48,65-69). Why not: each phrase's first 150 ms plays over a bed that is still falling; our 20 ms ramp ends at the span start instead.
- §3: A steepest-rise anchor for slow whooshes (HF: docs/packages/cli.mdx:764-766). Why not: on noise whooshes the steepest 4 ms-RMS frame is jitter (0.380 s here, 13 ms before the peak, while the envelope's steepest rise was at 0.200 s), and an early anchor puts the swell after a 2-6 frame whip. The peak anchor follows HF: skills/hyperframes/references/sound.md:36 and skills/media-use/audio/assets/sfx/manifest.json:85.
- §3: Clean Voice's own -1 dB limiter inside the dialogue chain (HF: packages/core/src/audioFxPresets.ts:107). Why not: the static gain after the chain would overrun it; one master limiter runs last (HF: packages/core/src/audioLeveller.ts:201-210).
- §3: Refusing (reference match) or capping (absolute target) gains beyond +12 dB (HF: packages/studio-server/src/helpers/loudness.ts:395-401,523-545). Why not: ref 01 §6 wants dialogue at about -14 LUFS whatever the source level, so ref 03 §3 **Dialogue chain, static gains** warns instead.
- §3: A 100 ms-window voice-over-bed gate, ≥ 10 dB in ≥ 95% of speech windows (proposed during the study, built on HF's audioCarve.ts windowing). Why not: it fails a mix built exactly to ref 01 §6: syllable troughs gave p05 2.4-6.9 dB, and only 45-77% of windows reached 10 dB, while per-span margins were 16.1-16.4 dB.
- §3: Pitch-preserving speed changes: atempo chains and 0.25 s rate slices (HF: packages/engine/src/services/audioMixer.ts:111-162), bullet and slow-mo presets (HF: packages/core/src/speedRamp.ts:166-172,225-230). Why not: ref 01 §5 "Never use: ... slow motion, speed ramps"; over-length clips follow ref 02 rule 5.
- §4: An atmosphere opacity floor of 15-25% for low-opacity layers (HF: skills/hyperframes/references/look.md:52). Why not: design guidance for drawn atmosphere layers; ref 01 §7 sets the bloom at 12-18% (screen blend), and the grade gate measures the result.
- §4: Avoid full-screen linear gradients on dark grounds (HF: skills/hyperframes/references/look.md:51). Why not: guidance for drawn backgrounds; ref 01 §1 clips are full-bleed footage with no gradient backgrounds.
- §4: `aq-mode=3:aq-strength=0.8` (plus `deblock=1,1`) on every non-ultrafast encode, and aq-mode 3 at CRF ≥ 20 as an option (HF: packages/engine/src/services/chunkEncoder.ts:406-407,427-434). Why not: no consistent banding gain in synthetic dark-vignette tests with HF's params: the flat 8×8 share went 0.104 → 0.129 (CRF 16) and 0.192 → 0.208 (CRF 20) on a grey vignette with grain, and 0.994 → 0.999 on an all-dark one; a reported 89% → 74% at CRF 20 did not reproduce. `deblock=1,1` lowered Laplacian variance 767 → 758 on a grainy frame, and ref 01 §7 gates sharpness.
- §4: `-video_track_timescale 90000` (HF: packages/engine/src/services/chunkEncoder.ts:548-549). Why not: not needed: ffmpeg's default MP4 timescale was 15360 at 60 fps (256 per frame) and 30000 at 30000/1001 (1001 per frame), both exact; the ref 03 §4 **Delivery gate** reads `stts`.
- §4: The even-dimension pad `pad=ceil(iw/2)*2:ceil(ih/2)*2` (HF: packages/engine/src/utils/evenDimensions.ts:19-23). Why not: canvases are fixed even sizes (1080×1440, or 1080×1920 on request), and crops are scaled to them.
- §4: A locked closed GOP for chunk concat: `-g`/`-keyint_min`/`-sc_threshold 0` plus `scenecut=0:open-gop=0:repeat-headers=1` (HF: packages/engine/src/services/chunkEncoder.ts:216-243). Why not: it is needed for chunks cut from one stream or for HLS, and EffectCraft parts are independent encodes. A `-c copy` concat of 3 independent libx264 parts (B-frames on and off) gave 225 frames = the sum of the parts, one `stts` entry, 0 off-grid and first pts 0; the frames == sum check covers this case.
- §4: A PSNR floor of 32 dB (HF: packages/engine/src/utils/psnr.ts:37-40) as proof of an untouched mux. Why not: a stream-copy mux must be picture-identical: render vs final PSNR was inf, also after an `h264_metadata` re-tag, so 32 dB would pass a re-encode. An unchanged picture is proven by stream hash (ref 05 §2 **Prove the freeze**).
- §4: Render provenance metadata tags (HF: docs/guides/rendering.mdx:217-238). Why not: we strip all global metadata with `-map_metadata -1`, because cuts inherit the source title and URL, and set at most a clip title.
- §4: `-avoid_negative_ts make_zero` on video-only encodes (HF: packages/engine/src/services/chunkEncoder.ts:556). Why not: unnecessary with `-bf 0` (DTS = PTS from 0, tested); the ref 03 §4 **Delivery gate** rejects any empty edit.
- §4: Pad/trim after the AAC encode by decoding and re-encoding it (HF: packages/producer/src/services/render/audioPadTrim.ts:16-19,171-185). Why not: the float mix is fitted to N frames before the single AAC encode, so there is no second AAC generation; only the ref 03 §3 **True peak after AAC** correction re-encodes, and it starts from the PCM.
- §4: HF's intermediate x264 CRF 18 veryfast with `pcm_s16le` audio (HF: skills/media-use/scripts/transcript-cut.mjs:202). Why not: our intermediates are re-encoded after EffectCraft or the grade, so CRF 12 keeps the generation loss low, and intermediates carry no audio (ref 03 §2 **Dialogue stem**).
- §4: `--copy` stream-copy cutting, which only warns at more than 1 s of drift (HF: skills/media-use/scripts/transcript-cut.mjs:145-159). Why not: copy cuts snap to keyframes, and 1 s is 60 frames at 60 fps, far looser than the exact-frame ref 03 §2 **Splice gates** on clips ≤ 59.5 s. Every cut is re-encoded.
- §4: 60 fps is "wasted on a talking-head clip" (HF: docs/guides/rendering.mdx:312). Why not: ref 01 §1 and the SKILL Defaults win: 60 fps when the source is 50/60 fps, 30 otherwise.
