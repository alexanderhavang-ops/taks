(function(){

  function el(id){ return document.getElementById(id); }

  async function api(method, path, body){
    const o = { method, credentials:'include' };
    if(body){
      o.headers = { 'Content-Type':'application/json' };
      o.body = JSON.stringify(body);
    }
    const r = await fetch(path, o);
    const t = await r.text();
    if(!r.ok) throw new Error(`HTTP  \n`);
    return t ? JSON.parse(t) : {};
  }

  function route(){
    const h = (location.hash||'#/nodes').slice(1);
    return h || '/nodes';
  }

  function setNav(r){
    document.querySelectorAll('.nav__item').forEach(a=>{
      a.classList.toggle('is-active', a.dataset.route === r);
    });
  }

  async function loadStatus(){
    try{
      const j = await api('GET','/api/v2/status');
      const n = el('nav_status');
      if(n) n.textContent = j.launch_enabled ? 'ok (launch enabled)' : 'ok (launch disabled)';
      const b = el('banner_launch_disabled');
      if(b) b.style.display = j.launch_enabled ? 'none':'block';
      const l = el('btn_launch');
      if(l) l.disabled = !j.launch_enabled;
    }catch{
      const n = el('nav_status');
      if(n) n.textContent = 'error';
    }
  }

  function render(){
    const r = route();
    const page = el('page');
    if(!page) return;

    if(r === '/nodes/new'){
      setNav('/nodes/new');
      window.PAGES.new?.(page);
    }else if(r === '/settings'){
      setNav('/settings');
      window.PAGES.settings?.(page);
    }else{
      setNav('/nodes');
      window.PAGES.nodes?.(page);
    }
    loadStatus();
  }

  window.CORE = { el, api, loadStatus };
  window.PAGES = {};

  window.addEventListener('hashchange', render);
  window.addEventListener('DOMContentLoaded', ()=>{
    if(!location.hash) location.hash = '#/nodes';
    render();
  });

})();
