#!/bin/bash
# Backs up Postgres, MongoDB, Qdrant, and .env into a timestamped tarball.
# Runs against live containers (no downtime). Keeps the last KEEP backups.
set -euo pipefail

APP_DIR="$HOME/rag_saas"
BACKUP_ROOT="$HOME/backups"
TS=$(date -u +%Y%m%d-%H%M%S)
WORK="$BACKUP_ROOT/tmp-$TS"
KEEP=14

mkdir -p "$WORK"
cd "$APP_DIR"

MONGO_PASS=$(grep '^MONGO_PASSWORD=' .env | cut -d= -f2-)
docker compose exec -T postgres pg_dump -U rag_admin -Fc rag_core_db > "$WORK/postgres.dump"
docker compose exec -T mongodb mongodump --username admin --password "$MONGO_PASS" --authenticationDatabase admin --archive > "$WORK/mongo.archive"

QDRANT_VOLUME=$(docker volume ls -q --filter name=qdrant_data)
QDRANT_MOUNT=$(docker volume inspect "$QDRANT_VOLUME" --format '{{.Mountpoint}}')
sudo tar -czf "$WORK/qdrant_data.tar.gz" -C "$QDRANT_MOUNT" .

cp .env "$WORK/.env.bak"

tar -czf "$BACKUP_ROOT/rag_saas-backup-$TS.tar.gz" -C "$BACKUP_ROOT" "tmp-$TS"
rm -rf "$WORK"

cd "$BACKUP_ROOT"
ls -1t rag_saas-backup-*.tar.gz | tail -n +$((KEEP + 1)) | xargs -r rm -f

echo "Backup complete: $BACKUP_ROOT/rag_saas-backup-$TS.tar.gz"
