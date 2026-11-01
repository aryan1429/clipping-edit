"""Synthetic media for the clipping-edit script tests (no real footage, no network).

Everything is generated with ffmpeg lavfi sources and numpy, so the tests run anywhere ffmpeg runs.
Import from a test file:
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import fixtures as fx

Main entry points:
- shots_video(path, shots, fps, size, audio=None)  hard cuts, punch-ins, flashes with exact frame counts
- talk_track(words, dur, sr)  speech-like bursts at given word times (numpy float32 mono)
- podcast(dirpath, ...)  a ready-made "podcast" source: mp4 + transcript.json + truth.json
- music_bed(path, dur), sfx_file(path, kind)  bed and SFX with known peak positions
"""
import json
import math
import os
import sys
from fractions import Fraction
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skill" / "scripts"))
import cliplib as cl  # noqa: E402

FF = None


def ffmpeg():
    global FF
    if FF is None:
        FF = cl.find_ffmpeg()
    return FF


TAGS_709 = "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv"
X264_709 = ["-x264-params", "colorprim=bt709:transfer=bt709:colormatrix=bt709"]


def _shot_filter(kind, frames, fps, w, h, idx):
    d = cl.t6(Fraction(frames) / Fraction(fps))
    r = cl.frac_str(Fraction(fps))
    if kind == "testsrc2":
        return f"testsrc2=s={w}x{h}:r={r}:d={d}"
    if kind == "hue":  # a second "camera": same pattern family, rotated hue and moved
        return f"testsrc2=s={w}x{h}:r={r}:d={d},hue=h=140:s=1.4,hflip"
    if kind == "bars":
        return f"smptehdbars=s={w}x{h}:r={r}:d={d}"
    if kind == "punch":  # same-angle punch-in (20 % tighter)
        return f"testsrc2=s={w}x{h}:r={r}:d={d},crop=iw*0.8:ih*0.8,scale={w}:{h}"
    if kind in ("white", "black", "gray"):
        c = {"white": "white", "black": "black", "gray": "0x808080"}[kind]
        return f"color=c={c}:s={w}x{h}:r={r}:d={d}"
    raise ValueError(kind)


def shots_video(path, shots, fps=60, size=(1280, 720), audio=None, crf=18, extra_vf=None, audio_codec="aac"):
    """Write an mp4 whose shots are [(kind, frames), ...] back to back (exact frame counts).

    kind: testsrc2 | hue | bars | punch | white | black | gray. audio: float32 mono/stereo numpy at 48 kHz
    (padded or cut to the video length) or None. Returns {'frames', 'cuts' (frame indices), 'fps'}.
    """
    w, h = size
    parts, labels = [], []
    for i, (kind, frames) in enumerate(shots):
        parts.append(f"{_shot_filter(kind, frames, fps, w, h, i)},format=yuv420p,setsar=1[s{i}]")
        labels.append(f"[s{i}]")
    vf = ",".join(x for x in [TAGS_709, extra_vf] if x)
    graph = ";".join(parts) + ";" + "".join(labels) + f"concat=n={len(shots)}:v=1:a=0,{vf}[v]"
    total = sum(f for _, f in shots)
    cmd = [ffmpeg(), "-v", "error", "-y", "-filter_complex", graph]
    wav = None
    if audio is not None:
        n = int(round(total / Fraction(fps) * 48000))
        a = np.zeros((n,) + audio.shape[1:], np.float32)
        a[: min(n, len(audio))] = audio[:n]
        wav = str(Path(path).with_suffix(".src.wav"))
        cl.write_wav_f32(wav, a, 48000)
        cmd += ["-i", wav]
    cmd += ["-map", "[v]"]
    if wav:  # the lavfi shots live inside the graph, so the WAV is input 0
        cmd += ["-map", "0:a", "-c:a", audio_codec, "-b:a", "192k", "-ar", "48000"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf), "-pix_fmt", "yuv420p", *X264_709,
            "-r", cl.frac_str(Fraction(fps)), "-movflags", "+faststart", str(path)]
    cl.run(cmd)
    if wav:
        os.remove(wav)
    cuts, k = [], 0
    for kind, frames in shots[:-1]:
        k += frames
        cuts.append(k)
    return {"frames": total, "cuts": cuts, "fps": cl.frac_str(Fraction(fps))}


def talk_track(words, dur, sr=48000, seed=7, level=0.08):
    """Speech-like audio: band-limited noise bursts with a ~5 Hz syllable envelope inside each word span.

    words: [{'start', 'end'}, ...] seconds. Silence elsewhere (true dead air). Returns float32 mono.
    """
    rng = np.random.default_rng(seed)
    n = int(round(dur * sr))
    out = np.zeros(n, np.float32)
    for i, wd in enumerate(words):
        a, b = int(round(wd["start"] * sr)), int(round(wd["end"] * sr))
        if b <= a:
            continue
        m = b - a
        noise = rng.standard_normal(m).astype(np.float32)
        # crude formant colouring: two resonances via moving sums
        k1, k2 = 9, 3
        c1 = np.convolve(noise, np.ones(k1) / k1, mode="same")
        c2 = noise - np.convolve(noise, np.ones(k2) / k2, mode="same")
        voiced = 0.8 * c1 + 0.2 * c2
        t = np.arange(m) / sr
        f0 = 110 + 25 * math.sin(i)
        voiced += 0.35 * np.sin(2 * np.pi * f0 * t).astype(np.float32)
        env = 0.55 + 0.45 * np.sin(2 * np.pi * 5.0 * t - np.pi / 2)
        edge = np.minimum(1, np.minimum(np.arange(m), np.arange(m)[::-1]) / (0.01 * sr))
        seg = voiced * env * edge
        seg = seg / (np.sqrt(np.mean(seg ** 2)) + 1e-9) * level
        out[a:b] += seg.astype(np.float32)
    return np.clip(out, -1, 1)


SENTENCE = ("so you're telling me um whatever I do you can do better uh yes I can "
            "prove it then okay watch this right now no way that actually worked").split()


def word_times(tokens, start=0.5, word_s=0.32, gap_s=0.06, pauses=None):
    """Assign start/end to tokens. pauses: {index_before_which: extra_gap_seconds} for dead air."""
    pauses = pauses or {}
    t, out = start, []
    for i, tok in enumerate(tokens):
        t += pauses.get(i, 0.0)
        dur = word_s * (0.45 if tok in ("um", "uh") else 1.0) * (0.8 + 0.4 * ((i * 37) % 10) / 10)
        out.append({"id": f"w{i}", "text": (" " if i else "") + tok, "start": round(t, 3), "end": round(t + dur, 3)})
        t += dur + gap_s
    return out


def podcast(dirpath, fps=60, size=(1280, 720), pauses=None, shots=None, audio_offset=0.0, name="podcast.mp4"):
    """A synthetic podcast source with a known transcript, known dead air and known cuts.

    Writes <dir>/<name>, <dir>/transcript.json ({'words': [...]}, source seconds) and <dir>/truth.json.
    """
    d = Path(dirpath)
    d.mkdir(parents=True, exist_ok=True)
    pauses = pauses if pauses is not None else {6: 0.9, 13: 1.4, 20: 0.5}
    words = word_times(SENTENCE, start=0.6, pauses=pauses)
    dur = words[-1]["end"] + 1.2
    fpsF = Fraction(fps)
    total = int(math.ceil(dur * fpsF))
    if shots is None:
        a = int(total * 0.35)
        b = int(total * 0.25)
        c = int(total * 0.15)
        shots = [("testsrc2", a), ("punch", c), ("hue", b), ("white", 2), ("testsrc2", total - a - b - c - 2)]
    track = talk_track(words, float(total / fpsF) + 0.5)
    if audio_offset:
        pad = np.zeros(int(round(audio_offset * 48000)), np.float32)
        track = np.concatenate([pad, track])
    info = shots_video(d / name, shots, fps=fps, size=size, audio=track)
    cl.write_json_atomic(d / "transcript.json", {"words": words})
    gaps = [{"after": words[i - 1]["id"], "before": words[i]["id"], "s": round(words[i]["start"] - words[i - 1]["end"], 3)}
            for i in range(1, len(words)) if words[i]["start"] - words[i - 1]["end"] > 0.3]
    truth = {"fps": cl.frac_str(fpsF), "frames": info["frames"], "cuts": info["cuts"],
             "shots": [[k, f] for k, f in shots], "dead_air": gaps,
             "fillers": [w["id"] for w in words if w["text"].strip() in ("um", "uh")],
             "audio_offset": audio_offset}
    cl.write_json_atomic(d / "truth.json", truth)
    return {"path": str(d / name), "words": words, "truth": truth}


def music_bed(path, dur=20.0, bpm=120, sr=48000, level=0.2, quiet_intro=0.0):
    """A loopable bed: chord pad + kick on every beat. quiet_intro seconds start 18 dB lower."""
    n = int(round(dur * sr))
    t = np.arange(n) / sr
    pad = sum(np.sin(2 * np.pi * f * t) for f in (110.0, 138.6, 164.8, 220.0)) / 4
    beat = 60.0 / bpm
    ph = (t % beat) / beat
    kick = np.sin(2 * np.pi * 55 * t) * np.exp(-ph * 18)
    x = (0.6 * pad + 0.8 * kick) * level
    if quiet_intro:
        x[: int(quiet_intro * sr)] *= 10 ** (-18 / 20)
    stereo = np.stack([x, x], axis=1).astype(np.float32)
    cl.write_wav_f32(path, stereo, sr)
    return {"path": str(path), "dur": dur, "bpm": bpm}


def sfx_file(path, kind="hit", sr=48000, peak_at=None, seed=3):
    """SFX with a known hit point. kind: hit (peak ~5 ms), whoosh (swell, peak at 60%), riser (crest at end).

    Returns {'path', 'peak_s'} where peak_s is where the 4 ms RMS envelope peaks (approximately).
    """
    rng = np.random.default_rng(seed)
    if kind == "hit":
        L = 0.6
        n = int(L * sr)
        t = np.arange(n) / sr
        x = (rng.standard_normal(n) * 0.5 + np.sin(2 * np.pi * 70 * t)) * np.exp(-t * 14)
        pk = 0.004
        x[: int(pk * sr)] *= np.linspace(0, 1, int(pk * sr))
    elif kind == "whoosh":
        L = 0.9
        n = int(L * sr)
        t = np.arange(n) / sr
        pk = peak_at or 0.55
        env = np.exp(-((t - pk) ** 2) / (2 * 0.12 ** 2))
        x = rng.standard_normal(n) * env
        x = np.convolve(x, np.ones(5) / 5, mode="same")
    elif kind == "riser":
        L = 2.0
        n = int(L * sr)
        t = np.arange(n) / sr
        pk = peak_at or 1.9
        env = np.clip(t / pk, 0, 1) ** 3 * np.exp(-np.clip(t - pk, 0, None) * 30)
        x = np.sin(2 * np.pi * (200 + 600 * t) * t) * env
    else:
        raise ValueError(kind)
    x = (x / (np.max(np.abs(x)) + 1e-9) * 0.7).astype(np.float32)
    stereo = np.stack([x, x], axis=1)
    cl.write_wav_f32(path, stereo, sr)
    env = np.sqrt(np.convolve(x.astype(np.float64) ** 2, np.ones(int(0.004 * sr)) / int(0.004 * sr), mode="same"))
    return {"path": str(path), "peak_s": float(np.argmax(env) / sr), "len_s": len(x) / sr}


if __name__ == "__main__":  # smoke test: python -P tests/fixtures.py <outdir>
    cl.utf8_stdio()
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "fixtures_out")
    p = podcast(out)
    print(json.dumps({"podcast": p["path"], "truth": p["truth"]}, indent=1))
    print(music_bed(out / "bed.wav"))
    for k in ("hit", "whoosh", "riser"):
        print(sfx_file(out / f"{k}.wav", k))
