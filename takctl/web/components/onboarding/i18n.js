// takctl/web/components/onboarding/i18n.js
// Simple deterministic i18n helper for takctl frontend

(function () {
  if (window.TAKS_I18N) return;

  const DICTS = {
    en: {
      "nav.onboarding": "Onboarding",
      "nav.list": "List",
      "nav.create_user": "Create user",
      "nav.import_users": "Import users file",
      "nav.import_jobs": "Import jobs",
      "nav.section": "Section",
      "nav.ai": "AI",
      "nav.ai3": "AI3",
      "nav.ai_costs": "AI Costs",
      "nav.martine": "Martine",
      "nav.simulate": "Simulate",
      "nav.documents": "Documents",
      "nav.settings": "Settings",

      "page.onboarding_create": "Onboarding — Create user",
      "page.onboarding_edit": "Onboarding — Edit user",
      "page.onboarding_list": "Onboarding — List",

      "policy.label": "Policy",
      "policy.open_pdf": "Open policy PDF",
      "policy.node_global": "Policy is node-global.",
      "policy.up_to_date": "Up to date",

      "tab.identity": "Identity",
      "tab.account": "Account",
      "tab.advanced": "Advanced",

      "field.callsign": "Callsign",
      "field.team": "Team",
      "field.team_color": "Team color",
      "field.battalion": "Battalion",
      "field.battalion_fal": "FALA Battalion",
      "field.company": "Company",
      "field.platoon": "Platoon",
      "field.group": "Group",
      "field.number": "Number",
      "field.n": "Number",

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
      "list.selected_count": "Selected={selected} / {total}",
      "list.select_all": "Select all",
      "list.clear_selection": "Clear selection",
      "list.print_mode": "Print mode",
      "list.print_selected": "Print selected",
      "list.print_all": "Print all",
      "list.summary": "Users={users}  Seen={seen}  Never={never}  Unknown={unknown}  DB={db} ({source})",

      "btn.create_user": "Create user",
      "btn.save_changes": "Save changes",
      "btn.edit": "Edit",
      "btn.card": "Card",
      "btn.working": "Working...",
      "btn.sending": "Sending...",
      "btn.email_card_link": "Email card link",
      "page.onboarding_create_title": "Create user",
      "page.onboarding_edit_title": "Edit user",
      "page.onboarding_subtitle": "Identity and artifacts are now controlled by global onboarding config.",
      "btn.logout": "Logout",

      "field.atak_role_type": "ATAK Role (My Role)",
      "field.atak_role": "ATAK Role (My Role)",
      "field.remarks": "Remarks",
      "hint.remarks": "Use hashtags, e.g. #soldier",

      "role.soldier": "Soldier",
      "role.team_lead": "Team Lead",

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
      "nav.onboarding": "Onboarding",
      "nav.list": "Lista",
      "nav.create_user": "Skapa användare",
      "nav.import_users": "Importera användarfil",
      "nav.import_jobs": "Importjobb",
      "nav.section": "Sektion",
      "nav.ai": "AI",
      "nav.ai3": "AI3",
      "nav.ai_costs": "AI-kostnader",
      "nav.martine": "Martine",
      "nav.simulate": "Simulera",
      "nav.documents": "Dokument",
      "nav.settings": "Inställningar",

      "page.onboarding_create": "Onboarding — Skapa användare",
      "page.onboarding_edit": "Onboarding — Redigera användare",
      "page.onboarding_list": "Onboarding — Lista",

      "policy.label": "Policy",
      "policy.open_pdf": "Öppna policy-PDF",
      "policy.node_global": "Policyn är nodglobal.",
      "policy.up_to_date": "Uppdaterad",

      "tab.identity": "Identitet",
      "tab.account": "Konto",
      "tab.advanced": "Avancerat",

      "field.callsign": "Anropssignal",
      "field.team": "Lag",
      "field.team_color": "Lagfärg",
      "field.battalion": "Bataljon",
      "field.battalion_fal": "FALA bataljon",
      "field.company": "Kompani",
      "field.platoon": "Pluton",
      "field.group": "Grupp",
      "field.number": "Nummer",
      "field.n": "Nummer",

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
      "list.selected_count": "Valda={selected} / {total}",
      "list.select_all": "Välj alla",
      "list.clear_selection": "Rensa val",
      "list.print_mode": "Utskriftsläge",
      "list.print_selected": "Skriv ut valda",
      "list.print_all": "Skriv ut alla",
      "list.summary": "Användare={users}  Sedda={seen}  Aldrig={never}  Okända={unknown}  DB={db} ({source})",

      "btn.create_user": "Skapa användare",
      "btn.save_changes": "Spara ändringar",
      "btn.edit": "Redigera",
      "btn.card": "Kort",
      "btn.working": "Arbetar...",
      "btn.sending": "Skickar...",
      "btn.email_card_link": "Maila kortlänk",
      "page.onboarding_create_title": "Skapa användare",
      "page.onboarding_edit_title": "Redigera användare",
      "page.onboarding_subtitle": "Identitet och artefakter styrs nu av global onboarding-konfig.",
      "btn.logout": "Logga ut",

      "field.atak_role_type": "ATAK-roll (Min roll)",
      "field.atak_role": "ATAK-roll (Min roll)",
      "field.remarks": "Kommentarer",
      "hint.remarks": "Använd hashtags, t.ex. #soldat",

      "role.soldier": "Soldat",
      "role.team_lead": "Gruppchef",

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

  const DEFAULT = "sv";

  function readRuntimeLang() {
    const v = String(window.TAKS_RUNTIME_LANGUAGE || DEFAULT).toLowerCase();
    if (DICTS[v]) return v;
    return DEFAULT;
  }

  let current = readRuntimeLang();

  function setLang(lang) {
    if (!DICTS[lang]) {
      console.warn("i18n: unknown lang", lang);
      return;
    }
    current = lang;
    window.currentLang = current;
    window.dispatchEvent(new CustomEvent("TAKS_LANG_CHANGED", { detail: { lang } }));
  }

  function t(key, opts) {
    const dict = DICTS[current] || DICTS[DEFAULT];
    let str = dict && dict[key];
    if (str == null) {
      str = (DICTS["en"] && DICTS["en"][key]) || key;
    }
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

  window.TAKS_I18N = DICTS;
  window.setTaksLang = setLang;
  window.t = t;
  window.tOr = tOr;
  window.currentLang = current;

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
    try { applyToDOM(document); } catch (e) {}
  });
})();
