// takctl/web/components/onboarding/i18n.js
// Simple deterministic i18n helper for takctl frontend
// Usage: t("nav.create_user") => localized string
// Put this file under takctl/web/components/onboarding/ and include it before your onboarding scripts.

(function () {
  if (window.TAKS_I18N) return; // don't re-init in HMR/dev double-load

  const DICTS = {
    en: {
      // nav / layout
      "nav.onboarding": "Onboarding",
      "nav.list": "List",
      "nav.create_user": "Create user",
      "nav.import_users": "Import users file",
      "nav.section": "Section",

      // header / policy
      "page.onboarding_create": "Onboarding — Create user",
      "policy.label": "Policy",
      "policy.open_pdf": "Open policy PDF",
      "policy.node_global": "Policy is node-global.",
      "policy.up_to_date": "Up to date",

      // tabs
      "tab.identity": "Identity",
      "tab.account": "Account",
      "tab.advanced": "Advanced",

      // identity fields (source)
      "field.callsign": "Callsign",
      "field.team_color": "Team color",
      "field.battalion": "Battalion",
      "field.company": "Company",
      "field.platoon": "Platoon",
      "field.number": "Number",

      // derived
      "derived.title": "Derived outputs",
      "derived.hint": "Edits here are temporary; changing source fields re-derives and overwrites them.",
      "derived.team": "Team",

      // buttons
      "btn.copy_callsign": "Copy callsign",
      "btn.copy_team": "Copy team",
      "btn.create_user": "Create user",

      // advanced / client-profile
      "field.atak_role": "ATAK Role (My Role)",
      "field.remarks": "Remarks",
      "hint.remarks": "Use hashtags, e.g. #soldier",

      // presets (display values)
      "role.soldier": "Soldier",
      "role.team_lead": "Team Lead"
    },

    sv: {
      // nav / layout
      "nav.onboarding": "Onboarding",
      "nav.list": "Lista",
      "nav.create_user": "Skapa användare",
      "nav.import_users": "Importera användarfil",
      "nav.section": "Sektion",

      // header / policy
      "page.onboarding_create": "Onboarding — Skapa användare",
      "policy.label": "Policy",
      "policy.open_pdf": "Öppna policy-PDF",
      "policy.node_global": "Policyn är nodglobal.",
      "policy.up_to_date": "Uppdaterad",

      // tabs
      "tab.identity": "Identitet",
      "tab.account": "Konto",
      "tab.advanced": "Avancerat",

      // identity fields (source)
      "field.callsign": "Anropssignal",
      "field.team_color": "Lagfärg",
      "field.battalion": "Bataljon",
      "field.company": "Kompani",
      "field.platoon": "Pluton",
      "field.number": "Nummer",

      // derived
      "derived.title": "Härlett",
      "derived.hint": "Ändringar här är temporära; när du ändrar källfälten härleds värdena om och skriver över dina ändringar.",
      "derived.team": "Lag",

      // buttons
      "btn.copy_callsign": "Kopiera anropssignal",
      "btn.copy_team": "Kopiera lag",
      "btn.create_user": "Skapa användare",

      // advanced / client-profile
      "field.atak_role": "ATAK-roll (Min roll)",
      "field.remarks": "Kommentarer",
      "hint.remarks": "Använd hashtags, t.ex. #soldat",

      // presets (display values)
      "role.soldier": "Soldat",
      "role.team_lead": "Gruppchef"
    }
  };

  // default language selection: use localStorage or fall back to sv (Swedish)
  const DEFAULT = "sv";
  const LS_KEY = "taks_ui_lang";

  function readSaved() {
    try {
      const v = localStorage.getItem(LS_KEY);
      if (v && DICTS[v]) return v;
    } catch (e) { /* ignore */ }
    // fallback heuristic: use browser lang if it starts with en
    const nav = (navigator.language || navigator.userLanguage || "").toLowerCase();
    if (nav && nav.startsWith("en")) return "en";
    return DEFAULT;
  }

  let current = readSaved();

  function setLang(lang) {
    if (!DICTS[lang]) {
      console.warn("i18n: unknown lang", lang);
      return;
    }
    current = lang;
    try { localStorage.setItem(LS_KEY, lang); } catch (e) {}
    // expose for debugging
    window.currentLang = current;
    // dispatch an event so UI can re-render if it wants to listen
    window.dispatchEvent(new CustomEvent("TAKS_LANG_CHANGED", { detail: { lang } }));
  }

  function t(key, opts) {
    const dict = DICTS[current] || DICTS[DEFAULT];
    let str = dict && dict[key];
    if (str == null) {
      // fallback to english then to key
      str = (DICTS["en"] && DICTS["en"][key]) || key;
    }
    // simple interpolation support, opts = {name:"x"}
    if (opts && typeof opts === "object") {
      Object.keys(opts).forEach(k => {
        str = str.split(`{${k}}`).join(String(opts[k]));
      });
    }
    return str;
  }

  function tOr(key, fallback) {
    const dict = DICTS[current] || DICTS[DEFAULT];
    const val = dict && dict[key];
    if (val != null) return val;
    if (DICTS["en"] && DICTS["en"][key]) return DICTS["en"][key];
    return fallback;
  }

  // Expose
  window.TAKS_I18N = DICTS;
  window.setTaksLang = setLang;
  window.t = t;
  window.tOr = tOr;
  window.currentLang = current;

  // small helper: auto-translate DOM nodes with data-i18n attribute (if used)
  // <span data-i18n="nav.create_user"></span>
  function applyToDOM(root = document) {
    const nodes = root.querySelectorAll("[data-i18n]");
    nodes.forEach(n => {
      const key = n.getAttribute("data-i18n");
      if (!key) return;
      const txt = t(key);
      if (n.tagName === "INPUT" || n.tagName === "TEXTAREA") {
        n.placeholder = txt;
      } else if (n.hasAttribute("data-i18n-html")) {
        n.innerHTML = txt;
      } else {
        n.textContent = txt;
      }
    });
  }

  window.taksI18nApply = applyToDOM;

  // when language changes, reapply to DOM automatically
  window.addEventListener("TAKS_LANG_CHANGED", () => {
    try { applyToDOM(document); } catch (e) { /* ignore */ }
  });

})();
