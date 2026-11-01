# HyperFrames study: verified draft sections

Distilled rules from the HyperFrames study (method and raw notes: `hyperframes.md` in this folder).
All 9 sections are independently verified. Verifiers re-opened every HyperFrames citation (693 claims checked, 62 refuted and fixed or removed, 91 line ranges corrected). They re-ran every ffmpeg command or snippet on synthetic media (360 runs, 15 failures fixed) and applied one owner per topic.
Next step: the cross-section reconciliation turns these into `skill/references/03-05`. Until then this file is not part of the installed skill.

<!-- G1 = ref 03 §1 | verified (fixed) -->
> **ref 03 §1: verified**

## Source intake: probe, normalise, ASR words
Scope: download -> `source_facts.json` + `transcript.json`. Tested on ffmpeg 7.1.

### Adopted (default)
1. **Probe once.** Write `source_facts.json`:
   - displayed W x H (swap if rotation % 180 = 90), SAR, duration, audio; `fps_r` (`num/den`), `fps_avg`, `vfr` = abs(avg - r) / r > 1%;
   - matrix/primaries/transfer/range; untagged matrix: bt709 if H >= 720 and not VP9/AV1, else smpte170m.
   - No ffprobe: `ffmpeg -hide_banner -i SRC` stderr (`N fps` = avg, `N tbr` = r); W x H from the comma part matching `^\d+x\d+`; snap a printed rate p to n = round(1.001p) or n x 1000/1001 if within 0.005.
   Why: later steps read these.
   HF: packages/cli/src/measure/media.ts:109-134, packages/engine/src/services/videoFrameExtractor.ts:220-227,971-979
2. **SDR at download.** Refines SKILL step 1 (old: "the best mp4"): `-f "bv[dynamic_range=SDR][ext=mp4]+ba[ext=m4a]/bv[dynamic_range=SDR]+ba/bv*+ba/b"`. HDR = transfer `smpte2084`/`arib-std-b67`; BT.2020 primaries alone are SDR.
   Why: yt-dlp sorts HDR first ("best mp4" took AV1 HDR10 in a test); `bv` (video-only) skips 360p combined SDR.
   HF: packages/engine/src/utils/hdr.ts:16-21
3. **Normalise every clip read.** Every ffmpeg read of source video starts `-vf` with `norm_vf`:
   - `fps=<canvas>` first (scale-then-fps lost a frame: 89 of 90);
   - `scale=trunc(iw*sar/2)*2:ih,setsar=1` if SAR != 1;
   - HDR: **HDR fallback**; SDR BT.2020: its tail from `zscale=p=bt709`; BT.601: `scale=in_color_matrix=bt601:out_color_matrix=bt709`;
   - last `setparams=colorspace=bt709:color_primaries=bt709:color_trc=bt709:range=tv`.
   - Encode: → ref 03 §4 **Seekable mezzanine**. cv2 never opens the raw download; detectors may set their own `fps=`.
   - Refines ref 01 §1 and Defaults Canvas (old: "60 fps if the source is 50/60"): 60 when `fps_avg` >= 50.
   - Re-time only with `fps=`; never relabel the rate (input `-r`, `setpts=PTS*k`): 0.1% = 60 ms/min drift.
   Why: cv2 indexed VFR at 48.16 fps, up to 0.488 s off; relabelled BT.601 red decoded (255,23,0), BT.2020 (200,60,40) as (171,87,52); converted (251,0,0), (199,58,39).
   HF: packages/cli/src/commands/measure/probe.ts:46-66, packages/engine/src/services/videoFrameExtractor.ts:1171-1173
4. **HDR fallback.**
   - `zscale=t=linear:npl=100,tonemap=hable:desat=0,zscale=p=bt709:t=bt709:m=bt709:r=tv,scale=out_color_matrix=bt709:out_range=tv`;
   - tags missing on frame 0 (`-frames:v 1 -vf showinfo`): prefix `setparams=` from the probe, else bt2020nc/bt2020; untagged, zscale fails;
   - no `zscale`/`tonemap` in `ffmpeg -hide_banner -filters`: stop with a fix hint.
   - Refines ref 01 §0.3 (old: "Measure source against output"): HDR source frames = this SDR copy.
   Why: PQ read as SDR: SATAVG 23 vs 64 tone-mapped; unnamed matrix: pure red/green Y 73/181, not 63/173.
   HF: packages/core/src/hdrToneMap.ts:15-43, packages/studio-server/src/helpers/proxyTranscoder.ts:679-686
5. **ASR on the video's clock.** Refines SKILL Generic gotchas (old: "decode with ffmpeg to 16 kHz mono float32"): always decode ASR audio with `-vn -af aresample=async=1:first_pts=0 -ac 1 -ar 16000 -f f32le -`.
   - Offset (video's vs ASR audio): 20 s at start, middle, end (same filter, `-ar 8000`); rises of 10 ms RMS; Pearson over ±500 ms (≥ 50 values), r <= 0.3 not judged; median (ours; HF: first 20 s).
   - abs(offset) > 1 canvas frame: add it to every word time (+ = video's audio late).
   Why: audio muxed 0.25 s late decoded 0.23 s early without the filter (~14 frames at 60 fps; PyAV too); +40 ms read 40.
   HF: packages/cli/src/measure/diff.ts:1059-1100
6. **Language and names.** Pass `language=` (yt-dlp `language`, else `detect_language` on 30 s of speech); `.en` models only for `en`; speech over music/crowd starts at `medium`. Refines SKILL Tool discovery (old: "`medium` for better accuracy on bigger GPUs"). Metadata names go to the caption cleanup (→ ref 04 §1 **Token timing contract**), never `hotwords`/`initial_prompt`.
   Why: `.en` models translate (HF); on noise `detect_language` said `nn` (p 0.45-0.53); seeded names landed in noise.
   HF: skills/media-use/audio/references/transcribe.md:14-22,37, .agents/skills/changelog-video/SKILL.md:118-120
7. **Normalise words.** Keep `raw_words.json`; `transcript.json` =
   - drop non-words: empty, `[_`/`[BLANK`, only ♪/�; fillers stay (→ ref 03 §2 **Fillers: safe list**);
   - join punctuation-only, `'t 'm 's 've 're 'll 'd` and no-leading-space tokens to the previous word; merge lone capital (not I/A/O) + lowercase word, lowercase end + `in'`;
   - spread start >= end runs evenly from previous end to next start (0.3 s/word at the end); round to ms;
   - ours: >= 1 canvas frame between starts (shift <= 2 frames);
   - clamp start >= 0, end = min(dur, max(start, end)); flag spans < 0.05 s; ids `w0..wN`; fixes key on ids; assert starts non-decreasing.
   Why: zero-length runs pop together (seeded `tiny`: 184-186 words, 178-183 zero-length); text matching gives a repeated word the wrong time.
   HF: packages/cli/src/whisper/normalize.ts:70-149,162-164,529-543, skills/media-use/audio/references/captions/transcript-handling.md:31, skills/hyperframes/references/captions.md:9
8. **Failure gate + hallucinations.** New SKILL step 2 gate:
   - per 60 s window, junk > 20% of entries: next model (small -> medium -> large-v3); LLM-flagged nonsense while picking: same, then re-pick;
   - `silencedetect=noise=-35dB:d=0.6`: drop words starting in the final silence (`silence_end` absent or >= duration - 0.05; 7.1 prints it at EOF);
   - ours: in other silences drop stock phrases (you, thank you, thanks for watching, subscribe, subtitles by) and metadata names starting in [start, end - 0.3 s].
   Why: Whisper invents "Thank you." over silence (HF); the seeded loop sat in the final silence (0% junk).
   HF: skills/hyperframes/references/captions.md:8-10
9. **Dropped-speech repair.**
   - Cut ~60 s windows at the quietest 100 ms within ±5 s.
   - Window with words: a gap >= 1.0 s (edges count) with mean(x^2) > 0.3 x the window's is skipped speech.
   - Re-decode [g0 - 0.5, g1 + 0.5] after 0.5 s of zeros (`vad_filter=False, condition_on_previous_text=False`); t -> max(0, t - 0.5) + lo.
   - Add words starting in the gap minus neighbours re-heard within 0.3 s of an edge (letters-only); **Normalise words** and the **Failure gate** apply. None added: re-decode the padded window; keep it if it has more words.
   - Leftovers -> `suspect_gaps`: no captions, never dead air (→ ref 03 §2 **Dead air**).
   Why: skipped speech = missing captions + cuts through it.
   HF: packages/cli/src/whisper/parakeet.ts:153-274, packages/cli/src/whisper/sherpaWorker.ts:30-81
10. **Script hygiene.** Refines SKILL Generic gotchas (old: "Set `PYTHONIOENCODING=utf8`"):
    - `for s in (sys.stdout, sys.stderr): s.reconfigure(encoding="utf-8", errors=s.errors)`; `encoding="utf-8"` on text IO; subprocess `errors="replace"`;
    - JSON on stdout, logs on stderr, exit 0/1/2 (ok/failed/usage); background job logs end `DONE ok|fail`; wait on it, never `pgrep -f`.
    Why: on Windows a non-cp1252 glyph printed to a pipe exited 1; `open()` defaulted to cp1252.
    HF: skills/media-use/audio/scripts/extract-audio-data.py:25-31,60-65, packages/cli/AGENTS.md:12-26, skills/hyperframes-cli/SKILL.md:66

### Optional
1. **Parakeet engine.** With `sherpa_onnx` + the int8 `parakeet-tdt-0.6b-v3` export (25 languages): `nemo_transducer`, greedy search, 16 kHz, 80-dim features, 4 threads; then **Normalise words** onward. WER/speed claims unverified: A/B on 2-3 sources first.
   HF: packages/cli/src/whisper/sherpa.ts:338-354, packages/cli/src/whisper/parakeet.ts:4-8,33-35

#### Not adopted
- HF `probe --normalize`: one whole-source CFR copy at the standard rate nearest the average (24000/1001, 24, 25, 30000/1001, 30, 50, 60000/1001, 60), AAC 192k (packages/cli/src/commands/measure/probe.ts:29-66): Defaults fix the canvas at 60 fps (30 under 50 fps), so each clip read is normalised straight to the canvas rate. A CRF-12 transcode of a 1-2 h source would break ref 02 rule 12's <= 40 min benchmark.
- Keeping 60000/1001 for 59.94 sources (reader proposal): Defaults: the canvas is 60 fps. `fps=60` duplicates 4 frames per 60 s (tested: 3597 in, 3601 out) with no A/V drift. Only relabelling the rate is banned.
- HF engine VFR threshold: 10% of max(r, avg) (packages/engine/src/utils/ffprobe.ts:974-975): We keep the measure tools' 1% (packages/cli/src/measure/media.ts:133). norm_vf resamples every source anyway, so `vfr` only adds a warning, and 1% also flags stream VODs with dropped frames.
- Seeding names into ASR via `hotwords`/`initial_prompt`: Tested offline with faster-whisper 1.2.1 on noise and silence: seeded names were written into non-speech, and a name prompt at temperature 0 made `tiny` loop 184-186 words. HF keeps whisper for timestamps only and fixes display spelling afterwards (.agents/skills/changelog-video/SKILL.md:118-120).
- External transcription API or user-supplied text as the failure fallback (skills/media-use/audio/references/captions/transcript-handling.md:41-43, 62-91): Dependencies stay within requirements.txt + ffmpeg. The local ladder small -> medium -> large-v3, then re-pick, covers it. A request can still ask for an API.
- HF default whisper models `small.en`/`medium.en` (skills/media-use/audio/references/transcribe.md:3,18; skills/hyperframes/references/captions.md:6): The SKILL keeps multilingual `small`/`medium`. A `.en` model is used only when the language is English, because `.en` models translate (HF).
- Parakeet-TDT as the default local engine (skills/media-use/references/operations.md:107-112; packages/cli/src/whisper/parakeet.ts:4-8): It needs sherpa-onnx, which is outside requirements.txt, and HF's WER/speed claims are unverified here. It stays Optional, behind an A/B.
- probe.ts tone-map order: primaries converted in linear light before hable (packages/cli/src/commands/measure/probe.ts:57): We keep one chain: HF's shared helper (packages/core/src/hdrToneMap.ts:29, used at videoFrameExtractor.ts:1194, proxyTranscoder.ts:682 and snapshot.ts:608) plus the named-matrix step (proxyTranscoder.ts:683). Without that step, tone-mapped pure red read Y 73, not 63.
- HF caption cleaner's short-filler drop: huh/uh/um/ah/oh shorter than 0.1 s (skills/media-use/audio/references/captions/transcript-handling.md:55): Fillers stay in transcript.json with ids. Ref 03 §2 **Fillers: safe list** cuts hesitations, ref 04 §1 **Token timing contract** drops them from captions, and 'OH!'/'AH!' can be reactions.
- Rejecting decimal frame rates such as 29.97 (packages/core/src/fps.ts:63-71): Canvas rates are integers (60/30) and `fps_r` is stored as `num/den`. 29.97 vs 30000/1001 differs by 1e-6, which is 0.06 ms/min.

<!-- G2 = ref 03 §2 | verified (major_rewrite) -->
> **ref 03 §2: verified**

## Cut list and splicing: frame-exact, click-free, one clock
Scope: word ids -> `cutlist.json` -> video-only `cut.mov` + one dialogue stem, one clock for all later timing.

### Adopted (default)
1. **Cut points by word id.** `transcript_lines.txt` lines start `[w812-w840] mm:ss  SPEAKER:`. The LLM writes `start_word`, `end_word`, `remove_words: [[i, j]]` (inclusive), `keep_gaps: [i]` (visual-payoff pauses); never seconds.
   - Python fills `start`/`end` (ref 02: -0.05/+0.15 s); rejects ids out of range, reversed or overlapping, and picks whose first/last 3 bare tokens miss `hook_line`/`payoff_line`.
   - Refines ref 02 rules 1-2, SKILL steps 2-3 (old: "`mm:ss  SPEAKER: sentence`"; "`{rank, score(1-10), start, end, ...}`").
   Why: lines carry 1 s timestamps; typed seconds miss word edges.
   HF: packages/cli/src/media-use/lib/cutlist.mjs:77-96
2. **One compiler per clip.** Python writes `cutlist.json`:
   - removals clamped to the window, sorted, merged when `start ≤ prev.end`, inverted, snapped (**Frame grid**);
   - kept pieces < 0.20 s: dropped if no word starts in them, else grown to 0.20 s (warn);
   - `kept_s` (+ any freeze hold) is the table's Length; assert ≤ 59.5 s before any render, else ref 02 rule 5.
   - "Keep the pauses" skips the gap pass.
   Why: one source of truth; an over-length clip fails in seconds.
   HF: packages/cli/src/media-use/lib/cutlist.mjs:6-29, 149-183
3. **Dead air: cut inside the gap, only silence.** Gap ≥ 0.30 s between kept words, not in `keep_gaps`: remove `[prev.end + 0.10, next.start - 0.10]` (0.20 s stays).
   - Quiet = 10 ms block power ≤ median word-block power - 15 dB (ours).
   - An edge whose 30 ms ramp zone is not quiet moves 0.05 s away from its word (pad ≤ 0.20 s).
   - A non-quiet run ≥ 0.10 s in a gap (laugh, skipped word) counts as a word; skip removals < 0.10 s.
   - Refines ref 01 §8 (old: "gaps ≥ 0.3 s between phrases are cut unless they are a visual payoff").
   Why: ASR word edges drift; raw-edge cuts clip tails; unrecognised sound is not dead air.
   HF: packages/cli/src/media-use/lib/cutlist.mjs:121-138; packages/cli/src/whisper/parakeet.ts:153-170
4. **Fillers: safe list.** Auto-remove only bare tokens (`re.sub(r'^[\W_]+|[\W_]+$', '', w.lower())`) in {um, umm, uh, uhh, uhm, er, erm}; like, so, oh, ah, you know only by LLM ids. Removed words leave the word list before the gap pass (pause + "um" + pause = one splice), each removal covering the word's `[start, end]`.
   Why: HF's documented `"um,uh,like"` deletes every verb "like"; "OH!" is often the reaction.
   HF: packages/cli/src/media-use/lib/cutlist.mjs:99-119; skills/media-use/references/operations.md:147
5. **Frame grid** (whole pipeline). `fps` = the file's exact rate (`Fraction`).
   - Boundaries (segment in/out): nearest frame edge, `k = round(t·fps)`; touching segments merge.
   - Events/samples (reveal, accent cause, sampled frame): the frame on screen at t, `k(t) = ⌊(t + 0.0005)·fps + 1e-6⌋` (0.5 ms absorbs ms rounding).
   - Times handed to ffmpeg: `T(k)` = k/fps floored to the µs, 6 decimals (`"%d.%06d"`), never 3.
   - Tested: `-ss 12.867` at 30 fps starts on frame 387, not 386; 3-dp `-ss/-t` miscounted 16-40 of 48 random cuts per rate, 6-dp 0 of 144 (60/30/29.97).
   Why: a boundary is an edge: nearest stays within ½ frame, inside the pads; an event must show on the frame on screen at t, never later.
   HF: skills/media-use/scripts/transcript-cut.mjs:278-285; skills/reverse-any-video/SKILL.md:19
6. **Video splice.** Cut from the clip's normalised CFR intermediate (→ ref 03 §1 **Normalise in every clip intermediate**), so face tracks, cut detection and the splice share frame k; clock = source time - its start W0.
   - Per segment, n = ko - ki: `ffmpeg -y -nostdin -ss T(ki) -i clip.mov -t T(n) -an -c:v libx264 -preset veryfast -crf 12 -fps_mode cfr -force_key_frames "expr:gte(t,n_forced)" seg_0000.mov` (flags: ref 03 §4 **Seekable mezzanine**; no `-frames:v`: it hides miscuts).
   - Join: `ffmpeg -f concat -i list.txt -c copy cut.mov` (list → ref 03 §4 **Windows-safe ffmpeg**).
   Why: CFR, exact frames (tested), 1 s keyframes for seeking.
   HF: skills/media-use/scripts/transcript-cut.mjs:101-103, 203-209
7. **Dialogue stem: one pre-rolled decode.** `ffmpeg -ss P -i SRC -map 0:a:0 -af "aresample=48000:async=1:first_pts=0,pan=mono|c0=0.5*c0+0.5*c1,atrim=start_sample=S0:end_sample=S1" -f f32le -`
   - t0 = W0 + K0/fps (K0 = first ki); P = max(0, ⌊t0⌋ - 1); S0 = round(t0·48000) - 48000·P; S1 likewise from the last ko.
   - Mono source: `pan=mono|c0=c0`; never `-ac 1` (3.0 dB hotter as f32le than s16le).
   - `async=1:first_pts=0` as in the ASR decode (ref 03 §1): without it, audio 0.25 s late made the stem 229 ms early at P = 0.
   - Float PCM until the single AAC (→ ref 03 §4 **One AAC encode, copied at the mux**); never AAC per segment (+29-31 ms and zero runs up to 19 ms each).
   Why: an AAC decode needs warm-up; per-segment encodes add priming gaps.
   HF: packages/producer/src/services/render/audioTruePeak.ts:105-107; skills/media-use/scripts/transcript-cut.mjs:96-100
8. **Ramps on every edge.** Slice the decode `x` in numpy, per segment `x[a:a+m]`, `a = round(ki·SR/fps) - round(K0·SR/fps)`, `m = round((o+n)·SR/fps) - round(o·SR/fps)` (o = output frame offset, SR = 48000), so Σm = round(Σn·SR/fps).
   - 30 ms linear ramps at both ends: `np.linspace(0, 1, min(1440, m // 4))`.
   - Clip start/end ramp too, inside ref 02's 0.05/0.15 s pads: a de-click, still ref 01's hard cut, no fade-in (§2, §5).
   - Tested click ratio (**Splice gates**): 0.14-0.16 ramped, up to 32 unramped.
   Why: an unramped join clicks.
   HF: packages/cli/src/media-use/lib/transcriptCutFade.mjs:5-21; skills/media-use/scripts/transcript-cut.mjs:106-114
9. **One clock.** Cut first, then caption: `remap(t) = (o + t·fps - ki)/fps` for the segment holding t; words starting in a removal drop; words crossing `ko` clamp.
   - Captions, crop path (output frame f <- source frame `ki + f - o`; face tracks stay cached in source frames), accent/SFX cues and duck spans all use it, then **Frame grid**.
   Why: per-splice offsets add up.
   HF: docs/guides/captions-and-recuts.mdx:116-119
10. **No slivers at splices.** Splices feed the reframe (resets → ref 04 §2 **Classified cut detector**; same-camera scale change → ref 04 §2 **Face carried across jump cuts**).
    - A hard or soft source cut in a segment's first/last 0.20 s moves that edge onto it when no word overlaps the sliver; else warn `sliver_kept`.
    Why: no < 0.20 s flash of another shot at frame 0 or a join.
    HF: packages/cli/src/measure/cuts.ts:1-2
11. **Splice gates** (every clip, pre-render).
    - frames == Σn; every pts·tb == i/fps (`Fraction`); keyframe gap < 1.05 s; stem samples == round(Σn·SR/fps).
    - Per splice: max |Δ| within ±5 ms ≤ 2 × the 99.9th pct of |Δ| over ±250 ms outside it; exact-zero runs < 20 samples within ±50 ms unless the source has that run.
    - Without ffprobe: `ffmpeg -v error -i cut.mov -map 0:v:0 -c copy -f framemd5 -` (rows = frames, `#tb`, pts), `ffmpeg -skip_frame nokey -i cut.mov -map 0:v:0 -vf showinfo -f null -` (keyframes), samples = bytes/2 of `-f s16le -`.
    Why: invisible on 1 fps review.
    HF: skills/media-use/scripts/transcript-cut.test.mjs:127-197, 243-264

### Optional
- **ffmpeg self-test** (new machine/build): cut testsrc2 + a 440 Hz sine at 30, 30000/1001 and 60 fps with HF's keeps 0.137-1.913, 2.845-4.111, 4.9-5.47; gates pass, and negative controls (per-segment AAC, 3-decimal times) fail them.
  HF: skills/media-use/scripts/transcript-cut.test.mjs:50-52

#### Not adopted
- HF --cut-silence example threshold of 0.8 s (docs/guides/captions-and-recuts.mdx:42; skills/media-use/references/operations.md:148): Ref 01 §8 wins on pacing: gaps ≥ 0.3 s between phrases are cut. We keep the 0.30 s trigger.
- HF 0.15 s silence pads on each side (packages/cli/src/media-use/lib/cutlist.mjs:4, 133-134): Every cut pause would end at 0.30 s, which is ref 01 §8's own cut threshold. We pad 0.10 s (0.20 s stays) and widen an edge toward 0.20 s only where its ramp zone is not quiet.
- HF filler example list "um,uh,like" (skills/media-use/references/operations.md:147): Bare-token matching removes every 'like', verbs included; HF's own test drops 'LIKE' (packages/cli/src/media-use/lib/cutlist.test.mjs:54-68). Only hesitation tokens are auto-removed. Context words go only when the LLM names their word ids (picking stays with the LLM, ref 02).
- HF caption cleaner's huh/uh/um/ah/oh < 0.1 s list used as an auto-cut list (skills/media-use/audio/references/captions/transcript-handling.md:55): 'OH!'/'AH!' are often the reaction itself (ref 01 §3 keeps hype lines). Auto-cut stays on the hesitation safe list.
- Ramps only on interior splices, none at the export's own start/end (skills/media-use/scripts/transcript-cut.mjs:106-108; packages/cli/src/media-use/lib/transcriptCutFade.mjs:7-8): A clip's first and last edges are also cuts into running audio. The 30 ms ramp ends inside ref 02's 0.05/0.15 s pads, so it still reads as ref 01 §5's hard cut.
- A+V segments with PCM audio cut straight from the AAC source by input seek (skills/media-use/scripts/transcript-cut.mjs:184-216): Tested on ffmpeg 7.1: plain -ss into an audio-only .m4a decoded the first 1-17 ms wrong (error up to 65% of the peak). Seeks into an A+V .mp4 were exact only because the demuxer seeks to a video keyframe. A whole-second pre-roll matched a full decode within 7e-6 on both, and HF pre-rolls the same way (packages/producer/src/services/render/audioTruePeak.ts:105-107). One stem decode works on either file and gives exact sample counts per segment.
- HF skipped-speech constant as the quiet threshold: mean power > 0.3 x the window mean (packages/cli/src/whisper/parakeet.ts:163): It was built for token-free stretches of at least 1 s, and it floats with talk time: about -8.4 dB re speech at 48% talk time, -8.0 dB in the test fixture. Ours is fixed against speech: median word-block power - 15 dB. In a lavfi fixture it kept a -1.5 dB laugh and removed a -25.4 dB breath.
- Re-ASR caption-sync gate (a reader proposal, not HF code): median |delta start| ≤ 1 frame against a second faster-whisper pass: A second ASR pass carries its own word-time error, likely above a 1-2 frame tolerance (not measured). The deterministic remap and the stem-sample gate check the same chain without that noise. Caption timing from pixels belongs to ref 04 §1.
- Two-tier pads (0.15 s for gaps ≥ 0.6 s, 0.08 s for 0.3-0.6 s) and a 0.20 s minimum removal (reader proposals): The tiers are non-monotonic: a 0.59 s gap ends at 0.16 s, a 0.61 s gap at 0.30 s. A 0.20 s minimum removal would leave gaps uncut against ref 01 §8: 0.30-0.40 s gaps with 0.10 s pads, 0.30-0.50 s with 0.15 s pads.
- Single-pass trim=start_frame/atrim + concat filter graph (idea from packages/cli/src/commands/measure/extract.ts:100-106): Per-segment input seeks with floored 6-decimal times tested exact at 30/29.97/60 fps and allow a per-segment frame check. One long graph needs a filter script on Windows. It can be added later as an alternative.

<!-- G3 = ref 03 §3 | verified (fixed) -->
> **ref 03 §3: verified**

## Audio: mix graph, ducking, loudness, SFX and audio gates
Scope: dialogue stem (ref 03 §2) to the checked AAC ref 03 §4 muxes. "Here" = ffmpeg 7.1, lavfi test media.

### Adopted (default)
1. **Float unity mix.**
   - Decode each stem once to f32 48 kHz stereo; upmix mono with `pan=stereo|FL=FL+FC|FR=FR+FC`, never `-ac 2`.
   - Sum in numpy at sample round(t·48000) in a buffer of the exact clip length (→ ref 03 §4 **Picture is the clock**). Intermediates stay `pcm_f32le` until the AAC.
   - ffmpeg path: per branch `adelay=delays=<n>S:all=1,apad,atrim=end_sample=<N>`, then `amix=inputs=K:duration=longest:dropout_transition=0:normalize=0`.
   Why: here `-ac 2` cost 3.01 dB; default amix cost 6.02 dB, then swelled 6 dB over 2 s after a branch ended; one-value `adelay` delayed only the first channel; an s16 intermediate clipped a +1.58 dBFS sum flat (36000 samples).
   HF: packages/engine/src/services/audioMixer.ts:226-229, :954-957, :1170-1176
2. **Envelopes as samples.** Multiply duck lanes and de-click ramps into the numpy buffer (`np.interp` per sample). Any `volume=...:eval=frame` expression stays ≤ 32 segments (RDP, epsilon 0.005 linear).
   Why: nested `if(lt(t,...))` failed graph init at 99 levels here (98 ran), dropping the audio.
   HF: packages/engine/src/services/audioVolumeEnvelope.ts:1-11; packages/engine/src/services/audioMixer.ts:199-224
3. **Dialogue chain, static gains.** Refines ref 01 §6 (old: "normalised to about -14 LUFS integrated").
   - Static pre-gain to -18 LUFS (ours), then Clean Voice: `highpass=f=80:poles=2,equalizer=f=250:t=q:w=1.2:g=-3,acompressor=threshold=0.1:ratio=3:attack=12:release=180:makeup=1.413,equalizer=f=3000:t=q:w=1:g=2.5`. Its -1 dB limiter moves to **Limiter last**.
   - Then one gain g = -14 - I, skipped within 0.5 LU. Warn if total gain > +12 dB (noise rises too). Never claim denoising.
   - No dynamic loudnorm: two-pass `linear=true` (I -14, TP -1.5, LRA 11) stays linear only if TP - I ≤ 12.5 dB and 0 < LRA ≤ 11, else goes dynamic (192 kHz out) silently; check `normalization_type`.
   Why: on a -40.6 LUFS stem the -20 dB threshold barely acted (PLR 26.1 vs 26.5 with EQ alone; pre-gained: 22.4); loudnorm went dynamic at TP - I 12.7, LRA 12.0 and LRA 0.
   HF: packages/core/src/audioFxPresets.ts:93-109, :147-150; skills/media-use/references/operations.md:193-200
4. **Measure the played window.** `ffmpeg -ss S -t D -i src -map 0:a:0 -vn -af ebur128=peak=true -f null -`, seeks before `-i` (times → ref 03 §2 **Frame grid**); parse the last summary `I:` and `Peak:` lines. Widen windows < 0.4 s (they read -70.0). Never gain-match a window ≤ -70 LUFS.
   Why: output-side `-t 4` read -20.0 LUFS for a window that is -60.0.
   HF: packages/studio-server/src/helpers/loudness.ts:448-457, :505-506
5. **Transcript duck lane.** Refines ref 01 §6 (old: "sidechain ducking (attack 20 ms, release 300 ms)"): same numbers, pre-rolled.
   - Spans = post-cut words (→ ref 03 §2 **One clock**) ∪ speech activity on the dialogue stem: 50 ms hop, 100 ms window, threshold max(-45, p90 - 30) dB, a span ends where ≥ 0.4 s below it starts, keep ≥ 0.3 s.
   - Merge spans when the gap < 0.6 s (short pauses stay ducked).
   - Bed gain 0.316 (-10 dB): 20 ms down-ramp ending at each span start, 300 ms up-ramp from its end; overlaps take the minimum; a bed entering mid-span starts ducked. Key = dialogue only.
   Why: a sidechain reacts after the first syllable; known times duck before it.
   HF: packages/cli/src/media-use/lib/duck.mjs:4, :36-103; packages/cli/src/audio/read/voice.ts:15, :126-157
6. **Bed entry, level, length.** Refines ref 01 §6 (old: "about -20 dBFS short-term in speechless stretches").
   - Offset = earliest point whose next 5 s reach the 75th percentile of all 5 s windows' mean short-term loudness (ours); S from ebur128's per-frame lines (`framelog=verbose` is silent at the default log level).
   - Unducked bed -20 LUFS over the used window.
   - Cover the clip: loop with a 0.3 s equal-power cos/sin crossfade.
   - No fades (ref 01 §2); 5 ms de-click ramps on the first and last samples.
   Why: a quiet intro drains the hook (an 8.3 s intro: offset 8.2 s here); a short file leaves a silent tail.
   HF: skills/media-use/audio/references/bgm.md:36; skills/hyperframes/references/sound.md:20; skills/media-use/audio/scripts/lib/bgm.mjs:205-226
7. **SFX on the hit.** Refines ref 01 §5 (old: "one SFX per flash or whip", no timing).
   - Per file, RMS of sqrt(mean of channel squares) every 1 ms over a centred 4 ms window; peak = argmax; onset = first ≥ 0.2 × peak; tail = last ≥ peak - 40 dB.
   - Start = (F + 1)/fps - peak_s for accent frame F (any class); start < 0 trims the head; decays run over the next cut.
   - Scale to -11 dBFS sample peak (ref 01 §6). QC: the SFX stem's peak lies in [F, F + 2].
   Why: the hit is not the file start (riser crest ≈ 2.5 s, whoosh 0.393 s here); a sound early reads wrong sooner than one late.
   HF: skills/hyperframes/references/sound.md:36; packages/core/src/audioAnalysis.ts:135-149, :332-361
8. **Distinct-variant library.**
   - A JSON manifest beside the SFX files: per file class (whoosh|hit|riser|boom), duration, onset/peak/tail, sample peak, md5, print, licence, source URL.
   - Same sound = equal md5, or print cosine ≥ 0.95 with length ratio 0.5-2. Print = sqrt of each octave's energy share (1/5-octave bands, 30 Hz-9 kHz) over 0.4 s from onset.
   - Before the first render: the manifest parses, every file decodes, distinct counts reach whoosh 4, hit 7, riser 2, boom 1 (ours, from ref 01 §5 maxima); short = warning `sfx_library_incomplete`.
   - Per clip: round-robin, no sound reused. An accent with no unused sound gets a new file (Openverse, CC0/CC BY only; credit CC BY on its own line of captions.md); none found = Defaults breach.
   Why: HF's own whoosh/whoosh-short and click/click-soft are byte-identical; a -9 dB copy scored cosine 1.000 here.
   HF: packages/cli/src/audio/read/effects.ts:14, :128-138, :205-263, :330; skills/media-use/audio/references/sfx.md:12
9. **Limiter last.** Master: float sum → static trim to -14 LUFS if |I + 14| > 0.5 → `aresample=192000,alimiter=limit=0.708:attack=5:release=50:level=0:latency=1,aresample=48000` (-3 dBFS: 2 dB under -1 dBTP) → AAC. No gain after it.
   Why: 7.1 defaults `level=1` re-normalised to 0 dBFS (+6.02 dB) and `latency=0` put audio 5.0 ms late; at 48 kHz a -2 dBFS limit left +3.5 dBTP on hot white noise; a mix with +5.5 dBTP plosives gave -2.9 dBTP (AAC -2.9 to -2.4), I -0.2 LU.
   HF: docs/reference/audio-effects.mdx:281-299; packages/core/src/audioLeveller.ts:201-210
10. **True peak after AAC.** Refines ref 01 §6 (old: "true peak ≤ -1 dBTP", no stage named). Encode once (→ ref 03 §4 **One AAC encode, copied at the mux**); measure the .m4a (last `Peak:`); require ≤ -1.0 dBTP. Else re-encode from the PCM with `volume=<att>dB`, att += -1 - 0.5·2^pass - max(tp_aac, tp_pcm + att); max 3 passes, then fail listing every pass.
    Why: AAC added 0.0-0.5 dB on mixes, 2.8 dB on limited white noise; one pass fixed that (+1.3 → -2.2 dBTP); a +5.5 dBTP PCM took two.
    HF: packages/producer/src/services/render/audioPadTrim.ts:49-52, :376-379, :442-451
11. **Audio gates** on audio.m4a and the stems. Refines ref 01 QC (old: "audio present"). Log `audio NN lufs:-14.1 tp:-2.4 lowered:0.0 clip:0 sil:0 vom:16`.
    - I -14 ±1 LU; TP per **True peak after AAC**; samples with |x| ≥ 0.999: 0.
    - `silencedetect=n=-50dB:d=0.1` reports nothing outside a planned ref 01 §6 mute (d=0.2 missed a 0.166 s tail here).
    - Per duck span (widened to ≥ 0.4 s): LUFS(dialogue) - LUFS(ducked bed) ≥ 12 dB; < 9 fails (ours). Fix: deepen that span by the shortfall, re-mix.
    - Bed energy below 150 Hz ≥ 50%: warn, pick another bed (phone speakers).
    - Every input decodes, has audio, is not silent in its used window.
    - Delivery note → ref 05 §1 **Measure, then look**.
    Why: ref 01 levels gave 16.1-16.4 dB span margins; HF dropped a 9 dB carve aim as "still fighting the voice"; 100 ms windows fail on syllable troughs (p05 2.4-6.9 dB).
    HF: packages/cli/src/audio/read/read.ts:161-180; skills/media-use/audio/scripts/carve.mjs:38-39; packages/core/src/audioCarve.ts:259-262; packages/cli/src/utils/checkAudio.ts:175-214

### Optional
12. **Even out speakers.** When speaking-window p80 - p20 > 6 dB (ours): HF's leveller before the static gain: 4096-sample windows, skip < peak - 42 dB, target p80, correct 0.55 × the gap, clamp ±12 dB, attack 0.35 s, release 0.9 s, snap < 0.4 dB.
    HF: packages/core/src/audioLeveller.ts:41-53, :73-76, :117-145
13. **Spectral carve.** If the bed must stay hot: peaking cuts (Q 1.4) on the bed at the voice's top 3 of 9 third-octave centres (160-6000 Hz), ranked with HF's 2 kHz weighting; -6 dB on the top band, -3 to -6 dB on the others; faded in by the duck lane.
    HF: packages/core/src/audioCarve.ts:25, :245-264, :443-495
14. **Calm release.** On request ("less pumping"): up-ramp 2.4 s. Refines ref 01 §6 (old: "release 300 ms").
    Why: 1.6 s still read as the bed "coming back" at each sentence break.
    HF: packages/core/src/audioCarve.ts:512-527
15. **Source already has music.** Onset regularity ≥ 0.35 on speechless stretches (peak autocorrelation of a 10 ms spectral-flux curve, 0.3-1.5 s lags): bed 6 dB lower (ours), logged; no bed only on request. Refines ref 01 §6 (old: "It rises to about -20 dBFS short-term").
    HF: packages/core/src/audioAnalysis.ts:536-552, :587, :600-617

#### Not adopted
- HF duck defaults 0.25 (-12 dB), 0.15 s attack, 0.4 s release (packages/cli/src/media-use/lib/duck.mjs:36-39; skills/media-use/scripts/audio-duck.mjs:13-16): Ref 01 §6 wins on style: about 10 dB down, attack 20 ms, release 300 ms. HF's own mixing.md:68 ('about 0.3-0.4') brackets our 0.316. **Transcript duck lane** takes only HF's mechanism.
- Level-match duck as the default: headroom 6 + 12s dB, max duck 24s dB; carve.mjs default s = 0.8 gives 15.6 dB and 19.2 dB (packages/core/src/audioCarve.ts:245-264, :672-727): Ref 01 §6 fixes a duck of about 10 dB. The per-span margin in **Audio gates** catches a bed that still fights the voice.
- 2.4 s bed release as the default (packages/core/src/audioCarve.ts:512-527): Ref 01 §6 'release 300 ms' wins. Kept as Optional **Calm release**, on request.
- Bed fade-in 0.4 s and fade-out 1.5 s (skills/hyperframes/references/film.md:32); 'end on a bar line with a short fade under the end card' (skills/hyperframes/references/sound.md:20); fades after trimming (skills/media-use/audio/references/bgm.md:36): Ref 01 §2 'The music bed is at full level from frame 0' and the Defaults Ending row (clean hard cut) win. Only 5 ms de-click ramps are kept.
- SFX at volume ~0.35 under voice and bed (skills/media-use/audio/references/sfx.md:44); hits 3-6 dB over the bed (sound.md:37): Ref 01 §6 'SFX peaks reach about -11 dBFS' wins.
- 'Rotate two or three takes of a repeated sound' (skills/hyperframes/references/sound.md:38): Ref 01 §5 and the Defaults SFX row are stricter: never reuse a sample within a clip.
- Skip a missing SFX, never block the render (skills/media-use/audio/references/sfx.md:32, :45): The Defaults SFX row requires one distinct SFX per accent. **Distinct-variant library** fetches a new file or reports the breach.
- Broadcast voice preset for 'shouty streams' (packages/core/src/audioFxPresets.ts:110-128): HF describes it as 'denser and more forward: a radio-presenter sound', not a fix for shouting, and the trigger was never measured. Clean Voice is the one default chain. The ffmpeg translation of Broadcast parses on 7.1 if a request asks for it.
- -16 LUFS default target (packages/studio-server/src/helpers/loudness.ts:503); 'mix around -16 to -14 LUFS for social' (sound.md:43): Ref 01 §6 sets -14 LUFS, gated at -14 ±1 LU.
- Bed under a voice at ~0.14 volume (sound.md:43), BGM_BED_VOLUME 0.12 ≈ -18 dB (skills/media-use/audio/references/bgm.md:34), about -31 LUFS under TTS (skills/media-use/audio/references/tts.md:21): Ref 01 §6 wins: bed at -20 in gaps, ducked about 10 dB, so about 16 dB under -14 LUFS dialogue (16.1-16.4 dB measured). That margin sits inside HF's own range.
- Baked sidechaincompress=threshold=0.03:ratio=8:attack=200:release=400 (skills/media-use/references/operations.md:177-181): Its 200 ms attack contradicts ref 01 §6 'attack 20 ms', and a reactive key lets the first syllable through. **Transcript duck lane** replaces it.
- Duck ramp starting at the span start (packages/cli/src/media-use/lib/duck.mjs:43-48, :65-69): Technical: each phrase's first 150 ms plays over a bed that is still falling. Our 20 ms ramp ends at the span start instead.
- Steepest-rise anchor for slow whooshes (docs/packages/cli.mdx:764-766): Technical: on noise whooshes the steepest 4 ms-RMS frame is jitter (0.380 s here, 13 ms before the peak, while the envelope's steepest rise was at 0.200 s). An early anchor also puts the swell after a 2-6 frame whip. The peak anchor follows sound.md:36 and manifest.json:85.
- Clean Voice's own -1 dB limiter inside the dialogue chain (packages/core/src/audioFxPresets.ts:107): Technical: the static gain after the chain would overrun it. One master limiter runs last (packages/core/src/audioLeveller.ts:201-210).
- Refusing (reference match) or capping (absolute target) gains beyond +12 dB (packages/studio-server/src/helpers/loudness.ts:395-401, :523-545): Ref 01 §6 wants dialogue at about -14 LUFS whatever the source level, so **Dialogue chain, static gains** warns instead.
- A 100 ms-window voice-over-bed gate: >= 10 dB in >= 95% of speech windows (a reader proposal built on audioCarve.ts windowing): It fails a mix built exactly to ref 01 §6: syllable troughs gave p05 2.4-6.9 dB, and only 45-77% of windows reached 10 dB, while per-span margins were 16.1-16.4 dB.
- Pitch-preserving speed changes: atempo chains and 0.25 s rate slices (packages/engine/src/services/audioMixer.ts:111-162), bullet and slow-mo presets (packages/core/src/speedRamp.ts:166-172, :225-230): Ref 01 §5 'Never use: ... slow motion, speed ramps'. Over-length clips follow ref 02 rule 5.

<!-- G4 = ref 03 §4 | verified (major_rewrite) -->
> **ref 03 §4: verified**

## Encode and mux: exact lengths, BT.709 tags, delivery settings
Scope: intermediates, final encode, audio length, mux and its gate, Windows ffmpeg; tested on ffmpeg 7.1.

### Adopted (default)
1. **Picture is the clock.** The render's N frames set every length (frame times → ref 03 §2 **Frame grid**).
   - Audio = round(N·SR/fps) samples (SR 48000; 60 fps: 800/frame): zero-pad or trim the float mix in numpy before the AAC. Event ends clamp to frame N. Never `-shortest`.
   Why: a mix 12.6 ms short made `-shortest` cut 150 frames to 149 (`-bf 0`) or 148 (B-frames); a 22.9 ms long one: 2.496 s of audio.
   HF: packages/producer/src/services/render/audioPadTrim.ts:11-14,47,299; skills/reverse-any-video/SKILL.md:18
2. **One AAC encode, copied at the mux.** Fit → AAC → true peak (→ ref 03 §3 **True peak after AAC**) → mux.
   - `ffmpeg -i mix_T.wav -c:a aac -b:a 192k -ar 48000 audio.m4a`
   - `ffmpeg -i video.mp4 -i audio.m4a -map 0:v:0 -map 1:a:0 -c copy -r <fps> -map_metadata -1 -movflags +faststart out.mp4`
   - Never a raw `.aac`, an AAC re-encode at the mux, or `-avoid_negative_ts make_zero`.
   Refines SKILL path A Render (old: "ffmpeg-mux the mixed audio with `-c:v copy` (no second video encode) and verify duration").
   Why: copied `.m4a`: in sync, audio edit 2.500 s. Raw `.aac`: 21.33 ms late. `make_zero`: empty 21 ms video edit (HF: black first frame). Re-encoded `audio.m4a`: 2.517 s. Cuts inherit the source title and URL.
   HF: packages/engine/src/services/audioMixer.ts:79-81; packages/engine/src/services/chunkEncoder.ts:892-924
3. **BT.709 tags (fallback).**
   - `setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv` on the footage before `ass` and `overlay`: they convert RGB by that tag (untagged = BT.601). Overlays stay RGBA.
   - Encoder: `-x264-params colorprim=bt709:transfer=bt709:colormatrix=bt709 -colorspace bt709 -color_primaries bt709 -color_trc bt709 -color_range tv`.
   - Matrix naming elsewhere → ref 04 §3 **Name matrix and range at every hop**.
   Why: untagged: #2BFF2B 33 off, #FF2BD6 30, #FF1A1A 22; tagged ≤ 1. On 7.1 `setparams` writes VUI + `colr`, x264 params the VUI only, the flags neither.
   HF: packages/engine/src/utils/sdrCaptureColor.ts:1-5; packages/engine/src/services/chunkEncoder.ts:419-423,474-511
4. **EffectCraft colour.** Once per EC version, decode an EC render of a ref 01 palette card as 709/601 × tv/pc: the decode within 4 code values is what EC wrote (right ≤ 1, wrong ≥ 17).
   - Tags match: copy as is.
   - Else re-tag at the copy-mux: `-bsf:v h264_metadata=colour_primaries=1:transfer_characteristics=1:matrix_coefficients=1:video_full_range_flag=0` (VUI) plus the `-color_*` flags (`colr`). BT.601: `matrix_coefficients=6`, `-colorspace smpte170m`; full range: `video_full_range_flag=1`, `-color_range pc`.
   Why: ffmpeg decodes untagged as BT.601 (card 34 off), Chrome reads ≥ 720-line H.264 as BT.709. On a copy the bsf alone writes no `colr`, the flags no VUI; both: 1/1/1/0, PSNR inf.
   HF: packages/engine/src/services/videoFrameExtractor.ts:971-979
5. **Delivery encode (fallback).** `-c:v libx264 -preset medium -crf 16 -bf 0 -pix_fmt yuv420p -r <fps> -an` plus **BT.709 tags**; audio joins at the mux. Image-sequence or pipe input: `-xerror`.
   Refines ref 01 §1 and SKILL path B (old: "h264 CRF 18 or lower" / "h264 CRF <= 18").
   Why: medium CRF 16 is HF's default `looks` tier ("visually lossless at 1080p"). `-bf 0`: video edit media_time 0, not 512 (2 frames). No `-xerror`: a corrupt PNG exited 0 with 59 of 60 frames.
   HF: packages/engine/src/services/chunkEncoder.ts:57,311-312,389-404; packages/cli/src/commands/render/plan.ts:46; docs/guides/rendering.mdx:262
6. **Seekable mezzanine.** Intermediates (clip copies, cut segments, plates, EC footage): `.mov`, `-an -c:v libx264 -preset veryfast -crf 12 -pix_fmt yuv420p -fps_mode cfr -force_key_frames "expr:gte(t,n_forced)"`.
   - Cuts add `-ss T(ki) -i <src> -t T(n) -frames:v n` (→ ref 03 §2 **Frame grid**, ref 03 §1 **Normalise in every clip intermediate**), then assert n frames. Audio → ref 03 §2 **Dialogue stem**.
   - Never .mkv/.webm or `-c copy` cuts.
   Refines SKILL path A (old: "near-lossless intermediate (keep 60 fps)").
   Why: x264 default: keyframes 4.17 s apart; forced: 1.000 s. A .mkv cut had 91/137 frames off the 60 fps grid, .mov 0. Without `-pix_fmt` a 4:2:2 10-bit source stayed yuv422p10le.
   HF: skills/media-use/scripts/transcript-cut.mjs:101-103,201-209
7. **Mux gate.** On the muxed file before delivery, by a stdlib box walk. Frames, ≤ 59.5 s, decode errors, black → ref 05 §1 **Stage, validate, promote**, **Black, frozen, frame 0**.
   - `moov` before `mdat`; 1 video + 1 `mp4a` 48 kHz stereo track; global tags only major_brand, minor_version, compatible_brands, encoder (+ title).
   - Video: one `stts` entry (60 fps: 256 at 1/15360); no empty edit (`elst` media_time −1); first decoded pts 0.
   - Audio: `elst` media_time > 0 (1024 = priming); |edit duration − N/fps| ≤ 1 ms, never the decoded count (end padding: 120832 for 120000).
   - `colr` nclx and VUI (`-bsf:v trace_headers`): 1/1/1, range 0, or the card's values.
   Refines ref 01 QC checklist (old: "audio present").
   Why: each tested defect (`-shortest`, raw `.aac`, `make_zero`, mux re-encode, untagged, inherited tags) fails one check.
   HF: skills/hyperframes-cli/SKILL.md:35; packages/producer/tests/audio-mux-parity/meta.json:3
8. **Windows-safe ffmpeg.**
   - `cwd=<job dir>` and bare relative names in filters (`ass=captions/01.ass:fontsdir=fonts`); an unescaped `C:/…` path failed to parse.
   - Per-frame values in a `sendcmd=f=<file>`; graphs over 8 KB (ours) via `-filter_complex_script <file>` (else `-/filter_complex`). Command lines cap at 32,767 chars (36,510: WinError 206).
   - Concat: a new `concat-<pid>-<n>.txt` beside the parts, bare `file 'part_01.mp4'` lines; absolute paths need `-safe 0` and `'` → `'\''`. Frames == sum of parts.
   - `-progress pipe:1 -nostats`: kill only after 180 s without `out_time_us` growth. Temp names → ref 05 §2 **Crash-safe writes**.
   - Exit 3221225781/3221225595/3221225794 = broken build: reinstall.
   Why: HF: a reused list silently gives a wrong video; a stall = a hung encode.
   HF: packages/engine/src/services/audioMixer.ts:964-974; packages/engine/src/services/chunkEncoder.ts:679-692; packages/engine/src/utils/runFfmpeg.ts:85-106; packages/studio-server/src/helpers/proxyTranscoder.ts:62-68

### Optional
- **Drafts.** `-preset ultrafast -crf 28` while iterating; never delivered.
  HF: packages/engine/src/services/chunkEncoder.ts:56

#### Not adopted
- Atmosphere opacity floor of 15-25% for low-opacity layers (skills/hyperframes/references/look.md:52): Design guidance for drawn atmosphere layers. Ref 01 §7 sets the bloom at 12-18% (screen blend), and the grade gate measures the result.
- Avoid full-screen linear gradients on dark grounds (skills/hyperframes/references/look.md:51): This is guidance for drawn backgrounds. Ref 01 §1 clips are full-bleed footage with no gradient backgrounds.
- aq-mode=3:aq-strength=0.8 (plus deblock=1,1) on every non-ultrafast encode (packages/engine/src/services/chunkEncoder.ts:406-407,427-434), and the earlier Optional 'aq-mode 3 at CRF >= 20': No consistent banding gain in synthetic dark-vignette tests with HF's params. Flat 8x8 share went 0.104 -> 0.129 (CRF 16) and 0.192 -> 0.208 (CRF 20) on a grey vignette with grain, and 0.994 -> 0.999 on an all-dark one. The earlier 89% -> 74% at CRF 20 did not reproduce. deblock=1,1 lowered Laplacian variance 767 -> 758 on a grainy frame, and ref 01 §7 gates sharpness.
- -video_track_timescale 90000 (packages/engine/src/services/chunkEncoder.ts:548-549): Not needed. ffmpeg's default MP4 timescale was 15360 at 60 fps (256 per frame) and 30000 at 30000/1001 (1001 per frame), both exact. The mux gate reads stts.
- Even-dimension pad pad=ceil(iw/2)*2:ceil(ih/2)*2 (packages/engine/src/utils/evenDimensions.ts:19-23): Canvases are fixed even sizes (1080x1440, or 1080x1920 on request), and crops are scaled to them.
- Locked closed GOP for chunk concat: -g/-keyint_min/-sc_threshold 0 plus scenecut=0:open-gop=0:repeat-headers=1 (packages/engine/src/services/chunkEncoder.ts:216-243): This is needed for chunks cut from one stream or for HLS. EffectCraft parts are independent encodes. A -c copy concat of 3 independent libx264 parts (B-frames on and off) gave 225 frames = sum of parts, one stts entry, 0 off-grid and first pts 0. The frames == sum check covers this case.
- PSNR floor of 32 dB (packages/engine/src/utils/psnr.ts:37-40) as proof of an untouched mux: A stream-copy mux must be picture-identical. Render vs final PSNR was inf, also after an h264_metadata re-tag, so 32 dB would pass a re-encode. Ref 05 §1 keeps 32 dB for regression re-renders only.
- Render provenance metadata tags (docs/guides/rendering.mdx:217-238): We strip all global metadata with -map_metadata -1, because cuts inherit the source title and URL, and set at most a clip title.
- -avoid_negative_ts make_zero on video-only encodes (packages/engine/src/services/chunkEncoder.ts:556): Unnecessary with -bf 0 (DTS = PTS from 0, tested). The mux gate rejects any empty edit.
- Pad/trim after the AAC encode by decoding and re-encoding it (packages/producer/src/services/render/audioPadTrim.ts:16-19,171-185): We fit the float mix to N frames before the single AAC encode, so there is no second AAC generation. Only ref 03 §3's true-peak correction re-encodes, and it starts from the PCM.

<!-- G5 = ref 04 §1 | verified (major_rewrite) -->
> **ref 04 §1: verified**

## Captions: timing contract, layout and legibility gates
Scope: frame-exact, machine-checked ref 01 §3 captions in both editors.

### Adopted (default)
1. **Token timing contract.** Refines ref 01 §3 Text cleanup (old: "fix whisper errors", no timing).
   - Step-5 cleanup, over clip word ids: `{"tokens":[{"d":"GONNA","src":["w813","w814"],"sp":"going to"}],"drop":["w812"]}`.
   - 0 errors before render: ids strictly increasing, each used once; src ∪ drop = all clip words (drop = fillers, stutters, self-corrections); asterisk tokens have no src.
   - norm(sp or d) matches norm(joined src texts): lowercase `[a-z0-9]`; equal, prefix, or Levenshtein ≤ max(1, ⌊min len/3⌋), else MISMATCH. start = src[0].start, end = src[-1].end.
   Why: rewrites ($100K, F**K) lose their times; without `sp` each failed.
   HF: .agents/skills/changelog-video/scripts/align-captions.mjs:11-15,39-58,123-127; .agents/skills/captions-overlay/SKILL.md:26
2. **ASS frame times.** k(t) = ⌊(t + 0.0005)·fps + 1e-6⌋ (→ ref 03 §2 **Frame grid**).
   - appear_f (a) = max(0, k(word.start) − 1); end_f = min(k(last.end + 0.6), next start_f); the last chunk ends at N.
   - Start = first frame on, End = first frame off, in floored centiseconds `cs = 100*k*den//num` (fps = num/den; H:MM:SS.cc).
   - ass keys on PTS: the burn input's first `pts_time` (showinfo) is 0; fix the cut, not `setpts` there.
   Why: floored cs exact at 23.976-60 fps; nearest: 8/24 starts a frame late at 30/60.
   HF: skills/reverse-any-video/SKILL.md:19; packages/cli/src/measure/media.ts:339-341
3. **Event mechanics.** Refines SKILL path B and ref 01 Editing tool (old: "`\fad`/`\t` for the 3-frame fade", "per-word `\fad`/`\blur`/`\fscx` tags") and ref 01 §3 Reveal (old: "opacity 0 to 100%, scale 90 to 100%, blur 6 to 0 px").
   - Per word one event per Layer (0 shadow, 1 glow, 2 fill), each `\an5\pos` at the word centre (cy = baseline − 0.304·`\fs`): unpositioned overlaps restack, `\an7` scales from the corner (12-14 px slide).
   - End = chunk end_f (hard kill; EffectCraft: out-point, full-canvas precomps).
   - Sole opacity owner: the entrance from 1/3, `\alpha&HAA&\fscx93\fscy93\blur4\t(0,T,\alpha&H00&\fscx100\fscy100\blur0)`, T = round(2000/fps) ms: alpha 33/67/100% on a..a+2 (`\fad`: 0-12% on a).
   Why: stacked, sliding, stuck, late words.
   HF: skills/hyperframes/references/captions.md:21,34,36-37; packages/lint/src/rules/captions.ts:26-36
4. **Size and stroke.** Refines ref 01 §3 Size for ASS (old: "At 1440: about 68 px").
   - `\fs` = em × (usWinAscent + usWinDescent)/unitsPerEm: Montserrat Black ×1.379 (68 px em = `\fs93.8`, 90 px = `\fs124.1`).
   - `\bord` = 0.04 × em (outside, under the fill); EffectCraft (centred stroke): Fill Over Stroke 0.08 × em (check one frame).
   - Gate: cap height 3.3% H ±1 px (47 px at 1440, 63 at 1920).
   Why: `\fs68` gave a 35 px cap (2.4% H) vs Pillow's 48.
   HF: registry/components/caption-emoji-pop/caption-emoji-pop.html:106-107
5. **Measured-fit chunks.** Refines ref 01 §3 Size (old: "cap height 3.3% H", "Max line width 80% W. Max 2 lines").
   - Line width = Pillow `getlength(line)` at the em × 1.02 (ASS) or × 1.14 (EffectCraft, unmeasured) + 2·`\bord`; lines ≤ 0.80 W, ≤ 2, split at argmin |w1 − w2|.
   - A word that breaks the fit starts the next chunk (never shrink), still with the punctuation/0.25 s flush. A lone word > 0.80 W may scale to ≥ 0.85×.
   Why: libass ink = 0.99-1.01 × (getlength + 2·`\bord`).
   HF: registry/components/caption-neon-accent/caption-neon-accent.html:139,295-299,311-373
6. **Keyword guard.** One-word keywords stay white if in: the a an and or but is are was were to of in on at for with by from as it its this that these those be been have has had do does did will would could should may might must can if then so just up out about. Digit/$/% tokens default to cyan. No randomness.
   Why: coloured "THE" is noise; NO/NOT/YES stay free for red.
   HF: registry/components/caption-neon-accent/caption-neon-accent.html:142-199,284-285
7. **Face avoidance per window.** Refines ref 01 §3 Position (old: "intersects the tracked face box (eyes to chin), move the block to y = 72% H").
   - Block box = caption-only render on #808080, max|px − 128| > 24 (+ shadow, glow; ass writes no alpha).
   - Low (72% H) when it meets the union of face boxes (eyes to chin, +5%) over [start_f, end_f); after a low chunk, return to 50% at the first of 2 clear chunks; cuts reset.
   - QC: 0 frames over a face.
   Why: heads move mid-chunk; per-chunk flips flicker.
   HF: skills/hyperframes/references/captions.md:45; docs/guides/captions-and-recuts.mdx:125-127
8. **9:16 UI band.** Refines ref 01 §3 Position on 9:16 (old: "move the block to y = 72% H"): on 1080×1920 caption, label and sticker boxes stay in y 168-1330 px; low = block bottom at 1330 (72% H is 1382); clear the right action rail (no width).
   Why: app UI covers y < 168 and > 1330 px.
   HF: skills/hyperframes/references/types/vertical.md:7
9. **Burned-in text scan.** Refines ref 01 §1 (old: stream overlays kept "only if cropping them out would cut the subject").
   - Pre-reframe: `ffmpeg -ss S -to E -i src.mp4 -vf "fps=1,scale=360:-1,tile=6xK" -frames:v 1 sheet.png`, K = ⌈(E − S)/6⌉ (6x10 drops > 60 s).
   - Crop out subtitles, lower thirds, chat, tickers; else keep clear.
   Why: source subtitles can start mid-clip.
   HF: skills/hyperframes/references/captions.md:39
10. **Presence, stale and sync gate (hard fail).** Refines ref 01 QC (old: "Captions sit within ±2 frames of the whisper word starts").
   - R = same editor's fill-only render (no entrance) on #808080 at end_f − 1; P = caption-free graded render (→ ref 04 §3 **Gate footage only, paired by index**).
   - Half size: word mask = |R − 128| > 64, eroded 1 px, minus pixels where P is within RGB 45 of R (< 25% left: skip); match = share within RGB 45 of R; skip accent spans.
   - Presence: every word ≥ 0.8 at chunk midpoints + ≥ 6 speech frames. Stale: ≤ 0.2 on end_f..end_f+2 (minus the next chunk's mask).
   - Sync: the match ≥ 0.5 run reaching min(full_f + 8, end_f − 1) starts at full_f = appear_f + 2, ±1.
   - Font: each `fontselect: (<family>, …) -> X` (info log) names that family (a typo gave `ArialMT`).
   Why: deleted 0.00, held 1.00, +4 shift lag 3-4; without P, a bright plate read 0.35.
   HF: .agents/skills/changelog-video/SKILL.md:162-167; packages/cli/src/measure/drawn.ts:9-14
11. **Legibility gate.** Refines ref 01 §3 (old: shadow "at 55% opacity").
   - At each word's full frame, render the shadow layer alone on the graded plate (glow, stroke = glyph paint).
   - Sample the word box inset 1 px on a ⌊w/12⌋ × ⌊h/6⌋ px grid; bg = per-channel median; pass max(WCAG fill, black stroke) ≥ 3.0.
   - Fail → other ref 01 position if face-clear, else that chunk's shadow 75%; never a box.
   Why: red over grey 130-170 read 2.0-2.9 at 55%, 3.3-4.2 at 75%.
   HF: packages/cli/src/commands/contrast-sample.ts:3-8,38-62; packages/cli/src/commands/contrast-audit.browser.js:600-636
12. **Non-speech text floors.** Refines ref 01 §2 (old: "add one asterisk line ... for ≤ 1.5 s").
   - Asterisk lines, context line, labels: fully typed ≥ 0.4 s (≤ 2 words) or ≥ 0.75·(0.5 + 0.3·n) s; font ≥ 2.6% of the short side (28 px).
   - Context line ≤ 3 words, typed in ≤ 0.45 s (+1.05 s = 1.5 s).
   Why: typed lines vanish unread.
   HF: packages/cli/src/utils/craftAudit.ts:5-21,447-450

### Optional
- **Speech-rate chunk cap.** Refines ref 01 §3 Chunking (old: "2-4 words per chunk (max 6)"): 3 words at ≥ 3.3 words/voiced s, 4 at 2.3-3.3, 5 below (bands ours).
   Why: 2-word flips on slow speech read choppy.
   HF: skills/hyperframes/references/captions.md:19

#### Not adopted
- Karaoke active-word highlight as the baseline at every energy level (skills/media-use/audio/references/captions/motion.md:15) and grey-to-ink per-word recolour (registry/components/caption-pill-karaoke/caption-pill-karaoke.html:148-151): Ref 01 §3 Reveal: 'No bounce and no karaoke recolour'. It is also on ref 02's NOT ADOPTED list.
- Mandatory audio-reactive caption scale/glow over music (skills/media-use/audio/references/captions/motion.md:21-23): Ref 01 §3 Reveal (3-frame entrance, 'No bounce') and §5 'Never use: beat shake, per-word zoom punches'.
- Highlight styles cycled every 2-4 groups (skills/media-use/audio/references/captions/motion.md:9-13,77) and overshoot/bounce on emotional keywords (skills/media-use/audio/references/captions/authoring.md:41): Ref 01 §3 specifies one caption look and 'No bounce'. HF's own catalog asks for one identity per composition (docs/prompting/captions-catalog.mdx:92).
- Seeded-random accent colour on 40-45% of non-function words, and accent words at 1.2x size (registry/components/caption-neon-accent/caption-neon-accent.html:286-299,447-448; registry/components/caption-emoji-pop/caption-emoji-pop.html:270-274): Ref 01 §3 Colour: 1-3 semantic keywords per chunk, chosen by meaning. Size is fixed by the cap height.
- Text-sized 30-40% scrim over footage brighter than 60, and blend mode chosen by backdrop brightness (skills/hyperframes/references/captions.md:38): Ref 01 §3 says 'no background box'. Contrast fixes stay inside the look (→ ref 04 §1 **Legibility gate**).
- Contrast fix that steps the fill colour toward white or black (suggestedColor; skills/hyperframes-cli/references/lint-validate-inspect.md:88; packages/cli/src/commands/contrast-bg.ts:47-50): Ref 01 §3 palette colours carry meaning. We move the block or deepen that chunk's shadow instead (→ ref 04 §1 **Legibility gate**).
- First caption 0.1-0.3 s in, because one at 0 s 'looks pre-existing' (skills/hyperframes/references/captions.md:20): Ref 01 §2 puts the first caption on screen by t ≤ 0.1 s. Ref 02 starts the clip 0.05 s before the hook word, so word 1 appears at frame 2 (60 fps).
- Final caption clears before the video ends; the last line holds ≥ 2 s (docs/guides/captions-and-recuts.mdx:135; skills/hyperframes/references/motion.md:22; packages/cli/src/utils/craftAudit.ts:17): SKILL Defaults 'Ending' and ref 01 §5: hard cut right after the payoff, with the payoff chunk still on screen (ref 02: end = last word + 0.15 s).
- Exit tweens (fade or blur-out 0.12-0.25 s, exits 40-50% shorter than entrances) and group end = last word + 0.5 s, 0.05 s before the next group (skills/hyperframes/references/captions.md:24; skills/hyperframes/references/motion.md:12,22; registry/components/caption-highlight/caption-highlight.html:183): Ref 01 §3: 'The exit is a hard cut'. A chunk holds until the next one starts, or 0.6 s after its last word.
- Portrait captions about 600-700 px from the bottom; burned-in captions at the bottom of the UI band (skills/hyperframes/references/captions.md:35; skills/hyperframes/references/types/vertical.md:7): Ref 01 §3 Position: 50% H, or 72% H when off the face. Only the 168-1330 px band is adopted (→ ref 04 §1 **9:16 UI band**).
- Group sizes of 3-5 / 4-6 words and pause breaks at 0.10-0.15 s (skills/hyperframes/references/captions.md:19; registry/components/caption-neon-accent/caption-neon-accent.html:135): Ref 01 §3 Chunking: 2-4 words (max 6), breaks at gaps > 0.25 s. HF's tiers survive only as the Optional speech-rate cap.
- Shrink-to-fit font loops: neon-accent fitFontSize 88 → 62 px in 2 px steps (floor 0.45x base); runtime fitTextFontSize 78 → 42 px (registry/components/caption-neon-accent/caption-neon-accent.html:235-244,382-385; skills/hyperframes/references/captions.md:32): Ref 01 §3 fixes cap height at 3.3% H. Re-chunk instead, as HF's own types/vertical.md:18 says ('cut words, never shrink'). Only a lone over-wide word scales, floor 0.85x.
- Entrance that completes on the spoken word: lead = min(7/30 s, gap to the previous group), plus a 0.05 s colour-fade lead (registry/components/caption-neon-accent/caption-neon-accent.html:466-471; registry/components/caption-pill-karaoke/caption-pill-karaoke.html:151): Ref 01 §3 Reveal measured each word appearing at word.start − 0-2 frames. A 7/30 s lead is up to 14 frames at 60 fps.
- Layered same-colour glow (4/10/20/40 px at 1.0/0.9/0.7/0.4) plus dark drop shadows 0 8px 16px and 0 16px 40px (registry/components/caption-neon-accent/caption-neon-accent.html:396-427): Ref 01 §3 specifies one same-colour glow (about 20 px, about 70%) and a soft black shadow at offset 0.
- Matted 'embed' words set behind the speaker (.agents/skills/captions-overlay/SKILL.md:20-32; skills/hyperframes/references/captions.md:41-45): Not part of ref 01's measured style (captions sit in front). It also needs a matting model outside requirements.txt.
- Caption presence and timing from caption-band frame differences (default threshold 5 grey levels, plain |edited − raw|) as a gate on our renders (skills/reverse-any-video/references/match.md:8; packages/cli/src/measure/events.ts:229): Built for third-party references; ref 05 §1 keeps it for reference studies. On our renders, a +10% luma grade alone moved |graded − raw| 7-18 levels in caption-free boxes (test). An affine ring fit separated presence (49-60 vs 1.0-1.2) but not a held chunk under the next chunk's box (45.0 vs 48.9). → ref 04 §1 **Presence, stale and sync gate**.

<!-- G6 = ref 04 §2 | verified (major_rewrite) -->
> **ref 04 §2: verified**

## Cut detection, reframe and accents
Scope: cuts, the crop across them, and frame-exact flashes, whips and pushes.

### Adopted (default)
1. **Classified cut detector.** Refines SKILL step 4 (old: "ffmpeg `scene` > 0.3") and ref 02 rule 13 (old: "histogram difference over 0.35").
   - Read the ref 03 §1 **Normalise in every clip intermediate** file (CFR, rate R) or `edited/NN.mp4`: `ffmpeg -nostdin -v error -ss A -i in -t D -an -vf scale=64:36:flags=area,format=gray -f rawvideo -` (A, D: ref 03 §2 **Frame grid**). Frame i = ceil(A·R − 1e-6) + i.
   - d[i] = mean |F[i] − F[i−1]|, d[0] = 0. typical = max(1, sorted[n//2]) of the d ≥ 0.5 among ±N neighbours (from i = 1); 1 if fewer than 4.
   - Hard hit: d ≥ 12 and ≥ 4×typical. Soft hit (same-angle punch-in): d ≥ 10, ≥ 8×typical, ≥ 4× the largest neighbour.
   - Consecutive hits merge (max change; soft only if all are). > M frames = `fast`; picture back within K frames (MAD < 0.4×change) = `flash`; the rest are cuts.
   - N, M, K = 12, 3, 4 × r, r = max(1, round(R/30)) (ours).
   - Reframe: detect on [start − 0.5 s, end + 0.5 s] (a window's first frame has no d); reset and snap at cuts and at every splice, never at `flash`/`fast`.
   - Renders: → ref 05 §1 **Events match the plan**.
   - Why: `scene>0.3` split a flash into 2 cuts and missed 20% punch-ins (port: d ≥ 19.6); the histogram tool logged 172 "cuts" on ref 1 (~27 real). At 60 fps, r = 1 read a 55% tint as a cut; r = 2 read `flash`.
   - HF: packages/cli/src/measure/cuts.ts:7-19,37-90; packages/cli/src/commands/measure/cuts.ts:31-36
2. **Accent timing.** Refines ref 01 §5 tint flash (old: "1-frame attack, 0.25-0.4 s decay", no curve).
   - Accents are output frame indices. Cause frame = the cut, the visible impact, or the frame showing word.start (ref 03 §2 **Frame grid**).
   - Flash, tint, wash: full peak ON the cause frame, then peak·(1 − u)² over ref 01's length (tint 0.25-0.4 s, red wash 0.5 s).
   - Whip: the switch frame (i = n//2, first p ≥ 0.5) is the cut frame. Stickers: 0-45 ms after their cause (0-2 frames at 60 fps).
   - ≥ 1 s between any two flash, tint or wash accents.
   - Speech and picture are the clock, never a beat. SFX: → ref 03 §3 **SFX on the hit**.
   - Why: an eased or late hit reads as lag.
   - HF: .agents/skills/motion-doctrine/SKILL.md:88; skills/hyperframes/references/film.md:34; skills/hyperframes/references/sound.md:14; skills/media-use/references/media-treatment-recipes.md:925-926
3. **White flash = wash + exposure push.** Refines ref 01 §5 White flash (old: "1-2 frames of overexposure (luma > 230), decaying over 0.3-0.4 s").
   - Cause frame and the next: (255,253,250) wash at 0.92 over the pushed picture, then 0.92·(1 − u)³ over 0.18 s.
   - Push: min(1, x·2^EV), x in 0-1, EV = EV0·(1 − u)² over 0.35 s. EV0 = 0.72, lowered per shot until the third frame reads luma ≤ 230 (ref 01: 1-2 frames); at shot luma ≥ 180 use 0.
   - Tested at EV0 0.72, frames > 230: 2 (black, testsrc2), 3 (mid grey), 5 (luma 160), 12 (209); passing needs EV0 ≤ 0.3 at 150, ≤ 0.08 at 170. Wash alone: 233 on black.
   - Why: a flat white layer lifts blacks; a push brightens the picture.
   - HF: skills/media-use/references/media-treatment-recipes.md:904-926; registry/blocks/editorial-flash-overlay/editorial-flash-overlay.html:23,101,114; packages/core/src/runtime/colorGrading.ts:1224
4. **Velocity-matched whip.** Refines ref 01 §5 whip (old: "2-6 frames (at 60 fps) of ... streak blur plus a ghost of the next shot").
   - n = 2-6 frames at 60 fps (1-3 at 30). Frame i: u = (i + 0.5)/n, p = inOutQuad(u).
   - A leaves by 1.5p·W, B arrives from 1.5(1 − p)·W (edge-replicate); out = (1 − p)A + pB (the ghost). Both move 1.5 W per unit p: speeds match.
   - Box blur on the travel axis only: length = round(⅔ · 0.75 W·(p(u + 1/n) − p(u − 1/n))), u clamped to 0-1 (240° shutter); 1080 W, n = 4: 152/371/371/152 px; n = 2-6: 68-480.
   - Consecutive whips keep one direction (default: content exits left) unless on-screen motion reverses.
   - Why: speed mismatch or ping-pong reads as an error; cross-axis blur smears faces.
   - HF: packages/shader-transitions/src/shaders/registry.ts:43-55; docs/guides/motion-blur.mdx:30; .agents/skills/motion-doctrine/SKILL.md:53,64-65
5. **Face carried across jump cuts.** Refines ref 02 rule 15 (old: "vary the crop scale by 4-10% between them", no anchor).
   - Anchor the scale change on the face: origin_B = face_B − p_A·crop_B/canvas (p_A: face centre on canvas at cut − 1), clamped to the source.
   - Gate: face-centre shift per axis ≤ 0.625% W (6.75 px at 1080 W) from cut − 1 to cut; if the clamp breaks it, keep ref 01 §4 framing.
   - Why: a jump that also moves the face makes eyes search.
   - HF: .agents/skills/motion-doctrine/SKILL.md:77-78; .agents/skills/motion-doctrine/scripts/seam-gate.mjs:43-44,263 (12 px at 1920)
6. **Push-ins on a parent; plate covers the canvas.**
   - Tracking keys stay on the footage layer; ref 01's 3-5% push and the freeze zoom go on a parent (Python: M_push∘M_track).
   - Face gate (SKILL step 4, bbox + 5%) on the composed transform at the ref 05 §1 **Frames by index** samples. Refines ref 02 rule 14 (old: "checked in QC on 1 fps samples").
   - A translated plate needs scale ≥ max_t(1 + 2|dx|/W, 1 + 2|dy|/H) × 1.02 (24 px at 1080 W: 1.0653).
   - FAIL if a 2-px border band of `raw/NN` (ungraded) is > 90% luma < 8 (bars, exposed edge). Graded frames false-fail (ref 01 grade + `vignette=PI/5`: clean RGB-24 shot, top/bottom bands 100% < 8).
   - Framing: → ref 05 §1 **Framing by shot medians**.
   - Why: a push or shift on the tracked layer cuts the face or shows a black edge.
   - HF: skills/hyperframes/references/motion.md:57; registry/components/camera-shake/camera-shake.html:690-730

### Optional
7. **Active speaker from lip motion** (2+ faces, no diarization). Refines ref 01 §4 (old: "the active speaker is chosen from mouth motion or diarization").
   - Per ≥ 2 s window and face: mouth ROI [x + 0.2w, y + 0.62h, 0.6w, 0.38h] of the median face box, grey, 160 px wide; motion = per-frame MAD; speech = |Δ per-frame RMS| (16 kHz).
   - Pearson r at lags −125..+45 ms (HF sync band). Speaker = top r if ≥ 0.3 and ≥ 0.1 over the next face (ours); else keep the last speaker or go wide.
   - Why: the crop follows the listener when two faces share a shot.
   - HF: packages/cli/src/measure/sync.ts:53-84,119-124; packages/cli/src/measure/person.ts:22-23,509-514
8. **Face detection fallbacks.**
   - Detect on a ≤ 960 px wide copy, min face 4% H. Drop faces inside pasted-in pictures (poster, photo; not a live facecam).
   - Frontal miss: profile detector (and its mirror, ours), then hold the last box ≤ 0.5 s (ours), then widen.
   - Models: YuNet needs its .onnx (no cv2 wheel ships one); cv2 5.0.0 has no `CascadeClassifier` or Haar XML. Preflight must report the model path.
   - Why: 3/4 angles drop out of frontal detectors; pictured faces steal the crop.
   - HF: packages/cli/src/measure/face.ts:14-17,102-123; packages/cli/src/measure/person.ts:467-474
9. **Meme-freeze timing** (only when it fits).
   - Push 2-4 frames (60 fps) into the hit, power3.in, radial blur: 12 taps along uv − 0.5, strength 0.08p.
   - Freeze (hard set): `trim=end_frame=<hit+1>,tpad=stop_mode=clone:stop_duration=1.5` (ref 01: 1.2-1.8 s); at most one flash.
   - 💀 enters 0.3 s after the hit, scale 1.18 → 1 over 0.24 s, power2.out.
   - Why: an eased freeze softens the hit; extra flashes strobe.
   - HF: registry/blocks/beat-freeze-cut/beat-freeze-cut.html:690-702,724-748; packages/shader-transitions/src/shaders/registry.ts:107-124; registry/blocks/freeze-frame-dressing/freeze-frame-dressing.html:99-104

#### Not adopted
- Flash rise of 0.035-0.055 s (skills/media-use/references/media-treatment-recipes.md:923): Ref 01 §5: tint '1-frame attack', white flash '1-2 frames of overexposure'; HF film.md:34 also makes a hit a 0 ms set.
- 'Never saturated red' flashes (media-treatment-recipes.md:925): Ref 01 §5 'Red fail wash: red-pink overlay at 65%, fading to 0 over 0.5 s'.
- A fixed +0.72 EV push start on every shot (media-treatment-recipes.md:916-917): At ref 01's graded luma 150-170 it held luma > 230 for 4-6 frames, against ref 01 §5's '1-2 frames of overexposure'. Item 3 lowers EV0 per shot.
- Recovery examples of 0.24-0.28 s (media-treatment-recipes.md:904-913; registry/blocks/beat-freeze-cut/beat-freeze-cut.html:746; registry/blocks/freeze-frame-dressing/freeze-frame-dressing.html:97): Shorter than ref 01 §5's white flash 'decaying over 0.3-0.4 s'. Item 3 uses 0.35 s, which is inside HF's own 0.24-0.38 s range (media-treatment-recipes.md:923-924).
- Outgoing pre-ramp (+0.82 EV, scale 1.035 over 0.12 s from cut − 0.16 s) and incoming scale 1.1 → 1 over 0.42 s (media-treatment-recipes.md:887-903): Ref 01 §5's white flash has no pre-roll, and the settle is a zoom inside a shot (ref 01 §4: 'no zoom changes inside a shot').
- Whip length 0.13-0.3 s (skills/hyperframes/references/motion.md:39) and the 0.55 s strip whip (registry/components/whip-pan-cut/whip-pan-cut.html:53): Ref 01 §5: whip '2-6 frames (at 60 fps)'.
- 'Never a crossfade' and the zero-overlap seam check (.agents/skills/motion-doctrine/SKILL.md:81; .agents/skills/motion-doctrine/scripts/seam-gate.mjs:453-468): Ref 01 §5's whip includes 'a ghost of the next shot'; item 4 mixes A and B by p.
- Whip blur caps: 16 px peak stdDeviation (whip-pan-cut.html:397-399), 15-20 px full-frame (motion.md:7), 18-20 px full-frame surface (.agents/skills/cut-the-curve/SKILL.md:48): These are sized for UI cards and text in 0.3-0.6 s moves ('readability ceiling', whip-pan-cut.html:397-398). A 2-6 frame footage whip travels 1.5 W, so item 4 sizes blur with HF's 240° shutter (docs/guides/motion-blur.mdx:30): 68-480 px at 1080 W.
- Dip cut: outgoing frame darkened ~40% for 3 frames before a hard cut (motion.md:41): Ref 01 §5: 'Every other cut is a hard cut'. Ref 02 rule 15's 4-10% scale change already marks same-camera jump cuts.
- Talking-head punch-ins on emphasis (skills/hyperframes/references/types/vertical.md:19), the 11% / 1.2 s power2.inOut camera move (registry/components/yt-camera-move/yt-camera-move.html:113-133) and one slow push 1.0 → 1.08 on calm footage (skills/hyperframes/references/film.md:35): Ref 01 §5 'Never use ... per-word zoom punches', ref 01 §4 'no zoom changes inside a shot', and ref 02's NOT ADOPTED punch-ins every 3-4 s. Only ref 01's 3-5% push on long holds stays (item 6).
- Beat-led cutting and beat-snapped accents: one clip per strong beat, 'cut on the beat' (skills/hyperframes/references/film.md:33-35; skills/hyperframes/references/motion.md:13): Clips are narrated, and HF sound.md:14 makes the voice the clock. Ref 01 §8 pacing follows speech, ref 01 §5 bans beat shake, and a beat tracker is outside requirements.txt.
- Stretch-cut connector after the freeze (scaleX 1.35, scaleY 0.92, blur 14 px, brightness 1.35; beat-freeze-cut.html:762-790), paper/tape dressing (freeze-frame-dressing.html:96-115) and the cinematic-zoom R/G/B split 1.06/1/0.94 (packages/shader-transitions/src/shaders/registry.ts:114-116): Ref 01 §5's meme freeze is '2-4 frame zoom/radial blur into a freeze', 'warm/sepia high-contrast meme grade', 'one 💀 PNG', 'hold for 1.2-1.8 s, then hard end'. Only the tape's entrance timing is reused, for the 💀 (item 9).
- Light-leak transition (registry/blocks/light-leak/light-leak.html:310) and two-sided flash-through-white (packages/shader-transitions/src/shaders/registry.ts:202-210): Not among ref 01 §5's accent types. Ref 01's white flash is overexposure on the hit frames (item 3), not a dip through white.
- Face-size bands (pass >= 0.25 H, fail < 0.06 H), 'subject = largest face' and the missing-face note on the last sampled frame (packages/cli/src/measure/face.ts:7-9,140-174): These grade a regenerated presenter's likeness (face.ts:1-3). Ref 01 §4 sets the close face at 24% H (20-30%) and tracks the active speaker; the ref 05 §1 framing gates cover the last shot.
- Roll, pitch and yaw terms of the camera-shake overscan solver (registry/components/camera-shake/camera-shake.html:718-727): Ref 01 §5 'Never use: beat shake', and no clip accent rotates the plate, so item 6 keeps only the translation term.
- Seam-gate 'moving at the boundary' check: exit or entry slower than 15 px/s fails (.agents/skills/motion-doctrine/scripts/seam-gate.mjs:40,423-427): Ref 01 §4 wants a locked camera ('Reframe with cuts, not fast pans'), so both sides of a hard cut are usually static. Only the carrier check is kept (item 5).

<!-- G7 = ref 04 §3 | verified (fixed) -->
> **ref 04 §3: verified**

## Grade and colour pipeline, grade gates
Scope: tagged BT.709 intermediate → graded footage, and the grade gate.

### Adopted (default)
1. **Grade and gate the footage only.**
   - Grade before captions and overlays (`[v]<grade>[g];[g]ass=...`); EffectCraft: in a canvas-size footage precomp (adjustment layer above the tracked source) under caption, sticker and flash layers.
   - Gate `raw/NN` vs `qc/NN_grade.mp4` (same chain, no ASS/overlays; path A: precomp rendered alone, untested), else `edited/NN` with caption/sticker boxes masked +8 px, accents ±0.5 s and the freeze skipped.
   - Samples t = i + 0.5 s (i < ⌊D⌋) per ref 05 §1 **Frames by index**, decoded with `scale=in_color_matrix=bt709:in_range=tv,format=bgr24`.
   - Refines ref 01 §7 QC gate (old: "sample 1 frame per second from source and output") and ref 01 Editing tool / SKILL path A (old: "grade on an adjustment layer").
   Why: captions alone gave sharpness x7.2 (luma, sat x1.00) on an ungraded clip.
   HF: docs/prompting/color-grading.mdx:10-11; packages/cli/src/media-use/lib/grade-analyzer.mjs:215-217
2. **One metric definition** for the gate and repo-only `analysis/tools/extract_ref.py`.
   - luma = mean HSV V, sat = median HSV S, on `cv2.resize(bgr, (90, 160))`.
   - gray resized to 720 px high (`INTER_AREA`): sharp = Laplacian variance (CV_64F), contrast = std, p2 = 2nd percentile.
   - ratio = out/src, 1 when both are under the floor (luma 1, contrast 1, sat 2.55).
   - Refines ref 01 §0.3 (old: "Laplacian variance (720p)", no method). Port it to extract_ref.py:44-45 (mean S, native Laplacian) and re-measure ref 01 (→ ref 05 §1 **Reference studies per frame**).
   Why: native vs 720 px Laplacian differed x6.8 on one soft frame (5.6 vs 38.2).
   HF: packages/cli/src/measure/look.ts:7,26-43; packages/cli/src/measure/media.ts:282-284
3. **Name the matrix at every RGB hop.** Input `raw/` is tagged BT.709 tv (→ ref 03 §1 **Normalise in every clip intermediate**).
   - YUV filters first (`lutyuv`, `eq`, `hqdn3d`, `unsharp`), then one RGB stage: `scale=in_color_matrix=bt709:in_range=tv,format=gbrp,<curves,vibrance,colorbalance,glow,vignette>,scale=out_color_matrix=bt709:out_range=tv,format=yuv420p`; tags per ref 03 §4 **BT.709 from the head of the graph**.
   - Path B Python frames: ffmpeg-decode with `scale=in_color_matrix=bt709:in_range=tv,format=bgr24`, never `cv2.VideoCapture`; encode piped frames with `scale=out_color_matrix=bt709:out_range=tv,format=yuv420p`.
   - Refines ref 01 §7 chain and SKILL path B (old: no matrix named).
   Why: card max |dRGB| as BT.709: ref 01's chain on untagged input 37 (encoded yuv444p); `-pix_fmt yuv420p` 40; explicit hops 4; cv2 decode 23, ffmpeg decode 4.
   HF: packages/engine/src/utils/sdrCaptureColor.ts:1-5
4. **HDR sources.** Grade and gate only the SDR copy → ref 03 §1 **SDR at download** and **HDR fallback**.
5. **Diagnose per camera group, correct, then one look.**
   - Per shot, median of 3 index-sampled frames of `format=yuv444p,signalstats,metadata=print:file=-` (YLOW/YHIGH = 10th/90th pct): dark YAVG < 71.4 and YHIGH < 165.75; high-key YAVG > 183.6 and YLOW > 76.5; flat (YHIGH − YLOW)/255 < 0.35; clip YLOW ≤ 16 or YHIGH ≥ 235.
   - Groups in shot order: join the first within |dU|, |dV| ≤ 4, |dY| ≤ 15 (initial); per-group values by `sendcmd` on `eq@g`, `lutyuv@c`, `curves@k`.
   - dark: gain to mean V 145-170 (night: Defaults +10% only). flat: steeper S until contrast ≥ x1.10.
   - Low headroom (> 3% of pixels at max(R,G,B) ≥ 228, which a x1.10 gain clips): no `eq` brightness or gain; RGB `curves=interp=pchip:all='0/0 0.5/M 1/1'`, M up from 0.62 until luma ≥ x1.10.
   - Then one look. Refines ref 01 §7 (old: one "Reference ffmpeg chain" for all).
   Why: bright source (16.6% at ≥ 228; YHIGH headroom 1.135 missed it): ref 01's eq luma x1.105, +16.6 pp clip; x1.10 gain x1.077, +16.6 pp; pchip M 0.62 x1.054, M 0.70 x1.104, +0.1 pp. Natural spline on a steep S: 255 at input 208.
   HF: packages/cli/src/media-use/lib/grade-analyzer.mjs:116-129,151-153; packages/core/src/colorGroups.ts:1-6
6. **Cast check on neutral pixels.**
   - Per group: pixels outside the face box x1.5 with HSV S < 0.30 and 0.2 < V < 0.9; skip under 5% of the frame.
   - BT.709 dU, dV of them: warmth = (dV − dU)/128, cast = dU + dV.
   - |warmth| ≥ 0.08 or |cast| ≥ 10: prepend `lutyuv=u='val+a':v='val+b'` (a = −dU/2, b = −dV/2) and drop ref 01's warm push; else keep it unless face hue ≥ 22°.
   - Refines ref 01 §7 (old: constant `colorbalance=rm=0.02:bm=-0.02`).
   Why: a 31% skin block put whole-frame warmth at +0.107 on grey (false) and +0.013 on a cool cast (neutrals −0.135); S < 0.15 kept no neutrals. Fix: −0.135 → −0.063.
   HF: packages/cli/src/media-use/lib/grade-analyzer.mjs:131-138; skills/media-use/references/media-treatment-recipes.md:138
7. **Threshold the glow, in RGB.** In the RGB stage (W:H = canvas): `split[a][b];[b]scale=iw/2:ih/2,lutrgb=r='val*gt(val,127)':g='val*gt(val,127)':b='val*gt(val,127)',gblur=sigma=10,scale=W:H[g];[a][g]blend=all_mode=screen:all_opacity=0.15`, then the vignette.
   - lutrgb thresholds per channel (HF: BT.601 luma); half-res sigma 10 ≈ ref 01's sigma 20.
   - EffectCraft: Glow threshold ~50% (unverified: on the card, 20-40% greys must stay +0).
   - Refines ref 01 §7 (old: whole-frame `gblur=sigma=20` screen, on YUV as written).
   Why: ref 01's glow moved neutral U/V 128→137 (magenta, even black); unthresholded RGB lifted 20%/40% grey +6/+8; thresholded +0 (50% grey +9).
   HF: packages/core/src/runtime/colorGrading.ts:1484-1485,2358-2369
8. **Gate haze, clipping and skin**, with the Defaults luma/sat/sharp ratios:
   - contrast ≥ x1.00 (target 1.10-1.15); p2 ≤ source + 6.
   - pixels with max(R,G,B) ≥ 250 rise ≤ 1 pp in the face box, ≤ 3 pp overall; mean(R − B) rises ≤ 12.
   - skin (inner 60% of the face box): saturation-weighted circular-mean hue 10-25°, drift ≤ 5°; dark skin (median V < 110) keeps ≥ 0.98x face std and median S.
   - All initial (HF's 12: "to be calibrated"). Refines ref 01 §7 (old: "no lifted-black haze", "skin hue stays 10-25°", unmeasured).
   Why: a 50% screen glow passed luma (x1.116) and sharpness (x2.41) with p2 +10; Y ≥ 235 saw 0% of a 16.6% channel clip.
   HF: packages/cli/src/measure/look.ts:79-86; packages/studio/src/components/editor/colorGradingFrameAnalysis.ts:173-191; docs/prompting/color-grading.mdx:104
9. **One sheet, measured log.**
   - `qc/NN_grade_sheet.jpg`, a row per group (≤ 4): source | graded at 0.25/0.5/0.75 of the clip + a 1:1 face crop; read only it.
   - Log `grade NN luma x1.13 sat x1.31 sharp x1.62 contrast x1.12 p2 +3 clip +0.4pp skin 18° frames=24`.
   - A stage whose toggle moves mean |d| < 0.5/255 did nothing: fix or drop.
   - Refines SKILL step 7 (old: "Review frames against ref 01's QC checklist").
   Why: command success is not a rendered look; glow is judged at 1:1.
   HF: skills/media-use/references/media-treatments.md:137-147,199-201

### Optional
10. **Bake the colour stage to a .cube** when both editors must match.
   - numpy grade → `LUT_3D_SIZE 33`, `DOMAIN_MIN 0 0 0`, `DOMAIN_MAX 1 1 1`, red fastest, `%.6f`; write per ref 05 §2 **Crash-safe writes**.
   - Apply `format=gbrp16le,lut3d=file=grade.cube:interp=tetrahedral` in the RGB stage; unsharp, glow, vignette outside.
   - Tests: identity rows ≤ 1e-6; lut3d vs numpy (16-bit RGB): identity 0, clipped look ≤ 3/255.
   - Skin gate fails → vibrance weight (1 − 0.72·sat)·mix(1, 0.55, skin). EffectCraft LUT parity unproven.
   Why: one function, same numbers in both paths.
   HF: packages/core/src/colorGradingBake.ts:96-121,408-435; packages/core/src/colorGradingBake.test.ts:56-119

#### Not adopted
- Natural Portrait / Product Polish bounded ranges as grade amounts (vibrance 0-0.06, saturation -0.04-0.06, contrast -0.05-0.08, exposure -0.06-0.14; skills/media-use/references/media-treatment-recipes.md:40-52): Ref 01 §7 targets win (mean luma 145-170, median sat 85-105, S-curve +10-15%), and these ranges cannot reach them.
- Analyzer correction amounts: exposure (0.32 - avg)·1.2 EV, contrast (0.35 - spread)·0.4, temperature -0.25·warmth, tint -cast/512 (packages/cli/src/media-use/lib/grade-analyzer.mjs:121-138,153): Too gentle for ref 01's targets. Only HF's diagnosis thresholds are adopted (Diagnose per camera group); the gate loop sets the amounts.
- blacks = +0.08·shadowClipRisk suggestion (packages/cli/src/media-use/lib/grade-analyzer.mjs:159): Under HF's own black-point math (packages/core/src/colorGradingBake.ts:103-106), a positive blacks value raises the black point and darkens clipped shadows further.
- 'If the treatment is not clearly better, keep the source unchanged' (skills/media-use/references/media-treatments.md:198): The SKILL Defaults Grade row requires a grade that measurably beats the source. Ref 01 §7 raises the failing parameter and re-renders instead of reverting.
- Replacing the +10% luma gate with 'no new clipping' on bright sources (reader proposal built on HF's headroom/clip-risk logic): The Defaults table is fixed, and the change is not needed. A pchip mid lift reached luma x1.104 with +0.1 pp clip on a source where ref 01's eq clipped +16.6 pp.
- Additive bloom, color += bloom·amount, one-click 0.55, max 3 (packages/core/src/runtime/colorGrading.ts:1376; packages/core/src/colorGrading.ts:853,929): Ref 01 §7 polish is a blurred screen blend at 12-18%. Only HF's luma threshold, half-res pass and RGB compositing are adopted (Threshold the glow, in RGB).
- UI Fidelity default payload 'none' (no grade) for screen recordings and slides (skills/media-use/references/media-treatment-recipes.md:153-156): The Defaults require a measurable grade on every clip. A lighter grade for screen or gameplay footage needs an explicit request.
- Whole-frame warmth/cast from frame-average U/V (packages/cli/src/media-use/lib/grade-analyzer.mjs:131-138 applied to whole frames): Skin dominates chroma. With a 31% skin block, whole-frame warmth read +0.107 on grey (a false cast) and only +0.013 on a real cool cast (neutral pixels: -0.135).
- Luma-percentile clip risk YHIGH >= 235 as the clipping gate (packages/cli/src/media-use/lib/grade-analyzer.mjs:116-117): It saw 0% of a 16.6% channel clip caused by eq. Kept only as a diagnosis class; the gate uses max(R,G,B) >= 250.
- -noaccurate_seek keyframe sampling for gate samples (packages/cli/src/media-use/lib/grade-analyzer.mjs:221-222): The same -ss 3.508 landed on 3.0 s with a 60-frame GOP and on 0.0 s with a 300-frame GOP. The gate pairs frames by index (ref 05 §1 Frames by index).
- HF look metrics as gate metrics: luma = mean BT.601 Y, saturation = mean (max - min)/max at 160 px wide (packages/cli/src/measure/look.ts:19-43): Ref 01 §0.3 names median HSV saturation, and extract_ref.py:44 measures luma as mean HSV V. Only HF's contrast = std, its floors and its ratio rule are adopted.
- Grain, dither, scanlines, halftone, film/VHS and other stylised looks: Not part of ref 01's look.
- Five samples per file as the analysis granularity (packages/cli/src/media-use/lib/grade-analyzer.mjs:7): Camera groups need per-shot samples, and the gate needs 1 fps paired frames.

<!-- G8 = ref 05 §1 | verified (major_rewrite) -->
> **ref 05 §1: verified**

## QC gates, review sheets and reference-study tooling
Scope: render gates, review sheets, notes, reference studies (ffmpeg 7.1, lavfi tests).

### Adopted (default)
1. **Frames by index.** Read frames by decode index, never by seeking.
   - Frame showing t: k(t) = floor((t + 0.0005)·fps + 1e-6) (→ ref 03 §2 **Frame grid**).
   - One decode per file: `-vf "select='eq(n\,0)+between(n\,59\,61)',setpts=N/(60)/TB" -fps_mode passthrough`; frames out must equal frames asked.
   - Pairs: raw↔edited at the same k; source↔output through the remap (→ ref 03 §2 **One clock**). `settb=1/1,setpts=N` after each `select`, then `psnr`/`ssim` with `shortest=1:repeatlast=0`; rows must equal pairs asked.
   - Samples: first and last frame; a 1 fps grid at t = i + 0.5 s (the grade gate uses it); k−1..k+1 around each cut and accent; each chunk's fully built frame.
   - Why: without `-fps_mode passthrough`, 4 picks gave 62 frames (`select` alone) or 3 (with `setpts`). After 2 dropped frames, PTS pairing read 24-25 dB on identical pictures, index pairing 45-53 dB.
   - HF: `packages/cli/src/measure/media.ts:212,339-341`, `packages/cli/src/commands/measure/frames.ts:52-75`, `packages/producer/src/regression-harness.ts:607-620,654-663`
2. **Stage, validate, promote.** Refines ref 01 §0.1 and its QC duration line (old: "asserts `duration <= 59.5 s` (ffprobe, or `ffmpeg -i` when ffprobe is absent)").
   - Render to a staged name; promote to `edited/NN-slug.mp4` only when no P0 remains (names, rename retries: → ref 05 §2 **Crash-safe writes**).
   - One decode, `ffmpeg -v error -i X -f null - -progress pipe:1`: stderr empty; frames (last `frame=`) == the plan's N, each EffectCraft part its own N; N/fps ≤ 59.5 s, else re-cut (Defaults).
   - Header (→ ref 03 §1 **Probe once**): canvas size, fps, `yuv420p`, one 48 kHz stereo AAC. Audio length and mux structure: → ref 03 §4 **Delivery gate**. Never gate on `Duration:`.
   - Why: a 2.5 s picture muxed with 3 s audio read `Duration: 00:00:03.00`; the decode counted 150 frames. `-c copy` counted 178 packets for 177 decoded frames; a damaged file decoded 145/150 frames with 32 error lines.
   - HF: `packages/producer/src/services/render/artifactTransaction.ts:23-33,230-271`
3. **Events match the plan.** New gate on `edited/NN` (detector → ref 04 §2 **Classified cut detector**).
   - Explained: a 1-frame hit within ±1 of a planned join or kept source cut; hits within a whip span ±1 or an accent window (−2 frames to decay end); a source event at the mapped frame.
   - Every planned hard cut and whip shows a hit. A seam without one passes when d ≥ max(6, 0.5 × seam change) and ≥ 4 × typical within ±1 (seam change = mean |ΔY| of the two raw frames meeting there, 64×36 grey; < 6: unverifiable).
   - P0: a missed cut or whip; an unexplained hit (sliver, doubled segment, part seam); a 2-3-frame hit at a hard cut (black or orphan frame).
   - Why (tested): a black frame at a join read as one 2-frame hit; a 2-frame tint flash as two 1-frame `flash` events; a 6% same-camera jump cut (d 7.9) passed only via the seam check.
   - HF: `packages/cli/src/measure/diff.ts:67,461-474`, `packages/cli/src/measure/cuts.ts:97-110`
4. **Captions from pixels.** → ref 04 §1 **Presence, stale and sync gate**.
5. **A/V offset.** New gate.
   - Onsets per cut-list segment ≥ 2 s, output span vs its source span: `-af aresample=async=1:first_pts=0 -ac 1 -ar 8000 -f f32le`, RMS per 80 samples, rises only, Pearson over lags ±500 ms. r ≤ 0.3 = unmeasured; P0 if |offset| > 1 frame.
   - Lip sync, 1-2 longest single-shot speech windows ≥ 2 s: mouth = median tallest face box (x + 0.2w, y + 0.62h, 0.6w × 0.38h), grey 160 px wide, mean |Δ| per frame vs |Δ RMS| per frame (16 kHz); Pearson over ±0.4 s, parabola-refined; + = picture late.
   - High: peak r ≥ 0.5, margin ≥ 0.1 over lags > 2 frames away, not at the search edge, speech (RMS > 0.1 × max) ≥ 10% of frames. Judge high only, speech ≥ 30%: P0 outside −125..+45 ms, unless the source window reads the same lag ±1 frame (source offset: P1). Medium/low = unmeasured, never a pass.
   - Why: priming, seeks and muxing shift sound. Tested: lip sync +2.2 / +33.0 / −198 ms for in sync / picture 2 f late / audio 200 ms late (all high); onsets 0/30/200 ms for 0/33/200 ms, also under a −10 dB bed and SFX hits; under a bed, 1-s windows misread 4 of 22 (to 500 ms, r 0.98), 2-s windows 0 of 30.
   - HF: `packages/cli/src/measure/diff.ts:1059-1100`, `packages/cli/src/measure/sync.ts:53-86,103-124`, `packages/cli/src/measure/person.ts:21-24,498-526`
6. **Black, frozen, frame 0.** New gate; refines ref 01 QC (old: "Frame 0 has speech or a reaction").
   - `ffmpeg -hide_banner -i X -vf "blackdetect=d=0:pix_th=0.10,freezedetect=n=-60dB:d=0.3" -an -f null -`: a black frame, or a freeze outside a planned still (meme freeze), = P0; P1 if the mapped source span shows it too.
   - Sampled indexes: RGB sum ≤ 12 in edited and ≥ 32 in raw on > 0.1% of the central 60% × 60% = P0 (dropped layer).
   - Frame 0 is the thumbnail: a detected face (speaker or reactor).
   - Why (tested): 1- and 2-frame blacks reported exactly, a 30-frame freeze as 0.45 s, a clean noisy clip as nothing. Full-frame black-only read 0.7-36% on clean dark shots under the ref 01 grade + `vignette=PI/5`; the centre read 0 and caught a dropped top panel (0.361).
   - HF: `packages/engine/src/utils/gpuParityDiff.ts:120-123,208-217`, `packages/cli/src/utils/craftAudit.ts:128-135`
7. **Framing by shot medians.** Refines ref 01 QC (old: "On 1 fps samples, the face is fully in frame on every close shot, eyes at y 22-35%").
   - Source face track mapped through the crop path; per close shot ≥ 1 s with ≥ 3 samples at 4/s, tallest face, medians: height 20-30% H, eyes 22-35% H, centre x 40-60% W (ref 01 §4).
   - Face fully in frame stays per sample (→ ref 04 §2 **Push-ins on a parent; canvas covered**); jitter stays ref 01's < 0.5% W.
   - Sticker, label and watermark boxes never overlap the face or the live caption box.
   - Why: a stray detection can't fail a shot; lucky samples can't pass one.
   - HF: `packages/cli/src/measure/person.ts:13-20,417-447`, `packages/cli/src/utils/checkPipeline.ts:344-381`
8. **Review sheets.** Refines SKILL step 7 (old: "Review frames against ref 01's QC checklist"); open every sheet before delivery.
   - `qc/NN/seams.jpg`: a row per cut and accent at k −12, −6, −1, 0, +1, +6, +12 (30 fps: −6, −3, −1, 0, +1, +3, +6; ±1 ours), 384 px tiles: `-vf "select='eq(n\,108)+eq(n\,114)+between(n\,119\,121)+eq(n\,126)+eq(n\,132)',scale=384:-2,tile=7x1" -frames:v 1`.
   - `beats.jpg`: each shot at min(start + 0.3 s, middle), plus the middle if ≥ 0.5 s later, 480 px. `phone.jpg`: each fully built chunk 360 px wide: readable?
   - Strips over 12 frames keep k−1..k+1 of each onset, ≥ half evenly spaced.
   - Why: 1 fps grids miss 1-3-frame flashes, slivers and seam jumps.
   - HF: `packages/cli/src/commands/snapshotReview.ts:10-16,139-151,292-335`, `packages/cli/src/commands/measure/frames.ts:138-156`
9. **Measure, then look.**
   - `qc/NN/qc.json`: `{ok, findings:[{id, measured, threshold, status, fix, ref}]}`; fix a warning or waive it in the clip's plan with a reason.
   - One line per problem: `t=12.40s f744 · captions · 4 f late → reveal at f740 · keep colour`. P0 = failed gate or Defaults breach (a reused SFX): blocks delivery; P1 = weakens (seam jump, soft payoff); P2 = polish.
   - Fix every P0 and cheap P1s; re-check changed frames only; full re-pass only while a P0 is open; a numeric near-miss with nothing visible: one bump, one re-render. Never score a render /10 (candidates keep ref 02 scores).
   - `REVIEW.md` in the job folder, short form in the reply: gate numbers; measured vs only looked at ("audio measured, not listened to"); fallbacks (edit path, ASR model/device, font, SFX variants); waivers; weakest moment.
   - Why: a score finds nothing to fix.
   - HF: `skills/hyperframes/references/review.md:7,32-38,44-51`
10. **Word timings.** → ref 03 §1 **Normalise words** and **Failure gate + hallucinations**.
11. **Reference studies per frame.** Refines SKILL "New reference shorts" (old: "cut times, 1 fps frame grid").
    - Events at native fps (→ ref 04 §2 **Classified cut detector**), not `extract_ref.py`'s HSV-histogram Bhattacharyya > 0.45 (172 "cuts" vs ~27 real on ref 1); flashes and whips count as accents.
    - A strip per event window: ±2 frames, merged within 0.25 s while ≤ 1.5 s. Caption switches from caption-band pixels, every frame. Stats: → ref 04 §3 **One metric definition**.
    - Note each number's resolution; re-measure ref 01's caption lead per frame (read off 1 fps frames and 10 fps sheets).
    - Match a reference one axis per render, as an absolute value ("cap height = 3.3% H"), never a relative nudge.
    - Why: second- or quarter-second sheets miss 1-3-frame timing and one-frame flashes; relative corrections pendulum.
    - HF: `skills/reverse-any-video/SKILL.md:19-21`, `skills/reverse-any-video/references/match.md:8`, `packages/cli/src/measure/events.ts:16-19,382-410`, `docs/prompting/recreating-references.mdx:29-38`

### Optional
1. **Regression renders** (skill changes). Index-paired SSIM (whole frame, worst 4×4 cell) of re-rendered stored cases vs their stored renders. Bar = the case's baseline p05 − 0.02, never tightened; a flipped case re-runs twice, fails on 2 of 3. Picture-unchanged re-edits: → ref 05 §2 **Prove the freeze**.
   - Why: regressions drop mean SSIM ≥ 0.05; encoder drift ~0.01.
   - HF: `skills/remotion-to-hyperframes/references/eval.md:68-75`, `packages/cli/src/measure/diff.ts:302-304`, `packages/studio/tests/e2e/edit-accuracy/ratchet.mjs:2-4`
2. **Locate reference shots in their source** (trims vs ref 02's pads): 100 Hz RMS envelopes (8 kHz, 80-sample RMS), lags keeping ≥ 90% inside, r ≥ 0.6.
   - HF: `packages/cli/src/measure/person.ts:34-37,122-153`

#### Not adopted
- HF review.md:38 'A film that feels busy: remove a third of the motion': Ref 01 §5 fixes accent density (1 per 6-8 s, at most 40% of cuts) and §8 fixes pacing. A blanket one-third cut would undershoot both.
- HF dead_stretch warning: nothing on screen changes for more than 3 s (packages/cli/src/utils/craftAudit.ts:18; docs/packages/cli.mdx:1294): Ref 01 §8 allows shots up to 7 s and speechless action stretches up to 5 s (9 s for the main climax), with music and an asterisk caption. Speech stretches change captions anyway. Not a gate.
- HF first_frame_empty fix: 'have the title or key image already on screen at 0 s' (packages/cli/src/utils/craftAudit.ts:133): Ref 01 §1-2: no title or hook banner; frame 0 is mid-sentence or a reaction close-up. Adopted only as 'frame 0 shows a detected face'.
- HF rebuild SSIM bars: mean 0.92, p05 0.85, worst cell 0.75 (packages/cli/src/measure/diff.ts:53-60): These bars grade a rebuild against its original. Our render differs from the source by design (crop, grade, captions, accents), and regression renders calibrate a per-case bar instead (eval.md:68-75).
- HF 'Render and diff once more, then stop' applied to visible defects (skills/reverse-any-video/SKILL.md:36): SKILL step 7 'fix before delivery' wins for P0 and visible defects. The stop applies only to numeric near-misses with nothing visible.
- HF persistence rule: a finding at a single sample demotes to info; one held across samples gates (skills/hyperframes-cli/references/lint-validate-inspect.md:68; packages/cli/src/utils/checkPipeline.ts:1890-1895): Our gates target 1-frame defects (black frames, slivers, dropped layers), and accent windows already exclude planned transients. The synthesis's untested '>= 3 frames' variant contradicted those gates.
- Caption presence by plain mean |edited - raw| with HF's change threshold of 5 (packages/cli/src/measure/events.ts:229), or by an affine ring-fit residual (synthesis proposal): Tested with the ref 01 grade. A caption-free box read 4.7-4.9 with the plain difference, right at the threshold. The residual passed a font-fallback render (43.8 >= 10) that ref 04 §1's caption-only match failed (0.086). Ref 04 §1 is the one method.
- HF black-only rule counted over the full frame (packages/engine/src/utils/gpuParityDiff.ts:120-123): Tested: clean dark shots under the ref 01 grade + vignette=PI/5 read 0.7-36%, a false P0 at the 0.1% bar. The central 60% x 60% read 0 and still caught a dropped panel (0.361).
- HF audio null test: residual <= -50 dBFS as proof of an untouched mux (packages/producer/src/utils/audioRegression.ts:83-87): One AAC generation of pink noise read -50.8 and -47.9 dB in two runs, straddling the bar. The mux is a stream copy, proven bit-exact by ref 05 §2 Prove the freeze; A/V offset catches shifts.
- HF frame tolerances: a 1-frame shortfall (packages/producer/src/services/render/artifactTransaction.ts:230-246) and video-frame coverage 0.95 (packages/producer/src/services/render/videoFrameCoverage.ts:40-44): That slack covers browser capture and container rounding. Our plans are integer frames rendered CFR, so decoded frames must equal N. A 0.95 bar would pass a 3 s loss in a 60 s clip.
- HF adaptive hold floor clamp(2·p10, 0.5, 1.5) grey levels for frozen pictures (packages/cli/src/measure/events.ts:103): A still talking head can sit under that floor. freezedetect=n=-60dB:d=0.3 found an injected 30-frame freeze (0.45 s reported) and nothing on a clean noisy clip.
- PSNR >= 32 dB for picture-unchanged re-edits (floor from packages/engine/src/utils/psnr.ts:37-44): Superseded by ref 05 §2 Prove the freeze: the video stream hash must stay identical.
- Decoded-audio end window (-1 frame to +1 frame + 1024 samples) as a separate artifact check (synthesis proposal): Ref 03 §4 Delivery gate owns audio length. Decoded AAC runs up to 1023 samples past the mix (tested: 120000 -> 120832), so that gate reads container durations instead.

<!-- G9 = ref 05 §2 | verified (fixed) -->
> **ref 05 §2: verified**

## Skill structure, re-edits, picking hygiene and the lessons loop
Scope: what ships, safe writes, caching, re-edits, versions, copy fidelity, lessons.

### Adopted (default)
1. **Ship stages, fill a plan.** Direction: each deterministic stage ships as a script with a `SCRIPT_VERSION`; one hand-written in 2 jobs ships next. Per clip Claude writes the plan `plans/NN-slug.vK.json` (cut word ids, chunks, accents, SFX ids, grade, mix, ending).
   Why: per-job rewrites drift toward the last job's look.
   HF: .agents/skills/changelog-video/SKILL.md:30-46
2. **Crash-safe writes.** Write `<name>.tmp-<pid>-<uuid8>`, then `os.replace`; ffmpeg writes `<out>.part.mp4` (a bare `.part` has no muxer), then renames. Windows: retry `PermissionError` (file held open, or a dir name taken) after 10, 20, 40, 80, 160, 320, 640 ms (1.27 s), then raise.
   Why: a kill mid-write truncates the real file; time-named temps collide.
   HF: skills/media-use/scripts/transcript-cut.mjs:123-125, packages/core/src/renameWithRetry.ts:5-8, packages/cli/src/whisper/transcribe.ts:303-315
3. **Stage cache = key + schema + sentinel.**
   - `cache/<stage>-v<N>-<sha16>/`; sha16 = first 16 hex of sha256 over `json.dumps({"stage": s, "schema": N, "inputs": i, "params": p}, sort_keys=True)`. Source = videoId + format_id + size; ASR adds model, compute_type, language.
   - Build in `<entry>.partial-<pid>-<uuid8>/`, write `.complete` last, rename (taken: keep theirs). Hit = `.complete` + non-empty outputs, else rebuild. Bump N when a key's output changes.
   - Seeds: `random.Random(f"{videoId}:{rank}:{item}")` (str seeds are stable); never `hash()` (salted per run).
   Why: a half-written entry or reshuffled SFX pick survives every re-edit.
   HF: packages/engine/src/services/extractionCache.ts:13-23,61-65,202-211,243-252, skills/hyperframes/SKILL.md:23
4. **Re-edits touch the smallest stage set.** Write the note into the plan as an absolute value ("end = 28.40 s"); re-run only:
   - start, end, max length, removed words, ending: cut and every stage after
   - aspect: crop, captions, video, mux
   - caption text or colours: captions, video, mux
   - accents: accents, mix, video, mux; grade: video, mux
   - SFX, music: mix, mux (`-c:v copy`); clip count: the added clips only
   Never re-download or re-run ASR while cached. Refines SKILL step 8 / ref 02 rule 10 (old: "Re-run steps 4-7 only" / "re-run only cut, reframe and render").
   Why: relative notes oscillate; full rebuilds drift on settled choices.
   HF: docs/prompting/editing-existing-videos.mdx:8-10,42
5. **Prove the freeze.**
   - `ffmpeg -v error -i X -map 0 -c copy -f streamhash -hash md5 -`, old vs new: audio-only re-edit = same `0,v,MD5=` line; visual-only = same audio line (→ ref 03 §4 **One AAC encode, copied at the mux**).
   - Caption-only: per-frame SSIM of the bands y < 40% H and y ≥ 85% H, paired by index (→ ref 05 §1 **Frames by index**): p05 ≥ 0.98. Lavfi test: caption 50% → 72% H 0.997; 6 px shift 0.88; mild grade 0.97. Assumes ref 01 caption positions; EffectCraft untested.
   Why: whole-frame SSIM scored the caption change 0.945, below an unwanted grade (0.971).
   HF: packages/cli/src/measure/diff.ts:303-304
6. **Versions, undo, hand edits.** Each render = `versions/NN-slug.vK.mp4` + `plans/NN-slug.vK.json`; `edited/NN-slug.mp4` copies the latest. "Undo" or "worse" re-delivers vK-1. A file Claude wrote whose sha256 changed is the person's edit: an input, never overwritten (`edited/` copy edited or locked: deliver `versions/`, say so). Extends ref 02 rule 9's layout.
   Why: a hand fix overwritten between turns is lost.
   HF: skills/hyperframes-cli/SKILL.md:52, packages/cli/src/media-use/lib/manifest.mjs:83-84
7. **Job ledger.**
   - `job.jsonl`, per written file: stage, path, sha256, input/params hashes, script/tool versions, written_by, time; append under an O_EXCL `.lock`; skip bad lines; last record per path wins.
   - Regenerate `INDEX.md` (id, stage, dur, dims, path); re-edits read it and `REVIEW.md` first (→ ref 05 §1 **Measure, then look**).
   - Name changed tool versions old → new; their first clip runs every gate. Hard blocker: write `REVIEW.md` before any fallback.
   Why: one file holds the state; a session dying mid-fallback still leaves a report.
   HF: skills/media-use/references/memory.md:33-35, skills/hyperframes/references/skill-lifecycle.md:49, skills/hyperframes-cli/references/doctor-browser.md:43-45
8. **Copy traces to the transcript.** Each number in `title` and `post_caption` equals a value spoken in the clip span after normalising ($1M = 1,000,000 = "a million"); each name occurs in the span, video title or channel (hashtags exempt). No derived claims ("40 min to 2 min" is not "20x faster"). Adds to ref 02 rule 7.
   Why: an invented number goes out under the creator's name.
   HF: skills/hyperframes/references/story.md:12-13
9. **Lessons loop.**
   - JSON lines in `$CLIP_EDIT_HOME/lessons.jsonl` (default `~/.clipping-edit`): ts, job, stage, kind (user_correction, qc_fail, fallback, missing_feature, banned_default), detail, fix, ref; paths scrubbed; best-effort.
   - A detail seen in ≥ 2 jobs becomes a ref rule, ref 01 number or QC check plus a regression case (→ ref 05 §1 **Regression checks**), committed without paths or names.
   - Each review logs generated-looking defaults as banned_default; promoted ones are proposed for ref 01 §5 "Never use".
   Why: corrections that live only in chat repeat.
   HF: packages/cli/src/media-use/lib/misses.mjs:11-27, skills/hyperframes/references/spec.md:64
10. **Context hygiene.** Stdout contract → ref 03 §1 **Script hygiene**; print it as `json.dumps(o, indent=1)` with each innermost `[..]`/`{..}` folded onto one line. Per-frame series go to `.tsv`. Never Read a `.cube`, crop path or per-frame file; view its sheet.
    Why: a 33^3 LUT is ~36k lines with no legible signal.
    HF: skills/media-use/references/grading.md:20, packages/cli/src/measure/media.ts:343-345
11. **Skill upkeep.** SKILL.md routes (Defaults, gates, "What to read" table); ref numbers never change. A skill lint (direction) fails on:
    - description > 320 B, SKILL.md > 7,168 B
    - empty name or description; unquoted frontmatter value with ": "
    - a SKILL.md code span with an exclamation mark, or ">" before a word character
    - a missing `references/`, `scripts/` or `assets/` path; `analysis/` not marked repo-only
    - a Defaults number differing between SKILL.md, README and ref 01 §0
    Drift: run from a checkout, preflight compares `skill/` with a copied install and warns, by bundle hash (sha256[:16] over sorted POSIX relpaths + NUL + text, CRLF → LF, + NUL; no `__pycache__`).
    Why: one bad frontmatter line or span stops the skill loading; copied installs drift.
    HF: scripts/check-core-skills.mjs:12-23,48-55, scripts/lint-skills.ts:39-55,70-79, packages/cli/src/utils/skillsManifest.ts:233-247, skills/hyperframes/SKILL.md:58-74

### Optional
12. **Remembered prefs and looks.** Record aspect, max length, clip count, SFX on/off, palette only when typed or approved; promote to per-user prefs once 2 jobs (distinct videoIds) confirm a value. Apply as a request with a receipt ("aspect 9:16 (jobs A, B)"); a live request wins; never relax a quality gate (longer max, no tracking, no grade gate, reused SFX). Refines SKILL Defaults (old: "Any of these can be changed by the request"). After approval, offer once to save the look to `$CLIP_EDIT_HOME/looks/<slug>/`.
    Why: one-off choices must not become defaults; prose loses continuous qualities (glow strength).
    HF: skills/media-use/references/memory.md:5,13,21,29, docs/prompting/recreating-references.mdx:44-46

#### Not adopted
- Never render merely because checks pass; pause at the final preview and wait for approval (skills/hyperframes-cli/references/conventions.md:17; skills/hyperframes/SKILL.md:48): SKILL.md Pipeline wins: a one-line trigger runs the whole job without asking questions.
- Do not build a substitute rasterizer on a blocked host (skills/hyperframes-cli/references/doctor-browser.md:40-43): SKILL.md Editing path B sanctions the ffmpeg + ASS/libass + Pillow fallback. Only 'write the report before any fallback' is adopted (Job ledger: REVIEW.md first).
- Remembered preferences that never skip a question (skills/media-use/references/memory.md:13): The one-line trigger asks nothing, so remembered values are Optional (Remembered prefs and looks). They apply as a request with a receipt line and never relax a quality gate.
- The change or question arrives within about the first second (skills/hyperframes/references/types/vertical.md:11-12): Ref 01 §2 wins as the gate: premise spoken by t <= 2.5 s, measured on the reference Shorts (ref 3 lands it at 1.3 s).
- Cache source key (path, mtime, size) (packages/engine/src/services/extractionCache.ts:8-9,73-79): A re-download changes path and mtime; HF itself keys downloaded media by content SHA-256 instead (:92-93). We key on videoId + format_id + size, so a multi-GB source is never hashed.
- Bundle hash over the sorted full OS path list (packages/cli/src/utils/skillsManifest.ts:223-225): HF's own docstring (:229-231) promises relative POSIX order. On Windows a backslash sorts after digits (tested: 'a0.md' sorts before 'a\x.md', but 'a/x.md' sorts before 'a0.md'), so the same tree hashes differently per OS. We sort POSIX relative paths.
- Cache LRU clock and GC sweeps (packages/engine/src/services/extractionCache.ts:24-26): Stage caches live in the job folder and go with it; no cross-job cache is kept.
