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

  function Mono(txt){
    return e("span", {
      style:{fontFamily:"ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace"}
    }, String(txt || ""));
  }

  function Pill(txt, kind){
    const bg = (kind==="ok") ? "rgba(46,160,67,.25)" : (kind==="warn") ? "rgba(187,128,9,.25)" : "rgba(248,81,73,.25)";
    const bd = (kind==="ok") ? "rgba(46,160,67,.5)"  : (kind==="warn") ? "rgba(187,128,9,.5)"  : "rgba(248,81,73,.5)";
    return e("span",{style:{
      display:"inline-flex", alignItems:"center", padding:"2px 10px", borderRadius:999,
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
    if (name === "chatter") return "Friendly Activity";
    if (name === "missions") return "Mission Status";
    return String(name || "");
  }

  function niceDomainEyebrow(name){
    if (name === "_summary") return "Latest assessment";
    if (name === "chatter") return "Communications";
    if (name === "missions") return "Operations";
    return "Situation";
  }

  function fixupLatestShape(data){
    try{
      const out = JSON.parse(JSON.stringify(data || {}));
      const doms = out.domains || {};
      Object.keys(doms).forEach(domName=>{
        const dom = doms[domName] || {};
        ["phase1","phase2","phase3"].forEach(ph=>{
          const phObj = dom[ph];
          if (!phObj || !phObj.files) return;
          if (phObj.files["latest.json"] && !phObj.files.latest_json) phObj.files.latest_json = phObj.files["latest.json"];
          if (phObj.files["trace.json"] && !phObj.files.trace_json) phObj.files.trace_json = phObj.files["trace.json"];
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

    const p1q = (((p1||{}).files||{}).latest_json || null);
    const qcount = (p1q && p1q.queries && Array.isArray(p1q.queries)) ? p1q.queries.length : null;
    const latestDir = (p1 && p1.dir) ? String(p1.dir) : "";

    const p2find = (((p2||{}).files||{}).findings_json || null);
    const p2trace = (((p2||{}).files||{}).trace_json || null);
    const p3card = (((p3||{}).files||{}).card_json || null);
    const p3trace = (((p3||{}).files||{}).trace_json || null);

    const runId =
      (p3card && p3card.run_id) ||
      (p3trace && p3trace.run_id) ||
      (p2trace && p2trace.run_id) ||
      null;

    return { p1, p2, p3, p2find, p2trace, p3card, p3trace, qcount, latestDir, runId };
  }

  function stripHtmlTags(s){
    return String(s || "")
      .replace(/<script[\s\S]*?<\/script>/gi, "")
      .replace(/<style[\s\S]*?<\/style>/gi, "")
      .replace(/<[^>]+>/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  }

  function escapeHtml(s){
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function normalizeOperationalText(s){
    let t = String(s || "").trim();
    if (!t) return "";

    t = t.replace(/^Phase2 findings$/i, "Latest assessment");
    t = t.replace(/\bphase ?2 findings\b/gi, "latest assessment");
    t = t.replace(/\bwas seeded in phase1\b/gi, "was recorded");
    t = t.replace(/\bwas seeded in initial ingest\b/gi, "was recorded");
    t = t.replace(/\bseeded in phase1\b/gi, "recorded");
    t = t.replace(/\bseeded in initial ingest\b/gi, "recorded");
    t = t.replace(/\bphase1\b/gi, "");
    t = t.replace(/\bphase2\b/gi, "");
    t = t.replace(/\binitial ingest\b/gi, "");
    t = t.replace(/\s{2,}/g, " ").trim();
    t = t.replace(/\s+([,.;:!?])/g, "$1").trim();

    return t;
  }

  function looksLikeTimestamp(s){
    const t = String(s || "").trim();
    if (!t) return false;
    return /\b\d{4}-\d{2}-\d{2}\b/.test(t) || /\b\d{2}:\d{2}\b/.test(t);
  }

  function uniqueNonEmpty(arr){
    const out = [];
    const seen = {};
    (arr || []).forEach(v=>{
      const s = String(v || "").trim();
      if (!s) return;
      if (seen[s]) return;
      seen[s] = true;
      out.push(s);
    });
    return out;
  }

  function extractTextFromP3Card(s){
    const html = s && s.p3card && typeof s.p3card.html === "string" ? s.p3card.html : "";
    return normalizeOperationalText(stripHtmlTags(html));
  }

  function deriveOperationalModel(name, s){
    const p2 = s.p2find || {};
    const p3Text = extractTextFromP3Card(s);

    let important = normalizeOperationalText(p2.important || "");
    let newest = normalizeOperationalText(p2.newest || "");
    let details = normalizeOperationalText(p2.details || "");

    if (!important && p3Text) important = p3Text;

    const title = niceDomainName(name);
    const eyebrow = niceDomainEyebrow(name);

    let timestamp = "";
    if (looksLikeTimestamp(newest)) timestamp = newest;

    let headline = important || details || newest || "No current assessment";
    let summary = "";

    if (name === "_summary"){
      summary = details && details !== headline ? details : "";
      if (!summary && newest && newest !== headline && !looksLikeTimestamp(newest)) summary = newest;
      return {
        title: title,
        eyebrow: eyebrow,
        headline: headline,
        timestamp: timestamp,
        summary: summary,
        bullets: []
      };
    }

    const bullets = uniqueNonEmpty([
      (newest && !looksLikeTimestamp(newest) && newest !== headline) ? newest : "",
      (details && details !== headline && details !== newest) ? details : ""
    ]).slice(0, 3);

    if (!summary && looksLikeTimestamp(newest)) summary = newest;
    if (!summary && details && details !== headline) summary = details;

    return {
      title: title,
      eyebrow: eyebrow,
      headline: headline,
      timestamp: timestamp,
      summary: summary,
      bullets: bullets
    };
  }

  function renderOperationalCard(name, s){
    const m = deriveOperationalModel(name, s);

    const summaryEl = m.summary
      ? e("div", {style:{opacity:.92, fontSize:15, lineHeight:"22px", marginBottom:m.bullets.length ? 10 : 0}}, m.summary)
      : null;

    const bulletsEl = (m.bullets && m.bullets.length)
      ? e("ul", {
          style:{
            margin:"8px 0 0 18px",
            padding:0,
            opacity:.92,
            lineHeight:"22px"
          }
        }, m.bullets.map((b, i)=>e("li",{key:i, style:{marginBottom:2}}, b)))
      : null;

    return e("div", {style:{marginTop:2}}, [
      e("div", {
        style:{
          fontSize:12,
          letterSpacing:".08em",
          textTransform:"uppercase",
          opacity:.62,
          fontWeight:700,
          marginBottom:12
        }
      }, m.eyebrow),
      e("div", {
        style:{
          fontSize:name === "_summary" ? 33 : 30,
          lineHeight:name === "_summary" ? "38px" : "34px",
          fontWeight:800,
          marginBottom:m.timestamp ? 8 : 12
        }
      }, m.headline),
      m.timestamp ? e("div", {
        style:{
          opacity:.72,
          fontSize:13,
          marginBottom:(summaryEl || bulletsEl) ? 12 : 0
        }
      }, m.timestamp) : null,
      summaryEl,
      bulletsEl
    ]);
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

  function CardShell(title, body, extraStyle){
    return e("div",{
      className:"llm-card",
      style:Object.assign({
        border:"1px solid rgba(255,255,255,.06)",
        borderRadius:18,
        padding:"18px 18px 16px 18px",
        background:"linear-gradient(90deg, rgba(255,255,255,.02), rgba(255,255,255,.01))",
        boxShadow:"0 0 0 1px rgba(0,0,0,.08) inset"
      }, extraStyle || {})
    },[
      e("div",{style:{fontSize:15,fontWeight:700,opacity:.96,marginBottom:8}}, title),
      body ? e("div",null, body) : null
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
      const t = setInterval(load, 5000);
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
        CardShell("Load error", e("pre",{style:{opacity:.9}}, String(err)))
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
      return CardShell("Summary", body, {marginBottom:12});
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
      return CardShell(niceDomainName(name), body, {minHeight: showDebug ? "auto" : 150});
    }));

    const debugFooter = showDebug ? CardShell(
      "Debug",
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
