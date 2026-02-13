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

function ImgTryList({ srcs, alt, className, title }) {
  let idx = 0;

  function onError(e) {
    idx += 1;
    if (srcs && idx < srcs.length) {
      e.target.src = srcs[idx];
    } else {
      try { e.target.style.display = "none"; } catch (_) {}
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

      // logo1/logo2: real SVG uploads exist -> SVG first is fine
      h(ImgTryList, {
        srcs: ["./assets/topbar/logo1.png", "./assets/logo1.svg", "./assets/logo1.png", "./assets/logo1.webp", "./assets/logo1.jpg", "./assets/logo1.jpeg"],
        alt: "Instance logo 1",
        className: "logo logo-inst",
        title: "Instance logo 1"
      }),

      h(ImgTryList, {
        srcs: ["./assets/topbar/logo2.png", "./assets/logo2.svg", "./assets/logo2.png", "./assets/logo2.webp", "./assets/logo2.jpg", "./assets/logo2.jpeg"],
        alt: "Instance logo 2",
        className: "logo logo-inst",
        title: "Instance logo 2"
      }),

      // logo3/logo4: may be raster + SVG wrapper; raster-first avoids blank wrapper in <img>
      h(ImgTryList, {
        srcs: ["./assets/topbar/logo3.png", "./assets/logo3.svg", "./assets/logo3.png", "./assets/logo3.webp", "./assets/logo3.jpg", "./assets/logo3.jpeg"],
        alt: "Instance logo 3",
        className: "logo logo-inst",
        title: "Instance logo 3"
      }),

      h(ImgTryList, {
        srcs: ["./assets/topbar/logo4.png", "./assets/logo4.svg", "./assets/logo4.png", "./assets/logo4.webp", "./assets/logo4.jpg", "./assets/logo4.jpeg"],
        alt: "Instance logo 4",
        className: "logo logo-inst",
        title: "Instance logo 4"
      })
    )
  );
}

function Layout(
{ tab, setTab, health, brand, children }) {
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

