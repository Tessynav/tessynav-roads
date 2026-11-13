#!/bin/sh
# Downloads the road data around a decrypted trip from the 'tiles' branch into ./allpacks5
#   sh get_packs.sh trip_dec.json
mkdir -p allpacks5
python3 - "$1" <<'PY' > need.txt
import json,math,sys
t=json.load(open(sys.argv[1]));C=0.005;need=set()
for r in t['g']:
  cx,cy=math.floor(r[2]/C),math.floor(r[1]/C)
  for dx in (-1,0,1):
    for dy in (-1,0,1): need.add('%d_%d'%(math.floor((cx+dx)/4),math.floor((cy+dy)/4)))
print('\n'.join(sorted(need)))
PY
while read k; do [ -f "allpacks5/$k.json" ] || curl -sS -f -o "allpacks5/$k.json" "https://raw.githubusercontent.com/Tessynav/tessynav-roads/tiles/p/$k.json" || rm -f "allpacks5/$k.json"; done < need.txt
ls allpacks5 | wc -l
