import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { S, api, get } from "@/shared/api/http";
import { fmtDateTime } from "@/shared/lib/format";
import { Badge, Button, Card, Field, Input, Spinner, Table } from "@/shared/ui/ui";

export function AuditPage() {
  const [f, setF] = useState({ action: "", actor: "" });
  const [applied, setApplied] = useState(f);
  const q = useQuery({ queryKey: ["audit", applied], queryFn: () => get<(S["AuditOut"])[]>("/audit-logs", { query: { action: applied.action || undefined, actor: applied.actor || undefined, limit: 200 } }) });
  const download = async () => {
    const text = await api<string>("GET", "/audit-logs/export", { text: true, query: { action: applied.action || undefined, actor: applied.actor || undefined } });
    const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([text], { type: "text/csv" })); a.download = "auditoria.csv"; a.click();
  };
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Auditoria</h1>
      <Card>
        <form className="flex flex-wrap items-end gap-3" onSubmit={(e) => { e.preventDefault(); setApplied(f); }}>
          <div className="w-60"><Field label="Ação" hint="Use * como curinga: auth.*">{(id) => <Input id={id} value={f.action} onChange={(e) => setF({ ...f, action: e.target.value })} placeholder="auth.login.*" />}</Field></div>
          <div className="w-60"><Field label="Ator">{(id) => <Input id={id} value={f.actor} onChange={(e) => setF({ ...f, actor: e.target.value })} placeholder="e-mail" />}</Field></div>
          <Button type="submit">Filtrar</Button><Button type="button" variant="secondary" onClick={download}>Exportar CSV</Button>
        </form>
      </Card>
      {q.isLoading ? <Spinner /> : (
        <Card pad={false}><Table head={["Quando", "Ator", "Ação", "Recurso", "Resultado", "IP", "Request"]}>
          {q.data?.map((l) => (
            <tr key={l.id}><td className="whitespace-nowrap px-3 py-1.5">{fmtDateTime(l.occurred_at)}</td><td className="px-3 py-1.5">{l.actor_label ?? l.actor_type}</td>
              <td className="px-3 py-1.5 font-mono text-xs">{l.action}</td><td className="px-3 py-1.5 text-xs">{l.resource_type} {l.resource_id?.slice(0, 8)}</td>
              <td className="px-3 py-1.5"><Badge tone={l.outcome === "success" ? "ok" : "danger"}>{l.outcome}</Badge></td><td className="px-3 py-1.5">{l.ip}</td><td className="px-3 py-1.5 font-mono text-xs">{l.request_id?.slice(0, 8)}</td></tr>))}
        </Table></Card>)}
    </div>
  );
}
