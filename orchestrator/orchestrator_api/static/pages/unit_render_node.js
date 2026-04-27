/* global CORE */

(function(){

  window.TAKS_UNIT = window.TAKS_UNIT || {};

  const S = window.TAKS_UNIT.shared;

  const A = window.TAKS_UNIT.api;


  function render(){
    return window.TAKS_UNIT.render.apply(null, arguments);
  }

  function renderNodeSummary(){
    return window.TAKS_UNIT.renderNodeSummary.apply(null, arguments);
  }

  function nodeStatusSnapshot(){
    return window.TAKS_UNIT.nodeStatusSnapshot.apply(null, arguments);
  }

  function clearInstallProgressState(){
    return window.TAKS_UNIT.clearInstallProgressState.apply(null, arguments);
  }

  function encodePathValue(v){
    return String(v || '').split('/').filter(Boolean).map(function(x){ return encodeURIComponent(x); }).join('/');
  }

  function backupUnit(node){
    return String((node && (node.unit || node.unit_path)) || (S.getRouteUnitPath ? S.getRouteUnitPath() : '') || '').trim();
  }

  function backupNodeId(node){
    return String((node && (node.node_id || node.fqdn || node.instance_id)) || '').trim();
  }

  function backupArtifactUrl(unit, backupId){
    return '/api/v2/units/' + encodePathValue(unit) + '/backups/' + encodeURIComponent(String(backupId || '')) + '/artifact';
  }

  function backupManifestUrl(unit, backupId){
    return '/api/v2/units/' + encodePathValue(unit) + '/backups/' + encodeURIComponent(String(backupId || '')) + '/manifest';
  }

  function backupHumanBytes(v){
    var n = Number(v || 0);
    if(!(n > 0)) return '0 B';
    if(n >= 1024 * 1024 * 1024) return (n / (1024 * 1024 * 1024)).toFixed(2) + ' GB';
    if(n >= 1024 * 1024) return (n / (1024 * 1024)).toFixed(2) + ' MB';
    if(n >= 1024) return (n / 1024).toFixed(1) + ' KB';
    return String(n) + ' B';
  }

  async function backupFetchJson(url, opts){
    var init = Object.assign({ credentials: 'same-origin' }, opts || {});
    init.headers = Object.assign({ Accept: 'application/json' }, (opts && opts.headers) || {});
    var resp = await fetch(url, init);
    var text = await resp.text();
    var obj = {};
    if(text){
      try{
        obj = JSON.parse(text);
      }catch(err){
        if(!resp.ok) throw new Error(text || ('HTTP ' + resp.status));
        throw new Error('Invalid JSON from ' + url);
      }
    }
    if(!resp.ok){
      throw new Error(String((obj && obj.detail) || text || ('HTTP ' + resp.status)));
    }
    return obj || {};
  }

  async function refreshBackupList(node){
    var unit = backupUnit(node);
    var el = S.byId('node_backup_list');
    if(!el || !unit) return;
    el.innerHTML = '';
    el.appendChild(S.el('div', { className: 'muted', text: 'Laddar…' }));
    try{
      var j = await backupFetchJson('/api/v2/units/' + encodePathValue(unit) + '/backups');
      var rows = Array.isArray(j.backups) ? j.backups : [];

      // ---- NONE OPTION (fresh node) ----
      var noneSelected = !rows.some(function(r){ return r && r.selected_for_restore; });

      var noneItem = S.el('div', {
        style: [
          'display:grid',
          'grid-template-columns:minmax(0,1fr) auto',
          'gap:12px',
          'align-items:center',
          'padding:12px',
          'border-radius:12px',
          'border:1px solid ' + (noneSelected ? 'rgba(34,197,94,.35)' : 'rgba(255,255,255,.08)'),
          'background:' + (noneSelected ? 'rgba(34,197,94,.07)' : 'rgba(255,255,255,.02)')
        ].join(';')
      });

      var noneLeft = S.el('div');
      noneLeft.appendChild(S.el('div', {
        style: 'font-weight:700',
        text: 'None (fresh node)'
      }));
      noneLeft.appendChild(S.el('div', {
        className: noneSelected ? 'ok' : 'muted',
        style: 'margin-top:4px',
        text: noneSelected ? 'no restore will be applied' : 'skip restore'
      }));

      noneItem.appendChild(noneLeft);

      var noneActions = S.el('div', { className: 'card__actions', style: 'justify-content:flex-end' });

      var btnNone = S.el('button', {
        className: noneSelected ? 'btn' : 'btn btn--secondary',
        text: noneSelected ? 'Selected' : 'Use none'
      });
      btnNone.disabled = noneSelected;

      btnNone.addEventListener('click', function(){
        btnNone.disabled = true;
        backupFetchJson('/api/v2/units/' + encodePathValue(unit) + '/backups/restore-selection', {
          method: 'DELETE'
        }).then(refreshList).catch(function(err){
          alert(String((err && err.message) || err || 'Clear failed'));
          btnNone.disabled = false;
        });
      });

      noneActions.appendChild(btnNone);
      noneItem.appendChild(noneActions);

      listEl.appendChild(noneItem);

      listEl.appendChild(S.el('div', {
        style: 'height:1px;background:rgba(255,255,255,.06);margin:4px 0'
      }));

      el.innerHTML = '';
      if(!rows.length){
        el.appendChild(S.el('div', { className: 'muted', text: 'Inga sparade säkerhetskopior än.' }));
        return;
      }
      rows.forEach(function(row){
        var backupId = String((row && row.backup_id) || '').trim();
        var artifactUrl = String((row && row.artifact_url) || backupArtifactUrl(unit, backupId));
        var manifestUrl = String((row && row.manifest_url) || backupManifestUrl(unit, backupId));
        var item = S.el('div', {
          style: 'padding:10px 12px;border-radius:10px;border:1px solid rgba(255,255,255,.08);background:rgba(255,255,255,.03)'
        });
        item.appendChild(S.el('div', {
          style: 'font-weight:600;word-break:break-all',
          text: backupId || 'backup'
        }));
        var meta = [];
        if(row && row.created_at) meta.push(String(row.created_at));
        meta.push(backupHumanBytes(row && row.size_bytes));
        item.appendChild(S.el('div', {
          className: 'muted',
          style: 'margin-top:4px',
          text: meta.join(' · ')
        }));
        var actions = S.el('div', { className: 'card__actions', style: 'margin-top:8px' });
        actions.appendChild(S.el('a', {
          className: 'btn btn--secondary',
          href: artifactUrl,
          target: '_blank',
          rel: 'noopener noreferrer',
          text: 'Download'
        }));
        actions.appendChild(S.el('a', {
          className: 'btn btn--secondary',
          href: manifestUrl,
          target: '_blank',
          rel: 'noopener noreferrer',
          text: 'Manifest'
        }));
        item.appendChild(actions);
        el.appendChild(item);
      });
    }catch(err){
      el.innerHTML = '';
      el.appendChild(S.el('div', {
        className: 'err',
        text: String((err && err.message) || err || 'Backup list failed')
      }));
    }
  }

  function renderNodeCard(node){
    const c = S.card(CORE.t('unit.server_node'));

    c.appendChild(renderNodeSummary(node));

    const aws = String((node && node.aws_state) || '').trim().toLowerCase();
    const hb = String(S.heartbeatState(node) || '').trim().toLowerCase();
    const nodeId = String((node && (node.node_id || node.fqdn || node.instance_id)) || '').trim();
    const fqdn = String((node && node.fqdn) || '').trim();
    const derivedStatus = String((node && node.derived_status) || '').trim().toLowerCase();

    const isStopped = !!nodeId && (aws === 'stopped' || derivedStatus === 'stopped');
    const isLiveish = !!nodeId && (
      aws === 'running' ||
      aws === 'pending' ||
      derivedStatus === 'running' ||
      derivedStatus === 'stale' ||
      derivedStatus === 'booting'
    );

    const snap = nodeStatusSnapshot(node);
    const statusTone = snap.tone;
    const statusText = snap.text;

    if(statusTone === 'err'){
      c.style.border = '1px solid rgba(239, 68, 68, .38)';
      c.style.boxShadow = '0 0 0 1px rgba(239, 68, 68, .12) inset';
    }else if(statusTone === 'warn'){
      c.style.border = '1px solid rgba(245, 158, 11, .38)';
      c.style.boxShadow = '0 0 0 1px rgba(245, 158, 11, .12) inset';
    }else if(statusTone === 'ok'){
      c.style.border = '1px solid rgba(34, 197, 94, .28)';
      c.style.boxShadow = '0 0 0 1px rgba(34, 197, 94, .10) inset';
    }

    if(fqdn){
      const linksWrap = S.el('div', { style: 'margin-top:12px' });
      linksWrap.appendChild(S.el('div', { className: 'label', text: CORE.t('unit.quick_links') }));

      const links = S.el('div', { className: 'card__actions', style: 'margin-top:8px' });

      function quickLink(text, href, secondary){
        if(isStopped){
          return S.el('span', {
            className: secondary ? 'btn btn--secondary' : 'btn',
            style: 'opacity:.45;pointer-events:none;cursor:not-allowed',
            title: 'Wake node to enable quick links',
            text: text
          });
        }
        return S.el('a', {
          className: secondary ? 'btn btn--secondary' : 'btn',
          href: href,
          target: '_blank',
          rel: 'noopener noreferrer',
          text: text
        });
      }

      links.appendChild(quickLink('TAKS', 'https://' + fqdn + '/', false));
      links.appendChild(quickLink('WebTAK', 'https://' + fqdn + ':8446/webtak/', true));
      links.appendChild(quickLink('Marti', 'https://' + fqdn + ':8446/Marti/', true));
      linksWrap.appendChild(links);
      c.appendChild(linksWrap);
    }

    const actionsWrap = S.el('div', { style: 'margin-top:14px' });
    actionsWrap.appendChild(S.el('div', { className: 'label', text: 'Åtgärder' }));

    const actions = S.el('div', { className: 'card__actions', style: 'margin-top:8px' });
    actions.appendChild(S.el('button', {
      id: 'node_refresh_btn',
      className: 'btn btn--secondary',
      text: 'Uppdatera'
    }));

    const awsState = String((node && node.aws_state) || '').trim().toLowerCase();

    if(isStopped){
      actions.appendChild(S.el('button', {
        id: 'node_wake_btn',
        className: 'btn',
        text: 'Wake',
        'data-node-id': nodeId
      }));
      actions.appendChild(S.el('button', {
        id: 'node_terminate_btn',
        className: 'btn btn--danger',
        text: 'Terminera',
        'data-node-id': nodeId
      }));
    }else if(isLiveish){
      actions.appendChild(S.el('button', {
        id: 'node_snooze_btn',
        className: 'btn btn--secondary',
        text: 'Snooze',
        'data-node-id': nodeId
      }));
      actions.appendChild(S.el('button', {
        id: 'node_terminate_btn',
        className: 'btn btn--danger',
        text: 'Terminera',
        'data-node-id': nodeId
      }));
    }else{
      actions.appendChild(S.el('button', {
        id: 'node_launch_btn',
        className: 'btn btn--danger',
        text: 'Starta'
      }));
    }

    actionsWrap.appendChild(actions);
    actionsWrap.appendChild(S.el('div', {
      id: 'node_action_status',
      className: 'muted',
      style: 'margin-top:8px'
    }));
    actionsWrap.appendChild(S.el('div', {
      id: 'node_launch_info',
      className: 'muted',
      style: 'margin-top:6px;display:grid;gap:4px'
    }));
    c.appendChild(actionsWrap);

    const advanced = S.el('details', { style: 'margin-top:14px' });
    advanced.appendChild(S.el('summary', { text: 'Avancerat' }));

    advanced.appendChild(S.el('div', {
      className: 'muted',
      style: 'margin-top:10px',
      text: 'Servern byggs från enhetens arvade identitet, filer och konfiguration.'
    }));

    const grid = S.el('div', { className: 'grid grid--6', style: 'margin-top:12px' });

    const nameCol = S.el('div', { style: 'grid-column: span 2;' });
    nameCol.appendChild(S.el('label', { className: 'label', text: 'Display name' }));
    const defaultUnitName = String((node && node.unit_path) || S.getRouteUnitPath() || 'node');
    nameCol.appendChild(S.el('input', {
      id: 'node_display_name',
      value: String((node && (((node.meta || {}).name) || node.display_name)) || defaultUnitName || String((node && node.fqdn) || 'node'))
    }));
    grid.appendChild(nameCol);

    const typeCol = S.el('div', { style: 'grid-column: span 2;' });
    typeCol.appendChild(S.el('label', { className: 'label', text: 'AWS size' }));
    const sel = S.el('select', { id: 'node_instance_type' });
    const launchDefaults = (((window.TAKS_UNIT || {}).launchDefaults) || {});
    const cur = String(
      (node && (node.instance_type || ((node.meta || {}).instance_type))) ||
      ((window.CORE && window.CORE.aws_default_instance_type) || '') ||
      launchDefaults.instance_type ||
      launchDefaults.aws_default_instance_type ||
      ((launchDefaults.core || {}).aws_default_instance_type) ||
      't3.small'
    );
    ['t3.small', 't3.medium', 't3.large'].forEach(function(x){
      const opt = S.el('option', { value: x, text: x });
      if(x === cur) opt.selected = true;
      sel.appendChild(opt);
    });
    typeCol.appendChild(sel);
    grid.appendChild(typeCol);
    advanced.appendChild(grid);

    const advGrid = S.el('div', { className: 'grid grid--6', style: 'margin-top:12px' });
    advGrid.appendChild(S.field('FQDN', S.el('input', {
      id: 'node_fqdn',
      value: String((node && node.fqdn) || (S.getRouteUnitPath() + '.aws.tak-hv-sandbox.se'))
    }), 3));
    advGrid.appendChild(S.field('AWS SG override', S.el('input', {
      id: 'node_aws_sg_id',
      value: String((node && (((node.meta || {}).sg_id) || node.subnet_id)) ? (((node.meta || {}).sg_id) || '') : ''),
      placeholder: 'default from orchestrator config'
    }), 2));
    advGrid.appendChild(S.field('AWS key override', S.el('input', {
      id: 'node_aws_key_name',
      value: '',
      placeholder: 'default from orchestrator config'
    })));
    advanced.appendChild(advGrid);

    const defaultsGrid = S.el('div', { className: 'grid grid--6', style: 'margin-top:12px' });
    defaultsGrid.appendChild(S.field(CORE.t('unit.field.region'), S.el('div', { id: 'node_default_region', text: '—' })));
    defaultsGrid.appendChild(S.field('AMI', S.el('div', { id: 'node_default_ami', style: 'word-break:break-all', text: '—' }), 2));
    defaultsGrid.appendChild(S.field('Subnet', S.el('div', { id: 'node_default_subnet', text: '—' }), 2));
    defaultsGrid.appendChild(S.field('Security group', S.el('div', { id: 'node_default_sg', text: '—' }), 2));
    defaultsGrid.appendChild(S.field(CORE.t('unit.field.iam_profile'), S.el('div', { id: 'node_default_profile', style: 'word-break:break-all', text: '—' }), 3));
    defaultsGrid.appendChild(S.field('Key pair', S.el('div', { id: 'node_default_key', text: '—' })));
    advanced.appendChild(defaultsGrid);

    const advActions = S.el('div', { className: 'card__actions', style: 'margin-top:12px' });
    advActions.appendChild(S.el('button', { id: 'node_preview_btn', className: 'btn btn--secondary', text: 'Förhandsvisa' }));
    advActions.appendChild(S.el('button', { id: 'node_dryrun_btn', className: 'btn btn--secondary', text: 'Torrkör' }));
    advanced.appendChild(advActions);

    advanced.appendChild(S.el('details', { style: 'margin-top:12px' },
      S.el('summary', { text: 'Plan' }),
      S.el('pre', { id: 'node_out_plan', text: '—' })
    ));
    advanced.appendChild(S.el('details', null,
      S.el('summary', { text: 'Cloud-init' }),
      S.el('pre', { id: 'node_out_cloudinit', text: '—' })
    ));
    advanced.appendChild(S.el('details', null,
      S.el('summary', { text: 'Raw' }),
      S.el('pre', { id: 'node_out_raw', text: '—' })
    ));

    c.appendChild(advanced);
    return c;
  }

  function setNodeActionStatus(text, cls){
    const el = S.byId('node_action_status');
    if(!el) return;
    el.textContent = String(text || '');
    el.className = cls || 'muted';
  }

  function setNodeLaunchInfo(info){
    const el = S.byId('node_launch_info');
    if(!el) return;
    if(!info){
      el.innerHTML = '';
      return;
    }

    const bits = [];
    if(info.instance_id) bits.push('instans: ' + String(info.instance_id));
    if(info.private_ip) bits.push('privat IP: ' + String(info.private_ip));
    if(info.public_ip) bits.push('publik IP: ' + String(info.public_ip));
    if(info.fqdn) bits.push('FQDN: ' + String(info.fqdn));

    el.innerHTML = '';
    bits.forEach(function(x, idx){
      const row = S.el('div', { className: 'muted', text: x });
      el.appendChild(row);
      if(idx === bits.length - 1 && info.dns_change && info.dns_change.Status){
        el.appendChild(S.el('div', {
          className: 'muted',
          text: 'DNS: ' + String(info.dns_change.Status)
        }));
      }
    });
  }

  async function startNodeProgressPoll(unitPath){
    const started = Date.now();
    const maxMs = 120000;

    async function tick(){
      try{
        const nodesResp = await A.loadNodes();
        const node = A.findNodeForUnit(nodesResp, unitPath);

        if(!node){
          if(Date.now() - started < maxMs){
            setNodeActionStatus('Väntar på att noden ska dyka upp…', 'muted');
            setTimeout(tick, 2500);
          }
          return;
        }

        const aws = String(node.aws_state || '').trim().toLowerCase();
        const hb = String(S.heartbeatState(node) || '').trim().toLowerCase();

        if(hb === 'online'){
          setNodeActionStatus('Nod online.', 'ok');
          render();
          return;
        }

        if(aws === 'running'){
          setNodeActionStatus('Instans igång. Väntar på första heartbeat…', 'muted');
        }else if(aws === 'pending'){
          setNodeActionStatus('Instans skapad. Väntar på att AWS ska starta den…', 'muted');
        }else{
          clearInstallProgressState(node, c);
          clearInstallProgressState(node, c);
          setNodeActionStatus('Start begärd. Väntar på status…', 'muted');
        }

        if(Date.now() - started < maxMs){
          setTimeout(tick, 2500);
        }else{
          setNodeActionStatus('Fortfarande ingen färdig nodstatus. Prova Uppdatera.', 'warn');
          render();
        }
      }catch(_e){
        if(Date.now() - started < maxMs){
          setTimeout(tick, 3000);
        }
      }
    }

    setTimeout(tick, 1200);
  }

  function wireNodeActions(){
    const previewBtn = S.byId('node_preview_btn');
    const dryrunBtn = S.byId('node_dryrun_btn');
    const launchBtn = S.byId('node_launch_btn');
    const wakeBtn = S.byId('node_wake_btn');
    const snoozeBtn = S.byId('node_snooze_btn');
    const refreshBtn = S.byId('node_refresh_btn');
    const terminateBtn = S.byId('node_terminate_btn');

    if(previewBtn) previewBtn.onclick = function(){ A.callNode('/api/v2/nodes/preview'); };
    if(dryrunBtn) dryrunBtn.onclick = function(){ A.callNode('/api/v2/nodes/dry-run'); };

    if(refreshBtn){
      refreshBtn.onclick = function(){
        setNodeActionStatus('Uppdaterar…', 'muted');
        render();
      };
    }

    if(launchBtn){
      launchBtn.onclick = async function(){
        setNodeActionStatus('Startar… förbereder bundle och begär AWS-instans…', 'muted');
        setNodeLaunchInfo(null);
        try{
          const j = await A.callNode('/api/v2/nodes/launch');
          if(j && j.launch){
            setNodeLaunchInfo(j.launch);
                setNodeActionStatus('Start begärd. Väntar på bundle-hämtning och första heartbeat…', 'ok');
          }else{
                setNodeActionStatus('Start begärd. Väntar på första heartbeat…', 'ok');
          }
          startNodeProgressPoll(S.getRouteUnitPath());
        }catch(e){
          const msg = String(e && e.message ? e.message : e);
          setNodeActionStatus(msg, 'err');
          alert(msg);
        }
      };
    }

    if(wakeBtn){
      wakeBtn.onclick = async function(){
        const nodeId = String(wakeBtn.getAttribute('data-node-id') || '').trim();
        if(!nodeId) return;
        if(!confirm('Väck stoppad nod ' + nodeId + '?')) return;

        setNodeActionStatus('Wake begärs… väntar på AWS-start och DNS-refresh…', 'muted');
        setNodeLaunchInfo(null);

        try{
          const j = await CORE.api('POST', '/api/v2/nodes/' + encodeURIComponent(nodeId) + '/wake', {});
          if(j && j.wake) setNodeLaunchInfo(j.wake);
          setNodeActionStatus('Wake begärd. Väntar på heartbeat…', 'ok');
          startNodeProgressPoll(S.getRouteUnitPath());
          setTimeout(function(){ render(); }, 700);
        }catch(e){
          const msg = String(e && e.message ? e.message : e);
          setNodeActionStatus(msg, 'err');
          alert(msg);
        }
      };
    }

    if(snoozeBtn){
      snoozeBtn.onclick = async function(){
        const nodeId = String(snoozeBtn.getAttribute('data-node-id') || '').trim();
        if(!nodeId) return;
        if(!confirm('Snooze/stoppa nod ' + nodeId + '?\n\nDin runtime data överlever detta. Inget går förlorat på noden.\n\nKostnaden för denna nod när den sover är liten och begränsad till kostnaden för storage.')) return;

        setNodeActionStatus('Snooze begärs… stoppar instans och flyttar DNS…', 'muted');

        try{
          const j = await CORE.api('POST', '/api/v2/nodes/' + encodeURIComponent(nodeId) + '/snooze', {});
          if(j && j.snooze) setNodeLaunchInfo(j.snooze);
          setNodeActionStatus('Snooze begärd.', 'ok');
          setTimeout(function(){ render(); }, 700);
        }catch(e){
          const msg = String(e && e.message ? e.message : e);
          setNodeActionStatus(msg, 'err');
          alert(msg);
        }
      };
    }

    if(terminateBtn){
      terminateBtn.onclick = async function(){
        const nodeId = String(terminateBtn.getAttribute('data-node-id') || '').trim();
        if(!nodeId) return;
        if(!confirm('Terminera nod ' + nodeId + '?\n\nTerminering innebär att du destruerar noden. DIN DATA KOMMER RADERAS. MKAY?')) return;

        setNodeActionStatus('Terminerar…', 'muted');

        try{
          await CORE.api('POST', '/api/v2/nodes/' + encodeURIComponent(nodeId) + '/terminate', {});
          setNodeActionStatus('Terminering begärd.', 'ok');
          alert('Terminering begärd för ' + nodeId);
          setTimeout(function(){ render(); }, 700);
        }catch(e){
          const msg = String(e && e.message ? e.message : e);
          setNodeActionStatus(msg, 'err');
          alert(msg);
        }
      };
    }
  }

  window.TAKS_UNIT.renderNodeCard = renderNodeCard;

  window.TAKS_UNIT.wireNodeActions = wireNodeActions;



  
  /* BACKUPS_TAB_V1_START */

  function backupAutoDownload(url){
    var href = String(url || '').trim();
    if(!href) return;
    var a = document.createElement('a');
    a.href = href;
    a.style.display = 'none';
    a.setAttribute('download', '');
    document.body.appendChild(a);
    a.click();
    setTimeout(function(){ if(a.parentNode) a.parentNode.removeChild(a); }, 0);
  }

  function renderBackupsPanel(node){
    var unit = backupUnit(node);
    var nodeId = backupNodeId(node);
    var wrap = S.el('div', { style: 'display:grid;gap:14px' });
    var card = S.card('Backups');

    var top = S.el('div', {
      style: 'display:flex;justify-content:space-between;gap:10px;align-items:center;flex-wrap:wrap'
    });
    top.appendChild(S.el('div', {
      className: 'muted',
      text: 'Backup files live in this unit’s orchestrator state. Select one to restore on next spawn.'
    }));

    var actions = S.el('div', { className: 'card__actions' });
    var upload = S.el('input', { type: 'file', accept: '.gz,.tgz,.tar.gz', style: 'display:none' });
    var btnUpload = S.el('button', { className: 'btn btn--secondary', text: 'Upload' });
    var btnRefresh = S.el('button', { className: 'btn btn--secondary', text: 'Refresh' });
    actions.appendChild(upload);
    actions.appendChild(btnUpload);
    actions.appendChild(btnRefresh);
    top.appendChild(actions);
    card.appendChild(top);

    var create = S.el('details', { style: 'margin-top:12px' });
    create.appendChild(S.el('summary', { text: 'Create backup from live node' }));
    var createActions = S.el('div', { className: 'card__actions', style: 'margin-top:10px' });
    var btnCreate = S.el('button', { className: 'btn', text: 'Backup users' });
    createActions.appendChild(btnCreate);
    create.appendChild(createActions);
    var status = S.el('div', { className: 'muted', style: 'margin-top:8px' });
    create.appendChild(status);
    if(!nodeId){
      btnCreate.disabled = true;
      btnCreate.style.opacity = '.55';
      status.textContent = 'No live node available.';
    }
    card.appendChild(create);

    var listEl = S.el('div', { style: 'margin-top:14px;display:grid;gap:8px' });
    card.appendChild(listEl);

    function setStatus(text, cls){
      status.className = cls || 'muted';
      status.textContent = String(text || '');
    }

    async function refreshList(){
      listEl.innerHTML = '';
      listEl.appendChild(S.el('div', { className: 'muted', text: 'Loading backups…' }));

      var j = await backupFetchJson('/api/v2/units/' + encodePathValue(unit) + '/backups');
      var rows = Array.isArray(j.backups) ? j.backups : [];
      listEl.innerHTML = '';

      if(!rows.length){
        listEl.appendChild(S.el('div', {
          className: 'muted',
          style: 'padding:12px;border:1px dashed rgba(255,255,255,.14);border-radius:12px',
          text: 'No backups yet.'
        }));
        return;
      }

      rows.forEach(function(row){
        var backupId = String((row && row.backup_id) || '').trim();
        var artifactUrl = String((row && row.artifact_url) || backupArtifactUrl(unit, backupId));
        var selected = !!(row && row.selected_for_restore);

        var item = S.el('div', {
          style: [
            'display:grid',
            'grid-template-columns:minmax(0,1fr) auto',
            'gap:12px',
            'align-items:center',
            'padding:12px',
            'border-radius:12px',
            'border:1px solid ' + (selected ? 'rgba(34,197,94,.35)' : 'rgba(255,255,255,.08)'),
            'background:' + (selected ? 'rgba(34,197,94,.07)' : 'rgba(255,255,255,.03)')
          ].join(';')
        });

        var left = S.el('div', { style: 'min-width:0' });
        left.appendChild(S.el('div', {
          style: 'font-weight:700;word-break:break-all',
          text: backupId || 'backup'
        }));

        var meta = [];
        if(row && row.created_at) meta.push(String(row.created_at));
        meta.push(backupHumanBytes(row && row.size_bytes));
        if(selected) meta.push('restore on next spawn');
        left.appendChild(S.el('div', {
          className: selected ? 'ok' : 'muted',
          style: 'margin-top:4px',
          text: meta.join(' · ')
        }));
        item.appendChild(left);

        var rowActions = S.el('div', { className: 'card__actions', style: 'justify-content:flex-end' });

        rowActions.appendChild(S.el('a', {
          className: 'btn btn--secondary',
          href: artifactUrl,
          text: 'Download'
        }));

        var btnSelect = S.el('button', {
          className: selected ? 'btn' : 'btn btn--secondary',
          text: selected ? 'Selected' : 'Use on next spawn'
        });
        btnSelect.disabled = selected;
        btnSelect.addEventListener('click', function(){
          btnSelect.disabled = true;
          backupFetchJson('/api/v2/units/' + encodePathValue(unit) + '/backups/' + encodeURIComponent(backupId) + '/select-restore', {
            method: 'POST'
          }).then(refreshList).catch(function(err){
            alert(String((err && err.message) || err || 'Select failed'));
            btnSelect.disabled = false;
          });
        });
        rowActions.appendChild(btnSelect);

        var btnDelete = S.el('button', {
          className: 'btn btn--danger',
          text: 'Delete'
        });
        btnDelete.addEventListener('click', function(){
          if(!confirm('Delete backup ' + backupId + '?')) return;
          btnDelete.disabled = true;
          backupFetchJson('/api/v2/units/' + encodePathValue(unit) + '/backups/' + encodeURIComponent(backupId), {
            method: 'DELETE'
          }).then(refreshList).catch(function(err){
            alert(String((err && err.message) || err || 'Delete failed'));
            btnDelete.disabled = false;
          });
        });
        rowActions.appendChild(btnDelete);

        item.appendChild(rowActions);
        listEl.appendChild(item);
      });
    }

    btnRefresh.addEventListener('click', function(){
      btnRefresh.disabled = true;
      refreshList().finally(function(){ btnRefresh.disabled = false; });
    });

    btnUpload.addEventListener('click', function(){ upload.click(); });
    upload.addEventListener('change', async function(){
      var file = upload.files && upload.files[0];
      if(!file) return;

      var fd = new FormData();
      fd.append('file', file);

      btnUpload.disabled = true;
      setStatus('Uploading backup…', 'muted');

      try{
        var resp = await fetch('/api/v2/units/' + encodePathValue(unit) + '/backups/upload', {
          method: 'POST',
          body: fd,
          credentials: 'same-origin'
        });
        var text = await resp.text();
        var obj = text ? JSON.parse(text) : {};
        if(!resp.ok) throw new Error(String((obj && obj.detail) || text || ('HTTP ' + resp.status)));
        setStatus('Uploaded.', 'ok');
        await refreshList();
      }catch(err){
        setStatus(String((err && err.message) || err || 'Upload failed'), 'err');
      }finally{
        upload.value = '';
        btnUpload.disabled = false;
      }
    });

    if(nodeId){
      btnCreate.addEventListener('click', async function(){
        btnCreate.disabled = true;
        setStatus('Creating backup…', 'muted');
        try{
          var j = await backupFetchJson('/api/v2/nodes/' + encodePathValue(nodeId) + '/backup', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
            body: JSON.stringify({ buckets: ['users'] })
          });
          var backup = (j && j.backup) || {};
          setStatus('Backup created.', 'ok');
          await refreshList();
          if(backup.artifact_url) backupAutoDownload(String(backup.artifact_url));
        }catch(err){
          setStatus(String((err && err.message) || err || 'Backup failed'), 'err');
        }finally{
          btnCreate.disabled = false;
        }
      });
    }

    setTimeout(function(){ refreshList().catch(function(err){ setStatus(String(err.message || err), 'err'); }); }, 0);

    wrap.appendChild(card);
    return wrap;
  }

  window.TAKS_UNIT.renderBackupsPanel = renderBackupsPanel;

  /* BACKUPS_TAB_V1_END */

})();
