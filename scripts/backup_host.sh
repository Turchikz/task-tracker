#!/usr/bin/env bash
set -euo pipefail
umask 077

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)}"
cd "$PROJECT_DIR"

# The self-hosted runner normally leaves .env in the checkout after deploy.
# If checkout cleanup removed it, borrow the stable production config only for
# this backup run and delete the temporary copy afterwards.
generated_local_env=0
stable_env="$HOME/projects/.config/task-tracker/.env"
if [ ! -f "$PROJECT_DIR/.env" ] && [ -f "$stable_env" ]; then
  cp "$stable_env" "$PROJECT_DIR/.env"
  chmod 600 "$PROJECT_DIR/.env"
  generated_local_env=1
fi

read_env_value() {
  local key="$1"
  local file="${2:-$PROJECT_DIR/.env}"
  [ -f "$file" ] || return 0
  sed -n "s/^${key}=//p" "$file" | tail -n 1 | sed -e "s/^['\"]//" -e "s/['\"]$//"
}

BACKUP_ROOT="${HOST_BACKUP_DIR:-$(read_env_value HOST_BACKUP_DIR)}"
BACKUP_ROOT="${BACKUP_ROOT:-$HOME/projects/backups/task-tracker}"
BACKUP_KEEP="${BACKUP_KEEP:-$(read_env_value BACKUP_KEEP)}"
BACKUP_KEEP="${BACKUP_KEEP:-20}"

mkdir -p "$BACKUP_ROOT"

if ! docker compose ps --status running --services | grep -qx db; then
  [ "$generated_local_env" -eq 0 ] || rm -f "$PROJECT_DIR/.env"
  echo "PostgreSQL container is not running; backup skipped." >&2
  exit 0
fi

stamp="$(date +%Y%m%d_%H%M%S)"
workdir="$(mktemp -d "$BACKUP_ROOT/.tasktracker_${stamp}_XXXXXX")"
archive="$BACKUP_ROOT/tasktracker_backup_${stamp}.tar.gz"
tmp_archive="${archive}.tmp"
checksum="${archive}.sha256"

cleanup() {
  rm -rf "$workdir" "$tmp_archive"
  if [ "$generated_local_env" -eq 1 ]; then
    rm -f "$PROJECT_DIR/.env"
  fi
}
trap cleanup EXIT INT TERM

version="unknown"
[ -f VERSION ] && version="$(tr -d '\r\n' < VERSION)"
commit="unknown"
if command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  commit="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
fi

printf 'Creating database dump...\n'
docker compose exec -T db sh -c \
  'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' \
  > "$workdir/database.dump"
test -s "$workdir/database.dump"

printf 'Creating media archive...\n'
if docker compose ps --status running --services | grep -qx web; then
  docker compose exec -T web python -c \
    'import os,sys,tarfile; os.makedirs("/app/media", exist_ok=True); t=tarfile.open(fileobj=sys.stdout.buffer, mode="w|gz"); t.add("/app/media", arcname="."); t.close()' \
    > "$workdir/media.tar.gz"
  test -s "$workdir/media.tar.gz"
else
  printf 'Web container is not running; media archive omitted.\n' >&2
fi

cat > "$workdir/manifest.txt" <<EOF
Task Tracker host backup
created_at=$(date --iso-8601=seconds 2>/dev/null || date)
version=$version
git_commit=$commit
project_dir=$PROJECT_DIR
contains_database=yes
contains_media=$([ -s "$workdir/media.tar.gz" ] && echo yes || echo no)
real_env_included=no
EOF

[ -f .env.example ] && cp .env.example "$workdir/env.example"
[ -f VERSION ] && cp VERSION "$workdir/VERSION"

printf 'Packing portable archive...\n'
tar -C "$workdir" -czf "$tmp_archive" .
test -s "$tmp_archive"
mv "$tmp_archive" "$archive"
(cd "$BACKUP_ROOT" && sha256sum "$(basename "$archive")") > "$checksum"

# The UI reads only this non-secret metadata through a read-only Docker bind mount.
mkdir -p "$PROJECT_DIR/backup_status"
python3 - "$PROJECT_DIR/backup_status/backup_status.json" "$archive" "$checksum" "$(test -s "$workdir/media.tar.gz" && echo true || echo false)" <<'PYBACKUPSTATUS'
import datetime, json, os, pathlib, sys
path = pathlib.Path(sys.argv[1])
archive = pathlib.Path(sys.argv[2])
checksum = pathlib.Path(sys.argv[3])
payload = {
    "completed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "archive_name": archive.name,
    "size_bytes": archive.stat().st_size,
    "media_included": sys.argv[4] == "true",
    "sha256": checksum.read_text(encoding="utf-8").split()[0],
    "host_os": "Linux",
}
tmp = path.with_suffix(".json.tmp")
tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
os.replace(tmp, path)
PYBACKUPSTATUS

ln -sfn "$(basename "$archive")" "$BACKUP_ROOT/latest.tar.gz" 2>/dev/null || true

# Keep the newest N archives and matching checksum files.
mapfile -t old_archives < <(ls -1t "$BACKUP_ROOT"/tasktracker_backup_*.tar.gz 2>/dev/null | tail -n +$((BACKUP_KEEP + 1)) || true)
for old in "${old_archives[@]:-}"; do
  [ -n "$old" ] || continue
  rm -f "$old" "${old}.sha256"
done

trap - EXIT INT TERM
rm -rf "$workdir"
if [ "$generated_local_env" -eq 1 ]; then
  rm -f "$PROJECT_DIR/.env"
fi

echo "Backup created outside Docker:"
echo "  $archive"
echo "  $checksum"
echo "Copy the .tar.gz and .sha256 files to a USB drive when needed."
