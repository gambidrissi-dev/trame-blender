# Test des outils Trame (mur, dalle, porte, fenêtre) : blender -b --python src/trame/scripts/test_trame_outils.py
import bpy, math
bpy.ops.preferences.addon_enable(module="bl_ext.user_default.trame")
import json
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
assert ue.get_type(mur).Name == "Mur 30 cm maçonnerie" and ue.get_container(mur)

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
assert ue.get_type(dalle).Name == "Dalle 25 cm béton"
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
assert ue.get_type(porte).Name == "Porte 90 × 210 battante à gauche"
assert len(f.by_type("IfcRelFillsElement")) == 1
op = tool.Ifc.get_object(porte)
# 90 cm de passage + chambranle de Bonsai de part et d'autre.
assert round(op.location.y, 2) == 4.55 and 0.9 <= round(op.dimensions.x, 2) <= 1.0, (op.location, op.dimensions)

# Fenêtre avec allège de 1 m.
bpy.ops.bim.trame_reglages_fenetre(mur=mur.id(), position=1.0, z=0, largeur=1.0, hauteur=1.2, allege=1.0)
(fenetre,) = f.by_type("IfcWindow")
assert ue.get_type(fenetre).Name == "Fenêtre 100 × 120 un vantail"
assert len(f.by_type("IfcRelFillsElement")) == 2
assert round(tool.Ifc.get_object(fenetre).location.z, 2) == 1.0
assert json.loads(ue.get_pset(ue.get_type(fenetre), "BBIM_Window")["Data"])["overall_width"] == 1.0

# Porte battante à droite, ouverte de l'autre côté du mur : type dédié, porte basculée.
x_avant = tool.Ifc.get_object(porte).matrix_world.translation.x
bpy.ops.bim.trame_reglages_porte(mur=mur.id(), position=4.3, z=0, largeur=0.8, hauteur=2.1, modele="SINGLE_SWING_RIGHT", retourner=True)
porte2 = [d for d in f.by_type("IfcDoor") if d != porte][0]
assert ue.get_type(porte2).Name == "Porte 80 × 210 battante à droite"
assert json.loads(ue.get_pset(ue.get_type(porte2), "BBIM_Door")["Data"])["door_type"] == "SINGLE_SWING_RIGHT"
assert len(f.by_type("IfcRelFillsElement")) == 3
assert abs(tool.Ifc.get_object(porte2).matrix_world.translation.x - x_avant) > 0.05  # passée de l'autre côté

# Mur accroché au bout d'un mur existant : raccordé automatiquement.
liaisons = len(f.by_type("IfcRelConnectsPathElements"))
bpy.ops.bim.trame_reglages_mur(points="1,7;5,7", z=0, longueur=4, angle=0, epaisseur=0.2, hauteur=2.5)
assert len(f.by_type("IfcRelConnectsPathElements")) == liaisons + 1

# Poteau 25 × 40 centré au point cliqué.
bpy.ops.bim.trame_reglages_poteau(x=3, y=4, z=0, largeur=0.25, profondeur=0.4, hauteur=2.7)
(poteau,) = f.by_type("IfcColumn")
po = tool.Ifc.get_object(poteau)
assert ue.get_type(poteau).Name == "Poteau 25 × 40 béton"
assert sorted(round(v, 2) for v in po.dimensions) == [0.25, 0.4, 2.7] and tuple(round(v, 2) for v in po.location[:2]) == (3, 4)

# Toits : deux pans sur 10 × 6 (pignons sur les petits côtés), quatre pans, un pan, terrasse.
bpy.ops.bim.trame_reglages_toit(points="0,20;10,20;10,26;0,26", z=0, forme="DEUX_PANS", pente=35, epaisseur=0.25, depart=2.5, debord=0)
toits = f.by_type("IfcRoof")
assert len(toits) == 1 and toits[0].PredefinedType == "GABLE_ROOF"
to = tool.Ifc.get_object(toits[0])
assert tuple(round(v, 1) for v in to.dimensions[:2]) == (10, 6) and round(to.location.z, 2) == 2.5
assert 2.0 < to.dimensions.z < 2.6, to.dimensions  # 3 m × tan 35° + épaisseur
bpy.ops.bim.trame_reglages_toit(points="0,30;10,30;10,36;0,36", z=0, forme="QUATRE_PANS", pente=30, epaisseur=0.2, depart=2.5, debord=0)
assert [r.PredefinedType for r in f.by_type("IfcRoof")] == ["GABLE_ROOF", "HIP_ROOF"]
bpy.ops.bim.trame_reglages_toit(points="0,40;6,40;6,44;0,44", z=0, forme="UN_PAN", pente=15, epaisseur=0.2, depart=2.5, debord=0)
assert len(f.by_type("IfcRoof")) == 3
bpy.ops.bim.trame_reglages_toit(points="0,50;6,50;6,54;0,54", z=0, forme="PLAT", epaisseur=0.3, depart=2.5, debord=0)
assert any(ue.get_type(s_).Name == "Toit-terrasse 30 cm béton" for s_ in f.by_type("IfcSlab"))

# Escalier : de (2,60) vers (6,60), 1 m de large, 2,70 m en 16 marches, centré sur la ligne.
bpy.ops.bim.trame_reglages_escalier(points="2,60;6,60", z=0, largeur=1.0, hauteur=2.7, marches=16)
(esc,) = f.by_type("IfcStairFlight")
eo = tool.Ifc.get_object(esc)
from mathutils import Vector as V
bb = [eo.matrix_world @ V(c) for c in eo.bound_box]
assert round(min(v.y for v in bb), 2) == 59.5 and round(max(v.y for v in bb), 2) == 60.5, [v.y for v in bb]
assert round(max(v.z for v in bb), 2) == 2.7 and round(min(v.x for v in bb), 2) == 2.0
# Saisie clavier : « 3,5 » mètres dans la direction de la souris.
from trame.bim.module.model.trame_outils import lire_longueur, point_a_distance
assert lire_longueur("3,5") == 3.5 and lire_longueur("2.") == 2.0 and lire_longueur("") is None and lire_longueur("0") is None
p = point_a_distance(V((1, 1, 0)), V((1, 9, 0)), 3.5)
assert tuple(round(c, 6) for c in p) == (1, 4.5, 0)
assert tuple(point_a_distance(V((0, 0, 0)), V((0, 0, 0)), 2)) == (2, 0, 0)
# Étages : un R+1 à 2,80 m au-dessus, actif ; un mur dessiné dessus y est rangé, à sa hauteur.
from trame.bim.module.model.trame_panneau import ajouter_etage, activer_etage, etages
r1 = ajouter_etage("R+1", 2.8)
activer_etage(r1)
assert [e.Name for e, _ in etages()] == ["R+1", "Rez-de-chaussée"] and round(etages()[0][1], 2) == 2.8
assert tool.Root.get_default_container() == r1 and round(tool.Root.get_default_container_elevation(), 2) == 2.8
bpy.ops.bim.trame_reglages_mur(points="0,70;5,70", z=2.8, longueur=5, angle=0, epaisseur=0.2, hauteur=2.5)
mur_r1 = max(f.by_type("IfcWall"), key=lambda w: w.id())
assert ue.get_container(mur_r1) == r1 and round(tool.Ifc.get_object(mur_r1).location.z, 2) == 2.8
from trame.bim.module.model.trame_outils import hauteur_etage_courant
assert hauteur_etage_courant() is None  # R+1 est le plus haut
activer_etage(etages()[-1][0])
assert round(hauteur_etage_courant(), 2) == 2.8  # le RDC monte jusqu'au R+1

# Coupe sur la ligne (0,80)→(10,80) : caméra au milieu, regard vers +Y (à gauche du tracé).
bpy.ops.bim.trame_reglages_coupe(points="0,80;10,80", nom="Coupe A", profondeur=12)
(dessin,) = [a for a in f.by_type("IfcAnnotation") if a.ObjectType == "DRAWING"]
cam = tool.Ifc.get_object(dessin)
regard = cam.matrix_world.to_3x3() @ V((0, 0, -1))
assert dessin.Name == "Coupe A" and tuple(round(c, 2) for c in cam.location[:2]) == (5, 80)
assert tuple(round(c, 2) for c in regard) == (0, 1, 0) and cam.data.clip_end == 12
# Cotes : géométrie, décalage vers la souris, annotation IFC.
from trame.bim.module.model.trame_plan import geometrie_cote, decalage_vers, attaches, texte_longueur, section, hachures, motif
ligne, n = geometrie_cote([(0, 0), (7, 0), (4, 0)], -1)
assert [tuple(round(c, 6) for c in p) for p in ligne] == [(0, -1), (4, -1), (7, -1)]
assert round(decalage_vers([(0, 0), (7, 0)], (3, 2)), 6) == 2
assert [tuple(round(c, 6) for c in b) for _, b in attaches([(0, 0), (7, 0)], 1.5)] == [(0, 1.5), (7, 1.5)]
assert texte_longueur(3.456) == "3,46"
bpy.ops.bim.trame_creer_cote(points="0,90;4,90;7,90", decalage=-1, z=0)
(cote,) = [a for a in f.by_type("IfcAnnotation") if a.ObjectType == "DIMENSION"]
assert ue.get_pset(cote, "Trame_Cote")["Decalage"] == -1 and ue.get_container(cote) == tool.Root.get_default_container()
assert len(tool.Ifc.get_object(cote).data.vertices) == 3

# Murs coupés : section d'un mur de 5 m × 20 cm à 1 m = 1 contour de 1 m² ; avec une porte = 2 contours.
def aire(c):
    return abs(sum(a.x * b.y - b.x * a.y for a, b in zip(c, c[1:] + c[:1]))) / 2
bpy.ops.bim.trame_reglages_mur(points="0,100;5,100", z=0, longueur=5, angle=0, epaisseur=0.2, hauteur=2.5)
mur_c = max(f.by_type("IfcWall"), key=lambda w: w.id())
contours = section(tool.Ifc.get_object(mur_c), 1.0)
assert len(contours) == 1 and round(aire(contours[0]), 3) == 1.0, [aire(c) for c in contours]
assert motif(mur_c) == "maconnerie"
mur_c2, pos = mur_sous_point(V((2.5, 100.05, 0)), 0)
bpy.ops.bim.trame_reglages_porte(mur=mur_c2.id(), position=pos, z=0, largeur=0.9, hauteur=2.1)
contours = section(tool.Ifc.get_object(mur_c), 1.0)
assert len(contours) == 2, len(contours)
assert motif(f.by_type("IfcColumn")[0]) == "beton"
carre = [V((0, 0, 0)), V((1, 0, 0)), V((1, 1, 0)), V((0, 1, 0))]
segs = hachures(carre, 0, 0.25)
assert len(segs) == 4 and all(round((b - a).length, 6) == 1 for a, b in segs)
# Matériaux : défauts présents avec couleur, création d'un matériau bois, mur dans ce matériau, hachure bois.
from trame.bim.module.model.trame_materiaux import materiaux, famille_de
noms = {m.Name for m in materiaux()}
assert {"Maçonnerie", "Béton", "Bois", "Isolant", "Plâtre"} <= noms
import ifcopenshell.util.element as ue2
beton = next(m for m in materiaux() if m.Name == "Béton")
assert famille_de(beton) == "BETON" and beton.HasRepresentation, "couleur 3D absente"
bpy.ops.bim.trame_creer_materiau(nom="Ossature bois", famille="BOIS", couleur=(0.7, 0.5, 0.3))
bpy.ops.bim.trame_reglages_mur(points="0,110;4,110", z=0, longueur=4, angle=0, epaisseur=0.15, hauteur=2.5, materiau="Ossature bois")
mur_bois = max(f.by_type("IfcWall"), key=lambda w: w.id())
assert ue.get_type(mur_bois).Name == "Mur 15 cm ossature bois" and motif(mur_bois) == "bois"
bpy.ops.bim.trame_reglages_mur(points="0,112;4,112", z=0, longueur=4, angle=0, epaisseur=0.07, hauteur=2.5, materiau="Plâtre")
assert motif(max(f.by_type("IfcWall"), key=lambda w: w.id())) == "platre"
# La couleur du matériau arrive sur l'objet 3D (matériau Blender issu du style IFC).
ob = tool.Ifc.get_object(mur_bois)
couleurs = [tuple(round(c, 2) for c in m.diffuse_color[:3]) for m in ob.data.materials if m]
assert (0.7, 0.5, 0.3) in couleurs, couleurs
# Calques : chaque élément créé par un outil est rangé sur son calque ; masquer/verrouiller un calque.
from trame.bim.module.model.trame_calques import calque_de, calques, basculer, elements_du_calque
nom_calque = lambda e: calque_de(e).Name if calque_de(e) else None
assert nom_calque(mur_bois) == "Murs" and nom_calque(max(f.by_type("IfcWall"), key=lambda w: w.id())) == "Cloisons"
assert nom_calque(porte) == "Menuiseries" and nom_calque(f.by_type("IfcColumn")[0]) == "Structure"
assert nom_calque(f.by_type("IfcRoof")[0]) == "Toiture" and nom_calque(f.by_type("IfcStairFlight")[0]) == "Escaliers"
assert nom_calque(cote) == "Cotation" and nom_calque(dalle) == "Dalles"
murs = calques()["Murs"]
basculer("Murs", "LayerOn")
assert murs.LayerOn is False and all(tool.Ifc.get_object(e).hide_get() for e in elements_du_calque(murs))
basculer("Murs", "LayerOn")
assert murs.LayerOn is True and not tool.Ifc.get_object(mur_bois).hide_get()
basculer("Menuiseries", "LayerBlocked")
assert tool.Ifc.get_object(porte).hide_select is True
# Vision plan : étage du dessous, contour des toits, pointillés.
from trame.bim.module.model.trame_plan import etage_inferieur, contours_toits, pointilles
activer_etage(r1)
assert etage_inferieur() == etages()[-1][0]
activer_etage(etages()[-1][0])
assert etage_inferieur() is None
contours = contours_toits()  # 3 toits paramétriques + 1 toit-terrasse au RDC
assert len(contours) == 4, len(contours)
assert any(sorted((round(p.x, 2), round(p.y, 2)) for p in c) == [(0, 20), (0, 26), (10, 20), (10, 26)] for c in contours)
tirets = pointilles([V((0, 0, 0)), V((1, 0, 0)), V((1, 1, 0)), V((0, 1, 0))], 0, tiret=0.25, vide=0.15)
assert len(tirets) == 12 and all((b - a).length <= 0.2500001 for a, b in tirets)
# Toiture : débord et toit sur le contour des murs.
from trame.bim.module.model.trame_outils import decaler_contour, contour_des_murs
import math
grand = decaler_contour([(0, 0), (4, 0), (4, 3), (0, 3)], 0.5)
assert sorted((round(x, 6), round(y, 6)) for x, y in grand) == [(-0.5, -0.5), (-0.5, 3.5), (4.5, -0.5), (4.5, 3.5)]
activer_etage(r1)
bpy.ops.bim.trame_reglages_mur(points="20,70;28,70;28,76;20,76;20,70", z=2.8, epaisseur=0.3, hauteur=2.5)
contour = contour_des_murs(2.8)
xs, ys = [p[0] for p in contour], [p[1] for p in contour]
assert (round(min(xs), 2), round(max(xs), 2), round(min(ys), 2), round(max(ys), 2)) == (20, 28, 70, 76), contour
nb_toits = len(f.by_type("IfcRoof"))
bpy.ops.bim.trame_reglages_toit(points=";".join(f"{x},{y}" for x, y in contour), z=2.8, forme="DEUX_PANS", pente=30,
                                epaisseur=0.2, depart=2.5, debord=0.5)
toit = max(f.by_type("IfcRoof"), key=lambda r: r.id())
assert len(f.by_type("IfcRoof")) == nb_toits + 1
ot = tool.Ifc.get_object(toit)
assert tuple(round(v, 2) for v in ot.dimensions[:2]) == (9, 7), ot.dimensions
assert round(ot.location.z, 3) == round(2.8 + 2.5 - 0.5 * math.tan(math.radians(30)), 3), ot.location.z
activer_etage(etages()[-1][0])
# Hauteurs des dalles : dessus de la dalle au niveau de l'étage ; toit-terrasse posé sur les murs.
def z_bornes(o):
    bb = [o.matrix_world @ V(c) for c in o.bound_box]
    return round(min(v.z for v in bb), 3), round(max(v.z for v in bb), 3)
assert z_bornes(tool.Ifc.get_object(dalle)) == (-0.25, 0.0), z_bornes(tool.Ifc.get_object(dalle))
terrasse = next(s_ for s_ in f.by_type("IfcSlab") if ue.get_type(s_).Name.startswith("Toit-terrasse"))
assert z_bornes(tool.Ifc.get_object(terrasse)) == (2.5, 2.8)

# Escaliers en L et en U : 2 volées + palier à mi-hauteur, regroupés dans un IfcStair, sur le calque Escaliers.
from trame.bim.module.model.trame_calques import calque_de
for forme, attendu_x, attendu_y in (("L_GAUCHE", None, None), ("U_DROITE", None, None)):
    avant_volees = set(f.by_type("IfcStairFlight"))
    bpy.ops.bim.trame_reglages_escalier(points="40,0;43,0", z=0, largeur=1.0, hauteur=2.8, marches=16, forme=forme)
    volees = sorted(set(f.by_type("IfcStairFlight")) - avant_volees, key=lambda e: e.id())
    assert len(volees) == 2
    escalier = ue.get_aggregate(volees[0])
    assert escalier and escalier.is_a("IfcStair") and ue.get_aggregate(volees[1]) == escalier
    parties = ue.get_parts(escalier)
    (palier,) = [p_ for p_ in parties if p_.is_a("IfcSlab")]
    assert z_bornes(tool.Ifc.get_object(palier))[1] == 1.4  # dessus du palier à mi-hauteur (8 marches sur 16)
    assert calque_de(palier).Name == "Escaliers" and calque_de(volees[0]).Name == "Escaliers"
    hauts = [z_bornes(tool.Ifc.get_object(v_))[1] for v_ in volees]
    assert hauts == [1.4, 2.8], hauts
    o2 = tool.Ifc.get_object(volees[1])
    regard2 = o2.matrix_world.to_3x3() @ V((1, 0, 0))
    if forme == "L_GAUCHE":
        assert tuple(round(c, 3) for c in regard2) == (0, 1, 0), regard2  # la 2e volée part vers la gauche (+Y)
    else:
        assert tuple(round(c, 3) for c in regard2) == (-1, 0, 0), regard2  # demi-tour
        bb2 = [o2.matrix_world @ V(c) for c in o2.bound_box]
        assert max(v.y for v in bb2) <= -0.49, "en U à droite, la 2e volée est du côté droit (-Y)"
# Velux dans le pan sud du toit « sur les murs » du R+1 : posé dans la pente, centré, toit percé.
from trame.bim.module.model.trame_plan import dans_un_toit, ouvertures_etage
from trame.bim.module.model.trame_outils import pan_sous_point
activer_etage(r1)
fen_avant = set(f.by_type("IfcWindow"))
assert pan_sous_point(24, 50) is None
bpy.ops.bim.trame_reglages_velux(x=24, y=50, largeur=0.78, hauteur=0.98)  # hors toit : rien n'est créé
assert set(f.by_type("IfcWindow")) == fen_avant
pan_point, pan_normale = pan_sous_point(24, 71.5)[1:]
bpy.ops.bim.trame_reglages_velux(x=24, y=71.5, largeur=0.78, hauteur=0.98)
(velux,) = set(f.by_type("IfcWindow")) - fen_avant
assert pan_sous_point(24, 71.5) is None or pan_sous_point(24, 71.5)[1].z < pan_point.z - 0.1  # le toit est percé là
assert ue.get_type(velux).Name == "Velux 78 × 98" and ue.get_type(velux).PredefinedType == "SKYLIGHT"
assert dans_un_toit(velux) and velux not in ouvertures_etage()
assert velux.FillsVoids[0].RelatingOpeningElement.VoidsElements[0].RelatingBuildingElement == toit
ov = tool.Ifc.get_object(velux)
monte = ov.matrix_world.to_3x3() @ V((0, 0, 1))
assert round(math.degrees(math.asin(monte.z))) == 30, monte  # l'axe qui monte la fenêtre suit la pente de 30°
assert abs((ov.matrix_world.to_3x3() @ V((0, 1, 0))).dot(pan_normale) + 1) < 1e-3  # profondeur vers l'intérieur
assert all(abs((ov.matrix_world @ V(c) - pan_point).dot(pan_normale)) < 0.3 for c in ov.bound_box)  # dans le pan
centre = sum((ov.matrix_world @ V(c) for c in ov.bound_box), V()) / 8
assert abs(centre.x - 24) < 0.05 and abs(centre.y - 71.5) < 0.1, centre
assert calque_de(velux).Name == "Menuiseries"
activer_etage(etages()[-1][0])
# Terrain : lecture d'un relevé, triangulation, import en IFC, plateforme, courbes de niveau.
from trame.bim.module.model.trame_terrain import lire_points, trianguler, courbes_de_niveau
assert lire_points("x;y;z\n1;2;3,5\n# commentaire\n4\t5\t6\nP7 7 8 9\n10,11,12") == [(1, 2, 3.5), (4, 5, 6), (7, 8, 9), (10, 11, 12)]
pyramide = [(0, 0, 0), (10, 0, 0), (10, 10, 0), (0, 10, 0), (5, 5, 2)]
sommets, triangles = trianguler(pyramide)
assert len(sommets) == 5 and len(triangles) == 4
import tempfile, os
chemin = os.path.join(tempfile.gettempdir(), "trame_releve_test.csv")
with open(chemin, "w") as fichier:
    fichier.write("x;y;z\n" + "\n".join(";".join(str(c).replace(".", ",") for c in p_) for p_ in pyramide))
geo_avant = set(f.by_type("IfcGeographicElement"))
bpy.ops.bim.trame_importer_releve(filepath=chemin)
(terrain,) = set(f.by_type("IfcGeographicElement")) - geo_avant
assert terrain.PredefinedType == "TERRAIN" and ue.get_container(terrain).is_a("IfcSite") and calque_de(terrain).Name == "Terrain"
to_ = tool.Ifc.get_object(terrain)
assert len(to_.data.vertices) == 5 and round(max(v.co.z for v in to_.data.vertices), 3) == 2
courbes = courbes_de_niveau(to_, 0.5)
assert courbes and {round(a.z, 3) for a, b in courbes} == {0.5, 1.0, 1.5}, {round(a.z, 3) for a, b in courbes}
bpy.ops.bim.trame_reglages_terrain(points="0,0;20,0;20,15;0,15", altitude=-0.5)
plateforme = tool.Ifc.get_object(max(f.by_type("IfcGeographicElement"), key=lambda e: e.id()))
assert {round(v.co.z, 3) for v in plateforme.data.vertices} == {-0.5}
# Les courbes de niveau s'arrêtent au bâtiment : un segment qui traverse le R+1 (20..28 × 70..76) est coupé.
from trame.bim.module.model.trame_plan import hors_batiment
activer_etage(r1)
coupe_ = hors_batiment([(V((10, 73, 0)), V((40, 73, 0)))])
assert len(coupe_) == 2 and sorted(round(b.x, 1) for a, b in coupe_)[0] == 20.0, [(a.x, b.x) for a, b in coupe_]
activer_etage(etages()[-1][0])
# Contour des murs malgré une porte et une baie : le tour est complet (bug corrigé).
bpy.ops.bim.trame_reglages_mur(points="60,0;70,0;70,8;60,8;60,0", z=0, epaisseur=0.3, hauteur=2.5)
m_, p_ = mur_sous_point(V((65, 0.1, 0)), 0)
bpy.ops.bim.trame_reglages_porte(mur=m_.id(), position=p_, z=0, largeur=0.9, hauteur=2.1)
m_, p_ = mur_sous_point(V((70.1, 4, 0)), 0)
bpy.ops.bim.trame_reglages_fenetre(mur=m_.id(), position=p_, z=0, largeur=2.4, hauteur=2.1, allege=0)
from shapely.geometry import Polygon as P_
tour = [c for c in [contour_des_murs(0)] if c][0]
xs, ys = [q[0] for q in tour], [q[1] for q in tour]
assert (round(min(xs), 2), round(max(xs), 2), round(min(ys), 2), round(max(ys), 2)) == (60, 70, 0, 8), tour
assert round(P_(tour).area, 1) == 80.0, P_(tour).area  # l'intérieur des pièces est dans l'emprise
assert len(hors_batiment([(V((55, 4, 0)), V((75, 4, 0)))])) == 2
print("TEST OUTILS OK")
