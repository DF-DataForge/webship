#!/bin/bash
[ -f /opt/stoqflow_mock/server.pid ] && kill "$(cat /opt/stoqflow_mock/server.pid)" 2>/dev/null; rm -f /opt/stoqflow_mock/server.pid
