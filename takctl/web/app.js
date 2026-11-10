/* element helper */
var h = (window.h || React.createElement); window.h = h;

function App() {
  const identity = useApi("api/whoami", {cacheMs:0,pollMs:30000});
  const [tabRaw, setTab] = React.useState("onboarding");

  const health = useApi("api/health", { cacheMs: 2000, pollMs: 10000 });
  const meta   = useApi("api/meta",   { cacheMs: 60000, pollMs: 0 });

  const brand =
    (meta && meta.ok && meta.data && (meta.data.brand || meta.data)) || {};

  const ALLOWED_TABS = {
    onboarding: true,
    ai: true,
    martine: true,
    replay: true,
    documents: true,
    files: true,
  "package-check": true,
    health: true,
    logs: true,
    config: true
  };
  const tab = ALLOWED_TABS[String(tabRaw || "")] ? tabRaw : "onboarding";

  const user = identity && identity.data && identity.data.user;
  if (!identity || !identity.data) return h('p',null,'Loading TAKS…');
  if (!user) { location.replace('/splash.html'); return null; }
  const visibleTabs = user.admin ? null : ['onboarding','martine'];
  const activeTab = visibleTabs && !visibleTabs.includes(tab) ? 'onboarding' : tab;
  return h(Layout, { tab:activeTab, setTab, health, brand, visibleTabs },
    activeTab === "onboarding" && h(user.admin ? OnboardingView : PersonalOnboardingView),
    activeTab === "ai" && h(AIHubView),
    activeTab === "martine" && h(MartineView),
    activeTab === "replay" && h(ReplayView),
    activeTab === "documents" && h(DocumentsPage),
    activeTab === "files" && h(FileBrowserPage),
    activeTab === "package-check" && h(PackageCheckPage),
    activeTab === "health" && h(HealthView),
    activeTab === "logs" && h(LogsViewerView),
    activeTab === "config" && h(ConfigView)
  );
}

const __rootEl = document.getElementById("root");
if (ReactDOM && typeof ReactDOM.createRoot === "function") {
  ReactDOM.createRoot(__rootEl).render(h(App));
} else {
  ReactDOM.render(h(App), __rootEl);
}
