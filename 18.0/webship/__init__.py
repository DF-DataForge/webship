# -*- coding: utf-8 -*-

# Import the models, wizards and controllers sub-packages so Odoo registers them
from . import models
from . import wizards
from . import controllers

# Post-install hook: runs the data migration script after the module is installed
def migrate(env):
    from .migrations.post_migration import migrate
    migrate(env)
