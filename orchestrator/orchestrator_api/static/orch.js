function el(id){ return document.getElementById(id); }

async function api(method, path, body){
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin'
  };
  if(body !== undefined){
    opts.body = JSON.stringify(body);
  }
  const r = await fetch(path, opts);
  const txt = await r.text();
  if(!r.ok){
    throw new Error(`HTTP ${r.status}\n${txt}`);
  }
  return txt ? JSON.parse(txt) : {};
}

function fmtTs(ts){
  if(!ts) return '—';
  try{ return new Date(ts * 1000).toISOString(); }
  catch{ return String(ts); }
}

function payload(){
  return {
    unit_path: el('unit_path').value.trim(),
    role: el('role').value.trim(),
    fqdn: el('fqdn').value.trim(),
    hostname: el('hostname').value.trim(),
    name: el('name').value.trim(),
    instance_type: el('instance_type').value.trim()
  };
}

// ---------------- Status ----------------
async function loadStatus(){
  const out = el('status_out');
  try{
    const j = await api('GET', '/api/v2/status');
    out.textContent = JSON.stringify(j, null, 2);

    const banner = el('banner_launch_disabled');
    if(j.launch_enabled !== true){
      banner.style.display = 'block';
      el('btn_launch').disabled = true;
    }else{
      banner.style.display = 'none';
      el('btn_launch').disabled = false;
    }
  }catch(e){
    out.textContent = String(e);
  }
}

// ---------------- Nodes list ----------------
async function loadNodes(){
  const tbody = el('nodes_tbody');
  tbody.innerHTML = `<tr><td class="muted" colspan="8">loading…</td></tr>`;

  try{
    const j = await api('GET', '/api/v2/nodes');
    if(!j.items || j.items.length === 0){
      tbody.innerHTML = `<tr><td class="muted" colspan="8">no registered nodes</td></tr>`;
      return;
    }

    tbody.innerHTML = '';
    for(const n of j.items){
      const tr = document.createElement('tr');

      function td(v){
        const x = document.createElement('td');
        x.textContent = v ?? '—';
        return x;
      }

      tr.appendChild(td(n.unit_path));
      tr.appendChild(td(n.role));
      tr.appendChild(td(n.fqdn));
      tr.appendChild(td(n.instance_id));
      tr.appendChild(td(n.public_ip));
      tr.appendChild(td(n.private_ip));
      tr.appendChild(td(fmtTs(n.last_seen_ts)));
      tr.appendChild(td(n.status));

      tbody.appendChild(tr);
    }

  }catch(e){
    tbody.innerHTML = `<tr><td colspan="8">${String(e)}</td></tr>`;
  }
}

// ---------------- Node actions ----------------
async function callNode(path){
  el('out_plan').textContent = '…';
  el('out_cloudinit').textContent = '…';
  el('out_raw').textContent = '…';

  try{
    const j = await api('POST', path, payload());
    el('out_plan').textContent = JSON.stringify(j.plan ?? {}, null, 2);
    el('out_cloudinit').textContent = j.cloud_init ?? '—';
    el('out_raw').textContent = JSON.stringify(j, null, 2);
  }catch(e){
    el('out_plan').textContent = String(e);
    el('out_cloudinit').textContent = '—';
    el('out_raw').textContent = String(e);
  }
}

// ---------------- Wiring ----------------
window.addEventListener('DOMContentLoaded', () => {

  el('btn_refresh_nodes').onclick = loadNodes;

  el('btn_preview').onclick  = () => callNode('/api/v2/nodes/preview');
  el('btn_dryrun').onclick   = () => callNode('/api/v2/nodes/dry-run');
  el('btn_launch').onclick   = () => callNode('/api/v2/nodes/launch');

  loadStatus();
  loadNodes();
});

