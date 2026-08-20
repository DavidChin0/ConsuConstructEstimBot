"""
OWASP Top-10 pre-deploy security gate — EstimaStruct SaaS.

P0 estrategico (identity.md, confirmado 2026-07-21): NINGUN deploy de produccion
del SaaS sale sin pasar esta auditoria. Este script ES el gate: lo corre CI/CD
antes de `alembic upgrade head` + deploy (F2 del roadmap CASE-SAAS-001). Hoy, sin
pipeline AWS todavia, se corre a mano antes de exponer la API a cualquier red que
no sea loopback.

Diseno:
  - stdlib-only. No agrega dependencias al runtime (bandit / pip-audit se usan SOLO
    si ya estan instalados; su ausencia degrada a WARN, no rompe el import).
  - Chequeos estaticos mapeados a OWASP Top 10 (2021), verificados contra el arbol
    real de `backend/`, no contra supuestos.
  - Severidades: BLOCKER (aborta el deploy), HIGH (aborta salvo --allow-high),
    WARN (informativo, no aborta), PASS (limpio).

Uso:
    D:\\LLM\\python\\python.exe -m backend.scripts_runner.security_audit_owasp
    D:\\LLM\\python\\python.exe -m backend.scripts_runner.security_audit_owasp --json
    D:\\LLM\\python\\python.exe -m backend.scripts_runner.security_audit_owasp --allow-high

Exit codes:
    0  sin hallazgos que bloqueen (puede haber WARN)
    2  hay al menos un BLOCKER (o HIGH sin --allow-high) -> NO desplegar

Estado base conocido al crear este gate (2026-08-04, roadmap CASE-SAAS-001 s2/sF1):
    0/144 endpoints con auth . CORS ["*"] . secretos en texto plano . sin rate limit.
    Es ESPERADO que este script salga ROJO hoy: F1 (Seguridad y multi-tenancy) aun no
    arranca. El gate no "arregla" nada -- hace que el hueco sea IMPOSIBLE de ignorar en
    cada deploy. Verde solo cuando F1 cierre.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from importlib import util as importlib_util
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent          # .../ESTIMASTRUCT/backend
PROJECT = BACKEND.parent                                   # .../ESTIMASTRUCT

BLOCKER, HIGH, WARN, PASS = "BLOCKER", "HIGH", "WARN", "PASS"
_ABORTING = {BLOCKER, HIGH}
_SEV_ORDER = {BLOCKER: 0, HIGH: 1, WARN: 2, PASS: 3}

# Directorios de fuente Python a escanear (relativos a backend/).
_SRC_DIRS = ["routers", "services", "mcp_server", "scripts_runner"]
# Archivos sueltos en la raiz de backend/ que importan al gate.
_ROOT_FILES = ["main.py", "config.py", "db.py"]


@dataclass
class Finding:
    owasp: str        # p.ej. "A01:2021"
    severity: str
    title: str
    detail: str = ""
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "owasp": self.owasp,
            "severity": self.severity,
            "title": self.title,
            "detail": self.detail,
            "evidence": self.evidence,
        }


# --------------------------------------------------------------------------- #
# Utilidades de escaneo                                                        #
# --------------------------------------------------------------------------- #

_SELF = Path(__file__).resolve()


def _py_files() -> list[Path]:
    # El propio gate se auto-excluye: sus literales de regex (allow_origins=['*'],
    # HTTPBearer, D:\Secrets, ...) matchearian los patrones y producirian PASS/HIT
    # falsos — en particular enmascararian el A01 real (0 endpoints con auth).
    files: list[Path] = []
    for d in _SRC_DIRS:
        p = BACKEND / d
        if p.is_dir():
            files.extend(sorted(q for q in p.rglob("*.py") if q.resolve() != _SELF))
    for f in _ROOT_FILES:
        p = BACKEND / f
        if p.is_file():
            files.append(p)
    return files


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _rel(p: Path) -> str:
    try:
        return str(p.relative_to(PROJECT)).replace("\\", "/")
    except ValueError:
        return str(p)


def _grep(files: list[Path], pattern: re.Pattern, cap: int = 12) -> list[str]:
    """Devuelve hasta `cap` hits 'path:line: texto' para un patron compilado."""
    hits: list[str] = []
    for f in files:
        for i, line in enumerate(_read(f).splitlines(), start=1):
            if pattern.search(line):
                hits.append(f"{_rel(f)}:{i}: {line.strip()[:160]}")
                if len(hits) >= cap:
                    return hits
    return hits


# --------------------------------------------------------------------------- #
# Chequeos OWASP. Cada uno devuelve uno o mas Finding (PASS si esta limpio).   #
# --------------------------------------------------------------------------- #

def check_a01_access_control(files: list[Path]) -> Finding:
    """A01 — Broken Access Control: hay CUALQUIER dependency de autorizacion?"""
    auth_pat = re.compile(
        r"HTTPBearer|OAuth2|Security\(|Depends\(\s*(get_current_user|require_|verify_|"
        r"auth|current_tenant|get_tenant)", re.IGNORECASE)
    hits = _grep(files, auth_pat)
    if not hits:
        tenant_hits = _grep(files, re.compile(r"\btenant_id\b"), cap=1)
        extra = [] if tenant_hits else ["Tampoco existe columna/filtro tenant_id: sin aislamiento por tenant."]
        return Finding(
            "A01:2021", BLOCKER, "Sin control de acceso en NINGUN endpoint",
            "No se encontro ninguna dependency de auth/autorizacion (HTTPBearer, OAuth2, "
            "get_current_user, require_*, current_tenant). La API entera es anonima: "
            "GET /presupuestos devuelve TODAS las obras de la BD. En multi-tenant esto es "
            "un data breach el dia 1 (R2 del roadmap). Bloquea F2/AWS.", extra)
    return Finding("A01:2021", PASS, "Control de acceso presente", evidence=hits[:4])


def check_a02_crypto_secrets(files: list[Path]) -> Finding:
    """A02 — Cryptographic Failures: secretos hardcodeados o leidos de texto plano."""
    secret_pat = re.compile(
        r"(sb_secret_[A-Za-z0-9]|D:\\+Secrets|password\s*=\s*[\"'][^\"']+[\"']|"
        r"SECRET_KEY\s*=\s*[\"'][^\"']+[\"']|api_key\s*=\s*[\"'][A-Za-z0-9]{12})",
        re.IGNORECASE)
    hits = _grep(files, secret_pat)
    if hits:
        return Finding(
            "A02:2021", HIGH, "Secretos en texto plano / hardcodeados en el codigo",
            "Credenciales embebidas o leidas de archivos planos (D:\\Secrets\\*.txt). En "
            "produccion deben venir de un secrets manager (F1). Rotar cualquier credencial "
            "que haya tocado git.", hits)
    return Finding("A02:2021", PASS, "Sin secretos hardcodeados detectados")


def check_a03_injection(files: list[Path]) -> Finding:
    """A03 — Injection: SQL construido con f-string / % / .format en vez de params."""
    inj_pat = re.compile(
        r"(execute\(\s*f[\"']|text\(\s*f[\"']|execute\([^)]*%\s)", re.IGNORECASE)
    hits = _grep(files, inj_pat)
    if hits:
        return Finding(
            "A03:2021", HIGH, "Posible SQL injection (SQL interpolado, no parametrizado)",
            "Consultas con f-string/% en execute()/text() en vez de parametros ligados. "
            "Revisar cada hit; usar parametros de SQLAlchemy/psycopg.", hits)
    return Finding("A03:2021", PASS, "Sin patrones evidentes de SQL interpolado")


def check_a05_misconfig(files: list[Path]) -> list[Finding]:
    """A05 — Security Misconfiguration: CORS *, reload/debug, AUTO_CREATE en prod."""
    out: list[Finding] = []

    cors = _grep(files, re.compile(r"allow_origins\s*=\s*\[\s*[\"']\*[\"']"))
    if cors:
        out.append(Finding(
            "A05:2021", BLOCKER, "CORS abierto a cualquier origen (allow_origins=['*'])",
            "Con credenciales/tokens permite que cualquier sitio invoque la API en nombre "
            "del usuario. Reemplazar por allowlist configurable por entorno (F1).", cors))
    else:
        out.append(Finding("A05:2021", PASS, "CORS no esta en wildcard"))

    debug = _grep(files, re.compile(r"debug\s*=\s*True|reload\s*=\s*True"))
    if debug:
        out.append(Finding(
            "A05:2021", WARN, "Modo debug/reload activado en codigo",
            "debug/reload expone stack traces y recarga codigo: nunca en produccion. "
            "Confirmar que el arranque de prod NO usa --reload.", debug))

    autoc = _grep(files, re.compile(r"create_all\("))
    if autoc:
        out.append(Finding(
            "A05:2021", WARN, "Base.metadata.create_all presente (schema auto-creado)",
            "AUTO_CREATE_SCHEMA salta el historial Alembic. En prod el schema debe venir "
            "solo de `alembic upgrade head` (R3 del roadmap). Verificar que "
            "ESTIMASTRUCT_AUTO_CREATE_SCHEMA=false en produccion.", autoc))
    return out


def check_a04_rate_limit(files: list[Path]) -> Finding:
    """A04 — Insecure Design: ausencia de rate limiting es un defecto de diseno."""
    rl_pat = re.compile(r"slowapi|Limiter|rate_limit|RateLimit|@limiter", re.IGNORECASE)
    hits = _grep(files, rl_pat)
    if not hits:
        return Finding(
            "A04:2021", HIGH, "Sin rate limiting en toda la API",
            "Ningun limitador (slowapi/Limiter/rate_limit). Prerrequisito de F4 (MCP "
            "publico) y de control de costo LLM/Meshy por tenant (R7). Un cliente puede "
            "quemar el margen o tumbar el servicio.")
    return Finding("A04:2021", PASS, "Rate limiting presente", evidence=hits[:3])


def check_a09_logging(files: list[Path]) -> Finding:
    """A09 — Security Logging Failures: existe algun canal de auditoria/logging?"""
    log_pat = re.compile(r"logging\.|logger\.|notifier|audit_log|structlog", re.IGNORECASE)
    hits = _grep(files, log_pat, cap=3)
    if not hits:
        return Finding(
            "A09:2021", WARN, "Sin logging/auditoria evidente",
            "No se detecto logging estructurado. Un breach sin logs de acceso es invisible. "
            "Exponer diagnostics.py + logs de auth cuando F1 aterrice.")
    return Finding("A09:2021", PASS, "Hay canal de logging/notificacion", evidence=hits)


def check_a06_dependencies() -> Finding:
    """A06 — Vulnerable Components: correr pip-audit si esta instalado."""
    if importlib_util.find_spec("pip_audit") is None:
        return Finding(
            "A06:2021", WARN, "pip-audit no instalado — no se auditaron dependencias",
            "Instalar en el runner de CI (dev-only): `pip install pip-audit`. El gate lo "
            "correra automaticamente cuando este presente. No se agrega al runtime.")
    req = BACKEND / "requirements.txt"
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pip_audit", "-r", str(req), "--strict"],
            capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return Finding("A06:2021", WARN, "pip-audit no pudo ejecutarse", str(exc))
    if proc.returncode != 0:
        tail = (proc.stdout or proc.stderr or "").strip().splitlines()[-12:]
        return Finding(
            "A06:2021", HIGH, "pip-audit reporto dependencias vulnerables",
            "Actualizar/pinnear las versiones afectadas antes de desplegar.", tail)
    return Finding("A06:2021", PASS, "pip-audit sin CVEs conocidos en requirements.txt")


def run_bandit() -> Finding:
    """SAST complementario: bandit si esta instalado (dev-only, no runtime)."""
    if importlib_util.find_spec("bandit") is None:
        return Finding(
            "SAST", WARN, "bandit no instalado — sin analisis estatico de seguridad",
            "Instalar en el runner de CI (dev-only): `pip install bandit`. El gate lo "
            "correra sobre backend/ cuando este presente.")
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "bandit", "-r", str(BACKEND),
             "-ll", "-q", "-x", ",".join(str(BACKEND / d) for d in ("__pycache__", "logs"))],
            capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return Finding("SAST", WARN, "bandit no pudo ejecutarse", str(exc))
    if proc.returncode != 0:
        tail = (proc.stdout or proc.stderr or "").strip().splitlines()[-15:]
        return Finding(
            "SAST", HIGH, "bandit reporto issues de severidad media/alta",
            "Revisar cada issue; suprimir con # nosec solo con justificacion.", tail)
    return Finding("SAST", PASS, "bandit sin issues medium/high")


def run_all_checks() -> list[Finding]:
    files = _py_files()
    findings: list[Finding] = [
        check_a01_access_control(files),
        check_a02_crypto_secrets(files),
        check_a03_injection(files),
        check_a04_rate_limit(files),
    ]
    findings.extend(check_a05_misconfig(files))
    findings.append(check_a09_logging(files))
    findings.append(check_a06_dependencies())
    findings.append(run_bandit())
    findings.sort(key=lambda f: (_SEV_ORDER.get(f.severity, 9), f.owasp))
    return findings


# --------------------------------------------------------------------------- #
# Presentacion                                                                 #
# --------------------------------------------------------------------------- #

def _print_report(findings: list[Finding], scanned: int) -> None:
    counts = {s: sum(1 for f in findings if f.severity == s) for s in (BLOCKER, HIGH, WARN, PASS)}
    print("=" * 72)
    print(" OWASP Top-10 pre-deploy gate — EstimaStruct SaaS")
    print(f" Archivos Python escaneados: {scanned}")
    print("=" * 72)
    for f in findings:
        print(f"\n[{f.severity:7}] {f.owasp}  {f.title}")
        if f.detail:
            print(f"          {f.detail}")
        for ev in f.evidence:
            print(f"            - {ev}")
    print("\n" + "-" * 72)
    print(f" BLOCKER={counts[BLOCKER]}  HIGH={counts[HIGH]}  WARN={counts[WARN]}  PASS={counts[PASS]}")
    print("-" * 72)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="OWASP Top-10 pre-deploy gate para EstimaStruct.")
    ap.add_argument("--json", action="store_true", help="Salida JSON en vez de reporte legible.")
    ap.add_argument("--allow-high", action="store_true",
                    help="No aborta por HIGH (solo BLOCKER). Los BLOCKER siempre abortan.")
    args = ap.parse_args(argv)

    findings = run_all_checks()
    scanned = len(_py_files())

    aborting = {BLOCKER} if args.allow_high else _ABORTING
    fail = any(f.severity in aborting for f in findings)

    if args.json:
        print(json.dumps({
            "gate": "owasp_top10_predeploy",
            "pass": not fail,
            "scanned_files": scanned,
            "findings": [f.to_dict() for f in findings],
        }, ensure_ascii=False, indent=2))
    else:
        _print_report(findings, scanned)
        if fail:
            print("\n RESULTADO: DEPLOY BLOQUEADO. Cerrar los hallazgos BLOCKER/HIGH "
                  "(F1 del roadmap) antes de exponer la API.")
        else:
            print("\n RESULTADO: gate verde. Ningun hallazgo bloqueante.")

    return 2 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
