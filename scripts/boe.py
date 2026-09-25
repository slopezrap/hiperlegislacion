"""Descarga y resume los sumarios diarios del BOE (API de datos abiertos).

Uso:
  python scripts/boe.py 2024-01-01 2024-12-31   # rango de fechas
  python scripts/boe.py --update                # desde el último día guardado hasta hoy

Genera, por año:
  data/s1/AAAA.csv    una fila por disposición de la Sección I (Disposiciones generales) y, entre 1981 y 1986,
                      por cada ley o decreto-ley de la antigua Sección V (Comunidades Autónomas)
  data/dias/AAAA.csv  una fila por día, diario y sección: nº de anuncios/disposiciones y páginas
"""
import csv, datetime as dt, gzip, json, os, re, sys, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, 'cache')
ERRORS = os.path.join(ROOT, 'data', 'dias_con_error.csv')
API = 'https://www.boe.es/datosabiertos/api/boe/sumario/{}'
S1_COLS = ['fecha', 'diario', 'seccion', 'id', 'departamento', 'ambito', 'tipo', 'pag_ini', 'pag_fin', 'titulo']
RANGO_LEY_AUTONOMICO = {'Ley', 'Decreto Legislativo', 'Decreto-ley'}
DIAS_COLS = ['fecha', 'diario', 'seccion', 'n', 'paginas']


ERROR = {'error': True}


def aslist(x):
    return x if isinstance(x, list) else ([] if x is None else [x])


def children(node, key):
    """Hijos `key` de un nodo del sumario; a veces la API los anida bajo «texto»."""
    if not isinstance(node, dict):
        return []
    if key in node:
        return aslist(node[key])
    return aslist((node.get('texto') or {}).get(key)) if isinstance(node.get('texto'), dict) else []


def fetch(day):
    """Devuelve el JSON del sumario de `day` (o None si no hubo BOE ese día). Usa caché local."""
    key = day.strftime('%Y%m%d')
    path = os.path.join(CACHE, key[:4], key + '.json.gz')
    if os.path.exists(path):
        with gzip.open(path, 'rt', encoding='utf-8') as f:
            txt = f.read()
        return json.loads(txt) if txt else None
    for attempt in range(5):
        try:
            req = urllib.request.Request(API.format(key), headers={'Accept': 'application/json', 'User-Agent': 'observatorio-hiperlegislacion'})
            with urllib.request.urlopen(req, timeout=60) as r:
                txt = r.read().decode('utf-8')
            break
        except urllib.error.HTTPError as e:
            if e.code == 404:
                txt = ''
                break
            time.sleep(2 ** attempt)
        except Exception:
            time.sleep(2 ** attempt)
    else:
        return ERROR  # la API falla de forma persistente con algunos días; se registran aparte
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with gzip.open(path + '.tmp', 'wt', encoding='utf-8') as f:
        f.write(txt)
    os.replace(path + '.tmp', path)
    return json.loads(txt) if txt else None


def find_items(node):
    if isinstance(node, list):
        for n in node:
            yield from find_items(n)
    elif isinstance(node, dict):
        if 'identificador' in node and 'titulo' in node:
            yield node
            return
        for v in node.values():
            if isinstance(v, (dict, list)):
                yield from find_items(v)


AUTONOMICO = re.compile(r'COMUNIDAD|COMUNITAT|CIUDAD AUT|ILLES BALEARS|PRINCIPADO|REGI[OÓ]N DE MURCIA', re.I)
JUDICIAL = re.compile(r'TRIBUNAL|CONSEJO GENERAL DEL PODER JUDICIAL|AUDIENCIA NACIONAL|JUZGADO', re.I)
EXTERIORES = re.compile(r'ASUNTOS EXTERIORES', re.I)
TIPOS = [  # (tipo, patrón al inicio del título); el orden importa
    ('Corrección', r'correcci[oó]n (de )?(errores|erratas)'),
    ('Ley Orgánica', r'ley org[aá]nica'),
    ('Real Decreto-ley', r'real decreto[- ]ley'),
    ('Real Decreto Legislativo', r'real decreto legislativo'),
    ('Ley', r'ley(es)?\b'),
    ('Decreto-ley', r'decreto[- ]ley'),
    ('Decreto Legislativo', r'decreto legislativo'),
    ('Real Decreto', r'real decreto\b'),
    ('Decreto', r'decreto\b'),
    ('Orden', r'orden\b'),
    ('Resolución', r'resoluci[oó]n\b'),
    ('Instrucción o circular', r'(instrucci[oó]n|circular)\b'),
    ('Tratado o acuerdo internacional', r'(instrumento|canje|convenio|acuerdo|tratado|protocolo|enmiendas?|modificaci[oó]n|modificaciones|adenda|acta|texto|estatutos|decisi[oó]n|reglamento|aplicaci[oó]n provisional|memorando|declaraci[oó]n|entrada en vigor)\b'),
]
TIPOS = [(t, re.compile(p, re.I)) for t, p in TIPOS]


def tipo(titulo, departamento=''):
    t = titulo.strip()
    if JUDICIAL.search(departamento) and not re.match(r'correcci', t, re.I):
        return 'Resolución judicial'
    for name, pat in TIPOS:
        if pat.match(t):
            if name == 'Tratado o acuerdo internacional' and not EXTERIORES.search(departamento):
                return 'Otras'
            return name
    return 'Otras'


def union_pages(intervals):
    total, cur_s, cur_e = 0, None, None
    for s, e in sorted(intervals):
        if cur_e is None or s > cur_e:
            if cur_e is not None:
                total += cur_e - cur_s + 1
            cur_s, cur_e = s, e
        else:
            cur_e = max(cur_e, e)
    if cur_e is not None:
        total += cur_e - cur_s + 1
    return total


def summarize(day, d):
    """Devuelve (filas_s1, filas_dias) de un sumario."""
    s1, dias = [], []
    fecha = day.isoformat()
    for di in children(d['data']['sumario'], 'diario'):
        num = di.get('numero', '')
        for sec in children(di, 'seccion'):
            code = sec.get('codigo', '?')
            ccaa_sec = 'COMUNIDADES AUT' in (sec.get('nombre') or '').upper()
            n, iv = 0, []
            for dep in children(sec, 'departamento'):
                dname = (dep.get('nombre') or '').strip()
                for it in find_items(dep):
                    n += 1
                    pdf = it.get('url_pdf') if isinstance(it.get('url_pdf'), dict) else {}
                    try:
                        pi, pf = int(pdf.get('pagina_inicial') or 0), int(pdf.get('pagina_final') or 0)
                    except ValueError:
                        pi = pf = 0
                    if pi and pf >= pi:
                        iv.append((pi, pf))
                    if code == '1' or ccaa_sec:
                        titulo = ' '.join((it.get('titulo') or '').split())
                        t = tipo(titulo, dname)
                        if ccaa_sec and t not in RANGO_LEY_AUTONOMICO:
                            continue
                        s1.append([fecha, num, code, it.get('identificador'), dname,
                                   'autonómico' if ccaa_sec or AUTONOMICO.search(dname) else 'estatal',
                                   t, pi or '', pf or '', titulo])
            dias.append([fecha, num, code, n, union_pages(iv)])
    return s1, dias


def read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, newline='', encoding='utf-8') as f:
        return list(csv.reader(f))[1:]


def write_csv(path, cols, rows):
    rows.sort(key=lambda r: (r[0], r[1], r[2]))
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(cols)
        w.writerows(rows)


def run(start, end, workers=6):
    days = [start + dt.timedelta(i) for i in range((end - start).days + 1)]
    by_year = {}
    for day in days:
        by_year.setdefault(day.year, []).append(day)
    for year, ydays in sorted(by_year.items(), reverse=True):  # los años recientes primero
        t0 = time.time()
        with ThreadPoolExecutor(workers) as ex:
            results = list(ex.map(lambda x: (x, fetch(x)), ydays))
        done = {day.isoformat() for day in ydays}
        new_s1, new_dias, failed = [], [], []
        for day, d in results:
            if d is ERROR:
                failed.append(day.isoformat())
            elif d:
                a, b = summarize(day, d)
                new_s1 += a
                new_dias += b
        errors = set(r[0] for r in read_csv(ERRORS) if r[0] not in done) | set(failed)
        with open(ERRORS, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f, lineterminator='\n')
            w.writerow(['fecha'])
            w.writerows([e] for e in sorted(errors))
        p1 = os.path.join(ROOT, 'data', 's1', f'{year}.csv')
        p2 = os.path.join(ROOT, 'data', 'dias', f'{year}.csv')
        s1 = [r for r in read_csv(p1) if r[0] not in done] + new_s1
        dias = [r for r in read_csv(p2) if r[0] not in done] + new_dias
        write_csv(p1, S1_COLS, s1)
        write_csv(p2, DIAS_COLS, dias)
        print(f'{year}: {len(ydays)} días, {sum(1 for _, d in results if d and d is not ERROR)} con BOE, '
              f'{len(new_s1)} disposiciones generales, {len(failed)} días con error de la API '
              f'({time.time() - t0:.0f}s)', flush=True)


if __name__ == '__main__':
    if sys.argv[1:] == ['--update']:
        files = sorted(os.listdir(os.path.join(ROOT, 'data', 'dias')))
        last = max(r[0] for r in read_csv(os.path.join(ROOT, 'data', 'dias', files[-1])))
        start = dt.date.fromisoformat(last) - dt.timedelta(days=3)  # re-lee los últimos días por si hubo extraordinarios
        run(start, dt.date.today())
    else:
        run(dt.date.fromisoformat(sys.argv[1]), dt.date.fromisoformat(sys.argv[2]))
