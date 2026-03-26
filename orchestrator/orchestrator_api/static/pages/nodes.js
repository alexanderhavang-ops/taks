/* global CORE */
(function(){

  function fmtAge(sec){
    if(sec == null) return '—';
    sec = Number(sec);
    if(sec < 60) return sec + 's';
    if(sec < 3600) return Math.floor(sec/60) + 'm';
    if(sec < 86400) return Math.floor(sec/3600) + 'h';
    return Math.floor(sec/86400) + 'd';
  }

  function statusBadge(st){
    const cls = {
      running: 'ok',
      booting: 'info',
      stale: 'warn',
      stopped: 'muted',
      unknown: 'err',
      untracked: 'warn',
      local: 'info',
      terminating: 'warn',
      terminated: 'err'
    }[st] || 'muted';

    const span = document.createElement('span');
    span.className = 'badge badge--' + cls;
    span.textContent = st || '—';
    return span;
  }

  async function deleteNode(id){
    if(!confirm(`Delete state for ${id}?`)) return;
    await CORE.api('DELETE', `/api/v2/nodes/${encodeURIComponent(id)}`);
    load();
  }

  async function terminateNode(id){
    if(!confirm(`Terminate AWS instance for ${id}?`)) return;
    try{
      const j = await CORE.api('POST', `/api/v2/nodes/${encodeURIComponent(id)}/terminate`, {});
      alert(`Terminate requested for ${id}\n\n${JSON.stringify(j.terminate || j || {}, null, 2)}`);
      load();
    }catch(e){
      const d = CORE.errorDetails ? CORE.errorDetails(e) : { msg: String((e && e.message) ? e.message : e), detail: '' };
      alert(`Terminate failed for ${id}\n\n${d.msg || 'Error'}${d.detail ? '\n\n' + d.detail : ''}`);
      throw e;
    }
  }

  function tdVal(v){
    const x = document.createElement('td');
    if(v instanceof Node) x.appendChild(v);
    else x.textContent = v ?? '—';
    return x;
  }

  function tdActions(n){
    const td = document.createElement('td');
    td.style.whiteSpace = 'nowrap';

    const st = String(n.derived_status || '').trim();
    const hasInstance = String(n.instance_id || n.aws_instance_id || '').trim().length > 0;

    if(hasInstance && st !== 'terminated' && st !== 'untracked'){
      const term = document.createElement('button');
      term.className = 'btn btn--danger';
      term.textContent = 'Terminate';
      term.onclick = () => terminateNode(n.node_id);
      td.appendChild(term);
    }else{
      td.textContent = '—';
    }

    return td;
  }

  function renderMainTable(tbody, nodes){
    if(!nodes?.length){
      tbody.innerHTML = `<tr><td colspan="9" class="muted">—</td></tr>`;
      return;
    }
    tbody.innerHTML = '';

    nodes.forEach(n=>{
      const tr = document.createElement('tr');

      const inst = n.aws_instance_id ?? n.instance_id ?? n.node_id;
      const pub  = n.aws_public_ip ?? n.public_ip;
      const priv = n.aws_private_ip ?? n.private_ip;

      tr.append(
        tdVal(n.unit_path ?? n.hostname ?? n.node_id),
        tdVal(n.role),
        tdVal(n.fqdn),
        tdVal(inst),
        tdVal(pub),
        tdVal(priv),
        tdVal(fmtAge(n.heartbeat_age_sec)),
        tdVal(statusBadge(n.derived_status)),
        tdActions(n)
      );

      tbody.appendChild(tr);
    });
  }

  function renderOrphaned(tbody, nodes){
    if(!nodes?.length){
      tbody.innerHTML = `<tr><td colspan="5" class="muted">—</td></tr>`;
      return;
    }
    tbody.innerHTML = '';

    nodes.forEach(n=>{
      const tr = document.createElement('tr');

      const btn = document.createElement('button');
      btn.className = 'btn btn--danger';
      btn.textContent = CORE.t('units.delete');
      btn.onclick = () => deleteNode(n.node_id);

      tr.append(
        tdVal(n.node_id),
        tdVal(fmtAge(n.heartbeat_age_sec)),
        tdVal(n.aws_state),
        tdVal(statusBadge(n.derived_status)),
        tdVal(btn)
      );

      tbody.appendChild(tr);
    });
  }

  async function load(){
    const activeBody = CORE.el('nodes_active_tbody');
    const untrackedBody = CORE.el('nodes_untracked_tbody');
    const orphanBody = CORE.el('nodes_orphaned_tbody');

    activeBody.innerHTML = `<tr><td colspan="9" class="muted">${CORE.t('common.loading')}</td></tr>`;
    untrackedBody.innerHTML = `<tr><td colspan="9" class="muted">${CORE.t('common.loading')}</td></tr>`;
    orphanBody.innerHTML = `<tr><td colspan="5" class="muted">${CORE.t('common.loading')}</td></tr>`;

    try{
      const j = await CORE.api('GET','/api/v2/nodes');
      const active = Array.isArray(j.items) ? j.items : [];
      const untracked = Array.isArray(j.untracked_items) ? j.untracked_items : [];
      const orphaned = Array.isArray(j.orphaned_items) ? j.orphaned_items : [];

      renderMainTable(activeBody, active);
      renderMainTable(untrackedBody, untracked);
      renderOrphaned(orphanBody, orphaned);
    }catch(e){
      const d = CORE.errorDetails(e);
      const msg = `${(d.msg || 'Error')}${d.detail ? '<br><br>' + d.detail : ''}`;
      activeBody.innerHTML = `<tr><td colspan="9">${msg}</td></tr>`;
      untrackedBody.innerHTML = '';
      orphanBody.innerHTML = '';
    }
  }

  window.PAGES = window.PAGES || {};
  window.PAGES.nodes = function(container){
    container.innerHTML=`
      <section class="card">
        <div class="card__head">
          <h3>${CORE.t('nodes.active')}</h3>
          <div class="card__actions">
            <button id="btn_refresh_nodes" class="btn btn--secondary">${CORE.t('nodes.refresh')}</button>
            <a class="btn" href="#/nodes/spawn">${CORE.t('nodes.spawn')}</a>
          </div>
        </div>

        <div class="tablewrap">
          <table class="table">
            <thead>
              <tr>
                <th>unit</th><th>role</th><th>fqdn</th><th>instance</th>
                <th>public</th><th>private</th><th>activity</th><th>status</th><th>action</th>
              </tr>
            </thead>
            <tbody id="nodes_active_tbody"></tbody>
          </table>
        </div>
      </section>

      <section class="card" style="margin-top:20px">
        <div class="card__head">
          <h3>Untracked nodes</h3>
        </div>

        <div class="tablewrap">
          <table class="table">
            <thead>
              <tr>
                <th>unit</th><th>role</th><th>fqdn</th><th>instance</th>
                <th>public</th><th>private</th><th>activity</th><th>status</th><th>action</th>
              </tr>
            </thead>
            <tbody id="nodes_untracked_tbody"></tbody>
          </table>
        </div>
      </section>

      <section class="card" style="margin-top:20px">
        <div class="card__head">
          <h3>${CORE.t('nodes.orphaned')}</h3>
        </div>

        <div class="tablewrap">
          <table class="table">
            <thead>
              <tr>
                <th>node</th><th>last seen</th><th>aws</th><th>status</th><th></th>
              </tr>
            </thead>
            <tbody id="nodes_orphaned_tbody"></tbody>
          </table>
        </div>
      </section>
    `;

    CORE.el('btn_refresh_nodes').onclick = load;
    load();
  };

})();
