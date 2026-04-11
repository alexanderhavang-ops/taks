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
  function _onboardText(v) {
    var x = String(v || "").trim();
    return x ? x : "okänt";
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
    return _deviceState(d).toUpperCase();
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
    var connected = !!(v.user && v.user.connected_now);
    var serverConnected = !!((v.server || {}).connected);
    var hasMatches = !!((v.user && Array.isArray(v.user.matched_user_names) && v.user.matched_user_names.length) || false);
    if (connected) return "good";
    if (serverConnected && hasMatches) return "warn";
    if (serverConnected) return "neutral";
    return "bad";
  }

  function _voiceText(voice) {
    var v = voice || {};
    if (!((v.server || {}).connected)) return "Voice: server ej ansluten";
    if (v.user && v.user.connected_now) return "Voice: ansluten nu";
    if (v.user && Array.isArray(v.user.matched_user_names) && v.user.matched_user_names.length) return "Voice: sedd tidigare";
    return "Voice: ingen träff";
  }

  function _deviceVoiceTone(v) {
    var voice = (v && v.voice) || {};
    if (voice.connected_now) return "good";
    if ((voice.matched_n || 0) > 0) return "warn";
    return "neutral";
  }

  function _deviceVoiceText(v) {
    var voice = (v && v.voice) || {};
    if (voice.connected_now) return "ANSLUTEN NU";
    if ((voice.matched_n || 0) > 0) return "SEDD";
    return "INGEN VOICE-TRÄFF";
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
    var s = String(stateText || "").toUpperCase();
    if (s === "CURRENT") return "good";
    if (s === "RECENT") return "warn";
    if (s === "STALE") return "bad";
    if (s === "NEVER") return "neutral";
    return "neutral";
  }

  function onboardTone(v) {
    var s = String(v || "").toUpperCase();
    if (s === "DOWNLOADED" || s === "COMPLETE" || s === "ACTIVE") return "good";
    if (s === "NEW" || s === "PACKAGE_GENERATED" || s === "QR_GENERATED") return "warn";
    if (!s || s === "—") return "neutral";
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
          h(Pill, null, _colText(d.observed_callsign || d.client_uid || "device")),
          h(StatusBadge, { tone: cotStateTone(stateText), text: stateText }),
          h(StatusBadge, { tone: _deviceVoiceTone(voiceDevice), text: _deviceVoiceText(voiceDevice) })
        ),
        h("div", { className: "muted", style: { fontSize: "12px" } },
          "endpoint_id: ", _colText(d.endpoint_id)
        )
      ),
      h(KV, { k: "client_uid" }, h("code", null, _colText(d.client_uid))),
      h(KV, { k: "Observed callsign" }, _colText(d.observed_callsign)),
      h(KV, { k: "Senaste CoT" }, _colText(d.last_cot_time)),
      h(KV, { k: "Senaste event" }, _colText(d.last_event_time)),
      h(KV, { k: "Ålder" }, _colText(d.age_human)),
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
      h(KV, { k: "Voice-kanaler" }, _voiceChannelsText(voice.channel_names)),
      h(KV, { k: "Voice-träffar" }, _colText(voice.matched_n || 0)),
      h(KV, { k: "Voice bästa match" }, _colText(voice.best_match_mode || "—")),
      matches.length ? h("div", {
        style: {
          marginTop: "10px",
          paddingTop: "10px",
          borderTop: "1px solid rgba(255,255,255,0.08)"
        }
      },
        h("div", { className: "muted", style: { fontWeight: 700, marginBottom: "8px" } }, "Voice-träffar"),
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
              h(Pill, null, _colText(m.callsign || m.name || "voice-user")),
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
    var primaryStateText = primaryDevice ? _deviceStateText(primaryDevice) : (activity ? (activity.is_current === true ? "CURRENT" : (activity.seen_recently === true ? "RECENT" : "STALE")) : "NEVER");
    var currentDevices = _countStates(devices, "current");
    var recentDevices = _countStates(devices, "recent");
    var staleDevices = _countStates(devices, "stale");
    var neverDevices = _countStates(devices, "never");
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
        h(StatusBadge, { tone: onboardTone(onboardStatus), text: "Onboarding: " + onboardStatus }),
        h(StatusBadge, { tone: cotStateTone(primaryStateText), text: "Primär device: " + primaryStateText }),
        h(StatusBadge, { tone: devices.length ? "good" : "neutral", text: "Devices: " + String(devices.length) }),
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
            SectionTitle("Identitet"),
            h(KV, { k: "Användarnamn" }, _colText(username)),
            h(KV, { k: "Anropssignal" }, _colText(header.callsign || ctx.callsign || ident.callsign)),
            h(KV, { k: "Team" }, _colText(header.team || ctx.team || ident.team)),
            h(KV, { k: "ATAK-roll" }, _colText(header.atak_role_type || ctx.atak_role_type || ident.atak_role_type)),
            h(KV, { k: "E-post" }, _colText(ctx.email)),
            h(KV, { k: "Grupper" }, _colText(_join(groups))),
            h(KV, { k: "Policy" }, _colText(ctx.policy_id || (card.policy && card.policy.id)))
          ),

          h(Box, null,
            SectionTitle("TAKS / konto"),
            h(KV, { k: "Origin" }, _colText(ti.origin)),
            h(KV, { k: "Lösenord känt" }, h(StatusBadge, { tone: boolTone(!!ti.password_known), text: _yn(!!ti.password_known) })),
            h(KV, { k: "Visa lösenord" }, _yn(!!(sel && sel.reveal_password))),
            h(KV, { k: "Soldatkort" },
              cardUrl ? h("a", { href: cardUrl, target: "_blank", rel: "noopener noreferrer" }, cardUrl) : "—"
            )
          ),

          h(Box, null,
            SectionTitle("Paketval"),
            h(KV, { k: "Paket-/endpointval" }, _colText(_endpointFlags(sel))),
            h(KV, { k: "Urval sparat" }, _yn(!!(sel && sel.ctx)))
          )
        ),

        h("div", null,
          h(Box, null,
            SectionTitle("Runtime / sammanfattning"),
            h(KV, { k: "Onboarding-status" }, h(StatusBadge, { tone: onboardTone(onboardStatus), text: onboardStatus })),
            h(KV, { k: "Primär status" }, h(StatusBadge, { tone: cotStateTone(primaryStateText), text: _colText(primaryStateText) })),
            h(KV, { k: "Devices" }, _colText(devices.length)),
            h(KV, { k: "Aktivitet" }, _colText(activity && activity.callsign ? (activity.callsign + " / " + _colText(activity.uid)) : "—")),
            h(KV, { k: "Senast sedd" }, _colText((activity && (activity.last_seen || activity.last_cot_time)) || "—")),
            h(KV, { k: "Marti-grupper" }, _colText(_join(marti.groups)))
          ),

          h(Box, null,
            SectionTitle("Voice / Mumble"),
            h(KV, { k: "Server" }, h(StatusBadge, {
              tone: ((voice.server || {}).connected) ? "good" : "bad",
              text: ((voice.server || {}).connected) ? "ANSLUTEN" : "EJ ANSLUTEN"
            })),
            h(KV, { k: "Användare i voice nu" }, _colText((voice.raw_counts && voice.raw_counts.users) || 0)),
            h(KV, { k: "Kanaler" }, _colText((voice.raw_counts && voice.raw_counts.channels) || 0)),
            h(KV, { k: "Användaren ansluten nu" }, h(StatusBadge, {
              tone: (voiceUser && voiceUser.connected_now) ? "good" : "neutral",
              text: (voiceUser && voiceUser.connected_now) ? "JA" : "NEJ"
            })),
            h(KV, { k: "Voice-kanaler" }, _colText(_voiceChannelsText(voiceUser.channel_names))),
            h(KV, { k: "Matchade voice-namn" }, _colText(_join(voiceUser.matched_user_names))),
            h(KV, { k: "Devices med voice nu" }, h(StatusBadge, {
              tone: voiceConnectedDevices ? "good" : "neutral",
              text: String(voiceConnectedDevices)
            }))
          ),

          h(Box, null,
            SectionTitle("Devices"),
            h(DeviceSummaryRow, { label: "Current", value: currentDevices, tone: currentDevices ? "good" : "neutral" }),
            h(DeviceSummaryRow, { label: "Recent", value: recentDevices, tone: recentDevices ? "warn" : "neutral" }),
            h(DeviceSummaryRow, { label: "Stale", value: staleDevices, tone: staleDevices ? "bad" : "neutral" }),
            h(DeviceSummaryRow, { label: "Never", value: neverDevices, tone: "neutral" })
          )
        )
      ),

      h(Box, null,
        SectionTitle("Device-detaljer", h("div", { className: "muted", style: { fontSize: "12px" } }, devices.length ? (String(devices.length) + " devices") : "Inga devices")),
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
        })) : h("div", { className: "muted" }, "Inga devices hittades för användaren.")
      ),

      h(Box, null,
        SectionTitle("Debug"),
        h(JsonToggle, { data: { userData: userData, cardData: cardData, voiceData: voiceData } })
      )
    );
  }

  window.OnboardingUserDetailPage = OnboardingUserDetailPage;
})();
