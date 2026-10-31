# 02 - Raw chapter studies: "Claude Code Can Now Clip ANY Video (Free Skill)" - Eddie | AI

Source: https://youtu.be/IY08-3TS2o8 . Studied in four slices (0-119 s, 119-189 s, 189-343 s, 343-499 s). Frames and stills: `<job>/tut1/`. Distilled rules: skill `references/02_eddie_claude_clipping_tutorial.md`.

> Raw notes taken slice by slice; some "ACTIONABLE" ideas below (karaoke recolour, zoom punch-ins every 3-4 s, 9:16 default, whooshes on every zoom) were later rejected. Where these notes disagree with `skill/references/`, the references win (see ref 02's NOT ADOPTED list).

=== result+finding ===
# Tutorial slice report: "Claude Code Can Now Clip ANY Video (Free Skill)" by Eddie | AI, 0 s to 119 s

**Method.** I read every frame from f_0001 to f_0060 (t=0 to 118 s) in 2x2 contact sheets, saved in <job>/tut1/sheets_a0/. I also pulled full-resolution stills: <job>/tut1/hi_{5,14,16,40,44,52,53,66,72,98,100,101}.png.

**What this slice does not show.** No terminal output from the clipping pipeline itself appears here: no yt-dlp, whisper or ffmpeg commands, and no face-detection library names. The agent run is shown only as "Working…" followed by the final summary table. The only tool names on screen are in the install preview card at about 44 s (the real install happens at 3:56). The Skool lesson page is deliberately blurred, so its text below is my reconstruction.

## Timeline: what is said and shown

- **0–4 s (hook).** The source is MrBeast on The Diary Of A CEO, 1:43:14 long. The tutorial cuts straight to the finished clip: "Claude Code just turned this long MrBeast video into seven separate clips ready to post. All I did was post one link."
- **4–6 s: "7 clips" grid.** Seven 9:16 cards, each with a green check. All are MrBeast single-person crops at roughly chest-up framing, with the face in the upper third.
  - Caption style:
    - Heavy geometric sans, ALL CAPS, very close to Montserrat ExtraBold/Black.
    - Small text, about 5–6% of frame height.
    - Placed at about 58–62% of frame height (chest level), not at the bottom.
    - 1–3 words per screen. Examples: "FUNNY BECAUSE", "SOME ASSISTANCE", "THING", "SEEING", "JUST LIKE", "INSANE HIT RATE", "KNOWS".
    - Highlighting: the emphasised or current word is gold-yellow (about #F5C518) and the rest are white ("SOME **ASSISTANCE**", "INSANE **HIT** RATE"). It reads as karaoke or keyword highlight.
    - Thin dark outline or shadow, no box.
- **8–12 s.**
  - **Source timeline.** On the YouTube player at 1:42:34 / 1:43:14, the progress bar has yellow markers where each clip was taken from. The clips are spread across the whole 1h43 video.
  - **Clip fan-out.** Seven clip cards fan out over the player. Caption words visible: "IT'S", "AS FUN", "WHICH IS", "BE HONEST", "SUCCESSFUL", "BUT ALSO".
  - **Second subject.** Some clips feature the host, Steven, not only MrBeast.
  - **Voiceover:** "It watched the whole thing, found the best moments, and cut them out by itself… It edits every single clip, too. The captions, the zooms, and it's done."
- **14–18 s: "Raw cut" vs "Edited".**
  - The raw cut is the plain vertical crop with no captions.
  - The edited version is slightly tighter (zoomed in) with a 2-word caption: "MONTH **JUST**", "HOW **DO**". The second word is yellow, and the caption sits at chest height.
- **18–24 s.** "FREE · Claude skill" badge. Example sources shown: MrBeast, Dana White, a bearded speaker on a dark stage.
  - Claim: "the same clipping system from my last video, the one running my Instagram that posts 20 reels a day".
  - His Instagram (eddieswork) shows 118 posts and "15.4K views in the last 30 days" in his dashboard.
- **32–36 s.** The tutorial's own lower-third captions are sentence-case white text with one keyword phrase in yellow italic serif, circled ("complete beginner's guide"). This is the tutorial's style, not the skill's output.
- **38–48 s: "Later in this video" chapter cards.**
  - **"How it picks the moments" (AT 5:08).** The card shows a timestamped transcript (mm:ss per line, 22:05 to 22:41).
    - A yellow **HOOK** tag marks the line at 22:25, "To go viral, you have to do something that's never been done before."
    - The preamble lines before it are skipped: 22:05–22:18, "I don't know why, but when people tell me I can't do something… Everything in my body just wants to go, f*** you. I obviously can."
    - So the clip starts on the hook line, not where the topic starts.
    - It continues with the purple cow story (22:28–22:41), ending on "You're going to go, holy sh*t", which is the payoff.
  - **"Install with one prompt" (AT 3:56).** Prompt: "Hey Claude can you set up this full repository for me." Agent output:
    - "Docs look clean. Checking prerequisites first."
    - "Checked **Python, ffmpeg, Node, GPU** ✓"
    - "All prerequisites present. Running the installer (both **Python deps and the optional Remotion engine**)."
    - "Ran project installer with Remotion ✓"
    - "Quick smoke test that the CLI and Python imports work: Smoke test CLI and Python imports ✓"
    - **What this tells us about the stack:** a Python CLI plus ffmpeg, with an optional Remotion (React/Node) renderer for captions and effects, and GPU use (likely faster-whisper/CUDA or NVENC).
  - **"What it costs" (AT 7:17).** OpusClip Pro at "$29 / month" (with a small note that looks like "3 podcasts like this a month") against Claude Pro at "$20 / month".
- **50–54 s: Skool page "AI Builders Club → Classroom → Long-Form Clipper".**
  - Course tiles: "Long-Form Clipper: This tool will clip your long-form videos into edited short-form videos"; "$2,000 Claude Short Form Editor: Drop in a raw talking-head video and Claude edits it into a finished vertical short"; "MUST-HAVE SKILL"; "AI Faceless Animations".
  - Module list: Module 1 Start Here (Lesson 1 What This Skill Does, Lesson 2 What You Need), Module 2 Setup (Once), Module 3 Clip Your First Video, Module 4 Fixes and Ground Rules.
  - Lesson 1 text, blurred, reconstructed with high confidence:
    - "You paste one link. Claude watches the whole video, picks the best moments, cuts them vertical, and edits every single one."
    - **What you get back:**
      - "**3 to 8 vertical clips (9:16, 1080x1920)**, ready for YouTube Shorts, Instagram Reels and TikTok"
      - "**Every clip starts on a hook and ends on a payoff, so it works for someone with zero context**"
      - "**The frame re-centres on whoever is speaking, every time the camera cuts**"
      - "**Zooms, word-by-word captions and a couple of subtle whooshes on every clip**"
      - "**A title and a ready-to-post caption for every clip**"
    - **My test run:**
      - "MrBeast on The Diary Of A CEO, 1 hour 43 minutes"
      - "**7 finished clips, 20 to 75 seconds each**"
      - "Under 40 minutes end to end, and I didn't touch anything after sending the prompt"
- **56–64 s.** "It's almost 2 hours long. Finding the good parts usually means scrubbing the full video yourself."
- **64–74 s.** YouTube Share, then he copies the youtu.be link. "Open Claude Code in the Clipper folder and type one line": the Claude desktop app, New session, project chip "Clipper Tool", model "Opus 4.5". Prompt, verbatim: **"Run the clipper skill for this video https://youtu.be/FjrJ2DJN_pA?si=6nB3QIKq6uXgsyyw"**, then "Working…". "That's the whole prompt."
- **76–86 s: "Four steps, all on its own".**
  1. **Watch:** "downloads + transcribes"
  2. **Pick:** "finds the best moments"
  3. **Cut:** "cuts them vertical"
  4. **Edit:** "captions, zooms, sounds"
- **86–92 s.** "On a 2-hour video like this one, the whole thing took only around **30 minutes**" (a "~30 min" stopwatch graphic). The Skool page says "under 40 minutes". Later, at about 164 s, he says editing all 7 clips took "only 7 minutes".
- **96–102 s: final agent output** (hi_98.png). Session title "Clip MrBeast podcast". The agent's final message:
  `Done. 7 clips are in output/mrbeast-if-you-want-to-be-liked-dont-hel-FjrJ2DJN_pA/edited/`
  - The output folder is named `output/<slugified title, truncated to ~35 chars>-<videoId>/edited/`. This implies a sibling raw-cuts folder, since he calls them "raw cuts" at 117 s.
  - It is followed by a markdown table with columns **# | Clip | Length | Opens with**:

    | # | Clip | Length | Opens with |
    |---|---|---|---|
    | 1 | Want To Be Liked? Don't Help People | 76 s | "The ironic part is the more I help people, the more shit I get" |
    | 2 | Billionaire On Paper, Broke In The Bank | 47 s | Steven: "Are you a billionaire?" / "On paper, yeah… less than a million dollars" |
    | 3 | The Purple Cow Rule Of Going Viral | 68 s | "To go viral, you have to do something that's never been done before" |
    | 4 | He Hid GoPros In Walmart | 60 s | "There's too many broken bars…" |
    | 5 | Why Nobody Makes Videos Like Him | 56 s | "If my mental health was a priority, I wouldn't be as successful" |
    | 6 | Not Everyone Can Handle 1% Hate | 48 s | "It will drive you crazy at our scale if you try to make people happy" |
    | 7 | The Worst Kind Of Employee | 29 s | "You put a bunch of A players around more A players…" |

  - Lengths run from 29 to 76 s, averaging about 55 s, so **3 of 7 are over 60 s**.
  - Titles are Title Case, 4–7 words, curiosity or contrast phrasing ("Billionaire On Paper, Broke In The Bank").
- **100 s: CAPTION card for clip 2.** "MrBeast is a billionaire with less than $1M in the bank. Here's why. #mrbeast #money #business". The post caption is one or two sentences, ends with "Here's why.", and carries 3 hashtags.
- **102–108 s: raw vs cut.**
  - YouTube at 1:01:52 / 1:43:14 (chapter "How Big Are MrBeast's Businesses?") becomes the 9:16 clip.
  - A **HOOK card** at 0:00 shows a speaker-labelled transcript: "Steven: *Are you a billionaire?*" (highlighted) / "MrBeast: On paper, yeah. But I mean, in my actual bank account, I've less than a million dollars." Speaker attribution is in the data, either through diarization or by inferring who speaks from the dialogue.
  - "It found the exact hook and started the clip right there." **The hook can be the interviewer's question.**
- **108–116 s: reframing.**
  - A wide two-shot of both people at the table has a yellow 9:16 box on the active speaker (Steven, right side).
  - On MrBeast's single shot, the box is labelled "**FACE CENTRED**". Across frames the box stays fixed while his hands move; it does not jitter after gestures.
  - "Every time the camera cuts, it recenters the frame on whoever's on the screen. So now nobody ends up half cut off."
  - **What the reframe does:**
    - It detects camera cuts and holds a static crop per shot, with no continuous tracking.
    - In a two-shot it chooses the speaker.
    - The crop is a full-height 9:16 window, with no letterbox or split-screen.
- **117–119 s.** "But these are just raw cuts. Here's where it gets better…" From here, outside this slice, the transcript describes the edit pass:
  - Zooms placed from the transcript "right when Mr. Beast finishes a point", centred on the face.
  - Captions "two to three words at a time", with "words that matter like billionaire and million get highlighted".
  - "Sound effects like these whooshes".
  - "Edited all these seven clips in only 7 minutes."
  - Follow-up prompt: "extract only the best clip and keep it under 30 seconds".

## Claims about cost and time

- **Free skill**, available behind the free AI Builders Club on Skool.
- **"Costs you nothing extra"** on top of Claude Pro at $20/month, compared with OpusClip Pro at $29/month.
- **2 h video takes about 30 min end to end.** The Skool page says "under 40 min".
- **Editing pass:** 7 clips in about 7 min.
- **Zero touches** after the prompt.

## ACTIONABLE for our skill

1. **Hook-first trimming.** Start every clip on the hook line, not where the topic begins. Drop throat-clearing and setup lines before it. Tag the hook line in the selection JSON (`hook_start`), as their HOOK tag on the 22:25 line does. The hook may be the interviewer's question ("Are you a billionaire?"). Allow `hook_speaker != main_speaker`.
2. **End on a payoff.** Require each candidate to have a closing punchline or resolution. Rule: "works for someone with zero context". Add a self-check that the clip makes sense with no prior context.
3. **Spread and count.** Sample candidates across the whole source (their markers span 0 to 1h43). Return a ranked list of 3–8 candidates. Each of our clips stays at 60 s or less by default, but keep the 3–8 ranked list (title, length, opening line) so the user can pick.
4. **Speaker-labelled, timestamped transcript.** Use word-level ASR (faster-whisper) plus diarization or speaker inference, and render it as `mm:ss  Speaker: line` for the LLM to pick from.
5. **Shot-aware reframe.** Detect camera cuts (scenedetect or ffmpeg `select='gt(scene,0.3)'`) and choose the crop centre once per shot from the face or active speaker. Add EMA smoothing within a shot, but snap at cuts and never pan across a cut. In a two-shot, follow the active speaker (diarization turn plus face side). Gate output: nobody "half cut off", so face boxes must be fully inside the crop.
6. **Transcript-driven zooms.** Punch in at the end of a point or sentence, centred on the face box, with the face kept inside the frame.
7. **Keyword highlight.** Highlight the important word (numbers, money, superlatives: "billionaire", "million") in gold-yellow (about #F5C518) with the other words white. Caption block at about 58–62% of frame height (chest), not bottom-safe-area.
8. **"A couple of subtle whooshes per clip".** Keep SFX sparse: about 2 per clip, on zooms or transitions.
9. **Deliverables per clip.**
   - A Title Case title of 4–7 words, curiosity or contrast phrasing.
   - A ready-to-post caption: 1–2 sentences, ending "Here's why." plus 3 hashtags.
   - A final summary table with columns `# | Clip | Length | Opens with`.
10. **Output layout.** `output/<slug(title)[:35]>-<videoId>/` with `raw/` and `edited/` subfolders, so the uncaptioned raw cut is kept beside the edit for before/after review.
11. **Install and preflight.** Check Python, ffmpeg, Node and GPU, plus a smoke test of the CLI and imports. Remotion is optional (they use it for the caption and effects engine). Keep our ffmpeg/ASS caption path as the default and treat Remotion as optional.
12. **One-line trigger.** "Run the clipper skill for this video <url>" should run the whole job with no questions. Support a modifier such as "only the best clip, under 30 seconds".

## Conflicts with our IShowSpeed-edit style

- **Canvas.** They render 9:16 at 1080x1920 with a full-height crop. Our style uses a 3:4 canvas. Keep 3:4 for Speed edits and offer 9:16 as an option. Their "face centred, full height" rule still applies inside a 3:4 window.
- **Clip length.** Their clips run 20–76 s, three of seven over 60 s. Our default cap is 60 s or less. Trim harder and keep their hook/payoff rule inside the cap.
- **Caption font.** Their font is close to ours (heavy geometric sans, ALL CAPS, 1–3 words). But their size is small and restrained, with one highlighted word and no pop or scale animation. Speed style is Montserrat Black, 2–4 words, bigger, with stronger animation. Adopt only the keyword-highlight rule and their chest-height placement.
- **Accent density.** "A couple of subtle whooshes" and a few zooms per clip is calmer than our accents every 6–8 s (about 8–10 per minute). Keep our cadence, but take their placement logic: zoom at the end of a point, SFX on the zoom.
- **Static crop vs smoothed tracking.** They hold a static crop per camera shot, so it barely moves while the speaker gestures. Our style uses a smoothed face crop. Combine the two: smooth within a shot, hard-reset at camera cuts, and use a deadzone so gestures don't drag the crop.
- **No colour correction** is visible or mentioned in this slice. The edited clips look like the source grade, apart from a slightly tighter crop. Our CC step is our own addition; there is no conflict, it simply isn't in theirs.

=== before-after ===
# Slice 119-189 s: before/after auto edit, the "What Claude adds" breakdown, and the re-edit by prompt

Source: "Claude Code Can Now Clip ANY Video (Free Skill)" by Eddie | AI. I extracted every frame at 4 fps (contact sheets in `<job>/tut1/ba/sheet_01..24.jpg`) and pulled full-res stills at key moments (`<job>/tut1/ba/hi_*.png`). I looked at all of them.

Most of this slice is a motion-graphics explainer the tutorial author made himself. It has a beige grid background, rounded phone-shaped cards, "Before"/"After" pills and a "What Claude adds" checklist. That presentation is not the skill's output. Only what is inside the 9:16 cards comes from the skill.

## Timeline: what is said and shown

| t (s) | Said (cleaned from the auto-captions) | Shown |
|---|---|---|
| 117-122 | "But these are just raw cuts. Here's where it gets better. This is the same clip before and after." | The presenter on camera. Then two 9:16 cards side by side: **Before** (black pill, card shown greyscale) and **After** (lime pill #D4F53C-ish, in colour), with an "Edited by Claude" badge (Claude asterisk logo) under After. Source: MrBeast on the Steven Bartlett podcast. |
| 122-124 | "Claude edited this one completely on its own." | After card captions: "ON PAPER YEAH", "BUT I MEAN", "IN MY ACTUAL", "BANK ACCOUNT", "I'VE LESS". |
| 124-133 | "First, it adds the zooms. It reads a transcript to figure out where a zoom actually makes sense, like here, right when Mr. Beast finishes a point." | A **Transcript** panel with timestamps (0:06 "So do you pay yourself at all?", 0:08 "A little bit.", 0:08 "But I also like I have some assistance and things like that.", 0:11 "So it's like I try to just pay myself what I spend, you know, personally a month just to like stay even.", 0:17 "How do you think about money in all of this?"). Every sentence ends with a diamond marker. A lime highlight walks down the sentences. At the end of the line "...a month just to like stay even." a lime **ZOOM** tag appears. So a zoom is placed at the **end of a sentence or point**, not at random. A checklist sits at top right: Zooms / Captions / Highlighted words / Sound effects, ticked one by one. |
| 133-140 | "Then it looks at the frame and zooms in around his face, so nothing important ever gets cut off." | A card shows a horizontal scan line sweeping, then a glowing lime **rounded face box** with corner brackets and a "**Face in frame** (check)" pill. The card scales up, which illustrates the punch-in. The zoom is centred on the face bbox, and the face box stays fully inside the frame. Estimated push-in about 1.2-1.4x (judged from the face-box size relative to the card). The checklist ticks Zooms. |
| 137-146 | "Next, the captions. It takes the transcript and puts it on the screen just two to three words at a time so it's easy to follow." | Another speaker (Steven) on screen. A white pill reads "**2-3 words at a time**". Captions: "BECAUSE MOST", "PEOPLE IN", "LIVES ARE", "PURSUING MONEY", "SO THAT THEY", "CAN CHILL OUT", "AND RETIRE", "YOU SEEM TO", "BE PURSUING IT", "PURELY FOR THE", "SAKE OF". |
| 146-152 | "And then the words that matter like billionaire and million get highlighted so they stand out." | Single-word or two-word captions: "**BILLIONAIRE?**" (wide shot of Steven seated) and "A **MILLION**". The keyword is yellow text inside a **dark translucent rounded-rect box with a glowing yellow-lime outline (neon glow)**. Non-key words beside it ("A") stay white with no box. |
| 152-162 | "And to finish it off, it adds these sound effects like these whooshes here. Listen closely." (The caption text "wishes" is a mis-hearing of "whooshes".) | Header "To finish it off: *sound effects*" (lime script font, tutorial graphics only). Three cards light up one after another with a lime glow on each **cut or transition**, which marks where a whoosh plays. Captions: "TO", "SO IT", "FUNNY", "THAN ANYONE", "ELSE EVEN GETS", "ON VIDEO VIEWS", "DEEPEST MODES", "LIKE THERE'S A", "REASON NO", "MAKES VIDEOS". The SFX sit on **cuts or zooms only**, not on every word. |
| 161-166 | "And it edited all these seven clips in only 7 minutes." | The presenter on camera. |
| 166-178 | "Now let's say you want something different. You just tell Claude, 'Hey Claude, extract only the best clip and keep it under 30 seconds with no sound effects. Also, use a blue color for the captions.' Send it and Claude does the full edit for you." | The prompt is typed into the **Claude desktop app (Claude Code UI)**. Window title "Clip MrBeast podcast". Footer: folder "Clipper Tool", mode "Auto", model "Opus 5.5 Medium". |
| ~180 | — | Full-res still of the earlier session. First prompt: "**Run the clipper skill for this video** https://youtu.be/FjrJ2DJN_pA?si=..." Reply: "**Done. 7 clips are in `output/mrbeast-if-you-want-to-be-liked-dont-hel-FjrJ2DJN_pA/edited/`**" followed by a table with the columns **# / Clip / Length / Opens with** (see the table below). |
| 180-185 | "There we go. It's now blue, under 30 seconds and has no sound effect." | Result card with a checklist: "Blue captions" (blue swatch), "**0:28 long**", "No sound effects" (mute icon). Captions: "YOU", "YOU PUT A", "BUNCH OF A", "PLAYERS AROUND", "MORE A PLAYERS", "THEY JUST BUILD", "OFF OF". The active word is now **blue (#2E8BFF-ish)** where it was yellow. The re-edit used **clip 7 (29 s, "The Worst Kind Of Employee")**, trimmed to 0:28. |
| 185-190 | "So now that we know this works, let me show you how you can set this up on your own computer... you only need Claude Code (free) and a paid Claude plan; the Pro plan works fine." | The presenter on camera. |

### Clip table shown at ~180 s (verbatim)

| # | Clip (title) | Length | Opens with |
|---|---|---|---|
| 1 | Want To Be Liked? Don't Help People | 76 s | "The ironic part is the more I help people, the more shit I get" |
| 2 | Billionaire On Paper, Broke In The Bank | 47 s | Steven: "Are you a billionaire?" / "On paper, yeah... less than a million dollars" |
| 3 | The Purple Cow Rule Of Going Viral | 68 s | "To go viral, you have to do something that's never been done before" |
| 4 | He Hid GoPros In Walmart | 60 s | "There's too many broken bars..." |
| 5 | Why Nobody Makes Videos Like Him | 56 s | "If my mental health was a priority, I wouldn't be as successful" |
| 6 | Not Everyone Can Handle 1% Hate | 48 s | "It will drive you crazy at our scale if you try to make people happy" |
| 7 | The Worst Kind Of Employee | 29 s | "You put a bunch of A players around more A players..." |

What the table tells us about the competitor's output:
- Clip lengths range from 29 to 76 s. Two clips (68 and 76 s) are over 60 s, so their default does not cap at 60 s.
- Each clip gets a Title Case "YouTube-ish" title.
- Each clip opens on a hook quote.
- Output folder pattern: `output/<slug-of-video-title>-<videoId>/edited/`.

## The output edit style, exactly as seen

- **Canvas:** 9:16 vertical (cards about 0.56 aspect), full-bleed single speaker. There is no split screen, no blurred-background letterbox, no b-roll, no progress bar, no persistent title or hook banner and no watermark in the clip. "Edited by Claude" is a badge in the tutorial graphic, not in the clip.
- **Framing:** a face-centred crop from the 16:9 podcast. On a camera cut the crop re-centres on whoever is on screen (said at 110-115 s). Wide shots stay wide; for example the "BILLIONAIRE?" shot shows the whole seated body with the face in the upper third. There is no visible jitter, which suggests a per-shot static or smoothed crop.
- **Colour:** the After clip is in normal colour, slightly warm and contrasty. The greyscale Before is the tutorial's presentation, not evidence of a colour grade.
- **Caption font:** a geometric heavy sans in ALL CAPS. It looks like **Montserrat ExtraBold/Black** (round O, flat-top A, wide letter spacing).
- **Caption colours and outline:** base words are white. The **currently spoken word is yellow/gold (~#F2C200)**, karaoke-style. Text has a thin dark outline or stroke plus a soft dark drop shadow, with no background box.
- **Caption size:** cap height about 4.5-5% of frame height. A line spans roughly 55-75% of the frame width.
- **Caption position:** horizontally centred, vertically about **62-66% down the frame** (lower-middle, around chest level, below the chin). It is not at the bottom edge.
- **Words per caption:** 1-3 per page ("2-3 words at a time"). Words build up within a page: "BUT I" becomes "BUT I MEAN", and "I TRY" becomes "I TRY TO". When a new page starts, the earlier words disappear.
- **Caption animation:** each new word **pops in with a quick scale-up**. Mid-pop frames show the newest word smaller and translucent (for example "THAT IS **BETTER**", "CAN CHILL **OUT**"). There is no slide or bounce of the whole line.
- **Keyword emphasis:** for words that matter (money and status nouns: BILLIONAIRE, MILLION), the word is shown alone or nearly alone, in yellow, inside a **dark rounded box with a neon yellow glowing border**. This happens about once every several seconds, not on every word.
- **Zooms:** punch-ins on the face, placed at **ends of sentences or points** chosen from the transcript. Each is held for a stretch (for example after "...stay even"). The zoom is anchored on the face box so the face is never clipped.
- **SFX:** whoosh on cuts and zooms. Optional: they can be switched off by prompt.
- **Customisation by natural language:** caption colour, maximum length, SFX on or off and number of clips can all be changed by plain prompt. This implies the skill exposes these as parameters.
- **Speed claim:** "edited all these seven clips in only 7 minutes", about 1 min per clip for the editing pass. Requirements: Claude Code (free) plus a paid Claude plan ("Pro works fine"). The model in the footer is Opus 5.5 Medium in Auto mode.

## ACTIONABLE for our skill

1. **Zoom placement comes from the transcript.** Put punch-ins at sentence or point ends (punctuation boundaries from the word timestamps), plus emphasis words. Never place them at random. Anchor every zoom on the tracked face bbox and clamp it so the bbox plus a margin stays inside the frame (a "face in frame" check). Use about 1.15-1.35x. Our own QC can reproduce their visual check: assert the face bbox stays in the frame after the zoom.
2. **Re-centre the crop on every camera cut.** Detect shots (for example with PySceneDetect or a histogram diff), find the active face in each shot, and reset the smoothing at each cut so the crop never drifts across one.
3. **Captions:** 2-3 words per page, words added one at a time, the active word in an accent colour, a white base, a thin dark stroke plus a soft shadow, and a quick scale-pop on each new word (for example 80% to 105% to 100% over about 120 ms). Position at about 62-66% of the frame height. This matches our Montserrat Black ALL CAPS spec, so adopt the karaoke active-word colour and the pop.
4. **Keyword boxes:** for money, number and status words (BILLIONAIRE, MILLION, numbers with $, superlatives), show the word alone in a dark rounded box with a glowing accent border. Limit it to about 1 every 6-8 s; this can count as one of our "accents".
5. **SFX:** a whoosh only on cuts or zooms, with a variety of samples. Provide an `sfx=false` switch.
6. **Expose prompt-level parameters** (caption accent colour, maximum duration, clip count, `sfx` on or off, "best clip only") so a follow-up like "only the best clip, under 30 s, no SFX, blue captions" re-renders without re-running download or transcription. Cache the intermediates: transcript, highlight scores, face tracks.
7. **Final summary table:** `# | Title | Length | Opens with (hook quote)`. Titles in Title Case. Each clip must start exactly on the hook line. Output goes to `output/<slug>-<videoId>/edited/`.
8. **Speed target:** about 1 min of edit time per clip (they did 7 clips in 7 min).

### Conflicts or differences against our IShowSpeed style

- **Canvas:** they use 9:16 full-bleed; we use 3:4. Keep 3:4, but their per-cut re-centring and face-bbox zoom clamping carry over directly.
- **Clip length:** their clips run 29-76 s and are not capped at 60. Ours stay at 60 s or under by default. Treat their 76 s and 68 s clips as a cautionary example.
- **Energy:** their edit is calm podcast style: no b-roll, no progress bar, no hook title card, no shake, SFX only at cuts, and mild zooms. IShowSpeed style wants more frequent and harder accents (every 6-8 s: zoom-punch, shake, keyword box, SFX). Use their rule of anchoring zooms at sentence ends as the placement logic, but add our higher-intensity accents on top.
- **Caption position:** they place captions at about 64% height. With our 3:4 canvas and a tighter face crop, captions at that height may cover the chin. Check against the face bbox and push them below it.
- **Highlight colour:** their default is yellow. We use varied accent colours, which fits since they also allow a prompt override (blue).

=== setup+picking ===
# Slice 189–343 s: setup and how it picks moments ("Claude Code Can Now Clip ANY Video", Eddie | AI)

I looked at every frame from f_0095 to f_0173, using contact sheets in <job>/tut1/sheets_s2/. I also pulled full-res stills at <job>/tut1/hi_207.png, hi_224.png, hi_251.png, hi_283.png and hi_339.png.

## 1. What you need (188–207 s)
- **What he says:** "you only need these two things: Claude Code, which you can download for free, and a paid Claude plan. The pro plan works fine. Everything else Claude will set up for you."
- **On screen:** a "You only need two things" graphic with two cards:
  - "Download Claude", labelled "Free download".
  - The "Pro – For everyday work" plan at $17/mo billed annually ($200 up front) or $20 billed monthly, labelled "Paid plan".
- **No API keys are mentioned or shown anywhere.** Transcription runs locally with faster-whisper. The LLM work is Claude Code itself, so no Anthropic API key is needed either.
- **Where the skill comes from:** a Skool community, "AI Builders Club" (skool.com/ai-builders-club-2189/about), "free to join for 7 days". The course card is "FREE AI CLIPPER – Long-Form Clipper".

## 2. Course page, Lesson 1 "What This Skill Does" (t≈206, hi_207.png)
- Tagline: "You paste one link. Claude watches the whole video, picks the best moments, [cuts them] vertical, and edits every single one."
- "What you get back":
  - "3 to 8 vertical clips (9:16, 1080x1920), ready for YouTube Shorts, Instagra[m], TikTok"
  - "Every clip starts on a hook and ends on a payoff, so it works for someone [with no] context"
  - "The frame re-centres on whoever is speaking, every time the camera cuts"
  - "Zooms, word-by-word captions and a couple of subtle whooshes on every [clip]"
  - "A title and a ready-to-post caption for every clip"
- "My test run":
  - "MrBeast on The Diary Of A CEO, 1 hour 43 minutes"
  - "7 finished clips, 28 to 75 seconds each"
- Course modules: Module 1 Start Here (Lesson 1 What This Skill Does, Lesson 2 What You Need), Module 2 Setup (Once), Module 3 Clip Your First Video, Module 4 Fixes and Ground Rules.

## 3. Skill structure (208–225 s, hi_224.png)
- He downloads `Claude-Video-Clipper-main.zip` (1,388 KB), uses right-click > Extract All, and gets a nested `Claude-Video-Clipper-main\Claude-Video-Clipper-main`.
- It is a repo-style project, not a bare SKILL.md. Repo root:

| Item | Type | Size |
|---|---|---|
| `.claude/` | folder (skill/instructions) | – |
| `assets/` | folder (fonts/SFX likely) | – |
| `clipper/` | folder (Python package) | – |
| `output/` | folder | – |
| `remotion/` | folder | – |
| `.gitattributes`, `.gitignore` | files | 1 KB each |
| `CLAUDE.md` | file | 1 KB |
| `install.py` | file | 4 KB |
| `LICENSE` | file | 2 KB |
| `README.md` | file | 7 KB |
| `requirements.txt` | file | 1 KB |
| `run.py` | file | 2 KB |

- Later (t≈346–348) the "Edit" stage card names the scripts **`cut.py`, `reframe.py`, `edit.py`, `sfx.py`**.

## 4. One-prompt setup (226–250 s)
- He opens the Claude Code desktop app on the folder "Clipper Tool" (Auto mode, Opus 5.5 Medium).
- Prompt typed on screen: **"Hey Claude can you set up this full repository for me."** He paraphrases it out loud as "can you set up this folder repository for me".
- What Claude does, step by step (t≈236–248):
  1. "Ran 2 commands"
  2. "Docs look clean. Checking prerequisites first."
  3. "Checked Python, ffmpeg, Node, GPU"
  4. "All prerequisites present. Running the installer (both Python deps and the optional Remotion engine)."
  5. A permission prompt: "Allow Claude to run this command? `python install.py`" (Allow)
  6. "Ran project installer with Remotion"
  7. "Quick smoke test that the CLI and imports work:" then "Smoke test CLI and Python imports"
- He says "If it asks for any permissions, just click allow. After a few minutes … setup is complete … you only do this setup once."

Final setup summary (hi_251.png), verbatim:
- "The Clipper Tool is set up and ready to use. The help screen runs and all the main Python packages load, but I haven't clipped a real video yet."
- **Tools it needs:** "Python 3.12, ffmpeg and Node.js v24 were already on your machine."
- **Python packages:** "the installer put everything in a private environment (`.venv`) inside the project folder, including the YouTube downloader (yt-dlp), the transcriber (faster-whisper) and OpenCV."
- **Remotion:** "I also installed the optional Remotion engine. It's a slower way to render the edit; the default engine needs nothing extra."
  - So the default renderer is Python/ffmpeg/OpenCV, and Remotion is an optional fallback.
- **Where it lives:** "…Open *that* folder in Claude Code so its built-in clipping instructions load." So the instructions come from the project's `.claude/` and `CLAUDE.md`.
- **To use it:** "say `clip this video: <youtube link>` and Claude handles the download, picks the moments, cuts them to vertical and edits them. Results go to `output/<video>/`."
- **Things to know:**
  - "First run is slower: the first transcription downloads a ~500 MB speech model once." (This matches the faster-whisper "small" model size.)
  - "Graphics card: you have an NVIDIA GTX 1650, so `--device cuda` could transcribe faster… The default (your processor) works fine." So the CLI has a `--device` flag and defaults to CPU.
  - "YouTube 'not a bot' error: run the fetch with `--cookies-from-browser chrome`."

## 5. Running it (250–285 s)
- Prompt: `clip this video: https://youtu.be/bWGoo2dwTKY?si=…`. He pastes the YouTube share link and uses his own 8-minute video.
- Claude replies (hi_283.png): "Ran 2 commands. It's an 8-minute video from your own channel (Eddie | AI), so rights are fine. Downloading and transcribing now, which should take about 2–4 minutes. [Downloading audio and transcribe video – View live output] Transcription is running in the background. I'll pick the moments as soon as it finishes."
  - So it checks rights or ownership.
  - It downloads the audio separately for transcription.
  - It runs transcription as a background task.
- He says the first run "has to download Whisper, which transcribes your videos". An on-screen toast reads "Whisper – Downloading the speech model, once".
- **Time claim:** "going to take two to four minutes to clip everything" (for the 8-minute video).

## 6. How it picks the best moments (286–343 s)
- An animated 4-stage pipeline graphic:
  1. **Watch:** "downloads + transcribes"
  2. **Pick:** "finds the best moments"
  3. **Cut:** "cuts them vertical"
  4. **Edit:** "captions, zooms, sounds"
- Heading on screen: "Claude really acts like your [editor]".

What he says, verbatim:
- "It reads the whole transcript of the video start to finish". On screen is a timestamped line-by-line transcript (mm:ss per line). **The LLM reads the full transcript, not chunks or heuristics.**
- "it's looking for moments that work on their own, something a total stranger could watch with zero context and fully understand". The on-screen badge says "0 context".
- "Right before it, Mr. Beast is kind of rambling. So Claude skips all of that and starts the clip exactly on this hook."
  - On screen, lines 22:19–22:23 ("I just…" crossed out, "I don't know if I should, but I can.", "And then I don't know.", "It's like…") are boxed and tagged **WARM-UP**, then removed.
  - Line 22:25 "To go viral, you have to do something that's never been done before." is tagged **HOOK**.
- "Now that's the first thing you hear and it ends on the payoff, so the clip actually feels finished instead of just cutting it through."
  - On screen, 23:23–23:28 "…And if something's never been done before, there's usually a reason because it's very f***ing hard." is tagged **PAYOFF**.
  - A timeline scrubber runs 0:00–1:08, so that clip is about 68 s long.
- "It also knows the types of hooks that work on shorts like a surprising fact or a bold claim or the start of a story. And every clip has to open with one of them."
  - The on-screen "Hooks that work on shorts" graphic labels every candidate clip with one of **four hook categories: `contrarian`, `surprising fact`, `novel claim`, `story opener`**.
- "Then it gives every clip a score out of 10 and ranks them so the best one is always first."
  - On screen (hi_339.png): cards labelled #1 10/10, then 9/10, 9/10, 8/10, 8/10, 7/10, and more. The pool is first scattered with scores (10, 9, 9, 8, 7, 8, 8), then sorted in descending order.

**The picking rules, put together:**
1. Read the full timestamped transcript.
2. Each clip must stand alone, so a viewer with 0 context understands it.
3. Start exactly on the hook line and trim the warm-up or rambling before it, including filler ("I just…").
4. The hook must be one of: contrarian, surprising fact, novel claim (bold claim), story opener.
5. End on a payoff line so the clip feels finished.
6. Score each clip 1–10 and rank in descending order (#1 first).
7. Return 3–8 clips, typically 28–75 s long (MrBeast test: 7 clips from 1 h 43 m).
8. Each clip also gets a title and a ready-to-post caption.

## 7. What the output clips look like (frames 68–75)
- Format: 9:16 MrBeast close-ups with the face centred.
- Captions: **2 words max**, ALL CAPS, heavy rounded geometric sans (Montserrat ExtraBold/Black-like). They have a dark outline/shadow and sit just below the chin (around 55–60 % of the height). The active word is in **yellow/gold** and the other word in white. Examples: "I'LL **DROP**", "I'VE **LESS**", "SAD **FACT**", "**99%**", "MORE A **PLAYERS**".
- Shots show visible punch-in zoom variation (tighter versus wider crops).

## 8. Cost and time claims
- Free apart from the Claude Pro plan ($17–20/mo). No other APIs.
- Setup takes "a few minutes", once.
- Clipping an 8-min video takes 2–4 min. The first run is longer because of the ~500 MB Whisper download.

---

## ACTIONABLE for our skill
1. **Use a repo-style layout plus a one-prompt installer:** `install.py` creates `.venv`, installs yt-dlp, faster-whisper and opencv, checks Python, ffmpeg, Node and GPU, then smoke-tests the CLI (`run.py --help`, imports). Add a `CLAUDE.md` with the trigger phrase `clip this video: <link>`. Output goes to `output/<video>/`.
2. **Split the pipeline into four modules:** `cut.py`, `reframe.py`, `edit.py`, `sfx.py`, plus a `run.py` CLI with `--device cpu|cuda` (default CPU and auto-detect CUDA) and a `--cookies-from-browser chrome` fallback for yt-dlp "not a bot" errors.
3. **Transcribe in the background** (faster-whisper with word timestamps; small model, ~500 MB) and download audio only for transcription. Tell the user the ETA.
4. **Picking prompt rules to copy:** read the whole timestamped transcript. Each candidate must
   - be understandable by "a total stranger with zero context";
   - start exactly on the hook line, with warm-up and filler trimmed;
   - open with a hook from one of {contrarian, surprising fact, novel/bold claim, story opener}, recorded as a `hook_type` field;
   - end on a payoff that "feels finished".
   Score each candidate /10, sort in descending order, and output the title and post caption for each.
5. **Return structured JSON per clip:** `{start, end, hook_line, hook_type, payoff_line, score, title, caption}`. Trim at word boundaries.
6. **Rights check:** note whether the source is the user's own channel (their demo does this).
7. **Speaker-change re-centre on every camera cut:** detect scene cuts, then re-detect the face and recentre.
8. **Caption look matches ours:** heavy sans, ALL CAPS, yellow active-word highlight with white for the rest, below-face position. Useful confirmation.

### Conflicts with our IShowSpeed-edit style
- **Clip length:** their clips are 28–75 s and the demo clip is 68 s. We cap at ≤60 s, so force end ≤ 60 s (pick a payoff before 60 s, or score down candidates that need more than 60 s).
- **Canvas:** they output 9:16 1080x1920. We use 3:4, so keep ours.
- **Captions:** their captions are 1–2 words. Ours are 2–4 words in Montserrat Black ALL CAPS. Same font family and look, but our phrases are longer.
- **Effects:** they use "a couple of subtle whooshes" and modest zooms per clip. IShowSpeed-style needs louder, more frequent accents every 6–8 s (SFX, punch zooms, shake), so their "subtle" setting is too tame for us.
- **Reframe:** they recentre on each camera cut, which is a static crop per shot. We want a smoothed, continuously tracked face crop, so keep our tracker and also reset it on scene cuts.
- **Number of clips:** they output 3–8 ranked clips. The scoring and ranking transfers directly, and our default is the top 3 clips scoring >= 7/10 unless the user asks for a different count.

=== editing+cost ===
# Slice 343s-499s: "how it edits" plus the cost comparison with OpusClip
Source: Eddie | AI, "Claude Code Can Now Clip ANY Video (Free Skill)". Sources used: the transcript lines from 336 s to 499 s, every 2 s frame from f_0172 to f_0250 (viewed as contact sheets), and full-res stills at 370, 373, 383, 399, 459 and 469 s.

## 1. Edit stage overview (339-350 s)
- **339 s, said:** "Now let's get into how it actually edits them. Once Claude picks the clip, it hands them off to a few Python scripts inside of the skill that do the actual editing all right from your computer."
- **On screen:** a 4-card pipeline, the same one used earlier in the video:
  1. **Watch**: "downloads + transcribes"
  2. **Pick**: "finds the best moments"
  3. **Cut**: "cuts them vertical"
  4. **Edit**: "captions, zooms, sounds"
- **~346 s:** the Edit card expands into a Python logo with 4 script chips: **`cut.py`, `reframe.py`, `edit.py`, `sfx.py`**. This is the skill's file layout:
  - LLM step: choosing the moments.
  - Deterministic Python steps: cut, reframe, edit (captions and zooms), sfx.

## 2. Captions from Whisper word timestamps (350-362 s)
- **Said:** "remember Whisper, it doesn't just write down what's being said, it saves the exact moment every single word is spoken. And that's how each caption pops in and out right on time."
- **On screen:** a "Whisper" card showing "Are you a billionaire? / On paper, yeah." with a timestamp under each word. The timestamps look like seconds:hundredths:
  - Are 0:00.12
  - you 0:00.26
  - a 0:00.40
  - billionaire? 0:00.52
  - On 0:02.24
  - paper, 0:02.54
  - yeah. 0:03.08
- Next to it is a vertical clip of the guest in side profile, with a caption reading "ARE YOU A".
- **Method:** per-word timestamps (Whisper `word_timestamps=True`) drive word-by-word captions. The course page (465 s) says it outright: "word-by-word captions".
- **Caption look in the outputs** (stills at 373, 399 and 459 s):
  - Bold geometric sans in ALL CAPS, possibly Montserrat ExtraBold or similar.
  - White words, with the current or last word in the accent yellow/gold. Examples: "SO **DO**", "ARE **YOU** A", "I'VE **LESS**", "ELSE **EVEN** GETS".
  - Small (about 5-6% of frame height) and placed just below the face at chest level, not at the bottom.
  - Thumbnails at 460 s show "THE", "SO DO YOU", "IF YOU'RE", "IT'S NOT THAT", "OBVIOUSLY NEVER", "DEEPLY", "AMONGST A BUNCH". That is 1-3 words per caption, and the active word changes colour (karaoke-style).
  - No box behind the text. There is a thin dark outline or shadow.

## 3. Face detection, zoom timing, framing on cuts (362-376 s)
- **Said:** "for the zooms, it uses face detection to find the face in every single shot. And then it places each zoom at the end of a sentence every few seconds. It even changes the framing on every camera cut so the jump doesn't feel too harsh."
- **On screen, 366-370 s:** a 16:9 podcast frame (two-shot with a table and chandelier). Then single shots of each speaker, each with a yellow rounded face box from a face detector. The animation does not name a library.
- **Zoom timeline:** a timeline bar for a 0:47 clip, with a playhead and tick marks.
  - The ticks are irregular: about 4 in the first 10 s, then spread across the clip, roughly 13-15 ticks in total.
  - Each tick is a sentence end, so zooms are tied to punctuation boundaries rather than a fixed interval.
- **Zoom amounts, 372-376 s:** 9:16 tiles labelled with scale factors **1.16×, 1.04×, 1.22×**.
  - Small, varied punch-ins.
  - Alternating: a strong 1.16× (highlighted chip), then a light 1.04×, then a strong 1.22×.
  - Consecutive camera cuts get different scales so jump cuts feel less harsh. The changed framing on cuts is a scale and offset change.
- **Course page (465 s):** "The frame re-centres on whoever is speaking, every time the camera cuts". So there is a shot-cut-triggered re-centre on the active speaker, not continuous smooth tracking. The re-centre seems to happen once per shot, though this is not stated explicitly.
- **Log at 399 s gives zoom density:**
  - `ok 01-want-to-be-liked-dont-help-people.mp4  zooms:19  captions:105`
  - `ok 02-billionaire-on-paper-broke-in-the-bank.mp4  zooms:13  captions:72`
  - Clips are 28-75 s, so this is about one zoom every 3-4 s and roughly 2.5-3 words per caption event.

## 4. Caption colour logic (376-386 s)
- **Said:** "for the caption color, it tries the creator's brand color first. Now, if it's not sure what the color is, it just pulls the color from the video so everything matches based off the video's branding."
- **On screen:** "Caption *colour*", with two cards:
  - **(1) Brand colour**: an empty swatch, then a "?", meaning unknown.
  - **(2) Colour from the video**: a colour picker on the video frame giving a 4-swatch palette (steel blue, dark teal, maroon, red). One swatch gets a check mark.
- **Log at 399 s:** `-> brand colours: accent #FFD60A (default)`.
  - The fallback default accent is **#FFD60A** (yellow), and the run used it.
  - **Order:** brand colour, then colour sampled from the video, then default #FFD60A.

## 5. Sound effects (386-395 s)
- **Said:** "for the sound effects, I gave it these three sound files in the [skill] file. So it adds couple of whooshes on every zoom."
- **On screen:** a file window titled "assets / sfx" containing:
  - **`click.wav`** (WAV)
  - **`whoosh-cinematic.mp3`** (MP3)
  - **`whoosh-heavy.mp3`** (MP3)
- The path chip reads **`claude-clipping-tool / assets / sfx`**. When "whoosh-heavy.mp3" is highlighted, a clip plays with caption "ELSE EVEN GETS".
- The course page says "a couple of subtle whooshes on every clip". The spoken line says "on every zoom", which conflicts with it. In practice it is probably a whoosh on some or all zooms, mixed subtly. There is no music bed.

## 6. Render (395-400 s)
- **Said:** "once the full workflow is done, it renders the final clip in 1080p."
- **Claude Code transcript on screen (399 s).** Prompt: `Run the clipper skill for this video https://youtu.be/FjrJ2DJN_pA?si=...` Steps shown:
  - Ran 2 commands
  - "It's a 1:43:14 podcast episode. Downloading and transcribing it now."
  - Downloading audio and transcribe video
  - Picked the 7 best moments
  - Cut 7 vertical clips
  - Added captions, zooms and sound effects
  - Rendering the final clips: "View live output"
- **Live output:**
```
-> brand colours: accent #FFD60A (default)
-> editing clip 1: Want To Be Liked? Don't Help People (python engine)
   ok 01-want-to-be-liked-dont-help-people.mp4  zooms:19  captions:105
-> editing clip 2: Billionaire On Paper, Broke In The Bank (python engine)
edited/02-billionaire-on-paper-broke-in-the-bank.mp4   [1080 x 1920]  100%
   ok 02-billionaire-on-paper-broke-in-the-bank.mp4  zooms:13  captions:72
```
- **Conventions visible in the log:**
  - Output folder `edited/`.
  - File names are a numbered, slugified title: `NN-title-slug.mp4`.
  - Each clip gets a Title Case title.
  - Each clip prints stats (zoom and caption counts).
  - "(python engine)" suggests there may be another engine, e.g. Remotion or ffmpeg, but this is not shown.
  - Output is 1080×1920 (9:16).

## 7. Cost comparison (400-455 s)
**OpusClip (spoken, with its site and pricing shown):**
- "Most clipping tools charge you by the minute."
- OpusClip is "the biggest clipping tool out there".
- **Starter: $15/mo, 150 credits per month, 1 credit = 1 minute of video processing.** Pricing page bullets also include AI clipping with Virality Score, AI animated captions in 20+ languages, and auto-post to Shorts/TikTok/Reels.
- **Pro: $29/mo, 300 credits.**

**The test podcast against OpusClip:**
- "this one Mr. Beast podcast would use up to 2/3 of your whole month". The on-screen bar shows 150 min/month with a 1:43:14 video filling much of it.
- "even Opus Clip's $29 plan only covers about three podcasts this long every single month". The card reads: OpusClip Pro $29/month, 300 minutes, about 3 podcasts like this a month.

**This skill:**
- "This skill doesn't use credits at all."
- On screen: "FREE SKILL", "0 credits", "$0", and a "Runs on your computer" checklist: Download, Whisper, Cutting, Editing.
- **Free and local:** download (yt-dlp implied), Whisper transcription, cutting, editing.
- **Only paid part:** "The only part that actually uses AI is only when Claude is picking the moments to cut... runs on your Claude plan." On screen, the "Pick" card is tagged "Your Claude plan".
- **Claude Pro: $20/month, about 5 podcasts like this a week, plus everything else you use Claude for.**
- **Implied architecture:**
  - The LLM reads only the transcript to pick moments.
  - No paid APIs: no paid transcription, no paid caption or reframe service.
  - Whisper runs locally.

## 8. Course page and test-run claims (455-470 s, Skool "AI Builders Club", $29/mo, 7-day free trial)
- **"Lesson 1: What This Skill Does" (verbatim):** "You paste one link. Claude watches the whole video, picks the best moments, cuts them vertical, and edits every single one."
- **What you get back:**
  - "3 to 8 vertical clips (9:16, 1080x1920), ready for YouTube Shorts, Instagram Reels and TikTok"
  - "Every clip starts on a hook and ends on a payoff, so it works for someone with zero context"
  - "The frame re-centres on whoever is speaking, every time the camera cuts"
  - "Zooms, word-by-word captions and a couple of subtle whooshes on every clip"
  - "A title and a ready-to-post caption for every clip"
- **My test run:**
  - "MrBeast on The Diary Of A CEO, 1 hour 43 minutes"
  - "7 finished clips, 28 to 75 seconds each"
  - "Under 40 minutes end to end, and I didn't touch anything after sending the prompt"
- **Course modules:**
  - Module 1: Start Here
  - Module 2: Setup (Once)
  - Module 3: Clip Your First Video
  - Module 4: Fixes and Ground Rules
- **487-499 s:** an outro plugging another video, "automate my Instagram to post 20 reels a day". Nothing about clipping.

## ACTIONABLE for our skill
1. **Split by job.** The LLM only picks moments and writes the title and post caption. Everything else is deterministic local Python, split as `cut.py` / `reframe.py` / `edit.py` / `sfx.py`. Keep our cost story the same: $0 marginal cost, everything local, Whisper local. This is in line with our design.
2. **Word-level Whisper timestamps** drive captions, with the active word highlighted in the accent colour (karaoke style). Their caption events average about 2.5-3 words (105 events in about 60 s).
3. **Place zooms at sentence ends from the transcript punctuation, not on a fixed timer.**
   - Spacing is irregular, about 3-4 s.
   - Use varied, small scales in the 1.04-1.22× range, alternating strong and light (for example 1.16 → 1.04 → 1.22).
   - Write the zoom count to the log per clip.
4. **On every camera or shot cut, re-centre on the active speaker** and change the scale slightly between consecutive shots, so jump cuts don't feel harsh. Detect shot cuts with scene detection and pick the speaker per shot.
5. **Accent colour order:** brand colour (if known) → dominant or saturated colour sampled from the video frames → default **#FFD60A**.
6. **Keep an SFX asset folder** (`assets/sfx`) with click plus 2 whoosh variants, and add a subtle whoosh on zooms.
7. **Output conventions:**
   - `edited/NN-title-slug.mp4`, plus a per-clip log line `ok file zooms:N captions:N`.
   - Write a title and a ready-to-post description for each clip.
   - Produce 3-8 clips per long video.
   - Each clip starts on a hook and ends on a payoff, so it works for someone with zero context.
8. **Benchmark against their claim:** a 1h43 video gives 7 clips in under 40 minutes end to end, with no human touch after the prompt. Aim to match or beat it.

### Conflicts with our IShowSpeed-edit style
- **Canvas:** they render 9:16 1080×1920. Our style uses a 3:4 canvas. Keep 3:4, or treat 9:16 as an export option only.
- **Clip length:** their clips run 28-75 s. Our cap is ≤60 s, so drop or trim anything over 60.
- **Framing:** they hold a static, re-centred frame per shot and change it only at cuts. We want a smoothed, continuously tracked face crop. Adopt their per-cut re-centre and scale variation on top of our smoothing (reset the smoother at shot cuts so it doesn't drift across a cut), rather than replacing it.
- **Zoom and accent density:** they zoom every 3-4 s at sentence ends (13-19 per clip), all subtle. Our accents land every 6-8 s and are louder (IShowSpeed punch-ins, SFX hits). We could use their sentence-end placement rule but thin it to every 6-8 s. Their 1.04-1.22× range suits our "rest" zooms, and accent zooms can go bigger.
- **Captions:** theirs are a smallish bold sans, 1-3 words, ALL CAPS, white with a yellow active word, placed at chest level. This roughly matches our Montserrat Black ALL CAPS 2-4 words, but ours should be bigger and heavier. Their single-word events ("THE", "DEEPLY") fall below our 2-word minimum, so merge them.
- **SFX:** theirs is "subtle whooshes", which is tamer than IShowSpeed edits (bass hits, rizz or vine booms, varied SFX). Keep their whoosh-on-zoom as the baseline and add our louder accent SFX at the 6-8 s accent points.
- **Brand-colour accent:** compatible. Our yellow/gold highlight matches their #FFD60A default, so we could use the same fallback order.
