#!/usr/bin/env python3
"""
viewer_postprocess.py — OBJ → GLB converter + scene_index.json generator.

Pipeline:
  Revit OBJ  +  keynote_map.json
       ↓
  viewer_postprocess.py --inspect    # show OBJ groups, keynote match stats
  viewer_postprocess.py --process    # convert OBJ → GLB, inject extras, write scene_index.json

Usage:
  D:\\LLM\\python\\python.exe viewer_postprocess.py --inspect  [project_dir]
  D:\\LLM\\python\\python.exe viewer_postprocess.py --process  [project_dir]

Requires:
  uv pip install trimesh pygltflib --system

Matching strategy:
  Revit OBJ groups objects by material name.
  keynote_map.json has material_name per element (from GetMaterialIds).
  Match: OBJ material name → keynote_map material_name → keynote.
"""

import sys
import os
import json
import argparse
import glob
import re
from collections import defaultdict

# Dependency check
missing = []
try:
    import trimesh
except ImportError:
    missing.append("trimesh")
try:
    import pygltflib
    from pygltflib import GLTF2
except ImportError:
    missing.append("pygltflib")

if missing:
    print("ERROR: Missing packages:", ", ".join(missing))
    print("Run: D:\\LLM\\python\\python.exe -m pip install", " ".join(missing))
    sys.exit(1)


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

VIEWER_ROOT = r"D:\OneDrive\Bots\Viewer\projects"


def find_file(project_dir, extensions):
    for ext in extensions:
        candidates = glob.glob(os.path.join(project_dir, f"*{ext}"))
        # prefer non-viewer files
        original = [f for f in candidates if "_viewer" not in os.path.basename(f)]
        if original:
            return original[0]
        if candidates:
            return candidates[0]
    return None


def load_keynote_map(project_dir):
    path = os.path.join(project_dir, "keynote_map.json")
    if not os.path.exists(path):
        print(f"ERROR: keynote_map.json not found in {project_dir}")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def auto_detect_project():
    if not os.path.exists(VIEWER_ROOT):
        return None
    projects = [
        d for d in os.listdir(VIEWER_ROOT)
        if os.path.isdir(os.path.join(VIEWER_ROOT, d))
    ]
    if not projects:
        return None
    projects.sort(
        key=lambda d: os.path.getmtime(os.path.join(VIEWER_ROOT, d)),
        reverse=True,
    )
    return os.path.join(VIEWER_ROOT, projects[0])


# ---------------------------------------------------------------------------
# BUILD MATERIAL → KEYNOTE MAP
# ---------------------------------------------------------------------------

def build_material_keynote_map(keynote_elements):
    """
    Build: material_name_lower → keynote  (from keynote_map elements)
    Also: type_name_lower → keynote  (fallback)
    Also: family_name_lower → keynote  (fallback)
    """
    mat_to_keynote = {}
    type_to_keynote = {}

    for eid, data in keynote_elements.items():
        kn = data.get("keynote", "").strip()
        if not kn:
            continue

        mat = normalize(data.get("material_name", ""))
        if mat:
            mat_to_keynote[mat] = kn

        type_name = normalize(data.get("type_name", ""))
        if type_name:
            type_to_keynote[type_name] = kn

    return mat_to_keynote, type_to_keynote


def normalize(name):
    """Normalize OBJ/Revit name for matching: underscores→spaces, collapse spaces, lowercase."""
    return re.sub(r'\s+', ' ', name.replace('_', ' ')).strip().lower()


def match_group_name(group_name, mat_to_keynote, type_to_keynote):
    """
    Match OBJ group/material name to keynote.
    Revit OBJ exports replace spaces with underscores in usemtl names.
    Normalize both sides before comparing.
    """
    name_norm = normalize(group_name)

    # Direct match (normalized)
    if name_norm in mat_to_keynote:
        return mat_to_keynote[name_norm]

    # Partial match — normalized
    for mat_name, kn in mat_to_keynote.items():
        if mat_name in name_norm or name_norm in mat_name:
            return kn

    # Fallback: type name
    if name_norm in type_to_keynote:
        return type_to_keynote[name_norm]

    for type_name, kn in type_to_keynote.items():
        if type_name in name_norm or name_norm in type_name:
            return kn

    return None


# ---------------------------------------------------------------------------
# INSPECT MODE
# ---------------------------------------------------------------------------

def cmd_inspect(project_dir):
    obj_path = find_file(project_dir, [".obj"])
    if not obj_path:
        print(f"ERROR: No .obj file found in {project_dir}")
        print("Run pyRevit 'Export Viewer GLB' button first.")
        sys.exit(1)

    print(f"\n=== INSPECT: {os.path.basename(obj_path)} ===\n")

    data = load_keynote_map(project_dir)
    keynote_elements = data.get("elements", {})
    mat_to_keynote, type_to_keynote = build_material_keynote_map(keynote_elements)

    print(f"keynote_map.json: {len(keynote_elements)} elements with keynotes")
    print(f"  Unique materials in map: {len(mat_to_keynote)}")
    print(f"  Unique types in map:     {len(type_to_keynote)}")

    # Parse OBJ groups and materials
    obj_materials = set()
    obj_groups = set()
    total_faces = 0
    with open(obj_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if line.startswith("usemtl "):
                obj_materials.add(line[7:].strip())
            elif line.startswith("g "):
                obj_groups.add(line[2:].strip())
            elif line.startswith("f "):
                total_faces += 1

    print(f"\nOBJ file stats:")
    print(f"  Unique materials (usemtl): {len(obj_materials)}")
    print(f"  Groups (g):                {len(obj_groups)}")
    print(f"  Faces:                     {total_faces:,}")

    # Try matching
    matched = 0
    unmatched = []
    print(f"\n--- Material matching (first 30) ---")
    for mat in sorted(obj_materials)[:30]:
        kn = match_group_name(mat, mat_to_keynote, type_to_keynote)
        status = f"→ {kn}" if kn else "NO MATCH"
        if kn:
            matched += 1
        else:
            unmatched.append(mat)
        print(f"  '{mat}' {status}")

    if len(obj_materials) > 30:
        print(f"  ... ({len(obj_materials) - 30} more)")
        for mat in sorted(obj_materials)[30:]:
            kn = match_group_name(mat, mat_to_keynote, type_to_keynote)
            if kn:
                matched += 1
            else:
                unmatched.append(mat)

    print(f"\n--- Match Stats ---")
    print(f"OBJ materials:     {len(obj_materials)}")
    print(f"Matched:           {matched}")
    print(f"Unmatched:         {len(unmatched)}")

    if unmatched:
        print(f"\nUnmatched materials (no keynote found):")
        for m in unmatched[:20]:
            print(f"  '{m}'")

    if matched == 0:
        print("\nACTION NEEDED: Zero matches.")
        print("Check that keynote_map.json has material_name populated.")
        print("Sample material_names from map:", list(mat_to_keynote.keys())[:5])
        print("Sample OBJ materials:", list(sorted(obj_materials))[:5])
    else:
        ratio = matched / len(obj_materials) * 100 if obj_materials else 0
        print(f"\nMatch rate: {ratio:.0f}%")
        if ratio > 50:
            print("OK — run --process when ready.")
        else:
            print("WARNING — low match rate. Inspect material names above.")


# ---------------------------------------------------------------------------
# PROCESS MODE
# ---------------------------------------------------------------------------

def cmd_process(project_dir):
    obj_path = find_file(project_dir, [".obj"])
    if not obj_path:
        print(f"ERROR: No .obj file found in {project_dir}")
        sys.exit(1)

    data = load_keynote_map(project_dir)
    meta = data.get("_meta", {})
    keynote_elements = data.get("elements", {})
    project_name = meta.get("safe_name", "model")

    mat_to_keynote, type_to_keynote = build_material_keynote_map(keynote_elements)

    print(f"Loading OBJ: {obj_path}")
    scene = trimesh.load(obj_path, process=False, force="scene")

    if isinstance(scene, trimesh.Trimesh):
        # Single mesh — wrap in scene
        scene = trimesh.scene.scene.Scene({"mesh": scene})

    print(f"  Geometries: {len(scene.geometry)}")
    print(f"  Nodes:      {len(scene.graph.nodes)}")

    # Build mapping: geometry_name → keynote + category
    geo_keynote = {}
    unmatched_geos = []

    for geo_name in scene.geometry.keys():
        kn = match_group_name(geo_name, mat_to_keynote, type_to_keynote)
        if kn:
            category = ""
            for eid, d in keynote_elements.items():
                if d.get("keynote") == kn:
                    category = d.get("category", "")
                    break
            geo_keynote[geo_name] = {"keynote": kn, "category": category}
        else:
            unmatched_geos.append(geo_name)

    print(f"  Matched geometries: {len(geo_keynote)}")
    print(f"  Unmatched:          {len(unmatched_geos)}")

    # Export to GLB
    out_glb = os.path.join(project_dir, project_name + "_viewer.glb")

    # Attach keynote as metadata in scene extras
    scene.metadata = {
        "keynote_map": {
            name: data["keynote"]
            for name, data in geo_keynote.items()
        },
        "project_id": project_name,
    }

    print(f"Exporting GLB: {out_glb}")
    scene.export(out_glb)
    size_mb = os.path.getsize(out_glb) / (1024 * 1024)
    print(f"  GLB size: {size_mb:.1f} MB")

    # Post-process GLB with pygltflib to inject keynotes into node extras
    print("Injecting keynotes into GLB node extras...")
    gltf = GLTF2().load(out_glb)

    injected = 0
    for node in gltf.nodes:
        name = node.name or ""
        kn = match_group_name(name, mat_to_keynote, type_to_keynote)
        if kn:
            if node.extras is None:
                node.extras = {}
            node.extras["keynote"] = kn
            # Add category
            for eid, d in keynote_elements.items():
                if d.get("keynote") == kn:
                    node.extras["category"] = d.get("category", "")
                    break
            injected += 1

    gltf.save(out_glb)
    print(f"  Keynotes injected into {injected} nodes")

    # Build scene_index.json
    keynote_to_meshes = defaultdict(list)
    mesh_to_keynote = {}
    category_to_meshes = defaultdict(list)

    for idx, node in enumerate(gltf.nodes):
        if node.extras and node.extras.get("keynote"):
            mesh_id = f"node_{idx:04d}"
            kn = node.extras["keynote"]
            cat = node.extras.get("category", "Unknown")
            keynote_to_meshes[kn].append(mesh_id)
            mesh_to_keynote[mesh_id] = kn
            category_to_meshes[cat].append(mesh_id)

    scene_index = {
        "project_id": project_name,
        "exported_at": meta.get("exported_at", ""),
        "glb_file": project_name + "_viewer.glb",
        "stats": {
            "total_nodes": len(gltf.nodes),
            "nodes_with_keynote": injected,
            "unique_keynotes": len(keynote_to_meshes),
            "categories": len(category_to_meshes),
        },
        "keynote_to_meshes": dict(keynote_to_meshes),
        "mesh_to_keynote": mesh_to_keynote,
        "category_to_meshes": dict(category_to_meshes),
    }

    scene_index_path = os.path.join(project_dir, "scene_index.json")
    with open(scene_index_path, "w", encoding="utf-8") as f:
        json.dump(scene_index, f, indent=2, ensure_ascii=False)

    print(f"\nDONE:")
    print(f"  {out_glb}  ({size_mb:.1f} MB)")
    print(f"  {scene_index_path}")
    print(f"\n  {len(keynote_to_meshes)} keynotes mapped")
    print(f"  Categories:")
    for cat, meshes in sorted(category_to_meshes.items()):
        print(f"    {cat}: {len(meshes)} nodes")


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Viewer OBJ→GLB post-processor")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--inspect", action="store_true",
                       help="Show OBJ groups and keynote match stats. Read-only.")
    group.add_argument("--process", action="store_true",
                       help="Convert OBJ→GLB, inject keynotes, write scene_index.json.")
    parser.add_argument("project_dir", nargs="?", default=None,
                        help="Path to project folder (has .obj + keynote_map.json)")
    args = parser.parse_args()

    if not args.project_dir:
        args.project_dir = auto_detect_project()
        if not args.project_dir:
            print(f"ERROR: No project found in {VIEWER_ROOT}")
            sys.exit(1)
        print(f"Auto-detected: {args.project_dir}")

    if not os.path.isdir(args.project_dir):
        print(f"ERROR: Not a directory: {args.project_dir}")
        sys.exit(1)

    if args.inspect:
        cmd_inspect(args.project_dir)
    else:
        cmd_process(args.project_dir)


if __name__ == "__main__":
    main()
