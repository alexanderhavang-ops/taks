(function(){
  window.PAGES.settings=function(container){
    container.innerHTML=`
      <section class="card">
        <div class="card__head">
          <h3>Global settings</h3>
          <div class="card__actions">
            <a class="btn btn--secondary" href="#/nodes">Back</a>
          </div>
        </div>
        <div class="muted">
          Next: wire defaults, AMI, subnet, security groups, branding, assets.
        </div>
      </section>
    `;
  };
})();
