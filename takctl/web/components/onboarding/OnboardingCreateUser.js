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

  // For config.pref-backed identity/config fields: show localized label + canonical ATAK key in parentheses
  const ATAK_PREF_KEYS = new Set([
    "callsign",
    "atak_role_type",
    "remarks",
    "team",
    "coord_display",
    "alt_display",
    "alt_units",
    "speed_units",
    "compass_heading_display",
    "bearing_units",
    "range_units",
    "north_ref",
    "domain_pref",
  ]);

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
    if (v && v !== tk) {
      if (ATAK_PREF_KEYS && ATAK_PREF_KEYS.has(key)) return `${v} (${key})`;
      return v;
    }
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

      // Special-case: group must be free-text (lots of real-world special cases),
      // but keep policy options as suggestions.
      if (k === "group") {
        const dlId = "__dl_group";
        return h(Field, { label: required ? (label + " *") : label },
          h("div", { style: { display: "flex", flexDirection: "column", gap: "6px" } },
            h("input", Object.assign({}, LP, {
              type: "text",
              value: String(value ?? ""),
              readOnly: ro,
              placeholder: ph,
              list: dlId,
              onChange: e => onChange(e.target.value)
            })),
            h("datalist", { id: dlId },
              opts.map(o => h("option", { key: String(o), value: String(o) }, String(o)))
            )
          )
        );
      }

      return h(Field, { label: required ? (label + " *") : label },
        h("select", Object.assign({}, LP, { value: String(value ?? ""), disabled: ro, onChange: e => onChange(e.target.value) }),
          opts.map(o => h("option", { key: String(o), value: String(o) }, String(o)))
        )
      );
    }

    if (ty === "bool" || ty === "boolean") {
      return h(Field, { label: required ? (label + " *") : label },
        h("label", { style: { display: "flex", gap: "10px", alignItems: "center" } },
          h("input", Object.assign({}, LP, {
            type: "checkbox",
            checked: !!value,
            disabled: ro,
            onChange: e => onChange(!!e.target.checked),
          })),
          h("span", null, "")
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

  // -----------------------------
  // Callsign policy (KISS)
  // -----------------------------
  const CALLSIGN_POLICIES = [
    { id: "FAL", label: "FAL" },
    { id: "FALFAL", label: "FALFAL" },
    { id: "FAL_TAK", label: "FAL-TAK" },
  ];

  const LS_KEY_DEFAULT_CALLSIGN_POLICY = "taks.callsign_policy_default";

  function _lsGet(key, defVal) {
    try {
      const v = window.localStorage ? window.localStorage.getItem(String(key)) : null;
      return (v == null || String(v).trim() === "") ? defVal : String(v);
    } catch (e) {
      return defVal;
    }
  }

  function _lsSet(key, val) {
    try {
      if (!window.localStorage) return;
      window.localStorage.setItem(String(key), String(val));
    } catch (e) {}
  }

  function _isValidPolicyId(x) {
    const s = String(x || "").trim().toUpperCase();
    return s === "FAL" || s === "FALFAL" || s === "FAL_TAK" || s === "FALSPECIAL";
  }

  function _normalizePolicyId(x) {
    const s = String(x || "").trim().toUpperCase();
    if (s === "FALSPECIAL") return "FAL_TAK"; // legacy alias
    if (_isValidPolicyId(s)) return s;
    return "";
  }

  function _effectiveCallsignPolicy(userOverride, globalDefault) {
    const u = _normalizePolicyId(userOverride);
    if (u) return u;
    const g = _normalizePolicyId(globalDefault);
    return g || "FAL_TAK";
  }

  function OnboardingCreateUserPage(props) {
    const routeUsername = (props && props.routeUsername) ? String(props.routeUsername) : "";

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

    // Global default callsign policy (persists)
    const [callsignPolicyDefault, setCallsignPolicyDefault] = useState("FAL_TAK");

    // Per-user override (optional; stored in ctx.callsign_policy)
    const [callsignPolicyOverride, setCallsignPolicyOverride] = useState("");

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
    const callsignDirtyRef = React.useRef(false);

    // Edit mode (when routeUsername provided)
    const isEdit = !!_norm(routeUsername);

    // Result
    const [busy, setBusy] = useState(false);
    const [err, setErr] = useState("");
    const [result, setResult] = useState(null);

    // Load global default once
    useEffect(() => {
      const v = _normalizePolicyId(_lsGet(LS_KEY_DEFAULT_CALLSIGN_POLICY, "FAL_TAK")) || "FAL_TAK";
      setCallsignPolicyDefault(v);
    }, []);

    // If routed to create:<username>, prefill username and load user
    useEffect(() => {
      const u = _norm(routeUsername);
      if (!u) return;
      setUsername(u);

      (async () => {
        try {
          const urls = _needLib().userUrls(u);
          const r = await fetch(urls.api_get);
          const j = await r.json().catch(() => ({}));
          if (!r.ok) throw new Error(j.detail || ("HTTP " + r.status));

          // ctx from taks_identity if present
          const ti = (j && j.taks_identity) ? j.taks_identity : null;
          const ctx = (ti && ti.ctx) ? ti.ctx : {};

          // password should not be shown in edit (keep blank)
          setPassword("");

          // groups_rw default to current groups for convenience
          const gg = (j && j.user && Array.isArray(j.user.groups)) ? j.user.groups : [];
          if (gg && gg.length) {
            setGroups(prev => Object.assign({}, prev, { groups_rw: gg.join(", ") }));
          }

          // policy_id from ctx if present
          const pid = (ctx && ctx.policy_id) ? String(ctx.policy_id) : "";
          if (pid) setPolicyId(pid);

          // callsign policy override from ctx
          const cp = (ctx && ctx.callsign_policy) ? _normalizePolicyId(ctx.callsign_policy) : "";
          setCallsignPolicyOverride(cp || "");

          // populate identity fields (best effort; policy load will later ensure defaults)
          setIdent(prev => Object.assign({}, prev, ctx || {}));

          // callsign override: preserve and mark dirty so derive doesn't clobber it
          const cso = (ctx && ctx.callsign) ? String(ctx.callsign) : "";
          if (cso) {
            callsignDirtyRef.current = true;
            setCallsignEdit(cso);
          }

        } catch (e) {
          setErr("Edit load failed: " + String((e && e.message) || e));
        }
      })();
    }, [routeUsername]);

    function _normBattalion(x) {
      const tt = String(x || "").trim();
      const m = tt.match(/^(\d{1,3})/);
      return m ? String(m[1]) : tt;
    }

    function _normFal(x) {
      return String(x || "").trim().toUpperCase();
    }

    function _battalionMaps() {
      const m = (policy && policy.maps) || {};
      return {
        b2f: (m && m.battalion_to_fal) || {},
        f2b: (m && m.fal_to_battalion) || {},
      };
    }

    const _FAL_BN_TO = {
      "10":"VJ","11":"VL","12":"VM","13":"VN","14":"VU","15":"VO","16":"VP",
      "17":"VJ","18":"VL",
      "19":"VJ","20":"VL","21":"VM","22":"VN","23":"VU","24":"VO","25":"VP","26":"VQ","27":"VV","28":"VW","29":"VX",
      "30":"VJ","31":"VL","32":"VW","33":"VM","34":"VN","35":"VU","36":"VO","37":"VP",
      "38":"VM","39":"VN","40":"VU","41":"VO","42":"VP","43":"VQ","44":"VV","45":"VW",
      "46":"VQ","47":"VV","48":"VW","49":"VX"
    };

    const _FAL_TO_BNS = (() => {
      const out = {};
      for (const [bn, fal] of Object.entries(_FAL_BN_TO)) {
        const k = String(fal || "").toUpperCase();
        if (!out[k]) out[k] = [];
        out[k].push(String(bn));
      }
      return out;
    })();

    function _battalionToFal(bnRaw) {
      const bn = _normBattalion(bnRaw);
      const maps = _battalionMaps();
      if (maps.b2f && maps.b2f[bn]) return String(maps.b2f[bn]);
      return _FAL_BN_TO[bn] ? String(_FAL_BN_TO[bn]) : "";
    }

    function _falToBattalion(falRaw) {
      const fal = _normFal(falRaw);
      const maps = _battalionMaps();
      if (maps.f2b && maps.f2b[fal]) return String(maps.f2b[fal]);
      const cands = _FAL_TO_BNS[fal] || [];
      return (cands.length === 1) ? String(cands[0]) : "";
    }

    function _setIdent(k, v) {
      const kk = String(k || "");
      const vv = (v == null) ? "" : String(v);

      if (kk === "battalion") {
        const batt = _normBattalion(vv);
        const mappedFal = _battalionToFal(batt);
        setIdent(prev => {
          const out = Object.assign({}, prev, { battalion: batt });
          if (mappedFal) out.battalion_fal = mappedFal;
          return out;
        });
        return;
      }

      if (kk === "battalion_fal") {
        const fal = _normFal(vv);
        const mappedBatt = _falToBattalion(fal);
        setIdent(prev => {
          const out = Object.assign({}, prev, { battalion_fal: fal });
          if (mappedBatt) out.battalion = mappedBatt;
          return out;
        });
        return;
      }

      if (kk === "n") {
        const nval = String(vv || "").trim();
        setIdent(prev => {
          const out = Object.assign({}, prev, { n: nval });
          const curRole = String(out.atak_role_type || "").trim();
          if ((nval === "1" || nval === "2") && (!curRole || curRole.toLowerCase() === "soldier")) {
            out.atak_role_type = "Team Lead";
          }
          return out;
        });
        return;
      }

      setIdent(prev => Object.assign({}, prev, { [kk]: vv }));
    }

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
          // Do NOT clobber policyId if edit-mode set it from ctx already
          setPolicyId(prev => prev ? prev : (defId || ""));
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
      for (const k of ["battalion", "battalion_fal", "company", "platoon", "group", "n", "team", "callsign_policy"]) {
        o[k] = String((ctx && ctx[k]) || "");
      }
      return JSON.stringify(o);
    }

    useEffect(() => {
      const battalion = _norm(ctxForDerive && ctxForDerive.battalion);
      const battalion_fal = _norm(ctxForDerive && ctxForDerive.battalion_fal);
      const company = _norm(ctxForDerive && ctxForDerive.company);
      const platoon = _norm(ctxForDerive && ctxForDerive.platoon);
      const group = _norm(ctxForDerive && ctxForDerive.group);
      const n = _norm(ctxForDerive && ctxForDerive.n);
      const team = _norm(ctxForDerive && ctxForDerive.team);

      const effectivePolicy = _effectiveCallsignPolicy(callsignPolicyOverride, callsignPolicyDefault);

      const hasBatt = !!(battalion_fal || battalion);
      const hierOk =
        (!company && !platoon && !group) ||
        ( company && !platoon && !group) ||
        ( company &&  platoon && !group) ||
        ( company &&  platoon &&  group);

      if (!policyId || !n || !hasBatt || !hierOk) {
        setDerived(null);
        setDerivedErr("");
        setDeriveBusy(false);
        _deriveLastKeyRef.current = "";
        if (_deriveAbortRef.current) { try { _deriveAbortRef.current.abort(); } catch (e) {} }
        _deriveAbortRef.current = null;
        return;
      }

      const key = _deriveKey(policyId, { battalion, battalion_fal, company, platoon, group, n, team, callsign_policy: effectivePolicy });
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
                ctx: { battalion, battalion_fal, company, platoon, group, n, team, callsign_policy: effectivePolicy }
              }),
              signal: ac.signal,
            });
            const data = await resp.json().catch(() => ({}));
            if (!resp.ok) throw new Error(data.error || data.detail || ("HTTP " + resp.status));

            setDerived(data || null);

            // Only auto-overwrite callsign if user hasn't touched it
            if (!callsignDirtyRef.current) {
              const di = (data && data.identity) || {};
              setCallsignEdit(di.callsign ? String(di.callsign) : "");
            }

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
      ctxForDerive && ctxForDerive.battalion_fal,
      ctxForDerive && ctxForDerive.company,
      ctxForDerive && ctxForDerive.platoon,
      ctxForDerive && ctxForDerive.group,
      ctxForDerive && ctxForDerive.n,
      ctxForDerive && ctxForDerive.team,
      callsignPolicyDefault,
      callsignPolicyOverride
    ]);

    async function doCreate() {
      setErr("");
      setResult(null);

      const u = _norm(username);
      if (!u) { setErr("Username required."); return; }
      if (!policyId) { setErr("Policy required."); return; }

      const effectivePolicy = _effectiveCallsignPolicy(callsignPolicyOverride, callsignPolicyDefault);

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

      ctx.callsign_policy = effectivePolicy;

      if (_norm(callsignEdit)) ctx.callsign = String(callsignEdit);

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

    const activePolicyName = policy ? `${policy.name} (${policyId})` : (policyId ? policyId : "—");

    const badgePrimary = _norm(callsignEdit) || "—";
    const battalion = _norm(ctxForDerive && ctxForDerive.battalion);
    const row2 = battalion ? `${battalion} HVBAT` : "—";

    const identityFieldsToRender = (((policy && policy.identity_fields) || [])).filter(f => String((f && f.key) || "") !== "callsign");

    const cardUrl = (result && result.card_url) || "";
    const pwValue = (result && result.taks_identity && result.taks_identity.password && result.taks_identity.password.value) || "";

    const effectivePolicyUi = _effectiveCallsignPolicy(callsignPolicyOverride, callsignPolicyDefault);

    function PolicySelect({ value, onChange, includeDefaultOption }) {
      const v = String(value || "");
      return h("select", Object.assign({}, LP, {
        value: v,
        onChange: e => onChange(e.target.value)
      }),
        includeDefaultOption ? h("option", { value: "" }, "Default (global)") : null,
        CALLSIGN_POLICIES.map(p => h("option", { key: p.id, value: p.id }, p.label))
      );
    }

    return h("div", { className: "ob-create-root" },
      h("div", { className: "card-title" }, isEdit ? ("Onboarding — Edit user") : t("page.onboarding_create")),

      err ? h("div", { className: "note", style: { marginBottom: "12px" } }, "ERR: ", err) : null,

      h("div", { className: "muted", style: { fontSize: "12px", marginBottom: "10px" } },
        "Policy: ",
        policy ? (`${activePolicyName} • v${_colText(policy.version)} • source=${_colText(policy._meta && policy._meta.source)}`) : (policyId ? activePolicyName : "Loading policy…")
      ),

      h(_needBadge().NameBadge, {
        callsign: badgePrimary,
        row2: row2,
        teamColor: _norm(ctxForDerive && ctxForDerive.team),
        statusText: ""
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

            h(Field, { label: _labelForKey("callsign", t("field.callsign")) },
              h("input", Object.assign({}, LP, {
                type: "text",
                value: callsignEdit,
                onChange: e => { callsignDirtyRef.current = true; setCallsignEdit(e.target.value); }
              })),
              h("div", { className: "muted", style: { fontSize: "12px", marginTop: "6px" } },
                "Policy: ",
                h("span", { style: { fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace" } }, effectivePolicyUi)
              )
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
            h(Field, { label: isEdit ? "Password (leave blank to keep unchanged)" : "Password (optional)" },
              h("input", { "data-lpignore": "true", autoComplete: "new-password", type: "text", value: password, placeholder: isEdit ? "leave blank to keep current" : "leave blank for TAKS-generated", onChange: e => setPassword(e.target.value) })
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

            h(Field, { label: "Callsign policy (global default)" },
              h("div", { style: { display: "flex", gap: "10px", alignItems: "center", flexWrap: "wrap" } },
                h(PolicySelect, {
                  value: callsignPolicyDefault,
                  onChange: (v) => {
                    const vv = _normalizePolicyId(v) || "FAL_TAK";
                    setCallsignPolicyDefault(vv);
                    _lsSet(LS_KEY_DEFAULT_CALLSIGN_POLICY, vv);
                  },
                  includeDefaultOption: false
                }),
                h("span", { className: "muted", style: { fontSize: "12px" } }, "Stored in browser (local)")
              )
            ),

            h(Field, { label: "Callsign policy override (this user)" },
              h("div", { style: { display: "flex", gap: "10px", alignItems: "center", flexWrap: "wrap" } },
                h(PolicySelect, {
                  value: callsignPolicyOverride,
                  onChange: (v) => setCallsignPolicyOverride(_normalizePolicyId(v) || ""),
                  includeDefaultOption: true
                }),
                h("span", { className: "muted", style: { fontSize: "12px" } },
                  callsignPolicyOverride ? "Overrides global" : "Uses global"
                )
              )
            ),

            h(Field, { label: "TTL (sec)" },
              h("input", Object.assign({}, LP, { type: "number", value: ttlSec, onChange: e => setTtlSec(e.target.value) }))
            ),

            ((policy && policy.config_fields) || []).map(f =>
              h(RenderField, {
                key: String(f.key || ""),
                f,
                value: cfg[String(f.key || "")],
                onChange: (v) => _setCfg(String(f.key || ""), v),
              })
            )
          ),

          h("div", { style: { display: "flex", gap: "20px", alignItems: "center", flexWrap: "wrap", marginTop: "12px" } },
            h("label", null,
              h("input", Object.assign({}, LP, { type: "checkbox", checked: revealPassword, onChange: e => setRevealPassword(e.target.checked) })),
              " Reveal password on card"
            )
          )
        ) : null,

        h("div", { style: { height: "12px" } }),

        h("button", {
          type: "button",
          onClick: doCreate,
          disabled: busy,
          style: {
            appearance: "none",
            WebkitAppearance: "none",
            MozAppearance: "none",

            width: "100%",
            padding: "14px 16px",
            borderRadius: "12px",

            border: "1px solid rgba(255,255,255,0.18)",
            background: "rgba(255,255,255,0.08)",
            color: "#fff",

            boxShadow: "0 10px 24px rgba(0,0,0,0.35)",
            fontWeight: 900,
            fontSize: "13px",
            letterSpacing: "0.10em",
            textTransform: "uppercase",

            cursor: busy ? "not-allowed" : "pointer",
            opacity: busy ? 0.65 : 1
          }
        }, busy ? "Saving…" : (isEdit ? "Save user" : t("btn.create_user"))),

        h("div", {
          style: { display: "flex", justifyContent: "flex-end", marginTop: "10px" }
        },
          result ? h("span", { className: "muted", style: { fontSize: "12px" } }, isEdit ? "Saved." : "User created.") : null
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
