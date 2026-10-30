#!/bin/sh
# Restore the empty database from its template and restart its server.
pkill -f "odoo-bin -c odoo.conf -d leeg " ; sleep 2
su postgres -c "dropdb --if-exists leeg && createdb -O odoo -T leeg_tpl leeg"
cd /opt/odoo20 && nohup venv/bin/python src/odoo-bin -c odoo.conf -d leeg --db-filter=^leeg$ --http-port=8071 --gevent-port=8073 > /opt/odoo20/server_leeg.log 2>&1 &
sleep 8
