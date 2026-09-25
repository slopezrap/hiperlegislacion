# Observatorio de la hiperlegislación

Cuántas normas se publican en España cada año, cuántas páginas ocupan y cuántas hay que corregir, con los datos abiertos del BOE desde 1979.

Web: https://slopezrap.github.io/hiperlegislacion/

## Cómo funciona

- `scripts/boe.py` descarga el sumario diario del BOE de su [API de datos abiertos](https://www.boe.es/datosabiertos/) y guarda:
  - `data/s1/AAAA.csv`: una fila por disposición de la Sección I (Disposiciones generales), con su tipo (ley, real decreto-ley, orden…), departamento, ámbito y páginas. Entre 1981 y 1986 incluye también las leyes y decretos-ley autonómicos de la antigua Sección V («Comunidades Autónomas»), marcados con su sección.
  - `data/dias/AAAA.csv`: por día, número de BOE y sección, cuántas disposiciones o anuncios hubo y cuántas páginas ocuparon.
- `scripts/build.py` agrega esos ficheros en `docs/data/`, que es lo que lee la web.
- Una GitHub Action ejecuta los dos scripts cada mañana y publica los datos nuevos.

Para reconstruirlo en local:

```
python scripts/boe.py 1979-01-01 2026-12-31   # la primera vez tarda alrededor de una hora
python scripts/build.py
python -m http.server -d docs
```

Solo usa la biblioteca estándar de Python.

## Limitaciones

- Solo cuenta lo que publica el BOE: no incluye los boletines autonómicos, provinciales ni el Diario Oficial de la UE.
- El tipo de norma se deduce del comienzo del título de cada disposición.
- Desde el 1 de enero de 2009 el BOE solo se publica en formato electrónico, a una columna y con cada disposición empezando en página nueva: las páginas de antes de 2009 no son comparables con las de después.
- La API del BOE devuelve un error persistente para algunos días; se listan en `data/dias_con_error.csv` y no se cuentan.

## Licencia y fuente

Fuente: Agencia Estatal Boletín Oficial del Estado. Datos derivados bajo licencia [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/deed.es); código bajo licencia MIT.

Proyecto de Sergio López Rapado, autor de [«Pragmatecmerismo»](https://slopezrap.github.io/pragmatecmerismo/).
