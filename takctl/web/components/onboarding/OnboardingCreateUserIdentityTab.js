/* global React */
(function () {
  var h = (window.h || React.createElement); window.h = h;

  const t = (window.t && typeof window.t === "function") ? window.t : (k) => String(k || "");
  const LP = { "data-lpignore": "true", autoComplete: "off" };

  function OnboardingCreateUserIdentityTab(props) {
    const Field = props.Field;
    const RenderField = props.RenderField;

    const policy = props.policy;
    const ident = props.ident || {};
    const setIdent = props.setIdent;

    const callsignEdit = props.callsignEdit || "";
    const setCallsignEdit = props.setCallsignEdit;
    const callsignDirtyRef = props.callsignDirtyRef;

    const labelForKey = props.labelForKey;
    const effectivePolicyUi = props.effectivePolicyUi;
    const derivedErr = props.derivedErr;

    const identityFieldsToRender = (((policy && policy.identity_fields) || [])).filter(function (f) {
      return String((f && f.key) || "") !== "callsign";
    });

    return h("div", null,
      h("div", { style: { fontWeight: 700, marginBottom: "10px" } }, t("tab.identity")),

      h("div", { className: "grid", style: { gridTemplateColumns: "1fr", gap: "12px" } },
        identityFieldsToRender.map(function (f) {
          return h(RenderField, {
            key: String(f.key || ""),
            f: f,
            value: ident[String(f.key || "")],
            onChange: function (v) { setIdent(String(f.key || ""), v); }
          });
        }),

        h(Field, { label: labelForKey("callsign", t("field.callsign")) },
          h("input", Object.assign({}, LP, {
            type: "text",
            value: callsignEdit,
            onChange: function (e) {
              callsignDirtyRef.current = true;
              setCallsignEdit(e.target.value);
            }
          })),
          h("div", { className: "muted", style: { fontSize: "12px", marginTop: "6px" } },
            "Policy: ",
            h("span", {
              style: { fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace" }
            }, effectivePolicyUi)
          )
        )
      ),

      derivedErr ? h("div", { className: "note", style: { marginTop: "10px" } }, "Derive error: ", derivedErr) : null
    );
  }

  window.OnboardingCreateUserIdentityTab = OnboardingCreateUserIdentityTab;
})();
