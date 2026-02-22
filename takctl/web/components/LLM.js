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
  function Details(label, children, open){
    return e("details",{open:!!open,style:{marginTop:10}},[
      e("summary",{style:{cursor:"pointer",fontWeight:800,userSelect:"none"}},label),
      e("div",{style:{marginTop:8}},children)
    ]);
  }

  function idxPhase0(snapshot){
    const p0 = snapshot && snapshot.phase0 ? snapshot.phase0 : null;
    const qs = p0 && Array.isArray(p0.queries) ? p0.queries : [];
    const by = {}; qs.forEach(q => by[String(q.name||"")] = q);
    return { p0, qs, by };
  }
  function rows(q){ return (q && (q.row_count===0 || q.row_count)) ? q.row_count : (q && (q.rowcount===0||q.rowcount)) ? q.rowcount : 0; }
  function ok(q){ return !!(q && q.ok===true); }

  function missionsSummary(by){
    const m = by["10_mission_list"], s = by["20_subscriptions"], i = by["30_invitations"], c = by["40_changes_timeline"];
    const mRows = rows(m), sRows = rows(s), iRows = rows(i), cRows = rows(c);
    const latestName = (m && m.rows && m.rows[0] && m.rows[0].name) ? String(m.rows[0].name) : "—";
    const latestTs   = (m && m.rows && m.rows[0] && m.rows[0].create_time) ? String(m.rows[0].create_time) : "—";
    const badge = (ok(m)&&ok(s)&&ok(i)&&ok(c)) ? Pill("OK","ok") : Pill("Needs attention","bad");
    const bullets = [
      `Missions: ${mRows} (latest: ${latestName})`,
      `Subscriptions: ${sRows} • Invitations: ${iRows}`,
      `Recent changes rows: ${cRows}`,
      `Latest create_time: ${latestTs}`
    ];
    return { badge, bullets };
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
    const msum = missionsSummary(by);

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

    const overview = e("div",{style:{display:"grid",gridTemplateColumns:"repeat(12, 1fr)",gap:14}},[
      e("div",{style:{gridColumn:"span 12"}}, Card("Summary", topStatus,
        e("div",{style:{opacity:.95,fontSize:13,lineHeight:"20px"}},[
          e("div",null,["Latest run: ", Mono(runId)]),
          e("div",null,["Timestamp: ", Mono(ts)]),
          err ? e("div",{style:{color:"salmon",marginTop:8}}, "Error: " + String(err)) : null,
          p0 ? e("div",{style:{marginTop:8,opacity:.9}},["Phase0 queries: ", Mono(String(qs.length))]) : e("div",{style:{marginTop:8,opacity:.9}},"No snapshot yet.")
        ])
      )),
      e("div",{style:{gridColumn:"span 6"}}, Card("Missions", msum.badge,
        e("div",{style:{opacity:.95,fontSize:13,lineHeight:"20px"}}, msum.bullets.map((b,i)=>e("div",{key:i},b))),
        ()=>setPage("missions")
      )),
      e("div",{style:{gridColumn:"span 6"}}, Card("Mini-domains (future)", Pill("TODO","neutral"),
        e("div",{style:{opacity:.85,fontSize:13,lineHeight:"20px"}},[
          e("div",null,"More cards will appear here: Clients, Certs, CRL, System Health…"),
          e("div",null,"This page stays clean; debug is optional.")
        ])
      ))
    ]);

    const missions = e("div",null,[
      Card("Missions — key facts", msum.badge,
        e("div",{style:{opacity:.95,fontSize:13,lineHeight:"20px"}}, msum.bullets.map((b,i)=>e("div",{key:i},b)))
      ),
      e("div",{style:{height:12}}),
      Card("Evidence", null, e("div",null,[
        tablePreview(by["10_mission_list"], 8),
        e("div",{style:{height:10}}),
        tablePreview(by["20_subscriptions"], 8),
        e("div",{style:{height:10}}),
        tablePreview(by["30_invitations"], 8),
        e("div",{style:{height:10}}),
        tablePreview(by["40_changes_timeline"], 8),
      ]))
    ]);

    const debug = showDebug ? Card("Debug — Phase0 timeline", null,
      e("div",null,[
        err ? e("div",{style:{color:"salmon",marginBottom:10}}, "Error: " + String(err)) : null,
        p0 ? Details("Phase 0 (queries="+qs.length+")", [
          qs.map((q,idx)=>Details(
            String(q.name||("q"+idx)) + " • ok=" + String(ok(q)) + " • rows=" + String(rows(q)),
            [ Pre(String(q.sql||""), 220) ],
            false
          ))
        ], false) : e("div",{style:{opacity:.9}}, "No snapshot/phase0 yet.")
      ])
    ) : null;

    return e("div",{style:{padding:18}},[
      header,
      page==="missions" ? missions : overview,
      debug
    ]);
  };
})();
