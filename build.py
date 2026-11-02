#!/usr/bin/env python3
"""TessyNav road tiles builder v1

Builds the road tiles the app loads instead of asking Overpass during the drive.
Same road rules as roads.js (classes, one-way, widths, lanes, crossings, stop signs), so the
drawn roads look exactly like before. Runs on GitHub Actions every week (see .github/workflows/build.yml).

  python3 build.py download   download the OpenStreetMap files listed in regions.json
  python3 build.py build      cut each region, keep the roads, write the tiles into out/

Output (published with GitHub Pages at https://tessynav.github.io/tessynav-roads/):
  out/index.json          version, build date, tile sizes, regions covered
  out/p/<px>_<py>.json    one pack = 4 x 4 road cells of 0.005 degrees (about 1.6 x 2.2 km)
     w  roads   [id, class, oneway, width m, name, first node, last node, lanes, [lng,lat,...]]
     n  marks   [lng, lat, 'c' crosswalk | 's' stop line]
     c  cells   {"tx,ty": [road numbers in w]}
     b  bridges and tunnels, same fields as w plus layer (kept for the bridge rebuild, not drawn yet)
     cb cells   {"tx,ty": [numbers in b]}
"""
import datetime, json, math, os, re, subprocess, sys
import osmium

R3T = 0.005          # road cell size in degrees (same as R3T in roads.js)
PACK = 4             # cells per pack side
PAD = 0.03           # extra margin when cutting a region, so roads at the edge are complete
CLS = {'motorway': 'motorway', 'trunk': 'trunk', 'primary': 'primary', 'secondary': 'secondary',
       'tertiary': 'tertiary', 'unclassified': 'minor', 'residential': 'minor',
       'living_street': 'minor', 'service': 'service'}
LINKS = {'motorway_link', 'trunk_link', 'primary_link', 'secondary_link', 'tertiary_link'}
W2 = {'motorway': 11, 'trunk': 10, 'primary': 13, 'secondary': 12, 'tertiary': 11, 'minor': 9.5, 'service': 5.5}
W1 = {'motorway': 10.5, 'trunk': 9.5, 'primary': 8, 'secondary': 7.5, 'tertiary': 6.5, 'minor': 5.5, 'service': 4}
HERE = os.path.dirname(os.path.abspath(__file__))
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
        self.ways, self.bridges, self.marks = [], [], []

    def node(self, n):
        t = n.tags
        hw = t.get('highway')
        if hw == 'stop':
            kind = 's'
        elif hw == 'crossing':
            c = t.get('crossing', '') + ' ' + t.get('crossing:markings', '')
            if re.search(r'unmarked|\bno\b', c):
                return
            kind = 'c'
        else:
            return
        self.marks.append([round(n.location.lon, 6), round(n.location.lat, 6), kind])

    def way(self, w):
        t = w.tags
        hw = t.get('highway')
        if not hw or t.get('area') == 'yes':
            return
        if hw not in CLS and hw not in LINKS:
            return
        if hw == 'service' and re.search(r'driveway|parking_aisle|drive-through', t.get('service', '')):
            return
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
        if t.get('bridge', 'no') != 'no' or t.get('tunnel', 'no') != 'no' or t.get('covered') == 'yes':
            rec.append(lead_int(t.get('layer')))
            self.bridges.append(rec)
        else:
            self.ways.append(rec)


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


def build(cfg):
    os.makedirs(os.path.join(OUT, 'p'), exist_ok=True)
    packs = {}

    def pack(key):
        if key not in packs:
            packs[key] = {'w': [], 'n': [], 'c': {}, 'b': [], 'cb': {}, '_w': {}, '_b': {}}
        return packs[key]

    for reg in cfg['regions']:
        b = reg['bbox']
        src = os.path.join(DATA, reg['source'] + '.osm.pbf')
        cut = os.path.join(DATA, 'cut.osm.pbf')
        roads = os.path.join(DATA, 'roads.osm.pbf')
        box = ','.join(str(v) for v in (b[0] - PAD, b[1] - PAD, b[2] + PAD, b[3] + PAD))
        run(['osmium', 'extract', '-b', box, '-s', 'complete_ways', '--overwrite', '-o', cut, src])
        run(['osmium', 'tags-filter', '--overwrite', '-o', roads, cut,
             'w/highway=motorway,trunk,primary,secondary,tertiary,unclassified,residential,living_street,service,'
             'motorway_link,trunk_link,primary_link,secondary_link,tertiary_link',
             'n/highway=crossing,stop'])
        h = Roads()
        h.apply_file(roads, locations=True)
        print(reg['name'], ':', len(h.ways), 'roads,', len(h.bridges), 'bridges/tunnels,', len(h.marks), 'marks', flush=True)
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
        for f in (cut, roads):
            os.remove(f)

    total = 0
    for (px, py), P in packs.items():
        for k in ('_w', '_b'):
            del P[k]
        for k in ('c', 'cb'):
            for ck in P[k]:
                P[k][ck] = sorted(set(P[k][ck]))
        P['n'] = [list(x) for x in sorted(set(tuple(m) for m in P['n']))]
        s = json.dumps(P, separators=(',', ':'), ensure_ascii=False)
        total += len(s)
        with open(os.path.join(OUT, 'p', '%d_%d.json' % (px, py)), 'w', encoding='utf-8') as fh:
            fh.write(s)
    index = {'v': 1, 'built': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%MZ'), 'r3t': R3T, 'pack': PACK,
             'regions': [{'name': r['name'], 'bbox': r['bbox']} for r in cfg['regions']], 'packs': len(packs)}
    with open(os.path.join(OUT, 'index.json'), 'w') as fh:
        json.dump(index, fh, separators=(',', ':'))
    open(os.path.join(OUT, '.nojekyll'), 'w').close()
    with open(os.path.join(OUT, 'index.html'), 'w') as fh:
        fh.write('<!doctype html><meta charset="utf-8"><title>TessyNav roads</title>'
                 '<p>TessyNav road tiles, built %s from OpenStreetMap data &copy; OpenStreetMap contributors (ODbL).</p>'
                 % index['built'])
    print('Wrote', len(packs), 'packs,', round(total / 1e6, 1), 'MB', flush=True)


if __name__ == '__main__':
    cfg = json.load(open(os.path.join(HERE, 'regions.json')))
    step = sys.argv[1] if len(sys.argv) > 1 else 'build'
    if step == 'download':
        download(cfg)
    elif step == 'build':
        build(cfg)
    else:
        sys.exit('use: build.py download | build')
