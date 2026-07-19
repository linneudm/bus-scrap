#!/bin/sh
set -eu

DATA_DIR="${BUS_SCRAP_DATA_DIR:-/app/data}"
mkdir -p "$DATA_DIR"

# Volume montado do host costuma pertencer a outro UID.
# Ajusta ownership e então desce privilégios para appsvc.
if [ "$(id -u)" -eq 0 ]; then
  chown -R appsvc:appsvc "$DATA_DIR"
  exec gosu appsvc python main.py "$@"
fi

exec python main.py "$@"
