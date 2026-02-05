(function(){
  async function fetchText(url){
    try{
      const r = await fetch(url, {cache:"no-store"});
      if(!r.ok) return "";
      return (await r.text()).trim();
    }catch(_){
      return "";
    }
  }

  function showSplash(){
    document.body.classList.add("__splash_on");
    const root = document.getElementById("__splash");
    if(root) root.style.display = "block";
  }

  function hideSplash(){
    document.body.classList.remove("__splash_on");
    const root = document.getElementById("__splash");
    if(root) root.style.display = "none";
  }

  function wireImgFallback(img){
    if(!img) return;
    const fb = img.getAttribute("data-fallback");
    if(!fb) return;
    img.addEventListener("error", function(){
      if(img.getAttribute("data-fallback-used")) return;
      img.setAttribute("data-fallback-used", "1");
      img.src = fb;
    });
  }

  async function loadSlogan(){
    // source of truth: runtime-uploaded slogan (symlinked into ./assets/)
    return await fetchText("./assets/slogan.txt");
  }

  async function render(){
    const root = document.getElementById("__splash");
    if(!root) return false;

    const html = await fetchText("./splash.html");
    if(!html) return false;

    root.innerHTML = html;
    return true;
  }

  async function wire(){
    // slogan
    const slogan = await loadSlogan();
    const el = document.getElementById("__splash_slogan");
    if(el) el.textContent = slogan || "";

    // logo fallback: prefer svg for logo1, fallback png
    wireImgFallback(document.getElementById("__logo1"));

    // hide if missing
    for(const id of ["__logo2","__logo3"]){
      const img = document.getElementById(id);
      if(img){
        img.addEventListener("error", ()=>{ try{ img.style.display="none"; }catch(_){} });
      }
    }

    // login wiring (kept simple)
    const btn = document.getElementById("__go");
    const u = document.getElementById("__u");
    const p = document.getElementById("__p");

    async function doLogin(){
      try{
        const r = await fetch("./api/login", {
          method: "POST",
          headers: {"content-type":"application/json"},
          body: JSON.stringify({username: (u && u.value)||"", password: (p && p.value)||""})
        });
        if(!r.ok){
          alert("Login failed");
          return;
        }
        hideSplash();
        window.location.reload();
      }catch(_){
        alert("Login failed");
      }
    }

    if(btn) btn.addEventListener("click", doLogin);
    if(p) p.addEventListener("keydown", (e)=>{ if(e.key==="Enter") doLogin(); });
    if(u) u.focus();
  }

  // boot
  (async function(){
    showSplash();
    const ok = await render();
    if(!ok){
      // if splash.html fails to load, keep page usable
      hideSplash();
      return;
    }
    wire();
  })();
})();
