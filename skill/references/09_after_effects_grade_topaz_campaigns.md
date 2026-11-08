# 09 - After Effects edit path, preset colour correction, Topaz enhance + 60 fps, and brand-campaign clips

Path C of the pipeline. Use it when the request says "edit in After Effects", names an AE colour-correction preset (`.ffx`),
asks for Topaz enhancement / higher fps, or the job is a paid **brand campaign** (a clip-farm brief with a product, a
required title line, tags and banned words). First built on a 7-clip campaign job (stage interviews and a keynote,
1080p24, 1080p30 and 4K60 sources -> 1080x1920 59.94 fps). Every number below was measured on that job.

Refs 01-08 still rule: style (01), picking (02), the cut / mix / mux mechanics and gates (03-05), captions (07), face
tracking (08). This ref only adds what changes when AE, a preset grade and Topaz are in the chain.

## 1. Stage order (one driver script per job, one stage per call, re-runnable)

| stage | what | tool |
|---|---|---|
| prep | `cutlist.py` -> `splice.py` at the **source's native fps** (not 60), then `face_track.py run` | skill scripts |
| track | face track + crop at the **source's native scale** (no upscale in the crop) | `face_track.py` |
| topaz | native crop -> Topaz 2x upscale + frame interpolation to 60000/1001 -> de-blend cut frames | Topaz ffmpeg |
| stab | `face_track.py run --mode steady` on the Topaz footage -> per-frame Position/Scale keys for AE | `face_track.py` |
| overlay | title measurement, framing (head room), caption tokens -> `captions.py` layout JSON | Pillow |
| ae | write `PLAN` JSON -> `build_clip2.jsx` builds the whole edit (stab keys, grade, per-word captions, title) | AE 2025 |
| render | `aerender` in 300-frame chunks (Lossless) -> one NVENC H.264 High encode per chunk -> copy-concat | aerender |
| audio | dialogue stem padded to the 59.94 length + one SFX per accent -> `mix_audio.py` | skill scripts |
| final | `finalize_mux.py` (one AAC encode, copy-mux, BT.709 tags, gate) | skill scripts |
| qc | `caption_gate.py`, `grade_gate.py`, `finalize_mux.py --check`, banned-word / tag check, review sheet | skill scripts |

Why native fps first: interpolating a 23.976 source after a 60 fps splice interpolates duplicated frames. Cut and track on
the source grid, interpolate once, deliver 60000/1001 so 29.97 -> x2 and 23.976 -> x2.5 are exact.

## 2. Topaz Video AI from the command line

- Topaz ships its own ffmpeg (`<Topaz install>/ffmpeg.exe`) with the filters `tvai_up` (upscale / enhance) and `tvai_fi`
  (frame interpolation). Set `TVAI_MODEL_DATA_DIR` and `TVAI_MODEL_DIR` to the models folder
  (`%ProgramData%/Topaz Labs LLC/Topaz Video AI/models`). It has `h264_nvenc` but no libx264.
- Chain used: `tvai_up=model=ghq-5:scale=2:device=0:vram=1:instances=1,tvai_fi=model=apo-8:fps=60000/1001:device=0:vram=1:instances=1,scale=1080:1920:flags=lanczos,setsar=1`
  (Gaia HQ v5 + Apollo v8). A 4K source cropped to 1080x1920 that is already ~60 fps needs neither: copy it through.
- **Quality rules (the first delivery was called "horrible"; root causes, all fixed):**
  1. Crop at the source's native scale (a 1080p 16:9 source gives a 608x1080 crop, `--max-upscale 1.0`) and write it
     near-lossless (x264 CRF 4). Zooming 1.25-2x in the crop plus a lossy lanczos intermediate fed Topaz soft, blocky
     input it could not recover.
  2. Use **Gaia HQ (`ghq-5`)**, not Proteus (`prob-3`), for compressed 1080p web interviews: Proteus turned skin to wax
     and invented texture on the macroblocks; Gaia kept pores and hair (A/B on the same frames).
  3. One lossy encode after Topaz: AE renders Lossless, then one NVENC H.264 High encode (CQ 15, 80 Mbps cap). AE's H.264
     output-module templates write Main profile at a fixed bitrate.
  4. Tame the preset (section 5): saturation 170 + sharpening on top of an enhanced source looked over-cooked.
- **Speed (RTX 3050 Laptop, 4 GB):** Gaia HQ 2x + Apollo on a 34 s 608x1080 29.97 clip took ~78 min (Proteus at
  540x960 was ~25 min). Plan the batch around it; only 1080p-or-lower sources go through Topaz. It saturates the GPU: never run an AE render (or a second Topaz job) at the same time - the AE
  render stalled at 0 frames in 9 min with both on the 4 GB card. Queue Topaz jobs back to back, AE renders after.
- **Interpolation ghosts at cuts:** `tvai_fi` blends across a hard cut / jump cut / speaker switch. After Topaz, rewrite
  the clip with every output frame whose source time falls strictly between native frames c-1 and c (c = each
  `path.json` reset) replaced by the nearest real frame (before the midpoint -> frame of c-1, after -> frame of c), and fix
  the frame count to round(N_native x 60000/1001 / fps_native). One-to-sixteen frames per clip were replaced.
- The intermediate stays an x264 CRF 10 file; only the final delivery follows the user's export codec rule.

## 3. Head room under a required title (vertical canvas)

A brand title sits at the top of the 9:16 safe area (box top y = 190 of 1920, two lines max, ~210 px tall). Stage and
keynote sources often have the head near the top of the frame, so the crop cannot put it lower (the crop is clamped
inside the source). Measure the face-box tops on the canvas (10th percentile of the fused boxes mapped through the crop)
and, when the head would touch the title, **drop the footage layer** in AE by `title_bottom + 120 - p10` px (cap 420).
The gap at the top is filled by a blurred copy of the backdrop (section 4), and the main layer gets a
top mask with a 70 px vertical feather. A burned-in bar in the source (e.g. a "Sponsored by" strip; measure its height,
~90 px of a 1080p frame on one source) is hidden by starting that mask below the bar. The face boxes are shifted by the drop
(and grown 4 % about the anchor for the push-ins) before `captions.py` lays out, so captions still avoid the face.

`face_track.py` settings for this layout: `--eyes-y 0.40 --face-h 0.17` (the framing gate's 22-35 % eyes band is
deliberately overridden for the title; record it as a waiver), `--max-upscale 1.0` at the native crop size (608x1080 for
1080p, 1080x1920 for 4K; up to 1.4 only for a short wide shot where the face is otherwise tiny - every bit of crop zoom
costs detail Topaz cannot restore).

Joins: a cut-list join that removed more than ~1.5 s of source (or any join on a multi-camera source) can land on another
angle. Pass those as `--cut-frames` (hard reset), not `--jump-cuts`; as jump cuts they produced a pan across the cut
(face moved 247 px; P0 `pan_across_cut`).

## 4. The AE comp: the whole edit in AE (`build_clip2.jsx`, data in a `var PLAN = {...}` include)

Bottom to top:
1. **blurred fill** (only when there is a drop or a mask): a canvas-size precomp holding the footage at ~340 %, anchored on the backdrop ~180 px
   in from the frame edge on the side away from the face, blur 120, brightness -30, so the band above the footage is the
   scene's colour. Anchoring on the face (or a 140 % copy pushed down) left the band black or showed a ghost face; check
   that the layer still covers 0..W (`W/2 - anchor_x * scale < 0` and the mirror for the right edge).
2. **CAM null**: position = face anchor + drop; Scale keys = a slow push 100 -> 104 % x punch-ins of +7 % at the accents
   (smoothstep 5 f in, hold ~40 f, 12 f out, ending before the next reset).
3. **footage parented to CAM, with face stabilisation keys**: `face_track.py run --mode steady` on the Topaz footage
   (`--face-h 0.6 --max-upscale 1.05`, resets = the native resets x the interpolation ratio) writes one Position/Scale key
   per frame (the `path.json` effectcraft block); in CAM's space, position = key - CAM position + 50 (null anchor 50,50).
   Fall back to `smooth` when steady fails its jitter gates. Optional top mask (feather 70) for a drop or a burned-in bar.
4. **the colour-correction preset on an adjustment layer** (section 5).
5. **captions, one text layer per word** from `captions_layout.json` (position = `baseline_center`, size = `em_px`,
   in/out = `appear_f`/`end_f`): Montserrat Black, fill colour, black stroke behind the fill, Drop Shadow (distance 0,
   softness 0.35 em), anchor at the visual centre (cap height / 2 above the baseline) so the 80 -> 100 % pop-in scales in
   place. **Deep Glow 2** (`PEDG2`; property 24 = radius, 25 = exposure) on keyword words only, radius 160, exposure
   0.25: exposure 0.55 washed a light-purple keyword to white, so use a saturated keyword colour (#9D5CFF) under a glow.
   Log `sourceRectAtTime` width vs the Pillow width for a few words (measured 1-3 % apart, so the layout's safe-area and
   face checks hold for the AE text).
6. **title**: text layer (product names purple via `TextDocument.characterRange(start, end).fillColor`) + rounded-rect
   shape layer (white, roundness 28, soft shadow) sized from the text's `sourceRectAtTime`; static and fully visible on
   frame 0 (TikTok's default cover is frame 0). Log the box bottom vs the bottom the caption layout assumed.

The grade sits under captions and title, so text colours stay exact (ref 04 section 3).
Run the build with the AE GUI (`AfterFX.exe -r` wrapper with its own log + end marker), quit the GUI, then render with
`aerender -project <aep> -comp <name> -s <f> -e <f> -RStemplate "Best Settings" -OMtemplate "Lossless" -mem_usage 10 20`
in 300-frame chunks, each followed by one NVENC H.264 High encode, then a concat-demuxer copy; audio is muxed afterwards
by `finalize_mux.py`. Give aerender absolute Windows paths (a relative path resolves against its install folder).
Spot-render 2-3 single frames (`-s f -e f`, ~3 s each) to check the look before the full render.

**Disk and memory on a laptop:** AE's disk cache filled the drive (23 GB, error 6662) and its RAM commit grew the
pagefile. Disable the disk cache in the prefs (back the prefs file up first), clear it between chunks, cap `-mem_usage`,
and never run AE and Topaz at the same time on one 4 GB GPU.

**Render memory blow-up (16-19 GB before the first frame) - causes and fixes, measured by bisecting the comp:**
1. A blurred, heavily scaled layer (the 340 % fill) directly in the comp **under a Sapphire effect on an adjustment
   layer** (the preset's `S_Sharpen`) - AE hands Sapphire the layer's whole transformed extent. Put the scaled copy in a
   canvas-size precomp and blur the precomp layer: same look, 60 frames in ~10 s at ~5.6 GB peak. Footage + preset
   alone, or the comp without the preset, never blew up.
2. **Multi-Frame Rendering** multiplies whatever one frame needs by the core count; `-mem_usage` does not cap it, and
   aerender ignored a smaller "Number of Concurrent Frame Renders". Render with MFR off
   (`["Concurrent Frame Rendering"] "Enable Concurrent Frame Renders" = 00` in the prefs).
3. **The AE GUI rewrites its prefs file on quit** (it dropped the MFR section and re-enabled the disk cache), so every
   GUI build stage silently undoes the render prefs. Re-pin them (`scripts/ae/ae_prefs.py`) right before every aerender
   call, not once per job.
4. Watch AE's render engine (`AfterFX.com`) private bytes and free RAM from the driver, and kill the aerender tree above a
   cap; on a retry halve the chunk. Measure private bytes, not the working set (the working set showed 3.9 GB while free
   RAM was already down to 1.3 GB).
5. aerender can hang without starting its engine after a killed run (a stale `dynamiclinkmanager`): end that process
   before each call, and treat "no `AfterFX.com` after 90 s" as a hang.
6. Single-frame spot renders do not show any of this (one frame never triggers MFR); spot-check 30-60 frames with the
   memory sampler before a batch.

## 5. Colour correction from a user preset (`.ffx`)

- Apply the user's preset file directly: `adj.applyPreset(new File("<preset>.ffx"))` on a full-frame adjustment layer.
  It reproduces third-party effects exactly (here: Sapphire `S_Sharpen`, Magic Bullet Looks `MB LookSuite3`, Lumetri
  Color, Brightness & Contrast). Log the effect matchNames after applying; if a plug-in is missing the preset loads
  without it - report that instead of silently substituting another tool.
- The preset studied ("Premium Glow CC"): S_Sharpen -> Looks (soft shoulder, slight cool shadows, lens vignette ~34) ->
  Lumetri contrast 25, highlights 10, shadows 45, whites 20, saturation 170 -> B&C +15 / +20. Bright, punchy, very
  saturated. On talking-head footage set Lumetri saturation to 140 by default (`PLAN.grade.lumetri =
  {"ADBE Lumetri-0020": 140}`; `-0007` is temperature); go further only when a gate or the review shows skin going
  orange or highlights clipping. Set values on the applied effects; never swap the preset's plug-ins for others.
- Then verify with `grade_gate.py <topaz.mp4> <ae render>` (the preset must beat the source on luma, saturation and
  sharpness).

## 6. Captions as an overlay for AE (v1 method; prefer AE text layers, section 4)

libass draws no alpha: `ass` on a `color=black@0` rgba source gives alpha 0 everywhere. Render the ASS twice, on black
(B) and on white (Wt), and solve per pixel `a = 1 - mean(Wt - B)/255`, `C = B / a` (exact for antialiasing, stroke,
shadow and glow), streamed frame by frame into a `qtrle` RGBA `.mov`. The overlay is pixel-identical to what
`caption_gate.py --ass` checked.

## 7. Brand-campaign clips (clip-farm briefs)

1. Turn the brief into a rules file (speaker, length, required product talk, products list, forbidden topics, banned
   words, safe numbers, title patterns, per-platform tags) and give every agent that file.
2. Pick with one agent per source, then **two adversarial verifiers per candidate**, one per lens: brief compliance
   (speaker share, product named, forbidden topics, other company / coin names, banned words, tags) and clip quality +
   fidelity (hook <= 2.5 s, complete payoff, length from word times, cuts that do not change meaning). 12 candidates ->
   7 kept; most fixes were title / caption wording ("explains X" -> "why X matters" when the speaker never names the
   product) and boundary nudges.
3. Other brands named in passing (a payment app, a chain, a partner product) go into `remove_words` when the cut keeps
   the meaning; otherwise drop the candidate.
4. Title = one line naming the real product; captions on the post quote the speaker verbatim (no "most" for "every", no
   added "AI"); never a number the clip does not contain.
5. ASR on brand names: transcribe with a product-name `initial_prompt`, then re-check low-probability product words
   **without** the prompt (the prompt biases towards the brand). Fix caption tokens per word id (`caption_fix`), merge
   split hyphen tokens ("on -ramp" -> "ON-RAMP").
6. Deliver `captions.md` with the title and the three platform captions per clip.
