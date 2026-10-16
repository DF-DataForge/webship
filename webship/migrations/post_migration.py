# Post-migration script that runs after the module is installed or upgraded.
# The reclassification lives in reclassify_process_codes() so the version-
# specific upgrade hook can call it too; post_init_hook alone only fires on
# fresh install, not on upgrade.
import logging

_logger = logging.getLogger(__name__)


_BLANK_ID = "(%s IS NULL OR %s IN ('', 'false', 'False', 'FALSE'))"
_HAS_ID = "(%s IS NOT NULL AND %s NOT IN ('', 'false', 'False', 'FALSE'))"
_IN_WS_SCOPE = (
    "(sp.location_id IN (SELECT id FROM stock_location WHERE df_is_webship_location = TRUE)"
    " OR sp.location_dest_id IN (SELECT id FROM stock_location WHERE df_is_webship_location = TRUE))"
)


def reclassify_process_codes(cr, label):
    """Re-align stock_picking.df_process_code with the actual Stoqflow state.

    - Blank process code + Stoqflow id populated -> 'F' (Finished)
    - Any state + no Stoqflow id                  -> 'M' (Manual)
      Without an id the picking was never really sent, so the only
      consistent state is Manual.
    Only touches pickings inside the Stoqflow location scope.
    ``label`` is used as a prefix in log output (e.g. 'post_migration' or
    'post_migration 19.0.1.2') so upgrade runs are distinguishable."""

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
        _logger.info("%s: set %d synced pickings to F (Finished)", label, synced_count)

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
        _logger.info("%s: set %d pickings with no Stoqflow id to M (Manual)", label, manual_count)

    if not synced_count and not manual_count:
        _logger.info("%s: no Stoqflow pickings needed reclassification", label)


def migrate(cr, registry):
    """post_init_hook entry point (runs on fresh install)."""
    reclassify_process_codes(cr, 'post_migration')
