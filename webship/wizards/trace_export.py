# -*- coding: utf-8 -*-
from odoo import models, fields


class WebshipTraceExport(models.TransientModel):
    _name = 'webship.trace.export'
    _description = 'Stoqflow Verbose Trace Export'

    # The full, interleaved Stoqflow trace for a picking (internal steps plus
    # HTTP payloads) rendered as one block of text so it can be selected and
    # copied in a single action for support.
    trace_text = fields.Text('Full Stoqflow trace', readonly=True)
