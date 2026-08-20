# goal-21068 — Cobertura FHIS -> catalogo EstimaStruct (STAGING)

**Rol:** estimastruct · **Fuente:** FHIS Manual de Rendimientos 2003-11 (Cred. BM 3443-HO) · via Quercusoft index

**Estado:** tabla intermedia construida, cero escritura a produccion. Poblar valores numericos = gated a 2o OK.


## 1. Volumen adquirido

- Actividades FHIS parseadas: **2204** (activas 2084 / inhabilitadas 120)
- Capitulos FHIS mapeados a CSI: **34** de 34
- Filas de rendimiento por recurso: **0** (pendiente extraccion PDF, gated)


## 2. Cobertura por division CSI del catalogo vivo (375 fichas v1.3)

| CSI div | Nombre | # fichas catalogo | FHIS cubre? |
|---|---|---:|---|
| 00 | (no en mapa CSI base) | 11 | NO — hueco |
| 01 | General Requirements | 16 | SI |
| 02 | Existing Conditions / Demolicion | 8 | SI |
| 03 | Concrete | 57 | SI |
| 04 | Masonry | 18 | SI |
| 05 | Metals | 47 | SI |
| 06 | (no en mapa CSI base) | 5 | NO — hueco |
| 07 | Thermal & Moisture Protection | 10 | SI |
| 08 | Openings | 24 | SI |
| 09 | Finishes | 22 | SI |
| 10 | (no en mapa CSI base) | 2 | SI |
| 11 | Equipment | 2 | NO — hueco |
| 12 | Furnishings | 13 | SI |
| 21 | (no en mapa CSI base) | 3 | NO — hueco |
| 22 | Plumbing | 56 | SI |
| 23 | (no en mapa CSI base) | 7 | NO — hueco |
| 25 | (no en mapa CSI base) | 4 | NO — hueco |
| 26 | Electrical | 33 | SI |
| 27 | (no en mapa CSI base) | 8 | NO — hueco |
| 28 | (no en mapa CSI base) | 2 | NO — hueco |
| 31 | Earthwork | 11 | SI |
| 32 | Exterior Improvements | 13 | SI |
| 33 | Utilities | 1 | SI |

**Cobertura:** 15/23 divisiones CSI del catalogo tienen fuente FHIS. Huecos: 8.
Los huecos son el segmento de edificacion vertical fina que goal-21065 §3 ya preveia rellenar con **Suarez Salazar**.


## 3. Crosswalk capitulo FHIS -> division CSI

| Cap FHIS | Nombre | #act (act) | CSI prim | Secundarias | Conf | Nota |
|---|---|---|---|---|---|---|
| F01 | Limpieza, demolicion, trazado y movimiento de tierra menor | 114 (108) | 02 Existing Conditions / Demolicion | 31 | media | Limpieza/demolicion (02) + corte/conformacion/acarreo (31 Earthwork) |
| F02 | Cimentacion (mamposteria, zapatas, pedestales, dados) | 139 (136) | 03 Concrete | 31 | media | Cimentacion de concreto (03 substructure); excavacion asociada -> 31 |
| F03 | Estructura de concreto (solera, castillo, columna, viga) | 350 (316) | 03 Concrete | - | alta | Solera/castillo/columna/viga/losa = estructura de concreto |
| F04 | Paredes (ladrillo, bloque, adobe, concreto) | 57 (50) | 04 Masonry | 03 | media | Paredes de bloque/ladrillo/adobe (04); pared de concreto reforzado -> 03 |
| F05 | Concreto y acero de refuerzo | 12 (11) | 03 Concrete | - | alta | Concreto y acero de refuerzo genericos |
| F06 | Acabados (afinado, azulejo, curado, jardin) | 39 (32) | 09 Finishes | - | alta | Afinado/azulejo/curado = acabados |
| F07 | Pisos | 42 (42) | 09 Finishes | - | alta | Pisos = acabados |
| F08 | Techos, cielo falso y canaletas | 80 (79) | 07 Thermal & Moisture Protection | 09 | media | Techos/canaletas (07 Moisture); cielo falso -> 09 Finishes |
| F09 | Losas | 13 (10) | 03 Concrete | - | alta | Losas de concreto = estructura |
| F10 | Tuberia de agua potable (PVC/concreto) | 189 (189) | 22 Plumbing | 33 | media | Tuberia agua potable interior (22); redes de sitio -> 33 Utilities |
| F11 | Saneamiento (cajas, tanque septico, letrina, pozo) | 70 (68) | 22 Plumbing | 33 | media | Cajas/tanque septico/letrina/pozo = saneamiento (22/33) |
| F12 | Ventaneria, contramarcos, divisiones y balcones | 81 (78) | 08 Openings | 10 | media | Contramarcos/ventaneria/balcones (08 Openings); divisiones -> 10 Specialties |
| F13 | Apoyos estructurales (neopreno) | 60 (60) | 05 Metals | 03 | media | Apoyos de neopreno = accesorio estructural (05/03) |
| F14 | Cercos, malla ciclon y postes | 33 (28) | 32 Exterior Improvements | - | alta | Cercos/malla ciclon/postes = obra exterior |
| F15 | Pavimentos, adoquin, bordillo y sellos | 28 (28) | 32 Exterior Improvements | 33 | media | Pavimentos/adoquin/bordillo (32); base vial -> 33 |
| F16 | Alcantarillado sanitario (pozos, PVC, pruebas) | 48 (45) | 33 Utilities | - | alta | Alcantarillado sanitario = utilities |
| F17 | Pinturas | 12 (12) | 09 Finishes | - | alta | Pinturas = acabados |
| F18 | Direccion tecnica de obra | 3 (3) | 01 General Requirements | - | alta | Direccion de obra = requisitos generales/indirectos |
| F19 | Cunetas y rejillas | 38 (38) | 32 Exterior Improvements | 33 | media | Cunetas (32 exterior) y rejillas de drenaje (33) |
| F20 | Aparatos sanitarios | 38 (36) | 22 Plumbing | - | alta | Aparatos sanitarios = plomeria |
| F21 | Instalacion electrica e iluminacion | 383 (377) | 26 Electrical | - | alta | Instalacion electrica e iluminacion |
| F22 | Drenaje pluvial (tragantes, bajantes) | 8 (8) | 22 Plumbing | 33 | media | Drenaje pluvial: bajantes (22) y tragantes de sitio (33) |
| F23 | Valvulas, impermeabilizacion y obra de concreto hidraulica | 85 (84) | 22 Plumbing | 07,33 | media | Valvulas/obra hidraulica (22/33); impermeabilizacion -> 07 |
| F25 | Horas maquina (tractor, equipo pesado) | 11 (11) | 31 Earthwork | - | alta | Horas maquina pesada = movimiento de tierra |
| F26 | Remocion y carga con maquinaria | 28 (26) | 31 Earthwork | - | alta | Remocion/carga con maquinaria = earthwork |
| F27 | Bajantes PVC | 47 (39) | 22 Plumbing | - | alta | Bajantes PVC = plomeria pluvial |
| F28 | Gradas, pasamanos y asta de bandera | 63 (61) | 05 Metals | 03 | media | Pasamanos/asta HG (05 Metals); gradas de concreto -> 03 |
| F30 | Puentes colgantes peatonales | 38 (35) | 32 Exterior Improvements | 05 | media | Puentes colgantes peatonales = obra especial exterior/metalica |
| F50 | Mobiliario escolar | 61 (40) | 12 Furnishings | - | alta | Mobiliario escolar = furnishings |
| F51 | Material didactico y alimentacion (programa social) | 13 (13) | 01 General Requirements | 12 | media | Material didactico/alimentacion = suministro social (fuera de obra fisica) |
| F52 | Ensayos de suelos (Proctor, densidad) | 2 (2) | 02 Existing Conditions / Demolicion | 31 | media | Ensayos de suelos = existing conditions/testing |
| F53 | Alquiler de maquinaria (excavadora) | 3 (3) | 31 Earthwork | - | alta | Alquiler de maquinaria = earthwork |
| F54 | Juegos infantiles y mobiliario de sitio | 9 (9) | 32 Exterior Improvements | 12 | media | Juegos infantiles/mobiliario de sitio = exterior/furnishings |
| F55 | Mobiliario urbano (bancas, faroles) | 7 (7) | 32 Exterior Improvements | 12 | media | Mobiliario urbano (bancas/faroles) = exterior/furnishings |

## 4. Frontera (lo que NO se hizo — gate de produccion)

- **No se poblo ni un valor de rendimiento** en el catalogo. `rendimiento_fuente` esta vacia por diseno.
- Poblar exige: (a) extraer los valores numericos de las fichas escaneadas del PDF FHIS, (b) 2o OK explicito de David, (c) confirmar a que BD escribe el backend activo (SQLite versionada del repo, no Postgres — memoria split-brain).
- Precios NO se tocan: se montan al final desde CHICO 2025/2026.
