#!/usr/bin/env python3
"""Generate the opening and end cards of the Stoqflow instruction videos.

Every card is an HTML page in the Data Forge house style (dark background,
teal-to-blue gradient from the logo, Inter Display), rendered to PNG with
headless Chromium and turned into a 5-second clip with ffmpeg.

    python3 docs/instructievideos/tools/make_cards.py [path/to/chromium-headless-shell]

Writes docs/instructievideos/cards/NN_open.jpg|mp4, NN_eind.jpg|mp4 and
ondertitel_balk.png (transparent). Edit VIDEOS below when a title changes.
"""
import base64
import html
import os
import shutil
import subprocess
import sys
import tempfile

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ASSETS = os.path.join(ROOT, 'assets')
OUT = os.path.join(ROOT, 'cards')
CHROME = (sys.argv[1] if len(sys.argv) > 1
          else '/opt/pw-browsers/chromium_headless_shell-1243/chrome-headless-shell-linux64/'
               'chrome-headless-shell')
FFMPEG = shutil.which('ffmpeg')

W, H = 1920, 1080
CLIP_SECONDS = 5

# House style, taken from the Data Forge logo
NAVY = '#0E1B2C'
NAVY_2 = '#13263D'
TEAL = '#2ED3B7'
BLUE = '#2B8FE3'
WHITE = '#FFFFFF'
MUTED = '#9FB3C8'
FONT = "'Inter Display', 'Inter', 'DejaVu Sans', sans-serif"

SERIES = {
    'A': 'Reeks A · Installatie en configuratie',
    'B': 'Reeks B · Basisflows met Stoqflow',
}

# (number, series, title)
VIDEOS = [
    ('01', 'A', 'De Stoqflow-koppeling in een notendop'),
    ('02', 'A', 'Installeren en verbinden met Stoqflow'),
    ('03', 'A', 'Magazijn, locatie en routes'),
    ('04', 'A', 'Synchronisatieregels: orders, klanten en vervoerders'),
    ('05', 'A', 'Producten klaarzetten voor Stoqflow'),
    ('06', 'A', 'Automatisering en bewaking'),
    ('07', 'B', 'Van verkooporder tot uitgaande levering'),
    ('08', 'B', 'Van inkooporder tot inkomende levering'),
    ('09', 'B', 'Bevoorraden vanuit het eigen magazijn'),
    ('10', 'B', 'Retours, backorders en voorraad'),
    ('11', 'B', 'Opvolgen en fouten oplossen'),
]


def data_uri(name):
    with open(os.path.join(ASSETS, name), 'rb') as f:
        return 'data:image/png;base64,' + base64.b64encode(f.read()).decode()


LOGO = data_uri('dataforge_logo.png')
LOGO_SQUARE = data_uri('dataforge_logo_square.png')
STOQFLOW = data_uri('stoqflow_logo.png')

BASE_CSS = f"""
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
html, body {{ width: {W}px; height: {H}px; overflow: hidden; }}
body {{
  font-family: {FONT}; color: {WHITE};
  background:
    radial-gradient(1200px 800px at 85% 15%, rgba(43,143,227,.22), transparent 60%),
    radial-gradient(900px 700px at 10% 95%, rgba(46,211,183,.18), transparent 60%),
    linear-gradient(160deg, {NAVY_2}, {NAVY});
  position: relative;
}}
.grad {{ background: linear-gradient(90deg, {TEAL}, {BLUE});
         -webkit-background-clip: text; background-clip: text; color: transparent; }}
.bar {{ position: absolute; left: 0; right: 0; bottom: 0; height: 14px;
        background: linear-gradient(90deg, {TEAL}, {BLUE}); }}
.grid {{ position: absolute; inset: 0; opacity: .07;
  background-image: linear-gradient({WHITE} 1px, transparent 1px),
                    linear-gradient(90deg, {WHITE} 1px, transparent 1px);
  background-size: 80px 80px; }}
.logo {{ position: absolute; left: 120px; top: 96px; height: 92px; }}
.series {{ font-size: 30px; font-weight: 600; letter-spacing: .14em;
           text-transform: uppercase; color: {TEAL}; }}
.foot {{ position: absolute; left: 120px; right: 120px; bottom: 76px;
         display: flex; align-items: center; justify-content: space-between;
         font-family: 'Inter', sans-serif; font-size: 28px; color: {MUTED}; }}
.foot .pair {{ display: flex; align-items: center; gap: 18px; }}
.foot img {{ height: 52px; }}
"""


def page(body, extra_css=''):
    return (f'<!doctype html><html lang="nl"><head><meta charset="utf-8">'
            f'<style>{BASE_CSS}{extra_css}</style></head><body>{body}</body></html>')


def opening_card(number, series, title):
    css = f"""
    .main {{ position: absolute; left: 120px; right: 160px; top: 330px; }}
    .num {{ font-size: 220px; font-weight: 900; line-height: .9; margin: 26px 0 18px; }}
    .title {{ font-size: 88px; font-weight: 800; line-height: 1.08; max-width: 1500px; }}
    """
    body = f"""
    <div class="grid"></div>
    <img class="logo" src="{LOGO}">
    <div class="main">
      <div class="series">{html.escape(SERIES[series])}</div>
      <div class="num grad">{number}</div>
      <div class="title">{html.escape(title)}</div>
    </div>
    <div class="foot">
      <div class="pair"><img src="{STOQFLOW}"><span>Koppeling Stoqflow by Data Forge</span></div>
      <span>www.data-forge.be</span>
    </div>
    <div class="bar"></div>
    """
    return page(body, css)


def end_card(number, next_video):
    css = f"""
    .main {{ position: absolute; left: 120px; top: 300px; right: 760px; }}
    .label {{ font-size: 34px; font-weight: 600; letter-spacing: .14em;
              text-transform: uppercase; color: {TEAL}; margin-bottom: 30px; }}
    .next {{ font-size: 80px; font-weight: 800; line-height: 1.1; }}
    .nextnum {{ font-size: 120px; font-weight: 900; line-height: 1; margin-bottom: 12px; }}
    .square {{ position: absolute; right: 150px; top: 230px; width: 520px; }}
    """
    if next_video:
        n_number, _series, n_title = next_video
        main = (f'<div class="label">Volgende video</div>'
                f'<div class="nextnum grad">{n_number}</div>'
                f'<div class="next">{html.escape(n_title)}</div>')
    else:
        main = ('<div class="label">Einde van de reeks</div>'
                '<div class="next">Bedankt voor het kijken.</div>'
                '<div class="next grad" style="margin-top:28px">Vragen? www.data-forge.be</div>')
    body = f"""
    <div class="grid"></div>
    <div class="main">{main}</div>
    <img class="square" src="{LOGO_SQUARE}">
    <div class="foot">
      <div class="pair"><img src="{STOQFLOW}"><span>Koppeling Stoqflow by Data Forge · video {number}</span></div>
      <span>www.data-forge.be</span>
    </div>
    <div class="bar"></div>
    """
    return page(body, css)


def lower_third():
    """Transparent lower-third bar for the 'Tekst in beeld' overlays: the
    editor types the text on top of it."""
    css = f"""
    html, body {{ background: transparent !important; }}
    .lt {{ position: absolute; left: 96px; bottom: 120px; width: 1100px; height: 120px;
           background: rgba(14,27,44,.88); border-radius: 14px; overflow: hidden; }}
    .lt::before {{ content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 14px;
                   background: linear-gradient(180deg, {TEAL}, {BLUE}); }}
    .lt img {{ position: absolute; right: 28px; top: 34px; height: 52px; opacity: .9; }}
    """
    body = f'<div class="lt"><img src="{LOGO}"></div>'
    return (f'<!doctype html><html><head><meta charset="utf-8"><style>{css}</style></head>'
            f'<body style="background:transparent">{body}</body></html>')


def render(doc, png_path, transparent=False):
    with tempfile.NamedTemporaryFile('w', suffix='.html', delete=False, encoding='utf-8') as f:
        f.write(doc)
        src = f.name
    try:
        cmd = [CHROME, '--headless', '--no-sandbox', '--disable-gpu', '--hide-scrollbars',
               '--force-device-scale-factor=1', f'--window-size={W},{H}',
               f'--screenshot={png_path}']
        if transparent:
            cmd.append('--default-background-color=00000000')
        cmd.append('file://' + src)
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    finally:
        os.unlink(src)


def to_clip(png_path, mp4_path):
    fade_out = CLIP_SECONDS - 0.6
    subprocess.run([
        FFMPEG, '-y', '-loglevel', 'error', '-loop', '1', '-framerate', '30', '-i', png_path,
        '-t', str(CLIP_SECONDS),
        '-vf', f'fade=t=in:st=0:d=0.6,fade=t=out:st={fade_out}:d=0.6,format=yuv420p',
        '-c:v', 'libx264', '-preset', 'slow', '-crf', '20', '-movflags', '+faststart', mp4_path,
    ], check=True)


def main():
    os.makedirs(OUT, exist_ok=True)
    for i, (number, series, title) in enumerate(VIDEOS):
        nxt = VIDEOS[i + 1] if i + 1 < len(VIDEOS) else None
        for kind, doc in (('open', opening_card(number, series, title)),
                          ('eind', end_card(number, nxt))):
            jpg = os.path.join(OUT, f'{number}_{kind}.jpg')
            with tempfile.TemporaryDirectory() as tmp:
                png = os.path.join(tmp, 'card.png')
                render(doc, png)
                Image.open(png).convert('RGB').save(jpg, quality=92, subsampling=0)
                if FFMPEG:
                    to_clip(png, jpg[:-4] + '.mp4')
            print('wrote', os.path.relpath(jpg, ROOT))
    render(lower_third(), os.path.join(OUT, 'ondertitel_balk.png'), transparent=True)
    print('wrote cards/ondertitel_balk.png')
    if not FFMPEG:
        print('ffmpeg not found: JPG cards written, MP4 clips skipped')


if __name__ == '__main__':
    main()
