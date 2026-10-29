# webship

Odoo module **Koppeling Stoqflow by Data Forge** (`webship`): integration between Odoo and Stoqflow (Webship) for e-commerce logistics and warehouse operations.

Extracted from `Pivotal-Dataforge/flat-pro` with its git history preserved.

## Branches

One branch per Odoo version, each with the addons at the repository root:

| Branch | Odoo |
|--------|------|
| `20.0` | 20.0 (this branch) |
| `main` | all versions in folders `18.0/`, `19.0/`, `20.0/` |

## Installation

Add this repository's root to the Odoo `addons_path` (on a hosting panel: this repo, branch `20.0`) and install the `webship` module.

Depends only on standard Odoo modules: `base`, `web`, `sale`, `product`, `purchase`, `stock`, `delivery`.

The `webship_demo_skateshop` demo module exists for Odoo 19 only (`19.0/` on `main`).
