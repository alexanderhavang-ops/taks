/* global React */
(function () {
  var h = (window.h || React.createElement); window.h = h;

  const LP = { "data-lpignore": "true", autoComplete: "off" };
  const t = (window.t && typeof window.t === "function") ? window.t : (k) => String(k || "");

  function _lang() {
    const v = String(window.currentLang || window.TAKS_RUNTIME_LANGUAGE || "sv").trim().toLowerCase();
    return v.startsWith("en") ? "en" : "sv";
  }

  function _L(sv, en) {
    return _lang() === "en" ? String(en) : String(sv);
  }

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
        h(Field, { label: _L("Användarnamn *", "Username *") },
          h("input", Object.assign({}, LP, {
            type: "text",
            value: username,
            placeholder: _L("t.ex. admin.46hvbat", "e.g. admin.46hvbat"),
            onChange: function (e) { setUsername(e.target.value); }
          }))
        ),

        h(Field, { label: _L("E-post", "Email") },
          h("input", Object.assign({}, LP, {
            type: "email",
            value: emailAddr,
            placeholder: "name@example.com",
            onChange: function (e) { setEmailAddr(e.target.value); }
          }))
        ),

        h(Field, {
          label: isEdit
            ? _L("Lösenord (lämna tomt för att behålla nuvarande)", "Password (leave blank to keep unchanged)")
            : _L("Lösenord (valfritt)", "Password (optional)")
        },
          h("input", {
            "data-lpignore": "true",
            autoComplete: "new-password",
            type: "text",
            value: password,
            placeholder: isEdit
              ? _L("lämna tomt för att behålla nuvarande", "leave blank to keep current")
              : _L("lämna tomt för TAKS-genererat", "leave blank for TAKS-generated"),
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
          " ",
          _L("Admin", "Admin")
        )
      ),

      h("div", { style: { height: "14px" } }),

      h("div", { style: { fontWeight: 700, marginBottom: "10px" } }, _L("Grupper", "Groups")),
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
