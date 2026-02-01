function UsersView() {
  const users = useApi("api/users");
  const [selected, setSelected] = React.useState(null);
  const user = selected ? useApi("api/users/" + encodeURIComponent(selected)) : {loading:false,data:null,error:null};

  return h("div", { className: "grid" },

    h("div", { className: "card" },
      h("div",{className:"row", style:{justifyContent:"space-between"}},
        h("div",{className:"title"},"Users"),
        h("div",{className:"muted"}, users.data ? (users.data.count + " total") : "")
      ),
      users.loading ? h("div",{className:"muted"},"Loading…") :
      users.error ? h("div",{className:"bad"}, users.error) :
      h("table", {},
        h("thead", {}, h("tr", {},
          h("th", {}, "username"),
          h("th", {}, "role")
        )),
        h("tbody", {},
          (users.data.users || []).map(u =>
            h("tr", {key:u.username, style:{cursor:"pointer"}, onClick:()=>setSelected(u.username)},
              h("td", {}, u.username),
              h("td", {}, u.role || "")
            )
          )
        )
      )
    ),

    h("div", { className: "card" },
      h("div",{className:"title"},"User detail"),
      !selected ? h("div",{className:"muted"},"Select a user") :
      user.loading ? h("div",{className:"muted"},"Loading…") :
      user.error ? h("div",{className:"bad"}, user.error) :
      h("div", {},
        h("div", {}, h("span",{className:"muted"},"username: "), user.data.username),
        h("div", {}, h("span",{className:"muted"},"role: "), user.data.role || ""),
        h("div", {}, h("span",{className:"muted"},"fingerprint: "), user.data.fingerprint || ""),
        h("div", {style:{marginTop:10}},
          h("div",{className:"muted"},"groups rw:"),
          (user.data.groups_rw||[]).map(g => h("span",{className:"pill", key:"rw-"+g}, g))
        ),
        h("div", {style:{marginTop:10}},
          h("div",{className:"muted"},"groups in:"),
          (user.data.groups_in||[]).map(g => h("span",{className:"pill", key:"in-"+g}, g))
        ),
        h("div", {style:{marginTop:10}},
          h("div",{className:"muted"},"groups out:"),
          (user.data.groups_out||[]).map(g => h("span",{className:"pill", key:"out-"+g}, g))
        )
      )
    )
  );
}
