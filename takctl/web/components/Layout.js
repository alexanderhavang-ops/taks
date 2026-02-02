function Layout(props) {
  const tab = props.tab;
  const setTab = props.setTab;
  const health = props.health;

  return h("div", {},
    h("div", {className:"row", style:{justifyContent:"space-between", marginBottom:12}},
      h("div", {},
        h("div", {className:"title"}, "takctl-web"),
        h("div", {className:"muted"},
          "health: ",
          health.loading ? "…" :
            health.error ? h("span",{className:"bad"}, health.error) :
            h("span",{className:"ok"}, "OK")
        )
      ),
      h("select", {value: tab, onChange: e => setTab(e.target.value)},
        h("option",{value:"users"},"Users"),
        h("option",{value:"clients"},"Clients"),
        h("option",{value:"crl"},"CRL"),
        h("option",{value:"certs"},"Certs")
      )
    ),
    props.children
  );
}
