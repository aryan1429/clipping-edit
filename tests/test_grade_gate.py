"""Tests for skill/scripts/grade_gate.py. Run from the repo root:
    python -P tests/test_grade_gate.py

All media are synthetic (lavfi through ffmpeg, plus numpy frames piped to ffmpeg for the skin cases) and live
in a fresh temp folder that is deleted at the end. The gate runs as a subprocess through its real CLI. Every
check prints one line; the exit code is 0 only when every check passed.

Covered:
- positive control: ref 01's reference chain (YUV eq + unsharp, then one RGB stage with vibrance,
  colorbalance and the thresholded half-res glow, matrices named at each hop) on a dull, soft source passes.
- negative controls that must FAIL: an ungraded copy (luma, sat, sharp); a lifted-black screen glow (p2 haze);
  an over-pushed eq on bright footage (clip); a strong warm push (warmth); captions alone on an ungraded clip
  pass sharpness without a mask and fail luma/sat/sharp with it; skin hue pushed to 40 deg; a flattened dark
  face (dark_skin); a blown face (face_clip).
- index pairing: a -g 300 re-encode reads ratios of 1; accent windows are skipped and leave the ratios of the
  clean grade; the 30000/1001 grid starts at frame 15; metrics() imported from the module reproduces the
  report (one definition for the gate and extract_ref.py); circular hue mean.
- refusals (exit 2): an edited/ file without --mask/--exclude, size / fps / length mismatch, a BT.601-tagged
  input, too few samples, a bad --waive name; --ffprobe none gives the same report; untagged input warns.
"""
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from fractions import Fraction
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixtures as fx  # noqa: E402  (also puts skill/scripts on sys.path)
import cliplib as cl  # noqa: E402
import grade_gate  # noqa: E402

SCRIPT = fx.ROOT / "skill" / "scripts" / "grade_gate.py"
FF = fx.ffmpeg()
W, H = 1080, 1440
TAGS = fx.TAGS_709
ENC = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p", *fx.X264_709]
# A dull, soft "raw" plate: an upscaled, blurred, darkened and desaturated card (headroom left for a grade).
RAW_VF = (f"scale={W}:{H}:flags=bicubic,gblur=sigma=2,eq=brightness=-0.1:contrast=0.8:saturation=0.4,"
          f"format=yuv420p,{TAGS}")
# Ref 01 section 7's chain, laid out per ref 04 section 3: YUV filters first, then one RGB stage with the
# matrix named on the way in and out, and the glow thresholded at half resolution.
GLOW = (f"split[a][b];[b]scale=iw/2:ih/2,lutrgb=r='val*gt(val,127)':g='val*gt(val,127)':b='val*gt(val,127)',"
        f"gblur=sigma=10,scale={W}:{H}[g];[a][g]blend=all_mode=screen:all_opacity=0.15")
TO_RGB = "scale=in_color_matrix=bt709:in_range=tv,format=gbrp"
TO_YUV = f"scale=out_color_matrix=bt709:out_range=tv,format=yuv420p,{TAGS}"
REF01 = (f"eq=brightness=0.04:contrast=1.12:saturation=1.2,unsharp=5:5:1.0:5:5:0.0,{TO_RGB},"
         f"vibrance=intensity=0.3,colorbalance=rm=0.02:bm=-0.02,{GLOW},{TO_YUV}")
FAILS = []


def check(name, cond, detail=""):
    print(f"{'ok  ' if cond else 'FAIL'} {name}" + (f"  [{detail}]" if detail and not cond else ""), flush=True)
    if not cond:
        FAILS.append(name)


def gate(*args):
    cp = subprocess.run([sys.executable, "-P", str(SCRIPT), *map(str, args)], capture_output=True)
    try:
        js = json.loads(cp.stdout.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        js = None
    return cp.returncode, js, cp.stderr.decode("utf-8", errors="replace")


def lavfi(out, src, vf, enc=ENC):
    cl.run([FF, "-v", "error", "-y", "-f", "lavfi", "-i", src, "-vf", vf, *enc, str(out)])
    return out


def grade(src, out, graph, enc=ENC):
    cl.run([FF, "-v", "error", "-y", "-i", str(src), "-filter_complex", f"[0:v]{graph}", *enc, str(out)])
    return out


def pipe_frames(out, frames, fps=30):
    """Encode RGB uint8 frames (n, h, w, 3) as tagged BT.709 tv H.264, converting with a named matrix."""
    n, h, w, _ = frames.shape
    cmd = [FF, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(fps),
           "-i", "-", "-vf", TO_YUV, *ENC[:4], "-crf", "8", *ENC[6:], str(out)]
    cl.run(cmd, input=frames.tobytes())
    return out


def failed(js):
    return set((js or {}).get("failed", []))


def gate_ok(js, name):
    return ((js or {}).get("gates", {}).get(name) or {}).get("ok")


def summary(js):
    return (js or {}).get("log") or (js or {}).get("error")


def caption_png(path, text):
    import cv2
    img = np.zeros((150, 864, 4), np.uint8)
    for colour, thick in (((0, 0, 0, 255), 14), ((255, 255, 255, 255), 5)):
        cv2.putText(img, text, (20, 110), cv2.FONT_HERSHEY_DUPLEX, 3.2, colour, thick, cv2.LINE_AA)
    cv2.imwrite(str(path), img)
    return path


# ---------------------------------------------------------------- cases

def case_core(d):
    raw = lavfi(d / "raw.mp4", f"testsrc2=s=270x360:r=30:d=10", RAW_VF)
    good = grade(raw, d / "ref01.mp4", REF01)
    code, js, err = gate(raw, good, "--json", d / "report.json")
    check("positive: ref 01 chain passes every gate (exit 0)", code == 0 and js and js["ok"] is True,
          summary(js) or err[-300:])
    on_disk = cl.read_json(d / "report.json") if (d / "report.json").is_file() else None
    check("positive: --json report equals stdout", on_disk == js)
    check("positive: log line in the ref format", bool(js) and js["log"].startswith("grade ") and " luma x" in js["log"]
          and " sat x" in js["log"] and " sharp x" in js["log"] and " p2 " in js["log"] and "frames=10" in js["log"],
          summary(js))
    check("positive: samples are t = i + 0.5 s at 30 fps", bool(js) and js["frames_used"] == [15 + 30 * i for i in range(10)],
          js and js["frames_used"])
    check("positive: face gates not applicable without --faces",
          bool(js) and all(js["gates"][k]["ok"] is None for k in ("skin", "dark_skin", "face_clip")))

    copy = grade(raw, d / "copy.mp4", "null", enc=ENC + ["-g", "300"])
    code, js2, _ = gate(raw, copy)
    check("negative: ungraded copy fails luma, sat and sharp (exit 1)",
          code == 1 and {"luma", "sat", "sharp"} <= failed(js2), summary(js2))
    check("pairing: -g 300 re-encode reads every ratio within 0.98-1.02",
          bool(js2) and all(0.98 <= js2["ratios"][k] <= 1.02 for k in ("luma", "sat", "sharp", "contrast")),
          js2 and js2["ratios"])

    # ref 01's chain with the glow done wrong: unthresholded, wide and at 50%, so it lifts the blacks
    haze = grade(raw, d / "haze.mp4", REF01.replace(GLOW, f"split[a][b];[b]scale=iw/2:ih/2,gblur=sigma=30,"
                                                          f"scale={W}:{H}[g];[a][g]blend=all_mode=screen:all_opacity=0.5"))
    code, js3, _ = gate(raw, haze)
    check("negative: lifted-black screen glow fails only the haze gate (p2), luma/sat/sharp pass",
          code == 1 and failed(js3) == {"p2"}, summary(js3))

    warm = grade(raw, d / "warm.mp4", REF01.replace("colorbalance=rm=0.02:bm=-0.02",
                                                    "colorbalance=rm=0.3:rh=0.2:bm=-0.3:bh=-0.2"))
    code, js4, _ = gate(raw, warm)
    check("negative: strong warm push fails warmth", code == 1 and failed(js4) == {"warmth"}, summary(js4))
    code, js5, _ = gate(raw, warm, "--waive", "warmth")
    check("waive: --waive warmth passes and reports it waived",
          code == 0 and js5 and js5["gates"]["warmth"]["ok"] is False and js5["gates"]["warmth"]["waived"] is True,
          summary(js5))

    # accents: two 0.3 s 55% green flashes over the samples at 2.5 and 5.5 s, skipped by --exclude
    # (accent +-0.5 s); the clean grade gated with the same --exclude is the baseline.
    flashes = grade(good, d / "flash.mp4", "drawbox=c=0x00FF00@0.55:t=fill:enable='between(t,2.4,2.7)+between(t,5.4,5.7)'"
                                           f",{TAGS}")
    excl = d / "excl.json"
    excl.write_text(json.dumps([[1.9, 3.2], [4.9, 6.2]]), encoding="utf-8")
    code, js6, _ = gate(raw, flashes, "--exclude", excl)
    _, base, _ = gate(raw, good, "--exclude", excl)
    _, bare, _ = gate(raw, flashes)
    used = (js6 or {}).get("frames_used", [])
    check("accents: the samples at 2.5 and 5.5 s are excluded, none used inside a window",
          bool(used) and not any(1.9 <= k / 30 < 3.2 or 4.9 <= k / 30 < 6.2 for k in used)
          and js6["frames_excluded"] == 2 and 75 not in used and 165 not in used, js6 and (used, js6["frames_excluded"]))
    check("accents: excluded flashes leave the clean grade's ratios (within 0.5%)", code == 0 and bool(base) and all(
        abs(js6["ratios"][k] / base["ratios"][k] - 1) <= 0.005 for k in ("luma", "sat", "sharp")),
        js6 and base and (js6["ratios"], base["ratios"]))
    check("accents: without --exclude the flashes do move the ratios", bool(bare) and bool(js) and
          any(abs(bare["ratios"][k] / js["ratios"][k] - 1) > 0.01 for k in ("luma", "sharp", "contrast")), bare and (bare["ratios"], js["ratios"]))

    # one metric definition: metrics() imported from the module reproduces the gate's numbers
    frames = cl.decode_frames_rgb(raw, FF, js["frames_used"], matrix="bt709", in_range="tv")
    per = [grade_gate.metrics(frames[k]) for k in js["frames_used"]]
    mine = {k: round(sum(m[k] for m in per) / len(per), 6) for k in ("luma", "sat", "sharp", "contrast", "p2")}
    check("parity: metrics() reproduces the report's raw metrics",
          all(abs(mine[k] - js["src_metrics"][k]) < 1e-5 for k in mine), (mine, js["src_metrics"]))

    code, js7, _ = gate(raw, good, "--ffprobe", "none")
    check("probe: --ffprobe none gives the same report", code == 0 and js7 == js)
    return raw


def case_clip(d):
    bright = lavfi(d / "bright.mp4", "testsrc2=s=270x360:r=30:d=10",
                   f"scale={W}:{H}:flags=bicubic,eq=brightness=0.12:contrast=0.62:saturation=0.45,format=yuv420p,{TAGS}")
    over = grade(bright, d / "over.mp4", f"eq=brightness=0.04:contrast=1.12:saturation=1.2,{TAGS}")
    code, js, _ = gate(bright, over)
    check("negative: over-pushed eq on bright footage fails clip", code == 1 and "clip" in failed(js), summary(js))
    pchip = grade(bright, d / "pchip.mp4", f"{TO_RGB},curves=interp=pchip:all='0/0 0.5/0.62 1/1',{TO_YUV}")
    code, js2, _ = gate(bright, pchip)
    check("low headroom: the pchip midtone curve passes clip", gate_ok(js2, "clip") is True, summary(js2))
    check("low headroom: ... but misses luma +10%", gate_ok(js2, "luma") is False, summary(js2))
    code, js3, _ = gate(bright, pchip, "--waive", "luma")
    check("low headroom: --waive luma moves luma out of the failures",
          bool(js3) and "luma" not in js3["failed"] and js3["gates"]["luma"]["waived"] is True, summary(js3))


def case_captions(d, raw):
    a, b = caption_png(d / "capA.png", "WATCH THIS"), caption_png(d / "capB.png", "NO WAY")
    cap_dir = d / "edited"
    cap_dir.mkdir()
    captioned = cap_dir / "03-test.mp4"
    cl.run([FF, "-v", "error", "-y", "-i", str(raw), "-loop", "1", "-i", str(a), "-loop", "1", "-i", str(b),
            "-filter_complex", "[0:v][1:v]overlay=108:1000:enable='lt(mod(t,1),0.5)'[x];"
                               f"[x][2:v]overlay=108:1000:enable='gte(mod(t,1),0.5)',format=yuv420p,{TAGS}[v]",
            "-map", "[v]", "-t", "10", *ENC, str(captioned)])
    code, js, err = gate(raw, captioned)
    check("edited: an edited/ file without --mask/--exclude is refused (exit 2)",
          code == 2 and js and js["error"]["code"] == "mask_required", err[-200:])
    empty, mask = d / "empty.json", d / "mask.json"
    empty.write_text("[]", encoding="utf-8")
    mask.write_text(json.dumps([{"t0": 0, "t1": 10, "box": [108, 1000, 972, 1150]}]), encoding="utf-8")
    code, js, _ = gate(raw, captioned, "--mask", empty, "--exclude", empty)
    check("captions: unmasked, captions alone fake the sharpness gain (the bug the mask fixes)",
          gate_ok(js, "sharp") is True, summary(js))
    code, js, _ = gate(raw, captioned, "--mask", mask, "--exclude", empty)
    check("negative: masked, an ungraded captioned clip fails luma, sat and sharp",
          code == 1 and {"luma", "sat", "sharp"} <= failed(js), summary(js))
    check("captions: masked ratios read ~x1.0", bool(js) and all(0.97 <= js["ratios"][k] <= 1.03
                                                                 for k in ("luma", "sat", "sharp")), js and js["ratios"])


def skin_frames(rng, n, size, face_rgb, face_box, tex=8.0, face_tex=None, blow=0.0):
    """Textured grey-blue background with a textured skin block; `blow` = share of block pixels at 255."""
    w, h = size
    yy, xx = np.mgrid[0:h, 0:w]
    base = np.stack([90 + 40 * np.sin(xx / 23.0), 100 + 40 * np.sin(yy / 17.0), 120 + 30 * np.cos((xx + yy) / 31.0)], -1)
    out = np.empty((n, h, w, 3), np.uint8)
    x0, y0, x1, y1 = face_box
    for i in range(n):
        f = base + rng.normal(0, tex, base.shape)
        fb = np.array(face_rgb, float) + rng.normal(0, face_tex if face_tex is not None else tex, (y1 - y0, x1 - x0, 1))
        if blow:
            fb[rng.random((y1 - y0, x1 - x0)) < blow] = 255
        f[y0:y1, x0:x1] = fb
        out[i] = np.clip(f, 0, 255).astype(np.uint8)
    return out


def case_skin(d):
    size, box, n = (360, 480), (100, 120, 260, 340), 270
    faces = d / "faces.json"
    faces.write_text(json.dumps({"fps": "30/1", "boxes": [[0, *box]]}), encoding="utf-8")
    seeds = iter(range(100, 200))

    def clip(name, rgb, **kw):
        return pipe_frames(d / name, skin_frames(np.random.default_rng(next(seeds)), n, size, rgb, box, **kw))

    src = clip("skin_src.mp4", (224, 172, 138))  # hue 23.7 deg
    for name, rgb, want in (("skin_orange.mp4", (224, 190, 120), False), ("skin_ok.mp4", (230, 176, 140), True)):
        code, js, _ = gate(src, clip(name, rgb), "--faces", faces)
        hue = js and js["out_metrics"]["skin_hue"]
        label = "negative: skin pushed to hue ~40 deg fails skin" if not want else "skin: hue ~24 deg passes skin"
        check(label, gate_ok(js, "skin") is want, (hue, summary(js)))
    code, js, _ = gate(src, clip("skin_blown.mp4", (224, 172, 138), blow=0.05), "--faces", faces)
    check("negative: a blown face fails face_clip", gate_ok(js, "face_clip") is False, summary(js))

    dark = clip("dark_src.mp4", (96, 66, 52), face_tex=10.0)
    code, js, _ = gate(dark, clip("dark_keep.mp4", (106, 73, 57), face_tex=11.0), "--faces", faces)
    check("dark skin: raw face median V < 110 arms the gate; texture kept passes",
          gate_ok(js, "dark_skin") is True, js and (js["gates"]["dark_skin"], summary(js)))
    code, js, _ = gate(dark, clip("dark_flat.mp4", (106, 73, 57), face_tex=4.0), "--faces", faces)
    check("negative: a flattened dark face fails dark_skin", gate_ok(js, "dark_skin") is False,
          js and js["gates"]["dark_skin"])

    check("unit: circular hue mean of 353 and 7 deg is 0, not 180",
          abs(grade_gate.skin_hue([353.0, 7.0], [1.0, 1.0])) < 1e-9)


def case_refusals(d, raw):
    def err_code(js):
        return ((js or {}).get("error") or {}).get("code")

    small = lavfi(d / "small.mp4", "testsrc2=s=540x720:r=30:d=10", f"format=yuv420p,{TAGS}")
    code, js, _ = gate(raw, small)
    check("refuse: size mismatch (exit 2)", code == 2 and err_code(js) == "size_mismatch", summary(js))
    fps25 = lavfi(d / "fps25.mp4", "testsrc2=s=270x360:r=25:d=10", RAW_VF)
    code, js, _ = gate(raw, fps25)
    check("refuse: fps mismatch (exit 2)", code == 2 and err_code(js) == "fps_mismatch", summary(js))
    short = grade(raw, d / "short.mp4", "trim=end_frame=290", enc=ENC)
    code, js, _ = gate(raw, short)
    check("refuse: grade-only render 10 frames short (exit 2)", code == 2 and err_code(js) == "length_mismatch",
          summary(js))
    t601 = lavfi(d / "t601.mp4", "testsrc2=s=270x360:r=30:d=10",
                 RAW_VF.replace(TAGS, "setparams=colorspace=smpte170m:range=tv"),
                 enc=ENC[:6] + ["-x264-params", "colormatrix=smpte170m"])
    code, js, _ = gate(raw, t601)
    check("refuse: BT.601-tagged input (exit 2)", code == 2 and err_code(js) == "not_bt709", summary(js))
    untagged = lavfi(d / "untagged.mp4", "testsrc2=s=270x360:r=30:d=10", RAW_VF.replace("," + TAGS, ""), enc=ENC[:6])
    code, js, _ = gate(raw, untagged)
    check("untagged input is read as BT.709 tv with a warning",
          js is not None and any("untagged" in w for w in js.get("warnings", [])), summary(js))
    code, js, _ = gate(raw, raw, "--waive", "luma,brightness")
    check("refuse: unknown --waive name (exit 2)", code == 2 and err_code(js) == "bad_waive", summary(js))

    s5 = lavfi(d / "s5.mp4", "testsrc2=s=270x360:r=30:d=5", RAW_VF)
    code, js, _ = gate(s5, s5)
    check("short clip: under 8 samples at 1 s falls back to 0.5 s steps",
          bool(js) and js.get("step_s") == 0.5 and len(js["frames_used"]) == 10, summary(js))
    s3 = lavfi(d / "s3.mp4", "testsrc2=s=270x360:r=30:d=3", RAW_VF)
    code, js, _ = gate(s3, s3)
    check("refuse: a 3 s clip has too few samples (exit 2)", code == 2 and err_code(js) == "too_few_samples",
          summary(js))


def case_ntsc(d):
    vf = f"format=yuv420p,{TAGS}"
    a = lavfi(d / "ntsc.mp4", "testsrc2=s=360x480:r=30000/1001:d=9", vf)
    code, js, _ = gate(a, a)
    fps = Fraction(30000, 1001)
    count = math.floor(Fraction(js["frames"]["raw"]) / fps) if js else 0
    want = [math.floor((i + Fraction(1, 2) + Fraction(1, 2000)) * fps + Fraction(1, 10 ** 6)) for i in range(count)]
    check("grid: 30000/1001 samples the frame showing i + 0.5 s (first index 15)",
          bool(js) and js["frames_used"] == want and want[0] == 15, js and js["frames_used"])
    b = lavfi(d / "sixty.mp4", "testsrc2=s=360x480:r=60:d=9", vf)
    code, js, _ = gate(b, b)
    check("grid: 60 fps samples 30, 90, ... 510", bool(js) and js["frames_used"] == [30 + 60 * i for i in range(9)],
          js and js["frames_used"])


def main():
    cl.utf8_stdio()
    d = Path(tempfile.mkdtemp(prefix="grade_gate_"))
    try:
        raw = case_core(d)
        case_clip(d)
        case_captions(d, raw)
        case_skin(d)
        case_refusals(d, raw)
        case_ntsc(d)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    print(f"{'PASS' if not FAILS else 'FAIL'}: {len(FAILS)} failed check(s)" + (f": {FAILS}" if FAILS else ""))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
