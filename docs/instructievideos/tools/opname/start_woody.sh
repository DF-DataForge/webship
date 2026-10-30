#!/bin/sh
# (Re)start the Odoo server for the demo database, with the mock Stoqflow trusted.
pkill -f '^venv/bin/python src/odoo-bin -c odoo.conf -d woody ' ; sleep 2
. /opt/stoqflow_mock/odoo-env.sh
cd /opt/odoo20 && nohup venv/bin/python src/odoo-bin -c odoo.conf -d woody --db-filter='^woody$' > /opt/odoo20/server.log 2>&1 &
sleep 8
