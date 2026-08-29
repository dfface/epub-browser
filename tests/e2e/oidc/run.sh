#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ARTIFACT_DIR="$SCRIPT_DIR/artifacts"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.yml"
PROJECT_NAME="epub_oidc_e2e_$$"
CERT_DIR=$(mktemp -d "${TMPDIR:-/tmp}/epub-oidc-e2e.XXXXXX")
STATUS=0

mkdir -p "$ARTIFACT_DIR"
export OIDC_E2E_CERT_DIR="$CERT_DIR"
export OIDC_E2E_ARTIFACT_DIR="$ARTIFACT_DIR"
export OIDC_E2E_BASE_URL="https://127.0.0.1:18443"

compose() {
  docker compose --project-name "$PROJECT_NAME" --file "$COMPOSE_FILE" "$@"
}

cleanup() {
  STATUS=$?
  if [ "$STATUS" -ne 0 ]; then
    compose logs --no-color >"$ARTIFACT_DIR/compose.log" 2>&1 || true
  fi
  compose down --volumes --remove-orphans >/dev/null 2>&1 || true
  if [ -d "$CERT_DIR" ]; then
    find "$CERT_DIR" -type f -delete
    rmdir "$CERT_DIR" 2>/dev/null || true
  fi
  exit "$STATUS"
}
trap cleanup EXIT HUP INT TERM

python3 - <<'PY'
import socket

for port in (18443, 18444):
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", port))
        except OSError as exc:
            raise SystemExit(f"OIDC E2E requires free loopback port {port}: {exc}")
PY

openssl req -x509 -newkey rsa:2048 -nodes -days 1 \
  -subj '/CN=EPUB Browser OIDC E2E CA' \
  -addext 'basicConstraints=critical,CA:TRUE' \
  -addext 'keyUsage=critical,keyCertSign,cRLSign' \
  -addext 'subjectKeyIdentifier=hash' \
  -keyout "$CERT_DIR/ca.key" -out "$CERT_DIR/ca.crt" >/dev/null 2>&1
openssl req -newkey rsa:2048 -nodes -subj '/CN=localhost' \
  -keyout "$CERT_DIR/server.key" -out "$CERT_DIR/server.csr" >/dev/null 2>&1
cat >"$CERT_DIR/server.ext" <<'EOF'
basicConstraints=CA:FALSE
keyUsage=digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectKeyIdentifier=hash
authorityKeyIdentifier=keyid,issuer
subjectAltName=DNS:localhost,IP:127.0.0.1
EOF
openssl x509 -req -days 1 -sha256 \
  -in "$CERT_DIR/server.csr" \
  -CA "$CERT_DIR/ca.crt" -CAkey "$CERT_DIR/ca.key" -CAcreateserial \
  -extfile "$CERT_DIR/server.ext" -out "$CERT_DIR/server.crt" >/dev/null 2>&1

compose up --detach --build --wait --wait-timeout 240
curl --fail --silent --show-error --noproxy '*' \
  --cacert "$CERT_DIR/ca.crt" \
  "$OIDC_E2E_BASE_URL/login" >/dev/null
compose exec --no-TTY epub-browser python -c \
  "import urllib.request; response = urllib.request.urlopen('https://127.0.0.1:18444/.well-known/openid-configuration', timeout=5); assert response.status == 200"
node "$SCRIPT_DIR/test_oidc.mjs"

echo "OIDC E2E passed; screenshots: $ARTIFACT_DIR"
