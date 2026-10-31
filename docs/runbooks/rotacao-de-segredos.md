# Runbook — Rotação de segredos

- **JWT (`GAMA_JWT_SECRET`)**: trocar o segredo invalida todos os access tokens (10 min) e TVs renovam sozinhas; refresh tokens continuam válidos (são opacos). Para rotação sem queda, subir novo `GAMA_JWT_KID` e manter o segredo antigo por 15 min (suporte a múltiplas chaves é item da Fase 2).
- **Fernet (`GAMA_FERNET_KEY`)**: cifra segredos de conectores (hoje sem uso no MVP), credencial pendente de pareamento (vida ≤ 10 min) e a **chave da API Groq** (`system_settings.secret_ciphertext`, ADR 0010). Antes de trocar: re-cifrar `data_sources.secret_encrypted` com a chave nova. Para a Groq, o caminho mais simples é colar a chave de novo em **Configurações → IA** depois da troca (sem isso a IA aparece como não configurada; nada mais é afetado).
- **Chave da API Groq**: gere uma nova em console.groq.com/keys, cole em **Configurações → IA → Salvar**, clique **Testar conexão** e só então revogue a antiga no console. Vazou? Revogue no console primeiro (a IA fica indisponível até salvar a nova).
- **Senha do Postgres**: alterar no `.env` e no banco (`ALTER USER`), reiniciar `api`/`worker`/`backup`.
- **Admin**: `docker compose exec api python -m app.cli bootstrap --admin-email X --admin-password '…'` cria/atribui; reset pelo painel (*Usuários → Redefinir senha*).
- **Credencial vazada de TV**: *TVs e playlists → Revogar* (efeito imediato; a TV volta ao pareamento) e re-parear.
