/* global React */
(function () {
  var h = (window.h || React.createElement); window.h = h;

  const useState = React.useState;
  const useEffect = React.useEffect;

  const t = (window.t && typeof window.t === "function") ? window.t : (k) => String(k || "");
  const lib = (window.TaksOnboarding && window.TaksOnboarding.lib) || null;
  function _needLib() { if (!lib) throw new Error("Missing onboarding lib"); return lib; }
  function _colText(v){ return _needLib().colText(v); }

  function KV(props) {
    return h("div", {
      style: {
        display: "grid",
        gridTemplateColumns: "180px minmax(0,1fr)",
        gap: "10px",
        marginBottom: "8px",
        alignItems: "start"
      }
    },
      h("div", { className: "muted", style: { fontWeight: 700 } }, props.k),
      h("div", null, props.children)
    );
  }

  function Box(props) {
    return h("div", {
      className: "box",
      style: { marginBottom: "12px" }
    }, props.children);
  }

  function jsonPre(v) {
    return h("pre", {
      style: {
        margin: 0,
        whiteSpace: "pre-wrap",
        overflowWrap: "anywhere",
        wordBreak: "break-word",
        fontSize: "12px",
        lineHeight: "16px"
      }
    }, JSON.stringify(v, null, 2));
  }

  function OnboardingUserDetailPage(props) {
    const routeUsername = (props && props.routeUsername) ? String(props.routeUsername) : "";
    const [busy, setBusy] = useState(true);
    const [err, setErr] = useState("");
    const [userData, setUserData] = useState(null);
    const [cardData, setCardData] = useState(null);

    useEffect(() => {
      const u = String(routeUsername || "").trim();
      if (!u) {
        setErr("Missing username");
        setBusy(false);
        return;
      }

      let alive = true;
      (async () => {
        setBusy(true);
        setErr("");
        try {
          const urls = _needLib().userUrls(u);

          const [rUser, rCard] = await Promise.all([
            fetch(urls.api_get),
            fetch(urls.card_json)
          ]);

          const jUser = await rUser.json().catch(() => ({}));
          const jCard = await rCard.json().catch(() => ({}));

          if (!rUser.ok) throw new Error(jUser.detail || ("HTTP " + rUser.status));
          if (!rCard.ok) throw new Error(jCard.detail || ("HTTP " + rCard.status));

          if (!alive) return;
          setUserData(jUser || {});
          setCardData(jCard || {});
        } catch (e) {
          if (!alive) return;
          setErr(String((e && e.message) || e || "Failed"));
        } finally {
          if (alive) setBusy(false);
        }
      })();

      return () => { alive = false; };
    }, [routeUsername]);

    if (busy) {
      return h("div", null,
        h("div", { className: "card-title" }, "Onboarding — Detalj"),
        h("div", { className: "muted" }, "Laddar…")
      );
    }

    if (err) {
      return h("div", null,
        h("div", { className: "card-title" }, "Onboarding — Detalj"),
        h("div", { className: "note" }, "ERR: ", err)
      );
    }

    const user = (userData && userData.user) || {};
    const ti = (userData && userData.taks_identity) || {};
    const sel = (userData && userData.selection) || {};
    const ctx = (ti && ti.ctx) || {};
    const ident = (ti && ti.identity) || {};
    const card = (cardData && cardData.card) || {};
    const meta = (cardData && cardData.meta) || {};
    const lifecycle = (card && card.lifecycle) || {};
    const activity = (card && card.activity) || {};
    const header = (card && card.header) || {};
    const marti = (card && card.marti) || {};

    const username = _colText(user.username || routeUsername);
    const groups = Array.isArray(user.groups) ? user.groups.join(", ") : "—";
    const cardUrl = (card && card.card_url) || "";

    return h("div", null,
      h("div", { className: "card-title" }, "Onboarding — Detalj"),

      h("div", {
        style: { display: "flex", gap: "8px", flexWrap: "wrap", marginBottom: "12px" }
      },
        h("button", {
          className: "btn",
          type: "button",
          onClick: function () {
            try {
              const lib = window.TaksOnboarding && window.TaksOnboarding.lib;
              if (lib && typeof lib.setHashRoute === "function") lib.setHashRoute("create", String(routeUsername || ""));
            } catch (e) {}
          }
        }, t("btn.edit")),
        cardUrl ? h("a", {
          className: "btn",
          href: cardUrl,
          target: "_blank",
          rel: "noopener noreferrer"
        }, t("btn.card")) : null
      ),

      h(Box, null,
        h("div", { className: "card-title", style: { fontSize: "16px", marginBottom: "10px" } }, "Identitet"),
        h(KV, { k: "Användarnamn" }, _colText(username)),
        h(KV, { k: "Grupper" }, _colText(groups)),
        h(KV, { k: "Callsign" }, _colText(ctx.callsign || header.callsign || ident.callsign)),
        h(KV, { k: "Team" }, _colText(ctx.team || header.team || ident.team)),
        h(KV, { k: "ATAK-roll" }, _colText(ctx.atak_role_type || ident.atak_role_type)),
        h(KV, { k: "E-post" }, _colText(ctx.email)),
        h(KV, { k: "Policy" }, _colText(ctx.policy_id)),
        h(KV, { k: "Lösenord känt" }, _colText(ti.password_known ? "Ja" : "Nej"))
      ),

      h(Box, null,
        h("div", { className: "card-title", style: { fontSize: "16px", marginBottom: "10px" } }, "Status"),
        h(KV, { k: "Onboarding-status" }, _colText(card.onboarding_status)),
        h(KV, { k: "State" }, _colText(activity.state || "")),
        h(KV, { k: "Senast sedd" }, _colText(activity.age_human)),
        h(KV, { k: "UID" }, _colText(activity.uid)),
        h(KV, { k: "Marti-grupper" }, _colText(Array.isArray(marti.groups) ? marti.groups.join(", ") : "—")),
        h(KV, { k: "DB" }, _colText(typeof meta.db_attached === "boolean" ? (meta.db_attached ? "attached" : "none") : "?"))
      ),

      h(Box, null,
        h("div", { className: "card-title", style: { fontSize: "16px", marginBottom: "10px" } }, "Livscykel"),
        jsonPre(lifecycle)
      ),

      h(Box, null,
        h("div", { className: "card-title", style: { fontSize: "16px", marginBottom: "10px" } }, "Selection"),
        jsonPre(sel)
      ),

      h(Box, null,
        h("div", { className: "card-title", style: { fontSize: "16px", marginBottom: "10px" } }, "Kortdata"),
        jsonPre(card)
      )
    );
  }

  window.OnboardingUserDetailPage = OnboardingUserDetailPage;
})();
