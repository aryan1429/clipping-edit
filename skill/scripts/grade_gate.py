"""Grade gate: does the graded footage measurably beat the raw footage on the same frames?

Ref 04 section 3 (grade gates) and ref 01 section 0 (Defaults). RAW is the reframed, ungraded clip
(raw/NN-slug.mp4, tagged BT.709 tv). GRADED is, preferably, the grade-only render of the same timeline
(qc/NN/grade.mp4: raw through the same grade chain, no captions or overlays). Failing that it may be the
delivered edited/NN-slug.mp4, and then caption/sticker boxes must be masked (--mask) and accent and freeze
spans skipped (--exclude): captions alone read as sharpness x7 on an ungraded clip.

Both files are sampled at the same decoded frame indexes, one index-exact decode per file (ref 05 section 1,
"Frames by index"): the frame showing t = i + 0.5 s for i < floor(D), k(t) = floor((t + 0.0005) * fps + 1e-6),
D = decoded frames / fps. Fewer than 8 usable samples: the grid halves to 0.5 s once, then the gate refuses.

metrics() below is THE metric definition, shared with analysis/tools/extract_ref.py (ref 04 section 3,
"One metric definition"): luma = mean HSV V and sat = median HSV S of the frame resized to 90x160; sharp =
Laplacian variance, contrast = std and p2 = 2nd percentile of the grey frame resized to 720 px high (INTER_AREA).

Gates (each GRADED vs RAW; all initial values, HyperFrames calls its own "to be calibrated"):
  luma      ratio >= 1.10          sat     ratio >= 1.25          sharp   ratio >= 1.40   (ref 01 Defaults)
  contrast  ratio >= 1.00 (target 1.10-1.15)                      p2      rise <= 6       (no lifted-black haze)
  warmth    mean(R - B) rise <= 12                                clip    max(R,G,B) >= 250 rise <= 3 pp
  face_clip the same inside the face box, rise <= 1 pp
  skin      inner 60% of the face box: saturation-weighted circular-mean hue in 10-25 deg, drift <= 5 deg
  dark_skin when the raw face's median V < 110: face grey std and median S keep >= 0.98x
  ratio(o, s) = 1 when both are under the floor (luma 1, contrast 1, sat 2.55, sharp 1), else o / s.
  The face gates are null (not applicable) without --faces or when no sample has a usable face box.

Usage:
  python -P grade_gate.py RAW GRADED [--faces faces.json] [--mask mask.json] [--exclude excl.json]
         [--edited] [--waive luma,sat,...] [--name NN] [--json report.json] [--ffmpeg PATH] [--ffprobe PATH|none]

Inputs:
  RAW, GRADED  Same canvas size and frame rate. A grade-only GRADED must also have the same frame count (+-1).
               Both must be BT.709 tv or untagged (untagged is decoded as BT.709 tv, with a warning).
  --faces      {"fps": "60/1", "boxes": [[frame, x0, y0, x1, y1], ...]} in canvas px. A sample uses the box
               with the latest time (frame / fps) at or before it; [frame, null] ends a track (no face).
  --mask       [{"t0": s, "t1": s, "box": [x0, y0, x1, y1]}, ...] caption/sticker boxes in canvas px; each is
               grown by 8 px and masked on every sample whose frame overlaps [t0, t1).
  --exclude    [[t0, t1], ...] seconds; samples whose frame overlaps a span are skipped. Pass accent windows
               already widened by 0.5 s on each side, and the freeze span.
  --edited     GRADED is a delivered edit (implied when GRADED sits in a folder named "edited"); --mask and
               --exclude are then required (an empty list states "nothing to mask").
  --waive      Gate names the request overrides; they are reported as waived instead of failed.
  --name       The clip number for the log line (default: leading digits of GRADED's name or its folder).
  --json       Also write the report there (atomically).

Output: one JSON object on stdout:
  {"ok", "version", "name", "raw", "graded", "mode": "grade_only"|"edited", "w", "h", "fps": "num/den",
   "frames": {"raw", "graded"}, "step_s", "frames_used": [k, ...], "frames_excluded",
   "src_metrics": {...}, "out_metrics": {...} (luma, sat, sharp, contrast, p2, warmth, clip, face_clip,
   skin_hue, face_v, face_std, face_sat, face_frames), "ratios": {luma, sat, sharp, contrast},
   "deltas": {p2, warmth, clip_pp, face_clip_pp, skin_hue_deg},
   "gates": {name: {"ok": bool|null, "measured", "limit", "waived"}}, "failed": [...], "waived": [...],
   "log": "grade NN luma x1.13 sat x1.31 sharp x1.62 contrast x1.12 p2 +3 warm +4 clip +0.4pp skin 18° frames=24",
   "warnings": [...]}
  The log line also goes to stderr.
Exit codes: 0 every gate passed (or was waived); 1 a gate failed; 2 usage error, unreadable or mismatched
input, too few samples, or a short decode.
"""
# Approach adapted from HyperFrames (github.com/heygen-com/hyperframes, Apache-2.0); independent Python implementation.
import argparse
import math
import os
import re
import sys
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cliplib as cl  # noqa: E402

SCRIPT_VERSION = "1.0.0"

GATES = ("luma", "sat", "sharp", "contrast", "p2", "warmth", "clip", "face_clip", "skin", "dark_skin")
MIN_RATIO = {"luma": 1.10, "sat": 1.25, "sharp": 1.40, "contrast": 1.00}
FLOORS = {"luma": 1.0, "sat": 2.55, "sharp": 1.0, "contrast": 1.0}
MAX_P2_RISE = 6.0
MAX_WARMTH_RISE = 12.0
MAX_CLIP_RISE_PP = 3.0
MAX_FACE_CLIP_RISE_PP = 1.0
SKIN_HUE = (10.0, 25.0)
MAX_SKIN_DRIFT = 5.0
DARK_SKIN_V = 110.0
DARK_SKIN_KEEP = 0.98      # 0.98 rather than 1.0 leaves room for encode noise
CLIP_LEVEL = 250
MASK_PAD = 8
MIN_SAMPLES = 8
MIN_INNER_PX = 400
SMALL = (90, 160)          # cv2 (width, height) of the luma/sat frame
GREY_H = 720


# ---------------------------------------------------------------- the metric definition

def _cv():
    try:
        import cv2
        import numpy as np
    except ImportError:
        raise cl.ClipError("missing_module", "grade_gate needs opencv-python and numpy",
                           hint="pip install opencv-python numpy (and run python with -P, not -I)", exit_code=2)
    return cv2, np


def _fully_valid(cv2, np, valid, size):
    """valid (h, w) bool -> bool at `size` (w, h), True only where the whole source area is unmasked."""
    area = cv2.resize(valid.astype(np.float32), size, interpolation=cv2.INTER_AREA)
    return area >= 0.999


def skin_hue(hue_deg, sat):
    """Saturation-weighted circular mean of hues in degrees, in (-180, 180]; None without saturation.

    Circular, so hues 353 and 7 average to 0, not 180.
    """
    import numpy as np
    h = np.radians(np.asarray(hue_deg, dtype=np.float64))
    s = np.asarray(sat, dtype=np.float64)
    ys, xs = float(np.sum(np.sin(h) * s)), float(np.sum(np.cos(h) * s))
    if abs(ys) < 1e-12 and abs(xs) < 1e-12:
        return None
    return _wrap(math.degrees(math.atan2(ys, xs)))


def _wrap(deg):
    d = (deg + 180.0) % 360.0 - 180.0
    return 180.0 if d == -180.0 else d


def metrics(rgb, valid=None, face=None):
    """Grade metrics of one RGB uint8 frame (h, w, 3). THE definition for the gate and extract_ref.py.

    valid: optional (h, w) bool, False on masked pixels (caption boxes). face: optional (x0, y0, x1, y1) px.
    Returns luma (mean HSV V, 0-255), sat (median HSV S, 0-255), warmth (mean R - B) on the 90x160 frame;
    sharp (Laplacian variance), contrast (std), p2 (2nd percentile) of the grey frame at 720 px high; clip
    (share of pixels with max(R,G,B) >= 250, full size); and with a usable face box face_clip, skin_hue
    (degrees), face_v and face_sat (median V and S of the inner 60%, 0-255) and face_std (grey std there).
    skin_vec is the per-pixel mean of S * (sin H, cos H) behind skin_hue, so frames average circularly.
    """
    cv2, np = _cv()
    h, w = rgb.shape[:2]
    small = cv2.resize(rgb, SMALL)  # INTER_LINEAR, as extract_ref.py has always measured
    hsv = cv2.cvtColor(small, cv2.COLOR_RGB2HSV)
    grey_size = (max(1, round(w * GREY_H / h)), GREY_H)
    g = cv2.resize(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY), grey_size, interpolation=cv2.INTER_AREA).astype(np.float64)
    lap = cv2.Laplacian(g, cv2.CV_64F)
    peak = rgb.max(axis=2)
    if valid is None:
        vs = vg = vf = slice(None)
    else:
        # A sample counts only when nothing masked can reach it: its whole area at the reduced size must be
        # unmasked, and for the Laplacian also its 3x3 neighbours (else caption edges leak into sharpness).
        vs = _fully_valid(cv2, np, valid, SMALL)
        vg = cv2.erode(_fully_valid(cv2, np, valid, grey_size).astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
        vf = valid
        if not vs.any() or not vg.any():
            raise cl.ClipError("mask_covers_frame", "the --mask boxes cover the whole frame on a sample",
                               hint="check the mask boxes are in canvas pixels [x0, y0, x1, y1]", exit_code=2)
    gs = g[vg]
    out = {
        "luma": float(hsv[..., 2][vs].mean()),
        "sat": float(np.median(hsv[..., 1][vs])),
        "warmth": float((small[..., 0].astype(np.float64) - small[..., 2])[vs].mean()),
        "sharp": float(lap[vg].var()),
        "contrast": float(gs.std()),
        "p2": float(np.percentile(gs, 2)),
        "clip": float((peak[vf] >= CLIP_LEVEL).mean()),
    }
    if face is not None:
        out.update(_face_metrics(cv2, np, rgb, valid, peak, face))
    return out


def _face_metrics(cv2, np, rgb, valid, peak, face):
    h, w = rgb.shape[:2]
    x0, y0, x1, y1 = (int(round(v)) for v in face)
    x0, x1 = max(0, min(x0, w)), max(0, min(x1, w))
    y0, y1 = max(0, min(y0, h)), max(0, min(y1, h))
    bw, bh = x1 - x0, y1 - y0
    ix0, ix1 = x0 + int(round(0.2 * bw)), x1 - int(round(0.2 * bw))
    iy0, iy1 = y0 + int(round(0.2 * bh)), y1 - int(round(0.2 * bh))
    if ix1 <= ix0 or iy1 <= iy0:
        return {}
    box_ok = np.ones((bh, bw), bool) if valid is None else valid[y0:y1, x0:x1]
    inner_ok = np.ones((iy1 - iy0, ix1 - ix0), bool) if valid is None else valid[iy0:iy1, ix0:ix1]
    if int(inner_ok.sum()) < MIN_INNER_PX:
        return {}
    inner = rgb[iy0:iy1, ix0:ix1]
    hsvf = cv2.cvtColor(inner.astype(np.float32) / 255.0, cv2.COLOR_RGB2HSV)  # H in degrees, S and V 0..1
    hue, s, v = hsvf[..., 0][inner_ok], hsvf[..., 1][inner_ok], hsvf[..., 2][inner_ok]
    grey = cv2.cvtColor(inner, cv2.COLOR_RGB2GRAY).astype(np.float64)[inner_ok]
    return {
        "face_clip": float((peak[y0:y1, x0:x1][box_ok] >= CLIP_LEVEL).mean()),
        "skin_hue": skin_hue(hue, s),
        "skin_vec": (float(np.sum(np.sin(np.radians(hue)) * s)) / s.size, float(np.sum(np.cos(np.radians(hue)) * s)) / s.size),
        "face_v": float(np.median(v)) * 255.0,
        "face_sat": float(np.median(s)) * 255.0,
        "face_std": float(grey.std()),
    }


def ratio(o, s, floor):
    """Graded over raw; two values under the floor are both "nothing" and count as equal."""
    if o < floor and s < floor:
        return 1.0
    return o / max(s, 1e-9)


# ---------------------------------------------------------------- inputs

def _load_list(path, what):
    obj = cl.read_json(path)
    if not isinstance(obj, list):
        raise cl.ClipError("bad_input", f"{what} must be a JSON list: {path}", exit_code=2)
    return obj


def load_mask(path):
    out = []
    for i, m in enumerate(_load_list(path, "--mask")):
        try:
            t0, t1 = float(m["t0"]), float(m["t1"])
            x0, y0, x1, y1 = (float(v) for v in m["box"])
        except (KeyError, TypeError, ValueError):
            raise cl.ClipError("bad_input", f"--mask entry {i} is not {{'t0', 't1', 'box': [x0, y0, x1, y1]}}",
                               exit_code=2)
        if t1 <= t0 or x1 <= x0 or y1 <= y0:
            raise cl.ClipError("bad_input", f"--mask entry {i} is empty or reversed: {m}", exit_code=2)
        out.append((t0, t1, (x0, y0, x1, y1)))
    return out


def load_exclude(path):
    out = []
    for i, span in enumerate(_load_list(path, "--exclude")):
        try:
            t0, t1 = float(span[0]), float(span[1])
        except (IndexError, TypeError, ValueError):
            raise cl.ClipError("bad_input", f"--exclude entry {i} is not [t0, t1]", exit_code=2)
        if t1 <= t0:
            raise cl.ClipError("bad_input", f"--exclude entry {i} is empty or reversed: {span}", exit_code=2)
        out.append((t0, t1))
    return out


def load_faces(path):
    """Sorted [(time_s, box or None)] from {"fps", "boxes": [[frame, x0, y0, x1, y1] | [frame, null]]}."""
    obj = cl.read_json(path)
    fps = cl.parse_rate(obj.get("fps")) if isinstance(obj, dict) else None
    if not fps or not isinstance(obj.get("boxes"), list):
        raise cl.ClipError("bad_input", f"--faces must be {{'fps', 'boxes': [[frame, x0, y0, x1, y1], ...]}}: {path}",
                           exit_code=2)
    track = []
    for i, b in enumerate(obj["boxes"]):
        try:
            frame = int(b[0])
            box = None if len(b) < 5 or b[1] is None else tuple(float(v) for v in b[1:5])
        except (IndexError, TypeError, ValueError):
            raise cl.ClipError("bad_input", f"--faces box {i} is not [frame, x0, y0, x1, y1]", exit_code=2)
        if box and (box[2] <= box[0] or box[3] <= box[1]):
            raise cl.ClipError("bad_input", f"--faces box {i} is empty or reversed: {b}", exit_code=2)
        track.append((Fraction(frame) / fps, box))
    track.sort(key=lambda x: x[0])
    return track


def face_at(track, t):
    box = None
    for ts, b in track:
        if ts > t:
            break
        box = b
    return box


def _overlaps(a0, a1, b0, b1):
    return a0 < b1 and b0 < a1


def sample_frames(n_frames, fps, step, exclude):
    """(used, excluded) frame indexes: the frame showing t = (i + 0.5) * step, for i < floor(D / step).

    k(t) = floor((t + 0.0005) * fps + 1e-6), the ref 03 Frame grid for samples, in exact rational arithmetic.
    A sample is excluded when its frame's display interval [k/fps, (k+1)/fps) overlaps an --exclude span.
    """
    dur = Fraction(n_frames) / fps
    used, excluded = [], 0
    for i in range(math.floor(dur / step)):
        t = (i + Fraction(1, 2)) * step
        k = math.floor((t + Fraction(1, 2000)) * fps + Fraction(1, 10 ** 6))
        if k >= n_frames:
            continue
        a, b = float(Fraction(k) / fps), float(Fraction(k + 1) / fps)
        if any(_overlaps(a, b, t0, t1) for t0, t1 in exclude):
            excluded += 1
        else:
            used.append(k)
    return used, excluded


def _probe_video(path, ffmpeg, ffprobe, warnings):
    info = cl.probe(path, ffmpeg, ffprobe)
    v = info.get("video")
    if not v or not v.get("width"):
        raise cl.ClipError("no_video", f"no video stream in {path}", exit_code=2)
    fps = v.get("fps_r") or v.get("fps_avg")
    if not fps:
        raise cl.ClipError("no_fps", f"cannot read the frame rate of {path}", exit_code=2)
    # Rule "Name the matrix at every RGB hop": raw/ is BT.709 tv and is decoded as exactly that.
    space, rng = v.get("color_space"), v.get("color_range")
    if (v.get("pix_fmt") or "").startswith("yuvj"):
        rng = "pc"
    if space not in (None, "bt709") or rng not in (None, "tv"):
        raise cl.ClipError("not_bt709", f"{Path(path).name} is {space or '?'}/{rng or '?'}, not BT.709 tv",
                           hint="the grade gate reads BT.709 tv intermediates; normalise per ref 03 section 1",
                           exit_code=2)
    if space is None or rng is None:
        warnings.append(f"{Path(path).name}: matrix/range untagged; decoded as BT.709 tv")
    return v, Fraction(fps)


def _default_name(graded):
    p = Path(graded)
    for s in (p.stem, p.parent.name):
        m = re.match(r"(\d+)", s)
        if m:
            return m.group(1)
    return p.stem


# ---------------------------------------------------------------- measuring

def measure(path, ffmpeg, idx, fps, masks, faces, w, h):
    """[metrics per sampled frame] in idx order, from one index-exact decode of `path`."""
    _, np = _cv()
    frames = cl.decode_frames_rgb(path, ffmpeg, idx, width=w, height=h, matrix="bt709", in_range="tv")
    missing = [k for k in idx if k not in frames]
    if missing:
        raise cl.ClipError("decode_short", f"{Path(path).name}: the decode returned {len(frames)} of {len(idx)} "
                           f"sampled frames (missing {missing[:10]})",
                           hint="the file is shorter than its packet count or damaged; re-render it", exit_code=2)
    out = []
    for k in idx:
        a, b = float(Fraction(k) / fps), float(Fraction(k + 1) / fps)
        valid = None
        live = [box for t0, t1, box in masks if _overlaps(a, b, t0, t1)]
        if live:
            valid = np.ones((h, w), bool)
            for x0, y0, x1, y1 in live:
                valid[max(0, int(y0) - MASK_PAD):max(0, int(math.ceil(y1)) + MASK_PAD),
                      max(0, int(x0) - MASK_PAD):max(0, int(math.ceil(x1)) + MASK_PAD)] = False
        face = face_at(faces, Fraction(k) / fps) if faces else None
        out.append(metrics(frames.pop(k), valid, face))
    return out


def aggregate(per, face_rows):
    """Mean of each metric over the samples; face metrics over the samples in face_rows only."""
    keys = ("luma", "sat", "sharp", "contrast", "p2", "warmth", "clip")
    agg = {k: sum(m[k] for m in per) / len(per) for k in keys}
    rows = [per[i] for i in face_rows]
    agg["face_frames"] = len(rows)
    if rows:
        for k in ("face_clip", "face_v", "face_std", "face_sat"):
            agg[k] = sum(m[k] for m in rows) / len(rows)
        # circular mean over frames as well: average the per-frame weighted unit vectors
        ys = sum(m["skin_vec"][0] for m in rows)
        xs = sum(m["skin_vec"][1] for m in rows)
        agg["skin_hue"] = _wrap(math.degrees(math.atan2(ys, xs))) if abs(ys) + abs(xs) > 1e-12 else None
    else:
        agg.update(face_clip=None, face_v=None, face_std=None, face_sat=None, skin_hue=None)
    return agg


def judge(src, out):
    """(ratios, deltas, gates) from the aggregated raw and graded metrics."""
    ratios = {k: ratio(out[k], src[k], FLOORS[k]) for k in ("luma", "sat", "sharp", "contrast")}
    has_face = src["face_frames"] > 0
    has_hue = has_face and src["skin_hue"] is not None and out["skin_hue"] is not None
    deltas = {"p2": out["p2"] - src["p2"], "warmth": out["warmth"] - src["warmth"],
              "clip_pp": 100.0 * (out["clip"] - src["clip"]),
              "face_clip_pp": 100.0 * (out["face_clip"] - src["face_clip"]) if has_face else None,
              "skin_hue_deg": _wrap(out["skin_hue"] - src["skin_hue"]) if has_hue else None}
    gates = {}
    for k in ("luma", "sat", "sharp"):
        gates[k] = {"ok": ratios[k] >= MIN_RATIO[k], "measured": ratios[k], "limit": f">= x{MIN_RATIO[k]:.2f}"}
    gates["contrast"] = {"ok": ratios["contrast"] >= MIN_RATIO["contrast"], "measured": ratios["contrast"],
                         "limit": ">= x1.00 (target x1.10-1.15)"}
    gates["p2"] = {"ok": deltas["p2"] <= MAX_P2_RISE, "measured": deltas["p2"], "limit": f"rise <= {MAX_P2_RISE:g}"}
    gates["warmth"] = {"ok": deltas["warmth"] <= MAX_WARMTH_RISE, "measured": deltas["warmth"],
                       "limit": f"mean(R-B) rise <= {MAX_WARMTH_RISE:g}"}
    gates["clip"] = {"ok": deltas["clip_pp"] <= MAX_CLIP_RISE_PP, "measured": deltas["clip_pp"],
                     "limit": f"max(R,G,B) >= {CLIP_LEVEL} rise <= {MAX_CLIP_RISE_PP:g} pp"}
    gates["face_clip"] = {"ok": deltas["face_clip_pp"] <= MAX_FACE_CLIP_RISE_PP if has_face else None,
                          "measured": deltas["face_clip_pp"], "limit": f"rise <= {MAX_FACE_CLIP_RISE_PP:g} pp in the face box"}
    if has_hue:
        hue = out["skin_hue"]
        ok = SKIN_HUE[0] <= hue <= SKIN_HUE[1] and abs(deltas["skin_hue_deg"]) <= MAX_SKIN_DRIFT
        gates["skin"] = {"ok": ok, "measured": {"hue": hue, "drift": deltas["skin_hue_deg"]},
                         "limit": f"hue {SKIN_HUE[0]:g}-{SKIN_HUE[1]:g} deg, drift <= {MAX_SKIN_DRIFT:g} deg"}
    else:
        gates["skin"] = {"ok": None, "measured": None, "limit": "needs a face box (--faces)"}
    if has_face and src["face_v"] < DARK_SKIN_V:
        keep_std, keep_sat = out["face_std"] / max(src["face_std"], 1e-9), out["face_sat"] / max(src["face_sat"], 1e-9)
        gates["dark_skin"] = {"ok": keep_std >= DARK_SKIN_KEEP and keep_sat >= DARK_SKIN_KEEP,
                              "measured": {"std": keep_std, "sat": keep_sat},
                              "limit": f"face std and median S >= x{DARK_SKIN_KEEP:g} (raw median V < {DARK_SKIN_V:g})"}
    else:
        gates["dark_skin"] = {"ok": None, "measured": src["face_v"] if has_face else None,
                              "limit": f"applies when the raw face median V < {DARK_SKIN_V:g}"}
    return ratios, deltas, gates


def log_line(name, ratios, deltas, out, n, failed):
    skin = f"{out['skin_hue']:.0f}°" if out.get("skin_hue") is not None else "-"
    line = (f"grade {name} luma x{ratios['luma']:.2f} sat x{ratios['sat']:.2f} sharp x{ratios['sharp']:.2f} "
            f"contrast x{ratios['contrast']:.2f} p2 {deltas['p2']:+.0f} warm {deltas['warmth']:+.0f} "
            f"clip {deltas['clip_pp']:+.1f}pp skin {skin} frames={n}")
    return line + (f" FAIL {','.join(failed)}" if failed else "")


def _round(obj):
    if isinstance(obj, float):
        return round(obj, 6)
    if isinstance(obj, dict):
        return {k: _round(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_round(v) for v in obj]
    return obj


# ---------------------------------------------------------------- CLI

def main() -> int:
    ap = argparse.ArgumentParser(description="Grade gate: graded vs raw footage on index-paired frames.")
    ap.add_argument("raw")
    ap.add_argument("graded")
    ap.add_argument("--faces")
    ap.add_argument("--mask")
    ap.add_argument("--exclude")
    ap.add_argument("--edited", action="store_true")
    ap.add_argument("--waive", default="")
    ap.add_argument("--name")
    ap.add_argument("--json")
    ap.add_argument("--ffmpeg")
    ap.add_argument("--ffprobe")
    args = ap.parse_args()

    waived = [x.strip() for x in args.waive.split(",") if x.strip()]
    unknown = [x for x in waived if x not in GATES]
    if unknown:
        raise cl.ClipError("bad_waive", f"unknown gate name(s) in --waive: {', '.join(unknown)}",
                           hint=f"gate names: {', '.join(GATES)}", exit_code=2)
    edited = args.edited or Path(args.graded).resolve().parent.name.lower() == "edited"
    if edited and (args.mask is None or args.exclude is None):
        raise cl.ClipError("mask_required", "GRADED is a delivered edit: --mask and --exclude are required",
                           hint="pass the caption/sticker boxes (--mask) and the accent +-0.5 s and freeze spans "
                                "(--exclude), or gate the grade-only render qc/NN/grade.mp4 instead", exit_code=2)
    masks = load_mask(args.mask) if args.mask else []
    exclude = load_exclude(args.exclude) if args.exclude else []
    faces = load_faces(args.faces) if args.faces else []

    ffmpeg = cl.find_ffmpeg(args.ffmpeg)
    ffprobe = cl.find_ffprobe(ffmpeg, args.ffprobe)
    warnings = []
    vr, fps = _probe_video(args.raw, ffmpeg, ffprobe, warnings)
    vg, fps_g = _probe_video(args.graded, ffmpeg, ffprobe, warnings)
    w, h = vr["width"], vr["height"]
    if (vg["width"], vg["height"]) != (w, h):
        raise cl.ClipError("size_mismatch", f"RAW is {w}x{h}, GRADED is {vg['width']}x{vg['height']}",
                           hint="gate the grade on the same canvas as raw/ (same crop and scale)", exit_code=2)
    if abs(float(fps) - float(fps_g)) >= 0.01:
        raise cl.ClipError("fps_mismatch", f"RAW is {cl.frac_str(fps)} fps, GRADED is {cl.frac_str(fps_g)} fps",
                           hint="render the grade on the raw frame grid", exit_code=2)
    n_raw, n_out = cl.count_frames(args.raw, ffmpeg), cl.count_frames(args.graded, ffmpeg)
    if not edited and abs(n_raw - n_out) > 1:
        raise cl.ClipError("length_mismatch", f"RAW has {n_raw} frames, GRADED has {n_out}",
                           hint="a grade-only render covers the whole raw timeline frame for frame", exit_code=2)
    n = min(n_raw, n_out)

    step = Fraction(1)
    idx, n_excl = sample_frames(n, fps, step, exclude)
    if len(idx) < MIN_SAMPLES:
        step = Fraction(1, 2)
        idx, n_excl = sample_frames(n, fps, step, exclude)
        warnings.append("under 8 samples on the 1 s grid; sampled every 0.5 s")
    if len(idx) < MIN_SAMPLES:
        raise cl.ClipError("too_few_samples", f"only {len(idx)} usable samples ({n_excl} excluded); need {MIN_SAMPLES}",
                           hint="the clip is too short or --exclude covers most of it", exit_code=2)
    cl.log(f"grade_gate: {len(idx)} samples at {float(step):g} s steps, {n_excl} excluded, {w}x{h} @ {cl.frac_str(fps)}")

    per_src = measure(args.raw, ffmpeg, idx, fps, masks, faces, w, h)
    per_out = measure(args.graded, ffmpeg, idx, fps, masks, faces, w, h)
    face_rows = [i for i, (a, b) in enumerate(zip(per_src, per_out)) if "face_std" in a and "face_std" in b]
    if faces and not face_rows:
        warnings.append("--faces given but no sample has a usable face box; face gates not applied")
    src, out = aggregate(per_src, face_rows), aggregate(per_out, face_rows)
    ratios, deltas, gates = judge(src, out)
    for k, g in gates.items():
        g["waived"] = k in waived
    failed = [k for k, g in gates.items() if g["ok"] is False and not g["waived"]]
    name = args.name or _default_name(args.graded)
    line = log_line(name, ratios, deltas, out, len(idx), failed)
    cl.log(line)
    for k in failed:
        cl.log(f"  gate {k} failed: measured {gates[k]['measured']}, limit {gates[k]['limit']}")
    for wmsg in warnings:
        cl.log(f"  warning: {wmsg}")

    report = _round({
        "ok": not failed, "version": SCRIPT_VERSION, "name": name,
        "raw": Path(args.raw).as_posix(), "graded": Path(args.graded).as_posix(),
        "mode": "edited" if edited else "grade_only", "w": w, "h": h, "fps": cl.frac_str(fps),
        "frames": {"raw": n_raw, "graded": n_out}, "step_s": float(step),
        "frames_used": idx, "frames_excluded": n_excl,
        "src_metrics": src, "out_metrics": out, "ratios": ratios, "deltas": deltas,
        "gates": gates, "failed": failed, "waived": waived, "log": line, "warnings": warnings,
    })
    if args.json:
        cl.write_json_atomic(args.json, report)
    cl.emit(report)
    return 0 if not failed else 1


if __name__ == "__main__":
    cl.run_main(main)
