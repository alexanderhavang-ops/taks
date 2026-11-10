/* global React */
(function () {
  function MartineView() {
    const target=React.useRef(null);
    React.useEffect(function () {
      return window.MartineChat.mount(target.current,{base:'/api/martine',loginUrl:'/splash.html'});
    },[]);
    return React.createElement('div',{ref:target,style:{maxWidth:'980px',margin:'0 auto',padding:'18px'}});
  }
  function PersonalOnboardingView() {
    const response=useApi('api/martine/onboarding',{cacheMs:0,pollMs:15000});
    const data=response && response.data;
    if (!data) return React.createElement('p',null,'Loading onboarding…');
    const h=React.createElement;
    return h('section',{className:'card'},h('h2',null,'My onboarding'),
      h('p',null,'Account: '+data.username),h('p',null,'Configured callsign: '+(data.configured_callsign||'—')),
      h('p',null,'Observed callsign: '+(data.observed_callsign||'—')),
      h('p',null,data.voice_connected?'Voice connected':'Voice not connected'),
      (data.devices||[]).map(d=>h('div',{className:'card',key:d.client_uid},
        h('strong',null,(/WEAR|WATCH/i.test((d.client_uid||'')+' '+(d.tak_platform||''))?'⌚ ':'📱 ')+(d.tak_device||d.client_uid)),
        h('p',null,(d.connection_event_name||d.state||'Unknown')+' · '+(d.observed_callsign||'')))),
      h('p',null,'Use Martine in the menu for help with enrollment, connections or voice.'));
  }
  window.PersonalOnboardingView=PersonalOnboardingView;
  window.MartineView=MartineView;
})();
