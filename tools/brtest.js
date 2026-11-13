const fs=require('fs');const TN=require(require('path').resolve(process.env.APP||'site/v2/js')+'/roads.js');TN.HV2=true;(new Function(fs.readFileSync((process.env.APP||'site/v2/js')+'/track.js','utf8')))();
const t=JSON.parse(fs.readFileSync('trip42_dec.json'));const A=820e3,B=1000e3;
const g=t.g.filter(r=>r[0]>A-20000&&r[0]<B);const net=new TN.Net();const need=new Set();
for(const r of g){const cx=Math.floor(r[2]/TN.CELL),cy=Math.floor(r[1]/TN.CELL);for(const dx of [-1,0,1])for(const dy of [-1,0,1])need.add(Math.floor((cx+dx)/4)+'_'+Math.floor((cy+dy)/4));}
let have=0;for(const k of need){const fn='allpacks5/'+k+'.json';if(fs.existsSync(fn)){net.addPack(k,JSON.parse(fs.readFileSync(fn)),true);have++;}}net.rebuildIndex();
console.log('packs',have,'of',need.size);
const tr=new TN.Track(net);let k=0;
for(let now=g[0][0];now<=g[g.length-1][0];now+=1000/30){while(k<g.length&&g[k][0]<=now){const r=g[k];tr.gps(r[0],r[2],r[1],r[3],r[4],r[5]);k++;}
 const c=tr.frame(now,1/30);if(!c||now<A) continue;
 if(Math.round(now)%15000<34&&c.w) console.log(Math.round(now/1000),'piece',c.w.id,c.w.cls,'bridge',!!c.w.br,'H',c.w.H,'hs?',!!c.w.hs,'deck here',TN.heightAt(c.w,c.s).toFixed(1),'car y',(c.y||0).toFixed(1));}
