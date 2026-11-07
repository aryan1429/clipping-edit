"""caption_gate.py - caption safe-area gate on real pixels: every word drawn, no caption ink outside the safe area
or over a face (ref 07).

Usage:
  python -P caption_gate.py --ass captions.ass [--layout layout.json] [--canvas WxH --fps F --frames N]
                            [--fontsdir DIR] [--faces faces.json] [--all-frames] [--qc DIR] [--out gate.json]
                            [safe-area flags]
  python -P caption_gate.py --video edited.mp4 --clean qc/NN/grade.mp4 [--layout layout.json] [--exclude a-b,...]
  python -P caption_gate.py --video caption_only.mp4 [--bg 808080] [--layout layout.json]
  python -P caption_gate.py --self-test [--workdir DIR] [--keep-temp]

Modes:
  ass    Renders the .ass alone over a #808080 canvas (color source in rgb24, then ass=...:fontsdir=..., run in the
         ASS folder with escaped names, ref 03 section 4 rule 8) and reads ink as max|px - 128| > thr (default 24,
         ref 04 section 1 rule 7: shadow and glow count). Frames: every event's first 4 frames (the entrance and its
         scale), its middle and last frame and each layout word's full frame, by default; --all-frames renders every
         frame (the gate warns when an event animates scale or position beyond a simple entrance). Also checks the
         header (PlayResX/Y must equal the canvas; WrapStyle 2 and ScaledBorderAndShadow yes are expected) and the
         font: every libass `fontselect: (<family>, ...) -> <font>` line must name the requested face (a missing or
         misspelt font falls back to a wider one; "Montserrat" picks the Regular weight), and with --layout it must
         be the layout's PostScript name.
  diff   --video + --clean: the delivered edit against its caption-free render (qc/NN/grade.mp4, same frames).
         Glyph ink = max|edit - clean| > --diff-thr (default 100: where the fill or the black stroke sits, one of
         them differs that much from any footage pixel), minus 8-connected blobs smaller than --min-blob px
         (default 24 px at a 1080 px short side, scaled by area: two encodes' grain). Halos are not judged here
         (over footage they read differently from the #808080 model, and the edit's encode moves footage pixels up
         to ~36 px around the captions); ass and plate modes measure them. Accents are not in the clean render:
         pass their frame spans with --exclude (stickers are checked like captions).
  plate  --video alone: a caption-only render (EffectCraft text layers over a flat --bg, default #808080).
         Ink = max|px - bg| > thr.
  Video modes read every frame by default (a render is opaque: a keyword pop between sampled frames would pass);
  --sample reads only the layout's sampled frames (warned). Video frames are decoded with the BT.709 tv matrix
  named (ref 04 section 3 rule 3).

Gate (exit 1 on any P0):
  outside_safe   ink outside the safe area (captions.py's rules: 9:16 UI band y 168-1330 of 1920 scaled to H plus
                 6 % / 12 % side margins; 3:4, 1:1, 16:9 title-safe margins; or the layout's own "safe" block, or
                 --profile/--margins/--safe, which apply in every mode once the canvas is known).
  edge_clipped   ink in the outer --edge px (default 2) of the frame: the glyphs are cut off by the frame edge.
  missing_word   (with --layout) a word's ink box holds less than 12 % strong ink (max|px - bg| > 64 on a flat
                 background, the diff mode glyph ink) on a frame where the layout shows it fully drawn: the word is
                 off-screen, moved or missing (ink drawn somewhere else is no proof that every word is drawn).
  off_frame, event_no_ink   (ass mode without --layout) an event's \\pos lies outside the canvas, or no strong ink
                 lies within 0.7 x its font size of its \\pos on any of its settled frames.
  face_cover     caption ink inside a face's eyes-to-chin region: the layout's per-chunk face regions, or --faces
                 per frame (ref 04 section 1 rule 7: 0 frames over a face).
  length_mismatch, decode_short   (video modes) the video has another frame count than the layout, or decoded fewer
                 frames than asked: captions in the missing frames were never checked.
  no_ink, playres_mismatch, font_fallback, font_not_layout (ass mode).
  model_drift    (warning; ass and plate modes) measured ink outside the layout JSON's predicted boxes by > 2 px:
                 the layout an EffectCraft builder reads would be wrong.
  Every finding names the frames and the event/word (event Name "c<chunk>w<word>" from captions.py, else the
  nearest \\pos), and the worst frames go to <qc>/caption_gate_sheet.png (safe area green, ink outside it blue).

Output (stdout; also --out and <qc>/caption_gate.json):
  {"ok", "version", "mode", "canvas", "fps", "frames_checked", "safe", "thr", "ink_bbox", "min_margin_px":
   {"left", "top", "right", "bottom"}, "font", "header", "model", "presence", "noise", "findings": [{"id", "rank",
   "frames", "words", "measured", "fix"}], "sheet", "warnings"}
Exit codes: 0 pass; 1 a P0 (or a self-test failed); 2 usage error, unreadable input or a render/decode tool failure.
"""
import argparse
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cliplib as cl  # noqa: E402
import captions as cap  # noqa: E402

SCRIPT_VERSION = "1.1.0"
DRIFT_TOL = 2.0
SHEET_TILES = 6
CORE_THR = 64        # strong ink on a flat bg: fill or stroke (shadow halos of neighbours stay below ~30)
CORE_DIFF = 100      # diff mode glyph ink: the fill or the black stroke differs > 100 from any footage pixel
MIN_COVER = 0.12     # a drawn word covers >= MIN_COVER of its box_ink with strong ink (measured minima in ref 07)
GEO_TAGS = r"\\(?:fscx|fscy|fsc|frz|frx|fry|fr|fax|fay|org|pos|fs\d|move)"


# ---------------------------------------------------------------- ASS parsing

def _ass_secs(s):
    h, m, sec = s.strip().split(":")
    return int(h) * 3600 + int(m) * 60 + float(sec)


def _animated(text):
    """True when the event moves or rescales beyond captions.py's entrance (<= 2 geometry \\t, no \\move)."""
    if re.search(r"\\move\s*\(", text):
        return True
    geo = [m for m in re.finditer(r"\\t\(([^()]*(?:\([^()]*\)[^()]*)*)\)", text) if re.search(GEO_TAGS, m.group(1))]
    return len(geo) > 2


def parse_ass(path):
    """{"info": {key: value}, "styles": {name: {field: value}}, "events": [{layer, start, end, style, name, text,
    pos, fs}]}."""
    try:
        text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    except OSError as e:
        raise cl.ClipError("input_missing", f"cannot read {path}: {e}", exit_code=2)
    info, styles, events = {}, {}, []
    section, fmt = None, None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(";"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section, fmt = line.lower(), None
            continue
        key, _, val = line.partition(":")
        key, val = key.strip(), val.strip()
        if section == "[script info]":
            info[key] = val
        elif section in ("[v4+ styles]", "[v4 styles]"):
            if key == "Format":
                fmt = [f.strip() for f in val.split(",")]
            elif key == "Style" and fmt:
                parts = [p.strip() for p in val.split(",", len(fmt) - 1)]
                d = dict(zip(fmt, parts))
                styles[d.get("Name", "")] = d
        elif section == "[events]":
            if key == "Format":
                fmt = [f.strip() for f in val.split(",")]
            elif key == "Dialogue" and fmt:
                parts = val.split(",", len(fmt) - 1)
                d = dict(zip(fmt, parts))
                t = d.get("Text", "")
                m = re.search(r"\\pos\(\s*(-?[0-9.]+)\s*,\s*(-?[0-9.]+)\s*\)", t)
                fsm = re.search(r"\\fs([0-9.]+)", t)
                try:
                    st = styles.get(d.get("Style", "").strip(), {})
                    fs = float(fsm.group(1)) if fsm else float(st.get("Fontsize", 0) or 0)
                    events.append({"layer": int(d.get("Layer", 0) or 0), "start": _ass_secs(d["Start"]),
                                   "end": _ass_secs(d["End"]), "style": d.get("Style", "").strip(),
                                   "name": d.get("Name", "").strip(), "text": t,
                                   "plain": re.sub(r"\{[^}]*\}", "", t),
                                   "pos": (float(m.group(1)), float(m.group(2))) if m else None, "fs": fs,
                                   "animated": _animated(t)})
                except (KeyError, ValueError):
                    raise cl.ClipError("bad_ass", f"unreadable Dialogue line: {raw[:120]}", exit_code=2)
    if not events:
        raise cl.ClipError("bad_ass", f"{path}: no Dialogue events", exit_code=2)
    return {"info": info, "styles": styles, "events": events}


def time_ms(k, fps):
    """The ms time ffmpeg's ass filter renders frame k at: (long long)(pts * av_q2d(time_base) * 1000), truncated,
    with the color source's time base 1/fps (double arithmetic, so an exact centisecond can land 1 ms low)."""
    f = Fraction(fps)
    return math.trunc(k * (f.denominator / f.numerator) * 1000)


def event_frames(ev, fps, n):
    """[first, last] frames on which the event is drawn (start_ms <= t_ms < end_ms), or None."""
    s_ms, e_ms = round(ev["start"] * 1000), round(ev["end"] * 1000)
    f = float(Fraction(fps))
    a = max(0, int(math.floor(s_ms / 1000 * f)) - 1)
    while a < n and time_ms(a, fps) < s_ms:
        a += 1
    b = min(n - 1, int(math.ceil(e_ms / 1000 * f)) + 1)
    while b >= a and time_ms(b, fps) >= e_ms:
        b -= 1
    return (a, b) if b >= a else None


def sample_frames(spans, n, all_frames=False, extra=()):
    if all_frames:
        return list(range(n))
    out = set(extra)
    for a, b in spans:
        out.update(range(a, min(b, a + 3) + 1))
        out.add((a + b) // 2)
        out.add(b)
    return sorted(f for f in out if 0 <= f < n)


# ---------------------------------------------------------------- rendering / decoding

def fesc(p):
    """A path as a filter option value, escaped for both filtergraph levels (captions.filter_escape)."""
    return cap.filter_escape(p)


def _select(frames):
    return "select='" + "+".join(f"eq(n\\,{k})" for k in frames) + "'"


class FramePipe:
    """Iterate (frame index, uint8 (h, w, 3)) for a sorted frame list from an rgb24 pipe; .err/.got/.rc after."""

    def __init__(self, cmd, w, h, frames, cwd=None):
        self.cmd, self.w, self.h, self.frames, self.cwd = [str(c) for c in cmd], w, h, frames, cwd
        self.err, self.got, self.rc = "", 0, None

    def __iter__(self):
        import threading
        import numpy as np
        size = self.w * self.h * 3
        p = subprocess.Popen(self.cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                             cwd=self.cwd)
        chunks = []
        t = threading.Thread(target=lambda: chunks.append(p.stderr.read()), daemon=True)
        t.start()
        try:
            for k in self.frames:
                buf = p.stdout.read(size)
                if len(buf) < size:
                    break
                self.got += 1
                yield k, np.frombuffer(buf, np.uint8).reshape(self.h, self.w, 3)
        finally:
            p.stdout.close()
            p.wait()
            t.join(timeout=10)
            self.rc = p.returncode
            self.err = (chunks[0] if chunks else b"").decode("utf-8", "replace")


def _rel_or_abs(p, cwd):
    p = Path(p).resolve()
    try:
        return p.relative_to(Path(cwd).resolve()).as_posix() or "."
    except ValueError:
        return p.as_posix()


def render_ass_cmd(ffmpeg, ass_path, fontsdir, w, h, fps, n, frames, workdir):
    """(cmd, cwd): the graph runs in the ASS folder with the bare ASS name, every value escaped (ref 03 section 4
    rule 8; an apostrophe or a drive colon in a path broke a single-quoted value)."""
    ass_path = Path(ass_path).resolve()
    cwd = ass_path.parent
    graph = (f"color=c=0x808080:s={w}x{h}:r={cl.frac_str(fps)}:d={cl.t6((Fraction(n) - Fraction(1, 2)) / fps)},"
             f"format=rgb24,{_select(frames)},ass=filename={fesc(ass_path.name)}"
             + (f":fontsdir={fesc(_rel_or_abs(fontsdir, cwd))}" if fontsdir else "") + "[out]")
    script = Path(workdir) / "caption_gate_graph.txt"
    script.write_text(graph, encoding="utf-8")
    return [ffmpeg, "-hide_banner", "-nostdin", "-v", "info", "-filter_complex_script", str(script), "-map", "[out]",
            "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], str(cwd)


def decode_cmd(ffmpeg, video, w, h, frames, workdir, tag, all_frames=False):
    sel = "" if all_frames else f"{_select(frames)},"
    graph = f"[0:v:0]{sel}scale={w}:{h}:in_color_matrix=bt709:in_range=tv:flags=bicubic,format=rgb24[out]"
    script = Path(workdir) / f"caption_gate_{tag}.txt"
    script.write_text(graph, encoding="utf-8")
    return [ffmpeg, "-hide_banner", "-nostdin", "-v", "error", "-i", str(Path(video).resolve()),
            "-filter_complex_script", str(script), "-map", "[out]", "-fps_mode", "passthrough", "-f", "rawvideo",
            "-pix_fmt", "rgb24", "-"]


# ---------------------------------------------------------------- measuring

_FLAT = {}


def _absdiff(frame, ref):
    """max over RGB of |frame - ref| as uint8 (ref: a grey int, an RGB tuple or a frame). Exact uint8 arithmetic
    (max - min), channel max by slices: ~10x faster than an int16 copy and .max(axis=2) on 1080x1920."""
    import numpy as np
    if not hasattr(ref, "shape"):
        rgb = (int(ref),) * 3 if isinstance(ref, (int, float)) else tuple(int(v) for v in ref)
        key = (frame.shape, rgb)
        if key not in _FLAT:
            _FLAT.clear()
            _FLAT[key] = np.empty(frame.shape, np.uint8)
            _FLAT[key][...] = np.array(rgb, np.uint8)
        ref = _FLAT[key]
    try:
        import cv2
        d = cv2.absdiff(frame, ref)
    except ImportError:
        d = np.maximum(frame, ref)
        d -= np.minimum(frame, ref)
    return np.maximum(np.maximum(d[..., 0], d[..., 1]), d[..., 2])


def ink_mask(frame, ref, thr, opening=False):
    m = _absdiff(frame, ref) > thr
    if opening:
        m = _dilate(_erode(m))
    return m


def _erode(m):
    o = m.copy()
    o[1:, :] &= m[:-1, :]
    o[:-1, :] &= m[1:, :]
    o[:, 1:] &= m[:, :-1]
    o[:, :-1] &= m[:, 1:]
    o[0, :] = o[-1, :] = False
    o[:, 0] = o[:, -1] = False
    return o


def _dilate(m):
    o = m.copy()
    o[1:, :] |= m[:-1, :]
    o[:-1, :] |= m[1:, :]
    o[:, 1:] |= m[:, :-1]
    o[:, :-1] |= m[:, 1:]
    return o


def drop_small_blobs(mask, min_px, stats):
    """mask minus 8-connected components smaller than min_px (codec grain survives a 3x3 opening as 5-13 px
    plus-shaped blobs; the smallest caption glyph, a period at 3.3 % H cap, is hundreds of px)."""
    if min_px <= 1 or not mask.any():
        return mask
    try:
        import cv2
    except ImportError:
        raise cl.ClipError("missing_dependency", "diff mode needs cv2 (opencv-python) for the blob filter",
                           exit_code=2)
    import numpy as np
    n, lab, st, _ = cv2.connectedComponentsWithStats(mask.view(np.uint8), connectivity=8)
    areas = st[1:, cv2.CC_STAT_AREA]
    small = np.nonzero(areas < min_px)[0] + 1
    if len(small) == 0:
        return mask
    keep = np.ones(n, bool)
    keep[small] = False
    keep[0] = False
    stats["blobs_dropped"] += len(small)
    stats["px_dropped"] += int(areas[small - 1].sum())
    stats["max_blob_dropped_px"] = max(stats["max_blob_dropped_px"], int(areas[small - 1].max()))
    return keep[lab]


def measure_frame(mask, safe, edge):
    """{bbox, outside_px, outside_bbox, edge_px, margins} for one ink mask (None when it holds no ink)."""
    import numpy as np
    ys = np.nonzero(mask.any(axis=1))[0]
    if len(ys) == 0:
        return None
    xs = np.nonzero(mask.any(axis=0))[0]
    bbox = (int(xs[0]), int(ys[0]), int(xs[-1]) + 1, int(ys[-1]) + 1)
    sx0, sy0 = int(math.ceil(safe["x0"] - 1e-9)), int(math.ceil(safe["y0"] - 1e-9))
    sx1, sy1 = int(math.floor(safe["x1"] + 1e-9)), int(math.floor(safe["y1"] + 1e-9))
    inside = int(mask[sy0:sy1, sx0:sx1].sum())
    total = int(mask.sum())
    out_px = total - inside
    out_bbox = None
    if out_px:
        o = mask.copy()
        o[sy0:sy1, sx0:sx1] = False
        oy = np.nonzero(o.any(axis=1))[0]
        ox = np.nonzero(o.any(axis=0))[0]
        out_bbox = (int(ox[0]), int(oy[0]), int(ox[-1]) + 1, int(oy[-1]) + 1)
    e = max(0, int(edge))
    edge_px = 0
    if e:
        edge_px = int(mask[:e, :].sum() + mask[-e:, :].sum() + mask[e:-e, :e].sum() + mask[e:-e, -e:].sum())
    return {"bbox": bbox, "outside_px": out_px, "outside_bbox": out_bbox, "edge_px": edge_px,
            "margins": {"left": bbox[0] - safe["x0"], "top": bbox[1] - safe["y0"], "right": safe["x1"] - bbox[2],
                        "bottom": safe["y1"] - bbox[3]}}


def _clip_box(b, w, h):
    x0, y0 = max(0, int(math.floor(b[0]))), max(0, int(math.floor(b[1])))
    x1, y1 = min(w, int(math.ceil(b[2]))), min(h, int(math.ceil(b[3])))
    return (x0, y0, x1, y1) if x1 > x0 and y1 > y0 else None


# ---------------------------------------------------------------- gate core

def masked(pipe, ref, thr):
    """(k, frame, ink mask, strong-ink mask) against a flat colour (an int grey or an RGB tuple)."""
    for k, fr in pipe:
        d = _absdiff(fr, ref)
        yield k, fr, d > thr, d > CORE_THR


def diffed(pipe_v, pipe_c, thr, min_blob, noise):
    """(k, edit frame, ink mask, strong-ink mask): glyph ink = max|edit - clean| > thr (default 100: the fill or the
    black stroke differs that much from any footage pixel) minus blobs under min_blob px; the same mask serves as the
    strong mask. Weaker differences are not judged here: a shadow halo over footage reads differently from the
    #808080 model (ass and plate modes measure halos), and the edit's encode changes footage pixels up to ~36 px
    around the captions (ringing, macroblock decisions; brightenings a shadow cannot make)."""
    for (k, fv), (_, fc) in zip(pipe_v, pipe_c):
        m = drop_small_blobs(_absdiff(fv, fc) > thr, min_blob, noise)
        yield k, fv, m, m


class Expect:
    """What the gate expects per frame: layout words (spans, full frames, boxes, chunk face regions), ASS events
    without a layout (anchors), and per-frame face regions from --faces."""

    def __init__(self, layout=None, events=None, spans=None, faces=None, face_style=None):
        self.layout = layout
        self.words = {}
        self.chunk_faces = {}
        if layout:
            for c in layout["chunks"]:
                self.chunk_faces[c["i"]] = [tuple(r) for r in c.get("faces") or []]
                for wd in c["words"]:
                    self.words[f"c{c['i']}w{wd['i']}"] = (c["i"], wd)
        self.events = events or {}          # name -> [ASS events]
        self.spans = spans or []            # [(name, a, b)]
        self.track = faces or []
        self.face_style = face_style or cap.DEFAULTS

    def active(self, k):
        return [n for n, a, b in self.spans if a <= k <= b]

    def full_frames(self):
        return [min(wd.get("full_f", wd["appear_f"] + 2), wd["end_f"] - 1) for _, wd in self.words.values()]

    def faces_at(self, k):
        if self.track:
            return cap.face_regions(self.face_style, cap.faces_in(self.track, k, k + 1))
        out = []
        for ci in {self.words[n][0] for n in self.active(k) if n in self.words}:
            out.extend(self.chunk_faces.get(ci, []))
        return out


def run_gate(tuples, safe, edge, thr_label, exp, qc=None, fps=None, check_drift=True):
    """Measure every (k, frame, mask, strong mask); returns (result dict, P0 findings, model drift list)."""
    worst = []  # (score, k, frame copy, mask, mask info)
    per_frame = {}
    union = None
    mins = {"left": math.inf, "top": math.inf, "right": math.inf, "bottom": math.inf}
    drift, checked = [], 0
    layout = exp.layout
    miss = {}        # word name -> [frames with coverage < MIN_COVER]
    cover = {}       # word name -> min coverage on its full frames
    ev_seen = {}     # (name, pos) -> strong ink found near the anchor on a settled frame
    face_hits = {}   # k -> px of ink inside face regions
    h = w = None
    for k, fr, mask, core in tuples:
        checked += 1
        h, w = mask.shape
        names = exp.active(k)
        if layout:  # every word the layout shows fully drawn on k must have its ink in its box
            for n in names:
                if n not in exp.words:
                    continue
                _, wd = exp.words[n]
                last = wd["end_f"] - 1
                full = min(wd.get("full_f", wd["appear_f"] + 2), last)
                if not full <= k <= last:
                    continue
                bx = wd["box_ink"]
                area = max(1.0, (bx[2] - bx[0]) * (bx[3] - bx[1]))
                cb = _clip_box(bx, w, h)
                cov = 0.0 if cb is None else float(core[cb[1]:cb[3], cb[0]:cb[2]].sum()) / area
                cover[n] = min(cover.get(n, math.inf), cov)
                if cov < MIN_COVER:
                    miss.setdefault(n, []).append(k)
        elif exp.events:  # no layout: strong ink near each settled event's anchor
            for n in names:
                for ev in exp.events.get(n, []):
                    if not ev["pos"] or not (0 <= ev["pos"][0] < w and 0 <= ev["pos"][1] < h):
                        continue
                    a, b = ev["_span"]
                    if k < min(a + 3, b):
                        continue
                    r = 0.7 * (ev["fs"] or 0.05 * h)
                    cb = _clip_box((ev["pos"][0] - r, ev["pos"][1] - r, ev["pos"][0] + r, ev["pos"][1] + r), w, h)
                    key = (n, ev["pos"])
                    ev_seen[key] = ev_seen.get(key, False) or bool(cb and core[cb[1]:cb[3], cb[0]:cb[2]].any())
        regions = exp.faces_at(k)
        if regions:
            px = 0
            for r in regions:
                cb = _clip_box(r, w, h)
                if cb:
                    px += int(mask[cb[1]:cb[3], cb[0]:cb[2]].sum())
            if px:
                face_hits[k] = (px, regions)
        m = measure_frame(mask, safe, edge)
        if m is None:
            continue
        b = m["bbox"]
        union = b if union is None else (min(union[0], b[0]), min(union[1], b[1]), max(union[2], b[2]),
                                         max(union[3], b[3]))
        for s in mins:
            mins[s] = min(mins[s], m["margins"][s])
        per_frame[k] = m
        if layout and check_drift:
            boxes = [exp.words[n][1]["box"] for n in names if n in exp.words]
            if boxes:
                pb = (min(x[0] for x in boxes), min(x[1] for x in boxes), max(x[2] for x in boxes),
                      max(x[3] for x in boxes))
                dv = max(pb[0] - b[0], pb[1] - b[1], b[2] - pb[2], b[3] - pb[3])
                if dv > DRIFT_TOL:
                    drift.append((k, round(dv, 1), b, [round(v, 1) for v in pb]))
        score = m["outside_px"] * 1000 + m["edge_px"] * 1000 + face_hits.get(k, (0,))[0] * 1000 \
            - min(m["margins"].values())
        if qc and (len(worst) < SHEET_TILES or score > worst[-1][0]):
            worst.append((score, k, fr.copy(), mask.copy(), m))
            worst.sort(key=lambda x: -x[0])
            del worst[SHEET_TILES:]
    findings = []

    def group(ids):
        """Contiguous runs of offending frames -> [(first, last)]."""
        runs = []
        for kk in sorted(ids):
            if runs and kk - runs[-1][1] <= 6:
                runs[-1][1] = kk
            else:
                runs.append([kk, kk])
        return runs

    for fid, key, fix in (("outside_safe", "outside_px",
                           "re-run captions.py (it fits and clamps every word) or fix the editor's positions; never "
                           "hand-place caption text"),
                          ("edge_clipped", "edge_px",
                           "glyphs run off the frame: a word wider than the frame, a 9:16 position on another canvas, "
                           "or PlayRes != video size")):
        bad = [kk for kk, mm in per_frame.items() if mm[key]]
        for a, b in group(bad):
            ks = [kk for kk in bad if a <= kk <= b]
            kw = max(ks, key=lambda kk: per_frame[kk][key])
            mm = per_frame[kw]
            region = mm["outside_bbox"] if fid == "outside_safe" else mm["bbox"]
            words = _attribute(exp.active(kw), region, exp)
            findings.append({"id": fid, "rank": "P0", "frames": [a, b], "worst_frame": kw,
                             "measured": {"px": mm[key], "ink_bbox": mm["bbox"], "outside_bbox": mm["outside_bbox"],
                                          "margins": {s: round(v, 1) for s, v in mm["margins"].items()}},
                             "words": words, "fix": fix})
    for n, ks in sorted(miss.items()):
        ci, wd = exp.words[n]
        for a, b in group(ks):
            findings.append({"id": "missing_word", "rank": "P0", "frames": [a, b], "worst_frame": a,
                             "measured": f"{wd['text']!r} covers {cover[n]:.2f} of its ink box {wd['box_ink']} with "
                                         f"strong ink (< {MIN_COVER}) on {len([x for x in ks if a <= x <= b])} "
                                         "checked frame(s) where the layout shows it fully drawn",
                             "words": [{"name": n, "text": wd["text"], "token": wd["token"], "box": wd["box_ink"]}],
                             "fix": "the word is off-screen, moved or missing: burn the ASS captions.py wrote (or "
                                    "place the editor's layer at the layout's anchor) and check the font and PlayRes"})
    if exp.events and not layout and w:
        for n, evs in sorted(exp.events.items()):
            for ev in evs:
                if ev["pos"] and not (0 <= ev["pos"][0] < w and 0 <= ev["pos"][1] < h):
                    findings.append({"id": "off_frame", "rank": "P0", "frames": list(ev["_span"]), "words": [
                        {"name": n, "text": ev["plain"][:60], "pos": ev["pos"]}],
                        "measured": f"\\pos{ev['pos']} lies outside the {w}x{h} canvas",
                        "fix": "the event is drawn off-screen: re-run captions.py, or fix the \\pos"})
                elif ev["pos"] and ev_seen.get((n, ev["pos"])) is False:
                    findings.append({"id": "event_no_ink", "rank": "P0", "frames": list(ev["_span"]), "words": [
                        {"name": n, "text": ev["plain"][:60], "pos": ev["pos"]}],
                        "measured": f"no strong ink within {0.7 * (ev['fs'] or 0.05 * h):.0f} px of \\pos{ev['pos']}",
                        "fix": "the event draws nothing near its anchor: check its text, alpha, font and PlayRes"})
    if face_hits:
        for a, b in group(face_hits):
            ks = [kk for kk in face_hits if a <= kk <= b]
            kw = max(ks, key=lambda kk: face_hits[kk][0])
            findings.append({"id": "face_cover", "rank": "P0", "frames": [a, b], "worst_frame": kw,
                             "measured": {"px": face_hits[kw][0],
                                          "regions": [[round(v, 1) for v in r] for r in face_hits[kw][1]]},
                             "words": _attribute(exp.active(kw), _union(face_hits[kw][1]), exp),
                             "fix": "caption ink sits on a face's eyes-to-chin region: re-run captions.py with the "
                                    "face track (--faces), never --allow-face-cover for delivery"})
    model = None
    if layout and check_drift:
        model = {"checked": checked, "drift_frames": len(drift), "max_drift_px": max([d[1] for d in drift], default=0),
                 "examples": [{"frame": d[0], "drift_px": d[1], "ink": d[2], "predicted": d[3]} for d in drift[:5]]}
    presence = None
    if layout:
        lo = min(cover.items(), key=lambda x: x[1]) if cover else None
        presence = {"words_checked": len(cover), "words_expected": len(exp.words), "min_cover": MIN_COVER,
                    "lowest": None if lo is None else {"word": lo[0], "text": exp.words[lo[0]][1]["text"],
                                                       "cover": round(lo[1], 3)},
                    "missing": sorted(miss)}
    sheet = None
    if qc and worst:
        sheet = contact_sheet(worst, safe, Path(qc) / "caption_gate_sheet.png", fps, thr_label)
    res = {"frames_checked": checked, "frames_with_ink": len(per_frame), "ink_bbox": union,
           "min_margin_px": {s: (None if v == math.inf else round(v, 1)) for s, v in mins.items()},
           "model": model, "presence": presence, "sheet": sheet}
    return res, findings, drift


def _union(boxes):
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def _attribute(names, region, exp):
    out = []
    if region is None:
        return out
    cx, cy = (region[0] + region[2]) / 2, (region[1] + region[3]) / 2
    if exp.layout:
        for n in names:
            if n in exp.words:
                b = exp.words[n][1]["box"]
                if b[0] < region[2] + 2 and region[0] < b[2] + 2 and b[1] < region[3] + 2 and region[1] < b[3] + 2:
                    if not any(o["name"] == n for o in out):
                        out.append({"name": n, "text": exp.words[n][1]["text"], "token": exp.words[n][1]["token"],
                                    "box": b})
    if not out:
        best = None
        for n in names:
            for ev in exp.events.get(n, []):
                if ev["pos"]:
                    d = math.hypot(ev["pos"][0] - cx, ev["pos"][1] - cy)
                    if best is None or d < best[0]:
                        best = (d, n, ev)
        if best:
            out.append({"name": best[1], "text": best[2]["plain"][:60], "pos": best[2]["pos"]})
    return out


def contact_sheet(worst, safe, path, fps, label):
    from PIL import Image, ImageDraw
    import numpy as np
    tiles = []
    for score, k, fr, mask, m in sorted(worst, key=lambda x: x[1]):
        img = fr.copy()
        out = mask.copy()
        sx0, sy0 = int(math.ceil(safe["x0"])), int(math.ceil(safe["y0"]))
        sx1, sy1 = int(math.floor(safe["x1"])), int(math.floor(safe["y1"]))
        out[sy0:sy1, sx0:sx1] = False
        img[out] = np.array([0, 90, 255], np.uint8)  # blue: no caption palette colour
        im = Image.fromarray(img)
        d = ImageDraw.Draw(im)
        lw = max(2, im.width // 300)
        d.rectangle([safe["x0"], safe["y0"], safe["x1"] - 1, safe["y1"] - 1], outline=(0, 230, 0), width=lw)
        bb = m["bbox"]
        d.rectangle([bb[0], bb[1], bb[2] - 1, bb[3] - 1], outline=(255, 230, 0), width=max(1, lw // 2))
        scale = 360 / im.width if im.width <= im.height else 480 / im.width
        im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))), Image.BILINEAR)
        d = ImageDraw.Draw(im)
        t = f"f{k}" + (f" {k / float(Fraction(fps)):.2f}s" if fps else "")
        t += f" out {m['outside_px']}px" if m["outside_px"] else f" min margin {min(m['margins'].values()):.0f}px"
        d.rectangle([0, 0, im.width, 18], fill=(0, 0, 0))
        d.text((4, 3), t, fill=(255, 255, 255))
        tiles.append(im)
    cols = min(3, len(tiles))
    rows = math.ceil(len(tiles) / cols)
    tw, th = max(t.width for t in tiles), max(t.height for t in tiles)
    sheet = Image.new("RGB", (cols * tw + (cols - 1) * 6, rows * th + (rows - 1) * 6 + 22), (24, 24, 24))
    ImageDraw.Draw(sheet).text((4, 5), f"caption_gate: green = safe area, blue = ink outside it, yellow = ink bbox "
                               f"({label})", fill=(255, 255, 255))
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % cols) * (tw + 6), 22 + (i // cols) * (th + 6)))
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = cl.tmp_path(path)
    sheet.save(tmp)
    cl.replace_with_retry(tmp, path)
    return str(path)


# ---------------------------------------------------------------- modes

def font_check(stderr, layout):
    """[findings], [{"requested", "selected"}] from libass fontselect lines."""
    sel = re.findall(r"fontselect: \((.*?), (\d+), (\d+)\) -> ([^,\r\n]*), (\d+), ([^\r\n]*)", stderr)
    findings, seen = [], []
    norm = lambda v: re.sub(r"[^a-z0-9]", "", v.lower())  # noqa: E731
    for fam, wt, it, ps, idx, name in sel:
        fam, ps = fam.strip(), ps.strip()
        seen.append({"requested": fam, "selected": ps})
        if layout:
            want = layout["font"].get("postscript")
            if want and ps != want:
                findings.append({"id": "font_not_layout", "rank": "P0", "frames": None, "words": [],
                                 "measured": f"libass drew {fam!r} with {ps!r}; the layout measured {want!r}",
                                 "fix": "burn with the layout's burn.filter (cwd burn.cwd) and its Fontname"})
            elif not want and not norm(ps).startswith(norm(fam)[:6]):
                findings.append({"id": "font_fallback", "rank": "P0", "frames": None, "words": [],
                                 "measured": f"libass fell back: {fam!r} -> {ps!r}",
                                 "fix": "fix the ASS Fontname or --fontsdir"})
        elif norm(ps) != norm(fam):
            # the face must be the requested family itself ("Montserrat Black" -> Montserrat-Black): a fallback
            # (ArialMT) or another weight of a prefix family ("Montserrat" -> Montserrat-Regular) both fail
            findings.append({"id": "font_fallback", "rank": "P0", "frames": None, "words": [],
                             "measured": f"libass drew {fam!r} with {ps!r} (a fallback or another weight)",
                             "fix": "use the font's legacy family as Fontname (captions.py writes it) with --fontsdir "
                                    "holding the file, or gate with --layout to compare against the measured font"})
    if not sel:
        findings.append({"id": "font_unverified", "rank": "info", "frames": None, "words": [],
                         "measured": "no fontselect line in the ffmpeg log", "fix": None})
    return findings, seen


def _safe_for(args, w, h, layout):
    if args.safe or args.margins or args.profile != "auto":
        return cap.safe_from_args(args, w, h)
    return (layout or {}).get("safe") or cap.safe_area(w, h)


def _faces_for(args, layout, fps, w, h, warnings):
    if not args.faces:
        return []
    return cap.load_faces(cl.read_json(args.faces), fps, (w, h), warnings)


def gate_ass(args, ffmpeg, layout):
    ass = parse_ass(args.ass)
    info = ass["info"]
    warnings, findings = [], []
    try:
        prx, pry = int(info.get("PlayResX", 0)), int(info.get("PlayResY", 0))
    except ValueError:
        prx = pry = 0
    if args.canvas:
        w, h = cap.parse_canvas(args.canvas)
    elif layout:
        w, h = layout["canvas"]["w"], layout["canvas"]["h"]
    elif prx and pry:
        w, h = prx, pry
        warnings.append("no --canvas or --layout: the canvas is taken from PlayResX/Y, so a PlayRes that differs from "
                        "the video size cannot be caught")
    else:
        raise cl.ClipError("usage", "pass --canvas WxH (the ASS has no PlayResX/Y)", exit_code=2)
    if (prx, pry) != (w, h):
        findings.append({"id": "playres_mismatch", "rank": "P0", "frames": None, "words": [],
                         "measured": f"PlayResX/Y {prx}x{pry} vs canvas {w}x{h}" + (" (missing: libass uses 384x288)"
                                                                                   if not prx else ""),
                         "fix": "PlayResX/Y must equal the video size, else libass rescales every \\pos and size"})
    header = {"PlayResX": prx, "PlayResY": pry, "WrapStyle": info.get("WrapStyle"),
              "ScaledBorderAndShadow": info.get("ScaledBorderAndShadow")}
    if str(info.get("WrapStyle", "")).strip() != "2":
        warnings.append(f"WrapStyle {info.get('WrapStyle')!r}: libass may re-wrap a long event onto more lines")
    if str(info.get("ScaledBorderAndShadow", "")).strip().lower() != "yes":
        warnings.append("ScaledBorderAndShadow is not yes: stroke and shadow ignore PlayRes scaling")
    fps = cl.parse_rate(args.fps or (layout or {}).get("fps"))
    if not fps:
        raise cl.ClipError("usage", "pass --fps (or --layout)", exit_code=2)
    n = args.frames or (layout or {}).get("frames")
    if not n:
        n = int(math.ceil(max(e["end"] for e in ass["events"]) * float(fps))) + 1
    safe = _safe_for(args, w, h, layout)
    spans, events = [], {}
    for i, ev in enumerate(ass["events"]):
        name = ev["name"] or f"e{i}"
        fr = event_frames(ev, fps, n)
        if fr:
            ev["_span"] = fr
            spans.append((name, fr[0], fr[1]))
            events.setdefault(name, []).append(ev)
        elif ev["pos"] is not None:
            ev["_span"] = (None, None)
    if any(ev["animated"] for ev in ass["events"]) and not args.all_frames:
        warnings.append("the ASS moves or rescales events beyond a simple entrance (\\move or several geometry \\t): "
                        "use --all-frames")
    exp = Expect(layout, events, spans, _faces_for(args, layout, fps, w, h, warnings),
                 (layout or {}).get("style"))
    frames = sample_frames([(a, b) for _, a, b in spans], n, args.all_frames, exp.full_frames())
    fontsdir = args.fontsdir or (layout or {}).get("font", {}).get("fontsdir")
    work = Path(tempfile.mkdtemp(prefix="caption-gate-"))
    try:
        cmd, cwd = render_ass_cmd(ffmpeg, args.ass, fontsdir, w, h, fps, n, frames, work)
        pipe = FramePipe(cmd, w, h, frames, cwd=cwd)
        res, f2, drift = run_gate(masked(pipe, 128, args.thr), safe, args.edge, f"ass, thr {args.thr}", exp,
                                  args.qc, fps)
        err, got, rc = pipe.err, pipe.got, pipe.rc
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if rc != 0 or got != len(frames):
        raise cl.ClipError("render_failed", f"ffmpeg rendered {got}/{len(frames)} frames (exit {rc})",
                           hint="\n".join(err.strip().splitlines()[-8:]), exit_code=2)
    ff, seen = font_check(err, layout)
    findings += ff + f2
    if drift:
        warnings.append(f"model_drift: {len(drift)} frames with ink up to {max(d[1] for d in drift)} px outside the "
                        "layout's predicted boxes")
    return {"mode": "ass", "canvas": [w, h], "fps": cl.frac_str(fps), "frames": n, "safe": safe, "thr": args.thr,
            "header": header, "font": {"fontsdir": fontsdir, "fontselect": seen,
                                       "styles": {k: v.get("Fontname", "") for k, v in ass["styles"].items()}},
            **res}, findings, warnings


def _layout_spans(layout):
    spans = []
    for c in layout["chunks"]:
        for wd in c["words"]:
            spans.append((f"c{c['i']}w{wd['i']}", wd["appear_f"], wd["end_f"] - 1))
    return spans


def gate_video(args, ffmpeg, layout):
    warnings, findings = [], []
    info = cl.probe(args.video, ffmpeg)
    v = info.get("video") or {}
    w, h = v.get("width"), v.get("height")
    if not w:
        raise cl.ClipError("unreadable_input", f"no video stream in {args.video}", exit_code=2)
    if layout and (layout["canvas"]["w"], layout["canvas"]["h"]) != (w, h):
        raise cl.ClipError("usage", f"video {w}x{h} differs from the layout canvas", exit_code=2)
    fps = cl.parse_rate(args.fps) or v.get("fps_avg") or v.get("fps_r")
    n = args.frames or cl.count_frames(args.video, ffmpeg)
    safe = _safe_for(args, w, h, layout)
    excl = set()
    for span in (args.exclude or "").split(","):
        if span.strip():
            try:
                a, _, b = span.partition("-")
                excl.update(range(int(a), int(b or a) + 1))
            except ValueError:
                raise cl.ClipError("usage", f"--exclude spans are a-b frame numbers, got {span!r}", exit_code=2)
    spans = _layout_spans(layout) if layout else []
    exp = Expect(layout, None, spans, _faces_for(args, layout, fps, w, h, warnings), (layout or {}).get("style"))
    if layout and layout["frames"] != n:
        late = [f"c{ci}w{wd['i']}:{wd['text']}" for ci, wd in exp.words.values() if wd["end_f"] > n]
        findings.append({"id": "length_mismatch", "rank": "P0", "frames": [min(n, layout["frames"]),
                                                                           max(n, layout["frames"]) - 1],
                         "words": late, "measured": f"the video has {n} frames, the layout {layout['frames']}"
                         + (f"; {len(late)} word span(s) reach past the video end and are not checked" if late else ""),
                         "fix": "render the whole clip (all --parts joined) and gate the same cut the layout was made "
                                "for"})
    sampled = bool(args.sample and layout and not args.all_frames)
    if sampled:
        frames = sample_frames([(a, b) for _, a, b in spans], n, False, exp.full_frames())
        warnings.append("--sample: only the layout's sampled frames are read; motion between them (an editor's keyword "
                        "pop) is not checked")
    else:
        frames = list(range(n))
    frames = [k for k in frames if k < n]
    keep = [k for k in frames if k not in excl]
    min_blob = args.min_blob if args.min_blob is not None else max(4, round(24 * (min(w, h) / 1080) ** 2))
    noise = {"blobs_dropped": 0, "px_dropped": 0, "max_blob_dropped_px": 0, "min_blob_px": min_blob}
    work = Path(tempfile.mkdtemp(prefix="caption-gate-"))

    def skip_excluded(it):
        for tup in it:
            if tup[0] not in excl:
                yield tup

    pipes = []
    try:
        if args.clean:
            ci = cl.probe(args.clean, ffmpeg)["video"]
            if (ci["width"], ci["height"]) != (w, h):
                raise cl.ClipError("usage", "--clean must have the same size as --video", exit_code=2)
            nc = cl.count_frames(args.clean, ffmpeg)
            if nc != n and not args.frames:
                raise cl.ClipError("bad_input", f"--clean has {nc} frames, --video {n}: not the same cut",
                                   exit_code=2)
            pv = FramePipe(decode_cmd(ffmpeg, args.video, w, h, frames, work, "v", not sampled), w, h, frames)
            pc = FramePipe(decode_cmd(ffmpeg, args.clean, w, h, frames, work, "c", not sampled), w, h, frames)
            pipes = [pv, pc]
            res, f2, drift = run_gate(skip_excluded(diffed(pv, pc, args.diff_thr, min_blob, noise)), safe, args.edge,
                                      f"diff, thr {args.diff_thr}", exp, args.qc, fps, check_drift=False)
            # the layout's halo bound assumes #808080; over bright footage a shadow halo reads wider, so model
            # drift is only meaningful in ass and plate modes (outside_safe, presence and faces still apply here)
            if layout:
                res["model"] = {"skipped": "diff mode: halos over footage differ from the #808080 model"}
            res["noise"] = noise
            mode = "diff"
        else:
            bg = args.bg.lstrip("#")
            ref = tuple(int(bg[i:i + 2], 16) for i in (0, 2, 4))
            pv = FramePipe(decode_cmd(ffmpeg, args.video, w, h, frames, work, "v", not sampled), w, h, frames)
            pipes = [pv]
            res, f2, drift = run_gate(skip_excluded(masked(pv, ref, args.thr)), safe, args.edge,
                                      f"plate, thr {args.thr}", exp, args.qc, fps)
            mode = "plate"
            drift = drift or []
    finally:
        shutil.rmtree(work, ignore_errors=True)
    findings += f2
    for p in pipes:
        if p.rc != 0 or p.got != len(frames):
            findings.append({"id": "decode_short", "rank": "P0", "frames": [p.got, len(frames) - 1], "words": [],
                             "measured": f"decoded {p.got}/{len(frames)} frames (exit {p.rc}): "
                                         + " | ".join(p.err.strip().splitlines()[-3:]),
                             "fix": "the file is truncated or corrupt: re-render it; the missing frames were not "
                                    "checked"})
    if drift:
        warnings.append(f"model_drift: {len(drift)} frames with ink up to {max(d[1] for d in drift)} px outside the "
                        "layout's predicted boxes (an EffectCraft render drifting from the layout?)")
    if mode == "diff" and noise["blobs_dropped"]:
        warnings.append(f"diff noise: {noise['blobs_dropped']} blobs < {min_blob} px dropped "
                        f"({noise['px_dropped']} px, largest {noise['max_blob_dropped_px']} px)")
    res["frames_checked"] = min(res["frames_checked"], len(keep))
    return {"mode": mode, "canvas": [w, h], "fps": cl.frac_str(fps) if fps else None, "frames": n, "safe": safe,
            "thr": args.diff_thr if args.clean else args.thr, "excluded_frames": len(excl & set(frames)),
            "sampled": sampled, **res}, findings, warnings


# ---------------------------------------------------------------- self-test

def _naive_ass(lay, path, w, h, fs=124.1, low_y=None, playres=None, fontname=None, peak=None):
    """A hand-rolled ASS like the jobs before captions.py: one event per chunk line, 9:16 numbers, no fit, no clamp."""
    pw, ph = playres or (w, h)
    lines = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {pw}", f"PlayResY: {ph}", "WrapStyle: 2",
             "ScaledBorderAndShadow: yes", "", "[V4+ Styles]",
             "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
             "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
             "MarginL, MarginR, MarginV, Encoding",
             f"Style: Cap,{fontname or lay['font']['ass_fontname']},{fs:.2f},&H00FFFFFF,&H00FFFFFF,&H00000000,"
             "&H00000000,0,0,0,0,100,100,0,0,1,4,0,5,0,0,0,1", "", "[Events]",
             "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    fps = cl.parse_rate(lay["fps"])
    for c in lay["chunks"]:
        text = " ".join(wd["text"] for wd in c["words"])
        y = (low_y if low_y is not None else 0.5) * 1920   # 9:16 pixel numbers on any canvas
        ent = f"\\fscx{peak}\\fscy{peak}\\t(0,66,\\fscx100\\fscy100)" if peak else ""
        lines.append(f"Dialogue: 0,{cap.ass_time(c['start_f'], fps)},{cap.ass_time(c['end_f'], fps)},Cap,c{c['i']},0,0,"
                     f"0,,{{\\an5\\pos({540 if w == 1080 else w / 2:.0f},{y:.0f}){ent}}}{text}")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _peak_ass(src, dst, peak):
    """captions.py's ASS with an entrance overshoot to `peak` % that its layout did not count."""
    s = Path(src).read_text(encoding="utf-8")
    s = re.sub(r"\\t\(0,(\d+),(\\alpha&H[0-9A-F]{2}&)\\fscx([0-9.]+)\\fscy([0-9.]+)",
               lambda m: f"\\t(0,{m.group(1)},{m.group(2)}\\fscx{float(m.group(3)) * peak / 100:.2f}"
                         f"\\fscy{float(m.group(4)) * peak / 100:.2f}", s)
    Path(dst).write_text(s, encoding="utf-8")


def _move_ass(src, dst, name, x=None, y=None):
    """Every event of Name `name` moved to \\pos(x, y) (None keeps that coordinate)."""
    out = []
    for ln in Path(src).read_text(encoding="utf-8").split("\n"):
        if ln.startswith("Dialogue") and f",{name}," in ln:
            ln = re.sub(r"\\pos\(([-0-9.]+),([-0-9.]+)\)",
                        lambda m: f"\\pos({m.group(1) if x is None else x},{m.group(2) if y is None else y})", ln)
        out.append(ln)
    Path(dst).write_text("\n".join(out), encoding="utf-8", newline="\n")


def _gate_cli(args_list):
    me = [sys.executable, "-P", os.path.abspath(__file__)] + [str(a) for a in args_list]
    cp = subprocess.run(me, capture_output=True, env={**os.environ, "PYTHONIOENCODING": "utf8"})
    try:
        import json
        out = json.loads(cp.stdout.decode("utf-8", "replace"))
    except ValueError:
        out = {"raw": cp.stdout.decode("utf-8", "replace")[-500:],
               "stderr": cp.stderr.decode("utf-8", "replace")[-800:]}
    return cp.returncode, out


def selftest(args, ffmpeg):
    own = not args.workdir
    work = Path(tempfile.mkdtemp(prefix="caption-gate-selftest-")) if own else Path(args.workdir)
    work.mkdir(parents=True, exist_ok=True)
    font = cap.load_font(args.font, args.fontsdir)
    results = []

    def record(name, want_ok, code, out, extra=None, want_ids=None, want_code=None):
        got_ok = code == 0
        ids = sorted({f["id"] for f in out.get("findings", []) if f.get("rank") == "P0"})
        if want_code is not None:
            good = code == want_code
        else:
            good = got_ok == want_ok and (code in (0, 1))
        if want_ids and not set(want_ids) <= set(ids):
            good = False
        r = {"case": name, "ok": good, "exit": code,
             "want": f"exit {want_code}" if want_code is not None else ("pass" if want_ok else "FAIL"), "p0": ids,
             "min_margin_px": out.get("min_margin_px"), "frames_checked": out.get("frames_checked"),
             "model": (out.get("model") or {}).get("max_drift_px"),
             "lowest_cover": ((out.get("presence") or {}).get("lowest") or {}).get("cover")}
        if extra:
            r.update(extra)
        if not good:
            r["detail"] = out.get("error") or out.get("raw") or out.get("findings")
        results.append(r)
        cl.log(f"{'ok  ' if good else 'FAIL'} {name}: exit {code} (want {r['want']}) p0={ids} "
               f"margins={out.get('min_margin_px')} drift={r['model']} cover={r['lowest_cover']} "
               f"frames={out.get('frames_checked')}")
        return r

    enc = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "14", "-pix_fmt", "yuv420p",
           "-x264-params", "colorprim=bt709:transfer=bt709:colormatrix=bt709"]
    tags = "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv"
    to709 = f"scale=out_color_matrix=bt709:out_range=tv,format=yuv420p,{tags}"

    def burn(d, src, ass, out, n, extra_enc=None, fontsdir=None):
        """Render `ass` (in folder d) over a lavfi source with the escaped filter, cwd = d."""
        fsd = fesc(_rel_or_abs(fontsdir or font["fontsdir"], d))
        vf = (f"ass={fesc(Path(ass).name)}:fontsdir={fsd}," if ass else "") + to709
        cl.run([ffmpeg, "-hide_banner", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", src, "-vf", vf,
                "-frames:v", str(n), *(extra_enc or enc), out], cwd=d)

    try:
        cases = cap.selftest_cases()
        built = {}
        for name, (w, h), toks, faces, style, checks in cases:
            d = work / name
            d.mkdir(parents=True, exist_ok=True)
            lay = cap.layout(toks, w, h, "30/1", None, cap.load_faces(faces, "30/1", (w, h)) if faces else None,
                             font, style, cap.safe_area(w, h), allow_face_cover=bool(checks.get("allow_cover")))
            cap.write_ass(lay, d / "captions.ass")
            lay["ass"] = str(d / "captions.ass")
            cl.write_json_atomic(d / "layout.json", lay)
            built[name] = (lay, d)
            want = not checks.get("allow_cover")
            code, out = _gate_cli(["--ass", d / "captions.ass", "--layout", d / "layout.json", "--qc", d / "qc"])
            drift = (out.get("model") or {}).get("max_drift_px")
            r = record(f"{'pos' if want else 'neg'}/{name}", want, code, out,
                       want_ids=None if want else ["face_cover"])
            if want and (drift is None or drift > DRIFT_TOL):
                r["ok"] = False
                r["detail"] = f"model drift {drift}"
                cl.log(f"FAIL pos/{name}: model drift {drift}")

        # negative controls: each must FAIL
        lay, d = built["long_words_9x16"]
        _naive_ass(lay, d / "naive.ass", 1080, 1920)
        code, out = _gate_cli(["--ass", d / "naive.ass", "--canvas", "1080x1920", "--fps", "30",
                               "--frames", lay["frames"], "--fontsdir", font["fontsdir"], "--qc", d / "qc_naive"])
        record("neg/naive_long_words_no_fit_9x16", False, code, out)

        lay, d = built["long_sentence_9x16_6word_chunks"]
        _naive_ass(lay, d / "naive.ass", 1080, 1920, low_y=0.72)
        code, out = _gate_cli(["--ass", d / "naive.ass", "--canvas", "1080x1920", "--fps", "30",
                               "--frames", lay["frames"], "--fontsdir", font["fontsdir"]])
        record("neg/naive_6word_lines_low_72pct_9x16", False, code, out)

        lay, d = built["face_over_centre_16x9"]
        _naive_ass(lay, d / "naive.ass", 1920, 1080, low_y=1330 / 1920)
        code, out = _gate_cli(["--ass", d / "naive.ass", "--canvas", "1920x1080", "--fps", "30",
                               "--frames", lay["frames"], "--fontsdir", font["fontsdir"]])
        record("neg/9x16_low_y1330_on_16x9", False, code, out)

        lay, d = built["numbers_9x16"]
        s = (d / "captions.ass").read_text(encoding="utf-8").replace("PlayResX: 1080", "PlayResX: 1920") \
            .replace("PlayResY: 1920", "PlayResY: 1080")
        (d / "playres.ass").write_text(s, encoding="utf-8")
        code, out = _gate_cli(["--ass", d / "playres.ass", "--canvas", "1080x1920", "--fps", "30",
                               "--frames", lay["frames"], "--fontsdir", font["fontsdir"]])
        record("neg/playres_1920x1080_on_1080x1920", False, code, out)

        s = (d / "captions.ass").read_text(encoding="utf-8").replace(f",{lay['font']['ass_fontname']},",
                                                                    ",Montserrat Blak,", 1)
        (d / "typo.ass").write_text(s, encoding="utf-8")
        code, out = _gate_cli(["--ass", d / "typo.ass", "--canvas", "1080x1920", "--fps", "30",
                               "--frames", lay["frames"], "--fontsdir", font["fontsdir"]])
        record("neg/fontname_typo_fallback", False, code, out)

        # another weight of a prefix family ("Montserrat" -> Montserrat-Regular) without --layout
        fam = lay["font"]["ass_fontname"]
        if " " in fam:
            s = (d / "captions.ass").read_text(encoding="utf-8").replace(f",{fam},", f",{fam.split()[0]},", 1)
            (d / "prefix.ass").write_text(s, encoding="utf-8")
            code, out = _gate_cli(["--ass", d / "prefix.ass", "--canvas", "1080x1920", "--fps", "30",
                                   "--frames", lay["frames"], "--fontsdir", font["fontsdir"]])
            record("neg/fontname_prefix_family_other_weight_no_layout", False, code, out, want_ids=["font_fallback"])

        lay, d = built["long_words_9x16"]
        _peak_ass(d / "captions.ass", d / "peak.ass", 125)
        code, out = _gate_cli(["--ass", d / "peak.ass", "--layout", d / "layout.json", "--all-frames"])
        record("neg/uncounted_entrance_overshoot_125pct", False, code, out)

        # a whole word drawn off-frame (left, below) must fail: other ink on screen is no proof
        lay, d = built["long_sentence_9x16_6word_chunks"]
        c0 = lay["chunks"][0]
        wname = f"c0w{len(c0['words']) - 1}"
        _move_ass(d / "captions.ass", d / "off_left.ass", wname, x=-900)
        code, out = _gate_cli(["--ass", d / "off_left.ass", "--layout", d / "layout.json"])
        record("neg/whole_word_off_frame_left", False, code, out, want_ids=["missing_word"])
        _move_ass(d / "captions.ass", d / "off_below.ass", wname, y=2100)
        code, out = _gate_cli(["--ass", d / "off_below.ass", "--layout", d / "layout.json"])
        record("neg/whole_word_below_frame", False, code, out, want_ids=["missing_word"])
        code, out = _gate_cli(["--ass", d / "off_below.ass", "--canvas", "1080x1920", "--fps", "30",
                               "--frames", lay["frames"], "--fontsdir", font["fontsdir"]])
        record("neg/whole_word_below_frame_no_layout", False, code, out, want_ids=["off_frame"])
        # --safe without --canvas/--layout applies to the PlayRes canvas
        code, out = _gate_cli(["--ass", d / "captions.ass", "--fps", "30", "--safe", "0,0,1080,400",
                               "--fontsdir", font["fontsdir"]])
        record("neg/safe_flag_without_canvas", False, code, out, want_ids=["outside_safe"])

        # face cover: a chunk the layout moved off a face, moved back onto it
        lay2, d2 = built["low_two_lines_face_9x16"]
        c = lay2["chunks"][0]
        dy = round(1920 * 0.5 - c["words"][0]["baseline_center"][1], 2)
        s = (d2 / "captions.ass").read_text(encoding="utf-8")
        out_l = []
        for ln in s.split("\n"):
            if ln.startswith("Dialogue") and re.search(r",c0w\d+,", ln):
                ln = re.sub(r"\\pos\(([-0-9.]+),([-0-9.]+)\)",
                            lambda m: f"\\pos({m.group(1)},{float(m.group(2)) + dy:.2f})", ln)
            out_l.append(ln)
        (d2 / "on_face.ass").write_text("\n".join(out_l), encoding="utf-8", newline="\n")
        code, out = _gate_cli(["--ass", d2 / "on_face.ass", "--layout", d2 / "layout.json"])
        record("neg/chunk_moved_onto_face", False, code, out, want_ids=["face_cover"])

        # an apostrophe in the job path renders (escaped values, cwd = the ASS folder); a broken render exits 2
        dq = work / "it's job, [x]"
        dq.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(d / "captions.ass", dq / "captions.ass")
        cl.write_json_atomic(dq / "layout.json", lay)
        code, out = _gate_cli(["--ass", dq / "captions.ass", "--layout", dq / "layout.json"])
        record("pos/apostrophe_comma_bracket_path", True, code, out)
        code, out = _gate_cli(["--ass", dq / "captions.ass", "--layout", dq / "layout.json", "--ffmpeg",
                               sys.executable])  # not an ffmpeg: the render fails -> a tool error, exit 2
        record("tool/render_failure_exit2", False, code, out, want_code=2)

        # video modes: plate (an editor's caption-only render) and diff (edit vs caption-free render)
        n = lay["frames"]
        dur = cl.t6(Fraction(n) / 30)
        grey = f"color=c=0x808080:s=1080x1920:r=30:d={dur},format=rgb24"
        burn(d, grey, d / "captions.ass", "plate_good.mp4", n)
        burn(d, grey, d / "naive.ass", "plate_naive.mp4", n)
        burn(d, grey, d / "off_left.ass", "plate_off.mp4", n)
        code, out = _gate_cli(["--video", d / "plate_good.mp4", "--layout", d / "layout.json", "--qc", d / "qc_plate"])
        record("pos/plate_caption_only_render", True, code, out)
        code, out = _gate_cli(["--video", d / "plate_naive.mp4", "--layout", d / "layout.json"])
        record("neg/plate_naive_render", False, code, out)
        code, out = _gate_cli(["--video", d / "plate_off.mp4", "--layout", d / "layout.json"])
        record("neg/plate_whole_word_off_frame", False, code, out, want_ids=["missing_word"])
        # a keyword pop to 200 % between the sampled frames (an editor's animation): every frame is read
        mid = [wd for c in lay["chunks"] for wd in c["words"] if wd["end_f"] - wd["appear_f"] >= 12][0]
        pf = mid["appear_f"] + 6
        pop = (f"Dialogue: 3,{cap.ass_time(pf, 30)},{cap.ass_time(pf + 3, 30)},Cap,pop,0,0,0,,{{\\an5\\fs"
               f"{lay['font']['ass_fs']}\\bord3.6\\shad0\\pos(900,{mid['anchor'][1]})\\fscx200\\fscy200}}HOME")
        (d / "pop.ass").write_text((d / "captions.ass").read_text(encoding="utf-8").rstrip("\n") + "\n" + pop + "\n",
                                   encoding="utf-8", newline="\n")
        burn(d, grey, d / "pop.ass", "plate_pop.mp4", n)
        code, out = _gate_cli(["--video", d / "plate_pop.mp4", "--layout", d / "layout.json"])
        record("neg/plate_pop_between_samples", False, code, out, want_ids=["outside_safe"])
        # a render that stopped early (a failed part)
        burn(d, grey, d / "captions.ass", "plate_trunc.mp4", n * 2 // 3)
        code, out = _gate_cli(["--video", d / "plate_trunc.mp4", "--layout", d / "layout.json"])
        record("neg/plate_truncated_render", False, code, out, want_ids=["length_mismatch"])
        # footage: one moving RGB source; the clean render and the edit encode it separately (the real pipeline:
        # graded frames -> [captions] -> encode), so the diff sees two encodes' noise plus the captions
        src = f"testsrc2=s=1080x1920:r=30:d={dur},format=rgb24"
        burn(d, src, None, "clean.mp4", n)
        burn(d, src, d / "captions.ass", "edit_good.mp4", n)
        burn(d, src, d / "naive.ass", "edit_naive.mp4", n)
        burn(d, src, d / "off_left.ass", "edit_off.mp4", n)
        code, out = _gate_cli(["--video", d / "edit_good.mp4", "--clean", d / "clean.mp4", "--layout",
                               d / "layout.json", "--qc", d / "qc_diff"])
        record("pos/diff_edit_vs_clean", True, code, out)
        code, out = _gate_cli(["--video", d / "edit_naive.mp4", "--clean", d / "clean.mp4", "--layout",
                               d / "layout.json"])
        record("neg/diff_naive_edit_vs_clean", False, code, out)
        code, out = _gate_cli(["--video", d / "edit_off.mp4", "--clean", d / "clean.mp4", "--layout",
                               d / "layout.json"])
        record("neg/diff_whole_word_off_frame", False, code, out, want_ids=["missing_word"])
        # grainy footage, two separate medium-preset encodes: grain must not read as caption ink
        gsrc = src + ",noise=alls=25:allf=t"
        genc = ["-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
                "-x264-params", "colorprim=bt709:transfer=bt709:colormatrix=bt709"]
        burn(d, gsrc, None, "clean_grain.mp4", n, genc)
        burn(d, gsrc, d / "captions.ass", "edit_grain.mp4", n, genc)
        code, out = _gate_cli(["--video", d / "edit_grain.mp4", "--clean", d / "clean_grain.mp4", "--layout",
                               d / "layout.json"])
        record("pos/diff_grainy_footage_two_encodes", True, code, out,
               extra={"noise": out.get("noise")})
    finally:
        if own and not args.keep_temp:
            shutil.rmtree(work, ignore_errors=True)
    ok = all(r["ok"] for r in results)
    return {"ok": ok, "version": SCRIPT_VERSION, "ffmpeg": cl.ffmpeg_version(ffmpeg), "font": font["path"],
            "passed": sum(r["ok"] for r in results), "failed": sum(not r["ok"] for r in results),
            "selftest": results, "workdir": None if own and not args.keep_temp else str(work)}


# ---------------------------------------------------------------- CLI

class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise cl.ClipError("usage", message, hint=self.format_usage().strip(), exit_code=2)


def main() -> int:
    try:
        return _run()
    except cl.ClipError as e:  # the JSON envelope carries the version too
        env = e.envelope()
        env["version"] = SCRIPT_VERSION
        cl.emit(env)
        cl.log(f"error [{e.code}]: {e.message}" + (f"\nhint: {e.hint}" if e.hint else ""))
        return e.exit_code


def _run():
    ap = _Parser(description="Caption safe-area gate on rendered pixels (ref 07).")
    ap.add_argument("--ass")
    ap.add_argument("--video", help="a delivered edit (with --clean) or a caption-only render")
    ap.add_argument("--clean", help="the caption-free render of the same frames (diff mode)")
    ap.add_argument("--layout", help="captions.py's layout JSON (canvas, fps, frames, safe area, word boxes, font)")
    ap.add_argument("--faces", help="face boxes (captions.py --faces forms): ink in their eyes-to-chin regions fails")
    ap.add_argument("--canvas")
    ap.add_argument("--fps")
    ap.add_argument("--frames", type=int)
    ap.add_argument("--fontsdir")
    ap.add_argument("--font", help="--self-test: the font to build the cases with")
    ap.add_argument("--all-frames", action="store_true", help="ass mode: render every frame")
    ap.add_argument("--sample", action="store_true", help="video modes: read only the layout's sampled frames")
    ap.add_argument("--thr", type=int, default=24, help="ink = max|px - bg| > thr (default 24)")
    ap.add_argument("--diff-thr", type=int, default=CORE_DIFF,
                    help=f"diff mode glyph threshold: max|edit - clean| > thr (default {CORE_DIFF})")
    ap.add_argument("--min-blob", type=int, help="diff mode: drop ink blobs under this many px (default 24 px at a "
                                                 "1080 px short side, scaled by area)")
    ap.add_argument("--bg", default="808080", help="plate mode background colour (default 808080)")
    ap.add_argument("--edge", type=int, default=2, help="px band at the frame edge that counts as clipped")
    ap.add_argument("--exclude", help="frame spans a-b,c-d to skip (accents in diff mode)")
    cap.add_safe_args(ap)
    ap.add_argument("--qc", help="folder for caption_gate_sheet.png and caption_gate.json")
    ap.add_argument("--out")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--workdir")
    ap.add_argument("--keep-temp", action="store_true")
    ap.add_argument("--ffmpeg")
    args = ap.parse_args()
    ffmpeg = cl.find_ffmpeg(args.ffmpeg)
    if args.self_test:
        res = selftest(args, ffmpeg)
        cl.emit(res)
        return 0 if res["ok"] else 1
    if bool(args.ass) == bool(args.video):
        ap.error("pass exactly one of --ass or --video (or --self-test)")
    layout = cl.read_json(args.layout) if args.layout else None
    if args.ass:
        res, findings, warnings = gate_ass(args, ffmpeg, layout)
    else:
        res, findings, warnings = gate_video(args, ffmpeg, layout)
    if res["frames_with_ink"] == 0:
        findings.append({"id": "no_ink", "rank": "P0", "frames": None, "words": [],
                         "measured": f"no caption ink on {res['frames_checked']} checked frames",
                         "fix": "every caption is off-screen or missing: check PlayRes, positions and the font"})
    findings.sort(key=lambda f: (f["rank"] != "P0", f["id"]))
    ok = not any(f["rank"] == "P0" for f in findings)
    out = {"ok": ok, "version": SCRIPT_VERSION, **res, "findings": findings, "warnings": warnings}
    for f in findings:
        cl.log(f"{f['rank']} {f['id']} frames {f['frames']}: {f['measured']} words={f['words']}")
    for wmsg in warnings:
        cl.log(f"warning: {wmsg}")
    cl.log(f"caption_gate {'PASS' if ok else 'FAIL'} {res['mode']}: {res['frames_checked']} frames, ink bbox "
           f"{res['ink_bbox']}, min margins {res['min_margin_px']}")
    if args.qc:
        cl.write_json_atomic(Path(args.qc) / "caption_gate.json", out)
    if args.out:
        cl.write_json_atomic(args.out, out)
    cl.emit(out)
    return 0 if ok else 1


if __name__ == "__main__":
    cl.run_main(main)
