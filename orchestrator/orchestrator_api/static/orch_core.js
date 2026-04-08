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
      'nav.settings_global': 'Globala inställningar',
      'nav.status': 'Status',
      'login.password': 'Lösenord',
      'login.submit': 'Logga in',
      'splash.choose': 'Välj vart du vill gå:',
      'splash.home': 'Hem',


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
      'units.untracked': 'Ospårade noder',
      'units.orphaned': 'Föräldralösa',

      'common.refresh': 'Uppdatera',
      'common.loading': 'laddar…',

      'nodes.title': 'Noder',
      'nodes.active': 'Aktiva noder',
      'nodes.orphaned': 'Föräldralösa noder',
      'nodes.refresh': 'Uppdatera',
      'nodes.spawn': 'Skapa nod',
      'nodes.untracked': 'Ospårade noder',
      'nodes.table.unit': 'enhet',
      'nodes.table.role': 'roll',
      'nodes.table.fqdn': 'fqdn',
      'nodes.table.instance': 'instans',
      'nodes.table.public': 'publik',
      'nodes.table.private': 'privat',
      'nodes.table.activity': 'aktivitet',
      'nodes.table.status': 'status',
      'nodes.table.action': 'åtgärd',
      'nodes.table.node': 'nod',
      'nodes.table.last_seen': 'senast sedd',
      'nodes.terminate': 'Terminera',
      'nodes.delete_state.confirm': 'Ta bort state för {id}?',
      'nodes.terminate.confirm': 'Terminera AWS-instans för {id}?',
      'nodes.terminate.requested': 'Terminering begärd för {id}',
      'nodes.terminate.failed': 'Terminering misslyckades för {id}',
      'common.none': '—',
      'common.error': 'Fel',
      'common.exists': 'finns',
      'common.missing': 'saknas',
      'common.back': 'Tillbaka',
      'common.preview': 'Förhandsvisa',
      'common.dry_run': 'Dry-run',
      'common.launch': 'Starta',
      'common.raw': 'Rådata',
      'common.plan': 'Plan',
      'common.cloud_init': 'Cloud-init',
      'common.create': 'Skapa',
      'common.save': 'Spara',
      'common.saved': 'Sparat',
      'common.saving': 'Sparar…',
      'common.copy': 'Kopiera',
      'new_node.title': 'Skapa nod',
      'new_node.for_unit': 'för {unit}',
      'new_node.back_to_unit': 'Tillbaka',
      'new_node.back_to_nodes': 'Tillbaka',
      'new_unit.title': 'Skapa enhet',
      'new_unit.back': 'Tillbaka',
      'new_unit.raw_response': 'Rådata',
      'new_unit.created_hint': 'Skapar unit.json under /opt/tak-orch/state/units/<unit_path>/unit.json.',
      'unit.title': 'Enhet',
      'unit.parent': 'HC: {parent}',
      'unit.parent.missing': 'HC saknas',
      'unit.back_to_units': '← Tillbaka till enheter',
      'unit.identity.edit': 'Redigera identitet',
      'unit.slogan': 'Slogan',
      'unit.symbol': 'Symbol',
      'unit.logo.change': 'Byt logotyp',
      'unit.quick_links': 'Snabblänkar',
      'unit.server_node': 'TAK-servernod',
      'unit.no_active_node': 'Ingen aktiv eller känd servernod kopplad till denna enhet just nu.',
      'unit.advanced_node_details': 'Avancerade noddetaljer',
      'unit.field.node': 'Nod',
      'unit.field.display_name': 'Visningsnamn',
      'unit.field.region': 'Region',
      'unit.field.last_seen': 'Senast sedd',
      'unit.field.instance_type': 'Instanstyp',
      'unit.field.security_groups': 'Security groups',
      'unit.field.launch_time': 'Starttid',
      'unit.field.launch_source': 'Startkälla',
      'unit.field.private_ip': 'Privat IP',
      'unit.field.public_ip': 'Publik IP',
      'unit.field.iam_profile': 'IAM-profil',
      'unit.field.no_iam_profile': 'Ingen instance profile kopplad',
      'unit.field.tags': 'Taggar',
      'symbol.help.headquarters': 'Högkvarter',
      'symbol.help.team': 'Team',
      'symbol.help.squad': 'Grupp',
      'symbol.help.platoon': 'Pluton',
      'symbol.help.company': 'Kompani',
      'symbol.help.battalion': 'Bataljon',
      'symbol.help.regiment': 'Regemente',
      'symbol.help.brigade': 'Brigad',
      'symbol.help.division': 'Division',
      'symbol.help.corps': 'Kår',
      'symbol.help.flag': 'Flagga / ledning',
      'symbol.help.custom': 'Anpassad',
      'time.seconds_ago': 's sedan',
      'time.minutes_ago': 'm sedan',
      'time.hours_ago': 'h sedan',
      'time.days_ago': 'd sedan',

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
      'units.orphaned': 'Föräldralösa',

      'common.refresh': 'Refresh',
      'common.loading': 'loading…',

      'nodes.title': 'Nodes',
      'nodes.active': 'Active nodes',
      'nodes.orphaned': 'Orphaned nodes',
      'nodes.refresh': 'Refresh',
      'nodes.spawn': 'Spawn node',
      'nodes.untracked': 'Untracked nodes',
      'nodes.table.unit': 'unit',
      'nodes.table.role': 'role',
      'nodes.table.fqdn': 'fqdn',
      'nodes.table.instance': 'instance',
      'nodes.table.public': 'public',
      'nodes.table.private': 'private',
      'nodes.table.activity': 'activity',
      'nodes.table.status': 'status',
      'nodes.table.action': 'action',
      'nodes.table.node': 'node',
      'nodes.table.last_seen': 'last seen',
      'nodes.terminate': 'Terminate',
      'nodes.delete_state.confirm': 'Delete state for {id}?',
      'nodes.terminate.confirm': 'Terminate node {id}?

THIS DESTROYS THE NODE.

YOUR DATA WILL BE DELETED. MKAY?',
      'nodes.terminate.requested': 'Terminate requested for {id}',
      'nodes.terminate.failed': 'Terminate failed for {id}',
      'common.none': '—',
      'common.error': 'Error',
      'common.exists': 'exists',
      'common.missing': 'missing',
      'common.back': 'Back',
      'common.preview': 'Preview',
      'common.dry_run': 'Dry-run',
      'common.launch': 'Launch',
      'common.raw': 'Raw',
      'common.plan': 'Plan',
      'common.cloud_init': 'Cloud-init',
      'common.create': 'Create',
      'common.save': 'Save',
      'common.saved': 'Saved',
      'common.saving': 'Saving…',
      'common.copy': 'Copy',
      'new_node.title': 'Spawn node',
      'new_node.for_unit': 'for {unit}',
      'new_node.back_to_unit': 'Back',
      'new_node.back_to_nodes': 'Back',
      'new_unit.title': 'New unit',
      'new_unit.back': 'Back',
      'new_unit.raw_response': 'Raw response',
      'new_unit.created_hint': 'Creates unit.json under /opt/tak-orch/state/units/<unit_path>/unit.json.',
      'unit.title': 'Unit',
      'unit.parent': 'Parent: {parent}',
      'unit.parent.missing': 'Parent missing',
      'unit.back_to_units': '← Back to units',
      'unit.identity.edit': 'Edit identity',
      'unit.slogan': 'Slogan',
      'unit.symbol': 'Symbol',
      'unit.logo.change': 'Change logo',
      'unit.quick_links': 'Quick links',
      'unit.server_node': 'TAK server node',
      'unit.no_active_node': 'No active or known server node is currently associated with this unit.',
      'unit.advanced_node_details': 'Advanced node details',
      'unit.field.node': 'Node',
      'unit.field.display_name': 'Display name',
      'unit.field.region': 'Region',
      'unit.field.last_seen': 'Last seen',
      'unit.field.instance_type': 'Instance type',
      'unit.field.security_groups': 'Security groups',
      'unit.field.launch_time': 'Launch time',
      'unit.field.launch_source': 'Launch source',
      'unit.field.private_ip': 'Private IP',
      'unit.field.public_ip': 'Public IP',
      'unit.field.iam_profile': 'IAM profile',
      'unit.field.no_iam_profile': 'No instance profile attached',
      'unit.field.tags': 'Tags',
      'symbol.help.headquarters': 'Headquarters',
      'symbol.help.team': 'Team',
      'symbol.help.squad': 'Squad',
      'symbol.help.platoon': 'Platoon',
      'symbol.help.company': 'Company',
      'symbol.help.battalion': 'Battalion',
      'symbol.help.regiment': 'Regiment',
      'symbol.help.brigade': 'Brigade',
      'symbol.help.division': 'Division',
      'symbol.help.corps': 'Corps',
      'symbol.help.flag': 'Flag / command',
      'symbol.help.custom': 'Custom',
      'time.seconds_ago': 's ago',
      'time.minutes_ago': 'm ago',
      'time.hours_ago': 'h ago',
      'time.days_ago': 'd ago',

    }
  };

  function _getLang(){
    const v = String((window.CORE && window.CORE.lang) || 'sv').trim().toLowerCase();
    return v === 'en' ? 'en' : 'sv';
  }

  function setLang(lang){
    lang = (lang === 'en') ? 'en' : 'sv';
    if((window.CORE && window.CORE.lang) === lang){
      applyTranslations();
      return;
    }
    window.CORE.lang = lang;
    applyTranslations();
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

  function applyTranslations(){
    try{
      const setText = function(id, key){
        const n = el(id);
        if(n) n.textContent = t(key);
      };

      setText('nav_units_link', 'nav.units');
      setText('nav_nodes_link', 'nav.nodes');
      setText('nav_settings_link', 'nav.settings');
      setText('nav_logout_link', 'nav.logout');
      setText('nav_status_title', 'nav.status');

      setText('login_password_label', 'login.password');
      setText('login_submit_btn', 'login.submit');

      setText('splash_intro', 'splash.choose');
      setText('splash_login_link', 'login.submit');
      setText('splash_home_link', 'splash.home');
    }catch(_e){}
  }

  function _errToString(e){
    if(!e) return 'Error';
    if(typeof e === 'string') return e;
    if(e instanceof Error) return e.message || String(e);
    return String(e);
  }

  function errorDetails(e){
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

  function _loginUrl(){
    const next = encodeURIComponent(window.location.pathname + (window.location.hash || ''));
    return '/login?next=' + next;
  }

  function _looksLikeHtml(text){
    const s = String(text || '').trim().toLowerCase();
    return s.startsWith('<!doctype html') || s.startsWith('<html') || s.includes('<title>');
  }

  function _isAuthResponse(res, data, text){
    if(res && (res.status === 401 || res.status === 403)) return true;

    if(data && typeof data === 'object'){
      if(data.authenticated === false) return true;
      if(String(data.detail || '').match(/unauthorized|forbidden|not authenticated|session/i)) return true;
    }

    const bodyText = String(text || '');
    if(bodyText && /unauthorized|forbidden|not authenticated|session expired/i.test(bodyText)) return true;

    return false;
  }

  function _shouldBounceToLogin(res, data, text){
    if(_isAuthResponse(res, data, text)) return true;
    if(res && (res.status === 502 || res.status === 503 || res.status === 504) && _looksLikeHtml(text)) return true;
    return false;
  }

  function _bounceToLogin(){
    try{
      if(window.CORE) window.CORE._sessionExpired = true;
      window.location.replace(_loginUrl());
    }catch(_){
      window.location.href = _loginUrl();
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
      // ignore parse errors
    }

    if(_shouldBounceToLogin(res, data, text)){
      _bounceToLogin();
      const err = new Error('SESSION_EXPIRED');
      err.status = res.status;
      err.body = (data !== null ? data : text);
      throw err;
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
      const launch = (j && typeof j.launch_enabled === 'boolean')
        ? (j.launch_enabled ? 'launch:on' : 'launch:off')
        : 'launch:?';
      target.textContent = `${ok} · ${launch}`;
    }catch(e){
      if(e && e.message === 'SESSION_EXPIRED') return;
      target.textContent = 'status:error';
    }
  }

  async function bootstrapSystemLang(){
    try{
      const j = await api('GET', '/api/v2/settings');
      const values = (j && j.values) || {};
      setLang(String(values.system_language || 'sv').trim().toLowerCase() === 'en' ? 'en' : 'sv');
    }catch(_e){
      setLang('sv');
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
  window.CORE.loginUrl = _loginUrl;
  window.CORE.bounceToLogin = _bounceToLogin;
  window.CORE._sessionExpired = false;

  window.TAKS = window.TAKS || {};
  if(typeof window.TAKS.api !== 'function'){
    window.TAKS.api = api;
  }

  bootstrapSystemLang().finally(function(){
    applyTranslations();
    loadStatus();
    setInterval(function(){
      if(window.CORE && window.CORE._sessionExpired) return;
      loadStatus();
    }, 5000);
  });
})();
