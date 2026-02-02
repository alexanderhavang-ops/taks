function CertsView() {
  const [uid, setUid] = React.useState("");
  const [limit, setLimit] = React.useState(200);

  const url = uid
    ? ("api/certs?limit=" + encodeURIComponent(limit) + "&client_uid=" + encodeURIComponent(uid))
    : ("api/certs?limit=" + encodeURIComponent(limit));

  const certs = useApi(url);

  return h("div", { className: "card" },
    h("div",{className:"row", style:{justifyContent:"space-between", marginBottom:10}},
      h("div",{className:"title"},"Certs"),
      h("div",{className:"row"},
        h("span",{className:"muted"},"limit"),
        h("input",{value:String(limit), onChange:e=>setLimit(Number(e.target.value||200)), style:{width:90}}),
        h("input",{placeholder:"filter by client_uid (optional)", value:uid, onChange:e=>setUid(e.target.value), style:{width:320}})
      )
    ),

    certs.loading ? h("div",{className:"muted"},"Loading…") :
    certs.error ? h("div",{className:"bad"}, certs.error) :
    h("table", {},
      h("thead", {}, h("tr", {},
        h("th", {}, "id"),
        h("th", {}, "client_uid"),
        h("th", {}, "subject_dn"),
        h("th", {}, "expires"),
        h("th", {}, "revoked_db"),
        h("th", {}, "serial"),
        h("th", {}, "revoked_crl")
      )),
      h("tbody", {},
        (certs.data.certs || []).map((c, idx) =>
          h("tr", {key: String(c.id) + ":" + idx},
            h("td", {}, c.id),
            h("td", {}, c.client_uid),
            h("td", {}, c.subject_dn),
            h("td", {}, fmtTs(c.expires)),
            h("td", {}, c.revoked_in_db ? "YES":"NO"),
            h("td", {}, c.serial_hex || ""),
            h("td", {}, (c.revoked_in_crl === null || c.revoked_in_crl === undefined) ? "?" : (c.revoked_in_crl ? "YES":"NO"))
          )
        )
      )
    )
  );
}
