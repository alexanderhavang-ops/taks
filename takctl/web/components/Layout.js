function TabButton({ id, tab, setTab, label }) {
  const active = (tab === id);
  return h("button", {
    className: active ? "tab tab-active" : "tab",
    onClick: () => setTab(id),
    type: "button",
  }, label);
}

/**
 * Try loading an image with fallback list.
 * Renders first that loads; hides itself if none do.
 */
function ImgTryList({ srcs, alt, className, title }) {
  let idx = 0;

  function onError(e) {
    idx += 1;
    if (srcs && idx < srcs.length) {
      e.target.src = srcs[idx];
    } else {
      try { e.target.style.display = "none"; } catch (_) {}
      try { if (e.target && e.target.parentElement) e.target.parentElement.style.display = "none"; } catch (_) {}
    }
  }

  return h("img", {
    src: (srcs && srcs.length ? srcs[0] : ""),
    alt: alt || "",
    title: title || "",
    className: className || "",
    onError,
  });
}

function BrandLeft({ brand }) {
  const slogan = (brand && brand.slogan) || "";

  // Git-owned product logo (always present)
  // Prefer horizontal PNG first; SVG is fallback.
  const taksLogoSrcs = [
    "./assets/taks-logo.png",
    "./assets/taks-logo.svg",
  ];

  return h("div", { className: "brand-left" },

    h(ImgTryList, {
      srcs: taksLogoSrcs,
      alt: "TAKS",
      className: "logo logo-product",
      title: "TAKS"
    }),

    h("div", { className: "brand-product" },
      h("div", { className: "brand-text" },
        h("div", { className: "brand-title" }, (brand && brand.title) ? brand.title : "takctl"),
        slogan ? h("div", { className: "brand-slogan" }, slogan) : null
      )
    )
  );
}

function TakServerLinks() {
  const host = (window && window.location && window.location.hostname) ? window.location.hostname : "";
  const martiUrl = host ? ("https://" + host + ":8446/Marti/") : "https://localhost:8446/Marti/";
  const webtakUrl = host ? ("https://" + host + ":8446/webtak/") : "https://localhost:8446/webtak/";

  const linkProps = {
    target: "_blank",
    rel: "noopener noreferrer",
    className: "toplink",
  };

  return h("div", { className: "taklinks" },
    h("a", { href: martiUrl, title: "Open Marti on :8446", ...linkProps }, "Marti"),
    h("span", { className: "muted", style: { margin: "0 8px" } }, "·"),
    h("a", { href: webtakUrl, title: "Open WebTak on :8446", ...linkProps }, "WebTak")
  );
}

function LangAndSessionControls() {
  const current = String(window.currentLang || window.TAKS_RUNTIME_LANGUAGE || "sv");

  function L(sv, en) { return (current === "en") ? String(en) : String(sv); }

  function logout() {
    const next = encodeURIComponent("/");
    window.location.href = "/logout?next=" + next;
  }

  return h("div", { style: { display: "flex", gap: "10px", alignItems: "center" } },
    h("button", {
      type: "button",
      className: "btn",
      onClick: logout,
      title: L("Logga ut", "Logout")
    }, L("Logga ut", "Logout"))
  );
}

function Layout({ tab, setTab, health, brand, children }) {
  const current = String(window.currentLang || window.TAKS_RUNTIME_LANGUAGE || "sv");

  function L(sv, en) {
    return (current === "en") ? String(en) : String(sv);
  }

  // Prefer the square-derived icon first (unit-current.png),
  // then fall back to svg and other extensions.
  const unitLogoSrcs = [
    "./assets/unit-current.png",
    "./assets/unit-current.svg",
    "./assets/unit-current.webp",
    "./assets/unit-current.jpg",
    "./assets/unit-current.jpeg",
  ];

  return h("div", { className: "app" },

    h("div", { className: "topbar" },

      h("div", { className: "brandblock" },
        h(BrandLeft, { brand })
      ),

      h("div", { className: "tabs" },

        h(TabButton, { id: "onboarding", tab, setTab, label: "Onboarding" }),

        h(TabButton, { id: "llm", tab, setTab, label: "AI" }),

        h(TabButton, { id: "usage", tab, setTab, label: L("Användning", "Usage") }),

        h(TabButton, { id: "martine", tab, setTab, label: "Martine" }),

        h(TabButton, { id: "replay", tab, setTab, label: L("Spel", "Replay") }),

        h(TabButton, { id: "config", tab, setTab, label: L("Konfig", "Config") })
      ),

      h("div", { className: "spacer" }),

      h(TakServerLinks),

      // Language + Logout + Session cluster (top-right)
      h("div", { className: "session" },
        h(LangAndSessionControls),
        h(ImgTryList, {
          srcs: unitLogoSrcs,
          alt: "Unit logo",
          className: "logo logo-inst logo-inst-single",
          title: "Unit logo (highest uploaded)"
        }),
        h(HealthBadge, { health })
      )
    ),

    h("div", { className: "body" },
      h("div", { className: "main" }, children)
    )
  );
}
