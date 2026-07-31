#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
revit_eye_watcher.py

Watcher visual para Autodesk Revit:
- detecta ventana Revit
- captura screenshot de la ventana
- usa Gemini Vision para detectar popups/modales y ubicar el boton objetivo
- opcionalmente mueve el mouse y hace click
- guarda evidencia JSON + PNG en output/revit-eye/runs/

Politica por defecto:
- solo botones no destructivos (`Cancel`, `Close`, `OK`, `Aceptar`, `Cerrar`)
- `--dry-run` por defecto si no se pasa `--click`
"""

from __future__ import annotations

import argparse
import base64
import ctypes
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


SCRIPT_DIR = Path(__file__).resolve().parent
BOT_ROOT = SCRIPT_DIR.parent.parent
OUTPUT_ROOT = BOT_ROOT / "output" / "revit-eye" / "runs"
DEFAULT_WINDOW_HINT = "Autodesk Revit"
DEFAULT_MODEL = "gemini-2.5-flash"
DEFAULT_INTERVAL = 2.0
DEFAULT_COOLDOWN = 6.0
DEFAULT_CONFIRM_HITS = 2
SAFE_LABELS = {
    "cancel", "close", "ok", "aceptar", "cerrar", "continue", "continuar"
}
DESTRUCTIVE_LABELS = {
    "delete", "remove", "detach", "overwrite", "discard", "purge", "unlink"
}


try:
    from google import genai  # type: ignore
except ImportError:
    genai = None

try:
    from PIL import ImageGrab
except ImportError:
    ImageGrab = None

try:
    import mss
    import mss.tools
except ImportError:
    mss = None


user32 = ctypes.windll.user32


@dataclass
class WindowInfo:
    hwnd: int
    title: str
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return max(0, self.right - self.left)

    @property
    def height(self) -> int:
        return max(0, self.bottom - self.top)


def load_gemini_api_key() -> str:
    env_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if env_key:
        return env_key

    secret_path = Path(r"D:\Secrets\GeminiDavidApi.txt")
    if secret_path.exists():
        return secret_path.read_text(encoding="utf-8").strip()

    raise RuntimeError(
        "No GEMINI_API_KEY in env and D:\\Secrets\\GeminiDavidApi.txt not found."
    )


def ensure_output_dir() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = OUTPUT_ROOT / stamp
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def log(msg: str) -> None:
    print(msg, flush=True)


def list_windows() -> List[WindowInfo]:
    windows: List[WindowInfo] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def enum_proc(hwnd, lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value.strip()
        if not title:
            return True
        rect = ctypes.wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        if rect.right <= rect.left or rect.bottom <= rect.top:
            return True
        windows.append(
            WindowInfo(
                hwnd=int(hwnd),
                title=title,
                left=rect.left,
                top=rect.top,
                right=rect.right,
                bottom=rect.bottom,
            )
        )
        return True

    user32.EnumWindows(enum_proc, 0)
    return windows


def find_window(window_hint: str) -> Optional[WindowInfo]:
    hint = window_hint.lower().strip()
    matches = [
        w for w in list_windows()
        if hint in w.title.lower()
    ]
    if not matches:
        return None
    matches.sort(key=lambda w: (w.width * w.height), reverse=True)
    return matches[0]


def activate_window(hwnd: int) -> None:
    user32.ShowWindow(hwnd, 9)
    user32.SetForegroundWindow(hwnd)


def capture_window(window: WindowInfo, output_png: Path) -> bytes:
    if mss is not None:
        with mss.MSS() as sct:
            monitor = {
                "left": window.left,
                "top": window.top,
                "width": window.width,
                "height": window.height,
            }
            shot = sct.grab(monitor)
            png_bytes = mss.tools.to_png(shot.rgb, shot.size)
            output_png.write_bytes(png_bytes)
            return png_bytes

    if ImageGrab is None:
        raise RuntimeError("Need either mss or Pillow.ImageGrab for screenshot capture.")
    image = ImageGrab.grab(bbox=(window.left, window.top, window.right, window.bottom))
    image.save(str(output_png), format="PNG")
    return output_png.read_bytes()


def parse_model_json(raw_text: str) -> Dict[str, Any]:
    text = (raw_text or "").strip()
    if not text:
        raise ValueError("Empty model response")
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:]
    text = text.strip().rstrip("`").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]
    return json.loads(text)


def popup_fingerprint(result: Dict[str, Any], window: WindowInfo) -> str:
    raw = "|".join([
        result.get("issue_type", ""),
        result.get("target_label", ""),
        result.get("summary", ""),
        result.get("window_title", window.title),
        ",".join(str(x) for x in result.get("box_2d", [0, 0, 0, 0])),
    ])
    return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()[:16]


def gemini_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "popup_detected": {"type": "boolean"},
            "issue_type": {"type": "string"},
            "summary": {"type": "string"},
            "target_label": {"type": "string"},
            "box_2d": {
                "type": "array",
                "items": {"type": "integer"},
                "minItems": 4,
                "maxItems": 4,
            },
            "recommended_action": {"type": "string"},
            "confidence": {"type": "number"},
        },
        "required": [
            "popup_detected",
            "issue_type",
            "summary",
            "target_label",
            "box_2d",
            "recommended_action",
            "confidence",
        ],
    }


def analyze_popup_with_gemini(
    image_bytes: bytes,
    mime_type: str,
    model: str,
) -> Dict[str, Any]:
    if genai is None:
        raise RuntimeError("google-genai package is not installed.")

    client = genai.Client(api_key=load_gemini_api_key())
    prompt = (
        "You are RevitEye. Inspect this Autodesk Revit screenshot. "
        "Only detect a blocking modal, warning popup, or dialog that interrupts workflow. "
        "If there is no popup, return popup_detected=false and box_2d=[0,0,0,0]. "
        "If there is a popup, choose the safest non-destructive button that dismisses or acknowledges it. "
        "Prefer labels like Cancel, Close, OK, Aceptar, Cerrar. "
        "Avoid destructive buttons like Delete, Remove, Overwrite, Purge unless absolutely no safe button exists. "
        "Return the chosen button bounding box in box_2d as [ymin, xmin, ymax, xmax] normalized to 0-1000. "
        "issue_type must be one of: PINNED_ELEMENTS, SAVE_CONFLICT, MISSING_TYPE, COPY_CONSTRAINT, "
        "ACTIVE_TRANSACTION_ERROR, UNKNOWN_MODAL, NO_DIALOG. "
        "recommended_action must be one of: CLICK_SAFE_BUTTON, WAIT, MANUAL_ATTENTION. "
        "Return JSON only."
    )

    interaction = client.interactions.create(
        model=model,
        input=[
            {"type": "text", "text": prompt},
            {
                "type": "image",
                "data": base64.b64encode(image_bytes).decode("utf-8"),
                "mime_type": mime_type,
            },
        ],
        response_format={
            "type": "text",
            "mime_type": "application/json",
            "schema": gemini_schema(),
        },
    )
    return parse_model_json(interaction.output_text)


def bbox_norm_to_screen(
    box_2d: List[int],
    window: WindowInfo,
) -> Tuple[int, int, int, int, int, int]:
    ymin, xmin, ymax, xmax = box_2d
    left = window.left + int(window.width * (xmin / 1000.0))
    top = window.top + int(window.height * (ymin / 1000.0))
    right = window.left + int(window.width * (xmax / 1000.0))
    bottom = window.top + int(window.height * (ymax / 1000.0))
    cx = left + max(1, (right - left) // 2)
    cy = top + max(1, (bottom - top) // 2)
    return left, top, right, bottom, cx, cy


def is_safe_target(label: str, allow_destructive: bool) -> bool:
    low = (label or "").strip().lower()
    if low in SAFE_LABELS:
        return True
    if low in DESTRUCTIVE_LABELS:
        return allow_destructive
    return False


def move_mouse_and_click(x: int, y: int) -> None:
    user32.SetCursorPos(int(x), int(y))
    time.sleep(0.15)
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    user32.mouse_event(0x0004, 0, 0, 0, 0)


def get_foreground_window_title() -> str:
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return ""
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value.strip()


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def watch(args: argparse.Namespace) -> int:
    run_dir = ensure_output_dir()
    log("RUN_DIR={}".format(run_dir))
    log("MODE={}".format("CLICK" if args.click else "DRY_RUN"))
    log("WINDOW_HINT={}".format(args.window_hint))
    log("CONFIRM_HITS={}".format(args.confirm_hits))

    last_click_at = 0.0
    hit_counter = 0
    last_fingerprint = ""
    same_popup_hits = 0
    last_heartbeat = 0.0

    while True:
        window = find_window(args.window_hint)
        if not window:
            log("WAITING_WINDOW")
            time.sleep(args.interval)
            if args.once:
                return 2
            continue

        if args.focus_window:
            activate_window(window.hwnd)
            time.sleep(0.2)
            window = find_window(args.window_hint) or window

        shot_name = "shot_{:03d}.png".format(hit_counter)
        json_name = "shot_{:03d}.json".format(hit_counter)
        shot_path = run_dir / shot_name
        json_path = run_dir / json_name
        image_bytes = capture_window(window, shot_path)

        result = analyze_popup_with_gemini(
            image_bytes=image_bytes,
            mime_type="image/png",
            model=args.model,
        )
        result["window_title"] = window.title
        result["window_rect"] = {
            "left": window.left,
            "top": window.top,
            "right": window.right,
            "bottom": window.bottom,
        }

        if result.get("popup_detected"):
            result["window_title"] = window.title
            fingerprint = popup_fingerprint(result, window)
            if fingerprint == last_fingerprint:
                same_popup_hits += 1
            else:
                same_popup_hits = 1
                last_fingerprint = fingerprint
            result["popup_fingerprint"] = fingerprint
            result["confirm_hits"] = same_popup_hits

            left, top, right, bottom, cx, cy = bbox_norm_to_screen(result["box_2d"], window)
            result["screen_bbox"] = {
                "left": left,
                "top": top,
                "right": right,
                "bottom": bottom,
            }
            result["click_point"] = {"x": cx, "y": cy}

            can_click = (
                float(result.get("confidence", 0)) >= args.min_confidence
                and is_safe_target(result.get("target_label", ""), args.allow_destructive)
                and result.get("recommended_action") == "CLICK_SAFE_BUTTON"
                and same_popup_hits >= args.confirm_hits
            )
            result["can_click"] = can_click

            now = time.time()
            if can_click and args.click and (now - last_click_at) >= args.cooldown:
                if args.no_focus and DEFAULT_WINDOW_HINT.lower() not in get_foreground_window_title().lower():
                    result["clicked"] = False
                    result["skip_reason"] = "foreground_window_changed"
                    log(
                        "SKIP_FOREGROUND issue={} label={} hits={}".format(
                            result.get("issue_type"),
                            result.get("target_label"),
                            same_popup_hits,
                        )
                    )
                else:
                    move_mouse_and_click(cx, cy)
                    result["clicked"] = True
                    last_click_at = now
                    log("CLICKED {} @{},{}".format(result.get("target_label"), cx, cy))
            else:
                result["clicked"] = False
                log(
                    "POPUP {} label={} conf={:.2f} click={}".format(
                        result.get("issue_type"),
                        result.get("target_label"),
                        float(result.get("confidence", 0)),
                        result["clicked"],
                    )
                )
        else:
            same_popup_hits = 0
            last_fingerprint = ""
            now = time.time()
            if (now - last_heartbeat) >= 15:
                log("NO_DIALOG")
                last_heartbeat = now

        write_json(json_path, result)
        hit_counter += 1

        if args.once:
            return 0
        time.sleep(args.interval)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="RevitEye popup watcher with Gemini + local mouse")
    parser.add_argument("--window-hint", default=DEFAULT_WINDOW_HINT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL)
    parser.add_argument("--cooldown", type=float, default=DEFAULT_COOLDOWN)
    parser.add_argument("--min-confidence", type=float, default=0.80)
    parser.add_argument("--confirm-hits", type=int, default=DEFAULT_CONFIRM_HITS)
    parser.add_argument("--click", action="store_true", help="Enable real mouse click")
    parser.add_argument("--allow-destructive", action="store_true")
    parser.add_argument("--focus-window", action="store_true")
    parser.add_argument("--no-focus", action="store_true", help="Never click unless Revit is already foreground")
    parser.add_argument("--once", action="store_true")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return watch(args)
    except KeyboardInterrupt:
        print("STOPPED")
        return 130
    except Exception as exc:
        print("ERROR={}".format(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
