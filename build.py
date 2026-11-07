#!/usr/bin/env python3
"""TessyNav road tiles builder v9 (v9: whole provinces as a grid of regions, tiles written region by region and merged at the borders; v8: schools, for school zone alerts; v3: parking lots, aisles, yield signs; v4: traffic lights; v5: REM at ground level;
v6: speed limits (OpenStreetMap maxspeed, km/h) as the last field of every road and bridge record, 0 = not recorded;
v7: railway level crossings as marks ('r'), and out/radars.json: Transports Quebec's photo radars and red-light cameras)

v2: also keeps railway bridges (REM / light rail, metro, trains) for the 3D bridges, and adds a ramp flag
    to roads and bridges, plus the bridge type (cable-stayed etc.) and layer to bridges.


Builds the road tiles the app loads instead of asking Overpass during the drive.
Same road rules as roads.js (classes, one-way, widths, lanes, crossings, stop signs), so the
drawn roads look exactly like before. Runs on GitHub Actions every week (see .github/workflows/build.yml).

  python3 build.py download   download the OpenStreetMap files listed in regions.json
  python3 build.py build      cut each region, keep the roads, write the tiles into out/

Output (published with GitHub Pages at https://tessynav.github.io/tessynav-roads/):
  out/index.json          version, build date, tile sizes, regions covered
  out/p/<px>_<py>.json    one pack = 4 x 4 road cells of 0.005 degrees (about 1.6 x 2.2 km)
     w  roads   [id, class, oneway, width m, name, first node, last node, lanes, [lng,lat,...], ramp 0/1]
     n  marks   [lng, lat, 'c' crosswalk | 's' stop line | 'y' yield | 't' traffic lights | 'r' railway level crossing]
     c  cells   {"tx,ty": [road numbers in w]}
     b  bridges and tunnels: [id, class, oneway, width, name, n0, n1, lanes, [lng,lat,...], layer, ramp, type,
        kind 'b' bridge / 't' tunnel]; class 'transit' = REM / light rail / metro, 'rail' = trains
     cb cells   {"tx,ty": [numbers in b]}
"""
import datetime, json, math, os, re, subprocess, sys, time
import osmium

R3T = 0.005          # road cell size in degrees (same as R3T in roads.js)
PACK = 4             # cells per pack side
PAD = 0.03           # extra margin when cutting a region, so roads at the edge are complete
CLS = {'motorway': 'motorway', 'trunk': 'trunk', 'primary': 'primary', 'secondary': 'secondary',
       'tertiary': 'tertiary', 'unclassified': 'minor', 'residential': 'minor',
       'living_street': 'minor', 'service': 'service'}
LINKS = {'motorway_link', 'trunk_link', 'primary_link', 'secondary_link', 'tertiary_link'}
RAIL = {'light_rail': 'transit', 'subway': 'transit', 'monorail': 'transit', 'rail': 'rail'}
W2 = {'motorway': 11, 'trunk': 10, 'primary': 13, 'secondary': 12, 'tertiary': 11, 'minor': 9.5, 'service': 5.5}
W1 = {'motorway': 10.5, 'trunk': 9.5, 'primary': 8, 'secondary': 7.5, 'tertiary': 6.5, 'minor': 5.5, 'service': 4}
HERE = os.path.dirname(os.path.abspath(__file__))


def speed_kmh(t):
    """the posted speed limit in km/h from OpenStreetMap tags ('50', '50 km/h', '30 mph'); 0 when not recorded.
    A road with different limits per direction keeps the forward one."""
    v = t.get('maxspeed') or t.get('maxspeed:forward') or ''
    m = re.match(r'\s*(\d+(?:\.\d+)?)\s*(mph|km/h|kmh|kph)?', v)
    if not m:
        return 0
    n = float(m.group(1))
    if m.group(2) == 'mph':
        n *= 1.609
    n = int(round(n))
    return n if 5 <= n <= 130 else 0
DATA = os.path.join(HERE, 'data')
OUT = os.path.join(HERE, 'out')


def road_w(cls, ow, ramp):
    if ramp:
        return 6
    return W1.get(cls, 6) if ow else W2.get(cls, 8)


def lead_float(s):
    m = re.match(r'\s*([-+]?\d*\.?\d+)', s or '')
    return float(m.group(1)) if m else None


def lead_int(s):
    m = re.match(r'\s*([-+]?\d+)', s or '')
    return int(m.group(1)) if m else 0


def cell(lng, lat):
    return math.floor(lng / R3T), math.floor(lat / R3T)


class Roads(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.ways, self.bridges, self.marks, self.parks, self.remg, self.schools = [], [], [], [], [], []

    def node(self, n):
        t = n.tags
        if t.get('amenity') == 'school':
            # a school mapped as a single point: its place, no outline
            self.schools.append([-n.id, [round(n.location.lon, 6), round(n.location.lat, 6)], t.get('name', '')[:60]])
            return
        hw = t.get('highway')
        if t.get('railway') == 'level_crossing':
            kind = 'r'
        elif hw == 'stop':
            kind = 's'
        elif hw == 'give_way':
            kind = 'y'
        elif hw == 'traffic_signals':
            kind = 't'
        elif hw == 'crossing':
            c = t.get('crossing', '') + ' ' + t.get('crossing:markings', '')
            if re.search(r'unmarked|\bno\b', c):
                return
            kind = 'c'
        else:
            return
        d = t.get('direction', '') or t.get('traffic_signals:direction', '')
        d = 'f' if d == 'forward' else 'b' if d == 'backward' else ''
        self.marks.append([round(n.location.lon, 6), round(n.location.lat, 6), kind, d])

    def parking(self, w, t):
        """surface parking lots as outlines (closed ways); garages and underground parking are not drawn"""
        if t.get('parking', 'surface') not in ('surface', ''):
            return
        try:
            pts = [(nd.lon, nd.lat) for nd in w.nodes]
        except osmium.InvalidLocationError:
            return
        if len(pts) < 4 or pts[0] != pts[-1]:
            return
        flat = []
        for lng, lat in pts[:-1]:
            flat += [round(lng, 6), round(lat, 6)]
        self.parks.append([w.id, flat])

    def school(self, w, t):
        """a school's grounds as an outline (simplified to at most 20 corners), for school zone alerts"""
        try:
            pts = [(nd.lon, nd.lat) for nd in w.nodes]
        except osmium.InvalidLocationError:
            return
        if len(pts) < 4 or pts[0] != pts[-1]:
            return
        pts = pts[:-1]
        step = max(1, (len(pts) + 19) // 20)
        flat = []
        for lng, lat in pts[::step]:
            flat += [round(lng, 6), round(lat, 6)]
        self.schools.append([w.id, flat, t.get('name', '')[:60]])

    def way(self, w):
        t = w.tags
        if t.get('amenity') == 'parking':
            self.parking(w, t)
            return
        if t.get('amenity') == 'school':
            self.school(w, t)
            return
        rw = t.get('railway')
        if rw in RAIL:
            self.rail_way(w, t, RAIL[rw])
            return
        hw = t.get('highway')
        if not hw or t.get('area') == 'yes':
            return
        if hw not in CLS and hw not in LINKS:
            return
        sv = t.get('service', '')
        if hw == 'service' and 'driveway' in sv:
            return
        pa = 1 if (hw == 'service' and re.search(r'parking_aisle|drive-through', sv)) else 0
        ramp = hw in LINKS
        cls = CLS[hw[:-5] if ramp else hw]
        ow = 0
        if t.get('oneway') in ('yes', '1', 'true') or t.get('junction') == 'roundabout' or hw == 'motorway':
            ow = 1
        elif t.get('oneway') in ('-1', 'reverse'):
            ow = -1
        lanes = lead_int(t.get('lanes'))
        wd = lead_float(t.get('width'))
        if not (wd and 2 < wd < 40):
            if lanes > 0:
                wd = max(3.5 if ow else 6, lanes * 3.4 + (2 if cls == 'minor' and not ow else 0))
            else:
                wd = road_w(cls, ow, ramp)
            if pa:
                wd = 5.5 if not ow else 3.5
        try:
            pts = [(nd.lon, nd.lat) for nd in w.nodes]
        except osmium.InvalidLocationError:
            return
        if len(pts) < 2:
            return
        flat = []
        for lng, lat in pts:
            flat += [round(lng, 6), round(lat, 6)]
        rec = [w.id, cls, ow, round(wd, 1), t.get('name', ''), w.nodes[0].ref, w.nodes[-1].ref, lanes, flat]
        lim = speed_kmh(t)
        if t.get('bridge', 'no') != 'no' or t.get('tunnel', 'no') != 'no' or t.get('covered') == 'yes':
            kind = 'b' if t.get('bridge', 'no') != 'no' else 't'
            rec += [lead_int(t.get('layer')), 1 if ramp else 0, t.get('bridge:structure', ''), kind, lim]
            self.bridges.append(rec)
        else:
            rec.append(1 if ramp else 0)
            rec.append(pa)
            rec.append(lim)
            self.ways.append(rec)

    def rail_way(self, w, t, cls):
        """railway bridges; plus the REM at ground level (so its line is continuous); tunnels are not drawn"""
        if t.get('bridge', 'no') == 'no':
            rem = 'REM' in (t.get('name', '') + ' ' + t.get('network', '') + ' ' + t.get('operator', ''))
            if not rem or t.get('tunnel', 'no') != 'no' or t.get('service') in ('yard', 'siding', 'spur', 'crossover'):
                return
            try:
                pts = [(nd.lon, nd.lat) for nd in w.nodes]
            except osmium.InvalidLocationError:
                return
            if len(pts) < 2:
                return
            flat = []
            for lng, lat in pts:
                flat += [round(lng, 6), round(lat, 6)]
            self.remg.append([w.id, flat])
            return
        if t.get('service') in ('yard', 'siding', 'spur'):
            return
        try:
            pts = [(nd.lon, nd.lat) for nd in w.nodes]
        except osmium.InvalidLocationError:
            return
        if len(pts) < 2:
            return
        flat = []
        for lng, lat in pts:
            flat += [round(lng, 6), round(lat, 6)]
        tracks = lead_int(t.get('tracks')) or 1
        self.bridges.append([w.id, cls, 0, round(4.5 * tracks, 1), t.get('name', ''), w.nodes[0].ref, w.nodes[-1].ref,
                             tracks, flat, lead_int(t.get('layer')), 0, t.get('bridge:structure', ''), 'b'])


def cells_of(flat):
    """every road cell a road passes through (by the box of each piece)"""
    out = set()
    for i in range(0, len(flat) - 2, 2):
        x0, x1 = sorted((flat[i], flat[i + 2]))
        y0, y1 = sorted((flat[i + 1], flat[i + 3]))
        cx0, cy0 = cell(x0, y0)
        cx1, cy1 = cell(x1, y1)
        for cx in range(cx0, cx1 + 1):
            for cy in range(cy0, cy1 + 1):
                out.add((cx, cy))
    return out


def run(cmd):
    print('+', ' '.join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def download(cfg):
    os.makedirs(DATA, exist_ok=True)
    for name, url in cfg['sources'].items():
        dst = os.path.join(DATA, name + '.osm.pbf')
        if url.startswith('http'):
            run(['curl', '-L', '--fail', '--retry', '3', '-o', dst, url])
        else:
            run(['cp', url, dst])


def regions_of(cfg):
    """the regions to build: plain boxes, or a grid ("step" in degrees) covering a big box, aligned to the tile grid"""
    out = []
    for r in cfg['regions']:
        if not r.get('step'):
            out.append(r)
            continue
        w, s_, e, n = r['bbox']
        st = r['step']
        y = s_
        while y < n - 1e-9:
            x = w
            while x < e - 1e-9:
                out.append({'name': '%s %.2f,%.2f' % (r['name'], x, y), 'source': r['source'],
                            'bbox': [round(x, 4), round(y, 4), round(min(e, x + st), 4), round(min(n, y + st), 4)]})
                x += st
            y += st
    return out


def merge_pack(E, P):
    """adds pack P (still with its _seen sets) into pack E (already written): roads and bridges by id, with the cell
    lists renumbered; parking lots, REM pieces and schools by id; marks as a set"""
    for wkey, ckey in (('w', 'c'), ('b', 'cb')):
        have = {rec[0]: i for i, rec in enumerate(E[wkey])}
        remap = {}
        for j, rec in enumerate(P[wkey]):
            if rec[0] in have:
                remap[j] = have[rec[0]]
            else:
                remap[j] = len(E[wkey])
                have[rec[0]] = remap[j]
                E[wkey].append(rec)
        for ck, lst in P[ckey].items():
            E[ckey][ck] = sorted(set(E[ckey].get(ck, [])) | {remap[j] for j in lst})
    for k in ('pk', 'rg', 'sc'):
        have = {x[0] for x in E.get(k, [])}
        E.setdefault(k, [])
        for x in P[k]:
            if x[0] not in have:
                E[k].append(x)
                have.add(x[0])
    E['n'] = [list(x) for x in sorted(set(tuple(m) for m in E.get('n', [])) | set(tuple(m) for m in P['n']))]
    return E


def build(cfg):
    os.makedirs(os.path.join(OUT, 'p'), exist_ok=True)
    packs = {}
    nschools = [0]
    written = set()

    def flush():
        """writes this region's tiles to disk, merging into tiles an earlier region already wrote (at the borders)"""
        for (px, py), P in packs.items():
            path = os.path.join(OUT, 'p', '%d_%d.json' % (px, py))
            if (px, py) in written:
                with open(path, encoding='utf-8') as fh:
                    E = json.load(fh)
                E = merge_pack(E, P)
            else:
                E = {k: v for k, v in P.items() if not k.startswith('_')}
                for k in ('c', 'cb'):
                    for ck in E[k]:
                        E[k][ck] = sorted(set(E[k][ck]))
                E['n'] = [list(x) for x in sorted(set(tuple(m) for m in E['n']))]
            with open(path, 'w', encoding='utf-8') as fh:
                fh.write(json.dumps(E, separators=(',', ':'), ensure_ascii=False))
            written.add((px, py))
        packs.clear()

    def pack(key):
        if key not in packs:
            packs[key] = {'w': [], 'n': [], 'c': {}, 'b': [], 'cb': {}, 'pk': [], 'rg': [], 'sc': [], '_w': {}, '_b': {}, '_pk': set(), '_rg': set(), '_sc': set()}
        return packs[key]

    regs = regions_of(cfg)
    print('regions to build:', len(regs), flush=True)
    for ri, reg in enumerate(regs):
        b = reg['bbox']
        src = os.path.join(DATA, reg['source'] + '.osm.pbf')
        cut = os.path.join(DATA, 'cut.osm.pbf')
        roads = os.path.join(DATA, 'roads.osm.pbf')
        box = ','.join(str(v) for v in (b[0] - PAD, b[1] - PAD, b[2] + PAD, b[3] + PAD))
        run(['osmium', 'extract', '-b', box, '-s', 'complete_ways', '--overwrite', '-o', cut, src])
        run(['osmium', 'tags-filter', '--overwrite', '-o', roads, cut,
             'w/highway=motorway,trunk,primary,secondary,tertiary,unclassified,residential,living_street,service,'
             'motorway_link,trunk_link,primary_link,secondary_link,tertiary_link',
             'w/railway=light_rail,subway,monorail,rail',
             'w/amenity=parking',
             'w/amenity=school', 'n/amenity=school',
             'n/highway=crossing,stop,give_way,traffic_signals',
             'n/railway=level_crossing'])
        h = Roads()
        h.apply_file(roads, locations=True)
        print(reg['name'], ':', len(h.ways), 'roads,', len(h.bridges), 'bridges/tunnels,', len(h.marks), 'marks,', len(h.parks), 'parking lots,', len(h.schools), 'schools', flush=True)
        for lst, wkey, ckey, seen in ((h.ways, 'w', 'c', '_w'), (h.bridges, 'b', 'cb', '_b')):
            for rec in lst:
                for cx, cy in cells_of(rec[8]):
                    P = pack((cx // PACK, cy // PACK))
                    idx = P[seen].get(rec[0])
                    if idx is None:
                        idx = len(P[wkey])
                        P[seen][rec[0]] = idx
                        P[wkey].append(rec)
                    P[ckey].setdefault('%d,%d' % (cx, cy), []).append(idx)
        for m in h.marks:
            cx, cy = cell(m[0], m[1])
            pack((cx // PACK, cy // PACK))['n'].append(m)
        for rg in h.remg:
            for cx, cy in cells_of(rg[1]):
                P = pack((cx // PACK, cy // PACK))
                if rg[0] not in P['_rg']:
                    P['_rg'].add(rg[0])
                    P['rg'].append(rg)
        for pk in h.parks:
            ring = pk[1] + pk[1][:2]
            for cx, cy in cells_of(ring):
                P = pack((cx // PACK, cy // PACK))
                if pk[0] not in P['_pk']:
                    P['_pk'].add(pk[0])
                    P['pk'].append(pk)
        for sc in h.schools:
            ring = sc[1] + sc[1][:2]
            for cx, cy in cells_of(ring if len(sc[1]) > 2 else sc[1] + sc[1]):
                P = pack((cx // PACK, cy // PACK))
                if sc[0] not in P['_sc']:
                    P['_sc'].add(sc[0])
                    P['sc'].append(sc)
        nschools[0] += len(h.schools)
        for f in (cut, roads):
            os.remove(f)
        flush()
        print('  region %d of %d done, tiles so far: %d' % (ri + 1, len(regs), len(written)), flush=True)

    total = sum(os.path.getsize(os.path.join(OUT, 'p', f)) for f in os.listdir(os.path.join(OUT, 'p')))
    index = {'v': 1, 'rail': 1, 'parking': 1, 'yield': 1, 'signals': 1, 'remground': 1, 'schools': nschools[0], 'built': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%MZ'), 'r3t': R3T, 'pack': PACK,
             'regions': [{'name': r['name'], 'bbox': r['bbox']} for r in cfg['regions']], 'packs': len(written)}
    with open(os.path.join(OUT, 'index.json'), 'w') as fh:
        json.dump(index, fh, separators=(',', ':'))
    open(os.path.join(OUT, '.nojekyll'), 'w').close()
    with open(os.path.join(OUT, 'index.html'), 'w') as fh:
        fh.write('<!doctype html><meta charset="utf-8"><title>TessyNav roads</title>'
                 '<p>TessyNav road tiles, built %s from OpenStreetMap data &copy; OpenStreetMap contributors (ODbL).</p>'
                 % index['built'])
    print('Wrote', len(written), 'packs,', round(total / 1e6, 1), 'MB', flush=True)
    if total > 950e6:
        print('WARNING: over 950 MB, too big for GitHub Pages (1 GB): trim the regions', flush=True)


RADARS_URL = ('https://ws.mapserver.transports.gouv.qc.ca/swtq?service=wfs&version=2.0.0&request=getfeature'
              '&typename=ms:radars_photos&srsname=EPSG:4326&outputformat=geojson')
RADAR_DIRS = {'nord-est': 45, 'nord-ouest': 315, 'sud-est': 135, 'sud-ouest': 225, 'nord': 0, 'sud': 180, 'est': 90, 'ouest': 270}


def radars():
    """out/radars.json: Transports Quebec's photo radars and red-light cameras (open data, CC-BY 4.0).
    Each entry: [lng, lat, kind, direction or -1, site id, description]
      kind 'f' fixed photo radar | 'r' red-light camera | 'fr' both | 'm' mobile radar zone
      direction: the compass heading covered (from 'en direction est' etc. in the description), -1 if not given"""
    import urllib.request
    j, err = None, None
    for attempt in range(4):   # (identifies itself like a normal browser, with a few tries: the server can refuse or time out)
        try:
            req = urllib.request.Request(RADARS_URL, headers={'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) TessyNav tile builder', 'Accept': 'application/json,*/*'})
            with urllib.request.urlopen(req, timeout=120) as r:
                j = json.load(r)
            break
        except Exception as e:
            err = e
            print('radars: try', attempt + 1, 'failed:', e, flush=True)
            time.sleep(15)
    if j is None:
        raise RuntimeError('radar list not available: ' + str(err))
    out = []
    for f in j.get('features', []):
        p, g = f.get('properties') or {}, f.get('geometry') or {}
        if g.get('type') != 'Point' or (p.get('dateFinService') or '').strip():
            continue
        t = (p.get('typeAppareil') or '').lower()
        kind = 'fr' if ('fixe' in t and 'feu' in t) else 'r' if 'feu' in t else 'm' if 'mobile' in t else 'f'
        desc = (p.get('description') or '').strip()
        m = re.search(r'direction\s+(nord-est|nord-ouest|sud-est|sud-ouest|nord|sud|est|ouest)', desc.lower())
        site = re.search(r'idSite=(\d+)', p.get('urlImage') or '')
        lng, lat = g['coordinates'][:2]
        out.append([round(lng, 6), round(lat, 6), kind, RADAR_DIRS[m.group(1)] if m else -1, int(site.group(1)) if site else 0, desc])
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, 'radars.json'), 'w', encoding='utf-8') as fh:
        json.dump({'date': time.strftime('%Y-%m-%d'), 'source': 'Gouvernement du Quebec, MTMD (CC-BY 4.0)', 'r': out}, fh, ensure_ascii=False, separators=(',', ':'))
    print('radars:', len(out), flush=True)


if __name__ == '__main__':
    cfg = json.load(open(os.path.join(HERE, 'regions.json')))
    step = sys.argv[1] if len(sys.argv) > 1 else 'build'
    if step == 'download':
        download(cfg)
    elif step == 'build':
        build(cfg)
        try:
            radars()   # (a problem with the radar list never stops the road tiles)
        except Exception as e:
            print('radars: skipped (' + str(e) + ')', flush=True)
    elif step == 'radars':
        radars()
    else:
        sys.exit('use: build.py download | build')
