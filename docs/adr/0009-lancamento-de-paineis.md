# ADR 0009 — Lançamento de painéis (no ar / fora do ar) e link de compartilhamento

Status: aceito · Data: 30/10/2026

**Decisão.** Cada dashboard tem um estado de publicação em `dashboards.status`: `published` (**no ar**) ou `offline` (**fora do ar**). Interruptor simples, sem rascunho/versionamento (continua Fase 2) e sem agendamento.

- `PUT /api/v1/dashboards/{id}/publication {online}` exige `dashboard:edit` com nível *edit* no recurso. Audita `dashboard.published` / `dashboard.unpublished` e emite `config_changed` (TVs refazem a playlist em segundos).
- **Fora do ar**: some da listagem e retorna 403 `dashboard_offline` (visualização, dados, preview) para quem não edita; quem edita continua vendo, editando e fazendo preview. A TV **pula** o painel (filtrado na consulta da playlist; acesso direto → 403). Se a playlist esvaziar, a TV mostra o aviso de playlist vazia.
- Dashboards **novas e duplicadas nascem fora do ar**; as semeadas (`bootstrap`) nascem no ar. Mudar o painel (editor) não o tira do ar.
- **Link de compartilhamento = link interno** (`/dashboards/{id}`): exige login e permissão (autorização no backend, princípios 1 e 6). Quem não tem concessão recebe 403. **Não há link público por token** — exigiria novo ADR por expor dados a quem tiver a URL.
- Playlists podem conter painéis fora do ar (a UI avisa que a TV pula).
