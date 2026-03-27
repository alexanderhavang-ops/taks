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

  const IdentityTab = window.OnboardingCreateUserIdentityTab || null;
  function _needIdentityTab(){ if (!IdentityTab) throw new Error("Missing OnboardingCreateUserIdentityTab.js"); return IdentityTab; }

  const AccountTab = window.OnboardingCreateUserAccountTab || null;
  function _needAccountTab(){ if (!AccountTab) throw new Error("Missing OnboardingCreateUserAccountTab.js"); return AccountTab; }

  const AdvancedTab = window.OnboardingCreateUserAdvancedTab || null;
  function _needAdvancedTab(){ if (!AdvancedTab) throw new Error("Missing OnboardingCreateUserAdvancedTab.js"); return AdvancedTab; }

  const t = (window.t && typeof window.t === "function") ? window.t : (k) => String(k || "");

  const common = (window.TaksOnboarding && window.TaksOnboarding.createUser && window.TaksOnboarding.createUser.common) || null;
  function _needCommon(){ if (!common) throw new Error("Missing create_user/common.js"); return common; }

  const LP = _needCommon().LP;
  const _norm = _needCommon().norm;
  const _labelForKey = _needCommon().labelForKey;
  const Field = _needCommon().Field;
  const RenderField = _needCommon().RenderField;
  const Tabs = _needCommon().Tabs;
  const CALLSIGN_POLICIES = _needCommon().CALLSIGN_POLICIES;
  const LS_KEY_DEFAULT_CALLSIGN_POLICY = _needCommon().LS_KEY_DEFAULT_CALLSIGN_POLICY;
  const _lsGet = _needCommon().lsGet;
  const _lsSet = _needCommon().lsSet;
  const _isValidPolicyId = _needCommon().isValidPolicyId;
  const _normalizePolicyId = _needCommon().normalizePolicyId;
  const _effectiveCallsignPolicy = _needCommon().effectiveCallsignPolicy;
  const PolicySelect = _needCommon().PolicySelect;
  const actions = (window.TaksOnboarding && window.TaksOnboarding.createUser && window.TaksOnboarding.createUser.actions) || null;
  function _needActions(){ if (!actions) throw new Error("Missing create_user/actions.js"); return actions; }
  const _doCreateAction = _needActions().doCreate;
  const _doEmailLinkAction = _needActions().doEmailLink;

  const deriveMod = (window.TaksOnboarding && window.TaksOnboarding.createUser && window.TaksOnboarding.createUser.derive) || null;
  function _needDerive(){ if (!deriveMod) throw new Error("Missing create_user/derive.js"); return deriveMod; }
  const _runDeriveEffect = _needDerive().runDeriveEffect;

  const identityLogic = (window.TaksOnboarding && window.TaksOnboarding.createUser && window.TaksOnboarding.createUser.identityLogic) || null;
  function _needIdentityLogic(){ if (!identityLogic) throw new Error("Missing create_user/identity_logic.js"); return identityLogic; }

  const _normBattalion = _needIdentityLogic().normBattalion;
  const _normFal = _needIdentityLogic().normFal;
  const _battalionToFal = function (policy, bnRaw) { return _needIdentityLogic().battalionToFal(policy, bnRaw); };
  const _falToBattalion = function (policy, falRaw) { return _needIdentityLogic().falToBattalion(policy, falRaw); };
  const _deriveKey = _needIdentityLogic().deriveKey;

  function OnboardingCreateUserPage(props) {
    const routeUsername = (props && props.routeUsername) ? String(props.routeUsername) : "";

    const [policyList, setPolicyList] = useState(null);
    const [policyId, setPolicyId] = useState("");
    const [policy, setPolicy] = useState(null);

    const [tab, setTab] = useState("identity");

    const [username, setUsername] = useState("");
    const [password, setPassword] = useState("");
    const [admin, setAdmin] = useState(false);
    const [emailAddr, setEmailAddr] = useState("");

    const [revealPassword, setRevealPassword] = useState(true);
    const [ttlSec, setTtlSec] = useState(600);

    const [artifactAtakAutoEnroll, setArtifactAtakAutoEnroll] = useState(false);
    const [artifactAtakSoftCertNoPassword, setArtifactAtakSoftCertNoPassword] = useState(false);
    const [artifactAtakSoftCertWithPassword, setArtifactAtakSoftCertWithPassword] = useState(false);
    const [artifactItakSoftCertNoPassword, setArtifactItakSoftCertNoPassword] = useState(true);
    const [artifactItakSoftCertWithPassword, setArtifactItakSoftCertWithPassword] = useState(false);

    const [callsignPolicyDefault, setCallsignPolicyDefault] = useState("FAL_TAK");
    const [callsignPolicyOverride, setCallsignPolicyOverride] = useState("");

    const [ident, setIdent] = useState({});
    const [groups, setGroups] = useState({ groups_rw: "46hvbat", groups_in: "", groups_out: "" });
    const [cfg, setCfg] = useState({});

    const [derived, setDerived] = useState(null);
    const [derivedErr, setDerivedErr] = useState("");
    const [deriveBusy, setDeriveBusy] = useState(false);
    const _deriveAbortRef = React.useRef(null);
    const _deriveLastKeyRef = React.useRef("");

    const [callsignEdit, setCallsignEdit] = useState("");
    const callsignDirtyRef = React.useRef(false);

    const isEdit = !!_norm(routeUsername);

    const [busy, setBusy] = useState(false);
    const [err, setErr] = useState("");
    const [result, setResult] = useState(null);

    const [emailBusy, setEmailBusy] = useState(false);
    const [emailErr, setEmailErr] = useState("");
    const [emailResult, setEmailResult] = useState(null);

    useEffect(() => {
      const v = _normalizePolicyId(_lsGet(LS_KEY_DEFAULT_CALLSIGN_POLICY, "FAL_TAK")) || "FAL_TAK";
      setCallsignPolicyDefault(v);
    }, []);

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

          const ti = (j && j.taks_identity) ? j.taks_identity : null;
          const ctx = (ti && ti.ctx) ? ti.ctx : {};

          setPassword("");

          const gg = (j && j.user && Array.isArray(j.user.groups)) ? j.user.groups : [];
          if (gg && gg.length) {
            setGroups(prev => Object.assign({}, prev, { groups_rw: gg.join(", ") }));
          }

          const pid = (ctx && ctx.policy_id) ? String(ctx.policy_id) : "";
          if (pid) setPolicyId(pid);

          const cp = (ctx && ctx.callsign_policy) ? _normalizePolicyId(ctx.callsign_policy) : "";
          setCallsignPolicyOverride(cp || "");

          const sel = (j && j.selection) ? j.selection : {};
          const ar = (sel && sel.artifacts_requested) ? sel.artifacts_requested : {};
          if (ar && typeof ar === "object" && Object.keys(ar).length) {
            setArtifactAtakAutoEnroll(!!ar.atak_auto_enroll);
            setArtifactAtakSoftCertNoPassword(!!ar.atak_soft_cert_no_password);
            setArtifactAtakSoftCertWithPassword(!!ar.atak_soft_cert_with_password);
            setArtifactItakSoftCertNoPassword(!!ar.itak_soft_cert_no_password);
            setArtifactItakSoftCertWithPassword(!!ar.itak_soft_cert_with_password);
          }

          setIdent(prev => Object.assign({}, prev, ctx || {}));

          const em = (ctx && ctx.email) ? String(ctx.email) : "";
          if (em) setEmailAddr(em);

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

    function _setIdent(k, v) {
      setIdent(prev => _needIdentityLogic().setIdentWithLogic(prev, k, v, policy));
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

    useEffect(() => {
      return _runDeriveEffect({
        policyId: policyId,
        ctxForDerive: ctxForDerive,
        norm: _norm,
        effectiveCallsignPolicy: _effectiveCallsignPolicy,
        callsignPolicyOverride: callsignPolicyOverride,
        callsignPolicyDefault: callsignPolicyDefault,
        deriveKey: _deriveKey,
        setDerived: setDerived,
        setDerivedErr: setDerivedErr,
        setDeriveBusy: setDeriveBusy,
        setCallsignEdit: setCallsignEdit,
        deriveAbortRef: _deriveAbortRef,
        deriveLastKeyRef: _deriveLastKeyRef,
        callsignDirtyRef: callsignDirtyRef
      });
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
      return _doCreateAction({
        norm: _norm,
        splitCsv: _splitCsv,
        effectiveCallsignPolicy: _effectiveCallsignPolicy,
        labelForKey: _labelForKey,
        username: username,
        policyId: policyId,
        policy: policy,
        ident: ident,
        callsignEdit: callsignEdit,
        emailAddr: emailAddr,
        password: password,
        admin: admin,
        groups: groups,
        ttlSec: ttlSec,
        revealPassword: revealPassword,
        callsignPolicyOverride: callsignPolicyOverride,
        callsignPolicyDefault: callsignPolicyDefault,
        artifactAtakAutoEnroll: artifactAtakAutoEnroll,
        artifactAtakSoftCertNoPassword: artifactAtakSoftCertNoPassword,
        artifactAtakSoftCertWithPassword: artifactAtakSoftCertWithPassword,
        artifactItakSoftCertNoPassword: artifactItakSoftCertNoPassword,
        artifactItakSoftCertWithPassword: artifactItakSoftCertWithPassword,
        setErr: setErr,
        setResult: setResult,
        setEmailErr: setEmailErr,
        setEmailResult: setEmailResult,
        setBusy: setBusy
      });
    }

    async function doEmailLink() {
      return _doEmailLinkAction({
        norm: _norm,
        username: username,
        emailAddr: emailAddr,
        ttlSec: ttlSec,
        revealPassword: revealPassword,
        setEmailErr: setEmailErr,
        setEmailResult: setEmailResult,
        setEmailBusy: setEmailBusy,
        setResult: setResult
      });
    }

    const activePolicyName = policy ? `${policy.name} (${policyId})` : (policyId ? policyId : "—");

    const badgePrimary = _norm(callsignEdit) || "—";
    const battalion = _norm(ctxForDerive && ctxForDerive.battalion);
    const row2 = battalion ? `${battalion} HVBAT` : "—";

    const identityFieldsToRender = (((policy && policy.identity_fields) || [])).filter(f => String((f && f.key) || "") !== "callsign");

    const cardUrl = (result && result.card_url) || "";
    const pwValue = (result && result.taks_identity && result.taks_identity.password && result.taks_identity.password.value) || "";
    const effectivePolicyUi = _effectiveCallsignPolicy(callsignPolicyOverride, callsignPolicyDefault);

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

        (tab === "identity") ? h(_needIdentityTab(), {
          Field: Field,
          RenderField: RenderField,
          t: t,
          labelForKey: _labelForKey,
          identityFieldsToRender: identityFieldsToRender,
          ident: ident,
          setIdent: _setIdent,
          callsignEdit: callsignEdit,
          setCallsignEdit: setCallsignEdit,
          callsignDirtyRef: callsignDirtyRef,
          effectivePolicyUi: effectivePolicyUi,
          derivedErr: derivedErr
        }) : null,

        (tab === "account") ? h(_needAccountTab(), {
          Field: Field,
          RenderField: RenderField,
          t: t,
          policy: policy,
          isEdit: isEdit,
          username: username,
          setUsername: setUsername,
          emailAddr: emailAddr,
          setEmailAddr: setEmailAddr,
          password: password,
          setPassword: setPassword,
          admin: admin,
          setAdmin: setAdmin,
          groups: groups,
          setGroups: _setGroups
        }) : null,

        (tab === "advanced") ? h(_needAdvancedTab(), {
          Field: Field,
          RenderField: RenderField,
          PolicySelect: PolicySelect,
          policy: policy,
          cfg: cfg,
          callsignPolicyDefault: callsignPolicyDefault,
          setCallsignPolicyDefault: setCallsignPolicyDefault,
          callsignPolicyOverride: callsignPolicyOverride,
          setCallsignPolicyOverride: setCallsignPolicyOverride,
          normalizePolicyId: _normalizePolicyId,
          lsSet: _lsSet,
          lsKeyDefaultCallsignPolicy: LS_KEY_DEFAULT_CALLSIGN_POLICY,
          ttlSec: ttlSec,
          setTtlSec: setTtlSec,
          revealPassword: revealPassword,
          setRevealPassword: setRevealPassword,
          setCfg: _setCfg,
          artifactAtakAutoEnroll: artifactAtakAutoEnroll,
          setArtifactAtakAutoEnroll: setArtifactAtakAutoEnroll,
          artifactAtakSoftCertNoPassword: artifactAtakSoftCertNoPassword,
          setArtifactAtakSoftCertNoPassword: setArtifactAtakSoftCertNoPassword,
          artifactAtakSoftCertWithPassword: artifactAtakSoftCertWithPassword,
          setArtifactAtakSoftCertWithPassword: setArtifactAtakSoftCertWithPassword,
          artifactItakSoftCertNoPassword: artifactItakSoftCertNoPassword,
          setArtifactItakSoftCertNoPassword: setArtifactItakSoftCertNoPassword,
          artifactItakSoftCertWithPassword: artifactItakSoftCertWithPassword,
          setArtifactItakSoftCertWithPassword: setArtifactItakSoftCertWithPassword
        }) : null,

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
          ),
          h("div", { style: { display: "flex", gap: "10px", alignItems: "center", flexWrap: "wrap", marginTop: "8px" } },
            h("b", null, "Email:"),
            _norm(emailAddr) || "—"
          ),
          h("div", { style: { display: "flex", gap: "10px", alignItems: "center", flexWrap: "wrap", marginTop: "10px" } },
            h("button", {
              type: "button",
              className: "btn",
              disabled: emailBusy || !_norm(username) || !_norm(emailAddr),
              onClick: doEmailLink
            }, emailBusy ? "Emailing…" : "Email link")
          ),
          emailErr ? h("div", { className: "muted", style: { marginTop: "8px", whiteSpace: "pre-wrap" } }, "Email error: " + String(emailErr)) : null,
          emailResult ? h("div", { className: "muted", style: { marginTop: "8px", whiteSpace: "pre-wrap" } },
            "Email sent to " + _colText(emailResult.email || emailAddr)
          ) : null
        ) : null
      )
    );
  }

  window.OnboardingCreateUserPage = OnboardingCreateUserPage;
})();
