import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { S, get, put } from "@/shared/api/http";
import { Button, Modal, Select, Spinner, useToasts } from "@/shared/ui/ui";

type Grant = { subject_type: "user" | "group" | "role"; subject_id: string; access_level: "view" | "edit" | "manage" };

/** Concessoes por recurso (dashboard/dataset/setor): usuario, grupo ou role. */
export function SharePanel({ resourceType, resourceId, onClose }: { resourceType: "dashboard" | "dataset" | "sector"; resourceId: string; onClose: () => void }) {
  const toast = useToasts((s) => s.push); const qc = useQueryClient();
  const grants = useQuery({ queryKey: ["grants", resourceType, resourceId], queryFn: () => get<S["GrantOut"][]>(`/resources/${resourceType}/${resourceId}/grants`) });
  const users = useQuery({ queryKey: ["users"], queryFn: () => get<S["UserOut"][]>("/users") });
  const groups = useQuery({ queryKey: ["groups"], queryFn: () => get<S["GroupOut"][]>("/groups") });
  const roles = useQuery({ queryKey: ["roles"], queryFn: () => get<S["RoleOut"][]>("/roles") });
  const [rows, setRows] = useState<Grant[]>([]);
  const [add, setAdd] = useState("");
  useEffect(() => { if (grants.data) setRows(grants.data.map((g) => ({ subject_type: g.subject_type as Grant["subject_type"], subject_id: g.subject_id, access_level: g.access_level as Grant["access_level"] }))); }, [grants.data]);
  const name = (g: Grant) => (g.subject_type === "user" ? users.data?.find((u) => u.id === g.subject_id)?.full_name : g.subject_type === "group" ? groups.data?.find((x) => x.id === g.subject_id)?.name : roles.data?.find((r) => r.id === g.subject_id)?.name) ?? g.subject_id;
  const save = async () => {
    try { await put(`/resources/${resourceType}/${resourceId}/grants`, { grants: rows }); toast("Acesso atualizado. Vale em até 60 s."); qc.invalidateQueries(); onClose(); }
    catch (e) { toast((e as Error).message, "danger"); }
  };
  const options: [string, string][] = [
    ...(users.data ?? []).map((u) => [`user:${u.id}`, `Usuário · ${u.full_name}`] as [string, string]),
    ...(groups.data ?? []).map((g) => [`group:${g.id}`, `Grupo · ${g.name}`] as [string, string]),
    ...(roles.data ?? []).map((r) => [`role:${r.id}`, `Perfil · ${r.name}`] as [string, string]),
  ].filter(([k]) => !rows.some((r) => `${r.subject_type}:${r.subject_id}` === k));
  return (
    <Modal open title="Quem pode acessar" onClose={onClose}>
      {grants.isLoading ? <Spinner /> : (
        <div className="space-y-3">
          <p className="text-sm text-ink-soft">Concessões valem para quem tem a permissão com escopo “concedido” (ex.: perfil Gestor).</p>
          {rows.length === 0 && <p className="text-sm text-ink-mute">Nenhuma concessão: apenas quem tem escopo “todos” enxerga.</p>}
          {rows.map((g, i) => (
            <div key={`${g.subject_type}${g.subject_id}`} className="flex items-center gap-2">
              <span className="flex-1 truncate text-sm">{name(g)} <span className="text-xs text-ink-mute">({g.subject_type})</span></span>
              <Select aria-label={`Nível de ${name(g)}`} className="w-32" value={g.access_level} onChange={(e) => setRows(rows.map((r, j) => (j === i ? { ...r, access_level: e.target.value as Grant["access_level"] } : r)))}>
                <option value="view">Ver</option><option value="edit">Editar</option><option value="manage">Gerenciar</option></Select>
              <button aria-label={`Remover ${name(g)}`} className="text-danger" onClick={() => setRows(rows.filter((_, j) => j !== i))}>✕</button>
            </div>
          ))}
          <div className="flex gap-2">
            <Select aria-label="Adicionar" value={add} onChange={(e) => setAdd(e.target.value)}><option value="">Adicionar usuário, grupo ou perfil…</option>{options.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select>
            <Button variant="secondary" disabled={!add} onClick={() => { const [t, id] = add.split(":"); setRows([...rows, { subject_type: t as Grant["subject_type"], subject_id: id, access_level: "view" }]); setAdd(""); }}>Adicionar</Button>
          </div>
          <div className="flex justify-end gap-2"><Button variant="ghost" onClick={onClose}>Cancelar</Button><Button onClick={save}>Salvar</Button></div>
        </div>
      )}
    </Modal>
  );
}
