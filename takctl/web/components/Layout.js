function TabButton({ id, tab, setTab, label }) {
  const active = (tab === id);
  return h("button", {
    className: active ? "tab tab-active" : "tab",
    onClick: () => setTab(id),
    type: "button",
  }, label);
}

function Layout({ tab, setTab, health, children }) {
  return h("div", { className: "app" },

    // Top bar
    h("div", { className: "topbar" },
      h("div", { className: "brand" }, "takctl"),

      h("div", { className: "tabs" },
        h(TabButton, { id: "users", tab, setTab, label: "Users" }),
        h(TabButton, { id: "clients", tab, setTab, label: "Clients" }),
        h(TabButton, { id: "crl", tab, setTab, label: "CRL" }),
        h(TabButton, { id: "certs", tab, setTab, label: "Certs" })
      ),

      h("div", { className: "spacer" }),

      h("div", { className: "health" },
        h("span", { className: "muted", style: { marginRight: "8px" } }, "api/health"),
        h(HealthBadge, { health })
      )
    ),

    // Main body (no left sidebar yet)
    h("div", { className: "body" },
      h("div", { className: "main" }, children)
    )
  );
}
