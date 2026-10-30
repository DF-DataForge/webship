#!/usr/bin/env python3
"""Assemble one instruction video from its recorded scene clips.

    assemble.py NN

Inputs
- docs/instructievideos/NN_*.md         draaiboek: scene number, voice-over, 'Tekst in beeld'
- /opt/rec/out/NN/sKK.mp4               recorded clip per scene (missing for card scenes)
- docs/instructievideos/cards/NN_*.jpg  opening and end card

Each scene lasts as long as its clip or its voice-over (plus breathing room),
whichever is longer; a short clip holds its last frame. The voice (Dena,
generated per scene and cached) starts LEAD seconds into the scene. The
'Tekst in beeld' is shown as a lower third during the first seconds.
Writes /opt/rec/final/NN.mp4 (H.264 + AAC, soft Dutch subtitles) and NN.srt.
"""
import asyncio
import glob
import hashlib
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile

DOCS = '/home/user/webship/docs/instructievideos'
sys.path.insert(0, os.path.join(DOCS, 'tools'))
import make_voiceover as mv  # noqa: E402
from make_subtitles import chunks, plain, srt_time  # noqa: E402

REC = '/opt/rec/out'
FINAL = '/opt/rec/final'
CACHE = '/opt/rec/tts_cache'
CHROME = '/opt/pw-browsers/chromium_headless_shell-1243/chrome-headless-shell-linux64/chrome-headless-shell'
VOICE = 'nl-BE-DenaNeural'
RATE = '-5%'
W, H, FPS = 1920, 1080, 30
LEAD = 0.5        # silence before the voice in a scene
TAIL = 0.8        # silence after the voice
CARD = 5.0        # opening / end card length without voice
OVERLAY_MAX = 5.0


def run(*cmd, **kw):
    subprocess.run(cmd, check=True, **kw)


def duration(path):
    out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                          '-of', 'csv=p=0', path], check=True, capture_output=True, text=True)
    return float(out.stdout.strip())


def draaiboek(number):
    path = glob.glob(os.path.join(DOCS, number + '_*.md'))[0]
    rows = []
    for line in open(path, encoding='utf-8'):
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if len(cells) >= 5 and re.fullmatch(r'\d+', cells[0]) and re.match(r'\d+:\d\d', cells[1]):
            voice = plain(cells[3])
            rows.append({
                'scene': int(cells[0]),
                'beeld': cells[2],
                'voice': '' if voice in ('', '—') else voice,
                'overlay': plain(cells[4]) if cells[4] not in ('', '—') else '',
            })
    return rows


def tts(text):
    os.makedirs(CACHE, exist_ok=True)
    key = hashlib.sha1((VOICE + RATE + mv.spoken(text)).encode()).hexdigest()[:16]
    wav = os.path.join(CACHE, key + '.wav')
    if not os.path.exists(wav):
        ctx = mv.ssl_context()
        if ctx:
            mv.edge_tts.communicate._SSL_CTX = ctx
        mp3 = wav[:-4] + '.mp3'
        asyncio.run(mv.synth(mv.spoken(text), VOICE, RATE, mp3))
        run('ffmpeg', '-y', '-loglevel', 'error', '-i', mp3, '-ar', '48000', '-ac', '1', wav)
    return wav


def render_overlay(text, png):
    """Lower third in the house style: dark bar, gradient accent, white text."""
    doc = f"""<!doctype html><html><head><meta charset="utf-8"><style>
    html,body{{margin:0;width:{W}px;height:{H}px;background:transparent;overflow:hidden}}
    .lt{{position:absolute;left:72px;bottom:96px;max-width:1300px;padding:22px 40px 24px 44px;
        background:rgba(14,27,44,.90);border-radius:14px;color:#fff;
        font:600 40px 'Inter','Inter Display',sans-serif;letter-spacing:.005em;overflow:hidden}}
    .lt::before{{content:'';position:absolute;left:0;top:0;bottom:0;width:12px;
        background:linear-gradient(180deg,#2ED3B7,#2B8FE3)}}
    </style></head><body><div class="lt">{html.escape(text)}</div></body></html>"""
    with tempfile.NamedTemporaryFile('w', suffix='.html', delete=False, encoding='utf-8') as f:
        f.write(doc)
        src = f.name
    try:
        run(CHROME, '--headless', '--no-sandbox', '--disable-gpu', '--hide-scrollbars',
            '--force-device-scale-factor=1', f'--window-size={W},{H}',
            '--default-background-color=00000000', f'--screenshot={png}', 'file://' + src,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    finally:
        os.unlink(src)


def stretched(src, target, tmp):
    """Re-render a recorded clip so it lasts `target` seconds by lengthening
    its still moments (frames shown 0.25 s or longer) in proportion; motion
    keeps its real speed. Returns the clip to use."""
    import json
    frames_dir = src[:-4] + '_frames'
    lst = os.path.join(frames_dir, 'list.json')
    if not os.path.exists(lst):
        return src
    items = json.load(open(lst))
    total = sum(i['dur'] for i in items)
    extra = target - total
    holds = [i for i in items if i['dur'] >= 0.25]
    hold_total = sum(i['dur'] for i in holds)
    if extra <= 0.3 or not hold_total:
        return src
    # Never stretch one still moment by more than 4x; the rest is a final hold.
    factor = min(1 + extra / hold_total, 4.0)
    for i in holds:
        i['dur'] *= factor
    out = os.path.join(tmp, 'st_' + os.path.basename(src))
    txt = ''.join("file '%s'\nduration %.4f\n" % (i['name'], i['dur']) for i in items)
    txt += "file '%s'\n" % items[-1]['name']
    listing = out + '.txt'
    open(listing, 'w').write(txt)
    run('ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', listing,
        '-vf', f'fps={FPS},scale={W}:{H}:flags=lanczos,format=yuv420p', '-c:v', 'libx264',
        '-preset', 'medium', '-crf', '18', out)
    return out


def scene_clip(src, length, out, overlay_png=None, still=False):
    """Video of exactly `length` seconds: the clip (or a still image), its last
    frame held, optional lower third fading in and out."""
    ins = ['-loop', '1', '-framerate', str(FPS), '-t', f'{length:.3f}', '-i', src] if still else ['-i', src]
    vf = f'[0:v]fps={FPS},scale={W}:{H},setsar=1,tpad=stop_mode=clone:stop_duration={length + 1:.3f},trim=duration={length:.3f},setpts=PTS-STARTPTS[v0]'
    if overlay_png:
        shown = min(OVERLAY_MAX, length - 0.4)
        ins += ['-loop', '1', '-framerate', str(FPS), '-t', f'{length:.3f}', '-i', overlay_png]
        vf += (f';[1:v]format=rgba,fade=t=in:st=0.4:d=0.35:alpha=1,'
               f'fade=t=out:st={shown:.2f}:d=0.35:alpha=1[ov];[v0][ov]overlay=0:0:format=auto[v]')
        last = '[v]'
    else:
        last = '[v0]'
    run('ffmpeg', '-y', '-loglevel', 'error', *ins, '-filter_complex', vf, '-map', last,
        '-an', '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p', '-r', str(FPS),
        '-video_track_timescale', '15360', out)


def scene_audio(voice_wav, length, out):
    if voice_wav:
        run('ffmpeg', '-y', '-loglevel', 'error', '-i', voice_wav, '-af',
            f'adelay={int(LEAD * 1000)},apad=whole_dur={length:.3f},atrim=duration={length:.3f}',
            '-ar', '48000', '-ac', '1', out)
    else:
        run('ffmpeg', '-y', '-loglevel', 'error', '-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=mono',
            '-t', f'{length:.3f}', out)


def main(number):
    rows = draaiboek(number)
    os.makedirs(FINAL, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix='asm-')
    videos, audios, subs = [], [], []
    t = 0.0
    try:
        for i, row in enumerate(rows):
            k = row['scene']
            beeld = row['beeld'].lower()
            is_open = i == 0 and beeld.startswith('openingskaart')
            is_end = beeld.startswith('eindkaart')
            voice = tts(row['voice']) if row['voice'] else None
            vlen = duration(voice) if voice else 0.0
            if is_open or is_end:
                src = os.path.join(DOCS, 'cards', '%s_%s.jpg' % (number, 'open' if is_open else 'eind'))
                length = max(CARD, LEAD + vlen + TAIL)
                still, overlay = True, None
            else:
                src = os.path.join(REC, number, 's%02d.mp4' % k)
                if not os.path.exists(src):
                    raise SystemExit('missing clip ' + src)
                length = max(duration(src), LEAD + vlen + TAIL)
                src = stretched(src, length, tmp)
                still = False
                overlay = None
                if row['overlay']:
                    overlay = os.path.join(tmp, 'ov%02d.png' % k)
                    render_overlay(row['overlay'], overlay)
            v = os.path.join(tmp, 'v%02d.mp4' % k)
            a = os.path.join(tmp, 'a%02d.wav' % k)
            scene_clip(src, length, v, overlay, still)
            scene_audio(voice, length, a)
            videos.append(v)
            audios.append(a)
            if voice:
                parts = chunks(row['voice'])
                total = sum(len(p) for p in parts)
                s = t + LEAD
                for p in parts:
                    share = vlen * len(p) / total
                    subs.append((s, s + share, p))
                    s += share
            print('scene %2d: %5.1fs (video %5.2f, audio %5.2f) %s' % (k, length, duration(v), duration(a),
                                                              'card' if still else os.path.basename(src)))
            t += length

        vlist = os.path.join(tmp, 'v.txt')
        alist = os.path.join(tmp, 'a.txt')
        open(vlist, 'w').write(''.join("file '%s'\n" % v for v in videos))
        open(alist, 'w').write(''.join("file '%s'\n" % a for a in audios))
        video = os.path.join(tmp, 'video.mp4')
        audio = os.path.join(tmp, 'audio.m4a')
        run('ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', vlist, '-c', 'copy', video)
        run('ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', alist,
            '-af', 'loudnorm=I=-16:TP=-1.5:LRA=11', '-ar', '48000', '-c:a', 'aac', '-b:a', '128k', audio)
        srt = os.path.join(FINAL, number + '.srt')
        with open(srt, 'w', encoding='utf-8') as f:
            for i, (s, e, text) in enumerate(subs, 1):
                f.write('%d\n%s --> %s\n%s\n\n' % (i, srt_time(s), srt_time(e - 0.05), text))
        out = os.path.join(FINAL, number + '.mp4')
        run('ffmpeg', '-y', '-loglevel', 'error', '-i', video, '-i', audio, '-i', srt,
            '-map', '0:v', '-map', '1:a', '-map', '2:s', '-c:v', 'copy', '-c:a', 'copy', '-c:s', 'mov_text',
            '-metadata:s:s:0', 'language=dut', '-metadata:s:a:0', 'language=dut',
            '-movflags', '+faststart', out)
        print('wrote %s (%s)' % (out, srt_time(t)[3:8]))
    finally:
        if not os.environ.get('KEEP'):
            shutil.rmtree(tmp, ignore_errors=True)
        else:
            print('kept', tmp)


if __name__ == '__main__':
    main(sys.argv[1])
