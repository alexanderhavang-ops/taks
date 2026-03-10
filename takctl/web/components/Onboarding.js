/* global React */
(function () {
  var h = (window.h || React.createElement); window.h = h;

  const useState = React.useState;
  const useEffect = React.useEffect;

  // shared onboarding helpers
  const lib = (window.TaksOnboarding && window.TaksOnboarding.lib) || null;
  function _needLib() { if (!lib) throw new Error('Missing onboarding lib: load components/onboarding/lib.js before Onboarding.js'); return lib; }

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
    const [route, setRoute] = useState(_needLib().parseHashRoute());

    useEffect(() => {
      function onHash() { setRoute(_needLib().parseHashRoute()); }
      window.addEventListener("hashchange", onHash);
      return () => window.removeEventListener("hashchange", onHash);
    }, []);

    function nav(sub, username) {
      _needLib().setHashRoute(sub, username || "");
      setRoute({ sub: String(sub || "list"), username: String(username || "") });
    }

    const sub = (route && route.sub) ? String(route.sub) : "list";
    const username = (route && route.username) ? String(route.username) : "";

    let page = null;

    if (sub === "create") {
      page = h(window.OnboardingCreateUserPage, { routeUsername: username });
    } else if (sub === "import") {
      page = h(window.OnboardingImportUsersPage);
    } else if (sub === "import-jobs") {
      page = h(window.OnboardingImportJobsPage);
    } else {
      page = h(window.OnboardingListPage, { onEdit: (u) => nav("create", u) });
    }

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
          h("div", { className: "card-title" }, (window.t ? window.t("nav.onboarding") : "Onboarding")),
          h("div", { className: "muted", style: { marginBottom: "10px" } }, (window.t ? window.t("nav.section") : "Section")),
          h(
            "div",
            { style: { display: "flex", flexDirection: "column", gap: "8px" } },

            h(SideItem, {
              id: "list",
              cur: sub,
              label: (window.t ? window.t("nav.list") : "List"),
              onClick: () => nav("list")
            }),

            h(SideItem, {
              id: "create",
              cur: sub,
              label: (window.t ? window.t("nav.create_user") : "Create user"),
              onClick: () => nav("create")
            }),

            h(SideItem, {
              id: "import",
              cur: sub,
              label: (window.t ? window.t("nav.import_users") : "Import users file"),
              onClick: () => nav("import")
            }),

            h(SideItem, {
              id: "import-jobs",
              cur: sub,
              label: (window.t ? window.t("nav.import_jobs") : "Import jobs"),
              onClick: () => nav("import-jobs")
            })
          )
        ),

        // main pane
        h("div", { style: { flex: "1 1 auto", minWidth: "0" } }, page)
      )
    );
  }

  window.OnboardingView = OnboardingView;
})();
