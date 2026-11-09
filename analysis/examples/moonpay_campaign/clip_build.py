"""clip_build.py - MoonPay clip pipeline: skill scripts (cut, splice, face track, captions, mix, mux) + Topaz + After Effects.

usage: py -P clip_build.py <stage> NN      stages: prep topaz overlay ae render audio final qc all
       clips_final.json (job root) holds the picked clips (rank = NN, source_id, word ids, title, captions...).
Canvas 1080x1920 @ 60000/1001. Native-fps cut + face track -> Topaz (Proteus up + Apollo interpolation to 59.94)
-> AE comp (footage, punch-in accents, Premium Glow CC adjustment layer, caption overlay, title) -> H.264 40 Mbps
-> finalize_mux with the dialogue + SFX mix.
"""
import json, os, sys, subprocess, math, shutil, re, glob, time
from fractions import Fraction
from pathlib import Path

JOB = Path(os.environ.get('CLIP_JOB', '.'))
SK = Path(os.environ.get('CLIP_SKILL_SCRIPTS', str(Path(__file__).resolve().parents[3] / 'skill' / 'scripts')))
PY = sys.executable
FFD = os.environ.get('CLIP_FFMPEG_DIR', '')   # folder holding ffmpeg + ffprobe
FF, FP = (f'{FFD}/ffmpeg.exe', f'{FFD}/ffprobe.exe') if FFD else ('ffmpeg', 'ffprobe')
TV = os.environ.get('TOPAZ_FFMPEG', 'C:/Program Files/Topaz Labs LLC/Topaz Video AI/ffmpeg.exe')
TVMD = r'C:\ProgramData\Topaz Labs LLC\Topaz Video AI\models'
PRESET = os.environ.get('CLIP_AE_PRESET', '')   # the colour-correction preset .ffx (ref 09 section 5)
FONT = 'C:/WINDOWS/Fonts/Montserrat-Black.ttf'
FONT_TITLE = 'C:/WINDOWS/Fonts/Montserrat-ExtraBold.ttf'
OUT_FPS = Fraction(60000, 1001)
W, H = 1080, 1920
DELIVER = Path(os.environ.get('CLIP_DELIVER', 'edited'))
ENV = dict(os.environ, PYTHONIOENCODING='utf8', TVAI_MODEL_DATA_DIR=TVMD, TVAI_MODEL_DIR=TVMD)

BANNER_SRC_PX = {'AddKLpRp3a8': 92}   # CNBC "Sponsored and Programmed by" bar at the top of the source frame
TITLE_TOP = 190                        # title box top on the canvas (9:16 top UI band ends ~168)
PURPLE, YELLOW, GREEN = '#9D5CFF', '#FFD84D', '#4DFF9A'
PRODUCT_WORDS = {'MOONPAY', "MOONPAY'S", 'PAYBOX', 'ONRAMP', 'OFFRAMP', 'ONRAMPS', 'OFFRAMPS', 'MOONAGENTS', 'ON-RAMP', 'OFF-RAMP', 'OWS', 'COMMERCE', 'AGENTS',
                 'ENTERPRISE', 'INSTITUTIONAL', 'TRADE'}
KEY_WORDS = {'AI', 'AGENT', 'AGENTS', 'CRYPTO', 'STABLECOINS', 'STABLECOIN', 'MONEY', 'INTERNET', 'SOFTWARE', 'WALLET',
             'WALLETS', 'PAYMENTS', 'PAYMENT', 'FIAT', 'BANKS', 'SECONDS', 'TRILLIONS', 'BILLION', 'MILLION', 'MILLIONS',
             'GLOBALLY', 'INSTANTLY', 'FUTURE', 'OPERATING', 'SYSTEM', 'CHECKOUT', 'MERCHANTS', 'TOKENIZATION', 'ONCHAIN',
             'ON-CHAIN', 'BLOCKCHAIN', 'DOLLARS', 'FREE', 'OPEN', 'COUNTRIES', 'CUSTOMERS'}


def run(cmd, check=True, **kw):
    print('$', ' '.join(str(c) for c in cmd)[:400], flush=True)
    r = subprocess.run([str(c) for c in cmd], env=ENV, text=True, capture_output=True, encoding='utf8', errors='replace', **kw)
    if r.stdout: print(r.stdout[-4000:])
    if r.returncode and r.stderr: print(r.stderr[-4000:])
    if check and r.returncode:
        raise SystemExit(f'FAILED rc={r.returncode}: {cmd[:3]}')
    return r


def clip_cfg(nn):
    cl = json.load(open(JOB / 'clips_final.json', encoding='utf8'))
    for c in cl['clips']:
        if int(c['rank']) == int(nn):
            return c
    raise SystemExit(f'no clip {nn}')


def cdir(nn):
    d = JOB / 'clips' / f'{int(nn):02d}'
    d.mkdir(parents=True, exist_ok=True)
    return d


def native_fps(sid):
    return Fraction(json.load(open(JOB / 'facts' / f'{sid}.json'))['canvas_fps'])


def nframes(path):
    r = run([FP, '-v', 'error', '-count_packets', '-select_streams', 'v:0', '-show_entries', 'stream=nb_read_packets,width,height,r_frame_rate',
             '-of', 'json', path])
    s = json.loads(r.stdout)['streams'][0]
    return int(s['nb_read_packets']), int(s['width']), int(s['height']), Fraction(s['r_frame_rate'])


# ------------------------------------------------------------------ prep: cut list, splice, face track, reframe render
def prep(nn):
    c, d = clip_cfg(nn), cdir(nn)
    sid = c['source_id']
    src = JOB / 'src' / f'{sid}.mp4'
    tr = JOB / 'asr' / sid / 'transcript.json'
    if c.get('asr_fix'):
        # word-timing corrections before cutting: ASR ends some words early, so a cut placed at the ASR word end left an
        # audible fragment of a removed brand name ("...pal") - review 2026-11-09. {word_id: {"start"?: s, "end"?: s}}
        a = json.load(open(tr, encoding='utf8'))
        for w in (a['words'] if isinstance(a, dict) else a):
            for k, v in c['asr_fix'].get(w['id'], {}).items():
                w[k] = v
        tr = d / 'transcript_fixed.json'
        json.dump(a, open(tr, 'w', encoding='utf8'), ensure_ascii=False)
    one = {'clips': [{k: c[k] for k in ('rank', 'start_word', 'end_word', 'remove_words', 'hook_line', 'payoff_line') if k in c}]}
    one['clips'][0].pop('hook_line', None); one['clips'][0].pop('payoff_line', None)
    json.dump(one, open(d / 'clip_one.json', 'w'), indent=1)
    run([PY, '-P', SK / 'cutlist.py', '--transcript', tr, '--clips', d / 'clip_one.json', '--rank', c['rank'],
         '--facts', JOB / 'facts' / f'{sid}.json', '--out', d / 'cutlist.json', '--source', src, '--max-len', '49.5',
         '--ffmpeg', FF, '--ffprobe', FP])
    run([PY, '-P', SK / 'splice.py', '--cutlist', d / 'cutlist.json', '--source', src, '--facts', JOB / 'facts' / f'{sid}.json',
         '--outdir', d, '--crf', '10', '--ffmpeg', FF, '--ffprobe', FP])
    track(nn)


def track(nn):
    c, d = clip_cfg(nn), cdir(nn)
    sid = c['source_id']
    cut = json.load(open(d / 'cutlist.json'))
    joins = [s['out_frame'] for s in cut['segments'][1:]]
    four_k = json.load(open(JOB / 'facts' / f'{sid}.json'))['video']['height'] >= 2000
    # v2: crop at the source's native scale (no upscale in the crop: Topaz does the 2x), rendered near-lossless
    size = '1080x1920' if four_k else '608x1080'
    upmax = c.get('max_upscale', 1.0)
    args = [PY, '-P', SK / 'face_track.py', 'run', d / 'cut.mov', '--workdir', d / 'face', '--size', size,
            '--audio', d / 'dialogue.wav', '--subject', c.get('subject', 'auto'), '--mode', c.get('cam_mode', 'smooth'),
            '--face-h', str(c.get('face_h', 0.17)), '--eyes-y', str(c.get('eyes_y', 0.40)), '--max-upscale', str(upmax)]
    # a join that removed > 1.5 s of source can land on another camera angle: hard cut (reset), else a jump cut
    segs = cut['segments']
    hard = [s['out_frame'] for p, s in zip(segs, segs[1:]) if s['src_in_s'] - p['src_out_s'] > 1.5 or c.get('hard_joins')]
    jump = [j for j in joins if j not in hard]
    if jump:
        args += ['--jump-cuts', ','.join(map(str, jump))]
    if hard:
        args += ['--cut-frames', ','.join(map(str, hard))]
    r = run(args, check=False)
    print('face_track rc', r.returncode)
    (d / 'face' / 'ft_rc.txt').write_text(str(r.returncode))
    run([PY, '-P', SK / 'face_track.py', 'render', d / 'cut.mov', d / 'face' / 'path.json', '--out', d / 'reframe.mp4', '--crf', '4'])


# ------------------------------------------------------------------ topaz: enhance + interpolate to 59.94, then de-blend cuts
def topaz(nn):
    wait_ram()
    c, d = clip_cfg(nn), cdir(nn)
    fps_in = native_fps(c['source_id'])
    n_in, w, h, _ = nframes(d / 'reframe.mp4')
    if w >= 1000 and fps_in == OUT_FPS:
        # 4K60 source: the native crop is 1080x1920 already (a 1:1 crop of the 4K frame) - no AI upscale needed
        shutil.copy(d / 'reframe.mp4', d / 'topaz.mp4')
        json.dump({'n_in': n_in, 'n_out': n_in, 'ratio': '1', 'fix': {}, 'topaz': 'skipped (4K60 native crop)'}, open(d / 'topaz_fix.json', 'w'))
        print('topaz skipped: 4K60 native crop', n_in)
        return
    # Gaia HQ (ghq-5) won the A/B on compressed 1080p YouTube faces (Proteus / Artemis smear skin into wax)
    flt = f'tvai_up=model=ghq-5:scale=2:device=0:vram=1:instances=1'
    if fps_in != OUT_FPS:
        flt += f',tvai_fi=model=apo-8:fps={OUT_FPS.numerator}/{OUT_FPS.denominator}:device=0:vram=1:instances=1'
    flt += f',scale={W}:{H}:flags=lanczos,setsar=1'
    raw = d / 'topaz_raw.mp4'
    run([TV, '-hide_banner', '-v', 'error', '-y', '-i', d / 'reframe.mp4', '-vf', flt, '-an', '-c:v', 'h264_nvenc',
         '-preset', 'p7', '-tune', 'hq', '-rc', 'vbr', '-cq', '11', '-b:v', '0', '-maxrate', '150M', '-bufsize', '240M',
         '-profile:v', 'high', '-pix_fmt', 'yuv420p', '-g', '60', '-bf', '0', '-r', f'{OUT_FPS.numerator}/{OUT_FPS.denominator}', raw])
    # target frame count on the 59.94 grid
    n_out = round(n_in * OUT_FPS / fps_in)
    ratio = OUT_FPS / fps_in
    path = json.load(open(d / 'face' / 'path.json'))
    resets = sorted(set(path.get('resets', [])))
    fix = {}
    if ratio != 1:
        for cidx in resets:  # cut between native frames cidx-1 and cidx
            j0 = math.floor((cidx - 1) * ratio)  # last output frame at/ before native cidx-1
            j1 = math.ceil(cidx * ratio)          # first output frame at/after native cidx
            for j in range(j0 + 1, j1):
                pos = j / ratio
                fix[j] = j0 if pos - (cidx - 1) < 0.5 else j1
    json.dump({'n_in': n_in, 'n_out': n_out, 'ratio': str(ratio), 'fix': fix}, open(d / 'topaz_fix.json', 'w'))
    # rewrite with exact frame count + de-blended cut frames (lossless-ish x264 crf 10 intermediate)
    import cv2, numpy as np
    cap = cv2.VideoCapture(str(raw))
    frames_src = []
    out = d / 'topaz.mp4'
    p = subprocess.Popen([FF, '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{W}x{H}', '-r',
                          f'{OUT_FPS.numerator}/{OUT_FPS.denominator}', '-i', '-', '-c:v', 'libx264', '-preset', 'medium', '-crf', '10',
                          '-pix_fmt', 'yuv420p', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709',
                          '-g', '60', '-bf', '0', str(out)], stdin=subprocess.PIPE)
    need_back = {v for v in fix.values()}
    cache, buf, last = {}, [], None
    # we need frames possibly ahead (j1): read all frames index-wise with a small lookahead window
    frames = []
    ok = True
    i = 0
    window = {}
    nread = 0
    def get(k):
        nonlocal nread, last
        while nread <= k:
            ok, fr = cap.read()
            if not ok:
                fr = last
            window[nread] = fr; last = fr; nread += 1
            for kk in [x for x in window if x < nread - 16]:
                del window[kk]
        return window[k]
    for j in range(n_out):
        fr = get(fix.get(j, j)) if fix.get(j, j) >= j - 15 else get(j)
        p.stdin.write(np.ascontiguousarray(fr).tobytes())
    p.stdin.close(); p.wait()
    cap.release()
    print('topaz done', n_in, '->', n_out, 'fixed', len(fix))
    raw.unlink()


# ------------------------------------------------------------------ stab: face tracking + stabilising keys for the AE footage layer
def stab(nn):
    c, d = clip_cfg(nn), cdir(nn)
    fix = json.load(open(d / 'topaz_fix.json'))
    p1 = json.load(open(d / 'face' / 'path.json'))
    ratio = Fraction(fix['ratio'])
    resets = sorted({int(math.ceil(r * ratio)) for r in p1.get('resets', [])})
    for mode in (c.get('stab_mode', 'steady'), 'smooth'):
        args = [PY, '-P', SK / 'face_track.py', 'run', d / 'topaz.mp4', '--workdir', d / 'stab', '--size', f'{W}x{H}',
                '--mode', mode, '--face-h', '0.6', '--max-upscale', str(c.get('stab_room', 1.05)), '--eyes-y', str(c.get('eyes_y', 0.40)),
                '--subject', c.get('subject', 'auto')]
        if resets:
            args += ['--cut-frames', ','.join(map(str, resets))]
        r = run(args, check=False)
        q = json.load(open(d / 'stab' / 'qc' / 'face_track_qc.json')) if (d / 'stab' / 'qc' / 'face_track_qc.json').exists() else {}
        bad = [f['id'] for f in q.get('findings', []) if f['rank'] == 'P0' and f['id'] not in ('face_height', 'eyes_y')]
        print('stab', mode, 'rc', r.returncode, 'P0 (excl. framing medians):', bad)
        if not bad:
            break
    json.dump({'mode': mode, 'p0': bad}, open(d / 'stab' / 'stab_mode.json', 'w'))


# ------------------------------------------------------------------ overlay: caption tokens -> captions.py -> transparent mov; title PNG
def tokens_for(c, cut, n_out):
    words = cut['words']
    toks = []
    fixes = c.get('caption_fix', {})
    for w in words:
        t = fixes.get(w['id'], w['text']).strip()
        if not t:
            continue
        if t.startswith('-') and toks:  # ASR split "on -ramp" / "tap -to -pay" -> one token
            prev = toks[-1]
            prev['d'] = prev['d'] + re.sub(r'[.,!?;:"]+$', '', t).upper()
            prev['src'].append(w['id'])
            if re.search(r'[.!?]$', t):
                prev['brk'] = True
            continue
        d = re.sub(r'[.,!?;:"]+$', '', t).strip('"').upper()
        d = re.sub(r'^[",]+', '', d)
        if not d:
            continue
        core = re.sub(r'[^A-Z0-9$%\'-]', '', d)
        col = None
        if core in PRODUCT_WORDS or core.startswith('MOONPAY'):
            col = PURPLE
        elif re.search(r'\d', core) or core in ('BILLION', 'MILLION', 'TRILLIONS', 'MILLIONS'):
            col = YELLOW
        elif core in KEY_WORDS:
            col = GREEN
        tk = {'d': d, 'src': [w['id']]}
        if w['id'] in c.get('brk_after', ()):  # end a chunk after this word (keeps a late word out of a dying chunk)
            tk['brk'] = True
        if w['id'] in c.get('solo_words', ()):  # a word that must stand alone (fits the gap above a close-up face)
            tk['solo'] = True
        if col:
            tk['c'] = col
        if re.search(r'[.!?]$', t):
            tk['brk'] = True
        toks.append(tk)
    # a number and its unit are one token ("$10" + "BILLION" split across chunks read as ten dollars - review 2026-11-09)
    units = {'BILLION', 'BILLIONS', 'MILLION', 'MILLIONS', 'TRILLION', 'TRILLIONS', 'THOUSAND', 'PERCENT', 'X'}
    glued = []
    for tk in toks:
        prev = glued[-1] if glued else None
        if prev and re.search(r'\d', prev['d']) and tk['d'] in units and not prev.get('brk'):
            prev['d'] += ' ' + tk['d']; prev['src'] += tk['src']
            prev['c'] = prev.get('c') or tk.get('c') or YELLOW
            if tk.get('brk'):
                prev['brk'] = True
            continue
        glued.append(tk)
    toks[:] = glued
    chunk_tokens(toks, {w['id']: w for w in words}, c.get('max_words', 4))
    return {'fps': f'{OUT_FPS.numerator}/{OUT_FPS.denominator}', 'frames': n_out,
            'words': [{'id': w['id'], 'start': w['start'], 'end': w['end']} for w in words], 'tokens': toks}


def chunk_tokens(toks, wmap, maxw=4):
    """ref 01 chunks: 2-4 words, break at sentence/comma punctuation or a gap > 0.25 s, balanced sizes, no 1-word orphans."""
    phrases, cur = [], []
    for i, t in enumerate(toks):
        if t.get('solo') and cur:
            phrases.append(cur); cur = []
        cur.append(t)
        end = wmap[t['src'][-1]]['end']
        nxt = toks[i + 1] if i + 1 < len(toks) else None
        gap = (wmap[nxt['src'][0]]['start'] - end) if nxt else 9
        raw = wmap[t['src'][-1]]['text'].strip()
        if t.get('brk') or t.get('solo') or (nxt and nxt.get('solo')) or raw[-1:] in ',;:' or gap > 0.25 or nxt is None:
            phrases.append(cur); cur = []
    # merge a 1-word phrase into a neighbour when that keeps <= maxw words
    merged = []
    for ph in phrases:
        if merged and (len(ph) == 1 or len(merged[-1]) == 1) and len(merged[-1]) + len(ph) <= maxw                 and not merged[-1][-1].get('brk') and not any(t.get('solo') for t in merged[-1] + ph):
            merged[-1] = merged[-1] + ph
        else:
            merged.append(ph)
    for t in toks:
        t.pop('brk', None)
    for ph in merged:
        for t in ph:
            t.pop('solo', None)
        n = len(ph)
        k = -(-n // maxw)
        sizes = [n // k + (1 if j < n % k else 0) for j in range(k)]
        i = 0
        for sz in sizes:
            i += sz
            ph[i - 1]['brk'] = True


def title_png(text, hl, out):
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    maxw = 900
    size = 70
    while True:
        f = ImageFont.truetype(FONT_TITLE, size)
        words = text.split()
        lines, cur = [], ''
        for w in words:
            t = (cur + ' ' + w).strip()
            if f.getlength(t) <= maxw:
                cur = t
            else:
                lines.append(cur); cur = w
        lines.append(cur)
        if len(lines) <= 2 or size <= 48:
            break
        size -= 4
    lh = int(size * 1.18)
    padx, pady = 34, 22
    widths = [f.getlength(l) for l in lines]
    bw = int(max(widths) + 2 * padx)
    bh = int(lh * len(lines) + 2 * pady - (lh - size * 1.0) * 0.6)
    img = Image.new('RGBA', (W, 520), (0, 0, 0, 0))
    x0 = (W - bw) // 2; y0 = 40
    sh = Image.new('RGBA', img.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle([x0 + 4, y0 + 10, x0 + bw + 4, y0 + bh + 10], radius=26, fill=(0, 0, 0, 110))
    sh = sh.filter(ImageFilter.GaussianBlur(14))
    img = Image.alpha_composite(img, sh)
    dr = ImageDraw.Draw(img)
    dr.rounded_rectangle([x0, y0, x0 + bw, y0 + bh], radius=26, fill=(255, 255, 255, 255))
    hlw = set(x.upper() for x in hl)
    for i, l in enumerate(lines):
        x = (W - widths[i]) / 2
        y = y0 + pady + i * lh
        for wi, w in enumerate(l.split(' ')):
            core = re.sub(r"[^A-Za-z0-9'?]", '', w).upper().rstrip('?')
            col = (124, 34, 255, 255) if (core in hlw or core.rstrip("'S") in hlw) else (12, 12, 16, 255)
            dr.text((x, y), w, font=f, fill=col)
            x += f.getlength(w + ' ')
    bbox = (x0, y0, x0 + bw, y0 + bh)
    img.save(out)
    return {'png': str(out), 'box': bbox, 'size': size, 'lines': lines}


def framing(c, d, n_out, tbox):
    """face anchor, head-room drop, banner mask and per-frame face boxes on the final canvas (after the drop)."""
    import statistics
    p1 = json.load(open(d / 'face' / 'path.json'))          # stage 1: source -> native crop (= topaz frame)
    banner = 0.0
    bsrc = BANNER_SRC_PX.get(c['source_id'], 0)
    for i in range(len(p1['frames_data']['cy'])):
        f1 = p1['frames_data']; y0 = f1['cy'][i] - f1['ch'][i] / 2
        if bsrc and y0 < bsrc:
            banner = max(banner, (bsrc - y0) * H / f1['ch'][i])
    path = json.load(open(d / 'stab' / 'path.json'))         # stage 2: AE face stabilisation on the topaz frame
    fd = path['frames_data']
    fbc = path.get('face', {}).get('fused_box') or [[], [], [], []]   # column-wise: [x[], y[], w[], h[]]
    fx = [None if fbc[0][i] is None else (fbc[0][i], fbc[1][i], fbc[2][i], fbc[3][i]) for i in range(len(fbc[0]))]
    xs, ys, tops, boxes = [], [], [], []
    for i, b in enumerate(fx):
        x0 = fd['cx'][i] - fd['cw'][i] / 2; y0 = fd['cy'][i] - fd['ch'][i] / 2
        sx, sy = W / fd['cw'][i], H / fd['ch'][i]
        if b:
            cb = [(b[0] - x0) * sx, (b[1] - y0) * sy, (b[0] + b[2] - x0) * sx, (b[1] + b[3] - y0) * sy]
            if -50 < cb[1] < H * 0.8:
                tops.append(cb[1]); xs.append((cb[0] + cb[2]) / 2); ys.append((cb[1] + cb[3]) / 2)
            boxes.append([i] + cb)
        else:
            boxes.append([i, None])
    tops.sort()
    p10 = tops[len(tops) // 10] if tops else 600
    ax, ay = (statistics.median(xs), statistics.median(ys)) if xs else (W / 2, H * 0.42)
    title_bot = TITLE_TOP + (tbox[3] - tbox[1])
    drop = int(min(c.get('drop_max', 420), max(0, title_bot + 120 - p10)))
    feather = 70
    mask_top = int(banner + feather / 2 + 6) if banner > 0 else (int(feather / 2) if drop > 0 else 0)
    # boxes after the drop, grown 9 % about the anchor (push + punch-ins), head-room above the box for hair
    g = 1.04   # push-in growth at the face; captions only need to clear eyes-to-chin (captions.py adds face_pad)
    out_boxes = []
    for bx in boxes:
        if bx[1] is None:
            out_boxes.append([bx[0], None]); continue
        _, x0, y0, x1, y1 = bx
        q = [ax + (x0 - ax) * g, ay + (y0 - ay) * g + drop, ax + (x1 - ax) * g, ay + (y1 - ay) * g + drop]
        out_boxes.append([bx[0]] + [round(v, 1) for v in q])
    # freeze-frames (AE holds frame src over f0..f1, e.g. to hide a branded audience cutaway): the face sits where it was
    # on frame src, grown 7 % for the slow push-in on the frozen frame
    byf = {b[0]: b for b in out_boxes}
    for fz in c.get('freezes', []):
        sb = byf.get(fz['src'])
        if not sb or sb[1] is None:
            raise SystemExit(f"freeze src frame {fz['src']} has no face box")
        cx, cy, hw, hh = (sb[1] + sb[3]) / 2, (sb[2] + sb[4]) / 2, (sb[3] - sb[1]) / 2 * 1.07, (sb[4] - sb[2]) / 2 * 1.07
        for i, b in enumerate(out_boxes):
            if fz['f0'] <= b[0] <= fz['f1']:
                out_boxes[i] = [b[0], round(cx - hw, 1), round(cy - hh, 1), round(cx + hw, 1), round(cy + hh, 1)]
    # punch-ins on wide stage shots (AE ZOOM null, a cut in/out at the shot's edges): scale the face boxes the same way
    for zm in c.get('zooms', []):
        k, zx, zy = zm['scale'] / 100.0, zm['cx'], zm['cy']
        for i, b in enumerate(out_boxes):
            if b[1] is not None and zm['f0'] <= b[0] <= zm['f1']:
                out_boxes[i] = [b[0], round(zx + (b[1] - zx) * k, 1), round(zy + (b[2] - zy) * k, 1),
                                round(zx + (b[3] - zx) * k, 1), round(zy + (b[4] - zy) * k, 1)]
    fr = {'anchor': [round(ax, 1), round(ay, 1)], 'drop': drop, 'mask_top': mask_top, 'feather': feather,
          'face_top_p10': round(p10, 1), 'banner_px': round(banner, 1)}
    json.dump(fr, open(d / 'framing.json', 'w'), indent=1)
    json.dump({'fps': path.get('fps') or str(native_fps(c['source_id'])), 'boxes': out_boxes}, open(d / 'faces_canvas.json', 'w'))
    return fr


def overlay(nn):
    c, d = clip_cfg(nn), cdir(nn)
    cut = json.load(open(d / 'cutlist.json'))
    fix = json.load(open(d / 'topaz_fix.json'))
    n_out = fix['n_out']
    t = title_png(c['title_onscreen'], c.get('title_highlight', []), d / 'title.png')
    json.dump(t, open(d / 'title.json', 'w'))
    fr = framing(c, d, n_out, t['box'])
    print('framing', fr)
    tk = tokens_for(c, cut, n_out)
    json.dump(tk, open(d / 'tokens.json', 'w', encoding='utf8'), indent=0, ensure_ascii=False)
    # captions stay below the title block and inside the 9:16 UI-safe band; faces = final canvas boxes (after the drop)
    r = run([PY, '-P', SK / 'captions.py', '--tokens', d / 'tokens.json', '--canvas', f'{W}x{H}', '--fps',
             f'{OUT_FPS.numerator}/{OUT_FPS.denominator}', '--frames', n_out, '--faces', d / 'faces_canvas.json',
             '--font', FONT, '--ass', d / 'captions.ass', '--layout', d / 'captions_layout.json',
             '--safe', f'65,{TITLE_TOP + (t["box"][3] - t["box"][1]) + 60},950,{c.get("safe_bottom", 1330)}', '--cap-frac', str(c.get('cap_frac', 0.030))] + (['--max-words', str(c['max_words'])] if c.get('max_words') else []), check=False)
    if r.returncode:
        print('captions.py rc', r.returncode)
        raise SystemExit(1)
    print('caption layout ok (AE builds the text layers from captions_layout.json)')


def ass_alpha(b, n_out, out):
    """libass draws no alpha: render the ASS on black and on white and solve a = 1 - (white - black)/255, C = black/a."""
    import numpy as np
    dur = (n_out + 2) / OUT_FPS
    def src(col):
        return subprocess.Popen([FF, '-v', 'error', '-f', 'lavfi', '-i',
                                 f'color=c={col}:s={W}x{H}:r={OUT_FPS.numerator}/{OUT_FPS.denominator}:d={float(dur):.6f},format=rgb24',
                                 '-vf', b['filter'] + ',format=rgb24', '-frames:v', str(n_out), '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
                                cwd=b['cwd'], stdout=subprocess.PIPE)
    pb, pw = src('black'), src('white')
    enc = subprocess.Popen([FF, '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgba', '-s', f'{W}x{H}', '-r',
                            f'{OUT_FPS.numerator}/{OUT_FPS.denominator}', '-i', '-', '-c:v', 'qtrle', str(out)], stdin=subprocess.PIPE)
    fs = W * H * 3
    n = 0
    while n < n_out:
        bb = pb.stdout.read(fs); ww = pw.stdout.read(fs)
        if len(bb) < fs or len(ww) < fs:
            break
        B = np.frombuffer(bb, np.uint8).reshape(H, W, 3).astype(np.float32)
        Wt = np.frombuffer(ww, np.uint8).reshape(H, W, 3).astype(np.float32)
        a = np.clip(1.0 - (Wt - B).mean(axis=2) / 255.0, 0, 1)
        C = np.where(a[..., None] > 1e-3, B / np.maximum(a[..., None], 1e-3), 0)
        o = np.dstack([np.clip(C, 0, 255), a * 255]).round().astype(np.uint8)
        enc.stdin.write(o.tobytes()); n += 1
    enc.stdin.close(); enc.wait(); pb.wait(); pw.wait()
    if n != n_out:
        raise SystemExit(f'caption overlay frames {n} != {n_out}')
    print('caption overlay', out, n, 'frames')


# ------------------------------------------------------------------ AE: plan -> build jsx -> aep + render queue
def accents(c, cut, n_out):
    """accent frames (59.94 grid): first mention of a product word / number, then every >= 6 s on key words."""
    words = cut['words']
    cand = []
    for w in words:
        core = re.sub(r'[^A-Za-z0-9$\'-]', '', w['text']).upper()
        pri = 2 if (core in PRODUCT_WORDS or core.startswith('MOONPAY')) else (1 if re.search(r'\d', core) else (0.5 if core in KEY_WORDS else 0))
        if pri:
            cand.append((w['start'], pri, core))
    out, last = [], -99
    for t, pri, core in sorted(cand, key=lambda x: (-x[1], x[0])):
        if all(abs(t - o) >= 5.5 for o in out) and t > 1.0 and t < float(n_out / OUT_FPS) - 2.0:
            out.append(t)
        if len(out) >= c.get('n_accents', 4):
            break
    return sorted(int(math.floor(t * OUT_FPS)) for t in out)


def ae(nn):
    c, d = clip_cfg(nn), cdir(nn)
    cut = json.load(open(d / 'cutlist.json'))
    fix = json.load(open(d / 'topaz_fix.json'))
    n_out = fix['n_out']
    acc = accents(c, cut, n_out)
    path = json.load(open(d / 'face' / 'path.json'))
    t = json.load(open(d / 'title.json'))
    fr = json.load(open(d / 'framing.json'))
    slug = c['slug']
    ax, ay = fr['anchor']; drop, mask_top, feather, p10 = fr['drop'], fr['mask_top'], fr['feather'], fr['face_top_p10']
    title_top = TITLE_TOP
    # scale keys: slow push 100 -> 100+push over the clip, punch-ins at the accents (ease 5 f in, hold, 12 f out)
    push, punch = c.get('push', 4.0), c.get('punch', 7.0)
    base = lambda f: 100 + push * f / max(1, n_out - 1)
    keys = {0: base(0), n_out - 1: base(n_out - 1)}
    resets60 = sorted(int(round(r * OUT_FPS / native_fps(c['source_id']))) for r in path.get('resets', []))
    def ss(x): return x * x * (3 - 2 * x)
    for a in acc:
        end_hold = a + 40
        nxt = [r for r in resets60 if r > a + 6]
        if nxt and nxt[0] < end_hold + 12:
            end_hold = max(a + 10, nxt[0] - 13)
        for k in range(0, 6):
            keys[a + k] = base(a + k) * (1 + punch / 100 * ss(k / 5))
        for k in range(0, 13):
            keys[end_hold + k] = base(end_hold + k) * (1 + punch / 100 * (1 - ss(k / 12)))
    scale_keys = [[f, round(v, 3)] for f, v in sorted(keys.items()) if 0 <= f < n_out]
    plan = {'name': f'MP{int(nn):02d} {slug}', 'fps': float(OUT_FPS), 'frames': n_out, 'W': W, 'H': H,
            'footage': (d / 'topaz.mp4').as_posix(), 'captions': (d / 'captions_alpha.mov').as_posix(),
            'title': (d / 'title.png').as_posix(), 'title_box': t['box'], 'preset': PRESET,
            'title_cy_png': (t['box'][1] + t['box'][3]) / 2, 'title_cy': title_top + (t['box'][3] - t['box'][1]) / 2,
            'drop': drop, 'mask_top': mask_top, 'feather': feather, 'face_top_p10': round(p10, 1), 'scale_keys': scale_keys,
            'anchor': [round(ax, 1), round(ay, 1)], 'accents': acc, 'push': push, 'punch': punch,
            'grade': dict(c.get('grade', {'lumetri': {'ADBE Lumetri-0020': 140}})),
            'aep': (d / f'MP{int(nn):02d}_{slug}.aep').as_posix(), 'out_video': (d / 'ae_video.mp4').as_posix()}
    # v2: everything in AE - stabilisation keys, caption words, title card
    sp = json.load(open(d / 'stab' / 'path.json'))
    ec = sp['effectcraft']
    assert len(ec['position']) == n_out, (len(ec['position']), n_out)
    plan['stab'] = {'anchor': ec['anchor'], 'position': [[round(x, 2), round(y, 2)] for x, y in ec['position']],
                    'scale': [round(v, 3) for v in ec['scale']]}
    plan['stab_mode'] = json.load(open(d / 'stab' / 'stab_mode.json'))['mode']
    lay = json.load(open(d / 'captions_layout.json', encoding='utf8'))
    words = []
    for ch in lay['chunks']:
        for wd in ch['words']:
            col = wd['color'].upper()
            words.append({'t': wd['text'], 'c': col, 'a': wd['appear_f'], 'f': wd['full_f'], 'e': wd['end_f'], 'ci': ch['i'],
                          'x': wd['baseline_center'][0], 'y': wd['baseline_center'][1], 'em': round(wd['em_px'] * wd.get('scale', 1.0), 3),
                          'kw': col != '#FFFFFF', 'inkw': wd['box_ink'][2] - wd['box_ink'][0]})
    plan['words'] = words
    plan['cap_font'] = lay['font']['postscript']
    plan['cap_ratio'] = lay['font']['cap_ratio']
    plan['stroke_em'] = lay['style']['bord_em']
    plan['shadow_alpha'] = lay['style']['shadow_alpha']
    plan['glow'] = c.get('glow', {'radius': 160, 'exposure': 0.25})
    # the preset's Sapphire sharpen, per source (review 2026-11-09, face Laplacian + 1:1 crops): Topaz-upscaled 1080p ->
    # 0.2 (0.5 turned AI texture into speckle); 4K-native -> 0.9 (0.5 under the preset's glow left skin waxy, 1.3 crunchy)
    plan['grade'].setdefault('sharpen_amp', 0.2 if 'topaz' not in fix else 0.9)
    plan['freezes'] = c.get('freezes', [])
    plan['zooms'] = c.get('zooms', [])
    # blurred band source: backdrop near the top of the frame (below any burned-in banner), beside the face - hands
    # gesturing at face height leaked into a face-height sample as orange ghosts (review 2026-11-09)
    plan['bg_y'] = c.get('bg_y', round(fr.get('banner_px', 0) + 150))
    # band colour: median of the backdrop rows at bg_y over the clip; the band is 75 % this flat colour over the blurred
    # footage, so a head or hand passing the sample point can only tint it faintly (review 2026-11-09)
    import cv2, numpy as np
    cap = cv2.VideoCapture(str(d / 'topaz.mp4')); nfr = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or n_out
    cols = []
    for fi in range(0, nfr, max(1, nfr // 24)):
        cap.set(cv2.CAP_PROP_POS_FRAMES, fi); ok, im = cap.read()
        if ok:
            y = min(im.shape[0] - 41, max(40, plan['bg_y']))
            cols.append(np.median(im[y - 40:y + 40].reshape(-1, 3), axis=0))
    cap.release()
    b, g, r = np.median(np.array(cols), axis=0) if cols else (40, 30, 60)
    plan['bg_color'] = c.get('bg_color', [round(float(r) / 255, 3), round(float(g) / 255, 3), round(float(b) / 255, 3)])
    text = chr(13).join(t['lines'])   # AE paragraph break
    hl, hlw = [], [x.upper() for x in c.get('title_highlight', [])]
    pos = 0
    for tok in re.split(r'(\s+)', text):
        core = re.sub(r"[^A-Za-z0-9']", '', tok).upper()
        if core and (core in hlw or core.replace("'S", '') in hlw):
            hl.append([pos, pos + len(tok.rstrip('?.,!'))])
        pos += len(tok)
    plan['title'] = {'text': text, 'font': 'Montserrat-ExtraBold', 'size': t['size'], 'hl': hl, 'hl_color': '#7C22FF',
                     'top': TITLE_TOP, 'pad_x': 34, 'pad_y': 22, 'bottom': TITLE_TOP + (t['box'][3] - t['box'][1])}
    json.dump(plan, open(d / 'ae_plan.json', 'w'), indent=1)
    jsx = d / 'build.jsx'
    jsx.write_text(f'var PLAN = {json.dumps(plan)};\n#include "{(JOB / "ae" / "build_clip2.jsx").as_posix()}"\n', encoding='utf8')
    r = run([PY, '-P', JOB / 'ae' / 'ae_run.py', 'run', jsx, '--timeout', '900', '--quiet', '600'], check=False)
    if 'BUILD_OK' not in (r.stdout or ''):
        raise SystemExit('AE build failed')


def free_ram_gb():
    r = subprocess.run(['powershell', '-NoProfile', '-c', '(Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory'],
                       capture_output=True, text=True)
    try:
        return int(r.stdout.strip()) / 1048576
    except ValueError:
        return 99


def wait_ram(need=3.5):
    """the user is on the laptop (Netflix): never start a heavy step below `need` GB free RAM"""
    import time
    while free_ram_gb() < need:
        print(f'waiting for RAM: {free_ram_gb():.1f} GB free', flush=True)
        time.sleep(30)


def render(nn):
    """aerender in chunks of <= 600 frames, each a fresh process with -mem_usage capped (AE's commit growth expanded the
    pagefile until the drive was full), then a copy-concat of the H.264 chunks."""
    d = cdir(nn)
    plan = json.load(open(d / 'ae_plan.json'))
    out = Path(plan['out_video'])
    for f in glob.glob(str(out.with_suffix('')) + '*'):
        os.remove(f)
    AER = 'C:/Program Files/Adobe/Adobe After Effects 2025/Support Files/aerender.exe'
    run([PY, '-P', JOB / 'ae' / 'ae_run.py', 'quit'], check=False)
    cache = Path(os.environ['LOCALAPPDATA']) / 'Temp' / 'Adobe' / 'After Effects'
    chd = d / 'chunks'; shutil.rmtree(chd, ignore_errors=True); chd.mkdir()
    n = plan['frames']; step = int(os.environ.get('CLIP_AE_CHUNK', 120))
    parts = []
    log = open(d / 'aerender.log', 'w', encoding='utf8')

    def ae_mem_mb():
        """working set of AE's render engine (AfterFX.com); -mem_usage did not cap it (8.4 GB seen on a 15 GB laptop)."""
        out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq AfterFX.com', '/FO', 'CSV', '/NH'], capture_output=True,
                             text=True, errors='replace').stdout
        return sum(int(re.sub(r'\D', '', ln.split('","')[-1]) or 0) // 1024 for ln in out.splitlines() if 'AfterFX' in ln)

    def aer(s0, e0, avi):
        """one aerender call under a RAM watchdog: kill the tree if AE passes CLIP_AE_MAX_MB or free RAM drops < 2.5 GB."""
        cap = int(os.environ.get('CLIP_AE_MAX_MB', 4500))
        sys.path.insert(0, str(JOB / "tools")); import ae_prefs  # AE GUI rewrites its prefs on quit: re-pin MFR + disk cache
        if not ae_prefs.pin(mfr_off=os.environ.get('CLIP_AE_MFR', '0') != '1'):
            print('  WARNING: AE prefs not pinned', flush=True)
        subprocess.run(['taskkill', '/IM', 'dynamiclinkmanager.exe', '/F'], capture_output=True)  # a stale one hangs aerender
        p = subprocess.Popen([AER, '-project', plan['aep'], '-comp', plan['name'], '-s', str(s0), '-e', str(e0),
                              '-RStemplate', 'Best Settings', '-OMtemplate', 'Lossless', '-output', str(avi), '-sound', 'OFF',
                              '-mem_usage', '10', '20', '-v', 'ERRORS_AND_PROGRESS'],
                             stdout=log, stderr=subprocess.STDOUT)
        t0 = time.time(); seen = False; last_eng = t0; last_sz = -1; last_grow = t0
        while p.poll() is None:
            time.sleep(4)
            mb = ae_mem_mb()
            now = time.time()
            if mb > 0:
                seen, last_eng = True, now
            sz = os.path.getsize(avi) if os.path.exists(avi) else 0
            if sz != last_sz:
                last_sz, last_grow = sz, now
            # aerender alive but its engine never started / died (seen 2026-11-09: aerender waited 26 min on a dead
            # engine), or the output stopped growing
            hung = ((not seen) and now - t0 > 90) or (seen and now - last_eng > 60) or (seen and now - last_grow > 240)
            if mb > cap or free_ram_gb() < 2.5 or time.time() - t0 > 5400 or hung:
                subprocess.run(['taskkill', '/PID', str(p.pid), '/T', '/F'], capture_output=True)
                p.wait()
                print(f'  watchdog: killed aerender f{s0}-{e0} (AE {mb} MB, free {free_ram_gb():.1f} GB)', flush=True)
                return False
        return True

    k, s0 = 0, 0
    while s0 < n:
        e0 = min(n, s0 + step) - 1
        for sub in cache.glob('*/Disk Cache*'):
            shutil.rmtree(sub, ignore_errors=True)
        wait_ram()
        part = chd / f'part{k:02d}.mp4'
        for attempt in range(3):
            for g in glob.glob(str(part.with_suffix('')) + '.*'):
                os.remove(g)
            if not aer(s0, e0, part.with_suffix('.avi')):
                # smaller chunk, then wait for RAM before the retry
                step = max(30, step // 2); e0 = min(n, s0 + step) - 1
                wait_ram(); continue
            got = sorted(glob.glob(str(part.with_suffix('')) + '.*'))
            got = [g for g in got if not g.endswith('.mp4')]
            nf = nframes(got[0])[0] if got and os.path.getsize(got[0]) > 1000 else 0
            if nf == e0 - s0 + 1:
                # one lossy encode from the lossless AE frames: H.264 High (delivery codec rule), then drop the big file
                run([FF, '-v', 'error', '-y', '-i', got[0], '-map', '0:v:0', '-c:v', 'h264_nvenc', '-preset', 'p7', '-tune', 'hq',
                     '-rc', 'vbr', '-cq', '18', '-b:v', '0', '-maxrate', '35M', '-bufsize', '70M', '-profile:v', 'high',
                     '-pix_fmt', 'yuv420p', '-bf', '0', '-g', '60', '-color_primaries', 'bt709', '-color_trc', 'bt709',
                     '-colorspace', 'bt709', '-r', f'{OUT_FPS.numerator}/{OUT_FPS.denominator}', str(part)])
                os.remove(got[0])
                got = [str(part)]
                nf = nframes(part)[0]
            print(f'chunk {k} f{s0}-{e0}: {nf} frames (want {e0 - s0 + 1}) attempt {attempt}', flush=True)
            if nf == e0 - s0 + 1:
                parts.append(got[0]); break
        else:
            raise SystemExit(f'chunk {k} failed')
        s0, k = e0 + 1, k + 1
    log.close()
    lst = chd / 'list.txt'
    lst.write_text(''.join("file '" + Path(p).as_posix() + "'\n" for p in parts))
    run([FF, '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', lst, '-map', '0:v:0', '-c', 'copy', out])
    print('render', out, nframes(out)[0], 'frames of', n)
    shutil.rmtree(chd, ignore_errors=True)


# ------------------------------------------------------------------ audio: dialogue + SFX -> mix_audio
def pick_sfx(k, used):
    """k distinct whooshes: rotate across packs, skip files already used in the job and any whose library fingerprint
    is too close (cos >= 0.85) to one already chosen (two files of one pack can be the same sound: mix gate sfx_reuse)."""
    import numpy as np
    lib = json.load(open(os.environ.get('CLIP_SFX_LIB', 'sfx_lib.json'), encoding='utf8'))
    pool = [f for f in lib['files'] if set(f.get('roles', [])) & {'whoosh', 'swoosh'} and 0.4 <= f['dur'] <= 2.0
            and f.get('peak_db', -99) > -20 and f.get('fp') and f['file'] not in used
            and not re.search(r'(?i)glitch|bass|boom|impact|hit|riser|scream|horror', f['rel'])]
    packs = {}
    for f in sorted(pool, key=lambda f: f['rel']):
        packs.setdefault(f['pack'], []).append(f)
    order = []
    while any(packs.values()):
        for p in sorted(packs):
            if packs[p]:
                order.append(packs[p].pop(0))
    def v(f):
        a = np.array(f['fp'], float); return a / (np.linalg.norm(a) + 1e-9)
    chosen = [f for f in lib['files'] if f['file'] in used and f.get('fp')]
    out = []
    for f in order:
        if all(float(v(f) @ v(g)) < 0.85 for g in chosen + out):
            out.append(f)
            if len(out) >= k:
                break
    for f in out:
        used.add(f['file'])
    return out


def audio(nn):
    c, d = clip_cfg(nn), cdir(nn)
    cut = json.load(open(d / 'cutlist.json'))
    fix = json.load(open(d / 'topaz_fix.json'))
    n_out = fix['n_out']
    plan = json.load(open(d / 'ae_plan.json'))
    # dialogue stem to the 59.94 length (pad/trim tail with silence)
    import numpy as np
    sr = 48000
    need = round(n_out * sr / OUT_FPS)
    raw = subprocess.run([FF, '-v', 'error', '-i', str(d / 'dialogue.wav'), '-f', 'f32le', '-ac', '1', '-ar', str(sr), '-'], capture_output=True).stdout
    a = np.frombuffer(raw, np.float32).copy()
    a = a[:need] if len(a) >= need else np.concatenate([a, np.zeros(need - len(a), np.float32)])
    run([FF, '-v', 'error', '-y', '-f', 'f32le', '-ar', str(sr), '-ac', '1', '-i', '-', '-c:a', 'pcm_f32le', str(d / 'dialogue60.wav')],
        input=None) if False else None
    p = subprocess.Popen([FF, '-v', 'error', '-y', '-f', 'f32le', '-ar', str(sr), '-ac', '1', '-i', '-', '-c:a', 'pcm_f32le', str(d / 'dialogue60.wav')], stdin=subprocess.PIPE)
    p.stdin.write(a.tobytes()); p.stdin.close(); p.wait()
    # music bed: licence-checked instrumental (find_music.py, ref 06), a different track per clip (candidate = rank),
    # kept low under the CEO's voice (-24 LUFS bed, ducked -10 dB while he speaks)
    mj = d / 'music' / 'music.json'
    if not mj.exists():
        run([PY, '-P', SK / 'find_music.py', '--mood', c.get('mood', 'inspiring'), '--query', c.get('music_query', 'corporate technology'),
             '--clip-s', f'{float(n_out / OUT_FPS):.1f}', '--dialogue', d / 'dialogue60.wav', '--top', '10', '--max-analyse', '14',
             '--pick', str(c.get('music_pick', c['rank'])), '--out-dir', d / 'music', '--ffmpeg', FF, '--ffprobe', FP])
    music = json.load(open(mj, encoding='utf8'))
    bed = dict(music['bed']); bed['lufs'] = c.get('bed_lufs', -24.0)
    usedf = JOB / 'sfx_used.json'
    used = set(json.load(open(usedf))) if usedf.exists() else set()
    sfx = pick_sfx(len(plan['accents']), used)
    gain = c.get('sfx_gain_db', -9.0)
    for attempt in range(4):
        json.dump(sorted(used), open(usedf, 'w'), indent=0)
        # mix_audio lands each hit's peak on (frame + 1): pass the accent frame itself (it measures the peak per file)
        items = [{'path': f['file'], 'frame': fr, 'gain_db': gain} for f, fr in zip(sfx, plan['accents'])]
        ap = {'fps': f'{OUT_FPS.numerator}/{OUT_FPS.denominator}', 'frames': n_out, 'dialogue': str(d / 'dialogue60.wav'),
              'words': [[w['start'], w['end']] for w in cut['words']], 'bed': bed, 'sfx': items,
              'duck': {'depth_db': -10, 'attack_s': 0.02, 'release_s': 0.3, 'merge_gap_s': 0.6}}
        json.dump(ap, open(d / 'audio_plan.json', 'w'), indent=1)
        r = run([PY, '-P', SK / 'mix_audio.py', '--plan', d / 'audio_plan.json', '--outdir', d / 'mix', '--ffmpeg', FF, '--ffprobe', FP], check=False)
        if not r.returncode:
            break
        rep = json.load(open(d / 'mix' / 'mix_report.json', encoding='utf8')) if (d / 'mix' / 'mix_report.json').exists() else {}
        failed = rep.get('failed', [])
        if failed != ['sfx_align']:
            raise SystemExit(f'mix failed: {failed}')
        # a sound whose loudest moment is not its onset hit cannot be aligned: swap it for another library sound
        bad = {m['i'] for m in rep['gates']['sfx_align']['measured']}
        print('sfx_align: swapping', sorted(bad), flush=True)
        got = pick_sfx(len(bad), used)
        if len(got) < len(bad):  # job pool exhausted: distinct within this clip, reuse across clips is fine
            mine = {f['file'] for f in sfx} | {f['file'] for f in got}
            got += pick_sfx(len(bad) - len(got), set(mine))
        if len(got) < len(bad):
            raise SystemExit('mix failed: no aligned SFX left in the library')
        repl = iter(got)
        sfx = [next(repl) if i in bad else f for i, f in enumerate(sfx)]
    else:
        raise SystemExit('mix failed: sfx_align after 4 swaps')
    json.dump(sorted(used), open(usedf, 'w'), indent=0)


def final(nn):
    c, d = clip_cfg(nn), cdir(nn)
    plan = json.load(open(d / 'ae_plan.json'))
    src = sorted(glob.glob(str(Path(plan['out_video']).with_suffix('')) + '*'))[0]
    # delivery codec rule: H.264 High (AE's H.264 template writes Main) -> one NVENC High pass
    vid = str(d / 'ae_video_high.mp4')
    vid = src
    if False:
     run([FF, '-v', 'error', '-y', '-i', src, '-c:v', 'h264_nvenc', '-preset', 'p7', '-tune', 'hq', '-rc', 'vbr',
         '-cq', '16', '-b:v', '0', '-maxrate', '60M', '-bufsize', '120M', '-profile:v', 'high', '-pix_fmt', 'yuv420p', '-bf', '0',
         '-g', '60', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709', vid])
    DELIVER.mkdir(exist_ok=True)
    out = DELIVER / f"{int(nn):02d}-{c['slug']}.mp4"
    r = run([PY, '-P', SK / 'finalize_mux.py', '--video', vid, '--mix', d / 'mix' / 'mix.wav', '--out', out,
             '--fps', f'{OUT_FPS.numerator}/{OUT_FPS.denominator}', '--frames', plan['frames'], '--max-dur', '50',
             '--ffmpeg', FF, '--ffprobe', FP], check=False)
    print('final rc', r.returncode, out)


STAGES = {'prep': prep, 'track': track, 'stab': stab, 'topaz': topaz, 'overlay': overlay, 'ae': ae, 'render': render, 'audio': audio, 'final': final}
# ------------------------------------------------------------------ qc: gates + review sheets
BANNED = ['best', 'safest', 'guaranteed', 'risk-free', '100% secure', 'unhackable', 'buy now', 'last chance', "don't miss out"]


def qc(nn):
    c, d = clip_cfg(nn), cdir(nn)
    q = d / 'qc'; q.mkdir(exist_ok=True)
    plan = json.load(open(d / 'ae_plan.json'))
    out = DELIVER / f"{int(nn):02d}-{c['slug']}.mp4"
    res = {}
    t = json.load(open(d / 'title.json'))
    safe_top = TITLE_TOP + (t['box'][3] - t['box'][1]) + 60
    r = run([PY, '-P', SK / 'caption_gate.py', '--ass', d / 'captions.ass', '--layout', d / 'captions_layout.json', '--qc', q,
             '--safe', f"65,{safe_top},950,{c.get('safe_bottom', 1330)}", '--ffmpeg', FF], check=False)
    res['caption_gate_rc'] = r.returncode
    vid = sorted(glob.glob(str(Path(plan['out_video']).with_suffix('')) + '*'))[0]
    dur = plan['frames'] / plan['fps']
    mask = [{'t0': 0, 't1': dur, 'box': [0, 0, W, TITLE_TOP + (t['box'][3] - t['box'][1]) + 20]},
            {'t0': 0, 't1': dur, 'box': [40, safe_top - 20, 1000, c.get('safe_bottom', 1330) + 20]}]
    excl = [[max(0, a / plan['fps'] - 0.5), a / plan['fps'] + 0.5] for a in plan['accents']]
    json.dump(mask, open(q / 'grade_mask.json', 'w')); json.dump(excl, open(q / 'grade_excl.json', 'w'))
    r = run([PY, '-P', SK / 'grade_gate.py', d / 'topaz.mp4', vid, '--edited', '--mask', q / 'grade_mask.json',
             '--exclude', q / 'grade_excl.json', '--json', q / 'grade_gate.json', '--name', f'clip{nn}',
             '--ffmpeg', FF, '--ffprobe', FP], check=False)
    res['grade_gate_rc'] = r.returncode
    r = run([PY, '-P', SK / 'finalize_mux.py', '--check', out, '--fps', f'{OUT_FPS.numerator}/{OUT_FPS.denominator}',
             '--frames', plan['frames'], '--max-dur', '50', '--ffmpeg', FF, '--ffprobe', FP], check=False)
    res['delivery_rc'] = r.returncode
    texts = [c['title_onscreen']] + list(c['post_captions'].values())
    res['banned_hits'] = [b for b in BANNED for t in texts if re.search(r'(?i)(?<![a-z])' + re.escape(b) + r'(?![a-z])', t)]
    res['tags_ok'] = ('@moonpayhq' in c['post_captions']['tiktok'] and '@moonpay' in c['post_captions']['instagram']
                      and '@moonpayhq' in c['post_captions']['youtube'])
    n = plan['frames']
    step = max(1, n // 12)
    run([FF, '-v', 'error', '-y', '-i', out, '-vf', f"select='not(mod(n\\,{step}))',scale=270:480,tile=6x2", '-frames:v', '1',
         '-fps_mode', 'vfr', q / 'final_sheet.jpg'])
    json.dump(res, open(q / 'qc.json', 'w'), indent=1)
    print('QC', nn, res)


STAGES['qc'] = qc


if __name__ == '__main__':
    st, nn = sys.argv[1], sys.argv[2]
    if st == 'all':
        for s in ('prep', 'topaz', 'overlay', 'ae', 'render', 'audio', 'final', 'qc'):
            STAGES[s](nn)
    else:
        STAGES[st](nn)
