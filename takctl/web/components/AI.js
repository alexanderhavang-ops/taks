(function(){
  const e = React.createElement;

  function tr(key, fallback){
    try{
      if (window.t && typeof window.t === "function") {
        const v = window.t(key);
        if (v && v !== key) return v;
      }
    }catch(_){}
    return fallback;
  }

  function SideBtn(props){
    const active = !!props.active;
    return e("button", {
      type: "button",
      className: active ? "tab tab-active" : "tab",
      onClick: props.onClick,
      style: {
        width: "100%",
        textAlign: "left",
        marginBottom: 6,
        display: "block",
        padding: "6px 10px",
        fontSize: 13,
        lineHeight: 1.2
      }
    }, props.label);
  }

  function getAiSubtabFromLocation(){
    try{
      const u = new URL(window.location.href);
      return u.searchParams.get("ai_view") || "domain";
    }catch(_){
      return "domain";
    }
  }

  function setAiSubtabInLocation(name){
    try{
      const u = new URL(window.location.href);
      if (name) u.searchParams.set("ai_view", name);
      else u.searchParams.delete("ai_view");
      window.history.replaceState({}, "", u.toString());
    }catch(_){}
  }

  window.AIHubView = function AIHubView(){
    const [subtab, setSubtab] = React.useState(getAiSubtabFromLocation());

    React.useEffect(()=>{
      const onPop = ()=>setSubtab(getAiSubtabFromLocation());
      window.addEventListener("popstate", onPop);
      return ()=>window.removeEventListener("popstate", onPop);
    }, []);

    function openSubtab(name){
      setSubtab(name);
      setAiSubtabInLocation(name);
    }

    let body = null;
    if (subtab === "section") body = e(window.LLM3SectionsView || (()=>e("div", null, "Missing LLM3SectionsView")));
    else if (subtab === "costs") body = e(window.UsageView || (()=>e("div", null, "Missing UsageView")));
    else body = e(window.LLM3View || (()=>e("div", null, "Missing LLM3View")));

    return e("div", {
      className: "llm-page",
      style: {
        display: "flex",
        gap: 12,
        alignItems: "flex-start",
        width: "100%",
        minWidth: 0
      }
    }, [
      e("div", {
        className: "llm-card",
        style: {
          width: 128,
          minWidth: 128,
          padding: 10,
          position: "sticky",
          top: 12,
          alignSelf: "flex-start"
        }
      }, [
        e("div", { style: { fontWeight: 800, marginBottom: 10, fontSize: 16 } }, tr("nav.ai", "AI")),
        e(SideBtn, {
          active: subtab === "domain",
          onClick: ()=>openSubtab("domain"),
          label: tr("nav.ai_by_domain", "Per domän")
        }),
        e(SideBtn, {
          active: subtab === "section",
          onClick: ()=>openSubtab("section"),
          label: tr("nav.ai_by_section", "Per sektion")
        }),
        e(SideBtn, {
          active: subtab === "costs",
          onClick: ()=>openSubtab("costs"),
          label: tr("nav.ai_costs", "AI-kostnader")
        })
      ]),
      e("div", { style: { flex: "1 1 0%", minWidth: 0, width: "100%" } }, body)
    ]);
  };
})();
