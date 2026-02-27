(function () {
  const e = React.createElement;

  async function fetchJson(url) {
    const r = await fetch(url, { cache: "no-store" });
    if (!r.ok) throw new Error(r.status + " " + r.statusText);
    return await r.json();
  }

  function Mono(x){ return e("span",{style:{fontFamily:"ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace"}},x); }
  function Pill(text, tone){
    const bg = tone==="ok"?"rgba(40,180,99,.18)":tone==="bad"?"rgba(231,76,60,.18)":"rgba(255,255,255,.10)";
    const bd = tone==="ok"?"rgba(40,180,99,.30)":tone==="bad"?"rgba(231,76,60,.30)":"rgba(255,255,255,.16)";
    const fg = tone==="ok"?"#bff2d3":tone==="bad"?"#ffd1cc":"#d6e3ff";
    return e("span",{style:{display:"inline-flex",alignItems:"center",gap:6,padding:"2px 8px",borderRadius:999,border:"1px solid "+bd,background:bg,color:fg,fontSize:12,lineHeight:"18px",whiteSpace:"nowrap"}},text);
  }
  function Card(title, right, body, onClick){
    return e("div",{
      onClick: onClick || null,
      style:{
        border:"1px solid rgba(255,255,255,0.10)", borderRadius:14, padding:14,
        background:"rgba(255,255,255,0.03)", cursor:onClick?"pointer":"default",
        boxShadow:"0 6px 20px rgba(0,0,0,0.25)"
      }
    },[
      e("div",{style:{display:"flex",alignItems:"center",gap:10,marginBottom:8}},[
        e("div",{style:{fontWeight:900,fontSize:14}},title),
        e("div",{style:{marginLeft:"auto"}}, right || null),
      ]),
      body
    ]);
  }
  function Pre(text, maxH){
    return e("pre",{style:{margin:0,padding:"10px 12px",background:"#0b0f19",color:"#d6e3ff",
      border:"1px solid rgba(255,255,255,0.08)",borderRadius:10,overflow:"auto",maxHeight:maxH||320,
      fontSize:12,whiteSpace:"pre-wrap",wordBreak:"break-word"}}, text);
  }
  function HtmlBlock(html, maxH){
    return e("div",{style:{
      margin:0,padding:"10px 12px",background:"#0b0f19",color:"#d6e3ff",
      border:"1px solid rgba(255,255,255,0.08)",borderRadius:10,overflow:"auto",
      maxHeight:maxH||320,fontSize:12
    }, dangerouslySetInnerHTML:{__html: String(html||"") }});
  }

  // Render a validated Phase3 HTML fragment as an actual card body (not debug).
  // Server already validates allowed tags; this is just wiring.
  function Phase3Fragment(html){
    return e("div",{
      style:{
        padding:"10px 12px",
        border:"1px solid rgba(255,255,255,0.08)",
        borderRadius:10,
        background:"rgba(0,0,0,0.25)",
        overflow:"auto"
      },
      dangerouslySetInnerHTML:{ __html: String(html||"") }
    });
  }

  function Details(label, children, open){
    return e("details",{open:!!open,style:{marginTop:10}},[
      e("summary",{style:{cursor:"pointer",fontWeight:800,userSelect:"none"}},label),
      e("div",{style:{marginTop:8}},children)
    ]);
  }

  function safeStringify(obj, maxBytes){
    try{
      const s = JSON.stringify(obj, null, 2);
      if (!maxBytes) return s;
      if (s.length <= maxBytes) return s;
      return s.slice(0, maxBytes) + "\n…(truncated)…\n";
    }catch(ex){
      return String(obj);
    }
  }

  function idxPhase0(snapshot){
    const p0 = snapshot && snapshot.phase0 ? snapshot.phase0 : null;
    const qs = p0 && Array.isArray(p0.queries) ? p0.queries : [];
    const by = {}; qs.forEach(q => by[String(q.name||"")] = q);
    return { p0, qs, by };
  }
  function rows(q){ return (q && (q.row_count===0 || q.row_count)) ? q.row_count : (q && (q.rowcount===0||q.rowcount)) ? q.rowcount : 0; }
  function ok(q){ return !!(q && q.ok===true); }

  function hasPhase3Card(p3Obj){
    return !!(p3Obj && p3Obj.ok === true && typeof p3Obj.html === "string" && p3Obj.html.trim().length);
  }

  function missionsSummary(by, phase2, phase3){
    const m = by["10_mission_list"], s = by["20_subscriptions"], i = by["30_invitations"], c = by["40_changes_timeline"];
    const mRows = rows(m), sRows = rows(s), iRows = rows(i), cRows = rows(c);
    const latestName = (m && m.rows && m.rows[0] && m.rows[0].name) ? String(m.rows[0].name) : "—";
    const latestTs   = (m && m.rows && m.rows[0] && m.rows[0].create_time) ? String(m.rows[0].create_time) : "—";

    // Badge is still evidence-health from phase0 queries (for now).
    const badge = (ok(m)&&ok(s)&&ok(i)&&ok(c)) ? Pill("OK","ok") : Pill("Needs attention","bad");

    // Prefer Phase3 rendered card if present.
    const phase3Ok = hasPhase3Card(phase3);
    if (phase3Ok){
      return { badge, mode:"phase3", html: String(phase3.html || "") };
    }

    // Else: Prefer Phase2 findings if present.
    let bullets = [];
    if (phase2 && phase2.ok === true){
      if (phase2.important) bullets.push("Important: " + String(phase2.important));
      if (phase2.newest)    bullets.push("Newest: " + String(phase2.newest));
      if (phase2.details)   bullets.push("Details: " + String(phase2.details));
    }
    if (!bullets.length){
      bullets = [
        `Missions: ${mRows} (latest: ${latestName})`,
        `Subscriptions: ${sRows} • Invitations: ${iRows}`,
        `Recent changes rows: ${cRows}`,
        `Latest create_time: ${latestTs}`
      ];
    }
    return { badge, mode:"bullets", bullets };
  }

  function tablePreview(q, maxRows){
    if (!q) return e("div", {style:{opacity:.9}}, "No data.");
    if (!ok(q)) return e("div",{style:{color:"salmon"}}, "Error: " + String(q.error||"unknown"));
    const cols = Array.isArray(q.columns) ? q.columns : (q.rows && q.rows[0] ? Object.keys(q.rows[0]) : []);
    const rr = Array.isArray(q.rows) ? q.rows.slice(0, maxRows||8) : [];
    return e("div", null, [
      e("div",{style:{display:"flex",gap:10,alignItems:"center",marginBottom:6,opacity:.95}},[
        Mono(String(q.name||"")), " ", Pill("rows="+rows(q),"neutral"),
        q.truncated ? e("span",{style:{opacity:.85}}, "(truncated)") : null
      ]),
      e("div",{style:{overflow:"auto",border:"1px solid rgba(255,255,255,0.10)",borderRadius:10}},[
        e("table",{style:{width:"100%",borderCollapse:"collapse",fontSize:12}},[
          e("thead",null,e("tr",null, cols.map(c=>e("th",{style:{textAlign:"left",padding:"8px 10px",borderBottom:"1px solid rgba(255,255,255,0.10)",opacity:.9}},c)))),
          e("tbody",null, rr.map((r,idx)=>e("tr",{key:idx}, cols.map(c=>e("td",{style:{padding:"8px 10px",borderBottom:"1px solid rgba(255,255,255,0.06)",verticalAlign:"top"}}, Mono(String(r && r[c]!==undefined ? r[c] : "")))))))
        ])
      ])
    ]);
  }

  function phaseBadge(latestObj){
    if (!latestObj) return Pill("—","neutral");
    if (latestObj.ok === true) return Pill("OK","ok");
    if (latestObj.ok === false) return Pill("ERR","bad");
    return Pill("—","neutral");
  }

  function phaseMetaLines(name, latestObj, pathKeyGuess){
    const lines = [];
    if (!latestObj){
      lines.push(`${name}: not present in snapshot`);
      return lines;
    }
    const rid = latestObj.run_id ? String(latestObj.run_id) : "—";
    lines.push(`${name} run_id: ${rid}`);
    if (latestObj.generated_utc) lines.push(`${name} generated_utc: ${String(latestObj.generated_utc)}`);

    // show any path-ish fields
    const pathKeys = Object.keys(latestObj).filter(k => /_path$/.test(k));
    if (pathKeys.length){
      pathKeys.slice(0, 6).forEach(k=>{
        const v = latestObj[k];
        if (v) lines.push(`${name} ${k}: ${String(v)}`);
      });
    } else if (pathKeyGuess && latestObj[pathKeyGuess]){
      lines.push(`${name} ${pathKeyGuess}: ${String(latestObj[pathKeyGuess])}`);
    }
    return lines;
  }

  window.LLMView = function LLMView() {
    const [latest, setLatest] = React.useState(null);
    const [snapshot, setSnapshot] = React.useState(null);
    const [err, setErr] = React.useState(null);
    const [page, setPage] = React.useState("overview"); // overview | missions
    const [showDebug, setShowDebug] = React.useState(false);

    async function load(){
      try{
        const bump = Date.now();
        const a = await fetchJson("/api/llm/views/tactical/latest?b="+bump);
        const b = await fetchJson("/api/llm/views/tactical/snapshot?b="+bump);
        setLatest(a); setSnapshot(b); setErr(null);
      }catch(ex){
        setErr(ex && (ex.message || String(ex)));
      }
    }
    React.useEffect(()=>{ load(); const t=setInterval(load, 5000); return ()=>clearInterval(t); },[]);

    const { p0, qs, by } = idxPhase0(snapshot||{});
    const topStatus = latest && latest.ok===true ? Pill("OK","ok") : Pill("ERR","bad");
    const runId = latest && latest.run_id ? String(latest.run_id) : "—";
    const ts = latest && latest.ts_utc ? String(latest.ts_utc) : "—";

    // phase1/phase2/phase3 (embedded by generator snapshot.json)
    const p1Latest = snapshot && snapshot.phase1_latest ? snapshot.phase1_latest : null;
    const p1Obj    = snapshot && snapshot.phase1 ? snapshot.phase1 : null;

    const p2Latest = snapshot && snapshot.phase2_latest ? snapshot.phase2_latest : null;
    const p2Obj    = snapshot && snapshot.phase2 ? snapshot.phase2 : null;

    const p3Latest = snapshot && snapshot.phase3_latest ? snapshot.phase3_latest : null;
    const p3Obj    = snapshot && snapshot.phase3 ? snapshot.phase3 : null;

    const msum = missionsSummary(by, p2Obj, p3Obj);

    const header = e("div",{style:{display:"flex",alignItems:"center",gap:12,marginBottom:14}},[
      e("h2",{style:{margin:"0 10px 0 0"}}, page==="missions" ? "Missions" : "LLM"),
      topStatus,
      e("div",{style:{opacity:.9,fontSize:12}},["run ", Mono(runId), " • ", Mono(ts)]),
      e("div",{style:{marginLeft:"auto",display:"flex",gap:10,alignItems:"center"}},[
        e("button",{onClick:()=>setShowDebug(!showDebug),
          style:{padding:"6px 10px",borderRadius:10,border:"1px solid rgba(255,255,255,0.15)",background:"#0b0f19",color:"#d6e3ff",cursor:"pointer"}},
          showDebug ? "Hide debug" : "Show debug"
        ),
        page==="missions"
          ? e("button",{onClick:()=>setPage("overview"),
              style:{padding:"6px 10px",borderRadius:10,border:"1px solid rgba(255,255,255,0.15)",background:"#0b0f19",color:"#d6e3ff",cursor:"pointer"}}, "Back")
          : null
      ])
    ]);

    const overviewMissionsBody =
      (msum.mode === "phase3")
        ? Phase3Fragment(msum.html)
        : e("div",{style:{opacity:.95,fontSize:13,lineHeight:"20px"}}, (msum.bullets||[]).map((b,i)=>e("div",{key:i},b)));

    const missionsTopBody =
      (msum.mode === "phase3")
        ? Phase3Fragment(msum.html)
        : e("div",{style:{opacity:.95,fontSize:13,lineHeight:"20px"}}, (msum.bullets||[]).map((b,i)=>e("div",{key:i},b)));

    const overview = e("div",{style:{display:"grid",gridTemplateColumns:"repeat(12, 1fr)",gap:14}},[
      e("div",{style:{gridColumn:"span 12"}}, Card("Summary", topStatus,
        e("div",{style:{opacity:.95,fontSize:13,lineHeight:"20px"}},[
          e("div",null,["Latest run: ", Mono(runId)]),
          e("div",null,["Timestamp: ", Mono(ts)]),
          err ? e("div",{style:{color:"salmon",marginTop:8}}, "Error: " + String(err)) : null,
          p0 ? e("div",{style:{marginTop:8,opacity:.9}},["Phase0 queries: ", Mono(String(qs.length))]) : e("div",{style:{marginTop:8,opacity:.9}},"No snapshot yet.")
        ])
      )),

      e("div",{style:{gridColumn:"span 6"}}, Card("Missions", msum.badge, overviewMissionsBody, ()=>setPage("missions"))),

      // Phase1A/Phase2/Phase3 status card
      e("div",{style:{gridColumn:"span 6"}}, Card("Missions pipeline", null,
        e("div",{style:{opacity:.95,fontSize:13,lineHeight:"20px"}},[
          e("div",{style:{display:"flex",gap:10,alignItems:"center"}},[
            e("div",{style:{fontWeight:800}}, "Phase1A (ops brief)"),
            phaseBadge(p1Latest),
          ]),
          e("div",{style:{opacity:.85,marginTop:2}}, p1Latest && p1Latest.run_id ? ["run_id: ", Mono(String(p1Latest.run_id))] : "—"),
          e("div",{style:{height:10}}),
          e("div",{style:{display:"flex",gap:10,alignItems:"center"}},[
            e("div",{style:{fontWeight:800}}, "Phase2 (datasets)"),
            phaseBadge(p2Latest),
          ]),
          e("div",{style:{opacity:.85,marginTop:2}}, p2Latest && p2Latest.run_id ? ["run_id: ", Mono(String(p2Latest.run_id))] : "—"),
          e("div",{style:{height:10}}),
          e("div",{style:{display:"flex",gap:10,alignItems:"center"}},[
            e("div",{style:{fontWeight:800}}, "Phase3 (card render)"),
            phaseBadge(p3Latest),
          ]),
          e("div",{style:{opacity:.85,marginTop:2}}, p3Latest && p3Latest.run_id ? ["run_id: ", Mono(String(p3Latest.run_id))] : "—")
        ])
      )),

      e("div",{style:{gridColumn:"span 6"}}, Card("Mini-domains (future)", Pill("TODO","neutral"),
        e("div",{style:{opacity:.85,fontSize:13,lineHeight:"20px"}},[
          e("div",null,"More cards will appear here: Clients, Certs, CRL, System Health…"),
          e("div",null,"This page stays clean; debug is optional.")
        ])
      ))
    ]);

    const missions = e("div",null,[
      Card("Missions", msum.badge, missionsTopBody),

      e("div",{style:{height:12}}),

      Details("Phase2 prompt.txt", [
        Pre(String(((snapshot||{}).phase2_prompt_text) || "MISSING: snapshot.phase2_prompt_text"), 420)
      ], false),

      Details("Phase2 response.txt", [
        Pre(String(((snapshot||{}).phase2_response_text) || "MISSING: snapshot.phase2_response_text"), 420)
      ], false),

      e("div",{style:{height:12}}),

      // Optional: Phase3 snippets on missions page too
      Details("Phase3 prompt.txt", [
        Pre(String(((snapshot||{}).phase3_prompt_text) || "MISSING: snapshot.phase3_prompt_text"), 420)
      ], false),

      Details("Phase3 response.html", [
        HtmlBlock(((snapshot||{}).phase3_response_text) || "<em>MISSING: snapshot.phase3_response_text</em>", 420)
      ], false),

      e("div",{style:{height:12}}),

      Card("Evidence (Phase0)", null, e("div",null,[
        tablePreview(by["10_mission_list"], 8),
        e("div",{style:{height:10}}),
        tablePreview(by["20_subscriptions"], 8),
        e("div",{style:{height:10}}),
        tablePreview(by["30_invitations"], 8),
        e("div",{style:{height:10}}),
        tablePreview(by["40_changes_timeline"], 8),
      ]))
    ]);

    const debug = showDebug ? Card("Debug", null,
      e("div",null,[
        err ? e("div",{style:{color:"salmon",marginBottom:10}}, "Error: " + String(err)) : null,

        // Phase0 debug (existing)
        p0 ? Details("Phase 0 (queries="+qs.length+")", [
          qs.map((q,idx)=>Details(
            String(q.name||("q"+idx)) + " • ok=" + String(ok(q)) + " • rows=" + String(rows(q)),
            [ Pre(String(q.sql||""), 220) ],
            false
          ))
        ], false) : e("div",{style:{opacity:.9}}, "No snapshot/phase0 yet."),

        // Phase1A debug
        Details("Phase 1A (ops brief)", [
          e("div",{style:{opacity:.95,fontSize:13,lineHeight:"20px"}}, phaseMetaLines("phase1", p1Latest)),
          e("div",{style:{height:8}}),
          p1Obj ? Details("phase1 object (embedded in snapshot)", [
            Pre(safeStringify(p1Obj, 20000), 360)
          ], false) : e("div",{style:{opacity:.85}}, "phase1 object not embedded (or missing)."),
          e("div",{style:{height:8}}),
          Details("phase1_latest (raw)", [
            Pre(safeStringify(p1Latest, 12000), 260)
          ], false)
        ], false),

        // Phase2 debug
        Details("Phase 2 (datasets)", [
          e("div",{style:{opacity:.95,fontSize:13,lineHeight:"20px"}}, phaseMetaLines("phase2", p2Latest)),
          e("div",{style:{height:8}}),
          p2Obj ? Details("phase2 object (embedded in snapshot)", [
            Pre(safeStringify(p2Obj, 20000), 360)
          ], false) : e("div",{style:{opacity:.85}}, "phase2 object not embedded (or missing)."),
          e("div",{style:{height:8}}),
          Details("phase2_latest (raw)", [
            Pre(safeStringify(p2Latest, 12000), 260)
          ], false)
        ], false),

        // Phase3 debug
        Details("Phase 3 (card render)", [
          e("div",{style:{opacity:.95,fontSize:13,lineHeight:"20px"}}, phaseMetaLines("phase3", p3Latest)),
          e("div",{style:{height:8}}),
          p3Obj ? Details("phase3 object (card.html.json, embedded in snapshot)", [
            Pre(safeStringify(p3Obj, 20000), 360)
          ], false) : e("div",{style:{opacity:.85}}, "phase3 object not embedded (or missing)."),
          e("div",{style:{height:8}}),
          Details("phase3_latest (raw)", [
            Pre(safeStringify(p3Latest, 12000), 260)
          ], false),
          e("div",{style:{height:8}}),
          Details("phase3 prompt.txt (embedded)", [
            Pre(String(((snapshot||{}).phase3_prompt_text) || "MISSING: snapshot.phase3_prompt_text"), 420)
          ], false),
          Details("phase3 response.html (embedded)", [
            HtmlBlock(((snapshot||{}).phase3_response_text) || "<em>MISSING: snapshot.phase3_response_text</em>", 420)
          ], false)
        ], false),

        Details("phase2 prompt.txt (embedded)", [
          Pre(String(((snapshot||{}).phase2_prompt_text) || "MISSING: snapshot.phase2_prompt_text"), 420)
        ], false),
        Details("phase2 response.txt (embedded)", [
          Pre(String(((snapshot||{}).phase2_response_text) || "MISSING: snapshot.phase2_response_text"), 420)
        ], false),

        Details("snapshot.json (trim)", [
          Pre(safeStringify({
            run_id: snapshot && snapshot.run_id,
            ok: snapshot && snapshot.ok,
            phase1_path: snapshot && snapshot.phase1_path,
            phase2_path: snapshot && snapshot.phase2_path,
            phase3_path: snapshot && snapshot.phase3_path,
            phase1_latest_ok: snapshot && snapshot.phase1_latest ? snapshot.phase1_latest.ok : null,
            phase2_latest_ok: snapshot && snapshot.phase2_latest ? snapshot.phase2_latest.ok : null,
            phase3_latest_ok: snapshot && snapshot.phase3_latest ? snapshot.phase3_latest.ok : null,
            keys: snapshot ? Object.keys(snapshot) : []
          }, 12000), 240)
        ], false)
      ])
    ) : null;

    return e("div",{style:{padding:18}},[
      header,
      page==="missions" ? missions : overview,
      debug
    ]);
  };
})();
