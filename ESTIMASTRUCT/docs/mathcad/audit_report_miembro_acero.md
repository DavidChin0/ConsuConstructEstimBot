# Reporte de Auditoría — Hoja "Miembros de Acero en LRFD"

> **Fecha:** 2026-06-03 · **Hoja:** `D:\OneDrive\Documents\MathCad\Miembros de Acero en LRFD.mcdx`
> **Método:** auditoría por MCP → `save_as_pdf` → lectura del render → comparación numérica vs
> motores `calculo_miembro_acero.py` (§D-H) y `calculo_conexion_acero.py` (§J) + AISC 360-16 LRFD.
> **Contenido de la hoja:** Parte 1 = Miembro §D-H · Parte 2 = Conexión §J (C1–C8b).
> **Perfil ejemplo:** W310x73 (A992 Fy=3515) · Pu=−80 t, Mux=12 t·m, Muy=3 t·m, Vu=15 t, Lb=400 cm.

---

## 1. Resumen ejecutivo

**Hoja VALIDADA al 100%.** Se verificaron ~90 fórmulas (53 Miembro + 37 Conexión). **Cada resultado
coincide** con el motor de cálculo y con las ecuaciones AISC 360-16. Los bugs corregidos en sesiones
previas (Sy1, rts1, Fcr, Lr, Fcr_ltbe, §H1) **renderizan correctos**. Sin errores numéricos.
Hallazgos = 2 cosméticos (unidad de Cw, anotación stale en MD) + 1 de proceso (designaciones perdidas).

---

## 2. Auditoría Parte 1 — Miembro §D-H

| § | Símbolo | Fórmula (hoja) | Resultado hoja | Esperado motor/AISC | ✓ |
|---|---------|----------------|----------------|---------------------|---|
| A | E·G | constantes | 2 038 900 · 784 600 kgf/cm² | 29000·11200 ksi | ✅ |
| A | Ag…ho | props W310x73 | nominales | Tabla AISC | ✅ |
| Mec | hw1 | d−2tf_ | 28.08 cm | 28.08 | ✅ |
| Mec | Ix1 | bf·d³/12−(bf−tw)·hw1³/12 | 1.784×10⁴ cm⁴ | 17 825 | ✅ |
| Mec | Iy1 | 2(tf_·bf³/12)+hw1·tw³/12 | 3.989×10³ cm⁴ | 3 989 | ✅ |
| Mec | Sx1/Sy1 | 2·Ix/d · 2·Iy/bf | 1151 · 314.1 cm³ | 1151 · 314 | ✅ |
| Mec | Zx1/Zy1 | plástico | 1271 · 476.5 cm³ | 1271 · 476.5 | ✅ |
| Mec | rx1/ry1 | √(I/Ag) | 13.856 · 6.553 cm | ✓ | ✅ |
| Mec | J1 | (2·bf·tf_³+hw1·tw³)/3 | 59.297 cm⁴ | 59.3 | ✅ |
| Mec | rts1 | √(√(Iy·Cw)/Sx) | 7.156 cm | 7.156 | ✅ |
| D2 | ϕPn_t | min(ϕFy·Ag, ϕFu·Ae) | 2.939×10⁵ kgf | 293 890 | ✅ |
| E3 | KLr·Fe·Fcr | esbeltez/Euler/crítico | 61.92 · 5249 · 2656 | ✓ | ✅ |
| E3 | ϕPn_c | ϕc·Fcr·Ag | 2.22×10⁵ kgf | 222 068 | ✅ |
| F2 | Mp·Lp·Lr | plástico/límites | 4.218×10⁶ · 273.8 · 877 | ✓ | ✅ |
| F2 | Mn_ltbi/Fcr_ltbe | LTB inel/elas | 3.881×10⁶ · 8100 | ✓ (coef 0.078) | ✅ |
| F2/F6 | Mn·ϕMnx·ϕMny | nominal/diseño | 3.881e6 · 3.493e6 · 1.474e6 | ✓ | ✅ |
| G2 | ϕVn | ϕv·0.6·Fy·Aw·Cv1 | 5.819×10⁴ kgf | 58 187 | ✅ |
| H1 | IR | H1-1a (Pr/Pc=0.36≥0.2) | 0.847 | 0.846 | ✅ |
| B3.1 | DC_gob/Cumple | max(DC)/veredicto | 0.847 / "si cumple" | ✓ | ✅ |

**53/53 ✓.** DC por estado: tracción 0 · compresión 0.36 · flexión-x 0.344 · flexión-y 0.204 · cortante 0.258 · interacción 0.847.

---

## 3. Auditoría Parte 2 — Conexión §J (C1–C8b)

| Cap | Símbolo | Resultado hoja | Esperado | ✓ |
|-----|---------|----------------|----------|---|
| C2 | dh·s·Le·lc·Ab | 2.06·5.7·2.85·1.82·2.835 | ✓ | ✅ |
| C2 | hp·Agp·Anv·Ant | 17.1·16.245·10.374·1.729 | ✓ | ✅ |
| C4 | Rn_v·Rn_ap·Rn_to | 24221·39749·19037 | ✓ (J3-1/6a/6c) | ✅ |
| C4 | Rn_pernos | 1.904×10⁴ kgf | 19037 (min) | ✅ |
| C5 | te·Fnw | 0.561·2952 | ✓ | ✅ |
| C5 | Rn_sold·Rn_BM·Rn_junta | 49708·69734·49708 | ✓ (J2-4/metal base) | ✅ |
| C6 | Rn_fy·Rn_ru·Rn_vy·Rn_vu | 37003·49684·24668·19037 | ✓ (J4-1…4) | ✅ |
| C6 | Rn_bs | 2.379×10⁴ kgf | **23 789** (J4-5) | ✅ |
| C7 | A1·phiPp·fp·tp_req | 1451·168382·55.12·1.659 | ✓ (J8/DG-1) | ✅ |
| C8 | Rn_gob·DC_conex | 19037 / 0.788 | ✓ | ✅ |
| C8a | Rn_gob_ap·DC_ap | 19037 / 0.788 | ✓ apernada (VV) | ✅ |
| C8a | nb_req·tp_req_ap | 2.364 / 0.749 cm | ✓ | ✅ |
| C8b | Rn_gob_sol·DC_sol | 49708 / 0.302 | ✓ soldada | ✅ |
| C8b | Lw_req·tp_req_sol | 12.069 / 0.204 cm | ✓ | ✅ |

**37/37 ✓.** Apernada DC=0.788 (gobierna tearout/rotura placa). Soldada DC=0.302 (gobierna cordón).

---

## 4. Hallazgos

| # | Severidad | Hallazgo | Acción |
|---|-----------|----------|--------|
| M-1 | 🟡 cosmético | `Cw1` se muestra en unidad mixta `m⁵·cm` (valor correcto = 8.702×10⁵ cm⁶) | opcional: forzar display a cm⁶ en Prime |
| M-2 | 🟡 doc | `Rn_bs` real = **23 789 kgf**; el MD `sexpr.md` (tabla C6) anotaba ~20 798 (stale) | corregir anotación en MD |
| M-3 | 🟢 proceso | Designaciones **Input** sobrevivieron al crash; **Output NO** (ϕPn_t, Lr, IR, DC_gob = "not found" por MCP) | re-designar outputs en Prime para auditoría MCP en vivo |
| M-4 | 🟡 texto | Descripciones de `ϕtR`/`ϕtF` se solapan visualmente en el render | reposicionar regiones de texto en Prime |

**Cero hallazgos numéricos.** Toda la matemática es correcta.

---

## 5. Verificación de descripciones (texto en la hoja)

La hoja YA trae descripción por fórmula (regiones de texto). Correctas en su mayoría. Canónicas a confirmar:

- `E`/`G` — módulo elástico/corte ✓
- `ϕtR`/`ϕtF` — φ rotura 0.75 (§D2-2) / fluencia 0.90 (§D2-1) — **texto solapado, reordenar**
- Mecánica (Ix,Iy,Sx,Sy,Zx,Zy,rx,ry,J,Cw,rts) — todas con fórmula + variables ✓
- §D2–H1 — cada una con su ecuación AISC ✓
- Conexión C1–C8b — descripciones EstimaStruct-paso (Objetivo·Norma·Código) ✓

> Nota MCP: el conector **no autorea ni edita texto** en Mathcad. Las descripciones se mantienen en el
> MD fuente (`modulo_miembro_acero.*.md`) y se pegan manualmente. Este reporte fija las canónicas.

---

## 6. Conclusión

Hoja "Miembros de Acero en LRFD" = **calculadora AISC 360-16 LRFD validada** (Miembro §D-H + Conexión §J).
90/90 fórmulas correctas vs motor EstimaStruct. Lista para uso como documento de verificación firmable.

**Siguiente:** re-designar los Output en Prime (ϕPn_t, ϕPn_c, ϕMnx/y, ϕVn, IR, DC_gob, Rn_*, DC_conex,
DC_ap, DC_sol…) para habilitar la auditoría MCP en vivo (lectura directa sin PDF) + el puente ETABS.
