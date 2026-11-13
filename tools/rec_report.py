"""Summary of one decrypted TessyNav trip: frame rate, drawing load, the car's sideways weave, notes.
   python3 rec_report.py trip_dec.json"""
import json,sys,math,collections,statistics as st
t=json.load(open(sys.argv[1]));print('duration min',round(t['dur']/60000,1))
print('notes',dict(collections.Counter(n[1] for n in t['n']).most_common(25)))
p=t['p'];fps=[r[1] for r in p]
print('fps median',st.median(fps),'| seconds under 45:',sum(1 for f in fps if f<45),'| freezes over 0.1 s:',sum(1 for r in p if r[2]>100))
fd={r[0]//1000:r[1] for r in p};rows=[]
for tt,d in t['x']:
  f=fd.get(tt//1000) or 55
  if 'calls' in d: rows.append((d['calls']/f,d.get('ktris',0)/f,f))
if rows:
  slow=[r for r in rows if r[2]<40];print('triangles (thousands) median',round(st.median([r[1] for r in rows])),'max',round(max(r[1] for r in rows)),'| when slow',round(st.median([r[1] for r in slow])) if slow else '-')
keys={}
for tt,d in t['x']:
  for k,v in d.items(): keys.setdefault(k,[]).append(v)
print('main-thread work (ms total)',{k:round(sum(v)) for k,v in sorted(keys.items(),key=lambda a:-sum(a[1])) if k not in ('calls','ktris','far')})
# sideways weave of the drawn car, measured on the recording itself (offset from the line 6 frames before/after)
f=t['f'];P=[(r[0]/1000,r[2]*78000*math.cos(math.radians(45.5))/math.cos(math.radians(45.5)),r[1]*111000,r[5]) for r in f]
rev=0;ls=0
for i in range(6,len(P)-6):
  a,b,c=P[i-6],P[i],P[i+6];dx,dz=c[1]-a[1],c[2]-a[2];L=math.hypot(dx,dz)
  if L<15: continue
  off=((b[1]-a[1])*dz-(b[2]-a[2])*dx)/L;s=1 if off>0.6 else -1 if off<-0.6 else 0
  if s and ls and s!=ls: rev+=1
  if s: ls=s
print('sideways weave: left-right reversals over 0.6 m =',rev)
