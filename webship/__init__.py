# -*- coding: utf-8 -*-

# Import the models and controllers sub-packages so Odoo registers them
from . import models
from . import controllers

# Post-install hook: runs the data migration script after the module is installed
def migrate(cr, registry):
    from .migrations.post_migration import migrate
    migrate(cr, registry)
