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
