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

  function getDetailFromLocation(){
    try{
      const u = new URL(window.location.href);
      return u.searchParams.get("detail") || "";
    }catch(_){
      return "";
    }
  }

  function setDetailInLocation(name){
    try{
      const u = new URL(window.location.href);
      if (name) u.searchParams.set("detail", name);
      else u.searchParams.delete("detail");
      window.history.replaceState({}, "", u.toString());
    }catch(_){}
  }

  function niceTitle(name){
    return name === "summary" ? "Summary" : name;
  }

  function isSectionDomain(dom){
    const meta = (dom && dom.meta) || {};
    return !!String(meta.section || "").trim();
  }

  function cardShell(title, body, onClick){
    return e("div", {
      className:"llm-card",
      onClick:onClick || undefined,
      title:onClick ? "Open detail page" : undefined,
      style:{
        padding:18,
        cursor:onClick ? "pointer" : "default"
      }
    }, [
      e("div", {style:{fontWeight:700, marginBottom:10}}, title),
      body
    ]);
  }

  function renderHtml(html){
    return e("div", {dangerouslySetInnerHTML:{__html:String(html||"")}});
  }

  window.LLM3View = function LLM3View(){
    const [data, setData] = React.useState(null);
    const [err, setErr] = React.useState("");
    const [busy, setBusy] = React.useState("");
    const [detailName, setDetailName] = React.useState(getDetailFromLocation());

    async function load(){
      try{
        const d = await fetchJson("/api/llm3/latest?b=" + Date.now());
        setData(d);
        setErr("");
      }catch(ex){
        setErr(ex.message || String(ex));
      }
    }

    React.useEffect(()=>{ load(); }, []);
    React.useEffect(()=>{
      const onPop = ()=>setDetailName(getDetailFromLocation());
      window.addEventListener("popstate", onPop);
      return ()=>window.removeEventListener("popstate", onPop);
    }, []);

    function openDetail(name){
      setDetailName(name || "");
      setDetailInLocation(name || "");
    }

    function closeDetail(){
      setDetailName("");
      setDetailInLocation("");
    }

    async function runPhase(phase){
      try{
        setBusy(phase);
        await fetchJson("/api/llm3/run/" + phase, {method:"POST", body:JSON.stringify({})});
        await load();
      }catch(ex){
        setErr(ex.message || String(ex));
      }finally{
        setBusy("");
      }
    }

    const allDomains = (data && data.domains) ? data.domains : {};
    const doms = Object.keys(allDomains)
      .filter(name => !isSectionDomain(allDomains[name]))
      .sort();

    if (detailName && allDomains[detailName] && !isSectionDomain(allDomains[detailName])){
      const dom = allDomains[detailName] || {};
      const files3 = ((dom.phase3 || {}).files || {});
      const detailHtml = ((files3["detail.json"] || {}).html || "");
      const cardHtml = ((files3["card.json"] || {}).html || "");
      const findings = (((dom.phase2 || {}).files || {})["findings.json"] || {});

      let body = null;
      if (detailHtml) body = renderHtml(detailHtml);
      else if (cardHtml) body = renderHtml(cardHtml);
      else body = e("pre", {style:{whiteSpace:"pre-wrap", overflow:"auto"}}, JSON.stringify(findings, null, 2));

      return e("div", {className:"llm-page", style:{overflowX:"hidden"}}, [
        e("div", {style:{display:"flex", gap:10, alignItems:"center", marginBottom:14}}, [
          e("h2", {style:{margin:0}}, "LLM3 Tactical Ops"),
          e("div", {style:{marginLeft:"auto", display:"flex", gap:10}}, [
            e("button", {onClick:closeDetail}, "Back to overview"),
            e("button", {onClick:load}, "Reload")
          ])
        ]),
        err ? e("div", {className:"llm-card", style:{padding:18, marginBottom:12}}, String(err)) : null,
        cardShell(niceTitle(detailName), body, null)
      ]);
    }

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
        const dom = allDomains[name] || {};
        const files3 = ((dom.phase3 || {}).files || {});
        const card = ((files3["card.json"] || {}).html || "");
        const findings = (((dom.phase2||{}).files||{})["findings.json"] || {});
        const title = niceTitle(name);

        if (card){
          return cardShell(title, renderHtml(card), ()=>openDetail(name));
        }

        return cardShell(
          title,
          e("pre", {style:{whiteSpace:"pre-wrap", overflow:"auto", maxHeight:320}}, JSON.stringify(findings, null, 2)),
          ()=>openDetail(name)
        );
      })) : e("div", {className:"llm-card", style:{padding:18}}, "No LLM3 state yet")
    ]);
  };
})();
