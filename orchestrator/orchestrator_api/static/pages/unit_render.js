/* global CORE */
(function(){
  window.TAKS_UNIT = window.TAKS_UNIT || {};
  const S = window.TAKS_UNIT.shared;
  const A = window.TAKS_UNIT.api;

  function renderHeaderCard(){
    return window.TAKS_UNIT.renderHeaderCard.apply(null, arguments);
  }

  function renderNodeSummary(){
    return window.TAKS_UNIT.renderNodeSummary.apply(null, arguments);
  }

  function renderNodeCard(){
    return window.TAKS_UNIT.renderNodeCard.apply(null, arguments);
  }

  function renderBackupsPanel(){
    return window.TAKS_UNIT.renderBackupsPanel.apply(null, arguments);
  }

  function renderFilesCard(){
    return window.TAKS_UNIT.renderFilesCard.apply(null, arguments);
  }

  function renderPolicyCard(){
    return window.TAKS_UNIT.renderPolicyCard.apply(null, arguments);
  }

  function renderBootstrapCard(){
    return window.TAKS_UNIT.renderBootstrapCard.apply(null, arguments);
  }

  function wireBrandActions(){
    return window.TAKS_UNIT.wireBrandActions.apply(null, arguments);
  }

  function wireNodeActions(){
    return window.TAKS_UNIT.wireNodeActions.apply(null, arguments);
  }

  function wireFileActions(){
    return window.TAKS_UNIT.wireFileActions.apply(null, arguments);
  }

  function wirePolicyActions(){
    return window.TAKS_UNIT.wirePolicyActions.apply(null, arguments);
  }

  function wireBootstrapActions(){
    return window.TAKS_UNIT.wireBootstrapActions.apply(null, arguments);
  }

  function unitTabsApi(){
    return (window.TAKS_UNIT && window.TAKS_UNIT.tabs) || null;
  }

  function findCardByTitle(root, title){
    const want = String(title || '').trim().toLowerCase();
    if(!root || !root.querySelectorAll) return null;

    const titles = root.querySelectorAll('.card__title');
    for(let i = 0; i < titles.length; i++){
      const t = titles[i];
      if(String(t.textContent || '').trim().toLowerCase() !== want) continue;
      let p = t;
      while(p && p.tagName && String(p.tagName).toLowerCase() !== 'section'){
        p = p.parentElement;
      }
      return p || t.parentElement || null;
    }
    return null;
  }

  function markValidationTarget(el, message){
    if(!el) return;
    el.setAttribute('data-validation-target', '1');
    el.style.border = '1px solid rgba(220,38,38,0.65)';
    if(!el.style.borderRadius) el.style.borderRadius = '12px';
    el.style.boxShadow = '0 0 0 1px rgba(220,38,38,0.14) inset';

    if(message){
      el.appendChild(S.el('div', {
        className: 'err',
        style: 'margin-top:10px;white-space:normal',
        text: message
      }));
    }
  }

  function annotateFilesValidation(card, validation){
    const issues = (((validation || {}).tabs || {}).files || {}).issues || [];
    if(!issues.length || !card) return;
    const target = findCardByTitle(card, 'Packages') || card;
    markValidationTarget(target, issues[0].message);
  }

  function annotateConfigValidation(root, validation){
    const issues = (((validation || {}).tabs || {}).config || {}).issues || [];
    if(!issues.length || !root) return;
    const target = findCardByTitle(root, 'secrets.d') || root;
    markValidationTarget(target, issues[0].message + ' Fix this in secrets.d before boot.');
  }

  function annotateNodeValidation(card, validation){
    const issues = (((validation || {}).tabs || {}).node || {}).issues || [];
    if(!issues.length || !card) return;

    const inp = card.querySelector('#node_fqdn');
    if(inp){
      inp.style.border = '1px solid rgba(220,38,38,0.65)';
      markValidationTarget(inp.parentElement || inp, issues[0].message);
      return;
    }

    markValidationTarget(card, issues[0].message);
  }

  function flashFirstValidationTarget(root){
    if(!root || !root.querySelector) return;
    const el = root.querySelector('[data-validation-target="1"]');
    if(!el) return;

    try{
      el.scrollIntoView({ block: 'nearest' });
    }catch(_e){}

    const prev = el.style.boxShadow || '';
    el.style.boxShadow = '0 0 0 3px rgba(220,38,38,0.24)';
    setTimeout(function(){
      el.style.boxShadow = prev || '0 0 0 1px rgba(220,38,38,0.14) inset';
    }, 1200);
  }

  function populateLaunchDefaults(){
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
  }


  function renderOverviewPanel(node, validation){
    const wrap = S.el('div', { style: 'display:grid;gap:14px' });

    if(!node){
      const empty = S.card('Overview');
      empty.appendChild(S.el('div', {
        className: 'muted',
        text: 'No active or known server node is currently associated with this unit.'
      }));
      wrap.appendChild(empty);
      return wrap;
    }

    const overview = S.card('Overview');

    function quickLink(text, href){
      return S.el('a', {
        className: 'btn',
        href: href,
        target: '_blank',
        rel: 'noopener noreferrer',
        text: text
      });
    }

    function installSummaryFromNode(node){
    const install = (node && node.install && typeof node.install === 'object') ? node.install : null;
    const steps = Array.isArray(install && install.steps) ? install.steps : [];
    if(!steps.length){
      return { text: '—', tone: 'muted' };
    }

    function norm(v){
      return String(v || '').trim().toLowerCase();
    }

    const states = steps.map(function(x){
      return norm((x && (x.state || x.status)) || '');
    });

    if(states.some(function(x){ return x === 'running' || x === 'started' || x === 'pending'; })){
      return { text: 'Pågår', tone: 'warn' };
    }

    if(states.some(function(x){ return x === 'failed' || x === 'error'; })){
      return { text: 'Fel', tone: 'err' };
    }

    const mains = steps.filter(function(x){
      return String((x && x.name) || '').trim() === 'install/main';
    });

    const main = mains.length ? mains[mains.length - 1] : null;
    if(main){
      const st = norm(main.state || main.status);
      if(st === 'succeeded' || st === 'success' || st === 'ok' || st === 'completed'){
        return { text: 'Klar', tone: 'ok' };
      }
      if(st === 'running' || st === 'started' || st === 'pending'){
        return { text: 'Pågår', tone: 'warn' };
      }
      if(st === 'failed' || st === 'error'){
        return { text: 'Fel', tone: 'err' };
      }
    }

    if(states.some(function(x){ return x === 'succeeded' || x === 'success' || x === 'ok' || x === 'completed'; })){
      return { text: 'Klar', tone: 'ok' };
    }

    return { text: '—', tone: 'muted' };
    }

    function serviceSummaryFromNode(node){
      const svc = (node && node.services && typeof node.services === 'object') ? node.services : null;
      if(!svc){
        return { text: '—', tone: 'muted' };
      }

      const overall = String(svc.overall || '').trim().toLowerCase();
      if(overall === 'ok'){
        return { text: 'OK', tone: 'ok' };
      }
      if(overall === 'warn' || overall === 'warning' || overall === 'stale'){
        return { text: 'Varning', tone: 'warn' };
      }
      if(overall === 'fail' || overall === 'error' || overall === 'red'){
        return { text: 'Fel', tone: 'err' };
      }

      const crit = Number(svc.critical_failed || 0);
      const fail = Number(svc.fail || 0);
      const warn = Number(svc.warn || 0);
      const ok = Number(svc.ok || 0);

      if(crit > 0 || fail > 0){
        return { text: 'Fel', tone: 'err' };
      }
      if(warn > 0){
        return { text: 'Varning', tone: 'warn' };
      }
      if(ok > 0){
        return { text: 'OK', tone: 'ok' };
      }

      return { text: '—', tone: 'muted' };
    }

    function summaryBox(title, state, targetTab){
      const tone = String((state && state.tone) || 'muted');
      const text = String((state && state.text) || '—');

      let border = 'rgba(255,255,255,0.08)';
      let bg = 'rgba(255,255,255,0.02)';

      if(tone === 'ok'){
        border = 'rgba(34,197,94,.18)';
        bg = 'rgba(34,197,94,.04)';
      }else if(tone === 'warn'){
        border = 'rgba(245,158,11,.24)';
        bg = 'rgba(245,158,11,.06)';
      }else if(tone === 'err'){
        border = 'rgba(239,68,68,.24)';
        bg = 'rgba(239,68,68,.06)';
      }

      const box = S.el('div', {
        style: 'padding:12px;border:1px solid ' + border + ';border-radius:12px;background:' + bg
      });

      const head = S.el('div', {
        style: 'display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap'
      });
      head.appendChild(S.el('div', { className: 'label', text: title }));

      if(window.TAKS_UNIT && typeof window.TAKS_UNIT.lightPill === 'function'){
        head.appendChild(window.TAKS_UNIT.lightPill(
          tone === 'ok' ? 'ok' : (tone === 'warn' ? 'warn' : (tone === 'err' ? 'err' : 'muted')),
          text
        ));
      }else{
        head.appendChild(S.el('div', { style: 'font-weight:700', text: text }));
      }

      box.appendChild(head);
      if(targetTab){
        box.style.cursor = 'pointer';
        box.title = 'Open ' + String(targetTab);
        box.addEventListener('click', function(ev){
          ev.preventDefault();
          ev.stopPropagation();
          window.TAKS_UNIT = window.TAKS_UNIT || {};

          var target = String(targetTab || '').trim();
          if(target.indexOf('node:') === 0){
            window.TAKS_UNIT.activeTab = 'node';
            window.TAKS_UNIT.nodeAutoOpen = target.split(':', 2)[1] || '';
          }else{
            window.TAKS_UNIT.activeTab = target;
            window.TAKS_UNIT.nodeAutoOpen = '';
          }

          const host =
            document.getElementById('page') ||
            document.getElementById('app') ||
            document.querySelector('main') ||
            document.body;
          if(window.TAKS_UNIT && typeof window.TAKS_UNIT.render === 'function' && host){
            window.TAKS_UNIT.render(host);
          }
        });
      }
      return box;
    }

    const fqdn = String((node && node.fqdn) || '').trim();
    const aws = String((node && node.aws_state) || '').trim().toLowerCase();
    const pub = String((node && (node.public_ip || node.aws_public_ip)) || '—').trim();

    const links = S.el('div', { className: 'card__actions', style: 'margin-top:8px' });
    if(fqdn){
      links.appendChild(quickLink('TAKS', 'https://' + fqdn + '/'));
      links.appendChild(quickLink('Marti', 'https://' + fqdn + ':8446/Marti/'));
      links.appendChild(quickLink('WebTAK', 'https://' + fqdn + ':8446/webtak/'));
    }
    overview.appendChild(links);

    const top = S.el('div', { className: 'grid grid--6', style: 'margin-top:12px' });
    top.appendChild(S.field('FQDN', S.el('div', { style: 'font-weight:700;word-break:break-all', text: fqdn || '—' }), 3));

    const awsKind =
      aws === 'running' ? 'ok' :
      (aws === 'pending' || aws === 'stopped' || aws === 'stopping' ? 'warn' : 'muted');
    top.appendChild(S.field('AWS', S.el('div', null, S.badge(aws || 'unknown', awsKind))));

    const pubWrap = S.el('div', { style: 'display:flex;gap:8px;align-items:center;flex-wrap:wrap' });
    pubWrap.appendChild(S.el('code', { text: pub }));
    if(pub && pub !== '—') pubWrap.appendChild(S.copyBtn(pub));
    top.appendChild(S.field('Public IP', pubWrap, 2));
    overview.appendChild(top);

    const bottom = S.el('div', { className: 'grid grid--6', style: 'margin-top:14px' });
    bottom.appendChild(S.el('div', { style: 'grid-column: span 3;' },
      summaryBox('Installation', installSummaryFromNode(node), 'node:install')
    ));
    bottom.appendChild(S.el('div', { style: 'grid-column: span 3;' },
      summaryBox('Service health', serviceSummaryFromNode(node), 'node:health')
    ));
    overview.appendChild(bottom);

    wrap.appendChild(overview);
    return wrap;
  }

  function renderNodePanel(node, validation, tabs){
    const wrap = S.el('div', { style: 'display:grid;gap:14px' });

    const aws = String((node && node.aws_state) || '').trim().toLowerCase();
    const derived = String((node && node.derived_status) || '').trim().toLowerCase();
    const hb = String(S.heartbeatState(node) || 'never').trim().toLowerCase();
    const hasNode = !!String((node && (node.node_id || node.fqdn || node.instance_id)) || '').trim();

    const isLive =
      hasNode && (
        hb === 'online' ||
        aws === 'running' ||
        aws === 'pending' ||
        derived === 'running' ||
        derived === 'stale' ||
        derived === 'booting'
      );

    if(!isLive){
      wrap.appendChild(tabs.renderReadinessCard(validation));
    }

    if(validation.tabs.node.blockers || validation.tabs.node.warnings){
      wrap.appendChild(tabs.renderIssueSummary('Node validation', validation.tabs.node));
    }

    const card = renderNodeCard(node);
    annotateNodeValidation(card, validation);
    wrap.appendChild(card);
    return wrap;
  }

  function renderFilesPanel(filesResp, validation, tabs){
    const wrap = S.el('div', { style: 'display:grid;gap:14px' });

    if(validation.tabs.files.blockers || validation.tabs.files.warnings){
      wrap.appendChild(tabs.renderIssueSummary('Files validation', validation.tabs.files));
    }

    const card = renderFilesCard(filesResp);
    annotateFilesValidation(card, validation);
    wrap.appendChild(card);
    return wrap;
  }


  function renderConfigPanel(bootstrapResp, validation, tabs){
    const wrap = S.el('div', { style: 'display:grid;gap:14px' });

    if(validation.tabs.config.blockers || validation.tabs.config.warnings){
      wrap.appendChild(tabs.renderIssueSummary('Config validation', validation.tabs.config));
    }

    const policyCard = renderPolicyCard(bootstrapResp, { showSeedActions: false });
    const bootstrapCard = renderBootstrapCard(bootstrapResp);

    const holder = S.el('div', { style: 'display:grid;gap:14px' });
    holder.appendChild(policyCard);
    holder.appendChild(bootstrapCard);
    annotateConfigValidation(holder, validation);

    wrap.appendChild(holder);
    return wrap;
  }


  function renderAdvancedPanel(bootstrapResp){
    const wrap = S.el('div', { style: 'display:grid;gap:14px' });

    const intro = S.card('Advanced');
    intro.appendChild(S.el('div', {
      className: 'muted',
      text: 'Low-frequency maintenance actions live here.'
    }));
    wrap.appendChild(intro);

    wrap.appendChild(renderPolicyCard(bootstrapResp, { showSeedActions: true }));
    return wrap;
  }

  function renderTabShell(activeTab, validation, onSelect){
    const shell = S.card();
    shell.style.padding = '0 18px 18px 18px';
    shell.appendChild(unitTabsApi().renderTabBar(activeTab, validation, onSelect));
    return shell;
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


    function unitFaviconInitials(ctx){
      const title = String((ctx && (ctx.title || ctx.unitPath)) || '').trim();
      const lower = title.toLowerCase();

      if(lower.indexOf('tak') >= 0 && lower.indexOf('lab') >= 0){
        return 'TL';
      }

      const words = title
        .replace(/[^A-Za-z0-9ÅÄÖåäö]+/g, ' ')
        .trim()
        .split(/\s+/)
        .filter(Boolean);

      if(words.length >= 2){
        return (words[0][0] + words[1][0]).toUpperCase();
      }

      return (title || 'T').slice(0, 2).toUpperCase();
    }

    function setGeneratedUnitFavicon(ctx){
      const initials = unitFaviconInitials(ctx);
      const svg =
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">' +
        '<rect width="64" height="64" rx="12" fill="#0b1220"/>' +
        '<path d="M8 16 L32 6 L56 16 V34 C56 48 45 57 32 61 C19 57 8 48 8 34 Z" fill="#1f3b73" stroke="#8fd8ff" stroke-width="3"/>' +
        '<path d="M16 32 H48 M32 16 V48" stroke="#8fd8ff" stroke-width="3" opacity="0.75"/>' +
        '<circle cx="32" cy="32" r="17" fill="none" stroke="#d7f4ff" stroke-width="2" opacity="0.55"/>' +
        '<text x="32" y="39" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="20" font-weight="800" fill="#ffffff">' +
        initials.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;') +
        '</text>' +
        '</svg>';

      const href = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);

      let link = document.querySelector("link[rel~='icon']");
      if(!link){
        link = document.createElement('link');
        link.rel = 'icon';
        document.head.appendChild(link);
      }
      link.type = 'image/svg+xml';
      link.href = href;

      let apple = document.querySelector("link[rel='apple-touch-icon']");
      if(!apple){
        apple = document.createElement('link');
        apple.rel = 'apple-touch-icon';
        document.head.appendChild(apple);
      }
      apple.href = href;
    }


    setGeneratedUnitFavicon(ctx);

    const node = A.findNodeForUnit(nodesResp, unitPath);
    const tabs = unitTabsApi();

    if(!tabs){
      S.clear(app);
      app.appendChild(renderHeaderCard(ctx));
      app.appendChild(renderNodeCard(node));
      app.appendChild(renderFilesCard(filesResp));
      app.appendChild(renderPolicyCard(bootstrapResp));
      app.appendChild(renderBootstrapCard(bootstrapResp));
      populateLaunchDefaults();
      wireBrandActions(ctx);
      wireNodeActions();
      wireFileActions(unitPath);
      wirePolicyActions(unitPath);
      wireBootstrapActions(unitPath, bootstrapResp);
      return;
    }

    const validation = tabs.computeValidation(node, filesResp, bootstrapResp);
    const allowedTabs = {
      overview: true,
      node: true,
      backups: true,
      files: true,
      config: true,
      advanced: true
    };

    let activeTab = String((window.TAKS_UNIT && window.TAKS_UNIT.activeTab) || '').trim();
    if(!allowedTabs[activeTab]){
      activeTab = tabs.firstBadTab(validation);
    }
    if(!allowedTabs[activeTab]){
      activeTab = 'overview';
    }

    S.clear(app);
    app.appendChild(renderHeaderCard(ctx));

    const shell = renderTabShell(activeTab, validation, function(nextTab){
      window.TAKS_UNIT.activeTab = nextTab;
      if(String(nextTab || '') !== 'node'){
        window.TAKS_UNIT.nodeAutoOpen = '';
      }
      render(app);
    });

    const body = S.el('div', { style: 'display:grid;gap:14px' });

    if(activeTab === 'node'){
      body.appendChild(renderNodePanel(node, validation, tabs));
    }else if(activeTab === 'backups'){
      body.appendChild(renderBackupsPanel(node, validation, tabs));
    }else if(activeTab === 'files'){
      body.appendChild(renderFilesPanel(filesResp, validation, tabs));
    }else if(activeTab === 'config'){
      body.appendChild(renderConfigPanel(bootstrapResp, validation, tabs));
    }else if(activeTab === 'advanced'){
      body.appendChild(renderAdvancedPanel(bootstrapResp));
    }else{
      body.appendChild(renderOverviewPanel(node, validation));
    }

    shell.appendChild(body);
    app.appendChild(shell);

    populateLaunchDefaults();
    wireBrandActions(ctx);
    wireNodeActions();
    wireFileActions(unitPath);
    wirePolicyActions(unitPath);
    wireBootstrapActions(unitPath, bootstrapResp);

    if(false && !validation.ready && activeTab !== 'overview'){
      flashFirstValidationTarget(body);
    }
  }


  window.TAKS_UNIT.render = render;
})();
