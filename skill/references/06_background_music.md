# 06 - Background music: choosing a licence-safe bed for a short

How to pick the music bed under a clip, where to get it, which licences are safe, and how `scripts/find_music.py` does it. The bed's levels come from ref 01 section 6 (continuous bed from frame 0, ducked about 10 dB under speech, about -20 LUFS in gaps). Mixing is `scripts/mix_audio.py`. Licence facts were checked on the official pages listed in section 6, accessed 2026-11-01. This is not legal advice: a licence page wins over this summary.

## 1. Choosing a bed
- **Mood from the transcript.** The LLM reads the clip's lines and picks one mood. Defaults:

| Mood | BPM (half/double time also counts) | Energy 0-1 | Prefer | Avoid |
|---|---|---|---|---|
| hype (default, ref 01) | 130-160 (65-80 half time) | 0.75 | phonk, trap, hip-hop, electronic, drill, dubstep | ambient, piano, acoustic, sad, calm |
| tense | 85-120 | 0.50 | dark, suspense, cinematic, drone | happy, upbeat, comedy |
| funny | 100-130 | 0.55 | quirky, comedy, playful, funk, ukulele | dark, sad, aggressive |
| emotional | 60-90 | 0.25 | piano, strings, sad, lofi, ambient | phonk, trap, aggressive |
| chill | 70-100 | 0.30 | lofi, chillhop, jazz, downtempo | aggressive, metal |
| epic | 120-150 | 0.70 | cinematic, orchestral, trailer | lofi, acoustic |
| inspiring | 100-128 | 0.55 | uplifting, motivational, pop | dark, aggressive |

- **No vocals under speech.** A sung or rapped line competes with the dialogue for 300-3400 Hz, so captions and ears lose. Use instrumentals only, or a vocal track only over speechless stretches (5 s or less, ref 01 section 8).
- **Strong from frame 0.** Enter at the track's strongest section. The entry point is the earliest time whose next 5 s reach the 75th percentile of all 5 s windows' mean short-term loudness (mix_audio.py's rule). A 6-20 s ambient intro would drain the hook. Never fade the bed in.
- **Phone-speaker low end.** Phone speakers roll off below about 150 Hz. A bed with 50% or more of its energy under 150 Hz (808-heavy phonk is typical) sounds thin and quiet on phones. Prefer beds with bright hats, snares and mid synths. mix_audio.py warns at the same 50% line.
- **Length.** Usable = duration - entry offset. If that is under the clip length, mix_audio.py loops it with a 0.3 s equal-power crossfade. That works, but a track that covers the clip is better.
- **Speech clash.** Prefer beds whose energy sits outside the dialogue's main bands, such as sub plus hats rather than a dense mid pad. The 10 dB duck handles the rest.

## 2. Sources, ranked by safety
Re-check the source page before each new track. Terms change: Pixabay's terms were updated on 2026-10-20.

1. **CC0 / Public Domain Mark** (Openverse, FMA, Freesound music)
   - No conditions, so no credit is needed. Credit anyway: it costs nothing and helps a dispute.
2. **YouTube Audio Library** (in YouTube Studio)
   - Two kinds of track:
     - "Attribution not required": the standard Audio Library licence, no credit needed.
     - "Attribution required": Creative Commons. YouTube says "you must credit the artist in your video's description". Copy the credit text from the Creative Commons icon in the "License type" column.
   - YouTube says Audio Library music "won't be claimed by a rights holder" through Content ID and can be used in monetised videos.
   - The help page says nothing about use outside YouTube. So treat "attribution not required" tracks as YouTube-only. For TikTok and Instagram, use a CC BY track (its licence is platform-free) or another source.
3. **Pixabay Music** (Pixabay Content License)
   - Free, and "without having to attribute the author".
   - You may "Modify or adapt Content into new works".
   - Prohibited: selling or distributing it on a "Standalone basis" (substantially unchanged), and misleading, illegal or trademark use.
   - "Audio" in the licence includes music. Syncing a track into an edited short is not Standalone.
4. **Incompetech (Kevin MacLeod)**
   - Licensed under CC BY 4.0. The credit block from the FAQ, with the track title first:
     `<Title> Kevin MacLeod (incompetech.com)` / `Licensed under Creative Commons: By Attribution 4.0` / `https://creativecommons.org/licenses/by/4.0/`
   - Where a credit is impossible, buy the paid Standard License.
5. **NCS (NoCopyrightSounds)**
   - "free to use for independent creators and their UGC" on YouTube and Twitch.
   - Credit "the Artist and song(s) used in the description". Copy the credit section from NCS's own video description.
   - Brands and services promoting products need a licence from NCS.
   - The usage policy page does not name TikTok or Instagram, so confirm with NCS before posting there.
   - Mostly EDM, not phonk. Local manifest licence text: `royalty-free (NCS usage policy), credit required`.
6. **Free Music Archive and Jamendo** (per-track Creative Commons)
   - **FMA:** "FMA artists can upload their own music and select a specific CC licence themselves". Licences run from CC0 and CC BY to BY-NC-ND. Read the licence on each song page.
   - **Jamendo:** "Every CC license on Jamendo starts with the condition BY", and Jamendo "does not support the CC0 license type". Many tracks are NC, ND or SA. find_music.py keeps only CC BY, which it reads from `license_ccurl`.
7. **Openverse** (search engine over Jamendo, Wikimedia Commons and Freesound audio)
   - No API key is needed.
   - `license=` accepts `by, by-nc, by-nc-nd, by-nc-sa, by-nd, by-sa, cc0, nc-sampling+, pdm, sampling+`. `category=music`.
   - Anonymous use is rate-limited (HTTP 429) and its pagination is limited.
   - Openverse indexes the licence but does not grant it. Open `foreign_landing_url` and confirm there.
   - Measured 2026-11-01:
     - `/v1/audio/stats/` answered in 0.04 s.
     - Filtered searches (`category=music&license=cc0,by`) were unreliable: HTTP 504 after 60 s, or no answer within 25-60 s.
     - `q=phonk` returned 0 results once. In a later run, `phonk` and `trap` answered within about 10 s and gave 14 CC BY 3.0 Jamendo tracks, while `hip hop beat` timed out.
     - A plain `q=electronic&page_size=5` answered in 20.6 s. All 5 results were Jamendo tracks under BY-NC-ND 3.0 or BY-NC-SA 3.0, so all were rejected.
   - Treat Openverse as a bonus source, not the main one.
- **Never:** "no copyright" re-uploads on random YouTube channels, slowed or reverb copies of chart songs, and anything ripped from a film or game. These are claimed or muted within hours.

## 3. Licence policy (find_music.py default)
- **Accept:**
  - CC0
  - Public Domain Mark
  - CC BY, which needs credit
  - local tracks whose `licences.json` licence says royalty-free / no attribution / attribution not required / Pixabay Content License / YouTube Audio Library
- **Reject:**
  - **NC:** a short on a monetised or brand account is commercial use.
  - **ND:** CC 4.0 legal code section 1(a) says "where the Licensed Material is a musical work, performance, or sound recording, Adapted Material is always produced where the Licensed Material is synched in timed relation with a moving image." BY-ND lets you "produce and reproduce, but not Share, Adapted Material". So you cannot publish the short.
  - **SA:** the synced short is Adapted Material, so section 3(b)(1) of BY-SA requires that "The Adapter's License You apply must be a Creative Commons license with the same License Elements". That puts the whole short under BY-SA.
  - **CC 3.0 tracks** (common on Jamendo) say the same: "the synchronization of the Work in timed-relation with a moving image ("synching") will be considered an Adaptation".
  - **Sampling+**, which covers sampling only.
  - **Unrecognised licence text.**
  - **Files with no manifest entry:** listed as `unverified`, never picked.
- **Override per request:** `--allow by-sa` (or `by-nc`, `custom`) only when the person has read the terms and accepts them, for example for a non-monetised personal post.
- **CC BY credit:** the credit must identify the creator, refer to the licence, and link to the material "to the extent reasonably practicable". It may be given "in any reasonable manner based on the medium" (CC BY 4.0 section 3(a)(1)-(2)). For a short, use the post caption or video description.

## 4. "Copyright-free" still gets claimed
- **Content ID claims still happen.** Royalty-free and CC tracks can still be claimed: an artist registers the track with a distributor's Content ID, or a third party re-uploads it. A claim is not a strike, but it can redirect the revenue or mute the audio.
- **Keep licence proof per clip.** find_music.py writes `music.json` with:
  - landing URL
  - licence name and URL
  - credit line
  - date retrieved

  Also keep a screenshot of the landing page showing the licence. To dispute a claim, quote the licence and the landing URL.
- **Trending in-app sounds are licensed only inside the app.** GEMA (the German music collecting society) says TikTok sounds may be presented or shared "only on TikTok, not on other platforms". Instagram's library is licensed "exclusively for use on Instagram" and not for commercial use.
- **Music added before upload is the uploader's responsibility.** A trending song baked into the exported MP4 is not covered by any platform licence. Reposting the same MP4 to YouTube Shorts gets it claimed.
- **To use a trending sound:** post the clip without music and add the sound in the app (personal accounts only). Business accounts use only TikTok's Commercial Music Library.

## 5. Credit line for captions.md
- One line per clip. Paste it into the post caption or description whenever `credit_required` is true. Keep it in `captions.md` anyway.
  `Music: "<Title>" by <Creator> (<landing URL>), licensed under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/)`
- **CC0 / PD:** `Music: "<Title>" by <Creator> (<landing URL>), CC0 1.0 (no credit required)`
- **Manifest attribution wins.** When the source gives its own credit text (Incompetech, the YouTube Audio Library CC pop-up, NCS), that verbatim text goes in `licences.json` as `attribution`, and the script uses it.
- On TikTok and Reels the caption is the only place for credit. Keep it on one line after the hashtags.

## 6. How find_music.py plugs into the pipeline
- **When to run it.** Step 6 (Polish), after the cutlist fixes the clip length and the dialogue stem exists, before mix_audio.py:
  - `find_music.py --mood hype --clip-s 47.2 --dialogue clips/01/dialogue.wav --library music/ --choose --out-dir clips/01`
  - It writes `clips/01/bed.<ext>` and `clips/01/music.json`.
  - Copy `music.json`'s `bed` block (`path`, `offset_s`, `lufs: -20`) into `audio_plan.json` as `"bed"`. Add `mutes` there if the clip has a tension mute.
  - Add `attribution` to the clip's `captions.md` entry.
- **Local library.** One folder for all jobs, with tracks plus `licences.json`:
  `{"neon.mp3": {"title", "artist", "source_url", "licence", "attribution", "notes", "tags": ["phonk", "instrumental"]}}`
  Tags help the ranking, and `instrumental` / `vocal` in the tags override the audio vocal heuristic.
- **Providers.**
  - `local` is always tried when `--library` is set.
  - `openverse` uses a 20 s timeout and 1 retry. If the filtered search still fails, the script tries one plain `q=` search and applies the category and licence filters itself. If that fails too, it uses a stale cache entry if there is one, otherwise it gives a warning.
  - `jamendo` runs only when `JAMENDO_CLIENT_ID` is set. The key is a free app key from devportal.jamendo.com and never reaches the cache or the output.
  - `--offline` uses the library only.
- **Exit codes.**
  - 1: no candidate passes the licence policy. The JSON `hints` say what to add.
  - 2: a usage error.
- **Re-edits.** Downloads, API answers (24 h) and features are cached under `~/.cache/clipping-edit/music` (or `CLIP_MUSIC_CACHE`), so a re-run with a new `--clip-s` or mood costs seconds.
- **Show the person the top 3** (title, score, BPM, licence, credit needed?) with the clip table. Use `--pick K` to change the pick.

### Sources (accessed 2026-11-01)
- CC BY 4.0 legal code: https://creativecommons.org/licenses/by/4.0/legalcode.en
- CC BY-ND 4.0: https://creativecommons.org/licenses/by-nd/4.0/legalcode.en
- CC BY-SA 4.0: https://creativecommons.org/licenses/by-sa/4.0/legalcode.en
- CC BY 3.0: https://creativecommons.org/licenses/by/3.0/legalcode
- YouTube Audio Library help: https://support.google.com/youtube/answer/3376882
- Pixabay licence summary: https://pixabay.com/service/license-summary/
- Pixabay terms (last updated 2026-10-20): https://pixabay.com/service/terms/
- NCS usage policy: https://ncs.io/usage-policy
- Incompetech FAQ: https://incompetech.com/music/royalty-free/faq.html
- Free Music Archive licence guide: https://freemusicarchive.org/License_Guide
- Jamendo, "Creative Commons explained": https://support-artist.jamendo.com/creative-commons-explained
- Jamendo API v3 tracks: https://developer.jamendo.com/v3.0/tracks
- Openverse API (OpenAPI schema at /v1/schema/): https://api.openverse.org/v1/
- GEMA, music on social media: https://www.gema.de/help/users/use-music/social-media-websites
