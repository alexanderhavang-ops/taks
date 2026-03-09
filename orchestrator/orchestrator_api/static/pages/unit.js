/* global CORE */
(function(){
  function esc(s){
    return String(s ?? '').replace(/[&<>"']/g, function(c){
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
    });
  }

  function getRouteUnitPath(){
    const h = (location.hash || '').trim();
    if(!h.startsWith('#/')) return '';
    const rest = h.slice(2);
    const qpos = rest.indexOf('?');
    const path = (qpos >= 0 ? rest.slice(0, qpos) : rest);
    const parts = path.split('/').filter(Boolean);
    if(parts.length >= 2 && parts[0] === 'units'){
      try { return decodeURIComponent(parts.slice(1).join('/')); }
      catch (_) { return parts.slice(1).join('/'); }
    }
    return '';
  }

  async function loadUnitFromList(unitPath){
    const uResp = await CORE.api('GET', '/api/v2/units');
    const items = (uResp && Array.isArray(uResp.items)) ? uResp.items : [];
    const u = items.find(function(x){ return String(x.unit_path || '') === unitPath; });
    return u || { unit_path: unitPath, title: unitPath, parent_path: '' };
  }

  async function loadBrand(unitPath){
    const url = '/api/public/brand?unit=' + encodeURIComponent(unitPath);
    return await CORE.api('GET', url);
  }

  function setLogoImg(imgEl, unitPath){
    if(!imgEl) return;

    const unitUrl = '/u/' + encodeURIComponent(unitPath) + '/assets/logo.svg';
    const sharedUrl = '/assets/taks-logo.svg';

    imgEl.onerror = function(){
      imgEl.onerror = null;
      imgEl.src = sharedUrl;
    };

    imgEl.src = unitUrl;
  }

  async function render(container){
    const unitPath = getRouteUnitPath();

    container.innerHTML = ''
      + '<section class="card">'
      + '  <div class="card__head">'
      + '    <h3>Enhet</h3>'
      + '    <div class="card__actions">'
      + '      <a class="btn btn--secondary" href="#/units">Tillbaka</a>'
      + '    </div>'
      + '  </div>'
      + '  <div class="muted">Laddar…</div>'
      + '</section>';

    try{
      const u = await loadUnitFromList(unitPath);

      container.innerHTML = ''
        + '<section class="card">'
        + '  <div class="card__head">'
        + '    <h3>' + esc(u.title) + (u.unit_path ? ' (' + esc(u.unit_path) + ')' : '') + '</h3>'
        + '    <div class="card__actions">'
        + '      <a class="btn btn--secondary" href="#/units">Tillbaka</a>'
        + '    </div>'
        + '  </div>'
        + '</section>'

        + '<section class="card">'
        + '  <div class="card__head"><h3>Noder</h3></div>'
        + '  <div class="muted">Kommer: visa nod, skapa nod för denna enhet (sen: exakt 1 nod per enhet).</div>'
        + '</section>'

        + '<section class="card">'
        + '  <div class="card__head"><h3>Branding</h3></div>'
        + '  <div class="grid grid--4" style="align-items:start; margin-top:10px">'
        + '    <div>'
        + '      <div class="muted" style="margin-bottom:8px">Logotyp</div>'
        + '      <div style="background:rgba(255,255,255,.03); border:1px solid var(--border); border-radius:12px; padding:12px; display:flex; align-items:center; justify-content:center; min-height:120px">'
        + '        <img id="unit_logo_img" alt="logo" style="max-width:100%; max-height:140px; display:block">'
        + '      </div>'
        + '    </div>'
        + '    <div style="grid-column: span 3;">'
        + '      <div class="muted" style="margin-bottom:8px">Slogan</div>'
        + '      <div id="unit_slogan" style="font-size:18px; font-weight:700; line-height:1.25">—</div>'
        + '      <div class="muted" style="margin-top:10px">Kommer: ladda upp logotyp + redigera slogan för denna enhet.</div>'
        + '    </div>'
        + '  </div>'
        + '</section>';

      const brand = await loadBrand(unitPath);
      const slogan = String((brand && brand.slogan) || '').trim() || '—';

      const slogEl = document.getElementById('unit_slogan');
      if(slogEl) slogEl.textContent = slogan;

      const img = document.getElementById('unit_logo_img');
      setLogoImg(img, unitPath);

    }catch(e){
      container.innerHTML = '<div class="card"><div class="muted">' + esc(String((e && e.message) ? e.message : e)) + '</div></div>';
    }
  }

  window.TAKS_PAGES = window.TAKS_PAGES || {};
  window.TAKS_PAGES.unit = { render: render };
})();
