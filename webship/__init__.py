# -*- coding: utf-8 -*-

from . import models
from . import controllers

def migrate(cr, registry):
    from .migrations.post_migration import migrate
    migrate(cr, registry)