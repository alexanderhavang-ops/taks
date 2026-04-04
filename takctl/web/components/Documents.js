(function () {
  'use strict';

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function fmtBool(v) {
    return v ? 'yes' : 'no';
  }

  function fmtNum(v) {
    const n = Number(v || 0);
    if (!isFinite(n)) return '';
    return String(n);
  }

  function byUploadedAtDesc(a, b) {
    return String(b.uploaded_at || '').localeCompare(String(a.uploaded_at || ''));
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

  function filteredDocs(root) {
    const docs = root._docs || [];
    const q = String((root.querySelector('[data-docs-filter]') || {}).value || '').trim().toLowerCase();
    const sort = String((root.querySelector('[data-docs-sort]') || {}).value || 'uploaded_desc');

    let items = docs.slice();

    if (q) {
      items = items.filter(function (it) {
        const hay = [
          it.title, it.filename, it.doc_id, it.status, it.uploaded_at,
          it.error, it.content_type
        ].join(' ').toLowerCase();
        return hay.indexOf(q) >= 0;
      });
    }

    items.sort(function (a, b) {
      if (sort === 'title_asc') return String(a.title || a.filename || '').localeCompare(String(b.title || b.filename || ''));
      if (sort === 'title_desc') return String(b.title || b.filename || '').localeCompare(String(a.title || a.filename || ''));
      if (sort === 'chunks_desc') return Number(b.chunk_count || 0) - Number(a.chunk_count || 0);
      if (sort === 'chunks_asc') return Number(a.chunk_count || 0) - Number(b.chunk_count || 0);
      if (sort === 'status_asc') return String(a.status || '').localeCompare(String(b.status || ''));
      return byUploadedAtDesc(a, b);
    });

    return items;
  }

  function renderList(root) {
    const listEl = root.querySelector('[data-docs-list]');
    const summaryEl = root.querySelector('[data-docs-summary]');
    const items = filteredDocs(root);
    const all = root._docs || [];

    const ready = all.filter(function (x) { return String(x.status || '') === 'ready'; }).length;
    const failed = all.filter(function (x) { return String(x.status || '') === 'failed'; }).length;

    summaryEl.innerHTML =
      '<span class="muted">Total: ' + esc(String(all.length)) + '</span>' +
      ' · <span class="muted">Ready: ' + esc(String(ready)) + '</span>' +
      ' · <span class="muted">Failed: ' + esc(String(failed)) + '</span>' +
      ' · <span class="muted">Shown: ' + esc(String(items.length)) + '</span>';

    if (!items.length) {
      listEl.innerHTML = '<div class="card"><div class="muted">No matching documents.</div></div>';
      return;
    }

    listEl.innerHTML = '' +
      '<div class="card" style="padding:0; overflow:auto">' +
        '<table style="width:100%; border-collapse:collapse; font-size:13px">' +
          '<thead>' +
            '<tr>' +
              '<th style="text-align:left; padding:10px; border-bottom:1px solid rgba(255,255,255,0.08)">Title</th>' +
              '<th style="text-align:left; padding:10px; border-bottom:1px solid rgba(255,255,255,0.08)">Status</th>' +
              '<th style="text-align:left; padding:10px; border-bottom:1px solid rgba(255,255,255,0.08)">Chunks</th>' +
              '<th style="text-align:left; padding:10px; border-bottom:1px solid rgba(255,255,255,0.08)">Uploaded</th>' +
              '<th style="text-align:left; padding:10px; border-bottom:1px solid rgba(255,255,255,0.08)">File</th>' +
              '<th style="text-align:left; padding:10px; border-bottom:1px solid rgba(255,255,255,0.08)">Actions</th>' +
            '</tr>' +
          '</thead>' +
          '<tbody>' +
            items.map(function (it) {
              const docId = esc(it.doc_id);
              const title = esc(it.title || it.filename || it.doc_id);
              const file = esc(it.filename || '');
              const status = esc(it.status || '');
              const uploaded = esc(it.uploaded_at || '');
              const chunks = esc(fmtNum(it.chunk_count));
              const err = it.error ? '<div class="muted" style="color:#ff8a8a; margin-top:4px">' + esc(it.error) + '</div>' : '';
              return '' +
                '<tr>' +
                  '<td style="padding:10px; border-bottom:1px solid rgba(255,255,255,0.06); vertical-align:top">' +
                    '<div><strong>' + title + '</strong></div>' +
                    '<div class="muted">doc_id: ' + docId + '</div>' +
                    '<div class="muted">active: ' + esc(fmtBool(!!it.active)) + '</div>' +
                    err +
                  '</td>' +
                  '<td style="padding:10px; border-bottom:1px solid rgba(255,255,255,0.06); vertical-align:top">' + status + '</td>' +
                  '<td style="padding:10px; border-bottom:1px solid rgba(255,255,255,0.06); vertical-align:top">' + chunks + '</td>' +
                  '<td style="padding:10px; border-bottom:1px solid rgba(255,255,255,0.06); vertical-align:top">' + uploaded + '</td>' +
                  '<td style="padding:10px; border-bottom:1px solid rgba(255,255,255,0.06); vertical-align:top">' + file + '</td>' +
                  '<td style="padding:10px; border-bottom:1px solid rgba(255,255,255,0.06); vertical-align:top">' +
                    '<div style="display:flex; gap:8px; flex-wrap:wrap">' +
                      '<button type="button" data-doc-detail="' + docId + '">Details</button>' +
                      '<button type="button" data-doc-delete="' + docId + '">Delete</button>' +
                    '</div>' +
                    '<div data-doc-detail-box="' + docId + '" style="display:none; margin-top:10px"></div>' +
                  '</td>' +
                '</tr>';
            }).join('') +
          '</tbody>' +
        '</table>' +
      '</div>';

    listEl.querySelectorAll('[data-doc-detail]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        showDetail(root, btn.getAttribute('data-doc-detail'));
      });
    });
    listEl.querySelectorAll('[data-doc-delete]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        deleteDoc(root, btn.getAttribute('data-doc-delete'));
      });
    });
  }

  async function loadDocs(root) {
    const statusEl = root.querySelector('[data-docs-status]');
    statusEl.textContent = 'Loading documents...';
    try {
      const data = await api('/api/docs');
      root._docs = ((data && data.items) || []).slice();
      statusEl.textContent = '';
      renderList(root);
    } catch (e) {
      statusEl.textContent = 'Failed to load documents: ' + e.message;
      root.querySelector('[data-docs-summary]').innerHTML = '';
      root.querySelector('[data-docs-list]').innerHTML = '';
    }
  }

  async function showDetail(root, docId) {
    const box = root.querySelector('[data-doc-detail-box="' + CSS.escape(docId) + '"]');
    const statusEl = root.querySelector('[data-docs-status]');
    if (!box) return;

    if (box.style.display === 'block') {
      box.style.display = 'none';
      box.innerHTML = '';
      return;
    }

    statusEl.textContent = 'Loading details for ' + docId + '...';
    try {
      const out = await api('/api/docs/' + encodeURIComponent(docId));
      const manifest = out.manifest || {};
      const status = out.status || {};
      const preview = out.extract_preview || '';
      box.innerHTML = '' +
        '<div class="card" style="background:rgba(255,255,255,0.02)">' +
          '<div><strong>Manifest</strong></div>' +
          '<pre style="white-space:pre-wrap; overflow:auto;">' + esc(JSON.stringify(manifest, null, 2)) + '</pre>' +
          '<div><strong>Status</strong></div>' +
          '<pre style="white-space:pre-wrap; overflow:auto;">' + esc(JSON.stringify(status, null, 2)) + '</pre>' +
          '<div><strong>Extract preview</strong></div>' +
          '<pre style="white-space:pre-wrap; overflow:auto;">' + esc(preview || '(empty)') + '</pre>' +
        '</div>';
      box.style.display = 'block';
      statusEl.textContent = '';
    } catch (e) {
      statusEl.textContent = 'Failed to load details: ' + e.message;
    }
  }

  async function deleteDoc(root, docId) {
    const statusEl = root.querySelector('[data-docs-status]');
    if (!window.confirm('Delete document ' + docId + '?')) return;
    statusEl.textContent = 'Deleting ' + docId + '...';
    try {
      await api('/api/docs/' + encodeURIComponent(docId), { method: 'DELETE' });
      statusEl.textContent = 'Deleted: ' + docId;
      await loadDocs(root);
    } catch (e) {
      statusEl.textContent = 'Delete failed: ' + e.message;
    }
  }

  async function handleUpload(root, ev) {
    ev.preventDefault();
    const form = ev.currentTarget;
    const fileEl = form.querySelector('input[type="file"]');
    const titleEl = form.querySelector('input[name="title"]');
    const statusEl = root.querySelector('[data-docs-status]');

    if (!fileEl.files || !fileEl.files.length) {
      statusEl.textContent = 'Choose a PDF or ZIP first.';
      return;
    }

    const fd = new FormData();
    fd.append('file', fileEl.files[0]);
    fd.append('title', titleEl.value || '');

    statusEl.textContent = 'Uploading and ingesting...';
    try {
      const out = await api('/api/docs/upload', { method: 'POST', body: fd });
      if (out && out.mode === 'zip') {
        statusEl.textContent =
          'ZIP done: imported ' + String(out.count_ok || 0) +
          ', failed ' + String(out.count_failed || 0) +
          ', skipped ' + String(out.count_skipped || 0);
      } else {
        statusEl.textContent = 'Done: ' + (out.doc_id || '(unknown doc_id)');
      }
      form.reset();
      await loadDocs(root);
    } catch (e) {
      statusEl.textContent = 'Upload failed: ' + e.message;
    }
  }

  function render(root) {
    root.innerHTML = '' +
      '<div class="page documents-page">' +
        '<h2>Documents</h2>' +
        '<div class="card" style="margin-bottom:16px">' +
          '<form data-docs-upload>' +
            '<div style="margin-bottom:8px"><input type="file" accept="application/pdf,.pdf,application/zip,.zip" /></div>' +
            '<div style="margin-bottom:8px"><input type="text" name="title" placeholder="Optional title (used for single PDF or single-PDF ZIP)" style="width:100%" /></div>' +
            '<div class="muted" style="margin-bottom:8px">You can upload one PDF or one ZIP containing multiple PDFs.</div>' +
            '<div><button type="submit">Upload file</button></div>' +
          '</form>' +
        '</div>' +
        '<div class="card" style="margin-bottom:16px">' +
          '<div style="display:flex; gap:12px; flex-wrap:wrap; align-items:center">' +
            '<input data-docs-filter type="text" placeholder="Filter documents..." style="flex:1; min-width:260px" />' +
            '<select data-docs-sort>' +
              '<option value="uploaded_desc">Newest first</option>' +
              '<option value="title_asc">Title A–Z</option>' +
              '<option value="title_desc">Title Z–A</option>' +
              '<option value="chunks_desc">Most chunks</option>' +
              '<option value="chunks_asc">Fewest chunks</option>' +
              '<option value="status_asc">Status</option>' +
            '</select>' +
          '</div>' +
          '<div data-docs-summary style="margin-top:10px"></div>' +
        '</div>' +
        '<div data-docs-status class="muted" style="margin-bottom:12px"></div>' +
        '<div data-docs-list></div>' +
      '</div>';

    root.querySelector('[data-docs-upload]').addEventListener('submit', handleUpload.bind(null, root));
    root.querySelector('[data-docs-filter]').addEventListener('input', function () { renderList(root); });
    root.querySelector('[data-docs-sort]').addEventListener('change', function () { renderList(root); });
    loadDocs(root);
  }

  window.DocumentsPage = function DocumentsPage() {
    const ref = React.useRef(null);
    React.useEffect(function () {
      if (ref.current) render(ref.current);
    }, []);
    return h("div", { ref: ref });
  };
})();
