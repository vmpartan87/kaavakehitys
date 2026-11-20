"""Vapaat toimitilat -> koordinaatit.

Lukee Kauppalehti Toimitilat -viennit (xlsx) ja paikantaa osoitteet
pääkaupunkiseudun osoiteluettelon (kartta.hel.fi avoindata:PKS_osoiteluettelo) avulla.
Tulos: raw/vapaat.json  [{osoite, kunta, kaupunginosa, m2, ilmoituksia, e, n, tarkkuus}]
"""
import json, re, sys, glob, unicodedata, collections
import openpyxl

CITIES = ('Helsinki', 'Espoo', 'Vantaa', 'Kauniainen')


def norm(s):
    s = unicodedata.normalize('NFC', str(s)).strip().lower()
    s = s.replace('.', ' ').replace('  ', ' ')
    return re.sub(r'\s+', ' ', s)


def load_addr(path='raw/osoitteet.json'):
    D = json.load(open(path))
    idx = {}
    for city, streets in D.items():
        m = {}
        for st, v in streets.items():
            pts = [(a[0], a[1] or a[0], a[2] + 25400000, a[3] + 6600000) for a in v['a']]
            m[norm(st)] = pts
            if v.get('s'):
                m.setdefault(norm(v['s']), pts)
        idx[city] = m
    return idx


ADDR_RE = re.compile(r'^(?P<st>.+?)\s+(?P<n1>\d+)\s*[a-zåäö]?(?:\s*[-–]\s*(?P<n2>\d+))?\b', re.I)


def parse(addr):
    a = str(addr).split(',')[0].strip()
    m = ADDR_RE.match(a)
    if not m:
        return norm(a), None, None
    n1 = int(m.group('n1')); n2 = int(m.group('n2')) if m.group('n2') else n1
    return norm(m.group('st')), n1, n2


def locate(idx, cities, st, n1, n2):
    for c in cities:
        pts = idx.get(c, {}).get(st)
        if not pts:
            continue
        if n1 is None:
            return None
        exact = [p for p in pts if p[0] <= n1 <= p[1] or n1 <= p[0] <= n2]
        if exact:
            e = sum(p[2] for p in exact) / len(exact); n = sum(p[3] for p in exact) / len(exact)
            return c, e, n, 'tarkka'
        near = sorted((abs(p[0] - n1), p) for p in pts if p[0] % 2 == n1 % 2)
        if near and near[0][0] <= 4:
            p = near[0][1]
            return c, p[2], p[3], 'lähin numero'
    return None


def read_xlsx(path):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    rows = list(wb['Kohteet'].iter_rows(values_only=True))
    hdr = next(i for i, r in enumerate(rows) if r and r[0] == 'Osoite')
    out = []
    for r in rows[hdr + 1:]:
        if not r or not r[0]:
            continue
        osoite, kosa, kunta, m2, lkm = (list(r) + [None] * 5)[:5]
        if kunta is None and kosa in CITIES:
            kunta, kosa = kosa, None
        out.append({'osoite': str(osoite).strip(), 'kaupunginosa': kosa, 'kunta': kunta,
                    'm2': float(m2) if isinstance(m2, (int, float)) else None, 'ilmoituksia': lkm or 1})
    return out


def main(paths):
    idx = load_addr()
    res, miss = [], []
    for p in paths:
        for row in read_xlsx(p):
            st, n1, n2 = parse(row['osoite'])
            cities = [row['kunta']] if row['kunta'] in CITIES else list(CITIES)
            hit = locate(idx, cities, st, n1, n2)
            if not hit and row['kunta'] in CITIES:
                hit = locate(idx, [c for c in CITIES if c != row['kunta']], st, n1, n2)
            if hit:
                c, e, n, tark = hit
                res.append({**row, 'kunta': c, 'e': round(e), 'n': round(n), 'tarkkuus': tark})
            else:
                miss.append(row)
    json.dump(res, open('raw/vapaat.json', 'w'), ensure_ascii=False)
    json.dump(miss, open('raw/vapaat_paikantamatta.json', 'w'), ensure_ascii=False)
    c = collections.Counter(r['tarkkuus'] for r in res)
    print(f'rivejä {len(res) + len(miss)}, paikannettu {len(res)} ({dict(c)}), ei paikannettu {len(miss)}')
    print('esim. paikantamatta:', [m['osoite'] for m in miss[:15]])


if __name__ == '__main__':
    main(sys.argv[1:] or glob.glob('raw/kauppalehti-*.xlsx'))
