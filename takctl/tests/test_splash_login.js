const fs=require('fs'),vm=require('vm'),assert=require('assert');
async function check(file){
 const callbacks={},posts=[];let destination='';
 const element=id=>({id,style:{},value:id==='__u'?'alexander':id==='__p'?'fixture':'',innerHTML:'',textContent:'',appendChild(){},querySelector(){return null;},focus(){},addEventListener(name,fn){callbacks[id+':'+name]=fn;}});
 const nodes=Object.fromEntries(['__splash','__u','__p','__go','__err','__brand_logos','__splash_slogan'].map(id=>[id,element(id)]));
 const context={URL,window:{location:{href:'https://unit.example/splash.html',replace:url=>destination=url}},document:{getElementById:id=>nodes[id]||null,body:{classList:{add(){},remove(){}}},createElement:()=>element('img')},fetch:async(url,options)=>{
  if(options?.method==='POST'){posts.push(JSON.parse(options.body));return {ok:true,json:async()=>({ok:true})};}
  return {ok:true,json:async()=>url.includes('whoami')?{authenticated:false}:{slogan:'TAKS',logos:[],login:{role:false}},text:async()=>'<form>Username Password</form>'};
 }};
 vm.runInNewContext(fs.readFileSync(file,'utf8'),context);
 for(let i=0;i<4;i++)await new Promise(setImmediate);
 assert(!nodes.__splash.innerHTML.includes('Failed to load'));
 assert(callbacks['__go:click'],'Main login submit was not wired');callbacks['__go:click']();
 for(let i=0;i<4;i++)await new Promise(setImmediate);
 assert.deepEqual(Object.keys(posts[0]).sort(),['password','username']);assert.equal(destination,'./');
 console.log('PASS main splash submit without role: '+file);
}
(async()=>{await check('takctl/web/splash.js');await check('orchestrator/orchestrator_api/static/login/splash.js');})().catch(e=>{console.error(e);process.exit(1);});
