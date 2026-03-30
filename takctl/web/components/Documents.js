(function () {
  'use strict';

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

  async function loadDocs(root) {
    const statusEl = root.querySelector('[data-docs-status]');
    const listEl = root.querySelector('[data-docs-list]');
    statusEl.textContent = 'Loading documents...';
    try {
      const data = await api('/api/docs');
      const items = (data && data.items) || [];
      if (!items.length) {
        listEl.innerHTML = '<div class="card"><div class="muted">No uploaded documents.</div></div>';
      } else {
        listEl.innerHTML = items.map(function (it) {
          return '' +
            '<div class="card" style="margin-bottom:12px">' +
              '<div><strong>' + esc(it.title || it.filename || it.doc_id) + '</strong></div>' +
              '<div class="muted">doc_id: ' + esc(it.doc_id) + '</div>' +
              '<div class="muted">file: ' + esc(it.filename || '') + '</div>' +
              '<div class="muted">status: ' + esc(it.status || '') + '</div>' +
              '<div class="muted">active: ' + esc(String(!!it.active)) + '</div>' +
              '<div class="muted">uploaded_at: ' + esc(it.uploaded_at || '') + '</div>' +
              '<div class="muted">chunks: ' + esc(it.chunk_count == null ? '' : String(it.chunk_count)) + '</div>' +
              (it.error ? '<div class="muted" style="color:#ff8a8a">error: ' + esc(it.error) + '</div>' : '') +
              '<div style="margin-top:8px; display:flex; gap:8px; flex-wrap:wrap">' +
                '<button type="button" data-doc-detail="' + esc(it.doc_id) + '">Details</button>' +
                '<button type="button" data-doc-delete="' + esc(it.doc_id) + '">Delete</button>' +
              '</div>' +
              '<div data-doc-detail-box="' + esc(it.doc_id) + '" style="display:none; margin-top:10px"></div>' +
            '</div>';
        }).join('');
      }
      statusEl.textContent = '';

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
    } catch (e) {
      statusEl.textContent = 'Failed to load documents: ' + e.message;
      listEl.innerHTML = '';
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
      statusEl.textContent = 'Choose a PDF first.';
      return;
    }

    const fd = new FormData();
    fd.append('file', fileEl.files[0]);
    fd.append('title', titleEl.value || '');

    statusEl.textContent = 'Uploading and ingesting...';
    try {
      const out = await api('/api/docs/upload', { method: 'POST', body: fd });
      statusEl.textContent = 'Done: ' + (out.doc_id || '(unknown doc_id)');
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
            '<div style="margin-bottom:8px"><input type="file" accept="application/pdf,.pdf" /></div>' +
            '<div style="margin-bottom:8px"><input type="text" name="title" placeholder="Optional title" style="width:100%" /></div>' +
            '<div><button type="submit">Upload PDF</button></div>' +
          '</form>' +
        '</div>' +
        '<div data-docs-status class="muted" style="margin-bottom:12px"></div>' +
        '<div data-docs-list></div>' +
      '</div>';

    root.querySelector('[data-docs-upload]').addEventListener('submit', handleUpload.bind(null, root));
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