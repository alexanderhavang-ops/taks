/* global React */
(function () {
  window.TaksOnboarding = window.TaksOnboarding || {};
  window.TaksOnboarding.createUser = window.TaksOnboarding.createUser || {};

  const LP = { "data-lpignore": "true", autoComplete: "off" };

  function norm(s){ return String(s || "").trim(); }

  function teamColorToCss(c) {
    const x = String(c || "").trim().toLowerCase();
    if (!x) return "";
    if (x === "white") return "#2f343a";
    if (x === "black") return "#111317";
    if (x === "red") return "#7a1f24";
    if (x === "blue") return "#173a6a";
    if (x === "green") return "#1c5a3b";
    if (x === "yellow") return "#6a5a12";
    if (x === "orange") return "#7a4318";
    if (x === "purple") return "#4c2a6a";
    if (x.startsWith("#") && (x.length === 4 || x.length === 7)) return x;
    return "#26303a";
  }

  window.TaksOnboarding.createUser.helpers = { LP, norm, teamColorToCss };
})();
