# Post-upgrade migration for webship 19.0.2.46.
#
# 'Object in Stoqflow' (df_object_in_webship) and 'Show Stoqflow page'
# (df_show_webship_page) are stored computed fields that used to depend on
# the picking's location ids only. Marking a location as a Stoqflow location
# after pickings already referenced it therefore never reclassified those
# pickings: they stayed stored as 'Mutation' with the Stoqflow tab hidden,
# even though one side is now a Stoqflow location. Pickings whose two sides
# are both Stoqflow locations were also always 'Mutation', while the new rule
# classifies them by their sale/purchase order or operation type.
#
# Replay the reclassification that the 'Stoqflow reclassify object types'
# scheduled action runs, so existing records are corrected on upgrade.
import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    pickings, changed = env['stock.picking']._ws_reclassify_object_types()
    _logger.info(
        "post_migration 19.0.2.46: recomputed %d picking(s), %d changed",
        len(pickings), len(changed))
