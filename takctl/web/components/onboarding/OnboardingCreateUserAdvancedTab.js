/* global React */
(function () {
  var h = (window.h || React.createElement); window.h = h;

  const t = (window.t && typeof window.t === "function") ? window.t : (k) => String(k || "");
  const LP = { "data-lpignore": "true", autoComplete: "off" };

  function _lang() {
    const v = String(window.currentLang || window.TAKS_RUNTIME_LANGUAGE || "sv").trim().toLowerCase();
    return v.startsWith("en") ? "en" : "sv";
  }

  function _L(sv, en) {
    return _lang() === "en" ? String(en) : String(sv);
  }

  function OnboardingCreateUserAdvancedTab(props) {
    const Field = props.Field;
    const RenderField = props.RenderField;
    const PolicySelect = props.PolicySelect;

    const policy = props.policy;
    const cfg = props.cfg || {};

    const callsignPolicyDefault = props.callsignPolicyDefault;
    const setCallsignPolicyDefault = props.setCallsignPolicyDefault;
    const callsignPolicyOverride = props.callsignPolicyOverride;
    const setCallsignPolicyOverride = props.setCallsignPolicyOverride;

    const normalizePolicyId = props.normalizePolicyId;
    const lsSet = props.lsSet;
    const lsKeyDefaultCallsignPolicy = props.lsKeyDefaultCallsignPolicy;

    const ttlSec = props.ttlSec;
    const setTtlSec = props.setTtlSec;

    const revealPassword = props.revealPassword;
    const setRevealPassword = props.setRevealPassword;

    const setCfg = props.setCfg;

    return h("div", null,
      h("div", { style: { fontWeight: 700, marginBottom: "10px" } }, t("tab.advanced")),

      h("div", { className: "grid", style: { gridTemplateColumns: "1fr", gap: "12px" } },

        h(Field, { label: _L("Anropssignalspolicy (global standard)", "Callsign policy (global default)") },
          h("div", { style: { display: "flex", gap: "10px", alignItems: "center", flexWrap: "wrap" } },
            h(PolicySelect, {
              value: callsignPolicyDefault,
              onChange: function (v) {
                const vv = normalizePolicyId(v) || "FAL_TAK";
                setCallsignPolicyDefault(vv);
                lsSet(lsKeyDefaultCallsignPolicy, vv);
              },
              includeDefaultOption: false
            }),
            h("span", { className: "muted", style: { fontSize: "12px" } },
              _L("Lagrad i webbläsaren (lokalt)", "Stored in browser (local)")
            )
          )
        ),

        h(Field, { label: _L("Anropssignalspolicy override (denna användare)", "Callsign policy override (this user)") },
          h("div", { style: { display: "flex", gap: "10px", alignItems: "center", flexWrap: "wrap" } },
            h(PolicySelect, {
              value: callsignPolicyOverride,
              onChange: function (v) { setCallsignPolicyOverride(normalizePolicyId(v) || ""); },
              includeDefaultOption: true
            }),
            h("span", { className: "muted", style: { fontSize: "12px" } },
              callsignPolicyOverride
                ? _L("Överskriver global", "Overrides global")
                : _L("Använder global", "Uses global")
            )
          )
        ),

        h(Field, { label: _L("TTL (sek)", "TTL (sec)") },
          h("input", Object.assign({}, LP, {
            type: "number",
            value: ttlSec,
            onChange: function (e) { setTtlSec(e.target.value); }
          }))
        ),

        ((policy && policy.config_fields) || []).map(function (f) {
          return h(RenderField, {
            key: String(f.key || ""),
            f: f,
            value: cfg[String(f.key || "")],
            onChange: function (v) { setCfg(String(f.key || ""), v); }
          });
        })
      ),

      h("div", { style: { display: "flex", gap: "20px", alignItems: "center", flexWrap: "wrap", marginTop: "12px" } },
        h("label", null,
          h("input", Object.assign({}, LP, {
            type: "checkbox",
            checked: revealPassword,
            onChange: function (e) { setRevealPassword(e.target.checked); }
          })),
          " ",
          _L("Visa lösenord på kort", "Reveal password on card")
        )
      )
    );
  }

  window.OnboardingCreateUserAdvancedTab = OnboardingCreateUserAdvancedTab;
})();
