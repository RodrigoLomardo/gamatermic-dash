#!/bin/sh
# Atualiza o snapshot do contrato OpenAPI e o cliente TS. Rode apos mudar endpoints/schemas e revise o diff.
set -eu
cd "$(dirname "$0")/../backend"
uv run python -c "import json;from app.main import app;print(json.dumps(app.openapi(),sort_keys=True,indent=1))" > ../docs/contracts/openapi.snapshot.json
cd ../frontend
npx openapi-typescript ../docs/contracts/openapi.snapshot.json -o src/shared/api/schema.d.ts
echo "snapshot e cliente atualizados"
