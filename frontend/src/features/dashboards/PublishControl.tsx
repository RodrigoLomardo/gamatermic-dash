import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { S, put } from "@/shared/api/http";
import { Badge, Button, Modal, useToasts } from "@/shared/ui/ui";

export const dashboardLink = (id: string) => `${window.location.origin}/dashboards/${id}`;
/** Link de visualizacao: abre direto na tela de TV (so o painel), apos o login. */
export const viewLink = (id: string) => `${window.location.origin}/tv/painel/${id}`;

export async function copyText(text: string): Promise<boolean> {
  try { await navigator.clipboard.writeText(text); return true; }
  catch {
    const t = document.createElement("textarea"); t.value = text; document.body.appendChild(t); t.select();
    const ok = document.execCommand("copy"); t.remove(); return ok;
  }
}

export const StatusBadge = ({ status }: { status: string }) =>
  status === "published" ? <Badge tone="ok">No ar</Badge> : <Badge tone="warn">Fora do ar</Badge>;

/** Acoes de lancar/retirar do ar e de copiar links; usadas pelo controle completo e pelo menu do card. */
export function usePublishActions(id: string, name: string) {
  const qc = useQueryClient(); const toast = useToasts((s) => s.push);
  const [busy, setBusy] = useState(false);
  const setOnline = async (next: boolean): Promise<boolean> => {
    setBusy(true);
    try {
      await put<S["DashboardOut"]>(`/dashboards/${id}/publication`, { online: next });
      toast(next ? `"${name}" está no ar.` : `"${name}" saiu do ar.`);
      qc.invalidateQueries({ queryKey: ["dashboards"] }); qc.invalidateQueries({ queryKey: ["dashboard", id] }); qc.invalidateQueries({ queryKey: ["playlists"] });
      return true;
    } catch (e) { toast((e as Error).message, "danger"); return false; } finally { setBusy(false); }
  };
  const copy = async (url: string, what: string) => toast((await copyText(url)) ? `${what} copiado.` : "Não foi possível copiar; copie manualmente.", "ok");
  return { busy, setOnline, copy };
}

/** Lanca/retira o painel (so quem edita) e copia o link interno (exige login e permissao). */
export function PublishControl({ id, name, status, canEdit, compact = false }: { id: string; name: string; status: string; canEdit: boolean; compact?: boolean }) {
  const { busy, setOnline, copy } = usePublishActions(id, name);
  const [confirm, setConfirm] = useState(false);
  const online = status === "published";
  const apply = async (next: boolean) => { if (await setOnline(next)) setConfirm(false); };
  return (
    <div className="flex flex-wrap items-center gap-2">
      <StatusBadge status={status} />
      {canEdit && (online
        ? <Button size="sm" variant="secondary" onClick={() => setConfirm(true)}>Tirar do ar</Button>
        : <Button size="sm" disabled={busy} onClick={() => apply(true)}>Lançar (colocar no ar)</Button>)}
      {online && <Button size="sm" variant="secondary" onClick={() => copy(dashboardLink(id), "Link do painel")} aria-label={`Copiar link de ${name}`}>{compact ? "Link do painel" : "Copiar link do painel"}</Button>}
      {online && <Button size="sm" variant="secondary" onClick={() => copy(viewLink(id), "Link de visualização")} aria-label={`Copiar link de visualização de ${name}`}>{compact ? "Link de visualização" : "Copiar link de visualização (TV)"}</Button>}
      <Modal open={confirm} title="Tirar o painel do ar?" onClose={() => setConfirm(false)}>
        <p className="mb-4 text-sm text-ink-soft">“{name}” some das listas dos gestores, o link deixa de funcionar para quem não edita e as TVs que o exibem passam a pular este painel. Quem edita continua vendo.</p>
        <div className="flex justify-end gap-2"><Button variant="ghost" onClick={() => setConfirm(false)}>Cancelar</Button><Button variant="danger" disabled={busy} onClick={() => apply(false)}>Tirar do ar</Button></div>
      </Modal>
    </div>
  );
}
