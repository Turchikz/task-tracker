#!/usr/bin/env sh
set -eu
exec "$(dirname "$0")/backup_host.sh" "$@"
