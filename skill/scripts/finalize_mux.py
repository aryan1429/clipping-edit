"""Fit the master mix to the rendered picture, encode AAC once, copy-mux, and gate a clip for delivery.

The last step of every clip (ref 03 section 4). The picture is the clock: the video's decoded frame count N
and its exact frame rate set the audio length, round(N * 48000 / fps) samples. The float master mix
(mix_audio.py) is zero-padded or trimmed to that length in numpy and encoded to AAC exactly once, as an .m4a,
so that the encoder priming lands in an edit list. True peak is checked after the codec; when it is over the
ceiling, the PCM is re-encoded lower, at most 3 times. The AAC is then copy-muxed with the video: explicit
maps, no inherited metadata, faststart, and BT.709 (or BT.601) tags in both the H.264 VUI and the MP4 colr box.
The mux never uses -shortest or -avoid_negative_ts. The muxed file is written under a staged name, run through
the delivery gate, and only then renamed onto --out.

Usage:
  python -P finalize_mux.py --video clips/NN/video.mp4 --mix clips/NN/mix.wav --out edited/NN-slug.mp4
         [--fps 60] [--frames N] [--tag 709tv|601tv|none] [--max-dur 59.5] [--ffmpeg PATH] [--ffprobe PATH|none]
  python -P finalize_mux.py --check FILE [--fps 60] [--frames N] [--tag 709tv|601tv|none] [--max-dur 59.5]
         [--ffmpeg PATH] [--ffprobe PATH|none]

Inputs:
  --video     The video-only MP4 from EffectCraft or the fallback encode: H.264 yuv420p on one frame grid (CFR).
              Any audio track in it is ignored (explicit -map).
  --mix       The master mix: mono or stereo audio in any format ffmpeg reads (mix_audio.py writes float
              stereo 48 kHz).
  --fps       The expected frame rate (60, 30, 30000/1001 ...). By default the video's own rate is used; when
              --fps is given, the video must match it.
  --frames    The expected frame count (the plan's N). The decoded count must equal it.
  --tag       The colour tags written at the mux and required by the gate (default 709tv).
              601tv = BT.601 matrix with BT.709 primaries and transfer.
              none = keep the video's own tags (the gate then only reports them).
  --max-dur   The longest allowed clip, as N/fps seconds (default 59.5).
  --check FILE  Run the delivery gate alone on an existing file.

Delivery gate (both modes; one entry per check in "gate"): faststart, streams, metadata, frames, fps,
first_pts, audio_priming, av_length, colr, vui, decode_errors, black_tail, max_dur, true_peak.

Output: one JSON object on stdout:
  {"ok", "version", "out", "frames", "fps": "num/den",
   "audio": {"samples", "tp_dbtp", "lowered_db", "passes": [{"pass", "tp_dbtp", "att_db"}], "mix_samples", "fit"},
   "gate": {name: {"ok", "measured", "limit"}}, "staged"}
  In mux mode, "staged" names the staged file kept after a failed gate (else null). When the gate passed but
  --out is held open by another program (Windows), the gated file stays under its staged name and "error" says
  why. In --check mode the audio block holds only the measured true peak.
  Logs, including a fix hint for every failed gate, go to stderr.
Exit codes:
  0  delivered (or the gate passed)
  1  a step or gate failed (the JSON says which). A staged file that failed the gate is kept for inspection;
     --out is never touched.
  2  usage error or unreadable input
"""
import argparse
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
from fractions import Fraction
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cliplib as cl  # noqa: E402

SCRIPT_VERSION = "1.0.0"
# Approach adapted from HyperFrames (github.com/heygen-com/hyperframes, Apache-2.0); independent Python implementation.

SR = 48000                                            # delivery sample rate
AAC_ARGS = ["-c:a", "aac", "-b:a", "192k", "-ar", str(SR)]   # ref 03 §4 One AAC encode, copied at the mux
TP_CEILING = -1.0             # dBTP on the encoded AAC (ref 03 §3 True peak after AAC)
TP_HEADROOM_DB = 0.5          # correction pass k aims 0.5 * 2**k dB under the ceiling (an AAC re-encode can stall)
TP_MAX_PASSES = 3             # correction re-encodes before the step fails
AV_TOL = Fraction(1, 1000)    # |audio edit - N/fps| in seconds (ref 03 §4 Mux gate)
AAC_FRAME = 1024              # samples per AAC frame: the allowance when the length must come from decoding
FIRST_PTS_TOL = 0.001         # seconds
TAIL = Fraction(1, 10)        # the last 0.1 s must not be black
BLACKDETECT = "blackdetect=d=0:pix_th=0.10:pic_th=0.98"
STALL_S = 180                 # kill ffmpeg only after this long without progress (ref 03 §4 Windows-safe ffmpeg)
ALLOWED_TAGS = {"major_brand", "minor_version", "compatible_brands", "encoder", "title"}

# --tag -> ((colour_primaries, transfer_characteristics, matrix_coefficients, video_full_range_flag), container
# flags). On a copy-mux the h264_metadata bsf writes only the VUI and the flags only the colr box, so both are
# needed (ref 03 §4 EffectCraft colour). 601tv keeps BT.709 primaries and transfer; only the matrix changes.
TAGS = {
    "709tv": ((1, 1, 1, 0), ["-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
                             "-color_range", "tv"]),
    "601tv": ((1, 1, 6, 0), ["-colorspace", "smpte170m", "-color_primaries", "bt709", "-color_trc", "bt709",
                             "-color_range", "tv"]),
}
VUI_FIELDS = ("colour_primaries", "transfer_characteristics", "matrix_coefficients", "video_full_range_flag")

# One fix hint per gate, logged with every failure.
FIX = {
    "faststart": "mux with -movflags +faststart (moov before mdat) and without fragmenting",
    "streams": "deliver one H.264 yuv420p video and one AAC 48 kHz stereo track: copy-mux with "
               "-map 0:v:0 -map 1:a:0 and nothing else",
    "metadata": "strip inherited source tags (comment, purl, description ...) with -map_metadata -1",
    "frames": "the decoded frame count is not the plan's N: re-render, or check --frames",
    "fps": "render CFR at the canvas rate (-fps_mode cfr) and copy-mux with -r <fps>",
    "first_pts": "never mux with -avoid_negative_ts make_zero: it adds an empty video edit (black first frame)",
    "audio_priming": "copy the AAC from an .m4a: a raw .aac or an AAC re-encode at the mux loses the priming edit",
    "av_length": "fit the mix to round(N*48000/fps) samples before the one AAC encode; never use -shortest",
    "colr": "add -colorspace/-color_primaries/-color_trc/-color_range to the copy-mux (container colr box)",
    "vui": "add -bsf:v h264_metadata=colour_primaries=..:matrix_coefficients=.. to the copy-mux (H.264 VUI)",
    "decode_errors": "the file does not decode cleanly: re-render or re-mux it",
    "black_tail": "the clip ends on black frames: trim them or fix the dropped layer, then re-render",
    "max_dur": "re-cut the clip under the max duration (Defaults: <= 59.5 s)",
    "true_peak": "run finalize_mux.py on the PCM mix (its AAC true-peak loop), or lower the master",
}


class _Parser(argparse.ArgumentParser):
    """argparse that reports usage errors as a ClipError, so stdout still carries one JSON object."""

    def error(self, message):
        raise cl.ClipError("usage", message, hint=self.format_usage().strip(), exit_code=2)


# ---------------------------------------------------------------- small helpers

def _r6(x):
    return None if x is None else round(float(x), 6) + 0.0


def _r2(x):
    return None if x is None else round(float(x), 2) + 0.0   # + 0.0 turns -0.0 into 0.0


def _tail(text, n=12):
    lines = [ln for ln in text.strip().splitlines() if ln.strip()]
    return "\n".join(lines[-n:]) or None


def _frame_time(k, fps):
    """Seek time of frame k: k/fps floored to the microsecond (ref 03 §2 Frame grid; cl.t6 alone rounds)."""
    return cl.t6(Fraction(math.floor(Fraction(k) / fps * 1_000_000), 1_000_000))


def _target_samples(frames, fps):
    """round(N * SR / fps) from the exact rational, halves rounded up: 800 per frame at 60/1."""
    return math.floor(Fraction(frames) * SR / fps + Fraction(1, 2))


def ffmpeg_watched(ffmpeg, args, what):
    """Run ffmpeg with -progress on stdout and kill it only after STALL_S s without out_time_us growth.

    Returns (exit code, last progress frame= value or None, stderr text). A long encode is never killed by a
    fixed timeout; a hung one is (ref 03 §4 Windows-safe ffmpeg). stdout carries the progress, so the command
    must write its output to a file or to `-f null -`.
    """
    cmd = [str(ffmpeg), "-nostdin", "-progress", "pipe:1", "-nostats", *[str(a) for a in args]]
    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except OSError as e:
        raise cl.ClipError("tool_missing", f"cannot run {ffmpeg}: {e}", exit_code=2)
    state = {"seen": time.monotonic(), "out_us": -1, "frame": None}
    err = []

    def read_progress():
        for raw in proc.stdout:
            key, _, val = raw.decode("utf-8", "replace").strip().partition("=")
            if key == "frame" and val.isdigit():
                state["frame"] = int(val)
            elif key == "out_time_us" and val.isdigit() and int(val) > state["out_us"]:
                state["out_us"], state["seen"] = int(val), time.monotonic()

    readers = [threading.Thread(target=read_progress, daemon=True),
               threading.Thread(target=lambda: err.append(proc.stderr.read()), daemon=True)]
    for t in readers:
        t.start()
    while True:
        try:
            proc.wait(timeout=1.0)
            break
        except subprocess.TimeoutExpired:
            if time.monotonic() - state["seen"] > STALL_S:
                proc.kill()
                proc.wait()
                raise cl.ClipError("ffmpeg_stalled", f"{what}: ffmpeg made no progress for {STALL_S} s and was killed",
                                   hint="check the input file and the disk; rerun")
    for t in readers:
        t.join()
    stderr = b"".join(err).decode("utf-8", "replace")
    rc = proc.returncode & 0xFFFFFFFF
    if rc in cl.BROKEN_BUILD_CODES:
        raise cl.ClipError("broken_ffmpeg_build", f"ffmpeg exited {cl.BROKEN_BUILD_CODES[rc]}",
                           hint="the ffmpeg build cannot start (missing DLL); reinstall it or use imageio-ffmpeg")
    return proc.returncode, state["frame"], stderr


# ---------------------------------------------------------------- ISO-BMFF box walk (stdlib, mdat never read)

def _boxes(buf, start, end):
    """(type, payload_start, box_end) for each box in buf[start:end]; ValueError on a malformed header."""
    pos = start
    while pos < end:
        if end - pos < 8:
            raise ValueError(f"truncated box header at moov byte {pos}")
        size, typ = struct.unpack_from(">I4s", buf, pos)
        head = 8
        if size == 1:
            size, head = struct.unpack_from(">Q", buf, pos + 8)[0], 16
        elif size == 0:
            size = end - pos
        if size < head or pos + size > end:
            raise ValueError(f"bad size {size} for box {typ!r} at moov byte {pos}")
        yield typ.decode("latin-1"), pos + head, pos + size
        pos += size


def _timescale(buf, ps):
    """mvhd/mdhd timescale: a u32 at payload +12 (version 0) or +20 (version 1)."""
    return struct.unpack_from(">I", buf, ps + (20 if buf[ps] == 1 else 12))[0]


def _elst(buf, ps, pe):
    """Edit list as [(segment_duration in movie ticks, media_time in media ticks; -1 = empty edit)]."""
    n = struct.unpack_from(">I", buf, ps + 4)[0]
    fmt, step = (">Qq", 20) if buf[ps] == 1 else (">Ii", 12)
    if ps + 8 + n * step > pe:
        raise ValueError("elst runs past its box")
    return [struct.unpack_from(fmt, buf, ps + 8 + i * step) for i in range(n)]


def _colr(buf, cs, ce):
    """'primaries/transfer/matrix/full_range' of a colr box ('-' = not stored), or what it holds instead."""
    kind = buf[cs:cs + 4].decode("latin-1")
    if kind == "nclx" and ce - cs >= 11:
        p, t, m, r = struct.unpack_from(">HHHB", buf, cs + 4)
        return f"{p}/{t}/{m}/{r >> 7}"
    if kind == "nclc" and ce - cs >= 10:      # QuickTime: no range flag
        return "{}/{}/{}/-".format(*struct.unpack_from(">HHH", buf, cs + 4))
    return f"colr {kind} (no code points)"


def _track(buf, s, e):
    t = {"handler": None, "timescale": None, "edits": None, "stts": [], "samples": None, "colr": "missing"}
    stsd = None

    def walk(a, b):
        nonlocal stsd
        for typ, ps, pe in _boxes(buf, a, b):
            if typ in ("edts", "mdia", "minf", "stbl"):
                walk(ps, pe)
            elif typ == "elst":
                t["edits"] = _elst(buf, ps, pe)
            elif typ == "mdhd":
                t["timescale"] = _timescale(buf, ps)
            elif typ == "hdlr":
                t["handler"] = buf[ps + 8:ps + 12].decode("latin-1")
            elif typ == "stts":
                n = struct.unpack_from(">I", buf, ps + 4)[0]
                if ps + 8 + 8 * n > pe:
                    raise ValueError("stts runs past its box")
                t["stts"] = [struct.unpack_from(">II", buf, ps + 8 + 8 * i) for i in range(n)]
            elif typ == "stsz":
                t["samples"] = struct.unpack_from(">I", buf, ps + 8)[0]
            elif typ == "stsd":
                stsd = (ps, pe)

    walk(s, e)
    if stsd and t["handler"] == "vide":
        for _, es, ee in _boxes(buf, stsd[0] + 8, stsd[1]):      # the first sample entry (avc1)
            # A visual sample entry has 78 bytes of fixed fields before its child boxes (avcC, colr, pasp).
            for ctyp, cs, ce in _boxes(buf, es + 78, ee):
                if ctyp == "colr":
                    t["colr"] = _colr(buf, cs, ce)
            break
    return t


def read_mp4(path):
    """Top-level box order plus per-track facts from moov. Reads box headers and moov only.

    Returns {"top": [types], "movie_timescale": int, "tracks": [{"handler", "timescale", "edits", "stts",
    "samples", "colr"}]}. Raises ValueError when the file is not a well-formed ISO-BMFF file.
    """
    with open(path, "rb") as f:
        total = os.fstat(f.fileno()).st_size
        top, moov, pos = [], None, 0
        while pos < total:
            f.seek(pos)
            hdr = f.read(16)
            if len(hdr) < 8:
                raise ValueError(f"truncated box header at byte {pos}")
            size, typ = struct.unpack_from(">I4s", hdr)
            head = 8
            if size == 1 and len(hdr) == 16:
                size, head = struct.unpack_from(">Q", hdr, 8)[0], 16
            elif size == 0:
                size = total - pos
            name = typ.decode("latin-1")
            if not re.fullmatch(r"[ -~]{4}", name) or size < head or pos + size > total:
                raise ValueError(f"no valid ISO-BMFF box at byte {pos} (type {name!r}, size {size})")
            top.append(name)
            if name == "moov" and moov is None:
                f.seek(pos + head)
                moov = f.read(size - head)
            pos += size
    if moov is None:
        raise ValueError("no moov box")
    movie_ts, tracks = None, []
    for typ, ps, pe in _boxes(moov, 0, len(moov)):
        if typ == "mvhd":
            movie_ts = _timescale(moov, ps)
        elif typ == "trak":
            tracks.append(_track(moov, ps, pe))
    if not movie_ts:
        raise ValueError("no mvhd timescale")
    return {"top": top, "movie_timescale": movie_ts, "tracks": tracks}


def _first(tracks, handler):
    return next((t for t in tracks if t["handler"] == handler), None)


def _cfr_rate(track):
    """Exact frame rate when the video track sits on one frame grid (one stts entry), else None."""
    if track and len(track["stts"]) == 1 and track["stts"][0][1] and track["timescale"]:
        return Fraction(track["timescale"], track["stts"][0][1])
    return None


def _stts_text(track):
    stts = track["stts"] if track else []
    more = " ..." if len(stts) > 4 else ""
    return f"{len(stts)} stts entries: " + ", ".join(f"{c}x{d}" for c, d in stts[:4]) + more


# ---------------------------------------------------------------- ffmpeg-side probes

def ffmpeg_header(path, ffmpeg):
    """(global metadata keys, [(stream kind, codec)]) from the `ffmpeg -i` header."""
    err = cl.run([ffmpeg, "-hide_banner", "-nostdin", "-i", str(path)], check=False).stderr
    head = err.split("Duration:", 1)[0]
    keys = re.findall(r"^ {4}([^\s:][^:]*?)\s*:", head, re.M)      # continuation lines have no key
    streams = [(k.lower(), c) for k, c in re.findall(r"^\s*Stream #\d+:\d+\S*: (\w+): (\S+)", err, re.M)]
    return keys, streams


def first_video_pts(path, ffmpeg):
    cp = cl.run([ffmpeg, "-hide_banner", "-nostdin", "-i", str(path), "-map", "0:v:0", "-vf", "showinfo",
                 "-frames:v", "1", "-f", "null", "-"], check=False)
    m = re.search(r"pts_time:\s*(-?[0-9.]+)", cp.stderr)
    return float(m.group(1)) if m else None


def vui_tags(path, ffmpeg):
    """'primaries/transfer/matrix/full_range' from the H.264 SPS VUI ('-' = absent), or 'missing'.

    trace_headers prints the extradata SPS first, at info level, so the first value of each field is the one.
    """
    cp = cl.run([ffmpeg, "-hide_banner", "-nostdin", "-v", "info", "-i", str(path), "-map", "0:v:0", "-c", "copy",
                 "-bsf:v", "trace_headers", "-frames:v", "1", "-f", "null", "-"], check=False)
    vals = {}
    for key, val in re.findall(r"\]\s+\d+\s+(" + "|".join(VUI_FIELDS) + r")\s+[01]+\s+=\s+(\d+)", cp.stderr):
        vals.setdefault(key, int(val))
    if not vals:
        return "missing"
    return "/".join(str(vals[k]) if k in vals else "-" for k in VUI_FIELDS)


def tail_black(path, ffmpeg, start_k, fps):
    """(frames decoded from frame start_k to the end, any black frame among them)."""
    cp = cl.run([ffmpeg, "-hide_banner", "-nostdin", "-progress", "pipe:1", "-nostats",
                 "-ss", _frame_time(start_k, fps), "-i", str(path), "-map", "0:v:0", "-vf", BLACKDETECT,
                 "-f", "null", "-"], check=False)
    frames = re.findall(r"^frame=(\d+)", cp.stdout, re.M)
    return (int(frames[-1]) if frames else 0), "black_start" in cp.stderr


# ---------------------------------------------------------------- delivery gate

def delivery_gate(path, ffmpeg, ffprobe, fps_want, frames_want, tag, max_dur):
    """Run every delivery check on `path`. Returns (gate dict, facts {"frames", "fps", "tp"})."""
    info = cl.probe(path, ffmpeg, ffprobe)                     # exit 2 when ffmpeg cannot read it
    v, a = info["video"], info["audio"]
    if v is None:
        raise cl.ClipError("no_video_stream", f"{path} has no video stream", hint=FIX["streams"])
    try:
        mp4 = read_mp4(path)
    except (OSError, ValueError, struct.error) as e:
        raise cl.ClipError("not_mp4", f"{path} is not a well-formed MP4: {e}", hint="deliver the MP4 that "
                           "finalize_mux.py writes")
    vt, at = _first(mp4["tracks"], "vide"), _first(mp4["tracks"], "soun")
    gate = {}

    def put(name, ok, measured, limit):
        gate[name] = {"ok": bool(ok), "measured": measured, "limit": limit}

    top = mp4["top"]
    put("faststart", "moov" in top and "mdat" in top and top.index("moov") < top.index("mdat") and "moof" not in top,
        ",".join(top), "moov before mdat, no moof")

    keys, streams = ffmpeg_header(path, ffmpeg)
    kinds = sorted(k for k, _ in streams)
    vdesc = f"{v['codec']} {v['pix_fmt']}"
    adesc = f"{a['codec']} {a['sample_rate']} Hz {a['channels']} ch" if a else None
    put("streams", kinds == ["audio", "video"] and vdesc == "h264 yuv420p" and adesc == f"aac {SR} Hz 2 ch",
        {"streams": [f"{k} {c}" for k, c in streams], "video": vdesc, "audio": adesc},
        f"1 video h264 yuv420p + 1 audio aac {SR} Hz 2 ch, nothing else")
    extra = sorted(set(keys) - ALLOWED_TAGS)
    put("metadata", not extra, {"keys": keys, "not_allowed": extra}, sorted(ALLOWED_TAGS))

    # One full decode: the frame count (never the packet count or Duration:) and the decoder errors.
    rc, decoded, err = ffmpeg_watched(ffmpeg, ["-v", "error", "-i", path, "-map", "0:v:0", "-map", "0:a:0?",
                                               "-f", "null", "-"], "decode check")
    n = decoded or 0
    put("frames", n > 0 and (frames_want is None or n == frames_want),
        {"decoded": n, "packets": vt["samples"] if vt else None}, frames_want if frames_want is not None else "> 0")

    rate = _cfr_rate(vt)
    put("fps", rate is not None and (fps_want is None or rate == fps_want),
        cl.frac_str(rate) if rate else _stts_text(vt),
        (cl.frac_str(fps_want) if fps_want else "any") + " on one stts entry")
    fps = fps_want or rate or v["fps_r"] or v["fps_avg"]
    if not fps:
        raise cl.ClipError("no_frame_rate", f"cannot tell the frame rate of {path}", hint="pass --fps")
    video_s = Fraction(n) / fps

    edits = vt["edits"] if vt else None
    empty = any(mt == -1 for _, mt in edits or [])
    pts = first_video_pts(path, ffmpeg)
    put("first_pts", not empty and pts is not None and abs(pts) <= FIRST_PTS_TOL,
        {"pts_s": _r6(pts), "empty_edit": empty}, f"0 +/- {FIRST_PTS_TOL} s, no empty video edit")

    a_edits = at["edits"] if at else None
    put("audio_priming", bool(a_edits) and a_edits[0][1] > 0,
        a_edits[0][1] if a_edits else "no audio edit list", "> 0 (AAC priming in the edit list)")

    if a_edits:
        # The edit list is what players present. Its ticks may be coarser than 1 ms (movie timescale < 1000),
        # so the tolerance never drops below one tick.
        ts = mp4["movie_timescale"]
        audio_s = Fraction(sum(seg for seg, _ in a_edits), ts)
        tol = max(AV_TOL, Fraction(1, ts))
        put("av_length", abs(audio_s - video_s) <= tol,
            {"audio_s": _r6(audio_s), "video_s": _r6(video_s), "delta_s": _r6(audio_s - video_s), "by": "edit list"},
            _r6(tol))
    elif a:
        # Fallback without an audio edit list: decoded AAC includes whole-frame end padding, hence the window
        # of -1 frame to +1 frame + 1024 samples (ref 05 §1).
        got = len(cl.decode_audio(path, ffmpeg, sr=SR, channels=1, src_channels=a["channels"]))
        audio_s = Fraction(got, SR)
        lo, hi = -1 / fps, 1 / fps + Fraction(AAC_FRAME, SR)
        put("av_length", lo <= audio_s - video_s <= hi,
            {"audio_s": _r6(audio_s), "video_s": _r6(video_s), "delta_s": _r6(audio_s - video_s),
             "by": "decoded samples"}, [_r6(lo), _r6(hi)])
    else:
        put("av_length", False, "no audio", _r6(AV_TOL))

    colr = vt["colr"] if vt else "missing"
    vui = vui_tags(path, ffmpeg)
    if tag == "none":
        put("colr", True, colr, "any (--tag none)")
        put("vui", True, vui, "any (--tag none)")
    else:
        want = "/".join(str(x) for x in TAGS[tag][0])
        put("colr", colr == want, colr, want)
        put("vui", vui == want, vui, want)

    errors = [ln for ln in err.splitlines() if ln.strip()]
    first = errors[0] if errors else (f"ffmpeg exited {rc}" if rc else None)
    put("decode_errors", rc == 0 and not errors, {"count": len(errors), "first": first}, 0)

    tail_n = max(1, math.ceil(TAIL * fps))
    got, black = tail_black(path, ffmpeg, max(0, n - tail_n), fps)
    put("black_tail", got > 0 and not black, {"frames": got, "black": black},
        f"no black frame in the last {tail_n} frames (0.1 s)")

    put("max_dur", video_s <= Fraction(max_dur), _r6(video_s), max_dur)

    tp = cl.ebur128(path, ffmpeg)["TP"] if a else None           # None from ebur128 = digital silence
    put("true_peak", a is not None and (tp is None or tp <= TP_CEILING), _r2(tp), TP_CEILING)
    return gate, {"frames": n, "fps": fps, "tp": tp}


def log_gate(gate, path):
    bad = [k for k, g in gate.items() if not g["ok"]]
    for k in bad:
        g = gate[k]
        cl.log(f"  FAIL {k}: measured {g['measured']} limit {g['limit']}\n    fix: {FIX[k]}")
    summary = f"gate {Path(path).name}: {len(gate) - len(bad)}/{len(gate)} ok"
    cl.log(summary + (f"; failed: {', '.join(bad)}" if bad else ""))


# ---------------------------------------------------------------- mux mode steps

def input_video(path, ffmpeg, ffprobe, fps_arg):
    """(decoded frame count N, exact frame rate) of the video to deliver. Fails before any work is done."""
    info = cl.probe(path, ffmpeg, ffprobe)
    v = info["video"]
    if v is None:
        raise cl.ClipError("no_video_stream", f"{path} has no video stream", exit_code=2)
    if (v["codec"], v["pix_fmt"]) != ("h264", "yuv420p"):
        raise cl.ClipError("video_format", f"the video is {v['codec']} {v['pix_fmt']}; delivery needs H.264 yuv420p",
                           hint="render H.264 yuv420p (ref 03 §4 Delivery encode: libx264 -preset medium -crf 16 "
                                "-bf 0 -pix_fmt yuv420p)")
    try:
        vt = _first(read_mp4(path)["tracks"], "vide")
    except (OSError, ValueError, struct.error) as e:
        raise cl.ClipError("video_not_mp4", f"{path} is not a readable MP4/MOV: {e}",
                           hint="render or encode the video to .mp4", exit_code=2)
    rate = _cfr_rate(vt)
    if rate is None:
        raise cl.ClipError("video_vfr", f"the video is not on one frame grid ({_stts_text(vt)})",
                           hint="render CFR at the canvas fps (-fps_mode cfr); the copy-mux keeps the timing as is")
    if fps_arg is not None and rate != fps_arg:
        raise cl.ClipError("fps_mismatch", f"the video runs at {cl.frac_str(rate)} fps, --fps says "
                           f"{cl.frac_str(fps_arg)}", hint="re-render at the canvas fps, or fix --fps")
    rc, frames, err = ffmpeg_watched(ffmpeg, ["-v", "error", "-i", path, "-map", "0:v:0", "-f", "null", "-"],
                                     "video decode")
    if not frames:
        raise cl.ClipError("unreadable_input", f"cannot decode {path}", hint=_tail(err), exit_code=2)
    if info["audio"]:
        cl.log("note: the video's own audio track is dropped (explicit -map)")
    return frames, rate


def load_mix(path, ffmpeg, ffprobe):
    """The master mix as float32 (n, 2) at 48 kHz. Mono is duplicated with pan, never -ac 2 (ref 03 §3)."""
    a = cl.probe(path, ffmpeg, ffprobe)["audio"]
    if a is None:
        raise cl.ClipError("mix_no_audio", f"{path} has no audio stream", exit_code=2)
    ch = a["channels"] or 2
    if ch not in (1, 2):
        raise cl.ClipError("mix_channels", f"the mix has {ch} channels; the master must be mono or stereo",
                           hint="deliver mix_audio.py's stereo mix.wav", exit_code=2)
    if a["sample_rate"] and a["sample_rate"] != SR:
        cl.log(f"warning: the mix is {a['sample_rate']} Hz; it is resampled to {SR} Hz")
    if not (a["codec"] or "").startswith(("pcm_", "flac")):
        cl.log(f"warning: the mix is {a['codec']} (lossy); the delivery encodes it again: pass the float master "
               f"(mix_audio.py mix.wav) so the AAC encode is the only lossy step")
    return cl.decode_audio(path, ffmpeg, sr=SR, channels=2, src_channels=ch)


def fit_mix(x, target):
    """Zero-pad or trim the float mix to exactly `target` samples (ref 03 §4 Picture is the clock)."""
    if len(x) == target:
        return x, "copy"
    if len(x) > target:
        return x[:target], "trim"
    return np.concatenate([x, np.zeros((target - len(x), x.shape[1]), np.float32)]), "pad"


def encode_aac(ffmpeg, wav, m4a, att_db):
    args = ["-v", "error", "-y", "-i", wav, "-map", "0:a:0"]
    if att_db:
        args += ["-af", f"volume={att_db:.3f}dB"]
    rc, _, err = ffmpeg_watched(ffmpeg, args + AAC_ARGS + [m4a], "AAC encode")
    if rc != 0:
        raise cl.ClipError("aac_encode_failed", f"the AAC encode exited {rc}", hint=_tail(err))


def aac_with_true_peak(ffmpeg, wav, m4a):
    """Encode the PCM to AAC and hold the true peak of the encoded audio at <= -1.0 dBTP.

    Each correction re-encodes the PCM (never the AAC) with att += -1 - 0.5 * 2**pass - max(tp_aac, tp_pcm + att):
    sized from the louder of the AAC and the attenuated PCM, aiming twice as far under each pass (ref 03 §3).
    Returns (final true peak or None for silence, attenuation dB, passes, ok).
    """
    att, tp_pcm, passes = 0.0, None, []
    for k in range(TP_MAX_PASSES + 1):
        encode_aac(ffmpeg, wav, m4a, att)
        tp = cl.ebur128(m4a, ffmpeg)["TP"]
        passes.append({"pass": k, "tp_dbtp": _r2(tp), "att_db": round(att, 3) + 0.0})
        cl.log(f"aac pass {k}: true peak {'-inf' if tp is None else tp} dBTP at {att:+.3f} dB")
        if tp is None or tp <= TP_CEILING:
            return tp, att, passes, True
        if k == TP_MAX_PASSES:
            return tp, att, passes, False
        if tp_pcm is None:
            tp_pcm = cl.ebur128(wav, ffmpeg)["TP"]
        ref = max(tp, tp_pcm + att if tp_pcm is not None else -math.inf)
        att += TP_CEILING - TP_HEADROOM_DB * 2 ** k - ref


def mux(ffmpeg, video, m4a, staged, fps, tag):
    """Copy-mux the video and the .m4a: explicit maps, no inherited metadata or chapters, faststart, tags."""
    args = ["-v", "error", "-y", "-i", video, "-i", m4a, "-map", "0:v:0", "-map", "1:a:0", "-c", "copy",
            "-r", cl.frac_str(fps), "-map_metadata", "-1", "-map_chapters", "-1"]
    if tag != "none":
        (p, t, m, r), flags = TAGS[tag]
        args += ["-bsf:v", f"h264_metadata=colour_primaries={p}:transfer_characteristics={t}:"
                           f"matrix_coefficients={m}:video_full_range_flag={r}", *flags]
    args += ["-movflags", "+faststart", staged]    # never -shortest, never -avoid_negative_ts
    rc, _, err = ffmpeg_watched(ffmpeg, args, "mux")
    if rc != 0:
        raise cl.ClipError("mux_failed", f"the copy-mux exited {rc}", hint=_tail(err))


def run_mux(args, ffmpeg, ffprobe):
    video, mix, out = Path(args.video), Path(args.mix), Path(args.out)
    for p in (video, mix):
        if not p.is_file():
            raise cl.ClipError("input_missing", f"no such file: {p}", exit_code=2)
    if out.suffix.lower() != ".mp4":
        raise cl.ClipError("usage", f"--out must be an .mp4 path: {out}", exit_code=2)
    if out.resolve() in (video.resolve(), mix.resolve()):
        raise cl.ClipError("usage", "--out must not overwrite an input", exit_code=2)

    frames, fps = input_video(video, ffmpeg, ffprobe, args.fps_q)
    if args.frames is not None and frames != args.frames:
        raise cl.ClipError("frames_mismatch", f"the video decodes to {frames} frames, --frames says {args.frames}",
                           hint=FIX["frames"])
    target = _target_samples(frames, fps)
    x = load_mix(mix, ffmpeg, ffprobe)
    y, fit = fit_mix(x, target)
    cl.log(f"video: {frames} frames at {cl.frac_str(fps)} = {cl.t6(Fraction(frames) / fps)} s; "
           f"mix {len(x)} samples -> {fit} to {target}")
    if abs(len(x) - target) > SR / fps:
        cl.log(f"warning: the mix and the picture differ by {(len(x) - target) * 1000 / SR:+.1f} ms (over one "
               f"frame); was the mix built for this render?")

    res = {"ok": False, "version": SCRIPT_VERSION, "out": out, "frames": frames, "fps": cl.frac_str(fps),
           "audio": {"samples": target, "tp_dbtp": None, "lowered_db": None, "passes": [], "mix_samples": len(x),
                     "fit": fit},
           "gate": {}, "staged": None}
    work = Path(tempfile.mkdtemp(prefix="finalize_mux-"))
    staged = None
    try:
        wav, m4a = work / "mix_fit.wav", work / "audio.m4a"
        cl.write_wav_f32(wav, y, SR)
        tp, att, passes, tp_ok = aac_with_true_peak(ffmpeg, wav, m4a)
        res["audio"].update(tp_dbtp=_r2(tp), lowered_db=_r2(-att), passes=passes)
        if not tp_ok:
            res["gate"]["true_peak"] = {"ok": False, "measured": _r2(tp), "limit": TP_CEILING}
            cl.log(f"error: AAC true peak still {tp} dBTP after {TP_MAX_PASSES} correction passes: {passes}\n"
                   f"    fix: lower the master (mix_audio.py limiter) and rerun")
            return res, 1

        try:
            out.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise cl.ClipError("out_unwritable", f"cannot create {out.parent}: {e}",
                               hint="choose an --out folder you can write to", exit_code=2)
        staged = Path(cl.tmp_path(out))
        mux(ffmpeg, video, m4a, staged, fps, args.tag)
        res["gate"], _ = delivery_gate(staged, ffmpeg, ffprobe, fps, frames, args.tag, args.max_dur)
        log_gate(res["gate"], out)
        if not all(g["ok"] for g in res["gate"].values()):
            res["staged"], staged = staged, None     # keep it for inspection
            cl.log(f"not delivered; staged file kept: {res['staged']}")
            return res, 1
        try:
            cl.replace_with_retry(staged, out)
        except cl.ClipError as e:                    # the validated file stays under its staged name
            res["staged"], staged = staged, None
            res["error"] = {"code": e.code, "message": e.message, "hint": e.hint}
            cl.log(f"error: {e.message}; the gated file is kept as {res['staged']}")
            return res, 1
        staged = None
        res["ok"] = True
        cl.log(f"delivered {out}")
        return res, 0
    finally:
        shutil.rmtree(work, ignore_errors=True)
        if staged is not None:                      # a mux or gate step raised: drop the partial file
            try:
                os.remove(staged)
            except OSError:
                pass


def run_check(args, ffmpeg, ffprobe):
    path = Path(args.check)
    gate, facts = delivery_gate(path, ffmpeg, ffprobe, args.fps_q, args.frames, args.tag, args.max_dur)
    log_gate(gate, path)
    ok = all(g["ok"] for g in gate.values())
    res = {"ok": ok, "version": SCRIPT_VERSION, "out": path, "frames": facts["frames"],
           "fps": cl.frac_str(facts["fps"]),
           "audio": {"samples": None, "tp_dbtp": _r2(facts["tp"]), "lowered_db": None, "passes": []}, "gate": gate}
    return res, 0 if ok else 1


# ---------------------------------------------------------------- CLI

def parse_args(argv):
    p = _Parser(prog="finalize_mux.py", description="Fit the mix to the picture, one AAC encode, copy-mux, "
                "delivery gate. See the module docstring.")
    p.add_argument("--video", help="video-only MP4 (H.264 yuv420p, CFR)")
    p.add_argument("--mix", help="master mix (mono/stereo, any ffmpeg-readable format)")
    p.add_argument("--out", help="delivered file, e.g. edited/NN-slug.mp4")
    p.add_argument("--check", metavar="FILE", help="run the delivery gate alone on FILE")
    p.add_argument("--fps", help="expected frame rate: 60, 30, 30000/1001 ... (default: the video's own)")
    p.add_argument("--frames", type=int, help="expected decoded frame count N")
    p.add_argument("--tag", choices=["709tv", "601tv", "none"], default="709tv",
                   help="colour tags written and required (default 709tv)")
    p.add_argument("--max-dur", type=float, default=59.5, help="max N/fps in seconds (default 59.5)")
    p.add_argument("--ffmpeg", help="ffmpeg executable")
    p.add_argument("--ffprobe", help="ffprobe executable, or 'none' for the ffmpeg-only probe")
    a = p.parse_args(argv)
    if a.check:
        if a.video or a.mix or a.out:
            p.error("--check FILE runs the gate alone; drop --video/--mix/--out")
    elif not (a.video and a.mix and a.out):
        p.error("mux mode needs --video, --mix and --out (or --check FILE)")
    try:
        a.fps_q = cl.parse_rate(a.fps) if a.fps else None
    except (ValueError, ZeroDivisionError, OverflowError):
        a.fps_q = None
    if a.fps and not a.fps_q:
        p.error(f"--fps: not a frame rate: {a.fps}")
    if a.frames is not None and a.frames <= 0:
        p.error("--frames must be > 0")
    if not a.max_dur > 0:
        p.error("--max-dur must be > 0")
    return a


def main() -> int:
    try:
        args = parse_args(sys.argv[1:])
        ffmpeg = cl.find_ffmpeg(args.ffmpeg)
        ffprobe = cl.find_ffprobe(ffmpeg, args.ffprobe)
        res, code = run_check(args, ffmpeg, ffprobe) if args.check else run_mux(args, ffmpeg, ffprobe)
    except cl.ClipError as e:
        # The same envelope cl.run_main prints, plus the version the contract puts on every stdout object.
        cl.emit({**e.envelope(), "version": SCRIPT_VERSION})
        cl.log(f"error [{e.code}]: {e.message}" + (f"\nhint: {e.hint}" if e.hint else ""))
        return e.exit_code
    cl.emit(res)
    return code


if __name__ == "__main__":
    cl.run_main(main)
