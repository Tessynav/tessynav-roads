"""TessyNav parking rules builder v1 — "Can I park here?" (test: Verdun, including Nuns' Island).
Reads the City of Montréal's on-street parking signs (open data, CC-BY 4.0) and turns each sign's text into rules
the app can check against the time: no parking / no stopping / time limit / paid, on which days, hours and months,
and which way along the street (the arrow).

  python3 parking.py            download, read and write out/parking/<borough>.json, with a report of the sign texts
                                it couldn't read (so the reader can be taught them)
"""
import csv, io, json, os, re, sys, urllib.request, collections

SIGNS = 'https://donnees.montreal.ca/dataset/8ac6dd33-b0d3-4eab-a334-5a6283eb7940/resource/7f1d4ae9-1a12-46d7-953e-6b9c18c78680/download/signalisation_stationnement.csv'
BOROUGHS = {'verdun': ['Verdun']}          # (test area; more boroughs later)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'parking')   # (kept in the repository: the app reads it from there)

DAYS = {'LUN': 0, 'MAR': 1, 'MER': 2, 'JEU': 3, 'VEN': 4, 'SAM': 5, 'DIM': 6,
        'LUNDI': 0, 'MARDI': 1, 'MERCREDI': 2, 'JEUDI': 3, 'VENDREDI': 4, 'SAMEDI': 5, 'DIMANCHE': 6}
MONTHS = {'JAN': 1, 'JANV': 1, 'JANVIER': 1, 'FEV': 2, 'FEVR': 2, 'FEVRIER': 2, 'MARS': 3, 'AVR': 4, 'AVRIL': 4,
          'MAI': 5, 'JUIN': 6, 'JUIL': 7, 'JUILLET': 7, 'AOUT': 8, 'SEPT': 9, 'SEPTEMBRE': 9, 'OCT': 10,
          'OCTOBRE': 10, 'NOV': 11, 'NOVEMBRE': 11, 'DEC': 12, 'DECEMBRE': 12}


def norm(t):
    t = (t or '').upper()
    for a, b in (('É', 'E'), ('È', 'E'), ('Ê', 'E'), ('À', 'A'), ('Â', 'A'), ('Û', 'U'), ('Ô', 'O'), ('Î', 'I'), ('Ç', 'C')):
        t = t.replace(a, b)
    return re.sub(r'\s+', ' ', t.replace('.', ' ').replace(',', ' ')).strip()


def days_of(t):
    """the days a rule applies (0 = Monday), from "LUN AU VEN", "LUN MER VEN", "SAM ET DIM"... (None: every day)"""
    w = r'(LUNDI|MARDI|MERCREDI|JEUDI|VENDREDI|SAMEDI|DIMANCHE|LUN|MAR|MER|JEU|VEN|SAM|DIM)'
    m = re.search(w + r'\s*(?:AU|A|-)\s*' + w, t)
    if m:
        a, b = DAYS[m.group(1)], DAYS[m.group(2)]
        out, d = [], a
        while True:
            out.append(d)
            if d == b:
                break
            d = (d + 1) % 7
        return out
    found = [DAYS[x] for x in re.findall(r'\b' + w + r'\b', t)]
    return sorted(set(found)) or None


def hours_of(t):
    """time ranges [[start, end] in minutes]: "08H-09H", "9H30-11H", "07H A 09H30" (None: all day)"""
    out = []
    for m in re.finditer(r'(\d{1,2})\s*H\s*(\d{2})?\s*(?:-|A|À)\s*(\d{1,2})\s*H\s*(\d{2})?', t):
        a = int(m.group(1)) * 60 + int(m.group(2) or 0)
        b = int(m.group(3)) * 60 + int(m.group(4) or 0)
        if 0 <= a <= 1440 and 0 <= b <= 1440 and a != b:
            out.append([a, b])
    return out or None


def season_of(t):
    """the dates of the year a rule applies, as [month, day, month, day]: "1 AVRIL AU 1 DEC" (None: all year)"""
    mo = r'(JANVIER|JANV|JAN|FEVRIER|FEVR|FEV|MARS|AVRIL|AVR|MAI|JUIN|JUILLET|JUIL|AOUT|SEPTEMBRE|SEPT|OCTOBRE|OCT|NOVEMBRE|NOV|DECEMBRE|DEC)'
    m = re.search(r'(\d{1,2})\s*(?:ER)?\s*' + mo + r'\s*(?:AU|A|-)\s*(\d{1,2})\s*(?:ER)?\s*' + mo, t)
    if m:
        return [MONTHS[m.group(2)], int(m.group(1)), MONTHS[m.group(4)], int(m.group(3))]
    m = re.search(r'\b' + mo + r'\s*(?:AU|A|-)\s*' + mo + r'\b', t)
    if m and m.group(1) not in ('MAR',):
        return [MONTHS[m.group(1)], 1, MONTHS[m.group(2)], 31]
    return None


def parse(desc):
    """one sign's text -> a rule {k: kind, d: days, h: hours, s: season, m: minutes, z: permit zone}, or None
    kinds: np = no parking, ns = no stopping, lim = time limit, pay = paid parking, perm = permit holders only"""
    t = norm(desc)
    if not t:
        return None
    r = {}
    if t.startswith('\\A') or t.startswith('A ') and 'ARRET' in t or 'ARRET INTERDIT' in t:
        r['k'] = 'ns'
    elif t.startswith('\\P') or 'STAT INT' in t or 'STATIONNEMENT INTERDIT' in t:
        r['k'] = 'np'
    elif 'TARIF' in t or 'PAYANT' in t or re.search(r'\bP\s*\$', t):
        r['k'] = 'pay'
    elif re.match(r'^P\b', t) or 'STATIONNEMENT' in t:
        mm = re.search(r'(\d{1,3})\s*MIN', t)
        hh = re.search(r'\bP\s*(\d)\s*H\b|(\d)\s*HEURES?', t)
        if mm:
            r['k'], r['m'] = 'lim', int(mm.group(1))
        elif hh:
            r['k'], r['m'] = 'lim', 60 * int(hh.group(1) or hh.group(2))
        elif re.search(r'\bS\d{1,3}[A-Z]?\b|VIGNETTE|RESERVE|PERMIS', t):
            r['k'] = 'perm'
        else:
            r['k'] = 'ok'
    else:
        return None
    z = re.search(r'\b(S\d{1,3}[A-Z]?)\b', t)
    if z:
        r['z'] = z.group(1)
        if 'EXCEPTE' in t or 'SAUF' in t:
            r['x'] = 1        # (the rule doesn't apply to that permit zone)
    d, h, s = days_of(t), hours_of(t), season_of(t)
    if d:
        r['d'] = d
    if h:
        r['h'] = h
    if s:
        r['s'] = s
    if 'EN TOUT TEMPS' in t or '24H' in t:
        r.pop('h', None); r.pop('d', None)
    return r


def main():
    os.makedirs(OUT, exist_ok=True)
    print('downloading the parking signs...', flush=True)
    raw = urllib.request.urlopen(SIGNS, timeout=300).read().decode('utf-8-sig', 'replace')
    rows = list(csv.DictReader(io.StringIO(raw)))
    print('signs in Montréal: %d' % len(rows), flush=True)
    for name, boroughs in BOROUGHS.items():
        want = {b.upper() for b in boroughs}
        out, bad, n = [], collections.Counter(), 0
        for r in rows:
            if (r.get('NOM_ARROND') or '').strip().upper() not in want:
                continue
            try:
                lng, lat = float(r.get('Longitude') or 'x'), float(r.get('Latitude') or 'x')
            except ValueError:
                continue
            n += 1
            desc = r.get('DESCRIPTION_RPA') or ''
            rule = parse(desc)
            if rule is None:
                bad[norm(desc)] += 1
                continue
            try:
                arrow = int(float(r.get('FLECHE_PAN') or 0))
            except ValueError:
                arrow = 0
            out.append([round(lng, 6), round(lat, 6), arrow, rule, desc.strip()[:80], int(float(r.get('POTEAU_ID_POT') or 0))])
        with open(os.path.join(OUT, name + '.json'), 'w') as fh:
            json.dump({'v': 1, 'area': name, 'src': 'Ville de Montréal, Signalisation (stationnement sur rue), CC-BY 4.0', 'signs': out}, fh, separators=(',', ':'))
        print('%s: %d signs, read %d (%.0f%%), not understood %d' % (name, n, len(out), 100.0 * len(out) / max(1, n), sum(bad.values())), flush=True)
        print('most common sign texts not understood (to teach the reader):', flush=True)
        for t, c in bad.most_common(40):
            print('  %5d  %s' % (c, t), flush=True)


if __name__ == '__main__':
    main()
