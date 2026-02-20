function HealthBadge({ health }) {
  const ok = health && !health.loading && !health.error && health.data && health.data.status === "ok";
  const loading = health && health.loading;

  const bg = ok ? "#22c55e" : (loading ? "#f59e0b" : "#ef4444");
  const title =
    ok ? "Backend: OK" :
    loading ? "Backend: loading..." :
    ("Backend: FAIL" + (health && health.error ? (" — " + String(health.error)) : ""));

  return h("span", {
    className: "health-dot",
    title,
    style: {
      display: "inline-block",
      width: "10px",
      height: "10px",
      borderRadius: "999px",
      background: bg,
      boxShadow: "0 0 0 1px rgba(255,255,255,0.10)",
    }
  });
}

