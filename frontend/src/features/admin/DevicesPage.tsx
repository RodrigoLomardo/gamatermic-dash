import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useAuth } from "@/app/auth";
import { S, del, get, patch, post, put } from "@/shared/api/http";
import { ago, fmtDateTime } from "@/shared/lib/format";
import { Badge, Button, Card, Empty, Field, Input, Modal, Select, Spinner, Table, useToasts } from "@/shared/ui/ui";

type Dev = S["DeviceOut"]; type PL = S["PlaylistOut"]; type Dash = S["DashboardSummary"];

export function DevicesPage() {
  const { can } = useAuth(); const qc = useQueryClient(); const toast = useToasts((s) => s.push);
  const [sp, setSp] = useSearchParams();
  const devices = useQuery({ queryKey: ["devices"], queryFn: () => get<Dev[]>("/devices"), enabled: can("device:manage"), refetchInterval: 10_000 });
  const playlists = useQuery({ queryKey: ["playlists"], queryFn: () => get<PL[]>("/playlists") });
  const dashboards = useQuery({ queryKey: ["dashboards"], queryFn: () => get<Dash[]>("/dashboards") });
  const [pair, setPair] = useState<{ code: string; info?: S["LookupOut"]; name: string; location: string; playlist: string } | null>(null);
  const [pl, setPl] = useState<PL | null>(null); const [items, setItems] = useState<S["PlaylistItemIn"][]>([]); const [newPl, setNewPl] = useState("");
  const guard = async (fn: () => Promise<unknown>, ok?: string) => { try { await fn(); if (ok) toast(ok); qc.invalidateQueries(); } catch (e) { toast((e as Error).message, "danger"); } };

  const lookup = async (code: string) => {
    try { const info = await get<S["LookupOut"]>("/device-pairing/lookup", { query: { user_code: code } }); setPair((p) => ({ name: "", location: "", playlist: playlists.data?.[0]?.id ?? "", ...p, code, info })); }
    catch (e) { toast((e as Error).message, "danger"); }
  };
  useEffect(() => { const c = sp.get("code"); if (c && can("device:manage")) { lookup(c); setSp({}, { replace: true }); } }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (pair && !pair.playlist && playlists.data?.length) setPair({ ...pair, playlist: playlists.data[0].id }); }, [pair, playlists.data]);
  const approve = () => guard(async () => { await post("/device-pairing/approve", { user_code: pair!.code, name: pair!.name, location: pair!.location || null, playlist_id: pair!.playlist || null }); setPair(null); }, "TV pareada! Ela começa a exibir em instantes.");
  const openPl = (p: PL) => { setPl(p); setItems(p.items.map((i) => ({ dashboard_id: i.dashboard_id, duration_seconds: i.duration_seconds, transition: i.transition }))); };
  const move = (i: number, d: number) => { const a = [...items]; [a[i], a[i + d]] = [a[i + d], a[i]]; setItems(a); };
  const dname = (id: string) => dashboards.data?.find((d) => d.id === id)?.name ?? id;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">TVs e playlists</h1>
      {can("device:manage") && (
        <Card title="Parear nova TV">
          <form className="flex flex-wrap items-end gap-3" onSubmit={(e) => { e.preventDefault(); const f = new FormData(e.currentTarget); lookup(String(f.get("code"))); }}>
            <div className="w-56"><Field label="Código exibido na TV" hint="Abra /tv no navegador da TV">{(id) => <Input id={id} name="code" placeholder="ABCD-2345" autoComplete="off" className="font-mono uppercase tracking-widest" required />}</Field></div>
            <Button type="submit">Localizar TV</Button>
          </form>
        </Card>
      )}
      {can("device:manage") && (
        <Card title="Dispositivos" pad={false}>
          {devices.isLoading ? <Spinner /> : devices.data?.length === 0 ? <div className="p-4"><Empty>Nenhuma TV pareada.</Empty></div> : (
            <Table head={["Nome", "Local", "Estado", "Último sinal", "Playlist", ""]}>
              {devices.data?.map((d) => (
                <tr key={d.id}>
                  <td className="px-3 py-2 font-medium">{d.name}</td><td className="px-3 py-2">{d.location ?? "—"}</td>
                  <td className="px-3 py-2">{d.status === "revoked" ? <Badge tone="danger">Revogada</Badge> : d.online ? <Badge tone="ok">Online</Badge> : <Badge tone="warn">Offline</Badge>}{d.stale_state === "offline" && d.online && <> <Badge tone="warn">sem rede</Badge></>}</td>
                  <td className="px-3 py-2" title={fmtDateTime(d.last_seen_at)}>{ago(d.last_seen_at)} <span className="text-xs text-ink-mute">{d.last_ip}</span></td>
                  <td className="px-3 py-2"><Select aria-label={`Playlist de ${d.name}`} disabled={d.status === "revoked"} className="w-44" value={d.playlist_id ?? ""} onChange={(e) => guard(() => put(`/devices/${d.id}/playlist`, { playlist_id: e.target.value || null }), "Playlist atribuída.")}><option value="">— nenhuma —</option>{playlists.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</Select></td>
                  <td className="px-3 py-2 text-right whitespace-nowrap">
                    {d.status === "active" && <Button size="sm" variant="ghost" onClick={() => { const n = prompt("Novo nome da TV", d.name); if (n) guard(() => patch(`/devices/${d.id}`, { name: n }), "Renomeada."); }}>Renomear</Button>}
                    {d.status === "active" && <Button size="sm" variant="danger" onClick={() => { if (confirm(`Revogar "${d.name}"? A TV volta à tela de pareamento.`)) guard(() => post(`/devices/${d.id}/revoke`), "TV revogada."); }}>Revogar</Button>}
                  </td>
                </tr>))}
            </Table>)}
        </Card>
      )}
      {can("playlist:manage") && (
        <Card title="Playlists" actions={<div className="flex gap-2"><Input aria-label="Nome da nova playlist" className="w-44" placeholder="Nova playlist" value={newPl} onChange={(e) => setNewPl(e.target.value)} /><Button size="sm" disabled={newPl.length < 2} onClick={() => guard(async () => { await post("/playlists", { name: newPl }); setNewPl(""); }, "Playlist criada.")}>Criar</Button></div>}>
          <ul className="divide-y divide-line">{playlists.data?.map((p) => (
            <li key={p.id} className="flex items-center justify-between py-2"><div><span className="font-medium">{p.name}</span><p className="text-xs text-ink-mute">{p.items.map((i) => `${i.dashboard_name} (${i.duration_seconds}s)`).join(" → ") || "vazia"} · {p.device_count} TV(s)</p></div>
              <div className="flex gap-2"><Button size="sm" variant="secondary" onClick={() => openPl(p)}>Editar</Button><Button size="sm" variant="ghost" onClick={() => { if (confirm("Excluir playlist?")) guard(() => del(`/playlists/${p.id}`), "Playlist removida."); }}>Excluir</Button></div></li>))}</ul>
        </Card>
      )}

      <Modal open={!!pair} title="Aprovar pareamento" onClose={() => setPair(null)}>
        {pair?.info && (<div className="space-y-3">
          <div className="rounded-lg bg-brand-soft p-3 text-sm"><p>Código <b className="font-mono">{pair.info.user_code}</b> · expira em {Math.max(0, Math.floor(pair.info.expires_in / 60))} min</p><p>IP da TV: <b>{pair.info.requested_ip}</b></p><p className="truncate">Navegador: {pair.info.user_agent}</p><p className="mt-1 text-xs text-warn">Confirme que este é o IP/navegador da TV que você está vendo.</p></div>
          <Field label="Nome da TV">{(id) => <Input id={id} value={pair.name} onChange={(e) => setPair({ ...pair, name: e.target.value })} placeholder="TV Comercial" />}</Field>
          <Field label="Local">{(id) => <Input id={id} value={pair.location} onChange={(e) => setPair({ ...pair, location: e.target.value })} placeholder="Sala de vendas" />}</Field>
          <Field label="Playlist">{(id) => <Select id={id} value={pair.playlist} onChange={(e) => setPair({ ...pair, playlist: e.target.value })}><option value="">— definir depois —</option>{playlists.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</Select>}</Field>
          <div className="flex justify-end gap-2"><Button variant="ghost" onClick={() => guard(async () => { await post("/device-pairing/deny", { user_code: pair.code }); setPair(null); }, "Recusado.")}>Recusar</Button><Button disabled={pair.name.length < 2} onClick={approve}>Aprovar</Button></div>
        </div>)}
      </Modal>

      <Modal open={!!pl} wide title={`Playlist — ${pl?.name}`} onClose={() => setPl(null)}>
        {pl && (<div className="space-y-3">
          {items.map((it, i) => (
            <div key={i} className="grid grid-cols-[auto_1fr_6rem_7rem_auto] items-center gap-2">
              <span className="flex flex-col"><button aria-label="Subir" disabled={i === 0} onClick={() => move(i, -1)}>▲</button><button aria-label="Descer" disabled={i === items.length - 1} onClick={() => move(i, 1)}>▼</button></span>
              <Select aria-label="Dashboard" value={it.dashboard_id} onChange={(e) => setItems(items.map((x, j) => (j === i ? { ...x, dashboard_id: e.target.value } : x)))}>{dashboards.data?.map((d) => <option key={d.id} value={d.id}>{d.name}{d.status !== "published" ? " (fora do ar — a TV pula)" : ""}</option>)}</Select>
              <Input aria-label="Duração em segundos" type="number" min={5} value={it.duration_seconds} onChange={(e) => setItems(items.map((x, j) => (j === i ? { ...x, duration_seconds: Number(e.target.value) } : x)))} />
              <Select aria-label="Transição" value={it.transition ?? "fade"} onChange={(e) => setItems(items.map((x, j) => (j === i ? { ...x, transition: e.target.value as "fade" } : x)))}><option value="fade">Fade</option><option value="slide">Deslizar</option><option value="none">Nenhuma</option></Select>
              <button aria-label={`Remover ${dname(it.dashboard_id)}`} className="text-danger" onClick={() => setItems(items.filter((_, j) => j !== i))}>✕</button>
            </div>))}
          <Button variant="secondary" size="sm" disabled={!dashboards.data?.length} onClick={() => setItems([...items, { dashboard_id: dashboards.data![0].id, duration_seconds: 30, transition: "fade" }])}>+ Dashboard</Button>
          <div className="flex justify-end"><Button onClick={() => guard(async () => { await put(`/playlists/${pl.id}/items`, items); setPl(null); }, "Playlist salva. As TVs atualizam sozinhas.")}>Salvar</Button></div>
        </div>)}
      </Modal>
    </div>
  );
}
