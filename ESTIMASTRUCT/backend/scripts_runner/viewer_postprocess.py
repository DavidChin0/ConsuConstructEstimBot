"""viewer_postprocess.py — Post-process OBJ exports from pyRevit into GLB + scene_index.json.

Usage (standalone or via revit_mcp.py python/{script}):
    python -m backend.scripts_runner.viewer_postprocess [project_name]

What it does:
  1. Scans _OBJ_EXPORTS_DIR for subdirectory {project_name} (or all if no arg).
  2. Converts each .obj found to .glb using obj2gltf (must be on PATH or npx).
  3. Moves the resulting .glb to _VIEWER_ROOT/{project_name}/{stem}_viewer.glb.
  4. Builds a base scene_index.json for the project (mesh list + project name).
  5. If _FULL_DUMP_PATH exists, merges:
       - levels         (list)
       - rooms          (list)
       - materials_full (list, empty-dict values stripped from appearance_params
                         and texture_paths)
       - project_info   (dict)
     into scene_index.json.
  6. Writes scene_index.json to _VIEWER_ROOT/{project_name}/scene_index.json.

Dependencies:
  - obj2gltf installed globally or via npx (`npm install -g obj2gltf`)
  - Python 3.8+

Paths:
  OBJ exports  : D:\\OneDrive\\Bots\\Estimbot\\EXPORTS\\OBJ_exports\\
  Full dump    : D:\\OneDrive\\Bots\\Estimbot\\EXPORTS\\project_full_dump.json
  Viewer root  : D:\\OneDrive\\Bots\\Viewer\\projects\\
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

# ── Canonical paths ──────────────────────────────────────────────────────────
_OBJ_EXPORTS_DIR = Path(r"D:\OneDrive\Bots\Estimbot\EXPORTS\OBJ_exports")
_FULL_DUMP_PATH  = Path(r"D:\OneDrive\Bots\Estimbot\EXPORTS\project_full_dump.json")
_VIEWER_ROOT     = Path(r"D:\OneDrive\Bots\Viewer\projects")

# ── Conversion tooling ───────────────────────────────────────────────────────
# Try `obj2gltf` directly (global install), fall back to `npx obj2gltf`.
_OBJ2GLTF_CMD = "obj2gltf"  # override with env var OBJ2GLTF_CMD if needed
_OBJ2GLTF_CMD = os.environ.get("OBJ2GLTF_CMD", _OBJ2GLTF_CMD)


# ── Material stripping ───────────────────────────────────────────────────────
def _strip_empty_dicts(mat: dict) -> dict:
    """Return a copy of a material dict with empty-dict values removed from
    'appearance_params' and 'texture_paths' keys only.

    Keeps the keys if they contain actual data; removes them entirely if they
    are empty dicts `{}`.
    """
    out = dict(mat)
    for field in ("appearance_params", "texture_paths"):
        if field in out and out[field] == {}:
            del out[field]
    return out


# ── OBJ → GLB conversion ─────────────────────────────────────────────────────
def _convert_obj_to_glb(obj_path: Path, out_path: Path) -> bool:
    """Convert a single OBJ file to GLB. Returns True on success."""
    cmd = [_OBJ2GLTF_CMD, "-i", str(obj_path), "-o", str(out_path)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            print(f"  [OK]  {obj_path.name} → {out_path.name}")
            return True
        # Try npx fallback
        print(f"  [WARN] obj2gltf direct failed (rc={result.returncode}), trying npx…")
    except FileNotFoundError:
        print("  [WARN] obj2gltf not found on PATH, trying npx…")

    # npx fallback
    cmd_npx = ["npx", "--yes", "obj2gltf", "-i", str(obj_path), "-o", str(out_path)]
    try:
        result = subprocess.run(cmd_npx, capture_output=True, text=True, timeout=180)
        if result.returncode == 0:
            print(f"  [OK]  {obj_path.name} → {out_path.name} (via npx)")
            return True
        print(f"  [ERR] npx obj2gltf failed (rc={result.returncode}):")
        if result.stderr:
            print("        " + result.stderr[:400])
        return False
    except Exception as e:
        print(f"  [ERR] Conversion exception: {e}")
        return False


# ── scene_index.json helpers ─────────────────────────────────────────────────
def _load_scene_index(proj_dir: Path) -> dict:
    """Load existing scene_index.json or return a fresh skeleton."""
    idx_path = proj_dir / "scene_index.json"
    if idx_path.exists():
        try:
            with open(idx_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"  [WARN] Could not parse existing scene_index.json: {e} — starting fresh")
    return {}


def _build_base_index(proj_dir: Path, project_name: str) -> dict:
    """Build the base scene_index from GLB files present in the project dir."""
    glb_files = sorted(proj_dir.glob("*_viewer.glb"), key=lambda p: p.stat().st_mtime, reverse=True)
    meshes = [
        {
            "glb_name": glb.name,
            "size_bytes": glb.stat().st_size,
        }
        for glb in glb_files
    ]
    return {
        "_meta": {
            "postprocess_version": "1.0",
            "project_name": project_name,
        },
        "project_name": project_name,
        "glb_files": [m["glb_name"] for m in meshes],
        "meshes": meshes,
    }


def _merge_dump_into_index(index: dict, dump: dict) -> dict:
    """Merge the four viewer-relevant sections from project_full_dump into index."""
    # levels — list, copied as-is
    if "levels" in dump:
        index["levels"] = dump["levels"]

    # rooms — list, copied as-is
    if "rooms" in dump:
        index["rooms"] = dump["rooms"]

    # materials_full — list, strip empty appearance_params / texture_paths
    if "materials_full" in dump:
        index["materials_full"] = [
            _strip_empty_dicts(m) for m in dump["materials_full"]
        ]

    # project_info — dict, copied as-is
    if "project_info" in dump:
        index["project_info"] = dump["project_info"]

    return index


def _write_scene_index(proj_dir: Path, index: dict) -> None:
    idx_path = proj_dir / "scene_index.json"
    with open(idx_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    print(f"  [OK]  scene_index.json written ({idx_path.stat().st_size:,} bytes)")


# ── dump loader ───────────────────────────────────────────────────────────────
def _load_dump() -> dict | None:
    """Load project_full_dump.json. Returns None silently if missing."""
    if not _FULL_DUMP_PATH.exists():
        return None
    try:
        with open(_FULL_DUMP_PATH, encoding="utf-8") as f:
            data = json.load(f)
        print(f"  [OK]  Loaded project_full_dump.json "
              f"(levels={len(data.get('levels', []))}, "
              f"rooms={len(data.get('rooms', []))}, "
              f"materials_full={len(data.get('materials_full', []))}, "
              f"project_info={'yes' if data.get('project_info') else 'no'})")
        return data
    except Exception as e:
        print(f"  [WARN] Could not load project_full_dump.json: {e}")
        return None


# ── per-project processing ────────────────────────────────────────────────────
def process_project(project_name: str, dump: dict | None) -> bool:
    """Convert OBJs and write scene_index.json for one project. Returns True on success."""
    print(f"\n── Project: {project_name} ──")

    # Ensure viewer project dir exists
    proj_dir = _VIEWER_ROOT / project_name
    proj_dir.mkdir(parents=True, exist_ok=True)

    # 1. Convert OBJ files if export dir exists
    obj_dir = _OBJ_EXPORTS_DIR / project_name
    converted = 0
    skipped   = 0
    failed    = 0

    if obj_dir.exists():
        obj_files = sorted(obj_dir.glob("*.obj"))
        if obj_files:
            print(f"  Found {len(obj_files)} OBJ file(s) to convert…")
            for obj_path in obj_files:
                stem = obj_path.stem
                glb_name = stem + "_viewer.glb"
                glb_out  = proj_dir / glb_name

                # Skip if GLB already exists and is newer than the OBJ
                if glb_out.exists() and glb_out.stat().st_mtime >= obj_path.stat().st_mtime:
                    print(f"  [SKIP] {glb_name} already up-to-date")
                    skipped += 1
                    continue

                ok = _convert_obj_to_glb(obj_path, glb_out)
                if ok:
                    converted += 1
                else:
                    failed += 1
        else:
            print(f"  No OBJ files in {obj_dir}")
    else:
        print(f"  OBJ export dir not found: {obj_dir} — skipping conversion")

    # 2. Build base scene_index (existing or fresh)
    index = _load_scene_index(proj_dir)
    base  = _build_base_index(proj_dir, project_name)

    # Merge base into index (preserves any existing keys not in base)
    for k, v in base.items():
        index[k] = v

    # 3. Merge dump sections if available
    if dump is not None:
        index = _merge_dump_into_index(index, dump)
        print(f"  [OK]  Merged dump data into scene_index")
    else:
        print(f"  [INFO] project_full_dump.json not found — scene_index written without dump enrichment")

    # 4. Write scene_index.json
    _write_scene_index(proj_dir, index)

    print(f"  Summary: converted={converted} skipped={skipped} failed={failed}")
    return failed == 0


# ── entry point ───────────────────────────────────────────────────────────────
def main(args: list[str] = None) -> int:
    args = args or sys.argv[1:]

    # Load dump once (shared across projects)
    dump = _load_dump()

    if args:
        # Process a single named project
        project_name = args[0]
        ok = process_project(project_name, dump)
        return 0 if ok else 1

    # No args — process all projects already in viewer root, plus any OBJ export dirs
    project_names: set[str] = set()

    if _VIEWER_ROOT.exists():
        for d in _VIEWER_ROOT.iterdir():
            if d.is_dir():
                project_names.add(d.name)

    if _OBJ_EXPORTS_DIR.exists():
        for d in _OBJ_EXPORTS_DIR.iterdir():
            if d.is_dir():
                project_names.add(d.name)

    if not project_names:
        print("No viewer projects or OBJ export dirs found.")
        print(f"  Viewer root   : {_VIEWER_ROOT}")
        print(f"  OBJ export dir: {_OBJ_EXPORTS_DIR}")
        return 0

    all_ok = True
    for name in sorted(project_names):
        ok = process_project(name, dump)
        if not ok:
            all_ok = False

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
