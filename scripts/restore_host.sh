#!/usr/bin/env bash
set -euo pipefail
umask 077

if [ "$#" -ne 1 ]; then
  echo "Usage: ./scripts/restore_host.sh /path/tasktracker_backup_YYYYMMDD_HHMMSS.tar.gz" >&2
  exit 1
fi

archive="$(realpath "$1")"
[ -s "$archive" ] || { echo "Backup not found or empty: $archive" >&2; exit 1; }

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)}"
cd "$PROJECT_DIR"

if [ -s "${archive}.sha256" ]; then
  echo "Verifying checksum..."
  (cd "$(dirname "$archive")" && sha256sum -c "$(basename "${archive}.sha256")")
fi

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT INT TERM

tar -xzf "$archive" -C "$workdir"
[ -s "$workdir/database.dump" ] || { echo "database.dump is missing." >&2; exit 1; }

echo "WARNING: this will replace the current Task Tracker database and media."
printf "Type RESTORE to continue: "
read -r confirmation
[ "$confirmation" = "RESTORE" ] || { echo "Cancelled."; exit 1; }

docker compose stop notifier web nginx >/dev/null 2>&1 || true
docker compose up -d db
for _ in $(seq 1 30); do
  if docker compose exec -T db sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
echo "Restoring PostgreSQL..."
docker compose exec -T db sh -c \
  'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner' \
  < "$workdir/database.dump"

if [ -s "$workdir/media.tar.gz" ]; then
  docker compose up -d web
  echo "Restoring media..."
  docker compose exec -T web python -c \
    'import os,shutil,sys,tarfile; root="/app/media"; os.makedirs(root, exist_ok=True); [shutil.rmtree(os.path.join(root,n)) if os.path.isdir(os.path.join(root,n)) and not os.path.islink(os.path.join(root,n)) else os.unlink(os.path.join(root,n)) for n in os.listdir(root)]; t=tarfile.open(fileobj=sys.stdin.buffer, mode="r|gz"); t.extractall(root, filter="data"); t.close()' \
    < "$workdir/media.tar.gz"
fi

docker compose up -d --remove-orphans
echo "Restore completed."
