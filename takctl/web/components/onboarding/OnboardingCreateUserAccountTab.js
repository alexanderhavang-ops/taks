/* global React */
(function () {
  var h = (window.h || React.createElement); window.h = h;

  const LP = { "data-lpignore": "true", autoComplete: "off" };
  const t = (window.t && typeof window.t === "function") ? window.t : (k) => String(k || "");

  function OnboardingCreateUserAccountTab(props) {
    const Field = props.Field;
    const RenderField = props.RenderField;

    const isEdit = !!props.isEdit;
    const policy = props.policy;

    const username = props.username || "";
    const setUsername = props.setUsername;

    const emailAddr = props.emailAddr || "";
    const setEmailAddr = props.setEmailAddr;

    const password = props.password || "";
    const setPassword = props.setPassword;

    const admin = !!props.admin;
    const setAdmin = props.setAdmin;

    const groups = props.groups || {};
    const setGroups = props.setGroups;

    return h("div", null,
      h("div", { style: { fontWeight: 700, marginBottom: "10px" } }, t("tab.account")),

      h("div", { className: "grid", style: { gridTemplateColumns: "1fr", gap: "12px" } },
        h(Field, { label: "Username *" },
          h("input", Object.assign({}, LP, {
            type: "text",
            value: username,
            placeholder: "e.g. admin.46hvbat",
            onChange: function (e) { setUsername(e.target.value); }
          }))
        ),
        h(Field, { label: "Email" },
          h("input", Object.assign({}, LP, {
            type: "email",
            value: emailAddr,
            placeholder: "name@example.com",
            onChange: function (e) { setEmailAddr(e.target.value); }
          }))
        ),
        h(Field, { label: isEdit ? "Password (leave blank to keep unchanged)" : "Password (optional)" },
          h("input", {
            "data-lpignore": "true",
            autoComplete: "new-password",
            type: "text",
            value: password,
            placeholder: isEdit ? "leave blank to keep current" : "leave blank for TAKS-generated",
            onChange: function (e) { setPassword(e.target.value); }
          })
        )
      ),

      h("div", { style: { display: "flex", gap: "20px", alignItems: "center", flexWrap: "wrap", marginTop: "12px" } },
        h("label", null,
          h("input", Object.assign({}, LP, {
            type: "checkbox",
            checked: admin,
            onChange: function (e) { setAdmin(e.target.checked); }
          })),
          " Admin"
        )
      ),

      h("div", { style: { height: "14px" } }),

      h("div", { style: { fontWeight: 700, marginBottom: "10px" } }, "Groups"),
      h("div", { className: "grid", style: { gridTemplateColumns: "1fr", gap: "12px" } },
        ((policy && policy.group_fields) || []).map(function (f) {
          return h(RenderField, {
            key: String(f.key || ""),
            f: f,
            value: groups[String(f.key || "")],
            onChange: function (v) { setGroups(String(f.key || ""), v); }
          });
        })
      )
    );
  }

  window.OnboardingCreateUserAccountTab = OnboardingCreateUserAccountTab;
})();
