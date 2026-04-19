/* global CORE */

(function(){

  window.TAKS_UNIT = window.TAKS_UNIT || {};

  const S = window.TAKS_UNIT.shared;

  const A = window.TAKS_UNIT.api;

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
            logoImg.src = '/u/' + encodeURIComponent(ctx.unitPath) + '/branding/current.png?ts=' + Date.now();
            logoImg.style.display = '';
          }
          window.location.reload();
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

  window.TAKS_UNIT.wireBrandActions = wireBrandActions;

})();
