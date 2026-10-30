#!/usr/bin/env python3
"""odoo_rpc.py fetch|push|eval ...  — trigger Stoqflow sync actions on the demo database over XML-RPC.
fetch = 'Gewijzigde orders ophalen' (incremental status update), push = 'Wachtende orders verwerken'."""
import sys, xmlrpc.client
URL, DB = 'http://localhost:8069', 'woody'
uid = xmlrpc.client.ServerProxy(URL + '/xmlrpc/2/common').authenticate(DB, 'admin', 'admin', {})
m = xmlrpc.client.ServerProxy(URL + '/xmlrpc/2/object', allow_none=True)
def call(model, method, *args, **kw):
    return m.execute_kw(DB, uid, 'admin', model, method, list(args), kw)
cmd = sys.argv[1]
if cmd in ('fetch', 'push', 'retours', 'backorders', 'stock'):
    sid = call('res.config.settings', 'create', {})
    meth = {'fetch': 'ws_fetch_status_updates', 'push': 'ws_sync_all_pickings_statusP',
            'retours': 'ws_fetch_retours', 'backorders': 'ws_fetch_backorders', 'stock': 'ws_import_stock'}[cmd]
    try:
        call('res.config.settings', meth, [sid])
    except xmlrpc.client.Fault as e:
        if 'cannot marshal None' not in str(e):
            raise
    print('ok', cmd)
elif cmd == 'call':          # odoo_rpc.py call model method '[ids]' 
    import json
    print(json.dumps(call(sys.argv[2], sys.argv[3], *json.loads(sys.argv[4]))))
