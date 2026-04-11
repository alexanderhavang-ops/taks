/* global React useApi */
(function () {
  var h = (window.h || React.createElement); window.h = h;

  const useState = React.useState;
  const useEffect = React.useEffect;

  const _t = (window.t || function (k) { return k; });

  const lib = (window.TaksOnboarding && window.TaksOnboarding.lib) || null;
  function _needLib() { if (!lib) throw new Error('Missing onboarding lib: load components/onboarding/lib.js before Onboarding.js'); return lib; }
  function _colText(v){ return _needLib().colText(v); }
  function _badgeForState(stateRaw){ return _needLib().badgeForState(stateRaw); }
  function _userState(row){ return _needLib().userState(row); }
  function _bestDevice(row){ return _needLib().bestDevice(row); }
  function _deviceTail(device){ return _needLib().deviceTail(device); }

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

  function _onboardTone(v) {
    const s = String(v || "").trim().toUpperCase();
    if (s === "DOWNLOADED" || s === "COMPLETE" || s === "ACTIVE") return "good";
    if (s === "NEW" || s === "PACKAGE_GENERATED" || s === "QR_GENERATED") return "warn";
    if (!s) return "neutral";
    return "neutral";
  }

  function _toneStyle(tone) {
    if (tone === "good") {
      return {
        border: "1px solid rgba(80,200,120,0.45)",
        background: "rgba(80,200,120,0.12)",
        color: "#b8f5c8"
      };
    }
    if (tone === "warn") {
      return {
        border: "1px solid rgba(240,190,70,0.45)",
        background: "rgba(240,190,70,0.12)",
        color: "#ffe29a"
      };
    }
    if (tone === "bad") {
      return {
        border: "1px solid rgba(255,90,90,0.45)",
        background: "rgba(255,90,90,0.12)",
        color: "#ffb3b3"
      };
    }
    return {
      border: "1px solid rgba(255,255,255,0.16)",
      background: "rgba(255,255,255,0.05)",
      color: "rgba(255,255,255,0.92)"
    };
  }

  function _pill(text, tone) {
    const st = _toneStyle(String(tone || "neutral"));
    return h("span", {
      style: {
        display: "inline-block",
        padding: "4px 10px",
        borderRadius: "999px",
        fontSize: "12px",
        fontWeight: 800,
        letterSpacing: "0.02em",
        whiteSpace: "nowrap",
        border: st.border,
        background: st.background,
        color: st.color
      }
    }, String(text || "—"));
  }

  function _voiceUser(row) {
    return ((row && row.voice) || {}).user || {};
  }

  function _voiceTone(row) {
    const voice = _voiceUser(row);
    const connectedNow = !!voice.connected_now;
    const matchedNames = Array.isArray(voice.matched_user_names) ? voice.matched_user_names : [];
    const serverConnected = !!((((row && row.voice) || {}).server || {}).connected);

    if (connectedNow) return "good";
    if (serverConnected && matchedNames.length) return "warn";
    if (serverConnected) return "neutral";
    return "bad";
  }

  function _voiceLabel(row) {
    const voice = _voiceUser(row);
    const connectedNow = !!voice.connected_now;
    const matchedNames = Array.isArray(voice.matched_user_names) ? voice.matched_user_names : [];
    const serverConnected = !!((((row && row.voice) || {}).server || {}).connected);

    if (connectedNow) return "ANSLUTEN";
    if (serverConnected && matchedNames.length) return "SEDD";
    if (serverConnected) return "—";
    return "SERVER NERE";
  }

  function _voiceChannels(row) {
    const voice = _voiceUser(row);
    const channels = Array.isArray(voice.channel_names) ? voice.channel_names : [];
    return channels.length ? channels.join(", ") : "—";
  }

  async function _openFreshCard(username) {
    const u = String(username || "").trim();
    if (!u) throw new Error("username required");

    const resp = await fetch("/api/onboarding/users/" + encodeURIComponent(u) + "/card-token", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({})
    });
    const j = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(j.detail || ("HTTP " + resp.status));

    const cardUrl = String((j && j.card_url) || "").trim();
    if (!cardUrl) throw new Error("missing card_url from card-token response");

    window.open(cardUrl, "_blank", "noopener,noreferrer");
  }

  function _submitPrintPack(usernames, printMode) {
    const list = Array.isArray(usernames) ? usernames.filter(Boolean).map(String) : [];
    if (!list.length) throw new Error("No users selected for print");

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

  async function _submitEmailPack(usernames, printMode) {
    const list = Array.isArray(usernames) ? usernames.filter(Boolean).map(String) : [];
    if (!list.length) throw new Error("No users selected for email");

    const resp = await fetch("/api/onboarding/email-pack", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        usernames: list,
        print_mode: String(printMode || "cards"),
      }),
    });

    let data = {};
    try { data = await resp.json(); } catch (e) { data = {}; }

    if (!resp.ok || data.ok === false) {
      const msg = (data && (data.detail || data.error)) ? String(data.detail || data.error) : ("HTTP " + resp.status);
      throw new Error(msg);
    }

    return data || {};
  }

  function PrintToolbar(props) {
    const rows = props.rows || [];
    const selectedMap = props.selectedMap || {};
    const usernames = rows.map(_rowUsername).filter(Boolean);
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
      h("button", { className: "btn", type: "button", onClick: function () { props.onSelectAllVisible(); } }, _t("list.select_all")),
      h("button", { className: "btn", type: "button", onClick: function () { props.onClear(); } }, _t("list.clear_selection")),
      h("div", { className: "muted", style: { marginLeft: "6px" } }, _t("list.print_mode") + ":"),
      h("select", {
        className: "inp",
        value: String(props.printMode || "cards"),
        onChange: function (e) { props.onPrintMode(String(e.target.value || "cards")); },
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
        onClick: function () { _submitPrintPack(selectedUsernames, props.printMode); }
      }, _t("list.print_selected")),
      h("button", {
        className: "btn",
        type: "button",
        disabled: usernames.length === 0,
        onClick: function () { _submitPrintPack(usernames, props.printMode); }
      }, _t("list.print_all")),
      h("button", {
        className: "btn",
        type: "button",
        disabled: selectedUsernames.length === 0,
        onClick: async function () {
          try {
            const out = await _submitEmailPack(selectedUsernames, props.printMode);
            window.alert(_t("list.email_result", {
              sent: _colText(out.sent),
              failed: _colText(out.failed),
              missing: _colText(out.missing_email),
            }));
          } catch (e) {
            window.alert(String((e && e.message) || e || "Email failed"));
          }
        }
      }, _t("list.email_selected")),
      h("button", {
        className: "btn",
        type: "button",
        disabled: usernames.length === 0,
        onClick: async function () {
          try {
            const out = await _submitEmailPack(usernames, props.printMode);
            window.alert(_t("list.email_result", {
              sent: _colText(out.sent),
              failed: _colText(out.failed),
              missing: _colText(out.missing_email),
            }));
          } catch (e) {
            window.alert(String((e && e.message) || e || "Email failed"));
          }
        }
      }, _t("list.email_all"))
    );
  }

  function _deviceSummary(row) {
    const ds = (row && Array.isArray(row.devices)) ? row.devices : [];
    if (!ds.length) return "0";
    let current = 0, recent = 0, stale = 0, never = 0;
    ds.forEach(function (d) {
      const s = String((d && d.state) || "never");
      if (s === "current") current += 1;
      else if (s === "recent") recent += 1;
      else if (s === "stale") stale += 1;
      else never += 1;
    });
    const bits = [];
    if (current) bits.push("C:" + current);
    if (recent) bits.push("R:" + recent);
    if (stale) bits.push("S:" + stale);
    if (never) bits.push("N:" + never);
    return String(ds.length) + " (" + bits.join(" ") + ")";
  }

  function OnboardingTable(props) {
    const rows = props.rows || [];
    const selectedMap = props.selectedMap || {};
    const allUsernames = rows.map(_rowUsername).filter(Boolean);
    const allSelected = allUsernames.length > 0 && allUsernames.every((u) => !!selectedMap[u]);

    return h(
      "table",
      { className: "tbl" },
      h("thead", null,
        h("tr", null,
          h("th", { style: { width: "36px" } },
            h("input", { type: "checkbox", checked: !!allSelected, onChange: function () { props.onToggleAllVisible(); } })
          ),
          h("th", null, _t("list.username")),
          h("th", null, _t("list.groups")),
          h("th", null, _t("list.onboard")),
          h("th", null, "Devices"),
          h("th", null, _t("list.state")),
          h("th", null, "Voice"),
          h("th", null, "Kanaler"),
          h("th", null, "Best device"),
          h("th", null, _t("list.actions"))
        )
      ),
      h("tbody", null,
        rows.map(function (u) {
          const hdr = (u && u.header) || {};
          const username = String(hdr.username || u.username || "");
          const groupsArr = (hdr && Array.isArray(hdr.groups)) ? hdr.groups : [];
          const onboardRaw = String((u && u.onboarding_status) || "").toUpperCase();
          const state = _userState(u);
          const best = _bestDevice(u);
          const key = username + ":" + String((best && best.client_uid) || "");
          const bestTxt = best ? _deviceTail(best) : "—";
          const voiceLabel = _voiceLabel(u);
          const voiceTone = _voiceTone(u);
          const voiceChannels = _voiceChannels(u);

          return h("tr", { key: key },
            h("td", null,
              h("input", {
                type: "checkbox",
                checked: !!selectedMap[username],
                onChange: function () { props.onToggleOne(username); }
              })
            ),
            h("td", null,
              h("button", {
                type: "button",
                className: "btn",
                style: { padding: "4px 8px" },
                onClick: function () {
                  try {
                    const lib2 = (window.TaksOnboarding && window.TaksOnboarding.lib) || null;
                    if (lib2 && typeof lib2.setHashRoute === "function") lib2.setHashRoute("detail", username);
                    else window.location.hash = "#onboarding/detail:" + encodeURIComponent(username);
                  } catch (e) {}
                }
              }, _colText(username || "—"))
            ),
            h("td", null, _colText(groupsArr.length ? groupsArr.join(", ") : "—")),
            h("td", null, _pill(onboardRaw || "—", _onboardTone(onboardRaw))),
            h("td", null, _colText(_deviceSummary(u))),
            h("td", null, _badgeForState(state)),
            h("td", null, _pill(voiceLabel, voiceTone)),
            h("td", null,
              h("div", {
                style: {
                  maxWidth: "240px",
                  whiteSpace: "normal",
                  overflowWrap: "anywhere",
                  wordBreak: "break-word"
                }
              }, _colText(voiceChannels))
            ),
            h("td", null, _colText(bestTxt)),
            h("td", null,
              h("div", { style: { display: "flex", gap: "8px", flexWrap: "wrap", alignItems: "center" } },
                h("button", {
                  className: "btn",
                  type: "button",
                  onClick: async function () {
                    try {
                      await _openFreshCard(username);
                    } catch (e) {
                      window.alert(String((e && e.message) || e || "Failed to open fresh card"));
                    }
                  }
                }, _t("btn.card")),
                h("button", {
                  className: "btn",
                  onClick: function () {
                    try {
                      const lib2 = (window.TaksOnboarding && window.TaksOnboarding.lib) || null;
                      if (lib2 && typeof lib2.setHashRoute === "function") lib2.setHashRoute("create", username);
                      else window.location.hash = "#onboarding/create:" + encodeURIComponent(username);
                    } catch (e) {}
                  }
                }, _t("btn.edit"))
              )
            )
          );
        })
      )
    );
  }

  function UnknownTable(props) {
    const rows = props.rows || [];
    return h(
      "table",
      { className: "tbl" },
      h("thead", null,
        h("tr", null,
          h("th", null, _t("list.username")),
          h("th", null, _t("list.state")),
          h("th", null, _t("list.age")),
          h("th", null, _t("field.callsign")),
          h("th", null, "UID")
        )
      ),
      h("tbody", null,
        rows.map(function (e) {
          const state = (e && (e.is_current === true ? "current" : (e.seen_recently === true ? "recent" : "stale"))) || "—";
          return h("tr", { key: (e.username || "") + ":" + (e.uid || "") },
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

    const selectedUsers = users.map(_rowUsername).filter(function (u) { return !!u && !!selectedMap[u]; });
    const selectedCount = selectedUsers.length;

    async function bulkDeleteSelected() {
      if (!selectedCount) return;

      if (!window.confirm(
        'Ta bort ' + String(selectedCount) + ' användare?\n\n' +
        'Detta tar bort TAKS onboarding-state och försöker ta bort användarna i TAK via UserManager.'
      )) {
        return;
      }

      const okRows = [];
      const failed = [];
      const warnings = [];

      for (const username of selectedUsers) {
        try {
          const resp = await fetch("/api/onboarding/users/" + encodeURIComponent(username) + "/delete", {
            method: "POST"
          });

          let data = null;
          try {
            data = await resp.json();
          } catch (e) {
            data = null;
          }

          if (!resp.ok) {
            const msg = (data && (data.detail || data.error)) || ("Delete failed (" + String(resp.status) + ")");
            failed.push(username + ": " + String(msg));
            continue;
          }

          okRows.push(username);
          if (data && data.warning) warnings.push(username + ": " + String(data.warning));
        } catch (e) {
          failed.push(username + ": " + String((e && e.message) || e || "Delete failed"));
        }
      }

      let msg = "";
      msg += "Borttagna: " + String(okRows.length);
      if (okRows.length) msg += "\n" + okRows.join(", ");
      if (warnings.length) msg += "\n\nVarningar:\n" + warnings.join("\n");
      if (failed.length) msg += "\n\nMisslyckades:\n" + failed.join("\n");

      window.alert(msg);
      window.location.reload();
    }

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
        if (allSelected) usernames.forEach(function (u) { delete out[u]; });
        else usernames.forEach(function (u) { out[u] = true; });
        return out;
      });
    }

    function clearSelection() {
      setSelectedMap({});
    }

    return h("div", null,
      h("div", { className: "card-title" }, _t("page.onboarding_list")),
      h("div", { className: "muted", style: { marginBottom: "8px" } }, ok ? _t("list.live_view") : _t("list.loading")),
      h("div", { className: "muted", style: { marginBottom: "10px" } },
        _t("list.summary", {
          users: _colText(summary.total_users),
          seen: _colText(summary.cot_seen),
          never: _colText(summary.never_seen),
          unknown: _colText(summary.unknown_endpoints),
          db: (typeof meta.db_attached === "boolean") ? (meta.db_attached ? "attached" : "none") : "?",
          source: _colText((meta && meta.db_source) || "no meta")
        }) +
        " • Voice now: " + _colText(summary.voice_connected_now || 0)
      ),
      h(PrintToolbar, {
        rows: users,
        selectedMap: selectedMap,
        onClear: clearSelection,
        onSelectAllVisible: toggleAllVisible,
        printMode: printMode,
        onPrintMode: setPrintMode
      }),
      h("div", {
        style: {
          display: "flex",
          gap: "10px",
          flexWrap: "wrap",
          alignItems: "center",
          marginBottom: "12px"
        }
      },
        h("div", { className: "muted" }, selectedCount ? (String(selectedCount) + " valda") : "Inga valda"),
        h("button", {
          className: "btn",
          type: "button",
          disabled: selectedCount < 1,
          style: {
            background: "#5a1f1f",
            borderColor: "#8b2e2e",
            color: "#fff"
          },
          onClick: function () { bulkDeleteSelected(); }
        }, "Ta bort valda användare")
      ),

      h(OnboardingTable, {
        rows: users,
        selectedMap: selectedMap,
        onToggleOne: toggleOne,
        onToggleAllVisible: toggleAllVisible
      }),

      unknown && unknown.length ? h("div", { style: { marginTop: "18px" } },
        h("div", { className: "card-title", style: { fontSize: "14px" } }, _t("list.unmanaged_endpoints")),
        h(UnknownTable, { rows: unknown })
      ) : null
    );
  }

  window.OnboardingListPage = OnboardingListPage;
})();
