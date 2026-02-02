function CRLView() {
  const crl = useApi("api/crl/status");
  return h("div", { className: "card" },
    h("div",{className:"title"},"CRL status"),
    crl.loading ? h("div",{className:"muted"},"Loading…") :
    crl.error ? h("div",{className:"bad"}, crl.error) :
    h("pre",{style:{whiteSpace:"pre-wrap"}}, JSON.stringify(crl.data, null, 2))
  );
}
