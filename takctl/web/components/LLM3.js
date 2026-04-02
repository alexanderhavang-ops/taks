(function(){
  const e = React.createElement;

  async function fetchJson(url, opts){
    const r = await fetch(url, Object.assign({headers:{"Content-Type":"application/json"}}, opts||{}));
    const t = await r.text();
    let j = {};
    try { j = t ? JSON.parse(t) : {}; } catch(_) { throw new Error(t || ("HTTP " + r.status)); }
    if (!r.ok) throw new Error((j && (j.detail || j.error)) || ("HTTP " + r.status));
    return j;
  }

  function renderHtmlCard(title, html){
    return e("div", {className:"llm-card", style:{padding:18}}, [
      e("div", {style:{fontWeight:700, marginBottom:10}}, title),
      e("div", {dangerouslySetInnerHTML:{__html:String(html||"")}})
    ]);
  }

  window.LLM3View = function LLM3View(){
    const [data, setData] = React.useState(null);
    const [err, setErr] = React.useState("");
    const [busy, setBusy] = React.useState("");

    async function load(){
      try{
        const d = await fetchJson("/api/llm3/latest?b=" + Date.now());
        setData(d); setErr("");
      }catch(ex){ setErr(ex.message || String(ex)); }
    }

    React.useEffect(()=>{ load(); }, []);

    async function runPhase(phase){
      try{
        setBusy(phase);
        await fetchJson("/api/llm3/run/" + phase, {method:"POST", body:JSON.stringify({})});
        await load();
      }catch(ex){ setErr(ex.message || String(ex)); }
      finally{ setBusy(""); }
    }

    const doms = (data && data.domains) ? Object.keys(data.domains).sort() : [];
    return e("div", {className:"llm-page", style:{overflowX:"hidden"}}, [
      e("div", {style:{display:"flex", gap:10, alignItems:"center", marginBottom:14}}, [
        e("h2", {style:{margin:0}}, "LLM3 Tactical Ops"),
        e("div", {style:{marginLeft:"auto", display:"flex", gap:10}}, [
          e("button", {onClick:()=>runPhase("phase2"), disabled:!!busy}, busy==="phase2"?"Running phase2...":"Run phase2"),
          e("button", {onClick:()=>runPhase("phase3"), disabled:!!busy}, busy==="phase3"?"Running phase3...":"Run phase3"),
          e("button", {onClick:load}, "Reload")
        ])
      ]),
      err ? e("div", {className:"llm-card", style:{padding:18, marginBottom:12}}, String(err)) : null,
      doms.length ? e("div", {style:{display:"grid", gridTemplateColumns:"repeat(auto-fit, minmax(420px, 1fr))", gap:12}}, doms.map(name=>{
        const dom = data.domains[name] || {};
        const card = (((dom.phase3||{}).files||{})["card.json"] || {}).html || "";
        const findings = (((dom.phase2||{}).files||{})["findings.json"] || {});
        const title = (name === "summary") ? "Summary" : name;
        if (card) return renderHtmlCard(title, card);
        return e("div", {className:"llm-card", style:{padding:18}}, [
          e("div", {style:{fontWeight:700, marginBottom:10}}, title),
          e("pre", {style:{whiteSpace:"pre-wrap", overflow:"auto", maxHeight:320}}, JSON.stringify(findings, null, 2))
        ]);
      })) : e("div", {className:"llm-card", style:{padding:18}}, "No LLM3 state yet")
    ]);
  };
})();
