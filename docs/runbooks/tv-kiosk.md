# Runbook — TV em modo kiosk e substituição

**Hardware suportado (premissa a validar no spike B):** mini-PC ou Android TV box/Chromecast com Google TV com Chromium/Chrome recente, 1920×1080 ou 4K. Smart TVs nativas com navegador antigo ficam fora. Build alvo: ES2020.

**Chrome/Chromium (Linux/Windows):**
```bash
chromium --kiosk --noerrdialogs --disable-infobars --autoplay-policy=no-user-gesture-required --disable-session-crashed-bubble --check-for-update-interval=31536000 https://SEU_DOMINIO/tv
```
Desative suspensão de tela/energia no SO e esconda o cursor. Reinício diário do navegador/PC (cron) é recomendado; o player também recarrega sozinho às 03:00 e quando a versão do frontend muda.

**Pareamento:** abra `/tv` → aparece o código (e QR). Em *TVs e playlists* informe o código, confira IP/navegador, nomeie e escolha a playlist. Troca de playlist/setor não exige re-parear.
**Substituir TV:** revogue a antiga e pareie a nova com a mesma playlist.
**Diagnóstico:** painel mostra *Online/Offline* e último sinal; badge **“Sem conexão”** na TV = sem resposta do servidor há 3 min (último dado continua visível); badge âmbar **“Dados de origem atrasados”** = dataset passou do SLA de frescor (a carga parou, não a rede).
**Checklist visual (legível a 3 m):** KPIs ≥ 48 px a 1080p, contraste AA, sem rolagem, relógio e “Dados de HH:MM” visíveis.
**Spike B (pendente — precisa do equipamento real):** manter 24 h via Caddy na rede da empresa; derrubar a rede por 10 min e conferir badge + último dado + reconexão sem intervenção; medir memória (DevTools Performance Monitor) no início e após 24 h.
