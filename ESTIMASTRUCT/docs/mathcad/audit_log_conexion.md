# Audit Log — Módulo Conexión de Acero §J

> **Fecha:** 2026-06-03 · **Motor auditado:** `backend\calculo_conexion_acero.py` (+ `perfiles_acero.py`, `acero_ficha.py`)
> **Método:** lectura línea-a-línea + verificación numérica contra `POST /conexion-acero/memoria-rapida`
> (VC cortante, SOLDADA, PLACA_BASE, W310X73). **Sin fórmulas inventadas.**
> Severidad: 🔴 alta · 🟠 media · 🟡 baja · 🟢 verificado OK.

---

## 1. Resumen ejecutivo

Motor **sólido**. §J2/J3/J4/J8 implementados con las ecuaciones correctas de AISC 360-16 y reproducen los ejemplos dentro de tolerancia. Incluye el **metal base J2-2** (que el módulo Soldadura viejo —ya borrado en R7— NO tenía → cierra ese gap). Sin fórmulas faltantes. Hallazgos = un tema de seguridad real (Fy de placa base) + simplificaciones conservadoras.

---

## 2. Hallazgos

### 🟠 C-1 — §J8 espesor de placa base usa el Fy de la columna, no el de la placa
`espesor_placa_base(Pu, Fy, …)` (línea 217) recibe `Fy` = el `acero` de la conexión. Para `PLACA_BASE` ese acero suele ser **A992 (columna, Fy=3515)**, pero la **placa base real es A36 (Fy=2531)**. `tp_req = l·√(2·fp/(0.90·Fy))` → con Fy mayor da `tp_req` **menor** → **espesor no conservador** (placa más delgada de lo debido).
**Recomendación:** pasar el Fy de la PLACA (input propio `Fy_placa`, default A36) a `espesor_placa_base`, separado del acero de la columna. **Impacto Mathcad:** en Cap. C7 usé `Fy_col`; cambiar a `Fy_placa`=2531 da `tp_req`≈1.65 cm (vs 1.41) — más realista.

### 🟠 C-3 — §J3 tearout usa una sola `lc` para todos los pernos
`rn_tearout(lc, t, Fu, n)` (línea 138) aplica la MISMA distancia libre `lc` a los `n` pernos. En realidad el perno de **borde** tiene `lc = Le − dh/2` y los **interiores** `lc = s − dh`, distintos. El motor toma una sola (la de borde, conservadora si es la menor).
**Recomendación:** separar tearout de borde vs interior, o documentar que `lc` debe ser la MENOR del grupo (conservador). **Impacto:** en el ejemplo tearout gobierna (19.04 t) — sensible.

### 🟡 C-2 — §J2 Fnw sin incremento direccional (θ=0)
`fnw_soldadura(FEXX, theta=0)` (línea 151) implementa `0.6·FEXX·(1+0.5·sin^1.5 θ)` pero usa **θ=0** por defecto → ignora el aumento hasta **1.5×** de filetes transversales (carga perpendicular al cordón). **Conservador** (deja capacidad sin usar). Correcto para diseño seguro; sub-óptimo para economía.
**Recomendación:** opcional, exponer θ del ángulo carga-cordón.

### 🟡 C-4 — §J8 A2 por defecto = A1 (sin confinamiento)
`calcular_conexion` usa `A2 = A1` si no se da el área del pedestal (línea ~342). El bono `√(A2/A1)` (hasta 2×) queda en 1.0 → **conservador**. Documentado; el usuario puede dar `A2` real.

### 🟡 C-5 — Agujeros estándar fijos (gap 0.16 cm)
`HOLE_GAP=0.16` (línea 51, 1.6 mm) asume agujero estándar. Agujeros sobre-dimensionados/ranurados (que reducen más el área neta y bajan φRn) NO se modelan. **Impacto:** bajo si se usan estándar.

---

## 3. Verificado OK 🟢

| Ítem | Línea | Verificación |
|------|-------|--------------|
| φ factores §J2/J3/J4/J8 | 40-46, 202 | 0.75/0.75/0.90/0.75/1.00/0.75/0.65 correctos |
| J3-1 corte | 113-115 | φ·Fnv·Ab·n (24.22 t ✓) |
| J3-6a aplastamiento | 132-135 | φ·2.4·db·t·Fu·n (39.75 t ✓) |
| J3-6c tearout | 138-140 | φ·1.2·lc·t·Fu·n (19.04 t ✓) |
| J3-3a combinado tracc-corte | 123-129 | F'nt = 1.3Fnt − Fnt/(φFnv)·frv ≤ Fnt |
| J2 te / Fnw / cordón / metal base | 146-165 | te=0.707w · Fnw=0.6FEXX · min(49.71, 69.73)=49.71 t ✓ |
| J4-1…J4-5 | 171-196 | fluencia/rotura/block shear correctos (37.00/49.69/24.67/19.04/20.80 t ✓) |
| J8 aplastamiento + DG-1 | 205-229 | φPp=168.4 t ✓ · tp_req=1.408 cm ✓ |
| metal base J2-2 (min) | 162-165 | cierra el gap del módulo Soldadura viejo (R7) |

---

## 4. Trazabilidad y reconstrucción

- **Fórmulas reconstruidas:** 0 (ninguna faltaba; todas en `rn_*` líneas 113-229).
- **Verificación numérica:** 3 tipos (VC cortante DC=0.788, SOLDADA DC=0.302, PLACA_BASE DC=0.475) — coinciden con la hoja Mathcad (Parte 2, Cap. C1–C8).
- **Soldadura:** el módulo standalone se borró en R7; su §J2 vive aquí (verificado equivalente + mejor: incluye metal base).

## 5. Acciones sugeridas (priorizadas)

1. 🟠 **C-1** — `Fy_placa` propio (A36) para el espesor de placa base. *(seguridad real)*
2. 🟠 **C-3** — tearout borde vs interior, o forzar `lc`=menor del grupo.
3. 🟡 **C-2 / C-4 / C-5** — θ direccional · A2 real · agujeros no-estándar (economía / completitud).

> Ninguna bloqueante. **C-1** es la única con impacto de seguridad (placa base más delgada de lo debido si se usa Fy de columna). Ya anotado en la hoja Mathcad Cap. C7 para usar `Fy_placa`.
