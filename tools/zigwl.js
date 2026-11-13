const fs=require('fs');const TN=require(require('path').resolve(process.env.APP||'site/v2/js')+'/roads.js');TN.HV2=true;(new Function(fs.readFileSync(process.env.TRACK,'utf8')))();
const t=JSON.parse(fs.readFileSync(process.env.TRIP));const A=+process.env.A*1000,B=+process.env.B*1000;
const g=t.g.filter(r=>r[0]>A-20000&&r[0]<B);const net=new TN.Net();const need=new Set();
for(const r of g){const cx=Math.floor(r[2]/TN.CELL),cy=Math.floor(r[1]/TN.CELL);for(const dx of [-1,0,1])for(const dy of [-1,0,1])need.add(Math.floor((cx+dx)/4)+'_'+Math.floor((cy+dy)/4));}
for(const k of need){const fn='allpacks5/'+k+'.json';if(fs.existsSync(fn)) net.addPack(k,JSON.parse(fs.readFileSync(fn)),true);}net.rebuildIndex();
if(process.env.WL) TN.settings={wideLanes:true};const tr=new TN.Track(net);let k=0,prev=null,flips=0,lastSign=0,lastFlipT=0,sumAbs=0,n=0,maxv=0,early=0;const lv=[];
for(let now=g[0][0];now<=g[g.length-1][0];now+=1000/30){while(k<g.length&&g[k][0]<=now){const r=g[k];tr.gps(r[0],r[2],r[1],r[3],r[4],r[5]);k++;}
 const c=tr.frame(now,1/30);if(!c||now<A||!c.w) {prev=null;continue;}
 if(c.early) early++;
 if(prev&&prev.w===c.w&&c.lat!=null&&prev.lat!=null){const v=(c.lat-prev.lat)*30;sumAbs+=Math.abs(v);n++;if(Math.abs(v)>maxv) maxv=Math.abs(v);
   const s=Math.abs(v)>0.4?Math.sign(v):0;if(s&&lastSign&&s!==lastSign) flips++;if(s) lastSign=s;}
 prev={w:c.w,lat:c.lat};}
console.log(process.env.TRACK.split('/').pop(),'sideways moves: mean',(sumAbs/n).toFixed(3),'m/s, fastest',maxv.toFixed(2),'m/s, left-right reversals',flips);
