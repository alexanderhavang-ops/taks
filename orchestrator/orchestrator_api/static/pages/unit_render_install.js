/* global CORE */

(function(){

  window.TAKS_UNIT = window.TAKS_UNIT || {};

  const S = window.TAKS_UNIT.shared;

  const A = window.TAKS_UNIT.api;


  function lightPill(){
    return (window.TAKS_UNIT && typeof window.TAKS_UNIT.lightPill === 'function')
      ? window.TAKS_UNIT.lightPill.apply(null, arguments)
      : S.el('span', { style: 'font-weight:700', text: String(arguments[1] || '—') });
  }

  function nodeStatusSnapshot(){
    return (window.TAKS_UNIT && typeof window.TAKS_UNIT.nodeStatusSnapshot === 'function')
      ? window.TAKS_UNIT.nodeStatusSnapshot.apply(null, arguments)
      : { tone: 'muted', text: '◌ Unknown', detail: '', stale: true, hb: 'never', awsState: '', derivedStatus: '' };
  }

  function installStateKind(state){
    const s = String(state || '').trim().toLowerCase();
    if(s === 'succeeded') return 'ok';
    if(s === 'not_complete') return 'err';
    if(s === 'completed_with_warnings') return 'err';
    if(s === 'failed') return 'err';
    if(s === 'running' || s === 'incomplete') return 'warn';
    if(s === 'stale') return 'warn';
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
    if(s === 'stale') return 'Senast känd';
    return 'Okänd';
  }

  function installBarColor(state){
    const s = String(state || '').trim().toLowerCase();
    if(s === 'succeeded') return '#16a34a';
    if(s === 'not_complete') return '#dc2626';
    if(s === 'completed_with_warnings') return '#dc2626';
    if(s === 'failed') return '#dc2626';
    if(s === 'running' || s === 'incomplete') return '#d97706';
    if(s === 'stale') return '#d97706';
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
    const snap = nodeStatusSnapshot(node);
    const stale = !!snap.stale;
    const visualState = stale ? 'stale' : installVisualState(summary);
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
    head.appendChild(lightPill(installStateKind(visualState), installStateLabel(visualState)));
    wrap.appendChild(head);

    const metaBits = [];
    if(total > 0) metaBits.push(completed + '/' + total + ' steg klara');
    if(failed > 0) metaBits.push(failed + ' fel');
    if(running > 0) metaBits.push(running + ' pågår');
    if(incomplete > 0) metaBits.push(incomplete + ' oavslutade');
    if(stale) metaBits.push('senast känd');
    if(summary.last_event_ts) metaBits.push('senast ' + summary.last_event_ts);
    wrap.appendChild(S.el('div', { className: 'muted', text: metaBits.join(' • ') || 'Ingen installationsdata' }));

    const details = S.el('details', { style: 'margin-top:2px' });
    if(window.TAKS_UNIT && window.TAKS_UNIT.nodeAutoOpen === 'install') details.open = true;
    details.appendChild(S.el('summary', { text: 'Visa installationsdetaljer' }));

    const inner = S.el('div', { style: 'display:grid;gap:10px;margin-top:10px' });

    const barOuter = S.el('div', {
      style: 'height:10px;border-radius:999px;background:rgba(255,255,255,0.10);overflow:hidden'
    });
    barOuter.appendChild(S.el('div', {
      style: 'height:100%;border-radius:999px;width:' + pct + '%;background:' + installBarColor(visualState)
    }));
    inner.appendChild(barOuter);

    if(stale){
      inner.appendChild(S.el('div', {
        className: 'muted',
        style: 'padding:8px 10px;border:1px solid rgba(245,158,11,0.35);border-radius:10px;background:rgba(245,158,11,0.08)',
        text: snap.hb === 'lost'
          ? 'Heartbeat är förlorad. Installationen nedan visas som senast kända värden.'
          : 'Heartbeat är gammal. Installationen nedan kan vara inaktuell.'
      }));
    }

    if(incomplete > 0 || failed > 0){
      inner.appendChild(S.el('div', {
        className: 'muted',
        style: 'padding:8px 10px;border:1px solid rgba(220,38,38,0.35);border-radius:10px;background:rgba(220,38,38,0.08)',
        text: failed > 0
          ? 'Installationen har fel. Fäll ut stegen nedan för att se var det gick fel.'
          : 'Installationen är inte komplett: vissa delsteg saknar avslutande status i loggen.'
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
        row.appendChild(lightPill(installStateKind(step.state || step.status || 'unknown'), installStateLabel(step.state || step.status || 'unknown')));
        row.appendChild(S.el('div', { className: 'muted', text: step.last_ts || '—' }));
        stepsWrap.appendChild(row);
      });

      stepsDetails.appendChild(stepsWrap);
      inner.appendChild(stepsDetails);
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
        row.appendChild(lightPill(installStateKind(ev.state || 'unknown'), installStateLabel(ev.state || 'unknown')));
        logBox.appendChild(row);
      });

      eventsDetails.appendChild(logBox);
      inner.appendChild(eventsDetails);
    }

    details.appendChild(inner);
    wrap.appendChild(details);

    return wrap;
  }


  window.TAKS_UNIT.clearInstallProgressState = clearInstallProgressState;
  window.TAKS_UNIT.renderInstallProgress = renderInstallProgress;
})();
