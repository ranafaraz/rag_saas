# Backup, Recovery, and Server Migration

## What runs where

The full stack runs as Docker Compose services inside a single Ubuntu VM
(`ragsaas-vm`, under Hyper-V on the host server). All application state lives
in named Docker volumes (`postgres_data`, `mongodb_data`, `qdrant_data`,
`redis_data`, `ollama_data`, `upload_data`); code lives in this git repo.

## Automatic recovery (already configured)

- Every service in `docker-compose.yml` has `restart: unless-stopped`, so a
  Docker daemon restart (e.g. after a VM reboot) brings everything back up
  automatically.
- The Hyper-V VM is set to auto-start when the host boots
  (`Set-VM -AutomaticStartAction Start`).
- `~/backup.sh` runs via cron every 6 hours on the VM, producing a timestamped
  tarball in `~/backups/` containing:
  - a `pg_dump` of the Postgres database
  - a `mongodump` archive of MongoDB
  - a tarball of the raw Qdrant data directory
  - a copy of `.env`
  The last 14 backups are kept on the VM.
- The Windows host pulls those backups down daily via the
  `RagSaasBackupPull` scheduled task, into
  `C:\HyperV\rag_saas_vm\backups\` — so a copy exists outside the VM's own
  disk.
- A weekly Hyper-V checkpoint (`RagSaasVMCheckpoint`, Sundays 4am, last 4
  kept) gives a whole-VM rollback point independent of the above.

## Restoring from a backup tarball

```bash
tar -xzf rag_saas-backup-<timestamp>.tar.gz
cd tmp-<timestamp>

# Postgres
docker compose exec -T postgres pg_restore -U rag_admin -d rag_core_db --clean --if-exists < postgres.dump

# MongoDB
docker compose exec -T mongodb mongorestore --username admin --password <password> \
  --authenticationDatabase admin --archive --drop < mongo.archive

# Qdrant (stop qdrant first, then replace its volume contents)
docker compose stop qdrant
docker run --rm -v rag_saas_qdrant_data:/data -v "$(pwd)":/backup alpine \
  sh -c "rm -rf /data/* && tar -xzf /backup/qdrant_data.tar.gz -C /data"
docker compose start qdrant

# .env — compare against .env.bak and merge as needed
```

## Moving the app to a different server

Everything needed to reproduce the app lives in two places: this git repo
(code + `docker-compose.yml`) and a backup tarball (data + `.env`). To move
to a new server:

1. Install Docker + Docker Compose on the new host (Linux; a Linux VM if the
   host is Windows Server, since Windows containers can't run this stack).
2. `git clone` this repo.
3. Copy the latest backup tarball from `C:\HyperV\rag_saas_vm\backups\` (or
   the VM's `~/backups/`) to the new host.
4. `docker compose up -d` to create empty volumes and start the stack.
5. Restore the data into the running containers using the steps above.
6. Re-pull the Ollama models: `docker compose exec ollama ollama pull nomic-embed-text`
   and `docker compose exec ollama ollama pull llama3.2:3b` (not included in
   backups since they're large and re-downloadable).

No host-specific configuration is required beyond Docker itself — networking,
secrets, and service wiring are all defined in `docker-compose.yml` and
`.env`.
