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
import json
assert json.loads(ue.get_pset(ue.get_type(fenetre), "BBIM_Window")["Data"])["overall_width"] == 1.0

# Poteau 25 × 40 centré au point cliqué.
bpy.ops.bim.trame_reglages_poteau(x=3, y=4, z=0, largeur=0.25, profondeur=0.4, hauteur=2.7)
(poteau,) = f.by_type("IfcColumn")
po = tool.Ifc.get_object(poteau)
assert ue.get_type(poteau).Name == "Poteau 25 × 40"
assert sorted(round(v, 2) for v in po.dimensions) == [0.25, 0.4, 2.7] and tuple(round(v, 2) for v in po.location[:2]) == (3, 4)

# Toits : deux pans sur 10 × 6 (pignons sur les petits côtés), quatre pans, un pan, terrasse.
bpy.ops.bim.trame_reglages_toit(points="0,20;10,20;10,26;0,26", z=0, forme="DEUX_PANS", pente=35, epaisseur=0.25, depart=2.5)
toits = f.by_type("IfcRoof")
assert len(toits) == 1 and toits[0].PredefinedType == "GABLE_ROOF"
to = tool.Ifc.get_object(toits[0])
assert tuple(round(v, 1) for v in to.dimensions[:2]) == (10, 6) and round(to.location.z, 2) == 2.5
assert 2.0 < to.dimensions.z < 2.6, to.dimensions  # 3 m × tan 35° + épaisseur
bpy.ops.bim.trame_reglages_toit(points="0,30;10,30;10,36;0,36", z=0, forme="QUATRE_PANS", pente=30, epaisseur=0.2, depart=2.5)
assert [r.PredefinedType for r in f.by_type("IfcRoof")] == ["GABLE_ROOF", "HIP_ROOF"]
bpy.ops.bim.trame_reglages_toit(points="0,40;6,40;6,44;0,44", z=0, forme="UN_PAN", pente=15, epaisseur=0.2, depart=2.5)
assert len(f.by_type("IfcRoof")) == 3
bpy.ops.bim.trame_reglages_toit(points="0,50;6,50;6,54;0,54", z=0, forme="PLAT", epaisseur=0.3, depart=2.5)
assert any(ue.get_type(s_).Name == "Toit-terrasse 30 cm" for s_ in f.by_type("IfcSlab"))

# Escalier : de (2,60) vers (6,60), 1 m de large, 2,70 m en 16 marches, centré sur la ligne.
bpy.ops.bim.trame_reglages_escalier(points="2,60;6,60", z=0, largeur=1.0, hauteur=2.7, marches=16)
(esc,) = f.by_type("IfcStairFlight")
eo = tool.Ifc.get_object(esc)
from mathutils import Vector as V
bb = [eo.matrix_world @ V(c) for c in eo.bound_box]
assert round(min(v.y for v in bb), 2) == 59.5 and round(max(v.y for v in bb), 2) == 60.5, [v.y for v in bb]
assert round(max(v.z for v in bb), 2) == 2.7 and round(min(v.x for v in bb), 2) == 2.0
print("TEST OUTILS OK")
