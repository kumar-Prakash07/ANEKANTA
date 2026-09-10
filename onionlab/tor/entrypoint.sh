#!/bin/sh
# Start Tor, wait for both descriptors, then publish the addresses.
set -eu

HS=/var/lib/tor/hidden_service
for d in market forum; do
  mkdir -p "$HS/$d" 2>/dev/null || true
  chmod 700 "$HS/$d" 2>/dev/null || true
done
chmod 700 "$HS" 2>/dev/null || true

tor -f /etc/tor/torrc &
TOR_PID=$!

# Tor requires each HiddenServiceDir to be mode 0700 and owned by the tor
# user, so the unprivileged site containers cannot read the hostname files
# directly. Copy them to a readable sibling directory instead: the address is
# public information by design, while the private keys beside it are not and
# stay behind 0700.
PUB=/srv/onion-addresses
mkdir -p "$PUB" 2>/dev/null || true
chmod 755 "$PUB" 2>/dev/null || true

i=0
while [ $i -lt 180 ]; do
  ready=1
  for d in market forum; do
    if [ -s "$HS/$d/hostname" ]; then
      cp "$HS/$d/hostname" "$PUB/$d" 2>/dev/null || true
      chmod 644 "$PUB/$d" 2>/dev/null || true
    else
      ready=0
    fi
  done
  [ $ready -eq 1 ] && break
  sleep 1
  i=$((i + 1))
done

if [ -s "$PUB/market" ]; then
  echo "============================================================"
  echo "ONIONLAB market: $(cat "$PUB/market")"
  echo "ONIONLAB forum : $(cat "$PUB/forum" 2>/dev/null || echo pending)"
  echo "============================================================"
else
  echo "ONIONLAB: hidden service descriptors not ready yet" >&2
fi

wait $TOR_PID
