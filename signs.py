"""TessyNav road signs builder v2 — the floating signs in the app (v2: Mapillary fills the areas the city list leaves empty).
Reads the City of Montréal's road signs (excluding parking; open data, CC-BY 4.0, updated daily) and keeps only the
signs that matter while driving, grouped by pole (top sign first), in small area files the app loads near the car:

  signs/t/<ix>_<iy>.json   {"v":1,"p":[[lng, lat, ["v40","u"]], ...]}   (an area is 0.02 x 0.02 degrees)
  signs/index.json         the list of areas, the date and the counts
  signs/report.txt         what was kept and skipped, for checking

Where the city has (almost) no signs (Verdun, LaSalle, Lachine, Pierrefonds, the South Shore, Laval...), the signs
Mapillary found in street photos are used instead (needs the MAPILLARY_TOKEN secret; such records carry a 4th
field "m", and the app then shows the Mapillary credit, as its terms ask).

Sign codes:  s stop · S4 "all approaches" plate · y yield · v<NN> speed limit · u no U-turn · l no left turn ·
             r no right turn · e do not enter · k school zone

  python3 signs.py
"""
import csv, io, json, math, os, re, shutil, urllib.request, urllib.parse, collections, datetime

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


# ---- Mapillary (signs detected in street photos), for the areas the city list leaves empty ----
MLY_BOX = (-73.98, 45.38, -73.33, 45.72)      # greater Montréal: Laval to Longueuil, Pierrefonds to Pointe-aux-Trembles
MLY_MIN = 15                                  # an area with fewer city poles than this asks Mapillary


def mly_kind(v):
    v = (v or '').lower()
    if v.startswith('regulatory--stop--'):
        return 's'
    if v.startswith('regulatory--yield--'):
        return 'y'
    m = re.match(r'regulatory--maximum-speed-limit-(\d{2,3})--', v)
    if m and 10 <= int(m.group(1)) <= 100:
        return 'v' + m.group(1)
    if v.startswith('regulatory--no-u-turn--'):
        return 'u'
    if v.startswith('regulatory--no-left-turn--'):
        return 'l'
    if v.startswith('regulatory--no-right-turn--'):
        return 'r'
    if v.startswith('regulatory--no-entry--'):
        return 'e'
    if 'school-zone' in v:
        return 'k'
    return None


def mapillary(tiles, report):
    tok = os.environ.get('MAPILLARY_TOKEN', '').strip()
    if not tok:
        report.append('Mapillary: no MAPILLARY_TOKEN secret, skipped')
        return
    x0, y0 = math.floor(MLY_BOX[0] * TILE), math.floor(MLY_BOX[1] * TILE)
    x1, y1 = math.floor(MLY_BOX[2] * TILE), math.floor(MLY_BOX[3] * TILE)
    asked = added = failed = 0
    kinds = collections.Counter()
    since = (datetime.datetime.utcnow() - datetime.timedelta(days=5 * 365)).strftime('%Y-%m-%d')
    for ix in range(x0, x1 + 1):
        for iy in range(y0, y1 + 1):
            key = '%d_%d' % (ix, iy)
            if len(tiles.get(key, [])) >= MLY_MIN:
                continue
            bb = '%.4f,%.4f,%.4f,%.4f' % (ix / TILE, iy / TILE, (ix + 1) / TILE, (iy + 1) / TILE)
            url = ('https://graph.mapillary.com/map_features?fields=id,object_value,geometry,last_seen_at'
                   '&limit=2000&bbox=' + bb + '&access_token=' + urllib.parse.quote(tok, safe=''))
            asked += 1
            got = []
            for page in range(5):
                try:
                    req = urllib.request.Request(url, headers={'User-Agent': 'tessynav-roads (github.com/Tessynav)'})
                    with urllib.request.urlopen(req, timeout=60) as r:
                        j = json.loads(r.read())
                except Exception as e:
                    failed += 1
                    if failed <= 3:
                        report.append('Mapillary error ' + key + ': ' + str(e)[:120])
                    break
                got += j.get('data', [])
                url = (j.get('paging') or {}).get('next')
                if not url:
                    break
            kept = []
            for f in got:
                k = mly_kind(f.get('object_value'))
                g = f.get('geometry') or {}
                if not k or g.get('type') != 'Point':
                    continue
                if (f.get('last_seen_at') or '9999')[:10] < since:
                    continue
                lng, lat = g['coordinates'][0], g['coordinates'][1]
                # the same sign seen twice: one is enough (same kind within 12 m)
                if any(q[2][0] == k and abs(q[0] - lng) < 0.00016 and abs(q[1] - lat) < 0.00011 for q in kept):
                    continue
                kept.append([round(lng, 6), round(lat, 6), [k], 'm'])
                kinds[k] += 1
            if kept:
                tiles[key] = tiles.get(key, []) + kept
                added += len(kept)
    report += ['', 'Mapillary: %d areas asked, %d signs added, %d errors' % (asked, added, failed)] + \
              ['  %s %d' % kv for kv in kinds.most_common()]


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
    mrep = []
    mapillary(tiles, mrep)
    if os.path.isdir(os.path.join(OUT, 't')):
        shutil.rmtree(os.path.join(OUT, 't'))
    os.makedirs(os.path.join(OUT, 't'), exist_ok=True)
    for key, ps in tiles.items():
        with open(os.path.join(OUT, 't', key + '.json'), 'w', encoding='utf-8') as f:
            json.dump({'v': 1, 'p': ps}, f, separators=(',', ':'), ensure_ascii=False)
    idx = {'v': 1, 'date': datetime.datetime.utcnow().strftime('%Y-%m-%d'), 'tile': TILE, 'tiles': sorted(tiles),
           'poles': sum(len(v) for v in tiles.values()), 'source': 'Ville de Montréal (CC-BY 4.0); Mapillary'}
    with open(os.path.join(OUT, 'index.json'), 'w', encoding='utf-8') as f:
        json.dump(idx, f, separators=(',', ':'))
    lines = ['Road signs ' + idx['date'], 'Rows read: %d' % len(rows), 'Poles kept: %d in %d areas' % (idx['poles'], len(tiles)),
             '', 'Signs kept by kind:'] + ['  %s %d' % kv for kv in kinds.most_common()] + \
            ['', 'Skipped:'] + ['  %s %d' % kv for kv in skipped.most_common()] + \
            ['', 'Status values (DESCRIPTION_REP):'] + ['  %s %d' % kv for kv in rep.most_common()] + mrep
    with open(os.path.join(OUT, 'report.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
