# Test cases — risk assessment

Companion to `test_cases.md`. For each scenario a score **0–10**, where **10 = practically cannot fail**
and **0 = very likely to fail**, with the code path (`file:line`) and the reason. Scores are grounded in the
actual code, not the intent.

> This is a static code review, not a test run. The two things are complementary: the automated suite
> (`webship/tests/`) proves the happy paths it covers; this document flags where the code is likely to
> break, including paths with no automated coverage.

## Priority fixes (score ≤ 4 — most likely to fail)

| # | Scenario | Score | Problem |
|---|----------|:---:|---------|
| 5c | Product match, SKU matches multiple | **1** | `match_product` reads `foundProduct['id']` on a `{'error': ...}` dict → **KeyError crash**, no message (`ws.py:2664-2667`, `ws.py:735`). |
| 4c | "Never send to Stoqflow" product | **1** | The flag `df_product_do_not_send_webship` is **not read** in the manual product-sync path; clicking Sync still POSTs/PUTs it (`ws.py:2671`, only checked in order/picking flows). |
| 7 (blank seq) | Partner match with blank match sequence | **2** | `match_partner_by_sequence` returns no errors → button shows **"Success"** though nothing was matched/linked (`ws.py:868-870`, `partner.py:176-177`). |
| 6 (multi-delivery) | Client sync, partner with >1 delivery child | **3** | `deliveryAdress.id` on a non-singleton recordset → **ValueError: Expected singleton** (`ws.py:1302-1306`). |
| 9a (multi-loc) | Stock import, product in >1 Webship location | **3** | Same total/reserved/available written to **every** quant of the product (`ws.py:3543-3547`, `3582-3587`); with 9b on, physical stock is multiplied. |
| stock_quant | Manual "apply Webship stock" | **3** | `if quant.df_webship_totalstock is None` is dead (a Float is never None), so a never-set quant applies `0.0` and zeroes inventory (`stock_quant.py:47-53`). |
| 4d | Product template, multiple variants | **4** | Guard exists only on `product.template` (`product_template.py:72`); the variant-level sync method never checks variant count. |
| 7g | Auto-match on order sync, multiple matches | **4** | `'multiple'` is only logged and skipped; the following `sync_partner` then **creates a duplicate** client (`ws.py:2855-2866`). |
| 9b | Stock import, "adjust Odoo stock" on | **4** | Not batched; combined with 9a over-counts; a Stoqflow `total: 0` zeroes Odoo stock (`ws.py:3589-3591`). |
| 11e | PO backorder (not retour) "cancelled" | **4** | Implemented as HTTP **DELETE** (irreversible), and a "Retour"+parent_order_id PO is handled by both the retour flow and the delete flow (`webship_backorder.py:377`, `242-246`). |
| 17a | Queue error handling | **4** | Only a raised **exception** marks `'E'`+emails; soft failures (missing SKU/supplier/address) leave the picking `'P'` and re-run forever without notice; the un-guarded `_ws_send_error_email` inside `except` can abort the rest of the queue (`res_config_settings.py:854-876`, `picking.py:706-714`). |

---

## Section-by-section

### 1. Order Odoo → Stoqflow
- **1a** matching SKUs → perfect — **7**. `build_order_object` (`ws.py:2257`) emits one item per line, but a line with `type=='service'` or `quantity==0` is silently dropped from `order_items` with no error (`ws.py:2378-2381`).
- **1b** product without SKU → blocked — **7**. Blocks correctly, but the same product yields two different messages: `No SKU for line with product %s` (`ws.py:2314/2319`) and `SKU missing on product %s` (`ws.py:2326`).
- **1c** SKU not in Stoqflow → error — **6**. `SKU not found in Stoqflow for product %s` (`ws.py:2330`); but if the SKU pre-fetch returned an error dict, every product reports "not found", masking the real API failure (`ws.py:2539-2543`).

### 2. Status Order Stoqflow → Odoo
- **2a** picking updated, qty/products match — **7**. `setPickingQuantities` maps `picks` (outbound) onto moves (`ws.py:1582-1599`).
- **2b** multiple lines same product, 4 split over 1+3 — **7**. `_allocate_qty_over_records` fills each move line up to its capacity (`product_uom_qty`), so 4 → 1 on the cap-1 line and 3 on the cap-3 line. Correct, but depends on deterministic ordering and matching `df_product_id_webship`.

### 3. Purchase Order Odoo → Stoqflow
- **3a** matching SKUs → perfect — **7**.
- **3b** no SKU → `SKU missing on product %s` (`ws.py:2500`) — **7** (same double-message as 1b).
- **3c** SKU not in Stoqflow → error (`ws.py:2504`) — **6**.
- **3d** no linked supplier → `Supplier does not exist in Stoqflow` (`ws.py:2497`) — **6**. `warehouse_id` (`ws.py:2511`) is unguarded; a missing warehouse mapping sends an empty value rather than erroring.
- **3e** draft/cancelled → error — **8**. Works, but the string reads "cannot **by** synced" (typo, `ws.py:2828`).
- **3f** done → error (`ws.py:2831`) — **9**.

### 4. Product Sync Odoo → Stoqflow
- **4a** new → POST success — **6**. Works, but `has_stock = product.type == 'product'` is stale on Odoo 19 (no `'product'` type) → always `False` (`ws.py:2691`).
- **4b** linked → PUT — **8**. Stale-id recovery re-creates; recursion has no depth guard (`ws.py:2793-2799`).
- **4c** "Never send" → not synced — **1** (see priority list).
- **4d** multiple variants → error — **4** (see priority list).

### 5. Product Match Odoo ↔ Stoqflow
- **5a** one match → link — **7**. Relies on the `total-count` header; if absent, reports "not found" (`ws.py:724-732`).
- **5b** no SKU → `Please provide an SKU in Odoo` (`product.py:137`) — **9**.
- **5c** multiple → error — **1** (KeyError crash; see priority list).

### 6. Partner/Client Sync Odoo → Stoqflow
- **6a** client → synced — **8** (`partner.py:198`, `force=True` bypasses the hash skip).
- **6b** supplier → synced — **7**.
- **6c** both → both — **8** (results concatenated).
- **6d** neither → error — **5**. String is correct (`partner.py:205`), but `df_is_client_in_webship` defaults True so a fresh partner never lands here; and a partner with >1 delivery child crashes first (score 3 case above).

### 7. Partner Match Odoo ↔ Stoqflow
- **7a/b/c/d** email / VAT / VAT→email / email→VAT — **7** each (`ws.py:805-933`). Query params are **not** URL-encoded (`?vat=`/`?email=` concatenated raw), so a `+`/space/`#` breaks the query (`ws.py:789/812/834`).
- **7e** multiple → selection wizard — **5**. Works for **clients** only; suppliers have no wizard, just an error (`partner.py:161-169`, `124-143`).
- **7f** none → error — **8**.
- **7g** auto-match before send — **4** (duplicate on multiple; see priority list).
- Blank-sequence false "Success" — **2** (see priority list). "Both" flags: a successful client match is overwritten by the supplier result in the display (`partner.py:164-169`).

### 8. Status Purchase Order Stoqflow → Odoo
- **8a** quantities applied correctly — **7** (native path) / lower on the legacy path. Uses `order_items[].received` for POs (`ws.py:1601-1613`); validation strategy is switchable (`webship.use_native_backorder`).
- **8b** unchanged `edited` timestamp → no update — **8**. `_fetch_and_update` compares `df_ws_lastChangeDate == sEdited` and returns early (`picking.py:792-796`).

### 9. Stock Import Stoqflow → Odoo
- **9a** total/reserved/available written — **7**; multi-location over-count — **3** (priority list). No consistency check; `available` derived if absent (`ws.py:3538-3587`).
- **9b** adjust on → Odoo qty = total — **4** (priority list).
- **9c** adjust off → only Stoqflow fields — **8**. Correct, but still creates empty quants when none exist (`ws.py:3576-3580`).
- **9d** no SKU match → skipped — **7**. `default_code` exact match, `limit=1`, silent (no counter/log).
- **9e** composed skipped — **6**. Exact-string `type == "composed"` dependency (`ws.py:3524`).

### 10. Parcel & Tracking Stoqflow → Odoo
- **10a** parcels → records — **7**. Full delete+recreate on every fetch churns ids/links; `address_2` dropped (`ws.py:2202-2255`).
- **10b** tracking → picking fields — **7**. Overwrites wholesale; empty joins leave stale values (`ws.py:1908-1918`).
- **10c** one parcel with URL → open directly — **9** (`picking.py:1154-1161`).
- **10d** multiple → selection list — **8** (`picking.py:1162-1170`).

### 11. Retour & Backorder
- **11a** "Retour" in ref → retour — **6**. Case-sensitive substring, `/purchase-orders` only (`retour_and_backorder.py:268`).
- **11b** matching SO → return picking — **5**. `ilike` substring + `limit=1` can pick the wrong SO; regex requires `Retour SO\d+` shape (`retour_and_backorder.py:94-105`).
- **11c** no SO → no picking, warning — **8** (`retour_and_backorder.py:451-463`).
- **11d** duplicate → update — **9** (double-guarded incl. SQL unique, `:21-23`, `:282`).
- **11e** PO parent_order_id → "cancelled" — **4** (DELETE + retour/backorder conflict; priority list).
- **11f** outbound parent_order_id → "cancelled" — **5**. Same delete path; `created_after` pointer can miss orders that gain a parent later (`webship_backorder.py:192-196`).

### 12. Domain Filter & Process Code
- **12a** match → P — **8** (`picking.py:334-335`).
- **12b** no match → M — **8** (`picking.py:382-384`).
- **12c** mk_instance_id change → promote M→P — **7**. Only re-evaluates records already at `'M'` (`picking.py:344-347`); `'NA'/'E'` never re-promoted.
- **12d** invalid domain → no crash, warning, keep code — **7**. `safe_eval` + `except` (`picking.py:387-392`); but leaving everything `'P'` means a broken filter syncs everything.

### 13. Merge Picking Lines
- **13a** same product/UoM/loc/origin merged — **8** (`picking.py:1191-1224`).
- **13b** different products/locations not merged — **9**.
- **13c** same product different origins not merged — **9** (origin in the key).
- **13d** `merge_picking` no longer used — **10**. Confirmed dead: `_schedule_merge_after_create` is defined but never called, the `ws.py` call is commented out, no XML references it. Matches the "should not be used" expectation.

### 14. Configuration & Connection
- **14a** valid creds → success — **8** (`res_config_settings.py:944-976`).
- **14b** missing creds → error — **6**. Check is `== False` only; an empty string or whitespace falls through to a real request (`res_config_settings.py:948-957`).
- **14c** cron settings saved/restored — **7**. Direct write/read on the `ir.cron` records (`:428-464`, `:497-515`); a missing/renamed cron silently shows disabled + reset interval.

### 15. Backorder on Complete
- **15a** enabled → backorder for remaining — **6** (native path processes Odoo's backorder confirmation; the legacy path is fragile — hence the `webship.use_native_backorder` toggle). Live wizard processing is the least-verified part.
- **15b** disabled → no backorder — **8** (short lines → warning, no validate).

### 16. Courier Mapping Stoqflow → Odoo
- **16a** preferred_courier → carrier — **6**. `limit=1` name/code fallback can resolve arbitrarily; the link is manual; two independent code paths (`setPickingQuantities` and `statusWsToOdoo`) must stay in sync (`delivery.py:14-40`, `ws.py:1922-1944`, `3132-3153`).
- **16b** unlinked courier → warning — **7**. Non-blocking; two separate warning sinks (`warnings` vs `self._sync_warnings`).

### 17.
- **17a** queue error → E + email + continue — **4** (priority list).
- **17b** SKUs with spaces/special chars encoded — **8**. All **SKU** params `quote()`-encoded (`ws.py:718/756/440/...`). Caveat: **email/VAT** params are NOT encoded (relates to 7) — a separate risk, not this scenario.
- **17c** no hard-coded Stoqflow ids — **10**. Confirmed: only `x-addon-public-key` (`ws.py:44`); no ObjectId-style literals anywhere.

### 18.
- **18a** client_number never set on create — **10**. Confirmed: the POST payload has no `client_number` (`ws.py:1338-1365`).
- **18b** migrations never set 'P' — **10** for the stated rule (no migration writes `'P'`). Note: they *demote* in-scope pending pickings without a Stoqflow id to `'M'`, so a genuinely pending `'P'` at upgrade time won't auto-push afterward.

### 19–24. Features added this session
Backed by the automated tests in `webship/tests/` (mocked HTTP).
- **19** Redundant client PUT suppression — **8**. Hash skip/force/re-match/failed-keeps-hash covered by `test_sync_partner_hash.py`.
- **20** Incremental status queue — **8**. Checkpoint, upsert, per-entry errors, toggle gating covered by `test_status_update_queue.py`.
- **21** Received-quantity PO validation — **8** (received-short/zero tested); **21d** live backorder creation — **6** (wizard processing not unit-verified).
- **22** Line comparison — **9**. All five statuses + ignored SKUs covered by `test_line_comparison.py`.
- **23** Link backorders — **7**. Match/mismatch/among-several/already-linked/no-ancestor covered by `test_link_backorders.py`; runs **synchronous** HTTP inside `_create_backorder` (guarded, never blocks) — the live wizard/HTTP path is the least-verified part.
- **24** Encoding & retry robustness — **8**. SKU/id params quoted; email/VAT params are the known gap (7/17b).

---

## Suggested next actions
1. Fix the two crashers first: **5c** (`match_product` KeyError on multiple matches) and the **>1 delivery child** singleton crash (6).
2. Honour **4c** (`df_product_do_not_send_webship`) in the manual product-sync path, or change the scenario's expectation.
3. Make **17a** mark soft-failed pickings (return non-empty error list) as `'E'` and guard `_ws_send_error_email`, so the queue can't silently loop or abort.
4. URL-encode email/VAT query params (7 / 24) with `quote()`, matching the SKU paths.
5. Bound the stock-import writes to one quant per (product, location) and skip the write when the value is unchanged (9a/9b/stock_quant).
