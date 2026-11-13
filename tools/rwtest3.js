const fs=require('fs'),vm=require('vm');
const TN=require(require('path').resolve(process.env.APP||'site/v2/js')+'/roads.js');TN.HV2=true;
const toMain=[];const wctx={URL,console,Float32Array,Float64Array,Uint16Array,Uint32Array,Array,Map,Set,Math,JSON,isNaN,String};
wctx.self=wctx;wctx.location={href:'https://x/js/roadworker.js?v=2&r=51'};
wctx.importScripts=()=>vm.runInContext(fs.readFileSync((process.env.APP||'site/v2/js')+'/roads.js','utf8'),wctx);
wctx.postMessage=(m,tr)=>toMain.push(structuredClone(m,{transfer:tr||[]}));
vm.createContext(wctx);vm.runInContext(fs.readFileSync((process.env.APP||'site/v2/js')+'/roadworker.js','utf8'),wctx);
const send=(m,tr)=>wctx.onmessage({data:structuredClone(m,{transfer:tr||[]})});
const keysFor=(lng,lat)=>{const s=new Set();for(let x=lng-0.03;x<=lng+0.03;x+=0.005)for(let y=lat-0.02;y<=lat+0.02;y+=0.005) s.add(Math.floor(Math.floor(x/TN.CELL)/4)+'_'+Math.floor(Math.floor(y/TN.CELL)/4));return [...s].filter(k=>fs.existsSync('allpacks5/'+k+'.json'));};
const load=ks=>ks.map(k=>[k,JSON.parse(fs.readFileSync('allpacks5/'+k+'.json'))]);
/* reference: everything on one thread, like before */
const ref=new TN.Net();ref.startAdd(load(keysFor(-73.546,45.462)));while(ref.job) ref.step(1e5);
/* main with the background builder working out the heights */
const net=new TN.Net();net.mirror=true;net.remoteHeights=true;
let t=Date.now();net.startAdd(load(keysFor(-73.546,45.462)));while(net.job) net.step(1e5);const tMain=Date.now()-t;
t=Date.now();ref.startRebuild();while(ref.job) ref.step(1e5);const tRef=Date.now()-t;
const sj=net.workerSyncJob();let r;do{r=sj.next();}while(!r.done);
send(r.value.msg,r.value.transfer);
const hm=toMain.find(m=>m.t==='heights'),sy=toMain.find(m=>m.t==='synced');toMain.length=0;
const n=net.applyHeights(hm.h);
console.log('main thread rebuild (index only):',tMain,'ms vs everything:',tRef,'ms | heights from the worker for',n,'pieces | synced',sy&&sy.ver===net.ver);
let same=0,diff=0,maxd=0;
for(const w of net.ways.values()){const v=ref.ways.get(w.id);const a=w.hs||null,b=v.hs||null;
  if(!a&&!b){if(!!w.br===!!v.br) same++;else diff++;continue;}
  if(!a||!b||a.length!==b.length){diff++;continue;}let d=0;for(let i=0;i<a.length;i++) d=Math.max(d,Math.abs(a[i]-b[i]));maxd=Math.max(maxd,d);d<0.01?same++:diff++;}
console.log('heights equal on',same,'pieces, different on',diff,'| biggest difference',maxd.toFixed(4),'m');
/* an area built by the worker vs the reference */
let ls=0,ld=0;for(const [cx,cy] of [[-14709,9096],[-14709,9095],[-14710,9096]]){
  const g=ref.buildCellJob(cx,cy);let q;do{q=g.next();}while(!q.done);ref._sg=null;const A=q.value;
  send({t:'cell',x:cx,y:cy,k:cx+','+cy,id:1});const B=toMain.pop().L;
  for(const k of ['lot','curb','road','mark','glow']){const a=A[k],b=B[k];if(!a||!a.n){if(b) ld++;continue;}
    const eq=b&&a.p.length===b.p.length&&a.p.every((v,i)=>Math.abs(v-b.p[i])<1e-3);eq?ls++:ld++;}}
console.log('road layers identical',ls,'different',ld);
{let t=Date.now();net.startRebuild();while(net.job) net.step(1e5);const a=Date.now()-t;t=Date.now();ref.startRebuild();while(ref.job) ref.step(1e5);console.log('a rebuild on the main thread now:',a,'ms (was',Date.now()-t,'ms)');}
