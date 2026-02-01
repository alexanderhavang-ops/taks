function App() {
  const [tab, setTab] = React.useState("users");

  // health: cache briefly to avoid flicker; poll every 10s
  const health = useApi("api/health", { cacheMs: 2000, pollMs: 10000 });

  return h(Layout, { tab, setTab, health },
    tab === "users" && h(UsersView),
    tab === "clients" && h(ClientsView),
    tab === "crl" && h(CRLView),
    tab === "certs" && h(CertsView)
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(h(App));
