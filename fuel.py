"""MapKoon gas stations (v1, Nov 21 2026): gas stations in Quebec from OpenStreetMap (Overpass API), drawn in the app as
simple 3D canopies (landmarks to turn by: no names, prices or logos are shown).
Writes fuel/fuel.json, kept in the repository (the app reads it from https://app.mapkoon.com/tessynav-roads/fuel/fuel.json).
Each station: [lat, lon, w, l, angle]   w/l: canopy size in metres when OSM draws the canopy (else 0), angle: its
direction in degrees (else null: the app lines it up with the nearest road).
Data © OpenStreetMap contributors (ODbL)."""
import json, math, os, sys, time, urllib.request, urllib.parse

SERVERS = ['https://overpass-api.de/api/interpreter',
           'https://overpass.kumi.systems/api/interpreter',
           'https://overpass.private.coffee/api/interpreter']
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fuel')
Q = ('[out:json][timeout:240];area["ISO3166-2"="CA-QC"][admin_level=4]->.a;'
     'nwr["amenity"="fuel"](area.a)->.f;'
     '.f out center tags;'
     'way["building"="roof"](area.a)->.r;'          # canopies drawn as roofs...
     'way.r(around.f:60);out geom tags;')           # ...near a gas station

def fetch():
    last = None
    for attempt in range(3):
        for url in SERVERS:
            try:
                req = urllib.request.Request(url, data=urllib.parse.urlencode({'data': Q}).encode(),
                                             headers={'User-Agent': 'MapKoon gas stations (github.com/Tessynav)'})
                with urllib.request.urlopen(req, timeout=300) as r:
                    return json.load(r).get('elements', [])
            except Exception as e:
                last = e; print('retry', url, e, flush=True); time.sleep(10)
    raise SystemExit('Overpass failed: %s' % last)

def rect(geom):
    """size and direction of a canopy outline: its longest side gives the direction"""
    lat0 = sum(p['lat'] for p in geom) / len(geom); k = math.cos(math.radians(lat0))
    P = [((p['lon']) * 111320 * k, p['lat'] * 110540) for p in geom]
    best = (0, 0)
    for a, b in zip(P, P[1:]):
        d = math.hypot(b[0] - a[0], b[1] - a[1])
        if d > best[0]: best = (d, math.degrees(math.atan2(b[0] - a[0], b[1] - a[1])))
    ang = math.radians(best[1]); ux, uy = math.sin(ang), math.cos(ang)
    al = [x * ux + y * uy for x, y in P]; ac = [-x * uy + y * ux for x, y in P]
    return max(al) - min(al), max(ac) - min(ac), best[1] % 180, sum(p['lat'] for p in geom) / len(geom), sum(p['lon'] for p in geom) / len(geom)

def main():
    els = fetch()
    st = [e for e in els if e.get('tags', {}).get('amenity') == 'fuel']
    roofs = [e for e in els if e.get('type') == 'way' and e.get('tags', {}).get('building') == 'roof' and e.get('geometry')]
    R = []
    for r in roofs:
        try:
            l, w, a, la, lo = rect(r['geometry'])
            if 6 <= l <= 60 and 4 <= w <= 30: R.append((la, lo, w, l, a))
        except Exception: pass
    out, used = [], set()
    for s in st:
        la = s.get('lat') or (s.get('center') or {}).get('lat'); lo = s.get('lon') or (s.get('center') or {}).get('lon')
        if la is None: continue
        if s.get('tags', {}).get('access') in ('private', 'no'): continue
        best, bd = None, 70
        for i, r in enumerate(R):
            if i in used: continue
            d = math.hypot((r[1] - lo) * 78000, (r[0] - la) * 110540)
            if d < bd: best, bd = i, d
        if best is not None:
            used.add(best); r = R[best]
            out.append([round(r[0], 6), round(r[1], 6), round(r[2], 1), round(r[3], 1), round(r[4], 1)])
        else:
            out.append([round(la, 6), round(lo, 6), 0, 0, None])
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, 'fuel.json'), 'w') as f:
        json.dump({'built': time.strftime('%Y-%m-%d'), 'n': len(out), 'src': 'OpenStreetMap contributors (ODbL)', 'st': out}, f, separators=(',', ':'))
    print(len(st), 'stations,', len(R), 'canopies found,', sum(1 for o in out if o[2]), 'with their canopy shape')

if __name__ == '__main__':
    main()
