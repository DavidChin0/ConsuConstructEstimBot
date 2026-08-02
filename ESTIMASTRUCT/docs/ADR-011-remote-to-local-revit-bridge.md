# ADR-011 (candidato): Puente API remota → agente local para operaciones Revit

> **Estado: PROPUESTA, sin aprobar.** No es canon. `docs/architecture.md` es el estado real del sistema; este documento vive aparte hasta que el Director lo apruebe, momento en el cual su contenido (resumido) se integra a `architecture.md §7` como ADR-011 real y este archivo pasa a histórico.
>
> **Goal de origen:** `goal-20165` (brain.goals, consuconstruct). **Problema separado de** `goal-20163`/`goal-20164` (esos resuelven consolidación de `PipeClient` y el principio de que `revit-mcp-stdio` es dependencia de instalación local — no un servicio remoto compartido). Este documento asume ese principio como restricción dura, no lo reabre.

---

## 1. Problema

CASE-SAAS-001 (`docs/architecture.md` ADR-007/008/009/010) mueve EstimaStruct a un modelo multi-tenant con una API remota/cloud. Esa API, en su superficie pública v1 (ADR-010, Fase F4), es **solo lectura + cálculo dry-run** — explícitamente no expone las 3 tools de escritura del MCP interno porque "el servidor no exige aprobación por sí mismo, garantía que hoy pone el cliente MCP local".

Pero hay una categoría de operación que la API remota necesitará ofrecer tarde o temprano (ejemplo canónico: "dibujar desde DB" — instanciar geometría en un modelo Revit vivo a partir de datos del presupuesto) que **solo puede ejecutarse en la máquina del cliente**, porque:

- Revit corre ahí, no en AWS.
- `revit-mcp-stdio` habla con Revit vía Named Pipe de Windows (`\\.\pipe\revit-mcp`), un mecanismo de IPC local que no cruza red (goal-20164, confirmado).
- Convertir ese pipe en un servicio remoto compartido violaría el principio ya asentado: cada cliente instala y corre su propio `revit-mcp-stdio`; no hay un pipe "de EstimaStruct SaaS" al que múltiples tenants apunten.

Hoy no existe mecanismo para que una petición que llega a la API remota (`FastAPI ECS/Lambda` según ADR-009) alcance el agente local del tenant correcto sin proxyar la conexión directo — lo cual reintroduciría exactamente el pipe compartido que el principio prohíbe (un backend remoto no puede abrir un socket hacia `127.0.0.1:8001` de la laptop de un cliente; solo el cliente puede iniciar esa conexión).

## 2. Restricciones duras (heredadas, no negociables aquí)

1. **No pipe compartido.** Ningún componente remoto abre conexión entrante hacia la máquina del cliente. Toda conexión la inicia el agente local (outbound-only), igual que hoy `mcp_http.py` solo hace `httpx.get`/`post` saliente hacia `127.0.0.1:8001` — nunca al revés.
2. **No ejecución de código arbitrario disparada por un tercero remoto.** La superficie pública MCP v1 (ADR-010) ya estableció esto para lectura; aquí aplica con más fuerza porque hablamos de escritura real en un modelo BIM del cliente.
3. **Aislamiento multi-tenant.** Cualquier job debe estar scopeado a un `tenant_id` y no debe ser visible ni ejecutable por el agente local de otro tenant.
4. **Degradación explícita, no fallo silencioso** — mismo principio que goal-20164 punto (2): si el agente local no está disponible, el usuario recibe un mensaje claro y accionable, no un timeout genérico.

## 3. Propuesta: job queue + polling del agente local

### 3.1 Arquitectura

```
Cliente MCP remoto / usuario SaaS
        │  POST /jobs  {tenant_id, tool, args}      (HTTP, API remota)
        ▼
┌───────────────────────────────┐
│  API remota (FastAPI ECS)     │
│  tabla `remote_job`           │
│  (Postgres RDS, ADR-009)      │
└───────────────┬───────────────┘
                │  el job queda en estado 'pending', NO se ejecuta acá
                │
        (agente local hace polling, conexión saliente)
                │
┌───────────────▼───────────────┐
│ Agente local (máquina cliente)│
│ EstimaStruct local + revit-mcp│
│ -stdio ya instalados          │
│ GET /jobs/next?tenant_id=...  │
│ (Bearer: agent_token)         │
└───────────────┬───────────────┘
                │ ejecuta vía PipeClient / revit-mcp-stdio (LOCAL, sin cambios)
                ▼
        Named Pipe → Revit.exe
                │
                │ POST /jobs/{id}/result  {status, output}
                ▼
        API remota marca job 'done'/'failed', usuario ve resultado
```

`remote_job` (tabla nueva en el esquema de la API remota, RDS):

| campo | tipo | notas |
|---|---|---|
| `id` | UUID | PK |
| `tenant_id` | UUID FK | scoping multi-tenant (mismo modelo de F1, ADR roadmap) |
| `tool` | text | **de un allowlist fijo**, nunca código libre (ver §4) |
| `args` | jsonb | argumentos tipados, validados con Pydantic antes de encolar |
| `status` | enum | `pending` → `claimed` → `done`\|`failed`\|`expired`\|`cancelled` (ver §3.4 y §5) |
| `created_at`, `claimed_at`, `completed_at` | timestamp | para métricas y timeout |
| `result` | jsonb | salida del agente local |
| `error` | text | si falla |

### 3.2 Ciclo de vida del job

1. Usuario en la UI/API remota pide una operación que necesita Revit (ej. "dibujar desde DB" para la obra X).
2. API remota valida `args` contra el schema Pydantic de esa `tool` (mismo patrón que `PartidaIn`/`RevitQIn` hoy en `backend/`), inserta `remote_job` en estado `pending`.
3. Responde al usuario de inmediato con `job_id` y estado (no bloquea el request HTTP esperando a Revit — Revit puede tardar segundos a minutos).
4. El **agente local** (proceso ya corriendo en la máquina del cliente — candidato natural: extender `backend/services/mcp_http.py` o un daemon hermano que ya sabe hablar con `revit-mcp-stdio`) hace **long-polling** cada N segundos: `GET /jobs/next?tenant_id=<el suyo>` con su `agent_token`.
5. Si hay un job `pending` para ese tenant, la API lo marca `claimed` (con `claimed_at`) y se lo entrega. El agente local lo ejecuta contra el pipe local (reusa el `PipeClient` consolidado de goal-20163, sin tocar esa capa).
6. Agente local hace `POST /jobs/{id}/result` con el resultado. API marca `done`/`failed`.
7. La UI/frontend consulta `GET /jobs/{id}` (polling corto desde el navegador, o el mismo canal que ya usa la app) hasta ver estado terminal.
8. **Ver §3.4:** en cualquier momento antes de `done`/`failed`, el caller original puede cancelar explícitamente el job — no depende de que expire por timeout.

### 3.3 Frecuencia de polling y latencia

- Polling cada 2-5s es razonable para una operación "dibujar desde DB" (no es tiempo real; el usuario ya espera segundos/minutos en Revit real). Long-polling (esperar hasta 20-30s en el `GET /jobs/next` si no hay job, en vez de responder vacío de inmediato) reduce el número de requests sin necesitar WebSocket.
- **Quién banca el polling:** el agente local, no la API. Es un proceso que ya corre en la máquina del cliente (hoy `mcp_http.py` ya gestiona un subprocess local); el costo es una conexión HTTP saliente periódica, no cómputo. La API remota banca el almacenamiento de la tabla `remote_job` (barata, filas efímeras).

### 3.4 Cancelación explícita (`cancelled`, distinto de `expired`)

El timeout/`expired` del §5 cubre el caso **pasivo**: nadie avisa nada, el job simplemente nunca se reclama o nunca reporta resultado, y el sistema lo descubre solo al vencer un plazo. Pero hay un caso **activo**, y más frecuente de lo que parece: el caller remoto aborta su lado (usuario cierra la pestaña, su cliente HTTP hace timeout, cambia de opinión y cancela desde la UI) mientras el job sigue vivo del lado del agente local. Sin una señal explícita, el agente local no tiene forma de enterarse de que ya nadie espera ese resultado.

Esto importa más de lo que parece a primera vista porque **`revit-mcp-stdio` es single-connection** — un solo pipe (`\\.\pipe\revit-mcp`), uso local exclusivo (`docs/architecture.md §2.2/§8.1`). Un job zombie no solo desperdicia trabajo: **bloquea el único canal hacia Revit** hasta que expire por timeout pasivo, impidiendo mientras tanto cualquier operación real que el usuario quiera hacer contra Revit — incluso desde la propia UI local, no solo otro job remoto en cola.

**Estado nuevo:** `cancelled`, agregado al enum de `remote_job.status` (§3.1) junto a `pending`/`claimed`/`done`/`failed`/`expired`. Es conceptualmente distinto de `expired`: `cancelled` = señal activa del caller ("ya no quiero esto"); `expired` = timeout pasivo ("algo salió mal, nadie respondió"). Un mismo job no debería terminar en ambos — si la cancelación llega a tiempo, le gana la carrera al timeout y el job nunca llega a evaluarse contra el plazo de `expired`.

**Endpoint: `POST /jobs/{id}/cancel`**

- **Quién puede cancelar:** únicamente el `tenant_id` (vía su `agent_token` o su sesión de usuario autenticada) que **creó** ese job — mismo scoping de tenant que ya aplica a `/jobs/next` y `/jobs/{id}/result` (§4, punto 2: "la API remota rechaza cualquier `remote_job` cuyo `tenant_id` no coincida con el del token"). La API valida `remote_job.tenant_id == token.tenant_id` antes de aceptar la cancelación; no hace falta un token nuevo, reusa el mismo mecanismo de auth del resto del flujo. Un tenant no puede cancelar (ni ver) jobs de otro tenant.
- **Transiciones válidas:**
  - `pending → cancelled`: caso simple — el agente local todavía ni lo reclamó. La API lo marca `cancelled`; el próximo `GET /jobs/next` del agente ya no lo entrega.
  - `claimed → cancelled`: el agente ya se lo llevó pero puede no haber tocado el pipe todavía. La API lo marca `cancelled` en su tabla; el agente se entera en su próximo chequeo de estado y aborta antes de invocar el pipe si aún no lo hizo (ver mecanismo abajo).
  - `done` / `failed` / `expired` → `cancelar` es no-op: la API responde 409 con el estado real ("el job ya terminó: `<status>`"). No tiene sentido cancelar algo que ya resolvió.

**Qué hace el agente local si YA está ejecutando el job contra el pipe cuando llega la cancelación** — el punto delicado, sin maquillar la limitación real:

1. **Antes de invocar el pipe:** el polling loop del agente local chequea el estado del job (mismo `GET /jobs/{id}`, o el campo viene incluido en la respuesta de `/jobs/next`) inmediatamente antes de ejecutar. Si ya está `cancelled`, no lo ejecuta — costo cero.
2. **Durante la ejecución, cuando la operación lo permite:** para operaciones no-transaccionales que procesan varios pasos (ej. un loop que instancia N elementos uno por uno vía `execute_revit_code`), el agente local puede chequear el estado del job **entre pasos** y abortar el resto del loop si detecta `cancelled` a mitad de camino — libera el pipe antes de terminar todo el batch, no espera a procesar los N elementos completos.
3. **Limitación real cuando NO se puede interrumpir:** si la operación ya entró a una transacción de Revit (`Transaction.Start()`, que es como `execute_revit_code` envuelve las escrituras hoy — goal-20163: "execute_revit_code ya envuelve transacción, no anidar"), **esa transacción puntual no se puede abortar a mitad** sin arriesgar corromper el documento Revit. La API de Revit no expone cancelación granular dentro de una transacción abierta; lo único seguro es dejarla terminar (`Commit` o `RollBack` completo). En ese caso el agente local **no aborta la escritura en curso**, pero sí hace lo que sí está en su control: en cuanto esa transacción puntual termina, libera el pipe **de inmediato** y descarta el resultado — si el job ya quedó `cancelled` mientras tanto, el agente simplemente no hace `POST /jobs/{id}/result` (nadie escucha ya) y queda libre para el siguiente job o para una operación real del usuario contra Revit. No espera al timeout de `expired` para soltar el pipe.
4. **Garantía real, resumida:** cancelar un job `pending` o `claimed`-sin-tocar-el-pipe es inmediato y limpio. Cancelar un job `claimed`-ejecutando-transacción-Revit no aborta esa escritura puntual (limitación de la API de Revit, no de este diseño) — pero acota el bloqueo del pipe al tiempo que falta para que esa transacción puntual termine, nunca al timeout completo de `expired`.

## 4. Seguridad: cómo el agente local valida que el job es legítimo

Este es el punto que ADR-010 ya identificó como el riesgo real ("el servidor no exige aprobación por sí mismo"). Tres capas:

1. **Allowlist de `tool`, no ejecución de código.** El agente local **nunca** ejecuta un `job.args` como IronPython arbitrario. Solo reconoce un catálogo fijo de operaciones con nombre y schema propios (ej. `dibujar_desde_db`, `import_quantities`, `sync_type_marks`) — el mismo patrón que ya separa "12 tools" del MCP interno de "código libre" (`execute_ironpython` existe hoy pero es una tool interna de desarrollo, no algo que un job remoto debería poder invocar). Si `job.tool` no está en el allowlist del agente local, se rechaza y se marca `failed` con motivo explícito — el agente local decide qué corre, no la API.
2. **Autenticación del agente, no solo del usuario.** Cada instalación local tiene su propio `agent_token` (emitido una vez al configurar el enlace SaaS↔instalación local, análogo a las API keys por tenant de ADR-010 F4). El agente se autentica con ese token al hacer polling — un tercero no puede inyectar jobs directamente al pipe del cliente sin ese token, y el token identifica inequívocamente a qué `tenant_id` pertenece ese agente (defensa adicional: la API remota rechaza cualquier `remote_job` cuyo `tenant_id` no coincida con el del token que hace polling — doble scoping, mismo patrón de RLS que F1 del roadmap).
3. **Confirmación humana para escritura destructiva, igual que hoy.** Operaciones que modifican el modelo Revit del cliente (como "dibujar desde DB") deberían requerir que el usuario vea y confirme el job *desde la propia UI local* antes de que el agente lo ejecute contra el pipe — no ejecución automática ciega apenas llega. Esto preserva el gate que hoy pone "el cliente MCP local" (ADR-010) también para el flujo remoto: el agente local puede mostrar "tenés un job pendiente: dibujar 12 elementos en obra X — ¿ejecutar?" antes de tocar el pipe. Para operaciones de solo lectura (ej. `get_revit_status`) no hace falta ese gate.

No se propone ejecución de código arbitrario remoto en ningún escenario — ni siquiera detrás de auth. El allowlist es la barrera de diseño, no una config opcional.

## 5. Qué pasa si el agente local está offline — `expired` (timeout, pasivo) vs `cancelled` (voluntario, activo)

Estos dos estados terminales se parecen (ninguno termina en `done`/`failed`) pero significan cosas distintas y la UI debe mostrarlos distinto — mezclarlos oculta información real al usuario y al Director cuando audite jobs fallidos.

**`expired` — timeout pasivo, algo salió mal (agente offline, colgado, o nunca instalado):**

- `remote_job` lleva un timeout (ej. `created_at + 5 min` sin pasar a `claimed`, o `claimed_at + N min` sin `result`) tras el cual un job worker (o un check perezoso al consultar `GET /jobs/{id}`) lo marca `expired`.
- Significa: **nadie del lado local respondió** — el agente puede estar apagado, la máquina del cliente offline, `revit-mcp-stdio` caído, o Revit colgado a mitad de una operación que nunca reportó.
- La UI, al ver `expired`, muestra un mensaje explícito y accionable: *"Tu agente local no respondió. Verificá que EstimaStruct esté corriendo en tu computadora (`START_POSTGRES_UNICA.ps1`) y que Revit esté abierto, luego reintentá."* — no un spinner infinito ni un error 500 genérico. Mismo espíritu que goal-20164 punto (2): degradación visible con sugerencia de acción, nunca fallo silencioso.
- El usuario puede reintentar el mismo job (nuevo `POST /jobs` o un botón "reintentar" que reencola) una vez su agente esté arriba.
- No hay reintento automático indefinido del lado servidor — evita acumular jobs zombis por tenants con el agente apagado permanentemente (ej. cliente que solo usa el SaaS para ver reportes, nunca instaló el agente local).

**`cancelled` — señal activa del propio caller, nada salió mal (§3.4):**

- Significa: **el usuario/caller decidió abortar** — cerró la pestaña, su cliente HTTP hizo timeout, cambió de opinión desde la UI. El agente local sigue vivo y respondiendo; no hay nada que diagnosticar del lado de conectividad.
- La UI, al ver `cancelled`, muestra un mensaje neutro, sin sugerir ningún troubleshooting: *"Operación cancelada."* — no el mismo texto de `expired`, porque no hay ningún paso de "verificá tu agente" que aplique aquí. Confundir ambos mensajes le haría perder tiempo al usuario revisando una conexión que nunca falló.
- No aplica reintento automático ni sugerido por defecto — si el usuario canceló a propósito, reintentar debe ser una acción nueva y deliberada (nuevo botón/click), no una oferta automática como en `expired`.
- Para auditoría/soporte (ej. si el Director revisa jobs fallidos de un tenant), `cancelled` no debería contar como incidente ni disparar alertas — es tráfico normal de un flujo interactivo. `expired`, en cambio, si se acumula para un mismo tenant, sí es señal de que su agente local tiene un problema real y vale la pena investigar (o contactarlo).

## 6. Alternativa descartada: proxy directo / túnel persistente (WebSocket o reverse-tunnel tipo ngrok)

**Propuesta descartada:** en vez de una tabla de jobs con polling, el agente local abre una conexión persistente (WebSocket o túnel reverse-proxy) hacia la API remota al arrancar, y la API remota reenvía requests en vivo por ese canal — efectivamente convirtiendo la conexión en un "pipe remoto" de baja latencia.

**Por qué se descarta:**

1. **Es, en espíritu, el mismo pipe compartido que el principio ya prohibió.** Aunque la conexión la abre el cliente (outbound), el resultado operacional es un canal remoto persistente y con estado que la API puede usar para invocar Revit del cliente en cualquier momento — exactamente la forma que goal-20164 descartó para el problema local. Mantener el límite de diseño nítido (job efímero + polling, sin canal vivo) es más defendible ante una auditoría de seguridad que "sí hay un túnel, pero técnicamente lo abrió el cliente".
2. **Estado de conexión por tenant a escala.** Un WebSocket persistente por instalación cliente obliga a la API remota (ECS Fargate, ADR-009) a mantener conexiones vivas, reconectar, y enrutar mensajes al socket correcto — complejidad operacional (sticky sessions, balanceo, reconexión tras deploy) que no existe con una tabla Postgres + polling stateless. Con `remote_job` en RDS, cualquier instancia ECS puede atender cualquier request; no hay afinidad de conexión que romper en cada deploy.
3. **Latencia no es el requisito real.** "Dibujar desde DB" no es una operación de UI en tiempo real — el usuario ya tolera segundos/minutos mientras Revit procesa. El polling de 2-5s (o long-polling de hasta 30s) es indistinguible en experiencia de un canal instantáneo para este caso de uso. Pagar la complejidad de un túnel persistente por una ganancia de latencia que el usuario no percibe no se justifica en esta fase.
4. **Reusa infraestructura ya construida.** No hay pieza de "job queue" o "webhook" existente en el repo (verificado: `grep -i "job_queue\|webhook\|poll"` en `ESTIMASTRUCT/` no devuelve infraestructura de colas, solo menciones sueltas en `CHANGELOG.md`, `ERROR_HANDLING_GUIDE.md` y vendored KaTeX). Una tabla Postgres + 2 endpoints (`/jobs`, `/jobs/next`, `/jobs/{id}/result`) es la pieza más simple compatible con el stack ya declarado (RDS Postgres, FastAPI) — no introduce Redis/Celery/SQS nuevo solo para este flujo. Si el volumen de jobs creciera mucho, migrar de "tabla + polling" a SQS + notificación es un cambio incremental sobre el mismo modelo de datos, no una reescritura.

## 7. Qué NO resuelve este documento (fuera de scope)

- El mecanismo de emisión/rotación de `agent_token` en detalle (se apoya en el mismo trabajo de API keys por tenant de ADR-010 F4 — no se duplica aquí).
- La UI de confirmación local del §4.3 (mockup, dónde vive el botón) — es implementación, no arquitectura.
- Si el "agente local" es un proceso nuevo o una extensión de `backend/services/mcp_http.py` — decisión de implementación a tomar cuando esto se apruebe, probablemente lo segundo dado que ya gestiona el ciclo de vida del subprocess `revit-mcp-stdio`.
- Billing/cuota por job remoto (heredaría el rate limiting por tenant de F1, no se re-diseña acá).

## 8. Verificación hecha antes de escribir esto

- `docs/architecture.md` completo leído (396 líneas) — ADR-001 real de este repo es "Postgres primario, SQLite compat", **no** el mismo "ADR-001" que goal-20163/20164 usan como shorthand para "revit-mcp-stdio es dependencia local". Son dos cosas distintas con el mismo número por casualidad de fuentes distintas (brain.goals vs. `docs/architecture.md`) — este documento no corrige esa numeración, solo la señala para que no se confunda al leer ambas fuentes.
- `docs/roadmap_case_saas_001_scope_v2.md` leído (secciones F1/F2/F4) — confirma que la superficie MCP pública v1 es solo-lectura + dry-run, y que F4 depende duro de F1 (auth/tenancy) + F2 (deploy). Este ADR-011 asume que F1/F2/F4 ya existen o se construyen en paralelo — el job queue no reemplaza esas fases, se monta sobre ellas (mismo `tenant_id`, mismo `agent_token`-por-tenant que las API keys de F4).
- `grep -i "job_queue|webhook|poll"` sobre todo el repo `ESTIMASTRUCT/` — sin resultado de infraestructura reusable (solo hits triviales en CHANGELOG, guía de manejo de errores y KaTeX vendorizado). No hay pieza existente que reusar; la tabla `remote_job` es diseño nuevo, no reinvención de algo que ya estaba.
- `backend/services/mcp_http.py` leído completo — confirma que el agente local de hoy ya es outbound-only (`httpx.get/post` hacia `127.0.0.1:8001`), patrón que este ADR extiende sin romper: el agente local seguiría siendo el único que abre conexiones, ahora también hacia la API remota para polling.

---

*Documento candidato, `goal-20165`. Redactado 2026-08-02. Revisado 2026-08-02: agregado mecanismo de cancelación explícita (§3.4) a pedido del Director — ver §5 para la distinción `cancelled` vs `expired`. Pendiente: sesión de arquitectura con el Director para aprobar/rechazar antes de integrar a `docs/architecture.md`.*
