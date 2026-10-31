# Ref 3: "Try to be slightly normal" (deagzzzshorts, IShowSpeed x MrBeast, 146M views)

> Raw study notes. The "Rules for our pipeline" section was written per ref; where it disagrees with `skill/references/01_ishowspeed_clip_style.md` (which reconciles all three refs), ref 01 wins.

File: <job>/refs/ref3.mp4. 1080x1440 (3:4), 60 fps, 52.22 s. Contact sheets: <job>/refs/ana3/sheet_00..04.jpg; dense 10 fps sheets: dsheet_A (0-2.5 s), dsheet_B (19.5-20.7 s), dsheet_C (26-28.4 s).

## 1. Format and layout
- The canvas is **1080x1440 (3:4)**, not 9:16, and the frame is fully filled. The source is 16:9 YouTube/IRL footage (MrBeast "red balls" challenge plus an IShowSpeed stream; frame 0 still shows the stream's chat overlay at the top right). It is centre-cropped and zoomed to fill. There is no letterbox, no stacked layout and no blurred background.
- There is **no persistent hook/title banner**. The only persistent element is a small, semi-transparent white watermark, **"@DEAGZZZSHORTS"**, centred at about y = 84% of the height and about 25% of the width wide, in a bold font at low opacity.
- A **vignette** darkens the corners in almost every frame, and the frame edges carry a soft white/light bloom.
- Context labels: "ISHOWSPEED" in small yellow text with a small red down-pointing triangle, placed as a pointer above the tiny far-away Speed (21-24 s). There is also a green "+$100,000" money pop at 26.2 s and again at 45 s.

## 2. Structure
- **Hook (0-1.6 s):** a cold open on a close-up of Speed's face with the sound-effect caption "*BARK*" (0-0.7 s). It cuts at 0.3 s to MrBeast's line "Try to be slightly normal." The joke premise is set in under 2 s. The music is at full level from frame 0.
- **Story arc:** this is several moments from one video (the MrBeast challenge), stitched chronologically:
  - Premise/banter (0-12 s)
  - "I'm gonna go on a ball and try to win, wish me luck" (12-20 s)
  - Wide-shot attempt: running across the red balls (20-30 s; no dialogue from about 21.5 to 30 s, so music carries it)
  - Fall/fail reaction: MrBeast says "Oh my gosh, I just lost 100 grand" (30-34 s), then "Let's go" and a hug (34-36 s)
  - Payoff: briefcases of cash, "can you wire me the money", "I don't want it in cash" (36-42 s)
  - Second payoff: "Here's another one", Speed loaded with briefcases, "I cannot hold it" (42-51 s)
  - Ending (51.4-52.2 s): Speed bent over holding the briefcases. It is a hard end with no outro or call to action, and the last frame flows naturally into a replay.
- **Cuts:** I counted about 20-25 real cuts. The detector found 14, so it **under-detected**: many jump cuts between similar same-scene shots were missed (for example 0.3 s, about 2.0 s and about 2.3 s in dsheet_A). True average shot length is about 2-2.5 s, with 0.3-1 s cuts in the hook and 4-9 s holds during the wide attempt shot and the briefcase finale.
- **False positives** in the detected list:
  - **26.23** is a **full-frame green colour flash** (a green tint layer for about 0.25 s at 26.2-26.4 s, together with the "+$100,000" pop). It is not a cut.
  - **27.87** is a **magenta/red tint flash** (about 0.3 s, 27.9-28.2 s). It is not a cut.
  - **20.0** is a real cut, hidden by a **whip/directional motion-blur transition** (19.9-20.1 s, heavy vertical streak blur).
  - **35-36** has a **full green-tint flash** on the hug ("*HUGS*").
  - **8.0** has a green-tinted frame on "NOW" (a colour flash at the cut).
- In short, these are **colour-flash accents (green, red/magenta) on punchlines and money moments**, plus a whip-blur transition into the action section.

## 3. Captions
- **Font:** a heavy geometric sans (Montserrat Black / ExtraBold class; it could be "The Bold Font"), **ALL CAPS**.
- **Size:** small. A cap height of about 3% of the frame height (about 40-45 px at 1440 tall). A 2-3 word chunk spans about 20-30% of the width. These are much smaller than typical "big bouncy" captions.
- **Position:** centre-anchored at **y of about 25%** (0-20 s and 36-52 s; roughly face/chest level, upper third) or **y of about 75%** in some shots (6-11 s, 30-35 s, 42-44 s). The placement is chosen to sit on the speaker's body without covering the mouth. In practice the caption sits just below the face.
- **Words per chunk:** 1-3 (mostly 1-2), each lasting about 0.2-0.5 s, for example "TRY TO BE" / "SLIGHTLY" / "NORMAL", "ALRIGHT" / "BE NORMAL", "ALL OF US", "GO ON A" / "BALLS", "I WILL WIN", "IF I WIN".
- **Colours:** each chunk gets one colour, rotating among **white, red (#FF1A1A), lime green (#3CFF3C), yellow (#FFE600) and cyan (#40E0E0)**. Some chunks are two-tone, with one emphasis word coloured and the rest white: "CAN YOU **WIRE**", "IN **CASH**", "WHAT IS **WRONG**", "I JUST **LOST**", "TRYNA **WIN**", "AROUND **YOU**".
- **Glow and stroke:** each word has a **strong outer glow in its own colour** (radius about 15-25 px, opacity about 70%), plus a thin dark drop shadow or stroke. There is no background box.
- **Active-word highlight:** no karaoke within a chunk. Emphasis comes from colour per chunk or per keyword.
- **Entrance:** there is a fast **blur/glow-in**: frame 1 is a blurred, larger glow blob and it settles in about 2-3 frames at 60 fps (see dsheet_A 009->011, "SLIGHTLY"). There is no big scale bounce, and the exit is a hard cut.
- **Emojis:** none.
- **Sound-effect captions** in asterisks: "*BARK*", "*STARTS RUNNING*", "*RUNNING*", "*HUGS*", "AHH". The visuals are captioned too, not just the speech.
- **Timing vs Whisper:** chunks are synced closely to word onsets, within ±1-2 frames (for example "SLIGHTLY" appears at about 0.9 s against a Whisper start of 0.96 s; "NORMAL" at about 1.3 s against 1.22 s). Words are paraphrased into a slangy register ("BALLS", "TRYNA WIN", "GOOD SHI-", "DAWG"). Lines Whisper missed (the "*BARK*", Speed's mumbles) are added manually.

## 4. Face tracking and framing
- The 16:9 source is cropped to 3:4, which keeps about 56% of the source width, and the crop window is placed on the active subject.
  - In close-ups, the **face fills about 25-35% of the frame height**. At 0 s the head is about 40% of the height; at 31-33 s MrBeast's head is about 30%.
  - The **face is on the upper-third line** (eyes at about y 30-38%), and horizontally centred or slightly off-centre.
  - The crop holds the framing smoothly. There are no jerky pans, and when the subject moves the camera is mostly the source's own handheld motion.
- **Two or more people:**
  - For a two-shot (MrBeast + Speed, 0.3-1.5 s, 42-47 s) the crop is placed to include both, with one person cut by the frame edge at the left or right. It does not split the screen.
  - In wide action shots (21-29 s) there is no face crop. The whole scene is shown, and a "ISHOWSPEED" pointer label marks the tiny subject.
  - The reaction cuts (31-33 s) go back to a single-face close-up.

## 5. Effects
- **Colour flashes:**
  - Green tint on "NOW" (8.0 s), on the "+$100,000" pop (26.2 s) and on the "*HUGS*" (35 s)
  - Red/magenta tint at 27.9 s
  - A white overexposure flash at 2.0 s (luma jumps to 232). Speed's shot "ALRIGHT" opens blown out and fades to normal over about 0.4 s (dsheet_A 018-022).
  - Each flash lasts about 0.2-0.4 s, with a fast attack and a decaying tint.
- **Whip/motion-blur transition** at 19.9-20.1 s (vertical streak blur) leads into the action wide shot.
- **Zoom punch-ins:** mild scale pushes on some shots (for example the 1.5-3 s "ALRIGHT" shot drifts in). There are few hard punch-ins; emphasis comes mostly from colour, not zoom.
- **Shake:** there is a slight shake/blur at the start of the 12 s shot ("ALL OF US", motion blur). It is otherwise rare.
- **Graphic labels:** "ISHOWSPEED" pointer tag (21-24 s) and "+$100,000" money text in green with glow (26 s, 45 s).
- **Not used:** no slow-motion and no freeze frames were visible, and there are no meme image inserts.
- **Audio:** RMS stays flat at about -16 to -20 dBFS through the no-speech stretch (21.5-30 s), so a **continuous background music bed** runs underneath. It appears to be a hype/phonk-style beat. It is ducked under speech (overall level stays the same with or without speech) and fills the gaps. There are likely also SFX hits on the colour flashes (bark at 0 s, whoosh at the 20 s whip). (I did not listen to the audio; this is inferred from levels.)

## 6. Colour
- The stats show **mean luma 154 (median 159) on a 0-255 scale**, so the result is **very bright**. Typical stream or vlog footage sits at about 100-120.
- Mean **saturation is 93 (median 93, peaks of 130-153 on flashes)**, against about 50-70 for an ungraded source. The hook frames (0-2 s) are lower at 52-64 because of the white overexposure and bloom.
- The grade has pushed highlights with blooming skies, **teal/cyan water and lime grass pumped**, and deep blue skies with high contrast in the later section (31-50 s). The overall look is hazy and glowy, with a soft white halation at the frame edges and a corner vignette.
- Sharpness (Laplacian variance) has a median of 437 and a mean of 792; the spikes come from frames with text or detail. The footage is sharpened (visible halo edges on the skin and the briefcase metal), but the bloom softens the overall look.

## 7. Rules for our pipeline
1. **Output length** ≤ 60 s. Target 45-55 s and end on a payoff beat with a hard cut, with no outro.
2. **Canvas:** full-bleed crop with no letterbox or blurred background. The ref uses 1080x1440 (3:4), which is the pipeline default; offer 1080x1920 (9:16, same full fill) on request.
3. **Hook:** a reaction close-up or the punchline from 0.0 s, with the premise line spoken within 2 s. The music bed is at full level from frame 0 at about -20 dB, under speech at about -16 dB, and continues through gaps with no speech.
4. **Cuts:** 0.3-1 s jump cuts in the first 3 s, a 2-2.5 s average shot afterwards, and holds of up to 9 s allowed for the action or payoff. Stitch chronological moments from one video into a setup -> attempt -> fail/reaction -> payoff arc.
5. **Caption text:** ALL CAPS, Montserrat Black (or The Bold Font), cap height about 3% of the frame height, 1-3 words per chunk, entering at the Whisper word start minus 1 frame.
6. **Caption placement:** centred at y 25% (just under the face). Switch to y 75% when the face sits low or the upper area is busy.
7. **Caption colour:** one colour per chunk, cycling through white, #FF1A1A, #3CFF3C, #FFE600 and #40E0E0. Optionally white text with one keyword coloured. Add an outer glow in the same colour (blur about 20 px, about 70% opacity) and a thin dark shadow, with no box.
8. **Caption entrance:** blur-to-sharp plus a glow fade-in over 2-3 frames (about 50 ms), with no bounce and a hard-cut exit.
9. **Non-speech captions:** add bracketed sound-effect and action captions such as "*BARK*", "*RUNNING*" and "*HUGS*" at non-speech moments.
10. **Context labels:** add a name pointer label (small yellow name plus a red down-triangle) over a tiny subject in wide shots, and a green "+$AMOUNT" glow pop on money moments.
11. **Face framing:** the face is 25-35% of the frame height with the eyes at y 30-38%. Use a smoothed crop centre (EMA or low-pass, with no jitter). For two people, widen the crop to include both, edge-cropping one if needed. For wide action shots, use no face crop and show the whole scene.
12. **Accents:** 3-5 full-frame colour-tint flashes per minute (green or magenta, 0.2-0.4 s, fast attack and decay) on punchlines, money or emotional moments. Add 1 white overexposure flash-in on a shot start, 1 directional motion-blur whip transition into the action section, and 1 SFX hit per flash or whip.
13. **Grade:** target mean luma of about 150-160 and mean HSV saturation of about 90-100 (on 0-255). Apply teal/cyan and green boosts, a contrast S-curve, an unsharp mask (about 1.0-1.5), soft highlight bloom, and a corner vignette of about 20-30%.
14. **Watermark:** a small semi-transparent handle centred at y about 84%, about 25% of the width, at about 40% opacity.
