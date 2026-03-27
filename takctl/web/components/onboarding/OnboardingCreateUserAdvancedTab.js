/* global React */
(function () {
  var h = (window.h || React.createElement); window.h = h;

  const t = (window.t && typeof window.t === "function") ? window.t : (k) => String(k || "");
  const LP = { "data-lpignore": "true", autoComplete: "off" };

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

    const artifactAtakAutoEnroll = !!props.artifactAtakAutoEnroll;
    const setArtifactAtakAutoEnroll = props.setArtifactAtakAutoEnroll;

    const artifactAtakSoftCertNoPassword = !!props.artifactAtakSoftCertNoPassword;
    const setArtifactAtakSoftCertNoPassword = props.setArtifactAtakSoftCertNoPassword;

    const artifactAtakSoftCertWithPassword = !!props.artifactAtakSoftCertWithPassword;
    const setArtifactAtakSoftCertWithPassword = props.setArtifactAtakSoftCertWithPassword;

    const artifactItakSoftCertNoPassword = !!props.artifactItakSoftCertNoPassword;
    const setArtifactItakSoftCertNoPassword = props.setArtifactItakSoftCertNoPassword;

    const artifactItakSoftCertWithPassword = !!props.artifactItakSoftCertWithPassword;
    const setArtifactItakSoftCertWithPassword = props.setArtifactItakSoftCertWithPassword;

    return h("div", null,
      h("div", { style: { fontWeight: 700, marginBottom: "10px" } }, t("tab.advanced")),

      h("div", { className: "grid", style: { gridTemplateColumns: "1fr", gap: "12px" } },

        h(Field, { label: "Callsign policy (global default)" },
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
            h("span", { className: "muted", style: { fontSize: "12px" } }, "Stored in browser (local)")
          )
        ),

        h(Field, { label: "Callsign policy override (this user)" },
          h("div", { style: { display: "flex", gap: "10px", alignItems: "center", flexWrap: "wrap" } },
            h(PolicySelect, {
              value: callsignPolicyOverride,
              onChange: function (v) { setCallsignPolicyOverride(normalizePolicyId(v) || ""); },
              includeDefaultOption: true
            }),
            h("span", { className: "muted", style: { fontSize: "12px" } },
              callsignPolicyOverride ? "Overrides global" : "Uses global"
            )
          )
        ),

        h(Field, { label: "TTL (sec)" },
          h("input", Object.assign({}, LP, {
            type: "number",
            value: ttlSec,
            onChange: function (e) { setTtlSec(e.target.value); }
          }))
        ),

        h(Field, { label: "Generated onboarding artifacts" },
          h("div", { style: { display: "grid", gap: "8px" } },
            h("label", null,
              h("input", Object.assign({}, LP, {
                type: "checkbox",
                checked: artifactAtakAutoEnroll,
                onChange: function (e) { setArtifactAtakAutoEnroll(e.target.checked); }
              })),
              " ATAK auto-enroll"
            ),
            h("label", null,
              h("input", Object.assign({}, LP, {
                type: "checkbox",
                checked: artifactAtakSoftCertNoPassword,
                onChange: function (e) {
                  const checked = !!e.target.checked;
                  setArtifactAtakSoftCertNoPassword(checked);
                  if (checked) setArtifactAtakSoftCertWithPassword(false);
                }
              })),
              " ATAK soft-cert zip (no password)"
            ),
            h("label", null,
              h("input", Object.assign({}, LP, {
                type: "checkbox",
                checked: artifactAtakSoftCertWithPassword,
                onChange: function (e) {
                  const checked = !!e.target.checked;
                  setArtifactAtakSoftCertWithPassword(checked);
                  if (checked) setArtifactAtakSoftCertNoPassword(false);
                }
              })),
              " ATAK soft-cert zip (with password)"
            ),
            h("label", null,
              h("input", Object.assign({}, LP, {
                type: "checkbox",
                checked: artifactItakSoftCertNoPassword,
                onChange: function (e) {
                  const checked = !!e.target.checked;
                  setArtifactItakSoftCertNoPassword(checked);
                  if (checked) setArtifactItakSoftCertWithPassword(false);
                }
              })),
              " iTAK zip (no password)"
            ),
            h("label", null,
              h("input", Object.assign({}, LP, {
                type: "checkbox",
                checked: artifactItakSoftCertWithPassword,
                onChange: function (e) {
                  const checked = !!e.target.checked;
                  setArtifactItakSoftCertWithPassword(checked);
                  if (checked) setArtifactItakSoftCertNoPassword(false);
                }
              })),
              " iTAK zip (with password)"
            ),
            h("div", { className: "muted", style: { fontSize: "12px" } },
              "ATAK/iTAK no-password vs with-password are mutually exclusive per client."
            )
          )
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
          " Reveal password on card"
        )
      )
    );
  }

  window.OnboardingCreateUserAdvancedTab = OnboardingCreateUserAdvancedTab;
})();
