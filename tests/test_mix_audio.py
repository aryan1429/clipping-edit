"""Tests for skill/scripts/mix_audio.py: synthetic media, the real CLI as a subprocess.

Run from the repo root:  python -P tests/test_mix_audio.py
One PASS/FAIL line per check; exit 0 only when every check passes. Negative controls (a too-hot bed, reused
and silent SFX, a hit on the last frame, a bed with a hole, bad plans) must FAIL their gates.
"""
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from fractions import Fraction
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixtures as fx  # noqa: E402

cl = fx.cl
SCRIPT = fx.ROOT / "skill" / "scripts" / "mix_audio.py"
SR = 48000
LIMITER = "aresample=192000,alimiter=limit=0.708:attack=5:release=50:level=0:latency=1,aresample=48000"
PHRASES = [(0.0, 2.6), (4.4, 7.0), (8.6, 11.6)]  # speech with two 1.8 s gaps
FAILED = []


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'} {name}" + (f"  [{detail}]" if detail else ""), flush=True)
    if not cond:
        FAILED.append(name)
    return bool(cond)


# ---------------------------------------------------------------- media

def words_in(phrases, step=0.3, length=0.25):
    out = []
    for a, b in phrases:
        t = a
        while t + step <= b + 1e-9:
            out.append({"start": round(t, 3), "end": round(t + length, 3)})
            t += step
    return out


def write_dialogue(path, words, n, gain_db=0.0, plosives=False):
    """Mono float stem like splice.py's (n samples). plosives adds 12 ms low thumps far above the speech."""
    x = fx.talk_track(words, n / SR + 0.1)[:n].astype(np.float64) * 10 ** (gain_db / 20)
    if plosives:
        tt = np.arange(int(0.012 * SR)) / SR
        for w in words[::4]:
            i = int(w["start"] * SR) + 200
            x[i:i + len(tt)] += 0.9 * np.sin(2 * np.pi * 110 * tt) * np.exp(-tt * 150)
    cl.write_wav_f32(path, x.astype(np.float32))


def steady_bed(path, dur, hole=None):
    """Tones at 500, 1000 and 2000 Hz: a flat envelope with a 2 ms period, so a 96-sample RMS reads the duck gain."""
    t = np.arange(int(round(dur * SR))) / SR
    x = sum(np.sin(2 * np.pi * f * t) for f in (500.0, 1000.0, 2000.0)) * (0.2 / 3)
    if hole:
        x[int(hole[0] * SR):int(hole[1] * SR)] = 0.0
    cl.write_wav_f32(path, np.stack([x, x], 1).astype(np.float32))


def read_wav(path):
    """(float32 samples (n, ch), sample rate, format tag, bits per sample) of a float WAV."""
    b = Path(path).read_bytes()
    assert b[:4] == b"RIFF" and b[8:12] == b"WAVE", path
    pos, fmt, data = 12, None, None
    while pos + 8 <= len(b):
        cid, size = b[pos:pos + 4], struct.unpack("<I", b[pos + 4:pos + 8])[0]
        if cid == b"fmt ":
            fmt = struct.unpack("<HHIIHH", b[pos + 8:pos + 24])
        elif cid == b"data":
            data = b[pos + 8:pos + 8 + size]
        pos += 8 + size + (size & 1)
    tag, ch, sr, _, _, bits = fmt
    return np.frombuffer(data, "<f4").reshape(-1, ch), sr, tag, bits


def build_media(work):
    words = words_in(PHRASES)
    write_dialogue(work / "dlg.wav", words, 576000)  # 720 frames at 60 fps
    steady_bed(work / "bed.wav", 30.0)
    steady_bed(work / "bed_hole.wav", 30.0, hole=(3.2, 3.7))
    steady_bed(work / "bed_short.wav", 10.0)
    fx.music_bed(work / "bed808.wav", dur=40.0, quiet_intro=8.3)  # kick + low pad: most energy under 150 Hz
    for kind in ("hit", "whoosh", "riser"):
        fx.sfx_file(work / f"{kind}.wav", kind)
    whoosh = read_wav(work / "whoosh.wav")[0]
    cl.write_wav_f32(work / "whoosh_mono.wav", whoosh[:, 0].copy())
    hit = read_wav(work / "hit.wav")[0]
    shutil.copyfile(work / "hit.wav", work / "hit_copy.wav")  # same bytes, other name
    cl.write_wav_f32(work / "hit_quiet.wav", hit * np.float32(10 ** (-9 / 20)))  # same sound, -9 dB
    cl.write_wav_f32(work / "silent.wav", np.zeros((24000, 2), np.float32))
    return words


# ---------------------------------------------------------------- running and measuring

def run(work, name, plan, extra=(), outroot="clips"):
    """Write the plan, run the CLI -> (exit code, stdout JSON or None, outdir). Relative plan paths resolve from cwd."""
    plan_path = work / f"{name}.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    outdir = work / outroot / name
    cp = subprocess.run([sys.executable, "-P", str(SCRIPT), "--plan", str(plan_path), "--outdir", str(outdir),
                         "--ffmpeg", fx.ffmpeg(), *extra], capture_output=True, cwd=work)
    try:
        j = json.loads(cp.stdout.decode("utf-8", "replace"))
    except json.JSONDecodeError:
        j = None
        print(cp.stderr.decode("utf-8", "replace")[-3000:])
    return cp.returncode, j, outdir


def base_plan(words, frames=720, fps="60/1", dialogue="dlg.wav"):
    return {"fps": fps, "frames": frames, "dialogue": dialogue, "words": [[w["start"], w["end"]] for w in words]}


def rms(x):
    return float(np.sqrt(np.mean(np.asarray(x, np.float64) ** 2)))


def rms_at(x, t, win=96):
    c = int(round(t * SR))
    return rms(x[c - win // 2:c + win // 2])


def db(v):
    return 20 * math.log10(v)


def lowpass(x, hz=20000.0):
    """Zero every FFT bin above hz (per channel)."""
    spec = np.fft.rfft(x, axis=0)
    spec[np.fft.rfftfreq(len(x), 1.0 / SR) > hz] = 0
    return np.fft.irfft(spec, len(x), axis=0)


def lane(t, spans, depth=10 ** (-10 / 20), attack=0.02, release=0.3):
    """The duck rule written out: 1 -> depth over [s - 20 ms, s], depth inside, depth -> 1 over [e, e + 300 ms]."""
    g = 1.0
    for s, e in spans:
        if s - attack < t < s:
            v = 1 - (1 - depth) * (t - (s - attack)) / attack
        elif s <= t <= e:
            v = depth
        elif e < t < e + release:
            v = depth + (1 - depth) * (t - e) / release
        else:
            v = 1.0
        g = min(g, v)
    return g


def check_passes(tag, m):
    """The limiter is re-run at most once, only after a miss of more than 0.5 LU, with the miss added to the trim."""
    p = m["passes"]
    ok = 1 <= len(p) <= 2 and abs(m["lufs"] + 14) <= 0.5 and p[-1]["trim_db"] == m["trim_db"]
    if len(p) == 2:
        ok = ok and abs(p[0]["lufs"] + 14) > 0.5 and p[1]["trim_db"] == round(p[0]["trim_db"] - 14 - p[0]["lufs"], 2)
    check(f"{tag}: master within 0.5 LU of -14 after at most one corrective limiter pass", ok, str(p))


def peak_frame(x, target_t, fps, search=0.25):
    """Independent hit measurement: argmax of a centred 4 ms RMS every 1 ms near target_t -> (frame showing it, t)."""
    a, b = max(0, int((target_t - search) * SR)), min(len(x), int((target_t + search) * SR))
    e = (x[a:b].astype(np.float64) ** 2).mean(axis=1)
    cs = np.concatenate([[0.0], np.cumsum(e)])
    centers = np.arange(0, len(e), 48)
    lo, hi = np.clip(centers - 96, 0, len(e)), np.clip(centers + 96, 0, len(e))
    t = (a + centers[int(np.argmax((cs[hi] - cs[lo]) / np.maximum(hi - lo, 1)))]) / SR
    return int(math.floor((t + 0.0005) * float(fps) + 1e-6)), t


# ---------------------------------------------------------------- cases

def case_default(work, words):
    print("-- default plan: 60 fps, steady bed, hit + riser + mono whoosh")
    fps, n = 60, 576000
    sfx = [("hit.wav", 198), ("riser.wav", 360), ("whoosh_mono.wav", 456)]
    plan = {**base_plan(words), "bed": {"path": "bed.wav", "offset_s": None, "lufs": -20.0},
            "sfx": [{"path": p, "frame": f, "gain_db": 0.0} for p, f in sfx],
            "duck": {"depth_db": -10, "attack_s": 0.02, "release_s": 0.3}}
    code, j, out = run(work, "default", plan)
    if not check("default: exit 0, ok, no failed gate", code == 0 and j and j["ok"] and j["failed"] == [],
                 f"exit {code}, failed {j and j.get('failed')}"):
        return
    check("default: version 1.0.0 and mix_report.json equal to stdout",
          j["version"] == "1.0.0" and json.loads((out / "mix_report.json").read_text("utf-8")) == j)
    mix, sr, tag, bits = read_wav(out / "mix.wav")
    check("default: mix.wav is float32 stereo 48 kHz", (sr, tag, bits, mix.shape[1]) == (SR, 3, 32, 2),
          f"sr {sr} tag {tag} bits {bits} ch {mix.shape[1]}")
    check("default: exactly round(N * 48000 / fps) samples", len(mix) == n == j["samples"], f"{len(mix)} vs {n}")
    stems = {k: read_wav(out / v)[0] for k, v in j["files"]["stems"].items()}
    check("default: three float stems of the same length", all(len(v) == n and v.shape[1] == 2 for v in stems.values()),
          str({k: v.shape for k, v in stems.items()}))
    dlg, bed, sfxs = stems["dialogue"], stems["bed"], stems["sfx"]

    # Duck lane: the bed stem divided by its unducked level must follow the rule's lane at every probe point.
    spans = [tuple(s) for s in j["duck"]["spans"]]
    inside = all(any(s - 1e-6 <= w["start"] and w["end"] <= e + 1e-6 for s, e in spans) for w in words)
    gaps = [b[0] - a[1] for a, b in zip(spans, spans[1:])]
    check("default: duck spans hold every word and merged gaps are >= 0.6 s", inside and min(gaps) >= 0.6,
          f"spans {spans}")
    ref = rms_at(bed, (spans[0][1] + 0.3 + spans[1][0] - 0.02) / 2)  # middle of the first gap, fully released
    probes = []
    for s, e in spans:
        for t in (s - 0.03, s - 0.015, s - 0.005, s + 0.005, (s + e) / 2, e + 0.05, e + 0.15, e + 0.25, e + 0.32):
            if 0.01 <= t <= n / SR - 0.01:
                probes.append(abs(rms_at(bed, t) / ref - lane(t, spans)))
    check("default: bed lane = 20 ms down-ramp ending at each span start, -10 dB, 300 ms up-ramp",
          max(probes) < 0.02, f"{len(probes)} probes, worst error {max(probes):.4f}")
    check("default: speech at t=0 -> the bed starts ducked", abs(rms_at(bed, 0.012) / ref - 10 ** -0.5) < 0.02,
          f"gain {rms_at(bed, 0.012) / ref:.3f}")

    # SFX on the hit, at -11 dBFS, mono upmixed at full level.
    for (path, frame), row in zip(sfx, j["sfx"]):
        k, _ = peak_frame(sfxs, (frame + 1) / fps, fps)
        a = int(round(row["start_s"] * SR))
        pk = db(float(np.abs(sfxs[a:a + int(2.1 * SR)]).max()))
        check(f"default: {path} peak shows in frames [F, F+2] (F={frame}) at -11 dBFS",
              row["aligned"] and frame <= row["peak_frame"] <= frame + 2 and frame <= k <= frame + 2
              and abs(pk + 11) < 0.1, f"report {row['peak_frame']} measured {k}, offset {row['peak_offset_frames']}, "
                                      f"peak {pk:.2f} dBFS")
    w = j["sfx"][2]
    seg = sfxs[int(round(w["start_s"] * SR)):int(round(w["start_s"] * SR)) + int(0.9 * SR)]
    check("default: mono SFX lands on both channels equally", np.array_equal(seg[:, 0], seg[:, 1])
          and abs(db(float(np.abs(seg[:, 1]).max())) + 11) < 0.1)
    check("default: mono dialogue duplicated to both channels", np.array_equal(dlg[:, 0], dlg[:, 1]))

    # Unity sum: in the released gap the master equals (dialogue + bed + SFX) x trim, not -6 dB (amix) or -3 dB.
    # Compared below 20 kHz: the 192 kHz limiter path's anti-alias filter (~23.3 kHz) trims the noise hit's top band.
    a, b = int(2.8 * SR), int(4.3 * SR)
    want = lowpass((dlg[a:b].astype(np.float64) + bed[a:b] + sfxs[a:b]) * 10 ** (j["master"]["trim_db"] / 20))
    got = lowpass(mix[a:b].astype(np.float64))
    resid, level = db(rms(got - want) / rms(want)), db(rms(got) / rms(want))
    check("default: master = unity float sum of the stems x static trim (below 20 kHz)",
          resid < -60 and abs(level) < 0.01, f"residual {resid:.1f} dB, level {level:+.4f} dB")

    # Master: the limiter as specified, nothing clipped, nothing shifted, loudness on target.
    peak = float(np.abs(mix).max())
    check("default: limiter chain verbatim, sample peak <= -2 dBFS, 0 clipped",
          j["master"]["limiter"] == LIMITER and peak <= 10 ** (-2.0 / 20) and j["master"]["clip_samples"] == 0,
          f"peak {db(peak):.2f} dBFS")
    check("default: master -14 +/- 1 LUFS (gate), no silence, lag 0 samples",
          abs(j["master"]["lufs"] + 14) <= 1 and j["master"]["silences"] == [] and j["master"]["lag_samples"] == 0,
          f"lufs {j['master']['lufs']} tp {j['master']['tp_dbtp']}")
    check_passes("default", j["master"])
    check("default: duck margins 16 +/- 1.5 dB on every span",
          all(abs(m["margin_db"] - 16) <= 1.5 for m in j["duck"]["margins"]),
          str([m["margin_db"] for m in j["duck"]["margins"]]))
    check("default: dialogue at -14 +/- 0.5 LUFS through the static chain",
          abs(j["dialogue"]["lufs"] + 14) <= 0.5 and "acompressor=threshold=0.1:ratio=3" in j["dialogue"]["chain"],
          f"lufs {j['dialogue']['lufs']} total gain {j['dialogue']['total_gain_db']}")
    check("default: report hands AAC + true peak to finalize_mux; log line format",
          "finalize_mux" in j["aac"] and re.fullmatch(r"audio default lufs:-?\d+\.\d tp:-?\d+\.\d clip:0 sil:0 vom:\d+",
                                                       j["log"]) is not None, j["log"])


def case_ntsc(work, words):
    print("-- 30000/1001 fps: fractional samples per frame")
    fps, frames = Fraction(30000, 1001), 361
    n = round(frames * SR / fps)
    write_dialogue(work / "dlg_ntsc.wav", words, n)
    sfx = [("riser.wav", 20), ("hit.wav", 150)]  # the riser crests 1.9 s in: its head is trimmed at the clip start
    plan = {**base_plan(words, frames, "30000/1001", "dlg_ntsc.wav"), "bed": {"path": "bed.wav"},
            "sfx": [{"path": p, "frame": f} for p, f in sfx]}
    plan["words"] = words  # cutlist-style {"start", "end"} objects are accepted too
    code, j, out = run(work, "ntsc", plan)
    if not check("ntsc: exit 0, ok", code == 0 and j and j["ok"], f"exit {code}, failed {j and j.get('failed')}"):
        return
    mix = read_wav(out / "mix.wav")[0]
    check("ntsc: exactly round(361 * 48000 * 1001 / 30000) = 578178 samples", len(mix) == n == j["samples"] == 578178,
          f"{len(mix)}")
    check("ntsc: word objects read like pairs", j["duck"]["word_spans"] == len(words), str(j["duck"]["word_spans"]))
    sfxs = read_wav(out / "mix_sfx.wav")[0]
    for (path, frame), row in zip(sfx, j["sfx"]):
        k, _ = peak_frame(sfxs, (frame + 1) / float(fps), fps)
        check(f"ntsc: {path} peak shows in frames [F, F+2] (F={frame})",
              row["aligned"] and frame <= k <= frame + 2, f"report {row['peak_frame']} measured {k}")
    check("ntsc: an SFX starting before 0 is head-trimmed and still lands",
          j["sfx"][0]["start_s"] < 0 and j["sfx"][0]["head_trimmed_s"] > 1.0 and j["sfx"][0]["aligned"],
          f"start {j['sfx'][0]['start_s']} trimmed {j['sfx'][0]['head_trimmed_s']}")


def case_hot_bed(work, words):
    print("-- negative control: a too-hot bed must fail the duck margin")
    plan = {**base_plan(words), "bed": {"path": "bed.wav", "lufs": -6.0}}
    code, j, out = run(work, "hot_bed", plan)
    if not check("hot bed: exit 1, not ok", code == 1 and j and not j["ok"], f"exit {code}"):
        return
    g = j["gates"]["duck_margin"]
    check("hot bed: only duck_margin fails, measured under 9 dB", j["failed"] == ["duck_margin"] and g["measured"] < 9,
          f"failed {j['failed']}, margin {g['measured']}")
    hint = j["hints"]["duck_margin"]
    m = re.search(r"duck\.depth_db -?[\d.]+ -> (-?[\d.]+)", hint)
    check("hot bed: hint says how far to deepen", m is not None, hint)
    check("hot bed: files still written", len(read_wav(out / "mix.wav")[0]) == 576000
          and (out / "mix_report.json").is_file())
    if m:  # positive control: the hinted depth fixes it
        plan["duck"] = {"depth_db": float(m.group(1))}
        code, j, _ = run(work, "hot_bed_fixed", plan)
        check("hot bed + hinted depth: duck margin back to >= 12 dB, exit 0",
              code == 0 and j and j["ok"] and j["gates"]["duck_margin"]["measured"] >= 11.9,
              f"exit {code}, margin {j and j['gates']['duck_margin']['measured']}")


def case_bad_sfx(work, words):
    print("-- negative controls: reused, silent and last-frame SFX")
    sfx = [("hit.wav", 100), ("hit.wav", 200), ("hit_copy.wav", 300), ("hit_quiet.wav", 400), ("silent.wav", 500),
           ("riser.wav", 600), ("whoosh.wav", 719)]
    plan = {**base_plan(words), "bed": {"path": "bed.wav"}, "sfx": [{"path": p, "frame": f} for p, f in sfx]}
    code, j, _ = run(work, "bad_sfx", plan)
    if not check("bad sfx: exit 1", code == 1 and j and not j["ok"], f"exit {code}"):
        return
    check("bad sfx: exactly inputs, sfx_align and sfx_reuse fail", j["failed"] == ["inputs", "sfx_align", "sfx_reuse"],
          str(j["failed"]))
    pairs = {(p["a"], p["b"], p["why"]) for p in j["gates"]["sfx_reuse"]["measured"]}
    want = {(0, 1, "same_file"), (0, 2, "same_bytes"), (1, 2, "same_bytes"), (0, 3, "same_sound"),
            (1, 3, "same_sound"), (2, 3, "same_sound")}
    check("bad sfx: same file, byte copy and -9 dB copy all detected; distinct sounds not flagged", pairs == want,
          str(sorted(pairs)))
    check("bad sfx: the silent file fails the inputs gate", j["gates"]["inputs"]["measured"] == ["sfx[4]"],
          str(j["gates"]["inputs"]["measured"]))
    miss = j["gates"]["sfx_align"]["measured"]
    check("bad sfx: a hit on the last frame cannot land (peak_cut)",
          len(miss) == 1 and miss[0]["i"] == 6 and miss[0]["peak_cut"], str(miss))


def case_hole(work, words):
    print("-- negative control: a bed hole in a speech gap; then the same hole inside a planned mute")
    plan = {**base_plan(words), "bed": {"path": "bed_hole.wav", "offset_s": 0.0}}
    code, j, _ = run(work, "hole", plan)
    if check("hole: exit 1, only the silence gate fails", code == 1 and j and j["failed"] == ["silence"],
             f"exit {code}, failed {j and j.get('failed')}"):
        holes = j["gates"]["silence"]["measured"]
        check("hole: the hole is found at 3.2-3.7 s", len(holes) == 1 and abs(holes[0][0] - 3.2) < 0.06
              and abs(holes[0][1] - 3.7) < 0.06, str(holes))
    plan["bed"]["mutes"] = [[3.1, 3.8]]
    code, j, _ = run(work, "hole_muted", plan)
    check("hole in a planned mute: exit 0, silence reported but allowed",
          code == 0 and j and j["ok"] and j["master"]["silences"] and j["gates"]["silence"]["measured"] == [],
          f"exit {code}, silences {j and j['master']['silences']}")


def case_808_offset(work, words):
    print("-- bass-heavy bed with an 8.3 s quiet intro, automatic entry point")
    code, j, _ = run(work, "bed808", {**base_plan(words), "bed": {"path": "bed808.wav"}})
    if not check("808 bed: exit 0 (low share only warns)", code == 0 and j and j["ok"],
                 f"exit {code}, failed {j and j.get('failed')}"):
        return
    g = j["gates"]["bed_low_share"]
    check("808 bed: low share >= 0.5 -> warn-level gate fails and a warning names it",
          not g["ok"] and g["level"] == "warn" and g["measured"] >= 0.5
          and any(w.startswith("bed_low_share") for w in j["warnings"]), f"share {g['measured']}")
    check("808 bed: automatic offset skips the quiet intro (8.2 +/- 0.15 s)",
          j["bed"]["offset_auto"] and abs(j["bed"]["offset_s"] - 8.2) <= 0.15, f"offset {j['bed']['offset_s']}")


def case_short_bed(work):
    print("-- 10 s bed under a 20 s clip: loops with crossfades, no holes")
    words = words_in([(0.0, 2.6), (4.4, 7.0), (8.6, 11.6), (13.0, 16.0), (17.5, 19.9)])
    write_dialogue(work / "dlg20.wav", words, 960000)
    code, j, out = run(work, "short_bed", {**base_plan(words, 1200, dialogue="dlg20.wav"),
                                          "bed": {"path": "bed_short.wav"}})
    if not check("short bed: exit 0", code == 0 and j and j["ok"], f"exit {code}, failed {j and j.get('failed')}"):
        return
    check("short bed: looped twice from offset 0, no silence", j["bed"]["loops"] == 2 and j["bed"]["offset_s"] == 0
          and j["master"]["silences"] == [], f"loops {j['bed']['loops']} offset {j['bed']['offset_s']}")
    bed = read_wav(out / "mix_bed.wav")[0]
    win = 960  # 20 ms
    levels = np.array([rms(bed[i:i + win]) for i in range(480, len(bed) - 480 - win, win)])
    check("short bed: no 20 ms window more than 14 dB under the median (no seam holes)",
          levels.min() >= np.median(levels) * 10 ** (-14 / 20),
          f"min {db(levels.min()):.1f} dB, median {db(float(np.median(levels))):.1f} dB")


def case_peaky(work, words):
    print("-- dialogue with hot 12 ms plosives: the limiter holds")
    write_dialogue(work / "dlg_peaky.wav", words, 576000, plosives=True)
    code, j, out = run(work, "peaky", {**base_plan(words, dialogue="dlg_peaky.wav"), "bed": {"path": "bed.wav"}})
    if not check("peaky: exit 0", code == 0 and j and j["ok"], f"exit {code}, failed {j and j.get('failed')}"):
        return
    peak = float(np.abs(read_wav(out / "mix.wav")[0]).max())
    m = j["master"]
    check("peaky: sample peak <= -2 dBFS (level=0: no re-normalise), true peak <= -2 dBTP, 0 clipped",
          peak <= 10 ** (-2.0 / 20) and m["tp_dbtp"] <= -2.0 and m["clip_samples"] == 0,
          f"peak {db(peak):.2f} dBFS, tp {m['tp_dbtp']}")
    check("peaky: -14 +/- 1 LUFS, lag 0 (latency=1)", abs(m["lufs"] + 14) <= 1 and m["lag_samples"] == 0,
          f"lufs {m['lufs']}")
    check_passes("peaky", m)


def case_quiet_no_ffprobe(work):
    print("-- quiet dialogue, no bed, no SFX; once with --ffprobe none")
    words = words_in([(0.0, 7.8)])
    n = 468 * 800  # 7.8 s at 60 fps
    write_dialogue(work / "dlg_quiet.wav", words, n - 100, gain_db=-21)  # 100 samples short: within one frame
    plan = base_plan(words, 468, dialogue="dlg_quiet.wav")
    code, j, out = run(work, "quiet", plan)
    if not check("quiet: exit 0", code == 0 and j and j["ok"], f"exit {code}, failed {j and j.get('failed')}"):
        return
    check("quiet: total dialogue gain > 12 dB is warned about", j["dialogue"]["total_gain_db"] > 12
          and any(w.startswith("dialogue_gain_high") for w in j["warnings"]), f"gain {j['dialogue']['total_gain_db']}")
    check("quiet: a stem under one frame short is fitted to the exact length with a warning",
          any(w.startswith("dialogue_length") for w in j["warnings"]) and len(read_wav(out / "mix.wav")[0]) == n)
    check("quiet: no bed -> no bed stem and no duck gates", j["bed"] is None and j["files"]["stems"]["bed"] is None
          and "duck_margin" not in j["gates"] and "bed_low_share" not in j["gates"])
    code2, j2, _ = run(work, "quiet", plan, extra=("--ffprobe", "none"), outroot="clips_noprobe")
    keys = ("samples", "dialogue", "duck", "master", "gates", "warnings", "log")
    check("quiet: --ffprobe none gives the identical result", code2 == 0 and j2
          and all(j[k] == j2[k] for k in keys), str([k for k in keys if j2 and j[k] != j2[k]]))


def case_exit2(work, words):
    print("-- usage errors and unreadable inputs exit 2 with one JSON error")
    cl.write_wav_f32(work / "dlg_cut.wav", np.zeros(576000 - 1600, np.float32))
    good = {**base_plan(words), "bed": {"path": "bed.wav"}}
    cases = [("no_frames", {k: v for k, v in good.items() if k != "frames"}, (), "bad_plan"),
             ("missing_dialogue", {**good, "dialogue": "nope.wav"}, (), "input_missing"),
             ("sfx_frame_range", {**good, "sfx": [{"path": "hit.wav", "frame": 720}]}, (), "bad_plan"),
             ("length_mismatch", {**good, "dialogue": "dlg_cut.wav"}, (), "length_mismatch"),
             ("usage", good, ("--bogus",), "usage")]
    for name, plan, extra, want in cases:
        code, j, _ = run(work, name, plan, extra=extra)
        got = j and j.get("error", {}).get("code")
        check(f"exit 2: {name} -> {want}", code == 2 and j is not None and j["ok"] is False and got == want,
              f"exit {code}, code {got}")


def main():
    work = Path(tempfile.mkdtemp(prefix="test_mix_audio-"))
    try:
        words = build_media(work)
        case_default(work, words)
        case_ntsc(work, words)
        case_hot_bed(work, words)
        case_bad_sfx(work, words)
        case_hole(work, words)
        case_808_offset(work, words)
        case_short_bed(work)
        case_peaky(work, words)
        case_quiet_no_ffprobe(work)
        case_exit2(work, words)
    finally:
        try:
            shutil.rmtree(work)
        except OSError as e:
            print(f"note: could not remove {work}: {e}")
    print("ALL PASS" if not FAILED else f"{len(FAILED)} FAILED: " + "; ".join(FAILED))
    return 0 if not FAILED else 1


if __name__ == "__main__":
    cl.utf8_stdio()
    sys.exit(main())
