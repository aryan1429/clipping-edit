"""Find a clip's wide-shot span (faces much smaller than the clip's median) on the caption canvas and write a punch-in
`zooms` entry into clips_final.json. usage: wide_zoom.py NN SCALE [min_frames]"""
import json, statistics as st, sys
from pathlib import Path

JOB = Path(__file__).resolve().parents[1]
nn, scale = int(sys.argv[1]), float(sys.argv[2])
min_len = int(sys.argv[3]) if len(sys.argv) > 3 else 60
boxes = [b for b in json.load(open(JOB / 'clips' / f'{nn:02d}' / 'faces_canvas.json'))['boxes'] if len(b) == 5]
med = st.median(b[3] - b[1] for b in boxes)
small = sorted(b[0] for b in boxes if (b[3] - b[1]) < 0.55 * med)
runs = []
for f in small:
    if runs and f - runs[-1][1] <= 3:
        runs[-1][1] = f
    else:
        runs.append([f, f])
runs = [r for r in runs if r[1] - r[0] + 1 >= min_len]
cfg = json.load(open(JOB / 'clips_final.json', encoding='utf8'))
clips = cfg if isinstance(cfg, list) else cfg['clips']
c = clips[nn - 1]
# snap each run to the shot's real cut frames (face detection lags a frame or two after a cut)
sp = json.load(open(JOB / 'clips' / f'{nn:02d}' / 'stab' / 'path.json'))
cuts = sorted(set(sp.get('resets', []) + sp.get('cuts', [])))
nfr = sp.get('frames') or (max(b[0] for b in boxes) + 1)
def snap(f, before):
    near = [c for c in cuts if (0 <= f - c <= 6 if before else 0 <= c - f - 1 <= 6)]
    return (max(near) if before else min(near) - 1) if near else f
runs = [[snap(f0, True), snap(f1, False)] for f0, f1 in runs]
zooms = []
for f0, f1 in runs:
    seg = [b for b in boxes if f0 <= b[0] <= f1]
    zooms.append({'f0': f0, 'f1': f1, 'scale': scale, 'cx': round(st.median((b[1] + b[3]) / 2 for b in seg)),
                  'cy': round(st.median((b[2] + b[4]) / 2 for b in seg))})
c['zooms'] = zooms
json.dump(cfg, open(JOB / 'clips_final.json', 'w', encoding='utf8'), indent=1, ensure_ascii=False)
print('median face w', round(med), 'zooms', zooms)
