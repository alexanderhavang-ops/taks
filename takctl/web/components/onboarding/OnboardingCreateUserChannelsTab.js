/* global React */
(function () {
  var h = (window.h || React.createElement); window.h = h;

  function _lang() {
    const v = String(window.currentLang || window.TAKS_RUNTIME_LANGUAGE || "sv").trim().toLowerCase();
    return v.startsWith("en") ? "en" : "sv";
  }

  function _L(sv, en) {
    return _lang() === "en" ? String(en) : String(sv);
  }

  function _uniq(items) {
    const out = [];
    const seen = {};
    (Array.isArray(items) ? items : []).forEach(function (x) {
      const s = String(x || "").trim();
      if (!s || seen[s]) return;
      seen[s] = true;
      out.push(s);
    });
    return out;
  }

  function OnboardingCreateUserChannelsTab(props) {
    const available = _uniq(props.available || []);
    const selected = _uniq(props.selected || []);
    const defaults = _uniq(props.defaultChannels || []);
    const setSelected = props.setSelected;
    const loading = !!props.loading;
    const error = String(props.error || "");

    const selectedMap = {};
    selected.forEach(function (x) { selectedMap[x] = true; });

    function saveList(xs) {
      if (typeof setSelected === "function") setSelected(_uniq(xs));
    }

    function toggle(ch) {
      if (selectedMap[ch]) {
        const next = selected.filter(function (x) { return x !== ch; });
        saveList(next.length ? next : defaults);
      } else {
        saveList(selected.concat([ch]));
      }
    }

    const selectedText = selected.length ? selected.join(", ") : "—";

    return h("div", null,
      h("div", { style: { fontWeight: 700, marginBottom: "10px" } },
        _L("Kanaler", "Channels")
      ),

      h("div", { className: "muted", style: { marginBottom: "12px", lineHeight: 1.45 } },
        _L(
          "Kanallistan sparas i användarens onboardingprofil och används av Mumble/VX nästa gång ett voice-onboardingpaket skapas. OpenFire/XMPP-bookmarks skrivs inte automatiskt i denna save-path ännu.",
          "The channel list is saved in the user's onboarding profile and used by Mumble/VX next time a voice onboarding package is created. OpenFire/XMPP bookmarks are not written automatically by this save path yet."
        )
      ),

      loading ? h("div", { className: "note", style: { marginBottom: "10px" } },
        _L("Beräknar tillgängliga kanaler…", "Deriving available channels…")
      ) : null,

      error ? h("div", { className: "note", style: { marginBottom: "10px" } },
        "ERR: ", error
      ) : null,

      h("div", { style: { display: "flex", gap: "10px", flexWrap: "wrap", marginBottom: "12px" } },
        h("button", {
          type: "button",
          className: "btn",
          onClick: function () { saveList(defaults); }
        }, _L("Återställ till standard", "Reset to default")),

        h("button", {
          type: "button",
          className: "btn",
          onClick: function () { saveList(available); }
        }, _L("Välj alla", "Select all")),

        h("span", { className: "muted", style: { alignSelf: "center", fontSize: "12px" } },
          _L("Minst en kanal sparas; tomt val återgår till standard.", "At least one channel is saved; an empty selection falls back to default.")
        )
      ),

      h("div", { className: "note", style: { marginBottom: "12px" } },
        h("div", { style: { fontWeight: 800, marginBottom: "4px" } },
          _L("Valda kanaler", "Selected channels")
        ),
        h("div", null, selectedText)
      ),

      h("div", {
        className: "grid",
        style: { gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "8px" }
      },
        available.length ? available.map(function (ch) {
          const on = !!selectedMap[ch];
          const isDefault = defaults.indexOf(ch) >= 0;
          return h("label", {
            key: ch,
            style: {
              display: "flex",
              gap: "10px",
              alignItems: "center",
              padding: "9px 10px",
              border: "1px solid rgba(255,255,255,0.10)",
              borderRadius: "10px",
              background: on ? "rgba(80,200,120,0.10)" : "rgba(255,255,255,0.03)"
            }
          },
            h("input", {
              type: "checkbox",
              checked: on,
              onChange: function () { toggle(ch); }
            }),
            h("span", { style: { fontWeight: on ? 800 : 500 } }, ch),
            isDefault ? h("span", { className: "muted", style: { marginLeft: "auto", fontSize: "11px" } },
              _L("standard", "default")
            ) : null
          );
        }) : h("div", { className: "muted" }, _L("Inga kanaler hittades.", "No channels found."))
      )
    );
  }

  window.OnboardingCreateUserChannelsTab = OnboardingCreateUserChannelsTab;
})();
