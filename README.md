# clipping-edit

A [Claude Code](https://claude.com/claude-code) skill that turns a long video (podcast, stream, interview) into short-form clips. Paste a YouTube link and Claude downloads it, transcribes it, picks the best moments and renders each one as a short of 60 s or less. Each short gets face tracking, word-by-word captions and a colour grade.

## Output style

The default look follows viral IShowSpeed-edit Shorts. The full spec is in [`skill/references/01_ishowspeed_clip_style.md`](skill/references/01_ishowspeed_clip_style.md), and it was studied from these Shorts:

- https://youtube.com/shorts/tnE-1xs64ls
- https://youtube.com/shorts/GbkSKbdsxZs
- https://youtube.com/shorts/LCS-pKmkb88

What that means in practice:
- The hook is spoken from frame 0 and the clip ends on the payoff.
- The crop follows the active speaker and resets at each camera cut.
- Captions are Montserrat Black ALL CAPS and build word by word, with 1-3 coloured keywords.
- An accent (flash or whip with SFX) lands about every 6-8 s.
- The grade comes out brighter, more saturated and sharper than the source.

Moment picking (hook types, /10 scoring, candidate table, titles and post captions) follows [`skill/references/02_eddie_claude_clipping_tutorial.md`](skill/references/02_eddie_claude_clipping_tutorial.md).

## Install

1. **Clone the repo:**
   ```sh
   git clone https://github.com/aryan1429/clipping-edit.git
   cd clipping-edit
   ```
2. **Install the skill.** Copy or symlink `skill/` into your Claude Code skills folder.
   - macOS / Linux:
     ```sh
     mkdir -p ~/.claude/skills
     ln -s "$PWD/skill" ~/.claude/skills/clipping-edit      # or: cp -r skill ~/.claude/skills/clipping-edit
     ```
   - Windows (PowerShell):
     ```powershell
     New-Item -ItemType Directory -Force "$env:USERPROFILE\.claude\skills" | Out-Null
     Copy-Item -Recurse skill "$env:USERPROFILE\.claude\skills\clipping-edit"
     # or a junction: cmd /c mklink /J "%USERPROFILE%\.claude\skills\clipping-edit" "%CD%\skill"
     ```
3. **Install the Python dependencies** (Python 3.9+). Use `python3` on macOS/Linux, `python` or `py -3` on Windows; a virtual environment is fine.
   ```sh
   python3 -m pip install -r requirements.txt
   ```
4. **Set up ffmpeg.** Put ffmpeg on `PATH`. If it is not there, the skill uses the binary bundled with `imageio-ffmpeg`.
5. **Get the Montserrat font** (Black weight, `Montserrat-Black.ttf` from the download's `static/` folder) from [Google Fonts](https://fonts.google.com/specimen/Montserrat) and install it, or set the `CLIP_FONT` env var to the `.ttf` path. Without it the skill falls back to Arial Black.
6. **Optional extras:**
   - **EffectCraft:** if it is installed, the skill uses it as the editor. Set `EFFECTCRAFT_CLI` to the CLI path or put `effectcraft-cli` on `PATH`. Without it, the skill renders with ffmpeg + ASS subtitles (libass) + Pillow.
   - **NVIDIA GPU with CUDA:** faster-whisper runs much faster with one. Without a GPU it runs on the CPU (int8).

### Check your setup

```sh
python3 skill/scripts/preflight.py
```

The script reports what it found (Python packages, ffmpeg, the font, EffectCraft and CUDA) and exits 1 if a required piece is missing.

## Usage

Open Claude Code in any folder and type a prompt like one of these:

| Prompt | What happens |
|---|---|
| `clip this: <youtube url>` | Runs the full pipeline. You get the candidate table and the top clips, rendered. |
| `best clip only, 9:16, 30 s: <url>` | Renders only the #1 moment, 1080x1920, at about 30 s. |
| `all clips, no captions: <url>` | Renders every candidate without captions. |
| `study this tutorial: <url>` | Analyses a clipping tutorial or reference Short and adds what it learns to the skill references. |

Each job writes to `output/<title>-<videoId>/`:
- `transcript.json` and `transcript_lines.txt`
- `clips.json`
- `raw/` (reframed only)
- `edited/` (finished clips)
- `captions.md` (title and post caption per clip)

## Defaults

Every default below can be overridden in your prompt. For example: "9:16", "45 s max", "top 5", "end on the freeze meme", "no face tracking", "use ffmpeg not EffectCraft".

| Setting | Default |
|---|---|
| Max clip length | 60 s (asserted ≤ 59.5 s after dead-air removal), target 35-55 s |
| Canvas | 3:4, 1080x1440, 60 fps (9:16 1080x1920 on request) |
| Clips rendered | top 3 that score ≥ 7/10 (always at least #1) |
| Face tracking | on; the crop resets at camera cuts and never pans across one |
| Captions | Montserrat Black ALL CAPS, 2-4 words per chunk, built word by word |
| Grade | must measurably beat the source on brightness, saturation and sharpness |
| Ending | clean hard cut after the payoff; the meme freeze + 💀 is used only when the moment fits |
| Editor | EffectCraft if installed, else ffmpeg + ASS/libass + Pillow |
| Transcription | faster-whisper with word timestamps; CUDA if available, else CPU int8 |
| Music | a mood-matched instrumental bed under the speech: CC0, PD, CC BY or royalty-free only (never NC, ND or SA), found by `skill/scripts/find_music.py` from your music folder, Openverse or Jamendo, with a credit line when the licence needs one |

## Repo layout

```
skill/                 the Claude Code skill (install this folder)
  SKILL.md             pipeline and defaults
  references/          numbered style and workflow studies (01 = clip style, 02 = picking/workflow)
  scripts/preflight.py finds Python packages, ffmpeg, CUDA, EffectCraft and the font
  scripts/cliplib.py   shared helpers for the stage scripts (ffprobe-optional probing, exact decodes, atomic writes)
analysis/              raw study material behind the references (repo only; not needed in the installed skill)
  refs/                per-reference-Short breakdowns
  tutorials/           per-tutorial breakdowns
  repos/               studies of other open-source video tools (HyperFrames)
  tools/extract_ref.py extracts cuts, frame grids, luma/sat/sharpness stats and a transcript from a video
tests/                 synthetic-media tests for the scripts (repo only); fixtures.py builds every test input with ffmpeg + numpy
```

## Status

- Done: the style spec, the moment-picking rules and the end-to-end workflow in `SKILL.md`.
- Done: a study of [HeyGen HyperFrames](https://github.com/heygen-com/hyperframes) (Apache-2.0). It covers frame-exact transcript cuts, click-free splices, ducking from word timings, loudness and true-peak gates, BT.709 tagging, HDR/VFR intake, cut detection, caption timing contracts and review sheets. Raw notes are in `analysis/repos/`; the verified rules are `skill/references/03-05`.
- Done: tested stage scripts in `skill/scripts/` (`probe_source`, `cutlist`, `splice`, `cuts`, `mix_audio`, `finalize_mux`, `grade_gate`, `find_music`). They cover intake, cutting, audio, music, the final mux and the gates; run `python -P tests/test_<name>.py` for each. Still written per job by following the references: reframe, captions and grade rendering.

## Responsible use

Only clip content you have the rights to use. Follow the terms of the platforms you download from and post to, and respect each creator's policies on clipping and reuploads. Credit the source where expected. Never commit downloaded media, cookies or tokens to this repo.

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).
