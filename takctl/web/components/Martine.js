/* global React */
(function () {
  var h = (window.h || React.createElement); window.h = h;
  const e = h;

  async function postJson(url, body){
    const r = await fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {})
    });
    const t = await r.text();
    let j = null;
    try { j = JSON.parse(t); } catch (_) {}
    if (!r.ok) {
      const msg = (j && (j.detail || j.error)) ? String(j.detail || j.error) : ("HTTP " + r.status + ": " + t.slice(0, 400));
      throw new Error(msg);
    }
    if (j == null) throw new Error("Non-JSON response from " + url + ": " + t.slice(0, 400));
    return j;
  }

  async function getJson(url){
    const r = await fetch(url, {
      method: "GET",
      credentials: "same-origin"
    });
    const t = await r.text();
    let j = null;
    try { j = JSON.parse(t); } catch (_) {}
    if (!r.ok) {
      const msg = (j && (j.detail || j.error)) ? String(j.detail || j.error) : ("HTTP " + r.status + ": " + t.slice(0, 400));
      throw new Error(msg);
    }
    if (j == null) throw new Error("Non-JSON response from " + url + ": " + t.slice(0, 400));
    return j;
  }

  function Box(props){
    return e("div", {
      style: {
        background: "rgba(255,255,255,0.03)",
        border: "1px solid rgba(255,255,255,0.08)",
        borderRadius: 12,
        padding: 16
      }
    }, props.children);
  }

  function Label(txt){
    return e("div", {
      style: {
        fontSize: 12,
        opacity: 0.8,
        marginBottom: 6,
        textTransform: "uppercase",
        letterSpacing: "0.04em"
      }
    }, String(txt || ""));
  }

  function Pre(obj){
    return e("pre", {
      style: {
        margin: 0,
        whiteSpace: "pre-wrap",
        overflowWrap: "anywhere",
        wordBreak: "break-word",
        fontSize: 12,
        lineHeight: "16px",
        fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace"
      }
    }, typeof obj === "string" ? obj : JSON.stringify(obj, null, 2));
  }

  function LinkList(logFiles){
    const entries = Object.entries(logFiles || {});
    if (!entries.length) return null;
    return e("div", { style: { display: "grid", gap: 6 } },
      entries.map(function(pair){
        const k = pair[0], v = pair[1];
        return e("div", { key: k, style: { fontSize: 13 } },
          e("span", { style: { display: "inline-block", minWidth: 170, opacity: 0.8 } }, k),
          e("code", null, String(v || ""))
        );
      })
    );
  }

  function eventTitle(ev){
    const t = String((ev && ev.type) || "");
    if (t === "run_started") return "Run started";
    if (t === "turn_started") return "Turn started";
    if (t === "llm_response_parsed") return "LLM decision";
    if (t === "tool_call_started") return "Tool call started";
    if (t === "tool_call_finished") return "Tool call finished";
    if (t === "final_answer") return "Final answer";
    if (t === "run_finished") return "Run finished";
    if (t === "run_failed") return "Run failed";
    if (t === "llm_parse_error") return "LLM parse error";
    if (t === "invalid_action") return "Invalid action";
    if (t === "invalid_tool") return "Invalid tool";
    if (t === "repair_turn_requested") return "Repair turn requested";
    return t || "event";
  }

  function eventSummary(ev){
    if (!ev) return "";
    if (ev.type === "run_started") return ev.user_input || "";
    if (ev.type === "turn_started") return "turn " + String(ev.turn || "");
    if (ev.type === "llm_response_parsed") {
      return [ev.action, ev.tool_name, ev.reason].filter(Boolean).join(" • ");
    }
    if (ev.type === "tool_call_started") {
      return [ev.tool_name, ev.reason].filter(Boolean).join(" • ");
    }
    if (ev.type === "tool_call_finished") {
      return [ev.tool_name, ev.ok === false ? "failed" : "ok"].filter(Boolean).join(" • ");
    }
    if (ev.type === "final_answer") return ev.answer_preview || "";
    if (ev.type === "run_finished") return ev.ok ? "ok" : "not ok";
    if (ev.type === "run_failed") return ev.error || "";
    if (ev.type === "repair_turn_requested") return ev.message || "";
    return "";
  }

  function TraceEvent(ev, idx){
    return e("div", {
      key: idx,
      style: {
        borderTop: idx === 0 ? "none" : "1px solid rgba(255,255,255,0.08)",
        paddingTop: idx === 0 ? 0 : 12,
        marginTop: idx === 0 ? 0 : 12
      }
    },
      e("div", {
        style: {
          display: "flex",
          justifyContent: "space-between",
          gap: 12,
          alignItems: "baseline",
          marginBottom: 4
        }
      },
        e("div", { style: { fontWeight: 700, fontSize: 14 } }, eventTitle(ev)),
        e("div", { style: { fontSize: 12, opacity: 0.7 } }, String(ev.ts || ""))
      ),
      eventSummary(ev) ? e("div", {
        style: {
          fontSize: 13,
          lineHeight: "18px",
          marginBottom: 8,
          opacity: 0.95,
          whiteSpace: "pre-wrap",
          overflowWrap: "anywhere"
        }
      }, eventSummary(ev)) : null,
      e(Pre, null, ev)
    );
  }

  function MartineView(){
    const [question, setQuestion] = React.useState("Where is Martine state stored?");
    const [loading, setLoading] = React.useState(false);
    const [error, setError] = React.useState("");
    const [result, setResult] = React.useState(null);
    const [events, setEvents] = React.useState([]);
    const [eventsError, setEventsError] = React.useState("");

    async function loadEvents(runId){
      if (!runId) return;
      try {
        const res = await getJson("/api/martine/runs/" + encodeURIComponent(runId) + "/events");
        setEvents(Array.isArray(res.events) ? res.events : []);
        setEventsError("");
      } catch (e) {
        setEventsError(String((e && e.message) || e || "Failed to load events"));
      }
    }

    async function ask(){
      const q = String(question || "").trim();
      if (!q) {
        setError("Question is empty");
        return;
      }
      setLoading(true);
      setError("");
      setResult(null);
      setEvents([]);
      setEventsError("");
      try {
        const res = await postJson("/api/martine/ask", { question: q });
        setResult(res);
        if (res && res.run_id) {
          await loadEvents(res.run_id);
        }
      } catch (e) {
        setError(String((e && e.message) || e || "Request failed"));
      } finally {
        setLoading(false);
      }
    }

    function onKeyDown(ev){
      if ((ev.metaKey || ev.ctrlKey) && ev.key === "Enter") ask();
    }

    return e("div", { style: { display: "grid", gap: 16 } },

      e("div", null,
        e("h2", { style: { margin: "0 0 6px 0" } }, "Martine"),
        e("div", { className: "muted", style: { opacity: 0.8 } },
          "Test Martine from the takctl web UI. This uses the same Python agent loop as the CLI."
        )
      ),

      e(Box, null,
        e(Label, null, "Question"),
        e("textarea", {
          value: question,
          onChange: function(ev){ setQuestion(ev.target.value); },
          onKeyDown: onKeyDown,
          rows: 5,
          placeholder: "Ask Martine something...",
          style: {
            width: "100%",
            minHeight: 120,
            resize: "vertical",
            borderRadius: 10,
            border: "1px solid rgba(255,255,255,0.12)",
            background: "rgba(0,0,0,0.15)",
            color: "inherit",
            padding: 12,
            boxSizing: "border-box",
            font: "inherit"
          }
        }),
        e("div", { style: { marginTop: 12, display: "flex", gap: 10, alignItems: "center" } },
          e("button", {
            type: "button",
            className: "btn",
            onClick: ask,
            disabled: loading
          }, loading ? "Thinking..." : "Ask Martine"),
          e("span", { style: { fontSize: 12, opacity: 0.75 } }, "Ctrl/Cmd+Enter to submit")
        )
      ),

      error ? e(Box, null,
        e(Label, null, "Error"),
        e("div", { style: { color: "#ff8f8f" } }, error)
      ) : null,

      result ? e(Box, null,
        e(Label, null, "Answer"),
        e("div", {
          style: {
            whiteSpace: "pre-wrap",
            overflowWrap: "anywhere",
            wordBreak: "break-word",
            fontSize: 15,
            lineHeight: "22px"
          }
        }, String((result && result.answer) || "")),
        e("div", { style: { marginTop: 12, fontSize: 13, opacity: 0.8 } },
          "run_id: ",
          e("code", null, String((result && result.run_id) || ""))
        )
      ) : null,

      result ? e(Box, null,
        e(Label, null, "Agent trace"),
        eventsError ? e("div", { style: { color: "#ff8f8f", marginBottom: 10 } }, eventsError) : null,
        events && events.length
          ? e("div", { style: { display: "grid", gap: 0 } }, events.map(TraceEvent))
          : e("div", { style: { opacity: 0.75, fontSize: 13 } }, "No trace events found")
      ) : null,

      result ? e(Box, null,
        e(Label, null, "Selection"),
        e(Pre, null, (result && result.selection) || {})
      ) : null,

      result ? e(Box, null,
        e(Label, null, "Tool result"),
        e(Pre, null, (result && result.tool_result) || {})
      ) : null,

      result ? e(Box, null,
        e(Label, null, "Log files"),
        e(LinkList, { logFiles: (result && result.log_files) || {} })
      ) : null
    );
  }

  window.MartineView = MartineView;
})();
