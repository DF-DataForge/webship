# Post-upgrade migration for webship 19.0.2.31.
#
# Until now the status sync wrote "No Stoqflow order ID or PO ID set on this
# picking" on every picking without a Stoqflow id, including the Manual ('M')
# ones that are deliberately never sent to Stoqflow. For those pickings the
# missing id is the normal state, not a failure, so the result column has to
# stay blank. fetchQuantities no longer writes the message for them; this
# clears the ones already stored so existing Manual pickings go blank too.
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("""
        UPDATE stock_picking
        SET df_picking_syncresult_webship = NULL
        WHERE df_process_code = 'M'
          AND df_picking_syncresult_webship LIKE
              '%No Stoqflow order ID or PO ID set on this picking%'
    """)
    if cr.rowcount:
        _logger.info(
            "post_migration 19.0.2.31: cleared the 'no Stoqflow id' sync result "
            "on %d manual picking(s)", cr.rowcount)
    else:
        _logger.info(
            "post_migration 19.0.2.31: no manual pickings carried the "
            "'no Stoqflow id' sync result")
