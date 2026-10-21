This are the most test cases to verify if the component works correct. Please analyze them one by one and say if there's a possibility that an error can appear in the case, in a scale 0 to 10. 10 being impossible to happen, and 0 being very likely to happen. 

The rest API is available on https://api-documentation.stoqflow.com/ and stored in this branch under the filename 

1. Order Odoo -> stoqflow

a) An order with 10 lines with products with matching SKU's between stoqflow and odoo must come through perfectly. Quantities and products must match.

b) An order with 10 lines containing one or more products without an sku may not go through. Error must be shown: no SKU for product(s) ...

c) An order with 10 lines containing one or more products with an sku that does not exist in stoqflow must throw an error.

2. Status Order Stoqflow -> Odoo

a) Picking must be updated in Odoo perfectly. Quantities and products must match

b) Picking containing different lines of the same product must be updated perfectly. For example if you have two lines: 1 time product A and 3 times product A on different and you get 4 from stoqflow, the 4 must be divided on the lines in Odoo.

3. Purchase Order Odoo -> Stoqflow

a) A purchase order with multiple lines with products with matching SKU's between stoqflow and odoo must come through perfectly. Quantities and products must match.

b) A purchase order with one or more products without an SKU may not go through. Error must be shown: SKU missing on product ...

c) A purchase order with one or more products with an SKU that does not exist in stoqflow must throw an error: SKU not found in Stoqflow for product ...

d) A purchase order without a linked supplier in stoqflow must throw an error: Supplier does not exist in Stoqflow.

e) A picking in draft or cancelled state must not be synced to stoqflow. Error must be shown: Draft or cancelled orders cannot be synced.

f) A picking in done state must not be synced to stoqflow. Error must be shown: Done pickings cannot be synced.

4. Product Sync Odoo -> Stoqflow

a) A product with a valid SKU that does not yet exist in stoqflow must be created as a new product in stoqflow. The sync result must show success.

b) A product that is already linked to a stoqflow product (has a stoqflow product ID) must be updated in stoqflow. The sync result must show success.

c) A product flagged as "Never send this product to Stoqflow" must not be synced.

d) A product template with multiple variants must throw an error: Cannot sync: Product has multiple variants.

5. Product Match Odoo <-> Stoqflow

a) A product with an SKU that matches exactly one product in stoqflow must be linked correctly. The stoqflow product ID must be stored on the odoo product.

b) A product without an SKU must show error: Please provide an SKU in Odoo.

c) A product with an SKU that matches multiple products in stoqflow must show an error.

6. Partner/Client Sync Odoo -> Stoqflow

a) A partner flagged as client must be synced to stoqflow clients. The sync result must show Success.

b) A partner flagged as supplier must be synced to stoqflow suppliers. The sync result must show Success.

c) A partner flagged as both client and supplier must be synced to both stoqflow clients and suppliers.

d) A partner not flagged as client or supplier must show error: Please set to client or supplier.

7. Partner Match Odoo <-> Stoqflow

a) Match by email only: a partner with an email matching exactly one stoqflow client must be linked correctly.

b) Match by VAT only: a partner with a VAT number matching exactly one stoqflow client must be linked correctly.

c) Match by VAT then email: if no stoqflow client is found by VAT, the system must fall back to searching by email.

d) Match by email then VAT: if no stoqflow client is found by email, the system must fall back to searching by VAT.

e) If multiple stoqflow clients are found for a partner, a selection wizard must open allowing the user to pick the correct one.

f) If no stoqflow client is found at all, an error must be shown.

g) When "match client when order syncs" is enabled, the contact must be automatically matched to a stoqflow client before the order is sent to stoqflow.

8. Status Purchase Order Stoqflow -> Odoo

a) Purchase order quantities fetched from stoqflow must be applied correctly to the picking in Odoo. Products and quantities must match.

b) If the stoqflow record has not changed since the last check (same edited timestamp), no update must be performed.

9. Stock Import Stoqflow -> Odoo

a) Stock levels imported from stoqflow must be written correctly to the stock quant: total stock, reserved stock, and available stock must match.

b) With "adjust Odoo stock automatically" enabled, the Odoo inventory quantity must be updated to match the stoqflow total stock.

c) With "adjust Odoo stock automatically" disabled, only the stoqflow fields on the quant must be written. The Odoo inventory quantity must remain unchanged.

d) A product that does not exist in Odoo (no matching SKU) must be skipped during import.

e) Composed products in stoqflow must be skipped during import, only basic products carry physical stock.

10. Parcel & Tracking Stoqflow -> Odoo

a) Parcels from a completed stoqflow order must be synced to webship.parcel records on the picking. All parcel details (tracking number, dimensions, shipping info) must be stored.

b) Tracking numbers and tracking URLs from parcels must be written to the picking fields (carrier_tracking_ref and tracking reference URLs).

c) When a picking has exactly one parcel with a tracking URL, clicking the tracking button must open that URL directly.

d) When a picking has multiple parcels with tracking URLs, clicking the tracking button must open a selection list to choose which parcel to track.

11. Retour & Backorder Processing

a) A purchase order in stoqflow with "Retour" in the supplier_reference must be detected as a retour and stored as a retour record in Odoo.

b) A retour with a matching sale order (extracted from the supplier_reference, e.g. "Retour SO123") must automatically create a return picking in Odoo.

c) A retour without a matching sale order must not create a return picking. A warning must be logged.

d) A duplicate retour (same stoqflow ID) must update the existing retour record instead of creating a new one.

e) A purchase order in stoqflow with a parent_order_id (backorder) that is not a retour must be cancelled in stoqflow automatically.

f) An outbound order in stoqflow with a parent_order_id (backorder) must be cancelled in stoqflow automatically.

12. Domain Filter & Process Code

a) A new picking that matches the configured domain filter must get process code P (pending) and be synced automatically.

b) A new picking that does not match the configured domain filter must get process code M (manual) and must not be synced automatically.

c) When mk_instance_id changes on a picking with process code M, the domain filter must be re-evaluated. If the picking now matches, the process code must be promoted to P.

d) An invalid domain filter must not crash the system. A warning must be logged and the picking must keep its current process code.

e) A picking with process code M (manual) is never pushed to Stoqflow, so it has no Stoqflow order/PO id by design. The status sync must leave its result column blank instead of writing "No Stoqflow order ID or PO ID set on this picking", and must clear that message when an earlier run already stored it. Pickings that are supposed to be in Stoqflow (P/E/F) must still report the missing id.

14. Configuration & Connection

a) Testing the API connection with valid credentials must return a success notification.

b) Testing the API connection with missing credentials (username, password, or URL) must show an error notification.

c) Cron job settings (process pending orders, fetch order info & quantities, import stock, send daily report) must be saved and restored correctly when toggling the active state and changing intervals.

15. Backorder on Complete

a) With "auto create backorder on complete" enabled, when stoqflow marks an order as completed with partial quantities, a backorder must be created in Odoo for the remaining quantities.

b) With "auto create backorder on complete" disabled, no backorder must be created even if stoqflow reports partial quantities.

16. Courier Mapping Stoqflow -> Odoo

a) When a stoqflow order has a preferred_courier set, the delivery carrier on the Odoo picking must be updated to the matching carrier. The courier must be linked to a delivery carrier in Odoo via the stoqflow courier settings.

b) When a stoqflow order has a preferred_courier that is not linked to any delivery carrier in Odoo, a warning must be shown in the sync result: Courier '...' present on Stoqflow order but not linked in Odoo.

17.
a) when an error happens treating the queue of orders, the line is marked 'E' error, a message is sent by e-mail, and the rest of the queue lines with status P is treated.

b) products with spaces and rare signes in the sku's in Odoo are synced perfectly (ensure proper encoding)

c) other than addon public key, there are no hard coded stoqflow ids found in the code

18.
When a client is created, client_number is never set when creating the client.

Never set a record by status P (process code p) when migrating. Because this will auto send to stoqflow

19. Redundant client PUT suppression (payload hash)

a) Syncing an order for a customer already present in Stoqflow, with nothing changed on the partner, must NOT send a PUT to clients/{id} (the stored payload hash matches, so the call is skipped).

b) After changing a field that is part of the client payload (name, street, city, zip, country, email, phone, mobile, vat), the next order sync must send exactly one PUT clients/{id} and re-store the new hash.

c) A brand-new customer must POST clients exactly once and store both the Stoqflow client id and the payload hash.

d) When a partner is re-matched to a different Stoqflow client (df_client_id_webship changes), the next sync must PUT again — the hash embeds the client id, so it self-invalidates.

e) A failed PUT (non-200 / API error) must NOT store the hash, so the next run retries the PUT.

f) The manual "Sync" button on the partner must always PUT even when the payload is unchanged (force bypasses the hash check).

g) During a single cron run over many pending pickings for the same customer, only the first picking may PUT the client; the rest must skip because the hash is persisted within the same transaction.

20. Incremental status updates (edited_after queue)

a) With "Incremental status updates" enabled, the cron must fetch only orders/purchase-orders changed since the last check via GET ...?edited_after=..., and update only the matched pickings — not one API call per open picking.

b) edited_after must be sent as (last checkpoint + 1 second) in ISO 8601 UTC format, so the newest record of the previous poll is not refetched on every run.

c) The checkpoint (webship.last_check_status_update) must advance to the newest 'edited' timestamp seen, and only when BOTH the orders and purchase-orders list calls succeed; a failed poll must be retried on the next run.

d) A record that changes again before the queue is processed must refresh its pending entry, not create a duplicate (upsert by Stoqflow id + object type + pending state).

e) A queue entry whose Stoqflow id has no unique matching picking must be marked 'skipped', not error.

f) A processing error on one entry must be recorded as 'error' on that entry only and must not block the rest of the queue.

g) Several queue entries pointing at the same picking must trigger fetchQuantities only once per picking per run.

h) With the setting disabled the incremental cron must be a no-op and the old per-picking status sync must run; with it enabled the old sync must be skipped. Toggling must be reversible with no data loss.

21. Received-quantity purchase-order validation

a) A completed PO where a line was received short (e.g. received 9 of 10 ordered) must validate the Odoo receipt at the RECEIVED quantity (9), never the ordered quantity.

b) A completed PO line with received 0 must never be validated as received at the ordered quantity; that move must stay at 0.

c) A completed PO with 0 received across all lines must leave the picking open (nothing to validate), not mark it fully done.

d) With "auto create backorder on complete" enabled, the unreceived remainder must be split into a backorder via Odoo's backorder confirmation, not force-completed at ordered quantities.

e) The developer-mode "Native backorder validation for receipts" toggle must switch between the native path (a-d) and the legacy path, and default OFF (legacy) so behaviour is unchanged until it is enabled.

22. Picking <-> Stoqflow line comparison

a) A picking whose products and ordered quantities exactly match its Stoqflow order must return every line as 'match' with no problems.

b) A quantity difference on a line must be reported as 'mismatch', showing both the Odoo and the Stoqflow amount.

c) A product present on the Odoo picking but absent from the Stoqflow order must be 'missing_in_stoqflow'; a product present on the Stoqflow order but absent from the picking must be 'missing_in_odoo'.

d) A picking product with no resolvable Stoqflow id and no matching SKU must be 'unresolved'.

e) Products whose SKU is on the Ignored SKUs list must be excluded from both sides (matching case- and space-insensitive).

f) The order lookup must validate that the API actually filtered on origin_number / origin_id (guard against a silently-ignored filter returning every order and matching the wrong one).

23. Link backorders to Stoqflow child orders

a) With "Link backorders" enabled, the moment Odoo creates a backorder it must query GET /{orders|purchase-orders}?parent_order_id=<parent Stoqflow id>, and when a child's contents match the backorder exactly, link it (store the child's Stoqflow id + number on the backorder).

b) When no child matches exactly, the backorder must be left UNLINKED and the line differences must be shown on df_picking_syncresult_webship, so it is clear the picking was not linked and why.

c) A Stoqflow child already linked to another Odoo picking must not be linked a second time.

d) A backorder whose ancestor chain has no Stoqflow id must be skipped (there is no parent order to query).

e) With the setting disabled, backorder creation must behave exactly as before — no query, no linking.

f) A failure during linking (API error / exception) must never block the backorder or the transfer validation that created it.

g) Splitting a parent leaves two children: the processed part (status completed/cancelled, with a delivered timestamp and received_product_items) and the open remainder. When both match the backorder's contents, the OPEN child must be linked — the processed one is only a last-resort fallback and the runner-up must be named in df_picking_syncresult_webship.

h) When several open children match, the lowest order-number suffix (PO00028-02 before PO00028-03) wins, so the oldest open remainder is linked first.

i) When nothing matches but a child holds exactly the not-received quantities of a processed sibling (quantity - received), that child must be named in df_picking_syncresult_webship as the likely counterpart.

j) One Odoo PO received in three rounds gives two Odoo backorders, each of which must land on its own Stoqflow child: the lookup queries the nearest linked ancestor first (the second backorder is a split of the first) and falls back to the ancestors above it when Stoqflow numbers every split off the original order. Two backorders must never share a child, even when they hold identical quantities.

k) Odoo and Stoqflow create their backorders in the same order, so the still-unlinked open children, oldest first (order-number suffix), line up with the still-unlinked Odoo backorders. The child at this backorder's position wins the ranking, and an earlier backorder that was left unlinked shifts the position by one — so the second Odoo backorder takes the second child even when both children hold the same quantities.

l) Every lookup writes one trace block to the server log — at WARNING when nothing was linked — listing the parents queried, every candidate with its status/quantities/comparison, the chronology and the outcome. With "Verbose logging" enabled the same block (plus the raw children payload) is stored as a webship.json.history trace row on the backorder, so it can be exported from the UI; with the setting off, no row is written.

m) Outbound orders report what was handled as "picks" (plus parcels) instead of "received" on the order items, so the shipped half of a split must still be recognised as processed, and the expected remainder must be computed as quantity - picked, counting a substituted pick against its parent_product_id.

n) A backorder is created with process code M (Manual) so the cron never pushes it to Stoqflow as a new order. The moment it is linked to a Stoqflow child the order does exist there, so the process code must become F (Sent to Stoqflow) and the change must be noted in the chatter. A backorder that stays unlinked keeps M.

24. Encoding & robustness of Stoqflow API calls

a) SKUs and Stoqflow ids containing spaces or special characters must be URL-encoded in every GET (products, orders, purchase-orders, clients) so the query stays well-formed (relates to 17b).

b) A parent_order_id or order id containing special characters must be safely quoted in the parent_order_id query and the by-id lookups.

c) The shared requests session's automatic retry (429/5xx) must not multiply a write once the redundant-call suppression (19) is in place — only meaningful PUT/POST calls should ever be retried.
