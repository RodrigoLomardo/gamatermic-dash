import { create } from "zustand";
import { ApiError, S, get, post, refreshSession, setAccessToken, setAuthHandlers } from "@/shared/api/http";

type Me = S["MeOut"];
type State = {
  user: Me | null; ready: boolean;
  bootstrap: () => Promise<void>;
  login: (email: string, password: string) => Promise<Me>;
  logout: () => Promise<void>;
  reloadMe: () => Promise<void>;
  can: (perm: string) => boolean;
};

export const useAuth = create<State>((set, getS) => ({
  user: null, ready: false,
  bootstrap: async () => {
    const tok = await refreshSession();
    if (tok) { try { set({ user: await get<Me>("/auth/me") }); } catch { /* sessao invalida */ } }
    set({ ready: true });
  },
  login: async (email, password) => {
    const t = await post<S["TokenOut"]>("/auth/login", { email, password }, { noAuth: true });
    setAccessToken(t.access_token);
    set({ user: t.user });
    return t.user;
  },
  logout: async () => {
    try { await post("/auth/logout"); } catch { /* ja deslogado */ }
    setAccessToken(null);
    set({ user: null });
  },
  reloadMe: async () => { set({ user: await get<Me>("/auth/me") }); },
  can: (perm) => !!getS().user?.permissions?.[perm],
}));

setAuthHandlers(
  () => useAuth.setState({ user: null }),
  (t) => useAuth.setState({ user: t.user }),
);

export const errMsg = (e: unknown): string => (e instanceof ApiError ? e.message : e instanceof Error ? e.message : "Erro inesperado.");
