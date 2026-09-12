#!/usr/bin/env bash
# 启动用户态 PostgreSQL+PostGIS 测试库（micromamba 环境 archdb），无需 root。
set -euo pipefail

PORT="${TEST_PG_PORT:-55436}"
ROOT_PREFIX="${MAMBA_ROOT_PREFIX:-$HOME/.local/share/mamba}"
BIN="$ROOT_PREFIX/envs/archdb/bin"
PGDATA="${TEST_PGDATA:-/tmp/archaeo-pgdata}"
SOCKET_DIR="/tmp/archaeo-pg-sock"

if [ ! -x "$BIN/pg_ctl" ]; then
  echo "postgresql not found in $BIN — install with:" >&2
  echo "  micromamba create -y -n archdb -c conda-forge 'postgresql=16' 'postgis=3.5'" >&2
  exit 1
fi

mkdir -p "$SOCKET_DIR"

if [ ! -d "$PGDATA" ]; then
  "$BIN/initdb" -D "$PGDATA" -U postgres --auth=trust -E UTF8 >/dev/null
  cat >> "$PGDATA/postgresql.conf" <<EOF
port = $PORT
unix_socket_directories = '$SOCKET_DIR'
listen_addresses = '127.0.0.1'
fsync = off
synchronous_commit = off
full_page_writes = off
EOF
fi

"$BIN/pg_ctl" -D "$PGDATA" -l "$PGDATA/server.log" -w start >/dev/null

# 等待可连接
for _ in $(seq 1 30); do
  if "$BIN/psql" -h 127.0.0.1 -p "$PORT" -U postgres -d postgres -c 'SELECT 1' >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

"$BIN/psql" -h 127.0.0.1 -p "$PORT" -U postgres -d postgres \
  -c "DROP DATABASE IF EXISTS archaeo_test;" >/dev/null
"$BIN/psql" -h 127.0.0.1 -p "$PORT" -U postgres -d postgres \
  -c "CREATE DATABASE archaeo_test;" >/dev/null

echo "PostgreSQL+PostGIS ready on 127.0.0.1:$PORT (db=archaeo_test)"
