(function () {
  const STYLE_ID = 'taks-logs-viewer-style';

  function ensureStyle() {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = `
      .taks-logs-root { display:flex; gap:16px; height:calc(100vh - 160px); min-height:540px; background:transparent; color:#111827; }
      .taks-logs-pane { background:#f7f9fc; color:#111827; border:1px solid #d7dee8; border-radius:12px; overflow:hidden; display:flex; flex-direction:column; box-shadow:0 1px 2px rgba(16,24,40,.04); }
      .taks-logs-nav { width:360px; min-width:320px; }
      .taks-logs-view { flex:1; min-width:0; }
      .taks-logs-toolbar { display:flex; align-items:center; gap:8px; padding:12px 14px; border-bottom:1px solid #e6ebf2; flex-wrap:wrap; background:#eef3f8; color:#111827; }
      .taks-logs-toolbar h2 { margin:0; font-size:16px; color:#111827; }
      .taks-logs-spacer { flex:1; }
      .taks-logs-btn { border:1px solid #c8d2df; background:#fff; color:#111827; border-radius:8px; padding:6px 10px; cursor:pointer; }
      .taks-logs-btn:hover { background:#f7f9fc; }
      .taks-logs-btn[disabled] { opacity:.5; cursor:default; }
      .taks-logs-btn.active { background:#e7f0ff; border-color:#b7d1ff; color:#0f3d91; }
      .taks-logs-breadcrumbs { display:flex; gap:6px; flex-wrap:wrap; font-size:13px; color:#475467; }
      .taks-logs-breadcrumbs a { color:#175cd3; text-decoration:none; }
      .taks-logs-breadcrumbs a:hover { text-decoration:underline; }
      .taks-logs-list { overflow:auto; background:#fdfefe; }
      .taks-logs-item { display:flex; align-items:center; gap:8px; padding:10px 14px; border-bottom:1px solid #eef2f6; cursor:pointer; color:#111827; }
      .taks-logs-item:hover { background:#f5f9ff; }
      .taks-logs-item.active { background:#eaf2ff; }
      .taks-logs-item-name { flex:1; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:#111827; font-size:13px; }
      .taks-logs-item-meta { color:#667085; font-size:12px; }
      .taks-logs-empty, .taks-logs-error, .taks-logs-loading { padding:14px; color:#475467; }
      .taks-logs-error { color:#b42318; }
      .taks-logs-pre-wrap { overflow:auto; margin:0; padding:14px; font:12px/1.45 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; white-space:pre-wrap; word-break:break-word; background:#f8fafc; color:#0f172a; height:100%; }
      .taks-logs-meta { font-size:12px; color:#667085; }
      .taks-logs-title { font:600 14px/1.2 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; max-width:48vw; color:#0f172a; }
    `;
    document.head.appendChild(style);
  }

  function el(tag, attrs) {
    const node = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach((k) => {
        const v = attrs[k];
        if (k === 'className') node.className = v;
        else if (k === 'text') node.textContent = v;
        else if (k === 'html') node.innerHTML = v;
        else if (k.startsWith('on') && typeof v === 'function') node.addEventListener(k.slice(2).toLowerCase(), v);
        else if (v !== undefined && v !== null) node.setAttribute(k, v);
      });
    }
    for (let i = 2; i < arguments.length; i += 1) {
      const child = arguments[i];
      if (child === null || child === undefined) continue;
      if (Array.isArray(child)) child.forEach((c) => c && node.appendChild(c));
      else if (typeof child === 'string') node.appendChild(document.createTextNode(child));
      else node.appendChild(child);
    }
    return node;
  }

  function fmtSize(bytes) {
    if (bytes === 0) return '0 B';
    if (!bytes && bytes !== 0) return '';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let value = bytes;
    let idx = 0;
    while (value >= 1024 && idx < units.length - 1) {
      value /= 1024;
      idx += 1;
    }
    return `${value >= 10 || idx === 0 ? value.toFixed(idx === 0 ? 0 : 0) : value.toFixed(1)} ${units[idx]}`;
  }

  function fmtStamp(iso) {
    if (!iso) return '';
    try { return new Date(iso).toLocaleString(); }
    catch (_) { return iso; }
  }

  function makeBreadcrumbs(path, onOpen) {
    const wrap = el('div', { className: 'taks-logs-breadcrumbs' });
    const parts = path === '/' ? [] : path.replace(/^\//, '').split('/');
    let accum = '';

    const rootLink = el('a', { href: '#', text: '/var/log', onclick: function (ev) { ev.preventDefault(); onOpen('/'); } });
    wrap.appendChild(rootLink);

    parts.forEach((part) => {
      accum += '/' + part;
      wrap.appendChild(el('span', { text: '/' }));
      wrap.appendChild(el('a', {
        href: '#',
        text: part,
        onclick: function (ev) { ev.preventDefault(); onOpen(accum); }
      }));
    });
    return wrap;
  }

  function LogsViewer(rootEl, opts) {
    ensureStyle();
    this.rootEl = rootEl;
    this.opts = opts || {};
    this.state = {
      dirPath: '/',
      dirEntries: [],
      currentFile: null,
      fileMode: 'tail',
      fileData: null,
      loadingList: false,
      loadingFile: false,
      listError: null,
      fileError: null
    };
    this.render();
    this.loadDir('/');
  }

  LogsViewer.prototype.apiGet = async function (url) {
    const res = await fetch(url, { credentials: 'same-origin' });
    let body = null;
    try { body = await res.json(); } catch (_) { body = null; }
    if (!res.ok) {
      const detail = body && body.detail ? body.detail : `${res.status} ${res.statusText}`;
      throw new Error(detail);
    }
    return body;
  };

  LogsViewer.prototype.loadDir = async function (path) {
    this.state.loadingList = true;
    this.state.listError = null;
    this.state.dirPath = path || '/';
    this.render();
    try {
      const data = await this.apiGet(`/api/logs/list?path=${encodeURIComponent(this.state.dirPath)}`);
      this.state.dirEntries = data.entries || [];
      this.state.dirPath = data.path || '/';
    } catch (err) {
      this.state.dirEntries = [];
      this.state.listError = String(err.message || err);
    } finally {
      this.state.loadingList = false;
      this.render();
    }
  };

  LogsViewer.prototype.loadFile = async function (path, mode) {
    this.state.loadingFile = true;
    this.state.fileError = null;
    this.state.currentFile = path;
    this.state.fileMode = mode || this.state.fileMode || 'tail';
    this.render();
    try {
      const qs = new URLSearchParams({ path: this.state.currentFile, mode: this.state.fileMode });
      if (this.state.fileMode === 'tail') qs.set('lines', '1000');
      const data = await this.apiGet(`/api/logs/read?${qs.toString()}`);
      this.state.fileData = data;
    } catch (err) {
      this.state.fileData = null;
      this.state.fileError = String(err.message || err);
    } finally {
      this.state.loadingFile = false;
      this.render();
    }
  };

  LogsViewer.prototype.renderNav = function () {
    const self = this;
    const state = this.state;
    const list = el('div', { className: 'taks-logs-list' });

    if (state.loadingList) list.appendChild(el('div', { className: 'taks-logs-loading', text: 'Loading directory…' }));
    else if (state.listError) list.appendChild(el('div', { className: 'taks-logs-error', text: state.listError }));
    else if (!state.dirEntries.length) list.appendChild(el('div', { className: 'taks-logs-empty', text: 'No visible files in this directory.' }));
    else {
      state.dirEntries.forEach((entry) => {
        const row = el('div', {
          className: `taks-logs-item${state.currentFile === entry.rel_path ? ' active' : ''}`,
          onclick: function () {
            if (entry.type === 'dir') {
              self.state.currentFile = null;
              self.state.fileData = null;
              self.state.fileError = null;
              self.loadDir(entry.rel_path);
            } else {
              self.loadFile(entry.rel_path, 'tail');
            }
          }
        },
          el('div', { text: entry.type === 'dir' ? '📁' : '📄' }),
          el('div', { className: 'taks-logs-item-name', text: entry.name }),
          el('div', { className: 'taks-logs-item-meta', text: entry.type === 'file' ? fmtSize(entry.size) : '' })
        );
        list.appendChild(row);
      });
    }

    return el('div', { className: 'taks-logs-pane taks-logs-nav' },
      el('div', { className: 'taks-logs-toolbar' },
        el('h2', { text: 'Log browser' }),
        el('div', { className: 'taks-logs-spacer' }),
        el('button', { className: 'taks-logs-btn', onclick: function () { self.loadDir(state.dirPath); }, type: 'button' }, 'Refresh')
      ),
      el('div', { className: 'taks-logs-loading' }, makeBreadcrumbs(state.dirPath, function (path) { self.loadDir(path); })),
      list
    );
  };

  LogsViewer.prototype.renderViewer = function () {
    const self = this;
    const state = this.state;
    const body = el('div', { style: 'flex:1; min-height:0; display:flex; flex-direction:column;' });

    if (!state.currentFile) {
      body.appendChild(el('div', { className: 'taks-logs-empty', text: 'Choose a log file on the left.' }));
    } else if (state.loadingFile) {
      body.appendChild(el('div', { className: 'taks-logs-loading', text: 'Loading file…' }));
    } else if (state.fileError) {
      body.appendChild(el('div', { className: 'taks-logs-error', text: state.fileError }));
    } else if (state.fileData) {
      const meta = state.fileData;
      body.appendChild(el('pre', { className: 'taks-logs-pre-wrap', text: meta.content || '' }));
    }

    return el('div', { className: 'taks-logs-pane taks-logs-view' },
      el('div', { className: 'taks-logs-toolbar' },
        el('div', { className: 'taks-logs-title', text: state.currentFile || 'No file selected' }),
        el('div', { className: 'taks-logs-spacer' }),
        el('button', {
          type: 'button',
          className: `taks-logs-btn${state.fileMode === 'tail' ? ' active' : ''}`,
          disabled: !state.currentFile,
          onclick: function () { if (state.currentFile) self.loadFile(state.currentFile, 'tail'); }
        }, 'Tail 1000'),
        el('button', {
          type: 'button',
          className: `taks-logs-btn${state.fileMode === 'full' ? ' active' : ''}`,
          disabled: !state.currentFile,
          onclick: function () { if (state.currentFile) self.loadFile(state.currentFile, 'full'); }
        }, 'Full file'),
        el('button', {
          type: 'button',
          className: 'taks-logs-btn',
          disabled: !state.currentFile,
          onclick: function () { if (state.currentFile) self.loadFile(state.currentFile, state.fileMode); }
        }, 'Refresh')
      ),
      el('div', { className: 'taks-logs-toolbar taks-logs-meta' },
        state.fileData ? `${fmtSize(state.fileData.size)} • ${fmtStamp(state.fileData.mtime)} • ${state.fileData.mode === 'tail' ? 'showing tail' : 'showing full file'}` : 'Read-only viewer for /var/log'
      ),
      body
    );
  };

  LogsViewer.prototype.render = function () {
    this.rootEl.innerHTML = '';
    this.rootEl.appendChild(el('div', { className: 'taks-logs-root' }, this.renderNav(), this.renderViewer()));
  };


  function LogsViewerView() {
    const rootRef = React.useRef(null);

    React.useEffect(function () {
      if (!rootRef.current) return;
      rootRef.current.innerHTML = '';
      if (!window.TaksLogsViewer || typeof window.TaksLogsViewer.mount !== 'function') return;
      window.TaksLogsViewer.mount(rootRef.current, {});
      return function () {
        if (rootRef.current) rootRef.current.innerHTML = '';
      };
    }, []);

    return React.createElement('div', {
      style: { height: 'calc(100vh - 140px)', minHeight: '540px' },
      ref: rootRef
    });
  }

  window.LogsViewerView = LogsViewerView;

  window.TaksLogsViewer = {
    mount: function (rootEl, opts) {
      return new LogsViewer(rootEl, opts || {});
    }
  };
})();
