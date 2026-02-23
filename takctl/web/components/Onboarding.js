/* global React */
(function () {
  var h = (window.h || React.createElement); window.h = h;

  const useState = React.useState;
  const useMemo = React.useMemo;
  const useEffect = React.useEffect;

  // shared onboarding helpers
  const lib = (window.TaksOnboarding && window.TaksOnboarding.lib) || null;
  function _needLib() { if (!lib) throw new Error('Missing onboarding lib: load components/onboarding/lib.js before Onboarding.js'); return lib; }
  function _colText(v){ return _needLib().colText(v); }
  function _groups(u){ return _needLib().groups(u); }
  function _tail(act){ return _needLib().tail(act); }
  function _deriveState(act){ return _needLib().deriveState(act); }
  function _badgeForState(stateRaw){ return _needLib().badgeForState(stateRaw); }
  function _userUrls(username){ return _needLib().userUrls(username); }
  function _parseHashSub(){ return _needLib().parseHashSub(); }
  function _setHashSub(sub){ return _needLib().setHashSub(sub); }
  function _splitCsv(s){ return _needLib().splitCsv(s); }

  // ---------------------------------------------------------------------------
  // tables (List)
  // ---------------------------------------------------------------------------
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
              h(
                "div",
                { style: { display: "flex", gap: "8px", flexWrap: "wrap", alignItems: "center" } },
                h(
                  "a",
                  {
                    className: "btn",
                    href: urls.card,
                    target: "_blank",
                    rel: "noopener noreferrer",
                    title: "Open the onboarding card (QR codes + links)",
                  },
                  "Card"
                )
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
          const state =
            (e && (e.is_current === true ? "current" : (e.seen_recently === true ? "recent" : "stale"))) || "—";
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

  function OnboardingListPage() {
    const data = useApi("api/onboarding/status", { cacheMs: 2000, pollMs: 10000 });

    const ok = data && data.ok;
    const d = (data && data.data) || {};
    const meta = d.meta || {};
    const summary = d.summary || {};
    const users = d.users || [];
    const unknown = d.unknown_endpoints || [];

    return h(
      "div",
      null,
      h("div", { className: "card-title" }, "Onboarding — List"),
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

  // ---------------------------------------------------------------------------
  // Create user (single-user UI smoke test)
  // ---------------------------------------------------------------------------

  function OnboardingCreateUserPage() {
    // -------------------------------------------------------------------------
    // Policy loading
    // -------------------------------------------------------------------------
    const [policyList, setPolicyList] = useState(null);  // response from /policies
    const [policyId, setPolicyId] = useState("");        // selected
    const [policy, setPolicy] = useState(null);          // full policy.json

    // -------------------------------------------------------------------------
    // Account (always same)
    // -------------------------------------------------------------------------
    const [username, setUsername] = useState("");
    const [password, setPassword] = useState("");
    const [admin, setAdmin] = useState(false);
    const [revealPassword, setRevealPassword] = useState(true);
    const [ttlSec, setTtlSec] = useState(600);

    // -------------------------------------------------------------------------
    // Identity + Groups + Config (policy-driven)
    // Stored as generic dicts keyed by policy field keys.
    // -------------------------------------------------------------------------
    const [ident, setIdent] = useState({});
    const [groups, setGroups] = useState({ groups_rw: "46hvbat", groups_in: "", groups_out: "" });
    const [cfg, setCfg] = useState({});

    // Result
    const [busy, setBusy] = useState(false);
    const [err, setErr] = useState("");
    const [result, setResult] = useState(null);

    function _setIdent(k, v) { setIdent(prev => Object.assign({}, prev, { [k]: v })); }
    function _setGroups(k, v) { setGroups(prev => Object.assign({}, prev, { [k]: v })); }
    function _setCfg(k, v) { setCfg(prev => Object.assign({}, prev, { [k]: v })); }

    function Field({ label, children }) {
      return h(
        "div",
        { style: { display: "flex", flexDirection: "column", gap: "6px" } },
        h("div", { className: "muted", style: { fontSize: "12px" } }, label),
        children
      );
    }

    function RenderField({ f, value, onChange }) {
      const t = String((f && f.type) || "text").toLowerCase();
      const required = !!(f && f.required);
            const ro = !!(f && f.readonly);
const ph = (f && f.key) ? String(f.key) : "";
      const label = (f && f.label) ? String(f.label) : ph;

      if (t === "select") {
        const opts = (f && f.options) || [];
        return h(Field, { label: required ? (label + " *") : label },
          h("select", { value: String(value ?? ""), disabled: ro, onChange: e => onChange(e.target.value) },
            opts.map(o => h("option", { key: String(o), value: String(o) }, String(o)))
          )
        );
      }
      if (t === "bool") {
        return h("label", { style: { display: "flex", gap: "10px", alignItems: "center" } },
          h("input", { type: "checkbox", checked: !!value, disabled: ro, onChange: e => onChange(!!e.target.checked) }),
          h("span", null, required ? (label + " *") : label)
        );
      }
      if (t === "csv") {
        return h(Field, { label: required ? (label + " *") : label },
          h("input", { type: "text", value: String(value ?? ""), readOnly: ro, placeholder: "comma,separated,groups", onChange: e => onChange(e.target.value) })
        );
      }
      // default text/number-ish
      const isNum = t === "number" || t === "int";
      return h(Field, { label: required ? (label + " *") : label },
        h("input", { type: isNum ? "number" : "text", value: String(value ?? ""), readOnly: ro, placeholder: ph, onChange: e => onChange(e.target.value) })
      );
    }

    // Load policies list once
    useEffect(() => {
      let alive = true;
      (async () => {
        try {
          const r = await fetch("api/onboarding/policies");
          const j = await r.json();
          if (!r.ok) throw new Error(j.detail || ("HTTP " + r.status));
          if (!alive) return;
          setPolicyList(j || null);

          const defId = (j && j.default_policy_id) ? String(j.default_policy_id) : "";
          setPolicyId(defId || "");
        } catch (e) {
          if (!alive) return;
          setErr("Policy list failed: " + String((e && e.message) || e));
        }
      })();
      return () => { alive = false; };
    }, []);

    // Load active policy when policyId changes
    useEffect(() => {
      let alive = true;
      if (!policyId) return;
      (async () => {
        try {
          const r = await fetch(`api/onboarding/policies/${encodeURIComponent(policyId)}`);
          const j = await r.json();
          if (!r.ok) throw new Error(j.detail || ("HTTP " + r.status));
          if (!alive) return;
          setPolicy(j || null);

          // Seed defaults into form dicts (only if not already set)
          const ident_fields = (j && j.identity_fields) || [];
          const group_fields = (j && j.group_fields) || [];
          const cfg_fields   = (j && j.config_fields) || [];

          setIdent(prev => {
            const out = Object.assign({}, prev);
            for (const f of ident_fields) {
              const k = String(f.key || "");
              if (!k) continue;
              if (out[k] === undefined || out[k] === null || out[k] === "") {
                out[k] = (f.default !== undefined) ? f.default : "";
              }
            }
            // Always keep policy_id in ctx via policyId, so no need to store it here.
            return out;
          });

          setGroups(prev => {
            const out = Object.assign({}, prev);
            for (const f of group_fields) {
              const k = String(f.key || "");
              if (!k) continue;
              if (out[k] === undefined || out[k] === null) {
                out[k] = (f.default !== undefined) ? f.default : "";
              }
            }
            return out;
          });

          setCfg(prev => {
            const out = Object.assign({}, prev);
            for (const f of cfg_fields) {
              const k = String(f.key || "");
              if (!k) continue;
              if (out[k] === undefined || out[k] === null || out[k] === "") {
                out[k] = (f.default !== undefined) ? f.default : "";
              }
            }
            return out;
          });

        } catch (e) {
          if (!alive) return;
          setErr("Policy load failed: " + String((e && e.message) || e));
        }
      })();
      return () => { alive = false; };
    }, [policyId]);

    async function doCreate() {
      setErr("");
      setResult(null);

      const u = String(username || "").trim();
      if (!u) { setErr("Username required."); return; }
      if (!policyId) { setErr("Policy required."); return; }

      // Build ctx from policy identity fields only (strict + predictable).
      // Note: configuration is shown in UI but not sent yet (avoid backend 422 until wired).
      const ctx = { policy_id: String(policyId) };
      const ident_fields = (policy && policy.identity_fields) || [];
      for (const f of ident_fields) {
        const k = String(f.key || "");
        if (!k) continue;
        const v = ident[k];
        if (f.required && (v === undefined || v === null || String(v).trim() === "")) {
          setErr(`Missing required field: ${String(f.label || k)}`);
          return;
        }
        ctx[k] = v;
      }

      const body = {
        password: String(password || "").trim() || null,
        admin: !!admin,
        groups_rw: _splitCsv(groups.groups_rw),
        groups_in: _splitCsv(groups.groups_in),
        groups_out: _splitCsv(groups.groups_out),
        ctx,
        paths: { B: true, itak: true, wintak: true },
        endpoints: {},
        ttl_sec: Number(ttlSec || 600),
        reveal_password: !!revealPassword,
      };

      setBusy(true);
      try {
        const resp = await fetch(`api/onboarding/users/${encodeURIComponent(u)}/create`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(body),
        });
        const j = await resp.json().catch(() => ({}));
        if (!resp.ok) throw new Error(j.detail || `HTTP ${resp.status}`);
        setResult(j || {});
      } catch (e) {
        setErr(String((e && e.message) || e || "Failed"));
      } finally {
        setBusy(false);
      }
    }

    async function copyText(txt) {
      try {
        await navigator.clipboard.writeText(String(txt || ""));
      } catch (e) {
        // fallback: ignore
      }
    }

    const cardUrl = (result && result.card_url) || "";
    const pwValue = (result && result.taks_identity && result.taks_identity.password && result.taks_identity.password.value) || "";

    const policies = (policyList && policyList.policies) || [];
    const docUrl = (policy && policy._meta && policy._meta.has_doc)
      ? (`/api/onboarding/policies/${encodeURIComponent(policyId)}/doc`)
      : ((policyList && policyId) ? (policies.find(x => x.id === policyId)?.doc_url || "") : "");

    return h("div", null,
      h("div", { className: "card-title" }, "Onboarding — Create user"),

      err && h("div", { className: "note", style: { marginBottom: "12px" } }, "ERR: ", err),

      // Policy picker
      h("div", { className: "box", style: { marginBottom: "12px" } },
        h("div", { className: "grid", style: { gridTemplateColumns: "minmax(220px, 320px) 1fr", gap: "12px", alignItems: "end" } },
          h(Field, { label: "Policy" },
            h("select", { value: String(policyId || ""), onChange: e => setPolicyId(e.target.value) },
              policies.map(p => h("option", { key: p.id, value: p.id }, `${p.name} (${p.id})`))
            )
          ),
          h("div", { className: "muted", style: { fontSize: "12px" } },
            policy ? (`v${_colText(policy.version)} • source=${_colText(policy._meta && policy._meta.source)}`) : "Loading policy…",
            docUrl ? h("span", null, " • ", h("a", { href: docUrl, target: "_blank", rel: "noopener noreferrer" }, "Open policy PDF")) : null
          )
        )
      ),

      // ACCOUNT
      h("details", { open: true, className: "box", style: { marginBottom: "12px" } },
        h("summary", { style: { cursor: "pointer", fontWeight: 600 } }, "Account"),
        h("div", { style: { marginTop: "12px" } },
          h("div", { className: "grid", style: { gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: "12px" } },
            h(Field, { label: "Username *" }, h("input", { type: "text", value: username, placeholder: "e.g. admin.46hvbat", onChange: e => setUsername(e.target.value) })),
            h(Field, { label: "Password (optional)" }, h("input", { type: "text", value: password, placeholder: "leave blank for TAKS-generated", onChange: e => setPassword(e.target.value) })),
            h(Field, { label: "TTL (sec)" }, h("input", { type: "number", value: ttlSec, onChange: e => setTtlSec(e.target.value) })),
          ),
          h("div", { style: { display: "flex", gap: "20px", alignItems: "center", flexWrap: "wrap", marginTop: "12px" } },
            h("label", null, h("input", { type: "checkbox", checked: admin, onChange: e => setAdmin(e.target.checked) }), " Admin"),
            h("label", null, h("input", { type: "checkbox", checked: revealPassword, onChange: e => setRevealPassword(e.target.checked) }), " Reveal password on card"),
          )
        )
      ),

      // IDENTITY (policy-driven)
      h("details", { open: true, className: "box", style: { marginBottom: "12px" } },
        h("summary", { style: { cursor: "pointer", fontWeight: 600 } }, "Identity"),
        h("div", { style: { marginTop: "12px" } },
          h("div", { className: "grid", style: { gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "12px" } },
            ((policy && policy.identity_fields) || []).map(f =>
              h(RenderField, {
                key: String(f.key || ""),
                f,
                value: ident[String(f.key || "")],
                onChange: (v) => _setIdent(String(f.key || ""), v),
              })
            )
          )
        )
      ),

      // GROUPS (policy-driven: rw/in/out)
      h("details", { open: true, className: "box", style: { marginBottom: "12px" } },
        h("summary", { style: { cursor: "pointer", fontWeight: 600 } }, "Groups"),
        h("div", { style: { marginTop: "12px" } },
          h("div", { className: "muted", style: { fontSize: "12px", marginBottom: "10px" } },
            "Marti-style groups: RW=read+write, IN=send-only, OUT=read-only."
          ),
          h("div", { className: "grid", style: { gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: "12px" } },
            ((policy && policy.group_fields) || []).map(f =>
              h(RenderField, {
                key: String(f.key || ""),
                f,
                value: groups[String(f.key || "")],
                onChange: (v) => _setGroups(String(f.key || ""), v),
              })
            )
          )
        )
      ),

      // CONFIG (policy-driven UI; not applied yet)
      h("details", { open: false, className: "box", style: { marginBottom: "12px" } },
        h("summary", { style: { cursor: "pointer", fontWeight: 600 } }, "Configuration"),
        h("div", { style: { marginTop: "12px" } },
          h("div", { className: "note", style: { marginBottom: "10px" } },
            "UI preview only for now (not yet written into config.pref / packages). Once single-user is stable, we’ll wire these settings into the generated artifacts."
          ),
          h("div", { className: "grid", style: { gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: "12px" } },
            ((policy && policy.config_fields) || []).map(f =>
              h(RenderField, {
                key: String(f.key || ""),
                f,
                value: cfg[String(f.key || "")],
                onChange: (v) => _setCfg(String(f.key || ""), v),
              })
            )
          )
        )
      ),

      // ACTION + RESULT
      h("div", { style: { display: "flex", gap: "12px", alignItems: "center", flexWrap: "wrap" } },
        h("button", { onClick: doCreate, disabled: busy }, busy ? "Creating…" : "Create user")
      ),

      result && h("div", { className: "note", style: { marginTop: "12px" } },
        h("div", { style: { display: "flex", gap: "10px", alignItems: "center", flexWrap: "wrap" } },
          h("b", null, "Card URL:"),
          cardUrl ? h("a", { href: cardUrl, target: "_blank", rel: "noopener noreferrer" }, cardUrl) : "—",
          cardUrl ? h("button", { className: "btn", onClick: () => copyText(cardUrl) }, "Copy") : null
        ),
        h("div", { style: { display: "flex", gap: "10px", alignItems: "center", flexWrap: "wrap", marginTop: "8px" } },
          h("b", null, "Password:"),
          pwValue || "—",
          pwValue ? h("button", { className: "btn", onClick: () => copyText(pwValue) }, "Copy") : null
        )
      )
    );
  }


  // ---------------------------------------------------------------------------
  // Import users (placeholder)
  // ---------------------------------------------------------------------------
  function OnboardingImportUsersPage() {
    return h(
      "div",
      null,
      h("div", { className: "card-title" }, "Onboarding — Import users file"),
      h(
        "div",
        { className: "muted" },
        "Next step: upload Excel/CSV → preview grid → confirm → bulk create."
      ),
      h(
        "div",
        { className: "note", style: { marginTop: "10px" } },
        "We’ll define the exact column grammar from policy/ctx once single-user is solid."
      )
    );
  }

  // ---------------------------------------------------------------------------
  // Root: left menu + subpage routing
  // ---------------------------------------------------------------------------
  function SideItem({ id, cur, label, onClick }) {
    const on = (String(cur) === String(id));
    const cls = "btn";
    return h(
      "button",
      {
        className: cls,
        onClick,
        style: {
          width: "100%",
          justifyContent: "flex-start",
          opacity: on ? 1 : 0.85,
          borderColor: on ? "#3a3a3a" : undefined,
        },
      },
      label
    );
  }

  function OnboardingView() {
    const [sub, setSub] = useState(_parseHashSub());

    useEffect(() => {
      function onHash() { setSub(_parseHashSub()); }
      window.addEventListener("hashchange", onHash);
      return () => window.removeEventListener("hashchange", onHash);
    }, []);

    function nav(to) {
      setSub(to);
      _setHashSub(to);
    }

    let page = null;
    if (sub === "create") page = h(OnboardingCreateUserPage);
    else if (sub === "import") page = h(OnboardingImportUsersPage);
    else page = h(OnboardingListPage);

    return h(
      "div",
      { className: "card" },
      h(
        "div",
        { style: { display: "flex", gap: "14px", alignItems: "stretch" } },

        // left menu
        h(
          "div",
          { style: { width: "220px", flex: "0 0 auto" } },
          h("div", { className: "card-title" }, "Onboarding"),
          h("div", { className: "muted", style: { marginBottom: "10px" } }, "Section"),
          h(
            "div",
            { style: { display: "flex", flexDirection: "column", gap: "8px" } },
            h(SideItem, { id: "list", cur: sub, label: "List", onClick: () => nav("list") }),
            h(SideItem, { id: "create", cur: sub, label: "Create user", onClick: () => nav("create") }),
            h(SideItem, { id: "import", cur: sub, label: "Import users file", onClick: () => nav("import") })
          )
        ),

        // main pane
        h("div", { style: { flex: "1 1 auto", minWidth: "0" } }, page)
      )
    );
  }

  window.OnboardingView = OnboardingView;
})();
