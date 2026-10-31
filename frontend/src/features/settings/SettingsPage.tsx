import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { ApiError, S, get, post, put } from "@/shared/api/http";
import { fmtDateTime } from "@/shared/lib/format";
import { Badge, Button, Card, ErrorBox, Field, Input, Select, Spinner, useToasts, cx } from "@/shared/ui/ui";

type Ai = S["AiSettingsOut"]; type TestOut = S["AiTestOut"];
const fail = (e: unknown) => (e instanceof ApiError ? e.message : (e as Error).message);

// abas da pagina: novas configuracoes do sistema entram aqui
const TABS = [{ id: "ai", label: "IA (Groq)" }] as const;

export function SettingsPage() {
  const [tab, setTab] = useState<(typeof TABS)[number]["id"]>("ai");
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Configurações</h1>
      <div role="tablist" aria-label="Seções de configuração" className="flex gap-1 border-b border-line">
        {TABS.map((t) => (
          <button key={t.id} role="tab" id={`tab-${t.id}`} aria-selected={tab === t.id} aria-controls={`panel-${t.id}`} onClick={() => setTab(t.id)}
            className={cx("-mb-px rounded-t-lg border-b-2 px-4 py-2 text-sm font-semibold", tab === t.id ? "border-accent text-ink" : "border-transparent text-ink-mute hover:text-ink")}>
            {t.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>{tab === "ai" && <AiSettings />}</div>
    </div>
  );
}

export function AiSettings() {
  const qc = useQueryClient(); const toast = useToasts((s) => s.push);
  const q = useQuery({ queryKey: ["settings-ai"], queryFn: () => get<Ai>("/settings/ai") });
  const [form, setForm] = useState<{ enabled: boolean; model: string; key: string }>({ enabled: false, model: "", key: "" });
  const [busy, setBusy] = useState(false);
  const [test, setTest] = useState<TestOut | null>(null);
  useEffect(() => { if (q.data) setForm({ enabled: q.data.enabled, model: q.data.model, key: "" }); }, [q.data]);

  if (q.isLoading) return <Spinner />;
  if (q.error) return <ErrorBox error={q.error} onRetry={() => q.refetch()} />;
  const d = q.data!;

  const save = async (apiKey?: string, enabled = form.enabled) => {
    setBusy(true); setTest(null);
    try {
      const out = await put<Ai>("/settings/ai", { enabled, model: form.model, api_key: apiKey });
      qc.setQueryData(["settings-ai"], out); qc.invalidateQueries({ queryKey: ["ai-status"] });
      toast(apiKey === "" ? "Chave removida." : "Configurações salvas.");
    } catch (e) { toast(fail(e), "danger"); } finally { setBusy(false); }
  };
  const removeKey = () => { if (confirm("Remover a chave da Groq? A IA ficará indisponível.")) save("", false); };
  const runTest = async () => {
    setBusy(true);
    try { setTest(await post<TestOut>("/settings/ai/test")); } catch (e) { toast(fail(e), "danger"); } finally { setBusy(false); }
  };

  return (
    <Card title="Assistente de dashboards (Groq)" actions={<Badge tone={d.enabled && d.api_key.configured ? "ok" : "neutral"}>{d.enabled && d.api_key.configured ? "Ativo" : "Inativo"}</Badge>}>
      <form className="max-w-xl space-y-4" onSubmit={(e) => { e.preventDefault(); save(form.key.trim() ? form.key.trim() : undefined); }}>
        <p className="text-sm text-ink-soft">
          A IA sugere gráficos a partir de um pedido em texto. Ela recebe só os nomes e tipos dos campos do dataset, nunca as linhas de dados nem campos pessoais.
          Crie a chave em <a className="font-semibold text-accent-dark underline" href="https://console.groq.com/keys" target="_blank" rel="noreferrer noopener">console.groq.com/keys</a>.
        </p>
        <Field label="Chave de API" hint={d.api_key.configured ? `Configurada (termina em ${d.api_key.last4}). Deixe em branco para manter.` : "Nenhuma chave configurada."}>
          {(id) => <Input id={id} type="password" autoComplete="off" spellCheck={false} value={form.key} placeholder={d.api_key.configured ? "••••••••••••" : "gsk_…"}
            onChange={(e) => setForm({ ...form, key: e.target.value })} />}
        </Field>
        <Field label="Modelo">
          {(id) => <Select id={id} value={form.model} onChange={(e) => setForm({ ...form, model: e.target.value })}>{d.models.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}</Select>}
        </Field>
        <label className="flex items-center gap-2 text-sm font-medium">
          <input type="checkbox" checked={form.enabled} onChange={(e) => setForm({ ...form, enabled: e.target.checked })} /> IA ativa para quem cria dashboards
        </label>
        <div className="flex flex-wrap gap-2">
          <Button type="submit" disabled={busy}>Salvar</Button>
          <Button type="button" variant="secondary" disabled={busy || !d.api_key.configured} onClick={runTest}>Testar conexão</Button>
          {d.api_key.configured && <Button type="button" variant="ghost" disabled={busy} onClick={removeKey}>Remover chave</Button>}
        </div>
        {test && (
          <p role="status" className={cx("rounded-lg p-3 text-sm", test.ok ? "border border-ok text-ok" : "border border-danger text-danger")}>
            {test.ok ? `Conexão OK com ${test.model} (${test.latency_ms} ms).` : test.error}
          </p>
        )}
        {d.updated_at && <p className="text-xs text-ink-mute">Última alteração: {fmtDateTime(d.updated_at)}</p>}
      </form>
    </Card>
  );
}
