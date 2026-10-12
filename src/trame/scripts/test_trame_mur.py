# Test de l outil Mur Trame : blender -b --python src/trame/scripts/test_trame_mur.py
import bpy, math
bpy.ops.preferences.addon_enable(module="bl_ext.user_default.trame")
import trame.tool as tool, ifcopenshell.util.element as ue
bpy.ops.bim.create_project()
assert tool.Root.get_default_container(), "pas d'étage par défaut"
bpy.ops.bim.trame_reglages_mur(x=1, y=2, z=0, longueur=5, angle=90, epaisseur=0.3, hauteur=2.7)
bpy.ops.bim.trame_reglages_mur(x=0, y=0, z=0, longueur=4, angle=0, epaisseur=0.3, hauteur=2.7)
f = tool.Ifc.get()
walls = f.by_type("IfcWall")
assert len(walls) == 2, walls
types = {ue.get_type(w).Name for w in walls}
assert types == {"Mur 30 cm"}, types
o = tool.Ifc.get_object(walls[0])
dims = sorted(round(v, 3) for v in o.dimensions)
print("DIMS", dims, "ROT", round(math.degrees(o.rotation_euler.z)), "LOC", tuple(round(v, 3) for v in o.location))
assert dims == [0.3, 2.7, 5.0], dims
print("TEST MUR OK", ue.get_container(walls[0]).Name)
