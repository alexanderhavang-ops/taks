(function(){
  // Load order matters: core -> app -> pages
  const files = [
    '/static/orch_core.js',
    '/static/orch_app.js',

    '/static/pages/nodes.js',
    '/static/pages/new_node.js',
    '/static/pages/new.js',
    '/static/pages/settings.js',
  ];

  function load(i){
    if(i >= files.length) return;
    const s = document.createElement('script');
    s.src = files[i];
    s.defer = true;
    s.onload = () => load(i+1);
    s.onerror = () => {
      console.error("Failed to load", files[i]);
      // Continue loading others so one missing file doesn't brick the UI
      load(i+1);
    };
    document.head.appendChild(s);
  }

  load(0);
})();
