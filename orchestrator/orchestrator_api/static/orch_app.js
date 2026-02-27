(function(){
  function el(id){ return document.getElementById(id); }

  async function api(method, path, body){
    const opts = {
      method,
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin'
    };
    if(body !== undefined) opts.body = JSON.stringify(body);
    const r = await fetch(path, opts);
    const txt = await r.text();
    if(!r.ok) throw new Error(`HTTP ${r.status}\n${txt}`);
    return txt ? JSON.parse(txt) : {};
  }

  function fmtTs(ts){
    if(!ts) return '—';
    try{ return new Date(ts * 1000).toISOString(); }
    catch{ return String(ts); }
  }

  function escapeHtml(s){
    return String(s ?? '').replace(/[&<>"']/g, (c) => ({
      '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
    }[c]));
  }

  function setActiveNav(route){
    for(const a of document.querySelectorAll('.nav__item')){
      const r = a.getAttribute('data-route');
      a.classList.toggle('is-active', r === route);
    }
  }

  function routeNow(){
    const h = (location.hash || '').trim();
    const r = h.startsWith('#') ? h.slice(1) : h;
    if(!r || r === '/') return '/nodes';
    return r.startsWith('/') ? r : `/${r}`;
  }

  async function loadStatus(){
    try{
      const j = await api('GET', '/api/v2/status');
      const nav = el('nav_status');
      if(nav) nav.textContent = j.launch_enabled ? 'ok (launch enabled)' : 'ok (launch disabled)';

      const out = el('status_out');
      if(out) out.textContent = JSON.stringify(j, null, 2);

      const banner = el('banner_launch_disabled');
      if(banner) banner.style.display = (j.launch_enabled !== true) ? 'block' : 'none';

      const launchBtn = el('btn_launch');
      if(launchBtn) launchBtn.disabled = (j.launch_enabled !== true);
    }catch(e){
      const nav = el('nav_status');
      if(nav) nav.textContent = 'error';
      const out = el('status_out');
      if(out) out.textContent = String(e);
    }
  }

  function render(){
    const r = routeNow();
    const page = el('page');
    if(!page) return;

    if(r === '/nodes/new'){
      setActiveNav('/nodes/new');
      window.TAKS_PAGES?.new_node?.render(page);
    }else if(r === '/settings'){
      setActiveNav('/settings');
      window.TAKS_PAGES?.settings?.render(page);
    }else{
      setActiveNav('/nodes');
      window.TAKS_PAGES?.nodes?.render(page);
    }

    loadStatus();
  }

  window.TAKS = {
    el, api, fmtTs, escapeHtml, loadStatus,
  };

  window.addEventListener('hashchange', render);
  window.addEventListener('DOMContentLoaded', () => {
    if(!location.hash) location.hash = '#/nodes';
    render();
  });
})();
