# StoqFlow Request Reduction — Implementation Plan

Portable guide for applying these changes to any branch of the `webship` module.
Two independent parts; each can be ported on its own:

- **Part 1 — Odoo → StoqFlow:** stop redundant `PUT clients/{id}` calls (payload-hash change detection).
- **Part 2 — StoqFlow → Odoo:** incremental status updates via `edited_after` and a queue table, with a settings toggle to fall back to the old method.

Reference implementation: branch `claude/stoqflow-request-analysis-vpyit5`, commits
`a2edad4` (Part 1) and `2b381f6` (Part 2). Line numbers below are from that branch —
on other branches, locate the named methods instead of trusting the numbers.

---

## Problem analysis

### Outbound flood (PUT clients)

1. `WebShipHandler.sync_partner()` (`webship/models/ws.py`) unconditionally PUT
   `clients/{id}` whenever the partner already had `df_client_id_webship` — no
   check whether anything changed since the last push.
2. `_sync_picking()` calls `sync_partner()` on **every** order sync, so a customer
   with N pickings was PUT N times.
3. The 30-minute cron `ir_cron_sync_statusP` → `ws_sync_all_pickings_statusP()`
   re-syncs every picking with `df_process_code == 'P'`. Soft failures
   ("Not all items are in stock", missing SKU, …) intentionally keep pickings at
   'P' until resolved — so each stuck picking re-PUT its unchanged client every
   30 minutes, forever. **The retry loop is intentional and must be preserved**;
   only the redundant client PUT inside it had to go.
4. The shared `requests.Session` retries PUTs up to 3× on 429/500/502/503
   (`Retry` adapter in `WebShipHandler.__init__`), multiplying each redundant PUT
   into up to 4 HTTP requests. Left as-is: once redundant PUTs are skipped it
   only applies to meaningful calls.

### Inbound flood (status polling)

The status cron `ir_cron_sync_statussen` → `ws_sync_statusses_since_last()`
(`res_config_settings.py`) searched **all** confirmed/assigned pickings with a
Webship location and called `picking.fetchQuantities()` for each — one
`GET /orders/{id}` (and/or `GET /purchase-orders/{id}`) per picking per run,
regardless of whether anything changed in StoqFlow.

The API supports delta queries: `GET /orders?edited_after=<ISO datetime>` and
`GET /purchase-orders?edited_after=...` return only changed records
(paginated, 50/page, `total-count` response header). The module's existing
`WebShipHandler.fetchAll(sUrl, sDetail, sEditedAfter, sCreatedAfter)` already
implements this including pagination.

---

## Part 1 — Payload-hash change detection for client PUTs

**Approach:** store a sha256 of the last successfully pushed client payload on
`res.partner`; skip the PUT when the payload is unchanged. Partner edits
propagate naturally (payload changes → hash mismatch → one PUT → re-baseline).

### 1.1 `webship/models/partner.py` — new field

Insert next to `df_last_webship_sync`:

```python
# sha256 of the last client payload successfully pushed to Stoqflow.
# WebShipHandler.sync_partner compares against this to skip redundant
# PUT clients/{id} calls when nothing changed since the last push.
df_webship_payload_hash = fields.Char(
    "Stoqflow client payload hash", readonly=True, copy=False)
```

No view change, no migration script: the ORM adds the column on `-u webship`,
and a NULL hash means "push once, then baseline" — self-healing on first run.

### 1.2 `webship/models/ws.py` — hash helper

Add `import hashlib` next to `import json`. Add a staticmethod on
`WebShipHandler`, directly above `sync_partner`:

```python
@staticmethod
def _client_payload_hash(payload, client_id):
    """Deterministic sha256 fingerprint of a client payload plus the
    Stoqflow client id it targets. Used by sync_partner to detect
    whether a PUT clients/{id} would send anything new."""
    canonical = json.dumps(payload, sort_keys=True, default=str,
                           separators=(',', ':'))
    return hashlib.sha256(
        (canonical + '|' + (client_id or '')).encode('utf-8')
    ).hexdigest()
```

Hash input = the `sJson` dict as built by `sync_partner` (after its False/''
pruning) **plus** `df_client_id_webship`. Including the client id makes the
stored hash self-invalidating when a partner is re-matched to a different
StoqFlow client — no invalidation hooks needed anywhere. (`performPut` passes
the payload through `removeFalseVals`, which returns a *copy*, so hashing the
pre-cleaned dict is a stable proxy for the wire payload.)

### 1.3 `webship/models/ws.py` — `sync_partner` changes

Signature: `def sync_partner(self, partner, fallback_partner=None, force=False):`

Replace the POST/PUT branch at the end (validation, email pre-check, and the
"email already exists" early return stay untouched):

```python
        result = self.performPost('clients', sJson)
        if result['status'] == 'success':
            partner.df_client_id_webship = result['data']['_id']
    else:
        payload_hash = self._client_payload_hash(
            sJson, partner.df_client_id_webship)
        if not force and partner.df_webship_payload_hash == payload_hash:
            self.showDebugInfo(
                'Client payload unchanged for partner %s (client %s) '
                '- skipping PUT' % (partner.id, partner.df_client_id_webship))
            return []
        result = self.performPut('clients', sJson, partner.df_client_id_webship)

    if result['status'] == 'success':
        # Baseline for the next change-detection pass. Recomputed here
        # (not reused from above) so the POST branch hashes with the
        # freshly assigned client id.
        partner.df_webship_payload_hash = self._client_payload_hash(
            sJson, partner.df_client_id_webship)
        partner.df_last_webship_sync = fields.Datetime.now()
        return []
    else:
        return ['Error: ' + result['errorText'] + ' (url: ' + result.get('url', '?') + ')']
```

Key semantics:
- Skip returns `[]` (success) **before** any HTTP call — callers treat it as success.
- Hash is written **only on success** — failed PUTs retry on the next cron pass.
- Per-cron-run dedup is automatic: the hash persists on the partner within the
  same transaction, so picking #2 for the same customer sees what picking #1 wrote.
- `df_last_webship_sync` (existed but was never written) is now populated.

### 1.4 `webship/models/partner.py` — manual button forces a push

In `ws_sync_partner` (the partner "Sync" button):

```python
sResult += wsHandler.sync_partner(record, force=True)
```

A manual click means "push now" — it must always hit StoqFlow (repairs
StoqFlow-side drift the hash can't see) and re-baselines on success. The
cron/order-sync call sites keep the default `force=False` — no change there.

### 1.5 Explicitly NOT changed

- `sync_sup()` in ws.py also PUTs `clients/{id}` but is dead code (zero callers,
  reads non-prefixed attribute names that don't exist) — leave it.
- `sync_supplier()`'s unconditional `PUT suppliers/{id}` — low-volume (manual
  button + PO sync). Possible follow-up: same helper with a second hash field.
- The urllib3 Retry adapter, the 'P'-retry cron loop, and the
  `_sync_picking → sync_partner` call site — behavior preserved by design.

---

## Part 2 — Incremental status-update queue (StoqFlow → Odoo)

**Approach:** a new table `webship.status.update` is filled by a cron that polls
only the changed records (`edited_after`), then processes each entry with the
existing `fetchQuantities()` on the matched picking. A settings toggle switches
between this flow and the old full sync, so falling back is one checkbox.

Request volume: from *one call per open picking per run* to
*two list calls + one call per actually-changed record*.

### 2.1 New model — `webship/models/status_update.py` (new file)

Copy the file from the reference branch. Summary of its contents:

- **Model** `webship.status.update`, `_order = 'create_date desc, id desc'`:
  - `df_webship_id` (Char, required, indexed) — StoqFlow `_id`
  - `df_object_type` (Selection: `order` / `purchase-order`)
  - `df_code_webship` (Char) — StoqFlow `order_number`
  - `df_status_webship` (Char), `df_edited` (Datetime)
  - `picking_id` (Many2one `stock.picking`, `ondelete='set null'`)
  - `state` (Selection: `pending` / `done` / `skipped` / `error`, default pending)
  - `df_result` (Text)
- **`getHandler()`** — same pattern as `picking.py`: build `WebShipHandler` from
  the `webship.username/password/base_url` params, then `set_env(self.env)`.
- **`_parse_stoqflow_datetime(value)`** — parses both `%Y-%m-%dT%H:%M:%S.%fZ`
  and `%Y-%m-%dT%H:%M:%SZ`, returns naive UTC datetime or False.
- **`_find_picking()`** — order → search `df_picking_id_webship`; purchase-order
  → `df_po_id_webship`. Only a unique match counts (log + skip on multiple).
- **`_queue_changed_records(wsHandler, endpoint, object_type, edited_after)`** —
  `wsHandler.fetchAll(endpoint, 'high', edited_after, None)`, iterate all pages,
  **upsert** per StoqFlow id: if a *pending* entry exists for the same id+type,
  refresh it (status/edited/number) instead of creating a duplicate. Returns
  `(success, max_edited_datetime)`.
- **`_process_pending()`** — for every `pending` entry (ordered by `df_edited`):
  no matching picking → `skipped`; cancelled picking → `skipped`; same picking
  already updated this run → `done` ("Already updated in this run");
  otherwise `picking.fetchQuantities()` in try/except → `done` with the
  picking's sync result, or `error` with the exception text. Errors never block
  the rest of the queue.
- **`cron_fetch_and_process()`** — cron entry point, **gated**: no-op with a log
  line unless `webship.use_status_update_queue == 'True'`. Calls `_fetch_and_process()`.
- **`_fetch_and_process()`** — the worker:
  1. Checkpoint = `webship.last_check_status_update` param; if empty, `now - 1 day`
     (first run looks back one day rather than fetching all history).
  2. `edited_after = checkpoint + 1 second`, formatted `%Y-%m-%dT%H:%M:%SZ`
     (the +1s avoids refetching the newest record of the previous poll).
  3. Queue changed `orders` and `purchase-orders`.
  4. Advance the checkpoint to the newest `edited` seen — **only when both list
     calls succeeded** (a failed poll is retried next run; the upsert keeps
     that idempotent).
  5. `_process_pending()`.
- **`action_process()`** — button: set selected entries back to pending and process.

Register it in `webship/models/__init__.py`: `from . import status_update`.

### 2.2 The fallback toggle — `webship/models/res_config_settings.py`

New Boolean setting (module convention: Boolean + `config_parameter`, checked
in code as `get_param(...) == 'True'`):

```python
webship_use_status_update_queue = fields.Boolean(
    string="Incremental status updates (edited_after)",
    config_parameter='webship.use_status_update_queue',
    help="When enabled, statuses and quantities are fetched from Stoqflow incrementally: a cron "
         "polls only the orders/purchase orders changed since the last check (edited_after) and "
         "updates the matched pickings via the status update queue. The old method (one API call "
         "per open picking on every run) is skipped while this is enabled. Disable to fall back "
         "to the old method.")
```

Plus a checkpoint field (editable so a wider window can be re-fetched):

```python
webship_last_check_status_update = fields.Datetime(
    string="Status updates last check",
    config_parameter='webship.last_check_status_update', help="...")
```

**Gate the OLD flow** at the top of `ws_sync_statusses_since_last()` — this must
live *inside* the method (not in the cron code) because the old cron record is
in a `noupdate="1"` block and existing databases keep its original code:

```python
if self.env['ir.config_parameter'].sudo().get_param('webship.use_status_update_queue') == 'True':
    _logger.info(
        "Skipping full status sync: incremental status updates (edited_after queue) are enabled")
    return
```

**Manual button** (bypasses the toggle — a click is explicit intent, useful for
testing the flow before switching the cron over):

```python
def ws_fetch_status_updates(self):
    self.env['webship.status.update']._fetch_and_process()
```

Net effect: **both crons can stay active permanently; the checkbox alone decides
which flow does the work.** Toggle off (default) = exact old behavior.

### 2.3 Cron — `webship/views/cron.xml`

Add inside the existing `<data noupdate="1">` block (new records in a noupdate
block ARE still created on upgrade; only updates are suppressed):

```xml
<record id="ir_cron_status_updates" model="ir.cron">
    <field name="name">Stoqflow fetch changed orders (status updates)</field>
    <field name="model_id" ref="model_webship_status_update"/>
    <field name="state">code</field>
    <field name="code">model.cron_fetch_and_process()</field>
    <field name="interval_number">10</field>
    <field name="interval_type">minutes</field>
    <field name="active">False</field>
</record>
```

Interval ("every X minutes") is adjusted on the cron record. Ships inactive,
matching the module convention.

### 2.4 Views — `webship/views/status_update_views.xml` (new file)

List (state decorations, optional raw-id column), form (statusbar +
"Process now" button), search (filters per state/type, group-by), action, and a
menu item under `webship.webship_root_menu`. Copy from the reference branch.

In `webship/views/res_config_settings_views.xml`, in the Synchronization block:
- a `<setting>` with the `webship_use_status_update_queue` checkbox,
- the old "Fetch order info" button paragraph gets
  `invisible="webship_use_status_update_queue"`,
- a new "Fetch changed orders" button (`ws_fetch_status_updates`),
- `webship_last_check_status_update` added to the Last Check Timestamps group.

### 2.5 Security — `webship/security/ir.model.access.csv`

```
access_webship_status_update,webship.status.update,model_webship_status_update,base.group_user,1,1,1,1
```

### 2.6 Manifest — `webship/__manifest__.py`

- Add `'views/status_update_views.xml'` to `data` (after `json_history_views.xml`).
- Bump `version` (reference branch: `19.0.1.2` → `19.0.1.3` for Part 1 →
  `19.0.1.4` for Part 2). No migration scripts needed for either part.

---

## Tests

Two test files under `webship/tests/` (plus `tests/__init__.py` importing them —
the directory did not exist before Part 1; follow `geodynamics/tests` conventions:
plain `TransactionCase`, no manifest entry needed).

**Test gotchas (apply to any branch):**
- Stored computes fire HTTP: writing `df_client_id_webship` on a partner triggers
  `_compute_code_client` → `fetchCode`; writing `df_picking_id_webship` on a
  picking triggers `_fetch_picking_code` → `fetch_picking_code`. Class-patch both
  in `setUp` (`mock.patch.object(WebShipHandler, 'fetchCode', ...)` /
  `mock.patch.object(StockPicking, 'fetch_picking_code', ...)`).
- Build the handler without `set_env` in Part 1 tests → all env-gated config
  lookups are skipped (give the fixture partner an email so the no-email
  validation doesn't fire).

**Part 1 — `test_sync_partner_hash.py`:** new client POSTs and stores hash +
timestamp; unchanged payload skips PUT; changed payload PUTs and updates hash;
failed PUT keeps the old hash (so the next run retries); `force=True` bypasses.

**Part 2 — `test_status_update_queue.py`:** a poll queues changed orders,
updates the matched picking exactly once via `fetchQuantities`, skips unknown
ids, advances the checkpoint, and sends `edited_after = checkpoint + 1s` in ISO
format; pending entries are upserted, not duplicated; a processing error is
recorded per entry; several entries for one picking → one update; cron is a
no-op with the toggle off; the old flow is skipped with the toggle on.

Run: `odoo-bin -d <testdb> -u webship --test-tags /webship --stop-after-init`

---

## Rollout & verification

1. Upgrade the module: `-u webship`. New columns/table appear; no data migration.
2. **Part 1 self-heals:** all partners start with an empty hash → the first sync
   round does one final full PUT per distinct customer (baselining), after that
   steady-state cron runs produce **zero** client PUTs.
3. **Part 2 rollout:** tick "Incremental status updates (edited_after)" in
   Settings → Stoqflow → Synchronization, activate the
   "Stoqflow fetch changed orders (status updates)" cron, pick the interval.
   Optionally set "Status updates last check" first (empty = look back 24h).
   The old status cron can stay active — it no-ops while the toggle is on.
4. **Fallback:** untick the checkbox. Old behavior returns instantly; the new
   cron becomes a no-op. Nothing else to revert.
5. **Measuring:** enable the "Log JSON payloads" setting
   (`webship.log_json`) and inspect `webship.json.history`:
   - Part 1: count rows with `method = 'PUT'` and endpoint starting `clients/`
     across two consecutive "Process pending orders" runs — run 2 must be zero.
   - Part 2: compare GET volume per status-cron run before/after the toggle.
   - Edit a partner's phone → exactly one `PUT clients/{id}` on the next order
     sync; `df_last_webship_sync` updates on the partner form.

## Porting checklist

- [ ] Part 1: field on `res.partner`, `hashlib` import, `_client_payload_hash`,
      `sync_partner` branch rewrite + `force` kwarg, `force=True` in the partner
      sync button.
- [ ] Part 2: `models/status_update.py` + `__init__.py` import, settings toggle +
      checkpoint field + gate in `ws_sync_statusses_since_last` + manual button,
      `status_update_views.xml` + settings view edits, access CSV row, cron record,
      manifest data entry.
- [ ] Bump manifest version; run the two test files; verify via
      `webship.json.history` on staging.
- [ ] Branch differences to watch: method/field names above are anchors — if a
      branch renamed `fetchQuantities`, `ws_sync_statusses_since_last`, or the
      `df_*_webship` fields, adapt the anchors; the design is unchanged.
