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

  function sideUnits(units, side){
    var out = {};
    var want = String(side || "");
    Object.keys(units || {}).forEach(function(k){
      var u = units[k] || {};
      if (String(u.side || "") === want) out[k] = u;
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


  function DetailTabButton(props){
    var label = props.label;
    var active = !!props.active;
    var onClick = props.onClick;
    return e("button", {
      type: "button",
      onClick: onClick,
      style: {
        padding: "6px 10px",
        borderRadius: 8,
        border: "1px solid rgba(255,255,255,0.10)",
        background: active ? "rgba(255,255,255,0.10)" : "transparent",
        color: "inherit",
        cursor: "pointer",
        fontSize: 12
      }
    }, label);
  }

  function workChainRows(work){
    return (Array.isArray(work) ? work : []).map(function(chain, idx){
      var items = Array.isArray(chain) ? chain.filter(Boolean) : [];
      var root = items.length ? items[0] : {};
      return {
        key: idx,
        title: String(root.title || root.action || "work"),
        description: String(root.description || ""),
        action: String(root.action || ""),
        status: String(root.status || ""),
        duration_s: Number(root.duration_s || 0),
        deadline_sim_time_s: root.deadline_sim_time_s,
        params: root.params || {},
        items: items
      };
    });
  }

  function WorkItemCard(props){
    var r = props.row || {};
    var compact = !!props.compact;
    return e("div", {
      style: {
        padding: 10,
        borderRadius: 8,
        background: compact ? "rgba(255,255,255,0.025)" : "rgba(255,255,255,0.04)",
        border: "1px solid rgba(255,255,255,0.06)",
        opacity: compact ? 0.9 : 1
      }
    },
      e("div", { style: { fontWeight: 600, fontSize: 13 } }, r.title),
      e("div", { style: { fontSize: 12, opacity: 0.7, marginTop: 2 } },
        [
          r.action,
          r.status,
          r.duration_s ? (r.duration_s + "s") : "",
          (r.deadline_sim_time_s != null) ? ("ddl " + fmtSimTime(r.deadline_sim_time_s)) : ""
        ].filter(Boolean).join(" · ")
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
  }

  function WorkChainCard(props){
    var chain = props.chain || {};
    var items = Array.isArray(chain.items) ? chain.items : [];
    return e("div", {
      style: {
        padding: 10,
        borderRadius: 8,
        background: "rgba(255,255,255,0.03)",
        border: "1px solid rgba(255,255,255,0.06)"
      }
    },
      e("div", { style: { fontWeight: 600, marginBottom: 8, fontSize: 13 } },
        "Kedja " + String((chain.key || 0) + 1)
      ),
      items.length ? e("div", { style: { display: "grid", gap: 8 } },
        items.map(function(it, i){
          return e(WorkItemCard, {
            key: i,
            row: {
              key: i,
              title: String(it.title || it.action || "work"),
              description: String(it.description || ""),
              action: String(it.action || ""),
              status: String(it.status || ""),
              duration_s: Number(it.duration_s || 0),
              deadline_sim_time_s: it.deadline_sim_time_s,
              params: it.params || {}
            },
            compact: false
          });
        })
      ) : e("div", { style: { opacity: 0.7, fontSize: 13 } }, "Tom kedja.")
    );
  }

  function UnitDetail(props){
    const u = props.unit;
    const initialTab = props.initialTab || "status";
    const tabState = React.useState(initialTab);
    const tab = tabState[0];
    const setTab = tabState[1];

    React.useEffect(function(){
      setTab(initialTab || "status");
    }, [u && u.callsign, initialTab]);

    if (!u) return e(Box, null, e("div", { style: { opacity: 0.75 } }, "Select a unit"));

    const active = workRootRows(u.work || []);
    const completed = workRootRows(u.completed_work || []);
    const futureChains = workChainRows(u.work || []).map(function(c){
      return {
        key: c.key,
        items: (c.items || []).slice(1)
      };
    }).filter(function(c){ return c.items.length > 0; });
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
        e("div", { style: { display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 10 } },
          e(DetailTabButton, {
            label: "Status",
            active: tab === "status",
            onClick: function(){ setTab("status"); }
          }),
          e(DetailTabButton, {
            label: "Current Work",
            active: tab === "current",
            onClick: function(){ setTab("current"); }
          }),
          e(DetailTabButton, {
            label: "Future Work",
            active: tab === "future",
            onClick: function(){ setTab("future"); }
          }),
          e(DetailTabButton, {
            label: "Correspondence",
            active: tab === "corr",
            onClick: function(){ setTab("corr"); }
          })
        ),

        tab === "status" ? e("div", { style: { display: "grid", gap: 12 } },
          e("div", null,
            e("div", { style: { fontWeight: 600, marginBottom: 8 } }, "Avslutat arbete"),
            completed.length ? e("div", { style: { display: "grid", gap: 8 } },
              completed.map(function(r){
                return e(WorkItemCard, { key: r.key, row: r, compact: true });
              })
            ) : e("div", { style: { opacity: 0.7, fontSize: 13 } }, "Inget avslutat arbete ännu.")
          ),
          e("div", null,
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
        ) : null,

        tab === "current" ? (
          active.length ? e("div", { style: { display: "grid", gap: 8 } },
            active.map(function(r){
              return e(WorkItemCard, { key: r.key, row: r, compact: false });
            })
          ) : e("div", { style: { opacity: 0.7, fontSize: 13 } }, "Ingen aktiv work-kedja.")
        ) : null,

        tab === "future" ? (
          futureChains.length ? e("div", { style: { display: "grid", gap: 8 } },
            futureChains.map(function(c){
              return e(WorkChainCard, { key: c.key, chain: c });
            })
          ) : e("div", { style: { opacity: 0.7, fontSize: 13 } }, "Ingen framtida work i kedjorna.")
        ) : null,

        tab === "corr" ? (
          corr.length ? e("div", { style: { display: "grid", gap: 8, maxHeight: 520, overflow: "auto" } },
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
        ) : null
      )
    );

    function row(k, v){
      return [
        e("div", { key: k + "-k", style: { opacity: 0.7 } }, String(k || "")),
        e("div", { key: k + "-v" }, String(v == null ? "" : v))
      ];
    }
  }




  function markerSymbolForUnit(m){
    var roots = workRootRows((m && m.work) || []);
    var root = roots.length ? roots[0] : {};
    var action = String(root.action || "");
    if (action === "move_unit") return "→";
    if (action === "llm_replan_from_inbox" || action === "llm_replan_from_deadline" || action === "llm_replan_from_world_change") return "P";
    if (action === "observe_area") return "O";
    if (action === "hold_position") return "H";
    return "";
  }

  function ReplayMap(props){
    const hostRef = React.useRef(null);
    const mapRef = React.useRef(null);
    const layerRef = React.useRef(null);

    const markers = Array.isArray(props.markers) ? props.markers : [];
    const units = props.units || {};

    React.useEffect(function(){
      if (!hostRef.current || !window.L) return;
      if (mapRef.current) return;

      var first = markers[0] || {};
      var lat = Number(first.lat || 55.422);
      var lon = Number(first.lon || 13.918);

      var map = window.L.map(hostRef.current, {
        zoomControl: true,
        attributionControl: true
      }).setView([lat, lon], 14);

      window.L.tileLayer("/api/geo/tiles/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: "&copy; OpenStreetMap contributors"
      }).addTo(map);

      mapRef.current = map;
      layerRef.current = window.L.layerGroup().addTo(map);

      setTimeout(function(){ map.invalidateSize(); }, 0);
    }, []);

    React.useEffect(function(){
      var map = mapRef.current;
      var layer = layerRef.current;
      if (!map || !layer || !window.L) return;

      layer.clearLayers();

      var bounds = [];
      markers.forEach(function(m){
        var lat = Number(m.lat);
        var lon = Number(m.lon);
        if (!isFinite(lat) || !isFinite(lon)) return;

        var side = String(m.side || "");
        var status = String(m.status || "");
        var role = String(m.role || "");
        var label = String(m.label || m.callsign || "");
        var unit = units[String(m.callsign || "")] || {};
        var symbol = markerSymbolForUnit(unit);

        var color = side === "red" ? "#ff6b6b" : "#6bb6ff";
        var radius = role === "platoon" ? 9 : 7;
        if (status === "working") radius += 2;

        var base = window.L.circleMarker([lat, lon], {
          radius: radius,
          color: color,
          weight: 2,
          fillColor: color,
          fillOpacity: 0.75
        });

        base.on("click", function(){
          if (props.onSelect) props.onSelect(String(m.callsign || ""));
        });
        base.bindTooltip(label, { permanent: true, direction: "top", offset: [0, -8] });
        base.addTo(layer);

        if (symbol) {
          var icon = window.L.marker([lat, lon], {
            interactive: true,
            icon: window.L.divIcon({
              className: "replay-map-symbol",
              html: '<div style="color:' + color + ';font-weight:700;font-size:14px;text-shadow:0 0 2px #000;">' + symbol + '</div>',
              iconSize: [16, 16],
              iconAnchor: [8, 8]
            })
          });
          icon.on("click", function(){
            if (props.onSelect) props.onSelect(String(m.callsign || ""));
          });
          icon.addTo(layer);
        }

        bounds.push([lat, lon]);
      });

      if (bounds.length === 1) {
        map.setView(bounds[0], Math.max(map.getZoom(), 14));
      } else if (bounds.length > 1) {
        map.fitBounds(bounds, { padding: [20, 20] });
      }

      setTimeout(function(){ map.invalidateSize(); }, 0);
    }, [JSON.stringify(markers), JSON.stringify(units)]);

    return e(Box, null,
      e("div", { style: { fontWeight: 600, marginBottom: 8 } }, "Karta"),
      e("div", {
        ref: hostRef,
        style: {
          height: "100%",
          minHeight: 520,
          borderRadius: 10,
          overflow: "hidden",
          background: "#1b1f24"
        }
      })
    );
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
    const [detailTab, setDetailTab] = React.useState("status");

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
                onSelect: function(cs){
                  setSelectedUnit(cs);
                  setDetailTab("status");
                },
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
            units: filteredUnits,
            onSelect: function(cs){
              setSelectedUnit(cs);
              setDetailTab("status");
            }
          })
        ),

        e("div", { style: { minHeight: 0, overflow: "auto" } },
          e(UnitDetail, {
            unit: selected && selected.side === selectedSide ? selected : null,
            initialTab: detailTab
          })
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
