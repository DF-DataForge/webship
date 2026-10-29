#!/usr/bin/env python3
"""Generate the illustrations of the Woody's Skate Supply demo.

Every image is drawn as SVG (flat "sticker" style: thick ink outlines,
off-white background, brand colours) and rendered to JPEG with headless Chromium.

    python3 tools/make_images.py [path/to/chromium-headless-shell]

Writes static/img/*.jpg (and *.png for the logo) next to this tools folder.
"""
import io
import math
import os
import random
import subprocess
import sys
import tempfile

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '..', 'static', 'img')
CHROME = (sys.argv[1] if len(sys.argv) > 1
          else '/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell')

# Brand palette, taken from the Woody's logo
INK = '#0B1A7A'     # navy outline
BONE = '#F2F6FB'    # cool off-white background
CYAN = '#00EEDD'
BLUE = '#0A6CFF'
SUN = '#FFD23F'     # warm pop colour, used sparingly
VIOLET = '#7B5CFF'
MAPLE = '#E9C58F'
FONT = "'Inter Display', 'Inter', 'DejaVu Sans', sans-serif"
SW = 9  # outline stroke width


def svg(width, height, body, bg=BONE):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}"><rect width="100%" height="100%" fill="{bg}"/>{body}</svg>')


def stroke(fill, width=SW):
    return (f'fill="{fill}" stroke="{INK}" stroke-width="{width}" '
            f'stroke-linejoin="round" stroke-linecap="round"')


def blob(cx, cy, r, color, seed=1):
    """Organic background blob."""
    rnd = random.Random(seed)
    pts = []
    n = 9
    for i in range(n):
        a = 2 * math.pi * i / n
        rr = r * (0.86 + rnd.random() * 0.22)
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    d = f'M{pts[0][0]:.0f},{pts[0][1]:.0f} '
    for i in range(n):
        p0, p1 = pts[i], pts[(i + 1) % n]
        mx, my = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
        d += f'Q{p0[0]:.0f},{p0[1]:.0f} {mx:.0f},{my:.0f} '
    return f'<path d="{d}Z" fill="{color}"/>'


def sparkles(color=INK, seed=3, n=6, area=(80, 80, 920, 920)):
    rnd = random.Random(seed)
    out = ''
    for _ in range(n):
        x = rnd.uniform(area[0], area[2])
        y = rnd.uniform(area[1], area[3])
        s = rnd.uniform(14, 26)
        out += (f'<path d="M{x},{y - s} L{x + s * .25},{y - s * .25} L{x + s},{y} '
                f'L{x + s * .25},{y + s * .25} L{x},{y + s} L{x - s * .25},{y + s * .25} '
                f'L{x - s},{y} L{x - s * .25},{y - s * .25}Z" fill="{color}"/>')
    return out


def shadow(cx, cy, rx, ry=None):
    return f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry or rx * 0.12}" fill="{INK}" opacity="0.12"/>'


def badge(x, y, r, text, fill=CYAN, size=None):
    size = size or r * 0.55
    return (f'<circle cx="{x}" cy="{y}" r="{r}" {stroke(fill, 6)}/>'
            f'<text x="{x}" y="{y + size * 0.36}" font-family="{FONT}" font-weight="900" '
            f'font-size="{size}" text-anchor="middle" fill="{INK}">{text}</text>')


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------

def tee(color, print_color, accent):
    body = ('M330,250 Q500,300 670,250 L830,330 L770,470 L700,440 L700,800 '
            'Q500,830 300,800 L300,440 L230,470 L170,330 Z')
    collar = 'M410,262 Q500,330 590,262'
    return (blob(500, 520, 380, accent, 2) + shadow(500, 850, 260)
            + f'<path d="{body}" {stroke(color)}/>'
            + f'<path d="{collar}" fill="none" stroke="{INK}" stroke-width="{SW}" stroke-linecap="round"/>'
            + f'<path d="M300,440 L300,470 M700,440 L700,470" stroke="{INK}" stroke-width="6"/>'
            + f'<text x="500" y="560" font-family="{FONT}" font-weight="900" font-size="74" '
              f'text-anchor="middle" fill="{print_color}" letter-spacing="-2">WOODY\'S</text>'
            + f'<text x="500" y="610" font-family="{FONT}" font-weight="700" font-size="26" '
              f'text-anchor="middle" fill="{print_color}" letter-spacing="8">SKATE SUPPLY</text>'
            + sparkles(INK, 5, 4))


def hoodie(color, print_color, accent):
    body = ('M350,260 Q500,215 650,260 L790,330 Q850,520 830,760 L740,770 L730,520 '
            'L700,560 L700,820 Q500,850 300,820 L300,560 L270,520 L260,770 L170,760 '
            'Q150,520 210,330 Z')
    hood = 'M370,265 Q380,150 500,145 Q620,150 630,265 Q560,330 500,330 Q440,330 370,265 Z'
    pocket = 'M380,650 L620,650 L660,780 L340,780 Z'
    return (blob(500, 520, 390, accent, 4) + shadow(500, 860, 290)
            + f'<path d="{body}" {stroke(color)}/>'
            + f'<path d="{hood}" {stroke(color)}/>'
            + f'<path d="M455,320 L450,430 M545,320 L550,430" stroke="{BONE}" stroke-width="8" stroke-linecap="round"/>'
            + f'<circle cx="450" cy="438" r="9" fill="{BONE}"/><circle cx="550" cy="438" r="9" fill="{BONE}"/>'
            + f'<path d="{pocket}" fill="none" stroke="{INK}" stroke-width="7" stroke-linejoin="round" opacity="0.9"/>'
            + f'<path d="{pocket}" fill="{INK}" opacity="0.12"/>'
            + f'<text x="500" y="560" font-family="{FONT}" font-weight="900" font-size="62" '
              f'text-anchor="middle" fill="{print_color}" letter-spacing="-1">KICKFLIP</text>'
            + sparkles(INK, 9, 4))


def beanie():
    dome = 'M260,600 Q260,250 500,240 Q740,250 740,600 Z'
    cuff = 'M230,590 L770,590 L760,760 Q500,790 240,760 Z'
    ribs = ''.join(f'<path d="M{x},600 L{x - 2},760" stroke="{INK}" stroke-width="4" opacity="0.35"/>'
                   for x in range(275, 760, 34))
    return (blob(500, 520, 380, CYAN, 6) + shadow(500, 840, 280)
            + f'<circle cx="500" cy="215" r="58" {stroke(BLUE)}/>'
            + f'<path d="{dome}" {stroke(BLUE)}/>'
            + f'<path d="M330,420 Q500,380 670,420" fill="none" stroke="{INK}" stroke-width="5" opacity="0.3"/>'
            + f'<path d="{cuff}" {stroke(BLUE)}/>' + ribs
            + f'<rect x="420" y="630" width="160" height="80" rx="8" {stroke(INK, 5)}/>'
            + f'<text x="500" y="684" font-family="{FONT}" font-weight="900" font-size="40" '
              f'text-anchor="middle" fill="{CYAN}">WSS</text>'
            + sparkles(INK, 11, 5))


def sock(x, y, rot, main, stripe):
    shape = ('M0,0 L150,0 L150,330 Q150,420 230,440 L300,455 Q360,470 350,530 '
             'Q340,590 270,580 L60,560 Q0,550 0,470 Z')
    return (f'<g transform="translate({x},{y}) rotate({rot})">'
            f'<path d="{shape}" {stroke(main)}/>'
            f'<rect x="0" y="0" width="150" height="70" {stroke(BONE, 7)}/>'
            f'<rect x="0" y="100" width="150" height="28" fill="{stripe}" stroke="{INK}" stroke-width="6"/>'
            f'<rect x="0" y="150" width="150" height="28" fill="{stripe}" stroke="{INK}" stroke-width="6"/>'
            f'<path d="M270,580 Q300,520 350,530" fill="{stripe}" stroke="{INK}" stroke-width="6"/>'
            f'</g>')


def socks():
    return (blob(500, 520, 380, SUN, 8) + shadow(500, 860, 270)
            + sock(250, 180, -8, BONE, BLUE) + sock(400, 230, 6, BONE, INK)
            + sparkles(INK, 13, 5))


def deck_shape(w, h):
    r = w / 2
    return (f'M{-w / 2},{-h / 2 + r} Q{-w / 2},{-h / 2} 0,{-h / 2} Q{w / 2},{-h / 2} {w / 2},{-h / 2 + r} '
            f'L{w / 2},{h / 2 - r} Q{w / 2},{h / 2} 0,{h / 2} Q{-w / 2},{h / 2} {-w / 2},{h / 2 - r} Z')


def deck_graphic(w, h, colors):
    """Bottom graphic of a deck, centred on 0,0."""
    c1, c2, c3 = colors
    clip_id = f'clip{abs(hash((w, h, colors))) % 100000}'
    return (f'<clipPath id="{clip_id}"><path d="{deck_shape(w, h)}"/></clipPath>'
            f'<g clip-path="url(#{clip_id})">'
            f'<rect x="{-w}" y="{-h}" width="{2 * w}" height="{2 * h}" fill="{c1}"/>'
            f'<circle cx="0" cy="{-h * 0.18}" r="{w * 0.62}" fill="{c2}"/>'
            f'<path d="M{-w},{h * 0.08} L{w},{h * 0.02} L{w},{h * 0.12} L{-w},{h * 0.18} Z" fill="{c3}"/>'
            f'<path d="M{-w},{h * 0.24} L{w},{h * 0.18} L{w},{h * 0.24} L{-w},{h * 0.30} Z" fill="{c3}"/>'
            f'<text x="0" y="{-h * 0.10}" font-family="{FONT}" font-weight="900" font-size="{w * 0.95}" '
            f'text-anchor="middle" fill="{INK}">W</text>'
            f'<text x="0" y="{h * 0.40}" font-family="{FONT}" font-weight="900" font-size="{w * 0.17}" '
            f'text-anchor="middle" fill="{c2}" letter-spacing="3">WOODY\'S</text>'
            f'</g><path d="{deck_shape(w, h)}" fill="none" stroke="{INK}" stroke-width="{SW}"/>')


def deck_top(w, h):
    grain = ''.join(f'<path d="M{x},{-h / 2 + 30} Q{x + 8},0 {x},{h / 2 - 30}" fill="none" '
                    f'stroke="#B98A4E" stroke-width="3" opacity="0.6"/>'
                    for x in range(int(-w / 2) + 18, int(w / 2) - 10, 22))
    return f'<path d="{deck_shape(w, h)}" {stroke(MAPLE)}/>' + grain


def deck_product(colors, wide=False, accent=CYAN):
    w, h = (230, 760) if wide else (210, 760)
    return (blob(500, 500, 400, accent, 14) + shadow(520, 900, 260)
            + f'<g transform="translate(400,500) rotate(-14)">{deck_top(w, h)}</g>'
            + f'<g transform="translate(590,490) rotate(10)">{deck_graphic(w, h, colors)}</g>'
            + sparkles(INK, 15, 4))


def truck(x, y, scale, metal, rot=0):
    return (f'<g transform="translate({x},{y}) rotate({rot}) scale({scale})">'
            f'<rect x="-230" y="-22" width="460" height="44" rx="22" {stroke("#9AA0A8")}/>'
            f'<path d="M-170,-10 L170,-10 L120,90 Q0,130 -120,90 Z" {stroke(metal)}/>'
            f'<rect x="-70" y="80" width="140" height="70" rx="12" {stroke(BLUE)}/>'
            f'<path d="M-110,150 L110,150 L130,200 L-130,200 Z" {stroke(metal)}/>'
            f'<circle cx="0" cy="40" r="16" fill="{INK}"/>'
            f'</g>')


def trucks_product(metal, accent):
    return (blob(500, 500, 380, accent, 17) + shadow(500, 860, 280)
            + truck(500, 330, 1.0, metal) + truck(500, 640, 1.0, metal)
            + sparkles(INK, 19, 4))


def wheel(x, y, r, color, core=BONE, label=''):
    out = (f'<circle cx="{x}" cy="{y}" r="{r}" {stroke(color)}/>'
           f'<circle cx="{x}" cy="{y}" r="{r * 0.55}" fill="none" stroke="{INK}" stroke-width="5" opacity="0.35"/>'
           f'<circle cx="{x}" cy="{y}" r="{r * 0.32}" {stroke(core, 6)}/>'
           f'<circle cx="{x}" cy="{y}" r="{r * 0.1}" fill="{INK}"/>')
    if label:
        out += (f'<text x="{x}" y="{y - r * 0.62}" font-family="{FONT}" font-weight="900" '
                f'font-size="{r * 0.2}" text-anchor="middle" fill="{INK}">{label}</text>')
    return out


def wheels_product(color, accent, label):
    pos = [(360, 360), (640, 360), (360, 640), (640, 640)]
    return (blob(500, 500, 400, accent, 21) + shadow(500, 860, 280)
            + ''.join(wheel(x, y, 125, color, label=label) for x, y in pos)
            + sparkles(INK, 23, 3))


def bearing(x, y, r):
    balls = ''.join(
        f'<circle cx="{x + r * 0.68 * math.cos(a):.1f}" cy="{y + r * 0.68 * math.sin(a):.1f}" '
        f'r="{r * 0.14:.1f}" fill="{INK}"/>'
        for a in [2 * math.pi * i / 7 for i in range(7)])
    return (f'<circle cx="{x}" cy="{y}" r="{r}" {stroke("#C9CCD1", 7)}/>'
            f'<circle cx="{x}" cy="{y}" r="{r * 0.82}" fill="{BLUE}" stroke="{INK}" stroke-width="5"/>'
            + balls
            + f'<circle cx="{x}" cy="{y}" r="{r * 0.45}" {stroke("#C9CCD1", 6)}/>'
            f'<circle cx="{x}" cy="{y}" r="{r * 0.22}" fill="{BONE}" stroke="{INK}" stroke-width="5"/>')


def bearings_product():
    pos = [(260 + 160 * (i % 4), 410 + 180 * (i // 4)) for i in range(8)]
    return (blob(500, 500, 380, CYAN, 25) + shadow(500, 820, 300)
            + ''.join(bearing(x, y, 72) for x, y in pos)
            + f'<text x="500" y="250" font-family="{FONT}" font-weight="900" font-size="64" '
              f'text-anchor="middle" fill="{INK}">ABEC-7</text>')


def grip_product():
    rnd = random.Random(27)
    grit = ''.join(f'<circle cx="{rnd.uniform(290, 710):.0f}" cy="{rnd.uniform(160, 860):.0f}" '
                   f'r="{rnd.uniform(1.5, 3.5):.1f}" fill="#555"/>' for _ in range(350))
    return (blob(500, 500, 400, BLUE, 29) + shadow(500, 900, 260)
            + f'<g transform="rotate(-8 500 500)">'
            f'<path d="M280,150 L720,150 L720,700 L600,870 L280,870 Z" {stroke("#262626")}/>'
            + grit
            + f'<path d="M720,700 L600,870 Q640,720 720,700 Z" {stroke(BONE, 7)}/>'
            f'<text x="500" y="520" font-family="{FONT}" font-weight="900" font-size="80" '
            f'text-anchor="middle" fill="{CYAN}" transform="rotate(-90 500 500)">GRIP</text></g>'
            + sparkles(INK, 31, 4))


def bolt(x, y, rot):
    return (f'<g transform="translate({x},{y}) rotate({rot})">'
            f'<rect x="-14" y="0" width="28" height="170" rx="6" {stroke("#C9CCD1", 6)}/>'
            + ''.join(f'<path d="M-14,{t} L14,{t + 8}" stroke="{INK}" stroke-width="3"/>'
                      for t in range(40, 165, 16))
            + f'<path d="M-42,0 Q0,-44 42,0 Z" {stroke("#C9CCD1", 6)}/>'
            f'</g>')


def nut(x, y):
    pts = ' '.join(f'{x + 34 * math.cos(math.pi / 3 * i):.0f},{y + 34 * math.sin(math.pi / 3 * i):.0f}'
                   for i in range(6))
    return (f'<polygon points="{pts}" {stroke(CYAN, 6)}/>'
            f'<circle cx="{x}" cy="{y}" r="14" fill="{BONE}" stroke="{INK}" stroke-width="5"/>')


def hardware_product():
    bolts = ''.join(bolt(250 + 72 * i, 260 + (i % 2) * 30, -8 + (i % 3) * 8) for i in range(8))
    nuts = ''.join(nut(250 + 72 * i, 640 + (i % 2) * 50) for i in range(8))
    return blob(500, 500, 400, SUN, 33) + shadow(500, 820, 300) + bolts + nuts


def complete(colors, wheel_color, metal='#C9CCD1', wide=False, rot=-32):
    w, h = (230, 760) if wide else (210, 760)
    wr = 52 if wide else 46
    axle = w / 2 + wr * 0.6
    wheels = ''.join(wheel(sx * axle, sy * (h / 2 - 150), wr, wheel_color)
                     for sx in (-1, 1) for sy in (-1, 1))
    trucks_ = ''.join(f'<rect x="{-axle}" y="{sy * (h / 2 - 150) - 14}" width="{2 * axle}" height="28" '
                      f'rx="14" {stroke(metal, 7)}/>' for sy in (-1, 1))
    return (f'<g transform="rotate({rot})">{trucks_}{wheels}{deck_graphic(w, h, colors)}</g>')


def complete_product(colors, wheel_color, accent, wide=False):
    return (blob(500, 500, 400, accent, 35) + shadow(500, 880, 300)
            + f'<g transform="translate(500,490)">{complete(colors, wheel_color, wide=wide)}</g>'
            + sparkles(INK, 37, 5))


# ---------------------------------------------------------------------------
# Website imagery
# ---------------------------------------------------------------------------

def hero():
    rnd = random.Random(41)
    stars = ''.join(f'<circle cx="{rnd.uniform(0, 1920):.0f}" cy="{rnd.uniform(0, 640):.0f}" '
                    f'r="{rnd.uniform(1, 3):.1f}" fill="{BONE}" opacity="{rnd.uniform(.2, .6):.2f}"/>'
                    for _ in range(90))
    ramp = (f'<path d="M980,1000 L980,620 Q1300,640 1420,1000 Z" fill="{BLUE}" stroke="{INK}" stroke-width="10"/>'
            f'<path d="M1560,1000 Q1680,640 2000,620 L2000,1000 Z" fill="{BLUE}" stroke="{INK}" stroke-width="10"/>'
            f'<rect x="960" y="604" width="40" height="22" fill="#C9CCD1" stroke="{INK}" stroke-width="6"/>')
    speed = ''.join(f'<path d="M{1190 - i * 40},{360 + i * 46} L{1390 - i * 40},{300 + i * 46}" '
                    f'stroke="{CYAN}" stroke-width="10" stroke-linecap="round" opacity="{.9 - i * .15:.2f}"/>'
                    for i in range(5))
    board = (f'<g transform="translate(1480,330) scale(0.62)">'
             f'{complete((BLUE, CYAN, INK), BONE, rot=58)}</g>')
    return svg(1920, 1000,
               stars
               + f'<circle cx="1500" cy="380" r="300" fill="{CYAN}"/>'
               + f'<circle cx="1500" cy="380" r="300" fill="none" stroke="{INK}" stroke-width="10"/>'
               + ''.join(f'<rect x="1150" y="{420 + i * 46}" width="700" height="{12 + i * 3}" fill="{INK}"/>'
                         for i in range(6))
               + ramp + speed + board
               + f'<rect x="0" y="960" width="1920" height="40" fill="{INK}"/>',
               bg='#081257')


def banner(content, bg, accent, seed):
    return svg(1200, 800, blob(600, 400, 420, accent, seed) + content, bg=bg)


def clothing_banner():
    return banner(
        f'<g transform="translate(70,40) scale(0.72)">{tee(INK, CYAN, "none")}</g>'
        f'<g transform="translate(470,80) scale(0.72)">{hoodie("#2F5D3A", BONE, "none")}</g>',
        BONE, SUN, 43)


def completes_banner():
    return banner(
        f'<g transform="translate(400,400) scale(0.82)">{complete((BLUE, CYAN, INK), BONE, rot=-62)}</g>'
        f'<g transform="translate(800,420) scale(0.82)">{complete((VIOLET, SUN, INK), BLUE, wide=True, rot=-48)}</g>',
        BONE, CYAN, 45)


def workshop_flatlay():
    """Knolling of all parts that go into a complete."""
    body = (f'<g transform="translate(300,400) rotate(90) scale(0.72)">{deck_top(210, 760)}</g>'
            f'<g transform="translate(300,620) rotate(90) scale(0.72)">{deck_graphic(210, 760, (BLUE, CYAN, INK))}</g>'
            + truck(760, 250, 0.55, '#C9CCD1') + truck(1000, 250, 0.55, '#C9CCD1')
            + ''.join(wheel(700 + 95 * i, 470, 42, BONE) for i in range(4))
            + ''.join(bearing(690 + 70 * i, 590, 30) for i in range(5))
            + ''.join(bolt(700 + 44 * i, 650, 0).replace('scale', 'scale') for i in range(0))
            + ''.join(f'<g transform="translate({1040 + 26 * i},560) scale(0.45)">{bolt(0, 0, 0)}</g>'
                      for i in range(5))
            + ''.join(nut(700 + 75 * i, 700) for i in range(6)))
    return svg(1200, 800, body, bg=BLUE)


def shipping():
    box = (f'<path d="M380,330 L600,250 L820,330 L820,610 L600,690 L380,610 Z" {stroke(MAPLE)}/>'
           f'<path d="M380,330 L600,410 L820,330" fill="none" stroke="{INK}" stroke-width="{SW}"/>'
           f'<path d="M600,410 L600,690" stroke="{INK}" stroke-width="{SW}"/>'
           f'<path d="M490,290 L710,370 L710,440 L490,360 Z" fill="{CYAN}" stroke="{INK}" stroke-width="6"/>'
           f'<path d="M640,470 L780,420 L780,520 L640,570 Z" {stroke(BONE, 6)}/>'
           f'<text x="710" y="508" font-family="{FONT}" font-weight="900" font-size="34" fill="{INK}" '
           f'transform="rotate(-20 710 508)" text-anchor="middle">WSS</text>')
    lines = ''.join(f'<path d="M{120 + i * 20},{380 + i * 60} L{320 + i * 10},{380 + i * 60}" '
                    f'stroke="{INK}" stroke-width="12" stroke-linecap="round"/>' for i in range(4))
    return svg(1200, 800, blob(600, 470, 380, CYAN, 47) + shadow(600, 720, 260) + box + lines
               + sparkles(INK, 49, 6, (100, 100, 1100, 700)), bg=BONE)


def logo():
    """Vector redraw of the Woody's logo: a skateboard above italic lettering."""
    outline = f'stroke="{INK}" stroke-width="14" stroke-linejoin="round" paint-order="stroke"'
    deck = ('M150,330 Q90,300 130,260 Q170,225 300,240 L1080,90 Q1300,40 1420,90 '
            'Q1500,130 1440,210 Q1380,280 1230,350 L640,520 Q560,540 520,500 Z')
    board = (
        f'<path d="{deck}" fill="{BLUE}" stroke="{INK}" stroke-width="16" stroke-linejoin="round"/>'
        f'<path d="M150,330 Q90,300 130,260 Q170,225 300,240 L1000,105 Q760,260 560,330 '
        f'Q760,330 900,360 L640,470 Q420,440 150,330 Z" fill="{CYAN}" stroke="{INK}" stroke-width="10" '
        f'stroke-linejoin="round"/>'
        f'<path d="M920,300 L1400,170 Q1300,260 1000,330 Z" fill="{INK}" opacity="0.9"/>')
    wheels = (''.join(
            f'<rect x="{x - 60}" y="{y - 70}" width="120" height="140" rx="50" fill="{c}" stroke="{INK}" stroke-width="14"/>'
            f'<ellipse cx="{x + 30}" cy="{y}" rx="34" ry="52" fill="{c2}" stroke="{INK}" stroke-width="12"/>'
            for x, y, c, c2 in [(330, 470, CYAN, CYAN), (530, 545, CYAN, CYAN), (1250, 400, CYAN, BLUE)]))
    text = (f'<g transform="skewX(-14)">'
            f'<text x="300" y="900" font-family="{FONT}" font-weight="900" font-size="300" '
            f'letter-spacing="-6" {outline}><tspan fill="{CYAN}">WOOD</tspan><tspan fill="{BLUE}">Y\'S</tspan></text>'
            f'<text x="420" y="1030" font-family="{FONT}" font-weight="900" font-size="110" '
            f'letter-spacing="34" fill="{BLUE}" stroke="{INK}" stroke-width="10" paint-order="stroke">SKATE SUPPLY</text>'
            f'</g>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="1240" viewBox="0 0 1600 1240">'
            f'{wheels}{board}{text}</svg>')


# ---------------------------------------------------------------------------

def product_images():
    p = lambda body: svg(1000, 1000, body)  # noqa: E731
    return {
        'tee_black': p(tee('#1D1D1D', CYAN, CYAN)),
        'tee_white': p(tee('#FBFBF8', BLUE, BLUE)),
        'hoodie_black': p(hoodie('#1D1D1D', CYAN, BLUE)),
        'hoodie_green': p(hoodie('#2F5D3A', BONE, CYAN)),
        'beanie': p(beanie()),
        'socks': p(socks()),
        'deck_80': p(deck_product((BLUE, CYAN, INK))),
        'deck_825': p(deck_product((VIOLET, SUN, INK), wide=True, accent=BLUE)),
        'truck_139': p(trucks_product('#C9CCD1', CYAN)),
        'truck_149': p(trucks_product('#3A3A3A', SUN)),
        'wheels_53': p(wheels_product('#FBFBF8', BLUE, '53MM')),
        'wheels_56': p(wheels_product(BLUE, CYAN, '56MM')),
        'bearings': p(bearings_product()),
        'grip': p(grip_product()),
        'hardware': p(hardware_product()),
        'complete_street': p(complete_product((BLUE, CYAN, INK), BONE, CYAN)),
        'complete_cruiser': p(complete_product((VIOLET, SUN, INK), BLUE, SUN, wide=True)),
        'hero': hero(),
        'banner_clothing': clothing_banner(),
        'banner_completes': completes_banner(),
        'workshop': workshop_flatlay(),
        'shipping': shipping(),
    }


def render(svg_text, width, height):
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, 'img.html')
        with open(src, 'w') as f:
            f.write('<html><body style="margin:0;background:transparent">' + svg_text + '</body></html>')
        png = os.path.join(tmp, 'out.png')
        subprocess.run([CHROME, '--headless', '--disable-gpu', '--no-sandbox', '--hide-scrollbars',
                        '--default-background-color=00000000',
                        f'--window-size={width},{height}', f'--screenshot={png}', src],
                       check=True, capture_output=True)
        with open(png, 'rb') as f:
            return Image.open(io.BytesIO(f.read())).copy()


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, text in product_images().items():
        width = int(text.split('width="')[1].split('"')[0])
        height = int(text.split('height="')[1].split('"')[0])
        img = render(text, width, height).convert('RGB')
        img.save(os.path.join(OUT, name + '.jpg'), quality=86, optimize=True, progressive=True)
        print(name)
    logo_img = render(logo(), 1600, 1240)
    logo_img = logo_img.crop(logo_img.getbbox())
    logo_img.thumbnail((800, 800))
    logo_img.save(os.path.join(OUT, 'logo.png'), optimize=True)
    print('logo')


if __name__ == '__main__':
    main()
