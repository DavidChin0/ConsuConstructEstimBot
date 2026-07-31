# Roadmap CASE-SAAS-001 — Scope v2 (expansión 2026-07-27)

> **Rol de este documento:** plan fasado de ejecución. No es estado actual — el estado actual manda desde `docs/architecture.md`. Cuando una fase de aquí se cierre, el resultado se refleja en `architecture.md` (§ correspondiente + ADR) y el hito se registra en `CHANGELOG.md`.
>
> **Origen:** el Director expandió el scope declarado de CASE-SAAS-001 (7 frentes, ADR-007/008/009, 2026-07-22) con 3 iniciativas nuevas: **MCP público para LLMs externos**, **PDF→CAD→estimación** y **PDF→3D vía Meshy**. Ver ADR-010 en `docs/architecture.md §9`.
>
> **Verificación:** todo el "estado real" de §2 fue verificado contra el código del repo el 2026-07-27, no asumido. Donde el roadmap previo o la sesión anterior decían algo distinto de lo que dice el código, manda el código y se anota la corrección.

---

## 1. Veredicto sobre "producto al 80%, 100% local en 2 semanas"

**Depende brutalmente de qué se llame "el producto". Las dos lecturas dan números opuestos.**

### Lectura A — "el producto" = motor de presupuestos + diseño estructural + viewer, uso local mono-usuario

**Creíble, y hasta conservador.** Esto sí está construido y verificado en vivo:

- Motor de pricing con bucketing 3-vías, `Decimal` cuantizado, fuente única en `services/pricing.py`.
- Catálogo CSI v1.2 vigente / v1.3 en curso, 144 endpoints en 24 routers.
- Diseño estructural: concreto CHOC-08, sismo, acero LRFD §D-H, conexiones §J — todos con motor puro + router + persistencia.
- Cronograma/Gantt, export PDF (ReportLab + Chromium), XLSX, publish a Supabase, backup ZIP portable.
- Puente Revit MCP HTTP :8100 (17 rutas reales en `revit_mcp.py`, no 11 como dice `architecture.md §5.1` — corregir).
- Viewer Babylon con pipeline Revit→IFC→GLB verificado 248/248 elementos matcheados, 222 con keynote.
- `estimastruct-mcp` STDIO con 12 tools, verificado con cliente MCP real.

Para esa definición yo diría **~85% hecho**. Lo que falta para "100% local" no son 2 semanas tampoco — son ~3-4 semanas de deuda técnica real (tests del pipeline de pricing, auditoría Alembic, consolidar el SQLite legacy del dashboard, cargas de piso ETABS). Pero el orden de magnitud del Director es correcto aquí.

### Lectura B — "el producto" = todo lo de este roadmap (SaaS + AWS + auth + RAG + MCP público + PDF→CAD + Meshy + ETABS bidireccional)

**No cuadra. Ni de lejos.** Los números:

| Métrica | Valor real verificado |
|---|---|
| Frentes del roadmap SaaS cerrados | **0 de 7.** Frente 1 está ~40% (MCP hecho 2026-07-26, Skill no) |
| Días de trabajo acumulados en CASE-SAAS-001 | **1** (arrancó 2026-07-26) |
| Endpoints con autenticación | **0 de 144** |
| CORS | `allow_origins=["*"]` en `backend/main.py:28` |
| Tests unitarios en el repo | **0.** No existe directorio `tests/`, ni un solo `test_*.py` |
| Endpoints con `response_model` Pydantic | **4 de 144** (~2.8%) |
| Migraciones Alembic | **1 sola**: `606c3f3a7b6b_baseline.py`. Todo cambio de `models.py` posterior al baseline está sin migración |
| `backend/cag/` (Frente 2, ADR-008) | **No existe** |
| Dependencias LLM / pgvector / PDF / CAD en el repo | **Ninguna.** `requirements.txt` no tiene `anthropic`, `pgvector`, `pdfplumber`, `ezdxf`, ni siquiera `mcp`/`httpx` que el MCP ya usa |
| Items 5, 6, 8 de este roadmap (PDF→CAD, Meshy, MCP público) | **0 líneas.** No están en código ni estaban en el roadmap previo — son features nuevas, no gaps a cerrar |

Trabajo pendiente estimado para el scope completo: **~160-235 días-persona** (detalle por fase abajo). Dos semanas son ~10 días-persona.

> **El factor es 16x-23x.** No es una diferencia de estimación optimista; es una diferencia de categoría.

### Estimación ponderada del scope SaaS completo

| Punto del scope | % real |
|---|---|
| 1. Puente ETABS | ~25% (import unidireccional funciona: 5 endpoints — concreto, acero ×2, conexiones, sismo. Sin escritura de vuelta) |
| 2. Herramientas Revit | ~35% (17 endpoints puente vivos de 70 mapeados; STDIO no construido) |
| 3. RAG EstimaStruct | 0% |
| 4. AWS + auth + hardening | 0% |
| 5. PDF→CAD→estimación | 0% |
| 6. PDF→3D Meshy | 0% |
| 7. LLM económico + CAG | ~15% (existe el transporte MCP interno; no hay LLM, ni CAG, ni corpus) |
| 8. MCP público multi-tenant | 0% |
| **Ponderado** | **~12-18%** |

**Recomendación al Director:** dejar de usar un solo número. Son dos productos distintos con dos madureces distintas. "EstimaStruct Desktop (interno ConsuConstruct)" está al 85% y se puede cerrar. "EstimaStruct SaaS" está al 15% y es un proyecto de 7-9 meses de un operador.

### Corrección a un gap previamente reportado

La sesión anterior dijo que el import ETABS es **"solo combos de concreto"**. Falso: hay 5 endpoints de import ETABS (`diseno_estructural.py:741` concreto, `acero_diseno.py:53` y `:248` acero, `conexion_acero.py:169` conexiones, `sismo.py:510` sismo). El gap real no es de cobertura de material — es que **todos son upload de archivo (CSV/XLSX) unidireccional**. No hay conexión viva a ETABS, no hay escritura de vuelta al modelo, y no hay cargas de piso automáticas.

---

## 2. Estado real verificado (2026-07-27)

Base para todas las estimaciones. Verificado leyendo código, no `architecture.md`.

```
backend/
├── 24 routers, 144 endpoints              ✅ operativo
├── services/pricing.py                    ✅ fuente única, sin tests
├── services/etabs_parse.py                ⚠️  helper de decode/detección xlsx; el parseo real vive en los routers
├── mcp_server/ (12 tools STDIO)           ✅ nuevo 2026-07-26, deps sin declarar en requirements.txt
├── alembic/versions/ → 1 archivo          🔴 solo baseline, drift sin auditar
├── cag/                                   🔴 no existe
├── main.py:28 allow_origins=["*"]         🔴
└── (sin auth, sin tests, 4/144 response_model)  🔴
```

Hallazgos que afectan la planeación:

1. **`mcp` y `httpx` no están en `backend/requirements.txt`** pese a que `backend/mcp_server/server.py` los importa. Un `pip install -r requirements.txt` limpio deja el MCP roto. Fix de 2 minutos, pero es señal de que no hay gate de dependencias.
2. **Una sola migración Alembic.** El baseline. Cada campo agregado a `models.py` desde entonces solo existe en la BD porque alguien lo creó a mano o porque `AUTO_CREATE_SCHEMA` estuvo en `true` en algún momento. Esto **bloquea AWS**: no se puede provisionar una RDS limpia sin un historial de migraciones que reproduzca el schema.
3. **Cero tests.** No es "pocos tests" — es cero. Con un motor de dinero (`Numeric(14,4)`, bucketing 3-vías, overhead compuesto) que ya tuvo un bug de doble conteo en producción (2026-07-03), esto es el riesgo #1 de todo el proyecto.
4. **`architecture.md §5.1` dice "11 endpoints puente Revit MCP"; hay 17.** Drift menor de documentación, corregir al cerrar la Fase 0.

---

## 3. Mapa: los 9 puntos → fases

| # | Punto del scope | Fase | Prioridad |
|---|---|---|---|
| 9 | Chequeo de realismo del timeline | **§1 de este doc** | Resuelto (arriba) |
| 7 | LLM económico + CAG/RAG conectado (¿mismo MCP o separado?) | **F0** (decisión) + **F3** (construcción) | MVP |
| 2 | Todas las herramientas Revit (MCP STDIO 46+ tools) | **F0** (cerrar Frente 1) + **F6** | MVP parcial |
| 4 | AWS deploy + auth + hardening | **F1** (auth/tenancy) + **F2** (AWS) | MVP — bloquea todo lo remoto |
| 3 | RAG específico EstimaStruct | **F3** | MVP |
| 8 | MCP público para LLMs externos | **F4** | MVP del SaaS, pero depende de F1+F2 |
| 1 | Puente ETABS perfeccionado + cargas de piso | **F5** | Nice-to-have para SaaS / MVP para uso interno |
| 5 | PDF→CAD→estimación | **F7** | Nice-to-have, alto riesgo |
| 6 | PDF→3D vía Meshy | **F8** | Nice-to-have, riesgo de producto |

---

## 4. Fases

Convención: estimaciones en **semanas-persona** para 1 operador (Director + agentes IA), 5 días productivos/semana. No incluyen tiempo de venta, soporte ni obra.

---

### F0 — Estabilización del núcleo `[BLOQUEA TODO]`

**Duración: 3-4 semanas. Dependencias: ninguna. Empezar ya.**

Esta fase no agrega ni una feature. Existe porque **no se puede poner en producción multi-tenant un motor de dinero sin tests, ni desplegar en RDS sin historial de migraciones.** Saltarse F0 no acelera el proyecto — mueve el costo a producción, donde un bug de pricing se cobra en dinero de cliente.

**Qué se construye:**

| Entregable | Detalle | MVP |
|---|---|---|
| Suite de tests del pipeline de pricing | Golden snapshots: 3 presupuestos reales congelados (Valle de Angeles + 2), assert sobre `costo_base`, `precio_unitario`, `total`, subtotales por capítulo y overhead. Cubre `rebucket_insumos`, `calc_base`, el path de `/calcular`, y regresión explícita del bug de doble conteo 2026-07-03 | **MVP** |
| Auditoría y regeneración de Alembic | Diff `Base.metadata` vs BD viva vs el único baseline. Emitir las migraciones faltantes. Verificar que una PG vacía + `alembic upgrade head` reproduce el schema exacto | **MVP — bloquea AWS** |
| `response_model` Pydantic en el núcleo | Solo los ~30 endpoints del núcleo presupuestal (presupuestos, capítulos, partidas, insumos, recursos, cálculos). Los ~45 de ingeniería quedan para después — sus contratos aún se mueven | **MVP** |
| Declarar dependencias faltantes | `mcp`, `httpx`, `ifcopenshell` a `requirements.txt`. Pin de versiones | **MVP** |
| Cerrar Frente 1: Skill EstimaStruct full-system | El acompañante del `estimastruct-mcp` que declara ADR-007 y nunca se construyó | **MVP** |
| **Decisión arquitectural (no código):** RAG/CAG — ¿cuelga del `estimastruct-mcp` o va en servidor propio? | Ver §5 "Decisiones pendientes" | **MVP** |
| Consolidar SQLite legacy del dashboard | `ESTIMASTRUCT_UI_DB` → Postgres. Elimina un code path entero | Nice-to-have |

**Riesgo:** bajo técnicamente, alto políticamente — no produce nada demostrable. Es exactamente la fase que un Director con prisa se salta y que después cuesta el triple.

**Definición de hecho:** `pytest` verde en CI, PG vacía se levanta con `alembic upgrade head`, `/docs` de FastAPI muestra schemas reales en el núcleo.

---

### F1 — Seguridad y multi-tenancy `[BLOQUEA TODO LO REMOTO]`

**Duración: 5-7 semanas. Depende de: F0.**

La fase más subestimada del proyecto. **No es "agregar login".** Es re-scopear cada query de 144 endpoints para que un tenant no pueda leer las obras de otro. Hoy `GET /presupuestos` devuelve *todas* las obras de la BD, sin excepción — eso es un data breach el día 1 de multi-tenant.

**Qué se construye:**

| Entregable | Detalle | MVP |
|---|---|---|
| Modelo de tenancy | Tabla `tenant`, `usuario`, `usuario_tenant`. Columna `tenant_id` en `presupuesto` y en todo lo que no cuelgue de él por FK (`recurso` es el caso peligroso: hoy es catálogo maestro global — decidir si es global compartido o por tenant) | **MVP** |
| Scoping de queries | Auditoría de las 144 rutas. Dependency de FastAPI que inyecta el `tenant_id` del token y filtra. Row-Level Security en Postgres como segunda barrera (defensa en profundidad — que un router olvidado no filtre no debería exponer datos) | **MVP** |
| Auth JWT/OAuth2 | Login, refresh, revocación. Roles mínimos: `owner`, `estimador`, `lectura` | **MVP** |
| CORS por allowlist | Reemplazar `["*"]` por origen configurable | **MVP** |
| Rate limiting | Por tenant y por endpoint. Prerrequisito de F4 | **MVP** |
| Gestión de secretos | `SUPABASE_SECRET_KEY`, credenciales PG, API keys de LLM → Secrets Manager, no `D:\Secrets\*.txt` | **MVP** |
| Auditoría OWASP Top 10 | Frente 7 del roadmap original | **MVP** |
| Feature flags por tenant | Qué módulos ve cada plan | Nice-to-have |

**Riesgo alto:** un scoping incompleto no falla ruidosamente. Falla mostrándole a un cliente el presupuesto de otro. Mitigación: RLS en Postgres + un test de integración que cree 2 tenants y verifique aislamiento en cada endpoint de lectura.

**Costo:** cero recurrente, todo es tiempo.

---

### F2 — Despliegue AWS

**Duración: 3-4 semanas. Depende de: F0 (Alembic) + F1 (auth). Estrictamente después.**

Desplegar antes de F1 es publicar una API sin autenticación en internet. No negociable.

**Qué se construye:**

| Entregable | Detalle | MVP |
|---|---|---|
| RDS PostgreSQL | Multi-AZ opcional al inicio. Backups automáticos. Migraciones vía `alembic upgrade head` en el deploy | **MVP** |
| Backend en ECS Fargate | ECS sobre Lambda: FastAPI con procesos largos (export PDF vía Chromium headless, recálculos masivos, scripts_runner) no encaja en el modelo Lambda. Lambda solo si después se separan endpoints puramente CRUD | **MVP** |
| Frontend + assets estáticos | S3 + CloudFront. **Los 194MB del viewer** (`D:\GitHub\3d Viewer assets\`: furniture 23M, gorilla_map 23M, hdri 5.6M, loft_interior 21M, textures 123M) van a S3, no al contenedor. El patrón ya se probó localmente con `VIEWER_ASSETS_PATH` — replicar cambiando la resolución a URL de CloudFront | **MVP** |
| CI/CD | Build → tests de F0 → migración → deploy. Sin la suite de F0 esto es un deploy a ciegas | **MVP** |
| Observabilidad | CloudWatch logs + métricas + alarma de error rate. `diagnostics.py` ya existe, exponerlo | **MVP** |
| Chromium headless en el contenedor | El export PDF depende de él. Es la parte más molesta del Dockerfile | **MVP** |
| Staging separado | Segundo entorno | Nice-to-have |

**Costo recurrente estimado (arranque, sin tráfico real):**

| Recurso | USD/mes aprox |
|---|---|
| RDS `db.t4g.small` single-AZ | 25-35 |
| ECS Fargate 1 tarea (0.5 vCPU / 1GB) | 15-20 |
| S3 (194MB + transferencia baja) | 1-3 |
| CloudFront | 1-10 (según tráfico) |
| ALB | ~18 |
| Secrets Manager, CloudWatch | 5-10 |
| **Total piso** | **~65-95/mes antes del primer cliente** |

Multi-AZ + staging duplica largo. **Con cero clientes pagando hoy, este es el primer costo fijo real del proyecto** — vale la pena decidir si se enciende cuando haya al menos un piloto comprometido.

---

### F3 — Capa IA: corpus, RAG, CAG y LLM económico

**Duración: 4-6 semanas. Depende de: F0. Puede correr en paralelo a F1 (se construye contra el Postgres local).**

Esta fase resuelve los puntos 3 y 7. **La confusión a limpiar primero:** ADR-008 dice CAG (context caching), la sesión anterior pidió RAG. Son cosas distintas y aquí la respuesta correcta es **las dos, separadas por naturaleza del corpus**.

#### 3.1 Partición del corpus — la decisión central

| Corpus | Naturaleza | Técnica correcta | Por qué |
|---|---|---|---|
| Normas ACI 318-19, AISC 360 LRFD, CHOC-08 | Fijo, se actualiza cada varios años, se consulta completo | **CAG** (prompt caching) | Cambia casi nunca. Cachear el prefijo cuesta 1.25x una vez y las lecturas cuestan 0.1x. Trocearlo y buscarlo por embedding pierde el contexto normativo entre cláusulas |
| Fichas CSI v1.3 (catálogo maestro) | Semi-fijo, ~cientos de fichas, versionado | **CAG por versión de template** | Ya está versionado en `Template2_Updated/`. Una caché por `template_version` |
| Histórico de presupuestos por cliente | Crece con cada obra, multi-tenant, búsqueda semántica ("¿cómo costeamos losa aligerada en Valle de Angeles?") | **RAG (pgvector)** | Crece sin techo, requiere filtrado por tenant, y la consulta es de similitud, no de recitación |
| `docs/architecture.md` + docs internos | Semi-fijo, para agentes de desarrollo | **RAG** (ya hay precedente: `backend/scripts_runner/embed_architecture.py`) | Corpus de desarrollo, no de producto |

#### 3.2 Esquema pgvector: **dedicado, no compartido**

El RAG que existe hoy (`rag.chunks`, escrito por `vault_sync.py`) es de **CustomerBot**, otro producto, otro corpus, otro ciclo de vida, y en otra base. Compartirlo acopla dos SaaS distintos y hace imposible el aislamiento por tenant.

**Decisión propuesta:** esquema `rag` **dentro de la BD `estimastruct`**, con `tenant_id` en cada chunk y filtro obligatorio. Reusar el *patrón* de CustomerBot (nomic-embed-text 768d, `metadata` jsonb), no la instancia.

> **Gotcha heredado de CustomerBot que NO se debe repetir:** allá los filtros leen `metadata->>'semantic_route'` y no la columna homónima, así que actualizar la columna no cambia nada para las búsquedas. Aquí: una sola fuente por campo filtrable — columna real con índice, no jsonb.

#### 3.3 Modelo LLM — corrección a ADR-007

ADR-007 nombra `claude-sonnet-4-6` / `claude-opus-4-7`. Ambos siguen activos pero ya no son la generación vigente. Precios actuales por millón de tokens (API Anthropic, primera parte):

| Modelo | Contexto | In | Out | Mínimo cacheable | Rol propuesto |
|---|---|---|---|---|---|
| `claude-haiku-4-5` | 200K | $1 | $5 | **4096 tokens** | Clasificación CSI, extracción de cantidades, resúmenes. El "LLM económico" del punto 7 |
| `claude-sonnet-5` | 1M | $3 ($2 intro hasta 2026-08-31) | $15 ($10 intro) | 1024 tokens | Camino caliente del producto: razonar sobre normas, armar presupuesto |
| `claude-opus-5` | 1M | $5 | $25 | 512 tokens | Solo tareas de alto valor / desarrollo |

> **Gotcha de costo que cambia el diseño de CAG:** el mínimo cacheable de `claude-haiku-4-5` es **4096 tokens** — 8x el de Opus 5. Un bloque de norma de 2K tokens **no se cachea en Haiku** y no da error: simplemente `cache_creation_input_tokens` sale en 0 y se paga precio completo cada vez. Si el CAG de normas se arma con chunks pequeños y se sirve con Haiku por barato, el ahorro no existe. **Diseñar los bloques CAG por encima de 4096 tokens, o servir el CAG con Sonnet 5.**
>
> Economía de la caché: escritura 1.25x (TTL 5min) o 2x (TTL 1h); lectura ~0.1x. Con TTL 5min el punto de equilibrio son 2 requests; con TTL 1h son 3.

**Embeddings:** la API de Anthropic **no tiene endpoint de embeddings**. El RAG seguirá con `nomic-embed-text` local (768d), como el resto del ecosistema. **Restricción operativa dura ya conocida:** con GPU de 4GB, un modelo grande residente en Ollama deja a nomic pasando de 0.3s a >60s. Ningún modelo local grande en el camino caliente; `keep_alive=0` siempre. En AWS esto se resuelve distinto (embeddings en el contenedor o servicio aparte) — decidirlo en F2.

#### 3.4 Entregables

| Entregable | MVP |
|---|---|
| `backend/cag/` — bloques de normas + fichas, con `cache_control`, TTL y verificación de `cache_read_input_tokens` | **MVP** |
| Esquema `rag` en `estimastruct` + ingest de histórico de presupuestos con `tenant_id` | **MVP** |
| Cliente Anthropic (`anthropic` a requirements) con selector de modelo por tarea | **MVP** |
| Endpoints `/ia/*`: consulta normativa (CAG), búsqueda de precedentes (RAG), sugerencia de partida | **MVP** |
| Ingest de docs de arquitectura al RAG | Nice-to-have |
| Evaluación (golden set de preguntas normativas + respuestas esperadas) | Nice-to-have pero muy recomendable |

**Costo recurrente:** variable por token. Con CAG bien armado y Haiku para el volumen, un tenant activo debería costar unidades de dólar al mes — pero **es costo variable sin techo si no se pone rate limiting por tenant** (que llega en F1).

---

### F4 — MCP público para LLMs externos `[NUEVO — punto 8]`

**Duración: 3-4 semanas. Depende DURO de: F1 (auth, tenancy, rate limiting) + F2 (estar desplegado).**

Esta es la superficie comercial del SaaS: exponer EstimaStruct como servicio consumible por *cualquier* cliente MCP (Claude, GPT, agentes de terceros). **Es un producto distinto del `estimastruct-mcp` interno**, aunque compartan implementación.

| Dimensión | `estimastruct-mcp` (interno, existe) | MCP público (nuevo) |
|---|---|---|
| Transporte | STDIO | **HTTP/SSE** — STDIO no sirve para acceso remoto multi-tenant |
| Audiencia | Director, Claude Code, Codex | Clientes del SaaS, agentes de terceros |
| Auth | Ninguna (proceso local) | API key por tenant, u OAuth por tenant |
| Superficie | 12 tools, 9 lectura + **3 escritura** | **Solo lectura + cálculo.** Las escrituras (`actualizar_cantidad`, `calcular_obra`, `ajustar_cuadrilla`) no salen sin un gate explícito |
| Rate limit | Ninguno | Por key y por tool |
| Billing | N/A | Por llamada o por tool |

**Por qué la superficie pública no lleva escritura al inicio:** el propio README del MCP interno lo advierte — el servidor **no exige aprobación por sí mismo**, el gate lo pone el cliente MCP. En STDIO local eso es aceptable porque el cliente es Claude Code con su sistema de permisos. En una API pública no hay tal garantía: un agente de terceros puede escribir en la obra de un cliente sin ninguna confirmación humana. La escritura remota necesita su propio diseño (tokens de escritura separados, confirmación fuera de banda, log de auditoría) y no cabe en el MVP.

**Qué se construye:**

| Entregable | MVP |
|---|---|
| Transporte HTTP/SSE MCP sobre la API de F2 | **MVP** |
| Superficie pública v1: subset de solo lectura + `calcular` en modo *dry-run* (calcula y devuelve, no persiste) | **MVP** |
| API keys por tenant: emisión, rotación, revocación | **MVP** |
| Rate limiting por key y por tool + métricas de uso por tool | **MVP** |
| Documentación pública de la superficie | **MVP** |
| Billing por uso (metering → factura) | Nice-to-have v1, MVP para monetizar |
| Escrituras con gate de confirmación fuera de banda | Nice-to-have (v2) |

**Riesgo:** exponer esto antes de F1 es catastrófico — una API sin tenancy que devuelve "todas las obras de la BD". El orden **F1 → F2 → F4** no admite atajos.

---

### F5 — Puente ETABS: de import a bidireccional `[punto 1]`

**Duración: 3-5 semanas. Depende de: F0. Independiente del resto — puede correr en cualquier momento.**

**Decisión previa a construir: reusar `ETABSFastMCP` vs construir STDIO nuevo (Frente 4).**

Lo que se sabe: `ETABSFastMCP` existe en `brain-agentic`, casos CASE-002/003 cerrados 2026-07-17, capa MCP completa validada en vivo (attach vía `GetObject`), con gotchas conocidos (elevación, modelo bloqueado, nombres numéricos). **No está conectado a EstimaStruct.**

**Recomendación: reusar, no reconstruir.** Frente 4 del roadmap original ("MCP STDIO `etabs-mcp-stdio`") se reinterpreta como *"cablear el bridge existente a EstimaStruct"*, no como *"escribir un bridge nuevo"*. Razones:

- El bridge ya está validado en vivo contra ETABS 22 y ya cargó sus gotchas.
- Construir uno nuevo duplica el conector C#, que es la parte cara y frágil.
- El acoplamiento cross-repo se resuelve igual que el MCP interno: el cliente habla HTTP/STDIO contra un endpoint configurable, no importa dónde viva.

**Contra-argumento a evaluar en la decisión:** `ETABSFastMCP` vive en otro repo con otro ciclo de release. Si EstimaStruct se vuelve SaaS y ETABS solo corre en la máquina del ingeniero, el bridge es inherentemente local — lo que significa que este frente **nunca es un servicio en la nube**, es un componente de escritorio que habla con el SaaS. Eso está bien, pero hay que declararlo.

| Entregable | MVP |
|---|---|
| ADR de decisión reusar-vs-construir | **MVP** |
| Cliente EstimaStruct → ETABS bridge (leer modelo abierto, no solo parsear CSV) | **MVP** |
| **Cargas de piso automáticas** (el gap declarado en `architecture.md §9`) | **MVP** |
| Escritura de vuelta a ETABS (secciones dimensionadas por el motor LRFD) | Nice-to-have, alto valor diferenciador |
| Sincronización de combos y espectro CHOC-08 | Nice-to-have |

**Riesgo:** dependencia de una app de escritorio comercial con automatización COM. El modelo bloqueado, la versión de ETABS y el estado de la instancia son fuentes de fallo fuera de nuestro control. Nunca poner esto en un camino crítico de usuario.

---

### F6 — Revit MCP STDIO completo `[punto 2]`

**Duración: 3-4 semanas. Depende de: F0. Independiente.**

Hoy: 17 rutas puente HTTP en `revit_mcp.py` contra el MCP :8100. Mapeado: 70 endpoints (35 read + 35 write) en `tool_manifest.py` (CASE-REVIT-API-DICT-001), con 20 sin mapear (geometry avanzada, worksets, design options, phasing).

| Entregable | MVP |
|---|---|
| MCP STDIO Revit con las 46+ tools que ya están mapeadas | **MVP** |
| Retiro del puente HTTP :8100 (o mantenerlo como fallback) | **MVP** |
| Scripts IronPython consolidados en `pyrevit/scripts/` (Frente 5 original) | **MVP** |
| Las 20 tools sin mapear (worksets, design options, phasing) | Nice-to-have |
| Migrar `PYREVIT_S10_export_viewer_glb.py` de OBJ a IFC, o retirarlo | Nice-to-have (el pipeline IFC ya lo reemplazó de facto) |

**Nota de valor:** este frente es capacidad de escritorio, no de SaaS. Revit corre en la máquina del modelador. Su valor real es hacer más denso el diferenciador Revit+EstimaStruct+ETABS, no habilitar el producto en la nube.

---

### F7 — PDF→CAD→estimación `[NUEVO — punto 5]`

**Duración: 6-10 semanas. Depende de: F0. La fase más incierta del roadmap.**

Feature completa desde cero. **La estimación tiene la varianza más alta de todo el documento porque el problema es fundamentalmente distinto según el input:**

| Tipo de PDF | Dificultad | Enfoque |
|---|---|---|
| **Vectorial** (exportado de Revit/AutoCAD) | Media | La geometría está en el archivo. Extraer paths, capas, textos, escala. `pdfplumber`/PyMuPDF + heurísticas. Precisión alcanzable: alta |
| **Escaneado** (raster, plano en papel fotografiado) | **Muy alta** | Requiere visión: detección de líneas, OCR de cotas, inferencia de escala, reconocimiento de símbolos. Precisión: incierta, dependiente de calidad del escaneo |

**Recomendación fuerte: partir el alcance.** El MVP debe ser **solo vectorial**. Escaneado es una segunda fase con su propia decisión go/no-go, tras medir precisión real sobre planos reales de ConsuConstruct.

**Pipeline propuesto (MVP vectorial):**

```
PDF vectorial
  → extracción de geometría (paths + capas + texto)
  → detección de escala (cota conocida o marco de título)
  → clasificación de entidades (muro / losa / columna / puerta / ventana)
  → cuantificación (m², ml, unidades)
  → mapeo a fichas CSI del catálogo existente
  → partidas con `revit_q` (reusa el flujo de takeoff que YA existe)
```

El último paso es la buena noticia: el modelo de datos ya tiene el hueco. `partida.revit_q` + `factor_e` + `factor_f` es exactamente el patrón de "cantidad importada de una fuente externa, con factores de ajuste editables". PDF→CAD **no necesita un flujo nuevo de presupuesto** — solo necesita llenar `revit_q` desde otra fuente. Eso reduce el riesgo de integración a casi cero; el riesgo vive todo en la extracción.

| Entregable | MVP |
|---|---|
| Extractor de geometría vectorial + detección de escala | **MVP** |
| Clasificador de entidades (heurísticas + LLM de visión de F3 para casos ambiguos) | **MVP** |
| Mapeo a CSI + escritura a `revit_q` | **MVP** |
| **UI de revisión humana obligatoria** antes de aceptar cantidades | **MVP — no negociable** |
| Métrica de precisión contra takeoff manual sobre planos reales | **MVP** — sin esto no se sabe si sirve |
| Soporte de PDF escaneado | Fase aparte, go/no-go tras medir |

**Riesgo alto de producto:** una cantidad mal extraída se convierte en dinero mal presupuestado. **Nunca aceptar cantidades de PDF sin revisión humana explícita, y marcarlas visualmente distintas** (el modelo ya tiene `color_tipo` en `partida` — usarlo). Si la precisión medida no supera un umbral acordado con el Director, la feature se congela: un takeoff automático poco confiable es peor que ninguno, porque induce confianza falsa.

**Costo:** tiempo + tokens de visión si se usa LLM en el clasificador.

---

### F8 — PDF→3D vía Meshy `[NUEVO — punto 6]`

**Duración: 2-3 semanas de integración. Depende de: F0. Bajo esfuerzo, alto riesgo de producto.**

Técnicamente es la fase más barata: llamar una API externa y meter el GLB resultante en un viewer Babylon que **ya existe y ya carga GLB**.

**Pero el riesgo no es técnico, es de confusión de producto, y es serio.**

| | Pipeline Revit→IFC→GLB (existe) | Pipeline PDF→Meshy→GLB (nuevo) |
|---|---|---|
| Origen | Modelo BIM real | Imagen 2D |
| Identidad por elemento | **Sí** — ElementId, 248/248 matcheados | **No** — malla generada |
| Metadata | keynote, categoría CSI, familia, tipo, nivel, type_mark | Ninguna |
| Fidelidad dimensional | Exacta (placement horneado con `use-world-coords`) | Aproximada / inventada por el modelo generativo |
| Uso legítimo | Verificación, takeoff, inspección de elementos | Visualización conceptual, pitch, referencia volumétrica |

**Si ambos se muestran en el mismo viewer sin distinción visual, un cliente puede clickear una malla generada creyendo que está inspeccionando un elemento BIM real.** Ese es el riesgo, y es un riesgo de credibilidad del producto entero — el diferenciador de EstimaStruct es precisamente que sus números salen de un modelo real.

**Mitigaciones obligatorias (no opcionales):**

1. **Modo separado en la UI.** No mezclar mallas Meshy y mallas IFC en la misma escena por defecto.
2. **Marca visual permanente:** badge "MODELO APROXIMADO — GENERADO POR IA", wireframe distinto, o tinte de material.
3. **Bloqueo funcional:** un mesh Meshy **no puede** alimentar `revit_q` ni ninguna cantidad. Cero conexión al pipeline de presupuesto.
4. **`_revitProps` ausente = panel de info deshabilitado.** El `showInfo()` del viewer ya depende de esa metadata; si no existe, no abrir el panel — no inventar contenido.

| Entregable | MVP |
|---|---|
| Secret nuevo: `MESHY_API_KEY` (Secrets Manager, no archivo plano) | **MVP** |
| Pipeline PDF → imagen (render de página) → Meshy → GLB → S3 | **MVP** |
| Modo "conceptual" separado en el viewer + marca visual | **MVP — no negociable** |
| Control de costo: cuota por tenant, confirmación antes de generar | **MVP** |
| Caché de generaciones (mismo input → no re-generar) | Nice-to-have |

**Costo recurrente: variable por generación.** Meshy cobra por crédito/generación según plan. **Esto es COGS variable atado a acción de usuario** — sin cuota por tenant, un usuario puede quemar presupuesto en una tarde. La cuota es MVP, no adorno. Verificar la tarifa vigente antes de comprometer precio al cliente.

**Recomendación honesta al Director:** esta feature es de demo/marketing, no de núcleo. Vale como diferenciador en un pitch ("mira, subes un plano y ves un volumen"). No vale como capacidad de ingeniería y no debe presentarse como tal. Priorizarla por encima de F1-F4 sería un error de secuencia.

---

## 5. Grafo de dependencias

```
                          F0 Estabilización (3-4 sem)
                          [BLOQUEA TODO]
                                │
        ┌───────────┬───────────┼───────────┬───────────┬───────────┐
        │           │           │           │           │           │
        ▼           ▼           ▼           ▼           ▼           ▼
   F1 Auth +    F3 IA        F5 ETABS    F6 Revit    F7 PDF→CAD  F8 Meshy
   Tenancy      RAG/CAG      (3-5 sem)   STDIO       (6-10 sem)  (2-3 sem)
   (5-7 sem)    (4-6 sem)                (3-4 sem)
        │           │
        ▼           │
   F2 AWS ◄─────────┘  (F3 se despliega con F2 o después)
   (3-4 sem)
        │
        ▼
   F4 MCP público
   (3-4 sem)
```

**Cadena crítica (lo mínimo para tener un SaaS vendible):**

`F0 → F1 → F2 → F4` = **14-19 semanas**, con F3 en paralelo. Redondeando: **4-5 meses hasta un SaaS multi-tenant con superficie MCP pública.**

**Scope completo (las 9 fases, con el paralelismo que un solo operador puede sostener):** **7-9 meses.**

Serie pura sin paralelismo: 32-47 semanas.

---

## 6. Decisiones pendientes del Director

Ninguna de estas es código. Todas bloquean o desvían fases enteras.

| # | Decisión | Fase que bloquea | Recomendación de este documento |
|---|---|---|---|
| D1 | ¿"80%" se refiere al producto local o al SaaS? | Comunicación y planeación | Separar en dos productos con dos números. Ver §1 |
| D2 | ¿RAG cuelga del `estimastruct-mcp` interno o va en servidor propio? | F0 (decisión) / F3 | **Ninguno de los dos: va como endpoints `/ia/*` de la API.** El MCP interno es un cliente HTTP de la API — si el RAG vive en la API, ambos MCP (interno y público) lo consumen gratis, sin duplicar. Meter el RAG dentro del servidor MCP lo haría inaccesible desde el frontend web |
| D3 | ¿`recurso` (catálogo maestro de precios) es global compartido o por tenant? | F1 | Probablemente híbrido: catálogo base global + overrides por tenant. Es la decisión de modelo de datos más delicada de F1 |
| D4 | ¿Reusar `ETABSFastMCP` o construir STDIO nuevo? | F5 | Reusar. Ver §F5 |
| D5 | ¿Se enciende AWS antes de tener un piloto comprometido? | F2 | No. ~$65-95/mes fijos con cero ingresos. Encender cuando haya un cliente piloto con fecha |
| D6 | Prioridad relativa de F7/F8 (features nuevas) vs F1-F4 (habilitadores del SaaS) | Secuencia global | F1-F4 primero. F8 es demo, F7 es incierto. Ninguno de los dos convierte a EstimaStruct en SaaS |
| D7 | ¿Modelo LLM del camino caliente? | F3 | `claude-haiku-4-5` para volumen, `claude-sonnet-5` para razonamiento sobre normas. Ojo con el mínimo cacheable de 4096 tokens en Haiku (§F3.3) |
| D8 | ¿La escritura remota entra en la superficie MCP pública v1? | F4 | No. Solo lectura + cálculo dry-run |

---

## 7. Riesgos ordenados por impacto

| # | Riesgo | Impacto | Mitigación | Fase |
|---|---|---|---|---|
| R1 | **Cero tests sobre un motor de dinero.** Ya hubo un bug de doble conteo en producción (2026-07-03) | Presupuesto incorrecto entregado a cliente → pérdida financiera y de credibilidad | Golden snapshots + regresión explícita del bug conocido | F0 |
| R2 | **Scoping multi-tenant incompleto.** Falla silenciosa: muestra datos de otro cliente | Data breach. Fin del producto | RLS en Postgres + test de aislamiento por endpoint | F1 |
| R3 | **Alembic con un solo baseline** | No se puede provisionar RDS limpia. Bloquea AWS por completo | Auditar y regenerar migraciones | F0 |
| R4 | **MCP público expuesto antes de tenancy** | API pública devolviendo todas las obras de todos | Orden F1→F2→F4 sin atajos | F4 |
| R5 | **Confusión BIM real vs 3D generado** | Cliente toma decisión sobre geometría inventada | Modo separado + marca visual + bloqueo funcional | F8 |
| R6 | **PDF→CAD con precisión insuficiente** | Cantidades erróneas con apariencia de automatización confiable | Revisión humana obligatoria + métrica de precisión + go/no-go | F7 |
| R7 | **Costo variable sin techo** (LLM + Meshy) | Un tenant quema el margen | Rate limiting (F1) + cuota Meshy por tenant (F8) | F1/F8 |
| R8 | **Ciclo de venta LATAM largo** — adopción BIM baja, hay que educar al cliente | Runway. AWS encendido sin ingresos | No encender AWS sin piloto comprometido (D5) | F2 |
| R9 | **Dependencia de apps de escritorio comerciales** (Revit, ETABS) fuera de nuestro control | Frentes F5/F6 nunca son "servicio en la nube" | Declararlo: son componentes de escritorio que hablan con el SaaS | F5/F6 |

---

## 8. Contexto de mercado y su efecto en la secuencia

Datos dados por el Director: adopción BIM baja en LATAM (oportunidad y riesgo), diferenciador defendible = stack Revit+EstimaStruct+ETABS integrado, competencia global indirecta (Procore, Togal.ai, Assemble, CostX) sin presencia regional ni este stack, **cero clientes externos pagando hoy**.

Tres consecuencias concretas para el orden de las fases:

1. **El diferenciador vive en F5 y F6, no en F1-F4.** Auth y AWS son mesa de entrada — nadie compra por tenerlos. Pero sin ellos no hay producto vendible. Son costo obligatorio, no valor.
2. **Adopción BIM baja debilita el diferenciador para el cliente promedio.** Si el prospecto no usa Revit, la integración Revit no le vende nada. Eso hace que **F7 (PDF→CAD) sea estratégicamente más interesante de lo que su riesgo técnico sugiere**: es el puente hacia el constructor que trabaja con planos PDF y no tiene BIM. Es el único item de este roadmap que abre mercado no-BIM. Vale la pena un spike acotado (1 semana, medir precisión sobre 5 planos vectoriales reales) antes de decidir su prioridad definitiva.
3. **Cero clientes pagando = el reloj de AWS no debe empezar todavía.** Construir F1 y F3 localmente, y encender F2 cuando haya un piloto con fecha.

---

## 9. Qué hacer en las próximas 2 semanas (respuesta constructiva)

El Director pidió 2 semanas. Dos semanas no cierran el SaaS, pero sí cierran cosas reales. Propuesta de esas 10 días-persona:

| Día | Trabajo | Fase |
|---|---|---|
| 1 | Declarar `mcp`/`httpx`/`ifcopenshell` en `requirements.txt`. Auditoría Alembic: diff `Base.metadata` vs BD viva, inventario del drift | F0 |
| 2-4 | Golden snapshots del pipeline de pricing: 3 presupuestos congelados + assert de totales + regresión del bug de doble conteo | F0 |
| 5-6 | Emitir las migraciones Alembic faltantes. Verificar PG vacía + `upgrade head` reproduce el schema | F0 |
| 7-8 | Skill EstimaStruct full-system (cierra Frente 1 de ADR-007) | F0 |
| 9 | `response_model` Pydantic en los ~10 endpoints más usados del núcleo | F0 |
| 10 | **Spike PDF→CAD:** 5 planos vectoriales reales, medir qué % de geometría y cotas se extrae. Insumo para D6 | F7 (spike) |

Al final de esas 2 semanas: **F0 al ~70%, cero features nuevas, y un dato duro sobre si PDF→CAD es viable.** Eso es lo que 10 días-persona compran honestamente.

---

*Documento creado 2026-07-27. Estado verificado contra código el mismo día. Próxima revisión: al cerrar F0.*
