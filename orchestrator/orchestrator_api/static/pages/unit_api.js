/* global CORE */
(function(){
  window.TAKS_UNIT = window.TAKS_UNIT || {};
  const S = window.TAKS_UNIT.shared;

  async function loadUnitFromList(unitPath){
    const uResp = await CORE.api('GET', '/api/v2/units');
    const items = (uResp && Array.isArray(uResp.items)) ? uResp.items : [];
    const u = items.find(function(x){ return String(x.unit_path || '') === unitPath; });
    return u || { unit_path: unitPath, title: unitPath, parent_path: '' };
  }

  async function loadBrand(unitPath){
    return await CORE.api('GET', '/api/public/brand?unit=' + encodeURIComponent(unitPath));
  }

  async function loadNodes(){
    return await CORE.api('GET', '/api/v2/nodes');
  }

  async function loadStatus(){
    return await CORE.api('GET', '/api/v2/status');
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

  async function uploadLogo(unitPath, file){
    const fd = new FormData();
    fd.append('file', file);

    const r = await fetch(
      '/api/v2/units/' + encodeURIComponent(unitPath) + '/logo',
      { method: 'POST', body: fd, credentials: 'include' }
    );

    if(r.ok) return;

    let msg = '';
    try{
      const j = await r.json();
      msg = (j && j.detail) ? String(j.detail) : JSON.stringify(j);
    }catch(_){
      try { msg = (await r.text() || '').trim(); }
      catch(__) { msg = ''; }
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

    const r = await fetch(url, { method: 'POST', body: fd, credentials: 'include' });

    if(r.ok) return await r.json();

    let msg = '';
    try{
      const j = await r.json();
      msg = (j && j.detail) ? String(j.detail) : JSON.stringify(j);
    }catch(_){
      try { msg = (await r.text() || '').trim(); }
      catch(__) { msg = ''; }
    }
    throw new Error(msg || ('HTTP ' + r.status));
  }

  function spawnPayload(){
    const unitPath = S.getRouteUnitPath();
    const instanceType = S.byId('node_instance_type') ? S.byId('node_instance_type').value.trim() : '';
    const displayName = S.byId('node_display_name') ? S.byId('node_display_name').value.trim() : '';
    const fqdn = S.byId('node_fqdn') ? S.byId('node_fqdn').value.trim() : '';
    const awsSgId = S.byId('node_aws_sg_id') ? S.byId('node_aws_sg_id').value.trim() : '';
    const awsKeyName = S.byId('node_aws_key_name') ? S.byId('node_aws_key_name').value.trim() : '';

    return {
      unit_path: unitPath,
      name: displayName,
      fqdn: fqdn,
      instance_type: instanceType || 't3.small',
      aws_sg_id: awsSgId || null,
      aws_key_name: awsKeyName || null
    };
  }

  async function callNode(path){
    const plan = S.byId('node_out_plan');
    const cloud = S.byId('node_out_cloudinit');
    const raw = S.byId('node_out_raw');

    if(plan) plan.textContent = '…';
    if(cloud) cloud.textContent = '…';
    if(raw) raw.textContent = '…';

    try{
      const j = await CORE.api('POST', path, spawnPayload());
      if(plan) plan.textContent = JSON.stringify(j.plan || {}, null, 2);
      if(cloud) cloud.textContent = j.cloud_init || '—';
      if(raw) raw.textContent = JSON.stringify(j, null, 2);
      return j;
    }catch(e){
      const msg = String(e && e.message ? e.message : e);
      if(plan) plan.textContent = msg;
      if(cloud) cloud.textContent = '—';
      if(raw) raw.textContent = msg;
      throw e;
    }
  }

  function findNodeForUnit(nodesResp, unitPath){
    const items = (nodesResp && Array.isArray(nodesResp.items)) ? nodesResp.items : [];
    const matches = items.filter(function(n){
      return String(n.unit_path || '').trim() === String(unitPath || '').trim();
    });

    const active = matches.find(function(n){
      const aws = String(n.aws_state || '').trim().toLowerCase();
      const st = String(n.derived_status || n.status || '').trim().toLowerCase();
      if(aws === 'terminated' || st === 'terminated') return false;
      if(st === 'untracked') return false;
      return true;
    });

    return active || null;
  }

  function setLogoFallback(imgEl, unitPath){
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

  window.TAKS_UNIT.api = {
    loadUnitFromList,
    loadBrand,
    loadNodes,
    loadStatus,
    loadUnitFiles,
    saveBrand,
    uploadLogo,
    uploadUnitFile,
    spawnPayload,
    callNode,
    findNodeForUnit,
    setLogoFallback
  };
})();
