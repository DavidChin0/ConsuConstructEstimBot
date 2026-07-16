# Módulos EstimaStruct → Actividades CSI generadas (antes del flujo ETABS)

> **Fecha:** 2026-06-03 · **Fuente:** `estimacion.db` (tabla `partida`, codigos `clave_csi` reales) +
> `calculo_estructural.py` (takeoff CSI 03), `acero_ficha.py` (fichas Div 05), `csi_utils.py` (prefijo→división).
> **Para:** saber qué partidas produce cada módulo ANTES de correr el procedimiento ETABS.

---

## Regla de división (csi_utils — prefijo type_mark → división CSI)

| Prefijos | División | Qué es |
|----------|----------|--------|
| V, P, S, R, GR, CON, CONC, ARM, ENC, CM, C(concreto) | **03** | Concreto |
| C, CG, CV, VV, SF, VA, RAI | **05** | Acero / metales |

---

## 1. Módulo CONCRETO  (viga/columna ACI 318-19 · `calculo_estructural.py`)

`takeoff_viga` / `takeoff_columna` → **3 actividades por elemento** (lo que crea el flujo ETABS, prefijo `ETABS`):

| CSI | Actividad | Unidad | Cantidad del motor |
|-----|-----------|--------|--------------------|
| **03 10 00** | Encofrado (columna/viga) | m² | `encofrado_m2` |
| **03 20 00** | Acero de refuerzo | kg | `acero_kg` (longitudinal) + `estribos_kg` |
| **03 30 00** | Concreto colado (f'c) | m³ | `concreto_m3` |

> Tag de las partidas ETABS: `[ETABS-ACERO:C1]` / `[ETABS-ACERO:V1]`.
> Catálogo manual relacionado (no-ETABS): 03 11 00 entrepiso · 03 21 00.x armados · 03 22 00 losa ·
> 03 31 00.x columnas/vigas/soleras coladas · 03 31 02 zapatas · 03 31 03 premezclado · 03 39 23 curado.

---

## 2. Módulo ACERO — MIEMBRO  (§D-H · `calculo_miembro_acero.py` + `acero_ficha.py`)

`mapear_perfil_a_ficha(perfil, rol)` → ficha Div 05 por perfil. **1 partida por miembro** (insumos embebidos: perfil + placas + pernos + pintura + montaje):

| CSI | Ficha | Actividad | Unidad |
|-----|-------|-----------|--------|
| **05 10 00** (.0–.2) · **05 20 00.4–.9** | **VA-x** | Viga de acero (IPR/WF) — incl. placas, pernos, pintura | lance / mL |
| **05 20 00** (.0–.14) | **C-x** | Columna de acero (HSS/WF) | mL / nivel |

---

## 3. Módulo ACERO — CONEXIÓN  (§J · `calculo_conexion_acero.py` + `acero_ficha.py`)

`_estados_por_tipo(tipo)` → ficha de conexión Div 05. **1 partida por conexión** (insumos: placa A36 + pernos A325 + soldadura E70 + labor):

| CSI | Ficha | Tipo | Actividad | Unidad |
|-----|-------|------|-----------|--------|
| **05 15 00.1/.2/.3** | **CV-x** | VC_CORTANTE | Conexión viga-columna **APERNADA** (placa simple) | pza |
| **05 15 00.4/.5/.6** | **VV-x** | VV | Conexión viga-viga **APERNADA** | pza |
| **05 20 00.15–.20** | **CX-x** | SOLDADA | Conexión **SOLDADA** (filete E70) | conexion |
| **05 05 23** | STR | — | Soldadura por arco manual (cercha↔placa, E70) | mL |
| **05 12 23** | STR | — | Placa de acero A36 (suelta) | m² |

---

## 4. Sub-módulo PLACA BASE §J8  (parte de Conexión · fichas BP-x)

| CSI | Ficha | Actividad | Unidad |
|-----|-------|-----------|--------|
| **03 15 13** | STR | Instalación de Anclajes de Columna (J-Bolts F1554) | pza |
| **05** (ficha BP-1/2/3) | **BP-x** | Placa base A36 + 4 J-bolt F1554 + soldadura + labor | pza |

> BP cruza dos divisiones: el anclaje al concreto (**03 15 13**) + la placa metálica (**Div 05**).

---

## 5. Otros metales (catálogo, no salen del cálculo ETABS directo)

| CSI | Prefijo | Actividad |
|-----|---------|-----------|
| 05 12 00 | STR | Cercha metálica (Pratt/etc.) |
| 05 31 13 / 05 31 23 | CG | Estructura canaleta galvanizada (entrepiso) |
| 05 31 33 | SF | Steel Framing |
| 05 51 00 | GR | Escalera metálica |
| 05 52 00 / 05 52 01 | RAI | Baranda / riel de aluminio + vidrio |

---

## 6. Resumen — qué espera el flujo ETABS por material

```
ETABS frame  ──clasifica──►  CONCRETO  →  03 10 00 (encofrado) + 03 20 00 (acero) + 03 30 00 (concreto)
                             ACERO     →  perfil→ficha:  VA-x (05 10 00) viga · C-x (05 20 00) columna
                                          conexión:      CV/VV (05 15 00) apernada · CX (05 20 00.x) soldada
                                          placa base:    03 15 13 (J-bolts) + BP-x (Div 05)
```

**Antes de ETABS:** el módulo de cálculo (Mathcad/motor) verifica el DISEÑO (DC ≤ 1). El flujo ETABS
toma ese diseño + las cantidades (longitud, sección, As, perfil) y **emite estas partidas CSI** al presupuesto.
