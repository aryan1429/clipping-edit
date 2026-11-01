"""probe_source.py - probe a downloaded source once and write source_facts.json (ref 03 section 1).

Usage:
  python -P probe_source.py SRC [--asr-audio AUDIO] [--canvas auto|60|30|NUM/DEN] [--out source_facts.json]
                            [--ffmpeg PATH] [--ffprobe PATH|none]

What it does (ref 03 section 1, Probe once / Normalise in every clip intermediate / HDR fallback /
ASR on the video's clock):
  probe      codec, pixel format, coded and displayed size, SAR, rotation, fps_r / fps_avg, VFR (|avg - r| / r
             > 1 %), colour tags, HDR (PQ / HLG transfer), bit depth, audio. Uses ffprobe when present, else the
             stderr of `ffmpeg -i` (rates snapped to N or N*1000/1001). Frame 0's own colour tags and the first
             audio and video timestamps come from one short `showinfo` / `ashowinfo` decode.
  canvas     auto = 60 when fps_avg >= 50, else 30; --canvas overrides it.
  norm_vf    the -vf string every ffmpeg read of the source video must start with, in this order:
               fps=<canvas>                                   (re-time first; never relabel the rate)
               scale=trunc(iw*sar/2)*2:ih,setsar=1            (SAR != 1)
               one colour step:
                 HDR          [setparams=<missing frame tags>,]zscale=t=linear:npl=100,tonemap=hable:desat=0,
                              zscale=p=bt709:t=bt709:m=bt709:r=tv,scale=out_color_matrix=bt709:out_range=tv
                 SDR BT.2020  [setparams=...,]zscale=p=bt709:t=bt709:m=bt709:r=tv,scale=out_color_matrix=...
                 BT.601 / other matrix / pc range
                              scale=in_color_matrix=<m>:in_range=<tv|pc>:out_color_matrix=bt709:out_range=tv:
                              flags=accurate_rnd+full_chroma_int
                 RGB          scale=out_color_matrix=bt709:out_range=tv:flags=accurate_rnd+full_chroma_int
               setparams=colorspace=bt709:color_primaries=bt709:color_trc=bt709:range=tv
             An untagged matrix is guessed as players do: bt709 from 720 coded lines unless VP9/AV1, else smpte170m.
             Rotation is applied by ffmpeg's autorotate before norm_vf: never pass -noautorotate.
  --asr-audio  the separate audio file Whisper transcribes. Three 20 s windows (start, middle, end) of both files
             are decoded at 8 kHz on the video's clock (aresample=async=1:first_pts=0); the onset curves (rises of
             10 ms RMS) are matched by Pearson r over +-500 ms; r <= 0.3 is not judged; the median of the judged
             windows is asr_offset_s (+ = SRC's audio is late: add it to every ASR word time).

Output (stdout, and --out when given; UTF-8):
  {"ok", "version", "src", "probe": "ffprobe"|"ffmpeg", "duration", "title",
   "video": {"codec", "pix_fmt", "width", "height", "display_w", "display_h", "sar", "rotation", "fps_r",
             "fps_avg", "vfr", "color": {"range", "space", "primaries", "transfer"}, "matrix_assumed",
             "hdr": "pq"|"hlg"|null, "bit_depth"},
   "audio": {"codec", "sample_rate", "channels", "layout", "start_vs_video_s"} | null,
   "canvas_fps": "60/1", "norm_vf", "needs": {"retime", "sar_fix", "matrix_convert", "tonemap", "rotate"},
   "filters": {"zscale", "tonemap"}, "asr_offset_s": float|null, "warnings": [str], "error"?: {...}}
  display_w x display_h is the picture norm_vf delivers (rotation applied, SAR squared to even width).
  rotation is the clockwise display rotation (0, 90, 180, 270).

Exit codes:
  0  ok
  1  facts written but the source cannot be used as is: HDR / BT.2020 source and ffmpeg lacks zscale or tonemap
     (norm_vf is null; error.code hdr_no_zscale / bt2020_no_zscale), no video stream (no_video), or the
     --asr-audio offset exceeds one canvas frame (asr_offset: shift every ASR word by asr_offset_s)
  2  usage error or unreadable input
Test-only flag: --assume-no-hdr-filters makes the filter check report zscale/tonemap as missing.
"""
import argparse
import os
import re
import statistics
import sys
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cliplib as cl  # noqa: E402

SCRIPT_VERSION = "1.0.0"
# Approach adapted from HyperFrames (github.com/heygen-com/hyperframes, Apache-2.0); independent Python implementation.

VFR_TOL = 0.01                      # vfr = |fps_avg - fps_r| / fps_r > 1 % (ref 03 section 1 Probe once)
HDR_TRANSFERS = {"smpte2084": "pq", "arib-std-b67": "hlg"}
BT2020 = {"bt2020", "bt2020nc", "bt2020c"}
UNKNOWN = {None, "", "unknown", "reserved", "unspecified"}
UNTAGGED_601_CODECS = {"vp9", "av1"}   # players read untagged VP9/AV1 as BT.601 (HF videoFrameExtractor.ts:971-979)
# Source matrix tag -> the name scale's in_color_matrix takes.
SCALE_MATRIX = {"bt709": "bt709", "smpte170m": "bt601", "bt470bg": "bt601", "smpte240m": "smpte240m", "fcc": "fcc",
                "bt2020nc": "bt2020", "bt2020c": "bt2020"}
TAGS_709 = "setparams=colorspace=bt709:color_primaries=bt709:color_trc=bt709:range=tv"
ZSCALE_TAIL = "zscale=p=bt709:t=bt709:m=bt709:r=tv,scale=out_color_matrix=bt709:out_range=tv"
TONEMAP = "zscale=t=linear:npl=100,tonemap=hable:desat=0," + ZSCALE_TAIL
EXACT = "flags=accurate_rnd+full_chroma_int"   # RGB<->YUV exits within 1-2 code values (ref 03 section 1)

ASR_WIN_S = 20.0                    # three windows: start, middle, end
ASR_SR = 8000
ASR_BLOCK = 80                      # 10 ms RMS blocks at 8 kHz
ASR_MAX_LAG = 50                    # +-500 ms in blocks
ASR_MIN_N = 50                      # values per Pearson
ASR_MIN_R = 0.3                     # r <= 0.3 is not judged


# ---------------------------------------------------------------- probing

def first_frames(src, ffmpeg, has_audio):
    """Frame 0's colour tags and the first decoded video / audio timestamps, from one short decode.

    ffprobe's stream tags can come from the container; zscale reads each frame's own tags, so the HDR and
    BT.2020 chains fill only what frame 0 lacks (HF hdrToneMap.ts).
    """
    cmd = [ffmpeg, "-hide_banner", "-nostdin", "-nostats", "-i", src,
           "-map", "0:v:0", "-vf", "showinfo", "-frames:v", "1", "-f", "null", "-"]
    if has_audio:
        cmd += ["-map", "0:a:0", "-af", "ashowinfo", "-frames:a", "1", "-f", "null", "-"]
    cp = cl.run(cmd, check=False)
    err = cp.stderr
    if cp.returncode != 0 and "Parsed_showinfo" not in err:
        raise cl.ClipError("unreadable_input", f"ffmpeg cannot decode the first video frame of {src}",
                           hint=err.strip()[-500:], exit_code=2)
    out = {"tags": {}, "v_pts": None, "a_pts": None}
    m = re.search(r"color_range:(\S+) color_space:(\S+) color_primaries:(\S+) color_trc:(\S+)", err)
    if m:
        out["tags"] = {k: (None if v in UNKNOWN else v) for k, v in
                       zip(("range", "space", "primaries", "transfer"), m.groups())}
    m = re.search(r"Parsed_showinfo_\d+ @ \S+\] n:\s*0 pts:\s*-?\d+ pts_time:(-?[0-9.]+)", err)
    if m:
        out["v_pts"] = float(m.group(1))
    m = re.search(r"Parsed_ashowinfo_\d+ @ \S+\] n:\s*0 pts:\s*-?\d+ pts_time:(-?[0-9.]+)", err)
    if m:
        out["a_pts"] = float(m.group(1))
    return out


def bit_depth(pix_fmt):
    """Bits per component from the pixel format name: yuv420p10le -> 10, p010le -> 10, yuv420p / nv12 -> 8."""
    m = re.search(r"(\d+)(le|be)$", pix_fmt or "")
    if not m:
        return 8
    n = int(m.group(1))
    return 16 if n in (48, 64) else n     # rgb48 / rgba64 count all channels


def is_rgb(pix_fmt):
    return bool(re.match(r"^(gbr|rgb|bgr|argb|abgr|rgba|bgra|0rgb|rgb0|0bgr|bgr0|x2rgb|x2bgr)", pix_fmt or ""))


def display_size(width, height, sar, rotation):
    """The picture norm_vf delivers: autorotate first (transpose swaps the size and inverts the SAR),
    then scale=trunc(iw*sar/2)*2:ih."""
    if rotation % 180 == 90:
        width, height, sar = height, width, 1 / sar
    if sar != 1:
        width = int(width * sar / 2) * 2
    return width, height


def parse_sar(s):
    m = re.match(r"^(\d+)[:/](\d+)$", s or "")
    if not m or int(m.group(1)) == 0 or int(m.group(2)) == 0:
        return Fraction(1)
    return Fraction(int(m.group(1)), int(m.group(2)))


# ---------------------------------------------------------------- colour plan

def colour_step(v, frame_tags, codec, warnings):
    """(matrix_assumed, hdr, step, kind) for the source's colour; step is the norm_vf colour filter or ''.

    kind: 'hdr' | 'bt2020' | 'convert' | None (already BT.709 tv; the final setparams only states it).
    """
    space, prim, trc, rng = v["color_space"], v["color_primaries"], v["color_transfer"], v["color_range"]
    hdr = HDR_TRANSFERS.get(trc)
    if hdr or prim in BT2020 or space in BT2020:
        # zscale needs every input tag on the frame; fill only the ones frame 0 lacks: from the probe, else the
        # BT.2020 defaults (HF). Ours: an SDR BT.2020 frame without a transfer tag gets bt2020-10 (the BT.709
        # curve), since zscale fails "no path between colorspaces" on an untagged transfer.
        fill = []
        for key, name, default in (("space", "colorspace", "bt2020nc"), ("primaries", "color_primaries", "bt2020"),
                                   ("transfer", "color_trc", None if hdr else "bt2020-10")):
            if frame_tags.get(key) in UNKNOWN:
                probed = {"space": space, "primaries": prim, "transfer": trc}[key]
                val = probed if probed not in UNKNOWN else default
                if val:
                    fill.append(f"{name}={val}")
        prefix = f"setparams={':'.join(fill)}," if fill else ""
        matrix = space if space not in UNKNOWN else "bt2020nc"
        if hdr:
            return matrix, hdr, prefix + TONEMAP, "hdr"
        return matrix, None, prefix + ZSCALE_TAIL, "bt2020"
    if is_rgb(v["pix_fmt"]):
        # Not in the ref (ours): name the RGB->YUV matrix. ffmpeg 7.1 already converts by the final setparams tag
        # (colorspace negotiation); older builds would default to BT.601 without this step.
        return "gbr", None, f"scale=out_color_matrix=bt709:out_range=tv:{EXACT}", "convert"
    if space in UNKNOWN:
        # The players' guess for an untagged matrix (ref 03 section 1 Probe once; HF: from 720 coded lines).
        space = "bt709" if v["height"] >= 720 and codec not in UNTAGGED_601_CODECS else "smpte170m"
        warnings.append(f"untagged_matrix: no matrix tag; assumed {space} ({v['height']} coded lines, {codec})")
    # pc range: yuvj* formats or a pc tag (ref 03 section 1). ffmpeg 7.1 would also convert pc->tv on its own
    # (range negotiation before the final setparams); naming in_range keeps it explicit on every build.
    full = rng == "pc" or (v["pix_fmt"] or "").startswith("yuvj")
    in_m = SCALE_MATRIX.get(space)
    if in_m is None:
        warnings.append(f"unsupported_matrix: {space} has no scale equivalent; read as bt709")
        in_m = "bt709"
    if in_m == "bt709" and not full:
        return space, None, "", None
    step = (f"scale=in_color_matrix={in_m}:in_range={'pc' if full else 'tv'}:out_color_matrix=bt709:out_range=tv:"
            f"{EXACT}")
    return space, None, step, "convert"


def rate_arg(f):
    return str(f.numerator) if f.denominator == 1 else cl.frac_str(f)


def parse_canvas(arg, fps_avg, fps_r):
    if arg == "auto":
        src = fps_avg or fps_r
        return Fraction(60 if src is not None and src >= 50 else 30)
    try:
        f = cl.parse_rate(arg)
    except (ValueError, ZeroDivisionError):
        f = None
    if f is None or f <= 0 or f > 240:
        raise cl.ClipError("bad_canvas", f"--canvas {arg!r} is not auto, 60, 30 or NUM/DEN", exit_code=2)
    return f


# ---------------------------------------------------------------- ASR offset

def onset_curve(path, ffmpeg, ss, dur):
    """Rises of the 10 ms RMS of one window, decoded on the file's own clock (first_pts=0 keeps a late start)."""
    import numpy as np
    cmd = [ffmpeg, "-nostdin", "-v", "error", "-ss", cl.t6(ss), "-i", path, "-t", cl.t6(dur), "-map", "0:a:0",
           "-vn", "-af", "aresample=async=1:first_pts=0", "-ac", "1", "-ar", str(ASR_SR), "-f", "f32le", "-"]
    x = np.frombuffer(cl.run(cmd, binary=True).stdout, dtype="<f4").astype(np.float64)
    x = x[: len(x) // ASR_BLOCK * ASR_BLOCK]
    rms = np.sqrt(np.mean(x.reshape(-1, ASR_BLOCK) ** 2, axis=1)) if len(x) else np.zeros(0)
    return np.maximum(0.0, np.diff(rms, prepend=rms[:1])) if len(rms) else rms


def best_lag(a, b):
    """(lag, r): lag in blocks by which curve a (SRC) is late against curve b (ASR audio), best Pearson r.

    Rule fix (ASR on the video's clock, script spec step 9): the spec pairs a[max(0,-lag):] with b[max(0,lag):]
    without saying which file is a; with a = SRC a positive lag means SRC is EARLY, against "+ = SRC's audio is
    late". Here a[i + lag] is paired with b[i], so +lag = SRC late (tested: SRC delayed 40 ms reads +40 ms).
    """
    import numpy as np
    best = (None, -1.0)
    for lag in range(-ASR_MAX_LAG, ASR_MAX_LAG + 1):
        n = min(len(a) - max(lag, 0), len(b) - max(-lag, 0))
        if n < ASR_MIN_N:
            continue
        x = a[max(lag, 0):max(lag, 0) + n]
        y = b[max(-lag, 0):max(-lag, 0) + n]
        if x.std() == 0 or y.std() == 0:
            continue
        r = float(np.corrcoef(x, y)[0, 1])
        if r > best[1]:
            best = (lag, r)
    return best


def asr_offset(src, audio, ffmpeg, dur):
    """Median offset in seconds over the judged windows (None if none is judged) and the per-window rows."""
    win = min(ASR_WIN_S, dur)
    starts = sorted({0.0, max(0.0, dur / 2 - ASR_WIN_S / 2), max(0.0, dur - ASR_WIN_S)})
    rows, judged = [], []
    for ss in starts:
        lag, r = best_lag(onset_curve(src, ffmpeg, ss, win), onset_curve(audio, ffmpeg, ss, win))
        ok = lag is not None and r > ASR_MIN_R
        rows.append({"start_s": round(ss, 3), "offset_ms": round(lag * ASR_BLOCK / ASR_SR * 1000) if ok else None,
                     "r": round(r, 3)})
        if ok:
            judged.append(lag * ASR_BLOCK / ASR_SR)
    return (round(statistics.median(judged), 6) if judged else None), rows


# ---------------------------------------------------------------- main

def build_facts(args, ffmpeg, ffprobe):
    src = str(Path(args.src))
    info = cl.probe(src, ffmpeg, ffprobe)
    asr_info = None
    if args.asr_audio:   # checked first: a bad --asr-audio is a usage error even when SRC has no audio
        asr_info = cl.probe(args.asr_audio, ffmpeg, ffprobe)
        if asr_info["audio"] is None:
            raise cl.ClipError("bad_asr_audio", f"--asr-audio {args.asr_audio} has no audio stream", exit_code=2)
    v = info["video"]
    if v is None:
        raise cl.ClipError("no_video", f"{src} has no video stream",
                           hint="pass the merged download (video + audio), not the audio-only file")
    warnings = []
    a = info["audio"]
    ff = first_frames(src, ffmpeg, a is not None)

    fps_r, fps_avg = v["fps_r"], v["fps_avg"]
    if fps_r is None and fps_avg is None:
        fps_r = Fraction(30)
        warnings.append("no_rate: the source states no frame rate; assumed 30/1")
    fps_r = fps_r or fps_avg
    fps_avg = fps_avg or fps_r
    vfr = abs(fps_avg - fps_r) / fps_r > VFR_TOL
    canvas = parse_canvas(args.canvas, fps_avg, fps_r)

    sar = parse_sar(v["sar"])
    rotation = int(v["rotation"] or 0) % 360
    disp_w, disp_h = display_size(v["width"], v["height"], sar, rotation)
    matrix, hdr, colour, kind = colour_step(v, ff["tags"], v["codec"], warnings)

    filters = cl.has_filters(ffmpeg, ["zscale", "tonemap"])
    if args.assume_no_hdr_filters:
        filters = {k: False for k in filters}
    error = None
    if kind in ("hdr", "bt2020") and not (filters["zscale"] and (filters["tonemap"] or kind == "bt2020")):
        code = "hdr_no_zscale" if kind == "hdr" else "bt2020_no_zscale"
        error = {"code": code,
                 "message": f"the source is {'HDR (' + hdr + ')' if hdr else 'BT.2020'} and this ffmpeg lacks "
                            f"{'zscale/tonemap' if kind == 'hdr' else 'zscale'}",
                 "hint": "re-download SDR (yt-dlp -f \"bv[dynamic_range=SDR][ext=mp4]+ba[ext=m4a]/"
                         "bv[dynamic_range=SDR]+ba/bv*+ba/b\") or use an ffmpeg built with libzimg"}
        norm_vf = None
    else:
        parts = [f"fps={rate_arg(canvas)}"]
        if sar != 1:
            parts.append("scale=trunc(iw*sar/2)*2:ih,setsar=1")
        if colour:
            parts.append(colour)
        parts.append(TAGS_709)
        norm_vf = ",".join(parts)

    if vfr:
        warnings.append("vfr: never index frames of the raw file")
    if rotation:
        warnings.append(f"rotate: displayed {rotation} deg clockwise; ffmpeg's autorotate turns it before norm_vf "
                        "(never pass -noautorotate; never open the raw file with cv2)")

    audio = None
    if a is None:
        warnings.append("no_audio: the source has no audio stream")
    else:
        # First decoded audio frame vs first video frame. Precise to one audio frame only: on a late-muxed AAC
        # stream the first frame's time can include the encoder priming (0.228 s read for audio muxed 0.25 s late);
        # --asr-audio measures the true offset from the content.
        late = None
        if ff["a_pts"] is not None and ff["v_pts"] is not None:
            late = round(ff["a_pts"] - ff["v_pts"], 6)
            if abs(late) > 0.001:
                warnings.append(f"audio_start: the audio starts about {late:+.3f} s from the first video frame; "
                                "decode it with aresample=async=1:first_pts=0 so samples stay on the video's clock")
        audio = {"codec": a["codec"], "sample_rate": a["sample_rate"], "channels": a["channels"],
                 "layout": a["layout"], "start_vs_video_s": late}

    asr_s = None
    if asr_info:
        if a is None:
            warnings.append("asr_offset_unmeasured: SRC has no audio to compare with --asr-audio")
        else:
            durs = [x for x in (info["duration"], asr_info["duration"]) if x]
            dur = min(durs) if durs else ASR_WIN_S
            asr_s, rows = asr_offset(src, str(args.asr_audio), ffmpeg, dur)
            cl.log("asr offset windows: " + "; ".join(f"{w['start_s']} s: {w['offset_ms']} ms (r {w['r']})"
                                                       for w in rows))
            if asr_s is None:
                warnings.append("asr_offset_unmeasured: no window correlated (r <= 0.3); check sync by ear")
            elif abs(asr_s) > 1 / canvas and error is None:
                error = {"code": "asr_offset",
                         "message": f"the ASR audio is {asr_s * 1000:+.0f} ms off the video's audio "
                                    f"(more than one canvas frame, {1000 / float(canvas):.1f} ms)",
                         "hint": f"add {asr_s:+.6f} s to every ASR word time (+ = the video's audio is late), or "
                                 "transcribe the merged file's audio decoded with aresample=async=1:first_pts=0"}

    facts = {
        "ok": error is None, "version": SCRIPT_VERSION, "src": Path(src).resolve().as_posix(),
        "probe": info["probe"],
        "duration": round(info["duration"], 6) if info["duration"] is not None else None,
        "title": info["title"],
        "video": {"codec": v["codec"], "pix_fmt": v["pix_fmt"], "width": v["width"], "height": v["height"],
                  "display_w": disp_w, "display_h": disp_h, "sar": f"{sar.numerator}:{sar.denominator}",
                  "rotation": rotation, "fps_r": cl.frac_str(fps_r), "fps_avg": cl.frac_str(fps_avg), "vfr": vfr,
                  "color": {"range": v["color_range"], "space": v["color_space"],
                            "primaries": v["color_primaries"], "transfer": v["color_transfer"]},
                  "matrix_assumed": matrix, "hdr": hdr, "bit_depth": bit_depth(v["pix_fmt"])},
        "audio": audio,
        "canvas_fps": cl.frac_str(canvas),
        "norm_vf": norm_vf,
        "needs": {"retime": vfr or fps_r != canvas, "sar_fix": sar != 1,
                  "matrix_convert": kind in ("convert", "bt2020", "hdr"), "tonemap": kind == "hdr",
                  "rotate": rotation != 0},
        "filters": filters,
        "asr_offset_s": asr_s,
        "warnings": warnings,
    }
    if error:
        facts["error"] = error
    return facts


def main() -> int:
    ap = argparse.ArgumentParser(description="Probe a source once and write source_facts.json (ref 03 section 1).")
    ap.add_argument("src", help="the downloaded source (video + audio)")
    ap.add_argument("--asr-audio", help="the audio file Whisper transcribes, to measure its offset against SRC")
    ap.add_argument("--canvas", default="auto", help="auto (60 if fps_avg >= 50 else 30), 60, 30 or NUM/DEN")
    ap.add_argument("--out", help="write the facts here too (atomic)")
    ap.add_argument("--ffmpeg", help="ffmpeg executable (default: PATH, then imageio-ffmpeg)")
    ap.add_argument("--ffprobe", help="ffprobe executable, or 'none' to use ffmpeg only")
    ap.add_argument("--assume-no-hdr-filters", action="store_true", help=argparse.SUPPRESS)
    try:
        args = ap.parse_args()
    except SystemExit as e:
        if e.code in (0, None):
            raise
        raise cl.ClipError("usage", "bad arguments (see the usage above)", exit_code=2)

    ffmpeg = cl.find_ffmpeg(args.ffmpeg)
    ffprobe = cl.find_ffprobe(ffmpeg, args.ffprobe)
    cl.log(f"probe_source {SCRIPT_VERSION}: {args.src} via {'ffprobe' if ffprobe else 'ffmpeg'}")
    try:
        facts = build_facts(args, ffmpeg, ffprobe)
    except cl.ClipError as e:
        # A source that ran but failed (no video) replaces old facts, so no stale norm_vf survives a rerun.
        if args.out and e.exit_code == 1:
            cl.write_json_atomic(args.out, {**e.envelope(), "version": SCRIPT_VERSION})
        raise
    if args.out:
        cl.write_json_atomic(args.out, facts)
    cl.emit(facts)
    if not facts["ok"]:
        cl.log(f"error [{facts['error']['code']}]: {facts['error']['message']}\nhint: {facts['error']['hint']}")
        return 1
    cl.log(f"canvas {facts['canvas_fps']}, norm_vf: {facts['norm_vf']}")
    return 0


if __name__ == "__main__":
    cl.run_main(main)
