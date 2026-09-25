"""Agrega data/s1 y data/dias en los ficheros que usa la web (docs/data).

Uso: python scripts/build.py
"""
import csv, datetime as dt, glob, json, os, re
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'docs', 'data')
FIRST_YEAR = 1979

CCAA = [  # (nombre corto, patrón sobre el departamento del BOE)
    ('Andalucía', r'ANDALUC'), ('Aragón', r'ARAG'), ('Asturias', r'ASTURIAS'),
    ('Illes Balears', r'BALEAR'), ('Canarias', r'CANARIAS'), ('Cantabria', r'CANTABRIA'),
    ('Castilla-La Mancha', r'CASTILLA[- ]LA MANCHA'), ('Castilla y León', r'CASTILLA Y LE'),
    ('Cataluña', r'CATALU'), ('Comunitat Valenciana', r'VALENCIA'), ('Extremadura', r'EXTREMADURA'),
    ('Galicia', r'GALICIA'), ('Madrid', r'MADRID'), ('Murcia', r'MURCIA'), ('Navarra', r'NAVARRA'),
    ('País Vasco', r'PA[IÍ]S VASCO|EUSKADI'), ('La Rioja', r'RIOJA'), ('Ceuta', r'CEUTA'), ('Melilla', r'MELILLA'),
]
CCAA = [(n, re.compile(p, re.I)) for n, p in CCAA]

# Qué cuenta como «norma con rango de ley»
RANGO_LEY = {
    'Ley Orgánica': 'Leyes estatales',
    'Ley': None,  # estatal o autonómica según el departamento
    'Real Decreto Legislativo': 'Leyes estatales',
    'Real Decreto-ley': 'Reales decretos-ley',
    'Decreto-ley': 'Decretos-ley autonómicos',
    'Decreto Legislativo': 'Leyes autonómicas',
}
SERIES_LEY = ['Leyes estatales', 'Reales decretos-ley', 'Leyes autonómicas', 'Decretos-ley autonómicos']


def ccaa(dep):
    for name, pat in CCAA:
        if pat.search(dep):
            return name
    return None


def rango_ley(row):
    t = row['tipo']
    if t not in RANGO_LEY:
        return None
    if t == 'Ley':
        return 'Leyes autonómicas' if row['ambito'] == 'autonómico' else 'Leyes estatales'
    if t in ('Decreto-ley', 'Decreto Legislativo') and row['ambito'] != 'autonómico':
        return None
    return RANGO_LEY[t]


def load(pattern):
    rows = []
    for p in sorted(glob.glob(os.path.join(ROOT, 'data', pattern, '*.csv'))):
        with open(p, newline='', encoding='utf-8') as f:
            rows += list(csv.DictReader(f))
    return rows


def main():
    s1 = [r for r in load('s1') if int(r['fecha'][:4]) >= FIRST_YEAR]
    dias = [r for r in load('dias') if int(r['fecha'][:4]) >= FIRST_YEAR]
    last = max(r['fecha'] for r in dias)
    last_d = dt.date.fromisoformat(last)
    cur_year = last_d.year

    pag_s1, pag_total, n_s1, n_corr, n_normas = Counter(), Counter(), Counter(), Counter(), Counter()
    dias_boe = defaultdict(set)
    for r in dias:
        y = int(r['fecha'][:4])
        pag_total[y] += int(r['paginas'])
        dias_boe[y].add(r['fecha'])
        if r['seccion'] == '1':
            pag_s1[y] += int(r['paginas'])
    ley = defaultdict(Counter)
    ccaa_leyes = defaultdict(Counter)
    tipos = defaultdict(Counter)
    for r in s1:
        y = int(r['fecha'][:4])
        if r['seccion'] == '1':
            n_s1[y] += 1
            tipos[y][r['tipo']] += 1
            if r['tipo'] == 'Corrección':
                n_corr[y] += 1
            elif r['tipo'] != 'Resolución judicial':
                n_normas[y] += 1
        rl = rango_ley(r)
        if rl:
            ley[y][rl] += 1
            if rl in ('Leyes autonómicas', 'Decretos-ley autonómicos'):
                c = ccaa(r['departamento'])
                if c:
                    ccaa_leyes[c][y] += 1

    years = list(range(FIRST_YEAR, cur_year + 1))
    errores = []
    perr = os.path.join(ROOT, 'data', 'dias_con_error.csv')
    if os.path.exists(perr):
        with open(perr, newline='', encoding='utf-8') as f:
            errores = [r['fecha'] for r in csv.DictReader(f)]

    # Mismo periodo del año anterior (hasta el mismo día del año)
    def ytd(year):
        try:
            cutoff = last_d.replace(year=year).isoformat()
        except ValueError:  # 29 de febrero
            cutoff = (last_d - dt.timedelta(days=1)).replace(year=year).isoformat()
        start = f'{year}-01-01'
        p = sum(int(r['paginas']) for r in dias if r['seccion'] == '1' and start <= r['fecha'] <= cutoff)
        rows = [r for r in s1 if start <= r['fecha'] <= cutoff]
        leyes = Counter(rango_ley(r) for r in rows)
        rows = [r for r in rows if r['seccion'] == '1']
        return {
            'hasta': cutoff,
            'paginas_s1': p,
            'normas': sum(1 for r in rows if r['tipo'] not in ('Corrección', 'Resolución judicial')),
            'correcciones': sum(1 for r in rows if r['tipo'] == 'Corrección'),
            'rango_ley': sum(leyes[s] for s in SERIES_LEY),
        }

    complete = [y for y in years if y < cur_year]
    ten = complete[-10:]
    ccaa_rank = sorted(((c, sum(v[y] for y in ten)) for c, v in ccaa_leyes.items()), key=lambda x: -x[1])

    out = {
        'actualizado': last,
        'anio_en_curso': cur_year,
        'anios': years,
        'paginas_s1': [pag_s1[y] for y in years],
        'paginas_boe': [pag_total[y] for y in years],
        'disposiciones_s1': [n_s1[y] for y in years],
        'normas': [n_normas[y] for y in years],
        'correcciones': [n_corr[y] for y in years],
        'dias_con_boe': [len(dias_boe[y]) for y in years],
        'rango_ley': {s: [ley[y][s] for y in years] for s in SERIES_LEY},
        'ytd': {'actual': ytd(cur_year), 'anterior': ytd(cur_year - 1)},
        'ccaa_ultimos_10': {'desde': ten[0], 'hasta': ten[-1], 'ranking': ccaa_rank},
        'tipos': {str(y): dict(tipos[y]) for y in years},
        'dias_con_error': errores,
    }
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, 'observatorio.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'))

    # CSV anual descargable
    with open(os.path.join(OUT, 'observatorio_anual.csv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(['anio', 'paginas_disposiciones_generales', 'paginas_boe', 'disposiciones_generales',
                    'normas_sin_correcciones_ni_judiciales', 'correcciones_de_errores'] + SERIES_LEY + ['anio_completo'])
        for i, y in enumerate(years):
            w.writerow([y, out['paginas_s1'][i], out['paginas_boe'][i], out['disposiciones_s1'][i], out['normas'][i],
                        out['correcciones'][i]] + [out['rango_ley'][s][i] for s in SERIES_LEY] + [int(y < cur_year)])
    print(f'Datos hasta {last}: {len(s1)} disposiciones generales, {len(years)} años')


if __name__ == '__main__':
    main()
