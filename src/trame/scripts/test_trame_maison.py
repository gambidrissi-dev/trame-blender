# Test de bout en bout : une maison R+1 construite uniquement avec les outils Trame,
# enregistrée en IFC puis rouverte. blender -b --python src/trame/scripts/test_trame_maison.py
import os, tempfile
import bpy
bpy.ops.preferences.addon_enable(module="bl_ext.user_default.trame")
import ifcopenshell, ifcopenshell.util.element as ue
import trame.tool as tool
from trame.bim.module.model.trame_panneau import ajouter_etage, activer_etage
from trame.bim.module.model.trame_outils import mur_sous_point
from mathutils import Vector

bpy.ops.bim.create_project()
f = tool.Ifc.get()
rdc = tool.Root.get_default_container()

# Rez-de-chaussée : 4 murs fermés de 10 × 8, dalle, porte, 2 fenêtres, poteau, escalier.
bpy.ops.bim.trame_reglages_mur(points="0,0;10,0;10,8;0,8;0,0", z=0, epaisseur=0.3, hauteur=2.8)
bpy.ops.bim.trame_reglages_dalle(points="0,0;10,0;10,8;0,8", z=0, epaisseur=0.2)
mur_sud, pos = mur_sous_point(Vector((5, 0.1, 0)), 0)
bpy.ops.bim.trame_reglages_porte(mur=mur_sud.id(), position=pos, z=0, largeur=0.9, hauteur=2.1)
mur_est, pos = mur_sous_point(Vector((10.1, 4, 0)), 0)
bpy.ops.bim.trame_reglages_fenetre(mur=mur_est.id(), position=pos, z=0, largeur=1.2, hauteur=1.35, allege=0.9)
mur_nord, pos = mur_sous_point(Vector((3, 8.1, 0)), 0)
bpy.ops.bim.trame_reglages_fenetre(mur=mur_nord.id(), position=pos, z=0, largeur=2.4, hauteur=2.1, allege=0, modele="DOUBLE_PANEL_VERTICAL")
bpy.ops.bim.trame_reglages_poteau(x=5, y=4, z=0, largeur=0.3, profondeur=0.3, hauteur=2.8)
bpy.ops.bim.trame_reglages_escalier(points="1,2;4,2", z=0, largeur=1.0, hauteur=2.8, marches=16, forme="L_GAUCHE")
bpy.ops.bim.trame_creer_materiau(nom="Brique", famille="MACONNERIE", couleur=(0.7, 0.35, 0.25))
bpy.ops.bim.trame_reglages_mur(points="10,0;14,0", z=0, longueur=4, angle=0, epaisseur=0.2, hauteur=1.2, materiau="Brique")

bpy.ops.bim.trame_creer_cote(points="0,0;5,0;10,0", decalage=-1.5, z=0)

# R+1 : murs, plancher, toit deux pans.
r1 = ajouter_etage("R+1", 2.8)
activer_etage(r1)
bpy.ops.bim.trame_reglages_mur(points="0,0;10,0;10,8;0,8;0,0", z=2.8, epaisseur=0.3, hauteur=2.5)
bpy.ops.bim.trame_reglages_dalle(points="0,0;10,0;10,8;0,8", z=2.8, epaisseur=0.2)
bpy.ops.bim.trame_reglages_toit(points="0,0;10,0;10,8;0,8", z=2.8, forme="DEUX_PANS", pente=35, epaisseur=0.25, depart=2.5)
bpy.ops.bim.trame_reglages_velux(x=3, y=1.5, largeur=0.78, hauteur=0.98)
from trame.bim.module.model.trame_terrain import creer_terrain
creer_terrain([(-10, -10, -0.5), (25, -10, 0.0), (25, 20, 1.0), (-10, 20, 0.5), (8, 5, 0.2)])

# Enregistrement en IFC.
chemin = os.path.join(tempfile.gettempdir(), "trame_maison_test.ifc")
if os.path.exists(chemin):
    os.remove(chemin)
bpy.ops.bim.save_project(filepath=chemin, should_save_as=True)
assert os.path.exists(chemin), "fichier IFC non écrit"

# Relecture du fichier, indépendamment de Blender.
g = ifcopenshell.open(chemin)
attendu = {"IfcWall": 9, "IfcSlab": 3, "IfcDoor": 1, "IfcWindow": 3, "IfcColumn": 1, "IfcStairFlight": 2,
           "IfcStair": 1, "IfcRoof": 1, "IfcBuildingStorey": 2, "IfcGeographicElement": 1}
compte = {c: len(g.by_type(c)) for c in attendu}
assert compte == attendu, compte
calques_ifc = {c.Name for c in g.by_type("IfcPresentationLayerWithStyle")}
assert {"Murs", "Dalles", "Toiture", "Menuiseries", "Structure", "Escaliers", "Cotation", "Terrain"} <= calques_ifc
assert len(g.by_type("IfcRelFillsElement")) == 4 and len(g.by_type("IfcRelVoidsElement")) == 4
assert any(ue.get_type(w).Name == "Mur 20 cm brique" for w in g.by_type("IfcWall"))
assert {m.Name for m in g.by_type("IfcMaterial")} >= {"Brique", "Maçonnerie", "Béton"}
assert sum(1 for w in g.by_type("IfcWindow") if ue.get_type(w).Name.startswith("Velux")) == 1
assert g.by_type("IfcGeographicElement")[0].PredefinedType == "TERRAIN"
etage_de = lambda e: ue.get_container(e).Name
assert sorted(etage_de(w) for w in g.by_type("IfcWall")) == ["R+1"] * 4 + ["Rez-de-chaussée"] * 5
assert etage_de(g.by_type("IfcRoof")[0]) == "R+1"
(cote,) = [a for a in g.by_type("IfcAnnotation") if a.ObjectType == "DIMENSION"]
assert etage_de(cote) == "Rez-de-chaussée" and ue.get_pset(cote, "Trame_Cote")["Decalage"] == -1.5

# Réouverture dans Trame.
bpy.ops.wm.read_homefile(use_empty=True)
bpy.ops.bim.load_project(filepath=chemin)
h = tool.Ifc.get()
assert h is not None and len(h.by_type("IfcWall")) == 9
objets = [o for o in bpy.data.objects if tool.Ifc.get_entity(o) and tool.Ifc.get_entity(o).is_a("IfcWall")]
assert len(objets) == 9, len(objets)
print("TEST MAISON OK", compte)
