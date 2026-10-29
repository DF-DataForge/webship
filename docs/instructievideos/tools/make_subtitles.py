#!/usr/bin/env python3
"""Generate SRT subtitles from the voice-over column of the video scripts.

    python3 docs/instructievideos/tools/make_subtitles.py

Reads every NN_*.md script next to this tools folder and writes
docs/instructievideos/ondertitels/NN.srt. The scene timecodes come from the
'Tijd' column; a long voice-over is split into subtitles of at most two lines
of 42 characters, each getting a share of the scene proportional to its
length. After the recording, shift or stretch the file in the editor to the
real voice-over (the timecodes in the scripts are estimates).
"""
import glob
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, 'ondertitels')

LINE = 42       # characters per subtitle line
MAX_LINES = 2


def seconds(stamp):
    minutes, secs = stamp.split(':')
    return int(minutes) * 60 + int(secs)


def srt_time(value):
    ms = int(round(value * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return '%02d:%02d:%02d,%03d' % (h, m, s, ms)


def plain(text):
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    return text.replace('`', '').strip()


def wrap(words, width):
    lines, current = [], ''
    for word in words:
        if current and len(current) + 1 + len(word) > width:
            lines.append(current)
            current = word
        else:
            current = (current + ' ' + word).strip()
    if current:
        lines.append(current)
    return lines


def chunks(text):
    """Split a voice-over into subtitles: sentence by sentence, and a sentence
    that does not fit on two lines over several subtitles."""
    out = []
    for sentence in re.split(r'(?<=[.?!:])\s+', text):
        lines = wrap(sentence.split(), LINE)
        for i in range(0, len(lines), MAX_LINES):
            out.append('\n'.join(lines[i:i + MAX_LINES]))
    return out


def scenes(path):
    """Yield (scene, start, end, voice-over) for each row of the draaiboek table."""
    for row in open(path, encoding='utf-8'):
        cells = [c.strip() for c in row.strip().strip('|').split('|')]
        if len(cells) < 4 or not re.fullmatch(r'\d+', cells[0]):
            continue
        match = re.fullmatch(r'(\d+:\d\d)\s*[–-]\s*(\d+:\d\d)', cells[1])
        if not match:
            continue
        voice = plain(cells[3])
        if voice and voice != '—':
            yield int(cells[0]), seconds(match.group(1)), seconds(match.group(2)), voice


def main():
    os.makedirs(OUT, exist_ok=True)
    for path in sorted(glob.glob(os.path.join(ROOT, '[0-9][0-9]_*.md'))):
        number = os.path.basename(path)[:2]
        entries = []
        for _scene, start, end, voice in scenes(path):
            parts = chunks(voice)
            total = sum(len(p) for p in parts)
            t = float(start)
            for part in parts:
                length = (end - start) * len(part) / total
                entries.append((t, t + length, part))
                t += length
        with open(os.path.join(OUT, number + '.srt'), 'w', encoding='utf-8') as f:
            for i, (start, end, text) in enumerate(entries, 1):
                f.write('%d\n%s --> %s\n%s\n\n' % (i, srt_time(start), srt_time(end - 0.05), text))
        print('wrote ondertitels/%s.srt (%d subtitles)' % (number, len(entries)))


if __name__ == '__main__':
    main()
