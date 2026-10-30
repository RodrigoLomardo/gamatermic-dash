import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { DragEvent, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useAuth } from "@/app/auth";
import { ApiError, S, api, get, patch, post, put } from "@/shared/api/http";
import { fmtDateTime } from "@/shared/lib/format";
import { Badge, Button, Card, Empty, ErrorBox, Field, Input, Modal, Select, Spinner, Table, useToasts } from "@/shared/ui/ui";

type Ds = S["DatasetOut"]; type Run = S["RunOut"];
const TONE: Record<string, "ok" | "warn" | "danger" | "neutral" | "accent"> = { succeeded: "ok", succeeded_with_errors: "warn", failed: "danger", cancelled: "neutral", queued: "accent", running: "accent" };
const LABEL: Record<string, string> = { succeeded: "Concluída", succeeded_with_errors: "Concluída com erros", failed: "Falhou", cancelled: "Cancelada", queued: "Na fila", running: "Processando" };
export const RunBadge = ({ status }: { status: string }) => <Badge tone={TONE[status] ?? "neutral"}>{LABEL[status] ?? status}</Badge>;

export function DatasetsPage() {
  const { can } = useAuth();
  const ds = useQuery({ queryKey: ["datasets"], queryFn: () => get<Ds[]>("/datasets") });
  const runs = useQuery({ queryKey: ["runs-recent"], queryFn: () => get<Run[]>("/ingestion/runs", { query: { limit: 8 } }), enabled: can("ingestion:view"), refetchInterval: 5000 });
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between"><h1 className="text-2xl font-bold">Dados e cargas</h1>
        {can("dataset:manage") && <Link to="/datasets/novo"><Button>Novo dataset a partir de arquivo</Button></Link>}</div>
      {ds.isLoading && <Spinner />}{ds.error && <ErrorBox error={ds.error} />}
      <div className="grid gap-4 md:grid-cols-2">
        {ds.data?.map((d) => (
          <Card key={d.id}>
            <Link to={`/datasets/${d.id}`} className="block">
              <div className="flex items-start justify-between gap-2"><h2 className="text-lg font-semibold text-brand">{d.name}</h2>{d.stale && <Badge tone="warn">Atrasado</Badge>}</div>
              <p className="text-sm text-ink-soft">{d.description}</p>
              <dl className="mt-3 grid grid-cols-3 gap-2 text-sm">
                <div><dt className="text-xs text-ink-mute">Linhas</dt><dd className="tabular font-semibold">{d.row_count.toLocaleString("pt-BR")}</dd></div>
                <div><dt className="text-xs text-ink-mute">Modo</dt><dd className="font-semibold">{d.load_mode}</dd></div>
                <div><dt className="text-xs text-ink-mute">Última carga</dt><dd className="font-semibold">{fmtDateTime(d.last_loaded_at)}</dd></div>
              </dl>
            </Link>
          </Card>
        ))}
      </div>
      {ds.data?.length === 0 && <Empty>Nenhum dataset ainda.</Empty>}
      {can("ingestion:view") && (
        <Card title="Cargas recentes">
          <RunsTable runs={runs.data ?? []} />
        </Card>
      )}
    </div>
  );
}

export function RunsTable({ runs, onOpen }: { runs: Run[]; onOpen?: (r: Run) => void }) {
  return (
    <Table head={["Quando", "Dataset", "Arquivo", "Status", "Lidas", "Novas", "Atual.", "Iguais", "Rejeit."]} empty={runs.length === 0 && <p className="p-4 text-center text-ink-mute">Sem cargas.</p>}>
      {runs.map((r) => (
        <tr key={r.id} className={onOpen ? "cursor-pointer hover:bg-brand-soft" : ""} onClick={() => onOpen?.(r)}>
          <td className="px-3 py-2">{fmtDateTime(r.created_at)}</td><td className="px-3 py-2">{r.dataset_slug}</td>
          <td className="max-w-[14rem] truncate px-3 py-2">{r.file_name}</td><td className="px-3 py-2"><RunBadge status={r.status} /></td>
          {[r.rows_read, r.rows_inserted, r.rows_updated, r.rows_unchanged, r.rows_rejected].map((n, i) => <td key={i} className="tabular px-3 py-2 text-right">{n}</td>)}
        </tr>
      ))}
    </Table>
  );
}

export function RunDetail({ runId, onClose }: { runId: string; onClose: () => void }) {
  const run = useQuery({ queryKey: ["run", runId], queryFn: () => get<Run>(`/ingestion/runs/${runId}`), refetchInterval: (q) => (["queued", "running"].includes(q.state.data?.status ?? "") ? 1500 : false) });
  const errs = useQuery({ queryKey: ["run-errors", runId, run.data?.status], queryFn: () => get<S["RowErrorOut"][]>(`/ingestion/runs/${runId}/errors`, { query: { limit: 200 } }), enabled: !!run.data && !["queued", "running"].includes(run.data.status) });
  const toast = useToasts((s) => s.push); const qc = useQueryClient();
  const act = async (what: "cancel" | "retry") => { try { await post(`/ingestion/runs/${runId}/${what}`); qc.invalidateQueries(); toast(what === "retry" ? "Reprocessamento enfileirado." : "Carga cancelada."); } catch (e) { toast((e as Error).message, "danger"); } };
  const csv = async () => {
    const text = await api<string>("GET", `/ingestion/runs/${runId}/errors.csv`, { text: true });
    const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([text], { type: "text/csv" })); a.download = `erros-${runId}.csv`; a.click();
  };
  const r = run.data;
  return (
    <Modal open wide title="Detalhe da carga" onClose={onClose}>
      {!r ? <Spinner /> : (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-3"><RunBadge status={r.status} /><span className="text-sm text-ink-soft">{r.file_name} → {r.dataset_slug}</span></div>
          {r.error_summary && <p role="status" className="rounded-lg bg-brand-soft p-3 text-sm">{r.error_summary}</p>}
          <dl className="grid grid-cols-5 gap-2 text-center text-sm">
            {[["Lidas", r.rows_read], ["Novas", r.rows_inserted], ["Atualizadas", r.rows_updated], ["Iguais", r.rows_unchanged], ["Rejeitadas", r.rows_rejected]].map(([l, n]) => (
              <div key={l as string} className="rounded-lg border border-line p-2"><dt className="text-xs text-ink-mute">{l}</dt><dd className="tabular text-lg font-bold">{n}</dd></div>))}
          </dl>
          <div className="flex gap-2">
            {["queued", "running"].includes(r.status) && <Button variant="secondary" onClick={() => act("cancel")}>Cancelar</Button>}
            {["failed", "cancelled"].includes(r.status) && <Button variant="secondary" onClick={() => act("retry")}>Reprocessar</Button>}
            {r.rows_rejected > 0 && <Button variant="secondary" onClick={csv}>Baixar relatório de erros (CSV)</Button>}
          </div>
          {(errs.data?.length ?? 0) > 0 && (
            <div className="max-h-72 overflow-auto rounded-lg border border-line">
              <Table head={["Linha", "Coluna", "Código", "Mensagem", "Trecho"]}>
                {errs.data!.map((e, i) => <tr key={i}><td className="tabular px-3 py-1.5">{e.row_number}</td><td className="px-3 py-1.5">{e.column_name}</td><td className="px-3 py-1.5">{e.error_code}</td><td className="px-3 py-1.5">{e.message}</td><td className="px-3 py-1.5 font-mono text-xs">{e.raw_excerpt}</td></tr>)}
              </Table>
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}

export function UploadBox({ dataset }: { dataset: Ds }) {
  const qc = useQueryClient(); const toast = useToasts((s) => s.push);
  const inp = useRef<HTMLInputElement>(null); const [over, setOver] = useState(false); const [openRun, setOpenRun] = useState<string | null>(null);
  const [sheet, setSheet] = useState((dataset.parser_options as { sheet?: string })?.sheet ?? "");
  const up = useMutation({
    mutationFn: async (file: File) => { const f = new FormData(); f.append("file", file); return api<Run>("POST", `/datasets/${dataset.id}/uploads`, { form: f, query: { sheet: sheet || undefined } }); },
    onSuccess: (r) => { qc.invalidateQueries(); if (r.duplicate) toast("Este arquivo já foi carregado antes (nada a fazer)."); else toast("Arquivo recebido. Processando…"); setOpenRun(r.id); },
    onError: (e) => toast(e instanceof ApiError ? e.message : "Falha no envio", "danger"),
  });
  const drop = (e: DragEvent) => { e.preventDefault(); setOver(false); const f = e.dataTransfer.files[0]; if (f) up.mutate(f); };
  return (
    <>
      <div onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)} onDrop={drop}
        className={`rounded-xl border-2 border-dashed p-8 text-center ${over ? "border-accent bg-accent-soft" : "border-line"}`}>
        <p className="font-semibold">Arraste um arquivo .csv ou .xlsx aqui</p>
        <p className="mb-3 text-sm text-ink-mute">Até 20 MB · modo de carga: <b>{dataset.load_mode}</b>{dataset.load_mode === "replace_snapshot" && " (o arquivo é o estado completo; o que sumiu é removido)"}</p>
        <div className="mb-3 flex items-center justify-center gap-2"><label className="text-sm" htmlFor="sheet">Aba (xlsx)</label><Input id="sheet" className="w-48" value={sheet} onChange={(e) => setSheet(e.target.value)} placeholder="primeira aba" /></div>
        <input ref={inp} type="file" hidden accept=".csv,.txt,.xlsx" aria-label="Selecionar arquivo" onChange={(e) => e.target.files?.[0] && up.mutate(e.target.files[0])} />
        <Button onClick={() => inp.current?.click()} disabled={up.isPending}>{up.isPending ? "Enviando…" : "Escolher arquivo"}</Button>
      </div>
      {openRun && <RunDetail runId={openRun} onClose={() => setOpenRun(null)} />}
    </>
  );
}

export function DatasetDetailPage() {
  const { id } = useParams(); const { can } = useAuth();
  const ds = useQuery({ queryKey: ["dataset", id], queryFn: () => get<Ds>(`/datasets/${id}`) });
  const runs = useQuery({ queryKey: ["runs", id], queryFn: () => get<Run[]>("/ingestion/runs", { query: { dataset_id: id } }), enabled: can("ingestion:view"), refetchInterval: 5000 });
  const prev = useQuery({ queryKey: ["preview", id], queryFn: () => get<S["PreviewOut"]>(`/datasets/${id}/preview`, { query: { limit: 20 } }) });
  const [open, setOpen] = useState<string | null>(null);
  if (ds.isLoading) return <Spinner />; if (ds.error) return <ErrorBox error={ds.error} />;
  const d = ds.data!;
  return (
    <div className="space-y-4">
      <Link to="/datasets" className="text-sm text-ink-mute hover:underline">← Dados e cargas</Link>
      <div className="flex flex-wrap items-center gap-3"><h1 className="text-2xl font-bold">{d.name}</h1>{d.stale && <Badge tone="warn">Dados atrasados</Badge>}<Badge>{d.row_count.toLocaleString("pt-BR")} linhas</Badge><Badge tone="accent">v{d.version}</Badge></div>
      <p className="text-sm text-ink-soft">{d.description} Última carga: {fmtDateTime(d.last_loaded_at)}. Chave: {d.key_fields.join(" + ") || "—"}.</p>
      {can("ingestion:upload") && <UploadBox dataset={d} />}
      {can("ingestion:view") && <Card title="Histórico de cargas"><RunsTable runs={runs.data ?? []} onOpen={(r) => setOpen(r.id)} /></Card>}
      <Card title="Campos">
        <Table head={["Campo", "Rótulo", "Tipo", "Papel", "Coluna no arquivo", "Sensível"]}>
          {d.fields.map((f) => <tr key={f.name}><td className="px-3 py-1.5 font-mono text-xs">{f.name}{f.is_key && " 🔑"}</td><td className="px-3 py-1.5">{f.label}</td><td className="px-3 py-1.5">{f.data_type}</td><td className="px-3 py-1.5">{f.role}</td><td className="px-3 py-1.5">{f.source_column}</td><td className="px-3 py-1.5">{f.sensitivity === "pii" ? <Badge tone="warn">PII mascarado</Badge> : "—"}</td></tr>)}
        </Table>
      </Card>
      <Card title="Amostra (20 linhas mais recentes)" pad={false}>
        <div className="overflow-x-auto"><Table head={prev.data?.columns ?? []}>
          {prev.data?.rows.map((r, i) => <tr key={i}>{prev.data!.columns.map((c) => <td key={c} className="max-w-[16rem] truncate px-3 py-1.5">{String(r[c] ?? "")}</td>)}</tr>)}
        </Table></div>
      </Card>
      {open && <RunDetail runId={open} onClose={() => setOpen(null)} />}
    </div>
  );
}

export function NewDatasetPage() {
  const nav = useNavigate(); const toast = useToasts((s) => s.push);
  const [file, setFile] = useState<File | null>(null);
  const [inf, setInf] = useState<S["InferOut"] | null>(null);
  const [fields, setFields] = useState<S["InferredField"][]>([]);
  const [meta, setMeta] = useState({ name: "", slug: "", mode: "upsert" });
  const infer = async (f: File, sheet?: string) => {
    setFile(f);
    const fd = new FormData(); fd.append("file", f); if (sheet) fd.append("sheet", sheet);
    try { const r = await api<S["InferOut"]>("POST", "/datasets/infer-schema", { form: fd }); setInf(r); setFields(r.columns); } catch (e) { toast((e as Error).message, "danger"); }
  };
  const upd = (i: number, p: Partial<S["InferredField"]>) => setFields(fields.map((f, j) => (j === i ? { ...f, ...p } : f)));
  const create = async () => {
    const tf = fields.find((f) => f.role === "time")?.name;
    try {
      const ds = await post<Ds>("/datasets", { slug: meta.slug, name: meta.name, load_mode: meta.mode, time_field: tf, parser_options: { sheet: inf?.sheet ?? undefined }, fields: fields.map(({ sample: _s, ...f }) => f) });
      toast("Dataset criado."); nav(`/datasets/${ds.id}`);
    } catch (e) { toast((e as Error).message, "danger"); }
  };
  void patch; void put;
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Novo dataset</h1>
      <Card title="1. Arquivo de amostra"><input type="file" accept=".csv,.txt,.xlsx" aria-label="Arquivo de amostra" onChange={(e) => e.target.files?.[0] && infer(e.target.files[0])} />
        {inf && inf.sheets.length > 1 && <div className="mt-3 w-64"><Field label="Aba">{(id) => <Select id={id} value={inf.sheet ?? ""} onChange={(e) => infer(file!, e.target.value)}>{inf.sheets.map((s) => <option key={s}>{s}</option>)}</Select>}</Field></div>}
      </Card>
      {inf && (
        <>
          <Card title="2. Identificação"><div className="grid gap-3 md:grid-cols-3">
            <Field label="Nome">{(id) => <Input id={id} value={meta.name} onChange={(e) => setMeta({ ...meta, name: e.target.value, slug: e.target.value.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "") })} />}</Field>
            <Field label="Identificador (slug)">{(id) => <Input id={id} value={meta.slug} onChange={(e) => setMeta({ ...meta, slug: e.target.value })} />}</Field>
            <Field label="Modo de carga" hint="upsert: atualiza pela chave · append: só adiciona · replace_snapshot: o arquivo é o estado completo">{(id) => <Select id={id} value={meta.mode} onChange={(e) => setMeta({ ...meta, mode: e.target.value })}><option>upsert</option><option>append</option><option>replace_snapshot</option></Select>}</Field>
          </div></Card>
          <Card title="3. Campos (marque a chave natural)" pad={false}>
            <Table head={["Coluna", "Campo", "Tipo", "Papel", "Chave", "Obrigatório", "Exemplos"]}>
              {fields.map((f, i) => (
                <tr key={f.source_column}>
                  <td className="px-3 py-1.5">{f.source_column}</td>
                  <td className="px-3 py-1.5"><Input aria-label={`Nome do campo ${f.source_column}`} value={f.name} onChange={(e) => upd(i, { name: e.target.value })} /></td>
                  <td className="px-3 py-1.5"><Select aria-label={`Tipo ${f.source_column}`} value={f.data_type} onChange={(e) => upd(i, { data_type: e.target.value })}>{["string", "integer", "decimal", "date", "datetime", "boolean"].map((t) => <option key={t}>{t}</option>)}</Select></td>
                  <td className="px-3 py-1.5"><Select aria-label={`Papel ${f.source_column}`} value={f.role} onChange={(e) => upd(i, { role: e.target.value })}>{["dimension", "measure", "time"].map((t) => <option key={t}>{t}</option>)}</Select></td>
                  <td className="px-3 py-1.5 text-center"><input type="checkbox" aria-label={`Chave ${f.source_column}`} checked={!!f.is_key} onChange={(e) => upd(i, { is_key: e.target.checked })} /></td>
                  <td className="px-3 py-1.5 text-center"><input type="checkbox" aria-label={`Obrigatório ${f.source_column}`} checked={!f.nullable} onChange={(e) => upd(i, { nullable: !e.target.checked })} /></td>
                  <td className="max-w-[14rem] truncate px-3 py-1.5 text-xs text-ink-mute">{f.sample?.join(" · ")}</td>
                </tr>
              ))}
            </Table>
          </Card>
          <Button disabled={!meta.name || !meta.slug || (meta.mode !== "append" && !fields.some((f) => f.is_key))} onClick={create}>Criar dataset</Button>
          {meta.mode !== "append" && !fields.some((f) => f.is_key) && <p className="text-sm text-warn">Marque ao menos um campo como chave (ex.: número do pedido).</p>}
        </>
      )}
    </div>
  );
}
