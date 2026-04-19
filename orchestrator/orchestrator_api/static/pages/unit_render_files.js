/* global CORE */

(function(){

  window.TAKS_UNIT = window.TAKS_UNIT || {};

  const S = window.TAKS_UNIT.shared;

  const A = window.TAKS_UNIT.api;


  function render(){
    return window.TAKS_UNIT.render.apply(null, arguments);
  }

  function subtreeLabel(name){
    const m = {
      packages: 'Packages',
      branding: 'Branding',
      users: 'Users',
      plugins: 'Plugins',
      maps: 'Maps',
      missions: 'Missions',
      documents: 'Documents',
      misc: 'Misc'
    };
    return m[name] || name;
  }

  function renderFilesCard(filesResp){
    const c = S.card('Enhetsfiler');
    const subtrees = (filesResp && filesResp.subtrees) ? filesResp.subtrees : {};
    const subtreeErrors = (filesResp && filesResp.subtree_errors) ? filesResp.subtree_errors : {};
    const order = ['packages', 'branding', 'users', 'plugins', 'maps', 'missions', 'documents', 'misc'];

    const top = S.el('div', { className: 'grid grid--6', style: 'margin-top:10px' });
    const subtreeCol = S.el('div');
    subtreeCol.appendChild(S.el('label', { className: 'label', text: 'Subtree' }));
    const subtreeSel = S.el('select', { id: 'unit_file_subtree' });
    order.forEach(function(name){
      subtreeSel.appendChild(S.el('option', { value: name, text: subtreeLabel(name) }));
    });
    subtreeCol.appendChild(subtreeSel);

    const nameCol = S.el('div', { style: 'grid-column: span 3;' });
    nameCol.appendChild(S.el('label', { className: 'label', text: 'Målfilnamn / relativ sökväg' }));
    nameCol.appendChild(S.el('input', {
      id: 'unit_file_name',
      placeholder: 't.ex. takserver.tar.gz eller config/example.txt'
    }));

    const btnCol = S.el('div', { style: 'display:flex;align-items:flex-end;gap:8px;' });
    btnCol.appendChild(S.el('button', {
      id: 'unit_file_upload_btn',
      className: 'btn',
      text: 'Ladda upp fil'
    }));
    btnCol.appendChild(S.el('input', {
      id: 'unit_file_input',
      type: 'file',
      style: 'display:none'
    }));

    top.appendChild(subtreeCol);
    top.appendChild(nameCol);
    top.appendChild(btnCol);
    c.appendChild(top);
    c.appendChild(S.el('div', { id: 'unit_file_upload_status', className: 'muted', style: 'margin-top:8px' }));

    order.forEach(function(name){
      const arr = Array.isArray(subtrees[name]) ? subtrees[name] : [];
      const subtreeError = String((subtreeErrors && subtreeErrors[name]) || '').trim();
      const box = S.el('div', { className: 'card', style: 'margin-top:14px' });
      box.appendChild(S.el('div', { className: 'card__title', text: subtreeLabel(name) }));

      if(subtreeError){
        box.appendChild(S.el('div', {
          className: 'err',
          style: 'margin-top:8px;white-space:normal;word-break:break-word',
          text: subtreeError
        }));
      }else if(!arr.length){
        box.appendChild(S.el('div', { className: 'muted', text: 'Tomt.' }));
      }else{
        const list = S.el('div', { style: 'display:grid;gap:8px' });

        arr.forEach(function(item){
          const inherited = !!item.inherited;
          const row = S.el('div', {
            style: 'display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;align-items:flex-start'
          });

          const left = S.el('div', { style: 'min-width:0;flex:1 1 auto' });
          const link = S.el('a', {
            href: item.download_url || '#',
            text: item.path || '',
            style: inherited
              ? 'font-style:italic;text-decoration:none'
              : 'text-decoration:none'
          });
          if(item.download_url){
            link.setAttribute('download', '');
          }
          left.appendChild(link);

          if(inherited){
            left.appendChild(S.el('div', {
              className: 'muted',
              style: 'font-style:italic;margin-top:4px',
              text: 'ärvd från ' + String(item.source_unit || 'okänd')
            }));
          }else if(item.source_unit){
            left.appendChild(S.el('div', {
              className: 'muted',
              style: 'margin-top:4px',
              text: 'lokal för ' + String(item.source_unit)
            }));
          }

          if(item.slot){
            left.appendChild(S.el('div', {
              className: 'muted',
              style: 'margin-top:4px',
              text: 'slot ' + String(item.slot)
            }));
          }

          if(item.source_name && item.source_name !== item.path){
            left.appendChild(S.el('div', {
              className: 'muted',
              style: 'margin-top:4px',
              text: 'källa: ' + String(item.source_name)
            }));
          }

          const right = S.el('div', {
            style: 'display:flex;gap:8px;align-items:center;flex-wrap:wrap;justify-content:flex-end'
          });

          const meta = [];
          if(item.bytes != null) meta.push(String(item.bytes) + ' B');
          if(item.kind) meta.push(String(item.kind));
          right.appendChild(S.el('div', { className: 'muted', text: meta.join(' · ') }));

          if(!inherited && item.delete_url){
            right.appendChild(S.el('button', {
              className: 'btn btn--danger',
              text: 'Ta bort',
              type: 'button',
              'data-delete-url': item.delete_url,
              'data-file-path': item.path || ''
            }));
          }

          row.appendChild(left);
          row.appendChild(right);
          list.appendChild(row);
        });

        box.appendChild(list);
      }

      c.appendChild(box);
    });

    return c;
  }

  function wireFileActions(unitPath){
    const fileBtn = S.byId('unit_file_upload_btn');
    const fileInp = S.byId('unit_file_input');
    const fileStatus = S.byId('unit_file_upload_status');

    if(fileBtn && fileInp){
      fileBtn.onclick = function(){ fileInp.click(); };
      fileInp.onchange = async function(){
        const f = fileInp.files && fileInp.files[0];
        const subtree = S.byId('unit_file_subtree') ? S.byId('unit_file_subtree').value : '';
        const nameInp = S.byId('unit_file_name');
        let name = nameInp ? nameInp.value.trim() : '';

        if(!f) return;

        if(!name && f.name){
          name = f.name;
          if(nameInp) nameInp.value = name;
        }

        if(!subtree || !name){
          if(fileStatus){
            fileStatus.textContent = 'Välj subtree först. Målfilnamn fylls nu automatiskt från filnamnet om det lämnas tomt.';
            fileStatus.className = 'err';
          }
          fileInp.value = '';
          return;
        }

        if(fileStatus){
          fileStatus.textContent = 'Laddar upp…';
          fileStatus.className = 'muted';
        }

        try{
          await A.uploadUnitFile(unitPath, subtree, name, f);
          if(fileStatus){
            fileStatus.textContent = 'Fil uppladdad.';
            fileStatus.className = 'ok';
          }
          render();
        }catch(e){
          if(fileStatus){
            fileStatus.textContent = String(e && e.message ? e.message : e);
            fileStatus.className = 'err';
          }
        }finally{
          fileInp.value = '';
        }
      };
    }

    document.querySelectorAll('button[data-delete-url]').forEach(function(btn){
      btn.onclick = async function(){
        const url = btn.getAttribute('data-delete-url') || '';
        const path = btn.getAttribute('data-file-path') || 'filen';
        if(!url) return;
        if(!confirm('Ta bort ' + path + '?')) return;

        if(fileStatus){
          fileStatus.textContent = 'Tar bort…';
          fileStatus.className = 'muted';
        }

        try{
          const r = await fetch(url, { method: 'DELETE', credentials: 'include' });
          if(!r.ok){
            let msg = '';
            try{
              const j = await r.json();
              msg = (j && j.detail) ? String(j.detail) : JSON.stringify(j);
            }catch(_){
              try { msg = (await r.text() || '').trim(); }
              catch(__) { msg = ''; }
            }
            throw new Error(msg || ('HTTP ' + r.status));
          }

          if(fileStatus){
            fileStatus.textContent = 'Fil borttagen.';
            fileStatus.className = 'ok';
          }
          render();
        }catch(e){
          if(fileStatus){
            fileStatus.textContent = String(e && e.message ? e.message : e);
            fileStatus.className = 'err';
          }
        }
      };
    });
  }

  window.TAKS_UNIT.renderFilesCard = renderFilesCard;

  window.TAKS_UNIT.wireFileActions = wireFileActions;

})();
