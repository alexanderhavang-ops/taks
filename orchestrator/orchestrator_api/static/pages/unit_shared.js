/* global CORE */
(function(){
  window.TAKS_UNIT = window.TAKS_UNIT || {};

  function byId(id){
    return document.getElementById(id);
  }

  function clear(el){
    while(el && el.firstChild) el.removeChild(el.firstChild);
  }

  function txt(s){
    return document.createTextNode(String(s == null ? '' : s));
  }

  function el(tag, attrs){
    const node = document.createElement(tag);
    const a = attrs || {};
    Object.keys(a).forEach(function(k){
      const v = a[k];
      if(v == null) return;
      if(k === 'className') node.className = v;
      else if(k === 'text') node.textContent = String(v);
      else if(k === 'style') node.style.cssText = String(v);
      else if(k === 'value') node.value = v;
      else if(k === 'checked') node.checked = !!v;
      else if(k === 'onclick') node.onclick = v;
      else if(k === 'onchange') node.onchange = v;
      else if(k === 'oninput') node.oninput = v;
      else node.setAttribute(k, String(v));
    });
    for(let i = 2; i < arguments.length; i++){
      const child = arguments[i];
      if(child == null) continue;
      if(Array.isArray(child)){
        child.forEach(function(x){
          if(x == null) return;
          node.appendChild(typeof x === 'string' ? txt(x) : x);
        });
      }else{
        node.appendChild(typeof child === 'string' ? txt(child) : child);
      }
    }
    return node;
  }

  function card(title){
    const sec = el('section', { className: 'card' });
    if(title){
      sec.appendChild(el('div', { className: 'card__title', text: title }));
    }
    return sec;
  }

  function getRouteUnitPath(){
    const h = (location.hash || '').trim();
    if(!h.startsWith('#/')) return '';
    const rest = h.slice(2);
    const qpos = rest.indexOf('?');
    const path = (qpos >= 0 ? rest.slice(0, qpos) : rest);
    const parts = path.split('/').filter(Boolean);
    if(parts.length >= 2 && parts[0] === 'units'){
      try { return decodeURIComponent(parts.slice(1).join('/')); }
      catch (_) { return parts.slice(1).join('/'); }
    }
    return '';
  }

  function symbolHelp(sym){
    const s = String(sym || '').trim();
    const m = {
      'HQ': 'Headquarters',
      '•': 'Team',
      '••': 'Squad',
      '•••': 'Platoon',
      'I': 'Company',
      'II': 'Battalion',
      'III': 'Regiment',
      'X': 'Brigade',
      'XX': 'Division',
      'XXX': 'Corps',
      '⚑': 'Flag / command'
    };
    if(!s) return '';
    return m[s] || 'Custom';
  }

  function fmtAge(sec){
    if(sec == null) return '—';
    sec = Number(sec);
    if(sec < 60) return sec + 's ago';
    if(sec < 3600) return Math.floor(sec / 60) + 'm ago';
    if(sec < 86400) return Math.floor(sec / 3600) + 'h ago';
    return Math.floor(sec / 86400) + 'd ago';
  }

  function heartbeatState(node){
    const age = node && node.heartbeat_age_sec;
    if(age == null) return 'never';
    const sec = Number(age);
    if(sec <= 90) return 'online';
    if(sec <= 300) return 'stale';
    return 'lost';
  }

  function badge(textValue, kind){
    return el('span', { className: 'badge badge--' + kind, text: textValue || '—' });
  }

  function copyBtn(value){
    return el('button', {
      className: 'btn btn--secondary',
      type: 'button',
      text: 'Copy',
      onclick: function(){
        if(navigator.clipboard && value) navigator.clipboard.writeText(String(value));
      }
    });
  }

  function field(label, valueNode, spanCols){
    const wrap = el('div', { style: spanCols ? ('grid-column: span ' + spanCols + ';') : '' });
    wrap.appendChild(el('label', { className: 'label', text: label }));
    wrap.appendChild(valueNode);
    return wrap;
  }

  window.TAKS_UNIT.shared = {
    byId,
    clear,
    txt,
    el,
    card,
    getRouteUnitPath,
    symbolHelp,
    fmtAge,
    heartbeatState,
    badge,
    copyBtn,
    field
  };
})();
