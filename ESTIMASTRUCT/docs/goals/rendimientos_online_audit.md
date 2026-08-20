# P0 — Auditoría online de rendimientos FHIS, Suárez Salazar y CYPE

## Decisión del Director (2026-08-20)

EstimaStruct debe auditar **rendimientos solamente**. Los precios existentes son
inmutables durante este goal. Esta orden constituye el segundo OK para poblar
rendimientos comparativos en la base SQLite canónica, pero no autoriza cambiar
precios, recalcular presupuestos ni promover automáticamente un rendimiento como
valor definitivo.

## Resultado exigido

Construir un pipeline reproducible que busque, descargue o raspe fuentes
verificables en línea, cruce sus actividades con el catálogo EstimaStruct y
registre cada rendimiento con trazabilidad bibliográfica. El último artefacto del
loop debe ser una lista de **todos los rendimientos auditados y nada de precios**.

## Fuentes y orden de trabajo

1. **FHIS Honduras.** Partir del índice público de 2,204 fichas en
   <https://quercusoft.com/honduras-fhis-200311/> y de los artefactos existentes
   en `development/rendimientos_fuente`. Seguir el enlace de descarga y buscar
   cada ficha/código en fuentes online hasta hallar el descompuesto numérico. Se
   admiten HTML, PDF, visor y endpoints públicos. Registrar URL final, código
   FHIS, fecha de consulta, página/ficha y hash del archivo descargado.
2. **Carlos Suárez Salazar, _Costo y tiempo en edificación_.** Verificar primero
   autor, edición, año, editorial, ISBN y acceso legítimo. Catálogos iniciales:
   UNFV (<https://biblioteca.unfv.edu.pe/cgi-bin/koha/opac-detail.pl?biblionumber=44721>),
   UNIBE (<https://opacbiblioteca.unibe.edu.do/bib/12111>) y UNPA
   (<https://biblioteca.unpa.edu.mx/bib/2046>). Existe un candidato alojado por
   el Colegio de Ingenieros Civiles del Municipio de Solidaridad
   (<https://ingenierosciviles.com.mx/Biblioteca/items/show/5>), pero antes de
   descargar o extraer debe verificarse que la institución ofrece legalmente el
   texto. Si no se puede verificar, usarlo sólo como pista bibliográfica y buscar
   otra fuente autorizada. No usar Scribd/idoc ni copias piratas. Extraer sólo
   los datos necesarios, con página/tabla, sin copiar ni redistribuir el libro.
3. **CYPE Honduras.** Comparar las actividades coincidentes contra
   <https://honduras.generadordeprecios.info/obra_nueva/>. Guardar la URL exacta
   de cada unidad de obra, parámetros del proyecto y coeficientes de mano de obra
   y maquinaria. Leer también la explicación oficial:
   <https://info.cype.com/es/producto/generador-de-precios-informacion-detallada/>.
   CYPE es contextual: no tratar sus coeficientes como verdad universal.

Si una fuente inicial falla, continuar con búsqueda web por título, ISBN, código
FHIS y descripción de actividad; inspeccionar enlaces y endpoints públicos y
aplicar scraping con límites, caché, identificación del cliente y backoff. No
evadir autenticación, paywalls, CAPTCHA, robots ni controles de acceso. Registrar
cada intento fallido y la razón. Nunca inventar un rendimiento.

## Contrato de datos

Usar `estimacion.db` versionada como fuente canónica conforme ADR-016. Crear una
migración idempotente y una tabla comparativa/auditable (no sobreescribir tablas
de precios) con, como mínimo:

- actividad/código EstimaStruct y unidad;
- fuente (`FHIS`, `SUAREZ_SALAZAR`, `CYPE_HN`), edición/año/ISBN cuando aplique;
- código o URL exacta, página/ficha/tabla y fecha de consulta;
- recurso (`mano_obra` o `maquinaria`), descripción, coeficiente y unidad nativa;
- coeficiente normalizado y fórmula de conversión explícita;
- tipo de match (`exacto`, `semántico`, `manual`), confianza y evidencia;
- condiciones/alcance de la actividad, hash del insumo y notas de discrepancia.

La clave de idempotencia debe impedir duplicar la misma
actividad+fuente+recurso+referencia. Conservar por separado los valores de las
tres fuentes; no promediar. Una recomendación puede emitirse sólo con regla
explícita y queda pendiente de aprobación del Director.

## Secuencia obligatoria

1. Inventariar tablas/campos de precios y generar hash/snapshot de sólo lectura.
2. Buscar y validar fuentes online; guardar manifiesto de procedencia.
3. Extraer rendimientos con parser reproducible, no mediante copiado opaco.
4. Cruzar con las actividades existentes y revisar manualmente matches dudosos.
5. Insertar únicamente datos comparativos de rendimiento mediante migración
   idempotente en SQLite canónica. PostgreSQL puede recibir espejo derivado, pero
   nunca ser la fuente canónica.
6. Ejecutar tests y repetir el loop de corrección hasta quedar limpio.
7. Entregar evidencia y dejar el goal `ready_for_director`; nunca autocerrarlo.

## Gates de aceptación

- Cero cambios en precios: demostrar hash y consultas antes/después para todas
  las columnas/tablas de precios. Cero recálculo de presupuestos.
- Al menos 10 actividades auditadas en el primer lote, distribuidas en varios
  capítulos, y continuar después sobre todos los matches alcanzables.
- Cada número debe tener URL online y página/ficha/tabla, o quedar como
  `NO_VERIFICADO` sin insertarse.
- Validar unidades, valores positivos, duplicados, conversiones y discrepancias.
- Tests de parser con fixtures pequeños y tests de migración/idempotencia.
- Revisión Python y council: DeepSeek V4 Flash como ejecutor inicial, Nemotron 3
  Ultra como reviewer; HY3, MiMo 2.5, Nemotron 3.5 Lightning y Gemma gratuito de
  OpenRouter como fallbacks según disponibilidad. La síntesis final requiere
  Codex GPT-5.4+ y Claude Sonnet. Si Sonnet no está disponible, no bloquear la
  recolección: registrar el gate y dejar la promoción pendiente.

## Salida final obligatoria

Crear CSV y Markdown titulados `rendimientos_auditados` con una fila por
actividad/recurso/fuente y exclusivamente estas columnas:

`actividad | unidad_actividad | recurso | rendimiento | unidad_rendimiento | fuente | referencia_online | pagina_ficha | confianza | estado`

No incluir precio unitario, costo, moneda, subtotal ni total. Añadir aparte un
resumen de cobertura y una bitácora de fuentes no encontradas; tampoco deben
contener precios.
