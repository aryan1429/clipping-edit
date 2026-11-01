# Contributing

Contributions are welcome. You can improve the skill, add a study of a new reference Short or tutorial, or fix a script.

## Adding a study

1. **Get a local copy of the reference video.** Use only content you are allowed to analyse. Keep the copy outside the repo or in an ignored folder.
2. **Extract the analysis material:**
   ```sh
   python3 analysis/tools/extract_ref.py <video.mp4> <outdir>
   ```
   The tool writes metadata, cut times, a 1 fps frame grid, luma/saturation/sharpness stats every 0.5 s, and a word-timestamped transcript.
3. **Write the raw breakdown:**
   - Reference Shorts go in `analysis/refs/refN.md`.
   - Tutorials go in `analysis/tutorials/NN_name.md`.
   - Studies of other open-source tools go in `analysis/repos/<name>.md`. Cite each lesson as `path:lines` in that repo, with the commit you studied. Respect its licence: re-implement ideas, don't paste code.
   - Record timestamps, what is on screen and the exact numbers you measured.
4. **Distil the rules** into `skill/references/NN_short_name.md`, using the next free number.
   - Start with the source link and a one-line scope.
   - Give rules as concrete numbers: sizes, timings, colours and thresholds.
   - When the study conflicts with an existing reference, add a NOT ADOPTED list that says which reference wins and why.
5. **Link the new reference** from `skill/SKILL.md`, in the references list, with a one-line summary of what it covers.

## Rules

- **Never commit media, credentials or job output.** That covers video, audio and frames, cookies (`cookies*.txt`), tokens, `.env` files and `jobs/` or `output/` folders. `.gitignore` covers the common cases, so check `git status` before you commit.
- **Keep the skill portable.**
  - No absolute paths, usernames or machine-specific hardware.
  - Find tools at runtime: Python on `PATH`; ffmpeg on `PATH`, else `imageio_ffmpeg`; EffectCraft via `EFFECTCRAFT_CLI` or `PATH`.
  - Anything Windows-, macOS- or Linux-specific must be marked as such.
- **Write defaults as defaults.** Say what the default is and that a request can override it, as in "3:4 by default, 9:16 on request".
- **Write gotchas generically,** naming the symptom and the fix. For example: "on some installs faster-whisper's PyAV decoder breaks; pass a 16 kHz numpy array decoded by ffmpeg."

## Style

- Keep files concise. Use short bullets, numbers over adjectives, and one idea per line.
- In scripts, put a usage docstring at the top and keep dependencies to `requirements.txt`. Anything optional must degrade gracefully when it is missing.
