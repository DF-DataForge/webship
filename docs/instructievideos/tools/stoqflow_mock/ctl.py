#!/usr/bin/env python3
"""Play the Stoqflow warehouse against the running mock (control API on
http://127.0.0.1:8099). Every change updates the record's 'edited' timestamp,
so Odoo's incremental status update picks it up.

References (REF) may be: the Stoqflow _id, the Stoqflow number (OR10041,
PO00028), the Odoo sale order name (S00004) for orders, or the Odoo picking
name / supplier_reference for purchase orders (SQF/IN/00002).

Examples
  ctl.py list orders                      # also: purchase-orders products clients suppliers inventory couriers stock
  ctl.py show order S00004
  ctl.py order advance S00004             # one step: ready-to-pick -> picking -> packing -> ready-to-ship -> completed
  ctl.py order advance S00004 --to packing --qty WSS-SOCKS=20
  ctl.py order ship S00003                # all the way to completed, full quantities, parcel with tracking
  ctl.py order ship S00004 --qty WSS-SOCKS=20 --courier postnl --backorder
  ctl.py order backorder S00004           # child order (parent_order_id) with the not-picked remainder
  ctl.py order parcel S00009 --courier dpd --tracking 05212345678901
  ctl.py order status S00008 on-hold
  ctl.py po advance SQF/IN/00002          # ordered -> in-transit -> delivered -> unpacking -> completed
  ctl.py po receive SQF/IN/00002          # receive everything, completed
  ctl.py po receive SQF/IN/00002 --qty WSS-SOCKS=200 --qty WSS-TEE-BLK-M=0 --backorder
  ctl.py po receive SQF/IN/00005 --zero   # completed, nothing received
  ctl.py retour S00004 --qty WSS-BEANIE=2 # retour PO 'Retour S00004', status delivered
  ctl.py stock WSS-SOCKS 110
  ctl.py touch order S00003
  ctl.py reset
"""
import argparse
import json
import sys
import urllib.error
import urllib.request
from urllib.parse import quote

BASE = 'http://127.0.0.1:8099'
KIND = {'order': 'orders', 'orders': 'orders', 'po': 'purchase-orders',
        'purchase-order': 'purchase-orders', 'purchase-orders': 'purchase-orders'}


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    path = '/'.join(quote(seg, safe='') for seg in path.split('|'))
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        sys.exit('ERROR %s: %s' % (e.code, e.read().decode()))
    except urllib.error.URLError as e:
        sys.exit('mock not reachable on %s: %s' % (BASE, e))


def qmap(pairs):
    out = {}
    for p in pairs or []:
        sku, _, n = p.partition('=')
        if not n:
            sys.exit('--qty expects SKU=QTY, got %r' % p)
        out[sku.strip()] = int(n)
    return out


def out(data):
    print(json.dumps(data, indent=2, ensure_ascii=False))


def print_list(kind, rows):
    if kind == 'orders':
        for o in rows:
            items = ', '.join('%s %s/%s' % (i['sku'], i.get('picked', 0), i['quantity']) for i in o['order_items'])
            print('%-11s %-24s %-13s origin=%-8s parent=%-24s %s  [%s] edited=%s' % (
                o['order_number'], o['_id'], o['status'], (o.get('origin') or {}).get('number', '-'),
                o.get('parent_order_id') or '-', (o.get('client_info') or {}).get('name', ''), items, o['edited']))
    elif kind == 'purchase-orders':
        for o in rows:
            items = ', '.join('%s %s/%s' % (i['sku'], i.get('received', 0), i['quantity']) for i in o['order_items'])
            print('%-11s %-24s %-10s ref=%-28s [%s] edited=%s' % (
                o['order_number'], o['_id'], o['status'], o.get('supplier_reference') or '-', items, o['edited']))
    elif kind == 'products':
        for p in rows:
            print('%-24s %-22s %-36s stock=%s' % (p['_id'], p['sku'], p.get('name'),
                                                  (p.get('product_items') or [{}])[0].get('quantity')))
    elif kind == 'inventory':
        for i in rows:
            print('%-22s total=%-5s reserved=%-5s available=%s' % (i['sku'], i['total'], i['reserved'], i['available']))
    elif kind in ('clients', 'suppliers'):
        for c in rows:
            print('%-24s %-8s %-32s %-32s vat=%s' % (c['_id'], c.get('client_number') or c.get('supplier_number'),
                                                    c.get('name'), c.get('email') or '-', c.get('vat') or '-'))
    else:
        out(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)

    p = sub.add_parser('list', help='list objects')
    p.add_argument('kind', choices=['orders', 'purchase-orders', 'po', 'products', 'clients', 'suppliers',
                                    'inventory', 'couriers', 'warehouses', 'company', 'stock'])
    p.add_argument('--json', action='store_true')

    p = sub.add_parser('show', help='show one order / purchase order as JSON')
    p.add_argument('kind', choices=list(KIND))
    p.add_argument('ref')

    def warehouse_opts(p, order):
        p.add_argument('--qty', action='append', metavar='SKU=QTY',
                       help='picked/received quantity for a SKU (others: full)')
        p.add_argument('--zero', action='store_true', help='nothing picked/received unless given with --qty')
        p.add_argument('--backorder', action='store_true',
                       help='after completing, create a child backorder (parent_order_id) for the remainder')
        if order:
            p.add_argument('--courier', help='bpost | postnl | dhl-parcel | dpd (default: by country)')
            p.add_argument('--tracking', help='tracking number (default: generated)')
            p.add_argument('--tracking-url')
            p.add_argument('--parcels', type=int, default=1)
        else:
            p.add_argument('--tracking', help='inbound tracking number')

    for name, kind in (('order', 'orders'), ('po', 'purchase-orders')):
        p = sub.add_parser(name, help='%s actions' % kind)
        s2 = p.add_subparsers(dest='action', required=True)
        a = s2.add_parser('advance', help='move one status forward (or --to STATUS)')
        a.add_argument('ref')
        a.add_argument('--to')
        warehouse_opts(a, name == 'order')
        a = s2.add_parser('ship' if name == 'order' else 'receive',
                          help='go straight to completed')
        a.add_argument('ref')
        warehouse_opts(a, name == 'order')
        a = s2.add_parser('status', help='set a status as-is (on-hold, cancelled, ...)')
        a.add_argument('ref')
        a.add_argument('status')
        a = s2.add_parser('backorder', help='create the backorder child for the not picked/received remainder')
        a.add_argument('ref')
        if name == 'order':
            a = s2.add_parser('parcel', help='add a parcel with tracking')
            a.add_argument('ref')
            a.add_argument('--courier')
            a.add_argument('--tracking')
            a.add_argument('--tracking-url')

    p = sub.add_parser('retour', help="create retour PO 'Retour <sale order>' for a shipped order")
    p.add_argument('ref', help='order ref (e.g. S00004)')
    p.add_argument('--qty', action='append', metavar='SKU=QTY')
    p.add_argument('--status', default='delivered', choices=['ordered', 'in-transit', 'delivered', 'unpacking', 'completed'])

    p = sub.add_parser('touch', help="bump 'edited' of an order / PO")
    p.add_argument('kind', choices=list(KIND))
    p.add_argument('ref')

    p = sub.add_parser('stock', help='set the physical stock of a SKU in the Stoqflow warehouse')
    p.add_argument('sku')
    p.add_argument('total', type=int)

    sub.add_parser('reset', help='re-seed the mock state')

    a = ap.parse_args()
    if a.cmd == 'list':
        kind = 'purchase-orders' if a.kind == 'po' else a.kind
        rows = call('GET', '|list|' + kind)
        return out(rows) if a.json else print_list(kind, rows)
    if a.cmd == 'show':
        return out(call('GET', '|show|%s|%s' % (KIND[a.kind], a.ref)))
    if a.cmd in ('order', 'po'):
        kind = KIND[a.cmd]
        if a.action in ('advance', 'ship', 'receive'):
            body = {'qty': qmap(a.qty), 'zero': a.zero, 'backorder': a.backorder,
                    'all': a.action in ('ship', 'receive'), 'to': getattr(a, 'to', None),
                    'tracking': a.tracking}
            if a.cmd == 'order':
                body.update(courier=a.courier, tracking_url=a.tracking_url, parcels=a.parcels)
            return out(call('POST', '|advance|%s|%s' % (kind, a.ref), body))
        if a.action == 'status':
            return out(call('POST', '|status|%s|%s' % (kind, a.ref), {'status': a.status}))
        if a.action == 'backorder':
            return out(call('POST', '|backorder|%s|%s' % (kind, a.ref), {}))
        if a.action == 'parcel':
            return out(call('POST', '|parcel|%s' % a.ref, {'courier': a.courier, 'tracking': a.tracking,
                                                           'tracking_url': a.tracking_url}))
    if a.cmd == 'retour':
        return out(call('POST', '|retour|%s' % a.ref, {'qty': qmap(a.qty), 'status': a.status}))
    if a.cmd == 'touch':
        return out(call('POST', '|touch|%s|%s' % (KIND[a.kind], a.ref), {}))
    if a.cmd == 'stock':
        return out(call('POST', '|stock', {'sku': a.sku, 'total': a.total}))
    if a.cmd == 'reset':
        return out(call('POST', '|reset', {}))


if __name__ == '__main__':
    main()
