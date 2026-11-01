"""Tests for skill/scripts/splice.py (run: python -P tests/test_splice.py from the repo root).

Runs the real CLI as a subprocess on synthetic media (tests/fixtures.py): the --selftest with its negative
controls, a cutlist.py -> splice.py chain on the fixtures podcast, re-timed sources (25 fps and VFR on a 30 fps
canvas), a late-starting mono audio stream, awkward paths and usage errors. One line per check; exit 0 = all pass.
"""
import json
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
import splice  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skill" / "scripts"
TAGS = "setparams=colorspace=bt709:color_primaries=bt709:color_trc=bt709:range=tv"
FAILS = []


def check(name, cond, detail=""):
    print(f"{'ok  ' if cond else 'FAIL'} {name}" + (f"  [{detail}]" if detail and not cond else ""), flush=True)
    if not cond:
        FAILS.append(name)


def run_cli(script, args, cwd=None):
    cp = subprocess.run([sys.executable, "-P", str(SCRIPTS / script), *map(str, args)], capture_output=True, cwd=cwd)
    try:
        js = json.loads(cp.stdout.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        js = None
    return cp.returncode, js, cp.stderr.decode("utf-8", errors="replace")


def write(path, obj):
    Path(path).write_text(json.dumps(obj), encoding="utf-8")
    return path


def facts(path, fps, duration):
    return write(path, {"canvas_fps": fps, "norm_vf": f"fps={fps},{TAGS}", "duration": duration})


def cut_file(path, pairs, fps):
    segs = cutlist.segments_from_frames(pairs, Fraction(fps))
    return write(path, {"fps": cl.frac_str(Fraction(fps)), "segments": segs, "frames": sum(s["frames"] for s in segs)})


def gates_ok(js):
    return bool(js) and js.get("ok") is True and all(g["ok"] for g in js["gates"].values())


def failed(js):
    return [k for k, g in (js or {}).get("gates", {}).items() if not g["ok"]] or (js or {}).get("error")


def case_selftest(d):
    code, js, err = run_cli("splice.py", ["--selftest", "--workdir", d / "work"])
    check("selftest: exit 0 and ok", code == 0 and js and js["ok"] is True, err[-400:])
    for rate in ("30/1", "30000/1001", "60/1"):
        e = (js or {}).get("selftest", {}).get(rate, {})
        check(f"selftest {rate}: positive cut passes every gate", e.get("positive", {}).get("ok") is True,
              e.get("positive", {}).get("failed"))
        for name, gate in (("per_segment_aac", "stem_samples"), ("decimals3", "frame_identity"), ("no_ramps", "click")):
            n = e.get("negatives", {}).get(name, {})
            check(f"selftest {rate}: negative control {name} fails {gate}", gate in n.get("failed", []), n)


def case_podcast(d):
    ff = fx.ffmpeg()
    p = fx.podcast(d / "pod", fps=60, size=(320, 180))
    n_words = len(p["words"])
    f = facts(d / "facts.json", "60/1", p["truth"]["frames"] / 60)
    c = write(d / "clips.json", [{"rank": 1, "start_word": "w0", "end_word": f"w{n_words - 1}"}])
    code, cj, err = run_cli("cutlist.py", ["--transcript", d / "pod" / "transcript.json", "--clips", c, "--rank", 1,
                                           "--facts", f, "--out", d / "clip" / "cutlist.json", "--source", p["path"]])
    check("chain: cutlist.py exit 0", code == 0, err[-300:])
    out = d / "clip"
    (out / "cut.mov").write_bytes(b"stale")  # a stale output from an earlier run must be replaced
    code, js, err = run_cli("splice.py", ["--cutlist", out / "cutlist.json", "--source", p["path"], "--facts", f,
                                          "--outdir", out, "--ffprobe", "none"])
    check("chain: splice.py exit 0, every gate ok", code == 0 and gates_ok(js), (code, failed(js), err[-300:]))
    if code:
        return
    frames = cl.count_frames(out / "cut.mov", ff)
    check("chain: cut.mov frames == cut-list frames (stale file replaced)", frames == cj["frames"] == js["frames"],
          (frames, cj["frames"]))
    check("chain: files named as in the contract", js["files"] == {"video": "cut.mov", "dialogue": "dialogue.wav"},
          js["files"])
    stem = cl.decode_audio(out / "dialogue.wav", ff, channels=1, src_channels=1, align_start=False)
    check("chain: dialogue.wav has round(frames * 800) samples", len(stem) == cj["frames"] * 800, len(stem))
    src = cl.decode_audio(p["path"], ff, channels=1, src_channels=1)
    err_max = 0.0
    for s in cj["segments"]:
        st, m, a = s["out_frame"] * 800, s["frames"] * 800, s["k_in"] * 800
        err_max = max(err_max, float(abs(stem[st + 1440:st + m - 1440] - src[a + 1440:a + m - 1440]).max()))
    check("chain: the stem equals the source at remapped positions between the ramps", err_max < 1e-4, err_max)
    leftovers = [x.name for x in out.iterdir() if ".tmp-" in x.name or x.name.startswith(".splice-")]
    check("chain: no temp files or segment folders left behind", not leftovers, leftovers)


def _retimed_source(path, kind):
    """kind 25: a 25 fps source; kind vfr: a 60 fps source thinned to VFR (frames 0-39, then 2 of every 3)."""
    track = fx.talk_track([{"start": 0.4, "end": 7.6}], 8.0)
    if kind == "25":
        fx.shots_video(path, [("testsrc2", 200)], fps=25, size=(320, 180), audio=track)
        return
    base = path.with_name("base60.mp4")
    fx.shots_video(base, [("testsrc2", 480)], fps=60, size=(320, 180), audio=track)
    cl.run([fx.ffmpeg(), "-v", "error", "-y", "-i", str(base), "-vf", "select='lt(n\\,40)+mod(n\\,3)'",
            "-fps_mode", "vfr", "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-c:a", "copy", str(path)])


def case_retimed(d):
    """norm_vf re-times these sources to the 30 fps canvas: the plain seek of ref 03 section 2 loses the frame on
    screen at k_in; splice.py's pre-roll keeps it and frame_identity proves it."""
    ff = fx.ffmpeg()
    pairs = [(4, 57), (85, 123), (147, 164), (182, 225)]  # the selftest keeps on the 30 fps grid
    for kind in ("25", "vfr"):
        src = d / f"src_{kind}.mp4"
        _retimed_source(src, kind)
        f = facts(d / f"facts_{kind}.json", "30/1", 8.0)
        c = cut_file(d / f"cut_{kind}.json", pairs, 30)
        code, js, err = run_cli("splice.py", ["--cutlist", c, "--source", src, "--facts", f, "--outdir", d / f"out_{kind}"])
        check(f"re-timed {kind} source on a 30 fps canvas: every gate ok (frame_identity included)",
              code == 0 and gates_ok(js), (code, failed(js), err[-300:]))

        def plain_seek(src_, seg, fps, norm_vf, out, ffmpeg, crf):  # the verified rule's command, as written
            cl.run([ffmpeg, "-v", "error", "-y", "-nostdin", "-ss", splice.T(seg["k_in"], fps), "-i", str(src_),
                    "-map", "0:V:0", "-vf", norm_vf, "-frames:v", str(seg["frames"]), *splice.mezz(crf), str(out)])

        work = d / f"plain_{kind}"
        work.mkdir()
        segs = cutlist.segments_from_frames(pairs, Fraction(30))
        norm_vf = f"fps=30,{TAGS}"
        splice.build_video(src, segs, Fraction(30), norm_vf, work, work / "cut.mov", ff, 12, encoder=plain_seek)
        g = splice.video_gates(work / "cut.mov", segs, Fraction(30), src, norm_vf, ff, None)
        check(f"negative control: the plain -ss T(k_in) cut of the {kind} source fails frame_identity only",
              [k for k, v in g.items() if not v["ok"]] == ["frame_identity"], {k: v["ok"] for k, v in g.items()})


def case_late_mono_audio(d):
    """A mono audio stream starting 0.25 s after the video: the stem must stay on the video's clock."""
    ff = fx.ffmpeg()
    video = d / "v.mp4"
    fx.shots_video(video, [("testsrc2", 240)], fps=60, size=(320, 180))
    tone = d / "tone.wav"
    x = fx.talk_track([{"start": 0.5, "end": 1.6}, {"start": 2.0, "end": 3.5}], 4.0)
    cl.write_wav_f32(tone, x)
    src = d / "late.mp4"
    cl.run([ff, "-v", "error", "-y", "-i", str(video), "-itsoffset", "0.25", "-i", str(tone), "-map", "0:v", "-map",
            "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", str(src)])
    f = facts(d / "facts.json", "60/1", 4.0)
    c = cut_file(d / "cut.json", [(0, 60), (90, 200)], 60)
    code, js, err = run_cli("splice.py", ["--cutlist", c, "--source", src, "--facts", f, "--outdir", d / "out"])
    check("late mono audio: exit 0, every gate ok", code == 0 and gates_ok(js), (code, failed(js), err[-300:]))
    if code:
        return
    import numpy as np
    stem = cl.decode_audio(d / "out" / "dialogue.wav", ff, channels=1, src_channels=1, align_start=False)
    want = np.concatenate([np.zeros(12000, np.float32), x])[:48000]  # the track as the video clock sees it
    n = 1 << 17
    corr = np.fft.irfft(np.fft.rfft(stem[:48000], n) * np.conj(np.fft.rfft(want, n)), n)
    lag = int(np.argmax(corr))
    lag = lag - n if lag > n // 2 else lag
    # mp4 stores the late start in its 1 ms movie timescale (measured -32 samples for every reader), so allow 1 ms;
    # a decode without async=1:first_pts=0 lands about -11000 samples off.
    check("late mono audio: the stem lines up with the track delayed 0.25 s (within the mux's 1 ms)",
          abs(lag) <= 48, lag)
    asr = cl.decode_audio(src, ff, channels=1, src_channels=1)  # the ASR clock (ref 03 section 1)
    diff = float(abs(stem[1440:60 * 800 - 1440] - asr[1440:60 * 800 - 1440]).max())
    check("late mono audio: the stem equals the ASR-clock decode sample for sample", diff < 1e-4, diff)


def case_paths(d):
    """An outdir with a space and an apostrophe, given relative to a different working directory."""
    p = fx.podcast(d / "src", fps=30, size=(320, 180), name="pod cast's.mp4")
    f = facts(d / "facts.json", "30/1", p["truth"]["frames"] / 30)
    c = cut_file(d / "cut.json", [(20, 70), (100, 160)], 30)
    elsewhere = d / "elsewhere"
    elsewhere.mkdir()
    code, js, err = run_cli("splice.py", ["--cutlist", c, "--source", p["path"], "--facts", f, "--outdir",
                                          "it's a dir/clip 01", "--keep-temp"], cwd=elsewhere)
    out = elsewhere / "it's a dir" / "clip 01"
    check("paths: space + apostrophe outdir relative to another cwd: exit 0", code == 0 and gates_ok(js),
          (code, failed(js), err[-300:]))
    check("paths: cut.mov and dialogue.wav written there", (out / "cut.mov").is_file() and (out / "dialogue.wav").is_file())
    check("paths: --keep-temp keeps the segment folder", any(x.name.startswith(".splice-") for x in out.iterdir()))


def case_errors(d):
    ff = fx.ffmpeg()
    src = d / "s.mp4"
    fx.shots_video(src, [("testsrc2", 120)], fps=60, size=(160, 90), audio=fx.talk_track([{"start": 0.2, "end": 1.8}], 2.0))
    silent = d / "silent.mp4"
    fx.shots_video(silent, [("testsrc2", 120)], fps=60, size=(160, 90))
    good = cut_file(d / "cut.json", [(10, 50), (70, 110)], 60)
    f60 = facts(d / "f60.json", "60/1", 2.0)
    cases = {
        "fps mismatch (facts 30, cut list 60)": ([good, src, facts(d / "f30.json", "30/1", 2.0)], "fps_mismatch"),
        "norm_vf without a leading fps=": ([good, src, write(d / "fx.json", {"canvas_fps": "60/1", "norm_vf": TAGS})],
                                           "bad_facts"),
        "cut past the source end": ([cut_file(d / "long.json", [(10, 50), (70, 300)], 60), src, f60], "cut_past_end"),
        "source without audio": ([good, silent, f60], "no_audio"),
        "inconsistent cut list": ([write(d / "bad.json", {"fps": "60/1", "segments": [{"k_in": 0, "k_out": 10, "frames": 9,
                                                                                       "out_frame": 0}]}), src, f60],
                                  "bad_cutlist"),
    }
    for name, ((c, s, f), want) in cases.items():
        code, js, _ = run_cli("splice.py", ["--cutlist", c, "--source", s, "--facts", f, "--outdir", d / "o"])
        got = (js or {}).get("error", {}).get("code")
        check(f"error {name}: exit 2 with {want}", code == 2 and got == want and js.get("version") == "1.0.0", (code, got))
    code, js, _ = run_cli("splice.py", ["--cutlist", good, "--source", src])
    check("error missing --facts/--outdir: exit 2 usage", code == 2 and js and js["error"]["code"] == "usage", (code, js))
    check("errors: no output folder was created for rejected inputs", not (d / "o").exists())


def main():
    cl.utf8_stdio()
    tmp = Path(tempfile.mkdtemp(prefix="test_splice-"))
    try:
        for case in (case_selftest, case_podcast, case_retimed, case_late_mono_audio, case_paths, case_errors):
            sub = tmp / case.__name__
            sub.mkdir()
            case(sub)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"{'FAILED ' + str(len(FAILS)) if FAILS else 'all passed'}: test_splice", flush=True)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
