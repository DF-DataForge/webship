#!/bin/bash
# One-time (idempotent) setup for the Stoqflow mock:
#  - local CA + server certificate for api.stoqflow.com
#  - /opt/stoqflow_mock/ca-bundle.pem = system bundle + certifi bundle + mock CA
#  - /etc/hosts entry 127.0.0.1 api.stoqflow.com
set -e
D=/opt/stoqflow_mock
C=$D/certs
mkdir -p $C
cd $C
if [ ! -f ca.key ]; then
  openssl genrsa -out ca.key 2048 2>/dev/null
  openssl req -x509 -new -key ca.key -sha256 -days 3650 -subj "/CN=Stoqflow Mock Local CA" -out ca.crt
fi
if [ ! -f server.crt ]; then
  openssl genrsa -out server.key 2048 2>/dev/null
  openssl req -new -key server.key -subj "/CN=api.stoqflow.com" -out server.csr
  cat > server.ext <<EXT
basicConstraints=CA:FALSE
keyUsage=digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=DNS:api.stoqflow.com,DNS:app.stoqflow.com,IP:127.0.0.1
EXT
  openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial -days 825 -sha256 -extfile server.ext -out server.crt 2>/dev/null
fi
CERTIFI=$(/opt/odoo20/venv/bin/python -c 'import certifi;print(certifi.where())')
{ cat /etc/ssl/certs/ca-certificates.crt 2>/dev/null; echo; cat "$CERTIFI"; echo; cat $C/ca.crt; } > $D/ca-bundle.pem
grep -qE '^127\.0\.0\.1[[:space:]]+api\.stoqflow\.com' /etc/hosts || echo '127.0.0.1 api.stoqflow.com' >> /etc/hosts
echo "setup ok: $C/server.crt, $D/ca-bundle.pem, /etc/hosts"
