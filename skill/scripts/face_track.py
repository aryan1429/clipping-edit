"""face_track.py - face-tracked reframe with a stabilised virtual camera (ref 08; ref 01 section 4; ref 04 section 2).

Usage:
  python -P face_track.py detect VIDEO --out det.json [--every N] [--max-width 960] [--min-face 0.04]
                          [--score 0.6] [--model PATH] [--max-frames N] [--force]
  python -P face_track.py track det.json --out tracks.json [--cuts cuts.json] [--cut-frames F,F,..] [--no-detect-cuts]
                          [--jump-cuts F,F,..] [--subject auto|largest|central|group|speaker] [--video VIDEO]
                          [--audio dialogue.wav] [--size 1080x1440] [--margin 0.05] [--hold 0.5]
  python -P face_track.py stabilize tracks.json --out path.json [--mode smooth|lock|steady] [--size 1080x1440]
                          [--face-h 0.24] [--eyes-y 0.28] [--margin 0.05] [--dead-zone 0.08] [--dead-zone-y 0.06]
                          [--strength 1.0] [--max-speed 0.5] [--max-upscale 2.0] [--lock-hz 4] [--lock-room 0.05]
                          [--jump-scale 0.07] [--no-reset]
  python -P face_track.py render VIDEO path.json --out preview.mp4 [--overlay] [--audio [WAV]] [--crf 18]
  python -P face_track.py qc path.json [--qc-dir DIR (default <path dir>/qc)] [--no-plot] [--video preview.mp4]
  python -P face_track.py run VIDEO --workdir DIR [detect/track/stabilize flags] [--audio [WAV]] [--render] [--overlay]
  python -P face_track.py selftest [--workdir DIR]

What it does:
  detect     YuNet (cv2.FaceDetectorYN, the official OpenCV Zoo .onnx) on a copy decoded by ffmpeg at <= 960 px
             wide, streamed frame by frame (never the whole clip in memory). The detector runs on every Nth frame
             (default: 1 at <= 30 fps, 2 above); every frame also gets pyramidal Lucas-Kanade flow of the
             features inside each face box (inner 70 %, forward-backward checked, median), which carries boxes
             across the skipped frames and is the precise motion signal of the stabiliser. Faces under
             --min-face x frame height are dropped. Output: per-frame faces in source pixels. The JSON is a
             cache: a re-run with the same video (size + mtime), model and parameters reuses it. A model that
             does not load (truncated download) is exit 2 (model_bad), before the video is read.
  track      Shots = [0, cut1), [cut1, cut2), ... from the UNION of every cut source: --cuts (cuts.py JSON
             reset_frames or a list), --cut-frames (e.g. splice frames) and cuts.py run on the video (default;
             --no-detect-cuts turns it off). No source at all is a warning (qc P1 no_cut_source). Inside a shot
             detections join tracks greedily (IoU >= 0.2 or centre distance <= 0.6 x face height); a track
             survives a miss of <= --hold s (linear fill), pieces that restart <= 1.5 s later at a plausible place
             and size are stitched; tracks under 0.2 s are dropped. Tracks never cross a shot boundary.
             Subject per shot: auto = presence x size x (0.5 + 0.5 x centrality), or a group when two faces share
             the shot (each present >= 50 % at >= 0.5 x the largest face, together >= 30 %) AND their union +
             margins fits the widest crop of --size; largest; central; group (same test; a two-shot that does not
             fit falls back to speaker cuts when audio is available, else the leading face, with a warning: never
             two half faces); speaker = active speaker from mouth motion vs the clip's audio (--audio
             dialogue.wav, else the video's; none is exit 2), 2 s windows, a switch held >= 2 s is a virtual cut.
             Hand-off: where the subject is gone for >= 0.5 s while another tracked face is on screen, that face
             takes over in a new segment (a virtual cut: the camera snaps, it never holds on an empty spot). A
             shot whose subject chain covers < 30 % of it is wide: all its faces, the full-size crop.
  stabilize  Per segment (resets at every cut, jump cut, speaker switch and hand-off; --no-reset is the negative
             control):
             1. Hampel outlier rejection on the subject's centre, eyes and size (+-0.25 s, 3 sigma; with flow, on
                the detections minus the integrated flow); a sample between its neighbours (a fast move) is kept.
             2. Fusion: per axis, the least-squares face path that matches the detections (sigma_d) and the LK
                flow steps (sigma_f), refit once without > 3 sigma residuals (monotonic samples kept). Frames with
                flow on both sides get almost no smoothing; every other frame the detections-only Whittaker
                low-pass (--lock-hz in lock, 6 Hz otherwise), so a flow gap never passes detector noise through.
                Before the face appears / after it leaves the path holds.
             3. One crop size per segment (no zoom inside a shot): face height --face-h of the canvas from the
                median face, at least the largest face + margins, inside the source, upscale <= --max-upscale.
                lock/steady keep --lock-room of travel each side unless the face needs it. A wide segment uses the
                full-size crop: static on the union of its faces when they fit, else it follows them.
                Jump cuts alternate the scale by --jump-scale and anchor the face on the canvas (ref 04 rule 5).
             4. Bounds per frame: the fused face box + a smooth envelope of how far the raw box sticks out beyond
                3 x its measured noise (<= half the margin), + --margin, inside the crop; the crop inside the
                source. At the source edge the face box itself (margin 0) stays inside.
             5. Camera path per axis. smooth (default): L1-optimal path (Grundmann et al. 2011, "Auto-directed
                video stabilization with robust L1 optimal camera paths") solved by scipy linprog/HiGHS:
                minimise w_p |excess beyond the dead zone| + w1 |v| + w2 |a| + w3 |jerk| + w_v |v over
                --max-speed|. Static segments joined by eased pans, computed offline, so pans start before a move
                (no lag). lock: the crop centre follows the fused face path exactly (face pinned on the canvas).
                steady: the smooth camera on the < 1 Hz part of the face path plus the > 1 Hz part added back
                where flow measured it (dense flow, face on screen): shake cancelled, deliberate moves framed like
                smooth; without flow it is the smooth camera. No scipy: a quadratic path (banded solve) + clamp.
  render     Preview / ffmpeg-path render: source decoded at full size, a sub-pixel warpAffine crop + scale per
             frame, piped into libx264 (BT.709 in and out). --audio muxes the video's audio, --audio WAV that file.
             --overlay draws the raw detection (red), the fused face (green) and the margin box (yellow).
  qc         Metrics and gates (ref 08 section 3): face box + margin inside the crop (fused box on rejected
             frames; raw boxes may enter the margin by the segment's noise tolerance), the face itself inside at
             the source edge, face_lost (a tracked face exists but none is shown), other faces cut / a second
             person left out (P1), crop inside the source, pans across a cut, camera oscillation per 0.5 s window
             and twitches (smooth), the face on the canvas vs the LK flow above 3 Hz (lock/steady) and, with
             --video, in the rendered clip, jump-cut anchor and scale, per-segment framing medians (ref 05
             section 1). Writes face_track_qc.json + face_track_path.png (matplotlib optional).
  run        detect -> cuts.py (merged with --cuts/--cut-frames) -> track -> stabilize -> qc
             [-> render -> qc --video].
  selftest   Simulated detections with known truth (no media, no model) plus a negative control per gate; one
             check per fixed review finding (see ref 08 section 4).

Outputs (stdout: one JSON object; --out gets the full data, written atomically):
  det.json     {"kind": "face_detections", "video", "fps", "width", "height", "frames", "det_size", "scale",
                "params", "cache_key", "faces": [[{"b": [x, y, w, h], "s", "lm": [10], "src": "det"|"flow",
                "fl": [dx, dy, n] | null}, ...] per frame]}   (source px; fl = box motion from frame k-1)
  tracks.json  {"kind": "face_tracks", ..., "size", "cuts", "cuts_from", "segments": [{"start", "end", "shot", "jump",
                "virtual_cut", "handoff", "speaker", "kind": "face"|"group"|"wide", "subject": [track ids]}],
                "subject": {"x", "y", "w", "h", "ex", "ey", "src", "fdx", "fdy"} per-frame arrays (null = no
                subject), "faces_all": [[x, y, w, h, track id], ...] per frame, "tracks": [...], "resets": [...]}
  path.json    {"kind": "crop_path", "mode", "src": [W, H], "out": [w, h], "frames": N, "resets", "segments": [...],
                "frames_data": {"cx", "cy", "cw", "ch"} per frame (source px, crop centre and size), "face": raw,
                fused and fused-box arrays, flow, every tracked face (+ used / rejected / clamped masks),
                "effectcraft": {"comp", "layer", "anchor", "position": [[x, y]...], "scale": [s%...]} (one key
                per frame for a footage layer with its anchor at the layer centre)}
Exit codes: 0 ok; 1 a gate failed (qc, selftest, render frame count); 2 usage error, unreadable input, no model or a
model that does not load.
"""
import argparse
import math
import os
import subprocess
import sys
import tempfile
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cliplib as cl  # noqa: E402

SCRIPT_VERSION = "1.1.0"
DETECT_VERSION = "1.0.0"       # det.json cache key: bump only when detect() output changes

MODEL_NAMES = ("face_detection_yunet_2023mar.onnx", "face_detection_yunet_2023mar_int8.onnx",
               "face_detection_yunet_2022mar.onnx")
MODEL_ENV = "CLIP_YUNET_MODEL"
MODEL_HINT = ("download face_detection_yunet_2023mar.onnx from the OpenCV Zoo "
              "(github.com/opencv/opencv_zoo, models/face_detection_yunet) into ./models or ~/models/yunet, "
              f"or pass --model / set {MODEL_ENV}")

# detect
MAX_W = 960                   # ref 04 section 2 Optional: detect on a <= 960 px wide copy
MIN_FACE = 0.04               # ... min face 4 % H
SCORE = 0.6
NMS = 0.3
TOP_K = 50
FLOW_INNER = 0.7              # LK features from the inner 70 % of the box (less background)
FLOW_FB = 0.7                 # forward-backward error limit, detection-scale px
FLOW_MIN_PTS = 5
# track
HOLD_S = 0.5                  # ref 04 section 2 Optional: hold the last box <= 0.5 s, then widen
ASSOC_IOU = 0.2
ASSOC_DIST = 0.6              # centre distance / face height
MIN_TRACK_S = 0.2
STITCH_S = 1.5                # ours: re-join pieces of one face split by a longer miss
MIN_COVER = 0.3               # subject present in < 30 % of a segment -> wide framing
GROUP_PRESENCE = 0.5
GROUP_SIZE = 0.5
GROUP_COPRESENT = 0.3         # ours: group members on screen together on >= 30 % of the shot
HANDOFF_S = 0.5               # ours: subject gone >= 0.5 s while another face is on screen -> hand-off (virtual cut)
SPEAKER_WIN_S = 2.0           # ref 04 section 2 Optional: >= 2 s windows, lags -125..+45 ms, r >= 0.3, +0.1
SPEAKER_HOP_S = 0.5
SPEAKER_R = 0.3
SPEAKER_LEAD = 0.1
# stabilize
SIZE = "1080x1440"            # SKILL default canvas (3:4); 1080x1920 for 9:16
FACE_H = 0.24                 # ref 01 section 4: face height 24 % H (20-30 %)
EYES_Y = 0.28                 # ref 01 section 4: eyes at 28 % H (22-35 %)
MARGIN = 0.05                 # SKILL step 4 gate: face bbox + 5 % (of the crop) inside the crop
DZ_X = 0.08                   # ref 01 section 4: dead zone 8 % W (a box 8 % of the crop wide, +-4 %)
DZ_Y = 0.06                   # ours: +-3 % H keeps the eyes inside ref 01's 22-35 % band
MAX_SPEED = 0.5               # soft speed cap, crop widths per second (see ref 08 for why not ref 01's 3 %)
MAX_UPSCALE = 2.0             # ref 01 section 4 Source scale
JUMP_SCALE = 0.07             # ref 02 rule 15 / ref 04 rule 5: 4-10 % scale change at a jump cut
LOCK_HZ = 4.0
STEADY_HZ = 1.0               # steady: motion above ~1 Hz counts as shake and is cancelled
LOCK_ROOM = 0.05              # lock: the crop is at most (1 - 2 x 0.05) of the largest crop, so it can follow
HAMPEL_S = 0.25
HAMPEL_K = 3.0
NOISE_K = 3.0                 # raw boxes may enter the margin by 3 x their measured noise (<= half the margin)
ENV_S = 0.25                  # raw-box noise envelope: rolling max +-0.5 s, averaged +-0.25 s
# smooth-mode L1 weights, per crop unit (see ref 08); w1 = W1 x fps, w2 = W2 x fps, w3 = W3 x fps^2 (x strength)
W_P = 1.0
W1 = 0.3                      # an excursion past the dead zone shorter than ~2 x W1 s is not followed
W2 = 0.05
W3 = 0.02
W_V = 4.0                     # hinge weight on speed above --max-speed, relative to w1
W_C = 0.02                    # weak pull to the exact target inside the dead zone (a static shot sits on the
#                               median target, not on a dead-zone edge)
SIGMA_D = 0.012               # detector noise, x median face height (>= 1 px)
SIGMA_F = 0.3                 # LK flow noise, detection-scale px
# qc gates (ref 08, Tested numbers; design choices)
GATE_CAM_JITTER = 0.05        # smooth: camera oscillation (worst 0.5 s window) <= 0.05 % of the canvas width
GATE_BUMP = 0.5               # smooth: a camera move >= 0.5 % W done in <= BUMP_S is a twitch (P1)
BUMP_S = 0.25
GATE_LOCK_JITTER = 0.2        # lock/steady: face high-pass std on the canvas vs the LK flow <= 0.2 % W
GATE_OUT_JITTER = 0.3         # lock/steady with --video: face high-pass std in the rendered clip <= 0.3 % W
FLOW_COVER = 0.8              # lock/steady: below 80 % flow coverage the canvas jitter is unverified (P1)
CLAMP_FRAC = 0.2              # lock/steady: crop at the source edge on > 20 % of the face frames (P1)
SHAKE_HZ = 3.0                # lock/steady gate: canvas motion above ~3 Hz (Whittaker high-pass) = shake residue
LOST_S = 0.5                  # face_lost: no face shown while one is tracked for > 0.5 s = P0 (shorter: P1)
JUMP_SHIFT = 0.00625          # ref 04 section 2 rule 5: face-centre shift per axis <= 0.625 % W at a jump cut
CUT_WIN_S = 0.25              # pan-across-cut window each side of a reset
CUT_PAN = 0.01                # ... moving > 1 % of the crop width toward the other shot's framing = a pan across


# ---------------------------------------------------------------- small helpers

def np_():
    import numpy as np
    return np


def parse_size(s):
    try:
        w, h = (int(x) for x in str(s).lower().split("x"))
        if w <= 0 or h <= 0 or w % 2 or h % 2:
            raise ValueError
        return w, h
    except ValueError:
        raise cl.ClipError("usage", f"--size must be WxH with even numbers, got {s!r}", exit_code=2)


def parse_frames(s, what):
    if s is None or str(s).strip() == "":
        return []
    try:
        out = sorted({int(x) for x in str(s).replace(" ", "").split(",") if x != ""})
    except ValueError:
        raise cl.ClipError("usage", f"{what} must be comma-separated frame numbers, got {s!r}", exit_code=2)
    return out


def load_cut_frames(path):
    """reset_frames of a cuts.py JSON, {"cuts": [...]}, {"reset_frames": [...]} or a plain list."""
    js = cl.read_json(path)
    if isinstance(js, dict):
        js = js.get("reset_frames", js.get("cuts"))
    if not isinstance(js, list) or not all(isinstance(x, int) for x in js):
        raise cl.ClipError("bad_cuts", f"{path}: expected cuts.py JSON (reset_frames) or a list of frames",
                           exit_code=2)
    return sorted(set(js))


def find_model(explicit=None):
    """(path, how) of the YuNet .onnx. Search order: --model, env CLIP_YUNET_MODEL (a set but missing path is an
    error, like a missing --model), then in each of ./models, ./models/yunet, ./ (cwd), <skill>/models,
    ~/models/yunet, ~/models, ~/.cache/opencv_zoo, ~/.cache/opencv_zoo/face_detection_yunet: the known file names
    (2023mar, 2023mar_int8, 2022mar), else the newest-named face_detection_yunet*.onnx. (None, hint) when none."""
    if explicit is not None:
        if explicit and Path(explicit).is_file():
            return str(Path(explicit).resolve()), "--model"
        raise cl.ClipError("model_missing", f"--model not found: {explicit!r}", hint=MODEL_HINT, exit_code=2)
    env = os.environ.get(MODEL_ENV)
    if env:
        if Path(env).is_file():
            return str(Path(env).resolve()), MODEL_ENV
        raise cl.ClipError("model_missing", f"{MODEL_ENV} points to a missing file: {env}", hint=MODEL_HINT,
                           exit_code=2)
    home = Path.home()
    dirs = [Path.cwd() / "models", Path.cwd() / "models" / "yunet", Path.cwd(),
            Path(__file__).resolve().parents[1] / "models", home / "models" / "yunet", home / "models",
            home / ".cache" / "opencv_zoo", home / ".cache" / "opencv_zoo" / "face_detection_yunet"]
    for d in dirs:
        for n in MODEL_NAMES:
            if (d / n).is_file():
                return str((d / n).resolve()), str(d)
        if d.is_dir():
            hits = sorted(d.glob("face_detection_yunet*.onnx"))
            if hits:
                return str(hits[-1].resolve()), str(d)
    return None, MODEL_HINT


def video_facts(video, ffmpeg):
    info = cl.probe(video, ffmpeg, cl.find_ffprobe(ffmpeg))
    v = info.get("video")
    if not v:
        raise cl.ClipError("no_video", f"{video} has no video stream", exit_code=2)
    fps = v.get("fps_r") or v.get("fps_avg")
    if not fps:
        raise cl.ClipError("no_rate", f"cannot read the frame rate of {video}", exit_code=2)
    return {"width": v["display_w"], "height": v["display_h"], "fps": Fraction(fps), "info": info,
            "sar": v.get("sar", "1:1"), "duration": info.get("duration")}


class FrameReader:
    """Stream decoded frames (h, w, ch) uint8 from ffmpeg one at a time; never holds the whole clip."""

    def __init__(self, video, ffmpeg, w, h, pix="bgr24", matrix=None, max_frames=None):
        self.w, self.h = w, h
        self.ch = 1 if pix == "gray" else 3
        conv = f":in_color_matrix={matrix}:in_range=tv" if matrix else ""   # name the YUV->RGB matrix (ref 03)
        vf = [f"scale={w}:{h}:flags=area{conv}", f"format={pix}"]
        cmd = [ffmpeg, "-v", "error", "-nostdin", "-i", str(video), "-map", "0:v:0", "-an", "-vf", ",".join(vf)]
        if max_frames:
            cmd += ["-frames:v", str(int(max_frames))]
        cmd += ["-f", "rawvideo", "-pix_fmt", pix, "-"]
        self.err = tempfile.TemporaryFile()
        try:
            self.p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=self.err, stdin=subprocess.DEVNULL,
                                      bufsize=w * h * self.ch * 2)
        except FileNotFoundError:
            raise cl.ClipError("tool_missing", f"cannot run {ffmpeg}", exit_code=2)
        self.size = w * h * self.ch

    def __iter__(self):
        np = np_()
        shape = (self.h, self.w) if self.ch == 1 else (self.h, self.w, 3)
        try:
            while True:
                buf = self.p.stdout.read(self.size)
                if not buf or len(buf) < self.size:
                    break
                yield np.frombuffer(buf, dtype=np.uint8).reshape(shape)
        finally:   # also when the consumer stops early (GeneratorExit)
            self.close()

    def close(self):
        if self.err.closed:
            return
        if self.p.poll() is None:
            try:
                self.p.stdout.close()
            except OSError:
                pass
            self.p.wait()
        self.err.seek(0)
        msg = self.err.read().decode("utf-8", errors="replace").strip()
        self.err.close()
        if self.p.returncode not in (0, None) and msg:
            cl.log(f"ffmpeg decode: {msg[-400:]}")


def iou(a, b):
    ax2, ay2, bx2, by2 = a[0] + a[2], a[1] + a[3], b[0] + b[2], b[1] + b[3]
    iw = max(0.0, min(ax2, bx2) - max(a[0], b[0]))
    ih = max(0.0, min(ay2, by2) - max(a[1], b[1]))
    inter = iw * ih
    u = a[2] * a[3] + b[2] * b[3] - inter
    return inter / u if u > 0 else 0.0


# ---------------------------------------------------------------- detect

def box_flow(prev_g, cur_g, box, cv2, np):
    """Median LK displacement (dx, dy, n) of the features inside the inner part of `box` (detection px)."""
    h_, w_ = prev_g.shape
    x, y, w, h = box
    ix, iy = x + w * (1 - FLOW_INNER) / 2, y + h * (1 - FLOW_INNER) / 2
    x0, y0 = int(max(0, ix)), int(max(0, iy))
    x1, y1 = int(min(w_, ix + w * FLOW_INNER)), int(min(h_, iy + h * FLOW_INNER))
    if x1 - x0 < 8 or y1 - y0 < 8:
        return None
    pts = cv2.goodFeaturesToTrack(prev_g[y0:y1, x0:x1], maxCorners=60, qualityLevel=0.01, minDistance=3,
                                  blockSize=5)
    if pts is None or len(pts) < FLOW_MIN_PTS:
        return None
    pts = pts.reshape(-1, 1, 2) + np.array([x0, y0], dtype=np.float32)
    lk = dict(winSize=(15, 15), maxLevel=3, criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01))
    nxt, st, _ = cv2.calcOpticalFlowPyrLK(prev_g, cur_g, pts, None, **lk)
    back, st2, _ = cv2.calcOpticalFlowPyrLK(cur_g, prev_g, nxt, None, **lk)
    fb = np.linalg.norm((back - pts).reshape(-1, 2), axis=1)
    ok = (st.reshape(-1) == 1) & (st2.reshape(-1) == 1) & (fb < FLOW_FB)
    if ok.sum() < FLOW_MIN_PTS:
        return None
    d = (nxt - pts).reshape(-1, 2)[ok]
    return float(np.median(d[:, 0])), float(np.median(d[:, 1])), int(ok.sum())


def detect(video, ffmpeg, out=None, every=0, max_width=MAX_W, min_face=MIN_FACE, score=SCORE, model=None,
           max_frames=None, force=False):
    import cv2
    np = np_()
    model_path, how = find_model(model)
    if not model_path:
        raise cl.ClipError("model_missing", "no YuNet face model found", hint=how, exit_code=2)
    if not hasattr(cv2, "FaceDetectorYN"):
        raise cl.ClipError("cv2_no_yunet", f"cv2 {cv2.__version__} has no FaceDetectorYN",
                           hint="pip install -U opencv-python (4.5.4+)", exit_code=2)
    try:   # load before touching the video: a truncated / corrupt download is a usage error with JSON, not a crash
        det = cv2.FaceDetectorYN.create(model_path, "", (320, 320), float(score), NMS, TOP_K)
    except cv2.error as e:
        why = str(e).split("error:")[-1].strip()[:240]
        raise cl.ClipError("model_bad", f"cannot load the YuNet model {model_path}: {why}",
                           hint=MODEL_HINT, exit_code=2)
    vf = video_facts(video, ffmpeg)
    W, H, fps = vf["width"], vf["height"], vf["fps"]
    if every <= 0:
        every = 1 if fps <= 31 else 2
    dw = min(int(max_width), W)
    dw -= dw % 2
    dh = int(round(H * dw / W / 2)) * 2
    scale = W / dw
    st = Path(video).stat()
    key = {"video": str(Path(video).resolve()), "bytes": st.st_size, "mtime": int(st.st_mtime), "every": every,
           "det_size": [dw, dh], "min_face": min_face, "score": score, "model": Path(model_path).name,
           "max_frames": max_frames, "version": DETECT_VERSION}
    if out and Path(out).is_file() and not force:
        try:
            old = cl.read_json(out)
            if old.get("cache_key") == key:
                cl.log(f"detect: cache hit {out}")
                old["cached"] = True
                return old
        except cl.ClipError:
            pass
    warnings = []
    if vf["sar"] not in ("1:1", None):
        warnings.append(f"non-square pixels (SAR {vf['sar']}): boxes are in stored pixels; normalise first")
    det.setInputSize((dw, dh))
    frames, prev_g, prev_boxes, n_det = [], None, [], 0
    for k, img in enumerate(FrameReader(video, ffmpeg, dw, dh, "bgr24", max_frames=max_frames)):
        g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        motions = []
        if prev_g is not None:
            for b in prev_boxes:
                motions.append(box_flow(prev_g, g, b, cv2, np))
        faces = []
        if k % every == 0:
            n_det += 1
            res = det.detect(img)[1]
            rows = [] if res is None else [r for r in res if r[3] >= min_face * dh]
            for r in rows:
                b = [float(r[0]), float(r[1]), float(r[2]), float(r[3])]
                best, fl = 0.0, None
                for pb, m in zip(prev_boxes, motions):
                    if m is None:
                        continue
                    o = iou(b, [pb[0] + m[0], pb[1] + m[1], pb[2], pb[3]])
                    if o > max(best, 0.3):
                        best, fl = o, m
                faces.append({"b": b, "s": float(r[14]), "lm": [float(v) for v in r[4:14]], "src": "det", "fl": fl})
        else:
            for pf, m in zip(frames[-1] if frames else [], motions):
                if m is None:
                    continue  # lost between detector frames: the tracker's hold covers it
                b = [pf["b"][0] + m[0], pf["b"][1] + m[1], pf["b"][2], pf["b"][3]]
                lm = [v + (m[0] if i % 2 == 0 else m[1]) for i, v in enumerate(pf["lm"])]
                faces.append({"b": b, "s": pf["s"], "lm": lm, "src": "flow", "fl": m})
        frames.append(faces)
        prev_g, prev_boxes = g, [f["b"] for f in faces]
        if k and k % 600 == 0:
            cl.log(f"detect: frame {k}")
    if not frames:
        raise cl.ClipError("decode_failed", f"no frames decoded from {video}", exit_code=2)
    # detection px -> source px
    sy = H / dh
    for faces in frames:
        for f in faces:
            f["b"] = [round(v * (scale if i % 2 == 0 else sy), 2) for i, v in enumerate(f["b"])]
            f["lm"] = [round(v * (scale if i % 2 == 0 else sy), 2) for i, v in enumerate(f["lm"])]
            f["s"] = round(f["s"], 3)
            if f["fl"] is not None:
                f["fl"] = [round(f["fl"][0] * scale, 3), round(f["fl"][1] * sy, 3), f["fl"][2]]
    with_face = sum(1 for f in frames if f)
    res = {"ok": True, "version": SCRIPT_VERSION, "kind": "face_detections", "video": str(video),
           "fps": cl.frac_str(fps), "width": W, "height": H, "frames": len(frames), "det_size": [dw, dh],
           "scale": round(scale, 6), "model": model_path, "model_found_by": how,
           "params": {"every": every, "max_width": max_width, "min_face": min_face, "score": score, "nms": NMS},
           "cache_key": key, "cached": False, "detector_frames": n_det,
           "frames_with_face": with_face, "warnings": warnings, "faces": frames}
    if out:
        cl.write_json_atomic(out, res)
    return res


def summary(res, drop=("faces", "subject", "frames_data", "face", "effectcraft", "tracks_full", "faces_all")):
    out = {k: v for k, v in res.items() if k not in drop}
    if isinstance(out.get("frames"), dict):
        out.pop("frames")
    return out


# ---------------------------------------------------------------- track

def segments_from_resets(n, resets):
    cuts = sorted({int(c) for c in resets if 0 < int(c) < n})
    bounds = [0] + cuts + [n]
    return [(a, b) for a, b in zip(bounds, bounds[1:]) if b > a]


def associate(frames, a, b, fps, hold_s=HOLD_S):
    """Tracks inside frames [a, b): [{"id", "boxes": {k: face}}]; gaps <= hold filled linearly (src interp)."""
    hold = max(1, int(round(hold_s * float(fps))))
    tracks, active = [], []
    for k in range(a, b):
        faces = frames[k]
        active = [t for t in active if k - t["last"] <= hold]
        pairs = []
        for ti, t in enumerate(active):
            lb = t["boxes"][t["last"]]["b"]
            for fi, f in enumerate(faces):
                o = iou(lb, f["b"])
                cd = math.hypot(lb[0] + lb[2] / 2 - f["b"][0] - f["b"][2] / 2,
                                lb[1] + lb[3] / 2 - f["b"][1] - f["b"][3] / 2) / max(1.0, lb[3], f["b"][3])
                if o >= ASSOC_IOU or cd <= ASSOC_DIST:
                    pairs.append((cd - o, ti, fi))
        pairs.sort()
        used_t, used_f = set(), set()
        for _, ti, fi in pairs:
            if ti in used_t or fi in used_f:
                continue
            used_t.add(ti)
            used_f.add(fi)
            t = active[ti]
            gap = k - t["last"]
            if gap > 1:  # came back within the hold: fill the miss
                p, q = t["boxes"][t["last"]], faces[fi]
                for j in range(1, gap):
                    u = j / gap
                    t["boxes"][t["last"] + j] = {
                        "b": [p["b"][i] + (q["b"][i] - p["b"][i]) * u for i in range(4)],
                        "lm": [p["lm"][i] + (q["lm"][i] - p["lm"][i]) * u for i in range(10)],
                        "s": 0.0, "src": "interp", "fl": None}
            t["boxes"][k] = faces[fi]
            t["last"] = k
        for fi, f in enumerate(faces):
            if fi not in used_f:
                t = {"id": len(tracks), "boxes": {k: f}, "last": k}
                tracks.append(t)
                active.append(t)
    tracks = stitch(tracks, fps)
    min_len = max(3, int(round(MIN_TRACK_S * float(fps))))
    return [t for t in tracks if sum(1 for f in t["boxes"].values() if f["src"] != "interp") >= min_len
            or len(t["boxes"]) >= (b - a) * 0.5]


def stitch(tracks, fps):
    """Join track pieces of one person split by a miss longer than the hold (profile turn, fast move, blur).

    B follows A when B starts after A ends, within STITCH_S, with a face height ratio of 0.6-1.67 and a centre
    distance <= (1 + 2 x gap seconds) x face height. The gap frames stay empty (the camera holds there). Pieces
    that are not stitched are handed over by subject_chain (a virtual cut), never left out of frame."""
    f = float(fps)
    pieces = sorted(tracks, key=lambda t: min(t["boxes"]))
    merged = []
    for t in pieces:
        first = min(t["boxes"])
        fb = t["boxes"][first]["b"]
        best = None
        for m in merged:
            last = max(m["boxes"])
            if last >= first or (first - last) > STITCH_S * f:
                continue
            lb = m["boxes"][last]["b"]
            ratio = fb[3] / max(1.0, lb[3])
            if not 0.6 <= ratio <= 1 / 0.6:
                continue
            dist = math.hypot(fb[0] + fb[2] / 2 - lb[0] - lb[2] / 2, fb[1] + fb[3] / 2 - lb[1] - lb[3] / 2)
            lim = (1.0 + 2.0 * (first - last) / f) * max(fb[3], lb[3])
            if dist <= lim and (best is None or dist / lim < best[0]):
                best = (dist / lim, m)
        if best is None:
            merged.append(t)
        else:
            best[1]["boxes"].update(t["boxes"])
            best[1]["last"] = max(best[1]["boxes"])
            best[1]["stitched"] = best[1].get("stitched", 0) + 1
    return merged


def track_stats(t, a, b, W):
    np = np_()
    ks = sorted(t["boxes"])
    hs = np.array([t["boxes"][k]["b"][3] for k in ks])
    cx = np.array([t["boxes"][k]["b"][0] + t["boxes"][k]["b"][2] / 2 for k in ks])
    presence = len(ks) / max(1, b - a)
    centrality = 1.0 - min(1.0, abs(float(np.median(cx)) - W / 2) / (W / 2))
    return {"presence": presence, "median_h": float(np.median(hs)), "centrality": centrality,
            "first": ks[0], "last": ks[-1], "n": len(ks)}


def auto_key(stats):
    big = max(s["median_h"] for s in stats) or 1.0
    return [s["presence"] * s["median_h"] / big * (0.5 + 0.5 * s["centrality"]) for s in stats]


def union_box(fs):
    x0 = min(f["b"][0] for f in fs)
    y0 = min(f["b"][1] for f in fs)
    x1 = max(f["b"][0] + f["b"][2] for f in fs)
    y1 = max(f["b"][1] + f["b"][3] for f in fs)
    return x0, y0, x1 - x0, y1 - y0


def max_crop(W, H, size):
    """(width, height) of the largest crop of a W x H source at the canvas aspect."""
    ow, oh = parse_size(size) if isinstance(size, str) else size
    chh = min(H, W * oh / ow)
    return chh * ow / oh, chh


def group_candidates(tr, stats, a, b):
    """Track indices that make a two-shot: present >= 50 % of the shot at >= 0.5 x the largest face, and on screen
    together with the leading one on >= 30 % of the shot ([] when fewer than two)."""
    if len(tr) < 2:
        return []
    big = max(s["median_h"] for s in stats)
    key = auto_key(stats)
    q = sorted((i for i, s in enumerate(stats)
                if s["presence"] >= GROUP_PRESENCE and s["median_h"] >= GROUP_SIZE * big), key=lambda i: -key[i])
    if len(q) < 2:
        return []
    lead = set(tr[q[0]]["boxes"])
    keep = [q[0]] + [i for i in q[1:] if len(lead & set(tr[i]["boxes"])) >= GROUP_COPRESENT * (b - a)]
    return keep if len(keep) >= 2 else []


def group_fit(tr, ids, max_cw, max_ch, margin):
    """(fits, need): need = the members' union box (90th percentile over the frames they share) + margins, as a
    multiple of the largest crop the source allows; fits when <= 1."""
    np = np_()
    common = set.intersection(*(set(tr[i]["boxes"]) for i in ids))
    if not common:
        return False, None
    us = [union_box([tr[i]["boxes"][k] for i in ids]) for k in common]
    w90 = float(np.percentile([u[2] for u in us], 90))
    h90 = float(np.percentile([u[3] for u in us], 90))
    need = max(w90 / (max_cw * (1 - 2 * margin)), h90 / (max_ch * (1 - 2 * margin)))
    return need <= 1.0, round(need, 3)


def pick_subject(tr, stats, mode, a, b, fit=None):
    """(track indices, note); note None | "auto_group" | "second_face" | "group_unfit" | "group_few".

    auto and group frame a two-shot as a group only when the members fit one crop (fit(ids) -> (bool, need));
    otherwise the leading face alone (never two half faces)."""
    if not tr:
        return [], None
    note = None
    if mode in ("group", "auto"):
        g = group_candidates(tr, stats, a, b)
        if g:
            if fit is None or fit(g)[0]:
                return g, ("auto_group" if mode == "auto" else None)
            note = "group_unfit" if mode == "group" else "second_face"
        elif mode == "group":
            note = "group_few"
    if mode == "largest":
        key = [s["presence"] * s["median_h"] for s in stats]
    elif mode == "central":
        key = [s["presence"] * (0.25 + s["centrality"]) for s in stats]
    else:
        key = auto_key(stats)
    return [max(range(len(tr)), key=lambda i: key[i])], note


def subject_chain(tr, stats, ids, a, b, fps):
    """[(start, end, [track idx])] covering [a, b): the subject, and wherever it is gone while another face is on
    screen for >= HANDOFF_S, that face (best auto score first). Each hand-off starts a new segment (a virtual cut:
    the camera snaps to the new face, it never holds on an empty spot or pans across). A group is not chained."""
    np = np_()
    if len(ids) != 1 or len(tr) < 2:
        return [(a, b, list(ids))]
    own = np.full(b - a, -1)
    for k in tr[ids[0]]["boxes"]:
        if a <= k < b:
            own[k - a] = ids[0]
    key = auto_key(stats)
    min_run = max(2, int(round(HANDOFF_S * float(fps))))
    for i in sorted(range(len(tr)), key=lambda i: -key[i]):
        if i == ids[0]:
            continue
        ks = sorted(k - a for k in tr[i]["boxes"] if a <= k < b and own[k - a] == -1)
        runs = []
        for k in ks:
            if runs and k == runs[-1][1]:
                runs[-1][1] = k + 1
            else:
                runs.append([k, k + 1])
        for r0, r1 in runs:
            if r1 - r0 >= min_run:
                own[r0:r1] = i
    first = next((int(o) for o in own if o >= 0), ids[0])
    cur, start, pieces = first, a, []
    for j, o in enumerate(own):
        if o >= 0 and o != cur:
            pieces.append((start, a + j, [cur]))
            cur, start = int(o), a + j
    pieces.append((start, b, [cur]))
    return pieces


def mouth_motion(video, ffmpeg, det, tracks_by_seg, max_frames=None):
    """{(seg, track id): float array of mouth-ROI MAD per frame (nan where the track is absent)}."""
    import cv2
    np = np_()
    dw, dh = det["det_size"]
    s = det["scale"]
    n = det["frames"]
    out = {}
    for si, (a, b, tracks) in enumerate(tracks_by_seg):
        for t in tracks:
            out[(si, t["id"])] = np.full(n, np.nan)
    owner = {}
    for si, (a, b, tracks) in enumerate(tracks_by_seg):
        for k in range(a, b):
            owner[k] = si
    prev = None
    for k, g in enumerate(FrameReader(video, ffmpeg, dw, dh, "gray", max_frames=max_frames or n)):
        if prev is not None and k in owner:
            si = owner[k]
            for t in tracks_by_seg[si][2]:
                f = t["boxes"].get(k)
                if f is None:
                    continue
                x, y, w, h = (v / s for v in f["b"])
                x0, y0 = int(max(0, x + 0.2 * w)), int(max(0, y + 0.62 * h))
                x1, y1 = int(min(dw, x + 0.8 * w)), int(min(dh, y + h))
                if x1 - x0 < 6 or y1 - y0 < 4:
                    continue
                r1 = cv2.resize(g[y0:y1, x0:x1], (48, 32), interpolation=cv2.INTER_AREA).astype(np.float32)
                r0 = cv2.resize(prev[y0:y1, x0:x1], (48, 32), interpolation=cv2.INTER_AREA).astype(np.float32)
                out[(si, t["id"])][k] = float(np.abs(r1 - r0).mean())
        prev = g
    return out


def speech_signal(audio, ffmpeg, fps, n):
    """|delta RMS| per video frame of `audio` (the clip's dialogue: a .wav or any file with an audio stream)."""
    np = np_()
    a = cl.probe(audio, ffmpeg).get("audio") or {}
    x = cl.decode_audio(audio, ffmpeg, sr=16000, channels=1, src_channels=a.get("channels") or 2)
    hop = 16000 / float(fps)
    rms = np.zeros(n)
    for k in range(n):
        lo, hi = int(k * hop), int((k + 1) * hop)
        seg = x[lo:hi]
        rms[k] = float(np.sqrt(np.mean(seg * seg))) if len(seg) else 0.0
    return np.abs(np.diff(rms, prepend=rms[0]))


def pearson(a, b):
    np = np_()
    m = ~(np.isnan(a) | np.isnan(b))
    if m.sum() < 8:
        return float("nan")
    a, b = a[m] - a[m].mean(), b[m] - b[m].mean()
    d = math.sqrt(float((a * a).sum() * (b * b).sum()))
    return float((a * b).sum() / d) if d > 0 else float("nan")


def speaker_windows(seg, tracks, mouth, speech, fps):
    """Active speaker per frame of seg (track id or None) from mouth motion vs speech (ref 04 section 2 Optional)."""
    a, b = seg
    f = float(fps)
    win, hop = int(round(SPEAKER_WIN_S * f)), max(1, int(round(SPEAKER_HOP_S * f)))
    lags = range(int(math.floor(-0.125 * f)), int(math.ceil(0.045 * f)) + 1)
    votes = {}
    rows = []
    for w0 in range(a, max(a + 1, b - win + 1), hop):
        w1 = min(b, w0 + win)
        rs = {}
        for t in tracks:
            m = mouth[t["id"]]
            best = -2.0
            for lag in lags:
                lo, hi = max(w0, w0 - lag), min(w1, w1 - lag)
                if hi - lo < 8:
                    continue
                r = pearson(m[lo:hi], speech[lo + lag:hi + lag])
                if not math.isnan(r):
                    best = max(best, r)
            rs[t["id"]] = best
        order = sorted(rs, key=lambda i: -rs[i])
        pick = None
        if order and rs[order[0]] >= SPEAKER_R and (len(order) == 1 or rs[order[0]] - rs[order[1]] >= SPEAKER_LEAD):
            pick = order[0]
        rows.append({"start": w0, "end": w1, "r": {str(k): round(v, 3) for k, v in rs.items()}, "speaker": pick})
        centre = (w0 + w1) // 2
        votes[centre] = pick
    # per frame: the nearest window centre's pick; None keeps the previous speaker (hysteresis)
    centres = sorted(votes)
    per = [None] * (b - a)
    last = None
    for k in range(a, b):
        c = min(centres, key=lambda x: abs(x - k)) if centres else None
        v = votes.get(c) if c is not None else None
        if v is not None:
            last = v
        per[k - a] = last
    # minimum hold: runs shorter than the window merge into the previous speaker
    first = next((v for v in per if v is not None), None)
    per = [first if v is None else v for v in per]
    runs, i = [], 0
    while i < len(per):
        j = i
        while j < len(per) and per[j] == per[i]:
            j += 1
        runs.append([i, j, per[i]])
        i = j
    merged = []
    for r in runs:
        if merged and (r[1] - r[0] < win or r[2] == merged[-1][2]):
            merged[-1][1] = r[1]
        else:
            merged.append(r)
    return [(a + r[0], a + r[1], r[2]) for r in merged], rows


def track(det, cut_frames=(), jump_cuts=(), subject="auto", hold_s=HOLD_S, video=None, ffmpeg=None, out=None,
          size=SIZE, margin=MARGIN, audio=None, cuts_from=None):
    """Shots -> tracks -> subject per segment. `size`/`margin` decide whether a two-shot fits one crop; `audio` is the
    clip's dialogue for --subject speaker (else the video's own audio); `cuts_from` "none" adds a warning."""
    np = np_()
    n, W, H = det["frames"], det["width"], det["height"]
    fps = cl.parse_rate(det["fps"])
    frames = det["faces"]
    if len(frames) != n:
        raise cl.ClipError("bad_detections", "faces list length differs from frames", exit_code=2)
    max_cw, max_ch = max_crop(W, H, size)
    resets = sorted({int(c) for c in list(cut_frames) + list(jump_cuts) if 0 < int(c) < n})
    jumps = set(int(j) for j in jump_cuts)
    warnings = []
    if cuts_from == "none":
        warnings.append("no cut source (no --cuts / --cut-frames, and cuts.py did not run: --no-detect-cuts or no "
                        "readable video): the camera never resets at a camera cut the track stage was not told about")
    segs = [[a, b, associate(frames, a, b, fps, hold_s)] for a, b in segments_from_resets(n, resets)]
    vid_ok = bool(video) and Path(str(video)).is_file()
    if audio and not Path(str(audio)).is_file():
        raise cl.ClipError("usage", f"--audio not found: {audio}", exit_code=2)
    lazy = {}

    def ff():
        if "ffmpeg" not in lazy:
            lazy["ffmpeg"] = ffmpeg or cl.find_ffmpeg()
        return lazy["ffmpeg"]

    def audio_src():
        if "audio" not in lazy:
            if audio:
                lazy["audio"] = str(audio)
            elif vid_ok and cl.probe(video, ff()).get("audio"):
                lazy["audio"] = str(video)
            else:
                lazy["audio"] = None
        return lazy["audio"]

    def speaker_data():
        if "mouth" not in lazy:
            lazy["mouth"] = mouth_motion(video, ff(), det, segs)
            lazy["speech"] = speech_signal(audio_src(), ff(), fps, n)
        return lazy["mouth"], lazy["speech"]

    if subject == "speaker":
        if not vid_ok:
            raise cl.ClipError("usage", "--subject speaker needs --video (mouth motion is read from the frames)",
                               exit_code=2)
        if not audio_src():
            raise cl.ClipError("speaker_no_audio", f"--subject speaker needs the clip's audio and {video} has none",
                               hint="pass --audio dialogue.wav (splice.py writes cut.mov without audio)", exit_code=2)
    out_segs, speaker_info = [], []
    for si, (a, b, tr) in enumerate(segs):
        stats = [track_stats(t, a, b, W) for t in tr]

        def fit(ids, tr=tr):
            return group_fit(tr, ids, max_cw, max_ch, margin)
        mode = subject
        if mode == "group":
            g = group_candidates(tr, stats, a, b)
            if g:
                ok, need = fit(g)
                if not ok:
                    if vid_ok and audio_src():
                        mode = "speaker"
                        warnings.append(f"shot {a}-{b}: the {len(g)} faces need {need}x the widest {size} crop: cut "
                                        "between speakers instead (never a split screen or half faces)")
                    else:
                        mode = "auto"
                        warnings.append(f"shot {a}-{b}: the {len(g)} faces need {need}x the widest {size} crop: framed "
                                        "the leading face; pass --video and --audio to cut between speakers")
            elif len(tr) >= 2:
                warnings.append(f"shot {a}-{b}: --subject group: the faces are not on screen together on >= "
                                f"{GROUP_COPRESENT:.0%} of the shot; framed one at a time")
        parts, is_spk = [(a, b, None)], False
        if mode == "speaker" and len(tr) >= 2:
            cands = [t for t, s in zip(tr, stats) if s["presence"] >= GROUP_PRESENCE]
            if len(cands) >= 2:
                mouth, speech = speaker_data()
                m = {t["id"]: mouth[(si, t["id"])] for t in cands}
                runs, rows = speaker_windows((a, b), cands, m, speech, fps)
                speaker_info.append({"shot": si, "windows": rows, "runs": [[x, y, z] for x, y, z in runs]})
                parts, is_spk = list(runs), True
        pick_mode = "auto" if mode == "speaker" else mode
        for pi, (pa, pb, spk) in enumerate(parts):
            if spk is not None:
                prim, note = [next(i for i, t in enumerate(tr) if t["id"] == spk)], None
            else:
                prim, note = pick_subject(tr, stats, pick_mode, a, b, fit)
            if note == "second_face":
                warnings.append(f"shot {a}-{b}: a second face shares the shot but both do not fit one {size} crop: "
                                "framed the leading face (qc second_face_cropped); --subject speaker --audio "
                                "dialogue.wav cuts between them")
            chain = subject_chain(tr, stats, prim, pa, pb, fps)
            covered = set()
            for ca, cb, ids in chain:
                for i in ids:
                    covered |= {k for k in tr[i]["boxes"] if ca <= k < cb}
            cover = len(covered) / max(1, pb - pa)
            if not prim or cover < MIN_COVER:
                ids = [i for i, t in enumerate(tr) if any(pa <= k < pb for k in t["boxes"])]
                out_segs.append({"start": pa, "end": pb, "shot": si, "jump": pa == a and a in jumps,
                                 "virtual_cut": pa != a, "handoff": False, "speaker": is_spk, "kind": "wide",
                                 "subject": [tr[i]["id"] for i in ids], "cover": round(cover, 3),
                                 "_tracks": [tr[i] for i in ids]})
                continue
            for ci, (ca, cb, ids) in enumerate(chain):
                ks = set()
                for i in ids:
                    ks |= {k for k in tr[i]["boxes"] if ca <= k < cb}
                out_segs.append({"start": ca, "end": cb, "shot": si, "jump": ca == a and a in jumps,
                                 "virtual_cut": ca != a, "handoff": ci > 0, "speaker": is_spk,
                                 "kind": "group" if len(ids) >= 2 else "face", "auto_group": note == "auto_group",
                                 "subject": [tr[i]["id"] for i in ids], "cover": round(len(ks) / max(1, cb - ca), 3),
                                 "_tracks": [tr[i] for i in ids]})
    # per-frame subject arrays (a group / wide segment: the union box of the members on screen)
    keys = ("x", "y", "w", "h", "ex", "ey", "fdx", "fdy")
    subj = {k: [None] * n for k in keys}
    subj["src"] = [None] * n
    for s in out_segs:
        for k in range(s["start"], s["end"]):
            fs = [t["boxes"][k] for t in s["_tracks"] if k in t["boxes"]]
            if not fs:
                continue
            x0, y0, uw, uh = union_box(fs)
            ex = float(np.mean([(f["lm"][0] + f["lm"][2]) / 2 for f in fs]))
            ey = float(np.mean([(f["lm"][1] + f["lm"][3]) / 2 for f in fs]))
            src = "det" if all(f["src"] == "det" for f in fs) else ("interp" if any(f["src"] == "interp" for f in fs)
                                                                    else "flow")
            fl = [f["fl"] for f in fs if f.get("fl")]
            vals = {"x": x0, "y": y0, "w": uw, "h": uh, "ex": ex, "ey": ey,
                    "fdx": float(np.mean([f[0] for f in fl])) if len(fl) == len(fs) else None,
                    "fdy": float(np.mean([f[1] for f in fl])) if len(fl) == len(fs) else None}
            if s["kind"] == "group" and len(fs) < len(s["_tracks"]):   # a member is missing: incomplete union
                src = "partial"
            for kk in keys:
                v = vals[kk]
                subj[kk][k] = None if v is None else round(v, 3)
            subj["src"][k] = src
    # every tracked face per frame (detector or flow boxes; qc checks that no face is lost or cut by the crop)
    faces_all = [[] for _ in range(n)]
    tracks_out = []
    for si, (a, b, tr) in enumerate(segs):
        for t in tr:
            st = track_stats(t, a, b, W)
            tracks_out.append({"id": t["id"], "shot": si, **{k: (round(v, 3) if isinstance(v, float) else v)
                                                              for k, v in st.items()}})
            for k, f in t["boxes"].items():
                if f["src"] in ("det", "flow"):
                    faces_all[k].append([round(float(v), 1) for v in f["b"]] + [t["id"]])
    seg_out = [{k: v for k, v in s.items() if not k.startswith("_")} for s in out_segs]
    all_resets = sorted({s["start"] for s in out_segs if s["start"] > 0})
    res = {"ok": True, "version": SCRIPT_VERSION, "kind": "face_tracks", "video": det.get("video"),
           "fps": det["fps"], "width": W, "height": H, "frames": n, "subject_mode": subject,
           "size": f"{parse_size(size)[0]}x{parse_size(size)[1]}" if isinstance(size, str) else f"{size[0]}x{size[1]}",
           "margin": margin, "hold_s": hold_s, "cuts": resets, "cuts_from": cuts_from, "jump_cuts": sorted(jumps),
           "resets": all_resets, "segments": seg_out, "tracks": tracks_out, "speaker": speaker_info,
           "warnings": warnings, "subject": subj, "faces_all": faces_all}
    if out:
        cl.write_json_atomic(out, res)
    return res


# ---------------------------------------------------------------- numerics

_FORCE_L2 = False             # selftest only: exercise the no-scipy camera path


def solve_banded_sym(a0, a1, a2, b):
    """Solve A p = b for a symmetric positive-definite pentadiagonal A (diagonals a0, a1, a2)."""
    np = np_()
    n = len(a0)
    try:
        from scipy.linalg import solveh_banded
        ab = np.zeros((3, n))
        ab[2] = a0
        ab[1, 1:] = a1[: n - 1]
        ab[0, 2:] = a2[: n - 2]
        return solveh_banded(ab, b)
    except ImportError:
        pass
    # banded Cholesky (L L^T), pure numpy/python: O(n)
    L0, L1, L2 = np.zeros(n), np.zeros(n), np.zeros(n)   # L[i,i], L[i,i-1], L[i,i-2]
    for i in range(n):
        if i >= 2:
            L2[i] = a2[i - 2] / L0[i - 2]
        if i >= 1:
            L1[i] = (a1[i - 1] - (L2[i] * L1[i - 1] if i >= 2 else 0.0)) / L0[i - 1]
        L0[i] = math.sqrt(max(1e-12, a0[i] - L1[i] ** 2 - L2[i] ** 2))
    y = np.zeros(n)
    for i in range(n):
        y[i] = (b[i] - (L1[i] * y[i - 1] if i >= 1 else 0) - (L2[i] * y[i - 2] if i >= 2 else 0)) / L0[i]
    x = np.zeros(n)
    for i in range(n - 1, -1, -1):
        x[i] = (y[i] - (L1[i + 1] * x[i + 1] if i + 1 < n else 0) - (L2[i + 2] * x[i + 2] if i + 2 < n else 0)) / L0[i]
    return x


def fuse(z, zw, u, uw, lam, level=0.0):
    """argmin_p sum zw (p - z)^2 + sum_k uw[k] (p_k - p_{k-1} - u_k)^2 + sum_k lam_k (p_{k-1} - 2 p_k + p_{k+1})^2.

    z/zw: measurements and weights (0 where missing); u[k]/uw[k]: step from k-1 to k (k >= 1); lam: a scalar or
    one weight per frame (the 2nd difference centred on it). With no measurement at all the path is pinned to
    `level` at frame 0 (never to 0)."""
    np = np_()
    n = len(z)
    zw = np.asarray(zw, float)
    a0 = zw.copy() + 1e-9
    a1, a2 = np.zeros(n), np.zeros(n)
    b = np.nan_to_num(np.asarray(z, float)) * zw
    for k in range(1, n):
        w = uw[k]
        if w > 0:
            a0[k] += w
            a0[k - 1] += w
            a1[k - 1] -= w
            b[k] += w * u[k]
            b[k - 1] -= w * u[k]
    lam_a = np.broadcast_to(np.asarray(lam, float), (n,))
    if n >= 3:
        for k in range(1, n - 1):
            lk = lam_a[k]
            if lk <= 0:
                continue
            a0[k - 1] += lk
            a0[k] += 4 * lk
            a0[k + 1] += lk
            a1[k - 1] -= 2 * lk
            a1[k] -= 2 * lk
            a2[k - 1] += lk
    if zw.sum() <= 0:  # nothing anchors the level: pin the first sample to `level`
        a0[0] += 1.0
        b[0] += float(level)
    return solve_banded_sym(a0, a1, a2, b)


def hampel(x, valid, half, k=HAMPEL_K, floor=0.0, keep_between=True):
    """valid mask with outliers removed: |x - rolling median| > k x 1.4826 MAD (and > floor).

    keep_between: a flagged sample that lies between its two nearest valid neighbours (+- floor, <= 4 frames apart)
    is kept: that is a fast move (monotonic), not a spike; the rolling median lags a fast move and would otherwise
    reject the real detections at its corners."""
    np = np_()
    v = valid.copy()
    n = len(x)
    for i in np.flatnonzero(valid):
        lo, hi = max(0, i - half), min(n, i + half + 1)
        w = x[lo:hi][valid[lo:hi]]
        if len(w) < 3:
            continue
        med = float(np.median(w))
        mad = 1.4826 * float(np.median(np.abs(w - med)))
        if abs(x[i] - med) > max(k * mad, floor):
            v[i] = False
    if keep_between:
        v |= valid & between(x, valid, floor)
    return v


def between(x, valid, floor):
    """True where a valid sample lies between its two nearest valid neighbours (+- floor, <= 4 frames apart): part
    of a monotonic move, not a spike. The first / last sample of a run counts when it continues the direction of
    its two neighbours on the other side by at most twice their step (a segment that starts mid-move)."""
    np = np_()
    out = np.zeros(len(x), bool)
    idx = np.flatnonzero(valid)
    L = len(idx)
    for j in range(L):
        i = idx[j]
        if 0 < j < L - 1:
            p, q = idx[j - 1], idx[j + 1]
            if q - p <= 4 and min(x[p], x[q]) - floor <= x[i] <= max(x[p], x[q]) + floor:
                out[i] = True
        elif L >= 3:
            q, q2 = (idx[1], idx[2]) if j == 0 else (idx[L - 2], idx[L - 3])
            if abs(q2 - i) <= 4:
                step, d = x[q2] - x[q], x[q] - x[i]
                if abs(d) <= floor or (step * d > 0 and abs(d) <= 2 * abs(step) + floor):
                    out[i] = True
    return out


def interp_nan(x):
    np = np_()
    x = np.asarray(x, float).copy()
    m = ~np.isnan(x)
    if m.sum() == 0:
        return x
    idx = np.arange(len(x))
    x[~m] = np.interp(idx[~m], idx[m], x[m])
    return x


def l1_path(tau, has, lo, hi, dz, w1, w2, w3, wv, vmax, wp=W_P, wc=W_C):
    """L1-optimal 1-D camera path (crop units). Returns (path, method). See the module docstring."""
    np = np_()
    n = len(tau)
    if n < 4:
        c = np.clip(np.nanmedian(np.where(has, tau, np.nan)) if has.any() else (lo + hi) / 2, lo, hi)
        return np.asarray(c, float) * np.ones(n), "static"
    try:
        if _FORCE_L2:
            raise ImportError
        from scipy.optimize import linprog
        from scipy.sparse import coo_matrix
    except ImportError:
        return l2_path(tau, has, lo, hi, w2), "l2_banded"
    # variable blocks
    oc, os_, o1 = 0, n, 2 * n
    o2 = o1 + n - 1
    o3 = o2 + n - 2
    ov = o3 + n - 3
    orr = ov + n - 1
    nv = orr + n
    cost = np.zeros(nv)
    cost[os_:os_ + n] = wp * has
    cost[orr:orr + n] = wc * has
    cost[o1:o2] = w1
    cost[o2:o3] = w2
    cost[o3:ov] = w3
    cost[ov:orr] = wv
    rows, cols, vals, rhs = [], [], [], []
    r = 0

    def add(entries, b):
        nonlocal r
        for c_, v_ in entries:
            rows.append(r)
            cols.append(c_)
            vals.append(v_)
        rhs.append(b)
        r += 1

    for t in np.flatnonzero(has):
        add([(oc + t, 1.0), (os_ + t, -1.0)], dz + tau[t])
        add([(oc + t, -1.0), (os_ + t, -1.0)], dz - tau[t])
        add([(oc + t, 1.0), (orr + t, -1.0)], tau[t])
        add([(oc + t, -1.0), (orr + t, -1.0)], -tau[t])
    stencils = [(o1, [1.0, -1.0], n - 1), (o2, [1.0, -2.0, 1.0], n - 2), (o3, [1.0, -3.0, 3.0, -1.0], n - 3)]
    for off, sten, m in stencils:
        for t in range(m):
            ent = [(oc + t + j, sten[len(sten) - 1 - j]) for j in range(len(sten))]
            add(ent + [(off + t, -1.0)], 0.0)
            add([(c_, -v_) for c_, v_ in ent] + [(off + t, -1.0)], 0.0)
    for t in range(n - 1):
        add([(oc + t + 1, 1.0), (oc + t, -1.0), (ov + t, -1.0)], vmax)
        add([(oc + t + 1, -1.0), (oc + t, 1.0), (ov + t, -1.0)], vmax)
    A = coo_matrix((vals, (rows, cols)), shape=(r, nv)).tocsr()
    bounds = np.zeros((nv, 2))
    bounds[:, 1] = np.inf
    bounds[:n, 0], bounds[:n, 1] = lo, hi
    res = linprog(cost, A_ub=A, b_ub=np.array(rhs), bounds=bounds, method="highs")
    if res.status != 0 or res.x is None:
        cl.log(f"stabilize: linprog status {res.status} ({res.message}); quadratic fallback")
        return l2_path(tau, has, lo, hi, w2), "l2_banded"
    return np.clip(res.x[:n], lo, hi), "l1_lp"


def l2_path(tau, has, lo, hi, lam):
    """Quadratic fallback: argmin sum_has (c - tau)^2 + lam' sum (D2 c)^2, then clamped (no scipy needed)."""
    np = np_()
    n = len(tau)
    zw = has.astype(float)
    lvl = float(np.nanmedian(np.where(has, tau, np.nan))) if has.any() else 0.0
    c = fuse(np.where(has, tau, 0.0), zw, np.zeros(n), np.zeros(n), max(1.0, lam * 50), lvl)
    return np.clip(c, lo, hi)


# ---------------------------------------------------------------- stabilize

def rolling_median(x, half):
    np = np_()
    n = len(x)
    if n == 0:
        return x
    pad = np.pad(x, half, mode="edge")
    try:
        from numpy.lib.stride_tricks import sliding_window_view
        return np.median(sliding_window_view(pad, 2 * half + 1), axis=1)
    except ImportError:
        return np.array([np.median(pad[i:i + 2 * half + 1]) for i in range(n)])


def rolling_max(x, half):
    np = np_()
    n = len(x)
    if n == 0:
        return x
    pad = np.pad(np.asarray(x, float), half, mode="edge")
    try:
        from numpy.lib.stride_tricks import sliding_window_view
        return sliding_window_view(pad, 2 * half + 1).max(axis=1)
    except ImportError:
        return np.array([pad[i:i + 2 * half + 1].max() for i in range(n)])


def moving_avg(x, half):
    """Centred moving average over +-half frames (edge-padded)."""
    np = np_()
    if len(x) == 0:
        return np.asarray(x, float)
    w = 2 * half + 1
    pad = np.pad(np.asarray(x, float), half, mode="edge")
    c = np.cumsum(np.concatenate([[0.0], pad]))
    return (c[w:] - c[:-w]) / w


def lowpass_reflect(x, fc, fps):
    """Whittaker low-pass (cut-off ~fc Hz) of x with odd-reflected ends (+-1 s), so the level and slope at a segment
    boundary do not bend the low-pass toward the first / last samples (a post-cut settle in steady mode)."""
    np = np_()
    x = np.asarray(x, float)
    m = len(x)
    pad = min(m - 1, max(2, int(round(fps))))
    if pad < 2:
        return x.copy()
    xp = np.concatenate([2 * x[0] - x[pad:0:-1], x, 2 * x[-1] - x[-2:-pad - 2:-1]])
    lam = (2 * math.sin(math.pi * min(fc, fps / 4) / fps)) ** -4
    L = len(xp)
    return fuse(xp, np.ones(L), np.zeros(L), np.zeros(L), lam)[pad:pad + m]


def envelope(r, half):
    """Smooth upper envelope of r >= 0: moving average (+-half) of the rolling max (+-2 half). It is >= r on every
    frame (each averaged max covers the frame) and changes slowly, so detector noise on the raw box widens the
    bound once instead of pushing the camera frame by frame."""
    return moving_avg(rolling_max(r, 2 * half), half)


def stabilize(tracks, size=SIZE, mode="smooth", face_h=FACE_H, eyes_y=EYES_Y, margin=MARGIN, dz_x=DZ_X, dz_y=DZ_Y,
              strength=1.0, max_speed=MAX_SPEED, max_upscale=MAX_UPSCALE, lock_hz=LOCK_HZ, jump_scale=JUMP_SCALE,
              reset=True, det_scale=None, lock_room=LOCK_ROOM, out=None):
    np = np_()
    ow, oh = parse_size(size) if isinstance(size, str) else size
    aspect = ow / oh
    W, H, n = tracks["width"], tracks["height"], tracks["frames"]
    fps = float(cl.parse_rate(tracks["fps"]))
    S = tracks["subject"]

    def arr(k):
        return np.array([np.nan if v is None else v for v in S[k]], float)

    fx, fy, fw, fh, ey, fdx, fdy = (arr(k) for k in ("x", "y", "w", "h", "ey", "fdx", "fdy"))
    src = S["src"]
    det_meas = np.array([s == "det" for s in src])
    present = ~np.isnan(fx)
    segs = [dict(s) for s in tracks["segments"]]
    if not reset:  # negative control: one segment over the whole clip, smoothing straight across the cuts
        kinds = [s["kind"] for s in segs]
        segs = [{"start": 0, "end": n, "shot": 0, "jump": False, "kind": "face" if "face" in kinds else kinds[0],
                 "subject": sorted({i for s in segs for i in s.get("subject", [])})}]
    dscale = det_scale or 1.0
    cx, cy, cw, ch = (np.zeros(n) for _ in range(4))
    fused_x, fused_ey = np.full(n, np.nan), np.full(n, np.nan)
    fbox = np.full((4, n), np.nan)
    used_valid = np.zeros(n, bool)
    rejected = np.zeros(n, bool)
    clamped = np.zeros(n, bool)
    clamp_x, clamp_y = np.zeros(n, bool), np.zeros(n, bool)
    seg_out, warnings = [], []
    ts = tracks.get("size")
    if ts and parse_size(ts)[0] * oh != parse_size(ts)[1] * ow:
        warnings.append(f"tracks were made for a {ts} canvas and the path is {ow}x{oh}: the two-shot fit decisions "
                        f"used the other aspect; re-run track with --size {ow}x{oh}")
    prev = None   # (segment dict, last canvas face position) for jump-cut anchoring
    jump_i = 0
    max_full = min(H, W / aspect)
    # lock/steady: travel room so the crop can follow shake (a full-height crop cannot move); a face that needs a
    # bigger crop takes it back (the room is given up before the face is cut)
    max_lock = max_full * (1 - 2 * lock_room) if mode in ("lock", "steady") else max_full
    half = max(2, int(round(HAMPEL_S * fps)))
    env_h = max(1, int(round(ENV_S * fps)))
    for s in segs:
        a, b = s["start"], s["end"]
        m = b - a
        sl = slice(a, b)
        pres = present[sl].copy()
        kind = s["kind"]
        info = {"start": a, "end": b, "kind": kind, "jump": bool(s.get("jump")),
                "virtual_cut": bool(s.get("virtual_cut")), "handoff": bool(s.get("handoff")),
                "speaker": bool(s.get("speaker")), "subject": s.get("subject", [])}
        # 0. static framing: no face at all, or a wide shot whose faces all fit one full-size crop (held still)
        static_c = None
        if pres.sum() == 0:
            static_c = (W / 2, H / 2)
        elif kind == "wide":
            x0, x1 = float(np.nanmin(fx[sl])), float(np.nanmax(fx[sl] + fw[sl]))
            y0, y1 = float(np.nanmin(fy[sl])), float(np.nanmax(fy[sl] + fh[sl]))
            if x1 - x0 <= max_full * aspect * (1 - 2 * margin) and y1 - y0 <= max_full * (1 - 2 * margin):
                static_c = ((x0 + x1) / 2, (y0 + y1) / 2)
        if static_c is not None:
            chh = max_full
            cww = chh * aspect
            cx[sl] = min(max(static_c[0], cww / 2), W - cww / 2)
            cy[sl] = min(max(static_c[1], chh / 2), H - chh / 2)
            cw[sl], ch[sl] = cww, chh
            info.update({"method": "static_wide", "mode": "static", "crop": [round(cww, 2), round(chh, 2)],
                         "upscale": round(oh / chh, 3), "limited": False})
            seg_out.append(info)
            prev = None
            continue
        seg_mode = "smooth" if kind == "wide" else mode   # a wide (action) shot is never face-pinned
        # 1. robust outlier rejection on the measurements. With flow, the Hampel test runs on the detections minus
        #    the integrated flow (camera shake and head moves cancel, only detector error and slow drift remain).
        hmed = float(np.nanmedian(fh[sl]))
        meas = det_meas[sl] & pres
        if meas.sum() < 3:   # no detector frame (group members never detected together, flow-only boxes)
            meas = pres.copy()
        ccx = fx[sl] + fw[sl] / 2
        ux, uy = fdx[sl].copy(), fdy[sl].copy()
        uok = ~np.isnan(ux) & ~np.isnan(uy) & pres
        uok[0] = False
        flow_cov = float(uok[1:][pres[1:]].mean()) if pres[1:].any() else 0.0
        hamp_flow = uok.sum() > 0.3 * m
        qx = np.cumsum(np.where(uok, np.nan_to_num(ux), 0.0)) if hamp_flow else 0.0
        qy = np.cumsum(np.where(uok, np.nan_to_num(uy), 0.0)) if hamp_flow else 0.0
        good = hampel(ccx - qx, meas, half, floor=0.04 * hmed)
        good &= hampel(ey[sl] - qy, meas, half, floor=0.04 * hmed)
        good &= hampel(fh[sl], meas, half, floor=0.06 * hmed)
        # 2. fusion of detections and flow. Steps with flow on both sides of a frame get almost no smoothing (flow is
        #    the precise motion); every other frame gets the detections-only Whittaker low-pass (cut-off --lock-hz in
        #    lock mode, 6 Hz otherwise), so a gap in the flow never passes raw detector noise to the camera.
        sd = max(1.0, SIGMA_D * hmed)
        sf = SIGMA_F * dscale
        uw = uok.astype(float) / sf ** 2
        ux, uy = np.where(uok, ux, 0.0), np.where(uok, uy, 0.0)
        fc = lock_hz if seg_mode == "lock" else 6.0
        lam = np.full(m, (2 * math.sin(math.pi * min(fc, fps / 4) / fps)) ** -4 / sd ** 2)
        if m >= 3:
            both = np.zeros(m, bool)
            both[1:-1] = uok[1:-1] & uok[2:]
            lam[both] = 1e-3 / sd ** 2
        zx, zy = np.nan_to_num(ccx), np.nan_to_num(ey[sl])
        # samples on a monotonic move (between their neighbours in x and y) are never dropped by the refit: a
        # detections-only low-pass lags a fast move, and dropping its corners would make it lag more
        mono = between(ccx, meas, 0.04 * hmed) & between(ey[sl], meas, 0.04 * hmed)
        lvx, lvy = float(np.nanmedian(ccx[pres])), float(np.nanmedian(ey[sl][pres]))
        for _ in range(2):
            zw = good.astype(float) / sd ** 2
            px = fuse(zx, zw, ux, uw, lam, lvx)
            pey = fuse(zy, zw, uy, uw, lam, lvy)
            res_ = np.hypot(zx - px, zy - pey)
            g_res = res_[good]
            if len(g_res) < 5:
                break
            lim = max(3.0 * 1.4826 * float(np.median(g_res)), 2.5 * sd)
            drop = good & (res_ > lim) & ~mono
            if not drop.any():
                break
            good &= ~drop
        n_out = int(meas.sum() - good.sum())
        # before the face first appears / after it leaves, hold the nearest fused value (never extrapolate a pan)
        pk = np.flatnonzero(pres)
        px[:pk[0]], pey[:pk[0]] = px[pk[0]], pey[pk[0]]
        px[pk[-1] + 1:], pey[pk[-1] + 1:] = px[pk[-1]], pey[pk[-1]]
        # box geometry relative to the fused points (smoothed sizes)
        wv = rolling_median(interp_nan(np.where(pres, fw[sl], np.nan)), half)
        hv = rolling_median(interp_nan(np.where(pres, fh[sl], np.nan)), half)
        top_off = rolling_median(interp_nan(np.where(pres, ey[sl] - fy[sl], np.nan)), half)   # eyes minus box top
        rej = meas & ~good                      # detections rejected as outliers
        raw_ok = pres & ~rej
        rejected[sl] = rej
        boxl, boxr = px - wv / 2, px + wv / 2
        boxt = pey - top_off
        boxb = boxt + hv
        fbox[:, sl] = np.where(pres, np.array([boxl, boxt, wv, hv]), np.nan)
        # detector noise of this segment: robust std of the raw box edges around the fused box (all four edges)
        rl, rr = boxl - fx[sl], fx[sl] + fw[sl] - boxr
        rt, rb = boxt - fy[sl], fy[sl] + fh[sl] - boxb
        sig = 0.0
        for r_ in (rl, rr, rt, rb):
            v_ = r_[raw_ok & np.isfinite(r_)]
            if len(v_) >= 5:
                sig = max(sig, 1.4826 * float(np.median(np.abs(v_ - np.median(v_)))))
        # the bound box = fused box + a smooth envelope of how far the raw box (detector, flow-carried or filled,
        # unless rejected) sticks out of it beyond the noise tolerance (NOISE_K sigma, at most half the margin; qc
        # allows the same): a real excursion is always held, but noise cannot push the camera frame by frame
        tol_px = NOISE_K * sig

        def env(r, tol_):
            return envelope(np.where(raw_ok, np.maximum(0.0, np.nan_to_num(r) - tol_), 0.0), env_h)
        # 3. crop size for the segment (big enough for the largest bound box + margins)
        bl, br = boxl - env(rl, tol_px), boxr + env(rr, tol_px)
        bt, bb = boxt - env(rt, tol_px), boxb + env(rb, tol_px)
        need = max(float(np.nanmax(np.where(pres, bb - bt, np.nan))) / (1 - 2 * margin),
                   float(np.nanmax(np.where(pres, br - bl, np.nan))) / (1 - 2 * margin) / aspect)
        if kind == "wide":
            lo_ch = hi_ch = max_full
        else:
            hi_ch = max(max_lock, min(need, max_full))
            lo_ch = max(need, min(hi_ch, oh / max_upscale))
        chh = hmed / face_h
        if s.get("jump") and prev is not None:
            # alternate punch in / back out; if the limits swallow the change, try the other direction
            jump_i += 1
            first = (1 - jump_scale) if jump_i % 2 == 1 else 1 / (1 - jump_scale)
            for f_ in (first, 1 / first):
                cand = min(max(prev["ch"] * f_, lo_ch), hi_ch)
                if abs(cand / prev["ch"] - 1) >= 0.04:
                    break
            chh = cand
            if abs(chh / prev["ch"] - 1) < 0.04:
                warnings.append(f"segment {a}-{b}: jump cut scale change {100 * abs(chh / prev['ch'] - 1):.1f} % "
                                "(< 4 %): the source size or upscale limit leaves no room")
        target_ch = chh
        chh = min(max(chh, lo_ch), hi_ch)
        limited = kind != "wide" and abs(chh - target_ch) > 0.01 * target_ch
        cww = chh * aspect
        tol_c = min(tol_px, 0.5 * margin * min(cww, chh))
        if tol_c < tol_px:   # the cap binds: rebuild the bound box with the capped tolerance
            bl, br = boxl - env(rl, tol_c), boxr + env(rr, tol_c)
            bt, bb = boxt - env(rt, tol_c), boxb + env(rb, tol_c)
        # 4. targets and bounds (crop units: x / cww, y / chh)
        tx = px.copy()
        ty = pey + (0.5 - eyes_y) * chh
        lo_x = np.maximum(cww / 2, br + margin * cww - cww / 2)
        hi_x = np.minimum(W - cww / 2, bl - margin * cww + cww / 2)
        lo_y = np.maximum(chh / 2, bb + margin * chh - chh / 2)
        hi_y = np.minimum(H - chh / 2, bt - margin * chh + chh / 2)
        unfit = ((lo_x > hi_x) | (lo_y > hi_y)) & pres
        # where face + margin cannot fit (source edge, face too big), keep the face box itself (margin 0) inside the
        # crop; a face bigger than the crop is centred. Frames without a face: only the source bounds.
        for lo_, hi_, l_, r_, size_, lim_ in ((lo_x, hi_x, bl, br, cww, W), (lo_y, hi_y, bt, bb, chh, H)):
            bad = (lo_ > hi_) & pres
            lo0 = np.maximum(size_ / 2, r_ - size_ / 2)
            hi0 = np.minimum(lim_ - size_ / 2, l_ + size_ / 2)
            ok0 = bad & (lo0 <= hi0)
            lo_[ok0], hi_[ok0] = lo0[ok0], hi0[ok0]
            big = bad & ~ok0
            c_ = np.clip((l_ + r_) / 2, size_ / 2, lim_ - size_ / 2)
            lo_[big], hi_[big] = c_[big], c_[big]
            lo_[~pres], hi_[~pres] = size_ / 2, lim_ - size_ / 2
        n_unfit = int(unfit.sum())
        has = pres.copy()
        pin_x = pin_y = None
        anchor_ok = None
        if s.get("jump") and prev is not None and has[0]:
            # ref 04 rule 5: keep the face where it was on the canvas, anchored on the face
            pin_x = px[0] + (0.5 - prev["pu"]) * cww
            pin_y = pey[0] + (0.5 - prev["pv"]) * chh
            anchor_ok = bool(lo_x[0] - 0.5 <= pin_x <= hi_x[0] + 0.5 and lo_y[0] - 0.5 <= pin_y <= hi_y[0] + 0.5)
        if seg_mode == "lock":
            path_x = np.clip(tx, lo_x, hi_x)
            path_y = np.clip(ty, lo_y, hi_y)
            clamp_x[sl], clamp_y[sl] = pres & (np.abs(path_x - tx) > 0.5), pres & (np.abs(path_y - ty) > 0.5)
            method = ("lock_fused" if flow_cov >= FLOW_COVER else "lock_partial_flow" if flow_cov > 0
                      else "lock_lowpass")
        else:
            st = max(1e-3, strength)
            w1, w2, w3 = W1 * fps * st, W2 * fps * st, W3 * fps * fps * st
            hfx = hfy = 0.0
            wgt_max = 0.0
            if seg_mode == "steady":
                # shake part = fused target minus its < 1 Hz low-pass; the L1 camera runs on the low-pass and the shake
                # part is added back where flow measured it (dense flow, face on screen; tapered), so handheld shake
                # is cancelled while deliberate moves get the smooth camera. Without flow it is the smooth camera.
                dens = moving_avg(uok.astype(float), max(1, int(round(0.1 * fps))))
                wgt = np.clip((dens - 0.5) / 0.4, 0.0, 1.0)
                wgt_max = float(wgt.max())
                hfx = (tx - lowpass_reflect(tx, STEADY_HZ, fps)) * wgt
                hfy = (ty - lowpass_reflect(ty, STEADY_HZ, fps)) * wgt
            lox, hix = (lo_x - hfx) / cww, (hi_x - hfx) / cww
            loy, hiy = (lo_y - hfy) / chh, (hi_y - hfy) / chh
            if pin_x is not None:
                e = 0.001   # +-0.1 % of the crop: well inside the qc jump_anchor limit (0.625 % W)
                for lo_, hi_, pin, size_ in ((lox, hix, pin_x, cww), (loy, hiy, pin_y, chh)):
                    want_lo, want_hi = pin / size_ - e, pin / size_ + e
                    lo_[0], hi_[0] = max(lo_[0], min(hi_[0], want_lo)), min(hi_[0], max(lo_[0], want_hi))
            vmx = max_speed / fps
            p1, method = l1_path((tx - hfx) / cww, has, lox, hix, dz_x / 2, w1, w2, w3, W_V * w1, vmx)
            p2, _ = l1_path((ty - hfy) / chh, has, loy, hiy, dz_y / 2, w1, w2, w3, W_V * w1, vmx * cww / chh)
            path_x = np.clip(p1 * cww + hfx, lo_x, hi_x)
            path_y = np.clip(p2 * chh + hfy, lo_y, hi_y)
            if seg_mode == "steady":
                method += "+steady" if wgt_max > 0 else "+steady(no flow: smooth)"
                # held at a bound (source edge or face box), the smooth part cannot make room for the shake part
                eb = 0.5 / cww, 0.5 / chh
                clamp_x[sl] = pres & (wgt > 0) & ((np.abs(path_x - (p1 * cww + hfx)) > 0.5)
                                                  | (p1 - lox < eb[0]) | (hix - p1 < eb[0]))
                clamp_y[sl] = pres & (wgt > 0) & ((np.abs(path_y - (p2 * chh + hfy)) > 0.5)
                                                  | (p2 - loy < eb[1]) | (hiy - p2 < eb[1]))
        cx[sl], cy[sl], cw[sl], ch[sl] = path_x, path_y, cww, chh
        fused_x[sl], fused_ey[sl] = np.where(pres, px, np.nan), np.where(pres, pey, np.nan)
        used_valid[sl] = good
        last = b - 1 - int(np.argmax(pres[::-1]))
        pu = (px[last - a] - (path_x[last - a] - cww / 2)) / cww
        pv = (pey[last - a] - (path_y[last - a] - chh / 2)) / chh
        prev = {"ch": chh, "pu": pu, "pv": pv}
        info.update({"method": method, "mode": seg_mode, "crop": [round(cww, 2), round(chh, 2)],
                     "upscale": round(oh / chh, 3), "limited": bool(limited), "flow": round(flow_cov, 3),
                     "outliers": n_out, "unfit_frames": n_unfit, "anchor": pin_x is not None, "anchor_ok": anchor_ok,
                     "noise_px": round(sig, 2), "noise_tol_px": round(tol_c, 2)})
        if limited:
            warnings.append(f"segment {a}-{b}: face height {100 * hmed / chh:.1f} % H (crop limited by "
                            f"{'source size' if chh >= max_full - 1e-6 else 'upscale or face size'})")
        if seg_mode in ("lock", "steady") and flow_cov < FLOW_COVER and m >= fps:
            warnings.append(f"segment {a}-{b}: {seg_mode} with flow on {100 * flow_cov:.0f} % of the face frames: "
                            + ("steady is the smooth camera where flow is missing" if seg_mode == "steady" else
                               "the --lock-hz low-pass passes detector noise there")
                            + "; qc cannot measure the canvas jitter without flow (render, then qc --video)")
        seg_out.append(info)
    clamped = clamp_x | clamp_y
    # EffectCraft keys: layer anchor at its centre, comp ow x oh; scale s = oh / ch
    sc = oh / ch
    pos_x = ow / 2 + sc * (W / 2 - cx)
    pos_y = oh / 2 + sc * (H / 2 - cy)
    r3 = lambda a_: [None if (isinstance(v, float) and math.isnan(v)) else round(float(v), 3) for v in a_]  # noqa: E731
    res = {"ok": True, "version": SCRIPT_VERSION, "kind": "crop_path", "video": tracks.get("video"),
           "fps": tracks["fps"], "frames": n, "src": [W, H], "out": [ow, oh], "mode": mode, "reset": reset,
           "subject_mode": tracks.get("subject_mode"), "cuts_from": tracks.get("cuts_from"), "det_scale": dscale,
           "params": {"face_h": face_h, "eyes_y": eyes_y, "margin": margin, "dead_zone_x": dz_x,
                      "dead_zone_y": dz_y, "strength": strength, "max_speed": max_speed,
                      "max_upscale": max_upscale, "lock_hz": lock_hz, "lock_room": lock_room,
                      "jump_scale": jump_scale},
           "lock_clamped_frames": int(clamped.sum()),
           "resets": [s["start"] for s in segs if s["start"] > 0],
           "cuts": tracks.get("cuts", []), "segments": seg_out, "warnings": warnings,
           "frames_data": {"cx": r3(cx), "cy": r3(cy), "cw": r3(cw), "ch": r3(ch)},
           "face": {"x": S["x"], "y": S["y"], "w": S["w"], "h": S["h"], "ex": S["ex"], "ey": S["ey"],
                    "fdx": S["fdx"], "fdy": S["fdy"], "src": src, "fused_cx": r3(fused_x), "fused_ey": r3(fused_ey),
                    "fused_box": [r3(fbox[i]) for i in range(4)],
                    "used": [bool(v) for v in used_valid], "rejected": [bool(v) for v in rejected],
                    "clamped": [bool(v) for v in clamped], "clamped_x": [bool(v) for v in clamp_x],
                    "clamped_y": [bool(v) for v in clamp_y], "all": tracks.get("faces_all")},
           "effectcraft": {"comp": [ow, oh], "layer": [W, H], "anchor": [W / 2, H / 2],
                           "position": [[round(float(x), 3), round(float(y), 3)] for x, y in zip(pos_x, pos_y)],
                           "scale": [round(float(v) * 100, 4) for v in sc],
                           "note": "one key per frame (frame k at k/fps); scale in %, uniform"}}
    if out:
        cl.write_json_atomic(out, res)
    return res


# ---------------------------------------------------------------- qc

def d2_rms(x, resets, n):
    """RMS of the 2nd difference of x, skipping any triple that touches a reset (and nan)."""
    np = np_()
    x = np.asarray(x, float)
    if len(x) < 3:
        return 0.0
    d2 = x[2:] - 2 * x[1:-1] + x[:-2]
    ok = ~np.isnan(d2)
    for r in resets:
        for j in (r - 2, r - 1):
            if 0 <= j < len(ok):
                ok[j] = False
    return float(np.sqrt(np.mean(d2[ok] ** 2))) if ok.any() else 0.0


def d2_sampled(x, used, resets, also=()):
    """2nd difference on triples of consecutive `used` frames with equal spacing N, / N^2 (px/frame^2).

    Detections may come every Nth frame; `also` arrays get the same triples (a camera path compared with them).
    Returns [rms of x, rms of each also]."""
    np = np_()
    idx = np.flatnonzero(used)
    rs = sorted(resets)
    tri = []
    for a, b, c in zip(idx, idx[1:], idx[2:]):
        if b - a == c - b and not any(a < r <= c for r in rs):
            tri.append((a, b, c))
    out = []
    for y in [np.asarray(x, float)] + [np.asarray(y, float) for y in also]:
        if not tri:
            out.append(0.0)
            continue
        d = np.array([(y[c] - 2 * y[b] + y[a]) / float((b - a) ** 2) for a, b, c in tri])
        d = d[~np.isnan(d)]
        out.append(float(np.sqrt(np.mean(d ** 2))) if len(d) else 0.0)
    return out


def hp_half(fps):
    """High-pass half window: +-0.2 s (6 frames at 30 fps, 12 at 60), so the same motion band at any frame rate."""
    return max(3, int(round(0.2 * float(fps))))


def hp(x, resets, half=6):
    """High-pass (x minus a centred moving average of +-half frames), per segment, for shake residue."""
    np = np_()
    x = np.asarray(x, float)
    out = np.full(len(x), np.nan)
    bounds = sorted({0, len(x), *[int(r) for r in resets if 0 < r < len(x)]})
    for a, b in zip(bounds, bounds[1:]):
        seg = x[a:b]
        if len(seg) <= 2 * half + 1 or np.isnan(seg).any():
            continue
        k = np.ones(2 * half + 1) / (2 * half + 1)
        sm = np.convolve(seg, k, mode="same")
        out[a + half:b - half] = (seg - sm)[half:len(seg) - half]
    return out


def runs_of(mask):
    """[(start, end)] of the True runs of a boolean array."""
    np = np_()
    m = np.concatenate([[0], np.asarray(mask, bool).astype(int), [0]])
    d = np.diff(m)
    return [(int(a), int(b)) for a, b in zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1))]


def osc_jitter(u, v, fps, win_s=0.5):
    """Worst 0.5 s window of camera oscillation on the canvas: sqrt(max(0, -mean(d2_k . d2_k+1))), canvas px.

    White noise of sigma px on every frame of a window reads 2 x sigma per axis; holds, eased pans and slow sways
    read ~0 (their 2nd differences keep their sign from one frame to the next), so this measures shake, not
    acceleration, and a noisy stretch fails whatever share of the clip it covers. Returns (value, first frame)."""
    np = np_()
    u, v = np.asarray(u, float), np.asarray(v, float)
    if len(u) < 4:
        return 0.0, None
    du = u[2:] - 2 * u[1:-1] + u[:-2]
    dv = v[2:] - 2 * v[1:-1] + v[:-2]
    p = np.nan_to_num(du[1:] * du[:-1] + dv[1:] * dv[:-1])
    w = max(3, int(round(win_s * float(fps))))
    if len(p) <= w:
        means = np.array([p.mean()])
    else:
        c = np.cumsum(np.concatenate([[0.0], p]))
        means = (c[w:] - c[:-w]) / w
    j = int(np.argmin(means))
    worst = -float(means[j])
    return (math.sqrt(worst) if worst > 0 else 0.0), j + 1


def camera_bumps(x, fps, thr, dur_s=BUMP_S, eps=0.1):
    """Short camera moves: runs of same-sign velocity (|v| > eps canvas px/frame) lasting <= dur_s with a
    displacement >= thr canvas px (a twitch, not an eased pan). Returns [(first frame, px, frames)]."""
    np = np_()
    v = np.diff(np.asarray(x, float))
    sgn = np.where(v > eps, 1, np.where(v < -eps, -1, 0))
    out, i, L = [], 0, len(v)
    maxd = max(1, int(round(dur_s * float(fps))))
    while i < L:
        if sgn[i] == 0:
            i += 1
            continue
        j = i
        while j < L and sgn[j] == sgn[i]:
            j += 1
        disp = float(v[i:j].sum())
        if j - i <= maxd and abs(disp) >= thr:
            out.append((i + 1, round(disp, 2), j - i))
        i = j
    return out


def measure_output(video, path, ffmpeg, width=540):
    """Face motion as the viewer sees it: LK flow of the face region in the RENDERED clip (canvas px).

    Returns {"out_face_d2_rms_px", "out_face_hp_std_px", "out_face_hp_std_by_segment", "out_frames"}: the integrated
    per-frame median feature motion inside the face box mapped onto the canvas, its shake band (> SHAKE_HZ, as
    the canvas_jitter gate) per segment (talking and expressions add a little)."""
    import cv2
    np = np_()
    ow, oh = path["out"]
    w = min(width, ow)
    w -= w % 2
    h = int(round(oh * w / ow / 2)) * 2
    k_ = w / ow
    F = path["frames_data"]
    fa = path["face"]
    resets = set(path["resets"])
    hh = hp_half(cl.parse_rate(path["fps"]))
    pos = []
    prev, cur_pos = None, np.zeros(2)
    for k, g in enumerate(FrameReader(video, ffmpeg, w, h, "gray")):
        if k >= len(F["cx"]):
            break
        if prev is None or k in resets or fa["x"][k - 1] is None:
            cur_pos = np.zeros(2)
            pos.append([np.nan, np.nan] if fa["x"][k] is None else list(cur_pos))
            prev = g
            continue
        j = k - 1
        s_ = oh / F["ch"][j]
        x0, y0 = F["cx"][j] - F["cw"][j] / 2, F["cy"][j] - F["ch"][j] / 2
        box = [(fa["x"][j] - x0) * s_ * k_, (fa["y"][j] - y0) * s_ * k_, fa["w"][j] * s_ * k_, fa["h"][j] * s_ * k_]
        m = box_flow(prev, g, box, cv2, np)
        if m is not None:
            cur_pos = cur_pos + np.array(m[:2]) / k_
        pos.append(list(cur_pos))
        prev = g
    pos = np.array(pos, float).reshape(-1, 2)
    res = sorted(resets)
    n = len(pos)
    # a face-free stretch (nan) splits the high-pass like a reset
    gaps = [i for i in range(1, n) if np.isnan(pos[i, 0]) != np.isnan(pos[i - 1, 0])]
    bounds = sorted({0, n, *res, *gaps})
    hx, hy = np.full(n, np.nan), np.full(n, np.nan)
    for a_, b_ in zip(bounds, bounds[1:]):   # the shake band (> SHAKE_HZ), as the canvas_jitter gate measures it
        if b_ - a_ >= max(8, hh) and np.isfinite(pos[a_:b_, 0]).all():
            hx[a_:b_] = pos[a_:b_, 0] - lowpass_reflect(pos[a_:b_, 0], SHAKE_HZ, cl.parse_rate(path["fps"]))
            hy[a_:b_] = pos[a_:b_, 1] - lowpass_reflect(pos[a_:b_, 1], SHAKE_HZ, cl.parse_rate(path["fps"]))
    by_seg = []
    for s in path["segments"]:
        a, b = s["start"], min(s["end"], n)
        if b - a >= 15 and np.isfinite(hx[a:b]).sum() >= 5:
            by_seg.append([a, b, round(float(np.hypot(np.nanstd(hx[a:b]), np.nanstd(hy[a:b]))), 3)])
    fin = np.isfinite(hx)
    return {"out_face_d2_rms_px": round(math.hypot(d2_rms(pos[:, 0], res, n), d2_rms(pos[:, 1], res, n)), 4),
            "out_face_hp_std_px": round(float(np.hypot(np.nanstd(hx), np.nanstd(hy))), 3) if fin.any() else None,
            "out_face_hp_std_by_segment": by_seg, "out_frames": n}


def qc(path, qc_dir=None, plot=True, truth=None, video=None, ffmpeg=None):
    np = np_()
    F = path["frames_data"]
    cx, cy, cw, ch = (np.array(F[k], float) for k in ("cx", "cy", "cw", "ch"))
    n = len(cx)
    W, H = path["src"]
    ow, oh = path["out"]
    fps = float(cl.parse_rate(path["fps"]))
    resets = path["resets"]
    mode = path["mode"]
    margin = path["params"]["margin"]
    fa = path["face"]
    segs = path["segments"]
    tol = 0.5

    def arr(k):
        v = fa.get(k)
        return np.full(n, np.nan) if v is None else np.array([np.nan if x is None else x for x in v], float)

    fx, fy, fw, fh, ey = (arr(k) for k in ("x", "y", "w", "h", "ey"))
    fcx, fey = arr("fused_cx"), arr("fused_ey")
    fdx, fdy = arr("fdx"), arr("fdy")
    fb = fa.get("fused_box")
    fbx, fby, fbw, fbh = ((np.array([np.nan if x is None else x for x in c], float) for c in fb) if fb
                          else (np.full(n, np.nan) for _ in range(4)))
    used = np.array(fa["used"], bool)
    pres = ~np.isnan(fx)
    raw_cx = fx + fw / 2
    rej = np.array(fa.get("rejected", [False] * n), bool)
    clamp = np.array(fa.get("clamped", [False] * n), bool)
    clx = np.array(fa.get("clamped_x", fa.get("clamped", [False] * n)), bool)
    cly = np.array(fa.get("clamped_y", fa.get("clamped", [False] * n)), bool)
    sc = oh / ch
    findings = []

    def find(fid, rank, measured, fix, frame=None):
        findings.append({"id": fid, "rank": rank, "frame": frame, "measured": measured, "fix": fix})

    seg_of = np.zeros(n, int)
    for i, s in enumerate(segs):
        seg_of[s["start"]:s["end"]] = i
    seg_mode = [s.get("mode", mode) for s in segs]
    smooth_seg = [m_ not in ("lock", "steady") for m_ in seg_mode]
    # --- camera motion: plain 2nd-difference RMS (reported) and raw detections vs the camera on the same
    #     detector-frame triples (detections may be every Nth frame)
    cam_j = math.hypot(d2_rms(cx, resets, n), d2_rms(cy, resets, n))
    rx, cxs = d2_sampled(raw_cx, used, resets, (cx,))
    ry, cys = d2_sampled(ey, used, resets, (cy,))
    raw_j, cam_js = math.hypot(rx, ry), math.hypot(cxs, cys)
    # --- smooth segments: oscillation (worst 0.5 s window) and twitches, on the canvas
    cu, cv_ = cx * sc, cy * sc
    jit_worst, jit_at, bumps = 0.0, None, []
    for i, s in enumerate(segs):
        a, b = s["start"], s["end"]
        if not smooth_seg[i] or b - a < 4:
            continue
        j, at = osc_jitter(cu[a:b], cv_[a:b], fps)
        if j > jit_worst:
            jit_worst, jit_at = j, a + (at or 0)
        for axis, xs in (("x", cu[a:b]), ("y", cv_[a:b])):
            for f0, d, L in camera_bumps(xs, fps, GATE_BUMP / 100 * ow):
                bumps.append({"frame": a + f0, "axis": axis, "px": d, "frames": L})
    # --- lock / steady segments: the face on the canvas measured against the LK flow (independent of the
    #     detector path the camera was built from): canvas step = scale x (flow step - camera step)
    hh = hp_half(fps)
    canvas_rows = []
    for i, s in enumerate(segs):
        if smooth_seg[i]:
            continue
        a, b = s["start"], s["end"]
        ok = np.zeros(b - a, bool)
        fu_, fv_ = np.zeros(b - a), np.zeros(b - a)      # face step (flow) on the canvas
        ru, rv = np.zeros(b - a), np.zeros(b - a)        # face step minus camera step on the canvas
        for k in range(a + 1, b):
            if pres[k] and pres[k - 1] and not (np.isnan(fdx[k]) or np.isnan(fdy[k])):
                ok[k - a] = True
                fu_[k - a], fv_[k - a] = sc[k] * fdx[k], sc[k] * fdy[k]
                ru[k - a] = sc[k] * (fdx[k] - (cx[k] - cx[k - 1]))
                rv[k - a] = sc[k] * (fdy[k] - (cy[k] - cy[k - 1]))
        npres = int(pres[a + 1:b].sum())
        cover = float(ok.sum()) / max(1, npres)

        def band_std(du, dv, okx, oky):
            """Integrate per run of measured frames, keep the shake band (> SHAKE_HZ), std (canvas px)."""
            hs = []
            for d_, okm in ((du, okx), (dv, oky)):
                h_ = np.full(b - a, np.nan)
                for r0, r1 in runs_of(okm):
                    if r1 - r0 >= max(8, hh):
                        pos_ = np.cumsum(d_[r0:r1])
                        h_[r0:r1] = pos_ - lowpass_reflect(pos_, SHAKE_HZ, fps)
                hs.append(h_)
            if max(np.isfinite(h_).sum() for h_ in hs) < 5:
                return None
            return float(np.hypot(*[np.nanstd(h_) if np.isfinite(h_).sum() >= 5 else 0.0 for h_ in hs]))
        # clamped frames (crop at the source edge) cannot follow: excluded per axis, reported as lock_clamped
        okx, oky = ok & ~clx[a:b], ok & ~cly[a:b]
        std, fstd = band_std(ru, rv, okx, oky), band_std(fu_, fv_, ok, ok)
        cf = float(clamp[a:b][pres[a:b]].mean()) if pres[a:b].any() else 0.0
        # deliberate moves that steady frames like smooth stay below ~2 Hz on the canvas; shake residue is above
        lim = GATE_LOCK_JITTER / 100 * ow
        canvas_rows.append({"start": a, "end": b, "mode": seg_mode[i], "flow_cover": round(cover, 3),
                            "hp_std_px": None if std is None else round(std, 3),
                            "face_hp_std_px": None if fstd is None else round(fstd, 3), "limit_px": round(lim, 3),
                            "clamped": round(cf, 3)})
    # --- face box + margin inside the crop. The subject box (a group / wide shot: the union of its faces); on frames
    #     whose detection was rejected as an outlier, the fused box (the face was there; the outlier box was not).
    x0, x1 = cx - cw / 2, cx + cw / 2
    y0, y1 = cy - ch / 2, cy + ch / 2
    use_f = rej & np.isfinite(fbx)
    gx, gy = np.where(use_f, fbx, fx), np.where(use_f, fby, fy)
    gw, gh = np.where(use_f, fbw, fw), np.where(use_f, fbh, fh)
    chk = pres & np.isfinite(gx)
    # a raw (detector) box may enter the margin by the segment's measured noise tolerance (stabilize: NOISE_K x the
    # robust std of the raw box around the fused box, <= half the margin); the fused box of a rejected one may not
    ntol = np.full(n, tol)
    for s in segs:
        ntol[s["start"]:s["end"]] = max(tol, float(s.get("noise_tol_px") or 0.0))
    ntol = np.where(use_f, tol, ntol)
    inside = ((gx >= x0 + margin * cw - ntol) & (gx + gw <= x1 - margin * cw + ntol) &
              (gy >= y0 + margin * ch - ntol) & (gy + gh <= y1 - margin * ch + ntol))
    # the part of a box outside the source (a face leaving the frame) cannot be in any crop: clip it to the source
    cbx0, cby0 = np.clip(gx, 0, W), np.clip(gy, 0, H)
    cbx1, cby1 = np.clip(gx + gw, 0, W), np.clip(gy + gh, 0, H)
    in_bbox = (cbx0 >= x0 - ntol) & (cbx1 <= x1 + ntol) & (cby0 >= y0 - ntol) & (cby1 <= y1 + ntol)
    bigger = (gw > cw + tol) | (gh > ch + tol)
    # face + margin cannot fit (source border, or the face is taller / wider than the crop minus margins): the
    # margin is reported, not gated; the face itself must still be fully inside unless it is bigger than the crop
    # (within the noise tolerance, as stabilize decides it on the fused box)
    edge = chk & ((gx - margin * cw < 0.5 + ntol) | (gx + gw + margin * cw > W - 0.5 - ntol)
                  | (gy - margin * ch < 0.5 + ntol) | (gy + gh + margin * ch > H - 0.5 - ntol)
                  | (gh > ch * (1 - 2 * margin) - 2 * ntol) | (gw > cw * (1 - 2 * margin) - 2 * ntol))
    gate_m = chk & ~edge
    gate_b = chk & edge & ~bigger
    inside_pct = 100.0 * float(inside[gate_m].mean()) if gate_m.any() else 100.0
    bbox_pct = 100.0 * float(in_bbox[chk & ~bigger].mean()) if (chk & ~bigger).any() else 100.0
    src_ok = (x0 >= -0.01) & (x1 <= W + 0.01) & (y0 >= -0.01) & (y1 <= H + 0.01)
    src_pct = 100.0 * float(src_ok.mean())
    # --- every tracked face: a frame that shows no face while one is tracked (face_lost), other faces cut by the
    #     crop edge, and a second person left out of a shot they share
    allf = fa.get("all")
    subj_sets = [set(s.get("subject", [])) for s in segs]
    lost = np.zeros(n, bool)
    other_cut = np.zeros(n, bool)
    second = {}
    if allf:
        for k in range(min(n, len(allf))):
            fs = allf[k]
            if not fs:
                continue
            si = int(seg_of[k])
            any_in = any_fit = False
            for bx, by, bw, bh, tid in fs:
                full = bx >= x0[k] - tol and bx + bw <= x1[k] + tol and by >= y0[k] - tol and by + bh <= y1[k] + tol
                over = min(bx + bw, x1[k]) > max(bx, x0[k]) and min(by + bh, y1[k]) > max(by, y0[k])
                any_in |= full
                any_fit |= bw <= cw[k] + tol and bh <= ch[k] + tol
                if tid not in subj_sets[si]:
                    if over and not full:
                        other_cut[k] = True
                    st = second.setdefault((si, tid), [0, 0, []])
                    st[0] += 1
                    st[1] += 0 if full else 1
                    st[2].append(bh)
            if not any_in and any_fit:
                lost[k] = True
    lost_runs = runs_of(lost)
    lost_long = [r for r in lost_runs if r[1] - r[0] > LOST_S * fps]
    second_rows = []
    for (si, tid), (cnt, outn, hs) in second.items():
        s = segs[si]
        L = s["end"] - s["start"]
        sub_h = float(np.nanmedian(fh[s["start"]:s["end"]])) if pres[s["start"]:s["end"]].any() else 0.0
        if (cnt >= GROUP_PRESENCE * L and float(np.median(hs)) >= GROUP_SIZE * sub_h and outn > 0.5 * cnt
                and not s.get("speaker") and s["kind"] != "wide"):
            second_rows.append([s["start"], s["end"], tid, round(outn / cnt, 3)])
    # --- pans across a cut. lock / steady cameras follow the face's shake on purpose: their smooth component
    #     (camera minus the face, or minus the face's > STEADY_HZ part) is what must not drift across a cut
    kx, ky = cx.copy(), cy.copy()          # camera smooth component
    gfx, gfy = fcx.copy(), fey.copy()      # face motion that justifies camera motion
    for i, s in enumerate(segs):
        if smooth_seg[i]:
            continue
        a, b = s["start"], s["end"]
        fol_x, fol_y = np.zeros(b - a), np.zeros(b - a)     # the face motion the camera follows on purpose
        for r0, r1 in runs_of(np.isfinite(fcx[a:b])):
            sx_, sy_ = fcx[a + r0:a + r1], fey[a + r0:a + r1]
            if seg_mode[i] == "lock":
                fol_x[r0:r1], fol_y[r0:r1] = sx_ - sx_[0], sy_ - sy_[0]
                gfx[a + r0:a + r1], gfy[a + r0:a + r1] = sx_[0], sy_[0]
            else:
                lx, ly = lowpass_reflect(sx_, STEADY_HZ, fps), lowpass_reflect(sy_, STEADY_HZ, fps)
                fol_x[r0:r1], fol_y[r0:r1] = sx_ - lx, sy_ - ly
                gfx[a + r0:a + r1], gfy[a + r0:a + r1] = lx, ly
            if r0 > 0:   # a run starts: no step from the face-free frames before it
                fol_x[r0:r1] -= fol_x[r0]
                fol_y[r0:r1] -= fol_y[r0]
        for kk, cc, fol, clm in ((kx, cx, fol_x, clx), (ky, cy, fol_y, cly)):
            dk = np.diff(cc[a:b], prepend=cc[a]) - np.diff(fol, prepend=fol[0])
            stuck = clm[a:b] | np.concatenate([[False], clm[a:b - 1]])
            dk[stuck] = 0.0      # a crop held at the source edge is not smoothing toward anything
            kk[a:b] = cc[a] + np.cumsum(dk)
    win = max(1, int(round(CUT_WIN_S * fps)))
    pans = []
    for r in path.get("cuts", []) or resets:
        if not 1 <= r < n:
            continue
        jump = np.array([cx[r] - cx[r - 1], cy[r] - cy[r - 1]])
        jn = float(np.hypot(*jump))
        dirn = jump / jn if jn > 1e-6 else None
        a_, b_ = max(0, r - 1 - win), min(n - 1, r + win)
        pre = np.array([kx[r - 1] - kx[a_], ky[r - 1] - ky[a_]])
        post = np.array([kx[b_] - kx[r], ky[b_] - ky[r]])

        def face_move(i, j):
            ok = np.flatnonzero(~np.isnan(gfx[i:j + 1]))
            if len(ok) < 2:
                return np.zeros(2)
            i2, j2 = i + ok[0], i + ok[-1]
            return np.array([gfx[j2] - gfx[i2], gfy[j2] - gfy[i2]])
        thr = CUT_PAN * float(cw[r])
        bad = False
        if dirn is not None:
            # camera motion toward the other shot's framing that the face itself does not make: a pre-cut drift
            # toward B (an offline smoother across the cut) or a post-cut settle (a causal smoother without a reset)
            pre_s = float(pre @ dirn) - max(0.0, float(face_move(a_, r - 1) @ dirn))
            post_s = float(post @ dirn) - max(0.0, float(face_move(r, b_) @ dirn))
            bad = pre_s > thr or post_s > thr
        # a smoother without a reset moves across the cut in small steps instead of snapping
        if not bad and r not in resets:
            bad = True
        if bad:
            pans.append(r)
    # --- jump cuts (ref 04 section 2 rule 5): scale change 4-10 %, face kept in place on the canvas
    jump_rows = []
    for i, s in enumerate(segs):
        if not s.get("jump") or i == 0:
            continue
        r = s["start"]
        ratio = float(ch[r] / ch[r - 1])
        prv = np.flatnonzero(np.isfinite(fcx[segs[i - 1]["start"]:r]))
        nxt = np.flatnonzero(np.isfinite(fcx[r:min(s["end"], r + max(2, int(round(0.1 * fps))))]))
        shift = None
        if len(prv) and len(nxt):
            j0, j1 = segs[i - 1]["start"] + int(prv[-1]), r + int(nxt[0])
            u0, v0 = (fcx[j0] - x0[j0]) * sc[j0], (fey[j0] - y0[j0]) * sc[j0]
            u1, v1 = (fcx[j1] - x0[j1]) * sc[j1], (fey[j1] - y0[j1]) * sc[j1]
            shift = float(max(abs(u1 - u0), abs(v1 - v0)))
        jump_rows.append({"frame": r, "scale_ratio": round(ratio, 4),
                          "face_shift_px": None if shift is None else round(shift, 2),
                          "anchor_ok": s.get("anchor_ok")})
        if not (0.90 <= ratio <= 0.96 or 1.04 <= ratio <= 1.11):
            find("jump_scale", "P1", f"jump cut at f{r}: crop scale ratio {ratio:.3f} (4-10 % change)",
                 "--jump-scale, or the source / upscale limit leaves no room", r)
        if shift is not None and shift > JUMP_SHIFT * ow:
            find("jump_anchor", "P0" if s.get("anchor_ok") is not False else "P1",
                 f"jump cut at f{r}: the face moves {shift:.1f} px on the canvas (<= {JUMP_SHIFT * ow:.2f})"
                 + ("" if s.get("anchor_ok") is not False else "; the source edge made the anchor impossible"),
                 "the new segment must start with the face where it was (stabilize anchors it)", r)
    # --- per-segment framing medians (canvas)
    seg_rows = []
    for i, s in enumerate(segs):
        a, b = s["start"], s["end"]
        m = pres[a:b]
        row = {"start": a, "end": b, "kind": s["kind"], "mode": seg_mode[i], "limited": s.get("limited", False)}
        if m.sum() >= 3 and s["kind"] != "wide":
            fh_pct = 100 * np.median((fh[a:b] / ch[a:b])[m])
            ey_pct = 100 * np.median(((ey[a:b] - (cy[a:b] - ch[a:b] / 2)) / ch[a:b])[m])
            cx_pct = 100 * np.median(((raw_cx[a:b] - (cx[a:b] - cw[a:b] / 2)) / cw[a:b])[m])
            row.update({"face_h_pct": round(float(fh_pct), 2), "eyes_y_pct": round(float(ey_pct), 2),
                        "centre_x_pct": round(float(cx_pct), 2)})
            rank = "P1" if s.get("limited") or s["kind"] == "group" else "P0"
            # frames whose ideal crop (eyes at --eyes-y, face centred) would leave the source: P1, not P0
            need_y = ey[a:b] + (0.5 - path["params"]["eyes_y"]) * ch[a:b]
            need_x = raw_cx[a:b]
            edge_y = float(((need_y < ch[a:b] / 2 - 1) | (need_y > H - ch[a:b] / 2 + 1))[m].mean())
            edge_x = float(((need_x < cw[a:b] / 2 - 1) | (need_x > W - cw[a:b] / 2 + 1))[m].mean())
            row.update({"crop_at_source_edge_x": round(edge_x, 3), "crop_at_source_edge_y": round(edge_y, 3)})
            if (b - a) / fps >= 1.0:
                if not 20 <= fh_pct <= 30 and s["kind"] != "group":
                    find("face_height", rank, f"segment {a}-{b}: face {fh_pct:.1f} % H (20-30)",
                         "crop size: --face-h, or the source is too small (limited)", a)
                if not 22 <= ey_pct <= 35:
                    find("eyes_y", "P1" if edge_y > 0.5 else rank, f"segment {a}-{b}: eyes at {ey_pct:.1f} % H "
                         f"(22-35); crop at the source edge on {100 * edge_y:.0f} % of frames",
                         "check --eyes-y and the dead zone; at the source edge only a wider crop helps", a)
                if not 40 <= cx_pct <= 60 and s["kind"] != "group":
                    find("centre_x", "P1" if edge_x > 0.5 else rank, f"segment {a}-{b}: face centre at "
                         f"{cx_pct:.1f} % W (40-60); crop at the source edge on {100 * edge_x:.0f} % of frames",
                         "the source edge limits the crop or the dead zone is too wide", a)
        seg_rows.append(row)
    out_metrics = {}
    if video:
        out_metrics = measure_output(video, path, ffmpeg or cl.find_ffmpeg())
    out_by = {a_: std for a_, b_, std in out_metrics.get("out_face_hp_std_by_segment", [])}
    # --- findings
    if inside_pct < 100.0:
        bad_k = np.flatnonzero(gate_m & ~inside)
        find("face_outside_margin", "P0", f"{inside_pct:.2f} % of frames hold the face box + {margin:.0%} margin "
             f"({len(bad_k)} frames, first {int(bad_k[0])}; {int((gate_m & ~inside & use_f).sum())} on the fused box "
             "of a rejected detection)", "widen the crop or check the subject track", int(bad_k[0]))
    # a rejected detection is gated on the fused box; if the rejected box itself was the real face, say so (P1)
    raw_in = ((fx >= x0 + margin * cw - tol) & (fx + fw <= x1 - margin * cw + tol) &
              (fy >= y0 + margin * ch - tol) & (fy + fh <= y1 - margin * ch + tol))
    rej_out = use_f & chk & ~edge & ~raw_in
    if rej_out.any():
        k0 = int(np.flatnonzero(rej_out)[0])
        find("rejected_box_outside", "P1", f"{int(rej_out.sum())} frames: a detection rejected as an outlier lies "
             f"outside the face + margin box (first f{k0}); if it was the real face, the crop missed it there",
             "review the preview at those frames (a fast move without flow?)", k0)
    if (gate_b & ~in_bbox).any():
        bad_k = np.flatnonzero(gate_b & ~in_bbox)
        find("face_outside_crop", "P0", f"{len(bad_k)} frames at the source edge cut the face itself (first "
             f"{int(bad_k[0])})", "the face box (margin 0) must stay inside the crop at the source edge", int(bad_k[0]))
    if src_pct < 100.0:
        find("crop_outside_source", "P0", f"{100 - src_pct:.2f} % of frames show outside the source",
             "clamp the crop (bug)")
    if lost_long:
        nl = sum(r[1] - r[0] for r in lost_long)
        find("face_lost", "P0", f"{nl} frames in {len(lost_long)} run(s) > {LOST_S} s show no face while a face is "
             f"tracked (first f{lost_long[0][0]}-{lost_long[0][1]})",
             "a missed cut or a subject swap: pass the cut (--cuts / --cut-frames) or check the tracks",
             lost_long[0][0])
    short_lost = [r for r in lost_runs if r not in lost_long]
    if short_lost:
        find("face_lost_brief", "P1", f"{sum(r[1] - r[0] for r in short_lost)} frames in {len(short_lost)} run(s) "
             f"<= {LOST_S} s show no face while one is tracked", "review the preview there", short_lost[0][0])
    if other_cut.any():
        k0 = int(np.flatnonzero(other_cut)[0])
        find("other_face_cut", "P1", f"{int(other_cut.sum())} frames: a face other than the subject is cut by the "
             "crop edge", "review the preview; --subject group / speaker if it is a second speaker", k0)
    if second_rows:
        find("second_face_cropped", "P1", f"{len(second_rows)} segment(s) leave a second person (present >= "
             f"{GROUP_PRESENCE:.0%}, >= {GROUP_SIZE}x the subject's size) out of the crop: {second_rows[:5]}",
             "two people who do not fit one crop: --subject speaker --audio dialogue.wav cuts between them",
             second_rows[0][0])
    if pans:
        find("pan_across_cut", "P0", f"{len(pans)} cut(s) with a pan across: {pans[:10]}",
             "reset the camera at every cut (track --cuts / cuts.py reset_frames)", pans[0])
    if jit_worst > GATE_CAM_JITTER / 100 * ow:
        find("camera_jitter", "P0", f"camera oscillation {jit_worst:.3f} px on the canvas in the worst 0.5 s window "
             f"(<= {GATE_CAM_JITTER / 100 * ow:.2f} = {GATE_CAM_JITTER} % W)",
             "raise --strength or check the detections for noise", jit_at)
    if bumps:
        find("camera_bump", "P1", f"{len(bumps)} camera move(s) of >= {GATE_BUMP} % W in <= {BUMP_S} s: "
             f"{bumps[:5]}", "a noise-driven twitch: check the detections / --margin near the face", bumps[0]["frame"])
    for row in canvas_rows:
        a, b = row["start"], row["end"]
        lim = row["limit_px"]
        if row["hp_std_px"] is not None and row["hp_std_px"] > lim:
            find("canvas_jitter", "P0", f"segment {a}-{b} ({row['mode']}): face high-pass std on the canvas "
                 f"{row['hp_std_px']:.2f} px above {SHAKE_HZ:g} Hz vs the LK flow (<= {lim:.2f} = "
                 f"{GATE_LOCK_JITTER} % W;"
                 f" the face itself moves {row['face_hp_std_px']} px in that band)",
                 "lock/steady need flow (detect computes it); without it use smooth or a lower --lock-hz", a)
        if a in out_by and out_by[a] > GATE_OUT_JITTER / 100 * ow:
            find("output_face_jitter", "P0", f"segment {a}-{b} ({row['mode']}): face high-pass std in the rendered "
                 f"clip {out_by[a]:.2f} px (<= {GATE_OUT_JITTER / 100 * ow:.2f} = {GATE_OUT_JITTER} % W)",
                 "the face is not held still: check flow coverage, clamped frames, or use smooth", a)
        if row["flow_cover"] < FLOW_COVER and (b - a) >= fps and a not in out_by:
            find("canvas_jitter_unverified", "P1", f"segment {a}-{b} ({row['mode']}): flow on "
                 f"{100 * row['flow_cover']:.0f} % of the face frames (< {FLOW_COVER:.0%}): the canvas jitter cannot "
                 "be measured there", "render and run qc --video (run --render does it)", a)
        if row["clamped"] > CLAMP_FRAC:
            find("lock_clamped", "P1", f"segment {a}-{b} ({row['mode']}): the crop hits the source edge on "
                 f"{100 * row['clamped']:.0f} % of the face frames, so the face is not pinned there",
                 "a smaller crop (--face-h) or more --lock-room gives it room; or use smooth", a)
    if path.get("cuts_from") == "none":
        find("no_cut_source", "P1", "the track stage had no cut source (no --cuts / --cut-frames, no video for "
             "cuts.py): a missed camera cut is panned across", "pass the cut list or the video (cuts.py runs on it)")
    if edge.any():
        find("face_at_source_edge", "info", f"{int(edge.sum())} frames: the face + margin cannot fit inside the "
             "source or the crop (edge or face too big); the margin is not gated there, the face box is", None)
    metrics = {"frames": n, "mode": mode, "resets": len(resets),
               "camera_d2_rms_px": round(cam_j, 4), "raw_d2_rms_px": round(raw_j, 4),
               "camera_d2_rms_at_det_px": round(cam_js, 4),
               "d2_rms_reduction_x": round(raw_j / cam_js, 1) if cam_js > 1e-9 else None,
               "camera_jitter_px": round(jit_worst, 4), "camera_jitter_pct_w": round(100 * jit_worst / ow, 5),
               "camera_bumps": len(bumps),
               "canvas_face_jitter_px": max([r["hp_std_px"] or 0.0 for r in canvas_rows], default=None),
               "canvas_segments": canvas_rows,
               "face_inside_margin_pct": round(inside_pct, 3), "face_inside_crop_pct": round(bbox_pct, 3),
               "crop_inside_source_pct": round(src_pct, 3), "pan_across_cut": len(pans),
               "face_lost_frames": int(lost.sum()), "other_face_cut_frames": int(other_cut.sum()),
               "second_face_cropped": second_rows, "jump_cuts": jump_rows,
               "edge_frames": int(edge.sum()), "rejected_detections": int(rej.sum()),
               "rejected_gated": int((use_f & chk).sum()), "lock_clamped_frames": path.get("lock_clamped_frames", 0)}
    v = np.hypot(np.diff(cx), np.diff(cy))
    v_ok = np.ones(len(v), bool)
    for r in resets:
        if 0 <= r - 1 < len(v_ok):
            v_ok[r - 1] = False
    metrics["max_speed_cw_per_s"] = round(float((v[v_ok] / cw[1:][v_ok]).max() * fps), 4) if v_ok.any() else 0.0
    metrics["static_frames_pct"] = round(100 * float(((v[v_ok] / cw[1:][v_ok]) < 0.0005).mean()), 2) if v_ok.any() \
        else 100.0
    metrics.update(out_metrics)
    if truth is not None:
        metrics.update(truth_metrics(path, truth))
    findings.sort(key=lambda x: ({"P0": 0, "P1": 1}.get(x["rank"], 2), x["frame"] if x["frame"] is not None else -1))
    res = {"ok": not any(x["rank"] == "P0" for x in findings), "version": SCRIPT_VERSION, "kind": "face_track_qc",
           "metrics": metrics, "segments": seg_rows, "findings": findings, "files": {}}
    if qc_dir:
        qd = Path(qc_dir)
        qd.mkdir(parents=True, exist_ok=True)
        if plot:
            png = plot_path(path, qd / "face_track_path.png")
            if png:
                res["files"]["plot"] = png
            else:
                res.setdefault("warnings", []).append("matplotlib missing: no plot")
        res["files"]["qc"] = str(qd / "face_track_qc.json")
        cl.write_json_atomic(qd / "face_track_qc.json", res)
    return res


def truth_metrics(path, truth):
    """Selftest only: the face on the canvas from the TRUE face path (no detector noise)."""
    np = np_()
    F = path["frames_data"]
    cx, cy, cw, ch = (np.array(F[k], float) for k in ("cx", "cy", "cw", "ch"))
    oh = path["out"][1]
    sc = oh / ch
    tx, ty = np.array(truth["cx"], float), np.array(truth["ey"], float)
    u = (tx - (cx - cw / 2)) * sc
    v = (ty - (cy - ch / 2)) * sc
    resets = path["resets"]
    n = len(cx)
    hh = hp_half(cl.parse_rate(path["fps"]))
    return {"truth_canvas_jitter_px": round(math.hypot(d2_rms(u, resets, n), d2_rms(v, resets, n)), 4),
            "truth_canvas_std_px": round(float(np.hypot(np.nanstd(hp(u, resets, hh)),
                                                        np.nanstd(hp(v, resets, hh)))), 3)}


def plot_path(path, png):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None
    np = np_()
    F = path["frames_data"]
    fa = path["face"]
    n = len(F["cx"])
    t = np.arange(n) / float(cl.parse_rate(path["fps"]))

    def arr(k):
        return np.array([np.nan if v is None else v for v in fa[k]], float)

    fx, fw, ey = arr("x"), arr("w"), arr("ey")
    used = np.array(fa["used"], bool)
    cx, cy, cw, ch = (np.array(F[k], float) for k in ("cx", "cy", "cw", "ch"))
    eyes_y = path["params"]["eyes_y"]
    fig, axs = plt.subplots(2, 1, figsize=(12, 6.5), sharex=True)
    rows = [("x (source px)", fx + fw / 2, arr("fused_cx"), cx, cw, path["params"]["dead_zone_x"] / 2),
            ("eyes y (source px)", ey, arr("fused_ey"), cy - (0.5 - eyes_y) * ch, ch,
             path["params"]["dead_zone_y"] / 2)]
    for ax, (lab, raw, fused, cam, size, dz) in zip(axs, rows):
        ax.plot(t[used], raw[used], ".", ms=2.5, color="#d62728", alpha=0.6, label="raw detections")
        ax.plot(t[~used & ~np.isnan(raw)], raw[~used & ~np.isnan(raw)], "x", ms=4, color="#7f7f7f",
                label="rejected / interpolated")
        ax.plot(t, fused, "-", lw=0.8, color="#2ca02c", label="fused face")
        ax.plot(t, cam, "-", lw=2.0, color="#1f77b4", label="camera target point")
        ax.fill_between(t, cam - dz * size, cam + dz * size, color="#1f77b4", alpha=0.12, label="dead zone")
        for r in path["resets"]:
            ax.axvline(r / float(cl.parse_rate(path["fps"])), color="k", lw=0.8, ls="--")
        ax.set_ylabel(lab)
        ax.invert_yaxis() if "y" in lab.split()[0] else None
    axs[0].legend(loc="upper right", fontsize=7, ncol=3)
    axs[1].set_xlabel("time (s); dashed = reset (cut)")
    fig.suptitle(f"face_track {path['mode']}: camera path vs detections")
    fig.tight_layout()
    fig.savefig(str(png), dpi=110)
    plt.close(fig)
    return str(png)


# ---------------------------------------------------------------- render

def render(video, path, out, ffmpeg, overlay=False, audio=False, crf=18):
    """audio: False = none, True = the video's own audio, a path = that file (e.g. dialogue.wav)."""
    import cv2
    np = np_()
    vf = video_facts(video, ffmpeg)
    W, H = vf["width"], vf["height"]
    if [W, H] != list(path["src"]):
        raise cl.ClipError("size_mismatch", f"video is {W}x{H}, the path was made for {path['src']}", exit_code=2)
    ow, oh = path["out"]
    F = path["frames_data"]
    cx, cy, cw, ch = (np.array(F[k], float) for k in ("cx", "cy", "cw", "ch"))
    n = len(cx)
    fa = path["face"]
    fps = path["fps"]
    tmp = cl.tmp_path(out)
    cmd = [ffmpeg, "-v", "error", "-nostdin", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{ow}x{oh}",
           "-r", fps, "-i", "-"]
    a_src = audio if isinstance(audio, str) else (str(video) if audio and vf["info"].get("audio") else None)
    if a_src:
        cmd += ["-i", a_src, "-map", "0:v:0", "-map", "1:a:0", "-c:a", "aac", "-b:a", "192k"]
    else:
        cmd += ["-map", "0:v:0"]
    cmd += ["-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p,"
                   "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf),
            "-x264-params", "colorprim=bt709:transfer=bt709:colormatrix=bt709", "-movflags", "+faststart", tmp]
    err = tempfile.TemporaryFile()
    enc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=err, stdout=subprocess.DEVNULL)
    k = 0
    try:
        space = (vf["info"]["video"].get("color_space") or "").lower()
        matrix = "bt601" if space in ("smpte170m", "bt470bg") else "bt709"
        for img in FrameReader(video, ffmpeg, W, H, "bgr24", matrix=matrix):
            j = min(k, n - 1)
            s = ow / cw[j]
            x0, y0 = cx[j] - cw[j] / 2, cy[j] - ch[j] / 2
            if s < 1.0:  # downscale: area-filter the frame first, then a sub-pixel shift
                small = cv2.resize(img, (max(1, int(round(W * s))), max(1, int(round(H * s)))),
                                   interpolation=cv2.INTER_AREA)
                sx, sy = small.shape[1] / W, small.shape[0] / H
                M = np.array([[1.0, 0, -x0 * sx], [0, 1.0, -y0 * sy]], np.float32)
                frame = cv2.warpAffine(small, M, (ow, oh), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            else:
                M = np.array([[s, 0, -s * x0 + 0.5 * (s - 1)], [0, s, -s * y0 + 0.5 * (s - 1)]], np.float32)
                frame = cv2.warpAffine(img, M, (ow, oh), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            if overlay and fa["x"][j] is not None:
                def P(x, y):
                    return int(round((x - x0) * s)), int(round((y - y0) * s))
                frame = frame.copy()
                bx, by, bw, bh = fa["x"][j], fa["y"][j], fa["w"][j], fa["h"][j]
                cv2.rectangle(frame, P(bx, by), P(bx + bw, by + bh), (0, 0, 255), 2)
                if fa["fused_cx"][j] is not None:
                    cv2.circle(frame, P(fa["fused_cx"][j], fa["fused_ey"][j]), 6, (0, 255, 0), -1)
                m = path["params"]["margin"]
                cv2.rectangle(frame, (int(m * ow), int(m * oh)), (int((1 - m) * ow), int((1 - m) * oh)),
                              (0, 255, 255), 1)
            enc.stdin.write(np.ascontiguousarray(frame).tobytes())
            k += 1
        enc.stdin.close()
        enc.wait()
    except (BrokenPipeError, OSError):
        enc.wait()
    err.seek(0)
    msg = err.read().decode("utf-8", errors="replace").strip()
    err.close()
    if enc.returncode != 0:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise cl.ClipError("encode_failed", f"ffmpeg encode exited {enc.returncode}", hint=msg[-400:] or None)
    cl.replace_with_retry(tmp, out)
    ok = k == n
    res = {"ok": ok, "version": SCRIPT_VERSION, "kind": "face_track_render", "out": str(out), "size": [ow, oh],
           "frames_rendered": k, "frames_path": n, "warnings": [] if ok else
           [f"rendered {k} frames, the path has {n}: the path was made from another cut of the video"]}
    return res


# ---------------------------------------------------------------- selftest (simulated detections)

def synth_detections(n, fps, W, H, truth_x, truth_ey, face_h, rng, noise=3.0, outlier_rate=0.02, flow_noise=0.15,
                     misses=(), every=1):
    """det.json-shaped dict from a true face path: YuNet-like box noise, outliers, misses, and LK-like flow."""
    faces = []
    for k in range(n):
        if any(a <= k < b for a, b in misses):
            faces.append([])
            continue
        h = face_h[k]
        w = 0.78 * h
        nx, ny = rng.normal(0, noise, 2)
        if rng.random() < outlier_rate:
            nx, ny = rng.normal(0, 12 * noise, 2)
        cxk, eyk = truth_x[k] + nx, truth_ey[k] + ny
        y = eyk - 0.38 * h
        lm = [cxk - 0.2 * w, eyk, cxk + 0.2 * w, eyk, cxk, eyk + 0.2 * h, cxk - 0.15 * w, eyk + 0.4 * h,
              cxk + 0.15 * w, eyk + 0.4 * h]
        fl = None
        if k > 0 and not any(a <= k - 1 < b for a, b in misses):
            fl = [float(truth_x[k] - truth_x[k - 1] + rng.normal(0, flow_noise)),
                  float(truth_ey[k] - truth_ey[k - 1] + rng.normal(0, flow_noise)), 30]
        faces.append([{"b": [cxk - w / 2, y, w, h], "s": 0.9, "lm": lm, "src": "det" if k % every == 0 else "flow",
                       "fl": fl}])
    return {"ok": True, "kind": "face_detections", "video": None, "fps": cl.frac_str(Fraction(fps)), "width": W,
            "height": H, "frames": n, "scale": 2.0, "faces": faces}


def synth_multi(n, fps, W, H, people, rng, noise=2.0, flow=True, flow_noise=0.15):
    """det.json-shaped dict with several faces: people = [(x, ey, h, present)] per-frame arrays (true centre x,
    eyes y, height; boolean presence). Flow is the true step (+ noise) where the face was there on k-1 too."""
    faces = []
    for k in range(n):
        fs = []
        for x, eyv, hv, pm in people:
            if not pm[k]:
                continue
            h = float(hv[k])
            w = 0.78 * h
            nx, ny = rng.normal(0, noise, 2)
            cxk, eyk = x[k] + nx, eyv[k] + ny
            lm = [cxk - 0.2 * w, eyk, cxk + 0.2 * w, eyk, cxk, eyk + 0.2 * h, cxk - 0.15 * w, eyk + 0.4 * h,
                  cxk + 0.15 * w, eyk + 0.4 * h]
            fl = None
            if flow and k > 0 and pm[k - 1]:
                fl = [float(x[k] - x[k - 1] + rng.normal(0, flow_noise)),
                      float(eyv[k] - eyv[k - 1] + rng.normal(0, flow_noise)), 30]
            fs.append({"b": [cxk - w / 2, eyk - 0.38 * h, w, h], "s": 0.9, "lm": lm, "src": "det", "fl": fl})
        faces.append(fs)
    return {"ok": True, "kind": "face_detections", "video": None, "fps": cl.frac_str(Fraction(fps)), "width": W,
            "height": H, "frames": n, "scale": 2.0, "faces": faces}


def true_inside(path, people, margin=0.0):
    """Fraction of (frame, person) pairs where the TRUE face box (+ margin of the crop) is inside the crop, and the
    count of frames where a present person is fully outside it."""
    np = np_()
    F = path["frames_data"]
    cx, cy, cw, ch = (np.array(F[k], float) for k in ("cx", "cy", "cw", "ch"))
    tot = ins = 0
    out_frames = set()
    for x, eyv, hv, pm in people:
        for k in np.flatnonzero(pm):
            h = float(hv[k])
            w = 0.78 * h
            bx, by = x[k] - w / 2, eyv[k] - 0.38 * h
            mx, my = margin * cw[k], margin * ch[k]
            ok = (bx >= cx[k] - cw[k] / 2 + mx - 0.5 and bx + w <= cx[k] + cw[k] / 2 - mx + 0.5
                  and by >= cy[k] - ch[k] / 2 + my - 0.5 and by + h <= cy[k] + ch[k] / 2 - my + 0.5)
            tot += 1
            ins += ok
            if bx + w < cx[k] - cw[k] / 2 or bx > cx[k] + cw[k] / 2:
                out_frames.add(int(k))
    return (ins / tot if tot else 1.0), len(out_frames)


def _trace(fps, n, cut, rng, shake=0.0):
    """True face path: shot A sways and makes a fast 25 %-of-crop move at 2.5 s; shot B sits elsewhere."""
    np = np_()
    t = np.arange(n) / fps
    # the move: a 0.2 s smoothstep from 760 to 1010 centred on 2.5 s
    u = np.clip((t - 2.4) / 0.2, 0, 1)
    x = 760 + 250 * (3 * u ** 2 - 2 * u ** 3) + 12 * np.sin(2 * np.pi * 0.3 * t)
    y = 300 + 6 * np.sin(2 * np.pi * 0.2 * t)       # room to move: a 9:16 crop of 16:9 is nearly full height
    x[cut:] = 1350 + 10 * np.sin(2 * np.pi * 0.25 * t[cut:])
    y[cut:] = 280.0
    if shake:
        # handheld shake: 3-7 Hz, random phases, `shake` px peak per axis
        for f_, a_ in ((3.1, 0.5), (4.7, 0.3), (6.3, 0.2)):
            x += shake * a_ * np.sin(2 * np.pi * f_ * t + rng.uniform(0, 6.28))
            y += shake * a_ * np.sin(2 * np.pi * f_ * t + rng.uniform(0, 6.28))
    return x, y


def _p0(q):
    return [f["id"] for f in q["findings"] if f["rank"] == "P0"]


def _ids(q, rank=None):
    return [f["id"] for f in q["findings"] if rank is None or f["rank"] == rank]


def selftest(workdir=None):
    global _FORCE_L2
    np = np_()
    rng = np.random.default_rng(11)
    fps, W, H = 30, 1920, 1080
    n, cut = 240, 150
    V = "1080x1920"
    checks = {}

    def check(name, cond, measured):
        checks[name] = {"ok": bool(cond), "measured": measured}
        cl.log(f"{'ok  ' if cond else 'FAIL'} {name}: {measured}")

    work = Path(workdir) if workdir else None
    if work:
        work.mkdir(parents=True, exist_ok=True)
    t_ = np.arange(n) / fps
    on = np.ones(n, bool)
    fh = np.full(n, 200.0)
    # --- smooth mode on noisy detections with outliers and a miss
    tx, ty = _trace(fps, n, cut, rng)
    det = synth_detections(n, fps, W, H, tx, ty, fh, rng, misses=[(60, 70)])
    tr = track(det, cut_frames=[cut])
    path = stabilize(tr, size=V, mode="smooth", det_scale=2.0)
    q = qc(path, qc_dir=(work / "smooth") if work else None, truth={"cx": tx, "ey": ty})
    m = q["metrics"]
    check("smooth: camera 2nd-diff RMS vs raw detections >= 20x lower (L1 path)",
          (m["d2_rms_reduction_x"] or 1e9) >= 20,
          f"raw {m['raw_d2_rms_px']} px/f^2 -> camera {m['camera_d2_rms_px']} ({m['d2_rms_reduction_x']}x); "
          f"oscillation {m['camera_jitter_px']} canvas px, bumps {m['camera_bumps']}")
    check("smooth: face box + 5 % margin inside the crop on every frame", m["face_inside_margin_pct"] == 100.0,
          f"{m['face_inside_margin_pct']} %")
    check("smooth: no pan across the cut", m["pan_across_cut"] == 0, m["pan_across_cut"])
    check("smooth: qc gate passes", q["ok"], _p0(q))
    cxp = np.array(path["frames_data"]["cx"])
    # zero lag: the camera's 50 % crossing of the move vs the face's (2.5 s = frame 75)
    a0, a1 = cxp[40], cxp[cut - 20]
    half = (a0 + a1) / 2
    cam_cross = int(np.argmax((cxp[:cut] - half) * np.sign(a1 - a0) >= 0))
    face_cross = int(np.argmax((tx[:cut] - (tx[40] + tx[cut - 20]) / 2) >= 0))
    check("smooth: zero lag on the fast move (camera 50 % crossing within +-2 frames of the face's)",
          abs(cam_cross - face_cross) <= 2, f"camera f{cam_cross}, face f{face_cross}")
    cw0 = path["frames_data"]["cw"][cut]
    post = float(np.max(np.abs(cxp[cut:cut + 8] - cxp[cut])))
    err0 = abs(cxp[cut] - tx[cut])
    check("smooth: reset snaps on the cut frame (face within the dead zone at f_cut, < 1 % W drift after)",
          err0 <= 0.04 * cw0 + 4 and post < 0.01 * cw0, f"offset {err0:.1f} px, drift {post:.2f} px (cw {cw0:.0f})")
    # --- no scipy: the quadratic fallback still cuts the jitter >= 10x and holds the face (regression: the 20x L1
    #     threshold made the selftest fail without the optional scipy)
    _FORCE_L2 = True
    try:
        p_l2 = stabilize(tr, size=V, mode="smooth", det_scale=2.0)
    finally:
        _FORCE_L2 = False
    q_l2 = qc(p_l2)
    m2 = q_l2["metrics"]
    check("no scipy: l2_banded camera >= 10x lower 2nd-diff RMS, face inside 100 %, qc passes",
          p_l2["segments"][0]["method"] == "l2_banded" and (m2["d2_rms_reduction_x"] or 1e9) >= 10
          and m2["face_inside_margin_pct"] == 100.0 and q_l2["ok"],
          f"{p_l2['segments'][0]['method']}: {m2['camera_d2_rms_px']} px/f^2 ({m2['d2_rms_reduction_x']}x), inside "
          f"{m2['face_inside_margin_pct']} %, P0 {_p0(q_l2)}")
    # --- negative control: no reset at the cut must fail the gate
    q_nr = qc(stabilize(tr, size=V, mode="smooth", det_scale=2.0, reset=False))
    check("negative: --no-reset is caught as a pan across the cut", q_nr["metrics"]["pan_across_cut"] >= 1,
          q_nr["metrics"]["pan_across_cut"])
    # --- lock mode cancels injected handheld shake on the canvas
    sx, sy = _trace(fps, n, cut, np.random.default_rng(5), shake=14.0)
    det_s = synth_detections(n, fps, W, H, sx, sy, fh, rng)
    tr_s = track(det_s, cut_frames=[cut])
    lock = stabilize(tr_s, size=V, mode="lock", det_scale=2.0)
    smooth = stabilize(tr_s, size=V, mode="smooth", det_scale=2.0)
    ql = qc(lock, qc_dir=(work / "lock") if work else None, truth={"cx": sx, "ey": sy})
    qs = qc(smooth, truth={"cx": sx, "ey": sy})
    sl, ss = ql["metrics"]["truth_canvas_std_px"], qs["metrics"]["truth_canvas_std_px"]
    check("lock: shake on the canvas (high-pass std) cut by >= 85 % vs smooth", sl <= 0.15 * ss,
          f"smooth {ss} px -> lock {sl} px ({100 * (1 - sl / ss):.1f} % removed)")
    check("lock: qc gate passes (flow-measured canvas jitter)", ql["ok"],
          f"canvas hp std {ql['metrics']['canvas_face_jitter_px']} px; P0 {_p0(ql)}")
    # negative control for the lock gate (regression: the gate compared the camera with the path it was built
    # from and could never fail): noise added to the lock camera must fail canvas_jitter
    bad = json_copy(lock)
    nz = np.random.default_rng(9).normal(0, 2.0, (2, n))
    bad["frames_data"]["cx"] = [v + float(e) for v, e in zip(bad["frames_data"]["cx"], nz[0])]
    bad["frames_data"]["cy"] = [v + float(e) for v, e in zip(bad["frames_data"]["cy"], nz[1])]
    q_bad = qc(bad)
    check("negative: N(0, 2 px) noise on the lock camera fails canvas_jitter (the gate is not circular)",
          "canvas_jitter" in _p0(q_bad),
          f"canvas hp std {q_bad['metrics']['canvas_face_jitter_px']} px, P0 {_p0(q_bad)}")
    steady = stabilize(tr_s, size=V, mode="steady", det_scale=2.0)
    qst = qc(steady, truth={"cx": sx, "ey": sy})

    def shot_b_shake(p_):   # canvas shake of the true face in shot B (no deliberate move there)
        F_ = p_["frames_data"]
        cx_, cy_, cw_, ch_ = (np.array(F_[k], float)[cut:] for k in ("cx", "cy", "cw", "ch"))
        s_ = 1920 / ch_
        u_, v_ = (sx[cut:] - (cx_ - cw_ / 2)) * s_, (sy[cut:] - (cy_ - ch_ / 2)) * s_
        return float(np.hypot(np.nanstd(hp(u_, [])), np.nanstd(hp(v_, []))))
    b_sm, b_st = shot_b_shake(smooth), shot_b_shake(steady)
    check("steady: shake on the canvas cut by >= 85 % vs smooth (shot B), qc gate passes",
          b_st <= 0.15 * b_sm and qst["ok"], f"smooth {b_sm:.3f} px -> steady {b_st:.3f} px "
          f"({100 * (1 - b_st / b_sm):.1f} % removed); whole clip incl. the fast move {ss} -> "
          f"{qst['metrics']['truth_canvas_std_px']} px; P0 {_p0(qst)}")
    # --- lock / steady without flow: steady is the smooth camera; lock is reported as unverified, never a pass
    #     by construction (regression: P0 circular gate)
    still_x, still_y = np.full(n, 900.0), np.full(n, 350.0)
    det_nf = synth_detections(n, fps, W, H, still_x, still_y, fh, np.random.default_rng(21), outlier_rate=0)
    for fs in det_nf["faces"]:
        for f in fs:
            f["fl"] = None
    tr_nf = track(det_nf)
    rows = {}
    for md in ("smooth", "lock", "steady"):
        p_ = stabilize(tr_nf, size=V, mode=md, det_scale=2.0)
        rows[md] = (p_, qc(p_, truth={"cx": still_x, "ey": still_y}))
    st_sm = rows["smooth"][1]["metrics"]["truth_canvas_std_px"]
    st_st = rows["steady"][1]["metrics"]["truth_canvas_std_px"]
    check("steady without flow = the smooth camera (true canvas std within 0.2 px of smooth)",
          abs(st_st - st_sm) <= 0.2 and "no flow" in rows["steady"][0]["segments"][0]["method"],
          f"smooth {st_sm} px, steady {st_st} px ({rows['steady'][0]['segments'][0]['method']})")
    q_lnf = rows["lock"][1]
    check("lock without flow: qc reports canvas_jitter_unverified (P1) instead of a circular pass",
          "canvas_jitter_unverified" in _ids(q_lnf, "P1"),
          f"true canvas std {q_lnf['metrics']['truth_canvas_std_px']} px; findings {_ids(q_lnf)}")
    # --- partial flow (flow on 50 % of frames, random): fusion keeps smoothing at the gaps (regression: the gaps
    #     passed raw detector noise to the lock camera, 11.3 px/f^2 vs 1.5 without flow)
    pf = {}
    for frac in (1.0, 0.5, 0.0):
        r_ = np.random.default_rng(7)
        mx = 900 + 10 * np.sin(2 * np.pi * 0.3 * t_)
        d_ = synth_detections(n, fps, W, H, mx, np.full(n, 300.0), fh, r_, noise=3.0, outlier_rate=0)
        keep = r_.random(n) < frac
        for k, fs in enumerate(d_["faces"]):
            for f in fs:
                if not keep[k]:
                    f["fl"] = None
        p_ = stabilize(track(d_), size=V, mode="lock", det_scale=2.0)
        pf[frac] = qc(p_, truth={"cx": mx, "ey": np.full(n, 300.0)})["metrics"]["truth_canvas_jitter_px"]
    check("partial flow (50 %): lock true canvas jitter <= 1.2 x the worse of full flow and no flow",
          pf[0.5] <= 1.2 * max(pf[1.0], pf[0.0]), f"100 % {pf[1.0]}, 50 % {pf[0.5]}, 0 % {pf[0.0]} px/f^2")
    # --- jump cut (same camera): the scale changes by --jump-scale and the face stays put on the canvas (ref 04 rule 5)
    jx = 900 + 8 * np.sin(2 * np.pi * 0.2 * t_)
    jx[cut:] += 14.0                         # the speaker shifted a little across the jump cut
    jy = np.full(n, 300.0)
    det_j = synth_detections(n, fps, W, H, jx, jy, np.full(n, 250.0), np.random.default_rng(3))
    pj = stabilize(track(det_j, jump_cuts=[cut]), size=V, mode="smooth", det_scale=2.0)
    F_ = pj["frames_data"]
    ratio = F_["ch"][cut] / F_["ch"][cut - 1]
    s0, s1 = 1920 / F_["ch"][cut - 1], 1920 / F_["ch"][cut]
    u0 = (jx[cut - 1] - (F_["cx"][cut - 1] - F_["cw"][cut - 1] / 2)) * s0
    u1 = (jx[cut] - (F_["cx"][cut] - F_["cw"][cut] / 2)) * s1
    qj = qc(pj)
    check("jump cut: crop scale changes 4-10 % and the face moves <= 0.625 % W (6.75 px) on the canvas; qc passes",
          0.90 <= ratio <= 0.96 and abs(u1 - u0) <= 6.75 and qj["ok"] and "jump_anchor" not in _ids(qj),
          f"scale ratio {ratio:.3f}, face shift {abs(u1 - u0):.2f} px, qc jump rows {qj['metrics']['jump_cuts']}")
    # jump-cut gates in qc (regression: only the selftest checked the anchor): shift shot 2 by 40 source px and keep
    # the scale -> jump_anchor P0 + jump_scale P1
    bj = json_copy(pj)
    for k in range(cut, n):
        bj["frames_data"]["cx"][k] += 40.0
        bj["frames_data"]["ch"][k] = bj["frames_data"]["ch"][cut - 1]
        bj["frames_data"]["cw"][k] = bj["frames_data"]["cw"][cut - 1]
        bj["frames_data"]["cy"][k] = bj["frames_data"]["cy"][cut - 1]
    qbj = qc(bj)
    check("negative: a jump cut that moves the face 40 px and keeps the scale fails jump_anchor (P0) + jump_scale (P1)",
          "jump_anchor" in _p0(qbj) and "jump_scale" in _ids(qbj, "P1"),
          f"rows {qbj['metrics']['jump_cuts']}; findings {_ids(qbj)}")
    # --- camera jitter gate: smooth sways pass (regression: 1.4826 x median |d2| failed continuous pans) ...
    sway = []
    for amp, hz in ((80, 0.2), (150, 0.25), (60, 0.5)):
        x_ = 900 + amp * np.sin(2 * np.pi * hz * np.arange(300) / fps)
        d_ = synth_detections(300, fps, W, H, x_, np.full(300, 350.0), np.full(300, 200.0),
                              np.random.default_rng(1), noise=0.5, outlier_rate=0)
        q_ = qc(stabilize(track(d_), size=V, mode="smooth", det_scale=2.0))
        sway.append((amp, hz, q_["metrics"]["camera_jitter_px"], q_["ok"], _p0(q_)))
    check("smooth sways (80 px 0.2 Hz, 150 px 0.25 Hz, 60 px 0.5 Hz) pass camera_jitter",
          all(r[3] for r in sway), [f"{a} px {h} Hz: {j} px ok={o} {p}" for a, h, j, o, p in sway])
    # ... and real camera noise fails whatever share of the clip it covers (regression: a whole-clip median let
    # noise on < 50 % of the frames pass)
    nz2 = json_copy(path)
    e = np.random.default_rng(1).normal(0, 2.0, (2, n - cut))
    for k in range(cut, n):
        nz2["frames_data"]["cx"][k] += float(e[0, k - cut])
        nz2["frames_data"]["cy"][k] += float(e[1, k - cut])
    zz = json_copy(path)
    for k in range(30, 78):
        zz["frames_data"]["cx"][k] += 10.0 * (1 if k % 2 else -1)
    q_n1, q_n2 = qc(nz2), qc(zz)
    check("negative: N(0, 2 px) camera noise on shot 2 only (37 % of frames) and a +-10 px zigzag on 20 % fail "
          "camera_jitter", "camera_jitter" in _p0(q_n1) and "camera_jitter" in _p0(q_n2),
          f"{q_n1['metrics']['camera_jitter_px']} / {q_n2['metrics']['camera_jitter_px']} px (limit "
          f"{GATE_CAM_JITTER / 100 * 1080:.2f})")
    # --- close-up with tight slack: the raw-box noise envelope keeps the camera still (regression: sparse
    #     noise-driven jerks passed the median gate); a twitch injected into a still path is reported
    cw_max = 607.5
    h_cu = (cw_max - 0.1 * cw_max - 12) / 0.78
    d_cu = synth_detections(300, fps, W, H, np.full(300, 960.0), np.full(300, 540 - 0.12 * h_cu),
                            np.full(300, h_cu), np.random.default_rng(2), noise=3.0, outlier_rate=0)
    r_h = np.random.default_rng(22)
    for fs in d_cu["faces"]:       # + 2 px height noise, centre kept
        for f in fs:
            dh_ = float(r_h.normal(0, 2.0))
            f["b"][1] -= dh_ / 2
            f["b"][3] += dh_
    p_cu = stabilize(track(d_cu), size=V, mode="smooth", det_scale=2.0)
    q_cu = qc(p_cu)
    mv = int((np.abs(np.diff(p_cu["frames_data"]["cx"])) > 0.05).sum())
    still = json_copy(rows["smooth"][0])
    for k, dv in zip(range(100, 103), (2.0, 4.0, 2.0)):
        for kk in range(k, n):
            still["frames_data"]["cx"][kk] += dv / 2
    q_tw = qc(still)
    check("close-up, 12 px slack: camera moves on <= 5 % of frames, no bump; negative: a 4 px twitch in 3 frames "
          "is reported (camera_bump)", mv <= 15 and q_cu["metrics"]["camera_bumps"] == 0 and q_cu["ok"]
          and "camera_bump" in _ids(q_tw), f"moves on {mv}/299 frames, bumps {q_cu['metrics']['camera_bumps']}, "
          f"P0 {_p0(q_cu)}; twitch: {_ids(q_tw)}")
    # --- close-up face 61 % of the source height: lock / steady give up travel room before cutting the face
    #     (regression: --lock-room shrank the crop below the face); a face wider than the crop is info, not P0
    cu_res = {}
    for md in ("smooth", "lock", "steady"):
        d_ = synth_detections(150, fps, W, H, np.full(150, 960.0), np.full(150, 520.0), np.full(150, 660.0),
                              np.random.default_rng(4), noise=1.0, outlier_rate=0)
        q_ = qc(stabilize(track(d_), size=V, mode=md, det_scale=2.0))
        cu_res[md] = (q_["metrics"]["face_inside_crop_pct"], _p0(q_))
    check("close-up (face 61 % H): smooth, lock and steady hold the whole face, no face_outside_margin P0",
          all(v[0] == 100.0 and "face_outside_margin" not in v[1] and "face_outside_crop" not in v[1]
              for v in cu_res.values()), cu_res)
    # --- steady at the source edge, then a fast move: the face box (margin 0) stays inside (regression: the
    #     whole face bound was dropped at the edge and qc skipped those frames)
    e_x = 15 + 78 + np.where(t_ < 2.0, 0.0, 500 * np.clip((t_ - 2.0) / 0.4, 0, 1) ** 2 *
                              (3 - 2 * np.clip((t_ - 2.0) / 0.4, 0, 1)))
    d_e = synth_detections(n, fps, W, H, e_x, np.full(n, 400.0), fh, np.random.default_rng(6), noise=2.0,
                           outlier_rate=0)
    p_e = stabilize(track(d_e), size=V, mode="steady", det_scale=2.0)
    q_e = qc(p_e)
    pe = [(e_x, np.full(n, 400.0), fh, on)]
    fin_e, out_e = true_inside(p_e, pe)
    bad_e = json_copy(p_e)       # negative control: push the crop 40 px right on the edge frames (face cut)
    for k in range(0, 50):
        bad_e["frames_data"]["cx"][k] += 40.0
    q_be = qc(bad_e)
    check("steady: face at the source edge then a 500 px move: the true face is fully inside the crop on every "
          "frame, qc passes; negative: a crop that cuts the face on edge frames fails face_outside_crop (P0)",
          fin_e == 1.0 and q_e["ok"] and "face_outside_crop" in _p0(q_be),
          f"true face inside {100 * fin_e:.1f} %, edge frames {q_e['metrics']['edge_frames']}, P0 {_p0(q_e)}; "
          f"negative P0 {_p0(q_be)}")
    # --- no flow, a 500 px move in 0.2 s: real detections at the corners are kept, rejected ones are gated on
    #     the fused box (regression: rejected frames left the margin gate)
    mvx = 760 + 500 * np.clip((t_ - 3.0) / 0.2, 0, 1) ** 2 * (3 - 2 * np.clip((t_ - 3.0) / 0.2, 0, 1))
    d_m = synth_detections(n, fps, W, H, mvx, np.full(n, 350.0), fh, np.random.default_rng(2), noise=3.0)
    for fs in d_m["faces"]:
        for f in fs:
            f["fl"] = None
    p_m = stabilize(track(d_m), size=V, mode="smooth", det_scale=2.0)
    q_m = qc(p_m)
    fin_m, _ = true_inside(p_m, [(mvx, np.full(n, 350.0), fh, on)], margin=0.05 - 0.01)
    check("no flow, 500 px move in 0.2 s: true face + 4 % margin inside on every frame, rejected frames gated",
          fin_m == 1.0 and q_m["ok"],
          f"true inside {100 * fin_m:.1f} %, rejected {q_m['metrics']['rejected_detections']}"
          f" (gated {q_m['metrics']['rejected_gated']}), P0 {_p0(q_m)}")
    # --- one face jumps 500 px with no cut (two tracks): a hand-off (virtual cut), never a camera on an empty spot
    #     (regression P0: only the chosen track was checked, the face was off-screen for half the shot)
    hx = np.where(np.arange(150) < 75, 700.0, 1200.0)
    p1 = [(hx, np.full(150, 350.0), np.full(150, 200.0), np.ones(150, bool))]
    d_h = synth_multi(150, fps, W, H, p1, np.random.default_rng(8))
    tr_h = track(d_h)
    p_h = stabilize(tr_h, size=V, mode="smooth", det_scale=2.0)
    q_h = qc(p_h)
    fin_h, out_h = true_inside(p_h, p1)
    check("hand-off: a face that jumps 500 px with no cut gets a virtual cut; true face inside 100 %, qc passes",
          fin_h == 1.0 and q_h["ok"] and 75 in p_h["resets"],
          f"segments {[(s['start'], s['end'], s['kind']) for s in p_h['segments']]}, true inside {100 * fin_h:.1f} %, "
          f"P0 {_p0(q_h)}")
    # 4 places, 40 frames each (4 tracks; was framed 'wide' and cut the face on 120/160 frames)
    x4 = np.repeat([300.0, 800.0, 1300.0, 1700.0], 40)
    p4 = [(x4, np.full(160, 350.0), np.full(160, 200.0), np.ones(160, bool))]
    p_4 = stabilize(track(synth_multi(160, fps, W, H, p4, np.random.default_rng(51))), size=V, det_scale=2.0)
    q_4 = qc(p_4)
    fin_4, _ = true_inside(p_4, p4)
    check("hand-off: one face at 4 places (4 tracks) -> 4 segments, never wide, true face inside 100 %",
          fin_4 == 1.0 and q_4["ok"] and all(s["kind"] == "face" for s in p_4["segments"]),
          f"{[(s['start'], s['kind']) for s in p_4['segments']]}, inside {100 * fin_4:.1f} %, P0 {_p0(q_4)}")
    # negative control: drop the subject after the jump (camera holds on an empty spot) -> face_lost P0
    tr_l = json_copy(tr_h)
    tr_l["segments"] = [dict(tr_l["segments"][0], end=150)]
    for k in range(75, 150):
        for key in ("x", "y", "w", "h", "ex", "ey", "fdx", "fdy", "src"):
            tr_l["subject"][key][k] = None
    q_l = qc(stabilize(tr_l, size=V, det_scale=2.0))
    check("negative: the camera held on an empty spot while the only face is elsewhere fails face_lost (P0)",
          "face_lost" in _p0(q_l), f"lost frames {q_l['metrics']['face_lost_frames']}, P0 {_p0(q_l)}")
    # a missed cut between two shots (face 900 -> 1300 at f200, cuts gave only f100) is a hand-off too
    mxs = np.where(np.arange(300) < 100, 700.0, np.where(np.arange(300) < 200, 900.0, 1300.0))
    pm_ = [(mxs, np.full(300, 350.0), np.full(300, 200.0), np.ones(300, bool))]
    p_mc = stabilize(track(synth_multi(300, fps, W, H, pm_, np.random.default_rng(12)), cut_frames=[100]),
                     size=V, det_scale=2.0)
    q_mc = qc(p_mc)
    fin_mc, _ = true_inside(p_mc, pm_)
    check("missed cut (f200 not in the cut list): hand-off resets there; true face inside 100 %, qc passes",
          fin_mc == 1.0 and q_mc["ok"] and 200 in p_mc["resets"],
          f"resets {p_mc['resets']}, inside {100 * fin_mc:.1f} %, P0 {_p0(q_mc)}")
    # --- 'wide' segments are checked and hold their faces (regression: a static strip crop cut faces with qc 100 %)
    wx = np.where(np.arange(300) < 110, 300.0, np.where(np.arange(300) < 185,
                  300 + 1300 * (np.arange(300) - 110) / 75.0, 1600.0))
    wpm = (np.arange(300) >= 110) & (np.arange(300) < 185)
    pw = [(wx, np.full(300, 350.0), np.full(300, 200.0), wpm)]
    tr_w = track(synth_multi(300, fps, W, H, pw, np.random.default_rng(13)))
    wres = {}
    for sz in ("1080x1440", V):
        p_ = stabilize(tr_w, size=sz, det_scale=2.0)
        q_ = qc(p_)
        wres[sz] = (true_inside(p_, pw), q_["ok"], _p0(q_), q_["metrics"]["face_inside_crop_pct"])
    check("wide (a face crossing 25 % of a shot): the true face stays inside the crop and qc measures it",
          all(v[0][0] == 1.0 and v[1] for v in wres.values()),
          {k: f"inside {100 * v[0][0]:.1f} %, qc {v[3]} %, ok {v[1]} {v[2]}" for k, v in wres.items()})
    # two faces never together in one shot (A f0-59, B 30 frames later): both framed in turn
    ca = np.arange(240) < 60
    cb = (np.arange(240) >= 100) & (np.arange(240) < 130)
    pc = [(np.full(240, 500.0), np.full(240, 350.0), np.full(240, 200.0), ca),
          (np.full(240, 1450.0), np.full(240, 350.0), np.full(240, 200.0), cb)]
    p_c = stabilize(track(synth_multi(240, fps, W, H, pc, np.random.default_rng(14))), size=V, det_scale=2.0)
    q_c = qc(p_c)
    fin_c, _ = true_inside(p_c, pc)
    check("two faces never on screen together (cover 25 % + 12.5 %): each framed in turn, inside 100 %, qc passes",
          fin_c == 1.0 and q_c["ok"], f"{[(s['start'], s['kind']) for s in p_c['segments']]}, inside "
          f"{100 * fin_c:.1f} %, P0 {_p0(q_c)}")
    # --- two people (SKILL: a wider crop that holds both, never two half faces or a split screen)
    g2 = [(np.full(150, 650.0), np.full(150, 350.0), np.full(150, 220.0), np.ones(150, bool)),
          (np.full(150, 1300.0), np.full(150, 350.0), np.full(150, 210.0), np.ones(150, bool))]
    d_g = synth_multi(150, fps, W, H, g2, np.random.default_rng(15))
    tg_916 = track(d_g, subject="group", size=V)
    p_g916 = stabilize(tg_916, size=V, det_scale=2.0)
    q_g916 = qc(p_g916)
    g3 = [(np.full(150, 750.0), np.full(150, 350.0), np.full(150, 220.0), np.ones(150, bool)),
          (np.full(150, 1200.0), np.full(150, 350.0), np.full(150, 210.0), np.ones(150, bool))]
    tg_34 = track(synth_multi(150, fps, W, H, g3, np.random.default_rng(15)), subject="group", size="1080x1440")
    p_g34 = stabilize(tg_34, size="1080x1440", det_scale=2.0)
    q_g34 = qc(p_g34)
    fin_916 = true_inside(p_g916, g2[:1])[0], true_inside(p_g916, g2[1:])[0]
    fin_34, _ = true_inside(p_g34, g3)
    check("group 650/1300 at 9:16 cannot hold both -> one face fully framed + warning (no half faces); 750/1200 at "
          "3:4 -> group, both inside",
          max(fin_916) == 1.0 and min(fin_916) < 0.05 and p_g916["segments"][0]["kind"] == "face"
          and any("do not fit" in w or "need" in w for w in tg_916["warnings"]) and q_g916["ok"]
          and p_g34["segments"][0]["kind"] == "group" and fin_34 == 1.0 and q_g34["ok"],
          f"9:16 kind {p_g916['segments'][0]['kind']}, faces inside {fin_916}, P1 {_ids(q_g916, 'P1')}; 3:4 kind "
          f"{p_g34['segments'][0]['kind']}, inside {100 * fin_34:.1f} %, P0 {_p0(q_g34)}")
    # auto with two persistent faces 600 / 1350: no single crop holds both -> warning + qc second_face_cropped
    a2 = [(np.full(150, 600.0), np.full(150, 350.0), np.full(150, 260.0), np.ones(150, bool)),
          (np.full(150, 1350.0), np.full(150, 350.0), np.full(150, 260.0), np.ones(150, bool))]
    ta = track(synth_multi(150, fps, W, H, a2, np.random.default_rng(16)), size="1080x1440")
    qa = qc(stabilize(ta, size="1080x1440", det_scale=2.0))
    a3 = [(np.full(150, 800.0), np.full(150, 350.0), np.full(150, 200.0), np.ones(150, bool)),
          (np.full(150, 1150.0), np.full(150, 350.0), np.full(150, 200.0), np.ones(150, bool))]
    tb = track(synth_multi(150, fps, W, H, a3, np.random.default_rng(17)), size="1080x1440")
    pb_ = stabilize(tb, size="1080x1440", det_scale=2.0)
    fin_b, _ = true_inside(pb_, a3)
    check("auto, two faces: too far apart -> warning + second_face_cropped P1; close enough -> group, both inside",
          ta["warnings"] and "second_face_cropped" in _ids(qa, "P1") and pb_["segments"][0]["kind"] == "group"
          and fin_b == 1.0, f"far: {_ids(qa)}; near: kind {pb_['segments'][0]['kind']}, inside {100 * fin_b:.1f} %")
    # group members never on screen together: no group; the fused path never pinned at x = 0 (regression)
    gn = [(np.full(240, 700.0), np.full(240, 350.0), np.full(240, 200.0), np.arange(240) < 120),
          (np.full(240, 1300.0), np.full(240, 350.0), np.full(240, 200.0), np.arange(240) >= 120)]
    tg_n = track(synth_multi(240, fps, W, H, gn, np.random.default_rng(18)), subject="group", size=V)
    p_gn = stabilize(tg_n, size=V, det_scale=2.0)
    fin_gn, _ = true_inside(p_gn, gn)
    fcx = [v for v in p_gn["face"]["fused_cx"] if v is not None]
    check("group members never together: not a group, each framed (hand-off), fused path never at 0, inside 100 %",
          all(s["kind"] != "group" for s in p_gn["segments"]) and min(fcx) > 400 and fin_gn == 1.0 and qc(p_gn)["ok"],
          f"{[(s['start'], s['kind']) for s in p_gn['segments']]}, fused x {min(fcx):.0f}-{max(fcx):.0f}, "
          f"inside {100 * fin_gn:.1f} %")
    # --- steady: no camera motion after the face leaves (regression: the shake residue kept driving the camera)
    xs_ = 700 + 150 * t_
    pm_s = np.arange(n) < 100
    ps = [(xs_, np.full(n, 350.0), fh, pm_s)]
    p_s = stabilize(track(synth_multi(n, fps, W, H, ps, np.random.default_rng(19)), cut_frames=[cut]), size=V,
                    mode="steady", det_scale=2.0)
    drift = float(np.ptp(np.array(p_s["frames_data"]["cx"][101:cut])))
    check("steady: the camera holds still after the face leaves (drift over f101-149 < 0.5 px), no pan across the cut",
          drift < 0.5 and qc(p_s)["metrics"]["pan_across_cut"] == 0, f"drift {drift:.2f} px")
    # --- cut sources merge, a missing cut source is reported
    with tempfile.TemporaryDirectory() as td:
        cj = Path(td) / "cuts.json"
        cj.write_text('{"reset_frames": [100]}', encoding="utf-8")
        ns = argparse.Namespace(cuts=str(cj), cut_frames="200", no_detect_cuts=True)
        got, how = _cut_list(ns, None, None)
        check("cuts: --cuts file + --cut-frames merge (union), sources recorded",
              got == [100, 200] and how == "file+list",
              f"{got} from {how}")
        tr_nc = track(det, cuts_from="none")
        q_nc = qc(stabilize(tr_nc, size=V, det_scale=2.0))
        check("no cut source: track warns and qc reports no_cut_source (P1)",
              any("no cut source" in w for w in tr_nc["warnings"]) and "no_cut_source" in _ids(q_nc, "P1"),
              _ids(q_nc))
        # --- speaker needs audio + video: exit 2 instead of a silent fall back to auto
        codes = []
        for kw in ({"video": None}, {"video": str(cj)}):
            try:
                track(d_g, subject="speaker", **kw)
                codes.append(0)
            except cl.ClipError as e_:
                codes.append(e_.exit_code)
        check("speaker without a readable video / audio: exit 2 (never a silent fall back to auto)",
              codes == [2, 2], codes)
        # --- model errors: a missing CLIP_YUNET_MODEL file and a corrupt .onnx exit 2 with JSON
        old = os.environ.get(MODEL_ENV)
        os.environ[MODEL_ENV] = str(Path(td) / "missing.onnx")
        try:
            find_model()
            env_code = 0
        except cl.ClipError as e_:
            env_code = e_.exit_code
        finally:
            if old is None:
                os.environ.pop(MODEL_ENV, None)
            else:
                os.environ[MODEL_ENV] = old
        badm = Path(td) / "face_detection_yunet_2023mar.onnx"
        badm.write_bytes(b"garbage")
        try:
            detect(str(Path(td) / "none.mp4"), "ffmpeg", model=str(badm))
            bad_code = (0, None)
        except cl.ClipError as e_:
            bad_code = (e_.exit_code, e_.code)
        check("model: CLIP_YUNET_MODEL pointing to a missing file -> exit 2; a corrupt .onnx -> model_bad exit 2",
              env_code == 2 and bad_code == (2, "model_bad"), f"env {env_code}, corrupt {bad_code}")
        # --- the qc subcommand writes next to the path in qc/ (same place as run and ref 08)
        pj_path = Path(td) / "wd" / "path.json"
        cl.write_json_atomic(pj_path, path)
        cp = subprocess.run([sys.executable, "-P", os.path.abspath(__file__), "qc", str(pj_path), "--no-plot"],
                            capture_output=True)
        check("qc subcommand: default --qc-dir is <path dir>/qc", cp.returncode == 0
              and (pj_path.parent / "qc" / "face_track_qc.json").is_file(), f"exit {cp.returncode}")
    ok = all(c["ok"] for c in checks.values())
    return {"ok": ok, "version": SCRIPT_VERSION, "kind": "face_track_selftest", "checks": checks,
            "smooth_metrics": m, "lock_metrics": ql["metrics"], "workdir": str(work) if work else None}


def json_copy(obj):
    import json
    return json.loads(json.dumps(obj))


# ---------------------------------------------------------------- CLI

class _Parser(argparse.ArgumentParser):
    def error(self, message):  # keep the one-JSON-object stdout contract on usage errors
        raise cl.ClipError("usage", message, hint=self.format_usage().strip(), exit_code=2)


def main() -> int:
    try:
        return _run()
    except cl.ClipError as e:  # the JSON envelope carries the version too
        env = e.envelope()
        env["version"] = SCRIPT_VERSION
        cl.emit(env)
        cl.log(f"error [{e.code}]: {e.message}" + (f"\nhint: {e.hint}" if e.hint else ""))
        return e.exit_code


def _add_detect(p):
    p.add_argument("--every", type=int, default=0, help="run the detector every Nth frame (0 = auto)")
    p.add_argument("--max-width", type=int, default=MAX_W)
    p.add_argument("--min-face", type=float, default=MIN_FACE, help="min face height, fraction of the frame")
    p.add_argument("--score", type=float, default=SCORE)
    p.add_argument("--model", help=f"YuNet .onnx (else ${MODEL_ENV}, ./models, ~/models/yunet, ...)")
    p.add_argument("--max-frames", type=int)
    p.add_argument("--force", action="store_true", help="ignore the detection cache")


def _add_track(p):
    p.add_argument("--cuts", help="cuts.py JSON (reset_frames) or a JSON list of frames (merged with the others)")
    p.add_argument("--cut-frames", help="comma-separated cut frames, e.g. the splice frames (merged)")
    p.add_argument("--no-detect-cuts", action="store_true", help="do not run cuts.py on the video (merged otherwise)")
    p.add_argument("--jump-cuts", help="comma-separated same-camera jump-cut frames (scale change + anchor)")
    p.add_argument("--subject", default="auto", choices=["auto", "largest", "central", "group", "speaker"])
    p.add_argument("--hold", type=float, default=HOLD_S)


def _add_stab(p):
    p.add_argument("--mode", default="smooth", choices=["smooth", "lock", "steady"])
    p.add_argument("--size", default=SIZE, help="output WxH (default 1080x1440; 1080x1920 for 9:16)")
    p.add_argument("--face-h", type=float, default=FACE_H)
    p.add_argument("--eyes-y", type=float, default=EYES_Y)
    p.add_argument("--margin", type=float, default=MARGIN)
    p.add_argument("--dead-zone", type=float, default=DZ_X, help="dead-zone width, fraction of the crop width")
    p.add_argument("--dead-zone-y", type=float, default=DZ_Y)
    p.add_argument("--strength", type=float, default=1.0, help="smooth mode: x the smoothness weights")
    p.add_argument("--max-speed", type=float, default=MAX_SPEED, help="soft cap, crop widths per second")
    p.add_argument("--max-upscale", type=float, default=MAX_UPSCALE)
    p.add_argument("--lock-hz", type=float, default=LOCK_HZ)
    p.add_argument("--lock-room", type=float, default=LOCK_ROOM, help="lock: travel room each side, x the crop")
    p.add_argument("--jump-scale", type=float, default=JUMP_SCALE)
    p.add_argument("--no-reset", action="store_true", help="negative control: smooth across cuts")


def _stab_kwargs(a):
    if not 0.05 <= a.face_h <= 0.9 or not 0 <= a.margin < 0.3 or not 0 <= a.eyes_y <= 1:
        raise cl.ClipError("usage", "--face-h 0.05-0.9, --margin 0-0.3, --eyes-y 0-1", exit_code=2)
    return dict(size=a.size, mode=a.mode, face_h=a.face_h, eyes_y=a.eyes_y, margin=a.margin, dz_x=a.dead_zone,
                dz_y=a.dead_zone_y, strength=a.strength, max_speed=a.max_speed, max_upscale=a.max_upscale,
                lock_hz=a.lock_hz, jump_scale=a.jump_scale, reset=not a.no_reset, lock_room=a.lock_room)


def _cut_list(a, video, ffmpeg):
    """Union of every cut source: --cuts file, --cut-frames, and cuts.py on the video (unless --no-detect-cuts or no
    readable video). Returns (sorted frames, "file+list+cuts.py" | "none")."""
    cuts, how = set(), []
    if a.cuts:
        cuts |= set(load_cut_frames(a.cuts))
        how.append("file")
    if a.cut_frames:
        cuts |= set(parse_frames(a.cut_frames, "--cut-frames"))
        how.append("list")
    if not getattr(a, "no_detect_cuts", False) and video and Path(str(video)).is_file():
        import cuts as cutsmod
        cuts |= set(cutsmod.detect(video, ffmpeg)["reset_frames"])
        how.append("cuts.py")
    return sorted(cuts), "+".join(how) or "none"


def _audio_arg(v, what):
    """--audio: True = the video's own audio, a path = that file (e.g. dialogue.wav for a video-only cut.mov)."""
    if v is None or v is True:
        return v
    if not Path(v).is_file():
        raise cl.ClipError("usage", f"{what} --audio not found: {v}", exit_code=2)
    return v


def _run():
    ap = _Parser(description="Face-tracked reframe with a stabilised virtual camera (ref 08).")
    sub = ap.add_subparsers(dest="cmd", parser_class=_Parser)
    p = sub.add_parser("detect")
    p.add_argument("video")
    p.add_argument("--out", required=True)
    _add_detect(p)
    p.add_argument("--ffmpeg")
    p = sub.add_parser("track")
    p.add_argument("det")
    p.add_argument("--out", required=True)
    _add_track(p)
    p.add_argument("--video", help="video for cuts.py and --subject speaker (default: det.json's video)")
    p.add_argument("--audio", help="the clip's audio for --subject speaker (dialogue.wav; default the video's)")
    p.add_argument("--size", default=SIZE, help="canvas WxH: decides whether a two-shot fits one crop")
    p.add_argument("--margin", type=float, default=MARGIN)
    p.add_argument("--ffmpeg")
    p = sub.add_parser("stabilize")
    p.add_argument("tracks")
    p.add_argument("--out", required=True)
    _add_stab(p)
    p = sub.add_parser("render")
    p.add_argument("video")
    p.add_argument("path")
    p.add_argument("--out", required=True)
    p.add_argument("--overlay", action="store_true")
    p.add_argument("--audio", nargs="?", const=True, help="mux audio: bare = the video's, or a file (dialogue.wav)")
    p.add_argument("--crf", type=int, default=18)
    p.add_argument("--ffmpeg")
    p = sub.add_parser("qc")
    p.add_argument("path")
    p.add_argument("--qc-dir", help="default: <path dir>/qc")
    p.add_argument("--video", help="the rendered preview: also measure the face motion the viewer sees")
    p.add_argument("--ffmpeg")
    p.add_argument("--no-plot", action="store_true")
    p = sub.add_parser("run")
    p.add_argument("video")
    p.add_argument("--workdir", required=True)
    _add_detect(p)
    _add_track(p)
    _add_stab(p)
    p.add_argument("--render", action="store_true")
    p.add_argument("--overlay", action="store_true")
    p.add_argument("--audio", nargs="?", const=True,
                   help="the clip's audio: a file (dialogue.wav: speaker detection + preview mux) or bare "
                        "(the video's own)")
    p.add_argument("--ffmpeg")
    p = sub.add_parser("selftest")
    p.add_argument("--workdir")
    a = ap.parse_args()
    if not a.cmd:
        ap.error("a subcommand is required: detect, track, stabilize, render, qc, run or selftest")

    if a.cmd == "selftest":
        res = selftest(a.workdir)
        cl.emit(res)
        return 0 if res["ok"] else 1
    if a.cmd == "qc":
        res = qc(cl.read_json(a.path), a.qc_dir or str(Path(a.path).resolve().parent / "qc"), not a.no_plot,
                 video=a.video, ffmpeg=cl.find_ffmpeg(a.ffmpeg) if a.video else None)
        for f in res["findings"]:
            cl.log(f"{f['rank']} {f['id']}: {f['measured']}")
        cl.emit(res)
        return 0 if res["ok"] else 1
    if a.cmd == "stabilize":
        tr = cl.read_json(a.tracks)
        if tr.get("kind") != "face_tracks":
            raise cl.ClipError("bad_input", f"{a.tracks} is not a track output", exit_code=2)
        res = stabilize(tr, out=a.out, det_scale=_det_scale(tr), **_stab_kwargs(a))
        cl.emit(summary(res))
        return 0
    ffmpeg = cl.find_ffmpeg(getattr(a, "ffmpeg", None))
    if a.cmd == "detect":
        res = detect(a.video, ffmpeg, a.out, a.every, a.max_width, a.min_face, a.score, a.model, a.max_frames, a.force)
        cl.emit(summary(res))
        return 0
    if a.cmd == "track":
        det = cl.read_json(a.det)
        if det.get("kind") != "face_detections":
            raise cl.ClipError("bad_input", f"{a.det} is not a detect output", exit_code=2)
        parse_size(a.size)
        video = a.video or det.get("video")
        cutf, how = _cut_list(a, video, ffmpeg)
        res = track(det, cutf, parse_frames(a.jump_cuts, "--jump-cuts"), a.subject, a.hold, video, ffmpeg, None,
                    size=a.size, margin=a.margin, audio=_audio_arg(a.audio, "track"), cuts_from=how)
        res["det_scale"] = det.get("scale")
        cl.write_json_atomic(a.out, res)
        cl.emit(summary(res))
        return 0
    if a.cmd == "render":
        res = render(a.video, cl.read_json(a.path), a.out, ffmpeg, a.overlay, _audio_arg(a.audio, "render"), a.crf)
        cl.emit(res)
        return 0 if res["ok"] else 1
    # run
    kw = _stab_kwargs(a)
    parse_size(a.size)
    aud = _audio_arg(a.audio, "run")
    wd = Path(a.workdir)
    wd.mkdir(parents=True, exist_ok=True)
    det = detect(a.video, ffmpeg, wd / "det.json", a.every, a.max_width, a.min_face, a.score, a.model,
                 a.max_frames, a.force)
    cutf, how = _cut_list(a, a.video, ffmpeg)
    tr = track(det, cutf, parse_frames(a.jump_cuts, "--jump-cuts"), a.subject, a.hold, a.video, ffmpeg, None,
               size=a.size, margin=a.margin, audio=aud if isinstance(aud, str) else None, cuts_from=how)
    tr["det_scale"] = det.get("scale")
    cl.write_json_atomic(wd / "tracks.json", tr)
    path = stabilize(tr, out=wd / "path.json", det_scale=det.get("scale"), **kw)
    q = qc(path, wd / "qc")
    out = {"ok": q["ok"], "version": SCRIPT_VERSION, "kind": "face_track_run", "workdir": str(wd),
           "files": {"det": str(wd / "det.json"), "tracks": str(wd / "tracks.json"), "path": str(wd / "path.json"),
                     **q["files"]},
           "detect": {k: det[k] for k in ("frames", "frames_with_face", "detector_frames", "cached", "det_size")},
           "cuts": cutf, "cuts_from": how, "segments": path["segments"], "qc": q["metrics"],
           "findings": q["findings"], "warnings": det.get("warnings", []) + tr["warnings"] + path["warnings"]}
    if a.render:
        r = render(a.video, path, wd / "preview.mp4", ffmpeg, a.overlay, aud)
        out["render"] = r
        out["files"]["preview"] = r["out"]
        if not a.overlay:   # the overlay boxes would be measured as motion
            q = qc(path, wd / "qc", video=r["out"], ffmpeg=ffmpeg)
            out["qc"], out["findings"] = q["metrics"], q["findings"]
        out["ok"] = q["ok"] and r["ok"]
    cl.emit(out)
    return 0 if out["ok"] else 1


def _det_scale(tr):
    return tr.get("det_scale") or 1.0


if __name__ == "__main__":
    cl.run_main(main)
