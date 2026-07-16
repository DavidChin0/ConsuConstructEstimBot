# Validación MCP — Hoja Miembro Acero LRFD  ·  Puente ETABS / EstimaStruct ↔ Mathcad

> **Fecha:** 2026-06-03 · **Hoja:** `D:\OneDrive\Documents\MathCad\Miembros de Acero en LRFD.mcdx`
> **Método:** variables DESIGNADAS Input/Output en Prime → leídas/escritas por MCP (alias) → comparadas
> contra el motor `calculo_miembro_acero.py`. La hoja queda como **calculadora auditable manejable por API**.

---

## 1. Requisito descubierto: DESIGNACIÓN

El MCP `get_input`/`get_real_output`/`set_real_input` **solo ven variables DESIGNADAS** (panel
**Input/Output Designation** de Prime + guardar). Globales tecleados sin designar → `"not found"`.
No hay tool para designar ni para autorear ecuaciones (manual en Prime). Confirmado en 2 hojas.

---

## 2. Validación en vivo (caso W310X73 A992, Pu=-80 t)

Cada variable leída por MCP, convertida de SI a ingeniería, vs el motor:

| Variable | MCP (SI base) | → ingeniería | Motor | ✓ |
|----------|---------------|--------------|-------|---|
| `Fy` | 344 703 747 Pa | 3515 kgf/cm² | 3515 | ✅ |
| `Ag` | 0.00929 m² | 92.9 cm² | 92.9 | ✅ |
| `Zx` | 1.2 L | 1200 cm³ | 1200 | ✅ |
| `Pu` | −784 532 N | −80000 kgf | −80000 | ✅ |
| `ϕPn_t` | 2 882 068 N | 293 890 kgf | 293 889 | ✅ |
| `ϕPn_c` | 2 177 554 N | 222 049 kgf | 222 049 | ✅ |
| `ϕMnx` | 342 558 J | 3 493 100 kgf·cm | 3 493 100 | ✅ |
| `ϕMny` | 144 569 J | 1 474 200 kgf·cm | 1 474 200 | ✅ |
| `ϕVn` | 570 623 N | 58 187 kgf | 58 187 | ✅ |
| `Lr` | 8.770 m | 877 cm | 877 | ✅ |
| `IR` | 0.8465 | — | 0.8465 | ✅ |

**11/11 coinciden** → las fórmulas de la hoja están **validadas contra el motor por MCP**, no solo visualmente.

---

## 3. Prueba del PUENTE (cambio de carga en vivo)

```
set_real_input("Pu", -1176798)   # -120000 kgf (simula nueva carga ETABS)
sync_worksheet()
get_input("IR")  →  1.0267        # antes 0.8465  → ahora NO cumple (>1.0)
get_input("ϕPn_c") → 222049 kgf   # capacidad NO cambia (no depende de la carga)  ✓
```
Coincide con el cálculo manual (Pr/Pc=0.54 → H1-1a → IR≈1.027). **La hoja recalcula al inyectar
cargas por MCP.** (Restaurado a Pu=-80000; no se guardó → archivo en disco intacto.)

---

## 4. Arquitectura del puente  (EstimaStruct / ETABS → Mathcad → verificación)

```
   ETABS  (cargas LRFD por combo) ──set_real_input──►  Pu, Mux, Muy, Vu, Lb, K
   EstimaStruct (perfil + props)  ──set_real_input──►  Ag, d, bf, tf_, tw, hw, Zx, Sx, Zy, Sy, rx, ry, rts, J, ho, Fy, Fu
                                                        │
                                                  sync_worksheet
                                                        │
   hoja Mathcad (AISC §D-H, auditable) ──get_real_output──►  ϕPn_t/c, ϕMnx/y, ϕVn, IR, DC_gob, Cumple
                                                        │
                                          EstimaStruct guarda DC / genera partida / reporte
```

**Uso:** EstimaStruct manda perfil+cargas → la hoja Mathcad (firmable por ingeniero) devuelve el DC
verificado contra AISC. Cada cambio de sección (EstimaStruct) o de carga (ETABS) re-corre la hoja.

---

## 5. Unidades — el MCP trabaja en SI base (¡convertir!)

`set_real_input` con `units="kgf"` → **rechazado** (`preserve_worksheet_units`). Usar **SI base** (sin arg units):

| Magnitud | Unidad MCP (SI) | Conversión a/desde ingeniería |
|----------|-----------------|-------------------------------|
| esfuerzo | Pa | kgf/cm² = Pa / 98066.5 |
| área | m² | cm² = m² × 10 000 |
| volumen (Z,S) | L (litro) | cm³ = L × 1000 |
| fuerza | N | kgf = N / 9.80665 |
| momento | J (= N·m) | kgf·cm = J × 10.1972 |
| longitud | m | cm = m × 100 |

> **Para la integración:** EstimaStruct/ETABS deben convertir a SI antes de `set_real_input` y de SI al leer.

## 6. Capacidades MCP confirmadas

| Operación | Estado |
|-----------|--------|
| open · sync · save (mcdx/pdf/rtf/xps) · close · version · flags | ✅ |
| `get_input` / `get_real_output` / `set_real_input` (variable DESIGNADA, en SI) | ✅ |
| variable NO designada | ⛔ "not found" |
| autorear ecuaciones · editar texto · designar | ⛔ (manual en Prime) |
| `set` con `units="kgf"` | ⛔ usar SI base |
| editar `.mcdx` directo (ZIP + `worksheet.xml` `<ml:real>`) | ✅ (fuera de MCP) |
