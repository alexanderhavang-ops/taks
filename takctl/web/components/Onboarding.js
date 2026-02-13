/* global React */
(function () {
  const h = React.createElement;

  function _colText(v) {
    if (v === null || v === undefined) return "—";
    const s = String(v);
    return s.length ? s : "—";
  }

  function _groups(u) {
    const gs = (u && u.groups) || [];
    return gs.length ? gs.join(",") : "—";
  }

  function _tail(act) {
    if (!act) return "—";
    const cs = act.callsign || "";
    const uid = act.uid || "";
    const t = (cs + " " + uid).trim();
    return t.length ? t : "—";
  }

  function _badgeForState(stateRaw) {
    const s = String(stateRaw || "").toLowerCase();
    let cls = "badge";
    if (s === "current") cls += " badge-current";
    else if (s === "recent") cls += " badge-recent";
    else if (s === "stale") cls += " badge-stale";
    else cls += " badge-never";

    return h("span", { className: cls }, _colText(stateRaw).toUpperCase());
  }

  function OnboardingTable({ rows }) {
    return h(
      "table",
      { className: "tbl" },
      h(
        "thead",
        null,
        h(
          "tr",
          null,
          h("th", null, "Username"),
          h("th", null, "Groups"),
          h("th", null, "Onboard"),
          h("th", null, "State"),
          h("th", null, "Age"),
          h("th", null, "Callsign / UID")
        )
      ),
      h(
        "tbody",
        null,
        (rows || []).map((u) => {
          const act = (u && u.activity) || {};
          return h(
            "tr",
            { key: (u.username || "") + ":" + (act.uid || "") },
            h("td", null, _colText(u.username)),
            h("td", null, _groups(u)),
            h("td", null, _colText((u.onboarding_status || "").toUpperCase())),
            h("td", null, _badgeForState(act.state)),
            h("td", null, _colText(act.age_human)),
            h("td", null, _tail(act))
          );
        })
      )
    );
  }

  function UnknownTable({ rows }) {
    return h(
      "table",
      { className: "tbl" },
      h(
        "thead",
        null,
        h(
          "tr",
          null,
          h("th", null, "Username"),
          h("th", null, "State"),
          h("th", null, "Age"),
          h("th", null, "Callsign"),
          h("th", null, "UID")
        )
      ),
      h(
        "tbody",
        null,
        (rows || []).map((e) => {
          return h(
            "tr",
            { key: (e.username || "") + ":" + (e.uid || "") },
            h("td", null, _colText(e.username)),
            h("td", null, _badgeForState(e.state)),
            h("td", null, _colText(e.age_human)),
            h("td", null, _colText(e.callsign)),
            h("td", null, _colText(e.uid))
          );
        })
      )
    );
  }

  function OnboardingView() {
    const data = useApi("api/onboarding/status", { cacheMs: 2000, pollMs: 10000 });

    const ok = data && data.ok;
    const d = (data && data.data) || {};
    const meta = d.meta || {};
    const summary = d.summary || {};
    const users = d.users || [];
    const unknown = d.unknown_endpoints || [];

    return h(
      "div",
      { className: "card" },
      h("div", { className: "card-title" }, "Onboarding"),
      h(
        "div",
        { className: "muted", style: { marginBottom: "8px" } },
        ok ? "Live view from /api/onboarding/status" : "Loading…"
      ),

      h(
        "div",
        { className: "muted", style: { marginBottom: "10px" } },
        `Users=${_colText(summary.total_users)}  ` +
          `Seen=${_colText(summary.cot_seen)}  ` +
          `Never=${_colText(summary.never_seen)}  ` +
          `Unknown=${_colText(summary.unknown_endpoints)}  ` +
          `DB=${meta.db_attached ? "attached" : "none"} (${_colText(meta.db_source)})`
      ),

      h(OnboardingTable, { rows: users }),

      unknown && unknown.length
        ? h(
            "div",
            { style: { marginTop: "18px" } },
            h("div", { className: "card-title", style: { fontSize: "14px" } }, "Unmanaged endpoints"),
            h(UnknownTable, { rows: unknown })
          )
        : null
    );
  }

  // export into global (expected by app.js)
  window.OnboardingView = OnboardingView;
})();
