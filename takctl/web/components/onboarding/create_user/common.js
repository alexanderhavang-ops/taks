/* global React */
(function () {
  var h = (window.h || React.createElement); window.h = h;

  const t = (window.t && typeof window.t === "function") ? window.t : (k) => String(k || "");

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

  function norm(s) {
    return String(s || "").trim();
  }

  function labelForKey(k, fallbackLabel) {
    const key = String(k || "");
    if (!key) return String(fallbackLabel || "");
    if (key === "n") {
      const v = t("field.number");
      return (v && v !== "field.number") ? v : (fallbackLabel || "Number");
    }
    const tk = "field." + key;
    const v = t(tk);
    if (v && v !== tk) {
      if (ATAK_PREF_KEYS.has(key)) return v + " (" + key + ")";
      return v;
    }
    return String(fallbackLabel || key);
  }

  function Field(props) {
    return h("div", { style: { display: "flex", flexDirection: "column", gap: "6px" } },
      h("div", { className: "muted", style: { fontSize: "12px" } }, props.label),
      props.children
    );
  }

  function RenderField(props) {
    const f = props.f || {};
    const value = props.value;
    const onChange = props.onChange;

    const ty = String(f.type || "text").toLowerCase();
    const required = !!f.required;
    const ro = !!f.readonly;
    const ph = f.key ? String(f.key) : "";
    const rawLabel = f.label ? String(f.label) : ph;
    const k = String(f.key || "");
    const label = labelForKey(k, rawLabel);

    if (ty === "select") {
      const opts = f.options || [];

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
              onChange: function (e) { onChange(e.target.value); }
            })),
            h("datalist", { id: dlId },
              opts.map(function (o) {
                return h("option", { key: String(o), value: String(o) }, String(o));
              })
            )
          )
        );
      }

      return h(Field, { label: required ? (label + " *") : label },
        h("select", Object.assign({}, LP, {
          value: String(value ?? ""),
          disabled: ro,
          onChange: function (e) { onChange(e.target.value); }
        }),
          opts.map(function (o) {
            return h("option", { key: String(o), value: String(o) }, String(o));
          })
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
            onChange: function (e) { onChange(!!e.target.checked); }
          })),
          h("span", null, "")
        )
      );
    }

    const isNum = ty === "number" || ty === "int";
    return h(Field, { label: required ? (label + " *") : label },
      h("input", Object.assign({}, LP, {
        type: isNum ? "number" : "text",
        value: String(value ?? ""),
        readOnly: ro,
        placeholder: ph,
        onChange: function (e) { onChange(e.target.value); }
      }))
    );
  }

  function Tabs(props) {
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
      (props.tabs || []).map(function (tt) {
        const active = props.value === tt.id;
        return h("button", {
          key: tt.id,
          type: "button",
          onClick: function () { props.onChange(tt.id); },
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

  const CALLSIGN_POLICIES = [
    { id: "FAL", label: "FAL" },
    { id: "FALFAL", label: "FALFAL" },
    { id: "FAL_TAK", label: "FAL-TAK" },
  ];

  const LS_KEY_DEFAULT_CALLSIGN_POLICY = "taks.callsign_policy_default";

  function lsGet(key, defVal) {
    try {
      const v = window.localStorage ? window.localStorage.getItem(String(key)) : null;
      return (v == null || String(v).trim() === "") ? defVal : String(v);
    } catch (e) {
      return defVal;
    }
  }

  function lsSet(key, val) {
    try {
      if (!window.localStorage) return;
      window.localStorage.setItem(String(key), String(val));
    } catch (e) {}
  }

  function isValidPolicyId(x) {
    const s = String(x || "").trim().toUpperCase();
    return s === "GENERIC" || s === "FAL" || s === "FALFAL" || s === "FAL_TAK" || s === "FALSPECIAL";
  }

  function normalizePolicyId(x) {
    const s = String(x || "").trim().toUpperCase();
    if (s === "FALSPECIAL") return "FAL_TAK";
    if (isValidPolicyId(s)) return s;
    return "";
  }

  function effectiveCallsignPolicy(userOverride, globalDefault) {
    const u = normalizePolicyId(userOverride);
    if (u) return u;
    const g = normalizePolicyId(globalDefault);
    return g || "FAL_TAK";
  }

  function PolicySelect(props) {
    const v = String(props.value || "");
    return h("select", Object.assign({}, LP, {
      value: v,
      onChange: function (e) { props.onChange(e.target.value); }
    }),
      props.includeDefaultOption ? h("option", { value: "" }, "Default (global)") : null,
      CALLSIGN_POLICIES.map(function (p) {
        return h("option", { key: p.id, value: p.id }, p.label);
      })
    );
  }

  window.TaksOnboarding = window.TaksOnboarding || {};
  window.TaksOnboarding.createUser = window.TaksOnboarding.createUser || {};
  window.TaksOnboarding.createUser.common = {
    LP: LP,
    norm: norm,
    labelForKey: labelForKey,
    Field: Field,
    RenderField: RenderField,
    Tabs: Tabs,
    CALLSIGN_POLICIES: CALLSIGN_POLICIES,
    LS_KEY_DEFAULT_CALLSIGN_POLICY: LS_KEY_DEFAULT_CALLSIGN_POLICY,
    lsGet: lsGet,
    lsSet: lsSet,
    isValidPolicyId: isValidPolicyId,
    normalizePolicyId: normalizePolicyId,
    effectiveCallsignPolicy: effectiveCallsignPolicy,
    PolicySelect: PolicySelect
  };
})();
