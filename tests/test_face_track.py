"""Tests for skill/scripts/face_track.py (run: python -P tests/test_face_track.py from the repo root).

- selftest: simulated detections with known truth (jitter, margin, zero lag, reset, jump cut, lock/steady shake).
- CLI chain on a written det.json: track -> stabilize (smooth, lock, steady) -> qc, and render on a lavfi clip.
- usage errors exit 2; detect on a face-free lavfi clip (when a YuNet model is found) finds nothing and the
  second run is a cache hit.
- Optional real footage: set CLIP_TEST_FACE_VIDEO to a short clip with one face to run `run` end to end.
One line per check; exit 0 = all pass.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixtures as fx  # noqa: E402  (also puts skill/scripts on sys.path)
import cliplib as cl  # noqa: E402
import face_track as ft  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skill" / "scripts" / "face_track.py"
FAILS = []


def check(name, cond, detail=""):
    print(f"{'ok  ' if cond else 'FAIL'} {name}" + (f"  [{detail}]" if detail and not cond else ""), flush=True)
    if not cond:
        FAILS.append(name)


def run_cli(args, env=None):
    cp = subprocess.run([sys.executable, "-P", str(SCRIPT), *map(str, args)], capture_output=True,
                        env={**os.environ, **(env or {})})
    try:
        js = json.loads(cp.stdout.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        js = None
    return cp.returncode, js, cp.stderr.decode("utf-8", errors="replace")


def case_selftest():
    code, js, err = run_cli(["selftest"])
    check("selftest: exit 0", code == 0, err[-600:])
    if js:
        for name, c in js["checks"].items():
            check(f"selftest: {name}", c["ok"], c["measured"])


def synth_det(d, n=60, fps=30):
    rng = np.random.default_rng(4)
    t = np.arange(n) / fps
    x = 800 + 10 * np.sin(2 * np.pi * 0.5 * t)
    x[n // 2:] = 1200
    y = np.full(n, 320.0)
    det = ft.synth_detections(n, fps, 1920, 1080, x, y, np.full(n, 240.0), rng)
    det.update({"ok": True, "version": ft.SCRIPT_VERSION, "scale": 2.0})
    p = d / "det.json"
    p.write_text(json.dumps(det), encoding="utf-8")
    return p, n


def case_chain(d):
    det, n = synth_det(d)
    code, js, err = run_cli(["track", det, "--out", d / "tracks.json", "--cut-frames", n // 2])
    check("track: exit 0, two face segments, reset at the cut", code == 0 and js and js["resets"] == [n // 2]
          and [s["kind"] for s in js["segments"]] == ["face", "face"], (code, js, err[-300:]))
    for mode in ("smooth", "lock", "steady"):
        out = d / f"path_{mode}.json"
        code, js, err = run_cli(["stabilize", d / "tracks.json", "--out", out, "--mode", mode, "--size", "1080x1920"])
        check(f"stabilize {mode}: exit 0", code == 0 and out.is_file(), err[-300:])
        code, js, err = run_cli(["qc", out, "--qc-dir", d / f"qc_{mode}"])
        m = js["metrics"] if js and "metrics" in js else {}
        check(f"qc {mode}: gate passes, face inside the margin, no pan across the cut",
              code == 0 and m.get("face_inside_margin_pct") == 100.0 and m.get("pan_across_cut") == 0,
              (code, m, js and js.get("findings")))
        if mode == "smooth":
            check("qc: writes the plot and the JSON", (d / "qc_smooth" / "face_track_qc.json").is_file()
                  and (d / "qc_smooth" / "face_track_path.png").is_file())
            p = json.loads(out.read_text(encoding="utf-8"))
            ec = p["effectcraft"]
            k = 5
            s = ec["scale"][k] / 100
            # the crop centre must land on the comp centre: pos + s * (centre - anchor) == comp / 2
            cxk, cyk = p["frames_data"]["cx"][k], p["frames_data"]["cy"][k]
            px = ec["position"][k][0] + s * (cxk - ec["anchor"][0])
            py = ec["position"][k][1] + s * (cyk - ec["anchor"][1])
            check("effectcraft keys map the crop centre to the comp centre", abs(px - 540) < 0.01
                  and abs(py - 960) < 0.01 and len(ec["position"]) == n, (px, py))
    code, js, err = run_cli(["stabilize", d / "tracks.json", "--out", d / "path_nr.json", "--no-reset"])
    code, js, err = run_cli(["qc", d / "path_nr.json", "--no-plot"])
    check("negative control: --no-reset fails the qc gate (pan_across_cut)", code == 1 and js
          and any(f["id"] == "pan_across_cut" for f in js["findings"]), (code, js and js.get("findings")))
    # render on a 1920x1080 lavfi clip with the same frame count
    src = d / "src.mp4"
    cl.run([fx.ffmpeg(), "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=s=1920x1080:r=30:d={n / 30}",
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", src])
    out = d / "preview.mp4"
    code, js, err = run_cli(["render", src, d / "path_smooth.json", "--out", out, "--overlay"])
    info = cl.probe(out, fx.ffmpeg()) if out.is_file() else None
    frames = cl.decoded_frame_count(out, fx.ffmpeg())[0] if out.is_file() else 0
    check("render: 1080x1920, one frame per path frame", code == 0 and info and info["video"]["width"] == 1080
          and info["video"]["height"] == 1920 and frames == n, (code, js, frames, err[-300:]))
    return src


def case_usage(d):
    code, js, _ = run_cli([])
    check("usage: no subcommand -> exit 2", code == 2 and js and js["error"]["code"] == "usage", js)
    det, _ = synth_det(d)
    code, js, _ = run_cli(["stabilize", det, "--out", d / "x.json"])
    check("usage: stabilize on a det.json -> exit 2 bad_input", code == 2 and js["error"]["code"] == "bad_input", js)
    code, js, _ = run_cli(["track", det, "--out", d / "t.json", "--cut-frames", "a,b"])
    check("usage: bad --cut-frames -> exit 2", code == 2, js)
    code, js, _ = run_cli(["detect", d / "missing.mp4", "--out", d / "d.json", "--model", d / "none.onnx"])
    check("usage: missing --model -> exit 2 model_missing", code == 2 and js["error"]["code"] == "model_missing", js)


def case_detect(d, src):
    model, how = ft.find_model()
    if not model:
        print(f"skip detect: no YuNet model ({how})")
        return
    out = d / "det_lavfi.json"
    code, js, err = run_cli(["detect", src, "--out", out])
    check("detect: face-free clip -> exit 0, no faces", code == 0 and js and js["frames_with_face"] == 0
          and js["frames"] == 60, (code, js, err[-300:]))
    code, js, _ = run_cli(["detect", src, "--out", out])
    check("detect: second run is a cache hit", code == 0 and js and js.get("cached") is True, js)
    real = os.environ.get("CLIP_TEST_FACE_VIDEO")
    if real and Path(real).is_file():
        code, js, err = run_cli(["run", real, "--workdir", d / "real", "--max-frames", 300])
        check("real clip: run passes the gate and finds a face", code == 0 and js and
              js["detect"]["frames_with_face"] > 0, (code, js and js.get("findings"), err[-300:]))


def main():
    cl.utf8_stdio()
    d = Path(tempfile.mkdtemp(prefix="test_face_track_"))
    try:
        case_selftest()
        src = case_chain(d)
        case_usage(d)
        case_detect(d, src)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    print(f"{'ALL PASS' if not FAILS else f'{len(FAILS)} FAILED: ' + ', '.join(FAILS)}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
