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

  function normalizeConfigResponse(d){
    if (!d || typeof d !== "object") return { items: [] };
    if (Array.isArray(d.items)) return d;

    const cfg = (d.config && typeof d.config === "object") ? d.config : {};
    const sec = (d.secrets && typeof d.secrets === "object") ? d.secrets : {};
    const meta = (d.meta && typeof d.meta === "object") ? d.meta : {};
    const cfgOwners = (d.config_owners && typeof d.config_owners === "object") ? d.config_owners : {};
    const secOwners = (d.secret_owners && typeof d.secret_owners === "object") ? d.secret_owners : {};

    const items = [];
    const seen = Object.create(null);

    function pushObject(obj, isSecret){
      Object.keys(obj).sort().forEach(function(name){
        if (seen[name]) return;
        seen[name] = true;

        const m = (meta[name] && typeof meta[name] === "object") ? meta[name] : {};
        const owner = isSecret ? secOwners[name] : cfgOwners[name];
        items.push({
          name: name,
          value: obj[name],
          secret: !!(isSecret || m.secret === true),
          is_set: isSecret ? String(obj[name] || "").trim() !== "" : true,
          owner: owner || "",
          component: owner || m.component || "",
          meta: m
        });
      });
    }

    pushObject(cfg, false);
    pushObject(sec, true);

    return Object.assign({}, d, { items: items });
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

  function helpTextStyle(){
    return {
      opacity: .72,
      fontSize: 12,
      marginTop: 6,
      lineHeight: "17px"
    };
  }

  function prettyComponentName(name){
    const n = String(name || "").trim();
    if (!n) return "Other";
    if (n === "core") return "Core";
    if (n === "llm") return "LLM";
    if (n === "marti") return "Marti";
    if (n === "martine") return "Martine";
    if (n === "onboarding") return "Onboarding";
    if (n === "replay") return "Simulera";
    if (n === "weather") return "Weather";
    if (n === "certs") return "Certs";
    if (n === "legacy") return "Legacy";
    return n.charAt(0).toUpperCase() + n.slice(1);
  }

  function groupNameForItem(item){
    if (item && item.owner) return prettyComponentName(item.owner);
    if (item && item.component) return prettyComponentName(item.component);
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
      const g = groupNameForItem(item);
      if (!groups[g]) groups[g] = [];
      groups[g].push(item);
    });

    const preferredOrder = ["Core", "Certs", "Marti", "Martine", "Onboarding", "LLM", "Weather", "Simulera", "Policy", "Logging", "Legacy", "Other"];
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

  function metaLine(item){
    const meta = (item && item.meta) || {};
    const bits = [];
    if (meta.type) bits.push("type: " + meta.type);
    if (!item.secret && Object.prototype.hasOwnProperty.call(meta, "default")) {
      bits.push("default: " + String(meta.default || ""));
    }
    if (item.component) bits.push("component: " + String(item.component));
    return bits.join(" · ");
  }

  function ItemRow(props){
    const item = props.item;
    const edits = props.edits;
    const setEdits = props.setEdits;
    const saving = !!props.saving;

    const changed = isChanged(item, edits);
    const val = currentUiValue(item, edits);
    const meta = item.meta || {};
    const metaInfo = metaLine(item);

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
      e("div", null, [
        e("div", {
          style: {
            fontSize: 13,
            fontWeight: 700,
            opacity: 0.96,
            paddingTop: 8
          }
        }, String(item.name || "")),
        metaInfo ? e("div", { style: helpTextStyle() }, metaInfo) : null
      ]),

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
        meta.doc
          ? e("div", { style: helpTextStyle() }, String(meta.doc))
          : null,
        item.secret
          ? e("div", {
              style: helpTextStyle()
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
        setData(normalizeConfigResponse(d));
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
        setData(normalizeConfigResponse(d));
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

    if (loading) {
      return e("div", { style: cardStyle() }, "Loading config…");
    }

    if (err) {
      return e("div", { style: cardStyle({ border: "1px solid rgba(248,81,73,.35)" }) }, [
        e("div", { style: { fontSize: 18, fontWeight: 800, marginBottom: 8 } }, (String(window.currentLang || window.TAKS_RUNTIME_LANGUAGE || "sv") === "en" ? "Settings" : "Inställningar")),
        e("div", { style: { whiteSpace: "pre-wrap", color: "#ffb4b4" } }, String(err || "Unknown error"))
      ]);
    }

    const items = (data && Array.isArray(data.items)) ? data.items : [];
    const groups = groupItems(items);
    const changed = hasAnyChanges(items, edits);

    return e("div", null, [
      e("div", { style: cardStyle({ marginBottom: 16 }) }, [
        e("div", { style: { fontSize: 22, fontWeight: 800, marginBottom: 8 } }, (String(window.currentLang || window.TAKS_RUNTIME_LANGUAGE || "sv") === "en" ? "Settings" : "Inställningar")),
        e("div", { style: { opacity: .76, fontSize: 13, lineHeight: "18px", marginBottom: 10 } },
          "All values are string-backed in runtime. Metadata is optional and used only for documentation and UI hints."
        ),
        e("div", { style: { display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" } }, [
          e("span", { style: pillStyle("ok") }, String(items.length) + " items"),
          data && data.config_source_kind ? e("span", { style: pillStyle("ok") }, "config: " + data.config_source_kind) : null,
          data && data.secrets_source_kind ? e("span", { style: pillStyle("ok") }, "secrets: " + data.secrets_source_kind) : null,
          changed ? e("span", { style: pillStyle("warn") }, "unsaved changes") : null
        ]),
        e("div", { style: { marginTop: 14, display: "flex", gap: 10 } }, [
          e("button", {
            onClick: save,
            disabled: saving,
            style: {
              border: "1px solid rgba(255,255,255,.12)",
              background: saving ? "rgba(255,255,255,.05)" : "rgba(46,160,67,.25)",
              color: "inherit",
              borderRadius: 10,
              padding: "8px 14px",
              cursor: saving ? "default" : "pointer"
            }
          }, saving ? "Saving…" : "Save"),
          e("button", {
            onClick: load,
            disabled: saving,
            style: {
              border: "1px solid rgba(255,255,255,.12)",
              background: "rgba(255,255,255,.04)",
              color: "inherit",
              borderRadius: 10,
              padding: "8px 14px",
              cursor: saving ? "default" : "pointer"
            }
          }, "Reload"),
          saveMsg ? e("div", { style: { alignSelf: "center", opacity: .8, fontSize: 13 } }, saveMsg) : null
        ])
      ]),
      groups.map(function(group, idx){
        return e(GroupCard, {
          key: idx,
          group: group,
          edits: edits,
          setEdits: setEdits,
          saving: saving
        });
      })
    ]);
  };
})();
