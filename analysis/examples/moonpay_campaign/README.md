# Worked example: 7-clip brand campaign in After Effects (ref 09)

`clip_build.py` (v2) drives one clip through the path C stages
`prep track topaz stab overlay ae render audio final qc`, reading `clips_final.json` (picked + verified candidates).
`brief_rules.md` is the rules file every picker / verifier agent got.

- **track**: face-tracked crop at the source's native scale (no zoom in the crop).
- **topaz**: Gaia HQ 2x + Apollo to 59.94 for 1080p sources; 4K60 sources are copied through.
- **stab**: `face_track.py --mode steady` on the enhanced footage -> per-frame Position/Scale keys for AE.
- **overlay**: title measurement, head-room drop, caption tokens -> `captions.py` layout.
- **ae**: writes `PLAN` and runs `skill/scripts/ae/build_clip2.jsx` (the whole edit: blurred band, CAM push/punch null,
  stabilised footage, optional wide-shot ZOOM null and freeze-frame holds, the colour-correction preset, per-word
  caption text layers with Deep Glow on keywords, title card).
- **render**: `aerender` Lossless chunks under a RAM watchdog (`ae_prefs.py` pins MFR off + disk cache off before each
  call), one NVENC H.264 High encode per chunk, copy-concat.
- **audio / final / qc**: music bed + one SFX per accent (`mix_audio.py`), `finalize_mux.py`, caption / grade /
  delivery gates, banned-word and tag checks.

`review_pack.py` builds per-clip review packs (3 contact sheets, cover frame, transcript, caption chunks, meta) for the
two-lens adversarial review (visual + copy/brief, each P0/P1 finding re-checked by a skeptic) described in ref 09.

Per-clip knobs in `clips_final.json`: `remove_words`, `caption_fix`, `solo_words`, `brk_after`, `max_words`,
`safe_bottom`, `drop_max`, `max_upscale`, `stab_room`, `freezes` ([{f0, f1, src}]), `zooms` ([{f0, f1, scale, cx, cy}]),
`hard_joins`, `title_highlight`, `post_captions`.

Environment: `CLIP_JOB` (job folder), `CLIP_SKILL_SCRIPTS`, `CLIP_FFMPEG_DIR`, `CLIP_AE_PRESET` (the colour-correction
`.ffx`), `CLIP_DELIVER`, `CLIP_SFX_LIB` (an SFX library index with roles + fingerprints), `TOPAZ_FFMPEG`,
`CLIP_AE_PREFS` (AE prefs file), `CLIP_AE_CHUNK`, `CLIP_AE_MAX_MB`.
Measured on a 4 GB laptop GPU: Topaz Gaia HQ 27-78 min per 25-35 s 1080p clip; AE ~0.17 s / frame with MFR off
(~6-9 min per clip); never run Topaz and AE renders at the same time.
