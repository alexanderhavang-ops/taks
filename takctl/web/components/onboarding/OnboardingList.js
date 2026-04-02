/* global React */
(function () {
  var h = (window.h || React.createElement); window.h = h;

  const useState = React.useState;
  const useMemo = React.useMemo;
  const useEffect = React.useEffect;

  const _t = (window.t || function (k) { return k; });

  // shared onboarding helpers
  const lib = (window.TaksOnboarding && window.TaksOnboarding.lib) || null;
  function _needLib() { if (!lib) throw new Error('Missing onboarding lib: load components/onboarding/lib.js before Onboarding.js'); return lib; }
  function _colText(v){ return _needLib().colText(v); }
  function _groups(u){ return _needLib().groups(u); }
  function _tail(act){ return _needLib().tail(act); }
  function _deriveState(act){ return _needLib().deriveState(act); }
  function _badgeForState(stateRaw){ return _needLib().badgeForState(stateRaw); }
  function _userUrls(username){ return _needLib().userUrls(username); }
  function _splitCsv(s){ return _needLib().splitCsv(s); }

  const PRINT_MODES = [
    { id: "cards", label: "Cards only" },
    { id: "passwords", label: "Passwords only" },
    { id: "cards_inline_passwords", label: "Cards + passwords same page" },
    { id: "cards_then_passwords", label: "Cards + passwords separate pages" },
  ];

  function _rowUsername(u) {
    const hdr = (u && u.header) || {};
    return String(hdr.username || u.username || "");
  }

  function _submitPrintPack(usernames, printMode) {
    const list = Array.isArray(usernames) ? usernames.filter(Boolean).map(String) : [];
    if (!list.length) {
      throw new Error("No users selected for print");
    }

    const form = document.createElement("form");
    form.method = "POST";
    form.action = "/api/onboarding/print-pack";
    form.target = "_blank";
    form.style.display = "none";

    const input = document.createElement("input");
    input.type = "hidden";
    input.name = "payload";
    input.value = JSON.stringify({
      usernames: list,
      print_mode: String(printMode || "cards"),
    });
    form.appendChild(input);

    document.body.appendChild(form);
    try {
      form.submit();
    } finally {
      document.body.removeChild(form);
    }
  }

  function PrintToolbar({
    rows,
    selectedMap,
    onClear,
    onSelectAllVisible,
    printMode,
    onPrintMode,
  }) {
    const usernames = (rows || []).map(_rowUsername).filter(Boolean);
    const selectedUsernames = usernames.filter((u) => !!selectedMap[u]);

    return h(
      "div",
      {
        className: "card",
        style: {
          marginBottom: "12px",
          padding: "12px",
          display: "flex",
          gap: "10px",
          flexWrap: "wrap",
          alignItems: "center"
        }
      },
      h("div", { className: "muted", style: { marginRight: "8px" } },
        _t("list.selected_count", { selected: _colText(selectedUsernames.length), total: _colText(usernames.length) })
      ),

      h("button", {
        className: "btn",
        type: "button",
        onClick: function () { onSelectAllVisible(); }
      }, _t("list.select_all")),

      h("button", {
        className: "btn",
        type: "button",
        onClick: function () { onClear(); }
      }, _t("list.clear_selection")),

      h("div", { className: "muted", style: { marginLeft: "6px" } }, _t("list.print_mode") + ":"),

      h("select", {
        className: "inp",
        value: String(printMode || "cards"),
        onChange: function (e) { onPrintMode(String(e.target.value || "cards")); },
        style: { minWidth: "260px" }
      },
        PRINT_MODES.map(function (m) {
          return h("option", { key: m.id, value: m.id }, m.label);
        })
      ),

      h("button", {
        className: "btn",
        type: "button",
        disabled: selectedUsernames.length === 0,
        onClick: function () {
          _submitPrintPack(selectedUsernames, printMode);
        }
      }, _t("list.print_selected")),

      h("button", {
        className: "btn",
        type: "button",
        disabled: usernames.length === 0,
        onClick: function () {
          _submitPrintPack(usernames, printMode);
        }
      }, _t("list.print_all"))
    );
  }

  // ---------------------------------------------------------------------------
  // tables (List)
  // ---------------------------------------------------------------------------
  function OnboardingTable({ rows, selectedMap, onToggleOne, onToggleAllVisible }) {
    const allUsernames = (rows || []).map(_rowUsername).filter(Boolean);
    const allSelected = allUsernames.length > 0 && allUsernames.every((u) => !!selectedMap[u]);

    return h(
      "table",
      { className: "tbl" },
      h(
        "thead",
        null,
        h(
          "tr",
          null,
          h("th", { style: { width: "36px" } },
            h("input", {
              type: "checkbox",
              checked: !!allSelected,
              onChange: function () { onToggleAllVisible(); }
            })
          ),
          h("th", null, _t("list.username")),
          h("th", null, _t("list.groups")),
          h("th", null, _t("list.onboard")),
          h("th", null, _t("list.state")),
          h("th", null, _t("list.age")),
          h("th", null, _t("list.callsign_uid")),
          h("th", null, _t("list.actions"))
        )
      ),
      h(
        "tbody",
        null,
        (rows || []).map((u) => {
          const hdr = (u && u.header) || {};
          const act = (u && u.activity) || null;

          const username = String(hdr.username || u.username || "");
          const groupsArr =
            (hdr && Array.isArray(hdr.groups) ? hdr.groups :
             (u && u.marti && Array.isArray(u.marti.groups) ? u.marti.groups :
              (u && Array.isArray(u.groups) ? u.groups : [])));

          const onboardRaw = (u && u.onboarding_status) || "";
          const onboard = String(onboardRaw || "").toUpperCase();

          const state = act ? _deriveState(act) : "never";
          const key = username + ":" + String((act && act.uid) || "");
          const urls = _userUrls(username);

          const groupsTxt = groupsArr.length ? groupsArr.join(", ") : "—";
          const callsign = (hdr && hdr.callsign) ? String(hdr.callsign) : "—";
          const uid = (act && act.uid) ? String(act.uid) : "—";

          return h(
            "tr",
            { key },
            h("td", null,
              h("input", {
                type: "checkbox",
                checked: !!selectedMap[username],
                onChange: function () { onToggleOne(username); }
              })
            ),
            h("td", null,
              h("button", {
                type: "button",
                className: "btn",
                style: { padding: "4px 8px" },
                onClick: function () {
                  try {
                    const lib = (window.TaksOnboarding && window.TaksOnboarding.lib) || null;
                    if (lib && typeof lib.setHashRoute === "function") lib.setHashRoute("detail", username);
                    else window.location.hash = "#onboarding/detail:" + encodeURIComponent(username);
                  } catch (e) {}
                }
              }, _colText(username || "—"))
            ),
            h("td", null, _colText(groupsTxt)),
            h("td", null, _colText(onboard || "—")),
            h("td", null, _badgeForState(state)),
            h("td", null, _colText(act ? act.age_human : "—")),
            h("td", null, _colText(`${callsign} / ${uid}`)),
            h(
              "td",
              null,
              h(
                "div",
                { style: { display: "flex", gap: "8px", flexWrap: "wrap", alignItems: "center" } },
                h(
                  "a",
                  {
                    className: "btn",
                    href: (function(){
                      try {
                        return urls.card;
                      } catch (e) { return urls.card; }
                    })(),
                    target: "_blank",
                    rel: "noopener noreferrer",
                    title: "Open the onboarding card (QR codes + links)",
                  },
                  _t("btn.card")
                ),
                h(
                  "button",
                  {
                    className: "btn",
                    onClick: function () {
                      try {
                        const lib = (window.TaksOnboarding && window.TaksOnboarding.lib) || null;
                        if (lib && typeof lib.setHashRoute === "function") lib.setHashRoute("create", username);
                        else window.location.hash = "#onboarding/create:" + encodeURIComponent(username);
                      } catch (e) {}
                    }
                  },
                  _t("btn.edit")
                )
              )
            )
          );
        })
      )
    );
  }

  function UnknownTable({ rows }) {
    return h(
      "table",
      { className: "tbl" },
      h(
        "thead",
        null,
        h(
          "tr",
          null,
          h("th", null, _t("list.username")),
          h("th", null, _t("list.state")),
          h("th", null, _t("list.age")),
          h("th", null, _t("field.callsign")),
          h("th", null, "UID")
        )
      ),
      h(
        "tbody",
        null,
        (rows || []).map((e) => {
          const state =
            (e && (e.is_current === true ? "current" : (e.seen_recently === true ? "recent" : "stale"))) || "—";
          return h(
            "tr",
            { key: (e.username || "") + ":" + (e.uid || "") },
            h("td", null, _colText(e.username)),
            h("td", null, _badgeForState(state)),
            h("td", null, _colText(e.age_human)),
            h("td", null, _colText(e.callsign)),
            h("td", null, _colText(e.uid))
          );
        })
      )
    );
  }

  function OnboardingListPage() {
    const data = useApi("api/onboarding/status", { cacheMs: 2000, pollMs: 10000 });

    const ok = data && data.ok;
    const d = (data && data.data) || {};
    const meta = d.meta || {};
    const summary = d.summary || {};
    const users = d.users || [];
    const unknown = d.unknown_endpoints || [];

    const [selectedMap, setSelectedMap] = useState({});
    const [printMode, setPrintMode] = useState("cards");

    useEffect(function () {
      const known = {};
      (users || []).forEach(function (u) {
        const username = _rowUsername(u);
        if (username) known[username] = true;
      });

      setSelectedMap(function (prev) {
        const out = {};
        Object.keys(prev || {}).forEach(function (k) {
          if (known[k] && prev[k]) out[k] = true;
        });
        return out;
      });
    }, [users]);

    function toggleOne(username) {
      const u = String(username || "");
      if (!u) return;
      setSelectedMap(function (prev) {
        const out = Object.assign({}, prev || {});
        if (out[u]) delete out[u];
        else out[u] = true;
        return out;
      });
    }

    function toggleAllVisible() {
      const usernames = (users || []).map(_rowUsername).filter(Boolean);
      const allSelected = usernames.length > 0 && usernames.every(function (u) { return !!selectedMap[u]; });

      setSelectedMap(function (prev) {
        const out = Object.assign({}, prev || {});
        if (allSelected) {
          usernames.forEach(function (u) { delete out[u]; });
        } else {
          usernames.forEach(function (u) { out[u] = true; });
        }
        return out;
      });
    }

    function clearSelection() {
      setSelectedMap({});
    }

    return h(
      "div",
      null,
      h("div", { className: "card-title" }, _t("page.onboarding_list")),
      h(
        "div",
        { className: "muted", style: { marginBottom: "8px" } },
        ok ? _t("list.live_view") : _t("list.loading")
      ),
      h(
        "div",
        { className: "muted", style: { marginBottom: "10px" } },
        _t("list.summary", {
          users: _colText(summary.total_users),
          seen: _colText(summary.cot_seen),
          never: _colText(summary.never_seen),
          unknown: _colText(summary.unknown_endpoints),
          db: (typeof meta.db_attached === "boolean") ? (meta.db_attached ? "attached" : "none") : "?",
          source: _colText((meta && meta.db_source) || "no meta")
        })
      ),

      h(PrintToolbar, {
        rows: users,
        selectedMap: selectedMap,
        onClear: clearSelection,
        onSelectAllVisible: toggleAllVisible,
        printMode: printMode,
        onPrintMode: setPrintMode
      }),

      h(OnboardingTable, {
        rows: users,
        selectedMap: selectedMap,
        onToggleOne: toggleOne,
        onToggleAllVisible: toggleAllVisible
      }),

      unknown && unknown.length
        ? h(
            "div",
            { style: { marginTop: "18px" } },
            h("div", { className: "card-title", style: { fontSize: "14px" } }, _t("list.unmanaged_endpoints")),
            h(UnknownTable, { rows: unknown })
          )
        : null
    );
  }

  window.OnboardingListPage = OnboardingListPage;
})();
