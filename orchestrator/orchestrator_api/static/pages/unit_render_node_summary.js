/* global CORE */

(function(){

  window.TAKS_UNIT = window.TAKS_UNIT || {};

  const S = window.TAKS_UNIT.shared;

  const A = window.TAKS_UNIT.api;


  function renderInstallProgress(){
    return (window.TAKS_UNIT && typeof window.TAKS_UNIT.renderInstallProgress === 'function')
      ? window.TAKS_UNIT.renderInstallProgress.apply(null, arguments)
      : null;
  }

  function renderNodeHealth(){
    return (window.TAKS_UNIT && typeof window.TAKS_UNIT.renderNodeHealth === 'function')
      ? window.TAKS_UNIT.renderNodeHealth.apply(null, arguments)
      : null;
  }

  function nodeStatusSnapshot(){
    return (window.TAKS_UNIT && typeof window.TAKS_UNIT.nodeStatusSnapshot === 'function')
      ? window.TAKS_UNIT.nodeStatusSnapshot.apply(null, arguments)
      : { tone: 'muted', text: '◌ Unknown', detail: '', stale: true };
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

    const snap = nodeStatusSnapshot(node);

    const statusWrap = S.el('div', { style: 'margin-top:12px;margin-bottom:12px' });
    statusWrap.appendChild(S.badge(snap.text, snap.tone));
    if(snap.detail){
      const boxBorder = snap.tone === 'err' ? 'rgba(239,68,68,.25)' : 'rgba(245,158,11,.25)';
      const boxBg = snap.tone === 'err' ? 'rgba(239,68,68,.08)' : 'rgba(245,158,11,.08)';
      const boxFg = snap.tone === 'err' ? '#fecaca' : '#f6d28b';
      statusWrap.appendChild(S.el('div', {
        style: 'margin-top:8px;padding:10px 12px;border-radius:10px;border:1px solid ' + boxBorder + ';background:' + boxBg + ';color:' + boxFg + ';font-size:12px;line-height:1.45',
        text: snap.detail
      }));
    }
    wrap.appendChild(statusWrap);

    const installBlock = renderInstallProgress(node);
    if(installBlock) wrap.appendChild(installBlock);

    const healthBlock = renderNodeHealth(node);
    if(healthBlock) wrap.appendChild(healthBlock);

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

  window.TAKS_UNIT.renderNodeSummary = renderNodeSummary;

})();
