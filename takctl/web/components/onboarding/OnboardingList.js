/* global React */
(function () {
  var h = (window.h || React.createElement); window.h = h;

  const useState = React.useState;
  const useMemo = React.useMemo;
  const useEffect = React.useEffect;

  const _t = (window.t || function (k) { return k; });

  // shared onboarding helpers
  const lib = (window.TaksOnboarding && window.TaksOnboarding.lib) || null;
  function _needLib() { if (!lib) throw new Error('Missing onboarding lib: load components/onboarding/lib.js before Onboarding.js'); return lib; }
  function _colText(v){ return _needLib().colText(v); }
  function _groups(u){ return _needLib().groups(u); }
  function _tail(act){ return _needLib().tail(act); }
  function _deriveState(act){ return _needLib().deriveState(act); }
  function _badgeForState(stateRaw){ return _needLib().badgeForState(stateRaw); }
  function _userUrls(username){ return _needLib().userUrls(username); }
  function _splitCsv(s){ return _needLib().splitCsv(s); }

  // ---------------------------------------------------------------------------
  // tables (List)
  // ---------------------------------------------------------------------------
  function OnboardingTable({ rows }) {
    return h(
      "table",
      { className: "tbl" },
      h(
        "thead",
        null,
        h(
          "tr",
          null,
          h("th", null, _t("list.username")),
          h("th", null, _t("list.groups")),
          h("th", null, _t("list.onboard")),
          h("th", null, _t("list.state")),
          h("th", null, _t("list.age")),
          h("th", null, _t("list.callsign_uid")),
          h("th", null, _t("list.actions"))
        )
      ),
      h(
        "tbody",
        null,
        (rows || []).map((u) => {
          const hdr = (u && u.header) || {};
          const act = (u && u.activity) || null;

          const username = String(hdr.username || u.username || "");
          const groupsArr =
            (hdr && Array.isArray(hdr.groups) ? hdr.groups :
             (u && u.marti && Array.isArray(u.marti.groups) ? u.marti.groups :
              (u && Array.isArray(u.groups) ? u.groups : [])));

          const onboardRaw = (u && u.onboarding_status) || "";
          const onboard = String(onboardRaw || "").toUpperCase();

          const state = act ? _deriveState(act) : "never";
          const key = username + ":" + String((act && act.uid) || "");
          const urls = _userUrls(username);

          const groupsTxt = groupsArr.length ? groupsArr.join(", ") : "—";
          const callsign = (hdr && hdr.callsign) ? String(hdr.callsign) : "—";
          const uid = (act && act.uid) ? String(act.uid) : "—";

          return h(
            "tr",
            { key },
            h("td", null, _colText(username || "—")),
            h("td", null, _colText(groupsTxt)),
            h("td", null, _colText(onboard || "—")),
            h("td", null, _badgeForState(state)),
            h("td", null, _colText(act ? act.age_human : "—")),
            h("td", null, _colText(`${callsign} / ${uid}`)),
            h(
              "td",
              null,
              h(
                "div",
                { style: { display: "flex", gap: "8px", flexWrap: "wrap", alignItems: "center" } },
                h(
                  "a",
                  {
                    className: "btn",
                    href: (function(){
                      try {
                        var lang = (window.currentLang || '').toString();
                        if (!lang) return urls.card;
                        return urls.card + (urls.card.indexOf('?') >= 0 ? '&' : '?') + 'lang=' + encodeURIComponent(lang);
                      } catch (e) { return urls.card; }
                    })(),
                    target: "_blank",
                    rel: "noopener noreferrer",
                    title: "Open the onboarding card (QR codes + links)",
                  },
                  _t("btn.card")
                ),
                h(
                  "button",
                  {
                    className: "btn",
                    onClick: () => {
                      // route: #onboarding/create:<username>
                      try {
                        const lib = (window.TaksOnboarding && window.TaksOnboarding.lib) || null;
                        if (lib && typeof lib.setHashRoute === "function") lib.setHashRoute("create", username);
                        else window.location.hash = "#onboarding/create:" + encodeURIComponent(username);
                      } catch (e) {}
                    }
                  },
                  _t("btn.edit")
                )
              )
            )
          );
        })
      )
    );
  }

  function UnknownTable({ rows }) {
    return h(
      "table",
      { className: "tbl" },
      h(
        "thead",
        null,
        h(
          "tr",
          null,
          h("th", null, _t("list.username")),
          h("th", null, _t("list.state")),
          h("th", null, _t("list.age")),
          h("th", null, _t("field.callsign")),
          h("th", null, "UID")
        )
      ),
      h(
        "tbody",
        null,
        (rows || []).map((e) => {
          const state =
            (e && (e.is_current === true ? "current" : (e.seen_recently === true ? "recent" : "stale"))) || "—";
          return h(
            "tr",
            { key: (e.username || "") + ":" + (e.uid || "") },
            h("td", null, _colText(e.username)),
            h("td", null, _badgeForState(state)),
            h("td", null, _colText(e.age_human)),
            h("td", null, _colText(e.callsign)),
            h("td", null, _colText(e.uid))
          );
        })
      )
    );
  }

  function OnboardingListPage() {
    const data = useApi("api/onboarding/status", { cacheMs: 2000, pollMs: 10000 });

    const ok = data && data.ok;
    const d = (data && data.data) || {};
    const meta = d.meta || {};
    const summary = d.summary || {};
    const users = d.users || [];
    const unknown = d.unknown_endpoints || [];

    return h(
      "div",
      null,
      h("div", { className: "card-title" }, _t("page.onboarding_list")),
      h(
        "div",
        { className: "muted", style: { marginBottom: "8px" } },
        ok ? _t("list.live_view") : _t("list.loading")
      ),
      h(
        "div",
        { className: "muted", style: { marginBottom: "10px" } },
        `Users=${_colText(summary.total_users)}  ` +
          `Seen=${_colText(summary.cot_seen)}  ` +
          `Never=${_colText(summary.never_seen)}  ` +
          `Unknown=${_colText(summary.unknown_endpoints)}  ` +
          `DB=${(typeof meta.db_attached === "boolean") ? (meta.db_attached ? "attached" : "none") : "?"} (${_colText((meta && meta.db_source) || "no meta")})`
      ),
      h(OnboardingTable, { rows: users }),
      unknown && unknown.length
        ? h(
            "div",
            { style: { marginTop: "18px" } },
            h("div", { className: "card-title", style: { fontSize: "14px" } }, _t("list.unmanaged_endpoints")),
            h(UnknownTable, { rows: unknown })
          )
        : null
    );
  }

  window.OnboardingListPage = OnboardingListPage;
})();
