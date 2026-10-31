import { fetchEventSource } from "@microsoft/fetch-event-source";
import QRCode from "qrcode";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { useTheme } from "@/app/theme";
import { ApiError, S, api, getFreshAccessToken, setAccessToken } from "@/shared/api/http";
import { fmtTime } from "@/shared/lib/format";
import { Logo, cx } from "@/shared/ui/ui";
import { WidgetCard } from "../widgets/WidgetCard";
import type { DashboardData } from "../widgets/types";
import { Source, backoff, burnInOffset, connectionState, nextPlayable, staleSources } from "./machine";

type Cfg = { device: { id: string; name: string | null; location: string | null } | null; mode: string; playlist: { dashboard_id: string; name: string; duration_seconds: number; transition: string }[]; playlist_version: number; heartbeat_seconds: number; poll_seconds: number; frontend_version: string };
type Data = DashboardData & { sources?: Source[] };
type Dash = S["DashboardOut"];

const APP_VERSION = (import.meta.env.VITE_APP_VERSION as string | undefined) ?? "dev";
const CACHE_KEY = "gama-tv-cache-v1";

function loadCache(): Record<string, { dash?: Dash; data?: Data; at?: number }> {
  try { return JSON.parse(localStorage.getItem(CACHE_KEY) ?? "{}"); } catch { return {}; }
}
function saveCache(c: Record<string, unknown>) { try { localStorage.setItem(CACHE_KEY, JSON.stringify(c)); } catch { /* quota/privado */ } }

/** /tv: modo dispositivo (pareamento). /tv/preview/:id: usuario logado testando como TV. */
export function TvPage({ preview = false }: { preview?: boolean }) {
  useTheme("tv");
  const { id: previewId } = useParams();
  const [stage, setStage] = useState<"boot" | "pairing" | "running">("boot");
  const tokenRef = useRef<string | null>(null);
  const expiresAt = useRef(0);

  const getToken = useCallback(async (): Promise<string> => {
    if (preview) return "";
    if (tokenRef.current && Date.now() < expiresAt.current - 60_000) return tokenRef.current;
    const t = await api<S["DeviceTokenOut"]>("POST", "/device/token", { noAuth: true });
    tokenRef.current = t.access_token;
    expiresAt.current = Date.now() + t.expires_in * 1000;
    return t.access_token;
  }, [preview]);

  useEffect(() => {
    if (preview) { setStage("running"); return; }
    if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
    getToken().then(() => setStage("running")).catch((e) => {
      if (e instanceof ApiError && e.status === 401) setStage("pairing");
      else setStage("running"); // rede fora no boot: tenta rodar com o cache local
    });
  }, [getToken, preview]);

  const unpair = useCallback(() => { tokenRef.current = null; expiresAt.current = 0; setAccessToken(null); setStage("pairing"); }, []);

  if (stage === "boot") return <Screen><p className="text-2xl text-ink-soft">Iniciando…</p></Screen>;
  if (stage === "pairing") return <Pairing onPaired={() => setStage("running")} />;
  return <Player getToken={getToken} onRevoked={unpair} preview={preview} previewId={previewId} />;
}

function Screen({ children }: { children: React.ReactNode }) {
  return <div className="flex h-screen w-screen flex-col items-center justify-center gap-8 bg-surface p-8 text-ink">{children}</div>;
}

function Pairing({ onPaired }: { onPaired: () => void }) {
  const [req, setReq] = useState<S["PairStartOut"] | null>(null);
  const [qr, setQr] = useState("");
  const [left, setLeft] = useState(0);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    let stop = false; let timer: number;
    const start = async () => {
      try {
        const r = await api<S["PairStartOut"]>("POST", "/device-pairing/start", { noAuth: true });
        if (stop) return;
        setReq(r); setMsg(null); setLeft(r.expires_in);
        setQr(await QRCode.toDataURL(`${location.origin}${r.verification_path}`, { margin: 1, width: 280, color: { dark: "#001F3B", light: "#ffffff" } }));
        let interval = r.interval * 1000;
        const poll = async () => {
          if (stop) return;
          try {
            const p = await api<S["PollOut"]>("POST", "/device-pairing/poll", { body: { device_code: r.device_code }, noAuth: true });
            if (p.status === "approved") return onPaired();
            if (p.status === "expired" || p.status === "denied") { setMsg(p.status === "denied" ? "Pareamento recusado." : "Código expirado."); return void (timer = window.setTimeout(start, 1500)); }
            if (p.status === "slow_down" && p.interval) interval = p.interval * 1000;
          } catch { /* rede: tenta no proximo ciclo */ }
          timer = window.setTimeout(poll, interval);
        };
        timer = window.setTimeout(poll, interval);
      } catch { setMsg("Sem conexão com o servidor. Tentando de novo…"); timer = window.setTimeout(start, 5000); }
    };
    start();
    return () => { stop = true; clearTimeout(timer); };
  }, [onPaired]);

  useEffect(() => { const t = setInterval(() => setLeft((s) => Math.max(0, s - 1)), 1000); return () => clearInterval(t); }, [req]);

  return (
    <Screen>
      <Logo light />
      <h1 className="text-4xl font-bold">Parear esta TV</h1>
      <div className="flex flex-wrap items-center justify-center gap-12">
        <div className="text-center">
          <p className="mb-3 text-xl text-ink-soft">Informe este código no painel de administração</p>
          <p aria-label="Código de pareamento" className="tabular rounded-2xl bg-panel px-10 py-6 text-[clamp(3rem,8vw,6rem)] font-extrabold tracking-[.15em] text-accent">{req?.user_code ?? "••••-••••"}</p>
          <p className="mt-3 text-lg text-ink-mute">Expira em {Math.floor(left / 60)}:{String(left % 60).padStart(2, "0")}</p>
        </div>
        {qr && <div className="text-center"><img src={qr} alt="QR code para aprovar o pareamento" className="rounded-xl bg-white p-2" width={240} height={240} /><p className="mt-2 text-ink-mute">ou escaneie para aprovar</p></div>}
      </div>
      {msg && <p role="status" className="text-xl text-warn">{msg}</p>}
    </Screen>
  );
}

function Player({ getToken, onRevoked, preview, previewId }: { getToken: () => Promise<string>; onRevoked: () => void; preview: boolean; previewId?: string }) {
  const [cfg, setCfg] = useState<Cfg | null>(null);
  const [idx, setIdx] = useState(0);
  const [dash, setDash] = useState<Record<string, Dash>>(() => Object.fromEntries(Object.entries(loadCache()).filter(([, v]) => v.dash).map(([k, v]) => [k, v.dash!])));
  const [data, setData] = useState<Record<string, Data>>(() => Object.fromEntries(Object.entries(loadCache()).filter(([, v]) => v.data).map(([k, v]) => [k, v.data!])));
  const [lastOk, setLastOk] = useState<number | null>(null);
  const [now, setNow] = useState(Date.now());
  const etags = useRef<Record<string, string>>({});
  const blocked = useRef(new Set<string>());
  const sseUp = useRef(false);

  const authed = useCallback(async <T,>(path: string, headers?: Record<string, string>): Promise<T> => {
    const tok = await getToken();
    try { return await api<T>("GET", path, { token: preview ? undefined : tok, headers }); }
    catch (e) { if (e instanceof ApiError && e.status === 401 && !preview) { if (e.code === "device_revoked") onRevoked(); } throw e; }
  }, [getToken, onRevoked, preview]);

  const persist = useCallback((id: string, patch: { dash?: Dash; data?: Data }) => {
    const c = loadCache(); c[id] = { ...c[id], ...patch, at: Date.now() }; saveCache(c);
  }, []);

  const loadConfig = useCallback(async () => {
    try {
      const c = await authed<Cfg>("/display/config");
      if (preview && previewId) c.playlist = c.playlist.filter((i) => i.dashboard_id === previewId);
      setCfg(c); setIdx((i) => (i >= c.playlist.length ? 0 : i)); setLastOk(Date.now());
      if (c.frontend_version !== APP_VERSION && APP_VERSION !== "dev" && c.frontend_version !== "dev") location.reload();
    } catch (e) { if (e instanceof ApiError && e.status === 401) onRevoked(); }
  }, [authed, onRevoked, preview, previewId]);

  /** force: recarrega definicao e ignora o ETag (usado por SSE); sem force o polling usa If-None-Match (304 barato). */
  const loadDashboard = useCallback(async (id: string, force = false) => {
    try {
      if (!dash[id] || force) { const d = await authed<Dash>(`/display/dashboards/${id}`); setDash((m) => ({ ...m, [id]: d })); persist(id, { dash: d }); }
      let etag: string | null = null;
      const r = await api<Data>("GET", `/display/dashboards/${id}/data`, {
        token: preview ? undefined : await getToken(),
        headers: !force && etags.current[id] ? { "If-None-Match": etags.current[id] } : undefined,
        onResponse: (res) => { etag = res.headers.get("etag"); },
      });
      setLastOk(Date.now());
      if (r) {
        if (etag) etags.current[id] = etag;
        setData((m) => ({ ...m, [id]: r })); persist(id, { data: r });
        // a definicao mudou (editor salvou) mesmo sem SSE: recarrega layout
        if (dashRef.current[id] && dashRef.current[id].version !== r.version) {
          const d = await authed<Dash>(`/display/dashboards/${id}`); setDash((m) => ({ ...m, [id]: d })); persist(id, { dash: d });
        }
      }
      blocked.current.delete(id);
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) blocked.current.add(id); // removido/sem acesso: pula
      if (e instanceof ApiError && e.status === 401) onRevoked();
    }
  }, [authed, dash, getToken, onRevoked, persist, preview]);
  const dashRef = useRef(dash); dashRef.current = dash;

  // boot + polling de fallback (60 s) + relogio
  useEffect(() => { loadConfig(); }, [loadConfig]);
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t); }, []);
  const current = cfg?.playlist[idx];
  useEffect(() => { if (current) loadDashboard(current.dashboard_id); }, [current?.dashboard_id]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!cfg) return;
    const t = setInterval(() => { if (cfg.playlist[idx]) loadDashboard(cfg.playlist[idx].dashboard_id); }, (cfg.poll_seconds || 60) * 1000);
    return () => clearInterval(t);
  }, [cfg, idx, loadDashboard]);

  // pre-carga da proxima dashboard
  useEffect(() => {
    if (!cfg || cfg.playlist.length < 2) return;
    const nxt = cfg.playlist[nextPlayable(idx, cfg.playlist, blocked.current)];
    if (nxt && !data[nxt.dashboard_id]) loadDashboard(nxt.dashboard_id);
  }, [cfg, idx, data, loadDashboard]);

  // rotacao
  useEffect(() => {
    if (!cfg || !current || cfg.playlist.length < 2) return;
    const t = setTimeout(() => setIdx((i) => nextPlayable(i, cfg.playlist, blocked.current)), Math.max(5, current.duration_seconds) * 1000);
    return () => clearTimeout(t);
  }, [cfg, current, idx]);

  // SSE autenticado (fetch-event-source envia Authorization; EventSource nativo nao envia)
  useEffect(() => {
    const ac = new AbortController(); let attempt = 0; let debounce: number | undefined;
    const invalidate = () => { clearTimeout(debounce); debounce = window.setTimeout(() => { const c = cfgRef.current; if (c?.playlist[idxRef.current]) loadRef.current(c.playlist[idxRef.current].dashboard_id, true); }, 1500); };
    (async () => {
      while (!ac.signal.aborted) {
        try {
          const tok = await getToken();
          await fetchEventSource("/api/v1/display/stream", {
            signal: ac.signal, openWhenHidden: true,
            headers: { Authorization: `Bearer ${preview ? (await getFreshAccessToken()) ?? "" : tok}`, "X-Requested-With": "gamatermic" },
            onopen: async (r) => { if (!r.ok) throw new ApiError(r.status, "sse", "SSE recusado"); sseUp.current = true; attempt = 0; },
            onmessage: (ev) => {
              setLastOk(Date.now());
              if (ev.event === "dataset_updated") invalidate();
              else if (ev.event === "config_changed") { loadConfigRef.current(); invalidate(); }
              else if (ev.event === "revoked") onRevoked();
            },
            onclose: () => { sseUp.current = false; throw new Error("closed"); },
            onerror: (e) => { sseUp.current = false; throw e; },
          });
        } catch (e) {
          sseUp.current = false;
          if (ac.signal.aborted) return;
          if (e instanceof ApiError && e.status === 401 && !preview) { /* token vencido: renova no proximo ciclo */ }
        }
        await new Promise((r) => setTimeout(r, backoff(attempt++)));
      }
    })();
    return () => { ac.abort(); clearTimeout(debounce); };
  }, [getToken, onRevoked, preview]);

  const cfgRef = useRef(cfg); cfgRef.current = cfg;
  const idxRef = useRef(idx); idxRef.current = idx;
  const loadRef = useRef(loadDashboard); loadRef.current = loadDashboard;
  const loadConfigRef = useRef(loadConfig); loadConfigRef.current = loadConfig;

  // heartbeat
  useEffect(() => {
    if (preview) return;
    const t = setInterval(async () => {
      const conn = connectionState(lastOkRef.current, Date.now());
      try { await api("POST", "/display/heartbeat", { body: { app_version: APP_VERSION, stale_state: conn === "offline" ? "offline" : "ok" }, token: await getToken() }); setLastOk(Date.now()); } catch { /* offline */ }
    }, 30_000);
    return () => clearInterval(t);
  }, [getToken, preview]);
  const lastOkRef = useRef(lastOk); lastOkRef.current = lastOk;

  // reload diario as 03:00 (SP) no limite de rotacao e versao do front
  useEffect(() => {
    const t = setInterval(() => { const h = new Date().toLocaleString("pt-BR", { timeZone: "America/Sao_Paulo", hour: "2-digit", minute: "2-digit", hour12: false }); if (h === "03:00" && !preview) location.reload(); }, 60_000);
    return () => clearInterval(t);
  }, [preview]);

  const d = current ? dash[current.dashboard_id] : undefined;
  const dd = current ? data[current.dashboard_id] : undefined;
  const results = useMemo(() => Object.fromEntries((dd?.widgets ?? []).map((r) => [r.widget_id, r])), [dd]);
  const conn = connectionState(lastOk, now);
  const stale = staleSources(dd?.sources);
  const asOf = dd?.widgets.map((w) => w.data_as_of).filter(Boolean).sort().pop() ?? null;
  const rows = d ? Math.max(1, ...d.widgets.map((w) => w.y + w.h)) : 1;
  const off = burnInOffset(now);

  if (!cfg) return <Screen><p className="text-2xl text-ink-soft" role="status">Carregando playlist…</p></Screen>;
  if (cfg.playlist.length === 0) return <Screen><Logo light /><p className="text-3xl">Nenhuma dashboard na playlist desta TV.</p><p className="text-ink-mute">Atribua uma playlist no painel de administração.</p></Screen>;

  return (
    <div className="flex h-screen w-screen flex-col bg-surface p-[clamp(.5rem,1vw,1.5rem)] text-ink" style={{ transform: `translate(${off.x}px, ${off.y}px)` }}>
      <header className="mb-[clamp(.4rem,.8vw,1rem)] flex items-center justify-between gap-4">
        <div className="flex items-baseline gap-4"><Logo light /><h1 className="text-[clamp(1.1rem,2vw,2.2rem)] font-bold">{current?.name}</h1></div>
        <div className="flex items-center gap-3 text-[clamp(.8rem,1.2vw,1.3rem)]">
          {conn === "offline" && <span role="status" className="rounded-full bg-danger px-3 py-1 font-bold text-white">Sem conexão · dados de {fmtTime(asOf)}</span>}
          {conn === "online" && stale.length > 0 && <span role="status" className="rounded-full bg-warn px-3 py-1 font-bold text-black">Dados de origem atrasados: {stale.map((s) => s.name).join(", ")}</span>}
          <span className="tabular text-ink-soft">Dados de {fmtTime(asOf)}</span>
          <time className="tabular text-[clamp(1.1rem,1.8vw,2rem)] font-bold" dateTime={new Date(now).toISOString()}>{new Date(now).toLocaleTimeString("pt-BR", { timeZone: "America/Sao_Paulo", hour: "2-digit", minute: "2-digit" })}</time>
        </div>
      </header>
      <div key={current?.dashboard_id} className={cx("grid min-h-0 flex-1 gap-[clamp(.4rem,.8vw,1rem)]", current?.transition === "slide" ? "slide-in" : current?.transition === "none" ? "" : "fade-in")}
        style={{ gridTemplateColumns: "repeat(12, minmax(0, 1fr))", gridTemplateRows: `repeat(${rows}, minmax(0, 1fr))` }}>
        {d ? d.widgets.map((w) => (
          <div key={w.id} className="min-h-0" style={{ gridColumn: `${w.x + 1} / span ${w.w}`, gridRow: `${w.y + 1} / span ${w.h}` }}>
            <WidgetCard widget={w} result={results[w.id]} tv />
          </div>
        )) : <div className="col-span-12 flex items-center justify-center text-2xl text-ink-mute" role="status">Carregando dashboard…</div>}
      </div>
      {cfg.playlist.length > 1 && (
        <nav aria-label="Playlist" className="mt-1 flex justify-center gap-2">
          {cfg.playlist.map((p, i) => <span key={p.dashboard_id} className={cx("h-1.5 rounded-full transition-all", i === idx ? "w-8 bg-accent" : "w-3 bg-line")} />)}
        </nav>
      )}
    </div>
  );
}
