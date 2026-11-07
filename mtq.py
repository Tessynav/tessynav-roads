#!/usr/bin/env python3
"""TessyNav — live road events from Transports Québec (Québec 511), every 15 minutes (see .github/workflows/mtq.yml).

Two open-data layers (CC BY 4.0, Gouvernement du Québec):
  ms:evenements        warnings: closures, accidents and other incidents
  ms:chantiers_mtmdet  road works, with start/end dates and often a schedule ("Friday between 10 p.m. and 6 a.m.")
Only what is active right now is kept (dates, and hours/days when the text gives them); ferry notices and truck-only
items are dropped. The result is a small file the app reads: mtq.json
  {"t": "...", "e": [{"id","k","d","dir","p","road","src"}...]}
     k    kind: closed, lane, works, accident, hazard
     d    text shown on the card (English)
     dir  N, S, E, W, or "" for both directions
     p    the affected stretch, [lng, lat, lng, lat, ...] (simplified)
"""
import datetime, json, re, sys, time, urllib.request
from zoneinfo import ZoneInfo

BASE = 'https://ws.mapserver.transports.gouv.qc.ca/swtq?service=wfs&version=2.0.0&request=getfeature&srsname=EPSG:4326&outputformat=geojson&typename='
TZ = ZoneInfo('America/Montreal')
DAYS = {'lundi': 0, 'mardi': 1, 'mercredi': 2, 'jeudi': 3, 'vendredi': 4, 'samedi': 5, 'dimanche': 6}


def fetch(layer):
    err = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(BASE + layer, headers={'User-Agent': 'Mozilla/5.0 TessyNav live events', 'Accept': 'application/json,*/*'})
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.load(r).get('features', [])
        except Exception as e:
            err = e
            print(layer, 'try', attempt + 1, 'failed:', e, flush=True)
            time.sleep(10)
    raise RuntimeError(layer + ' not available: ' + str(err))


def active_now(text, now):
    """True when a schedule in the text (French) covers this moment; True when the text gives no schedule.
    Understands: 'en tout temps', 'en continu', 'entre 22 h et 6 h (le lendemain)', 'du lundi au vendredi',
    'fin de semaine', and day names ('vendredi et samedi entre 23 h 30 et 8 h le lendemain')."""
    t = (text or '').lower().replace('\u00a0', ' ')
    if re.search(r'en tout temps|en continu', t) and not re.search(r'\bentre \d', t):
        return True
    m = re.search(r'entre (\d{1,2}) ?h ?(\d{2})? et (\d{1,2}) ?h ?(\d{2})?', t)
    days = set()
    if 'du lundi au vendredi' in t or 'du luni au vendredi' in t:
        days |= {0, 1, 2, 3, 4}
    elif re.search(r'du lundi au jeudi', t):
        days |= {0, 1, 2, 3}
    if 'fin de semaine' in t:
        days |= {5, 6}
    if not days:
        for name, d in DAYS.items():
            if re.search(r'\b' + name + r'\b', t):
                days.add(d)
    if not m and not days:
        return True                       # no schedule given: active for its whole date range
    wd, mins = now.weekday(), now.hour * 60 + now.minute
    if not m:
        return wd in days
    a = int(m.group(1)) * 60 + int(m.group(2) or 0)
    b = int(m.group(3)) * 60 + int(m.group(4) or 0)
    if a <= b:                            # same day, e.g. 7 h to 18 h
        return (not days or wd in days) and a <= mins < b
    # overnight, e.g. 22 h to 6 h the next day: tonight (if today is a listed day) or this morning (if yesterday was)
    if mins >= a:
        return not days or wd in days
    if mins < b:
        return not days or (wd - 1) % 7 in days
    return False


def kind_of(entrave, cause, text):
    s = (entrave + ' ' + text).lower().strip()
    if (cause or '').lower().startswith('accident') or 'accident' in s:
        return 'accident'
    if 'incendie' in (cause or '').lower():
        return 'hazard'
    if 'contresens' in s or re.search(r'fermeture de \d+ voies? sur|voies? (r[ée]tr[ée]cies?|d[ée]vi[ée]es?)|alternance|voie de virage', s):
        return 'lane'
    if re.search(r'route ferm|autoroute ferm|pont ferm|tunnel ferm|ferm[ée]e? compl|fermeture compl|acc[eè]s ferm|sortie ferm|^fermeture$|\bferm[ée]e?\b', s):
        return 'closed'
    return 'works'


def direction(d):
    d = (d or '').lower()
    if ' et ' in d or 'une direction' in d or not d:
        return ''
    return {'nord': 'N', 'sud': 'S', 'est': 'E', 'ouest': 'W'}.get(d.strip(), '')


def simplify(coords, keep=40):
    step = max(1, (len(coords) + keep - 1) // keep)
    pts = coords[::step]
    if coords and pts[-1] != coords[-1]:
        pts.append(coords[-1])
    flat = []
    for lng, lat in pts:
        flat += [round(lng, 6), round(lat, 6)]
    return flat


EN_ENTRAVE = [(r'^fermeture$', 'Road closed'), (r'fermeture de (\d+) voies? sur (\d+)', r'\1 of \2 lanes closed'),
              (r'circulation en alternance', 'Alternating traffic'), (r'circulation à contresens', 'Contraflow traffic'),
              (r'accès fermé', 'Access closed'), (r'sortie fermée', 'Exit closed')]
EN_CAUSE = {'accident': 'Accident', 'travaux': 'Road work', 'incendie': 'Fire', 'inspection': 'Inspection', 'mesures préventives': 'Preventive measures',
            'bris de la structure': 'Structural damage', 'événements spéciaux': 'Special event', 'déversement': 'Spill', 'travaux électriques': 'Electrical work',
            'travaux sur les services publics': 'Utility work'}


def english_event(p):
    e = (p.get('entrave') or '').strip()
    out = e
    for pat, rep in EN_ENTRAVE:
        if re.search(pat, e, re.I):
            out = re.sub(pat, rep, e, flags=re.I) if '\\' in rep else rep
            break
    c = EN_CAUSE.get((p.get('cause') or '').strip().lower(), (p.get('cause') or '').strip())
    where = re.sub(r'<br/?>', ' ', p.get('localisation') or '').strip()
    parts = [x for x in (out, c and '(' + c + ')', where) if x]
    return ' \u00b7 '.join(parts)[:220]


def main():
    now = datetime.datetime.now(TZ)
    out = []
    for f in fetch('ms:evenements'):
        p, g = f.get('properties') or {}, f.get('geometry') or {}
        loc, ent = (p.get('localisation') or ''), (p.get('entrave') or '')
        if g.get('type') != 'LineString' or not g.get('coordinates'):
            continue
        if re.search(r'\((ouvert|fermé)\)$', loc.strip(), re.I) or re.search(r'travers', ent + loc, re.I):
            continue                      # ferries
        if re.search(r'stationnement', ent, re.I) or (not ent and re.search(r'hauteur libre|limitations? de charge', loc, re.I)):
            continue                      # truck parking, height and weight limits
        out.append({'id': 'e' + str(p.get('identifiant')), 'k': kind_of(ent, p.get('cause'), ''), 'd': english_event(p),
                    'dir': direction(p.get('direction')), 'p': simplify(g['coordinates']), 'road': p.get('numeroRoute') or '', 'src': 'e'})
    for f in fetch('ms:chantiers_mtmdet'):
        p, g = f.get('properties') or {}, f.get('geometry') or {}
        if g.get('type') != 'LineString' or not g.get('coordinates'):
            continue
        ent = (p.get('entrave') or '').strip()
        if not ent or re.search(r'aucune fermeture de voie', ent, re.I):
            continue                      # nothing that affects cars (e.g. only oversize trucks)
        try:
            a = datetime.datetime.strptime(p.get('debut'), '%Y/%m/%d %H:%M:%S').replace(tzinfo=TZ)
            b = datetime.datetime.strptime(p.get('fin'), '%Y/%m/%d %H:%M:%S').replace(tzinfo=TZ)
        except Exception:
            continue
        if not (a <= now <= b) or not active_now(ent, now):
            continue                      # not today, or not at this hour
        en = [x.strip() for x in (p.get('descriptionAnglais') or '').replace('\r', '').split('\n') if x.strip()]
        text = ' \u00b7 '.join(en[1:4] if len(en) > 1 else en)[:220] or ent[:220]
        out.append({'id': 'w' + str(p.get('identifiant')), 'k': kind_of(ent, '', ''), 'd': text,
                    'dir': direction(p.get('direction')), 'p': simplify(g['coordinates']), 'road': p.get('routeAutoroute') or '', 'src': 'w'})
    res = {'t': now.isoformat(timespec='minutes'), 'source': 'Transports Québec (Québec 511), CC BY 4.0', 'e': out}
    with open('mtq.json', 'w') as fh:
        json.dump(res, fh, ensure_ascii=False, separators=(',', ':'))
    kinds = {}
    for x in out:
        kinds[x['k']] = kinds.get(x['k'], 0) + 1
    print('active now:', len(out), kinds, flush=True)


if __name__ == '__main__':
    main()
