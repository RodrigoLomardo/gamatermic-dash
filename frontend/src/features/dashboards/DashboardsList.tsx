import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/app/auth";
import { IconArrowUpRight, IconPlus, IconSearch, IconSparkles } from "@/app/icons";
import { S, del, get, post } from "@/shared/api/http";
import { fmtDateTime } from "@/shared/lib/format";
import { Button, Empty, ErrorBox, Modal, Spinner, cx, useToasts } from "@/shared/ui/ui";
import { CardMenu } from "./CardMenu";
import { DashPreview } from "./DashPreview";
import { dashboardLink, usePublishActions, viewLink } from "./PublishControl";

type Summary = S["DashboardSummary"];
const FILTERS = [["all", "Todos"], ["online", "No ar"], ["offline", "Fora do ar"]] as const;
const norm = (s: string) => s.toLocaleLowerCase("pt-BR").normalize("NFD").replace(/\p{M}/gu, "");

function DashCard({ d, i, sector }: { d: Summary; i: number; sector?: string }) {
  const { can } = useAuth(); const nav = useNavigate(); const qc = useQueryClient(); const toast = useToasts((s) => s.push);
  const { busy, setOnline, copy } = usePublishActions(d.id, d.name);
  const [menuOpen, setMenuOpen] = useState(false);
  const [askDelete, setAskDelete] = useState(false); const [deleting, setDeleting] = useState(false);
  const online = d.status === "published";
  const dup = async () => { try { const n = await post<S["DashboardOut"]>(`/dashboards/${d.id}/duplicate`); toast("Dashboard duplicada."); nav(`/dashboards/${n.id}/editar`); } catch (e) { toast((e as Error).message, "danger"); } };
  const remove = async () => {
    setDeleting(true);
    try { await del(`/dashboards/${d.id}`); toast(`"${d.name}" excluída.`); setAskDelete(false); await qc.invalidateQueries({ queryKey: ["dashboards"] }); await qc.invalidateQueries({ queryKey: ["playlists"] }); }
    catch (e) { toast((e as Error).message, "danger"); } finally { setDeleting(false); }
  };
  const toggle = () => {
    if (online && !confirm(`Tirar "${d.name}" do ar? Ele some das listas dos gestores e as TVs passam a pular este painel.`)) return;
    void setOnline(!online);
  };
  return (
    <article className={cx("library-card", menuOpen && "is-menu-open")} style={{ "--i": i } as React.CSSProperties}>
      <Link to={`/dashboards/${d.id}`} tabIndex={-1} aria-hidden="true"><DashPreview id={d.id} empty={d.widget_count === 0} /></Link>
      <div className="flex flex-1 flex-col p-6">
        <div className="flex items-center justify-between gap-3 text-xs font-semibold uppercase tracking-[0.16em]">
          <span className="truncate text-ink-mute">{sector ?? "Sem setor"}</span>
          <span className={cx("inline-flex shrink-0 items-center gap-2 normal-case tracking-normal", online ? "text-ok" : "text-warn")}>
            <span className="h-2 w-2 rounded-full bg-current" aria-hidden="true" />{online ? "No ar" : "Fora do ar"}
          </span>
        </div>
        <Link to={`/dashboards/${d.id}`} className="group mt-4 block">
          <h2 className="text-xl font-bold tracking-tight text-ink group-hover:text-accent-dark">{d.name}</h2>
          <p className="mt-2 line-clamp-2 min-h-[2.75rem] text-[15px] leading-relaxed text-ink-soft">{d.description || "Organize seus indicadores e acompanhe os resultados."}</p>
        </Link>
        <p className="mt-6 flex flex-wrap gap-x-5 gap-y-1 text-sm text-ink-mute"><span>{d.widget_count} widgets</span><span>{fmtDateTime(d.updated_at)}</span></p>
        <div className="mt-5 flex items-center justify-between border-t border-line pt-5">
          <Link to={`/dashboards/${d.id}`} className="inline-flex items-center gap-2 text-[15px] font-bold text-ink transition hover:text-accent-dark hover:gap-3">Abrir dashboard <IconArrowUpRight /></Link>
          <CardMenu id={d.id} name={d.name} online={online} busy={busy} canEdit={can("dashboard:edit")} canCreate={can("dashboard:create")} canDelete={can("dashboard:delete")}
            onDuplicate={dup} onToggleOnline={toggle} onCopyLink={() => copy(dashboardLink(d.id), "Link do painel")} onCopyViewLink={() => copy(viewLink(d.id), "Link de visualização")}
            onDelete={() => setAskDelete(true)} onOpenChange={setMenuOpen} />
        </div>
      </div>
      <Modal open={askDelete} title="Excluir dashboard?" onClose={() => !deleting && setAskDelete(false)}>
        <p className="text-sm text-ink-soft">Você vai excluir <strong className="text-ink">“{d.name}”</strong>.</p>
        <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-ink-soft">
          <li>Os {d.widget_count} widgets são apagados.</li>
          <li>O painel sai das playlists das TVs.</li>
          <li>Links compartilhados deixam de funcionar.</li>
        </ul>
        <p className="mt-3 text-sm font-semibold text-danger">Esta ação é irreversível.</p>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" autoFocus disabled={deleting} onClick={() => setAskDelete(false)}>Cancelar</Button>
          <Button variant="danger" disabled={deleting} onClick={remove}>{deleting ? "Excluindo…" : "Excluir definitivamente"}</Button>
        </div>
      </Modal>
    </article>
  );
}

export function DashboardsListPage() {
  const { can } = useAuth();
  const q = useQuery({ queryKey: ["dashboards"], queryFn: () => get<Summary[]>("/dashboards") });
  const sectors = useQuery({ queryKey: ["sectors"], queryFn: () => get<S["SectorOut"][]>("/sectors"), staleTime: 5 * 60_000 });
  const [search, setSearch] = useState(""); const [filter, setFilter] = useState<(typeof FILTERS)[number][0]>("all");
  const dashboards = useMemo(() => q.data ?? [], [q.data]);
  const sectorName = useMemo(() => new Map((sectors.data ?? []).map((s) => [s.id, s.name])), [sectors.data]);
  const counts = { all: dashboards.length, online: dashboards.filter((d) => d.status === "published").length, offline: dashboards.filter((d) => d.status !== "published").length };
  const visible = useMemo(() => {
    const term = norm(search.trim());
    return dashboards.filter((d) => (filter === "all" || (d.status === "published" ? "online" : "offline") === filter) && norm(`${d.name} ${d.description ?? ""}`).includes(term));
  }, [dashboards, filter, search]);
  return (
    <div className="mx-auto max-w-[1600px] space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-4xl font-bold tracking-tight">Dashboards</h1>
          <p className="mt-3 text-ink-soft">Uma visão clara de cada resultado.</p>
        </div>
        {can("dashboard:create") && (
          <div className="flex flex-wrap gap-3">
            {can("dataset:query") && <Link to="/dashboards/nova/ia"><Button variant="secondary" size="lg"><IconSparkles width={18} height={18} /> Criar com IA</Button></Link>}
            <Link to="/dashboards/nova"><Button size="lg"><IconPlus width={18} height={18} /> Novo dashboard</Button></Link>
          </div>
        )}
      </div>
      {q.isLoading && <Spinner />}
      {q.error && <ErrorBox error={q.error} onRetry={() => q.refetch()} />}
      {q.data?.length === 0 && <Empty>Nenhuma dashboard disponível para o seu perfil. Peça acesso a um administrador.</Empty>}
      {dashboards.length > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-line pb-6">
          <div className="flex flex-wrap gap-1" role="group" aria-label="Filtrar dashboards">
            {FILTERS.map(([v, label]) => (
              <button key={v} type="button" aria-pressed={filter === v} className={cx("library-tab", filter === v && "is-active")} onClick={() => setFilter(v)}>{label} <span>{counts[v]}</span></button>
            ))}
          </div>
          <label className="library-search"><IconSearch width={18} height={18} /><span className="sr-only">Buscar dashboards</span>
            <input type="search" placeholder="Buscar dashboard…" value={search} onChange={(e) => setSearch(e.target.value)} /></label>
        </div>
      )}
      {dashboards.length > 0 && visible.length === 0 && <Empty>Nenhum dashboard encontrado. Ajuste a busca ou o filtro.</Empty>}
      <div className="grid gap-6 md:grid-cols-2 2xl:grid-cols-3">
        {visible.map((d, i) => <DashCard key={d.id} d={d} i={i} sector={d.sector_id ? sectorName.get(d.sector_id) : undefined} />)}
      </div>
    </div>
  );
}
