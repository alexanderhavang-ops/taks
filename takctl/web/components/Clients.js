function ClientsView() {
  return h("div", { className: "card" },
    h("div", { className: "card-title" }, "Clients"),
    h("div", { className: "muted" }, "Coming soon (next step: /api/clients + table)")
  );
}
