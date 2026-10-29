# Post-upgrade migration for webship 19.0.2.49.
#
# The Odoo vs Stoqflow stock differences on stock.quant are now computed per
# product and location (summing lots/packages) and stay empty on quants that
# were never checked against Stoqflow. Recompute the stored values so existing
# rows follow the new rule instead of keeping the per-quant figures.
import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    quants = env['stock.quant'].search([('location_id.df_is_webship_location', '=', True)])
    env.add_to_compute(env['stock.quant']._fields['df_webship_diff_total'], quants)
    quants._recompute_recordset()
    _logger.info("post_migration 19.0.2.49: recomputed Stoqflow stock differences "
                 "on %d quant(s)", len(quants))
