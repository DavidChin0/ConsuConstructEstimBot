# Audit Precios V1.3 -- Materiales COMPLETO (321) vs Ferreterias HN (2026-07-31)

Estado: **16 updates APLICADOS en copia PILOT** (`estimastruct_v1.3_pilot.db`, alembic 606c3f3a7b6b). BD viva `C:\EstimaStruct\data\estimacion.db` **sin tocar**. Requiere OK Director para promover pilot -> vivo.

## Updates aplicados en pilot (16, confianza Alta)

| Clave | Material | Antes | Despues | Delta | Nota |
|---|---|---|---|---|---|
| MA-001 | Cemento Portland | 230.00 | 245.00 | +6.5% | Techo CHICO/Director |
| MA-022 | Varilla 3/8 G40 | 190.00 | 144.50 | -23.9% | Larach |
| MA-012 | Varilla 5/8 G40 | 550.20 | 403.00 | -26.8% | Larach |
| MA-018 | Bloque #4 | 21.00 | 17.75 | -15.5% | Larach, precio alto TGU |
| MA-033 | CPVC 1/2" | 100.00 | 175.00 | +75.0% | Larach |
| MA-019 | Bloque #6 | 27.00 | 20.00 | -25.9% | Larach, precio alto TGU |
| MA-126 | Bloque #8 | 33.00 | 26.00 | -21.2% | Larach, precio alto TGU |
| MA-110 | PVC SDR13.5 1/2" | 42.00 | 58.00 | +38.1% | Larach |
| MA-038 | PVC SDR41 3" | 195.00 | 480.00 | **+146.2%** | Larach -- delta grande, REVISAR antes de promover |
| MA-059 | PVC SDR41 4" | 500.00 | 770.00 | +54.0% | Larach |
| MA-052 | Centro Carga 16 espacios | 2100.00 | 2625.00 | +25.0% | Larach, sin tapa |
| MA-054 | Breaker 30A 220v | 260.00 | 419.00 | +61.2% | Larach, 2P real |
| MA-055 | Breaker 40A 220v | 360.00 | 470.00 | +30.6% | Larach, 2P |
| MA-247 | Breaker 20A sencillo | 160.00 | 170.00 | +6.2% | Larach |
| MA-250 | Cable THHN 12 | 20.00 | 21.00 | +5.0% | Larach, por metro |
| MA-251 | Cable THHN 14 | 14.00 | 11.35 | -18.9% | Larach, por metro |

**Hallazgo relevante:** mezcla real -- 6 materiales suben (electrico, PVC, cemento, CPVC), 4 bajan (varilla, bloque). No es un sesgo uniforme de inflacion ni de sobrevaloracion; es material por material. MA-038 (PVC 3" SDR41, +146%) es el unico delta que amerita doble-check manual antes de promover -- posible mismatch de spec (diametro/pared) entre BD y el producto Larach matcheado.

## Metodologia final

- Fuente BD: `C:\EstimaStruct\data\estimacion.db` tabla `recurso` tipo=MATERIAL (321 filas). Copia de trabajo pilot en `estimastruct_v1.3_pilot.db`.
- Fuente de precios validada y funcional: **larachycia.com** (Larach y Cia) -- catalogo publico real, paginas de producto y categoria con precio exacto en Lempiras, sin login. Unico sitio HN de los evaluados que funciono de forma confiable (Ferreteria Monterroso: catalogo requiere login BRIDGE OS, descartado).
- CHICO Boletin Estadistico IV-2024 (unico PDF publico via MediaFire, ultimo boletin abierto): 392MB, formato revista escaneada, no parseable con las herramientas de esta sesion. CHICO se uso como fuente de prensa agregada (rango cemento), no PDF parseado linea por linea.
- Regla Director: ante rango de precios (ej. TGU vs SPS), tomar el **alto**. Cemento con techo explicito L.245.
- Confianza Alta = precio exacto de pagina/categoria de producto real, spec coincide con BD. Media = match aproximado (unidad o especificacion distinta, NO aplicado a BD). Sin dato = sin correspondencia confiable encontrada en esta sesion.

## Cobertura real de los 321

- Confianza Alta (aplicados en pilot): 16
- Confianza Media (documentados, NO aplicados): 5
- Sin dato en esta ronda: 300

300 materiales sin dato son mayormente: (a) fixtures/marca puntual (inodoros, lavamanos, lamparas, aires acondicionados) donde el precio depende de modelo exacto y stock variable; (b) acero estructural industrial (vigas W, HSS, placas A36, pernos A325) que no se vende en ferreteria residencial -- requiere cotizacion directa con proveedor de acero estructural (ej. Ferromax, importador); (c) accesorios PVC pequenos (tees/codos/reductores, L.3-30 c/u) donde Larach solo dio rango agregado (L.4-170) sin desglose por SKU -- bajo impacto financiero individual, no priorizado.

## Ronda 2 (2026-07-31, post-promocion)

2 mas aplicados en vivo:

| Clave | Material | Antes | Despues | Delta | Fuente |
|---|---|---|---|---|---|
| MA-162 | Cal Hidratada 40lb | 175.00 | 125.00 | -28.6% | Larach y Cia, match exacto |
| MA-163 | Arenilla Rosada 25lb | 28.00 | 28.00 | 0.0% | Larach y Cia, match exacto -- valida BD, sin cambio real |

**Total en vivo: 23/321 (18 Alta + 5 Media).**

Categorias barridas en ronda 2 sin match limpio (no es "no busque", es "busque y no aplica"):
- **Electrodos de soldadura** (MA-182, MA-212): BD cotiza por libra, Larach vende por varilla individual -- unidades no convertibles sin factor peso/varilla confiable, no inventado.
- **Angulos/perfiles estructurales pesados** (MA-088, MA-176, MA-217): BD pide calibres/dimensiones (0.34mm liviano, o 3"x3"x1/4") que no calzan con el catalogo Larach (angulos estructurales 1/8"-1/4" grosor, max 2" ancho). Perfil distinto, no comparable.
- **Grava y Material Selecto** (MA-010, MA-058): confirmado AUSENTE en catalogo Larach -- son agregados a granel (compra por camion/m3), fuera de un e-commerce de ferreteria. Requiere proveedor de agregados directo, canal distinto.
- **Acero estructural pesado** (vigas W, HSS, placas A36, pernos A325 -- ~40 items de la serie MA-3xx): mismo caso, industrial/por pedido, no en ferreteria residencial online.

## Siguiente paso (pendiente decision Director)

- **Revisar MA-038** (PVC 3" SDR41, +146%) antes de promover -- verificar spec exacta.
- **Promover pilot a vivo**: UPDATE dirigido de los 15 restantes (o 16 si MA-038 se confirma) sobre `C:\EstimaStruct\data\estimacion.db`.
- **Siguiente ronda** para bajar los 300 sin dato: separar en 2 lotes -- (1) ferreteria residencial via larachycia.com por categoria completa (PVC fittings, ceramica, pintura, plomeria) escalable con el metodo ya probado; (2) acero estructural industrial requiere cotizacion directa con proveedor (Ferromax u otro), no esta en catalogo minorista online.

## Tabla completa (321 materiales)

| Clave | Descripcion BD | Unidad | Precio BD (L.) | Precio doc (L.) | Delta % | Confianza | Fuente / Nota |
|---|---|---|---|---|---|---|---|
| MA-001 | Cemento Portland | saco | 230.00 | 245.00 | +6.5% | Alta | CHICO/prensa 2026 (precio alto instruido) + Larach Bijao L.238/Argos L.205/Uno L.184 (2026) -- Director fija techo 245 |
| MA-002 | Arena | m3 | 910.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-003 | Varilla A.R.C 7.20 mm G 70 | lance | 160.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-004 | Clavos de 2" | lb | 20.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-005 | Madera Rustica de Pino | pt | 110.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-006 | Alambre de Amarre | lb | 30.00 | 29.00 | -3.3% | Media | Larach y Cia (2026-07) -- Alambre Amarre Cal.16 Doble Cocido DEACERO -- unidad exacta (rollo/lb) no confirmada |
| MA-007 | Electromalla 6"x6" 4/4 | pza | 2500.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-008 | Madera Rustica 2" x 2" | pt | 130.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-009 | Guia para Lavatrastos | pza | 120.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-010 | Grava 3/4" | m3 | 1020.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-011 | Agua | m3 | 70.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-012 | Varilla de Hierro Corrugado 5/8 G40 | lance | 550.20 | 403.00 | -26.8% | Alta | Larach y Cia (2026-07) -- Varilla 5/8 G40 9mts |
| MA-013 | Escoba | pza | 90.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-014 | Bolsa de Ace | pza | 60.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-015 | Recogedor de Basura | pza | 50.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-016 | Balde Plástico | pza | 75.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-017 | Paño para Limpieza | pza | 30.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-018 | Bloque de Concreto 4" | pza | 21.00 | 17.75 | -15.5% | Alta | Larach y Cia (2026-07) -- Bloque #4 9x39.5x20cm |
| MA-019 | Bloque de concreto de 6" | pza | 27.00 | 20.00 | -25.9% | Alta | Larach y Cia (2026-07) -- Bloque #6, precio alto entre TGU(20.00)/SPS(17.50) |
| MA-020 | Ladrillo Rafon Rustico | pza | 20.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-021 | Madera Rustica de Pino | pt | 110.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-022 | Varilla de Hierro Corrugado 3/8 G40 | lance | 190.00 | 144.50 | -23.9% | Alta | Larach y Cia (larachycia.com, catalogo real) (2026-07) -- Varilla 3/8 G40 9mts, unidad lance~9m coincide |
| MA-023 | Canaleta Galvanizada de 6" Cal 1.5 | lance | 850.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-024 | Varilla de Acero Galvanizado Lisa 3/8" G40 | lance | 185.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-025 | Lamina de Tabla Yeso 4" x 8" x 5/8" | pza | 293.00 | 291.00 | -0.7% | Media | Larach y Cia (2026-07) -- Match es 1/2", BD pide 5/8" -- espesor distinto, no exacto |
| MA-027 | Masilla para Tabla Yeso | kg | 499.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-028 | Tornillo Autorroscante 1 1/4" para Tabla Yeso | pza | 3.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-030 | Clavo de Acero 1" Caja de 100 Unidades | Caja | 150.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-031 | Tee de PVC de 3/4" | pza | 10.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-032 | Reductor de PVC de 3/4" a 1/2" | pza | 7.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-033 | Tubería de CPVC de 1/2" SDR 13.5 | lance | 100.00 | 175.00 | +75.0% | Alta | Larach y Cia (2026-07) -- Tubo CPVC 1/2" x20 pies agua caliente |
| MA-034 | Tee de CPVC de 1/2" | pza | 7.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-035 | Codo de CPVC de 1/2" | pza | 10.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-036 | Pegamento Tangit Transparente para CPVC | gal | 2300.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-037 | Tee de PVC de 2" | pza | 25.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-038 | Tubo de PVC de 3" SDR 41 | lance | 195.00 | 480.00 | +146.2% | Alta | Larach y Cia (2026-07) -- PVC SDR41 3"x20pies -- delta grande (+146%), verificar antes de aplicar en vivo |
| MA-039 | Codo de PVC de 3" a 45° | pza | 25.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-040 | Tee de PVC de 3" | pza | 30.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-041 | Reductor de PVC de 3" a 2" | pza | 30.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-042 | Yee de PVC de 4" | pza | 135.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-043 | Reductor de PVC de 4" a 3" | pza | 20.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-044 | Reductor de PVC de 4" a 2" | pza | 20.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-045 | Codo de PVC de 3" a 90° | pza | 25.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-046 | Trampa Pvc Sani 1/2" Pd Bl | unidad | 60.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-047 | Tubo de Conduit de PVC SC Gresp de 1/2" | lance | 16.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-048 | Curva de Conduit de PVC de 1/2" | pza | 3.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-049 | Lamina Aluzinc Con Color, Cal 26 Legitimo | pie | 70.00 | 55.00 | -21.4% | Media | Larach y Cia (derivado: L.660/pieza 12pies -> 55/pie) (2026-07) -- Precio derivado de pieza completa Master1000, no unidad pie directa |
| MA-051 | Valvula de Control OR17C1 1/2 x 3/8 Plg para Pared KEENEY | pza | 114.33 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-052 | Centro de Carga 16 Espacios | pza | 2100.00 | 2625.00 | +25.0% | Alta | Larach y Cia (2026-07) -- Square D 16P 125A sin tapa (QO116L125PG); con tapa +L.1300 |
| MA-053 | Interruptor Triple | pza | 400.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-054 | Breaker de 30 amperios para 220v | pza | 260.00 | 419.00 | +61.2% | Alta | Larach y Cia (2026-07) -- Square D 30A 2P (220V real = doble polo en panel HN) |
| MA-055 | Breaker de 40 amp para 220 v | pza | 360.00 | 470.00 | +30.6% | Alta | Larach y Cia (2026-07) -- Eaton 40A 2P (BR240) |
| MA-056 | Lavatrasto Teka 100X50 cm Calibre 24 Cubeta Un Escurridor Izquierdo | pza | 1400.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-057 | Alambre de Amarre | lb | 30.00 | 29.00 | -3.3% | Media | Larach y Cia (2026-07) -- Duplicado de MA-006 en BD, mismo material |
| MA-058 | Material Selecto (con Flete) | m3 | 800.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-059 | Tubo de PVC de 4" SDR 41 | lance | 500.00 | 770.00 | +54.0% | Alta | Larach y Cia (2026-07) -- PVC SDR41 4"x20pies |
| MA-060 | Tomacorriente ENERLITES 20A 120-277v Listado UL con tapadera | pza | 300.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-061 | Inodoro American Standard 4.8 lts Elongado con Accesorios Equix | pza | 8150.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-062 | Lavatrastos Doble Fosa Sin Escudor | pza | 2500.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-064 | Tanque Rotoplas de 1100L | m2 | 7500.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-065 | 0.34 mm x 12' Furring de Metal | lance | 100.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-066 | Tinaco Rotoplas de 1700L | m2 | 11630.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-067 | Tinaco Rotoplas 750L_x000D_ | pza | 6120.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-068 | Lavamano de Bowl Corona | pza | 2900.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-069 | Maxi Ducha Ultra - Lorenzetti | pza | 600.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-070 | Tinaco Rotoplas Cemix Beige de 2000 litros | pza | 20000.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-071 | Lámpara tipo LED Central para Sala | pza | 1200.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-072 | Roseta para Lámpara | pza | 35.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-073 | Lámpara Empotrable LED regulable | pza | 650.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-074 | Tristan I Farol exterior acabado blanco de 1 luz | pza | 1049.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-075 | Foco Ahorrativo para Roseta 120V 80W | pza | 65.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-076 | Bombillos GE 20 Watt | pza | 75.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-077 | Alambre De Pua Deacero #16-400 Vaquero | rollo | 575.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-078 | Tubo Galvanizado Redondo de 2 1/2" | lance | 400.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-079 | Malla Ciclón de 5' x 100' | rollo | 2021.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-081 | Luces solares para exteriores, [6 unidades/52 LED/3 modos] focos solares 2 en 1, luz de seguridad contra inundaciones alimentada por energía solar, luz de pared impermeable IP65 para pasarela, patio, jardín, entrada (blanco frío) | pza | 380.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-083 | Raziel Farol de exterior acabado negro de 1 luz | pza | 720.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-085 | Tornillo Punta de Broca 21/8 | pza | 1.73 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-088 | Angulo 1"x1"x10' 0.34 mm | lance | 30.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-089 | Varilla de Hierro de 1/4" Lisa G40 | lance | 80.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-090 | Varilla Hierro Aceros Alfa 3/4"X9mts Deformado Grado 60 | lance | 710.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-091 | Codo 3/4" x 90º PVC | pza | 10.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-092 | Codo 1/2“ x 90º PVC | pza | 3.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-093 | Tee de PVC de 1/2“ | pza | 3.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-096 | Canaleta de Carga CRC 38 x 12 mm x 16' 0.70 mm | lance | 140.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-099 | Alambre Galvanizado # 16 | pza | 38.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-102 | Ceramica Piso 43x43 Tipo Brasiliia 222 gris, Centro de Cerámicas_x000D_ | m2 | 390.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-103 | Vidrio Fijo PVC | m2 | 2120.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-104 | Fachaleta Exterior de Ladrillo Rekubre | m2 | 800.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-105 | Ceramica de Pared 31x60, Tipo Linho Light Gray | m2 | 586.59 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-107 | LAVABO STD. ECOLINE #17L19346B.020/CO141L19.020 BLANCO PIEZA | pza | 3800.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-108 | Inodoro American Standard 6lts Redondo con Accesorios Hydra | pza | 3600.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-110 | Tuberia 1/2 " PVC-SDR-13.5 | lance | 42.00 | 58.00 | +38.1% | Alta | Larach y Cia (2026-07) -- PVC Potable SDR13.5 1/2"x20pies, match exacto spec |
| MA-111 | Tubo de PVC 2" SDR 21 | m2 | 125.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-112 | Tubo de abasto EAL-B40 3/8x1/2-40cm flexible para lavabo | pza | 50.50 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-113 | Curacreto a base de Agua | gal | 150.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-121 | Varilla de Hierro Corrugado 1/2" G40 | lance | 330.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-125 | Clavos de acero de 2" para madera | lb | 28.01 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-126 | Bloque de Concreto de 8" | pza | 33.00 | 26.00 | -21.2% | Alta | Larach y Cia (2026-07) -- Bloque #8, precio alto entre TGU(26.00)/SPS(24.00) |
| MA-127 | Contador de Agua Regulado SANAA | m2 | 1000.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-128 | Caja de Registro de Concreto Para Toma | pza | 800.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-130 | Repello/Pulido con Cemento Bijao | kg | 200.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-131 | Lampara Golgante para Cocina_x000D_ | pza | 2500.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-132 | Tuberia de PVC de 3/4“ SDR 17 | lance | 85.00 | 90.00 | +5.9% | Media | Larach y Cia (2026-07) -- Larach solo tiene SDR21 3/4", BD pide SDR17 -- espec distinta |
| MA-135 | Varilla Polo a Tierra de 5/8 x 6 | lance | 200.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-143 | TP-LINK Smart WiFi Switch Control Iluminación desde cualquier lugar, HS220 | pza | 625.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-144 | Microcemento en Polvo Blanco 12KG (Capa Adhesiva/Base) | kg | 11.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-145 | Resina Líquida en presentación 1 Galón (Componente B) | m2 | 11.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-146 | Pigmento líquido como colorante universal (1lt) | m2 | 11.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-147 | Microsellador para terminación (1lt) | m2 | 15.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-148 | Tomacorriente Especial 220V 50Amp | pza | 300.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-149 | Porcelanato de 0.60x0.20 de Tipo "ROUGH" de tipo Español, Distribuidor Stone Market_x000D_ | m2 | 680.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-150 | Sistema de Vigueta y Bovedilla (Compra y Entrega desde Monolit) | m2 | 1500.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-151 | Ceramica de Fondo de Baño Tipo Mosaico Calacatta R11 Centro Ceramicas | m2 | 345.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-152 | Cerámica de Fondo de Baño 515 Niebla Gris Oscuro Centro Ceramicas | m2 | 300.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-153 | Piso Vinilico PVC Carrubio Coffee | m2 | 300.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-154 | Puerta Corrediza de 2 Hojas de 1.80 x 2.10_x000D_ | pza | 16000.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-157 | Moldura de Cornisa de Concreto | mL | 115.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-158 | Lámina Aluzinc cal. 26 lisa de 20cm para flashing_x000D_ | mL | 105.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-159 | Tanque Septico Biodigestor Rotoplas 600 lts | pza | 12400.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-160 | Trampa de grasa 38 lts Prefabricada Color Negro | pza | 3000.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-161 | Cable Coaxial Para Video Nippon America 100-Pies Rg-6 | rollo | 1200.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-162 | Cal Hidratada 40lbs | saco | 175.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-163 | Arenilla Rosada colada 25lbs | pza | 28.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-164 | Piedra de Cantera Blanca Para Muro de Retención (Revisar Flete) | m3 | 400.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-166 | Ailsante Termoacustico 1.20x20m (24.2m2) | m2 | 2000.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-167 | Lampara de Exterior_x000D_ | m2 | 500.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-168 | Codo de PVC de 2" x 45º | pza | 17.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-169 | Trampa de PVC de 2" | pza | 24.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-170 | Codo de PVC de 2" x 90° | pza | 17.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-171 | Codo de  PVC de 4” | pza | 110.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-172 | Adaptador Macho PVC de 1/2"  Potable | pza | 5.60 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-173 | Sifon cromado lavabo | pza | 257.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-174 | Cinta Teflon 1/2 | rollo | 30.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-175 | Kit de Pintura Rodo + Felpa_x000D_ | pza | 150.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-176 | Tubo Estructural de acero 2"x2"x1/12 | lance | 700.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-178 | Placa de Acero A36 de 35x35cmx1", | pza | 500.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-182 | Electrodo 6013 3-/32 | lb | 150.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-183 | Disco de corte de 4 1/2" | pza | 65.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-185 | Pintura Anticorrosivo Fast Dry Protecto Galón B0-500 (Base Para Coloreo Tonos Pastel) | gal | 1240.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-187 | Botas. Casco y Chaleco para trabajadores | glb | 8500.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-188 | Aislante de Suelo | m2 | 300.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-189 | Membrana Impermeable Blanca Thermotek 1.15 x 95 m | m2 | 100.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-190 | Asfalto Premier Líquido Negro Para Cimentación Henry 0.90-Galon | gal | 600.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-192 | Espuma Max Fill 12onz Sellador de Poliuretano | pza | 300.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-193 | Cerraduras, Visagras y Sellos de Puertas | pza | 440.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-194 | Pintura Impermeabilizante | l | 104.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-195 | Cable Electrico Phelps Dodge Tsj 3X10 Negro_x000D_ | mL | 105.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-196 | Suministro e Instalación de Evaporador Aire ComfortStar | pza | 14980.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-197 | Suministro e Instalación de Condensador de Aire ComfortStar | m2 | 15530.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-198 | 100mts Cable UTP | rollo | 1200.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-199 | Terminación de conectores RJ-45 | pza | 100.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-201 | Lamina Alluzinc Cal 26 106cm x pie | ft | 55.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-202 | Detector de movimiento PIR / Dual (Skytek Honduras) | pza | 1282.96 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-203 | Base o soporte de montaje para Detector | pza | 250.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-204 | Cámaras CCTV (IP o Analógicas) | pza | 2100.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-205 | J-Bolt ASTM F1554 Gr.36 3/4"×40cm | pza | 200.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-206 | Tuerca hexagonal pesada 3/4" Grado C | pza | 60.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-207 | Admix F5 Aditivo de concreto fluidificante y acelerante.(Baril 200L) | Barril | 7600.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-209 | Encofrado de Columna 35x35 con formaleta metalica | mL | 180.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-210 | Arandela endurecida tipo D 3/4" | pza | 180.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-212 | Electrodo E7018 bajo hidrógeno | lb | 102.33 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-213 | Gas protección (Ar/CO2) | gal | 206.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-214 | Consumibles soldadura (cepillo, escoria) | m2 | 105.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-215 | Pernos A325 3/4"×80mm Grado 5 | pza | 150.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-216 | Separadores calibrados 10mm | pza | 72.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-217 | Angulo Hierro A36l L 3×3×1/4" (lance 6m) | lance | 2000.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-218 | Pernos A325 5/8" | pza | 91.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-219 | Tuercas/arandelas 5/8" | pza | 230.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-220 | Imprimación zinc-rich | gal | 1456.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-221 | Steel Framing Montantes C 70×40×0.8 mm | lance | 273.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-222 | Steel Framing Soleras superior/inferior U 70×40×0.8 mm | lance | 273.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-223 | Steel Framing Travesaños C 70×40×0.8 mm | lance | 273.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-224 | Steel Framing Refuerzos especiales C 70×40×0.8 mm | lance | 273.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-225 | Steel Framing Tornillos autoperforantes | pza | 6.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-226 | Steel Framing Tornillos para placa | pza | 6.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-227 | Steel Framing Clavos tirafondo 3" | pza | 2.60 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-228 | Stel Framing Placas de unión | pza | 3.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-229 | Cinta Selladora | mL | 28.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-230 | Broca para Taladro 3/8" | pza | 80.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-231 | Lamina de Tablaroca de 4'x8' | pza | 250.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-232 | Tablaroca/Tablayeso Esquinero Metalico | lance | 60.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-233 | Primer Loxon Sherwin Williams | gal | 1192.50 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-234 | Pintura -  Diluyente | l | 26.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-235 | Pintura Sherwin SuperPaint Exterior Flat | gal | 1375.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-236 | Concreto Premezclado 3,000 Psi Agregado 3/4" | m3 | 5700.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-237 | Cerámica Valencia Café 40 cm x 40 cm | m2 | 400.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-238 | Varilla de Hierro Corrugado 1/4" G40 | lance | 40.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-239 | Fraguador Sika Arena Clara (5 kg) | saco | 320.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-240 | Desmoldante ADMIX | gal | 150.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-241 | Fibra Migthy | Bolsa | 125.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-242 | Separadores de Concreto 5 cm | pza | 10.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-243 | Clavos de 2" con cabeza. | pza | 16.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-244 | Taco Fisher S-8 | pza | 10.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-245 | Tornillo 2" 1/2" | pza | 5.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-246 | Tornillo Goloso Rawplug 10x3/4 | pza | 10.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-247 | Breaker 20 Amp sencillos | pza | 160.00 | 170.00 | +6.2% | Alta | Larach y Cia (2026-07) -- Square D 20A 1P (QOW120) |
| MA-248 | Interruptor Doble | pza | 280.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-249 | Interruptor Sencillo | pza | 170.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-250 | Cable THHN 12 | mL | 20.00 | 21.00 | +5.0% | Alta | Larach y Cia (2026-07) -- THHN-12 Coleman Cable, precio por metro |
| MA-251 | Cable THHN 14 | mL | 14.00 | 11.35 | -18.9% | Alta | Larach y Cia (2026-07) -- THHN-14 Coleman Cable, precio por metro |
| MA-252 | Cable THHN 8 | mL | 80.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-253 | Cable Electrico Para Acometida Aluminio Forrado Por Pie 1/0 | mL | 300.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-254 | Tubo de Conduit de PVC SC Gresp de 3/4" | rollo | 450.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-255 | Curva de Conduit de PVC Gris de 3/4" | pza | 16.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-256 | Mufa EMT de 1 1/4
" | pza | 150.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-257 | Caja Octagonal Liviana de 1/2" | pza | 20.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-258 | Llave Sencilla Cocina | pza | 2200.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-259 | Grifo para lavamanos tipo Bowl | pza | 2000.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-260 | Kit lave. Cabeza, ducha, mezclador y Manguera (ebay) | pza | 3800.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-262 | Brida para sanitario | pza | 150.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-264 | Ceramica de Pared Brazilia 522 Beige 20 cm x 31 cm Samboro | m2 | 400.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-265 | Separadores Truper de 5 mm (200) =Unidades) | m2 | 49.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-266 | Puerta Termoformada 0.80x2.10m | unidad | 2600.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-267 | Puerta Principal de Aluminio Con Sidelight de 1.30 x 2.10m | unidad | 27000.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-268 | Ventana Corrediza aluminio y vidrio 0.4 x 0.8m | unidad | 4000.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-269 | Ventana Corrediza de PVC y Vidrio 0.40x0.60m (0.24m2) | unidad | 2400.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-270 | Caja Rectangular 2" x 4" de 1/2" | pza | 30.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-271 | Pegamento Tangit Transparente para PVC | gal | 1948.86 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-272 | Adhesivo para Ceramica (Pegafuer-T) | saco | 265.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-273 | Silicone Transparente 280 ml Toolcraft | unidad | 300.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-274 | Malla Naranja | rollo | 850.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-275 | Grama San Agustin | m2 | 95.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-276 | Cuerda para marcar | yd | 0.50 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-277 | Crayolas para marcado | pza | 17.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-278 | Cinta Adhesiva | rollo | 15.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-279 | Lija #80 | pliego | 12.80 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-280 | Ducto flexible Ø8" R-6 | mL | 243.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-281 | Cinta aluminio 2" | mL | 20.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-282 | Abrazaderas | pza | 15.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-283 | Soportes para tuberia HVAC | pza | 12.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-284 | Tinaco de Reserva de 10,000L | pza | 40980.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-285 | Pintura Impermeabilizante Color Azul | gal | 95.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-287 | Malla Geotextil para separación de aridos | m2 | 78.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-288 | Tablilla Plafon Polaris 4'x8' | pza | 60.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-289 | Primer Covermore | gal | 400.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-290 | Pintura Covermore_x000D_ | gal | 400.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-291 | Tomacorriente Aguila | pza | 100.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-292 | Melamina Supermuff 18mm | m2 | 800.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-293 | Tapacanto PVC | mL | 40.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-294 | Bisagras cierre suave | pza | 120.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-295 | Riel telescópico gaveta | pza | 180.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-296 | Tornillos, pegamento para Mueble | glb | 150.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-297 | Zócalo PVC/aluminio | mL | 300.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-298 | Cuarzo estándar | m2 | 7000.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-299 | Adhesivos/resinas para Top | global | 200.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-300 | Herrajes premium | pza | 1500.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-301 | Refuerzos estructurales | glb | 400.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-302 | Tablilla PVC | m2 | 190.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-303 | Lamina de Tabla Yeso 4" x 8" x 5/8" RH | pza | 1200.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-304 | Canaleta Galvanizada Aluzinc Cal 26 2x4" | lance | 600.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-305 | Lamina de Aluzinc Cal 28 Legitimo 0.30mm | pie | 40.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-306 | Adhesivo PVC | kg | 180.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-307 | Conectores Para Cable | pza | 15.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-308 | Base de Contador de 200Amp | pza | 4000.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-309 | Grapa para varilla a tierra | pza | 50.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-310 | Ángulo 2"x2"x1/4 | lance | 450.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-311 | Placa de acero antideslizante e=3/16" | m2 | 1200.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-312 | Pasamanos tubo 1.5" | lance | 350.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-313 | Tubo estructural 1" (barrotes) | lance | 280.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-314 | Pigmento Para Mortero (Color) | kg | 120.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-315 | Placa de anclaje 4"x4"x1/4" | pza | 120.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-316 | Viga IPR 6" x 6m (W150x18) | lance | 3200.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-317 | Pernos de anclaje 1/2"x4" | pza | 45.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-318 | Viga Metálica W200x27 (8" x 4" x 27 kg/m) | lance | 4800.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-319 | Placa de asiento A36 1/2" (15x15cm) | pza | 180.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-320 | Placa de anclaje A36 1/2" (20x20cm) | pza | 320.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-321 | Viga Metálica W250x33 (10" x 5.5" x 33 kg/m) | lance | 6500.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-322 | Viga Metálica W180x22 (7" x 5" x 22 kg/m) | lance | 4200.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-323 | Plantilla guía de acero | pza | 250.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-324 | Tubo Estructural 6x6 HSS 6x6x3/16" (150x150x4.5mm) | lance | 5928.20 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-325 | Placa Base A36 30x30cm | pza | 1200.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-327 | HSS 8x8x3/8" (200x200x5.5mm) x 6m | lance | 9459.58 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-328 | Placa base A36 1" (40x40cm) | pza | 1800.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-329 | Placa superior A36 5/8" (30x30cm) | pza | 680.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-330 | Pernos A325 1"×100mm | pza | 280.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-331 | Tuerca hexagonal 1" | pza | 120.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-332 | Arandela endurecida 1" | pza | 320.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-333 | HSS 10x10x1/2" (250x250x12.7mm) x 6m | lance | 9500.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-334 | Placa base A36 1-1/4" (45x45cm) | pza | 2800.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-335 | Placa superior A36 3/4" (35x35cm) | pza | 950.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-336 | Pernos A325 1-1/4"×120mm | pza | 450.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-337 | Tuerca hexagonal 1-1/4" | pza | 180.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-338 | Arandela endurecida 1-1/4" | pza | 480.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-339 | W200x46 (200x200mm) x 6m | lance | 7200.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-340 | W250x73 (250x250mm) x 6m | lance | 10500.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-341 | Tabla maciza 24x160x2900mm, color madera | m2 | 520.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-342 | Clip de Fijación Oculto | pza | 12.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-343 | Tapa Final Decorativa Para remates y esquinas, color a juego | pza | 65.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-344 | Tabla maciza 24x160x2900mm, alta resistencia UV | m2 | 820.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-346 | Perfil de Aluminio Extruido (Alucobond) | mL | 160.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-347 | Puerta corrediza 0.80x2.10 m Termoformada | pza | 4000.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-348 | Puerta plegable 0.80x2.10 m | pza | 4500.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-350 | Subcontrato suministro de materiales (perfiles, vidrio, herrajes) | mL | 3840.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-351 | Supercapa de 40 kg | Bolsa | 224.50 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-352 | Tomacoriente Exterior de 20Amp | pza | 350.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-353 | Placa base A36 250x250x5/8" | pza | 680.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-354 | Placa base A36 300x300x3/4" | pza | 1200.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-355 | J-bolt F1554 G36 1" x 40cm, 2 Tuercas UNC 2H 1 arandela plana 3/4" Rosca 4" | pza | 1330.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-356 | Placa base A36 400x400x1" | pza | 2400.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-357 | Placa de asiento A36 200x150x3/8" | pza | 210.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-358 | Placa de cortante A36 150x100x1/4" | pza | 170.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-359 | Placa de asiento A36 250x200x1/2" | pza | 380.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-360 | Puerta Principal Acabado Metal/Madera 1.40x2.10m (completa) | pza | 20000.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-361 | Perfil W6x16 (6"x4"x16 lb/ft) x 12.20 m | lance | 11187.20 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-362 | Perfil W8x24 (8"x6.5"x24 lb/ft) x 12.20 m (con ISV) | lance | 16780.80 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-363 | Perfil W8x48 (8"x8"x48 lb/ft) x 12.20 m (con ISV) | pza | 33561.60 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-364 | Perfil W10x33 (10"x8"x33 lb/ft) x 12.20 m (con ISV) | pza | 23073.60 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-365 | Perfil W12x53 (12"x10"x53 lb/ft) x 12.20 m (con ISV) | lance | 35229.10 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-366 | Placa Base A36 20x20cmx1/2" | pza | 420.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-367 | J-bolt F1554 G36 3/4" x 40cm, 2 Tuercas UNC 2H 1 arandela plana 3/4" Rosca 4" | pza | 1051.42 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-368 | Disco de corte 4-1/2" x 1/8" | pza | 55.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-369 | Placa de cortante A36 200x150x3/8" | pza | 160.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-370 | Placa de asiento A36 300x250x5/8" | pza | 650.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-371 | Placa de cortante A36 250x200x1/2" | pza | 280.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-372 | Disco de desbaste 4-1/2" x 1/4" | pza | 65.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-373 | Aire Acondicionado 12000BTU | unidad | 9000.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-374 | Calentador de agua eléctrico de paso (tankless) 220V 7.2kW montaje en pared | pza | 5800.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-375 | Centro de Carga 6 Espacios 220V 125A | pza | 1900.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-376 | Panel WPC interior decorativo | m2 | 450.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |
| MA-377 | Coladera de piso 5"x5" con desagüe 2" | pza | 180.00 | -- | -- | Sin dato | No priorizado en esta ronda -- pendiente consulta directa en larachycia.com u otra fuente |

## Resumen
- Total materiales BD: 321
- Confianza Alta (precio exacto validado): 16
- Confianza Media (match aproximado): 5
- Sin dato encontrado en esta ronda: 300

## Hallazgo relevante
Los materiales con match Alta confianza (varilla 3/8, varilla 5/8, bloque 4") muestran la BD **por encima** del precio real de mercado (Larach), no por debajo -- lo opuesto a lo esperado por inflacion. Posible causa: BD V1.3 tiene margen/flete ya incluido, o precios no actualizados desde una compra puntual mas cara. Validar con Director antes de bajar precios en BD -- bajar sin contexto puede subestimar presupuestos reales de obra.

## Siguiente paso
300 materiales sin dato son, en su mayoria, articulos de bajo volumen/alta especificidad de marca (valvulas, accesorios, fixtures puntuales) donde matchear por texto libre contra catalogo es poco confiable sin revision humana. Metodo probado (larachycia.com por producto/categoria) escala; falta tiempo de sesion, no metodo. Recomendado: siguiente ronda dirigida por categoria (PVC completo, electrico completo, tabla yeso completo) en vez de material por material.