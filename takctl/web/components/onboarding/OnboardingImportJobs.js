/* global React */
(function () {
  var h = (window.h || React.createElement); window.h = h;

  const useState = React.useState;
  const useEffect = React.useEffect;

  const _t = (window.t || function (k) { return k; });

  const lib = (window.TaksOnboarding && window.TaksOnboarding.lib) || null;
  function _needLib() { if (!lib) throw new Error('Missing onboarding lib: load components/onboarding/lib.js before Onboarding.js'); return lib; }
  function _colText(v){ return _needLib().colText(v); }

  async function fetchJson(url) {
    const resp = await fetch(url, { cache: "no-store" });
    const text = await resp.text();
    let body = null;
    try { body = JSON.parse(text); } catch (e) { body = { raw: text }; }
    if (!resp.ok) {
      const msg = (body && (body.detail || body.error || body.message)) || ("HTTP " + resp.status);
      throw new Error(msg);
    }
    return body;
  }

  function stateLabel(job) {
    const st = String((job && job.state) || "");
    const errs = Number((job && job.error_count) || 0);
    if (st === "done" && errs > 0) return "done_with_errors";
    return st || "unknown";
  }

  function stateBadge(job) {
    const s = stateLabel(job);
    let cls = "badge";
    if (s === "running") cls += " badge-recent";
    else if (s === "done") cls += " badge-current";
    else if (s === "done_with_errors") cls += " badge-stale";
    else if (s === "failed") cls += " badge-stale";
    else cls += " badge-never";
    return h("span", { className: cls }, s.toUpperCase());
  }

  function JobTable({ jobs, onOpen }) {
    return h(
      "table",
      { className: "tbl", style: { marginTop: "10px" } },
      h("thead", null,
        h("tr", null,
          h("th", null, "Created"),
          h("th", null, "Job ID"),
          h("th", null, "State"),
          h("th", null, "Rows"),
          h("th", null, "Created"),
          h("th", null, "Updated"),
          h("th", null, "Skipped"),
          h("th", null, "Errors"),
          h("th", null, "Current"),
          h("th", null, "Action")
        )
      ),
      h("tbody", null,
        (jobs || []).map((job) =>
          h("tr", { key: String(job.job_id || "") },
            h("td", null, _colText(job.created_at)),
            h("td", null, _colText(job.job_id)),
            h("td", null, stateBadge(job)),
            h("td", null, _colText(job.done_rows) + " / " + _colText(job.total_rows)),
            h("td", null, _colText(job.created)),
            h("td", null, _colText(job.updated)),
            h("td", null, _colText(job.skipped)),
            h("td", null, _colText(job.error_count)),
            h("td", null,
              _colText(job.current_row) +
              ((job.current_username ? (" / " + String(job.current_username)) : ""))
            ),
            h("td", null,
              h("button", { className: "btn", onClick: () => onOpen(job.job_id) }, "View")
            )
          )
        )
      )
    );
  }

  function ResultBlock({ detail }) {
    if (!detail) return null;
    const job = (detail && detail.job) || {};
    const result = (detail && detail.result) || null;
    const errors = (result && result.errors) || [];
    const results = (result && result.results) || [];

    return h(
      "div",
      { className: "card", style: { marginTop: "12px" } },

      h("div", { className: "card-title", style: { fontSize: "14px" } }, "Job details"),
      h("div", { className: "muted", style: { marginTop: "8px" } },
        "Job ID: " + _colText(job.job_id)
      ),

      h("div", { style: { marginTop: "10px", display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "10px" } },
        h("div", { className: "note" }, h("b", null, "State"), h("div", { style: { marginTop: "6px" } }, stateBadge(job))),
        h("div", { className: "note" }, h("b", null, "Rows"), h("div", { style: { marginTop: "6px" } }, _colText(job.done_rows) + " / " + _colText(job.total_rows))),
        h("div", { className: "note" }, h("b", null, "Created / Updated / Skipped"), h("div", { style: { marginTop: "6px" } }, _colText(job.created) + " / " + _colText(job.updated) + " / " + _colText(job.skipped))),
        h("div", { className: "note" }, h("b", null, "Errors"), h("div", { style: { marginTop: "6px" } }, _colText(job.error_count)))
      ),

      job.last_error
        ? h("div", { className: "note", style: { marginTop: "10px", borderColor: "rgba(255,0,0,0.35)" } },
            h("b", null, "Last error"),
            h("div", { style: { marginTop: "6px", whiteSpace: "pre-wrap" } }, String(job.last_error))
          )
        : null,

      result
        ? h("details", { style: { marginTop: "12px" }, open: true },
            h("summary", { className: "muted" }, "Row results"),
            h("pre", { style: { marginTop: "8px", whiteSpace: "pre-wrap" } }, JSON.stringify(results, null, 2))
          )
        : null,

      result
        ? h("details", { style: { marginTop: "12px" }, open: errors.length > 0 },
            h("summary", { className: "muted" }, "Errors"),
            h("pre", { style: { marginTop: "8px", whiteSpace: "pre-wrap" } }, JSON.stringify(errors, null, 2))
          )
        : null
    );
  }

  function OnboardingImportJobsPage() {
    const [busy, setBusy] = useState(false);
    const [err, setErr] = useState("");
    const [jobs, setJobs] = useState([]);
    const [selectedJobId, setSelectedJobId] = useState("");
    const [detail, setDetail] = useState(null);

    async function refreshJobs() {
      setBusy(true);
      setErr("");
      try {
        const out = await fetchJson("/api/onboarding/import/jobs?limit=50");
        setJobs((out && out.jobs) || []);
      } catch (e) {
        setErr(String((e && e.message) || e));
      } finally {
        setBusy(false);
      }
    }

    async function openJob(jobId) {
      if (!jobId) return;
      setSelectedJobId(String(jobId));
      setErr("");
      try {
        const out = await fetchJson("/api/onboarding/import/jobs/" + encodeURIComponent(String(jobId)));
        setDetail(out || null);
      } catch (e) {
        setErr(String((e && e.message) || e));
      }
    }

    useEffect(() => {
      refreshJobs();
      const id = window.setInterval(refreshJobs, 3000);
      return () => window.clearInterval(id);
    }, []);

    useEffect(() => {
      if (!selectedJobId) return;
      const id = window.setInterval(function () {
        openJob(selectedJobId);
      }, 2000);
      return () => window.clearInterval(id);
    }, [selectedJobId]);

    return h(
      "div",
      null,
      h("div", { className: "card-title" }, "Onboarding — Import jobs"),
      h("div", { className: "muted", style: { marginBottom: "10px" } }, "History and live progress for onboarding import jobs."),

      h("div", { style: { display: "flex", gap: "10px", flexWrap: "wrap", marginBottom: "10px" } },
        h("button", { className: "btn", disabled: busy, onClick: refreshJobs }, busy ? "Refreshing…" : "Refresh"),
        h("button", { className: "btn", onClick: function () {
          try {
            _needLib().setHashRoute("import");
          } catch (e) {
            window.location.hash = "#onboarding/import";
          }
        } }, "Back to import")
      ),

      err
        ? h("div", { className: "note", style: { marginTop: "10px", borderColor: "rgba(255,0,0,0.35)" } },
            h("b", null, "Error: "),
            h("span", null, String(err))
          )
        : null,

      h(JobTable, { jobs, onOpen: openJob }),

      detail ? h(ResultBlock, { detail }) : null
    );
  }

  window.OnboardingImportJobsPage = OnboardingImportJobsPage;
})();
