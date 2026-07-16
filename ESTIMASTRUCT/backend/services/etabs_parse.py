import io
import os
from typing import Optional
from openpyxl import load_workbook

def _decode_bytes(raw: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, AttributeError):
            continue
    return raw.decode("utf-8", errors="ignore")

def _es_xlsx(nombre: str, ctype: str, raw: bytes) -> bool:
    n = (nombre or "").lower()
    ct = (ctype or "").lower()
    if n.endswith(".xlsx") or n.endswith(".xlsm"):
        return True
    if "spreadsheetml" in ct or "officedocument" in ct:
        return True
    return bool(raw and raw[:4] == _XLSX_MAGIC)

