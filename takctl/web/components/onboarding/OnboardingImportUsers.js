/* global React */
(function () {
  var h = (window.h || React.createElement); window.h = h;

  const useState = React.useState;

  const _t = (window.t || function (k) { return k; });

  const lib = (window.TaksOnboarding && window.TaksOnboarding.lib) || null;
  function _needLib() { if (!lib) throw new Error('Missing onboarding lib: load components/onboarding/lib.js before Onboarding.js'); return lib; }
  function _colText(v){ return _needLib().colText(v); }

  function _jsonPretty(obj) {
    try { return JSON.stringify(obj, null, 2); } catch (e) { return String(obj || ""); }
  }

  async function postMultipartJson(url, file, fieldName) {
    const fd = new FormData();
    fd.append(fieldName || "file", file);

    const resp = await fetch(url, { method: "POST", body: fd });
    const text = await resp.text();
    let body = null;
    try { body = JSON.parse(text); } catch (e) { body = { raw: text }; }

    if (!resp.ok) {
      const msg =
        (body && (body.detail || body.error || body.message)) ||
        ("HTTP " + resp.status);
      throw new Error(msg);
    }
    return body;
  }

  function MappingTable({ preview }) {
    const headers = (preview && preview.headers) || [];
    const headersNorm = (preview && preview.headers_norm) || [];
    const mapping = (preview && preview.mapping) || {};

    const rows = [];
    for (let i = 0; i < headers.length; i++) {
      const mapsTo = (mapping && mapping[String(i)]) ? String(mapping[String(i)]) : "—";
      rows.push({ idx: i, h: headers[i], hn: headersNorm[i], mapsTo });
    }

    return h(
      "table",
      { className: "tbl", style: { marginTop: "10px" } },
      h("thead", null,
        h("tr", null,
          h("th", null, _t("import.col_idx")),
          h("th", null, _t("import.header")),
          h("th", null, _t("import.header_norm")),
          h("th", null, _t("import.maps_to"))
        )
      ),
      h("tbody", null,
        rows.map((r) =>
          h("tr", { key: "m" + r.idx },
            h("td", null, _colText(r.idx)),
            h("td", null, _colText(r.h)),
            h("td", null, _colText(r.hn)),
            h("td", null, _colText(r.mapsTo))
          )
        )
      )
    );
  }

  function SampleUsersTable({ preview }) {
    const users = (preview && preview.sample_users) || [];
    return h(
      "table",
      { className: "tbl", style: { marginTop: "10px" } },
      h("thead", null,
        h("tr", null,
          h("th", null, _t("import.row")),
          h("th", null, _t("import.username")),
          h("th", null, _t("import.password")),
          h("th", null, _t("import.is_admin")),
          h("th", null, _t("import.groups"))
        )
      ),
      h("tbody", null,
        users.map((u, idx) => {
          const gs = (u && Array.isArray(u.groups)) ? u.groups : [];
          const ok = (u && u._row_ok === true);
          const cls = ok ? "badge badge-current" : "badge badge-stale";
          return h("tr", { key: "u" + idx },
            h("td", null, String(idx + 1)),
            h("td", null, _colText(u.username)),
            h("td", null, (u && u.password) ? "••••••" : "—"),
            h("td", null, h("span", { className: cls }, (u && u.is_admin) ? "YES" : "NO")),
            h("td", null, gs.length ? gs.join(", ") : "—")
          );
        })
      )
    );
  }

  function ValidationIssuesTable({ title, issues, bad }) {
    const rows = issues || [];
    if (!rows.length) return null;

    return h(
      "div",
      { style: { marginTop: "12px" } },
      h("div", { className: "muted" }, title),
      h(
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
          rows.map((x, idx) =>
            h("tr", { key: title + ":" + idx },
              h("td", null, _colText(x.row)),
              h("td", null, _colText(x.username)),
              h("td", null,
                h("span", { className: bad ? "badge badge-stale" : "badge badge-recent" }, _colText(x.code))
              ),
              h("td", null, _colText(x.message)),
              h("td", null, _colText(x.detail))
            )
          )
        )
      )
    );
  }

  function OnboardingImportUsersPage() {
    const [file, setFile] = useState(null);
    const [sampleN, setSampleN] = useState(5);
    const [updateExisting, setUpdateExisting] = useState(false);

    const [busy, setBusy] = useState(false);
    const [err, setErr] = useState("");
    const [preview, setPreview] = useState(null);
    const [validation, setValidation] = useState(null);
    const [result, setResult] = useState(null);

    async function doPreview() {
      if (!file) return;
      setBusy(true); setErr(""); setResult(null);
      try {
        const url = "/api/onboarding/import/preview?sample_n=" + encodeURIComponent(String(sampleN || 5));
        const out = await postMultipartJson(url, file, "file");
        setPreview(out);
      } catch (e) {
        setErr(String((e && e.message) || e));
      } finally {
        setBusy(false);
      }
    }

    async function doValidate() {
      if (!file) return;
      setBusy(true); setErr(""); setResult(null);
      try {
        const out = await postMultipartJson("/api/onboarding/import/validate", file, "file");
        setValidation(out);
      } catch (e) {
        setErr(String((e && e.message) || e));
      } finally {
        setBusy(false);
      }
    }

    function goJobs(jobId) {
      var hash = "#onboarding/import-jobs";
      if (jobId) hash += "?job_id=" + encodeURIComponent(String(jobId));
      try {
        window.location.hash = hash;
      } catch (e) {
        window.location.hash = "#onboarding/import-jobs";
      }
    }

    async function doStartJob(dryRun) {
      if (!file) return;

      if (!preview) {
        setErr("Run preview first.");
        return;
      }

      const missingRequired = (preview && preview.missing_required) || [];
      if (missingRequired.length > 0) {
        setErr("Preview shows missing required columns. Fix them before starting the import job.");
        return;
      }

      if (!validation) {
        setErr("Run validation before starting the import job.");
        return;
      }

      if (validation && validation.ok === false) {
        const errs = (validation && validation.errors) || [];
        if (errs.length > 0) {
          setErr("Validation has blocking errors. Fix them before starting the import job.");
          return;
        }
      }

      setBusy(true); setErr(""); setResult(null);
      try {
        const qs =
          "?dry_run=" + encodeURIComponent(dryRun ? "true" : "false") +
          "&update_existing=" + encodeURIComponent(updateExisting ? "true" : "false");
        const url = "/api/onboarding/import/jobs" + qs;
        const out = await postMultipartJson(url, file, "file");
        setResult(out);
        goJobs(out && out.job_id);
      } catch (e) {
        setErr(String((e && e.message) || e));
      } finally {
        setBusy(false);
      }
    }

    const missingRequired = (preview && preview.missing_required) || [];
    const okPreview = !!preview && Array.isArray(missingRequired) && missingRequired.length === 0;

    const vSummary = (validation && validation.summary) || {};
    const vErrors = (validation && validation.errors) || [];
    const vWarnings = (validation && validation.warnings) || [];
    const vOk = !!(validation && validation.ok === true);

    const canStart = !!file && !!preview && okPreview && !!validation && !busy && (vErrors.length === 0);

    return h(
      "div",
      null,

      h("div", { className: "card-title" }, _t("page.onboarding_import")),

      h("div", { className: "muted", style: { marginBottom: "10px" } },
        h("div", null, _t("import.how_it_works")),
        h("div", { style: { opacity: 0.75, marginTop: "2px" } }, _t("import.how_it_works_body")),
        h("div", { style: { opacity: 0.75, marginTop: "6px" } },
          "Tip: leave password blank to auto-generate a compliant password."
        )
      ),

      h("div", { className: "card", style: { marginTop: "10px" } },
        h("div", { className: "card-title", style: { fontSize: "14px" } }, _t("import.step1")),

        h("div", { style: { display: "flex", gap: "12px", alignItems: "center", flexWrap: "wrap", marginTop: "10px" } },
          h("input", {
            type: "file",
            accept: ".xlsx,.csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv",
            onChange: (e) => {
              const f = (e && e.target && e.target.files && e.target.files[0]) ? e.target.files[0] : null;
              setFile(f);
              setPreview(null);
              setValidation(null);
              setResult(null);
              setErr("");
            }
          }),

          h("div", { className: "muted" },
            _t("import.selected") + ": " + (file ? file.name : "—")
          ),

          h("div", { className: "muted" }, _t("import.sample_rows") + ":"),

          h("input", {
            className: "inp",
            style: { width: "70px" },
            value: String(sampleN || 5),
            onChange: (e) => setSampleN(parseInt(String(e.target.value || "5"), 10) || 5)
          }),

          h("button", { className: "btn", disabled: busy || !file, onClick: doPreview },
            busy ? _t("import.working") : _t("import.preview")
          ),

          h("button", { className: "btn", disabled: busy || !file, onClick: doValidate },
            busy ? _t("import.working") : "Validate"
          ),

          h("button", { className: "btn", onClick: function () { goJobs(); } },
            "Import jobs"
          )
        ),

        h("div", { style: { marginTop: "10px" } },
          h("label", { className: "muted", style: { display: "inline-flex", gap: "8px", alignItems: "center" } },
            h("input", {
              type: "checkbox",
              checked: !!updateExisting,
              onChange: (e) => setUpdateExisting(!!(e && e.target && e.target.checked))
            }),
            _t("import.update_existing")
          )
        ),

        err ? h("div", { className: "note", style: { marginTop: "10px", borderColor: "rgba(255,0,0,0.4)" } },
          h("b", null, _t("import.error") + ": "),
          h("span", null, String(err))
        ) : null
      ),

      preview ? h("div", { className: "card", style: { marginTop: "12px" } },
        h("div", { className: "card-title", style: { fontSize: "14px" } }, _t("import.step2")),

        okPreview
          ? h("div", { className: "note", style: { marginTop: "8px" } }, _t("import.preview_ok"))
          : h("div", { className: "note", style: { marginTop: "8px", borderColor: "rgba(255,180,0,0.35)" } },
              _t("import.preview_not_ok") + " (" + _colText(missingRequired.join(", ")) + ")"
            ),

        h("div", { className: "muted", style: { marginTop: "10px" } }, _t("import.mapping")),
        h(MappingTable, { preview }),

        h("div", { className: "muted", style: { marginTop: "12px" } }, _t("import.sample_users")),
        h(SampleUsersTable, { preview }),

        h("details", { style: { marginTop: "12px" } },
          h("summary", { className: "muted" }, _t("import.raw_preview")),
          h("pre", { style: { marginTop: "8px", whiteSpace: "pre-wrap" } }, _jsonPretty(preview))
        )
      ) : null,

      validation ? h("div", { className: "card", style: { marginTop: "12px" } },
        h("div", { className: "card-title", style: { fontSize: "14px" } }, "Validation"),

        h("div", { className: "note", style: { marginTop: "8px", borderColor: vOk ? "rgba(0,180,0,0.35)" : "rgba(255,180,0,0.35)" } },
          "Rows=" + _colText(vSummary.rows) +
          "  Errors=" + _colText(vSummary.errors) +
          "  Warnings=" + _colText(vSummary.warnings) +
          "  Result=" + (vOk ? "OK" : "CHECK REQUIRED")
        ),

        ValidationIssuesTable({ title: "Errors", issues: vErrors, bad: true }),
        ValidationIssuesTable({ title: "Warnings", issues: vWarnings, bad: false }),

        h("details", { style: { marginTop: "12px" } },
          h("summary", { className: "muted" }, "Raw validation"),
          h("pre", { style: { marginTop: "8px", whiteSpace: "pre-wrap" } }, _jsonPretty(validation))
        )
      ) : null,

      (preview || validation) ? h("div", { className: "card", style: { marginTop: "12px" } },
        h("div", { className: "card-title", style: { fontSize: "14px" } }, "Start import"),

        h("div", { className: "muted", style: { marginBottom: "10px" } },
          !preview
            ? "Run preview first."
            : !okPreview
              ? "Preview shows missing required columns. Fix them before starting the import job."
              : !validation
                ? "Run validation before starting the import job."
                : vErrors.length
                  ? "Validation has blocking errors. Start job is disabled."
                  : "Validation passed. You can start the import job."
        ),

        h("div", { style: { display: "flex", gap: "10px", flexWrap: "wrap" } },
          h("button", { className: "btn", disabled: !canStart, onClick: function () { doStartJob(true); } },
            "Start dry-run job"
          ),
          h("button", { className: "btn", disabled: !canStart, onClick: function () { doStartJob(false); } },
            "Start import job"
          ),
          h("button", { className: "btn", onClick: function () { goJobs(); } },
            "Open import jobs"
          )
        )
      ) : null,

      result ? h("div", { className: "card", style: { marginTop: "12px" } },
        h("div", { className: "card-title", style: { fontSize: "14px" } }, _t("import.result")),
        h("pre", { style: { marginTop: "8px", whiteSpace: "pre-wrap" } }, _jsonPretty(result))
      ) : null
    );
  }

  window.OnboardingImportUsersPage = OnboardingImportUsersPage;
})();
