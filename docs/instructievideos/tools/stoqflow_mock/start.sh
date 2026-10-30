#!/bin/bash
# Start the Stoqflow mock in the background (API https://api.stoqflow.com on 127.0.0.1:443,
# control API http://127.0.0.1:8099). Pass --reset to start from the seed state.
cd /opt/stoqflow_mock && ./setup.sh >/dev/null
[ -f server.pid ] && kill "$(cat server.pid)" 2>/dev/null && sleep 0.5
nohup python3 /opt/stoqflow_mock/server.py -v "$@" >> /opt/stoqflow_mock/server.log 2>&1 &
echo $! > server.pid
sleep 1; tail -2 /opt/stoqflow_mock/server.log
