(function(){
  async function fetchText(url){
    try{
      const r = await fetch(url, { cache:"no-store", credentials:"include" });
      if(!r.ok) return "";
      return (await r.text()).trim();
    }catch(_){
      return "";
    }
  }

  async function fetchJson(url){
    try{
      const r = await fetch(url, { cache:"no-store", credentials:"include" });
      if(!r.ok) return null;
      const t = await r.text();
      try { return t ? JSON.parse(t) : null; } catch(_) { return null; }
    }catch(_){
      return null;
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

  function imgWithFallback(primary, fallback, alt, cls){
    return `
      <img class="${cls||""}"
           src="${primary}"
           alt="${alt||""}"
           onerror="this.onerror=null; this.src='${fallback}';">
    `;
  }

  async function loadSlogan(){
    // Source of truth: runtime-uploaded slogan via assets/slogan.txt (symlinked by installer)
    return await fetchText("./assets/slogan.txt");
  }

  function render(){
    const root = document.getElementById("__splash");
    if(!root) return;

    root.innerHTML = `
      <div class="splash">
        <div class="splash-main">
          <div class="splash-taks">
            <img src="./assets/taks-logo.png" alt="TAKS">
          </div>

          <div class="splash-slogan" id="__splash_slogan"></div>

          <div class="brandchain">
            <div class="brandchain-row">
              ${imgWithFallback("./assets/logo1.svg","./assets/logo1.png","Försvarsmakten","brandchain-logo")}
              <span class="brandchain-sep">›</span>
              <img class="brandchain-logo" src="./assets/logo2.png" alt="Hemvärnet" onerror="this.style.display='none'">
              <span class="brandchain-sep">›</span>
              <img class="brandchain-logo" src="./assets/logo3.png" alt="Militärregion" onerror="this.style.display='none'">
            </div>
          </div>
        </div>

        <div class="login-wrap">
          <div class="login">
            <div class="login-form">
              <div class="field">
                <label>Username</label>
                <input id="__u" autocomplete="username" />
              </div>

              <div class="field">
                <label>Password</label>
                <input id="__p" type="password" autocomplete="current-password" />
              </div>

              <div class="actions">
                <button id="__go" type="button">Sign in</button>
              </div>
            </div>

            <div class="login-err" id="__err"></div>
          </div>
        </div>
      </div>
    `;
  }

  function setErr(msg){
    const e = document.getElementById("__err");
    if(!e) return;
    if(!msg){
      e.style.display = "none";
      e.textContent = "";
      return;
    }
    e.style.display = "block";
    e.innerHTML = msg.includes("<") ? msg : String(msg);
  }

  async function wire(){
    const slogan = await loadSlogan();
    const el = document.getElementById("__splash_slogan");
    if(el) el.textContent = slogan || "";

    const btn = document.getElementById("__go");
    const u = document.getElementById("__u");
    const p = document.getElementById("__p");

    async function doLogin(){
      setErr("");
      const username = (u && u.value || "").trim();
      const password = (p && p.value || "").trim();

      if(!username || !password){
        setErr("Missing username or password.");
        return;
      }

      if(btn) btn.disabled = true;

      try{
        const r = await fetch("./api/login", {
          method: "POST",
          credentials: "include",
          headers: {"content-type":"application/json"},
          body: JSON.stringify({username, password})
        });

        if(!r.ok){
          let detail = "";
          try{
            const t = await r.text();
            try{ detail = JSON.parse(t)?.detail || t; }catch(_){ detail = t; }
          }catch(_){}
          setErr(`Login failed${detail ? `: <code>${String(detail).slice(0,200)}</code>` : "."}`);
          return;
        }

        // Verify session immediately (no “optimistic” hide)
        const who = await fetchJson("./api/whoami");
        if(who && who.authenticated === true){
          hideSplash();
          window.location.reload();
          return;
        }

        setErr("Login succeeded but session not established (whoami failed).");
      }catch(_){
        setErr("Login failed.");
      }finally{
        if(btn) btn.disabled = false;
      }
    }

    if(btn) btn.addEventListener("click", doLogin);
    if(p) p.addEventListener("keydown", (e)=>{ if(e.key==="Enter") doLogin(); });
    if(u) u.focus();
  }

  async function boot(){
    // If already authenticated, do NOT show splash at all.
    const who = await fetchJson("./api/whoami");
    if(who && who.authenticated === true){
      hideSplash();
      return;
    }

    showSplash();
    render();
    wire();
  }

  boot();
})();
