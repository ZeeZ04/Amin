#!/usr/bin/env bash
# HTTPS for the home network, with a certificate phones will actually trust.
#
# mkcert creates a private certificate authority on this Mac and signs a cert
# for this Mac's local names. A self-signed cert would work too, but every
# phone would show a full-page security warning - and people learn to click
# through warnings, which defeats the point.
set -euo pipefail
cd "$(dirname "$0")/.."

command -v mkcert >/dev/null || { echo "installing mkcert"; brew install mkcert; }

host="$(scutil --get LocalHostName).local"
ip="$(ipconfig getifaddr en0 || true)"
mkdir -p data/certs
mkcert -install
mkcert -cert-file data/certs/amin.pem -key-file data/certs/amin-key.pem \
  "$host" localhost 127.0.0.1 ${ip:+"$ip"}

echo
echo "Certificate for: $host localhost ${ip}"
echo "Open on this Mac:   https://localhost:8443"
echo "Open on phones:     https://$host:8443"
echo
echo "Each phone must trust this Mac's CA once:"
echo "  1. AirDrop or email this file to the phone: $(mkcert -CAROOT)/rootCA.pem"
echo "  2. iPhone: Settings > General > VPN & Device Management > install it,"
echo "     then Settings > General > About > Certificate Trust Settings > turn it on."
echo "  3. Android: Settings > Security > Encryption & credentials > Install a certificate > CA."
echo
echo "Never share rootCA-key.pem: anyone with it can impersonate any website to your devices."
