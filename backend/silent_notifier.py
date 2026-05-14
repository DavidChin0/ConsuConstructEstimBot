"""
Sistema de notificaciones silenciosas — Monitorea errores sin interrumpir flujo
"""
import json
import threading
import time
from pathlib import Path
from typing import Optional, List, Callable
from datetime import datetime, timedelta
from collections import defaultdict

ERROR_LOG = Path(__file__).parent / "logs" / "errors.jsonl"


class SilentNotifier:
    """Monitor de errores con notificaciones asíncronas."""

    def __init__(self, check_interval: int = 30):
        self.check_interval = check_interval
        self.last_check = datetime.utcnow()
        self.error_counts = defaultdict(int)
        self.handlers: List[Callable] = []
        self._monitoring = False

    def subscribe(self, handler: Callable):
        """Registra un handler para notificaciones."""
        self.handlers.append(handler)

    def start_monitoring(self):
        """Inicia monitor en hilo separado (no bloquea)."""
        if self._monitoring:
            return
        self._monitoring = True
        thread = threading.Thread(target=self._monitor_loop, daemon=True)
        thread.start()

    def stop_monitoring(self):
        """Detiene monitor."""
        self._monitoring = False

    def _monitor_loop(self):
        """Loop de monitoreo en background."""
        while self._monitoring:
            try:
                self._check_errors()
            except Exception as e:
                pass
            time.sleep(self.check_interval)

    def _check_errors(self):
        """Lee errores nuevos desde log."""
        if not ERROR_LOG.exists():
            return

        new_errors = []
        try:
            with open(ERROR_LOG, "r") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        error_record = json.loads(line)
                        error_ts = datetime.fromisoformat(error_record["timestamp"])

                        if error_ts > self.last_check:
                            new_errors.append(error_record)
                    except json.JSONDecodeError:
                        pass

            self.last_check = datetime.utcnow()

            for error in new_errors:
                self._dispatch_notification(error)

        except Exception as e:
            pass

    def _dispatch_notification(self, error_record: dict):
        """Envía notificación a handlers registrados."""
        for handler in self.handlers:
            try:
                handler(error_record)
            except Exception:
                pass

    def get_summary(self, minutes: int = 60) -> dict:
        """Retorna resumen de errores recientes."""
        if not ERROR_LOG.exists():
            return {"total": 0, "by_code": {}, "recent": []}

        cutoff = datetime.utcnow() - timedelta(minutes=minutes)
        errors_by_code = defaultdict(int)
        recent_errors = []

        try:
            with open(ERROR_LOG, "r") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        error_record = json.loads(line)
                        error_ts = datetime.fromisoformat(error_record["timestamp"])

                        if error_ts > cutoff:
                            code = error_record.get("error_code", "UNKNOWN")
                            errors_by_code[code] += 1
                            recent_errors.append(error_record)
                    except json.JSONDecodeError:
                        pass

            recent_errors.sort(key=lambda x: x["timestamp"], reverse=True)

            return {
                "total": sum(errors_by_code.values()),
                "by_code": dict(errors_by_code),
                "recent": recent_errors[:10]
            }

        except Exception as e:
            return {"total": 0, "by_code": {}, "recent": [], "error": str(e)}


# Instancia global del notifier
notifier = SilentNotifier(check_interval=30)


def notify_slack(webhook_url: Optional[str] = None):
    """Handler para notificaciones a Slack (placeholder)."""
    def handler(error_record: dict):
        if not webhook_url:
            return
        try:
            import requests
            message = f"❌ {error_record['error_code']}: {error_record['message']}"
            requests.post(webhook_url, json={"text": message}, timeout=5)
        except Exception:
            pass
    return handler


def notify_file(filename: str = "notifications.log"):
    """Handler para notificaciones a archivo."""
    def handler(error_record: dict):
        try:
            log_path = Path(__file__).parent / "logs" / filename
            log_path.parent.mkdir(exist_ok=True)
            with open(log_path, "a") as f:
                f.write(json.dumps(error_record, ensure_ascii=False) + "\n")
        except Exception:
            pass
    return handler


def notify_memory(max_size: int = 100):
    """Handler que mantiene errores en memoria."""
    memory: List[dict] = []

    def handler(error_record: dict):
        memory.append(error_record)
        if len(memory) > max_size:
            memory.pop(0)

    handler.get_memory = lambda: memory
    return handler
