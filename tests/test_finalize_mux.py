"""Tests for skill/scripts/finalize_mux.py. Run from the repo root:
    python -P tests/test_finalize_mux.py

All media are synthetic (tests/fixtures.py plus direct ffmpeg calls) and live in a fresh temp folder that is
deleted at the end. The script runs as a subprocess through its real CLI. Every check prints one line; the
exit code is 0 only when every check passed.

Covered:
- mux mode: pad/trim/copy fits, exact audio edit (independent box read), unchanged picture, 709tv and 601tv
  tags proven by decoding a palette card, --tag none on a tagged B-frame video, a hot mix through the true-peak
  loop, a stray audio track and inherited tags dropped, a mono mix, 30 and 30000/1001 fps, a folder with a
  space and an apostrophe, an existing --out left untouched when the gate fails, and (Windows) a --out held
  open by another program.
- negative controls that must FAIL --check: -shortest from a short mix, an untagged file when 709tv is
  required, moov at the end, audio longer than video, an extra stream, a black tail, plus make_zero, a raw .aac,
  inherited metadata, the bsf without the container flags (and the reverse), hot audio, decode errors,
  over --max-dur, a wrong --fps.
- mux-mode refusals: VFR video, --frames/--fps mismatch, a non-H.264 video, a mix without audio, usage errors.
- the ffmpeg stall watchdog (a library call with the stall limit shortened).
"""
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixtures as fx  # noqa: E402  (also puts skill/scripts on sys.path)
import cliplib as cl  # noqa: E402

SCRIPT = fx.ROOT / "skill" / "scripts" / "finalize_mux.py"
FF = fx.ffmpeg()
SR = 48000
W, H = 360, 480
TAG_709 = ["-bsf:v", "h264_metadata=colour_primaries=1:transfer_characteristics=1:matrix_coefficients=1:"
           "video_full_range_flag=0", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
           "-color_range", "tv"]
# ref 01 caption palette plus grey and near-black, for the decode-by-tag checks
PALETTE = [(0x2B, 0xFF, 0x2B), (0xFF, 0x2B, 0xD6), (0xFF, 0x1A, 0x1A), (0xF5, 0xFF, 0x00), (0x40, 0xE0, 0xE0),
           (0xFF, 0xFF, 0xFF), (0x80, 0x80, 0x80), (0x10, 0x10, 0x10)]
FAILED = []


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'} {name}" + ("" if cond or not detail else f"  -- {detail}"), flush=True)
    if not cond:
        FAILED.append(name)


def run(*args):
    """Run the CLI; returns (exit code, parsed stdout JSON or None, stderr)."""
    cp = subprocess.run([sys.executable, "-P", str(SCRIPT), *[str(a) for a in args]], capture_output=True,
                        stdin=subprocess.DEVNULL)
    out, err = cp.stdout.decode("utf-8", "replace"), cp.stderr.decode("utf-8", "replace")
    try:
        doc = json.loads(out)
    except ValueError:
        doc = None
    return cp.returncode, doc, err


def failed(doc):
    return sorted(k for k, g in (doc or {}).get("gate", {}).items() if not g["ok"])


def ff(*args):
    cl.run([FF, "-v", "error", "-y", *[str(a) for a in args]])


# ---------------------------------------------------------------- media builders

def video(path, frames, fps="60", size=(W, H), vf=None, extra=()):
    """Untagged H.264 yuv420p, no B-frames (the delivery encode shape) from testsrc2."""
    w, h = size
    args = ["-f", "lavfi", "-i", f"testsrc2=s={w}x{h}:r={fps}", "-frames:v", frames]
    if vf:
        args += ["-vf", vf]
    ff(*args, "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-bf", "0", "-pix_fmt", "yuv420p",
       *extra, "-an", path)
    return path


def tone(path, samples, freq=440.0, amp=0.3, channels=2):
    t = np.arange(samples) / SR
    x = (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    cl.write_wav_f32(path, x if channels == 1 else np.stack([x, x], axis=1), SR)
    return path


def hot_noise(path, samples, seed=5):
    """White noise near full scale: AAC pushes its true peak well over -1 dBTP."""
    x = np.random.default_rng(seed).uniform(-0.98, 0.98, (samples, 2)).astype(np.float32)
    cl.write_wav_f32(path, x, SR)
    return path


def aac(wav, out, *extra):
    ff("-i", wav, *extra, "-c:a", "aac", "-b:a", "192k", "-ar", SR, out)
    return out


def mux_variant(out, vid, aud, *extra, faststart=True, tags=True, strip=True, maps=("0:v:0", "1:a:0")):
    """The rule's copy-mux with one thing changed (for the negative controls)."""
    args = ["-i", vid, "-i", aud]
    for m in maps:
        args += ["-map", m]
    args += ["-c", "copy", "-r", "60/1"]
    if strip:
        args += ["-map_metadata", "-1"]
    if tags:
        args += TAG_709
    args += list(extra)
    if faststart:
        args += ["-movflags", "+faststart"]
    ff(*args, out)
    return out


def palette_card(path, matrix, d):
    """30 frames of the palette as H.264 converted with `matrix` and then stripped of every colour tag."""
    img = np.zeros((H, W, 3), np.uint8)
    for i, c in enumerate(PALETTE):
        r, k = divmod(i, 2)
        img[r * 120:(r + 1) * 120, k * 180:(k + 1) * 180] = c
    ppm = d / f"card_{matrix}.ppm"
    ppm.write_bytes(b"P6\n%d %d\n255\n" % (W, H) + img.tobytes())
    # On ffmpeg 7.1 out_color_matrix also tags the encode (VUI matrix + range), so setparams clears the tags:
    # the card stands for a render whose tags are unknown.
    ff("-loop", "1", "-framerate", "60", "-i", ppm, "-frames:v", "30", "-vf",
       f"scale=out_color_matrix={matrix}:out_range=tv:flags=accurate_rnd+full_chroma_int,format=yuv420p,"
       "setparams=colorspace=unknown:range=unknown", "-c:v", "libx264", "-preset", "veryfast", "-crf", "4",
       "-bf", "0", path)
    return path


def palette_error(path):
    """Max code-value error over the patch centres when ffmpeg decodes the file by its own tags."""
    raw = cl.run([FF, "-v", "error", "-i", path, "-frames:v", "1", "-vf",
                  "scale=flags=accurate_rnd+full_chroma_int,format=rgb24", "-f", "rawvideo", "-pix_fmt", "rgb24",
                  "-"], binary=True).stdout
    x = np.frombuffer(raw, np.uint8).reshape(H, W, 3).astype(int)
    errs = []
    for i, c in enumerate(PALETTE):
        r, k = divmod(i, 2)
        errs.append(int(np.abs(x[r * 120 + 30:(r + 1) * 120 - 30, k * 180 + 40:(k + 1) * 180 - 40] - c).max()))
    return max(errs)


# ---------------------------------------------------------------- independent readers (not the script's code)

def edit_lists(path):
    """(movie timescale, [elst entries per track in file order]) by a plain byte search of a faststart file."""
    data = Path(path).read_bytes()
    i = data.find(b"mvhd")
    ts = struct.unpack_from(">I", data, i + 4 + (20 if data[i + 4] == 1 else 12))[0]
    out, i = [], data.find(b"elst")
    while i != -1 and len(out) < 2:
        n = struct.unpack_from(">I", data, i + 8)[0]
        fmt, step = (">Qq", 20) if data[i + 4] == 1 else (">Ii", 12)
        out.append([struct.unpack_from(fmt, data, i + 12 + k * step) for k in range(n)])
        i = data.find(b"elst", i + 4)
    return ts, out


def decoded_md5s(path):
    cp = cl.run([FF, "-v", "error", "-i", path, "-map", "0:v:0", "-f", "framemd5", "-"])
    return [ln.split(",")[-1].strip() for ln in cp.stdout.splitlines() if ln and not ln.startswith("#")]


def header(path):
    return cl.run([FF, "-hide_banner", "-nostdin", "-i", path], check=False).stderr


def vui(path):
    err = cl.run([FF, "-hide_banner", "-v", "info", "-i", path, "-map", "0:v:0", "-c", "copy", "-bsf:v",
                  "trace_headers", "-frames:v", "1", "-f", "null", "-"], check=False).stderr
    vals = {}
    for line in err.splitlines():
        parts = line.split()      # [trace_headers @ 0x..] <bit> <field> <bits> = <value>
        if len(parts) >= 4 and parts[-4] in ("colour_primaries", "transfer_characteristics", "matrix_coefficients",
                                             "video_full_range_flag") and parts[-2] == "=":
            vals.setdefault(parts[-4], parts[-1])
    return "/".join(vals.get(k, "-") for k in ("colour_primaries", "transfer_characteristics",
                                                "matrix_coefficients", "video_full_range_flag"))


# ---------------------------------------------------------------- the checks

def test_fits(d, v150):
    """Pad, trim and copy all deliver exactly 120000 samples against 150 frames at 60 fps."""
    for name, samples, fit in (("pad", 119395, "pad"), ("trim", 121099, "trim"), ("copy", 120000, "copy")):
        mix = fx.music_bed(d / f"bed_{name}.wav", dur=samples / SR)["path"]
        out = d / "edited" / f"01-{name}.mp4"
        rc, doc, err = run("--video", v150, "--mix", mix, "--out", out, "--frames", 150, "--fps", "60",
                           "--ffprobe", "none")
        ok = rc == 0 and doc and doc["ok"]
        check(f"mux {name}: exit 0, every gate ok", ok, f"rc={rc} failed={failed(doc)} {err[-300:]}")
        if not ok:
            continue
        a = doc["audio"]
        check(f"mux {name}: fit={fit}, mix {samples} -> 120000 samples",
              a["fit"] == fit and a["mix_samples"] == samples and a["samples"] == 120000, str(a))
        check(f"mux {name}: frames 150, fps 60/1, staged null, out exists",
              doc["frames"] == 150 and doc["fps"] == "60/1" and doc["staged"] is None and out.is_file())
        ts, (ve, ae) = edit_lists(out)
        check(f"mux {name}: video edit media_time 0 for 2.500 s, audio edit priming 1024 for 2.500 s",
              ve == [(ts * 5 // 2, 0)] and ae == [(ts * 5 // 2, 1024)], f"ts={ts} video={ve} audio={ae}")
    check("mux: no staged temp files left beside the outputs", not list((d / "edited").glob("*.tmp-*")))
    out = d / "edited" / "01-copy.mp4"
    if out.is_file():
        check("mux: picture unchanged by the copy-mux (decoded frame md5s equal)",
              decoded_md5s(out) == decoded_md5s(v150))
        h = header(out)
        check("mux: one video + one audio stream, yuv420p(tv, bt709)",
              h.count("Stream #") == 2 and "yuv420p(tv, bt709, progressive)" in h, h[-600:])
        rc, doc, _ = run("--check", out, "--frames", 150, "--fps", "60/1")
        check("--check on a delivered file: exit 0 and the contract's JSON keys",
              rc == 0 and doc["ok"] and {"ok", "version", "out", "frames", "fps", "audio", "gate"} <= set(doc)
              and {"samples", "tp_dbtp", "lowered_db", "passes"} <= set(doc["audio"])
              and all(set(g) == {"ok", "measured", "limit"} for g in doc["gate"].values()), str(doc)[:400])


def test_tags(d):
    card709 = palette_card(d / "card709.mp4", "bt709", d)
    card601 = palette_card(d / "card601.mp4", "bt601", d)
    mix = tone(d / "tone_30f.wav", 24000)
    e_raw = palette_error(card709)
    check("709 card without tags decodes wrong (BT.601 assumed, >= 17 off)", e_raw >= 17, f"err {e_raw}")
    out709 = d / "card709_tagged.mp4"
    rc, doc, err = run("--video", card709, "--mix", mix, "--out", out709, "--tag", "709tv")
    check("--tag 709tv: exit 0", rc == 0, f"failed={failed(doc)} {err[-300:]}")
    if rc == 0:
        e = palette_error(out709)
        check("--tag 709tv: decode by tag within 4 code values", e <= 4, f"err {e}")
        check("--tag 709tv: colr and VUI 1/1/1/0 (gate and independent trace)",
              doc["gate"]["colr"]["measured"] == "1/1/1/0" and vui(out709) == "1/1/1/0", vui(out709))
    out601 = d / "card601_tagged.mp4"
    rc, doc, err = run("--video", card601, "--mix", mix, "--out", out601, "--tag", "601tv")
    check("--tag 601tv: exit 0", rc == 0, f"failed={failed(doc)} {err[-300:]}")
    if rc == 0:
        e = palette_error(out601)
        check("--tag 601tv: decode by tag within 4 code values", e <= 4, f"err {e}")
        check("--tag 601tv: colr and VUI 1/1/6/0, container says smpte170m",
              doc["gate"]["colr"]["measured"] == "1/1/6/0" and vui(out601) == "1/1/6/0"
              and "smpte170m/bt709/bt709" in header(out601), vui(out601))


def test_passthrough_and_inputs(d):
    # A tagged B-frame video with its own 1 kHz audio and source tags; our mix is a 440 Hz tone.
    src = d / "src_av.mp4"
    k = np.arange(150 * 800) / SR
    fx.shots_video(src, [("testsrc2", 150)], fps=60, size=(W, H),
                   audio=(0.3 * np.sin(2 * np.pi * 1000 * k)).astype(np.float32))
    vid = d / "src_av_meta.mp4"
    ff("-i", src, "-map", "0", "-c", "copy", "-metadata", "title=Source title", "-metadata",
       "comment=https://example.com/watch?v=x", "-movflags", "+faststart", vid)
    out = d / "passthrough.mp4"
    rc, doc, err = run("--video", vid, "--mix", tone(d / "tone440.wav", 120000), "--out", out, "--tag", "none")
    check("--tag none on a tagged B-frame video with its own audio: exit 0", rc == 0,
          f"failed={failed(doc)} {err[-400:]}")
    if rc == 0:
        check("--tag none keeps the video's own tags (colr/VUI 1/1/1/0 reported)",
              doc["gate"]["colr"]["measured"] == "1/1/1/0" and doc["gate"]["vui"]["measured"] == "1/1/1/0")
        h = header(out)
        check("stray audio track dropped: exactly one audio stream", h.count("Audio:") == 1, h[-500:])
        check("inherited title/comment stripped", "comment" not in h and "Source title" not in h)
        x = cl.decode_audio(out, FF, channels=1)
        spec = np.abs(np.fft.rfft(x[SR // 2:SR // 2 + SR]))
        check("the delivered audio is our mix (440 Hz), not the video's (1 kHz)", abs(int(np.argmax(spec)) - 440) <= 2,
              f"peak {int(np.argmax(spec))} Hz")
        check("B-frame input: first pts 0 without an empty edit", doc["gate"]["first_pts"]["ok"])

    # mono mix: duplicated to both channels (pan, not -ac 2)
    v = video(d / "v150_mono.mp4", 150)
    out = d / "mono.mp4"
    rc, doc, err = run("--video", v, "--mix", tone(d / "mono.wav", 120000, channels=1), "--out", out)
    check("mono mix: exit 0 and 120000 samples", rc == 0 and doc["audio"]["samples"] == 120000,
          f"failed={failed(doc)} {err[-300:]}")
    if rc == 0:
        x = cl.decode_audio(out, FF, channels=2, src_channels=2)
        check("mono mix: left == right in the delivery", float(np.abs(x[:, 0] - x[:, 1]).max()) < 1e-3)

    # 30 fps and 30000/1001 fps: the audio length follows the exact rational rate
    for fps, frames, want_samples in (("30", 75, 120000), ("30000/1001", 90, 144144)):
        v = video(d / f"v_{fps.replace('/', '_')}.mp4", frames, fps=fps)
        out = d / f"fps_{fps.replace('/', '_')}.mp4"
        mix = fx.music_bed(d / f"bed_{frames}.wav", dur=2.4)["path"]
        rc, doc, err = run("--video", v, "--mix", mix, "--out", out, "--fps", fps, "--frames", frames)
        check(f"{fps} fps: exit 0, {want_samples} samples, fps {fps if '/' in fps else fps + '/1'}",
              rc == 0 and doc["audio"]["samples"] == want_samples and doc["fps"] == (fps if "/" in fps else fps + "/1"),
              f"rc={rc} failed={failed(doc)} audio={doc and doc.get('audio')} {err[-300:]}")


def test_true_peak(d, v150):
    out = d / "hot.mp4"
    rc, doc, err = run("--video", v150, "--mix", hot_noise(d / "hot.wav", 120000), "--out", out)
    check("hot mix: exit 0 after true-peak correction", rc == 0, f"failed={failed(doc)} {err[-400:]}")
    if rc == 0:
        a = doc["audio"]
        check("hot mix: pass 0 over -1 dBTP, then corrected (>= 2 passes, <= 4)",
              2 <= len(a["passes"]) <= 4 and a["passes"][0]["tp_dbtp"] > -1.0, str(a["passes"]))
        check("hot mix: final true peak <= -1.0 dBTP and lowered_db > 0",
              a["tp_dbtp"] <= -1.0 and a["lowered_db"] > 0, str(a))
        tp = cl.ebur128(out, FF)["TP"]
        check("hot mix: independent ebur128 of the delivery <= -1.0 dBTP", tp is not None and tp <= -1.0, str(tp))
    # the negative control: the same hot AAC muxed without the loop
    bad = mux_variant(d / "hot_noloop.mp4", v150, aac(d / "hot.wav", d / "hot.m4a"))
    rc, doc, _ = run("--check", bad, "--frames", 150)
    check("NEG hot AAC without the loop: --check fails true_peak only", rc == 1 and failed(doc) == ["true_peak"],
          f"rc={rc} failed={failed(doc)}")


def test_negative_controls(d, v150):
    good = aac(tone(d / "tone_2500.wav", 120000), d / "good.m4a")
    short = aac(tone(d / "tone_short.wav", 119395), d / "short.m4a")      # 2.4874 s
    long_ = aac(tone(d / "tone_long.wav", 144000), d / "long.m4a")        # 3.0 s
    ff("-i", d / "tone_2500.wav", "-c:a", "aac", "-b:a", "192k", "-f", "adts", d / "raw.aac")
    titled = d / "v150_titled.mp4"
    ff("-i", v150, "-c", "copy", "-metadata", "title=Source", "-metadata", "comment=https://example.com/watch",
       "-metadata", "description=a source description", titled)
    srt = d / "subs.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nhello\n", encoding="utf-8")
    with_subs = d / "n_subs.mp4"
    ff("-i", v150, "-i", good, "-i", srt, "-map", "0:v:0", "-map", "1:a:0", "-map", "2:s:0", "-c:v", "copy",
       "-c:a", "copy", "-c:s", "mov_text", "-map_metadata", "-1", *TAG_709, "-movflags", "+faststart", with_subs)
    cases = [
        ("-shortest from a short mix", mux_variant(d / "n_shortest.mp4", v150, short, "-shortest"),
         ["av_length", "frames"]),
        ("untagged when 709tv is required", mux_variant(d / "n_untagged.mp4", v150, good, tags=False),
         ["colr", "vui"]),
        ("moov at the end (no faststart)", mux_variant(d / "n_moov_end.mp4", v150, good, faststart=False),
         ["faststart"]),
        ("audio longer than video", mux_variant(d / "n_long.mp4", v150, long_), ["av_length"]),
        ("an extra stream (second audio track)",
         mux_variant(d / "n_extra.mp4", v150, good, maps=("0:v:0", "1:a:0", "1:a:0")), ["streams"]),
        ("an extra stream (subtitle track)", with_subs, ["streams"]),
        ("-avoid_negative_ts make_zero", mux_variant(d / "n_make_zero.mp4", v150, good, "-avoid_negative_ts",
                                                     "make_zero"), ["audio_priming", "av_length", "first_pts"]),
        ("raw .aac sidecar", mux_variant(d / "n_raw_aac.mp4", v150, d / "raw.aac"), ["audio_priming", "av_length"]),
        ("inherited source tags (no -map_metadata -1)", mux_variant(d / "n_meta.mp4", titled, good, strip=False),
         ["metadata"]),
        ("bsf without the container flags", mux_variant(d / "n_bsf_only.mp4", v150, good, *TAG_709[:2], tags=False),
         ["colr"]),
        ("container flags without the bsf", mux_variant(d / "n_flags_only.mp4", v150, good, *TAG_709[2:],
                                                        tags=False), ["vui"]),
    ]
    for name, path, want in cases:
        rc, doc, _ = run("--check", path, "--frames", 150, "--tag", "709tv")
        check(f"NEG {name}: --check exit 1, fails {want}", rc == 1 and failed(doc) == want,
              f"rc={rc} failed={failed(doc)}")
    rc, doc, _ = run("--check", d / "n_untagged.mp4", "--frames", 150)
    check("NEG untagged with the default --tag (709tv): fails colr and vui", rc == 1 and failed(doc) == ["colr", "vui"],
          f"rc={rc} failed={failed(doc)}")
    rc, doc, _ = run("--check", d / "n_untagged.mp4", "--frames", 150, "--tag", "none")
    check("untagged with --tag none: passes (tags only reported)", rc == 0, f"rc={rc} failed={failed(doc)}")

    # decode errors: overwrite bytes inside mdat of a good faststart file (moov stays intact)
    goodmux = mux_variant(d / "n_good.mp4", v150, good)
    rc, doc, _ = run("--check", goodmux, "--frames", 150)
    check("control: the same mux without a defect passes --check", rc == 0, f"failed={failed(doc)}")
    data = bytearray(goodmux.read_bytes())
    rng = np.random.default_rng(1)
    for frac in (0.35, 0.55, 0.75):
        at = int(len(data) * frac)
        data[at:at + 3000] = rng.integers(0, 256, 3000, dtype=np.uint8).tobytes()
    corrupt = d / "n_corrupt.mp4"
    corrupt.write_bytes(bytes(data))
    rc, doc, _ = run("--check", corrupt, "--frames", 150)
    check("NEG corrupted mdat: fails decode_errors", rc == 1 and "decode_errors" in failed(doc),
          f"rc={rc} failed={failed(doc)}")
    rc, doc, _ = run("--check", goodmux, "--max-dur", "2.0")
    check("NEG 2.5 s against --max-dur 2.0: fails max_dur only", rc == 1 and failed(doc) == ["max_dur"],
          f"rc={rc} failed={failed(doc)}")
    rc, doc, _ = run("--check", goodmux, "--fps", "30")
    check("NEG a 60 fps file checked with --fps 30: fails fps", rc == 1 and "fps" in failed(doc),
          f"rc={rc} failed={failed(doc)}")


def test_gate_failures_in_mux_mode(d, mix150):
    # black tail: the gate fails, --out keeps its old content, the staged file is kept and named
    black = d / "black_tail.mp4"
    fx.shots_video(black, [("testsrc2", 120), ("black", 30)], fps=60, size=(W, H))
    out = d / "edited" / "02-black.mp4"
    out.parent.mkdir(exist_ok=True)
    out.write_bytes(b"previous delivery")
    rc, doc, _ = run("--video", black, "--mix", mix150, "--out", out)
    staged = Path(doc["staged"]) if doc and doc.get("staged") else None
    check("NEG black tail (mux mode): exit 1, fails black_tail only", rc == 1 and failed(doc) == ["black_tail"],
          f"rc={rc} failed={failed(doc)}")
    check("gate failure: --out untouched, staged file kept", out.read_bytes() == b"previous delivery"
          and staged is not None and staged.is_file(), str(staged))
    if staged and staged.is_file():
        rc, doc, _ = run("--check", staged, "--frames", 150)
        check("NEG black tail (--check on the staged file): fails black_tail only",
              rc == 1 and failed(doc) == ["black_tail"], f"failed={failed(doc)}")
        staged.unlink()

    # 3600 frames at 60 fps = 60.0 s against the default 59.5 s
    v3600 = video(d / "v3600.mp4", 3600, size=(64, 48))
    mix = fx.music_bed(d / "bed_60s.wav", dur=60.0)["path"]
    out = d / "edited" / "03-long.mp4"
    rc, doc, _ = run("--video", v3600, "--mix", mix, "--out", out)
    staged = Path(doc["staged"]) if doc and doc.get("staged") else None
    check("NEG 60.0 s clip (mux mode, default --max-dur 59.5): exit 1, fails max_dur only, no out",
          rc == 1 and failed(doc) == ["max_dur"] and not out.exists() and staged is not None and staged.is_file(),
          f"rc={rc} failed={failed(doc)}")
    if staged and staged.is_file():
        staged.unlink()


def test_locked_destination(d, v150, mix150):
    """Windows: --out held open (a player) cannot be replaced; the gated file stays under its staged name."""
    if os.name != "nt":
        print("SKIP locked destination (Windows file locking only)")
        return
    out = d / "edited" / "04-locked.mp4"
    out.parent.mkdir(exist_ok=True)
    out.write_bytes(b"open in a player")
    with open(out, "rb"):
        rc, doc, _ = run("--video", v150, "--mix", mix150, "--out", out)
    staged = Path(doc["staged"]) if doc and doc.get("staged") else None
    check("locked --out: exit 1, error rename_blocked, every gate ok, gated file kept",
          rc == 1 and doc.get("error", {}).get("code") == "rename_blocked" and doc["gate"] and not failed(doc)
          and staged is not None and staged.is_file(), f"rc={rc} doc={str(doc)[:300]}")
    check("locked --out: the old file is untouched", out.read_bytes() == b"open in a player")
    if staged and staged.is_file():
        staged.unlink()


def test_refusals(d, v150, mix150):
    vfr = video(d / "vfr.mp4", 150, vf="select='not(eq(mod(n\\,7)\\,3))'", extra=("-fps_mode", "passthrough"))
    cases = [
        ("VFR video", ["--video", vfr, "--mix", mix150, "--out", d / "x1.mp4"], 1, "video_vfr"),
        ("--frames mismatch", ["--video", v150, "--mix", mix150, "--out", d / "x2.mp4", "--frames", 149], 1,
         "frames_mismatch"),
        ("--fps mismatch", ["--video", v150, "--mix", mix150, "--out", d / "x3.mp4", "--fps", "30"], 1,
         "fps_mismatch"),
        ("non-H.264 video", ["--video", video(d / "mpeg4.mp4", 30, extra=("-c:v", "mpeg4")), "--mix", mix150,
                             "--out", d / "x4.mp4"], 1, "video_format"),
        ("mix without audio", ["--video", v150, "--mix", v150, "--out", d / "x5.mp4"], 2, "mix_no_audio"),
        ("missing --mix", ["--video", v150, "--out", d / "x6.mp4"], 2, "usage"),
        ("--check with --video", ["--check", v150, "--video", v150], 2, "usage"),
        ("bad --fps", ["--check", v150, "--fps", "fast"], 2, "usage"),
        ("--out not .mp4", ["--video", v150, "--mix", mix150, "--out", d / "x7.mov"], 2, "usage"),
        ("missing video file", ["--video", d / "nope.mp4", "--mix", mix150, "--out", d / "x8.mp4"], 2,
         "input_missing"),
        ("missing --check file", ["--check", d / "nope.mp4"], 2, "input_missing"),
    ]
    for name, args, code, err_code in cases:
        rc, doc, _ = run(*args)
        got = (doc or {}).get("error", {}).get("code")
        check(f"refuse {name}: exit {code}, error {err_code}, JSON with version",
              rc == code and got == err_code and doc.get("version") == "1.0.0" and doc.get("ok") is False,
              f"rc={rc} doc={doc}")
    check("refusals wrote no output files", not any((d / f"x{i}.mp4").exists() for i in range(1, 9)))


def test_watchdog():
    """The stall guard kills an ffmpeg that stops reporting progress (library call, STALL_S shortened)."""
    import finalize_mux as fm
    saved, fm.STALL_S = fm.STALL_S, 2
    t0 = time.monotonic()
    try:
        # one frame per 1000 s, paced in real time: out_time_us stops growing after the first frame
        fm.ffmpeg_watched(FF, ["-v", "error", "-f", "lavfi", "-i", "nullsrc=s=16x16:r=1/1000,realtime=limit=100000",
                               "-f", "null", "-"], "stall test")
        code = None
    except cl.ClipError as e:
        code = e.code
    finally:
        fm.STALL_S = saved
    took = time.monotonic() - t0
    check("watchdog: an ffmpeg without progress is killed after STALL_S", code == "ffmpeg_stalled" and took < 15,
          f"code={code} took={took:.1f}s")


def main():
    d = Path(tempfile.mkdtemp(prefix="test_finalize_mux-"))
    try:
        v150 = video(d / "v150.mp4", 150)
        mix150 = tone(d / "tone150.wav", 120000)
        test_fits(d, v150)
        test_tags(d)
        test_passthrough_and_inputs(d)
        test_true_peak(d, v150)
        test_negative_controls(d, v150)
        test_gate_failures_in_mux_mode(d, mix150)
        test_locked_destination(d, v150, mix150)
        test_refusals(d, v150, mix150)
        test_watchdog()
        # a folder with a space and an apostrophe (Windows quoting, relative names)
        odd = d / "it's a dir"
        rc, doc, err = run("--video", v150, "--mix", mix150, "--out", odd / "01-odd.mp4")
        check("output folder with a space and an apostrophe: exit 0", rc == 0 and (odd / "01-odd.mp4").is_file(),
              err[-300:])
    finally:
        shutil.rmtree(d, ignore_errors=True)
    print(f"{'ALL PASSED' if not FAILED else f'{len(FAILED)} FAILED: ' + ', '.join(FAILED)}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    cl.utf8_stdio()
    sys.exit(main())
