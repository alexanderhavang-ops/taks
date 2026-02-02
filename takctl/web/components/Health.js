function HealthBadge({ health }) {
  const ok = health && !health.loading && !health.error && health.data && health.data.status === "ok";

  const dotStyle = {
    display: "inline-block",
    width: "10px",
    height: "10px",
    borderRadius: "50%",
    marginRight: "8px",
    background: ok ? "#22c55e" : (health && health.loading ? "#f59e0b" : "#ef4444")
  };

  const smallStyle = { opacity: 0.8, fontSize: "12px" };

  return h("div", { className: "card", style: { marginBottom: "12px" } },
    h("div", { style: { display: "flex", alignItems: "center", justifyContent: "space-between" } },
      h("div", null,
        h("div", { style: { fontWeight: 700 } }, "Backend health"),
        h("div", { style: smallStyle }, "Fetch: " + (health && health.loading ? "loading..." : ok ? "ok" : "error"))
      ),
      h("div", null,
        h("span", { style: dotStyle }),
        h("span", { style: smallStyle }, ok ? "OK" : (health && health.loading ? "..." : "FAIL"))
      )
    ),
    h("div", { style: { marginTop: "10px" } },
      h("div", { style: smallStyle }, "window.location: " + window.location.href),
      h("div", { style: smallStyle }, "api url: api/health")
    ),
    health && health.error && h("pre", { className: "pre", style: { marginTop: "10px" } }, String(health.error)),
    health && health.data && h("pre", { className: "pre", style: { marginTop: "10px" } }, JSON.stringify(health.data, null, 2))
  );
}
