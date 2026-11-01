"""Float audio master for one clip: dialogue chain, transcript duck lane, music bed, SFX on the hit, a unity
float sum and the final limiter, then the audio gates (ref 03 section 3; levels from ref 01 section 6).

usage:
  python -P mix_audio.py --plan clips/NN/audio_plan.json --outdir clips/NN [--ffmpeg PATH] [--ffprobe PATH|none]

input, audio_plan.json (times in output seconds, frames on the output grid):
  {"fps": "60/1", "frames": N,                    required: the clip's exact picture length
   "dialogue": "clips/NN/dialogue.wav",           required: splice.py's float stem (round(N * 48000 / fps) samples)
   "words": [[s, e], ...],                        cutlist words ({"start", "end"} objects also work); default []
   "bed": {"path": "music/bed.mp3", "offset_s": null, "lufs": -20.0, "mutes": [[s, e], ...]} | null,
   "sfx": [{"path": "sfx/hit-03.wav", "frame": F, "gain_db": 0.0}, ...],                 default []
   "duck": {"depth_db": -10, "attack_s": 0.02, "release_s": 0.3, "merge_gap_s": 0.6}}
  Missing keys take the defaults shown. bed.offset_s null picks the entry point automatically. bed.mutes are
  planned tension mutes (ref 01 section 6): the bed goes to zero there and the silence gate allows them.
  sfx gain_db is relative to the -11 dBFS SFX peak. Relative paths resolve against the current folder, then
  the plan's folder and its parents.

what it does:
  1. Dialogue: one decode to float 48 kHz stereo (mono goes to both channels at full level through pan, never
     -ac 2), a static pre-gain to -18 LUFS, the Clean Voice chain, then one static gain to -14 LUFS (skipped
     within 0.5 LU). No loudnorm and no denoising.
  2. Duck spans: the plan's words joined with speech activity on the dialogue stem, merged across gaps under
     0.6 s. The bed falls to depth_db on a 20 ms ramp that ENDS at each span start and comes back on a 300 ms
     ramp from its end; where ramps overlap the lower gain wins. Only the dialogue keys it.
  3. Bed: entry point = the earliest time whose next 5 s reach the 75th percentile of all 5 s windows' mean
     short-term loudness; looped with a 0.3 s equal-power crossfade when it is shorter than the clip; -20 LUFS
     unducked over the used window; 5 ms de-click ramps on its first and last samples; no fades.
  4. SFX: hit point = argmax of a 4 ms centred RMS every 1 ms; placed so the hit lands at (F + 1) / fps for
     accent frame F (a start before 0 trims the head); scaled to a sample peak of -11 dBFS + gain_db.
  5. Master: unity float sum in numpy (no amix), a static trim to -14 LUFS when it is more than 0.5 LU off,
     then aresample=192000,alimiter=limit=0.708:attack=5:release=50:level=0:latency=1,aresample=48000.
     If the limited master still misses -14 by more than 0.5 LU, the miss is added to the trim and the limiter
     runs once more. No gain after the limiter. Not here: the AAC encode and the true-peak-after-AAC loop
     (finalize_mux.py).

outputs in --outdir:
  mix.wav           float32 stereo 48 kHz master, exactly round(frames * 48000 / fps) samples
  mix_report.json   the JSON printed on stdout: levels, spans, SFX placements, gates, warnings, one log line
  mix_dialogue.wav, mix_bed.wav, mix_sfx.wav   float stems (the duck-margin gate measures them; kept for re-edits)

gates (an error-level failure exits 1; warn-level ones only add a warning):
  lufs (master -14 +/- 1 LU), clip (no sample with |x| >= 0.999), silence (silencedetect -50 dB / 0.1 s finds
  nothing outside a planned mute), duck_margin (dialogue minus ducked bed per span >= 9 dB; warning under
  12 dB), bed_low_share (warn: half the bed's energy or more under 150 Hz), inputs (each decodes and is not
  silent where it is used), sfx_align (each SFX peak shows in frames [F, F + 2]), sfx_reuse (no sound used
  twice: same file, same bytes or same spectral print), master_lag (the limiter path shifted nothing).

exit codes: 0 all gates pass; 1 a gate failed (files still written; the JSON names the gate and a fix hint);
  2 usage error, bad plan or unreadable input.
"""
import argparse
import hashlib
import math
import os
import re
import shutil
import sys
import tempfile
from fractions import Fraction
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cliplib as cl  # noqa: E402

SCRIPT_VERSION = "1.0.0"
# Approach adapted from HyperFrames (github.com/heygen-com/hyperframes, Apache-2.0); independent Python implementation.

SR = 48000

# Levels (ref 03 section 3 items 3, 6, 7 and 9; ref 01 section 6).
PRE_LUFS = -18.0            # static pre-gain target before Clean Voice (ours)
TARGET_LUFS = -14.0         # dialogue and master
SKIP_LU = 0.5               # a static gain within 0.5 LU of its target is skipped
LUFS_TOL = 1.0              # master gate: -14 +/- 1 LU
GAIN_WARN_DB = 12.0         # more dialogue gain than this lifts the noise floor too
SILENT_LUFS = -70.0         # ebur128's absolute gate: a window at or below it is silent; never gain-match it
BED_LUFS = -20.0            # unducked bed over the used window
SFX_PEAK_DBFS = -11.0       # SFX sample peak before the plan's gain_db
CLEAN_VOICE = ("highpass=f=80:poles=2,equalizer=f=250:t=q:w=1.2:g=-3,"
               "acompressor=threshold=0.1:ratio=3:attack=12:release=180:makeup=1.413,"
               "equalizer=f=3000:t=q:w=1:g=2.5")
# Ceiling -3 dBFS at 4x oversampling. level=0 stops ffmpeg 7.1's default re-normalising to 0 dBFS (+6 dB) and
# latency=1 removes the 5 ms lookahead delay; both were measured on 7.1 (ref 03 section 3, Limiter last).
LIMITER = "aresample=192000,alimiter=limit=0.708:attack=5:release=50:level=0:latency=1,aresample=48000"

# Duck lane (item 5).
DUCK_DEFAULTS = {"depth_db": -10.0, "attack_s": 0.02, "release_s": 0.3, "merge_gap_s": 0.6}
DUCK_RANGES = {"depth_db": (-60.0, 0.0), "attack_s": (0.0, 2.0), "release_s": (0.0, 10.0), "merge_gap_s": (0.0, 10.0)}
VAD_HOP = VAD_HALF = 2400   # levels every 50 ms over a centred 100 ms window
VAD_FLOOR_DB, VAD_BELOW_P90 = -45.0, 30.0
VAD_PAUSE_HOPS = 8          # a span ends where >= 0.4 s below the threshold starts
VAD_MIN_HOPS = 6            # spans shorter than 0.3 s are dropped

# Bed (item 6).
BED_WINDOW_S, BED_PERCENTILE, BED_STEP_S = 5.0, 0.75, 0.1
XFADE = int(0.3 * SR)       # loop crossfade (equal power)
DECLICK = int(0.005 * SR)   # 5 ms de-click ramps
TAIL_SILENCE = 10 ** (-60 / 20)

# SFX (items 7 and 8).
ENV_HOP, ENV_HALF = 48, 96  # 4 ms centred RMS every 1 ms
ONSET_RATIO, TAIL_DB, SFX_SILENT = 0.2, -40.0, 10 ** (-50 / 20)
PRINT_EDGES = 30.0 * 2.0 ** (np.arange(42) / 5.0)   # 1/5-octave band edges from 30 Hz while under 9 kHz
PRINT_S, PRINT_COS, PRINT_LEN_RATIO = 0.4, 0.95, (0.5, 2.0)
WELCH_FREQS = np.fft.rfftfreq(4096, 1.0 / SR)        # bins of the 4096-point Welch spectra (print, low share)

# Gates (item 11).
CLIP_LEVEL = 0.999
SILENCE_FILTER = "silencedetect=n=-50dB:d=0.1"
MARGIN_FAIL_DB, MARGIN_WARN_DB, MARGIN_WIN_S = 9.0, 12.0, 0.4
LOW_CUT_HZ, LOW_SHARE_WARN = 150.0, 0.5
LAG_SEARCH = 480            # +/- 10 ms

PLAN_KEYS = {"fps", "frames", "dialogue", "words", "bed", "sfx", "duck"}
BED_KEYS = {"path", "offset_s", "lufs", "mutes"}
SFX_KEYS = {"path", "frame", "gain_db"}
AAC_NOTE = ("not done here: finalize_mux.py encodes AAC once from mix.wav and runs the true-peak-after-AAC loop "
            "(ref 03 section 3, True peak after AAC); it knows the exact video length")


# ---------------------------------------------------------------- plan

def _bad(msg):
    return cl.ClipError("bad_plan", msg, hint="the audio_plan.json keys are listed in the mix_audio.py docstring",
                        exit_code=2)


def _number(v, what, lo=None, hi=None):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise _bad(f"{what} must be a number, got {v!r}")
    if (lo is not None and v < lo) or (hi is not None and v > hi):
        raise _bad(f"{what} = {v} is outside [{lo}, {hi}]")
    return float(v)


def _int(v, what, lo, hi):
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
        raise _bad(f"{what} must be an integer in [{lo}, {hi}], got {v!r}")
    return v


def _resolve(value, plan_dir, what):
    if not isinstance(value, str) or not value.strip():
        raise _bad(f"{what} needs a file path, got {value!r}")
    p = Path(value)
    candidates = [p] if p.is_absolute() else [Path.cwd() / p, plan_dir / p] + [d / p for d in plan_dir.parents]
    for c in candidates:
        if c.is_file():
            return c.resolve()
    raise cl.ClipError("input_missing", f"{what} not found: {value}",
                       hint="relative paths resolve against the current folder, then the plan's folder and its parents",
                       exit_code=2)


def _spans(value, what, clip_s, warnings):
    """[[s, e], ...] or [{"start", "end"}, ...] -> sorted (s, e) in seconds, rounded to 1 ms, inside the clip."""
    if value is None:
        return []
    if not isinstance(value, list):
        raise _bad(f"{what} must be a list of [start, end] pairs")
    out, dropped = [], 0
    for i, item in enumerate(value):
        if isinstance(item, dict):
            s, e = item.get("start"), item.get("end")
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            s, e = item
        else:
            raise _bad(f"{what}[{i}] must be [start, end], got {item!r}")
        s, e = _number(s, f"{what}[{i}] start"), _number(e, f"{what}[{i}] end")
        s, e = round(max(s, 0.0), 3), round(min(e, clip_s), 3)
        if e <= s:  # zero-length, reversed or outside the clip
            dropped += 1
            continue
        out.append((s, e))
    if dropped:
        warnings.append(f"spans_dropped: {dropped} {what} entries are empty or outside the clip")
    return sorted(out)


def load_plan(path, warnings):
    plan = cl.read_json(path)
    if not isinstance(plan, dict):
        raise _bad("the plan must be a JSON object")
    for k in sorted(set(plan) - PLAN_KEYS):
        warnings.append(f"plan_unknown_key: {k} (ignored)")
    try:
        fps = cl.parse_rate(plan.get("fps"))
    except (ValueError, ZeroDivisionError):
        fps = None
    if not fps or fps <= 0:
        raise _bad(f"fps must be a frame rate such as \"60/1\", got {plan.get('fps')!r}")
    frames = _int(plan.get("frames"), "frames", 1, 10 ** 7)
    clip_s = float(frames / fps)
    plan_dir = Path(path).resolve().parent
    cfg = {"fps": fps, "frames": frames, "clip_s": clip_s,
           "dialogue": _resolve(plan.get("dialogue"), plan_dir, "dialogue"),
           "words": _spans(plan.get("words"), "words", clip_s, warnings)}

    duck = plan.get("duck") or {}
    if not isinstance(duck, dict):
        raise _bad("duck must be an object")
    cfg["duck"] = dict(DUCK_DEFAULTS)
    for k, v in duck.items():
        if k not in DUCK_DEFAULTS:
            warnings.append(f"plan_unknown_key: duck.{k} (ignored)")
        elif v is not None:
            cfg["duck"][k] = _number(v, f"duck.{k}", *DUCK_RANGES[k])

    bed = plan.get("bed")
    if bed is not None:
        if not isinstance(bed, dict):
            raise _bad("bed must be an object or null")
        for k in sorted(set(bed) - BED_KEYS):
            warnings.append(f"plan_unknown_key: bed.{k} (ignored)")
        bed = {"path": _resolve(bed.get("path"), plan_dir, "bed.path"),
               "offset_s": None if bed.get("offset_s") is None else _number(bed["offset_s"], "bed.offset_s", 0.0),
               "lufs": BED_LUFS if bed.get("lufs") is None else _number(bed["lufs"], "bed.lufs", -60.0, 0.0),
               "mutes": _spans(bed.get("mutes"), "bed.mutes", clip_s, warnings)}
    cfg["bed"] = bed

    sfx = plan.get("sfx") or []
    if not isinstance(sfx, list):
        raise _bad("sfx must be a list")
    cfg["sfx"] = []
    for i, it in enumerate(sfx):
        if not isinstance(it, dict):
            raise _bad(f"sfx[{i}] must be an object with path and frame")
        for k in sorted(set(it) - SFX_KEYS):
            warnings.append(f"plan_unknown_key: sfx[{i}].{k} (ignored)")
        cfg["sfx"].append({"path": _resolve(it.get("path"), plan_dir, f"sfx[{i}].path"),
                           "frame": _int(it.get("frame"), f"sfx[{i}].frame", 0, frames - 1),
                           "gain_db": 0.0 if it.get("gain_db") is None
                           else _number(it["gain_db"], f"sfx[{i}].gain_db", -40.0, 20.0)})
    return cfg


# ---------------------------------------------------------------- ffmpeg I/O

def probe_audio(path, ffmpeg, ffprobe, what):
    info = cl.probe(path, ffmpeg, ffprobe)  # exit 2 when the file is unreadable
    if not info.get("audio"):
        raise cl.ClipError("no_audio", f"{what} has no audio stream: {path}",
                           hint="point the plan at a file with an audio track", exit_code=2)
    return info


def decode_stereo(path, ffmpeg, channels, start=None, duration=None):
    """(float32 (n, 2) at 48 kHz, ffmpeg error text). Seeks are input-side, so the window read is the window played.

    Mono reaches both channels at full level: `pan=stereo|FL=FL+FC|FR=FR+FC` passes stereo through unchanged and
    copies a mono FC to FL and FR (`-ac 2` would cost 3.01 dB). More than 2 channels take the standard downmix.
    """
    up = "aformat=channel_layouts=stereo" if channels and channels > 2 else "pan=stereo|FL=FL+FC|FR=FR+FC"
    cmd = [ffmpeg, "-v", "error", "-nostdin"]
    if start is not None:
        cmd += ["-ss", cl.t6(start)]
    if duration is not None:
        cmd += ["-t", cl.t6(duration)]
    cmd += ["-i", str(path), "-map", "0:a:0", "-vn", "-af", f"{up},aresample={SR}",
            "-f", "f32le", "-c:a", "pcm_f32le", "-"]
    cp = cl.run(cmd, binary=True, check=False)
    if cp.returncode != 0:
        raise cl.ClipError("unreadable_input", f"cannot decode {path}", hint=cp.stderr.strip()[-400:] or None,
                           exit_code=2)
    return _stereo(cp.stdout), cp.stderr.strip()


def ff_filter(ffmpeg, src, af):
    """Run a filter chain over a float WAV and return float32 (n, 2); every intermediate stays float."""
    cp = cl.run([ffmpeg, "-v", "error", "-nostdin", "-i", str(src), "-map", "0:a:0", "-af", af,
                 "-f", "f32le", "-c:a", "pcm_f32le", "-"], binary=True)
    return _stereo(cp.stdout)


def _stereo(raw):
    x = np.frombuffer(raw, dtype="<f4")
    return x[: len(x) // 2 * 2].reshape(-1, 2).copy()


def lufs_of(x, tmp, name, ffmpeg, true_peak=False):
    """ebur128 summary of an in-memory signal (written as a float WAV first)."""
    p = tmp / f"{name}.wav"
    cl.write_wav_f32(p, x, SR)
    return cl.ebur128(p, ffmpeg, true_peak=true_peak)


def silent_lufs(i):
    return i is None or i <= SILENT_LUFS


def fit(x, n):
    """Pad with zeros or cut to exactly n samples (the picture is the clock)."""
    if len(x) >= n:
        return x[:n]
    return np.concatenate([x, np.zeros((n - len(x), x.shape[1]), x.dtype)])


def find_silences(path, ffmpeg, clip_s):
    cp = cl.run([ffmpeg, "-hide_banner", "-nostdin", "-i", str(path), "-map", "0:a:0", "-af", SILENCE_FILTER,
                 "-f", "null", "-"])
    starts = [float(v) for v in re.findall(r"silence_start:\s*(-?[0-9.]+)", cp.stderr)]
    ends = [float(v) for v in re.findall(r"silence_end:\s*(-?[0-9.]+)", cp.stderr)]
    return [(round(s, 3), round(ends[i] if i < len(ends) else clip_s, 3)) for i, s in enumerate(starts)]


# ---------------------------------------------------------------- signal helpers

def window_power(x, hop, half):
    """Mean power over +/- half samples around sample j * hop, for every j. Energy is the mean over channels of
    x^2, so a phase-flipped channel still counts; windows are cut at the edges and averaged over what is left."""
    e = (x.astype(np.float64) ** 2).mean(axis=1)
    cs = np.concatenate([[0.0], np.cumsum(e)])
    centers = np.arange(0, len(e), hop)
    a = np.clip(centers - half, 0, len(e))
    b = np.clip(centers + half, 0, len(e))
    return np.maximum(cs[b] - cs[a], 0.0) / np.maximum(b - a, 1)


def rms_env(x):
    """RMS over a centred 4 ms window every 1 ms (frame j is centred on sample j * 48)."""
    return np.sqrt(window_power(x, ENV_HOP, ENV_HALF))


def moments(env):
    """(onset, peak, tail) envelope frames: peak = argmax, onset = first >= 0.2 x peak, tail = last >= peak - 40 dB."""
    pk = int(np.argmax(env))
    onset = int(np.argmax(env >= ONSET_RATIO * env[pk]))
    after = np.nonzero(env[pk + 1:] >= env[pk] * 10 ** (TAIL_DB / 20))[0]
    tail = pk + 1 + int(after[-1]) if len(after) else pk
    return onset, pk, tail


def welch_power(mono, nfft=4096, hop=2048):
    """Mean Hann-windowed power spectrum (Welch); shorter input is zero-padded to one window."""
    if len(mono) < nfft:
        mono = np.pad(mono, (0, nfft - len(mono)))
    frames = np.lib.stride_tricks.sliding_window_view(mono, nfft)[::hop]
    win = np.hanning(nfft)
    acc = np.zeros(nfft // 2 + 1)
    for i in range(0, len(frames), 256):
        acc += (np.abs(np.fft.rfft(frames[i:i + 256] * win, axis=1)) ** 2).sum(axis=0)
    return acc / len(frames)


def low_share(x):
    """Share of the energy between 20 and 150 Hz in everything above 20 Hz (phone speakers drop the low part)."""
    p, f = welch_power(x.mean(axis=1).astype(np.float64)), WELCH_FREQS
    total = p[f >= 20].sum()
    return float(p[(f >= 20) & (f < LOW_CUT_HZ)].sum() / total) if total > 0 else 0.0


def spectral_print(x, onset):
    """sqrt of each octave's energy share (1/5-octave bands 30 Hz - 9 kHz, summed by 5) over 0.4 s from the onset.

    A level change or a mono copy gives the same print, so a re-levelled duplicate still matches.
    """
    p, f = welch_power(x.mean(axis=1).astype(np.float64)[onset:onset + int(PRINT_S * SR)]), WELCH_FREQS
    bands = np.array([p[(f >= lo) & (f < hi)].sum() for lo, hi in zip(PRINT_EDGES[:-1], PRINT_EDGES[1:])])
    octaves = np.add.reduceat(bands, np.arange(0, len(bands), 5))  # 9 values; the last holds one band
    total = octaves.sum()
    return None if total <= 0 else [round(float(v), 4) for v in np.sqrt(octaves / total)]


def ramp(x, at_start):
    """Linear de-click ramp over DECLICK samples on the first (or last) samples, in place."""
    k = min(DECLICK, len(x))
    r = np.linspace(0.0, 1.0, k, dtype=np.float32)[:, None]
    if at_start:
        x[:k] *= r
    else:
        x[len(x) - k:] *= r[::-1]


def frame_at(t, fps):
    """The output frame showing time t (ref 03 section 2, Frame grid)."""
    return int(math.floor((t + 0.0005) * fps + 1e-6))


# ---------------------------------------------------------------- dialogue

def process_dialogue(cfg, n, ffmpeg, ffprobe, tmp, warnings):
    path = cfg["dialogue"]
    info = probe_audio(path, ffmpeg, ffprobe, "dialogue")
    codec = info["audio"].get("codec") or ""
    if not codec.startswith("pcm_f"):
        warnings.append(f"dialogue_not_float: {codec}; intermediates stay pcm_f32le until the AAC (ref 03 section 3)")
    x, err = decode_stereo(path, ffmpeg, info["audio"].get("channels"))
    per_frame = SR / float(cfg["fps"])
    if abs(len(x) - n) > per_frame:
        raise cl.ClipError("length_mismatch", f"dialogue has {len(x)} samples; {cfg['frames']} frames at "
                           f"{cl.frac_str(cfg['fps'])} need {n}",
                           hint="plan.frames and plan.fps must match the cutlist that made the dialogue stem",
                           exit_code=2)
    if len(x) != n:
        warnings.append(f"dialogue_length: {len(x)} samples fitted to {n} (under one frame off)")
    x = fit(x, n)
    row = {"what": "dialogue", "path": path.as_posix(), "codec": codec, "channels": info["audio"].get("channels"),
           "silent": False, "decode_errors": err or None}
    rep = {"path": path.as_posix(), "lufs_in": None, "pre_gain_db": 0.0, "chain": None, "lufs_chain": None,
           "gain_db": 0.0, "total_gain_db": 0.0, "lufs": None}
    i0 = lufs_of(x, tmp, "dialogue_in", ffmpeg)["I"]
    rep["lufs_in"] = i0
    if silent_lufs(i0):
        row["silent"] = True
        return x, rep, row
    pre = round(PRE_LUFS - i0, 2)
    chain = f"volume={pre:.2f}dB,{CLEAN_VOICE}"
    y = fit(ff_filter(ffmpeg, tmp / "dialogue_in.wav", chain), n)
    i1 = lufs_of(y, tmp, "dialogue_chain", ffmpeg)["I"]
    gain = round(TARGET_LUFS - i1, 2) if not silent_lufs(i1) and abs(i1 - TARGET_LUFS) > SKIP_LU else 0.0
    y *= np.float32(10 ** (gain / 20))
    total = round(pre + gain, 2)
    if total > GAIN_WARN_DB:
        warnings.append(f"dialogue_gain_high: +{total:.1f} dB total lifts the noise floor too (no denoising is done)")
    rep.update(pre_gain_db=pre, chain=chain, lufs_chain=i1, gain_db=gain, total_gain_db=total,
               lufs=None if silent_lufs(i1) else round(i1 + gain, 2))
    cl.log(f"mix_audio: dialogue {i0} LUFS, pre-gain {pre:+.2f} dB, Clean Voice, gain {gain:+.2f} dB")
    return y, rep, row


# ---------------------------------------------------------------- duck spans and lane

def speech_activity(x):
    """Voice spans on the dialogue stem: levels of a centred 100 ms window every 50 ms against
    max(-45, p90 - 30) dB; a span ends where >= 0.4 s below it starts; spans under 0.3 s are dropped."""
    power = window_power(x, VAD_HOP, VAD_HALF)
    db = np.full(len(power), -120.0)
    db[power > 0] = np.maximum(-120.0, 10 * np.log10(power[power > 0]))
    thr = max(VAD_FLOOR_DB, float(np.sort(db)[int(0.9 * (len(db) - 1))]) - VAD_BELOW_P90)
    hops, start, quiet = [], None, None
    for f, level in enumerate(db):
        if level >= thr:
            start = f if start is None else start
            quiet = None
        elif start is not None:
            quiet = f if quiet is None else quiet
            if f - quiet >= VAD_PAUSE_HOPS:
                if quiet - start >= VAD_MIN_HOPS:
                    hops.append((start, quiet))
                start = quiet = None
    if start is not None:
        end = quiet if quiet is not None else len(db)
        if end - start >= VAD_MIN_HOPS:
            hops.append((start, end))
    hop_s, clip_s = VAD_HOP / SR, len(x) / SR
    return [(round(s * hop_s, 3), round(min(t * hop_s, clip_s), 3)) for s, t in hops], round(thr, 1)


def merge_spans(spans, gap):
    """Join spans that overlap or sit closer than `gap` seconds (short pauses stay ducked)."""
    out = []
    for s, e in sorted(spans):
        if out and s - out[-1][1] < gap:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return [(round(s, 3), round(e, 3)) for s, e in out]


def duck_lane(n, spans, mutes, depth_db, attack_s, release_s):
    """Per-sample bed gain. The down-ramp ENDS at each span start (pre-rolled: the bed is already down for the
    first syllable), the up-ramp starts at its end, overlaps take the minimum, and mutes go to zero."""
    lane = np.ones(n, np.float32)
    depth = 10 ** (depth_db / 20)
    attack_s, release_s = max(attack_s, 1.0 / SR), max(release_s, 1.0 / SR)
    for (s, e), floor in [(sp, depth) for sp in spans] + [(m, 0.0) for m in mutes]:
        a, b = s - attack_s, e + release_s
        i0, i1 = max(0, int(math.floor(a * SR))), min(n, int(math.ceil(b * SR)) + 1)
        if i1 <= i0:
            continue
        shape = np.interp(np.arange(i0, i1) / SR, [a, s, e, b], [1.0, 0.0, 0.0, 1.0])
        lane[i0:i1] = np.minimum(lane[i0:i1], floor + (1.0 - floor) * shape)
    return lane


# ---------------------------------------------------------------- bed

_S_LINE = re.compile(r"\bt:\s*([0-9.]+)\s.*?\bS:\s*(-?[0-9.]+|-inf)")


def auto_offset(path, ffmpeg):
    """Earliest bed time whose next 5 s reach the 75th percentile of all 5 s windows' mean short-term loudness.

    ebur128 logs S (the 3 s short-term loudness ending at t) every 0.1 s, but only at framelog=info; the window
    starting at o is scored by the S values with o + 3 < t <= o + 5, which together cover o .. o + 5.
    """
    cp = cl.run([ffmpeg, "-hide_banner", "-nostdin", "-i", str(path), "-map", "0:a:0", "-vn",
                 "-af", "ebur128=framelog=info", "-f", "null", "-"], check=False)
    rows = [m.groups() for m in map(_S_LINE.search, cp.stderr.splitlines()) if m]
    if cp.returncode != 0 or not rows:
        raise cl.ClipError("unreadable_input", f"ebur128 cannot read the bed {path}",
                           hint=cp.stderr.strip()[-400:] or None, exit_code=2)
    t = np.array([float(a) for a, _ in rows])
    s = np.array([-120.7 if b == "-inf" else float(b) for _, b in rows])
    cands = np.arange(0.0, t[-1] - BED_WINDOW_S + 1e-6, BED_STEP_S)
    lo = np.searchsorted(t, cands + 3.0 + 1e-6, side="right")
    hi = np.searchsorted(t, cands + BED_WINDOW_S + 1e-6, side="right")
    cands, lo, hi = cands[hi > lo], lo[hi > lo], hi[hi > lo]
    if not len(cands):  # under 5 s of bed: start at the top
        return 0.0
    cs = np.concatenate([[0.0], np.cumsum(s)])
    # S is logged to 0.1 LU, so a mean of k values is exact at 1e-4; rounding removes the cumsum drift that
    # otherwise decides "reach" on a steady bed (an 8.3 s quiet intro gave 14.1 s instead of 8.2 s).
    score = np.round((cs[hi] - cs[lo]) / (hi - lo), 4)
    p75 = np.sort(score)[int(BED_PERCENTILE * (len(score) - 1))]
    return round(float(cands[np.argmax(score >= p75)]), 3)


def loop_cover(seed, n):
    """Repeat `seed` to n samples with a 0.3 s equal-power cos/sin crossfade at every seam -> (bed, loops)."""
    end = np.nonzero(np.abs(seed).max(axis=1) > TAIL_SILENCE)[0]
    if len(end):  # a silent tail would leave a hole at every seam
        seed = seed[: end[-1] + 1]
    xf = min(XFADE, len(seed) // 2)
    if xf < 1:
        reps = -(-n // len(seed))
        return np.tile(seed, (reps, 1))[:n], reps - 1
    u = np.linspace(0.0, 1.0, xf, dtype=np.float32)[:, None]
    seam = seed[-xf:] * np.cos(u * np.pi / 2) + seed[:xf] * np.sin(u * np.pi / 2)
    loops = -(-(n - len(seed)) // (len(seed) - xf))
    pieces = [seed[:-xf]] + [seam, seed[xf:-xf]] * loops + [seed[-xf:]]
    return np.concatenate(pieces)[:n], loops


def process_bed(cfg, n, spans, ffmpeg, ffprobe, tmp, warnings):
    bed_cfg, duck = cfg["bed"], cfg["duck"]
    path = bed_cfg["path"]
    info = probe_audio(path, ffmpeg, ffprobe, "bed")
    auto = bed_cfg["offset_s"] is None
    offset = auto_offset(path, ffmpeg) if auto else bed_cfg["offset_s"]
    # Decode only what the clip needs; a shorter result is the whole rest of the file, which then loops.
    seed, err = decode_stereo(path, ffmpeg, info["audio"].get("channels"), start=offset,
                              duration=cfg["clip_s"] + 1.0)
    if not len(seed):
        raise cl.ClipError("bed_empty", f"the bed has no audio after {offset:.3f} s: {path}",
                           hint="set bed.offset_s inside the file, or null for the automatic entry point", exit_code=2)
    if len(seed) >= n:
        bed, loops = seed[:n].copy(), 0
    else:
        bed, loops = loop_cover(seed, n)
    i_in = lufs_of(bed, tmp, "bed_used", ffmpeg)["I"]
    silent = silent_lufs(i_in)
    gain = 0.0 if silent else round(bed_cfg["lufs"] - i_in, 2)
    bed *= np.float32(10 ** (gain / 20))
    ramp(bed, True)
    ramp(bed, False)
    share = low_share(bed)
    lane = duck_lane(n, spans, bed_cfg["mutes"], duck["depth_db"], duck["attack_s"], duck["release_s"])
    rep = {"path": path.as_posix(), "offset_s": offset, "offset_auto": auto, "loops": loops, "lufs_in": i_in,
           "gain_db": gain, "lufs": None if silent else bed_cfg["lufs"], "low_share": round(share, 3),
           "mutes": [list(m) for m in bed_cfg["mutes"]]}
    row = {"what": "bed", "path": path.as_posix(), "codec": info["audio"].get("codec"),
           "channels": info["audio"].get("channels"), "silent": silent, "decode_errors": err or None}
    cl.log(f"mix_audio: bed offset {offset:.1f} s ({'auto' if auto else 'plan'}), loops {loops}, "
           f"{i_in} LUFS, gain {gain:+.2f} dB, low share {share:.2f}")
    return bed * lane[:, None], rep, row


# ---------------------------------------------------------------- SFX

def _md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def process_sfx(cfg, n, ffmpeg, ffprobe):
    """Place every SFX so its hit lands at (F + 1)/fps, then re-measure each placed copy on the clip's own 1 ms grid.

    Rule (ref 03 section 3, SFX on the hit) says "the SFX stem's peak lies in [F, F + 2]". The QC measures each
    SFX's own placed signal, not the summed bus: on the bus a louder neighbour (a boom's decay into a hit, a riser
    into its hit) owns the argmax of the other's window and fails a correctly placed sound.
    """
    fps = cfg["fps"]
    bus = np.zeros((n, 2), np.float32)
    rows, inputs = [], []
    for i, it in enumerate(cfg["sfx"]):
        path, frame = it["path"], it["frame"]
        info = probe_audio(path, ffmpeg, ffprobe, f"sfx[{i}]")
        x, err = decode_stereo(path, ffmpeg, info["audio"].get("channels"))
        if not len(x):
            raise cl.ClipError("unreadable_input", f"sfx[{i}] decodes to no samples: {path}", exit_code=2)
        env = rms_env(x)
        silent = float(env.max()) < SFX_SILENT
        inputs.append({"what": f"sfx[{i}]", "path": path.as_posix(), "codec": info["audio"].get("codec"),
                       "channels": info["audio"].get("channels"), "silent": silent, "decode_errors": err or None})
        row = {"i": i, "path": path.as_posix(), "frame": frame, "gain_db": it["gain_db"], "md5": _md5(path),
               "silent": silent, "length_s": None, "print": None, "aligned": False}
        rows.append(row)
        if silent:
            continue
        onset, pk, tail = moments(env)
        file_peak = float(np.abs(x).max())
        applied = round(SFX_PEAK_DBFS + it["gain_db"] - 20 * math.log10(file_peak), 2)
        target = round(Fraction(frame + 1) * SR / fps)  # the hit lands at (F + 1)/fps: late reads better than early
        i0 = target - pk * ENV_HOP
        y = x * np.float32(10 ** (applied / 20))
        head = max(0, -i0)
        start = max(0, i0)
        y = y[head:]
        end = min(n, start + len(y))
        tail_cut = start + len(y) > n
        y = y[: end - start]
        if head:
            ramp(y, True)  # the head was cut mid-sound
        if tail_cut:
            ramp(y, False)  # the clip ends mid-sound
        bus[start:end] += y
        peak_cut = target >= n  # F is the last frame: the hit would land after the clip ends
        t_pk = k = None
        if end > start:  # alignment QC on this sound alone, on the clip's 1 ms envelope grid
            g0 = start - start % ENV_HOP
            placed = np.zeros((end - g0, 2), np.float32)
            placed[start - g0:] = y
            t_pk = (g0 + int(np.argmax(rms_env(placed))) * ENV_HOP) / SR
            k = frame_at(t_pk, fps)
        row.update({"file_peak_dbfs": round(20 * math.log10(file_peak), 2), "applied_gain_db": applied,
                    "onset_s": round(onset * ENV_HOP / SR, 4), "peak_s": round(pk * ENV_HOP / SR, 4),
                    "tail_s": round(tail * ENV_HOP / SR, 4), "length_s": round((tail - onset) * ENV_HOP / SR, 4),
                    "start_s": round(i0 / SR, 6), "head_trimmed_s": round(head / SR, 6), "tail_cut": tail_cut,
                    "peak_t": None if t_pk is None else round(t_pk, 6), "peak_frame": k,
                    "peak_offset_frames": None if t_pk is None else round(t_pk * float(fps) - frame, 3),
                    "peak_cut": peak_cut, "aligned": k is not None and not peak_cut and frame <= k <= frame + 2,
                    "print": spectral_print(x, onset * ENV_HOP)})
    return bus, rows, inputs


def find_reuse(rows):
    """Pairs of SFX that are the same sound: same file, same bytes, or print cosine >= 0.95 at a length ratio 0.5-2."""
    pairs = []
    for j in range(len(rows)):
        for i in range(j):
            a, b = rows[i], rows[j]
            why, cos = None, None
            if os.path.normcase(a["path"]) == os.path.normcase(b["path"]):
                why = "same_file"
            elif a["md5"] == b["md5"]:
                why = "same_bytes"
            elif a["print"] and b["print"]:
                pa, pb = np.array(a["print"]), np.array(b["print"])
                cos = float(pa @ pb / (np.linalg.norm(pa) * np.linalg.norm(pb)))
                ratio = max(a["length_s"], 0.001) / max(b["length_s"], 0.001)
                if cos >= PRINT_COS and PRINT_LEN_RATIO[0] <= ratio <= PRINT_LEN_RATIO[1]:
                    why = "same_sound"
            if why:
                pairs.append({"a": i, "b": j, "why": why, "cos": None if cos is None else round(cos, 4)})
    return pairs


# ---------------------------------------------------------------- master and gates

def master_lag(ref, out):
    """Samples by which `out` trails `ref` over their loudest 2.7 s (0 = the limiter path shifted nothing)."""
    a = ref.mean(axis=1).astype(np.float64)
    b = out.mean(axis=1).astype(np.float64)
    w = min(len(a), 1 << 17)
    if w <= 2 * LAG_SEARCH:
        return 0
    cs = np.concatenate([[0.0], np.cumsum(a * a)])
    starts = np.arange(0, len(a) - w + 1, max(1, w // 2))
    s0 = int(starts[np.argmax(cs[starts + w] - cs[starts])])
    c = np.fft.irfft(np.fft.rfft(b[s0:s0 + w], 2 * w) * np.conj(np.fft.rfft(a[s0:s0 + w], 2 * w)), 2 * w)
    lags = np.r_[0:LAG_SEARCH + 1, -LAG_SEARCH:0]
    return int(lags[np.argmax(np.r_[c[:LAG_SEARCH + 1], c[-LAG_SEARCH:]])])


def duck_margins(spans, clip_s, dlg_path, bed_path, ffmpeg):
    """LUFS(dialogue) - LUFS(ducked bed) per span; spans under 0.4 s are widened around their centre
    (shorter ebur128 windows read -70)."""
    out = []
    for s, e in spans:
        a, b = s, e
        if b - a < MARGIN_WIN_S:
            a = max(0.0, min((s + e) / 2 - MARGIN_WIN_S / 2, clip_s - MARGIN_WIN_S))
            b = min(clip_s, a + MARGIN_WIN_S)
        d = cl.ebur128(dlg_path, ffmpeg, start=a, duration=b - a, true_peak=False)["I"]
        m = cl.ebur128(bed_path, ffmpeg, start=a, duration=b - a, true_peak=False)["I"]
        margin = None if silent_lufs(d) or silent_lufs(m) else round(d - m, 2)
        out.append({"s": s, "e": e, "window": [round(a, 6), round(b, 6)], "dialogue_lufs": d, "bed_lufs": m,
                    "margin_db": margin})
    return out


def gate(gates, name, ok, measured, limit, level="error"):
    gates[name] = {"ok": bool(ok), "measured": measured, "limit": limit, "level": level}


# ---------------------------------------------------------------- main

class _Parser(argparse.ArgumentParser):
    def error(self, message):  # keep the one-JSON-object stdout contract on usage errors
        raise cl.ClipError("usage", message, hint=self.format_usage().strip(), exit_code=2)


def main() -> int:
    ap = _Parser(description="Float audio master for one clip (ref 03 section 3).")
    ap.add_argument("--plan", required=True, help="audio_plan.json")
    ap.add_argument("--outdir", required=True, help="folder for mix.wav, mix_report.json and the stems")
    ap.add_argument("--ffmpeg", help="ffmpeg binary (default: PATH, then imageio-ffmpeg)")
    ap.add_argument("--ffprobe", help="ffprobe binary, or 'none' for the ffmpeg-only probe")
    args = ap.parse_args()
    ffmpeg = cl.find_ffmpeg(args.ffmpeg)
    ffprobe = cl.find_ffprobe(ffmpeg, args.ffprobe)
    warnings = []
    cfg = load_plan(args.plan, warnings)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="mix_audio-"))
    try:
        report = mix(cfg, args.plan, outdir, ffmpeg, ffprobe, tmp, warnings)
    finally:
        try:
            shutil.rmtree(tmp)
        except OSError as e:
            cl.log(f"mix_audio: could not remove the temp folder {tmp}: {e}")
    cl.write_json_atomic(outdir / "mix_report.json", report)
    cl.emit(report)
    cl.log(report["log"] + ("" if report["ok"] else "  FAILED: " + ", ".join(report["failed"])))
    return 0 if report["ok"] else 1


def mix(cfg, plan_path, outdir, ffmpeg, ffprobe, tmp, warnings):
    fps, frames, clip_s, duck = cfg["fps"], cfg["frames"], cfg["clip_s"], cfg["duck"]
    n = round(Fraction(frames) * SR / fps)
    files = {"mix": "mix.wav", "report": "mix_report.json",
             "stems": {"dialogue": "mix_dialogue.wav", "bed": None, "sfx": None}}

    dlg, dlg_rep, dlg_row = process_dialogue(cfg, n, ffmpeg, ffprobe, tmp, warnings)
    inputs = [dlg_row]
    vad, vad_thr = speech_activity(dlg)
    spans = merge_spans(cfg["words"] + vad, duck["merge_gap_s"])
    cl.write_wav_f32(outdir / files["stems"]["dialogue"], dlg, SR)
    total = dlg.copy()

    bed_rep = None
    if cfg["bed"]:
        bed, bed_rep, bed_row = process_bed(cfg, n, spans, ffmpeg, ffprobe, tmp, warnings)
        inputs.append(bed_row)
        files["stems"]["bed"] = "mix_bed.wav"
        cl.write_wav_f32(outdir / files["stems"]["bed"], bed, SR)
        total += bed

    sfx_rows, reuse = [], []
    if cfg["sfx"]:
        bus, sfx_rows, sfx_inputs = process_sfx(cfg, n, ffmpeg, ffprobe)
        inputs += sfx_inputs
        reuse = find_reuse(sfx_rows)
        files["stems"]["sfx"] = "mix_sfx.wav"
        cl.write_wav_f32(outdir / files["stems"]["sfx"], bus, SR)
        total += bus

    # Master: unity float sum, a static trim, the limiter last, nothing after it.
    i_sum = lufs_of(total, tmp, "sum", ffmpeg)["I"]
    trim = round(TARGET_LUFS - i_sum, 2) if not silent_lufs(i_sum) and abs(i_sum - TARGET_LUFS) > SKIP_LU else 0.0
    mix_path = outdir / files["mix"]
    passes = []
    for attempt in range(2):
        pre = total * np.float32(10 ** (trim / 20))
        cl.write_wav_f32(tmp / "premaster.wav", pre, SR)
        limited = ff_filter(ffmpeg, tmp / "premaster.wav", LIMITER)
        master = fit(limited, n)
        cl.write_wav_f32(mix_path, master, SR)
        meas = cl.ebur128(mix_path, ffmpeg, true_peak=True)
        passes.append({"trim_db": trim, "lufs": meas["I"]})
        if attempt or silent_lufs(meas["I"]) or abs(meas["I"] - TARGET_LUFS) <= SKIP_LU:
            break
        # Rule problem (ref 03 section 3, Limiter last): a trim measured on the float sum ignores what the limiter
        # itself takes (0.3-0.8 LU on dense speech peaks here). A sum inside the 0.5 LU skip came out of the
        # limiter at -15.0 LUFS, the edge of the +/-1 LU gate. One corrective pass moves the miss into the
        # pre-limiter trim; the limiter stays last and nothing is gained after it.
        trim = round(trim + TARGET_LUFS - meas["I"], 2)
    if len(limited) != n:
        warnings.append(f"limiter_length: the limiter returned {len(limited)} samples for {n}; fitted")
    lag = master_lag(pre, master)

    # Gates on the written master and stems.
    gates = {}
    lufs, tp = meas["I"], meas["TP"]
    peak = float(np.abs(master).max())
    clips = int(np.count_nonzero(np.abs(master) >= CLIP_LEVEL))
    gate(gates, "lufs", lufs is not None and abs(lufs - TARGET_LUFS) <= LUFS_TOL, lufs,
         [TARGET_LUFS - LUFS_TOL, TARGET_LUFS + LUFS_TOL])
    gate(gates, "clip", clips == 0, clips, 0)
    attack_s, release_s = duck["attack_s"], duck["release_s"]
    mutes = cfg["bed"]["mutes"] if cfg["bed"] else []
    silences = find_silences(mix_path, ffmpeg, clip_s)
    holes = [s for s in silences
             if not any(s[0] >= m0 - attack_s - 0.001 and s[1] <= m1 + release_s + 0.001 for m0, m1 in mutes)]
    gate(gates, "silence", not holes, [list(s) for s in holes], "none outside bed.mutes")

    margins = []
    if cfg["bed"]:
        margins = duck_margins(spans, clip_s, outdir / files["stems"]["dialogue"], outdir / files["stems"]["bed"],
                               ffmpeg)
        if any(m["dialogue_lufs"] is not None and silent_lufs(m["dialogue_lufs"]) for m in margins):
            warnings.append("duck_span_without_speech: a duck span has no measurable dialogue (check word times)")
        low = [m for m in margins if m["margin_db"] is not None]
        worst = min(low, key=lambda m: m["margin_db"]) if low else None
        gate(gates, "duck_margin", worst is None or worst["margin_db"] >= MARGIN_FAIL_DB,
             None if worst is None else worst["margin_db"], MARGIN_FAIL_DB)
        if worst and MARGIN_FAIL_DB <= worst["margin_db"] < MARGIN_WARN_DB:
            warnings.append(f"duck_margin_low: {worst['margin_db']} dB at {worst['s']}-{worst['e']} s "
                            f"(under {MARGIN_WARN_DB:.0f} dB the bed fights the voice)")
        gate(gates, "bed_low_share", bed_rep["low_share"] < LOW_SHARE_WARN, bed_rep["low_share"], LOW_SHARE_WARN,
             level="warn")
    gate(gates, "inputs", all(not r["silent"] and not r["decode_errors"] for r in inputs),
         [r["what"] for r in inputs if r["silent"] or r["decode_errors"]], "decodes, has audio, not silent where used")
    if sfx_rows:  # a silent SFX fails the inputs gate; it has no hit to align
        missed = [r for r in sfx_rows if not r["silent"] and not r["aligned"]]
        gate(gates, "sfx_align", not missed,
             [{"i": r["i"], "frame": r["frame"], "peak_frame": r["peak_frame"], "peak_cut": r["peak_cut"]}
              for r in missed], "peak in frames [F, F+2]")
        gate(gates, "sfx_reuse", not reuse, reuse, "every SFX a distinct sound")
    gate(gates, "master_lag", lag == 0, lag, 0)

    failed = [k for k, g in gates.items() if not g["ok"] and g["level"] == "error"]
    if "bed_low_share" in gates and not gates["bed_low_share"]["ok"]:
        warnings.append(f"bed_low_share: {bed_rep['low_share']} of the bed's energy is under 150 Hz; phone speakers "
                        "drop it, pick another bed")
    hints = fix_hints(failed, gates, inputs, duck)
    vom = [m["margin_db"] for m in margins if m["margin_db"] is not None]
    log = (f"audio {outdir.resolve().name} lufs:{_fmt(lufs)} tp:{_fmt(tp)} clip:{clips} sil:{len(holes)} "
           f"vom:{round(min(vom)) if vom else 'na'}")
    return {"ok": not failed, "version": SCRIPT_VERSION, "plan": Path(plan_path).resolve().as_posix(),
            "outdir": outdir.resolve().as_posix(), "fps": cl.frac_str(fps), "frames": frames, "sr": SR,
            "samples": n, "duration_s": round(n / SR, 6), "files": files, "dialogue": dlg_rep,
            "duck": {**duck, "spans": [list(s) for s in spans], "word_spans": len(cfg["words"]),
                     "vad_spans": len(vad), "vad_threshold_db": vad_thr, "margins": margins},
            "bed": bed_rep, "sfx": sfx_rows,
            "master": {"lufs_sum": i_sum, "trim_db": trim, "passes": passes, "limiter": LIMITER, "lufs": lufs,
                       "tp_dbtp": tp,
                       "sample_peak_dbfs": round(20 * math.log10(peak), 2) if peak > 0 else None,
                       "clip_samples": clips, "silences": [list(s) for s in silences], "lag_samples": lag},
            "inputs": inputs, "gates": gates, "failed": failed, "hints": hints, "aac": AAC_NOTE,
            "warnings": warnings, "log": log}


def _fmt(v):
    return "na" if v is None else f"{v:.1f}"


def fix_hints(failed, gates, inputs, duck):
    hints = {}
    if "lufs" in failed:
        hints["lufs"] = ("the master misses -14 LUFS after its static trim: heavy limiting of a very peaky mix lowers "
                         "it, or the mix is silent; lower sfx gain_db or check the dialogue stem")
    if "clip" in failed:
        hints["clip"] = "full-scale samples after the limiter: this ffmpeg's alimiter did not hold limit=0.708"
    if "silence" in failed:
        hints["silence"] = ("holes in the master at " + ", ".join(f"{a}-{b} s" for a, b in gates["silence"]["measured"])
                            + ": the bed has a gap or the clip has no bed; fix the bed, or plan the mute in bed.mutes")
    if "duck_margin" in failed:
        short = round(MARGIN_WARN_DB - gates["duck_margin"]["measured"], 1)
        hints["duck_margin"] = (f"deepen the duck by {short} dB (duck.depth_db {duck['depth_db']} -> "
                                f"{round(duck['depth_db'] - short, 1)}) or lower bed.lufs by {short} dB, then re-run")
    if "inputs" in failed:
        bad = [f"{r['what']} ({'silent where used' if r['silent'] else 'decode errors'})" for r in inputs
               if r["silent"] or r["decode_errors"]]
        hints["inputs"] = "replace or re-export: " + ", ".join(bad)
    if "sfx_align" in failed:
        hints["sfx_align"] = ("an SFX hit misses frames [F, F+2]; peak_cut means the accent is on the last frame, "
                              "where no hit can land: move it at least one frame earlier. " + ", ".join(
                                  f"sfx[{m['i']}] frame {m['frame']} -> peak frame {m['peak_frame']}"
                                  for m in gates["sfx_align"]["measured"]))
    if "sfx_reuse" in failed:
        hints["sfx_reuse"] = ("each accent needs a distinct sound (ref 01 section 5): swap in another variant for "
                              + ", ".join(f"sfx[{p['b']}] ({p['why']} as sfx[{p['a']}])"
                                          for p in gates["sfx_reuse"]["measured"]))
    if "master_lag" in failed:
        hints["master_lag"] = ("the limiter path moved the audio: this ffmpeg's alimiter lacks latency compensation "
                               "(latency=1); use ffmpeg 4.4 or newer")
    return hints


if __name__ == "__main__":
    cl.run_main(main)
