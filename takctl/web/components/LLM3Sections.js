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
      return u.searchParams.get("section_detail") || "";
    }catch(_){ return ""; }
  }

  function setDetailInLocation(name){
    try{
      const u = new URL(window.location.href);
      if (name) u.searchParams.set("section_detail", name);
      else u.searchParams.delete("section_detail");
      window.history.replaceState({}, "", u.toString());
    }catch(_){ }
  }

  function getSectionFromLocation(){
    try{
      const u = new URL(window.location.href);
      return u.searchParams.get("section") || "S1";
    }catch(_){ return "S1"; }
  }

  function setSectionInLocation(name){
    try{
      const u = new URL(window.location.href);
      if (name) u.searchParams.set("section", name);
      else u.searchParams.delete("section");
      window.history.replaceState({}, "", u.toString());
    }catch(_){ }
  }

  function renderHtml(html){
    return e("div", {dangerouslySetInnerHTML:{__html:String(html||"")}});
  }

  function cardShell(title, subtitle, body, onClick){
    return e("div", {
      className:"llm-card",
      onClick:onClick || undefined,
      title:onClick ? "Open detail page" : undefined,
      style:{ padding:18, cursor:onClick ? "pointer" : "default" }
    }, [
      subtitle ? e("div", {className:"muted", style:{marginBottom:6, fontSize:12}}, subtitle) : null,
      e("div", {style:{fontWeight:700, marginBottom:10}}, title),
      body
    ]);
  }

  function niceSectionLabel(section){
    const map = {
      S1: "S1/J1 Personal",
      S2: "S2/J2 Underrättelser",
      S3: "S3/J3 Operationer",
      S6: "S6/J6 Samband"
    };
    return map[String(section||"").toUpperCase()] || String(section||"");
  }

  function domainTitle(domName, dom){
    const meta = (dom && dom.meta) || {};
    return String(meta.card_title || domName || "");
  }

  function sectionDomains(data, section){
    const all = (data && data.domains) ? data.domains : {};
    return Object.keys(all).filter(name => {
      const meta = (all[name] || {}).meta || {};
      return String(meta.section || "").toUpperCase() === String(section || "").toUpperCase();
    }).sort((a,b)=>domainTitle(a, all[a]).localeCompare(domainTitle(b, all[b]), 'sv'));
  }

  function sectionSummaryText(data, section){
    const names = sectionDomains(data, section);
    const all = (data && data.domains) ? data.domains : {};
    for (const name of names){
      const dom = all[name] || {};
      const findings = (((dom.phase2||{}).files||{})["findings.json"] || {});
      const important = String(findings.important || "").trim();
      if (important) return important;
    }
    return "";
  }

  function SectionButton(props){
    const active = props.active;
    return e("button", {
      type:"button",
      className: active ? "tab tab-active" : "tab",
      onClick: props.onClick
    }, props.label);
  }

  window.LLM3SectionsView = function LLM3SectionsView(){
    const [data, setData] = React.useState(null);
    const [err, setErr] = React.useState("");
    const [busy, setBusy] = React.useState("");
    const [section, setSection] = React.useState(getSectionFromLocation());
    const [detailName, setDetailName] = React.useState(getDetailFromLocation());

    async function load(){
      try{
        const d = await fetchJson("/api/llm3/latest?b=" + Date.now());
        setData(d); setErr("");
      }catch(ex){ setErr(ex.message || String(ex)); }
    }

    React.useEffect(()=>{ load(); }, []);
    React.useEffect(()=>{
      const onPop = ()=>{ setSection(getSectionFromLocation()); setDetailName(getDetailFromLocation()); };
      window.addEventListener("popstate", onPop);
      return ()=>window.removeEventListener("popstate", onPop);
    }, []);

    function openSection(name){
      setSection(name);
      setDetailName("");
      setSectionInLocation(name);
      setDetailInLocation("");
    }

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
      }catch(ex){ setErr(ex.message || String(ex)); }
      finally{ setBusy(""); }
    }

    const sections = ["S1", "S2", "S3", "S6"];
    const names = sectionDomains(data, section);
    const all = (data && data.domains) ? data.domains : {};

    if (detailName && all[detailName]){
      const dom = all[detailName] || {};
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
          e("h2", {style:{margin:0}}, "AI by Section"),
          e("div", {style:{marginLeft:"auto", display:"flex", gap:10}}, [
            e("button", {onClick:closeDetail}, "Back to section"),
            e("button", {onClick:load}, "Reload")
          ])
        ]),
        err ? e("div", {className:"llm-card", style:{padding:18, marginBottom:12}}, String(err)) : null,
        cardShell(domainTitle(detailName, dom), niceSectionLabel(((dom.meta||{}).section)||section), body, null)
      ]);
    }

    return e("div", {className:"llm-page", style:{overflowX:"hidden"}}, [
      e("div", {style:{display:"flex", gap:10, alignItems:"center", marginBottom:14}}, [
        e("h2", {style:{margin:0}}, "AI by Section"),
        e("div", {style:{marginLeft:"auto", display:"flex", gap:10}}, [
          e("button", {onClick:()=>runPhase("phase2"), disabled:!!busy}, busy==="phase2"?"Running phase2...":"Run phase2"),
          e("button", {onClick:()=>runPhase("phase3"), disabled:!!busy}, busy==="phase3"?"Running phase3...":"Run phase3"),
          e("button", {onClick:load}, "Reload")
        ])
      ]),
      e("div", {style:{display:"flex", gap:8, marginBottom:12, flexWrap:"wrap"}}, sections.map(sec =>
        e(SectionButton, {key:sec, active: sec===section, onClick:()=>openSection(sec), label:niceSectionLabel(sec)})
      )),
      err ? e("div", {className:"llm-card", style:{padding:18, marginBottom:12}}, String(err)) : null,
      e("div", {className:"llm-card", style:{padding:18, marginBottom:12}}, [
        e("div", {style:{fontWeight:700, marginBottom:8}}, niceSectionLabel(section)),
        e("div", {className:"muted"}, sectionSummaryText(data, section) || "No current section summary yet.")
      ]),
      names.length ? e("div", {style:{display:"grid", gridTemplateColumns:"repeat(auto-fit, minmax(420px, 1fr))", gap:12}}, names.map(name=>{
        const dom = all[name] || {};
        const files3 = ((dom.phase3 || {}).files || {});
        const card = ((files3["card.json"] || {}).html || "");
        const findings = (((dom.phase2||{}).files||{})["findings.json"] || {});
        const title = domainTitle(name, dom) || name;
        if (card){
          return cardShell(title, null, renderHtml(card), ()=>openDetail(name));
        }
        return cardShell(title, null,
          e("pre", {style:{whiteSpace:"pre-wrap", overflow:"auto", maxHeight:320}}, JSON.stringify(findings, null, 2)),
          ()=>openDetail(name)
        );
      })) : e("div", {className:"llm-card", style:{padding:18}}, "No section state yet")
    ]);
  };
})();
