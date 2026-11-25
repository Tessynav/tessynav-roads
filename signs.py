"""TessyNav road signs builder v1 — the floating signs in the app.
Reads the City of Montréal's road signs (excluding parking; open data, CC-BY 4.0, updated daily) and keeps only the
signs that matter while driving, grouped by pole (top sign first), in small area files the app loads near the car:

  signs/t/<ix>_<iy>.json   {"v":1,"p":[[lng, lat, ["v40","u"]], ...]}   (an area is 0.02 x 0.02 degrees)
  signs/index.json         the list of areas, the date and the counts
  signs/report.txt         what was kept and skipped, for checking

Sign codes:  s stop · S4 "all approaches" plate · y yield · v<NN> speed limit · u no U-turn · l no left turn ·
             r no right turn · e do not enter · k school zone

  python3 signs.py
"""
import csv, io, json, math, os, re, shutil, urllib.request, collections, datetime

PKG = 'https://donnees.montreal.ca/api/3/action/package_show?id=c5bf5e9c-528b-4c28-b52f-218215992e35'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'signs')
TILE = 50   # areas per degree (0.02 degrees each)


def get(url, tries=3):
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'tessynav-roads (github.com/Tessynav)'})
            with urllib.request.urlopen(req, timeout=300) as r:
                return r.read()
        except Exception as e:
            print('download failed', k + 1, e)
    raise SystemExit('could not download ' + url)


def norm(t):
    t = (t or '').upper()
    for a, b in (('É', 'E'), ('È', 'E'), ('Ê', 'E'), ('À', 'A'), ('Â', 'A'), ('Û', 'U'), ('Ô', 'O'), ('Î', 'I'), ('Ç', 'C')):
        t = t.replace(a, b)
    return re.sub(r'\s+', ' ', t).strip()


def kind(code, desc):
    c, d = (code or '').upper(), norm(desc)
    if c.startswith('RA-K') or 'ARRETS TOUTES LES APPROCHES' in d:
        return 'S4'
    if c.startswith('RA-A') and c != 'RA-A-0' and d.startswith('ARRET'):
        return 's'
    if d.startswith('CEDEZ'):
        return 'y'
    m = re.match(r'MAXIMUM (\d{2,3})\b', d)
    if m and c.startswith('RC'):
        return 'v' + m.group(1)
    if 'INTERDICTION VIRAGE EN U' in d:
        return 'u'
    if 'INTERDICTION VIRAGE A GAUCHE' in d:
        return 'l'
    if 'INTERDICTION VIRAGE A DROITE' in d:
        return 'r'
    if d.startswith('ACCES INTERDIT'):
        return 'e'
    if d.startswith('ZONE SCOLAIRE'):
        return 'k'
    return None


def main():
    pkg = json.loads(get(PKG))['result']
    csv_url = next((r['url'] for r in pkg['resources'] if (r.get('format') or '').upper() == 'CSV'
                    and 'codification' not in (r.get('name') or '').lower()), None)
    if not csv_url:
        raise SystemExit('no CSV in the dataset')
    rows = list(csv.DictReader(io.StringIO(get(csv_url).decode('utf-8-sig', errors='replace'))))
    print('rows', len(rows))
    rep = collections.Counter(r.get('DESCRIPTION_REP', '') for r in rows)
    skipped = collections.Counter()
    poles = {}
    kinds = collections.Counter()
    for r in rows:
        if norm(r.get('DESCRIPTION_CAT')).startswith('ANNUL'):
            skipped['cancelled'] += 1
            continue
        if norm(r.get('DESCRIPTION_REP')) not in ('REEL', ''):
            skipped['not in place (' + (r.get('DESCRIPTION_REP') or '') + ')'] += 1
            continue
        if (r.get('PAS_SUR_RUE') or '').strip().lower() in ('true', 'vrai', 'oui', '1', 'x'):
            skipped['off the street'] += 1
            continue
        k = kind(r.get('CODE_RPA'), r.get('DESCRIPTION_RPA'))
        if not k:
            continue
        try:
            lng, lat = float(r['Longitude']), float(r['Latitude'])
        except (KeyError, ValueError):
            skipped['no position'] += 1
            continue
        if not (45.3 < lat < 45.8 and -74.1 < lng < -73.4):
            skipped['outside Montréal'] += 1
            continue
        pid = r.get('POTEAU_ID_POT') or ('%.5f,%.5f' % (lng, lat))
        try:
            pos = int(r.get('POSITION_POP') or 0)
        except ValueError:
            pos = 0
        p = poles.setdefault(pid, {'lng': lng, 'lat': lat, 's': []})
        if not any(x[1] == k for x in p['s']):
            p['s'].append((pos, k))
        kinds[k] += 1
    # an "all approaches" plate goes with its stop sign; alone it means nothing
    tiles = collections.defaultdict(list)
    for p in poles.values():
        s = [k for _, k in sorted(p['s'], key=lambda x: -x[0])]
        if 'S4' in s:
            s = [k for k in s if k != 'S4']
            if 's' in s:
                s[s.index('s')] = 'S4'
        if not s:
            continue
        ix, iy = math.floor(p['lng'] * TILE), math.floor(p['lat'] * TILE)
        tiles['%d_%d' % (ix, iy)].append([round(p['lng'], 6), round(p['lat'], 6), s])
    if os.path.isdir(os.path.join(OUT, 't')):
        shutil.rmtree(os.path.join(OUT, 't'))
    os.makedirs(os.path.join(OUT, 't'), exist_ok=True)
    for key, ps in tiles.items():
        with open(os.path.join(OUT, 't', key + '.json'), 'w', encoding='utf-8') as f:
            json.dump({'v': 1, 'p': ps}, f, separators=(',', ':'), ensure_ascii=False)
    idx = {'v': 1, 'date': datetime.datetime.utcnow().strftime('%Y-%m-%d'), 'tile': TILE, 'tiles': sorted(tiles),
           'poles': sum(len(v) for v in tiles.values()), 'source': 'Ville de Montréal (CC-BY 4.0)'}
    with open(os.path.join(OUT, 'index.json'), 'w', encoding='utf-8') as f:
        json.dump(idx, f, separators=(',', ':'))
    lines = ['Road signs ' + idx['date'], 'Rows read: %d' % len(rows), 'Poles kept: %d in %d areas' % (idx['poles'], len(tiles)),
             '', 'Signs kept by kind:'] + ['  %s %d' % kv for kv in kinds.most_common()] + \
            ['', 'Skipped:'] + ['  %s %d' % kv for kv in skipped.most_common()] + \
            ['', 'Status values (DESCRIPTION_REP):'] + ['  %s %d' % kv for kv in rep.most_common()]
    with open(os.path.join(OUT, 'report.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
