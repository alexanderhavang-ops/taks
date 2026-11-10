/* global React */
(function () {
  function MartineView() {
    const target=React.useRef(null);
    React.useEffect(function () {
      return window.MartineChat.mount(target.current,{base:'/api/martine',onLogin:()=>window.location.reload()});
    },[]);
    return React.createElement('div',{ref:target,style:{maxWidth:'980px',margin:'0 auto',padding:'18px'}});
  }
  window.MartineView=MartineView;
})();
