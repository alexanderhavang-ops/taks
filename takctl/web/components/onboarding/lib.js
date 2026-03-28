/* global React */
(function () {
  window.TaksOnboarding = window.TaksOnboarding || {};
  const lib = {};

  lib.colText = function (v) {
    if (v === null || v === undefined) return "—";
    const s = String(v);
    return s.length ? s : "—";
  };

  lib.groups = function (u) {
    const gs = (u && u.groups) || [];
    return gs.length ? gs.join(",") : "—";
  };

  lib.tail = function (act) {
    if (!act) return "—";
    const cs = act.callsign || "";
    const uid = act.uid || "";
    const t = (cs + " " + uid).trim();
    return t.length ? t : "—";
  };

  lib.deriveState = function (act) {
    if (!act) return "never";
    if (act.is_current === true) return "current";
    if (act.seen_recently === true) return "recent";
    return "stale";
  };

  lib.badgeForState = function (stateRaw) {
    const s = String(stateRaw || "").toLowerCase();
    let cls = "badge";
    if (s === "current") cls += " badge-current";
    else if (s === "recent") cls += " badge-recent";
    else if (s === "stale") cls += " badge-stale";
    else cls += " badge-never";
    return (window.h || React.createElement)(
      "span",
      { className: cls },
      lib.colText(stateRaw).toUpperCase()
    );
  };

  // ---------------------------------------------------------------------------
  // URLs + routing helpers
  // ---------------------------------------------------------------------------

  lib.userUrls = function (username) {
    const u = encodeURIComponent(String(username || ""));
    const base = `api/onboarding/users/${u}`;
    return {
      card: `${base}/card`,
      api_get: `/api/onboarding/users/${u}`,
      api_create: `/api/onboarding/users/${u}/create`,
      card_json: `/api/onboarding/users/${u}/card.json`,
    };
  };

  // Route format (hash):
  //   #onboarding/list
  //   #onboarding/create
  //   #onboarding/import
  //   #onboarding/import-jobs
  //   #onboarding/create:<username>   (may be URL-encoded as create%3Aalice)
  //
  // parseHashRoute() returns: { sub: "...", username: "" }
  lib.parseHashRoute = function () {
    const raw = String(window.location.hash || "");
    const m = raw.match(/#onboarding(?:\/([^?]+))?/i);
    let tail = (m && m[1]) ? String(m[1]) : "list";

    try { tail = decodeURIComponent(tail); } catch (e) {}

    tail = String(tail || "").trim();
    if (!tail) tail = "list";

    const parts = tail.split(":");
    const sub = String(parts[0] || "").toLowerCase();
    const username = (parts.length > 1) ? String(parts.slice(1).join(":") || "").trim() : "";

    if (sub === "create" || sub === "import" || sub === "import-jobs" || sub === "list") {
      return { sub, username };
    }
    return { sub: "list", username: "" };
  };

  lib.setHashRoute = function (sub, username) {
    const s = String(sub || "list").toLowerCase();
    const u = String(username || "").trim();

    let tail = s;
    if (s === "create" && u) tail = `create:${u}`;

    window.location.hash = `#onboarding/${encodeURIComponent(tail)}`;
  };

  lib.splitCsv = function (s) {
    const raw = String(s || "");
    return raw
      .split(",")
      .map((x) => String(x || "").trim())
      .filter((x) => x.length);
  };

  window.TaksOnboarding.lib = lib;
})();
