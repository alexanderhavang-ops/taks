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

  function progressPct(job) {
    const done = Number((job && job.done_rows) || 0);
    const total = Number((job && job.total_rows) || 0);
    if (!total || total < 1) return 0;
    const pct = Math.round((done * 100) / total);
    return Math.max(0, Math.min(100, pct));
  }

  function ProgressBar({ job }) {
    const pct = progressPct(job);
    return h(
      "div",
      { style: { minWidth: "180px" } },
      h("div", {
        style: {
          width: "100%",
          height: "10px",
          borderRadius: "999px",
          background: "rgba(255,255,255,0.08)",
          overflow: "hidden"
        }
      },
        h("div", {
          style: {
            width: pct + "%",
            height: "100%",
            background: "rgba(120,180,255,0.9)"
          }
        })
      ),
      h("div", { className: "muted", style: { marginTop: "4px", fontSize: "12px" } },
        _colText((job && job.done_rows) || 0) + " / " + _colText((job && job.total_rows) || 0) + " (" + pct + "%)"
      )
    );
  }

  function _hashQueryParam(name) {
    try {
      const raw = String(window.location.hash || "");
      const qidx = raw.indexOf("?");
      if (qidx < 0) return "";
      const qs = raw.slice(qidx + 1);
      const p = new URLSearchParams(qs);
      return String(p.get(name) || "");
    } catch (e) {
      return "";
    }
  }

  function _setHashWithJob(jobId) {
    const hash = "#onboarding/import-jobs" + (jobId ? ("?job_id=" + encodeURIComponent(String(jobId))) : "");
    window.location.hash = hash;
  }

  function JobTable({ jobs, selectedJobId, onOpen }) {
    return h(
      "table",
      { className: "tbl", style: { marginTop: "10px" } },
      h("thead", null,
        h("tr", null,
          h("th", null, "Job ID"),
          h("th", null, "State"),
          h("th", null, "Progress"),
          h("th", null, "Created at"),
          h("th", null, "Created"),
          h("th", null, "Updated"),
          h("th", null, "Skipped"),
          h("th", null, "Errors"),
          h("th", null, "Current"),
          h("th", null, "Action")
        )
      ),
      h("tbody", null,
        (jobs || []).map((job) => {
          const selected = String(job.job_id || "") === String(selectedJobId || "");
          return h("tr", { key: String(job.job_id || ""), style: selected ? { outline: "1px solid rgba(120,180,255,0.45)" } : null },
            h("td", null, _colText(job.job_id)),
            h("td", null, stateBadge(job)),
            h("td", null, h(ProgressBar, { job })),
            h("td", null, _colText(job.created_at)),
            h("td", null, _colText(job.created)),
            h("td", null, _colText(job.updated)),
            h("td", null, _colText(job.skipped)),
            h("td", null, _colText(job.error_count)),
            h("td", null,
              _colText(job.current_row) +
              ((job.current_username ? (" / " + String(job.current_username)) : ""))
            ),
            h("td", null,
              h("button", { className: "btn", onClick: function () { onOpen(job.job_id); } }, "View")
            )
          );
        })
      )
    );
  }

  function passwordSourceBadge(v) {
    const s = String(v || "");
    let cls = "badge badge-never";
    if (s === "generated") cls = "badge badge-current";
    else if (s === "provided") cls = "badge badge-recent";
    else if (s === "unchanged") cls = "badge badge-never";
    return h("span", { className: cls }, s ? s.toUpperCase() : "—");
  }

  function emailStatusCell(emailStatus) {
    if (!emailStatus) return "—";

    if (emailStatus.ok) {
      return h(
        "div",
        null,
        h("span", { className: "badge badge-current" }, "SENT"),
        emailStatus.to ? h("div", { className: "muted", style: { marginTop: "4px" } }, _colText(emailStatus.to)) : null
      );
    }

    return h(
      "div",
      null,
      h("span", { className: "badge badge-stale" }, "FAILED"),
      emailStatus.to ? h("div", { className: "muted", style: { marginTop: "4px" } }, _colText(emailStatus.to)) : null,
      emailStatus.error ? h("div", { className: "muted", style: { marginTop: "4px", whiteSpace: "pre-wrap" } }, _colText(emailStatus.error)) : null
    );
  }

  function RowResultsTable({ rows }) {
    const items = Array.isArray(rows) ? rows : [];
    if (!items.length) return null;

    return h(
      "table",
      { className: "tbl", style: { marginTop: "8px" } },
      h("thead", null,
        h("tr", null,
          h("th", null, "Row"),
          h("th", null, "Username"),
          h("th", null, "Status"),
          h("th", null, "Password"),
          h("th", null, "Email"),
          h("th", null, "Card"),
          h("th", null, "Message")
        )
      ),
      h("tbody", null,
        items.map((x, idx) => {
          const status = String(x && (x.status || x.result || x.outcome || "") || "");
          let cls = "badge badge-never";
          if (status === "created" || status === "updated" || status === "ok") cls = "badge badge-current";
          else if (status === "skipped" || status === "dry_run") cls = "badge badge-recent";
          else if (status === "error" || status === "failed") cls = "badge badge-stale";

          const cardUrl = (x && x.card_url) ? String(x.card_url) : "";
          const emailStatus = x && x.email_status;
          const pwSource = x && x.password_source;

          return h("tr", { key: "rr:" + idx },
            h("td", null, _colText(x && x.row)),
            h("td", null, _colText(x && x.username)),
            h("td", null, h("span", { className: cls }, _colText(status || "—"))),
            h("td", null,
              h("div", null, passwordSourceBadge(pwSource)),
              (x && x.password_generated)
                ? h("div", { className: "muted", style: { marginTop: "4px" } }, "generated")
                : null
            ),
            h("td", null, emailStatusCell(emailStatus)),
            h("td", null,
              cardUrl
                ? h("a", { href: cardUrl, target: "_blank", rel: "noopener noreferrer" }, "Open card")
                : "—"
            ),
            h("td", null, _colText((x && (x.message || x.detail || x.error || x.reason)) || ""))
          );
        })
      )
    );
  }

  function ErrorTable({ rows }) {
    const items = Array.isArray(rows) ? rows : [];
    if (!items.length) return null;

    return h(
      "table",
      { className: "tbl", style: { marginTop: "8px" } },
      h("thead", null,
        h("tr", null,
          h("th", null, "Row"),
          h("th", null, "Username"),
          h("th", null, "Code"),
          h("th", null, "Message"),
          h("th", null, "Detail")
        )
      ),
      h("tbody", null,
        items.map((x, idx) =>
          h("tr", { key: "er:" + idx },
            h("td", null, _colText(x && x.row)),
            h("td", null, _colText(x && x.username)),
            h("td", null, h("span", { className: "badge badge-stale" }, _colText(x && x.code))),
            h("td", null, _colText(x && x.message)),
            h("td", null, _colText((x && (x.detail || x.error)) || ""))
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
        h("div", { className: "note" }, h("b", null, "Progress"), h("div", { style: { marginTop: "6px" } }, h(ProgressBar, { job }))),
        h("div", { className: "note" }, h("b", null, "Created / Updated / Skipped"), h("div", { style: { marginTop: "6px" } }, _colText(job.created) + " / " + _colText(job.updated) + " / " + _colText(job.skipped))),
        h("div", { className: "note" }, h("b", null, "Errors"), h("div", { style: { marginTop: "6px" } }, _colText(job.error_count)))
      ),

      job.current_row || job.current_username
        ? h("div", { className: "note", style: { marginTop: "10px" } },
            h("b", null, "Current row"),
            h("div", { style: { marginTop: "6px" } },
              _colText(job.current_row) + (job.current_username ? (" / " + String(job.current_username)) : "")
            )
          )
        : null,

      job.last_error
        ? h("div", { className: "note", style: { marginTop: "10px", borderColor: "rgba(255,0,0,0.35)" } },
            h("b", null, "Last error"),
            h("div", { style: { marginTop: "6px", whiteSpace: "pre-wrap" } }, String(job.last_error))
          )
        : null,

      result
        ? h("div", { style: { marginTop: "12px" } },
            h("div", { className: "muted" }, "Row results"),
            h(RowResultsTable, { rows: results })
          )
        : null,

      result && errors.length
        ? h("div", { style: { marginTop: "12px" } },
            h("div", { className: "muted" }, "Errors"),
            h(ErrorTable, { rows: errors })
          )
        : null,

      h("details", { style: { marginTop: "12px" } },
        h("summary", { className: "muted" }, "Raw job detail"),
        h("pre", { style: { marginTop: "8px", whiteSpace: "pre-wrap" } }, JSON.stringify(detail, null, 2))
      )
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
        const list = (out && out.jobs) || [];
        setJobs(list);

        if (!selectedJobId) {
          const hashJobId = _hashQueryParam("job_id");
          if (hashJobId) {
            setSelectedJobId(String(hashJobId));
          } else if (list.length > 0) {
            setSelectedJobId(String(list[0].job_id || ""));
          }
        }
      } catch (e) {
        setErr(String((e && e.message) || e));
      } finally {
        setBusy(false);
      }
    }

    async function refreshSelectedJob(jobId) {
      if (!jobId) return;
      setErr("");
      try {
        const out = await fetchJson("/api/onboarding/import/jobs/" + encodeURIComponent(String(jobId)));
        setDetail(out || null);
      } catch (e) {
        setErr(String((e && e.message) || e));
      }
    }

    function openJob(jobId) {
      if (!jobId) return;
      const id = String(jobId);
      setSelectedJobId(id);
      _setHashWithJob(id);
    }

    useEffect(() => {
      refreshJobs();
      const id = window.setInterval(refreshJobs, 3000);
      return () => window.clearInterval(id);
    }, []);

    useEffect(() => {
      if (!selectedJobId) return;
      refreshSelectedJob(selectedJobId);
      const id = window.setInterval(function () {
        refreshSelectedJob(selectedJobId);
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

      h(JobTable, { jobs: jobs, selectedJobId: selectedJobId, onOpen: openJob }),

      detail ? h(ResultBlock, { detail }) : null
    );
  }

  window.OnboardingImportJobsPage = OnboardingImportJobsPage;
})();
