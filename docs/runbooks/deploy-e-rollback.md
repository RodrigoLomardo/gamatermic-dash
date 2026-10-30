# Runbook — Deploy e rollback

**Pré-requisitos (uma vez):** VPS Ubuntu LTS, Docker + compose plugin, usuário `deploy` sem root, UFW liberando só 22/80/443, SSH por chave, fail2ban, `unattended-upgrades`. DNS do domínio apontando para a VPS. Clonar o repositório em `/opt/gamatermic-dash`, copiar `.env.example` → `.env` e preencher (segredos com `openssl rand -base64 48`).

**Deploy:** Actions → *deploy* (informa tag/commit) ou, manualmente:
```bash
cd /opt/gamatermic-dash && git fetch --all --tags && git checkout <tag>
docker compose -f docker-compose.prod.yml --env-file .env build
docker compose -f docker-compose.prod.yml --env-file .env up -d --remove-orphans   # serviço `migrate` roda antes da API
curl -fsS https://$SITE_ADDRESS/api/v1/health/ready
```
Primeiro deploy: o serviço `migrate` executa `alembic upgrade head` e `bootstrap` (cria o admin de `GAMA_ADMIN_EMAIL`/`GAMA_ADMIN_PASSWORD`; troque a senha no primeiro acesso e remova `GAMA_ADMIN_PASSWORD` do `.env`). Depois, carregue os dados: *Dados e cargas → dataset → enviar arquivo*.

**Rollback:** `git checkout <tag-anterior>` + `build` + `up -d`. Migrations são aditivas por padrão; se uma migration precisar ser desfeita: `docker compose run --rm migrate alembic downgrade -1` **antes** de subir o código antigo, e restaure backup se houver perda de dados (ver backup-e-restore).
**Versão do frontend:** `GAMA_FRONTEND_VERSION` é lido pelas TVs (`/display/config`); ao mudar, as TVs recarregam sozinhas.
