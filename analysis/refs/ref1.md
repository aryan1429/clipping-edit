# Ref 1: "No way she did that" #ishowspeed #edit (deagzzzshorts, 124M views)

> Raw study notes. The "Rules for our pipeline" section was written per ref; where it disagrees with `skill/references/01_ishowspeed_clip_style.md` (which reconciles all three refs), ref 01 wins.

Source: `<job>/refs/ref1.mp4`. It is AV1, 1080x1440, 60 fps, 38.87 s long, with AAC 44.1k stereo audio. I looked at the 1 fps frames and at 10 fps dense sheets for 0-1.6, 3-4.6, 6.5-8.1, 9.3-10.9, 22.6-24.2, 26.4-28.0, 29.4-31.0 and 35.2-36.8 s. The sheets are saved as `<job>/refs/ana1/dense_*.jpg` and `sheet_0..2.jpg`.

## 1. Format and layout
- **Canvas is 3:4 (1080x1440), not 9:16.** The footage fills the whole frame. There is no letterboxing, no stacking and no blurred background. The source is a professionally shot multi-camera studio piece (white cyclorama, a black armchair, Speed in a Portugal #7 kit, a red-haired woman in magenta). It is not stream footage.
- **No hook banner and no persistent title text.** The only text on screen is the caption.
- **Watermark:** "@DEAGZZZSHORTS" is centred at about y = 85-86% of height. It is tiny (about 1.5% of height), white, about 30-40% opacity, and visible in every frame. A thin white bar sits at the same y. It is a constant overlay.
- In one frame (t = 2.0 s) a faint vertical seam shows at x of about 92%. It is a leftover from the edge of a shifted or scaled layer, so it is an artefact, not a design choice.

## 2. Structure and pace
- **Hook, 0-2.3 s:** Speed's close-up starts on frame 0 with speech straight away: "So you're telling me whatever I do, you can do better?" There is no intro, no title and no fade. Captions are on from 0.1 s. It works because the challenge premise is stated in the first 2 s.
- **Arc.** Each beat is a challenge, an attempt, then a reaction:
  1. 0-4.8 s: challenge set-up (Speed asks; reaction cutaway "Yeah" at 2.7 s; "Do this better than me, okay?" at 3.2-4.2 s).
  2. 4.3-7.5 s: Speed's backflip, shown wide, captioned "*BACKFLIPS*".
  3. 7.5-9.8 s: she copies it with no words; music carries this stretch.
  4. 9.8-11.5 s: "What the f**k" / "*LAUGHS*" reaction.
  5. 12.3-14.9 s: "Damn that was my one" and the next challenge, "Can you do this?"
  6. 15-20 s: second trick; "just don't twist it"; she does a cartwheel or aerial at about 19-20 s.
  7. 20.7-21.8 s: "DAMN.." with Speed holding his head in close-up; "Can you do the splits?" in her close-up.
  8. 22.2-25 s: Speed tries the split, "*GETS READY*", then "*FAILS*" on a red flash at 23.8 s.
  9. 25.8-29.5 s: she does a "*PERFECT SPLIT*"; "That's just insane"; "I'm sorry, that's just insane bro".
  10. 29.5-37.3 s: "Can you do this?"; a final trick; both laughing (32-35 s); Speed's shocked face at 35.5-37.3 s.
  11. 37.4-38.9 s: payoff freeze frame (see section 5).
- **Clip choice:** many moments from one long video, cut down hard. Dead time between tricks is removed. The order follows the original timeline, the story is one escalating challenge, and the reaction shots come from other camera angles.
- **Real cuts versus false positives:** analysis.json lists 172 "cuts", which is far too many. A frame-difference peak detector (diff > 25, ±9-frame NMS) finds about 27 events, and these are real cuts or transitions: 2.42, 3.15, 4.25, 6.92*, 7.53, 9.67*, 9.95, 10.98, 12.28, 13.38, 13.82, 16.38, 20.50, 21.13, 22.03, 22.87, 23.80*, 24.92, 25.83, 26.68*, 27.73, 29.57, 31.23, 31.82, 32.88, 35.45, 37.4. That is about 25 shots in 38.9 s, so **the average shot is about 1.5 s, ranging from 0.6 to 4 s.** The starred times are effect frames, not plain cuts:
  - The clusters 6.92-7.07 and 26.82-26.93 are a **chroma-green flash/transition**: 2-3 frames that are almost pure #00FF00 with the subject ghosted through (mean saturation jumps to 222 at 7.0 s).
  - 9.63-9.78 is a **white/overexposed flash** followed by a directional motion-blur whip.
  - 23.80-23.88 is a **red/pink colour wash** with "*FAILS*" in red.
  - 35.43-35.93 is a **motion-blur whip** into the reaction shot, then a zoom-blur into the freeze.
  - The many 0.01-0.05 s "shots" around 2.2-2.55, 7.4-7.7, 14.4-14.5 and 18.7-18.8 s are fast camera motion, whip blur or the impact frames of flips, not cuts.
- **Ending:** a hard stop on the meme freeze. It does not loop seamlessly, but the ending "Can you do this?" mirrors the opening challenge.

## 3. Captions
- **Font:** a geometric heavy sans in all caps. It looks like Montserrat Black/ExtraBold or Arial Black / Gotham Black. The letters are wide and tightly tracked, with straight apostrophes.
- **Size:** cap height is about 3% of frame height (about 22 px on a 720 px frame, about 44 px at 1440). A full line spans about 55-70% of the width. **The captions are small and clean**, nowhere near the giant 1-3-word MrBeast style.
- **Position:** centred horizontally. The first line's baseline is at **y ≈ 50-52% of height** in every shot, close-up or wide. Text often sits over the subject's chest or body. A second line, when there is one, sits just under it with almost no gap.
- **Chunking:** one phrase of 2-6 words per chunk, wrapping to 2 lines when needed: "WHATEVER I DO / YOU CAN DO BETTER?", "DO THIS BETTER / THAN ME OKAY?", "I'M SORRY / THAT'S JUST INSANE BRO". In two-line chunks the lines can differ in size; in "WHATEVER I DO" the first line is bigger.
- **Reveal:** **word by word, building up.** Each word appears at its spoken time and stays until the whole chunk clears. Each new word fades or pops in over about 2-4 frames, starting semi-transparent and soft. There is no bounce overshoot, no per-word box, and no karaoke recolouring of the active word.
- **Colour:** there is **semantic colour per word or phrase, fixed when the word appears**:
  - The base fill is white.
  - Key words take a solid saturated colour: green #2BFF2B for TELLING ME, DO BETTER, BETTER THAN ME, INSANE, DO THIS, THE SPLIT, PERFECT SPLIT; yellow #F5FF00 for WHATEVER I DO, *BACKFLIPS*, WHAT THE F**K; magenta #FF2BD6 for YEAH, OKAY, CAN YOU DO THE SPLIT?, *LAUGHS*; red #FF1A1A for DON'T, *FAILS*.
  - Some whole chunks are a single colour. "WHATEVER I DO" is all yellow, and the magenta lines are spoken by the woman, so **colour roughly codes the speaker or emotion.**
- **Stroke, shadow and glow:** there is no hard black outline. Instead there is a **wide, soft dark drop shadow or blur behind the text**, a smoky grey halo about 1-2x cap height (most visible on white backgrounds). Coloured words also get an **outer glow in their own colour** (green or yellow bloom around the letters). This keeps the text readable on the white cyc without a stroke.
- **Action captions:** stage-direction captions use asterisks: *BACKFLIPS*, *LAUGHS*, *GETS READY*, *FAILS*, *PERFECT SPLIT*. They also type on letter by letter. "*GETS READY*" builds "*GE", "*GETS", "*GETS RE" over about 0.5 s.
- **Emojis:** none in the captions. The only emoji is the 💀 in the ending freeze.
- **Timing against whisper:** the captions match whisper word starts within about ±1-2 frames.
  - "SO" appears at about 0.1 s (whisper 0.00), "YOU'RE" at 0.2 (0.28), "TELLING" at 0.3-0.4 (0.40), "ME" at 0.4-0.5 (0.54), "WHATEVER" at 0.8 (0.80), "I" at 1.0 (1.06), "DO" at 1.2 (1.40).
  - **This means words show up at or slightly before (about 0-0.1 s) the spoken onset.**
  - A chunk stays until the next chunk replaces it, so the screen is never caption-less during speech.
  - In the silent action stretch (4.8-9.8 s) the only caption is the action caption "*BACKFLIPS*", and some later shots have none.
  - Profanity is censored: "F**K".

## 4. Face tracking and framing
- **This is a multi-camera edit, not crop tracking.** The framing comes from choosing between a close-up camera (medium close-up, chest up) and a wide camera (full bodies). Within a shot the crop is mostly static, with a slow push or small reframe.
- **Close-ups** (0-3.2, 12.3-13.5, 20.7-22.5, 29.6-31.2, 32-35.3 s): the face height is about 18-25% of frame height. The head sits in the **upper third**, with the eyes at about y = 20-28%. The subject is centred or slightly off-centre; in Speed's close-ups he is pushed a little to the right. The headroom is tight; in some shots the top of the hair is cropped.
- **Wide shots:** both full bodies are shown so the trick is legible. People are 45-60% of frame height and positioned left and right.
- **Two people:** the wide shot holds both. For reactions it cuts to a two-shot over the shoulder (32-35 s: her face in profile or 3/4 with Speed's back in the foreground) or to single close-ups. It does not split the screen.
- **Movement:** when Speed stands up (3.2-4.2 s) the framing stays fixed and he rises out of frame. The reframe happens by cutting, not by panning. When we have only one source camera, the equivalent is a smoothed face-centred crop with a heavy dead-zone, so it looks like a locked camera rather than a jittery follow.

## 5. Effects
- **Chroma-green flash transitions** at 6.92-7.07 s and 26.68-26.93 s. These are 2-3 frames of a green (#00FF00) fill or tint with the outgoing and incoming subject faintly visible (difference or colour-overlay blend), then a fast green-to-normal fade over about 0.1 s. They land on the big action moments (the backflip landing and the jump into the split shot).
- **White flash / exposure blow-out** at 9.67-9.78 s, just before the "WHAT THE F**K" reaction.
- **Red colour wash** at 23.8-24.3 s on "*FAILS*". A full-frame red-pink overlay at about 60-70% fades out over about 0.5 s. This is the comedic "fail" accent.
- **Directional motion-blur whip transitions** at about 7.5, 9.9, 13.4, 27.7, 35.4 and 37.3 s. One or two frames of heavy horizontal or vertical smear plus a slight ghost of the next shot. On a 60 fps timeline the transition lasts about 2-6 frames.
- **Ending meme freeze** at 37.4-38.9 s. It enters through a zoom/radial blur (about 37.3-37.4 s). Speed's face is frozen in shock with his hands on his head while she laughs. A **💀 skull emoji** sits centre-left at about y = 50%, about 12% of frame width. The frame gets a **warm/sepia, crushed meme grade** (heavy yellow-green tint, high contrast). It is held about 1.5 s to the end.
- **Shake:** there is no beat shake. Motion energy comes from the source action, the whips and the flashes.
- **Zoom punch-ins:** no clear digital punch-ins on emphasis words. Emphasis comes from the coloured caption words and the cut to a close-up reaction instead.
- **Slow motion:** none is obvious. The flips play at real speed, and there are no speed ramps.
- **Audio:** the audio never goes silent. During the stretch with no dialogue (4.8-9.8 s, the backflip copy) the bed keeps running at about -20 to -24 dBFS short-term RMS, so **background music or a beat sits under everything**. Overall RMS during speech is about -12 to -20 dBFS, with music about 8-12 dB below the speech. Mid-clip there are loud peaks around -11 dBFS (likely transition SFX such as whooshes and impacts on the flashes) and a hit on the ending freeze. Music is ducked under dialogue and comes up in the action-only stretches.

## 6. Colour
- **Bright, high-key, clean "studio pop" grade.** The stats per 0.5 s give:
  - **luma: mean 209, median 215 (out of 255), range 148-248.**
  - The white cyc is pushed to near clip (230-248) and skin stays bright.
  - This is far brighter than typical stream footage, which sits around a luma mean of 100-140.
- **Saturation is selective rather than global.** The analysis.json sat (0-255 scale) has a median of 46 and a mean of 63.
  - The frame-average saturation is low because most of the frame is white background.
  - The hero colours are pushed hard: the red jersey (deep saturated red), the magenta outfit (hot pink, nearly clipping) and the skin (warm, glowing).
  - Close-ups reach sat 100-160 (for example 32-38 s).
  - **The look is "white background stays white, colours pop".** It suggests vibrance or saturation on mid-saturated colours plus a slight magenta/warm bias. The whites have a faint pink tint in the wide shots (8-20 s).
- **Contrast and sharpness:** blacks stay solid (the black chair, the camo). The image has a soft bloom or glow on highlights; the edges around the white cyc look dreamy and lifted. At the same time, detail is crisp:
  - Sharpness (Laplacian variance at 720p) has a median of 77 and goes up to 262 on clean close-up frames.
  - It drops to under 25 only on the motion-blur and flash frames (2.5, 3.0, 10.0, 11.0, 20.5-22.0, 24-25, 33.5, 35-38 s).
  - So: sharpen the subjects, add a soft highlight glow, and stack a fair amount of unsharp mask with a mild glow.

## 7. Rules for our pipeline to match Ref 1
1. **Length and canvas:** the final file is ≤ 60 s; this ref is 38.9 s, so aim for 30-50 s. Output 1080x1440 (3:4) like this ref; 1080x1920 (9:16) only on request. 60 fps if the source allows, otherwise 30. Fill the frame fully, with no letterbox or blur bars.
2. **Cold open:** the first frame is mid-sentence from the strongest premise line, with the caption on screen by 0.1 s. No intro card. The challenge or premise must be stated within 0-2.5 s.
3. **Story selection:** build one escalating arc (premise, attempt, reaction, repeated 3-5 times, then the biggest reaction last) from several moments of the long video, in their original order. Cut all dead air. Keep wordless action stretches only when the visual pays off (≤ 5 s each), with music under them.
4. **Cut rate:** 1 real cut every 1.0-2.0 s on average, with shots between 0.6 and 4 s. Alternate the wide/action framing with a tight reaction framing. Every punchline or fail gets a reaction close-up within ≤ 1 s.
5. **Captions:**
   - Uppercase heavy geometric sans: Montserrat Black/ExtraBold, falling back to Arial Black.
   - Cap height about 3% of frame height (about 44 px at 1440 tall, about 55 px at 1920). Line width ≤ 75% of frame width.
   - Centred, first-line baseline at y = 50% (±2%).
   - Chunks of 2-6 words, at most 2 lines.
   - Words appear one by one at whisper word start minus 0-2 frames, with a 3-frame fade-in and a slight scale from 90% to 100%. No bounce.
   - A chunk stays until the next one replaces it.
   - Base colour white #FFFFFF. Each chunk has 1-3 keyword(s) in an accent colour: green #2BFF2B (positive/emphasis), yellow #F5FF00 (setup/shock), magenta #FF2BD6 (second speaker), red #FF1A1A (negatives/fails).
   - No hard stroke. Use a soft dark blurred shadow (black at 50-60%, blur radius about 1.5x cap height, offset 0) plus a same-colour outer glow on the accent words.
   - Censor profanity with asterisks ("F**K").
6. **Action captions:** in moments with no speech, insert stage-direction captions in asterisks (*BACKFLIPS*, *LAUGHS*, *FAILS*, *PERFECT SPLIT*), coloured by sentiment and typed on letter by letter over about 0.4-0.6 s.
7. **Framing / face tracking:**
   - Detect faces and choose per segment between a "close" crop and a "wide" crop that keeps all people in frame.
   - Close crop: face height 18-25% of output height, eyes at y = 22-28%, horizontally centred ±10%.
   - Track with heavy smoothing (an EMA or 1-euro filter, a dead-zone of about 8% of width, a max pan of about 3% of width per second) so the crop reads as a locked camera. Reframe with cuts, not fast pans.
   - With 2+ people: use the wide crop when they interact physically, and cut to single-face close crops for reactions.
8. **Transitions** (about 6 per 40 s, only on big moments, never on every cut):
   - 2-3 frame chroma-green (#00FF00) flash with a ghosted subject, on landing or impact moments (max 2 per edit).
   - 1-2 frame white flash before a shock reaction.
   - A 0.5 s red overlay (60% to 0%) on a fail.
   - 2-6 frame directional motion-blur whips on the other big cuts.
   - Every other cut is a hard cut.
   - No beat shake, no slow motion, no constant zoom punches.
9. **Ending (optional, only when the moment fits; the skill default is a clean hard cut after the payoff):** freeze on the biggest reaction face. Enter it with a 2-4 frame zoom blur, apply a warm/sepia high-contrast meme grade, overlay one 💀 emoji (about 12% of width, mid-height), hold for 1.2-1.8 s, then end. Add an impact SFX on the freeze.
10. **Audio:**
    - Speech normalised to about -14 LUFS short-term peaks.
    - A background music bed throughout, ducked to about 10 dB under speech and raised to about -20 dBFS in wordless action stretches.
    - Whoosh/impact SFX on each flash or whip transition, each a different variant.
11. **Grade** (ffmpeg chain idea: `eq=brightness=0.04:contrast=1.12:saturation=1.25`, plus a `vibrance` filter at about 0.3, `unsharp=5:5:1.0`, and a light glow via a blurred screen-blend at about 15%):
    - Target mean luma 180-215 for bright scenes and at least 140 for darker ones.
    - Let whites approach 240+ without crushing skin.
    - Push saturated colours with vibrance (skin and wardrobe pop) while keeping the backgrounds neutral or white.
    - Keep blacks deep.
    - Hit a Laplacian sharpness median of at least 70 on non-blurred frames at 720p.
12. **Branding:** an optional small handle watermark centred at y = 85%, about 1.5% of height, white at 35% opacity. No persistent hook banner.
