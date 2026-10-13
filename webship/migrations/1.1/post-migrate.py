# Post-upgrade migration: ensure all Stoqflow pickings have a valid df_process_code.
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Re-classify Stoqflow pickings so df_process_code reflects reality.
    - Blank process code + Stoqflow id populated -> 'F' (Finished)
    - Any state + no Stoqflow id                  -> 'M' (Manual)
    All branches only apply to pickings that involve a Webship location."""

    # Treat 'false'/'False' strings on the id fields as empty so those
    # pickings are classified as unsynced (M) instead of incorrectly synced (F).
    blank_id = "(%s IS NULL OR %s IN ('', 'false', 'False', 'FALSE'))"
    has_id = "(%s IS NOT NULL AND %s NOT IN ('', 'false', 'False', 'FALSE'))"
    in_ws_scope = (
        "(sp.location_id IN (SELECT id FROM stock_location WHERE df_is_webship_location = TRUE)"
        " OR sp.location_dest_id IN (SELECT id FROM stock_location WHERE df_is_webship_location = TRUE))"
    )

    # Set synced pickings to F (Finished) - those that have a stoqflow order or PO id
    cr.execute("""
        UPDATE stock_picking sp
        SET df_process_code = 'F'
        WHERE (sp.df_process_code IS NULL OR sp.df_process_code = '' OR sp.df_process_code = 'false')
          AND (""" + has_id % ('sp.df_picking_id_webship', 'sp.df_picking_id_webship') + """
               OR """ + has_id % ('sp.df_po_id_webship', 'sp.df_po_id_webship') + """)
          AND """ + in_ws_scope + """
    """)
    synced_count = cr.rowcount
    if synced_count:
        _logger.info("post_migration 1.1: set %d synced pickings to F (Finished)", synced_count)

    # Set to M (Manual) any in-scope picking with no Stoqflow id.
    cr.execute("""
        UPDATE stock_picking sp
        SET df_process_code = 'M'
        WHERE """ + blank_id % ('sp.df_picking_id_webship', 'sp.df_picking_id_webship') + """
          AND """ + blank_id % ('sp.df_po_id_webship', 'sp.df_po_id_webship') + """
          AND (sp.df_process_code IS NULL OR sp.df_process_code != 'M')
          AND """ + in_ws_scope + """
    """)
    manual_count = cr.rowcount
    if manual_count:
        _logger.info("post_migration 1.1: set %d pickings with no Stoqflow id to M (Manual)", manual_count)

    if not synced_count and not manual_count:
        _logger.info("post_migration 1.1: no Stoqflow pickings needed reclassification")
