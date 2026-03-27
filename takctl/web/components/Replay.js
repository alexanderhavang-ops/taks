/* global React */
(function () {
  var h = (window.h || React.createElement); window.h = h;
  const e = h;

  async function postJson(url, body){
    const r = await fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {})
    });
    const t = await r.text();
    let j = null;
    try { j = JSON.parse(t); } catch (_) {}
    if (!r.ok) {
      const msg = (j && (j.detail || j.error)) ? String(j.detail || j.error) : ("HTTP " + r.status + ": " + t.slice(0, 400));
      throw new Error(msg);
    }
    return j || {};
  }

  function Box(props){
    return e("div", {
      style: {
        background: "rgba(255,255,255,0.03)",
        border: "1px solid rgba(255,255,255,0.08)",
        borderRadius: 12,
        padding: 12,
        minHeight: 0
      }
    }, props.children);
  }

  function ToolbarButton(props){
    return e("button", {
      type: "button",
      className: "btn",
      onClick: props.onClick,
      disabled: !!props.disabled
    }, props.label);
  }

  function SideTab(props){
    var active = !!props.active;
    return e("button", {
      type: "button",
      onClick: props.onClick,
      style: {
        padding: "6px 10px",
        borderRadius: 8,
        border: "1px solid rgba(255,255,255,0.10)",
        background: active ? "rgba(255,255,255,0.10)" : "transparent",
        color: "inherit",
        cursor: "pointer"
      }
    }, props.label);
  }

  function fmtSimTime(sim){
    var s = Number(sim || 0);
    var m = Math.floor(s / 60);
    var h = Math.floor(m / 60);
    m = m % 60;
    return h + "h " + m + "m";
  }

  function roleShort(role){
    return String(role || "");
  }

  function defaultExpandedMap(tree){
    var out = {};
    (tree || []).forEach(function walk(n){
      if (!n || !n.callsign) return;
      out[n.callsign] = true;
      (n.children || []).forEach(walk);
    });
    return out;
  }

  function TreeNode(props){
    const node = props.node || {};
    const selected = props.selected === node.callsign;
    const kids = Array.isArray(node.children) ? node.children : [];
    const hasKids = kids.length > 0;
    const expanded = !!props.expanded[node.callsign];

    return e("div", { style: { marginLeft: props.depth ? 14 : 0 } },
      e("div", {
        style: {
          display: "grid",
          gridTemplateColumns: "22px 1fr auto",
          gap: 8,
          alignItems: "center",
          padding: "5px 8px",
          borderRadius: 8,
          background: selected ? "rgba(255,255,255,0.08)" : "transparent",
          fontSize: 13
        }
      },
        e("button", {
          type: "button",
          onClick: function(ev){
            ev.stopPropagation();
            if (hasKids) props.onToggle(node.callsign);
          },
          style: {
            width: 20, height: 20, borderRadius: 6,
            border: "1px solid rgba(255,255,255,0.10)",
            background: "transparent", color: "inherit",
            cursor: hasKids ? "pointer" : "default",
            opacity: hasKids ? 1 : 0.25, padding: 0
          }
        }, hasKids ? (expanded ? "−" : "+") : "·"),

        e("div", {
          onClick: function(){ props.onSelect(node.callsign); },
          style: { cursor: "pointer", minWidth: 0 }
        },
          e("div", { style: { display: "flex", gap: 6, alignItems: "baseline", flexWrap: "wrap" } },
            e("span", { style: { fontWeight: selected ? 700 : 500 } }, node.callsign || ""),
            e("span", { style: { opacity: 0.65, fontSize: 12 } }, (node.side || "") + " · " + roleShort(node.role))
          )
        ),

        e("div", {
          onClick: function(){ props.onSelect(node.callsign); },
          style: { cursor: "pointer", opacity: 0.7, fontSize: 12, whiteSpace: "nowrap" }
        }, node.readiness || "")
      ),

      (hasKids && expanded) ? kids.map(function(k){
        return e(TreeNode, {
          key: k.callsign,
          node: k,
          selected: props.selected,
          onSelect: props.onSelect,
          depth: (props.depth || 0) + 1,
          expanded: props.expanded,
          onToggle: props.onToggle
        });
      }) : null
    );
  }

  function workRootRows(work){
    return (Array.isArray(work) ? work : []).map(function(chain, idx){
      var root = (Array.isArray(chain) && chain.length && chain[0]) ? chain[0] : {};
      return {
        key: idx,
        title: String(root.title || root.action || "work"),
        description: String(root.description || ""),
        action: String(root.action || ""),
        status: String(root.status || ""),
        duration_s: Number(root.duration_s || 0),
        deadline_sim_time_s: root.deadline_sim_time_s,
        params: root.params || {}
      };
    });
  }

  function correspondenceRows(unit){
    var inbox = Array.isArray(unit && unit.recent_inbox) ? unit.recent_inbox : [];
    var outbox = Array.isArray(unit && unit.recent_outbox) ? unit.recent_outbox : [];
    var rows = [];

    inbox.forEach(function(x, i){
      rows.push({
        key: "in-" + i,
        dir: "in",
        sim_time_s: Number(x.sim_time_s || 0),
        from: String(x.from || ""),
        to: String(x.to || ""),
        kind: String(x.kind || ""),
        message: String(x.message || "")
      });
    });

    outbox.forEach(function(x, i){
      rows.push({
        key: "out-" + i,
        dir: "out",
        sim_time_s: Number(x.sim_time_s || 0),
        from: String(x.from || ""),
        to: String(x.to || ""),
        kind: String(x.kind || ""),
        message: String(x.message || "")
      });
    });

    rows.sort(function(a, b){
      if (a.sim_time_s !== b.sim_time_s) return a.sim_time_s - b.sim_time_s;
      return String(a.key).localeCompare(String(b.key));
    });
    return rows;
  }

  function UnitDetail(props){
    const u = props.unit;
    if (!u) return e(Box, null, e("div", { style: { opacity: 0.75 } }, "Select a unit"));

    const active = workRootRows(u.work || []);
    const done = workRootRows(u.completed_work || []);
    const corr = correspondenceRows(u);

    return e("div", { style: { display: "grid", gap: 12 } },

      e(Box, null,
        e("div", { style: { fontWeight: 700, marginBottom: 8, fontSize: 18 } }, u.callsign || ""),
        e("div", { style: { display: "grid", gridTemplateColumns: "140px 1fr", gap: 6, fontSize: 13 } },
          row("Side", u.side),
          row("Role", u.role),
          row("Superior", u.superior || ""),
          row("Subordinates", (u.subordinates || []).join(", ")),
          row("Readiness", u.readiness || ""),
          row("Posture", u.posture || ""),
          row("Strength", u.strength),
          row("Combat value", u.combat_value || ""),
          row("Ammo", u.ammo || ""),
          row("Morale", u.morale || ""),
          row("Position", ((u.position || {}).lat || "") + ", " + ((u.position || {}).lon || ""))
        )
      ),

      e(Box, null,
        e("div", { style: { fontWeight: 600, marginBottom: 8 } }, "Aktivt work[]"),
        active.length ? e("div", { style: { display: "grid", gap: 8 } },
          active.map(function(r){
            return e("div", {
              key: r.key,
              style: {
                padding: 10,
                borderRadius: 8,
                background: "rgba(255,255,255,0.04)",
                border: "1px solid rgba(255,255,255,0.06)"
              }
            },
              e("div", { style: { fontWeight: 600, fontSize: 13 } }, r.title),
              e("div", { style: { fontSize: 12, opacity: 0.7, marginTop: 2 } },
                [r.action, r.status, r.duration_s ? (r.duration_s + "s") : ""].filter(Boolean).join(" · ")
              ),
              r.description ? e("div", { style: { fontSize: 12, marginTop: 4, opacity: 0.9 } }, r.description) : null,
              e("pre", {
                style: {
                  margin: "6px 0 0 0",
                  whiteSpace: "pre-wrap",
                  overflowWrap: "anywhere",
                  fontSize: 12,
                  lineHeight: "16px",
                  background: "rgba(0,0,0,0.15)",
                  padding: 8,
                  borderRadius: 8
                }
              }, JSON.stringify(r.params || {}, null, 2))
            );
          })
        ) : e("div", { style: { opacity: 0.7, fontSize: 13 } }, "Ingen aktiv work-kedja.")
      ),

      e(Box, null,
        e("div", { style: { fontWeight: 600, marginBottom: 8 } }, "completed_work[]"),
        done.length ? e("div", { style: { display: "grid", gap: 8 } },
          done.map(function(r){
            return e("div", {
              key: r.key,
              style: {
                padding: 10,
                borderRadius: 8,
                background: "rgba(255,255,255,0.025)",
                border: "1px solid rgba(255,255,255,0.06)",
                opacity: 0.85
              }
            },
              e("div", { style: { fontWeight: 600, fontSize: 13 } }, r.title),
              e("div", { style: { fontSize: 12, opacity: 0.7, marginTop: 2 } },
                [r.action, r.status].filter(Boolean).join(" · ")
              )
            );
          })
        ) : e("div", { style: { opacity: 0.7, fontSize: 13 } }, "Inget avslutat arbete ännu.")
      ),

      e(Box, null,
        e("div", { style: { fontWeight: 600, marginBottom: 8 } }, "Korrespondens"),
        corr.length ? e("div", { style: { display: "grid", gap: 8, maxHeight: 260, overflow: "auto" } },
          corr.map(function(r){
            return e("div", {
              key: r.key,
              style: {
                paddingBottom: 8,
                borderBottom: "1px solid rgba(255,255,255,0.06)",
                fontSize: 13
              }
            },
              e("div", { style: { opacity: 0.7, marginBottom: 3 } },
                fmtSimTime(r.sim_time_s) + " · " + r.dir + " · " + r.from + " → " + r.to + " · " + r.kind
              ),
              e("div", null, r.message)
            );
          })
        ) : e("div", { style: { opacity: 0.7, fontSize: 13 } }, "Ingen korrespondens ännu.")
      ),

      e(Box, null,
        e("div", { style: { fontWeight: 600, marginBottom: 8 } }, "Rått state.json"),
        e("pre", {
          style: {
            margin: 0,
            whiteSpace: "pre-wrap",
            overflowWrap: "anywhere",
            fontSize: 12,
            lineHeight: "16px",
            maxHeight: 360,
            overflow: "auto",
            background: "rgba(0,0,0,0.15)",
            padding: 10,
            borderRadius: 8
          }
        }, JSON.stringify(u.raw_state || {}, null, 2))
      )
    );

    function row(k, v){
      return [
        e("div", { key: k + "-k", style: { opacity: 0.7 } }, String(k || "")),
        e("div", { key: k + "-v" }, String(v == null ? "" : v))
      ];
    }
  }

  function ReplayMap(props){
    const markers = Array.isArray(props.markers) ? props.markers : [];
    const w = 900, h = 520, pad = 28;

    if (!markers.length) {
      return e(Box, null, e("div", { style: { opacity: 0.75 } }, "No map markers yet"));
    }

    let minLat = markers[0].lat, maxLat = markers[0].lat;
    let minLon = markers[0].lon, maxLon = markers[0].lon;
    markers.forEach(function(m){
      minLat = Math.min(minLat, m.lat);
      maxLat = Math.max(maxLat, m.lat);
      minLon = Math.min(minLon, m.lon);
      maxLon = Math.max(maxLon, m.lon);
    });

    if (minLat === maxLat) { minLat -= 0.002; maxLat += 0.002; }
    if (minLon === maxLon) { minLon -= 0.002; maxLon += 0.002; }

    function x(lon){ return pad + ((lon - minLon) / (maxLon - minLon)) * (w - pad * 2); }
    function y(lat){ return h - pad - ((lat - minLat) / (maxLat - minLat)) * (h - pad * 2); }

    return e(Box, null,
      e("svg", {
        viewBox: "0 0 " + w + " " + h,
        style: { width: "100%", height: 520, display: "block", background: "rgba(255,255,255,0.02)", borderRadius: 8 }
      },
        markers.map(function(m){
          var fill = (m.side === "red") ? "#d55" : "#6cf";
          var cx = x(m.lon), cy = y(m.lat);
          return e("g", {
            key: m.callsign,
            onClick: function(){ props.onSelect && props.onSelect(m.callsign); },
            style: { cursor: "pointer" }
          },
            e("circle", { cx: cx, cy: cy, r: 7, fill: fill }),
            e("text", {
              x: cx + 9, y: cy - 8, fill: "currentColor",
              style: { fontSize: 12, fontWeight: 600 }
            }, m.callsign)
          );
        })
      )
    );
  }

  function sideUnits(units, side){
    var out = {};
    Object.keys(units || {}).forEach(function(k){
      var u = units[k];
      if (u && u.side === side) out[k] = u;
    });
    return out;
  }

  function ReplayView(){
    const scenarios = useApi("api/replay/scenarios", { cacheMs: 60000, pollMs: 0 });
    const state = useApi("api/replay/state", { cacheMs: 0, pollMs: 2000 });

    const [selectedScenario, setSelectedScenario] = React.useState("at1_contact_001");
    const [selectedSide, setSelectedSide] = React.useState("blue");
    const [selectedUnit, setSelectedUnit] = React.useState(null);
    const [busy, setBusy] = React.useState(false);
    const [error, setError] = React.useState("");
    const [orderTextBlue, setOrderTextBlue] = React.useState("");
    const [orderTextRed, setOrderTextRed] = React.useState("");
    const [expandedBlue, setExpandedBlue] = React.useState({});
    const [expandedRed, setExpandedRed] = React.useState({});

    React.useEffect(function(){
      var items = (((scenarios || {}).data || {}).items || []);
      if (items.length && !selectedScenario) setSelectedScenario(String(items[0].id || ""));
    }, [scenarios && scenarios.data]);

    React.useEffect(function(){
      var data = (state && state.data) || {};
      var trees = data.trees || {};
      var blueTree = trees.blue || [];
      var redTree = trees.red || [];

      if (!Object.keys(expandedBlue || {}).length && blueTree.length) setExpandedBlue(defaultExpandedMap(blueTree));
      if (!Object.keys(expandedRed || {}).length && redTree.length) setExpandedRed(defaultExpandedMap(redTree));

      var orders = data.initial_orders || {};
      setOrderTextBlue(String((((orders.blue) || {}).text) || ""));
      setOrderTextRed(String((((orders.red) || {}).text) || ""));

      if (data.scenario && data.scenario.id) setSelectedScenario(String(data.scenario.id));

      var units = data.units || {};
      if (!selectedUnit) {
        var keys = Object.keys(units);
        if (keys.length) setSelectedUnit(keys[0]);
      } else if (!units[selectedUnit]) {
        var sideKeys = Object.keys(sideUnits(units, selectedSide));
        setSelectedUnit(sideKeys.length ? sideKeys[0] : null);
      }
    }, [state && state.data]);

    function toggleNodeBlue(cs){
      setExpandedBlue(function(prev){
        var next = Object.assign({}, prev || {});
        next[cs] = !next[cs];
        return next;
      });
    }

    function toggleNodeRed(cs){
      setExpandedRed(function(prev){
        var next = Object.assign({}, prev || {});
        next[cs] = !next[cs];
        return next;
      });
    }

    async function doReset(){
      setBusy(true); setError("");
      try {
        await postJson("/api/replay/reset", { scenario_id: selectedScenario });
      } catch (e) {
        setError(String((e && e.message) || e || "Reset failed"));
      } finally {
        setBusy(false);
      }
    }

    async function doSaveOrder(side){
      setBusy(true); setError("");
      try {
        await postJson("/api/replay/order0", {
          side: side,
          text: side === "blue" ? orderTextBlue : orderTextRed
        });
      } catch (e) {
        setError(String((e && e.message) || e || "Save failed"));
      } finally {
        setBusy(false);
      }
    }

    async function doSendOrder(side){
      setBusy(true); setError("");
      try {
        await postJson("/api/replay/send_order0", {
          side: side,
          text: side === "blue" ? orderTextBlue : orderTextRed
        });
      } catch (e) {
        setError(String((e && e.message) || e || "Send failed"));
      } finally {
        setBusy(false);
      }
    }

    async function doTick(){
      setBusy(true); setError("");
      try {
        await postJson("/api/replay/tick", {});
      } catch (e) {
        setError(String((e && e.message) || e || "Tick failed"));
      } finally {
        setBusy(false);
      }
    }

    const data = (state && state.data) || {};
    const items = (scenarios && scenarios.data && scenarios.data.items) || [];
    const units = data.units || {};
    const filteredUnits = sideUnits(units, selectedSide);
    const selected = selectedUnit ? units[selectedUnit] : null;
    const trees = data.trees || {};
    const tree = selectedSide === "blue" ? (trees.blue || []) : (trees.red || []);
    const expanded = selectedSide === "blue" ? expandedBlue : expandedRed;
    const toggleNode = selectedSide === "blue" ? toggleNodeBlue : toggleNodeRed;
    const chatBySide = data.chat_by_side || {};
    const chat = Array.isArray(chatBySide[selectedSide]) ? chatBySide[selectedSide] : [];
    const markers = (((data.map || {}).markers) || []).filter(function(m){ return m.side === selectedSide; });

    return e("div", { style: { display: "grid", gap: 12, height: "calc(100vh - 110px)" } },

      e(Box, null,
        e("div", { style: { display: "grid", gap: 10 } },

          e("div", { style: { display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" } },
            e("select", {
              value: selectedScenario,
              onChange: function(ev){ setSelectedScenario(ev.target.value); },
              style: {
                background: "rgba(0,0,0,0.15)",
                color: "inherit",
                border: "1px solid rgba(255,255,255,0.12)",
                borderRadius: 8,
                padding: "8px 10px"
              }
            },
              items.map(function(it){
                return e("option", { key: it.id, value: it.id }, it.title || it.id);
              })
            ),
            e(ToolbarButton, { label: "Reset", onClick: doReset, disabled: busy }),
            e(ToolbarButton, { label: "Tick", onClick: doTick, disabled: busy }),
            e("span", { style: { opacity: 0.75, fontSize: 13 } },
              "Tick: " + String((((data.runtime || {}).current_tick) || 0)) +
              " · step " + String((((data.runtime || {}).tick_interval_sec) || 0)) + "s"
            )
          ),

          e("div", { style: { display: "flex", gap: 8 } },
            e(SideTab, {
              label: "Blå",
              active: selectedSide === "blue",
              onClick: function(){ setSelectedSide("blue"); }
            }),
            e(SideTab, {
              label: "Röd",
              active: selectedSide === "red",
              onClick: function(){ setSelectedSide("red"); }
            })
          ),

          e("div", null,
            e("div", { style: { fontSize: 12, opacity: 0.75, marginBottom: 4 } },
              selectedSide === "blue" ? "Initial order blå" : "Initial order röd"
            ),
            e("textarea", {
              value: selectedSide === "blue" ? orderTextBlue : orderTextRed,
              onChange: function(ev){
                if (selectedSide === "blue") setOrderTextBlue(ev.target.value);
                else setOrderTextRed(ev.target.value);
              },
              rows: 5,
              style: {
                width: "100%",
                resize: "vertical",
                borderRadius: 10,
                border: "1px solid rgba(255,255,255,0.12)",
                background: "rgba(0,0,0,0.15)",
                color: "inherit",
                padding: 12,
                boxSizing: "border-box",
                font: "inherit"
              }
            }),
            e("div", { style: { marginTop: 8, display: "flex", gap: 8 } },
              e(ToolbarButton, {
                label: "Save order text",
                onClick: function(){ doSaveOrder(selectedSide); },
                disabled: busy
              }),
              e(ToolbarButton, {
                label: "Send initial order",
                onClick: function(){ doSendOrder(selectedSide); },
                disabled: busy
              })
            )
          ),

          error ? e("div", { style: { color: "#ff8f8f" } }, error) : null
        )
      ),

      e("div", {
        style: {
          display: "grid",
          gridTemplateColumns: "320px 1fr 420px",
          gap: 12,
          minHeight: 0,
          flex: "1 1 auto"
        }
      },
        e("div", { style: { minHeight: 0, overflow: "auto" } },
          e(Box, null,
            e("div", { style: { fontWeight: 600, marginBottom: 8 } },
              selectedSide === "blue" ? "Blå enheter" : "Röda enheter"
            ),
            tree.map(function(n){
              return e(TreeNode, {
                key: n.callsign,
                node: n,
                selected: selectedUnit,
                onSelect: setSelectedUnit,
                depth: 0,
                expanded: expanded,
                onToggle: toggleNode
              });
            })
          )
        ),

        e("div", { style: { minHeight: 0, overflow: "auto" } },
          e(ReplayMap, {
            markers: markers,
            onSelect: setSelectedUnit
          })
        ),

        e("div", { style: { minHeight: 0, overflow: "auto" } },
          e(UnitDetail, { unit: selected && selected.side === selectedSide ? selected : null })
        )
      ),

      e(Box, null,
        e("div", { style: { fontWeight: 600, marginBottom: 8 } },
          selectedSide === "blue" ? "Blå korrespondens" : "Röd korrespondens"
        ),
        chat.length ? e("div", { style: { display: "grid", gap: 8, maxHeight: 240, overflow: "auto" } },
          chat.map(function(r){
            return e("div", {
              key: r.key,
              style: {
                fontSize: 13,
                paddingBottom: 8,
                borderBottom: "1px solid rgba(255,255,255,0.06)"
              }
            },
              e("div", { style: { opacity: 0.7, marginBottom: 3 } },
                fmtSimTime(r.sim_time_s) + " · " + r.agent + " · " + r.from + " → " + r.to + " · " + r.kind
              ),
              e("div", null, r.message)
            );
          })
        ) : e("div", { style: { opacity: 0.7, fontSize: 13 } }, "Ingen korrespondens ännu.")
      )
    );
  }

  window.ReplayView = ReplayView;
})();
