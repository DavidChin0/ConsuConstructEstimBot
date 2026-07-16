# EstimaStruct — Manual de Usuario

> Manual operativo: cada menú, botón, el ciclo de exportación y cómo se conecta todo.
> Complemento de `ARQUITECTURA_Y_FLUJO.md` (el contrato técnico). Base: código real, 2026-06-01.
> Servidores: UI Flask `:5000` · API backend `:8002`. Tras editar `app.js`/`index.html` → reiniciar Flask + Ctrl+F5.

---

## 0. Qué es y cómo está la pantalla

EstimaStruct = **fuente de verdad del presupuesto** de obra. Todo gira alrededor del **código CSI** (llave maestra que une ficha ↔ keynote Revit ↔ cantidad ↔ partida ↔ propuesta).

**Pantalla principal** = tabla de partidas (renglones del presupuesto) de la **obra activa**. Encima, una **barra superior** con todos los controles. Los 5 módulos de cálculo se abren como pantallas completas encima.

Casi todo exige una **obra activa** (si no, alerta "Abre un presupuesto primero").

---

## 1. Barra superior (header) — botón por botón

| Control | Qué hace |
|---------|----------|
| **EstimaStruct** / by ConsuConstruct | Marca. Link a consuconstruct.com. |
| **Título de obra** (clic) | Nombre de la obra activa. Clic → renombrar / cambiar de obra. |
| **Badge versión** | Versión de la base de fichas (v1.0 / v1.1) de la obra. |
| **Totales** | Costo total de la obra (se actualiza al recalcular). |
| **SC: 20%** (pill sobrecosto) | Sobrecosto del presupuesto. Clic → editar % → recalcula el Precio Unitario de TODAS las partidas (`PU = (MO+MA)×(1+SC/100)`). |
| **⟳ Actualizar** | Recalcula todo el presupuesto (insumos → partidas → totales). |
| **👤 Cliente / Desarrollador** | Cambia de modo. **Cliente** = vista limpia. **Desarrollador** = muestra el menú ⚙, exportaciones avanzadas, factores Revit, colores. |
| **⚙ Menú ▾** | Menú dev (ver §2). Solo en modo Desarrollador. |
| **⬇ Exportar ▾** | Menú de exportación (ver §3 — EL CICLO). |
| **⚙ Módulos ▾** | Abre los 5 módulos de cálculo (ver §4). |
| **+ Nueva Obra** | Crea obra vacía o desde plantilla (Template2_Updated / CC2026). |

---

## 2. Menú ⚙ (Desarrollador)

| Ítem | Qué hace |
|------|----------|
| **ℹ About** | Info de la app. |
| **🗄 Bases de Datos** | Gestiona las fichas curadas (versiones v1.0/v1.1, dedup, sync). |
| **A− / A+ / ↺ tabla** | Tamaño de fuente de la tabla de partidas. |
| **➕ Agregar Fichas** | Inserta fichas (con insumos) de la base a la obra. |
| **Generar Keynotes para Revit (Paso 2)** | Genera `RevitKeynotes_<obra>.txt` desde la obra → se carga en Revit como Keynote Table. (Inicio del puente Revit.) |
| **Actualizar Cantidades de Revit (Paso 4)** | Importa el CSV de schedules de pyRevit → escribe `revit_q`/cantidad en las partidas por CSI. (Cierre del puente Revit.) |

> Pasos 1 y 3 ocurren EN Revit (cargar TXT, exportar schedules con pyRevit). EstimaStruct solo hace 2 y 4.

---

## 3. ⬇ Exportar — EL CICLO DE EXPORTACIÓN

4 tipos. Todos generan **XLSX** (openpyxl), con la paleta ConsuConstruct (amarillo casco / gris concreto). Todos usan la obra activa + su sobrecosto.

### 3.1 📄 Presupuesto — *(precios completos MA + MO)*
**Endpoint:** `GET /presupuestos/{pid}/export` → `Estimastruct_<obra>.xlsx`
**2 hojas:**
- **"presupuesto"** (interna, completa). Columnas: CSI · Type Mark · Descripción · Cantidad (revit_q) · Fórmula · **Cantidad Calc.** · Unidad · **Mano de Obra** · **INSUMOS** (=Material) · **PRECIO UNITARIO** · **Total**. Agrupado por capítulo CSI, con subtotales y TOTAL OBRA. Colores por `color_tipo` (amarillo/verde/azul/rosa). → **Aquí ves MO + MA + PU desglosados.**
- **"resumen"** (para el cliente). Membrete ConsuConstruct (Ing. David Chinchilla, CICH 8222). Tabla limpia: CSI · Descripción · Unidad · Cantidad · PU · Total. Solo partidas con cantidad > 0. TOTAL GLOBAL.

**Para qué:** el presupuesto operativo (hoja 1) + la propuesta presentable al cliente (hoja 2).

### 3.2 🧾 Insumos necesarios de esta obra — *(lista de compra)*
**Endpoint:** `GET /presupuestos/{pid}/export-insumos` → `Estimastruct_Insumos_<obra>.xlsx`
**2 hojas:**
- **"detalle"**: por cada actividad (cantidad > 0), separa **Materiales** y **Mano de obra**, cada insumo con rendimiento · costo unit · total (= rendimiento × costo_unit × **cantidad de la matriz**). Subtotal por sección + Total actividad.
- **"global"**: consolidado de toda la obra. Cabecera: Materiales total · Mano de obra total · Total general (= costo directo). Tabla "Consolidado global de insumos" + tabla **"Cantidad de insumos"** (rendimiento × total agrupado, **ceil para materiales** = cuánto comprar).

**Para qué:** **compras / logística** — cuánto material y cuánta mano de obra pedir para toda la obra.
Si hay insumos que no son MATERIAL/MANO_OBRA, el archivo sale con sufijo `_solo_ma_mo`.

### 3.3 🗂 Base de datos completa (insumos por renglón) — *(módulo completo, estilo OPUS)*
**Endpoint:** `GET /presupuestos/{pid}/export-db` → `Estimastruct_BD_<obra>.xlsx`
**1 hoja "BD":** por cada partida, una **fila MATRIZ** (azul OPUS: CSI · Type Mark · Descripción · Unidad · Cantidad · **MO total** · **INSUMOS total**) seguida de las **filas RECURSO** (cada insumo: Recurso · Clave · Descripción · Unidad · Rendimiento · Costo Unit · Total). No-MO primero, MO después.

**Para qué:** ver **toda la base de datos de la obra** desplegada (matriz + sus insumos), como en OPUS. La estructura completa del costo.

### 3.4 📋 Reporte auditoría XLSX — *(control de calidad)*
**Endpoint:** `GET /presupuestos/{pid}/audit-report` → `Estimastruct_Auditoria_<obra>.xlsx`
**4 hojas:** **resumen** (conteos, total visible) · **insumos** (todos los MA-/MO-/SC-/EQ-/HER-/DIS-/FL- visibles) · **codigos** (por código: variantes de nombre, precio canónico, regla — HER-00 = 5% de la MO) · **precio_cero** (insumos con precio 0 → faltan precios).

**Para qué:** **QA del catálogo** — detectar precios faltantes, nombres inconsistentes, códigos duplicados antes de exportar al cliente.

### Resumen del ciclo de export
| Export | Hojas | Para qué / cuándo |
|--------|-------|-------------------|
| **Presupuesto** | presupuesto + resumen | Operación + propuesta cliente (MA+MO+PU) |
| **Insumos necesarios** | detalle + global | Compras / logística (lista de compra) |
| **Base de datos completa** | BD | Ver toda la base (matriz + recursos) |
| **Auditoría** | resumen/insumos/codigos/precio_cero | QA de precios y catálogo |

---

## 4. ⚙ Módulos — los módulos de cálculo

Dropdown `⚙ Módulos ▾`. Cada uno abre pantalla completa. Exigen obra activa.

| Módulo | Para qué | Persiste / Partida |
|--------|----------|--------------------|
| **📐 Diseño (concreto)** | Concreto ACI 318-19 (vigas/columnas). Split-view: izq tabs (Geometría/Casos/Resultados/Procedimiento/Cómo se usa) · der **Hoja Mathcad siempre visible**. Calcula As, estribos, takeoff. Solo CONCRETO (el acero vive en su módulo). | ✅ / ✅ Div 03 |
| **🔧 Acero** | Acero LRFD AISC §D-H. Dropdown Vista: 🧮 Calculadora de miembro · 📥 Importar de ETABS (persistente) · 📖 Cómo se usa. Lista de elementos + "📦 Generar partidas Div 05" (suministro mL). | ✅ / ✅ Div 05 (mL) |
| **🔗 Conexión Acero** | Conexiones AISC §J (pernos/soldadura/elementos/block shear). Resuelve ficha CV/VV/CX **con insumos + costo**. Botón "📦 Generar partida Div 05" (pza). Demanda manual Vu/Nu/Mu. | calc / ✅ Div 05 (pza) |
| **🏗️ ETABS (sismo)** | Espectro sísmico CHOC-08 (concreto). Calcula la acción sísmica y exporta T,a/g para pegar en ETABS. | contexto |
| ~~🔩 Soldadura~~ | **ELIMINADO (R7)** — borrado físico (router/motor/tabla/modelo/vista) con backup de BD. Subsumido por Conexión §J (que cubre §J2 soldadura + metal base y genera partida Div 05). | — |

> Cada módulo de Diseño/Acero/Conexión muestra una **Hoja estilo Mathcad** (fórmula := sustitución = resultado, KaTeX) para que el cálculo sea auditable.

### 4.1 📐 Diseño (concreto) — ACI 318-19
**Layout (split-view):** sidebar izq (lista de elementos · ⬆ Importar de ETABS concreto · ⟳ V1.1 · ➕ nuevo) · central izq **tabs** (Geometría / Casos de Carga / Resultados / Procedimiento / Cómo se usa) · der **Hoja Mathcad SIEMPRE visible**.
**Cómo usar:** 1) genera elementos (crear/importar/sincronizar) → la Hoja se autopobla. 2) *Geometría*: b/d efectivo/material. 3) *Casos*: agrega combos (Mu/Vu/Tu/Nu viga · Pu/Mxx/Myy + esbeltez columna). 4) *Resultados*: ⚡ Calcular → As/estribos/takeoff. 5) 📦 Generar partidas CSI 03.
**Salida:** As · A's · Av/S · Smax · ✓Sísmico/✓ρg · partidas 03 10 00 (encofrado) / 03 20 00 (acero) / 03 30 00 (concreto).

### 4.2 🔧 Acero — AISC 360-16 LRFD §D-H
**Layout (= Diseño):** sidebar izq (⬆ Importar de ETABS · 📦 Generar partidas Div 05 · lista de elementos de acero con DC, clic → carga) · der **Hoja §D-H SIEMPRE visible** + tabs (🧮 Hoja · 📖 Cómo se usa).
**Cómo usar:** 1) ⬆ Importar ETABS (pega Frame/Section/Combo/P/V2/M2/M3, unidad, grado) → crea elementos + corre §D-H. 2) clic en un elemento → la Hoja se autopobla (perfil + cargas del caso gobernante). 3) edita perfil/cargas → recalcula en vivo. 4) 📦 Generar partidas Div 05 (suministro mL por ficha VA-x/C-x).
**Salida:** φRn por estado (§D tracc · §E compr · §F flexión/LTB · §G corte · §H interacción) · DC gobernante · cumple ✓/✗ (semáforo verde/naranja/rojo).

### 4.3 🔗 Conexión Acero — AISC 360-16 §J
**Layout:** dropdowns Tipo / Viga / Columna + 5 vistas (🧮 Cálculo en vivo · 📥 Importar ETABS (lote) · 🔩 Placas base (pedestales) · 📂 Guardadas · 📖 Cómo usar). Hoja Mathcad + **card de ficha** (CV/VV/CX con insumos + costo). En el cálculo, **💾 Guardar conexión** persiste la conexión actual (tipo+perfiles+geometría+demanda) en el presupuesto.
**Cómo usar (cálculo en vivo):** 1) elige Tipo (VC cortante/momento · VV · soldada · **placa base §J8**) + perfiles. 2) edita placa/pernos/soldadura + demanda Vu/Nu/Mu; si es placa base, edita además P_u/f'c/B/N/A₂ (vienen de ETABS pero quedan como variables; B,N,A₂=0 derivan del perfil). 3) la Hoja calcula §J (gobernante = mín φRn) + resuelve la ficha con su BOM. 4) en la card: cantidad (pza) → 📦 **Generar partida Div 05**.
**Cómo usar (importar lote):** 1) pega la tabla de fuerzas de ETABS (`member,P,V2,M2,M3,Combo`, coma o tab) + unidad + perfiles plantilla. 2) **Calcular lote §J** → por cada nudo se toma la envolvente de DC sobre todas las combinaciones; el tipo se auto-asigna (P domina→placa base · M→momento · resto→cortante). 3) tabla de resultados (nudo · ficha · estado gob · D/C · ✓ · combo), sobre-esforzados resaltados. Es **stateless**: para costear, vuelve al cálculo en vivo y genera la partida.
**Cómo usar (placas base / pedestales):** 1) la tabla se **autocompleta** con los pedestales de la obra (P1…Pn): lado→A₂, perfil de columna si está en la ficha, f'c. 2) pega las **Joint Reactions** de ETABS (`Joint,OutputCase,FX,FY,FZ`, coma/tab) + unidad. 3) por fila, ajusta el **joint** de ETABS y completa el **perfil** de columna faltante. 4) **Calcular placas base §J8** → por pedestal: Pu=|FZ| (envolvente sobre combos), A₂=lado², B×N deriva del perfil → φPp (aplastamiento concreto) + tp_req (espesor DG-1) + D/C. Sobre-esforzados resaltados. Stateless. *(Mañana: corre ETABS, exporta Joint Reactions, pega aquí.)*
**Cómo usar (guardadas):** vista 📂 lista las conexiones **persistidas** del presupuesto (etiqueta · tipo · perfiles · estado gobernante · D/C · ✓ · nº casos). Se guardan con 💾 en el cálculo. Botón 🗑 borra (cascade: casos+resultados). Backend: `POST/GET /conexion-acero/{pid}/conexiones`, `PUT/DELETE /conexion-acero/conexiones/{cid}`, `POST .../recalcular`. Tablas `conexion_acero`/`conexion_caso`/`conexion_resultado`.
**Salida:** φRn por estado §J (J2/J3/J4/block shear · **J8 placa base**) · DC · ficha CV/VV/CX + insumos + costo. Import lote = verificación masiva (envolvente). Cantidades masivas = Revit C10.

### 4.4 🏗️ ETABS (sismo) — CHOC-08
**Layout:** tabs Hoja / 📖 Procedimiento / ⬆ Cargar datos de ETABS.
**Cómo usar:** define zona/suelo/I/Rw/hn/W → calcula el espectro CHOC-08. **⬇ Exportar espectro** (pares T,a/g) para pegar en ETABS (Response Spectrum, User Defined). "Cargar datos de ETABS" importa W/T/V_din/deriva del export para verificar contra CHOC-08.
**Salida:** espectro de diseño · deriva límite · verificación de cortante/deriva.

---

## 5. El ciclo completo (cómo se conecta todo)

```
A) CATÁLOGO              B) MODELO + CANTIDADES (Revit)      C) ANÁLISIS (ETABS)
   Fichas con CSI            Paso 2: Generar Keynotes →          Procedimiento CHOC-08
   + insumos                   RevitKeynotes.txt → Revit          → modelo → export
        │                    Revit: Autotag + Schedules            │
        │                    Paso 4: Actualizar Cantidades         ▼
        ▼                      → revit_q por CSI            D) IMPORT + DISEÑO
   PRESUPUESTO  ◄──────────────────┘                          Módulos Diseño/Acero:
   (obra activa)                                              import ETABS → revisar
        │                                                     con fórmulas → partidas
        ├──────────────────────────────────────────────────────────┘
        ▼
E) EXPORT
   📄 Presupuesto (MA+MO+PU) ·  🧾 Insumos (compras) ·  🗂 BD completa ·  📋 Auditoría
        │
        ▼
F) ProposalBot → propuesta al cliente
```

- **CSI es el hilo** que conecta A→B→C→D→E. Una ficha mal codificada rompe la cadena.
- **Revit** aporta CANTIDADES (revit_q). **ETABS** aporta DEMANDA (fuerzas → diseño). EstimaStruct integra y exporta.

---

## 6. Dónde están las "últimas bridges" (para poner metas)

Puntos donde la cadena **aún no cierra** (gaps del audit — anota aquí tus metas):

| Puente | Estado | Meta (tweak aquí) |
|--------|--------|-------------------|
| **Acero → su módulo** | ✅ Fase 2 + R3: módulo Acero propio (calc+import+partidas) y endpoints stateful en `acero_diseno.py` | — |
| **Conexiones → presupuesto** | ✅ R4 import fuerzas-nudo + ✅ R5 persistencia (3 tablas + CRUD + 💾 Guardar / 📂 Guardadas). Pendiente menor: persistir lote/placas masivos + link a partida | Guardar-lote masivo + auto-link partida Div 05 |
| **Soldadura → Conexiones** | ✅ R7: Soldadura **borrada físicamente** (backup hecho). §J2 weld vive dentro de Conexión | — |
| **Fuerzas de nudo ETABS → Conexión** | ✅ R4: `import-etabs-fuerzas` (envolvente DC por nudo, batch §J) | — |
| **OmniClass/Assembly** | En BD, no se cruzan | Importar de Revit para clasificación dual |
| **Import cantidades** | "Replace total" (cera lo sin match) | Modo "merge" (solo actualizar lo que vino) |
| **pyRevit** | Productivo en %APPDATA% fuera del repo | Versionar `EstimBot.extension` en el repo |

---

*Manual operativo. Para la arquitectura interna y el plan de consolidación por fases, ver `ARQUITECTURA_Y_FLUJO.md`.*
