# 07 - Caption safe area: fit, place and gate every word on real pixels

Why this exists: captions were laid out by hand per job from the rules in ref 01 §3 and ref 04 §1, and words ended up off-screen or cut off at the frame edge. `scripts/captions.py` now does the layout (font check, measured fit, safe-area and face-clear placement, ASS + a layout JSON for EffectCraft) and `scripts/caption_gate.py` checks the rendered pixels. Never hand-place caption text: every rule below, typed stage directions and per-chunk shadow included, is a token field or a flag (§5 lists what stays manual).

**Precedence.** Ref 01 still owns the look (font, size, colours, stroke, shadow, glow, chunking, reveal). This reference owns where the ink may go and how that is proven. A rule that changes an older one says "Refines ... (old: ...)".

**Reading the rules.** "Tested" means measured here with ffmpeg 7.1 (libass 0.17.3) and Pillow 12.1 on synthetic media, Montserrat Black, while this reference was written. "Design choice" marks a number that was chosen, not measured. Ink always means a caption-only render on #808080 with max|px − 128| > 24, the same definition as ref 04 §1 rule 7, so shadow and glow count.

## 1. Root causes (each one reproduced)
1. **A word wider than the frame.** No rule stopped a single long token, and libass simply clips it at the frame edge.
   - Tested: at 1080×1920 (em 90.5 px) `UNBELIEVABLEEEEEEE` is 1121 px of advance; libass drew ink from x 0 to 1080, cut off on both sides. `SUPERCALIFRAGILISTIC` is 1158 px and `$100,000,000` is 657 px.
2. **Sizes in the wrong unit.** libass sizes `\fs` to the font's win box: `\fs` = em × (usWinAscent + usWinDescent)/unitsPerEm, which is ×1.379 for Montserrat Black. A builder that feeds `\fs` to an em-sized renderer (Pillow, EffectCraft/AE-style text), or the reverse, is 38% off. The old EffectCraft "× 1.14" was a guess, never a measurement.
   - Tested: the model below matched libass ink to ±1 px on 16 strings (W, I, J, AVATAR, $100K, Q, ...) at em 90 and 68.
3. **Halos and the entrance not in the box.** The rules measured `getlength + 2·\bord`. The shadow (blur ~60 px), the keyword glow (blur ~20 px) and any entrance overshoot add ink that this did not count.
   - Tested: ref 01's shadow and glow reach up to 21.1 px beyond the stroke at 1920 H (half-plane bound, §3 rule 4). An entrance peak of 125% on words fitted to the safe edge put ink at x 0 (left margin −65 px, right −88 px).
4. **No horizontal clamp, no right rail.** Lines were centred at W/2 with no check against the frame or the 9:16 action rail.
5. **Two lines at the low position.** Ref 01's low position (first baseline at 72% H) puts the baseline at y 1382 on 1920. That is already below the 9:16 UI band (y ≤ 1330), before line 2 is added.
   - Tested: naive 6-word lines at 72% H reached y 1426 (−96 px past the band) and were clipped at both sides.
6. **9:16 pixel numbers on other canvases.** y 1330 is off a 1080-high canvas.
   - Tested: a 9:16 low position (y 1330) on 1920×1080 drew no ink at all (every word off-frame).
7. **PlayResX/Y ≠ video size.** libass rescales every `\pos` and size.
   - Tested: a 1080×1920-laid-out ASS with PlayRes 1920×1080 drew no ink for y 1330, and with PlayRes 384×288 (the default when it is missing) also nothing. The self-test case put ink 570 px past the band bottom.
8. **Font fallback.** A Fontname that libass cannot match falls back to another font of different width, with no error.
   - Tested on "HELLO WORLD" at `\fs124.1`:

     | Fontname | libass picked | Ink width |
     |---|---|---|
     | `Montserrat Black` (legacy family, nameID 1) | Montserrat-Black | 722 px |
     | `Montserrat Blak` (typo) | ArialMT | 793 px (+9.8%) |
     | `Montserrat-Black` (PostScript name, nameID 6) | ArialMT | 793 px |
     | `Montserrat` (typographic family, nameID 16) | Montserrat-Regular | 692 px (wrong weight) |

   - A glyph missing from the font falls back per glyph: CJK went to YuGothicUI-Semibold and 🔥 to SegoeUIEmoji, both with unmeasured widths. Each fallback prints its own `fontselect:` line at `-v info`.
9. **Unpositioned simultaneous events restack.** libass's collision logic stacks events that overlap in time.
   - Tested: 6 per-word events without `\pos` stacked from y 929 down to y 1662 (`\an5`) and to y 1901 (`\an2`), far past the band.
10. **WrapStyle 0 re-wraps.** libass wraps a long positioned event onto more lines.
    - Tested: a long positioned event wrapped to 3 lines (y 804-1129) and was still clipped at the sides. With WrapStyle 2 it stayed on 1 line.
11. **libass `\blur` cap.** `\blur B` renders a gaussian of σ ≈ 0.85 B, and libass clamps B at 100.
    - Tested: σ/B was 0.84-0.85 for B 10-100. B 150 rendered the same σ 85 as B 100. Ref 01's 60 px shadow at 4K (B 120) is therefore softer than asked, and captions.py warns.
12. **Found while testing timing.** This is not an overflow cause, but it is fixed in the same script. ffmpeg's `ass` filter gives libass `trunc(pts × time_base × 1000)` ms, which is 1 ms low on some frames. A start written on an exact centisecond (ref 04 §1 rule 2's floored cs) then shows 1 frame late.
    - Tested on 1200 one-frame events (lavfi colour source and x264 mp4): floored cs had 23 late or missing frames at 30 and 60 fps, 3 at 25 and 50, 1 at 23.976 (mp4); ceil − 1 had 0 at all 8 rates.
13. **A gate that only measures the ink it sees.** Checking that drawn ink stays inside the area cannot notice a word that is not drawn at all.
    - Tested: one word moved to `\pos(-900, …)` or to y 2100, and a whole chunk moved to y 2600, all passed the first gate (exit 0, same ink bbox as the good file, drift 0) in ass, plate and diff modes. §4 rule 2 (`missing_word`) now fails each of them.
14. **Sampled frames on an opaque render.** A plate or diff render can animate anything; reading only each word's first frames, middle and last frame skips the rest.
    - Tested: a 200% keyword pop on frames 112-118 of a 135-frame plate passed with sampling (69 frames read). Every frame (the video-mode default now) fails it: `outside_safe` on frames 112-118, 11869 px, right margin −118 px.
15. **Face tracks on another clock.** Face boxes were read as output frames whatever fps the face file had.
    - Tested: a 30 fps face track (face on from 1.0 s to 3.0 s) under 60 fps captions left 2 chunks at mid over the face (box y 865-990, face y 600-1100) for about 1.2 s; a 25 fps crop_path under 30 fps captions left a chunk at mid while the face was still on screen. Both exited 0 with no warning.
16. **Two encodes' grain read as caption ink.** In diff mode the clean render and the edit are separate encodes, and grain differs between them.
    - Tested on testsrc2 at 1080×1920 with `noise=alls=N`: N 15 gave 2 `outside_safe` P0s at CRF 18 and 3 at CRF 23 (margins left −46, right −98, bottom −568) and N 25 at CRF 20 gave 8, all 5-13 px plus-shaped specks no word could be blamed for.

## 2. Safe areas (defaults; override per request)
Ink (the box defined in §3) stays inside [x0, x1) × [y0, y1). Profile by aspect W/H: ≤ 0.65 → 9:16, ≤ 0.90 → 3:4, ≤ 1.15 → 1:1, else 16:9. Override with `--profile`, `--margins l,t,r,b` (fractions) or `--safe x0,y0,x1,y1` (px). `caption_gate.py` takes the same flags in every mode once it knows the canvas (from `--canvas`, the layout, PlayResX/Y or the video), and otherwise reads the layout's `safe` block.

| Profile | Margins L / T / R / B | 1080×1920 | 1080×1440 | 1080×1080 | 1920×1080 |
|---|---|---|---|---|---|
| 9:16 | 6% W / 168 of 1920 / 12% W / 590 of 1920 | x 65-950, y 168-1330 | | | |
| 3:4 | 6% / 6% / 6% / 10% | | x 65-1015, y 87-1296 | | |
| 1:1 | 6% / 6% / 6% / 8% | | | x 65-1015, y 65-993 | |
| 16:9 | 5% / 5% / 5% / 10% | | | | x 96-1824, y 54-972 |

- The 9:16 band y 168-1330 is ref 04 §1 rule 8 (HF vertical.md), scaled by H/1920 on other 9:16 sizes.
- The 12% right margin is a design choice for the action rail, which ref 04 left without a width. It leaves 885 px of ink width; minus the halos that is about 843 px of text, close to ref 01's 80% W (864 px).
- The 3:4, 1:1 and 16:9 margins are design choices. 16:9 uses SMPTE title-safe (5%) plus a 10% bottom for player controls.
- Tested: `caption_gate.py --ass … --fps 30 --safe 0,0,1080,400` with no `--canvas` used to pass silently; it now applies the flag to the PlayRes canvas and fails (`outside_safe`).

## 3. Layout rules (`scripts/captions.py`)
1. **Font gate.** Refines ref 01 §3 Font (old: "fallback Montserrat ExtraBold, then Arial Black", unchecked).
   - Resolve `--font`, then env `CLIP_FONT`, then `--fontsdir`, then the OS font dirs. Fall back to ExtraBold, then Arial Black, with a warning; the layout then measures and names that font, so it stays consistent.
   - Exit 1 when:
     - the font is not found, or cannot be loaded (Pillow plus its sfnt tables);
     - `--fontname` is not the font's legacy family (nameID 1). The PostScript name and the typographic family are rejected too, because §1 rule 8 shows libass resolving them to other fonts;
     - a caption character has no glyph in the cmap (`--missing-glyph drop` removes it instead).
   - The ASS Fontname is the legacy family. With `--ass`, the font file is copied to `<ass folder>/fonts/` (`--no-font-copy` skips it) and the layout gets `burn` = {`cwd`, `fontsdir`, `filter`}. Burn by running ffmpeg in `burn.cwd` with `-vf <burn.filter>` (for example `ass=captions.ass:fontsdir=fonts`), as ref 03 §4 rule 8 says. Never paste the absolute `font.fontsdir` into a filter by hand.
   - Emoji are dropped with a warning (ref 01: stickers are PNGs). Emoji means the emoji code-point ranges (now including ‼ U+203C and ⁉ U+2049), or a symbol (Unicode So) the font has no glyph for. Symbols the font draws (° © ® ™) stay. Text is normalised: NFC, straight quotes, ALL CAPS, `{}\` replaced.
   - Tested:
     - missing font, typo Fontname, `Montserrat-Black`, `Montserrat`, a non-font file and CJK text each exit 1;
     - `--missing-glyph drop` and emoji text exit 0 with warnings;
     - `72°F`, `©2026`, `WOW™` and `R&D®` keep their symbols (before: `72F`, `2026`, `WOW`, `R&D`);
     - `LET'S GO ‼` now drops ‼ and exits 0 (before: exit 1, `glyph_missing`);
     - the burn filter ran in ffmpeg with exit 0 both relative (`ass=c.ass:fontsdir=fonts`) and escaped absolute (`fontsdir=C\\:/Windows/Fonts`). The raw absolute value failed with "No option name near 'WindowsFonts'".
2. **One size, two numbers.** Refines ref 04 §1 rule 4 (old: "×1.379" for Montserrat only).
   - em = cap_frac × H / (sCapHeight/unitsPerEm); `\fs` = em × (winAscent + winDescent)/unitsPerEm. Both are read from the font, so another font keeps the 3.3% H cap.
   - The layout JSON gives both: `em_px` for em-sized text engines and `ass_fs` for libass only.
   - Tested: em 90.51 px and `\fs` 124.82 at 1920 H; em 67.89 and `\fs` 93.61 at 1440; em 50.91 and `\fs` 70.21 at 1080.
3. **Measured ink, placed like libass.** Refines ref 04 §1 rule 5 (old: "getlength(line) at the em × 1.02 (ASS) or × 1.14 (EffectCraft, unmeasured) + 2·`\bord`").
   - Each word's ink is Pillow's tight ink at the same threshold (alpha > 24/127) relative to the advance-box left and the baseline.
   - libass places an `\an5` event with the advance box centred on `\pos` x and the win box centred on `\pos` y, so baseline = y + em·(winAscent − (winAscent + winDescent)/2)/unitsPerEm (0.4195 em; ref 04's 0.304·`\fs`).
   - Tested: ±1 px on 16 strings (§1 rule 2). Pillow's `getbbox` is not tight ink; it gave a 32 px "I" where libass drew 22.
4. **The box counts everything that can draw ink.**
   - box = ink + stroke (`\bord`, never scaled below 1×) + the halo pad, scaled about the anchor by the largest entrance scale (max of entrance_from, entrance_peak, 1).
   - Halo pad: a blurred glyph is never denser than a blurred half-plane at the same distance. So the composite of shadow (black, σ = 0.85 × blur) then glow (keyword colour), over #808080, bounds the halo; the pad is the largest distance where it still reads > 24. It is computed per colour and per shadow opacity, plus any shadow offset on its side.
   - Tested: 21.13 px at 1920 H with ref 01's shadow (blur 0.667 em, 55%) and glow (blur 0.222 em, 70%). The bound is conservative: where the layout put a box on the safe edge, the rendered ink stayed 10-29 px inside it (1080×1920 cases), and the gate saw 0 px of drift on every checked frame of the 15 positive cases.
5. **Fit by re-chunking; only a lone word scales.** Refines ref 04 §1 rule 5 (old: "A lone word > 0.80 W may scale to ≥ 0.85×", silent below that).
   - A line fits when its padded box is ≤ the safe width and its text (advance + 2·stroke) is ≤ 0.80 W.
   - A chunk is 1 line if it fits, else 2 lines split at argmin |w1 − w2|, but only if the 2-line block is no taller than the safe area. Else the longest prefix that fits stays and the rest becomes the next chunk.
   - A lone word that does not fit scales to fit. Below the 0.85 floor it still scales, so it never overflows, and a warning names it. A block that is still too tall or wide scales in steps of ≤ 2% until it fits. Stroke and halo pads do not shrink with the scale, so one proportional step was not enough.
   - Chunks come from the tokens' `brk` flags (hard cap 6 words), else ref 01's rules: punctuation, gaps > 0.25 s, 4 words.
   - Tested at 1080×1920:
     - `UNBELIEVABLEEEEEEE` scaled to 0.736, `SUPERCALIFRAGILISTIC` to 0.720 and `SUPERCALIFRAGILISTICEXPIALIDOCIOUS` to 0.416, each with a warning.
     - `INTERNATIONALLY` scaled to 0.888.
     - LLM chunks of 6 long words were re-chunked from 3 chunks into 9, 4 of them 2-line.
     - At 1080×1080, SUPERCALIFRAGILISTICEXPIALIDOCIOUS scaled to 0.764; at 1920×1080 nothing needed to scale.
     - `--safe 65,900,950,1060` (160 px tall) on HELLO WORLD THIS IS FINE gave 3 one-line chunks. Before, it stopped with "internal: a word box leaves the safe area by 8.0 px".
6. **Line 2 clears line 1's ink.** Refines ref 01 §3 (old: "line 2 sits directly under line 1 (line gap 0.15 em)").
   - Line 2's baseline sits line_adv = (cap + 0.15 em) below line 1's, or lower when the stroked ink of the two lines would come closer than a plain caps pair does. A Q tail, a comma or the top of a $ can cause that. So a caps-only pair keeps ref 01's exact gap.
   - Tested: `QUICK, JUMPY / QUARTZ, $900` had 11.3 px of overlapping ink boxes and fills touching in the render. Line 2 now sits at y 1063.9 instead of 1036.9, the stroked ink gap is 5.7 px, and no row between the lines holds fill pixels.
7. **Place, then clamp.**
   - Lines are centred on W/2; the block shifts sideways only as far as the safe area needs.
   - mid: first baseline at 50% H.
   - low: on 9:16, block bottom on the band bottom (ref 04 §1 rule 8); elsewhere, first baseline at 72% H.
   - high: block top on the safe top.
   - scan: when a face meets mid, low and high, the clear baseline nearest mid on an 8 px grid over the whole safe band (design choice).
   - Every position is clamped into the safe area.
   - Tested: 2-line chunks at the 9:16 low position ended 10-11 px above the band bottom (measured ink, y ≤ 1320).
8. **Face avoidance with the real box.** Refines ref 04 §1 rule 7 (old: "Low (72% H) when it meets the union of face boxes").
   - The padded block box is tested against every face box shown in [start_f, end_f), using the eyes-to-chin part: box top + 30% h, grown 5% (design choice, `--eyes-frac`, `--face-pad`).
   - Order: mid, low, high, scan. If no height in the band is clear, captions.py exits 1 (`face_cover`). `--allow-face-cover` accepts the least overlap with a warning, and the gate then fails it.
   - After a moved chunk the block returns to mid only when this chunk and the next are both clear; a cut (`cuts` in the tokens file) resets that.
   - Faces come as face_track.py's `path.json` (`kind: crop_path`: the subject box mapped through the per-frame crop to canvas px; its `out` must have the canvas aspect, another size is scaled), grade_gate.py's `{fps, boxes: [[f, x0, y0, x1, y1] | [f, null]]}`, `{frame: [x, y, w, h]}` or `[[f, x, y, w, h]]`. Each box holds until the file's next entry.
   - A file that names its fps is remapped to the caption clock by time: output frame = event_frame(f / file_fps, fps). Forms without an fps are read as output frames.
   - Each chunk's face regions go into the layout JSON (`faces`), so the gate can check the ink against them.
   - Tested:
     - a face over the centre of 9:16 sent 7/7 chunks low (and 5/5 from a face_track crop_path);
     - a face low on 9:16 sent 5/5 high;
     - a face over the centre of 16:9 sent 5/5 low;
     - a two-shot whose faces meet mid, low and high: the block went to scan at y 712-902 with 0 overlap (before: high, 59255 px² on a face, exit 0);
     - a 30 fps face file under 60 fps captions now gives the same positions as at 30 fps (mid, low ×4, mid) with 0 chunks over the face; a 25 fps crop_path under 30 fps sends its chunk low (y 1213-1330);
     - a face covering the whole band exits 1, or 0 with `--allow-face-cover`;
     - on a 45 s, 60 fps clip with a face drifting down, chunks went mid, low and high with 0 frames outside the safe area and 0 face cover.
9. **Keyword guard per chunk.** Refines ref 04 §1 rule 6 (old: any one-word keyword from the list stays white).
   - The list now holds all 49 words; THE was missing.
   - An isolated coloured function word turns white. A word inside a run of 2+ neighbouring tokens of the same colour keeps its colour: ref 01's yellow WHATEVER I DO, or a second speaker's whole magenta chunk.
   - Tested: green THE turns white; yellow WHATEVER I DO and magenta WHAT ARE YOU DOING keep every word coloured. Before, DO and ARE turned white.
10. **Timing.**
    - Times are ceil(100·k·den/num) − 1 cs (§1 rule 12). Refines ref 04 §1 rule 2 (old: floored cs `100*k*den//num`).
    - Two chunks whose first words appear on the same frame are merged when the merged chunk fits. Otherwise the first chunk is held 1 frame and the next starts 1 frame late, with a warning.
    - A chunk pushed to frame N or later is dropped, with a warning naming its words. Tokens starting at or after frame N are dropped with a warning.
    - Tested: 5 one-word `brk` tokens all at 1.9 s in a 60-frame clip became one 2-line chunk on frames 56-60. Before, they flashed for 1 frame each and END landed on frame 60, never shown.
11. **ASS that libass cannot rearrange.**
    - Header: PlayResX/Y = canvas, WrapStyle 2, ScaledBorderAndShadow yes, Style Bold 0, Spacing 0, Alignment 5, margins 0.
    - Each event carries `\an5\pos(...)\fs..\fsp0\shad0\q2`. Layer 0 is the shadow, layer 1 the glow (coloured words only), layer 2 the fill, with ref 04 §1 rule 3's entrance.
    - Typed tokens (`type`: true or seconds; asterisk tokens like `*LAUGHS*` by default; ref 01 §3 stage directions) get one override block per character, `{\alpha&HFF&\t(t,t+1,\alpha..)}`, with letter i of n at i/n of 0.5 s, on every layer. The event keeps one `\pos` and one advance, so the box is the same. Ref 04 §1 rule 12's fully-typed floors are warned.
    - A token's `shadow` (0-1) sets its whole chunk's shadow opacity, ref 04 §1 rule 11's 75% fallback; the halo pad follows it.
    - The event Name `c<chunk>w<word>` lets the gate name the word.
    - Tested: a typed `*LAUGHS*` and a 75% shadow chunk gated with `--all-frames` at 0 px drift and exit 0.
12. **Layout JSON for EffectCraft.** Refines SKILL path A (old: "per-chunk text layers", positions unspecified).
    - One text layer per word, at `baseline_center` (centre-justified point text) or `origin` (left-justified), font size `em_px` (already × scale), visible on frames [appear_f, end_f) and fully drawn from `full_f`.
    - The entrance scales about `anchor`. `box` is the ink the gate allows; `box_ink` is where the gate expects the word's own ink.
    - Do not re-flow text inside the editor (no paragraph boxes, no auto-size).
    - Untested here: EffectCraft's text widths against Pillow. Gate the EffectCraft caption-only render with plate mode (§4).

## 4. Gate (`scripts/caption_gate.py`)
1. **Real pixels, every distinct state.**
   - ass mode renders the ASS alone on #808080 (`color` source in rgb24, `select`, then `ass=...:fontsdir=...`). ffmpeg runs in the ASS folder with the bare ASS name, and every value is escaped for both filtergraph levels, so an apostrophe, comma or bracket in a job path renders.
   - ass mode reads each event's first 4 frames (the entrance and its peak), middle and last frame, plus each layout word's `full_f`; `--all-frames` reads every frame. The gate warns when an event moves or rescales beyond the entrance (`\move`, or 3+ geometry `\t`).
   - plate mode reads an editor's caption-only render over `--bg`. diff mode reads glyph ink, `|edit − qc/NN/grade.mp4| > 100`, minus small blobs (rule 5), with accent spans given in `--exclude`.
   - Both video modes read every frame by default. `--sample` reads only the layout's sampled frames, with a warning.
   - Video frames are decoded with the BT.709 tv matrix named.
   - Tested:
     - sampled and all-frames ass runs gave identical margins on 3 cases (19/16/277, 24/21/10, 29/26/272 px);
     - the 45 s, 60 fps, 116-word clip: layout in 0.9 s, ass gate 613 frames in 13.8 s, plate gate (all 2700 frames) in 58.9 s, diff gate (all 2700 frames) in 73 s, all 0 P0;
     - the uint8 difference (cv2.absdiff and channel max by slices) cut a 135-frame diff run from 17.7 s to 7.0 s;
     - a job folder named `it's job, [x]` passes. Before, an apostrophe gave "Error parsing filterchain" and exit 1.
2. **Every expected word is drawn (`missing_word`, with `--layout`).**
   - On each checked frame from a word's `full_f` to `end_f − 1`, its `box_ink` must hold ≥ 12% strong ink.
   - Strong ink means max|px − bg| > 64 in ass and plate modes, and the glyph ink (|edit − clean| > 100) in diff mode. For any footage pixel, either the white fill or the black stroke differs by more than 100 from it.
   - Neighbours' shadow halos stay under the strong threshold, so a missing narrow word is not covered by them.
   - Without a layout, ass mode fails an event whose `\pos` is off the canvas (`off_frame`), or one with no strong ink within 0.7 × its `\fs` of its `\pos` on its settled frames (`event_no_ink`).
   - Tested:
     - lowest coverage on correct renders: 0.578 (ass, the $/% case), 0.661 (plate), 0.707-0.709 (diff, clean and grainy); on the 45 s clip 0.611 (ass), 0.597 (plate) and 0.506 (diff);
     - 0.00 on every negative: a word at x −900, a word at y 2100, a chunk at y 2600, plate and diff renders of an off-frame word.
     - The 12% threshold is a design choice inside that 0.00-0.506 gap.
3. **Faces (`face_cover`).** Any ink inside a chunk's face regions (from the layout), or inside the per-frame regions of `--faces`, fails.
   - Tested: a face-clear chunk moved back onto the face failed (`face_cover`, plus `missing_word` for the empty spot). The two-shot scan layout passed with `--faces`. The unavoidable-face case (`--allow-face-cover`) failed.
4. **Length and decode (video modes).**
   - `length_mismatch`: the video's frame count differs from the layout's, naming the word spans past the end.
   - `decode_short`: fewer frames decoded than asked.
   - A diff `--clean` with another frame count exits 2.
   - Tested: a plate render of 48 of 71 frames failed (`length_mismatch`: 1 word span past the end). Before, it passed with no warning.
5. **Diff mode judges glyph ink only.** Ink is |edit − clean| > 100 (`--diff-thr`), minus 8-connected blobs smaller than `--min-blob`. The default is 24 px at a 1080 px short side, scaled by area (11 px at 720).
   - Halos are left to ass and plate modes, which measure them on #808080. Over footage a shadow halo reads differently from that model, and the edit's own encode changes footage pixels around the captions.
   - Tested on the 45 s clip, edit and clean encoded separately (x264 veryfast, CRF 18) over testsrc2:
     - the first rule (> 40 after a 3×3 opening) gave 14 `outside_safe` P0s, up to 10 px below the band;
     - those pixels lay 21-36 px below the glyph ink (ink bottom y 1309, differences down to y 1345) and included brightenings up to 48 on the grey scale, which a black shadow cannot make: encoder spread, not ink;
     - with glyph ink the run passes, with glyph margins of 25/20/21/18 px.
   - Tested, grain:
     - glyph-ink blobs more than 40 px from the active word boxes were at most 4 px (noise 15 at CRF 23; noise 25 at CRF 20 with preset medium; two encodes each);
     - the smallest caption component, a period's stroke ring alone (its fill matching the footage), is 94 px at em 50.9 (1080 H), 111 px at 1280 H and 357 px at 1920 H. The 24 px default sits between them (design choice);
     - the grain repros of §1 rule 16 (noise 15 at CRF 18 and 23, noise 25 at CRF 20) now pass with 0 P0, and a naive or off-frame edit still fails.
6. **P0s (exit 1):**
   - `outside_safe`: any ink pixel outside the safe area.
   - `edge_clipped`: ink in the outer 2 px of the frame.
   - `missing_word`, `off_frame`, `event_no_ink`: rule 2.
   - `face_cover`: rule 3.
   - `length_mismatch`, `decode_short`: rule 4.
   - `no_ink`: nothing drawn at all.
   - `playres_mismatch`.
   - `font_fallback`: without `--layout`, a `fontselect` face that is not the requested family itself (`Montserrat` → Montserrat-Regular fails as well as `Montserrat-Black` → ArialMT).
   - `font_not_layout`: with `--layout`, any font other than the layout's PostScript name, which also catches per-glyph fallback.
   - Each finding gives the frame run, the worst frame, the margins and the event or word (from the layout boxes, else the nearest `\pos`).
   - A render or decode tool failure (no frames out of ffmpeg) exits 2 (`render_failed`), not 1.
   - `model_drift` is a warning in ass and plate modes: ink more than 2 px outside the layout's predicted boxes, meaning an EffectCraft builder would read a wrong layout. Diff mode skips it, because halos over bright footage read wider than the #808080 model.
7. **Review sheet.** `<qc>/caption_gate_sheet.png` shows the 6 worst frames: safe area in green, ink outside it in blue (no caption palette colour), ink bbox in yellow, plus `caption_gate.json`.
8. **Self-tests:** `captions.py --self-test` (layout level, 4 s here) and `caption_gate.py --self-test` (pixels, about 2 min here).
   - Tested: captions.py 38/38 checks passed (16 layout cases, 10 rule checks, 12 CLI exit-code and burn checks). caption_gate.py 39/39 passed:
     - 15 positive ASS cases (1080×1920, 1920×1080, 1080×1080, 1080×1440; long words, long sentences, numbers/$/%, low 2 lines, faces incl. a crop_path, entrance overshoot counted, a two-shot scan, descender lines, typed stage directions with a 75% shadow), all exit 0 with drift 0;
     - plate, diff and grainy-diff positives and an apostrophe/comma/bracket job path exit 0; a broken ffmpeg exits 2;
     - 19 negative controls exit 1. The first group: naive long words, naive 72% H 2-line blocks, 9:16 y 1330 on 16:9 (`no_ink`, `off_frame`), PlayRes 1920×1080 on 1080×1920, a Fontname typo, the prefix family `Montserrat` without a layout and an uncounted 125% entrance.
     - The rest: an off-frame word (left, below, below without a layout), `--safe` without `--canvas`, a chunk moved onto a face, an unavoidable face cover, a naive plate render, a plate off-frame word, a plate pop between samples, a truncated plate, a naive diff edit and a diff off-frame word.

## 5. What stays manual
- Ref 04 §1 rule 10 (presence/stale/sync against the editor's own fill render) and rule 11 (the WCAG legibility sample over the graded frame) are not measured by these scripts. Run them as ref 04 says. When rule 11 fails, set `"shadow": 0.75` on a token of that chunk and re-run captions.py; never edit the ASS by hand.
- Stickers and accents are not captions: they are excluded from diff mode with `--exclude` and checked by their own gates.

## Workflow (both editors)
1. Write the token file (ref 04 §1 rule 1 plus output-second times, `c`, `brk`, and `type` / `shadow` where needed). Then run `captions.py --tokens ... --canvas WxH --fps F --frames N --faces clips/NN/path.json --ass clips/NN/captions.ass --layout clips/NN/captions_layout.json`. It exits 1 on a font or glyph problem or an unavoidable face: fix that, never bypass it.
2. Path B: burn with the layout's `burn` block, running ffmpeg with cwd = `burn.cwd` and `-vf <burn.filter>` (chain other filters after it with a comma). Path A: build the per-word text layers from the layout JSON.
3. Gate before delivery: `caption_gate.py --ass ... --layout ... --qc qc/NN` (path B), or plate mode on the EffectCraft caption-only render (path A). Then diff mode on `edited/NN-slug.mp4` against `qc/NN/grade.mp4`, with the accent spans excluded. Fix every P0 and read the sheet.
