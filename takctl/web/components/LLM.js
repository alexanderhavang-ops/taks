/* global React */
(function () {
  var h = (window.h || React.createElement); window.h = h;
  const e = h;

  // Prefer shared helper, but always provide a safe fallback.
  const _sharedFetchJson = (window.TaksApi && window.TaksApi.fetchJson) || window.fetchJson;
  async function fetchJson(url){
    if (typeof _sharedFetchJson === "function") return await _sharedFetchJson(url);
    const r = await fetch(url, { credentials: "same-origin" });
    const t = await r.text();
    if (!r.ok) throw new Error("HTTP " + r.status + " loading " + url + ": " + t.slice(0, 400));
    try { return JSON.parse(t); } catch { throw new Error("Non-JSON from " + url + ": " + t.slice(0, 400)); }
  }

  function Mono(txt){
    return e("span", {
      style:{fontFamily:"ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace"}
    }, String(txt || ""));
  }

  function Pill(txt, kind){
    const bg = (kind==="ok") ? "rgba(46,160,67,.25)" : (kind==="warn") ? "rgba(187,128,9,.25)" : "rgba(248,81,73,.25)";
    const bd = (kind==="ok") ? "rgba(46,160,67,.5)"  : (kind==="warn") ? "rgba(187,128,9,.5)"  : "rgba(248,81,73,.5)";
    return e("span",{style:{
      display:"inline-flex",alignItems:"center",padding:"2px 10px",borderRadius:999,
      border:"1px solid "+bd, background:bg, fontSize:12, lineHeight:"18px"
    }}, String(txt));
  }

  function Json(obj, maxH){
    return e("div",{
      className:"llm-json",
      style:{
        maxHeight:maxH||520,
        overflow:"auto",
        maxWidth:"100%",
        fontFamily:"ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, \"Liberation Mono\", \"Courier New\", monospace",
        fontSize:12,
        lineHeight:"16px",
        whiteSpace:"pre-wrap",
        overflowWrap:"anywhere",
        wordBreak:"break-word"
      }
    }, JSON.stringify(obj, null, 2));
  }

  function domainBadge(phaseObj){
    if (!phaseObj) return Pill("missing","bad");
    if (phaseObj.ok === true) return Pill("ok","ok");
    if (phaseObj.ok === false) return Pill("err","bad");
    return Pill("—","warn");
  }

  function niceDomainName(name){
    if (name === "_summary") return "Summary";
    return String(name || "");
  }

  function fixupLatestShape(data){
    try{
      const out = JSON.parse(JSON.stringify(data||{}));
      const doms = out.domains || {};
      Object.keys(doms).forEach(domName=>{
        const dom = doms[domName] || {};
        ["phase1","phase2","phase3"].forEach(ph=>{
          const phObj = dom[ph];
          if (!phObj || !phObj.files) return;
          if (phObj.files["latest.json"] && !phObj.files.latest_json) phObj.files.latest_json = phObj.files["latest.json"];
          if (phObj.files["trace.json"]  && !phObj.files.trace_json)  phObj.files.trace_json  = phObj.files["trace.json"];
          if (phObj.files["findings.json"] && !phObj.files.findings_json) phObj.files.findings_json = phObj.files["findings.json"];
          if (phObj.files["card.json"] && !phObj.files.card_json) phObj.files.card_json = phObj.files["card.json"];
        });
      });
      return out;
    }catch{
      return data;
    }
  }

  function domPhaseSummary(dom){
    const p1 = dom && dom.phase1 ? dom.phase1 : null;
    const p2 = dom && dom.phase2 ? dom.phase2 : null;
    const p3 = dom && dom.phase3 ? dom.phase3 : null;

    const p1q = (((p1||{}).files||{}).latest_json||null);
    const qcount = (p1q && p1q.queries && Array.isArray(p1q.queries)) ? p1q.queries.length : null;
    const latestDir = (p1 && p1.dir) ? String(p1.dir) : "";

    const p2find = (((p2||{}).files||{}).findings_json||null);
    const p2trace = (((p2||{}).files||{}).trace_json||null);
    const p3card = (((p3||{}).files||{}).card_json||null);
    const p3trace = (((p3||{}).files||{}).trace_json||null);

    const runId =
      (p3card && p3card.run_id) ||
      (p3trace && p3trace.run_id) ||
      (p2trace && p2trace.run_id) ||
      null;

    return { p1, p2, p3, p2find, p2trace, p3card, p3trace, qcount, latestDir, runId };
  }

  function HtmlCard(htmlStr){
    return e("div",{
      style:{
        marginTop:12,
        borderRadius:14,
        overflow:"hidden"
      },
      dangerouslySetInnerHTML:{__html: String(htmlStr || "")}
    });
  }

  function CardShell(title, subtitle, body, extraStyle){
    return e("div",{
      className:"llm-card",
      style:Object.assign({
        border:"1px solid rgba(255,255,255,.06)",
        borderRadius:16,
        padding:"14px 16px",
        background:"linear-gradient(90deg, rgba(255,255,255,.02), rgba(255,255,255,.01))",
        boxShadow:"0 0 0 1px rgba(0,0,0,.08) inset"
      }, extraStyle || {})
    },[
      e("div",{style:{display:"flex",alignItems:"center",justifyContent:"space-between",gap:12}},[
        e("div",null,[
          e("div",{style:{fontSize:18,fontWeight:700,marginBottom: subtitle ? 6 : 0}}, title),
          subtitle ? e("div",{style:{opacity:.9,fontSize:12}}, subtitle) : null
        ])
      ]),
      body ? e("div",{style:{marginTop:10}}, body) : null
    ]);
  }

  function phaseLabelToHuman(s){
    const p2 = s && s.p2find ? s.p2find : {};
    if (!p2 || !p2.important) return "";
    const important = String(p2.important || "");
    const newest = String(p2.newest || "");
    const details = String(p2.details || "");
    if (important || newest || details) return "Latest assessment";
    return "";
  }

  function cleanPhaseWords(text){
    let s = String(text || "");
    s = s.replace(/\b[Pp]hase\s*1\b/g, "initial ingest");
    s = s.replace(/\b[Pp]hase\s*2\b/g, "analysis");
    s = s.replace(/\b[Pp]hase\s*3\b/g, "card render");
    return s;
  }

  function renderOperationalFallback(name, s){
    const p2 = s.p2find || {};
    const important = p2.important ? cleanPhaseWords(String(p2.important)) : "";
    const newest = p2.newest ? cleanPhaseWords(String(p2.newest)) : "";
    const details = p2.details ? cleanPhaseWords(String(p2.details)) : "";

    const bits = [];
    const heading = (name === "_summary") ? phaseLabelToHuman(s) : "";
    if (heading) bits.push(e("div",{style:{fontSize:16,fontWeight:700,marginBottom:10}}, heading));
    if (important) bits.push(e("div",{style:{fontSize:16,fontWeight:700,marginBottom:10}}, important));
    if (newest && newest !== important) bits.push(e("div",{style:{opacity:.95,marginBottom:10}}, newest));
    if (details && details !== important && details !== newest) bits.push(e("div",{style:{opacity:.9}}, details));

    if (bits.length) return e("div",{style:{marginTop:12}}, bits);

    return e("div",{style:{marginTop:12,opacity:.75,fontSize:13}}, "No card available yet.");
  }

  function renderOperationalCard(name, s){
    const p3html = s.p3card && typeof s.p3card.html === "string" ? s.p3card.html : "";

    if (p3html && p3html.trim()){
      if (name === "_summary"){
        const p2 = s.p2find || {};
        const important = p2.important ? cleanPhaseWords(String(p2.important)) : "";
        const newest = p2.newest ? cleanPhaseWords(String(p2.newest)) : "";
        const details = p2.details ? cleanPhaseWords(String(p2.details)) : "";

        return e("div",{style:{marginTop:12}},[
          e("div",{style:{fontSize:16,fontWeight:700,marginBottom:10}}, "Latest assessment"),
          important ? e("div",{style:{fontSize:16,fontWeight:700,marginBottom:10}}, important) : null,
          newest && newest !== important ? e("div",{style:{opacity:.95,marginBottom:10}}, newest) : null,
          details && details !== important && details !== newest ? e("div",{style:{opacity:.9}}, details) : null
        ]);
      }
      return HtmlCard(p3html);
    }

    return renderOperationalFallback(name, s);
  }

  function renderDebugSection(s){
    const p1 = s.p1 || {};
    const p2 = s.p2 || {};
    const p3 = s.p3 || {};

    const p3run = ((s.runId && (s.p3||{}).dir)
      ? String((s.p3||{}).dir).replace(/\/latest\/[^/]+\/phase3$/, "/runs/" + s.runId + "/" + (((s.p3||{}).dir || "").split("/").slice(-2,-1)[0] || "") + "/phase3")
      : null);

    return e("div",null,[
      e("div",{style:{display:"flex",gap:10,flexWrap:"wrap",alignItems:"center",marginBottom:10}},[
        e("span",null,"p1 "), domainBadge(s.p1),
        e("span",null,"p2 "), domainBadge(s.p2),
        e("span",null,"p3 "), domainBadge(s.p3),
        s.qcount!=null ? e("span",{style:{opacity:.9}}, "phase1 queries: " + String(s.qcount)) : null
      ]),

      e("div",{style:{opacity:.8,fontSize:12,marginBottom:10,overflowWrap:"anywhere"}}, "latest dir: " + (s.latestDir || "—")),

      e("div",{style:{opacity:.95,margin:"10px 0 6px"}}, "Debug (latest/*)"),
      (p1.files && p1.files.latest_json) ? e("details",null,[
        e("summary",null,"phase1/latest.json"),
        Json(p1.files.latest_json, 520)
      ]) : null,
      (p1.files && p1.files.trace_json) ? e("details",null,[
        e("summary",null,"phase1/trace.json"),
        Json(p1.files.trace_json, 520)
      ]) : null,
      (p2.files && p2.files.findings_json) ? e("details",null,[
        e("summary",null,"phase2/findings.json"),
        Json(p2.files.findings_json, 520)
      ]) : null,
      (p2.files && p2.files.trace_json) ? e("details",null,[
        e("summary",null,"phase2/trace.json"),
        Json(p2.files.trace_json, 520)
      ]) : null,
      (p3.files && p3.files.card_json) ? e("details",null,[
        e("summary",null,"phase3/card.json"),
        Json(p3.files.card_json, 520)
      ]) : null,
      (p3.files && p3.files.trace_json) ? e("details",null,[
        e("summary",null,"phase3/trace.json"),
        Json(p3.files.trace_json, 520)
      ]) : null,

      e("div",{style:{opacity:.95,margin:"10px 0 6px"}}, "Debug (runs/<run_id>/...)"),
      s.runId ? e("div",{style:{opacity:.8,fontSize:12,marginBottom:8}}, ["run_id ", Mono(s.runId)]) : null,
      (s.runId && p3run) ? e("div",{style:{opacity:.8,fontSize:12,marginBottom:8,overflowWrap:"anywhere"}}, p3run) : null,
      (p3.files && p3.files.trace_json && p3.files.trace_json.files) ? e("details",null,[
        e("summary",null,"phase3 run files (prompt/response/cleaned/request/http)"),
        Json(p3.files.trace_json.files, 520)
      ]) : null
    ]);
  }

  window.LLMView = function TacticalOperationsView() {
    const [data, setData] = React.useState(null);
    const [err, setErr] = React.useState(null);
    const [showDebug, setShowDebug] = React.useState(false);

    async function load(){
      try{
        const bump = Date.now();
        const d = await fetchJson("/api/llm2/latest?b=" + bump);
        setData(fixupLatestShape(d));
        setErr(null);
      }catch(ex){
        setErr(ex && (ex.message || String(ex)));
      }
    }

    React.useEffect(()=>{
      load();
      const t=setInterval(load, 5000);
      return ()=>clearInterval(t);
    },[]);

    const header = e("div",{style:{display:"flex",alignItems:"center",gap:12,marginBottom:14}},[
      e("h2",{style:{margin:"0 10px 0 0"}}, "Tactical Operations"),
      e("div",{style:{marginLeft:"auto",display:"flex",gap:10,alignItems:"center"}},[
        e("button",{onClick:load}, "Reload"),
        e("button",{onClick:()=>setShowDebug(!showDebug)}, showDebug ? "Operative view" : "Debug view")
      ])
    ]);

    if (err){
      return e("div",{className:"llm-page"},[
        header,
        CardShell("Load error", "Failed to load /api/llm2/latest", e("pre",{style:{opacity:.9}}, String(err)))
      ]);
    }

    const doms = (data && data.domains) ? data.domains : {};
    const domNames = Object.keys(doms).sort((a,b)=>{
      if (a === "_summary") return -1;
      if (b === "_summary") return 1;
      return a.localeCompare(b);
    });

    const summaryName = domNames.find(n => n === "_summary") || null;
    const otherNames = domNames.filter(n => n !== "_summary");

    const summaryCard = summaryName ? (function(){
      const s = domPhaseSummary(doms[summaryName] || {});
      const body = showDebug ? renderDebugSection(s) : renderOperationalCard(summaryName, s);
      return CardShell("Summary", null, body, {marginBottom:12});
    })() : null;

    const othersGrid = e("div",{
      style:{
        display:"grid",
        gridTemplateColumns:"repeat(auto-fit, minmax(420px, 1fr))",
        gap:"12px"
      }
    }, otherNames.map(name=>{
      const s = domPhaseSummary(doms[name] || {});
      const body = showDebug ? renderDebugSection(s) : renderOperationalCard(name, s);
      return CardShell(niceDomainName(name), null, body);
    }));

    const debugFooter = showDebug ? CardShell(
      "Debug",
      null,
      e("div",null,[
        e("details",null,[ e("summary",null,"Full /api/llm2/latest (raw)"), Json(data || {missing:true}, 520) ])
      ]),
      {marginTop:12}
    ) : null;

    return e("div",{className:"llm-page", style:{overflowX:"hidden"}},[
      header,
      summaryCard,
      othersGrid,
      debugFooter
    ]);
  };
})();
