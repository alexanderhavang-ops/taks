/* global React */
(function () {
  function normBattalion(x) {
    const tt = String(x || "").trim();
    const m = tt.match(/^(\d{1,3})/);
    return m ? String(m[1]) : tt;
  }

  function normFal(x) {
    return String(x || "").trim().toUpperCase();
  }

  const FAL_BN_TO = {
    "10":"VJ","11":"VL","12":"VM","13":"VN","14":"VU","15":"VO","16":"VP",
    "17":"VJ","18":"VL",
    "19":"VJ","20":"VL","21":"VM","22":"VN","23":"VU","24":"VO","25":"VP","26":"VQ","27":"VV","28":"VW","29":"VX",
    "30":"VJ","31":"VL","32":"VW","33":"VM","34":"VN","35":"VU","36":"VO","37":"VP",
    "38":"VM","39":"VN","40":"VU","41":"VO","42":"VP","43":"VQ","44":"VV","45":"VW",
    "46":"VQ","47":"VV","48":"VW","49":"VX"
  };

  const FAL_TO_BNS = (function () {
    const out = {};
    Object.entries(FAL_BN_TO).forEach(function (kv) {
      const bn = kv[0];
      const fal = kv[1];
      const k = String(fal || "").toUpperCase();
      if (!out[k]) out[k] = [];
      out[k].push(String(bn));
    });
    return out;
  })();

  function battalionMaps(policy) {
    const m = (policy && policy.maps) || {};
    return {
      b2f: (m && m.battalion_to_fal) || {},
      f2b: (m && m.fal_to_battalion) || {}
    };
  }

  function battalionToFal(policy, bnRaw) {
    const bn = normBattalion(bnRaw);
    const maps = battalionMaps(policy);
    if (maps.b2f && maps.b2f[bn]) return String(maps.b2f[bn]);
    return FAL_BN_TO[bn] ? String(FAL_BN_TO[bn]) : "";
  }

  function falToBattalion(policy, falRaw) {
    const fal = normFal(falRaw);
    const maps = battalionMaps(policy);
    if (maps.f2b && maps.f2b[fal]) return String(maps.f2b[fal]);
    const cands = FAL_TO_BNS[fal] || [];
    return (cands.length === 1) ? String(cands[0]) : "";
  }

  function setIdentWithLogic(prev, k, v, policy) {
    const kk = String(k || "");
    const vv = (v == null) ? "" : String(v);

    if (kk === "battalion") {
      const batt = normBattalion(vv);
      const mappedFal = battalionToFal(policy, batt);
      const out = Object.assign({}, prev, { battalion: batt });
      if (mappedFal) out.battalion_fal = mappedFal;
      return out;
    }

    if (kk === "battalion_fal") {
      const fal = normFal(vv);
      const mappedBatt = falToBattalion(policy, fal);
      const out = Object.assign({}, prev, { battalion_fal: fal });
      if (mappedBatt) out.battalion = mappedBatt;
      return out;
    }

    if (kk === "n") {
      const nval = String(vv || "").trim();
      const out = Object.assign({}, prev, { n: nval });
      const curRole = String(out.atak_role_type || "").trim();
      if ((nval === "1" || nval === "2") && (!curRole || curRole.toLowerCase() === "soldier")) {
        out.atak_role_type = "Team Lead";
      }
      return out;
    }

    return Object.assign({}, prev, { [kk]: vv });
  }

  function deriveKey(policyId, ctx) {
    const o = { policy_id: String(policyId || "") };
    ["battalion", "battalion_fal", "company", "platoon", "group", "n", "team", "callsign_policy"].forEach(function (k) {
      o[k] = String((ctx && ctx[k]) || "");
    });
    return JSON.stringify(o);
  }

  window.TaksOnboarding = window.TaksOnboarding || {};
  window.TaksOnboarding.createUser = window.TaksOnboarding.createUser || {};
  window.TaksOnboarding.createUser.identityLogic = {
    normBattalion: normBattalion,
    normFal: normFal,
    battalionMaps: battalionMaps,
    FAL_BN_TO: FAL_BN_TO,
    battalionToFal: battalionToFal,
    falToBattalion: falToBattalion,
    setIdentWithLogic: setIdentWithLogic,
    deriveKey: deriveKey
  };
})();
