/* global CORE */
(function(){
  let pageLang = 'sv';
  let state = {
    current: null,
    showAdvanced: false,
    loading: false,
    saving: false,
    error: ''
  };

  function esc(s){
    return String(s ?? '').replace(/[&<>"']/g, function(c){
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
    });
  }

  function lang(){ return pageLang === 'en' ? 'en' : 'sv'; }
  function tr(sv, en){ return lang() === 'en' ? en : sv; }
  function setPageLang(v){ pageLang = String(v || 'sv').toLowerCase() === 'en' ? 'en' : 'sv'; }

  function componentTitle(name){
    const n = String(name || '').toLowerCase();
    if(n === 'core') return tr('Kärna', 'Core');
    if(n === 'auth') return tr('Autentisering', 'Authentication');
    return n ? (n.charAt(0).toUpperCase() + n.slice(1)) : tr('Övrigt', 'Other');
  }

  function levelLabel(v){
    const s = String(v || '').toLowerCase();
    return s === 'advanced' ? 'advanced' : 'basic';
  }

  function typeLabel(v){
    const s = String(v || '').toLowerCase();
    if(s === 'bool' || s === 'boolean') return 'bool';
    if(s === 'int' || s === 'integer') return tr('heltal', 'integer');
    if(s === 'number') return tr('nummer', 'number');
    if(s === 'string') return tr('sträng', 'string');
    return s || tr('sträng', 'string');
  }

  async function apiGet(url, opts){
    const r = await fetch(url, Object.assign({
      credentials: 'same-origin',
      headers: { 'accept': 'application/json' }
    }, opts || {}));
    if(!r.ok){
      let msg = r.status + ' ' + r.statusText;
      try{
        const j = await r.json();
        if(j && j.detail) msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail, null, 2);
      }catch(_e){}
      throw new Error(msg);
    }
    return r.json();
  }

  async function apiPost(url, body){
    const r = await fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'content-type': 'application/json',
        'accept': 'application/json'
      },
      body: JSON.stringify(body || {})
    });
    if(!r.ok){
      let msg = r.status + ' ' + r.statusText;
      try{
        const j = await r.json();
        if(j && j.detail) msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail, null, 2);
      }catch(_e){}
      throw new Error(msg);
    }
    return r.json();
  }

  function truthy(v){
    return String(v ?? '').trim().toLowerCase() === 'true';
  }

  function badge(text, kind){
    const styles = {
      ok:    'border:1px solid rgba(46,160,67,.45); background:rgba(46,160,67,.18); color:#d7ffe1;',
      warn:  'border:1px solid rgba(187,128,9,.45); background:rgba(187,128,9,.18); color:#ffe7b3;',
      muted: 'border:1px solid rgba(255,255,255,.12); background:rgba(255,255,255,.05); color:#dbe7ff;'
    };
    return `<span style="display:inline-flex; align-items:center; padding:2px 10px; border-radius:999px; font-size:12px; line-height:18px; ${styles[kind || 'muted']}">${esc(text)}</span>`;
  }

  function inputBaseStyle(){
    return [
      'width:100%',
      'box-sizing:border-box',
      'border-radius:12px',
      'padding:10px 12px',
      'border:1px solid rgba(255,255,255,.12)',
      'background:#081225',
      'color:#dbe7ff',
      'outline:none'
    ].join('; ');
  }

  function metaLine(field){
    const bits = [];
    if(field.type) bits.push(tr('typ', 'type') + ': ' + typeLabel(field.type));
    if(field.level) bits.push(tr('nivå', 'level') + ': ' + levelLabel(field.level));
    if(Object.prototype.hasOwnProperty.call(field, 'default') && String(field.default || '') !== ''){
      bits.push(tr('standard', 'default') + ': ' + String(field.default));
    }
    if(Array.isArray(field.enum) && field.enum.length){
      bits.push(tr('val', 'options') + ': ' + field.enum.join(', '));
    }
    if(Object.prototype.hasOwnProperty.call(field, 'min') && field.min !== null && field.min !== ''){
      bits.push('min: ' + String(field.min));
    }
    if(Object.prototype.hasOwnProperty.call(field, 'max') && field.max !== null && field.max !== ''){
      bits.push('max: ' + String(field.max));
    }
    return bits.join(' · ');
  }

  function fieldInputHtml(componentName, fieldName, field, currentValue, hasSecret){
    const id = 'fld_' + componentName + '__' + fieldName;
    const type = String(field.type || 'string').toLowerCase();
    const secret = !!field.secret;
    const enumVals = Array.isArray(field.enum) ? field.enum : [];
    const value = currentValue == null ? '' : String(currentValue);

    if(secret){
      return `
        <input
          id="${esc(id)}"
          data-component="${esc(componentName)}"
          data-field="${esc(fieldName)}"
          data-secret="true"
          type="password"
          placeholder="${hasSecret ? tr('Finns lagrad; skriv för att ersätta', 'Stored; enter to replace') : tr('Ange hemlighet', 'Enter secret')}"
          value=""
          style="${inputBaseStyle()}"
        />
      `;
    }

    if(enumVals.length){
      const opts = enumVals.map(function(v){
        const sel = String(v) === value ? ' selected' : '';
        return `<option value="${esc(v)}"${sel}>${esc(v)}</option>`;
      }).join('');
      return `
        <select
          id="${esc(id)}"
          data-component="${esc(componentName)}"
          data-field="${esc(fieldName)}"
          data-type="${esc(type)}"
          style="${inputBaseStyle()}"
        >${opts}</select>
      `;
    }

    if(type === 'bool' || type === 'boolean'){
      const cur = truthy(value);
      return `
        <select
          id="${esc(id)}"
          data-component="${esc(componentName)}"
          data-field="${esc(fieldName)}"
          data-type="bool"
          style="${inputBaseStyle()}"
        >
          <option value="true"${cur ? ' selected' : ''}>true</option>
          <option value="false"${!cur ? ' selected' : ''}>false</option>
        </select>
      `;
    }

    if(type === 'int' || type === 'integer' || type === 'number'){
      return `
        <input
          id="${esc(id)}"
          data-component="${esc(componentName)}"
          data-field="${esc(fieldName)}"
          data-type="${esc(type)}"
          type="number"
          value="${esc(value)}"
          style="${inputBaseStyle()}"
        />
      `;
    }

    return `
      <input
        id="${esc(id)}"
        data-component="${esc(componentName)}"
        data-field="${esc(fieldName)}"
        data-type="${esc(type)}"
        type="text"
        value="${esc(value)}"
        style="${inputBaseStyle()}"
      />
    `;
  }

  function fieldIsAdvanced(field){
    return String((field && field.level) || 'basic').toLowerCase() === 'advanced';
  }

  function renderField(componentName, name, field, values, hasSecrets){
    const currentValue = field.secret ? '' : (field.value ?? values[name] ?? '');
    const hasSecret = !!(hasSecrets && hasSecrets[name]);
    const meta = metaLine(field);
    const doc = String(field.doc || '');

    return `
      <div style="
        display:grid;
        grid-template-columns:minmax(260px, 360px) minmax(320px, 1fr) auto;
        gap:14px;
        align-items:start;
        padding:14px 0;
        border-top:1px solid rgba(255,255,255,.06);
      ">
        <div>
          <div style="font-size:13px; font-weight:800; color:#f3f7ff; padding-top:8px;">${esc(name)}</div>
          ${meta ? `<div class="muted" style="margin-top:6px; font-size:12px;">${esc(meta)}</div>` : ''}
        </div>

        <div>
          ${fieldInputHtml(componentName, name, field, currentValue, hasSecret)}
          ${doc ? `<div class="muted" style="margin-top:6px; line-height:1.45;">${esc(doc)}</div>` : ''}
          ${field.secret ? `<div class="muted" style="margin-top:6px;">${hasSecret ? tr('Hemlighet finns i runtime; lämna tomt för att behålla nuvarande värde.', 'Secret exists in runtime; leave blank to keep current value.') : tr('Hemlighet är tom just nu.', 'Secret is currently empty.')}</div>` : ''}
        </div>

        <div style="padding-top:8px; display:flex; justify-content:flex-end;">
          ${field.secret ? (hasSecret ? badge(tr('hemlighet satt', 'secret set'), 'ok') : badge(tr('hemlighet tom', 'secret empty'), 'warn')) : badge(typeLabel(field.type || 'string'), 'muted')}
        </div>
      </div>
    `;
  }

  function renderComponent(component, values, hasSecrets, showAdvanced){
    const fields = component && component.fields ? component.fields : {};
    const names = Object.keys(fields).sort().filter(function(name){
      if(showAdvanced) return true;
      return !fieldIsAdvanced(fields[name] || {});
    });

    const rows = names.map(function(name){
      return renderField(String(component.component || 'other'), name, fields[name] || {}, values, hasSecrets);
    }).join('');

    const hiddenCount = Object.keys(fields).length - names.length;

    return `
      <section class="card" style="margin-top:18px; padding:18px 18px 8px 18px; border-radius:18px;">
        <div style="display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; margin-bottom:4px;">
          <div>
            <h3 style="margin:0;">${esc(componentTitle(component.component || 'other'))}</h3>
            <div class="muted" style="margin-top:6px;">
              ${names.length} ${tr('fält', 'fields')}${hiddenCount > 0 ? ' · ' + hiddenCount + ' ' + tr('dolda advanced', 'hidden advanced') : ''}
            </div>
          </div>
          <div>${badge(componentTitle(component.component || 'other'), 'muted')}</div>
        </div>
        <div>${rows}</div>
      </section>
    `;
  }

  function collectPayload(components){
    const config_updates = {};
    const secret_updates = {};

    (components || []).forEach(function(component){
      const cname = String(component.component || 'other');
      const fields = component.fields || {};
      Object.keys(fields).forEach(function(name){
        const field = fields[name] || {};
        const id = 'fld_' + cname + '__' + name;
        const el = document.getElementById(id);
        if(!el) return;
        const val = String(el.value ?? '');
        if(field.secret){
          if(val.trim() !== '') secret_updates[name] = val;
        } else {
          config_updates[name] = val;
        }
      });
    });

    return { config_updates, secret_updates };
  }

  function renderPage(container){
    const current = state.current;
    const values = (current && current.values) || {};
    const hasSecrets = (current && current.has_secrets) || {};
    const components = (current && Array.isArray(current.components)) ? current.components : [];

    const statusHtml = state.error
      ? badge(tr('fel', 'error') + ': ' + state.error, 'warn')
      : state.saving
      ? badge(tr('sparar…', 'saving…'), 'muted')
      : state.loading
      ? badge(tr('laddar…', 'loading…'), 'muted')
      : current
      ? badge(tr('laddad', 'loaded'), 'ok')
      : '';

    const metaHtml = current
      ? 'Config: <code>' + esc(current.config_path || '/opt/tak-orch/orchestrator/conf.d') + '</code>' +
        (current.config_exists ? ' · ' + tr('finns', 'exists') : ' · ' + tr('saknas', 'missing')) +
        ' | Secrets: <code>' + esc(current.secrets_path || '/opt/tak-orch/orchestrator/secrets.d') + '</code>' +
        (current.secrets_exists ? ' · ' + tr('finns', 'exists') : ' · ' + tr('saknas', 'missing'))
      : tr('Laddar…', 'Loading…');

    container.innerHTML = `
      <section class="card" style="padding:20px; border-radius:18px;">
        <div style="display:flex; align-items:flex-start; justify-content:space-between; gap:18px; flex-wrap:wrap;">
          <div>
            <h3 style="margin:0 0 8px 0;">${tr('Inställningar', 'Settings')}</h3>
            <div class="muted" style="max-width:900px; line-height:1.5;">
              ${tr('Runtime-config för orchestratorn.', 'Runtime config for the orchestrator.')}
            </div>
            <div class="muted" style="margin-top:10px;">${metaHtml}</div>
          </div>

          <div style="display:flex; gap:10px; flex-wrap:wrap; align-items:center;">
            <button id="btn_cfg_toggle_advanced" type="button" class="${state.showAdvanced ? 'btn' : 'btn btn--secondary'}">${state.showAdvanced ? tr('Dölj advanced', 'Hide advanced') : tr('Visa advanced', 'Show advanced')}</button>
            <button id="btn_cfg_reload" class="btn btn--secondary">${tr('Ladda om', 'Reload')}</button>
            <button id="btn_cfg_save" class="btn">${tr('Spara', 'Save')}</button>
          </div>
        </div>

        <div style="margin-top:12px;">${statusHtml}</div>

        <div style="display:flex; gap:10px; flex-wrap:wrap; margin-top:12px;">
          ${badge('/opt/tak-orch/orchestrator/conf.d', 'muted')}
          ${badge('/opt/tak-orch/orchestrator/secrets.d', 'muted')}
        </div>
      </section>

      ${components.map(function(component){
        return renderComponent(component, values, hasSecrets, state.showAdvanced);
      }).join('')}
    `;

    document.getElementById('btn_cfg_toggle_advanced').onclick = function(){
      state.showAdvanced = !state.showAdvanced;
      renderPage(container);
    };
    document.getElementById('btn_cfg_reload').onclick = function(){
      loadCfg(container);
    };
    document.getElementById('btn_cfg_save').onclick = function(){
      saveCfg(container);
    };
  }

  async function loadCfg(container){
    state.loading = true;
    state.error = '';
    renderPage(container);

    try{
      const j = await apiGet('/api/v2/settings');
      state.current = j;
      setPageLang(((j.values || {}).system_language) || 'sv');
      state.loading = false;
      renderPage(container);
    }catch(err){
      state.loading = false;
      state.error = err.message || String(err);
      renderPage(container);
    }
  }

  async function saveCfg(container){
    if(!state.current){
      state.error = tr('ingen config laddad', 'no config loaded');
      renderPage(container);
      return;
    }

    const payload = collectPayload(state.current.components || []);

    state.saving = true;
    state.error = '';
    renderPage(container);

    try{
      const j = await apiPost('/api/v2/settings', payload);
      state.current = j;
      setPageLang(((j.values || {}).system_language) || 'sv');
      state.saving = false;
      renderPage(container);
    }catch(err){
      state.saving = false;
      state.error = err.message || String(err);
      renderPage(container);
    }
  }

  window.TAKS_PAGES = window.TAKS_PAGES || {};
  window.TAKS_PAGES.settings = {
    render: function(container){
      state = {
        current: null,
        showAdvanced: false,
        loading: false,
        saving: false,
        error: ''
      };
      renderPage(container);
      loadCfg(container);
    }
  };
})();
