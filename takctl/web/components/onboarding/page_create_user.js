/* global React */
(function () {
  var h = (window.h || React.createElement); window.h = h;
  const useState = React.useState;
  const useMemo = React.useMemo;
  const useEffect = React.useEffect;

  // shared onboarding helpers
  const lib = (window.TaksOnboarding && window.TaksOnboarding.lib) || null;
  function _needLib() { if (!lib) throw new Error('Missing onboarding lib: load components/onboarding/lib.js before page_create_user.js'); return lib; }
  function _colText(v){ return _needLib().colText(v); }
  function _splitCsv(s){ return _needLib().splitCsv(s); }

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
    const isNum = t === "number" || t === "int";
    return h(Field, { label: required ? (label + " *") : label },
      h("input", { type: isNum ? "number" : "text", value: String(value ?? ""), readOnly: ro, placeholder: ph, onChange: e => onChange(e.target.value) })
    );
  }

  function OnboardingCreateUserPage() {
    // Policy loading
    const [policyList, setPolicyList] = useState(null);
    const [policyId, setPolicyId] = useState("");
    const [policy, setPolicy] = useState(null);

    // Account
    const [username, setUsername] = useState("");
    const [password, setPassword] = useState("");
    const [admin, setAdmin] = useState(false);
    const [revealPassword, setRevealPassword] = useState(true);
    const [ttlSec, setTtlSec] = useState(600);

    // Identity + Groups + Config
    const [ident, setIdent] = useState({});
    const [groups, setGroups] = useState({ groups_rw: "46hvbat", groups_in: "", groups_out: "" });
    const [cfg, setCfg] = useState({});

    // Derived preview
    const [derived, setDerived] = useState(null);
    const [derivedErr, setDerivedErr] = useState("");
    const [deriveBusy, setDeriveBusy] = useState(false);

    // Result
    const [busy, setBusy] = useState(false);
    const [err, setErr] = useState("");
    const [result, setResult] = useState(null);

    function _setIdent(k, v) { setIdent(prev => Object.assign({}, prev, { [k]: v })); }
    function _setGroups(k, v) { setGroups(prev => Object.assign({}, prev, { [k]: v })); }
    function _setCfg(k, v) { setCfg(prev => Object.assign({}, prev, { [k]: v })); }

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

    const ctxForIdentity = useMemo(() => {
      const ctx = { policy_id: String(policyId || "") };
      const ident_fields = (policy && policy.identity_fields) || [];
      for (const f of ident_fields) {
        const k = String(f.key || "");
        if (!k) continue;
        ctx[k] = ident[k];
      }
      return ctx;
    }, [policyId, policy, ident]);

    // Derived preview (debounced)
    useEffect(() => {
      let alive = true;
      if (!policyId || !policy) return;

      // Only derive if required fields are present
      const ident_fields = (policy && policy.identity_fields) || [];
      for (const f of ident_fields) {
        if (!f || !f.required) continue;
        const k = String(f.key || "");
        const v = (k ? ctxForIdentity[k] : null);
        if (k && (v === undefined || v === null || String(v).trim() === "")) {
          setDerived(null);
          setDerivedErr("");
          return;
        }
      }

      const timer = setTimeout(() => {
        (async () => {
          setDeriveBusy(true);
          setDerivedErr("");
          try {
            const resp = await fetch("api/onboarding/derive", {
              method: "POST",
              headers: { "content-type": "application/json" },
              body: JSON.stringify({ policy_id: String(policyId), ctx: Object.assign({}, ctxForIdentity) }),
            });
            const j = await resp.json().catch(() => ({}));
            if (!resp.ok) throw new Error(j.error || j.detail || `HTTP ${resp.status}`);
            if (!alive) return;

            setDerived(j || null);

            // Auto-fill readonly-ish fields if empty (no stomping)
            const identOut = (j && j.identity) || {};
            setIdent(prev => {
              const out = Object.assign({}, prev);
              for (const kk of ["callsign", "team", "atak_role_type"]) {
                const nv = identOut[kk];
                if (nv !== undefined && nv !== null && String(nv).trim() !== "") {
                  if (out[kk] === undefined || out[kk] === null || String(out[kk]).trim() === "") {
                    out[kk] = nv;
                  }
                }
              }
              return out;
            });

          } catch (e) {
            if (!alive) return;
            setDerived(null);
            setDerivedErr(String((e && e.message) || e || "derive failed"));
          } finally {
            if (!alive) return;
            setDeriveBusy(false);
          }
        })();
      }, 250);

      return () => { alive = false; clearTimeout(timer); };
    }, [policyId, policy, ctxForIdentity]);

    async function doCreate() {
      setErr("");
      setResult(null);

      const u = String(username || "").trim();
      if (!u) { setErr("Username required."); return; }
      if (!policyId) { setErr("Policy required."); return; }

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
      try { await navigator.clipboard.writeText(String(txt || "")); } catch (e) {}
    }

    const policies = (policyList && policyList.policies) || [];
    const docUrl = (policy && policy._meta && policy._meta.has_doc)
      ? (`/api/onboarding/policies/${encodeURIComponent(policyId)}/doc`)
      : ((policyList && policyId) ? (policies.find(x => x.id === policyId)?.doc_url || "") : "");

    const derivedIdentity = (derived && derived.identity) || {};
    const derivedCtx = (derived && derived.ctx) || {};
    const derivedCallsign = derivedIdentity.callsign ? String(derivedIdentity.callsign) : "";
    const derivedTeam = derivedIdentity.team ? String(derivedIdentity.team) : "";
    const derivedRoleType = derivedIdentity.atak_role_type ? String(derivedIdentity.atak_role_type) : "";
    const derivedBnFal = derivedCtx.battalion_fal ? String(derivedCtx.battalion_fal) : "";
    const derivedCoFal = derivedCtx.company_fal ? String(derivedCtx.company_fal) : "";

    function applyDerivedToInputs() {
      setIdent(prev => {
        const out = Object.assign({}, prev);
        if (derivedCallsign) out.callsign = derivedCallsign;
        if (derivedTeam) out.team = derivedTeam;
        if (derivedRoleType) out.atak_role_type = derivedRoleType;
        return out;
      });
    }

    const cardUrl = (result && result.card_url) || "";
    const pwValue = (result && result.taks_identity && result.taks_identity.password && result.taks_identity.password.value) || "";

    return h("div", null,
      h("div", { className: "card-title" }, "Onboarding — Create user"),

      err && h("div", { className: "note", style: { marginBottom: "12px" } }, "ERR: ", err),

      // Policy picker
      h("div", { className: "box", style: { marginBottom: "12px" } },
        h("div", { className: "grid", style: { gridTemplateColumns: "minmax(220px, 360px) 1fr", gap: "12px", alignItems: "end" } },
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

      // Identity + Derived
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
          ),

          h("div", { className: "box", style: { marginTop: "12px" } },
            h("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "center", gap: "10px", flexWrap: "wrap" } },
              h("div", { style: { fontWeight: 600 } }, "Derived (policy grammar preview)"),
              h("div", { className: "muted", style: { fontSize: "12px" } }, deriveBusy ? "Deriving…" : (derived ? "Up to date" : "—"))
            ),
            derivedErr ? h("div", { className: "note", style: { marginTop: "10px" } }, "Derive error: ", derivedErr) : null,

            h("div", { className: "grid", style: { marginTop: "10px", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "12px" } },
              h(Field, { label: "Callsign" }, h("div", null, derivedCallsign || "—")),
              h(Field, { label: "Team (locationTeam)" }, h("div", null, derivedTeam || "—")),
              h(Field, { label: "atakRoleType" }, h("div", null, derivedRoleType || "—")),
              h(Field, { label: "Battalion FAL" }, h("div", null, derivedBnFal || "—")),
              h(Field, { label: "Company FAL" }, h("div", null, derivedCoFal || "—"))
            ),

            h("div", { style: { display: "flex", gap: "10px", flexWrap: "wrap", alignItems: "center", marginTop: "10px" } },
              (derivedCallsign || derivedTeam || derivedRoleType) ? h("button", { className: "btn", onClick: applyDerivedToInputs }, "Copy derived → identity fields") : null,
              derivedCallsign ? h("button", { className: "btn", onClick: () => copyText(derivedCallsign) }, "Copy callsign") : null,
              derivedTeam ? h("button", { className: "btn", onClick: () => copyText(derivedTeam) }, "Copy team") : null
            )
          )
        )
      ),

      // Account
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

      // Groups
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

      // Configuration (preview only)
      h("details", { open: false, className: "box", style: { marginBottom: "12px" } },
        h("summary", { style: { cursor: "pointer", fontWeight: 600 } }, "Configuration"),
        h("div", { style: { marginTop: "12px" } },
          h("div", { className: "note", style: { marginBottom: "10px" } },
            "UI preview only for now (not yet written into config.pref / packages)."
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

      // Action + Result
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

  window.TaksOnboardingPages = window.TaksOnboardingPages || {};
  window.TaksOnboardingPages.CreateUser = OnboardingCreateUserPage;
})();
