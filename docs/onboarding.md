# Rodando o Gamatermic Dash do zero

Guia para quem está abrindo o projeto pela primeira vez, numa máquina sem nada instalado. Assume macOS. No Windows, use WSL2 com Ubuntu e siga a parte de Linux: o `Makefile` não roda no PowerShell puro.

## 1. Instalar as ferramentas

| Ferramenta | Versão | Para quê |
|---|---|---|
| Git | qualquer | clonar o repo |
| Node | 22 | frontend |
| `uv` | recente | Python e dependências do backend |
| Docker Desktop | recente | Postgres de desenvolvimento |
| `make` | qualquer | atalhos do `Makefile` |

**macOS (Homebrew):**

```bash
# Homebrew, se ainda não tiver
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

brew install git node@22 uv
brew install --cask docker        # depois abra o Docker Desktop uma vez e aguarde ficar "running"
xcode-select --install            # traz o make
```

Se o `node` não ficar no PATH, rode `brew link --overwrite node@22`.

**Ubuntu/WSL:** `sudo apt install git make curl`, depois [nvm](https://github.com/nvm-sh/nvm) para o Node 22 (`nvm install 22`), `curl -LsSf https://astral.sh/uv/install.sh | sh` para o uv e o Docker Desktop com integração WSL.

Não é preciso instalar Python: o `uv` baixa o 3.12 sozinho (`pyproject.toml` pede `>=3.12,<3.14`).

**Confira as versões:**

```bash
git --version && node -v && uv --version && docker --version && make --version
```

O `node -v` deve mostrar `v22.x`.

## 2. Clonar e instalar as dependências

```bash
git clone https://github.com/RodrigoLomardo/gamatermic-dash.git
cd gamatermic-dash

cd backend && uv sync && cd ..       # cria backend/.venv com as deps travadas (uv.lock)
cd frontend && npm ci && cd ..       # instala exatamente o package-lock.json
```

Use `npm ci`, não `npm install`, para não alterar o lockfile. Se o clone pedir login, use `gh auth login` ou um token do GitHub.

## 3. Subir o Postgres

Com o Docker Desktop aberto:

```bash
make db
docker compose ps         # o serviço db deve ficar "healthy"
```

O banco fica em `localhost:5433`, usuário `gama`, senha `gama`.

Dois pontos que o README não cobre:

- O Docker cria só o banco `gamatermic`. Os testes usam o `gamatermic_test`, que você cria à mão:

  ```bash
  docker compose exec db psql -U gama -d gamatermic -c "create database gamatermic_test"
  ```

- O código assume por padrão conexão sem senha (`postgresql+asyncpg://gama@localhost:5433/...`). O container com senha pode recusar isso, por isso o passo 4 define a URL com senha.

## 4. Configurar o `.env` (desenvolvimento)

**Não copie o `.env.example`.** Ele é de produção: `GAMA_ENV=prod`, host `db` do Docker, cookie `secure` e `CHANGE_ME` nos segredos. Em dev, crie um `.env` mínimo na raiz do repo (já está no `.gitignore`):

```bash
cat > .env <<'EOF'
GAMA_ENV=dev
GAMA_DATABASE_URL=postgresql+asyncpg://gama:gama@localhost:5433/gamatermic
GAMA_ADMIN_EMAIL=admin@gamatermic.local
GAMA_ADMIN_PASSWORD=troque-por-uma-frase-longa-local
EOF
```

Os demais valores (JWT, Fernet, CORS) têm defaults de dev em `backend/app/core/config.py`. Nunca use esses defaults nem este `.env` em produção.

## 5. Criar as tabelas e os dados iniciais

```bash
make migrate       # aplica o schema (Alembic)
make bootstrap     # cria admin, roles, datasets e dashboards de partida
```

O login é o e-mail e a senha definidos no `.env`.

## 6. Carregar dados

O relatório real `Vendas Ploomes 2025_2026.xlsx` **não está no Git** (tem dados de clientes). Peça o arquivo ao responsável por um canal seguro, coloque-o em `.cursor/docs/` e rode:

```bash
make import FILE=".cursor/docs/Vendas Ploomes 2025_2026.xlsx"
```

Sem o arquivo, gere vendas fictícias com `python3 scripts/gerar-vendas-exemplo.py` (grava um CSV em `docs/exemplos/`, que pode ser enviado pela tela de carga do sistema).

## 7. Rodar o sistema

Dois terminais, ambos na raiz do repo:

```bash
# terminal 1
make dev-api       # http://localhost:8000/api/docs

# terminal 2
make dev-web       # http://localhost:5173
```

Abra http://localhost:5173 e entre com o admin do passo 4.

Para testar o modo TV, abra `http://localhost:5173/tv`, copie o código e aprove em **TVs e playlists**.

## 8. Testes e lint

```bash
export GAMA_TEST_DATABASE_URL=postgresql+asyncpg://gama:gama@localhost:5433/gamatermic_test
make test
make lint
```

O `export` é necessário: os testes leem essa variável direto do ambiente e **não leem o `.env`**. Sem ele tentam conectar sem senha e falham.

O E2E com Playwright é opcional: rode `cd frontend && npx playwright install` uma vez e veja a seção de E2E do README.

## 9. Dia a dia

```bash
git pull
cd backend && uv sync && cd ..       # se o uv.lock mudou
cd frontend && npm ci && cd ..       # se o package-lock.json mudou
make migrate                         # se entrou migration nova
make db                              # se o Docker foi reiniciado
```

Antes de abrir um PR, rode `make lint` e `make test`. O CI (`.github/workflows/ci.yml`) roda os mesmos checks e também falha se a API mudar sem regerar o snapshot (`scripts/update-openapi-snapshot.sh`).

## Problemas comuns

| Sintoma | Causa provável | Solução |
|---|---|---|
| `Cannot connect to the Docker daemon` | Docker Desktop fechado | Abra o app e espere ficar "running" |
| `password authentication failed for user "gama"` | Falta `GAMA_DATABASE_URL` com senha | Passo 4. Nos testes, exporte `GAMA_TEST_DATABASE_URL` (passo 8) |
| `database "gamatermic_test" does not exist` | Banco de teste não criado | Comando do passo 3 |
| `port 5433 already in use` | Outro Postgres usando a porta | Pare o outro Postgres ou use a opção sem Docker do README |
| `make: command not found` | Sem ferramentas de linha de comando | `xcode-select --install` |
| Login falha em `localhost` | `.env` copiado do `.env.example` (cookie `secure`) | Use o `.env` do passo 4 |
