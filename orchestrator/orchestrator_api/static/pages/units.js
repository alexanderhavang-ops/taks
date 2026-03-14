/* global CORE */
(function(){
  function esc(s){
    return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }

  function normalizeId(s){
    s = String(s ?? '').trim();
    s = s.replace(/^\/+/, '').replace(/\/+$/, '');
    return s;
  }

  function byId(id){ return document.getElementById(id); }

  function groupBy(arr, keyFn){
    const m = new Map();
    for(const x of arr){
      const k = keyFn(x);
      if(!m.has(k)) m.set(k, []);
      m.get(k).push(x);
    }
    return m;
  }

  function buildTree(units){
    const byParent = groupBy(units, u => (u.parent_path || ''));
    function walk(parentPath){
      const kids = (byParent.get(parentPath) || []).slice().sort((a,b)=>String(a.title).localeCompare(String(b.title)));
      return kids.map(u => ({ u, children: walk(u.unit_path) }));
    }
    return walk('');
  }

  function normalizeUnits(unitsResp){
    const items = (unitsResp && Array.isArray(unitsResp.items)) ? unitsResp.items : [];
    return items.map(u => ({
      unit_path: String(u.unit_path || '').trim(),
      title: String(u.title || u.unit_path || '').trim(),
      parent_path: String(u.parent_path || '').trim(),
      meta: u.meta || {}
    }));
  }

  function normalizeNodes(nodesResp){
    const items = (nodesResp && Array.isArray(nodesResp.items)) ? nodesResp.items : [];
    const orphaned = (nodesResp && Array.isArray(nodesResp.orphaned_items)) ? nodesResp.orphaned_items : [];
    return { items, orphaned };
  }

  async function loadBrand(unitPath){
    const url = '/api/public/brand?unit=' + encodeURIComponent(unitPath);
    try{
      return await CORE.api('GET', url);
    }catch(_){
      return {};
    }
  }

  function renderTreeRow(node, depth, openSet, unitToNodes, unitToSymbol, rows){
    const u = node.u;
    const children = node.children || [];
    const hasKids = children.length > 0;
    const isOpen = openSet.has(u.unit_path);

    const indent = depth * 18;
    const assigned = unitToNodes.get(u.unit_path) || [];
    const count = assigned.length;
    const symbol = String(unitToSymbol.get(u.unit_path) || '').trim();

    const name = `${u.title}${u.unit_path ? ` (${u.unit_path})` : ''}`;

    rows.push(`
      <div class="treeRow" style="padding-left:${indent}px">
        <div class="treeRow__left">
          <button class="treeToggle ${hasKids ? '' : 'is-hidden'}"
                  title="${hasKids ? (isOpen ? 'Fäll ihop' : 'Fäll ut') : ''}"
                  data-action="toggle-open"
                  data-unit="${esc(u.unit_path)}">${isOpen ? '▾' : '▸'}</button>
          ${
            symbol
              ? `<span class="treeSymbol" aria-hidden="true">${esc(symbol)}</span>`
              : `<span class="treeDot" aria-hidden="true"></span>`
          }
          <a class="treeRow__title" href="#/units/${encodeURIComponent(u.unit_path)}">${esc(name)}</a>
        </div>

        <div class="treeRow__right">
          <div class="muted" style="margin-right:10px">${count} noder</div>
          <button class="btn btn--secondary" data-action="toggle-duc" data-unit="${esc(u.unit_path)}">Lägg till DUC</button>
          <button class="btn btn--danger" data-action="delete-unit" data-unit="${esc(u.unit_path)}">Ta bort</button>
        </div>
      </div>

      <div id="duc_form_${esc(u.unit_path)}" class="ducForm" style="display:none; margin-left:${indent}px">
        <div class="muted" style="margin-bottom:8px">Skapa DUC under <b>${esc(u.title)}</b></div>
        <div class="grid grid--6">
          <div>
            <label class="label">Enhets-ID (DUC)</label>
            <input id="duc_id_${esc(u.unit_path)}" placeholder="t.ex. mrs" value="">
          </div>
          <div style="grid-column: span 2;">
            <label class="label">Namn (valfritt)</label>
            <input id="duc_title_${esc(u.unit_path)}" placeholder="t.ex. Militärregion Syd" value="">
          </div>
          <div style="grid-column: span 2; display:flex; align-items:flex-end; gap:8px;">
            <button class="btn" data-action="create-duc" data-hc="${esc(u.unit_path)}">Skapa DUC</button>
            <button class="btn btn--secondary" data-action="toggle-duc" data-unit="${esc(u.unit_path)}">Stäng</button>
          </div>
        </div>
      </div>
    `);

    if(hasKids && isOpen){
      for(const c of children){
        renderTreeRow(c, depth+1, openSet, unitToNodes, unitToSymbol, rows);
      }
    }
  }

  async function loadAndRender(container){
    container.innerHTML = `
      <section class="card">
        <div class="card__head">
          <h3>Enheter</h3>
          <div class="card__actions">
            <button id="btn_units_refresh" class="btn btn--secondary">Uppdatera</button>
          </div>
        </div>
        <div class="muted" id="units_summary">loading…</div>
        <div class="spacer"></div>
        <div id="units_tree"></div>

        <details style="margin-top:12px">
          <summary>Skapa rot-enhet</summary>
          <div class="spacer"></div>
          <div class="grid grid--6">
            <div>
              <label class="label">Enhets-ID</label>
              <input id="root_id" placeholder="t.ex. forsvarsmakten" value="">
            </div>
            <div style="grid-column: span 2;">
              <label class="label">Namn (valfritt)</label>
              <input id="root_title" placeholder="t.ex. Försvarsmakten" value="">
            </div>
            <div style="grid-column: span 2; display:flex; align-items:flex-end; gap:8px;">
              <button id="btn_create_root" class="btn">Skapa</button>
            </div>
          </div>
        </details>

        <details style="margin-top:10px">
          <summary>Övrigt</summary>
          <div class="spacer"></div>
          <div class="muted">Här kan vi senare visa orphaned/untracked, import/export, etc.</div>
        </details>
      </section>

      <style>
        .treeRow{
          display:flex;
          align-items:center;
          justify-content:space-between;
          gap:14px;
          padding:10px 10px;
          border-top:1px solid var(--border);
        }
        .treeRow:first-child{border-top:0}
        .treeRow__left{display:flex;align-items:center;gap:10px;min-width:0}
        .treeRow__right{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
        .treeToggle{
          width:26px;height:26px;border-radius:8px;
          border:1px solid var(--border);
          background:rgba(255,255,255,.03);
          color:var(--text);
          cursor:pointer;
        }
        .treeToggle.is-hidden{visibility:hidden}
        .treeDot{
          width:8px;height:8px;border-radius:999px;
          background:rgba(255,255,255,.18);
          box-shadow:0 0 0 1px rgba(255,255,255,.10);
        }
        .treeSymbol{
          min-width:20px;
          height:20px;
          display:inline-flex;
          align-items:center;
          justify-content:center;
          font-weight:700;
          font-size:12px;
          line-height:1;
          color:#8aa4ff;
          border:1px solid rgba(138,164,255,.18);
          border-radius:6px;
          background:rgba(138,164,255,.08);
          padding:0 4px;
        }
        .treeRow__title{
          font-weight:700;
          color:var(--text);
          text-decoration:none;
          white-space:nowrap;
          overflow:hidden;
          text-overflow:ellipsis;
          max-width:520px;
        }
        .treeRow__title:hover{
          text-decoration:underline;
        }
      </style>
    `;

    const openSet = new Set();

    async function refresh(){
      const summary = byId('units_summary');
      const treeBox = byId('units_tree');

      try{
        const [uResp, nResp] = await Promise.all([
          CORE.api('GET','/api/v2/units'),
          CORE.api('GET','/api/v2/nodes'),
        ]);

        const units = normalizeUnits(uResp);
        const nodes = normalizeNodes(nResp);

        const unitToNodes = new Map();
        for(const u of units) unitToNodes.set(u.unit_path, []);

        for(const n of nodes.items){
          const up = String(n.unit_path || '').trim();
          const st = String(n.derived_status || n.status || '').trim().toLowerCase();

          if(st === 'terminated' || st === 'untracked') continue;

          if(up && unitToNodes.has(up)) unitToNodes.get(up).push(n);
        }

        const unitToSymbol = new Map();
        await Promise.all(units.map(async (u) => {
          const brand = await loadBrand(u.unit_path);
          const sym = String((brand && brand.symbol) || '').trim();
          if(sym) unitToSymbol.set(u.unit_path, sym);
        }));

        const liveNodeCount = nodes.items.filter(function(n){
          const st = String(n.derived_status || n.status || '').trim().toLowerCase();
          return st !== 'terminated' && st !== 'untracked';
        }).length;

        summary.textContent = `Enheter: ${units.length} · Noder: ${liveNodeCount}`;

        const tree = buildTree(units);
        const rows = [];
        for(const top of tree){
          openSet.add(top.u.unit_path);
          renderTreeRow(top, 0, openSet, unitToNodes, unitToSymbol, rows);
        }
        treeBox.innerHTML = rows.join('') || `<div class="muted">No units.</div>`;
      }catch(e){
        alert(String(e && e.message ? e.message : e));
      }
    }

    async function createRoot(){
      const id = normalizeId(byId('root_id').value);
      const title = String(byId('root_title').value || '').trim();

      if(!id){ alert('Enhets-ID saknas.'); return; }

      try{
        await CORE.api('POST','/api/v2/units', {
          unit_path: id,
          title: title || id,
          parent_path: '',
          meta: {}
        });
        byId('root_id').value = '';
        byId('root_title').value = '';
        await refresh();
      }catch(e){
        alert(String(e && e.message ? e.message : e));
      }
    }

    async function createDUC(hc){
      const id = normalizeId(byId(`duc_id_${hc}`).value);
      const title = String(byId(`duc_title_${hc}`).value || '').trim();

      if(!id){ alert('DUC enhets-ID saknas.'); return; }

      try{
        await CORE.api('POST','/api/v2/units', {
          unit_path: id,
          title: title || id,
          parent_path: hc,
          meta: {}
        });
        const box = byId(`duc_form_${hc}`);
        if(box) box.style.display = 'none';
        await refresh();
      }catch(e){
        alert(String(e && e.message ? e.message : e));
      }
    }

    async function deleteUnit(unitPath){
      if(!confirm(`Ta bort enhet "${unitPath}"? (moves to quarantine)`)) return;
      try{
        await CORE.api('DELETE', `/api/v2/units/${encodeURIComponent(unitPath)}`);
        await refresh();
      }catch(e){
        alert(String(e && e.message ? e.message : e));
      }
    }

    function toggleDUC(unitPath){
      const box = byId(`duc_form_${unitPath}`);
      if(!box) return;
      box.style.display = (box.style.display === 'none' || !box.style.display) ? 'block' : 'none';
    }

    function toggleOpen(unitPath){
      if(openSet.has(unitPath)) openSet.delete(unitPath);
      else openSet.add(unitPath);
      refresh();
    }

    container.addEventListener('click', (ev) => {
      const t = ev.target;
      if(!(t instanceof HTMLElement)) return;
      const act = t.getAttribute('data-action');
      if(!act) return;

      if(act === 'toggle-duc'){
        toggleDUC(t.getAttribute('data-unit'));
      }else if(act === 'create-duc'){
        createDUC(t.getAttribute('data-hc'));
      }else if(act === 'delete-unit'){
        deleteUnit(t.getAttribute('data-unit'));
      }else if(act === 'toggle-open'){
        toggleOpen(t.getAttribute('data-unit'));
      }
    });

    byId('btn_units_refresh').onclick = refresh;
    byId('btn_create_root').onclick = createRoot;

    await refresh();
  }

  function render(container){
    loadAndRender(container);
  }

  window.TAKS_PAGES = window.TAKS_PAGES || {};
  window.TAKS_PAGES.units = { render };
})();
