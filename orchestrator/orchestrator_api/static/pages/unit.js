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

  async function loadUnitFiles(unitPath){
    return await CORE.api('GET', '/api/v2/units/' + encodeURIComponent(unitPath) + '/files');
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

  async function uploadUnitFile(unitPath, subtree, name, file){
    const fd = new FormData();
    fd.append('file', file);

    const url =
      '/api/v2/units/' + encodeURIComponent(unitPath) + '/files/upload' +
      '?subtree=' + encodeURIComponent(subtree) +
      '&name=' + encodeURIComponent(name);

    const r = await fetch(url, { method:'POST', body:fd, credentials:'include' });

    if(r.ok) return await r.json();

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

    const matches = items.filter(function(n){
      return String(n.unit_path || '').trim() === String(unitPath || '').trim();
    });

    const blocking = matches.find(function(n){
      const aws = String(n.aws_state || '').trim().toLowerCase();
      const st = String(n.derived_status || n.status || '').trim().toLowerCase();

      if (aws === 'terminated' || st === 'terminated') return false;
      if (st === 'untracked') return false;

      return true;
    });

    return blocking || null;
  }

  function fmtAge(sec){
    if(sec == null) return '—';
    sec = Number(sec);
    if(sec < 60) return sec + 's ago';
    if(sec < 3600) return Math.floor(sec/60) + 'm ago';
    if(sec < 86400) return Math.floor(sec/3600) + 'h ago';
    return Math.floor(sec/86400) + 'd ago';
  }

  function heartbeatState(node){
    const age = node && node.heartbeat_age_sec;
    if(age == null) return 'never';
    const sec = Number(age);
    if(sec <= 90) return 'online';
    if(sec <= 300) return 'stale';
    return 'lost';
  }

  function fmtNodeSummary(node){
    if(!node) return '<div class="muted">Ingen nod för denna enhet.</div>';

    const nodeId = esc(node.node_id || node.fqdn || node.instance_id || '—');
    const fqdnRaw = String(node.fqdn || '').trim();
    const fqdn = esc(fqdnRaw || '—');
    const aws = esc(node.aws_state || '—');
    const hb = esc(heartbeatState(node));
    const lastSeen = esc(fmtAge(node.heartbeat_age_sec));
    const priv = esc(node.private_ip || node.aws_private_ip || '—');
    const pub = esc(node.public_ip || node.aws_public_ip || '—');
    const inst = esc(node.instance_id || node.aws_instance_id || '—');

    const taksUrl = fqdnRaw ? ('https://' + fqdnRaw + '/') : '';
    const martiUrl = fqdnRaw ? ('https://' + fqdnRaw + ':8446/Marti/') : '';
    const webtakUrl = fqdnRaw ? ('https://' + fqdnRaw + ':8446/webtak/') : '';

    const awsBadgeClass = aws === 'running' ? 'ok' : (aws === 'terminated' ? 'err' : 'muted');
    const hbBadgeClass = hb === 'online' ? 'ok' : (hb === 'stale' ? 'warn' : (hb === 'lost' ? 'err' : 'muted'));

    return ''
      + '<div style="display:grid;gap:14px;margin-top:8px">'
      + '  <div class="grid grid--6">'
      + '    <div style="grid-column: span 2;"><label class="label">Node</label><div style="font-weight:700;word-break:break-all">' + nodeId + '</div></div>'
      + '    <div style="grid-column: span 2;"><label class="label">FQDN</label><div style="word-break:break-all">' + fqdn + '</div></div>'
      + '    <div><label class="label">AWS</label><div><span class="badge badge--' + awsBadgeClass + '">' + aws + '</span></div></div>'
      + '    <div><label class="label">Heartbeat</label><div><span class="badge badge--' + hbBadgeClass + '">' + hb + '</span></div></div>'
      + '  </div>'
      + '  <div class="grid grid--6">'
      + '    <div><label class="label">Last seen</label><div>' + lastSeen + '</div></div>'
      + '    <div style="grid-column: span 2;"><label class="label">Instance</label><div style="word-break:break-all">' + inst + '</div></div>'
      + '    <div><label class="label">Private IP</label><div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap"><code>' + priv + '</code><button class="btn btn--secondary" type="button" onclick="navigator.clipboard && navigator.clipboard.writeText(\'' + priv.replace(/\\/g,'\\\\').replace(/'/g,"\\'") + '\')">Copy</button></div></div>'
      + '    <div><label class="label">Public IP</label><div><code>' + pub + '</code></div></div>'
      + '  </div>'
      + '  <div class="card__actions">'
      + (taksUrl ? ('<a class="btn" target="_blank" rel="noopener noreferrer" href="' + esc(taksUrl) + '">TAKS</a>') : '')
      + (webtakUrl ? ('<a class="btn btn--secondary" target="_blank" rel="noopener noreferrer" href="' + esc(webtakUrl) + '">WebTAK</a>') : '')
      + (martiUrl ? ('<a class="btn btn--secondary" target="_blank" rel="noopener noreferrer" href="' + esc(martiUrl) + '">Marti</a>') : '')
      + '  </div>'
      + '</div>';
  }

  function defaultFqdn(unitPath){
    return String(unitPath || '') + '.tak-hv-sandbox.se';
  }

  function defaultHostname(unitPath){
    return 'tak-' + String(unitPath || '');
  }

  function subtreeLabel(name){
    const m = {
      packages: 'Packages',
      branding: 'Branding',
      users: 'Users',
      plugins: 'Plugins',
      maps: 'Maps',
      missions: 'Missions',
      misc: 'Misc'
    };
    return m[name] || name;
  }

  function renderFilesSection(filesResp){
    const subtrees = (filesResp && filesResp.subtrees) ? filesResp.subtrees : {};
    const order = ['packages','branding','users','plugins','maps','missions','misc'];

    let html = '';

    html += '<div class="grid grid--6" style="margin-top:10px">';
    html += '  <div>';
    html += '    <label class="label">Subtree</label>';
    html += '    <select id="unit_file_subtree">';
    order.forEach(function(name){
      html += '<option value="' + esc(name) + '">' + esc(subtreeLabel(name)) + '</option>';
    });
    html += '    </select>';
    html += '  </div>';
    html += '  <div style="grid-column: span 3;">';
    html += '    <label class="label">Målfilnamn / relativ sökväg</label>';
    html += '    <input id="unit_file_name" placeholder="t.ex. takserver.tar.gz eller config/example.txt">';
    html += '  </div>';
    html += '  <div style="display:flex;align-items:flex-end;gap:8px;">';
    html += '    <button id="unit_file_upload_btn" class="btn">Ladda upp fil</button>';
    html += '    <input id="unit_file_input" type="file" style="display:none">';
    html += '  </div>';
    html += '</div>';
    html += '<div id="unit_file_upload_status" class="muted" style="margin-top:8px"></div>';

    order.forEach(function(name){
      const items = Array.isArray(subtrees[name]) ? subtrees[name] : [];

      html += '<details style="margin-top:12px"' + (name === 'packages' ? ' open' : '') + '>';
      html += '  <summary>' + esc(subtreeLabel(name)) + ' (' + items.length + ')</summary>';
      html += '  <div class="spacer"></div>';

      if(!items.length){
        html += '  <div class="muted">Tomt.</div>';
      }else{
        html += '  <div style="display:grid;gap:8px">';
        items.forEach(function(it){
          html += ''
            + '<div style="display:flex;justify-content:space-between;gap:12px;border-top:1px solid var(--border);padding-top:8px">'
            + '  <div style="min-width:0">'
            + '    <div style="font-weight:600;word-break:break-all">' + esc(it.path || '') + '</div>'
            + '  </div>'
            + '  <div class="muted" style="white-space:nowrap">' + esc(String(it.bytes || 0)) + ' B</div>'
            + '</div>';
        });
        html += '  </div>';
      }

      html += '</details>';
    });

    return html;
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
      const filesResp = await loadUnitFiles(unitPath);

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
                  '<input id="node_instance_type" value="t3.small">' +
                '</div>' +
              '</div>' +

              '<div class="card__actions" style="margin-top:12px">' +
                '<button id="btn_node_preview" class="btn">Preview</button>' +
                '<button id="btn_node_dryrun" class="btn btn--secondary">Dry-run</button>' +
                '<button id="btn_node_launch" class="btn btn--danger">Launch</button>' +
                ((node && (node.instance_id || node.aws_instance_id)) ? '<button id="btn_node_terminate" class="btn btn--danger">Terminate</button>' : '') +
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
        '</section>' +

        '<section class="card">' +
          '<div class="card__head"><h3>Bundle files</h3></div>' +
          '<div class="muted">Filer i dessa subtrees inkluderas i bundle med parent→leaf-arv. Löv vinner vid filkonflikt.</div>' +
          renderFilesSection(filesResp) +
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

      const filesUploadBtn = byId('unit_file_upload_btn');
      const filesInput = byId('unit_file_input');
      const filesSubtree = byId('unit_file_subtree');
      const filesName = byId('unit_file_name');
      const filesStatus = byId('unit_file_upload_status');

      if(filesUploadBtn && filesInput){
        filesUploadBtn.onclick = function(){
          filesInput.click();
        };
      }

      if(filesInput){
        filesInput.onchange = async function(){
          const f = filesInput.files && filesInput.files[0];
          if(!f) return;

          const subtree = filesSubtree ? String(filesSubtree.value || '').trim() : '';
          const relname = filesName && String(filesName.value || '').trim()
            ? String(filesName.value || '').trim()
            : String(f.name || '').trim();

          if(!subtree){
            filesStatus.textContent = 'Välj subtree.';
            filesInput.value = '';
            return;
          }
          if(!relname){
            filesStatus.textContent = 'Ange filnamn.';
            filesInput.value = '';
            return;
          }

          filesUploadBtn.disabled = true;
          filesStatus.textContent = 'Laddar upp…';

          try{
            await uploadUnitFile(unitPath, subtree, relname, f);
            filesStatus.textContent = 'Uppladdad. Laddar om…';
            window.location.reload();
          }catch(e){
            filesStatus.textContent = 'Upload failed: ' + String((e && e.message) ? e.message : e);
            filesUploadBtn.disabled = false;
            filesInput.value = '';
          }
        };
      }

      const btnToggleSpawn = byId('btn_toggle_spawn');
      const spawnBox = byId('unit_spawn_box');
      const btnNodeClose = byId('btn_node_close');
      const btnNodePreview = byId('btn_node_preview');
      const btnNodeDryrun = byId('btn_node_dryrun');
      const btnNodeLaunch = byId('btn_node_launch');
      const btnNodeTerminate = byId('btn_node_terminate');

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

      if(btnNodePreview) btnNodePreview.onclick = function(){
        callNode('/api/v2/nodes/preview');
      };

      if(btnNodeDryrun) btnNodeDryrun.onclick = function(){
        callNode('/api/v2/nodes/dry-run');
      };

      if(btnNodeTerminate) btnNodeTerminate.onclick = async function(){
        const id = node && node.node_id ? String(node.node_id) : '';
        if(!id) return;
        if(!confirm('Terminate AWS instance for ' + id + '?')) return;
        try{
          const j = await CORE.api('POST', '/api/v2/nodes/' + encodeURIComponent(id) + '/terminate', {});
          alert('Terminate requested for ' + id + '\n\n' + JSON.stringify(j.terminate || j || {}, null, 2));
          window.TAKS_PAGES.unit.render(container);
        }catch(e){
          const msg = String((e && e.message) ? e.message : e);
          alert('Terminate failed for ' + id + '\n\n' + msg);
          throw e;
        }
      };

      if(btnNodeLaunch) btnNodeLaunch.onclick = async function(){
        const p = byId('node_out_plan');
        const c = byId('node_out_cloudinit');
        const r = byId('node_out_raw');

        btnNodeLaunch.disabled = true;
        if(btnNodePreview) btnNodePreview.disabled = true;
        if(btnNodeDryrun) btnNodeDryrun.disabled = true;

        if(p) p.textContent = 'Launching…';
        if(c) c.textContent = '—';
        if(r) r.textContent = '—';

        try{
          const j = await CORE.api('POST', '/api/v2/nodes/launch', spawnPayload());

          if(p) p.textContent = JSON.stringify(j.launch || j.plan || j || {}, null, 2);
          if(r) r.textContent = JSON.stringify(j, null, 2);

          let tries = 0;
          const maxTries = 12;

          const poll = async function(){
            tries += 1;
            try{
              const nodesResp = await loadNodes();
              const nodeNow = findNodeForUnit(nodesResp, unitPath);
              if(nodeNow){
                window.TAKS_PAGES.unit.render(container);
                return;
              }
            }catch(_){
            }

            if(tries < maxTries){
              setTimeout(poll, 2000);
            }else{
              window.TAKS_PAGES.unit.render(container);
            }
          };

          setTimeout(poll, 1000);
        }catch(e){
          const msg = String((e && e.message) ? e.message : e);
          if(p) p.textContent = msg;
          if(c) c.textContent = '—';
          if(r) r.textContent = msg;
          btnNodeLaunch.disabled = false;
          if(btnNodePreview) btnNodePreview.disabled = false;
          if(btnNodeDryrun) btnNodeDryrun.disabled = false;
        }
      };

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
