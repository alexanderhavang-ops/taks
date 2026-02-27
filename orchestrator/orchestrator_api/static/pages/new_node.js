(function(){
  function payload(){
    return {
      unit_path: TAKS.el('unit_path')?.value.trim() ?? '',
      role: TAKS.el('role')?.value.trim() ?? '',
      fqdn: TAKS.el('fqdn')?.value.trim() ?? '',
      hostname: TAKS.el('hostname')?.value.trim() ?? '',
      name: TAKS.el('name')?.value.trim() ?? '',
      instance_type: TAKS.el('instance_type')?.value.trim() ?? ''
    };
  }

  async function callNode(path){
    const outPlan = TAKS.el('out_plan');
    const outCloud = TAKS.el('out_cloudinit');
    const outRaw = TAKS.el('out_raw');
    if(outPlan) outPlan.textContent = '…';
    if(outCloud) outCloud.textContent = '…';
    if(outRaw) outRaw.textContent = '…';

    try{
      const j = await TAKS.api('POST', path, payload());
      if(outPlan) outPlan.textContent = JSON.stringify(j.plan ?? {}, null, 2);
      if(outCloud) outCloud.textContent = j.cloud_init ?? '—';
      if(outRaw) outRaw.textContent = JSON.stringify(j, null, 2);
    }catch(e){
      if(outPlan) outPlan.textContent = String(e);
      if(outCloud) outCloud.textContent = '—';
      if(outRaw) outRaw.textContent = String(e);
    }
  }

  function render(container){
    container.innerHTML = `
      <div id="banner_launch_disabled" class="banner banner--warn" style="display:none">
        <b>Launch disabled</b> — set <code>TAKS_LAUNCH_ENABLED=1</code> in <code>/opt/tak-orch/state/defaults.env</code> to enable.
      </div>

      <section class="card">
        <div class="card__head">
          <h3>New node creation</h3>
          <div class="card__actions">
            <a class="btn btn--secondary" href="#/nodes">Back</a>
            <button id="btn_preview" class="btn">Preview</button>
            <button id="btn_dryrun" class="btn btn--secondary">Dry-run</button>
            <button id="btn_launch" class="btn btn--danger">Launch</button>
          </div>
        </div>

        <div class="muted">
          <b>Preview</b> renders the plan + cloud-init. <b>Dry-run</b> performs an AWS dry-run. <b>Launch</b> creates the instance.
        </div>

        <div class="spacer"></div>

        <div class="grid grid--6">
          <div>
            <label class="label">unit_path</label>
            <input id="unit_path" placeholder="e.g. 46hvbat" value="">
          </div>
          <div>
            <label class="label">role</label>
            <input id="role" placeholder="e.g. tak-node" value="tak-node">
          </div>
          <div>
            <label class="label">fqdn</label>
            <input id="fqdn" placeholder="e.g. 46hvbat.tak-hv-sandbox.se" value="">
          </div>
          <div>
            <label class="label">hostname</label>
            <input id="hostname" placeholder="default: tak-&lt;unit_path&gt;" value="">
          </div>
          <div>
            <label class="label">name (AWS tag)</label>
            <input id="name" placeholder="default: hostname" value="">
          </div>
          <div>
            <label class="label">instance_type</label>
            <input id="instance_type" placeholder="e.g. t3.micro" value="t3.micro">
          </div>
        </div>

        <div class="spacer"></div>

        <details open>
          <summary>Plan (summary)</summary>
          <pre id="out_plan">—</pre>
        </details>

        <details>
          <summary>Cloud-init</summary>
          <pre id="out_cloudinit">—</pre>
        </details>

        <details>
          <summary>Raw response</summary>
          <pre id="out_raw">—</pre>
        </details>
      </section>
    `;

    TAKS.el('btn_preview').onclick = () => callNode('/api/v2/nodes/preview');
    TAKS.el('btn_dryrun').onclick  = () => callNode('/api/v2/nodes/dry-run');
    TAKS.el('btn_launch').onclick  = () => callNode('/api/v2/nodes/launch');
  }

  window.TAKS_PAGES = window.TAKS_PAGES || {};
  window.TAKS_PAGES.new_node = { render };
})();
