/* global React */
(function () {
  var h = (window.h || React.createElement); window.h = h;

  const useState = React.useState;

  const _t = (window.t || function (k) { return k; });

  // shared onboarding helpers (optional)
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

  function OnboardingImportUsersPage() {
    const [file, setFile] = useState(null);
    const [sampleN, setSampleN] = useState(5);
    const [updateExisting, setUpdateExisting] = useState(false);

    const [busy, setBusy] = useState(false);
    const [err, setErr] = useState("");
    const [preview, setPreview] = useState(null);
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

    async function doApply(dryRun) {
      if (!file) return;
      setBusy(true); setErr("");
      try {
        const qs =
          "?dry_run=" + encodeURIComponent(dryRun ? "true" : "false") +
          "&update_existing=" + encodeURIComponent(updateExisting ? "true" : "false");
        const url = "/api/onboarding/import/apply" + qs;
        const out = await postMultipartJson(url, file, "file");
        setResult(out);
      } catch (e) {
        setErr(String((e && e.message) || e));
      } finally {
        setBusy(false);
      }
    }

    const missingRequired = (preview && preview.missing_required) || [];
    const okPreview = preview && Array.isArray(missingRequired) && missingRequired.length === 0;

    return h(
      "div",
      null,

      h("div", { className: "card-title" }, _t("page.onboarding_import")),

      h("div", { className: "muted", style: { marginBottom: "10px" } },
        h("div", null, _t("import.how_it_works")),
        h("div", { style: { opacity: 0.75, marginTop: "2px" } }, _t("import.how_it_works_body"))
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

        h("div", { style: { display: "flex", gap: "10px", flexWrap: "wrap", marginTop: "12px" } },
          h("button", { className: "btn", disabled: busy || !file, onClick: () => doApply(true) },
            _t("import.apply_dry_run")
          ),
          h("button", { className: "btn", disabled: busy || !file, onClick: () => doApply(false) },
            _t("import.apply")
          )
        ),

        h("details", { style: { marginTop: "12px" } },
          h("summary", { className: "muted" }, _t("import.raw_preview")),
          h("pre", { style: { marginTop: "8px", whiteSpace: "pre-wrap" } }, _jsonPretty(preview))
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
