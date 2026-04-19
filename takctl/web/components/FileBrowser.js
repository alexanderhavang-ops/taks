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

  function humanBytes(v) {
    const n = Number(v);
    if (!isFinite(n) || n < 0) return '';
    if (n < 1024) return String(n) + ' B';
    if (n < 1024 * 1024) return (n / 1024).toFixed(1).replace(/\.0$/, '') + ' KB';
    if (n < 1024 * 1024 * 1024) return (n / (1024 * 1024)).toFixed(1).replace(/\.0$/, '') + ' MB';
    return (n / (1024 * 1024 * 1024)).toFixed(1).replace(/\.0$/, '') + ' GB';
  }

  function fmtWhen(s) {
    const raw = String(s || '').trim();
    if (!raw) return '';
    try {
      return new Date(raw).toLocaleString();
    } catch (_) {
      return raw;
    }
  }

  function parentPath(p) {
    const raw = String(p || '').trim().replace(/^\/+|\/+$/g, '');
    if (!raw) return '';
    const parts = raw.split('/');
    parts.pop();
    return parts.join('/');
  }

  function currentRoot(root) {
    const roots = Array.isArray(root._roots) ? root._roots : [];
    const key = String(root._rootKey || '');
    return roots.find(function (x) { return String(x.key || '') === key; }) || null;
  }

  function setStatus(root, msg, cls) {
    root._status = String(msg || '');
    root._statusClass = String(cls || 'muted');
    render(root);
  }

  async function loadRoots(root) {
    setStatus(root, 'Loading roots...', 'muted');
    try {
      const data = await api('/api/files/roots', { credentials: 'include' });
      root._roots = Array.isArray(data.roots) ? data.roots.slice() : [];
      if (!root._rootKey && root._roots.length) {
        root._rootKey = String(root._roots[0].key || '');
      }
      await loadList(root, '');
    } catch (e) {
      setStatus(root, 'Failed to load roots: ' + e.message, 'err');
    }
  }

  async function loadList(root, nextPath) {
    if (typeof nextPath === 'string') root._path = nextPath;
    const rootKey = String(root._rootKey || '');
    if (!rootKey) {
      root._entries = [];
      render(root);
      return;
    }

    setStatus(root, 'Loading...', 'muted');

    try {
      const data = await api(
        '/api/files/list?root=' + encodeURIComponent(rootKey) +
        '&path=' + encodeURIComponent(String(root._path || '')),
        { credentials: 'include' }
      );
      root._entries = Array.isArray(data.entries) ? data.entries.slice() : [];
      root._path = String(data.path || '');
      root._rootInfo = data.root || {};
      root._status = '';
      root._statusClass = 'muted';
      render(root);
    } catch (e) {
      setStatus(root, 'Failed to load directory: ' + e.message, 'err');
    }
  }

  async function doUpload(root, file) {
    if (!file) return;
    const rootKey = String(root._rootKey || '');
    const curPath = String(root._path || '');

    setStatus(root, 'Uploading ' + file.name + '...', 'muted');

    try {
      const fd = new FormData();
      fd.append('file', file);

      await api(
        '/api/files/upload?root=' + encodeURIComponent(rootKey) +
        '&path=' + encodeURIComponent(curPath),
        { method: 'POST', body: fd, credentials: 'include' }
      );

      setStatus(root, 'Uploaded: ' + file.name, 'ok');
      await loadList(root, curPath);
    } catch (e) {
      setStatus(root, 'Upload failed: ' + e.message, 'err');
    }
  }

  async function doRename(root, entryPath, oldName) {
    const next = window.prompt('New name', String(oldName || ''));
    if (next == null) return;
    const newName = String(next || '').trim();
    if (!newName || newName === String(oldName || '')) return;

    setStatus(root, 'Renaming...', 'muted');

    try {
      await api(
        '/api/files/rename?root=' + encodeURIComponent(String(root._rootKey || '')) +
        '&path=' + encodeURIComponent(String(entryPath || '')) +
        '&new_name=' + encodeURIComponent(newName),
        { method: 'POST', credentials: 'include' }
      );
      setStatus(root, 'Renamed to ' + newName, 'ok');
      await loadList(root, String(root._path || ''));
    } catch (e) {
      setStatus(root, 'Rename failed: ' + e.message, 'err');
    }
  }

  async function doDelete(root, entryPath, entryName, entryType) {
    const kind = String(entryType || '') === 'dir' ? 'directory' : 'file';
    const msg = kind === 'directory'
      ? ('Delete directory ' + entryName + ' and everything under it?')
      : ('Delete file ' + entryName + '?');

    if (!window.confirm(msg)) return;

    setStatus(root, 'Deleting...', 'muted');

    try {
      await api(
        '/api/files/item?root=' + encodeURIComponent(String(root._rootKey || '')) +
        '&path=' + encodeURIComponent(String(entryPath || '')),
        { method: 'DELETE', credentials: 'include' }
      );
      setStatus(root, 'Deleted: ' + entryName, 'ok');
      await loadList(root, String(root._path || ''));
    } catch (e) {
      setStatus(root, 'Delete failed: ' + e.message, 'err');
    }
  }

  function downloadUrl(rootKey, entryPath) {
    return '/api/files/download?root=' + encodeURIComponent(String(rootKey || '')) +
      '&path=' + encodeURIComponent(String(entryPath || ''));
  }

  function render(root) {
    const roots = Array.isArray(root._roots) ? root._roots : [];
    const entries = Array.isArray(root._entries) ? root._entries : [];
    const rootInfo = root._rootInfo || {};
    const activeRoot = currentRoot(root);
    const activeTitle = activeRoot ? String(activeRoot.title || activeRoot.key || '') : '';
    const activeKey = String(root._rootKey || '');
    const curPath = String(root._path || '');
    const status = String(root._status || '');
    const statusClass = String(root._statusClass || 'muted');
    const actualPath = String((rootInfo && rootInfo.resolved_path) || '');

    const pathParts = curPath ? curPath.split('/') : [];
    let walk = '';
    const crumbHtml = [
      '<button type="button" class="btn" data-nav-path="">'
        + esc(activeTitle || 'Root') +
      '</button>'
    ];

    pathParts.forEach(function (part) {
      walk = walk ? (walk + '/' + part) : part;
      crumbHtml.push(
        '<span class="muted">/</span>' +
        '<button type="button" class="btn" data-nav-path="' + esc(walk) + '">' +
          esc(part) +
        '</button>'
      );
    });

    const rowsHtml = entries.map(function (it) {
      const isDir = String(it.type || '') === 'dir';
      const path = String(it.path || '');
      const name = String(it.name || '');
      const size = isDir ? '—' : humanBytes(it.bytes);
      const when = fmtWhen(it.modified_iso);
      const openCtl = isDir
        ? '<button type="button" class="btn" data-open-path="' + esc(path) + '">Open</button>'
        : '<a class="btn" href="' + esc(downloadUrl(activeKey, path)) + '" download>Download</a>';
      const nameCtl = isDir
        ? '<button type="button" class="btn" data-open-path="' + esc(path) + '">' + esc(name) + '</button>'
        : '<a href="' + esc(downloadUrl(activeKey, path)) + '" download>' + esc(name) + '</a>';

      return '' +
        '<tr>' +
          '<td style="padding:10px; border-bottom:1px solid rgba(255,255,255,0.06); vertical-align:top">' +
            '<div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap">' +
              '<span class="muted">' + (isDir ? 'dir' : 'file') + '</span>' +
              nameCtl +
            '</div>' +
          '</td>' +
          '<td style="padding:10px; border-bottom:1px solid rgba(255,255,255,0.06); vertical-align:top">' + esc(size) + '</td>' +
          '<td style="padding:10px; border-bottom:1px solid rgba(255,255,255,0.06); vertical-align:top">' + esc(when) + '</td>' +
          '<td style="padding:10px; border-bottom:1px solid rgba(255,255,255,0.06); vertical-align:top">' +
            '<div style="display:flex; gap:8px; flex-wrap:wrap">' +
              openCtl +
              '<button type="button" class="btn" data-rename-path="' + esc(path) + '" data-rename-name="' + esc(name) + '">Rename</button>' +
              '<button type="button" class="btn btn--danger" data-delete-path="' + esc(path) + '" data-delete-name="' + esc(name) + '" data-delete-type="' + esc(it.type || '') + '">Delete</button>' +
            '</div>' +
          '</td>' +
        '</tr>';
    }).join('');

    root.innerHTML = '' +
      '<div class="page file-browser-page">' +
        '<h2>File Browser</h2>' +
        '<div style="display:grid; grid-template-columns:240px minmax(0,1fr); gap:16px">' +
          '<div class="card">' +
            '<div class="card__title">Roots</div>' +
            '<div style="display:grid; gap:8px; margin-top:10px">' +
              roots.map(function (r) {
                const key = String(r.key || '');
                const title = String(r.title || key);
                const active = key === activeKey;
                return '' +
                  '<button type="button" class="' + (active ? 'tab tab-active' : 'tab') + '" data-root-key="' + esc(key) + '">' +
                    esc(title) +
                  '</button>';
              }).join('') +
            '</div>' +
          '</div>' +
          '<div style="min-width:0">' +
            '<div class="card" style="margin-bottom:16px">' +
              '<div style="display:flex; gap:12px; justify-content:space-between; align-items:flex-start; flex-wrap:wrap">' +
                '<div style="min-width:0; flex:1 1 auto">' +
                  '<div class="card__title">' + esc(activeTitle || 'Files') + '</div>' +
                  '<div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-top:10px">' +
                    crumbHtml.join('') +
                    (curPath
                      ? '<button type="button" class="btn" data-nav-up="1">Up</button>'
                      : '') +
                  '</div>' +
                  (actualPath
                    ? '<div class="muted" style="margin-top:8px; word-break:break-all">' + esc(actualPath) + '</div>'
                    : '') +
                '</div>' +
                '<div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap">' +
                  '<button type="button" class="btn" data-upload-btn="1">Upload</button>' +
                  '<button type="button" class="btn" data-refresh-btn="1">Refresh</button>' +
                  '<input type="file" data-upload-input="1" style="display:none" />' +
                '</div>' +
              '</div>' +
            '</div>' +
            '<div class="' + esc(statusClass) + '" style="margin-bottom:12px">' + esc(status) + '</div>' +
            (!entries.length
              ? '<div class="card"><div class="muted">Empty directory.</div></div>'
              : '<div class="card" style="padding:0; overflow:auto">' +
                  '<table style="width:100%; border-collapse:collapse; font-size:13px">' +
                    '<thead>' +
                      '<tr>' +
                        '<th style="text-align:left; padding:10px; border-bottom:1px solid rgba(255,255,255,0.08)">Name</th>' +
                        '<th style="text-align:left; padding:10px; border-bottom:1px solid rgba(255,255,255,0.08)">Size</th>' +
                        '<th style="text-align:left; padding:10px; border-bottom:1px solid rgba(255,255,255,0.08)">Modified</th>' +
                        '<th style="text-align:left; padding:10px; border-bottom:1px solid rgba(255,255,255,0.08)">Actions</th>' +
                      '</tr>' +
                    '</thead>' +
                    '<tbody>' + rowsHtml + '</tbody>' +
                  '</table>' +
                '</div>') +
          '</div>' +
        '</div>' +
      '</div>';

    root.querySelectorAll('[data-root-key]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        root._rootKey = String(btn.getAttribute('data-root-key') || '');
        root._path = '';
        root._entries = [];
        root._rootInfo = {};
        loadList(root, '');
      });
    });

    root.querySelectorAll('[data-nav-path]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        loadList(root, String(btn.getAttribute('data-nav-path') || ''));
      });
    });

    root.querySelectorAll('[data-open-path]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        loadList(root, String(btn.getAttribute('data-open-path') || ''));
      });
    });

    const upBtn = root.querySelector('[data-nav-up]');
    if (upBtn) {
      upBtn.addEventListener('click', function () {
        loadList(root, parentPath(String(root._path || '')));
      });
    }

    root.querySelectorAll('[data-rename-path]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        doRename(
          root,
          String(btn.getAttribute('data-rename-path') || ''),
          String(btn.getAttribute('data-rename-name') || '')
        );
      });
    });

    root.querySelectorAll('[data-delete-path]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        doDelete(
          root,
          String(btn.getAttribute('data-delete-path') || ''),
          String(btn.getAttribute('data-delete-name') || ''),
          String(btn.getAttribute('data-delete-type') || '')
        );
      });
    });

    const uploadBtn = root.querySelector('[data-upload-btn]');
    const uploadInput = root.querySelector('[data-upload-input]');
    if (uploadBtn && uploadInput) {
      uploadBtn.addEventListener('click', function () {
        uploadInput.click();
      });
      uploadInput.addEventListener('change', function () {
        const f = uploadInput.files && uploadInput.files[0];
        uploadInput.value = '';
        if (f) doUpload(root, f);
      });
    }

    const refreshBtn = root.querySelector('[data-refresh-btn]');
    if (refreshBtn) {
      refreshBtn.addEventListener('click', function () {
        loadList(root, String(root._path || ''));
      });
    }
  }

  window.FileBrowserPage = function FileBrowserPage() {
    const ref = React.useRef(null);
    React.useEffect(function () {
      if (!ref.current) return;
      ref.current._roots = [];
      ref.current._entries = [];
      ref.current._rootInfo = {};
      ref.current._rootKey = 'documents';
      ref.current._path = '';
      ref.current._status = '';
      ref.current._statusClass = 'muted';
      render(ref.current);
      loadRoots(ref.current);
    }, []);
    return h('div', { ref: ref });
  };
})();
