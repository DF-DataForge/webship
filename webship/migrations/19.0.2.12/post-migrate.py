# Post-upgrade migration for webship 19.0.2.12.
#
# Backfill the Stoqflow status metadata on backorders that were linked to
# their Stoqflow child order by an older version (< 19.0.2.10), before the
# link step started populating df_status_webship / df_last_changedate_webship
# / df_picking_lastsync_webship. Those records show the green "Linked to
# Stoqflow backorder" result but an empty Status column.
#
# For each already-linked backorder with an empty Stoqflow status we fetch the
# order/PO once by its id and reuse _apply_stoqflow_child_metadata to fill the
# fields. This only writes metadata - it never changes quantities or validates
# the picking - so it is safe to replay.
import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Picking = env['stock.picking']

    pickings = Picking.search([
        ('backorder_id', '!=', False),
        '|',
            ('df_picking_id_webship', '!=', False),
            ('df_po_id_webship', '!=', False),
        '|',
            ('df_status_webship', '=', False),
            ('df_status_webship', '=', ''),
    ])
    if not pickings:
        _logger.info("post_migration 19.0.2.12: no linked backorders need a status backfill")
        return

    handler = Picking.getHandler()
    handler.set_env(env)

    filled = 0
    for picking in pickings:
        if picking.df_picking_id_webship:
            endpoint, ws_id = 'orders', picking.df_picking_id_webship
        elif picking.df_po_id_webship:
            endpoint, ws_id = 'purchase-orders', picking.df_po_id_webship
        else:
            continue
        try:
            result = handler.fetchByKey(endpoint, ws_id)
        except Exception as e:
            _logger.warning(
                "post_migration 19.0.2.12: fetch %s/%s failed for %s: %s",
                endpoint, ws_id, picking.name, e)
            continue
        if result.get('status') == 'error' or not result.get('data'):
            continue
        picking._apply_stoqflow_child_metadata(result['data'])
        if picking.df_status_webship:
            filled += 1

    _logger.info(
        "post_migration 19.0.2.12: backfilled Stoqflow status on %d/%d linked backorder(s)",
        filled, len(pickings))
