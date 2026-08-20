# rendimientos_fuente — staging FHIS (goal-21068)

Tabla intermedia de **rendimientos** para EstimaStruct, construida desde la fuente
primaria aprobada por David (2026-08-15): **FHIS Manual de Rendimientos 2003-11**
(Crédito Banco Mundial 3443-HO), con **Suárez Salazar** como complemento de huecos.

> **Esto es STAGING, no producción.** Nada aquí escribe en el catálogo vivo
> (`fichas_v1.x.json` / SQLite versionada / Postgres). Poblar los valores reales
> de rendimiento en el catálogo requiere un **2º OK explícito de David**.

## Pipeline

```
D:\LLM\python\python.exe parse_fhis_index.py      # etapa 1-2: adquisición + parseo
D:\LLM\python\python.exe crosswalk_fhis_csi.py     # etapa 3: crosswalk CSI + cobertura
```

`parse_fhis_index.py` lee el índice FHIS descargado
(`C:\Users\consu\.openclaw\workspace\artifacts\fhis\quercusoft_listado.html`,
2204 actividades) y lo normaliza a:

- `data/fhis_actividad.csv` / `.json` — índice (código, descripción, unidad,
  capítulo, inhabilitada, fuente, año)
- `data/rendimientos_fuente.db` — SQLite staging con 2 tablas:
  - `fhis_actividad` (poblada: 2204 filas)
  - `rendimiento_fuente` (**creada pero vacía** — valores por recurso viven en el
    PDF escaneado; poblarla = paso gated)

`crosswalk_fhis_csi.py` mapea cada capítulo FHIS (F01…F55) a su división CSI del
catálogo EstimaStruct y mide cobertura vs las 375 fichas vivas (v1.3):

- `data/crosswalk_fhis_csi.csv`
- `data/cobertura_report.md` — **15/23 divisiones CSI cubiertas**; los 8 huecos
  (HVAC, fire suppression, automation, comms, etc.) son el segmento de edificación
  vertical fina que se rellena con Suárez Salazar (previsto en goal-21065 §3).

## Qué falta (gated a 2º OK)

1. Adquirir el **PDF FHIS** (fichas escaneadas) y extraer los valores numéricos de
   rendimiento (cuadrilla, m·h/unidad, cantidad de material, % desperdicio) →
   poblar `rendimiento_fuente`.
2. Complementar con Suárez Salazar en las 8 divisiones hueco.
3. Componer APU = rendimiento (FHIS/Suárez) × precio (CHICO 2025/2026) y promover
   a `rendimientos_v1.4` en el catálogo vivo — **producción, requiere OK**.
4. Confirmar antes a qué BD escribe el backend activo (SQLite versionada del repo,
   no Postgres — ver split-brain).

## Fuente

- Índice: https://quercusoft.com/honduras-fhis-200311/ (digitalización Quercusoft)
- PDF FHIS: https://documentos.arq.com.mx/Detalles/262272.html · Scribd · idoc.pub
- Suárez Salazar, "Costo y Tiempo en Edificación" (Limusa)
