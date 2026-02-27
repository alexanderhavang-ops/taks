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

  // Shell only: pages are loaded from components/onboarding/*.js

  // ---------------------------------------------------------------------------
  // Root: left menu + subpage routing
  // ---------------------------------------------------------------------------
  function SideItem({ id, cur, label, onClick }) {
    const on = (String(cur) === String(id));
    const cls = "btn";
    return h(
      "button",
      {
        className: cls,
        onClick,
        style: {
          width: "100%",
          justifyContent: "flex-start",
          opacity: on ? 1 : 0.85,
          borderColor: on ? "#3a3a3a" : undefined,
        },
      },
      label
    );
  }

  function OnboardingView() {
    const [sub, setSub] = useState(_parseHashSub());

    useEffect(() => {
      function onHash() { setSub(_parseHashSub()); }
      window.addEventListener("hashchange", onHash);
      return () => window.removeEventListener("hashchange", onHash);
    }, []);

    function nav(to) {
      setSub(to);
      _setHashSub(to);
    }

    let page = null;
    if (sub === "create") page = h(window.OnboardingCreateUserPage);
    else if (sub === "import") page = h(window.OnboardingImportUsersPage);
    else page = h(window.OnboardingListPage);

    return h(
      "div",
      { className: "card" },
      h(
        "div",
        { style: { display: "flex", gap: "14px", alignItems: "stretch" } },

        // left menu
        h(
          "div",
          { style: { width: "220px", flex: "0 0 auto" } },
          h("div", { className: "card-title" }, "Onboarding"),
          h("div", { className: "muted", style: { marginBottom: "10px" } }, "Section"),
          h(
            "div",
            { style: { display: "flex", flexDirection: "column", gap: "8px" } },
            h(SideItem, { id: "list", cur: sub, label: "List", onClick: () => nav("list") }),
            h(SideItem, { id: "create", cur: sub, label: "Create user", onClick: () => nav("create") }),
            h(SideItem, { id: "import", cur: sub, label: "Import users file", onClick: () => nav("import") })
          )
        ),

        // main pane
        h("div", { style: { flex: "1 1 auto", minWidth: "0" } }, page)
      )
    );
  }

  window.OnboardingView = OnboardingView;
})();
