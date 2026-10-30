import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { Logo, cx } from "@/shared/ui/ui";
import { useAuth } from "./auth";

type Item = { to: string; label: string; perm?: string; any?: string[] };
const NAV: Item[] = [
  { to: "/dashboards", label: "Dashboards", perm: "dashboard:view" },
  { to: "/datasets", label: "Dados e cargas", any: ["dataset:view", "ingestion:view"] },
  { to: "/admin/devices", label: "TVs e playlists", any: ["device:manage", "playlist:manage"] },
  { to: "/admin/users", label: "Usuários", perm: "user:manage" },
  { to: "/admin/roles", label: "Perfis e grupos", any: ["role:manage", "group:manage"] },
  { to: "/admin/audit", label: "Auditoria", perm: "audit:view" },
];

export function Layout() {
  const { user, can, logout } = useAuth();
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const items = NAV.filter((i) => (i.perm ? can(i.perm) : i.any ? i.any.some(can) : true));
  const link = ({ isActive }: { isActive: boolean }) =>
    cx("block rounded-lg px-3 py-2 text-sm font-medium", isActive ? "bg-accent text-accent-on" : "text-white/80 hover:bg-white/10");
  return (
    <div className="flex min-h-full flex-col md:flex-row">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-white focus:p-2">Ir para o conteúdo</a>
      <header className="flex items-center justify-between bg-brand px-4 py-3 md:hidden">
        <Logo light />
        <button aria-label="Abrir menu" aria-expanded={open} className="rounded p-2 text-white" onClick={() => setOpen(!open)}>☰</button>
      </header>
      <aside className={cx("w-full shrink-0 bg-brand p-4 md:block md:w-60", open ? "block" : "hidden")}>
        <div className="mb-6 hidden md:block"><Logo light /></div>
        <nav aria-label="Principal" className="space-y-1">
          {items.map((i) => <NavLink key={i.to} to={i.to} className={link} onClick={() => setOpen(false)}>{i.label}</NavLink>)}
        </nav>
        <div className="mt-8 border-t border-white/15 pt-4 text-sm text-white/80">
          <p className="truncate font-semibold text-white">{user?.full_name}</p>
          <p className="truncate text-xs">{user?.roles.join(", ") || "sem perfil"}</p>
          <button className="mt-3 rounded-lg border border-white/30 px-3 py-1.5 text-xs font-semibold text-white hover:bg-white/10"
            onClick={async () => { await logout(); nav("/login"); }}>Sair</button>
        </div>
      </aside>
      <main id="main" className="min-w-0 flex-1 p-4 md:p-6"><Outlet /></main>
    </div>
  );
}
