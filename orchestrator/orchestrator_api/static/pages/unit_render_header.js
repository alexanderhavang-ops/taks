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
    logoImg.onerror = function(){ this.style.display = 'none'; };
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
      accept: '.png',
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

    logoImg.onerror = function(){ this.style.display = 'none'; };

    const effectiveLogoUrl = (ctx.logoUrl && String(ctx.logoUrl).trim())
      ? String(ctx.logoUrl).trim()
      : ('/u/' + encodeURIComponent(ctx.unitPath) + '/branding/current.png');
    logoImg.src = effectiveLogoUrl + (effectiveLogoUrl.indexOf('?') >= 0 ? '&' : '?') + 'ts=' + Date.now();
    logoImg.style.display = '';

    return c;
  }

  window.TAKS_UNIT.renderHeaderCard = renderHeaderCard;

})();
