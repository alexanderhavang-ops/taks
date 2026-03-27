/* global CORE */
(function(){
  window.TAKS_UNIT = window.TAKS_UNIT || {};
  const S = window.TAKS_UNIT.shared;
  const A = window.TAKS_UNIT.api;

  function renderHeaderCard(ctx){
    const c = S.card();

    const top = S.el('div', {
      style: 'display:flex;justify-content:space-between;align-items:center;margin-bottom:10px'
    });

    const leftTop = S.el('div');
    if(ctx.parent){
      leftTop.appendChild(S.el('a', {
        href: '#/units/' + encodeURIComponent(ctx.parent),
        className: 'muted',
        style: 'text-decoration:none',
        text: 'HC: ' + ctx.parent
      }));
    }else{
      leftTop.appendChild(S.el('span', { className: 'muted', text: 'HC saknas' }));
    }

    const rightTop = S.el('div',
      null,
      S.el('a', {
        href: '#/units',
        className: 'muted',
        style: 'text-decoration:none',
        text: '← Tillbaka till enheter'
      })
    );

    top.appendChild(leftTop);
    top.appendChild(rightTop);
    c.appendChild(top);

    const row = S.el('div', {
      style: 'display:flex;align-items:center;gap:24px'
    });

    const logoBox = S.el('div', {
      style: 'width:132px;min-width:132px;height:132px;border-radius:18px;border:1px solid var(--line);background:rgba(255,255,255,.02);display:flex;align-items:center;justify-content:center;padding:14px;overflow:hidden'
    });
    const logoImg = S.el('img', {
      id: 'brand_logo_img',
      alt: 'logo',
      style: 'max-width:100%;max-height:100%;object-fit:contain'
    });
    logoBox.appendChild(logoImg);
    row.appendChild(logoBox);

    const body = S.el('div', { style: 'min-width:0;flex:1 1 auto' });
    body.appendChild(S.el('div', { className: 'muted', style: 'margin-bottom:8px', text: 'Enhet' }));
    body.appendChild(S.el('div', {
      className: 'card__title',
      style: 'font-size:34px;line-height:1.1',
      text: '[' + (ctx.symbol || '') + '] ' + ctx.title
    }));

    const codeLine = S.el('div', { className: 'muted', style: 'margin-top:6px' });
    codeLine.appendChild(S.el('code', { text: ctx.unitPath }));
    body.appendChild(codeLine);

    if(ctx.slogan){
      const sloganWrap = S.el('div', { style: 'margin-top:18px' });
      sloganWrap.appendChild(S.el('span', {
        style: 'display:inline-block;padding:10px 16px;border-radius:12px;border:1px solid var(--line);background:rgba(255,255,255,.03);font-size:18px;font-weight:700;letter-spacing:.04em;text-transform:uppercase',
        text: '‘' + ctx.slogan + '’'
      }));
      body.appendChild(sloganWrap);
    }

    const details = S.el('details', { style: 'margin-top:18px' });
    details.appendChild(S.el('summary', { text: 'Redigera identitet' }));

    const grid = S.el('div', { className: 'grid grid--6', style: 'margin-top:12px' });

    const logoCol = S.el('div', { style: 'grid-column: span 2;' });
    logoCol.appendChild(S.el('button', {
      id: 'brand_logo_btn',
      className: 'btn btn--secondary',
      type: 'button',
      text: 'Byt logotyp'
    }));
    logoCol.appendChild(S.el('input', {
      id: 'brand_logo_file',
      type: 'file',
      accept: '.png,.jpg,.jpeg,.svg',
      style: 'display:none'
    }));
    logoCol.appendChild(S.el('div', {
      id: 'brand_logo_status',
      className: 'muted',
      style: 'margin-top:8px'
    }));

    const sloganCol = S.el('div', { style: 'grid-column: span 3;' });
    sloganCol.appendChild(S.el('label', { className: 'label', text: 'Slogan' }));
    sloganCol.appendChild(S.el('input', {
      id: 'brand_slogan',
      value: ctx.slogan || '',
      placeholder: 'Kort valspråk eller undertitel'
    }));

    const symbolCol = S.el('div', { style: 'grid-column: span 1;' });
    symbolCol.appendChild(S.el('label', { className: 'label', text: 'Symbol' }));
    symbolCol.appendChild(S.el('input', {
      id: 'brand_symbol',
      value: ctx.symbol || '',
      placeholder: 'II'
    }));
    symbolCol.appendChild(S.el('div', {
      id: 'brand_symbol_help',
      className: 'muted',
      style: 'margin-top:6px',
      text: S.symbolHelp(ctx.symbol || '')
    }));

    grid.appendChild(logoCol);
    grid.appendChild(sloganCol);
    grid.appendChild(symbolCol);
    details.appendChild(grid);

    const actions = S.el('div', { className: 'card__actions', style: 'margin-top:12px' });
    actions.appendChild(S.el('button', { id: 'brand_save_btn', className: 'btn', text: 'Spara' }));
    details.appendChild(actions);
    details.appendChild(S.el('div', { id: 'brand_save_status', className: 'muted', style: 'margin-top:8px' }));

    body.appendChild(details);
    row.appendChild(body);
    c.appendChild(row);

    if(ctx.logoUrl){
      logoImg.src = ctx.logoUrl;
    }else{
      A.setLogoFallback(logoImg, ctx.unitPath);
    }

    return c;
  }

  function renderNodeSummary(node){
    const wrap = S.el('div', { style: 'display:grid;gap:14px;margin-top:8px' });

    if(!node){
      wrap.appendChild(S.el('div', {
        className: 'muted',
        style: 'margin-top:14px',
        text: 'Ingen aktiv eller känd servernod kopplad till denna enhet just nu.'
      }));
      return wrap;
    }

    const aws = String(node.aws_state || '—');
    const hb = S.heartbeatState(node);
    const awsKind = aws === 'running' ? 'ok' : (aws === 'terminated' ? 'err' : 'muted');
    const hbKind = hb === 'online' ? 'ok' : (hb === 'stale' ? 'warn' : (hb === 'lost' ? 'err' : 'muted'));
    const fqdn = String(node.fqdn || '').trim();

    const row1 = S.el('div', { className: 'grid grid--6' });
    row1.appendChild(S.field('Node', S.el('div', { style: 'font-weight:700;word-break:break-all', text: node.node_id || node.fqdn || node.instance_id || '—' }), 2));
    row1.appendChild(S.field('FQDN', S.el('div', { style: 'word-break:break-all', text: fqdn || '—' }), 2));
    row1.appendChild(S.field('AWS', S.el('div', null, S.badge(aws, awsKind))));
    row1.appendChild(S.field('Heartbeat', S.el('div', null, S.badge(hb, hbKind))));
    wrap.appendChild(row1);

    const row2 = S.el('div', { className: 'grid grid--6' });
    row2.appendChild(S.field('Last seen', S.el('div', { text: S.fmtAge(node.heartbeat_age_sec) })));
    row2.appendChild(S.field('Instance', S.el('div', { style: 'word-break:break-all', text: node.instance_id || node.aws_instance_id || '—' }), 2));

    const privWrap = S.el('div', { style: 'display:flex;gap:8px;align-items:center;flex-wrap:wrap' });
    const priv = String(node.private_ip || node.aws_private_ip || '—');
    privWrap.appendChild(S.el('code', { text: priv }));
    if(priv && priv !== '—') privWrap.appendChild(S.copyBtn(priv));
    row2.appendChild(S.field('Private IP', privWrap));

    row2.appendChild(S.field('Public IP', S.el('div', null, S.el('code', { text: node.public_ip || node.aws_public_ip || '—' }))));
    wrap.appendChild(row2);

    return wrap;
  }

  function renderNodeCard(node){
    const c = S.card('TAK-servernod');

    c.appendChild(renderNodeSummary(node));

    const aws = String((node && node.aws_state) || '').trim().toLowerCase();
    const hb = String(S.heartbeatState(node) || '').trim().toLowerCase();
    const nodeId = String((node && (node.node_id || node.fqdn || node.instance_id)) || '').trim();
    const fqdn = String((node && node.fqdn) || '').trim();

    const looksRunning = !!node && (
      aws === 'running' ||
      aws === 'pending' ||
      aws === 'stopping' ||
      aws === 'shutting-down' ||
      hb === 'online' ||
      hb === 'stale'
    );

    if(fqdn){
      const linksWrap = S.el('div', { style: 'margin-top:12px' });
      linksWrap.appendChild(S.el('div', { className: 'label', text: 'Snabblänkar' }));

      const links = S.el('div', { className: 'card__actions', style: 'margin-top:8px' });
      links.appendChild(S.el('a', {
        className: 'btn',
        href: 'https://' + fqdn + '/',
        target: '_blank',
        rel: 'noopener noreferrer',
        text: 'TAKS'
      }));
      links.appendChild(S.el('a', {
        className: 'btn btn--secondary',
        href: 'https://' + fqdn + ':8446/webtak/',
        target: '_blank',
        rel: 'noopener noreferrer',
        text: 'WebTAK'
      }));
      links.appendChild(S.el('a', {
        className: 'btn btn--secondary',
        href: 'https://' + fqdn + ':8446/Marti/',
        target: '_blank',
        rel: 'noopener noreferrer',
        text: 'Marti'
      }));
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

    if(looksRunning && nodeId){
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
    const typeCol = S.el('div', { style: 'grid-column: span 2;' });
    typeCol.appendChild(S.el('label', { className: 'label', text: 'AWS size' }));
    const sel = S.el('select', { id: 'node_instance_type' });
    ['t3.small', 't3.medium', 't3.large'].forEach(function(x){
      const opt = S.el('option', { value: x, text: x });
      if(x === 't3.small') opt.selected = true;
      sel.appendChild(opt);
    });
    typeCol.appendChild(sel);
    grid.appendChild(typeCol);
    advanced.appendChild(grid);

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

  function renderFilesCard(filesResp){
    const c = S.card('Enhetsfiler');
    const subtrees = (filesResp && filesResp.subtrees) ? filesResp.subtrees : {};
    const order = ['packages', 'branding', 'users', 'plugins', 'maps', 'missions', 'misc'];

    const top = S.el('div', { className: 'grid grid--6', style: 'margin-top:10px' });
    const subtreeCol = S.el('div');
    subtreeCol.appendChild(S.el('label', { className: 'label', text: 'Subtree' }));
    const subtreeSel = S.el('select', { id: 'unit_file_subtree' });
    order.forEach(function(name){
      subtreeSel.appendChild(S.el('option', { value: name, text: subtreeLabel(name) }));
    });
    subtreeCol.appendChild(subtreeSel);

    const nameCol = S.el('div', { style: 'grid-column: span 3;' });
    nameCol.appendChild(S.el('label', { className: 'label', text: 'Målfilnamn / relativ sökväg' }));
    nameCol.appendChild(S.el('input', {
      id: 'unit_file_name',
      placeholder: 't.ex. takserver.tar.gz eller config/example.txt'
    }));

    const btnCol = S.el('div', { style: 'display:flex;align-items:flex-end;gap:8px;' });
    btnCol.appendChild(S.el('button', {
      id: 'unit_file_upload_btn',
      className: 'btn',
      text: 'Ladda upp fil'
    }));
    btnCol.appendChild(S.el('input', {
      id: 'unit_file_input',
      type: 'file',
      style: 'display:none'
    }));

    top.appendChild(subtreeCol);
    top.appendChild(nameCol);
    top.appendChild(btnCol);
    c.appendChild(top);
    c.appendChild(S.el('div', { id: 'unit_file_upload_status', className: 'muted', style: 'margin-top:8px' }));

    order.forEach(function(name){
      const arr = Array.isArray(subtrees[name]) ? subtrees[name] : [];
      const box = S.el('div', { className: 'card', style: 'margin-top:14px' });
      box.appendChild(S.el('div', { className: 'card__title', text: subtreeLabel(name) }));

      if(!arr.length){
        box.appendChild(S.el('div', { className: 'muted', text: 'Tomt.' }));
      }else{
        const list = S.el('div', { style: 'display:grid;gap:8px' });

        arr.forEach(function(item){
          const inherited = !!item.inherited;
          const row = S.el('div', {
            style: 'display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;align-items:flex-start'
          });

          const left = S.el('div', { style: 'min-width:0;flex:1 1 auto' });
          const link = S.el('a', {
            href: item.download_url || '#',
            text: item.path || '',
            style: inherited
              ? 'font-style:italic;text-decoration:none'
              : 'text-decoration:none'
          });
          if(item.download_url){
            link.setAttribute('download', '');
          }
          left.appendChild(link);

          if(inherited){
            left.appendChild(S.el('div', {
              className: 'muted',
              style: 'font-style:italic;margin-top:4px',
              text: 'ärvd från ' + String(item.source_unit || 'okänd')
            }));
          }else if(item.source_unit){
            left.appendChild(S.el('div', {
              className: 'muted',
              style: 'margin-top:4px',
              text: 'lokal för ' + String(item.source_unit)
            }));
          }

          const right = S.el('div', {
            style: 'display:flex;gap:8px;align-items:center;flex-wrap:wrap;justify-content:flex-end'
          });

          const meta = [];
          if(item.bytes != null) meta.push(String(item.bytes) + ' B');
          if(item.kind) meta.push(String(item.kind));
          right.appendChild(S.el('div', { className: 'muted', text: meta.join(' · ') }));

          if(!inherited && item.delete_url){
            right.appendChild(S.el('button', {
              className: 'btn btn--danger',
              text: 'Ta bort',
              type: 'button',
              'data-delete-url': item.delete_url,
              'data-file-path': item.path || ''
            }));
          }

          row.appendChild(left);
          row.appendChild(right);
          list.appendChild(row);
        });

        box.appendChild(list);
      }

      c.appendChild(box);
    });

    return c;
  }

  function wireBrandActions(ctx){
    const brandSymbolInp = S.byId('brand_symbol');
    const brandSymbolHelp = S.byId('brand_symbol_help');
    if(brandSymbolInp && brandSymbolHelp){
      brandSymbolInp.oninput = function(){
        brandSymbolHelp.textContent = S.symbolHelp(brandSymbolInp.value);
      };
    }

    const saveBtn = S.byId('brand_save_btn');
    if(saveBtn){
      saveBtn.onclick = async function(){
        const statusEl = S.byId('brand_save_status');
        if(statusEl){
          statusEl.textContent = 'Sparar…';
          statusEl.className = 'muted';
        }
        try{
          await A.saveBrand(
            ctx.unitPath,
            S.byId('brand_slogan') ? S.byId('brand_slogan').value : '',
            S.byId('brand_symbol') ? S.byId('brand_symbol').value : ''
          );
          if(statusEl){
            statusEl.textContent = 'Sparat.';
            statusEl.className = 'ok';
          }
        }catch(e){
          if(statusEl){
            statusEl.textContent = String(e && e.message ? e.message : e);
            statusEl.className = 'err';
          }
        }
      };
    }

    const logoBtn = S.byId('brand_logo_btn');
    const logoFile = S.byId('brand_logo_file');
    const logoStatus = S.byId('brand_logo_status');
    const logoImg = S.byId('brand_logo_img');

    if(logoBtn && logoFile){
      logoBtn.onclick = function(){ logoFile.click(); };
      logoFile.onchange = async function(){
        const f = logoFile.files && logoFile.files[0];
        if(!f) return;

        if(logoStatus){
          logoStatus.textContent = 'Laddar upp…';
          logoStatus.className = 'muted';
        }

        try{
          await A.uploadLogo(ctx.unitPath, f);
          if(logoStatus){
            logoStatus.textContent = 'Logotyp uppladdad.';
            logoStatus.className = 'ok';
          }
          if(logoImg){
            logoImg.src = '/u/' + encodeURIComponent(ctx.unitPath) + '/assets/logo.png?ts=' + Date.now();
            logoImg.style.display = '';
          }
        }catch(e){
          if(logoStatus){
            logoStatus.textContent = String(e && e.message ? e.message : e);
            logoStatus.className = 'err';
          }
        }finally{
          logoFile.value = '';
        }
      };
    }
  }

  function wireNodeActions(){
    const previewBtn = S.byId('node_preview_btn');
    const dryrunBtn = S.byId('node_dryrun_btn');
    const launchBtn = S.byId('node_launch_btn');
    const refreshBtn = S.byId('node_refresh_btn');
    const terminateBtn = S.byId('node_terminate_btn');
    const statusEl = S.byId('node_action_status');

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

    if(terminateBtn){
      terminateBtn.onclick = async function(){
        const nodeId = String(terminateBtn.getAttribute('data-node-id') || '').trim();
        if(!nodeId) return;
        if(!confirm('Terminera AWS-instans för ' + nodeId + '?')) return;

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

  function wireFileActions(unitPath){
    const fileBtn = S.byId('unit_file_upload_btn');
    const fileInp = S.byId('unit_file_input');
    const fileStatus = S.byId('unit_file_upload_status');

    if(fileBtn && fileInp){
      fileBtn.onclick = function(){ fileInp.click(); };
      fileInp.onchange = async function(){
        const f = fileInp.files && fileInp.files[0];
        const subtree = S.byId('unit_file_subtree') ? S.byId('unit_file_subtree').value : '';
        const nameInp = S.byId('unit_file_name');
        let name = nameInp ? nameInp.value.trim() : '';

        if(!f) return;

        if(!name && f.name){
          name = f.name;
          if(nameInp) nameInp.value = name;
        }

        if(!subtree || !name){
          if(fileStatus){
            fileStatus.textContent = 'Välj subtree först. Målfilnamn fylls nu automatiskt från filnamnet om det lämnas tomt.';
            fileStatus.className = 'err';
          }
          fileInp.value = '';
          return;
        }

        if(fileStatus){
          fileStatus.textContent = 'Laddar upp…';
          fileStatus.className = 'muted';
        }

        try{
          await A.uploadUnitFile(unitPath, subtree, name, f);
          if(fileStatus){
            fileStatus.textContent = 'Fil uppladdad.';
            fileStatus.className = 'ok';
          }
          render();
        }catch(e){
          if(fileStatus){
            fileStatus.textContent = String(e && e.message ? e.message : e);
            fileStatus.className = 'err';
          }
        }finally{
          fileInp.value = '';
        }
      };
    }

    document.querySelectorAll('button[data-delete-url]').forEach(function(btn){
      btn.onclick = async function(){
        const url = btn.getAttribute('data-delete-url') || '';
        const path = btn.getAttribute('data-file-path') || 'filen';
        if(!url) return;
        if(!confirm('Ta bort ' + path + '?')) return;

        if(fileStatus){
          fileStatus.textContent = 'Tar bort…';
          fileStatus.className = 'muted';
        }

        try{
          const r = await fetch(url, { method: 'DELETE', credentials: 'include' });
          if(!r.ok){
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

          if(fileStatus){
            fileStatus.textContent = 'Fil borttagen.';
            fileStatus.className = 'ok';
          }
          render();
        }catch(e){
          if(fileStatus){
            fileStatus.textContent = String(e && e.message ? e.message : e);
            fileStatus.className = 'err';
          }
        }
      };
    });
  }

  async function render(container){
    const app = container || S.byId('page') || S.byId('app');
    if(!app) return;

    const unitPath = S.getRouteUnitPath();
    if(!unitPath){
      S.clear(app);
      app.appendChild(
        S.el('section', { className: 'card' },
          S.el('div', { className: 'card__title', text: 'Enhet' }),
          S.el('div', { className: 'muted', text: 'Ingen unit_path i route.' })
        )
      );
      return;
    }

    let unit, brand, nodesResp, filesResp;
    try{
      const res = await Promise.all([
        A.loadUnitFromList(unitPath),
        A.loadBrand(unitPath),
        A.loadNodes(),
        A.loadUnitFiles(unitPath)
      ]);
      unit = res[0];
      brand = res[1];
      nodesResp = res[2];
      filesResp = res[3];
    }catch(e){
      S.clear(app);
      app.appendChild(
        S.el('section', { className: 'card' },
          S.el('div', { className: 'card__title', text: 'Enhet' }),
          S.el('div', { className: 'err', text: String(e && e.message ? e.message : e) })
        )
      );
      return;
    }

    const ctx = {
      unitPath: unitPath,
      title: unit.title || unit.unit_path || unitPath,
      parent: unit.parent_path || '',
      logoUrl: (brand && brand.logo_url) ? brand.logo_url : '',
      slogan: (brand && brand.slogan) ? brand.slogan : '',
      symbol: (brand && brand.symbol) ? brand.symbol : ''
    };

    const node = A.findNodeForUnit(nodesResp, unitPath);

    S.clear(app);
    app.appendChild(renderHeaderCard(ctx));
    app.appendChild(renderNodeCard(node));
    app.appendChild(renderFilesCard(filesResp));

    wireBrandActions(ctx);
    wireNodeActions();
    wireFileActions(unitPath);
  }

  window.TAKS_UNIT.render = render;
})();
