function App() {
  const [tab, setTab] = React.useState("users");

  // IMPORTANT: relative path so it works under /takctl/ mount
  const health = useApi("api/health", { cacheMs: 2000, pollMs: 10000 });

  return h(Layout, { tab, setTab, health },
    tab === "users" && h(UsersView),
    tab === "clients" && h(ClientsView),
    tab === "crl" && h(CRLView),
    tab === "certs" && h(CertsView)
  );
}

const __rootEl = document.getElementById("root");
if (ReactDOM && typeof ReactDOM.createRoot === "function") {
  ReactDOM.createRoot(__rootEl).render(h(App));
} else {
  ReactDOM.render(h(App), __rootEl);
}
