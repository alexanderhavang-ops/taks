/* global CORE */
(function(){
  window.TAKS_UNIT = window.TAKS_UNIT || {};
  const S = window.TAKS_UNIT.shared;
  const A = window.TAKS_UNIT.api;

  function tt(sv, en){
    return (window.CORE && window.CORE.lang === 'en') ? en : sv;
  }

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
        text: CORE.t('unit.parent', { parent: ctx.parent })
      }));
    }else{
      leftTop.appendChild(S.el('span', { className: 'muted', text: CORE.t('unit.parent.missing') }));
    }

    const rightTop = S.el('div',
      null,
      S.el('a', {
        href: '#/units',
        className: 'muted',
        style: 'text-decoration:none',
        text: CORE.t('unit.back_to_units')
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
    body.appendChild(S.el('div', { className: 'muted', style: 'margin-bottom:8px', text: CORE.t('unit.title') }));
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
    details.appendChild(S.el('summary', { text: CORE.t('unit.identity.edit') }));

    const grid = S.el('div', { className: 'grid grid--6', style: 'margin-top:12px' });

    const logoCol = S.el('div', { style: 'grid-column: span 2;' });
    logoCol.appendChild(S.el('button', {
      id: 'brand_logo_btn',
      className: 'btn btn--secondary',
      type: 'button',
      text: CORE.t('unit.logo.change')
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
    sloganCol.appendChild(S.el('label', { className: 'label', text: CORE.t('unit.slogan') }));
    sloganCol.appendChild(S.el('input', {
      id: 'brand_slogan',
      value: ctx.slogan || '',
      placeholder: 'Kort valspråk eller undertitel'
    }));

    const symbolCol = S.el('div', { style: 'grid-column: span 1;' });
    symbolCol.appendChild(S.el('label', { className: 'label', text: CORE.t('unit.symbol') }));
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
    actions.appendChild(S.el('button', { id: 'brand_save_btn', className: 'btn', text: CORE.t('common.save') }));
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

  function installStateKind(state){
    const s = String(state || '').trim().toLowerCase();
    if(s === 'succeeded') return 'ok';
    if(s === 'not_complete') return 'err';
    if(s === 'completed_with_warnings') return 'err';
    if(s === 'failed') return 'err';
    if(s === 'running' || s === 'incomplete') return 'warn';
    return 'muted';
  }

  function installStateLabel(state){
    const s = String(state || '').trim().toLowerCase();
    if(s === 'succeeded') return 'Klar';
    if(s === 'not_complete') return 'Inte klar';
    if(s === 'completed_with_warnings') return 'Inte klar';
    if(s === 'failed') return 'Fel';
    if(s === 'running') return 'Pågår';
    if(s === 'incomplete') return 'Oavslutad';
    return 'Okänd';
  }

  function installBarColor(state){
    const s = String(state || '').trim().toLowerCase();
    if(s === 'succeeded') return '#16a34a';
    if(s === 'not_complete') return '#dc2626';
    if(s === 'completed_with_warnings') return '#dc2626';
    if(s === 'failed') return '#dc2626';
    if(s === 'running' || s === 'incomplete') return '#d97706';
    return 'rgba(255,255,255,0.28)';
  }

  function installVisualState(summary){
    const state = String((summary && summary.state) || 'unknown').trim().toLowerCase();
    const total = Number((summary && summary.total_steps) || 0);
    const completed = Number((summary && summary.completed_steps) || 0);
    const failed = Number((summary && summary.failed_steps) || 0);
    const incomplete = Number((summary && summary.incomplete_steps) || 0);

    if(failed > 0) return 'failed';
    if(incomplete > 0) return 'not_complete';
    if(total > 0 && completed < total) return 'not_complete';
    return state;
  }

  function clearInstallProgressState(node, scopeEl){
    if(node && typeof node === 'object'){
      try {
        delete node.install;
      } catch (_) {
        node.install = null;
      }
    }
    const scope = scopeEl || document;
    if(scope && scope.querySelectorAll){
      scope.querySelectorAll('[data-install-progress="1"]').forEach(function(el){
        el.remove();
      });
    }
  }

  function renderInstallProgress(node){
    const install = node && node.install;
    if(!install || typeof install !== 'object') return null;

    const summary = (install.summary && typeof install.summary === 'object') ? install.summary : {};
    const steps = (Array.isArray(install.steps) ? install.steps : []).filter(function(step){
      return String((step && step.name) || '') !== 'install/main';
    });
    const events = Array.isArray(install.events) ? install.events : [];
    const state = String(summary.state || 'unknown');
    const visualState = installVisualState(summary);
    const pct = Math.max(0, Math.min(100, Number(summary.progress_pct || 0)));
    const total = Number(summary.total_steps || 0);
    const completed = Number(summary.completed_steps || 0);
    const failed = Number(summary.failed_steps || 0);
    const running = Number(summary.running_steps || 0);
    const incomplete = Number(summary.incomplete_steps || 0);

    const wrap = S.el('section', {
      'data-install-progress': '1',
      style: 'display:grid;gap:10px;margin-top:2px;padding:14px;border:1px solid rgba(255,255,255,0.08);border-radius:12px;background:rgba(255,255,255,0.02)'
    });

    const head = S.el('div', {
      style: 'display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap'
    });
    head.appendChild(S.el('div', { className: 'label', text: 'Installation' }));
    head.appendChild(S.badge(installStateLabel(visualState), installStateKind(visualState)));
    wrap.appendChild(head);

    const barOuter = S.el('div', {
      style: 'height:10px;border-radius:999px;background:rgba(255,255,255,0.10);overflow:hidden'
    });
    barOuter.appendChild(S.el('div', {
      style: 'height:100%;border-radius:999px;width:' + pct + '%;background:' + installBarColor(visualState)
    }));
    wrap.appendChild(barOuter);

    const metaBits = [];
    if(total > 0) metaBits.push(completed + '/' + total + ' steg klara');
    if(running > 0) metaBits.push(running + ' pågår');
    if(incomplete > 0) metaBits.push(incomplete + ' saknar slutstatus');
    if(failed > 0) metaBits.push(failed + ' fel');
    if(summary.last_event_ts) metaBits.push('senast ' + summary.last_event_ts);
    wrap.appendChild(S.el('div', { className: 'muted', text: metaBits.join(' • ') || 'Ingen installationsdata' }));

    if(incomplete > 0){
      wrap.appendChild(S.el('div', {
        className: 'muted',
        style: 'padding:8px 10px;border:1px solid rgba(220,38,38,0.35);border-radius:10px;background:rgba(220,38,38,0.08)',
        text: 'Installationen är inte komplett: vissa delsteg saknar avslutande status i loggen.'
      }));
    }

    if(steps.length){
      const stepsDetails = S.el('details', { style: 'margin-top:2px' });
      stepsDetails.appendChild(S.el('summary', { text: 'Installsteg' }));

      const stepsWrap = S.el('div', { style: 'display:grid;gap:8px;margin-top:10px' });
      steps.forEach(function(step){
        const row = S.el('div', {
          style: 'display:grid;grid-template-columns:minmax(0,1fr) auto auto;gap:10px;align-items:center;padding:8px 10px;border:1px solid rgba(255,255,255,0.06);border-radius:10px;background:rgba(255,255,255,0.02)'
        });
        row.appendChild(S.el('code', { style: 'word-break:break-word;white-space:normal', text: step.name || '—' }));
        row.appendChild(S.badge(installStateLabel(step.state || step.status || 'unknown'), installStateKind(step.state || step.status)));
        row.appendChild(S.el('div', { className: 'muted', text: step.last_ts || '—' }));
        stepsWrap.appendChild(row);
      });

      stepsDetails.appendChild(stepsWrap);
      wrap.appendChild(stepsDetails);
    }

    if(events.length){
      const eventsDetails = S.el('details', { style: 'margin-top:2px' });
      eventsDetails.appendChild(S.el('summary', { text: 'Installationslogg' }));

      const logBox = S.el('div', {
        style: 'margin-top:10px;max-height:260px;overflow:auto;border:1px solid rgba(255,255,255,0.06);border-radius:10px'
      });
      events.slice().reverse().forEach(function(ev){
        const row = S.el('div', {
          style: 'display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:10px;align-items:center;padding:8px 10px;border-top:1px solid rgba(255,255,255,0.06)'
        });
        row.appendChild(S.el('div', { className: 'muted', text: ev.ts || '—' }));
        row.appendChild(S.el('code', { style: 'word-break:break-word;white-space:normal', text: (ev.name || '—') + ' • ' + (ev.status || '—') }));
        row.appendChild(S.badge(installStateLabel(ev.state || 'unknown'), installStateKind(ev.state)));
        logBox.appendChild(row);
      });

      eventsDetails.appendChild(logBox);
      wrap.appendChild(eventsDetails);
    }

    return wrap;
  }

  function renderNodeSummary(node){
    const wrap = S.el('div', { style: 'display:grid;gap:14px;margin-top:8px' });

    if(!node){
      wrap.appendChild(S.el('div', {
        className: 'muted',
        style: 'margin-top:14px',
        text: CORE.t('unit.no_active_node')
      }));
      return wrap;
    }

    const aws = String(node.aws_state || '—');
    const hb = S.heartbeatState(node);
    const awsKind = aws === 'running' ? 'ok' : (aws === 'terminated' ? 'err' : 'muted');
    const hbKind = hb === 'online' ? 'ok' : (hb === 'stale' ? 'warn' : (hb === 'lost' ? 'err' : 'muted'));
    const fqdn = String(node.fqdn || '').trim();

    const row1 = S.el('div', { className: 'grid grid--6' });
    row1.appendChild(S.field(CORE.t('unit.field.node'), S.el('div', { style: 'font-weight:700;word-break:break-all', text: node.node_id || node.fqdn || node.instance_id || '—' }), 2));
    row1.appendChild(S.field('FQDN', S.el('div', { style: 'word-break:break-all', text: fqdn || '—' }), 2));
    row1.appendChild(S.field('AWS', S.el('div', null, S.badge(aws, awsKind))));
    row1.appendChild(S.field('Heartbeat', S.el('div', null, S.badge(hb, hbKind))));
    wrap.appendChild(row1);

    const row2 = S.el('div', { className: 'grid grid--6' });
    row2.appendChild(S.field(CORE.t('unit.field.last_seen'), S.el('div', { text: S.fmtAge(node.heartbeat_age_sec) })));
    row2.appendChild(S.field('Instance', S.el('div', { style: 'word-break:break-all', text: node.instance_id || node.aws_instance_id || '—' }), 2));

    const privWrap = S.el('div', { style: 'display:flex;gap:8px;align-items:center;flex-wrap:wrap' });
    const priv = String(node.private_ip || node.aws_private_ip || '—');
    privWrap.appendChild(S.el('code', { text: priv }));
    if(priv && priv !== '—') privWrap.appendChild(S.copyBtn(priv));
    row2.appendChild(S.field(CORE.t('unit.field.private_ip'), privWrap));

    const pubWrap = S.el('div', { style: 'display:flex;gap:8px;align-items:center;flex-wrap:wrap' });
    const pub = String(node.public_ip || node.aws_public_ip || '—');
    pubWrap.appendChild(S.el('code', { text: pub }));
    if(pub && pub !== '—') pubWrap.appendChild(S.copyBtn(pub));
    row2.appendChild(S.field(CORE.t('unit.field.public_ip'), pubWrap));
    wrap.appendChild(row2);

    const installBlock = renderInstallProgress(node);
    if(installBlock) wrap.appendChild(installBlock);

    const details = S.el('details', { style: 'margin-top:4px' });
    details.appendChild(S.el('summary', { text: CORE.t('unit.advanced_node_details') }));

    const grid = S.el('div', { className: 'grid grid--6', style: 'margin-top:12px' });
    grid.appendChild(S.field('FQDN', S.el('div', { style: 'word-break:break-all', text: node.fqdn || '—' }), 3));
    grid.appendChild(S.field(CORE.t('unit.field.display_name'), S.el('div', { text: node.display_name || ((node.meta || {}).name) || node.fqdn || '—' }), 2));
    grid.appendChild(S.field(CORE.t('unit.field.region'), S.el('div', { text: node.region || '—' })));
    grid.appendChild(S.field('AZ', S.el('div', { text: node.availability_zone || '—' })));

    grid.appendChild(S.field(CORE.t('unit.field.instance_type'), S.el('div', { text: node.instance_type || ((node.meta || {}).instance_type) || '—' }), 2));
    grid.appendChild(S.field('AMI', S.el('div', { style: 'word-break:break-all', text: node.image_id || '—' }), 2));
    grid.appendChild(S.field('Subnet', S.el('div', { text: node.subnet_id || ((node.meta || {}).subnet_id) || '—' })));
    grid.appendChild(S.field('VPC', S.el('div', { text: node.vpc_id || '—' })));

    grid.appendChild(S.field(CORE.t('unit.field.iam_profile'), S.el('div', { style: 'word-break:break-all', text: node.iam_instance_profile_arn || CORE.t('unit.field.no_iam_profile') }), 3));
    grid.appendChild(S.field(CORE.t('unit.field.launch_source'), S.el('div', { text: ((node.meta || {}).launch_source) || '—' })));
    grid.appendChild(S.field(CORE.t('unit.field.launch_time'), S.el('div', { text: node.launch_time || '—' }), 2));

    const sgs = Array.isArray(node.security_groups) ? node.security_groups : [];
    const sgText = sgs.length ? sgs.map(function(g){
      return (g.group_name || 'sg') + ' (' + (g.group_id || '—') + ')';
    }).join(', ') : '—';
    grid.appendChild(S.field(CORE.t('unit.field.security_groups'), S.el('div', { style: 'word-break:break-word', text: sgText }), 3));

    const tags = node.aws_tags || {};
    const tagText = Object.keys(tags).sort().map(function(k){ return k + '=' + tags[k]; }).join(', ') || '—';
    grid.appendChild(S.field(CORE.t('unit.field.tags'), S.el('div', { style: 'word-break:break-word', text: tagText }), 6));

    details.appendChild(grid);
    wrap.appendChild(details);

    return wrap;
  }

  function renderNodeCard(node){
    const c = S.card(CORE.t('unit.server_node'));

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
      linksWrap.appendChild(S.el('div', { className: 'label', text: CORE.t('unit.quick_links') }));

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

    const awsState = String((node && node.aws_state) || '').trim().toLowerCase();
    const derivedStatus = String((node && node.derived_status) || '').trim().toLowerCase();
    const isStopped = !!nodeId && (awsState === 'stopped' || derivedStatus === 'stopped');
    const isLiveish = !!nodeId && (
      awsState === 'running' ||
      awsState === 'pending' ||
      derivedStatus === 'running' ||
      derivedStatus === 'stale' ||
      derivedStatus === 'booting'
    );

    if(isStopped){
      actions.appendChild(S.el('button', {
        id: 'node_wake_btn',
        className: 'btn btn--secondary',
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
    nameCol.appendChild(S.el('input', {
      id: 'node_display_name',
      value: String((node && (((node.meta || {}).name) || node.display_name || node.fqdn)) || ('tak-' + String((node && node.unit_path) || S.getRouteUnitPath() || 'node')))
    }));
    grid.appendChild(nameCol);

    const typeCol = S.el('div', { style: 'grid-column: span 2;' });
    typeCol.appendChild(S.el('label', { className: 'label', text: 'AWS size' }));
    const sel = S.el('select', { id: 'node_instance_type' });
    ['t3.small', 't3.medium', 't3.large'].forEach(function(x){
      const opt = S.el('option', { value: x, text: x });
      const cur = String((node && (node.instance_type || ((node.meta || {}).instance_type))) || 't3.small');
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


  function bootstrapKindLabel(kind){
    return kind === 'secrets_d' ? 'secrets.d' : 'conf.d';
  }

  function bootstrapNames(payload, kind){
    const local = (((payload || {}).local || {})[kind]) || {};
    const effective = (((payload || {}).effective || {})[kind]) || {};
    return Array.from(new Set(Object.keys(local).concat(Object.keys(effective)))).sort();
  }

  function bootstrapEditorBoxStyle(readonly){
    return [
      'width:100%',
      'min-height:260px',
      'box-sizing:border-box',
      'resize:vertical',
      'padding:12px 14px',
      'border-radius:12px',
      'border:1px solid rgba(255,255,255,.10)',
      'background:' + (readonly ? 'rgba(255,255,255,.04)' : '#081225'),
      'color:#dbe7ff',
      'font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace',
      'font-size:12px',
      'line-height:1.45',
      'outline:none'
    ].join(';');
  }

  function renderBootstrapKindEditor(payload, kind){
    const local = (((payload || {}).local || {})[kind]) || {};
    const effective = (((payload || {}).effective || {})[kind]) || {};
    const names = Array.from(new Set(Object.keys(local).concat(Object.keys(effective)))).sort();
    const firstName = names.length ? names[0] : '';
    const title = bootstrapKindLabel(kind);
    const sourceNames = Object.keys((((payload || {}).effective_sources || {})[kind]) || {});
    const totalNames = Array.from(new Set(names.concat(sourceNames))).length;

    return S.el('section', {
        className: 'card',
        style: 'margin-top:14px; padding:16px 16px 14px 16px; border-radius:16px; border:1px solid rgba(255,255,255,.06); background:rgba(255,255,255,.02);'
      },
      S.el('div', {
        style: 'display:flex; align-items:flex-start; justify-content:space-between; gap:12px; flex-wrap:wrap; margin-bottom:8px;'
      },
        S.el('div', null,
          S.el('div', { className: 'card__title', style: 'margin:0 0 4px 0; font-size:18px;', text: title }),
          S.el('div', { className: 'muted', text: tt('Lokala overlays för den här enheten. Effektiv config byggs upp från rot till leaf där barnet vinner.', 'Local overlays for this unit. Effective config is built root-to-leaf and the child wins.') })
        ),
        S.el('div', { className: 'muted', style: 'white-space:nowrap; padding-top:4px;', text: String(totalNames) + ' ' + tt('filer', 'files') })
      ),

      S.el('div', {
        className: 'grid grid--6',
        style: 'margin-top:12px; align-items:end;'
      },
        S.el('div', { style: 'grid-column: span 2;' },
          S.el('label', { className: 'label', text: tt('Fil', 'File') }),
          (function(){
            const sel = S.el('select', { id: 'bootstrap_' + kind + '_name' });
            sel.appendChild(S.el('option', { value: '', text: tt('Välj fil…', 'Select file…') }));
            names.forEach(function(name){
              sel.appendChild(S.el('option', { value: name, text: name }));
            });
            if(firstName) sel.value = firstName;
            return sel;
          })()
        ),
        S.el('div', { style: 'grid-column: span 2;' },
          S.el('label', { className: 'label', text: tt('Ny fil', 'New file') }),
          S.el('input', {
            id: 'bootstrap_' + kind + '_new_name',
            placeholder: 'example.conf'
          })
        ),
        S.el('div', {
          style: 'grid-column: span 2; display:flex; align-items:flex-end; gap:8px; flex-wrap:wrap; justify-content:flex-end;'
        },
          S.el('button', {
            id: 'bootstrap_' + kind + '_use_new',
            className: 'btn btn--secondary',
            type: 'button',
            text: tt('Använd ny fil', 'Use new file')
          }),
          S.el('button', {
            id: 'bootstrap_' + kind + '_delete',
            className: 'btn btn--danger',
            type: 'button',
            text: tt('Ta bort lokal fil', 'Delete local file')
          })
        )
      ),

      S.el('div', {
        className: 'grid grid--6',
        style: 'margin-top:14px; align-items:start;'
      },
        S.el('div', { style: 'grid-column: span 3;' },
          S.el('div', {
            style: 'display:flex; align-items:center; justify-content:space-between; gap:10px; margin-bottom:6px;'
          },
            S.el('label', { className: 'label', text: tt('Lokal overlay', 'Local overlay') }),
            S.el('div', { className: 'muted', text: tt('Detta sparas på denna enhet', 'Stored on this unit') })
          ),
          S.el('textarea', {
            id: 'bootstrap_' + kind + '_local',
            style: bootstrapEditorBoxStyle(false)
          })
        ),
        S.el('div', { style: 'grid-column: span 3;' },
          S.el('div', {
            style: 'display:flex; align-items:center; justify-content:space-between; gap:10px; margin-bottom:6px;'
          },
            S.el('label', { className: 'label', text: tt('Effektiv config till bundle', 'Effective config for bundle') }),
            S.el('div', { className: 'muted', text: tt('Förhandsvisning efter arv', 'Preview after inheritance') })
          ),
          S.el('textarea', {
            id: 'bootstrap_' + kind + '_effective',
            readonly: 'readonly',
            style: bootstrapEditorBoxStyle(true)
          })
        )
      ),

      S.el('div', {
        style: 'display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; margin-top:10px;'
      },
        S.el('div', { id: 'bootstrap_' + kind + '_sources', className: 'muted', style: 'min-width:0; flex:1 1 auto;' }),
        S.el('div', { className: 'card__actions', style: 'margin-top:0;' },
          S.el('button', {
            id: 'bootstrap_' + kind + '_save',
            className: 'btn',
            type: 'button',
            text: tt('Spara overlay', 'Save overlay')
          })
        )
      ),

      S.el('div', { id: 'bootstrap_' + kind + '_status', className: 'muted', style: 'margin-top:8px' })
    );
  }

  function renderBootstrapCard(bootstrapResp){
    const c = S.card(tt('Nod-bootstrap', 'Node bootstrap'));
    c.style.padding = '18px';
    c.style.borderRadius = '18px';

    c.appendChild(S.el('div', {
      className: 'muted',
      style: 'line-height:1.5; margin-bottom:8px;',
      text: tt(
        'Dessa filer packas in i bundle:n som /etc/taks-bootstrap.d/{config.d,secrets.d} och seedar nodens runtime-config första gången. Om runtime-fil redan finns lämnas den i fred.',
        'These files are packed into the bundle as /etc/taks-bootstrap.d/{config.d,secrets.d} and seed the node runtime config the first time. If a runtime file already exists it is left untouched.'
      )
    }));

    c.appendChild(renderBootstrapKindEditor(bootstrapResp, 'conf_d'));
    c.appendChild(renderBootstrapKindEditor(bootstrapResp, 'secrets_d'));
    return c;
  }


  function refreshBootstrapEditor(payload, kind){
    const local = (((payload || {}).local || {})[kind]) || {};
    const effective = (((payload || {}).effective || {})[kind]) || {};
    const sources = (((payload || {}).effective_sources || {})[kind]) || {};
    const sel = S.byId('bootstrap_' + kind + '_name');
    const localTa = S.byId('bootstrap_' + kind + '_local');
    const effTa = S.byId('bootstrap_' + kind + '_effective');
    const srcEl = S.byId('bootstrap_' + kind + '_sources');
    if(!sel || !localTa || !effTa || !srcEl) return;
    const name = String(sel.value || '').trim();
    localTa.value = name ? String(local[name] || '') : '';
    effTa.value = name ? String(effective[name] || '') : '';
    const chain = name ? (sources[name] || []) : [];
    srcEl.textContent = name ? (tt('Källor i arvskedjan: ', 'Sources in inheritance chain: ') + (chain.length ? chain.join(' → ') : tt('inga', 'none'))) : '';
  }

  function wireBootstrapActions(unitPath, bootstrapResp){
    ['conf_d', 'secrets_d'].forEach(function(kind){
      const sel = S.byId('bootstrap_' + kind + '_name');
      const newName = S.byId('bootstrap_' + kind + '_new_name');
      const saveBtn = S.byId('bootstrap_' + kind + '_save');
      const delBtn = S.byId('bootstrap_' + kind + '_delete');
      const useNewBtn = S.byId('bootstrap_' + kind + '_use_new');
      const statusEl = S.byId('bootstrap_' + kind + '_status');
      const localTa = S.byId('bootstrap_' + kind + '_local');
      if(sel) sel.onchange = function(){ refreshBootstrapEditor(bootstrapResp, kind); };
      refreshBootstrapEditor(bootstrapResp, kind);

      if(useNewBtn && newName && sel){
        useNewBtn.onclick = function(){
          const name = String(newName.value || '').trim();
          if(!name) return;
          let found = false;
          Array.from(sel.options).forEach(function(opt){ if(opt.value === name) found = true; });
          if(!found){ sel.appendChild(S.el('option', { value: name, text: name })); }
          sel.value = name;
          refreshBootstrapEditor(bootstrapResp, kind);
        };
      }

      if(saveBtn && sel && localTa){
        saveBtn.onclick = async function(){
          const name = String(sel.value || '').trim() || String((newName && newName.value) || '').trim();
          if(!name){
            if(statusEl){ statusEl.textContent = tt('Välj eller ange filnamn först.', 'Select or enter a file name first.'); statusEl.className = 'err'; }
            return;
          }
          if(statusEl){ statusEl.textContent = CORE.t('common.saving'); statusEl.className = 'muted'; }
          try{
            await A.saveUnitBootstrapFile(unitPath, kind === 'secrets_d' ? 'secret' : 'config', name, localTa.value);
            if(statusEl){ statusEl.textContent = CORE.t('common.saved'); statusEl.className = 'ok'; }
            render();
          }catch(e){
            if(statusEl){ statusEl.textContent = String(e && e.message ? e.message : e); statusEl.className = 'err'; }
          }
        };
      }

      if(delBtn && sel){
        delBtn.onclick = async function(){
          const name = String(sel.value || '').trim();
          if(!name) return;
          if(!confirm(tt('Ta bort lokal overlay ' + name + '?', 'Delete local overlay ' + name + '?'))) return;
          if(statusEl){ statusEl.textContent = tt('Tar bort…', 'Deleting…'); statusEl.className = 'muted'; }
          try{
            await A.deleteUnitBootstrapFile(unitPath, kind === 'secrets_d' ? 'secret' : 'config', name);
            if(statusEl){ statusEl.textContent = tt('Borttagen.', 'Deleted.'); statusEl.className = 'ok'; }
            render();
          }catch(e){
            if(statusEl){ statusEl.textContent = String(e && e.message ? e.message : e); statusEl.className = 'err'; }
          }
        };
      }
    });
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
          statusEl.textContent = CORE.t('common.saving');
          statusEl.className = 'muted';
        }
        try{
          await A.saveBrand(
            ctx.unitPath,
            S.byId('brand_slogan') ? S.byId('brand_slogan').value : '',
            S.byId('brand_symbol') ? S.byId('brand_symbol').value : ''
          );
          if(statusEl){
            statusEl.textContent = CORE.t('common.saved');
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
            clearInstallProgressState(node, c);
            clearInstallProgressState(node, c);
            setNodeActionStatus('Start begärd. Väntar på bundle-hämtning och första heartbeat…', 'ok');
          }else{
            clearInstallProgressState(node, c);
            clearInstallProgressState(node, c);
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
          clearInstallProgressState(node, c);
          clearInstallProgressState(node, c);
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
          clearInstallProgressState(node, c);
          clearInstallProgressState(node, c);
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
          clearInstallProgressState(node, c);
          clearInstallProgressState(node, c);
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

    let unit, brand, nodesResp, filesResp, bootstrapResp, statusResp;
    try{
      const res = await Promise.all([
        A.loadUnitFromList(unitPath),
        A.loadBrand(unitPath),
        A.loadNodes(),
        A.loadUnitFiles(unitPath),
        A.loadUnitBootstrap(unitPath),
        A.loadStatus()
      ]);
      unit = res[0];
      brand = res[1];
      nodesResp = res[2];
      filesResp = res[3];
      bootstrapResp = res[4];
      statusResp = res[5];
      window.TAKS_UNIT.launchDefaults = ((statusResp || {}).launch_defaults) || {};
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
    app.appendChild(renderBootstrapCard(bootstrapResp));

    const defaults = (window.TAKS_UNIT && window.TAKS_UNIT.launchDefaults) || {};
    const setText = function(id, value){
      const x = S.byId(id);
      if(x) x.textContent = String(value || '—');
    };
    setText('node_default_region', defaults.region);
    setText('node_default_ami', defaults.ami);
    setText('node_default_subnet', defaults.subnet_id);
    setText('node_default_sg', defaults.security_group_id);
    setText('node_default_profile', defaults.instance_profile);
    setText('node_default_key', defaults.ssh_key_name);

    wireBrandActions(ctx);
    wireNodeActions();
    wireFileActions(unitPath);
    wireBootstrapActions(unitPath, bootstrapResp);
  }

  window.TAKS_UNIT.render = render;
})();
