/* global React */
(function () {
  var h = (window.h || React.createElement); window.h = h;

  const useState = React.useState;
  const useEffect = React.useEffect;

  const t = (window.t && typeof window.t === "function") ? window.t : (k) => String(k || "");
  const lib = (window.TaksOnboarding && window.TaksOnboarding.lib) || null;
  function _needLib() { if (!lib) throw new Error("Missing onboarding lib"); return lib; }
  function _colText(v){ return _needLib().colText(v); }

  function _yn(v) { return v ? "Ja" : "Nej"; }
  function _join(v) { return Array.isArray(v) && v.length ? v.join(", ") : "—"; }

  function Box(props) {
    return h("div", {
      className: "box",
      style: { marginBottom: "12px" }
    }, props.children);
  }

  function SectionTitle(txt) {
    return h("div", {
      className: "card-title",
      style: { fontSize: "16px", marginBottom: "10px" }
    }, txt);
  }

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

  function Pill(props) {
    return h("span", {
      style: {
        display: "inline-block",
        padding: "4px 10px",
        borderRadius: "999px",
        border: "1px solid rgba(255,255,255,0.16)",
        background: "rgba(255,255,255,0.05)",
        fontSize: "12px",
        fontWeight: 700
      }
    }, String(props.children || ""));
  }

  function SmallButton(props) {
    return h("button", Object.assign({
      className: "btn",
      type: "button",
      style: { padding: "6px 10px" }
    }, props), props.children);
  }

  function JsonToggle(props) {
    const [open, setOpen] = useState(false);
    return h("div", null,
      h(SmallButton, { onClick: function () { setOpen(!open); } }, open ? "Dölj debugdata" : "Visa debugdata"),
      open ? h("pre", {
        style: {
          marginTop: "10px",
          whiteSpace: "pre-wrap",
          overflowWrap: "anywhere",
          wordBreak: "break-word",
          fontSize: "12px",
          lineHeight: "16px"
        }
      }, JSON.stringify(props.data, null, 2)) : null
    );
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
        h("div", { className: "card-title" }, "Adminvy — användare"),
        h("div", { className: "muted" }, "Laddar…")
      );
    }

    if (err) {
      return h("div", null,
        h("div", { className: "card-title" }, "Adminvy — användare"),
        h("div", { className: "note" }, "ERR: ", err)
      );
    }

    const user = (userData && userData.user) || {};
    const ti = (userData && userData.taks_identity) || {};
    const sel = (userData && userData.selection) || {};
    const ctx = (ti && ti.ctx) || {};
    const ident = (ti && ti.identity) || {};
    const cardWrap = cardData || {};
    const card = (cardWrap && cardWrap.card) || {};
    const meta = (cardWrap && cardWrap.meta) || {};
    const lifecycle = (card && card.lifecycle) || {};
    const activity = (card && card.activity) || {};
    const header = (card && card.header) || {};
    const marti = (card && card.marti) || {};

    const username = String(user.username || routeUsername || "").trim();
    const groups = Array.isArray(user.groups) ? user.groups : [];
    const cardUrl = (userData && userData.card_url) || (card && card.card_url) || "";
    const onboardStatus = _colText(card.onboarding_status);
    const stateText = activity
      ? (activity.is_current === true ? "CURRENT" : (activity.seen_recently === true ? "RECENT" : "STALE"))
      : "NEVER";

    return h("div", null,
      h("div", { className: "card-title" }, "Adminvy — användare"),

      h("div", {
        style: {
          display: "flex",
          gap: "10px",
          flexWrap: "wrap",
          alignItems: "center",
          marginBottom: "12px"
        }
      },
        h(Pill, null, _colText(username)),
        h(Pill, null, "Onboarding: " + onboardStatus),
        h(Pill, null, "Status: " + stateText)
      ),

      h("div", {
        style: {
          display: "flex",
          gap: "8px",
          flexWrap: "wrap",
          marginBottom: "12px"
        }
      },
        h("button", {
          className: "btn",
          type: "button",
          onClick: function () {
            try {
              const lib = window.TaksOnboarding && window.TaksOnboarding.lib;
              if (lib && typeof lib.setHashRoute === "function") lib.setHashRoute("create", username);
            } catch (e) {}
          }
        }, t("btn.edit")),
        cardUrl ? h("a", {
          className: "btn",
          href: cardUrl,
          target: "_blank",
          rel: "noopener noreferrer"
        }, "Öppna soldatkort") : null
      ),

      h("div", {
        style: {
          display: "grid",
          gridTemplateColumns: "minmax(320px, 1fr) minmax(320px, 1fr)",
          gap: "12px"
        }
      },
        h("div", null,
          h(Box, null,
            SectionTitle("Identitet"),
            h(KV, { k: "Användarnamn" }, _colText(username)),
            h(KV, { k: "Anropssignal" }, _colText(ctx.callsign || header.callsign || ident.callsign)),
            h(KV, { k: "Team" }, _colText(ctx.team || header.team || ident.team)),
            h(KV, { k: "ATAK-roll" }, _colText(ctx.atak_role_type || ident.atak_role_type)),
            h(KV, { k: "E-post" }, _colText(ctx.email)),
            h(KV, { k: "Grupper" }, _colText(_join(groups))),
            h(KV, { k: "Policy" }, _colText(ctx.policy_id))
          ),

          h(Box, null,
            SectionTitle("TAKS / konto"),
            h(KV, { k: "Origin" }, _colText(ti.origin)),
            h(KV, { k: "Lösenord känt" }, _yn(!!ti.password_known)),
            h(KV, { k: "Reveal password" }, _yn(!!(sel && sel.reveal_password))),
            h(KV, { k: "Kortlänk" },
              cardUrl ? h("a", { href: cardUrl, target: "_blank", rel: "noopener noreferrer" }, cardUrl) : "—"
            )
          ),

          h(Box, null,
            SectionTitle("Selection"),
            h(KV, { k: "Endpoints" }, _colText(_join(Object.keys((sel && sel.endpoints) || {})))),
            h(KV, { k: "Ctx finns" }, _yn(!!(sel && sel.ctx)))
          )
        ),

        h("div", null,
          h(Box, null,
            SectionTitle("Runtime / aktivitet"),
            h(KV, { k: "Onboarding-status" }, onboardStatus),
            h(KV, { k: "Status" }, _colText(stateText)),
            h(KV, { k: "Ålder" }, _colText(activity.age_human)),
            h(KV, { k: "UID" }, _colText(activity.uid)),
            h(KV, { k: "Senast sedd" }, _colText(activity.last_seen)),
            h(KV, { k: "CoT anropssignal" }, _colText(activity.callsign)),
            h(KV, { k: "Marti-grupper" }, _colText(_join(marti.groups)))
          ),

          h(Box, null,
            SectionTitle("Livscykel"),
            h(KV, { k: "Stage" }, _colText(lifecycle.stage)),
            h(KV, { k: "Label" }, _colText(lifecycle.label)),
            h(KV, { k: "Lösenord känt" }, _yn(!!(lifecycle.evidence && lifecycle.evidence.taks_password_known))),
            h(KV, { k: "CoT sedd" }, _yn(!!(lifecycle.evidence && lifecycle.evidence.cot_seen))),
            h(KV, { k: "Sedd nyligen" }, _yn(!!(lifecycle.evidence && lifecycle.evidence.seen_recently))),
            h(KV, { k: "Har endpoint" }, _yn(!!(lifecycle.evidence && lifecycle.evidence.marti_client && lifecycle.evidence.marti_client.has_endpoint))),
            h(KV, { k: "Har certifikat" }, _yn(!!(lifecycle.evidence && lifecycle.evidence.marti_client && lifecycle.evidence.marti_client.has_certificate)))
          ),

          h(Box, null,
            SectionTitle("Teknisk metadata"),
            h(KV, { k: "DB attached" }, _colText(typeof meta.db_attached === "boolean" ? (meta.db_attached ? "yes" : "no") : "?")),
            h(KV, { k: "DB source" }, _colText(meta.db_source)),
            h(KV, { k: "DB target" }, _colText(meta.db_target)),
            h(KV, { k: "DB error" }, _colText(meta.db_error))
          )
        )
      ),

      h(Box, null,
        SectionTitle("Debug"),
        h(JsonToggle, { data: { userData: userData, cardData: cardData } })
      )
    );
  }

  window.OnboardingUserDetailPage = OnboardingUserDetailPage;
})();
