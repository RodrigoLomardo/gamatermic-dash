import { ReactNode, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { Logo, cx } from "@/shared/ui/ui";
import { useAuth } from "./auth";
import { IconDatabase, IconGrid, IconHistory, IconLogout, IconMenu, IconShield, IconSliders, IconTv, IconUsers } from "./icons";
import { ThemeToggle } from "./ThemeToggle";

type Item = { to: string; label: string; icon: ReactNode; perm?: string; any?: string[] };
const GROUPS: { title: string; items: Item[] }[] = [
  { title: "Workspace", items: [
    { to: "/dashboards", label: "Dashboards", icon: <IconGrid />, perm: "dashboard:view" },
    { to: "/datasets", label: "Dados e cargas", icon: <IconDatabase />, any: ["dataset:view", "ingestion:view"] },
    { to: "/admin/devices", label: "TVs e playlists", icon: <IconTv />, any: ["device:manage", "playlist:manage"] },
  ] },
  { title: "Administração", items: [
    { to: "/admin/users", label: "Usuários", icon: <IconUsers />, perm: "user:manage" },
    { to: "/admin/roles", label: "Perfis e grupos", icon: <IconShield />, any: ["role:manage", "group:manage"] },
    { to: "/admin/audit", label: "Auditoria", icon: <IconHistory />, perm: "audit:view" },
    { to: "/configuracoes", label: "Configurações", icon: <IconSliders />, perm: "settings:manage" },
  ] },
];

const initials = (name?: string) => (name ?? "?").split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]!.toUpperCase()).join("");

export function Layout() {
  const { user, can, logout } = useAuth();
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const allowed = (i: Item) => (i.perm ? can(i.perm) : i.any ? i.any.some(can) : true);
  const groups = GROUPS.map((g) => ({ ...g, items: g.items.filter(allowed) })).filter((g) => g.items.length);
  const link = ({ isActive }: { isActive: boolean }) => cx("nav-link", isActive && "is-active");
  return (
    <div className="flex min-h-full flex-col md:flex-row">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-panel focus:p-2">Ir para o conteúdo</a>
      <header className="flex items-center justify-between bg-sidebar px-4 py-3 md:hidden">
        <Logo light />
        <div className="flex items-center gap-2">
          <ThemeToggle onDark />
          <button aria-label="Abrir menu" aria-expanded={open} className="grid h-10 w-10 place-items-center rounded-xl text-white hover:bg-white/10" onClick={() => setOpen(!open)}><IconMenu /></button>
        </div>
      </header>
      <aside className={cx("w-full shrink-0 flex-col bg-sidebar px-4 py-6 md:sticky md:top-0 md:flex md:h-screen md:w-72 md:overflow-y-auto", open ? "flex" : "hidden")}>
        <div className="mb-8 hidden px-2 md:block"><Logo light height={44} /></div>
        <nav aria-label="Principal" className="flex-1 space-y-7">
          {groups.map((g) => (
            <div key={g.title}>
              <p className="mb-3 px-3 text-xs font-semibold uppercase tracking-[0.2em] text-white/45">{g.title}</p>
              <div className="space-y-1">
                {g.items.map((i) => <NavLink key={i.to} to={i.to} className={link} onClick={() => setOpen(false)}>{i.icon}{i.label}</NavLink>)}
              </div>
            </div>
          ))}
        </nav>
        <div className="mt-8 flex items-center gap-3 border-t border-white/15 px-2 pt-5">
          <span aria-hidden="true" className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-white/10 text-sm font-bold text-white">{initials(user?.full_name)}</span>
          <div className="min-w-0 flex-1 text-white">
            <p className="truncate text-sm font-semibold">{user?.full_name}</p>
            <p className="truncate text-xs text-white/60">{user?.roles.join(", ") || "sem perfil"}</p>
          </div>
          <button aria-label="Sair" title="Sair" className="grid h-10 w-10 place-items-center rounded-xl text-white/80 transition hover:bg-white/10 hover:text-white"
            onClick={async () => { await logout(); nav("/login"); }}><IconLogout /></button>
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="hidden items-center justify-between px-10 pt-8 md:flex">
          <p className="text-sm tracking-wide text-ink-mute">Workspace <span className="mx-2 opacity-60">/</span> <span className="font-semibold text-ink-soft">Gama Termic</span></p>
          <ThemeToggle />
        </div>
        <main id="main" className="min-w-0 flex-1 p-4 md:px-10 md:pb-10 md:pt-6"><div className="page-in"><Outlet /></div></main>
      </div>
    </div>
  );
}
