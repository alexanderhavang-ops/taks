/* global React */
(function () {
  var h = (window.h || React.createElement); window.h = h;

  window.TaksOnboarding = window.TaksOnboarding || {};
  window.TaksOnboarding.createUser = window.TaksOnboarding.createUser || {};

  const helpers = (window.TaksOnboarding.createUser && window.TaksOnboarding.createUser.helpers) || null;
  function needHelpers(){ if (!helpers) throw new Error("Missing create_user/helpers.js"); return helpers; }

  function NameBadge({ callsign, row2, teamColor, statusText }) {
    const bg = needHelpers().teamColorToCss(teamColor) || "#1f2937";

    // Use the unit logo from assets (your runtime symlink points it at logo3.svg)
    // Make it white via CSS filter.
    const logoUrl = "/assets/unit-current.svg";

    return h("div", { className: "box", style: { marginBottom: "12px", padding: "14px" } },
      h("div", {
        style: {
          display: "flex",
          alignItems: "center",
          gap: "16px",
          borderRadius: "12px",
          padding: "14px 16px",
          background: bg,
          border: "1px solid rgba(255,255,255,0.08)",
          boxShadow: "0 14px 40px rgba(0,0,0,.25)"
        }
      },
        h("img", {
          src: logoUrl,
          alt: "unit",
          style: {
            width: "34px",
            height: "34px",
            objectFit: "contain",
            // force white
            filter: "brightness(0) invert(1)",
            opacity: 0.95,
            flex: "0 0 auto"
          }
        }),

        // TWO ROWS ONLY (match the sample badge feel)
        h("div", { style: { minWidth: 0, flex: "1 1 auto" } },
          h("div", {
            style: {
              fontWeight: 900,
              fontSize: "22px",
              lineHeight: 1.05,
              letterSpacing: ".02em",
              textTransform: "uppercase",
              color: "#fff"
            }
          }, String(callsign || "—")),

          h("div", {
            style: {
              marginTop: "4px",
              fontWeight: 700,
              fontSize: "12px",
              letterSpacing: ".04em",
              textTransform: "uppercase",
              color: "rgba(255,255,255,.85)"
            }
          }, String(row2 || "—"))
        ),

        h("div", { className: "muted", style: { fontSize: "12px", textAlign: "right" } },
          String(statusText || "—")
        )
      )
    );
  }

  window.TaksOnboarding.createUser.badge = { NameBadge };
})();
