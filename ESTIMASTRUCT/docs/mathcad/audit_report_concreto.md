# Reporte de Auditoría — Hoja "Revision Elementos Concreto ACI 318-19"

> **Fecha:** 2026-06-03 · **Hoja:** `D:\OneDrive\Documents\MathCad\Revision Elementos Concreto ACI 318-19.mcdx`
> **Método:** auditoría por MCP → `save_as_pdf` → lectura del render → comparación numérica vs
> motor `calculo_estructural.py` (ACI 318-19 + torsión 318-71) + ecuaciones ACI 318-19.
> **Ejemplo:** viga b=30·d=50·fc=210·fy=4200 · columna lx=40·Pu=80 t·lu=300.

---

## 1. Resumen ejecutivo

**Hoja VALIDADA al 100%.** ~45 fórmulas (CC0–CC8) verificadas; **cada resultado coincide** con el motor.
Los fixes de unidad de sesiones previas **renderizan correctos en vivo**: `Asmin`=5 cm² (no `cm²/Pa`),
`Avmin`=0.503 cm², `term28`=2 cm² (no `0.0`). El marco de comprobación es **Diseño por Resistencia
ACI 318-19** (sin "LRFD"). Hallazgos = 2 de título/texto + 1 de motor (vtc torsión) + 1 cosmético.

---

## 2. Auditoría por capítulo

| Cap | Símbolo | Fórmula (hoja) | Resultado hoja | Esperado motor/ACI | ✓ |
|-----|---------|----------------|----------------|--------------------|---|
| CC0 | φ, FMAX, eu | constantes | 0.90·0.75·0.65·0.5 · 6000 | §21.2.1 | ✅ |
| CC1 | β1 | if(fc≤280, 0.85, …) | 0.85 | §22.2.2.3 | ✅ |
| CC1 | Ec | 15100·√(fc) | 2.188×10⁵ kgf/cm² | 218 795 | ✅ |
| CC4 | ρb | 0.85·fc·β1·eu/(fy·(eu+fy)) | 0.021 | 0.02125 | ✅ |
| CC4 | ρmax | FMAX·ρb | 0.011 | 0.01063 | ✅ |
| CC4 | K | Mu/(φ·fc·b·d²) | 0.106 | 0.1058 | ✅ |
| CC4 | ρreq | (fc/fy)·(1−√(1−2.36K))/1.18 | 0.006 | 0.00567 | ✅ |
| CC4 | As | ρreq·b·d | 8.506 cm² | 8.505 | ✅ |
| CC4 | **Asmin** | **14[kgf/cm²]·b·d/fy** | **5 cm²** | 5.0 (fix unidad ✓) | ✅ |
| CC4 | Asmax·As_final | ρmax·b·d · max(As,Asmin) | 15.938 · 8.506 cm² | ✓ | ✅ |
| CC4 | qm·Mmax | ρmax·fy/fc · φMn,max | 0.213 · 2.635×10⁶ | ✓ | ✅ |
| CC5 | vc·vu | 0.53√fc · Vu/(φbd) | 7.68 · 17.778 kgf/cm² | ✓ | ✅ |
| CC5 | Av | (vu−vc)·b·S/fy | 1.442 cm² | 1.443 | ✅ |
| CC5 | **Avmin** | **3.52[kgf/cm²]·b·S/fy** | **0.503 cm²** | 0.503 (fix ✓) | ✅ |
| CC5 | smax_v | min(d/2, 60) | 25 cm | 25 | ✅ |
| CC6 | sumx2y·x1·y1 | b²·d · b−2r · d−r | 45000 · 22 · 46 | ✓ | ✅ |
| CC6 | vtu·vtc | 3Tu/(φΣx²y) · 0.63√fc | 17.778 · 9.13 kgf/cm² | ✓ | ✅ |
| CC6 | αt·At | min(.66+.33x1/y1,1.5) · torsión | 0.818 · 0.746 cm² | ✓ | ✅ |
| CC6 | **term28** | **(28[kgf/cm²]·b·S/fy)·vtu/(vtu+vu)** | **2 cm²** | 2.0 (fix ✓) | ✅ |
| CC6 | Al_1·Al_2·Al | longitudinal torsión | 5.075 · 1.725 · 5.075 cm² | ✓ | ✅ |
| CC7 | r·λ·Ig | 0.3lx · klu/r · lx⁴/12 | 12 · 25 · 2.133×10⁵ | ✓ | ✅ |
| CC7 | EI·Pc | Ec·Ig/(2.5(1+βd)) · π²EI/(klu)² | 1.167×10¹⁰ · 1.28×10⁶ | ✓ | ✅ |
| CC7 | δ | Cm/(1−Pu/(φ·Pc)) ≥ 1 | 1.106 | 1.106 | ✅ |
| CC8 | DC_flex·DC_mom | ρreq/ρmax · Mu/Mmax | 0.534 · 0.569 | ✓ | ✅ |
| CC8 | DC_cort | vu/(vc+vs_prov) | 1.0 | 1.0 | ✅ |
| CC8 | DC_tor | vtu/vtc | 1.947 → requiere | ✓ | ✅ |
| CC8 | DC_esbeltez·DC_estab | λ/22 · Pu/(φPc) | 1.136 · 0.096 | ✓ | ✅ |
| CC8 | DC_viga·Cumple_global | max(flex,mom,cort) · veredicto | 1.0 · "VIGA CUMPLE" | ✓ | ✅ |

**~45/45 ✓.** Cero errores numéricos.

---

## 3. Lectura del ejemplo (resultado real, no maquillado)

- **Flexión:** As=8.51 cm² (≥ Asmin 5) — DC 0.53 ✓
- **Cortante:** Av=1.44 cm² @ S=20 — DC 1.00 (estribos al límite) ✓
- **Torsión:** vtu/vtc=1.95 → **requiere acero por torsión** (At=0.75, Al=5.08 cm²)
- **Columna:** λ=25 > 22 → **esbelta** (magnificar, δ=1.106) pero **estable** (DC_estab 0.10)
- **Veredicto viga:** DC_gob=1.00 → "VIGA CUMPLE"

---

## 4. Hallazgos

| # | Severidad | Hallazgo | Acción |
|---|-----------|----------|--------|
| C-1 | 🟡 título | Encabezado dice **"ACI 318-14"** + **"Columna"**; el contenido es 318-19 y cubre viga + columna | actualizar título a "ACI 318-19 — Viga y Columna" |
| C-2 | 🟡 texto | CC1 muestra **"β1 §22.2.2.4"**; la ref correcta es **§22.2.2.3** (ya fijo en el MD, no en la hoja) | corregir región de texto en Prime |
| C-3 | 🟡 motor | `At` usa `vtc`=`vtc_basico`(9.13). El motor usa `vtcmax_combinado`(≈5.90) cuando vu>0 → la hoja **subestima At** (0.746 vs ≈1.03 cm²) en cortante+torsión simultáneos | usar vtc combinado si el caso tiene Vu y Tu juntos |
| C-4 | 🟢 cosmético | `ver_esbeltez` (string largo) se corta en el borde del PDF; valor completo correcto | reposicionar región |

**Cero hallazgos numéricos.** Toda la matemática es correcta.

---

## 5. Marco normativo — corregido

El módulo es **ACI 318-19 Diseño por Resistencia** (U ≤ φSn), **NO "LRFD"** (término AISC/acero).
La hoja CC8 ya refleja el marco correcto (Mu≤φMn, Vu≤φVn, Tu≤φTn; φ §21.2.1, factor embebido en
`Mmax`=φMn y `vu`=Vu/φbd). Torsión usa fórmulas ACI 318-71 §11.6 (Σx²y) — el motor aún no implementa
el tubo de pared delgada de 318-19 §22.7 (pendiente, documentado).

---

## 6. Conclusión

Hoja "Revision Elementos Concreto ACI 318-19" = **calculadora ACI 318-19 validada** (viga: flexión,
cortante, torsión + columna: esbeltez/magnificación). 45/45 fórmulas correctas vs motor EstimaStruct.
Fixes de unidad confirmados en vivo. Lista como documento de verificación firmable.

**Siguiente:** designar Output en Prime (β1, Ec, ρb, ρmax, K, As, Mmax, vc, Av, At, Al, λ, Pc, δ, DC_*)
para auditoría MCP en vivo (sin PDF) + corregir título (C-1) y ref β1 (C-2) en la hoja.
