"""captions.py - lay out ref 01 captions so no ink can leave the safe area; write ASS + a layout JSON (ref 07).

Usage:
  python -P captions.py --tokens tokens.json --canvas 1080x1920 --fps 60/1 [--frames N | --duration S]
                        [--faces faces.json] [--font PATH] [--fontsdir DIR] [--fontname NAME]
                        [--ass captions.ass] [--layout layout.json] [--allow-face-cover] [--no-font-copy]
                        [style / safe-area flags below]
  python -P captions.py --self-test            layout-level tests (no ffmpeg); pixel tests: caption_gate.py --self-test

What it does (ref 07 has the measurements behind every step):
  font     Resolves the font (--font, env CLIP_FONT, --fontsdir, the OS font dirs; Montserrat Black, then
           Montserrat ExtraBold, then Arial Black, with a warning), loads it with Pillow and reads its name, OS/2,
           hhea, head and cmap tables. Exit 1 when it cannot be found or loaded, when --fontname is not the font's
           legacy family (nameID 1: libass matched the PostScript name to ArialMT and the typographic family to the
           Regular weight), or when a caption character has no glyph in it (--missing-glyph drop removes such
           characters instead). Emoji (the emoji code-point ranges, or a symbol the font cannot draw) are dropped
           with a warning (ref 01 section 3: stickers are PNG overlays); symbols the font draws (degree, (c), (R),
           TM) stay.
  size     em = cap_frac x H / (sCapHeight / unitsPerEm) (ref 01: cap height 3.3 % H); the ASS \\fs is
           em x (usWinAscent + usWinDescent) / unitsPerEm (libass sizes the win box, ref 04 section 1 rule 4).
           Both numbers are written to the layout JSON; never hand one where the other is meant.
  measure  Every word's ink box comes from the real font (Pillow, tight ink at the gate threshold), placed the way
           libass places an \\an5 event: the advance box centred on \\pos x, the win-metric box centred on \\pos y.
           The box then grows by the stroke, the shadow offset, the blur halos of the shadow and glow layers (a
           half-plane upper bound of what a caption-only render on #808080 shows at max|px - 128| > ink_thr, per
           colour and shadow opacity) and the entrance's largest scale.
  fit      Chunks come from the tokens' "brk" flags, else ref 01's rules (punctuation, gaps > 0.25 s, <= max_words).
           A chunk is one line if it fits, else two lines split at argmin |w1 - w2| (only when the 2-line block is
           not taller than the safe area), else it is re-chunked (a word that breaks the fit starts the next chunk).
           A line fits when its padded ink is <= the safe width and its text (advance + 2 x stroke) is <=
           max_width_frac x W. Only a lone word wider than that scales down, floor min_scale; if it still does not
           fit it scales further (warning), so ink never leaves the area. A block still taller or wider than the area
           scales down step by step until it fits (warning). Line 2 sits line_adv = (cap + line_gap_em) x em below
           line 1, or lower when the stroked ink of the two lines would come closer than a plain caps pair does
           (a Q tail, a comma, a $).
  place    Lines are centred on W/2; the block shifts sideways only as far as needed to sit inside the safe area.
           Vertical: mid = first baseline at mid_y x H; low = first baseline at low_y x H, or, on 9:16, block bottom
           on the UI band bottom (ref 04 section 1 rule 8); high = block top on the safe top; scan = when a face
           meets mid, low and high, the clear baseline nearest mid on an 8 px grid over the whole safe band. Every
           position is clamped inside the safe area. Face avoidance per chunk window over the union of the face
           boxes (eyes to chin, + face_pad); after a moved chunk, back to mid at the first of two clear chunks; cuts
           reset that (ref 04 section 1 rule 7). No clear height anywhere: exit 1 (face_cover) unless
           --allow-face-cover (least overlap, warning; caption_gate.py then fails it).
  safe     The safe area depends on the aspect ratio (profile auto): 9:16 = y 168-1330 of 1920 (scaled to H),
           x 6 % W left and 12 % W right (action rail); 3:4 = 6 % sides and top, 10 % bottom; 1:1 = 6 %, 8 % bottom;
           16:9 = 5 % sides and top, 10 % bottom. --profile, --margins and --safe override it.
  colour   Keyword guard (ref 04 section 1 rule 6, 49 words incl. THE), per chunk: an isolated coloured function word
           turns white; one inside a run of 2+ neighbouring tokens of the same colour (a coloured phrase, a second
           speaker's whole chunk, ref 01 section 3) keeps its colour.
  time     ref 04 section 1 rule 2: appear_f = max(0, k(word.start) - 1), k(t) = floor((t + 0.0005) fps + 1e-6);
           chunk end_f = min(k(last.end + 0.6), next chunk start_f), the last chunk ends at N. Two chunks whose
           first words appear on the same frame are merged when the merged chunk fits (else the first is held 1
           frame and the next starts 1 frame late, warning); a chunk pushed to frame N or later is dropped with a
           warning naming its words. ASS times are the largest whole centisecond strictly before the frame's time,
           ceil(100 k den / num) - 1 (the floor of ref 04 rule 2 shows a start a frame late where it lands exactly on
           a centisecond). Tokens that would appear at or after frame N are dropped with a warning.
  write    ASS: PlayResX/Y = canvas, WrapStyle 2 (libass never re-wraps), ScaledBorderAndShadow yes, Spacing 0;
           per word one event per layer (0 shadow, 1 glow for coloured words, 2 fill), each \\an5\\pos at the word
           centre, entrance per ref 04 section 1 rule 3, or typed letter by letter (one override block per
           character, same \\pos and advance) for "type" tokens; the event Name is "c<chunk>w<word>" so a gate can
           name the word. With --ass the font file is copied to <ass folder>/fonts (unless --no-font-copy) and the
           layout gets "burn": {"cwd", "fontsdir", "filter"}: run ffmpeg in burn.cwd with -vf burn.filter (both
           filtergraph escaping levels applied; ref 03 section 4 rule 8). Layout JSON: every word's anchor, baseline
           origin, em, \\fs, scale, frame range and boxes, for an EffectCraft builder to place one text layer per
           word at the same spot (anchor = layer centre).

Inputs:
  --tokens   {"fps": "60/1", "frames": N, "words": [{"id": "w813", "start": s, "end": s}, ...],
              "tokens": [{"d": "GONNA", "src": ["w813", "w814"], "sp": "going to", "start": s, "end": s,
                          "c": "green" | "#2BFF2B", "brk": true, "type": true | 0.5, "shadow": 0.75}, ...],
              "cuts": [frame, ...]}
             (or a bare token list). d = display text (ref 04 section 1 rule 1); times are OUTPUT seconds (after the
             cut list's remap): a token's own start/end, else words[src[0]].start .. words[src[-1]].end. c = keyword
             colour: white green yellow red magenta cyan or #RRGGBB (default white; digit/$/% tokens default cyan).
             brk = a chunk ends after this token (if no token has one, ref 01's chunk rules apply). type = typed on
             letter by letter over that many seconds (true = --type-s, default 0.5 s; asterisk tokens like *LAUGHS*
             default to true; false for none; ref 01 section 3 stage directions; ref 04 section 1 rule 12's
             fully-typed floors are warned). shadow = the shadow opacity of this token's chunk (ref 04 section 1
             rule 11's 75 % fallback; the highest value in a chunk applies to the whole chunk). cuts = output frames
             of camera cuts (reset the face-avoid hysteresis). fps/frames here are used when --fps/--frames/--duration
             are not given.
  --faces    face boxes in canvas px, each holding from its frame until the next entry of the same file
             ([frame, null] or an empty list ends it). A file with its own "fps" is remapped to the caption fps by
             time (frame -> event_frame(frame / file_fps, fps)); forms without one are read as output frames.
             Accepted forms:
               face_track.py's stabilize output (path.json, "kind": "crop_path", "fps", "out"): the subject face box
                 and the crop per frame in source px, mapped to canvas px through the crop ("out" must have the
                 canvas aspect ratio; another size is scaled)
               {"fps": "60/1", "boxes": [[frame, x0, y0, x1, y1] | [frame, null], ...]}   (grade_gate.py's form)
               {"<frame>": [x, y, w, h] | [[x, y, w, h], ...] | null, ...}
               [[frame, x, y, w, h], ...] or [{"frame": f, "box": [x, y, w, h]}, ...]
Output (stdout; the layout JSON also goes to --layout, the ASS to --ass, both written atomically):
  {"ok", "version", "ass", "layout", "burn", "canvas", "fps", "frames", "font": {...}, "safe": {...}, "pads": {...},
   "chunks": [{"i", "start_f", "end_f", "position": "mid"|"low"|"high"|"scan", "scale", "lines", "box", "faces",
     "face_overlap", "words": [{"i", "token", "text", "color", "line", "appear_f", "full_f", "end_f", "type_s",
       "shadow_alpha", "anchor": [x, y], "origin": [x, y], "baseline_center": [x, y], "em_px", "ass_fs", "scale",
       "box_ink": [x0, y0, x1, y1], "box": [...]}]}],
   "stats": {...}, "warnings": [str]}
  anchor = the \\an5 point (advance-box centre x, win-box centre y): the scale centre of the entrance.
  origin = advance-box left x on the baseline (left-justified point text); baseline_center = the same baseline at
  the advance centre (centre-justified point text). em_px = the font size an editor that sizes the em (Pillow,
  After Effects-style text) must use, already times scale; ass_fs = the libass \\fs (never use it as an em).
  box_ink = fill + stroke at full size; box = box_ink plus halos and entrance scale (what the gate measures).
  Frames [appear_f, end_f) are output frames; the word is on screen from appear_f until end_f - 1, fully drawn
  (entrance or typing done) from full_f. faces = the chunk's eyes-to-chin regions (the gate checks ink in them).
Exit codes: 0 ok (warnings possible); 1 font/glyph check failed, a chunk cannot avoid a face (face_cover) or a
self-test failed; 2 usage error or bad input.

Library: load_font(), load_faces(), safe_area(), profile_for(), layout(), write_ass(), ass_time(), parse_canvas(),
face_regions(), faces_in(), filter_escape(), burn_info() (caption_gate.py imports them).
"""
import argparse
import math
import os
import platform
import shutil
import struct
import subprocess
import sys
import tempfile
import unicodedata
from fractions import Fraction
from pathlib import Path
from statistics import NormalDist

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cliplib as cl  # noqa: E402

SCRIPT_VERSION = "1.1.0"

FONT_FILES = ["Montserrat-Black.ttf", "Montserrat-Black.otf", "MontserratBlack.ttf"]
FALLBACK_FILES = [["Montserrat-ExtraBold.ttf", "Montserrat-ExtraBold.otf"],
                  ["ariblk.ttf", "Arial Black.ttf", "Arial-Black.ttf", "Arial_Black.ttf"]]
COLOURS = {"white": "#FFFFFF", "green": "#2BFF2B", "yellow": "#F5FF00", "red": "#FF1A1A", "magenta": "#FF2BD6",
           "cyan": "#40E0E0"}
STAY_WHITE = set("the a an and or but is are was were to of in on at for with by from as it its this that these "
                 "those be been have has had do does did will would could should may might must can if then so just "
                 "up out about".split())  # ref 04 section 1 rule 6 (49 words)
PROFILES = {  # margins (left, top, right, bottom) as fractions of W, H, W, H (ref 07 section 2)
    "9:16": (0.06, 168 / 1920, 0.12, (1920 - 1330) / 1920),
    "3:4": (0.06, 0.06, 0.06, 0.10),
    "1:1": (0.06, 0.06, 0.06, 0.08),
    "16:9": (0.05, 0.05, 0.05, 0.10),
}
LIBASS_SIGMA = 0.85     # libass \blur B renders a gaussian of sigma ~0.85 B (measured 0.84-0.85 for B 10-100)
LIBASS_BLUR_MAX = 100   # libass clamps \blur at 100 (B 150 rendered the same sigma 85 as B 100)
DEFAULTS = dict(cap_frac=0.033, max_width_frac=0.80, max_lines=2, max_words=4, max_words_hard=6, min_scale=0.85,
                mid_y=0.50, low_y=0.72, line_gap_em=0.15, bord_em=0.04, shadow_blur_em=60 / 90, shadow_alpha=0.55,
                shadow_offset_em=(0.0, 0.0), glow_blur_em=20 / 90, glow_alpha=0.70, entrance_from=0.93,
                entrance_peak=1.0, ink_thr=24, face_pad=0.05, eyes_frac=0.30, gap_break=0.25, hold_after=0.6,
                type_s=0.5,
                auto_colour=True, missing_glyph="fail")
PUNCT_BREAK = tuple(".!?,;:")
EMOJI_RANGES = [(0x1F000, 0x1FAFF), (0x2600, 0x27BF), (0x2B00, 0x2BFF), (0xFE00, 0xFE0F), (0x200D, 0x200D),
                (0x1F1E6, 0x1F1FF), (0xE0020, 0xE007F), (0x20E3, 0x20E3), (0x2300, 0x23FF), (0x203C, 0x203C),
                (0x2049, 0x2049)]
TRANSLATE = {"\u2018": "'", "\u2019": "'", "\u201a": "'", "\u201b": "'", "\u2032": "'", "\u201c": '"', "\u201d": '"',
             "\u201e": '"', "\u2013": "-", "\u2014": "-", "\u2212": "-", "\u2026": "...", "\u00a0": " ",
             "\u2009": " ", "\u202f": " ", "{": "(", "}": ")", "\\": "/"}


# ---------------------------------------------------------------- font: tables, coverage, resolution

class FontInfo:
    """The sfnt facts libass and Pillow depend on, read without fontTools."""

    def __init__(self, path, index=0):
        self.path = str(path)
        data = Path(path).read_bytes()
        base = 0
        if data[:4] == b"ttcf":
            base = struct.unpack(">I", data[12 + 4 * index:16 + 4 * index])[0]
        if data[base:base + 4] not in (b"\x00\x01\x00\x00", b"OTTO", b"true"):
            raise ValueError("not a TrueType/OpenType font")
        n = struct.unpack(">H", data[base + 4:base + 6])[0]
        self.tables = {}
        for i in range(n):
            rec = data[base + 12 + 16 * i:base + 28 + 16 * i]
            _, off, ln = struct.unpack(">III", rec[4:16])
            self.tables[rec[:4].decode("latin-1")] = (off, ln)
        self._data = data
        self.upm = self._u16("head", 18)
        self.hhea_asc, self.hhea_desc = self._i16("hhea", 4), self._i16("hhea", 6)
        self.weight, self.win_asc, self.win_desc, self.cap = 400, 0, 0, None
        if "OS/2" in self.tables:
            ver = self._u16("OS/2", 0)
            self.weight = self._u16("OS/2", 4)
            self.win_asc, self.win_desc = self._u16("OS/2", 74), self._u16("OS/2", 76)
            if ver >= 2 and self.tables["OS/2"][1] >= 90:
                self.cap = self._i16("OS/2", 88) or None
        self.names = self._names()
        self._cmap = self._read_cmap()

    def _u16(self, tag, at):
        return struct.unpack(">H", self._data[self.tables[tag][0] + at:self.tables[tag][0] + at + 2])[0]

    def _i16(self, tag, at):
        return struct.unpack(">h", self._data[self.tables[tag][0] + at:self.tables[tag][0] + at + 2])[0]

    def _names(self):
        out = {}
        if "name" not in self.tables:
            return out
        off = self.tables["name"][0]
        _, count, soff = struct.unpack(">HHH", self._data[off:off + 6])
        for i in range(count):
            pid, eid, lid, nid, ln, so = struct.unpack(">HHHHHH", self._data[off + 6 + 12 * i:off + 18 + 12 * i])
            raw = self._data[off + soff + so:off + soff + so + ln]
            try:
                s = raw.decode("utf-16-be") if pid in (0, 3) else raw.decode("mac_roman")
            except UnicodeDecodeError:
                continue
            if nid in (1, 2, 4, 6, 16, 17):
                out.setdefault(nid, [])
                if s not in out[nid]:
                    out[nid].append(s)
        return out

    def _read_cmap(self):
        if "cmap" not in self.tables:
            return None
        off = self.tables["cmap"][0]
        n = struct.unpack(">H", self._data[off + 2:off + 4])[0]
        subs = {}
        for i in range(n):
            pid, eid, so = struct.unpack(">HHI", self._data[off + 4 + 8 * i:off + 12 + 8 * i])
            fmt = struct.unpack(">H", self._data[off + so:off + so + 2])[0]
            subs[(pid, eid, fmt)] = off + so
        for key in [(3, 10, 12), (0, 4, 12), (0, 6, 12), (3, 1, 4), (0, 3, 4), (0, 4, 4), (0, 1, 4), (0, 0, 4)]:
            if key in subs:
                return (key[2], subs[key])
        return None

    def has(self, cp):
        """True when the cmap maps code point cp to a real glyph (None when the cmap format is not read here)."""
        if self._cmap is None:
            return None
        fmt, o = self._cmap
        d = self._data
        if fmt == 12:
            ng = struct.unpack(">I", d[o + 12:o + 16])[0]
            for g in range(ng):
                s, e, gid = struct.unpack(">III", d[o + 16 + 12 * g:o + 28 + 12 * g])
                if s <= cp <= e:
                    return gid + (cp - s) != 0
            return False
        if cp > 0xFFFF:
            return False
        seg2 = struct.unpack(">H", d[o + 6:o + 8])[0]
        ends, starts = o + 14, o + 16 + seg2
        deltas, ranges = starts + seg2, starts + 2 * seg2
        for i in range(seg2 // 2):
            end = struct.unpack(">H", d[ends + 2 * i:ends + 2 * i + 2])[0]
            if cp > end:
                continue
            start = struct.unpack(">H", d[starts + 2 * i:starts + 2 * i + 2])[0]
            if cp < start:
                return False
            delta = struct.unpack(">h", d[deltas + 2 * i:deltas + 2 * i + 2])[0]
            ro = struct.unpack(">H", d[ranges + 2 * i:ranges + 2 * i + 2])[0]
            if ro == 0:
                return (cp + delta) & 0xFFFF != 0
            at = ranges + 2 * i + ro + 2 * (cp - start)
            gid = struct.unpack(">H", d[at:at + 2])[0]
            return gid != 0 and (gid + delta) & 0xFFFF != 0
        return False

    @property
    def family(self):
        """The legacy family (nameID 1), the name libass matches (tested: 'Montserrat Black' -> Montserrat-Black)."""
        return (self.names.get(1) or self.names.get(16) or [Path(self.path).stem])[0]

    def all_names(self):
        return {s for k in (1, 4, 6, 16) for s in self.names.get(k, [])}

    @property
    def box_units(self):
        """The vertical box libass sizes \\fs to: usWinAscent + usWinDescent, else hhea ascender - descender."""
        win = self.win_asc + self.win_desc
        return win if win > 0 else self.hhea_asc - self.hhea_desc

    @property
    def box_ascent(self):
        return self.win_asc if self.win_asc + self.win_desc > 0 else self.hhea_asc


def font_dirs(extra=None):
    """--fontsdir first, then the OS font folders (same list as preflight.py)."""
    home = Path.home()
    dirs = [Path(extra)] if extra else []
    sysname = platform.system()
    if sysname == "Windows":
        dirs += [Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts",
                 Path(os.environ.get("LOCALAPPDATA", home / "AppData/Local")) / "Microsoft/Windows/Fonts"]
    elif sysname == "Darwin":
        dirs += [home / "Library/Fonts", Path("/Library/Fonts"), Path("/System/Library/Fonts")]
    else:
        dirs += [home / ".fonts", home / ".local/share/fonts", Path("/usr/share/fonts"), Path("/usr/local/share/fonts")]
    return [d for d in dirs if d.is_dir()]


def _search(names, dirs):
    wanted = {n.lower() for n in names}
    for d in dirs:
        for n in names:
            if (d / n).is_file():
                return d / n
        try:
            for p in d.rglob("*"):
                if p.name.lower() in wanted:
                    return p
        except OSError:
            continue
    return None


def find_font(font=None, fontsdir=None):
    """(path, how, warnings). Raises ClipError(exit 1) when nothing loadable is found."""
    if font:
        if not Path(font).is_file():
            raise cl.ClipError("font_missing", f"--font not found: {font}",
                               hint="pass the .ttf path, or drop --font to search CLIP_FONT / --fontsdir / OS fonts")
        return Path(font), "--font", []
    env = os.environ.get("CLIP_FONT")
    if env and Path(env).is_file():
        return Path(env), "CLIP_FONT", []
    if fontsdir and not Path(fontsdir).is_dir():
        raise cl.ClipError("font_missing", f"--fontsdir is not a folder: {fontsdir}")
    dirs = font_dirs(fontsdir)
    p = _search(FONT_FILES, dirs)
    if p:
        return p, "font dir", []
    for names in FALLBACK_FILES:
        p = _search(names, dirs)
        if p:
            return p, "fallback", [f"Montserrat Black not found; using {p.name} (ref 01 fallback order)"]
    raise cl.ClipError("font_missing", "no caption font found (Montserrat Black, Montserrat ExtraBold, Arial Black)",
                       hint="install Montserrat (Google Fonts), or pass --font PATH / set CLIP_FONT")


def load_font(font=None, fontsdir=None, fontname=None):
    """Resolve, load and check the font. Returns {"info", "path", "fontsdir", "fontname", "how", "warnings"}."""
    path, how, warns = find_font(font, fontsdir)
    try:
        info = FontInfo(path)
        from PIL import ImageFont
        ImageFont.truetype(str(path), 40)
    except Exception as e:
        raise cl.ClipError("font_unloadable", f"cannot load font {path}: {type(e).__name__}: {e}")
    families = info.names.get(1) or [info.family]
    name = fontname or info.family
    if name not in families:
        other = "is a name of" if name in info.all_names() else "is not a name of"
        raise cl.ClipError("font_name_mismatch", f"ASS Fontname {name!r} {other} {Path(path).name} but not its legacy "
                           f"family (nameID 1: {families})",
                           hint=f"use --fontname {info.family!r} (or omit --fontname): libass matched the PostScript "
                                "name and the typographic family to other fonts (ArialMT, 10 % wider; the Regular "
                                "weight), ref 07 section 1 rule 8")
    if info.weight < 800:
        warns.append(f"font weight {info.weight} < 800: not the ref 01 Black look")
    fdir = Path(fontsdir) if fontsdir and (Path(fontsdir) / Path(path).name).is_file() else Path(path).parent
    return {"info": info, "path": str(path), "fontsdir": str(fdir), "fontname": name, "how": how, "warnings": warns}


# ---------------------------------------------------------------- text

def is_emoji(ch, font=None):
    """An emoji code point (the ranges above), or a symbol ('So') the font cannot draw. Symbols the font covers
    (degree, (c), (R), TM) are text and stay (dropping them changes the meaning: 72°F -> 72F)."""
    cp = ord(ch)
    if any(a <= cp <= b for a, b in EMOJI_RANGES):
        return True
    return unicodedata.category(ch) == "So" and (font is None or font.has(cp) is False)


def clean_text(s, font, missing="fail", warnings=None, where=""):
    """Normalised caption text: NFC, straight quotes, ALL CAPS, emoji dropped, glyph coverage checked."""
    warnings = warnings if warnings is not None else []
    s = unicodedata.normalize("NFC", str(s))
    s = "".join(TRANSLATE.get(c, c) for c in s)
    emo = [c for c in s if is_emoji(c, font)]
    if emo:
        warnings.append(f"{where}: dropped emoji {''.join(emo)!r} (stickers are PNG overlays, ref 01 section 3)")
        s = "".join(c for c in s if not is_emoji(c, font))
    s = " ".join(s.upper().split())
    bad = sorted({c for c in s if not c.isspace() and font.has(ord(c)) is False})
    if bad:
        if missing == "drop":
            warnings.append(f"{where}: dropped characters without a glyph in the font: {''.join(bad)!r}")
            s = " ".join("".join(c for c in s if c not in bad).split())
        else:
            raise cl.ClipError("glyph_missing", f"{where}: {''.join(bad)!r} has no glyph in {Path(font.path).name}; "
                               "libass would draw it with a fallback font of unmeasured width",
                               hint="fix the token text, pass a font that covers it (--font), or --missing-glyph drop")
    return s


def colour_hex(c, where):
    if c is None or c == "":
        return None
    c = str(c).strip()
    if c.lower() in COLOURS:
        return COLOURS[c.lower()]
    if len(c) == 7 and c[0] == "#":
        try:
            int(c[1:], 16)
            return c.upper()
        except ValueError:
            pass
    raise cl.ClipError("bad_input", f"{where}: colour {c!r} is not one of {sorted(COLOURS)} or #RRGGBB", exit_code=2)


def ass_colour(hexrgb):
    r, g, b = hexrgb[1:3], hexrgb[3:5], hexrgb[5:7]
    return f"&H{b}{g}{r}&".upper()


# ---------------------------------------------------------------- inputs

def parse_canvas(s):
    try:
        w, h = (int(v) for v in str(s).lower().split("x"))
        if w < 64 or h < 64:
            raise ValueError
        return w, h
    except ValueError:
        raise cl.ClipError("usage", f"--canvas must be WxH (e.g. 1080x1920), got {s!r}", exit_code=2)


def _num(v, what):
    try:
        x = float(v)
        if not math.isfinite(x):
            raise ValueError
        return x
    except (TypeError, ValueError):
        raise cl.ClipError("bad_input", f"{what} must be a number, got {v!r}", exit_code=2)


def load_tokens(obj, font, missing="fail", auto_colour=True, type_s=0.5):
    """[{token, text, start, end, color, brk, type_s, shadow}] in time order, plus (fps, frames, cuts) found in the
    file. The keyword guard (ref 04 section 1 rule 6) runs later, per chunk (keyword_guard)."""
    warnings = []
    meta = obj if isinstance(obj, dict) else {}
    toks = obj.get("tokens") if isinstance(obj, dict) else obj
    if not isinstance(toks, list) or not toks:
        raise cl.ClipError("bad_input", "--tokens needs a non-empty token list ({'tokens': [...]} or [...])",
                           exit_code=2)
    words = {}
    w = meta.get("words")
    if isinstance(w, dict):
        words = w
    elif isinstance(w, list):
        words = {x.get("id"): x for x in w if isinstance(x, dict)}
    out = []
    for i, t in enumerate(toks):
        where = f"token {i}"
        if not isinstance(t, dict) or "d" not in t:
            raise cl.ClipError("bad_input", f"{where} needs a 'd' (display text): {t!r}", exit_code=2)
        start, end = t.get("start"), t.get("end")
        src = t.get("src") or []
        if (start is None or end is None) and src:
            try:
                start = words[src[0]]["start"] if start is None else start
                end = words[src[-1]]["end"] if end is None else end
            except (KeyError, TypeError):
                raise cl.ClipError("bad_input", f"{where}: src {src} not found in 'words' (and no start/end)",
                                   exit_code=2)
        if start is None or end is None:
            raise cl.ClipError("bad_input", f"{where} ({t.get('d')!r}) has no start/end and no src times "
                               "(asterisk tokens need their own start/end)", exit_code=2)
        start, end = _num(start, f"{where} start"), _num(end, f"{where} end")
        if end < start or start < 0:
            raise cl.ClipError("bad_input", f"{where}: bad times {start}..{end}", exit_code=2)
        text = clean_text(t["d"], font, missing, warnings, where)
        if not text:
            warnings.append(f"{where}: empty after cleanup, skipped")
            continue
        col = colour_hex(t.get("c"), where)
        if col is None and auto_colour and any(ch.isdigit() or ch in "$%" for ch in text):
            col = COLOURS["cyan"]
        typ = t.get("type")
        if typ is None:  # ref 01 section 3: stage directions (*LAUGHS*) are typed on letter by letter
            typ = len(text) > 2 and text.startswith("*") and text.endswith("*")
        if isinstance(typ, bool):
            typ = type_s if typ else 0.0
        typ = _num(typ, f"{where} type")
        if not 0 <= typ <= 5:
            raise cl.ClipError("bad_input", f"{where}: type must be true/false or 0-5 seconds, got {typ}",
                               exit_code=2)
        sh = t.get("shadow")
        if sh is not None:
            sh = _num(sh, f"{where} shadow")
            if not 0 <= sh <= 1:
                raise cl.ClipError("bad_input", f"{where}: shadow must be an opacity 0-1, got {sh}", exit_code=2)
        out.append({"token": i, "text": text, "start": start, "end": end, "color": col or "#FFFFFF",
                    "brk": bool(t.get("brk")), "type_s": typ, "shadow": sh})
    for a, b in zip(out, out[1:]):
        if b["start"] < a["start"]:
            raise cl.ClipError("bad_input", f"token {b['token']} starts before token {a['token']}", exit_code=2)
    cuts = sorted(int(c) for c in meta.get("cuts", []) or [])
    return out, meta.get("fps"), meta.get("frames"), cuts, warnings


def keyword_guard(chunks, warnings):
    """ref 04 section 1 rule 6: an isolated one-word keyword from STAY_WHITE stays white. A word inside a run of 2+
    neighbouring tokens of the same colour in its chunk (a coloured phrase like yellow WHATEVER I DO, or a
    second speaker's whole magenta chunk, ref 01 section 3) keeps its colour."""
    for ch in chunks:
        for j, t in enumerate(ch):
            col = t["color"]
            if col == "#FFFFFF" or " " in t["text"]:
                continue
            letters = "".join(c for c in t["text"] if c.isalpha()).lower()
            if letters not in STAY_WHITE:
                continue
            prev_same = j > 0 and ch[j - 1]["color"] == col
            next_same = j + 1 < len(ch) and ch[j + 1]["color"] == col
            if not (prev_same or next_same):
                warnings.append(f"token {t['token']}: one-word keyword {t['text']!r} kept white (ref 04 section 1 "
                                "rule 6)")
                t["color"] = "#FFFFFF"


def load_faces(obj, out_fps=None, canvas=None, warnings=None):
    """[(output frame, [boxes x0,y0,x1,y1 in canvas px])] sorted; each entry holds until the next one.

    A file that names its own fps (face_track.py's crop_path, grade_gate.py's {fps, boxes}) is remapped to out_fps
    by time: output frame = event_frame(f / file_fps, out_fps). A crop_path whose "out" size differs from the canvas
    is scaled when the aspect ratio matches, else it exits 2. Forms without an fps are read as output frames."""
    warnings = warnings if warnings is not None else []
    rows = []
    file_fps = cl.parse_rate(obj.get("fps")) if isinstance(obj, dict) and obj.get("fps") else None
    out_fps = cl.parse_rate(out_fps) if out_fps else None
    sx = sy = 1.0
    if isinstance(obj, dict) and obj.get("kind") == "crop_path" and canvas:
        try:
            ow, oh = float(obj["out"][0]), float(obj["out"][1])
        except (KeyError, IndexError, TypeError, ValueError):
            raise cl.ClipError("bad_input", "--faces: crop_path without a readable 'out' size", exit_code=2)
        if (ow, oh) != tuple(float(v) for v in canvas):
            if abs(ow / oh - canvas[0] / canvas[1]) > 0.005 * canvas[0] / canvas[1]:
                raise cl.ClipError("bad_input", f"--faces: crop_path out {ow:.0f}x{oh:.0f} has another aspect ratio "
                                   f"than the canvas {canvas[0]}x{canvas[1]}", exit_code=2)
            sx, sy = canvas[0] / ow, canvas[1] / oh
            warnings.append(f"--faces: crop_path out {ow:.0f}x{oh:.0f} scaled to the canvas {canvas[0]}x{canvas[1]}")

    def xywh(b):
        x, y, w, h = (float(v) for v in b[:4])
        if w <= 0 or h <= 0:
            raise ValueError
        return (x, y, x + w, y + h)

    try:
        if isinstance(obj, dict) and obj.get("kind") == "crop_path":
            # face_track.py stabilize output: face box and crop per frame in source px -> canvas px
            fd, fa, oh = obj["frames_data"], obj["face"], float(obj["out"][1])
            for k in range(len(fd["cx"])):
                vals = (fa["x"][k], fa["y"][k], fa["w"][k], fa["h"][k], fd["cx"][k], fd["cy"][k], fd["cw"][k],
                        fd["ch"][k])
                if any(v is None for v in vals):
                    rows.append((k, []))
                    continue
                x, y, w, h, cx, cy, cw, ch = (float(v) for v in vals)
                sc, x0, y0 = oh / ch, cx - cw / 2, cy - ch / 2
                rows.append((k, [((x - x0) * sc, (y - y0) * sc, (x - x0 + w) * sc, (y - y0 + h) * sc)]))
        elif isinstance(obj, dict) and "boxes" in obj:
            for b in obj["boxes"]:
                f = int(b[0])
                rows.append((f, [] if len(b) < 5 or b[1] is None else [tuple(float(v) for v in b[1:5])]))
        elif isinstance(obj, dict):
            for k, v in obj.items():
                if v is None or v == []:
                    rows.append((int(k), []))
                elif isinstance(v[0], (list, tuple)):
                    rows.append((int(k), [xywh(b) for b in v]))
                else:
                    rows.append((int(k), [xywh(v)]))
        elif isinstance(obj, list):
            for r in obj:
                if isinstance(r, dict):
                    b = r.get("box")
                    rows.append((int(r["frame"]), [] if b is None else [xywh(b)]))
                else:
                    rows.append((int(r[0]), [] if len(r) < 5 or r[1] is None else [xywh(r[1:5])]))
        else:
            raise ValueError
    except (KeyError, IndexError, TypeError, ValueError):
        raise cl.ClipError("bad_input", "--faces: unreadable face boxes (see the docstring for the forms)",
                           exit_code=2)
    remap = file_fps and out_fps and file_fps != out_fps
    if remap:
        warnings.append(f"--faces: frames at {cl.frac_str(file_fps)} fps remapped to the caption clock "
                        f"{cl.frac_str(out_fps)} fps")
    merged = {}
    for f, bs in rows:
        if remap:
            f = cl.event_frame(Fraction(f) / file_fps, out_fps)
        if sx != 1.0 or sy != 1.0:
            bs = [(b[0] * sx, b[1] * sy, b[2] * sx, b[3] * sy) for b in bs]
        merged.setdefault(f, [])
        merged[f].extend(bs)
    for bs in merged.values():
        for b in bs:
            if b[2] <= b[0] or b[3] <= b[1]:
                raise cl.ClipError("bad_input", f"--faces: empty or reversed box {b}", exit_code=2)
    return sorted(merged.items())


def faces_in(track, f0, f1):
    """Every face box shown on frames [f0, f1)."""
    out, cur = [], []
    for f, bs in track:
        if f <= f0:
            cur = bs
        elif f < f1:
            out.extend(bs)
        else:
            break
    return cur + out


# ---------------------------------------------------------------- safe area

def profile_for(w, h):
    ar = w / h
    if ar <= 0.65:
        return "9:16"
    if ar <= 0.90:
        return "3:4"
    if ar <= 1.15:
        return "1:1"
    return "16:9"


def safe_area(w, h, profile="auto", margins=None, rect=None):
    """{"profile", "x0", "y0", "x1", "y1", "margins"} in canvas px; ink must stay inside [x0, x1) x [y0, y1)."""
    prof = profile_for(w, h) if profile in (None, "auto") else profile
    if prof not in PROFILES:
        raise cl.ClipError("usage", f"--profile must be auto or one of {sorted(PROFILES)}", exit_code=2)
    m = tuple(margins) if margins else PROFILES[prof]
    if rect:
        x0, y0, x1, y1 = (float(v) for v in rect)
        prof = "custom"
    else:
        x0, y0 = math.ceil(m[0] * w - 1e-9), math.ceil(m[1] * h - 1e-9)
        x1, y1 = math.floor(w - m[2] * w + 1e-9), math.floor(h - m[3] * h + 1e-9)
    if not (0 <= x0 < x1 <= w and 0 <= y0 < y1 <= h):
        raise cl.ClipError("usage", f"safe area {x0},{y0},{x1},{y1} is not inside the {w}x{h} canvas", exit_code=2)
    return {"profile": prof, "x0": x0, "y0": y0, "x1": x1, "y1": y1, "margins": list(m)}


# ---------------------------------------------------------------- measurement

class Measurer:
    """Advance widths and tight ink boxes from the real font, at the gate's ink threshold."""

    def __init__(self, path, em, ink_thr):
        from PIL import ImageFont
        self.font = ImageFont.truetype(str(path), em)
        self.em = em
        self.alpha_thr = ink_thr / 127.0 * 255.0   # white fill over #808080: |px - 128| > thr <=> alpha > thr/127
        self.engine = "raqm" if getattr(self.font, "layout_engine", 0) == getattr(ImageFont.Layout, "RAQM", -1) \
            else "basic"
        self._ink = {}

    def advance(self, text):
        return float(self.font.getlength(text))

    def ink(self, text):
        """(x0, y0, x1, y1) of the ink relative to (advance-box left, baseline), unscaled."""
        if text not in self._ink:
            import numpy as np
            from PIL import Image, ImageDraw
            pad = int(self.em * 2) + 4
            wd = int(self.advance(text)) + 2 * pad
            ht = int(self.em * 4)
            im = Image.new("L", (wd, ht), 0)
            ImageDraw.Draw(im).text((pad, int(self.em * 2.5)), text, font=self.font, fill=255, anchor="ls")
            a = np.asarray(im) > self.alpha_thr
            ys, xs = np.nonzero(a)
            if len(xs) == 0:
                self._ink[text] = (0.0, 0.0, 0.0, 0.0)
            else:
                self._ink[text] = (float(xs.min() - pad), float(ys.min() - int(self.em * 2.5)),
                                   float(xs.max() + 1 - pad), float(ys.max() + 1 - int(self.em * 2.5)))
        return self._ink[text]


def halo_pad(st, em, colours):
    """Pixels the shadow/glow halos add beyond the fill + stroke ink, per side (left, top, right, bottom).

    Half-plane upper bound: a blurred glyph is never denser than a blurred half-plane at the same distance, so the
    composite (shadow, then glow, over #808080) at distance d outside the stroked edge is bounded by
    a * Phi((b - d) / sigma) per layer. The pad is the largest d whose composite reaches max|px - 128| > ink_thr.
    """
    nd = NormalDist()
    bord = st["bord_em"] * em
    s_sig = LIBASS_SIGMA * min(LIBASS_BLUR_MAX, st["shadow_blur_em"] * em)
    g_sig = LIBASS_SIGMA * min(LIBASS_BLUR_MAX, st["glow_blur_em"] * em)
    glow_cols = [c for c in colours if c != "#FFFFFF"]
    best = 0.0
    for col in [None] + glow_cols:
        rgb = None if col is None else [int(col[i:i + 2], 16) for i in (1, 3, 5)]
        d, step, last = 0.0, 0.25, 0.0
        limit = bord + 4 * max(s_sig, g_sig, 1.0) + 4
        while d <= limit:
            a_s = st["shadow_alpha"] * (nd.cdf((bord - d) / s_sig) if s_sig > 0 else float(d <= bord))
            a_g = 0.0
            if rgb is not None:
                a_g = st["glow_alpha"] * (nd.cdf((bord - d) / g_sig) if g_sig > 0 else float(d <= bord))
            diff = 0.0
            for ch in range(3):
                v = 128.0 * (1 - a_s)
                if rgb is not None:
                    v = v * (1 - a_g) + rgb[ch] * a_g
                diff = max(diff, abs(v - 128.0))
            if diff > st["ink_thr"]:
                last = d
            d += step
        best = max(best, last + step)
    halo = max(0.0, best - bord)
    ox, oy = (v * em for v in st["shadow_offset_em"])
    # the shadow layer is offset by (ox, oy): its halo reaches further on that side
    return (halo + max(0.0, -ox), halo + max(0.0, -oy), halo + max(0.0, ox), halo + max(0.0, oy))


# ---------------------------------------------------------------- layout

class Ctx:
    def __init__(self, w, h, fps, frames, font, st, safe):
        self.w, self.h, self.fps, self.frames, self.font, self.st, self.safe = w, h, fps, frames, font, st, safe
        info = font["info"]
        cap_units = info.cap
        self.m0 = Measurer(font["path"], 100.0, st["ink_thr"])
        if not cap_units:
            cap_units = -self.m0.ink("H")[1] / 100.0 * info.upm
        self.cap_ratio = cap_units / info.upm
        self.em = st["cap_frac"] * h / self.cap_ratio
        self.fs = self.em * info.box_units / info.upm
        self.asc_off = self.em * (info.box_ascent - info.box_units / 2) / info.upm  # baseline - \pos y
        self.m = Measurer(font["path"], self.em, st["ink_thr"])
        self.bord = st["bord_em"] * self.em
        self.line_adv = (self.cap_ratio + st["line_gap_em"]) * self.em
        hy = self.m.ink("H")
        self.h_ink = hy[3] - hy[1]  # cap ink height: a plain caps line keeps ref 01's 0.15 em gap exactly
        self.scale_max = max(1.0, st["entrance_from"], st["entrance_peak"])
        self.pad_white = halo_pad(st, self.em, ["#FFFFFF"])
        self._pads = {}

    def pad(self, colour, sa=None):
        key = (colour, sa)
        if key not in self._pads:
            st = self.st if sa is None else {**self.st, "shadow_alpha": sa}
            self._pads[key] = halo_pad(st, self.em, [colour])
        return self._pads[key]

    def word_box(self, text, colour, scale, sa=None):
        """(ink_box, padded_box) relative to the word's anchor (the \\pos point), at scale."""
        adv = self.m.advance(text)
        x0, y0, x1, y1 = self.m.ink(text)
        # ink relative to the anchor: advance box centred on x, baseline asc_off below the anchor
        ink = (x0 - adv / 2, y0 + self.asc_off, x1 - adv / 2, y1 + self.asc_off)
        b = self.bord * max(1.0, scale)
        full = tuple(v * scale for v in ink)
        ink_b = (full[0] - b, full[1] - b, full[2] + b, full[3] + b)
        s = scale * self.scale_max
        grow = max(1.0, s)
        p = self.pad(colour, sa)
        big = tuple(v * s for v in ink)
        bb = self.bord * grow
        padded = (big[0] - bb - p[0] * grow, big[1] - bb - p[1] * grow, big[2] + bb + p[2] * grow,
                  big[3] + bb + p[3] * grow)
        return ink_b, padded

    def line_metrics(self, toks, scale=1.0):
        """Word anchors relative to the line's (centre x, baseline y), plus the line's text and padded widths and
        its stroked ink top/bottom relative to the baseline."""
        text = " ".join(t["text"] for t in toks)
        adv = self.m.advance(text) * scale
        left = -adv / 2
        words, pos = [], 0
        x0, x1 = math.inf, -math.inf
        top, bot = math.inf, -math.inf
        for t in toks:
            pre = self.m.advance(text[:pos]) * scale if pos else 0.0
            wadv = self.m.advance(t["text"]) * scale
            ax = left + pre + wadv / 2
            ink, padded = self.word_box(t["text"], t["color"], scale, t.get("sa"))
            words.append({"tok": t, "ax": ax, "ink": ink, "padded": padded, "adv": wadv, "left": left + pre})
            x0, x1 = min(x0, ax + padded[0]), max(x1, ax + padded[2])
            top, bot = min(top, ink[1] - self.asc_off * scale), max(bot, ink[3] - self.asc_off * scale)
            pos += len(t["text"]) + 1
        return {"text": text, "words": words, "text_w": adv + 2 * self.bord * scale, "pad_x0": x0, "pad_x1": x1,
                "pad_w": x1 - x0, "ink_top": top, "ink_bot": bot}

    def geometry(self, lines, scale):
        """([(line metrics, baseline y)], padded block box) relative to the first baseline y = 0 and x = W/2.

        Line n+1 sits ref 01's line_adv below line n, or lower when the stroked ink of the two lines would come
        closer than a plain caps pair does (a Q tail, a comma or a $ above the next line's caps)."""
        s = scale
        gap = self.line_adv * s - (self.h_ink * s + 2 * self.bord * max(1.0, s))
        out, by, prev = [], 0.0, None
        box = [math.inf, math.inf, -math.inf, -math.inf]
        for li, lt in enumerate(lines):
            lm = self.line_metrics(lt, s)
            if prev is not None:
                by += max(self.line_adv * s, prev["ink_bot"] - lm["ink_top"] + gap)
            for wv in lm["words"]:
                ay = by - self.asc_off * s
                p = wv["padded"]
                box = [min(box[0], wv["ax"] + p[0]), min(box[1], ay + p[1]), max(box[2], wv["ax"] + p[2]),
                       max(box[3], ay + p[3])]
            out.append((lm, by))
            prev = lm
        return out, box

    def fits(self, toks, scale=1.0):
        lm = self.line_metrics(toks, scale)
        return (lm["text_w"] <= self.st["max_width_frac"] * self.w + 1e-6 and
                lm["pad_w"] <= self.safe["x1"] - self.safe["x0"] + 1e-6), lm

    def block_fits_height(self, lines, scale=1.0):
        box = self.geometry(lines, scale)[1]
        return box[3] - box[1] <= self.safe["y1"] - self.safe["y0"] + 1e-6

    def arrange(self, toks):
        """[[tokens per line]] if the chunk fits at scale 1 in <= max_lines lines, else None. A 2-line block that
        is taller than the safe area is rejected (the chunk is re-chunked into 1-line chunks instead)."""
        ok, lm = self.fits(toks)
        if ok:
            return [toks]
        if self.st["max_lines"] >= 2 and len(toks) >= 2:
            best = None
            for k in range(1, len(toks)):
                o1, l1 = self.fits(toks[:k])
                o2, l2 = self.fits(toks[k:])
                if o1 and o2:
                    d = abs(l1["text_w"] - l2["text_w"])
                    if best is None or d < best[0]:
                        best = (d, k)
            if best and self.block_fits_height([toks[:best[1]], toks[best[1]:]]):
                return [toks[:best[1]], toks[best[1]:]]
        return None

    def lone_scale(self, tok):
        lm = self.line_metrics([tok])
        s1 = self.st["max_width_frac"] * self.w / lm["text_w"]
        s2 = (self.safe["x1"] - self.safe["x0"]) / lm["pad_w"]
        s = min(1.0, s1, s2)
        while s > 0.05 and not self.fits([tok], s)[0]:
            s *= 0.995
        return s


def auto_chunks(toks, st):
    """ref 01 section 3 chunking: break after punctuation, at gaps > gap_break, and at max_words."""
    if any(t["brk"] for t in toks):
        chunks, cur = [], []
        for t in toks:
            cur.append(t)
            if t["brk"] or len(cur) >= st["max_words_hard"]:
                chunks.append(cur)
                cur = []
        if cur:
            chunks.append(cur)
        return chunks
    chunks, cur = [], []
    for i, t in enumerate(toks):
        cur.append(t)
        nxt = toks[i + 1] if i + 1 < len(toks) else None
        if (nxt is None or t["text"].endswith(PUNCT_BREAK) or nxt["start"] - t["end"] > st["gap_break"]
                or len(cur) >= st["max_words"]):
            chunks.append(cur)
            cur = []
    return chunks


def fit_chunks(ctx, chunks, warnings):
    """Re-chunk until every chunk fits; returns [{"tokens", "lines", "scale"}]."""
    out = []
    pending = [list(c) for c in chunks]
    while pending:
        ch = pending.pop(0)
        lines = ctx.arrange(ch)
        if lines:
            out.append({"tokens": ch, "lines": lines, "scale": 1.0})
            continue
        if len(ch) == 1:
            s = ctx.lone_scale(ch[0])
            if s < ctx.st["min_scale"]:
                warnings.append(f"token {ch[0]['token']} {ch[0]['text']!r}: scaled to {s:.3f} (< floor "
                                f"{ctx.st['min_scale']}) to stay inside the safe area")
            else:
                warnings.append(f"token {ch[0]['token']} {ch[0]['text']!r}: lone over-wide word scaled to {s:.3f}")
            out.append({"tokens": ch, "lines": [ch], "scale": s})
            continue
        p = 1
        for k in range(len(ch) - 1, 0, -1):
            if ctx.arrange(ch[:k]):
                p = k
                break
        pending.insert(0, ch[p:])
        pending.insert(0, ch[:p])
    return out


def chunk_geometry(ctx, ch):
    """Block geometry relative to the first baseline at y = 0 and the canvas centre x = W/2."""
    return ctx.geometry(ch["lines"], ch["scale"])


def place(ctx, box, pos):
    """(dx, baseline_y) for a block box (relative to centre x, first baseline 0) at position pos, clamped."""
    sf = ctx.safe
    cx = ctx.w / 2
    dx = 0.0
    if cx + box[0] < sf["x0"]:
        dx = sf["x0"] - (cx + box[0])
    if cx + box[2] + dx > sf["x1"]:
        dx = sf["x1"] - (cx + box[2])
    if pos == "mid":
        by = ctx.st["mid_y"] * ctx.h
    elif pos == "low":
        by = sf["y1"] - box[3] if sf["profile"] == "9:16" else ctx.st["low_y"] * ctx.h
    else:
        by = sf["y0"] - box[1]
    by = min(by, sf["y1"] - box[3])
    by = max(by, sf["y0"] - box[1])
    return dx, by


def face_regions(st, boxes):
    """Eyes-to-chin regions of face boxes: box top + eyes_frac x h, grown face_pad on every side (st: a style dict
    or a Ctx)."""
    st = st.st if isinstance(st, Ctx) else st
    out = []
    for x0, y0, x1, y1 in boxes:
        w, h = x1 - x0, y1 - y0
        out.append((x0 - st["face_pad"] * w, y0 + st["eyes_frac"] * h - st["face_pad"] * h,
                    x1 + st["face_pad"] * w, y1 + st["face_pad"] * h))
    return out


def overlap(box, regions):
    a = 0.0
    for r in regions:
        ix = min(box[2], r[2]) - max(box[0], r[0])
        iy = min(box[3], r[3]) - max(box[1], r[1])
        if ix > 0 and iy > 0:
            a += ix * iy
    return a


def _merge_collisions(ctx, chunks, k, warnings):
    """Two chunks whose first words appear on the same frame would flash the first for 0 frames (and a 1-frame
    hold would push every later chunk off the audio): merge them into one chunk when the merged chunk fits."""
    appear = lambda t: max(0, k(t["start"]) - 1)  # noqa: E731
    i = 0
    while i + 1 < len(chunks):
        a, b = chunks[i], chunks[i + 1]
        if appear(b["tokens"][0]) <= appear(a["tokens"][0]) and a["scale"] == 1.0 and b["scale"] == 1.0:
            merged = a["tokens"] + b["tokens"]
            lines = ctx.arrange(merged) if len(merged) <= ctx.st["max_words_hard"] else None
            if lines:
                warnings.append(f"chunks {[t['text'] for t in a['tokens']]} and {[t['text'] for t in b['tokens']]} "
                                "start on the same frame; merged into one chunk")
                chunks[i] = {"tokens": merged, "lines": lines, "scale": 1.0}
                del chunks[i + 1]
                continue
        i += 1
    return chunks


def layout(tokens_obj, w, h, fps=None, frames=None, faces=None, font=None, style=None, safe=None, cuts=None,
           allow_face_cover=False):
    """The whole layout as a dict (see the module docstring); font = load_font(...) result; faces = load_faces(...)
    already on this fps and canvas. Raises face_cover (exit 1) when a chunk cannot avoid a face, unless
    allow_face_cover."""
    st = dict(DEFAULTS)
    st.update(style or {})
    warnings = list(font["warnings"])
    toks, f_fps, f_frames, f_cuts, tw = load_tokens(tokens_obj, font["info"], st["missing_glyph"], st["auto_colour"],
                                                    st["type_s"])
    warnings += tw
    fps = cl.parse_rate(fps or f_fps)
    if not fps:
        raise cl.ClipError("usage", "no frame rate: pass --fps or put 'fps' in the tokens file", exit_code=2)
    if not toks:
        raise cl.ClipError("bad_input", "no caption tokens left after cleanup", exit_code=2)
    k = lambda t: cl.event_frame(t, fps)  # noqa: E731
    n_frames = int(frames or f_frames or k(toks[-1]["end"] + st["hold_after"]) + 1)
    if fps >= 100:
        raise cl.ClipError("usage", f"fps {cl.frac_str(fps)}: ASS centisecond times need < 100 fps", exit_code=2)
    late = [t for t in toks if max(0, k(t["start"]) - 1) >= n_frames]
    if late:
        warnings.append(f"{len(late)} token(s) start at or after the last frame {n_frames} (first: token "
                        f"{late[0]['token']} {late[0]['text']!r} at {late[0]['start']:.3f} s); dropped")
        toks = [t for t in toks if t not in late]
        if not toks:
            raise cl.ClipError("bad_input", "every token starts after the clip end (check --frames/--duration and "
                               "that token times are output seconds)", exit_code=2)
    safe = safe or safe_area(w, h)
    ctx = Ctx(w, h, fps, n_frames, font, st, safe)
    if max(st["shadow_blur_em"], st["glow_blur_em"]) * ctx.em > LIBASS_BLUR_MAX:
        warnings.append(f"a blur exceeds libass's \\blur cap {LIBASS_BLUR_MAX}; it is clamped (softer than asked)")
    if ctx.line_adv * (st["max_lines"] - 1) + ctx.em * 1.5 > safe["y1"] - safe["y0"]:
        warnings.append("the safe area is shorter than a full caption block; blocks will be scaled")
    first = auto_chunks(toks, st)
    keyword_guard(first, warnings)
    for ch in first:  # ref 04 section 1 rule 11: a per-chunk shadow opacity ("shadow" on any token of the chunk)
        shs = [t["shadow"] for t in ch if t["shadow"] is not None]
        for t in ch:
            t["sa"] = max(shs) if shs else None
    chunks = _merge_collisions(ctx, fit_chunks(ctx, first, warnings), k, warnings)
    track = faces or []
    cut_set = set(cuts if cuts is not None else f_cuts)

    # timing (ref 04 section 1 rule 2)
    for ch in chunks:
        ch["appear"] = [max(0, k(t["start"]) - 1) for t in ch["tokens"]]
        ch["start_f"] = ch["appear"][0]
    for i, ch in enumerate(chunks):
        end = k(ch["tokens"][-1]["end"] + st["hold_after"])
        if i + 1 < len(chunks):
            end = min(end, chunks[i + 1]["start_f"])
        else:
            end = n_frames
        if end <= ch["start_f"]:
            end = ch["start_f"] + 1
            if i + 1 < len(chunks) and chunks[i + 1]["start_f"] < end:
                warnings.append(f"chunk {i} ({ch['tokens'][0]['text']!r}) has no frames before the next chunk "
                                "(merged it would not fit); held 1 frame, the next chunk starts 1 frame late")
                chunks[i + 1]["start_f"] = end
                chunks[i + 1]["appear"] = [max(a, end) for a in chunks[i + 1]["appear"]]
        ch["end_f"] = min(end, n_frames)
        ch["appear"] = [min(max(a, ch["start_f"]), max(ch["start_f"], ch["end_f"] - 1)) for a in ch["appear"]]
    gone = [ch for ch in chunks if ch["start_f"] >= n_frames]
    if gone:
        words = [t["text"] for ch in gone for t in ch["tokens"]]
        warnings.append(f"{len(words)} word(s) pushed to or past the last frame {n_frames} by 1-frame holds, dropped "
                        f"(never shown): {words}")
        chunks = [ch for ch in chunks if ch["start_f"] < n_frames]
        if not chunks:
            raise cl.ClipError("bad_input", "no caption chunk starts before the clip end", exit_code=2)

    # geometry and position
    sh, sw = safe["y1"] - safe["y0"], safe["x1"] - safe["x0"]
    for ch in chunks:
        ch["geo"], box = chunk_geometry(ctx, ch)
        if box[3] - box[1] > sh + 1e-6 or box[2] - box[0] > sw + 1e-6:
            for _ in range(400):  # stroke and halo pads do not shrink with the scale: iterate until it fits
                f = min(sh / (box[3] - box[1]), sw / (box[2] - box[0]))
                ch["scale"] *= min(0.98, f * 0.995)
                ch["geo"], box = chunk_geometry(ctx, ch)
                if box[3] - box[1] <= sh + 1e-6 and box[2] - box[0] <= sw + 1e-6:
                    break
            warnings.append(f"chunk {ch['tokens'][0]['text']!r}: block taller/wider than the safe area, scaled "
                            f"to {ch['scale']:.3f}")
        ch["rel_box"] = box
        ch["faces"] = face_regions(st, faces_in(track, ch["start_f"], ch["end_f"]))

    def abs_box(ch, pos, by=None):
        dx, by0 = place(ctx, ch["rel_box"], pos if by is None else "mid")
        by = by0 if by is None else by
        b = ch["rel_box"]
        return (ctx.w / 2 + dx + b[0], by + b[1], ctx.w / 2 + dx + b[2], by + b[3]), dx, by

    def scan(ch, ref_by):
        """Every baseline in the safe band on an 8 px grid (both ends included): the clear one nearest ref_by,
        else the least overlap."""
        lo, hi = safe["y0"] - ch["rel_box"][1], safe["y1"] - ch["rel_box"][3]
        ys = [lo + 8 * j for j in range(int(max(0.0, hi - lo) // 8) + 1)] + [max(lo, hi)]
        best = None
        for y in ys:
            b, dx, by = abs_box(ch, None, y)
            ov = overlap(b, ch["faces"])
            key = (ov > 0, ov, abs(by - ref_by))
            if best is None or key < best[0]:
                best = (key, ("scan", ov, b, dx, by))
        return best[1]

    clear_mid = [overlap(abs_box(ch, "mid")[0], ch["faces"]) == 0 for ch in chunks]
    prev, prev_by = "mid", None
    moved = 0
    covers = []
    for i, ch in enumerate(chunks):
        if any(ch["start_f"] >= c > (chunks[i - 1]["start_f"] if i else -1) for c in cut_set):
            prev = "mid"
        options = []
        for pos in ("mid", "low", "high"):
            b, dx, by = abs_box(ch, pos)
            options.append((pos, overlap(b, ch["faces"]), b, dx, by))
        want = "mid"
        if prev != "mid" and not (clear_mid[i] and (i + 1 >= len(chunks) or clear_mid[i + 1])):
            want = prev if prev in ("low", "high") and options[["mid", "low", "high"].index(prev)][1] == 0 else "low"
        pick = None
        if prev == "scan" and want != "mid":  # keep the previous scanned height while it stays clear
            b, dx, by = abs_box(ch, None, prev_by)
            if overlap(b, ch["faces"]) == 0 and b[1] >= safe["y0"] - 1e-6 and b[3] <= safe["y1"] + 1e-6:
                pick = ("scan", 0.0, b, dx, by)
        if pick is None:
            pick = next((o for o in options if o[0] == want and o[1] == 0), None)
        if pick is None:
            pick = next((o for o in options if o[1] == 0), None)
        if pick is None:  # mid, low and high all meet a face: any clear height in the band
            pick = scan(ch, prev_by if prev == "scan" else options[0][4])
        if pick[1] > 0:
            covers.append((i, pick[1]))
            warnings.append(f"chunk {i} ({ch['tokens'][0]['text']!r}): no height in the safe band clears the faces; "
                            f"least overlap {pick[1]:.0f} px^2 at baseline y {pick[4]:.0f}")
        ch["position"], ch["box"], ch["dx"], ch["by"] = pick[0], pick[2], pick[3], pick[4]
        ch["face_overlap"] = pick[1]
        moved += pick[0] != "mid"
        prev, prev_by = pick[0], pick[4]
    if covers and not allow_face_cover:
        i, ov = covers[0]
        raise cl.ClipError("face_cover", f"{len(covers)} chunk(s) cannot avoid a face anywhere in the safe band "
                           f"(first: chunk {i} {[t['text'] for t in chunks[i]['tokens']]}, overlap {ov:.0f} px^2); "
                           "ref 04 section 1 rule 7 allows 0 frames over a face",
                           hint="split the chunk shorter (brk), reframe wider, or pass --allow-face-cover to accept "
                                "the least-overlap height (caption_gate.py then reports face_cover)")

    # words, absolute
    out_chunks = []
    for ci, ch in enumerate(chunks):
        words = []
        s = ch["scale"]
        for li, (lm, by_rel) in enumerate(ch["geo"]):
            base_y = ch["by"] + by_rel
            for wv in lm["words"]:
                t = wv["tok"]
                ax = ctx.w / 2 + ch["dx"] + wv["ax"]
                ay = base_y - ctx.asc_off * s
                ink, pad = wv["ink"], wv["padded"]
                j = ch["tokens"].index(t)
                ap = ch["appear"][j]
                if t["type_s"] > 0:  # last letter starts at type_s x (n - 1) / n after the event start
                    nl = max(1, sum(not c.isspace() for c in t["text"]))
                    full = ap + math.ceil(t["type_s"] * (nl - 1) / nl * float(fps) - 1e-9) + 1
                else:  # the entrance runs T = round(2000 / fps) ms
                    full = ap + math.ceil(round(2000 / float(fps)) * float(fps) / 1000 - 1e-9)
                full = min(full, ch["end_f"] - 1)
                if t["type_s"] > 0:
                    nw = len(ch["tokens"])
                    floor_s = 0.4 if nw <= 2 else 0.75 * (0.5 + 0.3 * nw)
                    if (ch["end_f"] - full) / float(fps) < floor_s - 1e-9:
                        warnings.append(f"token {t['token']} {t['text']!r}: fully typed for only "
                                        f"{(ch['end_f'] - full) / float(fps):.2f} s (< {floor_s:.2f} s, ref 04 section "
                                        "1 rule 12)")
                words.append({"i": len(words), "token": t["token"], "text": t["text"], "color": t["color"],
                              "line": li, "appear_f": ap, "full_f": full, "end_f": ch["end_f"],
                              "type_s": round(t["type_s"], 3),
                              "shadow_alpha": round(t["sa"] if t.get("sa") is not None else st["shadow_alpha"], 3),
                              "anchor": [round(ax, 2), round(ay, 2)],
                              "origin": [round(ctx.w / 2 + ch["dx"] + wv["left"], 2), round(base_y, 2)],
                              "baseline_center": [round(ax, 2), round(base_y, 2)],
                              "em_px": round(ctx.em * s, 3), "ass_fs": round(ctx.fs, 2), "scale": round(s, 4),
                              "box_ink": [round(ax + ink[0], 1), round(ay + ink[1], 1), round(ax + ink[2], 1),
                                          round(ay + ink[3], 1)],
                              "box": [round(ax + pad[0], 1), round(ay + pad[1], 1), round(ax + pad[2], 1),
                                      round(ay + pad[3], 1)]})
        out_chunks.append({"i": ci, "start_f": ch["start_f"], "end_f": ch["end_f"], "position": ch["position"],
                           "scale": round(s, 4), "lines": [lm["text"] for lm, _ in ch["geo"]],
                           "box": [round(v, 1) for v in ch["box"]],
                           "faces": [[round(v, 1) for v in r] for r in ch["faces"]],
                           "face_overlap": round(ch["face_overlap"], 1), "words": words})

    sf = safe
    worst = min(min(w["box"][0] - sf["x0"], w["box"][1] - sf["y0"], sf["x1"] - w["box"][2], sf["y1"] - w["box"][3])
                for c in out_chunks for w in c["words"])
    if worst < -0.05:
        raise cl.ClipError("layout_overflow", f"internal: a word box leaves the safe area by {-worst:.1f} px",
                           hint="report this input; the fit should make it impossible")
    info = font["info"]
    return {"ok": True, "version": SCRIPT_VERSION, "canvas": {"w": w, "h": h}, "fps": cl.frac_str(fps),
            "frames": n_frames,
            "font": {"path": font["path"], "fontsdir": font["fontsdir"], "ass_fontname": font["fontname"],
                     "family": info.family, "postscript": (info.names.get(6) or [None])[0], "weight": info.weight,
                     "how": font["how"], "units_per_em": info.upm, "win_ascent": info.win_asc,
                     "win_descent": info.win_desc, "cap_ratio": round(ctx.cap_ratio, 4), "em_px": round(ctx.em, 3),
                     "ass_fs": round(ctx.fs, 2), "cap_px": round(ctx.em * ctx.cap_ratio, 2),
                     "anchor_to_baseline_px": round(ctx.asc_off, 3), "pillow_layout": ctx.m.engine},
            "style": {k2: (list(v) if isinstance(v, tuple) else v) for k2, v in st.items()},
            "safe": safe,
            "pads": {"bord_px": round(ctx.bord, 2), "halo_white_px": [round(v, 2) for v in ctx.pad_white],
                     "entrance_scale_max": ctx.scale_max, "ink_thr": st["ink_thr"]},
            "chunks": out_chunks,
            "stats": {"tokens": len(toks), "chunks": len(out_chunks),
                      "words": sum(len(c["words"]) for c in out_chunks),
                      "two_line_chunks": sum(len(c["lines"]) > 1 for c in out_chunks),
                      "scaled_words": sum(c["scale"] < 1 for c in out_chunks), "moved_for_face": moved,
                      "face_cover_chunks": len(covers),
                      "min_margin_px": round(worst, 1)},
            "warnings": warnings}


# ---------------------------------------------------------------- ASS

def ass_time(k, fps):
    """Frame k as ASS H:MM:SS.cc: the largest whole centisecond strictly before frame k's time (0 for k = 0).

    ffmpeg's ass filter hands libass trunc(pts x time_base x 1000) ms, which lands 1 ms below an exact
    centisecond on some frames; a start on that exact centisecond (ref 04 section 1 rule 2's floor) then shows a
    frame late (23/1200 frames at 30 and 60 fps, 3/1200 at 25 and 50). Valid below 100 fps.
    """
    f = Fraction(fps)
    n, d = 100 * int(k) * f.denominator, f.numerator
    cs = 0 if k <= 0 else -(-n // d) - 1
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def _alpha(opacity):
    return f"&H{max(0, min(255, round(255 * (1 - opacity)))):02X}&"


def filter_escape(value):
    """A value (a path) for an ffmpeg filter option, escaped for both levels of filtergraph parsing (ffmpeg-filters,
    "Notes on filtergraph escaping"): the option level escapes \\ ' :, then the graph level escapes \\ ' [ ] , ;.
    Use the result in one argv element of -vf / -filter_complex (no shell) or inside a -filter_complex_script."""
    v = str(value).replace("\\", "/")
    v = "".join("\\" + c if c in "\\':" else c for c in v)
    return "".join("\\" + c if c in "\\'[],;" else c for c in v)


def burn_info(ass_path, fontsdir):
    """{"cwd", "fontsdir", "filter"}: run ffmpeg with cwd = the ASS folder and -vf <filter> (ref 03 section 4 rule 8:
    bare relative names; a raw C:/ path does not parse). fontsdir is relative when it sits under the ASS folder."""
    ass_path = Path(ass_path).resolve()
    cwd = ass_path.parent
    fd = Path(fontsdir).resolve()
    try:
        rel = fd.relative_to(cwd).as_posix() or "."
    except ValueError:
        rel = fd.as_posix()
    return {"cwd": str(cwd), "fontsdir": rel,
            "filter": f"ass={filter_escape(ass_path.name)}:fontsdir={filter_escape(rel)}"}


def write_ass(lay, path):
    st, fps = lay["style"], cl.parse_rate(lay["fps"])
    w, h = lay["canvas"]["w"], lay["canvas"]["h"]
    em = lay["font"]["em_px"]
    T = round(2000 / float(fps))
    fs = lay["font"]["ass_fs"]
    bord = st["bord_em"] * em
    sb = min(LIBASS_BLUR_MAX, st["shadow_blur_em"] * em)
    gb = min(LIBASS_BLUR_MAX, st["glow_blur_em"] * em)
    ox, oy = (v * em for v in st["shadow_offset_em"])
    e0, ep = st["entrance_from"], st["entrance_peak"]
    lines = ["[Script Info]",
             f"; captions.py {SCRIPT_VERSION} (clipping-edit). Burn: the layout JSON's burn.filter with cwd = burn.cwd",
             f"; font: {lay['font']['path']}",
             f"; safe area: {lay['safe']['x0']},{lay['safe']['y0']},{lay['safe']['x1']},{lay['safe']['y1']} "
             f"({lay['safe']['profile']})",
             "ScriptType: v4.00+", f"PlayResX: {w}", f"PlayResY: {h}", "WrapStyle: 2",
             "ScaledBorderAndShadow: yes", "",
             "[V4+ Styles]",
             "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
             "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
             "MarginL, MarginR, MarginV, Encoding",
             f"Style: Cap,{lay['font']['ass_fontname']},{fs:.2f},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,"
             "100,100,0,0,1,0,0,5,0,0,0,1", "",
             "[Events]",
             "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]

    def entrance(op, s, blur_in):
        a0, a1 = _alpha(op / 3), _alpha(op)
        sc0, sc1, scp = 100 * s * e0, 100 * s, 100 * s * ep
        bi = f"\\blur{blur_in}" if blur_in else ""
        bo = "\\blur0" if blur_in else ""
        if ep > 1.0:
            half = max(1, T // 2)
            return (f"\\alpha{a0}\\fscx{sc0:.2f}\\fscy{sc0:.2f}{bi}\\t(0,{half},\\alpha{a1}\\fscx{scp:.2f}"
                    f"\\fscy{scp:.2f}{bo})\\t({half},{T},\\fscx{sc1:.2f}\\fscy{sc1:.2f})")
        return f"\\alpha{a0}\\fscx{sc0:.2f}\\fscy{sc0:.2f}{bi}\\t(0,{T},\\alpha{a1}\\fscx{sc1:.2f}\\fscy{sc1:.2f}{bo})"

    def typed(op, s, text, dur_ms):
        """Letter by letter (ref 01 section 3 stage directions): one override block per character, so the event
        keeps one \\pos and one advance (the layout's box); letter i of n turns on at dur x i / n."""
        a1 = _alpha(op)
        nl = max(1, sum(not c.isspace() for c in text))
        out, li = [], 0
        for c in text:
            if c.isspace():
                out.append(c)
                continue
            t = round(dur_ms * li / nl)
            out.append(f"{{\\alpha&HFF&\\t({t},{t + 1},\\alpha{a1})}}{c}")
            li += 1
        return f"\\fscx{100 * s:.2f}\\fscy{100 * s:.2f}", "".join(out)

    n = 0
    for ch in lay["chunks"]:
        for wd in ch["words"]:
            s = wd["scale"]
            x, y = wd["anchor"]
            t0, t1 = ass_time(wd["appear_f"], fps), ass_time(wd["end_f"], fps)
            name = f"c{ch['i']}w{wd['i']}"
            common = f"\\an5\\fs{fs:.2f}\\fsp0\\shad0\\q2"
            sa = wd.get("shadow_alpha", st["shadow_alpha"])
            dur = round(1000 * wd.get("type_s", 0.0))
            layers = [(0, f"\\pos({x + ox:.2f},{y + oy:.2f})\\bord{bord:.2f}\\blur{sb:.2f}\\1c&H000000&\\3c&H000000&",
                       sa, 0)]
            if wd["color"] != "#FFFFFF":
                c = ass_colour(wd["color"])
                layers.append((1, f"\\pos({x:.2f},{y:.2f})\\bord{bord:.2f}\\blur{gb:.2f}\\1c{c}\\3c{c}",
                               st["glow_alpha"], 0))
            layers.append((2, f"\\pos({x:.2f},{y:.2f})\\bord{bord:.2f}\\1c{ass_colour(wd['color'])}\\3c&H000000&",
                           1.0, 4))
            for layer, tags, op, blur_in in layers:
                if dur > 0:
                    head, body = typed(op, s, wd["text"], dur)
                else:
                    head, body = entrance(op, s, blur_in), wd["text"]
                lines.append(f"Dialogue: {layer},{t0},{t1},Cap,{name},0,0,0,,{{{common}{tags}{head}}}{body}")
                n += 1
    tmp = cl.tmp_path(path)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    cl.replace_with_retry(tmp, path)
    return n


# ---------------------------------------------------------------- self-test (layout level, no ffmpeg)

SELFTEST_SENTENCE = ("SO THE INTERNATIONALLY RECOGNIZED CHAMPIONSHIP ORGANIZERS ABSOLUTELY REFUSED TO "
                     "ACKNOWLEDGE THAT EXTRAORDINARY PERFORMANCE WHATSOEVER BROTHER")


def selftest_tokens(words, dt=0.32, brk_every=None, colours=None, extra=None):
    toks = []
    for i, wd in enumerate(words):
        t = {"d": wd, "start": round(0.2 + i * dt, 3), "end": round(0.2 + i * dt + dt * 0.8, 3)}
        if brk_every and (i + 1) % brk_every == 0:
            t["brk"] = True
        if colours and i in colours:
            t["c"] = colours[i]
        if extra and i in extra:
            t.update(extra[i])
        toks.append(t)
    return {"tokens": toks}


def selftest_cases():
    """(name, canvas, tokens obj, faces obj or None, style overrides, checks) shared with caption_gate.py.
    checks["allow_cover"]: a case that cannot avoid the face (laid out with allow_face_cover; the gate must FAIL)."""
    long_words = ["UNBELIEVABLEEEEEEE", "SUPERCALIFRAGILISTIC", "SUPERCALIFRAGILISTICEXPIALIDOCIOUS"]
    money = ["HE", "PAID", "$100,000,000", "FOR", "+$1,000,000", "AND", "100%", "IN", "2026"]
    sent = SELFTEST_SENTENCE.split()
    face_mid = {"fps": "30/1", "boxes": [[0, 390, 560, 690, 1000]]}
    face_mid_wide = {"0": [140, 1300, 800, 700]}
    face_low = {"fps": "30/1", "boxes": [[0, 300, 800, 780, 1500]]}
    n_cp = 120  # a 1920x1080 source cropped to 1080x1920: face at source (820, 250) 280x330 -> canvas y 444-1031
    crop_path = {"kind": "crop_path", "fps": "30/1", "src": [1920, 1080], "out": [1080, 1920],
                 "frames_data": {"cx": [960.0] * n_cp, "cy": [540.0] * n_cp, "cw": [607.5] * n_cp,
                                 "ch": [1080.0] * n_cp},
                 "face": {"x": [820.0] * n_cp, "y": [250.0] * n_cp, "w": [280.0] * n_cp, "h": [330.0] * n_cp}}
    two_shot = {"fps": "30/1", "boxes": [[0, 300, 80, 640, 560], [0, 420, 760, 800, 1340]]}
    face_everywhere = {"fps": "30/1", "boxes": [[0, 100, -1000, 980, 2000]]}
    staged = ["*LAUGHS*", "NO", "WAY", "BRO", "*FAILS*", "AGAIN"]
    return [
        ("long_words_9x16", (1080, 1920), selftest_tokens(long_words, brk_every=1, colours={0: "yellow"}), None, {},
         {"scaled": 3, "below_floor": 1}),
        ("long_sentence_9x16_6word_chunks", (1080, 1920), selftest_tokens(sent, brk_every=6,
                                                                           colours={2: "green", 9: "red"}), None,
         {}, {"rechunk": True}),
        ("numbers_9x16", (1080, 1920), selftest_tokens(money, brk_every=3), None, {}, {}),
        ("long_words_16x9", (1920, 1080), selftest_tokens(long_words + sent[:8], brk_every=4), None, {}, {}),
        ("long_words_1x1", (1080, 1080), selftest_tokens(long_words + money, brk_every=3), None, {}, {}),
        ("sentence_3x4", (1080, 1440), selftest_tokens(sent, colours={4: "magenta"}), None, {}, {}),
        ("low_two_lines_face_9x16", (1080, 1920), selftest_tokens(sent[:12], brk_every=6, colours={1: "cyan"}),
         face_mid, {}, {"position": "low", "two_lines": True}),
        ("face_over_centre_16x9", (1920, 1080), selftest_tokens(money + sent[:6], brk_every=3),
         {"fps": "30/1", "boxes": [[0, 760, 300, 1160, 700]]}, {}, {"position": "low"}),
        ("face_low_goes_high_9x16", (1080, 1920), selftest_tokens(sent[:8], brk_every=4), face_low, {},
         {"position": "high"}),
        ("face_wide_dict_form_9x16", (1080, 1920), selftest_tokens(sent[:8], brk_every=4), face_mid_wide, {}, {}),
        ("face_track_crop_path_9x16", (1080, 1920), selftest_tokens(sent[:8], brk_every=4), crop_path, {},
         {"position": "low"}),
        ("big_entrance_overshoot_9x16", (1080, 1920), selftest_tokens(long_words[:2] + sent[:8], brk_every=4), None,
         {"entrance_peak": 1.12, "entrance_from": 0.80}, {}),
        ("two_shot_scan_9x16", (1080, 1920), selftest_tokens(["WE", "WENT", "THERE", "AND", "CAME", "BACK"],
                                                              brk_every=3), two_shot, {}, {"position": "scan"}),
        ("descender_lines_9x16", (1080, 1920), selftest_tokens(["QUICK,", "JUMPY", "QUARTZ,", "$900"], brk_every=4),
         None, {}, {"two_lines": True, "position": "mid"}),
        ("typed_stage_directions_shadow_9x16", (1080, 1920),
         selftest_tokens(staged, dt=0.4, brk_every=2, colours={0: "yellow", 4: "red"},
                         extra={2: {"shadow": 0.75}}), None, {}, {"typed": 2, "shadow": 0.75}),
        ("face_unavoidable_allowed_9x16", (1080, 1920), selftest_tokens(sent[:4], brk_every=2), face_everywhere, {},
         {"allow_cover": True}),
    ]


def _check_layout(lay, checks):
    errs = []
    sf = lay["safe"]
    for c in lay["chunks"]:
        for wd in c["words"]:
            b = wd["box"]
            if b[0] < sf["x0"] - 0.05 or b[1] < sf["y0"] - 0.05 or b[2] > sf["x1"] + 0.05 or b[3] > sf["y1"] + 0.05:
                errs.append(f"word {wd['text']!r} box {b} leaves the safe area")
            if not wd["appear_f"] <= wd["full_f"] < wd["end_f"] <= lay["frames"]:
                errs.append(f"word {wd['text']!r} frames {wd['appear_f']}/{wd['full_f']}/{wd['end_f']} not inside "
                            f"0..{lay['frames']}")
        if len(c["lines"]) > lay["style"]["max_lines"]:
            errs.append(f"chunk {c['i']} has {len(c['lines'])} lines")
        if c["face_overlap"] > 0 and not checks.get("allow_cover"):
            errs.append(f"chunk {c['i']} overlaps a face by {c['face_overlap']} px^2")
        for wa in c["words"]:  # stroked ink of words on different lines never touches
            for wb in c["words"]:
                if wb["line"] == wa["line"] + 1 and overlap(wa["box_ink"], [wb["box_ink"]]) > 0:
                    errs.append(f"lines collide: {wa['text']!r} {wa['box_ink']} and {wb['text']!r} {wb['box_ink']}")
    st = lay["stats"]
    if "scaled" in checks and st["scaled_words"] < checks["scaled"]:
        errs.append(f"expected >= {checks['scaled']} scaled words, got {st['scaled_words']}")
    if "below_floor" in checks:
        n = sum("< floor" in w for w in lay["warnings"])
        if n < checks["below_floor"]:
            errs.append(f"expected {checks['below_floor']} below-floor warnings, got {n}")
    if checks.get("rechunk") and st["chunks"] <= math.ceil(st["tokens"] / 6):
        errs.append("expected re-chunking of over-wide 6-word chunks")
    if "position" in checks and not any(c["position"] == checks["position"] for c in lay["chunks"]):
        errs.append(f"expected a chunk at {checks['position']}, got {[c['position'] for c in lay['chunks']]}")
    if checks.get("two_lines") and not any(len(c["lines"]) == 2 and c["position"] == checks.get("position", "mid")
                                           for c in lay["chunks"]):
        errs.append("expected a two-line chunk at the checked position")
    if "typed" in checks:
        typed = [wd for c in lay["chunks"] for wd in c["words"] if wd["type_s"] > 0]
        if len(typed) != checks["typed"] or any(wd["full_f"] - wd["appear_f"] < 8 for wd in typed):
            errs.append(f"expected {checks['typed']} typed words fully drawn >= 8 frames after appear, got "
                        f"{[(wd['text'], wd['appear_f'], wd['full_f']) for wd in typed]}")
    if "shadow" in checks:
        sh = {wd["shadow_alpha"] for c in lay["chunks"] for wd in c["words"]
              if any(x["text"] == "WAY" for x in c["words"])}
        if sh != {checks["shadow"]}:
            errs.append(f"expected the chunk holding WAY at shadow {checks['shadow']}, got {sh}")
    if checks.get("allow_cover") and not st["face_cover_chunks"]:
        errs.append("expected an unavoidable face cover")
    return errs


def _unit_checks(font):
    """Regression checks of single rules (layout level): [(name, ok, detail)]."""
    out = []

    def lay(tokens, w=1080, h=1920, fps="30/1", frames=None, faces=None, **kw):
        return layout(tokens, w, h, fps, frames, faces, font, kw.pop("style", None), kw.pop("safe", None), **kw)

    def words(lt):
        return [(wd["text"], wd["color"]) for c in lt["chunks"] for wd in c["words"]]

    # face files on another clock are remapped by time (a 30 fps track under 60 fps captions)
    toks = selftest_tokens(["ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX"], dt=0.6, brk_every=1)
    f30 = {"fps": "30/1", "boxes": [[0, None], [60, 390, 560, 690, 1000], [90, None]]}
    f60 = {"fps": "60/1", "boxes": [[0, None], [120, 390, 560, 690, 1000], [180, None]]}
    p30 = [c["position"] for c in lay(toks, fps="60/1", faces=load_faces(f30, "60/1", (1080, 1920)))["chunks"]]
    p60 = [c["position"] for c in lay(toks, fps="60/1", faces=load_faces(f60, "60/1", (1080, 1920)))["chunks"]]
    out.append(("faces_fps_remapped", p30 == p60 and "low" in p60 and p60[0] == "mid", f"30 fps file {p30}, "
                f"60 fps file {p60}"))
    cp = {"kind": "crop_path", "fps": "25/1", "out": [1080, 1920],
          "frames_data": {"cx": [960.0] * 150, "cy": [540.0] * 150, "cw": [607.5] * 150, "ch": [1080.0] * 150},
          "face": {"x": [820.0] * 125 + [None] * 25, "y": [250.0] * 150, "w": [280.0] * 150, "h": [330.0] * 150}}
    lt = lay({"tokens": [{"d": "STILL", "start": 4.4, "end": 4.6}, {"d": "TALKING", "start": 4.6, "end": 4.9}]},
             frames=180, faces=load_faces(cp, "30/1", (1080, 1920)))
    out.append(("crop_path_25fps_under_30fps", lt["chunks"][0]["position"] != "mid" and
                lt["chunks"][0]["face_overlap"] == 0, f"position {lt['chunks'][0]['position']}"))
    # simultaneous brk tokens at the clip end: merged, never pushed past N
    lt = lay({"tokens": [{"d": d, "start": 1.9, "end": 2.0, "brk": True} for d in
                         ["YEAH", "RIGHT", "OKAY", "BYE", "END"]]}, frames=60)
    shown = [wd["text"] for c in lt["chunks"] for wd in c["words"] if wd["appear_f"] < 60]
    out.append(("simultaneous_tokens_at_clip_end", shown == ["YEAH", "RIGHT", "OKAY", "BYE", "END"] and
                all(c["end_f"] <= 60 and c["end_f"] - c["start_f"] >= 2 for c in lt["chunks"]),
                f"chunks {[(c['lines'], c['start_f'], c['end_f']) for c in lt['chunks']]}"))
    lt = lay({"tokens": [{"d": d, "start": 0.25 + 0.005 * i, "end": 0.3, "brk": True}
                         for i, d in enumerate(["A1", "B2", "C3", "D4", "STOP"])]}, frames=10)
    allw = [wd for c in lt["chunks"] for wd in c["words"]]
    out.append(("hold_chain_never_past_clip_end", all(wd["appear_f"] < 10 and wd["end_f"] <= 10 for wd in allw)
                and len(allw) == 5, f"{[(wd['text'], wd['appear_f'], wd['end_f']) for wd in allw]}"))
    # keyword guard: THE is guarded; a coloured phrase or a whole coloured chunk keeps its colour
    lt = lay({"tokens": [{"d": "THE", "start": 0.2, "end": 0.4, "c": "green"},
                         {"d": "DO", "start": 0.4, "end": 0.6, "c": "yellow", "brk": True}]})
    out.append(("guard_the_and_isolated_do", words(lt) == [("THE", "#FFFFFF"), ("DO", "#FFFFFF")], f"{words(lt)}"))
    toks = [("WHATEVER", "yellow"), ("I", "yellow"), ("DO", "yellow"), ("WHAT", "magenta"), ("ARE", "magenta"),
            ("YOU", "magenta"), ("DOING", "magenta")]
    lt = lay({"tokens": [{"d": d, "start": 0.2 + 0.3 * i, "end": 0.45 + 0.3 * i, "c": c, "brk": i in (2, 6)}
                         for i, (d, c) in enumerate(toks)]})
    out.append(("guard_keeps_coloured_phrases", [c for _, c in words(lt)] == [COLOURS[c] for _, c in toks],
                f"{words(lt)}"))
    # symbols the font has stay; real emoji (incl. U+203C) are dropped
    w = []
    s1 = clean_text("72\u00b0F \u00a92026 WOW\u2122 R&D\u00ae", font["info"], "fail", w, "t")
    s2 = clean_text("LET'S GO \u203c\ufe0f", font["info"], "fail", w, "t")
    out.append(("symbols_kept_emoji_dropped", s1 == "72\u00b0F \u00a92026 WOW\u2122 R&D\u00ae" and s2 == "LET'S GO",
                f"{s1!r} {s2!r}"))
    # a tight custom safe area fits (1-line re-chunk, iterated block scale) instead of an internal error
    try:
        lt = lay(selftest_tokens(["HELLO", "WORLD", "THIS", "IS", "FINE"]), frames=60,
                 safe=safe_area(1080, 1920, rect=(65, 900, 950, 1060)))
        out.append(("tight_custom_safe_area", lt["stats"]["min_margin_px"] >= 0, f"{lt['stats']}"))
    except cl.ClipError as e:
        out.append(("tight_custom_safe_area", False, f"{e.code}: {e.message}"))
    # unavoidable face cover is an error unless allowed
    try:
        lay(selftest_tokens(["WE", "WENT"]), faces=load_faces({"0": [100, -1000, 880, 3000]}))
        out.append(("face_cover_exit1", False, "no error"))
    except cl.ClipError as e:
        out.append(("face_cover_exit1", e.code == "face_cover" and e.exit_code == 1, e.code))
    # the burn filter escapes both filtergraph levels (ffmpeg-filters: ' -> \' -> \\\', : -> \: -> \\:)
    fe = filter_escape("C:/it's job, [x]/captions.ass")
    out.append(("filter_escape", fe == "C\\\\:/it\\\\\\'s job\\, \\[x\\]/captions.ass", fe))
    return out


def selftest(args):
    font = load_font(args.font, args.fontsdir)
    results, ok = [], True
    for name, (w, h), toks, faces, style, checks in selftest_cases():
        lay = layout(toks, w, h, "30/1", None, load_faces(faces, "30/1", (w, h)) if faces else None, font, style,
                     safe_area(w, h), allow_face_cover=bool(checks.get("allow_cover")))
        errs = _check_layout(lay, checks)
        results.append({"case": name, "ok": not errs, "errors": errs, "stats": lay["stats"],
                        "positions": [c["position"] for c in lay["chunks"]]})
        ok &= not errs
        cl.log(f"{'ok  ' if not errs else 'FAIL'} {name} {lay['stats']}" + ("" if not errs else f" {errs}"))
    for name, good, detail in _unit_checks(font):
        results.append({"case": name, "ok": bool(good), "detail": detail})
        ok &= bool(good)
        cl.log(f"{'ok  ' if good else 'FAIL'} {name}: {detail}")
    # CLI exit codes: missing font, unknown fontname, uncovered glyph
    work = Path(tempfile.mkdtemp(prefix="captions-selftest-"))
    try:
        tok = work / "t.json"
        cl.write_json_atomic(tok, selftest_tokens(["HELLO", "WORLD"]))
        me = [sys.executable, "-P", os.path.abspath(__file__), "--tokens", str(tok), "--canvas", "1080x1920",
              "--fps", "30", "--layout", str(work / "l.json"), "--ass", str(work / "c.ass")]
        extra = ["--font", font["path"]]
        cases = [("missing_font_exit1", me + ["--font", str(work / "NoSuchFont-Black.ttf")], 1),
                 ("fontname_mismatch_exit1", me + extra + ["--fontname", "Montserrat Blak"], 1),
                 ("not_a_font_exit1", me + ["--font", str(tok)], 1),
                 ("clean_run_exit0", me + extra, 0)]
        ps = (font["info"].names.get(6) or [None])[0]
        if ps and ps != font["info"].family:
            cases.append(("fontname_postscript_exit1", me + extra + ["--fontname", ps], 1))
        typo = (font["info"].names.get(16) or [None])[0]
        if typo and typo != font["info"].family:
            cases.append(("fontname_typographic_family_exit1", me + extra + ["--fontname", typo], 1))
        tok2 = work / "t2.json"
        cl.write_json_atomic(tok2, selftest_tokens(["HELLO", "\u4e16\u754c"]))
        cases.append(("uncovered_glyph_exit1", [*me[:4], str(tok2), *me[5:], *extra], 1))
        cases.append(("uncovered_glyph_drop_exit0", [*me[:4], str(tok2), *me[5:], *extra, "--missing-glyph", "drop"],
                      0))
        tok3 = work / "t3.json"
        cl.write_json_atomic(tok3, selftest_tokens(["FIRE\U0001F525", "\U0001F480", "GO\u203c"]))
        cases.append(("emoji_dropped_exit0", [*me[:4], str(tok3), *me[5:], *extra], 0))
        tok4 = work / "t4.json"
        cl.write_json_atomic(tok4, selftest_tokens(["WE", "WENT"]))
        fc = work / "faces.json"
        cl.write_json_atomic(fc, {"0": [100, -1000, 880, 3000]})
        cases.append(("face_cover_exit1", [*me[:4], str(tok4), *me[5:], *extra, "--faces", str(fc)], 1))
        cases.append(("face_cover_allowed_exit0", [*me[:4], str(tok4), *me[5:], *extra, "--faces", str(fc),
                                                   "--allow-face-cover"], 0))
        for cname, cmd, want in cases:
            cp = subprocess.run(cmd, capture_output=True, env={**os.environ, "PYTHONIOENCODING": "utf8"})
            good = cp.returncode == want
            results.append({"case": cname, "ok": good, "exit": cp.returncode, "want": want})
            ok &= good
            cl.log(f"{'ok  ' if good else 'FAIL'} {cname} exit {cp.returncode} (want {want})")
        # the clean run copied the font next to the ASS and wrote a relative burn filter
        import json
        lj = json.loads((work / "l.json").read_text(encoding="utf-8")) if (work / "l.json").is_file() else {}
        copied = (work / "fonts" / Path(font["path"]).name).is_file()
        good = (lj.get("burn") or {}).get("fontsdir") == "fonts" and copied
        results.append({"case": "burn_filter_relative_fontsdir", "ok": good, "burn": lj.get("burn")})
        ok &= good
        cl.log(f"{'ok  ' if good else 'FAIL'} burn_filter_relative_fontsdir {lj.get('burn')}")
    finally:
        if not args.keep_temp:
            shutil.rmtree(work, ignore_errors=True)
    return {"ok": ok, "version": SCRIPT_VERSION, "font": font["path"], "passed": sum(r["ok"] for r in results),
            "failed": sum(not r["ok"] for r in results), "selftest": results}


# ---------------------------------------------------------------- CLI

class _Parser(argparse.ArgumentParser):
    def error(self, message):  # keep the one-JSON-object stdout contract on usage errors
        raise cl.ClipError("usage", message, hint=self.format_usage().strip(), exit_code=2)


def _floats(s, n, what):
    try:
        v = [float(x) for x in str(s).split(",")]
        if len(v) != n:
            raise ValueError
        return v
    except ValueError:
        raise cl.ClipError("usage", f"{what} needs {n} comma-separated numbers, got {s!r}", exit_code=2)


def add_safe_args(ap):
    ap.add_argument("--profile", default="auto", help="safe-area profile: auto, 9:16, 3:4, 1:1, 16:9")
    ap.add_argument("--margins", help="l,t,r,b fractions of W,H,W,H (replaces the profile's margins)")
    ap.add_argument("--safe", help="x0,y0,x1,y1 canvas px (replaces the profile)")


def safe_from_args(args, w, h):
    return safe_area(w, h, args.profile, _floats(args.margins, 4, "--margins") if args.margins else None,
                     _floats(args.safe, 4, "--safe") if args.safe else None)


def main() -> int:
    try:
        return _run()
    except cl.ClipError as e:  # the JSON envelope carries the version too
        env = e.envelope()
        env["version"] = SCRIPT_VERSION
        cl.emit(env)
        cl.log(f"error [{e.code}]: {e.message}" + (f"\nhint: {e.hint}" if e.hint else ""))
        return e.exit_code


def _run():
    ap = _Parser(description="Caption layout inside the safe area -> ASS + layout JSON (ref 07).")
    ap.add_argument("--tokens")
    ap.add_argument("--canvas", help="WxH, e.g. 1080x1920")
    ap.add_argument("--fps", help="output frame rate (default: the tokens file's fps)")
    ap.add_argument("--frames", type=int, help="output frame count N (the last chunk ends at N)")
    ap.add_argument("--duration", help="output seconds (frames = round(duration x fps))")
    ap.add_argument("--faces", help="face boxes JSON (forms in the docstring)")
    ap.add_argument("--font")
    ap.add_argument("--fontsdir", help="folder searched first for the font; also the fontsdir to burn with")
    ap.add_argument("--fontname", help="ASS Fontname (default: the font's legacy family name)")
    ap.add_argument("--ass", help="write the ASS here")
    ap.add_argument("--layout", help="write the layout JSON here")
    add_safe_args(ap)
    for k, v in DEFAULTS.items():
        if k in ("shadow_offset_em", "auto_colour", "missing_glyph"):
            continue
        ap.add_argument("--" + k.replace("_", "-"), type=type(v), default=v)
    ap.add_argument("--shadow-offset-em", default="0,0", help="x,y shadow offset in em (ref 01: 0,0)")
    ap.add_argument("--no-auto-colour", action="store_true", help="no default cyan on digit/$/%% tokens")
    ap.add_argument("--missing-glyph", choices=["fail", "drop"], default="fail")
    ap.add_argument("--allow-face-cover", action="store_true",
                    help="accept the least-overlap height when no height in the safe band clears the faces")
    ap.add_argument("--no-font-copy", action="store_true",
                    help="do not copy the font into <ass folder>/fonts (burn.fontsdir is then the absolute folder)")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--keep-temp", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        res = selftest(args)
        cl.emit(res)
        return 0 if res["ok"] else 1
    missing = [f"--{n}" for n in ("tokens", "canvas") if not getattr(args, n)]
    if missing:
        ap.error(f"the following arguments are required: {', '.join(missing)} (or --self-test)")
    w, h = parse_canvas(args.canvas)
    style = {k: getattr(args, k) for k in DEFAULTS if k not in ("shadow_offset_em", "auto_colour", "missing_glyph")}
    style["shadow_offset_em"] = tuple(_floats(args.shadow_offset_em, 2, "--shadow-offset-em"))
    style["auto_colour"] = not args.no_auto_colour
    style["missing_glyph"] = args.missing_glyph
    if not (0 < style["min_scale"] <= 1) or style["max_lines"] < 1 or style["max_words"] < 1:
        raise cl.ClipError("usage", "--min-scale must be in (0, 1], --max-lines and --max-words >= 1", exit_code=2)
    font = load_font(args.font, args.fontsdir, args.fontname)
    obj = cl.read_json(args.tokens)
    fps = args.fps or (obj.get("fps") if isinstance(obj, dict) else None)
    frames = args.frames
    if frames is None and args.duration:
        r = cl.parse_rate(fps)
        if not r:
            raise cl.ClipError("usage", "--duration needs --fps", exit_code=2)
        frames = int(math.floor(_num(args.duration, "--duration") * float(r) + 0.5))
    face_warn = []
    if args.faces:
        r = cl.parse_rate(fps)
        if not r:
            raise cl.ClipError("usage", "--faces needs the output frame rate (--fps or the tokens file's fps)",
                               exit_code=2)
        faces = load_faces(cl.read_json(args.faces), r, (w, h), face_warn)
    else:
        faces = None
    if args.ass and not args.no_font_copy:
        # ref 03 section 4 rule 8: the burn runs in the ASS folder with fontsdir=fonts (a relative name)
        fdir = Path(args.ass).resolve().parent / "fonts"
        fdir.mkdir(parents=True, exist_ok=True)
        dst = fdir / Path(font["path"]).name
        if not dst.is_file() or dst.stat().st_size != Path(font["path"]).stat().st_size:
            tmp = cl.tmp_path(dst)
            shutil.copyfile(font["path"], tmp)
            cl.replace_with_retry(tmp, dst)
        font = {**font, "fontsdir": str(fdir)}
    lay = layout(obj, w, h, fps, frames, faces, font, style, safe_from_args(args, w, h),
                 allow_face_cover=args.allow_face_cover)
    lay["warnings"] = face_warn + lay["warnings"]
    if args.ass:
        lay["ass"] = str(args.ass)
        lay["ass_events"] = write_ass(lay, args.ass)
        lay["burn"] = burn_info(args.ass, lay["font"]["fontsdir"])
    else:
        lay["ass"] = None
    lay["layout"] = str(args.layout) if args.layout else None
    if args.layout:
        cl.write_json_atomic(args.layout, lay)
    for wmsg in lay["warnings"]:
        cl.log(f"warning: {wmsg}")
    cl.log(f"captions {lay['stats']['chunks']} chunks, {lay['stats']['words']} words, "
           f"min margin {lay['stats']['min_margin_px']} px, safe {lay['safe']['profile']} "
           f"{lay['safe']['x0']},{lay['safe']['y0']},{lay['safe']['x1']},{lay['safe']['y1']}")
    cl.emit(lay)
    return 0


if __name__ == "__main__":
    cl.run_main(main)
