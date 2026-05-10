/* global React */
(function () {
  var h = (window.h || React.createElement); window.h = h;

  var useState = React.useState;
  var useEffect = React.useEffect;

  var t = (window.t && typeof window.t === "function") ? window.t : function (k) { return String(k || ""); };
  var lib = (window.TaksOnboarding && window.TaksOnboarding.lib) || null;
  function _needLib() { if (!lib) throw new Error("Missing onboarding lib"); return lib; }
  function _colText(v){ return _needLib().colText(v); }

  function _yn(v) { return v ? "Ja" : "Nej"; }
  function _join(v) { return Array.isArray(v) && v.length ? v.join(", ") : "—"; }

  function _formatTimestamp(v) {
    var raw = String(v || "").trim();
    if (!raw) return "—";

    var d = new Date(raw);
    if (isNaN(d.getTime())) return raw;

    try {
      return d.toLocaleString("sv-SE", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit"
      });
    } catch (e) {
      return raw;
    }
  }

  function _relativeTimestamp(v) {
    var raw = String(v || "").trim();
    if (!raw) return "";

    var d = new Date(raw);
    if (isNaN(d.getTime())) return "";

    var sec = Math.round((Date.now() - d.getTime()) / 1000);
    if (sec < -30) return "framtid";
    if (sec < 30) return "nyss";

    var min = Math.floor(sec / 60);
    if (min < 60) return String(min) + " min sedan";

    var h = Math.floor(min / 60);
    var remMin = min % 60;
    if (h < 24) {
      return remMin ? (String(h) + " h " + String(remMin) + " min sedan") : (String(h) + " h sedan");
    }

    var dnr = Math.floor(h / 24);
    var remH = h % 24;
    if (dnr < 14) {
      return remH ? (String(dnr) + " d " + String(remH) + " h sedan") : (String(dnr) + " d sedan");
    }

    return "";
  }

  function _formatTimestampWithAge(v) {
    var ts = _formatTimestamp(v);
    if (ts === "—") return ts;

    var rel = _relativeTimestamp(v);
    return rel ? (ts + " (" + rel + ")") : ts;
  }
  function _onboardText(v) {
    var x = String(v || "").trim().toLowerCase();
    if (x === "done") return "Klar";
    if (x === "downloaded") return "Nedladdat";
    if (x === "started") return "Påbörjad";
    if (x === "invited") return "Inbjuden";
    if (x === "new") return "Ny";
    return x || "—";
  }

  function _endpointFlags(sel) {
    var ep = (sel && sel.endpoints) || {};
    var out = [];
    if (ep && ep.stream_host) out.push("stream-host");
    if (ep && ep.stream_port) out.push("stream-port");
    if (ep && ep.stream_ssl !== undefined) out.push("tls");
    return out.length ? out.join(", ") : "—";
  }
  function _deviceState(d) {
    var s = String((d && d.state) || "").toLowerCase();
    if (s) return s;
    if (d && d.is_current === true) return "current";
    if (d && d.seen_recently === true) return "recent";
    if (d && d.cot_seen) return "stale";
    return "never";
  }
  function _deviceStateText(d) {
    var st = _deviceState(d);
    if (st === "current") return "Online";
    if (st === "recent") return "Nyligen";
    if (st === "stale") return "Inaktiv";
    if (st === "never") return "Aldrig";
    return "—";
  }

  function _countStates(devices, wanted) {
    var n = 0;
    (devices || []).forEach(function (d) {
      if (_deviceState(d) === wanted) n += 1;
    });
    return n;
  }
  function _pickPrimaryDevice(devices) {
    var list = Array.isArray(devices) ? devices.slice() : [];
    if (!list.length) return null;
    var score = { current: 4, recent: 3, stale: 2, never: 1 };
    list.sort(function (a, b) {
      var sa = score[_deviceState(a)] || 0;
      var sb = score[_deviceState(b)] || 0;
      if (sa !== sb) return sb - sa;
      var ta = String((a && (a.last_cot_time || a.last_event_time)) || "");
      var tb = String((b && (b.last_cot_time || b.last_event_time)) || "");
      if (ta < tb) return 1;
      if (ta > tb) return -1;
      return 0;
    });
    return list[0] || null;
  }

  function _voiceTone(voice) {
    var v = voice || {};
    var user = v.user || {};
    if (user.connected_now) return "good";
    if (Array.isArray(user.matched_user_names) && user.matched_user_names.length) return "warn";
    return "bad";
  }

  function _voiceText(voice) {
    var v = voice || {};
    var user = v.user || {};
    if (user.connected_now) return "Tal: ansluten";
    if (Array.isArray(user.matched_user_names) && user.matched_user_names.length) return "Tal: tidigare sedd";
    return "Tal: ingen koppling";
  }

  function _deviceVoiceTone(v) {
    var voice = (v && v.voice) || {};
    if (voice.connected_now) return "good";
    if ((Array.isArray(voice.matches) && voice.matches.length) || Number(voice.matched_n || 0) > 0) return "warn";
    return "bad";
  }

  function _deviceVoiceText(v) {
    var voice = (v && v.voice) || {};
    if (voice.connected_now) return "TAL ANSLUTET";
    if ((Array.isArray(voice.matches) && voice.matches.length) || Number(voice.matched_n || 0) > 0) return "TALTRÄFF";
    return "INGEN TALKOPPLING";
  }

  function _voiceChannelsText(arr) {
    return Array.isArray(arr) && arr.length ? arr.join(", ") : "—";
  }

  function Box(props) {
    return h("div", {
      className: "box",
      style: { marginBottom: "12px" }
    }, props.children);
  }

  function SectionTitle(txt, right) {
    return h("div", {
      style: {
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        gap: "10px",
        marginBottom: "10px"
      }
    },
      h("div", {
        className: "card-title",
        style: { fontSize: "16px", marginBottom: 0 }
      }, txt),
      right || null
    );
  }

  function KV(props) {
    return h("div", {
      style: {
        display: "grid",
        gridTemplateColumns: "180px minmax(0,1fr)",
        gap: "10px",
        marginBottom: "8px",
        alignItems: "start"
      }
    },
      h("div", { className: "muted", style: { fontWeight: 700 } }, props.k),
      h("div", null, props.children)
    );
  }

  function Pill(props) {
    return h("span", {
      style: {
        display: "inline-block",
        padding: "4px 10px",
        borderRadius: "999px",
        border: "1px solid rgba(255,255,255,0.16)",
        background: "rgba(255,255,255,0.05)",
        fontSize: "12px",
        fontWeight: 700
      }
    }, String(props.children || ""));
  }

  function SmallButton(props) {
    return h("button", Object.assign({
      className: "btn",
      type: "button",
      style: { padding: "6px 10px" }
    }, props), props.children);
  }

  function StatusBadge(props) {
    var tone = String((props && props.tone) || "neutral");
    var text = String((props && props.text) || "—");

    var styles = {
      good:  { border: "1px solid rgba(80,200,120,0.45)", background: "rgba(80,200,120,0.12)", color: "#b8f5c8" },
      warn:  { border: "1px solid rgba(240,190,70,0.45)",  background: "rgba(240,190,70,0.12)",  color: "#ffe29a" },
      bad:   { border: "1px solid rgba(255,90,90,0.45)",   background: "rgba(255,90,90,0.12)",   color: "#ffb3b3" },
      neutral:{ border: "1px solid rgba(255,255,255,0.16)", background: "rgba(255,255,255,0.05)", color: "rgba(255,255,255,0.92)" }
    };
    var st = styles[tone] || styles.neutral;

    return h("span", {
      style: {
        display: "inline-block",
        padding: "4px 10px",
        borderRadius: "999px",
        fontSize: "12px",
        fontWeight: 800,
        letterSpacing: "0.02em",
        border: st.border,
        background: st.background,
        color: st.color
      }
    }, text);
  }

  function boolTone(v) {
    return v ? "good" : "bad";
  }

  function cotStateTone(stateText) {
    var s = String(stateText || "").trim().toUpperCase();
    if (s === "Online" || s === "ONLINE" || s === "AKTIV") return "good";
    if (s === "Nyligen" || s === "NYLIGEN") return "warn";
    if (s === "Inaktiv" || s === "INAKTIV") return "bad";
    if (s === "Aldrig" || s === "ALDRIG") return "neutral";
    return "neutral";
  }

  function onboardTone(v) {
    var s = String(v || "").trim().toLowerCase();
    if (s === "klar" || s === "done" || s === "active" || s === "aktiv") return "good";
    if (s === "ny" || s === "new" || s === "påbörjad" || s === "started" || s === "inbjuden" || s === "invited" || s === "nedladdat" || s === "downloaded") return "warn";
    if (s.indexOf("offboard") >= 0 || s.indexOf("fel") >= 0 || s.indexOf("fail") >= 0) return "bad";
    return "neutral";
  }

  function JsonToggle(props) {
    var _a = useState(false), open = _a[0], setOpen = _a[1];
    return h("div", null,
      h(SmallButton, { onClick: function () { setOpen(!open); } }, open ? "Dölj debugdata" : "Visa debugdata"),
      open ? h("pre", {
        style: {
          marginTop: "10px",
          whiteSpace: "pre-wrap",
          overflowWrap: "anywhere",
          wordBreak: "break-word",
          fontSize: "12px",
          lineHeight: "16px"
        }
      }, JSON.stringify(props.data, null, 2)) : null
    );
  }

  function DeviceSummaryRow(props) {
    var label = String(props.label || "");
    var value = Number(props.value || 0);
    var tone = String(props.tone || "neutral");
    return h("div", {
      style: {
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        gap: "10px",
        padding: "8px 10px",
        borderRadius: "10px",
        background: "rgba(255,255,255,0.03)",
        marginBottom: "8px"
      }
    },
      h("div", { className: "muted" }, label),
      h(StatusBadge, { tone: tone, text: String(value) })
    );
  }

  function DeviceCard(props) {
    var d = props.device || {};
    var voiceDevice = props.voiceDevice || {};
    var voice = (voiceDevice && voiceDevice.voice) || {};
    var stateText = _deviceStateText(d);
    var matches = Array.isArray(voice.matches) ? voice.matches : [];

    return h("div", {
      style: {
        border: "1px solid rgba(255,255,255,0.10)",
        borderRadius: "12px",
        padding: "12px",
        background: "rgba(255,255,255,0.03)"
      }
    },
      h("div", {
        style: {
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: "10px",
          flexWrap: "wrap",
          marginBottom: "10px"
        }
      },
        h("div", {
          style: {
            display: "flex",
            gap: "8px",
            alignItems: "center",
            flexWrap: "wrap"
          }
        },
          h(Pill, null, _colText([d.observed_callsign, d.tak_device].filter(Boolean).join(" / ") || d.client_uid || "device")),
          h(StatusBadge, { tone: cotStateTone(stateText), text: stateText }),
          h(StatusBadge, { tone: _deviceVoiceTone(voiceDevice), text: _deviceVoiceText(voiceDevice) })
        ),
        h("div", { className: "muted", style: { fontSize: "12px" } },
          "endpoint_id: ", _colText(d.endpoint_id)
        )
      ),
      h(KV, { k: "client_uid" }, h("code", null, _colText(d.client_uid))),
      h(KV, { k: "Observerad anropssignal" }, _colText(d.observed_callsign)),
      h(KV, { k: "Enhet" }, _colText(d.tak_device || "—")),
      h(KV, { k: "OS" }, _colText(d.tak_os || "—")),
      h(KV, { k: "Platform" }, _colText(d.tak_platform || d.client_platform || "—")),
      h(KV, { k: "Tidigare anropssignaler" }, _colText(Array.isArray(d.previous_observed_callsigns) && d.previous_observed_callsigns.length ? d.previous_observed_callsigns.join(", ") : "—")),
      h(KV, { k: "Senaste CoT" }, _colText(_formatTimestampWithAge(d.last_cot_time))),
      h(KV, { k: "Senaste event" }, _colText(_formatTimestampWithAge(d.last_event_time))),
      h(KV, { k: "Ålder" }, _colText(d.age_human)),
      h(KV, { k: "Enhet" }, _colText(d.tak_device || "—")),
      h(KV, { k: "Klient" }, _colText(
        (function () {
          var p = String(d.client_platform || d.tak_platform || "").trim();
          if (p) return p;
          var v = String(d.client_version || "").trim();
          if (!v) return "";
          var m = v.match(/^([A-Za-z][A-Za-z0-9._-]*)/);
          return m ? m[1] : "";
        })() || "—"
      )),
      h(KV, { k: "Version" }, _colText(
        d.tak_version || (function () {
          var v = String(d.client_version || "").trim();
          if (!v) return "—";
          var m = v.match(/^[A-Za-z][A-Za-z0-9._-]*[\/ ](.+)$/);
          return m ? m[1] : v;
        })()
      )),
      h(KV, { k: "Certifikat" }, _colText(d.certs_n)),
      h(KV, { k: "Revokerade cert" }, _colText(d.revoked_certs_n)),
      h(KV, { k: "CoT sedd" }, h(StatusBadge, { tone: boolTone(!!d.cot_seen), text: _yn(!!d.cot_seen) })),
      h(KV, { k: "Sedd nyligen" }, h(StatusBadge, { tone: boolTone(!!d.seen_recently), text: _yn(!!d.seen_recently) })),
      h(KV, { k: "Talkanaler" }, _voiceChannelsText(voice.channel_names)),
      h(KV, { k: "Talträffar" }, _colText(voice.matched_n || 0)),
      h(KV, { k: "Bästa talmatch" }, _colText(voice.best_match_mode || "—")),
      matches.length ? h("div", {
        style: {
          marginTop: "10px",
          paddingTop: "10px",
          borderTop: "1px solid rgba(255,255,255,0.08)"
        }
      },
        h("div", { className: "muted", style: { fontWeight: 700, marginBottom: "8px" } }, "Talträffar"),
        matches.map(function (m, idx) {
          return h("div", {
            key: String((m && m.name) || idx),
            style: {
              padding: "8px 10px",
              borderRadius: "10px",
              background: "rgba(255,255,255,0.03)",
              marginBottom: "8px"
            }
          },
            h("div", {
              style: {
                display: "flex",
                gap: "8px",
                alignItems: "center",
                flexWrap: "wrap",
                marginBottom: "6px"
              }
            },
              h(Pill, null, _colText(m.callsign || m.name || "talanvändare")),
              h(StatusBadge, { tone: m.connected_now ? "good" : "warn", text: m.connected_now ? "ANSLUTEN" : "SEDD" }),
              h(StatusBadge, { tone: "neutral", text: _colText(m.match_mode || "match") })
            ),
            h(KV, { k: "Namn" }, _colText(m.name)),
            h(KV, { k: "Kanal" }, _colText(m.channel_name || "—")),
            h(KV, { k: "Session" }, _colText(m.session)),
            h(KV, { k: "Suffix-kandidat" }, _colText(m.suffix_candidate || "—"))
          );
        })
      ) : null
    );
  }

  function OnboardingUserDetailPage(props) {
    var routeUsername = (props && props.routeUsername) ? String(props.routeUsername) : "";
    var _a = useState(true), busy = _a[0], setBusy = _a[1];
    var _b = useState(""), err = _b[0], setErr = _b[1];
    var _c = useState(null), userData = _c[0], setUserData = _c[1];
    var _d = useState(null), cardData = _d[0], setCardData = _d[1];
    var _e = useState(null), voiceData = _e[0], setVoiceData = _e[1];

    useEffect(function () {
      var u = String(routeUsername || "").trim();
      if (!u) {
        setErr("Missing username");
        setBusy(false);
        return;
      }

      var alive = true;
      (async function () {
        setBusy(true);
        setErr("");
        try {
          var urls = _needLib().userUrls(u);

          var _a = await Promise.all([
            fetch(urls.api_get),
            fetch(urls.card_json),
            fetch("/api/onboarding/users/" + encodeURIComponent(u) + "/voice-live")
          ]), rUser = _a[0], rCard = _a[1], rVoice = _a[2];

          var jUser = await rUser.json().catch(function () { return ({}); });
          var jCard = await rCard.json().catch(function () { return ({}); });
          var jVoice = await rVoice.json().catch(function () { return ({}); });

          if (!rUser.ok) throw new Error(jUser.detail || ("HTTP " + rUser.status));
          if (!rCard.ok) throw new Error(jCard.detail || ("HTTP " + rCard.status));
          if (!rVoice.ok) throw new Error(jVoice.detail || ("HTTP " + rVoice.status));

          if (!alive) return;
          setUserData(jUser || {});
          setCardData(jCard || {});
          setVoiceData(jVoice || {});
        } catch (e) {
          if (!alive) return;
          setErr(String((e && e.message) || e || "Failed"));
        } finally {
          if (alive) setBusy(false);
        }
      })();

      return function () { alive = false; };
    }, [routeUsername]);

    if (busy) {
      return h("div", null,
        h("div", { className: "card-title" }, "Adminvy — användare"),
        h("div", { className: "muted" }, "Laddar…")
      );
    }

    if (err) {
      return h("div", null,
        h("div", { className: "card-title" }, "Adminvy — användare"),
        h("div", { className: "note" }, "ERR: ", err)
      );
    }

    var user = (userData && userData.user) || {};
    var ti = (userData && userData.taks_identity) || {};
    var sel = (userData && userData.selection) || {};
    var ctx = (ti && ti.ctx) || {};
    var ident = (ti && ti.identity) || {};
    var cardWrap = cardData || {};
    var card = (cardWrap && cardWrap.card) || {};
    var lifecycle = (card && card.lifecycle) || {};
    var activity = (card && card.activity) || {};
    var header = (card && card.header) || {};
    var marti = (card && card.marti) || {};
    var devices = Array.isArray(card.devices) ? card.devices : [];
    var voice = voiceData || {};
    var voiceUser = (voice && voice.user) || {};
    var voiceDevices = Array.isArray(voice.devices) ? voice.devices : [];
    var voiceByClientUid = {};
    voiceDevices.forEach(function (vd) {
      var k = String((vd && vd.client_uid) || "").trim();
      if (k) voiceByClientUid[k] = vd;
    });

    var username = String(user.username || routeUsername || "").trim();
    var groups = Array.isArray(user.groups) ? user.groups : [];
    var cardUrl = (userData && userData.card_url) || (card && card.card_url) || "";
    var onboardStatus = _onboardText((card.onboarding && card.onboarding.status) || (lifecycle.evidence && lifecycle.evidence.onboarding_status));
    var primaryDevice = _pickPrimaryDevice(devices);
    var primaryStateText = primaryDevice ? _deviceStateText(primaryDevice) : (activity ? (activity.is_current === true ? "Online" : (activity.seen_recently === true ? "Nyligen" : "Inaktiv")) : "Aldrig");
    var primaryLifecycleText = String((lifecycle && (lifecycle.label || lifecycle.stage)) || primaryStateText || "—");
    var primaryLifecycleTone = (primaryLifecycleText === "Active" || String((lifecycle && lifecycle.stage) || "") === "SG3") ? "good" : cotStateTone(primaryStateText);
    var currentDevices = _countStates(devices, "current");
    var recentDevices = _countStates(devices, "recent");
    var staleDevices = _countStates(devices, "stale");
    var neverDevices = _countStates(devices, "never");
    if ((activity && activity.cot_seen === true) || currentDevices > 0 || String((lifecycle && lifecycle.stage) || "") === "SG3") {
      onboardStatus = "Klar";
    }
    var voiceConnectedDevices = 0;
    voiceDevices.forEach(function (vd) {
      if (vd && vd.voice && vd.voice.connected_now) voiceConnectedDevices += 1;
    });

    return h("div", null,
      h("div", { className: "card-title" }, "Adminvy — användare"),

      h("div", {
        style: {
          display: "flex",
          gap: "10px",
          flexWrap: "wrap",
          alignItems: "center",
          marginBottom: "12px"
        }
      },
        h(Pill, null, _colText(username)),
        h(StatusBadge, { tone: onboardTone(onboardStatus), text: "Introduktion: " + onboardStatus }),
        h(StatusBadge, { tone: cotStateTone(primaryStateText), text: "CoT: " + primaryStateText }),
        h(StatusBadge, { tone: devices.length ? "good" : "neutral", text: "Enheter: " + String(currentDevices) + " online / " + String(devices.length) + " kända" }),
        h(StatusBadge, { tone: _voiceTone(voice), text: _voiceText(voice) })
      ),

      h("div", {
        style: {
          display: "flex",
          gap: "8px",
          flexWrap: "wrap",
          marginBottom: "12px"
        }
      },
        h("button", {
          className: "btn",
          type: "button",
          onClick: function () {
            try {
              var lib2 = window.TaksOnboarding && window.TaksOnboarding.lib;
              if (lib2 && typeof lib2.setHashRoute === "function") lib2.setHashRoute("create", username);
            } catch (e) {}
          }
        }, t("btn.edit")),
        h("button", {
          className: "btn",
          type: "button",
          style: {
            background: "#5a1f1f",
            borderColor: "#8b2e2e",
            color: "#fff"
          },
          onClick: async function () {
            if (!username) {
              window.alert("Saknar användarnamn.");
              return;
            }
            if (!window.confirm('Ta bort användare "' + username + '"?\n\nDetta tar bort TAKS onboarding-state och försöker ta bort användaren i TAK via UserManager.')) {
              return;
            }
            try {
              var resp = await fetch("/api/onboarding/users/" + encodeURIComponent(username) + "/delete", {
                method: "POST"
              });

              var data = null;
              try {
                data = await resp.json();
              } catch (e) {
                data = null;
              }

              if (!resp.ok) {
                var msg = (data && (data.detail || data.error)) || ("Delete failed (" + String(resp.status) + ")");
                throw new Error(String(msg));
              }

              if (data && data.warning) {
                window.alert(String(data.warning));
              }

              try {
                var lib2 = window.TaksOnboarding && window.TaksOnboarding.lib;
                if (lib2 && typeof lib2.setHashRoute === "function") lib2.setHashRoute("list");
                else window.location.hash = "#onboarding/list";
              } catch (e) {
                window.location.hash = "#onboarding/list";
              }
            } catch (e) {
              window.alert(String((e && e.message) || e || "Delete failed"));
            }
          }
        }, "Ta bort användare"),
        cardUrl ? h("a", {
          className: "btn",
          href: cardUrl,
          target: "_blank",
          rel: "noopener noreferrer"
        }, "Soldatkort") : null
      ),

      h("div", {
        style: {
          display: "grid",
          gridTemplateColumns: "minmax(320px, 1fr) minmax(320px, 1fr)",
          gap: "12px"
        }
      },
        h("div", null,
          h(Box, null,
            SectionTitle("Konto"),
            h(KV, { k: "Användarnamn" }, _colText(username)),
            h(KV, { k: "Konfigurerad anropssignal" }, _colText((card.callsigns && card.callsigns.configured) || header.configured_callsign || header.callsign || ctx.callsign || ident.callsign)),
            h(KV, { k: "Online som" }, _colText((card.callsigns && card.callsigns.current_observed) || (activity && activity.callsign) || "—")),
            h(KV, { k: "Tidigare anropssignaler" }, _colText((function () {
              var cs = (card.callsigns || {});
              var prev = Array.isArray(cs.previous_observed) ? cs.previous_observed : [];
              return prev.length ? prev.join(", ") : "—";
            })())),
            h(KV, { k: "Team" }, _colText(header.team || ctx.team || ident.team)),
            h(KV, { k: "TAK-roll" }, _colText(header.atak_role_type || ctx.atak_role_type || ident.atak_role_type)),
            h(KV, { k: "E-post" }, _colText(ctx.email)),
            h(KV, { k: "Grupper" }, _colText(_join(groups))),
            h(KV, { k: "Policy" }, _colText(ctx.policy_id || (card.policy && card.policy.id)))
          ),

          h(Box, null,
            SectionTitle("Kontostatus"),
            h(KV, { k: "Källa" }, _colText(ti.origin)),
            h(KV, { k: "Lösenord känt" }, h(StatusBadge, { tone: boolTone(!!ti.password_known), text: _yn(!!ti.password_known) })),
          ),

        ),

        h("div", null,
          h(Box, null,
            SectionTitle("Närvaro / drift"),
            h(KV, { k: "Introduktion" }, h(StatusBadge, { tone: onboardTone(onboardStatus), text: _colText(onboardStatus) })),
            h(KV, { k: "CoT" }, h(StatusBadge, { tone: cotStateTone(primaryStateText), text: _colText(primaryStateText) })),
            h(KV, { k: "Enheter" }, _colText(String(currentDevices) + " online / " + String(devices.length) + " kända")),
            h(KV, { k: "Aktuell CoT-session" }, _colText(activity && activity.callsign ? (activity.callsign + " / " + _colText(activity.uid)) : "—")),
            h(KV, { k: "Senast sedd" }, _colText(_formatTimestampWithAge(activity && (activity.last_seen || activity.last_cot_time)))),
            h(KV, { k: "Chat" }, _colText((card.openfire || card.xmpp) ? "XMPP + GeoChat" : ((activity && activity.cot_seen) ? "Endast GeoChat" : "—"))),
          ),

          h(Box, null,
            (function () {
              var matchedNames = Array.isArray(voiceUser.matched_user_names) ? voiceUser.matched_user_names : [];
              var channelNames = Array.isArray(voiceUser.channel_names) ? voiceUser.channel_names : [];
              var statusTone = (voiceUser && voiceUser.connected_now) ? "good" : (matchedNames.length ? "warn" : "bad");
              var statusText = (voiceUser && voiceUser.connected_now) ? "ANSLUTEN" : (matchedNames.length ? "TIDIGARE SEDD" : "INGEN KOPPLING");

              return [
                SectionTitle("Tal"),
                h(KV, { k: "Status" }, h(StatusBadge, { tone: statusTone, text: statusText })),
                matchedNames.length ? h(KV, { k: "Matchade talnamn" }, _colText(_join(matchedNames))) : null,
                channelNames.length ? h(KV, { k: "Talkanaler" }, _colText(_voiceChannelsText(channelNames))) : null,
                h(KV, { k: "Enheter anslutna till tal nu" }, _colText(voiceConnectedDevices))
              ];
            })()
          ),

          h(Box, null,
            SectionTitle("Enheter"),
            h(DeviceSummaryRow, { label: "Online", value: currentDevices, tone: currentDevices ? "good" : "neutral" }),
            h(DeviceSummaryRow, { label: "Nyligen", value: recentDevices, tone: recentDevices ? "warn" : "neutral" }),
            h(DeviceSummaryRow, { label: "Inaktiv", value: staleDevices, tone: staleDevices ? "bad" : "neutral" }),
            h(DeviceSummaryRow, { label: "Aldrig", value: neverDevices, tone: "neutral" })
          )
        )
      ),

      h(Box, null,
        SectionTitle("Enhetsdetaljer", h("div", { className: "muted", style: { fontSize: "12px" } }, devices.length ? (String(devices.length) + " enheter") : "Inga enheter")),
        devices.length ? h("div", {
          style: {
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))",
            gap: "12px"
          }
        }, devices.map(function (d, idx) {
          var k = String((d && d.client_uid) || "").trim();
          var vd = k ? (voiceByClientUid[k] || null) : null;
          return h(DeviceCard, {
            key: String((d && d.client_uid) || idx),
            device: d,
            voiceDevice: vd
          });
        })) : h("div", { className: "muted" }, "Inga enheter hittades för användaren.")
      ),

      h(Box, null,
        SectionTitle("Debug"),
        h(JsonToggle, { data: { userData: userData, cardData: cardData, voiceData: voiceData } })
      )
    );
  }

  window.OnboardingUserDetailPage = OnboardingUserDetailPage;
})();
