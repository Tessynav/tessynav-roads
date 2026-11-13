const fs=require('fs');const TN=require(require('path').resolve(process.env.APP||'site/v2/js')+'/roads.js');TN.HV2=true;(new Function(fs.readFileSync(process.env.TRACK,"utf8")))();if(process.env.NOEASE) TN.NOEASE=true;if(process.env.MID) TN.MIDDLE=true;
const t=JSON.parse(fs.readFileSync(process.env.TRIP));const A=+process.env.A*1000,B=+process.env.B*1000;
const g=t.g.filter(r=>r[0]>A-20000&&r[0]<B);const net=new TN.Net();const need=new Set();
for(const r of g){const cx=Math.floor(r[2]/TN.CELL),cy=Math.floor(r[1]/TN.CELL);for(const dx of [-1,0,1])for(const dy of [-1,0,1])need.add(Math.floor((cx+dx)/4)+'_'+Math.floor((cy+dy)/4));}
for(const k of need){const fn='allpacks5/'+k+'.json';if(fs.existsSync(fn)) net.addPack(k,JSON.parse(fs.readFileSync(fn)),true);}net.rebuildIndex();
const tr=new TN.Track(net);let k=0;const hist=[];const out=[];let px=null,pz=null,sumSide=0,n=0,rev=0,ls=0;
for(let now=g[0][0];now<=g[g.length-1][0];now+=1000/30){while(k<g.length&&g[k][0]<=now){const r=g[k];tr.gps(r[0],r[2],r[1],r[3],r[4],r[5]);k++;}
 const c=tr.frame(now,1/30);if(!c||now<A){px=null;continue;}
 /* the car's own sideways movement in the world: perpendicular to its smoothed direction of travel */
 hist.push([c.x,c.z]);if(hist.length>31) hist.shift();const a0=hist[0],a1=hist[hist.length-1];let hx=a1[0]-a0[0],hz=a1[1]-a0[1];const hl=Math.hypot(hx,hz)||1;const rx=-hz/hl,rz=hx/hl;
 if(px!=null){const side=((c.x-px)*rx+(c.z-pz)*rz)*30;sumSide+=Math.abs(side);n++;const sg=Math.abs(side)>0.5?Math.sign(side):0;if(sg&&ls&&sg!==ls) rev++;if(sg) ls=sg;
   if(Math.round(now)%500<34) out.push(side.toFixed(1));}
 px=c.x;pz=c.z;}
console.log(process.env.TRACK.split('/').pop(),'world sideways speed mean',(sumSide/n).toFixed(2),'m/s, reversals',rev,'| every 0.5s:',out.slice(0,60).join(' '));
