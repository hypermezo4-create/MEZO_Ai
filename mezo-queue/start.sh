#!/bin/sh
set -eu
if [ -z "${VALKEY_PASSWORD:-}" ]; then
  echo "VALKEY_PASSWORD is required" >&2
  exit 1
fi
umask 077
cat > /tmp/valkey.conf <<EOF
bind 0.0.0.0
protected-mode yes
port 6379
dir /data
appendonly yes
appendfsync everysec
requirepass ${VALKEY_PASSWORD}
maxmemory-policy noeviction
EOF
exec valkey-server /tmp/valkey.conf
