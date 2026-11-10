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
  if (!user || !user.admin) return h('div',null,
    h('header',{style:{padding:'12px 24px',display:'flex',justifyContent:'space-between'}},h('strong',null,'TAKS'),user && h('button',{className:'btn',onClick:async()=>{await fetch('/api/logout');location.reload();}},'Sign out')),
    h(MartineView));
  return h(Layout, { tab, setTab, health, brand },
    tab === "onboarding" && h(OnboardingView),
    tab === "ai" && h(AIHubView),
    tab === "martine" && h(MartineView),
    tab === "replay" && h(ReplayView),
    tab === "documents" && h(DocumentsPage),
    tab === "files" && h(FileBrowserPage),
    tab === "package-check" && h(PackageCheckPage),
    tab === "health" && h(HealthView),
    tab === "logs" && h(LogsViewerView),
    tab === "config" && h(ConfigView)
  );
}

const __rootEl = document.getElementById("root");
if (ReactDOM && typeof ReactDOM.createRoot === "function") {
  ReactDOM.createRoot(__rootEl).render(h(App));
} else {
  ReactDOM.render(h(App), __rootEl);
}
