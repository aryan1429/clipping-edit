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
| track | face track only (re-run after changing joins / upscale) | `face_track.py` |
| topaz | reframed preview -> Topaz upscale + frame interpolation to 60000/1001 -> de-blend cut frames | Topaz ffmpeg |
| overlay | title PNG, framing (head room), caption tokens -> `captions.py` -> alpha overlay | Pillow, libass |
| ae | write `PLAN` JSON -> `build_clip.jsx` builds the comp + render-queue item, saves the .aep | AE 2025 |
| render | `aerender` the project's queue (H.264 template, video only) | aerender |
| audio | dialogue stem padded to the 59.94 length + one SFX per accent -> `mix_audio.py` | skill scripts |
| final | `finalize_mux.py` (one AAC encode, copy-mux, BT.709 tags, gate) | skill scripts |
| qc | `caption_gate.py`, `grade_gate.py`, `finalize_mux.py --check`, banned-word / tag check, review sheet | skill scripts |

Why native fps first: interpolating a 23.976 source after a 60 fps splice interpolates duplicated frames. Cut and track on
the source grid, interpolate once, deliver 60000/1001 so 29.97 -> x2 and 23.976 -> x2.5 are exact.

## 2. Topaz Video AI from the command line

- Topaz ships its own ffmpeg (`<Topaz install>/ffmpeg.exe`) with the filters `tvai_up` (upscale / enhance) and `tvai_fi`
  (frame interpolation). Set `TVAI_MODEL_DATA_DIR` and `TVAI_MODEL_DIR` to the models folder
  (`%ProgramData%/Topaz Labs LLC/Topaz Video AI/models`). It has `h264_nvenc` but no libx264.
- Chain used: `tvai_up=model=prob-3:scale=2:device=0:vram=1:instances=1,tvai_fi=model=apo-8:fps=60000/1001:device=0:vram=1:instances=1,scale=1080:1920:flags=lanczos,setsar=1`
  (Proteus v3 + Apollo v8). For a 4K source the reframe is rendered at 1080x1920 and `scale=1` (enhance only); a source that
  is already ~60 fps skips `tvai_fi`.
- Render the face-tracked reframe at **half the canvas (540x960)** for 1080p sources and let Topaz do the 2x: a true 2x
  model upscale is sharper than lanczos-to-1080 followed by a 1x enhance (A/B on the same frame: brick and hair detail
  visibly crisper).
- **Speed (RTX 3050 Laptop, 4 GB):** ~25-27 min for a 34-40 s clip (540x960 -> 1080x1920 + 24/30 -> 59.94). The first
  ~60 s is model load. It saturates the GPU: never run an AE render (or a second Topaz job) at the same time - the AE
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
The gap at the top is filled by a blurred (80), darkened (-35) 140 % copy of the same footage, and the main layer gets a
top mask with a 70 px vertical feather. A burned-in bar in the source (e.g. a "Sponsored by" strip, 54 px of a 1080p
frame) is hidden by starting that mask below the bar's canvas position. The caption face boxes are shifted by the same drop
(and grown 9 % for the push-ins) before `captions.py` lays out, so captions still avoid the face.

`face_track.py` settings for this layout: `--eyes-y 0.40 --face-h 0.22` (the framing gate's 22-35 % eyes band is
deliberately overridden for the title; record it as a waiver), `--max-upscale` relative to the render size
(1.25 at 540x960 = 2.5x of the source, 1.5 for a single wide camera, 2.0 for long wide stage shots, 1.35 at 1080x1920 for
4K sources).

Joins: a cut-list join that removed more than ~1.5 s of source (or any join on a multi-camera source) can land on another
angle. Pass those as `--cut-frames` (hard reset), not `--jump-cuts`; as jump cuts they produced a pan across the cut
(face moved 247 px; P0 `pan_across_cut`).

## 4. The AE comp (`build_clip.jsx`, data in a `var PLAN = {...}` include)

Bottom to top:
1. blurred fill copy (enabled only when there is a drop or a mask),
2. the Topaz footage, anchor = the median face centre on the canvas, position = anchor + drop; Scale keys = a slow push
   100 -> 104 % over the clip x punch-ins of +7 % at the accents (smoothstep 5 f in, hold ~40 f, 12 f out, ending before
   the next reset),
3. **the colour-correction preset on an adjustment layer** (section 5),
4. the caption overlay (alpha `.mov`, `AlphaMode.STRAIGHT`),
5. the title PNG (pop in 88 -> 103 -> 100 % over 6 f, on for the whole clip).

The grade sits under captions and title, so text colours stay exact (ref 04 section 3).
Render queue: `Best Settings` + output module template `H.264 - Match Render Settings - 40 Mbps` (AE 2025 lists
5 / 15 / 40 Mbps H.264 templates), video only; audio is muxed afterwards by `finalize_mux.py`. Run the build with the AE
GUI (`AfterFX.exe -r` wrapper with its own log + end marker), quit the GUI, then `aerender -project <aep>`.

## 5. Colour correction from a user preset (`.ffx`)

- Apply the user's preset file directly: `adj.applyPreset(new File("<preset>.ffx"))` on a full-frame adjustment layer.
  It reproduces third-party effects exactly (here: Sapphire `S_Sharpen`, Magic Bullet Looks `MB LookSuite3`, Lumetri
  Color, Brightness & Contrast). Log the effect matchNames after applying; if a plug-in is missing the preset loads
  without it - report that instead of silently substituting another tool.
- The preset studied ("Premium Glow CC"): S_Sharpen -> Looks (soft shoulder, slight cool shadows, lens vignette ~34) ->
  Lumetri contrast 25, highlights 10, shadows 45, whites 20, saturation 170 -> B&C +15 / +20. Bright, punchy, very
  saturated. Override only by setting values on the applied effects (`PLAN.grade.lumetri = {"ADBE Lumetri-0020": 140}`),
  and only when a gate or the review shows skin going orange or highlights clipping.
- Then verify with `grade_gate.py <topaz.mp4> <ae render>` (the preset must beat the source on luma, saturation and
  sharpness).

## 6. Captions as an overlay for AE

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
