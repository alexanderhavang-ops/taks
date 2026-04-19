(function () {
  function missing(title, detail){
    return ''
      + '<div class="card">'
      + '  <div class="card__title">' + title + '</div>'
      + '  <div class="muted">' + detail + '</div>'
      + '</div>';
  }

  function setActiveNav(route){
    document.querySelectorAll('.nav__item[data-route]').forEach(function(a){
      a.classList.toggle('is-active', a.dataset.route === route);
    });
  }

  function recentUnitsStorageKey(){
    return 'taks:recent-units';
  }

  function currentUnitPathFromRoute(route){
    const r = String(route || '').trim();
    if(!r.startsWith('/units/')) return '';
    try{
      return decodeURIComponent(r.slice('/units/'.length) || '').trim();
    }catch(_e){
      return String(r.slice('/units/'.length) || '').trim();
    }
  }

  function loadRecentUnits(){
    try{
      const raw = localStorage.getItem(recentUnitsStorageKey()) || '[]';
      const arr = JSON.parse(raw);
      if(!Array.isArray(arr)) return [];
      return arr
        .map(function(x){ return String(x || '').trim(); })
        .filter(Boolean)
        .slice(0, 3);
    }catch(_e){
      return [];
    }
  }

  function saveRecentUnits(items){
    try{
      const arr = (Array.isArray(items) ? items : [])
        .map(function(x){ return String(x || '').trim(); })
        .filter(Boolean)
        .slice(0, 3);
      localStorage.setItem(recentUnitsStorageKey(), JSON.stringify(arr));
    }catch(_e){}
  }

  function rememberRecentUnit(unitPath){
    const cur = String(unitPath || '').trim();
    if(!cur) return;
    const arr = loadRecentUnits().filter(function(x){ return x !== cur; });
    arr.unshift(cur);
    saveRecentUnits(arr);
  }

  function recentUnitsTitle(){
    return (window.CORE && window.CORE.lang === 'en') ? 'Recent units' : 'Senaste enheter';
  }

  function renderRecentUnits(activeUnitPath){
    const nav = document.querySelector('.nav');
    if(!nav) return;

    let host = document.getElementById('nav_recent_units');
    if(!host){
      host = document.createElement('div');
      host.id = 'nav_recent_units';

      const firstMeta = nav.querySelector('.nav__meta');
      if(firstMeta) nav.insertBefore(host, firstMeta);
      else nav.appendChild(host);
    }

    host.innerHTML = '';

    const items = loadRecentUnits();
    if(!items.length) return;

    const sep = document.createElement('div');
    sep.className = 'nav__sep';
    host.appendChild(sep);

    const meta = document.createElement('div');
    meta.className = 'nav__meta';

    const title = document.createElement('div');
    title.className = 'nav__metaTitle';
    title.textContent = recentUnitsTitle();
    meta.appendChild(title);

    host.appendChild(meta);

    items.forEach(function(unitPath){
      const a = document.createElement('a');
      a.className = 'nav__item';
      a.href = '#/units/' + encodeURIComponent(unitPath);
      a.textContent = unitPath;
      if(String(activeUnitPath || '').trim() === unitPath){
        a.classList.add('is-active');
      }
      host.appendChild(a);
    });
  }

  function routeNow(){
    const h = (location.hash || '').trim();
    if (!h) return '/units';
    if (h.startsWith('#')) {
      const rest = h.slice(1);
      const q = rest.indexOf('?');
      return (q >= 0 ? rest.slice(0, q) : rest) || '/units';
    }
    return '/units';
  }

  async function refreshStatus(){
    const el = document.getElementById('nav_status');
    if(!el) return;
    try {
      const r = await fetch('/api/v2/status', { credentials: 'include' });
      const j = await r.json();
      const launch = j.launch_enabled ? 'launch:on' : 'launch:off';
      el.textContent = (j.service || 'ok') + ' · ' + launch;
    } catch(e) {
      el.textContent = 'status: error';
    }
  }

  function render(){
    const r = routeNow();
    const page = document.getElementById('page');
    if(!page) return;

    window.TAKS_PAGES = window.TAKS_PAGES || {};
    window.PAGES = window.PAGES || {};

    // Keep Units highlighted also when we are on a unit subpage.
    const navRoute = (r === '/units' || r.startsWith('/units/')) ? '/units' : r;
    setActiveNav(navRoute);

    const activeUnitPath = currentUnitPathFromRoute(r);
    if(activeUnitPath) rememberRecentUnit(activeUnitPath);
    renderRecentUnits(activeUnitPath);

    if (r === '/units') {
      if(window.TAKS_PAGES?.units?.render) window.TAKS_PAGES.units.render(page);
      else page.innerHTML = missing(CORE.t('nav.units'), 'Missing page module: TAKS_PAGES.units');
    }
    else if (r.startsWith('/units/')) {
      const unitPath = decodeURIComponent(r.slice('/units/'.length) || '');
      if(window.TAKS_PAGES?.unit?.render) window.TAKS_PAGES.unit.render(page, { unit_path: unitPath });
      else page.innerHTML = missing(CORE.t('unit.title'), 'Missing page module: TAKS_PAGES.unit');
    }
    else if (r === '/nodes') {
      if(window.TAKS_PAGES?.nodes?.render) window.TAKS_PAGES.nodes.render(page);
      else if(window.PAGES?.nodes) window.PAGES.nodes(page);
      else page.innerHTML = missing(CORE.t('nav.nodes'), 'Missing nodes page module');
    }
    else if (r === '/nodes/spawn') {
      if(window.PAGES?.new) window.PAGES.new(page);
      else page.innerHTML = missing(CORE.t('nav.spawn_node'), 'Missing page module: PAGES.new (legacy spawn)');
    }
    else if (r === '/settings') {
      if(window.TAKS_PAGES?.settings?.render) window.TAKS_PAGES.settings.render(page);
      else if(window.PAGES?.settings) window.PAGES.settings(page);
      else page.innerHTML = missing(CORE.t('nav.settings'), 'Missing settings page module');
    }
    else {
      page.innerHTML = missing(CORE.t('common.error'), 'No route: ' + r);
    }

    refreshStatus();
  }

  window.addEventListener('hashchange', render);
  window.addEventListener('taks:lang', render);
  window.addEventListener('load', function(){
    if(!location.hash) location.hash = '#/units';
    render();
  });
})();
