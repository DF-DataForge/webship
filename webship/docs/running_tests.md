# Running the webship tests

The module ships a unit-test suite under `webship/tests/` (plain
`odoo.tests.common.TransactionCase`, all external HTTP mocked). The tests are
registered in `webship/tests/__init__.py` and are discovered automatically when
the module is upgraded with `--test-enable` / `--test-tags`.

> **"The command prints nothing" is expected.** With `> /tmp/webship_test.log 2>&1`
> all output (Odoo logs to stderr) goes to the log file, so the terminal stays
> silent and returns when the run finishes — the tests still ran. Read the log
> for the result (see *Reading the results* below), or use `2>&1 | tee
> /tmp/webship_test.log` instead of the redirect to watch it live **and** save it.

## Run the whole webship suite

```bash
./odoo-bin -c /etc/odoo19.conf -d Test1901 -u webship \
  --test-tags /webship \
  --stop-after-init > /tmp/webship_test.log 2>&1
```

Run from the Odoo source directory (where `odoo-bin` lives, e.g.
`/opt/odoo19`), or use its full path.

- `-c /etc/odoo19.conf` — the Odoo server config (db host/user, addons_path, …).
- `-d Test1901` — the **test database** to run against (upgraded in place; use a
  disposable DB, not production).
- `-u webship` — upgrade the module so the latest code/tests are loaded.
- `--test-tags /webship` — run every test in the `webship` module.
- `--stop-after-init` — exit once the tests finish.
- `> /tmp/webship_test.log 2>&1` — capture all output (Odoo logs the results to
  stderr).

## Run only specific test classes

Comma-separate `/<module>:<ClassName>` tags. Example (two classes):

```bash
./odoo-bin -c /etc/odoo19.conf -d Test1901 -u webship \
  --test-tags /webship:TestBackorderOnComplete,/webship:TestCourierMapping \
  --stop-after-init > /tmp/webship_test.log 2>&1
```

Run just the classes added for the dry-test fixes:

```bash
./odoo-bin -c /etc/odoo19.conf -d Test1901 -u webship \
  --test-tags /webship:TestQueryEncoding,/webship:TestPartnerMatchBlankSequence,/webship:TestRetourSaleOrderMatch,/webship:TestConnectionCredentials \
  --stop-after-init > /tmp/webship_test.log 2>&1
```

## Reading the results

The command redirects everything to `/tmp/webship_test.log`. Check the tail for
the summary line:

```bash
tail -n 40 /tmp/webship_test.log
grep -E "FAIL|ERROR|failed|tests? in" /tmp/webship_test.log
```

A clean run ends with two summary lines like:

```
odoo.tests.stats: webship: 8 tests 2.23s 841 queries
odoo.tests.result: 0 failed, 0 error(s) of 4 tests when loading database 'Test1901'
```

`0 failed, 0 error(s)` means everything passed. Any `FAIL`/`ERROR` lines name the
failing test method and the assertion. (The `stats` line counts test *methods*;
the `result` line counts test *cases/classes* — both being non-zero with no
failures is normal.)

## Test classes

| Class | Covers |
|-------|--------|
| `TestBackorderOnComplete` | Backorder-on-complete enabled/disabled (15) |
| `TestClientPayload` | Client POST payload shape (18a) |
| `TestConnectionCredentials` | **Test connection: empty/whitespace creds → danger; `test()` error handling (14b/14a)** |
| `TestCourierMapping` | preferred_courier → carrier + unlinked warning (16) |
| `TestDomainFilter` | Domain filter → process code P/M, promotion (12) |
| `TestEmptyOrder` | All-lines-excluded order not sent (1a edge) |
| `TestLineComparison` | Picking ↔ Stoqflow line comparison statuses (22) |
| `TestLinkBackorders` | Link backorders to Stoqflow child orders (23) |
| `TestOrderAutoMatch` | Auto-match client on order sync (7g) |
| `TestParcelsTracking` | Parcels + tracking sync (10) |
| `TestPartnerMatchBlankSequence` | **Manual Match: no false "Success" on a blank sequence (7)** |
| `TestPerformDelete` | performDelete behaviour |
| `TestPoReceivedValidation` | Received-quantity PO validation (21) |
| `TestProductMatch` | match_product by SKU, multiple-match guard (5) |
| `TestProductSync` | Product create/update/never-send/variants (4) |
| `TestQueryEncoding` | **Client/supplier vat & email GETs are URL-encoded (24a/7)** |
| `TestRetourSaleOrderMatch` | **Retour → sale order exact unique match (11b)** |
| `TestRetours` | Retour detection / duplicate update (11) |
| `TestStatusQtyToOdoo` | Quantities Stoqflow → Odoo, split over lines (2) |
| `TestStatusUpdateQueue` | Incremental status update queue (20) |
| `TestStockImport` | Stock import to quants (9) |
| `TestStoqflowLive` | Live integration (network; usually skipped) |
| `TestSyncGates` | Draft/cancelled/done sync gates (3e/3f) |
| `TestSyncPartnerDelivery` | Partner sync with delivery address |
| `TestSyncPartnerHash` | Redundant client PUT suppression (19) |
| `TestSyncRetry` | Queue error → E + email + continue (17a) |
| `TestVerboseLogging` | Verbose JSON logging |

Classes in **bold** were added alongside the dry-test fixes; see
`test_cases_risk_assessment.md` for the mapping from scenario to fix.
