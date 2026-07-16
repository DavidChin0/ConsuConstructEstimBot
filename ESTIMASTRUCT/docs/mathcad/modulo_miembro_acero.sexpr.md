# Hoja Acero LRFD — Fórmulas en S-expr (copy-paste a Mathcad Prime) · CONTINUACIÓN: Conexión §J

> **Continuación.** La **Parte 1 (Miembro §D-H)** está en `modulo_miembro_acero.mcdx-author.md` (forma `:=`)
> y ya se pegó/validó en Prime — **no se repite aquí**. Este MD sigue con la **Parte 2: Conexión §J** en
> formato **S-expr** (ML lineal de Prime) para **pegar directo** en una región. Resultado y descripción APARTE.
> Fórmulas 1:1 de `calculo_conexion_acero.py`. Métrico **kgf · cm**.

---

## MANUAL — gramática S-expr de Prime (referencia)

| Construcción | S-expr |
|--------------|--------|
| definir `x :=` | `(:= (@LABEL VARIABLE x) BODY)` |
| evaluar `= res` | `(= EXPR (@RSCALE valor unidad))` |
| variable (operando) | nombre **pelado** |
| π / unidad / keyword | `(@LABEL CONSTANT π)` · `(@LABEL UNIT kgf)` · `(@LABEL KEYWORD if)` |
| `* / + - ^` | `(* a b)` `(/ a b)` `(+ a b)` `(- a b)` `(^ base exp)` (cadenas anidan a la izquierda) |
| √ | `(@NTHROOT 2 x)` |
| paréntesis | `(@PARENS x)` |
| ≤ ≥ < > | `(@LEQ a b)` `(@GEQ a b)` `(@LT a b)` `(@GT a b)` |
| `min/max/abs` | `(@APPLY min (@ARGS (@SEP a b)))` · 3 args: `(@SEP (@SEP a b) c)` |
| `if(c,a,b)` | `(@APPLY (@LABEL KEYWORD if) (@ARGS (@SEP (@SEP c a) b)))` |
| resultado con unidad | `(@RSCALE (@PARENS (* 5.819 (^ 10 4))) (@LABEL UNIT kgf))` |
| **resultado ADIMENSIONAL** | `(@RSCALE valor @RPLACEHOLDER)` — **NUNCA pelado** (ej. `(@RSCALE 0.847 @RPLACEHOLDER)`) |
| unidad compuesta | `(/ (@LABEL UNIT kgf) (^ (@LABEL UNIT cm) 2))` · kgf·cm = `(* (@LABEL UNIT kgf) (@LABEL UNIT cm))` |
| texto (string) | comillas **peladas** `"si cumple"` (NO `@STR`) · resultado = `(@RSCALE "si cumple" @RPLACEHOLDER)` |

> **El TARGET** lleva `(@LABEL VARIABLE x)`; **los operandos** van pelados. Pega cada línea en su región.
> Una conexión real usa UN tipo: VC cortante = C4+C6 · Soldada = C5+C6 · Placa base = C7. C8 toma el `min` aplicable.

---

## DESCRIPCIÓN POR FÓRMULA (formato EstimaStruct-paso)

Cada tabla bajo un Cap. trae, por fórmula, las columnas tipo `_paso(...)` del motor:

| Columna | Significado | Equivale en motor |
|---------|-------------|-------------------|
| **Símbolo** | nombre de la variable Mathcad | `simbolo` |
| **Objetivo** | qué calcula / para qué sirve | `etiqueta` |
| **Norma (Cap)** | sección/ecuación AISC 360-16 que la gobierna | `referencia` |
| **Código motor** | función Python que la implementa (`calculo_conexion_acero.py`) | `def` |
| **Resultado** | valor del ejemplo W310x73 (kgf·cm) | `valor` |

> Trazable: cada fórmula → su ecuación AISC → su función en el motor. Cero fórmulas inventadas.

---

## Cap. C1 — Materiales + electrodo + perno  (inputs · Tabla 2-4 / J2.5 / J3.2)
```
(:= (@LABEL VARIABLE Fyp) (* 2531 (/ (@LABEL UNIT kgf) (^ (@LABEL UNIT cm) 2))))
(:= (@LABEL VARIABLE Fup) (* 4078 (/ (@LABEL UNIT kgf) (^ (@LABEL UNIT cm) 2))))
(:= (@LABEL VARIABLE FEXX) (* 4920 (/ (@LABEL UNIT kgf) (^ (@LABEL UNIT cm) 2))))
(:= (@LABEL VARIABLE Fnt) (* 6328 (/ (@LABEL UNIT kgf) (^ (@LABEL UNIT cm) 2))))
(:= (@LABEL VARIABLE Fnv) (* 3797 (/ (@LABEL UNIT kgf) (^ (@LABEL UNIT cm) 2))))
(:= (@LABEL VARIABLE phi_sold) 0.75)
(:= (@LABEL VARIABLE phi_perno) 0.75)
(:= (@LABEL VARIABLE phi_fy) 0.90)
(:= (@LABEL VARIABLE phi_ru) 0.75)
(:= (@LABEL VARIABLE phi_vy) 1.00)
(:= (@LABEL VARIABLE phi_bs) 0.75)
```
| Símbolo | Qué es | Valor | Origen / cómo se define |
|---------|--------|-------|-------------------------|
| `Fyp`/`Fup` | fluencia/rotura de la PLACA (A36) | 2531 / 4078 kgf/cm² | **FIJO** `ACEROS["A36"]` (`perfiles_acero.py`) |
| `FEXX` | resistencia del electrodo (E70XX) | 4920 kgf/cm² | **FIJO** `FEXX_E70` (`perfiles_acero.py`) |
| `Fnt`/`Fnv` | tracción / cortante nominal del perno A325 (roscas EN corte) | 6328 / 3797 kgf/cm² | **FIJO** `PERNOS["A325"]{Fnt, Fnv_N}` |
| `phi_sold`/`phi_perno` | φ soldadura / perno | 0.75 / 0.75 | **FIJO** `PHI_SOLD`/`PHI_PERNO` (§J2.4 / §J3.6) |
| `phi_fy`/`phi_ru` | φ fluencia tracción / rotura | 0.90 / 0.75 | **FIJO** `PHI_FLUENCIA`/`PHI_ROTURA` (§J4.1 / J4.2) |
| `phi_vy`/`phi_bs` | φ fluencia cortante / block shear | 1.00 / 0.75 | **FIJO** `PHI_CORTE_FLU`/`PHI_BLOCK` (§J4.3 / J4.5) |

## Cap. C2 — Geometría de la conexión  (J3.3/J3.4)

> **Perfil de la conexión = W310x73** (viga y columna). **Reusa `d, bf, tf_, tw` de la Parte 1** (ya
> definidos en la hoja). Si pegas Conexión sola, define primero: `(:= d (* 31 cm))`, `(:= bf (* 25.4 cm))`,
> `(:= tf_ (* 1.46 cm))`, `(:= tw (* 0.89 cm))`.

**Inputs de diseño** (lo único elegido a mano):
```
(:= (@LABEL VARIABLE db) (* 1.9 (@LABEL UNIT cm)))
(:= (@LABEL VARIABLE nb) 3)
(:= (@LABEL VARIABLE tp) (* 0.95 (@LABEL UNIT cm)))
(:= (@LABEL VARIABLE w) (* 0.794 (@LABEL UNIT cm)))
(:= (@LABEL VARIABLE Lw) (* 40 (@LABEL UNIT cm)))
(:= (@LABEL VARIABLE gap) (* 0.16 (@LABEL UNIT cm)))
```
| Símbolo | Qué es | Origen / cómo se define |
|---------|--------|-------------------------|
| `db` | diámetro del perno | **elegido** (detalle de taller). Ej. Ø3/4"=1.9 cm |
| `nb` | número de pernos | **elegido** (cantidad en la fila vertical) |
| `tp` | espesor de la placa de conexión | **elegido** (plancha comercial). Ej. 3/8"=0.95 cm |
| `w` | pierna del filete de soldadura | **elegido** (si es soldada). Ej. 5/16"=0.794 cm |
| `Lw` | longitud del cordón de soldadura | **elegido** (= altura de placa, 1 o 2 lados) |
| `gap` | sobre-dimensión del agujero estándar | **FIJO** = `HOLE_GAP` = 0.16 cm (1.6 mm, agujero estándar, `calculo_conexion_acero.py`) |

**Geometría derivada** (fórmulas dependientes de `db`, `nb`, `tp`):
```
(:= (@LABEL VARIABLE dh) (= (+ db gap) (@RSCALE 2.06 (@LABEL UNIT cm))))
(:= (@LABEL VARIABLE s) (= (* 3 db) (@RSCALE 5.7 (@LABEL UNIT cm))))
(:= (@LABEL VARIABLE Le) (= (* 1.5 db) (@RSCALE 2.85 (@LABEL UNIT cm))))
(:= (@LABEL VARIABLE lc) (= (- Le (/ dh 2)) (@RSCALE 1.82 (@LABEL UNIT cm))))
(:= (@LABEL VARIABLE Ab) (= (* (/ (@LABEL CONSTANT π) 4) (^ db 2)) (@RSCALE 2.835 (^ (@LABEL UNIT cm) 2))))
(:= (@LABEL VARIABLE hp) (= (+ (* (@PARENS (- nb 1)) s) (* 2 Le)) (@RSCALE 17.1 (@LABEL UNIT cm))))
(:= (@LABEL VARIABLE Agp) (= (* tp hp) (@RSCALE 16.245 (^ (@LABEL UNIT cm) 2))))
(:= (@LABEL VARIABLE Agv) (= (* tp hp) (@RSCALE 16.245 (^ (@LABEL UNIT cm) 2))))
(:= (@LABEL VARIABLE Anv) (= (- Agp (* (* nb dh) tp)) (@RSCALE 10.374 (^ (@LABEL UNIT cm) 2))))
(:= (@LABEL VARIABLE Ant) (= (* lc tp) (@RSCALE 1.729 (^ (@LABEL UNIT cm) 2))))
```
| Símbolo | Objetivo (qué calcula) | Norma (Cap) | Código motor | Resultado |
|---------|------------------------|-------------|--------------|-----------|
| dh | Ø del agujero = db + holgura estándar | AISC §J3.2 | `_geometria` | 2.06 cm |
| s | gramil entre pernos (mínimo 3·db) | §J3.3 | `_geometria` | 5.7 cm |
| Le | distancia perno-borde (mínimo 1.5·db) | §J3.4 | `_geometria` | 2.85 cm |
| lc | distancia libre al borde (para tearout) | §J3.10 | `_geometria` | 1.82 cm |
| Ab | área bruta de un perno (π/4·db²) | §J3.6 | `_area_perno` | 2.835 cm² |
| hp | altura de la placa = (nb−1)·s + 2·Le | layout taller | `_geometria` | 17.1 cm |
| Agp / Agv | área bruta de la placa (tracción / cortante) | §J4 | `_geometria` | 16.245 cm² |
| Anv | área NETA a cortante = Agp − nb·dh·tp | §J4.2 (§B4.3b) | `_geometria` | 10.374 cm² |
| Ant | área NETA a tracción = lc·tp | §J4.3 (§B4.3b) | `_geometria` | 1.729 cm² |

## Cap. C3 — Demanda  (inputs · J1.1)
```
(:= (@LABEL VARIABLE Vu_c) (* 15000 (@LABEL UNIT kgf)))
(:= (@LABEL VARIABLE Nu_c) (* 0 (@LABEL UNIT kgf)))
(:= (@LABEL VARIABLE Pu_c) (* 80000 (@LABEL UNIT kgf)))
```
| Símbolo | Qué es | Origen / cómo se define |
|---------|--------|-------------------------|
| `Vu_c` | cortante último de la conexión | **de ETABS** (`caso.vu_t`), combo LRFD gobernante |
| `Nu_c` | axial (tracción) de la conexión | **de ETABS** (`caso.nu_t`) |
| `Pu_c` | axial de columna (solo placa base) | **de ETABS** (`caso.pu_t`, reacción FZ del nudo) |

## Cap. C4 — §J3 Pernos  (J3-1 · J3-6a · J3-6c)
```
(:= (@LABEL VARIABLE Rn_v) (= (* (* (* phi_perno Fnv) Ab) nb) (@RSCALE 24223 (@LABEL UNIT kgf))))
(:= (@LABEL VARIABLE Rn_ap) (= (* (* phi_perno (@PARENS (* (* (* 2.4 db) tp) Fup))) nb) (@RSCALE 39748 (@LABEL UNIT kgf))))
(:= (@LABEL VARIABLE Rn_to) (= (* (* phi_perno (@PARENS (* (* (* 1.2 lc) tp) Fup))) nb) (@RSCALE 19037 (@LABEL UNIT kgf))))
(:= (@LABEL VARIABLE Rn_pernos) (= (@APPLY min (@ARGS (@SEP (@SEP Rn_v Rn_ap) Rn_to))) (@RSCALE 19037 (@LABEL UNIT kgf))))
```
| Símbolo | Objetivo (qué calcula) | Norma (Cap) | Código motor | Resultado |
|---------|------------------------|-------------|--------------|-----------|
| Rn_v | resistencia del grupo de pernos a CORTE | AISC §J3.6 (ec. J3-1) | `rn_corte_pernos` | 24223 kgf |
| Rn_ap | APLASTAMIENTO de la placa contra el perno | §J3.10 (ec. J3-6a) | `rn_aplastamiento` | 39748 kgf |
| Rn_to | DESGARRE de borde (tear-out) | §J3.10 (ec. J3-6c) | `rn_tearout` | 19037 kgf |
| Rn_pernos | gobernante de pernos = el MENOR de los 3 | §J3.10 | `min(...)` | **19037 kgf** |

## Cap. C5 — §J2 Soldadura  (J2-3/4 · metal base J2-2)
```
(:= (@LABEL VARIABLE te) (= (* 0.707 w) (@RSCALE 0.5614 (@LABEL UNIT cm))))
(:= (@LABEL VARIABLE Fnw) (= (* 0.6 FEXX) (@RSCALE 2952 (/ (@LABEL UNIT kgf) (^ (@LABEL UNIT cm) 2)))))
(:= (@LABEL VARIABLE Rn_sold) (= (* (* phi_sold Fnw) (@PARENS (* te Lw))) (@RSCALE 49714 (@LABEL UNIT kgf))))
(:= (@LABEL VARIABLE Rn_BM) (= (* (* (* phi_ru 0.6) Fup) (@PARENS (* tp Lw))) (@RSCALE 69734 (@LABEL UNIT kgf))))
(:= (@LABEL VARIABLE Rn_junta) (= (@APPLY min (@ARGS (@SEP Rn_sold Rn_BM))) (@RSCALE 49714 (@LABEL UNIT kgf))))
```
| Símbolo | Objetivo (qué calcula) | Norma (Cap) | Código motor | Resultado |
|---------|------------------------|-------------|--------------|-----------|
| te | garganta efectiva del filete (0.707·w) | AISC §J2.2a | `garganta_filete` | 0.5614 cm |
| Fnw | resistencia nominal del metal de soldadura (0.6·FEXX, θ=0) | §J2.4 (Tabla J2.5) | `fnw_soldadura` | 2952 kgf/cm² |
| Rn_sold | resistencia del CORDÓN de soldadura | §J2.4 (ec. J2-4) | `rn_soldadura` | 49714 kgf |
| Rn_BM | resistencia del METAL BASE a cortante | §J2.4 / §J4.2 | `rn_metal_base_corte` | 69734 kgf |
| Rn_junta | gobernante junta soldada = min(cordón, base) | §J2.4 | `min(...)` | **49714 kgf** |

## Cap. C6 — §J4 Elementos (placa)  (J4-1…J4-5)
```
(:= (@LABEL VARIABLE Ae_p) Agp)
(:= (@LABEL VARIABLE Rn_fy) (= (* (* phi_fy Fyp) Agp) (@RSCALE 37004 (@LABEL UNIT kgf))))
(:= (@LABEL VARIABLE Rn_ru) (= (* (* phi_ru Fup) Ae_p) (@RSCALE 49685 (@LABEL UNIT kgf))))
(:= (@LABEL VARIABLE Rn_vy) (= (* (* (* phi_vy 0.6) Fyp) Agv) (@RSCALE 24670 (@LABEL UNIT kgf))))
(:= (@LABEL VARIABLE Rn_vu) (= (* (* (* phi_ru 0.6) Fup) Anv) (@RSCALE 19037 (@LABEL UNIT kgf))))
(:= (@LABEL VARIABLE bs_rotura) (+ (* (* 0.6 Fup) Anv) (* Fup Ant)))
(:= (@LABEL VARIABLE bs_fluenc) (+ (* (* 0.6 Fyp) Agv) (* Fup Ant)))
(:= (@LABEL VARIABLE Rn_bs) (= (* phi_bs (@APPLY min (@ARGS (@SEP bs_rotura bs_fluenc)))) (@RSCALE 23789 (@LABEL UNIT kgf))))
```
| Símbolo | Objetivo (qué calcula) | Norma (Cap) | Código motor | Resultado |
|---------|------------------------|-------------|--------------|-----------|
| Rn_fy | FLUENCIA en área bruta a tracción | AISC §J4.1 (ec. J4-1) | `rn_fluencia_traccion` | 37004 kgf |
| Rn_ru | ROTURA en área neta a tracción | §J4.1 (ec. J4-2) | `rn_rotura_traccion` | 49685 kgf |
| Rn_vy | FLUENCIA por cortante en área bruta | §J4.2 (ec. J4-3) | `rn_fluencia_corte` | 24670 kgf |
| Rn_vu | ROTURA por cortante en área neta | §J4.2 (ec. J4-4) | `rn_rotura_corte` | 19037 kgf |
| Rn_bs | BLOQUE de cortante (block shear) | §J4.3 (ec. J4-5) | `rn_block_shear` | 23789 kgf (gobierna bs_fluenc) |

> `Ant` depende del layout de pernos — ajústala a tu detalle. No gobierna en el ejemplo (gobierna tearout).

## Cap. C7 — §J8 Placa base  (J8 + Design Guide 1)
```
(:= (@LABEL VARIABLE fc) (* 210 (/ (@LABEL UNIT kgf) (^ (@LABEL UNIT cm) 2))))
(:= (@LABEL VARIABLE Fy_placa) (* 2531 (/ (@LABEL UNIT kgf) (^ (@LABEL UNIT cm) 2))))
(:= (@LABEL VARIABLE Bpl) (= (+ bf (* 10 (@LABEL UNIT cm))) (@RSCALE 35.4 (@LABEL UNIT cm))))
(:= (@LABEL VARIABLE Npl) (= (+ d (* 10 (@LABEL UNIT cm))) (@RSCALE 41 (@LABEL UNIT cm))))
(:= (@LABEL VARIABLE A1) (= (* Bpl Npl) (@RSCALE 1451 (^ (@LABEL UNIT cm) 2))))
(:= (@LABEL VARIABLE A2) A1)
(:= (@LABEL VARIABLE ratio_j8) (= (@APPLY min (@ARGS (@SEP (@NTHROOT 2 (/ A2 A1)) 2))) (@RSCALE 1 @RPLACEHOLDER)))
(:= (@LABEL VARIABLE Pp) (= (@APPLY min (@ARGS (@SEP (* (* (* 0.85 fc) A1) ratio_j8) (* (* 1.7 fc) A1)))) (@RSCALE 259095 (@LABEL UNIT kgf))))
(:= (@LABEL VARIABLE phiPp) (= (* 0.65 Pp) (@RSCALE 168399 (@LABEL UNIT kgf))))
(:= (@LABEL VARIABLE fp) (= (/ Pu_c (* Bpl Npl)) (@RSCALE 55.12 (/ (@LABEL UNIT kgf) (^ (@LABEL UNIT cm) 2)))))
(:= (@LABEL VARIABLE m_pl) (= (/ (@PARENS (- Npl (* 0.95 d))) 2) (@RSCALE 5.78 (@LABEL UNIT cm))))
(:= (@LABEL VARIABLE n_pl) (= (/ (@PARENS (- Bpl (* 0.80 bf))) 2) (@RSCALE 7.54 (@LABEL UNIT cm))))
(:= (@LABEL VARIABLE n_prima) (= (/ (@NTHROOT 2 (* d bf)) 4) (@RSCALE 7.02 (@LABEL UNIT cm))))
(:= (@LABEL VARIABLE l_vol) (= (@APPLY max (@ARGS (@SEP (@SEP m_pl n_pl) n_prima))) (@RSCALE 7.54 (@LABEL UNIT cm))))
(:= (@LABEL VARIABLE tp_req) (= (* l_vol (@NTHROOT 2 (/ (* 2 fp) (@PARENS (* 0.90 Fy_placa))))) (@RSCALE 1.65 (@LABEL UNIT cm))))
```
| Símbolo | Objetivo (qué calcula) | Norma (Cap) | Código motor | Resultado |
|---------|------------------------|-------------|--------------|-----------|
| `fc` | f'c del concreto del pedestal | ACI 318 | input | 210 kgf/cm² |
| `Fy_placa` | fluencia de la placa (A36, **NO** la de la columna — audit C-1) | — | `ACEROS["A36"]` (FIJO) | 2531 kgf/cm² |
| `d`/`bf` | peralte/ancho del perfil columna W310x73 | — | reusados Parte 1 | 31 / 25.4 cm |
| Bpl·Npl | dimensiones de la placa (bf+10 · d+10) | AISC DG-1 | `espesor_placa_base` | 35.4 · 41 cm |
| A1·A2 | área placa · área pedestal (confinamiento A2≥A1) | §J8 | `rn_aplastamiento_concreto` | 1451 · 1451 cm² |
| phiPp | resistencia del concreto al APLASTAMIENTO = 0.65·min(0.85·fc·A1·√(A2/A1), 1.7·fc·A1) | §J8 (ec. J8-1/2) | `rn_aplastamiento_concreto` | **168399 kgf** |
| fp | presión de contacto bajo la placa = Pu/(Bpl·Npl) | DG-1 | `espesor_placa_base` | 55.12 kgf/cm² |
| l_vol | voladizo crítico = max(m, n, n') | DG-1 | `espesor_placa_base` | 7.54 cm |
| tp_req | espesor REQUERIDO de la placa = l·√(2·fp/(0.90·Fy_placa)) | AISC Design Guide 1 | `espesor_placa_base` | **1.65 cm** |

> **Auditoría C-1:** `Fy_placa` = A36 (2531), NO el de la columna. Con A992 daría tp_req=1.41 (no conservador).

## Cap. C8 — Verificación  (§B3.1 / J1.1)
```
(:= (@LABEL VARIABLE Rn_gob) (= (@APPLY min (@ARGS (@SEP (@SEP (@SEP (@SEP (@SEP (@SEP Rn_pernos Rn_junta) Rn_fy) Rn_ru) Rn_vy) Rn_vu) Rn_bs))) (@RSCALE 19037 (@LABEL UNIT kgf))))
(:= (@LABEL VARIABLE DC_conex) (= (/ Vu_c Rn_gob) (@RSCALE 0.788 @RPLACEHOLDER)))
(:= (@LABEL VARIABLE cumple_conex) (= (@APPLY (@LABEL KEYWORD if) (@ARGS (@SEP (@SEP (@LEQ DC_conex 1) "si cumple") "revisar"))) (@RSCALE "si cumple" @RPLACEHOLDER)))
```
| Símbolo | Objetivo (qué calcula) | Norma (Cap) | Código motor | Resultado |
|---------|------------------------|-------------|--------------|-----------|
| Rn_gob | capacidad GOBERNANTE = min de los estados aplicables al tipo de conexión | AISC §B3.1 | `_estados_por_tipo` + min | 19037 kgf (tearout) |
| DC_conex | relación Demanda/Capacidad = Vu_c / Rn_gob | §B3.1 (LRFD) | `calcular_conexion` | **0.788** |
| cumple_conex | veredicto: "si cumple" si DC ≤ 1 | §B3.1 | `if(...)` | "si cumple" |

> `Rn_gob` (C8) = min de TODOS los estados presentes (híbrido/conservador). Para una conexión de UN solo tipo,
> usa la auditoría separada: **C8a apernada** (VV) · **C8b soldada** (SOLDADA) · **C7** placa base.

## Cap. C8a — Auditoría conexión APERNADA  (tipo VV · §J3 + §J4)

> Estados del motor (`_estados_por_tipo("VV")`): **pernos (C4) + elementos j4 (C6)**. SIN soldadura.
> Capacidad = min(Rn_pernos, Rn_fy, Rn_ru, Rn_vy, Rn_vu, Rn_bs).
```
(:= (@LABEL VARIABLE Rn_gob_ap) (= (@APPLY min (@ARGS (@SEP (@SEP (@SEP (@SEP (@SEP Rn_pernos Rn_fy) Rn_ru) Rn_vy) Rn_vu) Rn_bs))) (@RSCALE 19037 (@LABEL UNIT kgf))))
(:= (@LABEL VARIABLE DC_ap) (= (/ Vu_c Rn_gob_ap) (@RSCALE 0.788 @RPLACEHOLDER)))
(:= (@LABEL VARIABLE cumple_ap) (= (@APPLY (@LABEL KEYWORD if) (@ARGS (@SEP (@SEP (@LEQ DC_ap 1) "cumple") "revisar"))) (@RSCALE "cumple" @RPLACEHOLDER)))
```
| Símbolo | Objetivo (qué comprueba) | Norma (Cap) | Código motor | Resultado |
|---------|--------------------------|-------------|--------------|-----------|
| Rn_gob_ap | capacidad gobernante apernada = min(pernos, elementos) | AISC §J3 + §J4 | `_estados_por_tipo("VV")` | 19037 kgf |
| DC_ap | Demanda/Capacidad = Vu_c / Rn_gob_ap | §B3.1 (LRFD) | `calcular_conexion` | **0.788** ✓ |
| cumple_ap | veredicto apernada (DC ≤ 1) | §B3.1 | `if(...)` | "cumple" |

> Gobierna a 19037 kgf: **empatan desgarre de borde (Rn_to, C4) y rotura por cortante de la placa (Rn_vu, C6)** — ambos por agujeros. Sensibles a `Le` y `tp`.

**Diseño resultante (lo calculado) — APERNADA**
```
(:= (@LABEL VARIABLE nb_req) (= (/ (* Vu_c nb) Rn_pernos) (@RSCALE 2.36 @RPLACEHOLDER)))
(:= (@LABEL VARIABLE tp_req_ap) (= (/ Vu_c (* (* (* phi_ru 0.6) Fup) (@PARENS (- hp (* nb dh))))) (@RSCALE 0.748 (@LABEL UNIT cm))))
```
| Elemento | Qué se calcula | Norma | Requerido (calc) | Provisto | Origen |
|----------|----------------|-------|------------------|----------|--------|
| Pernos | nb equiv. a demanda = nb·DC_ap = Vu·nb/Rn_pernos | §J3 | nb_req=2.36 → **3** | 3 · Ø db=1.9 cm (A325) | C2/C4 |
| Placa (espesor) | tp_req = Vu/(φ·0.6·Fup·(hp−nb·dh)) | §J4.2 | tp_req=**0.75 cm** | tp=0.95 cm | C6 |
| Placa (alto) | hp = (nb−1)·s + 2·Le | layout | — | hp=17.1 cm | C2 |
| Gramil/borde | s=3·db · Le=1.5·db | §J3.3/J3.4 | — | s=5.7 · Le=2.85 cm | C2 |
| Material placa | A36 | — | — | Fyp=2531 · Fup=4078 | C1 |

> Pernos: 3 Ø3/4" A325 cubren (nb·DC=2.36 ≤ 3). Placa 0.95 cm > tp_req 0.75 cm → OK. **Build:** placa 0.95×17.1 cm A36 + 3 pernos Ø3/4" A325.

## Cap. C8b — Auditoría conexión SOLDADA  (tipo SOLDADA · §J2)

> Estado del motor (`_estados_por_tipo("SOLDADA")`): **solo junta soldada (C5)** = min(cordón, metal base).
> Sin agujeros → los elementos (C6) van con área BRUTA y no gobiernan.
```
(:= (@LABEL VARIABLE Rn_gob_sol) (= (@APPLY min (@ARGS (@SEP Rn_sold Rn_BM))) (@RSCALE 49714 (@LABEL UNIT kgf))))
(:= (@LABEL VARIABLE DC_sol) (= (/ Vu_c Rn_gob_sol) (@RSCALE 0.302 @RPLACEHOLDER)))
(:= (@LABEL VARIABLE cumple_sol) (= (@APPLY (@LABEL KEYWORD if) (@ARGS (@SEP (@SEP (@LEQ DC_sol 1) "cumple") "revisar"))) (@RSCALE "cumple" @RPLACEHOLDER)))
```
| Símbolo | Objetivo (qué comprueba) | Norma (Cap) | Código motor | Resultado |
|---------|--------------------------|-------------|--------------|-----------|
| Rn_gob_sol | capacidad gobernante soldada = min(cordón, metal base) | AISC §J2.4 | `_estados_por_tipo("SOLDADA")` | 49714 kgf |
| DC_sol | Demanda/Capacidad = Vu_c / Rn_gob_sol | §B3.1 (LRFD) | `calcular_conexion` | **0.302** ✓ |
| cumple_sol | veredicto soldada (DC ≤ 1) | §B3.1 | `if(...)` | "cumple" |

> Gobierna el **cordón (Rn_sold, C5)** = 49714 < metal base 69734. DC bajo (0.30) = amplia reserva.
> Para chequear la placa soldada: elementos C6 con área **bruta** `Agp` (sin `Anv`/block shear).

**Diseño resultante (lo calculado) — SOLDADA**
```
(:= (@LABEL VARIABLE Lw_req) (= (/ Vu_c (* (* phi_sold Fnw) te)) (@RSCALE 12.07 (@LABEL UNIT cm))))
(:= (@LABEL VARIABLE tp_req_sol) (= (/ Vu_c (* (* (* phi_ru 0.6) Fup) Lw)) (@RSCALE 0.204 (@LABEL UNIT cm))))
```
| Elemento | Qué se calcula | Norma | Requerido (calc) | Provisto | Origen |
|----------|----------------|-------|------------------|----------|--------|
| Cordón (longitud) | Lw_req = Vu/(φ·Fnw·te) | §J2.4 | Lw_req=**12.07 cm** | Lw=40 cm (2×20) | C2/C5 |
| Cordón (pierna) | w → garganta te=0.707·w | §J2.2 | — | w=0.794 cm (5/16") · te=0.5614 | C2/C5 |
| Electrodo | E70XX | Tabla J2.5 | — | FEXX=4920 | C1 |
| Placa (espesor) | tp_req = Vu/(φ·0.6·Fup·Lw) | §J4.2 | tp_req=**0.20 cm** | tp=0.95 cm | C6 |
| Material placa | A36 | — | — | Fyp=2531 · Fup=4078 | C1 |

> Cordón: Lw_req 12.07 cm ≪ Lw 40 cm → mucha reserva (basta 1 lado ~12 cm, se usan 2×20). Placa 0.95 ≫ tp_req 0.20 cm. **Build:** placa 0.95 cm A36 + filete 5/16" E70, Lw=40 cm.

---

> **Confirmadas:** `if`, `min`, `max`, `@NTHROOT 2`, `@GEQ`, `@LEQ`, `@RSCALE` (con unidad, `@RPLACEHOLDER` adimensional/string), `@PARENS`, `@SEP`, strings con comillas peladas `"..."`.
> **A verificar al pegar:** `@GT`/`@LT` (>,<), `@APPLY abs`, `@ARGS` de 1 arg.
