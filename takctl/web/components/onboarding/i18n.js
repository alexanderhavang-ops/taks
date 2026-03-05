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
      "page.onboarding_edit": "Onboarding — Edit user",
      "page.onboarding_list": "Onboarding — List",

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
      "field.team": "Team",
      "field.team_color": "Team color", // legacy key (older UI)
      "field.battalion": "Battalion",
      "field.battalion_fal": "FALA Battalion",
      "field.company": "Company",
      "field.platoon": "Platoon",
      "field.group": "Group",
      "field.number": "Number",
      "field.n": "Number",

      // list table
      "list.live_view": "Live view from /api/onboarding/status",
      "list.loading": "Loading…",
      "list.username": "Username",
      "list.groups": "Groups",
      "list.onboard": "Onboard",
      "list.state": "State",
      "list.age": "Age",
      "list.callsign_uid": "Callsign / UID",
      "list.actions": "Actions",
      "list.unmanaged_endpoints": "Unmanaged endpoints",

      // buttons
      "btn.create_user": "Create user",
      "btn.save_changes": "Save changes",
      "btn.edit": "Edit",
      "btn.card": "Card",

      // advanced / client-profile
      "field.atak_role_type": "ATAK Role (My Role)",
      "field.atak_role": "ATAK Role (My Role)", // legacy key (older UI)
      "field.remarks": "Remarks",
      "hint.remarks": "Use hashtags, e.g. #soldier",

      // presets (display values)
      "role.soldier": "Soldier",
      "role.team_lead": "Team Lead",

      // soldier card (server-rendered page)
      "soldier.title": "Soldier Card",
      "soldier.atak_import": "ATAK — Import package",
      "soldier.step1": "Scan QR to import server + identity defaults",
      "soldier.step2": "Enter credentials (if provided)",
      "soldier.step3": "Connect",
      "soldier.profile": "Profile",
      "soldier.lifecycle": "Lifecycle",
      "soldier.credentials": "Credentials",
      "soldier.token_expires": "Expires",
      "soldier.token_url": "Token URL",
      "soldier.copy": "Copy",
      "soldier.password_unknown": "Password: unknown (origin=marti)",
      "soldier.password_external": "This user appears created outside TAKS. Ask admin for out-of-band password or reset."
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
      "page.onboarding_edit": "Onboarding — Redigera användare",
      "page.onboarding_list": "Onboarding — Lista",

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
      "field.team": "Lag",
      "field.team_color": "Lagfärg", // legacy key (older UI)
      "field.battalion": "Bataljon",
      "field.battalion_fal": "FALA bataljon",
      "field.company": "Kompani",
      "field.platoon": "Pluton",
      "field.group": "Grupp",
      "field.number": "Nummer",
      "field.n": "Nummer",

      // list table
      "list.live_view": "Live vy från /api/onboarding/status",
      "list.loading": "Laddar…",
      "list.username": "Användarnamn",
      "list.groups": "Grupper",
      "list.onboard": "Onboard",
      "list.state": "Status",
      "list.age": "Ålder",
      "list.callsign_uid": "Anropssignal / UID",
      "list.actions": "Åtgärder",
      "list.unmanaged_endpoints": "Ohanterade klienter",

      // buttons
      "btn.create_user": "Skapa användare",
      "btn.save_changes": "Spara ändringar",
      "btn.edit": "Redigera",
      "btn.card": "Kort",

      // advanced / client-profile
      "field.atak_role_type": "ATAK-roll (Min roll)",
      "field.atak_role": "ATAK-roll (Min roll)", // legacy key (older UI)
      "field.remarks": "Kommentarer",
      "hint.remarks": "Använd hashtags, t.ex. #soldat",

      // presets (display values)
      "role.soldier": "Soldat",
      "role.team_lead": "Gruppchef",

      // soldier card (server-rendered page)
      "soldier.title": "Soldatkort",
      "soldier.atak_import": "ATAK — Importpaket",
      "soldier.step1": "Skanna QR för att importera server + identitet",
      "soldier.step2": "Ange uppgifter (om tillhandahålls)",
      "soldier.step3": "Anslut",
      "soldier.profile": "Profil",
      "soldier.lifecycle": "Livscykel",
      "soldier.credentials": "Autentisering",
      "soldier.token_expires": "Går ut",
      "soldier.token_url": "Token-URL",
      "soldier.copy": "Kopiera",
      "soldier.password_unknown": "Lösenord: okänt (origin=marti)",
      "soldier.password_external": "Denna användare skapades utanför TAKS. Be admin om lösenord eller återställning."
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

  window.addEventListener("TAKS_LANG_CHANGED", () => {
    try { applyToDOM(document); } catch (e) { /* ignore */ }
  });

})();
