(function () {
  "use strict";

  var BASE = "./"; // relative to /takctl/
  var WHOAMI = BASE + "api/whoami";
  var LOGIN  = BASE + "api/login";
  var FRAG   = BASE + "splash.fragment.html";

  var BRAND  = BASE + "assets/brand.json";
  function $(id) { return document.getElementById(id); }

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

  function renderBrandLogos() {
    var host = document.getElementById("__brand_logos");
    if (!host) return;

    host.innerHTML = "";

    fetch(BRAND, { cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (b) {
        if (!b) { setSlogan("TAKS"); return; }

        // Slogan is part of brand.json contract
        setSlogan(b.slogan);

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

          var base = "./assets/logo" + n + ".";
          img.src = base + ext;

          var all = ["svg", "png", "webp", "jpg", "jpeg"];
          var fb = [];
          for (var i = 0; i < all.length; i++) {
            if (all[i] !== ext) fb.push(base + all[i]);
          }
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
    var u = $("__u"), p = $("__p"), go = $("__go");
    if (!u || !p || !go) return;

    function submit() {
      setErr("");
      go.disabled = true;

      fetch(LOGIN, {
        method: "POST",
        headers: { "content-type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ username: u.value || "", password: p.value || "" })
      })
      .then(function (r) {
        if (!r.ok) return r.text().then(function (t) { throw new Error(t || ("HTTP " + r.status)); });
        return r.json().catch(function () { return {}; });
      })
      .then(function () {
        window.location.replace("./");
      })
      .catch(function () {
        setErr("Login failed");
      })
      .finally(function () {
        go.disabled = false;
      });
    }

    go.addEventListener("click", submit);
    p.addEventListener("keydown", function (ev) { if (ev.key === "Enter") submit(); });
    u.addEventListener("keydown", function (ev) { if (ev.key === "Enter") submit(); });

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

  function whoamiThen(mode) {
    fetch(WHOAMI, { cache: "no-store", credentials: "include" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) {
        var authed = !!(j && j.authenticated === true);

        if (mode === "standalone") {
          if (authed) window.location.replace("./");
          else ensureFragmentThenWire();
          return;
        }

        if (!authed) {
          document.body.classList.add("__splash_on");
          var host = document.getElementById("__splash");
          if (host) host.style.display = "block";
          ensureFragmentThenWire();
        } else {
          document.body.classList.remove("__splash_on");
          var host2 = document.getElementById("__splash");
          if (host2) host2.style.display = "none";
        }
      })
      .catch(function () {
        if (mode === "standalone") {
          ensureFragmentThenWire();
        } else {
          document.body.classList.add("__splash_on");
          var host = document.getElementById("__splash");
          if (host) host.style.display = "block";
          ensureFragmentThenWire();
        }
      });
  }

  var hasRoot = !!document.getElementById("root");
  var mode = hasRoot ? "overlay" : "standalone";
  whoamiThen(mode);
})();
