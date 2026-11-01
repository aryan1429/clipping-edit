"""Tests for skill/scripts/find_music.py: a synthetic local library, mocked Openverse / Jamendo servers on
127.0.0.1 (no internet), the real CLI as a subprocess, and mix_audio.py run on the music.json it writes.

Run from the repo root:  python -P tests/test_find_music.py
One PASS/FAIL line per check; exit 0 only when every check passes.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixtures as fx  # noqa: E402

cl = fx.cl
SCRIPT = fx.ROOT / "skill" / "scripts" / "find_music.py"
MIX = fx.ROOT / "skill" / "scripts" / "mix_audio.py"
SR = 48000
DUR = 24.0
FAILED = []


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'} {name}" + (f"  [{detail}]" if detail else ""), flush=True)
    if not cond:
        FAILED.append(name)
    return bool(cond)


# ---------------------------------------------------------------- media

def bright_layer(n, bpm, seed=1, level=0.06):
    """Hats on every 8th note (noise above 5 kHz) + a mid chord stab (500-2000 Hz) per beat: keeps the low end
    under half the energy and gives the onset envelope something above the kick."""
    rng = np.random.default_rng(seed)
    t = np.arange(n) / SR
    beat = 60.0 / bpm
    ph8 = (t % (beat / 2)) / (beat / 2)
    noise = rng.standard_normal(n)
    hp = noise - np.convolve(noise, np.ones(4) / 4, mode="same")
    hats = hp * np.exp(-ph8 * 30)
    ph = (t % beat) / beat
    chord = sum(np.sin(2 * np.pi * f * t) for f in (523.3, 659.3, 784.0, 1046.5)) / 4 * np.exp(-ph * 4)
    return level * (1.2 * hats + 2.2 * chord)


def make_track(path, bpm, kind="normal", quiet_intro=0.0, seed=1):
    """kind: normal | bass (raw music_bed + a sub drone) | vocal (normal + speech-like bursts)."""
    raw = Path(str(path) + ".raw.wav")
    fx.music_bed(raw, dur=DUR, bpm=bpm, level=0.2)
    x = cl.decode_audio(raw, fx.ffmpeg(), sr=SR, channels=1, src_channels=2).astype(np.float64)
    os.remove(raw)
    n = len(x)
    t = np.arange(n) / SR
    if kind == "bass":
        x = x + 0.25 * np.sin(2 * np.pi * 45 * t)
    else:
        x = x + bright_layer(n, bpm, seed)
    if kind == "vocal":
        rng = np.random.default_rng(seed + 100)  # irregular words and pauses, like real singing or rap
        words, tw = [], 0.4
        while tw < DUR - 0.8:
            d = float(rng.uniform(0.12, 0.5))
            words.append({"start": tw, "end": tw + d})
            tw += d + float(rng.choice([rng.uniform(0.03, 0.15), rng.uniform(0.3, 0.9)], p=[0.8, 0.2]))
        x = x + fx.talk_track(words, DUR, SR, seed=seed, level=0.12)[:n]
    if quiet_intro:
        x[: int(quiet_intro * SR)] *= 10 ** (-18 / 20)
    x = x / max(1e-9, np.max(np.abs(x))) * 0.7
    cl.write_wav_f32(path, np.stack([x, x], 1).astype(np.float32), SR)


LIB = {  # file: (bpm, kind, quiet_intro, manifest entry or None)
    "neon_rush_140.wav": (140, "normal", 0.0, {"title": "Neon Rush", "artist": "Test Artist A",
                                               "source_url": "https://example.org/neon-rush", "licence": "CC0 1.0",
                                               "tags": ["phonk", "trap", "instrumental"]}),
    "slow_morning_92.wav": (92, "normal", 0.0, {"title": "Slow Morning", "artist": "Test Artist B",
                                                "source_url": "https://example.org/slow-morning",
                                                "licence": "CC BY 4.0",
                                                "attribution": "Slow Morning Test Artist B (example.org)\nLicensed "
                                                               "under Creative Commons: By Attribution 4.0\n"
                                                               "https://creativecommons.org/licenses/by/4.0/"}),
    "late_start_140.wav": (140, "normal", 6.0, {"title": "Late Start", "artist": "Test Artist C",
                                                "source_url": "https://example.org/late-start",
                                                "licence": "Pixabay Content License (royalty-free, no attribution)"}),
    "sub_quake_140.wav": (140, "bass", 0.0, {"title": "Sub Quake", "artist": "Test Artist D",
                                             "source_url": "https://example.org/sub-quake",
                                             "licence": "YouTube Audio Library (attribution not required)"}),
    "talk_over_140.wav": (140, "vocal", 0.0, {"title": "Talk Over", "artist": "Test Artist E",
                                              "source_url": "https://example.org/talk-over", "licence": "CC0"}),
    "no_papers_128.wav": (128, "normal", 0.0, None),
    "nc_local_140.wav": (140, "normal", 0.0, {"title": "NC Local", "artist": "Test Artist F",
                                              "source_url": "https://example.org/nc", "licence": "CC BY-NC 4.0"}),
}


def build_library(root):
    root.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for i, (name, (bpm, kind, qi, entry)) in enumerate(LIB.items()):
        make_track(root / name, bpm, kind, qi, seed=i + 1)
        if entry:
            manifest[name] = dict(entry, notes="synthetic test track")
    cl.write_json_atomic(root / "licences.json", manifest)


# ---------------------------------------------------------------- mock servers

def ov_item(i, title, lic, ver, file, genres=("electronic",), tags=("trap",)):
    lic_url = (f"https://creativecommons.org/licenses/{lic}/{ver}/" if lic.startswith("by") else
               "https://creativecommons.org/publicdomain/zero/1.0/" if lic == "cc0" else None)
    return {"id": f"ov-{i:04d}", "title": title, "indexed_on": "2024-01-01T00:00:00Z",
            "foreign_landing_url": f"https://example.org/ov/{i}", "url": f"{{BASE}}/files/{file}",
            "creator": f"OV Creator {i}", "creator_url": None, "license": lic, "license_version": ver,
            "license_url": lic_url, "provider": "jamendo", "source": "jamendo", "category": "music",
            "genres": list(genres), "filesize": 1000, "filetype": "wav",
            "tags": [{"name": t, "accuracy": None} for t in tags], "alt_files": None,
            "attribution": f'"{title}" by OV Creator {i} is licensed under {lic.upper()} {ver}.',
            "fields_matched": ["title"], "mature": False, "audio_set": None, "duration": int(DUR * 1000),
            "bit_rate": None, "sample_rate": 48000, "thumbnail": None, "detail_url": "", "related_url": "",
            "waveform": ""}


def openverse_page():
    items = [ov_item(1, "Open Drift", "by", "4.0", "ov_by_120.wav", genres=("hip-hop",), tags=("phonk", "trap")),
             ov_item(2, "Public Pulse", "cc0", "1.0", "ov_cc0_150.wav"),
             ov_item(3, "Shop Only", "by-nc", "4.0", "ov_by_120.wav"),
             ov_item(4, "Do Not Touch", "by-nd", "4.0", "ov_by_120.wav"),
             ov_item(5, "Share Me", "by-sa", "4.0", "ov_by_120.wav"),
             ov_item(6, "Triple Lock", "by-nc-sa", "3.0", "ov_by_120.wav"),
             ov_item(7, "Sample Bits", "sampling+", "1.0", "ov_by_120.wav")]
    return {"result_count": len(items), "page_count": 1, "page_size": 20, "page": 1, "results": items}


def jamendo_page():
    def tr(i, name, ccurl, file, vi="instrumental"):
        return {"id": str(9000 + i), "name": name, "duration": int(DUR), "artist_id": "1", "artist_name": f"JM {i}",
                "artist_idstr": "jm", "album_name": "", "album_id": "", "album_image": "",
                "license_ccurl": ccurl, "position": 1, "releasedate": "2020-01-01",
                "audio": f"{{BASE}}/files/{file}", "audiodownload": f"{{BASE}}/files/{file}",
                "audiodownload_allowed": True, "prourl": "", "shorturl": f"https://jamen.do/t/{9000 + i}",
                "shareurl": f"https://www.jamendo.com/track/{9000 + i}", "waveform": "{}", "image": "",
                "musicinfo": {"vocalinstrumental": vi, "lang": "", "gender": "", "acousticelectric": "electric",
                              "speed": "high", "tags": {"genres": ["hiphop", "electronic"], "instruments": ["synth"],
                                                        "vartags": ["energetic"]}},
                "content_id_free": False}
    res = [tr(1, "Jam Free", "http://creativecommons.org/licenses/by/3.0/", "jm_by_135.wav"),
           tr(2, "Jam NC SA", "http://creativecommons.org/licenses/by-nc-sa/3.0/", "jm_by_135.wav"),
           tr(3, "Jam ND", "http://creativecommons.org/licenses/by-nd/3.0/", "jm_by_135.wav")]
    return {"headers": {"status": "success", "code": 0, "error_message": "", "warnings": "",
                        "results_count": len(res)}, "results": res}


class Mock:
    mode = "ok"            # ok | 504 | slow
    files = {}
    hits = {}
    lock = threading.Lock()
    base = ""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        p = urllib.parse.urlsplit(self.path)
        with Mock.lock:
            Mock.hits[p.path] = Mock.hits.get(p.path, 0) + 1
        try:
            if p.path.startswith("/ov/"):
                if Mock.mode == "504" or (Mock.mode == "filtered504" and "license=" in p.query):
                    return self._send(504, b"error code: 504", "text/plain")
                if Mock.mode == "slow":
                    time.sleep(2.5)
                body = json.dumps(openverse_page()).replace("{BASE}", Mock.base).encode()
                return self._send(200, body)
            if p.path.startswith("/jm/"):
                q = urllib.parse.parse_qs(p.query)
                Mock.jm_query = q
                if q.get("client_id") != ["test-key"]:
                    return self._send(200, json.dumps({"headers": {"status": "failed", "code": 5,
                                                                   "error_message": "bad client id"},
                                                       "results": []}).encode())
                return self._send(200, json.dumps(jamendo_page()).replace("{BASE}", Mock.base).encode())
            if p.path.startswith("/files/"):
                f = Mock.files.get(p.path[len("/files/"):])
                if f:
                    return self._send(200, Path(f).read_bytes(), "audio/wav")
            return self._send(404, b"not found", "text/plain")
        except (ConnectionError, OSError):
            pass


# ---------------------------------------------------------------- CLI

def run(args, env_extra=None):
    env = dict(os.environ)
    env.pop("JAMENDO_CLIENT_ID", None)
    env.update(env_extra or {})
    cp = subprocess.run([sys.executable, "-P", str(SCRIPT)] + [str(a) for a in args], capture_output=True,
                        env=env)
    out = cp.stdout.decode("utf-8", errors="replace")
    try:
        j = json.loads(out)
    except ValueError:
        j = None
        print(out[-2000:], cp.stderr.decode("utf-8", errors="replace")[-3000:])
    return cp.returncode, j, cp.stderr.decode("utf-8", errors="replace")


def by_title(j, title):
    for c in (j or {}).get("candidates", []) + (j or {}).get("unverified", []):
        if c["title"] == title:
            return c
    return None


def tempo_ok(est, true):
    for mult in (1.0, 2.0, 0.5):
        if est and abs(est - true * mult) <= 0.03 * true * mult:
            return mult
    return None


# ---------------------------------------------------------------- cases

def case_local(work, lib, cache):
    code, j, err = run(["--mood", "hype", "--clip-s", 20, "--library", lib, "--offline", "--top", 10,
                        "--cache-dir", cache])
    check("local: exit 0 with JSON", code == 0 and j and j["ok"], f"exit {code}")
    if not j:
        return None
    cands = j["candidates"]
    titles = [c["title"] for c in cands]
    check("local: hype ranks the 140 BPM instrumental first", titles[:1] == ["Neon Rush"], str(titles))
    for name, (bpm, kind, qi, entry) in LIB.items():
        title = entry["title"] if entry else Path(name).stem
        c = by_title(j, title)
        if not c:
            check(f"tempo {title}: present", False)
            continue
        est = c["features"]["bpm_raw"]
        mult = tempo_ok(est, bpm)
        check(f"tempo {title}: {est} within 3% of {bpm} (or half/double)", mult is not None,
              f"octave x{mult}" if mult and mult != 1.0 else "")
    neon = by_title(j, "Neon Rush")
    slow = by_title(j, "Slow Morning")
    check("tempo flag: 92 BPM counted outside the hype range", slow and slow["features"]["bpm"] not in
          (None,) and not 130 <= slow["features"]["bpm"] <= 160 and slow["score_parts"]["tempo"] < 40,
          str(slow and slow["features"]["bpm"]))
    late = by_title(j, "Late Start")
    off = late and late["features"]["entry_offset_s"]
    check("entry offset skips the 6 s quiet intro", late and 5.0 <= off <= 7.5, f"offset {off}")
    check("intro quiet length measured ~6 s", late and 5.4 <= late["features"]["intro_quiet_s"] <= 6.6,
          str(late and late["features"]["intro_quiet_s"]))
    check("quiet intro penalised", late and late["score_parts"]["quiet_intro"] < 0)
    check("no quiet intro on Neon Rush", neon and neon["features"]["entry_offset_s"] <= 1.0
          and neon["features"]["intro_quiet_s"] == 0, str(neon and neon["features"]["entry_offset_s"]))
    sub = by_title(j, "Sub Quake")
    check("bass-heavy track warned", sub and sub["features"]["low_share"] > 0.5
          and any(w.startswith("low_end_heavy") for w in sub["warnings"]), str(sub and sub["features"]["low_share"]))
    check("bass-heavy track penalised", sub and sub["score_parts"]["low_end"] < 0)
    check("normal tracks not warned for low end", neon and neon["features"]["low_share"] <= 0.5
          and not neon["warnings"], str(neon and neon["features"]["low_share"]))
    voc = by_title(j, "Talk Over")
    check("vocal track: audio heuristic flags vocals", voc and voc["features"]["vocal_source"] == "audio"
          and voc["features"]["vocal_score"] >= 0.5, str(voc and voc["features"]["vocal_score"]))
    others = [c["features"]["vocal_score"] for c in cands if c["title"] in ("Late Start", "Sub Quake")]
    check("instrumentals score low on vocals", others and max(others) <= 0.35, str(others))
    check("vocal track penalised and ranked below Neon Rush", voc and voc["score_parts"]["vocals"] <= -12
          and voc["score"] < neon["score"], f"{voc and voc['score']} vs {neon and neon['score']}")
    check("tags win: Neon Rush vocal source = tags", neon and neon["features"]["vocal_source"] == "tags")
    unv = [c["title"] for c in j["unverified"]]
    check("no manifest entry -> unverified, never a candidate", "no_papers_128" in unv
          and "no_papers_128" not in titles, str(unv))
    check("local NC licence -> not a candidate", "NC Local" in unv and "NC Local" not in titles)
    check("CC BY local: credit required, uses manifest attribution", slow and slow["licence"]["credit_required"]
          and slow["attribution"].startswith("Slow Morning Test Artist B") and slow["score_parts"]["credit"] < 0)
    check("Pixabay / YTAL royalty-free: no credit needed", late and late["licence"]["code"] == "royalty-free"
          and not late["licence"]["credit_required"] and sub["licence"]["code"] == "royalty-free")
    for c in cands:
        lic = c["licence"]
        if not (lic.get("name") and "credit_required" in lic and c.get("attribution")):
            check(f"licence block complete: {c['title']}", False, json.dumps(lic))
            break
    else:
        check("every candidate has a licence block and an attribution line", True)
    check("loop note: 24 s track vs 20 s clip, no loop", neon and not neon["features"]["loop_needed"])
    return j


def case_loop_and_dialogue(work, lib, cache, dlg):
    code, j, _ = run(["--mood", "hype", "--clip-s", 45, "--library", lib, "--offline", "--cache-dir", cache,
                      "--dialogue", dlg])
    neon = by_title(j, "Neon Rush")
    check("45 s clip: loop needed noted and penalised", neon and neon["features"]["loop_needed"]
          and neon["score_parts"]["loop"] < 0 and any("loops" in r for r in neon["reasons"]))
    clash = neon and neon["features"]["dialogue_clash"]
    check("--dialogue: clash measured in [0, 1]", clash is not None and 0 <= clash <= 1, str(clash))
    voc = by_title(j, "Talk Over")
    check("--dialogue: the vocal track clashes more than Sub Quake",
          voc and by_title(j, "Sub Quake") and voc["features"]["dialogue_clash"]
          > by_title(j, "Sub Quake")["features"]["dialogue_clash"],
          f"{voc and voc['features']['dialogue_clash']} vs "
          f"{by_title(j, 'Sub Quake') and by_title(j, 'Sub Quake')['features']['dialogue_clash']}")
    code, j2, _ = run(["--mood", "chill", "--clip-s", 20, "--library", lib, "--offline", "--cache-dir", cache])
    check("mood chill ranks the 92 BPM track first", j2 and j2["candidates"][0]["title"] == "Slow Morning",
          str(j2 and [c["title"] for c in j2["candidates"]]))
    code, j3, _ = run(["--mood", "hype", "--bpm", "85-100", "--clip-s", 20, "--library", lib, "--offline",
                       "--cache-dir", cache])
    check("--bpm override moves the tempo range", j3 and j3["profile"]["bpm"] == [85.0, 100.0]
          and j3["candidates"][0]["title"] == "Slow Morning", str(j3 and j3["candidates"][0]["title"]))


def case_remote(work, lib, cache, port):
    base = f"http://127.0.0.1:{port}"
    Mock.mode = "ok"
    args = ["--mood", "hype", "--clip-s", 20, "--library", lib, "--cache-dir", cache, "--top", 12,
            "--openverse-api", f"{base}/ov/v1/audio/", "--jamendo-api", f"{base}/jm/v3.0/tracks/",
            "--timeout", 2, "--retry-backoff", 0.2]
    code, j, err = run(args, {"JAMENDO_CLIENT_ID": "test-key"})
    check("remote: exit 0", code == 0 and j is not None, f"exit {code}")
    if not j:
        return
    titles = [c["title"] for c in j["candidates"]]
    rej = {r["title"]: r["why"] for r in j["rejected"]}
    check("openverse: CC BY and CC0 tracks are candidates", "Open Drift" in titles and "Public Pulse" in titles,
          str(titles))
    for t, part in (("Shop Only", "NC"), ("Do Not Touch", "ND"), ("Share Me", "SA"), ("Triple Lock", "NC"),
                    ("Sample Bits", "Sampling"), ("Jam NC SA", "SA"), ("Jam ND", "ND")):
        check(f"rejected {t} ({part})", t in rej and t not in titles and part in rej[t], rej.get(t))
    check("jamendo: CC BY 3.0 track accepted", "Jam Free" in titles)
    od = by_title(j, "Open Drift")
    check("openverse licence block: CC BY 4.0, url, credit", od and od["licence"]["name"] == "CC BY 4.0"
          and od["licence"]["url"] == "https://creativecommons.org/licenses/by/4.0/"
          and od["licence"]["credit_required"] and od["source_url"] == "https://example.org/ov/1")
    check("attribution line names title, creator, landing URL and licence", od and od["attribution"] ==
          'Music: "Open Drift" by OV Creator 1 (https://example.org/ov/1), licensed under CC BY 4.0 '
          '(https://creativecommons.org/licenses/by/4.0/)', od and od["attribution"])
    pp = by_title(j, "Public Pulse")
    check("tempo of the remote 150 BPM track", pp and tempo_ok(pp["features"]["bpm_raw"], 150) is not None,
          str(pp and pp["features"]["bpm_raw"]))
    q = getattr(Mock, "jm_query", {})
    check("jamendo request parameters", q.get("vocalinstrumental") == ["instrumental"]
          and q.get("include") == ["licenses musicinfo"] and q.get("audioformat") == ["mp32"]
          and q.get("speed") == ["high veryhigh"] and "phonk" in q.get("fuzzytags", [""])[0], str(q))
    blob = json.dumps(j) + err
    check("the Jamendo key never reaches the output", "test-key" not in blob)
    cached = list((Path(cache) / "api").rglob("*.json"))
    check("API responses cached on disk without the key", cached and all(
        "test-key" not in p.read_text(encoding="utf-8") for p in cached), str(len(cached)))
    hits_before = dict(Mock.hits)
    code, j2, _ = run(args, {"JAMENDO_CLIENT_ID": "test-key"})
    new_hits = {k: v - hits_before.get(k, 0) for k, v in Mock.hits.items() if v - hits_before.get(k, 0)}
    check("second run: API and downloads served from the cache", code == 0 and not new_hits, str(new_hits))


def case_down(work, lib, port):
    base = f"http://127.0.0.1:{port}"
    for mode in ("504", "slow"):
        Mock.mode = mode
        cache = work / f"cache_{mode}"
        t0 = time.time()
        code, j, err = run(["--mood", "hype", "--clip-s", 20, "--library", lib, "--cache-dir", cache,
                            "--openverse-api", f"{base}/ov/v1/audio/", "--providers", "local,openverse",
                            "--timeout", 1, "--retry-backoff", 0.2])
        dt = time.time() - t0
        w = (j or {}).get("warnings", [])
        check(f"openverse {mode}: exit 0, warning, local results kept", code == 0 and j and
              j["providers"]["openverse"]["status"] == "down" and any(x.startswith("openverse_down") for x in w)
              and j["candidates"] and j["candidates"][0]["provider"] == "local", f"exit {code}, {w}")
        check(f"openverse {mode}: one retry, then the provider is skipped", Mock.hits.get("/ov/v1/audio/", 0) >= 2
              and dt < 40, f"{dt:.1f} s")
        Mock.hits.clear()
    # filtered search down, plain q= search up (the live state on 2026-11-01): licence filter applied locally
    Mock.mode = "filtered504"
    code, j, _ = run(["--mood", "hype", "--clip-s", 20, "--cache-dir", work / "cache_plain", "--providers",
                      "openverse", "--openverse-api", f"{base}/ov/v1/audio/", "--timeout", 1, "--retry-backoff", 0.1])
    titles = [c["title"] for c in (j or {}).get("candidates", [])]
    rej = [r["title"] for r in (j or {}).get("rejected", [])]
    check("filtered search down -> plain search, licence policy applied locally", code == 0 and j and
          any(x.startswith("openverse_filtered_down") for x in j["warnings"]) and "Open Drift" in titles
          and "Share Me" in rej and "Shop Only" in rej and "Share Me" not in titles, f"{titles} / {rej}")
    Mock.hits.clear()
    # stale cache: a good response cached, then the API goes down and the TTL has passed
    Mock.mode = "ok"
    cache = work / "cache_stale"
    args = ["--mood", "hype", "--clip-s", 20, "--cache-dir", cache, "--providers", "openverse",
            "--openverse-api", f"{base}/ov/v1/audio/", "--timeout", 1, "--retry-backoff", 0.1]
    run(args)
    for p in (cache / "api").rglob("*.json"):
        d = json.loads(p.read_text(encoding="utf-8"))
        d["fetched_epoch"] -= 3 * 86400
        p.write_text(json.dumps(d), encoding="utf-8")
    Mock.mode = "504"
    code, j, _ = run(args)
    check("openverse down + stale cache: cached results used with a warning", code == 0 and j and
          any(x.startswith("openverse_stale_cache") for x in j["warnings"]) and by_title(j, "Open Drift"))
    Mock.mode = "ok"


def case_none_licensed(work, port):
    base = f"http://127.0.0.1:{port}"
    lib = work / "badlib"
    lib.mkdir()
    shutil.copy(work / "lib" / "no_papers_128.wav", lib / "mystery.wav")
    Mock.mode = "504"
    code, j, _ = run(["--mood", "hype", "--clip-s", 20, "--library", lib, "--cache-dir", work / "cache_none",
                      "--openverse-api", f"{base}/ov/v1/audio/", "--timeout", 1, "--retry-backoff", 0.1])
    Mock.mode = "ok"
    hints = " ".join((j or {}).get("hints", []))
    check("no licensed candidate -> exit 1 with hints", code == 1 and j and j["ok"] is False
          and j["error"]["code"] == "no_licensed_candidate" and "JAMENDO_CLIENT_ID" in hints
          and "licences.json" in hints and "Openverse" in hints, f"exit {code}")
    check("unverified local track still listed", j and [c["title"] for c in j["unverified"]] == ["mystery"])
    code, j, _ = run(["--mood", "angry"])
    check("usage error -> exit 2", code == 2 and j and j["error"]["code"] == "usage")
    code, j, _ = run(["--mood", "hype", "--choose", "--offline"])
    check("--choose without --out-dir -> exit 2", code == 2)


def case_pick_and_mix(work, lib, cache):
    out = work / "clip01"
    code, j, _ = run(["--mood", "hype", "--clip-s", 12, "--library", lib, "--offline", "--cache-dir", cache,
                      "--pick", 2, "--out-dir", out])
    mj = out / "music.json"
    check("--pick 2: exit 0 and music.json written", code == 0 and mj.is_file(), f"exit {code}")
    if not mj.is_file():
        return
    m = json.loads(mj.read_text(encoding="utf-8"))
    want = j["candidates"][1]
    check("music.json fields", all(k in m for k in ("path", "offset_s", "lufs_target", "licence", "attribution",
                                                     "source_url", "retrieved_at", "bed"))
          and m["lufs_target"] == -20.0 and m["title"] == want["title"] and Path(m["path"]).is_file()
          and Path(m["path"]).name == "bed.wav", json.dumps({k: m.get(k) for k in ("path", "title")}))
    check("retrieved_at is a UTC date", len(m["retrieved_at"]) == 10 and m["retrieved_at"][4] == "-")
    check("the picked bed (Late Start) enters after its quiet intro", m["title"] == "Late Start"
          and m["offset_s"] >= 5.0, f"{m['title']} {m['offset_s']}")
    # mix_audio.py on the bed block: synthetic dialogue + plan
    fps, frames = 30, 12 * 30
    n = frames * SR // fps
    words = fx.word_times(fx.SENTENCE, start=0.3)
    words = [w for w in words if w["end"] < 11.5]
    cl.write_wav_f32(out / "dialogue.wav", fx.talk_track(words, n / SR)[:n].astype(np.float32))
    plan = {"fps": "30/1", "frames": frames, "dialogue": (out / "dialogue.wav").as_posix(),
            "words": [[w["start"], w["end"]] for w in words], "bed": m["bed"]}
    cl.write_json_atomic(out / "audio_plan.json", plan)
    cp = subprocess.run([sys.executable, "-P", str(MIX), "--plan", str(out / "audio_plan.json"),
                         "--outdir", str(out / "mix")], capture_output=True)
    try:
        rep = json.loads(cp.stdout.decode("utf-8", errors="replace"))
    except ValueError:
        rep = {}
        print(cp.stderr.decode("utf-8", errors="replace")[-2000:])
    bed = rep.get("bed") or (rep.get("levels") or {}).get("bed") or {}
    check("mix_audio.py accepts music.json's bed block (exit 0)", cp.returncode == 0,
          f"exit {cp.returncode}, failed {rep.get('failed')}")
    check("mix_audio.py used the offset from music.json", bed.get("offset_s") == m["offset_s"]
          and bed.get("offset_auto") is False, json.dumps(bed)[:200])
    check("mix_audio.py report has no unknown-key warnings for the bed",
          not any("bed." in w for w in rep.get("warnings", [])), str(rep.get("warnings")))
    # find_music's offset equals mix_audio's own automatic choice on the same file
    plan["bed"] = {"path": m["path"], "offset_s": None}
    cl.write_json_atomic(out / "audio_plan_auto.json", plan)
    cp = subprocess.run([sys.executable, "-P", str(MIX), "--plan", str(out / "audio_plan_auto.json"),
                         "--outdir", str(out / "mix_auto")], capture_output=True)
    try:
        rep2 = json.loads(cp.stdout.decode("utf-8", errors="replace"))
    except ValueError:
        rep2 = {}
    bed2 = rep2.get("bed") or (rep2.get("levels") or {}).get("bed") or {}
    check("entry offset matches mix_audio.py's automatic rule", bed2.get("offset_s") == m["offset_s"],
          f"{bed2.get('offset_s')} vs {m['offset_s']}")
    code, j, _ = run(["--mood", "hype", "--clip-s", 12, "--library", lib, "--offline", "--cache-dir", cache,
                      "--choose", "--out-dir", out])
    m = json.loads(mj.read_text(encoding="utf-8"))
    check("--choose picks the best (Neon Rush)", code == 0 and m["title"] == "Neon Rush")


def main():
    work = Path(tempfile.mkdtemp(prefix="test_find_music-"))
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    srv.daemon_threads = True
    port = srv.server_address[1]
    Mock.base = f"http://127.0.0.1:{port}"
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        lib = work / "lib"
        build_library(lib)
        files = work / "files"
        files.mkdir()
        make_track(files / "ov_by_120.wav", 120, seed=11)
        make_track(files / "ov_cc0_150.wav", 150, seed=12)
        make_track(files / "jm_by_135.wav", 135, seed=13)
        Mock.files = {p.name: str(p) for p in files.iterdir()}
        words = fx.word_times(fx.SENTENCE, start=0.3)
        cl.write_wav_f32(work / "dlg.wav", fx.talk_track(words, 20.0))
        cache = work / "cache"
        case_local(work, lib, cache)
        case_loop_and_dialogue(work, lib, cache, work / "dlg.wav")
        case_remote(work, lib, work / "cache_remote", port)
        case_down(work, lib, port)
        case_none_licensed(work, port)
        case_pick_and_mix(work, lib, cache)
    finally:
        srv.shutdown()
        try:
            shutil.rmtree(work)
        except OSError as e:
            print(f"note: could not remove {work}: {e}")
    print("ALL PASS" if not FAILED else f"{len(FAILED)} FAILED: " + "; ".join(FAILED))
    return 0 if not FAILED else 1


if __name__ == "__main__":
    cl.utf8_stdio()
    sys.exit(main())
