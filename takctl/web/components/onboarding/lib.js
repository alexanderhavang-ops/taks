
/* global React */
(function () {
  window.TaksOnboarding = window.TaksOnboarding || {};
  const lib = {};

  // Use reported hardware/client metadata, never callsigns or account names.
  lib.deviceKind = function (d) {
    d = d || {};
    const hardware = [d.tak_device, d.tak_os].filter(Boolean).join(" ");
    const client = [d.tak_platform, d.client_platform, d.client_product].filter(Boolean).join(" ");
    if (/weartak|wear\s?os|galaxy\s*watch|pixel\s*watch|smartwatch|\bwatch\b|\bSM-R\d/i.test(hardware + " " + client)) return "watch";
    if (/wintak|webtak|martine|server|linux|windows/i.test(client)) return "computer";
    if (/atak|itak/i.test(client) || /android|iphone|\bSM-[AFGS]\d/i.test(hardware)) return "phone";
    return "unknown";
  };

  lib.deviceLabel = function (d) {
    return { phone: "Telefon", watch: "Klocka", computer: "Dator / tjänst", unknown: "Enhet" }[lib.deviceKind(d)];
  };

  lib.DeviceIcon = function (props) {
    const h = window.h || React.createElement;
    const kind = lib.deviceKind(props.device);
    const paths = {
      phone: ["M9 2h14a3 3 0 0 1 3 3v38a3 3 0 0 1-3 3H9a3 3 0 0 1-3-3V5a3 3 0 0 1 3-3Z", "M12 7h8M14 40h4"],
      watch: ["M11 13V3h10v10M11 35v10h10V35", "M8 13h16a3 3 0 0 1 3 3v16a3 3 0 0 1-3 3H8a3 3 0 0 1-3-3V16a3 3 0 0 1 3-3ZM28 21v6", "M16 18v7l5 3"],
      computer: ["M2 8h28v24H2ZM16 32v8M8 40h16"],
      unknown: ["M6 8h20v32H6ZM13 34h6"]
    };
    return h("svg", { viewBox: "0 0 32 48", width: props.size || 22, height: (props.size || 22) * 1.5, fill: "none", stroke: "currentColor", strokeWidth: 1.7, strokeLinecap: "round", strokeLinejoin: "round", role: "img", "aria-label": lib.deviceLabel(props.device), style: { flexShrink: 0 } },
      h("title", null, lib.deviceLabel(props.device)), paths[kind].map(function (p, i) { return h("path", { key: i, d: p }); }));
  };

  lib.DeviceStrip = function (props) {
    const h = window.h || React.createElement;
    const devices = Array.isArray(props.devices) ? props.devices : [];
    return h("div", { style: { display: "flex", flexWrap: "wrap", gap: "6px", marginBottom: "5px" } }, devices.map(function (d, i) {
      const online = String(d.state || "").toLowerCase() === "current";
      const title = [lib.deviceLabel(d), d.tak_device || d.tak_platform, online ? "Online" : "Inaktiv", d.client_uid].filter(Boolean).join(" · ");
      return h("span", { key: d.client_uid || i, title: title, style: { display: "inline-flex", alignItems: "center", gap: "5px", border: "1px solid rgba(255,255,255,.15)", borderRadius: "8px", padding: "4px 7px", color: online ? "#b8f5c8" : "#acb3be" } }, h(lib.DeviceIcon, { device: d, size: 14 }), lib.deviceLabel(d), h("span", { "aria-label": online ? "Online" : "Inaktiv" }, online ? "●" : "○"));
    }));
  };

  lib.colText = function (v) {
    if (v === null || v === undefined) return "—";
    const s = String(v);
    return s.length ? s : "—";
  };

  lib.groups = function (u) {
    const gs = (u && u.groups) || [];
    return gs.length ? gs.join(",") : "—";
  };

  lib.deriveState = function (activity) {
    if (!activity) return "never";
    if (activity.is_current === true) return "current";
    if (activity.seen_recently === true) return "recent";
    return "stale";
  };

  lib.bestDevice = function (userRow) {
    const ds = (userRow && Array.isArray(userRow.devices)) ? userRow.devices : [];
    if (!ds.length) return null;

    function score(d) {
      const st = String((d && d.state) || "").toLowerCase();
      if (st === "current") return 400;
      if (st === "recent") return 300;
      if (st === "stale") return 200;
      return 100;
    }

    return ds.slice().sort(function (a, b) {
      const sa = score(a), sb = score(b);
      if (sa !== sb) return sb - sa;
      return String((b && b.last_cot_time) || (b && b.last_event_time) || "")
        .localeCompare(String((a && a.last_cot_time) || (a && a.last_event_time) || ""));
    })[0] || null;
  };

  lib.userState = function (userRow) {
    const best = lib.bestDevice(userRow);
    if (best && best.state) return String(best.state || "never");
    return lib.deriveState(userRow && userRow.activity);
  };

  lib.userDeviceCount = function (userRow) {
    const ds = (userRow && Array.isArray(userRow.devices)) ? userRow.devices : [];
    return ds.length;
  };

  lib.tail = function (act) {
    if (!act) return "—";
    const cs = act.callsign || "";
    const uid = act.uid || "";
    const t = (cs + " " + uid).trim();
    return t.length ? t : "—";
  };

  lib.deviceTail = function (device) {
    if (!device) return "—";
    const act = device.activity || {};
    const ep = device.endpoint || {};
    const cs = act.callsign || device.observed_callsign || ep.callsign || "";
    const dev = device.tak_device || "";
    const uid = device.client_uid || ep.uid || act.uid || "";
    const t = [cs, dev, uid].filter(function (x) { return String(x || "").trim().length; }).join(" / ");
    return t.length ? t : "—";
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
    return {
      card: `${base}/card`,
      api_get: `/api/onboarding/users/${u}`,
      api_create: `/api/onboarding/users/${u}/create`,
      card_json: `/api/onboarding/users/${u}/card.json`,
    };
  };

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

    if (sub === "create" || sub === "detail" || sub === "import" || sub === "import-jobs" || sub === "list") {
      return { sub, username };
    }
    return { sub: "list", username: "" };
  };

  lib.setHashRoute = function (sub, username) {
    const s = String(sub || "list").toLowerCase();
    const u = String(username || "").trim();

    let tail = s;
    if ((s === "create" || s === "detail") && u) tail = `${s}:${u}`;

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
