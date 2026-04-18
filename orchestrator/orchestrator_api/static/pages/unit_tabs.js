/* global CORE */
(function(){
  window.TAKS_UNIT = window.TAKS_UNIT || {};
  const S = window.TAKS_UNIT.shared;

  function issue(tab, code, message, target, severity){
    return {
      tab: String(tab || ''),
      code: String(code || ''),
      message: String(message || ''),
      target: String(target || ''),
      severity: String(severity || 'blocker')
    };
  }

  function makeTabState(){
    return { blockers: 0, warnings: 0, issues: [] };
  }

  function emptyValidation(){
    return {
      ready: true,
      blockers: 0,
      warnings: 0,
      tabs: {
        overview: makeTabState(),
        node: makeTabState(),
        files: makeTabState(),
        config: makeTabState()
      }
    };
  }

  function addIssue(validation, x){
    if(!validation || !x || !x.tab || !validation.tabs || !validation.tabs[x.tab]) return;
    validation.tabs[x.tab].issues.push(x);
    if(String(x.severity || '') === 'warning'){
      validation.tabs[x.tab].warnings += 1;
      validation.warnings += 1;
    }else{
      validation.tabs[x.tab].blockers += 1;
      validation.blockers += 1;
      validation.ready = false;
    }
  }

  function ensureMap(x){
    return (x && typeof x === 'object') ? x : {};
  }

  function mergedBootstrapMaps(bootstrapResp){
    const eff = ensureMap((bootstrapResp || {}).effective);
    const loc = ensureMap((bootstrapResp || {}).local);
    return {
      conf_d: Object.assign({}, ensureMap(eff.conf_d), ensureMap(loc.conf_d)),
      secrets_d: Object.assign({}, ensureMap(eff.secrets_d), ensureMap(loc.secrets_d))
    };
  }

  function escapeRe(s){
    return String(s || '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  function firstConfiguredValue(fileMap, keys){
    const texts = Object.values(ensureMap(fileMap)).map(function(v){
      return String(v || '');
    });
    const names = Array.isArray(keys) ? keys : [keys];

    for(let i = 0; i < names.length; i++){
      const rx = new RegExp('^\\s*' + escapeRe(names[i]) + '\\s*=\\s*(.*?)\\s*$', 'm');
      for(let j = 0; j < texts.length; j++){
        const m = texts[j].match(rx);
        if(m) return String(m[1] || '').trim();
      }
    }
    return '';
  }

  function hasTakserverDeb(filesResp){
    const subtrees = ensureMap((filesResp || {}).subtrees);
    const arr = Array.isArray(subtrees.packages) ? subtrees.packages : [];
    return arr.some(function(item){
      const candidates = [
        item && item.path,
        item && item.source_name,
        item && item.name
      ];
      return candidates.some(function(v){
        const leaf = String(v || '').toLowerCase().split('/').pop();
        return /^takserver_.*_all\.deb$/.test(leaf);
      });
    });
  }

  function computeValidation(node, filesResp, bootstrapResp){
    const v = emptyValidation();
    const maps = mergedBootstrapMaps(bootstrapResp);

    if(!hasTakserverDeb(filesResp)){
      addIssue(v, issue(
        'files',
        'missing_takserver_deb',
        'TakServer deb is not available in Packages.',
        'files-packages',
        'blocker'
      ));
    }

    const adminPassword = firstConfiguredValue(maps.secrets_d, ['takctl_admin_password', 'admin_password']);
    if(!adminPassword){
      addIssue(v, issue(
        'config',
        'missing_admin_password',
        'Admin password is not set.',
        'config-secrets',
        'blocker'
      ));
    }else if(/^changeme$/i.test(adminPassword)){
      addIssue(v, issue(
        'config',
        'placeholder_admin_password',
        'Admin password is still CHANGEME.',
        'config-secrets',
        'blocker'
      ));
    }

    const nodeFqdn = String((node && node.fqdn) || '').trim() ||
      firstConfiguredValue(maps.conf_d, ['node_fqdn', 'fqdn']);

    if(!nodeFqdn){
      addIssue(v, issue(
        'node',
        'missing_node_fqdn',
        'Node FQDN is not set.',
        'node-launch',
        'blocker'
      ));
    }

    return v;
  }

  function tabTone(tabState){
    if(!tabState) return 'secondary';
    if(tabState.blockers > 0) return 'err';
    if(tabState.warnings > 0) return 'warn';
    return 'secondary';
  }

  function firstBadTab(validation){
    if(!validation || !validation.tabs) return 'overview';
    if(validation.tabs.files && validation.tabs.files.blockers > 0) return 'files';
    if(validation.tabs.config && validation.tabs.config.blockers > 0) return 'config';
    if(validation.tabs.node && validation.tabs.node.blockers > 0) return 'node';
    return 'overview';
  }

  function renderReadinessCard(validation){
    const c = S.card('Boot readiness');
    const ready = !!(validation && validation.ready);

    c.appendChild(S.el('div', {
      style: 'display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap'
    },
      S.el('div', {
        className: 'muted',
        text: ready
          ? 'Node can be booted from current files and config.'
          : 'Fix the red tabs before boot.'
      }),
      S.badge(ready ? 'Ready' : 'Blocked', ready ? 'ok' : 'err')
    ));

    c.appendChild(S.el('div', {
      className: 'muted',
      style: 'margin-top:8px',
      text:
        'Blockers: ' + String((validation && validation.blockers) || 0) +
        ' · Warnings: ' + String((validation && validation.warnings) || 0)
    }));

    return c;
  }

  function renderIssueSummary(title, tabState){
    const c = S.card(title || 'Validation');
    const state = tabState || makeTabState();
    if(state.blockers === 0 && state.warnings === 0){
      c.appendChild(S.el('div', { className: 'ok', text: 'No issues detected.' }));
      return c;
    }

    c.appendChild(S.el('div', {
      className: state.blockers > 0 ? 'err' : 'muted',
      text: state.blockers > 0 ? 'Boot blockers found.' : 'Warnings found.'
    }));

    const list = S.el('div', { style: 'display:grid;gap:8px;margin-top:10px' });
    state.issues.forEach(function(x){
      list.appendChild(S.el('div', {
        className: x.severity === 'warning' ? 'muted' : 'err',
        style: 'white-space:normal',
        text: x.message
      }));
    });
    c.appendChild(list);
    return c;
  }

  function renderTabBar(activeTab, validation, onSelect){
    const labels = {
      overview: 'Overview',
      node: 'Node',
      files: 'Files',
      config: 'Config'
    };

    const bar = S.el('div', { style: 'display:flex;gap:8px;flex-wrap:wrap' });

    Object.keys(labels).forEach(function(key){
      const state = (validation && validation.tabs && validation.tabs[key]) || makeTabState();
      const tone = tabTone(state);
      const count = state.blockers > 0 ? state.blockers : state.warnings;
      const style = [
        'padding:10px 14px',
        'border-radius:12px',
        'border:1px solid ' + (
          tone === 'err' ? 'rgba(220,38,38,0.65)' :
          tone === 'warn' ? 'rgba(245,158,11,0.55)' :
          'rgba(255,255,255,0.12)'
        ),
        'background:' + (
          tone === 'err' ? 'rgba(220,38,38,0.16)' :
          tone === 'warn' ? 'rgba(245,158,11,0.16)' :
          'rgba(255,255,255,0.03)'
        ),
        key === activeTab ? 'opacity:1' : 'opacity:.92'
      ].join(';');

      const btn = S.el('button', {
        type: 'button',
        className: 'btn btn--secondary',
        style: style
      });

      btn.appendChild(S.el('span', { text: labels[key] }));
      if(count > 0){
        btn.appendChild(S.el('span', {
          style: 'display:inline-block;margin-left:8px;padding:1px 7px;border-radius:999px;font-size:12px',
          text: String(count)
        }));
      }

      btn.onclick = function(){
        if(typeof onSelect === 'function') onSelect(key);
      };

      bar.appendChild(btn);
    });

    return bar;
  }

  window.TAKS_UNIT.tabs = {
    issue: issue,
    emptyValidation: emptyValidation,
    computeValidation: computeValidation,
    tabTone: tabTone,
    firstBadTab: firstBadTab,
    renderReadinessCard: renderReadinessCard,
    renderIssueSummary: renderIssueSummary,
    renderTabBar: renderTabBar
  };
})();
