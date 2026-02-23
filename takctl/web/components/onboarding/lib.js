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

  lib.userUrls = function (username) {
    const u = encodeURIComponent(String(username || ""));
    const base = `api/onboarding/users/${u}`;
    return { card: `${base}/card` };
  };

  lib.parseHashSub = function () {
    const raw = String(window.location.hash || "");
    const m = raw.match(/#onboarding(?:\/([a-z0-9_-]+))?/i);
    const sub = (m && m[1]) ? String(m[1]).toLowerCase() : "list";
    if (sub === "create" || sub === "import" || sub === "list") return sub;
    return "list";
  };

  lib.setHashSub = function (sub) {
    const s = String(sub || "list").toLowerCase();
    window.location.hash = `#onboarding/${encodeURIComponent(s)}`;
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
