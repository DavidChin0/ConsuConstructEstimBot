# Análisis de Combinaciones de Muros - ESTIMASTRUCT V1.1

**Fecha:** 2026-05-01  
**Status:** Análisis de gaps entre V1.1 actual y lista requerida

---

## 📊 RESUMEN EJECUTIVO

- **Fichas base de muros disponibles:** 8
- **Acabados disponibles:** 3 tipos principales
- **Cerámicas para baño disponibles:** 7
- **Combinaciones posibles teóricas:** 8 × 3 × 7 = 168
- **Combinaciones explícitas en V1.1:** 8 (solo bases, sin combinar)
- **Combinaciones faltantes:** ~160

---

## 📦 FICHAS BASE DISPONIBLES EN V1.1

### Bloques de Concreto (División 04 26)

| CSI | Código | Descripción | Espacio |
|-----|--------|-------------|---------|
| 04 26 00.1 | STR-05 | Pared de Bloque de Concreto de Partición 4" | 10 cm |
| 04 26 00.2 | STR-06 | Pared bloque 6" | 15 cm |
| 04 26 00.3 | STR-07 | Pared bloque 8" | 20 cm |
| 04 26 00.13 | STR-08 | Entabicado de Bloque 15 cm Con Repello y Pulido | 15 cm + acabado |

### Ladrillo (División 04 21)

| CSI | Código | Descripción |
|-----|--------|-------------|
| 04 21 13 | STR-09 | Pared Arquitectónica de Ladrillo Rafón de 90mm |
| 04 21 16 | STR-10 | Bordillo de concreto de ducha de ladrillo rafón |

### Piedra (División 04 41/43)

| CSI | Código | Descripción |
|-----|--------|-------------|
| 04 41 00 | STR-12 | Pared de Piedra de Cantera |
| 04 43 13.1 | STR-11 | Fachaleta de Piedra/Madera para Exterior |

---

## 🎨 ACABADOS DISPONIBLES EN V1.1

| CSI | Código | Descripción | Tipo |
|-----|--------|-------------|------|
| 04 05 13.1 | COA01 | Repello 1:4 | Repello simple |
| 04 05 13.2 | COA02 | Pulido con Cemento Bijao 2.5mm | Pulido |
| 04 05 13.3 | COA03 | Repello y Pulido de Mochetas, Ventanas | Repello + Pulido |

**Variantes de acabado requeridas según lista:**
- DC Nivel 1 (Detalle Constructor nivel básico)
- DC Nivel 2 (Detalle Constructor nivel avanzado)
- Exterior (para intemperie)
- Interior (para secano)
- Fachaleta EXT (acabado especial exterior)

---

## 🛁 CERÁMICAS PARA BAÑO DISPONIBLES EN V1.1

| CSI | Código | Descripción | Tamaño | Uso |
|-----|--------|-------------|--------|-----|
| 09 30 13.7 | CER-01 | Cerámica Baño "Optima Ivory" | 25x75 cm | Pared |
| 09 30 13.4 | CER-02 | Cerámica Barcelona Beige Samboro | 20x31 cm | Pared |
| 09 30 13.3 | CER-03 | Cerámica Baño 515 Niebla Gris Oscuro | Standard | Fondo |
| 09 30 13.8 | CER-04 | Cerámica Baño Mosaico Calacatta R11 | Mosaico | Decorativo |

---

## ❌ COMBINACIONES FALTANTES (Según lista requerida)

### PATRÓN A: Bloques 4" con acabados

**Requeridas en lista:**
```
✓ C - Bloque de 4* (10cm) + Repello y Pulido DC Nivel 1
✓ C - Bloque de 4* (10cm) + Repello y Pulido DC Nivel 2
✓ C - Bloque de 4* (10cm) + Repello y Pulido Interior
✓ C - Bloque de 4* (10cm) + Repello y Pulido Interior +Ceramica Baño 2.10
✓ C - Bloque de 4* (10cm) + Repello y Pulido Exterior +Ceramica Baño 1.50m
```

**Estado en V1.1:**
- ✅ Bloque 4" existe (STR-05)
- ❌ Acabados DC Nivel 1 NO existen
- ❌ Acabados DC Nivel 2 NO existen
- ❌ Combinaciones explícitas NO existen

---

### PATRÓN B: Bloques 6" con acabados

**Requeridas en lista:**
```
✓ C - Bloque de 6*                                                    [SUELTO]
✓ C - Bloque de 6* (15cm)                                             [SUELTO]
✓ C - Bloque de 6* (15cm) + Repello y Pulido DC Nivel 1              [FALTA]
✓ C - Bloque de 6* (15cm) + Repello y Pulido DC Nivel 2              [FALTA]
✓ C - Bloque de 6* (15cm) + Repello y Pulido Exterior +Ceramica 1.50m [FALTA]
✓ C - Bloque de 6* (15cm) + Repello y Pulido Exterior +Ceramica 1.50m (Samboro) [FALTA]
✓ C - Bloque de 6* (15cm) + Repello y Pulido Exterior +Ceramica Baño 2.10 [FALTA]
✓ C - Bloque de 6* (15cm) + Repello y Pulido Exterior +Ceramica Baño 2.10 (Samboro) [FALTA]
```

**Estado en V1.1:**
- ✅ Bloque 6" existe (STR-06)
- ❌ Ninguna combinación explícita

---

### PATRÓN C: Bloques 8" con acabados

**Requerida en lista:**
```
✓ C - Bloque de 8* (20cm) Muro de Retención
```

**Estado en V1.1:**
- ✅ Bloque 8" existe (STR-07) pero sin especificar "Muro de Retención"
- ❌ Especificación de retención falta

---

### PATRÓN D: Ladrillo Rafón

**Requerida en lista:**
```
✓ C - Pared Arquitectónica de Ladrillo Rafón de 90mm
```

**Estado en V1.1:**
- ✅ Existe (STR-09) - PERO falta especificar acabado + cerámica

---

### PATRÓN E: Especiales

**Requeridas en lista:**
```
✓ C - Bloque 4 Natural                          [FALTA]
✓ C - Pared Existente                           [FALTA]
✓ C - Pared Existente + VINYL                   [FALTA]
✓ C - Pared Existente + WPCInt                  [FALTA]
✓ C - Bordillo de Ducha                         [EXISTE: STR-10]
```

---

## 🔴 COMBINACIONES CRÍTICAS FALTANTES

### Nivel 1: Combinaciones más solicitadas (TOP 10)

| # | Combinación | Bloque | Acabado | Cerámica | V1.1 | Prioridad |
|---|-------------|--------|---------|----------|------|-----------|
| 1 | Bloque 6" + Repello + Cerámica Baño 1.50m | ✅ | ❌ | ✅ | ❌ | 🔴 CRÍTICA |
| 2 | Bloque 6" + Repello + Cerámica Baño 2.10 | ✅ | ❌ | ✅ | ❌ | 🔴 CRÍTICA |
| 3 | Bloque 6" + Repello DC Nivel 1 | ✅ | ❌ | N/A | ❌ | 🔴 CRÍTICA |
| 4 | Bloque 6" + Repello DC Nivel 2 | ✅ | ❌ | N/A | ❌ | 🔴 CRÍTICA |
| 5 | Bloque 4" + Repello DC Nivel 1 | ✅ | ❌ | N/A | ❌ | 🟠 ALTA |
| 6 | Bloque 4" + Repello + Cerámica Baño | ✅ | ❌ | ✅ | ❌ | 🟠 ALTA |
| 7 | Pared Existente (sin obra) | N/A | N/A | N/A | ❌ | 🟠 ALTA |
| 8 | Bloque 4 Natural (sin acabado) | ✅ | ❌ | N/A | ❌ | 🟠 ALTA |
| 9 | Ladrillo Rafón + acabado | ✅ | ❌ | ✅ | ❌ | 🟡 MEDIA |
| 10 | Bloque 8" con especificación retención | ✅ | ❌ | N/A | ❌ | 🟡 MEDIA |

---

## 📋 MATRIZ DE COMBINACIONES POSIBLES

### BLOQUES × ACABADOS × APLICACIONES

```
Bloques Base (8):
├── 4" bloque concreto
├── 6" bloque concreto
├── 8" bloque concreto (retención)
├── 15cm entabicado
├── Ladrillo Rafón 90mm
├── Piedra Cantera
├── Fachaleta Piedra/Madera
└── Bordillo ducha

Acabados (3 base + 5 variantes requeridas):
├── Repello 1:4
├── Pulido Cemento
├── Repello + Pulido
├── [FALTA] Repello DC Nivel 1
├── [FALTA] Repello DC Nivel 2
├── [FALTA] Acabado Exterior
├── [FALTA] Acabado Interior
└── [FALTA] Fachaleta EXT

Cerámicas (7 + especificaciones):
├── Cerámica 1.50m (CER-01)
├── Cerámica 2.10 (CER-02/03/04)
├── Cerámica Samboro 1.50m (CER-02 variant)
├── Cerámica Samboro 2.10 (CER-02 variant)
└── Sin cerámica (repello solo)

COMBINACIONES TEÓRICAS: 8 × 8 × 7 = 448
COMBINACIONES REQUERIDAS (lista): ~35
COMBINACIONES EN V1.1: 8 (solo bases)
BRECHA: ~27 combinaciones faltantes
```

---

## 💾 ACCIONES RECOMENDADAS

### Corto Plazo (Next Session)
1. **Crear fichas de acabados normalizados:**
   - `04 05 13.DC1` - Repello y Pulido DC Nivel 1
   - `04 05 13.DC2` - Repello y Pulido DC Nivel 2
   - `04 05 13.EXT` - Acabado Exterior
   - `04 05 13.INT` - Acabado Interior

2. **Crear fichas especiales:**
   - `04 26 00.Natural` - Bloque 4" Natural sin acabado
   - `04 26 00.Exist` - Pared Existente
   - `04 26 00.Exist.Vinyl` - Pared Existente + Vinyl
   - `04 26 00.Exist.WPC` - Pared Existente + WPC Interior

### Mediano Plazo (This sprint)
1. **Generar fichas combinadas explícitas** para top 10 combinaciones
2. **Validar especificaciones** de cerámicas (1.50m vs 2.10m)
3. **Mapear cerámica Samboro** como variante de CER-02

### Largo Plazo
1. **Crear sistema de composición** que permita combinar fichas dinámicamente
2. **Template system** para generar automáticamente fichas de combinaciones

---

## 📎 REFERENCIAS

- **Fichas V1.1:** `D:\OneDrive\Bots\Estimbot\Estimacion\development\Template2_Updated\v1.1\fichas\fichas_v1.1.json`
- **Lista requerida:** Proporcionada en screenshot (35+ combinaciones)
- **Clasificación:** MasterFormat 2018 (Divisiones 04, 05, 09)
