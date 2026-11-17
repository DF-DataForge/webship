# Extends stock.lot with a lookup / creation helper for Stoqflow batches.
# Stoqflow reports stock per batch (GET products/{id}?detail=high); a batch
# Odoo does not know yet gets a lot so the Stoqflow Stock screen can show it
# next to the Odoo lots and adjust it.
from odoo import api, models


class StockLot(models.Model):
    _inherit = 'stock.lot'

    @api.model
    def _df_get_or_create_for_batch(self, product, batch, company, expiry=None):
        """Return the lot named ``batch`` of ``product`` (owned by ``company``
        or shared), creating it when Odoo does not know the batch yet.
        ``expiry`` (a datetime) is stored on a new lot when the product_expiry
        module is installed."""
        lot = self.search([
            ('name', '=', batch),
            ('product_id', '=', product.id),
            ('company_id', 'in', [company.id, False]),
        ], limit=1)
        if lot:
            return lot
        vals = {'name': batch, 'product_id': product.id, 'company_id': company.id}
        if expiry and 'expiration_date' in self._fields:
            vals['expiration_date'] = expiry
        return self.create(vals)
