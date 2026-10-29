# Post-upgrade migration for webship 19.0.2.48.
#
# The status sync used to write "No Stoqflow order ID or PO ID set on this
# picking" on every non-Manual picking without a Stoqflow id, including
# Pending ones that were simply not pushed yet and NA/Cancelled ones that
# never will be. The message is now only written for pickings that were sent
# to Stoqflow ('F') and lost their id; this clears the placeholder already
# stored on every other picking. Real error texts are left untouched: only
# the exact placeholder (as the Html field stores it) is matched.
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("""
        UPDATE stock_picking
        SET df_picking_syncresult_webship = NULL
        WHERE COALESCE(df_process_code, '') != 'F'
          AND (df_picking_id_webship IS NULL OR df_picking_id_webship IN ('', 'false', 'False'))
          AND (df_po_id_webship IS NULL OR df_po_id_webship IN ('', 'false', 'False'))
          AND regexp_replace(COALESCE(df_picking_syncresult_webship, ''), '<[^>]*>', '', 'g')
              = 'No Stoqflow order ID or PO ID set on this picking'
    """)
    if cr.rowcount:
        _logger.info(
            "post_migration 19.0.2.48: cleared the 'no Stoqflow id' placeholder "
            "on %d picking(s) never sent to Stoqflow", cr.rowcount)
    else:
        _logger.info(
            "post_migration 19.0.2.48: no unsent pickings carried the "
            "'no Stoqflow id' placeholder")
