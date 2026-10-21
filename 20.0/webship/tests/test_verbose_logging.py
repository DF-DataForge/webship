# -*- coding: utf-8 -*-
from unittest import mock

from odoo.tests.common import TransactionCase

from odoo.addons.webship.models.picking import StockPicking
from odoo.addons.webship.models.ws import WebShipHandler


class TestVerboseLogging(TransactionCase):
    """Verbose logging setting: when enabled, showDebugInfo records a 'trace'
    row in webship.json.history (tagged with the current picking) and HTTP
    payload logging is implied; when disabled nothing is recorded."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(StockPicking, 'fetch_picking_code', return_value='X')
        patcher.start()
        self.addCleanup(patcher.stop)

        self.param = self.env['ir.config_parameter'].sudo()
        self.History = self.env['webship.json.history']
        self.handler = WebShipHandler('u', 'p', 'http://test/')
        self.handler.set_env(self.env)

    def _trace_count(self):
        return self.History.search_count([('direction', '=', 'trace')])

    def test_no_trace_when_disabled(self):
        self.param.set_str('webship.verbose_logging', 'False')
        self.param.set_str('webship.log_json', 'False')
        before = self._trace_count()
        self.handler.showDebugInfo('hello')
        self.assertEqual(self._trace_count(), before)
        # Neither logging setting is on, so HTTP payloads are not logged either.
        self.assertFalse(self.handler._http_logging_enabled())

    def test_trace_recorded_when_enabled(self):
        self.param.set_str('webship.verbose_logging', 'True')
        before = self._trace_count()
        self.handler.showDebugInfo('a diagnostic message')
        rows = self.History.search([('direction', '=', 'trace')])
        self.assertEqual(len(rows), before + 1)
        self.assertIn('a diagnostic message', rows[0].json_payload)
        # Verbose logging is a superset: it implies HTTP payload logging.
        self.assertTrue(self.handler._http_logging_enabled())

    def test_log_json_alone_enables_http_logging_not_trace(self):
        # 'Log JSON payloads' on but verbose off: HTTP logging on, but the
        # internal showDebugInfo trace is NOT recorded.
        self.param.set_str('webship.verbose_logging', 'False')
        self.param.set_str('webship.log_json', 'True')
        before = self._trace_count()
        self.handler.showDebugInfo('should not be stored')
        self.assertEqual(self._trace_count(), before)
        self.assertTrue(self.handler._http_logging_enabled())

    def test_verbose_tags_current_picking(self):
        self.param.set_str('webship.verbose_logging', 'True')
        ws_loc = self.env['stock.location'].create({
            'name': 'WS', 'usage': 'internal',
            'location_id': self.env.ref('stock.stock_location_stock').location_id.id,
            'df_is_webship_location': True,
        })
        suppliers = self.env.ref('stock.stock_location_suppliers')
        product = self.env['product.product'].create({'name': 'W', 'default_code': 'S1'})
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.env.ref('stock.picking_type_in').id,
            'location_id': suppliers.id, 'location_dest_id': ws_loc.id,
            'move_ids': [(0, 0, {
                'product_id': product.id, 'product_uom_qty': 1,
                'uom_id': product.uom_id.id,
                'location_id': suppliers.id, 'location_dest_id': ws_loc.id,
            })],
        })
        with self.handler._with_logging_picking(picking):
            self.handler.showDebugInfo('tagged message')
        row = self.History.search(
            [('direction', '=', 'trace'), ('json_payload', 'like', 'tagged message')], limit=1)
        self.assertEqual(row.picking_id, picking)
