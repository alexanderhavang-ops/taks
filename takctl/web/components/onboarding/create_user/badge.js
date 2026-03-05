/* global React */
/* ob-namebadge-v3 (KISS) */
(function () {
  var h = (window.h || React.createElement); window.h = h;

  window.TaksOnboarding = window.TaksOnboarding || {};
  window.TaksOnboarding.createUser = window.TaksOnboarding.createUser || {};

  const helpers = (window.TaksOnboarding.createUser && window.TaksOnboarding.createUser.helpers) || null;
  function needHelpers(){ if (!helpers) throw new Error("Missing create_user/helpers.js"); return helpers; }

  // KISS badge:
  // - same proportions/feel as the example badge
  // - uses team color
  // - no extra chrome, no status text
  function NameBadge({ callsign, row2, teamColor }) {
    const bg = needHelpers().teamColorToCss(teamColor) || "#c01616";

    return h("div", {
      style: {
        height: "86px",
        minWidth: "260px",
        maxWidth: "460px",
        borderRadius: "6px",
        padding: "12px 14px",
        background: bg,
        boxShadow: "0 8px 18px rgba(0,0,0,0.38)",
        border: "1px solid rgba(0,0,0,0.12)",
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        gap: "6px",
        overflow: "hidden"
      }
    },
      h("div", {
        style: {
          fontFamily: "ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif",
          fontWeight: 900,
          fontSize: "20px",
          lineHeight: 1.0,
          letterSpacing: "0.02em",
          textTransform: "uppercase",
          color: "#fff",
          whiteSpace: "nowrap",
          overflow: "hidden",
          textOverflow: "ellipsis"
        }
      }, String(callsign || "—")),

      h("div", {
        style: {
          fontFamily: "ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif",
          fontWeight: 800,
          fontSize: "12px",
          lineHeight: 1.0,
          letterSpacing: "0.06em",
          textTransform: "uppercase",
          color: "rgba(255,255,255,0.92)",
          whiteSpace: "nowrap",
          overflow: "hidden",
          textOverflow: "ellipsis"
        }
      }, String(row2 || "—"))
    );
  }

  window.TaksOnboarding.createUser.badge = { NameBadge };
})();
