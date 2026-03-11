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

  function byId(id){
    return document.getElementById(id);
  }

  function symbolHelp(sym){
    const s = String(sym || '').trim();
    const m = {
      'HQ': 'Headquarters',
      '•': 'Team',
      '••': 'Squad',
      '•••': 'Platoon',
      'I': 'Company',
      'II': 'Battalion',
      'III': 'Regiment',
      'X': 'Brigade',
      'XX': 'Division',
      'XXX': 'Corps',
      '⚑': 'Flag / command'
    };
    if(!s) return '';
    return m[s] || 'Custom';
  }

  function updateSymbolHelp(){
    const inp = byId('brand_symbol');
    const help = byId('brand_symbol_help');
    if(!inp || !help) return;
    help.textContent = symbolHelp(inp.value);
  }

  function spawnPayload(){
    const g = id => byId(id) ? byId(id).value.trim() : '';
    return {
      unit_path: g('node_unit_path'),
      role: g('node_role'),
      fqdn: g('node_fqdn'),
      hostname: g('node_hostname'),
      name: g('node_name'),
      instance_type: g('node_instance_type')
    };
  }

  async function callNode(path){
    const p = byId('node_out_plan');
    const c = byId('node_out_cloudinit');
    const r = byId('node_out_raw');

    if(p) p.textContent = '…';
    if(c) c.textContent = '…';
    if(r) r.textContent = '…';

    try{
      const j = await CORE.api('POST', path, spawnPayload());
      if(p) p.textContent = JSON.stringify(j.plan || {}, null, 2);
      if(c) c.textContent = j.cloud_init || '—';
      if(r) r.textContent = JSON.stringify(j, null, 2);
    }catch(e){
      if(p) p.textContent = String(e && e.message ? e.message : e);
      if(c) c.textContent = '—';
      if(r) r.textContent = String(e && e.message ? e.message : e);
    }
  }

  async function loadUnitFromList(unitPath){
    const uResp = await CORE.api('GET','/api/v2/units');
    const items = (uResp && Array.isArray(uResp.items)) ? uResp.items : [];
    const u = items.find(function(x){ return String(x.unit_path || '') === unitPath; });
    return u || { unit_path: unitPath, title: unitPath, parent_path: '' };
  }

  async function loadBrand(unitPath){
    const url = '/api/public/brand?unit=' + encodeURIComponent(unitPath);
    return await CORE.api('GET', url);
  }

  async function loadNodes(){
    return await CORE.api('GET','/api/v2/nodes');
  }

  async function saveBrand(unitPath, slogan, symbol){
    return await CORE.api(
      'POST',
      '/api/v2/units/' + encodeURIComponent(unitPath) + '/brand',
      {
        slogan: String(slogan || '').trim(),
        symbol: String(symbol || '').trim()
      }
    );
  }

  function setLogoImg(imgEl, unitPath){
    if(!imgEl) return;

    const tries = [
      '/u/' + encodeURIComponent(unitPath) + '/assets/logo.svg',
      '/u/' + encodeURIComponent(unitPath) + '/assets/logo.png',
      '/assets/taks-logo.svg'
    ];

    function next(){
      const u = tries.shift();
      if(!u){
        imgEl.style.display = 'none';
        return;
      }
      imgEl.src = u;
    }

    imgEl.onerror = next;
    next();
  }

  async function uploadLogo(unitPath, file){
    const fd = new FormData();
    fd.append('file', file);

    const r = await fetch(
      '/api/v2/units/' + encodeURIComponent(unitPath) + '/logo',
      { method:'POST', body:fd, credentials:'include' }
    );

    if(r.ok) return;

    let msg = '';
    try{
      const j = await r.json();
      if(j && j.detail) msg = String(j.detail);
      else msg = JSON.stringify(j);
    }catch(_){
      try{
        msg = (await r.text() || '').trim();
      }catch(__){
        msg = '';
      }
    }

    throw new Error(msg || ('HTTP ' + r.status));
  }

  function findNodeForUnit(nodesResp, unitPath){
    const items = (nodesResp && Array.isArray(nodesResp.items)) ? nodesResp.items : [];
    return items.find(function(n){
      return String(n.unit_path || '').trim() === String(unitPath || '').trim();
    }) || null;
  }

  function fmtNodeSummary(node){
    if(!node) return '<div class="muted">Ingen nod för denna enhet.</div>';

    const nodeId = esc(node.node_id || node.instance_id || '—');
    const fqdn = esc(node.fqdn || '—');
    const status = esc(node.derived_status || node.status || 'unknown');
    const aws = esc(node.aws_state || '—');

    return ''
      + '<div class="grid grid--6" style="margin-top:6px">'
      + '  <div><label class="label">Node</label><div>' + nodeId + '</div></div>'
      + '  <div style="grid-column: span 2;"><label class="label">FQDN</label><div>' + fqdn + '</div></div>'
      + '  <div><label class="label">Status</label><div>' + status + '</div></div>'
      + '  <div><label class="label">AWS</label><div>' + aws + '</div></div>'
      + '</div>';
  }

  function defaultFqdn(unitPath){
    return String(unitPath || '') + '.tak-hv-sandbox.se';
  }

  function defaultHostname(unitPath){
    return 'tak-' + String(unitPath || '');
  }

  async function render(container){
    const unitPath = getRouteUnitPath();

    container.innerHTML =
      '<section class="card">' +
        '<div class="card__head">' +
          '<h3>Enhet</h3>' +
          '<div class="card__actions">' +
            '<a class="btn btn--secondary" href="#/units">Tillbaka</a>' +
          '</div>' +
        '</div>' +
        '<div class="muted">Laddar…</div>' +
      '</section>';

    try{
      const u = await loadUnitFromList(unitPath);
      const brand = await loadBrand(unitPath);
      const nodesResp = await loadNodes();

      const slogan = String((brand && brand.slogan) || '').trim();
      const symbol = String((brand && brand.symbol) || '').trim();
      const node = findNodeForUnit(nodesResp, unitPath);

      const headerTitle =
        (symbol ? '[' + esc(symbol) + '] ' : '') +
        esc(u.title) +
        (u.unit_path ? ' (' + esc(u.unit_path) + ')' : '');

      const headerSlogan = slogan
        ? '<div class="muted" style="margin-top:6px;font-size:15px">' + esc(slogan) + '</div>'
        : '';

      container.innerHTML =
        '<section class="card">' +
          '<div class="card__head">' +
            '<div>' +
              '<h3>' + headerTitle + '</h3>' +
              headerSlogan +
            '</div>' +
            '<div class="card__actions">' +
              '<a class="btn btn--secondary" href="#/units">Tillbaka</a>' +
            '</div>' +
          '</div>' +
        '</section>' +

        '<section class="card">' +
          '<div class="card__head">' +
            '<h3>Noder</h3>' +
            '<div class="card__actions">' +
              (node ? '' : '<button id="btn_toggle_spawn" class="btn">Skapa nod</button>') +
            '</div>' +
          '</div>' +
          fmtNodeSummary(node) +
          '<div class="muted" style="margin-top:10px">Noden ärver branding, filer och senare settings från denna enhet och dess parent-kedja.</div>' +
          (node
            ? '<div class="muted" style="margin-top:10px">Stoppa nod / Terminera nod kommer här när backend-endpoints finns.</div>'
            : '') +

          (!node ? (
            '<div id="unit_spawn_box" style="display:none; margin-top:14px">' +
              '<div class="grid grid--6">' +
                '<div>' +
                  '<label class="label">unit_path</label>' +
                  '<input id="node_unit_path" value="' + esc(unitPath) + '">' +
                '</div>' +
                '<div>' +
                  '<label class="label">role</label>' +
                  '<input id="node_role" value="tak-node">' +
                '</div>' +
                '<div>' +
                  '<label class="label">fqdn</label>' +
                  '<input id="node_fqdn" value="' + esc(defaultFqdn(unitPath)) + '">' +
                '</div>' +
                '<div>' +
                  '<label class="label">hostname</label>' +
                  '<input id="node_hostname" value="' + esc(defaultHostname(unitPath)) + '">' +
                '</div>' +
                '<div>' +
                  '<label class="label">name</label>' +
                  '<input id="node_name" value="' + esc(defaultHostname(unitPath)) + '">' +
                '</div>' +
                '<div>' +
                  '<label class="label">instance_type</label>' +
                  '<input id="node_instance_type" value="t3.micro">' +
                '</div>' +
              '</div>' +

              '<div class="card__actions" style="margin-top:12px">' +
                '<button id="btn_node_preview" class="btn">Preview</button>' +
                '<button id="btn_node_dryrun" class="btn btn--secondary">Dry-run</button>' +
                '<button id="btn_node_launch" class="btn btn--danger">Launch</button>' +
                '<button id="btn_node_close" class="btn btn--secondary">Stäng</button>' +
              '</div>' +

              '<details open style="margin-top:12px"><summary>Plan</summary><pre id="node_out_plan">—</pre></details>' +
              '<details><summary>Cloud-init</summary><pre id="node_out_cloudinit">—</pre></details>' +
              '<details><summary>Raw</summary><pre id="node_out_raw">—</pre></details>' +
            '</div>'
          ) : '') +
        '</section>' +

        '<section class="card">' +
          '<div class="card__head"><h3>Branding</h3></div>' +

          '<div class="grid grid--4" style="align-items:start;margin-top:10px">' +

            '<div>' +
              '<div class="muted" style="margin-bottom:8px">Logotyp</div>' +
              '<div style="background:rgba(255,255,255,.03);border:1px solid var(--border);border-radius:12px;padding:12px;display:flex;align-items:center;justify-content:center;min-height:120px">' +
                '<img id="unit_logo_img" style="max-width:100%;max-height:140px">' +
              '</div>' +
              '<div style="margin-top:10px;display:flex;gap:8px;align-items:center;flex-wrap:wrap">' +
                '<button id="logo_upload_btn" class="btn btn--secondary">Ladda upp logotyp</button>' +
                '<input id="logo_file_input" type="file" accept=".png,.svg,image/png,image/svg+xml" style="display:none">' +
              '</div>' +
              '<div id="logo_upload_status" class="muted" style="margin-top:8px"></div>' +
            '</div>' +

            '<div style="grid-column: span 3;">' +
              '<div class="grid grid--6">' +
                '<div style="grid-column: span 4;">' +
                  '<label class="label">Slogan</label>' +
                  '<input id="brand_slogan" placeholder="t.ex. ALLTID REDO">' +
                '</div>' +
                '<div>' +
                  '<label class="label">Symbol</label>' +
                  '<input id="brand_symbol" list="brand_symbol_presets" placeholder="t.ex. II">' +
                  '<datalist id="brand_symbol_presets">' +
                    '<option value="HQ"></option>' +
                    '<option value="•"></option>' +
                    '<option value="••"></option>' +
                    '<option value="•••"></option>' +
                    '<option value="I"></option>' +
                    '<option value="II"></option>' +
                    '<option value="III"></option>' +
                    '<option value="X"></option>' +
                    '<option value="XX"></option>' +
                    '<option value="XXX"></option>' +
                    '<option value="⚑"></option>' +
                  '</datalist>' +
                '</div>' +
                '<div style="display:flex;align-items:flex-end">' +
                  '<button id="brand_save_btn" class="btn">Spara</button>' +
                '</div>' +
              '</div>' +
              '<div class="muted" style="margin-top:8px">Välj ur listan eller skriv egen.</div>' +
              '<div id="brand_symbol_help" class="muted" style="margin-top:4px"></div>' +
              '<div id="brand_save_status" class="muted" style="margin-top:10px"></div>' +
            '</div>' +

          '</div>' +
        '</section>';

      const sloganInput = byId('brand_slogan');
      const symbolInput = byId('brand_symbol');
      const saveBtn = byId('brand_save_btn');
      const saveStatus = byId('brand_save_status');

      if(sloganInput) sloganInput.value = slogan;
      if(symbolInput) symbolInput.value = symbol;
      updateSymbolHelp();

      const img = byId('unit_logo_img');
      setLogoImg(img, unitPath);

      const uploadBtn = byId('logo_upload_btn');
      const uploadInp = byId('logo_file_input');
      const uploadStatus = byId('logo_upload_status');

      uploadBtn.onclick = function(){
        if(uploadInp) uploadInp.click();
      };

      uploadInp.onchange = async function(){
        const f = uploadInp.files && uploadInp.files[0];
        if(!f) return;

        const name = String(f.name || '').toLowerCase();
        if(!(name.endsWith('.png') || name.endsWith('.svg'))){
          uploadStatus.textContent = 'Bara .png eller .svg är tillåtet.';
          uploadInp.value = '';
          return;
        }

        uploadBtn.disabled = true;
        uploadStatus.textContent = 'Laddar upp…';

        try{
          await uploadLogo(unitPath, f);
          uploadStatus.textContent = 'Uppladdad. Laddar om…';
          window.location.reload();
        }catch(e){
          uploadStatus.textContent = 'Upload failed: ' + String((e && e.message) ? e.message : e);
          uploadBtn.disabled = false;
          uploadInp.value = '';
        }
      };

      if(symbolInput){
        symbolInput.oninput = updateSymbolHelp;
        symbolInput.onchange = updateSymbolHelp;
      }

      saveBtn.onclick = async function(){
        const newSlogan = sloganInput ? sloganInput.value : '';
        const newSymbol = symbolInput ? symbolInput.value : '';

        saveBtn.disabled = true;
        saveStatus.textContent = 'Sparar…';

        try{
          await saveBrand(unitPath, newSlogan, newSymbol);
          updateSymbolHelp();
          saveStatus.textContent = 'Sparat.';
          saveBtn.disabled = false;
        }catch(e){
          saveStatus.textContent = 'Save failed: ' + String((e && e.message) ? e.message : e);
          saveBtn.disabled = false;
        }
      };

      const btnToggleSpawn = byId('btn_toggle_spawn');
      const spawnBox = byId('unit_spawn_box');
      const btnNodeClose = byId('btn_node_close');
      const btnNodePreview = byId('btn_node_preview');
      const btnNodeDryrun = byId('btn_node_dryrun');
      const btnNodeLaunch = byId('btn_node_launch');

      if(btnToggleSpawn && spawnBox){
        btnToggleSpawn.onclick = function(){
          spawnBox.style.display = 'block';
          btnToggleSpawn.style.display = 'none';
        };
      }

      if(btnNodeClose && spawnBox && btnToggleSpawn){
        btnNodeClose.onclick = function(){
          spawnBox.style.display = 'none';
          btnToggleSpawn.style.display = '';
        };
      }

      if(btnNodePreview) btnNodePreview.onclick = function(){ callNode('/api/v2/nodes/preview'); };
      if(btnNodeDryrun) btnNodeDryrun.onclick = function(){ callNode('/api/v2/nodes/dry-run'); };
      if(btnNodeLaunch) btnNodeLaunch.onclick = function(){ callNode('/api/v2/nodes/launch'); };

    }catch(e){
      container.innerHTML =
        '<div class="card"><div class="muted">' +
        esc(String((e && e.message) ? e.message : e)) +
        '</div></div>';
    }
  }

  window.TAKS_PAGES = window.TAKS_PAGES || {};
  window.TAKS_PAGES.unit = { render: render };

})();
