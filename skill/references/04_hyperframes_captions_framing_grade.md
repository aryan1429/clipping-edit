# 04 - HyperFrames study: captions, framing and grade

Studied from HeyGen HyperFrames (https://github.com/heygen-com/hyperframes, Apache-2.0, (c) 2026 HeyGen, Inc.) at commit 8c22ddb (2026-11-01). The method, raw notes and full learning index are in `analysis/repos/hyperframes.md` (repo-relative; not part of the installed skill).

**Precedence.** Ref 01 wins on style: canvas, caption look, accents, grade targets, pacing and ending. Ref 02 wins on moment-picking and job layout. The SKILL.md Defaults table is fixed. Refs 03-05 win on technical correctness where 01/02 are silent or vague: timing and sync, cutting and splicing, audio levels and mixing, encode/mux and colour metadata, QC gates and job hygiene. A rule that changes an older one says "Refines ... (old: ...)".

**Reading the rules.** "HF: path:lines" cites the HyperFrames repo at that commit. "Tested" or "here" means measured with ffmpeg 7.1 on synthetic lavfi media while this reference was written. Pointers like "→ ref 03 §2 **Frame grid**" name the section and the rule's bold title.

## 1. Captions: timing contract, layout and legibility gates
Scope: frame-exact, machine-checked ref 01 §3 captions in both editors.

### Adopted (default)
1. **Token timing contract.** Refines ref 01 §3 Text cleanup (old: "fix whisper errors", no timing). The one format for the LLM's caption text fixes.
   - Step-5 cleanup, over the clip's word ids: `{"tokens":[{"d":"GONNA","src":["w813","w814"],"sp":"going to"}],"drop":["w812"]}`.
   - 0 errors before render: ids strictly increasing, each used once; src ∪ drop = all clip words (drop = fillers, stutters, self-corrections); asterisk tokens have no src.
   - ASR fixes are `d`/`sp` on src ids; a merge is a multi-id src. Names from the video metadata (→ ref 03 §1 **Language and names**) fix spellings here.
   - norm(sp or d) matches norm(joined src texts): lowercase `[a-z0-9]`; equal, prefix, or Levenshtein ≤ max(1, ⌊min len/3⌋), else MISMATCH. start = src[0].start, end = src[-1].end.
   Why: rewrites ($100K, F**K) lose their times; without `sp` each failed.
   HF: .agents/skills/changelog-video/scripts/align-captions.mjs:11-15,39-58,123-127; .agents/skills/captions-overlay/SKILL.md:26
2. **ASS frame times.** Frames per ref 03 §2 **Frame grid**: `k(t) = floor((t + 0.0005)*fps + 1e-6)`, on output times (`k(remap(word.start))`, ref 03 §2 **One clock**).
   - appear_f (a) = max(0, k(word.start) − 1); end_f = min(k(last.end + 0.6), next start_f); the last chunk ends at N.
   - Start = first frame on, End = first frame off, in floored centiseconds `cs = 100*k*den//num` (fps = num/den; H:MM:SS.cc).
   - `ass` keys on PTS: the burn input's first `pts_time` (showinfo) is 0; fix the cut, not `setpts` there.
   Why: floored cs was exact at 23.976-60 fps; nearest-cs rounding put 8/24 starts a frame late at 30/60.
   HF: skills/reverse-any-video/SKILL.md:19; packages/cli/src/measure/media.ts:339-341
3. **Event mechanics.** Refines SKILL path B and ref 01 Editing tool (old: "`\fad`/`\t` for the 3-frame fade", "per-word `\fad`/`\blur`/`\fscx` tags") and ref 01 §3 Reveal (old: "opacity 0 to 100%, scale 90 to 100%, blur 6 to 0 px").
   - Per word one event per Layer (0 shadow, 1 glow, 2 fill), each `\an5\pos` at the word centre (cy = baseline − 0.304·`\fs`): unpositioned overlaps restack, `\an7` scales from the corner (12-14 px slide).
   - End = chunk end_f (hard kill; EffectCraft: out-point, full-canvas precomps).
   - Sole opacity owner: the entrance from 1/3, `\alpha&HAA&\fscx93\fscy93\blur4\t(0,T,\alpha&H00&\fscx100\fscy100\blur0)`, T = round(2000/fps) ms: alpha 33/67/100% on a..a+2 (`\fad`: 0-12% on a).
   - Layer order, bottom to top (not in HF): graded footage (→ ref 04 §3 **Grade and gate the footage only**) → accents (→ ref 04 §2) → captions → stickers and 💀.
   Why: stacked, sliding, stuck and late words; a flash drawn over captions washes them out.
   HF: skills/hyperframes/references/captions.md:21,34,36-37; packages/lint/src/rules/captions.ts:26-36
4. **Size and stroke.** Refines ref 01 §3 Size for ASS (old: "At 1440: about 68 px").
   - `\fs` = em × (usWinAscent + usWinDescent)/unitsPerEm: Montserrat Black ×1.379 (68 px em = `\fs93.8`, 90 px = `\fs124.1`).
   - `\bord` = 0.04 × em (outside, under the fill); EffectCraft (centred stroke): Fill Over Stroke 0.08 × em (check one frame).
   - Gate: cap height 3.3% H ±1 px (47 px at 1440, 63 at 1920).
   Why: `\fs68` gave a 35 px cap (2.4% H) vs Pillow's 48.
   HF: registry/components/caption-emoji-pop/caption-emoji-pop.html:106-107
5. **Measured-fit chunks.** Refines ref 01 §3 Size (old: "cap height 3.3% H", "Max line width 80% W. Max 2 lines").
   - Line width = Pillow `getlength(line)` at the em × 1.02 (ASS) or × 1.14 (EffectCraft, unmeasured) + 2·`\bord`.
   - Lines ≤ 0.80 W, ≤ 2, split at argmin |w1 − w2|.
   - A word that breaks the fit starts the next chunk (never shrink), still with the punctuation/0.25 s flush. A lone word > 0.80 W may scale to ≥ 0.85×.
   Why: libass ink = 0.99-1.01 × (getlength + 2·`\bord`).
   HF: registry/components/caption-neon-accent/caption-neon-accent.html:139,295-299,311-373
6. **Keyword guard.** One-word keywords stay white if in: the a an and or but is are was were to of in on at for with by from as it its this that these those be been have has had do does did will would could should may might must can if then so just up out about (49 words).
   - Digit/$/% tokens default to cyan. No randomness.
   Why: coloured "THE" is noise; NO/NOT/YES stay free for red.
   HF: registry/components/caption-neon-accent/caption-neon-accent.html:142-199,284-285
7. **Face avoidance per window.** Refines ref 01 §3 Position (old: "intersects the tracked face box (eyes to chin), move the block to y = 72% H").
   - Block box = caption-only render on #808080, max|px − 128| > 24 (includes shadow and glow; `ass` writes no alpha).
   - Low (72% H) when it meets the union of face boxes (eyes to chin, +5%) over [start_f, end_f).
   - After a low chunk, return to 50% at the first of 2 clear chunks; cuts reset.
   - QC: 0 frames over a face.
   Why: heads move mid-chunk; per-chunk flips flicker.
   HF: skills/hyperframes/references/captions.md:45; docs/guides/captions-and-recuts.mdx:125-127
8. **9:16 UI band.** Refines ref 01 §3 Position on 9:16 (old: "move the block to y = 72% H").
   - On 1080×1920, caption, label and sticker boxes stay in y 168-1330 px.
   - Low = block bottom at 1330 (72% H is 1382). Clear the right action rail (no width given).
   Why: app UI covers y < 168 and > 1330 px.
   HF: skills/hyperframes/references/types/vertical.md:7
9. **Burned-in text scan.** Refines ref 01 §1 (old: stream overlays kept "only if cropping them out would cut the subject").
   - Before the reframe: `ffmpeg -ss S -to E -i src.mp4 -vf "fps=1,scale=360:-1,tile=6xK" -frames:v 1 sheet.png`, K = ⌈(E − S)/6⌉ (a fixed 6x10 drops everything after 60 s).
   - Crop out subtitles, lower thirds, chat and tickers; else keep the captions clear of them.
   Why: source subtitles can start mid-clip.
   HF: skills/hyperframes/references/captions.md:39
10. **Presence, stale and sync gate** (hard fail). Refines ref 01 QC (old: "Captions sit within ±2 frames of the whisper word starts").
    - R = the same editor's fill-only render (no entrance) on #808080 at end_f − 1; P = the caption-free graded render `qc/NN/grade.mp4` (→ ref 04 §3 **Grade and gate the footage only**).
    - Half size: word mask = |R − 128| > 64, eroded 1 px, minus pixels where P is within RGB 45 of R (< 25% left: skip the frame); match = share within RGB 45 of R.
    - Skip accent spans ±2 frames (the accents sit under the captions but are not in P).
    - Presence: every word ≥ 0.8 at chunk midpoints + ≥ 6 speech frames. Stale: ≤ 0.2 on end_f..end_f+2 (minus the next chunk's mask).
    - Sync: the match ≥ 0.5 run reaching min(full_f + 8, end_f − 1) starts at full_f = appear_f + 2, ±1.
    - Font: each `fontselect: (<family>, …) -> X` line (info log level) names that family (a typo gave `ArialMT`).
    Why: deleted chunk 0.00, held chunk 1.00, +4-frame shift lag 3-4; without P, a bright caption-free plate read 0.35.
    HF: .agents/skills/changelog-video/SKILL.md:162-167; packages/cli/src/measure/drawn.ts:9-14
11. **Legibility gate.** Refines ref 01 §3 (old: shadow "at 55% opacity").
    - At each word's full frame, render the shadow layer alone over the same frame of `qc/NN/grade.mp4` (glow and stroke count as glyph paint).
    - Sample the word box inset 1 px on a ⌊w/12⌋ × ⌊h/6⌋ px grid; bg = per-channel median; pass max(WCAG fill, black stroke) ≥ 3.0.
    - Fail → the other ref 01 position if face-clear, else that chunk's shadow at 75%; never a box.
    Why: red over grey 130-170 read 2.0-2.9 at 55%, 3.3-4.2 at 75%.
    HF: packages/cli/src/commands/contrast-sample.ts:3-8,38-62; packages/cli/src/commands/contrast-audit.browser.js:600-636
12. **Non-speech text floors.** Refines ref 01 §2 (old: "add one asterisk line ... for ≤ 1.5 s").
    - Asterisk lines, context line, labels: fully typed for ≥ 0.4 s (≤ 2 words) or ≥ 0.75·(0.5 + 0.3·n) s; font ≥ 2.6% of the short side (28 px).
    - Context line ≤ 3 words, typed in ≤ 0.45 s (+1.05 s = 1.5 s).
    Why: typed lines vanish unread.
    HF: packages/cli/src/utils/craftAudit.ts:5-21,447-450

### Optional
- **Speech-rate chunk cap.** Refines ref 01 §3 Chunking (old: "2-4 words per chunk (max 6)"): 3 words at ≥ 3.3 words/voiced s, 4 at 2.3-3.3, 5 below (threshold ours).
  Why: 2-word flips on slow speech read choppy.
  HF: skills/hyperframes/references/captions.md:19

## 2. Cut detection, reframe and accents
Scope: cuts, the crop across them, and frame-exact flashes, whips and pushes.

### Adopted (default)
1. **Classified cut detector.** Refines SKILL step 4 (old: "ffmpeg `scene` > 0.3") and ref 02 rule 13 (old: "histogram difference over 0.35").
   - Input: the ref 03 §1 **Normalise in every clip intermediate** file (CFR, rate R) or `edited/NN-slug.mp4`. The decoded window (lead included) snaps to boundary frames k0 and k1 (ref 03 §2 **Frame grid**): `ffmpeg -nostdin -v error -ss T(k0) -i in -map 0:v:0 -an -vf scale=64:36:flags=area,format=gray -frames:v <k1 − k0> -f rawvideo -pix_fmt gray -`; decoded frame j is frame k0 + j of the file.
   - A VFR input (average rate > 1% off the stream rate) or a grid R other than the stream rate gets `fps=R` before the scale, with a `retimed` warning: index frames of the CFR intermediate instead.
   - d[j] = mean |F[j] − F[j−1]|, d[0] = 0. typical = max(1, sorted[n//2]) of the d ≥ 0.5 among ±N neighbours (from j = 1); 1 if fewer than 4.
   - Hard hit: d ≥ 12 and ≥ 4×typical, tested first. Soft hit: d ≥ 10, ≥ 8×typical, ≥ 4× the largest neighbour. So a large same-angle punch-in is a hard hit; only a smaller one (10 ≤ d < 12 among quiet neighbours) is soft. Both are cuts.
   - Consecutive hits merge (max change; soft only if all are). > M frames = `fast`; picture back within K frames (MAD < 0.4×change) = `flash`; the rest are cuts.
   - Blank bridge (ours): a cut followed by the next event within K frames, with every frame shown between them flat (64×36 grey std ≤ 4), is a `flash`; the next event keeps its own class (a cut into a new shot, a `flash` when the old shot returns).
   - N, M, K = 12, 3, 4 × r, r = max(1, round(R/30)) (scaling not in HF).
   - Reframe: detect on [start − 0.5 s, end + 0.5 s] (a window's first frame has no d; events in the lead are dropped); reset and snap at cuts and at every splice, never at `flash`/`fast`.
   - Rendered edits: → ref 05 §1 **Events match the plan**.
   - Implemented by `scripts/cuts.py` (`reset_frames` = hard and soft cut frames; frame 0 = the frame at `--start`, t in absolute seconds). It keeps every decoded frame in memory (2.3 KB each): detect on clip windows, not whole long sources.
   Why: `scene>0.3` split a flash into 2 cuts and missed 20% punch-ins (this detector: d ≥ 19.6); a histogram detector logged 172 "cuts" on ref 1 (~27 real). At 60 fps, r = 1 read a 55% tint as a cut; r = 2 read `flash`. Without `fps=R` a VFR join put the cut at 1.983 s, not 2.000 s. Tested: a 20% punch-in (crop 0.8) read d 21.5 = hard; a 10% one on moving footage d 10.34 = soft; 8-9% d 8.6-9.5 and 6% d 6.8 = no event. A dip through 2 white frames into a different shot read as two hard cuts 2 frames apart (d 127.8, 126.9) because the first shot never returns; the bridge makes it a flash + one cut, so the reframe resets once, on the new shot.
   HF: packages/cli/src/measure/cuts.ts:7-19,37-90; packages/cli/src/commands/measure/cuts.ts:31-36
2. **Accent timing.** Refines ref 01 §5 tint flash (old: "1-frame attack, 0.25-0.4 s decay", no curve).
   - Accents are output frame indices. Cause frame = the cut, the visible impact, or `k(remap(word.start))` (ref 03 §2 **Frame grid**, **One clock**).
   - Tint flash, red wash: full peak ON the cause frame, then peak·(1 − u)² over ref 01's length (tint 0.25-0.4 s, red wash 0.5 s). White flash → ref 04 §2 **White flash = wash + exposure push**.
   - Whip: the switch frame (i = n//2, the first p ≥ 0.5) is the cut frame. Stickers: 0-45 ms after their cause (0-2 frames at 60 fps).
   - ≥ 1 s between any two flash, tint or wash accents.
   - Speech and picture are the clock, never a beat. SFX: → ref 03 §3 **SFX on the hit**.
   Why: an eased or late hit reads as lag.
   HF: .agents/skills/motion-doctrine/SKILL.md:88; skills/hyperframes/references/film.md:34; skills/hyperframes/references/sound.md:14; skills/media-use/references/media-treatment-recipes.md:925-926
3. **White flash = wash + exposure push.** Refines ref 01 §5 White flash (old: "1-2 frames of overexposure (luma > 230), decaying over 0.3-0.4 s").
   - Cause frame and the next: (255,253,250) wash at 0.92 over the pushed picture, then 0.92·(1 − u)³ over 0.18 s.
   - Push: min(1, x·2^EV), x in 0-1, EV = EV0·(1 − u)² over 0.35 s.
   - EV0 = 0.72, lowered per shot until the third frame reads luma ≤ 230 (ref 01: 1-2 frames); at shot luma ≥ 180 use 0.
   - Both sit above the graded footage (after the grade), so the grade diagnosis and `qc/NN/grade.mp4` never see them.
   - Tested at EV0 0.72, frames > 230: 2 (black, testsrc2), 3 (mid grey), 5 (luma 160), 12 (209). Passing needs EV0 ≤ 0.3 at 150, ≤ 0.08 at 170. Wash alone: 233 on black.
   Why: a flat white layer lifts blacks; a push brightens the picture.
   HF: skills/media-use/references/media-treatment-recipes.md:904-926; registry/blocks/editorial-flash-overlay/editorial-flash-overlay.html:23,101,114; packages/core/src/runtime/colorGrading.ts:1224
4. **Velocity-matched whip.** Refines ref 01 §5 whip (old: "2-6 frames (at 60 fps) of horizontal or vertical streak blur plus a ghost of the next shot").
   - n = 2-6 frames at 60 fps (1-3 at 30). Frame i: u = (i + 0.5)/n, p = inOutQuad(u).
   - A leaves by 1.5p·W, B arrives from 1.5(1 − p)·W (edge-replicate); out = (1 − p)A + pB (the ghost). Both move 1.5 W per unit p: speeds match.
   - Box blur on the travel axis only: length = round(⅔ · 0.75 W·(p(u + 1/n) − p(u − 1/n))), u clamped to 0-1 (240° shutter). At 1080 W, n = 4: 152/371/371/152 px; n = 2-6: 68-480 px.
   - Consecutive whips keep one direction (default: content exits left) unless on-screen motion reverses.
   Why: speed mismatch or ping-pong reads as an error; cross-axis blur smears faces.
   HF: packages/shader-transitions/src/shaders/registry.ts:43-55; docs/guides/motion-blur.mdx:30; .agents/skills/motion-doctrine/SKILL.md:53,64-65
5. **Face carried across jump cuts.** Refines ref 02 rule 15 (old: "vary the crop scale by 4-10% between them", no anchor).
   - Anchor the scale change on the face: origin_B = face_B − p_A·crop_B/canvas (p_A: face centre on canvas at cut − 1), clamped to the source.
   - Gate: face-centre shift per axis ≤ 0.625% W (6.75 px at 1080 W) from cut − 1 to cut; if the clamp breaks it, keep ref 01 §4 framing.
   Why: a jump that also moves the face makes the eyes search.
   HF: .agents/skills/motion-doctrine/SKILL.md:77-78; .agents/skills/motion-doctrine/scripts/seam-gate.mjs:43-44,263 (12 px at 1920)
6. **Push-ins on a parent; plate covers the canvas.**
   - Tracking keys stay on the footage layer; ref 01's 3-5% push and the freeze zoom go on a parent (Python: M_push∘M_track).
   - Face gate (SKILL step 4, bbox + 5%) on the composed transform at every ref 05 §1 **Frames by index** sample. Refines ref 02 rule 14 (old: "checked in QC on 1 fps samples").
   - A translated plate needs scale ≥ max_t(1 + 2|dx|/W, 1 + 2|dy|/H) × 1.02 (24 px at 1080 W: 1.0653).
   - FAIL if a 2-px border band of the ungraded `raw/NN-slug.mp4` is > 90% luma < 8 (bars, exposed edge). Graded frames false-fail: ref 01 grade + `vignette=PI/5` left the top/bottom bands of a clean RGB-24 shot 100% < 8.
   - Per-shot framing medians: → ref 05 §1 **Framing by shot medians**.
   Why: a push or shift on the tracked layer cuts the face or shows a black edge.
   HF: skills/hyperframes/references/motion.md:57; registry/components/camera-shake/camera-shake.html:690-730

### Optional
- **Active speaker from lip motion** (2+ faces, no diarization). Refines ref 01 §4 (old: "the active speaker is chosen from mouth motion or diarization").
  - Per ≥ 2 s window and face: mouth ROI [x + 0.2w, y + 0.62h, 0.6w, 0.38h] of the median face box, grey, 160 px wide; motion = per-frame MAD; speech = |Δ per-frame RMS| (16 kHz).
  - Pearson r at lags −125..+45 ms (HF sync band). Speaker = top r if ≥ 0.3 and ≥ 0.1 over the next face (threshold ours); else keep the last speaker or go wide.
  - The same mouth signal drives the lip-sync check in ref 05 §1 **A/V offset**.
  Why: the crop follows the listener when two faces share a shot.
  HF: packages/cli/src/measure/sync.ts:53-84,119-124; packages/cli/src/measure/person.ts:22-23,509-514
- **Face detection fallbacks.**
  - Detect on a ≤ 960 px wide copy, min face 4% H. Drop faces inside pasted-in pictures (poster, photo; not a live facecam).
  - Frontal miss: profile detector (and its mirror, not in HF), then hold the last box ≤ 0.5 s (threshold ours), then widen.
  - Models: YuNet needs its .onnx (no cv2 wheel ships one); cv2 5.0.0 has no `CascadeClassifier` or Haar XML. Gate: a face model loads before reframing; `scripts/preflight.py` should report its path (it does not check one yet).
  Why: 3/4 angles drop out of frontal detectors; pictured faces steal the crop.
  HF: packages/cli/src/measure/face.ts:14-17,102-123; packages/cli/src/measure/person.ts:467-474
- **Meme-freeze timing** (only when the ending fits, per the Defaults).
  - Push 2-4 frames (60 fps) into the hit, power3.in, radial blur: 12 taps along uv − 0.5, strength 0.08p, equal on R, G and B.
  - Freeze (hard set): `trim=end_frame=<hit+1>,tpad=stop_mode=clone:stop_duration=1.5` (ref 01: 1.2-1.8 s); at most one flash.
  - 💀 enters 0.3 s after the hit, scale 1.18 → 1 over 0.24 s, power2.out.
  Why: an eased freeze softens the hit; extra flashes strobe.
  HF: registry/blocks/beat-freeze-cut/beat-freeze-cut.html:690-702,724-748; packages/shader-transitions/src/shaders/registry.ts:107-124; registry/blocks/freeze-frame-dressing/freeze-frame-dressing.html:99-104

## 3. Grade and colour pipeline, grade gates
Scope: the tagged BT.709 clip intermediate → graded footage, and the grade gate.

### Adopted (default)
1. **Grade and gate the footage only.** Refines ref 01 §7 QC gate (old: "sample 1 frame per second from source and output") and ref 01 Editing tool / SKILL path A (old: "grade on an adjustment layer").
   - Grade before captions and overlays (`[v]<grade>[g];[g]ass=...`). EffectCraft: in a canvas-size footage precomp (adjustment layer above the tracked source), under the accent, caption and sticker layers (order → ref 04 §1 **Event mechanics**).
   - Render `qc/NN/grade.mp4` full-length in both editors: same chain, no ASS or overlays (EffectCraft: the footage precomp rendered alone, untested). The caption gates reuse it.
   - Gate `raw/NN-slug.mp4` vs `qc/NN/grade.mp4`. Fallback `edited/NN-slug.mp4`: mask caption and sticker block boxes (→ ref 04 §1 **Face avoidance per window**) + 8 px; skip accents ±0.5 s and the freeze. A masked sample counts only where its whole source area is unmasked (→ **One metric definition**).
   - Samples: frames showing t = i + 0.5 s (i < ⌊D⌋), indexed per ref 05 §1 **Frames by index**, decoded with `scale=in_color_matrix=bt709:in_range=tv,format=rgb24`. Under 8 usable samples the step halves to 0.5 s once, then the gate refuses (exit 2).
   - Inputs: same canvas size and fps (a grade-only render also the same frames ±1); BT.709 tv or untagged (read as BT.709 tv with a warning); another matrix or pc range is refused (exit 2).
   - Implemented by `scripts/grade_gate.py` (`--mask`, `--exclude`, `--faces`, `--waive`). A file in `edited/` (or `--edited`) needs `--mask` and `--exclude`; an empty list states "nothing to mask". The reframe step writes `--faces` as `{fps, boxes: [[frame, x0, y0, x1, y1] | [frame, null]]}` in canvas px (null ends a track).
   Why: captions alone gave sharpness x7.2 (luma, sat x1.00) on an ungraded clip. Tested: with the whole-area rule, a masked ungraded captioned clip read luma/sat/sharp x0.97-1.03; unmasked, sharpness passed at x1.4.
   HF: docs/prompting/color-grading.mdx:10-11; packages/cli/src/media-use/lib/grade-analyzer.mjs:215-217
2. **One metric definition** for the grade gate and the repo-only reference tool `analysis/tools/extract_ref.py`.
   - luma = mean HSV V, sat = median HSV S, on `cv2.resize(rgb, (90, 160))` (RGB frames, `cv2.COLOR_RGB2HSV`; the numbers equal the BGR version's).
   - gray resized to 720 px high (`INTER_AREA`): sharp = Laplacian variance (CV_64F), contrast = std, p2 = 2nd percentile.
   - ratio = out/src, 1 when both are under the floor (luma 1, contrast 1, sat 2.55).
   - With a mask, a reduced-size sample counts only when its whole source area is unmasked (the `INTER_AREA`-resized mask reads 1), and the 720 px Laplacian mask is also eroded by 1 px.
   - Implemented by `metrics()` in `scripts/grade_gate.py`.
   - Refines ref 01 §0.3 (old: "Laplacian variance (720p)", no method). Port it to extract_ref.py:44-45 (now mean S, native-size Laplacian, cv2 BGR frames): import `grade_gate.metrics`, feed it RGB frames decoded by ffmpeg, and re-measure ref 01 (→ ref 05 §1 **Reference studies per frame**).
   Why: native vs 720 px Laplacian differed x6.8 on one soft frame (5.6 vs 38.2). Tested: at 1080×1440 one 90×160 cell spans 12×9 source px, so a box grown by 8 px still bled caption pixels into neighbouring samples through the resize, and the 3×3 Laplacian reached across the mask edge.
   HF: packages/cli/src/measure/look.ts:7,26-43; packages/cli/src/measure/media.ts:282-284
3. **Name the matrix at every RGB hop.** Refines ref 01 §7 chain and SKILL path B (old: no matrix named). Input is tagged BT.709 tv (→ ref 03 §1 **Normalise in every clip intermediate**); tags at the encode → ref 03 §4 **BT.709 from the head of the graph**.
   - YUV filters first (`lutyuv`, `eq`, `hqdn3d`, `unsharp`), then one RGB stage: `scale=in_color_matrix=bt709:in_range=tv,format=gbrp,<curves,vibrance,colorbalance,glow,vignette>,scale=out_color_matrix=bt709:out_range=tv:flags=accurate_rnd+full_chroma_int,format=yuv420p`.
   - Path B Python frames: ffmpeg-decode with `scale=in_color_matrix=bt709:in_range=tv,format=bgr24`, never `cv2.VideoCapture` (analysis only); encode piped frames with `scale=out_color_matrix=bt709:out_range=tv:flags=accurate_rnd+full_chroma_int,format=yuv420p`.
   - `color=` sources (flash, wash, tint plates): `format=gbrp,scale=out_color_matrix=bt709:out_range=tv:flags=accurate_rnd+full_chroma_int,format=yuv420p`, never `format=yuv420p` alone.
   - The exit names only matrix and range: libx264 still needs `-x264-params colorprim=bt709:transfer=bt709:colormatrix=bt709` (→ ref 03 §4 **BT.709 from the head of the graph**), and `colr` comes from the mux re-tag.
   Why: max |dRGB| decoded as BT.709: ref 01's chain on untagged input 37 (encoded yuv444p), with `-pix_fmt yuv420p` 40, explicit hops 4. RGB → yuv420p exit: no matrix 33-34, named 3, named + flags 1-3 (no change on flat patches). A `color=` source alone 28-33 (`setparams` first did not help), named 2-4. Decode: cv2 23 (6-patch card) and 35 (palette card), ffmpeg 4.
   HF: packages/engine/src/utils/sdrCaptureColor.ts:1-5
4. **HDR sources.** Grade and gate only the SDR copy: → ref 03 §1 **SDR at download** and **HDR fallback**.
5. **Diagnose per camera group, correct, then one look.** Refines ref 01 §7 (old: one "Reference ffmpeg chain" for all).
   - Per shot, median of 3 index-sampled frames of `format=yuv444p,signalstats,metadata=print:file=-` (YLOW/YHIGH = 10th/90th pct):
     - dark: YAVG < 71.4 and YHIGH < 165.75; high-key: YAVG > 183.6 and YLOW > 76.5;
     - flat: (YHIGH − YLOW)/255 < 0.35; clip: YLOW ≤ 16 or YHIGH ≥ 235.
   - Groups in shot order: join the first group within |dU|, |dV| ≤ 4, |dY| ≤ 15 (threshold ours, initial); per-group values by `sendcmd` on `eq@g`, `lutyuv@c`, `curves@k`.
   - dark: gain to mean V 145-170 (night footage: the Defaults +10% only). flat: steeper S until contrast ≥ x1.10.
   - Low headroom (> 3% of pixels at max(R,G,B) ≥ 228, which a x1.10 gain clips): no `eq` brightness or gain; RGB `curves=interp=pchip:all='0/0 0.5/M 1/1'`, M up from 0.62 until luma ≥ x1.10.
   - Then one look.
   Why: on a bright source (16.6% at ≥ 228; YHIGH headroom 1.135 missed it) ref 01's eq gave luma x1.105 with +16.6 pp clip; a x1.10 gain x1.077, +16.6 pp; pchip M 0.62 x1.054, M 0.70 x1.104, +0.1 pp. A natural spline on a steep S hit 255 at input 208. Tested: ref 01's chain assumes headroom. On a saturated plate (testsrc2, mean V 180) it pushed 28.3 pp of pixels to max(R,G,B) ≥ 250 and failed the clip gate; on a dull, soft plate (mean V 135) it passed every gate (luma x1.26, sat x1.45, sharp x3.66, contrast x1.09, p2 −3, warm +7, clip +0.0 pp).
   HF: packages/cli/src/media-use/lib/grade-analyzer.mjs:116-129,151-153; packages/core/src/colorGroups.ts:1-6
6. **Cast check on neutral pixels.** Refines ref 01 §7 (old: constant `colorbalance=rm=0.02:bm=-0.02`).
   - Per group: pixels outside the face box x1.5 with HSV S < 0.30 and 0.2 < V < 0.9; skip under 5% of the frame.
   - BT.709 dU, dV of them: warmth = (dV − dU)/128, cast = dU + dV.
   - |warmth| ≥ 0.08 or |cast| ≥ 10: prepend `lutyuv=u='val+a':v='val+b'` (a = −dU/2, b = −dV/2; `val+-6.2` parses as `val-6.2`) and drop ref 01's warm push; else keep it unless face hue ≥ 22°.
   Why: a 31% skin block put whole-frame warmth at +0.107 on grey (false) and +0.013 on a cool cast (neutrals −0.135); S < 0.15 kept no neutrals. Fix: −0.135 → −0.063.
   HF: packages/cli/src/media-use/lib/grade-analyzer.mjs:131-138; skills/media-use/references/media-treatment-recipes.md:138
7. **Threshold the glow, in RGB.** Refines ref 01 §7 (old: whole-frame `gblur=sigma=20` screen, on YUV as written).
   - In the RGB stage (W:H = canvas): `split[a][b];[b]scale=iw/2:ih/2,lutrgb=r='val*gt(val,127)':g='val*gt(val,127)':b='val*gt(val,127)',gblur=sigma=10,scale=W:H[g];[a][g]blend=all_mode=screen:all_opacity=0.15`, then the vignette.
   - lutrgb thresholds per channel (HF: BT.601 luma); half-res sigma 10 ≈ ref 01's sigma 20.
   - EffectCraft: Glow threshold ~50% (unverified: on a card, 20-40% greys must stay +0).
   Why: ref 01's glow moved neutral U/V 128 → 137 (magenta, even on black); unthresholded RGB lifted 20%/40% grey +6/+8; thresholded +0 (50% grey +9).
   HF: packages/core/src/runtime/colorGrading.ts:1484-1485,2358-2369
8. **Gate haze, clipping and skin**, on top of the Defaults luma/sat/sharp ratios. Refines ref 01 §7 (old: "no lifted-black haze", "skin hue stays 10-25°", unmeasured).
   - contrast ≥ x1.00 (target 1.10-1.15); p2 ≤ source + 6.
   - Pixels with max(R,G,B) ≥ 250 rise ≤ 1 pp in the face box, ≤ 3 pp overall; mean(R − B) rises ≤ 12.
   - Skin (inner 60% of the face box): saturation-weighted circular-mean hue 10-25°, drift ≤ 5°; dark skin (median V < 110) keeps ≥ 0.98x face std and median S.
   - All thresholds initial (HF's 12 is still "to be calibrated"); calibrate the clip gate on real clips (untested: every threshold here is measured on synthetic plates only).
   - Implemented by `scripts/grade_gate.py`: each gate `{ok, measured, limit, waived}`; face gates are null without `--faces`; `--waive` only for request overrides.
   Why: a 50% screen glow passed luma (x1.116) and sharpness (x2.41) with p2 +10; Y ≥ 235 saw 0% of a 16.6% channel clip. Re-tested, the glow's p2 rise depends on the plate and the glow width: a full-res `gblur=sigma=20` screen at 50% on a dull plate gave only p2 +4/+5; a wider unthresholded glow (about sigma 60 at full res) at 50% over ref 01's chain gave p2 +9 and failed only p2. Contrast never caught haze (x1.06-1.13), so p2 is the haze gate in practice.
   HF: packages/cli/src/measure/look.ts:79-86; packages/studio/src/components/editor/colorGradingFrameAnalysis.ts:173-191; docs/prompting/color-grading.mdx:104
9. **One sheet, measured log.** Adds the grade to SKILL step 7's review (other sheets → ref 05 §1 **Review sheets**).
   - `qc/NN/grade_sheet.jpg`: a row per group (≤ 4): source | graded at 0.25/0.5/0.75 of the clip + a 1:1 face crop; read only it. Not built by a script yet.
   - Log `grade NN luma x1.13 sat x1.31 sharp x1.62 contrast x1.12 p2 +3 warm +4 clip +0.4pp skin 18° frames=24` (`skin -` without a face; ` FAIL gate,gate` appended on failure); `grade_gate.py` writes it to stderr and the JSON `log`.
   - A stage whose toggle moves mean |d| < 0.5/255 did nothing: fix or drop it (a grade-step check, not in the gate).
   Why: command success is not a rendered look; glow is judged at 1:1.
   HF: skills/media-use/references/media-treatments.md:137-147,199-201

### Optional
- **Bake the colour stage to a .cube** when both editors must match.
  - numpy grade → `LUT_3D_SIZE 33`, `DOMAIN_MIN 0 0 0`, `DOMAIN_MAX 1 1 1`, red fastest, `%.6f`; write it per ref 05 §2 **Crash-safe writes**.
  - Apply `format=gbrp16le,lut3d=file=grade.cube:interp=tetrahedral` in the RGB stage; unsharp, glow and vignette stay outside.
  - Tests: identity rows ≤ 1e-6; lut3d vs numpy (16-bit RGB): identity 0, clipped look ≤ 3/255.
  - Skin gate fails → vibrance weight (1 − 0.72·sat)·mix(1, 0.55, skin). EffectCraft LUT parity unproven.
  Why: one function, same numbers in both paths.
  HF: packages/core/src/colorGradingBake.ts:96-121,408-435; packages/core/src/colorGradingBake.test.ts:56-119

## Not adopted (and why)
- §1: Karaoke active-word highlight as the baseline at every energy level, and grey-to-ink per-word recolour (HF: skills/media-use/audio/references/captions/motion.md:15; registry/components/caption-pill-karaoke/caption-pill-karaoke.html:148-151). Why not: ref 01 §3 Reveal: "No bounce and no karaoke recolour"; it is also on ref 02's NOT ADOPTED list.
- §1: Mandatory audio-reactive caption scale/glow over music (HF: skills/media-use/audio/references/captions/motion.md:21-23). Why not: ref 01 §3 Reveal (3-frame entrance, "No bounce") and §5 bans "beat shake, per-word zoom punches".
- §1: Highlight styles cycled every 2-4 groups, and overshoot/bounce on emotional keywords (HF: skills/media-use/audio/references/captions/motion.md:9-13,77; skills/media-use/audio/references/captions/authoring.md:41). Why not: ref 01 §3 specifies one caption look and "No bounce"; HF's own catalog asks for one identity per composition (HF: docs/prompting/captions-catalog.mdx:92).
- §1: Seeded-random accent colour on 40-45% of non-function words, and accent words at 1.2x size (HF: registry/components/caption-neon-accent/caption-neon-accent.html:286-299,447-448; registry/components/caption-emoji-pop/caption-emoji-pop.html:270-274). Why not: ref 01 §3 Colour: 1-3 semantic keywords per chunk, chosen by meaning; size is fixed by the cap height.
- §1: A text-sized 30-40% scrim over footage brighter than 60, and a blend mode chosen by backdrop brightness (HF: skills/hyperframes/references/captions.md:38). Why not: ref 01 §3 says "no background box"; contrast fixes stay inside the look (→ ref 04 §1 **Legibility gate**).
- §1: A contrast fix that steps the fill colour toward white or black (suggestedColor; HF: skills/hyperframes-cli/references/lint-validate-inspect.md:88; packages/cli/src/commands/contrast-bg.ts:47-50). Why not: ref 01 §3 palette colours carry meaning; we move the block or deepen that chunk's shadow (→ ref 04 §1 **Legibility gate**).
- §1: First caption 0.1-0.3 s in, because one at 0 s "looks pre-existing" (HF: skills/hyperframes/references/captions.md:20). Why not: ref 01 §2 puts the first caption on screen by t ≤ 0.1 s; ref 02 starts the clip 0.05 s before the hook word, so word 1 appears at frame 2 (60 fps).
- §1: The final caption clears before the video ends; the last line holds ≥ 2 s (HF: docs/guides/captions-and-recuts.mdx:135; skills/hyperframes/references/motion.md:22; packages/cli/src/utils/craftAudit.ts:17). Why not: the SKILL Defaults Ending row and ref 01 §5: hard cut right after the payoff, with the payoff chunk still on screen (ref 02: end = last word + 0.15 s).
- §1: Exit tweens (fade or blur-out 0.12-0.25 s, exits 40-50% shorter than entrances) and group end = last word + 0.5 s, 0.05 s before the next group (HF: skills/hyperframes/references/captions.md:24; skills/hyperframes/references/motion.md:12,22; registry/components/caption-highlight/caption-highlight.html:183). Why not: ref 01 §3: "The exit is a hard cut"; a chunk holds until the next one starts, or 0.6 s after its last word.
- §1: Portrait captions about 600-700 px from the bottom; burned-in captions at the bottom of the UI band (HF: skills/hyperframes/references/captions.md:35; skills/hyperframes/references/types/vertical.md:7). Why not: ref 01 §3 Position: 50% H, or 72% H when off the face; only the 168-1330 px band is adopted (→ ref 04 §1 **9:16 UI band**).
- §1: Group sizes of 3-5 / 4-6 words and pause breaks at 0.10-0.15 s (HF: skills/hyperframes/references/captions.md:19; registry/components/caption-neon-accent/caption-neon-accent.html:135). Why not: ref 01 §3 Chunking: 2-4 words (max 6), breaks at gaps > 0.25 s; HF's tiers survive only as the Optional ref 04 §1 **Speech-rate chunk cap**.
- §1: Shrink-to-fit font loops: neon-accent's local fitFontSize 88 → 62 px in 2 px steps (floor 0.45x base); runtime fitTextFontSize 78 → 42 px (HF: registry/components/caption-neon-accent/caption-neon-accent.html:235-244,382-385; skills/hyperframes/references/captions.md:32). Why not: ref 01 §3 fixes cap height at 3.3% H. Re-chunk instead, as HF's own types/vertical.md:18 says ("cut words, never shrink"); only a lone over-wide word scales, floor 0.85x.
- §1: An entrance that completes on the spoken word: lead = min(7/30 s, gap to the previous group), plus a 0.05 s colour-fade lead (HF: registry/components/caption-neon-accent/caption-neon-accent.html:466-471; registry/components/caption-pill-karaoke/caption-pill-karaoke.html:151). Why not: ref 01 §3 Reveal measured each word appearing at word.start − 0-2 frames; a 7/30 s lead is up to 14 frames at 60 fps.
- §1: Starting ASS fades 1 frame early because `\alpha&HFF&` ink shows 1-2 frames after t0 (proposed during the study). Why not: ref 04 §1 **Event mechanics** starts the entrance at 1/3 opacity on appear_f (33-45% on that frame); one more frame early would show each word 2 frames before word.start, against ref 01's "word.start - 1 frame".
- §1: Layered same-colour glow (4/10/20/40 px at 1.0/0.9/0.7/0.4) plus dark drop shadows 0 8px 16px and 0 16px 40px (HF: registry/components/caption-neon-accent/caption-neon-accent.html:396-427). Why not: ref 01 §3 specifies one same-colour glow (about 20 px, about 70%) and a soft black shadow at offset 0.
- §1: Matted "embed" words set behind the speaker (HF: .agents/skills/captions-overlay/SKILL.md:20-32; skills/hyperframes/references/captions.md:41-45). Why not: not part of ref 01's measured style (captions sit in front), and it needs a matting model outside requirements.txt.
- §1: Caption presence and timing on our renders from caption-band frame differences (default threshold 5 grey levels, plain |edited − raw|), or from an affine ring-fit residual (HF: skills/reverse-any-video/references/match.md:8; packages/cli/src/measure/events.ts:229; the residual was proposed during the study). Why not: built for third-party references, and ref 05 §1 **Reference studies per frame** keeps band switches for those. On our renders a +10% luma grade alone moved |graded − raw| 7-18 levels in caption-free boxes. The ring fit separated presence (49-60 vs 1.0-1.2) but not a held chunk under the next chunk's box (45.0 vs 48.9). → ref 04 §1 **Presence, stale and sync gate** is the one method.
- §2: Flash rise of 0.035-0.055 s (HF: skills/media-use/references/media-treatment-recipes.md:923). Why not: ref 01 §5: tint "1-frame attack", white flash "1-2 frames of overexposure"; HF film.md:34 also makes a hit a 0 ms set.
- §2: "Never saturated red" flashes (HF: skills/media-use/references/media-treatment-recipes.md:925). Why not: ref 01 §5 Red fail wash: "red-pink overlay at 65%, fading to 0 over 0.5 s".
- §2: A fixed +0.72 EV push start on every shot (HF: skills/media-use/references/media-treatment-recipes.md:916-917). Why not: at ref 01's graded luma 150-170 it held luma > 230 for 4-6 frames, against ref 01 §5's "1-2 frames of overexposure"; ref 04 §2 **White flash = wash + exposure push** lowers EV0 per shot.
- §2: Recovery examples of 0.24-0.28 s (HF: skills/media-use/references/media-treatment-recipes.md:904-913; registry/blocks/beat-freeze-cut/beat-freeze-cut.html:746; registry/blocks/freeze-frame-dressing/freeze-frame-dressing.html:97). Why not: shorter than ref 01 §5's white flash "decaying over 0.3-0.4 s". We use 0.35 s, inside HF's own 0.24-0.38 s range (HF: media-treatment-recipes.md:923-924).
- §2: Outgoing pre-ramp (+0.82 EV, scale 1.035 over 0.12 s from cut − 0.16 s) and incoming scale 1.1 → 1 over 0.42 s (HF: skills/media-use/references/media-treatment-recipes.md:887-903). Why not: ref 01 §5's white flash has no pre-roll, and the settle is a zoom inside a shot (ref 01 §4: "no zoom changes inside a shot").
- §2: Whip length 0.13-0.3 s and the 0.55 s strip whip (HF: skills/hyperframes/references/motion.md:39; registry/components/whip-pan-cut/whip-pan-cut.html:53). Why not: ref 01 §5: whip "2-6 frames (at 60 fps)".
- §2: "Never a crossfade" and the zero-overlap seam check (HF: .agents/skills/motion-doctrine/SKILL.md:81; .agents/skills/motion-doctrine/scripts/seam-gate.mjs:453-468). Why not: ref 01 §5's whip includes "a ghost of the next shot"; ref 04 §2 **Velocity-matched whip** mixes A and B by p.
- §2: Whip blur caps: 16 px peak stdDeviation, 15-20 px full-frame, 18-20 px on a full-frame surface (HF: registry/components/whip-pan-cut/whip-pan-cut.html:397-399; skills/hyperframes/references/motion.md:7; .agents/skills/cut-the-curve/SKILL.md:48). Why not: they are sized for UI cards and text in 0.3-0.6 s moves ("readability ceiling", whip-pan-cut.html:397-398). A 2-6 frame footage whip travels 1.5 W, so ref 04 §2 **Velocity-matched whip** sizes blur with HF's 240° shutter (HF: docs/guides/motion-blur.mdx:30): 68-480 px at 1080 W.
- §2: Dip cut: the outgoing frame darkened ~40% for 3 frames before a hard cut (HF: skills/hyperframes/references/motion.md:41). Why not: ref 01 §5: "Every other cut is a hard cut"; ref 02 rule 15's 4-10% scale change already marks same-camera jump cuts.
- §2: Transition mix: at most a third of seams are hard cuts, 3-5 transition kinds per film; 2-3 repeated inter-scene transitions (HF: skills/hyperframes/references/motion.md:30; .agents/skills/motion-doctrine/SKILL.md:155-156). Why not: ref 01 §5 wins: "1 accent per 6-8 s, and never more than 40% of cuts. Every other cut is a hard cut."
- §2: Talking-head punch-ins on emphasis, the 11% / 1.2 s power2.inOut camera move, and one slow push 1.0 → 1.08 on calm footage (HF: skills/hyperframes/references/types/vertical.md:19; registry/components/yt-camera-move/yt-camera-move.html:113-133; skills/hyperframes/references/film.md:35). Why not: ref 01 §5 bans "per-word zoom punches" and keeps the Mild push-in to "about 3-5% scale drift over a shot", "on long holds only"; ref 01 §4 "no zoom changes inside a shot", and ref 02's NOT ADOPTED punch-ins every 3-4 s. Only ref 01's 3-5% push stays (ref 04 §2 **Push-ins on a parent; plate covers the canvas**).
- §2: Beat-led cutting, beat-snapped accents ("cut on the beat", one clip per strong beat) and beat-trust gating (HF: skills/hyperframes/references/film.md:33-35; skills/hyperframes/references/motion.md:13; packages/core/src/beats/beatDetection.ts:45). Why not: clips are narrated and HF's sound.md:14 makes the voice the clock; ref 01 §8 pacing follows speech, ref 01 §5 bans beat shake, and a beat tracker is outside requirements.txt.
- §2: Stretch-cut connector after the freeze (scaleX 1.35, scaleY 0.92, blur 14 px, brightness 1.35), paper/tape dressing, and the cinematic-zoom R/G/B split 1.06/1/0.94 (HF: registry/blocks/beat-freeze-cut/beat-freeze-cut.html:762-790; registry/blocks/freeze-frame-dressing/freeze-frame-dressing.html:96-115; packages/shader-transitions/src/shaders/registry.ts:114-116). Why not: ref 01 §5's meme freeze is "2-4 frame zoom/radial blur into a freeze", a "warm/sepia high-contrast meme grade", "one 💀 PNG", "hold for 1.2-1.8 s, then hard end". Only the tape's entrance timing is reused, for the 💀 (ref 04 §2 **Meme-freeze timing**).
- §2: Light-leak transition and a two-sided flash through white (HF: registry/blocks/light-leak/light-leak.html:310; packages/shader-transitions/src/shaders/registry.ts:202-210). Why not: not among ref 01 §5's accent types; ref 01's white flash is overexposure on the hit frames (ref 04 §2 **White flash = wash + exposure push**), not a dip through white.
- §2: Face-size bands (pass ≥ 0.25 H, fail < 0.06 H), "subject = largest face" and the missing-face note on the last sampled frame (HF: packages/cli/src/measure/face.ts:7-9,140-174). Why not: these grade a regenerated presenter's likeness (face.ts:1-3). Ref 01 §4 sets the close face at 24% H (20-30%) and tracks the active speaker; ref 05 §1 **Framing by shot medians** covers the last shot.
- §2: Roll, pitch and yaw terms of the camera-shake overscan solver (HF: registry/components/camera-shake/camera-shake.html:718-727). Why not: ref 01 §5 bans "beat shake", and no clip accent rotates the plate, so ref 04 §2 **Push-ins on a parent; plate covers the canvas** keeps only the translation term.
- §2: Seam-gate "moving at the boundary" check: an exit or entry slower than 15 px/s fails (HF: .agents/skills/motion-doctrine/scripts/seam-gate.mjs:40,423-427). Why not: ref 01 §4 wants a locked camera ("Reframe with cuts, not fast pans"), so both sides of a hard cut are usually static. Only the carrier check is kept (ref 04 §2 **Face carried across jump cuts**).
- §3: Natural Portrait / Product Polish bounded ranges as grade amounts: vibrance 0-0.06, saturation −0.04-0.06, contrast −0.05-0.08, exposure −0.06-0.14 (HF: skills/media-use/references/media-treatment-recipes.md:40-52). Why not: ref 01 §7 targets win (mean luma 145-170, median sat 85-105, S-curve +10-15%), and these ranges cannot reach them.
- §3: Analyzer correction amounts: exposure (0.32 − avg)·1.2 EV, contrast (0.35 − spread)·0.4, temperature −0.25·warmth, tint −cast/512 (HF: packages/cli/src/media-use/lib/grade-analyzer.mjs:121-138,153). Why not: too gentle for ref 01's targets. Only HF's diagnosis thresholds are adopted (ref 04 §3 **Diagnose per camera group, correct, then one look**); the gate loop sets the amounts.
- §3: A blacks = +0.08·shadowClipRisk suggestion (HF: packages/cli/src/media-use/lib/grade-analyzer.mjs:159). Why not: under HF's own black-point math (HF: packages/core/src/colorGradingBake.ts:103-106) a positive blacks value raises the black point and darkens clipped shadows further.
- §3: "If the treatment is not clearly better, keep the source unchanged" (HF: skills/media-use/references/media-treatments.md:198). Why not: the SKILL Defaults Grade row requires a grade that measurably beats the source; ref 01 §7 raises the failing parameter and re-renders instead of reverting.
- §3: Replacing the +10% luma gate with "no new clipping" on bright sources (proposed during the study, built on HF's headroom/clip-risk logic). Why not: the Defaults table is fixed, and it is not needed: a pchip mid lift reached luma x1.104 with +0.1 pp clip on a source where ref 01's eq clipped +16.6 pp.
- §3: Additive bloom, color += bloom·amount, one-click 0.55, max 3 (HF: packages/core/src/runtime/colorGrading.ts:1376; packages/core/src/colorGrading.ts:853,929). Why not: ref 01 §7 polish is a blurred screen blend at 12-18%. Only HF's luma threshold, half-res pass and RGB compositing are adopted (ref 04 §3 **Threshold the glow, in RGB**).
- §3: The UI Fidelity default payload "none" (no grade) for screen recordings and slides (HF: skills/media-use/references/media-treatment-recipes.md:153-156). Why not: the Defaults require a measurable grade on every clip; a lighter grade for screen or gameplay footage needs an explicit request.
- §3: Whole-frame warmth/cast from frame-average U/V (HF: packages/cli/src/media-use/lib/grade-analyzer.mjs:131-138, applied to whole frames). Why not: skin dominates chroma. With a 31% skin block, whole-frame warmth read +0.107 on grey (a false cast) and only +0.013 on a real cool cast (neutral pixels: −0.135).
- §3: Luma-percentile clip risk, YHIGH ≥ 235, as the clipping gate (HF: packages/cli/src/media-use/lib/grade-analyzer.mjs:116-117). Why not: it saw 0% of a 16.6% channel clip caused by eq. It stays a diagnosis class; the gate uses max(R,G,B) ≥ 250.
- §3: `-noaccurate_seek` keyframe sampling for gate samples (HF: packages/cli/src/media-use/lib/grade-analyzer.mjs:221-222). Why not: the same `-ss 3.508` landed on 3.0 s with a 60-frame GOP and on 0.0 s with a 300-frame GOP. The gate pairs frames by index (ref 05 §1 **Frames by index**).
- §3: HF look metrics as gate metrics: luma = mean BT.601 Y, saturation = mean (max − min)/max at 160 px wide (HF: packages/cli/src/measure/look.ts:19-43). Why not: ref 01 §0.3 names median HSV saturation, and extract_ref.py:44 measures luma as mean HSV V. Only HF's contrast = std, its floors and its ratio rule are adopted (ref 04 §3 **One metric definition**).
- §3: Grain, dither, scanlines, halftone, film/VHS and other stylised looks. Why not: not part of ref 01's look.
- §3: Five samples per file as the analysis granularity (HF: packages/cli/src/media-use/lib/grade-analyzer.mjs:7). Why not: camera groups need per-shot samples, and the gate needs 1 fps paired frames.
