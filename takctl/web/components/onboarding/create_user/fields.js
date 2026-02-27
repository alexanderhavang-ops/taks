/* global React */
(function () {
  var h = (window.h || React.createElement); window.h = h;

  window.TaksOnboarding = window.TaksOnboarding || {};
  window.TaksOnboarding.createUser = window.TaksOnboarding.createUser || {};

  const helpers = (window.TaksOnboarding.createUser && window.TaksOnboarding.createUser.helpers) || null;
  function needHelpers(){ if (!helpers) throw new Error("Missing create_user/helpers.js"); return helpers; }
  function LP(){ return needHelpers().LP; }

  function Field({ label, children }) {
    return h(
      "div",
      { style: { display: "flex", flexDirection: "column", gap: "6px" } },
      h("div", { className: "muted", style: { fontSize: "12px" } }, label),
      children
    );
  }

  function RenderField({ f, value, onChange, right }) {
    const t = String((f && f.type) || "text").toLowerCase();
    const required = !!(f && f.required);
    const ro = !!(f && f.readonly);
    const ph = (f && f.key) ? String(f.key) : "";
    const label = (f && f.label) ? String(f.label) : ph;

    function wrapControl(ctrl){
      if (!right) return ctrl;
      return h("div", { style: { display: "flex", gap: "10px", alignItems: "center" } },
        h("div", { style: { flex: 1, minWidth: 0 } }, ctrl),
        right
      );
    }

    if (t === "select") {
      const opts = (f && f.options) || [];
      return h(Field, { label: required ? (label + " *") : label },
        wrapControl(
          h("select", Object.assign({}, LP(), { value: String(value ?? ""), disabled: ro, onChange: e => onChange(e.target.value) }),
            opts.map(o => h("option", { key: String(o), value: String(o) }, String(o)))
          )
        )
      );
    }

    if (t === "bool") {
      return h("label", { style: { display: "flex", gap: "10px", alignItems: "center" } },
        h("input", Object.assign({}, LP(), { type: "checkbox", checked: !!value, disabled: ro, onChange: e => onChange(!!e.target.checked) })),
        h("span", null, required ? (label + " *") : label)
      );
    }

    if (t === "csv") {
      return h(Field, { label: required ? (label + " *") : label },
        wrapControl(
          h("input", Object.assign({}, LP(), { type: "text", value: String(value ?? ""), readOnly: ro, placeholder: "comma,separated,groups", onChange: e => onChange(e.target.value) }))
        )
      );
    }

    const isNum = t === "number" || t === "int";
    return h(Field, { label: required ? (label + " *") : label },
      wrapControl(
        h("input", Object.assign({}, LP(), { type: isNum ? "number" : "text", value: String(value ?? ""), readOnly: ro, placeholder: ph, onChange: e => onChange(e.target.value) }))
      )
    );
  }

  window.TaksOnboarding.createUser.fields = { Field, RenderField };
})();
