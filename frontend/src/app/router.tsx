import { ComponentType, LazyExoticComponent, lazy, Suspense } from "react";
import { Navigate, Outlet, createBrowserRouter } from "react-router-dom";
import { Spinner } from "@/shared/ui/ui";
import { ChangePasswordPage, LoginPage, RequireAuth } from "@/features/auth/AuthPages";
import { useAuth } from "./auth";
import { Layout } from "./Layout";

const L = (p: Promise<any>, name: string): LazyExoticComponent<ComponentType<any>> => lazy(() => p.then((m) => ({ default: m[name] })));
const DashboardsListPage = L(import("@/features/dashboards/DashboardPages"), "DashboardsListPage");
const DashboardViewPage = L(import("@/features/dashboards/DashboardPages"), "DashboardViewPage");
const AnalysisPage = L(import("@/features/analysis/AnalysisPage"), "AnalysisPage");
const EditorPage = L(import("@/features/dashboard-editor/EditorPage"), "EditorPage");
const NewDashboardPage = L(import("@/features/dashboard-editor/EditorPage"), "NewDashboardPage");
const DatasetsPage = L(import("@/features/datasets/DatasetPages"), "DatasetsPage");
const DatasetDetailPage = L(import("@/features/datasets/DatasetPages"), "DatasetDetailPage");
const NewDatasetPage = L(import("@/features/datasets/DatasetPages"), "NewDatasetPage");
const UsersPage = L(import("@/features/admin/UsersPage"), "UsersPage");
const RolesPage = L(import("@/features/admin/RolesPage"), "RolesPage");
const DevicesPage = L(import("@/features/admin/DevicesPage"), "DevicesPage");
const AuditPage = L(import("@/features/admin/AuditPage"), "AuditPage");
const SettingsPage = L(import("@/features/settings/SettingsPage"), "SettingsPage");
const AiCreatePage = L(import("@/features/ai-dashboards/AiCreatePage"), "AiCreatePage");
const TvPage = L(import("@/features/tv-player/TvPage"), "TvPage");

const S = ({ children }: { children: JSX.Element }) => <Suspense fallback={<Spinner />}>{children}</Suspense>;
const guard = (el: JSX.Element, perm?: string) => <RequireAuth perm={perm}><S>{el}</S></RequireAuth>;

function Boot({ children }: { children: JSX.Element }) {
  const ready = useAuth((s) => s.ready);
  if (!ready) { useAuth.getState().bootstrap(); return <Spinner label="Iniciando…" />; }
  return children;
}

function Oops() {
  return (
    <div role="alert" className="flex h-full flex-col items-center justify-center gap-3 p-8 text-center">
      <h1 className="text-2xl font-bold">Algo deu errado</h1>
      <p className="text-ink-soft">A tela encontrou um erro inesperado. Seus dados não foram afetados.</p>
      <button className="rounded-lg bg-accent px-4 py-2 font-semibold text-accent-on" onClick={() => location.reload()}>Recarregar</button>
    </div>
  );
}

export const router = createBrowserRouter([
  // player de TV: sem login de usuario (credencial de dispositivo); preview exige usuario
  { path: "/tv", errorElement: <Oops />, element: <S><TvPage /></S> },
  // link de visualizacao: mesma tela da TV, so o painel (sem menu). Pede login e volta direto para ca.
  { path: "/tv/painel/:id", errorElement: <Oops />, element: <Boot><RequireAuth perm="dashboard:view"><S><TvPage preview /></S></RequireAuth></Boot> },
  { path: "/tv/preview/:id", element: <Boot><RequireAuth perm="dashboard:view"><S><TvPage preview /></S></RequireAuth></Boot> },
  {
    path: "/",
    errorElement: <Oops />,
    element: <Boot><Outlet /></Boot>,
    children: [
      { path: "login", element: <LoginPage /> },
      {
        element: <RequireAuth><Layout /></RequireAuth>,
        children: [
          { index: true, element: <Navigate to="/dashboards" replace /> },
          { path: "trocar-senha", element: <ChangePasswordPage /> },
          { path: "dashboards", element: guard(<DashboardsListPage />, "dashboard:view") },
          { path: "dashboards/nova", element: guard(<NewDashboardPage />, "dashboard:create") },
          { path: "dashboards/nova/ia", element: guard(<AiCreatePage />, "dashboard:create") },
          { path: "dashboards/:id", element: guard(<DashboardViewPage />, "dashboard:view") },
          { path: "dashboards/:id/analise", element: guard(<AnalysisPage />, "dashboard:view") },
          { path: "dashboards/:id/editar", element: guard(<EditorPage />, "dashboard:edit") },
          { path: "datasets", element: guard(<DatasetsPage />, "dataset:view") },
          { path: "datasets/novo", element: guard(<NewDatasetPage />, "dataset:manage") },
          { path: "datasets/:id", element: guard(<DatasetDetailPage />, "dataset:view") },
          { path: "admin/devices", element: guard(<DevicesPage />) },
          { path: "admin/users", element: guard(<UsersPage />, "user:manage") },
          { path: "admin/roles", element: guard(<RolesPage />, "role:manage") },
          { path: "admin/audit", element: guard(<AuditPage />, "audit:view") },
          { path: "configuracoes", element: guard(<SettingsPage />, "settings:manage") },
          { path: "*", element: <div className="p-8 text-center text-ink-soft">Página não encontrada.</div> },
        ],
      },
    ],
  },
]);

