# Test cases — risk assessment (dry test)

Companion to `test_cases.md`. A **static code review ("dry test")**, not a test run: each scenario in
`test_cases.md` is analysed against the current branch code and scored **0–10**, where
**10 = practically cannot fail** and **0 = very likely to fail**, with the code path (`file:line`) and the
reason grounded in what the code actually does.

> Method: every scenario was re-verified against the source on this branch. Where a scenario is backed by
> an automated test in `webship/tests/`, the score reflects both the implementation and the test coverage.
> Regression tests for the fixes made alongside this review were added (`TestQueryEncoding`,
> `TestPartnerMatchBlankSequence`, `TestRetourSaleOrderMatch`, `TestConnectionCredentials`); see
> `running_tests.md` for how to run the suite.
> Several defects flagged in earlier reviews (the `match_product` KeyError, the delivery-child singleton
> crash, the unread "never send" flag, the multi-location stock over-count, the manual-apply zeroing) have
> since been **fixed** and now score high — this document reflects the code as it stands, not its history.

## Priority fixes (score ≤ 4 — most likely to fail)

All items originally in this tier have been **resolved or consciously accepted** this session:

| # | Scenario | Original | Outcome |
|---|----------|:---:|---------|
| 24a / 7 | Client/supplier `vat`/`email` GETs not URL-encoded | 3 | **Fixed** — `quote(str(x), safe='')` at all sites |
| 24c | Write-retry could duplicate a POST | 3 | **Closed** — mitigated by order unique constraint + `_find_existing_order` / PO `supplier_reference` pre-checks |
| 3d | PO without linked supplier | 3 | **Accepted** — auto-create is intended (consistent with client/order sync) |
| 7 (blank seq) | Partner match, blank sequence false "Success" | 3 | **Fixed** — manual Match reports "Success" only when actually linked |
| 8b | PO status, unchanged record → no update | 4 | **Non-issue** — guard exists in `fetchQuantities` (`picking.py:1171`); legacy poll uses `state != 'done'` |
| 11b | Retour → matching SO picks wrong order | 4 | **Fixed** — exact unique `name` match + `picking_id.sale_id` fallback |
| 11e / 11f | Backorder "cancel" is an irreversible DELETE | 4 | **Accepted** — rarely-used flow, slated for removal (JSON backup taken before delete) |
| 14b | Test connection, missing credentials | 4 | **Fixed** — `strip()` guard + `test()` wrapped in try/except |
| 8a | Redundant unguarded `button_validate()` in PO poll | 6 | **Fixed** — removed (setPickingQuantities already validates) |

---

## Section-by-section

### 1. Order Odoo → Stoqflow
- **1a** matching SKUs → perfect — **9**. `build_order_object` (`ws.py:2312`) emits one item per move, SKUs URL-encoded via `quote` (`ws.py:771`), qty = `product_uom_qty`. Caveats: a fractional qty errors (`ws.py:2391-2392`); a `type=='service'` or `quantity==0` line is silently dropped from `order_items` (`ws.py:2436`).
- **1b** product without SKU → blocked — **8**. Correctly blocks (`ws.py:2959-2962`), but raises **two** messages for the same product: `No SKU for line with product %s` (`ws.py:2373-2375`) and `SKU missing on product %s` (`ws.py:2380-2382`); neither exactly matches the spec wording.
- **1c** SKU not in Stoqflow → error — **9**. `get_webship_sku` → `None` (`ws.py:2595-2599`) → `SKU not found in Stoqflow for product %s (code: %s)` (`ws.py:2386-2388`). Handles the all-missing case too.

### 2. Status Order Stoqflow → Odoo
- **2a** picking updated, qty/products match — **8**. `setPickingQuantities` resets moves/lines to 0 then allocates by `df_product_id_webship` (`ws.py:1947,2001-2119`); unresolved products stay 0 with a warning (`ws.py:2154-2191`).
- **2b** two lines same product, 4 split over 1+3 — **8**. `pMap` aggregates the product total; `_allocate_qty_over_records` fills each move line up to its move-demand capacity (`ws.py:2047-2098`, `1616-1621`) → 1 + 3. Latent bug: capacity reads `move_id.product_uom_qty`, so a single move with multiple move lines would over-allocate.

### 3. Purchase Order Odoo → Stoqflow
- **3a** matching SKUs → perfect — **8**. `build_po_object` (`ws.py:2509`) mirrors the order builder. `warehouse_id` (`ws.py:2567`) is unvalidated — a missing mapping sends an empty value rather than erroring.
- **3b** no SKU → `SKU missing on product %s` (`ws.py:2558`, exact match) — **9** (plus the duplicate `No SKU…` message).
- **3c** SKU not in Stoqflow → `SKU not found in Stoqflow for product %s (code: %s)` (`ws.py:2561-2562`) — **9**.
- **3d** no linked supplier → error — **N/A (by design)**. `_sync_picking` intentionally **auto-creates** the supplier via `sync_supplier` when the partner has no `df_supplier_id_webship` (`ws.py:3075-3083`), consistent with how order sync auto-creates the client. The `"Supplier does not exist in Stoqflow"` message (`ws.py:2553-2554`) is a fallback that only surfaces if that creation fails. **Decision: keep as-is; the test-case expectation is superseded** — PO sync creates a missing supplier rather than erroring.
- **3e** draft/cancelled → error — **8**. Guarded (`ws.py:2889-2890`) but the string reads "cannot **by** synced" (typo) and differs from the spec.
- **3f** done → `Done pickings cannot be synced` (`ws.py:2892-2893`, exact) — **9**.

### 4. Product Sync Odoo → Stoqflow
- **4a** new → POST success — **8**. `df_product_id_webship == False` → `findProductBySku` returns `[]` → POST (`ws.py:2831-2844`). Minor: a missing `total-count` header also returns `[]`, so an existing product could be POSTed as a duplicate (`ws.py:741-742`).
- **4b** linked → PUT — **9**. Pops read-only `brand_id`/`sku`, PUTs; stale-id 404 recovery re-creates (`ws.py:2845-2860`).
- **4c** "Never send" → not synced — **9**. **Fixed.** The manual button checks `df_product_do_not_send_webship` and skips before `sync_product` (`product.py:166-170`).
- **4d** multiple variants → error — **9**. `UserError("Cannot sync: Product has multiple variants.")` when `len(product_variant_ids) != 1` (`product_template.py:73-76,83-86`); the variant-level method needs no guard (a variant is inherently singular).

### 5. Product Match Odoo ↔ Stoqflow
- **5a** one match → link — **9**. `findProductBySku` → `{'id':…}` on `total-count == 1`; stored on the product (`ws.py:2714-2728,744-747`).
- **5b** no SKU → `Please provide an SKU in Odoo` (`product.py:136-137`) — **8**. An empty-string (not `False`) code would slip past the guard.
- **5c** multiple → error — **9**. **Fixed.** `match_product` explicitly checks `isinstance(foundProduct, dict) and 'error' in foundProduct` and returns `['Multiple SKU found in Stoqflow']` before reading `['id']` (`ws.py:2720-2726`). No KeyError.

### 6. Partner/Client Sync Odoo → Stoqflow
- **6a** client → synced — **8** (`partner.py:198-199`, `force=True`). Depends on required billing fields (`ws.py:1288-1336`).
- **6b** supplier → synced — **8** (`partner.py:201-202` → `ws.py:1104-1169`).
- **6c** both → both — **8** (results concatenated, `partner.py:198-202`).
- **6d** neither → error — **7**. String is correct (`partner.py:205-206`), but `df_is_client_in_webship` defaults **True** (`partner.py:19`), so "neither" is never the out-of-box state. The multi-delivery-child singleton crash is **fixed** — manual sync uses a `limit=1` search and never reads `.id` on a recordset (`ws.py:1347-1348`).

### 7. Partner Match Odoo ↔ Stoqflow
- **7a/b/c/d** email / VAT / VAT→email / email→VAT — **7 / 8 / 8 / 8** (`ws.py:842-948,820-916`). All depend on an explicit match sequence (see blank-sequence bug) and on unencoded query params (24a).
- **7e** multiple → selection wizard — **7**. Works for **clients** (`partner.py:161-163` → `select_stoqflow_client.py:21`); the **supplier** branch never checks `.get('multiple')` (`partner.py:167-169`), so multiple supplier matches only dump an error, no wizard.
- **7f** none → error — **8** (e.g. `ws.py:948`, surfaced at `partner.py:178-185`).
- **7g** auto-match before send, multiple → no duplicate — **9**. **Fixed.** On `multiple`, `_sync_picking` returns an error early **without** calling `sync_partner`, so no duplicate client is created (`ws.py:2904-2931`).
- **Blank match sequence → false "Success"** — **8**. **Fixed this session.** The blank-sequence *skip* is intentional for the order-sync auto-match path; the manual `ws_match_partner` button now reports "Success" only when the contact is actually linked, otherwise an informative "nothing was linked" message (`partner.py:175-190`). (Supplier multi-match wizard parity is still open — see 7e.)
- **Email/VAT params not URL-encoded** — **3** (priority list, 24a).

### 8. Status Purchase Order Stoqflow → Odoo
- **8a** quantities applied correctly — **8**. **Fixed this session.** Qty mapping from `order_items[].received` is sound (`ws.py:2055-2066,2080-2151`); the redundant unguarded `button_validate()` in the PO poll has been removed — `setPickingQuantities` already validates a completed PO internally (`ws.py:2200-2210`), so the second validate (which could raise and abort the poll, and force-validate a picking 21c wants left open) is gone.
- **8b** unchanged `edited` timestamp → no update — **8**. The `df_ws_lastChangeDate == sEdited` guard **does exist**, in `fetchQuantities` (`picking.py:1171`) — the path used by the incremental status queue (feature 20, the recommended flow). The legacy PO poll instead relies on the `state != 'done'` gate (`ws.py:1557`), so a done PO is not re-updated either. Adequately handled on both paths; no change needed.

### 9. Stock Import Stoqflow → Odoo
- **9a** total/reserved/available written; multi-location — **9**. **Fixed.** Writes to a single resolved location's quant (`ws.py:3658-3694`), no longer the same total to every quant; `available` defaults to `total - reserved`.
- **9b** adjust on → Odoo qty = total — **7**. `inventory_quantity = total; _apply_inventory()` (`ws.py:3696-3698`). Not batched (per-item), and a Stoqflow `total:0` **does** zero on-hand for products present in the feed.
- **9c** adjust off → only Stoqflow fields — **8**. On-hand untouched, but an empty `0.0` quant is still **created** to hold the `df_webship_*` fields when none exists (`ws.py:3678-3687`).
- **9d** no SKU match → skipped — **10**. `if not product: continue` (`ws.py:3646-3647`); items without a `sku` skipped too.
- **9e** composed skipped — **8**. `type == "composed"` exact, **case-sensitive** (`ws.py:3636-3637`).
- **stock_quant manual apply** — **9**. **Fixed.** The dead `is None` branch is gone; now gates on `if not quant.df_last_check_webship:` and raises rather than zeroing an unfetched quant (`stock_quant.py:50-59`).

### 10. Parcel & Tracking Stoqflow → Odoo
- **10a** parcels → records — **6**. Full **delete + recreate** on every sync churns ids/links (`ws.py:2263-2287`), and `address_2` is dropped (model has only `df_shipping_address`; sync reads `address_1` only — `webship_parcel.py:27`, `ws.py:2304`).
- **10b** tracking → picking fields — **7**. Written to `carrier_tracking_ref` / `df_carrier_tracking_urls` (`ws.py:1966-1969`), but gated on truthiness — a re-sync with no parcels or empty tracking leaves stale values.
- **10c** one parcel with URL → open directly — **10** (`picking.py:1201-1208`).
- **10d** multiple → selection list — **10** (`picking.py:1209-1217`).

### 11. Retour & Backorder
- **11a** "Retour" in ref → retour — **8**. `'Retour' in supplier_ref`, `/purchase-orders` only (`retour_and_backorder.py:255,269`). Case-sensitive; orders never scanned.
- **11b** matching SO → return picking — **8**. **Fixed this session.** The SO lookup is now an **exact** `('name','=',ref)` match that only accepts a **unique** result (`retour_and_backorder.py:103-113`); on 0 or multiple matches it falls back to `picking_id.sale_id` rather than guessing, so a `SO12` ref can no longer resolve to `SO123`. The extraction regex (`Retour SO\d+` shape, `:94`) is intentionally left strict.
- **11c** no SO → no picking, warning — **9** (`retour_and_backorder.py:451-463`).
- **11d** duplicate → update — **10** (search-then-write + `UNIQUE(df_stoqflow_id)`, `:21-23,282,343-345`).
- **11e** PO parent_order_id → "cancelled" — **4** (unchanged). Irreversible HTTP **DELETE** (`webship_backorder.py:452`), gated on `auto_delete='True'` + create-time `process_code 'P'` + an existing Odoo backorder (`:285-286,424-425`); a full-order JSON backup is stored before deletion (`:368-374`). Known gap: a PO that is *both* `'Retour'` and has `parent_order_id` is tracked by both models and could be deleted. **Decision: leave as-is** — this flow is rarely used and is slated for removal.
- **11f** outbound parent_order_id → "cancelled" — **4** (unchanged). Same DELETE path/gating via `_fetch_backorders_for('orders',…)` (`webship_backorder.py:184-189,242-244,452`). **Decision: leave as-is** (see 11e).

### 12. Domain Filter & Process Code
- **12a** match → P — **8**. Default `'P'`; in-scope non-backorder pickings run the filter and stay P on match (`picking.py:290,340-388`).
- **12b** no match → M — **9** (`picking.py:388-390`); M excluded from the P-sync cron.
- **12c** mk_instance_id change → promote M→P — **9**. `write()` re-runs the filter with `promote=True` only for `'M'` (`picking.py:350-353`); `NA`/`E` never re-promoted (intended).
- **12d** invalid domain → no crash, warning, keep code — **8**. `safe_eval` + try/except logs and posts to chatter (`picking.py:380-398`); but a broken filter leaves everything at the default `'P'`, i.e. syncs everything.

### 13. Merge Picking Lines *(not a numbered scenario in `test_cases.md`; retained from earlier reviews)*
- No merge logic exists: `picking_get_line_items` emits one output per move with no grouping (`ws.py:1450-1468`), and `setPickingQuantities` keeps lines separate. So same-product/same-origin lines are **not** merged (10/10 for "different products/origins not merged"; the "should be merged" reading is not implemented). `merge_picking` is confirmed **dead/absent** — no definition and no XML reference anywhere — matching the "should not be used" expectation. — **10**.

### 14. Configuration & Connection
- **14a** valid creds → success — **9**. `GET products` → `success` notification (`res_config_settings.py:1000-1038`); `test()` now wraps the request in try/except (`ws.py:334-351`) so a transient network/TLS error returns a clean `danger` notification instead of a traceback.
- **14b** missing creds → error — **8**. **Fixed this session.** The guard now uses a `strip()`-based truthiness check on login/password/URL (`res_config_settings.py:1004-1013`), so an empty or whitespace value is caught and reported rather than falling through to a real request; `test()` is also hardened (14a).
- **14c** cron settings saved/restored — **9**. Direct guarded write/read on the `ir.cron` records with defaults on a missing cron (`res_config_settings.py:446-535,390-392`). Only fragility: resolution by hard-coded xml_id.

### 15. Backorder on Complete
- **15a** enabled → backorder for remaining — **6**. The **native** path validates received qty and processes `stock.backorder.confirmation` cleanly (`ws.py:1700-1785`) and is the only unit-tested path (`test_backorder_on_complete.py:70-89`), but it is gated behind `webship.use_native_backorder` which **defaults OFF**; the shipped **legacy** default force-completes via a non-standard `make_backorder()` + forced `_action_done()` (`ws.py:1827-1892`, `picking.py:1184-1193`) — fragile and untested.
- **15b** disabled → no backorder — **9**. Short lines → red syncresult message, no validate (`ws.py:1787-1797,1893-1907`); verified by `test_no_backorder_when_disabled`.

### 16. Courier Mapping Stoqflow → Odoo
- **16a** preferred_courier → carrier — **7**. Two paths (`setPickingQuantities` `ws.py:1973-1995`, `statusWsToOdoo` `ws.py:3223-3244`) resolve identically via `stoqflow_find_delivery_carrier` (`delivery.py:14-40`): exact unique-code match, then `=ilike` name fallback, both `limit=1`. Arbitrary only if two carriers link to the same courier/name.
- **16b** unlinked courier → warning — **8**. Two warning sinks, both surfaced (`ws.py:1989-1991`/`2231-2255`; `self._sync_warnings` → `picking.py:691-704`); identical text. The `_sync_warnings` note is dropped if the same sync also returns a fatal error (errors take priority).

### 17.
- **17a** queue error → E + email + continue — **9**. **Fixed/robust.** A picking is marked `'E'` on **both** a raised exception and a non-empty returned error list; soft failures (missing SKU/supplier/address) are *returned*, not swallowed, so they mark `'E'` + email too (`res_config_settings.py:876-932`, `ws.py:2367-2392,1111-1129,2940-2951`). Infinite looping is bounded by `df_sync_retry_count >= max_retries` (`:893-897`), and the email goes through `_ws_safe_send_error_email` (`:868-874`) which swallows mail errors so the queue can't abort.
- **17b** SKUs with spaces/special chars encoded — **9**. All SKU URL params `quote(str(...), safe='')` (`ws.py:455,471,495,578,733,771,3107,3126,3168`). Caveat: email/VAT params are **not** encoded (separate risk, 24a).
- **17c** no hard-coded Stoqflow ids — **10**. Confirmed: only the addon public key `ws.py:44`; no ObjectId-style literals anywhere.

### 18.
- **18a** client_number never set on create — **10**. The POST payload has no `client_number` (`ws.py:1389,1416`); it is only ever read back via `fetchCode` (`ws.py:398-403`).
- **18b** migrations never set 'P' — **10**. All migration scripts write only `'F'`/`'M'` (`migrations/1.1`, `19.0.1.2`, `post_migration.py`); none write `'P'`.

### 19. Redundant client PUT suppression (payload hash)
Backed by `test_sync_partner_hash.py` / `test_client_payload.py`.
- **19a** unchanged → no PUT — **9** (`ws.py:1420-1426`; test `:56-69`).
- **19b** changed field → one PUT + rehash — **8** (`ws.py:1427-1434`; test mutates only `phone` — other payload fields feed the hash but aren't individually exercised).
- **19c** new customer → POST once, store id + hash — **9** (`ws.py:1416-1418,1433`; test `:46-54`).
- **19d** re-match to different client → self-invalidates — **7**. Logic correct (hash embeds client id, `ws.py:1259-1268`) but **untested**.
- **19e** failed PUT → no hash stored — **9** (`ws.py:1437-1438`; test `:83-95`).
- **19f** manual button → always PUT — **9** (`partner.py:199` `force=True`; test `:97-105`).
- **19g** one cron run, many pickings same customer → only first PUTs — **6**. Relies on same-transaction ORM persistence (`ws.py:2346,2936`); correct but **untested**.

### 20. Incremental status updates (edited_after queue)
Backed by `test_status_update_queue.py`.
- **20a** incremental list fetch, matched pickings only — **9** (`status_update.py:89-194`; test `:53-85`).
- **20b** edited_after = checkpoint + 1s, ISO 8601 UTC — **9** (`status_update.py:228-229`; test asserts `2026-07-01T00:00:01Z`).
- **20c** checkpoint advances only when both calls succeed; failed poll retried — **7**. Impl `status_update.py:238-242`; the **failure/retry branch is untested**.
- **20d** re-change before processing → upsert — **9** (`status_update.py:118-131`; test `:87-102`).
- **20e** no unique picking → skipped — **8** (`status_update.py:80-87,150-154`; the >1-match branch is untested).
- **20f** per-entry error, doesn't block rest — **9** (`status_update.py:176-192`; test `:104-116`).
- **20g** same picking → fetchQuantities once — **9** (`status_update.py:168-178`; test `:118-137`).
- **20h** toggle no-op/skip old sync, reversible — **9** (`status_update.py:201-207`; tests `:139-155`).

### 21. Received-quantity purchase-order validation
Backed by `test_po_received_validation.py` / `test_backorder_on_complete.py`.
- **21a** received short (9 of 10) validated at received — **8** (`ws.py:2055-2066,1700-1825`; test `:68-73`).
- **21b** received 0 → move stays 0 — **9** (`ws.py:2017`; test `:75-79`).
- **21c** 0 across all lines → picking left open — **9** (`ws.py:1716-1724`; test `:75-81`).
- **21d** auto-backorder on → native split — **8** (`ws.py:1726-1743`; test `:70-89`).
- **21e** dev toggle native/legacy, default OFF — **5**. Impl `ws.py:1691-1698,2207-2210`, but **every test forces native=True** — the default-OFF legacy path is entirely **untested**.

### 22. Picking ↔ Stoqflow line comparison
Backed by `test_line_comparison.py`.
- **22a** exact match → all 'match' — **9** (`picking.py:940-962`; test `:77-82`).
- **22b** qty difference → 'mismatch' with both amounts — **9** (`picking.py:948-951`; test `:84-89`).
- **22c** missing_in_stoqflow / missing_in_odoo — **9** (`picking.py:944-947,965-979`; test `:91-103`).
- **22d** unresolved — **9** (`picking.py:909-937`; test `:105-112`).
- **22e** ignored SKUs, case/space-insensitive, both sides — **7**. Impl normalizes `strip().casefold()` (`picking.py:833-893`), but the test uses an exact `'SKU2'` — insensitivity coded, **not asserted**.
- **22f** order lookup validates the API actually filtered — **6**. Guard exists (`ws.py:507-516`) but the tests mock the lookup, so the guard is **untested**.

### 23. Link backorders to Stoqflow child orders
Backed by `test_link_backorders.py`.
- **23a** enabled → query children, exact-match link — **8** (`picking.py:1006-1072`, `ws.py:570-591`; the `?parent_order_id=` GET is mocked).
- **23b** no child → unlinked + differences shown — **8** (`picking.py:1076-1093`; test `:83-92`).
- **23c** child already linked elsewhere → not reused — **9** (`picking.py:1049-1057`; test `:102-110`).
- **23d** no Stoqflow ancestor → skipped — **9** (`picking.py:1030-1039`; test `:112-119`).
- **23e** disabled → unchanged — **9** (`picking.py:995`; tests `:141-158`).
- **23f** linking failure never blocks backorder/validation — **6**. Double try/except (`picking.py:994-1004`); correct by construction but **no test injects a failure**.

### 24. Encoding & robustness of Stoqflow API calls
- **24a** SKUs/ids URL-encoded in every GET — **8**. **Fixed this session.** Product/order/PO params were already `quote()`-encoded; the client/supplier `vat`/`email` GETs are now wrapped in `quote(str(x), safe='')` too (`ws.py:680,708,804,827,849,958,980,1001,1155,1412`). No encoding unit test yet.
- **24b** parent_order_id / by-id lookups quoted — **7**. `find_stoqflow_backorders` quotes `parent_order_id` (`ws.py:578`); by-id lookups quote (`ws.py:455,471,495`). Untested.
- **24c** session retry must not multiply a write — **8**. The session `Retry` still allows `POST`/`PUT` on `429/5xx` (`ws.py:61-67`), but duplicate creation is **mitigated by existing dedup**: orders are guarded by a server-side unique constraint *and* a pre-POST `_find_existing_order` lookup by `origin.id` that links instead of re-creating (`ws.py:2979-3017`); POs are guarded by a pre-POST `supplier_reference` lookup (`ws.py:3103-3140`); both have recover-and-link `try/except` on network errors. Residual theoretical gap: a PO endpoint returning a spurious 5xx *after* committing the create, within the same urllib3 retry loop — the PO pre-check is app-level, not a DB constraint — but 429/503 mean "not processed" and the next cron's pre-check links any stray PO. Left as-is by decision.

---

## Suggested next actions
1. ~~**URL-encode the client/supplier `email`/`vat` query params**~~ — **done** (`quote(str(x), safe='')` at all client/supplier `vat`/`email` GETs, matching the SKU paths), with a regression test (`TestQueryEncoding`).
2. ~~**Restrict the session `Retry` for writes**~~ — **not needed** (24c): duplicate POSTs are already prevented by the order unique constraint + `_find_existing_order` pre-check and the PO `supplier_reference` pre-check. Left as-is by decision.
3. ~~**Make 3d error**~~ — **decided: keep auto-create** (consistent with client/order sync); the 3d test-case expectation is superseded.
4. ~~**Guard the second `button_validate()` in the PO poll**~~ — **done**: removed it entirely; `setPickingQuantities` already validates the completed PO (8a).
5. ~~**Fix the missing-credentials check**~~ — **done**: `strip()`-based guard + `test()` wrapped in try/except (14b/14a).
6. ~~**Harden retour → SO matching**~~ — **done** (11b): exact unique `name` match, falls back to `picking_id.sale_id` on 0/multiple.
7. ~~**Reconsider the irreversible DELETE** for backorder cancellation~~ — **decided: leave as-is** (11e/11f); the flow is rarely used and slated for removal. The retour/backorder double-handling gap is accepted for now.
8. ~~Fix the false "Success" on a blank match sequence~~ — **done** (manual Match button reports "Success" only when actually linked). Still open: give suppliers the same multi-match wizard as clients (7e).
9. Add tests for the untested-but-shipping paths: the legacy backorder/validation default (15a/21e), the checkpoint failure/retry branch (20c), and write-retry behaviour (24c).
