"""clipping-edit preflight: find the tools this skill needs and print where they are.

usage: python preflight.py [--json-only] [--model PATH]

Checks Python modules, ffmpeg, CUDA, the EffectCraft CLI, the Montserrat Black font and the YuNet face model
(face_track.py). YuNet search order (same as face_track.find_model): --model PATH, env CLIP_YUNET_MODEL (when set,
a missing file is reported, never silently replaced), then in each of ./models, ./models/yunet, ./ (cwd),
<skill>/models, ~/models/yunet, ~/models, ~/.cache/opencv_zoo, ~/.cache/opencv_zoo/face_detection_yunet: the known
file names (face_detection_yunet_2023mar.onnx, ..._2023mar_int8.onnx, ..._2022mar.onnx), else the newest-named
face_detection_yunet*.onnx. A found model is test-loaded (a truncated download is reported).
Prints a status table, then one line `PREFLIGHT_JSON {...}` with the resolved paths.
Exit 0 when every required piece is present (optional ones may be missing), exit 1 otherwise.
Works on Windows, macOS and Linux; uses only the standard library plus whatever it finds.
"""
import importlib
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

REQUIRED_MODULES = ["yt_dlp", "faster_whisper", "cv2", "numpy", "PIL"]
OPTIONAL_MODULES = ["imageio_ffmpeg", "torch"]
EC_NAMES = ["effectcraft-cli", "effectcraft-cli.exe", "effectcraft"]
FONT_FILES = ["Montserrat-Black.ttf", "Montserrat-Black.otf", "MontserratBlack.ttf"]
YUNET_FILES = ["face_detection_yunet_2023mar.onnx", "face_detection_yunet_2023mar_int8.onnx",
               "face_detection_yunet_2022mar.onnx"]
YUNET_HINT = ("not found - download face_detection_yunet_2023mar.onnx from the OpenCV Zoo "
              "(github.com/opencv/opencv_zoo, models/face_detection_yunet) into ./models or ~/models/yunet, "
              "or set CLIP_YUNET_MODEL / pass --model")


def check_module(name):
    try:
        mod = importlib.import_module(name)
        return True, str(getattr(mod, "__version__", "") or "ok")
    except Exception as e:  # ImportError or a broken native build
        return False, f"{type(e).__name__}: {e}"[:80]


def find_ffmpeg():
    exe = shutil.which("ffmpeg")
    if exe:
        return exe, "PATH"
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe(), "imageio_ffmpeg"
    except Exception:
        return None, "not found"


def find_ffprobe(ffmpeg):
    exe = shutil.which("ffprobe")
    if exe:
        return exe
    if ffmpeg:
        p = Path(ffmpeg).with_name("ffprobe" + (".exe" if ffmpeg.lower().endswith(".exe") else ""))
        if p.exists():
            return str(p)
    return None  # optional: ffmpeg -i can stand in for duration checks


def check_cuda():
    try:
        import ctranslate2  # faster-whisper's backend
        n = ctranslate2.get_cuda_device_count()
        if n > 0:
            return True, f"ctranslate2 sees {n} CUDA device(s)"
    except Exception:
        pass
    try:
        import torch
        if torch.cuda.is_available():
            return True, f"torch: {torch.cuda.get_device_name(0)}"
    except Exception:
        pass
    return False, "no CUDA - faster-whisper will use CPU int8"


def find_effectcraft():
    env = os.environ.get("EFFECTCRAFT_CLI")
    if env:
        if Path(env).is_file():
            return env, "EFFECTCRAFT_CLI"
        exe = shutil.which(env)  # also accept a command name on PATH
        if exe:
            return exe, "EFFECTCRAFT_CLI"
        return None, f"EFFECTCRAFT_CLI set but not found: {env}"
    for name in EC_NAMES:
        exe = shutil.which(name)
        if exe:
            return exe, "PATH"
    return None, "not found - use the ffmpeg + ASS/libass + Pillow fallback"


def font_dirs():
    home = Path.home()
    sysname = platform.system()
    if sysname == "Windows":
        dirs = [Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts",
                Path(os.environ.get("LOCALAPPDATA", home / "AppData/Local")) / "Microsoft/Windows/Fonts"]
    elif sysname == "Darwin":
        dirs = [home / "Library/Fonts", Path("/Library/Fonts"), Path("/System/Library/Fonts")]
    else:
        dirs = [home / ".fonts", home / ".local/share/fonts", Path("/usr/share/fonts"), Path("/usr/local/share/fonts")]
    return [d for d in dirs if d.is_dir()]


def find_font():
    env = os.environ.get("CLIP_FONT")
    if env and Path(env).is_file():
        return env, "CLIP_FONT"
    wanted = {f.lower() for f in FONT_FILES}
    for d in font_dirs():
        for f in FONT_FILES:  # fast path: flat font dir
            if (d / f).is_file():
                return str(d / f), "font dir"
        try:
            for p in d.rglob("*"):
                if p.name.lower() in wanted:
                    return str(p), "font dir"
        except OSError:
            continue
    if shutil.which("fc-match"):
        try:
            out = subprocess.run(["fc-match", "-f", "%{file}", "Montserrat:black"],
                                 capture_output=True, text=True, timeout=10).stdout.strip()
            if out and "montserrat" in out.lower():
                return out, "fc-match"
        except Exception:
            pass
    return None, "not found - install Montserrat (Google Fonts) or set CLIP_FONT; fallback Arial Black"


def find_yunet(explicit=None):
    """Same search order as face_track.find_model (kept stdlib-only here). explicit "" = --model without a path."""
    if explicit is not None:
        if not explicit:
            return None, "--model given without a path"
        if Path(explicit).is_file():
            return str(Path(explicit).resolve()), "--model"
        return None, f"--model not found: {explicit}"
    env = os.environ.get("CLIP_YUNET_MODEL")
    if env:
        if Path(env).is_file():
            return str(Path(env).resolve()), "CLIP_YUNET_MODEL"
        return None, f"CLIP_YUNET_MODEL set but not found: {env} (face_track.py exits 2 on it; fix or unset it)"
    home = Path.home()
    dirs = [Path.cwd() / "models", Path.cwd() / "models" / "yunet", Path.cwd(),
            Path(__file__).resolve().parents[1] / "models", home / "models" / "yunet", home / "models",
            home / ".cache" / "opencv_zoo", home / ".cache" / "opencv_zoo" / "face_detection_yunet"]
    for d in dirs:
        for f in YUNET_FILES:
            if (d / f).is_file():
                return str((d / f).resolve()), str(d)
        if d.is_dir():
            hits = sorted(d.glob("face_detection_yunet*.onnx"))
            if hits:
                return str(hits[-1].resolve()), str(d)
    return None, YUNET_HINT


def check_yunet_loads(path):
    """True when cv2 has FaceDetectorYN and the model loads (catches a truncated download)."""
    try:
        import cv2
        if not hasattr(cv2, "FaceDetectorYN"):
            return False, f"cv2 {cv2.__version__} has no FaceDetectorYN (needs opencv-python 4.5.4+)"
        cv2.FaceDetectorYN.create(path, "", (320, 240), 0.6, 0.3, 50)
        return True, "loads"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"[:80]


def main():
    json_only = "--json-only" in sys.argv
    model_arg = None
    if "--model" in sys.argv:
        i = sys.argv.index("--model")
        nxt = sys.argv[i + 1] if i + 1 < len(sys.argv) else ""
        model_arg = "" if nxt.startswith("--") else nxt
    rows = []  # (item, status, required, detail)
    res = {"python": sys.executable, "python_version": platform.python_version(), "os": platform.system()}

    for m in REQUIRED_MODULES + OPTIONAL_MODULES:
        ok, detail = check_module(m)
        rows.append((f"module {m}", ok, m in REQUIRED_MODULES, detail))
        res[f"mod_{m}"] = ok

    ffmpeg, src = find_ffmpeg()
    rows.append(("ffmpeg", bool(ffmpeg), True, f"{ffmpeg} ({src})" if ffmpeg else src))
    res["ffmpeg"] = ffmpeg
    ffprobe = find_ffprobe(ffmpeg)
    rows.append(("ffprobe", bool(ffprobe), False, ffprobe or "not found - use `ffmpeg -i` for durations"))
    res["ffprobe"] = ffprobe

    cuda, detail = check_cuda()
    rows.append(("CUDA", cuda, False, detail))
    res["cuda"] = cuda
    res["whisper_device"] = "cuda" if cuda else "cpu"
    res["whisper_compute_type"] = "int8_float16" if cuda else "int8"

    ec, detail = find_effectcraft()
    rows.append(("EffectCraft CLI", bool(ec), False, ec or detail))
    res["effectcraft_cli"] = ec
    res["edit_path"] = "effectcraft" if ec else "ffmpeg_ass_pillow"

    font, detail = find_font()
    rows.append(("Montserrat Black", bool(font), False, font or detail))
    res["font"] = font

    yunet, detail = find_yunet(model_arg)
    if yunet:
        ok, why = check_yunet_loads(yunet)
        detail = f"{yunet} ({detail})" if ok else f"{yunet}: {why}"
        yunet = yunet if ok else None
    rows.append(("YuNet face model", bool(yunet), False, detail))
    res["yunet_model"] = yunet

    missing = [r[0] for r in rows if r[2] and not r[1]]
    res["missing_required"] = missing

    if not json_only:
        w = max(len(r[0]) for r in rows)
        print(f"{'item'.ljust(w)}  status    detail")
        for item, ok, req, detail in rows:
            status = "OK" if ok else ("MISSING" if req else "optional")
            print(f"{item.ljust(w)}  {status.ljust(8)}  {detail}")
        if missing:
            print("\nRequired pieces missing: " + ", ".join(missing))
            print(f'Install: "{sys.executable}" -m pip install yt-dlp faster-whisper opencv-python numpy pillow imageio-ffmpeg')
    print("PREFLIGHT_JSON " + json.dumps(res))
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
