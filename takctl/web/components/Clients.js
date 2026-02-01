function ClientsView() {
  const [limit, setLimit] = React.useState(30);
  const clients = useApi("api/clients?limit=" + encodeURIComponent(limit));

  return h("div", { className: "card" },
    h("div",{className:"row", style:{justifyContent:"space-between", marginBottom:10}},
      h("div",{className:"title"},"Clients"),
      h("div",{className:"row"},
        h("span",{className:"muted"},"limit"),
        h("input",{value:String(limit), onChange:e=>setLimit(Number(e.target.value||30)), style:{width:80}})
      )
    ),
    clients.loading ? h("div",{className:"muted"},"Loading…") :
    clients.error ? h("div",{className:"bad"}, clients.error) :
    h("table", {},
      h("thead", {}, h("tr", {},
        h("th", {}, "callsign"),
        h("th", {}, "uid"),
        h("th", {}, "last_seen")
      )),
      h("tbody", {},
        (clients.data.clients || []).map((c, idx) =>
          h("tr", {key: c.uid + ":" + idx},
            h("td", {}, c.callsign),
            h("td", {}, c.uid),
            h("td", {}, fmtTs(c.last_seen))
          )
        )
      )
    )
  );
}
