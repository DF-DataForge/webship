# Post-upgrade migration: force-rename the module's ir.cron records to the
# names declared in views/cron.xml. cron.xml uses noupdate="1", so names
# hand-edited in the Odoo UI (or inherited from older releases) are not
# refreshed on a normal upgrade. Every cron shipped by this module must
# start with 'Stoqflow'.
import logging

_logger = logging.getLogger(__name__)


_CRON_NAMES = {
    'webship.ir_cron_sync_statussen': 'Stoqflow sync statusses',
    'webship.ir_cron_sync_statusP': 'Stoqflow sync status P',
    'webship.ir_cron_import_stock': 'Stoqflow import stock',
    'webship.ir_cron_daily_report': 'Stoqflow daily processing report',
    'webship.ir_cron_sync_retours_and_backorders': 'Stoqflow sync retours and backorders',
    'webship.ir_cron_auto_delete_backorders': 'Stoqflow fetch backorders',
}


def migrate(cr, version):
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    for xml_id, name in _CRON_NAMES.items():
        cron = env.ref(xml_id, raise_if_not_found=False)
        if not cron:
            continue
        if cron.name != name:
            _logger.info("Renaming cron %s: %r -> %r", xml_id, cron.name, name)
            cron.sudo().write({'name': name})
