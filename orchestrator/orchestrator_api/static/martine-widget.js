/* Shared Martine UI adapter. All permissions remain on the server. */
(function () {
  "use strict";
  function el(tag, text, style) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (style) Object.assign(node.style, style);
    return node;
  }
  function mount(root, options) {
    options = options || {};
    const base = options.base || "/api/martine";
    let stopped = false, identity = null, nodeId = "", busy = false;
    const thread = "main";
    Object.assign(root.style, {color:"#e8eef7",fontFamily:"system-ui,sans-serif"});
    async function request(path, body) {
      const response = await fetch(base + path, {method:body === undefined ? "GET":"POST",credentials:"same-origin",
        headers:{"Content-Type":"application/json","X-TAKS-Chat":"1"},body:body === undefined ? undefined:JSON.stringify(body)});
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Martine is unavailable");
      return data;
    }
    function query() { return "?conversation_id="+encodeURIComponent(thread)+(options.orchestrator?"&node_id="+encodeURIComponent(nodeId):""); }
    function button(text, action) {
      const b = el("button",text,{padding:"9px 13px",borderRadius:"9px",border:"1px solid #3b4a60",background:"#22344d",color:"#f1f6ff",cursor:"pointer"});
      b.type="button"; b.addEventListener("click",action); return b;
    }
    function field(label, type) {
      const wrapper=el("label",label,{display:"grid",gap:"5px",marginBottom:"12px"});
      const input=el("input");input.type=type||"text";input.autocomplete=type==="password"?"current-password":"username";
      Object.assign(input.style,{padding:"10px",borderRadius:"8px",border:"1px solid #3b4a60",background:"#101924",color:"#f1f6ff"});
      wrapper.append(input);return {wrapper,input};
    }
    function header() {
      root.replaceChildren();
      root.append(el("h2","Martine",{margin:"0 0 7px",fontSize:"24px"}),
        el("p","Ask about onboarding, connections, voice or server operations.",{color:"#aebed2",margin:"0 0 18px"}));
    }
    function login() { window.location.replace(options.loginUrl || '/login'); }
    async function conversation(info) {
      identity=info.user;nodeId=info.node_id || nodeId || ((info.nodes||[])[0]||{}).node_id || "";header();
      if(options.orchestrator && identity.admin){
        const select=el("select",undefined,{padding:"9px",marginBottom:"14px",background:"#172331",color:"#e8eef7",border:"1px solid #3b4a60",borderRadius:"8px"});select.setAttribute("aria-label","TAKS node");
        (info.nodes||[]).forEach(n=>{const o=el("option",n.label);o.value=n.node_id;select.append(o);});select.value=nodeId;
        select.addEventListener("change",()=>{if(busy){select.value=nodeId;return;}nodeId=select.value;conversation(info);});root.append(select);
        if(!nodeId){root.append(el("p","No TAK node is currently available."));return;}
      }
      const messages=el("div",undefined,{display:"grid",gap:"13px",maxHeight:"58vh",minHeight:"220px",overflowY:"auto",padding:"12px",border:"1px solid #2d3a4c",borderRadius:"12px",background:"#0d141d"});
      messages.setAttribute("role","log");messages.setAttribute("aria-live","polite");messages.setAttribute("aria-label","Conversation with Martine");root.append(messages);
      function message(role,text){const row=el("div",text,{padding:"12px 14px",whiteSpace:"pre-wrap",overflowWrap:"anywhere",lineHeight:"1.5",borderRadius:"11px",background:role==="user"?"#20344e":"#18232f",marginLeft:role==="user"?"25px":"0",marginRight:role==="user"?"0":"25px"});row.setAttribute("aria-label",role==="user"?"You":"Martine");messages.append(row);messages.scrollTop=messages.scrollHeight;return row;}
      const suggestions=el("div",undefined,{display:"flex",gap:"8px",flexWrap:"wrap",margin:"12px 0"});
      const form=el("form"),input=el("textarea");input.rows=3;input.placeholder="Ask Martine… Avoid pasting passwords or certificates.";input.setAttribute("aria-label","Message to Martine");
      Object.assign(input.style,{boxSizing:"border-box",width:"100%",padding:"12px",background:"#111d2b",color:"#e8eef7",border:"1px solid #3b4a60",borderRadius:"10px",resize:"vertical"});
      const send=button("Send",()=>form.requestSubmit());send.style.marginTop="9px";
      const examples=identity.admin?["Check the server connections","Read recent voice authentication failures"]:["Check my onboarding","Why won’t my voice connect?"];
      examples.forEach(text=>suggestions.append(button(text,()=>{input.value=text;input.focus();})));root.append(suggestions);form.append(input,send);root.append(form);
      input.addEventListener("keydown",event=>{if(event.key==="Enter"&&!event.shiftKey){event.preventDefault();form.requestSubmit();}});
      try{const data=await request("/history"+query());data.messages.forEach(m=>message(m.role,m.text));}catch(e){message("assistant",e.message);}
      form.addEventListener("submit",async event=>{event.preventDefault();const text=input.value.trim();if(!text||busy)return;busy=true;send.disabled=true;input.disabled=true;input.value="";message("user",text);const pending=message("assistant","Martine is checking…");
        try {
          let data=await request("/ask",{message:text,conversation_id:thread,node_id:nodeId});
          if(!data.job_id)throw new Error(data.error||"Request rejected");const job=data.job_id;let complete=false;
          for(let i=0;i<240&&!stopped;i++){
            await new Promise(resolve=>setTimeout(resolve,1000));data=await request("/jobs/"+encodeURIComponent(job)+query());
            if(data.status==="done"){complete=true;break;}
          }
          if(stopped)return;if(!complete)throw new Error("Still working. Please try again shortly.");
          pending.textContent=data.answer||data.error||"No answer was returned.";
          (data.actions||[]).forEach(action=>{const card=el("div",undefined,{padding:"12px",border:"1px solid #bd9a4c",borderRadius:"9px"});card.append(el("strong",action.service+" · "+action.operation),el("pre",JSON.stringify(action.arguments,null,2),{whiteSpace:"pre-wrap",overflowWrap:"anywhere"}));
            const approve=button("Approve this change",async()=>{approve.disabled=true;try{const r=await request("/actions/"+encodeURIComponent(action.id)+"/confirm",{node_id:nodeId});message("assistant",r.ok?"Change completed.":"Change could not be completed.");card.remove();}catch(e){message("assistant",e.message);}});card.append(approve);messages.append(card);});
        }catch(e){pending.textContent=e.message;}finally{busy=false;send.disabled=false;input.disabled=false;input.focus();messages.scrollTop=messages.scrollHeight;}
      });
    }
    async function start(){try{const info=await request("/me");if(info.authenticated)await conversation(info);else login();}catch(e){login();}}
    start();return ()=>{stopped=true;root.replaceChildren();};
  }
  window.MartineChat={mount};
})();
