# 01 - IShowSpeed clipping-short style (user target style)

Studied 2026-10-31 from the three reference Shorts the user sent ("these are the example type video"). This file **overrides `SKILL.md` step 5** (karaoke captions, lower-middle). Captions here are centred, build word by word, and use semantic keyword colours.

## Sources

| Ref | URL | Channel / title | Length | Canvas | Footage |
|---|---|---|---|---|---|
| 1 | https://youtube.com/shorts/tnE-1xs64ls | deagzzzshorts, "No way she did that" (124M views) | 38.87 s | 1080x1440 (3:4), 60 fps | multi-cam studio shoot (white cyc) |
| 2 | https://youtube.com/shorts/GbkSKbdsxZs | wShortzzzz, "Rule No 1 Never doubt IShowSpeed" | 38.67 s | 2160x2880 (3:4), 60 fps | IRL stream + vlog cam, upscaled, soft |
| 3 | https://youtube.com/shorts/LCS-pKmkb88 | deagzzzshorts, "Try to be slightly normal" (Speed x MrBeast, 146M views) | 52.22 s | 1080x1440 (3:4), 60 fps | 16:9 YouTube/stream footage, centre-cropped |

The full studies are in `C:/Users/aryan/clipping-edit/analysis/refs/ref{1,2,3}.md`. The local media and contact sheets are in `C:/Users/aryan/clipping_jobs/refs/` (`ref*.mp4`, `ana1/`, `ana2/`, `ana3/`).

## Per-ref summary

**Ref 1 (challenge, studio).**
- Opens cold mid-sentence on the premise ("So you're telling me whatever I do, you can do better?"), with the caption up by 0.1 s.
- The arc repeats challenge, attempt, reaction about 5 times. Shots average about 1.5 s.
- Captions are small, about 3% H cap height, centred at y about 50%, with a word-by-word build.
- Colour is white plus semantic accent words (green, yellow, magenta, red). There is no stroke; a wide soft dark shadow and a same-colour glow keep the text readable.
- Stage directions appear in asterisks (*BACKFLIPS*, *FAILS*).
- Framing comes from choosing between a close camera and a wide camera, with no visible tracking.
- Accents (about 6 per 40 s):
  - 2-3 frame chroma-green flashes on landings
  - a white flash before the shock
  - a red wash on the fail
  - motion-blur whips
- Ending: a meme freeze with a zoom-blur entry, a sepia grade and a 💀 emoji, held for 1.5 s. (Ref-1 specific; NOT a default - see Ending row.)
- Very bright high-key grade (luma mean 209). Colour is selective: the background stays white and the wardrobe and skin pop.
- The music bed runs throughout.

**Ref 2 (challenge, IRL stream).**
- Cold open on the boldest claim. A yellow flash hits the first cut at 1.13 s.
- Average shot is about 2.2 s, with long holds only on the climax attempt.
- Captions are Montserrat Black caps, cap height about 3.7% H, centred at y 47% / 52%, with a word-by-word build.
- Text is white with a thin dark stroke and a soft shadow. 1-3 keywords per chunk take green, yellow, red or teal.
- Text is LLM-cleaned: whisper errors are fixed, "!!" is added, and there are asterisk directions.
- Colour-tint flashes (40-60% opacity, 0.3-0.5 s decay) land on about half of the cuts.
- A "+1" sticker pops at the climax.
- Ending: a meme outro with a 3D emoji fly-in, particles and a yellow/red title card at y 80%, then a 0.3 s fade to black.
- The music is muted for the tension stretch and comes back as a build-up before the climax.
- Grade is mild (luma 133, sat 58), and the image is soft (Laplacian about 22). We must beat it.

**Ref 3 (MrBeast challenge).**
- Cold open on a reaction close-up with "*BARK*". The premise lands by 1.3 s.
- Jump cuts of 0.3-1 s in the first 3 s, then shots of 2-2.5 s, with holds of up to 9 s on the wide action.
- Captions are smaller chunks (1-3 words) placed at y about 25% (just under the face) or y about 75%.
- Each chunk takes one colour from a rotating palette (white, red, lime, yellow, cyan). There is a strong outer glow in the same colour and a blur-in entrance over 2-3 frames.
- Labels: an "ISHOWSPEED" pointer tag over the tiny subject in wide shots, and a green "+$100,000" pop.
- Green or magenta tint flashes land on punchlines, with one white flash-in and one whip into the action.
- Ending: a hard cut on the payoff, with no outro.
- Brightest and most saturated grade of the three: luma 154, sat 93. Teal and green are boosted, plus bloom, a vignette and strong sharpening.

## Where the refs agree (adopt as-is)
- Full-bleed crop: no letterbox, no blur bars, no stacked layout, **no persistent hook/title banner**.
- Cold open: dialogue or reaction at frame 0, the caption on screen by 0.1 s, and the premise stated within 2-2.5 s.
- Many moments from one source, kept in chronological order and built into one escalating arc: setup, attempt, fail/reaction, payoff. Dead air is cut.
- Captions:
  - ALL CAPS heavy geometric sans (Montserrat Black).
  - Small: cap height about 3-3.7% H.
  - Each word appears at its whisper start minus 0-2 frames.
  - Entrance is a 2-4 frame fade or blur-in, with **no bounce** and no karaoke box.
  - Emphasis comes from semantic colour, plus a same-colour glow.
- Asterisk stage-direction or SFX captions in stretches with no speech.
- Accents are full-frame colour-tint flashes and directional motion-blur whips, used on big moments only.
  - No beat shake, no slow motion, no constant zoom punch-ins.
- Two people: a wider crop holds both. Never use a split screen.
- A continuous music bed sits under the speech and comes up in the gaps.
- The grade is brighter and more saturated than the source footage, and sharpened.
- A small watermark is centred at y about 84-86%.

## Where the refs disagree (default chosen)

| Topic | Ref 1 | Ref 2 | Ref 3 | **Default** |
|---|---|---|---|---|
| Canvas | 3:4 | 3:4 | 3:4 | **1080x1440 3:4, 60 fps** (all refs agree; user said match these refs). `--aspect 9:16` gives 1080x1920 only on request |
| Caption y | 50-52% | 47% / 52% | 25% or 75% | **centre at 50% of H**; move to 72% if the text box overlaps the mouth or eyes box of a tracked face |
| Words per chunk | 2-6, word build | 2-6, word build | 1-3, chunk at once | **2-4 words (max 6), max 2 lines, word-by-word additive build** |
| Outline | none, wide soft shadow | thin dark stroke + shadow | glow + thin shadow | **thin dark stroke (4% of font size) + soft black shadow (blur ~1x cap height, 55%) + same-colour glow on accent words** |
| Colour use | white + accent keywords | white + 1-3 keywords | one colour per chunk | **white base + 1-3 semantic keywords; a whole chunk may take one colour for exclamations/second speaker** |
| Flash density | ~6 / 40 s | ~50% of cuts | 3-5 / min | **1 accent per 6-8 s (5-8 per 45 s), never more than 40% of cuts** |
| Pace (avg shot) | 1.5 s | 2.2 s | 2-2.5 s | **1.8-2.2 s average; 0.3-1 s jump cuts in the first 3 s; holds up to 7 s only on the action/climax** |
| Ending | meme freeze + 💀 | emoji fly-in + title + fade | hard cut | **normal clean ending by default** (hard cut on the payoff/last reaction line, ref 3). Meme freeze + 💀 ONLY when the clip is a comedic fail/"no way" reaction moment that fits it (user 2026-10-31: not every clip has the skull) |
| Music in tension | stays | muted, then build-up | stays | **continuous, ducked**; optional 2-4 s mute before the climax |
| Grade level | luma 209 (studio) | 133 (mild) | 154, sat 93 | **ref 3 targets** (see grade) |
| Close-face size | 18-25% H | 20-28% H | 25-35% H | **24% H (range 20-30%)** |

## STYLE SPEC (measurable)

### 0. Hard user rules (non-negotiable)
1. **Final file is ≤ 60.0 s.** Target 35-55 s. The render step asserts `duration <= 59.5 s` with ffprobe and re-cuts if it fails.
2. **Face tracking is always on.** Every speaking shot is face-tracked and the crop is never a blind centre crop. The exception is a deliberate wide action shot that keeps all subjects in frame.
3. **Colour correction must look sharper, brighter and more colourful than the source.** Measure source against output on the same frames. All three must hold:
   - mean luma +10% or more
   - median HSV saturation +25% or more
   - Laplacian variance (720p) ×1.4 or more
4. **Captions may use EffectCraft or whatever fits best.** The recommended tool is below.

### 1. Canvas and layout
- 1080x1440 (3:4) 60 fps, h264 CRF 18 or lower, `yuv420p`, AAC 192k, 48 kHz.
- 60 fps if the source is 50/60, otherwise 30.
- Full-bleed crop from the source. No letterbox, blur bars, stacked layout or split screen.
- No hook banner and no persistent title.
- Optional watermark: centred at y = 85% H, cap height about 1.5% H, white at 35% opacity.
- Keep stream overlays (viewer count, chat) only if cropping them out would cut the subject.

### 2. Hook (first 3 s)
- Frame 0 is mid-sentence on the strongest premise or claim line, or on a reaction close-up. There is no intro card, no fade-in and no title.
- The premise must be spoken by t ≤ 2.5 s.
- The first caption is visible by t ≤ 0.1 s.
- 1-3 jump cuts of 0.3-1 s in the first 3 s. A colour flash (yellow or white) may hit the first cut.
- The music bed is at full level from frame 0.
- The "hook text" is the caption itself. Do not add a hook banner (none of the refs do). If the clip needs context, add one asterisk line (for example "*SPEED CHALLENGES HER*") in the caption style for ≤ 1.5 s.

### 3. Captions
- **Font:** Montserrat Black (`C:/Windows/Fonts/Montserrat-Black.ttf`, installed). Fallback: Montserrat ExtraBold, then Arial Black.
  - ALL CAPS, tracking 0, straight apostrophes.
- **Size:** cap height 3.3% H (about 63 px at 1920), so font size about 90 px at 1920 (Montserrat cap height ≈ 0.70 em). At 1440: about 68 px.
  - Max line width 80% W. Max 2 lines; line 2 sits directly under line 1 (line gap 0.15 em).
- **Position:** centred horizontally, first-line baseline at y = 50% H ±2%.
  - If the caption box intersects the tracked face box (eyes to chin), move the block to y = 72% H.
  - Never cover the mouth.
- **Chunking:** split on whisper word timestamps and on punctuation or pauses (gap > 0.25 s).
  - 2-4 words per chunk (max 6); single-word chunks are allowed for punch words.
  - A chunk stays until the next chunk starts, or until 0.6 s after its last word if there is silence.
- **Reveal:** additive word-by-word. Each word appears at `word.start - 1 frame`.
  - Entrance over 3 frames: opacity 0 to 100%, scale 90 to 100%, blur 6 to 0 px.
  - No bounce and no karaoke recolour. The exit is a hard cut.
- **Colour:** base white `#FFFFFF`. Each chunk gets 1-3 keyword(s) in a semantic accent colour:
  - green `#2BFF2B`: positive or emphasis (BETTER, INSANE, WIN, LET'S GO)
  - yellow `#F5FF00`: setup or shock (WHATEVER I DO, WHAT THE F**K)
  - red `#FF1A1A`: negatives or fails (CAN'T, DON'T, LOST, *FAILS*)
  - magenta `#FF2BD6`: the second speaker (their whole chunk may be magenta)
  - cyan `#40E0E0`: money or numbers, or an alternate colour so two chunks in a row don't share one
  - A whole chunk may take one colour for exclamations. Avoid the same accent colour on 3 chunks in a row.
- **Stroke, shadow and glow:**
  - dark stroke `#000000` at 4% of font size (about 4 px at 90 px)
  - soft black shadow, offset 0, blur about 60 px at 55% opacity
  - accent words also get an outer glow in their own colour (blur about 20 px, about 70% opacity)
  - no background box
- **Text cleanup (LLM pass):**
  - fix whisper errors
  - censor profanity with asterisks (`F**K`, `SH*T`)
  - add "!!" on hype lines
  - slangy register is fine (TRYNA, BRO, DAWG)
  - add missing non-speech moments
- **Stage directions:** 2-5 per short, in asterisks (*LAUGHS*, *FAILS*, *GOING FOR DUNK*, *HUGS*).
  - Coloured by sentiment.
  - Typed on letter by letter over 0.4-0.6 s.
  - Placed in speechless action stretches and on fails.
- **Emojis and stickers:** no inline emojis in captions. Stickers are PNG overlays: at most 1 climax pop (e.g. a green "+1" or "+$100,000" with glow, about 0.5 s) plus the optional ending 💀. In wide shots where the subject is tiny, an optional name pointer label (small yellow name plus a red down-triangle).

### 4. Face framing and tracking
- **Detector:** a face detector (MediaPipe / YuNet / InsightFace) on every frame, or every 2nd frame with interpolation. Identity is held by IoU or embedding, and the active speaker is chosen from mouth motion or diarization.
- **Smoothing:** a 1-euro filter or EMA (α ≈ 0.08 at 30 fps).
  - dead-zone 8% W
  - max pan speed 3% W per second
  - no zoom changes inside a shot
  - The result should read as a locked camera. Reframe with cuts, not fast pans.
- **Close crop (single speaker or reaction):**
  - face height 24% H (range 20-30%)
  - eyes at y = 28% H (range 22-35%)
  - face centre at x = 50% W ±10%
  - headroom may be tight; never cut the chin or the face sides
- **Wide crop:** when 2 or more people interact physically, or for action (tricks, dunks, running), use the widest crop that holds all bodies, with people at 45-60% H. One person may be edge-cropped in a two-shot. Captions then go to y 50%, offset toward the speaker by up to 10% W.
- **Alternation:** cut between wide/action and close/reaction framing. Every punchline or fail gets a reaction close-up within ≤ 1 s.
- **Source scale:** if the crop would upscale the source by more than 2.0x, widen to the maximum the source allows rather than blow it up. Sharpness beats tightness.

### 5. Effects (accents only on big moments)

| Effect | Spec | When | Max |
|---|---|---|---|
| Colour-tint flash | full-frame `#00FF00` / `#FF2BD6` / `#F5FF00` tint at 50-60% peak, 1-frame attack, 0.25-0.4 s decay, subject ghosted through | landing, impact, money, hugs, punchlines | 4 per 45 s |
| White flash | 1-2 frames of overexposure (luma > 230), decaying over 0.3-0.4 s | just before a shock reaction or on a shot start | 2 |
| Red fail wash | red-pink overlay at 65%, fading to 0 over 0.5 s, with a red *FAILS* caption | fail moments | 1-2 |
| Directional motion-blur whip | 2-6 frames (at 60 fps) of horizontal or vertical streak blur plus a ghost of the next shot | into an action section, or a big cut | 2-4 |
| Mild push-in | about 3-5% scale drift over a shot | on long holds only | n/a |

- In total, 1 accent per 6-8 s, and never more than 40% of cuts. Every other cut is a hard cut.
- **Never use:** beat shake, per-word zoom punches, slow motion, speed ramps or a split screen.
- **SFX:** one SFX per flash or whip (whoosh, impact, riser hit), each a different variant (see the user's unique-variant rule). Add an impact hit on the ending freeze (when one is used).
- **Ending (default = normal clipping ending):** hard cut right after the payoff line / last reaction, no trailing silence; ideally the last frame flows into a replay (ref 3). Most clips end this way.
- **Optional meme-freeze ending** (only when the moment is a comedic fail/shock reaction where it clearly fits; never automatic, user 2026-10-31):
  - 2-4 frame zoom/radial blur into a freeze of the biggest reaction face
  - warm/sepia high-contrast meme grade
  - one 💀 PNG (12% W, at mid-height, centre-left)
  - hold for 1.2-1.8 s, then hard end

### 6. Audio
- Dialogue is normalised to about -14 LUFS integrated, with true peak ≤ -1 dBTP.
- **Music bed:**
  - A hype/phonk/trap beat runs under everything from frame 0.
  - It is ducked about 10 dB under speech with sidechain ducking (attack 20 ms, release 300 ms).
  - It rises to about -20 dBFS short-term in speechless stretches.
  - Optional: mute it for 2-4 s of tension before the climax, bring it back as a build-up, and let natural sound or the crowd play on the climax itself.
- SFX peaks reach about -11 dBFS. The ending sting may sit up to 6 dB over the dialogue.

### 7. Colour grade (targets measured on output against source, same frames)
- **Brightness:**
  - mean luma (0-255) target 145-170 for normal footage
  - target at least 180 for bright studio or outdoor footage
  - never below 135 on non-night footage
  - whites may approach 240+; do not crush skin
- **Saturation:**
  - median HSV saturation target 85-105 (0-255), with selective vibrance so skin, wardrobe, grass, water and sky pop
  - neutral or white backgrounds stay neutral
  - skin hue stays 10-25° (no orange cast)
- **Contrast:** gentle S-curve (+10-15%) with deep blacks and no lifted-black haze.
- **Sharpness:**
  - Laplacian variance at 720p ≥ 1.4x the source
  - ≥ 70 on non-blurred frames (beat ref 2's 22)
  - apply the unsharp mask after scaling
- **Polish:** soft highlight bloom (blurred screen-blend at 12-18%) and an optional corner vignette at 20%.
- **Reference ffmpeg chain** (after the crop/scale to the output size):
  `eq=brightness=0.04:contrast=1.12:saturation=1.2,vibrance=intensity=0.3,colorbalance=rm=0.02:bm=-0.02,unsharp=5:5:1.0:5:5:0.0`, plus a glow (split, `gblur=sigma=20`, `blend=all_mode=screen:all_opacity=0.15`), plus an optional `vignette=PI/5`.
  - For upscaled sources (scale > 1.5x), denoise with `hqdn3d=1.5:1.5:6:6` before sharpening, use `scale=flags=lanczos`, and raise the unsharp amount to 1.3.
- **QC gate:** sample 1 frame per second from source and output and check the three ratios from the hard rules. If any check fails, raise that parameter and re-render.

### 8. Pacing and length
- Length: 35-55 s target, ≤ 60 s hard (≤ 59.5 s asserted).
- Average shot 1.8-2.2 s (range 0.3-7 s): fast jump cuts in the hook, holds only on the climax action.
- Remove dead air: gaps ≥ 0.3 s between phrases are cut unless they are a visual payoff.
- Speechless action stretches are ≤ 5 s each (up to 9 s for the main climax) and always carry music plus an asterisk caption.
- Structure: hook/premise (0-3 s), then setup, then attempts and reactions escalating 2-5 times, then the biggest reaction or payoff last, then the ending (clean hard cut by default; meme freeze only when it fits).
  - Moments stay in source order.

## Editing tool: EffectCraft (user choice, 2026-10-31) - SUPERSEDES the earlier libass recommendation

The user said: "for editing software, u can use effect craft". The edit (captions, zooms, flashes, stickers, optional freeze ending, grade) is built **by script in EffectCraft**, the same way as the AMV edits. Binary, build/render commands and EC gotchas: memory `amv-effectcraft-port` + amv-edit skill ref 19 (portable 0.16.0 `effectcraft-cli.exe`; run the update check first).

Split of work:
- **Python/ffmpeg (prep):** download, transcribe (word timestamps), pick moments, cut + concat the source segments to an intermediate (high bitrate / near-lossless, keep 60 fps), face detection -> smoothed crop path per frame (reset at camera cuts), caption chunk list with keyword colours, accent/SFX timeline, audio mix (dialogue -14 LUFS + ducked music + SFX).
- **EffectCraft (edit):** 1080x1440 60 fps comp; source layer with Position/Scale keyframes from the crop path (that is the face tracking); text layers per caption chunk (Montserrat Black, ALL CAPS, word-by-word build via per-word layers or text animators, stroke + shadow + glow on keywords); zoom punches, flashes/whips, sticker PNGs; grade on an adjustment layer (Brightness/Contrast, Hue/Sat or Vibrance, Unsharp/Sharpen, glow via blurred copy in Screen - remember adjustment-layer blend modes are ignored in EC, use CC Composite).
- **Render:** EC render at high bitrate (>= 30000 kbps), `--parts` if memory runs out; finish with ffmpeg mux of the mixed audio using `-c:v copy` (no second video encode, to keep it sharp); verify duration <= 59.5 s.
- **Fallback:** if EC cannot do something (e.g. colour emoji text), render it as a Pillow PNG and import it as a footage layer. ASS/libass captions are a fallback only if EC fails outright.

## QC checklist before delivery
- [ ] ffprobe duration ≤ 59.5 s; 1080x1440 3:4 (or 1080x1920 if 9:16 was asked for); audio present.
- [ ] Frame 0 has speech or a reaction; caption visible by 0.1 s; premise within 2.5 s.
- [ ] On 1 fps samples, the face is fully in frame on every close shot, eyes at y 22-35%, and the crop has no jitter (frame-to-frame centre delta < 0.5% W when there is no cut).
- [ ] Captions sit within ±2 frames of the whisper word starts, never cover the mouth, stay inside 80% W, profanity is censored, and accent colours are used.
- [ ] The grade ratios against the source pass (luma +10% or more, sat +25% or more, sharpness ×1.4 or more).
- [ ] Accent count ≤ 1 per 6 s, with no beat shake, no slow motion, and every SFX a distinct variant.
- [ ] The ending is a clean hard cut after the payoff (default) or, only where it fits, a meme freeze of 1.2-1.8 s; no trailing silence.
