"""Shared helpers for the clipping-edit scripts (not a CLI).

Import it from a sibling script like this (`python -P` does not put the script's folder on sys.path):
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import cliplib as cl

Conventions every script follows (ref 03 section 1, "Script hygiene"):
- One JSON object on stdout; progress and logs on stderr.
- Exit codes: 0 ok, 1 a step or gate failed, 2 usage error or unreadable input.
- UTF-8 stdio on every platform; subprocess output is decoded with errors="replace".
- ffprobe is optional. Every probe has an ffmpeg-only fallback (imageio-ffmpeg ships no ffprobe).
- Times handed to ffmpeg are written with 6 decimals (`t6`); frame rates are exact fractions.
Dependencies: the standard library; numpy only for the decode helpers.
"""
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIB_VERSION = "1.0.0"

# Windows NTSTATUS exit codes that mean the ffmpeg build itself is broken (missing or bad DLLs).
BROKEN_BUILD_CODES = {3221225781: "STATUS_DLL_NOT_FOUND", 3221225595: "STATUS_INVALID_IMAGE_FORMAT",
                      3221225794: "STATUS_DLL_INIT_FAILED"}


# ---------------------------------------------------------------- stdio, errors, JSON envelope

def utf8_stdio():
    """Make stdout/stderr UTF-8 so titles and emoji never crash a Windows pipe."""
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors=s.errors)
        except Exception:
            pass


def log(*parts):
    print(*parts, file=sys.stderr, flush=True)


class ClipError(Exception):
    """A failure with a stable code, a message, an optional fix hint and an exit code (1 or 2)."""

    def __init__(self, code, message, hint=None, exit_code=1):
        super().__init__(message)
        self.code, self.message, self.hint, self.exit_code = code, message, hint, exit_code

    def envelope(self):
        err = {"code": self.code, "message": self.message}
        if self.hint:
            err["hint"] = self.hint
        return {"ok": False, "error": err}


def emit(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=1, default=_json_default), flush=True)


def _json_default(o):
    if isinstance(o, Fraction):
        return frac_str(o)
    if isinstance(o, Path):
        return o.as_posix()
    try:  # numpy scalars and arrays
        import numpy as np
        if isinstance(o, np.generic):
            return o.item()
        if isinstance(o, np.ndarray):
            return o.tolist()
    except Exception:
        pass
    raise TypeError(f"not JSON serialisable: {type(o).__name__}")


def run_main(main):
    """Run `main()` (returns an exit code) with UTF-8 stdio and a JSON error envelope on ClipError."""
    utf8_stdio()
    try:
        code = main()
    except ClipError as e:
        emit(e.envelope())
        log(f"error [{e.code}]: {e.message}" + (f"\nhint: {e.hint}" if e.hint else ""))
        code = e.exit_code
    except KeyboardInterrupt:
        code = 1
    sys.exit(code if isinstance(code, int) else 0)


# ---------------------------------------------------------------- tools

def find_ffmpeg(explicit=None):
    if explicit:
        p = shutil.which(explicit) or (explicit if Path(explicit).is_file() else None)
        if not p:
            raise ClipError("ffmpeg_missing", f"--ffmpeg not found: {explicit}", exit_code=2)
        return p
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        raise ClipError("ffmpeg_missing", "ffmpeg not found on PATH and imageio-ffmpeg is not installed",
                        hint="pip install imageio-ffmpeg, or put ffmpeg on PATH", exit_code=2)


def find_ffprobe(ffmpeg=None, explicit=None):
    """ffprobe path or None. explicit='none' forces the ffmpeg-only fallback."""
    if explicit:
        if explicit.lower() == "none":
            return None
        p = shutil.which(explicit) or (explicit if Path(explicit).is_file() else None)
        if not p:
            raise ClipError("ffprobe_missing", f"--ffprobe not found: {explicit}", exit_code=2)
        return p
    exe = shutil.which("ffprobe")
    if exe:
        return exe
    if ffmpeg:
        name = "ffprobe" + (".exe" if str(ffmpeg).lower().endswith(".exe") else "")
        p = Path(ffmpeg).with_name(name)
        if p.is_file():
            return str(p)
    return None


def run(cmd, *, timeout=None, check=True, binary=False, input=None, cwd=None):
    """subprocess.run with captured output, no stdin prompts and a readable error on failure."""
    cmd = [str(c) for c in cmd]
    try:
        cp = subprocess.run(cmd, input=input, capture_output=True, timeout=timeout, cwd=cwd,
                            stdin=None if input is not None else subprocess.DEVNULL)
    except FileNotFoundError:
        raise ClipError("tool_missing", f"cannot run {cmd[0]}", exit_code=2)
    except subprocess.TimeoutExpired:
        raise ClipError("timeout", f"{Path(cmd[0]).name} exceeded {timeout} s")
    out = cp.stdout if binary else cp.stdout.decode("utf-8", errors="replace")
    err = cp.stderr.decode("utf-8", errors="replace")
    cp = subprocess.CompletedProcess(cmd, cp.returncode, out, err)
    if check and cp.returncode != 0:
        rc = cp.returncode & 0xFFFFFFFF
        if rc in BROKEN_BUILD_CODES:
            raise ClipError("broken_ffmpeg_build", f"{Path(cmd[0]).name} exited {BROKEN_BUILD_CODES[rc]}",
                            hint="the ffmpeg build cannot start (missing DLL); reinstall it or use imageio-ffmpeg")
        tail = "\n".join(err.strip().splitlines()[-15:])
        raise ClipError("tool_failed", f"{Path(cmd[0]).name} exited {cp.returncode}", hint=tail or None)
    return cp


def ffmpeg_version(ffmpeg):
    first = run([ffmpeg, "-hide_banner", "-version"], check=False).stdout.splitlines()
    return first[0].strip() if first else "unknown"


def has_filters(ffmpeg, names):
    """{name: bool} for each filter name in `names`."""
    out = run([ffmpeg, "-hide_banner", "-filters"], check=False).stdout
    present = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and re.fullmatch(r"[TSC.]{2,3}", parts[0]):
            present.add(parts[1])
    return {n: n in present for n in names}


# ---------------------------------------------------------------- numbers and time

def t6(x):
    """A time in seconds as ffmpeg should get it: 6 decimals, never '-0.000000'."""
    s = f"{float(x):.6f}"
    return "0.000000" if s == "-0.000000" else s


def frac_str(f):
    f = Fraction(f)
    return f"{f.numerator}/{f.denominator}"


def parse_rate(s):
    """'30000/1001', '60/1', '29.97', '59.94', '60', '1k' -> Fraction. Printed decimals snap to N or N*1000/1001."""
    if s is None:
        return None
    if isinstance(s, (int, Fraction)):
        return Fraction(s)
    s = str(s).strip()
    if not s or s in ("0/0", "N/A"):
        return None
    if "/" in s:
        n, d = s.split("/", 1)
        if float(d) == 0:
            return None
        return Fraction(int(n), int(d))
    mult = 1000 if s.endswith("k") else 1
    p = float(s.rstrip("k")) * mult
    if p <= 0:
        return None
    if abs(p - round(p)) < 0.005:
        return Fraction(round(p))
    n = round(p * 1.001)
    if abs(p - n * 1000 / 1001) < 0.006:
        return Fraction(n * 1000, 1001)
    return Fraction(p).limit_denominator(1001)


def _hms(s):
    h, m, sec = s.split(":")
    return int(h) * 3600 + int(m) * 60 + float(sec)


# ---------------------------------------------------------------- probing

_SPACE_NAMES = {"bt709", "bt470bg", "smpte170m", "smpte240m", "bt2020nc", "bt2020c", "bt2020", "fcc",
                "ycgco", "gbr", "rgb", "ictcp", "chroma-derived-nc", "chroma-derived-c", "smpte2085"}
_FIELD_ORDER = {"progressive", "top first", "bottom first", "top coded first (swapped)",
                "bottom coded first (swapped)", "tt", "bb", "tb", "bt"}
_LAYOUT_CHANNELS = {"mono": 1, "stereo": 2, "2.1": 3, "3.0": 3, "quad": 4, "4.0": 4, "5.0": 5, "5.1": 6,
                    "6.1": 7, "7.1": 8}


def probe(path, ffmpeg=None, ffprobe=None):
    """Container and first video/audio stream facts, via ffprobe when present, else `ffmpeg -i`.

    Returns {"path", "probe", "duration", "start", "title",
             "video": {"codec", "pix_fmt", "width", "height", "sar", "rotation", "display_w", "display_h",
                       "fps_r", "fps_avg" (Fraction or None), "color_range", "color_space",
                       "color_transfer", "color_primaries", "start"} or None,
             "audio": {"codec", "sample_rate", "channels", "layout", "start"} or None}.
    rotation is the clockwise display rotation in degrees (0, 90, 180, 270).
    """
    path = str(path)
    if not Path(path).is_file():
        raise ClipError("input_missing", f"no such file: {path}", exit_code=2)
    ffmpeg = ffmpeg or find_ffmpeg()
    if ffprobe:
        info = _probe_ffprobe(path, ffprobe)
    else:
        info = _probe_ffmpeg(path, ffmpeg)
    v = info.get("video")
    if v:
        rot = v.get("rotation") or 0
        swap = rot % 180 == 90
        v["display_w"], v["display_h"] = (v["height"], v["width"]) if swap else (v["width"], v["height"])
    return info


def _probe_ffprobe(path, ffprobe):
    cp = run([ffprobe, "-v", "error", "-show_format", "-show_streams", "-of", "json", path], check=False)
    if cp.returncode != 0:
        raise ClipError("unreadable_input", f"ffprobe cannot read {path}", hint=cp.stderr.strip()[-500:], exit_code=2)
    j = json.loads(cp.stdout or "{}")
    fmt = j.get("format", {})
    info = {"path": path, "probe": "ffprobe", "duration": _f(fmt.get("duration")), "start": _f(fmt.get("start_time")),
            "title": (fmt.get("tags") or {}).get("title"), "video": None, "audio": None}
    for st in j.get("streams", []):
        kind = st.get("codec_type")
        if kind == "video" and info["video"] is None and not (st.get("disposition") or {}).get("attached_pic"):
            rot = 0
            for sd in st.get("side_data_list", []) or []:
                if "rotation" in sd:
                    rot = int(round(-float(sd["rotation"]))) % 360
            if not rot and (st.get("tags") or {}).get("rotate"):
                rot = int(st["tags"]["rotate"]) % 360
            info["video"] = {
                "codec": st.get("codec_name"), "pix_fmt": st.get("pix_fmt"),
                "width": int(st.get("width", 0)), "height": int(st.get("height", 0)),
                "sar": (st.get("sample_aspect_ratio") or "1:1").replace("0:1", "1:1"), "rotation": rot,
                "fps_r": parse_rate(st.get("r_frame_rate")), "fps_avg": parse_rate(st.get("avg_frame_rate")),
                "color_range": st.get("color_range"), "color_space": st.get("color_space"),
                "color_transfer": st.get("color_transfer"), "color_primaries": st.get("color_primaries"),
                "start": _f(st.get("start_time")), "nb_frames": _i(st.get("nb_frames"))}
        elif kind == "audio" and info["audio"] is None:
            info["audio"] = {"codec": st.get("codec_name"), "sample_rate": _i(st.get("sample_rate")),
                             "channels": _i(st.get("channels")), "layout": st.get("channel_layout"),
                             "start": _f(st.get("start_time"))}
    return info


def _probe_ffmpeg(path, ffmpeg):
    cp = run([ffmpeg, "-hide_banner", "-nostdin", "-i", path], check=False)
    err = cp.stderr
    if "Input #0" not in err:
        raise ClipError("unreadable_input", f"ffmpeg cannot read {path}", hint=err.strip()[-500:], exit_code=2)
    info = {"path": path, "probe": "ffmpeg", "duration": None, "start": None, "title": None, "video": None, "audio": None}
    m = re.search(r"Duration:\s*([0-9:.]+|N/A)(?:,\s*start:\s*(-?[0-9.]+))?", err)
    if m:
        info["duration"] = _hms(m.group(1)) if m.group(1) != "N/A" else None
        info["start"] = _f(m.group(2))
    head = err.split("Stream #", 1)[0]
    m = re.search(r"^\s{4}title\s*:\s*(.+)$", head, re.M)
    if m:
        info["title"] = m.group(1).strip()
    blocks = re.split(r"\n(?=\s*Stream #)", err)
    for b in blocks:
        first = b.strip().splitlines()[0] if b.strip() else ""
        if not first.startswith("Stream #"):
            continue
        if ": Video:" in first and info["video"] is None and "(attached pic)" not in first:
            info["video"] = _parse_video_line(first, b)
        elif ": Audio:" in first and info["audio"] is None:
            info["audio"] = _parse_audio_line(first)
    return info


def _split_top(s):
    """Split on commas that are not inside parentheses or brackets."""
    out, depth, cur = [], 0, ""
    for ch in s:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def _parse_video_line(first, block):
    body = first.split(": Video:", 1)[1].strip()
    parts = _split_top(body)
    v = {"codec": parts[0].split()[0] if parts else None, "pix_fmt": None, "width": 0, "height": 0, "sar": "1:1",
         "rotation": 0, "fps_r": None, "fps_avg": None, "color_range": None, "color_space": None,
         "color_transfer": None, "color_primaries": None, "start": None, "nb_frames": None}
    for p in parts[1:]:
        m = re.match(r"^([a-z0-9_]+)(?:\((.*)\))?$", p)
        if m and v["pix_fmt"] is None and not re.match(r"^\d", p):
            v["pix_fmt"] = m.group(1)
            for tok in (t.strip() for t in (m.group(2) or "").split(",")):
                if tok in ("tv", "pc"):
                    v["color_range"] = tok
                elif "/" in tok:
                    sp, pr, tr = (tok.split("/") + [None, None])[:3]
                    v["color_space"], v["color_primaries"], v["color_transfer"] = (_nz(sp), _nz(pr), _nz(tr))
                elif tok in _SPACE_NAMES:
                    v["color_space"] = v["color_primaries"] = v["color_transfer"] = tok
            continue
        m = re.match(r"^(\d+)x(\d+)(?:\s*\[SAR (\d+):(\d+) DAR \d+:\d+\])?", p)
        if m and not v["width"]:
            v["width"], v["height"] = int(m.group(1)), int(m.group(2))
            if m.group(3):
                v["sar"] = f"{m.group(3)}:{m.group(4)}"
            continue
        m = re.match(r"^([0-9.]+k?) fps$", p)
        if m:
            v["fps_avg"] = parse_rate(m.group(1))
            continue
        m = re.match(r"^([0-9.]+k?) tbr$", p)
        if m:
            v["fps_r"] = parse_rate(m.group(1))
    m = re.search(r"displaymatrix: rotation of (-?[0-9.]+) degrees", block)
    if m:
        v["rotation"] = int(round(-float(m.group(1)))) % 360
    else:
        m = re.search(r"^\s*rotate\s*:\s*(-?\d+)", block, re.M)
        if m:
            v["rotation"] = int(m.group(1)) % 360
    if v["sar"] in ("0:1", "0:0"):
        v["sar"] = "1:1"
    return v


def _parse_audio_line(first):
    body = first.split(": Audio:", 1)[1].strip()
    parts = _split_top(body)
    a = {"codec": parts[0].split()[0] if parts else None, "sample_rate": None, "channels": None, "layout": None,
         "start": None}
    for p in parts[1:]:
        m = re.match(r"^(\d+) Hz$", p)
        if m:
            a["sample_rate"] = int(m.group(1))
            continue
        m = re.match(r"^(\d+) channels", p)
        if m and a["channels"] is None:
            a["channels"] = int(m.group(1))
            continue
        base = p.split("(")[0].strip()
        if a["layout"] is None and base in _LAYOUT_CHANNELS:
            a["layout"], a["channels"] = p, _LAYOUT_CHANNELS[base]
    return a


def _nz(x):
    return None if x in (None, "", "unknown") else x


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _i(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- frame-level facts

def count_frames(path, ffmpeg, stream="v:0"):
    """Number of video packets (= frames) by stream copy; fast, decodes nothing."""
    cp = run([ffmpeg, "-v", "error", "-nostdin", "-i", str(path), "-map", f"0:{stream}", "-c", "copy",
              "-f", "null", "-", "-progress", "pipe:1"], check=False)
    frames = re.findall(r"^frame=(\d+)", cp.stdout, re.M)
    if cp.returncode != 0 or not frames:
        raise ClipError("unreadable_input", f"cannot count frames of {path}", hint=cp.stderr.strip()[-400:])
    return int(frames[-1])


def decoded_frame_count(path, ffmpeg, stream="v:0"):
    """Frames a decoder actually outputs (slower than count_frames; catches undecodable packets)."""
    cp = run([ffmpeg, "-v", "error", "-nostdin", "-i", str(path), "-map", f"0:{stream}", "-f", "null", "-",
              "-progress", "pipe:1"], check=False)
    frames = re.findall(r"^frame=(\d+)", cp.stdout, re.M)
    if not frames:
        raise ClipError("unreadable_input", f"cannot decode {path}", hint=cp.stderr.strip()[-400:])
    return int(frames[-1]), cp.stderr.strip()


def packet_times(path, ffmpeg, stream="v:0"):
    """(time_base Fraction, [(pts, duration), ...] sorted by pts) from a stream-copy framemd5 dump."""
    cp = run([ffmpeg, "-v", "error", "-nostdin", "-i", str(path), "-map", f"0:{stream}", "-c", "copy",
              "-f", "framemd5", "-"])
    tb, rows = None, []
    for line in cp.stdout.splitlines():
        if line.startswith("#tb"):
            tb = Fraction(line.split(":", 1)[1].strip())
        elif line and not line.startswith("#"):
            f = [x.strip() for x in line.split(",")]
            if len(f) >= 4:
                rows.append((int(f[2]), int(f[3])))
    rows.sort()
    return tb, rows


def keyframe_times(path, ffmpeg):
    """Seconds of each keyframe of the first video stream (decodes keyframes only)."""
    cp = run([ffmpeg, "-hide_banner", "-nostdin", "-skip_frame", "nokey", "-i", str(path), "-map", "0:v:0",
              "-vf", "showinfo", "-f", "null", "-"], check=False)
    return [float(x) for x in re.findall(r"pts_time:\s*(-?[0-9.]+)", cp.stderr)]


# ---------------------------------------------------------------- decoding

def decode_audio(path, ffmpeg, sr=48000, channels=1, start=None, duration=None, stream="a:0", af=None,
                 src_channels=None, align_start=True):
    """Decode audio to float32 numpy, shape (n,) for mono or (n, channels).

    - `start`/`duration` seek on the input side (6 decimals), so the measured window is the played window.
    - Mono from stereo uses an explicit 0.5/0.5 pan (a plain -ac 1 to float output can sum to +3 dB).
    - align_start pads a late-starting audio stream so sample 0 is the container's time 0
      (aresample=async=1:first_pts=0); skipped when seeking.
    """
    import numpy as np
    chain = []
    if align_start and start is None:
        chain.append("aresample=async=1:first_pts=0")
    if af:
        chain.append(af)
    if channels == 1 and (src_channels or 2) == 2:
        chain.append("pan=mono|c0=0.5*c0+0.5*c1")
    elif channels == 2 and src_channels == 1:
        chain.append("pan=stereo|c0=c0|c1=c0")
    chain.append(f"aresample={sr}")
    cmd = [ffmpeg, "-v", "error", "-nostdin"]
    if start is not None:
        cmd += ["-ss", t6(start)]
    if duration is not None:
        cmd += ["-t", t6(duration)]
    cmd += ["-i", str(path), "-map", f"0:{stream}", "-vn", "-af", ",".join(chain)]
    if channels not in (1, 2) or (channels == 1 and src_channels not in (None, 1, 2)):
        cmd += ["-ac", str(channels)]
    cmd += ["-f", "f32le", "-acodec", "pcm_f32le", "-"]
    raw = run(cmd, binary=True).stdout
    x = np.frombuffer(raw, dtype="<f4").copy()
    return x if channels == 1 else x.reshape(-1, channels)


def write_wav_f32(path, x, sr=48000):
    """Write float32 PCM WAV (mono (n,) or (n, ch)) atomically, without clipping."""
    import numpy as np
    import struct
    x = np.asarray(x, dtype="<f4")
    ch = 1 if x.ndim == 1 else x.shape[1]
    data = x.tobytes()
    hdr = b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE"
    hdr += b"fmt " + struct.pack("<IHHIIHH", 16, 3, ch, sr, sr * ch * 4, ch * 4, 32)
    hdr += b"data" + struct.pack("<I", len(data))
    tmp = tmp_path(path)
    with open(tmp, "wb") as f:
        f.write(hdr)
        f.write(data)
    replace_with_retry(tmp, path)


def decode_gray(path, ffmpeg, width, height, fps=None, start=None, duration=None, pre_vf=None):
    """Grey frames as uint8 numpy (n, height, width); scale uses area averaging."""
    import numpy as np
    vf = []
    if pre_vf:
        vf.append(pre_vf)
    if fps is not None:
        vf.append(f"fps={frac_str(fps)}")
    vf.append(f"scale={width}:{height}:flags=area,format=gray")
    cmd = [ffmpeg, "-v", "error", "-nostdin"]
    if start is not None:
        cmd += ["-ss", t6(start)]
    if duration is not None:
        cmd += ["-t", t6(duration)]
    cmd += ["-i", str(path), "-map", "0:v:0", "-an", "-vf", ",".join(vf), "-f", "rawvideo", "-pix_fmt", "gray", "-"]
    raw = run(cmd, binary=True).stdout
    n = len(raw) // (width * height)
    return np.frombuffer(raw[: n * width * height], dtype=np.uint8).reshape(n, height, width)


def decode_frames_rgb(path, ffmpeg, indices, width=None, height=None, matrix="bt709", in_range="tv"):
    """{index: uint8 (h, w, 3) RGB} for exact decoded frame indices, from one decode.

    Uses select by frame number with -fps_mode passthrough (no PTS pairing) and names the YUV->RGB
    matrix and range explicitly (an untagged convert would use BT.601).
    """
    import numpy as np
    idx = sorted({int(i) for i in indices if i >= 0})
    if not idx:
        return {}
    info = probe(path, ffmpeg)
    w = width or info["video"]["width"]
    h = height or info["video"]["height"]
    sel = "+".join(f"eq(n\\,{i})" for i in idx)
    vf = f"select='{sel}',scale={w}:{h}:in_color_matrix={matrix}:in_range={in_range}:flags=bicubic,format=rgb24"
    cmd = [ffmpeg, "-v", "error", "-nostdin", "-i", str(path), "-map", "0:v:0", "-an", "-vf", vf,
           "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    if len(vf) > 6000:
        script = tmp_path(Path(path).with_suffix(".select.txt"))
        Path(script).write_text(f"[0:v:0]{vf}[out]", encoding="utf-8")
        cmd = [ffmpeg, "-v", "error", "-nostdin", "-i", str(path), "-filter_complex_script", script, "-map", "[out]",
               "-an", "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    try:
        raw = run(cmd, binary=True).stdout
    finally:
        if len(vf) > 6000:
            try:
                os.remove(script)
            except OSError:
                pass
    size = w * h * 3
    got = len(raw) // size
    frames = {i: np.frombuffer(raw[k * size:(k + 1) * size], dtype=np.uint8).reshape(h, w, 3)
              for k, i in enumerate(idx[:got])}
    return frames


# ---------------------------------------------------------------- loudness

def ebur128(path, ffmpeg, start=None, duration=None, stream="a:0", true_peak=True):
    """{'I': LUFS, 'LRA': LU, 'TP': dBTP or None} of the played window (seek on the input side)."""
    cmd = [ffmpeg, "-hide_banner", "-nostdin", "-v", "info"]
    if start is not None:
        cmd += ["-ss", t6(start)]
    if duration is not None:
        cmd += ["-t", t6(duration)]
    af = "ebur128=peak=true" if true_peak else "ebur128"
    cmd += ["-i", str(path), "-map", f"0:{stream}", "-vn", "-af", af, "-f", "null", "-"]
    err = run(cmd, check=False).stderr
    summary = err.rsplit("Summary:", 1)[-1] if "Summary:" in err else err

    def last(pat):
        m = re.findall(pat, summary)
        return float(m[-1]) if m and m[-1] not in ("-inf", "inf", "nan") else None

    out = {"I": last(r"I:\s*(-?[0-9.]+|-inf) LUFS"), "LRA": last(r"LRA:\s*(-?[0-9.]+) LU"),
           "TP": last(r"Peak:\s*(-?[0-9.]+|-inf) dBFS") if true_peak else None}
    if out["I"] is None and "Summary:" not in err:
        raise ClipError("loudness_failed", f"ebur128 found no audio in {path}", hint=err.strip()[-300:])
    return out


# ---------------------------------------------------------------- files

def tmp_path(path):
    """A collision-free sibling temp name that keeps the extension (ffmpeg picks the muxer from it)."""
    p = Path(path)
    return str(p.with_name(f"{p.stem}.tmp-{os.getpid()}-{uuid.uuid4().hex[:8]}{p.suffix}"))


def replace_with_retry(src, dst):
    """os.replace with retries for Windows files held open by a viewer (10, 20 ... 640 ms)."""
    delay = 0.01
    for attempt in range(8):
        try:
            os.replace(src, dst)
            return str(dst)
        except PermissionError:
            if attempt == 7:
                raise ClipError("rename_blocked", f"cannot replace {dst} (file in use)",
                                hint="close the file in any player or explorer preview and rerun")
            time.sleep(delay)
            delay *= 2


def write_json_atomic(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = tmp_path(path)
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1, default=_json_default)
        f.write("\n")
    return replace_with_retry(tmp, path)


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise ClipError("input_missing", f"no such file: {path}", exit_code=2)
    except json.JSONDecodeError as e:
        raise ClipError("bad_json", f"{path}: {e}", exit_code=2)
