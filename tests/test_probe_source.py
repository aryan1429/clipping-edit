"""Tests for skill/scripts/probe_source.py (run: python -P tests/test_probe_source.py from the repo root).

Runs the real CLI as a subprocess on synthetic sources (lavfi, built here and with tests/fixtures.py): 60 fps,
30000/1001, 60000/1001, VFR, rotated, SAR 4:3, BT.601-tagged, untagged SD and HD, full range, RGB, HDR PQ and HLG
10-bit, SDR BT.2020 and late-starting audio. Every source carries a solid colour patch in the centre of a moving
testsrc2 picture. For each one it checks the facts, then encodes `-vf <norm_vf>` with the seekable-mezzanine flags
(ref 03 section 4) and checks the result's fps, frame count, displayed size, BT.709 tags and the decoded colour of
the patch. Relabel-only encodes are the negative controls the colour check must catch. Then: the ASR offset
(40 ms, 10 ms, 0 ms, uncorrelated, late audio), the exit-1 gates (no video, HDR/BT.2020 without zscale, offset
over one frame), usage errors, --out, --canvas and a non-ASCII path and title. Every run uses --ffprobe none;
when an ffprobe is installed the facts are also compared with the ffprobe path. One line per check; exit 0 = pass.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from fractions import Fraction
from pathlib import Path


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixtures as fx  # noqa: E402  (also puts skill/scripts on sys.path)
import cliplib as cl  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skill" / "scripts" / "probe_source.py"
FAILS = []
EXACT = "flags=accurate_rnd+full_chroma_int"
TAGS_709 = "setparams=colorspace=bt709:color_primaries=bt709:color_trc=bt709:range=tv"
# Seekable mezzanine (ref 03 section 4), the encode every norm_vf read feeds.
MEZZ = ["-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "12", "-pix_fmt", "yuv420p", "-fps_mode", "cfr",
        "-force_key_frames", "expr:gte(t,n_forced)"]
RED = (255, 0, 0)
ORANGE = (200, 60, 40)   # the BT.2020 case of ref 03 section 1: relabelled it reads (171, 87, 52)


def check(name, cond, detail=""):
    print(f"{'ok  ' if cond else 'FAIL'} {name}" + (f"  [{detail}]" if detail and not cond else ""), flush=True)
    if not cond:
        FAILS.append(name)


def run_cli(args, ffprobe="none"):
    cmd = [sys.executable, "-P", str(SCRIPT), *map(str, args), "--ffmpeg", fx.ffmpeg()]
    if ffprobe:
        cmd += ["--ffprobe", ffprobe]
    cp = subprocess.run(cmd, capture_output=True)
    try:
        js = json.loads(cp.stdout.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        js = None
    return cp.returncode, js, cp.stderr.decode("utf-8", errors="replace")


def ff(*args):
    return cl.run([fx.ffmpeg(), "-v", "error", "-nostdin", "-y", *map(str, args)])


# ---------------------------------------------------------------- source fixtures

def tags(space, prim, trc, rng="tv"):
    return f"setparams=colorspace={space}:color_primaries={prim}:color_trc={trc}:range={rng}"


def x264(prim, trc, matrix, full=False):
    return ["-x264-params", f"colorprim={prim}:transfer={trc}:colormatrix={matrix}" + (":fullrange=on" if full else "")]


def zs_from_709(t, extra=""):
    """zscale from BT.709 RGB to 10-bit BT.2020 YUV with transfer t (npl=100 maps SDR white to 100 nits)."""
    return (f"zscale=pin=bt709:tin=bt709:rin=pc:p=bt2020:t={t}:m=bt2020nc:r=tv{extra},format=yuv420p10le")


# enc -> (RGB->YUV conversion and tags, encoder args). The YUV is always written truthfully in the named matrix;
# the "u" variants carry no colour tags at all.
ENCODINGS = {
    "709": (f"scale=out_color_matrix=bt709:out_range=tv:{EXACT},format=yuv420p,{tags('bt709', 'bt709', 'bt709')}",
            x264("bt709", "bt709", "bt709")),
    "601": (f"scale=out_color_matrix=bt601:out_range=tv:{EXACT},format=yuv420p,"
            f"{tags('smpte170m', 'smpte170m', 'smpte170m')}", x264("smpte170m", "smpte170m", "smpte170m")),
    "601u": (f"scale=out_color_matrix=bt601:out_range=tv:{EXACT},format=yuv420p,"
             f"setparams=colorspace=unknown:color_primaries=unknown:color_trc=unknown:range=unknown", []),
    "709u": (f"scale=out_color_matrix=bt709:out_range=tv:{EXACT},format=yuv420p,"
             f"setparams=colorspace=unknown:color_primaries=unknown:color_trc=unknown:range=unknown", []),
    "709pc": (f"scale=out_color_matrix=bt709:out_range=pc:{EXACT},format=yuv420p,"
              f"{tags('bt709', 'bt709', 'bt709', 'pc')}", x264("bt709", "bt709", "bt709", full=True)),
    "2020": (f"{zs_from_709('bt2020-10')},{tags('bt2020nc', 'bt2020', 'bt2020-10')}",
             x264("bt2020", "bt2020-10", "bt2020nc")),
    "pq": (f"{zs_from_709('smpte2084', ':npl=100')},{tags('bt2020nc', 'bt2020', 'smpte2084')}",
           x264("bt2020", "smpte2084", "bt2020nc")),
    "hlg": (f"{zs_from_709('arib-std-b67', ':npl=100')},{tags('bt2020nc', 'bt2020', 'arib-std-b67')}",
            x264("bt2020", "arib-std-b67", "bt2020nc")),
    "rgb": ("format=rgb24", None),   # PNG in .mov: an RGB source
}


def make_src(path, w=320, h=180, rate="60", frames=120, patch=RED, enc="709", vf_extra=None, audio=None,
             pre=(), post=()):
    """A testsrc2 picture with a solid `patch` box (the middle ninth) in RGB, then converted per ENCODINGS[enc].

    audio: an extra lavfi audio source string (e.g. 'sine=...') muxed as AAC. vf_extra runs after the colour
    step (e.g. 'setsar=4/3'). pre/post: extra args before the inputs / before the output.
    """
    conv, enc_args = ENCODINGS[enc]
    d = cl.t6(Fraction(frames + 2) / Fraction(cl.parse_rate(rate)))
    hexc = "".join(f"{c:02X}" for c in patch)
    graph = (f"testsrc2=s={w}x{h}:r={rate}:d={d},format=gbrp[bg];"
             f"color=c=0x{hexc}:s={w // 3}x{h // 3}:r={rate}:d={d},format=gbrp[fg];"
             f"[bg][fg]overlay=x={w // 3}:y={h // 3}:format=gbrp:shortest=1,{conv}"
             + (f",{vf_extra}" if vf_extra else "") + "[v]")
    cmd = [*pre, "-filter_complex", graph]
    if audio:
        cmd += ["-f", "lavfi", "-i", audio]
    cmd += ["-map", "[v]", "-frames:v", frames]
    if audio:
        cmd += ["-map", "0:a", "-c:a", "aac", "-b:a", "128k", "-ar", "48000"]
    if enc == "rgb":
        cmd += ["-c:v", "png"]
    else:
        cmd += ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "6", *enc_args]
    ff(*cmd, *post, path)
    return path


def patch_rgb(path, frame):
    """Mean RGB of the centre of the patch (BT.709 tv decode; the patch is the middle ninth of the picture)."""
    img = cl.decode_frames_rgb(path, fx.ffmpeg(), [frame])[frame].astype(float)
    h, w = img.shape[:2]
    return tuple(int(round(x)) for x in img[h * 4 // 9:h * 5 // 9, w * 4 // 9:w * 5 // 9].reshape(-1, 3).mean(0))


def near(rgb, want, tol):
    return max(abs(a - b) for a, b in zip(rgb, want)) <= tol


# ---------------------------------------------------------------- per-source checks

def encode(src, vf, out):
    ff("-i", src, "-vf", vf, *MEZZ, out)
    return out


def run_source(d, name, src, expect, ffprobe_exe):
    """Probe SRC, check the facts against `expect`, encode through norm_vf and check the mezzanine."""
    code, js, err = run_cli([src, "--out", d / f"{name}.json"])
    check(f"{name}: exit 0 and ok", code == 0 and js and js["ok"] is True, err[-500:])
    if not js or not js.get("ok"):
        return None
    v = js["video"]
    for key, want in expect.get("video", {}).items():
        check(f"{name}: video.{key} == {want!r}", v.get(key) == want, f"got {v.get(key)!r}")
    for key, want in expect.get("needs", {}).items():
        check(f"{name}: needs.{key} == {want}", js["needs"][key] is want, js["needs"])
    check(f"{name}: canvas_fps {expect['canvas']}", js["canvas_fps"] == expect["canvas"], js["canvas_fps"])
    vf = js["norm_vf"]
    canvas = Fraction(js["canvas_fps"])
    rate = str(canvas.numerator) if canvas.denominator == 1 else js["canvas_fps"]
    check(f"{name}: norm_vf starts fps={rate} and ends with the BT.709 setparams",
          vf.startswith(f"fps={rate},") and vf.endswith("," + TAGS_709), vf)
    for part in expect.get("vf_has", []):
        check(f"{name}: norm_vf has {part!r}", part in vf, vf)
    for part in expect.get("vf_lacks", []):
        check(f"{name}: norm_vf lacks {part!r}", part not in vf, vf)
    for w in expect.get("warn", []):
        check(f"{name}: warning {w}", any(x.startswith(w) for x in js["warnings"]), js["warnings"])
    on_disk = json.loads(Path(d / f"{name}.json").read_text(encoding="utf-8"))
    check(f"{name}: --out equals stdout", on_disk == js)
    if ffprobe_exe:   # the ffprobe path must agree with the ffmpeg-only path (fps_avg only to 2 decimals)
        code2, js2, _ = run_cli([src], ffprobe=ffprobe_exe)
        a, b = dict(js), dict(js2 or {})
        for x in (a, b):
            x.pop("probe", None)
            x["video"] = {k: val for k, val in x.get("video", {}).items() if k != "fps_avg"}
        check(f"{name}: ffprobe facts == ffmpeg facts", code2 == 0 and a == b)
        check(f"{name}: ffprobe fps_avg within 0.01", abs(float(Fraction(js2["video"]["fps_avg"])) -
                                                          float(Fraction(v["fps_avg"]))) < 0.01)

    # The norm_vf read, encoded with the mezzanine flags.
    out = encode(src, vf, d / f"{name}.mov")
    info = cl.probe(out, fx.ffmpeg())
    ov = info["video"]
    check(f"{name}: mezzanine fps == canvas", ov["fps_r"] == canvas and ov["fps_avg"] == canvas,
          f"{ov['fps_r']} / {ov['fps_avg']}")
    frames = cl.count_frames(out, fx.ffmpeg())
    check(f"{name}: mezzanine frames == {expect['frames']}", frames == expect["frames"], f"got {frames}")
    check(f"{name}: mezzanine size == display {v['display_w']}x{v['display_h']} == {expect['size']}",
          (ov["width"], ov["height"]) == (v["display_w"], v["display_h"]) == expect["size"],
          f"{ov['width']}x{ov['height']}")
    check(f"{name}: mezzanine SAR 1:1", ov["sar"] == "1:1", ov["sar"])
    tags_out = (ov["color_range"], ov["color_space"], ov["color_primaries"], ov["color_transfer"])
    check(f"{name}: mezzanine tagged yuv420p tv/bt709", ov["pix_fmt"] == "yuv420p" and
          tags_out == ("tv", "bt709", "bt709", "bt709"), f"{ov['pix_fmt']} {tags_out}")
    if "patch" in expect:
        want, tol = expect["patch"]
        got = patch_rgb(out, min(10, frames - 1))
        if callable(want):
            check(f"{name}: patch colour {got} {want.__doc__}", want(got), got)
        else:
            check(f"{name}: patch colour {got} within {tol} of {want}", near(got, want, tol), got)
    if "relabel_misses" in expect:   # negative control: the same read without the colour step
        bad = encode(src, f"fps={rate},{TAGS_709}", d / f"{name}_relabel.mov")
        got = patch_rgb(bad, 10)
        check(f"{name}: negative control relabel-only reads {got}, not the patch",
              expect["relabel_misses"](got), got)
    return js


def case_sources(d, ffprobe_exe):
    S = {}
    S["cfr60"] = make_src(d / "cfr60.mp4", rate="60", frames=120)
    run_source(d, "cfr60", S["cfr60"], {
        "video": {"fps_r": "60/1", "fps_avg": "60/1", "vfr": False, "hdr": None, "matrix_assumed": "bt709",
                  "bit_depth": 8, "codec": "h264"},
        "needs": {"retime": False, "sar_fix": False, "matrix_convert": False, "tonemap": False, "rotate": False},
        "canvas": "60/1", "frames": 120, "size": (320, 180), "patch": (RED, 6),
        "vf_lacks": ["scale=", "zscale"]}, ffprobe_exe)
    # The exact string for the plain case: fps first, then only the tags.
    _, js, _ = run_cli([S["cfr60"]])
    check("cfr60: norm_vf == 'fps=60,<BT.709 setparams>'", js and js["norm_vf"] == f"fps=60,{TAGS_709}",
          js and js["norm_vf"])

    run_source(d, "ntsc30", make_src(d / "ntsc30.mp4", rate="30000/1001", frames=90), {
        "video": {"fps_r": "30000/1001", "vfr": False}, "needs": {"retime": True},
        "canvas": "30/1", "frames": 90, "size": (320, 180), "patch": (RED, 6)}, ffprobe_exe)
    run_source(d, "ntsc60", make_src(d / "ntsc60.mp4", rate="60000/1001", frames=180), {
        "video": {"fps_r": "60000/1001", "fps_avg": "60000/1001", "vfr": False}, "needs": {"retime": True},
        "canvas": "60/1", "frames": 180, "size": (320, 180)}, ffprobe_exe)

    # VFR: every frame for 2 s, then 2 of every 3 (ref 03 section 1 test (c)): fps_avg 48, canvas 30.
    vfr = d / "vfr.mp4"
    ff("-f", "lavfi", "-i", "testsrc2=s=320x180:r=60:d=5", "-vf",
       f"select='lt(n\\,120)+mod(n\\,3)',{TAGS_709}", "-fps_mode", "vfr", "-c:v", "libx264", "-preset", "ultrafast",
       *x264("bt709", "bt709", "bt709"), vfr)
    js = run_source(d, "vfr", vfr, {"video": {"fps_r": "60/1", "vfr": True}, "needs": {"retime": True},
                                    "canvas": "30/1", "frames": 150, "size": (320, 180), "warn": ["vfr:"]},
                    ffprobe_exe)
    if js:
        check("vfr: fps_avg about 48", abs(float(Fraction(js["video"]["fps_avg"])) - 48) < 0.5, js["video"]["fps_avg"])

    # Rotated: the display matrix of a 320x180 file -> a 180x320 picture; the centred patch stays centred.
    rot = d / "rot90.mp4"
    ff("-display_rotation:v:0", "90", "-i", S["cfr60"], "-c", "copy", rot)
    run_source(d, "rot90", rot, {
        "video": {"width": 320, "height": 180, "display_w": 180, "display_h": 320, "rotation": 270},
        "needs": {"rotate": True, "sar_fix": False}, "canvas": "60/1", "frames": 120, "size": (180, 320),
        "patch": (RED, 6), "warn": ["rotate:"]}, ffprobe_exe)

    # SAR 4:3: 320x240 coded -> trunc(320*4/3/2)*2 = 426 wide.
    run_source(d, "sar43", make_src(d / "sar43.mp4", w=320, h=240, rate="30", frames=60, vf_extra="setsar=4/3"), {
        "video": {"sar": "4:3", "width": 320, "display_w": 426, "display_h": 240}, "needs": {"sar_fix": True},
        "canvas": "30/1", "frames": 60, "size": (426, 240), "patch": (RED, 6),
        "vf_has": ["scale=trunc(iw*sar/2)*2:ih,setsar=1"]}, ffprobe_exe)

    # BT.601-tagged red: relabelled it decodes about (255, 23, 0) (ref 03 section 1).
    run_source(d, "bt601", make_src(d / "bt601.mp4", w=640, h=480, rate="30", frames=30, enc="601"), {
        "video": {"matrix_assumed": "smpte170m"}, "needs": {"matrix_convert": True},
        "canvas": "30/1", "frames": 30, "size": (640, 480), "patch": (RED, 6),
        "vf_has": ["scale=in_color_matrix=bt601:in_range=tv:out_color_matrix=bt709"],
        "relabel_misses": lambda c: c[1] >= 15}, ffprobe_exe)
    # Untagged SD: the players' guess is BT.601 below 720 coded lines.
    run_source(d, "untagged_sd", make_src(d / "untagged_sd.mp4", w=640, h=480, rate="30", frames=30, enc="601u"), {
        "video": {"matrix_assumed": "smpte170m", "color": {"range": None, "space": None, "primaries": None,
                                                           "transfer": None}},
        "canvas": "30/1", "frames": 30, "size": (640, 480), "patch": (RED, 6), "warn": ["untagged_matrix:"],
        "vf_has": ["in_color_matrix=bt601"], "relabel_misses": lambda c: c[1] >= 15}, ffprobe_exe)
    # Untagged HD (H.264, 720 lines): BT.709 is assumed, so no conversion.
    run_source(d, "untagged_hd", make_src(d / "untagged_hd.mp4", w=1280, h=720, rate="30", frames=20, enc="709u"), {
        "video": {"matrix_assumed": "bt709"}, "needs": {"matrix_convert": False},
        "canvas": "30/1", "frames": 20, "size": (1280, 720), "patch": (RED, 6), "warn": ["untagged_matrix:"],
        "vf_lacks": ["scale="]}, ffprobe_exe)
    # Untagged HD VP9: players read it as BT.601 at any size.
    vp9 = d / "untagged_vp9.webm"
    make_src(vp9, w=1280, h=720, rate="30", frames=15, enc="601u",
             post=["-c:v", "libvpx-vp9", "-deadline", "realtime", "-cpu-used", "8", "-crf", "4", "-b:v", "0"])
    run_source(d, "untagged_vp9", vp9, {
        "video": {"codec": "vp9", "matrix_assumed": "smpte170m"}, "canvas": "30/1", "frames": 15,
        "size": (1280, 720), "patch": (RED, 8), "vf_has": ["in_color_matrix=bt601"]}, ffprobe_exe)
    # Full-range BT.709: in_range=pc. No relabel negative here: ffmpeg 7.1 negotiates the range itself, so a
    # setparams=range=tv on pc frames gets a correct auto-inserted pc->tv conversion (measured: exact patch).
    run_source(d, "fullrange", make_src(d / "fullrange.mp4", rate="30", frames=30, enc="709pc", patch=ORANGE), {
        "video": {"color": {"range": "pc", "space": "bt709", "primaries": "bt709", "transfer": "bt709"}},
        "needs": {"matrix_convert": True}, "canvas": "30/1", "frames": 30, "size": (320, 180),
        "patch": (ORANGE, 4), "vf_has": ["in_color_matrix=bt709:in_range=pc"]}, ffprobe_exe)
    # RGB source (PNG in .mov).
    run_source(d, "rgb", make_src(d / "rgb_src.mov", rate="30", frames=20, enc="rgb", patch=ORANGE), {
        "video": {"codec": "png", "matrix_assumed": "gbr"}, "needs": {"matrix_convert": True}, "canvas": "30/1",
        "frames": 20, "size": (320, 180), "patch": (ORANGE, 4),
        "vf_has": ["scale=out_color_matrix=bt709:out_range=tv"]}, ffprobe_exe)
    # SDR BT.2020: zscale tail only; relabelled it reads about (171, 87, 52).
    S["bt2020"] = make_src(d / "bt2020.mp4", rate="30", frames=30, enc="2020", patch=ORANGE)
    run_source(d, "bt2020", S["bt2020"], {
        "video": {"hdr": None, "bit_depth": 10, "matrix_assumed": "bt2020nc"},
        "needs": {"matrix_convert": True, "tonemap": False}, "canvas": "30/1", "frames": 30, "size": (320, 180),
        "patch": (ORANGE, 4), "vf_has": ["zscale=p=bt709:t=bt709:m=bt709:r=tv"], "vf_lacks": ["tonemap"],
        "relabel_misses": lambda c: not near(c, ORANGE, 10)}, ffprobe_exe)

    # Partly tagged BT.2020 (VUI transfer = unspecified): zscale has no path without it, so frame 0's missing
    # transfer is filled (bt2020-10, ours); a relabel-only read still misses the patch.
    notrc = d / "bt2020_notrc.mp4"
    ff("-i", S["bt2020"], "-c", "copy", "-bsf:v", "h264_metadata=transfer_characteristics=2", notrc)
    js = run_source(d, "bt2020_notrc", notrc, {
        "video": {"hdr": None, "color": {"range": "tv", "space": "bt2020nc", "primaries": "bt2020",
                                         "transfer": None}},
        "canvas": "30/1", "frames": 30, "size": (320, 180), "patch": (ORANGE, 4),
        "vf_has": ["setparams=color_trc=bt2020-10,zscale=p=bt709"],
        "relabel_misses": lambda c: not near(c, ORANGE, 10)}, ffprobe_exe)
    if js:   # negative control: the same chain without the fill
        try:
            encode(notrc, js["norm_vf"].replace("setparams=color_trc=bt2020-10,", ""), d / "notrc_nofill.mov")
            failed = False
        except cl.ClipError as e:
            failed = "no path between colorspaces" in (e.hint or "")
        check("bt2020_notrc: negative control without the fill fails in zscale (no path)", failed)

    # HDR PQ / HLG 10-bit. Tone-mapped red stays clearly red; read as SDR it is washed out (ref 03 section 1:
    # SATAVG 23 vs 64).
    def red_ok(c):
        """is red-dominant (R - max(G, B) >= 100)"""
        return c[0] - max(c[1], c[2]) >= 100
    S["pq"] = make_src(d / "pq.mp4", rate="60", frames=60, enc="pq")
    run_source(d, "hdr_pq", S["pq"], {
        "video": {"hdr": "pq", "bit_depth": 10, "pix_fmt": "yuv420p10le", "matrix_assumed": "bt2020nc"},
        "needs": {"tonemap": True, "matrix_convert": True}, "canvas": "60/1", "frames": 60, "size": (320, 180),
        "patch": (red_ok, None), "vf_has": ["zscale=t=linear:npl=100,tonemap=hable:desat=0,"
                                            "zscale=p=bt709:t=bt709:m=bt709:r=tv,scale=out_color_matrix=bt709"],
        "vf_lacks": ["setparams=colorspace=bt2020nc"],   # frame 0 is fully tagged: nothing to fill
        "relabel_misses": lambda c: c[0] - max(c[1], c[2]) < 100}, ffprobe_exe)
    # PQ with only the transfer tagged: the matrix and primaries are filled with the BT.2020 defaults (HF).
    pq_bare = d / "pq_bare.mp4"
    ff("-i", S["pq"], "-c", "copy", "-bsf:v", "h264_metadata=colour_primaries=2:matrix_coefficients=2", pq_bare)
    run_source(d, "hdr_pq_bare", pq_bare, {
        "video": {"hdr": "pq", "matrix_assumed": "bt2020nc"}, "canvas": "60/1", "frames": 60, "size": (320, 180),
        "patch": (red_ok, None), "vf_has": ["setparams=colorspace=bt2020nc:color_primaries=bt2020,zscale=t=linear"]},
        ffprobe_exe)
    run_source(d, "hdr_hlg", make_src(d / "hlg.mp4", rate="30", frames=30, enc="hlg"), {
        "video": {"hdr": "hlg"}, "needs": {"tonemap": True}, "canvas": "30/1", "frames": 30, "size": (320, 180),
        "patch": (red_ok, None), "vf_has": ["tonemap=hable"]}, ffprobe_exe)

    # Late audio: the audio stream starts 0.25 s after the video (-itsoffset).
    S["late"] = make_src(d / "late.mp4", rate="30", frames=60, audio=gated_noise(4, 0.0),
                         pre=["-itsoffset", "0.25"])
    js = run_source(d, "late_audio", S["late"], {"canvas": "30/1", "frames": 60, "size": (320, 180),
                                                 "patch": (RED, 6), "warn": ["audio_start:"]}, ffprobe_exe)
    if js:
        late = (js["audio"] or {}).get("start_vs_video_s")
        check(f"late_audio: audio.start_vs_video_s {late} about +0.23 (0.25 s minus the AAC priming)",
              late is not None and 0.2 <= late <= 0.26, late)
    return S


# ---------------------------------------------------------------- ASR offset

def gated_noise(dur, delay_ms, seed=1, f1=1.7, f2=0.31):
    """Pink noise gated by a slow two-sine pattern (onsets every few hundred ms), optionally delayed."""
    gate = f"if(gt(sin(2*PI*{f1}*t)*sin(2*PI*{f2}*t+1)+0.2*sin(2*PI*5.3*t),0.3),1,0.03)"
    s = f"anoisesrc=d={dur}:c=pink:r=48000:a=0.5:seed={seed},volume='{gate}':eval=frame"
    return s + (f",adelay={delay_ms}:all=1" if delay_ms else "")


def case_asr(d, S):
    asr = d / "asr.m4a"
    ff("-f", "lavfi", "-i", gated_noise(24, 0), "-c:a", "aac", "-b:a", "128k", asr)
    vid = "testsrc2=s=160x90:r=30:d=24"
    cases = {}
    for name, delay in (("asr_40ms", 40), ("asr_10ms", 10), ("asr_0ms", 0)):
        p = d / f"{name}.mp4"
        ff("-f", "lavfi", "-i", vid, "-f", "lavfi", "-i", gated_noise(24, delay), "-map", "0:v", "-map", "1:a",
           "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-b:a", "128k", "-shortest", p)
        cases[name] = p

    code, js, err = run_cli([cases["asr_40ms"], "--asr-audio", asr, "--out", d / "asr40.json"])
    off = js and js.get("asr_offset_s")
    check(f"asr 40 ms: offset {off} == 0.040 +- 0.010", off is not None and abs(off - 0.04) <= 0.0101, err[-300:])
    check("asr 40 ms: over one 30 fps frame -> exit 1, error asr_offset", code == 1 and js and
          js["ok"] is False and js["error"]["code"] == "asr_offset", (code, js and js.get("error")))
    out = json.loads(Path(d / "asr40.json").read_text(encoding="utf-8"))
    check("asr 40 ms: facts still written with norm_vf and the offset", out.get("norm_vf", "").startswith("fps=30,")
          and out.get("asr_offset_s") == off)

    code, js, err = run_cli([cases["asr_10ms"], "--asr-audio", asr])
    off = js and js.get("asr_offset_s")
    check(f"asr 10 ms: offset {off} == 0.010 +- 0.010, within a frame -> exit 0",
          code == 0 and off is not None and abs(off - 0.01) <= 0.0101, (code, err[-300:]))
    code, js, err = run_cli([cases["asr_0ms"], "--asr-audio", asr])
    check("asr 0 ms: offset 0 -> exit 0", code == 0 and js and js.get("asr_offset_s") == 0, (code, js and
                                                                                             js.get("asr_offset_s")))
    code, js, _ = run_cli([cases["asr_0ms"], "--asr-audio", cases["asr_0ms"]])
    check("asr: a file against itself -> 0", code == 0 and js and js.get("asr_offset_s") == 0)

    other = d / "other.m4a"
    ff("-f", "lavfi", "-i", gated_noise(24, 0, seed=9, f1=0.83, f2=2.9), "-c:a", "aac", other)
    code, js, _ = run_cli([cases["asr_0ms"], "--asr-audio", other])
    check("asr: unrelated audio -> offset null, warning, exit 0", code == 0 and js and js["asr_offset_s"] is None
          and any(w.startswith("asr_offset_unmeasured") for w in js["warnings"]), js and js.get("warnings"))

    # The late-audio source against the same audio without the offset: words must move +0.25 s. (The first
    # decoded audio frame reads ~0.228 s: it can include the AAC priming, so the content offset is the truth.)
    plain = d / "late_plain.m4a"
    ff("-f", "lavfi", "-i", gated_noise(4, 0), "-c:a", "aac", "-b:a", "128k", plain)
    code, js, _ = run_cli([S["late"], "--asr-audio", plain])
    off = js and js.get("asr_offset_s")
    check(f"late_audio: asr offset {off} == 0.250 +- 0.010 -> exit 1",
          code == 1 and off is not None and abs(off - 0.25) <= 0.0101, code)
    return asr


# ---------------------------------------------------------------- gates, usage, paths

def case_gates(d, S, asr):
    code, js, _ = run_cli([S["pq"], "--assume-no-hdr-filters", "--out", d / "nohdr.json"])
    check("HDR without zscale/tonemap -> exit 1, hdr_no_zscale, norm_vf null",
          code == 1 and js and js["error"]["code"] == "hdr_no_zscale" and js["norm_vf"] is None
          and "libzimg" in js["error"]["hint"], js and js.get("error"))
    out = json.loads(Path(d / "nohdr.json").read_text(encoding="utf-8"))
    check("HDR without zscale: --out written with ok false", out.get("ok") is False and out.get("norm_vf") is None)
    code, js, _ = run_cli([S["bt2020"], "--assume-no-hdr-filters"])
    check("SDR BT.2020 without zscale -> exit 1, bt2020_no_zscale",
          code == 1 and js and js["error"]["code"] == "bt2020_no_zscale", js and js.get("error"))

    stale = d / "stale.json"
    stale.write_text('{"ok": true, "norm_vf": "fps=60"}', encoding="utf-8")
    code, js, _ = run_cli([asr, "--out", stale])
    check("audio-only file -> exit 1, no_video", code == 1 and js and js["error"]["code"] == "no_video", js)
    check("no_video replaces the old --out (no stale norm_vf)",
          json.loads(stale.read_text(encoding="utf-8")).get("ok") is False)

    bad = d / "bad.mp4"
    bad.write_bytes(b"this is not a video file\n" * 50)
    code, js, _ = run_cli([bad])
    check("unreadable file -> exit 2 with a JSON error", code == 2 and js and js["ok"] is False, code)
    code, js, _ = run_cli([d / "missing.mp4"])
    check("missing file -> exit 2", code == 2 and js and js["error"]["code"] == "input_missing", js)
    code, js, _ = run_cli([S["cfr60"], "--canvas", "fast"])
    check("--canvas fast -> exit 2", code == 2 and js and js["error"]["code"] == "bad_canvas", js)
    code, js, _ = run_cli([S["cfr60"], "--bogus"])
    check("unknown option -> exit 2", code == 2 and js and js["ok"] is False, code)
    code, js, _ = run_cli([S["cfr60"], "--asr-audio", d / "missing.wav"])
    check("missing --asr-audio (SRC without audio) -> exit 2", code == 2 and js["error"]["code"] == "input_missing",
          js)
    code, js, _ = run_cli([S["late"], "--asr-audio", S["cfr60"]])
    check("--asr-audio without an audio stream -> exit 2", code == 2 and js["error"]["code"] == "bad_asr_audio", js)

    # --canvas overrides: 30 on a 60 fps source halves the frames; NUM/DEN is kept as a fraction.
    code, js, _ = run_cli([S["cfr60"], "--canvas", "30"])
    ok = code == 0 and js and js["norm_vf"].startswith("fps=30,") and js["needs"]["retime"] is True
    check("--canvas 30 on 60 fps: fps=30 and retime", ok, js and js.get("norm_vf"))
    if ok:
        n = cl.count_frames(encode(S["cfr60"], js["norm_vf"], d / "canvas30.mov"), fx.ffmpeg())
        check(f"--canvas 30: 2 s -> 60 frames (got {n})", n == 60)
    code, js, _ = run_cli([S["cfr60"], "--canvas", "30000/1001"])
    check("--canvas 30000/1001 -> canvas_fps 30000/1001, fps=30000/1001",
          code == 0 and js and js["canvas_fps"] == "30000/1001" and js["norm_vf"].startswith("fps=30000/1001,"),
          js and js.get("norm_vf"))

    # Non-ASCII path with spaces and an apostrophe, a non-cp1252 title, stdout piped (subprocess) on Windows.
    odd_dir = d / "dir with space's ü"
    odd_dir.mkdir()
    odd = odd_dir / "clip ✓ ünï.mp4"
    title = "Tést ✓ 🎙 «quotes»"
    ff("-i", S["cfr60"], "-c", "copy", "-metadata", f"title={title}", odd)
    code, js, err = run_cli([odd, "--out", odd_dir / "facts ✓.json"])
    check("non-ASCII path and title: exit 0", code == 0 and js and js["ok"], err[-300:])
    check("non-ASCII title round-trips", js and js["title"] == title, js and js.get("title"))
    check("src is the absolute path", js and Path(js["src"]) == odd.resolve(), js and js.get("src"))
    check("--out under a non-ASCII folder is UTF-8 JSON",
          json.loads((odd_dir / "facts ✓.json").read_text(encoding="utf-8")).get("title") == title)


def main():
    cl.utf8_stdio()
    ffprobe_exe = cl.find_ffprobe(fx.ffmpeg())
    print(f"ffmpeg: {cl.ffmpeg_version(fx.ffmpeg())}; ffprobe: {ffprobe_exe or 'absent (ffmpeg-only path only)'}")
    d = Path(tempfile.mkdtemp(prefix="test_probe_source_"))
    try:
        S = case_sources(d, ffprobe_exe)
        asr = case_asr(d, S)
        case_gates(d, S, asr)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    print(f"\n{'ALL PASS' if not FAILS else f'{len(FAILS)} FAILED: ' + ', '.join(FAILS)}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
