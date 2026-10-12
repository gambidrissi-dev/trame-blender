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
bpy.ops.bim.trame_reglages_escalier(points="1,2;5,2", z=0, largeur=1.0, hauteur=2.8, marches=16)

bpy.ops.bim.trame_creer_cote(points="0,0;5,0;10,0", decalage=-1.5, z=0)

# R+1 : murs, plancher, toit deux pans.
r1 = ajouter_etage("R+1", 2.8)
activer_etage(r1)
bpy.ops.bim.trame_reglages_mur(points="0,0;10,0;10,8;0,8;0,0", z=2.8, epaisseur=0.3, hauteur=2.5)
bpy.ops.bim.trame_reglages_dalle(points="0,0;10,0;10,8;0,8", z=2.8, epaisseur=0.2)
bpy.ops.bim.trame_reglages_toit(points="0,0;10,0;10,8;0,8", z=2.8, forme="DEUX_PANS", pente=35, epaisseur=0.25, depart=2.5)

# Enregistrement en IFC.
chemin = os.path.join(tempfile.gettempdir(), "trame_maison_test.ifc")
if os.path.exists(chemin):
    os.remove(chemin)
bpy.ops.bim.save_project(filepath=chemin, should_save_as=True)
assert os.path.exists(chemin), "fichier IFC non écrit"

# Relecture du fichier, indépendamment de Blender.
g = ifcopenshell.open(chemin)
attendu = {"IfcWall": 8, "IfcSlab": 2, "IfcDoor": 1, "IfcWindow": 2, "IfcColumn": 1, "IfcStairFlight": 1,
           "IfcRoof": 1, "IfcBuildingStorey": 2}
compte = {c: len(g.by_type(c)) for c in attendu}
assert compte == attendu, compte
calques_ifc = {c.Name for c in g.by_type("IfcPresentationLayerWithStyle")}
assert {"Murs", "Dalles", "Toiture", "Menuiseries", "Structure", "Escaliers", "Cotation"} <= calques_ifc
assert len(g.by_type("IfcRelFillsElement")) == 3 and len(g.by_type("IfcRelVoidsElement")) == 3
etage_de = lambda e: ue.get_container(e).Name
assert sorted(etage_de(w) for w in g.by_type("IfcWall")) == ["R+1"] * 4 + ["Rez-de-chaussée"] * 4
assert etage_de(g.by_type("IfcRoof")[0]) == "R+1"
(cote,) = [a for a in g.by_type("IfcAnnotation") if a.ObjectType == "DIMENSION"]
assert etage_de(cote) == "Rez-de-chaussée" and ue.get_pset(cote, "Trame_Cote")["Decalage"] == -1.5

# Réouverture dans Trame.
bpy.ops.wm.read_homefile(use_empty=True)
bpy.ops.bim.load_project(filepath=chemin)
h = tool.Ifc.get()
assert h is not None and len(h.by_type("IfcWall")) == 8
objets = [o for o in bpy.data.objects if tool.Ifc.get_entity(o) and tool.Ifc.get_entity(o).is_a("IfcWall")]
assert len(objets) == 8, len(objets)
print("TEST MAISON OK", compte)
