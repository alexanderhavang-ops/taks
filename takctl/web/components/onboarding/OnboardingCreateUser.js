/* global React */
(function () {
  var h = (window.h || React.createElement); window.h = h;

  const useState = React.useState;
  const useMemo = React.useMemo;
  const useEffect = React.useEffect;

  const lib = (window.TaksOnboarding && window.TaksOnboarding.lib) || null;
  function _needLib() { if (!lib) throw new Error('Missing onboarding lib: load components/onboarding/lib.js before OnboardingCreateUser.js'); return lib; }
  function _colText(v){ return _needLib().colText(v); }
  function _splitCsv(s){ return _needLib().splitCsv(s); }

  const badge = (window.TaksOnboarding && window.TaksOnboarding.createUser && window.TaksOnboarding.createUser.badge) || null;
  function _needBadge(){ if (!badge) throw new Error("Missing create_user/badge.js"); return badge; }

  const t = (window.t && typeof window.t === "function") ? window.t : (k) => String(k || "");

  const LP = { "data-lpignore": "true", autoComplete: "off" };
  function _norm(s){ return String(s || "").trim(); }

  function _labelForKey(k, fallbackLabel) {
    const key = String(k || "");
    if (!key) return String(fallbackLabel || "");
    if (key === "n") {
      const v = t("field.number");
      return (v && v !== "field.number") ? v : (fallbackLabel || "Number");
    }
    const tk = "field." + key;
    const v = t(tk);
    if (v && v !== tk) return v;
    return String(fallbackLabel || key);
  }

  function Field({ label, children }) {
    return h("div", { style: { display: "flex", flexDirection: "column", gap: "6px" } },
      h("div", { className: "muted", style: { fontSize: "12px" } }, label),
      children
    );
  }

  function RenderField({ f, value, onChange }) {
    const ty = String((f && f.type) || "text").toLowerCase();
    const required = !!(f && f.required);
    const ro = !!(f && f.readonly);
    const ph = (f && f.key) ? String(f.key) : "";
    const rawLabel = (f && f.label) ? String(f.label) : ph;
    const k = String((f && f.key) || "");
    const label = _labelForKey(k, rawLabel);

    if (ty === "select") {
      const opts = (f && f.options) || [];
      return h(Field, { label: required ? (label + " *") : label },
        h("select", Object.assign({}, LP, { value: String(value ?? ""), disabled: ro, onChange: e => onChange(e.target.value) }),
          opts.map(o => h("option", { key: String(o), value: String(o) }, String(o)))
        )
      );
    }
    const isNum = ty === "number" || ty === "int";
    return h(Field, { label: required ? (label + " *") : label },
      h("input", Object.assign({}, LP, { type: isNum ? "number" : "text", value: String(value ?? ""), readOnly: ro, placeholder: ph, onChange: e => onChange(e.target.value) }))
    );
  }

  function Tabs({ value, onChange, tabs }) {
    return h("div", { style: { margin: "6px 0 14px 0" } },
      h("div", {
        style: {
          display: "flex",
          gap: "2px",
          flexWrap: "wrap",
          borderBottom: "1px solid rgba(255,255,255,0.10)",
          paddingBottom: "0px"
        }
      },
      tabs.map(tt => {
        const active = value === tt.id;
        return h("button", {
          key: tt.id,
          type: "button",
          onClick: () => onChange(tt.id),
          style: {
            background: active ? "rgba(255,255,255,0.06)" : "transparent",
            color: "inherit",
            border: "1px solid rgba(255,255,255,0.10)",
            borderBottom: active ? "1px solid transparent" : "1px solid rgba(255,255,255,0.10)",
            padding: "8px 12px",
            borderTopLeftRadius: "10px",
            borderTopRightRadius: "10px",
            borderBottomLeftRadius: "0px",
            borderBottomRightRadius: "0px",
            fontSize: "13px",
            cursor: "pointer",
            marginBottom: "-1px",
            opacity: active ? 1 : 0.9
          }
        }, tt.label);
      }))
    );
  }

  function OnboardingCreateUserPage() {
    const [policyList, setPolicyList] = useState(null);
    const [policyId, setPolicyId] = useState("");
    const [policy, setPolicy] = useState(null);

    const [tab, setTab] = useState("identity");

    // Account
    const [username, setUsername] = useState("");
    const [password, setPassword] = useState("");
    const [admin, setAdmin] = useState(false);

    // Advanced
    const [revealPassword, setRevealPassword] = useState(true);
    const [ttlSec, setTtlSec] = useState(600);

    // Identity + Groups + Config
    const [ident, setIdent] = useState({});
    const [groups, setGroups] = useState({ groups_rw: "46hvbat", groups_in: "", groups_out: "" });
    const [cfg, setCfg] = useState({});

    // Derived preview + single editable override: callsign
    const [derived, setDerived] = useState(null);
    const [derivedErr, setDerivedErr] = useState("");
    const [deriveBusy, setDeriveBusy] = useState(false);
    const _deriveAbortRef = React.useRef(null);
    const _deriveLastKeyRef = React.useRef("");

    const [callsignEdit, setCallsignEdit] = useState("");

    // Result
    const [busy, setBusy] = useState(false);
    const [err, setErr] = useState("");
    const [result, setResult] = useState(null);

    function _setIdent(k, v) { setIdent(prev => Object.assign({}, prev, { [k]: v })); }
    function _setGroups(k, v) { setGroups(prev => Object.assign({}, prev, { [k]: v })); }
    function _setCfg(k, v) { setCfg(prev => Object.assign({}, prev, { [k]: v })); }

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
                if (f.default !== undefined) out[k] = f.default;
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

    const ctxForDerive = useMemo(() => {
      const ctx = {};
      const ident_fields = (policy && policy.identity_fields) || [];
      for (const f of ident_fields) {
        const k = String(f.key || "");
        if (!k) continue;
        ctx[k] = ident[k];
      }
      return ctx;
    }, [policy, ident]);

    function _deriveKey(policyId, ctx) {
      const o = { policy_id: String(policyId || "") };
      for (const k of ["battalion", "battalion_fala", "company", "platoon", "n", "team_color"]) {
        o[k] = String((ctx && ctx[k]) || "");
      }
      return JSON.stringify(o);
    }

    // Debounced derive
    useEffect(() => {
      const battalion = _norm(ctxForDerive && ctxForDerive.battalion);
      const battalion_fala = _norm(ctxForDerive && ctxForDerive.battalion_fala);
      const company = _norm(ctxForDerive && ctxForDerive.company);
      const platoon = _norm(ctxForDerive && ctxForDerive.platoon);
      const n = _norm(ctxForDerive && ctxForDerive.n);
      const team_color = _norm(ctxForDerive && ctxForDerive.team_color);

      if (!policyId || !company || !platoon || !n) {
        setDerived(null);
        setDerivedErr("");
        setDeriveBusy(false);
        _deriveLastKeyRef.current = "";
        if (_deriveAbortRef.current) { try { _deriveAbortRef.current.abort(); } catch (e) {} }
        _deriveAbortRef.current = null;
        return;
      }

      const key = _deriveKey(policyId, { battalion, battalion_fala, company, platoon, n, team_color });
      if (key === _deriveLastKeyRef.current) return;

      const timer = setTimeout(() => {
        (async () => {
          _deriveLastKeyRef.current = key;

          if (_deriveAbortRef.current) { try { _deriveAbortRef.current.abort(); } catch (e) {} }
          const ac = new AbortController();
          _deriveAbortRef.current = ac;

          setDeriveBusy(true);
          setDerivedErr("");
          try {
            const resp = await fetch("/api/onboarding/derive", {
              method: "POST",
              headers: { "content-type": "application/json" },
              body: JSON.stringify({
                policy_id: String(policyId),
                ctx: { battalion, battalion_fala, company, platoon, n, team_color }
              }),
              signal: ac.signal,
            });
            const data = await resp.json().catch(() => ({}));
            if (!resp.ok) throw new Error(data.error || data.detail || ("HTTP " + resp.status));

            setDerived(data || null);

            // Source changed => overwrite callsign override (temporary override behavior)
            const di = (data && data.identity) || {};
            setCallsignEdit(di.callsign ? String(di.callsign) : "");

          } catch (e) {
            if (e && e.name === "AbortError") return;
            setDerived(null);
            setDerivedErr(String((e && e.message) || e || "derive failed"));
          } finally {
            setDeriveBusy(false);
          }
        })();
      }, 450);

      return () => { clearTimeout(timer); };
    }, [
      policyId,
      ctxForDerive && ctxForDerive.battalion,
      ctxForDerive && ctxForDerive.battalion_fala,
      ctxForDerive && ctxForDerive.company,
      ctxForDerive && ctxForDerive.platoon,
      ctxForDerive && ctxForDerive.n,
      ctxForDerive && ctxForDerive.team_color
    ]);

    async function doCreate() {
      setErr("");
      setResult(null);

      const u = _norm(username);
      if (!u) { setErr("Username required."); return; }
      if (!policyId) { setErr("Policy required."); return; }

      const ctx = { policy_id: String(policyId) };
      const ident_fields = (policy && policy.identity_fields) || [];
      for (const f of ident_fields) {
        const k = String(f.key || "");
        if (!k) continue;
        const v = ident[k];
        if (f.required && (v === undefined || v === null || String(v).trim() === "")) {
          setErr(`Missing required field: ${String(_labelForKey(k, f.label || k))}`);
          return;
        }
        ctx[k] = v;
      }

      // Single callsign override (exactly once)
      if (_norm(callsignEdit)) ctx.callsign = String(callsignEdit);

      // NOTE: config_fields wiring later (atak_role + remarks)
      // We still carry cfg in body for future, but backend currently ignores it.
      // ctx._client_profile = cfg;  // keep for later when you want it

      const body = {
        password: _norm(password) || null,
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

    const policies = (policyList && policyList.policies) || [];
    const activePolicyName = policy ? `${policy.name} (${policyId})` : (policyId ? policyId : "—");

    const docUrl = (policy && policy._meta && policy._meta.has_doc)
      ? (`/api/onboarding/policies/${encodeURIComponent(policyId)}/doc`)
      : ((policyList && policyId) ? (policies.find(x => x.id === policyId)?.doc_url || "") : "");

    // Badge content
    const company = _norm(ctxForDerive && ctxForDerive.company);
    const platoon = _norm(ctxForDerive && ctxForDerive.platoon);
    const n = _norm(ctxForDerive && ctxForDerive.n);
    const battalion = _norm(ctxForDerive && ctxForDerive.battalion);

    const badgePrimary = _norm(callsignEdit) || "—";
    const row2 = battalion ? `${battalion} HVBAT` : "—";

    const statusText = deriveBusy ? "…" : (derived ? t("policy.up_to_date") : "—");

    const identityFieldsToRender = ((policy && policy.identity_fields) || []);

    const cardUrl = (result && result.card_url) || "";
    const pwValue = (result && result.taks_identity && result.taks_identity.password && result.taks_identity.password.value) || "";

    return h("div", { className: "ob-create-root" },
      h("div", { className: "card-title" }, t("page.onboarding_create")),

      err ? h("div", { className: "note", style: { marginBottom: "12px" } }, "ERR: ", err) : null,

      h("div", { className: "box", style: { marginBottom: "12px" } },
        h("div", { style: { display: "flex", justifyContent: "space-between", gap: "12px", flexWrap: "wrap", alignItems: "center" } },
          h("div", null,
            h("div", { style: { fontWeight: 600 } }, t("policy.label")),
            h("div", { className: "muted", style: { fontSize: "12px", marginTop: "2px" } },
              policy ? (`${activePolicyName} • v${_colText(policy.version)} • source=${_colText(policy._meta && policy._meta.source)}`) : (policyId ? activePolicyName : "Loading policy…"),
              docUrl ? h("span", null, " • ", h("a", { href: docUrl, target: "_blank", rel: "noopener noreferrer" }, t("policy.open_pdf"))) : null
            )
          ),
          h("div", { className: "muted", style: { fontSize: "12px" } }, t("policy.node_global"))
        )
      ),

      h(_needBadge().NameBadge, {
        callsign: badgePrimary,
        row2: row2,
        teamColor: _norm(ctxForDerive && ctxForDerive.team_color),
        statusText: statusText
      }),

      h("div", { className: "box" },
        h(Tabs, {
          value: tab,
          onChange: setTab,
          tabs: [
            { id: "identity", label: t("tab.identity") },
            { id: "account", label: t("tab.account") },
            { id: "advanced", label: t("tab.advanced") }
          ]
        }),

        (tab === "identity") ? h("div", null,
          h("div", { style: { fontWeight: 700, marginBottom: "10px" } }, t("tab.identity")),

          h("div", { className: "grid", style: { gridTemplateColumns: "1fr", gap: "12px" } },
            identityFieldsToRender.map(f =>
              h(RenderField, {
                key: String(f.key || ""),
                f,
                value: ident[String(f.key || "")],
                onChange: (v) => _setIdent(String(f.key || ""), v),
              })
            ),

            // Single callsign override (derived -> editable)
            h(Field, { label: t("field.callsign") },
              h("input", Object.assign({}, LP, {
                type: "text",
                value: callsignEdit,
                onChange: e => setCallsignEdit(e.target.value)
              }))
            )
          ),

          derivedErr ? h("div", { className: "note", style: { marginTop: "10px" } }, "Derive error: ", derivedErr) : null
        ) : null,

        (tab === "account") ? h("div", null,
          h("div", { style: { fontWeight: 700, marginBottom: "10px" } }, t("tab.account")),
          h("div", { className: "grid", style: { gridTemplateColumns: "1fr", gap: "12px" } },
            h(Field, { label: "Username *" },
              h("input", Object.assign({}, LP, { type: "text", value: username, placeholder: "e.g. admin.46hvbat", onChange: e => setUsername(e.target.value) }))
            ),
            h(Field, { label: "Password (optional)" },
              h("input", { "data-lpignore": "true", autoComplete: "new-password", type: "text", value: password, placeholder: "leave blank for TAKS-generated", onChange: e => setPassword(e.target.value) })
            )
          ),
          h("div", { style: { display: "flex", gap: "20px", alignItems: "center", flexWrap: "wrap", marginTop: "12px" } },
            h("label", null,
              h("input", Object.assign({}, LP, { type: "checkbox", checked: admin, onChange: e => setAdmin(e.target.checked) })),
              " Admin"
            )
          ),

          h("div", { style: { height: "14px" } }),

          h("div", { style: { fontWeight: 700, marginBottom: "10px" } }, "Groups"),
          h("div", { className: "grid", style: { gridTemplateColumns: "1fr", gap: "12px" } },
            ((policy && policy.group_fields) || []).map(f =>
              h(RenderField, {
                key: String(f.key || ""),
                f,
                value: groups[String(f.key || "")],
                onChange: (v) => _setGroups(String(f.key || ""), v),
              })
            )
          )
        ) : null,

        (tab === "advanced") ? h("div", null,
          h("div", { style: { fontWeight: 700, marginBottom: "10px" } }, t("tab.advanced")),
          h("div", { className: "grid", style: { gridTemplateColumns: "1fr", gap: "12px" } },
            h(Field, { label: "TTL (sec)" },
              h("input", Object.assign({}, LP, { type: "number", value: ttlSec, onChange: e => setTtlSec(e.target.value) }))
            )
          ),
          h("div", { style: { display: "flex", gap: "20px", alignItems: "center", flexWrap: "wrap", marginTop: "12px" } },
            h("label", null,
              h("input", Object.assign({}, LP, { type: "checkbox", checked: revealPassword, onChange: e => setRevealPassword(e.target.checked) })),
              " Reveal password on card"
            )
          )
        ) : null,

        h("div", { style: { display: "flex", justifyContent: "space-between", gap: "12px", alignItems: "center", flexWrap: "wrap", marginTop: "14px" } },
          h("div", null, result ? h("span", { className: "muted", style: { fontSize: "12px" } }, "User created.") : null),
          h("button", { onClick: doCreate, disabled: busy }, busy ? "Creating…" : t("btn.create_user"))
        ),

        result ? h("div", { className: "note", style: { marginTop: "12px" } },
          h("div", { style: { display: "flex", gap: "10px", alignItems: "center", flexWrap: "wrap" } },
            h("b", null, "Card URL:"),
            cardUrl ? h("a", { href: cardUrl, target: "_blank", rel: "noopener noreferrer" }, cardUrl) : "—"
          ),
          h("div", { style: { display: "flex", gap: "10px", alignItems: "center", flexWrap: "wrap", marginTop: "8px" } },
            h("b", null, "Password:"),
            pwValue || "—"
          )
        ) : null
      )
    );
  }

  window.OnboardingCreateUserPage = OnboardingCreateUserPage;
})();
