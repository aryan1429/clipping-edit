# Worked example: 7-clip brand campaign in After Effects (ref 09)

`clip_build.py` drives one clip through the path C stages (`prep track topaz overlay ae render audio final qc`),
reading `clips_final.json` (picked + verified candidates). `brief_rules.md` is the rules file every picker / verifier
agent got. The AE side is `skill/scripts/ae/build_clip.jsx` (in this repo); `ae_run.py`-style wrapper runs it in AE with a log marker.

Environment: `CLIP_JOB` (job folder), `CLIP_SKILL_SCRIPTS`, `CLIP_FFMPEG_DIR`, `CLIP_AE_PRESET` (the colour-correction
`.ffx`), `CLIP_DELIVER`, `CLIP_SFX_LIB` (an SFX library index with roles + fingerprints), `TOPAZ_FFMPEG`.
Measured on a 4 GB laptop GPU: Topaz ~25 min / 35-40 s clip, AE ~0.6 s / frame; run them one at a time.
