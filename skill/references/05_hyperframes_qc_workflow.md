# 05 - HyperFrames study: QC gates, review and skill workflow

Studied from HeyGen HyperFrames (https://github.com/heygen-com/hyperframes, Apache-2.0, (c) 2026 HeyGen, Inc.) at commit 8c22ddb (2026-11-01). The method, raw notes and full learning index are in `analysis/repos/hyperframes.md` (repo-relative; not part of the installed skill).

**Precedence.** Ref 01 wins on style: canvas, caption look, accents, grade targets, pacing and ending. Ref 02 wins on moment-picking and job layout. The SKILL.md Defaults table is fixed. Refs 03-05 win on technical correctness where 01/02 are silent or vague: timing and sync, cutting and splicing, audio levels and mixing, encode/mux and colour metadata, QC gates and job hygiene. A rule that changes an older one says "Refines ... (old: ...)".

**Reading the rules.** "HF: path:lines" cites the HyperFrames repo at that commit. "Tested" or "here" means measured with ffmpeg 7.1 on synthetic lavfi media while this reference was written. Pointers like "→ ref 03 §2 **Frame grid**" name the section and the rule's bold title.

## 1. QC gates, review sheets and reference-study tooling
Scope: gates on the staged render, review sheets, review notes, reference studies.

### Adopted (default)
1. **Frames by index.** Read frames by decode index, never by seeking.
   - Frame showing t: `k(t) = floor((t + 0.0005)*fps + 1e-6)` (→ ref 03 §2 **Frame grid**).
   - One decode per file (60 = the fps): `-vf "select='eq(n\,0)+between(n\,59\,61)',setpts=N/(60)/TB" -fps_mode passthrough`; frames out must equal frames asked.
   - Pairs: raw ↔ edited at the same k; source ↔ output through `remap()` (→ ref 03 §2 **One clock**).
   - Pair metrics: `settb=1/1,setpts=N` after each `select`, then `psnr`/`ssim` with `shortest=1:repeatlast=0`; rows must equal pairs asked.
   - Samples: first and last frame; a 1 fps grid at t = i + 0.5 s (the grade gate's, → ref 04 §3 **Grade and gate the footage only**); k−1..k+1 around each cut and accent; each chunk's fully built frame.
   - Implemented by `scripts/cliplib.py` `decode_frames_rgb` (used by `grade_gate.py`, which refuses a short decode with exit 2); `cuts.py` reads every frame in one decode.
   Why: without `-fps_mode passthrough`, 4 picks gave 62 frames (`select` alone) or 3 (with `setpts`); after 2 dropped frames, PTS pairing read 24-25 dB on identical pictures, index pairing 45-53 dB.
   HF: packages/cli/src/measure/media.ts:212,339-341; packages/cli/src/commands/measure/frames.ts:52-75; packages/producer/src/regression-harness.ts:607-620,654-663
2. **Stage, validate, promote.** Refines ref 01 §0.1 and QC (old: "asserts `duration <= 59.5 s` (ffprobe, or `ffmpeg -i` when ffprobe is absent)"; "Duration ≤ 59.5 s (ffprobe or `ffmpeg -i`)").
   - Render to a staged temp name (→ ref 05 §2 **Crash-safe writes**). Only with no P0 open does it become `versions/NN-slug.vK.mp4` and its copy `edited/NN-slug.mp4` (→ ref 05 §2 **Versions, undo, hand edits**).
   - One decode, `ffmpeg -v error -i X -f null - -progress pipe:1`: stderr empty; frames (last `frame=`) == the plan's N, each EffectCraft part its own N; N/fps ≤ 59.5 s, else re-cut (Defaults).
   - Count frames by decoding, never by `-c copy` packets.
   - Header (→ ref 03 §1 **Probe once**): canvas size, fps, `yuv420p`, one 48 kHz stereo AAC. Tracks, audio length, mux structure and colour tags → ref 03 §4 **Delivery gate**.
   - Never gate on the container `Duration:`.
   - Implemented for the delivery file by `scripts/finalize_mux.py`: it muxes to a staged name, runs ref 03 §4 **Delivery gate** (frames, decode errors, ≤ `--max-dur`) and renames onto `--out` only on a pass; a failed gate keeps the staged file and never touches `--out`; an `--out` still locked after the retries keeps the gated file under its staged name (`rename_blocked`). The `versions/` copy and the per-part EffectCraft counts are not scripted.
   Why: a 2.5 s picture muxed with 3 s audio read `Duration: 00:00:03.00` while the decode counted 150 frames; `-c copy` counted 178 packets for 177 decoded frames; a damaged file decoded 145/150 frames with 32 error lines.
   HF: packages/producer/src/services/render/artifactTransaction.ts:23-33,230-271
3. **Events match the plan.** New gate on the staged render. Detector → ref 04 §2 **Classified cut detector** at the render's fps; match events of every class (cut, `fast`, `flash`).
   - Plan: `{fps, frames, cuts, jump_cuts, accent_spans}` in output frames. `cuts` lists every planned join, whip switch frame and kept source cut (source hard/soft events mapped into the clip); `accent_spans` lists flashes, tints, washes, whips and any kept source flash; `jump_cuts` are same-camera punch-ins, never required.
   - Explained: a 1-frame hit within ±1 of a planned cut; any event starting inside an accent span widened by 1 frame each side (spans start 1 frame before the cause, so this is the −2-frame window; whips ±1); a jump cut explains one event within ±1.
   - Every planned cut shows a hit. A planned cut without one passes when some d within ±1 is ≥ 6 and ≥ 4 × typical (seam confirmation, on the whole render's d). The 0.5 × seam-change term (mean |ΔY| of the two raw frames meeting there, 64×36 grey; < 6 = unverifiable) is not implemented: the plan carries no seam change, so list a cut under 6 grey levels as a jump cut.
   - P0: a missed cut or whip; an unexplained hit (sliver, doubled segment, part seam, stray flash); a 2-3-frame hit at a planned cut outside every accent span (black or orphan frame); a shot < 0.20 s between two boundaries, one unplanned (`sliver`); decoded frames ≠ the plan's N.
   - A `sliver_kept` warning (→ ref 03 §2 **No slivers at splices**) is a review item: look at its seams row.
   - Implemented by `scripts/cuts.py --plan plan.json` on the whole render (exit 1 on any P0). Untested on media: a 2-6-frame whip, a 55% green tint at 60 fps, a 0.35 s white-flash decay inside an accent span, and a full 720-frame edit; the rules cover them through accent spans.
   Why (tested): a black frame at a join read as one 2-frame hit; a 2-frame tint flash, and a 2-frame sliver at 60 fps, as two 1-frame `flash` events; a 0.35 s flash decay as a 4-frame cut; same-camera jumps read d 5.6-8.3 at 4-6% (a 6% jump, d 7.9, passed only via the seam check) and 11.4-12.0 at 10% (found in 1 of 3 files).
   HF: packages/cli/src/measure/diff.ts:67,461-474; packages/cli/src/measure/cuts.ts:97-110
4. **Captions from pixels.** → ref 04 §1 **Presence, stale and sync gate** (the one caption-pixel method).
5. **A/V offset.** New gate.
   - Onsets: per cut-list segment ≥ 2 s, the output span vs its source span, with the decode and onset curve of ref 03 §1 **ASR on the video's clock** (8 kHz, rises of 10 ms RMS, Pearson over ±500 ms; r ≤ 0.3 = unmeasured). P0 if |offset| > 1 frame.
   - Lip sync: the 1-2 longest single-shot speech windows ≥ 2 s; mouth signal of the median tallest face box → ref 04 §2 **Active speaker from lip motion**. Pearson over ±0.4 s, parabola-refined; + = picture late.
   - High confidence: peak r ≥ 0.5, margin ≥ 0.1 over lags > 2 frames away, not at the search edge, speech (RMS > 0.1 × max) ≥ 10% of frames. Medium/low = unmeasured, never a pass.
   - Judge high only, with speech ≥ 30%: P0 outside −125..+45 ms, unless the source window reads the same lag ±1 frame (a source offset: P1).
   Why: priming, seeks and muxing shift sound. Tested: lip sync +2.2 / +33.0 / −198 ms for in sync / picture 2 f late / audio 200 ms late (all high); onsets 0/30/200 ms for 0/33/200 ms, also under a −10 dB bed and SFX hits; under a bed, 1-s windows misread 4 of 22 (to 500 ms, r 0.98), 2-s windows 0 of 30.
   HF: packages/cli/src/measure/diff.ts:1059-1100; packages/cli/src/measure/sync.ts:53-86,103-124; packages/cli/src/measure/person.ts:21-24,498-526
6. **Black, frozen, frame 0.** New gate; refines ref 01 QC (old: "Frame 0 has speech or a reaction").
   - `ffmpeg -hide_banner -i X -vf "blackdetect=d=0:pix_th=0.10,freezedetect=n=-60dB:d=0.3" -an -f null -`: a black frame, or a freeze outside a planned still (meme freeze), = P0; P1 if the mapped source span shows it too.
   - Sampled indexes: RGB sum ≤ 12 in edited and ≥ 32 in raw on > 0.1% of the central 60% × 60% = P0 (a dropped layer).
   - Frame 0 is the thumbnail: it shows a detected face (speaker or reactor).
   - Scripted so far only at the tail: `finalize_mux.py`'s `black_tail` check (no black frame in the last 0.1 s, `blackdetect=d=0:pix_th=0.10:pic_th=0.98`).
   Why (tested): 1- and 2-frame blacks were reported exactly, a 30-frame freeze as 0.45 s, a clean noisy clip as nothing; full-frame black-only read 0.7-36% on clean dark shots under the ref 01 grade + `vignette=PI/5`, while the centre read 0 and caught a dropped top panel (0.361).
   HF: packages/engine/src/utils/gpuParityDiff.ts:120-123,208-217; packages/cli/src/utils/craftAudit.ts:128-135
7. **Framing by shot medians.** Refines ref 01 QC (old: "On 1 fps samples, the face is fully in frame on every close shot, eyes at y 22-35%").
   - Map the source face track through the crop path. Per close shot ≥ 1 s with ≥ 3 samples at 4/s, tallest face, medians: height 20-30% H, eyes 22-35% H, centre x 40-60% W (ref 01 §4).
   - Face fully in frame stays per sample (→ ref 04 §2 **Push-ins on a parent; plate covers the canvas**); jitter stays ref 01's < 0.5% W.
   - Sticker, label and watermark boxes never overlap the face or the live caption block box (→ ref 04 §1 **Face avoidance per window**).
   Why: a stray detection can't fail a shot, and lucky samples can't pass one.
   HF: packages/cli/src/measure/person.ts:13-20,417-447; packages/cli/src/utils/checkPipeline.ts:344-381
8. **Review sheets.** Refines SKILL step 7 (old: "Review frames against ref 01's QC checklist"). All sheets live in `qc/NN/`; open every one before delivery.
   - `seams.jpg`: a row per cut and accent at k −12, −6, −1, 0, +1, +6, +12 (30 fps: −6, −3, −1, 0, +1, +3, +6; ±1 is threshold ours), 384 px tiles: `-vf "select='eq(n\,108)+eq(n\,114)+between(n\,119\,121)+eq(n\,126)+eq(n\,132)',scale=384:-2,tile=7x1" -frames:v 1`.
   - `beats.jpg`: each shot at min(start + 0.3 s, middle), plus the middle if ≥ 0.5 s later, 480 px.
   - `phone.jpg`: each fully built chunk at 360 px wide: is it readable?
   - Grade sheet → ref 04 §3 **One sheet, measured log**.
   - A strip over 12 frames keeps k−1..k+1 of each onset; at least half its frames are evenly spaced.
   Why: 1 fps grids miss 1-3-frame flashes, slivers and seam jumps.
   HF: packages/cli/src/commands/snapshotReview.ts:10-16,139-151,292-335; packages/cli/src/commands/measure/frames.ts:138-156
9. **Measure, then look.**
   - `qc/NN/qc.json`: `{ok, findings: [{id, measured, threshold, status, fix, ref}]}`. Fix a warning, or waive it in the clip's plan (`waivers: {finding_id: reason}`, → ref 05 §2 **Ship stages, fill a plan**).
   - One line per problem: `t=12.40s f744 · captions · 4 f late → reveal at f740 · keep colour`.
   - P0 = a failed gate or a Defaults breach (e.g. a reused SFX): blocks delivery. P1 = weakens (seam jump, soft payoff). P2 = polish.
   - Fix every P0 and the cheap P1s; re-check only the changed frames; a full re-pass only while a P0 is open. A numeric near-miss with nothing visible: one bump, one re-render.
   - Never score a render /10 (candidates keep ref 02 scores).
   - `REVIEW.md` in the job folder, its short form in the reply: gate numbers; measured vs only looked at ("audio measured, not listened to"); fallbacks (edit path, ASR model/device, font, SFX variants); waivers; the weakest moment.
   - On a hard blocker, `REVIEW.md` is written before any fallback (→ ref 05 §2 **Job ledger**).
   Why: a score finds nothing to fix.
   HF: skills/hyperframes/references/review.md:7,32-38,44-51
10. **Word timings.** → ref 03 §1 **Normalise words** and **Failure gate + hallucinations**.
11. **Reference studies per frame.** Refines SKILL "New reference shorts" (old: "cut times, 1 fps frame grid").
    - Events at native fps (→ ref 04 §2 **Classified cut detector**), not the repo-only `analysis/tools/extract_ref.py` HSV-histogram test (Bhattacharyya > 0.45: 172 "cuts" vs ~27 real on ref 1). Flashes and whips count as accents.
    - A strip per event window: ±2 frames, merged within 0.25 s while ≤ 1.5 s.
    - Caption switches from caption-band pixels, every frame (reference studies only; our renders use ref 04 §1).
    - Stats: → ref 04 §3 **One metric definition**. Per-sample stats go to a `.tsv` beside a compact JSON summary (→ ref 05 §2 **Context hygiene**).
    - Note each number's resolution; re-measure ref 01's caption lead per frame (it was read off 1 fps frames and 10 fps sheets).
    - Match a reference one axis per render, as an absolute value ("cap height = 3.3% H"), never a relative nudge.
    Why: second- or quarter-second sheets miss 1-3-frame timing and one-frame flashes; relative corrections pendulum.
    HF: skills/reverse-any-video/SKILL.md:19-21; skills/reverse-any-video/references/match.md:8; packages/cli/src/measure/events.ts:16-19,382-410; docs/prompting/recreating-references.mdx:29-38

### Optional
- **Regression renders** (skill changes). Index-paired SSIM (whole frame, and the worst 4×4 cell) of re-rendered stored cases vs their stored renders.
  - Bar = the case's baseline p05 − 0.02, never tightened. A case that flips re-runs twice and fails on 2 of 3.
  - Picture-unchanged re-edits: → ref 05 §2 **Prove the freeze**.
  Why: regressions drop mean SSIM by ≥ 0.05; encoder drift is ~0.01.
  HF: skills/remotion-to-hyperframes/references/eval.md:68-75; packages/cli/src/measure/diff.ts:302-304; packages/studio/tests/e2e/edit-accuracy/ratchet.mjs:2-4
- **Locate reference shots in their source** (trims vs ref 02's pads): 100 Hz RMS envelopes (8 kHz, 80-sample RMS), lags keeping ≥ 90% inside, r ≥ 0.6.
  HF: packages/cli/src/measure/person.ts:34-37,122-153

## 2. Skill structure, re-edits, picking hygiene and the lessons loop
Scope: what ships, safe writes, caching, re-edits, versions, copy fidelity, lessons, skill upkeep.

### Adopted (default)
1. **Ship stages, fill a plan.**
   - Direction: each deterministic stage ships as a script with a `SCRIPT_VERSION`; a step hand-written in 2 jobs becomes the next script.
   - Shipped (`scripts/`): `probe_source.py` (ref 03 §1), `cutlist.py` and `splice.py` (ref 03 §2), `mix_audio.py` (ref 03 §3), `finalize_mux.py` (ref 03 §4), `cuts.py` (ref 04 §2, ref 05 §1), `grade_gate.py` (ref 04 §3), shared helpers in `cliplib.py`. Run them; never re-type their steps.
   - Per clip, Claude writes only the plan `plans/NN-slug.vK.json`: cut word ids (`start_word`, `end_word`, `remove_words`, `keep_gaps`), chunks, accents, SFX ids, grade, mix, ending, `waivers: {finding_id: reason}`.
   - `cutlist.json` and every later stage file are derived from the plan (by the shipped script where one exists), never hand-written (→ ref 03 §2 **One compiler per clip**).
   Why: per-job rewrites drift toward the last job's look.
   HF: .agents/skills/changelog-video/SKILL.md:30-46
2. **Crash-safe writes.**
   - Write a sibling temp `<stem>.tmp-<pid>-<uuid8><ext>`, then `os.replace` (the shipped `cliplib.tmp_path` / `replace_with_retry`). Keep the extension: ffmpeg picks the muxer from it (`out.part` fails with "Unable to choose an output format"; `.mp4` endings work).
   - Windows: retry `PermissionError` (a file held open) after 10, 20, 40, 80, 160, 320, 640 ms (1.27 s), then raise. Every shipped script writes its outputs this way.
   - A dir rename onto an existing dir also raises `PermissionError`: for cache dirs, keep theirs (ref 05 §2 **Stage cache = key + schema + sentinel**).
   Why: a kill mid-write truncates the real file; time-named temps collide.
   HF: skills/media-use/scripts/transcript-cut.mjs:123-125; packages/core/src/renameWithRetry.ts:5-8; packages/cli/src/whisper/transcribe.ts:303-315
3. **Stage cache = key + schema + sentinel.**
   - `cache/<stage>-v<N>-<sha16>/`; sha16 = the first 16 hex of sha256 over `json.dumps({"stage": s, "schema": N, "inputs": i, "params": p}, sort_keys=True)`.
   - Source = videoId + format_id + size; ASR adds model, compute_type, language. Cached intake outputs: `source_facts.json`, `raw_words.json`, `transcript.json`, face tracks (in source frames).
   - Build in `<entry>.partial-<pid>-<uuid8>/`, write `.complete` last, then rename (name taken: keep theirs, delete ours).
   - Hit = `.complete` + non-empty outputs, else rebuild. Bump N when a key's output changes.
   - Seeds: `random.Random(f"{videoId}:{rank}:{item}")` (str seeds are stable); never `hash()` (salted per run).
   Why: a half-written entry or a reshuffled SFX pick survives every re-edit. Tested: the key ignores dict order and a schema bump misses; str seeds gave the same picks under PYTHONHASHSEED 1 and 2.
   HF: packages/engine/src/services/extractionCache.ts:13-23,61-65,202-211,243-252; skills/hyperframes/SKILL.md:23
4. **Re-edits touch the smallest stage set.** Refines SKILL step 8 / ref 02 rule 10 (old: "Re-run steps 4-7 only" / "re-run only cut, reframe and render").
   - Write the note into the plan as an absolute value ("end = 28.40 s"), then re-run only:
     - start, end, max length, removed words, "keep the pauses", ending: the cut-list recompile (→ ref 03 §2 **One compiler per clip**) and every stage after it;
     - aspect: crop, captions, video, mux;
     - caption text or colours: captions, video, mux;
     - accents: accents, mix, video, mux; grade: video, mux;
     - SFX, music: mix, mux (`-c:v copy`); clip count: the added clips only.
   - Never re-download, re-probe or re-run ASR while cached; face tracks cached in source frames survive recompiles.
   Why: relative notes oscillate; full rebuilds drift on settled choices.
   HF: docs/prompting/editing-existing-videos.mdx:8-10,42
5. **Prove the freeze.**
   - `ffmpeg -v error -i X -map 0 -c copy -f streamhash -hash md5 -`, old vs new: an audio-only re-edit keeps the same `0,v,MD5=` line; a visual-only one the same audio line (→ ref 03 §4 **One AAC encode, copied at the mux**).
   - Caption-only: per-frame SSIM of the bands y < 40% H and y ≥ 85% H, paired by index (→ ref 05 §1 **Frames by index**): p05 ≥ 0.98.
   - Lavfi test: caption 50% → 72% H read 0.997; a 6 px shift 0.88; a mild grade 0.97. Assumes ref 01 caption positions; untested on EffectCraft renders.
   Why: whole-frame SSIM scored the caption change 0.945, below an unwanted grade (0.971).
   HF: packages/cli/src/measure/diff.ts:303-304
6. **Versions, undo, hand edits.** Extends ref 02 rule 9's layout.
   - Each render = `versions/NN-slug.vK.mp4` + `plans/NN-slug.vK.json`; `edited/NN-slug.mp4` is a copy of the latest. "Undo" or "worse" re-delivers vK−1.
   - A file Claude wrote whose sha256 changed is the person's edit: an input, never overwritten.
   - `edited/` copy hand-edited, or still locked after every retry: keep the validated `versions/` file, deliver its path and name the blocked file.
   Why: a hand fix overwritten between turns is lost.
   HF: skills/hyperframes-cli/SKILL.md:52; packages/cli/src/media-use/lib/manifest.mjs:83-84
7. **Job ledger.**
   - `job.jsonl`, one JSON line per written file: stage, path, sha256, input/params hashes, script/tool versions, written_by, time. Append under an O_EXCL `.lock`; skip bad lines; the last line per path wins.
   - Regenerate `INDEX.md` (id, stage, dur, dims, path). Re-edits read `REVIEW.md` (→ ref 05 §1 **Measure, then look**), then `INDEX.md`, first.
   - Name changed tool versions old → new; their first clip runs every gate.
   - Hard blocker: write `REVIEW.md` before any fallback.
   Why: one file holds the state; a session dying mid-fallback still leaves a report.
   HF: skills/media-use/references/memory.md:33-35; skills/hyperframes/references/skill-lifecycle.md:49; skills/hyperframes-cli/references/doctor-browser.md:43-45
8. **Copy traces to the transcript.** Adds to ref 02 rule 7.
   - Each number in `title` and `post_caption` equals a value spoken in the clip span after normalising ($1M = 1,000,000 = "a million").
   - Each name occurs in the span, the video title or the channel name. Hashtags and the separate SFX credit line are exempt.
   - No derived claims ("40 min to 2 min" is not "20x faster").
   Why: an invented number goes out under the creator's name.
   HF: skills/hyperframes/references/story.md:12-13
9. **Lessons loop.**
   - JSON lines in `$CLIP_EDIT_HOME/lessons.jsonl` (default `~/.clipping-edit`): ts, job, stage, kind (user_correction, qc_fail, fallback, missing_feature, banned_default), detail, fix, ref. Paths scrubbed; best-effort.
   - A detail seen in ≥ 2 jobs becomes a ref rule, a ref 01 number or a QC check, plus a regression case (→ ref 05 §1 **Regression renders**), committed without paths or names.
   - Each review logs generated-looking defaults as banned_default; promoted ones are proposed for ref 01 §5 "Never use".
   Why: corrections that live only in chat repeat.
   HF: packages/cli/src/media-use/lib/misses.mjs:11-27; skills/hyperframes/references/spec.md:64
10. **Context hygiene.**
    - Stdout contract → ref 03 §1 **Script hygiene**; print it as `json.dumps(o, indent=1)` with each innermost `[..]`/`{..}` folded onto one line.
    - Per-frame series go to `.tsv`. Never Read a `.cube`, crop path or per-frame file; view its sheet.
    Why: a 33^3 LUT is ~36k lines with no legible signal.
    HF: skills/media-use/references/grading.md:20; packages/cli/src/measure/media.ts:343-345
11. **Skill upkeep.** SKILL.md routes (Defaults, gates, a "What to read" table); ref numbers never change.
    - Skill lint (direction) fails on:
      - description > 320 B, SKILL.md > 7,168 B;
      - an empty name or description; an unquoted frontmatter value containing ": ";
      - a SKILL.md code span with an exclamation mark, or ">" before a word character;
      - a missing `references/`, `scripts/` or `assets/` path; an `analysis/` path not marked repo-only;
      - a Defaults number that differs between SKILL.md, README and ref 01 §0.
    - Drift check (direction): run from a checkout, compare `skill/` with the copied install by bundle hash and warn. Hash = sha256[:16] over sorted POSIX relpaths + NUL + text (CRLF → LF) + NUL; no `__pycache__`.
    Why: one bad frontmatter line or span stops the skill loading; copied installs drift.
    HF: scripts/check-core-skills.mjs:12-23,48-55; scripts/lint-skills.ts:39-55,70-79; packages/cli/src/utils/skillsManifest.ts:233-247; skills/hyperframes/SKILL.md:58-74

### Optional
- **Remembered prefs and looks.** Refines SKILL Defaults (old: "Any of these can be changed by the request").
  - Save aspect, max length, clip count, SFX on/off and palette only when typed or approved; promote to per-user prefs once 2 jobs (distinct videoIds) confirm a value.
  - Apply as a request with a receipt ("aspect 9:16 (jobs A, B)"); a live request wins.
  - Never relax a quality gate (longer max, no tracking, no grade gate, reused SFX).
  - After approval, offer once to save the look to `$CLIP_EDIT_HOME/looks/<slug>/`.
  Why: one-off choices must not become defaults; prose loses continuous qualities (glow strength).
  HF: skills/media-use/references/memory.md:5,13,21,29; docs/prompting/recreating-references.mdx:44-46

## Not adopted (and why)
- §1: "A film that feels busy: remove a third of the motion" (HF: skills/hyperframes/references/review.md:38). Why not: ref 01 §5 fixes accent density (1 per 6-8 s, at most 40% of cuts) and §8 fixes pacing; a blanket one-third cut would undershoot both.
- §1: The `dead_stretch` warning: nothing on screen changes for more than 3 s (HF: packages/cli/src/utils/craftAudit.ts:18; docs/packages/cli.mdx:1294). Why not: ref 01 §8 allows shots up to 7 s and speechless action stretches up to 5 s (9 s for the main climax), with music and an asterisk caption; speech stretches change captions anyway. Not a gate.
- §1: The `first_frame_empty` fix: "have the title or key image already on screen at 0 s" (HF: packages/cli/src/utils/craftAudit.ts:133). Why not: ref 01 §1-2: no title or hook banner; frame 0 is mid-sentence or a reaction close-up. Adopted only as "frame 0 shows a detected face" (ref 05 §1 **Black, frozen, frame 0**).
- §1: HF rebuild SSIM bars: mean 0.92, p05 0.85, worst cell 0.75 (HF: packages/cli/src/measure/diff.ts:53-60). Why not: they grade a rebuild against its original; our render differs from the source by design (crop, grade, captions, accents), and ref 05 §1 **Regression renders** calibrates a per-case bar instead (HF: skills/remotion-to-hyperframes/references/eval.md:68-75).
- §1: "Render and diff once more, then stop" applied to visible defects (HF: skills/reverse-any-video/SKILL.md:36). Why not: SKILL step 7's "fix before delivery" wins for P0 and visible defects; the stop applies only to numeric near-misses with nothing visible.
- §1: The persistence rule: a finding at a single sample demotes to info, one held across samples gates (HF: skills/hyperframes-cli/references/lint-validate-inspect.md:68; packages/cli/src/utils/checkPipeline.ts:1890-1895). Why not: our gates target 1-frame defects (black frames, slivers, dropped layers), and accent windows already exclude planned transients. A "held ≥ 3 frames" variant proposed during the study was untested and contradicted those gates.
- §1: A second caption-pixel gate from an affine ring-fit residual on the graded frame (proposed during the study). Why not: ref 04 §1 **Presence, stale and sync gate** is the one method. Tested with the ref 01 grade: the residual passed a font-fallback render (43.8 ≥ 10) that the caption-only match failed (0.086). The plain caption-band difference is listed in ref 04's Not adopted.
- §1: HF's black-only rule counted over the full frame (HF: packages/engine/src/utils/gpuParityDiff.ts:120-123). Why not: tested, clean dark shots under the ref 01 grade + `vignette=PI/5` read 0.7-36%, a false P0 at the 0.1% bar; the central 60% × 60% read 0 and still caught a dropped panel (0.361).
- §1: HF's audio null test, residual ≤ -50 dBFS as proof of an untouched mux (HF: packages/producer/src/utils/audioRegression.ts:83-87). Why not: one AAC generation of pink noise read -50.8 and -47.9 dB in two runs, straddling the bar. The mux is a stream copy, proven bit-exact by ref 05 §2 **Prove the freeze**; ref 05 §1 **A/V offset** catches shifts.
- §1: HF frame tolerances: a 1-frame shortfall (HF: packages/producer/src/services/render/artifactTransaction.ts:230-246) and video-frame coverage 0.95 (HF: packages/producer/src/services/render/videoFrameCoverage.ts:40-44). Why not: that slack covers browser capture and container rounding. Our plans are integer frames rendered CFR, so decoded frames must equal N; a 0.95 bar would pass a 3 s loss in a 60 s clip.
- §1: HF's adaptive hold floor clamp(2·p10, 0.5, 1.5) grey levels for frozen pictures (HF: packages/cli/src/measure/events.ts:103). Why not: a still talking head can sit under that floor; `freezedetect=n=-60dB:d=0.3` found an injected 30-frame freeze (0.45 s reported) and nothing on a clean noisy clip.
- §1: A decoded-audio end window (−1 frame to +1 frame + 1024 samples) as a separate render check (proposed during the study). Why not: ref 03 §4 **Delivery gate** owns audio length; decoded AAC runs up to 1023 samples past the mix (tested: 120000 → 120832), so that gate reads the edit-list durations instead.
- §1: Reading a reference's music and effects from separated stems (HF: docs/packages/cli.mdx:851-858). Why not: it uploads the recording to HeyGen's `/v3/audio/stems` with a HeyGen credential, outside requirements.txt; for a reference's mix level, run ebur128 on the played window (ref 03 §3 **Measure the played window**).
- §2: Never render merely because checks pass; pause at the final preview and wait for approval (HF: skills/hyperframes-cli/references/conventions.md:17; skills/hyperframes/SKILL.md:48). Why not: the SKILL.md Pipeline wins: a one-line trigger runs the whole job without asking questions.
- §2: Do not build a substitute rasterizer on a blocked host (HF: skills/hyperframes-cli/references/doctor-browser.md:40-43). Why not: SKILL.md Editing path B sanctions the ffmpeg + ASS/libass + Pillow fallback. Only "write the report before any fallback" is adopted (ref 05 §2 **Job ledger**).
- §2: Remembered preferences that never skip a question (HF: skills/media-use/references/memory.md:13). Why not: the one-line trigger asks nothing, so remembered values are Optional (ref 05 §2 **Remembered prefs and looks**); they apply as a request with a receipt line and never relax a quality gate.
- §2: The change or question arrives within about the first second (HF: skills/hyperframes/references/types/vertical.md:11-12). Why not: ref 01 §2 wins as the gate: premise spoken by t ≤ 2.5 s, measured on the reference Shorts (ref 3 lands it at 1.3 s).
- §2: Cache source key (path, mtime, size) (HF: packages/engine/src/services/extractionCache.ts:8-9,73-79). Why not: a re-download changes path and mtime; HF itself keys downloaded media by content SHA-256 instead (:92-93). We key on videoId + format_id + size, so a multi-GB source is never hashed.
- §2: A bundle hash over the sorted full OS path list (HF: packages/cli/src/utils/skillsManifest.ts:223-225). Why not: HF's own docstring (:229-231) promises relative POSIX order. On Windows a backslash sorts after digits (tested: `a0.md` sorts before `a\x.md`, but `a/x.md` sorts before `a0.md`), so the same tree hashes differently per OS. We sort POSIX relative paths.
- §2: A cache LRU clock and GC sweeps (HF: packages/engine/src/services/extractionCache.ts:24-26). Why not: stage caches live in the job folder and go with it; no cross-job cache is kept.
