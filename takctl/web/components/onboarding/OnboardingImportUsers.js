/* global React */
(function () {
  var h = (window.h || React.createElement); window.h = h;

  const useState = React.useState;
  const useMemo = React.useMemo;
  const useEffect = React.useEffect;

  // shared onboarding helpers
  const lib = (window.TaksOnboarding && window.TaksOnboarding.lib) || null;
  function _needLib() { if (!lib) throw new Error('Missing onboarding lib: load components/onboarding/lib.js before Onboarding.js'); return lib; }
  function _colText(v){ return _needLib().colText(v); }
  function _groups(u){ return _needLib().groups(u); }
  function _tail(act){ return _needLib().tail(act); }
  function _deriveState(act){ return _needLib().deriveState(act); }
  function _badgeForState(stateRaw){ return _needLib().badgeForState(stateRaw); }
  function _userUrls(username){ return _needLib().userUrls(username); }
  function _parseHashSub(){ return _needLib().parseHashSub(); }
  function _setHashSub(sub){ return _needLib().setHashSub(sub); }
  function _splitCsv(s){ return _needLib().splitCsv(s); }

  // ---------------------------------------------------------------------------
  // Import users (placeholder)
  // ---------------------------------------------------------------------------
  function OnboardingImportUsersPage() {
    return h(
      "div",
      null,
      h("div", { className: "card-title" }, "Onboarding — Import users file"),
      h(
        "div",
        { className: "muted" },
        "Next step: upload Excel/CSV → preview grid → confirm → bulk create."
      ),
      h(
        "div",
        { className: "note", style: { marginTop: "10px" } },
        "We’ll define the exact column grammar from policy/ctx once single-user is solid."
      )
    );
  }

  window.OnboardingImportUsersPage = OnboardingImportUsersPage;
})();
