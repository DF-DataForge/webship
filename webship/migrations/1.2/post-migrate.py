# Post-upgrade migration: replace raw Stoqflow product IDs in sync result
# messages with product name + SKU for better readability.
import logging
import re
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def _make_label(name, sku):
    if sku:
        return "'%s' (SKU: %s)" % (name, sku)
    return "'%s'" % name


def migrate(cr, version):
    """Find pickings whose df_picking_syncresult_webship contains raw
    Stoqflow product_id references and replace them with product name + SKU."""

    cr.execute("""
        SELECT id, df_picking_syncresult_webship
        FROM stock_picking
        WHERE df_picking_syncresult_webship LIKE '%%Stoqflow product_id%%'
           OR df_picking_syncresult_webship LIKE '%%Stoqflow ID ''%%'
    """)
    rows = cr.fetchall()
    if not rows:
        _logger.info("post_migration 1.2: no pickings with raw Stoqflow IDs in sync results")
        return

    _logger.info("post_migration 1.2: found %d pickings with raw Stoqflow IDs to fix", len(rows))

    env = api.Environment(cr, SUPERUSER_ID, {})

    # Build lookup: stoqflow_id -> readable label from products
    ws_id_to_label = {}

    all_products = env['product.product'].sudo().search([('df_product_id_webship', '!=', False)])
    for p in all_products:
        if p.df_product_id_webship:
            ws_id_to_label[p.df_product_id_webship] = _make_label(p.name, p.default_code or '')

    def _replace_id(match):
        ws_id = match.group(1)
        return ws_id_to_label.get(ws_id, match.group(0))

    pattern = re.compile(r"Stoqflow (?:product_id|ID) '([^']+)'")

    updated = 0
    for picking_id, result_html in rows:
        new_html = pattern.sub(_replace_id, result_html)
        if new_html != result_html:
            cr.execute(
                "UPDATE stock_picking SET df_picking_syncresult_webship = %s WHERE id = %s",
                (new_html, picking_id)
            )
            updated += 1

    _logger.info("post_migration 1.2: updated %d picking sync result messages", updated)
