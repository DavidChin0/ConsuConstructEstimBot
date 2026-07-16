# Audit Log — Módulo Miembro de Acero LRFD §D-H

> **Fecha:** 2026-06-02 · **Motor auditado:** `backend\calculo_miembro_acero.py` (+ `perfiles_acero.py`)
> **Método:** lectura línea-a-línea + verificación numérica contra el endpoint en vivo
> (`POST /miembro-acero/memoria-rapida`, W310X73 A992). **Sin fórmulas inventadas.**
> Severidad: 🔴 alta (incorrecto/inseguro) · 🟠 media (conservador o incompleto) · 🟡 baja (doc/cosmético) · 🟢 verificado OK.

---

## 1. Resumen ejecutivo

Motor **sólido y verificable**. Las 7 familias de estados (§D/E/F/F7/G/G4/H) están implementadas con las ecuaciones correctas de AISC 360-16 y reproducen el ejemplo numérico dentro de tolerancia. **No falta ninguna fórmula que requiera reconstrucción** — los hallazgos son límites de **alcance normativo** (estados no codificados) y una **inconsistencia de documentación**, no errores de cálculo. DC gobernante del caso patrón: 0.8465 (§H1), CUMPLE.

---

## 2. Hallazgos

### 🟠 A-1 — §H1 no evalúa tracción + flexión combinada
`calcular_miembro` línea **325**: `if (Pu < 0 and (Mux > 0 or Muy > 0))`. La interacción §H1 se construye **solo** cuando `P_u` es compresión. Un miembro en **tracción + flexión** no recibe chequeo de interacción (§H1.2 permite `P_c = φP_n,tracción`); se verifica tracción y flexión por separado, lo que puede ser **no conservador** para tracción axial alta + momento.
**Recomendación:** añadir rama `Pu > 0` con `Pc = phiPn_t` y la misma H1-1a/1b. **Impacto Mathcad:** la hoja ya define `DC_traccion` y `DC_flexion_*` por separado; agregar `IR_traccion` análogo.

### 🟠 A-4 — HSS pared esbelta: §E7 y §F7 esbelta aproximados
- §E compresión HSS: línea **284-288** emite aviso "§E7 reduce φPn (no codificado, optimista)" cuando `b/t > 1.40√(E/Fy)`. No se aplica reducción por ancho efectivo → **φPn optimista** para HSS de pared esbelta.
- §F7 esbelta: línea **187** `return Fy*Sx` con comentario "Se≈Sx aprox" — no codifica el módulo de sección efectivo (`Se`) del ancho efectivo.
**Recomendación:** codificar §E7 (Q·factor) y `Se` (§F7-3) o restringir el catálogo a HSS compactas. **Impacto:** afecta solo HSS de pared esbelta (las del catálogo actual HSS8X8X1/4, 6X6X3/16 son compactas → sin efecto práctico hoy).

### 🟠 A-5 — §F I-shape asume sección compacta (sin §F3/§F4)
`mn_flexion` (línea 133) implementa F2 (fluencia + LTB) pero **no** chequea pandeo local de ala (§F3) ni de alma (§F4/F5). Para perfiles W laminados estándar esto es correcto (casi todos compactos), pero un perfil de **ala no-compacta/esbelta** quedaría no conservador.
**Recomendación:** añadir chequeo de `λ_f = bf/(2tf)` vs `λ_pf, λ_rf` (§F3) y reducir Mn si aplica. **Impacto:** bajo con catálogo CISC/AISC actual.

### 🟡 A-3 — Cv1 de alma no-compacta usa forma G2-4 simplificada
`vn_cortante` línea **169**: `Cv1 = lim2/h_tw` (sin separar la región intermedia G2-3 de la esbelta G2-4). Comentado "(aprox)". Conservador o ligeramente impreciso solo cuando `h/tw > 2.24√(E/Fy)` — raro en W laminados (la mayoría dan `Cv1=1, φ=1.0`).
**Recomendación:** opcional, separar G2-3 (`Cv1` lineal) de G2-4 (`Cv1` cuadrático).

### 🟡 A-2 — Docstring desactualizado (doc ↔ código)
Cabecera líneas **20-21**: *"HSS: §E/§F omitidos (fórmula I-shape no aplica) — fase siguiente"*. **Falso desde R1** (2026-06-02): el código ya tiene `mn_flexion_hss` (§F7), `vn_cortante_hss` (§G4) y §E3 vale para HSS. Inconsistencia de documentación.
**Recomendación:** actualizar el docstring para reflejar HSS §E3/§F7/§G4 implementados.

### 🟡 A-6 — Tracción `Ae = Ag` (U=1) — documentado, no es bug
Línea **263**: `Ae = Ag`. Correcto a nivel de miembro (sin agujeros); la reducción por conexión pernada (§D3, U<1) se trata en el módulo §J. Ya se emite aviso al usuario (línea 269). **Sin acción.**

---

## 3. Verificado OK 🟢

| Ítem | Línea | Verificación |
|------|-------|--------------|
| Factores φ (§D/E/F/G) | 39-44 | 0.90/0.75/0.90/0.90/1.00 correctos |
| E3 frontera + Fcr | 98-104 | `4.71√(E/Fy)` y `0.658^(Fy/Fe)` / `0.877Fe` correctos (Fcr=2655.8 ✓) |
| F2-6 Lr (forma completa) | 125-130 | incluye `1+√(1+6.76·(…)²)` — AISC exacto (Lr=877 ✓) |
| F2-2 LTB inelástico | 142 | `Cb[Mp−(Mp−0.7FySx)(Lb−Lp)/(Lr−Lp)]≤Mp` (Mn=38.812 ✓) |
| H1-1a/1b | 211-219 | umbral 0.2, `(8/9)` correcto (IR=0.8465 ✓) |
| Bug carga-cero | 254-259, 337-346 | capacidades siempre calculadas; `hay_demanda` separa "sin carga" de "no cumple" |
| Gobernante = max DC | 342-346 | solo estados con `demanda>0` |

---

## 4. Trazabilidad y reconstrucción

- **Fórmulas reconstruidas:** 0 (ninguna faltaba; todas presentes en el motor).
- **Fuente de cada ecuación:** funciones puras `pn_*`, `fcr_columna`, `mn_flexion`, `mn_flexion_hss`, `vn_cortante`, `vn_cortante_hss`, `interaccion_h1` (líneas 75-219) + narración `memoria_miembro`.
- **Verificación numérica:** endpoint en vivo, 25 pasos, DC_gob=0.8465 — coincide con la hoja Mathcad autoreada (§Verificación MCP).
- **Propiedades de sección:** auditadas en su propio módulo (`perfiles_acero` → `modulo_perfiles`).

## 5. Acciones sugeridas (priorizadas)

1. 🟠 **A-1** — extender §H1 a tracción+flexión (`Pc = φPn,tracción`). *(mayor valor de seguridad)*
2. 🟡 **A-2** — corregir docstring HSS (1 línea).
3. 🟠 **A-5 / A-4** — §F3 ala no-compacta + §E7/§F7 esbeltas, o restringir catálogo a compactas + aviso explícito.
4. 🟡 **A-3** — refinar Cv1 G2-3/G2-4 (opcional).

> Ninguna acción es bloqueante para el uso actual (catálogo de perfiles compactos). A-1 es la única con impacto de seguridad real, y solo en miembros con tracción axial significativa + flexión.
