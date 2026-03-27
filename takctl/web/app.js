/* element helper */
var h = (window.h || React.createElement); window.h = h;

function App() {
  const [tabRaw, setTab] = React.useState("onboarding");

  const health = useApi("api/health", { cacheMs: 2000, pollMs: 10000 });
  const meta   = useApi("api/meta",   { cacheMs: 60000, pollMs: 0 });

  const brand =
    (meta && meta.ok && meta.data && (meta.data.brand || meta.data)) || {};

  const ALLOWED_TABS = {
    onboarding: true,
    llm: true,
    usage: true,
    martine: true,
    replay: true,
    config: true
  };
  const tab = ALLOWED_TABS[String(tabRaw || "")] ? tabRaw : "onboarding";

  return h(Layout, { tab, setTab, health, brand },
    tab === "onboarding" && h(OnboardingView),
    tab === "llm" && h(LLMView),
    tab === "usage" && h(UsageView),
    tab === "martine" && h(MartineView),
    tab === "replay" && h(ReplayView),
    tab === "config" && h(ConfigView)
  );
}

const __rootEl = document.getElementById("root");
if (ReactDOM && typeof ReactDOM.createRoot === "function") {
  ReactDOM.createRoot(__rootEl).render(h(App));
} else {
  ReactDOM.render(h(App), __rootEl);
}
