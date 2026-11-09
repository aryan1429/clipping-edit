"""Build a review pack per delivered clip for the adversarial review agents.
review/NN/: sheet_a.jpg .. (24 frames per sheet, 4x6 at 270x480, ~1 frame per 0.5-0.8 s), first_frame.png (cover),
transcript.txt (kept words with output times), captions.txt (chunks as shown, with times), meta.json (title, post
captions, qc.json, gate summaries). usage: review_pack.py [NN ...]"""
import json, os, subprocess, sys
from pathlib import Path

JOB = Path(os.environ.get('CLIP_JOB', '.'))
FF = (os.environ.get('CLIP_FFMPEG_DIR', '') + '/ffmpeg.exe') if os.environ.get('CLIP_FFMPEG_DIR') else 'ffmpeg'
DL = Path(os.environ.get('CLIP_DELIVER', 'edited'))


def main(nns):
    cfg = json.load(open(JOB / 'clips_final.json', encoding='utf8'))
    clips = cfg if isinstance(cfg, list) else cfg['clips']
    for nn in nns:
        c = clips[int(nn) - 1]
        d = JOB / 'clips' / f'{int(nn):02d}'
        out = JOB / 'review' / f'{int(nn):02d}'
        out.mkdir(parents=True, exist_ok=True)
        vids = sorted(DL.glob(f'{int(nn):02d}-*.mp4'))
        if not vids:
            print('no delivery for', nn); continue
        v = vids[-1]
        plan = json.load(open(d / 'ae_plan.json'))
        n = plan['frames']
        per = 24
        k = 3  # three sheets -> 72 frames over the clip
        step = max(1, n // (per * k))
        for i in range(k):
            s0 = i * per * step
            subprocess.run([FF, '-v', 'error', '-y', '-i', str(v), '-vf',
                            f"select='gte(n\\,{s0})*lt(n\\,{s0 + per * step})*not(mod(n-{s0}\\,{step}))',"
                            f"scale=270:480,drawtext=text='%{{n}}':x=6:y=6:fontsize=22:fontcolor=yellow:box=1:boxcolor=black@0.6,tile=6x4",
                            '-frames:v', '1', '-fps_mode', 'vfr', str(out / f'sheet_{"abc"[i]}.jpg')], check=True)
        subprocess.run([FF, '-v', 'error', '-y', '-i', str(v), '-frames:v', '1', str(out / 'first_frame.png')], check=True)
        cut = json.load(open(d / 'cutlist.json'))
        lines = []
        for w in cut['words']:
            lines.append(f"{w['start']:7.2f}-{w['end']:6.2f}  {w['id']:>6}  {w['text']}")
        (out / 'transcript.txt').write_text('\n'.join(lines), encoding='utf8')
        lay = json.load(open(d / 'captions_layout.json', encoding='utf8'))
        caps = []
        for ch in lay.get('chunks', []):
            cols = {w['text']: w.get('color') for w in ch.get('words', []) if w.get('color', '#FFFFFF').upper() != '#FFFFFF'}
            caps.append(f"f{ch['start_f']}-{ch['end_f']}  {' / '.join(ch['lines'])}" + (f"   colours {cols}" if cols else ''))
        (out / 'captions.txt').write_text('\n'.join(caps), encoding='utf8')
        meta = {'clip': int(nn), 'video': str(v), 'frames': n, 'fps': '60000/1001', 'title': c.get('title_onscreen'),
                'post_captions': c.get('post_captions'), 'source_id': c.get('source_id'),
                'qc': json.load(open(d / 'qc' / 'qc.json')) if (d / 'qc' / 'qc.json').exists() else None,
                'sheet_frame_step': step, 'caption_fix': c.get('caption_fix')}
        json.dump(meta, open(out / 'meta.json', 'w', encoding='utf8'), indent=1, ensure_ascii=False)
        print('pack', nn, v.name, 'chunks', len(caps))


if __name__ == '__main__':
    main(sys.argv[1:] or ['1', '2', '3', '4', '5', '6', '7'])
