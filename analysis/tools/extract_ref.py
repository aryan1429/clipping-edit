"""Extract analysis material from a reference short: metadata, cut times, frame grid, transcript.
usage: python -I extract_ref.py <video.mp4> <outdir>"""
import sys, os, json, subprocess, cv2, numpy as np
import imageio_ffmpeg
src, out = sys.argv[1], sys.argv[2]
os.makedirs(out + "/frames", exist_ok=True)
cap = cv2.VideoCapture(src)
fps = cap.get(cv2.CAP_PROP_FPS); n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
w, h = int(cap.get(3)), int(cap.get(4))
prev = None; cuts = []; stats = []; i = 0
while True:
    ok, f = cap.read()
    if not ok: break
    small = cv2.resize(f, (90, 160))
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [16, 8], [0, 180, 0, 256]); cv2.normalize(hist, hist)
    if prev is not None and cv2.compareHist(prev, hist, cv2.HISTCMP_BHATTACHARYYA) > 0.45:
        cuts.append(round(i / fps, 2))
    prev = hist
    if i % int(round(fps / 2)) == 0:  # stats every 0.5 s
        stats.append(dict(t=round(i / fps, 2), luma=float(hsv[..., 2].mean()), sat=float(hsv[..., 1].mean()),
                          sharp=float(cv2.Laplacian(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var())))
    if i % int(round(fps)) == 0:  # frame every 1 s
        cv2.imwrite(f"{out}/frames/t{i/fps:05.1f}.jpg", cv2.resize(f, (w * 720 // h, 720)))
    i += 1
dur = i / fps
pcm = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-loglevel", "error", "-i", src, "-ac", "1", "-ar", "16000", "-f", "s16le", "-"], check=True, capture_output=True).stdout
audio = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768
from faster_whisper import WhisperModel
try: m = WhisperModel("small", device="cuda", compute_type="int8_float16")
except Exception: m = WhisperModel("small", device="cpu", compute_type="int8")
segs, info = m.transcribe(audio, word_timestamps=True)
words = [dict(w=x.word, s=round(x.start, 2), e=round(x.end, 2)) for s in segs for x in s.words]
json.dump(dict(src=src, fps=fps, frames=i, dur=round(dur, 2), w=w, h=h, cuts=cuts,
               shot_lengths=[round(b - a, 2) for a, b in zip([0] + cuts, cuts + [dur])],
               stats=stats, lang=info.language, words=words), open(out + "/analysis.json", "w"), indent=1)
print(src, f"{w}x{h} {fps:.2f}fps {dur:.1f}s cuts={len(cuts)} words={len(words)} lang={info.language}")
