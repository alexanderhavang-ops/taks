/* global React */
(function () {
  var h = (window.h || React.createElement); window.h = h;
  const e = h;

  const _sharedFetchJson = (window.TaksApi && window.TaksApi.fetchJson) || window.fetchJson;

  async function fetchJson(url){
    if (typeof _sharedFetchJson === "function") return await _sharedFetchJson(url);
    const r = await fetch(url, { credentials: "same-origin" });
    const t = await r.text();
    if (!r.ok) throw new Error("HTTP " + r.status + " loading " + url + ": " + t.slice(0, 400));
    try { return JSON.parse(t); } catch { throw new Error("Non-JSON from " + url + ": " + t.slice(0, 400)); }
  }

  async function postJson(url, body){
    const r = await fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      body: JSON.stringify(body || {})
    });
    const t = await r.text();
    let j = null;
    try { j = t ? JSON.parse(t) : null; } catch (_) {}
    if (!r.ok) {
      throw new Error((j && (j.detail || j.error)) || ("HTTP " + r.status + " posting " + url + ": " + t.slice(0, 400)));
    }
    return j;
  }

  function cardStyle(extra){
    return Object.assign({
      border: "1px solid rgba(255,255,255,.06)",
      borderRadius: 18,
      padding: "18px 18px 16px 18px",
      background: "linear-gradient(90deg, rgba(255,255,255,.02), rgba(255,255,255,.01))",
      boxShadow: "0 0 0 1px rgba(0,0,0,.08) inset"
    }, extra || {});
  }

  function pillStyle(kind){
    if (kind === "ok") {
      return {
        display:"inline-flex", alignItems:"center", padding:"2px 10px", borderRadius:999,
        border:"1px solid rgba(46,160,67,.5)", background:"rgba(46,160,67,.25)", fontSize:12, lineHeight:"18px"
      };
    }
    if (kind === "warn") {
      return {
        display:"inline-flex", alignItems:"center", padding:"2px 10px", borderRadius:999,
        border:"1px solid rgba(187,128,9,.5)", background:"rgba(187,128,9,.25)", fontSize:12, lineHeight:"18px"
      };
    }
    return {
      display:"inline-flex", alignItems:"center", padding:"2px 10px", borderRadius:999,
      border:"1px solid rgba(248,81,73,.5)", background:"rgba(248,81,73,.25)", fontSize:12, lineHeight:"18px"
    };
  }

  function inputStyle(){
    return {
      width: "100%",
      boxSizing: "border-box",
      border: "1px solid rgba(255,255,255,.10)",
      background: "rgba(255,255,255,.03)",
      color: "inherit",
      borderRadius: 10,
      padding: "8px 10px",
      fontSize: 13,
      lineHeight: "18px"
    };
  }

  function groupNameForItemName(name){
    const n = String(name || "").toLowerCase();

    if (n.startsWith("llm_") || n.startsWith("bedrock_") || n.startsWith("aws_")) return "LLM";
    if (n.startsWith("replay_")) return "Replay";
    if (n.startsWith("martine_")) return "Martine";
    if (n.startsWith("onboarding_")) return "Onboarding";
    if (
      n.startsWith("db_") ||
      n.startsWith("coreconfig_") ||
      n.startsWith("ca_") ||
      n.startsWith("crl_") ||
      n.startsWith("tak_") ||
      n === "sudo_user" ||
      n === "hostname" ||
      n === "fqdn" ||
      n === "battalion"
    ) return "Core / TAK";
    if (n.startsWith("default_policy_") || n.startsWith("policy_")) return "Policy";
    if (n.startsWith("audit_")) return "Logging";
    return "Other";
  }

  function sortItems(items){
    return (items || []).slice().sort(function(a, b){
      return String(a.name || "").localeCompare(String(b.name || ""));
    });
  }

  function groupItems(items){
    const groups = {};
    sortItems(items).forEach(function(item){
      const g = groupNameForItemName(item && item.name);
      if (!groups[g]) groups[g] = [];
      groups[g].push(item);
    });

    const preferredOrder = ["LLM", "Replay", "Martine", "Core / TAK", "Onboarding", "Policy", "Logging", "Other"];
    const present = Object.keys(groups);

    return preferredOrder
      .filter(function(g){ return present.indexOf(g) >= 0; })
      .concat(
        present.filter(function(g){ return preferredOrder.indexOf(g) < 0; }).sort()
      )
      .map(function(g){
        return { name: g, items: groups[g] || [] };
      });
  }

  function stableValueText(v){
    if (v === null || typeof v === "undefined") return "";
    if (typeof v === "boolean") return v ? "true" : "false";
    return String(v);
  }

  function normalizeValueForEdit(item){
    if (item.secret) return "";
    return stableValueText(item.value);
  }

  function currentUiValue(item, edits){
    if (Object.prototype.hasOwnProperty.call(edits, item.name)) return edits[item.name];
    return normalizeValueForEdit(item);
  }

  function isChanged(item, edits){
    if (!Object.prototype.hasOwnProperty.call(edits, item.name)) return false;
    const next = String(edits[item.name] || "");
    if (item.secret) return next.trim() !== "";
    return next !== normalizeValueForEdit(item);
  }

  function buildUpdatePayload(items, edits){
    const config_updates = {};
    const secret_updates = {};

    (items || []).forEach(function(item){
      if (!isChanged(item, edits)) return;
      const v = String(edits[item.name] || "");
      if (item.secret) secret_updates[item.name] = v;
      else config_updates[item.name] = v;
    });

    return { config_updates: config_updates, secret_updates: secret_updates };
  }

  function hasAnyChanges(items, edits){
    return (items || []).some(function(item){ return isChanged(item, edits); });
  }

  function ItemRow(props){
    const item = props.item;
    const edits = props.edits;
    const setEdits = props.setEdits;
    const saving = !!props.saving;

    const changed = isChanged(item, edits);
    const val = currentUiValue(item, edits);

    return e("div", {
      style: {
        display: "grid",
        gridTemplateColumns: "minmax(220px, 320px) 1fr auto",
        gap: 12,
        alignItems: "start",
        padding: "10px 0",
        borderTop: "1px solid rgba(255,255,255,.05)"
      }
    }, [
      e("div", {
        style: {
          fontSize: 13,
          fontWeight: 700,
          opacity: 0.96,
          paddingTop: 8
        }
      }, String(item.name || "")),

      e("div", null, [
        item.secret
          ? e("input", {
              type: "password",
              value: val,
              placeholder: item.is_set ? "Stored; enter to replace" : "Enter secret",
              disabled: saving,
              style: inputStyle(),
              onChange: function(ev){
                const next = String(ev.target.value || "");
                setEdits(function(prev){
                  const out = Object.assign({}, prev);
                  out[item.name] = next;
                  return out;
                });
              }
            })
          : e("input", {
              type: "text",
              value: val,
              disabled: saving,
              style: Object.assign({}, inputStyle(), changed ? {
                border: "1px solid rgba(187,128,9,.55)",
                background: "rgba(187,128,9,.08)"
              } : null),
              onChange: function(ev){
                const next = String(ev.target.value || "");
                setEdits(function(prev){
                  const out = Object.assign({}, prev);
                  out[item.name] = next;
                  return out;
                });
              }
            }),
        item.secret
          ? e("div", {
              style: {
                opacity: .72,
                fontSize: 12,
                marginTop: 6
              }
            }, item.is_set ? "Secret exists in runtime; leave blank to keep current value." : "Secret is currently empty.")
          : null
      ]),

      e("div", { style: { paddingTop: 8 } },
        item.secret
          ? e("span", { style: pillStyle(changed ? "warn" : (item.is_set ? "ok" : "warn")) }, changed ? "pending" : (item.is_set ? "secret set" : "secret empty"))
          : e("span", { style: pillStyle(changed ? "warn" : "ok") }, changed ? "changed" : "config")
      )
    ]);
  }

  function GroupCard(props){
    const group = props.group;
    const edits = props.edits;
    const setEdits = props.setEdits;
    const saving = !!props.saving;

    const changedCount = (group.items || []).filter(function(item){
      return isChanged(item, edits);
    }).length;

    return e("div", { style: cardStyle({ marginBottom: 16 }) }, [
      e("div", {
        style: {
          fontSize: 18,
          fontWeight: 800,
          marginBottom: 6
        }
      }, group.name),
      e("div", {
        style: {
          opacity: .7,
          fontSize: 13,
          marginBottom: 8
        }
      }, String(group.items.length) + " entries" + (changedCount ? (" · " + changedCount + " changed") : "")),
      e("div", null, group.items.map(function(item, idx){
        return e(ItemRow, {
          key: idx,
          item: item,
          edits: edits,
          setEdits: setEdits,
          saving: saving
        });
      }))
    ]);
  }

  window.ConfigView = function ConfigView() {
    const [data, setData] = React.useState(null);
    const [err, setErr] = React.useState(null);
    const [loading, setLoading] = React.useState(true);
    const [saving, setSaving] = React.useState(false);
    const [saveMsg, setSaveMsg] = React.useState("");
    const [edits, setEdits] = React.useState({});

    async function load(){
      try{
        setLoading(true);
        const d = await fetchJson("/api/config");
        setData(d);
        setErr(null);
        setEdits({});
      }catch(ex){
        setErr(ex && (ex.message || String(ex)));
      }finally{
        setLoading(false);
      }
    }

    async function save(){
      try{
        setSaving(true);
        setErr(null);
        setSaveMsg("");

        const items = (data && Array.isArray(data.items)) ? data.items : [];
        const payload = buildUpdatePayload(items, edits);

        if (!Object.keys(payload.config_updates).length && !Object.keys(payload.secret_updates).length) {
          setSaveMsg("No changes to save.");
          return;
        }

        const d = await postJson("/api/config", payload);
        setData(d);
        setEdits({});
        setSaveMsg("Saved.");
      }catch(ex){
        setErr(ex && (ex.message || String(ex)));
      }finally{
        setSaving(false);
      }
    }

    React.useEffect(function(){
      load();
    }, []);

    const items = (data && Array.isArray(data.items)) ? data.items : [];
    const groups = groupItems(items);
    const dirty = hasAnyChanges(items, edits);

    const header = e("div", {
      style: { marginBottom: 18 }
    }, [
      e("div", {
        style: {
          fontSize: 12,
          letterSpacing: ".08em",
          textTransform: "uppercase",
          opacity: .62,
          fontWeight: 700,
          marginBottom: 8
        }
      }, "System configuration"),
      e("div", {
        style: {
          fontSize: 32,
          lineHeight: "38px",
          fontWeight: 800,
          marginBottom: 10
        }
      }, "Config"),
      e("div", {
        style: {
          opacity: .9,
          maxWidth: 980,
          lineHeight: "24px"
        }
      }, "Runtime configuration editor. Grouping is done in the frontend from variable names. Secrets are never shown after save, only whether they are set.")
    ]);

    const metaCard = e("div", { style: cardStyle({ marginBottom: 16 }) }, [
      e("div", {
        style: {
          fontSize: 18,
          fontWeight: 800,
          marginBottom: 10
        }
      }, "Runtime sources"),
      e("div", {
        style: {
          display: "grid",
          gap: 10
        }
      }, [
        e("div", null, [
          e("div", { style: { fontSize: 13, opacity: .75, marginBottom: 4 } }, "Config path"),
          e("div", { style: { fontFamily:'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace', fontSize:13, overflowWrap:"anywhere" } }, String((data && data.config_path) || ""))
        ]),
        e("div", null, [
          e("div", { style: { fontSize: 13, opacity: .75, marginBottom: 4 } }, "Secrets path"),
          e("div", { style: { fontFamily:'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace', fontSize:13, overflowWrap:"anywhere" } }, String((data && data.secrets_path) || ""))
        ]),
        e("div", {
          style: {
            display: "flex",
            gap: 10,
            alignItems: "center",
            flexWrap: "wrap",
            marginTop: 4
          }
        }, [
          e("button", { onClick: save, type: "button", disabled: saving || !dirty }, saving ? "Saving..." : "Save"),
          e("button", { onClick: load, type: "button", disabled: saving || loading }, loading ? "Reloading..." : "Reload"),
          e("button", {
            onClick: function(){ setEdits({}); setSaveMsg(""); },
            type: "button",
            disabled: saving || !dirty
          }, "Reset unsaved"),
          dirty ? e("span", { style: pillStyle("warn") }, "unsaved changes") : e("span", { style: pillStyle("ok") }, "saved state"),
          saveMsg ? e("span", { style: { opacity: .75, fontSize: 12 } }, saveMsg) : null
        ])
      ])
    ]);

    if (err) {
      return e("div", { className: "config-page" }, [
        header,
        metaCard,
        e("div", { style: cardStyle() }, [
          e("div", {
            style: {
              fontSize: 18,
              fontWeight: 800,
              marginBottom: 10
            }
          }, "Error"),
          e("pre", {
            style: {
              margin: 0,
              opacity: .92,
              whiteSpace: "pre-wrap",
              overflowWrap: "anywhere"
            }
          }, String(err))
        ])
      ]);
    }

    return e("div", { className: "config-page" }, [
      header,
      metaCard
    ].concat(groups.map(function(group, idx){
      return e(GroupCard, {
        key: idx,
        group: group,
        edits: edits,
        setEdits: setEdits,
        saving: saving
      });
    })));
  };
})();
