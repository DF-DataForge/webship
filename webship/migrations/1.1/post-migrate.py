# Post-upgrade migration: ensure all Stoqflow pickings have a valid df_process_code.
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Fix pickings with blank df_process_code.
    - Already synced (have a Stoqflow ID) -> set to 'F' (Finished)
    - Not yet synced (no Stoqflow ID) -> set to 'M' (Manual)
    Only applies to pickings that involve a Webship location."""

    # Set synced pickings to F (Finished) - those that have a stoqflow order or PO id
    cr.execute("""
        UPDATE stock_picking sp
        SET df_process_code = 'F'
        WHERE (sp.df_process_code IS NULL OR sp.df_process_code = '' OR sp.df_process_code = 'false')
          AND (sp.df_picking_id_webship IS NOT NULL AND sp.df_picking_id_webship != ''
               OR sp.df_po_id_webship IS NOT NULL AND sp.df_po_id_webship != '')
          AND (sp.location_id IN (SELECT id FROM stock_location WHERE df_is_webship_location = TRUE)
               OR sp.location_dest_id IN (SELECT id FROM stock_location WHERE df_is_webship_location = TRUE))
    """)
    synced_count = cr.rowcount
    if synced_count:
        _logger.info("post_migration 1.1: set %d synced pickings to F (Finished)", synced_count)

    # Set unsynced pickings to M (Manual) - no stoqflow ID yet
    cr.execute("""
        UPDATE stock_picking sp
        SET df_process_code = 'M'
        WHERE (sp.df_process_code IS NULL OR sp.df_process_code = '' OR sp.df_process_code = 'false')
          AND (sp.df_picking_id_webship IS NULL OR sp.df_picking_id_webship = '')
          AND (sp.df_po_id_webship IS NULL OR sp.df_po_id_webship = '')
          AND (sp.location_id IN (SELECT id FROM stock_location WHERE df_is_webship_location = TRUE)
               OR sp.location_dest_id IN (SELECT id FROM stock_location WHERE df_is_webship_location = TRUE))
    """)
    manual_count = cr.rowcount
    if manual_count:
        _logger.info("post_migration 1.1: set %d unsynced pickings to M (Manual)", manual_count)

    if not synced_count and not manual_count:
        _logger.info("post_migration 1.1: no Stoqflow pickings with blank df_process_code found")
