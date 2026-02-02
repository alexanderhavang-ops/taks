function CRLView() {
  return h("div", { className: "card" },
    h("div", { className: "card-title" }, "CRL"),
    h("div", { className: "muted" }, "Coming soon (next step: /api/crl/status)")
  );
}
