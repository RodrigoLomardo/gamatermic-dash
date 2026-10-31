import type { components } from "./schema";

export type S = components["schemas"];

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public extra: Record<string, unknown> = {}) {
    super(message);
  }
}

const BASE = "/api/v1";
let accessToken: string | null = null;
let refreshing: Promise<string | null> | null = null;
let onAuthLost: () => void = () => {};
let onTokenRefreshed: (t: S["TokenOut"]) => void = () => {};

export const setAccessToken = (t: string | null) => { accessToken = t; };
export const getAccessToken = () => accessToken;

/** Access token valido: renova (single-flight) se faltar menos de 60 s para expirar. Para conexoes longas (SSE do modo visualizacao). */
export async function getFreshAccessToken(): Promise<string | null> {
  if (accessToken) {
    try {
      const exp = JSON.parse(atob(accessToken.split(".")[1].replace(/-/g, "+").replace(/_/g, "/"))).exp as number;
      if (exp * 1000 - Date.now() > 60_000) return accessToken;
    } catch { /* token ilegivel: renova */ }
  }
  return refreshSession();
}
export const setAuthHandlers = (lost: () => void, refreshed: (t: S["TokenOut"]) => void) => { onAuthLost = lost; onTokenRefreshed = refreshed; };

async function toError(res: Response): Promise<ApiError> {
  let body: any = {};
  try { body = await res.json(); } catch { /* corpo vazio */ }
  const { detail, code, type: _t, title: _ti, status: _s, instance: _i, ...extra } = body;
  return new ApiError(res.status, code ?? "error", detail ?? res.statusText, extra);
}

/** Renovacao unica (single-flight): abas/requests concorrentes compartilham a mesma chamada. */
export function refreshSession(): Promise<string | null> {
  if (!refreshing) {
    refreshing = fetch(`${BASE}/auth/refresh`, { method: "POST", credentials: "include", headers: { "X-Requested-With": "gamatermic" } })
      .then(async (r) => {
        if (!r.ok) return null;
        const t = (await r.json()) as S["TokenOut"];
        accessToken = t.access_token;
        onTokenRefreshed(t);
        return accessToken;
      })
      .catch(() => null)
      .finally(() => { setTimeout(() => { refreshing = null; }, 0); });
  }
  return refreshing;
}

type Opts = {
  body?: unknown; query?: Record<string, string | number | boolean | undefined | null>; form?: FormData;
  headers?: Record<string, string>; token?: string | null; noAuth?: boolean; signal?: AbortSignal; text?: boolean; onResponse?: (r: Response) => void;
};

export async function api<T = unknown>(method: string, path: string, o: Opts = {}): Promise<T> {
  const q = o.query ? "?" + new URLSearchParams(Object.entries(o.query).filter(([, v]) => v != null && v !== "").map(([k, v]) => [k, String(v)])).toString() : "";
  const send = (tok: string | null) => {
    const h: Record<string, string> = { "X-Requested-With": "gamatermic", ...(o.headers ?? {}) };
    if (tok && !o.noAuth) h.Authorization = `Bearer ${tok}`;
    if (o.body !== undefined) h["Content-Type"] = "application/json";
    return fetch(`${BASE}${path}${q}`, {
      method, headers: h, credentials: "include", signal: o.signal,
      body: o.form ?? (o.body !== undefined ? JSON.stringify(o.body) : undefined),
    });
  };
  let res = await send(o.token !== undefined ? o.token : accessToken);
  if (res.status === 401 && !o.noAuth && o.token === undefined && !path.startsWith("/auth/")) {
    const fresh = await refreshSession();
    if (fresh) res = await send(fresh);
    else { setAccessToken(null); onAuthLost(); }
  }
  o.onResponse?.(res);
  if (res.status === 304) return undefined as T;
  if (!res.ok) throw await toError(res);
  if (res.status === 204) return undefined as T;
  return (o.text ? await res.text() : await res.json()) as T;
}

export const get = <T>(p: string, o?: Opts) => api<T>("GET", p, o);
export const post = <T>(p: string, body?: unknown, o?: Opts) => api<T>("POST", p, { ...o, body });
export const put = <T>(p: string, body?: unknown, o?: Opts) => api<T>("PUT", p, { ...o, body });
export const patch = <T>(p: string, body?: unknown, o?: Opts) => api<T>("PATCH", p, { ...o, body });
export const del = <T>(p: string, o?: Opts) => api<T>("DELETE", p, o);
