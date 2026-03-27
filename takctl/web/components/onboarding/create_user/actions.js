/* global React */
(function () {
  function buildCreateBody(props) {
    const norm = props.norm;
    const splitCsv = props.splitCsv;
    const effectiveCallsignPolicy = props.effectiveCallsignPolicy;
    const labelForKey = props.labelForKey;

    const username = props.username;
    const policyId = props.policyId;
    const policy = props.policy;
    const ident = props.ident;
    const callsignEdit = props.callsignEdit;
    const emailAddr = props.emailAddr;
    const password = props.password;
    const admin = props.admin;
    const groups = props.groups;
    const ttlSec = props.ttlSec;
    const revealPassword = props.revealPassword;

    const callsignPolicyOverride = props.callsignPolicyOverride;
    const callsignPolicyDefault = props.callsignPolicyDefault;

    const artifactAtakAutoEnroll = props.artifactAtakAutoEnroll;
    const artifactAtakSoftCertNoPassword = props.artifactAtakSoftCertNoPassword;
    const artifactAtakSoftCertWithPassword = props.artifactAtakSoftCertWithPassword;
    const artifactItakSoftCertNoPassword = props.artifactItakSoftCertNoPassword;
    const artifactItakSoftCertWithPassword = props.artifactItakSoftCertWithPassword;

    const u = norm(username);
    if (!u) {
      return { ok: false, error: "Username required." };
    }
    if (!policyId) {
      return { ok: false, error: "Policy required." };
    }

    const effectivePolicy = effectiveCallsignPolicy(callsignPolicyOverride, callsignPolicyDefault);

    const ctx = { policy_id: String(policyId) };
    const identFields = (policy && policy.identity_fields) || [];
    for (const f of identFields) {
      const k = String(f.key || "");
      if (!k) continue;
      const v = ident[k];
      if (f.required && (v === undefined || v === null || String(v).trim() === "")) {
        return { ok: false, error: "Missing required field: " + String(labelForKey(k, f.label || k)) };
      }
      ctx[k] = v;
    }

    ctx.callsign_policy = effectivePolicy;
    if (norm(callsignEdit)) ctx.callsign = String(callsignEdit);
    if (norm(emailAddr)) ctx.email = String(emailAddr);

    const artifacts_requested = {
      atak_auto_enroll: !!artifactAtakAutoEnroll,
      atak_soft_cert_no_password: !!artifactAtakSoftCertNoPassword,
      atak_soft_cert_with_password: !!artifactAtakSoftCertWithPassword,
      itak_soft_cert_no_password: !!artifactItakSoftCertNoPassword,
      itak_soft_cert_with_password: !!artifactItakSoftCertWithPassword,
    };

    const body = {
      password: norm(password) || null,
      admin: !!admin,
      groups_rw: splitCsv(groups.groups_rw),
      groups_in: splitCsv(groups.groups_in),
      groups_out: splitCsv(groups.groups_out),
      ctx: ctx,
      artifacts_requested: artifacts_requested,
      paths: {
        B: !!(
          artifactAtakSoftCertNoPassword ||
          artifactAtakSoftCertWithPassword ||
          artifactItakSoftCertNoPassword ||
          artifactItakSoftCertWithPassword
        ),
        itak: !!(
          artifactItakSoftCertNoPassword ||
          artifactItakSoftCertWithPassword
        ),
        wintak: !!(
          artifactAtakSoftCertNoPassword ||
          artifactAtakSoftCertWithPassword
        ),
      },
      endpoints: {},
      ttl_sec: Number(ttlSec || 600),
      reveal_password: !!revealPassword,
    };

    return { ok: true, username: u, body: body };
  }

  async function doCreate(props) {
    props.setErr("");
    props.setResult(null);
    props.setEmailErr("");
    props.setEmailResult(null);

    const built = buildCreateBody(props);
    if (!built.ok) {
      props.setErr(String(built.error || "Failed"));
      return;
    }

    props.setBusy(true);
    try {
      const resp = await fetch("api/onboarding/users/" + encodeURIComponent(built.username) + "/create", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(built.body),
      });
      const j = await resp.json().catch(function () { return {}; });
      if (!resp.ok) throw new Error(j.detail || ("HTTP " + resp.status));
      props.setResult(j || {});
    } catch (e) {
      props.setErr(String((e && e.message) || e || "Failed"));
    } finally {
      props.setBusy(false);
    }
  }

  async function doEmailLink(props) {
    props.setEmailErr("");
    props.setEmailResult(null);

    const u = props.norm(props.username);
    const em = props.norm(props.emailAddr);
    if (!u) { props.setEmailErr("Username required."); return; }
    if (!em) { props.setEmailErr("Email required."); return; }

    props.setEmailBusy(true);
    try {
      const resp = await fetch("api/onboarding/users/" + encodeURIComponent(u) + "/email-link", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          email: em,
          ttl_sec: Number(props.ttlSec || 600),
          reveal_password: !!props.revealPassword,
        }),
      });
      const j = await resp.json().catch(function () { return {}; });
      if (!resp.ok) throw new Error(j.detail || ("HTTP " + resp.status));
      props.setEmailResult(j || {});
      if (j && j.card_url) {
        props.setResult(function (prev) {
          return Object.assign({}, prev || {}, { card_url: j.card_url, card_token: j.card_token });
        });
      }
    } catch (e) {
      props.setEmailErr(String((e && e.message) || e || "Failed"));
    } finally {
      props.setEmailBusy(false);
    }
  }

  window.TaksOnboarding = window.TaksOnboarding || {};
  window.TaksOnboarding.createUser = window.TaksOnboarding.createUser || {};
  window.TaksOnboarding.createUser.actions = {
    buildCreateBody: buildCreateBody,
    doCreate: doCreate,
    doEmailLink: doEmailLink
  };
})();
