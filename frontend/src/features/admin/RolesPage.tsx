import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { S, del, get, post, put } from "@/shared/api/http";
import { Badge, Button, Card, Input, Modal, Select, Spinner, Table, useToasts } from "@/shared/ui/ui";

type Role = S["RoleOut"]; type Grp = S["GroupOut"]; type Perm = S["PermissionOut"]; type U = S["UserOut"];

export function RolesPage() {
  const qc = useQueryClient(); const toast = useToasts((s) => s.push);
  const roles = useQuery({ queryKey: ["roles"], queryFn: () => get<Role[]>("/roles") });
  const perms = useQuery({ queryKey: ["perms"], queryFn: () => get<Perm[]>("/permissions") });
  const groups = useQuery({ queryKey: ["groups"], queryFn: () => get<Grp[]>("/groups") });
  const users = useQuery({ queryKey: ["users"], queryFn: () => get<U[]>("/users") });
  const [sel, setSel] = useState<Role | null>(null); const [name, setName] = useState(""); const [gname, setG] = useState("");
  const [grp, setGrp] = useState<Grp | null>(null);
  const [map, setMap] = useState<Record<string, "all" | "granted">>({});
  const refresh = () => { qc.invalidateQueries({ queryKey: ["roles"] }); qc.invalidateQueries({ queryKey: ["groups"] }); };
  const guard = async (fn: () => Promise<unknown>, ok: string) => { try { await fn(); toast(ok); refresh(); } catch (e) { toast((e as Error).message, "danger"); } };
  const open = (r: Role) => { setSel(r); setMap(Object.fromEntries(r.permissions.map((p) => [p.code, p.scope]))); };
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Perfis, permissões e grupos</h1>
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Perfis (roles)" actions={<div className="flex gap-2"><Input aria-label="Nome do novo perfil" className="w-40" placeholder="Novo perfil" value={name} onChange={(e) => setName(e.target.value)} /><Button size="sm" disabled={name.length < 2} onClick={() => guard(async () => { await post("/roles", { name, permissions: [] }); setName(""); }, "Perfil criado.")}>Criar</Button></div>}>
          {roles.isLoading ? <Spinner /> : <ul className="divide-y divide-line">{roles.data?.map((r) => (
            <li key={r.id} className="flex items-center justify-between py-2"><div><span className="font-medium">{r.name}</span> {r.is_system && <Badge>sistema</Badge>}<p className="text-xs text-ink-mute">{r.permissions.length} permissões</p></div>
              <Button size="sm" variant="secondary" onClick={() => open(r)}>{r.is_system ? "Ver" : "Editar"}</Button></li>))}</ul>}
        </Card>
        <Card title="Grupos" actions={<div className="flex gap-2"><Input aria-label="Nome do novo grupo" className="w-40" placeholder="Novo grupo" value={gname} onChange={(e) => setG(e.target.value)} /><Button size="sm" disabled={gname.length < 2} onClick={() => guard(async () => { await post("/groups", { name: gname }); setG(""); }, "Grupo criado.")}>Criar</Button></div>}>
          <ul className="divide-y divide-line">{groups.data?.map((g) => (
            <li key={g.id} className="flex items-center justify-between py-2"><div><span className="font-medium">{g.name}</span><p className="text-xs text-ink-mute">{g.member_ids.length} membros · {g.role_ids.length} perfis</p></div>
              <Button size="sm" variant="secondary" onClick={() => setGrp(g)}>Gerenciar</Button></li>))}
            {groups.data?.length === 0 && <li className="py-2 text-sm text-ink-mute">Nenhum grupo.</li>}</ul>
        </Card>
      </div>
      <Modal open={!!sel} wide title={`Perfil — ${sel?.name}`} onClose={() => setSel(null)}>
        {sel && (<div className="space-y-3">
          <p className="text-sm text-ink-soft">Escopo <b>todos</b> vale para qualquer recurso; <b>concedidos</b> exige concessão no recurso ou setor.</p>
          <Table head={["Permissão", "Descrição", "Escopo"]}>{perms.data?.map((p) => (
            <tr key={p.code}><td className="px-3 py-1.5 font-mono text-xs">{p.code}</td><td className="px-3 py-1.5">{p.description}</td>
              <td className="px-3 py-1.5"><Select aria-label={`Escopo de ${p.code}`} disabled={sel.is_system} className="w-36" value={map[p.code] ?? ""} onChange={(e) => { const m = { ...map }; if (!e.target.value) delete m[p.code]; else m[p.code] = e.target.value as "all" | "granted"; setMap(m); }}>
                <option value="">— não —</option><option value="all">todos</option><option value="granted">concedidos</option></Select></td></tr>))}</Table>
          {!sel.is_system && <div className="flex justify-between"><Button variant="danger" onClick={() => guard(async () => { await del(`/roles/${sel.id}`); setSel(null); }, "Perfil removido.")}>Excluir</Button>
            <Button onClick={() => guard(async () => { await put(`/roles/${sel.id}/permissions`, Object.entries(map).map(([code, scope]) => ({ code, scope }))); setSel(null); }, "Permissões salvas (valem em até 60 s).")}>Salvar</Button></div>}
        </div>)}
      </Modal>
      <Modal open={!!grp} wide title={`Grupo — ${grp?.name}`} onClose={() => setGrp(null)}>
        {grp && (<div className="grid gap-4 md:grid-cols-2">
          <fieldset><legend className="mb-1 text-sm font-semibold">Membros</legend>{users.data?.map((u) => (
            <label key={u.id} className="flex items-center gap-2 py-0.5 text-sm"><input type="checkbox" checked={grp.member_ids.includes(u.id)} onChange={(e) => guard(async () => { const ids = e.target.checked ? [...grp.member_ids, u.id] : grp.member_ids.filter((x) => x !== u.id); setGrp(await put<Grp>(`/groups/${grp.id}/members`, { ids })); }, "Membros atualizados.")} /> {u.full_name}</label>))}</fieldset>
          <fieldset><legend className="mb-1 text-sm font-semibold">Perfis do grupo</legend>{roles.data?.map((r) => (
            <label key={r.id} className="flex items-center gap-2 py-0.5 text-sm"><input type="checkbox" checked={grp.role_ids.includes(r.id)} onChange={(e) => guard(async () => { const ids = e.target.checked ? [...grp.role_ids, r.id] : grp.role_ids.filter((x) => x !== r.id); setGrp(await put<Grp>(`/groups/${grp.id}/roles`, { ids })); }, "Perfis atualizados.")} /> {r.name}</label>))}</fieldset>
          <div className="md:col-span-2"><Button variant="danger" onClick={() => guard(async () => { await del(`/groups/${grp.id}`); setGrp(null); }, "Grupo removido.")}>Excluir grupo</Button></div>
        </div>)}
      </Modal>
    </div>
  );
}
