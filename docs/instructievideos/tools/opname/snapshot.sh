#!/bin/sh
# snapshot.sh NAME  — copy database woody to woody_NAME (server restarted around it)
pkill -f '^venv/bin/python src/odoo-bin -c odoo.conf -d woody ' ; sleep 2
su postgres -c "dropdb --if-exists woody_$1; createdb -O odoo -T woody woody_$1"
cp /opt/stoqflow_mock/state.json /opt/rec/mock_state_$1.json 2>/dev/null
/opt/rec/start_woody.sh
