import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { S, put } from "@/shared/api/http";
import { Badge, Button, Modal, useToasts } from "@/shared/ui/ui";

export const dashboardLink = (id: string) => `${window.location.origin}/dashboards/${id}`;

export async function copyText(text: string): Promise<boolean> {
  try { await navigator.clipboard.writeText(text); return true; }
  catch {
    const t = document.createElement("textarea"); t.value = text; document.body.appendChild(t); t.select();
    const ok = document.execCommand("copy"); t.remove(); return ok;
  }
}

export const StatusBadge = ({ status }: { status: string }) =>
  status === "published" ? <Badge tone="ok">No ar</Badge> : <Badge tone="warn">Fora do ar</Badge>;

/** Lanca/retira o painel (so quem edita) e copia o link interno (exige login e permissao). */
export function PublishControl({ id, name, status, canEdit, compact = false }: { id: string; name: string; status: string; canEdit: boolean; compact?: boolean }) {
  const qc = useQueryClient(); const toast = useToasts((s) => s.push);
  const [confirm, setConfirm] = useState(false); const [busy, setBusy] = useState(false);
  const online = status === "published";
  const apply = async (next: boolean) => {
    setBusy(true);
    try {
      await put<S["DashboardOut"]>(`/dashboards/${id}/publication`, { online: next });
      toast(next ? `"${name}" está no ar.` : `"${name}" saiu do ar.`);
      qc.invalidateQueries({ queryKey: ["dashboards"] }); qc.invalidateQueries({ queryKey: ["dashboard", id] }); qc.invalidateQueries({ queryKey: ["playlists"] });
      setConfirm(false);
    } catch (e) { toast((e as Error).message, "danger"); } finally { setBusy(false); }
  };
  const copy = async () => toast((await copyText(dashboardLink(id))) ? "Link copiado." : "Não foi possível copiar; copie manualmente.", "ok");
  return (
    <div className="flex flex-wrap items-center gap-2">
      <StatusBadge status={status} />
      {canEdit && (online
        ? <Button size="sm" variant="secondary" onClick={() => setConfirm(true)}>Tirar do ar</Button>
        : <Button size="sm" disabled={busy} onClick={() => apply(true)}>Lançar (colocar no ar)</Button>)}
      {online && <Button size="sm" variant="secondary" onClick={copy} aria-label={`Copiar link de ${name}`}>{compact ? "Copiar link" : "Copiar link do painel"}</Button>}
      <Modal open={confirm} title="Tirar o painel do ar?" onClose={() => setConfirm(false)}>
        <p className="mb-4 text-sm text-ink-soft">“{name}” some das listas dos gestores, o link deixa de funcionar para quem não edita e as TVs que o exibem passam a pular este painel. Quem edita continua vendo.</p>
        <div className="flex justify-end gap-2"><Button variant="ghost" onClick={() => setConfirm(false)}>Cancelar</Button><Button variant="danger" disabled={busy} onClick={() => apply(false)}>Tirar do ar</Button></div>
      </Modal>
    </div>
  );
}
