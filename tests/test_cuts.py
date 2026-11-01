"""Tests for skill/scripts/cuts.py (run: python -P tests/test_cuts.py from the repo root).

Every media case runs the real CLI as a subprocess on synthetic video (tests/fixtures.py and lavfi): the fixtures
podcast (punch-in, hard cut, 2-frame white flash) at 60 and 30 fps, a soft-class 10 % punch-in, HyperFrames' own
flash fixture, windows with and without the lead, a 59.94 fps file through the ffmpeg-only probe, a VFR concat, and
the plan gate with its negative controls (missed cut, unplanned events, sliver, orphan frame, frame count). The
detector core is also checked on hand-made d arrays (HyperFrames' unit cases). One line per check; exit 0 = all pass.
"""
import json
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
import cuts  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skill" / "scripts" / "cuts.py"
FAILS = []


def check(name, cond, detail=""):
    print(f"{'ok  ' if cond else 'FAIL'} {name}" + (f"  [{detail}]" if detail and not cond else ""), flush=True)
    if not cond:
        FAILS.append(name)


def run_cli(args):
    cp = subprocess.run([sys.executable, "-P", str(SCRIPT), *map(str, args)], capture_output=True)
    try:
        js = json.loads(cp.stdout.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        js = None
    return cp.returncode, js, cp.stderr.decode("utf-8", errors="replace")


def write(path, obj):
    Path(path).write_text(json.dumps(obj), encoding="utf-8")
    return path


def evs(js):
    return [(e["frame"], e["kind"]) for e in js["events"]] if js else None


def ids(js):
    return sorted((x["id"], x["frame"]) for x in js["gate"]["findings"] if x["rank"] == "P0") if js else None


def lavfi_video(path, graph, fps=60):
    """Encode a filter graph ending in [v] (CFR, BT.709 tags) like fixtures.shots_video does."""
    cl.run([fx.ffmpeg(), "-v", "error", "-y", "-filter_complex", graph, "-map", "[v]", "-c:v", "libx264",
            "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", *fx.X264_709, "-r", str(fps), str(path)])
    return path


def punch_video(path, crop, at=60, total=120):
    """testsrc2 that punches in (same angle, crop factor `crop`) at frame `at`, motion continuing across it."""
    g = (f"testsrc2=s=1280x720:r=60:d={total / 60},split[a][b];"
         f"[b]crop=iw*{crop}:ih*{crop},scale=1280:720,setsar=1[bc];"
         f"[a][bc]overlay=enable='gte(n\\,{at})',format=yuv420p,{fx.TAGS_709}[v]")
    return lavfi_video(path, g)


# ---------------------------------------------------------------- detector core on d arrays (HF cuts.test.ts)

def case_unit():
    def d_of(n, base, hits):
        d = np.full(n, float(base))
        d[0] = 0.0
        for i, x in hits.items():
            d[i] = x
        return d

    h = cuts.hits_from_diffs(d_of(60, 1, {20: 40, 40: 30, 41: 25}), 1)
    check("unit: 40 at 20 and 30/25 at 40-41 -> [{20, 1, 40}, {40, 2, 30}]",
          [(x["frame"], x["frames"], x["change"]) for x in h] == [(20, 1, 40.0), (40, 2, 30.0)], h)
    h = cuts.hits_from_diffs(d_of(60, 1, {30: 11.3}), 1)
    check("unit: 11.3 among 1s -> one soft hit", [(x["frame"], x["soft"]) for x in h] == [(30, True)], h)
    h = cuts.hits_from_diffs(d_of(60, 1, {29: 5, 30: 11}), 1)
    check("unit: 11 next to a 5 -> no hit (not alone)", h == [], h)
    d = np.array([0.0] + [10.5 if i % 2 else 0.0 for i in range(1, 60)])
    check("unit: alternating 10.5 / 0 -> no hit", cuts.hits_from_diffs(d, 1) == [])
    check("unit: 9 among 1s -> no hit", cuts.hits_from_diffs(d_of(60, 1, {30: 9}), 1) == [])
    check("unit: r = max(1, round(fps/30)): 24->1, 30->1, 59.94->2, 60->2, 120->4",
          [cuts.scale_r(Fraction(x)) for x in (24, 30, Fraction(60000, 1001), 60, 120)] == [1, 1, 2, 2, 4])
    check("unit: windows(2) = (24, 6, 8)", cuts.windows(2) == (24, 6, 8))


# ---------------------------------------------------------------- the fixtures podcast

def case_podcast(d):
    p = fx.podcast(d / "pod60")
    truth = p["truth"]
    a, b, w, w2 = truth["cuts"]          # punch-in, hard cut, white flash start, back to picture
    out = d / "pod60" / "cuts.json"
    code, js, err = run_cli([p["path"], "--out", out])
    check("podcast 60: exit 0", code == 0, err[-300:])
    if not js:
        return p
    kinds = dict(evs(js))
    check("podcast 60: version + fps 60/1 + r 2", js["version"] == cuts.SCRIPT_VERSION and js["fps"] == "60/1"
          and js["params"] == {"r": 2, "N": 24, "M": 6, "K": 8}, js.get("params"))
    check("podcast 60: same-angle punch-in found as a cut", kinds.get(a) in ("hard", "soft"), evs(js))
    check("podcast 60: hard cut found", kinds.get(b) == "hard", evs(js))
    check("podcast 60: 2-frame white flash = one flash + the new shot's cut, not 2 cuts",
          kinds.get(w) == "flash" and kinds.get(w2) == "hard", evs(js))
    check("podcast 60: nothing else (testsrc2 motion is not a cut)", sorted(kinds) == [a, b, w, w2], evs(js))
    check("podcast 60: reset_frames = hard/soft cut frames only", js["reset_frames"] == [a, b, w2], js["reset_frames"])
    e = next(x for x in js["events"] if x["frame"] == b)
    check("podcast 60: t = frame/fps, d and typical reported", e["t"] == round(b / 60, 6) and e["d"] > 50
          and e["typical"] >= 1 and e["len"] == 1, e)
    check("podcast 60: punch-in d about 21", 15 < next(x["d"] for x in js["events"] if x["frame"] == a) < 30)
    check("podcast 60: --out holds the same JSON", json.loads(out.read_text(encoding="utf-8")) == js)
    check("podcast 60: ffmpeg-only probe works (no ffprobe here)", js["probe"] in ("ffmpeg", "ffprobe")
          and js["vfr"] is False and js["retimed"] is False)
    return p


def case_podcast_30(d):
    p = fx.podcast(d / "pod30", fps=30)
    a, b, w, w2 = p["truth"]["cuts"]
    code, js, err = run_cli([p["path"], "--ffprobe", "none"])
    check("podcast 30: exit 0, r 1", code == 0 and js["params"]["r"] == 1, err[-300:])
    check("podcast 30: punch, cut, flash + cut classified the same at r = 1",
          evs(js) == [(a, evs(js)[0][1]), (b, "hard"), (w, "flash"), (w2, "hard")]
          and evs(js)[0][1] in ("hard", "soft"), evs(js))


# ---------------------------------------------------------------- soft class and HyperFrames' fixture

def case_soft(d):
    v10 = punch_video(d / "punch10.mp4", 0.90)
    code, js, err = run_cli([v10])
    check("soft: 10 % punch-in -> one soft cut at 60 (d 10-12)", evs(js) == [(60, "soft")]
          and 10 <= js["events"][0]["d"] < 12 and js["reset_frames"] == [60], evs(js) or err[-300:])
    v6 = punch_video(d / "punch6.mp4", 0.94)
    code, js, err = run_cli([v6])
    check("soft: 6 % punch-in -> no event (under the soft level)", code == 0 and evs(js) == [], evs(js))
    return v6


def case_hf_fixture(d):
    # HF cuts fixture: scrolling testsrc2 with a white flash at 2-2.1 s, then smptebars -> rgbtestsrc (1 s xfade).
    v = d / "hf.mp4"
    cl.run([fx.ffmpeg(), "-v", "error", "-y",
            "-f", "lavfi", "-i", "testsrc2=s=160x90:r=24:d=4,scroll=horizontal=0.015,"
                                 "eq=brightness=1:enable='between(t,2,2.1)'",
            "-f", "lavfi", "-i", "smptebars=s=160x90:r=24:d=3", "-f", "lavfi", "-i", "rgbtestsrc=s=160x90:r=24:d=3",
            "-filter_complex", "[1][2]xfade=transition=fade:duration=1:offset=2[x];[0][x]concat=n=2:v=1:a=0,"
                               "format=yuv420p[v]", "-map", "[v]", "-c:v", "libx264", "-preset", "veryfast", str(v)])
    code, js, err = run_cli([v])
    check("hf fixture: flashes at 48 and 51, one cut at 96, dissolve not a cut",
          evs(js) == [(48, "flash"), (51, "flash"), (96, "hard")], evs(js) or err[-300:])


# ---------------------------------------------------------------- windows

def case_windows(p):
    v = p["path"]
    a, b = p["truth"]["cuts"][:2]                          # 315 (5.25 s), 450 (7.5 s)
    code, js, err = run_cli([v, "--start", 7.4, "--end", 9, "--lead", 0])
    check("window: --start 7.4 --lead 0 -> cut at frame 6 (frame 0 = the frame at start), t absolute",
          code == 0 and evs(js) == [(b - 444, "hard")] and js["events"][0]["t"] == 7.5
          and js["window"]["k_start"] == 444 and js["window"]["decoded"] == 540 - 444, evs(js) or err[-300:])
    code, js, err = run_cli([v, "--start", 7.4917, "--end", 9, "--lead", 0])
    check("window: start on the cut frame with --lead 0 -> not seen (frame 0 has no d)", evs(js) == [], evs(js))
    code, js, err = run_cli([v, "--start", 7.4917, "--end", 9])
    check("window: same start with the default 0.5 s lead -> found at frame 0",
          evs(js) == [(0, "hard")] and js["window"]["k_first"] == 420 and js["reset_frames"] == [0], evs(js))
    code, js, err = run_cli([v, "--start", 5.3, "--end", 7.45])
    check("window: events in the lead (5.25 s) and after --end (7.5 s) are not reported", evs(js) == [], evs(js))
    code, js, err = run_cli([v, "--start", 5.0, "--end", 7.6])
    check("window: [5.0, 7.6) -> punch-in at 15, cut at 150", [f for f, _ in evs(js)] == [a - 300, b - 300], evs(js))


def case_rates(d):
    # 59.94 fps through the ffmpeg-only probe (stderr "59.94 fps, 59.94 tbr").
    v = d / "ntsc.mp4"
    fx.shots_video(v, [("testsrc2", 120), ("bars", 60)], fps=Fraction(60000, 1001), size=(640, 360))
    code, js, err = run_cli([v, "--ffprobe", "none"])
    check("59.94: fps 60000/1001 via the ffmpeg probe, cut at 120, t 2.002",
          code == 0 and js["probe"] == "ffmpeg" and js["fps"] == "60000/1001" and evs(js) == [(120, "hard")]
          and js["events"][0]["t"] == round(120 * 1001 / 60000, 6) and not js["retimed"], evs(js) or err[-300:])
    code, js, err = run_cli([v, "--start", 1.9, "--end", 3, "--ffprobe", "none"])
    k = round(Fraction("1.9") * Fraction(60000, 1001))
    check("59.94: windowed seek keeps the grid (cut at 120 - k_start)", evs(js) == [(120 - k, "hard")]
          and js["events"][0]["t"] == round(120 * 1001 / 60000, 6), evs(js))

    # VFR: a 30 fps segment then a 60 fps segment, stream-copied together ("44.6 fps, 60 tbr").
    a30, b60, lst = d / "a30.mp4", d / "b60.mp4", d / "list.txt"
    for path, src in ((a30, "testsrc2=s=320x180:r=30:d=2"), (b60, "testsrc2=s=320x180:r=60:d=2,hue=h=140:s=1.4,hflip")):
        cl.run([fx.ffmpeg(), "-v", "error", "-y", "-f", "lavfi", "-i", src, "-c:v", "libx264", "-preset", "veryfast",
                "-pix_fmt", "yuv420p", str(path)])
    lst.write_text("file 'a30.mp4'\nfile 'b60.mp4'\n", encoding="utf-8")
    vfr = d / "vfr.mp4"
    cl.run([fx.ffmpeg(), "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst.name, "-c", "copy", vfr.name],
           cwd=str(d))
    code, js, err = run_cli([vfr, "--ffprobe", "none"])
    check("vfr: flagged, re-timed to 60/1 with a warning, cut at frame 120 = t 2.000",
          code == 0 and js["vfr"] and js["retimed"] and js["fps"] == "60/1" and evs(js) == [(120, "hard")]
          and js["events"][0]["t"] == 2.0 and any(w.startswith("retimed") for w in js["warnings"]),
          evs(js) or err[-300:])
    code, js, err = run_cli([vfr, "--start", 1.5, "--end", 3, "--ffprobe", "none"])
    check("vfr: windowed (start 1.5) -> cut at frame 30, t 2.000", evs(js) == [(30, "hard")]
          and js["events"][0]["t"] == 2.0, evs(js))


# ---------------------------------------------------------------- plan gate

def case_plan(d, p, v6):
    v = p["path"]
    a, b, w, w2 = p["truth"]["cuts"]
    n = p["truth"]["frames"]
    good = {"fps": "60/1", "frames": n, "cuts": [b, w2], "jump_cuts": [a], "accent_spans": [[w - 1, w + 10]]}

    code, js, err = run_cli([v, "--plan", write(d / "plan_ok.json", good)])
    check("plan: clean plan passes (exit 0, no findings)", code == 0 and js["ok"] and js["gate"]["ok"]
          and js["gate"]["findings"] == [], js and js["gate"])
    code, js, err = run_cli([v, "--plan", write(d / "plan_ok2.json", dict(good, cuts=[a, b, w2], jump_cuts=[]))])
    check("plan: the punch-in listed as a planned cut also passes", code == 0 and js["gate"]["ok"], js and js["gate"])

    code, js, err = run_cli([v, "--plan", write(d / "plan_miss.json", dict(good, cuts=[200, b, w2]))])
    check("plan NEG: a planned cut with no change -> P0 missed_cut, exit 1",
          code == 1 and not js["ok"] and ids(js) == [("missed_cut", 200)] and js["gate"]["missing"] == [200],
          js and js["gate"])
    code, js, err = run_cli([v, "--plan", write(d / "plan_unpl.json", dict(good, cuts=[w2]))])
    check("plan NEG: an unplanned hard cut -> P0 unplanned_hard, exit 1",
          code == 1 and ids(js) == [("unplanned_hard", b)], js and js["gate"])
    code, js, err = run_cli([v, "--plan", write(d / "plan_noacc.json", dict(good, accent_spans=[]))])
    check("plan NEG: the white flash without its accent span -> P0 unplanned_flash (+ sliver), exit 1",
          code == 1 and ("unplanned_flash", w) in ids(js) and ("sliver", w) in ids(js), js and js["gate"])
    code, js, err = run_cli([v, "--plan", write(d / "plan_n.json", dict(good, frames=n - 2))])
    check("plan NEG: frame count differs from the plan -> P0 frame_count", code == 1
          and ("frame_count", None) in [(x["id"], x["frame"]) for x in js["gate"]["findings"]], js and js["gate"])

    # Seam confirmation: a 6 % punch-in shows no event but d >= 6 and >= 4 x typical at the planned cut.
    code, js, err = run_cli([v6, "--plan", write(d / "plan_seam.json", {"fps": "60/1", "frames": 120, "cuts": [60]})])
    check("plan: a planned cut with no event passes by seam confirmation", code == 0
          and js["gate"]["seam_confirmed"] == [60], js and js["gate"])
    code, js, err = run_cli([v6, "--plan", write(d / "plan_seam2.json",
                                                 {"fps": "60/1", "frames": 120, "cuts": [], "jump_cuts": [60]})])
    check("plan: the same punch-in as a jump cut is never required", code == 0 and js["gate"]["findings"] == [])


def case_slivers(d):
    # A 2-frame sliver of another shot inside one shot (motion continues): reads as two flash events.
    g = ("testsrc2=s=640x360:r=60:d=4,split[a][b];[b]hue=h=140:s=1.4,hflip[h];"
         f"[a][h]overlay=enable='between(n\\,150\\,151)',format=yuv420p,{fx.TAGS_709}[v]")
    v = lavfi_video(d / "sliver.mp4", g)
    code, js, err = run_cli([v])
    check("sliver: a 2-frame insert reads as flash events at 150 and 152", evs(js) == [(150, "flash"), (152, "flash")],
          evs(js) or err[-300:])
    code, js, err = run_cli([v, "--plan", write(d / "plan_sl.json", {"fps": "60/1", "frames": 240, "cuts": []})])
    check("sliver NEG: unplanned -> P0 unplanned_flash x2 + sliver, exit 1",
          code == 1 and ids(js) == [("sliver", 150), ("unplanned_flash", 150), ("unplanned_flash", 152)],
          js and js["gate"])

    # A 2-frame sliver of a third shot at a planned join (the edge was not moved onto the cut).
    v = d / "join_sliver.mp4"
    fx.shots_video(v, [("testsrc2", 100), ("hue", 2), ("bars", 100)], size=(640, 360))
    code, js, err = run_cli([v, "--plan", write(d / "plan_js.json", {"fps": "60/1", "frames": 202, "cuts": [100]})])
    check("sliver NEG: 2 frames of another shot after a planned join -> P0 unplanned_hard + sliver",
          code == 1 and ids(js) == [("sliver", 100), ("unplanned_hard", 102)], js and js["gate"])

    # An orphan black frame at a planned join reads as one 2-frame hit.
    v = d / "orphan.mp4"
    fx.shots_video(v, [("testsrc2", 100), ("black", 1), ("hue", 100)], size=(640, 360))
    code, js, err = run_cli([v, "--plan", write(d / "plan_or.json", {"fps": "60/1", "frames": 201, "cuts": [101]})])
    check("orphan NEG: a black frame at the join -> P0 interloper (2-frame hit)",
          code == 1 and evs(js) == [(100, "hard")] and js["events"][0]["len"] == 2
          and ids(js) == [("interloper", 100)], js and (evs(js), js.get("gate")))


# ---------------------------------------------------------------- usage errors

def case_usage(d, p):
    code, js, err = run_cli([d / "nope.mp4"])
    check("usage: missing video -> exit 2 with a JSON error and version", code == 2 and js and js["ok"] is False
          and js["error"]["code"] == "input_missing" and js["version"] == cuts.SCRIPT_VERSION, (code, js))
    plan = write(d / "plan_u.json", {"fps": "60/1", "frames": p["truth"]["frames"], "cuts": []})
    code, js, err = run_cli([p["path"], "--plan", plan, "--start", 1])
    check("usage: --plan with --start -> exit 2", code == 2 and js["error"]["code"] == "usage", js)
    code, js, err = run_cli([p["path"], "--plan", plan, "--fps", "30"])
    check("usage: --fps differing from plan.fps -> exit 2", code == 2, js)
    code, js, err = run_cli([p["path"], "--plan", write(d / "plan_bad.json", {"fps": "60/1", "frames": 10,
                                                                             "cuts": [50]})])
    check("usage: planned cut outside the frame range -> exit 2 bad_plan", code == 2
          and js["error"]["code"] == "bad_plan", js)
    code, js, err = run_cli([p["path"], "--start", 3, "--end", 2])
    check("usage: --end before --start -> exit 2", code == 2, js)
    code, js, err = run_cli([p["path"], "--start", 999])
    check("usage: --start past the end -> exit 2 empty_window", code == 2 and js["error"]["code"] == "empty_window", js)


def main():
    cl.utf8_stdio()
    d = Path(tempfile.mkdtemp(prefix="test_cuts_"))
    try:
        case_unit()
        p = case_podcast(d)
        case_podcast_30(d)
        v6 = case_soft(d)
        case_hf_fixture(d)
        case_windows(p)
        case_rates(d)
        case_plan(d, p, v6)
        case_slivers(d)
        case_usage(d, p)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    print(f"{'ALL PASS' if not FAILS else f'{len(FAILS)} FAILED: ' + ', '.join(FAILS)}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
