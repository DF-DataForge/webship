# Access check shared by the XLSX export routes.
from odoo.http import request
from werkzeug.exceptions import Forbidden


def check_stoqflow_manager():
    """The exports read Stoqflow data with the company's API login (and Odoo
    contacts with sudo), so only Stoqflow administrators may download them.
    auth='user' alone also lets portal and webshop customers in."""
    if not request.env.user.has_group('webship.group_webship_manager'):
        raise Forbidden()
