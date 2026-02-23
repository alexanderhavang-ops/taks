/* element helper */
var h = (window.h || React.createElement); window.h = h;

function App() {
  const [tabRaw, setTab] = React.useState("onboarding");

  // Root-native: keep API calls relative (works at /).
  const health = useApi("api/health", { cacheMs: 2000, pollMs: 10000 });
  const meta   = useApi("api/meta",   { cacheMs: 60000, pollMs: 0 });

  const brand =
    (meta && meta.ok && meta.data && (meta.data.brand || meta.data)) || {};

  const ALLOWED_TABS = { onboarding: true, llm: true };
  const tab = ALLOWED_TABS[String(tabRaw || "")] ? tabRaw : "onboarding";

  return h(Layout, { tab, setTab, health, brand },
    tab === "onboarding" && h(OnboardingView),
    tab === "llm" && h(LLMView)
  );
}

const __rootEl = document.getElementById("root");
if (ReactDOM && typeof ReactDOM.createRoot === "function") {
  ReactDOM.createRoot(__rootEl).render(h(App));
} else {
  ReactDOM.render(h(App), __rootEl);
}
