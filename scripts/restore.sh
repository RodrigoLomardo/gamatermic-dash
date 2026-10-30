#!/bin/sh
# Restaura um backup .dump.enc em um banco (use um banco NOVO/limpo).
# Uso: restore.sh <arquivo.dump.enc> <banco-destino>   (PG* e BACKUP_PASSPHRASE no ambiente)
set -eu
FILE="${1:?arquivo}"; DB="${2:?banco destino}"
: "${BACKUP_PASSPHRASE:?defina BACKUP_PASSPHRASE}"
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass env:BACKUP_PASSPHRASE -in "$FILE" | pg_restore --no-owner --clean --if-exists -d "$DB"
echo "restore ok em $DB"
