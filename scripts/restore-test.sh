#!/bin/sh
# Teste de restore (rodar trimestralmente): restaura o ultimo backup em banco temporario e compara contagens.
set -eu
DIR="${1:-./backups}"; SRC_DB="${PGDATABASE:-gamatermic}"; TMP="restore_test_$$"
LATEST="$(ls -1t "$DIR"/gamatermic-*.dump.enc | head -1)"
echo "usando $LATEST"
createdb "$TMP"
trap 'dropdb --if-exists "$TMP"' EXIT
sh "$(dirname "$0")/restore.sh" "$LATEST" "$TMP"
for t in users dashboards widgets datasets dataset_rows devices audit_logs; do
  a="$(psql -Atc "select count(*) from $t" "$SRC_DB")"; b="$(psql -Atc "select count(*) from $t" "$TMP")"
  echo "$t: origem=$a restaurado=$b"
done
echo "restore-test concluido (divergencias pequenas sao esperadas se houve escrita apos o backup)"
