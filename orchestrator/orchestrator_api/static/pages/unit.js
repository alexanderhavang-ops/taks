/* global CORE */
(function(){
  function esc(s){
    return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }

  async function loadUnit(unitPath){
    const uResp = await CORE.api('GET','/api/v2/units');
    const items = (uResp && Array.isArray(uResp.items)) ? uResp.items : [];
    const u = items.find(x => String(x.unit_path || '') === unitPath);
    return u || { unit_path: unitPath, title: unitPath, parent_path: '' };
  }

  async function render(container, ctx){
    const unitPath = String(ctx?.unit_path || '').trim();
    container.innerHTML = `
      <section class="card">
        <div class="card__head">
          <h3>Enhet</h3>
          <div class="card__actions">
            <a class="btn btn--secondary" href="#/units">Tillbaka</a>
          </div>
        </div>
        <div class="muted">Laddar…</div>
      </section>
    `;

    try{
      const u = await loadUnit(unitPath);
      container.innerHTML = `
        <section class="card">
          <div class="card__head">
            <h3>${esc(u.title)} (${esc(u.unit_path)})</h3>
            <div class="card__actions">
              <a class="btn btn--secondary" href="#/units">Tillbaka</a>
            </div>
          </div>

          <div class="muted" style="margin-top:6px">
            Här bygger vi: assets, config, ikoner, settings, typ, status, noder, barn-enheter.
          </div>
        </section>
      `;
    }catch(e){
      container.innerHTML = `<div class="card"><div class="muted">${esc(String(e))}</div></div>`;
    }
  }

  window.TAKS_PAGES = window.TAKS_PAGES || {};
  window.TAKS_PAGES.unit = { render };
})();
