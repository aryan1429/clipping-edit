"""clipping-edit preflight: find the tools this skill needs and print where they are.

usage: python preflight.py [--json-only]

Checks Python modules, ffmpeg, CUDA, the EffectCraft CLI and the Montserrat Black font.
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


def main():
    json_only = "--json-only" in sys.argv
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
