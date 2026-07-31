# Auditoría de Fórmulas — Mapa de Estructura

> **Propósito:** inventario de TODO el código de EstimaStruct que ejecuta una fórmula de cálculo, clasificado por si esa fórmula hoy **se ve** (narrada con LaTeX y expuesta por endpoint) o **corre ciega** (calcula, escribe resultado, y nadie puede auditar el paso).
> **Alcance:** read-only. Este documento no propone código; describe el estado actual verificado contra el repo el 2026-07-27.
> **Fuente de estado arquitectural:** `docs/architecture.md`. Este archivo lo complementa a nivel de fórmula, no lo reemplaza.
> **Regla de diseño que gobierna el módulo nuevo:** el motor de cálculo es la ÚNICA fuente de verdad. La Auditoría de Fórmulas debe **LEER y NARRAR**, nunca recalcular por su cuenta (ADR-003, `architecture.md §7`).

---

## 0. Correcciones a la premisa de partida

Verificado contra el árbol real del repo:

| Afirmación previa | Realidad verificada |
|---|---|
| Existe `backend/calculo_soldadura.py` | **NO existe.** No hay ningún archivo de soldadura en `backend/`. |
| Existe `memoria_soldadura(...)` | **NO existe.** La soldadura de filete AISC §J2 vive **dentro** de `calculo_conexion_acero.py` (`garganta_filete`, `fnw_soldadura`, `rn_soldadura`, `rn_metal_base_corte`) y se narra dentro de `memoria_conexion`. |
| Endpoints `GET /{sid}/memoria` y `POST /soldadura-estructural/memoria-rapida` | **NO existen.** El endpoint real es `POST /conexion-acero/memoria-rapida`. |

Implicación para el módulo nuevo: **no hay un dominio "soldadura" separado que auditar**; es una sección de conexiones.

Segunda corrección, relevante al dominio pricing:

- `architecture.md §4 Paso 7` documenta overhead de proyecto como `administracion + utilidad + imprevistos + otros_factor` sobre subtotal, más `iva` (default 15%) al final. **En el código esos cuatro campos existen en `ConfigPresupuesto` (`models.py:36-39`) pero NINGÚN cálculo los lee.** El único factor aplicado es `sobrecosto` (`routers/calculos.py:37-41`, comentario explícito: *"El sobrecosto ya incluye IVA y cualquier margen adicional del negocio"*). Los campos se persisten, se duplican al clonar un presupuesto (`presupuestos.py:558-561`, `scripts.py:143-146`) y se devuelven al frontend (`presupuestos.py:375-378`) — pero son **datos muertos**. Una auditoría de fórmulas honesta debe exponer esto, porque hoy el usuario ve campos de utilidad/IVA en la UI que no mueven ningún número.

---

## 1. Resumen ejecutivo

| Métrica | Valor |
|---|---|
| Archivos que ejecutan fórmulas de cálculo | **14** |
| Con narración (`memoria_*`) **y** expuesta por endpoint | **4** |
| **Ciegos** (calculan, no narran) | **10** |
| Pasos narrados hoy (`_paso(...)`) | 160 (69 concreto + 38 conexiones + 31 miembro acero + 22 sismo) |
| Fórmulas con LaTeX simbólico mapeado | ~99 en `LATEX_BY_FORMULA` + inline en sismo |
| Dominios con narración | concreto ACI, sísmico CHOC-08, acero LRFD §D-H, conexiones AISC §J |
| Dominios **sin** narración | **pricing / dinero, cronograma, takeoff y factores, propiedades de sección, mapeo ficha↔CSI, conversión de unidades, prorrateo bancario, predimensionamiento, placas base masivas** |

**Lectura corta:** todo lo que es *ingeniería estructural* ya se ve. Todo lo que es *dinero, tiempo y cantidad* corre ciego. El gap principal no está en el lado estructural — está en el lado presupuestal, que es exactamente donde el error tiene consecuencia financiera (precedente: bug de doble conteo en producción, 2026-07-03).

---

## 2. MÓDULOS CIEGOS — el trabajo pendiente real

Ordenados por riesgo (riesgo financiero directo primero).

### C-01 · `backend/services/pricing.py` — **PRIORIDAD MÁXIMA**

| Campo | Valor |
|---|---|
| Dominio | **Pricing / dinero** |
| Qué calcula | Bucketing 3-vías de insumos, costo base, precio unitario, total de partida |
| Narración | **NINGUNA.** Cero `_paso`, cero LaTeX, cero `memoria_*` |
| Endpoints propios | **NINGUNO.** Es módulo puro importado por 5 routers |
| Riesgo | **Alto — es el motor de dinero.** Ya produjo un bug de doble conteo en producción (2026-07-03, documentado en el propio docstring del archivo, líneas 10-19) |

Firmas públicas (todas puras, sin ORM salvo la última):

```
quantize_money(x) -> float                                  # Decimal 4dp ROUND_HALF_UP
calc_base(costo_mo, costo_ma, unitario_matriz) -> float
rebucket_insumos(insumos) -> tuple[float, float, float]     # (mo, ma, otros)
precio_unitario(base, sobrecosto_pct) -> float
recalcular_partida(partida, sobrecosto_pct) -> None         # ESCRIBE in-place sobre el ORM
```

Fórmulas ejecutadas (ya documentadas en prosa en `architecture.md §4`, nunca renderizadas al usuario):

- `costo_mo = Σ insumo.total donde tipo == MANO_OBRA`
- `costo_ma = Σ insumo.total donde tipo == MATERIAL`
- `unitario_matriz = Σ insumo.total donde tipo ∉ {MANO_OBRA, MATERIAL}`
- `costo_base = costo_mo + costo_ma + unitario_matriz`
- `PU = costo_base × (1 + sobrecosto/100)`
- `total = cantidad × PU`
- Cuantización: `Decimal(str(x)).quantize(0.0001, ROUND_HALF_UP)` en cada boundary de escritura

**Nota de arquitectura para el módulo de auditoría:** `recalcular_partida` **escribe**. Una auditoría que la llame para "mostrar el paso" mutaría la partida. Las tres funciones seguras de leer son `calc_base`, `rebucket_insumos` y `precio_unitario` — son puras y devuelven valor sin efecto. Ése es el punto de enganche correcto.

---

### C-02 · `backend/routers/calculos.py` — agregación de presupuesto e indirectos

| Campo | Valor |
|---|---|
| Dominio | Pricing (nivel obra) |
| Qué calcula | Recálculo global de la obra, costo directo, factor de indirectos, reporte por capítulo |
| Narración | **NINGUNA** |
| Endpoints | `POST /presupuestos/{pid}/calcular` · `GET /presupuestos/{pid}/reporte` |

Firmas:

```
_recalcular_todo(p: Presupuesto, db: Session) -> float      # ESCRIBE; devuelve base_total
_factor_indirectos(cfg: ConfigPresupuesto) -> float          # PURA, segura de leer
recalcular(pid, db)        # endpoint, commit
reporte(pid, db)           # endpoint, read-only — mejor punto de enganche
```

Fórmulas ciegas:

- `insumo.total = cantidad × costo_unit` (con skip-unchanged para evitar 6759 UPDATEs inútiles, línea 23)
- `costo_directo = Σ (partida.cantidad × partida.costo_base)` ← **ojo: usa `costo_base`, sin sobrecosto**
- `factor_indirectos = 1 + sobrecosto/100`
- `total_con_indirectos = costo_directo × factor`
- En `reporte`: `costo_directo = Σ partida.total` ← **usa `total`, que YA lleva sobrecosto**

⚠️ **Hallazgo:** los dos endpoints llaman "costo_directo" a dos cosas distintas. En `/calcular` es `Σ cantidad × costo_base` (sin markup); en `/reporte` es `Σ partida.total` (con markup). Luego `/reporte` vuelve a multiplicar por `1 + pct/100`, aplicando el sobrecosto **dos veces** sobre esa base. Nadie lo ve hoy porque no hay narración. Esto solo es exhibible con auditoría de fórmulas — es el caso de uso que justifica el módulo.

- Default silencioso: si no hay `config`, `sobrecosto = 20.0` (hardcode en `calculos.py:14,73` y `partidas.py:82`).

---

### C-03 · `backend/routers/export_pdf.py` — prorrateo bancario

| Campo | Valor |
|---|---|
| Dominio | Pricing (documento financiero al banco) |
| Qué calcula | Factor de prorrateo para forzar el total del presupuesto a un `valor_banco` exacto, y Gantt prorrateado |
| Narración | **NINGUNA** |
| Endpoints | `GET /export-pdf/{pid}?report=banco&valor_banco=...` |

Firmas:

```
_costos_obra(p) -> ...                       # total_real = Σ partida.total
_rows_presupuesto_banco(p, factor: float)
_gantt_banco_data(p, factor: float)
_export_pdf_banco(p, ctx, q) -> StreamingResponse
```

Fórmulas ciegas:

- `factor = valor_banco / total_real`
- `pu_banco = precio_unitario × factor` · `total_banco = total × factor`
- Fila TOTAL **forzada** a `valor_banco` exacto (no a la suma de las filas redondeadas) — decisión deliberada documentada en el docstring, pero invisible en el PDF resultante
- Gantt: buffer fijo `BUFFER_CONTRATIEMPOS_DIAS = 26` (1 mes laboral) añadido al final

Riesgo: el documento que llega al banco lleva números prorrateados por un factor que no aparece en ningún lado. Candidato directo a sección de auditoría.

---

### C-04 · `backend/cronograma.py` + `backend/routers/cronograma.py` — duración y Gantt

| Campo | Valor |
|---|---|
| Dominio | **Cronograma** |
| Qué calcula | Jornadas-hombre por partida, duración en días, fase constructiva, fechas |
| Narración | **NINGUNA** |
| Endpoints | `GET /presupuestos/{pid}/cronograma` · `POST /presupuestos/{pid}/cronograma/personal` · `GET /presupuestos/{pid}/export-cronograma` |

Firmas (motor puro, sin ORM — ideal para auditar):

```
cargar_catalogo(path: str | None = None) -> dict
_jornadas(csi, cantidad, catalogo) -> tuple[float, float, str]   # (jh_esp, jh_ay, fuente)
duracion_actividad(csi, cantidad, catalogo, n_esp=3, n_ay=3) -> dict
_fase_de(csi, cap) -> tuple[str, int]
_suma_dias_laborales(inicio: date, dias_lab: int) -> date
construir_cronograma(partidas: list[dict], catalogo=None, fecha_arranque=None) -> list[dict]
```

Fórmulas ciegas:

- `duración = max(ceil(jh_esp / N_esp), ceil(jh_ay / N_ay), 1)`
- `jh_esp = esp_u × cantidad` · `jh_ay = ay_u × cantidad` (rendimientos del catálogo v1.2)
- Cascada de prioridad de fuente **invisible**: `TIEMPOS_FIJOS` > `MANUAL_SPLIT` > catálogo v1.2 > `SIN_TIEMPO` (⇒ 1 día). El campo `fuente` ya viaja en la respuesta pero no se narra ni se explica.
- Offsets de fase hardcodeados por división CSI (`CAP_FASE`, `CSI_FASE`) — números mágicos (0, 3, 8, 22, 29, 50, 80, 120 días) sin justificación visible
- Calendario: 6 días/semana, domingo no laboral (`DIAS_SEMANA = 6`)
- Defaults: `DEF_ESP = 3`, `DEF_AY = 3`, `CREW_LUMP = 3`

---

### C-05 · `backend/routers/partidas.py` — takeoff y factores de cantidad

| Campo | Valor |
|---|---|
| Dominio | Pricing / takeoff cuantitativo |
| Qué calcula | Cantidad final de partida a partir de la cantidad bruta de Revit |
| Narración | **NINGUNA** |
| Endpoints | `PATCH /partidas/{pid}/cantidad` · `/revit-q` · `/factores` |

Firmas:

```
_safe_factor(v, default=1.0) -> float
_calcular_partida(partida, sobrecosto) -> None    # delega a pricing.recalcular_partida
_get_sobrecosto(capitulo_id, db) -> float
```

Fórmulas ciegas:

- `cantidad = ceil(revit_q) × factor_e × factor_f`
- `_safe_factor`: **un factor 0 se convierte silenciosamente en 1.0** (`return f if f else default`). El usuario que teclea 0 obtiene 1 sin aviso. Esto solo sale a la luz con auditoría.
- `PATCH /cantidad` sincroniza `revit_q = cantidad` (colapsa el origen del dato)

---

### C-06 · `backend/perfiles_acero.py` — propiedades de sección

| Campo | Valor |
|---|---|
| Dominio | Acero LRFD (upstream de los motores que SÍ narran) |
| Qué calcula | Propiedades geométricas de sección (Ix, Iy, Sx, Zx, ry, J, Cw, rts, λ) que alimentan `calculo_miembro_acero` y `calculo_conexion_acero` |
| Narración | **NINGUNA** |
| Endpoints | Indirecto: `GET /miembro-acero/catalogo`, `GET /conexion-acero/catalogo` (devuelven el catálogo, no el cálculo) |

Firma:

```
props_seccion(perfil_dict: dict, perfil_nombre: str = "") -> dict
```

Fórmulas ciegas — **tres rutas de resolución distintas**, invisibles al usuario:

1. `fuente = "tabla"` → valores exactos AISC/CISC de `TABLA_W`, con conversión SI→cm (÷10, ÷100, ÷1e3, ÷1e4, ÷1e6)
2. `fuente = "derivada"` → deriva de 3 rectángulos, **~3 % conservador** por admisión del propio docstring:
   `Ix = bf·d³/12 − (bf−tw)·hw³/12` · `Zx = bf·tf·(d−tf) + tw·hw²/4` · `J = (2·bf·tf³ + hw·tw³)/3` · `Cw = Iy·ho²/4` · `rts = √(√(Iy·Cw)/Sx)`
3. `fuente = "hss"` → sección cerrada: `I = (b⁴−bi⁴)/12` · `Z = (b³−bi³)/4` · `J = 4·Am²·t/(4(b−t))` · `λ = (b−3t)/t`

**Este es el gap más traicionero:** las memorias de acero muestran φPn, φMn, φVn perfectamente narradas — pero el `Zx` que entra a `Mp = Fy·Zx` puede venir de tabla exacta **o de una derivación 3 % conservadora**, y la memoria no lo dice. La auditoría debería exponer el campo `fuente` en cada memoria de acero.

---

### C-07 · `backend/acero_ficha.py` — mapeo perfil→ficha CSI y envolvente D/C

| Campo | Valor |
|---|---|
| Dominio | Acero / puente a presupuesto |
| Qué calcula | Agregación de miembros por ficha Div 05, envolvente de D/C, longitudes totales, resolución de ficha de conexión, insumos de ficha |
| Narración | **NINGUNA** |
| Endpoints | vía `POST /diseno/{pid}/import-etabs-acero`, `/acero-generar-partidas`, `/conexion-generar-partida` |

Firmas:

```
mapear_perfil_a_ficha(perfil: str, rol: str = "") -> dict
agregar_por_ficha(miembros: list) -> dict
conexion_ficha(perfil_vig, perfil_col, tipo="VC_CORTANTE") -> dict
insumos_ficha(codigo: str, version: str = "v1.2") -> dict
catalogo_acero() -> dict
_clase_peso(perfil_norm) -> str
```

Fórmulas / reglas ciegas:

- `longitud_total_mL = Σ longitud por (ficha, perfil_norm, rol)`
- `dc_max = max(dc)` del grupo → define `combo_gobernante`
- `sobre_esforzados` cuando `dc > DC_LIMITE = 1.0` (AISC §H1.1)
- **Regla silenciosa:** perfil dual sin rol explícito ⇒ **se asume COLUMNA** (emite aviso en `avisos[]`, pero el aviso no se renderiza en ningún lado)
- Clasificación ligera/media/pesada por peso de perfil → mapea a fichas CV-1/2/3, VV-1/2/3, BP-1/2/3

---

### C-08 · `backend/routers/acero_diseno.py` — placas base masivas §J8

| Campo | Valor |
|---|---|
| Dominio | Acero / conexiones (batch desde ETABS) |
| Qué calcula | Envolvente de D/C por pedestal sobre todas sus combinaciones de carga, para diseño masivo de placas base |
| Narración | **NINGUNA** — aunque el motor subyacente (`calcular_conexion`) SÍ tiene `memoria_conexion` disponible y no se usa aquí |
| Endpoints | `GET /diseno/{pid}/pedestales-base` · `POST /diseno/{pid}/placas-base-etabs` |

Fórmulas ciegas:

- `Pu = |FZ| × factor_unidad` · `Vu = hypot(FX, FY) × factor_unidad`
- `A2 = A2_cm2` o, si 0, `lado_cm²`
- Envolvente: se corre `calcular_conexion` por cada combo y se **retiene el de mayor DC** — el usuario ve un solo número y no sabe qué combo lo produjo ni cuántos se descartaron
- Reconocimiento de pedestal por regex `^P-?\d+$` sobre `type_mark`, o substring "pedestal" en notas

**Enganche de bajo costo:** este endpoint ya tiene `elem` y `caso` en la forma exacta que consume `memoria_conexion(elem, caso)`. Narrar el combo gobernante es reusar la memoria existente, no escribir fórmula nueva.

---

### C-09 · `backend/routers/diseno_estructural.py` — mampostería, predimensionamiento, generación de partidas

| Campo | Valor |
|---|---|
| Dominio | Concreto / mampostería / takeoff |
| Qué calcula | Takeoff de muro de mampostería, predimensionamiento de secciones, generación de partidas CSI desde resultados |
| Narración | **PARCIAL.** El router expone `memoria_calculo` para casos de diseño, pero estos tres bloques quedan fuera |
| Endpoints | `POST /diseno/{pid}/mamposteria` · `POST /diseno/predimensionar` · `POST /diseno/casos/{cid}/generar-partidas` · `GET /diseno/{pid}/resumen` |

Fórmulas ciegas — mampostería (líneas 1153+):

- `area_m2 = longitud_m × altura_m`
- `acero_kg = area_m2 × 3.5` — **constante `ACERO_KG_M2 = 3.5` con comentario `# kg/m² approx`, sin referencia normativa**
- `concreto_m3 = area_m2 × 0.023` — **`CONCRETO_M3_M2 = 0.023`, `# m³/m² approx`, sin referencia**

Estos dos números generan partidas de acero y concreto que van directo al presupuesto. Son las constantes menos justificadas del sistema y hoy son invisibles.

Fórmulas ciegas — predimensionamiento (`calculo_estructural.predimensionar`, línea 1317):

```
predimensionar(tipo, niveles=1, luz_libre_cm=0.0, b_apoyo_cm=0.0, recubrimiento_cm=4.0) -> dict
```

- COLUMNA: `lado_min = niveles × 10 × 0.8`; `b = h = ↑múltiplo de 5 ≥ lado_min`
- VIGA: `h = (luz_libre − 2·b_apoyo)/10`; `↑múltiplo de 5`; `b ≈ h/2` (mín 20)
- `d = h − recubrimiento`

Función **pura**, con las fórmulas ya escritas en el docstring, y devuelve `regla_usada` + `notas`. Es el módulo ciego más barato de narrar: la información ya está estructurada, solo le falta el formato `_paso`.

---

### C-10 · `backend/seccion_ficha.py` — conversión de unidades y mapeo sección→ficha

| Campo | Valor |
|---|---|
| Dominio | Concreto / normalización de datos ETABS |
| Qué calcula | Factores de conversión de unidades (kgf/kN/t), mapeo de dimensiones de sección a ficha CSI, parseo de tablas ETABS |
| Narración | **NINGUNA** |
| Endpoints | vía `POST /diseno/{pid}/import-etabs-concreto`, `POST /diseno/{pid}/placas-base-etabs` |

Firmas:

```
factores_unidad(unidad_entrada: str) -> tuple[float, float]    # (ff, fm) fuerza y momento
mapear_seccion_a_ficha(b_cm, h_cm, tipo="VIGA") -> dict
parse_concreto_texto(texto) -> dict · parse_reacciones_texto(texto) -> dict
```

Fórmulas ciegas:

- `KN_POR_T = 9.80665` — conversión t-fuerza ↔ kN
- Factores de fuerza/momento aplicados a **cada** número que entra desde ETABS. **Un `unidad` mal seleccionado escala todo el diseño por ~9.8× sin ninguna señal visible.**
- Redondeo dimensional a clave de ficha (`_clave_dim`), decide qué ficha CSI recibe la cantidad

---

### Ciegos menores (registrados, prioridad baja)

| Archivo | Fórmula ciega | Nota |
|---|---|---|
| `backend/routers/insumos.py` | `insumo.total = cantidad × costo_unit` → dispara `rebucket_insumos` | Delega correctamente a `pricing.py`; sin narración |
| `backend/routers/export.py:399-400` | Split **2-vías** para display Excel: `mo_total` vs `ins_total` | Re-implementación local del bucketing, solo para mostrar; **no escribe a BD**, pero contradice visualmente el modelo 3-vías real |
| `backend/routers/portal_publish.py` | Reenvía `sobrecosto` + total a Supabase | No recalcula; propaga |
| `backend/etabs_procedimiento.py` | Parseo, detección de casos DEAD/SISMO, conversión | Tiene documentación expuesta (`GET /diseno/sismo/procedimiento`) pero narra el *procedimiento operativo*, no las fórmulas ejecutadas |

---

## 3. MÓDULOS CON NARRACIÓN — patrón a reusar

Los cuatro comparten un contrato idéntico. **Ese contrato es el que el módulo de Auditoría debe adoptar.**

### N-01 · `backend/calculo_estructural.py` — concreto ACI 318-19

| Campo | Valor |
|---|---|
| Dominio | Concreto reforzado (vigas simple/doble/T, cortante, torsión, columna con esbeltez, takeoff CSI 03) |
| Motor | `calcular_caso(elem: dict, caso: dict) -> dict` (línea 448) — **única fuente de verdad** |
| Narración | `memoria_calculo(elem: dict, caso: dict) -> dict` (línea 851) |
| Pasos | 69 · `LATEX_BY_FORMULA` con 57 entradas (línea 746) |
| Endpoints | `GET /diseno/casos/{cid}/memoria` (stateful, desde BD) · `POST /diseno/memoria-rapida` (stateless) |
| Frontend | `frontend/js/calculo-estructural.js:339` y `:630` |
| Secciones narradas | Materiales → Geometría → Flexión → Cortante → Torsión → Columna → Takeoff → Verificación |
| **NO narrado** | `predimensionar()` (misma archivo, ver C-09) |

Además es el **proveedor de infraestructura de narración**: `_fmt`, `_paso` y `_ascii_to_latex` se importan desde aquí en `calculo_conexion_acero.py:30` y `calculo_miembro_acero.py:30`.

### N-02 · `backend/calculo_sismico_choc08.py` — sísmico CHOC-08

| Campo | Valor |
|---|---|
| Dominio | Sísmico (periodo, coeficiente, cortante basal, espectro, derivas) |
| Motor | Funciones puras: `periodo_metodo_a`, `coef_sismico`, `cortante_basal`, `cortante_estatico`, `escalado_cortante`, `verificar_derivas`, `acel_espectral`, `deriva_limite`, `construir_espectro` |
| Narración | `memoria_sismica(entrada: dict) -> dict` (línea 211) |
| Pasos | 22 · **sin** `LATEX_BY_FORMULA`; usa `latex=` / `latex_sub=` **inline** por paso (líneas 259+) |
| Endpoints | `POST /diseno/sismo/memoria` · `POST /diseno/sismo/espectro-csv` · usado internamente en `GET/PUT /diseno/{pid}/sismo`, `POST /diseno/{pid}/sismo/from-estudio-suelo`, `POST /diseno/sismo/import-etabs` |
| Frontend | `calculo-estructural.js:1418` |
| Salida extra | `espectro[[T, a/g]]` además de `{meta, pasos, constantes}` |

⚠️ **Divergencia de patrón:** es el único que no usa el mapa `LATEX_BY_FORMULA`. Firma de entrada también divergente: recibe **un solo dict** `entrada`, no el par `(elem, caso)`. Un módulo de auditoría genérico debe manejar ambas firmas.

### N-03 · `backend/calculo_miembro_acero.py` — acero LRFD §D-H

| Campo | Valor |
|---|---|
| Dominio | Acero LRFD (tracción §D, compresión §E, flexión §F, cortante §G, interacción §H) |
| Motor | `calcular_miembro(elem: dict, caso: dict) -> dict` (línea 225) |
| Narración | `memoria_miembro(elem: dict, caso: dict) -> dict` (línea 419) |
| Pasos | 31 · `LATEX_BY_FORMULA` con 22 entradas (línea 376) |
| Endpoints | `POST /miembro-acero/memoria-rapida` (stateless) · `GET /diseno/casos/{cid}/memoria` **rama acero** (`diseno_estructural.py:600-607` desvía a `memoria_miembro` cuando el elemento es de acero) |
| Frontend | `calculo-estructural.js:2232` |
| Dependencia ciega | `perfiles_acero.props_seccion` (ver C-06) |

### N-04 · `backend/calculo_conexion_acero.py` — conexiones AISC §J (incluye soldadura)

| Campo | Valor |
|---|---|
| Dominio | Conexiones §J: pernos §J3, soldadura de filete §J2, fluencia/rotura §J4, block shear §J4.5, placa base §J8 |
| Motor | `calcular_conexion(elem: dict, caso: dict) -> dict` (línea 267) |
| Narración | `memoria_conexion(elem: dict, caso: dict) -> dict` (línea 482) |
| Pasos | 38 · `LATEX_BY_FORMULA` con 20 entradas (línea 445) + `latex=` inline en §J8 |
| Endpoints | `POST /conexion-acero/memoria-rapida` (stateless) |
| Frontend | `calculo-estructural.js:3212` |
| **Gap de exposición** | `POST /conexion-acero/conexiones/{cid}/recalcular` **persiste** el resultado pero **NO devuelve memoria**. No existe `GET /conexion-acero/conexiones/{cid}/memoria`. La conexión guardada en BD no es auditable — solo la calculadora en vivo lo es. |

---

## 4. Contrato de narración — lo que la auditoría debe reusar

Idéntico en los cuatro motores narrados. Definido en `calculo_estructural.py:662` (`_paso`).

### 4.1 Firma del paso

```python
_paso(seccion, simbolo, etiqueta, valor, unidad, formula, sustitucion,
      referencia, descripcion, tipo="intermedio", latex=None, latex_sub=None) -> dict
```

### 4.2 Forma del dict devuelto

```
{
  "seccion":     str,   # agrupador ("Materiales", "Flexión", "Placa base §J8", ...)
  "simbolo":     str,   # notación ("φR_{n,gob}")
  "etiqueta":    str,   # nombre legible en español
  "valor":       num|bool,
  "unidad":      str,
  "formula":     str,   # ASCII verbatim — CLAVE del mapa LATEX_BY_FORMULA
  "sustitucion": str,   # sustitución con NÚMEROS REALES, reproducible a mano
  "referencia":  str,   # norma/sección ("AISC §J8 ec.J8-1", "ACI 318-19 §21.2.1")
  "descripcion": str,   # español, qué significa el paso
  "tipo":        str,   # input | intermedio | resultado | check | takeoff
  "latex":       str|None,      # fórmula simbólica
  "latex_sub":   str|None       # sustitución numérica en LaTeX
}
```

### 4.3 Respuesta de una `memoria_*`

```
{ "meta": {...}, "pasos": [ ...paso... ], "constantes": [ {simbolo, latex, valor, unidad, desc} ] }
```
(`memoria_sismica` añade `"espectro": [[T, a_g], ...]`)

### 4.4 Post-proceso LaTeX (idéntico en los 3 que usan el mapa)

```python
for p in P:
    if p["tipo"] != "input" and p["latex"] is None:
        p["latex"] = LATEX_BY_FORMULA.get(p["formula"])
    p["latex_sub"] = _ascii_to_latex(p["sustitucion"])
```

`_ascii_to_latex` devuelve `None` si el texto es prosa (acentos o `%`) → el frontend cae a `<code>` monospace. Degradación elegante, nunca rojo roto.

### 4.5 Firmas de entrada — dos formas, no una

| Forma | Motores | Ejemplo |
|---|---|---|
| `(elem: dict, caso: dict)` | concreto, miembro acero, conexión | `memoria_calculo(elem, caso)` |
| `(entrada: dict)` | sísmico | `memoria_sismica(entrada)` |

Un adaptador de auditoría debe soportar ambas. Los módulos ciegos tienen firmas aún más heterogéneas (`calc_base(mo, ma, matriz)`, `duracion_actividad(csi, cantidad, catalogo, n_esp, n_ay)`, `props_seccion(perfil_dict, perfil_nombre)`) — normalizarlas es parte del diseño del módulo nuevo.

---

## 5. Mapa de endpoints — dónde puede colgarse la auditoría

### 5.1 Endpoints que YA devuelven memoria (reusar tal cual)

| Verbo | Ruta | Motor | Estado |
|---|---|---|---|
| GET | `/diseno/casos/{cid}/memoria` | concreto **o** miembro acero (bifurca por material) | stateful, desde BD |
| POST | `/diseno/memoria-rapida` | concreto | stateless |
| POST | `/diseno/sismo/memoria` | sísmico | stateless |
| POST | `/miembro-acero/memoria-rapida` | acero LRFD | stateless |
| POST | `/conexion-acero/memoria-rapida` | conexiones §J | stateless |

### 5.2 Endpoints que calculan y NO narran (candidatos a enganche)

| Verbo | Ruta | Fórmula ciega que ejecuta |
|---|---|---|
| POST | `/presupuestos/{pid}/calcular` | bucketing 3-vías + base + PU + total, obra completa |
| GET | `/presupuestos/{pid}/reporte` | subtotales por capítulo + factor indirectos (**read-only ⇒ mejor punto de enganche para pricing**) |
| PATCH | `/partidas/{pid}/cantidad` \| `/revit-q` \| `/factores` | `cantidad = ceil(revit_q)·fe·ff` + recálculo |
| POST/PATCH/DELETE | `/insumos/*`, `/partidas/{pid}/insumos` | `total = cantidad × costo_unit` + rebucket |
| GET | `/presupuestos/{pid}/cronograma` | duración, fases, fechas |
| POST | `/presupuestos/{pid}/cronograma/personal` | recalcula duración con n_esp/n_ay |
| GET | `/export-pdf/{pid}?report=banco` | factor de prorrateo bancario |
| POST | `/diseno/predimensionar` | reglas de predimensionamiento (**función pura, ya devuelve `regla_usada`**) |
| POST | `/diseno/{pid}/mamposteria` | `area × 3.5 kg/m²`, `area × 0.023 m³/m²` |
| POST | `/diseno/casos/{cid}/generar-partidas` | takeoff → cantidades CSI |
| GET | `/diseno/{pid}/resumen` | agregación de resultados de diseño |
| POST | `/diseno/{pid}/import-etabs-concreto` \| `/import-etabs-acero` \| `/import-etabs-acero-fuerzas` | conversión de unidades + envolventes |
| POST | `/diseno/{pid}/placas-base-etabs` | envolvente D/C §J8 por pedestal |
| GET | `/diseno/{pid}/pedestales-base` | `A2 = lado²` |
| POST | `/diseno/{pid}/acero-generar-partidas` \| `/conexion-generar-partida` | agregación por ficha + longitudes |
| POST | `/conexion-acero/conexiones/{cid}/recalcular` | persiste sin devolver memoria (**memoria ya existe, solo falta exponerla**) |
| GET | `/conexion-acero/{pid}/conexiones` | lista resultados sin trazabilidad |

### 5.3 Endpoints ausentes que la auditoría necesitaría

- `GET /conexion-acero/conexiones/{cid}/memoria` — narrar una conexión **persistida** (hoy solo la calculadora en vivo narra)
- Ningún endpoint narra pricing, cronograma ni takeoff. **Ese es el hueco.**

---

## 6. Priorización sugerida para el módulo nuevo

| # | Módulo ciego | Dominio | Riesgo | Costo de narrar |
|---|---|---|---|---|
| 1 | `services/pricing.py` + `routers/calculos.py` | dinero | **crítico** — precedente de bug en producción; discrepancia costo_directo detectada en §C-02 | medio (3 funciones puras) |
| 2 | `routers/export_pdf.py` (banco) | dinero | **alto** — documento que va al banco | bajo |
| 3 | `routers/partidas.py` (factores) | cantidad | **alto** — `_safe_factor` convierte 0→1 en silencio | bajo |
| 4 | `routers/diseno_estructural.py` (mampostería) | cantidad | **alto** — constantes 3.5 y 0.023 sin norma, van al presupuesto | bajo |
| 5 | `cronograma.py` | tiempo | medio — no es dinero directo, pero define el Gantt entregado | medio |
| 6 | `perfiles_acero.props_seccion` | ingeniería | medio — invalida silenciosamente memorias de acero que sí se ven | bajo (basta exponer `fuente`) |
| 7 | `seccion_ficha.factores_unidad` | ingeniería | medio — error de unidad escala todo ×9.8 | muy bajo |
| 8 | `calculo_estructural.predimensionar` | ingeniería | bajo | **muy bajo — fórmulas ya en docstring, devuelve `regla_usada`** |
| 9 | `routers/acero_diseno.py` (placas base) | ingeniería | bajo | **muy bajo — reusa `memoria_conexion` existente** |
| 10 | `acero_ficha.agregar_por_ficha` | cantidad | bajo — pero la regla "dual ⇒ COLUMNA" es invisible | bajo |

**Quick wins** (narración casi gratis, motor ya devuelve la información estructurada): #8, #9, #7, #6.

---

## 7. Restricción de diseño no negociable

Verificado en los cuatro motores narrados: `memoria_*` **llama al motor** y narra su salida — no reimplementa. Ejemplo literal, `calculo_conexion_acero.py:485`:

```python
res = calcular_conexion(elem, caso)   # el motor calcula
# ... a partir de aquí solo se LEE res para construir los _paso
```

El módulo de Auditoría de Fórmulas debe respetar exactamente esto: **leer la salida del motor y narrarla.** Si la auditoría recalcula, deja de auditar el sistema y pasa a auditar una copia — que es precisamente el fallo que ADR-003 (`architecture.md §7`) prohíbe y que causó el bug de doble conteo de 2026-07-03.

Corolario para pricing: usar `calc_base`, `rebucket_insumos` y `precio_unitario` (puras, sin efecto). **Nunca** `recalcular_partida`, que escribe in-place sobre el ORM.

---

*Generado 2026-07-27 · análisis read-only del árbol `D:\GitHub\EstimBot\ConsuConstructEstimBot\ESTIMASTRUCT\`. Ningún archivo de `backend/` o `frontend/` fue modificado.*
