(function(){
  function _byId(id){
    return document.getElementById(id);
  }

  function _val(id){
    const el = _byId(id);
    return (el && typeof el.value === 'string') ? el.value : '';
  }

  function _normUnitPath(s){
    // UI convenience: allow user to type /foo/bar, but store foo/bar
    s = String(s ?? '').trim();
    s = s.replace(/^\/+/, '');     // drop leading slashes
    s = s.replace(/\/+$/, '');     // drop trailing slashes
    return s;
  }

  function _normParentPath(s){
    // Parent path: allow "/" meaning root ("")
    s = String(s ?? '').trim();
    s = s.replace(/^\/+/, '');
    s = s.replace(/\/+$/, '');
    return s;
  }

  function payload(){
    return {
      unit_path: _normUnitPath(_val('unit_path')),
      title: String(_val('title') ?? '').trim(),
      parent_path: _normParentPath(_val('parent_path')),
    };
  }

  async function createUnit(){
    const out = _byId('out_raw');
    const p = payload();

    // Always show what we're about to send (debugging without guessing)
    if(out){
      out.textContent = "REQUEST:\n" + JSON.stringify(p, null, 2) + "\n\nRESPONSE:\n…";
    }

    if(!p.unit_path){
      if(out){
        out.textContent =
          "CLIENT ERROR: unit_path is empty after normalization.\n\n" +
          "Tip: use e.g. 46hvbat or forsvarsmakten (no leading slash).\n\n" +
          "REQUEST:\n" + JSON.stringify(p, null, 2);
      }
      return;
    }

    try{
      const j = await window.TAKS.api('POST', '/api/v2/units', p);
      if(out){
        out.textContent =
          "REQUEST:\n" + JSON.stringify(p, null, 2) + "\n\nRESPONSE:\n" +
          JSON.stringify(j, null, 2);
      }
    }catch(e){
      if(out){
        out.textContent =
          "REQUEST:\n" + JSON.stringify(p, null, 2) + "\n\nRESPONSE:\n" +
          String(e);
      }
    }
  }

  function render(container){
    container.innerHTML = `
      <section class="card">
        <div class="card__head">
          <h3>New unit</h3>
          <div class="card__actions">
            <a class="btn btn--secondary" href="#/nodes">Back</a>
            <button id="btn_create_unit" class="btn">Create</button>
          </div>
        </div>

        <div class="muted">
          Creates <code>unit.json</code> under <code>/opt/tak-orch/state/units/&lt;unit_path&gt;/unit.json</code>.
        </div>

        <div class="spacer"></div>

        <div class="grid grid--6">
          <div>
            <label class="label">unit_path</label>
            <input id="unit_path" placeholder="e.g. 46hvbat (no leading slash)" value="">
          </div>
          <div style="grid-column: span 2;">
            <label class="label">title</label>
            <input id="title" placeholder="e.g. 46. HVBataljon" value="">
          </div>
          <div style="grid-column: span 2;">
            <label class="label">parent_path</label>
            <input id="parent_path" placeholder="optional (use empty or / for root)" value="">
          </div>
        </div>

        <details open style="margin-top:12px">
          <summary>Raw response</summary>
          <pre id="out_raw">—</pre>
        </details>
      </section>
    `;

    _byId('btn_create_unit').onclick = createUnit;
  }

  window.TAKS_PAGES = window.TAKS_PAGES || {};
  window.TAKS_PAGES.new_unit = { render };
})();
