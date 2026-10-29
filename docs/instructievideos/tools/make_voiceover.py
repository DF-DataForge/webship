#!/usr/bin/env python3
"""Generate the voice-over of the instruction videos with a neural Flemish voice.

    pip install edge-tts
    python3 docs/instructievideos/tools/make_voiceover.py [--voice nl-BE-ArnaudNeural] [--rate -5%] [NN ...]
    python3 docs/instructievideos/tools/make_voiceover.py --sample

Reads the voice-over column of every NN_*.md script, speaks each scene with a
Microsoft neural voice (default nl-BE-DenaNeural, via the edge-tts package)
and lays the scenes out on one track per video, each starting at its timecode
from the draaiboek (or right after the previous scene when that one ran long).

Writes voiceover/NN.mp3 (mono, loudness -16 LUFS), voiceover/NN_scenes.csv
(start and end of each scene in that track, to record the screen against) and
ondertitels/NN.srt, timed on the generated speech. --sample writes a short
voice test for every Flemish voice to voiceover/stemproef_*.mp3.

Pronunciation: the spoken text goes through LEXICON first (e.g. 'Stoqflow' is
spoken as 'Stokflow'); the subtitles keep the written form.
"""
import argparse
import asyncio
import csv
import glob
import os
import re
import shutil
import ssl
import subprocess
import sys
import tempfile

import edge_tts
import edge_tts.communicate

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, 'voiceover')
SUBS = os.path.join(ROOT, 'ondertitels')
sys.path.insert(0, HERE)
from make_subtitles import chunks, scenes, srt_time  # noqa: E402

FFMPEG = shutil.which('ffmpeg')
FFPROBE = shutil.which('ffprobe')

VOICES = ['nl-BE-DenaNeural', 'nl-BE-ArnaudNeural']
GAP = 0.4          # minimum silence between two scenes, in seconds
TAIL = 1.0         # silence after the last scene

# Written form -> how the voice should say it. Whole words only, applied in order.
LEXICON = [
    (r'SQF/Stock', 'S Q F Stock'),
    (r'H800/Stock', 'H achthonderd Stock'),
    (r'Stoqflow', 'Stokflow'),
    (r"SKU's", "S K U's"),
    (r'SKU', 'S K U'),
    (r'SQF', 'S Q F'),
    (r'H800', 'H achthonderd'),
    (r'Odoo\.sh', 'Odoo punt S H'),
    (r'19\.0', 'negentien punt nul'),
    (r'JSON', 'djeesson'),
    (r'HS-code', 'H S code'),
    (r"Woody's", 'Woedies'),
    (r'Key', 'Kie'),
    (r'Secret', 'Siekret'),
    # Flemish 'vie-dee-joo', not the English 'vid-ee-oh'
    (r"[Vv]ideo's", "viedeejoos"),
    (r'[Vv]ideo', 'viedeejo'),
    (r'0([1-9])', r'\1'),      # 'video 07' -> 'video 7', not 'nul zeven'
]

SAMPLE = ('In deze video ziet u hoe het werkt. Ga in Odoo naar Stoqflow, Instellingen. Vul de Key en het Secret in, '
          'en klik op Verbinding testen. Elke levering uit SQF/Stock wordt een order in Stoqflow, '
          'en zonder SKU kan Odoo het product niet doorsturen.')


def spoken(text):
    for written, said in LEXICON:
        text = re.sub(r'(?<![\w-])%s(?![\w])' % written, said, text)
    return text


def ssl_context():
    """Behind a TLS-inspecting proxy, trust the CA bundle the environment
    points to instead of certifi's."""
    cafile = os.environ.get('SSL_CERT_FILE') or os.environ.get('REQUESTS_CA_BUNDLE')
    if not cafile and os.path.exists('/root/.ccr/ca-bundle.crt'):
        cafile = '/root/.ccr/ca-bundle.crt'
    return ssl.create_default_context(cafile=cafile) if cafile else None


async def synth(text, voice, rate, path):
    proxy = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')
    communicate = edge_tts.Communicate(text, voice, rate=rate, proxy=proxy)
    with open(path, 'wb') as f:
        async for chunk in communicate.stream():
            if chunk['type'] == 'audio':
                f.write(chunk['data'])


def duration(path):
    out = subprocess.run([FFPROBE, '-v', 'error', '-show_entries', 'format=duration',
                          '-of', 'csv=p=0', path], check=True, capture_output=True, text=True)
    return float(out.stdout.strip())


def to_wav(src, dst):
    subprocess.run([FFMPEG, '-y', '-loglevel', 'error', '-i', src, '-ar', '48000', '-ac', '1',
                    dst], check=True)


def silence(seconds, dst):
    subprocess.run([FFMPEG, '-y', '-loglevel', 'error', '-f', 'lavfi',
                    '-i', 'anullsrc=r=48000:cl=mono', '-t', '%.3f' % seconds, dst], check=True)


def master(wav_list, dst):
    """Concatenate the pieces and normalise to -16 LUFS / -1.5 dBTP."""
    with tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False) as f:
        for wav in wav_list:
            f.write("file '%s'\n" % wav)
        listing = f.name
    try:
        subprocess.run([FFMPEG, '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0',
                        '-i', listing, '-af', 'loudnorm=I=-16:TP=-1.5:LRA=11',
                        '-ar', '48000', '-ac', '1', '-c:a', 'libmp3lame', '-b:a', '64k', dst],
                       check=True)
    finally:
        os.unlink(listing)


def make_video(path, voice, rate):
    number = os.path.basename(path)[:2]
    rows = list(scenes(path))
    timeline, subtitles, pieces = [], [], []
    with tempfile.TemporaryDirectory() as tmp:
        cursor = 0.0
        for i, (scene, start, end, text) in enumerate(rows):
            mp3 = os.path.join(tmp, '%02d.mp3' % i)
            asyncio.run(synth(spoken(text), voice, rate, mp3))
            wav = mp3[:-4] + '.wav'
            to_wav(mp3, wav)
            length = duration(wav)
            begin = max(float(start), cursor + (GAP if cursor else 0.0))
            if begin > cursor:
                gap = os.path.join(tmp, 'gap%02d.wav' % i)
                silence(begin - cursor, gap)
                pieces.append(gap)
            pieces.append(wav)
            timeline.append((scene, start, end, begin, begin + length))
            parts = chunks(text)
            total = sum(len(p) for p in parts)
            t = begin
            for part in parts:
                share = length * len(part) / total
                subtitles.append((t, t + share, part))
                t += share
            cursor = begin + length
        tail = os.path.join(tmp, 'tail.wav')
        silence(TAIL, tail)
        pieces.append(tail)
        os.makedirs(OUT, exist_ok=True)
        master(pieces, os.path.join(OUT, number + '.mp3'))

    # Scenes without a voice-over (opening and end card) are not in the sheet.
    with open(os.path.join(OUT, number + '_scenes.csv'), 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['scene', 'draaiboek_van', 'draaiboek_tot', 'spraak_van', 'spraak_tot'])
        for scene, start, end, begin, stop in timeline:
            writer.writerow([scene, srt_time(start)[3:8], srt_time(end)[3:8],
                             srt_time(begin)[3:11], srt_time(stop)[3:11]])
    os.makedirs(SUBS, exist_ok=True)
    with open(os.path.join(SUBS, number + '.srt'), 'w', encoding='utf-8') as f:
        for i, (start, end, text) in enumerate(subtitles, 1):
            f.write('%d\n%s --> %s\n%s\n\n' % (i, srt_time(start), srt_time(end - 0.05), text))
    planned = rows[-1][2] if rows else 0
    print('voiceover/%s.mp3: %d scenes, speech ends at %s (draaiboek: %s)' % (
        number, len(rows), srt_time(cursor)[3:8], srt_time(planned)[3:8]))


def make_samples(rate):
    os.makedirs(OUT, exist_ok=True)
    for voice in VOICES:
        name = voice.split('-')[2].replace('Neural', '').lower()
        dst = os.path.join(OUT, 'stemproef_%s.mp3' % name)
        asyncio.run(synth(spoken(SAMPLE), voice, rate, dst))
        print('wrote voiceover/stemproef_%s.mp3' % name)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('videos', nargs='*', help='video numbers, e.g. 02 07 (default: all)')
    parser.add_argument('--voice', default=VOICES[0], help='edge-tts voice (default %(default)s)')
    parser.add_argument('--rate', default='-5%', help='speaking rate (default %(default)s)')
    parser.add_argument('--sample', action='store_true', help='only write a voice test per voice')
    args = parser.parse_args()
    if not FFMPEG or not FFPROBE:
        sys.exit('ffmpeg and ffprobe are needed')
    ctx = ssl_context()
    if ctx:
        edge_tts.communicate._SSL_CTX = ctx
    if args.sample:
        make_samples(args.rate)
        return
    for path in sorted(glob.glob(os.path.join(ROOT, '[0-9][0-9]_*.md'))):
        if args.videos and os.path.basename(path)[:2] not in args.videos:
            continue
        make_video(path, args.voice, args.rate)


if __name__ == '__main__':
    main()
