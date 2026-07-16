# Hoja Mathcad — Miembro de Acero LRFD §D-H · Script de autoría (Prime 9, CON UNIDADES)

> **Cómo usar:** abre Mathcad Prime 9 (hoja en blanco), entiende las VARIABLES (§A),
> luego **copia-pega cada bloque de código tal cual** (sin los comentarios — los bloques ya
> están limpios). La explicación va en la tabla bajo cada bloque, separada. **Con unidades.**
> Guarda como `modulo_miembro_acero.mcdx`. Al final corre la §Verificación MCP.
>
> Sintaxis Prime: `:` → `:=` · `pi`=π · `^` potencia · `sqrt(x)` · `if(cond,a,b)` · `min(a,b)` ·
> unidad tras el número (`92.9*cm^2`). `kgf`, `cm` son nativos de Prime — no se define ninguna unidad custom.
> Ecuaciones 1:1 de `calculo_miembro_acero.py`. Cálculo dimensionalmente cerrado.
> **`§` = «Sección»** (cláusula de la norma). `Sección D2` = artículo D2 de **AISC 360-16**. Los `Cap. N` son los capítulos de ESTA hoja (organización), no de la norma.

---

## Sección A — DEFINICIÓN DE VARIABLES (entender primero)

### A.1 Constantes y factores
| Símbolo | Significado | Unidad |
|---------|-------------|--------|
| `E` / `G` | módulo elástico (29 000 ksi) / de corte (11 200 ksi) | kgf/cm² |
| `phi_t_flu`/`phi_t_rot` | φ tracción fluencia 0.90 / rotura 0.75 (§D2) | — |
| `phi_c` / `phi_b` | φ compresión 0.90 (§E1) / flexión 0.90 (§F1) | — |

### A.2 Inputs material + sección (drivables por MCP)
| Símbolo | Significado | Unidad |
|---------|-------------|--------|
| `Fy`/`Fu` | fluencia / rotura del acero | kgf/cm² |
| `Ag` | área bruta | cm² |
| `d`/`bf` | peralte / ancho de ala | cm |
| `tf_` | espesor de ala (guion bajo en el nombre) | cm |
| `tw`/`hw` | espesor / altura libre del alma | cm |
| `Zx`/`Sx` · `Zy`/`Sy` | módulo plástico/elástico eje fuerte · débil | cm³ |
| `rx`/`ry` · `rts` | radio de giro fuerte/débil · efectivo LTB | cm |
| `J` · `ho` | constante torsional · separación de alas (d−tf_) | cm⁴ · cm |

### A.3 Inputs demanda + geometría (drivables por MCP)
| Símbolo | Significado | Unidad |
|---------|-------------|--------|
| `Pu` | axial último (+ tracción / − compresión) | kgf |
| `Mux`/`Muy` | momento último eje fuerte / débil | kgf·cm |
| `Vu` | cortante último | kgf |
| `L` · `Lb` | longitud del miembro · no arriostrada lateral | cm |
| `K` · `Cb` | factor de longitud efectiva (§C) · gradiente de momento | — |

### A.4 Outputs (lee el MCP)
`phiPn_t,phiPn_c` (kgf) · `phiMnx,phiMny` (kgf·cm) · `phiVn` (kgf) · `IR,DC_gob` (—) · `cumple` (1=OK).

---

## Cap. 0 — UNIDADES + CONSTANTES  ·  AISC 360-16 Sección B3.1 (base LRFD) · E,G (Sección E) · φ (Sección D2/E1/F1/G1)
```
E := 2038900*kgf/cm^2
G := 784600*kgf/cm^2
phi_t_flu := 0.90
phi_t_rot := 0.75
phi_c := 0.90
phi_b := 0.90
```
*Explicación:* módulos elásticos del acero y factores LRFD. **Toda la hoja en kgf · cm · kgf·cm** — sin unidad custom de tonelada, para no equivocarse (y no choca con el espesor `tf_`).

## Cap. 1 — INPUTS MATERIAL  [A992]  ·  AISC 360-16 Tabla 2-4 (Fy, Fu) · Sección A3.1
```
Fy := 3515*kgf/cm^2
Fu := 4570*kgf/cm^2
```
*Explicación:* esfuerzos de fluencia (`Fy`) y rotura (`Fu`). A36 → 2531/4078 · A500-C → 3235/4360.

## Cap. 2 — INPUTS SECCIÓN  [W310X73]  ·  AISC Manual Tabla 1-1 (perfiles W) · Sección B4.1 (clasificación compacta)
```
Ag := 92.9*cm^2
d := 31.0*cm
bf := 25.4*cm
tf_ := 1.46*cm
tw := 0.89*cm
hw := 27.59*cm
Zx := 1200*cm^3
Sx := 1060*cm^3
rx := 13.33*cm
ry := 6.46*cm
rts := 7.35*cm
J := 57.1*cm^4
ho := 29.54*cm
Zy := 466*cm^3
Sy := 306*cm^3
```
*Explicación:* propiedades geométricas del perfil (de `TABLA_W`/`props_seccion`). `tf_` = espesor de ala.

> **Dos fuentes (motor `props_seccion`):** si el perfil está en `TABLA_W` (como W310X73), `Zx,Sx,Zy,Sy,Ix,Iy…` son **valores tabulados AISC/CISC** (exactos, los de §2). Si NO está en tabla y es perfil I, el motor los **deriva de la geometría** (3 rectángulos, líneas 232-237) → §2b. Usa **§2 (tabla) O §2b (derivada), no ambos**.

> ⚠ **GOTCHA Prime (exponente + división):** al teclear `d^3/12`, Prime mete el `/12` **dentro
> del exponente** → interpreta `d^(3/12)` (mal, da valores absurdos como 3.513 cm⁴ en vez de
> ~17824). **Solución:** parentiza la potencia → `(d^3)/12`; o tras escribir el exponente pulsa
> **Espacio / →** para salir antes del `/`. Abajo ya van parentizadas.

## Cap. 2b — PROPIEDADES DERIVADAS DE GEOMETRÍA  ·  mecánica de secciones (no es cláusula AISC; deriva props cuando el perfil no está tabulado)  (sin TABLA_W · sobrescribe Cap. 2)
```
hw := d - 2*tf_
Ix := bf*(d^3)/12 - (bf - tw)*(hw^3)/12
Iy := 2*(tf_*(bf^3)/12) + hw*(tw^3)/12
Sx := 2*Ix/d
Sy := 2*Iy/bf
Zx := bf*tf_*(d - tf_) + tw*(hw^2)/4
Zy := tf_*(bf^2)/2 + hw*(tw^2)/4
rx := sqrt(Ix/Ag)
ry := sqrt(Iy/Ag)
J := (2*bf*(tf_^3) + hw*(tw^3))/3
ho := d - tf_
Cw := Iy*(ho^2)/4
rts := sqrt((sqrt(Iy*Cw))/Sx)
```
> ⚠ **GOTCHA radical (rts):** el `/Sx` debe quedar FUERA del sqrt interno. Si tecleas
> `sqrt(sqrt(Iy*Cw)/Sx)` sin paréntesis, Prime mete el `/Sx` DENTRO del radical interno →
> `sqrt(sqrt((Iy·Cw)/Sx))` → unidad `cm^(7/4)` y valor erróneo (41.7 en vez de 7.15). **Fix:**
> parentiza `(sqrt(Iy*Cw))` y tras el sqrt interno pulsa **→** para salir del radical antes del `/`.
> Correcto: `rts ≈ 7.15 cm` (tabla 7.35).
> **¿Cuándo usar §2b?** SOLO si el perfil NO está en `TABLA_W`. **W310X73 SÍ está tabulado →
> omite §2b por completo** y usa los valores de §2 (más exactos). §2b es para perfiles fuera de catálogo.

**Comprobación opcional de Ix (forma a prueba de balas — una sola división):**
```
Ix1 := (bf*(d^3) - (bf - tw)*(hw1^3))/12
```
Esperado: `Ix1 ≈ 17824 cm⁴` (= 1.78×10⁻⁴ m⁴; tabla 16500, +8% por ignorar filetes).
- Si sale unidad compuesta rara tipo `m^(11/4)·cm^(5/4)` (los exponentes suman 4 → SÍ es length⁴, valor correcto ≈17709 cm⁴): tus inputs **mezclan `m` y `cm`**. Unifícalos todos a `cm`, o fuerza el display a `cm^4`. NO es error de fórmula.
- Si aparece `tw'` (con apóstrofo): es variable distinta — bórrala y teclea `tw` plano.
- Para ver el resultado en cm⁴: clic en el resultado → casilla de unidad → escribe `cm^4`.
| Símbolo | Calcula (descomposición en 3 rectángulos) | In | Out |
|---------|-------------------------------------------|----|-----|
| `hw` | altura libre del alma | d,tf_ | cm |
| `Ix` | inercia eje fuerte = ala llena − vacío del alma | bf,d,tw,hw | cm⁴ |
| `Iy` | inercia eje débil = 2 alas + alma | tf_,bf,hw,tw | cm⁴ |
| `Sx` | **módulo elástico eje fuerte = 2·Ix/d** | Ix,d | cm³ |
| `Sy` | **módulo elástico eje débil = 2·Iy/bf** | Iy,bf | cm³ |
| `Zx` | **módulo plástico eje fuerte = bf·tf_·(d−tf_) + tw·hw²/4** | bf,tf_,d,tw,hw | cm³ |
| `Zy` | **módulo plástico eje débil = tf_·bf²/2 + hw·tw²/4** | tf_,bf,hw,tw | cm³ |
| `rx`/`ry` | radios de giro = √(I/Ag) | Ix,Iy,Ag | cm |
| `J` | constante torsional St. Venant (3 rect.) | bf,tf_,hw,tw | cm⁴ |
| `ho`/`Cw`/`rts` | sep. alas / alabeo / radio LTB efectivo | — | cm,cm⁶,cm |

> **Aviso de fidelidad:** la descomposición en 3 rectángulos **ignora los filetes** → desviación ~3-8 % vs tabla
> (W310X73 derivado: Zx≈1271 vs tabla 1200). El motor marca estas props `fuente="derivada"` y **prefiere
> TABLA_W cuando existe**. Para HSS cuadrado el motor usa fórmulas cerradas distintas (Ix=(b⁴−bi⁴)/12,
> Sx=2I/b, Zx=(b³−bi³)/4) — hoja HSS aparte.

## Cap. 3 — INPUTS DEMANDA + GEOMETRÍA  ·  AISC 360-16 Sección B3.1 (demanda LRFD, combos) · Sección C (análisis, K)
```
Pu := -80000*kgf
Mux := 1200000*kgf*cm
Muy := 300000*kgf*cm
Vu := 15000*kgf
L := 400*cm
K := 1.0
Lb := 400*cm
Cb := 1.0
```
*Explicación:* fuerzas últimas del análisis (ETABS, combo LRFD). `Pu` negativo = compresión. `L` longitud, `K` factor efectivo, `Lb` no arriostrada, `Cb` gradiente.

## Cap. 4 — TRACCIÓN  ·  AISC 360-16 Sección D2  (D2-1 fluencia área bruta · D2-2 rotura área neta)
```
Ae := Ag
phiPn_flu := phi_t_flu*Fy*Ag
phiPn_rot := phi_t_rot*Fu*Ae
phiPn_t := min(phiPn_flu, phiPn_rot)
```
| Símbolo | Calcula | In | Out |
|---------|---------|----|-----|
| `Ae` | área neta efectiva (U=1, sin agujeros) | Ag | cm² |
| `phiPn_flu` | φPn fluencia área bruta (D2-1) | Fy,Ag | kgf |
| `phiPn_rot` | φPn rotura área neta (D2-2) | Fu,Ae | kgf |
| `phiPn_t` | tracción gobernante = el menor | ↑ | **293889 kgf** |

## Cap. 5 — COMPRESIÓN  ·  AISC 360-16 Sección E3 (pandeo por flexión)  (E3-1 Pn · E3-2/3 Fcr · E3-4 Fe)
```
rmin := min(rx, ry)
KLr := K*L/rmin
Fe := (pi^2)*E/(KLr^2)
lim_c := 4.71*sqrt(E/Fy)
Fcr_inel := (0.658^(Fy/Fe))*Fy
Fcr_elas := 0.877*Fe
Fcr := if(KLr <= lim_c, Fcr_inel, Fcr_elas)
phiPn_c := phi_c*Fcr*Ag
```
| Símbolo | Calcula | In | Out |
|---------|---------|----|-----|
| `rmin` | radio de giro menor (eje débil de pandeo) | rx,ry | cm |
| `KLr` | relación de esbeltez | K,L,rmin | 61.9 |
| `Fe` | esfuerzo crítico de Euler (E3-4) | E,KLr | 5248.6 kgf/cm² |
| `lim_c` | frontera inelástico/elástico = 4.71√(E/Fy) | E,Fy | 113.4 |
| `Fcr_inel` | crítico inelástico (E3-2) = 0.658^(Fy/Fe)·Fy | Fy,Fe | 2655.8 kgf/cm² |
| `Fcr_elas` | crítico elástico (E3-3) = 0.877·Fe | Fe | kgf/cm² |
| `Fcr` | crítico gobernante: inel. si KLr≤lim_c, sino elás. | KLr,lim_c,… | 2655.8 kgf/cm² |
| `phiPn_c` | φPn compresión (E3-1) | Fcr,Ag | **222049 kgf** |

> ⚠ **GOTCHA `if` en Prime:** `if(cond, a, b)` ES la sintaxis correcta. El error "Missing term"
> aparece cuando metes expresiones complejas DIRECTO en los slots: `0.658^(Fy/Fe)` y luego `*Fy`
> → el `*Fy` entra al exponente; `sqrt(E/Fy)` y luego `,` → la coma entra al radical. **Solución:**
> **precalcula cada pieza como variable** (`lim_c`, `Fcr_inel`, `Fcr_elas`) y deja el `if` con refs
> simples → `if(KLr <= lim_c, Fcr_inel, Fcr_elas)`. Condición `≤` se teclea `<=`. Aplicado igual en Cap. 7.

## Cap. 6 — FLEXIÓN  ·  AISC 360-16 Sección F2 (fluencia + LTB, eje fuerte) + Sección F6 (eje débil)
```
Mp := Fy*Zx
Lp := 1.76*ry*sqrt(E/Fy)
A_lr := 1.95*rts*(E/(0.7*Fy))
B_lr := sqrt(J/(Sx*ho))
beta := (0.7*Fy/E)*(Sx*ho/J)
C_lr := sqrt(1 + sqrt(1 + 6.76*beta^2))
Lr := A_lr*B_lr*C_lr
Mn_ltbi := Cb*(Mp - (Mp - 0.7*Fy*Sx)*(Lb-Lp)/(Lr-Lp))
lam_lr := (Lb/rts)^2
Fcr_ltbe := (Cb*(pi^2)*E/lam_lr)*sqrt(1 + 0.078*(J/(Sx*ho))*lam_lr)
Mn_inel := min(Mn_ltbi, Mp)
Mn_elas := min(Fcr_ltbe*Sx, Mp)
Mn_noLp := if(Lb <= Lr, Mn_inel, Mn_elas)
Mn := if(Lb <= Lp, Mp, Mn_noLp)
phiMnx := phi_b*Mn
Mny := min(Fy*Zy, 1.6*Fy*Sy)
phiMny := phi_b*Mny
```
| Símbolo | Calcula | In | Out |
|---------|---------|----|-----|
| `Mp` | momento plástico (F2-1) | Fy,Zx | 4 218 000 kgf·cm |
| `Lp` | límite Lb para fluencia plena (F2-5) | ry,E,Fy | 273.8 cm |
| `A_lr` | pieza Lr: 1.95·rts·E/(0.7Fy) (F2-6) | rts,E,Fy | 11878 cm |
| `B_lr` | pieza Lr: √(J/(Sx·ho)) | J,Sx,ho | 0.0427 |
| `beta` | pieza Lr: (0.7·Fy/E)·(Sx·ho/J) — **0.7 DENTRO** | Fy,E,Sx,ho,J | 0.662 |
| `C_lr` | pieza Lr: √(1+√(1+6.76·beta²)) | beta | 1.729 |
| `Lr` | límite Lb LTB (F2-6) = A_lr·B_lr·C_lr | ↑ | **877 cm** |
| `Mn_ltbi` | Mn por LTB inelástico crudo (F2-2) | Cb,Mp,Fy,Sx,Lb,Lp,Lr | kgf·cm |
| `lam_lr` | (Lb/rts)² aislado (para F2-3) | Lb,rts | — |
| `Fcr_ltbe` | esfuerzo crítico LTB elástico (F2-3) | Cb,E,lam_lr,J,Sx,ho | kgf/cm² |
| `Mn_inel` | rama LTB inelástico = min(Mn_ltbi, Mp) | Mn_ltbi,Mp | 3 881 200 kgf·cm |
| `Mn_elas` | rama LTB elástico = min(Fcr_ltbe·Sx, Mp) | Fcr_ltbe,Sx,Mp | kgf·cm |
| `Mn_noLp` | si Lb≤Lr → Mn_inel, sino Mn_elas | Lb,Lr | kgf·cm |
| `Mn` | final: si Lb≤Lp → Mp, sino Mn_noLp | Lb,Lp,Mp,Mn_noLp | 3 881 200 kgf·cm |
| `phiMnx` | φMn eje fuerte = 0.90·Mn | Mn | **3 493 100 kgf·cm** |
| `Mny` | Mn eje débil (F6-1, sin LTB) | Fy,Zy,Sy | kgf·cm |
| `phiMny` | φMn eje débil | Mny | **1 474 200 kgf·cm** |

## Cap. 7 — CORTANTE  ·  AISC 360-16 Sección G2 (fluencia del alma, G2-1)
```
htw := hw/tw
Aw := d*tw
lim_v := 2.24*sqrt(E/Fy)
Cv_ne := min(1.10*sqrt(5.34*E/Fy)/htw, 1)
Cv1 := if(htw <= lim_v, 1, Cv_ne)
phi_v := if(htw <= lim_v, 1.00, 0.90)
phiVn := phi_v*0.6*Fy*Aw*Cv1
```
| Símbolo | Calcula | In | Out |
|---------|---------|----|-----|
| `htw` | esbeltez del alma | hw,tw | — |
| `Aw` | área del alma a cortante | d,tw | cm² |
| `lim_v` | frontera de alma compacta = 2.24√(E/Fy) | E,Fy | — |
| `Cv_ne` | coef. cortante si alma NO compacta (G2-4) | E,Fy,htw | — |
| `Cv1` | coef. cortante: 1.0 si htw≤lim_v, sino Cv_ne | htw,lim_v,Cv_ne | 1.0 (compacta) |
| `phi_v` | φ cortante (1.00 alma compacta / 0.90 resto) | htw,lim_v | 1.00 |
| `phiVn` | φVn fluencia del alma (G2-1) | phi_v,Fy,Aw,Cv1 | **58187 kgf** |

## Cap. 8 — INTERACCIÓN FLEXO-COMPRESIÓN  ·  AISC 360-16 Sección H1.1  (H1-1a si Pr/Pc≥0.2 · H1-1b si <0.2)
```
Pr := abs(Pu)
Pc := phiPn_c
Mcx := phiMnx
Mcy := phiMny
IR := if(Pr/Pc >= 0.2, Pr/Pc + (8/9)*(Mux/Mcx + Muy/Mcy), Pr/(2*Pc) + (Mux/Mcx + Muy/Mcy))
```
| Símbolo | Calcula | In | Out |
|---------|---------|----|-----|
| `Pr` | demanda axial requerida | Pu | kgf |
| `Pc`·`Mcx`·`Mcy` | capacidades axial·flexión x·flexión y | phiPn_c,phiMnx,phiMny | kgf,kgf·cm |
| `IR` | razón interacción — H1-1a si Pr/Pc≥0.2, sino H1-1b | Pr,Pc,Mux,Mcx,Muy,Mcy | **0.8465** |

## Cap. 9 — VERIFICACIÓN LRFD  (Sección B3.1)
```
DC_traccion := if(Pu > 0*kgf, Pu/phiPn_t, 0)
DC_compresion := if(Pu < 0*kgf, abs(Pu)/phiPn_c, 0)
DC_flexion_x := Mux/phiMnx
DC_flexion_y := Muy/phiMny
DC_cortante := Vu/phiVn
DC_interaccion := IR
DC_gob := max(DC_traccion, DC_compresion, DC_flexion_x, DC_flexion_y, DC_cortante, DC_interaccion)
cumple := if(DC_gob <= 1.0, 1, 0)
```
| Símbolo | Calcula | Out |
|---------|---------|-----|
| `DC_*` | demanda/capacidad por estado (0 si no aplica) | — |
| `DC_gob` | el mayor DC = estado gobernante | **0.8465** |
| `cumple` | veredicto LRFD (1 = OK) | **1** |

> Todos los DC e IR salen **adimensionales** (numerador y denominador comparten unidad). Si Prime
> marca error de unidad en un DC, demanda y capacidad no tienen la misma unidad base.

---

## Verificación MCP  (requiere DESIGNAR Input/Output en Prime)

> ✅ **HALLAZGO MCP (resuelto 2026-06-03):** el MCP `get_input`/`get_real_output`/`set_real_input` por
> nombre **SÍ funciona, PERO solo con variables DESIGNADAS** como Input/Output. Verificado:
> `get_input("E")`=2038900 kgf/cm² (lo devuelve en **Pa/SI**) · `set_real_input("ϕtR",0.75)` OK.
> Sin designar → "not found" (fue la causa de todos los fallos previos).
>
> **Cómo designar (en Prime, una vez):** pestaña/panel **"Input/Output Designation"** → arrastrar/marcar
> cada variable como **Input** o **Output** (le da un *alias* = el nombre que usa el MCP). **Guardar.**
> No hay tool MCP para designar ni para autorear ecuaciones — eso es manual en Prime.
>
> **Designar para barrer perfiles:**
> - **Inputs:** `Ag, d, bf, tf_, tw, hw, Zx, Sx, rx, ry, rts, J, ho, Zy, Sy` (la §2) + `Fy, Fu, Pu, Mux, Muy, Vu, L, K, Lb, Cb`
> - **Outputs:** `ϕPn_t, ϕPn_c, ϕMnx, ϕMny, ϕVn, IR, DC_gob, Cumple`
>
> **Unidades:** el MCP devuelve/acepta **SI base** (Pa, m, N…). Usa el arg `units` de `set_real_input`
> (`"cm^2"`, `"kgf"`) o convierte (1 kgf/cm² = 98066.5 Pa).
>
> **Flujo de swap de sección (una vez designado + guardado):**
> ```
> set_real_input(ws, "Ag", 45.5, "cm^2") ; set_real_input(ws, "Zx", 380, "cm^3") ; … (todas las de §2)
> sync_worksheet(ws)
> get_real_output(ws, "DC_gob")   # nuevo DC del perfil
> ```
> Alternativa sin designar: `save_worksheet` a **PDF** → leer el PDF/imagen (verificación visual).
>
> **Edición directa del .mcdx (sin MCP):** el `.mcdx` es ZIP+`mathcad/worksheet.xml`; los valores están en
> `<ml:define><ml:id>Ag</ml:id>…<ml:real>92.9</ml:real>`. Editable por script (zip) → Prime recalcula al abrir.

**Esperados** (motor `POST /miembro-acero/memoria-rapida`, W310X73 A992, caso §3):

| Output | Esperado | Unidad |
|--------|----------|--------|
| `phiPn_t` | 293889 | kgf |
| `phiPn_c` | 222049 | kgf |
| `phiMnx` | 3 493 100 | kgf·cm |
| `phiMny` | 1 474 200 | kgf·cm |
| `phiVn` | 58187 | kgf |
| `IR` / `DC_gob` | 0.8465 | — |
| `cumple` | 1 | — |

**Lo que el MCP SÍ permite (worksheet-level):**
```
open_worksheet("…/Miembros de Acero en LRFD.mcdx")   # OK
sync_worksheet("Miembros de Acero en LRFD")           # OK (recalcula)
save_worksheet("Miembros de Acero en LRFD", "…/out.pdf", "pdf")   # OK → revisar visual
# get_real_output / set_real_input  → "not found"  (NO sirve por nombre)
```
> Para que el MCP lea/escriba por nombre habría que designar las variables como Input/Output en
> Prime (no trivial con subíndices) — pendiente de investigar si el wrapper lo soporta.

> **Nota fidelidad:** rama HSS (§F7/§G4) NO está en esta hoja I-shape (gobernante del ejemplo = §H1). Hoja HSS aparte — ver auditoría §A-4.

---
---

# PARTE 2 — CONEXIÓN DE ACERO §J  (continuación · AISC 360-16 Sección J)

> Mismo método: variables primero · fórmula limpia copy-paste · explicación aparte · **kgf · cm** ·
> `if`/`min` descompuestos · refs AISC por capítulo. Fuente: `calculo_conexion_acero.py`. 1:1, sin inventar.
> **Nombres con sufijo de conexión** (`Fyp`, `Vu_c`, `tp`…) para NO chocar con el miembro de la Parte 1
> (`Fy`=3515 del A992 es del miembro; la placa de conexión suele ser A36 → `Fyp`=2531).
> Una conexión real usa UN tipo: **VC cortante** = §J3 pernos + §J4 placa · **Soldada** = §J2 + §J4 ·
> **Placa base** = §J8. La verificación toma el `min` de los estados que apliquen.

## Cap. C1 — MATERIALES + ELECTRODO + PERNO  ·  AISC 360-16 Tabla 2-4 · Tabla J2.5 · Tabla J3.2
```
Fyp := 2531*kgf/cm^2
Fup := 4078*kgf/cm^2
FEXX := 4920*kgf/cm^2
Fnt := 6328*kgf/cm^2
Fnv := 3797*kgf/cm^2
phi_sold := 0.75
phi_perno := 0.75
phi_fy := 0.90
phi_ru := 0.75
phi_vy := 1.00
phi_bs := 0.75
```
| Símbolo | Significado | Valor |
|---------|-------------|-------|
| `Fyp`/`Fup` | fluencia/rotura de la PLACA (A36) | 2531 / 4078 kgf/cm² |
| `FEXX` | resistencia del electrodo (E70XX) | 4920 kgf/cm² |
| `Fnt`/`Fnv` | tracción / cortante nominal del perno (A325, roscas EN corte) | 6328 / 3797 kgf/cm² |
| `phi_*` | factores LRFD: sold/perno 0.75 · fluencia-tracc 0.90 · rotura 0.75 · fluencia-corte 1.00 · block 0.75 | — |

## Cap. C2 — GEOMETRÍA DE LA CONEXIÓN  ·  AISC 360-16 Sección J3.3/J3.4 (gramil, bordes)
```
tp := 0.95*cm
db := 1.9*cm
nb := 3
s := 5.7*cm
Le := 2.85*cm
lc := 1.82*cm
w := 0.794*cm
Lw := 40*cm
Ab := (pi/4)*db^2
hp := (nb - 1)*s + 2*Le
Agp := tp*hp
gap := 0.16*cm
Anv := Agp - nb*(db + gap)*tp
```
| Símbolo | Significado | In | Out |
|---------|-------------|----|-----|
| `tp` | espesor de la placa de conexión | — | 0.95 cm |
| `db`·`nb` | diámetro · número de pernos | — | 1.9 cm · 3 |
| `s`·`Le`·`lc` | paso (gramil) · distancia al borde · distancia libre (tearout) | — | 5.7 · 2.85 · 1.82 cm |
| `w`·`Lw` | pierna del filete · longitud del cordón (si soldada) | — | 0.794 · 40 cm |
| `Ab` | área nominal del perno = π/4·db² | db | 2.835 cm² |
| `hp` | altura de la placa = (nb−1)·s + 2·Le | nb,s,Le | 17.1 cm |
| `Agp` | área bruta de la placa = tp·hp | tp,hp | 16.245 cm² |
| `Anv` | área neta a cortante = Agp − nb·(db+gap)·tp | Agp,nb,db,tp | 10.374 cm² |

## Cap. C3 — DEMANDA DE LA CONEXIÓN  ·  AISC 360-16 Sección J1.1 (ETABS, combo LRFD)
```
Vu_c := 15000*kgf
Nu_c := 0*kgf
Pu_c := 80000*kgf
```
*Explicación:* `Vu_c` cortante de la conexión · `Nu_c` axial (tracción) · `Pu_c` axial de columna (solo placa base). De ETABS / fuerzas-nudo.

## Cap. C4 — §J3 PERNOS  ·  AISC 360-16 Sección J3  (corte J3-1 · aplast. J3-6a · tearout J3-6c)
```
Rn_v := phi_perno*Fnv*Ab*nb
Rn_ap := phi_perno*(2.4*db*tp*Fup)*nb
Rn_to := phi_perno*(1.2*lc*tp*Fup)*nb
Rn_pernos := min(Rn_v, Rn_ap, Rn_to)
```
| Símbolo | Calcula | In | Out |
|---------|---------|----|-----|
| `Rn_v` | φRn cortante del grupo (J3-1) = φ·Fnv·Ab·nb | Fnv,Ab,nb | 24223 kgf |
| `Rn_ap` | φRn aplastamiento (J3-6a) = φ·2.4·db·tp·Fup·nb | db,tp,Fup,nb | 39748 kgf |
| `Rn_to` | φRn desgarre/tearout (J3-6c) = φ·1.2·lc·tp·Fup·nb | lc,tp,Fup,nb | 19037 kgf |
| `Rn_pernos` | gobernante de pernos = el menor | ↑ | **19037 kgf** |

## Cap. C5 — §J2 SOLDADURA  ·  AISC 360-16 Sección J2  (filete J2-3/4 · metal base J2-2)
```
te := 0.707*w
Fnw := 0.6*FEXX
Rn_sold := phi_sold*Fnw*(te*Lw)
Rn_BM := phi_ru*0.6*Fup*(tp*Lw)
Rn_junta := min(Rn_sold, Rn_BM)
```
| Símbolo | Calcula | In | Out |
|---------|---------|----|-----|
| `te` | garganta efectiva del filete = 0.707·w (J2.2a) | w | 0.5614 cm |
| `Fnw` | resistencia nominal del metal de aporte = 0.6·FEXX (θ=0) | FEXX | 2952 kgf/cm² |
| `Rn_sold` | φRn del cordón (J2-3/4) = φ·Fnw·te·Lw | Fnw,te,Lw | 49714 kgf |
| `Rn_BM` | φRn del metal BASE (J2-2) = φ·0.6·Fup·tp·Lw | Fup,tp,Lw | 69734 kgf |
| `Rn_junta` | junta = min(cordón, metal base) | ↑ | **49714 kgf** |

> ⚠ **Límites del filete (Tabla J2.4 / §J2.2b):** w ≥ w_min (por t_placa) · w ≤ w_max · L ≥ 4·w. Revisar aparte.

## Cap. C6 — §J4 ELEMENTOS (placa)  ·  AISC 360-16 Sección J4  (J4-1…J4-5)
```
Ae_p := Agp
Agv := tp*hp
Ant := (Le - 0.5*(db + gap))*tp
Rn_fy := phi_fy*Fyp*Agp
Rn_ru := phi_ru*Fup*Ae_p
Rn_vy := phi_vy*0.6*Fyp*Agv
Rn_vu := phi_ru*0.6*Fup*Anv
bs_rotura := 0.6*Fup*Anv + Fup*Ant
bs_fluenc := 0.6*Fyp*Agv + Fup*Ant
Rn_bs := phi_bs*min(bs_rotura, bs_fluenc)
```
| Símbolo | Calcula | In | Out |
|---------|---------|----|-----|
| `Rn_fy` | fluencia por tracción (J4-1) = φ·Fyp·Agp | Fyp,Agp | 37004 kgf |
| `Rn_ru` | rotura por tracción (J4-2) = φ·Fup·Ae | Fup,Ae_p | 49685 kgf |
| `Rn_vy` | fluencia por cortante (J4-3) = φ·0.6·Fyp·Agv | Fyp,Agv | 24670 kgf |
| `Rn_vu` | rotura por cortante (J4-4) = φ·0.6·Fup·Anv | Fup,Anv | 19037 kgf |
| `Rn_bs` | block shear (J4-5) = φ·min(rotura, fluencia) | Fyp,Fup,Agv,Anv,Ant | ~20798 kgf |

> `Ant` (área neta a tracción) depende del layout de pernos; ajústala a tu detalle. En el ejemplo block shear NO gobierna (gobierna tearout).

## Cap. C7 — §J8 PLACA BASE  ·  AISC 360-16 Sección J8 + Design Guide 1  (aplastamiento + espesor)
```
fc := 210*kgf/cm^2
Fy_col := 3515*kgf/cm^2
dcol := 31.0*cm
bfcol := 25.4*cm
Bpl := bfcol + 10*cm
Npl := dcol + 10*cm
A1 := Bpl*Npl
A2 := A1
ratio := min(sqrt(A2/A1), 2)
Pp := min(0.85*fc*A1*ratio, 1.7*fc*A1)
phiPp := 0.65*Pp
fp := Pu_c/(Bpl*Npl)
m := (Npl - 0.95*dcol)/2
n_pl := (Bpl - 0.80*bfcol)/2
n_prima := sqrt(dcol*bfcol)/4
l_vol := max(m, n_pl, n_prima)
tp_req := l_vol*sqrt(2*fp/(0.90*Fy_col))
```
| Símbolo | Calcula | In | Out |
|---------|---------|----|-----|
| `Bpl`·`Npl` | placa: ancho (bf+10) · largo (d+10) | bfcol,dcol | 35.4 · 41 cm |
| `A1`·`A2` | área de placa · área del pedestal (≥A1) | Bpl,Npl | 1451 · 1451 cm² |
| `phiPp` | aplastamiento del concreto (J8-1) = 0.65·min(0.85·fc·A1·√(A2/A1), 1.7·fc·A1) | fc,A1,A2 | **168399 kgf** |
| `fp` | presión de contacto = Pu/(Bpl·Npl) | Pu_c,A1 | 55.12 kgf/cm² |
| `l_vol` | voladizo crítico = max(m, n, n') (DG-1) | m,n_pl,n_prima | 7.54 cm |
| `tp_req` | espesor requerido = l·√(2·fp/(0.90·Fy)) | l_vol,fp,Fy_col | 1.408 cm (vs tp=1.9 → OK) |

> ⚠ **Auditoría C-1 — Fy de la placa base:** el motor usa el `Fy` del acero de la conexión (A992 columna, 3515) → `tp_req`=1.408. **Pero la placa base real es A36** (`Fy`=2531). Lo correcto: `Fy_placa := 2531*kgf/cm^2` y `tp_req := l_vol*sqrt(2*fp/(0.90*Fy_placa))` → `tp_req`≈**1.65 cm** (más conservador). Usa `Fy_placa`, NO `Fy_col`, para el espesor.

## Cap. C8 — VERIFICACIÓN DE LA CONEXIÓN  ·  AISC 360-16 Sección B3.1 / J1.1
```
Rn_gob := min(Rn_pernos, Rn_junta, Rn_fy, Rn_ru, Rn_vy, Rn_vu, Rn_bs)
DC_conex := Vu_c/Rn_gob
cumple_conex := if(DC_conex <= 1.0, 1, 0)
```
> Incluye en `Rn_gob` SOLO los estados del tipo de conexión real: **VC cortante** → pernos + elementos
> (no `Rn_junta`); **soldada** → junta + elementos (no `Rn_pernos`); **placa base** → compara `Pu_c` vs `phiPp`
> y `tp` vs `tp_req`. Para el ejemplo VC cortante: `Rn_gob` = tearout **19037 kgf**, `DC` = 15000/19037 = **0.788** → CUMPLE.

| Output | Esperado (motor) |
|--------|------------------|
| VC cortante `Rn_gob` / `DC` | 19037 kgf / 0.788 (gob: tearout J3-6c) |
| Soldada `Rn_junta` / `DC` | 49714 kgf / 0.302 (gob: cordón J2) |
| Placa base `phiPp` / `DC` | 168399 kgf / 0.475 · `tp_req`=1.408 cm |
