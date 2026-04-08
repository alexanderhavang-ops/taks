/* global CORE */
(function(){
  window.TAKS_PAGES = window.TAKS_PAGES || {};

  const FILES = [
    '/static/pages/unit_shared.js',
    '/static/pages/unit_api.js',
    '/static/pages/unit_render.js'
  ];

  let loadPromise = null;

  function esc(s){
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  function loadScript(src){
    return new Promise(function(resolve, reject){
      const existing = document.querySelector('script[data-unit-split="' + src + '"]');
      if(existing){
        if(existing.dataset.loaded === '1') return resolve();
        existing.addEventListener('load', function(){ resolve(); }, { once: true });
        existing.addEventListener('error', function(){ reject(new Error('Failed to load ' + src)); }, { once: true });
        return;
      }

      const s = document.createElement('script');
      s.src = src + '?v=20260408-snoozewake-1';
      s.async = false;
      s.dataset.unitSplit = src;
      s.onload = function(){
        s.dataset.loaded = '1';
        resolve();
      };
      s.onerror = function(){
        reject(new Error('Failed to load ' + src));
      };
      document.head.appendChild(s);
    });
  }

  async function ensureLoaded(){
    if(window.TAKS_UNIT && typeof window.TAKS_UNIT.render === 'function'){
      return;
    }
    if(!loadPromise){
      loadPromise = (async function(){
        for(const src of FILES){
          await loadScript(src);
        }
        if(!(window.TAKS_UNIT && typeof window.TAKS_UNIT.render === 'function')){
          throw new Error('TAKS unit modules failed to initialize');
        }
      })();
    }
    return loadPromise;
  }

  window.TAKS_PAGES.unit = {
    render: function(container){
      ensureLoaded()
        .then(function(){
          return window.TAKS_UNIT.render(container);
        })
        .catch(function(e){
          const app = container || document.getElementById('page') || document.getElementById('app');
          if(app){
            app.innerHTML =
              '<section class="card">' +
              '<div class="card__title">Unit</div>' +
              '<div class="err">' + esc(e && e.message ? e.message : e) + '</div>' +
              '</section>';
          }
        });
    }
  };
})();
