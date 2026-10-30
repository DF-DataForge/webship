#!/bin/sh
# restore.sh NAME  — reset database woody (and the mock state) to snapshot NAME
pkill -f '^venv/bin/python src/odoo-bin -c odoo.conf -d woody ' ; sleep 2
su postgres -c "dropdb --if-exists woody; createdb -O odoo -T woody_$1 woody"
if [ -f /opt/rec/mock_state_$1.json ]; then /opt/stoqflow_mock/stop.sh; cp /opt/rec/mock_state_$1.json /opt/stoqflow_mock/state.json; /opt/stoqflow_mock/start.sh; fi
/opt/rec/start_woody.sh
