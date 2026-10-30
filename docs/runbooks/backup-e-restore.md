# Runbook — Backup e restore (RPO 24 h, RTO 4 h)

O serviço `backup` roda `scripts/backup.sh` a cada 24 h: `pg_dump -Fc` criptografado com AES-256 (`BACKUP_PASSPHRASE`), retenção `BACKUP_RETENTION_DAYS`, cópia externa opcional via `rclone` (`BACKUP_RCLONE_REMOTE`). **Guarde a frase fora do servidor** (sem ela o backup é inútil).

**Restaurar (VPS nova ou banco limpo):**
```bash
docker compose -f docker-compose.prod.yml up -d db
docker compose -f docker-compose.prod.yml exec -e BACKUP_PASSPHRASE=... backup sh /scripts/restore.sh /backups/gamatermic-AAAAMMDDTHHMMSSZ.dump.enc "$POSTGRES_DB"
docker compose -f docker-compose.prod.yml up -d
```
**Teste trimestral:** `scripts/restore-test.sh <dir>` restaura o último backup em banco temporário e compara contagens (users, dashboards, widgets, datasets, dataset_rows, devices, audit_logs). Validado em 30/10/2026 no ambiente de desenvolvimento (10.407 linhas de dados restauradas idênticas). **Registre cada teste aqui** (data, responsável, resultado).
Os arquivos brutos de upload (`uploads`) são descartáveis: o dado já está no banco; a retenção é de 90 dias.
