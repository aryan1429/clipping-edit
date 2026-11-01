"""Tests for skill/scripts/cutlist.py (run: python -P tests/test_cutlist.py from the repo root).

Every case runs the real CLI as a subprocess on synthetic inputs (tests/fixtures.py, lavfi audio) and prints one
line per check; the library API (load, remap, ...) is checked on the files the CLI wrote. Exit 0 = all pass.
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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixtures as fx  # noqa: E402  (also puts skill/scripts on sys.path)
import cliplib as cl  # noqa: E402
import cutlist  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skill" / "scripts" / "cutlist.py"
FAILS = []


def check(name, cond, detail=""):
    print(f"{'ok  ' if cond else 'FAIL'} {name}" + (f"  [{detail}]" if detail and not cond else ""), flush=True)
    if not cond:
        FAILS.append(name)


def run_cli(args, cwd=None):
    cp = subprocess.run([sys.executable, "-P", str(SCRIPT), *map(str, args)], capture_output=True, cwd=cwd)
    out = cp.stdout.decode("utf-8", errors="replace")
    try:
        js = json.loads(out)
    except json.JSONDecodeError:
        js = None
    return cp.returncode, js, cp.stderr.decode("utf-8", errors="replace")


def write(path, obj):
    Path(path).write_text(json.dumps(obj), encoding="utf-8")
    return path


def spans(js):
    return [[s["src_in_s"], s["src_out_s"]] for s in js["segments"]]


def close(a, b, tol):
    return len(a) == len(b) and all(abs(x - y) <= tol for p, q in zip(a, b) for x, y in zip(p, q))


# The spec vector (ref 03 section 2 test plan): "um" is a filler, 'thing'->'is' is a 0.32 s gap.
SPEC_WORDS = [(" so", 0.05, 0.3), (" um", 0.45, 0.7), (" the", 0.85, 1.1), (" thing", 1.15, 1.5),
              (" is", 1.82, 2.0), (" crazy", 3.2, 3.6)]


def spec_transcript(path, ids=True):
    words = [{"text": t, "start": a, "end": b} for t, a, b in SPEC_WORDS]
    if ids:
        for i, w in enumerate(words):
            w["id"] = f"w{i}"
    return write(path, {"words": words})


def facts(path, fps="60/1", duration=10.0):
    return write(path, {"canvas_fps": fps, "duration": duration, "src": "src.mp4"})


def case_spec_vector(d):
    t, f = spec_transcript(d / "t.json"), facts(d / "f.json")
    c = write(d / "c.json", [{"rank": 2, "start_word": "w0", "end_word": "w5"},
                             {"rank": 1, "start_word": "w0", "end_word": "w5", "hook_line": "So, um, the thing...",
                              "payoff_line": "the thing is CRAZY!"}])
    code, js, err = run_cli(["--transcript", t, "--clips", c, "--rank", 1, "--facts", f, "--out", d / "o" / "cut.json"])
    check("spec vector: exit 0", code == 0, err[-300:])
    if code:
        return
    check("spec vector: kept [[0,0.4],[0.75,1.6],[1.72,2.1],[3.1,3.75]] on the 60 fps grid",
          spans(js) == [[0.0, 0.4], [0.75, 1.6], [1.716667, 2.1], [3.1, 3.75]], spans(js))
    check("spec vector: 137 frames, kept_s 2.283333", js["frames"] == 137 and js["kept_s"] == 2.283333,
          (js["frames"], js["kept_s"]))
    cut = cutlist.load(d / "o" / "cut.json")
    check("spec vector: remap(1.15) = 0.8", abs(cutlist.remap(1.15, cut) - 0.8) < 1e-9)
    check("spec vector: remap(3.2) = 1.7333", abs(cutlist.remap(3.2, cut) - 104 / 60) < 1e-9)
    check("spec vector: remap(0.45) is None (inside the um removal)", cutlist.remap(0.45, cut) is None)
    check("spec vector: the removal holding 'um' is named filler, the others dead_air",
          [r["why"] for r in js["removed"]] == ["filler", "dead_air", "dead_air"], js["removed"])
    check("spec vector: output words drop 'um' and are remapped",
          [(w["id"], w["start"]) for w in js["words"]] == [("w0", 0.05), ("w2", 0.5), ("w3", 0.8), ("w4", 1.353333),
                                                          ("w5", 1.733333)], js["words"])
    check("spec vector: warns that the quiet test was skipped", any("quiet_test_skipped" in w for w in js["warnings"]))
    check("spec vector: stdout object carries ok/version/out", js["ok"] is True and js["version"] == "1.0.0"
          and Path(js["out"]).name == "cut.json")


def case_library(d):
    cut = cutlist.load(d / "o" / "cut.json")
    n = cutlist.cut_frames(cut)
    rt = all(cutlist.src_to_out_frame(cutlist.out_to_src_frame(f, cut), cut) == f for f in range(n))
    check("library: out_to_src_frame / src_to_out_frame round-trip every output frame", rt)
    check("library: a source frame inside a removal maps to None", cutlist.src_to_out_frame(30, cut) is None)
    try:
        cutlist.out_to_src_frame(n, cut)
        raised = False
    except cl.ClipError as e:
        raised = e.code == "frame_out_of_range"
    check("library: out_to_src_frame past the end raises frame_out_of_range", raised)
    check("library: remap_span clamps an end that crosses k_out", cutlist.remap_span(1.5, 1.7, cut) == (1.15, 1.25),
          cutlist.remap_span(1.5, 1.7, cut))
    bad = dict(cut, segments=[dict(cut["segments"][0], frames=99)] + cut["segments"][1:])
    write(d / "bad_cut.json", bad)
    try:
        cutlist.load(d / "bad_cut.json")
        code = None
    except cl.ClipError as e:
        code = (e.code, e.exit_code)
    check("library: load rejects an inconsistent cut list (bad_cutlist, exit 2)", code == ("bad_cutlist", 2), code)


def case_options(d):
    t, f = spec_transcript(d / "t.json", ids=False), facts(d / "f.json")
    c = write(d / "c.json", [{"rank": 1, "start_word": 0, "end_word": "5", "keep_gaps": ["w4"]}])
    code, js, err = run_cli(["--transcript", t, "--clips", c, "--rank", 1, "--facts", f, "--out", d / "k.json"])
    check("keep_gaps: the pause after w4 survives (ids assigned, int and string refs)",
          code == 0 and spans(js)[-1] == [1.716667, 3.75], (code, js and spans(js), err[-200:]))
    c = write(d / "c2.json", [{"rank": 1, "start_word": "w0", "end_word": "w5"}])
    code, js, err = run_cli(["--transcript", t, "--clips", c, "--rank", 1, "--facts", f, "--out", d / "p.json",
                             "--keep-pauses"])
    check("--keep-pauses: only the filler goes", code == 0 and spans(js) == [[0.0, 0.45], [0.7, 3.75]],
          (code, js and spans(js)))
    c = write(d / "c3.json", [{"rank": 1, "start_word": "w1", "end_word": "w5"}])
    code, js, err = run_cli(["--transcript", t, "--clips", c, "--rank", 1, "--facts", f, "--out", d / "h.json"])
    check("filler as start_word: the clip starts 0.05 s before the first kept word",
          code == 0 and spans(js)[0][0] == 0.8 and js["window"]["start_word"] == "w1", (code, js and spans(js)))
    f2 = facts(d / "f2.json", duration=3.65)
    code, js, err = run_cli(["--transcript", t, "--clips", c, "--rank", 1, "--facts", f2, "--out", d / "w.json"])
    check("window clamps to the source duration", code == 0 and js["window"]["end_s"] == 3.65
          and js["segments"][-1]["k_out"] <= math.floor(3.65 * 60), (code, js and js["window"]))
    raw = [{"text": t, "start": a, "end": b} for t, a, b in SPEC_WORDS]
    raw.insert(3, {"text": "  ", "start": 1.12, "end": 1.13})  # an empty entry: skipped, later ids keep their index
    t2 = write(d / "t2.json", {"words": raw, "suspect_gaps": [[2.4, 2.8]]})
    c = write(d / "c5.json", [{"rank": 1, "start_word": "w0", "end_word": "w6"}])
    code, js, err = run_cli(["--transcript", t2, "--clips", c, "--rank", 1, "--facts", f, "--out", d / "e.json"])
    check("transcript: an empty entry is skipped with a warning and ids keep their index",
          code == 0 and [w["id"] for w in js["words"]] == ["w0", "w2", "w4", "w5", "w6"]
          and any(w.startswith("transcript_entries_skipped: 1") for w in js["warnings"]), (code, js and js["words"]))
    check("transcript: suspect_gaps stay as kept sound (never dead air)",
          code == 0 and js["sounds"] == [[2.4, 2.8]] and cutlist.remap(2.6, cutlist.load(d / "e.json")) is not None,
          js and js["sounds"])
    f3 = facts(d / "f3.json", fps="30000/1001")
    c = write(d / "c4.json", [{"rank": 1, "start_word": "w0", "end_word": "w5"}])
    code, js, err = run_cli(["--transcript", t, "--clips", c, "--rank", 1, "--facts", f3, "--out", d / "n.json"])
    fps = Fraction(30000, 1001)
    want = [math.floor(Fraction(x) * fps + Fraction(1, 2)) for x in ("0.75", "1.6", "1.72", "2.1")]
    got = [js["segments"][1]["k_in"], js["segments"][1]["k_out"], js["segments"][2]["k_in"],
           js["segments"][2]["k_out"]] if code == 0 else None
    check("29.97 canvas: boundaries are round(t * 30000/1001)", got == want, (got, want))


def case_errors(d):
    t, f = spec_transcript(d / "t.json"), facts(d / "f.json")
    bad = {"reversed range": ({"start_word": "w0", "end_word": "w5", "remove_words": [["w3", "w2"]]}, "bad_ids"),
           "id out of range": ({"start_word": "w0", "end_word": "w999"}, "bad_ids"),
           "overlapping ranges": ({"start_word": "w0", "end_word": "w5", "remove_words": [["w1", "w3"], ["w3", "w4"]]},
                                  "bad_ids"),
           "range not strictly inside": ({"start_word": "w0", "end_word": "w5", "remove_words": [["w0", "w1"]]},
                                         "bad_ids"),
           "start after end": ({"start_word": "w4", "end_word": "w2"}, "bad_ids"),
           "hook_line mismatch": ({"start_word": "w0", "end_word": "w5", "hook_line": "so what thing"},
                                  "id_text_mismatch"),
           "payoff_line mismatch": ({"start_word": "w0", "end_word": "w5", "payoff_line": "is not crazy"},
                                    "id_text_mismatch")}
    for name, (cand, want) in bad.items():
        c = write(d / "c.json", [dict(cand, rank=1)])
        out = d / "never.json"
        code, js, _ = run_cli(["--transcript", t, "--clips", c, "--rank", 1, "--facts", f, "--out", out])
        got = js and js.get("error", {}).get("code")
        check(f"error {name}: exit 1 with {want}, nothing written", code == 1 and got == want and not out.exists(),
              (code, got))
    c = write(d / "c.json", [{"rank": 1, "start_word": "w0", "end_word": "w5"}])
    code, js, _ = run_cli(["--transcript", t, "--clips", c, "--rank", 1, "--facts", f])
    check("missing --out: exit 2 with a usage envelope", code == 2 and js and js["error"]["code"] == "usage"
          and js["version"] == "1.0.0", (code, js))
    code, js, _ = run_cli(["--transcript", t, "--clips", c, "--rank", 7, "--facts", f, "--out", d / "x.json"])
    check("unknown rank: exit 2 (bad_clips)", code == 2 and js["error"]["code"] == "bad_clips", (code, js))
    code, js, _ = run_cli(["--transcript", d / "nope.json", "--clips", c, "--rank", 1, "--facts", f, "--out", d / "x.json"])
    check("missing transcript: exit 2 (input_missing)", code == 2 and js["error"]["code"] == "input_missing", (code, js))


def case_too_long(d):
    words = [{"id": f"w{i}", "text": f" word{i}", "start": round(0.5 + 0.9 * i, 3), "end": round(0.5 + 0.9 * (i + 1), 3)}
             for i in range(70)]
    t, f = write(d / "t.json", {"words": words}), facts(d / "f.json", duration=80.0)
    c = write(d / "c.json", [{"rank": 1, "start_word": "w0", "end_word": "w69"}])
    out = d / "o" / "cut.json"
    code, js, _ = run_cli(["--transcript", t, "--clips", c, "--rank", 1, "--facts", f, "--out", out])
    check("too_long: 70 x 0.9 s words exit 1 with over_s > 0 and write nothing",
          code == 1 and js["error"]["code"] == "too_long" and js["over_s"] > 3.0 and not out.exists(), (code, js))
    c = write(d / "c2.json", [{"rank": 1, "start_word": "w0", "end_word": "w60", "freeze_s": 6.0}])
    code, js, _ = run_cli(["--transcript", t, "--clips", c, "--rank", 1, "--facts", f, "--out", out])
    check("too_long: freeze_s counts toward the length", code == 1 and js["error"]["code"] == "too_long"
          and abs(js["kept_s"] + 6.0 - 59.5 - js["over_s"]) < 1e-6, (code, js))
    code, js, _ = run_cli(["--transcript", t, "--clips", c, "--rank", 1, "--facts", f, "--out", out, "--max-len", 70])
    check("--max-len raises the limit", code == 0 and out.exists(), (code, js and js.get("error")))


def case_slivers(d):
    t, f = spec_transcript(d / "t.json"), facts(d / "f.json")
    c = write(d / "c.json", [{"rank": 1, "start_word": "w0", "end_word": "w5"}])

    def run(events):
        sc = write(d / "cuts.json", {"events": events, "reset_frames": []})
        code, js, err = run_cli(["--transcript", t, "--clips", c, "--rank", 1, "--facts", f, "--out", d / "s.json",
                                 "--shot-cuts", sc])
        return code, js, err

    # Segment 1 is canvas frames 45..96 at 60 fps; 'the' starts at 0.85 s (frame 51), 'thing' ends at 1.5 s (90).
    code, js, err = run([{"frame": 5, "t": 50 / 60, "kind": "hard"}, {"frame": 47, "t": 92 / 60, "kind": "soft"}])
    seg = js["segments"][1] if code == 0 else {}
    check("sliver: a hard cut 5 frames into a segment becomes its start", seg.get("k_in") == 50, (code, seg, err[-200:]))
    check("sliver: a soft cut 4 frames before a segment end becomes its end", seg.get("k_out") == 92, seg)
    check("sliver: kept time shrinks by those 9 frames", code == 0 and js["frames"] == 137 - 9, js and js["frames"])
    code, js, _ = run([{"frame": 7, "t": 52 / 60, "kind": "hard"}])
    check("sliver: a cut whose sliver holds a word start is kept with sliver_kept",
          code == 0 and js["segments"][1]["k_in"] == 45 and any(w.startswith("sliver_kept") for w in js["warnings"]),
          js and (js["segments"][1], js["warnings"]))
    code, js, _ = run([{"frame": 5, "t": 50 / 60, "kind": "flash"}, {"frame": 6, "t": 51 / 60, "kind": "fast"}])
    check("sliver: flash and fast events are ignored", code == 0 and js["segments"][1]["k_in"] == 45, js and js["segments"][1])


def case_quiet_guard(d):
    """ref 03 section 2 test plan: 'thing' sounds until 1.62, a laugh (-1.5 dB re words) at 2.3-2.7 and a breath
    (-25.4 dB) at 2.85-3.05. The laugh is kept with 0.10 s pads, the breath is cut, the thing->is gap stays."""
    ff = fx.ffmpeg()
    dlg = d / "dlg.wav"
    words = "+".join(f"between(t\\,{a}\\,{b})" for a, b in ((0.05, 0.3), (0.45, 0.7), (0.85, 1.1), (1.15, 1.62),
                                                              (1.82, 2.0), (3.2, 3.6)))
    cl.run([ff, "-v", "error", "-y", "-f", "lavfi", "-i", f"aevalsrc=0.3*sin(2*PI*200*t)*({words}):s=48000:d=4",
            "-f", "lavfi", "-i", "anoisesrc=color=pink:amplitude=1.0:d=4:r=48000:seed=3",
            "-f", "lavfi", "-i", "anoisesrc=color=white:amplitude=0.02:d=4:r=48000:seed=4",
            "-f", "lavfi", "-i", "anoisesrc=color=white:amplitude=0.003:d=4:r=48000:seed=5",
            "-filter_complex", "[1]volume=0:enable='not(between(t,2.3,2.7))'[laugh];"
                               "[2]volume=0:enable='not(between(t,2.85,3.05))'[breath];"
                               "[0][laugh][breath][3]amix=inputs=4:normalize=0",
            "-c:a", "pcm_s16le", str(dlg)])
    audio = cl.decode_audio(dlg, ff, channels=1, src_channels=1)
    src = d / "quiet.mp4"
    fx.shots_video(src, [("testsrc2", 240)], fps=60, size=(320, 180), audio=audio)
    t, f = spec_transcript(d / "t.json"), facts(d / "f.json", duration=4.0)
    c = write(d / "c.json", [{"rank": 1, "start_word": "w0", "end_word": "w5"}])
    code, js, err = run_cli(["--transcript", t, "--clips", c, "--rank", 1, "--facts", f, "--out", d / "q.json",
                             "--source", src, "--ffprobe", "none"])
    check("quiet guard: exit 0", code == 0, err[-300:])
    if code:
        return
    check("quiet guard: kept [[0,0.4],[0.75,2.1],[2.2,2.81],[3.1,3.75]] (+-0.02 s)",
          close(spans(js), [[0, 0.4], [0.75, 2.1], [2.2, 2.81], [3.1, 3.75]], 0.02), spans(js))
    check("quiet guard: the laugh is kept as sound, the breath is not",
          any(abs(a - 2.3) <= 0.02 and abs(b - 2.71) <= 0.02 for a, b in js["sounds"])
          and not any(a < 3.0 and b > 2.9 for a, b in js["sounds"]), js["sounds"])
    check("quiet guard: the quiet test ran (no skip warning)", js["params"]["quiet_test"] is True
          and not any("quiet_test_skipped" in w for w in js["warnings"]), js["warnings"])


def case_podcast(d):
    """The fixtures podcast: pauses of 0.9, 1.4 and 0.5 s, fillers 'um' and 'uh'; quiet test on its audio."""
    p = fx.podcast(d / "pod", fps=60, size=(320, 180))
    words = p["words"]
    f = facts(d / "f.json", duration=p["truth"]["frames"] / 60)
    c = write(d / "c.json", [{"rank": 1, "start_word": "w0", "end_word": f"w{len(words) - 1}",
                              "hook_line": "so you're telling me", "payoff_line": "that actually worked"}])
    code, js, err = run_cli(["--transcript", d / "pod" / "transcript.json", "--clips", c, "--rank", 1, "--facts", f,
                             "--out", d / "pod.json", "--source", p["path"]])
    check("podcast: exit 0", code == 0, err[-300:])
    if code:
        return
    out_ids = [w["id"] for w in js["words"]]
    check("podcast: the fillers um/uh are gone, every other word kept",
          out_ids == [w["id"] for w in words if w["id"] not in p["truth"]["fillers"]], out_ids)
    gaps = [b["start"] - a["end"] for a, b in zip(js["words"], js["words"][1:])]
    check("podcast: no gap >= 0.30 s is left between output words", max(gaps) < 0.30, round(max(gaps), 3))
    out = {w["id"]: w for w in js["words"]}
    left = []
    for g in p["truth"]["dead_air"]:  # the pause before g["before"], measured from the previous KEPT word
        prev = max((i for i in out if int(i[1:]) < int(g["before"][1:])), key=lambda i: int(i[1:]))
        left.append(round(out[g["before"]]["start"] - out[prev]["end"], 4))
    check("podcast: every dead-air pause (0.96/1.46/0.56 s) is cut to 0.20 s (+1 frame)",
          len(left) == 3 and all(x <= 0.2 + 1 / 60 + 1e-6 for x in left), left)
    src_dur = {w["id"]: w["end"] - w["start"] for w in words}
    check("podcast: kept words keep their length",
          all(abs((w["end"] - w["start"]) - src_dur[w["id"]]) < 2e-6 for w in js["words"]))
    whys = {r["why"] for r in js["removed"]}
    check("podcast: removals are named filler and dead_air", whys == {"filler", "dead_air"}, whys)


def main():
    cl.utf8_stdio()
    tmp = Path(tempfile.mkdtemp(prefix="test_cutlist-"))
    try:
        for case in (case_spec_vector, case_library, case_options, case_errors, case_too_long, case_slivers,
                     case_quiet_guard, case_podcast):
            sub = tmp / case.__name__
            sub.mkdir(exist_ok=True)
            if case is case_library:
                sub = tmp / "case_spec_vector"
            case(sub)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"{'FAILED ' + str(len(FAILS)) if FAILS else 'all passed'}: test_cutlist", flush=True)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
