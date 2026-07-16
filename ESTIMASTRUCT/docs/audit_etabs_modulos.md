# Auditoría — Módulos ETABS / Diseño / Conexiones (4 puntos) + Pasos a ejecutar

> **Fecha:** 2026-06-03 · **Alcance:** backend `routers/` + `frontend/js/app.js` + `acero_ficha.py`.
> **Método:** investigación read-only (3 sondas paralelas). **NO se ejecutó ningún cambio** — solo auditoría + plan.
> Regla rectora (usuario): **Diseño = solo revisa ETABS. Conexiones = único módulo que genera ficha con insumos.**

---

## PUNTO 1 — ¿Qué modifica "Guardar contexto Sísmico"?

**Cadena:** `app.js:3853` botón `et-guardar-ctx` → `guardarContextoSismico()` (`app.js:3751`) → **`PUT /diseno/{pid}/sismo`** → `diseno_estructural.py:892 upsert_contexto_sismico()`.

**Modifica SOLO la tabla `contexto_sismico`** (1 fila por presupuesto, upsert). Campos escritos:
`norma`(=CHOC-08), `municipio`, `zona`, `z_factor`, `suelo`, `s_coef`, `ta_s`, `tb_s`, `c_exp`,
`importancia_i`, `rw`, `deriva_limite`, `hn_m`, `w_t`, `v_din_t`, `deriva_real`, `espectro_json`, `notas`, `updated_at`.

Los derivados (Z, S, Ta, Tb, c, deriva límite, espectro) se **recalculan server-side** con el motor CHOC-08 (`memoria_sismica`), no vienen del cliente.

**Sin efectos colaterales:** NO toca `diseno_elemento`, `caso_diseno`, `resultado_diseno`, `partida`. NO recalcula elementos. NO genera partidas. **Veredicto: 🟢 correcto — guarda solo el contexto sísmico del presupuesto.** No requiere acción.

---

## PUNTO 2 — Eliminar generación de 03 10 00 / 03 20 00 / 03 30 00 desde diseño estructural

**Dónde se generan** (ÚNICO lugar): `diseno_estructural.py:1599-1666` endpoint **`POST /diseno/casos/{cid}/generar-partidas`** → `generar_partidas()`:
- `1623` Encofrado **03 10 00** (m²) · `1633` Acero refuerzo **03 20 00** (kg) · `1642` Concreto colado **03 30 00** (m³).
- vía helper `_crear_o_actualizar_partida()` (`diseno_estructural.py:263`).
- Cantidades de `takeoff_viga`/`takeoff_columna` (`calculo_estructural.py:376/411`).

**Frontend que lo dispara:**
- `app.js:2694` `btnGenElem` → `generarPartidasElem()` (`app.js:3628`) → POST `/generar-partidas` (líneas 3635, 3665).
- `app.js:3431` (generar en lote) → mismo endpoint.
- Botones HTML: `btn-diseno-generar-elem` ("📦 Generar Partidas CSI 03"), `btn-diseno-generar-todo`.

**Veredicto: 🔴 VIOLA la regla** (diseño concreto exporta partidas). **Eliminar.**

### Pasos PUNTO 2
1. **Backend** — deshabilitar `POST /diseno/casos/{cid}/generar-partidas` (`diseno_estructural.py:1599`): borrar el endpoint **o** devolver `410 Gone` ("diseño solo revisa; partidas de concreto salen del flujo ETABS"). Mantener `takeoff_*` y `ResultadoDiseno` (sirven para revisión).
2. **Frontend** — quitar botones `btn-diseno-generar-elem` + `btn-diseno-generar-todo` (HTML) y sus listeners (`app.js:2694`); borrar/neutralizar `generarPartidasElem()` (`3628`) y las llamadas en `3431/3635/3665`.
3. **Verificar** que `POST /casos/{cid}/calcular` (review, `585`) sigue intacto (NO crea partidas — correcto).

---

## PUNTO 4 — Diseño Acero y Diseño Concreto: solo revisan, jamás exportan fichas

**Inventario de generación de partidas en los módulos de DISEÑO:**

| Router | Endpoint | Línea | Qué crea | Acción |
|--------|----------|-------|----------|--------|
| diseno_estructural | `POST /casos/{cid}/generar-partidas` | 1599 | 03 10/20/30 concreto | 🔴 ELIMINAR (Punto 2) |
| diseno_estructural | `POST /{pid}/mamposteria` | 1729 | 04 20 00 + opt 03 20/03 30 | 🟠 confirmar (¿es "diseño"? — mampostería aparte) |
| acero_diseno | `POST /{pid}/acero-generar-partidas` | 375 | 05 10/05 20 acero | 🔴 ELIMINAR |
| acero_diseno | `POST /{pid}/import-etabs-acero` (flag `generar=true`) | 54 / 152-168 | 05 10/05 20 acero | 🔴 quitar el flag generar |
| acero_diseno | `POST /{pid}/conexion-generar-partida` | 459 | 05 + INSUMOS | 🟢 **CONSERVAR** (es el módulo Conexiones, Punto 3) |

**Read-only OK (no tocar):** `/casos/{cid}/calcular`, `/import-etabs-concreto`, `/import-etabs-acero-fuerzas`, `/placas-base-etabs`, todos los GET.

### Pasos PUNTO 4
1. **Backend acero** — deshabilitar `POST /diseno/{pid}/acero-generar-partidas` (`acero_diseno.py:375`) (borrar o 410).
2. **Backend acero** — en `POST /diseno/{pid}/import-etabs-acero` (`54`) quitar la rama `generar` (`152-168`) → que importe/revise sin crear partidas Div 05.
3. **Frontend** — quitar botón que llama `acero-generar-partidas` (`app.js:4843`) + el checkbox `acero-generar` (`app.js:4965`).
4. **NO tocar** `conexion-generar-partida` (`459`) ni su botón (`app.js:5742`) — es Conexiones (Punto 3).
5. **Mampostería** (`1729`): el usuario no la mencionó. **Decisión pendiente** — si "diseño = solo revisa" aplica también, eliminar; si es herramienta aparte, dejar. **Escalar.**

---

## PUNTO 3 — Conexiones por pyRevit: botón, CSV export/import, ficha con insumos

**Estado del botón:** 🟢 **EXISTE y está wired.** Tab "Conexiones" (`app.js:5089-5569`), conectado a `/conexion-acero/*` (catálogo, cálculo §J, CRUD, import lote ETABS).

**Ficha con INSUMOS (materiales + mano de obra):** 🟢 **FUNCIONA.**
- `acero_ficha.py:603 conexion_ficha()` resuelve ficha (CV/VV/CX/BP) y **emite insumos** (`672`).
- `acero_ficha.py:561 insumos_ficha()` lee BOM de `development\Template2_Updated\{v1.x}\fichas\fichas_*.json`.
- `acero_diseno.py:459 conexion-generar-partida` crea Partida Div 05 + **inserta `InsumoPartida`** separando `MANO_OBRA` vs materiales (`475-520`).

**CSV export de cantidad de conexiones:** 🔴 **NO EXISTE** (`export.py` no exporta conexiones).
**CSV import desde pyRevit (conteo de conexiones):** 🔴 **NO EXISTE.** Solo hay import de **fuerzas-nudo ETABS** (`conexion_acero.py:169 import-etabs-fuerzas`), que NO es un CSV de pyRevit con `{tipo, cantidad}`.

**Veredicto:** botón ✓ · ficha+insumos ✓ · **falta el puente pyRevit↔CSV (conteo).** El flujo hoy es: pegar fuerzas ETABS → §J → ficha+insumos. Falta: pyRevit determina conexiones → CSV con conteo → import → ficha×cantidad.

### Pasos PUNTO 3
1. **Definir contrato CSV pyRevit** (acordar columnas). Propuesta:
   `frame_o_nudo, tipo, perfil_vig, perfil_col, cantidad` (tipo ∈ VC_CORTANTE/VC_MOMENTO/VV/SOLDADA/PLACA_BASE).
2. **Backend EXPORT** — nuevo `GET /conexion-acero/{pid}/export-csv` → CSV con las conexiones resueltas + `cantidad` por ficha (plantilla/verificación para pyRevit). Reusar `conexion_ficha()`.
3. **Backend IMPORT** — nuevo `POST /conexion-acero/{pid}/import-pyrevit-csv` (multipart o texto): por cada fila → `conexion_ficha(perfil_vig, perfil_col, tipo)` → generar Partida Div 05 con insumos **× cantidad** (reusar la lógica de `conexion-generar-partida:459`, multiplicando cantidades de insumo por `cantidad`).
4. **Frontend** — en el tab Conexiones agregar: botón **"⬇ Exportar CSV conexiones"** (export) + botón **"⬆ Importar CSV pyRevit"** (file input → import). Mostrar resumen (n fichas, n insumos, costo).
5. **Validación** — cruzar: nº de conexiones del CSV pyRevit vs nº verificadas §J (avisar si difieren).

---

## PLAN DE EJECUCIÓN CONSOLIDADO (ordenado)

> ⚠️ Toca BD/endpoints/frontend. **Requiere confirmación explícita antes de ejecutar** (regla: no modificar sin OK). Backup BD antes.

**Fase A — Diseño = solo revisión (Puntos 2 + 4)**
- A1. Backend: 410/borrar `generar-partidas` (concreto, `diseno_estructural.py:1599`).
- A2. Backend: 410/borrar `acero-generar-partidas` (`acero_diseno.py:375`) + quitar flag `generar` en `import-etabs-acero` (`54/152-168`).
- A3. Frontend: quitar botones `btn-diseno-generar-elem`, `btn-diseno-generar-todo`, el de acero (`app.js:4843`), checkbox `acero-generar` (`4965`); limpiar `generarPartidasElem` + llamadas (`2694/3431/3628/3635/3665`).
- A4. Decisión mampostería (`1729`) — escalar.

**Fase B — Conexiones = puente pyRevit (Punto 3)**
- B1. Acordar contrato CSV (columnas).
- B2. Backend: `GET .../export-csv` (conteo conexiones).
- B3. Backend: `POST .../import-pyrevit-csv` → ficha + insumos × cantidad (reusa `459`).
- B4. Frontend: botones export/import en tab Conexiones + resumen.
- B5. Validación cruzada conteo vs §J.

**Sin cambios (correctos):** Punto 1 (contexto sísmico), `conexion-generar-partida` (ficha+insumos), todos los endpoints de cálculo/review.

**Resultado esperado:** Diseño Acero/Concreto **solo revisan** ETABS (DC, memorias) sin tocar el presupuesto. Las **partidas estructurales reales** entran por: (a) flujo ETABS de concreto separado [si se mantiene fuera de diseño], (b) **Conexiones** vía CSV pyRevit → ficha con insumos (materiales + mano de obra).
