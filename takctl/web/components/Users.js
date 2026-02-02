function UsersView() {
  return h("div", { className: "card" },
    h("div", { className: "card-title" }, "Users"),
    h("div", { className: "muted" }, "Coming soon (next step: /api/users + table)")
  );
}
