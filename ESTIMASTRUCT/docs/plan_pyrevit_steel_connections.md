# Plan — pyRevit "Export Steel Connections" → EstimaStruct Conexiones

> **ESTADO 2026-06-03:** ✅ **Fase 1 (pyRevit) EJECUTADA** (pasos 1-6 + unificación) — botón corre, CSV con VV/VC por keynote.
> ✅ **Fase 2 (EstimaStruct) EJECUTADA** — endpoint import + UI. Validado: VC→CV-1, VV→VV-1 con insumos.
> Cambios: `scripts\count_connections.py` (reescrito) · `EstimBot.extension\...\script.py` (delega) ·
> `routers\acero_diseno.py` (`POST /diseno/{pid}/conexion-import-pyrevit-csv`) · `frontend\js\app.js` (UI import).

> **Fecha:** 2026-06-03 · **Análisis read-only + plan. NO ejecutado.**
> **Botón desplegado:** `%APPDATA%\pyRevit\Extensions\EstimBot.extension\EstimBot.tab\Export.panel\Export Steel Connections.pushbutton\script.py`
> **Fuente OneDrive (divergente):** `D:\OneDrive\Bots\Estimbot\ExportTools.extension\...\ExportSteelConnections.pushbutton\script.py` → delega a `scripts\count_connections.py`
> **Export:** `D:\OneDrive\Bots\Estimbot\EXPORTS\S5_schedules\C10_connections_latest.csv`

---

## 1. Diagnóstico (corrida real: 31 vigas, 6 columnas, 0 clasificadas, CSV vacío)

| # | Severidad | Problema | Evidencia |
|---|-----------|----------|-----------|
| D-1 | 🔴 bug | `format()` mezcla manual+auto en el alert | `script.py:200` `"...L {:,}...".format(total_nodes,len,total_cost,csv_ts)` → `ValueError: cannot switch...` |
| D-2 | 🔴 lógica | Clasifica por regex de Type Name vs `CONN_MAP` (6 combos W×W) | columnas reales "P5 30x30 W150x24"/canaletas → 0 match → CSV solo header |
| D-3 | 🟠 datos | Canaletas (C6x10.5 galvanizado) colectadas como estructura | nodos sin clasificar: "P5 30x30 Canaleta..." ×6 |
| D-4 | 🟠 diseño | pyRevit PRE-decide ficha+CSI+costo (todo a soldada 05 20 00.15-.20) | `CONN_MAP` hardcodea CSI soldada + costo |
| D-5 | 🟡 mantenim. | 2 copias divergentes del script (OneDrive vs desplegada) | formatos CSV distintos |

**D-1 no bloquea el export** (el alert va después de `write_csv`). El bloqueante real es **D-2/D-3**: clasificación por nombre + sin filtro keynote → nada clasifica.

---

## 2. Elementos a incluir (regla del usuario — vínculo por KEYNOTE)

Solo elementos cuyo **keynote = CSI** esté en:

| Rango CSI | Elemento | Rol | Fuente |
|-----------|----------|-----|--------|
| `03 31 00.20`–`03 31 00.27` | Pedestales P1–P7 (concreto) | base de columna | DB `partida` prefijo P |
| `05 20 00.4`–`05 20 00.9` | Vigas acero VA7–VA11 | **viga** | DB prefijo VA |
| `05 20 00.10`–`05 20 00.14` | Columnas acero C6–C10 | **columna** | DB prefijo C |

**EXCLUIR:** canaletas galvanizadas (`05 31 xx`), HSS C1–C5 (`05 20 00.0`–`.3`), todo lo demás.

> Decisión pendiente 🟠: los **pedestales** ¿generan conexión *base plate* (§J8 / ficha BP) o solo identifican qué columna es de acero? El usuario pidió tipos **Viga/Viga** y **Viga/Columna**. Propuesta: tratar columna↔pedestal como **base plate** aparte (BP), no como VV/VC. **Confirmar.**

---

## 3. Tipos de conexión a exportar

| Tipo | Geometría | Miembros | Mapea a EstimaStruct |
|------|-----------|----------|----------------------|
| **VC** (Viga/Columna) | endpoint de viga dentro de bbox de columna acero | VA (05 20 00.4-.9) ↔ C (05 20 00.10-.14) | tipo VC_CORTANTE → ficha CV (apernada) / CX (soldada) |
| **VV** (Viga/Viga) | endpoint de viga toca otra viga | VA ↔ VA | tipo VV → ficha VV |
| **BP** (base, opcional) | columna sobre pedestal | C ↔ P (03 31) | §J8 placa base → ficha BP |

**pyRevit exporta el tipo GEOMÉTRICO (VV/VC/BP) + perfiles + CSIs + cantidad. NO decide soldada/apernada** — eso lo decide el módulo Conexiones de EstimaStruct (requisito previo).

---

## 4. Contrato CSV propuesto (pyRevit → EstimaStruct)

Reemplazar el CSV actual (pre-costeado, soldada fija) por crudo:

```
tipo_conexion,csi_viga,perfil_viga,csi_columna,perfil_columna,cantidad
VC,05 20 00.5,W200x36,05 20 00.14,W310x73,4
VV,05 20 00.6,W200x71,05 20 00.6,W200x71,2
BP,,,05 20 00.10,W150x24,1   # columna↔pedestal (si se incluye)
```

- Sin `costo_unit`/`subtotal` (EstimaStruct los pone desde la ficha+insumos).
- `cantidad` = nº de nodos de esa combinación.
- EstimaStruct decide soldada/apernada → resuelve ficha → insumos × cantidad.

---

## 5. PLAN DE IMPLEMENTACIÓN

### Fase 1 — pyRevit (arreglar botón + filtro keynote + tipo)
1. **Fix D-1:** línea 200 → `"Nodos: {0} | Tipos: {1} | Total: L {2:,}\n\n{3}".format(total_nodes, len(rows), total_cost, csv_ts)`.
2. **Leer keynote, no Type Name:** función `get_keynote(elem)` vía `BuiltInParameter.KEYNOTE_PARAM` del tipo (fallback al type del símbolo). Devuelve el CSI.
3. **Filtro de inclusión:** sets `PEDESTAL = {03 31 00.20..27}`, `VIGA = {05 20 00.4..9}`, `COLUMNA = {05 20 00.10..14}`. Descartar elemento si su keynote no cae en ninguno (excluye canaletas/HSS).
4. **Colectar** vigas (OST_StructuralFraming) y columnas (OST_StructuralColumns) **solo si keynote ∈ rango**.
5. **Detectar nodos** (endpoint viga ∈ bbox columna) y **clasificar TIPO**: si el otro miembro es COLUMNA→VC, si es VIGA→VV, si es PEDESTAL→BP.
6. **Reescribir `write_csv`** al contrato §4 (crudo, sin costo, con tipo+CSIs+perfiles+cantidad). Quitar `CONN_MAP` (ya no pre-decide ficha/costo).
7. **Unificar copias:** dejar UNA fuente (recomendado: `count_connections.py` en OneDrive, y que el `.pushbutton` desplegado delegue ahí, como hace `ExportTools`). Borrar el self-contained divergente.

### Fase 2 — EstimaStruct (import + decidir soldada/apernada + ficha+insumos)
8. **Endpoint import:** `POST /conexion-acero/{pid}/import-pyrevit-csv` — parsea el CSV §4.
9. **Decisión soldada/apernada** en el módulo (regla o toggle UI):
   - VV → tipo `VV` (apernada, ficha VV-x).
   - VC → default `VC_CORTANTE` (apernada CV-x) con opción de marcar `SOLDADA` (CX-x).
   - BP → `PLACA_BASE` (ficha BP-x).
10. **Resolver ficha + insumos:** por fila → `conexion_ficha(perfil_vig, perfil_col, tipo)` → generar Partida Div 05 con `InsumoPartida` (materiales + MANO_OBRA) **× cantidad** (reusar `acero_diseno.py:459`).
11. **Frontend (tab Conexiones):** botón "⬆ Importar CSV pyRevit" (file input) + selector soldada/apernada por tipo + resumen (n conexiones, n fichas, costo).

### Verificación
12. Correr botón en el modelo real → CSV con filas (ya no vacío) → importar → confirmar fichas+insumos generados solo para los elementos en rango.

---

## 6. Orden sugerido

`Fase 1 (pyRevit)` primero → produce CSV correcto → luego `Fase 2 (EstimaStruct import)`.
Bloque mínimo para destrabar HOY: pasos **1–6** (botón clasifica + exporta crudo con CSI+tipo).

> ⚠️ Tocar el script pyRevit desplegado + crear endpoints/frontend. **Requiere OK antes de ejecutar.** Confirmar también: (a) pedestales = BP o fuera; (b) HSS C1–C5 realmente excluidas.
