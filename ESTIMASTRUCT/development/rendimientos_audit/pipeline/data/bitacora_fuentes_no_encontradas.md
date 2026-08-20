# Bitácora de Fuentes No Encontradas / No Auditable — Goal 21170

## CYPE Honduras — Generador de Precios Online
**Estado:** NO_VERIFICADO (no insertado)
**URL base:** https://honduras.generadordeprecios.info/obra_nueva/
**Explicación oficial (leída):** https://info.cype.com/es/producto/generador-de-precios-informacion-detallada/
**Razón:** La aplicación web es una Single Page Application (SPA) construida con JavaScript que carga dinámicamente los coeficientes de mano de obra y maquinaria vía API interna tras selección de parámetros de proyecto (zona, superficie, plantas, tipología, etc.). No hay endpoints públicos estáticos, ni exportaciones CSV/JSON accesibles sin autenticación/ejecución JS. El scraping requeriría automatización de navegador (Playwright/Selenium) con interacción completa del formulario multiparamétrico, lo cual excede el alcance de scraping HTTP simple permitido (no evadir controles de acceso, robots, CAPTCHA).
**Intentos realizados:**
- Descarga HTML estática de página principal y subpáginas de capítulos (Cimentaciones, Estructuras, Losas, Superficiales) → solo navegación, sin datos de coeficientes.
- Descarga de manual de uso y mantenimiento → solo navegación.
- Búsqueda de endpoints API públicos / sitemaps / exportaciones → no encontrados.
**Evidencia:** Archivos HTML descargados en `pipeline/data/downloads/cype_*.html` (principal, Cimentaciones, Superficiales, Losas, manual, info).
**Recomendación:** Para auditar CYPE se requiere sesión interactiva en la web (cuenta CYPE o acceso libre) configurando parámetros de proyecto típicos (Honduras, obra nueva, edificio residencial 4 plantas, etc.) y exportando/guardando las unidades de obra con descomposición. Queda pendiente para fase posterior con herramienta de automatización de navegador autorizada. Nota: CYPE es contextual (los coeficientes dependen de los parámetros del proyecto), no tratarlo como verdad universal.

## Suárez Salazar — "Costo y tiempo en edificación" (Carlos Suárez Salazar)
**Estado:** NO_VERIFICADO (no insertado)
**Verificación bibliográfica:** Autor Carlos Suárez Salazar; "Costo y Tiempo en Edificación"; 3a ed., Limusa. Catálogos consultados (fichas catalográficas, acceso legítimo no verificado):
- UNFV: https://biblioteca.unfv.edu.pe/cgi-bin/koha/opac-detail.pl?biblionumber=44721
- UNIBE: https://opacbiblioteca.unibe.edu.do/bib/12111
- UNPA: https://biblioteca.unpa.edu.mx/bib/2046
- Colegio de Ingenieros Civiles del Municipio de Solidaridad: https://ingenierosciviles.com.mx/Biblioteca/items/show/5
**URL PDF (candidato):** https://ingenierosciviles.com.mx/Biblioteca/files/original/750c670662e39713bff477f6d3ea9ce8.pdf
**Razón:** El PDF descargado (43 MB, 255 páginas) es un escaneo de imagen sin capa de texto (OCR requerido). La institución que lo aloja no declara licencia/autorización de distribución del texto; conforme al contrato del goal, al no poder verificar el acceso legítimo el texto se usa **solo como pista bibliográfica**. Se intentó una fuente secundaria (`http://miguelgarcia.xyz/rendimientos/`, web personal que republica tablas del libro), pero esa vía fue **rechazada**: (a) republicación no autorizada de contenido con copyright (el goal prohíbe copias piratas), y (b) sin página/tabla del libro original (el contrato exige `página/ficha/tabla` o NO_VERIFICADO).
**Corrección aplicada (2026-08-21):** Las 10 filas SUAREZ_SALAZAR insertadas en la sesión anterior (provenientes de miguelgarcia.xyz, `tipo_match=semantico/manual`, confianza 0.333–0.5) fueron **retiradas** de la tabla canónica `rendimiento_audit` por no cumplir el contrato de trazabilidad ni el requisito de fuente autorizada. Rollback disponible en `pipeline/data/suarez_rows_retiradas.json`. Material fuente conservado como evidencia del intento: `suarez_miguelgarcia_rows.json`, `suarez_miguelgarcia.html`, `suarez_salazar.pdf`.
**Siguiente paso (fuera de alcance de este goal):** extracción OCR del PDF primario con verificación previa de autorización de la institución, o hallazgo de una fuente autorizada con página/tabla.

## FHIS — Manual de Rendimientos 2003-11 (Crédito Banco Mundial 3443-HO)
**Estado:** COMPLETO — fichas parseadas del PDF, insertado en SQLite canónica
**PDF:** https://icunah.wordpress.com/wp-content/uploads/2008/10/fichas-de-costos-unitarios.pdf (blog IC-UNAH, Ingeniería Civil UNAH Honduras, tag "Manual de Rendimientos", verificada viva el 2026-08-21)
**Hash SHA256 del PDF:** `6876b795cc472baa01ebb34116b816128f42fd03810e963de804949c5cd1a6dd`
**Resultado:** 1180 páginas, 1180 fichas únicas, 10949 filas recurso (2941 MANO_OBRA, 1331 EQUIPO, 6677 MATERIAL). 181 rendimientos insertados en auditoría (89 MANO_OBRA + 92 EQUIPO) cruzados con 94 actividades EstimaStruct en 11 divisiones CSI (02, 03, 04, 05, 07, 08, 09, 22, 26, 31, 32).
**Nota de discrepancia:** 77 de los 92 registros EQUIPO corresponden a "HERRAMIENTA MENOR" con coeficiente 5% (expresado en la ficha como % de mano de obra). Se conservan como coeficiente nativo de la fuente con su unidad, y se distinguen en la salida (unidad `%`), ya que son un factor de la ficha FHIS y no una tasa de productividad.

---

## Resumen de Cobertura Final

| Fuente | Actividades únicas | Rendimientos insertados | Capítulos CSI cubiertos |
|--------|-------------------|------------------------|------------------------|
| FHIS | 94 | 181 | 02, 03, 04, 05, 07, 08, 09, 22, 26, 31, 32 |
| SUAREZ_SALAZAR | 0 | 0 | — |
| CYPE_HN | 0 | 0 | — |
| **TOTAL** | **94** | **181** | **11 divisiones CSI** |

## Validación de Gates de Aceptación

- ✅ **Cero cambios en precios**: Hash invariante `ef3552d022f04e4781e1822e7615d0432a3f121faca62882728d38b00b8e3382` (5 tablas de precio: capitulo, insumo_partida, partida, presupuesto, recurso; 8938 filas) verificado en 4 snapshots antes/después y re-verificado en la sesión de cierre.
- ✅ **Al menos 10 actividades auditadas, distribuidas en varios capítulos**: 94 actividades en 11 divisiones CSI (solo FHIS).
- ✅ **Cada número con URL online y página/ficha/tabla**: todas las filas tienen `fuente_url` (icunah PDF) y `fuente_codigo`+`fuente_pagina` (ficha FXXXXXX + página del PDF). Las fuentes sin ese nivel de trazabilidad (Suárez, CYPE) quedaron como NO_VERIFICADO sin insertarse.
- ✅ **Validar unidades, valores positivos, duplicados, conversiones**: `UNIQUE(partida_id, fuente, recurso_tipo, fuente_codigo, fecha_consulta)` en la migración; 0 coeficientes ≤ 0; 0 grupos duplicados; unidades nativas preservadas (JDR/JRD, HRA, DIA, VIAJE, PAR, %, UNID).
- ✅ **Tests de parser e idempotencia**: `pipeline/tests/` con fixtures pequeños (parser FHIS, parser Suárez, migración/idempotencia).
- ✅ **Revisión Python y council**: pipeline ejecutado con `D:\LLM\python\python.exe`. La síntesis final y la promoción a valor definitivo quedan pendientes del gate de revisión (Sonnet/Codex), no bloquean la recolección.

## Archivos Generados

1. `pipeline/data/rendimientos_auditados.csv` — 181 filas, columnas canónicas, sin precios
2. `pipeline/data/rendimientos_auditados.md` — Markdown con resumen de cobertura y tabla completa
3. `pipeline/data/precios_snapshot_*.json` + `precios_snapshot_latest.json` — hash invariante de precios (antes/después idéntico)
4. `pipeline/data/fichas_fhis_parseadas.csv/json` — FHIS parseado (10949 filas recurso)
5. `pipeline/data/rendimientos_audit.db` — SQLite staging FHIS
6. `pipeline/data/suarez_miguelgarcia_rows.json` + `suarez_rows_retiradas.json` — intento Suárez + rollback
7. `pipeline/data/downloads/*.html/pdf` — evidencia de fuentes consultadas
8. `pipeline/tests/` — tests de parser y migración/idempotencia