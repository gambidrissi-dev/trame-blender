# Test des outils Trame (mur, dalle, porte, fenêtre) : blender -b --python src/trame/scripts/test_trame_outils.py
import bpy, math
bpy.ops.preferences.addon_enable(module="bl_ext.user_default.trame")
import trame.tool as tool, ifcopenshell.util.element as ue
bpy.ops.bim.create_project()
assert tool.Root.get_default_container(), "pas d'étage par défaut"
f = tool.Ifc.get()

# Un mur seul : longueur et angle de la fenêtre de réglages priment sur le tracé.
bpy.ops.bim.trame_reglages_mur(points="1,2;1,3", z=0, longueur=5, angle=90, epaisseur=0.3, hauteur=2.7)
o = tool.Ifc.get_object(f.by_type("IfcWall")[0])
assert sorted(round(v, 3) for v in o.dimensions) == [0.3, 2.7, 5.0], o.dimensions
assert round(math.degrees(o.rotation_euler.z)) == 90 and tuple(round(v, 3) for v in o.location) == (1, 2, 0)
mur = tool.Ifc.get_entity(o)
assert ue.get_type(mur).Name == "Mur 30 cm" and ue.get_container(mur)

# Accroche : les extrémités du mur seul sont proposées comme cibles.
from trame.bim.module.model.trame_outils import extremites_murs, mur_sous_point
cibles = {(round(v.x, 3), round(v.y, 3)) for v in extremites_murs(0)}
assert {(1, 2), (1, 7)} <= cibles, cibles

# Chaîne ouverte de 3 points : 2 murs, 1 raccord.
bpy.ops.bim.trame_reglages_mur(points="10,0;14,0;14,3", z=0, epaisseur=0.2, hauteur=2.5)
assert len(f.by_type("IfcWall")) == 3
assert len(f.by_type("IfcRelConnectsPathElements")) == 1

# Contour fermé (rectangle) : 4 murs, 4 raccords.
bpy.ops.bim.trame_reglages_mur(points="20,0;24,0;24,3;20,3;20,0", z=0, epaisseur=0.2, hauteur=2.5)
assert len(f.by_type("IfcWall")) == 7
assert len(f.by_type("IfcRelConnectsPathElements")) == 5, len(f.by_type("IfcRelConnectsPathElements"))
cibles = {(round(v.x, 3), round(v.y, 3)) for v in extremites_murs(0)}
assert {(20, 0), (24, 0), (24, 3), (20, 3)} <= cibles, cibles

# Dalle : contour de 4 points, fermée automatiquement, type « Dalle 25 cm ».
bpy.ops.bim.trame_reglages_dalle(points="20,0;24,0;24,3;20,3", z=0, epaisseur=0.25)
(dalle,) = f.by_type("IfcSlab")
assert ue.get_type(dalle).Name == "Dalle 25 cm"
o = tool.Ifc.get_object(dalle)
assert sorted(round(v, 2) for v in o.dimensions) == [0.25, 3.0, 4.0], o.dimensions

# Clic sur un mur : le mur seul (x=1, de y=2 à y=7) est trouvé à 3 m de son début.
from mathutils import Vector
mur, position = mur_sous_point(Vector((1.05, 5, 0)), 0)
assert tool.Ifc.get_object(mur) == tool.Ifc.get_object(f.by_type("IfcWall")[0]) and round(position, 2) == 3.0
assert mur_sous_point(Vector((50, 50, 0)), 0) is None

# Porte centrée à 3 m dans ce mur : le mur est percé, la porte fait 90 cm et commence à 2,55 m.
bpy.ops.bim.trame_reglages_porte(mur=mur.id(), position=3.0, z=0, largeur=0.9, hauteur=2.1)
(porte,) = f.by_type("IfcDoor")
assert ue.get_type(porte).Name == "Porte 90 × 210"
assert len(f.by_type("IfcRelFillsElement")) == 1
op = tool.Ifc.get_object(porte)
# 90 cm de passage + chambranle de Bonsai de part et d'autre.
assert round(op.location.y, 2) == 4.55 and 0.9 <= round(op.dimensions.x, 2) <= 1.0, (op.location, op.dimensions)

# Fenêtre avec allège de 1 m.
bpy.ops.bim.trame_reglages_fenetre(mur=mur.id(), position=1.0, z=0, largeur=1.0, hauteur=1.2, allege=1.0)
(fenetre,) = f.by_type("IfcWindow")
assert ue.get_type(fenetre).Name == "Fenêtre 100 × 120"
assert len(f.by_type("IfcRelFillsElement")) == 2
assert round(tool.Ifc.get_object(fenetre).location.z, 2) == 1.0
print("TEST OUTILS OK")
