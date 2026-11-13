const fs=require('fs');const TN=require(require('path').resolve(process.env.APP||'site/v2/js')+'/roads.js');TN.HV2=true;(new Function(fs.readFileSync(process.env.TRACK,'utf8')))();
const t=JSON.parse(fs.readFileSync(process.env.TRIP));const A=+process.env.A*1000,B=+process.env.B*1000;
const g=t.g.filter(r=>r[0]>A-20000&&r[0]<B);const net=new TN.Net();const need=new Set();
for(const r of g){const cx=Math.floor(r[2]/TN.CELL),cy=Math.floor(r[1]/TN.CELL);for(const dx of [-1,0,1])for(const dy of [-1,0,1])need.add(Math.floor((cx+dx)/4)+'_'+Math.floor((cy+dy)/4));}
for(const k of need){const fn='allpacks5/'+k+'.json';if(fs.existsSync(fn)) net.addPack(k,JSON.parse(fs.readFileSync(fn)),true);}net.rebuildIndex();
const tr=new TN.Track(net);let k=0,ph=null,pr=0,flips=0,maxr=0,jerks=0;const ds=[];
for(let now=g[0][0];now<=g[g.length-1][0];now+=1000/30){while(k<g.length&&g[k][0]<=now){const r=g[k];tr.gps(r[0],r[2],r[1],r[3],r[4],r[5]);k++;}
 const c=tr.frame(now,1/30);if(!c||now<A){ph=null;continue;}
 if(ph!=null){const r=(((c.hd-ph+540)%360)-180)*30;if(Math.abs(r)>maxr) maxr=Math.abs(r);if(Math.abs(r-pr)>300) jerks++;
   if(r*pr<0&&Math.abs(r)>8&&Math.abs(pr)>8) flips++;pr=r;}
 ph=c.hd;}
console.log(process.env.TRACK.split('/').pop(),'| heading: left-right wobbles',flips,'| sudden heading kicks',jerks,'| fastest turn',maxr.toFixed(0),'deg/s');
