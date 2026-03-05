/* global CORE */
(function(){
  function esc(s){
    return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }

  function pick(o, keys, fallback){
    for(const k of keys){
      const v = o && o[k];
      if(v !== undefined && v !== null && String(v).trim() !== '') return v;
    }
    return fallback;
  }

  async function loadUnit(unitPath){
    const uResp = await CORE.api('GET','/api/v2/units');
    const items = (uResp && Array.isArray(uResp.items)) ? uResp.items : [];
    const u = items.find(x => String(x.unit_path || '') === unitPath);
    return u || { unit_path: unitPath, title: unitPath, parent_path: '' };
  }

  async function loadNodes(){
    const nResp = await CORE.api('GET','/api/v2/nodes');
    // Expect shape: { items:[...], count:n } but tolerate other shapes
    if(nResp && Array.isArray(nResp.items)) return nResp.items;
    if(Array.isArray(nResp)) return nResp;
    return [];
  }

  function renderNodesTable(nodes){
    if(!nodes.length){
      return `<div class="muted" style="margin-top:8px">Inga noder i denna enhet.</div>`;
    }

    const rows = nodes.map(n => {
      const name = pick(n, ['name','hostname','fqdn','instance_id','id'], '—');
      const role = pick(n, ['role'], '—');
      const itype = pick(n, ['instance_type'], '—');
      const state = pick(n, ['state','status','lifecycle','phase'], '—');
      const fqdn = pick(n, ['fqdn'], '');
      const inst = pick(n, ['instance_id'], '');
      return `
        <tr>
          <td><code>${esc(name)}</code></td>
          <td>${esc(role)}</td>
          <td>${esc(itype)}</td>
          <td>${esc(state)}</td>
          <td class="muted"><code>${esc(fqdn || inst || '—')}</code></td>
        </tr>
      `;
    }).join('');

    return `
      <div class="tablewrap" style="margin-top:10px">
        <table class="table">
          <thead>
            <tr>
              <th>Nod</th>
              <th>Roll</th>
              <th>Typ</th>
              <th>Status</th>
              <th class="muted">FQDN / Instance</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    `;
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
      const [u, allNodes] = await Promise.all([loadUnit(unitPath), loadNodes()]);
      const nodes = allNodes.filter(n => String(n.unit_path || '') === unitPath);

      const spawnHref = `#/nodes/spawn?unit_path=${encodeURIComponent(unitPath)}`;

      container.innerHTML = `
        <section class="card">
          <div class="card__head">
            <div>
              <h3>${esc(u.title)} (${esc(u.unit_path)})</h3>
              <div class="muted" style="margin-top:4px">Orchestrator-vy: noder, config, assets.</div>
            </div>
            <div class="card__actions">
              <a class="btn" href="${spawnHref}">Skapa nod</a>
              <a class="btn btn--secondary" href="#/units">Tillbaka</a>
            </div>
          </div>

          <div class="spacer"></div>

          <div class="muted"><b>Noder</b> · ${nodes.length} st</div>
          ${renderNodesTable(nodes)}
        </section>
      `;
    }catch(e){
      container.innerHTML = `<div class="card"><div class="muted">${esc(String(e))}</div></div>`;
    }
  }

  window.TAKS_PAGES = window.TAKS_PAGES || {};
  window.TAKS_PAGES.unit = { render };
})();
