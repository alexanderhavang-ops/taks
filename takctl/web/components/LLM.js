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

  function Mono(txt){ return e("span",{style:{fontFamily:"ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace"}}, String(txt||"")); }
  function Pill(txt, kind){
    const bg = (kind==="ok") ? "rgba(46,160,67,.25)" : (kind==="warn") ? "rgba(187,128,9,.25)" : "rgba(248,81,73,.25)";
    const bd = (kind==="ok") ? "rgba(46,160,67,.5)"  : (kind==="warn") ? "rgba(187,128,9,.5)"  : "rgba(248,81,73,.5)";
    return e("span",{style:{
      display:"inline-flex",alignItems:"center",padding:"2px 10px",borderRadius:999,
      border:"1px solid "+bd, background:bg, fontSize:12, lineHeight:"18px"
    }}, String(txt));
  }

  function Card(title, subtitle, body){
    return e("div",{className:"llm-card"},[
      e("div",{className:"llm-card-head"},[
        e("div",{className:"llm-card-title"}, title),
        subtitle ? e("div",{className:"llm-card-subtitle"}, subtitle) : null
      ]),
      body ? e("div",{className:"llm-payload"}, body) : null
    ]);
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

  function TextBlock(txt, maxH){
    return e("pre",{
      style:{
        margin:0,
        maxHeight:maxH||520,
        overflow:"auto",
        maxWidth:"100%",
        fontFamily:"ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, \"Liberation Mono\", \"Courier New\", monospace",
        fontSize:12,
        lineHeight:"16px",
        whiteSpace:"pre-wrap",
        overflowWrap:"anywhere",
        wordBreak:"break-word",
        opacity:.95
      }
    }, String(txt||""));
  }

  function domainBadge(phaseObj){
    if (!phaseObj) return Pill("missing","bad");
    if (phaseObj.ok === true) return Pill("ok","ok");
    if (phaseObj.ok === false) return Pill("err","bad");
    return Pill("—","warn");
  }

  function domPhaseSummary(dom){
    const p1 = dom && dom.phase1 ? dom.phase1 : null;
    const p2 = dom && dom.phase2 ? dom.phase2 : null;
    const p3 = dom && dom.phase3 ? dom.phase3 : null;

    const p1q = (((p1||{}).files||{}).latest_json||null);
    const qcount = (p1q && p1q.queries && Array.isArray(p1q.queries)) ? p1q.queries.length : null;

    const elapsed =
      (p1q && p1q.queries && p1q.queries[0] && typeof p1q.queries[0].elapsed_ms === "number")
        ? ("elapsed " + String(p1q.queries[0].elapsed_ms) + "ms (first query)")
        : null;

    const latestDir = (p1 && p1.dir) ? String(p1.dir) : "";
    return { p1, p2, p3, qcount, elapsed, latestDir };
  }

  // Normalize llm2_debug shape (api/llm2/latest returns files["latest.json"] etc)
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

  function renderCardHtml(htmlStr){
    return e("div", {
      className:"llm-card-render",
      style:{marginTop:8},
      dangerouslySetInnerHTML:{__html: String(htmlStr||"")}
    });
  }

  window.LLMView = function TacticalOperationsView() {
    const [data, setData] = React.useState(null);
    const [err, setErr] = React.useState(null);
    const [showDebug, setShowDebug] = React.useState(false);

    async function load(){
      try{
        const bump = Date.now();
        const d = await fetchJson("/api/llm2/latest?b="+bump);
        setData(fixupLatestShape(d));
        setErr(null);
      }catch(ex){
        setErr(ex && (ex.message || String(ex)));
      }
    }
    React.useEffect(()=>{ load(); const t=setInterval(load, 5000); return ()=>clearInterval(t); },[]);

    const topOk = data && data.ok===true;
    const topStatus = topOk ? Pill("OK","ok") : Pill("ERR","bad");
    const phase = (data && data.run && data.run.phase) ? String(data.run.phase) : "—";
    const runId = (data && data.run && (data.run.run_id || data.run.rid)) ? String(data.run.run_id || data.run.rid) : "—";

    const header = e("div",{style:{display:"flex",alignItems:"center",gap:12,marginBottom:14}},[
      e("h2",{style:{margin:"0 10px 0 0"}}, "Tactical Operations"),
      topStatus,
      e("div",{style:{opacity:.9,fontSize:12}},["phase ", Mono(phase)]),
      e("div",{style:{marginLeft:"auto",display:"flex",gap:10,alignItems:"center"}},[
        e("button",{onClick:load}, "Reload"),
        e("button",{onClick:()=>setShowDebug(!showDebug)}, showDebug ? "Hide debug" : "Debug view")
      ])
    ]);

    if (err){
      return e("div",{className:"llm-page"},[
        header,
        Card("Load error", "Failed to load /api/llm2/latest", e("pre",{style:{opacity:.9}}, String(err)))
      ]);
    }

    const doms = (data && data.domains) ? data.domains : {};
    const domNames = Object.keys(doms).sort();

    const grid = e("div",{className:"llm-content"}, domNames.map(name=>{
      const dom = doms[name] || {};
      const s = domPhaseSummary(dom);

      const subtitle = e("div",{style:{display:"flex",gap:10,flexWrap:"wrap",alignItems:"center"}},[
        e("span",null,"p1 "), domainBadge(s.p1),
        e("span",null,"p2 "), domainBadge(s.p2),
        e("span",null,"p3 "), domainBadge(s.p3),
        s.qcount!=null ? e("span",{style:{opacity:.9}}, "phase1 queries: "+String(s.qcount)) : null,
        s.elapsed ? e("span",{style:{opacity:.9}}, s.elapsed) : null,
      ]);

      // Operative view: render phase3 card if present.
      const p3card = (((s.p3||{}).files||{}).card_json||null);
      const cardHtml = (p3card && typeof p3card.html === "string") ? p3card.html : "";
      const operativeBody = e("div",null,[
        cardHtml
          ? renderCardHtml(cardHtml)
          : e("div",{style:{opacity:.85,fontSize:13,marginTop:8}},[
              e("div",null,"No card available yet."),
              e("div",null,["run_id ", Mono(runId)])
            ])
      ]);

      if (!showDebug){
        return Card(name, subtitle, operativeBody);
      }

      // Debug view: phase payloads + run file excerpts (if present).
      const p1 = s.p1 || {};
      const p2 = s.p2 || {};
      const p3 = s.p3 || {};
      const runFiles = (dom && dom.run_files) ? dom.run_files : {};

      const body = e("div",null,[
        e("div",{style:{opacity:.9,fontSize:12,marginBottom:6, overflowWrap:"anywhere"}}, "latest dir: " + (s.latestDir || "—")),

        e("div",{style:{opacity:.9,margin:"10px 0 6px"}}, "Debug (latest/*)"),
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

        e("div",{style:{opacity:.9,margin:"10px 0 6px"}}, "Debug (runs/<run_id>/…)"),

        (runFiles && runFiles.phase1 && runFiles.phase1.ok) ? e("details",null,[
          e("summary",null,"phase1 run files (prompt/response/cleaned/request/http)"),
          runFiles.phase1.prompt_txt ? e("details",null,[ e("summary",null,"prompt.txt"), TextBlock(runFiles.phase1.prompt_txt, 520) ]) : null,
          runFiles.phase1.response_text_txt ? e("details",null,[ e("summary",null,"response_text.txt"), TextBlock(runFiles.phase1.response_text_txt, 520) ]) : null,
          runFiles.phase1.cleaned_text_txt ? e("details",null,[ e("summary",null,"cleaned_text.txt"), TextBlock(runFiles.phase1.cleaned_text_txt, 520) ]) : null,
          runFiles.phase1.request_json ? e("details",null,[ e("summary",null,"request.json"), Json(runFiles.phase1.request_json, 520) ]) : null,
          runFiles.phase1.response_http_json ? e("details",null,[ e("summary",null,"response.http.json"), Json(runFiles.phase1.response_http_json, 520) ]) : null,
        ]) : null,

        (runFiles && runFiles.phase2 && runFiles.phase2.ok) ? e("details",null,[
          e("summary",null,"phase2 run files (prompt/response/cleaned/request/http)"),
          runFiles.phase2.prompt_txt ? e("details",null,[ e("summary",null,"prompt.txt"), TextBlock(runFiles.phase2.prompt_txt, 520) ]) : null,
          runFiles.phase2.response_text_txt ? e("details",null,[ e("summary",null,"response_text.txt"), TextBlock(runFiles.phase2.response_text_txt, 520) ]) : null,
          runFiles.phase2.cleaned_text_txt ? e("details",null,[ e("summary",null,"cleaned_text.txt"), TextBlock(runFiles.phase2.cleaned_text_txt, 520) ]) : null,
          runFiles.phase2.request_json ? e("details",null,[ e("summary",null,"request.json"), Json(runFiles.phase2.request_json, 520) ]) : null,
          runFiles.phase2.response_http_json ? e("details",null,[ e("summary",null,"response.http.json"), Json(runFiles.phase2.response_http_json, 520) ]) : null,
        ]) : null,

        (runFiles && runFiles.phase3 && runFiles.phase3.ok) ? e("details",null,[
          e("summary",null,"phase3 run files (prompt/response/cleaned/request/http)"),
          runFiles.phase3.prompt_txt ? e("details",null,[ e("summary",null,"prompt.txt"), TextBlock(runFiles.phase3.prompt_txt, 520) ]) : null,
          runFiles.phase3.response_text_txt ? e("details",null,[ e("summary",null,"response_text.txt"), TextBlock(runFiles.phase3.response_text_txt, 520) ]) : null,
          runFiles.phase3.cleaned_text_txt ? e("details",null,[ e("summary",null,"cleaned_text.txt"), TextBlock(runFiles.phase3.cleaned_text_txt, 520) ]) : null,
          runFiles.phase3.request_json ? e("details",null,[ e("summary",null,"request.json"), Json(runFiles.phase3.request_json, 520) ]) : null,
          runFiles.phase3.response_http_json ? e("details",null,[ e("summary",null,"response.http.json"), Json(runFiles.phase3.response_http_json, 520) ]) : null,
        ]) : null,
      ]);

      return Card(name, subtitle, body);
    }));

    const debugFooter = showDebug ? Card(
      "Debug",
      null,
      e("div",null,[
        e("div",{style:{opacity:.9,marginBottom:8}}, ["run_id ", Mono(runId)]),
        e("details",null,[ e("summary",null,"Full /api/llm2/latest (raw)"), Json(data || {missing:true}, 520) ])
      ])
    ) : null;

    return e("div",{className:"llm-page", style:{overflowX:"hidden"}},[
      header,
      grid,
      debugFooter
    ]);
  };
})();
