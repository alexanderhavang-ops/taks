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

  function MartineView(){
    const [question, setQuestion] = React.useState("Where is Martine state stored?");
    const [loading, setLoading] = React.useState(false);
    const [error, setError] = React.useState("");
    const [result, setResult] = React.useState(null);

    async function ask(){
      const q = String(question || "").trim();
      if (!q) {
        setError("Question is empty");
        return;
      }
      setLoading(true);
      setError("");
      try {
        const res = await postJson("/api/martine/ask", { question: q });
        setResult(res);
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
