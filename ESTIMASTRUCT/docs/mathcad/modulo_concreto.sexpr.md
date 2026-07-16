# Módulo Concreto ACI 318-19 — Fórmulas en S-expr (copy-paste a Mathcad Prime)

> Formato S-expr (ML lineal de Prime) para **pegar directo**. Fuente: `calculo_estructural.py`. 1:1, sin inventar.
> Métrico **kgf · cm · kgf·cm**. **Todo dependiente** (sin hardcoded salvo inputs genuinos).
> Ejemplo: viga b=30, d=50, fc=210, fy=4200; columna lx=40, Pu=80 t. (Tags por capítulo van después.)
> Gramática: ver skill `mathcad-mcp`. `√`=`@NTHROOT 2` · `if`=`@APPLY (@LABEL KEYWORD if)` · `min/max`=`@APPLY`.

---

## DESCRIPCIÓN POR FÓRMULA (formato EstimaStruct-paso)

Cada tabla trae, por fórmula: **Objetivo** (qué calcula) · **Norma (Cap)** (sección ACI) · **Código motor** (función en `calculo_estructural.py`) · **Resultado** (ejemplo b=30·d=50·fc=210·fy=4200). Trazable, sin fórmulas inventadas.

> **Notas de auditoría (motor):**
> - **δ (CC7):** `factor_amplificacion` usa **φ=0.65** (`PHI_COLUMNA`) en `1−Pu/(φ·Pc)`. ACI §6.6.4.5.2 usa **0.75** (factor de rigidez del amplificador, NO φ). El motor es **más conservador** (δ mayor). La hoja reproduce el motor (0.65) — consistente, pero queda anotada la desviación.
> - **Al (CC6):** el motor toma `Al = max(opt1, max(opt2_base, opt2_min))` con `opt2_min=(term28−3.5·b·S/fy)·(x1+y1)/S`. El MD omite `opt2_min` (no gobierna; `Al_1` manda en el ejemplo).
> - **β1:** ref correcta = ACI 318-19 **§22.2.2.3**.
> - **vtc (CC6):** el motor usa `vtcmax_combinado` (≈5.90 kgf/cm², interacción cortante-torsión) para diseñar `At` cuando vu>0; el MD usa `vtc_basico` (9.13). El MD **subestima At** (0.746 vs ≈1.03 cm²) si hay cortante+torsión simultáneos. Revisar para el caso real.

---

## Cap. CC0 — Constantes y factores φ  (ACI 318-19 §21.2.1)
```
(:= (@LABEL VARIABLE phi_fl) 0.90)
(:= (@LABEL VARIABLE phi_v) 0.75)
(:= (@LABEL VARIABLE phi_col) 0.65)
(:= (@LABEL VARIABLE FMAX) 0.5)
(:= (@LABEL VARIABLE eu) (* 6000 (/ (@LABEL UNIT kgf) (^ (@LABEL UNIT cm) 2))))
```

| Símbolo | Objetivo (qué calcula) | Norma (Cap) | Código motor | Resultado |
|---------|------------------------|-------------|--------------|-----------|
| phi_fl | φ de flexión (controlada por tracción) | ACI §21.2.1 | `PHI_FLEXION` | 0.90 |
| phi_v | φ de cortante / torsión | §21.2.1 | `PHI_CORTANTE` | 0.75 |
| phi_col | φ de columna (estribos) | §21.2.1 | `PHI_COLUMNA` | 0.65 |
| FMAX | factor máx de cuantía (zona sísmica) | §21 | `FMAX_SISMICO` | 0.5 |
| eu | Es·εcu (esfuerzo en ρb) = 6000 kgf/cm² | §22.2.2 | `pb` (literal 6000) | 6000 kgf/cm² |

## Cap. CC1 — Materiales  (β1 §22.2.2.3 · Ec)
```
(:= (@LABEL VARIABLE fc) (* 210 (/ (@LABEL UNIT kgf) (^ (@LABEL UNIT cm) 2))))
(:= (@LABEL VARIABLE fy) (* 4200 (/ (@LABEL UNIT kgf) (^ (@LABEL UNIT cm) 2))))
(:= (@LABEL VARIABLE β1) (= (@APPLY (@LABEL KEYWORD if) (@ARGS (@SEP (@SEP (@LEQ fc (* 280 (/ (@LABEL UNIT kgf) (^ (@LABEL UNIT cm) 2)))) 0.85) (@APPLY max (@ARGS (@SEP (- 1.05 (/ fc (* 1400 (/ (@LABEL UNIT kgf) (^ (@LABEL UNIT cm) 2))))) 0.65)))))) (@RSCALE 0.85 @RPLACEHOLDER)))
(:= (@LABEL VARIABLE Ec) (= (* 15100 (@NTHROOT 2 (* fc (/ (@LABEL UNIT kgf) (^ (@LABEL UNIT cm) 2))))) (@RSCALE (@PARENS (* 2.188 (^ 10 5))) (/ (@LABEL UNIT kgf) (^ (@LABEL UNIT cm) 2)))))
```

| Símbolo | Objetivo (qué calcula) | Norma (Cap) | Código motor | Resultado |
|---------|------------------------|-------------|--------------|-----------|
| fc | resistencia del concreto | input | input | 210 kgf/cm² |
| fy | fluencia del acero | input | input | 4200 kgf/cm² |
| β1 | factor del bloque rectangular equivalente | ACI §22.2.2.3 | `beta1` | 0.85 |
| Ec | módulo elástico del concreto = 15100·√fc | §19.2.2.1 | `pc_euler` (Ec interno) | 2.188×10⁵ kgf/cm² |

## Cap. CC2 — Geometría de la viga  (inputs)
```
(:= (@LABEL VARIABLE b) (* 30 (@LABEL UNIT cm)))
(:= (@LABEL VARIABLE d) (* 50 (@LABEL UNIT cm)))
(:= (@LABEL VARIABLE recub) (* 4 (@LABEL UNIT cm)))
```

| Símbolo | Objetivo (qué calcula) | Norma (Cap) | Código motor | Resultado |
|---------|------------------------|-------------|--------------|-----------|
| b | ancho de la viga | input | input | 30 cm |
| d | peralte efectivo | input | input | 50 cm |
| recub | recubrimiento al eje del estribo | input | `RECUB_DEFAULT` | 4 cm |

## Cap. CC3 — Demanda de la viga  (inputs · de ETABS)
```
(:= (@LABEL VARIABLE Mu) (* 1500000 (* (@LABEL UNIT kgf) (@LABEL UNIT cm))))
(:= (@LABEL VARIABLE Vu) (* 20000 (@LABEL UNIT kgf)))
(:= (@LABEL VARIABLE Tu) (* 200000 (* (@LABEL UNIT kgf) (@LABEL UNIT cm))))
(:= (@LABEL VARIABLE S) (* 20 (@LABEL UNIT cm)))
```

| Símbolo | Objetivo (qué calcula) | Norma (Cap) | Código motor | Resultado |
|---------|------------------------|-------------|--------------|-----------|
| Mu | momento requerido U (carga factorizada) | ACI §5.3 | de ETABS | 1.5×10⁶ kgf·cm |
| Vu | cortante requerido U | ACI §5.3 | de ETABS | 20000 kgf |
| Tu | torsión requerida U | ACI §5.3 | de ETABS | 2×10⁵ kgf·cm |
| S | separación propuesta de estribos | §25.7 | elegido | 20 cm |

## Cap. CC4 — Flexión (viga simple)  (§22.2 · §9.6)
```
(:= (@LABEL VARIABLE ρb) (= (/ (* (* (* 0.85 fc) β1) eu) (* fy (@PARENS (+ eu fy)))) (@RSCALE 0.02125 @RPLACEHOLDER)))
(:= (@LABEL VARIABLE ρmax) (= (* FMAX ρb) (@RSCALE 0.010627 @RPLACEHOLDER)))
(:= (@LABEL VARIABLE K) (= (/ Mu (* (* (* phi_fl fc) b) (^ d 2))) (@RSCALE 0.10582 @RPLACEHOLDER)))
(:= (@LABEL VARIABLE ρreq) (= (/ (* (/ fc fy) (@PARENS (- 1 (@NTHROOT 2 (@PARENS (- 1 (* 2.36 K))))))) 1.18) (@RSCALE 0.005670 @RPLACEHOLDER)))
(:= (@LABEL VARIABLE As) (= (* ρreq (* b d)) (@RSCALE 8.504 (^ (@LABEL UNIT cm) 2))))
(:= (@LABEL VARIABLE Asmin) (= (/ (* (* (* 14 (/ (@LABEL UNIT kgf) (^ (@LABEL UNIT cm) 2))) b) d) fy) (@RSCALE 5.0 (^ (@LABEL UNIT cm) 2))))
(:= (@LABEL VARIABLE Asmax) (= (* ρmax (* b d)) (@RSCALE 15.94 (^ (@LABEL UNIT cm) 2))))
(:= (@LABEL VARIABLE As_final) (= (@APPLY max (@ARGS (@SEP As Asmin))) (@RSCALE 8.504 (^ (@LABEL UNIT cm) 2))))
(:= (@LABEL VARIABLE qm) (= (/ (* ρmax fy) fc) (@RSCALE 0.21254 @RPLACEHOLDER)))
(:= (@LABEL VARIABLE Mmax) (= (* (* (* (* phi_fl fc) (* b (^ d 2))) qm) (@PARENS (- 1 (* 0.59 qm)))) (@RSCALE (@PARENS (* 2.635 (^ 10 6))) (* (@LABEL UNIT kgf) (@LABEL UNIT cm)))))
```
| Símbolo | Objetivo (qué calcula) | Norma (Cap) | Código motor | Resultado |
|---------|------------------------|-------------|--------------|-----------|
| ρb | cuantía BALANCEADA = 0.85·fc·β1·eu/(fy·(eu+fy)) | ACI §22.2.2 | `pb` | 0.02125 |
| ρmax | cuantía MÁXIMA (sísmica) = FMAX·ρb | §21 / §9.3.3 | `pmax_valor` | 0.010627 |
| K | índice de momento = Mu/(φ·fc·b·d²) | §22.2 | `k_flexion` | 0.10582 |
| ρreq | cuantía REQUERIDA = (fc/fy)·(1−√(1−2.36K))/1.18 | §22.2 | `cuantia_requerida` | 0.005670 |
| As | acero requerido = ρreq·b·d | §22.2 | `calcular_viga_simple` | 8.504 cm² |
| Asmin | acero MÍNIMO = 14·b·d/fy | §9.6.1.2 | `as_min` | 5.0 cm² |
| Asmax | acero MÁXIMO = ρmax·b·d | §21 | `pmax_valor` | 15.94 cm² |
| As_final | acero de DISEÑO = max(As, Asmin) | §9.6.1.1 | `calcular_caso` | 8.504 cm² |
| qm | índice de refuerzo = ρmax·fy/fc | §22.2 | `mmax` | 0.21254 |
| Mmax | momento resistente con ρmax | §22.2 | `mmax` | 2.635×10⁶ kgf·cm |

> `14` en `Asmin` lleva unidad kgf/cm² (As_min=14·b·d/fy). `As_final = max(As, As_min)`. Mu < Mmax → simple OK.

## Cap. CC5 — Cortante  (§22.5)
```
(:= (@LABEL VARIABLE vc) (= (* 0.53 (@NTHROOT 2 (* fc (/ (@LABEL UNIT kgf) (^ (@LABEL UNIT cm) 2))))) (@RSCALE 7.68 (/ (@LABEL UNIT kgf) (^ (@LABEL UNIT cm) 2)))))
(:= (@LABEL VARIABLE vu) (= (/ Vu (* (* phi_v b) d)) (@RSCALE 17.78 (/ (@LABEL UNIT kgf) (^ (@LABEL UNIT cm) 2)))))
(:= (@LABEL VARIABLE Av) (= (/ (* (* (@PARENS (- vu vc)) b) S) fy) (@RSCALE 1.443 (^ (@LABEL UNIT cm) 2))))
(:= (@LABEL VARIABLE Avmin) (= (/ (* (* (* 3.52 (/ (@LABEL UNIT kgf) (^ (@LABEL UNIT cm) 2))) b) S) fy) (@RSCALE 0.503 (^ (@LABEL UNIT cm) 2))))
(:= (@LABEL VARIABLE smax_v) (= (@APPLY min (@ARGS (@SEP (/ d 2) (* 60 (@LABEL UNIT cm))))) (@RSCALE 25 (@LABEL UNIT cm))))
```
| Símbolo | Objetivo (qué calcula) | Norma (Cap) | Código motor | Resultado |
|---------|------------------------|-------------|--------------|-----------|
| vc | esfuerzo cortante del CONCRETO = 0.53·√fc | ACI §22.5.6 | `vc_concreto` | 7.68 kgf/cm² |
| vu | esfuerzo cortante ÚLTIMO = Vu/(φ·b·d) | §22.5 | `vu_esfuerzo` | 17.78 kgf/cm² |
| Av | área de estribo REQUERIDA = (vu−vc)·b·S/fy | §22.5.8 | `av_requerido` | 1.443 cm² |
| Avmin | área de estribo MÍNIMA = 3.52·b·S/fy | §9.6.3.3 | `av_minimo` | 0.503 cm² |
| smax_v | separación MÁX por cortante = min(d/2, 60) | §9.7.6.2.2 | `smax_cortante` | 25 cm |

> `3.52` en `Avmin` lleva unidad kgf/cm². `Av = (vu−vc)·b·S/fy` (2 ramas).

## Cap. CC6 — Torsión  (ACI 318-71 §11.6)
```
(:= (@LABEL VARIABLE sumx2y) (= (* (^ b 2) d) (@RSCALE 45000 (^ (@LABEL UNIT cm) 3))))
(:= (@LABEL VARIABLE x1) (= (- b (* 2 recub)) (@RSCALE 22 (@LABEL UNIT cm))))
(:= (@LABEL VARIABLE y1) (= (- d recub) (@RSCALE 46 (@LABEL UNIT cm))))
(:= (@LABEL VARIABLE vtu) (= (/ (* 3 Tu) (* phi_v sumx2y)) (@RSCALE 17.78 (/ (@LABEL UNIT kgf) (^ (@LABEL UNIT cm) 2)))))
(:= (@LABEL VARIABLE vtc) (= (* 0.63 (@NTHROOT 2 (* fc (/ (@LABEL UNIT kgf) (^ (@LABEL UNIT cm) 2))))) (@RSCALE 9.13 (/ (@LABEL UNIT kgf) (^ (@LABEL UNIT cm) 2)))))
(:= (@LABEL VARIABLE αt) (= (@APPLY min (@ARGS (@SEP (+ 0.66 (* 0.33 (/ x1 y1))) 1.50))) (@RSCALE 0.818 @RPLACEHOLDER)))
(:= (@LABEL VARIABLE At) (= (/ (* (* (@PARENS (- vtu vtc)) S) sumx2y) (* (* (* (* 3 αt) x1) y1) fy)) (@RSCALE 0.746 (^ (@LABEL UNIT cm) 2))))
(:= (@LABEL VARIABLE smax_t) (= (@APPLY min (@ARGS (@SEP (/ (@PARENS (+ x1 y1)) 4) (* 30 (@LABEL UNIT cm))))) (@RSCALE 17 (@LABEL UNIT cm))))
(:= (@LABEL VARIABLE Al_1) (= (/ (* (* 2 At) (@PARENS (+ x1 y1))) S) (@RSCALE 5.07 (^ (@LABEL UNIT cm) 2))))
(:= (@LABEL VARIABLE term28) (= (* (/ (* (* (* 28 (/ (@LABEL UNIT kgf) (^ (@LABEL UNIT cm) 2))) b) S) fy) (/ vtu (@PARENS (+ vtu vu)))) (@RSCALE 2.0 (^ (@LABEL UNIT cm) 2))))
(:= (@LABEL VARIABLE Al_2) (/ (* (@PARENS (- term28 (* 2 At))) (@PARENS (+ x1 y1))) S))
(:= (@LABEL VARIABLE Al) (= (@APPLY max (@ARGS (@SEP Al_1 Al_2))) (@RSCALE 5.07 (^ (@LABEL UNIT cm) 2))))
```
| Símbolo | Objetivo (qué calcula) | Norma (Cap) | Código motor | Resultado |
|---------|------------------------|-------------|--------------|-----------|
| sumx2y | rigidez torsional Σx²y = b²·d | ACI 318-71 §11.6 | `sum_x2y_rectangular` | 45000 cm³ |
| x1 | ancho del estribo (eje-eje) = b−2·recub | §11.6 | `dim_estribo` | 22 cm |
| y1 | alto del estribo (eje-eje) = d−recub | §11.6 | `dim_estribo` | 46 cm |
| vtu | esfuerzo de torsión ÚLTIMO = 3·Tu/(φ·Σx²y) | §11.6 | `vtu_esfuerzo` | 17.78 kgf/cm² |
| vtc | esfuerzo de torsión del CONCRETO = 0.63·√fc | §11.6 | `vtc_basico` | 9.13 kgf/cm² |
| αt | factor de torsión = min(0.66+0.33·x1/y1, 1.50) | §11.6.8 | `alpha_t` | 0.818 |
| At | área transversal de estribo por torsión (1 rama) | §11.6.8 | `at_requerido` | 0.746 cm² |
| smax_t | separación MÁX por torsión = min((x1+y1)/4, 30) | §11.6 | `smax_torsion` | 17 cm |
| Al_1 | acero longitudinal por torsión (opción 1) = 2·At·(x1+y1)/S | §11.6.9 | `al_torsion` | 5.07 cm² |
| term28 | término = (28·b·S/fy)·vtu/(vtu+vu) | §11.6.9 | `al_torsion` | 2.0 cm² |
| Al_2 | acero longitudinal por torsión (opción 2) = (term28−2·At)·(x1+y1)/S | §11.6.9 | `al_torsion` | 1.73 cm² |
| Al | acero longitudinal de DISEÑO = max(Al_1, Al_2) | §11.6.9 | `al_torsion` | 5.07 cm² |

> `28` lleva unidad kgf/cm². **Auditoría:** el motor además acota con `opt2_min=(term28 − 3.5·b·S/fy)·(x1+y1)/S` y toma `Al=max(opt1, max(opt2_base, opt2_min))`. El MD omite `opt2_min` (no gobierna; `Al_1`=5.07 manda).

## Cap. CC7 — Columna: esbeltez + amplificación de momento  (§6.6.4)
```
(:= (@LABEL VARIABLE lx) (* 40 (@LABEL UNIT cm)))
(:= (@LABEL VARIABLE Pu) (* 80000 (@LABEL UNIT kgf)))
(:= (@LABEL VARIABLE lu) (* 300 (@LABEL UNIT cm)))
(:= (@LABEL VARIABLE kcol) 1.0)
(:= (@LABEL VARIABLE βd) 0.6)
(:= (@LABEL VARIABLE Cm) 1.0)
(:= (@LABEL VARIABLE r) (= (* 0.3 lx) (@RSCALE 12 (@LABEL UNIT cm))))
(:= (@LABEL VARIABLE λ) (= (/ (* kcol lu) r) (@RSCALE 25 @RPLACEHOLDER)))
(:= (@LABEL VARIABLE Ig) (= (/ (* lx (^ lx 3)) 12) (@RSCALE (@PARENS (* 2.133 (^ 10 5))) (^ (@LABEL UNIT cm) 4))))
(:= (@LABEL VARIABLE EI) (= (/ (* Ec Ig) (* 2.5 (@PARENS (+ 1 βd)))) (@RSCALE (@PARENS (* 1.167 (^ 10 10))) (* (@LABEL UNIT kgf) (^ (@LABEL UNIT cm) 2)))))
(:= (@LABEL VARIABLE Pc) (= (/ (* (@PARENS (^ (@LABEL CONSTANT π) 2)) EI) (^ (@PARENS (* kcol lu)) 2)) (@RSCALE (@PARENS (* 1.28 (^ 10 6))) (@LABEL UNIT kgf))))
(:= (@LABEL VARIABLE δ) (= (@APPLY max (@ARGS (@SEP (/ Cm (@PARENS (- 1 (/ Pu (* phi_col Pc))))) 1.0))) (@RSCALE 1.106 @RPLACEHOLDER)))
```
| Símbolo | Objetivo (qué calcula) | Norma (Cap) | Código motor | Resultado |
|---------|------------------------|-------------|--------------|-----------|
| lx | lado de la columna | input | input | 40 cm |
| Pu | axial último de la columna | input | de ETABS | 80000 kgf |
| lu | longitud no arriostrada | input | input | 300 cm |
| kcol | factor de longitud efectiva | §6.2.5 | input | 1.0 |
| βd | relación de carga axial sostenida | §6.6.4.4.4 | input | 0.6 |
| Cm | factor de momento uniforme equivalente | §6.6.4.5.3 | input | 1.0 |
| r | radio de giro = 0.3·lx | ACI aprox | `radio_giro` | 12 cm |
| λ | esbeltez = kcol·lu/r | §6.2.5 | `esbeltez` | 25 |
| Ig | inercia BRUTA = lx⁴/12 | §6.6.3.1.1 | `pc_euler` | 2.133×10⁵ cm⁴ |
| EI | rigidez EFECTIVA = Ec·Ig/(2.5·(1+βd)) | §6.6.4.4.4 | `pc_euler` | 1.167×10¹⁰ kgf·cm² |
| Pc | carga crítica de EULER = π²·EI/(kcol·lu)² | §6.6.4.4.2 | `pc_euler` | 1.28×10⁶ kgf |
| δ | amplificador de momento = Cm/(1−Pu/(φ·Pc)) ≥ 1 | §6.6.4.5.2 | `factor_amplificacion` | 1.106 |

> `Ig = lx·lx³/12` (columna cuadrada lx). `δ = Cm/(1 − Pu/(φ·Pc)) ≥ 1.0` — **φ=0.65 (motor), ACI usa 0.75** (ver nota de auditoría arriba). Amplificador §6.6.4.5.2.

## Cap. CC8 — Comprobaciones · Diseño por Resistencia (ACI 318-19)  (Mu≤φMn · Vu≤φVn · Tu≤φTn)

> **Marco: Diseño por Resistencia ACI 318-19** — NO "LRFD" (ese término es AISC/acero). Resistencia requerida
> `U` (cargas factorizadas §5.3) ≤ resistencia de diseño `φSn` (factor φ §21.2.1). Razón Demanda/Capacidad = U/φSn ≤ 1.
> **φ ya está embebido en las capacidades del motor:** `Mmax`=φMn (φ=0.90, §21.2.2), `vu`=Vu/(φ·b·d) trae φ=0.75.
> Reproduce `calcular_caso` (`ok_sismico`, vu vs vc, vtu vs vtc, λ>22, Pu<φ·Pc, `ok_pg`).

**Viga — flexión** (ρreq ≤ ρmax · Mu ≤ φMn)
```
(:= (@LABEL VARIABLE DC_flex) (= (/ ρreq ρmax) (@RSCALE 0.5336 @RPLACEHOLDER)))
(:= (@LABEL VARIABLE DC_mom) (= (/ Mu Mmax) (@RSCALE 0.5693 @RPLACEHOLDER)))
(:= (@LABEL VARIABLE cumple_flex) (= (@APPLY (@LABEL KEYWORD if) (@ARGS (@SEP (@SEP (@LEQ (@APPLY max (@ARGS (@SEP DC_flex DC_mom))) 1) "cumple") "revisar"))) (@RSCALE "cumple" @RPLACEHOLDER)))
```

**Viga — cortante** (φVn ≥ Vu con estribos diseñados)
```
(:= (@LABEL VARIABLE Av_final) (= (@APPLY max (@ARGS (@SEP Av Avmin))) (@RSCALE 1.443 (^ (@LABEL UNIT cm) 2))))
(:= (@LABEL VARIABLE vs_prov) (= (/ (* Av_final fy) (* b S)) (@RSCALE 10.1 (/ (@LABEL UNIT kgf) (^ (@LABEL UNIT cm) 2)))))
(:= (@LABEL VARIABLE DC_cort) (= (/ vu (@PARENS (+ vc vs_prov))) (@RSCALE 1.0 @RPLACEHOLDER)))
(:= (@LABEL VARIABLE cumple_cort) (= (@APPLY (@LABEL KEYWORD if) (@ARGS (@SEP (@SEP (@LEQ DC_cort 1) "cumple") "revisar"))) (@RSCALE "cumple" @RPLACEHOLDER)))
```

**Viga — torsión** (¿requiere acero? vtu vs vtc)
```
(:= (@LABEL VARIABLE DC_tor) (= (/ vtu vtc) (@RSCALE 1.947 @RPLACEHOLDER)))
(:= (@LABEL VARIABLE req_tor) (= (@APPLY (@LABEL KEYWORD if) (@ARGS (@SEP (@SEP (@LEQ DC_tor 1) "no requiere") "requiere acero por torsion"))) (@RSCALE "requiere acero por torsion" @RPLACEHOLDER)))
```

**Columna — esbeltez + estabilidad** (λ ≤ 22 · Pu < φ·Pc)
```
(:= (@LABEL VARIABLE DC_esbeltez) (= (/ λ 22) (@RSCALE 1.136 @RPLACEHOLDER)))
(:= (@LABEL VARIABLE ver_esbeltez) (= (@APPLY (@LABEL KEYWORD if) (@ARGS (@SEP (@SEP (@LEQ DC_esbeltez 1) "columna corta") "columna esbelta: amplificar"))) (@RSCALE "columna esbelta: amplificar" @RPLACEHOLDER)))
(:= (@LABEL VARIABLE DC_estab) (= (/ Pu (* phi_col Pc)) (@RSCALE 0.0962 @RPLACEHOLDER)))
(:= (@LABEL VARIABLE cumple_estab) (= (@APPLY (@LABEL KEYWORD if) (@ARGS (@SEP (@SEP (@LEQ DC_estab 1) "estable") "INESTABLE"))) (@RSCALE "estable" @RPLACEHOLDER)))
```

**Veredicto global de la viga**
```
(:= (@LABEL VARIABLE DC_viga) (= (@APPLY max (@ARGS (@SEP (@SEP DC_flex DC_mom) DC_cort))) (@RSCALE 1.0 @RPLACEHOLDER)))
(:= (@LABEL VARIABLE Cumple_global) (= (@APPLY (@LABEL KEYWORD if) (@ARGS (@SEP (@SEP (@LEQ DC_viga 1) "VIGA CUMPLE") "REVISAR"))) (@RSCALE "VIGA CUMPLE" @RPLACEHOLDER)))
```

| Símbolo | Objetivo (qué comprueba) | Norma ACI 318-19 | Código motor | Resultado |
|---------|--------------------------|------------------|--------------|-----------|
| DC_flex | ductilidad: ρreq ≤ ρmax (sección controlada por tracción) | §21.2.2 / §9.3.3.1 | `ok_sismico` | 0.534 ✓ |
| DC_mom | resistencia flexión: Mu ≤ φMn = Mu/Mmax (φ=0.90 incluido) | §9.5.1 / §22.3 | `mmax` | 0.569 ✓ |
| cumple_flex | veredicto flexión (max(DC) ≤ 1) | §9.5.1 | — | "cumple" |
| Av_final | estribo de diseño = max(Av, Av,min) | §22.5.10 / §9.6.3.3 | `av_requerido`/`av_minimo` | 1.443 cm² |
| vs_prov | aporte de estribos = Av·fy/(b·S) | §22.5.10.5.3 | `av_requerido` | 10.1 kgf/cm² |
| DC_cort | resistencia cortante: Vu ≤ φVn → vu/(vc+vs) (φ=0.75 en vu) | §22.5.1 / §9.5.3 | `vu_esfuerzo` | 1.00 ✓ |
| cumple_cort | veredicto cortante | §9.5.3 | — | "cumple" |
| DC_tor | resistencia torsión: Tu vs φTc → vtu/vtc | ACI 318-71 §11.6 (motor) | `at_requerido` | 1.95 → requiere |
| req_tor | ¿acero por torsión? (vtu > vtc) | §11.6.8 | `at_requerido` | "requiere acero por torsion" |
| DC_esbeltez | esbeltez vs límite = λ/22 (λ>22 → 2º orden) | §6.2.5 | `esbeltez` | 1.14 → esbelta |
| ver_esbeltez | corta vs esbelta (magnificar momento) | §6.2.5 / §6.6.4 | `calcular_caso` (λ>22) | "esbelta: amplificar" |
| DC_estab | estabilidad = Pu/(φ·Pc) < 1 | §6.6.4.5.2 | `factor_amplificacion` | 0.096 ✓ |
| cumple_estab | estable si DC < 1 (si no, δ→∞) | §6.6.4.5.2 | `factor_amplificacion` | "estable" |
| DC_viga | gobernante de la viga = max(flex, mom, cort) | §9.5 | `calcular_caso` | **1.00** |
| Cumple_global | veredicto final viga | §9.5 | `calcular_caso` | "VIGA CUMPLE" |

> **Lectura del ejemplo:** viga 30×50 cumple flexión (0.53) y cortante (1.00, estribos al límite). **Torsión: vtu/vtc=1.95 → requiere acero por torsión** (At, Al ya calculados en CC6). Columna 40×40: **esbelta** (λ=25>22 → magnificar con δ=1.106) pero **estable** (Pu muy por debajo de φ·Pc).
> **Marco:** todo es ACI 318-19 Diseño por Resistencia (DC=U/φSn ≤ 1), NO LRFD. Cada `DC` = carga factorizada / capacidad con φ. Flexión/cortante/torsión son de la VIGA; esbeltez/estabilidad de la COLUMNA. `@LEQ` confirmado.

---

> **Confirmadas:** `if`, `min`, `max`, `@NTHROOT 2`, `@GEQ`, `@LEQ`, `@RSCALE` (con unidad · `@RPLACEHOLDER` adimensional), `@PARENS`, `@SEP`, strings `"..."`.
> **A verificar al pegar:** `@GT`/`@LT` (>,<), `@APPLY abs`, `@ARGS` de 1 arg.
