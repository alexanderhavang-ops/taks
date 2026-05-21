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
    { id: "cards", label: "Endast kort" },
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
    if (!ds.length) return "0 kända";

    let current = 0, recent = 0, stale = 0, never = 0;
    ds.forEach(function (d) {
      const st = String((d && d.state) || "never").toLowerCase();
      if (st === "current") current += 1;
      else if (st === "recent") recent += 1;
      else if (st === "stale") stale += 1;
      else never += 1;
    });

    const bits = [];
    if (current) bits.push(String(current) + " current");
    if (recent) bits.push(String(recent) + " recent");
    if (stale) bits.push(String(stale) + " stale");
    if (never) bits.push(String(never) + " never");

    return bits.join(" / ") + " / " + String(ds.length) + " kända";
  }

  function _displayLifecycle(row) {
    const lc = (row && row.lifecycle) || {};
    return String(lc.label || lc.stage || (row && row.onboarding_status) || "—");
  }

  function _callsignLine(row) {
    const h = (row && row.header) || {};
    const cs = (row && row.callsigns) || {};
    const configured = String(h.configured_callsign || h.callsign || cs.configured || "").trim();
    const observed = String(h.current_observed_callsign || cs.current_observed || "").trim();

    if (configured && observed && configured.toUpperCase() !== observed.toUpperCase()) {
      return "cfg " + configured + " / obs " + observed;
    }
    return configured || observed || "—";
  }

  function _callsignSummaryText(row) {
    const h = (row && row.header) || {};
    const cs = (row && row.callsigns) || {};
    const configured = String(h.configured_callsign || cs.configured || h.callsign || "").trim();
    const observed = String(h.current_observed_callsign || cs.current_observed || "").trim();

    if (configured && observed && configured.toUpperCase() !== observed.toUpperCase()) {
      return "cfg " + configured + " / obs " + observed;
    }
    return configured || observed || "—";
  }

  function _primaryStatusLabel(row) {
    const lc = (row && row.lifecycle) || {};
    const label = String(lc.label || "").trim();
    const stage = String(lc.stage || "").trim();

    if (label) return label;
    if (stage) return stage;

    const state = String(_userState(row) || "").trim();
    return state || "—";
  }

  function _primaryStatusTone(row) {
    const lc = (row && row.lifecycle) || {};
    const stage = String(lc.stage || "");
    const label = String(lc.label || "").toLowerCase();

    if (stage === "SG3" || label === "active") return "good";
    if (stage === "SG4" || label.indexOf("offboard") >= 0) return "bad";

    const state = String(_userState(row) || "").toLowerCase();
    if (state === "current") return "good";
    if (state === "recent") return "warn";
    if (state === "stale") return "bad";
    return "neutral";
  }

  function _asArray(v) {
    return Array.isArray(v) ? v : [];
  }

  function _deviceState(d) {
    return String((d && d.state) || "never").toLowerCase();
  }

  function _isOnlineDevice(d) {
    return _deviceState(d) === "current" || d && d.is_current === true;
  }

  function _devicesForRow(row) {
    return _asArray(row && row.devices);
  }

  function _currentDevices(row) {
    return _devicesForRow(row).filter(_isOnlineDevice);
  }

  function _oldDevices(row) {
    return _devicesForRow(row).filter(function (d) { return !_isOnlineDevice(d); });
  }

  function _deviceKey(d, idx) {
    return [
      String((d && d.client_uid) || ""),
      String((d && d.observed_callsign) || ""),
      String((d && d.endpoint_id) || idx || "")
    ].join(":");
  }

  function _deviceName(d) {
    if (!d) return "—";
    const callsign = String(d.observed_callsign || d.current_observed_callsign || "").trim();
    const dev = String(d.tak_device || "").trim();
    const platform = String(d.tak_platform || d.client_platform || "").trim();

    const bits = [];
    if (callsign) bits.push(callsign);
    if (dev) bits.push(dev);
    else if (platform) bits.push(platform);

    return bits.length ? bits.join(" / ") : String(d.client_uid || "device");
  }

  function _deviceTech(d) {
    if (!d) return "—";
    const dev = String(d.tak_device || "").trim();
    const platform = String(d.tak_platform || d.client_platform || "").trim();
    const version = String(d.tak_version || d.client_version || "").trim();

    const bits = [];
    if (dev) bits.push(dev);
    if (platform) bits.push(platform);
    if (version && bits.length < 2) bits.push(version);

    return bits.length ? bits.join(" / ") : String(d.client_uid || "—");
  }

  function _configuredCallsign(row) {
    const h = (row && row.header) || {};
    const cs = (row && row.callsigns) || {};
    return String(h.configured_callsign || cs.configured || h.callsign || "").trim();
  }

  function _currentObservedCallsign(row) {
    const h = (row && row.header) || {};
    const cs = (row && row.callsigns) || {};
    return String(h.current_observed_callsign || cs.current_observed || "").trim();
  }

  function _accountLabel(row) {
    const h = (row && row.header) || {};
    const username = String(h.username || row.username || "").trim();
    const configured = _configuredCallsign(row);
    return configured ? (username + " (" + configured + ")") : (username || "—");
  }

  function _callsignWarning(row) {
    const configured = _configuredCallsign(row);
    const observed = _currentObservedCallsign(row);
    if (configured && observed && configured.toUpperCase() !== observed.toUpperCase()) {
      return "Sedd som " + observed;
    }
    return "";
  }

  function _onboardingText(row) {
    const activity = (row && row.activity) || {};
    const devices = (row && Array.isArray(row.devices)) ? row.devices : [];
    const current = devices.filter(function (d) { return String((d && d.state) || "").toLowerCase() === "current"; });

    if (activity.cot_seen === true || current.length > 0) return "Klar";

    const raw = String((row && row.onboarding_status) || ((row && row.lifecycle && row.lifecycle.evidence) ? row.lifecycle.evidence.onboarding_status : "") || "").trim().toLowerCase();
    if (raw === "done") return "Klar";
    if (raw === "nedladdat") return "Nedladdat";
    if (raw === "started") return "Påbörjad";
    if (raw === "invited") return "Inbjuden";
    if (raw === "new") return "Ny";
    return raw || "—";
  }

  function _onboardingTone(row) {
    return _onboardingText(row) === "Klar" ? "good" : "warn";
  }

  function _cotText(row) {
    const current = _currentDevices(row);
    const devices = _devicesForRow(row);

    if (current.length > 1) return String(current.length) + " sessioner online";
    if (current.length === 1) {
      const cs = String(current[0].observed_callsign || _currentObservedCallsign(row) || "").trim();
      return cs ? ("Online: " + cs) : "Online";
    }

    if (devices.some(function (d) { return _deviceState(d) === "recent"; })) return "Inaktiv";
    if (devices.length) return "Inaktiv";
    return "Aldrig";
  }

  function _cotTone(row) {
    const t = _cotText(row).toLowerCase();
    if (t.indexOf("online") >= 0) return "good";
    if (t === "stale") return "warn";
    return "neutral";
  }

  function _deviceCountText(row) {
    const devices = _devicesForRow(row);
    const current = _currentDevices(row);
    if (!devices.length) return "0 online / 0 kända";
    return String(current.length) + " online / " + String(devices.length) + " kända";
  }

  function _voiceText(row) {
    const vs = (row && row.voice_summary) || {};
    const connected = vs.connected_now === true || vs.device_connected_now > 0 || vs.matched_connected_users > 0;
    if (!connected) return "—";
    const n = Number(vs.device_connected_now || vs.matched_connected_users || 0);
    return n > 1 ? (String(n) + " sessions") : "Online";
  }

  function _voiceTone2(row) {
    return _voiceText(row) === "—" ? "neutral" : "good";
  }

  function _channelText(row) {
    const vs = (row && row.voice_summary) || {};
    const chans = _asArray(vs.channel_names);
    if (chans.length) return chans.join(", ");
    return _voiceChannels(row) || "—";
  }

  function _chatText(row) {
    const activity = (row && row.activity) || {};
    const cot = activity.cot_seen === true || _currentDevices(row).length > 0;

    const xmpp = (row && (row.xmpp || row.openfire)) || {};
    const hasXmpp = !!(row && (row.xmpp || row.openfire));
    const online = (
      xmpp.connected_now === true ||
      xmpp.connected === true ||
      xmpp.online === true ||
      xmpp.status === "online"
    );

    if (xmpp.bot === true && online && cot) return "Martine XMPP + GeoChat";
    if (xmpp.bot === true && online) return "Martine XMPP";
    if (online && cot) return "XMPP online + GeoChat";
    if (online) return "XMPP online";
    if (hasXmpp && cot) return "XMPP känd + GeoChat";
    if (hasXmpp) return "XMPP känd";
    if (cot) return "Endast GeoChat";
    return "—";
  }

  function _chatTone(row) {
    const t = _chatText(row);
    if (t === "XMPP online + GeoChat" || t === "Martine XMPP + GeoChat") return "good";
    if (t === "XMPP online" || t === "Martine XMPP") return "good";
    if (t === "XMPP känd + GeoChat" || t === "XMPP känd" || t === "Endast GeoChat") return "warn";
    return "neutral";
  }

  function _chatDetailText(row) {
    const xmpp = (row && (row.xmpp || row.openfire)) || {};
    if (!xmpp || !Object.keys(xmpp).length) return "";

    const rooms = _asArray(xmpp.room_labels).length ? _asArray(xmpp.room_labels) : _asArray(xmpp.rooms);
    const online = (
      xmpp.connected_now === true ||
      xmpp.connected === true ||
      xmpp.online === true ||
      xmpp.status === "online"
    );

    if (xmpp.bot === true) {
      return rooms.length ? (String(rooms.length) + " XMPP-rum") : "bot-session online";
    }

    if (online) {
      if (rooms.length) return rooms.slice(0, 2).join(", ") + (rooms.length > 2 ? " +" + String(rooms.length - 2) : "");
      return "TAK-client online";
    }

    if (rooms.length) return rooms.slice(0, 2).join(", ") + (rooms.length > 2 ? " +" + String(rooms.length - 2) : "");
    if (xmpp.jid) return "JID känd";
    return "";
  }


  function _channelLabel(raw) {
    var x = String(raw || "").trim();
    if (!x) return "";

    x = x.split("@", 1)[0];
    x = x.replace(/^\s+|\s+$/g, "");
    if (!x) return "";

    var parts = x.split("-");
    if (parts.length < 2) return x;

    var prefix = parts[0].toLowerCase();
    var rest = parts.slice(1).join("-").toUpperCase();

    var pretty = {
      "batl": "BatL",
      "plutl": "PlutL",
      "kompl": "KompL",
      "gruppl": "GruppL"
    }[prefix] || parts[0];

    return pretty + "-" + rest;
  }

  function _channelKey(raw) {
    return _channelLabel(raw).toLowerCase();
  }

  function _addChannelKind(map, raw, kind) {
    var label = _channelLabel(raw);
    var key = _channelKey(raw);
    if (!label || !key) return;

    if (!map[key]) map[key] = { label: label, tal: false, chat: false };
    map[key][kind] = true;
  }

  function _voiceChannelNames(row) {
    var out = [];
    var vs = (row && row.voice_summary) || {};
    out = out.concat(_asArray(vs.channel_names));

    var vu = _voiceUser(row);
    out = out.concat(_asArray(vu.channel_names));

    return out;
  }

  function _chatRoomNames(row) {
    var xmpp = (row && (row.xmpp || row.openfire)) || {};
    var rooms = _asArray(xmpp.room_labels).length ? _asArray(xmpp.room_labels) : _asArray(xmpp.rooms);
    return rooms;
  }

  function _combinedChannelRows(row) {
    var xmpp = (row && (row.xmpp || row.openfire)) || {};
    var map = {};

    var xmppOnline = (
      xmpp.connected_now === true ||
      xmpp.connected === true ||
      xmpp.online === true ||
      xmpp.status === "online" ||
      xmpp.bot === true
    );

    _voiceChannelNames(row).forEach(function (ch) {
      _addChannelKind(map, ch, "tal");
    });

    _chatRoomNames(row).forEach(function (ch) {
      _addChannelKind(map, ch, "chat");
    });

    var rows = Object.keys(map).sort().map(function (k) {
      var r = map[k];
      r.chat_online = !!xmppOnline;
      r.tal_online = !!r.tal;
      return r;
    });

    if (xmpp.bot === true) {
      var n = _asArray(xmpp.rooms).length || _asArray(xmpp.room_labels).length;
      return [{
        label: n ? String(n) + " XMPP-rum" : "XMPP-bot",
        tal: false,
        chat: true,
        chat_online: true,
        bot: true
      }];
    }

    return rows;
  }

  function _renderCombinedChannels(row) {
    var rows = _combinedChannelRows(row);

    if (!rows.length) return _colText("—");

    return h("div", { style: { display: "grid", gap: "4px", maxWidth: "320px" } },
      rows.slice(0, 5).map(function (r, idx) {
        return h("div", {
          key: "chan:" + idx,
          style: { display: "flex", alignItems: "center", gap: "6px", flexWrap: "wrap" }
        },
          h("span", { style: { fontWeight: 650 } }, _colText(r.label)),
          r.tal ? _pill("tal", r.tal_online ? "good" : "warn") : null,
          r.chat ? _pill("chat", r.chat_online ? "good" : "warn") : null
        );
      }).concat(rows.length > 5 ? [
        h("div", { key: "more", className: "muted", style: { fontSize: "11px" } }, "+" + String(rows.length - 5) + " fler")
      ] : [])
    );
  }

  function _voiceForDevice(row, d) {
    const uid = String((d && d.client_uid) || "").trim();
    const cs = String((d && d.observed_callsign) || "").trim().toUpperCase();
    const all = []
      .concat(_asArray(row && row.voice_devices))
      .concat(_asArray(row && row.voice && row.voice.devices));

    for (let i = 0; i < all.length; i += 1) {
      const vd = all[i] || {};
      const vuid = String(vd.client_uid || "").trim();
      const vcs = String(vd.observed_callsign || "").trim().toUpperCase();
      if ((uid && vuid === uid) || (cs && vcs === cs)) return vd;
    }
    return null;
  }

  function _deviceVoiceText(row, d) {
    const vd = _voiceForDevice(row, d);
    const v = (vd && vd.voice) || {};
    if (v.connected_now === true) {
      const chans = _asArray(v.channel_names);
      return chans.length ? chans.join(", ") : "Online";
    }
    return "—";
  }

  function _deviceVoiceTone(row, d) {
    return _deviceVoiceText(row, d) === "—" ? "neutral" : "good";
  }

  function _renderAccountCell(username, row) {
    const warning = _callsignWarning(row);
    return h("div", null,
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
      }, _colText(_accountLabel(row))),
      warning ? h("div", {
        className: "muted",
        style: { marginTop: "4px", fontSize: "12px" }
      }, "⚠ ", _colText(warning)) : null
    );
  }

  function _renderActions(username) {
    return h("div", { style: { display: "flex", gap: "8px", flexWrap: "wrap", alignItems: "center" } },
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
    );
  }

  function OnboardingTable(props) {
    const rows = props.rows || [];
    const selectedMap = props.selectedMap || {};
    const allUsernames = rows.map(_rowUsername).filter(Boolean);
    const allSelected = allUsernames.length > 0 && allUsernames.every((u) => !!selectedMap[u]);
    const useState = (React && React.useState) ? React.useState : window.React.useState;
    const statePair = useState({});
    const expanded = statePair[0] || {};
    const setExpanded = statePair[1];

    function toggleExpanded(username) {
      setExpanded(function (prev) {
        const next = Object.assign({}, prev || {});
        next[username] = !next[username];
        return next;
      });
    }

    const bodyRows = [];

    rows.forEach(function (u) {
      const hdr = (u && u.header) || {};
      const username = String(hdr.username || u.username || "");
      const devices = _devicesForRow(u);
      const current = _currentDevices(u);
      const gamla = _oldDevices(u);
      const showSessionRows = current.length > 1;
      const expandedNow = !!expanded[username];
      const gamlaButtonText = gamla.length
        ? ((expandedNow ? "Dölj" : "Visa") + " " + String(gamla.length) + " gamla")
        : "";

      bodyRows.push(h("tr", { key: "acct:" + username },
        h("td", null,
          h("input", {
            type: "checkbox",
            checked: !!selectedMap[username],
            onChange: function () { props.onToggleOne(username); }
          })
        ),
        h("td", null, _renderAccountCell(username, u)),
        h("td", null, _pill(_onboardingText(u), _onboardingTone(u))),
        h("td", null, _pill(_cotText(u), _cotTone(u))),
        h("td", null,
          h("div", null,
            h("div", null, _colText(_deviceCountText(u))),
            gamla.length ? h("button", {
              type: "button",
              className: "btn",
              style: { marginTop: "4px", padding: "2px 7px", fontSize: "12px" },
              onClick: function () { toggleExpanded(username); }
            }, gamlaButtonText) : null
          )
        ),
        h("td", null, _renderCombinedChannels(u)),
        h("td", null, _renderActions(username))
      ));

      if (showSessionRows) {
        current.forEach(function (d, idx) {
          bodyRows.push(h("tr", {
            key: "cur:" + username + ":" + _deviceKey(d, idx),
            style: { background: "rgba(255,255,255,0.025)" }
          },
            h("td", null, ""),
            h("td", null, h("div", { style: { paddingLeft: "18px" } }, "↳ ", _colText(_deviceName(d)))),
            h("td", null, ""),
            h("td", null, _pill("Online", "good")),
            h("td", null, _colText(_deviceTech(d))),
            h("td", null, _renderCombinedChannels(u)),
            h("td", null, "")
          ));
        });
      }

      if (expandedNow) {
        gamla.forEach(function (d, idx) {
          const st = _deviceState(d);
          const label = st === "recent" ? "Inaktiv" : (st === "stale" ? "Inaktiv" : "Old");
          const tone = st === "recent" ? "warn" : "neutral";

          bodyRows.push(h("tr", {
            key: "old:" + username + ":" + _deviceKey(d, idx),
            style: { background: "rgba(255,255,255,0.015)" }
          },
            h("td", null, ""),
            h("td", null, h("div", { style: { paddingLeft: "18px" } }, "↳ ", _colText(_deviceName(d)))),
            h("td", null, ""),
            h("td", null, _pill(label, tone)),
            h("td", null, _colText(_deviceTech(d))),
            h("td", null, _renderCombinedChannels(u)),
            h("td", null, "")
          ));
        });
      }
    });

    return h(
      "table",
      { className: "tbl" },
      h("thead", null,
        h("tr", null,
          h("th", { style: { width: "36px" } },
            h("input", { type: "checkbox", checked: !!allSelected, onChange: function () { props.onToggleAllVisible(); } })
          ),
          h("th", null, "Konto"),
          h("th", null, "Introduktion"),
          h("th", null, "CoT"),
          h("th", null, "Enheter"),
          h("th", null, "Kanaler"),
          h("th", null, _t("list.actions"))
        )
      ),
      h("tbody", null, bodyRows)
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

    const known = {};
    users.map(_rowUsername).filter(Boolean).forEach(function (u) {
      known[u] = true;
    });

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
      const kända = {};
      (users || []).forEach(function (u) {
        const username = _rowUsername(u);
        if (username) kända[username] = true;
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
        " • Tal nu: " + _colText(summary.voice_connected_now || 0)
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
