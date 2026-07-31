# Auditoría — Inventario completo de fórmulas de cálculo (backend EstimaStruct)

Extracción read-only. Generado 2026-07-27. Alcance: `backend/calculo_*.py`,
`backend/services/pricing.py`, `backend/cronograma.py`, `backend/perfiles_acero.py`
(función `props_seccion`, usada por el motor de miembros), y los routers que
exponen estos motores por HTTP.

**Nota de alcance:** `backend/calculo_soldadura.py` **no existe** en el repo actual.
La soldadura AISC §J2 está consolidada dentro de `backend/calculo_conexion_acero.py`.

**Convención de "expuesto":**
- **SÍ (memoria)** = la fórmula aparece como paso narrado (símbolo+fórmula+sustitución+valor)
  en un endpoint `*/memoria*` o `*/memoria-rapida` (las "Hojas" estilo Mathcad del frontend).
- **SÍ (resultado)** = el valor numérico final viaja en el dict `resultado`/`estados`/`j8`/`geo`
  devuelto por un endpoint que persiste o calcula (`/calcular`, `/import-etabs-*`, etc.), aunque
  el paso intermedio no tenga narración propia.
- **NO** = se calcula pero el valor no aparece en ningún `return`/response HTTP localizado.

---

## 1. `backend/calculo_estructural.py` — Motor ACI 318-19 (concreto)

Fuente: adaptación de `Viga-Colum.xls` (Rosado & Rosado, ACI 318-71) con factores φ
actualizados a ACI 318-19 §21.2.1. Unidades: cm, t, t·m, kg, kg/cm².
Expuesto vía: `POST /diseno/casos/{cid}/calcular` (persiste `ResultadoDiseno`),
`GET /diseno/casos/{cid}/memoria` y `POST /diseno/memoria-rapida` (narrado completo,
stateless), `POST /diseno/predimensionar`.

### A — Materiales

| Fórmula | Archivo:línea | Expresión | LaTeX | Variables | Norma | Expuesto |
|---|---|---|---|---|---|---|
| β₁ | `calculo_estructural.py:34-38` | `β1 = 0.85 si fc≤280; si no max(1.05−fc/1400, 0.65)` | `\beta_1=\begin{cases}0.85&f'_c\le280\\1.05-f'_c/1400&f'_c>280\end{cases}` | fc (kg/cm²) | ACI 318-19 §22.2.2.3 | SÍ (memoria) |
| ρb (cuantía balanceada) | `calculo_estructural.py:41-44` | `pb = 0.85·fc·β1·6000/(fy·(6000+fy))` | `\rho_b=\dfrac{0.85f'_c\beta_1\cdot6000}{f_y(6000+f_y)}` | fc, fy | ACI 318-19 §22.2.2 | SÍ (memoria+resultado `pb`) |
| ρmax (cuantía máxima sísmica) | `calculo_estructural.py:47-49` | `pmax = fmax·pb` (fmax=0.5) | `\rho_{max}=0.5\rho_b` | fc, fy, fmax | ACI 318-19 §21 | SÍ (memoria+resultado `pmax`) |
| Ec (módulo elasticidad) | `calculo_estructural.py:873,888-890` | `Ec = 15100·√fc` | `E_c=15100\sqrt{f'_c}` | fc | ACI 318-19 §19.2.2.1 | SÍ (memoria) |

### B — Viga simple (flexión)

| Fórmula | Archivo:línea | Expresión | LaTeX | Variables | Norma | Expuesto |
|---|---|---|---|---|---|---|
| K (índice de resistencia) | `calculo_estructural.py:56-62` | `K = Mu·10⁵/(φ·fc·b·d²)` | `K=\dfrac{M_u}{\phi f'_c b d^2}` | Mu(t·m), b, d, fc, φ=0.90 | MD §3.4 · ACI 318-71 | SÍ (memoria) |
| ρ requerida | `calculo_estructural.py:65-70` | `p = (fc/fy)·(1−√(1−2.36K))/1.18` (nan si K>0.424) | `\rho=\dfrac{f'_c}{f_y}\dfrac{1-\sqrt{1-2.36K}}{1.18}` | K, fc, fy | MD §3.5 · ACI 318-71 | SÍ (memoria) |
| As,min | `calculo_estructural.py:73-76` | `As,min = 14·b·d/fy` (bw si viga T) | `A_{s,min}=\dfrac{14bd}{f_y}` | b, d, fy | ACI 318-19 §9.6.1.2 | SÍ (memoria+resultado `as_min_cm2`) |
| Mmax (con ρmax) | `calculo_estructural.py:79-84` | `Mmax = φ·fc·b·d²·qmax·(1−0.59·qmax)/10⁵`, `qmax=pmax·fy/fc` | `M_{max}=\phi f'_c bd^2q_{max}(1-0.59q_{max})` | b, d, fc, fy, φ | MD §3.3 · ACI 318-71 | SÍ (memoria+resultado `Mmax_tm`) |
| As (adoptado) | `calculo_estructural.py:99` / `1047-1049` | `As = max(As_req, As,min)` | `A_s=\max(A_{s,req},A_{s,min})` | As_req, As,min | MD §3.6 | SÍ (memoria+resultado `as_cm2`) |
| As,max (sísmico) | `calculo_estructural.py:94-95` | `As,max = pmax·b·d` | `A_{s,max}=\rho_{max}bd` | pmax, b, d | MD §13 · ACI 318-71 | SÍ (memoria+resultado `as_max_cm2`) |

### C — Viga doblemente armada

| Fórmula | Archivo:línea | Expresión | LaTeX | Variables | Norma | Expuesto |
|---|---|---|---|---|---|---|
| f's (acero a compresión) | `calculo_estructural.py:129-132` | `fs = 6000·[1−(d'/d)(1+fy/6000)] ≤ fy` | `f'_s=6000[1-\tfrac{d'}{d}(1+\tfrac{f_y}{6000})]\le f_y` | d, d', fy | ACI 318-19 (compat. deformaciones) | SÍ (memoria) |
| ΔM | `calculo_estructural.py:145,953-955` | `ΔM = (Mu−Mmax)` | `\Delta M=M_u-M_{max}` | Mu, Mmax | MD §4.1 | SÍ (memoria) |
| A's (acero compresión) | `calculo_estructural.py:148` | `A's = ΔM·10⁵/(φ·f's·(d−d'))` | `A'_s=\dfrac{\Delta M}{\phi f'_s(d-d')}` | ΔM, φ, f's, d, d' | MD §4.3 · ACI 318-71 | SÍ (memoria+resultado `a_prima_cm2`) |
| As2 | `calculo_estructural.py:149` | `As2 = A's·f's/fy` | `A_{s2}=\dfrac{A'_sf'_s}{f_y}` | A's, f's, fy | MD §4.4 | SÍ (memoria) |
| As1 | `calculo_estructural.py:150` | `As1 = pmax·b·d` | `A_{s1}=\rho_{max}bd` | pmax, b, d | MD §4.5 | SÍ (memoria) |
| As total (doble armado) | `calculo_estructural.py:151` | `As = As1+As2` | `A_s=A_{s1}+A_{s2}` | As1, As2 | MD §4.6 · ACI 318-71 | SÍ (memoria+resultado) |
| ρb corregida / As,max doble | `calculo_estructural.py:153-155` | `pb_corr = pb + p'·fs'/fy`; `Asmax = 0.5·pb_corr·b·d` | — | p', fs', fy, pb | ACI 318-71 | SÍ (resultado `as_max_cm2`) |

### D — Viga T

| Fórmula | Archivo:línea | Expresión | LaTeX | Variables | Norma | Expuesto |
|---|---|---|---|---|---|---|
| Mp (momento del patín) | `calculo_estructural.py:185-186` | `Mp = φ·0.85·fc·bp·t·(d−t/2)/10⁵` | `M_p=\phi\,0.85f'_cb_pt(d-t/2)` | bp, t, d, fc, φ | MD §5.1 · ACI 318-71 | SÍ (memoria+resultado `Mp_patin_tm`) |
| Cf, Asf (acero equivalente patín) | `calculo_estructural.py:195-196` | `Cf=0.85·fc·(bp−bw)·t`; `Asf=Cf/fy` | `A_{sf}=\dfrac{0.85f'_c(b_p-b_w)t}{f_y}` | fc, bp, bw, t, fy | MD §5.3 · ACI 318-71 | SÍ (memoria+resultado `Asf_cm2`) |
| Mf (momento de las alas) | `calculo_estructural.py:197` | `Mf = φ·Cf·(d−t/2)/10⁵` | `M_f=\phi C_f(d-t/2)` | Cf, d, t, φ | MD §5.4 | SÍ (memoria+resultado `Mf_tm`) |
| pw (cuantía del alma) | `calculo_estructural.py:200-202` | `K=ΔM/(φ·fc·bw·d²)`; `pw=(fc/fy)(1−√(1−2.36K))/1.18` | — | ΔM, fc, bw, d, fy | MD §5.6-5.7 · ACI 318-71 | SÍ (memoria) |
| As total viga T | `calculo_estructural.py:204` | `As = Asw + Asf` | `A_s=A_{sw}+A_{sf}` | Asw, Asf | MD §5.9 · ACI 318-71 | SÍ (memoria+resultado) |
| ρb,T / As,max viga T | `calculo_estructural.py:206-208` | `pb_T=(bw/bp)(pb+Asf/(bw·d))`; `Asmax=0.5·pb_T·bp·d` | — | bw, bp, Asf, d, pb | ACI 318-71 | SÍ (resultado `as_max_cm2`) |

### E — Cortante

| Fórmula | Archivo:línea | Expresión | LaTeX | Variables | Norma | Expuesto |
|---|---|---|---|---|---|---|
| vc (resistencia concreto) | `calculo_estructural.py:239-247` | `vc=0.53√fc` (Nu=0); `·√(1+0.0285Nu/Ag)` (compr.); `·(1+0.0285Nu/Ag)` (tensión, ≥0) | `v_c=0.53\sqrt{f'_c}` | fc, Nu(kg), Ag | ACI 318-19 §22.5.6 | SÍ (memoria+resultado `vc_kg_cm2`) |
| vu (esfuerzo cortante actuante) | `calculo_estructural.py:250-256` | `vu = Vu·1000/(φ·bw·d)` | `v_u=\dfrac{V_u}{\phi b_wd}` | Vu(t), bw, d, φ=0.75 | MD §6.1 · ACI 318-71 | SÍ (memoria) |
| Av requerido | `calculo_estructural.py:259-263` | `Av=(vu−vc)·bw·S/fy` (0 si vu≤vc) | `A_v=\dfrac{(v_u-v_c)b_wS}{f_y}` | vu, vc, bw, S, fy | ACI 318-19 §22.5.8 | SÍ (memoria+resultado `av_cm2`) |
| Av,min | `calculo_estructural.py:266-268` | `Av,min = 3.52·bw·S/fy` | `A_{v,min}=\dfrac{3.52b_wS}{f_y}` | bw, S, fy | ACI 318-19 §9.6.3.3 | SÍ (memoria) |
| S,max cortante | `calculo_estructural.py:271-273` | `Smax = min(d/2, 60)` | — | d | — | SÍ (memoria vía `s_max_cm`) |

### F — Torsión (ACI 318-71 §11.6, clásicas)

| Fórmula | Archivo:línea | Expresión | LaTeX | Variables | Norma | Expuesto |
|---|---|---|---|---|---|---|
| Σx²y | `calculo_estructural.py:280-283` | `Σx²y = b²·d` (b=lado menor) | `\Sigma x^2y=b^2h` | b, d | ACI 318-71 §11.6 | SÍ (memoria, solo si Tu>0) |
| x1, y1 (estribo cerrado) | `calculo_estructural.py:286-290` | `x1=bw−2·rec`; `y1=d−rec` (rec=4cm) | `x_1=b_w-2\,rec` | bw, d, rec | ACI 318-71 §11.6 | SÍ (memoria) |
| vtu (esfuerzo torsión) | `calculo_estructural.py:293-296` | `vtu = 3·Tu·10⁵/(φ·Σx²y)` | `v_{tu}=\dfrac{3T_u}{\phi\Sigma x^2y}` | Tu(t·m), Σx²y, φ=0.75 | ACI 318-71 §11.6 | SÍ (memoria+resultado `vtu_kg_cm2`) |
| vtc básico | `calculo_estructural.py:299-301` | `vtc = 0.63√fc` | `v_{tc}=0.63\sqrt{f'_c}` | fc | — | SÍ (memoria) |
| vtc,max combinado | `calculo_estructural.py:304-308` | `vtc,max = 0.636√fc/√(1+(1.2vu/vtu)²)` | `v_{tc,max}=\dfrac{0.636\sqrt{f'_c}}{\sqrt{1+(1.2v_u/v_{tu})^2}}` | fc, vu, vtu | ACI 318-71 §11.6.6.2 | SÍ (memoria) |
| αt | `calculo_estructural.py:311-313` | `αt = min(0.66+0.33·x1/y1, 1.50)` | `\alpha_t=0.66+0.33x_1/y_1\le1.50` | x1, y1 | ACI 318-71 §11.6.8 | SÍ (memoria) |
| At requerido (1 rama) | `calculo_estructural.py:316-322` | `At=(vtu−vtc)·S·Σx²y/(3·αt·x1·y1·fy)` | `A_t=\dfrac{(v_{tu}-v_{tc})S\Sigma x^2y}{3\alpha_tx_1y_1f_y}` | vtu, vtc, S, Σx²y, αt, x1, y1, fy | ACI 318-71 §11.6.8 | SÍ (memoria+resultado `at_cm2`) |
| S,max torsión | `calculo_estructural.py:325-327` | `Smax = min((x1+y1)/4, 30)` | — | x1, y1 | — | SÍ (memoria) |
| Al (long. por torsión) | `calculo_estructural.py:330-338` | `opt1=2At(x1+y1)/S`; `opt2=max[(28bwS/fy·vtu/(vtu+vu))−2At, …−3.5bwS/fy]·(x1+y1)/S`; `Al=max(opt1,opt2)` | `A_l=\max[2A_t(x_1+y_1)/S,\;A_{l,min}]` | At, S, x1, y1, bw, vu, vtu, fy | ACI 318-71 §11.6.9 | SÍ (memoria+resultado `al_cm2`) |

### G — Columna: esbeltez (2º orden)

| Fórmula | Archivo:línea | Expresión | LaTeX | Variables | Norma | Expuesto |
|---|---|---|---|---|---|---|
| r (radio de giro) | `calculo_estructural.py:345-347` | `r = 0.3·t` | `r=0.3t` | t (lx o ly) | ACI aprox | SÍ (memoria) |
| λ (esbeltez) | `calculo_estructural.py:350-352` | `λ = k·lu/r` (esbelta si λ>22) | `\lambda=\dfrac{k\,l_u}{r}` | k, lu, r | — | SÍ (memoria) |
| Pc (carga crítica Euler) | `calculo_estructural.py:355-360` | `EI=Ec·Ig/(2.5(1+βd))`; `Pc=π²EI/(k·lu)²/1000` | `P_c=\dfrac{\pi^2EI}{(kl_u)^2}` | fc, Ig, k, lu, βd | ACI 318-19 §6.6.4.4 | SÍ (memoria, si λ>22) |
| δ (amplificador momento) | `calculo_estructural.py:363-369` | `δ = Cm/(1−Pu/(φ·Pc)) ≥ 1.0` (φ=0.65) | `\delta=\dfrac{C_m}{1-P_u/(\phi P_c)}\ge1.0` | Cm, Pu, φ, Pc | ACI 318-19 §6.6.4.4 | SÍ (memoria+resultado `delta_x`/`delta_y`) |
| ρg (cuantía geométrica) | `calculo_estructural.py:600-606` | `pg = As_col/Ag·100` (chk 1%≤ρg≤8%) | `\rho_g=\dfrac{A_{s,col}}{A_g}\times100` | As_col, Ag | MD §9.8 · ACI 318-71 | SÍ (memoria+resultado `pg_pct`, `ok_pg`) |

### H — Takeoff CSI 03 (cantidades)

| Fórmula | Archivo:línea | Expresión | LaTeX | Variables | Norma | Expuesto |
|---|---|---|---|---|---|---|
| Volumen concreto (viga) | `calculo_estructural.py:390` | `Vol = b·h·L`, `h=(d+rec)/100` | `V=b\cdot h\cdot L` | b, d, rec, L | CSI 03 30 00 | SÍ (resultado `concreto_m3`) |
| Encofrado (viga) | `calculo_estructural.py:391` | `Enc = (2·h+b)·L` | `Enc=(2h+b)L` | h, b, L | CSI 03 10 00 | SÍ (resultado `encofrado_m2`) |
| Acero longitudinal (viga) | `calculo_estructural.py:393-394` | `Acl=(As+A's+Al)·10⁻⁴·L·7850·1.15` | `Acl=(A_s+A'_s+A_l)10^{-4}L\cdot7850\cdot1.15` | As, A's, Al, L, densidad=7850, +15% empalme | CSI 03 20 00 | SÍ (resultado `acero_kg`) |
| Estribos (viga) | `calculo_estructural.py:396-401` | `n_estribos=L/(S/100)`; `Aes=Av·10⁻⁴·n·perím·7850` | `Aes=(A_v+2A_t)10^{-4}n\,p_{est}\cdot7850` | Av, S, L, perím estribo | CSI 03 20 00 | SÍ (resultado `estribos_kg`) |
| Volumen/Encofrado/Acero (columna) | `calculo_estructural.py:424-434` | análogas con Lx·Ly en vez de b·h | igual patrón | lx, ly, L, As_col | CSI 03 | SÍ (resultado) |

### I — Predimensionamiento (G2, regla del Director)

| Fórmula | Archivo:línea | Expresión | Variables | Norma | Expuesto |
|---|---|---|---|---|---|
| Columna: lado mínimo | `calculo_estructural.py:1335-1350` | `lado_min = niveles·10·0.8`; redondeo ↑ múltiplo 5 | niveles | Regla interna (Director) | SÍ — `POST /diseno/predimensionar` |
| Viga: peralte h | `calculo_estructural.py:1352-1368` | `h = (luz_libre−2·b_apoyo)/10`; `b≈h/2 (mín 20)`; redondeo ↑ múltiplo 5 | luz_libre, b_apoyo | Regla interna (Director) | SÍ — `POST /diseno/predimensionar` |

---

## 2. `backend/calculo_conexion_acero.py` — Conexiones de acero (AISC 360-16 §J, LRFD)

Unidades: kgf, cm, t. Criterio `Ru ≤ φRn` (§B3.1). Expuesto vía
`POST /conexion-acero/memoria-rapida` (narrado completo), CRUD persistente
`/conexion-acero/{pid}/conexiones*`, lote `/conexion-acero/import-etabs-fuerzas`,
y placas base `/diseno/{pid}/placas-base-etabs`.

### Constantes φ (líneas 40-51)
`PHI_SOLD=0.75 (§J2.4)`, `PHI_PERNO=0.75 (§J3.6)`, `PHI_FLUENCIA=0.90 (§J4.1)`,
`PHI_ROTURA=0.75 (§J4.2)`, `PHI_CORTE_FLU=1.00 (§J4.3)`, `PHI_CORTE_ROT=0.75 (§J4.4)`,
`PHI_BLOCK=0.75 (§J4.5)`, `PHI_APLAST=0.65 (§J8)`. Todas expuestas en `constantes[]`
de `memoria_conexion`.

### §J3 — Pernos

| Fórmula | Línea | Expresión | LaTeX | Norma | Expuesto |
|---|---|---|---|---|---|
| Ab (área nominal) | `109` | `Ab = π/4·db²` | `A_b=\tfrac{\pi}{4}d_b^2` | AISC §J3.6 | SÍ (memoria) |
| φRn corte pernos | `113-115` | `φRn = 0.75·Fnv·Ab·n` (J3-1) | `\phi R_{n,v}=0.75F_{nv}A_bn` | AISC §J3.6 ec.J3-1 | SÍ (memoria+`estados.perno_cortante`) |
| φRn tracción pernos | `118-120` | `φRn = 0.75·Fnt·Ab·n` (J3-1) | `\phi R_{n,t}=0.75F_{nt}A_bn` | AISC §J3.6 ec.J3-1 | SÍ (memoria+`estados.perno_traccion`) |
| F'nt combinado (tensión-corte) | `123-129` | `F'nt=1.3Fnt−(Fnt/(φFnv))·frv ≤ Fnt` (J3-3a) | `F'_{nt}=1.3F_{nt}-\tfrac{F_{nt}}{\phi F_{nv}}f_{rv}` | AISC §J3.7 ec.J3-3a | SÍ (memoria) |
| φRn aplastamiento | `132-135` | `φRn=0.75·(2.4·db·t·Fu)·n` (J3-6a) | `\phi R_n=0.75(2.4d_btF_u)n` | AISC §J3.10 ec.J3-6a | SÍ (memoria+`estados.perno_aplastamiento`) |
| φRn tearout/desgarre | `138-140` | `φRn=0.75·(1.2·lc·t·Fu)·n` (J3-6c) | `\phi R_n=0.75(1.2l_ctF_u)n` | AISC §J3.10 ec.J3-6c | SÍ (memoria+`estados.perno_tearout`) |

### §J2 — Soldadura

| Fórmula | Línea | Expresión | LaTeX | Norma | Expuesto |
|---|---|---|---|---|---|
| te (garganta efectiva) | `146-148` | `te = 0.707·w` | `t_e=0.707w` | AISC §J2.2a | SÍ (memoria) |
| Fnw (esfuerzo nominal cordón) | `151-154` | `Fnw=0.60·FEXX·(1+0.5·sin^1.5θ)` (J2-5, θ=0) | `F_{nw}=0.60F_{EXX}(1+0.5\sin^{1.5}\theta)` | AISC §J2.4 ec.J2-5 | SÍ (memoria) |
| φRn soldadura | `157-159` | `φRn=0.75·Fnw·te·L` (J2-3/4) | `\phi R_{n,sold}=0.75F_{nw}t_eL` | AISC §J2.4 ec.J2-3 | SÍ (memoria+`estados.soldadura`) |
| φRn metal base (corte) | `162-165` | `φRn=0.75·0.60·Fu·t_base·L` (J2-2, FnBM=0.6Fu) | `\phi R_{n,BM}=0.75\cdot0.6F_ut_{base}L` | AISC §J2.4(a) ec.J2-2 | SÍ (memoria+`estados.metal_base`) |
| Límites geométricos filete | `380-394` | `wmin` (Tabla J2.4 por espesor); `wmax=t_thin−0.16`; `Lmin=4w` | — | AISC Tabla J2.4 / §J2.2b | SÍ (memoria, chk `chk_soldadura`) |

### §J4 — Elementos afectados (placa de conexión)

| Fórmula | Línea | Expresión | LaTeX | Norma | Expuesto |
|---|---|---|---|---|---|
| φRn fluencia tracción | `171-173` | `φRn=0.90·Fy·Ag` (J4-1) | `\phi R_n=0.90F_yA_g` | AISC §J4.1 ec.J4-1 | SÍ (memoria+`estados.fluencia_traccion`) |
| φRn rotura tracción | `176-178` | `φRn=0.75·Fu·Ae` (J4-2) | `\phi R_n=0.75F_uA_e` | AISC §J4.1 ec.J4-2 | SÍ (memoria+`estados.rotura_traccion`) |
| φRn fluencia corte | `181-183` | `φRn=1.00·0.60·Fy·Agv` (J4-3) | `\phi R_n=0.60F_yA_{gv}` | AISC §J4.2 ec.J4-3 | SÍ (memoria+`estados.fluencia_corte`) |
| φRn rotura corte | `186-188` | `φRn=0.75·0.60·Fu·Anv` (J4-4) | `\phi R_n=0.45F_uA_{nv}` | AISC §J4.2 ec.J4-4 | SÍ (memoria+`estados.rotura_corte`) |
| φRn block shear | `191-196` | `φRn=0.75·min[0.6Fu·Anv+Ubs·Fu·Ant, 0.6Fy·Agv+Ubs·Fu·Ant]` (J4-5) | `\phi R_n=0.75[0.6F_uA_{nv}+U_{bs}F_uA_{nt}]` | AISC §J4.3 ec.J4-5 | SÍ (memoria+`estados.block_shear`) |

### §J8 — Placa base (aplastamiento concreto + espesor)

| Fórmula | Línea | Expresión | LaTeX | Norma | Expuesto |
|---|---|---|---|---|---|
| φPp aplastamiento concreto | `205-214` | `Pp=min(0.85·fc·A1·√(A2/A1), 1.7·fc·A1)`; `φPp=0.65·Pp` | `\phi P_p=0.65\cdot0.85f'_cA_1\sqrt{A_2/A_1}\le0.65\cdot1.7f'_cA_1` | AISC §J8 ec.J8-1/2 · ACI 318 §14 | SÍ (memoria+`j8.phiPp_t`) |
| Espesor placa base | `217-229` | `m=(N−0.95d)/2`; `n=(B−0.80bf)/2`; `n'=√(d·bf)/4`; `l=max(m,n,n')`; `fp=Pu/(B·N)`; `tp=l·√(2fp/(0.90Fy))` | `t_{p,req}=l\sqrt{2f_p/(0.90F_y)}` | AISC Design Guide 1 | SÍ (memoria+`j8.tp_req`) |

### Geometría derivada y demanda (helpers)

| Fórmula | Línea | Expresión | Norma | Expuesto |
|---|---|---|---|---|
| Geometría placa/pernos | `235-261` | `s=3db`, `Le=1.5db`, `lc=Le−dhole/2`, `h_placa=(n−1)s+2Le`, `Agv/Anv/Ag/Ae/Agt/Ant` | Convención interna | SÍ (memoria+`resultado.geo`) |
| Demanda gobernante | `367-375` | `demanda=max(|Vu|,|Nu|)`; VC_MOMENTO: `Fuf=Mu/(d−tf)` (par de alas); PLACA_BASE: `demanda=Pu_axial` | AISC §J10 | SÍ (memoria: paso `F_uf`) |
| DC (demanda/capacidad) | `377-378` | `DC = demanda/φRn_gob` (cumple si ≤1.0) | AISC §B3.1 | SÍ (memoria+`resultado.dc_ratio`) |

---

## 3. `backend/calculo_miembro_acero.py` — Miembros de acero LRFD (AISC 360-16 §D/E/F/G/H)

Verificación INDEPENDIENTE (chequeo cruzado del Steel Frame Design de ETABS).
Unidades kgf, cm, t. Expuesto vía `POST /miembro-acero/memoria-rapida` (narrado
completo, stateless) y `backend/services/partidas_bridge._correr_caso_acero`
(persiste `acero_estado_gob`, `acero_phi_rn_gob`, `acero_dc`, `acero_cumple`,
`acero_estados_json` en `ResultadoDiseno`, devuelto por `POST /diseno/casos/{cid}/calcular`
cuando `material_tipo == "ACERO"`).

### §D — Tracción

| Fórmula | Línea | Expresión | LaTeX | Norma | Expuesto |
|---|---|---|---|---|---|
| φPn fluencia | `75-77` | `φPn=0.90·Fy·Ag` (D2-1) | `\phi P_n=0.90F_yA_g` | AISC §D2(a) | SÍ (memoria+`estados.traccion`) |
| φPn rotura | `80-82` | `φPn=0.75·Fu·Ae` (D2-2) | `\phi P_n=0.75F_uA_e` | AISC §D2(b) | SÍ (memoria) |
| φPn gobernante | `264` | `φPn=min(fluencia, rotura)` | `\phi P_n=\min(0.90F_yA_g,0.75F_uA_e)` | AISC §D2 | SÍ (memoria+resultado) |

### §E — Compresión (pandeo por flexión, E3)

| Fórmula | Línea | Expresión | LaTeX | Norma | Expuesto |
|---|---|---|---|---|---|
| KL/r (esbeltez) | `88-90` | `KL/r = K·L/r_min` | `\dfrac{KL}{r}=\dfrac{KL}{r_{min}}` | AISC §E2 | SÍ (memoria) |
| Fe (Euler) | `93-95` | `Fe = π²E/(KL/r)²` (E3-4) | `F_e=\dfrac{\pi^2E}{(KL/r)^2}` | AISC ec.E3-4 | SÍ (memoria) |
| Fcr | `98-104` | inelástico: `Fcr=0.658^(Fy/Fe)·Fy` si `KL/r≤4.71√(E/Fy)` (E3-2); si no `Fcr=0.877·Fe` (E3-3) | `F_{cr}=(0.658^{F_y/F_e})F_y` / `0.877F_e` | AISC ec.E3-2/E3-3 | SÍ (memoria) |
| φPn compresión | `107-109` | `φPn=0.90·Fcr·Ag` (E3-1) | `\phi P_n=0.90F_{cr}A_g` | AISC §E3 | SÍ (memoria+`estados.compresion`) |

### §F — Flexión (I-shape con LTB §F2; HSS sin LTB §F7)

| Fórmula | Línea | Expresión | LaTeX | Norma | Expuesto |
|---|---|---|---|---|---|
| Mp (momento plástico) | `115-117` | `Mp = Fy·Zx` (F2-1) | `M_p=F_yZ_x` | AISC ec.F2-1 | SÍ (memoria) |
| Lp | `120-122` | `Lp = 1.76·ry·√(E/Fy)` (F2-5) | `L_p=1.76r_y\sqrt{E/F_y}` | AISC ec.F2-5 | SÍ (memoria) |
| Lr | `125-130` | fórmula compuesta con rts, Sx, J, ho (F2-6) | `L_r=1.95r_{ts}\tfrac{E}{0.7F_y}\sqrt{J/(S_xh_o)}\sqrt{1+\sqrt{1+6.76(\cdots)^2}}` | AISC ec.F2-6 | SÍ (memoria) |
| Mn (zona plástico/LTB inel./LTB elást.) | `133-148` | `Mn=Mp` (Lb≤Lp); `Mn=Cb[Mp−(Mp−0.7FySx)(Lb−Lp)/(Lr−Lp)]≤Mp` (F2-2); `Mn=Fcr·Sx≤Mp` con `Fcr` de F2-4 (Lb>Lr) | ver `LATEX_BY_FORMULA` líneas 395-398 | AISC §F2 | SÍ (memoria) |
| φMnx | `296` | `φMnx = 0.90·Mn` | `\phi M_n=0.90M_n` | AISC §F1 | SÍ (memoria+`estados.flexion_x`) |
| Mny (eje débil) | `151-153` | `Mny = min(Fy·Zy, 1.6·Fy·Sy)` (F6-1) | `M_{ny}=\min(F_yZ_y,1.6F_yS_y)` | AISC §F6 | SÍ (memoria+`estados.flexion_y`) |
| Mn HSS (F7, con FLB) | `175-187` | `Mp=Fy·Zx`; `λp=1.12√(E/Fy)`, `λr=1.40√(E/Fy)`; compacta→Mp; no-compacta→`Mn=Mp−(Mp−FySx)(3.57λ√(Fy/E)−4)`; esbelta→`Fy·Sx` (aprox) | AISC §F7-1/F7-2/F7-3 | AISC 360-16 §F7 | SÍ (memoria) |

### §G — Cortante

| Fórmula | Línea | Expresión | LaTeX | Norma | Expuesto |
|---|---|---|---|---|---|
| φVn (I-shape) | `159-172` | `Aw=d·tw`; `h/tw` vs límites; `Cv1`; `φVn=φ·0.6·Fy·Aw·Cv1` (G2-1) | `\phi V_n=\phi\,0.6F_yA_wC_{v1}` | AISC §G2 | SÍ (memoria+`estados.cortante`) |
| φVn (HSS, §G4) | `190-205` | `Aw=2·flat·t`; `Cv2` por esbeltez; `φVn=0.90·0.6·Fy·Aw·Cv2` | mismo patrón | AISC §G4 | SÍ (memoria) |

### §H — Interacción flexo-compresión

| Fórmula | Línea | Expresión | LaTeX | Norma | Expuesto |
|---|---|---|---|---|---|
| Razón de interacción | `211-219` | `Pr/Pc≥0.2 → Pr/Pc+(8/9)(Mrx/Mcx+Mry/Mcy)` (H1-1a); si no `Pr/(2Pc)+(Mrx/Mcx+Mry/Mcy)` (H1-1b) | ver líneas 404-407 | AISC ec.H1-1a/1b | SÍ (memoria+`estados.interaccion`) |

### Propiedades de sección derivadas (`backend/perfiles_acero.py::props_seccion`)

| Fórmula | Línea | Expresión | LaTeX | Expuesto |
|---|---|---|---|---|
| Sx, Sy | `perfiles_acero.py:235` | `Sx=2Ix/d`; `Sy=2Iy/bf` | `S_x=2I_x/d` | SÍ (memoria, sección "Seccion") |
| Zx (I-shape derivada) | `perfiles_acero.py:236-237` | `Zx=bf·tf·(d−tf)+tw·hw²/4` | `Z_x=b_ft_f(d-t_f)+t_wh_w^2/4` | SÍ (memoria) |
| rx, ry | `perfiles_acero.py:238-239` | `rx=√(Ix/Ag)`; `ry=√(Iy/Ag)` | `r_x=\sqrt{I_x/A_g}` | SÍ (memoria) |
| J (torsión) | `perfiles_acero.py:240` | `J=(2·bf·tf³+hw·tw³)/3` | — | SÍ (memoria, usado en Lr) |
| rts | `perfiles_acero.py:242` | `rts=√(√(Iy·Cw)/Sx)` | `r_{ts}=\sqrt{\sqrt{I_yC_w}/S_x}` | SÍ (memoria) |
| HSS: I, S, Z, r, J | `perfiles_acero.py:211-221` | sección hueca cuadrada, `bi=b−2t`, `I=(b⁴−bi⁴)/12`, `Am=(b−t)²`, `J=4Am²t/(4(b−t))` | — | SÍ (memoria, cuando `es_hss`) |

---

## 4. `backend/calculo_sismico_choc08.py` — Acción sísmica CHOC-08

Módulo ADITIVO, no toca el motor ACI. Unidades kgf, m, s, g=9.81 m/s².
Expuesto vía `POST /diseno/sismo/memoria` (narrado completo, stateless),
`POST /diseno/sismo/espectro-csv`, `PUT /diseno/{pid}/sismo` (persiste
`ContextoSismico`), `POST /diseno/sismo/import-etabs` (enriquece con escalado
+ verificación de derivas).

| Fórmula | Línea | Expresión | LaTeX | Variables | Norma | Expuesto |
|---|---|---|---|---|---|---|
| T_A (período Método A) | `79-81` | `T_A = Ct·hn^0.75` (Ct=0.0731, marco concreto) | `T_A=0.0731h_n^{3/4}` | hn | CHOC-08 1.3.6.5.3 | SÍ (memoria+meta `T_A`) |
| C (coeficiente sísmico) | `84-88` | `C = min(1.25·S/T^(2/3), 2.75)` | `C=\dfrac{1.25S}{T^{2/3}}\le2.75` | S, T | CHOC-08 1.3.6.4 | SÍ (memoria+meta `C`) |
| V (cortante basal) | `91-93` | `V = (Z·I·C/Rw)·W` | `V=\dfrac{ZIC}{R_w}W` | Z, I, C, Rw, W | CHOC-08 1.3.6.2 | SÍ (memoria+meta `V_kgf`) |
| C/Rw ≥ piso | `115,323-331` | `C/Rw ≥ 0.075` (C_RW_MIN) | `C/R_w\ge0.075` | C, Rw | CHOC-08 1.3.6.4 | SÍ (memoria, check) |
| Escalado cortante dinámico | `102-129` | `V_obj = pct·V_est` (pct=90% regular/100% irregular); `factor=max(1, V_obj/V_din)`; `cumple: V_din≥V_obj` | — | CHOC-08 1.3.6.5.3 | SÍ — `res["escalado"]` en `/diseno/sismo/import-etabs` |
| Verificación derivas por piso | `132-174` | por piso: `cumple = drift ≤ deriva_limite` | — | CHOC-08 1.3.5.8.2 | SÍ — `res["verificacion_derivas"]` |
| a/g(T) — rama ascendente | `177-180` | `a/g = 2.5·Z·(0.4+0.7T/Ta)` (T<Ta) | `a/g=2.5Z(0.4+0.7T/T_a)` | Z, T, Ta | CHOC-08 1.3.6-10 | SÍ (memoria+`espectro[]`) |
| a/g(T) — meseta | `181-182` | `a/g = 2.75·Z` (Ta≤T≤Tb) | `a/g=2.75Z` | Z | CHOC-08 1.3.6-11 | SÍ (memoria+meta `a_max_g`) |
| a/g(T) — rama descendente | `183-184` | `a/g = 2.75·Z·(Tb/T)^c` (T>Tb) | `a/g=2.75Z(T_b/T)^c` | Z, Tb, T, c | CHOC-08 1.3.6-12 | SÍ (memoria+`espectro[]`) |
| Deriva de entrepiso límite | `187-191` | `T<0.7: min(0.04/Rw,0.005)`; `T≥0.7: min(0.03/Rw,0.004)` | `\Delta_{lim}=\min(0.04/R_w,0.005)` | T, Rw | CHOC-08 1.3.5.8.2 | SÍ (memoria+meta `deriva_limite`) |
| Clasificación de suelo S1-S4 (SPT) | `sismo.py:225-254` (router, no en calculo_sismico) | promedio ponderado N60, mínimos, cohesivos blandos → S1..S4 | — | CHOC-08 Tabla 1.3.4-1 | SÍ — `POST /diseno/sismo/inferir-suelo` |
| qadm en profundidad de desplante | `sismo.py:256-273` | interpola capa SPT en `prof_desplante_m` → `qb_kg_cm2` | — | Estudio geotécnico (no-CHOC) | SÍ — `inferir-suelo` |

---

## 5. `backend/services/pricing.py` — Costeo de partidas (fuente única)

Módulo PURO (sin ORM), usa `decimal.Decimal` con `ROUND_HALF_UP` a 4 decimales
en los boundaries de escritura. Expuesto de forma indirecta: los valores que
produce se escriben en columnas `Partida.costo_base/precio_unitario/total` y
`Partida.costo_mo/costo_ma/unitario_matriz`, devueltas por endpoints de
`routers/partidas.py`, `routers/insumos.py`, `routers/presupuestos.py`,
`routers/calculos.py`, `routers/export.py` y `routers/acero_diseno.py`
(`conexion-generar-partida`).

| Fórmula | Línea | Expresión | Variables | Expuesto |
|---|---|---|---|---|
| Cuantización monetaria | `45-47` | `quantize_money(x) = round(x, 4, HALF_UP)` | x | SÍ (todos los campos monetarios de partida) |
| Costo base | `50-53` | `costo_base = costo_mo + costo_ma + unitario_matriz` | costo_mo, costo_ma, unitario_matriz | SÍ (`Partida.costo_base`, vía `GET`/serializers de partidas) |
| Bucketing 3 vías | `56-65` | `mo=Σ total(MANO_OBRA)`; `ma=Σ total(MATERIAL)`; `otros=Σ total(resto)` | insumos[].tipo, .total | SÍ (`Partida.costo_mo/costo_ma/unitario_matriz`) |
| Precio unitario | `68-71` | `PU = base·(1 + sobrecosto/100)` | base, sobrecosto_pct | SÍ (`Partida.precio_unitario`) |
| Total partida | `74-81` (`recalcular_partida`) | `total = cantidad · PU` | cantidad, PU | SÍ (`Partida.total`) |

---

## 6. `backend/routers/calculos.py` — Indirectos y totales de presupuesto

No es un `calculo_*.py` pero contiene fórmulas propias sobre el resultado de
`pricing.py`. Expuesto directamente vía `POST /presupuestos/{pid}/calcular` y
`GET /presupuestos/{pid}/reporte`.

| Fórmula | Línea | Expresión | Variables | Expuesto |
|---|---|---|---|---|
| Costo directo acumulado | `12-34` (`_recalcular_todo`) | `base_total = Σ(cantidad_partida · costo_base_partida)` | partidas del presupuesto | SÍ — response `costo_directo` |
| Factor de indirectos | `37-41` (`_factor_indirectos`) | `factor = 1 + sobrecosto/100` | sobrecosto% (config) | SÍ — implícito en `total_con_indirectos` |
| Total con indirectos | `57-59`, `86-94` | `total_con_indirectos = costo_directo · factor`; `monto_indirecto = costo_directo·pct/100` | costo_directo, factor/pct | SÍ — response de ambos endpoints |

---

## 7. `backend/cronograma.py` — Motor de cronograma (Gantt)

Módulo PURO. Expuesto vía `GET /presupuestos/{pid}/cronograma` y
`GET /presupuestos/{pid}/export-cronograma` (XLSX).

| Fórmula | Línea | Expresión | Variables | Norma/fuente | Expuesto |
|---|---|---|---|---|---|
| Jornadas-hombre por actividad | `141-158` (`_jornadas`) | prioridad `TIEMPOS_FIJOS` > `MANUAL_SPLIT` > catálogo V1.2: `jh_esp = esp_u·cantidad`; `jh_ay = ay_u·cantidad` | csi, cantidad, catálogo | Catálogo V1.2 (coef. `jor` de la ficha) | SÍ (`actividades[].jh_esp/jh_ay`) |
| Duración de actividad | `161-175` (`duracion_actividad`) | `dias = max(ceil(jh_esp/n_esp), ceil(jh_ay/n_ay), 1)` | jh_esp, jh_ay, n_esp, n_ay | Regla interna (cuadrilla chica 3+3 default) | SÍ (`actividades[].duracion_dias`) |
| Fecha de inicio (salta domingos) | `207-214` (`_suma_dias_laborales`) | suma `dias_lab` días hábiles (excluye domingo, `weekday()==6`) desde `fecha_arranque` | fecha_arranque, dias_lab | — | SÍ (`actividades[].fecha_inicio/fecha_fin`) |
| Secuenciación por fase | `218-254` (`construir_cronograma`) | `inicio_lab = cursor_lab.get(fase, offset)`; `cursor_lab[fase] += duracion` (encadenado por fase, offsets fijos por división CSI) | fase, offset (`CAP_FASE`/`CSI_FASE`) | Regla interna | SÍ (`actividades[].offset_dias/span_dias`) |
| Días laborables del proyecto (router) | `cronograma.py` (router) `102-111` | L-V cuentan 1.0, sábado 0.5, domingo 0 | fecha_inicio, fecha_fin | Regla interna ConsuConstruct | SÍ — response `dias_laborables` |

---

## Resumen de cobertura HTTP

El patrón arquitectónico del backend (motor puro → función `memoria_*` narrada →
router `*/memoria-rapida` o `*/memoria`) hace que **prácticamente ninguna fórmula
quede sin salida HTTP**: cada paso intermedio de cada motor (`calculo_estructural.py`,
`calculo_conexion_acero.py`, `calculo_miembro_acero.py`, `calculo_sismico_choc08.py`)
se narra explícitamente (símbolo + fórmula + sustitución numérica + valor + LaTeX)
en el endpoint `memoria` correspondiente para alimentar la "Hoja" estilo Mathcad del
frontend. Las excepciones son variables puramente internas de bucketing/formato
(p. ej. `_fmt`, `_paso`, conversores LaTeX) que no son fórmulas de ingeniería.

No se encontraron fórmulas de ingeniería o de costeo calculadas pero **completamente
mudas** (sin ningún `return`/response que las exponga, ni siquiera de forma parcial).
