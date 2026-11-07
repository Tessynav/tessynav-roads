"""TessyNav chargers (v1): Tesla Superchargers and other fast chargers in Quebec, from OpenStreetMap (Overpass API).
Writes chargers.json, published on the "chargers" branch, where the app reads it:
https://raw.githubusercontent.com/Tessynav/tessynav-roads/chargers/chargers.json

Each site: [id, lat, lon, name, stalls, max kW, kind, network]
  kind "sc": Tesla Supercharger;  kind "dc": other fast charger (CCS / CHAdeMO, 50 kW and more)
Tesla destination chargers (slow, at hotels) and ordinary level 2 chargers are left out.
Data © OpenStreetMap contributors (ODbL).
"""
import json, re, sys, time, datetime, urllib.request, urllib.parse

REGIONS = ['CA-QC']        # provinces (ISO 3166-2); more can be added later
SERVERS = ['https://overpass-api.de/api/interpreter',
           'https://overpass.kumi.systems/api/interpreter',
           'https://overpass.private.coffee/api/interpreter']


def query(iso):
    q = ('[out:json][timeout:180];area["ISO3166-2"="%s"][admin_level=4]->.a;'
         'nwr["amenity"="charging_station"](area.a);out center tags;' % iso)
    last = None
    for attempt in range(2):
        for url in SERVERS:
            try:
                req = urllib.request.Request(url, data=urllib.parse.urlencode({'data': q}).encode(),
                                             headers={'User-Agent': 'TessyNav chargers (github.com/Tessynav)'})
                with urllib.request.urlopen(req, timeout=240) as r:
                    j = json.load(r)
                print(iso, 'from', url, ':', len(j.get('elements', [])), 'charging stations', flush=True)
                return j.get('elements', [])
            except Exception as e:
                last = e
                print('  ', url, 'failed:', e, flush=True)
        time.sleep(20)
    raise SystemExit('Overpass not reachable: %s' % last)


def kw_of(t):
    best = 0
    for k, v in t.items():
        if k.startswith('socket:') and k.endswith(':output') or k in ('charging_station:output', 'output'):
            for m in re.finditer(r'(\d+(?:[.,]\d+)?)\s*(kw|kva|w|v|a)?\b', str(v).lower()):
                x, unit = float(m.group(1).replace(',', '.')), m.group(2)
                if unit in ('v', 'a'):
                    continue                         # (volts and amps, not power)
                if unit == 'w':
                    x /= 1000
                if unit or x <= 400:
                    best = max(best, x)
    return int(best)


def count_of(t, keys):
    n = 0
    for k in keys:
        v = t.get(k)
        if v and re.fullmatch(r'\d+', str(v).strip()):
            n += int(v)
    return n


def classify(t):
    text = ' '.join(str(t.get(k, '')) for k in ('name', 'brand', 'operator', 'network', 'brand:en', 'operator:en')).lower()
    if 'tesla' in text or 'supercharger' in text:
        if 'destination' in text:
            return None                          # slow chargers at hotels and restaurants
        if 'supercharger' in text or any(k.startswith('socket:tesla_supercharger') or k.startswith('socket:nacs') for k in t):
            return 'sc'
        return None
    fast = any(k.split(':')[1] in ('type2_combo', 'ccs', 'chademo', 'nacs') for k in t if k.startswith('socket:') and k.count(':') == 1)
    if fast and kw_of(t) >= 50:
        return 'dc'
    return None


def main():
    out = []
    for iso in REGIONS:
        for e in query(iso):
            t = e.get('tags', {})
            kind = classify(t)
            if not kind:
                continue
            lat = e.get('lat', e.get('center', {}).get('lat'))
            lon = e.get('lon', e.get('center', {}).get('lon'))
            if lat is None or lon is None:
                continue
            stalls = 0
            try:
                stalls = int(str(t.get('capacity', '0')).split(';')[0])
            except ValueError:
                pass
            if not stalls:
                stalls = count_of(t, [k for k in t if k.startswith('socket:') and k.count(':') == 1])
            name = t.get('name') or t.get('brand') or ('Tesla Supercharger' if kind == 'sc' else 'Fast charger')
            net = 'Tesla' if kind == 'sc' else (t.get('network') or t.get('operator') or t.get('brand') or '')
            out.append([e['type'][0] + str(e['id']), round(lat, 6), round(lon, 6), name, stalls, kw_of(t), kind, net])
    out.sort(key=lambda s: (s[6], s[1], s[2]))
    sc = sum(1 for s in out if s[6] == 'sc')
    res = {'t': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%MZ'), 'regions': REGIONS,
           'src': 'OpenStreetMap contributors (ODbL)', 's': out}
    with open('chargers.json', 'w', encoding='utf-8') as fh:
        json.dump(res, fh, ensure_ascii=False, separators=(',', ':'))
    print('Superchargers:', sc, '| other fast chargers:', len(out) - sc, flush=True)
    if sc < 10:
        sys.exit('Too few Superchargers found (%d): not publishing' % sc)


if __name__ == '__main__':
    main()
