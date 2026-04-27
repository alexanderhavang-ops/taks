(function () {
  'use strict';

  var h = (window.h || React.createElement); window.h = h;

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  async function api(path, opts) {
    const r = await fetch(path, opts || {});
    const text = await r.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch (_) {}
    if (!r.ok) {
      throw new Error((data && (data.detail || data.error)) || text || ('HTTP ' + r.status));
    }
    return data;
  }

  function statusClass(status) {
    const s = String(status || '').toUpperCase();
    if (s === 'PASS') return 'ok';
    if (s === 'WARN') return 'warn';
    if (s === 'FAIL') return 'err';
    return 'muted';
  }

  function statusIcon(status) {
    const s = String(status || '').toUpperCase();
    if (s === 'PASS') return '✓';
    if (s === 'WARN') return '!';
    if (s === 'FAIL') return '×';
    return 'i';
  }

  function humanSummary(out) {
    const sum = (out && out.summary) || {};
    return [
      'PASS ' + String(sum.PASS || 0),
      'WARN ' + String(sum.WARN || 0),
      'FAIL ' + String(sum.FAIL || 0),
      'INFO ' + String(sum.INFO || 0)
    ].join(' · ');
  }

  function groupResults(results) {
    const groups = [];
    const by = {};
    (Array.isArray(results) ? results : []).forEach(function (r) {
      const g = String(r.group || 'general');
      if (!by[g]) {
        by[g] = [];
        groups.push(g);
      }
      by[g].push(r);
    });
    return groups.map(function (g) {
      return { group: g, rows: by[g] || [] };
    });
  }

  function resultTone(out) {
    const status = String((out && out.status) || '').toLowerCase();
    if (status === 'pass') return 'ok';
    if (status === 'warn') return 'warn';
    if (status === 'fail') return 'err';
    return 'muted';
  }

  function renderResults(root) {
    const box = root.querySelector('[data-package-results]');
    const out = root._result;
    if (!box) return;

    if (!out) {
      box.innerHTML = '<div class="card"><div class="muted">No check has been run yet.</div></div>';
      return;
    }

    const groups = groupResults(out.results);
    const tone = resultTone(out);
    const title = tone === 'ok'
      ? 'Package check passed'
      : (tone === 'warn' ? 'Package check completed with warnings' : 'Package check failed');

    box.innerHTML = '' +
      '<div class="card" style="margin-bottom:16px">' +
        '<div style="display:flex; gap:12px; align-items:flex-start; justify-content:space-between; flex-wrap:wrap">' +
          '<div>' +
            '<div class="' + esc(tone) + '" style="font-size:18px; font-weight:800">' + esc(title) + '</div>' +
            '<div class="muted" style="margin-top:6px">' + esc(humanSummary(out)) + '</div>' +
          '</div>' +
          '<div style="display:flex; gap:8px; flex-wrap:wrap">' +
            '<span class="tab tab-active">Type: ' + esc(out.package_type || 'unknown') + '</span>' +
            '<span class="tab tab-active">Style: ' + esc(out.platform_style || 'unknown') + '</span>' +
          '</div>' +
        '</div>' +
      '</div>' +
      groups.map(function (g) {
        return '' +
          '<details class="card" open style="margin-bottom:12px">' +
            '<summary style="cursor:pointer; font-weight:800">' + esc(g.group) + '</summary>' +
            '<div style="display:grid; gap:10px; margin-top:12px">' +
              g.rows.map(function (r) {
                const st = String(r.status || 'INFO').toUpperCase();
                const cls = statusClass(st);
                const detail = String(r.detail || '');
                return '' +
                  '<div style="border:1px solid rgba(255,255,255,0.08); border-radius:12px; padding:10px; background:rgba(255,255,255,0.02)">' +
                    '<div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap">' +
                      '<span class="' + esc(cls) + '" style="font-weight:900">' + esc(statusIcon(st)) + ' ' + esc(st) + '</span>' +
                      '<span style="font-weight:700">' + esc(r.name || '') + '</span>' +
                    '</div>' +
                    (detail
                      ? '<pre style="white-space:pre-wrap; overflow:auto; margin:8px 0 0 0; font-size:12px">' + esc(detail) + '</pre>'
                      : '') +
                  '</div>';
              }).join('') +
            '</div>' +
          '</details>';
      }).join('');
  }

  async function runCheck(root) {
    const urlEl = root.querySelector('[data-package-url]');
    const hostEl = root.querySelector('[data-expected-host]');
    const userEl = root.querySelector('[data-expected-user]');
    const callsignEl = root.querySelector('[data-expected-callsign]');
    const statusEl = root.querySelector('[data-package-status]');
    const btn = root.querySelector('[data-run-check]');

    const zipUrl = String((urlEl && urlEl.value) || '').trim();
    if (!zipUrl) {
      statusEl.textContent = 'Paste a ZIP URL first.';
      statusEl.className = 'warn';
      return;
    }

    statusEl.textContent = 'Downloading and checking package...';
    statusEl.className = 'muted';
    if (btn) btn.disabled = true;

    try {
      const out = await api('/api/package-check/zip-url', {
        method: 'POST',
        credentials: 'include',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          zip_url: zipUrl,
          expected_host: String((hostEl && hostEl.value) || '').trim(),
          expected_user: String((userEl && userEl.value) || '').trim(),
          expected_callsign: String((callsignEl && callsignEl.value) || '').trim()
        })
      });

      root._result = out || {};
      const tone = resultTone(out);
      statusEl.textContent = 'Done: ' + humanSummary(out);
      statusEl.className = tone;
      renderResults(root);
    } catch (e) {
      root._result = null;
      statusEl.textContent = 'Check failed: ' + String((e && e.message) || e || 'unknown error');
      statusEl.className = 'err';
      renderResults(root);
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  function fillExpectedHost(root) {
    const urlEl = root.querySelector('[data-package-url]');
    const hostEl = root.querySelector('[data-expected-host]');
    if (!urlEl || !hostEl) return;

    try {
      const u = new URL(String(urlEl.value || '').trim());
      hostEl.value = u.hostname || '';
    } catch (_) {
      hostEl.value = window.location.hostname || '';
    }
  }

  function render(root) {
    root.innerHTML = '' +
      '<div class="page package-check-page">' +
        '<h2>Test ZIP URL</h2>' +
        '<div class="card" style="margin-bottom:16px">' +
          '<div class="card__title">Package checker</div>' +
          '<div class="muted" style="margin-top:6px">' +
            'Paste a TAK onboarding ZIP URL. TAKS will download it server-side, classify the package, parse XML/PREF files, inspect manifest contents, and validate certs where present.' +
          '</div>' +
          '<form data-package-form style="display:grid; gap:10px; margin-top:14px">' +
            '<label class="label">ZIP URL</label>' +
            '<input data-package-url type="url" required placeholder="https://host/api/onboarding/cards/.../packages/atak/soft-cert/package.zip?regen=1" style="width:100%" />' +
            '<div class="grid grid--6" style="gap:10px">' +
              '<div style="grid-column:span 2">' +
                '<label class="label">Expected host</label>' +
                '<input data-expected-host type="text" placeholder="optional; derived from URL if empty" style="width:100%" />' +
              '</div>' +
              '<div style="grid-column:span 2">' +
                '<label class="label">Expected user</label>' +
                '<input data-expected-user type="text" placeholder="optional; searches UserAuthenticationFile.xml" style="width:100%" />' +
              '</div>' +
              '<div style="grid-column:span 2">' +
                '<label class="label">Expected callsign</label>' +
                '<input data-expected-callsign type="text" placeholder="optional; compares locationCallsign" style="width:100%" />' +
              '</div>' +
            '</div>' +
            '<div style="display:flex; gap:8px; flex-wrap:wrap; align-items:center">' +
              '<button data-run-check type="submit" class="btn">Run check</button>' +
              '<button data-fill-host type="button" class="btn btn--secondary">Fill host from URL</button>' +
              '<button data-clear-results type="button" class="btn btn--secondary">Clear</button>' +
            '</div>' +
            '<div data-package-status class="muted"></div>' +
          '</form>' +
        '</div>' +
        '<div data-package-results></div>' +
      '</div>';

    root.querySelector('[data-package-form]').addEventListener('submit', function (ev) {
      ev.preventDefault();
      runCheck(root);
    });

    root.querySelector('[data-fill-host]').addEventListener('click', function () {
      fillExpectedHost(root);
    });

    root.querySelector('[data-clear-results]').addEventListener('click', function () {
      root._result = null;
      const statusEl = root.querySelector('[data-package-status]');
      statusEl.textContent = '';
      statusEl.className = 'muted';
      renderResults(root);
    });

    renderResults(root);
  }

  window.PackageCheckPage = function PackageCheckPage() {
    const ref = React.useRef(null);
    React.useEffect(function () {
      if (ref.current) render(ref.current);
    }, []);
    return h("div", { ref: ref });
  };
})();
