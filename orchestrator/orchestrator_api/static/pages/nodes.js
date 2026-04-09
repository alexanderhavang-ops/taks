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
    if(!confirm(CORE.t('nodes.delete_state.confirm', { id }))) return;
    await CORE.api('DELETE', `/api/v2/nodes/${encodeURIComponent(id)}`);
    load();
  }

  async function terminateNode(id){
    if(!confirm('Terminera nod ' + id + '?\n\nTerminering innebär att du destruerar noden. DIN DATA KOMMER RADERAS. MKAY?')) return;
    try{
      const j = await CORE.api('POST', `/api/v2/nodes/${encodeURIComponent(id)}/terminate`, {});
      alert('Terminering begärd för ' + id + '\n\n' + JSON.stringify(j.terminate || j || {}, null, 2));
      load();
    }catch(e){
      const d = CORE.errorDetails ? CORE.errorDetails(e) : { msg: String((e && e.message) ? e.message : e), detail: '' };
      alert('Terminering misslyckades för ' + id + '\n\n' + (d.msg || CORE.t('common.error')) + (d.detail ? '\n\n' + d.detail : ''));
      throw e;
    }
  }

  async function snoozeNode(id){
    if(!confirm('Snooze/stoppa nod ' + id + '?\n\nDin runtime data överlever detta. Inget går förlorat på noden.\n\nKostnaden för denna nod när den sover är liten och begränsad till kostnaden för storage.')) return;
    try{
      const j = await CORE.api('POST', `/api/v2/nodes/${encodeURIComponent(id)}/snooze`, {});
      alert('Snooze begärd för ' + id + '\n\n' + JSON.stringify(j.snooze || j || {}, null, 2));
      load();
    }catch(e){
      const d = CORE.errorDetails ? CORE.errorDetails(e) : { msg: String((e && e.message) ? e.message : e), detail: '' };
      alert('Snooze misslyckades för ' + id + '\n\n' + (d.msg || CORE.t('common.error')) + (d.detail ? '\n\n' + d.detail : ''));
      throw e;
    }
  }

  async function wakeNode(id){
    if(!confirm('Väck stoppad nod ' + id + '?')) return;
    try{
      const j = await CORE.api('POST', `/api/v2/nodes/${encodeURIComponent(id)}/wake`, {});
      alert('Wake begärd för ' + id + '\n\n' + JSON.stringify(j.wake || j || {}, null, 2));
      load();
    }catch(e){
      const d = CORE.errorDetails ? CORE.errorDetails(e) : { msg: String((e && e.message) ? e.message : e), detail: '' };
      alert('Wake misslyckades för ' + id + '\n\n' + (d.msg || CORE.t('common.error')) + (d.detail ? '\n\n' + d.detail : ''));
      throw e;
    }
  }

  function tdVal(v){
    const x = document.createElement('td');
    if(v instanceof Node) x.appendChild(v);
    else x.textContent = v ?? '—';
    return x;
  }

  function tdUnitLink(n){
    const td = document.createElement('td');
    const unit = String((n && n.unit_path) || '').trim();
    if(unit){
      const a = document.createElement('a');
      a.href = '#/units/' + encodeURIComponent(unit);
      a.textContent = unit;
      td.appendChild(a);
      return td;
    }
    td.textContent = (n && (n.hostname ?? n.node_id)) ?? '—';
    return td;
  }

  function tdActions(n){
    const td = document.createElement('td');
    td.style.whiteSpace = 'nowrap';

    const st = String(n.derived_status || '').trim().toLowerCase();
    const aws = String(n.aws_state || '').trim().toLowerCase();
    const hasInstance = String(n.instance_id || n.aws_instance_id || '').trim().length > 0;

    if(!hasInstance || st === 'terminated' || st === 'untracked' || aws === 'terminated'){
      td.textContent = CORE.t('common.none');
      return td;
    }

    const addBtn = function(text, cls, onclick){
      const b = document.createElement('button');
      b.className = cls;
      b.textContent = text;
      b.onclick = onclick;
      if(td.childNodes.length) b.style.marginLeft = '8px';
      td.appendChild(b);
    };

    if(st === 'stopped' || aws === 'stopped'){
      addBtn('Wake', 'btn btn--secondary', () => wakeNode(n.node_id));
      addBtn('Terminera', 'btn btn--danger', () => terminateNode(n.node_id));
      return td;
    }

    if(st === 'running' || st === 'stale' || st === 'booting' || aws === 'running' || aws === 'pending'){
      addBtn('Snooze', 'btn btn--secondary', () => snoozeNode(n.node_id));
      addBtn('Terminera', 'btn btn--danger', () => terminateNode(n.node_id));
      return td;
    }

    addBtn('Terminera', 'btn btn--danger', () => terminateNode(n.node_id));
    return td;
  }

  function renderMainTable(tbody, nodes){
    if(!nodes?.length){
      tbody.innerHTML = `<tr><td colspan="9" class="muted">${CORE.t('common.none')}</td></tr>`;
      return;
    }
    tbody.innerHTML = '';

    nodes.forEach(n=>{
      const tr = document.createElement('tr');

      const inst = n.aws_instance_id ?? n.instance_id ?? n.node_id;
      const pub  = n.aws_public_ip ?? n.public_ip;
      const priv = n.aws_private_ip ?? n.private_ip;

      tr.append(
        tdUnitLink(n),
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
      tbody.innerHTML = `<tr><td colspan="5" class="muted">${CORE.t('common.none')}</td></tr>`;
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
                <th>${CORE.t('nodes.table.unit')}</th><th>${CORE.t('nodes.table.role')}</th><th>${CORE.t('nodes.table.fqdn')}</th><th>${CORE.t('nodes.table.instance')}</th>
                <th>${CORE.t('nodes.table.public')}</th><th>${CORE.t('nodes.table.private')}</th><th>${CORE.t('nodes.table.activity')}</th><th>${CORE.t('nodes.table.status')}</th><th>${CORE.t('nodes.table.action')}</th>
              </tr>
            </thead>
            <tbody id="nodes_active_tbody"></tbody>
          </table>
        </div>
      </section>

      <section class="card" style="margin-top:20px">
        <div class="card__head">
          <h3>${CORE.t('nodes.untracked')}</h3>
        </div>

        <div class="tablewrap">
          <table class="table">
            <thead>
              <tr>
                <th>${CORE.t('nodes.table.unit')}</th><th>${CORE.t('nodes.table.role')}</th><th>${CORE.t('nodes.table.fqdn')}</th><th>${CORE.t('nodes.table.instance')}</th>
                <th>${CORE.t('nodes.table.public')}</th><th>${CORE.t('nodes.table.private')}</th><th>${CORE.t('nodes.table.activity')}</th><th>${CORE.t('nodes.table.status')}</th><th>${CORE.t('nodes.table.action')}</th>
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
                <th>${CORE.t('nodes.table.node')}</th><th>${CORE.t('nodes.table.last_seen')}</th><th>aws</th><th>${CORE.t('nodes.table.status')}</th><th></th>
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
