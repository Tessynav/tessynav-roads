"""TessyNav road signs builder v0 (first step: a look at the data only).
Reads the City of Montréal's road signs (excluding parking; open data, CC-BY 4.0, updated daily) and writes a short
report to signs/report.txt: the columns, how many signs of each kind, per borough, and a few example rows near
Nuns' Island, so the next step (floating signs in the app) can be built on what the file really contains.

  python3 signs.py
"""
import csv, io, json, os, sys, urllib.request, collections

PKG = 'https://donnees.montreal.ca/api/3/action/package_show?id=c5bf5e9c-528b-4c28-b52f-218215992e35'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'signs')


def get(url, tries=3):
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'tessynav-roads (github.com/Tessynav)'})
            with urllib.request.urlopen(req, timeout=300) as r:
                return r.read()
        except Exception as e:
            print('download failed', k + 1, e)
    raise SystemExit('could not download ' + url)


def main():
    os.makedirs(OUT, exist_ok=True)
    pkg = json.loads(get(PKG))['result']
    res = pkg['resources']
    lines = ['Dataset: ' + pkg.get('title', ''), 'Last modified: ' + str(pkg.get('metadata_modified')), '', 'Files:']
    for r in res:
        lines.append('  %s | %s | %s' % (r.get('name'), r.get('format'), r.get('url')))
    csv_url = next((r['url'] for r in res if (r.get('format') or '').upper() == 'CSV' and 'codification' not in (r.get('name') or '').lower()), None)
    if not csv_url:
        raise SystemExit('no CSV in the dataset')
    raw = get(csv_url)
    lines += ['', 'CSV: %s (%.1f MB)' % (csv_url, len(raw) / 1e6)]
    text = raw.decode('utf-8-sig', errors='replace')
    rows = list(csv.DictReader(io.StringIO(text)))
    lines += ['Rows: %d' % len(rows), 'Columns: ' + ', '.join(rows[0].keys() if rows else []), '']

    def col(*names):
        for n in names:
            if rows and n in rows[0]:
                return n
        return None
    cDesc = col('DESCRIPTION_RPA', 'DESCRIPTION')
    cCode = col('CODE_RPA', 'CODE')
    cCat = col('DESCRIPTION_CAT', 'CATEGORIE')
    cArr = col('NOM_ARROND', 'ARRONDISSEMENT')
    cLat, cLng = col('Latitude', 'LATITUDE', 'lat'), col('Longitude', 'LONGITUDE', 'lng')
    cArrow = col('FLECHE_PAN')
    cPole = col('POTEAU_ID_POT', 'POTEAU_ID')

    kinds = collections.Counter((r.get(cCode, ''), r.get(cDesc, '')) for r in rows)
    lines.append('Sign kinds (code | description | count), most common first:')
    for (code, desc), n in kinds.most_common(150):
        lines.append('  %s | %s | %d' % (code, desc, n))
    if cCat:
        lines += ['', 'Categories:']
        for k, n in collections.Counter(r.get(cCat, '') for r in rows).most_common(40):
            lines.append('  %s | %d' % (k, n))
    if cArr:
        lines += ['', 'Per borough:']
        for k, n in collections.Counter(r.get(cArr, '') for r in rows).most_common(40):
            lines.append('  %s | %d' % (k, n))
    if cArrow:
        lines += ['', 'Arrow codes (FLECHE_PAN):']
        for k, n in collections.Counter(r.get(cArrow, '') for r in rows).most_common(15):
            lines.append('  %s | %d' % (k, n))
    if cPole:
        per = collections.Counter(r.get(cPole) for r in rows)
        lines += ['', 'Signs per pole: ' + ', '.join('%d sign(s): %d poles' % (k, v) for k, v in sorted(collections.Counter(per.values()).items())[:8])]
    # examples on Nuns' Island (around 45.455-45.475, -73.56/-73.53)
    lines += ['', 'Examples on Nuns\' Island (all columns):']
    shown = 0
    for r in rows:
        try:
            la, lo = float(r.get(cLat) or 0), float(r.get(cLng) or 0)
        except ValueError:
            continue
        if 45.452 < la < 45.475 and -73.565 < lo < -73.53:
            lines.append('  ' + json.dumps(r, ensure_ascii=False))
            shown += 1
            if shown >= 40:
                break
    lines.append('  (%d shown)' % shown)
    open(os.path.join(OUT, 'report.txt'), 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    print('\n'.join(lines[:60]))


if __name__ == '__main__':
    main()
