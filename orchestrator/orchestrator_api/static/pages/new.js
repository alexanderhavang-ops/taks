(function(){

  function qparam(name){
    try{
      const h = String(location.hash || '');
      const qpos = h.indexOf('?');
      const qs = qpos >= 0 ? h.slice(qpos + 1) : '';
      const p = new URLSearchParams(qs);
      return (p.get(name) || '').trim();
    }catch(_){
      return '';
    }
  }

  function payload(){
    const g = id => CORE.el(id)?.value.trim() || '';
    return {
      unit_path: g('unit_path'),
      role: g('role'),
      fqdn: g('fqdn'),
      hostname: g('hostname'),
      name: g('name'),
      instance_type: g('instance_type')
    };
  }

  function applyUnitDefaults(){
    const unit = qparam('unit');
    if(!unit) return;

    const unitEl = CORE.el('unit_path');
    const fqdnEl = CORE.el('fqdn');
    const hostEl = CORE.el('hostname');
    const nameEl = CORE.el('name');

    if(unitEl && !unitEl.value.trim()) unitEl.value = unit;

    if(fqdnEl && !fqdnEl.value.trim()){
      fqdnEl.value = unit + '.tak-hv-sandbox.se';
    }

    if(hostEl && !hostEl.value.trim()){
      hostEl.value = 'tak-' + unit;
    }

    if(nameEl && !nameEl.value.trim()){
      nameEl.value = 'tak-' + unit;
    }
  }

  async function call(path){
    const p = CORE.el('out_plan');
    const c = CORE.el('out_cloudinit');
    const r = CORE.el('out_raw');
    if(p) p.textContent = '…';
    if(c) c.textContent = '…';
    if(r) r.textContent = '…';
    try{
      const j = await CORE.api('POST', path, payload());
      if(p) p.textContent = JSON.stringify(j.plan || {}, null, 2);
      if(c) c.textContent = j.cloud_init || '—';
      if(r) r.textContent = JSON.stringify(j, null, 2);
    }catch(e){
      if(p) p.textContent = String(e);
      if(c) c.textContent = '—';
      if(r) r.textContent = String(e);
    }
  }

  window.PAGES = window.PAGES || {};
  window.PAGES.new = function(container){
    const unit = qparam('unit');

    container.innerHTML = `
      <div id="banner_launch_disabled" class="banner banner--warn" style="display:none">
        <b>Launch disabled</b>
      </div>

      <section class="card">
        <div class="card__head">
          <h3>Skapa nod${unit ? ` för ${unit}` : ''}</h3>
          <div class="card__actions">
            <a class="btn btn--secondary" href="${unit ? '#/units/' + encodeURIComponent(unit) : '#/nodes'}">Tillbaka</a>
            <button id="btn_preview" class="btn">Preview</button>
            <button id="btn_dryrun" class="btn btn--secondary">Dry-run</button>
            <button id="btn_launch" class="btn btn--danger">Launch</button>
          </div>
        </div>

        <div class="grid grid--6">
          <div><label class="label">unit_path</label><input id="unit_path"></div>
          <div><label class="label">role</label><input id="role" value="tak-node"></div>
          <div><label class="label">fqdn</label><input id="fqdn"></div>
          <div><label class="label">hostname</label><input id="hostname"></div>
          <div><label class="label">name</label><input id="name"></div>
          <div><label class="label">instance_type</label><input id="instance_type" value="t3.small"></div>
        </div>

        <details open><summary>Plan</summary><pre id="out_plan">—</pre></details>
        <details><summary>Cloud-init</summary><pre id="out_cloudinit">—</pre></details>
        <details><summary>Raw</summary><pre id="out_raw">—</pre></details>
      </section>
    `;

    applyUnitDefaults();

    CORE.el('btn_preview').onclick = () => call('/api/v2/nodes/preview');
    CORE.el('btn_dryrun').onclick = () => call('/api/v2/nodes/dry-run');
    CORE.el('btn_launch').onclick = () => call('/api/v2/nodes/launch');
  };

})();
