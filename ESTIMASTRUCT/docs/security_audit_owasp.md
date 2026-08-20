# Auditoría OWASP obligatoria pre-deploy — EstimaStruct SaaS

> **Mandato P0 estratégico** (identity.md, confirmado 2026-07-21): **ningún deploy de
> producción del SaaS sale sin pasar la auditoría OWASP Top 10.** No es recomendación;
> es gate. Este documento define el mandato, el mecanismo y el estado base.
>
> **Rol del documento:** política + contrato de auditoría. El estado técnico manda desde
> `docs/architecture.md`; el plan fasado desde `docs/roadmap_case_saas_001_scope_v2.md`
> (la auditoría OWASP es el "Frente 7" del scope original, absorbido en **F1 — Seguridad
> y multi-tenancy**). Origen del requisito: F1, tabla de entregables, "Auditoría OWASP
> Top 10 — MVP".

---

## 1. El gate

**Script:** `backend/scripts_runner/security_audit_owasp.py`
**Corrida canónica:**

```
D:\LLM\python\python.exe -m backend.scripts_runner.security_audit_owasp
```

- `--json` → salida máquina (para CI).
- `--allow-high` → solo aborta por BLOCKER (para desbloquear temporalmente un HIGH ya
  aceptado por escrito; **los BLOCKER siempre abortan**).
- **Exit 0** = sin hallazgos bloqueantes. **Exit 2** = hay BLOCKER (o HIGH sin
  `--allow-high`) → **no desplegar**.

**Diseño deliberado:**

- **stdlib-only.** No agrega ninguna dependencia al runtime. `bandit` y `pip-audit` se
  corren **solo si ya están instalados** en el runner (dev-only); si faltan, degradan a
  `WARN`, no rompen el gate.
- Chequeos estáticos mapeados a **OWASP Top 10 (2021)**, verificados contra el árbol real
  de `backend/`, no contra supuestos.
- El propio script se auto-excluye del escaneo (sus literales de regex matchearían los
  patrones y enmascararían el A01 real).

## 2. Dónde se engancha

| Momento | Hoy (sin AWS) | Cuando exista F2 (CI/CD AWS) |
|---|---|---|
| Antes de exponer la API fuera de loopback | Corrida manual, obligatoria | — |
| Pipeline de deploy | — | Paso **antes** de `alembic upgrade head` + deploy. Exit≠0 aborta el pipeline |

Secuencia del deploy con el gate (F2):

```
build → tests (F0) → security_audit_owasp (exit 0) → alembic upgrade head → deploy
                          │
                          └─ exit 2 ⇒ pipeline abortado, deploy cancelado
```

## 3. Estado base — 2026-08-04 (corrida real del gate)

Es **esperado que hoy salga ROJO**: F1 aún no arranca. El gate no arregla nada — hace el
hueco imposible de ignorar en cada deploy.

| OWASP | Sev | Hallazgo | Cierra en |
|---|---|---|---|
| A01:2021 | **BLOCKER** | Sin control de acceso en ningún endpoint (0/144 auth, sin `tenant_id`) | F1 — auth JWT + tenancy |
| A05:2021 | **BLOCKER** | CORS `allow_origins=["*"]` (`backend/main.py:28`) | F1 — allowlist por entorno |
| A02:2021 | HIGH | Secretos leídos de texto plano (`D:\Secrets\*.txt` en varios `scripts_runner/`) | F1 — secrets manager + rotación |
| A04:2021 | HIGH | Sin rate limiting en toda la API | F1 — rate limit por tenant/endpoint |
| A05:2021 | WARN | `Base.metadata.create_all` (auto-schema salta Alembic) | F0 — `AUTO_CREATE_SCHEMA=false` en prod |
| A06:2021 | WARN | `pip-audit` no instalado en el runner | F0/F2 — instalar dev-only en CI |
| SAST | WARN | `bandit` no instalado en el runner | F0/F2 — instalar dev-only en CI |
| A03:2021 | PASS | Sin SQL interpolado evidente (ORM SQLAlchemy) | — |
| A09:2021 | PASS | Existe canal de logging/notificación | — |

> Los dos BLOCKER + dos HIGH son exactamente los riesgos **R2** (data breach multi-tenant),
> **R7** (costo variable sin techo) y la deuda de secretos declarados en el roadmap §F1/§7.
> El gate no descubre nada nuevo — **codifica** lo ya sabido en algo que corre en cada deploy.

## 4. Definición de "verde"

El gate pasa (exit 0) cuando, para producción:

1. **A01** — toda ruta que devuelve datos de obra exige auth y filtra por `tenant_id`
   (dependency de FastAPI + RLS en Postgres como segunda barrera).
2. **A05** — `allow_origins` es una allowlist configurable, no `["*"]`;
   `ESTIMASTRUCT_AUTO_CREATE_SCHEMA=false`; sin `--reload`.
3. **A02** — cero secretos en código/archivos planos; todo desde secrets manager.
4. **A04** — rate limiting activo por tenant y por endpoint.
5. **A06 / SAST** — `pip-audit` y `bandit` instalados en CI y sin hallazgos medium/high.

Mientras cualquiera de esos siga rojo, **el deploy de producción está bloqueado por
política, no por olvido.**

## 5. Mantenimiento del gate

- Cada endpoint nuevo hereda el requisito de auth/tenancy: si se agrega una ruta sin
  dependency de autorización una vez que F1 aterrice, A01 volverá a BLOCKER. Correcto.
- Al agregar un chequeo nuevo: una función `check_*` que devuelve `Finding`, registrada en
  `run_all_checks()`. Mantener stdlib-only.
- No suprimir un BLOCKER con `--allow-high` — ese flag solo aplica a HIGH, y su uso debe
  quedar registrado con autorización explícita del Director.

---

*Creado 2026-08-04 (goal #20348, rol estimastruct). Estado base verificado con corrida real
del gate el mismo día. Próxima revisión: al cerrar F1.*
