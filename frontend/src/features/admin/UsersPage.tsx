import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { S, get, patch, post, put } from "@/shared/api/http";
import { fmtDateTime } from "@/shared/lib/format";
import { Badge, Button, Card, Field, Input, Modal, Spinner, Table, useToasts } from "@/shared/ui/ui";

type U = S["UserOut"]; type Role = S["RoleOut"]; type Grp = S["GroupOut"];

export function UsersPage() {
  const qc = useQueryClient(); const toast = useToasts((s) => s.push);
  const users = useQuery({ queryKey: ["users"], queryFn: () => get<U[]>("/users") });
  const roles = useQuery({ queryKey: ["roles"], queryFn: () => get<Role[]>("/roles") });
  const groups = useQuery({ queryKey: ["groups"], queryFn: () => get<Grp[]>("/groups") });
  const [edit, setEdit] = useState<U | null>(null); const [creating, setCreating] = useState(false);
  const [secret, setSecret] = useState<{ email: string; pw: string } | null>(null);
  const [form, setForm] = useState({ email: "", full_name: "" });
  const [eff, setEff] = useState<any>(null);
  const refresh = () => qc.invalidateQueries({ queryKey: ["users"] });
  const run = async (fn: () => Promise<unknown>, ok: string) => { try { await fn(); toast(ok); refresh(); } catch (e) { toast((e as Error).message, "danger"); } };
  const create = async () => {
    try { const u = await post<U>("/users", { ...form, role_ids: [], group_ids: [] }); setCreating(false); setSecret({ email: u.email, pw: u.temp_password! }); setForm({ email: "", full_name: "" }); refresh(); }
    catch (e) { toast((e as Error).message, "danger"); }
  };
  const toggle = (list: string[], id: string) => (list.includes(id) ? list.filter((x) => x !== id) : [...list, id]);
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between"><h1 className="text-2xl font-bold">Usuários</h1><Button onClick={() => setCreating(true)}>Novo usuário</Button></div>
      {users.isLoading ? <Spinner /> : (
        <Card pad={false}><Table head={["Nome", "E-mail", "Status", "Último acesso", ""]}>
          {users.data?.map((u) => (
            <tr key={u.id}>
              <td className="px-3 py-2 font-medium">{u.full_name}</td><td className="px-3 py-2">{u.email}</td>
              <td className="px-3 py-2">{u.status === "active" ? (u.locked_until && new Date(u.locked_until) > new Date() ? <Badge tone="danger">Bloqueado</Badge> : <Badge tone="ok">Ativo</Badge>) : <Badge>Inativo</Badge>}{u.must_change_password && <> <Badge tone="warn">Senha provisória</Badge></>}</td>
              <td className="px-3 py-2">{fmtDateTime(u.last_login_at)}</td>
              <td className="px-3 py-2 text-right"><Button size="sm" variant="secondary" onClick={() => setEdit(u)}>Gerenciar</Button></td>
            </tr>))}
        </Table></Card>
      )}
      <Modal open={creating} title="Novo usuário" onClose={() => setCreating(false)}>
        <div className="space-y-3">
          <Field label="Nome completo">{(id) => <Input id={id} value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />}</Field>
          <Field label="E-mail">{(id) => <Input id={id} type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />}</Field>
          <p className="text-xs text-ink-mute">Uma senha provisória será gerada; a pessoa deverá trocá-la no primeiro acesso.</p>
          <Button onClick={create} disabled={!form.email || form.full_name.length < 2}>Criar usuário</Button>
        </div>
      </Modal>
      <Modal open={!!secret} title="Senha provisória" onClose={() => setSecret(null)}>
        <p className="mb-2 text-sm">Entregue com segurança a <b>{secret?.email}</b>. Ela <b>não será exibida novamente</b>.</p>
        <code className="block select-all rounded-lg bg-brand-soft p-3 text-lg font-bold">{secret?.pw}</code>
      </Modal>
      <Modal open={!!edit} wide title={`Gerenciar — ${edit?.full_name}`} onClose={() => { setEdit(null); setEff(null); }}>
        {edit && (
          <div className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              <fieldset><legend className="mb-1 text-sm font-semibold">Perfis</legend>{roles.data?.map((r) => (
                <label key={r.id} className="flex items-center gap-2 py-0.5 text-sm"><input type="checkbox" checked={edit.role_ids.includes(r.id)} onChange={async (e) => { const ids = e.target.checked ? [...edit.role_ids, r.id] : edit.role_ids.filter((x) => x !== r.id); try { const u = await put<U>(`/users/${edit.id}/roles`, { ids }); setEdit(u); refresh(); setEff(null); } catch (x) { toast((x as Error).message, "danger"); } }} /> {r.name}</label>))}</fieldset>
              <fieldset><legend className="mb-1 text-sm font-semibold">Grupos</legend>{groups.data?.map((g) => (
                <label key={g.id} className="flex items-center gap-2 py-0.5 text-sm"><input type="checkbox" checked={edit.group_ids.includes(g.id)} onChange={async () => { try { const u = await put<U>(`/users/${edit.id}/groups`, { ids: toggle(edit.group_ids, g.id) }); setEdit(u); refresh(); setEff(null); } catch (x) { toast((x as Error).message, "danger"); } }} /> {g.name}</label>))}{groups.data?.length === 0 && <p className="text-sm text-ink-mute">Nenhum grupo.</p>}</fieldset>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button variant="secondary" onClick={async () => setEff(await get(`/users/${edit.id}/effective-permissions`))}>Ver permissões efetivas</Button>
              <Button variant="secondary" onClick={() => run(() => post(`/users/${edit.id}/unlock`), "Usuário desbloqueado.")}>Desbloquear</Button>
              <Button variant="secondary" onClick={async () => { try { const u = await post<U>(`/users/${edit.id}/reset-password`); setSecret({ email: u.email, pw: u.temp_password! }); setEdit(null); refresh(); } catch (e) { toast((e as Error).message, "danger"); } }}>Redefinir senha</Button>
              {edit.status === "active" ? <Button variant="danger" onClick={() => run(async () => { await patch(`/users/${edit.id}`, { status: "disabled" }); setEdit(null); }, "Usuário desativado.")}>Desativar</Button>
                : <Button variant="secondary" onClick={() => run(async () => { await patch(`/users/${edit.id}`, { status: "active" }); setEdit(null); }, "Usuário reativado.")}>Reativar</Button>}
              <Button variant="ghost" onClick={() => { if (confirm("Anonimizar (LGPD)? Esta ação é irreversível.")) run(async () => { await post(`/users/${edit.id}/anonymize`); setEdit(null); }, "Usuário anonimizado."); }}>Anonimizar (LGPD)</Button>
            </div>
            {eff && (
              <div className="rounded-lg bg-brand-soft p-3 text-sm">
                <p className="mb-2 text-ink-soft">{eff.explanation}</p>
                <ul className="grid gap-x-4 sm:grid-cols-2">{Object.entries(eff.permissions as Record<string, string>).map(([k, v]) => <li key={k}><code>{k}</code> → <b>{v === "all" ? "todos" : "concedidos"}</b></li>)}</ul>
                {eff.grants.length > 0 && <p className="mt-2">{eff.grants.length} concessão(ões) por recurso/setor.</p>}
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
}
