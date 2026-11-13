const fs=require('fs');const TN=require(require('path').resolve(process.env.APP||'site/v2/js')+'/roads.js');(new Function(fs.readFileSync(process.env.TRACK,"utf8")))();if(process.env.NOEASE) TN.NOEASE=true;if(process.env.MID) TN.MIDDLE=true;
const t=JSON.parse(fs.readFileSync(process.env.TRIP));const A=+process.env.A*1000,B=+process.env.B*1000;
const g=t.g.filter(r=>r[0]>A-20000&&r[0]<B);const net=new TN.Net();const need=new Set();
for(const r of g){const cx=Math.floor(r[2]/TN.CELL),cy=Math.floor(r[1]/TN.CELL);for(const dx of [-1,0,1])for(const dy of [-1,0,1])need.add(Math.floor((cx+dx)/4)+'_'+Math.floor((cy+dy)/4));}
for(const k of need){const fn='allpacks5/'+k+'.json';if(fs.existsSync(fn)) net.addPack(k,JSON.parse(fs.readFileSync(fn)),true);}net.rebuildIndex();
const tr=new TN.Track(net);let k=0;const ds=[];let sw=0,lastW=null,big=0,prevHd=null;
for(let now=g[0][0];now<=g[g.length-1][0];now+=1000/20){while(k<g.length&&g[k][0]<=now){const r=g[k];tr.gps(r[0],r[2],r[1],r[3],r[4],r[5]);k++;}
 const c=tr.frame(now,1/20);if(!c||now<A) continue;const r=g[Math.max(0,k-1)];if(r[3]>6) continue;const q=TN.toLocal(r[2],r[1]);ds.push(Math.hypot(c.x-q[0],c.z-q[1]));
 if(c.w&&c.w!==lastW){sw++;lastW=c.w;}
 if(prevHd!=null){const a=Math.abs(((c.hd-prevHd+540)%360)-180)*20;if(a>60) big++;}prevHd=c.hd;}
ds.sort((a,b)=>a-b);const P=f=>ds[Math.floor(ds.length*f)].toFixed(1);
console.log(process.env.TRIP.slice(0,5),'samples',ds.length,'car-GPS median',P(0.5),'p95',P(0.95),'p99',P(0.99),'max',ds[ds.length-1].toFixed(1),'| piece changes',sw,'| sharp turns',big);
