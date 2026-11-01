"""Find a licence-safe background-music bed for one short: target profile from the mood, candidates from a local
library, Openverse and Jamendo, licence policy, audio fit analysis, ranking, and an optional pick that writes the
bed and music.json for mix_audio.py (ref 06; bed levels and entry rule from ref 01 section 6).

usage:
  python -P find_music.py --mood hype --clip-s 45 [--bpm 130-160] [--dialogue clips/NN/dialogue.wav]
         [--library music/] [--providers local,openverse,jamendo] [--offline] [--query "dark phonk"]
         [--top 5] [--allow by-sa,...] [--pick K | --choose] [--out-dir clips/NN] [--cache-dir DIR]
         [--timeout 20] [--retry-backoff 3] [--max-analyse 10] [--ffmpeg PATH] [--ffprobe PATH|none]
         [--openverse-api URL] [--jamendo-api URL]

inputs:
  --mood        hype | tense | funny | emotional | chill | epic | inspiring (the LLM picks it from the transcript)
  --bpm         "LO-HI" overrides the mood's tempo range (half and double time still count, flagged)
  --clip-s      the clip's length in seconds (default 45): sets the analysis window and the loop check
  --dialogue    the clip's dialogue stem; adds the spectral clash with the speech band to the score
  --library     a folder of downloaded tracks (repeatable). Its licences.json manifest:
                  {"<file name or relative path>": {"title", "artist", "source_url", "licence", "attribution",
                   "notes", optional "licence_url", "tags": [...], "retrieved": "YYYY-MM-DD"}}
                Tracks without an entry are analysed and listed under "unverified", never picked.
  --providers   comma list of local, openverse, jamendo (default all; each one is skipped when unavailable).
                jamendo needs the env var JAMENDO_CLIENT_ID (a free key from devportal.jamendo.com).
  --allow       licence codes to accept beyond the default policy, e.g. "by-sa" or "custom" (see Licence policy)
  --pick K      download / copy candidate K (1-based) to --out-dir as bed.<ext> and write music.json
  --choose      the same for the best candidate
  --openverse-api, --jamendo-api   base URLs for a mirror or a test server

providers (results merged, deduplicated by title + creator):
  local      every audio file under --library; licence from the manifest.
  openverse  GET https://api.openverse.org/v1/audio/?q=..&category=music&license=cc0,by&mature=false&page_size=20
             (no key). One query per preferred genre term (max 3). Timeout --timeout s, 1 retry after
             --retry-backoff s. When the filtered search fails, one plain ?q=..&page_size=20 search (no retry) is
             tried and filtered here by category, licence and mature (on 2026-11-01 filtered searches timed out
             while plain ones answered). A query that fails both ways marks the provider down for this run.
             Responses are cached on disk by query (24 h); when the API is down a stale cache entry is used with
             a warning.
  jamendo    GET https://api.jamendo.com/v3.0/tracks/?client_id=..&format=json&limit=20
             &vocalinstrumental=instrumental&speed=..&fuzzytags=..&include=licenses+musicinfo&audioformat=mp32
             only when JAMENDO_CLIENT_ID is set. The licence comes from license_ccurl. The key never reaches the
             cache file names, the cached JSON or the output.

licence policy (default; --allow adds codes):
  accept  cc0, pdm (public domain mark), by (CC BY: credit required), and local manifest licences that say
          royalty-free / no attribution / attribution not required / Pixabay Content License / YouTube Audio
          Library (code "royalty-free"; credit required when the text says "credit" or "attribution required").
  reject  every NC (non-commercial: shorts are monetised), ND and SA licence, sampling+ / nc-sampling+, and
          unknown text (code "custom"). CC 4.0 legal code section 1(a): "where the Licensed Material is a musical
          work, performance, or sound recording, Adapted Material is always produced where the Licensed Material
          is synched in timed relation with a moving image" (CC 3.0 says the same of "synching"). So BY-ND forbids
          sharing the short, and BY-SA would put the whole short under BY-SA.
  local files without a manifest entry: code "unknown", listed, never picked.

fit analysis (numpy + ffmpeg; downloads and features are cached under --cache-dir):
  tempo         onset envelope = positive log-spectral flux (11025 Hz, 512-point FFT, hop 64 = 172 frames/s),
                minus a 0.5 s moving mean; autocorrelation scored at lags k * L (k = 1..4, weights 1, 1/2, 1/3,
                1/4) for 50-220 BPM in 0.1 steps, times a log-normal prior (120 BPM, 1 octave). The effective BPM
                is the raw value, x2 or x0.5, whichever lands in (or nearest) the mood range; the octave is flagged.
  loudness      integrated LUFS via cliplib.ebur128.
  entry_offset  mix_audio.py's rule: the earliest time whose next 5 s reach the 75th percentile of all 5 s
                windows' mean short-term loudness (ebur128 framelog, 0.1 s steps). music.json carries it.
  intro_quiet   the first 0.2 s window within 9 dB of the 75th-percentile window level.
  low_share     share of the energy at 20-150 Hz over the used window (entry .. entry + clip): warn above 0.50
                (phone speakers lose it; mix_audio.py warns at the same level).
  vocals        tags win (instrumental -> 0, vocal / rap / lyrics / singing -> 1). Otherwise 0.5 * the
                300-3400 Hz energy share term + 0.5 * the irregularity of that band's envelope (1 - its best
                autocorrelation near a 4-beat or 8-beat lag: loops repeat, voices do not).
  clash         with --dialogue: the share of the bed's energy inside the 1/3-octave bands that hold 80% of the
                dialogue's energy (speech frames only).
  energy        0.6 * min(onset peaks per s / 4, 1) + 0.4 * min(spectral centroid / 3000 Hz, 1).
  length        usable = duration - entry_offset; loop_needed when usable < clip_s (mix_audio.py loops it with
                a 0.3 s crossfade: fine, but noted).

score (0-100; weights):
  + tempo fit 40      1 inside the range, falling linearly to 0 at 15% outside
  + tag fit 25        0.5 + 0.25 per preferred tag/genre hit (max 2) - 0.25 per avoided hit (max 2); no tags 0.5
  + energy fit 15     1 - |energy - mood target| / 0.5
  + beat clarity 10   tempo confidence (best lag score over the median, mapped 1.0 -> 0, 3.0 -> 1)
  + length fit 10     min(usable / clip_s, 1)
  - vocals            25 x vocal score
  - quiet intro       1 per second of quiet intro, max 8 (the entry offset skips it, but it marks a slow build)
  - low end           50 x (low_share - 0.5) when above 0.5, max 15
  - dialogue clash    15 x clash (only with --dialogue)
  - credit required   3
  - loop needed       4

outputs:
  stdout  one JSON object: profile, providers (status, counts, warnings), candidates (top N, ranked: score,
          score_parts, features, reasons, warnings, licence block, attribution), unverified, rejected, picked,
          music_json, warnings, hints, log.
  --out-dir/bed.<ext> and --out-dir/music.json with --pick / --choose:
          {"path", "offset_s", "lufs_target": -20.0, "bed": {"path", "offset_s", "lufs"} (paste into
           audio_plan.json), "licence": {...}, "attribution", "credit_required", "title", "creator",
           "source_url", "provider", "retrieved_at" (UTC date), "licence_proof": {...}}

exit codes: 0 at least one candidate passes the licence policy (and the pick, if asked, was written);
  1 none passes (the JSON carries hints) or the picked download failed; 2 usage error or unreadable input.
"""
import argparse
import hashlib
import json
import math
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cliplib as cl  # noqa: E402

SCRIPT_VERSION = "1.0.0"
ANALYSIS_VERSION = 1        # bump when a feature's definition changes (invalidates the feature cache)

OPENVERSE_API = "https://api.openverse.org/v1/audio/"
JAMENDO_API = "https://api.jamendo.com/v3.0/tracks/"
USER_AGENT = f"clipping-edit-find_music/{SCRIPT_VERSION} (+https://github.com/aryan1429/clipping-edit)"
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".flac"}
MANIFEST = "licences.json"
JSON_TTL_S = 24 * 3600
MAX_DOWNLOAD = 60 * 1024 * 1024
MIN_TRACK_S = 15.0

# Mood table: tempo range, energy target (0-1), preferred and avoided tags/genres, Openverse queries, Jamendo speed.
MOODS = {
    "hype": {"bpm": (130, 160), "energy": 0.75,
             "prefer": ["phonk", "trap", "hip-hop", "hiphop", "hip hop", "electronic", "edm", "drill", "bass",
                        "hype", "energetic", "aggressive", "workout", "dubstep"],
             "avoid": ["ambient", "piano", "acoustic", "lullaby", "sad", "calm", "classical", "folk", "meditation"],
             "queries": ["phonk", "trap", "hip hop beat"], "speed": "high+veryhigh",
             "fuzzytags": "phonk+trap+hiphop+electronic"},
    "tense": {"bpm": (85, 120), "energy": 0.5,
              "prefer": ["dark", "suspense", "tension", "cinematic", "drone", "thriller", "horror", "ominous"],
              "avoid": ["happy", "upbeat", "comedy", "ukulele", "romantic"],
              "queries": ["dark suspense", "tension cinematic", "dark trap"], "speed": "medium+high",
              "fuzzytags": "dark+suspense+cinematic+soundtrack"},
    "funny": {"bpm": (100, 130), "energy": 0.55,
              "prefer": ["funny", "comedy", "quirky", "playful", "ukulele", "cartoon", "funk", "bouncy"],
              "avoid": ["dark", "sad", "aggressive", "horror", "epic"],
              "queries": ["funny quirky", "comedy", "playful"], "speed": "medium+high",
              "fuzzytags": "funny+comedy+quirky+funk"},
    "emotional": {"bpm": (60, 90), "energy": 0.25,
                  "prefer": ["emotional", "sad", "piano", "strings", "melancholic", "lofi", "ambient", "cinematic"],
                  "avoid": ["aggressive", "phonk", "trap", "metal", "comedy", "dubstep"],
                  "queries": ["emotional piano", "sad strings", "melancholic"], "speed": "verylow+low",
                  "fuzzytags": "emotional+sad+piano+ambient"},
    "chill": {"bpm": (70, 100), "energy": 0.3,
              "prefer": ["lofi", "lo-fi", "chill", "chillhop", "jazz", "ambient", "relax", "downtempo"],
              "avoid": ["aggressive", "metal", "horror", "dubstep"],
              "queries": ["lofi", "chill beat", "chillhop"], "speed": "low+medium",
              "fuzzytags": "lofi+chillout+jazz+downtempo"},
    "epic": {"bpm": (120, 150), "energy": 0.7,
             "prefer": ["epic", "cinematic", "orchestral", "trailer", "heroic", "dubstep", "battle"],
             "avoid": ["lofi", "acoustic", "ukulele", "lullaby"],
             "queries": ["epic cinematic", "trailer", "orchestral"], "speed": "high+veryhigh",
             "fuzzytags": "epic+cinematic+orchestral+soundtrack"},
    "inspiring": {"bpm": (100, 128), "energy": 0.55,
                  "prefer": ["inspiring", "uplifting", "motivational", "corporate", "pop", "positive", "hopeful"],
                  "avoid": ["dark", "aggressive", "horror", "sad"],
                  "queries": ["uplifting", "inspiring", "motivational"], "speed": "medium+high",
                  "fuzzytags": "uplifting+inspiring+motivational+pop"},
}

# Score weights (points out of 100) and penalties, as documented above.
W_TEMPO, W_TAGS, W_ENERGY, W_CLARITY, W_LENGTH = 40.0, 25.0, 15.0, 10.0, 10.0
P_VOCALS, P_INTRO_PER_S, P_INTRO_MAX = 25.0, 1.0, 8.0
P_LOW_SLOPE, P_LOW_MAX, LOW_SHARE_WARN = 50.0, 15.0, 0.5
P_CLASH, P_CREDIT, P_LOOP = 15.0, 3.0, 4.0
TEMPO_TOL = 0.15

# Analysis constants.
ASR = 11025                 # analysis sample rate
NFFT, HOP = 512, 64         # 172.3 frames/s onset envelope
MAX_ANALYSE_S = 150.0
ENTRY_WINDOW_S, ENTRY_PCT, ENTRY_STEP_S = 5.0, 0.75, 0.1   # = mix_audio.py's bed entry rule
INTRO_WIN_S, INTRO_BELOW_DB = 0.2, 9.0
VOCAL_BAND = (300.0, 3400.0)
LOW_CUT = 150.0
BED_LUFS_TARGET = -20.0     # ref 01 section 6 / mix_audio.py BED_LUFS
_S_LINE = re.compile(r"\bt:\s*([0-9.]+)\s.*?\bS:\s*(-?[0-9.]+|-inf)")
THIRD_OCT = 100.0 * 2.0 ** (np.arange(0, 17) / 3.0)          # 100 Hz .. ~4 kHz band edges (16 bands)

# Licences.
CC_NAMES = {"cc0": "CC0 1.0", "pdm": "Public Domain Mark 1.0", "by": "CC BY", "by-sa": "CC BY-SA", "by-nd": "CC BY-ND",
            "by-nc": "CC BY-NC", "by-nc-sa": "CC BY-NC-SA", "by-nc-nd": "CC BY-NC-ND", "sampling+": "Sampling Plus",
            "nc-sampling+": "NC Sampling Plus"}
ACCEPT = {"cc0", "pdm", "by", "royalty-free"}
NO_CREDIT = {"cc0", "pdm"}
ROYALTY_FREE_WORDS = ("royalty-free", "royalty free", "no attribution", "attribution not required",
                      "pixabay content license", "pixabay license", "youtube audio library")
CREDIT_WORDS = ("attribution required", "credit required", "credit the", "must credit", "credit needed")
REJECT_WHY = {"nc": "NC: non-commercial only, and a short on a monetised account is commercial use",
              "nd": "ND: syncing music to video makes Adapted Material (CC 4.0 s.1(a)), which ND forbids sharing",
              "sa": "SA: the synced short becomes Adapted Material and would have to be released under BY-SA",
              "sampling": "Sampling+: allows sampling parts, not using the whole recording as a bed",
              "custom": "licence text not recognised: add it to --allow custom only after reading its terms",
              "unknown": "no licences.json entry: licence unknown, never auto-picked"}


def log(msg):
    cl.log(f"find_music: {msg}")


def utc_now():
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- licences

def parse_cc(text):
    """('by-nc-sa', '4.0') from a CC URL or a free-text licence name; (None, None) when it is not CC."""
    if not text:
        return None, None
    s = str(text).strip().lower()
    m = re.search(r"creativecommons\.org/(licenses|publicdomain)/([a-z+-]+)/(\d\.\d)", s)
    if m:
        kind, code, ver = m.groups()
        if kind == "publicdomain":
            return ("cc0" if code == "zero" else "pdm" if code == "mark" else None), ver
        return code, ver
    if re.search(r"\bcc[\s-]?0\b|\bcc[\s-]?zero\b|creative commons zero|public domain dedication", s):
        return "cc0", "1.0"
    if re.search(r"public domain", s):
        return "pdm", "1.0"
    ver = (re.search(r"\b(\d\.\d)\b", s) or [None, None])[1]
    if s in CC_NAMES or s.replace("_", "-") in CC_NAMES:
        return s.replace("_", "-"), ver
    if re.search(r"\bcc\b|creative commons|attribution|\bby\b", s):
        parts = ["by"]
        if re.search(r"\bnc\b|non-?commercial", s):
            parts.append("nc")
        if re.search(r"\bsa\b|share-?alike", s):
            parts.append("sa")
        if re.search(r"\bnd\b|no-?deriv", s):
            parts.append("nd")
        if re.search(r"\bcc\b|creative commons|\bcc-by\b", s) or len(parts) > 1:
            return "-".join(parts), ver
    return None, None


def cc_url(code, ver):
    if code == "cc0":
        return "https://creativecommons.org/publicdomain/zero/1.0/"
    if code == "pdm":
        return "https://creativecommons.org/publicdomain/mark/1.0/"
    if code and code.startswith("by"):
        return f"https://creativecommons.org/licenses/{code}/{ver or '4.0'}/"
    return None


def licence_block(code, ver=None, url=None, text=None, allow=(), credit=None):
    """The licence block every candidate carries: code, name, url, credit_required, accepted, reason."""
    allow = set(allow)
    if code == "royalty-free":
        name = text or "royalty-free"
    elif code in ("custom", "unknown"):
        name = text or code
    else:
        name = CC_NAMES.get(code, code or "unknown") + (f" {ver}" if ver and code not in ("cc0", "pdm") else "")
    why = None
    if code in ACCEPT or code in allow:
        ok = True
    elif code in ("unknown", "custom"):
        ok, why = False, REJECT_WHY[code]
    elif code and "sampling" in code:
        ok, why = False, REJECT_WHY["sampling"]
    else:
        parts = set((code or "").split("-"))
        why = "; ".join(REJECT_WHY[p] for p in ("nc", "nd", "sa") if p in parts) or "not in the licence policy"
        ok = False
    if credit is None:
        credit = code not in NO_CREDIT and code != "royalty-free"
    return {"code": code, "name": name, "version": ver, "url": url or cc_url(code, ver),
            "credit_required": bool(credit), "accepted": ok, "reason": None if ok else why,
            "allowed_by_override": bool(ok and code not in ACCEPT)}


def local_licence(entry, allow):
    text = str(entry.get("licence") or entry.get("license") or "").strip()
    low = text.lower()
    code, ver = parse_cc(entry.get("licence_url") or "")
    if not code:
        code, ver = parse_cc(text)
    if code:
        return licence_block(code, ver, entry.get("licence_url"), text or None, allow)
    if any(w in low for w in ROYALTY_FREE_WORDS):
        credit = any(w in low for w in CREDIT_WORDS) and "attribution not required" not in low
        if "credit_required" in entry:
            credit = bool(entry["credit_required"])
        return licence_block("royalty-free", None, entry.get("licence_url"), text, allow, credit=credit)
    return licence_block("custom", None, entry.get("licence_url"), text or None, allow,
                         credit=bool(entry.get("credit_required", True)))


def attribution_line(title, creator, source_url, lic):
    """The credit line for captions.md (also a fine YouTube description line)."""
    t = f'"{title}"' if title else "Untitled track"
    by = f" by {creator}" if creator else ""
    src = f" ({source_url})" if source_url else ""
    if lic["code"] in ("cc0", "pdm"):
        return f"Music: {t}{by}{src}, {lic['name']} (no credit required)"
    if lic["code"] in ("royalty-free", "custom"):
        return f"Music: {t}{by}{src}, {lic['name']}"
    return f"Music: {t}{by}{src}, licensed under {lic['name']} ({lic['url']})"


# ---------------------------------------------------------------- HTTP with cache

class ProviderDown(Exception):
    def __init__(self, kind, message):
        super().__init__(message)
        self.kind, self.message = kind, message


def _key(s):
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:20]


def redact(url):
    """Drop client_id from a URL (logs, cache keys and the output never hold the Jamendo key)."""
    p = urllib.parse.urlsplit(url)
    q = [(k, v) for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=True) if k != "client_id"]
    return urllib.parse.urlunsplit(p._replace(query=urllib.parse.urlencode(q, safe="+,")))


def http_get(url, timeout, max_bytes=None):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read(max_bytes + 1) if max_bytes else r.read()
            if max_bytes and len(data) > max_bytes:
                raise ProviderDown("too_large", f"{redact(url)} is over {max_bytes // (1 << 20)} MB")
            return data, r.headers.get("Content-Type") or ""
    except urllib.error.HTTPError as e:
        raise ProviderDown(f"http_{e.code}", f"HTTP {e.code} from {redact(url)}")
    except (TimeoutError, OSError) as e:  # socket.timeout, URLError (an OSError) and connection resets
        reason = getattr(e, "reason", e)
        kind = "timeout" if isinstance(reason, TimeoutError) or "timed out" in str(reason) else "network"
        raise ProviderDown(kind, f"{kind} after {timeout} s: {redact(url)} ({reason})" if kind == "timeout"
                           else f"network error: {redact(url)} ({reason})")


def get_json(url, cache_dir, provider, timeout, backoff, warnings, retries=1):
    """(data, fetched_at, from_cache). `retries` retries after `backoff` s on 5xx / 429 / timeout / network errors.
    A fresh cache entry (24 h) skips the network; when the call fails a stale entry is used with a warning."""
    path = Path(cache_dir) / "api" / provider / f"{_key(redact(url))}.json"
    cached = None
    if path.is_file():
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cached = None
    if cached and time.time() - cached.get("fetched_epoch", 0) < JSON_TTL_S:
        return cached["data"], cached["fetched_at"], True
    last = None
    for attempt in range(retries + 1):
        try:
            raw, _ = http_get(url, timeout)
            data = json.loads(raw.decode("utf-8", errors="replace"))
            now = utc_now()
            cl.write_json_atomic(path, {"url": redact(url), "fetched_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                        "fetched_epoch": time.time(), "data": data})
            return data, now.strftime("%Y-%m-%dT%H:%M:%SZ"), False
        except ValueError:
            last = ProviderDown("bad_json", f"{provider} returned invalid JSON")
            break
        except ProviderDown as e:
            last = e
            retry = e.kind in ("timeout", "network", "http_429") or e.kind.startswith("http_5")
            if attempt < retries and retry:
                log(f"{provider}: {e.message}; retrying in {backoff:g} s")
                time.sleep(backoff)
                continue
            break
    if cached:
        warnings.append(f"{provider}_stale_cache: {last.message}; using the cached response from "
                        f"{cached.get('fetched_at')}")
        return cached["data"], cached["fetched_at"], True
    raise last


def download(url, cache_dir, timeout, backoff, ext_hint=None):
    """Cached download -> local path. The extension comes from the URL, then ext_hint, then .mp3."""
    ext = Path(urllib.parse.urlsplit(url).path).suffix.lower()
    if ext not in AUDIO_EXT:
        ext = ("." + ext_hint.lower().lstrip(".")) if ext_hint and "." + ext_hint.lower().lstrip(".") in AUDIO_EXT \
            else ".mp3"
    dest = Path(cache_dir) / "audio" / f"{_key(redact(url))}{ext}"
    if dest.is_file() and dest.stat().st_size > 0:
        return dest, True
    last = None
    for attempt in range(2):
        try:
            data, _ = http_get(url, timeout, MAX_DOWNLOAD)
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = cl.tmp_path(dest)
            with open(tmp, "wb") as f:
                f.write(data)
            cl.replace_with_retry(tmp, dest)
            return dest, False
        except ProviderDown as e:
            last = e
            if attempt == 0 and e.kind != "too_large" and not e.kind.startswith("http_4"):
                time.sleep(backoff)
                continue
            break
    raise last


# ---------------------------------------------------------------- providers

def words_of(*parts):
    out = []
    for p in parts:
        if isinstance(p, (list, tuple)):
            out += [str(x) for x in p if x]
        elif p:
            out.append(str(p))
    return " ".join(out).lower().replace("_", " ")


def provider_local(folders, allow, warnings):
    cands = []
    for folder in folders:
        root = Path(folder)
        if not root.is_dir():
            raise cl.ClipError("input_missing", f"--library is not a folder: {folder}", exit_code=2)
        manifest = {}
        mp = root / MANIFEST
        if mp.is_file():
            m = cl.read_json(mp)
            if not isinstance(m, dict):
                raise cl.ClipError("bad_json", f"{mp} must map file names to entries", exit_code=2)
            manifest = {k.replace("\\", "/").lower(): v for k, v in m.items() if isinstance(v, dict)}
        else:
            warnings.append(f"local_no_manifest: {root.as_posix()} has no {MANIFEST}; its tracks stay unverified")
        for f in sorted(root.rglob("*")):
            if not f.is_file() or f.suffix.lower() not in AUDIO_EXT:
                continue
            rel = f.relative_to(root).as_posix()
            entry = manifest.get(rel.lower()) or manifest.get(f.name.lower())
            if entry:
                lic = local_licence(entry, allow)
                title = entry.get("title") or f.stem
                creator = entry.get("artist") or entry.get("creator")
                src = entry.get("source_url")
                attr = entry.get("attribution") or attribution_line(title, creator, src, lic)
                tags = words_of(entry.get("tags"), entry.get("genre"), entry.get("notes"), title, f.stem)
                retrieved = entry.get("retrieved")
            else:
                lic = licence_block("unknown", allow=allow)
                title, creator, src, retrieved = f.stem, None, None, None
                attr = None
                tags = words_of(f.stem)
            cands.append({"id": f"local:{rel}", "provider": "local", "title": title, "creator": creator,
                          "source_url": src, "download_url": None, "local_path": f.resolve().as_posix(),
                          "tags_text": tags, "licence": lic, "attribution": attr, "duration_s": None,
                          "vocal_tag": vocal_from_tags(tags), "retrieved_at": retrieved,
                          "manifest": bool(entry)})
    return cands


def vocal_from_tags(text):
    """1.0 / 0.0 when tags say vocal / instrumental, else None (the audio heuristic decides)."""
    if not text:
        return None
    if re.search(r"\binstrumental\b|\bno vocals?\b|\bwithout vocals?\b", text):
        return 0.0
    if re.search(r"\bvocals?\b|\brap\b|\blyrics?\b|\bsinging\b|\bsinger\b|\bsong with\b", text):
        return 1.0
    return None


def provider_openverse(base, profile, query, allow, cache_dir, timeout, backoff, warnings):
    licences = ["cc0", "by"] + sorted(c for c in allow if c.startswith("by") and c != "by")
    queries = ([query] if query else []) + profile["queries"]
    out, rejected, status, fetched = [], [], "ok", []
    for q in queries[:3]:
        params = {"q": q, "category": "music", "license": ",".join(licences), "mature": "false", "page_size": 20}
        url = base + ("&" if "?" in base else "?") + urllib.parse.urlencode(params, safe=",+")
        try:
            data, at, from_cache = get_json(url, cache_dir, "openverse", timeout, backoff, warnings)
            mode = "filtered"
        except ProviderDown as e:
            # Measured 2026-11-01: filtered searches timed out or gave 504 while a plain q= search answered in
            # ~20 s. One plain attempt, filtered here (category, licence, mature), before giving up.
            plain = base + ("&" if "?" in base else "?") + urllib.parse.urlencode({"q": q, "page_size": 20})
            try:
                data, at, from_cache = get_json(plain, cache_dir, "openverse", timeout, 0.0, warnings, retries=0)
                mode = "plain"
                warnings.append(f"openverse_filtered_down: {e.message}; used a plain q={q!r} search filtered "
                                f"locally (fewer licensed results)")
            except ProviderDown as e2:
                warnings.append(f"openverse_down: {e.message}; plain search: {e2.message}. Retry Openverse later; "
                                f"local results are still used")
                status = "partial" if fetched else "down"
                break
        fetched.append({"query": q, "mode": mode, "fetched_at": at, "cache": from_cache})
        for r in (data or {}).get("results", []) or []:
            if not isinstance(r, dict) or (r.get("category") not in (None, "music")):
                continue
            lic_code = (r.get("license") or "").lower()
            lic = licence_block(lic_code, r.get("license_version"), r.get("license_url"), allow=allow)
            dur = (r.get("duration") or 0) / 1000.0 or None
            genres = r.get("genres") or []
            tags = [t.get("name") for t in (r.get("tags") or []) if isinstance(t, dict)]
            tags_text = words_of(genres, tags, r.get("title"))
            c = {"id": f"openverse:{r.get('id')}", "provider": "openverse", "title": r.get("title"),
                 "creator": r.get("creator"), "source_url": r.get("foreign_landing_url"),
                 "download_url": r.get("url"), "filetype": r.get("filetype"), "local_path": None,
                 "tags_text": tags_text, "licence": lic, "duration_s": dur,
                 "provider_attribution": r.get("attribution"), "vocal_tag": vocal_from_tags(tags_text),
                 "retrieved_at": at[:10], "api_query": q, "upstream": r.get("source")}
            c["attribution"] = attribution_line(c["title"], c["creator"], c["source_url"], lic)
            if r.get("mature"):
                continue
            (out if lic["accepted"] else rejected).append(c)
    return out, rejected, {"status": status, "queries": fetched}


def provider_jamendo(base, profile, query, allow, cache_dir, timeout, backoff, warnings):
    key = os.environ.get("JAMENDO_CLIENT_ID", "").strip()
    if not key:
        return [], [], {"status": "skipped", "note": "set JAMENDO_CLIENT_ID (free key: devportal.jamendo.com)"}
    params = [("client_id", key), ("format", "json"), ("limit", "20"), ("vocalinstrumental", "instrumental"),
              ("speed", profile["speed"]), ("fuzzytags", profile["fuzzytags"]), ("include", "licenses+musicinfo"),
              ("audioformat", "mp32"), ("audiodlformat", "mp32"), ("order", "popularity_total")]
    if query:
        params.append(("search", query))
    url = base + ("&" if "?" in base else "?") + urllib.parse.urlencode(params, safe="+,")
    try:
        data, at, from_cache = get_json(url, cache_dir, "jamendo", timeout, backoff, warnings)
    except ProviderDown as e:
        warnings.append(f"jamendo_down: {e.message}")
        return [], [], {"status": "down"}
    head = (data or {}).get("headers") or {}
    if head.get("status") not in (None, "success"):
        warnings.append(f"jamendo_error: code {head.get('code')}: {head.get('error_message')}")
        return [], [], {"status": "error", "code": head.get("code")}
    out, rejected = [], []
    for r in (data or {}).get("results", []) or []:
        if not isinstance(r, dict):
            continue
        code, ver = parse_cc(r.get("license_ccurl") or "")
        lic = licence_block(code or "custom", ver, r.get("license_ccurl"), allow=allow)
        mi = r.get("musicinfo") or {}
        tg = mi.get("tags") or {}
        tags_text = words_of(tg.get("genres"), tg.get("instruments"), tg.get("vartags"), r.get("name"))
        vi = (mi.get("vocalinstrumental") or "").lower()
        vt = 0.0 if vi == "instrumental" else 1.0 if vi == "vocal" else vocal_from_tags(tags_text)
        dl = r.get("audiodownload") if r.get("audiodownload_allowed") and r.get("audiodownload") else r.get("audio")
        c = {"id": f"jamendo:{r.get('id')}", "provider": "jamendo", "title": r.get("name"),
             "creator": r.get("artist_name"), "source_url": r.get("shareurl") or r.get("shorturl"),
             "download_url": dl, "filetype": "mp3", "local_path": None, "tags_text": tags_text, "licence": lic,
             "duration_s": float(r["duration"]) if r.get("duration") else None, "vocal_tag": vt,
             "retrieved_at": at[:10], "jamendo_speed": mi.get("speed")}
        c["attribution"] = attribution_line(c["title"], c["creator"], c["source_url"], lic)
        (out if lic["accepted"] else rejected).append(c)
    return out, rejected, {"status": "ok", "fetched_at": at, "cache": from_cache}


# ---------------------------------------------------------------- audio analysis

def decode_mono(path, ffmpeg, ffprobe):
    info = cl.probe(path, ffmpeg, ffprobe)
    if not info.get("audio"):
        raise cl.ClipError("no_audio", f"no audio stream: {path}", exit_code=2)
    x = cl.decode_audio(path, ffmpeg, sr=ASR, channels=1, duration=MAX_ANALYSE_S,
                        src_channels=info["audio"].get("channels"))
    return x.astype(np.float64), info


def short_term_series(path, ffmpeg):
    """(t, S) from ebur128 framelog: the 3 s short-term loudness every 0.1 s (mix_audio.py's source)."""
    cp = cl.run([ffmpeg, "-hide_banner", "-nostdin", "-i", str(path), "-map", "0:a:0", "-vn",
                 "-af", "ebur128=framelog=info", "-f", "null", "-"], check=False)
    rows = [m.groups() for m in map(_S_LINE.search, cp.stderr.splitlines()) if m]
    if cp.returncode != 0 or not rows:
        raise cl.ClipError("unreadable_input", f"ebur128 cannot read {path}", hint=cp.stderr.strip()[-300:],
                           exit_code=2)
    return (np.array([float(a) for a, _ in rows]),
            np.array([-120.7 if b == "-inf" else float(b) for _, b in rows]))


def entry_offset(t, s):
    """mix_audio.py auto_offset: earliest start whose next 5 s reach the 75th pct of all 5 s windows' mean S."""
    cands = np.arange(0.0, t[-1] - ENTRY_WINDOW_S + 1e-6, ENTRY_STEP_S)
    lo = np.searchsorted(t, cands + 3.0 + 1e-6, side="right")
    hi = np.searchsorted(t, cands + ENTRY_WINDOW_S + 1e-6, side="right")
    cands, lo, hi = cands[hi > lo], lo[hi > lo], hi[hi > lo]
    if not len(cands):
        return 0.0
    cs = np.concatenate([[0.0], np.cumsum(s)])
    score = np.round((cs[hi] - cs[lo]) / (hi - lo), 4)
    p75 = np.sort(score)[int(ENTRY_PCT * (len(score) - 1))]
    return round(float(cands[np.argmax(score >= p75)]), 3)


def intro_quiet(x):
    w = int(INTRO_WIN_S * ASR)
    n = len(x) // w
    if n < 3:
        return 0.0
    db = 10 * np.log10(np.mean(x[: n * w].reshape(n, w) ** 2, axis=1) + 1e-12)
    ref = np.percentile(db, 75)
    first = int(np.argmax(db >= ref - INTRO_BELOW_DB))
    q = first * INTRO_WIN_S
    return round(q, 1) if q >= 0.5 else 0.0


def stft_power(x):
    """(power (frames, NFFT/2+1) float32, freqs) with a Hann window, hop 64 at 11025 Hz."""
    if len(x) < NFFT:
        x = np.pad(x, (0, NFFT - len(x)))
    frames = np.lib.stride_tricks.sliding_window_view(x, NFFT)[::HOP]
    win = np.hanning(NFFT).astype(np.float32)
    out = np.empty((len(frames), NFFT // 2 + 1), np.float32)
    for i in range(0, len(frames), 4096):
        out[i:i + 4096] = np.abs(np.fft.rfft(frames[i:i + 4096].astype(np.float32) * win, axis=1)) ** 2
    return out, np.fft.rfftfreq(NFFT, 1.0 / ASR)


def autocorr(v):
    v = v - v.mean()
    n = len(v)
    f = np.fft.rfft(v, 2 * n)
    ac = np.fft.irfft(f * np.conj(f))[:n]
    return ac / ac[0] if ac[0] > 0 else ac


def tempo(power, fps):
    """(raw BPM, confidence) from onset-envelope autocorrelation with a log-normal prior at 120 BPM."""
    logm = np.log1p(100.0 * np.sqrt(power, dtype=np.float32))
    flux = np.maximum(np.diff(logm, axis=0), 0).sum(axis=1).astype(np.float64)
    k = max(1, int(0.5 * fps))
    mov = np.convolve(flux, np.ones(k) / k, mode="same")
    env = np.maximum(flux - mov, 0)
    if len(env) < 4 * fps or env.std() == 0:
        return None, 0.0, env
    ac = autocorr(env)
    bpms = np.arange(50.0, 220.0 + 1e-9, 0.1)
    lags = 60.0 * fps / bpms
    idx = np.arange(len(ac))
    score = np.zeros_like(bpms)
    for m, w in ((1, 1.0), (2, 0.5), (3, 1 / 3), (4, 0.25)):
        score += w * np.interp(m * lags, idx, ac, right=0.0)
    prior = np.exp(-0.5 * np.log2(bpms / 120.0) ** 2)
    total = score * prior
    best = int(np.argmax(total))
    med = float(np.median(np.maximum(total, 1e-9)))
    conf = float(total[best] / med) if med > 0 else 0.0
    return round(float(bpms[best]), 1), round(conf, 2), env


def octave_fit(bpm, lo, hi):
    """(effective BPM, octave label or None, fit 0-1): raw, x2 or x0.5, whichever fits the range best."""
    best = None
    for mult, label in ((1.0, None), (2.0, "x2"), (0.5, "x0.5")):
        b = bpm * mult
        if lo <= b <= hi:
            d = 0.0
        else:
            d = (lo / b - 1.0) if b < lo else (b / hi - 1.0)
        if best is None or d < best[3] - 1e-9:
            best = (b, label, max(0.0, 1.0 - d / TEMPO_TOL), d)
    return round(best[0], 1), best[1], round(best[2], 3)


def band_share(power, freqs, lo, hi):
    tot = power[:, freqs >= 20].sum()
    return float(power[:, (freqs >= lo) & (freqs < hi)].sum() / tot) if tot > 0 else 0.0


def vocal_audio(power, freqs, bpm, fps):
    """0-1 vocal-presence heuristic: 300-3400 Hz energy share and the irregularity of that band's envelope."""
    share = band_share(power, freqs, *VOCAL_BAND)
    band = np.sqrt(power[:, (freqs >= VOCAL_BAND[0]) & (freqs < VOCAL_BAND[1])].sum(axis=1).astype(np.float64))
    irregular = 0.5
    if bpm and len(band) > 10 * fps:
        ac = autocorr(band)
        best = -1.0
        for beats in (4, 8):
            lag = beats * 60.0 * fps / bpm
            lo, hi = int(lag * 0.97), int(math.ceil(lag * 1.03)) + 1
            if hi < len(ac):
                best = max(best, float(ac[lo:hi].max()))
        if best > -1.0:
            irregular = float(np.clip(1.0 - best, 0.0, 1.0))
    share_term = float(np.clip((share - 0.25) / 0.4, 0.0, 1.0))
    irr_term = float(np.clip((irregular - 0.1) / 0.5, 0.0, 1.0))
    return round(0.5 * share_term + 0.5 * irr_term, 3), round(share, 3), round(irregular, 3)


def third_octave(power, freqs):
    p = power.mean(axis=0)
    return np.array([p[(freqs >= a) & (freqs < b)].sum() for a, b in zip(THIRD_OCT[:-1], THIRD_OCT[1:])])


def energy_of(env, power, freqs, fps):
    dur = len(env) / fps
    thr = env.mean() + env.std()
    peaks = (env[1:-1] > thr) & (env[1:-1] >= env[:-2]) & (env[1:-1] > env[2:])
    pos = np.nonzero(peaks)[0]
    kept, last = 0, -1e9
    for p in pos:  # at most one onset per 0.1 s
        if p - last >= 0.1 * fps:
            kept, last = kept + 1, p
    rate = kept / dur if dur > 0 else 0.0
    p = power.mean(axis=0)
    centroid = float((p * freqs).sum() / p.sum()) if p.sum() > 0 else 0.0
    e = 0.6 * min(rate / 4.0, 1.0) + 0.4 * min(centroid / 3000.0, 1.0)
    return round(e, 3), round(rate, 2), round(centroid, 0)


def analyse(path, clip_s, ffmpeg, ffprobe, cache_dir):
    """Features of one audio file (cached by file size + mtime + clip_s + ANALYSIS_VERSION)."""
    st = Path(path).stat()
    key = _key(f"{Path(path).resolve().as_posix()}|{st.st_size}|{int(st.st_mtime)}|{clip_s:.2f}|{ANALYSIS_VERSION}")
    cp = Path(cache_dir) / "features" / f"{key}.json"
    if cp.is_file():
        try:
            return json.loads(cp.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    x, info = decode_mono(path, ffmpeg, ffprobe)
    if not len(x) or not np.any(x):
        raise cl.ClipError("silent_audio", f"no usable audio in {path}", exit_code=2)
    dur = info.get("duration") or len(x) / ASR
    t, s = short_term_series(path, ffmpeg)
    offset = entry_offset(t, s)
    lufs = cl.ebur128(path, ffmpeg, true_peak=False)["I"]
    fps = ASR / HOP
    power, freqs = stft_power(x)
    bpm, conf, env = tempo(power, fps)
    a, b = int(offset * fps), int((offset + max(clip_s, 10.0)) * fps)
    win = power[a:b] if b - a > 2 * fps else power
    low = band_share(win, freqs, 20.0, LOW_CUT)
    voc, vshare, virr = vocal_audio(power, freqs, bpm, fps)
    energy, rate, centroid = energy_of(env, power, freqs, fps)
    feats = {"duration_s": round(float(dur), 2), "lufs_i": lufs, "entry_offset_s": offset,
             "intro_quiet_s": intro_quiet(x), "bpm_raw": bpm, "tempo_confidence": conf,
             "low_share": round(low, 3), "vocal_audio": voc, "vocal_band_share": vshare,
             "vocal_irregularity": virr, "energy": energy, "onset_rate": rate, "centroid_hz": centroid,
             "bands": [float(v) for v in third_octave(win, freqs)]}
    cl.write_json_atomic(cp, feats)
    return feats


def dialogue_bands(path, ffmpeg, ffprobe):
    x, _ = decode_mono(path, ffmpeg, ffprobe)
    power, freqs = stft_power(x)
    e = power.sum(axis=1)
    if not np.any(e > 0):
        raise cl.ClipError("silent_audio", f"the dialogue is silent: {path}", exit_code=2)
    thr = np.percentile(e[e > 0], 90) * 10 ** (-30 / 10)
    speech = power[e >= thr]
    return third_octave(speech, freqs)


def clash(bed_bands, dlg_bands):
    """Share of the bed's 100 Hz - 4 kHz energy inside the bands that hold 80% of the dialogue's energy."""
    d = np.asarray(dlg_bands, float)
    b = np.asarray(bed_bands, float)
    if d.sum() <= 0 or b.sum() <= 0:
        return 0.0
    order = np.argsort(d)[::-1]
    cum = np.cumsum(d[order]) / d.sum()
    mask = np.zeros(len(d), bool)
    mask[order[: int(np.searchsorted(cum, 0.8)) + 1]] = True
    return round(float(b[mask].sum() / b.sum()), 3)


# ---------------------------------------------------------------- scoring

def score(c, f, profile, clip_s, dlg):
    lo, hi = profile["bpm"]
    parts, reasons, warns = {}, [], []
    if f["bpm_raw"]:
        eff, octave, tfit = octave_fit(f["bpm_raw"], lo, hi)
    else:
        eff, octave, tfit = None, None, 0.0
    parts["tempo"] = round(W_TEMPO * tfit, 2)
    if eff is None:
        reasons.append("no clear tempo")
    else:
        where = "in" if tfit >= 1 else "outside"
        reasons.append(f"tempo {eff:g} BPM {where} the {profile['name']} range {lo}-{hi}"
                       + (f" (measured {f['bpm_raw']:g}, counted {octave})" if octave else ""))
    text = c.get("tags_text") or ""
    hits = [w for w in profile["prefer"] if re.search(r"\b" + re.escape(w) + r"\b", text)]
    miss = [w for w in profile["avoid"] if re.search(r"\b" + re.escape(w) + r"\b", text)]
    tag_fit = float(np.clip(0.5 + 0.25 * min(len(hits), 2) - 0.25 * min(len(miss), 2), 0, 1))
    parts["tags"] = round(W_TAGS * tag_fit, 2)
    if hits:
        reasons.append("tags match: " + ", ".join(hits[:4]))
    if miss:
        reasons.append("tags against the mood: " + ", ".join(miss[:4]))
    efit = max(0.0, 1.0 - abs(f["energy"] - profile["energy"]) / 0.5)
    parts["energy"] = round(W_ENERGY * efit, 2)
    parts["clarity"] = round(W_CLARITY * float(np.clip((f["tempo_confidence"] - 1.0) / 2.0, 0, 1)), 2)
    usable = max(0.0, f["duration_s"] - f["entry_offset_s"])
    loop = usable < clip_s
    parts["length"] = round(W_LENGTH * min(usable / clip_s, 1.0), 2) if clip_s > 0 else W_LENGTH
    # penalties
    vt = c.get("vocal_tag")
    vocal, vsrc = (vt, "tags") if vt is not None else (f["vocal_audio"], "audio")
    parts["vocals"] = -round(P_VOCALS * vocal, 2)
    if vocal >= 0.5:
        reasons.append(f"vocals likely ({vsrc}): they fight the speech")
    elif vsrc == "tags":
        reasons.append("instrumental (tags)")
    iq = f["intro_quiet_s"]
    parts["quiet_intro"] = -round(min(P_INTRO_MAX, P_INTRO_PER_S * iq), 2) if iq >= 1.0 else 0.0
    if iq >= 1.0:
        reasons.append(f"quiet intro {iq:g} s: skipped, the bed enters at {f['entry_offset_s']:g} s")
    low = f["low_share"]
    parts["low_end"] = -round(min(P_LOW_MAX, P_LOW_SLOPE * (low - LOW_SHARE_WARN)), 2) if low > LOW_SHARE_WARN else 0.0
    if low > LOW_SHARE_WARN:
        warns.append(f"low_end_heavy: {low:.0%} of the energy is under {LOW_CUT:g} Hz; phone speakers lose it, "
                     f"so the bed will sound thin and quiet on phones")
    cl_val = None
    if dlg is not None:
        cl_val = clash(f["bands"], dlg)
        parts["clash"] = -round(P_CLASH * cl_val, 2)
        if cl_val >= 0.5:
            reasons.append(f"{cl_val:.0%} of the bed sits in the speech band")
    parts["credit"] = -P_CREDIT if c["licence"]["credit_required"] else 0.0
    if c["licence"]["credit_required"]:
        reasons.append(f"credit required ({c['licence']['name']}): put the attribution in captions.md")
    parts["loop"] = -P_LOOP if loop else 0.0
    if loop:
        reasons.append(f"loops: {usable:.1f} s from the entry point < {clip_s:g} s clip (0.3 s crossfade in mix)")
    total = round(float(np.clip(sum(parts.values()), 0, 100)), 1)
    feats = {"bpm": eff, "bpm_raw": f["bpm_raw"], "bpm_octave": octave, "tempo_confidence": f["tempo_confidence"],
             "lufs_i": f["lufs_i"], "entry_offset_s": f["entry_offset_s"], "intro_quiet_s": iq,
             "low_share": low, "vocal_score": round(float(vocal), 3), "vocal_source": vsrc,
             "vocal_band_share": f["vocal_band_share"], "vocal_irregularity": f["vocal_irregularity"],
             "dialogue_clash": cl_val, "energy": f["energy"], "onset_rate": f["onset_rate"],
             "centroid_hz": f["centroid_hz"], "duration_s": f["duration_s"], "usable_s": round(usable, 2),
             "loop_needed": loop}
    return total, parts, feats, reasons, warns


# ---------------------------------------------------------------- main

class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise cl.ClipError("usage", message, hint=self.format_usage().strip(), exit_code=2)


def parse_bpm(s):
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*", s or "")
    if not m or not 30 <= float(m.group(1)) < float(m.group(2)) <= 300:
        raise cl.ClipError("usage", f"--bpm must look like 130-160 (30-300), got {s!r}", exit_code=2)
    return float(m.group(1)), float(m.group(2))


def default_cache():
    env = os.environ.get("CLIP_MUSIC_CACHE")
    return Path(env) if env else Path.home() / ".cache" / "clipping-edit" / "music"


def dedupe(cands):
    seen, out = set(), []
    for c in cands:
        k = (re.sub(r"\W+", "", (c.get("title") or "").lower()), re.sub(r"\W+", "", (c.get("creator") or "").lower()))
        if k != ("", "") and k in seen:
            continue
        seen.add(k)
        out.append(c)
    return out


def public(c):
    keep = ("rank", "id", "provider", "title", "creator", "source_url", "download_url", "local_path", "score",
            "score_parts", "features", "reasons", "warnings", "licence", "attribution", "retrieved_at")
    return {k: c.get(k) for k in keep if k in c}


def main() -> int:
    ap = _Parser(description="Find a licence-safe background-music bed for a short (ref 06).")
    ap.add_argument("--mood", default="hype", choices=sorted(MOODS))
    ap.add_argument("--bpm", help="tempo range override, e.g. 130-160")
    ap.add_argument("--clip-s", type=float, default=45.0)
    ap.add_argument("--dialogue", help="the clip's dialogue stem, for the spectral clash")
    ap.add_argument("--library", action="append", default=[], help="folder of downloaded tracks (repeatable)")
    ap.add_argument("--providers", default="local,openverse,jamendo")
    ap.add_argument("--offline", action="store_true", help="local library only, no network")
    ap.add_argument("--query", help="extra search words for the online providers")
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--allow", default="", help="extra licence codes to accept, e.g. by-sa or custom")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--pick", type=int, help="candidate K (1-based) -> bed.<ext> + music.json in --out-dir")
    g.add_argument("--choose", action="store_true", help="pick the best candidate")
    ap.add_argument("--out-dir", help="where bed.<ext> and music.json go (needed with --pick/--choose)")
    ap.add_argument("--cache-dir", help="API, download and feature cache (default ~/.cache/clipping-edit/music)")
    ap.add_argument("--timeout", type=float, default=20.0, help="seconds per HTTP request")
    ap.add_argument("--retry-backoff", type=float, default=3.0, help="seconds before the single retry")
    ap.add_argument("--max-analyse", type=int, default=10, help="remote tracks downloaded and analysed, max")
    ap.add_argument("--openverse-api", default=OPENVERSE_API)
    ap.add_argument("--jamendo-api", default=JAMENDO_API)
    ap.add_argument("--ffmpeg")
    ap.add_argument("--ffprobe")
    args = ap.parse_args()

    if args.clip_s <= 0 or args.clip_s > 600:
        raise cl.ClipError("usage", "--clip-s must be in (0, 600]", exit_code=2)
    if args.top < 1:
        raise cl.ClipError("usage", "--top must be >= 1", exit_code=2)
    if (args.pick is not None or args.choose) and not args.out_dir:
        raise cl.ClipError("usage", "--pick/--choose need --out-dir", exit_code=2)
    providers = [p.strip() for p in args.providers.split(",") if p.strip()]
    bad = set(providers) - {"local", "openverse", "jamendo"}
    if bad:
        raise cl.ClipError("usage", f"unknown provider(s): {', '.join(sorted(bad))}", exit_code=2)
    if args.offline:
        providers = [p for p in providers if p == "local"]
    allow = {a.strip().lower() for a in args.allow.split(",") if a.strip()}
    profile = dict(MOODS[args.mood], name=args.mood)
    if args.bpm:
        profile["bpm"] = parse_bpm(args.bpm)
    ffmpeg = cl.find_ffmpeg(args.ffmpeg)
    ffprobe = cl.find_ffprobe(ffmpeg, args.ffprobe)
    cache = Path(args.cache_dir) if args.cache_dir else default_cache()
    cache.mkdir(parents=True, exist_ok=True)
    warnings, hints, prov_rep = [], [], {}
    t0 = time.time()

    pool, rejected = [], []
    if "local" in providers:
        if args.library:
            loc = provider_local(args.library, allow, warnings)
            pool += loc
            prov_rep["local"] = {"status": "ok", "tracks": len(loc),
                                 "with_manifest": sum(1 for c in loc if c["manifest"])}
        else:
            prov_rep["local"] = {"status": "skipped", "note": "no --library folder"}
    remote = []
    if "openverse" in providers:
        ok, rej, rep = provider_openverse(args.openverse_api, profile, args.query, allow, cache, args.timeout,
                                          args.retry_backoff, warnings)
        rep.update(accepted=len(ok), rejected=len(rej))
        prov_rep["openverse"], remote, rejected = rep, remote + ok, rejected + rej
    if "jamendo" in providers:
        ok, rej, rep = provider_jamendo(args.jamendo_api, profile, args.query, allow, cache, args.timeout,
                                        args.retry_backoff, warnings)
        rep.update(accepted=len(ok), rejected=len(rej))
        prov_rep["jamendo"], remote, rejected = rep, remote + ok, rejected + rej

    rejected = list({c["id"]: c for c in rejected}.values())
    # Remote: skip very short items, pre-rank by tags, download and analyse at most --max-analyse.
    remote = [c for c in dedupe(remote) if not c["duration_s"] or c["duration_s"] >= MIN_TRACK_S]

    def pre(c):
        t = c.get("tags_text") or ""
        return (sum(1 for w in profile["prefer"] if w in t) - sum(1 for w in profile["avoid"] if w in t)
                - (2 if c.get("vocal_tag") == 1.0 else 0))
    remote.sort(key=pre, reverse=True)
    failed_dl = 0
    for c in remote[: args.max_analyse]:
        if not c.get("download_url"):
            continue
        try:
            p, hit = download(c["download_url"], cache, args.timeout, args.retry_backoff, c.get("filetype"))
            c["local_path"] = p.resolve().as_posix()
            pool.append(c)
        except ProviderDown as e:
            failed_dl += 1
            log(f"download failed for {c['id']}: {e.message}")
    if failed_dl:
        warnings.append(f"downloads_failed: {failed_dl} remote tracks could not be downloaded")

    dlg = None
    if args.dialogue:
        if not Path(args.dialogue).is_file():
            raise cl.ClipError("input_missing", f"--dialogue not found: {args.dialogue}", exit_code=2)
        dlg = dialogue_bands(args.dialogue, ffmpeg, ffprobe)

    scored = []
    for c in pool:
        try:
            f = analyse(c["local_path"], args.clip_s, ffmpeg, ffprobe, cache)
        except cl.ClipError as e:
            warnings.append(f"analysis_failed: {c['id']}: {e.message}")
            continue
        total, parts, feats, reasons, warns = score(c, f, profile, args.clip_s, dlg)
        if f["duration_s"] < MIN_TRACK_S:
            warns.append(f"short_track: {f['duration_s']:.1f} s")
        c.update(score=total, score_parts=parts, features=feats, reasons=reasons, warnings=warns)
        scored.append(c)
        log(f"{c['id']}: {total:.1f}  bpm {feats['bpm']} entry {feats['entry_offset_s']} s  "
            f"low {feats['low_share']:.2f}  vocals {feats['vocal_score']:.2f}")
    scored.sort(key=lambda c: (-c["score"], c["id"]))
    good = [c for c in scored if c["licence"]["accepted"]]
    unverified = [c for c in scored if not c["licence"]["accepted"]]
    for i, c in enumerate(good[: args.top], 1):
        c["rank"] = i
    top = good[: args.top]

    report = {"ok": bool(good), "script": "find_music.py", "version": SCRIPT_VERSION,
              "profile": {"mood": args.mood, "bpm": list(profile["bpm"]),
                          "half_time": [round(profile["bpm"][0] / 2, 1), round(profile["bpm"][1] / 2, 1)],
                          "energy": profile["energy"], "prefer": profile["prefer"], "avoid": profile["avoid"],
                          "clip_s": args.clip_s, "dialogue": bool(dlg is not None),
                          "allow_extra": sorted(allow)},
              "providers": prov_rep, "candidates": [public(c) for c in top],
              "unverified": [dict(public(c), why=c["licence"]["reason"]) for c in unverified],
              "rejected": [{"id": c["id"], "title": c["title"], "creator": c["creator"],
                            "licence": c["licence"]["name"], "source_url": c["source_url"],
                            "why": c["licence"]["reason"]} for c in rejected],
              "picked": None, "music_json": None, "warnings": warnings, "hints": hints}
    code = 0
    if not good:
        hints += ["add a local library: download tracks from YouTube Audio Library, Pixabay Music, NCS or "
                  "Incompetech into a folder with a licences.json manifest and pass --library (ref 06)",
                  "set JAMENDO_CLIENT_ID (free key from devportal.jamendo.com) to search Jamendo",
                  "Openverse search can time out (HTTP 504): retry later; cached answers are reused"]
        if unverified:
            hints.insert(0, f"{len(unverified)} local tracks have no licences.json entry; add their licence to use them")
        report["error"] = {"code": "no_licensed_candidate",
                           "message": "no candidate passes the licence policy (CC0, PD, CC BY, royalty-free)"}
        code = 1
    elif args.pick is not None or args.choose:
        k = 1 if args.choose else args.pick
        if not 1 <= k <= len(top):
            raise cl.ClipError("usage", f"--pick {k} is outside 1..{len(top)}", exit_code=2)
        report["picked"], report["music_json"] = write_pick(top[k - 1], Path(args.out_dir))
    elapsed = time.time() - t0
    best = top[0] if top else None
    report["log"] = (f"find_music: mood {args.mood}, {len(scored)} analysed, {len(good)} licensed, "
                     f"{len(rejected)} rejected, {len(unverified)} unverified"
                     + (f"; best {best['score']:.1f} {best['title']!r}" if best else "")
                     + (f"; picked -> {report['music_json']}" if report["music_json"] else "")
                     + f" ({elapsed:.1f} s)")
    cl.emit(report)
    log(report["log"][len("find_music: "):])
    return code


def write_pick(c, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    src = Path(c["local_path"])
    dest = out_dir / f"bed{src.suffix.lower() or '.mp3'}"
    tmp = cl.tmp_path(dest)
    shutil.copyfile(src, tmp)
    cl.replace_with_retry(tmp, dest)
    today = utc_now().strftime("%Y-%m-%d")
    path = dest.resolve().as_posix()
    off = c["features"]["entry_offset_s"]
    music = {"path": path, "offset_s": off, "lufs_target": BED_LUFS_TARGET,
             "bed": {"path": path, "offset_s": off, "lufs": BED_LUFS_TARGET},
             "title": c["title"], "creator": c["creator"], "provider": c["provider"], "source_url": c["source_url"],
             "licence": c["licence"], "attribution": c["attribution"],
             "credit_required": c["licence"]["credit_required"], "retrieved_at": today,
             "licence_proof": {"landing_url": c["source_url"], "licence_url": c["licence"]["url"],
                               "licence": c["licence"]["name"], "metadata_retrieved": c.get("retrieved_at"),
                               "file_copied": today, "download_url": c.get("download_url"),
                               "note": "keep this with the clip: it is the evidence for a Content ID dispute"},
             "features": c["features"], "score": c["score"], "script": "find_music.py", "version": SCRIPT_VERSION}
    mj = out_dir / "music.json"
    cl.write_json_atomic(mj, music)
    log(f"picked {c['id']} -> {dest.as_posix()} (entry {off} s)")
    return public(c), mj.resolve().as_posix()


if __name__ == "__main__":
    cl.run_main(main)
