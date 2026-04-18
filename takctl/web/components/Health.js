var h = (window.h || React.createElement); window.h = h;

function _healthLang() {
  const v = String(window.currentLang || window.TAKS_RUNTIME_LANGUAGE || "sv").trim().toLowerCase();
  return v.startsWith("en") ? "en" : "sv";
}

function _healthTr(sv, en) {
  return _healthLang() === "en" ? en : sv;
}

function _healthStatusKind(status) {
  const s = String(status || "").trim().toLowerCase();
  if (s === "ok" || s === "healthy" || s === "green" || s === "pass") return "ok";
  if (s === "degraded" || s === "warn" || s === "warning" || s === "amber" || s === "yellow") return "warn";
  if (s === "loading") return "loading";
  if (s === "fail" || s === "failed" || s === "error" || s === "red" || s === "critical") return "err";
  return "muted";
}

function _healthStatusLabel(status) {
  const s = String(status || "").trim().toLowerCase();
  if (s === "ok" || s === "healthy" || s === "green" || s === "pass") return "OK";
  if (s === "degraded" || s === "warn" || s === "warning" || s === "amber" || s === "yellow") {
    return _healthTr("Varning", "Warning");
  }
  if (s === "loading") return _healthTr("Laddar", "Loading");
  if (s === "fail" || s === "failed" || s === "error" || s === "red" || s === "critical") {
    return _healthTr("Fel", "Fail");
  }
  return _healthTr("Okänd", "Unknown");
}

function _healthTone(status) {
  const kind = _healthStatusKind(status);
  if (kind === "ok") {
    return {
      fg: "#d1fae5",
      bg: "rgba(34,197,94,.14)",
      border: "1px solid rgba(34,197,94,.28)",
      dot: "#22c55e"
    };
  }
  if (kind === "warn" || kind === "loading") {
    return {
      fg: "#fde68a",
      bg: "rgba(245,158,11,.14)",
      border: "1px solid rgba(245,158,11,.28)",
      dot: "#f59e0b"
    };
  }
  if (kind === "err") {
    return {
      fg: "#fecaca",
      bg: "rgba(239,68,68,.14)",
      border: "1px solid rgba(239,68,68,.28)",
      dot: "#ef4444"
    };
  }
  return {
    fg: "rgba(255,255,255,.86)",
    bg: "rgba(255,255,255,.04)",
    border: "1px solid rgba(255,255,255,.10)",
    dot: "rgba(255,255,255,.55)"
  };
}

function _healthFriendlyName(name) {
  const raw = String(name || "").trim();
  if (!raw) return "—";
  return raw
    .replace(/^check[_-]/i, "")
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function _healthCardStyle(extra) {
  return Object.assign({
    border: "1px solid rgba(255,255,255,.08)",
    borderRadius: "14px",
    background: "linear-gradient(180deg, rgba(255,255,255,.03), rgba(255,255,255,.015))",
    boxShadow: "0 10px 24px rgba(0,0,0,.18)",
    padding: "14px"
  }, extra || {});
}

function _healthMonospacePre(obj) {
  return h("pre", {
    style: {
      margin: 0,
      whiteSpace: "pre-wrap",
      wordBreak: "break-word",
      fontSize: "12px",
      lineHeight: 1.45,
      padding: "12px",
      borderRadius: "10px",
      background: "rgba(0,0,0,.22)",
      overflowX: "auto"
    }
  }, JSON.stringify(obj, null, 2));
}

function HealthBadge({ health }) {
  const loading = !!(health && health.loading);
  const status = loading
    ? "loading"
    : (health && health.data && health.data.status) ? health.data.status : "error";

  const tone = _healthTone(status);
  const title =
    _healthStatusKind(status) === "ok" ? "Backend: OK" :
    _healthStatusKind(status) === "warn" ? "Backend: DEGRADED" :
    _healthStatusKind(status) === "loading" ? "Backend: loading..." :
    ("Backend: FAIL" + (health && health.error ? (" — " + String(health.error)) : ""));

  return h("span", {
    className: "health-dot",
    title,
    style: {
      display: "inline-block",
      width: "10px",
      height: "10px",
      borderRadius: "999px",
      background: tone.dot,
      boxShadow: "0 0 0 1px rgba(255,255,255,0.10)"
    }
  });
}

function ServerHealthPill({ status, large }) {
  const tone = _healthTone(status);
  return h("span", {
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: "8px",
      padding: large ? "8px 14px" : "4px 10px",
      borderRadius: "999px",
      fontSize: large ? "13px" : "12px",
      fontWeight: 800,
      color: tone.fg,
      background: tone.bg,
      border: tone.border,
      whiteSpace: "nowrap"
    }
  }, [
    h("span", {
      style: {
        width: large ? "10px" : "8px",
        height: large ? "10px" : "8px",
        borderRadius: "999px",
        background: tone.dot,
        display: "inline-block",
        boxShadow: "0 0 0 1px rgba(255,255,255,.10)"
      }
    }),
    _healthStatusLabel(status)
  ]);
}

function ServerHealthMetricCard({ label, value, hint }) {
  const valueNode =
    (typeof value === "string" || typeof value === "number")
      ? String(value)
      : value;

  return h("div", { style: _healthCardStyle({ padding: "12px 14px" }) }, [
    h("div", {
      style: {
        fontSize: "11px",
        opacity: .68,
        marginBottom: "8px",
        textTransform: "uppercase",
        letterSpacing: ".05em"
      }
    }, label),
    h("div", {
      style: {
        fontSize: "28px",
        lineHeight: 1.05,
        fontWeight: 800,
        wordBreak: "break-word"
      }
    }, valueNode),
    hint ? h("div", {
      className: "muted",
      style: { marginTop: "8px", fontSize: "12px" }
    }, hint) : null
  ]);
}

function _serverHealthPayload(data) {
  if (data && typeof data === "object" && data.payload && typeof data.payload === "object") {
    return data.payload;
  }
  return {};
}

function _serverHealthRollup(data, payload) {
  if (payload && payload.rollup && typeof payload.rollup === "object") return payload.rollup;
  if (data && data.summary && typeof data.summary === "object") return data.summary;
  return {};
}

function _serverHealthChecks(payload) {
  const src = payload && payload.checks;
  let items = [];

  if (Array.isArray(src)) {
    items = src.slice();
  } else if (src && typeof src === "object") {
    items = Object.keys(src).map(function(k){
      const v = src[k];
      if (v && typeof v === "object" && !Array.isArray(v)) {
        return Object.assign({ name: k }, v);
      }
      return { name: k, detail: v };
    });
  }

  return items.map(function(item, idx){
    const status = item && item.status != null
      ? item.status
      : (item && item.ok === true ? "ok" : (item && item.ok === false ? "fail" : "unknown"));

    const summary =
      item && item.summary != null ? item.summary :
      item && item.message != null ? item.message :
      item && item.detail != null ? item.detail :
      item && item.reason != null ? item.reason :
      "";

    return {
      key: String((item && (item.name || item.id || item.key || item.check)) || ("check-" + String(idx + 1))),
      name: String((item && (item.name || item.id || item.key || item.check)) || ("check-" + String(idx + 1))),
      status: String(status || "unknown"),
      summary: String(summary || ""),
      raw: item
    };
  }).sort(function(a, b){
    function rank(v) {
      const k = _healthStatusKind(v);
      if (k === "err") return 0;
      if (k === "warn") return 1;
      if (k === "ok") return 2;
      return 3;
    }
    const ra = rank(a.status);
    const rb = rank(b.status);
    if (ra !== rb) return ra - rb;
    return String(a.name || "").localeCompare(String(b.name || ""));
  });
}

function ServerHealthCheckRow({ item }) {
  const tone = _healthTone(item.status);
  const friendly = _healthFriendlyName(item.name);
  const showRawName = friendly.toLowerCase() !== String(item.name || "").toLowerCase();

  return h("details", {
    style: {
      border: "1px solid rgba(255,255,255,.07)",
      borderRadius: "12px",
      background: "rgba(255,255,255,.018)",
      overflow: "hidden"
    }
  }, [
    h("summary", {
      style: {
        listStyle: "none",
        cursor: "pointer",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: "12px",
        padding: "12px 14px"
      }
    }, [
      h("div", {
        style: {
          display: "flex",
          alignItems: "center",
          gap: "12px",
          minWidth: 0,
          flex: "1 1 auto"
        }
      }, [
        h("span", {
          style: {
            width: "10px",
            height: "10px",
            borderRadius: "999px",
            background: tone.dot,
            display: "inline-block",
            boxShadow: "0 0 0 1px rgba(255,255,255,.10)",
            flex: "0 0 auto"
          }
        }),
        h("div", { style: { minWidth: 0 } }, [
          h("div", {
            style: {
              fontWeight: 700,
              wordBreak: "break-word",
              whiteSpace: "normal"
            }
          }, friendly),
          showRawName ? h("div", {
            className: "muted",
            style: {
              fontSize: "12px",
              marginTop: "2px",
              fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
            }
          }, String(item.name || "")) : null
        ])
      ]),
      h(ServerHealthPill, { status: item.status })
    ]),
    h("div", {
      style: {
        padding: "0 14px 14px 14px",
        display: "grid",
        gap: "10px"
      }
    }, [
      item.summary ? h("div", {
        className: "muted",
        style: {
          whiteSpace: "pre-wrap",
          wordBreak: "break-word"
        }
      }, item.summary) : null,
      _healthMonospacePre(item.raw)
    ])
  ]);
}

function HealthView() {
  const api = useApi("api/server-health", { cacheMs: 2000, pollMs: 10000 });

  const loading = !!(api && api.loading);
  const err = api && api.error ? String(api.error) : "";
  const data = (api && api.data) || {};
  const payload = _serverHealthPayload(data);
  const rollup = _serverHealthRollup(data, payload);
  const checks = _serverHealthChecks(payload);

  const overall = String(
    (rollup && (rollup.overall || rollup.status)) ||
    payload.status ||
    (loading ? "loading" : (data && data.ok ? "ok" : "unknown"))
  );

  const generatedAt = String(
    (payload && (payload.generated_at || payload.updated_at || payload.checked_at || payload.created_at)) ||
    (data && data.generated_at) ||
    ""
  );

  const exists = !!(data && data.exists);
  const path = String((data && data.path) || "");

  const total = Number(
    (rollup && rollup.total) != null ? rollup.total :
    checks.length
  );
  const okCount = Number(
    (rollup && rollup.ok) != null ? rollup.ok :
    checks.filter(function(x){ return _healthStatusKind(x.status) === "ok"; }).length
  );
  const warnCount = Number(
    (rollup && rollup.warn) != null ? rollup.warn :
    checks.filter(function(x){ return _healthStatusKind(x.status) === "warn"; }).length
  );
  const failCount = Number(
    (rollup && rollup.fail) != null ? rollup.fail :
    checks.filter(function(x){ return _healthStatusKind(x.status) === "err"; }).length
  );
  const skipCount = Number(
    (rollup && rollup.skip) != null ? rollup.skip : 0
  );

  return h("div", { style: { display: "grid", gap: "14px" } }, [

    h("section", {
      style: _healthCardStyle({
        padding: "18px",
        border: _healthTone(overall).border,
        background: "linear-gradient(180deg, rgba(255,255,255,.04), rgba(255,255,255,.018))"
      })
    }, [
      h("div", {
        style: {
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: "14px",
          flexWrap: "wrap"
        }
      }, [
        h("div", { style: { minWidth: 0, flex: "1 1 420px" } }, [
          h("div", {
            style: { fontSize: "28px", fontWeight: 800, lineHeight: 1.05, marginBottom: "6px" }
          }, _healthTr("Serverhälsa", "Server Health")),
          h("div", {
            className: "muted",
            style: { maxWidth: "980px" }
          }, _healthTr(
            "Visar lokal hälsa från noden och samma typ av checks som rapporteras uppåt.",
            "Shows local node health and the same kind of checks that are reported upward."
          ))
        ]),
        h("div", {
          style: {
            display: "grid",
            justifyItems: "end",
            gap: "8px",
            minWidth: "220px"
          }
        }, [
          h(ServerHealthPill, { status: overall, large: true }),
          generatedAt ? h("div", {
            className: "muted",
            style: { fontSize: "12px" }
          }, generatedAt) : null
        ])
      ])
    ]),

    loading ? h("div", { style: _healthCardStyle() },
      _healthTr("Laddar serverhälsa…", "Loading server health…")
    ) : null,

    err ? h("div", {
      style: _healthCardStyle({
        border: "1px solid rgba(239,68,68,.35)",
        background: "rgba(239,68,68,.08)",
        color: "#fecaca"
      })
    }, err) : null,

    (!loading && !exists) ? h("div", {
      style: _healthCardStyle({
        border: "1px solid rgba(245,158,11,.35)",
        background: "rgba(245,158,11,.08)",
        color: "#fde68a"
      })
    }, [
      h("div", { style: { fontWeight: 800, marginBottom: "6px" } },
        _healthTr("Ingen node-health.json hittades", "No node-health.json found")
      ),
      h("div", { style: { opacity: .9 } }, path || "/opt/tak/takctl-state/node-health.json")
    ]) : null,

    h("div", {
      style: {
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
        gap: "10px"
      }
    }, [
      h(ServerHealthMetricCard, {
        label: _healthTr("Övergripande", "Overall"),
        value: h(ServerHealthPill, { status: overall }),
        hint: generatedAt ? generatedAt : undefined
      }),
      h(ServerHealthMetricCard, {
        label: "Checks",
        value: total,
        hint: exists ? _healthTr("Källa: lokal fil", "Source: local file") : undefined
      }),
      h(ServerHealthMetricCard, {
        label: "OK",
        value: okCount
      }),
      h(ServerHealthMetricCard, {
        label: _healthTr("Varningar", "Warnings"),
        value: warnCount
      }),
      h(ServerHealthMetricCard, {
        label: _healthTr("Fel", "Failures"),
        value: failCount
      }),
      h(ServerHealthMetricCard, {
        label: "Skip",
        value: skipCount
      })
    ]),

    h("section", { style: _healthCardStyle() }, [
      h("div", {
        style: {
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "12px",
          flexWrap: "wrap",
          marginBottom: "12px"
        }
      }, [
        h("div", {
          style: { fontSize: "18px", fontWeight: 800 }
        }, _healthTr("Kontroller", "Checks")),
        h("div", {
          className: "muted",
          style: { fontSize: "12px" }
        }, _healthTr("Varningar och fel visas först", "Warnings and failures are shown first"))
      ]),
      checks.length
        ? h("div", { style: { display: "grid", gap: "8px" } },
            checks.map(function(item){
              return h(ServerHealthCheckRow, { key: item.key, item: item });
            })
          )
        : h("div", { className: "muted" },
            _healthTr("Inga checks rapporterade.", "No checks reported.")
          )
    ]),

    h("details", { style: _healthCardStyle() }, [
      h("summary", {
        style: { cursor: "pointer", fontWeight: 800 }
      }, _healthTr("Visa rådata", "Show raw data")),
      h("div", { style: { marginTop: "12px", display: "grid", gap: "10px" } }, [
        h("div", {
          className: "muted",
          style: { fontSize: "12px" }
        }, path || "/opt/tak/takctl-state/node-health.json"),
        _healthMonospacePre(data)
      ])
    ])
  ]);
}
