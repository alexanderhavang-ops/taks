function TabButton({ id, tab, setTab, label }) {
  const active = (tab === id);
  return h("button", {
    className: active ? "tab tab-active" : "tab",
    onClick: () => setTab(id),
    type: "button",
  }, label);
}

/**
 * Try loading an image with fallback extensions.
 * Renders the first that loads, hides itself if none do.
 */
function ImgTry({ base, exts, alt, className, title }) {
  let idx = 0;

  function onError(e) {
    idx += 1;
    if (idx < exts.length) {
      e.target.src = base + exts[idx];
    } else {
      try { e.target.style.display = "none"; } catch (_) {}
    }
  }

  return h("img", {
    src: base + exts[0],
    alt: alt || "",
    title: title || "",
    className: className || "",
    onError,
  });
}

function BrandBlock({ brand }) {
  const slogan = (brand && brand.slogan) || "";

  return h("div", { className: "brandblock" },

    h("div", { className: "brand-left" },
      h("div", { className: "brand-product" },
        h("div", { className: "brand-text" },
          h("div", { className: "brand-title" }, (brand && brand.title) ? brand.title : "takctl"),
          slogan ? h("div", { className: "brand-slogan" }, slogan) : null
        )
      )
    ),

    // Instance-owned logos (runtime state)
    h("div", { className: "brand-right" },
      h(ImgTry, {
        base: "./assets/logo1",
        // Prefer SVG first (if present), then PNG
        exts: [".svg", ".png"],
        alt: "Instance logo 1",
        className: "logo logo-inst",
        title: "Instance logo 1"
      }),
      h(ImgTry, {
        base: "./assets/logo2",
        exts: [".svg", ".png"],
        alt: "Instance logo 2",
        className: "logo logo-inst",
        title: "Instance logo 2"
      }),
      h(ImgTry, {
        base: "./assets/logo3",
        exts: [".svg", ".png"],
        alt: "Instance logo 3",
        className: "logo logo-inst",
        title: "Instance logo 3"
      }),
      h(ImgTry, {
        base: "./assets/logo4",
        exts: [".svg", ".png"],
        alt: "Instance logo 4",
        className: "logo logo-inst",
        title: "Instance logo 4"
      })
    )
  );
}

function Layout({ tab, setTab, health, brand, children }) {
  return h("div", { className: "app" },

    h("div", { className: "topbar" },
      h(BrandBlock, { brand }),

      h("div", { className: "tabs" },
        h(TabButton, { id: "users", tab, setTab, label: "Users" }),
        h(TabButton, { id: "clients", tab, setTab, label: "Clients" }),
        h(TabButton, { id: "onboarding", tab, setTab, label: "Onboarding" }),
        h(TabButton, { id: "crl", tab, setTab, label: "CRL" }),
        h(TabButton, { id: "certs", tab, setTab, label: "Certs" })
      ),

      h("div", { className: "spacer" }),

      h("div", { className: "health" },
        (brand && (brand.apply_ts_utc || brand.apply_ts || brand.applied_ts_utc))
          ? h("span", { className: "muted", style: { marginRight: "10px" } }, "Applied: " + (brand.apply_ts_utc || brand.apply_ts || brand.applied_ts_utc))
          : null,
        h("span", { className: "muted", style: { marginRight: "8px" } }, "api/health"),
        h(HealthBadge, { health })
      )
    ),

    h("div", { className: "body" },
      h("div", { className: "main" }, children)
    )
  );
}

