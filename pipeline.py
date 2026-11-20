"""Kaavapotentiaali – analyysiputki.

Lukee selaimella haetut raakatiedot (raw/*.json, EPSG:3879) ja tuottaa
ehdokastontit + taustatasot WGS84-muodossa portaalille (out/data.json).
"""
import json, math, collections
from pyproj import Transformer
from shapely.geometry import Polygon, MultiPolygon, Point, shape
from shapely.strtree import STRtree



CFG = json.load(open('config.json'))
T = Transformer.from_crs(3879, 4326, always_xy=True)


def unpack(g):
    """Delta-koodattu [[ring-flat]] -> [[[x,y],...]]"""
    polys = []
    for poly in g:
        rings = []
        for flat in poly:
            pts, x, y = [], 0, 0
            for i in range(0, len(flat), 2):
                x += flat[i]; y += flat[i + 1]
                pts.append((x, y))
            rings.append(pts)
        polys.append(rings)
    return polys


def to_shape(polys):
    ps = []
    for rings in polys:
        if len(rings[0]) < 4:
            continue
        p = Polygon(rings[0], [r for r in rings[1:] if len(r) >= 4])
        if not p.is_valid:
            p = p.buffer(0)
        ps.append(p)
    if not ps:
        return None
    return ps[0] if len(ps) == 1 else MultiPolygon([q for p in ps for q in (p.geoms if hasattr(p, 'geoms') else [p])])


def wgs_coords(geom, prec=6):
    def ring(r):
        xs, ys = T.transform([c[0] for c in r], [c[1] for c in r])
        return [[round(a, prec), round(b, prec)] for a, b in zip(xs, ys)]
    if geom.geom_type == 'Polygon':
        return [[ring(geom.exterior.coords)] + [ring(i.coords) for i in geom.interiors]]
    out = []
    for p in geom.geoms:
        out += wgs_coords(p, prec)
    return out


def wgs_line(coords, prec=5):
    xs, ys = T.transform([c[0] for c in coords], [c[1] for c in coords])
    return [[round(a, prec), round(b, prec)] for a, b in zip(xs, ys)]


# ---------- rakennusten käyttötarkoitusluokat ----------
HEL_KT = CFG['hel_rakennusluokat']


def use_group(code, label):
    """Palauttaa (ryhmä, selite). Ryhmät: asuin, liike, toimisto, pysakointi, teollisuus, varasto, julkinen, muu."""
    c = (code or '').strip()
    lab = label or ''
    if len(c) == 3:  # Helsinki, luokitus 1994
        lab = HEL_KT.get(c, c)
        if c[0] == '0': g = 'asuin'
        elif c[:2] in ('11', '12', '14'): g = 'liike'
        elif c[:2] == '15': g = 'toimisto'
        elif c in ('162', '163'): g = 'pysakointi'
        elif c[0] == '6': g = 'teollisuus'
        elif c[0] == '7' and c[:2] in ('71',): g = 'varasto'
        elif c[0] in '2345': g = 'julkinen'
        else: g = 'muu'
        return g, lab
    m = c[:4] if len(c) >= 4 else (lab[:4] if lab[:4].isdigit() else '')
    if lab[:4].isdigit():
        lab = lab[5:]
    if not m:
        return 'muu', lab or 'ei tietoa'
    if m.startswith('01') or m.startswith('02'): g = 'asuin'
    elif m.startswith('03'): g = 'liike'
    elif m.startswith('04'): g = 'toimisto'
    elif m in ('0513', '0514'): g = 'pysakointi'
    elif m.startswith('09') or m.startswith('10') or m.startswith('11'): g = 'teollisuus'
    elif m.startswith('12'): g = 'varasto'
    elif m[:2] in ('06', '07', '08'): g = 'julkinen'
    else: g = 'muu'
    return g, lab


def summarize_buildings(bs, kunta):
    """bs-rivit kunnittain: HEL [ka, vuosi, koodi, kerrosluku, luokka2018, kokala],
    ESP [ka, vuosi, koodi, kerrosluku, selite, kiint, osoite], VAN [ka, vuosi, selite, kerrosluku, kiint, osoite]"""
    tot = 0; yw = 0; ywn = 0; years = []; maxk = 0
    groups = collections.Counter(); labels = collections.Counter(); addrs = []
    for b in bs:
        ka = b[0] or 0
        yr = b[1] if b[1] and b[1] > 1700 else None
        if kunta == 'Vantaa':
            g, lab = use_group(None, b[2])
            if len(b) > 5 and b[5]: addrs.append(b[5])
        elif kunta == 'Espoo':
            g, lab = use_group(b[2], b[4])
            if len(b) > 6 and b[6].strip(): addrs.append(b[6].strip())
        else:
            g, lab = use_group(b[2], None)
        if g in ('muu',) and ka < 50:
            continue  # talousrakennukset yms. eivät määritä käyttöä
        tot += ka
        if yr:
            years.append(yr)
            if ka:
                yw += yr * ka; ywn += ka
        if b[3]:
            maxk = max(maxk, b[3])
        groups[g] += max(ka, 1)
        labels[lab] += max(ka, 1)
    yavg = round(yw / ywn) if ywn else (round(sum(years) / len(years)) if years else None)
    gsum = sum(groups.values()) or 1
    return {
        'kerrosala_nyt': int(tot),
        'rak_lkm': len(bs),
        'valm_vuosi': yavg,
        'vanhin': min(years) if years else None,
        'kerroksia_max': maxk or None,
        'kaytto': [[k, round(v / gsum, 2)] for k, v in groups.most_common(3)],
        'kaytto_selite': [k for k, _ in labels.most_common(3)],
        'osoite_rak': addrs[0] if addrs else None,
    }


def main():
    E = CFG['yk_tehokkuus']           # kunta -> merkintä -> tavoitetehokkuus (AK)
    YK_SELITE = CFG['yk_selitteet']
    ctx = json.load(open('raw/ctx.json'))

    # asemat
    stations = []
    for typ, arr in ctx['asemat'].items():
        for s in arr:
            stations.append((typ, s['n'], Point(s['g'][:2])))
    st_tree = STRtree([s[2] for s in stations])

    # kaupunginosanimet
    names = [(n['n'], Point(n['g'][:2])) for n in ctx['bg']['nimet'] if n.get('n')]
    nm_tree = STRtree([p for _, p in names])

    van = json.load(open('raw/van.json'))
    van_kos = [(k['n'], to_shape(k['g'])) for k in van['kos']]

    # vireillä olevat kaavat
    vir = []
    for v in ctx['hel_vireilla']:
        g = v['g']; polys = [g['coordinates']] if g['type'] == 'Polygon' else g['coordinates']
        s = to_shape(polys)
        if s is not None:
            vir.append({'kunta': 'Helsinki', 'tunnus': v['k'], 'nimi': None, 'vaihe': v.get('h'),  'url': None, 'geom': s})
    esp = json.load(open('raw/esp.json'))
    for v in esp['vir']:
        s = to_shape(v['g'])
        if s is not None:
            vir.append({'kunta': 'Espoo', 'tunnus': v['k'], 'nimi': v.get('n'), 'vaihe': v.get('vaihe'), 'url': v.get('www'), 'geom': s})
    for v in van['vir']:
        s = to_shape(v['g'])
        if s is not None:
            vir.append({'kunta': 'Vantaa', 'tunnus': v['k'], 'nimi': v.get('n'), 'vaihe': v.get('vaihe'), 'url': v.get('www'), 'geom': s})
    vir_tree = STRtree([v['geom'] for v in vir])

    # vapaat toimitilat (Kauppalehti Toimitilat -vienti, paikannettu vapaat.py:llä)
    import os
    vapaat = json.load(open('raw/vapaat.json')) if os.path.exists('raw/vapaat.json') else []
    vap_tree = STRtree([Point(v['e'], v['n']) for v in vapaat]) if vapaat else None

    recs = []

    def add(kunta, rid, kaava, ktk, ktk_tark, osoite, ala, ro, yk, bs, polys):
        geom = to_shape(polys)
        if geom is None or geom.area < 100:
            return
        ala = ala or geom.area
        # yleiskaava-osuudet: tuntemattomat pois nimittäjästä
        known = {k: v for k, v in (yk or {}).items() if k not in ('?', '-', 'X')}
        ks = sum(known.values())
        Ek = E.get(kunta, {})
        if kunta == 'Espoo':
            yk_tila = 'ei_tietoa'
            res_share = None
            e_target = CFG['espoo_oletustehokkuus']
            yk_main = None
        else:
            yk_tila = 'ok' if ks > 0 else 'ei_tietoa'
            res_share = sum(v for k, v in known.items() if k in Ek) / ks if ks else 0
            e_target = (sum(v * Ek[k] for k, v in known.items() if k in Ek) / ks) if ks else 0
            yk_main = max(known.items(), key=lambda kv: kv[1])[0] if known else None
        potential = ala * e_target
        bsum = summarize_buildings(bs, kunta)
        c = geom.centroid
        # lähin asema
        idx = st_tree.nearest(c)
        st = stations[idx]
        dist = c.distance(st[2])
        # kaupunginosa
        kos = None
        if kunta == 'Vantaa':
            for n, s in van_kos:
                if s is not None and s.contains(c):
                    kos = n; break
        if not kos:
            kos = names[nm_tree.nearest(c)][0]
        # vireillä
        hits = [vir[i] for i in vir_tree.query(geom, predicate='intersects')]
        hits = [h for h in hits if h['geom'].intersection(geom).area > 0.2 * geom.area]
        vh = [vapaat[i] for i in vap_tree.query(geom.buffer(CFG.get('vuokra_puskuri_m', 15)))] if vap_tree is not None else []
        # sama tila voi olla ilmoitettu eri osoitekirjoitusasuilla tai osiin jaettuna:
        # lasketaan osoitepisteittäin suurin ilmoitettu tila ja summataan pisteet
        per_pt = {}
        for v in vh:
            k = (round(v['e'] / 10), round(v['n'] / 10))
            per_pt[k] = max(per_pt.get(k, 0), v['m2'] or 0)
        vuokra_m2 = int(sum(per_pt.values()))
        cur = bsum['kerrosala_nyt']
        ref = max(ro or 0, potential)
        flags = {
            'vanha': bool(bsum['valm_vuosi'] and bsum['valm_vuosi'] < CFG['vanha_raja']),
            'matala': bool(ref and cur < CFG['matala_osuus'] * ref and cur >= CFG['tyhja_osuus'] * ala),
            'tyhja': bool(cur < CFG['tyhja_osuus'] * ala or any(k == 'pysakointi' and v >= 0.5 for k, v in bsum['kaytto'])),
            'vuokra': bool(vh),
        }
        x, y = T.transform(c.x, c.y)
        recs.append({
            'id': rid, 'kunta': kunta, 'kaupunginosa': kos, 'kaava': kaava,
            'ak': ktk, 'ak_tarkka': ktk_tark, 'osoite': osoite or bsum.pop('osoite_rak', None),
            'ala': int(round(ala)), 'rakennusoikeus': ro,
            'yk_tila': yk_tila, 'yk_paa': yk_main, 'yk_selite': YK_SELITE.get(kunta, {}).get(yk_main) if yk_main else None,
            'yk_osuudet': {k: round(v / ks, 2) for k, v in sorted(known.items(), key=lambda kv: -kv[1])} if ks else {},
            'asuin_osuus': round(res_share, 2) if res_share is not None else None,
            'e_tavoite': round(e_target, 2),
            'potentiaali': int(round(potential / 100.0) * 100),
            'asema': st[1], 'asema_tyyppi': st[0], 'asema_m': int(round(dist)),
            'vuokra_m2': vuokra_m2, 'vuokra_lkm': len(vh),
            'vuokra_osuus': round(vuokra_m2 / cur, 2) if cur else None,
            'vuokra': [{'o': v['osoite'], 'm2': v['m2'], 'n': v['ilmoituksia']} for v in sorted(vh, key=lambda v: -(v['m2'] or 0))][:12],
            'vireilla': [{'tunnus': h['tunnus'], 'nimi': h['nimi'], 'vaihe': h['vaihe'], 'url': h['url']} for h in hits][:3],
            'liput': flags,
            'lon': round(x, 6), 'lat': round(y, 6), 'e': int(c.x), 'n': int(c.y),
            'geom': wgs_coords(geom.simplify(1.0), 6),
            **{k: v for k, v in bsum.items() if k != 'osoite_rak'},
        })

    for o in json.load(open('raw/hel.json')):
        add('Helsinki', o['id'], o.get('kaava'), o['ktk'], o['ktk'], o.get('os'), o.get('ala'), o.get('ro'), o['yk'], o['b'], o['g'] if isinstance(o['g'][0][0][0], list) else unpack(o['g']))
    for i, o in enumerate(esp['c']):
        add('Espoo', f"ESP-{o.get('kaava','').replace(' ','')}-{i}", o.get('kaava'), 'K' if o['base'].startswith('K') else 'T', o['kt'], None, o.get('ala'), None, {}, o.get('b') or [], unpack(o['g']))
    for i, o in enumerate(van['c']):
        add('Vantaa', f"VAN-{i}", None, o['ktk'], o['ktk'], None, o.get('ala'), None, o['yk'], o['b'], unpack(o['g']))

    # pisteytys
    W = CFG['pisteet']
    for r in recs:
        s = 0
        s += min(r['potentiaali'] / W['potentiaali_taysi'], 1) * W['potentiaali']
        if r['asuin_osuus'] is None:
            s += W['yk_tuntematon']
        else:
            s += r['asuin_osuus'] * W['yk']
        f = r['liput']
        s += min((W['vanha'] if f['vanha'] else 0) + (W['matala'] if f['matala'] else 0) + (W['tyhja'] if f['tyhja'] else 0) + (W['vuokra'] if f.get('vuokra') else 0), W['vajaa_max'])
        d = r['asema_m']
        s += W['asema'] if d <= 500 else W['asema'] * 0.7 if d <= 800 else W['asema'] * 0.4 if d <= 1200 else 0
        r['pisteet'] = int(round(s))

    recs.sort(key=lambda r: -r['pisteet'])

    # taustatasot
    def poly_layer(feats, tol):
        out = []
        for f in feats:
            g = f['g'] if 'g' in f else f
            if not g:
                continue
            polys = [g['coordinates']] if g['type'] == 'Polygon' else g['coordinates']
            s = to_shape(polys)
            if s is None:
                continue
            s = s.simplify(tol)
            out.append({'p': f.get('p', {}), 'c': wgs_coords(s, 5)})
        return out

    def line_layer(feats, key='g'):
        out = []
        for f in feats:
            g = f[key]
            if not g:
                continue
            lines = [g['coordinates']] if g['type'] == 'LineString' else g['coordinates']
            for l in lines:
                if len(l) >= 2:
                    out.append({'c': f.get('c'), 'l': wgs_line(l)})
        return out

    bg = {
        'kunnat': poly_layer(ctx['bg']['kunnat'], 20),
        'meri': poly_layer(ctx['bg']['meri'], 20),
        'tiet': line_layer(ctx['bg']['tiet']),
        'rata': line_layer(ctx['bg']['rata']),
        'metro': line_layer(ctx['bg']['metro']),
        'nimet': [{'n': n['n'], 'll': wgs_line([n['g'][:2]])[0]} for n in ctx['bg']['nimet'] if n.get('n')],
        'asemat': [{'t': t, 'n': n, 'll': wgs_line([(p.x, p.y)])[0]} for t, n, p in stations],
        'vireilla': [{'kunta': v['kunta'], 'tunnus': v['tunnus'], 'nimi': v['nimi'], 'vaihe': v['vaihe'], 'url': v['url'], 'c': wgs_coords(v['geom'].simplify(3), 5)} for v in vir],
    }
    json.dump({'paivitetty': CFG['paivitetty'], 'vuokra_lahde': CFG.get('vuokra_lahde'), 'asetukset': {k: CFG[k] for k in ('yk_tehokkuus', 'yk_selitteet', 'pisteet', 'vanha_raja', 'matala_osuus', 'tyhja_osuus', 'espoo_oletustehokkuus')}, 'kohteet': recs, 'tausta': bg},
              open('out/data.json', 'w'), ensure_ascii=False, separators=(',', ':'))
    c = collections.Counter((r['kunta'], r['potentiaali'] >= 2500) for r in recs)
    print('kohteita', len(recs), dict(c))


if __name__ == '__main__':
    main()
