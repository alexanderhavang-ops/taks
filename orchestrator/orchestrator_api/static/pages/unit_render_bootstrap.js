/* global CORE */

(function(){

  window.TAKS_UNIT = window.TAKS_UNIT || {};

  const S = window.TAKS_UNIT.shared;

  const A = window.TAKS_UNIT.api;


  function tt(sv, en){
    return (window.CORE && window.CORE.lang === 'en') ? en : sv;
  }


  function render(){
    return window.TAKS_UNIT.render.apply(null, arguments);
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

  function _effectivePolicyId(bootstrapResp){
    try{
      const conf = ((bootstrapResp || {}).effective || {}).conf_d || {};
      const txt = String((conf["policy.conf"] || "")).trim();
      if(!txt) return "";
      const m = txt.match(/^\s*default_policy_id\s*=\s*(.+?)\s*$/m);
      return m ? String(m[1] || '').trim() : "";
    }catch(_e){
      return "";
    }
  }


  function renderPolicyCard(bootstrapResp, opts){
    const c = S.card('Policy');
    const policyId = _effectivePolicyId(bootstrapResp) || '—';
    const showSeedActions = !opts || opts.showSeedActions !== false;

    c.appendChild(
      S.el('div', {
        className: 'muted',
        text: tt(
          'Effektiv policy för denna nod efter arv i conf.d.',
          'Effective policy for this node after conf.d inheritance.'
        )
      })
    );

    c.appendChild(S.el('div', { style: 'height:8px' }));

    const grid = S.el('div', { className: 'grid grid--2' });
    grid.appendChild(
      S.field('default_policy_id', S.el('div', { text: policyId }))
    );
    c.appendChild(grid);

    if(showSeedActions){
      c.appendChild(S.el('div', { style: 'height:10px' }));

      c.appendChild(S.el('div', { className: 'card__actions' },
        S.el('button', {
          id: 'bootstrap_seed_critical_btn',
          className: 'btn btn--secondary',
          type: 'button',
          text: tt('Seed critical keys', 'Seed critical keys')
        })
      ));

      c.appendChild(S.el('div', {
        id: 'bootstrap_seed_critical_status',
        className: 'muted',
        style: 'margin-top:8px'
      }));
    }

    return c;
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

  function wirePolicyActions(unitPath){
    const btn = S.byId('bootstrap_seed_critical_btn');
    const status = S.byId('bootstrap_seed_critical_status');
    if(!btn || !status) return;

    btn.onclick = async function(){
      btn.disabled = true;
      status.className = 'muted';
      status.textContent = tt('Seedar kritiska nycklar…', 'Seeding critical keys…');
      try{
        const j = await A.seedCriticalBootstrap(unitPath, 'tak-node');
        const confAdded = ((((j || {}).seeded || {}).conf_d) || []).length;
        const secAdded = ((((j || {}).seeded || {}).secrets_d) || []).length;
        status.className = 'ok';
        status.textContent =
          tt('Klart. conf.d: ', 'Done. conf.d: ') + confAdded +
          ', secrets.d: ' + secAdded;
        await render();
      }catch(e){
        status.className = 'err';
        status.textContent = String(e && e.message ? e.message : e);
      }finally{
        btn.disabled = false;
      }
    };
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

  window.TAKS_UNIT.renderPolicyCard = renderPolicyCard;

  window.TAKS_UNIT.renderBootstrapCard = renderBootstrapCard;

  window.TAKS_UNIT.wirePolicyActions = wirePolicyActions;

  window.TAKS_UNIT.wireBootstrapActions = wireBootstrapActions;

})();
