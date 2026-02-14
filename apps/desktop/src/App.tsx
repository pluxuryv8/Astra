import { Suspense, lazy } from "react";

const AppShell = lazy(() => import("./app/AppShell"));
const OverlayApp = lazy(() => import("./app/OverlayApp"));
const LegacyApp = lazy(() => import("./legacy_ui/LegacyApp"));

export default function App() {
  const view = new URLSearchParams(window.location.search).get("view");
  if (view === "overlay") {
    return (
      <Suspense fallback={<div className="app-boot">Загрузка интерфейса…</div>}>
        <OverlayApp />
      </Suspense>
    );
  }

  if (view === "settings") {
    return (
      <Suspense fallback={<div className="app-boot">Загрузка интерфейса…</div>}>
        <LegacyApp />
      </Suspense>
    );
  }

  return (
    <Suspense fallback={<div className="app-boot">Загрузка интерфейса…</div>}>
      <AppShell />
    </Suspense>
  );
}
