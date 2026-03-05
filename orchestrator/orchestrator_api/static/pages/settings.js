/* global CORE */
(function(){
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
    `;

    const sv = document.getElementById('btn_lang_sv');
    const en = document.getElementById('btn_lang_en');
    if(sv) sv.onclick = () => CORE.setLang('sv');
    if(en) en.onclick = () => CORE.setLang('en');
  }

  window.TAKS_PAGES = window.TAKS_PAGES || {};
  window.TAKS_PAGES.settings = { render };
})();
