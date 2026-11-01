"""cutlist.py - compile one clip's cut decisions into a frame-snapped cut list (ref 03 section 2).

Usage:
  python -P cutlist.py --transcript transcript.json --clips clips.json --rank N --facts source_facts.json
                       --out clips/NN/cutlist.json [--source SRC] [--keep-pauses] [--max-len 59.5]
                       [--shot-cuts cuts.json] [--ffmpeg PATH] [--ffprobe PATH|none]

What it does (ref 03 section 2, "One compiler per clip"):
  window   start_word.start - 0.05 s .. end_word.end + 0.15 s (ref 02), clamped to the source
  remove   the LLM's remove_words ranges and the safe fillers (um, umm, uh, uhh, uhm, er, erm), each
           maximal run of removed words as one span [first.start, last.end]
  dead air every gap >= 0.30 s between kept words (or kept sounds), unless --keep-pauses or the gap
           follows a word named in keep_gaps: remove [prev.end + 0.10, next.start - 0.10] when >= 0.10 s.
           With --source the source audio guards it: quiet = 10 ms block power <= median word-block
           power - 15 dB; an edge whose 30 ms ramp zone is loud moves 0.05 s away from its word (pad <= 0.20 s);
           a loud run >= 0.10 s outside every word (laugh, skipped word) and transcript suspect_gaps count
           as kept sound. Without --source the word gaps are trusted (warning quiet_test_skipped).
  pieces   kept pieces under 0.20 s are dropped when no kept word or sound starts in them, else grown.
  frames   boundaries snap to the canvas grid k = round(t * fps) (ref 03 section 2 "Frame grid").
  slivers  with --shot-cuts, a hard/soft source cut inside a segment's first/last 0.20 s becomes the edge
           when no kept word or sound overlaps the sliver (else warning sliver_kept).
  length   exit 1 (too_long, nothing written) when kept_s + freeze_s > --max-len.

Inputs:
  transcript.json {"words": [{"id": "w0", "text": " so", "start": s, "end": e}, ...], "suspect_gaps"?: [[s, e]]}
                  (source seconds; ids w<index> are assigned when missing; "word" is accepted for "text")
  clips.json      a list of candidates (or {"clips": [...]}); the one with rank == N gives start_word, end_word
                  ("w812" or 812), optional remove_words [[i, j], ...] (inclusive), keep_gaps [i, ...] (keep the
                  pause after word i), hook_line / payoff_line (the first / last 3 bare tokens must match the
                  words, fillers ignored) and freeze_s (a freeze hold that counts toward the length)
  source_facts    from probe_source.py: canvas_fps, duration, src
  cuts.json       cuts.py output ({"events": [{"t", "kind", ...}]} or a list of events); hard/soft/cut used
Output (--out, written atomically; the same object on stdout plus "out"):
  {"ok", "version", "src", "fps": "60/1", "sr": 48000,
   "window": {"start_word", "end_word", "start_s", "end_s"},
   "segments": [{"i", "k_in", "k_out", "frames", "out_frame", "src_in_s", "src_out_s"}], "frames", "kept_s",
   "removed": [{"start_s", "end_s", "why": "dead_air"|"filler"|"llm"|"sliver"}],
   "words": [{"id", "text", "start", "end"}] (output seconds), "sounds": [[s, e]], "params", "warnings"}
  k_in/k_out index the canvas-fps grid over source time (frame k = time k/fps); out_frame = earlier frames.
Exit codes: 0 ok; 1 a rule failed (too_long, bad_ids, id_text_mismatch, empty); 2 usage error or unreadable input.

Library (splice.py, the mix and caption steps):
  load(path) -> dict                       validated cut list
  remap(t_src, cut) -> float | None        source seconds -> output seconds (None inside a removal)
  remap_span(t0, t1, cut) -> (o0, o1)|None a word/duck span; the end clamps to the start's segment
  out_to_src_frame(f_out, cut) -> int      output frame -> canvas source frame (crop paths, face tracks)
  src_to_out_frame(k_src, cut) -> int|None canvas source frame -> output frame
  segments_from_frames(pairs, fps)         [(k_in, k_out), ...] -> segment dicts
  decode_mono(...)                         the pre-rolled mono 48 kHz decode shared with splice.py
"""
import argparse
import bisect
import math
import os
import re
import sys
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cliplib as cl  # noqa: E402

SCRIPT_VERSION = "1.0.0"
# Approach adapted from HyperFrames (github.com/heygen-com/hyperframes, Apache-2.0); independent Python implementation.

SR = 48000
US = 1_000_000                     # internal times are integer microseconds (no float drift in gap tests)
HEAD_PAD_US = 50_000               # ref 02: the clip starts 0.05 s before its first word ...
TAIL_PAD_US = 150_000              # ... and ends 0.15 s after its last word
MIN_GAP_US = 300_000               # ref 03 section 2 Dead air: gaps >= 0.30 s are cut ...
PAD_US = 100_000                   # ... from prev.end + 0.10 to next.start - 0.10
PAD_STEP_US = 50_000               # a loud ramp zone moves its edge 0.05 s away from the word ...
PAD_MAX_US = 200_000               # ... up to a 0.20 s pad
MIN_REMOVAL_US = 100_000           # removals under 0.10 s are skipped
SOUND_MIN_US = 100_000             # a loud run >= 0.10 s outside every word counts as a word
MIN_PIECE_US = 200_000             # kept pieces under 0.20 s are dropped or grown
RAMP_US = 30_000                   # the stem's 30 ms edge ramps (splice.py) sit in this zone
QUIET_DB = -15.0                   # quiet = block power <= median word-block power - 15 dB
BLOCK = 480                        # 10 ms at 48 kHz
FILLERS = {"um", "umm", "uh", "uhh", "uhm", "er", "erm"}   # ref 03 section 2 Fillers: safe list
CUT_KINDS = {"hard", "soft", "cut"}                        # flash / fast events never move an edge
WHY_ORDER = ("llm", "filler", "dead_air", "sliver")         # a removed span is named by its first cause here
# 5.0/5.1/6.x/7.x layouts carry dialogue in FC, the third channel; it joins FL/FR in the mono fold.
FC_LAYOUTS = {"3.0", "4.0", "5.0", "5.0(side)", "5.1", "5.1(side)", "6.0", "6.1", "6.1(back)", "7.0", "7.1",
              "7.1(wide)", "7.1(wide-side)"}


# ---------------------------------------------------------------- small helpers

def us(t):
    return int(round(float(t) * US))


def s6(u):
    return round(u / US, 6)


def rnd(x):
    """Round half up (a Fraction or int); the one rounding rule for frames and sample positions."""
    return math.floor(Fraction(x) + Fraction(1, 2))


def snap(u, fps):
    """Boundary convention (ref 03 section 2 Frame grid): the nearest frame edge, k = round(t * fps)."""
    return rnd(Fraction(u, US) * fps)


def frame_us(k, fps):
    return Fraction(k) / fps * US


def bare(text):
    """Lower-case token without leading/trailing punctuation (curly apostrophes folded to ')."""
    return re.sub(r"^[\W_]+|[\W_]+$", "", str(text).lower().replace("\u2019", "'"))


def _tokens(text):
    return [b for b in (bare(t) for t in str(text).split()) if b and b not in FILLERS]


# ---------------------------------------------------------------- library API

def segments_from_frames(pairs, fps):
    """[(k_in, k_out), ...] (increasing, non-touching) -> cut-list segment dicts with output offsets."""
    fps = Fraction(fps)
    segs, o = [], 0
    for i, (k_in, k_out) in enumerate(pairs):
        n = int(k_out) - int(k_in)
        segs.append({"i": i, "k_in": int(k_in), "k_out": int(k_out), "frames": n, "out_frame": o,
                     "src_in_s": round(float(Fraction(k_in) / fps), 6),
                     "src_out_s": round(float(Fraction(k_out) / fps), 6)})
        o += n
    return segs


def load(path):
    """Read and validate a cut list (segments ordered, frame counts and offsets consistent)."""
    cut = cl.read_json(path)
    _validate(cut, str(path))
    return cut


def _validate(cut, where):
    def bad(msg):
        raise cl.ClipError("bad_cutlist", f"{where}: {msg}", hint="rebuild it with cutlist.py", exit_code=2)

    if not isinstance(cut, dict):
        bad("not a JSON object")
    fps = cl.parse_rate(cut.get("fps"))
    if not fps or fps <= 0:
        bad(f"bad fps {cut.get('fps')!r}")
    segs = cut.get("segments")
    if not isinstance(segs, list) or not segs:
        bad("no segments")
    o, prev_out = 0, None
    for s in segs:
        try:
            k_in, k_out, n, of = (int(s[k]) for k in ("k_in", "k_out", "frames", "out_frame"))
        except (KeyError, TypeError, ValueError):
            bad(f"segment {s!r} lacks integer k_in/k_out/frames/out_frame")
        if n <= 0 or k_out - k_in != n or of != o or k_in < 0 or (prev_out is not None and k_in <= prev_out):
            bad(f"segment {s!r} is inconsistent (frames = k_out - k_in > 0, out_frame = running sum, "
                f"increasing and not touching the previous one)")
        o += n
        prev_out = k_out
    if cut.get("frames") is not None and int(cut["frames"]) != o:
        bad(f"frames {cut['frames']} != sum of segment frames {o}")


def _exact(t):
    """Seconds as an exact Fraction at microsecond precision (JSON times carry 6 decimals)."""
    return Fraction(us(t), US)


def _seg_at(x, segs):
    """Index of the segment holding canvas position x (k_in <= x < k_out), or None."""
    i = bisect.bisect_right([s["k_in"] for s in segs], x) - 1
    if i < 0 or x >= segs[i]["k_out"]:
        return None
    return i


def remap(t_src, cut):
    """Source seconds -> output seconds, (o + t*fps - k_in)/fps for the segment holding t; None in a removal."""
    fps = cl.parse_rate(cut["fps"])
    t = _exact(t_src)
    i = _seg_at(t * fps, cut["segments"])
    if i is None:
        return None
    s = cut["segments"][i]
    return float(t + Fraction(s["out_frame"] - s["k_in"]) / fps)


def remap_span(t0, t1, cut):
    """(start, end) in output seconds for a source span; None when the start is removed.

    The end clamps to the end of the segment that holds the start (ref 03 section 2 One clock)."""
    fps = cl.parse_rate(cut["fps"])
    a, b = _exact(t0), _exact(t1)
    i = _seg_at(a * fps, cut["segments"])
    if i is None:
        return None
    s = cut["segments"][i]
    off = Fraction(s["out_frame"] - s["k_in"]) / fps
    b = min(max(a, b), Fraction(s["k_out"]) / fps)
    return float(a + off), float(b + off)


def out_to_src_frame(f_out, cut):
    segs = cut["segments"]
    f = int(f_out)
    i = bisect.bisect_right([s["out_frame"] for s in segs], f) - 1
    if i < 0 or f >= segs[i]["out_frame"] + segs[i]["frames"]:
        raise cl.ClipError("frame_out_of_range", f"output frame {f_out} is outside the cut (0..{cut_frames(cut) - 1})")
    return segs[i]["k_in"] + f - segs[i]["out_frame"]


def src_to_out_frame(k_src, cut):
    segs = cut["segments"]
    i = _seg_at(int(k_src), segs)
    if i is None:
        return None
    return segs[i]["out_frame"] + int(k_src) - segs[i]["k_in"]


def cut_frames(cut):
    return sum(s["frames"] for s in cut["segments"])


def mono_pan(channels, layout=None):
    """pan filter folding the source to mono; never -ac (its gain differs by 3 dB between s16 and f32)."""
    if channels == 1:
        return "pan=mono|c0=c0"
    if channels and channels > 2 and (layout or "").strip() in FC_LAYOUTS:
        return "pan=mono|c0=0.5*c0+0.5*c1+0.7071*c2"
    return "pan=mono|c0=0.5*c0+0.5*c1"


def decode_mono(src, ffmpeg, start_sample, n_samples, channels, layout=None):
    """Float32 mono 48 kHz samples [start_sample, start_sample + n_samples) of the source's first audio stream.

    ONE pre-rolled decode (ref 03 section 2 Dialogue stem): seek to a whole second P = floor(t0) - 1, then trim
    by sample index, so an AAC decoder is warm and sample k is source time k / 48000. aresample async=1:first_pts=0
    keeps a late-starting audio stream on the video's clock, like the ASR decode. May return fewer samples when
    the source audio ends early (callers pad and warn)."""
    import numpy as np
    p = max(0, start_sample // SR - 1)
    s0 = start_sample - p * SR
    af = f"aresample={SR}:async=1:first_pts=0,{mono_pan(channels, layout)},atrim=start_sample={s0}:end_sample={s0 + n_samples}"
    cmd = [ffmpeg, "-v", "error", "-nostdin"]
    if p > 0:
        cmd += ["-ss", cl.t6(p)]
    cmd += ["-i", str(src), "-map", "0:a:0", "-vn", "-af", af, "-f", "f32le", "-acodec", "pcm_f32le", "-"]
    raw = cl.run(cmd, binary=True).stdout
    return np.frombuffer(raw, dtype="<f4").copy()


def source_audio(src, ffmpeg, ffprobe):
    """(channels, layout) of the first audio stream; exit 2 when there is none."""
    info = cl.probe(src, ffmpeg, ffprobe)
    a = info.get("audio")
    if not a:
        raise cl.ClipError("no_audio", f"{src} has no audio stream", hint="pass the downloaded A+V source", exit_code=2)
    return a.get("channels"), a.get("layout")


# ---------------------------------------------------------------- inputs

def load_words(path):
    """(words, suspect_gaps, skipped): words as {"id", "text", "s", "e"} in microseconds; empty, malformed or
    non-finite entries are skipped (counted) and the others keep ids from their original index."""
    data = cl.read_json(path)
    raw = data.get("words") if isinstance(data, dict) else data
    if not isinstance(raw, list):
        raise cl.ClipError("bad_transcript", f"{path}: no word list", hint='expected {"words": [...]}', exit_code=2)
    words, prev, skipped = [], None, 0
    for i, w in enumerate(raw):
        try:
            text = w.get("text", w.get("word"))
            start, end = float(w["start"]), float(w["end"])
        except (AttributeError, KeyError, TypeError, ValueError):
            skipped += 1
            continue
        if text is None or not str(text).strip() or not (math.isfinite(start) and math.isfinite(end)):
            skipped += 1
            continue
        wid = str(w.get("id") or f"w{i}")
        if prev is not None and us(start) < prev:
            raise cl.ClipError("bad_transcript", f"{path}: word {wid} starts before the previous word",
                               hint="word starts must be non-decreasing (ref 03 section 1 Normalise words)",
                               exit_code=2)
        prev = us(start)
        words.append({"id": wid, "text": str(text), "s": us(start), "e": max(us(start), us(end))})
    ids = [w["id"] for w in words]
    if len(set(ids)) != len(ids):
        raise cl.ClipError("bad_transcript", f"{path}: duplicate word ids", exit_code=2)
    gaps = (data.get("suspect_gaps") or []) if isinstance(data, dict) else []
    try:
        suspect = [(us(a), us(b)) for a, b in gaps if float(b) > float(a)]
    except (TypeError, ValueError):
        raise cl.ClipError("bad_transcript", f"{path}: suspect_gaps must be [[start, end], ...]", exit_code=2)
    return words, suspect, skipped


def pick_candidate(path, rank):
    data = cl.read_json(path)
    items = data.get("clips") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise cl.ClipError("bad_clips", f"{path}: expected a list of candidates", exit_code=2)
    for c in items:
        try:
            if isinstance(c, dict) and int(c.get("rank")) == rank:
                return c
        except (TypeError, ValueError):
            continue
    raise cl.ClipError("bad_clips", f"{path}: no candidate with rank {rank}", exit_code=2)


def _word_key(ref, field):
    if isinstance(ref, bool) or ref is None:
        raise cl.ClipError("bad_clips", f"{field} is missing or not a word id: {ref!r}", exit_code=2)
    if isinstance(ref, int):
        return f"w{ref}"
    m = re.fullmatch(r"\s*w?(\d+)\s*", str(ref))
    if not m:
        raise cl.ClipError("bad_clips", f"{field} {ref!r} is not a word id like 'w812' or 812", exit_code=2)
    return f"w{int(m.group(1))}"


def resolve_ids(cand, words):
    """Positions (s, e, [(i, j)], keep_gap_ids) of the candidate's word ids; exit 1 bad_ids on a rule failure."""
    pos = {w["id"]: k for k, w in enumerate(words)}

    def at(ref, field):
        key = _word_key(ref, field)
        if key not in pos:
            raise cl.ClipError("bad_ids", f"{field} {ref!r}: no word {key} in the transcript (ids w0..w{len(words) - 1})",
                               hint="use the [wA-wB] ids printed in transcript_lines.txt")
        return pos[key]

    s, e = at(cand.get("start_word"), "start_word"), at(cand.get("end_word"), "end_word")
    if s > e:
        raise cl.ClipError("bad_ids", f"start_word {words[s]['id']} comes after end_word {words[e]['id']}")
    ranges = []
    for r in cand.get("remove_words") or []:
        if not isinstance(r, (list, tuple)) or len(r) != 2:
            raise cl.ClipError("bad_clips", f"remove_words entry {r!r} is not [i, j]", exit_code=2)
        i, j = at(r[0], "remove_words"), at(r[1], "remove_words")
        if i > j:
            raise cl.ClipError("bad_ids", f"remove_words range {r!r} is reversed")
        if not (s < i and j < e):
            raise cl.ClipError("bad_ids", f"remove_words range {r!r} is not strictly inside "
                               f"({words[s]['id']}, {words[e]['id']})", hint="move start_word/end_word instead")
        ranges.append((i, j))
    ranges.sort()
    for (i0, j0), (i1, j1) in zip(ranges, ranges[1:]):
        if i1 <= j0:
            raise cl.ClipError("bad_ids", f"remove_words ranges [{words[i0]['id']}, {words[j0]['id']}] and "
                               f"[{words[i1]['id']}, {words[j1]['id']}] overlap")
    keep = set()
    for g in cand.get("keep_gaps") or []:
        k = at(g, "keep_gaps")
        if not s <= k < e:
            raise cl.ClipError("bad_ids", f"keep_gaps id {g!r} is outside the clip")
        keep.add(k)
    return s, e, ranges, keep


def check_lines(cand, words, s, e):
    """hook_line / payoff_line must match the first / last 3 bare tokens of the picked words (fillers ignored)."""
    span = [t for w in words[s:e + 1] for t in _tokens(w["text"])]
    for field, head in (("hook_line", True), ("payoff_line", False)):
        line = cand.get(field)
        if not line:
            continue
        want = _tokens(line)
        want = want[:3] if head else want[-3:]
        if not want:
            continue
        got = span[:len(want)] if head else span[-len(want):]
        if got != want:
            wid = words[s]["id"] if head else words[e]["id"]
            raise cl.ClipError("id_text_mismatch",
                               f"{field} {' '.join(want)!r} does not match the words at {wid}: {' '.join(got)!r}",
                               hint=f"point {'start_word' if head else 'end_word'} at the line's "
                                    f"{'first' if head else 'last'} word")


def load_shot_cuts(path, fps):
    """Canvas frame boundaries of the hard/soft cuts in a cuts.py result (time t -> round(t * fps))."""
    data = cl.read_json(path)
    events = data.get("events") if isinstance(data, dict) else data
    if not isinstance(events, list):
        raise cl.ClipError("bad_shot_cuts", f"{path}: no event list", exit_code=2)
    out = []
    for ev in events:
        if not isinstance(ev, dict) or str(ev.get("kind", "")).lower() not in CUT_KINDS:
            continue
        if ev.get("t") is None:
            raise cl.ClipError("bad_shot_cuts", f"{path}: event {ev!r} has no source time t", exit_code=2)
        out.append(snap(us(ev["t"]), fps))
    return sorted(set(out))


# ---------------------------------------------------------------- the quiet test

class Loudness:
    """Power of the source audio over the clip window: 10 ms blocks and exact spans (mean of x^2)."""

    def __init__(self, x, i0):
        import numpy as np
        self.i0 = i0
        self.c = np.concatenate(([0.0], np.cumsum(np.square(x, dtype=np.float64))))
        n = len(x) // BLOCK
        self.block = (self.c[BLOCK:n * BLOCK + 1:BLOCK] - self.c[0:n * BLOCK:BLOCK]) / BLOCK

    def idx(self, u):
        return min(max(rnd(Fraction(u * SR, US)) - self.i0, 0), len(self.c) - 1)

    def span(self, a, b):
        i, j = self.idx(a), self.idx(b)
        return float((self.c[j] - self.c[i]) / (j - i)) if j > i else 0.0

    def block_us(self, b):
        return rnd(Fraction((self.i0 + b * BLOCK) * US, SR))


def _subtract(pieces, holes):
    """Interval difference: parts of `pieces` outside every hole (all (a, b) in microseconds)."""
    out = []
    for a, b in pieces:
        cur = [(a, b)]
        for ha, hb in holes:
            nxt = []
            for x, y in cur:
                if hb <= x or ha >= y:
                    nxt.append((x, y))
                    continue
                if x < ha:
                    nxt.append((x, ha))
                if hb < y:
                    nxt.append((hb, y))
            cur = nxt
        out.extend(cur)
    return out


def _merge(iv):
    out = []
    for a, b in sorted(iv):
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def loud_sounds(loud, thr, window_words, removed_spans):
    """Loud runs (1-block holes bridged) outside every word and removed span, >= 0.10 s: kept as sound."""
    on = loud.block > thr
    if len(on) > 2:
        bridge = on[:-2] & on[2:]
        on[1:-1] |= bridge
    runs, b = [], 0
    while b < len(on):
        if on[b]:
            c = b
            while c < len(on) and on[c]:
                c += 1
            runs.append((loud.block_us(b), loud.block_us(c)))
            b = c
        else:
            b += 1
    holes = [(w["s"], w["e"]) for w in window_words] + list(removed_spans)
    return [(a, b) for a, b in _subtract(runs, holes) if b - a >= SOUND_MIN_US] if runs else []


def quiet_threshold(loud, kept_words):
    """Median power of the 10 ms blocks inside kept words, minus 15 dB (ref 03 section 2 Dead air)."""
    import numpy as np
    n = len(loud.block)
    mask = np.zeros(n, bool)
    for w in kept_words:
        b0 = math.ceil((Fraction(w["s"] * SR, US) - loud.i0) / BLOCK)
        b1 = math.floor((Fraction(w["e"] * SR, US) - loud.i0) / BLOCK)
        mask[max(b0, 0):min(b1, n)] = True
    if not mask.any():  # words shorter than a block: use the blocks they touch
        for w in kept_words:
            b0 = math.floor((Fraction(w["s"] * SR, US) - loud.i0) / BLOCK)
            b1 = math.ceil((Fraction(w["e"] * SR, US) - loud.i0) / BLOCK)
            mask[max(b0, 0):min(b1, n)] = True
    med = float(np.median(loud.block[mask])) if mask.any() else 0.0
    return med * 10 ** (QUIET_DB / 10), med


# ---------------------------------------------------------------- the compiler

def removed_runs(words, s, e, ranges):
    """{position: why} of the removed words (LLM ranges, safe fillers) and one (start, end, why) per maximal run.

    A run is removed as one span; the dead-air pass then joins the pauses around it (pause + "um" + pause =
    one splice, ref 03 section 2 Fillers)."""
    why = {k: "llm" for i, j in ranges for k in range(i, j + 1)}
    for k in range(s, e + 1):
        if k not in why and bare(words[k]["text"]) in FILLERS:
            why[k] = "filler"
    runs, k = [], s
    while k <= e:
        if k not in why:
            k += 1
            continue
        j = k
        while j + 1 <= e and j + 1 in why:
            j += 1
        kind = "llm" if any(why[x] == "llm" for x in range(k, j + 1)) else "filler"
        runs.append((words[k]["s"], words[j]["e"], kind))
        k = j + 1
    return why, runs


def dead_air(items, keep_gaps, loud, thr):
    """Removals in the gaps >= 0.30 s between consecutive kept items (ref 03 section 2 Dead air)."""
    out = []
    for (_, pe, pk), (ns, _, _) in zip(items, items[1:]):
        if (pk is not None and pk in keep_gaps) or ns - pe < MIN_GAP_US:
            continue
        a, b = pe + PAD_US, ns - PAD_US
        if loud is not None:  # a loud 30 ms ramp zone moves its edge away from the word, up to a 0.20 s pad
            while a - pe < PAD_MAX_US and loud.span(a - RAMP_US, a) > thr:
                a += PAD_STEP_US
            while ns - b < PAD_MAX_US and loud.span(b, b + RAMP_US) > thr:
                b -= PAD_STEP_US
        if b - a >= MIN_REMOVAL_US:
            out.append((a, b, "dead_air"))
    return out


def kept_pieces(removals, A, B, has_start, warnings):
    """The window minus the removals; a piece under 0.20 s is dropped unless a kept word/sound starts in it."""
    pieces, cur = [], A
    for a, b in _merge([(a, b) for a, b, _ in removals]):
        if a > cur:
            pieces.append((cur, a))
        cur = max(cur, b)
    if cur < B:
        pieces.append((cur, B))
    out = []
    for a, b in pieces:
        if b - a >= MIN_PIECE_US:
            out.append((a, b))
        elif has_start(a, b):
            nb = min(B, a + MIN_PIECE_US)
            out.append((max(A, nb - MIN_PIECE_US), nb))
            warnings.append(f"short_piece_grown@{s6(a)}: a {s6(b - a)} s piece holding a word start grew to 0.20 s")
    return _merge(out)


def min_frames(fps):
    return math.ceil(Fraction(MIN_PIECE_US, US) * fps)


def snap_segments(pieces, fps, k_min, k_max, has_start, warnings):
    """Pieces -> (k_in, k_out) on the canvas grid inside [k_min, k_max]; touching ones merge and the 0.20 s
    minimum is re-applied in frames."""
    m = min_frames(fps)

    def merge(pairs):
        out = []
        for a, b in sorted(pairs):
            a, b = max(a, k_min), min(b, k_max)
            if b <= a:
                continue
            if out and a <= out[-1][1]:
                out[-1] = (out[-1][0], max(out[-1][1], b))
            else:
                out.append((a, b))
        return out

    out = []
    for a, b in merge([(snap(a, fps), snap(b, fps)) for a, b in pieces]):
        if b - a >= m:
            out.append((a, b))
        elif has_start(frame_us(a, fps), frame_us(b, fps)):
            nb = min(k_max, a + m)
            out.append((max(k_min, nb - m), nb))
            warnings.append(f"short_piece_grown@{s6(frame_us(a, fps))}: a {b - a}-frame segment holding a word "
                            f"start grew to {m} frames")
    return merge(out)


def move_slivers(segs, shot_cuts, items, fps, warnings):
    """A hard/soft source cut in a segment's first/last 0.20 s becomes its edge when no kept word or sound
    overlaps the sliver and >= 0.20 s remain; else warning sliver_kept (ref 03 section 2 No slivers at
    splices). Returns (segments, [(start_us, end_us, "sliver")])."""
    m = min_frames(fps)

    def busy(ka, kb):
        lo, hi = frame_us(ka, fps), frame_us(kb, fps)
        return any(a < hi and b > lo for a, b, _ in items)

    out, slivers = [], []
    for idx, (a, b) in enumerate(segs):
        head = [c for c in shot_cuts if a < c < a + m]
        if head:
            c = max(head)
            if not busy(a, c) and b - c >= m:
                slivers.append((frame_us(a, fps), frame_us(c, fps), "sliver"))
                a = c
            else:
                warnings.append(f"sliver_kept@{s6(frame_us(c, fps))}: a source cut {c - a} frames after "
                                f"segment {idx}'s start")
        tail = [c for c in shot_cuts if b - m < c < b]
        if tail:
            c = min(tail)
            if not busy(c, b) and c - a >= m:
                slivers.append((frame_us(c, fps), frame_us(b, fps), "sliver"))
                b = c
            else:
                warnings.append(f"sliver_kept@{s6(frame_us(c, fps))}: a source cut {b - c} frames before "
                                f"segment {idx}'s end")
        out.append((a, b))
    return out, slivers


def name_removed(segs, k_min, k_max, causes, fps):
    """The window minus the segments, in source seconds. A span holding a removed word is named by it (llm
    before filler), else dead_air, else sliver; a dropped short piece counts as dead air."""
    gaps, cur = [], k_min
    for a, b in segs:
        if a > cur:
            gaps.append((cur, a))
        cur = b
    if k_max > cur:
        gaps.append((cur, k_max))
    removed = []
    for ga, gb in gaps:
        lo, hi = frame_us(ga, fps), frame_us(gb, fps)
        share = {w: 0 for w in WHY_ORDER}
        for a, b, w in causes:
            share[w] += max(0, min(b, hi) - max(a, lo))
        why = next((w for w in WHY_ORDER if share[w] > 0), "dead_air")
        removed.append({"start_s": round(float(lo / US), 6), "end_s": round(float(hi / US), 6), "why": why})
    return removed


def compile_cut(words, suspect, cand, fps, duration_us, loud_src, keep_pauses, shot_cuts):
    """Return (cut dict without ok/version/src, warnings). loud_src: callable (A, B) -> Loudness, or None."""
    warnings = []
    s, e, ranges, keep_gaps = resolve_ids(cand, words)
    check_lines(cand, words, s, e)

    # Window: ref 02 pads, clamped to the source.
    A = max(0, words[s]["s"] - HEAD_PAD_US)
    B = words[e]["e"] + TAIL_PAD_US
    if duration_us is not None:
        B = min(B, duration_us)
    if B <= A:
        raise cl.ClipError("empty", "the clip window is empty")

    why, runs = removed_runs(words, s, e, ranges)
    kept = [k for k in range(s, e + 1) if k not in why]
    if not kept:
        raise cl.ClipError("empty", "every word of the clip is removed", hint="check remove_words and the picks")
    run_spans = [(a, b) for a, b, _ in runs]

    # Kept sound: transcript suspect_gaps (ref 03 section 1: never dead air) and loud runs outside words.
    loud = loud_src(A, B) if loud_src else None
    thr = None
    sounds = [(max(a, A), min(b, B)) for a, b in suspect if b > A and a < B]
    if loud is not None:
        thr, med = quiet_threshold(loud, [words[k] for k in kept])
        if med < 1e-8:
            warnings.append("words_silent: the kept words' audio is below -80 dB; transcript and source may be "
                            "misaligned (check asr_offset_s in source_facts.json)")
        sounds += loud_sounds(loud, thr, words[s:e + 1], run_spans)
    else:
        warnings.append("quiet_test_skipped: no --source, dead-air removals trust the word gaps")
    sounds = _merge(_subtract(sounds, run_spans))
    items = sorted([(words[k]["s"], words[k]["e"], k) for k in kept] + [(a, b, None) for a, b in sounds],
                   key=lambda it: (it[0], it[1]))

    removals = list(runs) + ([] if keep_pauses else dead_air(items, keep_gaps, loud, thr))
    for k in sorted(keep_gaps):
        if k in why:
            warnings.append(f"keep_gaps_removed_word: {words[k]['id']} is removed, its keep_gaps entry does nothing")
    # A removed first/last word: the clip starts/ends on the first/last kept word with the ref 02 pads.
    if kept[0] != s:
        removals.append((A, words[kept[0]]["s"] - HEAD_PAD_US, why[s]))
    if kept[-1] != e:
        removals.append((words[kept[-1]]["e"] + TAIL_PAD_US, B, why[e]))
    removals = [(max(a, A), min(b, B), w) for a, b, w in removals if min(b, B) > max(a, A)]

    starts = sorted([words[k]["s"] for k in kept] + [a for a, _ in sounds])

    def has_start(a, b):
        i = bisect.bisect_left(starts, a)
        return i < len(starts) and starts[i] < b

    k_min, k_max = snap(A, fps), snap(B, fps)
    if duration_us is not None:
        k_max = min(k_max, math.floor(Fraction(duration_us, US) * fps))
    segs = snap_segments(kept_pieces(removals, A, B, has_start, warnings), fps, k_min, k_max, has_start, warnings)
    segs, slivers = move_slivers(segs, shot_cuts, items, fps, warnings)
    if not segs:
        raise cl.ClipError("empty", "no kept segment survives the 0.20 s minimum")

    segments = segments_from_frames(segs, fps)
    total = sum(x["frames"] for x in segments)
    cut = {"fps": cl.frac_str(fps), "sr": SR,
           "window": {"start_word": words[s]["id"], "end_word": words[e]["id"], "start_s": s6(A), "end_s": s6(B)},
           "segments": segments, "frames": total, "kept_s": round(float(total / fps), 6),
           "removed": name_removed(segs, k_min, k_max, removals + slivers, fps)}
    out_words = []
    for k in kept:  # One clock: a word starting in a removal drops, an end crossing k_out clamps
        w = words[k]
        span = remap_span(w["s"] / US, w["e"] / US, cut)
        if span is None:
            warnings.append(f"word_dropped@{s6(w['s'])}: kept word {w['id']} starts inside a removal")
            continue
        out_words.append({"id": w["id"], "text": w["text"], "start": round(span[0], 6), "end": round(span[1], 6)})
    cut["words"] = out_words
    cut["sounds"] = [[s6(a), s6(b)] for a, b in sounds]
    cut["params"] = {"head_pad_s": s6(HEAD_PAD_US), "tail_pad_s": s6(TAIL_PAD_US), "min_gap_s": s6(MIN_GAP_US),
                     "pad_s": s6(PAD_US), "pad_max_s": s6(PAD_MAX_US), "min_removal_s": s6(MIN_REMOVAL_US),
                     "min_piece_s": s6(MIN_PIECE_US), "quiet_db": QUIET_DB, "ramp_s": s6(RAMP_US),
                     "quiet_test": loud is not None, "quiet_power": thr, "keep_pauses": bool(keep_pauses),
                     "fillers": sorted(FILLERS)}
    return cut, warnings


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
    ap = _Parser(description="Compile one clip's cut decisions into a frame-snapped cutlist.json (ref 03 section 2).")
    ap.add_argument("--transcript", required=True)
    ap.add_argument("--clips", required=True)
    ap.add_argument("--rank", required=True, type=int)
    ap.add_argument("--facts", required=True, help="source_facts.json (canvas_fps, duration)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--source", help="the source media; enables the quiet test on its audio")
    ap.add_argument("--keep-pauses", action="store_true", help="skip the dead-air pass")
    ap.add_argument("--max-len", type=float, default=59.5)
    ap.add_argument("--shot-cuts", help="cuts.py output for the clip window (sliver rule)")
    ap.add_argument("--ffmpeg")
    ap.add_argument("--ffprobe", help="PATH or none")
    args = ap.parse_args()

    facts = cl.read_json(args.facts)
    fps = cl.parse_rate(facts.get("canvas_fps")) if isinstance(facts, dict) else None
    if not fps or fps <= 0:
        raise cl.ClipError("bad_facts", f"{args.facts}: no canvas_fps", hint="run probe_source.py first", exit_code=2)
    duration = facts.get("duration")
    duration_us = us(duration) if duration else None
    words, suspect, skipped = load_words(args.transcript)
    cand = pick_candidate(args.clips, args.rank)
    try:
        freeze = float(cand.get("freeze_s") or 0.0)
    except (TypeError, ValueError):
        raise cl.ClipError("bad_clips", f"freeze_s {cand.get('freeze_s')!r} is not a number of seconds", exit_code=2)
    shot_cuts = load_shot_cuts(args.shot_cuts, fps) if args.shot_cuts else []

    loud_src = None
    if args.source:
        ffmpeg = cl.find_ffmpeg(args.ffmpeg)
        ffprobe = cl.find_ffprobe(ffmpeg, args.ffprobe)
        channels, layout = source_audio(args.source, ffmpeg, ffprobe)

        def loud_src(a, b):
            i0, i1 = rnd(Fraction(a * SR, US)), rnd(Fraction(b * SR, US))
            x = decode_mono(args.source, ffmpeg, i0, i1 - i0, channels, layout)
            cl.log(f"quiet test: {len(x) / SR:.2f} s of source audio from {a / US:.3f} s")
            return Loudness(x, i0)

    cut, warnings = compile_cut(words, suspect, cand, fps, duration_us, loud_src, args.keep_pauses, shot_cuts)
    if skipped:
        warnings.insert(0, f"transcript_entries_skipped: {skipped} empty or malformed word entries were ignored")
    length = cut["kept_s"] + freeze
    if length > args.max_len:
        over = round(length - args.max_len, 6)
        cl.emit({"ok": False, "version": SCRIPT_VERSION,
                 "error": {"code": "too_long", "message": f"kept {cut['kept_s']:.3f} s + freeze {freeze:.3f} s is "
                                                          f"{over:.3f} s over --max-len {args.max_len}",
                           "hint": "ref 02 rule 5: use an earlier payoff, cut the middle tangent (remove_words) "
                                   "or drop the candidate"},
                 "kept_s": cut["kept_s"], "freeze_s": freeze, "max_len": args.max_len, "over_s": over})
        cl.log(f"too_long: {over:.3f} s over {args.max_len} s; nothing written")
        return 1

    cut = {"ok": True, "version": SCRIPT_VERSION, "src": args.source or facts.get("src"), **cut, "warnings": warnings}
    cl.write_json_atomic(args.out, cut)
    for w in warnings:
        cl.log("warning:", w)
    cl.log(f"cutlist: {len(cut['segments'])} segments, {cut['frames']} frames, {cut['kept_s']:.3f} s -> {args.out}")
    cl.emit({**cut, "out": str(args.out)})
    return 0


if __name__ == "__main__":
    cl.run_main(main)
