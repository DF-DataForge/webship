#!/usr/bin/env python3
"""Animated explainer slides (schema's) in the Data Forge house style.

Each slide is an HTML page whose elements appear one after another (CSS
animation delays); the recorder films it like any other scene. Slides never
imitate the Stoqflow application: the 'In Stoqflow' slides show the state of
the order as a neutral card.

    slides.py            writes /opt/rec/slides/<name>.html for every slide in SLIDES
"""
import html
import os

OUT = '/opt/rec/slides'
ASSETS = '/home/user/webship/docs/instructievideos/assets'
STEP = 0.9   # seconds between two elements appearing

CSS = """
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:1920px;height:1080px;overflow:hidden}
body{font-family:'Inter','Inter Display',sans-serif;color:#fff;
 background:radial-gradient(1100px 760px at 88% 12%,rgba(43,143,227,.20),transparent 60%),
 radial-gradient(900px 700px at 8% 96%,rgba(46,211,183,.16),transparent 60%),linear-gradient(160deg,#13263D,#0E1B2C)}
#__rec_cursor{display:none!important}
.grid{position:absolute;inset:0;opacity:.06;background-image:linear-gradient(#fff 1px,transparent 1px),linear-gradient(90deg,#fff 1px,transparent 1px);background-size:80px 80px}
.logo{position:absolute;right:90px;bottom:70px;height:46px;opacity:.9}
.wrap{position:absolute;left:120px;right:120px;top:110px}
.kicker{font:600 28px 'Inter';letter-spacing:.14em;text-transform:uppercase;color:#2ED3B7}
h1{font:800 64px 'Inter Display','Inter';margin:14px 0 54px;line-height:1.1}
.a{opacity:0;animation:up .6s ease-out forwards}
@keyframes up{from{opacity:0;transform:translateY(18px)}to{opacity:1;transform:none}}
.row{display:flex;align-items:center;gap:26px;margin-bottom:46px}
.box{border-radius:18px;padding:24px 30px;min-width:300px;background:rgba(255,255,255,.07);border:2px solid rgba(255,255,255,.18)}
.box .t{font:700 34px 'Inter'}
.box .s{font:500 24px 'Inter';color:#9FB3C8;margin-top:6px}
.box.odoo{border-color:#8E6CA8;background:rgba(142,108,168,.18)}
.box.sf{border-color:#2ED3B7;background:rgba(46,211,183,.14)}
.box.muted{opacity:.55}
.box.loc{border-color:#2B8FE3;background:rgba(43,143,227,.18)}
.arrow{font:700 46px 'Inter';color:#2ED3B7}
.arrow.back{color:#2B8FE3}
.lbl{font:600 26px 'Inter';color:#9FB3C8;min-width:250px}
table{border-collapse:collapse;font:500 30px 'Inter';width:100%}
th{text-align:left;color:#2ED3B7;font-weight:700;padding:14px 22px;border-bottom:2px solid rgba(255,255,255,.25)}
td{padding:16px 22px;border-bottom:1px solid rgba(255,255,255,.12)}
td b{color:#2ED3B7}
.steps{list-style:none;font:500 34px 'Inter'}
.steps li{display:flex;gap:26px;align-items:baseline;margin-bottom:34px}
.steps .n{font:800 34px 'Inter Display';color:#2ED3B7;min-width:52px}
.code{font:500 30px 'DejaVu Sans Mono',monospace;background:rgba(0,0,0,.35);border-radius:16px;padding:30px 36px;line-height:1.6;border:1px solid rgba(255,255,255,.15)}
.code .c{color:#9FB3C8}.code .h{color:#2ED3B7}
.pipe{display:flex;gap:18px;flex-wrap:wrap;align-items:center;margin-bottom:46px}
.pill{border-radius:40px;padding:14px 28px;font:600 28px 'Inter';background:rgba(255,255,255,.08);border:2px solid rgba(255,255,255,.2)}
.pill.on{background:linear-gradient(90deg,#2ED3B7,#2B8FE3);border-color:transparent;color:#0E1B2C}
.card{border-radius:20px;background:rgba(255,255,255,.06);border:2px solid rgba(46,211,183,.5);padding:34px 40px;margin-bottom:34px}
.card .h{font:700 36px 'Inter';margin-bottom:18px}
.card .l{font:500 28px 'Inter';color:#C9D6E3;line-height:1.55}
.tag{display:inline-block;font:700 22px 'Inter';letter-spacing:.08em;text-transform:uppercase;color:#0E1B2C;background:#2ED3B7;border-radius:8px;padding:4px 12px;margin-right:12px;vertical-align:middle}
.note{font:500 28px 'Inter';color:#9FB3C8;margin-top:10px}
"""


class Slide:
    def __init__(self, kicker, title):
        self.kicker, self.title, self.parts, self.n = kicker, title, [], 1

    def _a(self):
        d = self.n * STEP
        self.n += 1
        return f'class="a" style="animation-delay:{d:.2f}s"'

    def flow(self, items, label=None):
        """items: list of (title, sub, kind) or '→' / '←' / '⇄'"""
        out = f'<div class="row">'
        if label:
            out += f'<div class="lbl a" style="animation-delay:{self.n * STEP:.2f}s">{html.escape(label)}</div>'
        for it in items:
            if isinstance(it, str):
                cls = 'arrow back' if it in ('←', '⇠') else 'arrow'
                out += f'<div {self._a().replace("class=\"a\"", f"class=\"a {cls}\"")}>{it}</div>'
            else:
                t, s, kind = (list(it) + ['', ''])[:3]
                out += (f'<div {self._a().replace("class=\"a\"", f"class=\"a box {kind}\"")}>'
                        f'<div class="t">{html.escape(t)}</div>'
                        + (f'<div class="s">{html.escape(s)}</div>' if s else '') + '</div>')
        self.parts.append(out + '</div>')
        return self

    def table(self, header, rows):
        out = '<table><tr>' + ''.join(f'<th>{html.escape(h)}</th>' for h in header) + '</tr>'
        for r in rows:
            out += f'<tr {self._a()}>' + ''.join(f'<td>{c}</td>' for c in r) + '</tr>'
        self.parts.append(out + '</table>')
        return self

    def steps(self, items):
        out = '<ul class="steps">'
        for i, it in enumerate(items, 1):
            out += f'<li {self._a()}><span class="n">{i}</span><span>{it}</span></li>'
        self.parts.append(out + '</ul>')
        return self

    def code(self, lines):
        self.parts.append(f'<div {self._a().replace("class=\"a\"", "class=\"a code\"")}>' + '<br>'.join(lines) + '</div>')
        return self

    def pipeline(self, states, upto=None):
        out = '<div class="pipe">'
        for i, s in enumerate(states):
            on = upto is not None and i <= upto
            out += (f'<div {self._a().replace("class=\"a\"", "class=\"a pill" + (" on" if on else "") + "\"")}>'
                    f'{html.escape(s)}</div>')
            if i < len(states) - 1:
                out += f'<div {self._a().replace("class=\"a\"", "class=\"a arrow\"")} >→</div>'
        self.parts.append(out + '</div>')
        return self

    def card(self, head, lines, tag=None):
        t = f'<span class="tag">{html.escape(tag)}</span>' if tag else ''
        body = '<br>'.join(lines)
        self.parts.append(f'<div {self._a().replace("class=\"a\"", "class=\"a card\"")}>'
                          f'<div class="h">{t}{html.escape(head)}</div><div class="l">{body}</div></div>')
        return self

    def note(self, text):
        self.parts.append(f'<div {self._a().replace("class=\"a\"", "class=\"a note\"")}>{text}</div>')
        return self

    def raw(self, markup):
        self.parts.append(f'<div {self._a()}>{markup}</div>')
        return self

    def html(self):
        logo = os.path.join(ASSETS, 'dataforge_logo.png')
        return (f'<!doctype html><html lang="nl"><head><meta charset="utf-8"><style>{CSS}</style></head><body>'
                f'<div class="grid"></div><div class="wrap"><div class="kicker">{html.escape(self.kicker)}</div>'
                f'<h1>{html.escape(self.title)}</h1>{"".join(self.parts)}</div>'
                f'<img class="logo" src="file://{logo}"></body></html>')

    @property
    def length(self):
        """Seconds until the last element has appeared."""
        return self.n * STEP + 0.6


SLIDES = {}


def slide(name, kicker, title):
    s = Slide(kicker, title)
    SLIDES[name] = s
    return s


def write_all():
    os.makedirs(OUT, exist_ok=True)
    for name, s in SLIDES.items():
        with open(os.path.join(OUT, name + '.html'), 'w', encoding='utf-8') as f:
            f.write(s.html())
    return {name: s.length for name, s in SLIDES.items()}
