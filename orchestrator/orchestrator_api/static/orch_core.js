(function(){
  function el(id){ return document.getElementById(id); }

  // ---------------- i18n ------------------------------------------------------
  const _i18n = {
    sv: {
      'nav.units': 'Enheter',
      'nav.nodes': 'Noder',
      'nav.settings': 'Inställningar',
      'nav.spawn_node': 'Skapa nod',
      'nav.logout': 'Logga ut',

      'units.title': 'Enheter',
      'units.summary': 'Enheter: {units} · Noder: {nodes} · DUC-enheter: {duc}',

      'units.create_root.title': 'Skapa rot-enhet',
      'units.create_root.help': 'Rot-enhet har ingen HC. Detta görs sällan.',
      'units.create_root.id': 'Enhets-ID',
      'units.create_root.name': 'Namn (valfritt)',
      'units.create_root.btn': 'Skapa',

      'units.add_duc': 'Lägg till DUC',
      'units.create_duc.title': 'Skapa DUC under {hc}',
      'units.create_duc.id': 'Enhets-ID (DUC)',
      'units.create_duc.name': 'Namn (valfritt)',
      'units.create_duc.btn': 'Skapa DUC',
      'units.close': 'Stäng',

      'units.delete': 'Ta bort',
      'units.delete.confirm': 'Ta bort enhet "{unit}"? (flyttas till karantän)',
      'units.nodes_assigned': 'Tilldelade noder',
      'units.nodes_none': 'Inga noder tilldelade.',

      'units.hc.none': 'rot — ingen HC',
      'units.hc.some': 'HC {hc}',

      'units.secondary.title': 'Övrigt',
      'units.untracked': 'Untracked noder',
      'units.orphaned': 'Orphaned',

      'common.refresh': 'Uppdatera',
      'common.loading': 'laddar…',

      'nodes.title': 'Noder',
      'nodes.active': 'Aktiva noder',
      'nodes.orphaned': 'Orphaned noder',
      'nodes.refresh': 'Uppdatera',
      'nodes.spawn': 'Skapa nod',
    },

    en: {
      'nav.units': 'Units',
      'nav.nodes': 'Nodes',
      'nav.settings': 'Settings',
      'nav.spawn_node': 'Spawn node',
      'nav.logout': 'Logout',

      'units.title': 'Units',
      'units.summary': 'Units: {units} · Nodes: {nodes} · Child units: {duc}',

      'units.create_root.title': 'Create root unit',
      'units.create_root.help': 'Root units have no parent. This is typically done once.',
      'units.create_root.id': 'Unit ID',
      'units.create_root.name': 'Name (optional)',
      'units.create_root.btn': 'Create',

      'units.add_duc': 'Add child',
      'units.create_duc.title': 'Create child under {hc}',
      'units.create_duc.id': 'Child unit ID',
      'units.create_duc.name': 'Name (optional)',
      'units.create_duc.btn': 'Create child',
      'units.close': 'Close',

      'units.delete': 'Delete',
      'units.delete.confirm': 'Delete unit "{unit}"? (moves to quarantine)',
      'units.nodes_assigned': 'Assigned nodes',
      'units.nodes_none': 'No nodes assigned.',

      'units.hc.none': 'root — no parent',
      'units.hc.some': 'Parent {hc}',

      'units.secondary.title': 'Secondary',
      'units.untracked': 'Untracked nodes',
      'units.orphaned': 'Orphaned',

      'common.refresh': 'Refresh',
      'common.loading': 'loading…',

      'nodes.title': 'Nodes',
      'nodes.active': 'Active nodes',
      'nodes.orphaned': 'Orphaned nodes',
      'nodes.refresh': 'Refresh',
      'nodes.spawn': 'Spawn node',
    }
  };

  function _getLang(){
    try{
      const v = (localStorage.getItem('taks_lang') || '').trim();
      if(v === 'en' || v === 'sv') return v;
    }catch(e){}
    return 'sv';
  }

  function setLang(lang){
    lang = (lang === 'en') ? 'en' : 'sv';
    try{ localStorage.setItem('taks_lang', lang); }catch(e){}
    window.CORE.lang = lang;
    // allow pages/router to re-render translations without forcing a full reload
    window.dispatchEvent(new Event('taks:lang'));
  }

  function t(key, vars){
    const lang = window.CORE?.lang || _getLang();
    const dict = _i18n[lang] || _i18n.sv;
    let s = dict[key] ?? key;
    if(vars && typeof vars === 'object'){
      for(const k of Object.keys(vars)){
        s = s.replaceAll(`{${k}}`, String(vars[k]));
      }
    }
    return s;
  }

  // --------------- HTTP + error helpers --------------------------------------
  function _errToString(e){
    if(!e) return 'Error';
    if(typeof e === 'string') return e;
    if(e instanceof Error) return e.message || String(e);
    return String(e);
  }

  function errorDetails(e){
    // Prefer CORE.api error shape: err.status + err.body (json or text)
    try{
      const status = (e && typeof e.status === 'number') ? e.status : null;
      const body = (e && Object.prototype.hasOwnProperty.call(e,'body')) ? e.body : null;

      let detail = '';
      if(body && typeof body === 'object' && body.detail) detail = String(body.detail);
      else if(typeof body === 'string') detail = body.trim();
      else detail = '';

      const msg = (e instanceof Error && e.message) ? e.message : _errToString(e);
      return { status, msg, detail };
    }catch(_){
      return { status: null, msg: _errToString(e), detail: '' };
    }
  }

  async function api(method, path, body){
    const opts = {
      method: method,
      credentials: 'same-origin',
      headers: {}
    };
    if(body !== undefined){
      opts.headers['content-type'] = 'application/json';
      opts.body = JSON.stringify(body);
    }

    let res;
    try{
      res = await fetch(path, opts);
    }catch(e){
      const err = new Error(`NETWORK: ${String(e)}`);
      err.status = 0;
      err.body = null;
      throw err;
    }

    const ct = (res.headers.get('content-type') || '').toLowerCase();
    const isJson = ct.includes('application/json');

    let text = '';
    let data = null;
    try{
      if(isJson) data = await res.json();
      else text = await res.text();
    }catch(e){
      // ignore parse errors; we'll use whatever we got
    }

    if(!res.ok){
      const detail =
        (data && typeof data === 'object' && data.detail) ? String(data.detail) :
        (text ? text.trim() : '');

      const msg = detail
        ? `HTTP ${res.status} ${res.statusText}: ${detail}`
        : `HTTP ${res.status} ${res.statusText}`;

      const err = new Error(msg);
      err.status = res.status;
      err.body = (data !== null ? data : text);
      throw err;
    }

    if(data !== null) return data;
    if(text) return { ok: true, text };
    return { ok: true };
  }

  async function loadStatus(){
    const target = el('nav_status');
    if(!target) return;
    try{
      const j = await api('GET','/api/v2/status');
      const ok = j && j.ok ? 'ok' : '??';
      const launch = (j && typeof j.launch_enabled === 'boolean') ? (j.launch_enabled ? 'launch:on' : 'launch:off') : 'launch:?';
      target.textContent = `${ok} · ${launch}`;
    }catch(e){
      target.textContent = 'status:error';
    }
  }

  window.CORE = window.CORE || {};
  window.CORE.el = el;
  window.CORE.api = api;
  window.CORE.loadStatus = loadStatus;
  window.CORE.t = t;
  window.CORE.setLang = setLang;
  window.CORE.lang = _getLang();
  window.CORE.errorDetails = errorDetails;

  // Compatibility shim: some pages call window.TAKS.api(...)
  window.TAKS = window.TAKS || {};
  if(typeof window.TAKS.api !== 'function'){
    window.TAKS.api = api;
  }

  // Kick status polling
  loadStatus();
  setInterval(loadStatus, 5000);
})();
