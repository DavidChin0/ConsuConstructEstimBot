"""Fix CompoundStructure validation errors for 3 problematic assemblies:
1. STR-05: "C - Repello y Pulido + Bloque de 4\" (10cm) + Ceramica Baño 2.10m" - Finish2 ceramic at 0mm
2. STR-06: "C - Repello y Pulido + Bloque de 6\" (15cm) + Ceramica Baño 2.10m" - Finish2 ceramic at 0mm
3. ENC-01: "F - Vigueta Bovedilla +Losa de Concreto de 8cm" - StructuralDeck bovedilla at 0mm

Fix: Recreate types from scratch with MIN_WIDTH_MM=1.0 for non-Membrane layers.
Run via execute_revit_code on Revit MCP bridge with target document open.
"""
from __future__ import annotations

CODE = r'''
from pyrevit import revit, DB
import json

doc = revit.doc

MIN_WIDTH_MM = 1.0  # Minimum width for non-Membrane layers (Revit requires >0)

def mm_to_ft(mm):
    return mm / 304.8

def ft_to_mm(ft):
    return ft * 304.8

def get_material_id(mat_name):
    """Find material by name, return ElementId or InvalidElementId."""
    mats = DB.FilteredElementCollector(doc).OfClass(DB.Material).ToElements()
    for m in mats:
        try:
            if m.Name == mat_name:
                return m.Id
        except:
            pass
    return DB.ElementId.InvalidElementId

def get_base_wall_type(type_name):
    """Find existing wall type by name to duplicate."""
    types = DB.FilteredElementCollector(doc).OfClass(DB.WallType).ToElements()
    for t in types:
        try:
            if t.Name == type_name:
                return t
        except:
            pass
    return None

def get_base_floor_type(type_name):
    """Find existing floor type by name to duplicate."""
    types = DB.FilteredElementCollector(doc).OfClass(DB.FloorType).ToElements()
    for t in types:
        try:
            if t.Name == type_name:
                return t
        except:
            pass
    return None

def create_compound_structure(layers_data):
    """Create CompoundStructure from layer definitions.
    layers_data: list of dicts with keys: function, material_name, width_mm
    function: string like "Finish1", "Structure", "Membrane", etc.
    """
    cs = DB.CompoundStructure()
    layer_list = []
    
    for i, layer in enumerate(layers_data):
        func_str = layer['function']
        mat_name = layer['material_name']
        width_mm = layer['width_mm']
        
        # Apply minimum width for non-Membrane layers
        if func_str != "Membrane" and width_mm < MIN_WIDTH_MM:
            print("WARNING: Layer {} ({}) width {:.2f}mm < MIN_WIDTH_MM ({}mm), setting to {}".format(
                i, func_str, width_mm, MIN_WIDTH_MM, MIN_WIDTH_MM))
            width_mm = MIN_WIDTH_MM
        
        # Skip CC-none material (placeholder for void)
        if mat_name and "CC-none" in mat_name:
            print("SKIPPING CC-none layer: {} ({})".format(func_str, mat_name))
            continue
        
        # Map function string to Revit MaterialLayerFunction
        func_map = {
            "Structure": DB.MaterialLayerFunction.Structure,
            "Substrate": DB.MaterialLayerFunction.Substrate,
            "Finish1": DB.MaterialLayerFunction.Finish1,
            "Finish2": DB.MaterialLayerFunction.Finish2,
            "Membrane": DB.MaterialLayerFunction.Membrane,
            "Insulation": DB.MaterialLayerFunction.ThermalOrAirLayer,
        }
        func = func_map.get(func_str, DB.MaterialLayerFunction.Structure)
        
        mat_id = get_material_id(mat_name) if mat_name else DB.ElementId.InvalidElementId
        
        ml = DB.MaterialLayer(mat_id, mm_to_ft(width_mm), func)
        layer_list.append(ml)
    
    if not layer_list:
        raise Exception("No valid layers after filtering!")
    
    cs.SetLayers(layer_list)
    return cs

def fix_wall_type():
    """Fix the two STR wall types with Ceramica 2.10m at 0mm."""
    results = []
    
    # STR-05: 4" Bloque + Ceramica 2.10m
    base_name = "C - Repello y Pulido + Bloque de 4\" (10cm) + Ceramica Baño 1.50m"
    new_name = "C - Repello y Pulido + Bloque de 4\" (10cm) + Ceramica Baño 2.10m (Fixed)"
    base_type = get_base_wall_type(base_name)
    
    if not base_type:
        results.append({"type": "STR-05 2.10m", "ok": False, "error": "Base type not found: " + base_name})
    else:
        try:
            # Get the compound structure from base and modify
            cs = base_type.GetCompoundStructure()
            layers_out = []
            for layer in cs.GetLayers():
                mat_id = layer.MaterialId
                mat = doc.GetElement(mat_id) if mat_id and mat_id != DB.ElementId.InvalidElementId else None
                mat_name = mat.Name if mat else None
                width_mm = round(layer.Width * 304.8, 2)
                func = str(layer.Function)
                
                # Fix ceramic layer width
                if mat_name and "Ceramica" in mat_name and func == "Finish2" and width_mm == 0.0:
                    width_mm = 20.0  # Same as 1.50m version
                    print("FIXED: {} layer width 0.0 -> 20.0mm".format(mat_name))
                
                layers_out.append({
                    "function": func,
                    "material_name": mat_name,
                    "width_mm": width_mm
                })
            
            # Duplicate and set new structure
            new_type = base_type.Duplicate(new_name)
            new_cs = create_compound_structure(layers_out)
            new_type.SetCompoundStructure(new_cs)
            
            # Set keynote and type mark
            kn = base_type.get_Parameter(DB.BuiltInParameter.KEYNOTE_PARAM)
            if kn:
                kn.Set("04 26 00.1")
            tm = new_type.get_Parameter(DB.BuiltInParameter.ALL_MODEL_TYPE_MARK)
            if tm:
                tm.Set("STR-05")
            
            results.append({"type": "STR-05 2.10m", "ok": True, "new_name": new_name})
        except Exception as ex:
            results.append({"type": "STR-05 2.10m", "ok": False, "error": str(ex)})
    
    # STR-06: 6" Bloque + Ceramica 2.10m
    base_name = "C - Repello y Pulido + Bloque de 6\" (15cm) + Ceramica Baño 1.50m"
    new_name = "C - Repello y Pulido + Bloque de 6\" (15cm) + Ceramica Baño 2.10m (Fixed)"
    base_type = get_base_wall_type(base_name)
    
    if not base_type:
        results.append({"type": "STR-06 2.10m", "ok": False, "error": "Base type not found: " + base_name})
    else:
        try:
            cs = base_type.GetCompoundStructure()
            layers_out = []
            for layer in cs.GetLayers():
                mat_id = layer.MaterialId
                mat = doc.GetElement(mat_id) if mat_id and mat_id != DB.ElementId.InvalidElementId else None
                mat_name = mat.Name if mat else None
                width_mm = round(layer.Width * 304.8, 2)
                func = str(layer.Function)
                
                if mat_name and "Ceramica" in mat_name and func == "Finish2" and width_mm == 0.0:
                    width_mm = 20.0
                    print("FIXED: {} layer width 0.0 -> 20.0mm".format(mat_name))
                
                layers_out.append({
                    "function": func,
                    "material_name": mat_name,
                    "width_mm": width_mm
                })
            
            new_type = base_type.Duplicate(new_name)
            new_cs = create_compound_structure(layers_out)
            new_type.SetCompoundStructure(new_cs)
            
            kn = base_type.get_Parameter(DB.BuiltInParameter.KEYNOTE_PARAM)
            if kn:
                kn.Set("04 26 00.2")
            tm = new_type.get_Parameter(DB.BuiltInParameter.ALL_MODEL_TYPE_MARK)
            if tm:
                tm.Set("STR-06")
            
            results.append({"type": "STR-06 2.10m", "ok": True, "new_name": new_name})
        except Exception as ex:
            results.append({"type": "STR-06 2.10m", "ok": False, "error": str(ex)})
    
    return results

def fix_floor_type():
    """Fix ENC-01 floor type with StructuralDeck at 0mm."""
    results = []
    
    # Base: "Entrepiso Vigueta-Bovedilla ENC-01" (simple 150mm concrete)
    base_name = "Entrepiso Vigueta-Bovedilla ENC-01"
    new_name = "F - Vigueta Bovedilla +Losa de Concreto de 8cm (Fixed)"
    base_type = get_base_floor_type(base_name)
    
    if not base_type:
        results.append({"type": "ENC-01", "ok": False, "error": "Base type not found: " + base_name})
    else:
        try:
            # Build new compound structure: 80mm concrete topping + 150mm structural deck (bovedilla)
            layers_out = [
                {"function": "Finish1", "material_name": "CC-PisoConcreto", "width_mm": 80.0},
                {"function": "StructuralDeck", "material_name": "CC-Bovedilla", "width_mm": 150.0},
            ]
            
            new_type = base_type.Duplicate(new_name)
            new_cs = create_compound_structure(layers_out)
            new_type.SetCompoundStructure(new_cs)
            
            kn = new_type.get_Parameter(DB.BuiltInParameter.KEYNOTE_PARAM)
            if kn:
                kn.Set("03 11 00")
            tm = new_type.get_Parameter(DB.BuiltInParameter.ALL_MODEL_TYPE_MARK)
            if tm:
                tm.Set("ENC-01")
            
            results.append({"type": "ENC-01", "ok": True, "new_name": new_name})
        except Exception as ex:
            results.append({"type": "ENC-01", "ok": False, "error": str(ex)})
    
    return results

# Main execution
print("=== Fixing CompoundStructure validation errors ===")
print("MIN_WIDTH_MM =", MIN_WIDTH_MM)

all_results = []
all_results.extend(fix_wall_type())
all_results.extend(fix_floor_type())

print("\n=== RESULTS ===")
for r in all_results:
    print(json.dumps(r))

print("\nDone.")
'''

def get_code():
    return CODE


if __name__ == "__main__":
    print("Paste CODE into execute_revit_code on the Revit MCP bridge.")
    print("Target: estimastruct_blank_template.rvt (or project with the problematic types)")
    print("The script will create NEW fixed types (suffix '(Fixed)') without modifying originals.")