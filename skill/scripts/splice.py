"""splice.py - cut a clip's video segments and dialogue stem from the source and gate them (ref 03 section 2).

Usage:
  python -P splice.py --cutlist cutlist.json --source SRC --facts source_facts.json --outdir clips/NN
                      [--crf 12] [--keep-temp] [--ffmpeg PATH] [--ffprobe PATH|none]
  python -P splice.py --selftest [--workdir DIR] [--keep-temp] [--ffmpeg PATH] [--ffprobe PATH|none]

What it does:
  video    one segment per cut-list segment, read through the source facts' norm_vf, encoded with the seekable
           mezzanine flags (ref 03 section 4: .mov, libx264 veryfast CRF 12, yuv420p, cfr, a keyframe every
           second, video only, exactly `frames` frames), then joined by the concat demuxer with -c copy into
           <outdir>/cut.mov. Each segment seeks a whole canvas second early and trims on the canvas grid
           (settb=1/fps, trim=start_pts), so norm_vf's fps= sees the frame on screen at k_in even when it
           re-times the source (VFR, 24/25 -> 30, 50 -> 60).
  audio    ONE pre-rolled decode of the source audio to float 48 kHz mono, sliced per segment by sample index,
           30 ms linear ramps on every segment edge, written as <outdir>/dialogue.wav (pcm_f32le, exactly
           round(frames * 48000 / fps) samples).
  gates    (all must pass, else exit 1 and the outputs keep their temp names):
           frames         packets (and ffprobe's count when present) and decoded frames == cut-list frames
           pts_grid       every packet pts * time_base == i / fps (Fraction math)
           keyframe_gap   <= 1.05 s between keyframes (and from the last one to the end)
           frame_identity each segment's first/last frame matches canvas frame k_in / k_out - 1 of the source
                          better than its neighbours (grey 128x72 thumbnails; catches one-frame miscuts that a
                          frame count cannot see)
           stem_samples   dialogue.wav is 48 kHz mono with exactly round(frames * 48000 / fps) samples
           click          per splice: max |step| within +-5 ms <= 2 x the 99.9th percentile of |step| over the
                          +-250 ms around it
           zero_run       per splice: no run of >= 20 exact zeros within +-50 ms that the source does not have
  --selftest   builds lavfi fixtures (testsrc2 + 440 Hz sine, AAC) at 30, 30000/1001 and 60 fps, cuts them with a
               fixed keep list, and requires the gates to pass; the negative controls must fail their gate:
               per-segment AAC -> stem_samples, 3-decimal seek times -> frame_identity, no ramps -> click.
               Files go to --workdir (kept) or a temp folder (removed unless --keep-temp).
Output (stdout): {"ok", "version", "frames", "outdir", "files": {"video": "cut.mov", "dialogue": "dialogue.wav"},
                  "promoted", "gates": {name: {"ok", "measured", "limit"}}, "splices": [...], "warnings"}
Exit codes: 0 all gates pass; 1 a gate or step failed; 2 usage error or unreadable input.
"""
import argparse
import math
import os
import re
import shutil
import sys
import tempfile
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cliplib as cl  # noqa: E402
import cutlist  # noqa: E402

SCRIPT_VERSION = "1.0.0"
# Approach adapted from HyperFrames (github.com/heygen-com/hyperframes, Apache-2.0); independent Python implementation.

SR = cutlist.SR
US = cutlist.US
RAMP = 1440                 # 30 ms at 48 kHz (ref 03 section 2 Ramps on every edge)
CLICK_WIN = 240             # +-5 ms around a splice ...
CLICK_CTX = 12000           # ... against +-250 ms of context
CLICK_PCT = 99.9
CLICK_MAX = 2.0
ZERO_WIN = 2400             # +-50 ms
ZERO_RUN_MAX = 20           # exact-zero runs must stay shorter than this
KEYFRAME_GAP_MAX = 1.05
THUMB_W, THUMB_H = 128, 72
IDENT_EXCESS = 0.25         # grey levels a neighbour may beat the target frame by (measured: right >= 0.7 below, wrong >= 0.7 above)
IDENT_MAD = 4.0             # grey levels; a CRF 12 copy of the same frame measured <= 0.31
TAGS_709 = "setparams=colorspace=bt709:color_primaries=bt709:color_trc=bt709:range=tv"
SELFTEST_RATES = ("30/1", "30000/1001", "60/1")
# HF's keeps plus one starting at 6.067 s: its frame time (6.0667 s at 30/60 fps, 6.0727 s at 29.97) rounds UP at
# 3 decimals at every rate, so a 3-decimal seek must start that segment a frame late.
SELFTEST_KEEPS = (("0.137", "1.913"), ("2.845", "4.111"), ("4.9", "5.47"), ("6.067", "7.5"))
SELFTEST_DUR = 8


def mezz(crf):
    """Seekable mezzanine flags (ref 03 section 4), video only."""
    return ["-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf), "-pix_fmt", "yuv420p",
            "-fps_mode", "cfr", "-force_key_frames", "expr:gte(t,n_forced)"]


def T(k, fps):
    """Frame k's time for ffmpeg: k/fps floored to the microsecond, 6 decimals (ref 03 section 2 Frame grid)."""
    u = math.floor(Fraction(k) / Fraction(fps) * US)
    return f"{u // US}.{u % US:06d}"


def norm_vf_of(facts, fps, where):
    vf = facts.get("norm_vf") if isinstance(facts, dict) else None
    m = re.match(r"\s*fps=([^,:]+)", vf or "")
    if not m or cl.parse_rate(m.group(1)) != fps:
        raise cl.ClipError("bad_facts", f"{where}: norm_vf must start with fps={cl.frac_str(fps)} (got {vf!r})",
                           hint="rerun probe_source.py; the cut list and the facts must share the canvas fps",
                           exit_code=2)
    return vf


# ---------------------------------------------------------------- video

def encode_segment(src, seg, fps, norm_vf, out, ffmpeg, crf):
    # Rule problem (ref 03 section 2 Video splice): `-ss T(k_in) -i SRC -vf <norm_vf>` drops the source frame that
    # is on screen at T(k_in) but started before it whenever norm_vf's fps= re-times the source (25 or 23.976 ->
    # 30, VFR -> 30: 2 of 150 frames wrong in testing), because accurate seek discards it before fps= sees it.
    # So seek >= 1 s early to a whole canvas frame k_a and trim on the canvas grid instead (pts == k - k_a after
    # settb). setpts drops the stream rate, hence -r (without it the encoder fell back to 25 fps).
    ka = max(0, seg["k_in"] - math.ceil(fps))
    tb = 1 / Fraction(fps)
    vf = f"{norm_vf},settb={tb.numerator}/{tb.denominator},trim=start_pts={seg['k_in'] - ka},setpts=PTS-STARTPTS"
    cmd = [ffmpeg, "-hide_banner", "-nostdin", "-v", "error", "-y"]
    if ka:
        cmd += ["-ss", T(ka, fps)]
    cmd += ["-i", str(src), "-map", "0:V:0", "-vf", vf, "-frames:v", str(seg["frames"]), "-r", cl.frac_str(fps),
            "-map_metadata", "-1", *mezz(crf), str(out)]
    cl.run(cmd)


def encode_segment_3dp(src, seg, fps, norm_vf, out, ffmpeg, crf):
    """Negative control only: the plain per-segment seek with times printed to 3 decimals (the known miscut)."""
    cmd = [ffmpeg, "-hide_banner", "-nostdin", "-v", "error", "-y", "-ss", f"{float(seg['k_in'] / fps):.3f}",
           "-i", str(src), "-map", "0:V:0", "-vf", norm_vf, "-frames:v", str(seg["frames"]), "-map_metadata", "-1",
           *mezz(crf), str(out)]
    cl.run(cmd)


def concat(parts, out, ffmpeg):
    """Concat demuxer, -c copy; the list sits beside the parts with bare names (no -safe 0, no escaping)."""
    folder = Path(parts[0]).parent
    lst = folder / f"concat-{os.getpid()}-{len(parts)}.txt"
    lst.write_text("".join(f"file '{Path(p).name}'\n" for p in parts), encoding="utf-8")
    cl.run([ffmpeg, "-hide_banner", "-nostdin", "-v", "error", "-y", "-f", "concat", "-i", str(lst), "-c", "copy",
            "-map_metadata", "-1", str(out)])


def build_video(src, segs, fps, norm_vf, tmpdir, out, ffmpeg, crf, encoder=encode_segment):
    parts = []
    for s in segs:
        part = Path(tmpdir) / f"seg_{s['i']:04d}.mov"
        encoder(src, s, fps, norm_vf, part, ffmpeg, crf)
        got = cl.count_frames(part, ffmpeg)
        if got != s["frames"]:
            raise cl.ClipError("segment_frames", f"segment {s['i']} (k {s['k_in']}-{s['k_out']}) has {got} frames, "
                               f"expected {s['frames']}", hint="the source may end before the cut; check its duration")
        cl.log(f"segment {s['i']}: {got} frames from canvas frame {s['k_in']}")
        parts.append(part)
    concat(parts, out, ffmpeg)


# ---------------------------------------------------------------- audio

def stem_layout(segs, fps):
    """(base, [(x_offset, stem_start, m)]): base = source sample of the first k_in; m from the OUTPUT frame offsets,
    so the lengths sum to round(total * SR / fps) exactly (ref 03 section 2 Ramps on every edge)."""
    base = cutlist.rnd(Fraction(segs[0]["k_in"] * SR) / fps)
    lay = []
    for s in segs:
        a = cutlist.rnd(Fraction(s["k_in"] * SR) / fps) - base
        st = cutlist.rnd(Fraction(s["out_frame"] * SR) / fps)
        m = cutlist.rnd(Fraction((s["out_frame"] + s["frames"]) * SR) / fps) - st
        lay.append((a, st, m))
    return base, lay


def source_window(src, segs, fps, ffmpeg, channels, layout=None):
    """The pre-rolled source decode covering every segment, zero-padded if the source audio ends early."""
    import numpy as np
    base, lay = stem_layout(segs, fps)
    need = max(a + m for a, _, m in lay)
    x = cutlist.decode_mono(src, ffmpeg, base, need, channels, layout)
    warnings = []
    if len(x) < need:
        warnings.append(f"audio_short: the source audio ends {(need - len(x)) / SR * 1000:.1f} ms before the cut; "
                        "the stem is padded with silence")
        x = np.concatenate([x, np.zeros(need - len(x), np.float32)])
    return x, lay, warnings


def assemble_stem(x, lay, ramps=True):
    import numpy as np
    parts = []
    for a, _, m in lay:
        seg = x[a:a + m].astype(np.float32, copy=True)
        n = min(RAMP, m // 4)
        if ramps and n > 0:
            r = np.linspace(0, 1, n, dtype=np.float32)
            seg[:n] *= r
            seg[m - n:] *= r[::-1]
        parts.append(seg)
    return np.concatenate(parts)


def read_pcm(path, ffmpeg, af=None):
    """Float32 samples of a file's first audio stream, interleaved as stored (no resampling unless af asks)."""
    import numpy as np
    cmd = [ffmpeg, "-v", "error", "-nostdin", "-i", str(path), "-map", "0:a:0"]
    if af:
        cmd += ["-af", af]
    raw = cl.run(cmd + ["-f", "f32le", "-acodec", "pcm_f32le", "-"], binary=True).stdout
    return np.frombuffer(raw, dtype="<f4").copy()


# ---------------------------------------------------------------- gates

def _gray(raw):
    import numpy as np
    n = len(raw) // (THUMB_W * THUMB_H)
    return np.frombuffer(raw[:n * THUMB_W * THUMB_H], np.uint8).reshape(n, THUMB_H, THUMB_W).astype(np.float32)


def cut_thumbs(video, ffmpeg):
    """Every decoded frame of the cut as a grey thumbnail (the count doubles as the decoded-frame gate)."""
    raw = cl.run([ffmpeg, "-v", "error", "-nostdin", "-i", str(video), "-map", "0:v:0", "-vf",
                  f"scale={THUMB_W}:{THUMB_H}:flags=area,format=gray", "-fps_mode", "passthrough", "-f", "rawvideo",
                  "-pix_fmt", "gray", "-"], binary=True).stdout
    return _gray(raw)


def ref_thumbs(src, fps, norm_vf, needed, ffmpeg):
    """{canvas frame: grey thumbnail} of the source read through norm_vf.

    Frames are found by pts on the canvas grid (showinfo after settb=1/fps), from a seek >= 1 s before each
    cluster, so the reference never depends on the segment cutter's trim, -frames:v or concat."""
    pre = math.ceil(fps)
    tb = 1 / Fraction(fps)
    clusters = []
    for k in sorted({k for k in needed if k >= 0}):
        if clusters and k - clusters[-1][-1] <= 2 * pre:
            clusters[-1].append(k)
        else:
            clusters.append([k])
    out = {}
    for ks in clusters:
        kr = max(0, ks[0] - pre)
        sel = "+".join(f"eq(pts\\,{k - kr})" for k in ks)
        vf = (f"{norm_vf},settb={tb.numerator}/{tb.denominator},select='{sel}',showinfo,format=yuv420p,"
              f"scale={THUMB_W}:{THUMB_H}:flags=area,format=gray")
        cmd = [ffmpeg, "-hide_banner", "-nostdin", "-v", "info"]
        if kr:
            cmd += ["-ss", T(kr, fps)]
        cmd += ["-i", str(src), "-map", "0:V:0", "-vf", vf, "-frames:v", str(len(ks)), "-fps_mode", "passthrough",
                "-f", "rawvideo", "-pix_fmt", "gray", "-"]
        cp = cl.run(cmd, binary=True)
        pts = [int(p) for p in re.findall(r"\[Parsed_showinfo_\d+ @ [^\]]+\] n:\s*\d+ pts:\s*(-?\d+)", cp.stderr)]
        for fr, p in zip(_gray(cp.stdout), pts):
            out[kr + p] = fr
    return out


def identity_gate(thumbs, ref, segs):
    import numpy as np
    bad, detail = 0, []
    for s in segs:
        last = s["out_frame"] + s["frames"] - 1
        for edge, f, k in (("first", s["out_frame"], s["k_in"]), ("last", last, s["k_out"] - 1)):
            if f >= len(thumbs) or k not in ref:
                bad += 1
                detail.append({"seg": s["i"], "edge": edge, "mad": None, "excess": None})
                continue
            # mean |difference| to the target canvas frame and to its neighbours; a neighbour that matches
            # clearly better means the segment edge is a frame off
            d = {kk: float(np.abs(thumbs[f] - ref[kk]).mean()) for kk in (k - 1, k, k + 1) if kk in ref}
            others = [v for kk, v in d.items() if kk != k]
            excess = d[k] - min(others) if others else 0.0
            ok = d[k] <= IDENT_MAD and excess <= IDENT_EXCESS
            bad += 0 if ok else 1
            detail.append({"seg": s["i"], "edge": edge, "mad": round(d[k], 3), "excess": round(excess, 3)})
    return {"ok": bad == 0, "measured": bad, "limit": 0, "detail": detail}


def ffprobe_packets(path, ffprobe):
    cp = cl.run([ffprobe, "-v", "error", "-count_packets", "-select_streams", "v:0", "-show_entries",
                 "stream=nb_read_packets", "-of", "csv=p=0", str(path)])
    return int(cp.stdout.strip().split(",")[0])


def video_gates(video, segs, fps, src, norm_vf, ffmpeg, ffprobe):
    total = sum(s["frames"] for s in segs)
    tb, rows = cl.packet_times(video, ffmpeg)
    thumbs = cut_thumbs(video, ffmpeg)
    counts = {"packets": len(rows), "decoded": len(thumbs)}
    if ffprobe:
        counts["ffprobe_packets"] = ffprobe_packets(video, ffprobe)
    gates = {"frames": {"ok": all(v == total for v in counts.values()), "measured": counts["decoded"],
                        "limit": total, "detail": counts}}
    off = sum(1 for i, (pts, _) in enumerate(rows) if pts * tb * fps != i)
    gates["pts_grid"] = {"ok": off == 0 and bool(rows), "measured": off, "limit": 0}
    kf = sorted(cl.keyframe_times(video, ffmpeg))
    end = float(Fraction(total) / fps)
    marks = [0.0] + kf + [end]
    gap = max(b - a for a, b in zip(marks, marks[1:]))
    gates["keyframe_gap"] = {"ok": bool(kf) and gap <= KEYFRAME_GAP_MAX, "measured": round(gap, 6),
                             "limit": KEYFRAME_GAP_MAX}
    needed = [s[edge] + dk for s in segs for edge, dks in (("k_in", (-1, 0, 1)), ("k_out", (-2, -1, 0))) for dk in dks]
    gates["frame_identity"] = identity_gate(thumbs, ref_thumbs(src, fps, norm_vf, needed, ffmpeg), segs)
    return gates


def _longest_true(b):
    import numpy as np
    if not b.any():
        return 0
    d = np.diff(np.concatenate(([0], b.astype(np.int8), [0])))
    return int((np.flatnonzero(d == -1) - np.flatnonzero(d == 1)).max())


def audio_gates(stem, lay, x, format_ok=True):
    """stem_samples, click and zero_run gates; x is the source decode the layout indexes (ref 03 section 2)."""
    import numpy as np
    expected = lay[-1][1] + lay[-1][2]
    gates = {"stem_samples": {"ok": bool(format_ok) and len(stem) == expected, "measured": len(stem),
                              "limit": expected}}
    d = np.abs(np.diff(stem.astype(np.float64)))
    starts = np.array([st for _, st, _ in lay])
    offs = np.array([a for a, _, _ in lay])
    splices, worst, zmax, clicks_ok = [], 0.0, 0, True
    for _, st, _ in lay[1:]:
        # Click: the largest step within +-5 ms of the splice against the 99.9th percentile step around it.
        inside = d[max(0, st - CLICK_WIN):max(0, min(len(d), st + CLICK_WIN))]
        ctx = np.concatenate((d[max(0, st - CLICK_CTX):max(0, st - CLICK_WIN)],
                              d[min(len(d), st + CLICK_WIN):min(len(d), st + CLICK_CTX)]))
        p = float(np.percentile(ctx, CLICK_PCT)) if ctx.size else 0.0
        mx = float(inside.max()) if inside.size else 0.0
        ok = mx <= CLICK_MAX * p if p > 0 else mx == 0.0
        ratio = mx / p if p > 0 else (0.0 if mx == 0.0 else None)
        clicks_ok &= ok
        worst = None if worst is None or ratio is None else max(worst, ratio)
        # Exact zeros the source does not have at the mapped position (ramp end points count; they are single).
        lo, hi = max(0, st - ZERO_WIN), min(len(stem), st + ZERO_WIN)
        js = np.arange(lo, hi)
        seg = np.clip(np.searchsorted(starts, js, side="right") - 1, 0, len(lay) - 1)
        idx = offs[seg] + js - starts[seg]
        src_zero = np.zeros(len(js), bool)
        valid = (idx >= 0) & (idx < len(x))
        src_zero[valid] = x[idx[valid]] == 0
        run = _longest_true((stem[lo:hi] == 0) & ~src_zero)
        zmax = max(zmax, run)
        splices.append({"stem_sample": int(st), "click_ratio": None if ratio is None else round(ratio, 3),
                        "zero_run": run})
    gates["click"] = {"ok": clicks_ok, "measured": None if worst is None else round(worst, 3), "limit": CLICK_MAX}
    gates["zero_run"] = {"ok": zmax < ZERO_RUN_MAX, "measured": zmax, "limit": ZERO_RUN_MAX - 1}
    return gates, splices


# ---------------------------------------------------------------- one clip

def splice_clip(cut, src, facts, outdir, ffmpeg, ffprobe, crf=12, keep_temp=False, where="facts"):
    fps = cl.parse_rate(cut["fps"])
    canvas = cl.parse_rate(facts.get("canvas_fps")) if isinstance(facts, dict) else None
    if canvas != fps:
        raise cl.ClipError("fps_mismatch", f"cut list fps {cut['fps']} != canvas_fps "
                           f"{cl.frac_str(canvas) if canvas else None} in {where}",
                           hint="rebuild the cut list from these source facts", exit_code=2)
    norm_vf = norm_vf_of(facts, fps, where)
    segs = cut["segments"]
    total = sum(s["frames"] for s in segs)
    info = cl.probe(src, ffmpeg, ffprobe)
    if not info.get("video"):
        raise cl.ClipError("no_video", f"{src} has no video stream", exit_code=2)
    a = info.get("audio")
    if not a:
        raise cl.ClipError("no_audio", f"{src} has no audio stream (the dialogue stem needs one)", exit_code=2)
    end_s = float(Fraction(segs[-1]["k_out"]) / fps)
    if info.get("duration") and end_s > info["duration"] + float(1 / fps):
        raise cl.ClipError("cut_past_end", f"the cut ends at {end_s:.3f} s but {src} lasts {info['duration']:.3f} s",
                           hint="the cut list was built for another source", exit_code=2)

    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    final = {"video": outdir / "cut.mov", "dialogue": outdir / "dialogue.wav"}
    tmp = {k: Path(cl.tmp_path(p)) for k, p in final.items()}
    work = Path(tempfile.mkdtemp(prefix=".splice-", dir=outdir))
    try:
        build_video(src, segs, fps, norm_vf, work, tmp["video"], ffmpeg, crf)
        x, lay, warnings = source_window(src, segs, fps, ffmpeg, a.get("channels"), a.get("layout"))
        cl.write_wav_f32(tmp["dialogue"], assemble_stem(x, lay))
        gates = video_gates(tmp["video"], segs, fps, src, norm_vf, ffmpeg, ffprobe)
        wav = cl.probe(tmp["dialogue"], ffmpeg, ffprobe).get("audio") or {}
        ag, splices = audio_gates(read_pcm(tmp["dialogue"], ffmpeg), lay, x,
                                  wav.get("sample_rate") == SR and wav.get("channels") == 1)
        gates.update(ag)
    except BaseException:  # a failed step leaves no half-written outputs behind
        for p in tmp.values():
            p.unlink(missing_ok=True)
        raise
    finally:
        if keep_temp:
            cl.log(f"segments kept in {work}")
        else:
            shutil.rmtree(work, ignore_errors=True)
    ok = all(g["ok"] for g in gates.values())
    if ok:
        for k in final:
            cl.replace_with_retry(tmp[k], final[k])
    files = {k: (final[k] if ok else tmp[k]).name for k in final}
    for name, g in gates.items():
        cl.log(f"gate {name}: {'ok' if g['ok'] else 'FAIL'} measured {g['measured']} limit {g['limit']}")
    return {"ok": ok, "version": SCRIPT_VERSION, "frames": total, "outdir": str(outdir), "files": files,
            "promoted": ok, "gates": gates, "splices": splices, "warnings": warnings}


# ---------------------------------------------------------------- self-test

def _fixture(path, rate, ffmpeg):
    cl.run([ffmpeg, "-hide_banner", "-nostdin", "-v", "error", "-y",
            "-f", "lavfi", "-i", f"testsrc2=size=640x360:rate={rate}:duration={SELFTEST_DUR}",
            "-f", "lavfi", "-i", f"sine=frequency=440:sample_rate={SR}:duration={SELFTEST_DUR}",
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ac", "2",
            str(path)])


def _failed(gates):
    return sorted(k for k, g in gates.items() if not g["ok"])


def _per_segment_aac(src, segs, fps, norm_vf, folder, ffmpeg):
    """Negative control: A+V segments with their own AAC encode, joined with -c copy (priming at every splice)."""
    parts = []
    for s in segs:
        part = folder / f"seg_{s['i']:04d}.mov"
        cl.run([ffmpeg, "-hide_banner", "-nostdin", "-v", "error", "-y", "-ss", T(s["k_in"], fps), "-i", str(src),
                "-map", "0:V:0", "-map", "0:a:0", "-vf", norm_vf, "-t", T(s["frames"], fps), "-c:v", "libx264",
                "-preset", "veryfast", "-crf", "12", "-pix_fmt", "yuv420p", "-fps_mode", "cfr",
                "-c:a", "aac", "-b:a", "192k", "-ar", str(SR), str(part)])
        parts.append(part)
    out = folder / "cut_aac.mov"
    concat(parts, out, ffmpeg)
    return read_pcm(out, ffmpeg, af=f"aresample={SR},{cutlist.mono_pan(2)}")


def selftest(args, ffmpeg, ffprobe):
    own = not args.workdir
    work = Path(tempfile.mkdtemp(prefix="splice-selftest-")) if own else Path(args.workdir)
    work.mkdir(parents=True, exist_ok=True)
    report, all_ok = {}, True
    try:
        for rate in SELFTEST_RATES:
            fps = cl.parse_rate(rate)
            d = work / f"r{fps.numerator}_{fps.denominator}"
            d.mkdir(parents=True, exist_ok=True)
            src = d / "fx.mp4"
            _fixture(src, rate, ffmpeg)
            facts = {"canvas_fps": rate, "norm_vf": f"fps={rate},{TAGS_709}"}
            segs = cutlist.segments_from_frames(
                [(cutlist.rnd(Fraction(a) * fps), cutlist.rnd(Fraction(b) * fps)) for a, b in SELFTEST_KEEPS], fps)
            cut = {"fps": cl.frac_str(fps), "segments": segs, "frames": sum(s["frames"] for s in segs)}
            cl.log(f"selftest {rate}: positive")
            pos = splice_clip(cut, src, facts, d / "positive", ffmpeg, ffprobe, where="selftest")
            entry = {"positive": {"ok": pos["ok"], "failed": _failed(pos["gates"]), "gates": pos["gates"]},
                     "negatives": {}}
            norm_vf = facts["norm_vf"]

            cl.log(f"selftest {rate}: negative control per-segment AAC")
            x, lay, _ = source_window(src, segs, fps, ffmpeg, 2)
            neg = d / "neg_aac"
            neg.mkdir(exist_ok=True)
            g, _ = audio_gates(_per_segment_aac(src, segs, fps, norm_vf, neg, ffmpeg), lay, x)
            entry["negatives"]["per_segment_aac"] = {"expect": "stem_samples", "failed": _failed(g)}

            cl.log(f"selftest {rate}: negative control 3-decimal seeks")
            neg = d / "neg_3dp"
            neg.mkdir(exist_ok=True)
            build_video(src, segs, fps, norm_vf, neg, neg / "cut_3dp.mov", ffmpeg, 12, encoder=encode_segment_3dp)
            g = video_gates(neg / "cut_3dp.mov", segs, fps, src, norm_vf, ffmpeg, ffprobe)
            entry["negatives"]["decimals3"] = {"expect": "frame_identity", "failed": _failed(g)}

            cl.log(f"selftest {rate}: negative control no ramps")
            g, _ = audio_gates(assemble_stem(x, lay, ramps=False), lay, x)
            entry["negatives"]["no_ramps"] = {"expect": "click", "failed": _failed(g)}

            for n in entry["negatives"].values():
                n["ok"] = n["expect"] in n["failed"]
            entry["ok"] = pos["ok"] and all(n["ok"] for n in entry["negatives"].values())
            all_ok &= entry["ok"]
            cl.log(f"selftest {rate}: {'ok' if entry['ok'] else 'FAIL'}")
            report[cl.frac_str(fps)] = entry
    finally:
        if own and not args.keep_temp:
            shutil.rmtree(work, ignore_errors=True)
    return {"ok": all_ok, "version": SCRIPT_VERSION, "ffmpeg": cl.ffmpeg_version(ffmpeg), "selftest": report,
            "workdir": None if own and not args.keep_temp else str(work)}


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
    ap = _Parser(description="Cut cut.mov + dialogue.wav from a cut list and gate them (ref 03 section 2).")
    ap.add_argument("--cutlist")
    ap.add_argument("--source")
    ap.add_argument("--facts")
    ap.add_argument("--outdir")
    ap.add_argument("--crf", type=int, default=12)
    ap.add_argument("--keep-temp", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--workdir", help="--selftest: where to build the fixtures (kept)")
    ap.add_argument("--ffmpeg")
    ap.add_argument("--ffprobe", help="PATH or none")
    args = ap.parse_args()
    ffmpeg = cl.find_ffmpeg(args.ffmpeg)
    ffprobe = cl.find_ffprobe(ffmpeg, args.ffprobe)
    if args.selftest:
        res = selftest(args, ffmpeg, ffprobe)
    else:
        missing = [f"--{n}" for n in ("cutlist", "source", "facts", "outdir") if not getattr(args, n)]
        if missing:
            ap.error(f"the following arguments are required: {', '.join(missing)} (or --selftest)")
        res = splice_clip(cutlist.load(args.cutlist), args.source, cl.read_json(args.facts), args.outdir, ffmpeg,
                          ffprobe, args.crf, args.keep_temp, where=args.facts)
    cl.emit(res)
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    cl.run_main(main)
