#!/usr/bin/env python3
"""Render an 'In Stoqflow' slide from the live state of the mock.

    live_slide.py order|po REF OUT.html [--still]

Shows the Stoqflow document as a neutral Data Forge card (never a copy of the
Stoqflow app): number, customer or supplier, lines with picked/received
quantities, the status pipeline and parcels. --still renders without the
appear animation (used for the later states of the same scene).
"""
import html
import json
import sys
import urllib.request
from urllib.parse import quote

sys.path.insert(0, '/opt/rec')
from slides import CSS, ASSETS  # noqa: E402

ORDER = [('ready-to-pick', 'Klaar om te picken'), ('picking', 'Picken'), ('packing', 'Inpakken'),
         ('ready-to-ship', 'Klaar om te verzenden'), ('completed', 'Voltooid')]
PO = [('ordered', 'Besteld'), ('in-transit', 'Onderweg'), ('delivered', 'Geleverd'),
      ('unpacking', 'Uitpakken'), ('completed', 'Voltooid')]
OTHER = {'cancelled': 'Geannuleerd', 'on-hold': 'Gepauzeerd', 'concept': 'Concept'}


def get(path):
    with urllib.request.urlopen('http://127.0.0.1:8099' + path) as r:
        return json.load(r)


def main():
    kind, ref, out = sys.argv[1:4]
    still = '--still' in sys.argv
    doc = get('/show/%s/%s' % ('orders' if kind == 'order' else 'purchase-orders', quote(ref, safe='')))
    states = ORDER if kind == 'order' else PO
    keys = [k for k, _ in states]
    cur = doc.get('status')
    idx = keys.index(cur) if cur in keys else -1
    if kind == 'order':
        ci = doc.get('client_info') or {}
        who = ci.get('name') or ' '.join(filter(None, [ci.get('first_name'), ci.get('last_name')])) or ci.get('company') or ''
        who_line = 'Klant: <b>%s</b>' % html.escape(who) if who else ''
        ref_line = 'Referentie Odoo: <b>%s</b>' % html.escape(str((doc.get('origin') or {}).get('number', '')))
        lines = ['%d × %s <span style="color:#9FB3C8">(%s)</span> — gepickt: <b>%d</b>' % (
            it['quantity'], html.escape(it.get('name') or ''), html.escape(it.get('sku') or ''), it.get('picked', 0))
            for it in doc.get('order_items', [])]
        title = 'Order %s' % doc.get('order_number')
    else:
        who_line = 'Leveranciersreferentie: <b>%s</b>' % html.escape(doc.get('supplier_reference') or '')
        ref_line = ''
        lines = ['%d × %s <span style="color:#9FB3C8">(%s)</span> — ontvangen: <b>%d</b>' % (
            it['quantity'], html.escape(it.get('name') or ''), html.escape(it.get('sku') or ''), it.get('received', 0))
            for it in doc.get('order_items', [])]
        title = 'Inkooporder %s' % doc.get('order_number')
    parcels = doc.get('parcels') or []
    parcel_html = ''
    if parcels:
        parcel_html = '<div class="card"><div class="h"><span class="tag">Pakket</span>%s</div><div class="l">%s</div></div>' % (
            html.escape(str(parcels[-1].get('courier') or parcels[-1].get('carrier') or '')),
            'Tracking: <b>%s</b>' % html.escape(str(parcels[-1].get('tracking_number') or parcels[-1].get('tracking_code') or '')))
    pills = []
    for i, (k, label) in enumerate(states):
        on = i <= idx
        pills.append('<div class="pill%s">%s</div>' % (' on' if on else '', html.escape(label)))
    pipe = '<div class="arrow">→</div>'.join(pills)
    if cur in OTHER:
        pipe = '<div class="pill on">%s</div>' % OTHER[cur]
    anim = '' if still else ' a'
    body = (f'<div class="card{anim}" style="animation-delay:.4s"><div class="h"><span class="tag">In Stoqflow</span>{html.escape(title)}</div>'
            f'<div class="l">{who_line}<br>{ref_line}<br><br>' + '<br>'.join(lines) + '</div></div>'
            f'<div class="pipe{anim}" style="animation-delay:1.2s">{pipe}</div>{parcel_html}')
    css = CSS + ('.a{opacity:1!important;animation:none!important}' if still else '')
    page = (f'<!doctype html><html lang="nl"><head><meta charset="utf-8"><style>{css}</style></head><body>'
            f'<div class="grid"></div><div class="wrap"><div class="kicker">Het magazijn</div>'
            f'<h1>Wat er in Stoqflow gebeurt</h1>{body}</div>'
            f'<img class="logo" src="file://{ASSETS}/dataforge_logo.png"></body></html>')
    open(out, 'w', encoding='utf-8').write(page)


if __name__ == '__main__':
    main()
