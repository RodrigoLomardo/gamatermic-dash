import { FormEvent, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth, errMsg } from "@/app/auth";
import { post } from "@/shared/api/http";
import { ThemeToggle } from "@/app/ThemeToggle";
import { Button, Card, Field, Input, Logo, Spinner, useToasts } from "@/shared/ui/ui";

export function RequireAuth({ perm, children }: { perm?: string; children: JSX.Element }) {
  const { user, ready, can } = useAuth();
  const loc = useLocation();
  if (!ready) return <Spinner />;
  if (!user) return <Navigate to="/login" replace state={{ from: loc.pathname }} />;
  if (user.must_change_password && loc.pathname !== "/trocar-senha") return <Navigate to="/trocar-senha" replace />;
  if (perm && !can(perm)) return <div role="alert" className="p-8 text-center text-ink-soft">Você não tem permissão para acessar esta área.</div>;
  return children;
}

export function LoginPage() {
  const { login, user } = useAuth();
  const nav = useNavigate();
  const loc = useLocation() as { state?: { from?: string } };
  const [email, setEmail] = useState(""); const [pw, setPw] = useState("");
  const [err, setErr] = useState<string | null>(null); const [busy, setBusy] = useState(false);
  if (user && !user.must_change_password) return <Navigate to="/dashboards" replace />;
  const submit = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true); setErr(null);
    try { const u = await login(email.trim(), pw); nav(u.must_change_password ? "/trocar-senha" : loc.state?.from ?? "/dashboards", { replace: true }); }
    catch (x) { setErr(errMsg(x)); } finally { setBusy(false); }
  };
  return (
    <div className="flex min-h-full items-center justify-center bg-sidebar p-4">
      <div className="w-full max-w-sm space-y-6">
        <div className="flex items-center justify-between"><Logo light /><ThemeToggle onDark /></div>
        <Card>
          <form onSubmit={submit} className="space-y-4" aria-label="Entrar">
            <h1 className="text-xl font-bold">Entrar</h1>
            <Field label="E-mail">{(id) => <Input id={id} type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />}</Field>
            <Field label="Senha" error={err}>{(id) => <Input id={id} type="password" autoComplete="current-password" required value={pw} onChange={(e) => setPw(e.target.value)} />}</Field>
            <Button type="submit" className="w-full" disabled={busy}>{busy ? "Entrando…" : "Entrar"}</Button>
          </form>
        </Card>
        <p className="text-center text-xs text-white/60">Acesso restrito a colaboradores. Esqueceu a senha? Fale com um administrador.</p>
      </div>
    </div>
  );
}

export function ChangePasswordPage() {
  const { user, reloadMe, logout } = useAuth();
  const nav = useNavigate(); const toast = useToasts((s) => s.push);
  const [cur, setCur] = useState(""); const [nw, setNw] = useState(""); const [nw2, setNw2] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault(); setErr(null);
    if (nw !== nw2) return setErr("As senhas não conferem.");
    try {
      await post("/auth/change-password", { current_password: cur, new_password: nw });
      toast("Senha alterada. Entre novamente.");
      await logout(); nav("/login");
    } catch (x) { setErr(errMsg(x)); }
  };
  void reloadMe;
  return (
    <div className="mx-auto max-w-md">
      <Card title={user?.must_change_password ? "Defina uma nova senha" : "Trocar senha"}>
        <form onSubmit={submit} className="space-y-4">
          {user?.must_change_password && <p className="text-sm text-ink-soft">Por segurança, troque a senha temporária no primeiro acesso.</p>}
          <Field label="Senha atual">{(id) => <Input id={id} type="password" autoComplete="current-password" required value={cur} onChange={(e) => setCur(e.target.value)} />}</Field>
          <Field label="Nova senha" hint="Mínimo de 12 caracteres. Frases longas funcionam bem; senhas comuns são recusadas.">{(id) => <Input id={id} type="password" autoComplete="new-password" required minLength={12} value={nw} onChange={(e) => setNw(e.target.value)} />}</Field>
          <Field label="Repita a nova senha" error={err}>{(id) => <Input id={id} type="password" autoComplete="new-password" required value={nw2} onChange={(e) => setNw2(e.target.value)} />}</Field>
          <Button type="submit">Salvar nova senha</Button>
        </form>
      </Card>
    </div>
  );
}
