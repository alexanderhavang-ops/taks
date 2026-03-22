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
    if (name === "presence") return "Presence";
    if (name === "weather") return "Weather";
    if (name === "timeline") return "Timeline";
    if (name === "enemy") return "Enemy";
    return String(name || "");
  }

  function niceDomainEyebrow(name){
    if (name === "_summary") return "Latest assessment";
    if (name === "chatter") return "Communications";
    if (name === "missions") return "Operations";
    if (name === "presence") return "Presence";
    if (name === "weather") return "Weather";
    if (name === "timeline") return "Timeline";
    if (name === "enemy") return "Enemy";
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
          if (phObj.files["detail.json"] && !phObj.files.detail_json) phObj.files.detail_json = phObj.files["detail.json"];
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
    const p3detail = (((p3||{}).files||{}).detail_json || null);
    const p3trace = (((p3||{}).files||{}).trace_json || null);

    const runId =
      (p3trace && p3trace.run_id) ||
      (p2trace && p2trace.run_id) ||
      null;

    return { p1, p2, p3, p2find, p2trace, p3card, p3detail, p3trace, qcount, latestDir, runId };
  }

  function decodeHtmlEntities(s){
    const t = String(s || "");
    if (!t) return "";
    try{
      const el = document.createElement("textarea");
      el.innerHTML = t;
      return el.value;
    }catch{
      return t
        .replace(/&#x27;/gi, "'")
        .replace(/&#39;/g, "'")
        .replace(/&quot;/g, "\"")
        .replace(/&amp;/g, "&")
        .replace(/&lt;/g, "<")
        .replace(/&gt;/g, ">");
    }
  }

  function stripHtmlTags(s){
    return decodeHtmlEntities(
      String(s || "")
        .replace(/<script[\s\S]*?<\/script>/gi, "")
        .replace(/<style[\s\S]*?<\/style>/gi, "")
        .replace(/<[^>]+>/g, " ")
        .replace(/\s+/g, " ")
        .trim()
    );
  }

  function normalizeOperationalText(s){
    let t = decodeHtmlEntities(String(s || "").trim());
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
    return /\b\d{4}-\d{2}-\d{2}\b/.test(t) || /\b\d{2}:\d{2}\b/.test(t) || /\bTNR\s+\d{6,}\w?\b/i.test(t);
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

  function extractFromPhase3Card(s){
    const htmlCard = s && s.p3card && typeof s.p3card.html === "string" ? s.p3card.html : "";
    if (!htmlCard) return null;

    const h3m = htmlCard.match(/<h3[^>]*>([\s\S]*?)<\/h3>/i);
    const pm = htmlCard.match(/<p[^>]*>([\s\S]*?)<\/p>/i);
    const lis = [];
    const reLi = /<li[^>]*>([\s\S]*?)<\/li>/ig;
    let m;
    while ((m = reLi.exec(htmlCard)) !== null) {
      lis.push(normalizeOperationalText(stripHtmlTags(m[1] || "")));
      if (lis.length >= 4) break;
    }

    const headline = h3m ? normalizeOperationalText(stripHtmlTags(h3m[1] || "")) : "";
    const summary = pm ? normalizeOperationalText(stripHtmlTags(pm[1] || "")) : "";

    return {
      headline: headline,
      summary: summary,
      bullets: uniqueNonEmpty(lis)
    };
  }

  function isBadSummaryText(t){
    const s = String(t || "").trim().toLowerCase();
    if (!s) return true;
    if (s === "no current assessment") return true;
    if (s.indexOf("phase2_failed") >= 0) return true;
    if (s.indexOf("no_json_object_start") >= 0) return true;
    if (s.indexOf("failed:") >= 0) return true;
    return false;
  }

  function deriveOperationalModel(name, s){
    const p2 = s.p2find || {};
    const p3 = extractFromPhase3Card(s);

    let important = "";
    let newest = "";
    let details = "";

    if (p3 && p3.headline) {
      important = p3.headline;
      details = p3.summary || "";
      newest = "";
    } else {
      important = normalizeOperationalText(p2.important || "");
      newest = normalizeOperationalText(p2.newest || "");
      details = normalizeOperationalText(p2.details || "");
    }

    const title = niceDomainName(name);
    const eyebrow = niceDomainEyebrow(name);

    let timestamp = "";
    if (looksLikeTimestamp(newest)) timestamp = newest;

    let headline = important || details || newest || "No current assessment";

    if (name === "_summary"){
      const summary = details && details !== headline ? details : "";
      return { title, eyebrow, headline, timestamp, summary, bullets: [] };
    }

    const bullets = p3 && p3.bullets && p3.bullets.length
      ? p3.bullets
      : uniqueNonEmpty([
          (newest && !looksLikeTimestamp(newest) && newest !== headline) ? newest : "",
          (details && details !== headline && details !== newest) ? details : ""
        ]).slice(0, 4);

    const summary = (p3 && p3.summary && p3.summary !== headline) ? p3.summary : "";

    return { title, eyebrow, headline, timestamp, summary, bullets };
  }

  function buildSummaryFallback(otherNames, doms){
    const models = otherNames.map(name => deriveOperationalModel(name, domPhaseSummary(doms[name] || {})));
    const good = models.filter(m => !isBadSummaryText(m.headline));

    if (!good.length) {
      return {
        title: "Summary",
        eyebrow: "Latest assessment",
        headline: "No current assessment",
        timestamp: "",
        summary: "",
        bullets: []
      };
    }

    const headline = good.length === 1
      ? "One active domain shows operationally relevant activity."
      : good.length + " active domains show operationally relevant activity.";

    const bullets = [];
    good.forEach(m=>{
      const lead = m.headline || "";
      const extra = m.summary || (m.bullets && m.bullets[0]) || "";
      bullets.push(
        extra && extra !== lead
          ? (m.title + ": " + lead + " " + extra)
          : (m.title + ": " + lead)
      );
    });

    return {
      title: "Summary",
      eyebrow: "Latest assessment",
      headline: headline,
      timestamp: "",
      summary: "",
      bullets: uniqueNonEmpty(bullets).slice(0, 4)
    };
  }

  function escapeHtml(s){
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function sanitizeHtmlLite(s){
    let t = String(s || "");
    t = t.replace(/<\s*script[\s\S]*?<\/\s*script\s*>/gi, "");
    t = t.replace(/<\s*style[\s\S]*?<\/\s*style\s*>/gi, "");
    t = t.replace(/<\s*(iframe|object|embed|link|meta)\b[^>]*>/gi, "");
    t = t.replace(/\son\w+\s*=\s*(".*?"|'.*?'|[^\s>]+)/gi, "");
    t = t.replace(/\sstyle\s*=\s*(".*?"|'.*?'|[^\s>]+)/gi, "");
    t = t.replace(/\s(href|src)\s*=\s*("|\')\s*javascript:[\s\S]*?\2/gi, "");
    return t.trim();
  }

  function buildFallbackDetailHtml(title, model, meta){
    const bullets = (model.bullets || []).map(function(b){
      return "<li>" + escapeHtml(b) + "</li>";
    }).join("");

    const metaBits = [];
    if (meta && meta.runId) metaBits.push("Run " + escapeHtml(meta.runId));
    if (meta && meta.timestamp) metaBits.push(escapeHtml(meta.timestamp));
    if (meta && meta.latestDir) metaBits.push(escapeHtml(meta.latestDir));

    const metaHtml = metaBits.length
      ? "<div style=\"display:flex;flex-wrap:wrap;gap:8px;margin:0 0 18px 0;\">"
          + metaBits.map(function(x){
              return "<span style=\"display:inline-flex;align-items:center;padding:4px 10px;border-radius:999px;border:1px solid rgba(255,255,255,.08);background:rgba(255,255,255,.03);font-size:12px;opacity:.86;\">"
                + x +
              "</span>";
            }).join("")
        + "</div>"
      : "";

    return ""
      + "<div class=\"llm-detail-page\">"
      +   "<div style=\"font-size:12px;letter-spacing:.08em;text-transform:uppercase;opacity:.62;font-weight:700;margin-bottom:12px;\">"
      +     escapeHtml(model.eyebrow || "")
      +   "</div>"
      +   "<h1 style=\"margin:0 0 14px 0;line-height:1.15;font-size:38px;font-weight:800;\">"
      +     escapeHtml(model.headline || title)
      +   "</h1>"
      +   metaHtml
      +   (model.summary ? "<div style=\"font-size:18px;line-height:1.65;opacity:.94;margin:0 0 20px 0;\">" + escapeHtml(model.summary) + "</div>" : "")
      +   (bullets ? "<div style=\"margin-top:16px;\"><div style=\"font-size:12px;letter-spacing:.08em;text-transform:uppercase;opacity:.62;font-weight:700;margin-bottom:10px;\">Key points</div><ul style=\"line-height:1.85;font-size:17px;padding-left:24px;\">" + bullets + "</ul></div>" : "")
      + "</div>";
  }

  function buildSummaryAggregateDetailHtml(otherNames, doms){
    const sections = otherNames.map(function(name){
      const s = domPhaseSummary(doms[name] || {});
      const model = deriveOperationalModel(name, s);
      const bullets = (model.bullets || []).map(function(b){
        return "<li>" + escapeHtml(b) + "</li>";
      }).join("");
      return {
        name: name,
        title: niceDomainName(name),
        eyebrow: niceDomainEyebrow(name),
        headline: model.headline || "",
        summary: model.summary || "",
        bullets: bullets
      };
    }).filter(function(sec){
      return !isBadSummaryText(sec.headline);
    });

    if (!sections.length) {
      return "<div><h1 style=\"margin:0 0 12px 0;font-size:38px;line-height:1.15;\">No current assessment</h1></div>";
    }

    const intro = sections.length === 1
      ? "One domain currently shows operationally relevant activity."
      : sections.length + " domains currently show operationally relevant activity.";

    return ""
      + "<div class=\"llm-detail-page\">"
      +   "<div style=\"font-size:12px;letter-spacing:.08em;text-transform:uppercase;opacity:.62;font-weight:700;margin-bottom:12px;\">Latest assessment</div>"
      +   "<h1 style=\"margin:0 0 14px 0;line-height:1.15;font-size:38px;font-weight:800;\">Summary</h1>"
      +   "<div style=\"font-size:18px;line-height:1.65;opacity:.94;margin:0 0 22px 0;\">" + escapeHtml(intro) + "</div>"
      +   sections.map(function(sec){
            return ""
              + "<section style=\"margin:0 0 18px 0;padding:16px 16px 14px 16px;border:1px solid rgba(255,255,255,.06);border-radius:16px;background:rgba(255,255,255,.02);\">"
              +   "<div style=\"font-size:12px;letter-spacing:.08em;text-transform:uppercase;opacity:.62;font-weight:700;margin-bottom:8px;\">" + escapeHtml(sec.eyebrow) + "</div>"
              +   "<h2 style=\"margin:0 0 10px 0;font-size:24px;line-height:1.25;\">" + escapeHtml(sec.title) + "</h2>"
              +   "<div style=\"font-size:18px;line-height:1.55;font-weight:700;margin:0 0 10px 0;\">" + escapeHtml(sec.headline) + "</div>"
              +   (sec.summary ? "<div style=\"line-height:1.7;opacity:.92;margin:0 0 10px 0;\">" + escapeHtml(sec.summary) + "</div>" : "")
              +   (sec.bullets ? "<ul style=\"line-height:1.8;padding-left:24px;margin:0;\">" + sec.bullets + "</ul>" : "")
              + "</section>";
          }).join("")
      + "</div>";
  }

  function renderOperationalCardFromModel(name, m){
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

  function renderOperationalCard(name, s){
    return renderOperationalCardFromModel(name, deriveOperationalModel(name, s));
  }

  function renderDebugSection(s){
    const p1 = s.p1 || {};
    const p2 = s.p2 || {};
    const p3 = s.p3 || {};

    return e("div",null,[
      e("div",{style:{display:"flex",gap:10,flexWrap:"wrap",alignItems:"center",marginBottom:10}},[
        e("span",null,"p1 "), domainBadge(s.p1),
        e("span",null,"p2 "), domainBadge(s.p2),
        e("span",null,"p3 "), domainBadge(s.p3),
        s.qcount!=null ? e("span",{style:{opacity:.9}}, "phase1 queries: " + String(s.qcount)) : null
      ]),
      e("div",{style:{opacity:.8,fontSize:12,marginBottom:10,overflowWrap:"anywhere"}}, "latest dir: " + (s.latestDir || "—")),
      e("div",{style:{opacity:.95,margin:"10px 0 6px"}}, "Debug (latest/*)"),
      (p1.files && p1.files.latest_json) ? e("details",null,[ e("summary",null,"phase1/latest.json"), Json(p1.files.latest_json, 520) ]) : null,
      (p1.files && p1.files.trace_json) ? e("details",null,[ e("summary",null,"phase1/trace.json"), Json(p1.files.trace_json, 520) ]) : null,
      (p2.files && p2.files.findings_json) ? e("details",null,[ e("summary",null,"phase2/findings.json"), Json(p2.files.findings_json, 520) ]) : null,
      (p2.files && p2.files.trace_json) ? e("details",null,[ e("summary",null,"phase2/trace.json"), Json(p2.files.trace_json, 520) ]) : null,
      (p3.files && p3.files.card_json) ? e("details",null,[ e("summary",null,"phase3/card.json"), Json(p3.files.card_json, 520) ]) : null,
      (p3.files && p3.files.detail_json) ? e("details",null,[ e("summary",null,"phase3/detail.json"), Json(p3.files.detail_json, 520) ]) : null,
      (p3.files && p3.files.trace_json) ? e("details",null,[ e("summary",null,"phase3/trace.json"), Json(p3.files.trace_json, 520) ]) : null
    ]);
  }

  function CardShell(title, body, extraStyle, onClick){
    return e("div",{
      className:"llm-card",
      onClick: onClick || undefined,
      title: onClick ? "Open detail page" : undefined,
      style:Object.assign({
        border:"1px solid rgba(255,255,255,.06)",
        borderRadius:18,
        padding:"18px 18px 16px 18px",
        background:"linear-gradient(90deg, rgba(255,255,255,.02), rgba(255,255,255,.01))",
        boxShadow:"0 0 0 1px rgba(0,0,0,.08) inset",
        cursor: onClick ? "pointer" : "default",
        transition:"transform .12s ease, box-shadow .12s ease, border-color .12s ease"
      }, extraStyle || {})
    },[
      e("div",{style:{
        display:"flex",
        alignItems:"center",
        gap:10,
        marginBottom:8
      }},[
        e("div",{style:{fontSize:15,fontWeight:700,opacity:.96}}, title),
        onClick ? e("div",{style:{
          marginLeft:"auto",
          fontSize:11,
          letterSpacing:".08em",
          textTransform:"uppercase",
          opacity:.5
        }}, "Open") : null
      ]),
      body ? e("div",null, body) : null
    ]);
  }

  function getDetailFromLocation(){
    try{
      const u = new URL(window.location.href);
      return u.searchParams.get("detail") || "";
    }catch{
      return "";
    }
  }

  function setDetailInLocation(name){
    const u = new URL(window.location.href);
    if (name) u.searchParams.set("detail", name);
    else u.searchParams.delete("detail");
    window.history.pushState({}, "", u.toString());
  }

  function DetailPageShell(title, eyebrow, html, metaBits){
    return e("div", {
      style:{
        border:"1px solid rgba(255,255,255,.06)",
        borderRadius:20,
        padding:22,
        background:"linear-gradient(90deg, rgba(255,255,255,.02), rgba(255,255,255,.01))"
      }
    }, [
      e("div", {
        style:{
          fontSize:12,
          letterSpacing:".08em",
          textTransform:"uppercase",
          opacity:.62,
          fontWeight:700,
          marginBottom:10
        }
      }, eyebrow || ""),
      e("div", {
        style:{
          fontSize:18,
          fontWeight:700,
          opacity:.96,
          marginBottom:10
        }
      }, title),
      (metaBits && metaBits.length) ? e("div", {
        style:{
          display:"flex",
          flexWrap:"wrap",
          gap:8,
          marginBottom:16
        }
      }, metaBits.map(function(bit, idx){
        return e("span", {
          key: idx,
          style:{
            display:"inline-flex",
            alignItems:"center",
            padding:"4px 10px",
            borderRadius:999,
            border:"1px solid rgba(255,255,255,.08)",
            background:"rgba(255,255,255,.03)",
            fontSize:12,
            opacity:.86
          }
        }, bit);
      })) : null,
      e("div", {
        className:"llm-detail-html",
        style:{
          border:"1px solid rgba(255,255,255,.05)",
          borderRadius:16,
          padding:20,
          background:"rgba(255,255,255,.02)",
          lineHeight:1.75
        },
        dangerouslySetInnerHTML:{__html: sanitizeHtmlLite(html)}
      })
    ]);
  }

  window.LLMView = function TacticalOperationsView() {
    const [data, setData] = React.useState(null);
    const [err, setErr] = React.useState(null);
    const [showDebug, setShowDebug] = React.useState(false);
    const [detailName, setDetailName] = React.useState(getDetailFromLocation());

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
      const onPop = ()=>setDetailName(getDetailFromLocation());
      window.addEventListener("popstate", onPop);
      return ()=>{
        clearInterval(t);
        window.removeEventListener("popstate", onPop);
      };
    },[]);

    function openDetailPage(name){
      setDetailInLocation(name);
      setDetailName(name);
    }

    function closeDetailPage(){
      setDetailInLocation("");
      setDetailName("");
    }

    const header = e("div",{style:{display:"flex",alignItems:"center",gap:12,marginBottom:14}},[
      e("h2",{style:{margin:"0 10px 0 0"}}, "Tactical Operations"),
      e("div",{style:{marginLeft:"auto",display:"flex",gap:10,alignItems:"center"}},[
        detailName ? e("button",{onClick:closeDetailPage}, "Back to overview") : null,
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

    if (detailName) {
      const s = domPhaseSummary(doms[detailName] || {});
      const model = deriveOperationalModel(detailName, s);

      let title = niceDomainName(detailName);
      let eyebrow = niceDomainEyebrow(detailName);
      let html = "";
      let stateForDebug = s;
      let metaBits = [];

      if (s.runId) metaBits.push("Run " + s.runId);
      if (model.timestamp) metaBits.push(model.timestamp);

      if (detailName === "_summary") {
        const useOwnSummaryDetail =
          s.p3detail &&
          typeof s.p3detail.html === "string" &&
          String(s.p3detail.html).trim() &&
          !isBadSummaryText(model.headline);
        title = "Summary";
        eyebrow = "Latest assessment";
        html = useOwnSummaryDetail
          ? String(s.p3detail.html)
          : buildSummaryAggregateDetailHtml(otherNames, doms);
      } else {
        html = (s.p3detail && typeof s.p3detail.html === "string" && String(s.p3detail.html).trim())
          ? String(s.p3detail.html)
          : buildFallbackDetailHtml(title, model, {
              runId: s.runId || "",
              timestamp: model.timestamp || "",
              latestDir: ""
            });
      }

      const detailBody = showDebug
        ? e("div", null, [
            e("div", {
              style:{
                marginBottom:12,
                opacity:.85,
                fontSize:13
              }
            }, "Detail page: " + title),
            renderDebugSection(stateForDebug),
            e("div", {style:{marginTop:12}}, [
              DetailPageShell(title, eyebrow, html, metaBits)
            ])
          ])
        : DetailPageShell(title, eyebrow, html, metaBits);

      return e("div",{className:"llm-page", style:{overflowX:"hidden"}},[
        header,
        detailBody
      ]);
    }

    const summaryCard = (function(){
      const summaryState = summaryName ? domPhaseSummary(doms[summaryName] || {}) : null;
      const summaryModel = summaryState ? deriveOperationalModel("_summary", summaryState) : null;
      const useFallbackSummary = !summaryModel || isBadSummaryText(summaryModel.headline);
      const fallbackModel = buildSummaryFallback(otherNames, doms);

      const body = showDebug
        ? (summaryState ? renderDebugSection(summaryState) : renderOperationalCardFromModel("_summary", fallbackModel))
        : renderOperationalCardFromModel("_summary", useFallbackSummary ? fallbackModel : summaryModel);

      const onClick = !showDebug ? ()=>openDetailPage("_summary") : null;

      return CardShell("Summary", body, {marginBottom:12}, onClick);
    })();

    const othersGrid = e("div",{
      style:{
        display:"grid",
        gridTemplateColumns:"repeat(auto-fit, minmax(420px, 1fr))",
        gap:"12px"
      }
    }, otherNames.map(name=>{
      const s = domPhaseSummary(doms[name] || {});
      const body = showDebug ? renderDebugSection(s) : renderOperationalCard(name, s);
      const onClick = !showDebug ? ()=>openDetailPage(name) : null;
      return CardShell(niceDomainName(name), body, {minHeight: showDebug ? "auto" : 150}, onClick);
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
