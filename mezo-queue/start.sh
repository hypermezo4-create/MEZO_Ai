#!/bin/sh
set -eu
if [ -z "${VALKEY_PASSWORD:-}" ]; then
  echo "VALKEY_PASSWORD is required" >&2
  exit 1
fi
bind_host=${MEZO_BIND_HOST:-0.0.0.0}
case "$bind_host" in
  0.0.0.0) bind_addresses="0.0.0.0" ;;
  ::) bind_addresses="0.0.0.0 ::" ;;
  *) echo "MEZO_BIND_HOST must be 0.0.0.0 or ::" >&2; exit 1 ;;
esac
umask 077
cat > /tmp/valkey.conf <<EOF
bind ${bind_addresses}
protected-mode yes
port 6379
dir /data
appendonly yes
appendfsync everysec
requirepass ${VALKEY_PASSWORD}
maxmemory-policy noeviction
EOF
exec valkey-server /tmp/valkey.conf
