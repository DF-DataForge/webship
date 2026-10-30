# source this before starting Odoo so it trusts the mock CA and bypasses the HTTPS proxy
export REQUESTS_CA_BUNDLE=/opt/stoqflow_mock/ca-bundle.pem
export NO_PROXY="${NO_PROXY:+$NO_PROXY,}api.stoqflow.com"
export no_proxy="${no_proxy:+$no_proxy,}api.stoqflow.com"
