#!/bin/sh
# Backup diario criptografado (AES-256) do Postgres. RPO alvo: 24 h.
# Uso: backup.sh <diretorio-destino>   (PG* e BACKUP_PASSPHRASE vem do ambiente)
set -eu
DEST="${1:-./backups}"
: "${BACKUP_PASSPHRASE:?defina BACKUP_PASSPHRASE}"
mkdir -p "$DEST"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$DEST/gamatermic-$STAMP.dump.enc"
pg_dump -Fc --no-owner | openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt -pass env:BACKUP_PASSPHRASE -out "$OUT"
[ -s "$OUT" ] || { echo "backup vazio" >&2; exit 1; }
echo "backup ok: $OUT ($(wc -c < "$OUT") bytes)"
find "$DEST" -name 'gamatermic-*.dump.enc' -mtime +"${BACKUP_RETENTION_DAYS:-14}" -delete
if [ -n "${BACKUP_RCLONE_REMOTE:-}" ]; then rclone copy "$OUT" "$BACKUP_RCLONE_REMOTE" && echo "enviado para $BACKUP_RCLONE_REMOTE"; fi
