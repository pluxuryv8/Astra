import MainApp from "./MainApp";
import OverlayApp from "./OverlayApp";
import SettingsApp from "./SettingsApp";

export default function App() {
  const view = new URLSearchParams(window.location.search).get("view");
  if (view === "overlay") return <OverlayApp />;
  if (view === "settings") return <SettingsApp />;
  return <MainApp />;
}
