# Post-upgrade migration for webship 19.0.1.2.
# Replays the process-code reclassification so upgrades from previous
# versions pick up the latest rule (anything inside the Stoqflow scope
# without a Stoqflow id becomes 'M' (Manual), regardless of its current
# process code). The post_init_hook only fires on fresh install, so this
# script is what actually runs on Upgrade.
import logging

_logger = logging.getLogger(__name__)


_BLANK_ID = "(%s IS NULL OR %s IN ('', 'false', 'False', 'FALSE'))"
_HAS_ID = "(%s IS NOT NULL AND %s NOT IN ('', 'false', 'False', 'FALSE'))"
_IN_WS_SCOPE = (
    "(sp.location_id IN (SELECT id FROM stock_location WHERE df_is_webship_location = TRUE)"
    " OR sp.location_dest_id IN (SELECT id FROM stock_location WHERE df_is_webship_location = TRUE))"
)


def migrate(cr, version):
    # Set synced pickings to F (Finished) - those that have a stoqflow order or PO id
    cr.execute("""
        UPDATE stock_picking sp
        SET df_process_code = 'F'
        WHERE (sp.df_process_code IS NULL OR sp.df_process_code = '' OR sp.df_process_code = 'false')
          AND (""" + _HAS_ID % ('sp.df_picking_id_webship', 'sp.df_picking_id_webship') + """
               OR """ + _HAS_ID % ('sp.df_po_id_webship', 'sp.df_po_id_webship') + """)
          AND """ + _IN_WS_SCOPE + """
    """)
    synced_count = cr.rowcount
    if synced_count:
        _logger.info("post_migration 19.0.1.2: set %d synced pickings to F (Finished)", synced_count)

    # Set to M (Manual) any in-scope picking with no Stoqflow id, regardless
    # of its current process code. Without an id the picking was never
    # actually sent, so blank/'F'/'P'/'E' all collapse to 'M'.
    cr.execute("""
        UPDATE stock_picking sp
        SET df_process_code = 'M'
        WHERE """ + _BLANK_ID % ('sp.df_picking_id_webship', 'sp.df_picking_id_webship') + """
          AND """ + _BLANK_ID % ('sp.df_po_id_webship', 'sp.df_po_id_webship') + """
          AND (sp.df_process_code IS NULL OR sp.df_process_code != 'M')
          AND """ + _IN_WS_SCOPE + """
    """)
    manual_count = cr.rowcount
    if manual_count:
        _logger.info("post_migration 19.0.1.2: set %d pickings with no Stoqflow id to M (Manual)", manual_count)

    if not synced_count and not manual_count:
        _logger.info("post_migration 19.0.1.2: no Stoqflow pickings needed reclassification")
