"""cuts.py - classified shot-cut detector and the render cut gate (ref 04 section 2; ref 05 section 1).

Usage:
  python -P cuts.py VIDEO [--start S] [--end E] [--lead 0.5] [--fps NUM/DEN] [--plan plan.json]
                    [--out cuts.json] [--ffmpeg PATH] [--ffprobe PATH|none]

What it does:
  detect   Every frame of the window is read as 64x36 grey (scale=64:36:flags=area). d[i] = mean |F[i] - F[i-1]|,
           d[0] = 0. typical = max(1, median) of the neighbours' d >= 0.5 within +-N frames (1 when fewer than 4).
           Hard hit: d >= 12 and d >= 4 x typical. Soft hit (same-angle punch-in): d >= 10, d >= 8 x typical and
           d >= 4 x the largest neighbour. Hits on consecutive frames merge into one event (largest change; soft
           only if every hit is soft). An event longer than M frames is `fast` (whip, fast move, dissolve); one
           whose picture comes back within K frames (MAD < 0.4 x change) is `flash`; the rest are `hard`/`soft`
           cuts. N, M, K = 12r, 3r, 4r with r = max(1, round(fps / 30)) (ref 04 section 2, Classified cut detector).
           Blank bridge (ours): a cut followed by another event within K frames, with only flat frames (grey std
           <= 4) shown in between, is a flash: a dip through white/black into a new shot resets once, on the new
           shot.
  window   With --start/--end the decode covers [start - lead, end + lead] (a window's first frame has no d, so
           a cut on it would be missed without the lead); events are reported inside [start, end) only.
           Boundaries snap to the frame grid k = round(t * fps) (ref 03 section 2, Frame grid); the seek time is
           k/fps floored to the microsecond, and the frame count is exact (-frames:v). Every decoded frame is kept
           (2.3 KB each), so detect on clip windows rather than on a whole hour-long source.
  retime   The input should be a CFR clip intermediate (ref 03 section 1). A VFR input (average rate more than 1 %
           off the stream rate), or an --fps different from the stream rate, is re-timed with fps=R first, so
           frame indices sit on the R grid; a warning says so.
  gate     --plan runs the events-vs-plan gate (ref 05 section 1, Events match the plan) on the whole render and
           exits 1 on any P0. See match_plan() for the rules.

Inputs:
  VIDEO       any video ffmpeg reads: a clip intermediate (for reframe resets) or a render (for the gate).
  --start/--end  source seconds of the window (default: the whole file). --lead seconds of context (default 0.5).
  --fps       the frame grid (default: the stream's rate). Must match plan.fps when --plan is given.
  --plan      {"fps": "60/1", "frames": N, "cuts": [f, ...], "jump_cuts": [f, ...], "accent_spans": [[a, b], ...]}
              in output frames. cuts = every planned join, whip switch frame and kept source cut (cuts.py hard/soft
              events mapped into the clip); jump_cuts = same-camera punch-ins (never required: a 4-10 % punch-in
              can stay under the soft level); accent_spans = inclusive frame spans of flashes, tints, washes and
              whips (and any source flash kept in the clip). Not combinable with --start/--end.

Output (stdout; the same object to --out, written atomically):
  {"ok", "version", "video", "fps": "60/1", "probe": "ffprobe"|"ffmpeg", "vfr", "retimed",
   "window": {"start", "end", "lead", "k_start", "k_first", "decoded"},
   "params": {"r", "N", "M", "K"},
   "events": [{"frame", "t", "kind": "hard"|"soft"|"flash"|"fast", "d", "typical", "len"}],
   "reset_frames": [frame, ...],                     hard and soft cut frames only (reframe smoother resets)
   "gate": {"ok", "missing", "unplanned", "seam_confirmed", "findings": [{"id", "rank", "frame", "measured",
            "fix"}]}                                 only with --plan
   "warnings": [str]}
  frame counts from frame 0 = the frame at --start (k_start = round(start * fps) on the absolute grid); t is
  absolute source seconds of the event's first frame (k / fps, 6 decimals). k_first is the absolute grid frame
  of the first decoded frame (it sits in the lead).
Exit codes: 0 ok; 1 the plan gate found a P0; 2 usage error or unreadable input.

Library:
  detect(video, ffmpeg, start=None, end=None, fps=None, lead=0.5, ffprobe=None) -> dict
      the result above plus "diffs" (numpy float array, d per decoded frame; diffs[0] is the frame k_first) and
      "diffs_first" (the event-frame number of diffs[0], <= 0). The CLI drops both from its JSON.
  match_plan(events, plan, diffs=None) -> dict
      the "gate" block. diffs = detect(...)["diffs"] of the WHOLE render enables the seam confirmation of a
      planned cut that shows no event, and the frame-count check.
  hits_from_diffs(d, r) -> [hit], classify(frames, hits, r) -> [event]   the detector core (unit tests)
"""
import argparse
import math
import os
import sys
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cliplib as cl  # noqa: E402

SCRIPT_VERSION = "1.0.0"
# Approach adapted from HyperFrames (github.com/heygen-com/hyperframes, Apache-2.0); independent Python implementation.

SIG_W, SIG_H = 64, 36          # the grey signature every frame is reduced to
HARD = 12.0                    # hard hit: d >= HARD and d >= HARD_RATIO x typical
HARD_RATIO = 4.0
SOFT = 10.0                    # soft hit: d >= SOFT, >= SOFT_RATIO x typical, >= SOFT_ALONE x largest neighbour
SOFT_RATIO = 8.0
SOFT_ALONE = 4.0
HELD = 0.5                     # neighbour d below this is a held frame and does not count toward typical
MIN_MOVING = 4                 # fewer moving neighbours than this -> typical = 1
RETURNED = 0.4                 # flash: the picture comes back to MAD < RETURNED x change
FLAT_STD = 4.0                 # blank bridge: a frame whose grey std is <= this is a flat white/black/colour fill
CONFIRM = 6.0                  # ref 05 section 1: a planned cut with no event still passes on d >= CONFIRM ...
CONFIRM_RATIO = 4.0            # ... and d >= CONFIRM_RATIO x typical within +-1 frame (seam confirmation)
ACCENT_SLACK = 1               # ref 05 section 1: accent windows start 2 frames before the cause (plan spans
#                                start 1 before) and whip spans count +-1, so every span is widened by 1 frame
SLIVER_S = Fraction(1, 5)      # ref 03 section 2: no shot shorter than 0.20 s between cuts
VFR_TOL = 0.01                 # ref 03 section 1: VFR = average rate more than 1 % off the stream rate
CUT_KINDS = ("hard", "soft")


def scale_r(fps):
    """r = max(1, round(fps / 30)): the detector windows grow with the frame rate (ref 04 section 2)."""
    return max(1, int(math.floor(Fraction(fps) / 30 + Fraction(1, 2))))


def windows(r):
    """(N, M, K): neighbours each side, longest cut in frames, flash return reach in frames."""
    return 12 * r, 3 * r, 4 * r


def snap(t, fps):
    """Window boundary -> frame on the grid, k = round(t * fps) (half up; ref 03 section 2 Frame grid)."""
    return int(math.floor(Fraction(t) * Fraction(fps) + Fraction(1, 2)))


def seek_str(k, fps):
    """k/fps floored to the microsecond, 6 decimals, so frame k is the first frame ffmpeg keeps."""
    us = math.floor(Fraction(k) / Fraction(fps) * 1_000_000)
    return cl.t6(Fraction(us, 1_000_000))


def to_fraction(s, what):
    try:
        return Fraction(str(s))
    except (ValueError, ZeroDivisionError):
        raise cl.ClipError("usage", f"{what} must be a number, got {s!r}", exit_code=2)


# ---------------------------------------------------------------- detector core

def frame_diffs(frames):
    """d[i] = mean |F[i] - F[i-1]| in grey levels, d[0] = 0 (chunked so long windows stay small in memory)."""
    import numpy as np
    n = len(frames)
    d = np.zeros(n, dtype=np.float64)
    step = 2048
    for a in range(1, n, step):
        b = min(n, a + step)
        cur = frames[a:b].astype(np.int16)
        prev = frames[a - 1:b - 1].astype(np.int16)
        d[a:b] = np.abs(cur - prev).mean(axis=(1, 2))
    return d


def neighbours(d, i, n_each):
    """The moving neighbours of frame i: d of frames i-N..i-1 (never frame 0) and i+1..i+N that are >= HELD."""
    lo = max(1, i - n_each)
    near = list(d[lo:i]) + list(d[i + 1:i + n_each + 1])
    return [x for x in near if x >= HELD]


def typical_of(near):
    if len(near) < MIN_MOVING:
        return 1.0
    return max(1.0, float(sorted(near)[len(near) // 2]))


def hits_from_diffs(d, r):
    """Hard/soft hits on d, merged when consecutive: [{"frame", "frames", "change", "soft", "typical"}].

    typical is the one at the frame with the largest change of the merged run.
    """
    n_each = windows(r)[0]
    out = []
    for i in range(1, len(d)):
        x = float(d[i])
        if x < SOFT:  # below both levels: no hit (cheap early exit; HARD > SOFT)
            continue
        near = neighbours(d, i, n_each)
        typical = typical_of(near)
        if x >= HARD and x >= HARD_RATIO * typical:
            soft = False
        elif x >= SOFT_RATIO * typical and x >= SOFT_ALONE * max([0.0] + near):
            soft = True
        else:
            continue
        last = out[-1] if out else None
        if last and i == last["frame"] + last["frames"]:
            last["frames"] += 1
            if x > last["change"]:
                last["change"], last["typical"] = x, typical
            last["soft"] = last["soft"] and soft
        else:
            out.append({"frame": i, "frames": 1, "change": x, "soft": soft, "typical": typical})
    return out


def classify(frames, hits, r):
    """Name each merged hit: fast (> M frames), flash (picture back within K frames) or hard/soft (a cut).

    frames: the grey signatures (n, 36, 64) uint8. Negative indices are guarded explicitly (Python would wrap).
    """
    _, m_max, k_back = windows(r)
    n = len(frames)

    def mad(a, b):
        return float(abs(frames[a].astype("int16") - frames[b].astype("int16")).mean())

    events = []
    for h in hits:
        f, end, limit = h["frame"], h["frame"] + h["frames"], RETURNED * h["change"]
        if h["frames"] > m_max:
            kind = "fast"
        else:
            back = False
            for k in range(1, k_back + 1):
                # the frame before the hit against the frames after it ...
                if f - 1 >= 0 and end - 1 + k < n and mad(f - 1, end - 1 + k) < limit:
                    back = True
                # ... or an earlier frame against the first frame after the hit
                if f - k >= 0 and end < n and mad(f - k, end) < limit:
                    back = True
                if back:
                    break
            kind = "flash" if back else ("soft" if h["soft"] else "hard")
        events.append({"frame": f, "kind": kind, "d": h["change"], "typical": h["typical"], "len": h["frames"]})

    # Blank bridge (ours; extends ref 04 section 2 Classified cut detector). A dip through white or black between
    # two DIFFERENT shots (A | 2 white frames | B) never brings A back, so the return test above reads it as two
    # cuts K frames apart with a blank "shot" between them. When a cut is followed by the next event within K
    # frames and every frame shown in between is flat, the first change is the flash; the next event keeps its
    # own class (a cut when B is a new shot, a flash when A comes back).
    for a, b in zip(events, events[1:]):
        if a["kind"] in CUT_KINDS and b["frame"] - a["frame"] <= k_back:
            between = range(a["frame"] + a["len"] - 1, b["frame"])
            if all(float(frames[i].std()) <= FLAT_STD for i in between):
                a["kind"] = "flash"
    return events


# ---------------------------------------------------------------- probe and decode

def stream_rate(video, ffmpeg, ffprobe):
    """(probe name, stream rate fps_r or None, average rate or None) of the first video stream."""
    info = cl.probe(video, ffmpeg, ffprobe)
    v = info.get("video")
    if not v:
        raise cl.ClipError("no_video", f"{video} has no video stream", exit_code=2)
    return info["probe"], v.get("fps_r"), v.get("fps_avg")


def decode_window(video, ffmpeg, fps, k0, count, retime):
    """Grey 64x36 frames from grid frame k0 on (count frames, or to EOF when count is None)."""
    import numpy as np
    vf = ([f"fps={cl.frac_str(fps)}"] if retime else []) + [f"scale={SIG_W}:{SIG_H}:flags=area", "format=gray"]
    cmd = [ffmpeg, "-v", "error", "-nostdin"]
    if k0 > 0:
        cmd += ["-ss", seek_str(k0, fps)]
    cmd += ["-i", str(video), "-map", "0:v:0", "-an", "-vf", ",".join(vf)]
    if count is not None:
        cmd += ["-frames:v", str(count)]
    cmd += ["-f", "rawvideo", "-pix_fmt", "gray", "-"]
    cp = cl.run(cmd, binary=True, check=False)
    if cp.returncode != 0:
        raise cl.ClipError("decode_failed", f"ffmpeg could not decode {video}", hint=cp.stderr.strip()[-400:],
                           exit_code=2)
    size = SIG_W * SIG_H
    n = len(cp.stdout) // size
    return np.frombuffer(cp.stdout[: n * size], dtype=np.uint8).reshape(n, SIG_H, SIG_W)


def detect(video, ffmpeg, start=None, end=None, fps=None, lead=0.5, ffprobe=None):
    """Classified events of VIDEO over [start, end) (source seconds; None = file start / EOF). See the docstring."""
    if not Path(video).is_file():
        raise cl.ClipError("input_missing", f"no such file: {video}", exit_code=2)
    start = None if start is None else to_fraction(start, "--start")
    end = None if end is None else to_fraction(end, "--end")
    lead = to_fraction(lead, "--lead")
    if lead < 0 or (start is not None and start < 0):
        raise cl.ClipError("usage", "--start and --lead must be >= 0", exit_code=2)
    if start is not None and end is not None and end <= start:
        raise cl.ClipError("usage", f"--end {float(end)} must be after --start {float(start)}", exit_code=2)

    probe_name, rate, avg = stream_rate(video, ffmpeg, ffprobe)
    warnings = []
    want = cl.parse_rate(fps) if fps is not None else rate
    if want is None or want <= 0:
        raise cl.ClipError("no_rate", f"cannot read the frame rate of {video}", hint="pass --fps NUM/DEN", exit_code=2)
    vfr = bool(rate and avg and abs(float(avg) - float(rate)) / float(rate) > VFR_TOL)
    retime = vfr or rate is None or want != rate
    if retime:
        why = "VFR" if vfr else f"stream rate {cl.frac_str(rate) if rate else 'unknown'}"
        warnings.append(f"retimed: {why} input re-timed with fps={cl.frac_str(want)}; frame indices sit on that "
                        f"grid (detect on the CFR clip intermediate of ref 03 section 1 instead)")

    r = scale_r(want)
    k_start = snap(start, want) if start is not None else 0
    k_end = snap(end, want) if end is not None else None
    lead_frames = snap(lead, want) if (start is not None or end is not None) else 0
    k0 = max(0, k_start - lead_frames)
    count = (k_end + lead_frames - k0) if k_end is not None else None
    frames = decode_window(video, ffmpeg, want, k0, count, retime)
    n = len(frames)
    if n == 0:
        raise cl.ClipError("empty_window", f"no frames decoded from {video} at {seek_str(k0, want)} s",
                           hint="check --start against the file's duration", exit_code=2)
    if k_end is not None and k0 + n < k_end:
        warnings.append(f"window_past_eof: the file ends at grid frame {k0 + n}, before --end (frame {k_end})")

    d = frame_diffs(frames)
    rel = k0 - k_start                     # event frame of decoded frame 0 (<= 0 when a lead was decoded)
    last = (k_end - k_start) if k_end is not None else None
    events = []
    for e in classify(frames, hits_from_diffs(d, r), r):
        f = e["frame"] + rel
        if f < 0 or (last is not None and f >= last):
            continue                       # in the lead: context only
        events.append({"frame": f, "t": round(float(Fraction(k0 + e["frame"]) / want), 6), "kind": e["kind"],
                       "d": round(e["d"], 3), "typical": round(e["typical"], 3), "len": e["len"]})
    n_each, m_max, k_back = windows(r)
    return {"video": str(video), "fps": cl.frac_str(want), "probe": probe_name, "vfr": vfr, "retimed": retime,
            "window": {"start": None if start is None else round(float(start), 6),
                       "end": None if end is None else round(float(end), 6), "lead": round(float(lead), 6),
                       "k_start": k_start, "k_first": k0, "decoded": n},
            "params": {"r": r, "N": n_each, "M": m_max, "K": k_back},
            "events": events,
            "reset_frames": [e["frame"] for e in events if e["kind"] in CUT_KINDS],
            "warnings": warnings, "diffs": d, "diffs_first": rel}


# ---------------------------------------------------------------- plan gate (ref 05 section 1)

def _frames_list(plan, key):
    v = plan.get(key, [])
    if not isinstance(v, list) or not all(isinstance(x, int) and not isinstance(x, bool) for x in v):
        raise cl.ClipError("bad_plan", f"plan.{key} must be a list of frame integers", exit_code=2)
    return sorted(v)


def check_plan(plan):
    """Validate a plan dict; returns (fps Fraction, frames, cuts, jump_cuts, accent_spans)."""
    if not isinstance(plan, dict):
        raise cl.ClipError("bad_plan", "the plan must be a JSON object", exit_code=2)
    fps = cl.parse_rate(plan.get("fps"))
    frames = plan.get("frames")
    if fps is None or not isinstance(frames, int) or frames <= 0:
        raise cl.ClipError("bad_plan", "the plan needs fps (\"60/1\") and frames (an integer > 0)", exit_code=2)
    spans = plan.get("accent_spans", [])
    if not isinstance(spans, list) or not all(isinstance(s, list) and len(s) == 2 and all(isinstance(x, int)
                                                                                             for x in s)
                                              and s[0] <= s[1] for s in spans):
        raise cl.ClipError("bad_plan", "plan.accent_spans must be [[first, last], ...] inclusive frame pairs",
                           exit_code=2)
    cuts, jumps = _frames_list(plan, "cuts"), _frames_list(plan, "jump_cuts")
    outside = [f for f in cuts + jumps if not 0 < f < frames]
    if outside:
        raise cl.ClipError("bad_plan", f"planned cut frames outside 1..{frames - 1}: {outside}", exit_code=2)
    return fps, frames, cuts, jumps, [tuple(s) for s in spans]


def match_plan(events, plan, diffs=None):
    """The events-vs-plan gate (ref 05 section 1, Events match the plan). Returns the "gate" block.

    events: detect()["events"] of the whole render (frame 0 = its first frame). Rules, in order:
      accents  an event starting inside an accent span widened by ACCENT_SLACK is explained, whatever its kind
               (a 0.35 s flash decay reads as a multi-frame hit at 60 fps).
      cuts     each planned cut takes one event that covers it ([frame - 1, frame + len]): a hard/soft cut not
               used by another planned cut, or an accent-explained event (a whip's switch). No event: the cut
               still passes when d >= 6 and >= 4 x typical within +-1 frame (seam confirmation; needs diffs),
               else P0 missed_cut. A hard/soft event of 2-3 frames at a planned cut outside every accent span
               is P0 interloper (a black or orphan frame at the join).
      jumps    a planned jump cut explains one event within +-1 frame and is never required.
      rest     every other event is P0 unplanned_<kind> (sliver, doubled segment, part seam, stray flash). Two
               boundaries (planned cuts and unplanned events) closer than 0.20 s, one of them unplanned, add a
               P0 sliver naming the short shot.
      frames   with diffs, the decoded frame count must equal plan.frames (P0 frame_count).
    """
    fps, n_plan, cuts, jumps, spans = check_plan(plan)
    r = scale_r(fps)
    findings, used = [], set()

    def p0(fid, frame, measured, fix):
        findings.append({"id": fid, "rank": "P0", "frame": frame, "measured": measured, "fix": fix})

    if diffs is not None and len(diffs) != n_plan:
        p0("frame_count", None, f"{len(diffs)} frames decoded, plan has {n_plan}",
           "re-render: the render's frame count must equal the plan's N before cuts can be matched")

    def in_accent(e):
        return any(a - ACCENT_SLACK <= e["frame"] <= b + ACCENT_SLACK for a, b in spans)

    accent_ok = {i for i, e in enumerate(events) if in_accent(e)}
    seam_confirmed, missing = [], []
    for f in cuts:
        best = None
        for i, e in enumerate(events):
            if not (e["frame"] - 1 <= f <= e["frame"] + e["len"]):
                continue
            if i in accent_ok or (e["kind"] in CUT_KINDS and i not in used):
                dist = 0 if e["frame"] <= f < e["frame"] + e["len"] else 1
                if best is None or dist < best[0]:
                    best = (dist, i)
        if best is not None:
            i = best[1]
            used.add(i)
            e = events[i]
            if e["kind"] in CUT_KINDS and e["len"] > 1 and i not in accent_ok:
                p0("interloper", e["frame"], f"{e['len']}-frame change at the planned cut {f}",
                   "a black or orphan frame sits at the join: re-cut the join on the frame grid and check the "
                   "concat for a doubled or missing frame")
            continue
        if diffs is not None and _seam_confirms(diffs, f, r):
            seam_confirmed.append(f)
            findings.append({"id": "seam_confirmed", "rank": "info", "frame": f,
                             "measured": "no event, but d >= 6 and >= 4 x typical within +-1 frame", "fix": None})
            continue
        missing.append(f)
        p0("missed_cut", f, "no change at the planned cut",
           "the render does not cut here: check the segment order and the join frame (if both shots meet with "
           "under 6 grey levels of change the cut is unverifiable; list it as a jump cut)")

    for f in jumps:
        near = [i for i, e in enumerate(events) if i not in used and i not in accent_ok and abs(e["frame"] - f) <= 1]
        if near:
            used.add(min(near, key=lambda i: abs(events[i]["frame"] - f)))

    unplanned = [e for i, e in enumerate(events) if i not in used and i not in accent_ok]
    for e in unplanned:
        p0(f"unplanned_{e['kind']}", e["frame"], f"{e['len']}-frame {e['kind']} change, d {e['d']}",
           "an unexplained change: a sliver, a doubled segment, a part seam or a stray flash; fix the render, or "
           "add it to the plan (cuts, jump_cuts or accent_spans) when it is intended")

    # Slivers: the shot between two boundaries is shorter than 0.20 s and one boundary is unplanned.
    min_len = int(math.floor(SLIVER_S * fps + Fraction(1, 2)))
    bounds = sorted([(f, False) for f in cuts] + [(e["frame"], True) for e in unplanned])
    for (a, ua), (b, ub) in zip(bounds, bounds[1:]):
        if (ua or ub) and 0 < b - a < min_len:
            p0("sliver", a, f"{b - a}-frame shot {a}-{b - 1} between cuts (< {min_len} frames = 0.20 s)",
               "remove the sliver: move the join onto the cut (ref 03 section 2, Splices are cuts; no slivers)")

    findings.sort(key=lambda x: (x["rank"] != "P0", -1 if x["frame"] is None else x["frame"], x["id"]))
    return {"ok": not any(x["rank"] == "P0" for x in findings), "missing": missing,
            "unplanned": [{"frame": e["frame"], "len": e["len"], "kind": e["kind"]} for e in unplanned],
            "seam_confirmed": seam_confirmed, "findings": findings}


def _seam_confirms(diffs, f, r):
    """A planned cut with no event passes when some frame within +-1 changes by >= 6 and >= 4 x typical."""
    n_each = windows(r)[0]
    for i in (f - 1, f, f + 1):
        if 1 <= i < len(diffs):
            x = float(diffs[i])
            if x >= CONFIRM and x >= CONFIRM_RATIO * typical_of(neighbours(diffs, i, n_each)):
                return True
    return False


# ---------------------------------------------------------------- CLI

class _Parser(argparse.ArgumentParser):
    def error(self, message):  # keep the one-JSON-object stdout contract on usage errors
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
    ap = _Parser(description="Classified shot-cut detector and render cut gate (ref 04 section 2, ref 05 section 1).")
    ap.add_argument("video")
    ap.add_argument("--start", help="window start, source seconds")
    ap.add_argument("--end", help="window end, source seconds")
    ap.add_argument("--lead", default="0.5", help="seconds of context decoded around the window (default 0.5)")
    ap.add_argument("--fps", help="frame grid NUM/DEN (default: the stream rate)")
    ap.add_argument("--plan", help="plan.json in output frames: runs the events-vs-plan gate")
    ap.add_argument("--out", help="also write the JSON here (atomically)")
    ap.add_argument("--ffmpeg")
    ap.add_argument("--ffprobe", help="PATH or none")
    args = ap.parse_args()
    ffmpeg = cl.find_ffmpeg(args.ffmpeg)
    ffprobe = cl.find_ffprobe(ffmpeg, args.ffprobe)

    plan = None
    if args.plan:
        if args.start is not None or args.end is not None:
            raise cl.ClipError("usage", "--plan gates the whole render; drop --start/--end", exit_code=2)
        plan = cl.read_json(args.plan)
        plan_fps = check_plan(plan)[0]
        if args.fps is not None and cl.parse_rate(args.fps) != plan_fps:
            raise cl.ClipError("usage", f"--fps {args.fps} differs from plan.fps {plan.get('fps')}", exit_code=2)
        args.fps = cl.frac_str(plan_fps)

    res = detect(args.video, ffmpeg, args.start, args.end, args.fps, args.lead, ffprobe)
    for e in res["events"]:
        cl.log(f"f{e['frame']} t={e['t']:.3f}s {e['kind']} d={e['d']} typical={e['typical']} len={e['len']}")
    diffs = res.pop("diffs")
    res.pop("diffs_first")
    out = {"ok": True, "version": SCRIPT_VERSION, **res}
    if plan is not None:
        gate = match_plan(res["events"], plan, diffs)
        for x in gate["findings"]:
            cl.log(f"{x['rank']} {x['id']} f{x['frame']}: {x['measured']}" + (f" -> {x['fix']}" if x["fix"] else ""))
        out["gate"] = gate
        out["ok"] = gate["ok"]
    for w in out["warnings"]:
        cl.log(f"warning: {w}")
    if args.out:
        cl.write_json_atomic(args.out, out)
    cl.emit(out)
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    cl.run_main(main)
