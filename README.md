# webship

Odoo module **Koppeling Stoqflow by Data Forge** (`webship`): integration between Odoo and Stoqflow (Webship) for e-commerce logistics and warehouse operations.

Extracted from `Pivotal-Dataforge/flat-pro` with its git history preserved.

## Installation

Add this repository's root to the Odoo `addons_path` and install the `webship` module.

Depends only on standard Odoo modules: `base`, `web`, `sale`, `product`, `purchase`, `stock`, `delivery`.

## Demo database: Ollie's Skate Supply

`webship_demo_skateshop` turns a **fresh, empty** Odoo 19 database into a demo company that uses Stoqflow as its e-fulfilment partner. Install it from Apps (it pulls in `webship`, eCommerce, Manufacturing and the Belgian chart of accounts). Never install it on a production database: it renames the main company and creates warehouses, partners, products and orders.

What it sets up:

- **Company** Ollie's Skate Supply BV (Antwerpen), Belgian chart of accounts, EUR, 21% VAT.
- **Warehouses**
  - `WKS` Skate Workshop Antwerpen: own warehouse where components arrive and boards are assembled.
  - `SQF` Stoqflow Fulfilment: its stock location is flagged *Is Stoqflow locatie*, so receipts into it become Stoqflow purchase orders and deliveries out of it become Stoqflow orders.
- **Webshop** (Odoo eCommerce) selling tees, hoodies, beanies, socks and complete boards from the `SQF` warehouse. Backend sales also default to `SQF`.
- **Routes**
  - Clothing: *Buy*, received directly in `SQF`.
  - Components: *Buy*, received in `WKS`; not synced to Stoqflow (*Don't sync this product*).
  - Complete boards: *Manufacture* in `WKS` (bill of materials: deck, 2 trucks, wheels, bearings, grip tape, hardware) + *Stoqflow Fulfilment: Supply Product from Skate Workshop* (WKS → transit → SQF).
  - Replenishment rules (manual trigger) for all of the above, visible under Inventory > Replenishment.
- **Documents**: received and delivered history, plus open documents that are pending for Stoqflow (process code `P`): a clothing restock PO, a resupply of complete boards from the workshop, and webshop and B2B orders. The B2B order of 24 socks shows the packaging split (2 × `OSS-SOCKS-12`).

Stoqflow API credentials are not set and the Stoqflow crons are switched off. To sync for real, enter sandbox credentials under Settings > Stoqflow, run *Fetch companies and warehouses*, link the `SQF/Stock` location to the Stoqflow warehouse, and switch the crons back on.
