/* global CORE */
(function(){
  function esc(s){
    return String(s ?? '').replace(/[&<>"']/g, function(c){
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
    });
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

  async function apiPut(url, body){
    const r = await fetch(url, {
      method: 'PUT',
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

  function render(container){
    container.innerHTML = `
      <section class="card">
        <div class="card__head">
          <h3>${CORE.t('nav.settings')}</h3>
        </div>

        <div class="muted" style="margin-top:10px">
          <div style="margin-bottom:8px">Språk / Language</div>
          <div style="display:flex; gap:10px; flex-wrap:wrap;">
            <button id="btn_lang_sv" class="btn btn--secondary">Svenska</button>
            <button id="btn_lang_en" class="btn btn--secondary">English</button>
          </div>
        </div>
      </section>

      <section class="card" style="margin-top:16px;">
        <div class="card__head" style="display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap;">
          <div>
            <h3 style="margin:0;">Orchestrator config</h3>
            <div class="muted" id="cfg_meta" style="margin-top:6px;">Laddar…</div>
          </div>
          <div style="display:flex; gap:10px; flex-wrap:wrap;">
            <button id="btn_cfg_reload" class="btn btn--secondary">Ladda om</button>
            <button id="btn_cfg_save" class="btn">Spara</button>
          </div>
        </div>

        <div id="cfg_status" class="muted" style="margin-top:10px;"></div>

        <div style="margin-top:12px;">
          <textarea
            id="cfg_editor"
            spellcheck="false"
            style="
              width:100%;
              min-height:420px;
              box-sizing:border-box;
              resize:vertical;
              border-radius:12px;
              padding:14px;
              font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
              font-size:13px;
              line-height:1.5;
              background:#081225;
              color:#dbe7ff;
              border:1px solid rgba(255,255,255,0.12);
            "
          ></textarea>
        </div>

        <div class="muted" style="margin-top:10px;">
          Canonical config: <code>/etc/taks/tak_orch.conf</code><br>
          Secrets: <code>/etc/taks/secrets.conf</code>.
        </div>
      </section>
    `;

    const sv = document.getElementById('btn_lang_sv');
    const en = document.getElementById('btn_lang_en');
    const reloadBtn = document.getElementById('btn_cfg_reload');
    const saveBtn = document.getElementById('btn_cfg_save');
    const editor = document.getElementById('cfg_editor');
    const statusEl = document.getElementById('cfg_status');
    const metaEl = document.getElementById('cfg_meta');

    if(sv) sv.onclick = () => CORE.setLang('sv');
    if(en) en.onclick = () => CORE.setLang('en');

    async function loadCfg(){
      statusEl.textContent = 'Laddar config…';
      statusEl.style.color = '';
      try{
        const j = await apiGet('/api/v2/settings');
        editor.value = '';
        metaEl.textContent =
          'Config: ' + (j.config_path || '/etc/taks/tak_orch.conf') +
          (j.config_exists ? ' · finns' : ' · saknas') +
          ' | Secrets: ' + (j.secrets_path || '/etc/taks/secrets.conf') +
          (j.secrets_exists ? ' · finns' : ' · saknas');
        statusEl.textContent = 'OK';
      }catch(err){
        metaEl.textContent = 'Kunde inte läsa config';
        statusEl.textContent = 'Fel: ' + err.message;
        statusEl.style.color = '#ffb4b4';
      }
    }

    async function saveCfg(){
      statusEl.textContent = 'Skrivning flyttas till riktig config-editor';
      statusEl.style.color = '#ffb4b4';
    }

    if(reloadBtn) reloadBtn.onclick = loadCfg;
    if(saveBtn) saveBtn.onclick = saveCfg;

    loadCfg();
  }

  window.TAKS_PAGES = window.TAKS_PAGES || {};
  window.TAKS_PAGES.settings = { render };
})();
