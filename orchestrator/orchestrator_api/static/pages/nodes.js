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
      local: 'info'
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

  function renderActive(tbody, nodes){
    if(!nodes?.length){
      tbody.innerHTML = `<tr><td colspan="8" class="muted">no active nodes</td></tr>`;
      return;
    }
    tbody.innerHTML = '';

    nodes.forEach(n=>{
      const tr = document.createElement('tr');
      const td = v => {
        const x=document.createElement('td');
        if(v instanceof Node) x.appendChild(v);
        else x.textContent = v ?? '—';
        return x;
      };

      const inst = n.aws_instance_id ?? n.instance_id ?? n.node_id;
      const pub  = n.aws_public_ip ?? n.public_ip;
      const priv = n.aws_private_ip ?? n.private_ip;

      tr.append(
        td(n.unit_path ?? n.hostname ?? n.node_id),
        td(n.role),
        td(n.fqdn),
        td(inst),
        td(pub),
        td(priv),
        td(fmtAge(n.heartbeat_age_sec)),
        td(statusBadge(n.derived_status))
      );

      tbody.appendChild(tr);
    });
  }

  function renderOrphaned(tbody, nodes){
    if(!nodes?.length){
      tbody.innerHTML = `<tr><td colspan="6" class="muted">no orphaned nodes</td></tr>`;
      return;
    }
    tbody.innerHTML = '';

    nodes.forEach(n=>{
      const tr = document.createElement('tr');
      const td = v => {
        const x=document.createElement('td');
        if(v instanceof Node) x.appendChild(v);
        else x.textContent = v ?? '—';
        return x;
      };

      const btn = document.createElement('button');
      btn.className = 'btn btn--danger';
      btn.textContent = 'Delete';
      btn.onclick = () => deleteNode(n.node_id);

      tr.append(
        td(n.node_id),
        td(fmtAge(n.heartbeat_age_sec)),
        td(n.aws_state),
        td(statusBadge(n.derived_status)),
        td(btn)
      );

      tbody.appendChild(tr);
    });
  }

  async function load(){
    const activeBody = CORE.el('nodes_active_tbody');
    const orphanBody = CORE.el('nodes_orphaned_tbody');

    activeBody.innerHTML = `<tr><td colspan="8" class="muted">loading…</td></tr>`;
    orphanBody.innerHTML = `<tr><td colspan="6" class="muted">loading…</td></tr>`;

    try{
      const j = await CORE.api('GET','/api/v2/nodes');

      renderActive(activeBody, j.items);
      renderOrphaned(orphanBody, j.orphaned_items);

    }catch(e){
      activeBody.innerHTML = `<tr><td colspan="8">${e}</td></tr>`;
      orphanBody.innerHTML = '';
    }
  }

  window.PAGES.nodes = function(container){
    container.innerHTML=`

      <section class="card">
        <div class="card__head">
          <h3>Active nodes</h3>
          <div class="card__actions">
            <button id="btn_refresh_nodes" class="btn">Refresh</button>
            <a class="btn btn--secondary" href="#/nodes/new">New node</a>
          </div>
        </div>

        <div class="tablewrap">
          <table class="table">
            <thead>
              <tr>
                <th>unit</th><th>role</th><th>fqdn</th><th>instance</th>
                <th>public</th><th>private</th><th>activity</th><th>status</th>
              </tr>
            </thead>
            <tbody id="nodes_active_tbody"></tbody>
          </table>
        </div>
      </section>

      <section class="card" style="margin-top:20px">
        <div class="card__head">
          <h3>Orphaned nodes</h3>
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
