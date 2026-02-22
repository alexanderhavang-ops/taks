/* global React */
(function () {
  var h = (window.h || React.createElement); window.h = h;

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

  function _deriveState(act) {
    if (!act) return "never";
    if (act.is_current === true) return "current";
    if (act.seen_recently === true) return "recent";
    return "stale";
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

  function _userUrls(username) {
    const u = encodeURIComponent(String(username || ""));
    const base = `api/onboarding/users/${u}`;
    return {
      generate: `${base}/generate`,
      card: `${base}/card`,
      // Option C QR endpoint (PNG). We append ?password=...&b=... in the UI.
      optc_qr_png_base: `${base}/packages/atak/package-creds/qr.png`,
      // Optional direct download of the creds package zip (also needs ?password=...)
      optc_zip_base: `${base}/packages/atak/package-creds/package.zip?regen=1`,
    };
  }

  function OptionCPanel({ username, urls }) {
    const [open, setOpen] = React.useState(false);
    const [pw, setPw] = React.useState("");
    const [bump, setBump] = React.useState(0);

    function qrUrl() {
      const p = (pw || "").trim();
      if (!p) return "";
      const b = bump || Date.now();
      return `${urls.optc_qr_png_base}?b=${encodeURIComponent(String(b))}&password=${encodeURIComponent(p)}`;
    }

    function zipUrl() {
      const p = (pw || "").trim();
      if (!p) return "";
      const b = bump || Date.now();
      return `${urls.optc_zip_base}&b=${encodeURIComponent(String(b))}&password=${encodeURIComponent(p)}`;
    }

    return h(
      "div",
      null,
      h("a", {
        className: "btn",
        href: "#",
        onClick: (e) => { e.preventDefault(); setOpen(!open); },
        title: "Option C: render an ATAK import QR that embeds username/password into certs/config.pref (experimental).",
      }, open ? "Option C (hide)" : "Option C"),

      open ? h(
        "div",
        {
          style: {
            marginTop: "10px",
            padding: "12px",
            border: "1px dashed #ddd",
            borderRadius: "12px",
            background: "#fff",
          }
        },
        h("div", { className: "card-title", style: { fontSize: "13px", marginBottom: "6px" } },
          "Option C (Experimental) — package import QR with embedded creds"
        ),
        h("div", { className: "muted", style: { fontSize: "12px", marginBottom: "10px", lineHeight: "1.35" } },
          "This renders a QR that imports an ATAK mission package where ",
          h("code", null, "certs/config.pref"),
          " includes ",
          h("code", null, "useAuth0"),
          ", ",
          h("code", null, "cacheCreds0"),
          ", ",
          h("code", null, "username0"),
          ", ",
          h("code", null, "password0"),
          ". Password is not stored by TAKS; it is only used to generate the package/QR."
        ),

        h("div", { style: { display: "flex", gap: "10px", alignItems: "flex-end", flexWrap: "wrap" } },
          h("label", { className: "muted", style: { fontSize: "12px", display: "flex", flexDirection: "column", gap: "6px" } },
            "Password (for " + _colText(username) + ")",
            h("input", {
              type: "password",
              value: pw,
              onChange: (e) => setPw(e.target.value),
              placeholder: "Enter enrollment password",
              style: {
                padding: "8px 10px",
                border: "1px solid #ddd",
                borderRadius: "10px",
                minWidth: "260px",
              }
            })
          ),

          h("a", {
            className: "btn",
            href: "#",
            onClick: (e) => { e.preventDefault(); setBump(Date.now()); },
            title: "Bump cache + regenerate QR image",
            style: { opacity: (pw || "").trim() ? 1 : 0.5, pointerEvents: (pw || "").trim() ? "auto" : "none" }
          }, "Generate QR"),

          (pw || "").trim()
            ? h("a", {
                className: "btn",
                href: zipUrl(),
                target: "_blank",
                rel: "noopener noreferrer",
                title: "Download the creds-embedded package.zip (debug)",
              }, "Download zip")
            : null
        ),

        (pw || "").trim()
          ? h("div", { style: { marginTop: "12px", display: "flex", justifyContent: "center" } },
              h("img", {
                alt: "ATAK package-creds QR",
                src: qrUrl(),
                style: { width: "280px", height: "280px", imageRendering: "pixelated" }
              })
            )
          : h("div", { className: "muted", style: { fontSize: "12px", marginTop: "10px" } },
              "Enter a password and click “Generate QR”."
            )
      ) : null
    );
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
          h("th", null, "Callsign / UID"),
          h("th", null, "Onboarding")
        )
      ),
      h(
        "tbody",
        null,
        (rows || []).map((u) => {
          const act = (u && u.activity) || null;
          const state = _deriveState(act);
          const key = (u.username || "") + ":" + ((act && act.uid) || "");

          const urls = _userUrls(u.username);

          return h(
            "tr",
            { key },
            h("td", null, _colText(u.username)),
            h("td", null, _groups(u)),
            h("td", null, _colText((u.onboarding_status || "").toUpperCase())),
            h("td", null, _badgeForState(state)),
            h("td", null, _colText(act ? act.age_human : "—")),
            h("td", null, _tail(act)),
            h(
              "td",
              null,
              h("div", { style: { display: "flex", gap: "8px", flexWrap: "wrap", alignItems: "center" } },
                h("a", {
                  className: "btn",
                  href: urls.generate,
                  target: "_blank",
                  rel: "noopener noreferrer",
                  title: "Generate onboarding data (paths A/B/C + iTAK/WinTAK) then proceed to the card",
                }, "Generate"),
                h("a", {
                  className: "btn",
                  href: urls.card,
                  target: "_blank",
                  rel: "noopener noreferrer",
                  title: "Open the onboarding card (QR codes + links)",
                }, "Card"),
                h(OptionCPanel, { username: u.username, urls })
              )
            )
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
          const state = (e && (e.is_current === true ? "current" : (e.seen_recently === true ? "recent" : "stale"))) || "—";
          return h(
            "tr",
            { key: (e.username || "") + ":" + (e.uid || "") },
            h("td", null, _colText(e.username)),
            h("td", null, _badgeForState(state)),
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

  window.OnboardingView = OnboardingView;
})();
