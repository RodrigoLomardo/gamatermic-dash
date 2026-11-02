import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { S, get, post } from "@/shared/api/http";
import { Button, Card, Input, Spinner, Table, useToasts } from "@/shared/ui/ui";
import { SharePanel } from "./SharePanel";

const slugify = (v: string) => v.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

/** Setores: agrupam dashboards; a concessão no setor libera todas as dashboards dele para usuários, grupos ou perfis. */
export function SectorsPage() {
  const qc = useQueryClient(); const toast = useToasts((s) => s.push);
  const sectors = useQuery({ queryKey: ["sectors"], queryFn: () => get<S["SectorOut"][]>("/sectors") });
  const dashboards = useQuery({ queryKey: ["dashboards"], queryFn: () => get<S["DashboardSummary"][]>("/dashboards") });
  const [name, setName] = useState(""); const [sel, setSel] = useState<S["SectorOut"] | null>(null);
  const counts = useMemo(() => {
    const m = new Map<string, number>();
    for (const d of dashboards.data ?? []) if (d.sector_id) m.set(d.sector_id, (m.get(d.sector_id) ?? 0) + 1);
    return m;
  }, [dashboards.data]);
  const create = async () => {
    try { await post("/sectors", { name: name.trim(), slug: slugify(name) }); setName(""); qc.invalidateQueries({ queryKey: ["sectors"] }); toast("Setor criado."); }
    catch (e) { toast((e as Error).message, "danger"); }
  };
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Setores</h1>
      <p className="text-sm text-ink-soft">
        Dê acesso a um setor para liberar todas as dashboards dele. Quem tem o perfil Visualizador ou Gestor só enxerga o que foi concedido
        no setor ou na própria dashboard. Para atribuir uma dashboard a um setor, use as Configurações do editor.
      </p>
      <Card title="Setores cadastrados" actions={
        <div className="flex gap-2">
          <Input aria-label="Nome do novo setor" className="w-48" placeholder="Novo setor" value={name} onChange={(e) => setName(e.target.value)} />
          <Button size="sm" disabled={slugify(name).length < 2} onClick={create}>Criar</Button>
        </div>}>
        {sectors.isLoading ? <Spinner /> : (
          <Table head={["Setor", "Dashboards", ""]} empty="Nenhum setor.">
            {sectors.data?.map((s) => (
              <tr key={s.id}>
                <td className="px-3 py-2 font-medium">{s.name} <span className="text-xs text-ink-mute">{s.slug}</span></td>
                <td className="px-3 py-2">{counts.get(s.id) ?? 0}</td>
                <td className="px-3 py-2 text-right"><Button size="sm" variant="secondary" onClick={() => setSel(s)}>Quem pode acessar</Button></td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
      {sel && <SharePanel resourceType="sector" resourceId={sel.id} onClose={() => setSel(null)} />}
    </div>
  );
}
