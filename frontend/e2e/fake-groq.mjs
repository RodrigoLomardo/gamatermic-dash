// Groq falsa para o E2E (ADR 0010): responde /models e /chat/completions com propostas deterministicas
// montadas a partir dos campos que a API enviou. Uso: node e2e/fake-groq.mjs  (porta FAKE_GROQ_PORT, padrao 8765)
// e suba a API com GAMA_GROQ_BASE_URL=http://127.0.0.1:8765/openai/v1
import http from "node:http";

const PORT = Number(process.env.FAKE_GROQ_PORT ?? 8765);
const MODELS = ["openai/gpt-oss-120b", "openai/gpt-oss-20b"];

const W = (o) => ({ rationale: "Sugestão de teste.", measures: [], dimensions: [], columns: [], time_granularity: null, period_preset: null, filters: [],
  sort_by: null, sort_dir: "desc", limit: null, format: "currency", horizontal: null, target: null, x: null, y: null, w: null, h: null, ...o });

function proposals(userMsg) {
  const ctx = JSON.parse(userMsg.split("DATASET:\n")[1].split("\n\nPEDIDO")[0]);
  const num = ctx.campos.find((f) => f.type === "decimal") ?? ctx.campos.find((f) => f.type === "integer");
  const dim = ctx.campos.find((f) => f.type === "string" && f.role === "dimension");
  // painel com layout: estreita o primeiro grafico largo (w >= 8) e poe o ranking ao lado; painel novo: KPIs no topo
  const wide = ctx.layout_atual?.widgets.find((w) => w.w >= 8);
  const layout_changes = wide ? [{ ref: wide.ref, x: wide.x, y: wide.y, w: wide.w - 4, h: wide.h, reason: "Estreita para abrir espaço ao lado." }] : [];
  const pos = (x, y, w, h) => (ctx.layout_atual ? {} : { x, y, w, h });
  const out = [W({ type: "kpi", title: "Registros", measures: [{ agg: "count", field: null, label: "Registros" }], format: "integer", ...pos(0, 0, 3, 3) })];
  if (num) out.push(W({ type: "kpi", title: `Total de ${num.label}`, measures: [{ agg: "sum", field: num.name, label: "Total" }], ...pos(3, 0, 3, 3) }));
  if (num && ctx.campo_de_tempo) out.push(W({ type: "line", title: `${num.label} por mês`, measures: [{ agg: "sum", field: num.name, label: "Total" }], time_granularity: "month", ...pos(0, 3, 8, 4) }));
  if (num && dim) out.push(W({ type: "bar", title: `Top ${dim.label}`, measures: [{ agg: "sum", field: num.name, label: "Total" }], dimensions: [dim.name], sort_by: "measure", limit: 10, horizontal: true,
    ...(wide ? { x: wide.x + wide.w - 4, y: wide.y, w: 4, h: wide.h } : pos(8, 3, 4, 4)) }));
  out.push(W({ type: "bar", title: "Campo inventado", measures: [{ agg: "sum", field: "nao_existe", label: "X" }], dimensions: ["nao_existe"] }));
  return { explanation: `Sugestões para ${ctx.dataset}.`, widgets: out, layout_changes };
}

http.createServer((req, res) => {
  let body = "";
  req.on("data", (c) => (body += c));
  req.on("end", () => {
    const send = (status, obj) => { res.writeHead(status, { "Content-Type": "application/json" }); res.end(JSON.stringify(obj)); };
    if (!/^Bearer gsk_\S{16,}$/.test(req.headers.authorization ?? "")) return send(401, { error: { message: "Invalid API Key" } });
    if (req.method === "GET" && req.url.endsWith("/models")) return send(200, { data: MODELS.map((id) => ({ id })) });
    if (req.method === "POST" && req.url.endsWith("/chat/completions")) {
      const msgs = JSON.parse(body).messages;
      const last = msgs.at(-1).content;
      const content = last.includes("recusados") ? { explanation: "", widgets: [], layout_changes: [] } : proposals(msgs[1].content);
      return send(200, { choices: [{ message: { content: JSON.stringify(content) } }], usage: { prompt_tokens: 812, completion_tokens: 240 } });
    }
    send(404, { error: { message: "not found" } });
  });
}).listen(PORT, "127.0.0.1", () => console.log(`fake groq em http://127.0.0.1:${PORT}/openai/v1`));
