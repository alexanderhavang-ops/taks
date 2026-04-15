/* global React */
(function () {
  function runDeriveEffect(props) {
    const policyId = props.policyId;
    const ctxForDerive = props.ctxForDerive;
    const norm = props.norm;
    const effectiveCallsignPolicy = props.effectiveCallsignPolicy;
    const callsignPolicyOverride = props.callsignPolicyOverride;
    const callsignPolicyDefault = props.callsignPolicyDefault;
    const deriveKey = props.deriveKey;

    const setDerived = props.setDerived;
    const setDerivedErr = props.setDerivedErr;
    const setDeriveBusy = props.setDeriveBusy;
    const setCallsignEdit = props.setCallsignEdit;

    const deriveAbortRef = props.deriveAbortRef;
    const deriveLastKeyRef = props.deriveLastKeyRef;
    const callsignDirtyRef = props.callsignDirtyRef;

    const unit = norm(ctxForDerive && ctxForDerive.unit);
    const battalion = norm(ctxForDerive && ctxForDerive.battalion);
    const battalion_fal = norm(ctxForDerive && ctxForDerive.battalion_fal);
    const company = norm(ctxForDerive && ctxForDerive.company);
    const platoon = norm(ctxForDerive && ctxForDerive.platoon);
    const group = norm(ctxForDerive && ctxForDerive.group);
    const n = norm(ctxForDerive && ctxForDerive.n);
    const team = norm(ctxForDerive && ctxForDerive.team);

    const isGenericPolicy = String(policyId || "").trim().toLowerCase() !== "hemvarnet";
    const effectivePolicy = isGenericPolicy ? "GENERIC" : effectiveCallsignPolicy(callsignPolicyOverride, callsignPolicyDefault);

    const hasBasis = isGenericPolicy
      ? !!unit
      : !!(battalion_fal || battalion);

    const hierOk = isGenericPolicy || (
      (!company && !platoon && !group) ||
      ( company && !platoon && !group) ||
      ( company &&  platoon && !group) ||
      ( company &&  platoon &&  group)
    );

    if (!policyId || !n || !hasBasis || !hierOk) {
      setDerived(null);
      setDerivedErr("");
      setDeriveBusy(false);
      deriveLastKeyRef.current = "";
      if (deriveAbortRef.current) { try { deriveAbortRef.current.abort(); } catch (e) {} }
      deriveAbortRef.current = null;
      return;
    }

    const key = deriveKey(policyId, {
      unit: unit,
      battalion: battalion,
      battalion_fal: battalion_fal,
      company: company,
      platoon: platoon,
      group: group,
      n: n,
      team: team,
      callsign_policy: effectivePolicy
    });
    if (key === deriveLastKeyRef.current) return;

    const timer = setTimeout(function () {
      (async function () {
        deriveLastKeyRef.current = key;

        if (deriveAbortRef.current) { try { deriveAbortRef.current.abort(); } catch (e) {} }
        const ac = new AbortController();
        deriveAbortRef.current = ac;

        setDeriveBusy(true);
        setDerivedErr("");
        try {
          const resp = await fetch("/api/onboarding/derive", {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({
              policy_id: String(policyId),
              ctx: {
                unit: unit,
                battalion: battalion,
                battalion_fal: battalion_fal,
                company: company,
                platoon: platoon,
                group: group,
                n: n,
                team: team,
                callsign_policy: effectivePolicy
              }
            }),
            signal: ac.signal,
          });
          const data = await resp.json().catch(function () { return {}; });
          if (!resp.ok) throw new Error(data.error || data.detail || ("HTTP " + resp.status));

          setDerived(data || null);

          if (!callsignDirtyRef.current) {
            const di = (data && data.identity) || {};
            setCallsignEdit(di.callsign ? String(di.callsign) : "");
          }
        } catch (e) {
          if (e && e.name === "AbortError") return;
          setDerived(null);
          setDerivedErr(String((e && e.message) || e || "derive failed"));
        } finally {
          setDeriveBusy(false);
        }
      })();
    }, 450);

    return function cleanup() {
      clearTimeout(timer);
    };
  }

  window.TaksOnboarding = window.TaksOnboarding || {};
  window.TaksOnboarding.createUser = window.TaksOnboarding.createUser || {};
  window.TaksOnboarding.createUser.derive = {
    runDeriveEffect: runDeriveEffect
  };
})();
