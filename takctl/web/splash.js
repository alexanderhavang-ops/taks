(function () {
  "use strict";

  var BASE = "./"; // root-native (relative)
  var WHOAMI = BASE + "api/whoami";
  var LOGIN  = BASE + "api/login";
  var FRAG   = BASE + "splash.fragment.html";

  function $(id) { return document.getElementById(id); }

  function unitFromQuery() {
    try {
      var u = new URL(window.location.href);
      return (u.searchParams.get("unit") || "").trim();
    } catch (_) {
      return "";
    }
  }

  var UNIT = unitFromQuery();
  var BRAND = BASE + "api/public/brand" + (UNIT ? ("?unit=" + encodeURIComponent(UNIT)) : "");

  function setErr(msg) {
    var e = $("__err");
    if (!e) return;
    e.textContent = msg || "";
    e.style.display = msg ? "block" : "none";
  }

  function setSlogan(text) {
    var el = $("__splash_slogan");
    if (!el) return;
    var t = (text == null ? "" : String(text)).trim();
    el.textContent = t ? t : "TAKS";
  }

  function logoUrlUnit(n, ext) {
    if (!UNIT) return null;
    return BASE + "u/" + encodeURIComponent(UNIT) + "/assets/logo" + n + "." + ext;
  }

  function logoUrlShared(n, ext) {
    return BASE + "assets/logo" + n + "." + ext;
  }

  function renderBrandLogos() {
    var host = document.getElementById("__brand_logos");
    if (!host) return;

    host.innerHTML = "";

    fetch(BRAND, { cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (b) {
        if (!b) { setSlogan("TAKS"); return; }

        setSlogan(b.slogan);

        // Role field toggle (shared splash.fragment.html):
        // Default: show role if present.
        // If brand.json contains { "login": { "role": false } }, hide it (node login).
        try {
          var rf = document.getElementById("__r");
          if (rf) {
            var wantRole = true;
            if (b && b.login && b.login.role === false) wantRole = false;
            // hide the whole field wrapper (the parent .field)
            var wrap = rf.closest ? rf.closest(".field") : null;
            if (wrap) wrap.style.display = wantRole ? "" : "none";
            else rf.style.display = wantRole ? "" : "none";
          }
        } catch (_) {}


        if (!b.logos || !b.logos.length) return;

        b.logos.forEach(function (it) {
          if (!it || it.uploaded !== true) return;
          var n = it.n;
          if (!(n >= 1 && n <= 4)) return;

          var img = document.createElement("img");
          img.className = "brandchain-logo inst";
          img.alt = "logo" + n;

          var ext = (it && it.ext) ? String(it.ext).toLowerCase() : "";
          if (!ext) ext = "svg";

          // Prefer unit asset if unit is set; fallback to shared
          var primary = (UNIT ? logoUrlUnit(n, ext) : logoUrlShared(n, ext));
          img.src = primary;

          var all = ["svg", "png", "webp", "jpg", "jpeg"];
          var fb = [];

          if (UNIT) {
            for (var i = 0; i < all.length; i++) if (all[i] !== ext) fb.push(logoUrlUnit(n, all[i]));
            fb.push(logoUrlShared(n, ext));
            for (var j = 0; j < all.length; j++) if (all[j] !== ext) fb.push(logoUrlShared(n, all[j]));
          } else {
            for (var k = 0; k < all.length; k++) if (all[k] !== ext) fb.push(logoUrlShared(n, all[k]));
          }

          fb = fb.filter(function (x) { return !!x; });

          img.dataset.fallback = fb.join(",");
          img.onerror = function () {
            var f = (this.dataset.fallback || "").split(",");
            if (f.length && f[0]) {
              this.src = f.shift();
              this.dataset.fallback = f.join(",");
            } else {
              this.style.display = "none";
            }
          };
          host.appendChild(img);
        });
      })
      .catch(function () {
        setSlogan("TAKS");
      });
  }

  function wireLogin() {
    var u = $("__u"), r = $("__r"), p = $("__p"), go = $("__go");
    if (!u || !p || !go) return;

    // Keep role sticky for now (UI freshness / faster iteration)
    try {
      if (r) r.value = (localStorage.getItem("taks_role") || "");
    } catch (_) {}

    function submit() {
      setErr("");
      go.disabled = true;

      var role = r ? (r.value || "") : "";
      try { localStorage.setItem("taks_role", role); } catch (_) {}

      fetch(LOGIN, {
        method: "POST",
        headers: { "content-type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          username: u.value || "",
          password: p.value || "",
          role: role
        })
      })
      .then(function (r2) {
        if (!r2.ok) return r2.text().then(function (t) { throw new Error(t || ("HTTP " + r2.status)); });
        return r2.json().catch(function () { return {}; });
      })
      .then(function () {
        window.location.replace("./");
      })
      .catch(function (e) {
        var msg = "Login failed";
        try {
          if (e && e.message) {
            // If backend returned JSON, message may contain it. Try to extract detail.
            var t = String(e.message || "");
            try {
              var j = JSON.parse(t);
              if (j && j.detail) msg = "Login failed: " + j.detail;
              else msg = "Login failed: " + t;
            } catch (_) {
              msg = "Login failed: " + t;
            }
          }
        } catch (_) {}
        setErr(msg);
      })
      .finally(function () {
        go.disabled = false;
      });
    }

    go.addEventListener("click", submit);
    p.addEventListener("keydown", function (ev) { if (ev.key === "Enter") submit(); });
    u.addEventListener("keydown", function (ev) { if (ev.key === "Enter") submit(); });
    if (r) r.addEventListener("keydown", function (ev) { if (ev.key === "Enter") submit(); });

    try { u.focus(); } catch (_) {}
  }

  function ensureFragmentThenWire() {
    var host = document.getElementById("__splash");
    if (!host) return;

    if (host.querySelector && host.querySelector("#__u")) {
      renderBrandLogos();
      wireLogin();
      return;
    }

    fetch(FRAG, { cache: "no-store" })
      .then(function (r) { return r.ok ? r.text() : ""; })
      .then(function (html) {
        if (html) host.innerHTML = html;
        renderBrandLogos();
        wireLogin();
      })
      .catch(function () {
        host.innerHTML = '<div style="padding:16px;color:#fff">Failed to load splash fragment.</div>';
      });
  }

  function showSplashContainer() {
    document.body.classList.add("__splash_on");
    var host = document.getElementById("__splash");
    if (host) host.style.display = "block";
  }

  function hideSplashContainer() {
    document.body.classList.remove("__splash_on");
    var host = document.getElementById("__splash");
    if (host) host.style.display = "none";
  }

  function whoamiThen(mode) {
    fetch(WHOAMI, { cache: "no-store", credentials: "include" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) {
        var authed = !!(j && j.authenticated === true);

        if (mode === "standalone") {
          if (authed) window.location.replace("./");
          else { showSplashContainer(); ensureFragmentThenWire(); }
          return;
        }

        if (!authed) { showSplashContainer(); ensureFragmentThenWire(); }
        else { hideSplashContainer(); }
      })
      .catch(function () {
        showSplashContainer();
        ensureFragmentThenWire();
      });
  }

  var hasRoot = !!document.getElementById("root");
  var mode = hasRoot ? "overlay" : "standalone";
  whoamiThen(mode);
})();
