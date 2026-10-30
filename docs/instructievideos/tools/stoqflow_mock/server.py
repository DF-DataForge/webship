#!/usr/bin/env python3
"""Local mock of the Stoqflow (Webship) REST API, for demos of the Odoo
`webship` module.

Two listeners run in this process and share one state:

  * https://api.stoqflow.com/  (127.0.0.1:443, TLS with the local CA in certs/)
    The Stoqflow API as used by the module: products, clients, suppliers,
    company, warehouses, couriers, inventory, orders, purchase-orders.
  * http://127.0.0.1:8099/     control API used by ctl.py to "play the
    warehouse" (advance orders / purchase orders, add parcels, create
    backorders and retours, reset the state). Never exposed to Odoo.

State lives in memory and is saved to state.json after every change, so it
survives restarts. `ctl.py reset` (or deleting state.json) re-seeds it.

Auth: HTTP basic auth with any key/secret, except the key `wrong-key` (or the
secret `wrong-secret`) which is answered with 401 - use it to show a failing
"Test connection". Requests without basic auth are also refused with 401.
"""
import argparse
import base64
import copy
import json
import logging
import os
import random
import re
import ssl
import string
import sys
import threading
import time
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs, unquote

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.environ.get('STOQFLOW_MOCK_STATE', os.path.join(BASE_DIR, 'state.json'))
CERT_DIR = os.path.join(BASE_DIR, 'certs')

WRONG_KEY = 'wrong-key'
WRONG_SECRET = 'wrong-secret'
PAGE_SIZE = 50

ORDER_FLOW = ['ready-to-pick', 'picking', 'packing', 'ready-to-ship', 'completed']
PO_FLOW = ['ordered', 'in-transit', 'delivered', 'unpacking', 'completed']
ORDER_STATUSES = {'concept', 'awaiting-payment', 'on-hold', 'ready-to-pick', 'picking',
                  'ready-to-pack', 'packing', 'ready-to-ship', 'completed', 'cancelled'}
PO_STATUSES = {'concept', 'ordered', 'on-hold', 'in-transit', 'delivered', 'unpacking',
               'completed', 'cancelled'}
RESERVING_STATUSES = {'on-hold', 'ready-to-pick', 'picking', 'ready-to-pack', 'packing',
                      'ready-to-ship'}

COURIERS = [
    # code, name, tracking-number generator, tracking url template
    ('bpost', 'bpost'),
    ('postnl', 'PostNL'),
    ('dhl-parcel', 'DHL Parcel'),
    ('dpd', 'DPD'),
]
COUNTRY_COURIER = {'BE': 'bpost', 'NL': 'postnl', 'DE': 'dhl-parcel', 'FR': 'dpd'}

log = logging.getLogger('stoqflow-mock')
LOCK = threading.RLock()
STATE = {}
_last_ts = [None]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def now_dt():
    """Current UTC time, strictly increasing between calls (>= 1 ms apart),
    so every change gets its own 'edited' timestamp."""
    dt = datetime.now(timezone.utc).replace(tzinfo=None)
    dt = dt.replace(microsecond=(dt.microsecond // 1000) * 1000)
    if _last_ts[0] and dt <= _last_ts[0]:
        dt = _last_ts[0] + timedelta(milliseconds=1)
    _last_ts[0] = dt
    return dt


def iso(dt):
    return dt.strftime('%Y-%m-%dT%H:%M:%S.') + '%03dZ' % (dt.microsecond // 1000)


def now_iso():
    return iso(now_dt())


def parse_dt(value):
    """Parse the edited_after / created_after formats the module sends:
    '2026-10-30T08:00:00Z', '2026-10-30 08:00:00', with or without ms."""
    if not value:
        return None
    v = value.strip().replace('Z', '').replace('T', ' ')
    for fmt in ('%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
        try:
            return datetime.strptime(v, fmt)
        except ValueError:
            continue
    return None


def parse_iso(value):
    return datetime.strptime(value, '%Y-%m-%dT%H:%M:%S.%fZ')


def new_id():
    """24-hex MongoDB-style ObjectId."""
    return '%08x' % int(time.time()) + ''.join(random.choice('0123456789abcdef') for _ in range(16))


def next_number(kind, prefix, width):
    STATE['counters'][kind] += 1
    return '%s%0*d' % (prefix, width, STATE['counters'][kind])


def touch(obj):
    obj['edited'] = now_iso()
    return obj


def save():
    tmp = STATE_FILE + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(STATE, f, indent=1, sort_keys=False)
    os.replace(tmp, STATE_FILE)


# ---------------------------------------------------------------------------
# seed
# ---------------------------------------------------------------------------

# Physical stock in the Stoqflow warehouse, per SKU. Mirrors the demo's
# SQF/Stock quants, except Woody's Crew Socks (Odoo 117, Stoqflow 114) so the
# stock-difference screen has something to show. Products only show up in
# GET /inventory once they exist in Stoqflow (synced from Odoo, or seeded).
SEED_STOCK = {
    'WSS-BEANIE': 38, 'WSS-SOCKS': 114,
    'WSS-CMP-CRUISER-825': 9, 'WSS-CMP-STREET-80': 14,
    'WSS-HOOD-BLK-S': 8, 'WSS-HOOD-BLK-M': 8, 'WSS-HOOD-BLK-L': 8, 'WSS-HOOD-BLK-XL': 8,
    'WSS-HOOD-GRN-S': 8, 'WSS-HOOD-GRN-M': 7, 'WSS-HOOD-GRN-L': 8, 'WSS-HOOD-GRN-XL': 8,
    'WSS-TEE-BLK-S': 12, 'WSS-TEE-BLK-M': 12, 'WSS-TEE-BLK-L': 12, 'WSS-TEE-BLK-XL': 12,
    'WSS-TEE-WHT-S': 10, 'WSS-TEE-WHT-M': 12, 'WSS-TEE-WHT-L': 12, 'WSS-TEE-WHT-XL': 12,
}


def seed():
    t = now_dt() - timedelta(days=90)
    created = iso(t)
    company_id = '64f1c0a2e4b0a1d2c3f40001'
    brand_id = '64f1c0a2e4b0a1d2c3f40011'
    shop_id = '64f1c0a2e4b0a1d2c3f40021'
    warehouse_id = '64f1c0a2e4b0a1d2c3f40031'
    state = {
        'counters': {'order': 10040, 'po': 27, 'client': 11, 'supplier': 4, 'parcel': 0},
        'company': {
            '_id': company_id,
            'name': "Woody's Skate Supply",
            'vat': 'BE0789123456',
            'email': 'hello@woodys-skate.example',
            'address': {'address_1': 'Kammenstraat 42', 'postal_code': '2000',
                        'city': 'Antwerpen', 'country': 'BE'},
            'brands': [{
                '_id': brand_id,
                'name': "Woody's",
                'company_id': company_id,
                'shops': [{'_id': shop_id, 'name': "Woody's webshop",
                           'brand_id': brand_id, 'company_id': company_id,
                           'url': 'https://woodys-skate.example'}],
            }],
            'created': created, 'edited': created,
        },
        'warehouses': [{
            '_id': warehouse_id,
            'name': 'Stoqflow Fulfilment Antwerpen',
            'code': 'ANR1',
            'address': {'address_1': 'Noorderlaan 147', 'postal_code': '2030',
                        'city': 'Antwerpen', 'country': 'BE'},
            'created': created, 'edited': created,
        }],
        'couriers': [{'_id': '64f1c0a2e4b0a1d2c3f4005%d' % i, 'courier': code, 'name': name}
                     for i, (code, name) in enumerate(COURIERS)],
        'products': [],
        'clients': [],
        'suppliers': [],
        'orders': [],
        'purchase_orders': [],
        'stock': dict(SEED_STOCK),
    }
    STATE.clear()
    STATE.update(state)
    # WSS-BEANIE already exists in Stoqflow -> 'Match' links it, 'Sync' says
    # "SKU already exists in Stoqflow. Use the Match button".
    STATE['products'].append({
        '_id': '64f1c0a2e4b0a1d2c3f40101',
        'sku': 'WSS-BEANIE', 'name': "Woody's Beanie", 'type': 'basic',
        'brand_id': brand_id, 'company_id': company_id, 'has_stock': True,
        'price': 4.2, 'retail_price': 19.95, 'hs_code': '65050090',
        'country_of_origin': 'PT', 'barcodes': [],
        'properties': {'weight': 80, 'length': 22, 'width': 20, 'height': 3,
                       'unit': {'value': 1, 'unit': 'item'}},
        'created': created, 'edited': created,
    })
    # Concrete Wave Skateshop already exists as a client (match by e-mail or VAT).
    _add_client({'name': 'Concrete Wave Skateshop', 'contact': 'Concrete Wave Skateshop',
                 'email': 'orders@concretewave.example', 'phone': '+32 9 222 33 44',
                 'vat': 'BE0456789123',
                 'addresses': {'billing': {'address_1': 'Overpoortstraat 23', 'postal_code': '9000',
                                           'city': 'Gent', 'country': 'BE'}}}, created)
    # Two clients sharing Emma's e-mail -> "multiple matching clients" demo.
    _add_client({'name': 'Emma Janssens', 'contact': 'Emma Janssens',
                 'email': 'emma.janssens@example.com', 'phone': '+32 485 66 77 88',
                 'addresses': {'billing': {'address_1': 'Bondgenotenlaan 101', 'postal_code': '3000',
                                           'city': 'Leuven', 'country': 'BE'}}}, created)
    _add_client({'name': 'E. Janssens', 'contact': 'Emma Janssens',
                 'email': 'emma.janssens@example.com',
                 'addresses': {'billing': {'address_1': 'Tiensestraat 12', 'postal_code': '3000',
                                           'city': 'Leuven', 'country': 'BE'}}}, created)
    # Supplier used as sender of retour purchase orders.
    _add_supplier({'name': "Woody's webshop returns", 'email': 'returns@woodys-skate.example',
                   'address': {'address_1': 'Noorderlaan 147', 'postal_code': '2030',
                               'city': 'Antwerpen', 'country': 'BE'}}, created)
    save()


def _add_client(data, created=None):
    created = created or now_iso()
    c = dict(data)
    c['_id'] = new_id()
    c['client_number'] = next_number('client', 'CL', 5)
    c['company_id'] = STATE['company']['_id']
    c['created'] = created
    c['edited'] = created
    STATE['clients'].append(c)
    return c


def _add_supplier(data, created=None):
    created = created or now_iso()
    s = dict(data)
    s['_id'] = new_id()
    s['supplier_number'] = s.get('supplier_number') or next_number('supplier', 'SU', 5)
    s['company_id'] = STATE['company']['_id']
    s['created'] = created
    s['edited'] = created
    STATE['suppliers'].append(s)
    return s


def load():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            STATE.clear()
            STATE.update(json.load(f))
        log.info('state loaded from %s', STATE_FILE)
    else:
        seed()
        log.info('state seeded, saved to %s', STATE_FILE)


# ---------------------------------------------------------------------------
# lookups / views
# ---------------------------------------------------------------------------

def collection(name):
    return STATE[{'orders': 'orders', 'purchase-orders': 'purchase_orders'}.get(name, name)]


def find(coll, oid):
    for o in collection(coll):
        if o['_id'] == oid:
            return o
    return None


def product_by_id(pid):
    return find('products', pid)


def product_by_sku(sku):
    for p in STATE['products']:
        if p['sku'] == sku:
            return p
    return None


def reserved_by_sku():
    res = {}
    for o in STATE['orders']:
        if o['status'] in RESERVING_STATUSES:
            for it in o.get('order_items', []):
                res[it['sku']] = res.get(it['sku'], 0) + it['quantity'] - (it.get('picked') or 0)
    return res


def product_view(p):
    v = copy.deepcopy(p)
    total = STATE['stock'].get(p['sku'], 0) if p.get('has_stock', True) else 0
    v['product_items'] = [{'_id': p['_id'][:16] + '00000001', 'warehouse_id': STATE['warehouses'][0]['_id'],
                           'quantity': total}]
    return v


def inventory_items():
    res = reserved_by_sku()
    out = []
    for p in STATE['products']:
        if not p.get('has_stock', True):
            continue
        total = STATE['stock'].get(p['sku'], 0)
        reserved = min(res.get(p['sku'], 0), total)
        out.append({
            '_id': p['_id'][:16] + '000000ee',
            'product_id': p['_id'], 'sku': p['sku'], 'name': p.get('name'),
            'type': p.get('type', 'basic'), 'company_id': STATE['company']['_id'],
            'warehouse_id': STATE['warehouses'][0]['_id'],
            'total': total, 'reserved': reserved, 'available': total - reserved,
        })
    return out


def project(obj, fields):
    if not fields:
        return obj
    keep = set(f.strip() for f in fields.split(',') if f.strip()) | {'_id'}
    return {k: v for k, v in obj.items() if k in keep}


def list_filter(items, q, kind):
    def qv(key):
        vals = q.get(key)
        return vals[0] if vals else None

    out = list(items)
    if qv('edited_after'):
        d = parse_dt(qv('edited_after'))
        if d:
            out = [o for o in out if parse_iso(o.get('edited') or o['created']) >= d]
    if qv('created_after'):
        d = parse_dt(qv('created_after'))
        if d:
            out = [o for o in out if parse_iso(o['created']) >= d]
    if qv('subset'):
        ids = set(qv('subset').split(','))
        out = [o for o in out if o['_id'] in ids]
    if qv('sku') is not None:
        skus = set(s for s in qv('sku').split(','))
        out = [o for o in out if o.get('sku') in skus]
    for key in ('email', 'vat'):
        if qv(key) is not None:
            val = qv(key).strip().lower()
            out = [o for o in out if (o.get(key) or '').strip().lower() == val]
    if qv('origin_id') is not None:
        out = [o for o in out if str((o.get('origin') or {}).get('id', '')) == qv('origin_id')]
    if qv('origin_number') is not None:
        out = [o for o in out if str((o.get('origin') or {}).get('number', '')) == qv('origin_number')]
    if qv('order_number') is not None:
        val = qv('order_number')
        out = [o for o in out if o.get('order_number') == val
               or str((o.get('origin') or {}).get('number', '')) == val]
    if qv('parent_order_id') is not None:
        out = [o for o in out if (o.get('parent_order_id') or '') == qv('parent_order_id')]
    if qv('supplier_reference') is not None:
        out = [o for o in out if (o.get('supplier_reference') or '') == qv('supplier_reference')]
    if qv('status') is not None:
        sts = set(qv('status').split(','))
        out = [o for o in out if o.get('status') in sts]
    return out


# ---------------------------------------------------------------------------
# validation helpers
# ---------------------------------------------------------------------------

class ApiError(Exception):
    def __init__(self, code, body):
        super().__init__(str(body))
        self.code = code
        self.body = body


def field_error(field, message, code=400):
    return ApiError(code, [{'field': field, 'message': message}])


def not_found():
    return ApiError(404, {'error': 'asset-not-found', 'message': 'asset-not-found'})


def build_items(raw_items, with_received=False):
    if not isinstance(raw_items, list) or not raw_items:
        raise field_error('order_items', 'must contain at least one item')
    items = []
    for i, it in enumerate(raw_items):
        p = product_by_id(it.get('product_id'))
        if not p:
            raise field_error('order_items.%d.product_id' % i, 'product does not exist')
        qty = it.get('quantity')
        if not isinstance(qty, (int, float)) or qty <= 0 or float(qty) != int(qty):
            raise field_error('order_items.%d.quantity' % i, 'must be a positive integer')
        item = {'_id': new_id(), 'product_id': p['_id'], 'sku': p['sku'], 'name': p.get('name'),
                'quantity': int(qty)}
        if with_received:
            item['received'] = 0
        else:
            item['picked'] = 0
        items.append(item)
    return items


# ---------------------------------------------------------------------------
# API handlers
# ---------------------------------------------------------------------------

def api_list(kind, q):
    if kind == 'products':
        items = [product_view(p) for p in STATE['products']]
    elif kind == 'inventory':
        items = inventory_items()
    elif kind in ('clients', 'suppliers', 'orders', 'purchase-orders', 'warehouses', 'couriers'):
        items = copy.deepcopy(collection(kind))
    else:
        raise not_found()
    items = list_filter(items, q, kind)
    items.sort(key=lambda o: (o.get('created') or '', o['_id']))
    total = len(items)
    page = int((q.get('page') or ['1'])[0] or 1)
    items = items[(page - 1) * PAGE_SIZE: page * PAGE_SIZE]
    fields = (q.get('fields') or [None])[0]
    detail = (q.get('detail') or ['high'])[0]
    if kind in ('orders', 'purchase-orders') and detail == 'low':
        items = [{k: v for k, v in o.items() if k not in ('picks', 'parcels')} for o in items]
    items = [project(o, fields) for o in items]
    return 200, items, {'total-count': str(total)}


def api_get(kind, oid, q):
    if kind == 'products':
        p = product_by_id(oid)
        if not p:
            raise not_found()
        return 200, project(product_view(p), (q.get('fields') or [None])[0]), {}
    if kind in ('clients', 'suppliers', 'orders', 'purchase-orders', 'warehouses', 'couriers'):
        o = find(kind, oid)
        if not o:
            raise not_found()
        return 200, copy.deepcopy(o), {}
    raise not_found()


def api_post(kind, body):
    if not isinstance(body, dict):
        raise ApiError(400, [{'field': 'body', 'message': 'must be a JSON object'}])
    company_id = STATE['company']['_id']
    if kind == 'products':
        for f in ('brand_id', 'sku', 'name'):
            if not body.get(f):
                raise field_error(f, 'is required')
        if body['brand_id'] not in [b['_id'] for b in STATE['company']['brands']]:
            raise field_error('brand_id', 'brand does not exist')
        if product_by_sku(body['sku']):
            # Stoqflow forwards the MongoDB duplicate-key error with HTTP 200
            return 200, [{'index': 0, 'code': 11000}], {}
        p = dict(body)
        p.setdefault('type', 'basic')
        p['_id'] = new_id()
        p['company_id'] = company_id
        p['created'] = p['edited'] = now_iso()
        STATE['products'].append(p)
        save()
        return 200, product_view(p), {}
    if kind == 'clients':
        if not body.get('name'):
            raise field_error('name', 'is required')
        if body.get('email') and not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', body['email']):
            raise field_error('email', 'must be a valid e-mail address')
        c = _add_client(body)
        save()
        return 200, c, {}
    if kind == 'suppliers':
        if not body.get('name'):
            raise field_error('name', 'is required')
        s = _add_supplier(body)
        save()
        return 200, s, {}
    if kind == 'orders':
        shop_ids = [s['_id'] for b in STATE['company']['brands'] for s in b['shops']]
        if body.get('shop_id') not in shop_ids:
            raise field_error('shop_id', 'shop does not exist')
        if body.get('client_id') and not find('clients', body['client_id']):
            raise field_error('client_id', 'client does not exist')
        if not body.get('client_id') and not body.get('client_info'):
            raise field_error('client_id', 'client_id or client_info is required')
        origin = body.get('origin')
        if origin and origin.get('id') is not None:
            for o in STATE['orders']:
                if (o.get('origin') or {}).get('id') == origin.get('id') and o.get('shop_id') == body['shop_id']:
                    raise field_error('origin', 'reference must be unique')
        status = body.get('status') or 'concept'
        if status not in ORDER_STATUSES:
            raise field_error('status', 'invalid status')
        items = build_items(body.get('order_items'))
        ts = now_iso()
        o = {
            '_id': new_id(),
            'order_number': next_number('order', 'OR', 5),
            'company_id': company_id,
            'shop_id': body['shop_id'],
            'warehouse_id': STATE['warehouses'][0]['_id'],
            'client_id': body.get('client_id'),
            'client_info': body.get('client_info') or {},
            'origin': origin,
            'status': status,
            'notes': body.get('notes'),
            'scheduled': body.get('scheduled'),
            'preferred_courier': body.get('preferred_courier'),
            'order_items': items,
            'picks': [],
            'parcels': [],
            'parent_order_id': None,
            'created': ts, 'edited': ts,
        }
        STATE['orders'].append(o)
        save()
        return 200, copy.deepcopy(o), {}
    if kind == 'purchase-orders':
        if not find('suppliers', body.get('supplier_id') or ''):
            raise field_error('supplier_id', 'supplier does not exist')
        if not find('warehouses', body.get('warehouse_id') or ''):
            raise field_error('warehouse_id', 'warehouse does not exist')
        ref = body.get('supplier_reference')
        if ref and any(po.get('supplier_reference') == ref for po in STATE['purchase_orders']):
            raise field_error('supplier_reference', 'reference must be unique')
        status = body.get('status') or 'concept'
        if status not in PO_STATUSES:
            raise field_error('status', 'invalid status')
        items = build_items(body.get('order_items'), with_received=True)
        ts = now_iso()
        po = {
            '_id': new_id(),
            'order_number': next_number('po', 'PO', 5),
            'company_id': company_id,
            'supplier_id': body['supplier_id'],
            'warehouse_id': body['warehouse_id'],
            'supplier_reference': ref,
            'status': status,
            'scheduled': body.get('scheduled'),
            'notes': body.get('notes'),
            'tracking_numbers': '',
            'order_items': items,
            'delivered': None,
            'received_product_items': [],
            'parent_order_id': None,
            'created': ts, 'edited': ts,
        }
        STATE['purchase_orders'].append(po)
        save()
        return 200, copy.deepcopy(po), {}
    raise not_found()


def api_put(kind, oid, sub, body):
    if not isinstance(body, dict):
        raise ApiError(400, [{'field': 'body', 'message': 'must be a JSON object'}])
    if kind in ('orders', 'purchase-orders') and sub == 'status':
        o = find(kind, oid)
        if not o:
            raise not_found()
        st = body.get('status')
        valid = ORDER_STATUSES if kind == 'orders' else PO_STATUSES
        if st not in valid:
            raise field_error('status', 'invalid status')
        if o['status'] == 'completed' and st != 'completed':
            raise field_error('status', 'order is already completed')
        if o['status'] == 'cancelled' and st != 'cancelled':
            raise field_error('status', 'order is cancelled')
        o['status'] = st
        touch(o)
        save()
        return 200, copy.deepcopy(o), {}
    if sub:
        raise not_found()
    o = find(kind, oid)
    if not o:
        raise not_found()
    if kind == 'products':
        body = {k: v for k, v in body.items() if k not in ('_id', 'sku', 'brand_id', 'company_id')}
        o.update(body)
        touch(o)
        save()
        return 200, product_view(o), {}
    if kind in ('clients', 'suppliers'):
        body = {k: v for k, v in body.items() if k not in ('_id', 'client_number', 'company_id')}
        if kind == 'clients' and body.get('email') and not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', body['email']):
            raise field_error('email', 'must be a valid e-mail address')
        o.update(body)
        touch(o)
        save()
        return 200, copy.deepcopy(o), {}
    if kind == 'orders':
        if o['status'] in ('completed', 'cancelled', 'packing', 'ready-to-ship'):
            raise field_error('status', 'order can no longer be changed (status %s)' % o['status'])
        if 'client_id' in body and body['client_id'] and not find('clients', body['client_id']):
            raise field_error('client_id', 'client does not exist')
        if 'order_items' in body:
            o['order_items'] = build_items(body['order_items'])
        for k in ('client_id', 'client_info', 'notes', 'scheduled', 'preferred_courier'):
            if k in body:
                o[k] = body[k]
        touch(o)
        save()
        return 200, copy.deepcopy(o), {}
    if kind == 'purchase-orders':
        if 'order_items' in body:
            o['order_items'] = build_items(body['order_items'], with_received=True)
        for k in ('supplier_id', 'warehouse_id', 'supplier_reference', 'notes', 'scheduled'):
            if k in body:
                o[k] = body[k]
        touch(o)
        save()
        return 200, copy.deepcopy(o), {}
    raise not_found()


def api_delete(kind, oid):
    if kind not in ('products', 'clients', 'suppliers', 'orders', 'purchase-orders'):
        raise not_found()
    coll = collection(kind)
    for i, o in enumerate(coll):
        if o['_id'] == oid:
            del coll[i]
            save()
            return 200, {'deleted': True, '_id': oid}, {}
    raise not_found()


# ---------------------------------------------------------------------------
# warehouse simulation (control API)
# ---------------------------------------------------------------------------

def resolve(kind, ref):
    """Find an order / PO by _id, Stoqflow number, Odoo origin number
    (sale order name, e.g. S00004), supplier_reference or Odoo picking name
    (e.g. SQF/IN/00002). Parent orders win over backorder children."""
    coll = collection(kind)
    ref = str(ref).strip()
    tests = [
        lambda o: o['_id'] == ref,
        lambda o: o.get('order_number') == ref,
        lambda o: str((o.get('origin') or {}).get('number', '')) == ref,
        lambda o: (o.get('supplier_reference') or '') == ref,
        lambda o: (o.get('supplier_reference') or '').endswith('-' + ref),
        lambda o: ref.lower() in (o.get('supplier_reference') or '').lower(),
    ]
    for t in tests:
        hits = [o for o in coll if t(o)]
        if hits:
            hits.sort(key=lambda o: o['created'])
            non_child = [o for o in hits if not o.get('parent_order_id')]
            return (non_child or hits)[-1]   # most recent, parents first
    raise ApiError(404, {'error': 'no %s matches %r' % (kind, ref)})


def qty_for(items, qty_map, zero=False):
    """Picked/received quantity per order item: explicit SKU=qty wins, otherwise
    0 when zero=True, else the ordered quantity (full)."""
    out = {}
    for it in items:
        if it['sku'] in (qty_map or {}):
            out[it['_id']] = max(0, int(qty_map[it['sku']]))
        else:
            out[it['_id']] = 0 if zero else it['quantity']
    return out


def tracking_for(courier, order):
    digits = ''.join(random.choice(string.digits) for _ in range(10))
    country = (order.get('client_info') or {}).get('country') or 'BE'
    postal = ((order.get('client_info') or {}).get('postal_code') or '').replace(' ', '')
    if courier == 'bpost':
        tn = '32329990' + digits
        url = 'https://track.bpost.cloud/btr/web/#/search?itemCode=%s&lang=en' % tn
    elif courier == 'postnl':
        tn = '3SWSKS' + digits[:7]
        url = 'https://jouw.postnl.nl/track-and-trace/%s-%s-%s' % (tn, country, postal)
    elif courier == 'dhl-parcel':
        tn = 'JVGL06' + digits
        url = 'https://www.dhl.com/be-en/home/tracking/tracking-parcel.html?tracking-id=%s' % tn
    elif courier == 'dpd':
        tn = '0521' + digits
        url = 'https://tracking.dpd.de/status/en_BE/parcel/%s' % tn
    else:
        tn = 'TRK' + digits
        url = 'https://track.example/%s' % tn
    return tn, url


def courier_code(value, order):
    if not value:
        value = order.get('preferred_courier') or COUNTRY_COURIER.get(
            (order.get('client_info') or {}).get('country') or 'BE', 'bpost')
    v = value.strip().lower()
    for code, name in COURIERS:
        if v in (code, name.lower()):
            return code
    raise ApiError(400, {'error': 'unknown courier %r (use one of %s)' % (value, ', '.join(c for c, _ in COURIERS))})


def set_picks(o, qty_map=None, zero=False):
    picked = qty_for(o['order_items'], qty_map, zero)
    o['picks'] = []
    for it in o['order_items']:
        q = picked[it['_id']]
        it['picked'] = q
        if q:
            o['picks'].append({'_id': new_id(), 'product_id': it['product_id'], 'sku': it['sku'],
                               'quantity': q, 'location': 'A-%02d-%02d' % (random.randint(1, 12), random.randint(1, 30)),
                               'picked_at': now_iso()})


def add_parcel(o, courier=None, tracking=None, tracking_url=None):
    code = courier_code(courier, o)
    tn, url = tracking_for(code, o)
    if tracking:
        tn = tracking
        url = tracking_url or _url_with(code, o, tn)
    ci = o.get('client_info') or {}
    STATE['counters']['parcel'] += 1
    contents = []
    weight = 0
    for p in o.get('picks') or []:
        prod = product_by_id(p['product_id']) or {}
        w = ((prod.get('properties') or {}).get('weight') or 100) * p['quantity']
        weight += w
        contents.append({'product_id': p['product_id'], 'sku': p['sku'], 'description': prod.get('name', ''),
                         'quantity': p['quantity'], 'weight': w, 'hs_code': prod.get('hs_code', ''),
                         'origin_country': prod.get('country_of_origin', ''),
                         'value': round((prod.get('retail_price') or 0) * p['quantity'], 2)})
    parcel = {
        '_id': new_id(),
        'number': len(o.get('parcels') or []) + 1,
        'tracking_number': tn,
        'tracking_url': url,
        'label_url': 'https://api.stoqflow.com/labels/%s.pdf' % tn,
        'provider': code,
        'provider_id': 'shp_%06d' % STATE['counters']['parcel'],
        'weight': max(weight, 100),
        'length': 40, 'width': 30, 'height': 15,
        'shipping_cost': {'bpost': 4.95, 'postnl': 6.25, 'dhl-parcel': 6.95, 'dpd': 7.45}.get(code, 5.0),
        'shipping_address': {'name': ci.get('name', ''), 'company': ci.get('company', ''),
                             'address_1': ci.get('address_1', ''), 'postal_code': ci.get('postal_code', ''),
                             'city': ci.get('city', ''), 'country': ci.get('country', '')},
        'contents': contents,
        'resources': [{'_id': new_id(), 'name': 'Box M (40x30x15)', 'quantity': 1}],
        'created': now_iso(),
    }
    o.setdefault('parcels', []).append(parcel)
    o['preferred_courier'] = code
    return parcel


def _url_with(code, o, tn):
    ci = o.get('client_info') or {}
    return {
        'bpost': 'https://track.bpost.cloud/btr/web/#/search?itemCode=%s&lang=en' % tn,
        'postnl': 'https://jouw.postnl.nl/track-and-trace/%s-%s-%s' % (
            tn, ci.get('country') or 'BE', (ci.get('postal_code') or '').replace(' ', '')),
        'dhl-parcel': 'https://www.dhl.com/be-en/home/tracking/tracking-parcel.html?tracking-id=%s' % tn,
        'dpd': 'https://tracking.dpd.de/status/en_BE/parcel/%s' % tn,
    }.get(code, 'https://track.example/%s' % tn)


def create_order_backorder(parent):
    remaining = []
    for it in parent['order_items']:
        rest = it['quantity'] - (it.get('picked') or 0)
        if rest > 0:
            remaining.append({'_id': new_id(), 'product_id': it['product_id'], 'sku': it['sku'],
                              'name': it.get('name'), 'quantity': rest, 'picked': 0})
    if not remaining:
        raise ApiError(400, {'error': 'nothing left to back-order on %s' % parent['order_number']})
    n = len([o for o in STATE['orders'] if o.get('parent_order_id') == parent['_id']]) + 1
    ts = now_iso()
    child = {
        '_id': new_id(),
        'order_number': '%s-%02d' % (parent['order_number'], n),
        'company_id': parent['company_id'], 'shop_id': parent['shop_id'],
        'warehouse_id': parent['warehouse_id'], 'client_id': parent.get('client_id'),
        'client_info': copy.deepcopy(parent.get('client_info')), 'origin': None,
        'status': 'ready-to-pick', 'notes': 'Backorder of %s' % parent['order_number'],
        'scheduled': None, 'preferred_courier': parent.get('preferred_courier'),
        'order_items': remaining, 'picks': [], 'parcels': [],
        'parent_order_id': parent['_id'], 'created': ts, 'edited': ts,
    }
    STATE['orders'].append(child)
    return child


def create_po_backorder(parent):
    remaining = []
    for it in parent['order_items']:
        rest = it['quantity'] - (it.get('received') or 0)
        if rest > 0:
            remaining.append({'_id': new_id(), 'product_id': it['product_id'], 'sku': it['sku'],
                              'name': it.get('name'), 'quantity': rest, 'received': 0})
    if not remaining:
        raise ApiError(400, {'error': 'nothing left to back-order on %s' % parent['order_number']})
    n = len([o for o in STATE['purchase_orders'] if o.get('parent_order_id') == parent['_id']]) + 1
    ts = now_iso()
    child = {
        '_id': new_id(),
        'order_number': '%s-%02d' % (parent['order_number'], n),
        'company_id': parent['company_id'], 'supplier_id': parent['supplier_id'],
        'warehouse_id': parent['warehouse_id'],
        'supplier_reference': '%s (backorder %d)' % (parent.get('supplier_reference') or parent['order_number'], n),
        'status': 'ordered', 'scheduled': None, 'notes': 'Backorder of %s' % parent['order_number'],
        'tracking_numbers': '', 'order_items': remaining, 'delivered': None,
        'received_product_items': [], 'parent_order_id': parent['_id'], 'created': ts, 'edited': ts,
    }
    STATE['purchase_orders'].append(child)
    return child


def order_step(o, target, opts):
    """Move an order one status forward (to `target`), filling in the data the
    warehouse produces at that step."""
    if target in ('packing', 'ready-to-ship', 'completed') and not o.get('picks'):
        set_picks(o, opts.get('qty'), opts.get('zero'))
    if target in ('ready-to-ship', 'completed') and not o.get('parcels') and any(
            it.get('picked') for it in o['order_items']):
        for _ in range(max(1, int(opts.get('parcels') or 1))):
            add_parcel(o, opts.get('courier'), opts.get('tracking'), opts.get('tracking_url'))
    if target == 'completed' and o['status'] != 'completed':
        for it in o['order_items']:
            STATE['stock'][it['sku']] = STATE['stock'].get(it['sku'], 0) - (it.get('picked') or 0)
        o['shipped'] = now_iso()
    o['status'] = target
    touch(o)


def po_step(po, target, opts):
    if target in ('in-transit', 'delivered', 'unpacking', 'completed') and not po.get('tracking_numbers'):
        po['tracking_numbers'] = opts.get('tracking') or ('JVGL06' + ''.join(random.choice(string.digits) for _ in range(10)))
    if target in ('delivered', 'unpacking', 'completed') and not po.get('delivered'):
        po['delivered'] = now_iso()
    received_set = STATE.setdefault('received_set', [])
    if target in ('unpacking', 'completed') and po['_id'] not in received_set:
        rec = qty_for(po['order_items'], opts.get('qty'), opts.get('zero'))
        po['received_product_items'] = []
        for it in po['order_items']:
            it['received'] = rec[it['_id']]
            if it['received']:
                po['received_product_items'].append({'_id': new_id(), 'product_id': it['product_id'],
                                                     'sku': it['sku'], 'quantity': it['received'],
                                                     'received_at': now_iso()})
        received_set.append(po['_id'])
    if target == 'completed' and po['status'] != 'completed':
        for it in po['order_items']:
            STATE['stock'][it['sku']] = STATE['stock'].get(it['sku'], 0) + (it.get('received') or 0)
    po['status'] = target
    touch(po)


def advance(kind, ref, opts, to=None, all_the_way=False):
    o = resolve(kind, ref)
    flow = ORDER_FLOW if kind == 'orders' else PO_FLOW
    step = order_step if kind == 'orders' else po_step
    if o['status'] in ('completed', 'cancelled'):
        raise ApiError(400, {'error': '%s is already %s' % (o['order_number'], o['status'])})
    if opts.get('qty') or opts.get('zero'):
        # explicit quantities replace earlier picks / receipts
        if kind == 'orders':
            o['picks'] = []
            o['parcels'] = []
        else:
            if o['_id'] in STATE.setdefault('received_set', []):
                STATE['received_set'].remove(o['_id'])
    cur = o['status']
    idx = flow.index(cur) if cur in flow else -1
    target = to or (flow[-1] if all_the_way else flow[idx + 1])
    if target not in flow:
        # plain status change (on-hold, concept, cancelled ...)
        o['status'] = target
        touch(o)
    else:
        tidx = flow.index(target)
        if tidx <= idx:
            raise ApiError(400, {'error': '%s is already %s' % (o['order_number'], cur)})
        for s in flow[idx + 1: tidx + 1]:
            step(o, s, opts)
    result = {'updated': summary(o, kind)}
    if opts.get('backorder') and o['status'] == 'completed':
        child = create_order_backorder(o) if kind == 'orders' else create_po_backorder(o)
        result['backorder'] = summary(child, kind)
    save()
    return result


def summary(o, kind):
    s = {'_id': o['_id'], 'order_number': o['order_number'], 'status': o['status'], 'edited': o['edited']}
    if kind == 'orders':
        s['origin'] = (o.get('origin') or {}).get('number')
        s['items'] = ['%s %s/%s picked' % (it['sku'], it.get('picked', 0), it['quantity']) for it in o['order_items']]
        if o.get('parcels'):
            s['parcels'] = ['%s %s %s' % (p['provider'], p['tracking_number'], p['tracking_url']) for p in o['parcels']]
    else:
        s['supplier_reference'] = o.get('supplier_reference')
        s['items'] = ['%s %s/%s received' % (it['sku'], it.get('received', 0), it['quantity']) for it in o['order_items']]
    if o.get('parent_order_id'):
        s['parent_order_id'] = o['parent_order_id']
    return s


def create_retour(ref, qty_map=None, status='delivered'):
    order = resolve('orders', ref)
    number = (order.get('origin') or {}).get('number') or order['order_number']
    if order.get('parent_order_id') and not order.get('origin'):
        parent = find('orders', order['parent_order_id'])
        number = ((parent or {}).get('origin') or {}).get('number') or number
    supplier = next((s for s in STATE['suppliers'] if s.get('email') == 'returns@woodys-skate.example'), None) \
        or STATE['suppliers'][0]
    items = []
    for it in order['order_items']:
        q = (qty_map or {}).get(it['sku'], it.get('picked') or it['quantity'])
        if q:
            items.append({'_id': new_id(), 'product_id': it['product_id'], 'sku': it['sku'],
                          'name': it.get('name'), 'quantity': int(q), 'received': 0})
    if not items:
        raise ApiError(400, {'error': 'no items to return'})
    ts = now_iso()
    po = {
        '_id': new_id(), 'order_number': next_number('po', 'PO', 5),
        'company_id': STATE['company']['_id'], 'supplier_id': supplier['_id'],
        'warehouse_id': STATE['warehouses'][0]['_id'],
        'supplier_reference': 'Retour %s' % number, 'status': 'ordered', 'scheduled': None,
        'notes': 'Return of order %s (%s)' % (order['order_number'], number),
        'tracking_numbers': '', 'order_items': items, 'delivered': None,
        'received_product_items': [], 'parent_order_id': None, 'created': ts, 'edited': ts,
    }
    STATE['purchase_orders'].append(po)
    if status and status != 'ordered':
        flow = PO_FLOW
        for s in flow[1: flow.index(status) + 1]:
            po_step(po, s, {})
    save()
    return {'retour': summary(po, 'purchase-orders')}


# ---------------------------------------------------------------------------
# HTTP plumbing
# ---------------------------------------------------------------------------

class BaseHandler(BaseHTTPRequestHandler):
    server_version = 'Stoqflow-Mock/1.0'
    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt, *args):
        log.info('%s %s', self.__class__.__name__[:3], fmt % args)

    def _send(self, code, body, headers=None):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _body(self):
        n = int(self.headers.get('Content-Length') or 0)
        if not n:
            return {}
        raw = self.rfile.read(n)
        try:
            return json.loads(raw.decode() or '{}')
        except ValueError:
            raise ApiError(400, [{'field': 'body', 'message': 'invalid JSON'}])


class ApiHandler(BaseHandler):
    def _auth_ok(self):
        h = self.headers.get('Authorization') or ''
        if not h.startswith('Basic '):
            return False
        try:
            key, _, secret = base64.b64decode(h[6:]).decode().partition(':')
        except Exception:
            return False
        return bool(key) and key != WRONG_KEY and secret != WRONG_SECRET

    def _dispatch(self, method):
        try:
            if not self._auth_ok():
                return self._send(401, {'error': 'unauthorized', 'message': 'Invalid API key or secret'})
            parts = urlsplit(self.path)
            q = parse_qs(parts.query, keep_blank_values=True)
            segs = [unquote(s) for s in parts.path.split('/') if s]
            if segs and segs[0] in ('v1', 'v2'):
                segs = segs[1:]
            if not segs:
                raise not_found()
            kind = segs[0]
            oid = segs[1] if len(segs) > 1 else None
            sub = segs[2] if len(segs) > 2 else None
            with LOCK:
                if method == 'GET':
                    if kind == 'company' and not oid:
                        code, body, hdr = 200, copy.deepcopy(STATE['company']), {'total-count': '1'}
                    elif oid:
                        code, body, hdr = api_get(kind, oid, q)
                    else:
                        code, body, hdr = api_list(kind, q)
                elif method == 'POST' and not oid:
                    code, body, hdr = api_post(kind, self._body())
                elif method == 'PUT' and oid:
                    code, body, hdr = api_put(kind, oid, sub, self._body())
                elif method == 'DELETE' and oid:
                    code, body, hdr = api_delete(kind, oid)
                else:
                    raise ApiError(405, {'error': 'method not allowed'})
            self._send(code, body, hdr)
        except ApiError as e:
            self._send(e.code, e.body)
        except Exception as e:  # pragma: no cover
            log.exception('API error')
            self._send(500, {'error': 'internal', 'message': str(e)})

    def do_GET(self):
        self._dispatch('GET')

    def do_POST(self):
        self._dispatch('POST')

    def do_PUT(self):
        self._dispatch('PUT')

    def do_DELETE(self):
        self._dispatch('DELETE')


class CtlHandler(BaseHandler):
    """Control API (plain HTTP, 127.0.0.1 only):
      GET  /list/<orders|purchase-orders|products|clients|suppliers|inventory|couriers|warehouses|company>
      GET  /show/<orders|purchase-orders>/<ref>
      POST /advance/<orders|purchase-orders>/<ref>  {to, all, qty:{sku:n}, zero, courier, tracking, tracking_url, parcels, backorder}
      POST /status/<orders|purchase-orders>/<ref>   {status}
      POST /backorder/<orders|purchase-orders>/<ref>
      POST /parcel/<ref>                            {courier, tracking, tracking_url}
      POST /retour/<order ref>                      {qty:{sku:n}, status}
      POST /touch/<orders|purchase-orders>/<ref>
      POST /stock                                   {sku, total}
      POST /reset
    """

    def do_GET(self):
        try:
            segs = [unquote(s) for s in urlsplit(self.path).path.split('/') if s]
            with LOCK:
                if segs[:1] == ['list'] and len(segs) == 2:
                    kind = segs[1]
                    if kind == 'inventory':
                        return self._send(200, inventory_items())
                    if kind == 'company':
                        return self._send(200, STATE['company'])
                    if kind == 'stock':
                        return self._send(200, STATE['stock'])
                    if kind == 'products':
                        return self._send(200, [product_view(p) for p in STATE['products']])
                    return self._send(200, collection(kind))
                if segs[:1] == ['show'] and len(segs) == 3:
                    return self._send(200, resolve(segs[1], segs[2]))
            raise ApiError(404, {'error': 'unknown control endpoint'})
        except ApiError as e:
            self._send(e.code, e.body)
        except KeyError as e:
            self._send(404, {'error': 'unknown collection %s' % e})

    def do_POST(self):
        try:
            segs = [unquote(s) for s in urlsplit(self.path).path.split('/') if s]
            body = self._body() or {}
            with LOCK:
                op = segs[0] if segs else ''
                if op == 'reset':
                    seed()
                    return self._send(200, {'reset': True})
                if op == 'advance' and len(segs) == 3:
                    return self._send(200, advance(segs[1], segs[2], body, body.get('to'), body.get('all')))
                if op == 'status' and len(segs) == 3:
                    return self._send(200, advance(segs[1], segs[2], {}, body['status']))
                if op == 'backorder' and len(segs) == 3:
                    o = resolve(segs[1], segs[2])
                    child = create_order_backorder(o) if segs[1] == 'orders' else create_po_backorder(o)
                    save()
                    return self._send(200, {'backorder': summary(child, segs[1])})
                if op == 'parcel' and len(segs) == 2:
                    o = resolve('orders', segs[1])
                    if not o.get('picks'):
                        set_picks(o)
                    add_parcel(o, body.get('courier'), body.get('tracking'), body.get('tracking_url'))
                    touch(o)
                    save()
                    return self._send(200, {'updated': summary(o, 'orders')})
                if op == 'retour' and len(segs) == 2:
                    return self._send(200, create_retour(segs[1], body.get('qty'), body.get('status') or 'delivered'))
                if op == 'touch' and len(segs) == 3:
                    o = resolve(segs[1], segs[2])
                    touch(o)
                    save()
                    return self._send(200, {'updated': summary(o, segs[1])})
                if op == 'stock':
                    STATE['stock'][body['sku']] = int(body['total'])
                    p = product_by_sku(body['sku'])
                    if p:
                        touch(p)
                    save()
                    return self._send(200, {body['sku']: STATE['stock'][body['sku']]})
            raise ApiError(404, {'error': 'unknown control endpoint'})
        except ApiError as e:
            self._send(e.code, e.body)


def serve(server, name):
    log.info('%s listening on %s:%s', name, *server.server_address[:2])
    server.serve_forever()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--host', default='127.0.0.1')
    ap.add_argument('--port', type=int, default=443)
    ap.add_argument('--ctl-port', type=int, default=8099)
    ap.add_argument('--reset', action='store_true', help='re-seed the state on start')
    ap.add_argument('--verbose', '-v', action='store_true')
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format='%(asctime)s %(levelname)s %(message)s')
    if not args.verbose:
        log.setLevel(logging.INFO)
    if args.reset and os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)
    load()

    api = ThreadingHTTPServer((args.host, args.port), ApiHandler)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(os.path.join(CERT_DIR, 'server.crt'), os.path.join(CERT_DIR, 'server.key'))
    api.socket = ctx.wrap_socket(api.socket, server_side=True)
    ctl = ThreadingHTTPServer(('127.0.0.1', args.ctl_port), CtlHandler)
    threading.Thread(target=serve, args=(ctl, 'control API (http)'), daemon=True).start()
    try:
        serve(api, 'Stoqflow API (https://api.stoqflow.com/)')
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
