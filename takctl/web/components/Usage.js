/* global React */
(function () {
  var h = (window.h || React.createElement); window.h = h;
  const e = h;

  function fmtInt(v){
    try { return Number(v || 0).toLocaleString("sv-SE"); }
    catch (_) { return String(v || 0); }
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

  function StatCard(props){
    return e("div", {
      style: {
        background: "rgba(255,255,255,0.025)",
        border: "1px solid rgba(255,255,255,0.08)",
        borderRadius: 12,
        padding: 14
      }
    }, [
      e("div", {
        key: "label",
        style: { fontSize: 12, opacity: 0.72, textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 8 }
      }, String(props.label || "")),
      e("div", {
        key: "value",
        style: { fontSize: 28, lineHeight: "32px", fontWeight: 700 }
      }, fmtInt(props.value))
    ]);
  }

  function Th(props){
    props = props || {};
    return e("th", {
      style: Object.assign({
        textAlign: "left",
        fontSize: 12,
        opacity: 0.75,
        fontWeight: 600,
        padding: "10px 12px",
        borderBottom: "1px solid rgba(255,255,255,0.08)",
        whiteSpace: "nowrap"
      }, props.extra || {})
    }, props.children);
  }

  function Td(props){
    props = props || {};
    return e("td", {
      style: Object.assign({
        padding: "10px 12px",
        borderBottom: "1px solid rgba(255,255,255,0.06)",
        verticalAlign: "top",
        fontSize: 13
      }, props.extra || {})
    }, props.children);
  }

  function UsageView(){
    const meta = useApi("/api/llm/usage", { cacheMs: 10000, pollMs: 0 });
    const base = (meta && meta.data) || {};
    const months = Array.isArray(base.months) ? base.months : [];
    const initialMonth = String(base.selected_month || "");
    const [month, setMonth] = React.useState("");

    React.useEffect(function(){
      if (!month && initialMonth) setMonth(initialMonth);
    }, [initialMonth, month]);

    const url = month ? ("/api/llm/usage?month=" + encodeURIComponent(month)) : "/api/llm/usage";
    const dataState = useApi(url, { cacheMs: 10000, pollMs: 0 });
    const data = (dataState && dataState.data) || base || {};
    const rows = Array.isArray(data.rows) ? data.rows : [];
    const totals = data.totals || {};
    const selectedMonth = String(data.selected_month || month || "");

    return e("div", { style: { display: "grid", gap: 16 } }, [

      e("div", { key: "head" }, [
        e("h2", { key: "h", style: { margin: "0 0 6px 0" } }, "LLM Usage"),
        e("div", {
          key: "sub",
          className: "muted",
          style: { opacity: 0.8 }
        }, "Tokenförbrukning per purpose och månad från llm_usage.jsonl.")
      ]),

      e(Box, { key: "toolbar" }, [
        e("div", {
          key: "row",
          style: { display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }
        }, [
          e("label", {
            key: "lbl",
            style: { fontSize: 13, opacity: 0.85, fontWeight: 600 }
          }, "Månad"),
          e("select", {
            key: "sel",
            value: selectedMonth,
            onChange: function(ev){ setMonth(String(ev.target.value || "")); },
            style: {
              minWidth: 180,
              border: "1px solid rgba(255,255,255,0.12)",
              background: "rgba(255,255,255,0.03)",
              color: "inherit",
              borderRadius: 10,
              padding: "8px 10px",
              fontSize: 13
            }
          }, months.map(function(m){
            return e("option", { key: m, value: m }, m);
          })),
          e("div", {
            key: "path",
            style: { fontSize: 12, opacity: 0.7 }
          }, String(data.log_path || ""))
        ])
      ]),

      e("div", {
        key: "stats",
        style: {
          display: "grid",
          gridTemplateColumns: "repeat(5, minmax(140px, 1fr))",
          gap: 12
        }
      }, [
        e(StatCard, { key: "calls", label: "Calls", value: totals.calls }),
        e(StatCard, { key: "in", label: "Input tokens", value: totals.input_tokens }),
        e(StatCard, { key: "out", label: "Output tokens", value: totals.output_tokens }),
        e(StatCard, { key: "total", label: "Total tokens", value: totals.total_tokens }),
        e(StatCard, { key: "err", label: "Errors", value: totals.errors })
      ]),

      (meta && meta.loading) || (dataState && dataState.loading)
        ? e(Box, { key: "loading" }, e("div", null, "Laddar usage…"))
        : null,

      (meta && meta.error)
        ? e(Box, { key: "err1" }, e("div", { style: { color: "#ff8f8f" } }, String(meta.error)))
        : null,

      (dataState && dataState.error)
        ? e(Box, { key: "err2" }, e("div", { style: { color: "#ff8f8f" } }, String(dataState.error)))
        : null,

      e(Box, { key: "table" }, [
        e("div", {
          key: "cap",
          style: { fontSize: 13, opacity: 0.8, marginBottom: 10 }
        }, selectedMonth ? ("Månad: " + selectedMonth) : "Ingen data"),

        e("div", {
          key: "wrap",
          style: { overflowX: "auto" }
        }, [
          e("table", {
            key: "tbl",
            style: {
              width: "100%",
              borderCollapse: "collapse",
              minWidth: 980
            }
          }, [
            e("thead", { key: "thead" },
              e("tr", null, [
                e(Th, { key: "purpose" }, "Purpose"),
                e(Th, { key: "calls", extra: { textAlign: "right" } }, "Calls"),
                e(Th, { key: "in", extra: { textAlign: "right" } }, "In"),
                e(Th, { key: "out", extra: { textAlign: "right" } }, "Out"),
                e(Th, { key: "total", extra: { textAlign: "right" } }, "Total"),
                e(Th, { key: "avg", extra: { textAlign: "right" } }, "Avg total"),
                e(Th, { key: "errors", extra: { textAlign: "right" } }, "Err"),
                e(Th, { key: "last" }, "Last seen")
              ])
            ),
            e("tbody", { key: "tbody" },
              rows.length
                ? rows.map(function(r){
                    return e("tr", { key: String(r.purpose || "") }, [
                      e(Td, { key: "purpose" }, e("code", null, String(r.purpose || ""))),
                      e(Td, { key: "calls", extra: { textAlign: "right", whiteSpace: "nowrap" } }, fmtInt(r.calls)),
                      e(Td, { key: "in", extra: { textAlign: "right", whiteSpace: "nowrap" } }, fmtInt(r.input_tokens)),
                      e(Td, { key: "out", extra: { textAlign: "right", whiteSpace: "nowrap" } }, fmtInt(r.output_tokens)),
                      e(Td, { key: "total", extra: { textAlign: "right", whiteSpace: "nowrap", fontWeight: 700 } }, fmtInt(r.total_tokens)),
                      e(Td, { key: "avg", extra: { textAlign: "right", whiteSpace: "nowrap" } }, fmtInt(r.avg_total_tokens)),
                      e(Td, { key: "errors", extra: { textAlign: "right", whiteSpace: "nowrap" } }, fmtInt(r.errors)),
                      e(Td, { key: "last", extra: { whiteSpace: "nowrap", opacity: 0.85 } }, String(r.last_ts_utc || ""))
                    ]);
                  })
                : e("tr", { key: "empty" }, [
                    e("td", {
                      colSpan: 8,
                      style: {
                        padding: "16px 12px",
                        opacity: 0.75
                      }
                    }, "Ingen usage-data för vald månad.")
                  ])
            )
          ])
        ])
      ])
    ]);
  }

  window.UsageView = UsageView;
})();
